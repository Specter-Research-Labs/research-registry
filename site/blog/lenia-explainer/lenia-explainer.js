(() => {
    "use strict";

    const content = document.querySelector(".doc-content");
    if (!content) return;

    const WIDGET_INIT = {
        sandbox: initSandbox,
        kernel: initKernel,
        growth: initGrowth,
        search: initSearch,
        cvt: initCVT,
        mapelites: initMapElites,
        isoline: initIsoline,
    };

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

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

    // -- helpers --

    function makeHeader(el, title) {
        const header = document.createElement("div");
        header.className = "lenia-widget-header";
        const titleEl = document.createElement("div");
        titleEl.className = "lenia-widget-title";
        titleEl.textContent = title;
        header.appendChild(titleEl);
        el.prepend(header);
        return header;
    }

    function makeSlider(label, min, max, step, value, onChange) {
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
        readout.textContent = Number(value).toFixed(3);
        input.addEventListener("input", () => {
            const v = Number(input.value);
            readout.textContent = v.toFixed(3);
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
        cvs.ctx.drawImage(tmp, 0, 0);
    }

    function makeMetric(label, value) {
        const m = document.createElement("div");
        m.className = "lenia-metric";
        const lbl = document.createElement("span");
        lbl.className = "lenia-metric-label";
        lbl.textContent = label;
        const val = document.createElement("span");
        val.className = "lenia-metric-value";
        val.textContent = value;
        m.append(lbl, val);
        return m;
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

    // -- W1: Live Lenia Sandbox --

    function initSandbox(el) {
        makeHeader(el, "Live Lenia simulation");

        const creatureName = el.dataset.creature || "orbium";
        const wrap = document.createElement("div");
        wrap.className = "lenia-canvas-wrap";
        const canvas = document.createElement("canvas");
        canvas.width = 128;
        canvas.height = 128;
        canvas.style.width = "100%";
        canvas.style.height = "auto";
        canvas.style.imageRendering = "pixelated";
        wrap.appendChild(canvas);

        const controls = document.createElement("div");
        controls.className = "lenia-controls";
        const playingRef = { value: !reducedMotion };
        const playBtn = makeBtn(playingRef.value ? "Pause" : "Play", () => {
            playingRef.value = !playingRef.value;
            playBtn.textContent = playingRef.value ? "Pause" : "Play";
        });
        const resetBtn = makeBtn("Reset", () => {
            if (engine) engine.reset();
        });
        controls.append(playBtn, resetBtn);

        const body = document.createElement("div");
        body.className = "lenia-widget-body";
        body.append(wrap, controls);
        el.appendChild(body);

        let engine = null;

        if (typeof LeniaGPU !== "undefined" && navigator.gpu) {
            LeniaGPU.load(creatureName, canvas).then((e) => {
                if (e) {
                    engine = e;
                    if (!reducedMotion) gpuTick();
                } else {
                    engine = loadReplayFallback(canvas, creatureName, playingRef);
                }
            }).catch(() => {
                engine = loadReplayFallback(canvas, creatureName, playingRef);
            });
        } else {
            engine = loadReplayFallback(canvas, creatureName, playingRef);
        }

        function gpuTick() {
            if (!engine || !engine.step) return;
            if (playingRef.value) {
                engine.step();
                engine.render();
            }
            requestAnimationFrame(gpuTick);
        }
    }

    const LENIA_SPECTRUM = [
        [5, 4, 10], [124, 245, 255], [80, 123, 255],
        [191, 55, 255], [255, 58, 175], [255, 113, 56], [255, 204, 69],
    ];

    function buildSpectrumLookup() {
        const lookup = new Uint8ClampedArray(256 * 4);
        for (let v = 0; v < 256; v++) {
            const norm = v / 255;
            const corrected = Math.pow(norm, 0.88);
            const scaled = corrected * (LENIA_SPECTRUM.length - 1);
            const lo = Math.floor(scaled);
            const hi = Math.min(lo + 1, LENIA_SPECTRUM.length - 1);
            const t = scaled - lo;
            const base = v * 4;
            lookup[base] = Math.round(LENIA_SPECTRUM[lo][0] + (LENIA_SPECTRUM[hi][0] - LENIA_SPECTRUM[lo][0]) * t);
            lookup[base + 1] = Math.round(LENIA_SPECTRUM[lo][1] + (LENIA_SPECTRUM[hi][1] - LENIA_SPECTRUM[lo][1]) * t);
            lookup[base + 2] = Math.round(LENIA_SPECTRUM[lo][2] + (LENIA_SPECTRUM[hi][2] - LENIA_SPECTRUM[lo][2]) * t);
            lookup[base + 3] = 255;
        }
        return lookup;
    }

    function loadReplayFallback(canvas, creature, playingRef) {
        const ctx = canvas.getContext("2d", { alpha: false });
        if (!ctx) return null;

        const sx = 128, sy = 128;
        canvas.width = sx;
        canvas.height = sy;

        const R = 13, rK = 0.5;
        const bK = [1.0], wK = [0.2], aK = [0.5];
        const mu = 0.15, sigma = 0.017, h = 0.1, dt = 0.2;
        const kernelRadius = Math.ceil(R * rK);

        const kernel = new Float32Array((2 * kernelRadius + 1) * (2 * kernelRadius + 1));
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
                const idx = (ky + kernelRadius) * (2 * kernelRadius + 1) + (kx + kernelRadius);
                kernel[idx] = val;
                kernelSum += val;
            }
        }
        if (kernelSum > 0) {
            for (let i = 0; i < kernel.length; i++) kernel[i] /= kernelSum;
        }

        let state = new Float32Array(sx * sy);
        const rng = splitmix32(0);
        const patchR = 0.16 * sx;
        const patchR2 = patchR * patchR;
        const cx = sx / 2, cy = sy / 2;
        for (let y = 0; y < sy; y++) {
            for (let x = 0; x < sx; x++) {
                const dx = x - cx, dy = y - cy;
                if (dx * dx + dy * dy <= patchR2) {
                    state[y * sx + x] = rng();
                }
            }
        }

        const lookup = buildSpectrumLookup();
        const imageData = ctx.createImageData(sx, sy);
        const kSize = 2 * kernelRadius + 1;

        function stepCPU() {
            const next = new Float32Array(sx * sy);
            for (let y = 0; y < sy; y++) {
                for (let x = 0; x < sx; x++) {
                    let U = 0;
                    for (let ky = -kernelRadius; ky <= kernelRadius; ky++) {
                        for (let kx = -kernelRadius; kx <= kernelRadius; kx++) {
                            const kIdx = (ky + kernelRadius) * kSize + (kx + kernelRadius);
                            const w = kernel[kIdx];
                            if (w < 1e-10) continue;
                            const nx = ((x + kx) % sx + sx) % sx;
                            const ny = ((y + ky) % sy + sy) % sy;
                            U += state[ny * sx + nx] * w;
                        }
                    }
                    const diff = (U - mu) / sigma;
                    const G = (2 * Math.exp(-(diff * diff) / 2) - 1) * h;
                    next[y * sx + x] = Math.max(0, Math.min(1, state[y * sx + x] + dt * G));
                }
            }
            state = next;
        }

        function renderFrame() {
            for (let i = 0; i < sx * sy; i++) {
                const byteVal = Math.round(Math.max(0, Math.min(1, state[i])) * 255);
                const src = byteVal * 4;
                const dst = i * 4;
                imageData.data[dst] = lookup[src];
                imageData.data[dst + 1] = lookup[src + 1];
                imageData.data[dst + 2] = lookup[src + 2];
                imageData.data[dst + 3] = 255;
            }
            ctx.putImageData(imageData, 0, 0);
        }

        renderFrame();

        let lastFrame = 0;
        function tick(now) {
            if (playingRef.value && now - lastFrame > 80) {
                stepCPU();
                renderFrame();
                lastFrame = now;
            }
            requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);

        return {
            reset() {
                state = new Float32Array(sx * sy);
                const rng2 = splitmix32(0);
                for (let y = 0; y < sy; y++) {
                    for (let x = 0; x < sx; x++) {
                        const dx = x - cx, dy = y - cy;
                        if (dx * dx + dy * dy <= patchR2) {
                            state[y * sx + x] = rng2();
                        }
                    }
                }
                renderFrame();
            }
        };
    }

    // -- W2: Kernel Visualizer --

    function initKernel(el) {
        makeHeader(el, "Kernel visualizer");
        const defaults = parseDefaults(el);
        let R = defaults.R ?? 13;
        let r = defaults.r ?? 0.5;
        const bArr = defaults.b ?? [1];
        const wArr = defaults.w ?? [0.2];
        const aArr = defaults.a ?? [0.5];

        const profileCvs = initCanvas(300, 180);
        const heatCvs = initCanvas(200, 200);

        const profileWrap = document.createElement("div");
        profileWrap.className = "lenia-canvas-wrap plot";
        profileWrap.appendChild(profileCvs.canvas);

        const heatWrap = document.createElement("div");
        heatWrap.className = "lenia-canvas-wrap plot";
        heatWrap.appendChild(heatCvs.canvas);

        const body = document.createElement("div");
        body.className = "lenia-widget-body dual-panel";
        body.append(profileWrap, heatWrap);

        const controls = document.createElement("div");
        controls.className = "lenia-controls";
        const sR = makeSlider("R", 4, 30, 1, R, (v) => { R = v; draw(); });
        const sr = makeSlider("r", 0.1, 1.0, 0.01, r, (v) => { r = v; draw(); });
        controls.append(sR.group, sr.group);

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

            const pad = { left: 36, right: 12, top: 12, bottom: 24 };
            const pw = w - pad.left - pad.right;
            const ph = h - pad.top - pad.bottom;

            let maxVal = 0;
            const steps = 200;
            const values = [];
            for (let i = 0; i <= steps; i++) {
                const D = i / steps;
                const v = kernelProfile(D);
                values.push(v);
                if (v > maxVal) maxVal = v;
            }
            if (maxVal === 0) maxVal = 1;

            ctx.strokeStyle = "rgba(11, 14, 20, 0.15)";
            ctx.lineWidth = 0.5;
            ctx.beginPath();
            ctx.moveTo(pad.left, pad.top + ph);
            ctx.lineTo(pad.left + pw, pad.top + ph);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(pad.left, pad.top);
            ctx.lineTo(pad.left, pad.top + ph);
            ctx.stroke();

            ctx.fillStyle = "#657694";
            ctx.font = "10px sans-serif";
            ctx.textAlign = "center";
            ctx.fillText("0", pad.left, pad.top + ph + 14);
            ctx.fillText("1", pad.left + pw, pad.top + ph + 14);
            ctx.textAlign = "right";
            ctx.fillText("0", pad.left - 4, pad.top + ph + 3);
            ctx.fillText(maxVal.toFixed(2), pad.left - 4, pad.top + 10);

            ctx.beginPath();
            ctx.strokeStyle = "#5367bf";
            ctx.lineWidth = 2;
            for (let i = 0; i <= steps; i++) {
                const x = pad.left + (i / steps) * pw;
                const y = pad.top + ph - (values[i] / maxVal) * ph;
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.stroke();

            ctx.fillStyle = "rgba(83, 103, 191, 0.12)";
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
        }

        function drawHeatmap() {
            const { ctx, w, h } = heatCvs;
            const mid = w / 2;
            const scale = w / (2 * R * 1.2);

            let maxVal = 0;
            const grid = [];
            for (let y = 0; y < h; y++) {
                const row = [];
                for (let x = 0; x < w; x++) {
                    const dx = x - mid;
                    const dy = y - mid;
                    const dist = Math.sqrt(dx * dx + dy * dy);
                    const D = dist / (R * r * scale);
                    const v = kernelProfile(D);
                    row.push(v);
                    if (v > maxVal) maxVal = v;
                }
                grid.push(row);
            }
            if (maxVal === 0) maxVal = 1;

            const imageData = ctx.createImageData(w, h);
            for (let y = 0; y < h; y++) {
                for (let x = 0; x < w; x++) {
                    const t = grid[y][x] / maxVal;
                    const idx = (y * w + x) * 4;
                    imageData.data[idx] = Math.round(11 + t * 72);
                    imageData.data[idx + 1] = Math.round(14 + t * 89);
                    imageData.data[idx + 2] = Math.round(20 + t * 171);
                    imageData.data[idx + 3] = 255;
                }
            }
            putPixels(heatCvs, imageData);
        }
    }

    // -- W3: Growth Function Explorer --

    function initGrowth(el) {
        makeHeader(el, "Growth function explorer");
        const defaults = parseDefaults(el);
        let m = defaults.m ?? 0.15;
        let s = defaults.s ?? 0.017;
        let h = defaults.h ?? 0.1;
        let uIndicator = m;

        const cvs = initCanvas(500, 220);
        const wrap = document.createElement("div");
        wrap.className = "lenia-canvas-wrap plot";
        wrap.appendChild(cvs.canvas);

        const controls = document.createElement("div");
        controls.className = "lenia-controls";
        const sM = makeSlider("\u03bc", 0.01, 0.5, 0.001, m, (v) => { m = v; draw(); });
        const sS = makeSlider("\u03c3", 0.005, 0.2, 0.001, s, (v) => { s = v; draw(); });
        const sH = makeSlider("h", 0.01, 1.0, 0.001, h, (v) => { h = v; draw(); });
        controls.append(sM.group, sS.group, sH.group);

        const body = document.createElement("div");
        body.className = "lenia-widget-body";
        body.append(wrap, controls);
        el.appendChild(body);

        let dragging = false;
        const pad = { left: 42, right: 16, top: 16, bottom: 24 };

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
            const plotW = cvs.w - pad.left - pad.right;
            return Math.max(0, Math.min(1, (x - pad.left) / plotW));
        }

        function startDrag(e) {
            dragging = true;
            uIndicator = xToU(e.clientX);
            draw();
        }

        function onDrag(e) {
            if (!dragging) return;
            uIndicator = xToU(e.clientX);
            draw();
        }

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

            ctx.strokeStyle = "rgba(11, 14, 20, 0.15)";
            ctx.lineWidth = 0.5;
            ctx.beginPath();
            ctx.moveTo(pad.left, midY);
            ctx.lineTo(pad.left + pw, midY);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(pad.left, pad.top);
            ctx.lineTo(pad.left, pad.top + ph);
            ctx.stroke();

            ctx.fillStyle = "#657694";
            ctx.font = "10px sans-serif";
            ctx.textAlign = "center";
            ctx.fillText("0", pad.left, ch - pad.bottom + 14);
            ctx.fillText("1", pad.left + pw, ch - pad.bottom + 14);
            ctx.textAlign = "right";
            ctx.fillText("0", pad.left - 4, midY + 3);
            ctx.fillText(h.toFixed(2), pad.left - 4, pad.top + 10);
            ctx.fillText((-h).toFixed(2), pad.left - 4, pad.top + ph + 3);

            const steps = 400;
            const vals = [];
            for (let i = 0; i <= steps; i++) {
                vals.push(growthFn(i / steps));
            }

            ctx.beginPath();
            ctx.fillStyle = "rgba(63, 132, 88, 0.12)";
            ctx.moveTo(pad.left, midY);
            for (let i = 0; i <= steps; i++) {
                const x = pad.left + (i / steps) * pw;
                const v = vals[i];
                if (v >= 0) {
                    const y = midY - (v / h) * (ph / 2);
                    ctx.lineTo(x, y);
                } else {
                    ctx.lineTo(x, midY);
                }
            }
            ctx.lineTo(pad.left + pw, midY);
            ctx.closePath();
            ctx.fill();

            ctx.beginPath();
            ctx.fillStyle = "rgba(193, 98, 63, 0.12)";
            ctx.moveTo(pad.left, midY);
            for (let i = 0; i <= steps; i++) {
                const x = pad.left + (i / steps) * pw;
                const v = vals[i];
                if (v < 0) {
                    const y = midY - (v / h) * (ph / 2);
                    ctx.lineTo(x, y);
                } else {
                    ctx.lineTo(x, midY);
                }
            }
            ctx.lineTo(pad.left + pw, midY);
            ctx.closePath();
            ctx.fill();

            ctx.beginPath();
            ctx.strokeStyle = "#5367bf";
            ctx.lineWidth = 2;
            for (let i = 0; i <= steps; i++) {
                const x = pad.left + (i / steps) * pw;
                const y = midY - (vals[i] / h) * (ph / 2);
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.stroke();

            const uX = pad.left + uIndicator * pw;
            ctx.beginPath();
            ctx.strokeStyle = "#ff6600";
            ctx.lineWidth = 1.5;
            ctx.setLineDash([4, 3]);
            ctx.moveTo(uX, pad.top);
            ctx.lineTo(uX, pad.top + ph);
            ctx.stroke();
            ctx.setLineDash([]);

            const gVal = growthFn(uIndicator);
            const dotY = midY - (gVal / h) * (ph / 2);
            ctx.beginPath();
            ctx.arc(uX, dotY, 4, 0, Math.PI * 2);
            ctx.fillStyle = "#ff6600";
            ctx.fill();

            ctx.fillStyle = "#0b0e14";
            ctx.font = "11px sans-serif";
            ctx.textAlign = "left";
            ctx.fillText(
                "U=" + uIndicator.toFixed(3) + "  G=" + gVal.toFixed(4),
                uX + 8,
                dotY - 6
            );
        }
    }

    // -- W4: Search Landscape Comparison --

    function initSearch(el) {
        makeHeader(el, "Search strategy comparison");
        const maxSteps = parseInt(el.dataset.steps) || 200;
        const autoPlay = el.dataset.autoPlay !== "false";

        const panelW = 200;
        const panelH = 200;

        function landscape(x, y) {
            const d1 = Math.sqrt((x - 0.3) * (x - 0.3) + (y - 0.7) * (y - 0.7));
            const d2 = Math.sqrt((x - 0.75) * (x - 0.75) + (y - 0.25) * (y - 0.25));
            const p1 = 0.7 * Math.exp(-(d1 * d1) / 0.02);
            const p2 = 1.0 * Math.exp(-(d2 * d2) / 0.01);
            const ripple = 0.15 * Math.sin(x * 12) * Math.sin(y * 12);
            return Math.max(0, Math.min(1, p1 + p2 + ripple));
        }

        function makePanel(title) {
            const { canvas, ctx, w, h } = initCanvas(panelW, panelH);
            const wrap = document.createElement("div");
            wrap.className = "lenia-canvas-wrap plot";
            wrap.appendChild(canvas);
            const col = document.createElement("div");
            const label = document.createElement("div");
            label.className = "lenia-widget-title";
            label.style.marginBottom = "6px";
            label.textContent = title;
            const metric = document.createElement("div");
            metric.className = "lenia-metric";
            metric.style.fontSize = "11px";
            col.append(label, wrap, metric);
            return { canvas, ctx, w, h, col, metric };
        }

        const pRandom = makePanel("Random search");
        const pES = makePanel("ES (gradient)");
        const pME = makePanel("MAP-Elites");

        const body = document.createElement("div");
        body.className = "lenia-widget-body triple-panel";
        body.append(pRandom.col, pES.col, pME.col);

        const controls = document.createElement("div");
        controls.className = "lenia-controls";
        let step = 0;
        let playing = autoPlay && !reducedMotion;

        const stepSlider = makeSlider("step", 0, maxSteps, 1, 0, (v) => {
            step = Math.round(v);
            drawAll();
        });
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
                randomTrace.push({ x: rng(), y: rng(), f: 0 });
                randomTrace[i].f = landscape(randomTrace[i].x, randomTrace[i].y);
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
                    const v = Math.round(f * 40 + 220);
                    imgData.data[idx] = v;
                    imgData.data[idx + 1] = v;
                    imgData.data[idx + 2] = v;
                    imgData.data[idx + 3] = 255;
                }
            }
            putPixels(panel, imgData);
        }

        function drawAll() {
            drawBackground(pRandom);
            drawBackground(pES);
            drawBackground(pME);

            let rBest = 0;
            for (let i = 0; i < step && i < randomTrace.length; i++) {
                const p = randomTrace[i];
                pRandom.ctx.fillStyle = "rgba(83, 103, 191, 0.5)";
                pRandom.ctx.beginPath();
                pRandom.ctx.arc(p.x * panelW, p.y * panelH, 2, 0, Math.PI * 2);
                pRandom.ctx.fill();
                if (p.f > rBest) rBest = p.f;
            }
            pRandom.metric.textContent = "best: " + rBest.toFixed(3);

            pES.ctx.strokeStyle = "rgba(83, 103, 191, 0.6)";
            pES.ctx.lineWidth = 1;
            pES.ctx.beginPath();
            for (let i = 0; i < step && i < esTrace.length; i++) {
                const p = esTrace[i];
                if (i === 0) pES.ctx.moveTo(p.x * panelW, p.y * panelH);
                else pES.ctx.lineTo(p.x * panelW, p.y * panelH);
            }
            pES.ctx.stroke();
            if (step > 0 && step <= esTrace.length) {
                const last = esTrace[Math.min(step - 1, esTrace.length - 1)];
                pES.ctx.fillStyle = "#ff6600";
                pES.ctx.beginPath();
                pES.ctx.arc(last.x * panelW, last.y * panelH, 4, 0, Math.PI * 2);
                pES.ctx.fill();
                pES.metric.textContent = "fitness: " + last.f.toFixed(3);
            }

            const gridN = 8;
            const cellW = panelW / gridN;
            const cellH = panelH / gridN;
            let coverage = 0;
            for (let i = 0; i < meGrid.length; i++) {
                const cell = meGrid[i];
                if (cell && cell.step < step) {
                    coverage++;
                    const gx = i % gridN;
                    const gy = Math.floor(i / gridN);
                    const cr = Math.round(60 + cell.f * 130);
                    const cg = Math.round(130 + cell.f * 60);
                    const cb = Math.round(80 + cell.f * 100);
                    pME.ctx.fillStyle = "rgba(" + cr + "," + cg + "," + cb + ",0.7)";
                    pME.ctx.fillRect(gx * cellW + 1, gy * cellH + 1, cellW - 2, cellH - 2);
                }
            }
            pME.ctx.strokeStyle = "rgba(11, 14, 20, 0.12)";
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
            pME.metric.textContent = "coverage: " + coverage + "/" + (gridN * gridN);
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

    // -- W5: CVT Builder --

    function initCVT(el) {
        makeHeader(el, "Centroidal Voronoi tessellation (Lloyd's algorithm)");
        const nCentroids = parseInt(el.dataset.centroids) || 64;
        const cvs = initCanvas(400, 400);
        const wrap = document.createElement("div");
        wrap.className = "lenia-canvas-wrap plot";
        wrap.appendChild(cvs.canvas);

        const controls = document.createElement("div");
        controls.className = "lenia-controls";
        let iteration = 0;
        let playing = false;

        const iterLabel = document.createElement("span");
        iterLabel.className = "lenia-metric";
        iterLabel.textContent = "iteration: 0";

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
            draw();
        });
        controls.append(stepBtn, playBtn, resetBtn, iterLabel);

        const body = document.createElement("div");
        body.className = "lenia-widget-body";
        body.append(wrap, controls);
        el.appendChild(body);

        let centroids;

        function initCentroids() {
            const rng = splitmix32(7);
            centroids = [];
            for (let i = 0; i < nCentroids; i++) {
                centroids.push([rng(), rng()]);
            }
        }

        function lloydStep() {
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
            iterLabel.textContent = "iteration: " + iteration;
        }

        function draw() {
            const { ctx, w, h } = cvs;
            const imgData = ctx.createImageData(w, h);

            const colors = centroids.map((_, i) => {
                const hue = (i * 360 / nCentroids + 30) % 360;
                return hslToRgb(hue, 0.25, 0.88);
            });

            for (let y = 0; y < h; y++) {
                for (let x = 0; x < w; x++) {
                    const px = (x + 0.5) / w;
                    const py = (y + 0.5) / h;
                    let minD = Infinity, minK = 0;
                    for (let k = 0; k < nCentroids; k++) {
                        const dx = px - centroids[k][0];
                        const dy = py - centroids[k][1];
                        const d = dx * dx + dy * dy;
                        if (d < minD) { minD = d; minK = k; }
                    }
                    const idx = (y * w + x) * 4;
                    const c = colors[minK];
                    imgData.data[idx] = c[0];
                    imgData.data[idx + 1] = c[1];
                    imgData.data[idx + 2] = c[2];
                    imgData.data[idx + 3] = 255;
                }
            }
            putPixels(cvs, imgData);

            ctx.fillStyle = "#0b0e14";
            for (let k = 0; k < nCentroids; k++) {
                ctx.beginPath();
                ctx.arc(centroids[k][0] * w, centroids[k][1] * h, 3, 0, Math.PI * 2);
                ctx.fill();
            }
        }

        function hslToRgb(h, s, l) {
            h /= 360;
            let r, g, b;
            if (s === 0) {
                r = g = b = l;
            } else {
                const hue2rgb = (p, q, t) => {
                    if (t < 0) t += 1;
                    if (t > 1) t -= 1;
                    if (t < 1/6) return p + (q - p) * 6 * t;
                    if (t < 1/2) return q;
                    if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
                    return p;
                };
                const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
                const p = 2 * l - q;
                r = hue2rgb(p, q, h + 1/3);
                g = hue2rgb(p, q, h);
                b = hue2rgb(p, q, h - 1/3);
            }
            return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
        }

        initCentroids();
        draw();

        if (!reducedMotion) {
            function tick() {
                if (playing) {
                    lloydStep();
                    draw();
                }
                requestAnimationFrame(tick);
            }
            requestAnimationFrame(tick);
        }
    }

    // -- W6: MAP-Elites Step-Through --

    function initMapElites(el) {
        makeHeader(el, "MAP-Elites step-through");
        const traceSrc = el.dataset.traceSrc;
        const nCentroids = parseInt(el.dataset.centroids) || 64;

        const gridCvs = initCanvas(300, 300);
        const gridWrap = document.createElement("div");
        gridWrap.className = "lenia-canvas-wrap plot";
        gridWrap.appendChild(gridCvs.canvas);

        const narration = document.createElement("div");
        narration.className = "lenia-narration";
        narration.textContent = "Loading trace data...";

        const body = document.createElement("div");
        body.className = "lenia-widget-body dual-panel";
        body.append(gridWrap, narration);

        const controls = document.createElement("div");
        controls.className = "lenia-controls";

        const metricsBar = document.createElement("div");
        metricsBar.className = "lenia-metrics-bar";

        el.append(body, controls, metricsBar);

        let trace = null;
        let gen = 0;
        let playing = false;
        let repertoire = [];

        function loadTrace() {
            if (!traceSrc) {
                useSyntheticTrace();
                return;
            }
            fetch(traceSrc)
                .then((r) => r.json())
                .then((data) => {
                    trace = data;
                    setupControls();
                    drawState();
                })
                .catch(() => {
                    useSyntheticTrace();
                });
        }

        function useSyntheticTrace() {
            const rng = splitmix32(42);
            const cents = [];
            for (let i = 0; i < nCentroids; i++) {
                cents.push([rng(), rng()]);
            }

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
            });
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
                    if (playing && now - lastTick > 400) {
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
                        imgData.data[idx] = Math.round(30 + f * 50);
                        imgData.data[idx + 1] = Math.round(80 + f * 120);
                        imgData.data[idx + 2] = Math.round(60 + f * 100);
                    } else {
                        imgData.data[idx] = 240;
                        imgData.data[idx + 1] = 240;
                        imgData.data[idx + 2] = 240;
                    }
                    imgData.data[idx + 3] = 255;
                }
            }
            putPixels(gridCvs, imgData);

            for (let k = 0; k < trace.centroids.length; k++) {
                const cx = trace.centroids[k][0] * w;
                const cy = trace.centroids[k][1] * h;
                ctx.fillStyle = repertoire[k] !== null ? "#0b0e14" : "rgba(11,14,20,0.25)";
                ctx.beginPath();
                ctx.arc(cx, cy, 2, 0, Math.PI * 2);
                ctx.fill();
            }

            if (gen > 0 && gen <= trace.generations.length) {
                const ev = trace.generations[gen - 1];
                const cx = ev.child_descriptor[0] * w;
                const cy = ev.child_descriptor[1] * h;
                ctx.strokeStyle = ev.outcome === "placed" ? "#3c7f61" : "#c1623f";
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.arc(cx, cy, 6, 0, Math.PI * 2);
                ctx.stroke();

                const parentC = trace.centroids[ev.parent_idx];
                ctx.strokeStyle = "rgba(83, 103, 191, 0.6)";
                ctx.lineWidth = 1;
                ctx.setLineDash([3, 3]);
                ctx.beginPath();
                ctx.moveTo(parentC[0] * w, parentC[1] * h);
                ctx.lineTo(cx, cy);
                ctx.stroke();
                ctx.setLineDash([]);
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
                makeMetric("coverage", coverage + "/" + trace.centroids.length),
                makeMetric("QD score", totalFit.toFixed(2)),
                makeMetric("max fitness", maxFit.toFixed(3))
            );

            if (gen > 0 && gen <= trace.generations.length) {
                const ev = trace.generations[gen - 1];
                if (ev.outcome === "placed") {
                    narration.textContent = ev.previous_fitness !== null
                        ? "Child placed in cell " + ev.landing_cell +
                          " (fitness " + ev.child_fitness.toFixed(3) +
                          " > " + ev.previous_fitness.toFixed(3) + ")"
                        : "Child placed in empty cell " + ev.landing_cell +
                          " (fitness " + ev.child_fitness.toFixed(3) + ")";
                } else {
                    narration.textContent =
                        "Child discarded from cell " + ev.landing_cell +
                        " (fitness " + ev.child_fitness.toFixed(3) +
                        " did not exceed incumbent)";
                }
            } else {
                narration.textContent = gen === 0
                    ? "Press Play or Step to begin the MAP-Elites loop."
                    : "Repertoire complete.";
            }
        }

        loadTrace();
    }

    // -- W7: Isoline Variation Visualizer --

    function initIsoline(el) {
        makeHeader(el, "Isoline variation");
        let isoSigma = parseFloat(el.dataset.isoSigma) || 0.005;
        let lineSigma = parseFloat(el.dataset.lineSigma) || 0.05;

        const cvs = initCanvas(400, 400);
        const wrap = document.createElement("div");
        wrap.className = "lenia-canvas-wrap plot";
        wrap.appendChild(cvs.canvas);

        const controls = document.createElement("div");
        controls.className = "lenia-controls";
        const sIso = makeSlider("iso \u03c3", 0.001, 0.05, 0.001, isoSigma, (v) => {
            isoSigma = v;
            draw();
        });
        const sLine = makeSlider("line \u03c3", 0.005, 0.2, 0.005, lineSigma, (v) => {
            lineSigma = v;
            draw();
        });
        controls.append(sIso.group, sLine.group);

        const body = document.createElement("div");
        body.className = "lenia-widget-body";
        body.append(wrap, controls);
        el.appendChild(body);

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

            ctx.fillStyle = "#f5f5f5";
            ctx.fillRect(0, 0, w, h);

            const ax = pointA[0] * w, ay = pointA[1] * h;
            const bx = pointB[0] * w, by = pointB[1] * h;

            const dx = pointB[0] - pointA[0];
            const dy = pointB[1] - pointA[1];
            const len = Math.sqrt(dx * dx + dy * dy) || 1e-6;
            const dirX = dx / len;
            const dirY = dy / len;

            const rng = splitmix32(123);
            const nSamples = 80;

            ctx.fillStyle = "rgba(83, 103, 191, 0.2)";
            for (let i = 0; i < nSamples; i++) {
                const isoX = gaussRandom(rng) * isoSigma;
                const isoY = gaussRandom(rng) * isoSigma;
                const cx = pointA[0] + isoX;
                const cy = pointA[1] + isoY;
                ctx.beginPath();
                ctx.arc(cx * w, cy * h, 2.5, 0, Math.PI * 2);
                ctx.fill();
            }

            const rng2 = splitmix32(456);
            ctx.fillStyle = "rgba(193, 98, 63, 0.2)";
            for (let i = 0; i < nSamples; i++) {
                const lineT = gaussRandom(rng2) * lineSigma;
                const cx = pointA[0] + dirX * lineT;
                const cy = pointA[1] + dirY * lineT;
                ctx.beginPath();
                ctx.arc(cx * w, cy * h, 2.5, 0, Math.PI * 2);
                ctx.fill();
            }

            const rng3 = splitmix32(789);
            ctx.fillStyle = "rgba(63, 132, 88, 0.35)";
            for (let i = 0; i < nSamples; i++) {
                const isoX = gaussRandom(rng3) * isoSigma;
                const isoY = gaussRandom(rng3) * isoSigma;
                const lineT = gaussRandom(rng3) * lineSigma;
                const cx = pointA[0] + isoX + dirX * lineT;
                const cy = pointA[1] + isoY + dirY * lineT;
                ctx.beginPath();
                ctx.arc(cx * w, cy * h, 3, 0, Math.PI * 2);
                ctx.fill();
            }

            ctx.setLineDash([5, 4]);
            ctx.strokeStyle = "rgba(11, 14, 20, 0.3)";
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(ax, ay);
            ctx.lineTo(bx, by);
            ctx.stroke();
            ctx.setLineDash([]);

            ctx.fillStyle = "#5367bf";
            ctx.beginPath();
            ctx.arc(ax, ay, 7, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = "#fff";
            ctx.font = "bold 10px sans-serif";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText("A", ax, ay);

            ctx.fillStyle = "#c1623f";
            ctx.beginPath();
            ctx.arc(bx, by, 7, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = "#fff";
            ctx.fillText("B", bx, by);

            ctx.fillStyle = "#657694";
            ctx.font = "11px sans-serif";
            ctx.textAlign = "left";
            ctx.textBaseline = "top";
            ctx.fillText("isotropic (blue) + directional (red) = combined (green)", 8, h - 18);
        }

        draw();
    }
})();
