import Foundation
import Metal

final class FlowSandboxMetalRuntimeState {
    private struct StrokeUniforms {
        var centerX: Int32
        var centerY: Int32
        var radius: Int32
        var tool: UInt32
        var step: UInt32
        var strength: Float
    }

    private struct StampUniforms {
        var originX: Int32
        var originY: Int32
        var stampWidth: Int32
        var stampHeight: Int32
    }

    private struct SpawnUniforms {
        var enabled: UInt32
        var originX: Int32
        var originY: Int32
        var patchSize: Int32
        var value: Float
    }

    private enum StrokeToolCode: UInt32 {
        case food = 0
        case wall = 1
        case erase = 2
        case mutation = 3
    }

    let config: BatchedConfig
    let parameterCount: Int

    private let autoFoodSeed: Int
    private let device: MTLDevice
    private let commandQueue: MTLCommandQueue
    private let fullMetalPipeline: FlowLeniaMetalFullPipeline
    private let preparePipeline: MTLComputePipelineState
    private let finalizePipeline: MTLComputePipelineState
    private let displayPipeline: MTLComputePipelineState
    private let strokePipeline: MTLComputePipelineState
    private let stampPipeline: MTLComputePipelineState

    private let massBuffer: MTLBuffer
    private let paramsBuffer: MTLBuffer
    private let foodBuffer: MTLBuffer
    private let wallBuffer: MTLBuffer
    private let effectiveMassBuffer: MTLBuffer
    private let nextMassBuffer: MTLBuffer
    private let nextParamsBuffer: MTLBuffer
    private let displayBuffer: MTLBuffer
    private var displayDirty = true
    private var stampBufferCache: [UUID: (mass: MTLBuffer, params: MTLBuffer)] = [:]

    init(config: BatchedConfig, kernels: CompiledKernels, parameterCount: Int, autoFoodSeed: Int) {
        guard let device = MTLCreateSystemDefaultDevice(),
              let commandQueue = device.makeCommandQueue() else {
            preconditionFailure("Full-metal sandbox mode requires a Metal device and command queue.")
        }

        self.config = config
        self.parameterCount = parameterCount
        self.autoFoodSeed = autoFoodSeed
        self.device = device
        self.commandQueue = commandQueue
        self.fullMetalPipeline = FlowLeniaMetalFullPipeline(
            config: config,
            kernels: kernels,
            batchCount: 1,
            device: device,
            commandQueue: commandQueue
        )

        let library = Self.makeLibrary(
            device: device,
            source: Self.kernelSource(
                parameterCount: parameterCount,
                sx: config.sx,
                sy: config.sy
            )
        )
        self.preparePipeline = Self.makePipeline(device: device, library: library, name: "sandboxPrepareEffectiveMass")
        self.finalizePipeline = Self.makePipeline(device: device, library: library, name: "sandboxFinalizeState")
        self.displayPipeline = Self.makePipeline(device: device, library: library, name: "sandboxDisplayField")
        self.strokePipeline = Self.makePipeline(device: device, library: library, name: "sandboxApplyPointStroke")
        self.stampPipeline = Self.makePipeline(device: device, library: library, name: "sandboxApplyStamp")

        let cellCount = config.sx * config.sy
        let massByteCount = cellCount * MemoryLayout<Float>.stride
        let paramByteCount = cellCount * parameterCount * MemoryLayout<Float>.stride
        let scalarByteCount = cellCount * MemoryLayout<Float>.stride

        self.massBuffer = Self.makeSharedBuffer(device: device, length: massByteCount, label: "sandbox.mass")
        self.paramsBuffer = Self.makeSharedBuffer(device: device, length: paramByteCount, label: "sandbox.params")
        self.foodBuffer = Self.makeSharedBuffer(device: device, length: scalarByteCount, label: "sandbox.food")
        self.wallBuffer = Self.makeSharedBuffer(device: device, length: scalarByteCount, label: "sandbox.walls")
        self.effectiveMassBuffer = Self.makeSharedBuffer(device: device, length: scalarByteCount, label: "sandbox.effective")
        self.nextMassBuffer = Self.makeSharedBuffer(device: device, length: massByteCount, label: "sandbox.nextMass")
        self.nextParamsBuffer = Self.makeSharedBuffer(device: device, length: paramByteCount, label: "sandbox.nextParams")
        self.displayBuffer = Self.makeSharedBuffer(device: device, length: scalarByteCount, label: "sandbox.display")

        reset(initialStamp: nil)
    }

