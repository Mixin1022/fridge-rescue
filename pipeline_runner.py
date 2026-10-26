"""Content-addressed, restartable recipe processing with visible stage timings."""
import os
import json
from pathlib import Path
import threading

_BROWSER_LOCK=threading.Lock()
_RECOGNITION_LOCK=threading.Lock()
_ART_LOCK=threading.Lock()

def resource_call(lock, stage, label, callback):
    if not lock.acquire(blocking=False):
        stage(label)
        lock.acquire()
    try:return callback()
    finally:lock.release()

from pipeline_state import PipelineState,digest,rules_digest,write_json

def process_job(store,job):
    identifier,kind,value=job
    folder=store.folder/'jobs'/identifier;folder.mkdir(parents=True,exist_ok=True)
    def stage(text):
        store.update_job(identifier,'running',text)
        (folder/'last-stage.txt').write_text(text,encoding='utf-8')
    pipe=PipelineState(folder,store.folder/'stage-cache',stage)
    from pipeline_acquisition import acquire_input
    source=pipe.run('source','取得或恢复本任务内容',digest([kind,value]),'source-snapshot-v1',lambda:resource_call(_BROWSER_LOCK,stage,'等待下载通道（其他任务正在获取内容）',lambda:acquire_input(store,kind,value,folder,stage)),cache=False)
    source_id=source['source_digest']
    is_post=source['type']=='post'
    if is_post:
        from post_recipe import post_records
        records=pipe.run('post_ocr','识别图文文字',source_id,rules_digest(['post_recipe.py']),lambda:resource_call(_RECOGNITION_LOCK,stage,'等待文字识别资源',lambda:post_records(source['post'])))
    else:
        from video_recipe import ocr_video,transcribe
        from importlib.metadata import version,PackageNotFoundError
        try:ocr_version=version('rapidocr')
        except PackageNotFoundError:ocr_version='unknown'
        records=pipe.run('ocr','识别视频字幕',source_id,rules_digest(['video_recipe.py'],{'fps':1,'threshold':.55,'ocr_package':ocr_version,'revision':os.getenv('FRIDGE_OCR_REVISION','default')}),lambda:resource_call(_RECOGNITION_LOCK,stage,'等待字幕识别资源',lambda:ocr_video(Path(source['video']),store.folder/'models'/'ocr',1,.55,True)))
        write_json(folder/'ocr-evidence.json',records)
        speech_model=os.getenv('SPEECH_MODEL','small')
        def speech():
            try:return resource_call(_RECOGNITION_LOCK,stage,'等待语音识别资源',lambda:transcribe(Path(source['video']),speech_model,store.folder/'models'/'speech',True))
            except ValueError as error:
                if '没有音轨' not in str(error):raise
                return []
        spoken=pipe.run('speech','识别视频语音',source_id,rules_digest(['video_recipe.py'],{'speech_model':speech_model}),speech)
        records=list(records)+list(spoken)
    if not is_post:
        from pipeline_acquisition import description_records
        records=list(records)+description_records(source.get('post_text',''))
    write_json(folder/'recognition-evidence.json',records)
    from video_recipe import build_recipe
    from deepseek_recipe import load_config,analyze
    from recipe_note_status import exclude_explicit_sides,annotate_recipe
    model_name=load_config()[1]
    text_rules=rules_digest(['deepseek_recipe.py','content_classifier.py','recipe_scope.py','recipe_note_status.py'],model_name)
    result=build_recipe(records,value if kind=='link' else None)
    def organize():
        try:return analyze(records,folder/'deepseek-candidate.json')
        except Exception as error:
            write_json(folder/'analysis-diagnostic.json',{'error_type':type(error).__name__,'message':str(error)[:500]})
            write_json(folder/'recognition-draft.json',result)
            raise ValueError('DeepSeek 整理失败：'+str(error)[:180]+'。原文保留，可从本阶段重试。') from None
    model=pipe.run('analysis','整理食材和步骤',digest([source_id,records]),text_rules,organize)
    exclude_explicit_sides(model)
    result.update(deepseek=model,analysis_status='deepseek',title=model.get('title',''),source_digest=source_id,source_snapshot_reused=source.get('resumed_snapshot',False),job_id=identifier)
    write_json(folder/'recipe.json',result)
    from recipe_review_cycle import run_review_cycle
    hint_path=folder/'review-hints.json'
    try:
        hints=json.loads(hint_path.read_text(encoding='utf-8'))
        if not isinstance(hints,list) or not all(isinstance(h,str) for h in hints):raise ValueError('invalid hints')
    except (OSError,ValueError):
        hints=store.learning_hints();write_json(hint_path,hints)
    review_rules=rules_digest(['recipe_review_cycle.py','recipe_checks.py','recipe_revision.py','recipe_auto_review.py','deepseek_recipe.py'],{'model':model_name,'hints':hints})
    review_input=digest([source_id,model,records]);review_key=digest([review_input,review_rules])
    resumed_text={'used':False}
    def review_text():
        finalized=folder/'finalized-text.json'
        try:
            saved=json.loads(finalized.read_text(encoding='utf-8'))
            if saved['key']==review_key and saved['value_digest']==digest(saved['value']):
                resumed_text['used']=True
                return saved['value']
        except (OSError,ValueError,KeyError,TypeError):pass
        value=run_review_cycle(model,records,folder,hints,stage)
        # A marked draft is a saved per-job decision, NOT a successful shared AI cache.
        write_json(finalized,{'key':review_key,'value_digest':digest(value),'value':value})
        return value
    reviewed=pipe.run('review','检查依据并局部修正',review_input,review_rules,review_text,
                      cache_when=lambda value:not value[1].get('review_error') and not value[1].get('correction_error'))
    if resumed_text['used']:
        pipe.timings[-1]['resumed_snapshot']=True
        write_json(folder/'timings.json',pipe.timings)
    result['deepseek'],result['auto_review']=reviewed
    exclude_explicit_sides(result['deepseek'])
    annotate_recipe(result)
    result['title']=result['deepseek'].get('title',result['title'])
    write_json(folder/'recipe.json',result)
    result['rule_revision']=digest([text_rules,review_rules])
    write_json(folder/'auto-review.json',result['auto_review'])
    if not result['auto_review']['passed']:
        report_key=digest([result['deepseek'],result['auto_review']]);report_file=folder/'feedback-recorded.json'
        try:reported=json.loads(report_file.read_text(encoding='utf-8')).get('key')==report_key
        except (OSError,ValueError,TypeError):reported=False
        if not reported:
            store.add_system_feedback(result,result['auto_review']['issues'])
            write_json(report_file,{'key':report_key})
    if result['note_status']=='insufficient':
        write_json(folder/'recipe.json',result)
        raise ValueError('内容不足：无法补造缺失的材料或步骤')
    from codex_recipe_art import attach
    from recipe_art_layout import art_content
    from recipe_quality import drawing_allowed
    allowed,reason=drawing_allowed(result)
    if allowed:
        def draw():
            resource_call(_ART_LOCK,stage,'文字已保存，等待绘图通道',lambda:attach(result,folder,stage))
            return {k:result[k] for k in ('recipe_art','art_layout','art_status','art_warning','art_masks') if k in result}
        art_rules=['codex_recipe_art.py','recipe_art_layout.py','art_batches.py']
        if (Path(__file__).parent/'assets/gazpacho-specific-v1.png').exists():art_rules.append('assets/gazpacho-specific-v1.png')
        art=pipe.run('art','生成水彩插图素材',digest([source_id,art_content(result)]),rules_digest(art_rules,os.getenv('FRIDGE_ART_REVISION','default')),draw,
                     cache_when=lambda value:value.get('art_status')=='completed')
        result.update(art)
        if result.get('art_status')!='completed':
            pipe.timings[-1].update(state='incomplete',error=result.get('art_warning','插图未完成'))
            write_json(folder/'timings.json',pipe.timings)
            write_json(folder/'stage-status.json',pipe.timings[-1])
        if result.get('art_masks'):
            result['note_status']='needs_confirmation'
            result.setdefault('note_warnings',[]).append('部分插图自检发现问题，已遮蔽对应格并标问号；文字仍按原文保留。')
    else:result.update(art_status='awaiting_review',art_warning=reason)
    art_issues=[{'text':m['text'],'severity':'advisory','target':{'field':m['field'],'index':m['index']}} for m in result.get('art_masks',[])]
    if result.get('art_status')=='failed':art_issues.append({'text':result.get('art_warning','插画未完成'),'severity':'advisory'})
    if art_issues:
        key=digest(art_issues);record=folder/'art-feedback-recorded.json'
        try:reported=json.loads(record.read_text(encoding='utf-8')).get('key')==key
        except (OSError,ValueError,TypeError):reported=False
        if not reported:
            store.add_system_feedback(result,art_issues,kind='illustration_issue');write_json(record,{'key':key})
    result['pipeline']=pipe.snapshot()
    write_json(folder/'recipe.json',result)
    from render_recipe import render_recipe
    pipe.run('render','排布便签文字和箭头',digest([result['deepseek'],result.get('art_layout'),result.get('recipe_art')]),rules_digest(['recipe_note_template.html','render_recipe.py']),lambda:render_recipe(result,folder/'recipe.html'),cache=False)
    result['pipeline']=pipe.snapshot()
    write_json(folder/'recipe.json',result)
    saved=store.save_recipe({'recipe':result})
    message='便签已生成，可收录或报错'
    if result['note_status']=='needs_confirmation':message='便签已生成，问号处待确认，可收录或报错'
    if result.get('art_status')!='completed':message='文字已保存；插画未完成，可从绘图阶段重试'
    store.update_job(identifier,'completed',message,recipe_id=saved['id'])
