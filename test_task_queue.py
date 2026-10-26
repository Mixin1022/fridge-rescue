import json
import tempfile
import threading
import unittest
from pathlib import Path
from cloud_store import Store
from cloud_worker import start_worker
from pipeline_state import write_json,PipelineState
from art_batches import process_failure

class TaskQueueTests(unittest.TestCase):
    def test_two_jobs_progress_before_first_finishes(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'work') as folder:
            store=Store(folder)
            ids={store.create_job('post','a'),store.create_job('post','b')}
            barrier=threading.Barrier(2);seen=[];done=threading.Event();guard=threading.Lock()
            def process(store,job):
                with guard:seen.append(job[0])
                barrier.wait(timeout=4)
                store.update_job(job[0],'completed','done')
                with guard:
                    if all(j['state']=='completed' for j in store.jobs()):done.set()
            stop,worker=start_worker(store,process)
            try:
                self.assertTrue(done.wait(6))
                self.assertEqual(set(seen),ids)
                self.assertEqual(len(seen),2)
            finally:
                stop.set();worker.join(2)
                for t in threading.enumerate():
                    if t.name.startswith('recipe-worker-'):t.join(2)

    def test_old_quota_failure_and_text_warnings_are_visible(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'work') as folder:
            store=Store(folder);identifier=store.create_job('post','a')
            path=Path(folder)/'jobs'/identifier
            write_json(path/'recipe.json',{'title':'Noodles','art_status':'failed','art_warning':'generic','auto_review':{'passed':False,'issues':[{'text':'missing evidence'}]}})
            write_json(path/'timings.json',[{'stage':'analysis','label':'text','state':'failed'},{'stage':'analysis','label':'text','state':'completed'},{'stage':'art','label':'art','state':'completed'}])
            write_json(path/'stage-status.json',{'started':0,'seconds':1})
            (path/'art-task').mkdir();(path/'art-task'/'codex.log').write_text("ERROR: You’ve hit your usage limit",encoding='utf-8')
            store.update_job(identifier,'completed','done')
            job=store.jobs()[0]
            self.assertTrue(job['needs_attention']);self.assertEqual(job['recovered_failures'],1)
            self.assertEqual(job['stages'][-1]['state'],'incomplete')
            self.assertIn('额度',job['warnings'][-1])
            self.assertNotIn('recipe_art',job)

    def test_failed_stage_preserves_reason(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'work') as folder:
            pipe=PipelineState(Path(folder)/'job',Path(folder)/'cache')
            def fail():raise ValueError('missing evidence')
            with self.assertRaises(ValueError):pipe.run('analysis','text','a','b',fail)
            self.assertEqual(pipe.timings[-1]['error'],'missing evidence')
            self.assertEqual(pipe.timings[-1]['state'],'failed')

    def test_parallel_cache_writes_remain_valid(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'work') as folder:
            target=Path(folder)/'cache.json'
            threads=[threading.Thread(target=write_json,args=(target,{'value':i})) for i in range(20)]
            for t in threads:t.start()
            for t in threads:t.join()
            self.assertIn(json.loads(target.read_text())['value'],range(20))
            self.assertEqual(len(list(Path(folder).glob('*.tmp'))),0)