    func reset(initialStamp: CreatureStamp?) {
        Self.zero(buffer: massBuffer)
        Self.zero(buffer: paramsBuffer)
        Self.zero(buffer: foodBuffer)
        Self.zero(buffer: effectiveMassBuffer)
        Self.zero(buffer: nextMassBuffer)
        Self.zero(buffer: nextParamsBuffer)
        Self.zero(buffer: displayBuffer)
        Self.fill(buffer: wallBuffer, with: 1)
        displayDirty = true

        if let initialStamp {
            applyCreatureStamp(initialStamp, center: SIMD2<Int>(config.sx / 2, config.sy / 2))
        }
    }

    func step(
        stepCount: Int,
        autoFoodEnabled: Bool,
        autoFoodProbability: Float,
        autoFoodPatchSize: Int,
        autoFoodValue: Float
    ) {
        let spawn = Self.spawnPatch(
            enabled: autoFoodEnabled,
            probability: autoFoodProbability,
            patchSize: autoFoodPatchSize,
            value: autoFoodValue,
            step: stepCount,
            seed: autoFoodSeed,
            sx: config.sx,
            sy: config.sy
        )
        let spawnUniforms = SpawnUniforms(
            enabled: spawn.enabled ? 1 : 0,
            originX: Int32(spawn.originX),
            originY: Int32(spawn.originY),
            patchSize: Int32(spawn.patchSize),
            value: spawn.value
        )

        guard let baseCommandBuffer = commandQueue.makeCommandBuffer() else {
            preconditionFailure("Failed to create sandbox Metal command buffer.")
        }
        baseCommandBuffer.label = "sandbox.step"

        encode(preparePipeline, on: baseCommandBuffer, cellCount: config.sx * config.sy) { encoder in
            encoder.setBuffer(massBuffer, offset: 0, index: 0)
            encoder.setBuffer(foodBuffer, offset: 0, index: 1)
            encoder.setBuffer(wallBuffer, offset: 0, index: 2)
            encoder.setBuffer(effectiveMassBuffer, offset: 0, index: 3)
        }

        fullMetalPipeline.encodeStep(
            on: baseCommandBuffer,
            preparedMassBuffer: effectiveMassBuffer,
            paramsBuffer: paramsBuffer,
            nextMassBuffer: nextMassBuffer,
            nextParamsBuffer: nextParamsBuffer
        )

        withUnsafeBytes(of: spawnUniforms) { rawUniforms in
            encode(finalizePipeline, on: baseCommandBuffer, cellCount: config.sx * config.sy) { encoder in
                encoder.setBuffer(nextMassBuffer, offset: 0, index: 0)
                encoder.setBuffer(nextParamsBuffer, offset: 0, index: 1)
                encoder.setBuffer(foodBuffer, offset: 0, index: 2)
                encoder.setBuffer(wallBuffer, offset: 0, index: 3)
                encoder.setBuffer(massBuffer, offset: 0, index: 4)
                encoder.setBuffer(paramsBuffer, offset: 0, index: 5)
                encoder.setBuffer(foodBuffer, offset: 0, index: 6)
                encoder.setBytes(rawUniforms.baseAddress!, length: rawUniforms.count, index: 7)
            }
        }

        baseCommandBuffer.commit()
        baseCommandBuffer.waitUntilCompleted()
        displayDirty = true
    }

