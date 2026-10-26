"""Content-addressed checkpoints and per-job timings; never cache failed stages."""
import hashlib
import json
import os
import time
import uuid
import threading
_WRITE_LOCK=threading.Lock()
from pathlib import Path

ROOT = Path(__file__).parent
SCHEMA = 'recipe-pipeline-v2'

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def file_digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def rules_digest(files, settings=None):
    return digest({'schema':SCHEMA,'files':{name:file_digest(ROOT/name) for name in files},'settings':settings})

def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with _WRITE_LOCK:
        temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
            os.replace(temp,path)
        finally:
            temp.unlink(missing_ok=True)


class PipelineState:
    def __init__(self,folder,cache_root,notify=lambda text:None):
        self.folder=Path(folder);self.cache_root=Path(cache_root);self.notify=notify
        self.folder.mkdir(parents=True,exist_ok=True)
        path=self.folder/'timings.json'
        try:self.timings=json.loads(path.read_text(encoding='utf-8'))
        except (OSError,ValueError):self.timings=[]

    def run(self,name,label,input_key,rule_key,callback,cache=True,cache_when=lambda value:True):
        key=digest({'stage':name,'input':input_key,'rules':rule_key})
        path=self.cache_root/name/(key+'.json')
        started=time.time();hit=False;state='failed'
        event={'stage':name,'label':label,'started':started,'cache_hit':False,'state':'running'}
        write_json(self.folder/'stage-status.json',event)
        self.notify(label)
        try:
            if cache and path.exists():
                try:
                    saved=json.loads(path.read_text(encoding='utf-8'))
                    if saved.get('key')==key and saved.get('value_digest')==digest(saved['value']):
                        value=saved['value'];hit=True
                except (OSError,ValueError,KeyError,TypeError):pass
            if not hit:
                value=callback()
                if cache and cache_when(value):write_json(path,{'key':key,'value_digest':digest(value),'value':value})
            state='completed'
            return value
        except Exception as error:
            import re
            message=re.sub(r'https?://\S+', '[链接已隐藏]', str(error))
            message=re.sub(r'(?i)(cookie|token|authorization|api[_-]?key)\s*[:=]\s*\S+', r'\1=[已隐藏]', message)
            event['error']=message[:400]
            raise
        finally:
            event.update(seconds=round(time.time()-started,3),cache_hit=hit,state=state)
            self.timings.append(event)
            write_json(self.folder/'timings.json',self.timings)
            write_json(self.folder/'stage-status.json',event)

    def snapshot(self):
        return {'stages':self.timings,'total_seconds':round(sum(x.get('seconds',0) for x in self.timings),3)}
