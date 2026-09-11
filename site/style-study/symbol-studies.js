const node=(x,y,r=4)=>`<circle cx="${x}" cy="${y}" r="${r}" fill="var(--paper)"/>`;
const box=(x,y,w=16,h=24)=>`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="2" fill="var(--paper)"/>`;
const path=d=>`<path d="${d}"/>`;
const symbolSets={
 wiring:[
 ['Compose','Two processes joined through matching ports.',path('M6 48H90')+box(22,36)+box(58,36)],
 ['Parallel','Two processes retain separate input and output wires.',path('M6 26H90M6 70H90')+box(40,14)+box(40,58)],
 ['Feedback','An output returns to an input through an explicit loop.',path('M6 40H90M72 40V70Q72 80 62 80H28Q18 80 18 70V40')+box(38,28,20,24)+path('M43 76L38 80L43 84')],
 ['Substitute','An outer interface contains a composed pair of processes.',box(16,20,64,56)+path('M4 48H92')+box(27,37,14,22)+box(55,37,14,22)],
 ['Braid','Two wires exchange order. The gap marks a crossing, not a junction.',path('M6 20C38 20 58 76 90 76M6 76C24 76 34 61 42 53M54 41C64 29 73 20 90 20')]
 ],
 relations:[
 ['A₄','A four-node chain from the simply laced Dynkin family.',path('M12 48H84')+[12,36,60,84].map(x=>node(x,48)).join('')],
 ['D₄','Three branches meet at one node.',path('M48 48L16 72M48 48L80 72M48 48V14')+[[48,48],[16,72],[80,72],[48,14]].map(p=>node(...p)).join('')],
 ['E₆','A five-node chain with a branch at its middle.',path('M8 58H88M48 58V23')+[8,28,48,68,88].map(x=>node(x,58,3.5)).join('')+node(48,23,3.5)],
 ['I₂(5)','The edge label is part of the Coxeter diagram.',path('M18 55H78')+node(18,55)+node(78,55)+'<text x="48" y="42" stroke="none" fill="currentColor" text-anchor="middle" font-family="serif" font-size="17">5</text>'],
 ['Commuting square','Two directed routes share a source and target; commutativity is a condition to establish.',path('M20 20H76V76M20 20V76H76M66 16L76 20L66 24M72 66L76 76L80 66M16 66L20 76L24 66M66 72L76 76L66 80')+node(20,20,3)]
 ]};
const host=document.querySelector('.engraved-grid');
function drawSymbols(style){host.innerHTML=symbolSets[style].map(([name,desc,body])=>{const svg=`<svg viewBox="0 0 96 96" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;return `<article>${svg}<h3>${name}</h3><p>${desc}</p><span class="symbol-small">${svg.repeat(3)}</span></article>`}).join('');document.querySelectorAll('[data-symbol-style]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.symbolStyle===style)));document.querySelector('#symbol-family-note').textContent=style==='wiring'?'Wiring studies: interfaces, composition, and feedback. These are schematic design studies, not a formal specification of an experiment.':'Mathematical references drawn as diagrams, not relabeled as generic actions. Edge labels and graph structure belong to their meaning.';}
document.querySelectorAll('[data-symbol-style]').forEach(b=>b.addEventListener('click',()=>drawSymbols(b.dataset.symbolStyle)));drawSymbols('wiring');
const branching=path('M8 48H25C42 48 44 12 68 12H88M25 48C42 48 44 36 68 36H88M25 48C42 48 44 60 68 60H88M25 48C42 48 44 84 68 84H88')+node(25,48)+[12,36,60,84].map(y=>node(88,y,3)).join('');
document.querySelector('.symbol-in-use>svg').outerHTML=`<svg viewBox="0 0 96 96" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">${branching}</svg>`;
