import json
import logging
import os
import signal
import threading
import time
from pathlib import Path

import config
import media
import state
import suggestions
import telegram_api as tg
import ui


BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
ALLOWED_USER_ID = int(os.environ['TELEGRAM_ALLOWED_USER_ID'])

STOP = threading.Event()

config.STATE_DIR.mkdir(parents=True, exist_ok=True)
config.LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger('media-downloader')
logger.setLevel(logging.INFO)

if not logger.handlers:
    from logging.handlers import RotatingFileHandler

    fh = RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )

    fh.setFormatter(
        logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    )

    logger.addHandler(fh)
    logger.addHandler(logging.StreamHandler())


# ============================================================
# TELEGRAM
# ============================================================

def send(text, chat_id=ALLOWED_USER_ID, markup=None):
    try:
        return tg.send(
            chat_id,
            text,
            markup or ui.persistent_commands()
        )
    except Exception:
        logger.exception('send failed')
        return None


# ============================================================
# FILE EXTRACTION
# ============================================================

def extract_file(message):
    for typ in ('document', 'video', 'audio'):
        if typ in message:
            x = message[typ]

            name = (
                x.get('file_name')
                or f"telegram-{x.get('file_unique_id', 'unknown')}"
            )

            return {
                'file_id': x['file_id'],
                'file_unique_id': x.get('file_unique_id'),
                'file_name': Path(name).name,
                'file_size': int(x.get('file_size', 0) or 0),
                'media_type': typ
            }

    return None


# ============================================================
# QUEUE
# ============================================================

def process_queue():
    with state.LOCK:
        queue = state.DATA.setdefault('queue', [])

        if state.DATA.get('active') or not queue:
            return

        job = queue.pop(0)

        # Reserve the worker slot before releasing the lock.
        state.DATA['active'] = job
        state.save()

    threading.Thread(
        target=media.perform,
        args=(job, process_queue),
        daemon=True
    ).start()


def enqueue(destination):
    dest = media.relative(
        media.validate_destination(destination)
    )

    with state.LOCK:
        pending = state.DATA.get('pending')

        if not pending:
            no_pending = True
        else:
            no_pending = False

            job = {
                'chat_id': pending['chat_id'],
                'destination': dest,
                'file': dict(pending['file'])
            }

            state.DATA['pending'] = None
            state.DATA['awaiting_manual_show_path'] = False

            queue = state.DATA.setdefault('queue', [])

            if state.DATA.get('active'):
                queue.append(job)
                position = len(queue)
                state.save()
                queued = True
            else:
                # Reserve the active slot while still holding the lock.
                state.DATA['active'] = job
                state.save()
                queued = False

    if no_pending:
        send('ℹ️ There is no pending file.')
        return

    if queued:
        send(
            f"⏳ Added to queue\n\n"
            f"📄 {job['file']['file_name']}\n"
            f"🔢 Position: {position}"
        )
        return

    threading.Thread(
        target=media.perform,
        args=(job, process_queue),
        daemon=True
    ).start()


# ============================================================
# STATUS
# ============================================================

def status():
    with state.LOCK:
        active = state.DATA.get('active')
        queue_count = len(state.DATA.get('queue', []))
        recent = list(state.DATA.get('recent_shows', []))

    lines = [
        '🖥️ DREAM-MPC Media',
        (
            f'💾 Free disk: '
            f'{media.human_size(__import__("shutil").disk_usage(config.MEDIA_ROOT).free)}'
        )
    ]

    if active:
        lines += [
            f"⬇️ Active: {active['file']['file_name']}",
            f"📁 Destination: {active['destination']}"
        ]
    else:
        lines.append('✅ No active import.')

    lines.append(f'⏳ Queued files: {queue_count}')

    if recent:
        lines += ['📺 Recent shows:', *recent]

    send('\n'.join(lines))


# ============================================================
# HISTORY
# ============================================================

def history():
    with state.LOCK:
        entries = list(
            reversed(state.DATA.get('history', [])[:20])
        )

    if not entries:
        send('ℹ️ No media import history yet.')
        return

    lines = [
        '📜 Recent media imports',
        ''
    ]

    for x in entries:
        icon = {
            'completed': '✅',
            'failed': '❌',
            'cancelled': '🚫'
        }.get(x['status'].lower(), '•')

        lines += [
            f"{icon} {x['status'].upper()}: {x['file']}",
            f"📁 {x['destination']}",
            f"🕒 {x['time']}",
            ''
        ]

    send('\n'.join(lines))


