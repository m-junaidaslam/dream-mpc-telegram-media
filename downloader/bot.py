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

BOT_TOKEN=os.environ['TELEGRAM_BOT_TOKEN']
ALLOWED_USER_ID=int(os.environ['TELEGRAM_ALLOWED_USER_ID'])
STOP=threading.Event()
config.STATE_DIR.mkdir(parents=True,exist_ok=True); config.LOG_DIR.mkdir(parents=True,exist_ok=True)
logger=logging.getLogger('media-downloader'); logger.setLevel(logging.INFO)
if not logger.handlers:
    from logging.handlers import RotatingFileHandler
    fh=RotatingFileHandler(config.LOG_FILE,maxBytes=5*1024*1024,backupCount=5,encoding='utf-8'); fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s')); logger.addHandler(fh); logger.addHandler(logging.StreamHandler())


def send(text, chat_id=ALLOWED_USER_ID, markup=None):
    try: return tg.send(chat_id,text,markup or ui.persistent_commands())
    except Exception: logger.exception('send failed'); return None

def extract_file(message):
    for typ in ('document','video','audio'):
        if typ in message:
            x=message[typ]; name=x.get('file_name') or f"telegram-{x.get('file_unique_id','unknown')}"
            return {'file_id':x['file_id'],'file_unique_id':x.get('file_unique_id'),'file_name':Path(name).name,'file_size':int(x.get('file_size',0) or 0),'media_type':typ}
    return None

def process_queue():
    with state.LOCK:
        if state.DATA.get('active') or not state.DATA['queue']: state.save(); return
        job=state.DATA['queue'].pop(0); state.save()
    threading.Thread(target=media.perform,args=(job,process_queue),daemon=True).start()

def enqueue(destination):
    with state.LOCK:
        pending=state.DATA.get('pending')
        if not pending: send('There is no pending file.'); return
        state.DATA['pending']=None; state.DATA['awaiting_manual_show_path']=False; state.save()
    dest=media.relative(media.validate_destination(destination)); job={'chat_id':pending['chat_id'],'destination':dest,'file':pending['file']}
    with state.LOCK:
        if state.DATA.get('active'):
            state.DATA['queue'].append(job); pos=len(state.DATA['queue']); state.save(); send(f"Added to queue: {job['file']['file_name']}\nPosition: {pos}"); return
    threading.Thread(target=media.perform,args=(job,process_queue),daemon=True).start()

def status():
    with state.LOCK: active=state.DATA.get('active'); q=len(state.DATA['queue']); recent=list(state.DATA.get('recent_shows',[]))
    lines=['DREAM-MPC Media',f'Free disk: {media.human_size(__import__("shutil").disk_usage(config.MEDIA_ROOT).free)}']
    lines += [f"Active: {active['file']['file_name']}",f"Destination: {active['destination']}"] if active else ['No active import.']
    lines.append(f'Queued files: {q}')
    if recent: lines += ['Recent shows:',*recent]
    send('\n'.join(lines))

def history():
    entries=list(state.DATA.get('history',[])[:20])
    if not entries: send('No media import history yet.'); return
    lines=['Recent media imports:','']
    for x in entries: lines += [f"{x['status'].upper()}: {x['file']}",f"  {x['destination']}",f"  {x['time']}",'']
    send('\n'.join(lines))

def cancel():
    with state.LOCK: active=state.DATA.get('active'); pending=state.DATA.get('pending')
    if active: media.CANCEL.set(); send('Cancellation requested.')
    elif pending:
        with state.LOCK: state.DATA['pending']=None; state.DATA['awaiting_manual_show_path']=False; state.save()
        send('Pending file cleared.')
    else: send('Nothing is pending or importing.')

