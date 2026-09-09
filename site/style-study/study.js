const palettes={
 proposed:{name:'Teal & vermilion',note:'The proposed direction: deep teal for evidence, vermilion for interventions. Ochre and violet extend the categorical palette.',colors:['#f4f1e8','#172021','#245d63','#b8432e','#926b16','#79568e'],surface:'#e6ece6'},
 earlier:{name:'Earlier report accents',note:'Reconstructed from the earlier report CSS: cobalt, red, violet, and chartreuse. The chartreuse belongs on a surface or marker, not small text.',colors:['#f5f1e7','#111722','#2f56df','#b43b45','#d7ff2f','#7953bf'],surface:'#e1e7fc'},
 current:{name:'Current sage',note:'The current publication direction: muted green, terracotta, and broad sage surfaces. Compare it with tinted panels turned off.',colors:['#f4f1e8','#172021','#365b4e','#a44733','#947031','#797086'],surface:'#e6e9df'},
 blue:{name:'Ultramarine & apricot',note:'A cooler primary accent against warm paper. Dark burnt orange carries text and controls; the pale apricot is reserved for surfaces.',colors:['#f8f4ea','#20212b','#344aa0','#ae4a28','#8a701e','#806096'],surface:'#f5e7d7'},
 plum:{name:'Aubergine & copper',note:'A warmer, more bookish alternative. Aubergine anchors the figures, copper marks change, and olive provides a third category.',colors:['#f6f0e8','#29212b','#654266','#a44d31','#72703b','#49667f'],surface:'#ebe1e8'}
};
const roles=['Paper','Ink','Primary','Intervention','Category 3','Category 4'];
const keys=['paper','ink','primary','secondary','tertiary','fourth'];
const params=new URLSearchParams(location.search);
let chosen=palettes[params.get('palette')]?params.get('palette'):'blue';
const tinted=document.querySelector('#tinted'),accentTitle=document.querySelector('#accent-title');
tinted.checked=params.get('tint')!=='off';accentTitle.checked=params.get('headline')==='accent';
function luminance(hex){const rgb=hex.slice(1).match(/../g).map(v=>parseInt(v,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;}
function contrast(a,b){let x=luminance(a),y=luminance(b);return(Math.max(x,y)+.05)/(Math.min(x,y)+.05);}
function apply(){const p=palettes[chosen];keys.forEach((k,i)=>document.body.style.setProperty('--'+k,p.colors[i]));document.body.style.setProperty('--surface',p.surface);document.body.style.setProperty('--on-primary',contrast(p.colors[2],'#ffffff')>contrast(p.colors[2],'#172021')?'#ffffff':'#172021');document.body.classList.toggle('no-tint',!tinted.checked);document.body.classList.toggle('accent-title',accentTitle.checked);document.querySelector('#palette-name').textContent=p.name;document.querySelector('#palette-note').textContent=p.note;document.querySelector('#palette-position').textContent='Palette '+(Object.keys(palettes).indexOf(chosen)+1)+' / 5';document.querySelectorAll('[data-palette]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.palette===chosen)));document.querySelector('#swatches').innerHTML=p.colors.map((c,i)=>`<div class="swatch"><i style="background:${c}"></i>${roles[i]}<code>${c.toUpperCase()}</code></div>`).join('');document.querySelector('#contrast-notes').textContent='Contrast on paper · '+p.colors.slice(2).map((c,i)=>roles[i+2]+': '+contrast(c,p.colors[0]).toFixed(1)+':1').join(' · ')+' · Small text needs 4.5:1; chart lines need 3:1.';const q=new URLSearchParams({palette:chosen,tint:tinted.checked?'on':'off',headline:accentTitle.checked?'accent':'ink',composition:'instrument'});const activeTreatment=new URLSearchParams(location.search).get('treatment');if(activeTreatment)q.set('treatment',activeTreatment);history.replaceState(null,'','?'+q+location.hash);}
const options=document.querySelector('#palette-options');for(const [id,p] of Object.entries(palettes)){const b=document.createElement('button');b.type='button';b.dataset.palette=id;b.innerHTML=`<span class="palette-chip" aria-hidden="true">${p.colors.slice(2).map(c=>`<i style="background:${c}"></i>`).join('')}</span>${p.name}`;b.addEventListener('click',()=>{chosen=id;apply()});options.append(b);}
tinted.addEventListener('change',apply);accentTitle.addEventListener('change',apply);apply();
document.querySelector('#copy-link').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(location.href);document.querySelector('#copy-status').textContent='Link copied';}catch{document.querySelector('#copy-status').textContent='Copy the address from your browser to share this combination.';}});
document.querySelector('#block-tactic').addEventListener('click',e=>{const b=e.currentTarget,on=b.getAttribute('aria-pressed')!=='true';b.setAttribute('aria-pressed',String(on));document.querySelector('.proof-panel').classList.toggle('blocked',on);b.textContent=on?'Restore the direct tactic':'Remove the direct tactic';document.querySelector('#proof-status').textContent=on?'Swapping the factors still leaves a route to a proof.':'Both routes are available in this schematic.';});
fetch('/assets/writing-causal-response.svg').then(r=>{if(!r.ok)throw Error('Chart unavailable');return r.text()}).then(s=>{const doc=new DOMParser().parseFromString(s,'image/svg+xml');const values=[...doc.querySelectorAll('circle title')].map(t=>t.textContent.match(/Age (\d+): ([\d.]+)/)).filter(Boolean).map(m=>[+m[1],+m[2]]);if(values.length!==19)throw Error('Unexpected chart data');const xy=values.map(([a,v])=>[54+(a-60)/720*420,210-v/.01*160]);document.querySelector('#response-chart').innerHTML=`<svg viewBox="0 0 510 270" role="img" aria-label="Mean field distance after the fixed disturbance decreases with intervention age"><g stroke="var(--ink)" opacity=".15"><path d="M54 50H474M54 130H474M54 210H474"/></g><g fill="var(--ink)" font-family="monospace" font-size="12"><text x="6" y="54">0.010</text><text x="6" y="134">0.005</text><text x="30" y="214">0</text><text x="48" y="234">60</text><text x="248" y="234">420</text><text x="454" y="234">780</text><text x="175" y="261">Age at intervention (steps)</text></g><path d="M${xy.map(p=>p.join(',')).join('L')}" fill="none" stroke="var(--primary)" stroke-width="3" stroke-linejoin="round"/>${xy.map((p,i)=>`<circle cx="${p[0]}" cy="${p[1]}" r="3" fill="var(--primary)"><title>Age ${values[i][0]}: ${values[i][1]}</title></circle>`).join('')}</svg>`;}).catch(e=>{document.querySelector('#response-chart').textContent=e.message;});
document.querySelector('.composition-examples').dataset.composition='instrument';
const transition=document.querySelector('.transition-study');
const replay=document.querySelector('#replay-transition');
const transitionStatus=document.querySelector('#transition-status');
let transitionFrame=0;
function replayTransition(){
 cancelAnimationFrame(transitionFrame);
 const paths=[...transition.querySelectorAll('.transition-paths path')];
 const dots=[...transition.querySelectorAll('.travel-point')];
 if(matchMedia('(prefers-reduced-motion: reduce)').matches){
  transitionStatus.textContent='Motion is reduced in your settings. The two paths separate, cross, and meet again.';
  dots.forEach((dot,i)=>{const p=paths[i].getPointAtLength(paths[i].getTotalLength()*.52);dot.setAttribute('cx',p.x);dot.setAttribute('cy',p.y);dot.style.opacity=1;});return;
 }
 const start=performance.now();replay.textContent='Restart transition';
 function frame(now){
  const progress=Math.min(1,(now-start)/3600);
  transitionStatus.textContent=progress<.2?'One path.':progress<.8?'Two paths separate and cross.':'The paths meet again.';
  paths.slice(0,2).forEach((path,i)=>{const length=path.getTotalLength();path.style.strokeDasharray=length;path.style.strokeDashoffset=length*(1-progress);const p=path.getPointAtLength(length*progress);dots[i].setAttribute('cx',p.x);dots[i].setAttribute('cy',p.y);dots[i].style.opacity=progress<1?1:0;});
  if(progress<1)transitionFrame=requestAnimationFrame(frame);else replay.textContent='Replay transition';
 }
 transitionFrame=requestAnimationFrame(frame);
}
replay.addEventListener('click',replayTransition);
const transitionObserver=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)){replayTransition();transitionObserver.disconnect();}},{threshold:.5});transitionObserver.observe(transition);
const creature=document.querySelector('#study-creature'),motionControl=document.querySelector('#study-motion');
const motionPreference=matchMedia('(prefers-reduced-motion: reduce)');
function syncMotion(){motionControl.textContent=creature.paused?'Play motion':'Pause motion';}
creature.addEventListener('play',syncMotion);creature.addEventListener('pause',syncMotion);motionControl.addEventListener('click',()=>{if(creature.paused)creature.play().catch(syncMotion);else creature.pause();});
if(motionPreference.matches){creature.autoplay=false;creature.pause();syncMotion();}motionPreference.addEventListener('change',()=>{if(motionPreference.matches)creature.pause();});

const aperture=document.querySelector('#aperture-study');
aperture.innerHTML=Array.from({length:5},(_,ring)=>Array.from({length:8+ring*5},(_,i)=>{const n=8+ring*5,a=i/n*Math.PI*2,r=18+ring*20;return `<ellipse cx="${150+Math.cos(a)*r}" cy="${110+Math.sin(a)*r}" rx="${3+ring*.6}" ry="${5+ring*.6}" transform="rotate(${a*180/Math.PI} ${150+Math.cos(a)*r} ${110+Math.sin(a)*r})" fill="none" stroke="var(--primary)" stroke-width="1.3"/>`}).join('')).join('');
document.querySelectorAll('button[data-type]').forEach(button=>button.addEventListener('click',()=>{document.querySelector('.type-specimen').dataset.type=button.dataset.type;document.querySelectorAll('button[data-type]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));}));
