#!/usr/bin/env python3
"""Reaggregate saved transplant and history results without changing experiment artifacts.
Run: uv run --with matplotlib python SCRIPT --campaign ROOT --output JSON --figures DIR
Confidence intervals and transplant invariants are source-reported, not re-estimated.
"""
import argparse,gzip,hashlib,json
from pathlib import Path
from statistics import mean
from collections import defaultdict
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=argparse.ArgumentParser();p.add_argument('--campaign',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--figures',type=Path,required=True);a=p.parse_args();sources=[]
def read(name):
 raw=(a.campaign/name).read_bytes();sources.append({'file':name,'sha256':hashlib.sha256(raw).hexdigest()});return json.loads(raw)
def grouped(vals):
 g=defaultdict(list)
 for k,v in vals:g[k].append(v)
 return mean(map(mean,g.values()))
t=read('developmental-susceptibility-transplant-v1/results.json');r=read('causal-return-loop-v1/results.json');o=read('causal-history-order-v1/results.json');b=read('information-body-return-v1/results.json')
p=a.campaign/'developmental-susceptibility-transplant-v1/analyzed-organisms.jsonl.gz';sources.append({'file':str(p.relative_to(a.campaign)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
with gzip.open(p,'rt') as f:rows=[json.loads(x) for x in f]
effects={};errors=[]
for state in t['states']:
 for window,steps in t['windows'].items():
  vals=[]
  for row in rows:
   tr=row['states'][state]['trajectory'];v=mean(sum(weight*tr[h][str(step)]['radius'] for h,weight in t['contrastDefinitions']['nativeSpecificity']) for step in steps);vals.append((row['groupId'],v))
  measured=grouped(vals);saved=t['stateWindowEffects'][state][window]['radius']['nativeSpecificity'];errors.append(abs(measured-saved['mean']));effects[state+':'+window]={'mean':measured,'lower':saved['lower'],'upper':saved['upper']}
assert max(errors)<1e-12
history={}
for domain,key in [('score','q44AbsoluteScoreGap'),('state','q44StateDistance')]:
 val=mean(x['combined'][domain][key] for x in r['rows']);saved=r[domain+'Memory'][key];assert abs(val-saved['mean'])<1e-12;history[key]=saved
for key in ['matchedChallengeHistoryDistance','loopMinusHoldRepertoireWidth','challengeEffectRankCorrelation']:
 val=mean(x['combined']['future']['immediate'][key] for x in r['rows']);saved=r['futureMemory']['immediate'][key];assert abs(val-saved['mean'])<1e-12;history[key]=saved
matched=mean(x['pairings'][side]['returnMatch']['normalizedGap'] for x in r['rows'] for side in ['endingHigh','endingLow']);assert abs(matched-r['returnMatch']['normalizedScoreGap']['mean'])<1e-12
v=mean(x['contrasts']['alternatingMinusBlockedFutureCombined'] for x in o['ancestors']);assert abs(v-o['primary']['alternatingMinusBlockedFutureRepertoireCombined']['mean'])<1e-12
result={'scope':'Transplant: 28 radius contrasts reaggregated from 64 organism trajectories. Return loop: five contrasts and matching gap reaggregated from 64 saved ancestor rows. Pulse order: primary reaggregated from 30 ancestor rows. Body-return endpoints source-checked only. No raw-state or image reconstruction; intervals retained from original analyses.','sources':sources,'transplantEffects':effects,'maximumTransplantMeanError':max(errors),'transplantAuditReported':t['transplantAudit'],'factorialReported':{w:t['hiddenVisibleFactorial'][w]['radius']['nativeSpecificity'] for w in ['immediate','early']},'returnLoop':history,'normalizedScoreGap':matched,'orderPrimary':o['primary'],'bodyReturnReported':b['headline']}
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n');a.figures.mkdir(parents=True,exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})
for mobile in [False,True]:
 fig,ax=plt.subplots(figsize=(4.6 if mobile else 7.2,4.6),layout='constrained',facecolor='#faf6ed');ax.set_facecolor('#faf6ed')
 keys=['q032-self','q032-fromq048','q048-self','q048-fromq032'];labels=['Age 32 body\nAge 32 composition','Age 32 body\nAge 48 composition','Age 48 body\nAge 48 composition','Age 48 body\nAge 32 composition']
 for y,k in enumerate(keys):
  x=effects[k+':immediate'];ax.errorbar(x['mean'],y,xerr=[[x['mean']-x['lower']],[x['upper']-x['mean']]],fmt='o',color='#31596e' if y<2 else '#995323',capsize=4)
 ax.axvline(0,color='#777',lw=.8);ax.set_yticks(range(4),labels);ax.invert_yaxis();ax.set_xlabel('Radius response specific to the native direction\n(order contrast minus orthogonal control)');ax.set_title('The recipient retains its age-dependent response',loc='left',fontsize=10 if mobile else 13,pad=16);ax.grid(axis='x',alpha=.15)
 fig.savefig(a.figures/('recipient-response'+('-mobile' if mobile else '')+'.svg'),metadata={'Date':None});plt.close(fig)
print(json.dumps({'transplantRows':len(rows),'contrasts':len(effects),'maximumError':max(errors),'scoreMatch':matched,'orderPrimary':v}))
