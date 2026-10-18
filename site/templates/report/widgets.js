// Widgets for explorer-layout reports. Each widget block holds a static figure
// rendered at its defaults; a widget hydrates it in place when it nears the
// viewport. Controls are native form elements, so their current state (which a
// review tool may have restored) is the widget's state.

const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");

const round = (n) => Math.round(n * 100) / 100;

function part(root, name) {
  const element = root.querySelector(`[data-part="${name}"]`);
  if (element === null) throw new Error(`${root.id}: missing data-part="${name}"`);
  return element;
}

function controls(root, onChange) {
  const form = root.querySelector("form");
  if (form === null) throw new Error(`${root.id}: missing form`);
  form.addEventListener("submit", (event) => event.preventDefault());
  form.addEventListener("input", onChange);
  form.addEventListener("change", onChange);
  return form.elements;
}

function blob(cx, cy, rx, ry, phase) {
  let d = "";
  for (let i = 0; i <= 64; i++) {
    const t = (i / 64) * Math.PI * 2;
    const f = 1 + 0.065 * Math.sin(3 * t + phase) + 0.04 * Math.cos(5 * t);
    d += `${i ? "L" : "M"}${round(cx + Math.cos(t) * rx * f)},${round(cy + Math.sin(t) * ry * f)}`;
  }
  return `${d}Z`;
}

function arrow(x1, y1, x2, y2, className, missing) {
  const a = Math.atan2(y2 - y1, x2 - x1);
  const s = 7;
  const head = `M${round(x2 - s * Math.cos(a - 0.4))},${round(y2 - s * Math.sin(a - 0.4))}L${round(x2)},${round(y2)}` +
    `L${round(x2 - s * Math.cos(a + 0.4))},${round(y2 - s * Math.sin(a + 0.4))}`;
  return `<g class="rk-rm-edge ${className}"><path d="M${round(x1)},${round(y1)}L${round(x2)},${round(y2)}"` +
    `${missing ? ' class="is-missing"' : ""}/><path d="${head}"/></g>`;
}

function text(x, y, content, attributes = "") {
  return `<text x="${round(x)}" y="${round(y)}" ${attributes}>${content}</text>`;
}

function routeMap(root, data) {
  const map = part(root, "map");
  const mobile = matchMedia(data.layouts.mobile.media);
  const key = ([a, b]) => `${a},${b}`;
  const form = controls(root, draw);
  mobile.addEventListener("change", draw);

  function draw() {
    const network = form.network.value;
    const budget = form.budget.valueAsNumber;
    const broken = form.breakLink.checked;
    const spec = data.networks[network];
    if (spec === undefined) throw new Error(`route-map: unknown network ${network}`);
    let edges = [...data.baseEdges, ...spec.addedEdges];
    if (broken) edges = edges.filter((edge) => key(edge) !== key(data.breakableEdge));
    const present = new Set(edges.map(key));

    const dist = Array(data.states).fill(Infinity);
    const parent = Array(data.states).fill(-1);
    dist[data.start] = 0;
    const queue = [data.start];
    while (queue.length) {
      const a = queue.shift();
      for (const [u, v] of edges) {
        if (u === a && dist[v] === Infinity) {
          dist[v] = dist[a] + 1;
          parent[v] = a;
          queue.push(v);
        }
      }
    }
    const reachable = dist[data.target] <= budget;
    const route = new Set();
    if (reachable) {
      for (let n = data.target; parent[n] >= 0; n = parent[n]) route.add(key([parent[n], n]));
    }

    const layout = mobile.matches ? data.layouts.mobile : data.layouts.desktop;
    const r = layout.nodeRadius;
    let svg = `<title>${data.svgTitle}</title><desc>${data.svgDesc}</desc>`;
    for (const edge of data.drawnEdges) {
      const [a, b] = edge;
      const [x1, y1] = layout.positions[a];
      const [x2, y2] = layout.positions[b];
      const dx = x2 - x1;
      const dy = y2 - y1;
      const len = Math.hypot(dx, dy);
      const exists = present.has(key(edge));
      const state = route.has(key(edge)) ? "is-route"
        : exists && dist[a] < budget && dist[b] <= budget ? "is-active" : "is-idle";
      svg += arrow(x1 + (dx * r) / len, y1 + (dy * r) / len, x2 - (dx * (r + 5)) / len, y2 - (dy * (r + 5)) / len, state, !exists);
    }
    layout.positions.forEach(([x, y], i) => {
      const on = dist[i] <= budget ? " is-on" : "";
      const rx = layout.nodeBase + (i % 3) * 3;
      const ry = layout.nodeBase - (i % 3) * 2;
      svg += `<path class="rk-rm-node${on}" d="${blob(x, y, rx, ry, i)}"/>`;
      if (on) svg += `<circle class="rk-rm-dot" cx="${x}" cy="${y}" r="3"/>`;
      if (i === data.target) svg += `<circle class="rk-rm-ring${on}" cx="${x}" cy="${y}" r="${layout.targetRing}"/>`;
      if (i === data.start || i === data.target) {
        svg += text(x, y + layout.labelOffset, i === data.start ? "START" : "TARGET",
          `text-anchor="middle" font-size="${layout.labelSize}"`);
      }
    });
    map.setAttribute("viewBox", layout.viewBox);
    map.innerHTML = svg;

    let count = 0;
    for (let i = 0; i < data.states; i++) if (i !== data.start && dist[i] <= budget) count++;
    part(root, "count").textContent = count;
    part(root, "budget-value").textContent = budget;
    part(root, "budget-copy").textContent = budget;

    const readout = reachable ? data.readout.reachable : data.readout.unreachable;
    const cases = readout.explanation;
    const setting = network + (broken ? "+broken" : "");
    const sentence = cases[setting];
    if (sentence === undefined) throw new Error(`route-map: no readout for ${setting}`);
    part(root, "headline").textContent = readout.headline;
    part(root, "explanation").textContent =
      readout.lead.replace("{distance}", dist[data.target]).replace("{budget}", budget) + sentence;
  }
  draw();
}

