"""Download an observed platform media URL with bounded reads and redirects."""
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler
import uuid

def validate_media_url(url):
    parsed=urlparse(url)
    host=parsed.hostname or ''
    suffixes=('xhscdn.com','xhscdn.net','xiaohongshu.com')
    if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None,443) or not any(host==s or host.endswith('.'+s) for s in suffixes):
        raise ValueError('视频地址不属于允许的平台域名')

class MediaRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        validate_media_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def download_observed(urls, folder, cookies, referer, limit=250*1024*1024):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    for url in urls[:8]:
        target=folder/('browser-'+uuid.uuid4().hex+'.mp4')
        try:
            validate_media_url(url)
            opener=build_opener(MediaRedirect(),HTTPCookieProcessor(cookies))
            request=Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':referer})
            with opener.open(request,timeout=30) as response:
                validate_media_url(response.url)
                total=0
                with target.open('wb') as stream:
                    while True:
                        chunk=response.read(min(1024*1024,limit-total+1))
                        if not chunk:break
                        total+=len(chunk)
                        if total>limit:raise ValueError('视频超过250MB')
                        stream.write(chunk)
            with target.open('rb') as stream:
                if stream.read(12)[4:8]!=b'ftyp':raise ValueError('不是可读取的MP4视频')
            return target
        except Exception:
            target.unlink(missing_ok=True)
    raise ValueError('浏览器视频地址不可下载或不是MP4；可能为分段流、地址过期或平台限制')