    func applyStroke(_ stroke: SandboxStroke, stepCount: Int) {
        guard !stroke.points.isEmpty else { return }
        guard let commandBuffer = commandQueue.makeCommandBuffer() else {
            preconditionFailure("Failed to create sandbox stroke command buffer.")
        }
        var encodedPoint = false
        for point in stroke.points {
            guard let tool = strokeToolCode(for: stroke.tool) else {
                continue
            }
            let uniforms = StrokeUniforms(
                centerX: Int32(point.x),
                centerY: Int32(point.y),
                radius: Int32(stroke.radius),
                tool: tool.rawValue,
                step: UInt32(max(0, stepCount)),
                strength: stroke.strength
            )
            withUnsafeBytes(of: uniforms) { rawUniforms in
                encode(strokePipeline, on: commandBuffer, cellCount: config.sx * config.sy) { encoder in
                    encoder.setBuffer(massBuffer, offset: 0, index: 0)
                    encoder.setBuffer(paramsBuffer, offset: 0, index: 1)
                    encoder.setBuffer(foodBuffer, offset: 0, index: 2)
                    encoder.setBuffer(wallBuffer, offset: 0, index: 3)
                    encoder.setBytes(rawUniforms.baseAddress!, length: rawUniforms.count, index: 4)
                }
            }
            encodedPoint = true
        }
        guard encodedPoint else {
            return
        }
        commandBuffer.commit()
        commandBuffer.waitUntilCompleted()
        displayDirty = true
    }

    func applyFoodRect(_ rect: SandboxRect, value: Float) {
        let x0 = max(0, rect.x)
        let y0 = max(0, rect.y)
        let x1 = min(config.sx, rect.x + rect.width)
        let y1 = min(config.sy, rect.y + rect.height)
        guard x0 < x1, y0 < y1 else { return }
        let food = foodBuffer.contents().bindMemory(to: Float.self, capacity: config.sx * config.sy)
        let walls = wallBuffer.contents().bindMemory(to: Float.self, capacity: config.sx * config.sy)
        let clampedValue = max(0, value)
        for x in x0..<x1 {
            for y in y0..<y1 {
                let index = x * config.sy + y
                guard walls[index] > 0.5 else { continue }
                food[index] = max(food[index], clampedValue)
            }
        }
        displayDirty = true
    }

    func applyCreatureStamp(_ stamp: CreatureStamp, center: SIMD2<Int>) {
        guard stamp.parameterCount == parameterCount else {
            return
        }

        let originX = center.x - (stamp.width / 2)
        let originY = center.y - (stamp.height / 2)
        let uniforms = StampUniforms(
            originX: Int32(originX),
            originY: Int32(originY),
            stampWidth: Int32(stamp.width),
            stampHeight: Int32(stamp.height)
        )

        let cachedBuffers: (mass: MTLBuffer, params: MTLBuffer)
        if let existing = stampBufferCache[stamp.id] {
            cachedBuffers = existing
        } else {
            let stampMassBuffer = Self.makeSharedBuffer(
                device: device,
                length: stamp.mass.count * MemoryLayout<Float>.stride,
                label: "sandbox.stamp.mass.\(stamp.id.uuidString)"
            )
            let stampParamBuffer = Self.makeSharedBuffer(
                device: device,
                length: stamp.params.count * MemoryLayout<Float>.stride,
                label: "sandbox.stamp.params.\(stamp.id.uuidString)"
            )
            Self.writeFloats(stamp.mass, to: stampMassBuffer)
            Self.writeFloats(stamp.params, to: stampParamBuffer)
            cachedBuffers = (stampMassBuffer, stampParamBuffer)
            stampBufferCache[stamp.id] = cachedBuffers
        }

        guard let commandBuffer = commandQueue.makeCommandBuffer() else {
            preconditionFailure("Failed to create sandbox stamp command buffer.")
        }
        withUnsafeBytes(of: uniforms) { rawUniforms in
            encode(stampPipeline, on: commandBuffer, cellCount: stamp.width * stamp.height) { encoder in
                encoder.setBuffer(massBuffer, offset: 0, index: 0)
                encoder.setBuffer(paramsBuffer, offset: 0, index: 1)
                encoder.setBuffer(wallBuffer, offset: 0, index: 2)
                encoder.setBuffer(cachedBuffers.mass, offset: 0, index: 3)
                encoder.setBuffer(cachedBuffers.params, offset: 0, index: 4)
                encoder.setBytes(rawUniforms.baseAddress!, length: rawUniforms.count, index: 5)
            }
        }
        commandBuffer.commit()
        commandBuffer.waitUntilCompleted()
        displayDirty = true
    }

