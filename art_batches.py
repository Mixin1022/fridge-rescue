"""Bounded small art jobs; never infer generated file locations from prose."""
import json
import subprocess
from pathlib import Path
from recipe_art_layout import validate_art_masks


def process_failure(log_text):
    normalized=log_text.lower().replace('’', "'")
    if "you've hit your usage limit" in normalized or 'usage_limit_reached' in normalized:
        return 'Codex 绘图额度已达上限；食谱文字和已完成插图已保留。额度恢复后，请点“从断点继续”，无需重新导入或重复识别。'
    return '本批绘图进程失败；已保存的插图保留供继续。'


def run_batches(plan, recipe, folder, command, prompt, env, flags, log, timeout):
    from pipeline_state import file_digest
    folder=Path(folder)
    review=folder/'art-review.json'
    state_path=folder/'art-cell-checkpoint.json'
    state={}
    if state_path.exists():
        saved=json.loads(state_path.read_text(encoding='utf-8-sig'))
        if saved.get('content_digest')==plan['content_digest']:state=saved.get('files',{})
    pending=[]
    for cell in plan['cells']:
        path=folder/cell['file']
        if cell['content'].get('question_notes'):continue
        if path.is_file() and not path.is_symlink() and state.get(cell['file'])==file_digest(path):continue
        pending.append(cell)
    all_masks=[]
    run=subprocess.CompletedProcess(command,0)
    for offset in range(0,len(pending),3):
        batch=pending[offset:offset+3]
        issues=[]
        for attempt in range(3):
            targets=batch if attempt==0 else [c for c in batch if any(m['field']==c['field'] and m['index']==c['index'] for m in issues)]
            request={'cells':targets,'issues':issues}
            (folder/'active-art-batch.json').write_text(json.dumps(request,ensure_ascii=False),encoding='utf-8')
            review.unlink(missing_ok=True)
            instruction=prompt+'\nIMPORTANT: This invocation handles ONLY cells in active-art-batch.json. Preserve all other files. Inspect existing target PNGs first and reuse only if visually correct; otherwise generate/correct them. Report issues ONLY for this batch. After each generation, use the exact local image path returned by the tool, confirm it exists, copy it to the specified cell file and confirm destination exists before proceeding. Never concatenate prose such as "as" into a file path. If copying fails, inspect the actual returned path instead of repeating the malformed path. Write a fresh art-review.json before finishing.'
            log.flush()
            log_offset=log.tell()
            run=subprocess.run(command,input=instruction,text=True,encoding='utf-8',stdout=log,stderr=log,env=env,timeout=timeout,creationflags=flags)
            if run.returncode!=0:
                log.flush()
                with Path(log.name).open('rb') as diagnostic:
                    diagnostic.seek(log_offset)
                    failure_log=diagnostic.read().decode('utf-8',errors='replace')
                raise RuntimeError(process_failure(failure_log))
            if not review.exists():raise RuntimeError('本批绘图缺少自检报告；插图已保留，未冒充完成。')
            report=json.loads(review.read_text(encoding='utf-8-sig'))
            if report.get('rejected'):report={'rejected':False,'issues':[{'field':c['field'],'index':c['index'],'text':'本批插图自检未通过'} for c in batch]}
            issues=validate_art_masks(recipe,report)
            keys={(c['field'],c['index']) for c in batch}
            if any((m['field'],m['index']) not in keys for m in issues):raise ValueError('插图自检超出当前批次')
            for cell in batch:
                path=folder/cell['file']
                bad=any(m['field']==cell['field'] and m['index']==cell['index'] for m in issues)
                if not path.is_file() or path.is_symlink():
                    if not bad:issues.append({'field':cell['field'],'index':cell['index'],'text':'插图文件未保存'})
                elif not bad:state[cell['file']]=file_digest(path)
            state_path.write_text(json.dumps({'content_digest':plan['content_digest'],'files':state}),encoding='utf-8')
            (folder/f'art-review-batch-{offset//3+1}-round-{attempt+1}.json').write_text(json.dumps({'rejected':False,'issues':issues}),encoding='utf-8')
            if not issues:break
        all_masks.extend(issues)
    review.write_text(json.dumps({'rejected':False,'issues':all_masks},ensure_ascii=False),encoding='utf-8')
    return run
