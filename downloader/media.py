import logging
import os
import shutil
import threading
import time
from pathlib import Path

import config
import state
import telegram_api as tg


CANCEL = threading.Event()
IMPORT_LOCK = threading.Lock()

logger = logging.getLogger('media-downloader')


# ============================================================
# SIZE FORMATTING
# ============================================================

def human_size(size):
    value = float(size or 0)

    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if value < 1024:
            return f'{value:.1f} {unit}'

        value /= 1024

    return f'{value:.1f} PB'


# ============================================================
# DESTINATION VALIDATION
# ============================================================

def validate_destination(text):
    text = text.strip().replace('\\', '/')

    if not text:
        raise ValueError('Invalid destination')

    if ':' in text:
        raise ValueError('Invalid destination')

    if text.startswith('/'):
        raise ValueError('Invalid destination')

    raw = text.split('/')

    if any(
        part.strip() in ('.', '..')
        for part in raw
    ):
        raise ValueError(
            'Path traversal is not allowed'
        )

    parts = [
        part.strip()
        for part in raw
        if part.strip()
    ]

    root = (
        parts[0].lower()
        if parts
        else ''
    )

    if root not in config.MEDIA_CATEGORIES:
        raise ValueError(
            'Unsupported destination'
        )

    dest = config.MEDIA_ROOT.joinpath(
        config.MEDIA_CATEGORIES[root],
        *parts[1:]
    ).resolve()

    try:
        dest.relative_to(config.MEDIA_ROOT)
    except ValueError as exc:
        raise ValueError(
            'Destination is outside media root'
        ) from exc

    return dest


def relative(dest):
    return str(
        dest.relative_to(config.MEDIA_ROOT)
    ).replace('\\', '/')


# ============================================================
# FILE CLEANUP
# ============================================================

def remove_file(path):
    if not path:
        return

    try:
        p = Path(path)

        if p.is_file() or p.is_symlink():
            p.unlink()

    except Exception:
        logger.exception(
            'Failed to remove file: %s',
            path
        )


def clean_bot_temp(bot_token):
    directory = (
        config.TELEGRAM_DATA_ROOT
        / bot_token
        / 'temp'
    )

    if not directory.exists():
        return

    for item in directory.iterdir():
        try:
            if item.is_file() or item.is_symlink():
                item.unlink()

            elif item.is_dir():
                shutil.rmtree(item)

        except Exception:
            logger.exception(
                'Failed to clean Telegram temporary item: %s',
                item
            )


def cleanup_stale_parts():
    cutoff = (
        time.time()
        - config.STALE_PART_HOURS * 3600
    )

    for root in config.MEDIA_CATEGORIES.values():
        base = config.MEDIA_ROOT / root

        if not base.exists():
            continue

        for path in base.rglob('.*.part'):
            try:
                if (
                    path.is_file()
                    and path.stat().st_mtime < cutoff
                ):
                    path.unlink()

                    logger.info(
                        'Removed stale partial file: %s',
                        path
                    )

            except Exception:
                logger.exception(
                    'Failed to inspect/remove stale partial file: %s',
                    path
                )


# ============================================================
# DISK SPACE
# ============================================================

def verify_space(size):
    free = shutil.disk_usage(
        config.MEDIA_ROOT
    ).free

    required = int(size or 0)

    minimum_remaining = (
        config.MINIMUM_FREE_GB
        * 1024 ** 3
    )

    if free - required < minimum_remaining:
        raise RuntimeError(
            'Not enough disk space. '
            f'Free: {human_size(free)}'
        )


# ============================================================
# COPY FILE
# ============================================================

def copy_file(
    source,
    temp,
    chat_id,
    message_id,
    filename,
    destination
):
    total = source.stat().st_size
    copied = 0
    last_progress_update = 0

    with source.open('rb') as src, temp.open('wb') as dst:

        while True:
            if CANCEL.is_set():
                raise InterruptedError(
                    'Import cancelled'
                )

            block = src.read(
                config.COPY_BUFFER_SIZE
            )

            if not block:
                break

            dst.write(block)
            copied += len(block)

            now = time.time()

            if (
                message_id
                and now - last_progress_update
                >= config.PROGRESS_UPDATE_SECONDS
            ):
                if total > 0:
                    percentage = (
                        copied / total * 100
                    )
                else:
                    percentage = 100

                tg.edit(
                    chat_id,
                    message_id,
                    (
                        f'⬇️ Importing\n\n'
                        f'📄 {filename}\n'
                        f'📊 {percentage:.0f}%\n'
                        f'💾 {human_size(copied)} / '
                        f'{human_size(total)}\n'
                        f'📁 {destination}'
                    )
                )

                last_progress_update = now

        dst.flush()
        os.fsync(dst.fileno())

    return copied