    func displaySurface() -> LeniaMetalFieldSurface {
        refreshDisplayIfNeeded()
        return LeniaMetalFieldSurface(buffer: displayBuffer, width: config.sx, height: config.sy)
    }

    func frameBytes() -> Data {
        refreshDisplayIfNeeded()
        let values = Self.readFloats(from: displayBuffer, count: config.sx * config.sy)
        var bytes = [UInt8](repeating: 0, count: values.count)
        for index in values.indices {
            bytes[index] = UInt8(min(255, max(0, Int((values[index] * 255.0).rounded()))))
        }
        return Data(bytes)
    }

    func materializeMetrics() -> FlowSandboxMetrics {
        let cellCount = config.sx * config.sy
        let mass = Self.readFloats(from: massBuffer, count: cellCount)
        let food = Self.readFloats(from: foodBuffer, count: cellCount)
        let walls = Self.readFloats(from: wallBuffer, count: cellCount)
        return FlowSandboxMetrics(
            mass: mass,
            food: food,
            walls: walls
        )
    }

    func materializeStateSnapshot(step: Int) -> FlowSandboxStateSnapshot {
        let cellCount = config.sx * config.sy
        return FlowSandboxStateSnapshot(
            step: step,
            width: config.sx,
            height: config.sy,
            channels: 1,
            parameterCount: parameterCount,
            mass: Self.readFloats(from: massBuffer, count: cellCount),
            params: Self.readFloats(from: paramsBuffer, count: cellCount * parameterCount),
            food: Self.readFloats(from: foodBuffer, count: cellCount),
            walls: Self.readFloats(from: wallBuffer, count: cellCount)
        )
    }

    func restore(_ snapshot: FlowSandboxStateSnapshot) {
        Self.writeFloats(snapshot.mass, to: massBuffer)
        Self.writeFloats(snapshot.params, to: paramsBuffer)
        Self.writeFloats(snapshot.food, to: foodBuffer)
        Self.writeFloats(snapshot.walls, to: wallBuffer)
        Self.zero(buffer: effectiveMassBuffer)
        Self.zero(buffer: nextMassBuffer)
        Self.zero(buffer: nextParamsBuffer)
        displayDirty = true
    }

    private func refreshDisplayIfNeeded() {
        guard displayDirty else { return }
        guard let commandBuffer = commandQueue.makeCommandBuffer() else {
            preconditionFailure("Failed to create sandbox display command buffer.")
        }
        encodeDisplay(on: commandBuffer)
        commandBuffer.commit()
        commandBuffer.waitUntilCompleted()
        displayDirty = false
    }

    private func encodeDisplay(on commandBuffer: any MTLCommandBuffer) {
        encode(displayPipeline, on: commandBuffer, cellCount: config.sx * config.sy) { encoder in
            encoder.setBuffer(massBuffer, offset: 0, index: 0)
            encoder.setBuffer(foodBuffer, offset: 0, index: 1)
            encoder.setBuffer(wallBuffer, offset: 0, index: 2)
            encoder.setBuffer(displayBuffer, offset: 0, index: 3)
        }
    }