const RELAXATION = "dx/dt = k(m - x)";

function modelPlayback(root, data) {
  const { model, chart, specimen } = data;
  if (model.equation !== RELAXATION) throw new Error(`model-playback: unknown model ${model.equation}`);
  const plot = part(root, "chart");
  const play = part(root, "play");
  const mobile = matchMedia(chart.mobile.media);
  let frame = 0;
  let timer = 0;
  let playing = false;
  let t = 0;
  let geometry;

  const form = controls(root, (event) => {
    if (event.target === form.time) {
      stop();
      drawTime();
    } else {
      drawMemory();
    }
  });
  const tMax = Number(form.time.max);
  if (tMax !== model.tMax) throw new Error(`model-playback: time control ends at ${tMax}, model at ${model.tMax}`);

  function x(time, side, memory) {
    const s = model.offset[side];
    const ti = model.challenges.reduce((last, c) => (c <= time ? c : last), 0);
    const u = time - ti;
    const k = model.k;
    if (memory === "stored") return model.x0 + s * (1 - Math.exp(-k * u));
    const z = 1 / model.fadingTau;
    return model.x0 + ((s * k) / (k - z)) * (Math.exp(-z * time) - Math.exp(-z * ti) * Math.exp(-k * u));
  }

  function drawMemory() {
    const memory = form.memory.value;
    const copy = data.memory[memory];
    if (copy === undefined) throw new Error(`model-playback: unknown memory ${memory}`);
    const size = mobile.matches ? chart.mobile : chart.desktop;
    const { width, height, left } = size;
    const { right, top, bottom } = chart;
    const w = width - left - right;
    const h = height - top - bottom;
    const X = (time) => left + (time / tMax) * w;
    const Y = (value) => top + (1 - value) * h;
    geometry = { X, Y, top, bottom: height - bottom, memory };

    let svg = `<title>${chart.title}</title><desc>${chart.desc}</desc>`;
    chart.gridY.forEach((value, i) => {
      const mid = value === model.x0 ? " is-mid" : "";
      svg += `<path class="rk-mp-grid${mid}" d="M${left},${round(Y(value))}H${width - right}"/>`;
      svg += text(left - 9, Y(value) + 4, chart.gridYLabels[i], 'text-anchor="end" font-size="12"');
    });
    chart.gridT.forEach((time, i) => {
      const challenge = model.challenges.includes(time) ? " is-challenge" : "";
      svg += `<path class="rk-mp-grid${challenge}" d="M${round(X(time))} ${top}V${height - bottom}"/>`;
      svg += text(X(time), height - bottom + 22, String(time), 'text-anchor="middle" font-size="11"');
      if (i < chart.tLabels.length) svg += text(X(time), 24, chart.tLabels[i], 'text-anchor="middle" font-size="12"');
    });
    svg += text(left, height - 5, chart.xAxis, 'font-size="10"');
    svg += `<text transform="translate(13 ${round(top + h / 2)}) rotate(-90)" text-anchor="middle" font-size="10">${chart.yAxis}</text>`;
    const resets = new Set(model.challenges.map((c) => Math.round((c / tMax) * chart.samples)));
    for (const side of ["a", "b"]) {
      let d = "";
      for (let i = 0; i <= chart.samples; i++) {
        const time = (i / chart.samples) * tMax;
        if (resets.has(i)) d += `L${round(X(time))},${round(Y(x(time - 0.0001, side, memory)))}`;
        d += `${i ? "L" : "M"}${round(X(time))},${round(Y(x(time, side, memory)))}`;
      }
      svg += `<path class="rk-mp-curve is-${side}" d="${d}"/>`;
    }
    svg += '<path class="rk-mp-cursor" data-cursor/>';
    svg += '<circle class="rk-mp-dot is-a" r="4.5" data-dot="a"/><circle class="rk-mp-dot is-b" r="4.5" data-dot="b"/>';
    plot.setAttribute("viewBox", `0 0 ${width} ${height}`);
    plot.setAttribute("aria-label", copy.chartLabel);
    plot.innerHTML = svg;
    part(root, "headline").textContent = copy.headline;
    part(root, "explanation").textContent = copy.explanation;
    drawTime();
  }

  function drawTime() {
    const time = playing ? t : form.time.valueAsNumber;
    const { X, Y, top, bottom, memory } = geometry;
    plot.querySelector("[data-cursor]").setAttribute("d", `M${round(X(time))} ${top}V${bottom}`);
    for (const side of ["a", "b"]) {
      const value = x(time, side, memory);
      const dot = plot.querySelector(`[data-dot="${side}"]`);
      dot.setAttribute("cx", round(X(time)));
      dot.setAttribute("cy", round(Y(value)));
      const rx = specimen.rxBase + value * specimen.rxPerUnit;
      part(root, `body-${side}`).innerHTML =
        `<path class="rk-mp-body is-${side}" d="${blob(specimen.cx, specimen.cy, rx, specimen.area / rx, 0)}"/>`;
    }
    part(root, "time-value").textContent = time.toFixed(1);
  }

  function label(on) {
    play.setAttribute("aria-pressed", String(on));
    play.setAttribute("aria-label", `${on ? "Pause" : "Play"} the teaching model`);
    play.textContent = on ? "Ⅱ" : "▶";
  }

  function advance(dt) {
    t = Math.min(tMax, t + dt * data.time.playRate);
    form.time.value = t;
    drawTime();
    if (t >= tMax) stop();
  }

  function stop() {
    playing = false;
    cancelAnimationFrame(frame);
    clearInterval(timer);
    label(false);
  }

  function start() {
    t = form.time.valueAsNumber >= tMax ? 0 : form.time.valueAsNumber;
    playing = true;
    label(true);
    if (reducedMotion.matches) {
      drawTime();
      timer = setInterval(() => advance(1), 1000);
      return;
    }
    let last = 0;
    const step = (now) => {
      if (!playing) return;
      if (last) advance((now - last) / 1000);
      last = now;
      if (playing) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
  }

  play.addEventListener("click", () => (playing ? stop() : start()));
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stop();
  });
  mobile.addEventListener("change", drawMemory);
  drawMemory();
}

const WIDGETS = { "route-map": routeMap, "model-playback": modelPlayback };

async function hydrate(root) {
  try {
    const response = await fetch(root.dataset.src);
    if (!response.ok) throw new Error(`${root.dataset.src}: HTTP ${response.status}`);
    WIDGETS[root.dataset.widget](root, await response.json());
    root.dataset.widgetState = "ready";
  } catch (error) {
    root.dataset.widgetState = "error";
    const note = document.createElement("p");
    note.className = "rk-widget-error";
    note.textContent = `This figure could not start and shows its default state: ${error.message}`;
    root.append(note);
    throw error;
  }
}

const observer = new IntersectionObserver((entries) => {
  for (const entry of entries) {
    if (entry.isIntersecting) {
      observer.unobserve(entry.target);
      hydrate(entry.target);
    }
  }
}, { rootMargin: "300px 0px" });

for (const root of document.querySelectorAll("[data-widget]")) {
  if (!(root.dataset.widget in WIDGETS)) throw new Error(`unknown widget ${root.dataset.widget}`);
  observer.observe(root);
}
