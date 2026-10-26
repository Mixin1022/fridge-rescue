"""AI draws a tile atlas. Code owns crop positions, captions and route order."""
import math
from pipeline_state import digest

VERSION='watercolor-atlas-v1'

def art_content(recipe):
    model=recipe.get('deepseek') or recipe
    return {'title':model.get('title') or recipe.get('title',''),
            **{key:[{k:v for k,v in item.items() if k in ('name','quantity','text','instruction','question_notes')} for item in model.get(key,[])] for key in ('ingredients','steps')}}

def plan_for(recipe):
    content=art_content(recipe)
    count=sum(len(content[k]) for k in ('ingredients','steps'))
    if not count or count>64:raise ValueError('插图条目为空或超过64项，请拆分食谱')
    cols=4 if count>6 else 3
    rows=math.ceil(count/cols)
    cells=[]
    for key in ('ingredients','steps'):
        for i,item in enumerate(content[key]):
            n=len(cells)
            cells.append({'field':key,'index':i,'row':n//cols,'column':n%cols,'content':item})
    return {'version':VERSION,'columns':cols,'rows':rows,'content_digest':digest(content),'cells':cells}

def layout_for_plan(recipe,width=1024,height=1536):
    plan=plan_for(recipe)
    layout={'mode':'tiles-v1','version':VERSION,'content_digest':plan['content_digest'],'canvas':{'width':width,'height':height},'ingredients':[],'steps':[]}
    for cell in plan['cells']:
        layout[cell['field']].append({'x':cell['column']/plan['columns'],'y':cell['row']/plan['rows'],'w':1/plan['columns'],'h':1/plan['rows']})
    return layout

def validate_layout(recipe,layout):
    canvas=layout.get('canvas') or {}
    width,height=canvas.get('width'),canvas.get('height')
    if type(width) is not int or type(height) is not int or width<1 or height<1 or width*height>20_000_000:raise ValueError('插图画布尺寸无效')
    expected=layout_for_plan(recipe,width,height)
    if layout!=expected:raise ValueError('插图布局与本次食谱内容不匹配，禁止复用旧图')
    return layout

def validate_art_masks(recipe,report):
    if not isinstance(report,dict) or not isinstance(report.get('issues'),list) or len(report['issues'])>64 or report.get('rejected'):
        raise ValueError('插图整体无法对应素材分格，不能显示为成品')
    model=recipe.get('deepseek') or recipe;masks=[]
    for issue in report['issues']:
        if not isinstance(issue,dict):raise ValueError('插图问题条目无效')
        field,index=issue.get('field'),issue.get('index')
        if field not in ('ingredients','steps') or type(index) is not int or not 0<=index<len(model.get(field,[])) or not isinstance(issue.get('text'),str) or not 1<=len(issue['text'].strip())<=500:
            raise ValueError('插图问题没有定位到有效素材格')
        masks.append({'field':field,'index':index,'text':issue['text']})
    return masks