    private func strokeToolCode(for tool: SandboxTool) -> StrokeToolCode? {
        switch tool {
        case .creatureStamp:
            nil
        case .food:
            .food
        case .wall:
            .wall
        case .erase:
            .erase
        case .mutation:
            .mutation
        }
    }

    private func encode(
        _ pipeline: MTLComputePipelineState,
        on commandBuffer: any MTLCommandBuffer,
        cellCount: Int,
        configure: (MTLComputeCommandEncoder) -> Void
    ) {
        guard let encoder = commandBuffer.makeComputeCommandEncoder() else {
            preconditionFailure("Failed to create sandbox compute encoder.")
        }
        encoder.setComputePipelineState(pipeline)
        configure(encoder)
        let width = max(1, pipeline.threadExecutionWidth)
        let threadsPerGroup = MTLSize(width: width, height: 1, depth: 1)
        let threads = MTLSize(width: cellCount, height: 1, depth: 1)
        encoder.dispatchThreads(threads, threadsPerThreadgroup: threadsPerGroup)
        encoder.endEncoding()
    }

    private static func makeSharedBuffer(device: MTLDevice, length: Int, label: String) -> MTLBuffer {
        guard let buffer = device.makeBuffer(length: length, options: .storageModeShared) else {
            preconditionFailure("Failed to allocate Metal sandbox buffer \(label).")
        }
        buffer.label = label
        return buffer
    }

    private static func makePipeline(device: MTLDevice, library: MTLLibrary, name: String) -> MTLComputePipelineState {
        guard let function = library.makeFunction(name: name) else {
            preconditionFailure("Missing Metal sandbox function \(name).")
        }
        do {
            return try device.makeComputePipelineState(function: function)
        } catch {
            preconditionFailure("Failed to build Metal sandbox pipeline \(name): \(error)")
        }
    }

    private static func makeLibrary(device: MTLDevice, source: String) -> MTLLibrary {
        do {
            return try device.makeLibrary(source: source, options: nil)
        } catch {
            preconditionFailure("Failed to compile Metal sandbox library: \(error)")
        }
    }

    private static func writeFloats(_ values: [Float], to buffer: MTLBuffer) {
        values.withUnsafeBytes { raw in
            guard let baseAddress = raw.baseAddress else { return }
            memcpy(buffer.contents(), baseAddress, raw.count)
        }
    }

    private static func readFloats(from buffer: MTLBuffer, count: Int) -> [Float] {
        let pointer = buffer.contents().bindMemory(to: Float.self, capacity: count)
        return Array(UnsafeBufferPointer(start: pointer, count: count))
    }

    private static func zero(buffer: MTLBuffer) {
        memset(buffer.contents(), 0, buffer.length)
    }

    private static func fill(buffer: MTLBuffer, with value: Float) {
        let pointer = buffer.contents().bindMemory(to: Float.self, capacity: buffer.length / MemoryLayout<Float>.stride)
        let count = buffer.length / MemoryLayout<Float>.stride
        for index in 0..<count {
            pointer[index] = value
        }
    }

    private static func spawnPatch(
        enabled: Bool,
        probability: Float,
        patchSize: Int,
        value: Float,
        step: Int,
        seed: Int,
        sx: Int,
        sy: Int
    ) -> (enabled: Bool, originX: Int, originY: Int, patchSize: Int, value: Float) {
        guard enabled else {
            return (false, 0, 0, 0, 0)
        }
        var rng = SeededRandomNumberGenerator(seed: UInt64(seed) + UInt64(step))
        guard Float.random(in: 0..<1, using: &rng) < probability else {
            return (false, 0, 0, 0, 0)
        }
        let clampedPatchSize = max(1, min(min(sx, sy), patchSize))
        let maxX = max(0, sx - clampedPatchSize)
        let maxY = max(0, sy - clampedPatchSize)
        let x0 = Int.random(in: 0...maxX, using: &rng)
        let y0 = Int.random(in: 0...maxY, using: &rng)
        return (true, x0, y0, clampedPatchSize, max(0, value))
    }

