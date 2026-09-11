"""Build the study plate and cover from the report's published measurements."""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'site/assets/blog/lenia-morphospace-report'
OUT = SOURCE
data = json.loads((SOURCE / 'fish-explainer.json').read_text())

def text(x, y, value, size=16, color='#20212b', extra=''):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" {extra}>{html.escape(str(value))}</text>'

def start(width, height, title):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img"><title>{html.escape(title)}</title><g font-family="Georgia,serif">']

svg = start(1200, 1130, 'Twelve shape differences and four measured fish landmark constellations')
svg += ['<rect width="1200" height="1130" fill="#f8f4ea"/>', text(40,55,'Where the resemblance holds.',36), text(40,88,'flow-map-elite-53 and its nearest fish and tissue neighbors',18)]
svg += [text(930,125,'● Fish',15,'#344aa0'),text(1030,125,'◆ Tissue',15,'#ae4a28')]
x0, scale = 345, 77
for tick in range(9):
    x=x0+tick*scale
    svg += [f'<path d="M{x} 150V685" stroke="#20212b" opacity=".10"/>',text(x,145,tick,13,extra='text-anchor="middle"')]
for i,row in enumerate(sorted(data['distances'],key=lambda r:-r['embryomaker'])):
    y=181+i*43
    f,t=row['fish'],row['embryomaker'];xf,xt=x0+f*scale,x0+t*scale
    tie=f==t
    svg += [text(40,y+5,row['label'],17),f'<path d="M{xf} {y}H{xt}" stroke="#77796e" stroke-width="2"/>', f'<path d="M{xt} {y-6}l6 6 -6 6 -6 -6Z" fill="#ae4a28"/>',f'<circle cx="{xf}" cy="{y}" r="{3 if tie else 5}" fill="#344aa0"/>',text(1000,y+5,f'{f:.2f}',15,'#344aa0'),text(1080,y+5,f'{t:.2f}'+(' =' if tie else ''),15,'#ae4a28')]
svg += [text(345,722,'Normalized coordinate difference · common 0–8 scale',15),text(40,763,'= Exact agreement between the two differences, not a missing mark.',16),text(40,826,'Four fish, eleven landmarks each.',29),text(40,853,'Same x–y projection and coordinate scale; points are measured locations, not body outlines.',16)]
for i,fish in enumerate(data['fish'][:4]):
    cx=165+i*285
    svg += [text(cx,900,fish.get('commonName',fish['name']),16,extra='text-anchor="middle"'),text(cx,922,fish['name'],13,extra='text-anchor="middle" font-style="italic"')]
    for n,p in enumerate(fish['points']):
        x,y=cx+p[0]*220,990-p[1]*220
        svg += [f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.8" fill="#344aa0"/>']
svg += [text(40,1100,'Source: report figure data and the cited fish landmark study. Positions retain their published normalization.',14),'</g></svg>']
(OUT/'comparison-plate.svg').write_text(''.join(svg))

packet=json.loads((SOURCE/'visual-data.json').read_text())
svg=start(1000,1000,'Flow Lenia shape map, cropped to the populated region; selected observations in apricot')
svg += ['<defs><clipPath id="field"><rect x="0" y="0" width="1000" height="900"/></clipPath></defs><g clip-path="url(#field)">']
# A uniform scale preserves the PCA geometry; the cover deliberately shows a crop.
for selected in [False,True]:
    for p in packet['points']:
        if p['source']!='lenia_swarm' or bool(p['selected'])!=selected: continue
        x=(p['x']+4)*47.5;y=450-p['y']*47.5
        if not 0<=x<=1000 or not 0<=y<=900:continue
        color='#f1bc91' if selected else '#f8f4ea'
        svg.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{3 if selected else 1.4}" fill="{color}" opacity="{.95 if selected else .24}"/>')
svg += ['</g>',text(25,940,'FLOW LENIA / SHAPE SPACE',21,'#f8f4ea'),text(25,975,'PCA projection · cropped view · selected group in apricot',16,'#f8f4ea'),'</g></svg>']
(OUT/'measured-cover.svg').write_text(''.join(svg))
