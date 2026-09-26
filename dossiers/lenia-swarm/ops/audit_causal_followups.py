#!/usr/bin/env python3
"""Verify later dose-control aggregates; render the reading guide's evidence figure.

uv run --with matplotlib python SCRIPT --campaign ROOT --output JSON --figure SVG
The controller result is copied with a source hash, not independently re-fitted.
"""
import argparse, hashlib, json
from pathlib import Path
from statistics import mean
from collections import defaultdict
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=argparse.ArgumentParser();p.add_argument('--campaign',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--figure',type=Path,required=True);a=p.parse_args()
sources=[]
def read(name):
 raw=(a.campaign/name).read_bytes();sources.append({'file':name,'sha256':hashlib.sha256(raw).hexdigest()});return json.loads(raw)
d=read('developmental-causal-impedance-v1/results.json');c=read('developmental-whole-control-tournament-v1/corrected-results.json')
rows=d['analyzedRecords'];errors=[]
for r in d['denseChronologicalProfile']:
 groups=defaultdict(list)
 for x in rows:
  if x['arm']==r['arm'] and x['age']==r['age']:groups[x['groupId']].append(x['distances'][str(r['horizon'])])
 errors.append(abs(mean(map(mean,groups.values()))-r['distance']['mean']))
assert max(errors)<1e-12
contrasts={}
for arm in ['fixed_0.12','matched_effective']:
 for h in [120,240]:
  groups=defaultdict(lambda:defaultdict(list))
  for r in rows:
   if r['arm']==arm and r['age'] in [60,100,140,180,660,700,740,780]:groups[r['groupId']]['early' if r['age']<200 else 'late'].append(r['distances'][str(h)])
  values=[mean(x['late'])-mean(x['early']) for x in groups.values()]
  saved=d['matchedRecovery'][str(h)][arm];assert abs(mean(values)-saved['mean'])<1e-12
  contrasts[f'{arm}:{h}']={'mean':mean(values),'negativeGroups':sum(x<0 for x in values),'reported95':saved['bootstrap95']}
matched=[r for r in rows if r['arm']=='matched_effective']
within=sum(abs(r['probeA4']-r['targetA4'])<=.25*r['targetA4'] for r in matched)
result={'sources':sources,'scope':'All 266 age-by-horizon-by-arm means and four downstream contrasts reconstructed from 7,296 saved rows. No raw-frame replay for this follow-up. Controller statistics source-checked only.','rows':len(rows),'maxProfileError':max(errors),'contrasts':contrasts,'matchedWithin25Percent':within,'matchedTotal':len(matched),'turnIdentified':d['turnSecondary']['identifiabilityGate']['passed'],'controllerPrimary':c['primary'],'controllerHeldOut':c['heldOut'],'controllerBoundary':c['claimBoundary']}
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
fig,axs=plt.subplots(2,1,figsize=(7.2,7.5),layout='constrained',facecolor='#faf6ed')
for ax,h in zip(axs,[4,120]):
 ax.set_facecolor('#faf6ed')
 for arm,color,label in [('fixed_0.12','#995323','Fixed swap fraction'),('matched_effective','#31596e','Attempted early-response match')]:
  rr=[r for r in d['denseChronologicalProfile'] if r['arm']==arm and r['horizon']==h]
  ages=[r['age'] for r in rr];ys=[r['distance']['mean'] for r in rr]
  ax.plot(ages,ys,color=color,lw=2,label=label)
  ax.fill_between(ages,[r['distance']['bootstrap95'][0] for r in rr],[r['distance']['bootstrap95'][1] for r in rr],color=color,alpha=.12)
 ax.set_title(f'{h} steps after intervention',loc='left',fontweight='bold');ax.set_ylabel('Difference from untouched shape');ax.grid(axis='y',alpha=.15);ax.ticklabel_format(axis='y',style='plain');ax.set_ylim(bottom=0)
axs[0].legend(frameon=False,fontsize=10);axs[1].set_xlabel('Age when the intervention is applied (simulation steps)')
a.figure.parent.mkdir(parents=True,exist_ok=True);fig.savefig(a.figure,metadata={'Date':None});print(json.dumps({'rows':len(rows),'error':max(errors),'matched':within,'total':len(matched),'contrasts':contrasts}))

fig.set_size_inches(4.2,7.5)
axs[0].legend(frameon=False,fontsize=8)
for ax in axs: ax.tick_params(labelsize=9); ax.yaxis.label.set_size(10)
axs[1].set_xlabel("Age at intervention (simulation steps)",fontsize=10)
fig.savefig(a.figure.with_name(a.figure.stem+"-mobile.svg"),metadata={"Date":None})
