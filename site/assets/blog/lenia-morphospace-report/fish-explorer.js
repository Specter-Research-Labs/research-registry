(async () => {
  const root = document.querySelector('[data-fish-explorer]');
  if (!root) return;
  const response = await fetch('/assets/blog/lenia-morphospace-report/fish-explainer.json');
  if (!response.ok) throw new Error(`Fish coordinates: HTTP ${response.status}`);
  const data = await response.json();
  const svg = root.querySelector('svg');
  const choice = root.querySelector('select');
  const angle = root.querySelector('input');
  const label = root.querySelector('.report-fish-point-label');
  let selectedPoint = null;
  const ns = 'http://www.w3.org/2000/svg';
  const sub = (a, b) => a.map((v, i) => v - b[i]);
  const dot = (a, b) => a.reduce((s, v, i) => s + v * b[i], 0);
  const unit = a => a.map(v => v / Math.hypot(...a));
  const cross = (a, b) => [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
  const aligned = data.fish.map(fish => {
    const p = fish.points;
    const tail = p[5].map((v, i) => (v + p[10][i]) / 2);
    const axis = unit(sub(tail, p[0]));
    const dorsal = sub(p[6], p[0]);
    const up = unit(dorsal.map((v, i) => v - dot(dorsal, axis)*axis[i]));
    const across = cross(axis, up);
    return p.map(v => [dot(v, axis), dot(v, up), dot(v, across)]);
  });
  const extent = Math.max(...aligned.flat().map(p => Math.hypot(...p)));
  const scale = 260 / extent;
  const guidePaths = [[0,1,2,3,4,5],[0,7,8,9,4,10],[0,6,5],[6,10],[1,7],[2,8],[3,9],[5,10]];
  const el = (tag, attrs, text) => {
    const node = document.createElementNS(ns, tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  data.fish.forEach((fish, i) => choice.add(new Option(`${fish.commonName} · ${fish.name}`, i)));
  function draw() {
    const index = Number(choice.value);
    const fish = data.fish[index];
    const theta = Number(angle.value) * Math.PI / 180;
    const projected = aligned[index].map(([x,y,z]) => [350+x*scale,160-(y*Math.cos(theta)+z*Math.sin(theta))*scale]);
    svg.replaceChildren(el('title', {}, `${fish.name}: eleven measured landmarks, ${angle.value} degrees around the body axis`));
    for (const path of guidePaths) svg.append(el('polyline', {points: path.map(i => projected[i].join(',')).join(' '), fill:'none',stroke:'#254fd4','stroke-opacity':'.25','stroke-width':'1.5'}));
    projected.forEach(([x,y],i) => {
      const name = `${i+1}. ${data.landmarks[i]}`;
      const group = el('g', {role:'button',tabindex:'0','aria-label':name,'aria-pressed':String(i === selectedPoint)});
      group.append(el('circle',{cx:x,cy:y,r:30,fill:'transparent'}));
      group.append(el('circle',{cx:x,cy:y,r:5,fill:'#254fd4',stroke:'#f2eee3','stroke-width':2}));
      group.append(el('text',{x:x+9,y:y+(i%2 ? 18 : -10),fill:'#254fd4','font-size':14,'font-family':'monospace'},i+1));
      const identify = () => { selectedPoint = i; label.textContent = name; svg.querySelectorAll('[role=button]').forEach((node, j) => node.setAttribute('aria-pressed', String(j === i))); };
      
      group.addEventListener('focus',identify);
      group.addEventListener('click',identify);
      group.addEventListener('keydown',event => { if (event.key === 'Enter' || event.key === ' ') {event.preventDefault();identify();} });
      svg.append(group);
    });
    root.querySelector('h4').textContent = fish.commonName;
    root.querySelector('.report-fish-scientific').textContent = fish.name;
    root.querySelector('.report-fish-controls > p').textContent = index === 0 ? 'The fish nearest to flow-map-elite-53. Turn it to see how paired landmarks separate in three dimensions.' : 'Another measured specimen from the reference dataset. The same anatomical landmarks reveal a different arrangement.';
    svg.setAttribute('aria-label',`${fish.name}, eleven numbered anatomical landmarks`);
  }
  choice.addEventListener('change',() => {label.textContent=selectedPoint === null ? 'Select a numbered point to identify it.' : `${selectedPoint+1}. ${data.landmarks[selectedPoint]}`;draw();});
  angle.addEventListener('input',draw);
  draw();
  root.querySelector('.report-fish-fallback').hidden = true;
  root.querySelector('.report-fish-controls').hidden = false;
  svg.removeAttribute('hidden');
})();
