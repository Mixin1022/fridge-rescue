"""One bounded source-grounded correction; never loop until a reviewer passes."""
import json
from pathlib import Path
from recipe_auto_review import review
from recipe_revision import revise
from recipe_checks import local_checks,prepare_local,normalize_findings

def run_review_cycle(model, records, folder, hints=(), stage=lambda text:None):
    folder=Path(folder)
    folder.mkdir(parents=True,exist_ok=True)
    model,local_changes=prepare_local(model,records)
    (folder/'local-checks.json').write_text(json.dumps({'changes':local_changes},ensure_ascii=False,indent=2),encoding='utf-8')
    history=[]
    previous_issues = None
    for attempt in range(3):
        stage('自动复核材料与步骤' if attempt==0 else '复核修正后的材料与步骤')
        try:
            definite=local_checks(model,records)
            result={'passed':False,'issues':definite,'method':'local-source-check'} if definite else review(model,records,hints,diagnostic_path=folder/f'review-raw-{attempt+1}.json')
            result=normalize_findings(result,model)
        except Exception as error:
            result={'passed':False,'issues':[{'text':'自动复核暂未完成，内容待确认','severity':'blocking','evidence_ids':[]}], 'review_error':type(error).__name__}
        history.append(result)
        (folder/'review-history.json').write_text(json.dumps(history,ensure_ascii=False,indent=2),encoding='utf-8')
        fingerprint = sorted(i['text'] for i in result['issues'] if i.get('severity','blocking')=='blocking')
        if result['passed'] or attempt==2 or fingerprint==previous_issues or result.get('review_error'):
            return model,result
        previous_issues = fingerprint
        stage('根据原文修正问题（最多三轮复核）')
        # Remove reviewer evidence indices: the organizer receives its own deduplicated IDs.
        findings=[{'text':issue['text']} for issue in result['issues'] if issue.get('severity','blocking')=='blocking']
        try:
            corrected=revise(model,records,folder/f'revision-{attempt+1}',findings)
        except Exception as error:
            result['correction_error']=type(error).__name__
            return model,result
        if corrected == model:
            return model,result
        model=corrected
        (folder/'revised-text.json').write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf-8')
