"""One persisted worker, deliberately no interactive browser login in cloud."""
import json
import os
import threading
from pathlib import Path


from pipeline_runner import process_job


def start_worker(store, processor=process_job):
    stop = threading.Event()
    def loop(worker_index):
        import time
        cleanup_after = 0
        while not stop.is_set():
            if worker_index == 0 and time.monotonic() >= cleanup_after:
                try:
                    store.archive_uncollected()
                except Exception:
                    # A housekeeping failure must not terminate recipe processing.
                    pass
                cleanup_after = time.monotonic() + 86400
            job = store.claim()
            if not job:
                stop.wait(1)
                continue
            try:
                processor(store, job)
            except ValueError as error:
                store.update_job(job[0], 'failed', '处理未完成', error=str(error)[:250])
            except Exception as error:
                import re
                folder = store.folder / 'jobs' / job[0]
                folder.mkdir(parents=True, exist_ok=True)
                stage_file = folder / 'last-stage.txt'
                stage_name = stage_file.read_text(encoding='utf-8') if stage_file.exists() else '启动任务'
                message = re.sub(r'https?://\S+', '[链接已隐藏]', str(error))
                message = re.sub(r'(?i)(cookie|token|authorization|sessionid)\s*[:=]\s*\S+', r'\1=[已隐藏]', message)
                (folder / 'task-diagnostic.json').write_text(json.dumps({'stage':stage_name,'error_type':type(error).__name__,'message':message[:2000]},ensure_ascii=False,indent=2),encoding='utf-8')
                store.update_job(job[0], 'failed', stage_name + '失败', error=type(error).__name__ + '：' + message[:180])
    workers=[threading.Thread(target=loop,args=(i,),name=f'recipe-worker-{i+1}',daemon=True) for i in range(2)]
    for thread in workers:thread.start()
    return stop, workers[0]
