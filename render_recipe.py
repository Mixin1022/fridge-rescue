"""Render saved recipe JSON as a self-contained offline HTML page."""
import argparse
import json
import re
import html
from pathlib import Path
from illustration_assets import note_template


def render_recipe(recipe, output):
    template = note_template()
    data = dict(recipe)
    payload = json.dumps(data, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    Path(output).write_text(template.replace('__RECIPE_DATA__', payload), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recipe', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    destination = args.output or args.recipe.with_name('recipe.html')
    render_recipe(json.loads(args.recipe.read_text(encoding='utf-8-sig')), destination)
    print(destination.resolve())
