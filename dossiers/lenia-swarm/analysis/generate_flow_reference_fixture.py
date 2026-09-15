"""Run the pinned author implementation; no native simulator code is used here."""
import argparse, base64, json, pathlib, subprocess, sys, types
import jax, jax.numpy as jnp, equinox as eqx, numpy as np
PIN = 'dce428c6b0c5079a06e5606fb7b5ac1fe1323bc5'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--reference-checkout', type=pathlib.Path, required=True)
parser.add_argument('--output', type=pathlib.Path, required=True)
args = parser.parse_args()
actual = subprocess.check_output(['git', '-C', str(args.reference_checkout), 'rev-parse', 'HEAD'], text=True).strip()
if actual != PIN:
    parser.error(f'Reference must be checked out at {PIN}; found {actual}')
if subprocess.check_output(['git', '-C', str(args.reference_checkout), 'status', '--porcelain'], text=True).strip():
    parser.error('Reference checkout must be clean')
package=types.ModuleType('flowlenia');package.__path__=[str(args.reference_checkout/'flowlenia')];sys.modules['flowlenia']=package
from flowlenia.flowlenia import Config, FlowLenia, State
from flowlenia.utils import sobel
cfg=Config(X=32,Y=32,C=2,c0=[0,0,1,1],c1=[[0,2],[1,3]],k=4,dd=5,dt=.2,sigma=.65,border='wall')
model=FlowLenia(cfg,jax.random.key(1))
params=dict(R=6.,r=[.42,.55,.68,.81],m=[.12,.16,.2,.24],s=[.035,.04,.045,.05],h=[.3,.4,.5,.6],
 a=[[v]*3 for v in [.25,.35,.45,.55]], b=[[1.,0.,0.]]*4,w=[[.16,.2,.16]]*4)
for name,value in params.items():
 model=eqx.tree_at(lambda m:getattr(m,name),model,jnp.array(value,dtype=jnp.float32))
x,y,c=np.indices((32,32,2))
a=np.zeros((32,32,2),dtype=np.float32)
mask=((x-12)**2/49+(y-17)**2/25<1)|((x-19)**2+(y-12)**2<9)
a[mask]=(.12+.58*((x*17+y*11+c*7)%29)/29)[mask]
state=model.initialize(jax.random.key(2))._replace(A=jnp.array(a))
def encode(a):return base64.b64encode(np.asarray(a,dtype='<f4').tobytes()).decode()
out={'reference_commit':PIN,'config':cfg._asdict(),'params':params,
 'dtype':'little-endian float32','input':encode(a),'steps':{}}
for step in range(1,9):
 state=model(state)
 if step in [1,8]:out['steps'][str(step)]=encode(state.A)
print('ramp gradients',np.asarray(sobel(jnp.arange(9,dtype=jnp.float32)[:,None,None]*jnp.ones((9,12,1))))[4,5,:,0])
args.output.write_text(json.dumps(out,indent=2)+'\n')
print(f'Wrote {args.output}')