# ============================================================
# MEDIA IMPORT
# ============================================================

def perform(job, on_done):
    with IMPORT_LOCK:

        CANCEL.clear()

        chat = job['chat_id']
        info = job['file']

        filename = Path(
            info['file_name']
        ).name

        dest = validate_destination(
            job['destination']
        )

        rel = relative(dest)

        expected = int(
            info.get('file_size', 0) or 0
        )

        # bot.py normally reserves the active slot before
        # starting this worker. Saving again here makes the
        # worker self-contained and keeps the state accurate.
        with state.LOCK:
            state.DATA['active'] = job
            state.save()

        temp = None
        source = None

        try:
            logger.info(
                'Starting import: %s -> %s',
                filename,
                rel
            )

            # Check advertised Telegram file size first.
            verify_space(expected)

            dest.mkdir(
                parents=True,
                exist_ok=True
            )

            final = dest / filename

            if final.exists():
                raise FileExistsError(
                    f'File already exists: {filename}'
                )

            temp = dest / f'.{filename}.part'

            remove_file(temp)

            try:
                msg = tg.send(
                    chat,
                    (
                        f'⏳ Preparing import\n\n'
                        f'📄 {filename}\n'
                        f'📁 Destination: {rel}'
                    )
                )
            except Exception:
                logger.exception(
                    'Could not send preparation message'
                )
                msg = None

            file = tg.call(
                'getFile',
                {
                    'file_id': info['file_id']
                },
                timeout=300
            )

            source = Path(
                file['file_path']
            )

            if not source.is_file():
                raise FileNotFoundError(
                    'Telegram file is not readable'
                )

            with state.LOCK:
                job['telegram_source'] = str(source)
                job['temporary_path'] = str(temp)

                state.DATA['active'] = job
                state.save()

            actual = source.stat().st_size

            # Check again using the actual downloaded size.
            verify_space(actual)

            message_id = (
                msg.get('message_id')
                if msg
                else None
            )

            copied = copy_file(
                source,
                temp,
                chat,
                message_id,
                filename,
                rel
            )

            if copied != actual:
                raise IOError(
                    'Copied size mismatch'
                )

            if not temp.is_file():
                raise IOError(
                    'Temporary file disappeared during import'
                )

            if temp.stat().st_size != actual:
                raise IOError(
                    'Copied size mismatch'
                )

            # Atomic rename within the destination filesystem.
            os.replace(
                temp,
                final
            )

            # Telegram's source copy is no longer required.
            remove_file(source)
            source = None
            temp = None

            state.remember_show(rel)

            state.add_history(
                filename,
                rel,
                actual,
                'completed',
                time.strftime(
                    '%Y-%m-%d %H:%M:%S'
                )
            )

            logger.info(
                'Import completed: %s -> %s (%s)',
                filename,
                rel,
                human_size(actual)
            )

            try:
                tg.send(
                    chat,
                    (
                        f'✅ Media import complete\n\n'
                        f'📄 {filename}\n'
                        f'💾 Size: {human_size(actual)}\n'
                        f'📁 Saved to: {rel}'
                    )
                )
            except Exception:
                logger.exception(
                    'Could not send completion message'
                )

        except InterruptedError:
            logger.info(
                'Import cancelled: %s',
                filename
            )

            remove_file(temp)
            remove_file(source)

            state.add_history(
                filename,
                rel,
                expected,
                'cancelled',
                time.strftime(
                    '%Y-%m-%d %H:%M:%S'
                )
            )

            try:
                tg.send(
                    chat,
                    (
                        f'🚫 Import cancelled\n\n'
                        f'📄 {filename}'
                    )
                )
            except Exception:
                logger.exception(
                    'Could not send cancellation message'
                )

        except Exception as exc:
            logger.exception(
                'Media import failed: %s -> %s',
                filename,
                rel
            )

            remove_file(temp)
            remove_file(source)

            state.add_history(
                filename,
                rel,
                expected,
                'failed',
                time.strftime(
                    '%Y-%m-%d %H:%M:%S'
                )
            )

            try:
                tg.send(
                    chat,
                    (
                        f'❌ Media import failed\n\n'
                        f'📄 {filename}\n'
                        f'⚠️ Reason: {exc}'
                    )
                )
            except Exception:
                logger.exception(
                    'Could not send import failure message'
                )

        finally:
            with state.LOCK:
                state.DATA['active'] = None
                state.save()

            CANCEL.clear()

            try:
                on_done()
            except Exception:
                logger.exception(
                    'Queue continuation failed'
                )