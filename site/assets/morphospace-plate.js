(async()=>{
 const host=document.querySelector('#live-plate');
 const data=await fetch('/assets/blog/lenia-morphospace-report/fish-explainer.json').then(r=>{if(!r.ok)throw Error('Figure data unavailable');return r.json()});
 host.innerHTML=`<h3>Four fish, eleven landmarks each</h3><p>Same x–y projection and coordinate scale; points mark measured anatomy, not body outlines.</p><label>Landmark <select id="landmark-choice"><option value="-1">All landmarks</option>${data.landmarks.map((l,i)=>`<option value="${i}">${l}</option>`).join('')}</select></label><div class="live-fish"></div><p class="landmark-status" role="status"></p><a href="/assets/blog/lenia-morphospace-report/comparison-plate.svg" target="_blank">Export comparison SVG ↗</a>`;
 const bars=document.querySelector('.report-coordinate-bars');
 const rows=[...bars.querySelectorAll('.report-coordinate-row:not(.report-coordinate-header)')];
 document.querySelector('#coordinate-order').addEventListener('change',event=>{
   const key=event.target.value;
   const ordered=key==='original'?rows:[...rows].sort((a,b)=>{
     const value=row=>data.distances.find(d=>d.label===row.firstElementChild.textContent)[key];
     return value(b)-value(a);
   });
   ordered.forEach(row=>bars.append(row));
 });
 host.querySelector('.live-fish').innerHTML=data.fish.slice(0,4).map(f=>`<figure><figcaption>${f.commonName}<em>${f.name}</em></figcaption><svg viewBox="0 0 250 140" role="group" aria-label="${f.commonName} landmarks">${f.points.map((p,i)=>`<circle cx="${140+p[0]*210}" cy="${70-p[1]*210}" r="3.5" tabindex="0" role="button" aria-label="${data.landmarks[i]}" data-point="${i}"><title>${data.landmarks[i]}</title></circle>`).join('')}</svg></figure>`).join('');
 function select(n){host.querySelector('#landmark-choice').value=n;host.querySelectorAll('[data-point]').forEach(p=>{p.classList.toggle('selected',p.dataset.point===String(n));p.classList.toggle('faded',n>=0&&p.dataset.point!==String(n));p.setAttribute('aria-pressed',String(p.dataset.point===String(n)))});host.querySelector('.landmark-status').textContent=n<0?'':data.landmarks[n]+' highlighted in all four specimens.'}
 host.querySelector('#landmark-choice').addEventListener('change',e=>select(Number(e.target.value)));
 host.querySelectorAll('[data-point]').forEach(p=>{p.addEventListener('click',()=>select(Number(p.dataset.point)));p.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(Number(p.dataset.point))}})});
})().catch(e=>{document.querySelector('#live-plate').textContent='The comparison could not load. Use the SVG export below.';console.error(e)});
