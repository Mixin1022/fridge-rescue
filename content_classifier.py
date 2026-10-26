"""Conservative local rules: uncertain text is retained, never silently deleted."""
import re

FOOD = re.compile(r'番茄|黄瓜|青椒|红椒|面包|大蒜|洋葱|葱姜|皮蛋|肉末|猪肉|牛肉|鸡肉|章鱼|橄榄油|辣椒|花椒|酱油|蚝油|豆瓣酱|白醋|雪梨醋|盐|白糖')
OPERATION = re.compile(r'切成|切片|切丝|切块|剁|刨|撒上|放入|加入|倒入|下锅|锅里|煎|炒|炖|炸|搅拌|搅打|打湿|稀释|铺上|捞出|装盘|收汁|调味|准备|先取|淋|过.*筛|过滤|加(?:一点|少许)|做.*(?:酱|油|浇头)|煮.*(?:面|分钟)|(?:小火|中火|大火).*煮')
STATE = re.compile(r'油温|成热|金黄|杀出.*水|出水|浓稠|稀稠|熟透|炒熟|像视频.*状态|干拌面和汤面')
SOCIAL = re.compile(r'(?:在|来).*西班牙.*(?:住|煮|生活).*以后|习惯.*节奏|点赞|关注|订阅|下期|第一次喝|我觉得.*(?:就是|好吃)|他们家.*调味|如果.*只能留下|我想肯定就是|日思夜想|大功告成')
PACKAGING = re.compile(r'营养(?:素参考|成分表)|营州成分表|每\s*100.*(?:营养|营州|营养表|参考|参语)|(?:儿童|儿量|青少年).*避免.*(?:摄入|据入|盐油|油糖)|(?:净)?含量\s*[:：]|净含量|此日期前最佳|见背面喷码|原汁添加量|添加量\s*[>＞]|香辛')


def classify_content(item, neighbors):
    text = item['text'].strip()
    if PACKAGING.search(text):
        return 'narration', '包装标签或健康警示，排除出食谱并保留原文'
    if item.get('kind') == 'ingredient_card':
        return 'ingredient', '画面用量卡'
    operation = OPERATION.search(text)
    # Mixed sentences with concrete operations must survive praise/introduction.
    if SOCIAL.search(text) and not operation:
        return 'narration', '开场、评价或生活叙述，没有明确操作'
    if operation:
        return 'operation', '包含具体烹饪动作'
    if STATE.search(text) and not re.match(r'^熟透的', text):
        return 'state', '温度、熟度或烹饪状态'
    # Recover caption fragments using a nearby complete spoken sentence.
    for other in neighbors:
        if other is item or other['source'] == item['source']:
            continue
        if max(item['start'], other['start']) - min(item['end'], other['end']) > 1:
            continue
        if len(text) >= 2 and text in other['text'] and OPERATION.search(other['text']):
            return 'operation', '属于同时间语音中的烹饪动作'
    if FOOD.search(text) and not re.search(r'我|觉得|这个时候|就是|够了|做法', text):
        return 'ingredient', '食材或调料描述，不要求包含动作'
    return 'uncertain', '规则不能确定用途，保留原文供核对'
