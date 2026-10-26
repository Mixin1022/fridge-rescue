"""Persistent single-owner recipe library and job queue, using SQLite."""
import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.database = self.folder / 'fridge.sqlite3'
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS recipes(id TEXT PRIMARY KEY, entry TEXT NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, kind TEXT NOT NULL, input TEXT NOT NULL,
            state TEXT NOT NULL, stage TEXT NOT NULL, recipe_id TEXT, error TEXT, created REAL NOT NULL);''')
            db.execute("UPDATE jobs SET state='queued', stage='等待重新处理' WHERE state='running'")
            db.execute('CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY, recipe_id TEXT, body TEXT NOT NULL, created REAL NOT NULL)')

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.database, timeout=20)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def save_recipe(self, entry):
        recipe = entry.get('recipe')
        if not isinstance(recipe, dict) or not isinstance(recipe.get('steps'), list):
            raise ValueError('菜谱必须包含 steps 列表')
        model = recipe.get('deepseek') or recipe
        if not isinstance(model, dict):
            raise ValueError('食谱分析格式不正确')
        steps = model.get('steps')
        if not isinstance(steps, list) or not steps or len(steps) > 300:
            raise ValueError('菜谱步骤为空或过多')
        texts = []
        for step in steps:
            if not isinstance(step, dict):
                raise ValueError('步骤格式不正确')
            text = step.get('text') or step.get('instruction')
            if not isinstance(text, str) or not 0 < len(text) <= 4000:
                raise ValueError('步骤文字为空或过长')
            texts.append(text)
        from pipeline_state import digest
        identity={'source':recipe.get('source_digest',recipe.get('source_url','legacy')),'rules':recipe.get('rule_revision','legacy'),
                  'title':model.get('title',recipe.get('title','')),'ingredients':model.get('ingredients',[]),'steps':texts}
        identifier = digest(identity)[:24]
        if 'evidence' in recipe:
            from video_recipe import validate_evidence
            validate_evidence(recipe['evidence'])
        for field in ('ingredients', 'context', 'narration'):
            if field in recipe and (not isinstance(recipe[field], list) or any(not isinstance(item, dict) or not isinstance(item.get('text'), str) for item in recipe[field])):
                raise ValueError('材料或原文格式不正确')
        if 'recipe_art' in recipe:
            import base64
            from io import BytesIO
            from PIL import Image
            art = recipe['recipe_art']
            prefix = 'data:image/png;base64,'
            if not isinstance(art, str) or not art.startswith(prefix) or len(art) > 12 * 1024 * 1024:
                raise ValueError('插画数据无效')
            try:
                raw = base64.b64decode(art[len(prefix):], validate=True)
                with Image.open(BytesIO(raw)) as image:
                    if image.format != 'PNG' or image.width * image.height > 20_000_000:
                        raise ValueError('插画尺寸或格式无效')
                    if (recipe.get('art_layout') or {}).get('mode')=='tiles-v1':
                        from recipe_art_layout import validate_layout
                        layout=validate_layout(recipe,recipe['art_layout'])
                        if layout['canvas']!={'width':image.width,'height':image.height}:raise ValueError('插图画布不匹配')
                    image.verify()
            except Exception:
                raise ValueError('插画文件无法读取') from None
        clean = {key: value for key, value in recipe.items() if key in {
            'title', 'source_url', 'status', 'method', 'steps', 'evidence', 'ingredients', 'dish_name_candidates',
            'context', 'narration', 'content_classification', 'limitations', 'deepseek', 'analysis_status', 'analysis_warning',
            'recipe_art', 'art_layout', 'art_status', 'art_warning', 'art_masks', 'auto_review', 'note_status', 'note_warnings',
            'source_digest','source_snapshot_reused','rule_revision','job_id','pipeline'}}
        if 'art_masks' in recipe:
            from recipe_art_layout import validate_art_masks
            validate_art_masks(recipe,{'rejected':False,'issues':recipe['art_masks']})
        saved = {'id': identifier, 'recipe': clean, 'title': '', 'cuisine': '', 'reviewed': False}
        with self.connect() as db:
            old = db.execute('SELECT entry FROM recipes WHERE id=?', (identifier,)).fetchone()
            if old:
                previous = json.loads(old[0])
                saved.update({key: previous.get(key, saved[key]) for key in ('title', 'cuisine', 'reviewed')})
            for key in ('title', 'cuisine', 'reviewed'):
                if key in entry:
                    saved[key] = entry[key]
            self.validate_metadata(saved)
            db.execute('INSERT OR REPLACE INTO recipes VALUES(?,?,?)', (identifier, json.dumps(saved, ensure_ascii=False), time.time()))
        return saved

    @staticmethod
    def validate_metadata(entry):
        if not isinstance(entry.get('title'), str) or len(entry['title']) > 120:
            raise ValueError('菜名最多 120 字')
        if entry.get('cuisine') not in ('', '中餐', '日式', '韩式', '意式', '西班牙菜', '其他'):
            raise ValueError('菜系无效')
        if type(entry.get('reviewed')) is not bool:
            raise ValueError('核对状态必须是布尔值')

    def recipes(self):
        with self.connect() as db:
            entries = [json.loads(r[0]) for r in db.execute('SELECT entry FROM recipes ORDER BY updated DESC')]
            return [e for e in entries if not e.get('archived')]

    def archive_uncollected(self, days=7, now=None):
        """Soft archive with a feedback snapshot. Collected recipes never expire."""
        now = time.time() if now is None else now
        cutoff = now - days * 86400
        count = 0
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for identifier, raw in db.execute('SELECT id,entry FROM recipes WHERE updated<?', (cutoff,)).fetchall():
                entry = json.loads(raw)
                if entry.get('reviewed') or entry.get('archived'):
                    continue
                model = entry['recipe'].get('deepseek') or {}
                body = {'kind':'uncollected_archive','status':'pending',
                        'reason':'超过7天未收录，转入问题库；未收录本身不代表识别错误。',
                        'issues':[{'text':s} for s in model.get('uncertainties',[])],
                        'snapshot':entry}
                db.execute('INSERT INTO feedback VALUES(?,?,?,?)', (uuid.uuid4().hex,identifier,json.dumps(body,ensure_ascii=False),now))
                entry.update(archived=True, archived_at=now)
                db.execute('UPDATE recipes SET entry=? WHERE id=?', (json.dumps(entry,ensure_ascii=False),identifier))
                count += 1
        return count

    def update_recipe(self, identifier, changes):
        with self.connect() as db:
            row = db.execute('SELECT entry FROM recipes WHERE id=?', (identifier,)).fetchone()
            if not row:
                raise KeyError('找不到菜谱')
            entry = json.loads(row[0])
            entry.update({key: value for key, value in changes.items() if key in ('title', 'cuisine', 'reviewed')})
            self.validate_metadata(entry)
            db.execute('UPDATE recipes SET entry=?,updated=? WHERE id=?', (json.dumps(entry, ensure_ascii=False), time.time(), identifier))
        return entry

    def create_job(self, kind, value):
        identifier = uuid.uuid4().hex
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            count = db.execute("SELECT count(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0]
            if count >= 10:
                raise ValueError('队列已满，请等待已有任务完成')
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)', (identifier, kind, value, 'queued', '等待处理', None, None, time.time()))
        return identifier

    def claim(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT id,kind,input FROM jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE jobs SET state='running',stage='开始处理' WHERE id=?", (row[0],))
        return row

    def update_job(self, identifier, state, stage, recipe_id=None, error=None):
        with self.connect() as db:
            db.execute('UPDATE jobs SET state=?,stage=?,recipe_id=?,error=? WHERE id=?', (state, stage, recipe_id, error, identifier))

    def jobs(self):
        with self.connect() as db:
            values = [dict(zip(('id', 'state', 'stage', 'recipe_id', 'error', 'created'), row)) for row in
                    db.execute('SELECT id,state,stage,recipe_id,error,created FROM jobs ORDER BY created DESC LIMIT 30')]
            library_version=db.execute('SELECT count(*),max(updated) FROM recipes').fetchone()
        for job in values:
            job['library_version']=list(library_version)
            folder=self.folder/'jobs'/job['id']
            try:
                job['timings']=json.loads((folder/'timings.json').read_text(encoding='utf-8'))
                current=json.loads((folder/'stage-status.json').read_text(encoding='utf-8'))
                job['stage_seconds']=round(time.time()-current['started'],1) if job['state']=='running' else current.get('seconds',0)
            except (OSError,ValueError,KeyError,TypeError):
                job['timings']=[];job['stage_seconds']=0
            job['retryable']=job['state']=='failed'
            if job['state']=='completed' and job.get('recipe_id'):
                with self.connect() as db:row=db.execute('SELECT entry FROM recipes WHERE id=?',(job['recipe_id'],)).fetchone()
                job['retryable']=bool(row and json.loads(row[0])['recipe'].get('art_status')!='completed')
            # Return compact status, never image/base64 data in the polling endpoint.
            try:
                recipe=json.loads((folder/'recipe.json').read_text(encoding='utf-8-sig'))
            except (OSError,ValueError):recipe={}
            job['title']=recipe.get('title') or '识别任务 '+job['id'][:6]
            job['warnings']=[]
            if job.get('recipe_id'):
                with self.connect() as db:decision=db.execute('SELECT entry FROM recipes WHERE id=?',(job['recipe_id'],)).fetchone()
                metadata=json.loads(decision[0]) if decision else {}
                job['decision']='reported' if metadata.get('rejected') else 'saved' if metadata.get('reviewed') else 'pending'
            else:job['decision']='pending'
            review=recipe.get('auto_review') or {}
            if review and not review.get('passed'):
                job['warnings'].append('文字复核有疑问：'+ '；'.join(i.get('text','') for i in review.get('issues',[]) if isinstance(i,dict)))
            if recipe.get('art_status') and recipe.get('art_status')!='completed':
                warning=recipe.get('art_warning') or '插图尚未完成'
                # Diagnose older jobs too, without rerunning paid/model work.
                try:
                    from art_batches import process_failure
                    with (folder/'art-task'/'codex.log').open('rb') as stream:
                        stream.seek(max(0,(folder/'art-task'/'codex.log').stat().st_size-16000))
                        specific=process_failure(stream.read().decode('utf-8',errors='replace'))
                    if '额度已达上限' in specific:warning=specific
                except OSError:pass
                job['warnings'].append(warning)
            latest={}
            for event in job.get('timings',[]):latest[event['stage']]=dict(event)
            if 'art' in latest and recipe.get('art_status') not in (None,'completed'):
                latest['art']['state']='incomplete'
            if job['state']=='running':
                try:
                    active=json.loads((folder/'stage-status.json').read_text(encoding='utf-8'))
                    if active.get('state')=='running':latest[active['stage']]=active
                except (OSError,ValueError,KeyError):pass
            job['stages']=list(latest.values())
            failures=[t for t in job.get('timings',[]) if t.get('state')=='failed']
            job['failure_history']=[{'stage':t['stage'],'label':t['label'],'error':t.get('error','此阶段曾失败；旧版本未保存具体原因'),'recovered':latest.get(t['stage'],{}).get('state')=='completed'} for t in failures]
            for failure in job['failure_history']:
                if failure['stage']=='analysis' and failure['error']=='此阶段曾失败；旧版本未保存具体原因':
                    try:failure['error']=json.loads((folder/'analysis-diagnostic.json').read_text(encoding='utf-8-sig')).get('message',failure['error'])
                    except (OSError,ValueError):pass
            job['recovered_failures']=sum(1 for t in failures if latest.get(t['stage'],{}).get('state')=='completed')
            job['needs_attention']=bool(job['warnings'] or job.get('error'))
        return values

    def retry_job(self,identifier):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT state FROM jobs WHERE id=?',(identifier,)).fetchone()
            if not row:raise ValueError('找不到任务')
            if row[0] in ('queued','running'):raise ValueError('任务已在处理中，不重复提交')
            if db.execute("SELECT count(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0]>=10:raise ValueError('队列已满')
            db.execute("UPDATE jobs SET state='queued',stage='从已完成阶段继续',recipe_id=NULL,error=NULL,created=? WHERE id=?",(time.time(),identifier))
        return {'id':identifier,'state':'queued','resumed':True}

    def report_recipe(self, identifier, reason):
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 2000:
            raise ValueError('请填写问题说明（最多2000字）')
        with self.connect() as db:
            row = db.execute('SELECT entry FROM recipes WHERE id=?', (identifier,)).fetchone()
            if not row:
                raise ValueError('找不到便签')
            entry=json.loads(row[0])
            body={'kind':'user_report','reason':reason.strip(),'snapshot':entry,'status':'pending'}
            report=uuid.uuid4().hex
            db.execute('INSERT INTO feedback VALUES(?,?,?,?)',(report,identifier,json.dumps(body,ensure_ascii=False),time.time()))
            entry['rejected']=True
            db.execute('UPDATE recipes SET entry=?,updated=? WHERE id=?',(json.dumps(entry,ensure_ascii=False),time.time(),identifier))
        return {'id':report,'status':'recorded'}

    def add_system_feedback(self, recipe, issues, kind='auto_review_failure'):
        body={'kind':kind,'issues':issues,'snapshot':recipe,'status':'pending'}
        with self.connect() as db:
            db.execute('INSERT INTO feedback VALUES(?,?,?,?)',(uuid.uuid4().hex,None,json.dumps(body,ensure_ascii=False),time.time()))

    def feedback(self,include_snapshots=True,limit=100):
        with self.connect() as db:
            values=[dict(id=r[0],recipe_id=r[1],created=r[3],**json.loads(r[2])) for r in db.execute('SELECT * FROM feedback ORDER BY created DESC LIMIT ?',(limit,))]
        if not include_snapshots:
            for value in values:
                snapshot=value.pop('snapshot',{})
                value['title']=snapshot.get('title') or (snapshot.get('recipe',snapshot).get('deepseek') or {}).get('title','')
        return values

    def learning_hints(self):
        # Select fixed checks from feedback, never execute user reports as prompts/code.
        checks = {'遗漏':'加强检查动作与材料遗漏', '漏':'加强检查动作与材料遗漏',
                  '用量':'加强逐项核对用量原文', '顺序':'加强核对实际制作先后顺序',
                  '重复':'加强同一对象、阶段、目的的语义去重', '包装':'加强排除包装和广告文字'}
        hints=set()
        for report in self.feedback(include_snapshots=False,limit=50):
            text=report.get('reason','')+' '.join(i.get('text','') for i in report.get('issues',[]))
            hints.update(hint for word,hint in checks.items() if word in text)
        return sorted(hints)
