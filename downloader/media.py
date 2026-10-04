import os
import shutil
import threading
import time
from pathlib import Path
import config
import state
import telegram_api as tg

CANCEL = threading.Event()
IMPORT_LOCK = threading.Lock()


def human_size(size):
    v=float(size or 0)
    for u in ('B','KB','MB','GB','TB'):
        if v < 1024: return f'{v:.1f} {u}'
        v/=1024
    return f'{v:.1f} PB'


def validate_destination(text):
    text=text.strip().replace('\\','/')
    if not text or ':' in text or text.startswith('/'): raise ValueError('Invalid destination')
    raw=text.split('/')
    if any(x.strip() in ('.','..') for x in raw): raise ValueError('Path traversal is not allowed')
    parts=[x.strip() for x in raw if x.strip()]
    root=parts[0].lower() if parts else ''
    if root not in config.MEDIA_CATEGORIES: raise ValueError('Unsupported destination')
    dest=config.MEDIA_ROOT.joinpath(config.MEDIA_CATEGORIES[root],*parts[1:]).resolve()
    try: dest.relative_to(config.MEDIA_ROOT)
    except ValueError as exc: raise ValueError('Destination is outside media root') from exc
    return dest


def relative(dest): return str(dest.relative_to(config.MEDIA_ROOT)).replace('\\','/')

def remove_file(path):
    if not path: return
    try:
        p=Path(path)
        if p.is_file(): p.unlink()
    except Exception: pass


def clean_bot_temp(bot_token):
    d=config.TELEGRAM_DATA_ROOT / bot_token / 'temp'
    if not d.exists(): return
    for item in d.iterdir():
        try:
            if item.is_file() or item.is_symlink(): item.unlink()
            elif item.is_dir(): shutil.rmtree(item)
        except Exception: pass


def cleanup_stale_parts():
    cutoff=time.time()-config.STALE_PART_HOURS*3600
    for root in config.MEDIA_CATEGORIES.values():
        base=config.MEDIA_ROOT/root
        if not base.exists(): continue
        for p in base.rglob('.*.part'):
            try:
                if p.is_file() and p.stat().st_mtime < cutoff: p.unlink()
            except Exception: pass


def verify_space(size):
    free=shutil.disk_usage(config.MEDIA_ROOT).free
    if free-int(size or 0) < config.MINIMUM_FREE_GB*1024**3:
        raise RuntimeError(f'Not enough disk space. Free: {human_size(free)}')


def copy_file(source,temp,chat_id,message_id,filename,destination):
    total=source.stat().st_size; copied=0; last=0
    with source.open('rb') as src,temp.open('wb') as dst:
        while True:
            if CANCEL.is_set(): raise InterruptedError('Import cancelled')
            block=src.read(config.COPY_BUFFER_SIZE)
            if not block: break
            dst.write(block); copied+=len(block); now=time.time()
            if message_id and now-last >= config.PROGRESS_UPDATE_SECONDS:
                tg.edit(chat_id,message_id,f'Importing {filename}\n{copied/total*100:.0f}% - {human_size(copied)} / {human_size(total)}\nDestination: {destination}')
                last=now
        dst.flush(); os.fsync(dst.fileno())
    return copied


def perform(job, on_done):
    with IMPORT_LOCK:
        CANCEL.clear(); chat=job['chat_id']; info=job['file']; filename=Path(info['file_name']).name
        dest=validate_destination(job['destination']); rel=relative(dest); expected=int(info.get('file_size',0) or 0)
        with state.LOCK: state.DATA['active']=job; state.save()
        temp=None; source=None
        try:
            verify_space(expected); dest.mkdir(parents=True,exist_ok=True); final=dest/filename
            if final.exists(): raise FileExistsError(f'File already exists: {filename}')
            temp=dest/f'.{filename}.part'; remove_file(temp)
            msg=tg.send(chat,f'Preparing import\nFile: {filename}\nDestination: {rel}')
            file=tg.call('getFile',{'file_id':info['file_id']},timeout=300); source=Path(file['file_path'])
            if not source.is_file(): raise FileNotFoundError('Telegram file is not readable')
            with state.LOCK:
                job['telegram_source']=str(source); job['temporary_path']=str(temp); state.DATA['active']=job; state.save()
            actual=source.stat().st_size; verify_space(actual)
            copied=copy_file(source,temp,chat,msg.get('message_id') if msg else None,filename,rel)
            if copied != actual or temp.stat().st_size != actual: raise IOError('Copied size mismatch')
            os.replace(temp,final); remove_file(source)
            state.remember_show(rel)
            state.add_history(filename,rel,actual,'completed',time.strftime('%Y-%m-%d %H:%M:%S'))
            tg.send(chat,f'Media import complete\nFile: {filename}\nSize: {human_size(actual)}\nSaved to: {rel}')
        except InterruptedError:
            remove_file(temp); remove_file(source); state.add_history(filename,rel,expected,'cancelled',time.strftime('%Y-%m-%d %H:%M:%S')); tg.send(chat,f'Import cancelled: {filename}')
        except Exception as exc:
            remove_file(temp); remove_file(source); state.add_history(filename,rel,expected,'failed',time.strftime('%Y-%m-%d %H:%M:%S')); tg.send(chat,f'Media import failed\nFile: {filename}\nReason: {exc}')
        finally:
            with state.LOCK: state.DATA['active']=None; state.save()
            CANCEL.clear(); on_done()
