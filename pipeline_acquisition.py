"""Resume a verified local source snapshot; never persist login cookies in checkpoints."""
import json
from pathlib import Path
from pipeline_state import digest,file_digest,write_json,rules_digest

def acquire_input(store,kind,value,folder,stage):
    folder=Path(folder)
    source_rules=rules_digest(['pipeline_acquisition.py','note_link.py','browser_media_download.py','video_recipe.py'])
    input_key=digest({'kind':kind,'value':value,'source_rules':source_rules,'file':file_digest(value) if kind in ('video','post') else None})
    manifest=folder/'source-snapshot.json'
    if manifest.exists():
        try:
            saved=json.loads(manifest.read_text(encoding='utf-8'))
            valid=saved['input_key']==input_key
            if saved['type']=='video':
                p=Path(saved['video']).resolve()
                valid=valid and (kind=='video' or p.is_relative_to(folder.resolve())) and p.is_file() and file_digest(p)==saved['source_digest'] and saved.get('post_text_digest',digest(''))==digest(saved.get('post_text',''))
            else:valid=valid and digest(saved['post'])==saved['source_digest']
            if valid:
                saved['resumed_snapshot']=True
                stage('继续使用本任务已取得的内容快照')
                return saved
        except (OSError,KeyError,ValueError,TypeError):pass
    acquired=None
    if kind=='link':
        from note_link import acquire_note,acquire_douyin
        stage('打开帖子并取得内容')
        acquired=acquire_note(value,store.folder/'browser-profile') if ('xiaohongshu' in value or 'xhslink.' in value) else acquire_douyin(value,store.folder/'browser-profile')
        write_json(folder/'acquisition-diagnostic.json',{'kind':acquired['kind'],'media':acquired.get('media_diagnostic',{})})
    if kind=='post' or acquired and acquired['kind']=='post':
        post=acquired['post'] if acquired else json.loads(Path(value).read_text(encoding='utf-8-sig'))
        saved={'type':'post','post':post,'source_digest':digest(post)}
    else:
        video=Path(value) if kind=='video' else None
        if kind=='link':
            from browser_video import cookie_jar
            from video_recipe import download_video
            from browser_media_download import download_observed
            cookies=cookie_jar(acquired.get('cookies',[]),acquired.get('platform','xiaohongshu'))
            url=acquired.get('url',value)
            if acquired.get('media_urls'):
                try:
                    stage('读取浏览器中的视频')
                    video=download_observed(acquired['media_urls'],folder/'downloads',cookies,url)
                except ValueError as error:write_json(folder/'browser-media-diagnostic.json',{'message':str(error)})
            if video is None:
                stage('下载视频')
                try:video=download_video(url,folder/'downloads',cookies=cookies,max_bytes=250*1024*1024)
                except Exception as error:
                    import re
                    message=re.sub(r'https?://\S+','[链接已隐藏]',str(error))
                    write_json(folder/'download-diagnostic.json',{'error_type':type(error).__name__,'message':message[:1500]})
                    raise ValueError('视频下载失败：'+message[:180]) from None
        import cv2
        cap=cv2.VideoCapture(str(video))
        try:
            fps,frames=cap.get(cv2.CAP_PROP_FPS),cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if not cap.isOpened() or fps<=0 or frames<=0:raise ValueError('视频不能解码')
            if frames/fps>300 or max(cap.get(cv2.CAP_PROP_FRAME_WIDTH),cap.get(cv2.CAP_PROP_FRAME_HEIGHT))>4096:raise ValueError('视频超过5分钟或尺寸超过4096')
        finally:cap.release()
        saved={'type':'video','video':str(Path(video).resolve()),'source_digest':file_digest(video)}
    if saved['type']=='video':
        saved['post_text']=(acquired or {}).get('post_text','')
        saved['post_text_digest']=digest(saved['post_text'])
    saved.update(input_key=input_key,resumed_snapshot=False)
    write_json(manifest,saved)
    return saved


def description_records(text):
    """Post body is separate text evidence, not video timestamps or speech."""
    if not isinstance(text,str):raise ValueError('帖子正文格式无效')
    if len(text)>30000:raise ValueError('帖子正文超过30000字，请拆分提交')
    return [{'text':line.strip(),'start':float(i),'end':float(i+1),
             'source':'manual_fixture','kind':'post_text','source_label':'视频帖正文（序号非视频时间）'}
            for i,line in enumerate(text.splitlines()) if line.strip()]
