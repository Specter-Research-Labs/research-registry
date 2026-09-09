"""Build the Writing cover from the synthesis report's stored heatmap values.
Run from the registry root: python3 dossiers/lenia-swarm/ops/build_publication_covers.py
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
source = ROOT / "site/dossiers/lenia-swarm/causal-emergence/reports/synthesis-v7/index.html"
rows = [(int(a), float(v)) for a, v in re.findall(r"same 0\.12 command, age (\d+), horizon 120: ([\d.]+)", source.read_text())]
assert len(rows) == 19 and len(set(a for a, _ in rows)) == 19
points = " ".join(f"{52+(a-60)/720*480:.2f},{224-v/.010*124:.2f}" for a,v in rows)
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 580 310" role="img" aria-labelledby="title desc"><title id="title">The same push has less effect later</title><desc id="desc">Fixed 0.12 intervention; mean D4 field distance after 120 steps. Nineteen intervention ages, 64 organisms in sixteen groups. Values transcribed from the synthesis heatmap.</desc><rect width="580" height="310" fill="#e6e9df"/><g fill="#172021" font-family="Arial,sans-serif"><text x="32" y="43" font-size="26" font-weight="700">The same push, later in life.</text><text x="32" y="70" font-size="14">Difference from the untouched future · +120 steps</text></g><g stroke="#17202120"><path d="M52 100H532M52 162H532M52 224H532"/></g><path d="M{points.replace(' ', ' L')}" fill="none" stroke="#365b4e" stroke-width="4" stroke-linejoin="round"/><g fill="#365b4e">'''
for a,v in rows:
    svg += f'<circle cx="{52+(a-60)/720*480:.2f}" cy="{224-v/.010*124:.2f}" r="3"><title>Age {a}: {v:.6f}</title></circle>'
svg += '<g font-family="monospace" font-size="12" fill="#536054"><text x="8" y="104">.010</text><text x="8" y="166">.005</text><text x="32" y="228">0</text><text x="48" y="247">60</text><text x="271" y="247">420</text><text x="510" y="247">780</text><text x="215" y="282">Passage at intervention</text></g></g></svg>'
(ROOT / "site/assets/writing-causal-response.svg").write_text(svg)
