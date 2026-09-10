(() => {
  'use strict';
  const root = document.documentElement;
  const blue = [114, 146, 245], apricot = [242, 175, 126], ink = [21, 28, 43];
  function field(canvas, patch, composition) {
    if (!(patch.data instanceof Float32Array) || patch.data.length !== patch.width * patch.height * patch.channels) throw new Error('Invalid decoded channel field.');
    const context = canvas.getContext('2d');
    const raster = context.createImageData(patch.width, patch.height);
    for (let i = 0; i < patch.width * patch.height; i++) {
      let total = 0;
      for (let c = 0; c < patch.channels; c++) total += patch.data[i * patch.channels + c];
      const fraction = total > 0 ? patch.data[i * patch.channels] / total : 0;
      const brightness = 1 - Math.exp(-1.8 * total);
      for (let c = 0; c < 3; c++) {
        const color = composition ? blue[c] * fraction + apricot[c] * (1 - fraction) : [244, 238, 222][c];
        raster.data[i * 4 + c] = Math.round(ink[c] + brightness * (color - ink[c]));
      }
      raster.data[i * 4 + 3] = 255;
    }
    context.putImageData(raster, 0, 0);
  }
  // The publication uses one color scale for the host and every transplant.
  for (const [condition, patch] of Object.entries(PATCHES)) {
    field(document.getElementById(`visible-${condition}`), patch, false);
    field(document.getElementById(`hidden-${condition}`), patch, true);
  }
  const state = document.getElementById('synthesis-state');
  const buttons = [...document.querySelectorAll('[data-field-view]')];
  const host = PATCHES.self_reencode;
  const mass = (patch, i) => patch.data[i * 2] + patch.data[i * 2 + 1];
  const fraction = (patch, i) => mass(patch, i) > 0 ? patch.data[i * 2] / mass(patch, i) : 0;
  // Reconstruct channel densities before coloring, with one fixed crop for all
  // donors. The source arrays and numerical comparisons stay at native resolution.
  let x0 = host.width, y0 = host.height, x1 = 0, y1 = 0;
  for (let y = 0; y < host.height; y++) for (let x = 0; x < host.width; x++) {
    if (mass(host, y * host.width + x) > .01) {
      x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y);
    }
  }
  const side = Math.min(host.width, Math.ceil(Math.max(x1 - x0 + 1, y1 - y0 + 1) * 1.3));
  const left = Math.max(0, Math.min(host.width - side, (x0 + x1 + 1 - side) / 2));
  const top = Math.max(0, Math.min(host.height - side, (y0 + y1 + 1 - side) / 2));
  const presentations = new Map();
  function presentation(patch) {
    if (presentations.has(patch)) return presentations.get(patch);
    const size = 512, data = new Float32Array(size * size * 2);
    for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
      const sx = Math.max(0, Math.min(patch.width - 1, left + (x + .5) * side / size - .5));
      const sy = Math.max(0, Math.min(patch.height - 1, top + (y + .5) * side / size - .5));
      const ix = Math.floor(sx), iy = Math.floor(sy), fx = sx - ix, fy = sy - iy;
      const nx = Math.min(ix + 1, patch.width - 1), ny = Math.min(iy + 1, patch.height - 1);
      for (let c = 0; c < 2; c++) {
        const a = patch.data[(iy * patch.width + ix) * 2 + c], b = patch.data[(iy * patch.width + nx) * 2 + c];
        const d = patch.data[(ny * patch.width + ix) * 2 + c], e = patch.data[(ny * patch.width + nx) * 2 + c];
        data[(y * size + x) * 2 + c] = (a * (1 - fx) + b * fx) * (1 - fy) + (d * (1 - fx) + e * fx) * fy;
      }
    }
    const result = {width:size, height:size, channels:2, data};
    presentations.set(patch, result);
    return result;
  }
  // Fixed diverging scale: colors saturate at +/-25 percentage points.
  // The numeric readout uses the full, unclipped channel fractions.
  const differenceScale = .25;
  function difference(canvas, patch) {
    const displayHost = presentation(host), displayPatch = presentation(patch);
    const ctx = canvas.getContext('2d'), pixels = ctx.createImageData(displayHost.width, displayHost.height);
    for (let i = 0; i < displayHost.width * displayHost.height; i++) {
      const total = mass(displayHost, i), delta = fraction(displayPatch, i) - fraction(displayHost, i);
      const brightness = 1 - Math.exp(-1.8 * total);
      const magnitude = Math.min(1, Math.abs(delta) / differenceScale);
      const color = delta >= 0 ? blue : apricot;
      for (let c = 0; c < 3; c++) pixels.data[i * 4 + c] = Math.round(ink[c] + brightness * (.08 * (230 - ink[c]) + .92 * magnitude * (color[c] - ink[c])));
      pixels.data[i * 4 + 3] = 255;
    }
    ctx.putImageData(pixels, 0, 0);
    let weightedChange = 0, weight = 0;
    for (let i = 0; i < host.width * host.height; i++) {
      const total = mass(host, i);
      weightedChange += total * Math.abs(fraction(patch, i) - fraction(host, i)); weight += total;
    }
    return 100 * weightedChange / weight;
  }
  let mode = 'difference';
  function showField() {
    const canvas = document.getElementById('synthesis-field'), patch = PATCHES[state.value];
    const label = state.selectedOptions[0].textContent;
    let reading;
    if (mode === 'difference') {
      const change = difference(canvas, patch);
      reading = `${label}: ${change.toFixed(1)} percentage-point mean change from host, weighted by matter.`;
    } else {
      field(canvas, presentation(patch), mode === 'composition');
      reading = mode === 'composition' ? `${label}: blue and apricot show the two channel fractions.` : `${label}: total matter is unchanged by every transplant.`;
    }
    canvas.setAttribute('aria-label', reading);
    buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.fieldView === mode)));
    document.getElementById('field-reading').textContent = reading;
    document.getElementById('field-scale').textContent = mode === 'difference'
      ? `Channel 1 change: apricot ≤ −25 pp · blue ≥ +25 pp. Shared scale; colors saturate at the ends.`
      : 'Saved transplant states · brightness shows total matter.';
  }
  buttons.forEach(button => button.addEventListener('click', () => { mode = button.dataset.fieldView; showField(); }));
  state.addEventListener('change', showField);
  showField();

  const rows = [...document.querySelectorAll('.impedance-heatmap rect title')].flatMap(title => {
    const match = title.textContent.match(/^same 0\.12 command, age (\d+), horizon (\d+): ([\d.]+)$/);
    return match ? [{age: +match[1], horizon: +match[2], value: +match[3]}] : [];
  });
  if (rows.length !== 133) throw new Error('The developmental instrument requires all 133 recorded means.');
  const ages = [60, 180, 380, 580, 780];
  const portraits = [...document.querySelectorAll('#impedance .native-strip img')];
  if (portraits.length !== ages.length) throw new Error('Five age-matched native portraits are required.');
  const slider = document.getElementById('synthesis-age');
  const horizon = document.getElementById('synthesis-horizon');
  const play = document.getElementById('synthesis-play');
  const svg = document.getElementById('synthesis-age-chart');
  const number = (age, h) => rows.find(row => row.age === age && row.horizon === h).value;
  const ns = 'http://www.w3.org/2000/svg';
  function add(tag, attributes, text) {
    const element = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attributes)) element.setAttribute(k, v);
    if (text !== undefined) element.textContent = text;
    svg.append(element);
    return element;
  }
  function portrait(index) {
    const canvas = document.getElementById('synthesis-age-field'), ctx = canvas.getContext('2d');
    ctx.drawImage(portraits[index], 0, 0, 128, 128);
    const pixels = ctx.getImageData(0, 0, 128, 128);
    for (let i = 0; i < pixels.data.length; i += 4) {
      const amount = pixels.data[i] / 255;
      for (let c = 0; c < 3; c++) pixels.data[i + c] = Math.round(ink[c] + amount * (apricot[c] - ink[c]));
    }
    ctx.putImageData(pixels, 0, 0);
  }
  let ready = false;
  function render() {
    const index = +slider.value, age = ages[index], h = +horizon.value;
    const selected = rows.filter(row => row.horizon === h);
    const max = Math.ceil(Math.max(...selected.map(row => row.value)) * 1000) / 1000;
    const width = svg.getBoundingClientRect().width < 450 ? 340 : 660;
    svg.setAttribute("viewBox", `0 0 ${width} 300`);
    const right = width - 20;
    const x = age => 58 + (age - 60) / 720 * (right - 58), y = value => 248 - value / max * 213;
    const primary = getComputedStyle(root).getPropertyValue('--specter-blue').trim();
    svg.replaceChildren();
    for (let i = 0; i <= 4; i++) {
      const v = max * i / 4;
      add('line', {x1:58, x2:right, y1:y(v), y2:y(v), stroke:'#d7d2c9', 'stroke-width':1});
      add('text', {x:48, y:y(v)+4, 'text-anchor':'end'}, v.toFixed(max < .004 ? 4 : 3));
    }
    for (const a of (width < 450 ? [60,380,780] : ages)) add('text', {x:x(a), y:272, 'text-anchor':'middle'}, a);
    add('text', {x:(58+right)/2,y:298,'text-anchor':'middle'}, 'Age at intervention (passage)');
    add('polyline', {points:selected.map(row=>`${x(row.age)},${y(row.value)}`).join(' '), fill:'none', stroke:primary, 'stroke-width':2.5});
    add('line', {x1:x(age),x2:x(age),y1:25,y2:248,stroke:'#ae4a28','stroke-dasharray':'3 5','stroke-width':1});
    for (const row of selected) {
      const dot = add('circle',{cx:x(row.age),cy:y(row.value),r:row.age===age?6:2.5,fill:row.age===age?'#ae4a28':primary});
      const title = document.createElementNS(ns,'title');title.textContent=`Passage ${row.age}: ${row.value.toFixed(6)}`;dot.append(title);
    }
    const value = number(age,h), initial = number(60,h), reduction = (1-value/initial)*100;
    document.getElementById('synthesis-age-value').textContent = value.toFixed(4);
    document.getElementById('synthesis-age-label').textContent = `Passage ${age}`;
    document.getElementById('synthesis-age-reading').textContent = age === 60
      ? `At passage 60, the mean difference after ${h} steps is ${value.toFixed(6)}. Move to a later checkpoint to compare the effect.`
      : `At passage ${age}, the mean difference after ${h} steps is ${value.toFixed(6)}—${Math.abs(reduction).toFixed(0)}% ${reduction>=0?'smaller':'larger'} than at passage 60.`;
    if (ready) portrait(index);
  }
  let timer;
  function stop() { clearInterval(timer); timer = undefined; play.textContent = 'Play five checkpoints'; }
  play.addEventListener('click', () => {
    if (timer) { stop(); return; }
    if (+slider.value === 4) slider.value = '0';
    render();play.textContent = 'Pause checkpoints';
    timer = setInterval(() => { slider.value=String(+slider.value+1);render();if(+slider.value===4)stop(); }, 1600);
  });
  slider.addEventListener('input', () => { stop(); render(); });
  horizon.addEventListener('change', render);
  document.addEventListener('visibilitychange', () => { if(document.hidden)stop(); });
  new IntersectionObserver(entries => { if (!entries[0].isIntersecting)stop(); }).observe(document.getElementById('development-observation'));
  render();
  let previousWidth;
  new ResizeObserver(entries => {
    const width = entries[0].contentRect.width;
    if (width !== previousWidth) { previousWidth = width; render(); }
  }).observe(document.querySelector('.synthesis-age-data'));
  Promise.all(portraits.map(img=>img.decode())).then(()=>{ready=true;render();});
})();