def show_selection():
    with state.LOCK:
        pending=state.DATA.get('pending'); recent=list(state.DATA.get('recent_shows',[]))[:2]
    if not pending: send('There is no pending file.'); return
    suggestion=suggestions.suggest_show_destination(pending['file']['file_name'],pending.get('caption',''),recent)
    with state.LOCK: state.DATA['pending']['suggested_show']=suggestion; state.DATA['awaiting_manual_show_path']=True; state.save()
    text='Choose a show destination, or type it directly without the Shows/ prefix.\nExample: The Neighborhood/Season 08'
    tg.send(ALLOWED_USER_ID,text,ui.show_keyboard(recent,suggestion) or ui.persistent_commands())

def process_callback(q):
    cid=q.get('id'); uid=q.get('from',{}).get('id'); data=q.get('data','')
    if uid != ALLOWED_USER_ID: tg.answer(cid,'Not authorized'); return
    tg.answer(cid)
    if data=='cat:shows': show_selection(); return
    if data in ('cat:movies','cat:music','cat:home'): enqueue(data.split(':')[1].title()); return
    if data.startswith('show:recent:'):
        try: enqueue(state.DATA['recent_shows'][int(data.rsplit(':',1)[1])])
        except Exception: send('That recent destination is no longer available.')
        return
    if data=='show:suggested':
        suggestion=(state.DATA.get('pending') or {}).get('suggested_show')
        if suggestion: enqueue(suggestion)
        else: send('No suggestion is currently available.')

def process_message(m):
    if m.get('from',{}).get('id') != ALLOWED_USER_ID: return
    text=(m.get('text') or '').strip(); lowered=text.casefold()
    if lowered in ('status','/status'): status(); return
    if lowered in ('history','/history'): history(); return
    if lowered in ('cancel','/cancel'): cancel(); return
    f=extract_file(m)
    if f:
        with state.LOCK: state.DATA['pending']={'chat_id':m['chat']['id'],'file':f,'caption':m.get('caption','')}; state.DATA['awaiting_manual_show_path']=False; state.save()
        tg.send(ALLOWED_USER_ID,f"File received\n\n{f['file_name']}\nSize: {media.human_size(f['file_size'])}\n\nWhat is it?",ui.category_keyboard()); return
    with state.LOCK: pending=state.DATA.get('pending'); manual=state.DATA.get('awaiting_manual_show_path',False)
    if text and pending and manual:
        path=text if text.casefold().startswith('shows/') else f'Shows/{text}'
        try: enqueue(path)
        except Exception as exc: send(f'Invalid destination: {exc}')

def recover():
    media.cleanup_stale_parts()
    with state.LOCK:
        interrupted=state.DATA.get('active')
        if interrupted:
            media.remove_file(interrupted.get('telegram_source')); media.remove_file(interrupted.get('temporary_path')); media.clean_bot_temp(BOT_TOKEN)
            try: media.remove_file(media.validate_destination(interrupted['destination'])/f".{Path(interrupted['file']['file_name']).name}.part")
            except Exception: pass
            interrupted.pop('telegram_source',None); interrupted.pop('temporary_path',None); state.DATA['queue'].insert(0,interrupted); state.DATA['active']=None
        state.save()
    process_queue()

def main():
    logger.info('DREAM-MPC Media Downloader starting'); recover(); config.HEALTH_FILE.write_text(str(int(time.time()))); offset=int(state.DATA.get('offset',0) or 0)
    send('DREAM-MPC Media Downloader is ready.')
    while not STOP.is_set():
        try:
            config.HEALTH_FILE.write_text(str(int(time.time())))
            updates=tg.call('getUpdates',{'offset':offset,'timeout':30,'allowed_updates':json.dumps(['message','callback_query'])},timeout=45)
            for u in updates:
                offset=u['update_id']+1
                with state.LOCK: state.DATA['offset']=offset; state.save()
                if u.get('callback_query'): process_callback(u['callback_query'])
                elif u.get('message'): process_message(u['message'])
        except Exception as exc: logger.exception('Polling error: %s',exc); time.sleep(5)

def shutdown(*_):
    STOP.set(); media.CANCEL.set()
    try: config.HEALTH_FILE.unlink(missing_ok=True)
    except Exception: pass
signal.signal(signal.SIGTERM,shutdown); signal.signal(signal.SIGINT,shutdown)
if __name__=='__main__': main()