    private static func kernelSource(
        parameterCount: Int,
        sx: Int,
        sy: Int
    ) -> String {
        return """
        #include <metal_stdlib>
        using namespace metal;

        struct StrokeUniforms {
            int centerX;
            int centerY;
            int radius;
            uint tool;
            uint step;
            float strength;
        };

        struct StampUniforms {
            int originX;
            int originY;
            int stampWidth;
            int stampHeight;
        };

        struct SpawnUniforms {
            uint enabled;
            int originX;
            int originY;
            int patchSize;
            float value;
        };

        constant int kParamCount = \(parameterCount);
        constant int kSX = \(sx);
        constant int kSY = \(sy);

        inline uint splitmix(uint value) {
            value += 0x9e3779b9u;
            value = (value ^ (value >> 16)) * 0x85ebca6bu;
            value = (value ^ (value >> 13)) * 0xc2b2ae35u;
            value ^= (value >> 16);
            return value;
        }

        inline float unitFloat(uint value) {
            return max((float(splitmix(value) & 0x00ffffffu) / 16777216.0f), 1.0e-6f);
        }

        inline float gaussianNoise(uint seedA, uint seedB) {
            float u1 = unitFloat(seedA);
            float u2 = unitFloat(seedB);
            float radius = sqrt(-2.0f * log(u1));
            float angle = 6.28318530718f * u2;
            return radius * cos(angle);
        }

        inline bool insideCircle(int x, int y, int centerX, int centerY, int radius) {
            int dx = x - centerX;
            int dy = y - centerY;
            return (dx * dx + dy * dy) <= (radius * radius);
        }

        kernel void sandboxPrepareEffectiveMass(
            device const float *mass [[buffer(0)]],
            device const float *food [[buffer(1)]],
            device const float *walls [[buffer(2)]],
            device float *effectiveMass [[buffer(3)]],
            uint gid [[thread_position_in_grid]]
        ) {
            if (gid >= uint(kSX * kSY)) {
                return;
            }
            float wall = walls[gid] > 0.5f ? 1.0f : 0.0f;
            float baseMass = mass[gid] * wall;
            float baseFood = food[gid] * wall;
            effectiveMass[gid] = clamp(baseMass + baseFood * 0.12f, 0.0f, 1.0f);
        }

        kernel void sandboxFinalizeState(
            device const float *nextMass [[buffer(0)]],
            device const float *nextParams [[buffer(1)]],
            device const float *foodIn [[buffer(2)]],
            device const float *walls [[buffer(3)]],
            device float *massOut [[buffer(4)]],
            device float *paramsOut [[buffer(5)]],
            device float *foodOut [[buffer(6)]],
            constant SpawnUniforms &spawn [[buffer(7)]],
            uint gid [[thread_position_in_grid]]
        ) {
            if (gid >= uint(kSX * kSY)) {
                return;
            }
            int x = int(gid / uint(kSY));
            int y = int(gid % uint(kSY));
            float wall = walls[gid] > 0.5f ? 1.0f : 0.0f;
            float next = clamp(nextMass[gid], 0.0f, 1.0f) * wall;
            massOut[gid] = next;

            uint paramBase = gid * uint(kParamCount);
            for (int k = 0; k < kParamCount; ++k) {
                paramsOut[paramBase + uint(k)] = nextParams[paramBase + uint(k)] * wall;
            }

            float foodValue = max(foodIn[gid] * 0.996f - next * 0.003f, 0.0f);
            if (spawn.enabled != 0u &&
                x >= spawn.originX && x < (spawn.originX + spawn.patchSize) &&
                y >= spawn.originY && y < (spawn.originY + spawn.patchSize)) {
                foodValue = max(foodValue, spawn.value);
            }
            foodOut[gid] = foodValue * wall;
        }

        kernel void sandboxDisplayField(
            device const float *mass [[buffer(0)]],
            device const float *food [[buffer(1)]],
            device const float *walls [[buffer(2)]],
            device float *display [[buffer(3)]],
            uint gid [[thread_position_in_grid]]
        ) {
            if (gid >= uint(kSX * kSY)) {
                return;
            }
            float wall = walls[gid] > 0.5f ? 1.0f : 0.0f;
            display[gid] = clamp(mass[gid] + food[gid] * 0.55f, 0.0f, 1.0f) * wall;
        }

        kernel void sandboxApplyPointStroke(
            device float *mass [[buffer(0)]],
            device float *params [[buffer(1)]],
            device float *food [[buffer(2)]],
            device float *walls [[buffer(3)]],
            constant StrokeUniforms &stroke [[buffer(4)]],
            uint gid [[thread_position_in_grid]]
        ) {
            if (gid >= uint(kSX * kSY)) {
                return;
            }
            int x = int(gid / uint(kSY));
            int y = int(gid % uint(kSY));
            if (!insideCircle(x, y, stroke.centerX, stroke.centerY, stroke.radius)) {
                return;
            }

            uint paramBase = gid * uint(kParamCount);
            switch (stroke.tool) {
                case 0u:
                    food[gid] = clamp(food[gid] + stroke.strength, 0.0f, 1.0f);
                    break;
                case 1u:
                    walls[gid] = 0.0f;
                    mass[gid] = 0.0f;
                    food[gid] = 0.0f;
                    for (int k = 0; k < kParamCount; ++k) {
                        params[paramBase + uint(k)] = 0.0f;
                    }
                    break;
                case 2u:
                    walls[gid] = 1.0f;
                    mass[gid] = 0.0f;
                    food[gid] = 0.0f;
                    for (int k = 0; k < kParamCount; ++k) {
                        params[paramBase + uint(k)] = 0.0f;
                    }
                    break;
                default: {
                    if (walls[gid] <= 0.5f) {
                        break;
                    }
                    for (int k = 0; k < kParamCount; ++k) {
                        uint seedA = stroke.step * 131u ^ uint((x + 1) * 977) ^ uint((y + 1) * 6151) ^ uint(k * 17 + 1);
                        uint seedB = seedA ^ 0x9e3779b9u;
                        float noise = gaussianNoise(seedA, seedB) * (stroke.strength * 0.15f);
                        params[paramBase + uint(k)] = clamp(params[paramBase + uint(k)] + noise, -2.0f, 2.0f);
                    }
                    break;
                }
            }
        }

        kernel void sandboxApplyStamp(
            device float *mass [[buffer(0)]],
            device float *params [[buffer(1)]],
            device const float *walls [[buffer(2)]],
            device const float *stampMass [[buffer(3)]],
            device const float *stampParams [[buffer(4)]],
            constant StampUniforms &stamp [[buffer(5)]],
            uint gid [[thread_position_in_grid]]
        ) {
            uint stampCount = uint(stamp.stampWidth * stamp.stampHeight);
            if (gid >= stampCount) {
                return;
            }
            int localX = int(gid / uint(stamp.stampHeight));
            int localY = int(gid % uint(stamp.stampHeight));
            int worldX = stamp.originX + localX;
            int worldY = stamp.originY + localY;
            if (worldX < 0 || worldY < 0 || worldX >= kSX || worldY >= kSY) {
                return;
            }

            uint worldIndex = uint(worldX * kSY + worldY);
            if (walls[worldIndex] <= 0.5f) {
                return;
            }

            float stampValue = stampMass[gid];
            if (stampValue <= 0.0f) {
                return;
            }
            mass[worldIndex] = max(mass[worldIndex], stampValue);

            if (stampValue > 0.01f) {
                uint worldParamBase = worldIndex * uint(kParamCount);
                uint stampParamBase = gid * uint(kParamCount);
                for (int k = 0; k < kParamCount; ++k) {
                    params[worldParamBase + uint(k)] = stampParams[stampParamBase + uint(k)];
                }
            }
        }
        """
    }
}
