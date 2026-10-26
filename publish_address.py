"""Publish only the tunnel URL, never the backend access token."""
import json
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlsplit
from urllib.error import HTTPError, URLError

def failure_detail(error):
    if isinstance(error,HTTPError):return 'HTTP '+str(error.code)+'; check Cloudflare request filtering or publisher authorization.'
    if isinstance(error,URLError):return 'Network connection failed ('+type(error.reason).__name__+').'
    return type(error).__name__+'; check publisher configuration.'

def publish(root):
    root=Path(root)
    config=root/'work/address-publisher.json'
    if not config.exists():return False
    settings=json.loads(config.read_text(encoding='utf-8-sig'))
    endpoint=settings['endpoint'];parsed=urlsplit(endpoint)
    if parsed.scheme!='https' or parsed.username or parsed.password:raise ValueError('Invalid registry endpoint')
    address=(root/'work/phone-address.txt').read_text(encoding='utf-8-sig').strip()
    req=Request(endpoint,data=json.dumps({'url':address}).encode(),method='PUT',headers={'Content-Type':'application/json','Authorization':'Bearer '+settings['write_token'],'User-Agent':'FridgeRescue-AddressPublisher/1.0','Accept':'application/json'})
    with urlopen(req,timeout=15) as response:
        if json.load(response).get('ok') is not True:raise ValueError('Registry did not confirm update')
    return True

if __name__=='__main__':
    import time
    root=Path(__file__).resolve().parent
    for attempt in range(3):
        try:
            ok=publish(root)
            print('Phone address updated automatically.' if ok else 'Address publisher not configured yet.')
            break
        except Exception as error:
            if attempt==2:raise SystemExit('Address publish failed. '+failure_detail(error)+' Local backend remains running.')
            time.sleep(2)
