import json
import os
import urllib.error
import urllib.parse
import urllib.request


BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']

API_BASE = os.environ.get(
    'TELEGRAM_BOT_API_BASE',
    'http://telegram-bot-api:8081'
).rstrip('/')


# ============================================================
# TELEGRAM API CALL
# ============================================================

def call(method, params=None, timeout=60):
    url = f'{API_BASE}/bot{BOT_TOKEN}/{method}'

    data = (
        urllib.parse.urlencode(params).encode('utf-8')
        if params is not None
        else None
    )

    request = urllib.request.Request(
        url,
        data=data
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout
        ) as response:
            raw = response.read().decode('utf-8')

    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode(
                'utf-8',
                errors='replace'
            )
        except Exception:
            body = ''

        raise RuntimeError(
            f'Telegram API HTTP error '
            f'{exc.code} for {method}: {body}'
        ) from exc

    except urllib.error.URLError as exc:
        raise RuntimeError(
            f'Telegram API connection error '
            f'for {method}: {exc.reason}'
        ) from exc

    except TimeoutError as exc:
        raise RuntimeError(
            f'Telegram API timeout '
            f'for {method}'
        ) from exc

    try:
        result = json.loads(raw)

    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f'Telegram API returned invalid JSON '
            f'for {method}'
        ) from exc

    if not isinstance(result, dict):
        raise RuntimeError(
            f'Telegram API returned an unexpected '
            f'response for {method}'
        )

    if not result.get('ok'):
        description = result.get(
            'description',
            'Unknown Telegram API error'
        )

        error_code = result.get(
            'error_code'
        )

        if error_code:
            raise RuntimeError(
                f'Telegram API error '
                f'{error_code} for {method}: '
                f'{description}'
            )

        raise RuntimeError(
            f'Telegram API error '
            f'for {method}: {description}'
        )

    return result.get('result')


# ============================================================
# SEND MESSAGE
# ============================================================

def send(chat_id, text, markup=None):
    params = {
        'chat_id': chat_id,
        'text': text
    }

    if markup is not None:
        params['reply_markup'] = json.dumps(
            markup
        )

    return call(
        'sendMessage',
        params
    )


# ============================================================
# EDIT MESSAGE
# ============================================================

def edit(chat_id, message_id, text):
    try:
        return call(
            'editMessageText',
            {
                'chat_id': chat_id,
                'message_id': message_id,
                'text': text
            }
        )

    except Exception:
        # Progress updates are best-effort.
        # A failed edit must never fail the media import.
        return None


# ============================================================
# ANSWER CALLBACK
# ============================================================

def answer(callback_id, text=None):
    params = {
        'callback_query_id': callback_id
    }

    if text:
        params['text'] = text

    return call(
        'answerCallbackQuery',
        params
    )