import json
import os
import threading
from config import STATE_FILE, HISTORY_LIMIT, RECENT_SHOW_LIMIT

LOCK = threading.RLock()
DEFAULT = {
    'offset': 0, 'last_destination': None, 'recent_shows': [], 'pending': None,
    'queue': [], 'active': None, 'history': [], 'low_disk_notified': False,
    'awaiting_manual_show_path': False,
}


def load():
    if not STATE_FILE.exists():
        return dict(DEFAULT)
    try:
        data = json.loads(STATE_FILE.read_text(encoding='utf-8'))
        result = dict(DEFAULT); result.update(data)
        result['queue'] = result['queue'] if isinstance(result.get('queue'), list) else []
        result['history'] = result['history'] if isinstance(result.get('history'), list) else []
        result['recent_shows'] = result['recent_shows'] if isinstance(result.get('recent_shows'), list) else []
        result['recent_shows'] = result['recent_shows'][:RECENT_SHOW_LIMIT]
        return result
    except Exception:
        return dict(DEFAULT)


DATA = load()


def save():
    with LOCK:
        tmp = STATE_FILE.with_suffix('.tmp')
        tmp.write_text(json.dumps(DATA, indent=2, ensure_ascii=False), encoding='utf-8')
        os.replace(tmp, STATE_FILE)


def remember_show(path):
    if not path.lower().startswith('shows/'):
        return
    with LOCK:
        recent = [x for x in DATA.get('recent_shows', []) if x != path]
        recent.insert(0, path)
        DATA['recent_shows'] = recent[:RECENT_SHOW_LIMIT]
        save()


def add_history(filename, destination, size, status, timestamp):
    with LOCK:
        DATA['history'].insert(0, {'time': timestamp, 'file': filename, 'destination': destination, 'size': int(size or 0), 'status': status})
        DATA['history'] = DATA['history'][:HISTORY_LIMIT]
        save()
