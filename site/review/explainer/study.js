const base='/assets/blog/lenia-morphospace-report/motion/';
const body=document.querySelector('#body'),motion=document.querySelector('#motion');
const estimate=document.querySelector('#estimate'),reveal=document.querySelector('#reveal');
let selected='870da94a',playing=false,measurements=new Map();
const reduced=matchMedia('(prefers-reduced-motion: reduce)');
function play(next){playing=next;body.src=base+selected+(next?'-transparent.webp':'.png');motion.textContent=next?'Pause motion':'Play motion';motion.setAttribute('aria-pressed',String(next));}
motion.addEventListener('click',()=>play(!playing));
reduced.addEventListener('change',()=>{if(reduced.matches)play(false)});
body.addEventListener('error',()=>{if(playing){play(false);motion.textContent='Retry motion'}});
function reset(){document.querySelector('#result').hidden=true;reveal.hidden=false;estimate.disabled=false;}
document.querySelectorAll('[data-id]').forEach(button=>button.addEventListener('click',()=>{selected=button.dataset.id;document.querySelectorAll('[data-id]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));body.alt='Unobstructed replay of Flow Lenia body '+selected.toUpperCase();document.querySelector('#specimen-name').textContent=selected.toUpperCase();play(playing);reset();}));
estimate.addEventListener('input',()=>{document.querySelector('#estimate-value').value=estimate.value+'%';reset()});
reveal.disabled=true;
fetch('/dossiers/lenia-swarm/morphospace/').then(r=>{if(!r.ok)throw Error('Report unavailable');return r.text()}).then(html=>{
 const doc=new DOMParser().parseFromString(html,'text/html');
 doc.querySelectorAll('.report-response-row').forEach(row=>{const id=row.querySelector('.report-specimen-label span').textContent.trim().toLowerCase();measurements.set(id,{progress:parseFloat(row.querySelector('strong').textContent),turn:row.lastElementChild.textContent.trim()})});
 if(!['870da94a','781d0200'].every(id=>measurements.has(id)))throw Error('Expected measurements not found');
 reveal.disabled=false;document.querySelector('#load-status').textContent='Measurements read directly from the current Morphospace report.';
}).catch(error=>{document.querySelector('#load-status').textContent='Could not load measurements. '+error.message;});
reveal.addEventListener('click',()=>{const measured=measurements.get(selected),guess=Number(estimate.value);document.querySelector('#guess').textContent=guess+'%';document.querySelector('#actual').textContent=measured.progress+'%';document.querySelector('#turn').textContent=measured.turn.replace(' turn','');document.querySelector('#guess-mark').style.left=guess+'%';document.querySelector('#actual-mark').style.left=measured.progress+'%';const diff=Math.abs(guess-measured.progress);document.querySelector('#difference').textContent=diff===0?'Your estimate matches the reported median.':`Your estimate is ${diff} percentage points ${guess>measured.progress?'above':'below'} the reported median.`;document.querySelector('#result').hidden=false;reveal.hidden=true;});
