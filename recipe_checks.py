"""Deterministic, source-grounded checks and scoped text corrections."""
from copy import deepcopy
import re
from decimal import Decimal
from content_classifier import PACKAGING
from deepseek_recipe import missing_numbers

UNITS={'kg':('mass',1000),'千克':('mass',1000),'公斤':('mass',1000),'g':('mass',1),'克':('mass',1),
       'ml':('volume',1),'毫升':('volume',1),'l':('volume',1000),'升':('volume',1000),
       '分钟':('time',1),'小时':('time',60),'cm':('length',1),'厘米':('length',1),'mm':('length',Decimal('.1')),'毫米':('length',Decimal('.1')),
       '度':('temperature',1),'℃':('temperature',1),'次':('repeat',1),'片':('slice',1),'个':('count',1),'大勺':('tablespoon',1),'小勺':('teaspoon',1)}
UNIT_PATTERN='|'.join(sorted(map(re.escape,UNITS),key=len,reverse=True))

def measures(text):
    result=set()
    if '半小时' in text:result.add(('time',Decimal(30)))
    digits={'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
    def count_word(match):
        word=match[1]
        if '十' in word:
            left,right=word.split('十',1)
            if (left and left not in digits) or (right and right not in digits):return word
            return str(digits.get(left,1)*10+digits.get(right,0))
        return str(digits[word]) if word in digits else word
    text=re.sub(r'([一二两三四五六七八九十]{1,3})(?=\s*(?:个|片|大勺|小勺|次|分钟|小时))',count_word,text)
    for number,unit in re.findall(r'(\d+(?:\.\d+)?)\s*('+UNIT_PATTERN+r')',text,re.I):
        dimension,scale=UNITS[unit.lower()];result.add((dimension,Decimal(number)*scale))
    for low,high,unit in re.findall(r'(\d+)\s*[-–~至]\s*(\d+)\s*('+UNIT_PATTERN+r')',text,re.I):
        dimension,scale=UNITS[unit.lower()];result.update((dimension,Decimal(n)*scale) for n in (low,high))
    return result

def local_checks(model,records):
    issues=[]
    for key in ('ingredients','steps'):
        for index,item in enumerate(model.get(key,[])):
            refs=item.get('evidence_ids',[])
            if not refs or any(type(i) is not int or not 0<=i<len(records) for i in refs):
                issues.append({'text':'条目缺少有效原文依据','severity':'blocking','evidence_ids':[], 'target':{'field':key,'index':index}})
                continue
            source=' '.join(records[i]['text'] for i in refs)
            text=item.get('text',item.get('instruction',''))+' '+item.get('quantity','')
            # Check explicit measurement dimensions, not just whether a number occurs nearby.
            unsupported=measures(text)-measures(source)
            if missing_numbers(text,source) or unsupported or all(PACKAGING.search(records[i]['text']) for i in refs):
                issues.append({'text':'数值或制作内容与引用原文不符','severity':'blocking','evidence_ids':refs,'target':{'field':key,'index':index}})
    return issues

def prepare_local(model,records):
    """Fix only explicit, mechanically provable omissions; never infer quantities."""
    model=deepcopy(model);changes=[]
    # Aids explicitly named in a step must be listed, without guessing their kind/amount.
    for step in model.get('steps',[]):
        if '干粉' not in step.get('text',''):continue
        refs=[i for i in step.get('evidence_ids',[]) if type(i) is int and 0<=i<len(records) and '干粉' in records[i]['text']]
        if refs and not any('干粉' in (x.get('name','')+x.get('text','')) for x in model.get('ingredients',[])):
            model.setdefault('ingredients',[]).append({'name':'干粉（防粘）','quantity':'','text':'干粉（防粘）','evidence_ids':refs})
            changes.append('根据步骤和原文补回干粉；未添加用量或推断种类')
    for word in ('白糖','盐','牛奶','黄油'):
        materials=[x for x in model.get('ingredients',[]) if x.get('name')==word]
        if len(materials)<2:continue
        for item in materials:
            matches=[s['text'] for s in model.get('steps',[]) if word in s.get('text','') and item.get('quantity') and item['quantity'] in s['text']]
            scopes={scope for text in matches for scope in ('面团','馅料') if scope in text}
            if len(scopes)==1:
                scope=next(iter(scopes));item['name']=word+'（'+scope+'）';item['text']=item['name']+item.get('quantity','')
                changes.append('按现有步骤明确'+word+'用途：'+scope)
    return model,changes

def normalize_findings(result,model):
    """An exact named ingredient already present disproves only a structured omission."""
    result=deepcopy(result)
    names={x.get('name','').split('（')[0].strip() for x in model.get('ingredients',[])}
    for issue in result.get('issues',[]):
        if issue.get('check_type')=='missing_ingredient' and issue.get('subject') in names:
            issue.update(severity='advisory',local_check='候选材料表已有该名称，遗漏结论不成立')
    result['passed']=not any(i.get('severity','blocking')=='blocking' for i in result.get('issues',[]))
    return result

def apply_patch(model,patch,records):
    """Apply exact-index replacements/additions; every other item stays byte-equivalent."""
    if not isinstance(patch,dict) or not isinstance(patch.get('changes'),list) or len(patch['changes'])>40:
        raise ValueError('局部修正格式无效')
    result=deepcopy(model);seen=set()
    for change in patch['changes']:
        field=change.get('field');index=change.get('index');op=change.get('op')
        if field not in ('ingredients','steps') or type(index) is not int or op not in ('replace','append','insert'):
            raise ValueError('局部修正目标无效')
        if (field,index) in seen:raise ValueError('局部修正重复目标')
        seen.add((field,index))
        items=result.get(field,[]);item=change.get('item')
        if not isinstance(item,dict) or not isinstance(item.get('text'),str) or not item['text'].strip():raise ValueError('局部修正条目无效')
        if field=='ingredients' and (not isinstance(item.get('name'),str) or not item['name'].strip() or not isinstance(item.get('quantity'),str)):
            raise ValueError('局部修正材料缺少名称或用量字段')
        if op=='replace':
            if not 0<=index<len(items):raise ValueError('局部修正位置越界')
            if change.get('expected_text')!=items[index].get('text'):raise ValueError('局部修正基线已改变')
            items[index]=item
        elif op=='insert':
            if not 0<=index<=len(items):raise ValueError('插入位置越界')
            items.insert(index,item)
        else:
            if index!=len(items):raise ValueError('新增条目必须追加，禁止隐式改序')
            items.append(item)
    if local_checks(result,records):raise ValueError('局部修正未通过原文依据检查')
    return result
