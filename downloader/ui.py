from config import MEDIA_CATEGORIES


def persistent_commands():
    return {
        'keyboard': [[{'text': 'Status'}, {'text': 'History'}, {'text': 'Cancel'}]],
        'resize_keyboard': True,
        'is_persistent': True,
        'input_field_placeholder': 'Forward a media file...'
    }


def category_keyboard():
    return {'inline_keyboard': [[
        {'text': 'Shows', 'callback_data': 'cat:shows'},
        {'text': 'Movies', 'callback_data': 'cat:movies'},
        {'text': 'Music', 'callback_data': 'cat:music'},
        {'text': 'Home', 'callback_data': 'cat:home'},
    ]]}


def show_keyboard(recent, suggestion=None):
    rows = []
    for i, path in enumerate(recent[:2]):
        display = path[6:] if path.lower().startswith('shows/') else path
        rows.append([{'text': display, 'callback_data': f'show:recent:{i}'}])
    if suggestion and suggestion not in recent[:2]:
        display = suggestion[6:] if suggestion.lower().startswith('shows/') else suggestion
        rows.append([{'text': f'Suggested: {display}', 'callback_data': 'show:suggested'}])
    return {'inline_keyboard': rows} if rows else None
