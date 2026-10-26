"""Embed saved artwork locally; page rendering never calls image generation."""
import base64
from pathlib import Path


def note_template(embed_library_icons=False):
    root = Path(__file__).parent
    template = (root / 'recipe_note_template.html').read_text(encoding='utf-8')
    atlas = root / 'assets' / 'fluid-pen-wash-study-v5.png'
    image = 'data:image/png;base64,' + base64.b64encode(atlas.read_bytes()).decode('ascii') if embed_library_icons and atlas.exists() else ''
    header = root / 'assets' / 'recipe-note-fairies-v1.png'
    friends = '<img class="note-friends" alt="奶蓝蝴蝶结食材小精灵与菜谱小本" src="data:image/png;base64,' + base64.b64encode(header.read_bytes()).decode('ascii') + '">' if '__NOTE_FRIENDS__' in template and header.exists() else ''
    template = template.replace('__NOTE_FRIENDS__', friends).replace('__NOTE_STYLE__', (root / 'recipe_note_style.css').read_text(encoding='utf-8'))
    return template.replace('__WATERCOLOR_ATLAS__', image).replace('__VISUAL_STYLE__', (root / 'visual_style.css').read_text(encoding='utf-8'))
