import json
import os
import urllib.parse
import urllib.request

BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
API_BASE = os.environ.get('TELEGRAM_BOT_API_BASE', 'http://telegram-bot-api:8081')


def call(method, params=None, timeout=60):
    url = f'{API_BASE}/bot{BOT_TOKEN}/{method}'
    data = urllib.parse.urlencode(params).encode('utf-8') if params is not None else None
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=timeout) as response:
        result = json.loads(response.read().decode('utf-8'))
    if not result.get('ok'):
        raise RuntimeError(f'Telegram API error: {result}')
    return result.get('result')


def send(chat_id, text, markup=None):
    params = {'chat_id': chat_id, 'text': text}
    if markup is not None:
        params['reply_markup'] = json.dumps(markup)
    return call('sendMessage', params)


def edit(chat_id, message_id, text):
    try:
        return call('editMessageText', {'chat_id': chat_id, 'message_id': message_id, 'text': text})
    except Exception:
        return None


def answer(callback_id, text=None):
    params = {'callback_query_id': callback_id}
    if text: params['text'] = text
    return call('answerCallbackQuery', params)
