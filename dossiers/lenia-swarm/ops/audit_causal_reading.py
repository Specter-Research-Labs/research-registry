#!/usr/bin/env python3
"""Check released developmental claims against saved rows and replay frames.

Run with uv run --with numpy --with pillow --with scipy python, passing
--campaign (analysis root), --runs (raw campaign root), and --output.
No simulation or historical analysis files are modified.
"""
import argparse, hashlib, json, gzip
from collections import Counter
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.stats import spearmanr
p=argparse.ArgumentParser();p.add_argument('--campaign',type=Path,required=True);p.add_argument('--runs',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
sources=[]
def read(name):
 raw=(a.campaign/name).read_bytes();sources.append({'file':name,'sha256':hashlib.sha256(raw).hexdigest()});return json.loads(raw)
s=read('steerability-age-profile-v1/results.json');b=read('basin-width-init-variation-v1/results.json');plan=read('steerability-age-profile-v1/plan.json')
ages=plan['design']['ages'];early=ages[:3];late=ages[-3:]
rows=[]
for sr,br in zip(s['organisms'],b['organisms']):
 assert sr['creatureId']==br['creatureId']
 ds=sr['divergenceByAge'];ws=br['widthByStep'];scores=sr['windowScores'];peaks=[x for i,x in enumerate(ages[1:-1],1) if scores[str(x)]>scores[str(ages[i-1])] and scores[str(x)]>scores[str(ages[i+1])]]
 actual=min(peaks,key=lambda x:(-scores[str(x)],x)) if peaks else None;assert actual==sr['turnAge']
 rows.append({'ordinal':sr['ordinal'],'family':sr['familyId'],'responseEarly':float(np.mean([ds[str(x)] for x in early])),'responseLate':float(np.mean([ds[str(x)] for x in late])),'spreadEarly':br['earlyWidth'],'spreadLate':br['lateWidth'],'turnAge':actual,'earliestPeak':min(peaks) if peaks else None})
for entry,field in [(s,'response'),(b,'spread')]:
 fv=entry['primary']['familyValues'];assert abs(np.mean(list(fv.values()))-entry['primary']['bootstrap']['mean'])<1e-14
# Independently reconstruct each released +120-step shape-distance value from PNGs.
def sqrt_image(path):
 with Image.open(path) as im: v=np.asarray(im.convert('L'),dtype=float).reshape(32,4,32,4).sum((1,3))
 assert v.sum()>0
 return np.sqrt(v/v.sum())
def distance(left,right):
 lf=np.fft.fft2(left,s=(63,63));best=0.
 for base in [right,np.fliplr(right)]:
  for k in range(4):best=max(best,float(np.fft.ifft2(lf*np.conj(np.fft.fft2(np.rot90(base,k),s=(63,63)))).real.max()))
 return 1-min(1.,max(0.,best))
rawroot=a.runs/'steerability-age-profile-v1/full';errors=[];early_profile={str(age):[] for age in ages};digest=hashlib.sha256()
for sr in s['organisms']:
 ident=f"s{sr['ordinal']:02d}"
 for age in ages:
  values=[];short=[]
  for horizon,vals in [(age+120,values),(age+4,short)]:
   bp=rawroot/f'{ident}-baseline/frames/frame_{horizon:06d}.png';left=sqrt_image(bp);digest.update(bp.read_bytes())
   for seed in range(1,5):
    pp=rawroot/f'{ident}-a{age:03d}-c{seed:02d}/frames/frame_{horizon:06d}.png';vals.append(distance(left,sqrt_image(pp)));digest.update(pp.read_bytes())
  errors.append(abs(np.mean(values)-sr['divergenceByAge'][str(age)]));early_profile[str(age)].append(float(np.mean(short)))
 print(f"Checked {ident}",flush=True)
changes=[r['responseEarly']-r['responseLate'] for r in rows];spread=[r['spreadLate']-r['spreadEarly'] for r in rows]
result={'scope':'Independent reconstruction from saved PNGs and rows; no new physics runs. Early/late joint counts and four-step diagnostics are exploratory, not frozen tests.','sources':sources,'rawFrameContentDigest':digest.hexdigest(),'replayedComparisons':len(errors)*4,'maximumPublishedDistanceError':max(errors),'primaryContrasts':{'response':s['primary']['bootstrap'],'siblingSpread':b['primary']['bootstrap']},'jointExploratory':{'organisms':len(rows),'responseDeclines':sum(x>0 for x in changes),'spreadIncreases':sum(x>0 for x in spread),'both':sum(x>0 and y>0 for x,y in zip(changes,spread)),'spearmanAcrossOrganisms':float(spearmanr(changes,spread).statistic)},'turnAudit':{'rule':plan['turnRule']['turnAge'],'turnCounts':dict(Counter(str(r['turnAge']) for r in rows)),'selectedPeakDiffersFromEarliest':sum(r['turnAge']!=r['earliestPeak'] for r in rows),'onlineAvailableAtTurn':False,'reason':'Strict peaks use the next sampled age; the selected peak is the highest across the baseline grid.'},'fourStepDiagnostic':{'meaning':'Already-evolved response four steps after the baseline age, not instantaneous intervention magnitude.','meanByAge':{k:float(np.mean(v)) for k,v in early_profile.items()}},'rows':rows}

# Recompute the recovery prediction comparison from the saved held-out probabilities.
recovery=read('preinjury-recovery-confirmation-v2/association-report.json')
predictions=recovery['outOfFoldPrediction']['rows'];losses={}
for key in ['baselineProbability','integratedProbability']:
 family_losses=[]
 for family in sorted({r['family'] for r in predictions}):
  selected=[r for r in predictions if r['family']==family]
  family_losses.append(float(np.mean([-r['label']*np.log(r[key])-(1-r['label'])*np.log(1-r[key]) for r in selected])))
 losses[key]=float(np.mean(family_losses))
reported=recovery['outOfFoldPrediction']['equalFamilyMetrics']
assert abs(losses['baselineProbability']-reported['baseline']['logLoss'])<1e-12
assert abs(losses['integratedProbability']-reported['integrated']['logLoss'])<1e-12
result['recoveryPrediction']={'rows':len(predictions),'recomputedLogLoss':losses,'difference':losses['integratedProbability']-losses['baselineProbability'],'reported95Interval':recovery['fixedPredictionBootstrap']['percentile95Interval'],'scope':'Saved out-of-fold probabilities checked; models and permutations not rerun.'}
# Check hidden-composition effects from all 64 saved organism trajectories.
phase=read('fresh-phase-operator-v1/results-v3.json')
phase_file=a.campaign/'fresh-phase-operator-v1/analyzed-organisms.jsonl.gz'
sources.append({'file':'fresh-phase-operator-v1/analyzed-organisms.jsonl.gz','sha256':hashlib.sha256(phase_file.read_bytes()).hexdigest()})
with gzip.open(phase_file,'rt') as f: phase_rows=[json.loads(line) for line in f]
nonintact=[x['name'] for x in phase['design']['conditions'] if x['name']!='intact']
phase_effects=[]
for step in [32,128,512]:
 for metric in ['radius','fieldHellingerFromIntact']:
  vals=[]
  for group in sorted({r['groupId'] for r in phase_rows}):
   vals.append(float(np.mean([np.mean([r['trajectory'][str(step)][c][metric] for c in nonintact])-r['trajectory'][str(step)]['intact'][metric] for r in phase_rows if r['groupId']==group])))
  mean=float(np.mean(vals)); expected=phase['checkpointEffects'][str(step)]['anyPhaseRewriteMinusIntact'][metric]['mean'];assert abs(mean-expected)<1e-12
  phase_effects.append({'step':step,'metric':metric,'mean':mean})
result['hiddenComposition']={'rows':len(phase_rows),'recomputedEffects':phase_effects,'decoyContrastAt128':phase['checkpointEffects']['128']['field06FamilyMeanMinusDecoy03FamilyMean']['radius'],'scope':'Organism-level trajectory aggregates checked; starting-state invariants taken from the saved audit, not independently re-executed.'}
result['profiles']={'response120':{str(age):float(np.mean([r['divergenceByAge'][str(age)] for r in s['organisms']])) for age in ages},'siblingSpread':{str(age):float(np.mean([r['widthByStep'][str(age)] for r in b['organisms']])) for age in ages}}

a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('rows','sources','primaryContrasts')},indent=2))
