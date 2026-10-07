import json
import logging
import os
import threading
import time

from config import (
    STATE_FILE,
    HISTORY_LIMIT,
    RECENT_SHOW_LIMIT
)


LOCK = threading.RLock()
logger = logging.getLogger('media-downloader')


DEFAULT = {
    'offset': 0,
    'last_destination': None,
    'recent_shows': [],
    'pending': None,
    'queue': [],
    'active': None,
    'history': [],
    'low_disk_notified': False,
    'awaiting_manual_show_path': False,
}


# ============================================================
# DEFAULT STATE
# ============================================================

def default_state():
    return {
        'offset': 0,
        'last_destination': None,
        'recent_shows': [],
        'pending': None,
        'queue': [],
        'active': None,
        'history': [],
        'low_disk_notified': False,
        'awaiting_manual_show_path': False,
    }


# ============================================================
# LOAD STATE
# ============================================================

def load():
    if not STATE_FILE.exists():
        return default_state()

    try:
        data = json.loads(
            STATE_FILE.read_text(
                encoding='utf-8'
            )
        )

        if not isinstance(data, dict):
            raise ValueError(
                'State file does not contain a JSON object'
            )

        result = default_state()
        result.update(data)

        if not isinstance(
            result.get('queue'),
            list
        ):
            result['queue'] = []

        if not isinstance(
            result.get('history'),
            list
        ):
            result['history'] = []

        if not isinstance(
            result.get('recent_shows'),
            list
        ):
            result['recent_shows'] = []

        result['history'] = (
            result['history'][:HISTORY_LIMIT]
        )

        result['recent_shows'] = (
            result['recent_shows'][:RECENT_SHOW_LIMIT]
        )

        return result

    except Exception:
        logger.exception(
            'Failed to load state file: %s',
            STATE_FILE
        )

        # Preserve the damaged state file instead of silently
        # overwriting it on the next save.
        try:
            timestamp = time.strftime(
                '%Y%m%d-%H%M%S'
            )

            backup = STATE_FILE.with_name(
                f'{STATE_FILE.stem}.corrupt-'
                f'{timestamp}{STATE_FILE.suffix}'
            )

            os.replace(
                STATE_FILE,
                backup
            )

            logger.error(
                'Corrupt state file moved to: %s',
                backup
            )

        except Exception:
            logger.exception(
                'Could not preserve corrupt state file'
            )

        return default_state()


DATA = load()


# ============================================================
# SAVE STATE
# ============================================================

def save():
    with LOCK:
        STATE_FILE.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        tmp = STATE_FILE.with_suffix(
            '.tmp'
        )

        try:
            tmp.write_text(
                json.dumps(
                    DATA,
                    indent=2,
                    ensure_ascii=False
                ),
                encoding='utf-8'
            )

            os.replace(
                tmp,
                STATE_FILE
            )

        except Exception:
            logger.exception(
                'Failed to save state file: %s',
                STATE_FILE
            )

            try:
                tmp.unlink(
                    missing_ok=True
                )
            except Exception:
                logger.exception(
                    'Could not remove failed temporary state file'
                )

            raise


# ============================================================
# RECENT SHOWS
# ============================================================

def remember_show(path):
    if not path.lower().startswith(
        'shows/'
    ):
        return

    with LOCK:
        recent = [
            item
            for item in DATA.get(
                'recent_shows',
                []
            )
            if item != path
        ]

        recent.insert(
            0,
            path
        )

        DATA['recent_shows'] = (
            recent[:RECENT_SHOW_LIMIT]
        )

        save()


# ============================================================
# HISTORY
# ============================================================

def add_history(
    filename,
    destination,
    size,
    status,
    timestamp
):
    with LOCK:
        history = DATA.setdefault(
            'history',
            []
        )

        history.insert(
            0,
            {
                'time': timestamp,
                'file': filename,
                'destination': destination,
                'size': int(size or 0),
                'status': status
            }
        )

        DATA['history'] = (
            history[:HISTORY_LIMIT]
        )

        save()