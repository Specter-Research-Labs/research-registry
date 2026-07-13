(() => {
    "use strict";

    const content = document.querySelector(".doc-content");
    if (!content) return;

    const WIDGET_INIT = {
        creaturewall: initCreatureWall,
        sandbox: initSandbox,
        kernel: initKernel,
        growth: initGrowth,
        massconservation: initMassConservation,
        search: initSearch,
        cvt: initCVT,
        mapelites: initMapElites,
        isoline: initIsoline,
    };

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const LENIA_SPECTRUM = [
        [5, 4, 10],
        [124, 245, 255],
        [80, 123, 255],
        [191, 55, 255],
        [255, 58, 175],
        [255, 113, 56],
        [255, 204, 69],
    ];

    function lazyInit(el, initFn) {
        const observer = new IntersectionObserver(
            (entries) => {
                for (const entry of entries) {
                    if (entry.isIntersecting) {
                        observer.unobserve(el);
                        initFn(el);
                        el.classList.add("is-ready");
                    }
                }
            },
            { rootMargin: "200px" }
        );
        observer.observe(el);
    }

    const widgets = content.querySelectorAll(".lenia-widget[data-widget]");
    for (const el of widgets) {
        const type = el.dataset.widget;
        const initFn = WIDGET_INIT[type];
        if (!initFn) {
            console.warn("[lenia-explainer] unknown widget type:", type);
            continue;
        }
        lazyInit(el, initFn);
    }

    function makeHeader(el, title, subtitle) {
        const header = document.createElement("div");
        header.className = "lenia-widget-header";
        const titleEl = document.createElement("div");
        titleEl.className = "lenia-widget-title";
        titleEl.textContent = title;
        header.appendChild(titleEl);
        if (subtitle) {
            const sub = document.createElement("div");
            sub.className = "lenia-widget-subtitle";
            sub.textContent = subtitle;
            header.appendChild(sub);
        }
        el.appendChild(header);
        return header;
    }

    function makeSlider(label, min, max, step, value, onChange, format) {
        const group = document.createElement("div");
        group.className = "lenia-slider-group";
        const lbl = document.createElement("label");
        lbl.textContent = label;
        const input = document.createElement("input");
        input.type = "range";
        input.min = String(min);
        input.max = String(max);
        input.step = String(step);
        input.value = String(value);
        const readout = document.createElement("span");
        readout.className = "lenia-slider-value";
        const fmt = format || ((v) => Number(v).toFixed(3));
        readout.textContent = fmt(value);
        input.addEventListener("input", () => {
            const v = Number(input.value);
            readout.textContent = fmt(v);
            onChange(v);
        });
        group.append(lbl, input, readout);
        return { group, input, readout };
    }

    function makeBtn(text, onClick) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "lenia-btn";
        btn.textContent = text;
        btn.addEventListener("click", onClick);
        return btn;
    }

    function parseDefaults(el) {
        const raw = el.dataset.defaults;
        if (!raw) return {};
        return JSON.parse(raw);
    }

    function dpr() {
        return Math.min(window.devicePixelRatio || 1, 2);
    }

    function initCanvas(width, height) {
        const canvas = document.createElement("canvas");
        const ratio = dpr();
        canvas.width = width * ratio;
        canvas.height = height * ratio;
        canvas.style.width = "100%";
        canvas.style.height = "auto";
        const ctx = canvas.getContext("2d");
        ctx.scale(ratio, ratio);
        return { canvas, ctx, w: width, h: height, ratio };
    }

    function putPixels(cvs, imageData) {
        const tmp = document.createElement("canvas");
        tmp.width = cvs.w;
        tmp.height = cvs.h;
        const tmpCtx = tmp.getContext("2d");
        tmpCtx.putImageData(imageData, 0, 0);
        cvs.ctx.imageSmoothingEnabled = false;
        cvs.ctx.drawImage(tmp, 0, 0);
        cvs.ctx.imageSmoothingEnabled = true;
    }

    function makeMetric(label, value, kind) {
        const m = document.createElement("div");
        m.className = "lenia-metric";
        const lbl = document.createElement("span");
        lbl.className = "lenia-metric-label";
        lbl.textContent = label;
        const val = document.createElement("span");
        val.className = "lenia-metric-value" + (kind ? " " + kind : "");
        val.textContent = value;
        m.append(lbl, val);
        return m;
    }

    function makeCaption(text) {
        const cap = document.createElement("div");
        cap.className = "lenia-canvas-caption";
        cap.textContent = text;
        return cap;
    }

    function splitmix32(seed) {
        let s = seed | 0;
        return () => {
            s = (s + 0x9e3779b9) | 0;
            let z = s;
            z = Math.imul(z ^ (z >>> 16), 0x85ebca6b);
            z = Math.imul(z ^ (z >>> 13), 0xc2b2ae35);
            z = (z ^ (z >>> 16)) >>> 0;
            return z / 0x100000000;
        };
    }

    function spectrumColor(t) {
        const corrected = Math.pow(Math.max(0, Math.min(1, t)), 0.88);
        const scaled = corrected * (LENIA_SPECTRUM.length - 1);
        const lo = Math.floor(scaled);
        const hi = Math.min(lo + 1, LENIA_SPECTRUM.length - 1);
        const b = scaled - lo;
        return [
            Math.round(LENIA_SPECTRUM[lo][0] + (LENIA_SPECTRUM[hi][0] - LENIA_SPECTRUM[lo][0]) * b),
            Math.round(LENIA_SPECTRUM[lo][1] + (LENIA_SPECTRUM[hi][1] - LENIA_SPECTRUM[lo][1]) * b),
            Math.round(LENIA_SPECTRUM[lo][2] + (LENIA_SPECTRUM[hi][2] - LENIA_SPECTRUM[lo][2]) * b),
        ];
    }

    function buildSpectrumLookup() {
        const lookup = new Uint8ClampedArray(256 * 4);
        for (let v = 0; v < 256; v++) {
            const c = spectrumColor(v / 255);
            const base = v * 4;
            lookup[base] = c[0];
            lookup[base + 1] = c[1];
            lookup[base + 2] = c[2];
            lookup[base + 3] = 255;
        }
        return lookup;
    }

    function makeCanvasWrap(cls) {
        const wrap = document.createElement("div");
        wrap.className = "lenia-canvas-wrap " + (cls || "");
        return wrap;
    }

    function makeLegend(items) {
        const legend = document.createElement("div");
        legend.className = "lenia-legend";
        for (const it of items) {
            const span = document.createElement("span");
            span.className = "lenia-legend-item";
            const sw = document.createElement("span");
            sw.className = "lenia-legend-swatch";
            sw.style.background = it.color;
            span.append(sw, document.createTextNode(it.label));
            legend.appendChild(span);
        }
        return legend;
    }

    // ---------------------------------------------------------------
    // shared: CPU Lenia engine used by smaller widgets
    // ---------------------------------------------------------------

    function makeCPUEngine(opts) {
        const sx = opts.sx;
        const sy = opts.sy;
        const R = opts.R;
        const rK = opts.r;
        const bK = opts.b;
        const wK = opts.w;
        const aK = opts.a;
        const mu = opts.mu;
        const sigma = opts.sigma;
        const h = opts.h;
        const dt = opts.dt;
        const seed = opts.seed ?? 0;
        const patchR = (opts.patchR ?? 0.18) * Math.min(sx, sy);

        const kernelRadius = Math.ceil(R * rK);
        const kSize = 2 * kernelRadius + 1;
        const kernel = new Float32Array(kSize * kSize);
        let kernelSum = 0;
        for (let ky = -kernelRadius; ky <= kernelRadius; ky++) {
            for (let kx = -kernelRadius; kx <= kernelRadius; kx++) {
                const dist = Math.sqrt(kx * kx + ky * ky);
                const D = dist / (R * rK);
                let val = 0;
                for (let g = 0; g < bK.length; g++) {
                    const diff = D - aK[g];
                    val += bK[g] * Math.exp(-(diff * diff) / (2 * wK[g] * wK[g]));
                }
                kernel[(ky + kernelRadius) * kSize + (kx + kernelRadius)] = val;
                kernelSum += val;
            }
        }
        if (kernelSum > 0) for (let i = 0; i < kernel.length; i++) kernel[i] /= kernelSum;

        let state = new Float32Array(sx * sy);

        function seedPatch(cx, cy, rng) {
            const r2 = patchR * patchR;
            for (let y = 0; y < sy; y++) {
                for (let x = 0; x < sx; x++) {
                    const dx = x - cx, dy = y - cy;
                    if (dx * dx + dy * dy <= r2) {
                        state[y * sx + x] = rng();
                    }
                }
            }
        }

        function reset(extraSeed) {
            state = new Float32Array(sx * sy);
            const rng = splitmix32(seed + (extraSeed || 0));
            seedPatch(sx / 2, sy / 2, rng);
        }

        function step(massPreserving) {
            const next = new Float32Array(sx * sy);
            let dMass = 0;
            for (let y = 0; y < sy; y++) {
                for (let x = 0; x < sx; x++) {
                    let U = 0;
                    for (let ky = -kernelRadius; ky <= kernelRadius; ky++) {
                        for (let kx = -kernelRadius; kx <= kernelRadius; kx++) {
                            const kIdx = (ky + kernelRadius) * kSize + (kx + kernelRadius);
                            const wK = kernel[kIdx];
                            if (wK < 1e-10) continue;
                            const nx = ((x + kx) % sx + sx) % sx;
                            const ny = ((y + ky) % sy + sy) % sy;
                            U += state[ny * sx + nx] * wK;
                        }
                    }
                    const diff = (U - mu) / sigma;
                    const G = (2 * Math.exp(-(diff * diff) / 2) - 1) * h;
                    const cur = state[y * sx + x];
                    const candidate = Math.max(0, Math.min(1, cur + dt * G));
                    dMass += candidate - cur;
                    next[y * sx + x] = candidate;
                }
            }
            if (massPreserving) {
                const totalMass = next.reduce((a, b) => a + b, 0);
                const targetMass = state.reduce((a, b) => a + b, 0);
                if (totalMass > 0) {
                    const f = targetMass / totalMass;
                    for (let i = 0; i < next.length; i++) next[i] = Math.min(1, next[i] * f);
                }
            }
            state = next;
            return dMass;
        }

        reset();
        return {
            step,
            reset,
            mass() { let m = 0; for (let i = 0; i < state.length; i++) m += state[i]; return m; },
            getState() { return state; },
            seedAt(cx, cy, rng) { seedPatch(cx, cy, rng); },
            sx, sy,
        };
    }

    function renderStateToImageData(state, sx, sy, imageData, lookup) {
        for (let i = 0; i < sx * sy; i++) {
            const byteVal = Math.round(Math.max(0, Math.min(1, state[i])) * 255);
            const src = byteVal * 4;
            const dst = i * 4;
            imageData.data[dst] = lookup[src];
            imageData.data[dst + 1] = lookup[src + 1];
            imageData.data[dst + 2] = lookup[src + 2];
            imageData.data[dst + 3] = 255;
        }
    }

    // ---------------------------------------------------------------
    // W0: Creature wall (hero, top of page)
    // ---------------------------------------------------------------

    function initCreatureWall(el) {
        makeHeader(el, "Orbium", "single-channel, single-Gaussian Lenia");

        const wrap = makeCanvasWrap("dark");
        const canvas = document.createElement("canvas");
        canvas.style.imageRendering = "pixelated";
        wrap.appendChild(canvas);
        const caption = makeCaption("loading...");
        wrap.appendChild(caption);

        const body = document.createElement("div");
        body.className = "lenia-widget-body";
        body.append(wrap);
        el.appendChild(body);

        function startWebGPU() {
            if (typeof LeniaGPU === "undefined" || !navigator.gpu) return false;
            LeniaGPU.load("orbium", canvas).then((engine) => {
                if (!engine) throw new Error("WebGPU did not return an engine");
                caption.textContent = "WebGPU · basic Lenia";
                engine.render();
                const tick = () => {
                    if (!reducedMotion) engine.step();
                    engine.render();
                    requestAnimationFrame(tick);
                };
                requestAnimationFrame(tick);
            }).catch(() => startCPUFallback());
            return true;
        }

        function startCPUFallback() {
            const cpuCanvas = initCanvas(96, 96);
            wrap.replaceChild(cpuCanvas.canvas, canvas);
            const engine = makeCPUEngine({
                sx: 96, sy: 96, R: 13, r: 1,
                b: [1], w: [0.15], a: [0.5],
                mu: 0.15, sigma: 0.015, h: 1, dt: 0.1,
                seed: 17, patchR: 0.14,
            });
            const pixels = cpuCanvas.ctx.createImageData(96, 96);
            const lookup = buildSpectrumLookup();
            caption.textContent = "CPU fallback";
            let lastStep = 0;
            const tick = (now) => {
                if (!reducedMotion && now - lastStep >= 45) {
                    engine.step(false);
                    lastStep = now;
                }
                renderStateToImageData(engine.getState(), 96, 96, pixels, lookup);
                putPixels(cpuCanvas, pixels);
                requestAnimationFrame(tick);
            };
            requestAnimationFrame(tick);
        }

        if (!startWebGPU()) startCPUFallback();
    }

    // ---------------------------------------------------------------
    // W1: Sandbox (the big live simulation)
    // ---------------------------------------------------------------

    function initSandbox(el) {
        makeHeader(el, "Live Lenia simulation", "switch creature in the dropdown, click to reseed");

        const defaultCreature = el.dataset.creature || "orbium";
        const wrap = makeCanvasWrap("dark");
        const canvas = document.createElement("canvas");
        canvas.style.imageRendering = "pixelated";
        wrap.appendChild(canvas);
        const caption = makeCaption("loading...");
        wrap.appendChild(caption);

        const side = document.createElement("div");
        side.style.display = "flex";
        side.style.flexDirection = "column";
        side.style.gap = "10px";

        const select = document.createElement("select");
        select.className = "lenia-select";
        for (const c of ["orbium", "geminium", "aquarium"]) {
            const opt = document.createElement("option");
            opt.value = c;
            opt.textContent = c;
            select.appendChild(opt);
        }
        select.value = defaultCreature;

        const playingRef = { value: !reducedMotion };
        const playBtn = makeBtn(playingRef.value ? "Pause" : "Play", () => {
            playingRef.value = !playingRef.value;
            playBtn.textContent = playingRef.value ? "Pause" : "Play";
        });
        const resetBtn = makeBtn("Reset", () => engine && engine.reset && engine.reset());
        const resetSpeed = { value: 1 };
        const speedSlider = makeSlider("speed", 0.25, 4.0, 0.25, 1, (v) => { resetSpeed.value = v; }, (v) => Number(v).toFixed(2) + "x");

        const row1 = document.createElement("div");
        row1.style.display = "flex";
        row1.style.gap = "8px";
        row1.style.alignItems = "center";
        row1.append(select, playBtn, resetBtn);

        const fpsMetric = makeMetric("fps", "—");
        const stepMetric = makeMetric("steps", "0");
        const metricsBox = document.createElement("div");
        metricsBox.style.display = "flex";
        metricsBox.style.flexWrap = "wrap";
        metricsBox.style.gap = "6px";
        metricsBox.append(fpsMetric, stepMetric);

        side.append(row1, speedSlider.group, metricsBox);

        const body = document.createElement("div");
        body.className = "lenia-widget-body sandbox-layout";
        body.append(wrap, side);
        el.appendChild(body);

        let engine = null;
        let stepCount = 0;
        let lastFpsTime = performance.now();
        let frames = 0;

        function loadCreature(name) {
            stepCount = 0;
            stepMetric.querySelector(".lenia-metric-value").textContent = "0";
            caption.textContent = name;
            if (typeof LeniaGPU === "undefined" || !navigator.gpu) {
                caption.textContent = "WebGPU required";
                return;
            }
            LeniaGPU.load(name, canvas).then((e) => {
                if (!e) {
                    caption.textContent = "WebGPU init failed";
                    return;
                }
                engine = e;
                caption.textContent = `WebGPU · ${e.dynamics} Lenia`;
                runLoop();
            }).catch(() => {
                caption.textContent = "WebGPU init failed";
            });
        }

        select.addEventListener("change", () => loadCreature(select.value));

        canvas.addEventListener("click", () => {
            if (!engine || !engine.reset) return;
            engine.reset();
        });

        loadCreature(defaultCreature);

        function runLoop() {
            let acc = 0;
            const target = 16;
            let lastTime = performance.now();
            function frame(now) {
                const dt = now - lastTime;
                lastTime = now;
                acc += dt * resetSpeed.value;
                if (playingRef.value && engine && engine.step) {
                    while (acc >= target) {
                        engine.step();
                        stepCount++;
                        acc -= target;
                    }
                    if (engine.render) engine.render();
                }
                frames++;
                if (now - lastFpsTime > 500) {
                    const fps = (frames * 1000) / (now - lastFpsTime);
                    fpsMetric.querySelector(".lenia-metric-value").textContent = fps.toFixed(0);
                    lastFpsTime = now;
                    frames = 0;
                    stepMetric.querySelector(".lenia-metric-value").textContent = String(stepCount);
                }
                requestAnimationFrame(frame);
            }
            requestAnimationFrame(frame);
        }
    }

    // ---------------------------------------------------------------
    // W2: Kernel visualizer
    // ---------------------------------------------------------------

    function initKernel(el) {
        makeHeader(el, "Kernel visualizer", "the donut profile every cell convolves against");
        const defaults = parseDefaults(el);
        let R = defaults.R ?? 13;
        let r = defaults.r ?? 0.5;
        let bArr = (defaults.b ?? [1]).slice();
        let wArr = (defaults.w ?? [0.2]).slice();
        let aArr = (defaults.a ?? [0.5]).slice();

        const profileCvs = initCanvas(420, 220);
        const heatCvs = initCanvas(260, 260);

        const profileWrap = makeCanvasWrap("plot");
        profileWrap.appendChild(profileCvs.canvas);
        profileWrap.appendChild(makeCaption("radial profile K(D)"));

        const heatWrap = makeCanvasWrap("dark");
        heatWrap.appendChild(heatCvs.canvas);
        heatWrap.appendChild(makeCaption("2D kernel weights"));

        const body = document.createElement("div");
        body.className = "lenia-widget-body dual-panel";
        body.append(profileWrap, heatWrap);

        const controls = document.createElement("div");
        controls.className = "lenia-controls";
        const sR = makeSlider("R", 4, 30, 1, R, (v) => { R = v; draw(); }, (v) => Number(v).toFixed(0));
        const sr = makeSlider("r", 0.1, 1.0, 0.01, r, (v) => { r = v; draw(); });
        const sa = makeSlider("a", 0.0, 1.0, 0.01, aArr[0], (v) => { aArr[0] = v; draw(); });
        const sw = makeSlider("w", 0.01, 0.5, 0.01, wArr[0], (v) => { wArr[0] = v; draw(); });
        controls.append(sR.group, sr.group, sa.group, sw.group);

        el.append(body, controls);
        draw();

        function kernelProfile(D) {
            let val = 0;
            for (let g = 0; g < bArr.length; g++) {
                const diff = D - aArr[g];
                val += bArr[g] * Math.exp(-(diff * diff) / (2 * wArr[g] * wArr[g]));
            }
            return val;
        }

        function draw() {
            drawProfile();
            drawHeatmap();
        }

        function drawProfile() {
            const { ctx, w, h } = profileCvs;
            ctx.clearRect(0, 0, w, h);

            const pad = { left: 44, right: 18, top: 18, bottom: 28 };
            const pw = w - pad.left - pad.right;
            const ph = h - pad.top - pad.bottom;

            const steps = 240;
            const values = [];
            let maxVal = 0;
            for (let i = 0; i <= steps; i++) {
                const D = i / steps;
                const v = kernelProfile(D);
                values.push(v);
                if (v > maxVal) maxVal = v;
            }
            if (maxVal === 0) maxVal = 1;

            ctx.strokeStyle = "rgba(11, 14, 20, 0.06)";
            ctx.lineWidth = 1;
            for (let i = 1; i < 5; i++) {
                const y = pad.top + (i / 5) * ph;
                ctx.beginPath();
                ctx.moveTo(pad.left, y);
                ctx.lineTo(pad.left + pw, y);
                ctx.stroke();
            }

            ctx.strokeStyle = "rgba(11, 14, 20, 0.35)";
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(pad.left, pad.top + ph);
            ctx.lineTo(pad.left + pw, pad.top + ph);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(pad.left, pad.top);
            ctx.lineTo(pad.left, pad.top + ph);
            ctx.stroke();

            ctx.fillStyle = "rgba(11, 14, 20, 0.55)";
            ctx.font = "10px var(--sl-font-mono, monospace)";
            ctx.textAlign = "center";
            ctx.fillText("D=0", pad.left, pad.top + ph + 16);
            ctx.fillText("D=1", pad.left + pw, pad.top + ph + 16);
            ctx.textAlign = "right";
            ctx.fillText("0", pad.left - 6, pad.top + ph + 3);
            ctx.fillText(maxVal.toFixed(2), pad.left - 6, pad.top + 10);

            const grad = ctx.createLinearGradient(pad.left, 0, pad.left + pw, 0);
            grad.addColorStop(0.0, "rgba(80, 123, 255, 0.18)");
            grad.addColorStop(0.5, "rgba(255, 58, 175, 0.20)");
            grad.addColorStop(1.0, "rgba(255, 204, 69, 0.10)");

            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.moveTo(pad.left, pad.top + ph);
            for (let i = 0; i <= steps; i++) {
                const x = pad.left + (i / steps) * pw;
                const y = pad.top + ph - (values[i] / maxVal) * ph;
                ctx.lineTo(x, y);
            }
            ctx.lineTo(pad.left + pw, pad.top + ph);
            ctx.closePath();
            ctx.fill();

            ctx.strokeStyle = "#ff6600";
            ctx.lineWidth = 2.2;
            ctx.lineJoin = "round";
            ctx.beginPath();
            for (let i = 0; i <= steps; i++) {
                const x = pad.left + (i / steps) * pw;
                const y = pad.top + ph - (values[i] / maxVal) * ph;
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.stroke();

            for (let g = 0; g < aArr.length; g++) {
                const x = pad.left + aArr[g] * pw;
                ctx.strokeStyle = "rgba(255, 102, 0, 0.5)";
                ctx.lineWidth = 1;
                ctx.setLineDash([3, 3]);
                ctx.beginPath();
                ctx.moveTo(x, pad.top);
                ctx.lineTo(x, pad.top + ph);
                ctx.stroke();
                ctx.setLineDash([]);
                ctx.fillStyle = "rgba(255, 102, 0, 0.9)";
                ctx.font = "10px var(--sl-font-mono, monospace)";
                ctx.textAlign = "center";
                ctx.fillText("a=" + aArr[g].toFixed(2), x, pad.top - 4);
            }
        }

        function drawHeatmap() {
            const { ctx, w, h } = heatCvs;
            const mid = w / 2;
            const scale = w / (2 * R * 1.2);

            let maxVal = 0;
            const grid = new Float32Array(w * h);
            for (let y = 0; y < h; y++) {
                for (let x = 0; x < w; x++) {
                    const dx = x - mid;
                    const dy = y - mid;
                    const dist = Math.sqrt(dx * dx + dy * dy);
                    const D = dist / (R * r * scale);
                    const v = kernelProfile(D);
                    grid[y * w + x] = v;
                    if (v > maxVal) maxVal = v;
                }
            }
            if (maxVal === 0) maxVal = 1;

            const imageData = ctx.createImageData(w, h);
            for (let y = 0; y < h; y++) {
                for (let x = 0; x < w; x++) {
                    const t = grid[y * w + x] / maxVal;
                    const c = spectrumColor(t);
                    const idx = (y * w + x) * 4;
                    imageData.data[idx] = c[0];
                    imageData.data[idx + 1] = c[1];
                    imageData.data[idx + 2] = c[2];
                    imageData.data[idx + 3] = 255;
                }
            }
            putPixels(heatCvs, imageData);

            ctx.strokeStyle = "rgba(255, 255, 255, 0.16)";
            ctx.lineWidth = 1;
            const isoLevels = [0.25, 0.5, 0.75];
            for (const lvl of isoLevels) {
                ctx.beginPath();
                for (let theta = 0; theta < Math.PI * 2; theta += 0.04) {
                    let bestR = 0;
                    for (let rr = 0; rr < w / 2; rr += 0.5) {
                        const D = rr / (R * r * scale);
                        const v = kernelProfile(D) / maxVal;
                        if (v >= lvl) bestR = rr;
                    }
                    if (bestR > 0) {
                        const px = mid + Math.cos(theta) * bestR;
                        const py = mid + Math.sin(theta) * bestR;
                        if (theta === 0) ctx.moveTo(px, py);
                        else ctx.lineTo(px, py);
                    }
                }
                ctx.closePath();
                ctx.stroke();
            }

            ctx.fillStyle = "rgba(255, 255, 255, 0.8)";
            ctx.font = "10px var(--sl-font-mono, monospace)";
            ctx.textAlign = "left";
            ctx.fillText("R=" + R + "  r=" + r.toFixed(2), 8, 16);
        }
    }

    // ---------------------------------------------------------------
    // W3: Growth function explorer
    // ---------------------------------------------------------------

    function initGrowth(el) {
        makeHeader(el, "Growth function explorer", "drag along the curve to read G(U)");
        const defaults = parseDefaults(el);
        let m = defaults.m ?? 0.15;
        let s = defaults.s ?? 0.017;
        let h = defaults.h ?? 0.1;
        let uIndicator = m;

        const cvs = initCanvas(440, 280);
        const wrap = makeCanvasWrap("plot");
        wrap.appendChild(cvs.canvas);
        wrap.appendChild(makeCaption("G(U) = (2·exp(-(U-mu)²/(2σ²)) - 1)·h"));

        const sx = 96, sy = 96;
        const previewCvs = document.createElement("canvas");
        previewCvs.width = sx;
        previewCvs.height = sy;
        previewCvs.style.imageRendering = "pixelated";
        const previewWrap = makeCanvasWrap("dark");
        previewWrap.appendChild(previewCvs);
        const previewCard = document.createElement("div");
        previewCard.className = "lenia-creature-card";
        const previewTitle = document.createElement("div");
        previewTitle.className = "lenia-panel-title";
        previewTitle.textContent = "Live preview";
        previewCard.append(previewTitle, previewWrap);

        const controls = document.createElement("div");
        controls.className = "lenia-controls";
        const sM = makeSlider("μ", 0.01, 0.5, 0.001, m, (v) => { m = v; rebuildPreview(); draw(); });
        const sS = makeSlider("σ", 0.005, 0.2, 0.001, s, (v) => { s = v; rebuildPreview(); draw(); });
        const sH = makeSlider("h", 0.01, 1.0, 0.001, h, (v) => { h = v; rebuildPreview(); draw(); });
        controls.append(sM.group, sS.group, sH.group);

        const body = document.createElement("div");
        body.className = "lenia-widget-body sandbox-layout";
        body.append(wrap, previewCard);
        el.append(body, controls);

        const previewCtx = previewCvs.getContext("2d", { alpha: false });
        const previewImg = previewCtx.createImageData(sx, sy);
        const previewLookup = buildSpectrumLookup();
        let previewEngine = null;
        function rebuildPreview() {
            previewEngine = makeCPUEngine({
                sx, sy, R: 11, r: 0.5, b: [1], w: [0.2], a: [0.5],
                mu: m, sigma: s, h, dt: 0.2, seed: 0, patchR: 0.18,
            });
        }
        rebuildPreview();
        function renderPreview() {
            renderStateToImageData(previewEngine.getState(), sx, sy, previewImg, previewLookup);
            previewCtx.putImageData(previewImg, 0, 0);
        }
        renderPreview();
        let previewLast = 0;
        function previewTick(now) {
            if (now - previewLast > 80) {
                previewEngine.step();
                renderPreview();
                previewLast = now;
            }
            requestAnimationFrame(previewTick);
        }
        requestAnimationFrame(previewTick);

        let dragging = false;
        const pad = { left: 48, right: 20, top: 24, bottom: 36 };

        cvs.canvas.addEventListener("mousedown", startDrag);
        cvs.canvas.addEventListener("mousemove", onDrag);
        cvs.canvas.addEventListener("mouseup", () => { dragging = false; });
        cvs.canvas.addEventListener("mouseleave", () => { dragging = false; });
        cvs.canvas.addEventListener("touchstart", (e) => { e.preventDefault(); startDrag(e.touches[0]); }, { passive: false });
        cvs.canvas.addEventListener("touchmove", (e) => { e.preventDefault(); onDrag(e.touches[0]); }, { passive: false });
        cvs.canvas.addEventListener("touchend", () => { dragging = false; });

        function xToU(clientX) {
            const rect = cvs.canvas.getBoundingClientRect();
            const x = clientX - rect.left;
            const visiblePlotW = (cvs.w - pad.left - pad.right) * (rect.width / cvs.w);
            const xInPlot = x - pad.left * (rect.width / cvs.w);
            return Math.max(0, Math.min(1, xInPlot / visiblePlotW));
        }

        function startDrag(e) { dragging = true; uIndicator = xToU(e.clientX); draw(); }
        function onDrag(e) { if (!dragging) return; uIndicator = xToU(e.clientX); draw(); }

        draw();

        function growthFn(U) {
            const diff = (U - m) / s;
            return (2 * Math.exp(-(diff * diff) / 2) - 1) * h;
        }

        function draw() {
            const { ctx, w: cw, h: ch } = cvs;
            ctx.clearRect(0, 0, cw, ch);

            const pw = cw - pad.left - pad.right;
            const ph = ch - pad.top - pad.bottom;
            const midY = pad.top + ph / 2;

            ctx.strokeStyle = "rgba(11, 14, 20, 0.06)";
            ctx.lineWidth = 1;
            for (let i = 1; i < 4; i++) {
                const y = pad.top + (i / 4) * ph;
                ctx.beginPath();
                ctx.moveTo(pad.left, y);
                ctx.lineTo(pad.left + pw, y);
                ctx.stroke();
            }

            ctx.strokeStyle = "rgba(11, 14, 20, 0.4)";
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(pad.left, midY);
            ctx.lineTo(pad.left + pw, midY);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(pad.left, pad.top);
            ctx.lineTo(pad.left, pad.top + ph);
            ctx.stroke();

            ctx.fillStyle = "rgba(11, 14, 20, 0.55)";
            ctx.font = "10px var(--sl-font-mono, monospace)";
            ctx.textAlign = "center";
            ctx.fillText("U=0", pad.left, ch - pad.bottom + 18);
            ctx.fillText("U=1", pad.left + pw, ch - pad.bottom + 18);
            ctx.textAlign = "right";
            ctx.fillText("0", pad.left - 6, midY + 3);
            ctx.fillText("+" + h.toFixed(2), pad.left - 6, pad.top + 10);
            ctx.fillText("-" + h.toFixed(2), pad.left - 6, pad.top + ph + 3);

            const steps = 500;
            const vals = [];
            for (let i = 0; i <= steps; i++) vals.push(growthFn(i / steps));

            ctx.fillStyle = "rgba(63, 132, 88, 0.15)";
            ctx.beginPath();
            ctx.moveTo(pad.left, midY);
            for (let i = 0; i <= steps; i++) {
                const x = pad.left + (i / steps) * pw;
                const v = vals[i];
                if (v >= 0) ctx.lineTo(x, midY - (v / h) * (ph / 2));
                else ctx.lineTo(x, midY);
            }
            ctx.lineTo(pad.left + pw, midY);
            ctx.closePath();
            ctx.fill();

            ctx.fillStyle = "rgba(193, 98, 63, 0.13)";
            ctx.beginPath();
            ctx.moveTo(pad.left, midY);
            for (let i = 0; i <= steps; i++) {
                const x = pad.left + (i / steps) * pw;
                const v = vals[i];
                if (v < 0) ctx.lineTo(x, midY - (v / h) * (ph / 2));
                else ctx.lineTo(x, midY);
            }
            ctx.lineTo(pad.left + pw, midY);
            ctx.closePath();
            ctx.fill();

            ctx.beginPath();
            ctx.strokeStyle = "#ff6600";
            ctx.lineWidth = 2.4;
            ctx.lineJoin = "round";
            for (let i = 0; i <= steps; i++) {
                const x = pad.left + (i / steps) * pw;
                const y = midY - (vals[i] / h) * (ph / 2);
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.stroke();

            const muX = pad.left + m * pw;
            ctx.strokeStyle = "rgba(80, 123, 255, 0.65)";
            ctx.lineWidth = 1;
            ctx.setLineDash([4, 3]);
            ctx.beginPath();
            ctx.moveTo(muX, pad.top);
            ctx.lineTo(muX, pad.top + ph);
            ctx.stroke();
            ctx.setLineDash([]);
            ctx.fillStyle = "rgba(80, 123, 255, 0.95)";
            ctx.font = "10px var(--sl-font-mono, monospace)";
            ctx.textAlign = "center";
            ctx.fillText("μ=" + m.toFixed(3), muX, pad.top - 8);

            const uX = pad.left + uIndicator * pw;
            ctx.beginPath();
            ctx.strokeStyle = "#0b0e14";
            ctx.lineWidth = 1.4;
            ctx.setLineDash([5, 4]);
            ctx.moveTo(uX, pad.top);
            ctx.lineTo(uX, pad.top + ph);
            ctx.stroke();
            ctx.setLineDash([]);

            const gVal = growthFn(uIndicator);
            const dotY = midY - (gVal / h) * (ph / 2);
            ctx.beginPath();
            ctx.fillStyle = gVal >= 0 ? "#3f8458" : "#c1623f";
            ctx.arc(uX, dotY, 5, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = "#fff";
            ctx.lineWidth = 1.5;
            ctx.stroke();

            ctx.fillStyle = "#0b0e14";
            ctx.font = "11px var(--sl-font-mono, monospace)";
            ctx.textAlign = "left";
            const label = "U=" + uIndicator.toFixed(3) + "  G=" + (gVal >= 0 ? "+" : "") + gVal.toFixed(4);
            const textX = Math.min(uX + 10, cw - pad.right - 130);
            const textY = Math.max(dotY - 10, pad.top + 14);
            ctx.fillStyle = "rgba(255, 255, 255, 0.92)";
            ctx.fillRect(textX - 4, textY - 12, 130, 16);
            ctx.fillStyle = "#0b0e14";
            ctx.fillText(label, textX, textY);
        }
    }

    // ---------------------------------------------------------------
    // W4: Mass conservation (basic Lenia vs Flow Lenia)
    // ---------------------------------------------------------------

    function initMassConservation(el) {
        makeHeader(el, "Mass: lost vs conserved", "same seed, same K and G, different update");

        const sx = 96, sy = 96;
        const opts = {
            sx, sy,
            R: 13, r: 0.5, b: [1], w: [0.2], a: [0.5],
            mu: 0.15, sigma: 0.017, h: 0.1, dt: 0.2,
            seed: 3, patchR: 0.18,
        };

        const engineA = makeCPUEngine(opts);
        const engineB = makeCPUEngine(opts);

        const cvsA = document.createElement("canvas");
        cvsA.width = sx; cvsA.height = sy; cvsA.style.imageRendering = "pixelated";
        const cvsB = document.createElement("canvas");
        cvsB.width = sx; cvsB.height = sy; cvsB.style.imageRendering = "pixelated";

        const cardA = document.createElement("div");
        cardA.className = "lenia-creature-card";
        const titleA = document.createElement("div");
        titleA.className = "lenia-panel-title";
        titleA.textContent = "Basic Lenia";
        const wrapA = makeCanvasWrap("dark");
        wrapA.appendChild(cvsA);
        const massPlotA = document.createElement("div");
        massPlotA.className = "lenia-mass-plot-wrap";
        const plotCanvasA = document.createElement("canvas");
        plotCanvasA.width = 360; plotCanvasA.height = 60;
        massPlotA.appendChild(plotCanvasA);
        cardA.append(titleA, wrapA, massPlotA);

        const cardB = document.createElement("div");
        cardB.className = "lenia-creature-card";
        const titleB = document.createElement("div");
        titleB.className = "lenia-panel-title";
        titleB.textContent = "Flow Lenia (mass-preserving)";
        const wrapB = makeCanvasWrap("dark");
        wrapB.appendChild(cvsB);
        const massPlotB = document.createElement("div");
        massPlotB.className = "lenia-mass-plot-wrap";
        const plotCanvasB = document.createElement("canvas");
        plotCanvasB.width = 360; plotCanvasB.height = 60;
        massPlotB.appendChild(plotCanvasB);
        cardB.append(titleB, wrapB, massPlotB);

        const body = document.createElement("div");
        body.className = "lenia-widget-body dual-panel";
        body.append(cardA, cardB);
        el.appendChild(body);

        const controls = document.createElement("div");
        controls.className = "lenia-controls";
        let playing = !reducedMotion;
        const playBtn = makeBtn(playing ? "Pause" : "Play", () => { playing = !playing; playBtn.textContent = playing ? "Pause" : "Play"; });
        const resetBtn = makeBtn("Reset", () => {
            engineA.reset(); engineB.reset();
            massHistA.length = 0; massHistB.length = 0;
            initialMassA = engineA.mass(); initialMassB = engineB.mass();
            renderAll();
        });
        controls.append(playBtn, resetBtn);

        const legend = makeLegend([
            { label: "Basic", color: "#c1623f" },
            { label: "Flow (rescaled)", color: "#3f8458" },
            { label: "initial mass reference", color: "rgba(11,14,20,0.35)" },
        ]);
        controls.append(legend);
        el.appendChild(controls);

        const ctxA = cvsA.getContext("2d");
        const ctxB = cvsB.getContext("2d");
        const lookup = buildSpectrumLookup();
        const imgA = ctxA.createImageData(sx, sy);
        const imgB = ctxB.createImageData(sx, sy);
        const pctxA = plotCanvasA.getContext("2d");
        const pctxB = plotCanvasB.getContext("2d");

        let initialMassA = engineA.mass();
        let initialMassB = engineB.mass();
        const massHistA = [];
        const massHistB = [];
        const maxHistLen = 240;

        function renderState() {
            renderStateToImageData(engineA.getState(), sx, sy, imgA, lookup);
            ctxA.putImageData(imgA, 0, 0);
            renderStateToImageData(engineB.getState(), sx, sy, imgB, lookup);
            ctxB.putImageData(imgB, 0, 0);
        }

        function renderPlot(ctx, data, refMass, color, cw, ch) {
            ctx.clearRect(0, 0, cw, ch);
            ctx.fillStyle = "rgba(11, 14, 20, 0.02)";
            ctx.fillRect(0, 0, cw, ch);

            const padX = 2, padY = 4;
            const pw = cw - padX * 2;
            const ph = ch - padY * 2;
            let maxV = refMass * 1.3;
            for (const v of data) if (v > maxV) maxV = v;

            ctx.strokeStyle = "rgba(11, 14, 20, 0.3)";
            ctx.setLineDash([3, 3]);
            ctx.lineWidth = 1;
            const refY = padY + ph - (refMass / maxV) * ph;
            ctx.beginPath();
            ctx.moveTo(padX, refY);
            ctx.lineTo(padX + pw, refY);
            ctx.stroke();
            ctx.setLineDash([]);

            ctx.strokeStyle = color;
            ctx.lineWidth = 1.8;
            ctx.beginPath();
            for (let i = 0; i < data.length; i++) {
                const x = padX + (i / Math.max(1, maxHistLen - 1)) * pw;
                const y = padY + ph - (data[i] / maxV) * ph;
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.stroke();

            ctx.fillStyle = "rgba(11, 14, 20, 0.55)";
            ctx.font = "9px var(--sl-font-mono, monospace)";
            ctx.textAlign = "right";
            const last = data[data.length - 1];
            if (last !== undefined) {
                const pct = ((last / refMass - 1) * 100);
                const sign = pct >= 0 ? "+" : "";
                ctx.fillText("mass " + sign + pct.toFixed(1) + "%", cw - 4, 11);
            } else {
                ctx.fillText("mass —", cw - 4, 11);
            }
        }

        function renderAll() {
            renderState();
            renderPlot(pctxA, massHistA, initialMassA, "#c1623f", plotCanvasA.width, plotCanvasA.height);
            renderPlot(pctxB, massHistB, initialMassB, "#3f8458", plotCanvasB.width, plotCanvasB.height);
        }

        renderAll();

        let lastFrame = 0;
        function tick(now) {
            if (playing && now - lastFrame > 60) {
                engineA.step(false);
                engineB.step(true);
                massHistA.push(engineA.mass());
                massHistB.push(engineB.mass());
                if (massHistA.length > maxHistLen) massHistA.shift();
                if (massHistB.length > maxHistLen) massHistB.shift();
                renderAll();
                lastFrame = now;
            }
            requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
    }

    // ---------------------------------------------------------------
    // W5: Search strategy comparison
    // ---------------------------------------------------------------

    function initSearch(el) {
        makeHeader(el, "Search strategy comparison", "200-step fitness budget on the same multimodal landscape");
        const maxSteps = parseInt(el.dataset.steps) || 200;
        const autoPlay = el.dataset.autoPlay !== "false";

        const panelW = 240;
        const panelH = 240;

        function landscape(x, y) {
            const d1 = Math.sqrt((x - 0.3) ** 2 + (y - 0.7) ** 2);
            const d2 = Math.sqrt((x - 0.75) ** 2 + (y - 0.25) ** 2);
            const p1 = 0.7 * Math.exp(-(d1 * d1) / 0.02);
            const p2 = 1.0 * Math.exp(-(d2 * d2) / 0.012);
            const ripple = 0.15 * Math.sin(x * 12) * Math.sin(y * 12);
            return Math.max(0, Math.min(1, p1 + p2 + ripple));
        }

        function makePanel(title, color) {
            const card = document.createElement("div");
            card.className = "lenia-strategy-card";
            const t = document.createElement("div");
            t.className = "lenia-panel-title";
            t.textContent = title;
            const { canvas, ctx, w, h } = initCanvas(panelW, panelH);
            const wrap = makeCanvasWrap("dark");
            wrap.appendChild(canvas);
            const caption = makeCaption("0 / " + maxSteps);
            wrap.appendChild(caption);
            const captionRow = document.createElement("div");
            captionRow.className = "lenia-canvas-caption-row";
            const lhs = document.createElement("span");
            lhs.textContent = "best";
            const rhs = document.createElement("span");
            rhs.className = "accent";
            rhs.textContent = "0.000";
            captionRow.append(lhs, rhs);
            const sparkWrap = document.createElement("div");
            sparkWrap.className = "lenia-mass-plot-wrap";
            const sparkCvs = document.createElement("canvas");
            sparkCvs.width = panelW; sparkCvs.height = 40;
            sparkWrap.appendChild(sparkCvs);
            card.append(t, wrap, captionRow, sparkWrap);
            return { canvas, ctx, w, h, card, captionRow, caption, bestVal: rhs, sparkCtx: sparkCvs.getContext("2d"), sparkW: panelW, sparkH: 40, color };
        }

        const pRandom = makePanel("Random search", "#ffcc45");
        const pES = makePanel("ES (gradient)", "#7cf5ff");
        const pME = makePanel("MAP-Elites", "#ff6600");

        const body = document.createElement("div");
        body.className = "lenia-widget-body triple-panel";
        body.append(pRandom.card, pES.card, pME.card);

        const controls = document.createElement("div");
        controls.className = "lenia-controls";
        let step = 0;
        let playing = autoPlay && !reducedMotion;

        const stepSlider = makeSlider("step", 0, maxSteps, 1, 0, (v) => {
            step = Math.round(v);
            drawAll();
        }, (v) => String(Math.round(v)));
        const playBtn = makeBtn(playing ? "Pause" : "Play", () => {
            playing = !playing;
            playBtn.textContent = playing ? "Pause" : "Play";
        });
        const resetBtn = makeBtn("Reset", () => {
            step = 0;
            stepSlider.input.value = "0";
            stepSlider.readout.textContent = "0";
            initTraces();
            drawAll();
        });
        controls.append(stepSlider.group, playBtn, resetBtn);
        el.append(body, controls);

        let randomTrace, esTrace, meGrid;

        function initTraces() {
            const rng = splitmix32(42);
            randomTrace = [];
            for (let i = 0; i < maxSteps; i++) {
                const p = { x: rng(), y: rng() };
                p.f = landscape(p.x, p.y);
                randomTrace.push(p);
            }

            const esRng = splitmix32(77);
            esTrace = [{ x: 0.5 + (esRng() - 0.5) * 0.3, y: 0.5 + (esRng() - 0.5) * 0.3 }];
            esTrace[0].f = landscape(esTrace[0].x, esTrace[0].y);
            for (let i = 1; i < maxSteps; i++) {
                const prev = esTrace[i - 1];
                let bestX = prev.x, bestY = prev.y, bestF = prev.f;
                const sigma = 0.05 * (1 - i / maxSteps);
                for (let t = 0; t < 8; t++) {
                    const nx = Math.max(0, Math.min(1, prev.x + (esRng() - 0.5) * sigma * 2));
                    const ny = Math.max(0, Math.min(1, prev.y + (esRng() - 0.5) * sigma * 2));
                    const nf = landscape(nx, ny);
                    if (nf > bestF) { bestX = nx; bestY = ny; bestF = nf; }
                }
                esTrace.push({ x: bestX, y: bestY, f: bestF });
            }

            const gridN = 8;
            meGrid = Array.from({ length: gridN * gridN }, () => null);
            const meRng = splitmix32(99);
            for (let i = 0; i < maxSteps; i++) {
                const cx = meRng();
                const cy = meRng();
                const cf = landscape(cx, cy);
                const gx = Math.min(gridN - 1, Math.floor(cx * gridN));
                const gy = Math.min(gridN - 1, Math.floor(cy * gridN));
                const idx = gy * gridN + gx;
                if (meGrid[idx] === null || cf > meGrid[idx].f) {
                    meGrid[idx] = { x: cx, y: cy, f: cf, step: i };
                }
            }
        }

        initTraces();

        function drawBackground(panel) {
            const imgData = panel.ctx.createImageData(panel.w, panel.h);
            for (let y = 0; y < panel.h; y++) {
                for (let x = 0; x < panel.w; x++) {
                    const f = landscape(x / panel.w, y / panel.h);
                    const idx = (y * panel.w + x) * 4;
                    const c = spectrumColor(f * 0.6);
                    imgData.data[idx] = Math.round(c[0] * 0.7 + 25);
                    imgData.data[idx + 1] = Math.round(c[1] * 0.7 + 30);
                    imgData.data[idx + 2] = Math.round(c[2] * 0.7 + 38);
                    imgData.data[idx + 3] = 255;
                }
            }
            const tmp = document.createElement("canvas");
            tmp.width = panel.w; tmp.height = panel.h;
            tmp.getContext("2d").putImageData(imgData, 0, 0);
            panel.ctx.imageSmoothingEnabled = false;
            panel.ctx.drawImage(tmp, 0, 0);
            panel.ctx.imageSmoothingEnabled = true;
        }

        function drawSpark(panel, bestOverTime) {
            const ctx = panel.sparkCtx;
            const sw = panel.sparkW, sh = panel.sparkH;
            ctx.clearRect(0, 0, sw, sh);
            ctx.fillStyle = "rgba(11, 14, 20, 0.02)";
            ctx.fillRect(0, 0, sw, sh);
            const padX = 4, padY = 6;
            const pw = sw - padX * 2;
            const ph = sh - padY * 2;
            ctx.strokeStyle = "rgba(11, 14, 20, 0.18)";
            ctx.setLineDash([2, 3]);
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(padX, padY + ph * 0.5);
            ctx.lineTo(padX + pw, padY + ph * 0.5);
            ctx.stroke();
            ctx.setLineDash([]);
            if (bestOverTime.length === 0) return;
            ctx.fillStyle = panel.color + "33";
            ctx.beginPath();
            ctx.moveTo(padX, padY + ph);
            for (let i = 0; i < bestOverTime.length; i++) {
                const x = padX + (i / Math.max(1, maxSteps - 1)) * pw;
                const y = padY + ph - bestOverTime[i] * ph;
                ctx.lineTo(x, y);
            }
            ctx.lineTo(padX + (bestOverTime.length - 1) / Math.max(1, maxSteps - 1) * pw, padY + ph);
            ctx.closePath();
            ctx.fill();
            ctx.strokeStyle = panel.color;
            ctx.lineWidth = 1.6;
            ctx.beginPath();
            for (let i = 0; i < bestOverTime.length; i++) {
                const x = padX + (i / Math.max(1, maxSteps - 1)) * pw;
                const y = padY + ph - bestOverTime[i] * ph;
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.stroke();
        }

        function drawAll() {
            drawBackground(pRandom);
            drawBackground(pES);
            drawBackground(pME);

            let rBest = 0;
            const rSpark = [];
            for (let i = 0; i < step && i < randomTrace.length; i++) {
                const p = randomTrace[i];
                const t = (i + 1) / maxSteps;
                pRandom.ctx.fillStyle = `rgba(255, 204, 69, ${0.35 + 0.55 * t})`;
                pRandom.ctx.beginPath();
                pRandom.ctx.arc(p.x * panelW, p.y * panelH, 2.5, 0, Math.PI * 2);
                pRandom.ctx.fill();
                if (p.f > rBest) rBest = p.f;
                rSpark.push(rBest);
            }
            pRandom.caption.textContent = step + " / " + maxSteps;
            pRandom.bestVal.textContent = rBest.toFixed(3);
            drawSpark(pRandom, rSpark);

            pES.ctx.strokeStyle = "rgba(124, 245, 255, 0.7)";
            pES.ctx.lineWidth = 1.5;
            pES.ctx.beginPath();
            const eSpark = [];
            let eBest = 0;
            for (let i = 0; i < step && i < esTrace.length; i++) {
                const p = esTrace[i];
                if (i === 0) pES.ctx.moveTo(p.x * panelW, p.y * panelH);
                else pES.ctx.lineTo(p.x * panelW, p.y * panelH);
                if (p.f > eBest) eBest = p.f;
                eSpark.push(eBest);
            }
            pES.ctx.stroke();
            if (step > 0 && step <= esTrace.length) {
                const last = esTrace[Math.min(step - 1, esTrace.length - 1)];
                pES.ctx.fillStyle = "#ff6600";
                pES.ctx.beginPath();
                pES.ctx.arc(last.x * panelW, last.y * panelH, 5, 0, Math.PI * 2);
                pES.ctx.fill();
                pES.ctx.strokeStyle = "rgba(255,255,255,0.85)";
                pES.ctx.lineWidth = 1.5;
                pES.ctx.stroke();
                pES.bestVal.textContent = last.f.toFixed(3);
            } else {
                pES.bestVal.textContent = "0.000";
            }
            pES.caption.textContent = step + " / " + maxSteps;
            drawSpark(pES, eSpark);

            const gridN = 8;
            const cellW = panelW / gridN;
            const cellH = panelH / gridN;
            let coverage = 0;
            let meBest = 0;
            for (let i = 0; i < meGrid.length; i++) {
                const cell = meGrid[i];
                if (cell && cell.step < step) {
                    coverage++;
                    if (cell.f > meBest) meBest = cell.f;
                    const gx = i % gridN;
                    const gy = Math.floor(i / gridN);
                    const c = spectrumColor(0.25 + cell.f * 0.7);
                    pME.ctx.fillStyle = `rgba(${c[0]}, ${c[1]}, ${c[2]}, 0.82)`;
                    pME.ctx.fillRect(gx * cellW + 1, gy * cellH + 1, cellW - 2, cellH - 2);
                }
            }
            pME.ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
            pME.ctx.lineWidth = 0.5;
            for (let i = 1; i < gridN; i++) {
                pME.ctx.beginPath();
                pME.ctx.moveTo(i * cellW, 0);
                pME.ctx.lineTo(i * cellW, panelH);
                pME.ctx.stroke();
                pME.ctx.beginPath();
                pME.ctx.moveTo(0, i * cellH);
                pME.ctx.lineTo(panelW, i * cellH);
                pME.ctx.stroke();
            }
            pME.caption.textContent = coverage + " / " + (gridN * gridN) + " niches";
            pME.bestVal.textContent = meBest.toFixed(3);

            const mSpark = [];
            let runningMax = 0;
            const sortedByStep = meGrid.filter((c) => c !== null).sort((a, b) => a.step - b.step);
            let cur = 0;
            for (let i = 0; i < step; i++) {
                while (cur < sortedByStep.length && sortedByStep[cur].step <= i) {
                    if (sortedByStep[cur].f > runningMax) runningMax = sortedByStep[cur].f;
                    cur++;
                }
                mSpark.push(runningMax);
            }
            drawSpark(pME, mSpark);
        }

        drawAll();

        if (!reducedMotion) {
            function autoStep() {
                if (playing && step < maxSteps) {
                    step++;
                    stepSlider.input.value = String(step);
                    stepSlider.readout.textContent = String(step);
                    drawAll();
                }
                requestAnimationFrame(autoStep);
            }
            requestAnimationFrame(autoStep);
        }
    }

    // ---------------------------------------------------------------
    // W6: CVT builder
    // ---------------------------------------------------------------

    function initCVT(el) {
        makeHeader(el, "Centroidal Voronoi tessellation", "Lloyd's algorithm partitioning descriptor space");
        const nCentroids = parseInt(el.dataset.centroids) || 64;
        const cvs = initCanvas(480, 480);
        const wrap = makeCanvasWrap("plot");
        wrap.appendChild(cvs.canvas);
        wrap.appendChild(makeCaption("descriptor space (2D)"));

        const controls = document.createElement("div");
        controls.className = "lenia-controls";
        let iteration = 0;
        let playing = false;

        const iterMetric = makeMetric("iteration", "0");
        const stepBtn = makeBtn("Step", () => { lloydStep(); draw(); });
        const playBtn = makeBtn("Play", () => {
            playing = !playing;
            playBtn.textContent = playing ? "Pause" : "Play";
        });
        const resetBtn = makeBtn("Reset", () => {
            playing = false;
            playBtn.textContent = "Play";
            iteration = 0;
            initCentroids();
            iterMetric.querySelector(".lenia-metric-value").textContent = "0";
            draw();
        });
        controls.append(stepBtn, playBtn, resetBtn, iterMetric);

        const body = document.createElement("div");
        body.className = "lenia-widget-body";
        body.append(wrap);
        el.append(body, controls);

        let centroids;
        let prevCentroids;
        let anim = { progress: 1 };

        function initCentroids() {
            const rng = splitmix32(7);
            centroids = [];
            for (let i = 0; i < nCentroids; i++) centroids.push([rng(), rng()]);
            prevCentroids = centroids.map((c) => c.slice());
            anim.progress = 1;
        }

        function lloydStep() {
            prevCentroids = centroids.map((c) => c.slice());
            const sums = Array.from({ length: nCentroids }, () => [0, 0, 0]);
            const res = 128;
            for (let y = 0; y < res; y++) {
                for (let x = 0; x < res; x++) {
                    const px = (x + 0.5) / res;
                    const py = (y + 0.5) / res;
                    let minD = Infinity, minK = 0;
                    for (let k = 0; k < nCentroids; k++) {
                        const dx = px - centroids[k][0];
                        const dy = py - centroids[k][1];
                        const d = dx * dx + dy * dy;
                        if (d < minD) { minD = d; minK = k; }
                    }
                    sums[minK][0] += px;
                    sums[minK][1] += py;
                    sums[minK][2]++;
                }
            }
            for (let k = 0; k < nCentroids; k++) {
                if (sums[k][2] > 0) {
                    centroids[k][0] = sums[k][0] / sums[k][2];
                    centroids[k][1] = sums[k][1] / sums[k][2];
                }
            }
            iteration++;
            iterMetric.querySelector(".lenia-metric-value").textContent = String(iteration);
            anim.progress = 0;
        }

        function lerpCentroid(k) {
            const t = anim.progress;
            return [
                prevCentroids[k][0] + (centroids[k][0] - prevCentroids[k][0]) * t,
                prevCentroids[k][1] + (centroids[k][1] - prevCentroids[k][1]) * t,
            ];
        }

        function draw() {
            const { ctx, w, h } = cvs;
            const imgData = ctx.createImageData(w, h);

            const interp = centroids.map((_, k) => lerpCentroid(k));
            const colors = interp.map((_, i) => spectrumColor(0.15 + ((i * 37) % nCentroids) / nCentroids * 0.7));

            for (let y = 0; y < h; y++) {
                for (let x = 0; x < w; x++) {
                    const px = (x + 0.5) / w;
                    const py = (y + 0.5) / h;
                    let minD = Infinity, minK = 0;
                    for (let k = 0; k < nCentroids; k++) {
                        const dx = px - interp[k][0];
                        const dy = py - interp[k][1];
                        const d = dx * dx + dy * dy;
                        if (d < minD) { minD = d; minK = k; }
                    }
                    const idx = (y * w + x) * 4;
                    const c = colors[minK];
                    imgData.data[idx] = Math.round(c[0] * 0.32 + 200);
                    imgData.data[idx + 1] = Math.round(c[1] * 0.32 + 200);
                    imgData.data[idx + 2] = Math.round(c[2] * 0.32 + 200);
                    imgData.data[idx + 3] = 255;
                }
            }
            putPixels(cvs, imgData);

            ctx.strokeStyle = "rgba(11, 14, 20, 0.06)";
            ctx.lineWidth = 1;
            for (let i = 0; i < interp.length; i++) {
                for (let j = i + 1; j < interp.length; j++) {
                    const dx = interp[i][0] - interp[j][0];
                    const dy = interp[i][1] - interp[j][1];
                    if (dx * dx + dy * dy < 0.025) {
                        ctx.beginPath();
                        ctx.moveTo(interp[i][0] * w, interp[i][1] * h);
                        ctx.lineTo(interp[j][0] * w, interp[j][1] * h);
                        ctx.stroke();
                    }
                }
            }

            for (let k = 0; k < nCentroids; k++) {
                ctx.beginPath();
                ctx.fillStyle = "#0b0e14";
                ctx.arc(interp[k][0] * w, interp[k][1] * h, 3, 0, Math.PI * 2);
                ctx.fill();
            }
        }

        initCentroids();
        draw();

        if (!reducedMotion) {
            let lastStep = 0;
            function tick(now) {
                if (anim.progress < 1) {
                    anim.progress = Math.min(1, anim.progress + 0.05);
                    draw();
                }
                if (playing && anim.progress >= 1 && now - lastStep > 600) {
                    lloydStep();
                    draw();
                    lastStep = now;
                }
                requestAnimationFrame(tick);
            }
            requestAnimationFrame(tick);
        }
    }

    // ---------------------------------------------------------------
    // W7: MAP-Elites step-through
    // ---------------------------------------------------------------

    function initMapElites(el) {
        makeHeader(el, "MAP-Elites step-through", "select, vary, evaluate, place");
        const traceSrc = el.dataset.traceSrc;
        const nCentroids = parseInt(el.dataset.centroids) || 64;

        const gridCvs = initCanvas(380, 380);
        const gridWrap = makeCanvasWrap("plot");
        gridWrap.appendChild(gridCvs.canvas);
        gridWrap.appendChild(makeCaption("descriptor archive"));

        const narration = document.createElement("div");
        narration.className = "lenia-narration";
        narration.textContent = "Loading trace...";

        const body = document.createElement("div");
        body.className = "lenia-widget-body";
        body.append(gridWrap);

        const controls = document.createElement("div");
        controls.className = "lenia-controls";

        const metricsBar = document.createElement("div");
        metricsBar.className = "lenia-metrics-bar";

        el.append(body, narration, controls, metricsBar);

        let trace = null;
        let gen = 0;
        let playing = false;
        let repertoire = [];

        function loadTrace() {
            if (!traceSrc) { useSyntheticTrace(); return; }
            fetch(traceSrc)
                .then((r) => r.json())
                .then((data) => {
                    trace = data;
                    setupControls();
                    drawState();
                })
                .catch(() => useSyntheticTrace());
        }

        function useSyntheticTrace() {
            const rng = splitmix32(42);
            const cents = [];
            for (let i = 0; i < nCentroids; i++) cents.push([rng(), rng()]);
            const gens = [];
            for (let i = 0; i < 80; i++) {
                const parentIdx = Math.floor(rng() * nCentroids);
                const childDesc = [
                    Math.max(0, Math.min(1, cents[parentIdx][0] + (rng() - 0.5) * 0.3)),
                    Math.max(0, Math.min(1, cents[parentIdx][1] + (rng() - 0.5) * 0.3)),
                ];
                let minD = Infinity, landing = 0;
                for (let k = 0; k < nCentroids; k++) {
                    const dx = childDesc[0] - cents[k][0];
                    const dy = childDesc[1] - cents[k][1];
                    const d = dx * dx + dy * dy;
                    if (d < minD) { minD = d; landing = k; }
                }
                const fitness = 0.3 + rng() * 0.7;
                gens.push({
                    parent_idx: parentIdx,
                    child_descriptor: childDesc,
                    child_fitness: fitness,
                    landing_cell: landing,
                    outcome: rng() > 0.4 ? "placed" : "discarded",
                    previous_fitness: rng() > 0.6 ? 0.2 + rng() * 0.5 : null,
                });
            }
            trace = { centroids: cents, generations: gens };
            setupControls();
            drawState();
        }

        function setupControls() {
            const maxGen = trace.generations.length;
            const slider = makeSlider("gen", 0, maxGen, 1, 0, (v) => {
                gen = Math.round(v);
                drawState();
            }, (v) => String(Math.round(v)));
            const playBtn = makeBtn("Play", () => {
                playing = !playing;
                playBtn.textContent = playing ? "Pause" : "Play";
            });
            const resetBtn = makeBtn("Reset", () => {
                gen = 0;
                slider.input.value = "0";
                slider.readout.textContent = "0";
                playing = false;
                playBtn.textContent = "Play";
                drawState();
            });
            controls.replaceChildren();
            controls.append(slider.group, playBtn, resetBtn);

            if (!reducedMotion) {
                let lastTick = 0;
                function tick(now) {
                    if (playing && now - lastTick > 350) {
                        if (gen < maxGen) {
                            gen++;
                            slider.input.value = String(gen);
                            slider.readout.textContent = String(gen);
                            drawState();
                        } else {
                            playing = false;
                            playBtn.textContent = "Play";
                        }
                        lastTick = now;
                    }
                    requestAnimationFrame(tick);
                }
                requestAnimationFrame(tick);
            }
        }

        function drawState() {
            if (!trace) return;
            const { ctx, w, h } = gridCvs;
            ctx.clearRect(0, 0, w, h);

            repertoire = new Array(trace.centroids.length).fill(null);
            for (let i = 0; i < gen && i < trace.generations.length; i++) {
                const ev = trace.generations[i];
                if (ev.outcome === "placed") {
                    repertoire[ev.landing_cell] = ev.child_fitness;
                }
            }

            const imgData = ctx.createImageData(w, h);
            for (let py = 0; py < h; py++) {
                for (let px = 0; px < w; px++) {
                    const nx = (px + 0.5) / w;
                    const ny = (py + 0.5) / h;
                    let minD = Infinity, minK = 0;
                    for (let k = 0; k < trace.centroids.length; k++) {
                        const dx = nx - trace.centroids[k][0];
                        const dy = ny - trace.centroids[k][1];
                        const d = dx * dx + dy * dy;
                        if (d < minD) { minD = d; minK = k; }
                    }
                    const idx = (py * w + px) * 4;
                    if (repertoire[minK] !== null) {
                        const f = repertoire[minK];
                        const c = spectrumColor(0.25 + f * 0.7);
                        imgData.data[idx] = Math.round(c[0] * 0.7 + 50);
                        imgData.data[idx + 1] = Math.round(c[1] * 0.7 + 50);
                        imgData.data[idx + 2] = Math.round(c[2] * 0.7 + 50);
                    } else {
                        imgData.data[idx] = 244;
                        imgData.data[idx + 1] = 245;
                        imgData.data[idx + 2] = 247;
                    }
                    imgData.data[idx + 3] = 255;
                }
            }
            putPixels(gridCvs, imgData);

            for (let k = 0; k < trace.centroids.length; k++) {
                const cx = trace.centroids[k][0] * w;
                const cy = trace.centroids[k][1] * h;
                ctx.fillStyle = repertoire[k] !== null ? "#0b0e14" : "rgba(11,14,20,0.18)";
                ctx.beginPath();
                ctx.arc(cx, cy, 2, 0, Math.PI * 2);
                ctx.fill();
            }

            if (gen > 0 && gen <= trace.generations.length) {
                const ev = trace.generations[gen - 1];
                const cx = ev.child_descriptor[0] * w;
                const cy = ev.child_descriptor[1] * h;
                ctx.strokeStyle = ev.outcome === "placed" ? "#3f8458" : "#c1623f";
                ctx.lineWidth = 2.5;
                ctx.beginPath();
                ctx.arc(cx, cy, 8, 0, Math.PI * 2);
                ctx.stroke();

                const parentC = trace.centroids[ev.parent_idx];
                ctx.strokeStyle = "rgba(255, 102, 0, 0.7)";
                ctx.lineWidth = 1.5;
                ctx.setLineDash([4, 4]);
                ctx.beginPath();
                ctx.moveTo(parentC[0] * w, parentC[1] * h);
                ctx.lineTo(cx, cy);
                ctx.stroke();
                ctx.setLineDash([]);

                ctx.fillStyle = "#ff6600";
                ctx.beginPath();
                ctx.arc(parentC[0] * w, parentC[1] * h, 3.5, 0, Math.PI * 2);
                ctx.fill();
            }

            let coverage = 0, totalFit = 0, maxFit = 0;
            for (const f of repertoire) {
                if (f !== null) {
                    coverage++;
                    totalFit += f;
                    if (f > maxFit) maxFit = f;
                }
            }

            metricsBar.replaceChildren(
                makeMetric("generation", String(gen)),
                makeMetric("coverage", coverage + " / " + trace.centroids.length),
                makeMetric("QD score", totalFit.toFixed(2), "accent"),
                makeMetric("max fitness", maxFit.toFixed(3))
            );

            if (gen > 0 && gen <= trace.generations.length) {
                const ev = trace.generations[gen - 1];
                if (ev.outcome === "placed") {
                    narration.textContent = ev.previous_fitness !== null
                        ? "Child placed in cell " + ev.landing_cell +
                          " (fitness " + ev.child_fitness.toFixed(3) +
                          " > incumbent " + ev.previous_fitness.toFixed(3) + ")"
                        : "Child placed in empty cell " + ev.landing_cell +
                          " (fitness " + ev.child_fitness.toFixed(3) + ")";
                } else {
                    narration.textContent =
                        "Child discarded from cell " + ev.landing_cell +
                        " (fitness " + ev.child_fitness.toFixed(3) +
                        " did not beat incumbent)";
                }
            } else {
                narration.textContent = gen === 0
                    ? "Press Play to walk through the MAP-Elites loop generation by generation."
                    : "Repertoire complete.";
            }
        }

        loadTrace();
    }

    // ---------------------------------------------------------------
    // W8: Isoline variation
    // ---------------------------------------------------------------

    function initIsoline(el) {
        makeHeader(el, "Isoline variation", "drag A and B to set the line; samples redraw live");
        let isoSigma = parseFloat(el.dataset.isoSigma) || 0.03;
        let lineSigma = parseFloat(el.dataset.lineSigma) || 0.12;

        const cvs = initCanvas(460, 460);
        const wrap = makeCanvasWrap("plot");
        wrap.appendChild(cvs.canvas);
        wrap.appendChild(makeCaption("descriptor space"));

        const controls = document.createElement("div");
        controls.className = "lenia-controls";
        const sIso = makeSlider("iso σ", 0.001, 0.08, 0.001, isoSigma, (v) => {
            isoSigma = v;
            draw();
        });
        const sLine = makeSlider("line σ", 0.005, 0.25, 0.005, lineSigma, (v) => {
            lineSigma = v;
            draw();
        });
        controls.append(sIso.group, sLine.group);

        const legend = makeLegend([
            { label: "isotropic", color: "rgba(80, 123, 255, 0.7)" },
            { label: "directional", color: "rgba(255, 113, 56, 0.7)" },
            { label: "combined", color: "rgba(63, 132, 88, 0.85)" },
        ]);
        controls.append(legend);

        const body = document.createElement("div");
        body.className = "lenia-widget-body";
        body.append(wrap);
        el.append(body, controls);

        let pointA = [0.3, 0.5];
        let pointB = [0.7, 0.5];
        let draggingPoint = null;

        cvs.canvas.addEventListener("mousedown", (e) => {
            const p = canvasCoord(e);
            if (dist(p, pointA) < 0.04) draggingPoint = "A";
            else if (dist(p, pointB) < 0.04) draggingPoint = "B";
        });
        cvs.canvas.addEventListener("mousemove", (e) => {
            if (!draggingPoint) return;
            const p = canvasCoord(e);
            if (draggingPoint === "A") pointA = [clamp01(p[0]), clamp01(p[1])];
            else pointB = [clamp01(p[0]), clamp01(p[1])];
            draw();
        });
        cvs.canvas.addEventListener("mouseup", () => { draggingPoint = null; });
        cvs.canvas.addEventListener("mouseleave", () => { draggingPoint = null; });

        cvs.canvas.addEventListener("touchstart", (e) => {
            e.preventDefault();
            const p = canvasCoord(e.touches[0]);
            if (dist(p, pointA) < 0.06) draggingPoint = "A";
            else if (dist(p, pointB) < 0.06) draggingPoint = "B";
        }, { passive: false });
        cvs.canvas.addEventListener("touchmove", (e) => {
            e.preventDefault();
            if (!draggingPoint) return;
            const p = canvasCoord(e.touches[0]);
            if (draggingPoint === "A") pointA = [clamp01(p[0]), clamp01(p[1])];
            else pointB = [clamp01(p[0]), clamp01(p[1])];
            draw();
        }, { passive: false });
        cvs.canvas.addEventListener("touchend", () => { draggingPoint = null; });

        function canvasCoord(e) {
            const rect = cvs.canvas.getBoundingClientRect();
            return [(e.clientX - rect.left) / rect.width, (e.clientY - rect.top) / rect.height];
        }

        function dist(a, b) {
            return Math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2);
        }

        function clamp01(v) { return Math.max(0, Math.min(1, v)); }

        function gaussRandom(rng) {
            const u1 = rng();
            const u2 = rng();
            return Math.sqrt(-2 * Math.log(u1 + 1e-10)) * Math.cos(2 * Math.PI * u2);
        }

        function draw() {
            const { ctx, w, h } = cvs;
            ctx.clearRect(0, 0, w, h);

            const grad = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w * 0.7);
            grad.addColorStop(0, "rgba(255, 102, 0, 0.04)");
            grad.addColorStop(1, "rgba(11, 14, 20, 0.02)");
            ctx.fillStyle = grad;
            ctx.fillRect(0, 0, w, h);

            ctx.strokeStyle = "rgba(11, 14, 20, 0.04)";
            ctx.lineWidth = 1;
            const gridStep = w / 10;
            for (let i = 1; i < 10; i++) {
                ctx.beginPath();
                ctx.moveTo(i * gridStep, 0); ctx.lineTo(i * gridStep, h); ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(0, i * gridStep); ctx.lineTo(w, i * gridStep); ctx.stroke();
            }

            const ax = pointA[0] * w, ay = pointA[1] * h;
            const bx = pointB[0] * w, by = pointB[1] * h;

            const dx = pointB[0] - pointA[0];
            const dy = pointB[1] - pointA[1];
            const len = Math.sqrt(dx * dx + dy * dy) || 1e-6;
            const dirX = dx / len, dirY = dy / len;

            const nSamples = 100;

            const rng = splitmix32(123);
            ctx.fillStyle = "rgba(80, 123, 255, 0.35)";
            for (let i = 0; i < nSamples; i++) {
                const isoX = gaussRandom(rng) * isoSigma;
                const isoY = gaussRandom(rng) * isoSigma;
                ctx.beginPath();
                ctx.arc((pointA[0] + isoX) * w, (pointA[1] + isoY) * h, 2.5, 0, Math.PI * 2);
                ctx.fill();
            }

            const rng2 = splitmix32(456);
            ctx.fillStyle = "rgba(255, 113, 56, 0.35)";
            for (let i = 0; i < nSamples; i++) {
                const lineT = gaussRandom(rng2) * lineSigma;
                ctx.beginPath();
                ctx.arc((pointA[0] + dirX * lineT) * w, (pointA[1] + dirY * lineT) * h, 2.5, 0, Math.PI * 2);
                ctx.fill();
            }

            const rng3 = splitmix32(789);
            ctx.fillStyle = "rgba(63, 132, 88, 0.6)";
            for (let i = 0; i < nSamples; i++) {
                const isoX = gaussRandom(rng3) * isoSigma;
                const isoY = gaussRandom(rng3) * isoSigma;
                const lineT = gaussRandom(rng3) * lineSigma;
                ctx.beginPath();
                ctx.arc((pointA[0] + isoX + dirX * lineT) * w, (pointA[1] + isoY + dirY * lineT) * h, 3, 0, Math.PI * 2);
                ctx.fill();
            }

            ctx.setLineDash([6, 4]);
            ctx.strokeStyle = "rgba(11, 14, 20, 0.35)";
            ctx.lineWidth = 1.2;
            ctx.beginPath();
            ctx.moveTo(ax, ay);
            ctx.lineTo(bx, by);
            ctx.stroke();
            ctx.setLineDash([]);

            ctx.fillStyle = "#0b0e14";
            ctx.strokeStyle = "#fff";
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.arc(ax, ay, 9, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
            ctx.fillStyle = "#fff";
            ctx.font = "bold 11px var(--sl-font-mono, monospace)";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText("A", ax, ay);

            ctx.fillStyle = "#ff6600";
            ctx.strokeStyle = "#fff";
            ctx.beginPath();
            ctx.arc(bx, by, 9, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
            ctx.fillStyle = "#fff";
            ctx.fillText("B", bx, by);
        }

        draw();
    }
})();
