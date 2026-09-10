#!/usr/bin/env python3
"""Render the local explainer with Pandoc citations and a template-owned bibliography."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / 'site/review/explainer'

def main():
    rendered = subprocess.run([
        'pandoc', str(STUDY / 'narrative.md'), '--to=html5', '--citeproc',
        '--bibliography', str(STUDY / 'references.bib'), '--wrap=none',
    ], check=True, capture_output=True, text=True)
    if rendered.stderr:
        raise RuntimeError(rendered.stderr)
    prose, bibliography = rendered.stdout.split('<div id="refs"', 1)
    slots = re.split(r'<!-- SLOT:(\w+) -->', prose)
    template = (STUDY / 'template.html').read_text()
    for name, content in zip(slots[1::2], slots[2::2]):
        template = template.replace(f'${name}$', content)
    template = template.replace('$references$', '<div id="refs"' + bibliography)
    if re.search(r'\$\w+\$', template):
        raise ValueError('Unfilled template slot')
    (STUDY / 'index.html').write_text(template)

if __name__ == '__main__':
    main()
