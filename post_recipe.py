"""Ordered post text and image OCR; does not invent visual-only cooking actions."""
import base64
import io
import re

def validate_post(data):
    if not isinstance(data, dict): raise ValueError('图文格式无效')
    text = data.get('text', '')
    images = data.get('images', [])
    if not isinstance(text, str) or len(text) > 30000 or not isinstance(images, list) or len(images) > 12: raise ValueError('图文内容过大')
    cleaned = []
    total = 0
    for item in images:
        if not isinstance(item, str): raise ValueError('图片格式无效')
        raw = base64.b64decode(item, validate=True)
        total += len(raw)
        if len(raw) > 8*1024*1024 or total > 20*1024*1024: raise ValueError('图片总大小上限20MB，单张8MB')
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ('JPEG','PNG','WEBP') or image.width*image.height > 20000000: raise ValueError('请选择JPEG、PNG或WebP图片')
            image.verify()
        cleaned.append(item)
    if not text.strip() and not cleaned: raise ValueError('请粘贴正文或选择图片')
    return {'text':text, 'images':cleaned}

def post_records(data, reader=None):
    records=[]
    for index, line in enumerate(re.split(r'[\n。；]', data['text'])):
        if line.strip(): records.append({'text':line.strip(),'start':float(index),'end':float(index+1),'source':'manual_fixture','kind':'post_text','source_label':'帖子正文'})
    if data['images'] and reader is None:
        from ocr_engine import ChineseOCR
        reader=ChineseOCR()
    from PIL import Image
    import numpy as np
    offset=len(records)+1
    for index, item in enumerate(data['images']):
        with Image.open(io.BytesIO(base64.b64decode(item))) as image:
            lines=reader.readtext(np.array(image.convert('RGB')))
        lines.sort(key=lambda row:(min(p[1] for p in row[0]),min(p[0] for p in row[0])))
        for box,text,confidence in lines:
            records.append({'text':text,'start':float(offset+index),'end':float(offset+index+1),'source':'ocr','kind':'post_image','image_index':index+1,'confidence':confidence,'source_label':'第'+str(index+1)+'张图片'})
    return records
