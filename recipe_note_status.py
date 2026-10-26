"""Expose unresolved facts without pretending a review passed or inventing content."""
from copy import deepcopy
import re

def exclude_explicit_sides(model):
    """Only remove explicitly labeled side drinks, never infer from ingredient names."""
    title=model.get('title') or ''
    if re.search(r'(奶茶|果茶|茶饮|饮品|果汁|咖啡)(?:制作|做法)?$',title):return model
    removed={}
    for key in ('ingredients','steps'):
        kept=[];side=[]
        for item in model.get(key,[]):
            text=item.get('name','')+' '+item.get('text','')
            tagged=bool(re.search(r'[（(]饮品[）)]|【饮品】',text)) if key=='ingredients' else bool(re.match(r'\s*(?:【饮品】|饮品\s*[:：])',item.get('text','')))
            (side if tagged else kept).append(item)
        model[key]=kept
        if side:removed[key]=side
    if removed:model['excluded_side_items']=removed
    return model

def annotate_recipe(recipe):
    model=deepcopy(recipe['deepseek'])
    review=recipe.get('auto_review') or {}
    warnings=[]
    issues=[i for i in review.get('issues',[]) if i.get('severity','blocking')=='blocking']
    issues += [{'text':s,'evidence_ids':[]} for s in model.get('uncertainties',[])]
    for issue in issues:
        text=issue['text'];refs=set(issue.get('evidence_ids',[]));matched=False
        target=issue.get('target') or {}
        field,index=target.get('field'),target.get('index')
        if field in ('ingredients','steps') and type(index) is int and 0<=index<len(model.get(field,[])):
            model[field][index].setdefault('question_notes',[]).append(text)
            matched=True
        for key in ('ingredients','steps'):
            for item in model.get(key,[]):
                if not target and refs and refs.intersection(item.get('evidence_ids',[])):
                    item.setdefault('question_notes',[])
                    if text not in item['question_notes']:item['question_notes'].append(text)
                    matched=True
        if not matched and text not in warnings:warnings.append(text)
    recipe['deepseek']=model
    recipe['note_warnings']=warnings
    recipe['note_status']='insufficient' if not model.get('ingredients') or not model.get('steps') else 'needs_confirmation' if issues or not review.get('passed') else 'ready'
    return recipe
