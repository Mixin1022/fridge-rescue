"""Create private runtime files without overwriting existing credentials."""
import json,secrets
from pathlib import Path
root=Path(__file__).resolve().parent
work=root/'work';work.mkdir(exist_ok=True)
for name,value in [('access-token.txt',secrets.token_urlsafe(32)),('local-config.json',json.dumps({'allowed_origins':[],'host':'127.0.0.1','port':8080},indent=2))]:
    target=work/name
    if not target.exists():target.write_text(value,encoding='utf-8')
print('Initialized work/. Access password: work/access-token.txt (keep private).')
print('Configure DeepSeek using config/deepseek-config.example.json. No model was called.')
