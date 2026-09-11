(() => {
  const source = document.querySelector('.impedance-heatmap');
  const explorer = document.getElementById('response-explorer');
  if (!source || !explorer) return;
  const rows = [...source.querySelectorAll('rect title')].flatMap(title => {
    const match = title.textContent.match(/^same 0\.12 command, age (\d+), horizon (\d+): ([\d.]+)$/);
    return match ? [{age: Number(match[1]), horizon: Number(match[2]), value: Number(match[3])}] : [];
  });
  if (rows.length !== 133) throw new Error('Expected 19 ages and 7 horizons from the fixed-command heatmap.');
  const ages = [...new Set(rows.map(row => row.age))];
  const horizons = [...new Set(rows.map(row => row.horizon))];
  const ageSelect = document.getElementById('response-age');
  const horizonSelect = document.getElementById('response-horizon');
  ages.forEach(age => ageSelect.add(new Option(age, age, false, age === 780)));
  const value = (age, horizon) => rows.find(row => row.age === age && row.horizon === horizon).value;
  const ns = 'http://www.w3.org/2000/svg';
  const add = (svg, tag, attrs, text) => {
    const element = document.createElementNS(ns, tag);
    for (const [key, val] of Object.entries(attrs)) element.setAttribute(key, val);
    if (text !== undefined) element.textContent = text;
    svg.append(element);
    return element;
  };
  function plot(id, xs, series, maximum, ticks, label, selected) {
    const svg = document.getElementById(id);
    svg.replaceChildren();
    const x = v => 65 + (v - xs[0]) / (xs.at(-1) - xs[0]) * 405;
    const y = v => 275 - v / maximum * 220;
    for (let i = 0; i <= 4; i++) {
      const val = maximum * i / 4;
      add(svg, 'line', {x1:65,x2:470,y1:y(val),y2:y(val),stroke:'#c8cbc3'});
      add(svg, 'text', {x:56,y:y(val)+5,'text-anchor':'end'}, val.toFixed(maximum < .004 ? 4 : 3));
    }
    for (const tick of ticks) add(svg, 'text', {x:x(tick),y:301,'text-anchor':'middle'}, tick);
    add(svg, 'text', {x:65,y:23}, 'Difference between future fields');
    add(svg, 'text', {x:267,y:337,'text-anchor':'middle'}, label);
    for (const item of series) {
      add(svg, 'polyline', {points:xs.map(v=>`${x(v)},${y(item.get(v))}`).join(' '),fill:'none',stroke:item.color,'stroke-width':2.5});
      for (const v of xs) {
        const circle = add(svg, 'circle', {cx:x(v),cy:y(item.get(v)),r:v===selected?6:3.5,fill:item.color});
        add(circle,'title',{},`${item.name}: ${v}, difference ${item.get(v).toFixed(6)}`);
      }
    }
    series.forEach((item,i)=>add(svg,'text',{x:470,y:22+i*20,'text-anchor':'end',fill:item.color,'font-weight':700},item.name));
  }
  function render() {
    const age = Number(ageSelect.value), horizon = Number(horizonSelect.value);
    const maximum = Math.ceil(Math.max(...ages.map(a=>value(a,horizon)))*1000)/1000;
    plot('response-by-age',ages,[{name:`After ${horizon} steps`,color:'#187a6b',get:a=>value(a,horizon)}],maximum,[60,220,380,580,780],'Passage when intervention is applied',age);
    plot('response-by-horizon',horizons,[{name:'Passage 60',color:'#8561b0',get:h=>value(60,h)},{name:`Passage ${age}`,color:'#187a6b',get:h=>value(age,h)}],.016,[4,64,120,240],'Steps after intervention',horizon);
    document.getElementById('response-reading').textContent = `After ${horizon} steps, the field difference is ${value(60,horizon).toFixed(6)} for passage 60 and ${value(age,horizon).toFixed(6)} for passage ${age}. Zero would mean no difference on this measure.`;
  }
  ageSelect.addEventListener('change',render);
  horizonSelect.addEventListener('change',render);
  render();
  explorer.hidden = false;
})();
