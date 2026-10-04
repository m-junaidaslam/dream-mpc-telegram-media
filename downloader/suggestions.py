import re

EPISODE_RE = re.compile(r'(?i)^(?P<show>.*?)[ ._-]+S(?P<season>\d{1,2})E\d{1,3}(?:\b|[ ._-])')
NOISE_RE = re.compile(r'[._]+')


def suggest_show_destination(filename, caption='', recent_shows=None):
    recent_shows = recent_shows or []
    for source in (filename, caption):
        if not source:
            continue
        match = EPISODE_RE.search(source)
        if not match:
            continue
        show = NOISE_RE.sub(' ', match.group('show')).strip(' -_.')
        show = re.sub(r'\s+', ' ', show)
        if not show:
            continue
        season = int(match.group('season'))
        candidate = f'Shows/{show}/Season {season:02d}'
        # Prefer an existing recent path with the same normalized show/season.
        norm = candidate.casefold()
        for existing in recent_shows:
            if existing.casefold() == norm:
                return existing
        return candidate
    return None
