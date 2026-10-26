"""Check publishable source paths; runtime/build outputs are explicitly excluded."""
from pathlib import Path
import re,json
ROOT=Path(__file__).resolve().parents[1]
EXCLUDED={'.git','.venv','__pycache__','work','.wrangler','node_modules','cloudflare-pages'}
GENERATED={'index.html','recipe-preview.html','recipe-library.json','wrangler-auto-address.json','.env'}
def source_files():
    return sorted(f for f in ROOT.rglob('*') if f.is_file() and not any(x in EXCLUDED for x in f.relative_to(ROOT).parts) and f.name not in GENERATED and f.suffix not in {'.zip','.pyc','.log','.sqlite3','.db'})
def check():
    files=source_files();problems=[]
    for f in files:
        if f.stat().st_size>=100*1024*1024:problems.append(str(f.relative_to(ROOT))+': GitHub file limit')
        if f.suffix.lower() in {'.png','.jpg','.mp4','.webp'}:continue
        text=f.read_text(encoding='utf-8-sig')
        if re.search(r'sk-[A-Za-z0-9_-]{24,}',text):problems.append(str(f.relative_to(ROOT))+': possible credential')
        if ('fridge'+'1022'+'receipe') in text or ('mixin'+'1022') in text:problems.append(str(f.relative_to(ROOT))+': personal deployment identifier')
    if problems:raise SystemExit('Release check failed: '+str(problems))
    print(f'Source check passed: {len(files)} files; runtime, credentials and generated outputs excluded.')
if __name__=='__main__':check()
