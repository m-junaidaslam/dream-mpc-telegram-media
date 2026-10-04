import os
from pathlib import Path

# User-configurable behavior. Edit these defaults or override with env vars.
MEDIA_ROOT = Path(os.environ.get('MEDIA_ROOT', '/media')).resolve()
TELEGRAM_DATA_ROOT = Path(os.environ.get('TELEGRAM_DATA_ROOT', '/var/lib/telegram-bot-api')).resolve()
WARNING_FREE_GB = int(os.environ.get('WARNING_FREE_GB', '30'))
MINIMUM_FREE_GB = int(os.environ.get('MINIMUM_FREE_GB', '10'))
HISTORY_LIMIT = int(os.environ.get('HISTORY_LIMIT', '50'))
RECENT_SHOW_LIMIT = int(os.environ.get('RECENT_SHOW_LIMIT', '2'))
COPY_BUFFER_MB = int(os.environ.get('COPY_BUFFER_MB', '4'))
PROGRESS_UPDATE_SECONDS = int(os.environ.get('PROGRESS_UPDATE_SECONDS', '10'))
STALE_PART_HOURS = int(os.environ.get('STALE_PART_HOURS', '24'))
DISK_CHECK_SECONDS = int(os.environ.get('DISK_CHECK_SECONDS', '300'))

# Public categories offered by the bot. Change labels/folders here later.
MEDIA_CATEGORIES = {
    'home': 'Home',
    'shows': 'Shows',
    'movies': 'Movies',
    'music': 'Music',
}

STATE_DIR = Path('/app/state')
LOG_DIR = Path('/app/logs')
STATE_FILE = STATE_DIR / 'state.json'
HEALTH_FILE = STATE_DIR / 'healthy'
LOG_FILE = LOG_DIR / 'media-downloader.log'
COPY_BUFFER_SIZE = COPY_BUFFER_MB * 1024 * 1024
