import os
from pathlib import Path


# ============================================================
# HELPERS
# ============================================================

def env_int(name, default, minimum=0):
    value = int(os.environ.get(name, str(default)))

    if value < minimum:
        raise ValueError(
            f'{name} must be at least {minimum}, got {value}'
        )

    return value


# ============================================================
# PATHS
# ============================================================

MEDIA_ROOT = Path(
    os.environ.get(
        'MEDIA_ROOT',
        '/media'
    )
).resolve()

TELEGRAM_DATA_ROOT = Path(
    os.environ.get(
        'TELEGRAM_DATA_ROOT',
        '/var/lib/telegram-bot-api'
    )
).resolve()


# ============================================================
# USER-CONFIGURABLE BEHAVIOR
# ============================================================

WARNING_FREE_GB = env_int(
    'WARNING_FREE_GB',
    30,
    minimum=0
)

MINIMUM_FREE_GB = env_int(
    'MINIMUM_FREE_GB',
    10,
    minimum=0
)

HISTORY_LIMIT = env_int(
    'HISTORY_LIMIT',
    50,
    minimum=1
)

RECENT_SHOW_LIMIT = env_int(
    'RECENT_SHOW_LIMIT',
    2,
    minimum=1
)

COPY_BUFFER_MB = env_int(
    'COPY_BUFFER_MB',
    4,
    minimum=1
)

PROGRESS_UPDATE_SECONDS = env_int(
    'PROGRESS_UPDATE_SECONDS',
    10,
    minimum=1
)

STALE_PART_HOURS = env_int(
    'STALE_PART_HOURS',
    24,
    minimum=1
)

DISK_CHECK_SECONDS = env_int(
    'DISK_CHECK_SECONDS',
    300,
    minimum=1
)


# ============================================================
# MEDIA CATEGORIES
# ============================================================

MEDIA_CATEGORIES = {
    'home': 'Home',
    'shows': 'Shows',
    'movies': 'Movies',
    'music': 'Music',
}


# ============================================================
# APPLICATION PATHS
# ============================================================

STATE_DIR = Path('/app/state')
LOG_DIR = Path('/app/logs')

STATE_FILE = STATE_DIR / 'state.json'
HEALTH_FILE = STATE_DIR / 'healthy'
LOG_FILE = LOG_DIR / 'media-downloader.log'


# ============================================================
# DERIVED VALUES
# ============================================================

COPY_BUFFER_SIZE = COPY_BUFFER_MB * 1024 * 1024