# ============================================================
# CANCEL
# ============================================================

def cancel():
    with state.LOCK:
        active = state.DATA.get('active')
        pending = state.DATA.get('pending')

        if pending and not active:
            state.DATA['pending'] = None
            state.DATA['awaiting_manual_show_path'] = False
            state.save()
            cleared_pending = True
        else:
            cleared_pending = False

    if active:
        media.CANCEL.set()
        send('🛑 Cancellation requested.')

    elif cleared_pending:
        send('🗑️ Pending file cleared.')

    else:
        send('ℹ️ Nothing is pending or importing.')


# ============================================================
# SHOW DESTINATION SELECTION
# ============================================================

def show_selection():
    with state.LOCK:
        pending = state.DATA.get('pending')
        recent = list(
            state.DATA.get('recent_shows', [])
        )[:2]

        if pending:
            pending = dict(pending)
            pending['file'] = dict(pending['file'])

    if not pending:
        send('ℹ️ There is no pending file.')
        return

    suggestion = suggestions.suggest_show_destination(
        pending['file']['file_name'],
        pending.get('caption', ''),
        recent
    )

    with state.LOCK:
        current = state.DATA.get('pending')

        # Make sure another Telegram message has not replaced the
        # pending file while the suggestion was being calculated.
        pending_changed = (
            not current
            or current['file'].get('file_id')
            != pending['file'].get('file_id')
        )

        if not pending_changed:
            state.DATA['pending']['suggested_show'] = suggestion
            state.DATA['awaiting_manual_show_path'] = True
            state.save()

    # Never perform Telegram/network operations while holding
    # the state lock.
    if pending_changed:
        send('⚠️ The pending file has changed. Please choose again.')
        return

    text = (
        '📺 Choose a show destination\n\n'
        '💡 Or type it directly without the Shows/ prefix.\n'
        'Example: The Neighborhood/Season 08'
    )

    try:
        tg.send(
            ALLOWED_USER_ID,
            text,
            ui.show_keyboard(recent, suggestion)
            or ui.persistent_commands()
        )
    except Exception:
        logger.exception('Failed to send show selection')
        send('⚠️ Could not display show destinations. Please try again.')


# ============================================================
# CALLBACKS
# ============================================================

def process_callback(q):
    callback_id = q.get('id')
    user_id = q.get('from', {}).get('id')
    data = q.get('data', '')

    if user_id != ALLOWED_USER_ID:
        try:
            tg.answer(callback_id, '⛔ Not authorized')
        except Exception:
            logger.exception('Failed to answer unauthorized callback')
        return

    try:
        tg.answer(callback_id)
    except Exception:
        logger.exception('Failed to answer callback')

    if data == 'cat:shows':
        show_selection()
        return

    if data in ('cat:movies', 'cat:music', 'cat:home'):
        enqueue(data.split(':')[1].title())
        return

    if data.startswith('show:recent:'):
        try:
            index = int(data.rsplit(':', 1)[1])

            with state.LOCK:
                recent = list(
                    state.DATA.get('recent_shows', [])
                )

            if index < 0 or index >= len(recent):
                raise IndexError

            enqueue(recent[index])

        except (ValueError, IndexError):
            send(
                '⚠️ That recent destination is no longer available.'
            )

        except Exception:
            logger.exception('Failed to process recent destination')
            send(
                '⚠️ That recent destination is no longer available.'
            )

        return

    if data == 'show:suggested':
        with state.LOCK:
            pending = state.DATA.get('pending')
            suggestion = (
                pending.get('suggested_show')
                if pending
                else None
            )

        if suggestion:
            enqueue(suggestion)
        else:
            send('ℹ️ No suggestion is currently available.')

        return


# ============================================================
# MESSAGES
# ============================================================

