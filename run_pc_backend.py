"""Start from any checkout path. Initialize with python setup_local.py first."""
import os,json,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parent
settings=root/'work/local-config.json'
config=json.loads(settings.read_text(encoding='utf-8-sig')) if settings.exists() else {}
for key,value in {'HOST':str(config.get('host','127.0.0.1')),'PORT':str(config.get('port',8080)),
 'FRIDGE_DATA_DIR':str(root/'work/cloud-data'),'HF_HOME':str(root/'work/models/huggingface'),
 'FRIDGE_ALLOWED_ORIGINS':','.join(config.get('allowed_origins',[]))}.items():os.environ.setdefault(key,value)
if not os.environ.get('FRIDGE_ACCESS_TOKEN'):
    token=root/'work/access-token.txt'
    if not token.exists():raise SystemExit('Run python setup_local.py first.')
    os.environ['FRIDGE_ACCESS_TOKEN']=token.read_text(encoding='utf-8-sig').strip()
print('Backend starting. Password remains in work/access-token.txt; do not publish it.')
raise SystemExit(subprocess.call([sys.executable,str(root/'cloud_server.py')],cwd=root))
