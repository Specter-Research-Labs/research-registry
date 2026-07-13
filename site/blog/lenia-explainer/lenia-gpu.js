var LeniaGPU = (() => {
    "use strict";

    function splitmix32(seed) {
        let state = seed | 0;
        return () => {
            state = (state + 0x9e3779b9) | 0;
            let z = state;
            z = Math.imul(z ^ (z >>> 16), 0x85ebca6b);
            z = Math.imul(z ^ (z >>> 13), 0xc2b2ae35);
            z = (z ^ (z >>> 16)) >>> 0;
            return z / 0x100000000;
        };
    }

    function parseEngineConfig(genotype, runConfig) {
        const nbK = genotype.r.length;
        const channels = runConfig.channels;

        const c0 = [];
        const c1 = Array.from({ length: channels }, () => []);
        for (let k = 0; k < nbK; k++) {
            const sourceChannel = runConfig.connectivity[0]?.[k] ?? 0;
            c0.push(sourceChannel);
            const targetChannels = runConfig.connectivity[1]?.[k] ?? [0];
            const targets = Array.isArray(targetChannels) ? targetChannels : [targetChannels];
            for (const ch of targets) {
                if (ch < channels) c1[ch].push(k);
            }
        }

        return {
            sx: runConfig.grid.sx,
            sy: runConfig.grid.sy,
            channels,
            nbK,
            dt: runConfig.flow.dt,
            dd: runConfig.flow.dd,
            sigma: runConfig.flow.sigma,
            n: runConfig.flow.n,
            thetaA: runConfig.flow.theta_a,
            dynamics: runConfig.dynamics ?? "flow",
            border: (runConfig.reintegration?.border ?? "torus"),
            R: genotype.R,
            c0,
            c1,
        };
    }

    function buildKernelBuffer(genotype, config) {
        const { sx, sy, nbK } = config;
        const midX = Math.floor(sx / 2);
        const midY = Math.floor(sy / 2);
        const kernels = new Float32Array(sx * sy * nbK);

        for (let k = 0; k < nbK; k++) {
            const rK = genotype.r[k];
            const divisor = genotype.R * rK;
            const bK = genotype.b[k];
            const wK = genotype.w[k];
            const aK = genotype.a[k];
            const nGauss = bK.length;

            let sum = 0;
            for (let y = 0; y < sy; y++) {
                for (let x = 0; x < sx; x++) {
                    const dx = x - midX;
                    const dy = y - midY;
                    const dist = Math.sqrt(dx * dx + dy * dy);
                    const D = dist / divisor;

                    let val = 0;
                    for (let g = 0; g < nGauss; g++) {
                        const diff = D - aK[g];
                        val += bK[g] * Math.exp(-(diff * diff) / (2 * wK[g] * wK[g]));
                    }

                    kernels[(y * sx + x) * nbK + k] = val;
                    sum += val;
                }
            }

            if (sum > 0) {
                for (let i = 0; i < sx * sy; i++) {
                    kernels[i * nbK + k] /= sum;
                }
            }
        }

        return kernels;
    }

    function buildGrowthParams(genotype) {
        const nbK = genotype.r.length;
        const params = new Float32Array(nbK * 4);
        for (let k = 0; k < nbK; k++) {
            params[k * 4] = genotype.m[k];
            params[k * 4 + 1] = genotype.s[k];
            params[k * 4 + 2] = genotype.h[k];
            params[k * 4 + 3] = 0;
        }
        return params;
    }

    function buildC0Buffer(config) {
        return new Uint32Array(config.c0);
    }

    function buildC1MaskBuffer(config) {
        const { channels, nbK, c1 } = config;
        const mask = new Float32Array(channels * nbK);
        for (let ch = 0; ch < channels; ch++) {
            for (const k of c1[ch]) {
                mask[ch * nbK + k] = 1.0;
            }
        }
        return mask;
    }

    function rle2cells(rle) {
        const stripped = rle.replace(/!$/, "") + "$";
        const twoCharPrefix = "pqrstuvwxy@";
        const rows = [];
        let row = [];
        let count = "";
        let last = "";
        for (let i = 0; i < stripped.length; i++) {
            const ch = stripped[i];
            if (ch >= "0" && ch <= "9") { count += ch; continue; }
            if (twoCharPrefix.indexOf(ch) >= 0) { last = ch; continue; }
            const token = last + ch;
            last = "";
            if (token === "$") {
                const n = count === "" ? 1 : parseInt(count, 10);
                rows.push(row);
                for (let k = 1; k < n; k++) rows.push([]);
                row = [];
                count = "";
                continue;
            }
            let val;
            if (token === "." || token === "b") val = 0;
            else if (token === "o") val = 255;
            else if (token.length === 1) val = token.charCodeAt(0) - 64;
            else val = (token.charCodeAt(0) - 112) * 24 + (token.charCodeAt(1) - 65 + 25);
            const n = count === "" ? 1 : parseInt(count, 10);
            for (let k = 0; k < n; k++) row.push(val / 255);
            count = "";
        }
        const w = rows.reduce((m, r) => Math.max(m, r.length), 0);
        const h = rows.length;
        const data = new Float32Array(w * h);
        for (let y = 0; y < h; y++) {
            const r = rows[y];
            for (let x = 0; x < r.length; x++) data[y * w + x] = r[x];
        }
        return { w, h, data };
    }

    function initFromRle(init, config) {
        const { sx, sy, channels } = config;
        const state = new Float32Array(sx * sy * channels);
        const { w, h, data } = rle2cells(init.cells);
        const x0 = Math.floor(init.cx * sx - w / 2);
        const y0 = Math.floor(init.cy * sy - h / 2);
        const ch = init.channel;
        for (let y = 0; y < h; y++) {
            for (let x = 0; x < w; x++) {
                const px = ((x0 + x) % sx + sx) % sx;
                const py = ((y0 + y) % sy + sy) % sy;
                state[(py * sx + px) * channels + ch] = data[y * w + x];
            }
        }
        return state;
    }

    function initFromPatches(init, config) {
        const { sx, sy, channels } = config;
        const state = new Float32Array(sx * sy * channels);
        const rng = splitmix32(init.seed);
        const low = init.a_uniform.low;
        const high = init.a_uniform.high;

        for (const patch of init.patches) {
            const cx = patch.cx * sx;
            const cy = patch.cy * sy;
            const r = patch.radius * Math.min(sx, sy);
            const r2 = r * r;

            for (let y = 0; y < sy; y++) {
                for (let x = 0; x < sx; x++) {
                    const dx = x - cx;
                    const dy = y - cy;
                    if (dx * dx + dy * dy <= r2) {
                        for (let ch = 0; ch < channels; ch++) {
                            const val = low + rng() * (high - low);
                            state[(y * sx + x) * channels + ch] = Math.max(0, Math.min(1, val));
                        }
                    }
                }
            }
        }

        return state;
    }

    function generateInitialState(phenotype, config) {
        const init = phenotype.init;
        if (init.kind === "rle") return initFromRle(init, config);
        if (init.kind === "patches") return initFromPatches(init, config);
        throw new Error(`unknown init kind: ${init.kind}`);
    }

    async function fetchShader(basePath, name) {
        const resp = await fetch(basePath + name);
        if (!resp.ok) throw new Error(`could not load ${name}: HTTP ${resp.status}`);
        return await resp.text();
    }

    async function createEngine(device, genotype, phenotype, runConfig, shaderBasePath) {
        const config = parseEngineConfig(genotype, runConfig);
        const { sx, sy, channels, nbK, dd } = config;

        const stateSize = sx * sy * channels;
        const flowSize = sx * sy * channels * 2;
        const kernelRadius = Math.ceil(genotype.R * Math.max(...genotype.r));

        const configData = new ArrayBuffer(48);
        const cv = new DataView(configData);
        cv.setUint32(0, sx, true);
        cv.setUint32(4, sy, true);
        cv.setUint32(8, channels, true);
        cv.setUint32(12, nbK, true);
        cv.setFloat32(16, config.dt, true);
        cv.setInt32(20, dd, true);
        cv.setFloat32(24, config.sigma, true);
        cv.setInt32(28, config.n, true);
        cv.setFloat32(32, config.thetaA, true);
        cv.setUint32(36, config.border === "torus" ? 1 : 0, true);
        cv.setInt32(40, kernelRadius, true);
        cv.setUint32(44, 0, true);

        const configBuffer = device.createBuffer({ size: 48, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST });
        device.queue.writeBuffer(configBuffer, 0, new Uint8Array(configData));

        const stateBufferA = device.createBuffer({ size: stateSize * 4, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST });
        const stateBufferB = device.createBuffer({ size: stateSize * 4, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST | GPUBufferUsage.COPY_SRC });
        const flowBuffer = device.createBuffer({ size: flowSize * 4, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST });

        const write = (buf, data) => device.queue.writeBuffer(buf, 0, data.buffer, data.byteOffset, data.byteLength);

        const kernelData = buildKernelBuffer(genotype, config);
        const kernelBuffer = device.createBuffer({ size: kernelData.byteLength, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST });
        write(kernelBuffer, kernelData);

        const growthData = buildGrowthParams(genotype);
        const growthBuffer = device.createBuffer({ size: growthData.byteLength, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST });
        write(growthBuffer, growthData);

        const c0Data = buildC0Buffer(config);
        const c0Buffer = device.createBuffer({ size: Math.max(c0Data.byteLength, 4), usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST });
        write(c0Buffer, c0Data);

        const c1Data = buildC1MaskBuffer(config);
        const c1Buffer = device.createBuffer({ size: Math.max(c1Data.byteLength, 4), usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST });
        write(c1Buffer, c1Data);

        const initialState = generateInitialState(phenotype, config);
        write(stateBufferA, initialState);

        const stepSource = await fetchShader(shaderBasePath, "lenia-step.wgsl");
        const stepModule = device.createShaderModule({ code: stepSource });

        const stepBindGroupLayout = device.createBindGroupLayout({
            entries: [
                { binding: 0, visibility: GPUShaderStage.COMPUTE, buffer: { type: "uniform" } },
                { binding: 1, visibility: GPUShaderStage.COMPUTE, buffer: { type: "read-only-storage" } },
                { binding: 2, visibility: GPUShaderStage.COMPUTE, buffer: { type: "storage" } },
                { binding: 3, visibility: GPUShaderStage.COMPUTE, buffer: { type: "read-only-storage" } },
                { binding: 4, visibility: GPUShaderStage.COMPUTE, buffer: { type: "read-only-storage" } },
                { binding: 5, visibility: GPUShaderStage.COMPUTE, buffer: { type: "read-only-storage" } },
                { binding: 6, visibility: GPUShaderStage.COMPUTE, buffer: { type: "read-only-storage" } },
                { binding: 7, visibility: GPUShaderStage.COMPUTE, buffer: { type: "storage" } },
            ],
        });

        const growthPipeline = device.createComputePipeline({
            layout: device.createPipelineLayout({ bindGroupLayouts: [stepBindGroupLayout] }),
            compute: { module: stepModule, entryPoint: "compute_growth" },
        });

        const flowPipeline = device.createComputePipeline({
            layout: device.createPipelineLayout({ bindGroupLayouts: [stepBindGroupLayout] }),
            compute: { module: stepModule, entryPoint: "compute_flow" },
        });

        const reintegratePipeline = device.createComputePipeline({
            layout: device.createPipelineLayout({ bindGroupLayouts: [stepBindGroupLayout] }),
            compute: { module: stepModule, entryPoint: "reintegrate" },
        });

        const basicPipeline = device.createComputePipeline({
            layout: device.createPipelineLayout({ bindGroupLayouts: [stepBindGroupLayout] }),
            compute: { module: stepModule, entryPoint: "compute_basic" },
        });

        const flowBindGroup = device.createBindGroup({
            layout: stepBindGroupLayout,
            entries: [
                { binding: 0, resource: { buffer: configBuffer } },
                { binding: 1, resource: { buffer: stateBufferA } },
                { binding: 2, resource: { buffer: stateBufferB } },
                { binding: 3, resource: { buffer: kernelBuffer } },
                { binding: 4, resource: { buffer: growthBuffer } },
                { binding: 5, resource: { buffer: c0Buffer } },
                { binding: 6, resource: { buffer: c1Buffer } },
                { binding: 7, resource: { buffer: flowBuffer } },
            ],
        });

        const reintBindGroup = device.createBindGroup({
            layout: stepBindGroupLayout,
            entries: [
                { binding: 0, resource: { buffer: configBuffer } },
                { binding: 1, resource: { buffer: stateBufferA } },
                { binding: 2, resource: { buffer: stateBufferB } },
                { binding: 3, resource: { buffer: kernelBuffer } },
                { binding: 4, resource: { buffer: growthBuffer } },
                { binding: 5, resource: { buffer: c0Buffer } },
                { binding: 6, resource: { buffer: c1Buffer } },
                { binding: 7, resource: { buffer: flowBuffer } },
            ],
        });

        const workgroupsX = Math.ceil(sx / 8);
        const workgroupsY = Math.ceil(sy / 8);

        const renderModule = device.createShaderModule({ code: `
            struct V { @builtin(position) pos: vec4f, @location(0) uv: vec2f };
            @vertex fn vs(@builtin(vertex_index) i: u32) -> V {
                var p = array<vec2f, 3>(vec2f(-1,-1), vec2f(3,-1), vec2f(-1,3));
                var o: V;
                o.pos = vec4f(p[i], 0, 1);
                o.uv = p[i] * vec2f(0.5, -0.5) + vec2f(0.5, 0.5);
                return o;
            }

            struct RConf { sx: u32, sy: u32, channels: u32 };
            @group(0) @binding(0) var<uniform> rc: RConf;
            @group(0) @binding(1) var<storage, read> state: array<f32>;

            fn spectrum(idx: u32) -> vec3f {
                switch idx {
                    case 0u: { return vec3f(0.0196, 0.0157, 0.0392); }
                    case 1u: { return vec3f(0.4863, 0.9608, 1.0); }
                    case 2u: { return vec3f(0.3137, 0.4824, 1.0); }
                    case 3u: { return vec3f(0.7490, 0.2157, 1.0); }
                    case 4u: { return vec3f(1.0, 0.2275, 0.6863); }
                    case 5u: { return vec3f(1.0, 0.4431, 0.2196); }
                    case 6u: { return vec3f(1.0, 0.8, 0.2706); }
                    default: { return vec3f(0.0); }
                }
            }

            @fragment fn fs(v: V) -> @location(0) vec4f {
                let x = min(u32(v.uv.x * f32(rc.sx)), rc.sx - 1u);
                let y = min(u32(v.uv.y * f32(rc.sy)), rc.sy - 1u);
                var total: f32 = 0.0;
                for (var ch = 0u; ch < rc.channels; ch++) {
                    total += state[(y * rc.sx + x) * rc.channels + ch];
                }
                total = clamp(total, 0.0, 1.0);
                let corrected = pow(total, 0.88);
                let scaled = corrected * 6.0;
                let lo = u32(floor(scaled));
                let hi = min(lo + 1u, 6u);
                let blend = scaled - f32(lo);
                let color = mix(spectrum(lo), spectrum(hi), blend);
                return vec4f(color, 1.0);
            }
        ` });

        const renderConfigData = new ArrayBuffer(16);
        const rcv = new DataView(renderConfigData);
        rcv.setUint32(0, sx, true);
        rcv.setUint32(4, sy, true);
        rcv.setUint32(8, channels, true);
        const renderConfigBuffer = device.createBuffer({ size: 16, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST });
        device.queue.writeBuffer(renderConfigBuffer, 0, new Uint8Array(renderConfigData));

        return {
            config,

            step() {
                const encoder = device.createCommandEncoder();

                if (config.dynamics === "basic") {
                    const basicPass = encoder.beginComputePass();
                    basicPass.setPipeline(basicPipeline);
                    basicPass.setBindGroup(0, flowBindGroup);
                    basicPass.dispatchWorkgroups(workgroupsX, workgroupsY);
                    basicPass.end();

                    encoder.copyBufferToBuffer(stateBufferB, 0, stateBufferA, 0, stateSize * 4);
                    device.queue.submit([encoder.finish()]);
                    return;
                }

                const zeros = new Float32Array(stateSize);
                write(stateBufferB, zeros);

                const growthPass = encoder.beginComputePass();
                growthPass.setPipeline(growthPipeline);
                growthPass.setBindGroup(0, flowBindGroup);
                growthPass.dispatchWorkgroups(workgroupsX, workgroupsY);
                growthPass.end();

                const gradientPass = encoder.beginComputePass();
                gradientPass.setPipeline(flowPipeline);
                gradientPass.setBindGroup(0, flowBindGroup);
                gradientPass.dispatchWorkgroups(workgroupsX, workgroupsY);
                gradientPass.end();

                const reintPass = encoder.beginComputePass();
                reintPass.setPipeline(reintegratePipeline);
                reintPass.setBindGroup(0, reintBindGroup);
                reintPass.dispatchWorkgroups(workgroupsX, workgroupsY);
                reintPass.end();

                encoder.copyBufferToBuffer(stateBufferB, 0, stateBufferA, 0, stateSize * 4);
                device.queue.submit([encoder.finish()]);
            },

            render(gpuCtx, renderPipeline, renderBindGroup) {
                const encoder = device.createCommandEncoder();
                const pass = encoder.beginRenderPass({
                    colorAttachments: [{
                        view: gpuCtx.getCurrentTexture().createView(),
                        loadOp: "clear",
                        clearValue: { r: 0, g: 0, b: 0, a: 1 },
                        storeOp: "store",
                    }],
                });
                pass.setPipeline(renderPipeline);
                pass.setBindGroup(0, renderBindGroup);
                pass.draw(3);
                pass.end();
                device.queue.submit([encoder.finish()]);
            },

            reset() {
                const state = generateInitialState(phenotype, config);
                write(stateBufferA, state);
            },

            destroy() {
                configBuffer.destroy();
                stateBufferA.destroy();
                stateBufferB.destroy();
                flowBuffer.destroy();
                kernelBuffer.destroy();
                growthBuffer.destroy();
                c0Buffer.destroy();
                c1Buffer.destroy();
                renderConfigBuffer.destroy();
            },

            _device: device,
            _renderModule: renderModule,
            _renderConfigBuffer: renderConfigBuffer,
            _stateBufferA: stateBufferA,
        };
    }

    async function load(creatureName, canvas) {
        if (!navigator.gpu) return null;

        const adapter = await navigator.gpu.requestAdapter();
        if (!adapter) return null;

        const scriptEl = document.querySelector('script[src$="lenia-gpu.js"]');
        const scriptSrc = scriptEl ? scriptEl.src : "";
        const basePath = scriptSrc.substring(0, scriptSrc.lastIndexOf("/") + 1);
        const shaderBasePath = basePath + "shaders/";

        const resp = await fetch(basePath + "creatures.json");
        if (!resp.ok) throw new Error(`could not load creature catalog: HTTP ${resp.status}`);
        const catalog = await resp.json();
        const creature = catalog[creatureName];
        if (!creature) return null;

        const { genotype, phenotype, runConfig } = creature;
        const { sx, sy } = runConfig.grid;

        const device = await adapter.requestDevice();
        canvas.width = sx;
        canvas.height = sy;
        const gpuCtx = canvas.getContext("webgpu");
        if (!gpuCtx) throw new Error("WebGPU canvas context is unavailable");
        gpuCtx.configure({ device, format: navigator.gpu.getPreferredCanvasFormat(), alphaMode: "opaque" });

        const engine = await createEngine(device, genotype, phenotype, runConfig, shaderBasePath);

        const canvasFormat = navigator.gpu.getPreferredCanvasFormat();
        const renderPipeline = device.createRenderPipeline({
            layout: "auto",
            vertex: { module: engine._renderModule, entryPoint: "vs" },
            fragment: { module: engine._renderModule, entryPoint: "fs", targets: [{ format: canvasFormat }] },
        });

        const renderBindGroup = device.createBindGroup({
            layout: renderPipeline.getBindGroupLayout(0),
            entries: [
                { binding: 0, resource: { buffer: engine._renderConfigBuffer } },
                { binding: 1, resource: { buffer: engine._stateBufferA } },
            ],
        });

        return {
            dynamics: engine.config.dynamics,
            step() {
                engine.step();
            },

            render() {
                engine.render(gpuCtx, renderPipeline, renderBindGroup);
            },

            reset() {
                engine.reset();
            },

            destroy() {
                engine.destroy();
            },
        };
    }

    return { load };
})();