def process_message(m):
    if m.get('from', {}).get('id') != ALLOWED_USER_ID:
        return

    text = (m.get('text') or '').strip()
    lowered = text.casefold()

    if lowered in ('status', '/status', '📊 status'):
        status()
        return

    if lowered in ('history', '/history', '📜 history'):
        history()
        return

    if lowered in ('cancel', '/cancel', '❌ cancel'):
        cancel()
        return

    f = extract_file(m)

    if f:
        with state.LOCK:
            existing_pending = state.DATA.get('pending')

            if existing_pending:
                existing_name = (
                    existing_pending
                    .get('file', {})
                    .get('file_name', 'unknown file')
                )
            else:
                existing_name = None

        if existing_name:
            send(
                '⚠️ Another file is already waiting for a destination:\n\n'
                f'📄 {existing_name}\n\n'
                'Choose its destination or press ❌ Cancel before '
                'sending another file.'
            )
            return

        with state.LOCK:
            state.DATA['pending'] = {
                'chat_id': m['chat']['id'],
                'file': f,
                'caption': m.get('caption', '')
            }

            state.DATA['awaiting_manual_show_path'] = False
            state.save()

        try:
            tg.send(
                ALLOWED_USER_ID,
                (
                    f"📥 File received\n\n"
                    f"📄 {f['file_name']}\n"
                    f"💾 Size: {media.human_size(f['file_size'])}\n\n"
                    f"❓ What is it?"
                ),
                ui.category_keyboard()
            )
        except Exception:
            logger.exception('Failed to send category selection')
            send(
                '⚠️ File received, but the category menu could not '
                'be displayed.\n\n'
                'Please press ❌ Cancel and send the file again.'
            )

        return

    with state.LOCK:
        pending = state.DATA.get('pending')
        manual = state.DATA.get(
            'awaiting_manual_show_path',
            False
        )

    if text and pending and manual:
        path = (
            text
            if text.casefold().startswith('shows/')
            else f'Shows/{text}'
        )

        try:
            enqueue(path)
        except Exception as exc:
            logger.exception('Invalid manual destination')
            send(f'⚠️ Invalid destination: {exc}')


# ============================================================
# RECOVERY
# ============================================================

def recover():
    media.cleanup_stale_parts()

    with state.LOCK:
        interrupted = state.DATA.get('active')

        if interrupted:
            media.remove_file(
                interrupted.get('telegram_source')
            )

            media.remove_file(
                interrupted.get('temporary_path')
            )

            media.clean_bot_temp(BOT_TOKEN)

            try:
                destination = media.validate_destination(
                    interrupted['destination']
                )

                filename = Path(
                    interrupted['file']['file_name']
                ).name

                media.remove_file(
                    destination / f'.{filename}.part'
                )

            except Exception:
                logger.exception(
                    'Could not fully clean interrupted import'
                )

            interrupted.pop('telegram_source', None)
            interrupted.pop('temporary_path', None)

            state.DATA.setdefault(
                'queue',
                []
            ).insert(0, interrupted)

            state.DATA['active'] = None

        state.save()

    process_queue()


# ============================================================
# MAIN LOOP
# ============================================================

def main():
    logger.info('DREAM-MPC Media Downloader starting')

    recover()

    config.HEALTH_FILE.write_text(
        str(int(time.time()))
    )

    with state.LOCK:
        offset = int(
            state.DATA.get('offset', 0) or 0
        )

    send('✅ DREAM-MPC Media Downloader is ready.')

    while not STOP.is_set():
        try:
            config.HEALTH_FILE.write_text(
                str(int(time.time()))
            )

            updates = tg.call(
                'getUpdates',
                {
                    'offset': offset,
                    'timeout': 30,
                    'allowed_updates': json.dumps(
                        ['message', 'callback_query']
                    )
                },
                timeout=45
            )

            for u in updates:
                offset = u['update_id'] + 1

                with state.LOCK:
                    state.DATA['offset'] = offset
                    state.save()

                if u.get('callback_query'):
                    process_callback(
                        u['callback_query']
                    )

                elif u.get('message'):
                    process_message(
                        u['message']
                    )

        except Exception as exc:
            logger.exception(
                'Polling error: %s',
                exc
            )

            if not STOP.is_set():
                time.sleep(5)


# ============================================================
# SHUTDOWN
# ============================================================

def shutdown(*_):
    logger.info('Shutdown requested')

    STOP.set()
    media.CANCEL.set()

    try:
        config.HEALTH_FILE.unlink(
            missing_ok=True
        )
    except Exception:
        logger.exception(
            'Could not remove health file'
        )


signal.signal(
    signal.SIGTERM,
    shutdown
)

signal.signal(
    signal.SIGINT,
    shutdown
)


if __name__ == '__main__':
    main()