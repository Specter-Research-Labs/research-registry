import Foundation
import Metal
import MLX

public enum LabGridPreset: Int, CaseIterable, Identifiable, Sendable {
    case compact128 = 128
    case standard256 = 256
    case expansive512 = 512

    public var id: Int { rawValue }
    public var size: Int { rawValue }
}

public enum SandboxTool: String, CaseIterable, Identifiable, Sendable {
    case creatureStamp = "Creature"
    case food = "Food"
    case wall = "Wall"
    case erase = "Erase"
    case mutation = "Mutation"

    public var id: String { rawValue }
}

public struct SandboxStroke: Sendable {
    public let tool: SandboxTool
    public let points: [SIMD2<Int>]
    public let radius: Int
    public let strength: Float

    public init(tool: SandboxTool, points: [SIMD2<Int>], radius: Int, strength: Float) {
        self.tool = tool
        self.points = points
        self.radius = radius
        self.strength = strength
    }
}

public struct SandboxRect: Sendable {
    public let x: Int
    public let y: Int
    public let width: Int
    public let height: Int

    public init(x: Int, y: Int, width: Int, height: Int) {
        self.x = x
        self.y = y
        self.width = width
        self.height = height
    }
}

public struct CreatureStamp: Identifiable, Hashable, Sendable {
    public let id: UUID
    public let name: String
    public let width: Int
    public let height: Int
    public let mass: [Float]
    public let params: [Float]
    public let parameterCount: Int

    public init(
        id: UUID = UUID(),
        name: String,
        width: Int,
        height: Int,
        mass: [Float],
        params: [Float],
        parameterCount: Int
    ) {
        self.id = id
        self.name = name
        self.width = width
        self.height = height
        self.mass = mass
        self.params = params
        self.parameterCount = parameterCount
    }
}

public struct FlowSandboxMetrics: Sendable {
    public let massMean: Float
    public let occupancy: Float
    public let foodMean: Float
    public let wallFraction: Float
    public let massPeak: Float
    public let foodPeak: Float
    public let nonFiniteFraction: Float

    public init(
        massMean: Float,
        occupancy: Float,
        foodMean: Float,
        wallFraction: Float,
        massPeak: Float,
        foodPeak: Float,
        nonFiniteFraction: Float
    ) {
        self.massMean = massMean
        self.occupancy = occupancy
        self.foodMean = foodMean
        self.wallFraction = wallFraction
        self.massPeak = massPeak
        self.foodPeak = foodPeak
        self.nonFiniteFraction = nonFiniteFraction
    }
}

public struct FlowSandboxRuntimeTelemetry: Sendable {
    public let lastStepDurationMs: Double
    public let realizedStepRateHz: Double

    public init(lastStepDurationMs: Double, realizedStepRateHz: Double) {
        self.lastStepDurationMs = lastStepDurationMs
        self.realizedStepRateHz = realizedStepRateHz
    }
}

public struct FlowSandboxKernelContract: Identifiable, Sendable {
    public let id: Int
    public let radius: Float
    public let center: Float
    public let sigma: Float
    public let gain: Float
    public let beta: [Float]
    public let weights: [Float]
    public let anchors: [Float]

    public init(
        id: Int,
        radius: Float,
        center: Float,
        sigma: Float,
        gain: Float,
        beta: [Float],
        weights: [Float],
        anchors: [Float]
    ) {
        self.id = id
        self.radius = radius
        self.center = center
        self.sigma = sigma
        self.gain = gain
        self.beta = beta
        self.weights = weights
        self.anchors = anchors
    }
}

public struct FlowSandboxWorldContract: Sendable {
    public let backend: FlowSandboxBackend
    public let gridSize: Int
    public let channels: Int
    public let parameterFieldMode: FlowLeniaParameterFieldMode
    public let parameterFieldCount: Int
    public let kernelCount: Int
    public let dt: Float
    public let dd: Int
    public let sigma: Float
    public let n: Int
    public let thetaA: Float
    public let border: String
    public let kernelProfile: String
    public let seed: Int
    public let radius: Float
    public let executionSummary: String
    public let fieldSummary: String
    public let featureSummary: String
    public let connectivitySummary: String
    public let kernels: [FlowSandboxKernelContract]

    public init(
        backend: FlowSandboxBackend,
        gridSize: Int,
        channels: Int,
        parameterFieldMode: FlowLeniaParameterFieldMode,
        parameterFieldCount: Int,
        kernelCount: Int,
        dt: Float,
        dd: Int,
        sigma: Float,
        n: Int,
        thetaA: Float,
        border: String,
        kernelProfile: String,
        seed: Int,
        radius: Float,
        executionSummary: String,
        fieldSummary: String,
        featureSummary: String,
        connectivitySummary: String,
        kernels: [FlowSandboxKernelContract]
    ) {
        self.backend = backend
        self.gridSize = gridSize
        self.channels = channels
        self.parameterFieldMode = parameterFieldMode
        self.parameterFieldCount = parameterFieldCount
        self.kernelCount = kernelCount
        self.dt = dt
        self.dd = dd
        self.sigma = sigma
        self.n = n
        self.thetaA = thetaA
        self.border = border
        self.kernelProfile = kernelProfile
        self.seed = seed
        self.radius = radius
        self.executionSummary = executionSummary
        self.fieldSummary = fieldSummary
        self.featureSummary = featureSummary
        self.connectivitySummary = connectivitySummary
        self.kernels = kernels
    }
}

public final class LeniaMetalFieldSurface: @unchecked Sendable {
    public let width: Int
    public let height: Int

    private enum Storage {
        case mlx(MLXArray)
        case metal(any MTLBuffer)
    }

    private let storage: Storage

    public init(field: MLXArray, width: Int, height: Int) {
        self.width = width
        self.height = height
        let contiguous = field.contiguous()
        eval(contiguous)
        self.storage = .mlx(contiguous)
    }

    public init(buffer: any MTLBuffer, width: Int, height: Int) {
        self.width = width
        self.height = height
        self.storage = .metal(buffer)
    }

    public func metalBuffer(on device: any MTLDevice, noCopy: Bool = true) -> (any MTLBuffer)? {
        switch storage {
        case .mlx(let field):
            field.asMTLBuffer(device: device, noCopy: noCopy)
        case .metal(let buffer):
            buffer.device.registryID == device.registryID ? buffer : nil
        }
    }
}

public struct FlowSandboxSnapshot: Sendable {
    public let step: Int
    public let width: Int
    public let height: Int
    public let bytes: Data?
    public let sharedField: LeniaMetalFieldSurface?
    public let metrics: FlowSandboxMetrics

    public init(
        step: Int,
        width: Int,
        height: Int,
        bytes: Data? = nil,
        sharedField: LeniaMetalFieldSurface? = nil,
        metrics: FlowSandboxMetrics
    ) {
        self.step = step
        self.width = width
        self.height = height
        self.bytes = bytes
        self.sharedField = sharedField
        self.metrics = metrics
    }
}

public struct FlowSandboxStateSnapshot: Sendable {
    public let step: Int
    public let width: Int
    public let height: Int
    public let mass: [Float]
    public let params: [Float]
    public let food: [Float]
    public let walls: [Float]

    public init(
        step: Int,
        width: Int,
        height: Int,
        mass: [Float],
        params: [Float],
        food: [Float],
        walls: [Float]
    ) {
        self.step = step
        self.width = width
        self.height = height
        self.mass = mass
        self.params = params
        self.food = food
        self.walls = walls
    }
}

public func buildWarmCreatureStamp(
    id: UUID = UUID(),
    name: String,
    params: ResolvedParams,
    seed: Int,
    warmupSteps: Int = 80,
    warmupGridSize: Int = 128,
    cropThreshold: Float = 0.05,
    padding: Int = 6
) -> CreatureStamp {
    let gridSize = max(32, warmupGridSize)
    let config = flowSandboxConfig(gridSize: gridSize, nbK: params.r.count)
    let c0 = Array(repeating: 0, count: params.r.count)
    let c1 = [Array(0..<params.r.count)]
    let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)
    let engine = FlowLeniaBatched(config: config, kernels: kernels)

    var state = flowSandboxSeedState(seed: seed, gridSize: gridSize)
    for _ in 0..<warmupSteps {
        state = engine.step(state)
    }
    eval(state)

    let mass = state[0, 0..., 0..., 0].asArray(Float.self)
    let bounds = creatureStampBounds(
        mass: mass,
        width: gridSize,
        height: gridSize,
        threshold: cropThreshold,
        padding: padding
    )

    let stampWidth = bounds.maxX - bounds.minX + 1
    let stampHeight = bounds.maxY - bounds.minY + 1
    var stampMass = [Float](repeating: 0, count: stampWidth * stampHeight)
    var stampParams = [Float](repeating: 0, count: stampWidth * stampHeight * params.h.count)

    for x in bounds.minX...bounds.maxX {
        for y in bounds.minY...bounds.maxY {
            let sourceIndex = x * gridSize + y
            let targetX = x - bounds.minX
            let targetY = y - bounds.minY
            let targetIndex = targetX * stampHeight + targetY
            let massValue = mass[sourceIndex]
            stampMass[targetIndex] = massValue
            let paramBase = targetIndex * params.h.count
            for k in 0..<params.h.count {
                stampParams[paramBase + k] = massValue > cropThreshold ? params.h[k] : 0
            }
        }
    }

    return CreatureStamp(
        id: id,
        name: name,
        width: stampWidth,
        height: stampHeight,
        mass: stampMass,
        params: stampParams,
        parameterCount: params.h.count
    )
}

public func buildSeedCreatureStamp(
    id: UUID = UUID(),
    name: String,
    params: ResolvedParams,
    seed: Int,
    gridSize: Int = 128,
    cropThreshold: Float = 0.05,
    padding: Int = 6
) -> CreatureStamp {
    let resolvedGridSize = max(32, gridSize)
    let mass = flowSandboxSeedStateValues(seed: seed, gridSize: resolvedGridSize)
    let bounds = creatureStampBounds(
        mass: mass,
        width: resolvedGridSize,
        height: resolvedGridSize,
        threshold: cropThreshold,
        padding: padding
    )

    let stampWidth = bounds.maxX - bounds.minX + 1
    let stampHeight = bounds.maxY - bounds.minY + 1
    var stampMass = [Float](repeating: 0, count: stampWidth * stampHeight)
    var stampParams = [Float](repeating: 0, count: stampWidth * stampHeight * params.h.count)

    for x in bounds.minX...bounds.maxX {
        for y in bounds.minY...bounds.maxY {
            let sourceIndex = x * resolvedGridSize + y
            let targetX = x - bounds.minX
            let targetY = y - bounds.minY
            let targetIndex = targetX * stampHeight + targetY
            let massValue = mass[sourceIndex]
            stampMass[targetIndex] = massValue
            let paramBase = targetIndex * params.h.count
            for k in 0..<params.h.count {
                stampParams[paramBase + k] = massValue > cropThreshold ? params.h[k] : 0
            }
        }
    }

    return CreatureStamp(
        id: id,
        name: name,
        width: stampWidth,
        height: stampHeight,
        mass: stampMass,
        params: stampParams,
        parameterCount: params.h.count
    )
}

public actor FlowSandboxRuntime {
    public let gridPreset: LabGridPreset
    public let params: ResolvedParams
    public let config: BatchedConfig
    public let backend: FlowSandboxBackend

    private let stepper: FlowSandboxStepper
    private let parameterCount: Int
    private let initialStamp: CreatureStamp?
    private let autoFoodSeed: Int
    private let metalState: FlowSandboxMetalRuntimeState?

    private var state: MLXArray
    private var paramState: MLXArray
    private var foodState: MLXArray
    private var wallMask: MLXArray

    private var simulationTask: Task<Void, Never>?
    private var isPaused = true
    private var stepCount = 0
    private var targetFrameDuration: Duration = .milliseconds(16)
    private var autoFoodEnabled = false
    private var autoFoodProbability: Float = 0.03
    private var autoFoodPatchSize = 12
    private var autoFoodValue: Float = 0.35
    private var lastStepDurationMs = 0.0
    private var cachedMetrics = FlowSandboxMetrics(
        massMean: 0,
        occupancy: 0,
        foodMean: 0,
        wallFraction: 0,
        massPeak: 0,
        foodPeak: 0,
        nonFiniteFraction: 0
    )
    private var metricsDirty = true

    public init(
        params: ResolvedParams,
        gridPreset: LabGridPreset = .standard256,
        initialStamp: CreatureStamp? = nil,
        backend: FlowSandboxBackend = .metalFull,
        autoFoodSeed: Int = 17
    ) {
        self.params = params
        self.gridPreset = gridPreset
        self.initialStamp = initialStamp
        self.backend = backend
        self.autoFoodSeed = autoFoodSeed
        self.parameterCount = params.h.count
        self.config = flowSandboxConfig(gridSize: gridPreset.size, nbK: params.r.count)

        let c0 = Array(repeating: 0, count: params.r.count)
        let c1 = [Array(0..<params.r.count)]
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)
        self.stepper = FlowSandboxStepper(
            backend: backend,
            config: config,
            kernels: kernels
        )
        self.metalState = backend == .metalFull
            ? FlowSandboxMetalRuntimeState(
                config: config,
                kernels: kernels,
                parameterCount: parameterCount,
                autoFoodSeed: autoFoodSeed
            )
            : nil

        let size = gridPreset.size
        self.state = MLX.zeros([1, size, size, 1])
        self.paramState = MLX.zeros([1, size, size, parameterCount])
        self.foodState = MLX.zeros([1, size, size])
        self.wallMask = MLX.ones([1, size, size, 1])
        self.stepCount = 0

        if let metalState {
            metalState.reset(initialStamp: initialStamp)
            cachedMetrics = metalState.materializeMetrics()
            metricsDirty = false
            return
        }

        if let initialStamp {
            eval(state, paramState, foodState, wallMask)
            var mass = state.asArray(Float.self)
            var paramsArray = paramState.asArray(Float.self)
            let food = foodState.asArray(Float.self)
            let walls = wallMask.asArray(Float.self)
            let center = SIMD2<Int>(size / 2, size / 2)
            let originX = center.x - (initialStamp.width / 2)
            let originY = center.y - (initialStamp.height / 2)
            for localX in 0..<initialStamp.width {
                for localY in 0..<initialStamp.height {
                    let worldX = originX + localX
                    let worldY = originY + localY
                    guard sandboxContains(x: worldX, y: worldY, size: config.sx) else { continue }
                    let stampIndex = localX * initialStamp.height + localY
                    let wallIndex = worldX * config.sy + worldY
                    guard walls[wallIndex] > 0.5 else { continue }

                    let massIndex = worldX * config.sy + worldY
                    mass[massIndex] = max(mass[massIndex], initialStamp.mass[stampIndex])
                    let paramBase = massIndex * parameterCount
                    let stampParamBase = stampIndex * parameterCount
                    if initialStamp.mass[stampIndex] > 0.01 {
                        for k in 0..<parameterCount {
                            paramsArray[paramBase + k] = initialStamp.params[stampParamBase + k]
                        }
                    }
                }
            }
            state = MLXArray(mass).reshaped([1, config.sx, config.sy, 1])
            paramState = MLXArray(paramsArray).reshaped([1, config.sx, config.sy, parameterCount])
            foodState = MLXArray(food).reshaped([1, config.sx, config.sy])
            wallMask = MLXArray(walls).reshaped([1, config.sx, config.sy, 1])
        }
        eval(state, paramState, foodState, wallMask)
        let initialMass = state[0, 0..., 0..., 0].asArray(Float.self)
        let initialFood = foodState[0, 0..., 0...].asArray(Float.self)
        let initialWalls = wallMask[0, 0..., 0..., 0].asArray(Float.self)
        cachedMetrics = computeMetrics(
            mass: initialMass,
            food: initialFood,
            walls: initialWalls
        )
        metricsDirty = false
    }

    deinit {
        simulationTask?.cancel()
    }

    public func start() {
        if simulationTask == nil {
            let runtime = self
            simulationTask = Task {
                await runtime.runLoop()
            }
        }
        isPaused = false
    }

    public func pause() {
        isPaused = true
    }

    public func resume() {
        start()
    }

    public func stop() {
        simulationTask?.cancel()
        simulationTask = nil
        isPaused = true
    }

    public func worldContract() -> FlowSandboxWorldContract {
        FlowSandboxWorldContract(
            backend: backend,
            gridSize: config.sx,
            channels: config.channels,
            parameterFieldMode: FlowLeniaParameterFieldMode.resolve(
                parameterFieldCount: parameterCount,
                kernelCount: config.nbK
            ),
            parameterFieldCount: parameterCount,
            kernelCount: config.nbK,
            dt: config.dt,
            dd: config.dd,
            sigma: config.sigma,
            n: config.n,
            thetaA: config.thetaA,
            border: config.border,
            kernelProfile: config.implementation.kernelProfile,
            seed: params.seed,
            radius: params.R,
            executionSummary: sandboxExecutionSummary(for: backend),
            fieldSummary: "\(config.channels) matter lane + \(parameterCount) parameter lanes + food scalar + wall mask",
            featureSummary: "food deposition, wall carving, erase restore, mutation brush, transported parameter field",
            connectivitySummary: "matter lane 0 -> 0 across \(config.nbK) kernels; parameter lanes advect with transported mass",
            kernels: params.r.indices.map { index in
                FlowSandboxKernelContract(
                    id: index,
                    radius: params.r[index],
                    center: params.m[index],
                    sigma: params.s[index],
                    gain: params.h[index],
                    beta: params.b[index],
                    weights: params.w[index],
                    anchors: params.a[index]
                )
            }
        )
    }

    public func setSpeedCap(hz: Int) {
        let clamped = max(1, min(240, hz))
        targetFrameDuration = .milliseconds(max(1, Int((1000.0 / Double(clamped)).rounded())))
    }

    public func setAutoFoodSpawn(enabled: Bool, probability: Float? = nil, patchSize: Int? = nil, value: Float? = nil) {
        autoFoodEnabled = enabled
        if let probability { autoFoodProbability = max(0, min(1, probability)) }
        if let patchSize { autoFoodPatchSize = max(1, min(config.sx, patchSize)) }
        if let value { autoFoodValue = max(0, value) }
    }

    public func reset() {
        resetState()
    }

    public func telemetry() -> FlowSandboxRuntimeTelemetry {
        FlowSandboxRuntimeTelemetry(
            lastStepDurationMs: lastStepDurationMs,
            realizedStepRateHz: lastStepDurationMs > 0 ? 1_000.0 / lastStepDurationMs : 0
        )
    }

    public func step() {
        if let metalState {
            metalState.step(
                stepCount: stepCount,
                autoFoodEnabled: autoFoodEnabled,
                autoFoodProbability: autoFoodProbability,
                autoFoodPatchSize: autoFoodPatchSize,
                autoFoodValue: autoFoodValue
            )
            stepCount += 1
            metricsDirty = true
            return
        }
        state = sandboxApplyWallMask(state, mask: wallMask)
        paramState = sandboxApplyWallMask(paramState, mask: wallMask)
        foodState = sandboxApplyWallMaskToField(foodState, mask: wallMask)

        let effectiveState = sandboxInjectFood(into: state, food: foodState)
        let stepped = stepper.step(effectiveState, paramState)
        state = sandboxApplyWallMask(MLX.clip(stepped.0, min: MLXArray(0.0), max: MLXArray(1.0)), mask: wallMask)
        paramState = sandboxApplyWallMask(stepped.1, mask: wallMask)
        updateFoodField()
        stepCount += 1
        metricsDirty = true
    }

    public func applyStroke(_ stroke: SandboxStroke) {
        guard !stroke.points.isEmpty else { return }
        if let metalState {
            metalState.applyStroke(stroke, stepCount: stepCount)
            metricsDirty = true
            return
        }
        let strokeMask = sandboxStrokeMask(
            points: stroke.points,
            radius: stroke.radius,
            size: config.sx
        )
        let strokeMask2D = strokeMask.squeezed(axis: 3)
        let invertedMask = MLXArray(1.0) - strokeMask
        let strokeParamMask = MLX.broadcast(strokeMask, to: [1, config.sx, config.sy, parameterCount])
        let invertedParamMask = MLXArray(1.0) - strokeParamMask

        switch stroke.tool {
        case .creatureStamp:
            return
        case .food:
            foodState = MLX.clip(
                foodState + strokeMask2D * MLXArray(stroke.strength),
                min: MLXArray(0.0),
                max: MLXArray(1.0)
            )
        case .wall:
            wallMask = wallMask * invertedMask
            state = state * invertedMask
            foodState = foodState * invertedMask.squeezed(axis: 3)
            paramState = paramState * invertedParamMask
        case .erase:
            wallMask = MLX.maximum(wallMask, strokeMask)
            state = state * invertedMask
            foodState = foodState * invertedMask.squeezed(axis: 3)
            paramState = paramState * invertedParamMask
        case .mutation:
            let noise = sandboxMutationNoise(
                points: stroke.points,
                radius: stroke.radius,
                strength: stroke.strength,
                step: stepCount,
                size: config.sx,
                parameterCount: parameterCount
            )
            paramState = MLX.clip(
                paramState + noise,
                min: MLXArray(-2.0),
                max: MLXArray(2.0)
            )
        }
        eval(state, paramState, foodState, wallMask)
        metricsDirty = true
    }

    public func applyFoodRect(_ rect: SandboxRect, value: Float) {
        let x0 = max(0, rect.x)
        let y0 = max(0, rect.y)
        let x1 = min(config.sx, rect.x + rect.width)
        let y1 = min(config.sy, rect.y + rect.height)
        guard x0 < x1, y0 < y1 else { return }
        let clampedValue = max(0, value)

        if let metalState {
            metalState.applyFoodRect(
                SandboxRect(x: x0, y: y0, width: x1 - x0, height: y1 - y0),
                value: clampedValue
            )
            metricsDirty = true
            return
        }

        eval(foodState, wallMask)
        var food = foodState.asArray(Float.self)
        let walls = wallMask[0, 0..., 0..., 0].asArray(Float.self)
        for x in x0..<x1 {
            for y in y0..<y1 {
                let index = x * config.sy + y
                guard walls[index] > 0.5 else { continue }
                food[index] = max(food[index], clampedValue)
            }
        }
        foodState = MLXArray(food).reshaped([1, config.sx, config.sy])
        eval(state, paramState, foodState, wallMask)
        metricsDirty = true
    }

    public func applyCreatureStamp(_ stamp: CreatureStamp, center: SIMD2<Int>) {
        guard stamp.parameterCount == parameterCount else {
            return
        }
        if let metalState {
            metalState.applyCreatureStamp(stamp, center: center)
            metricsDirty = true
            return
        }
        let patch = sandboxStampPatch(
            stamp: stamp,
            center: center,
            size: config.sx,
            parameterCount: parameterCount
        )
        let openSupport = patch.support * wallMask
        state = MLX.maximum(state, patch.mass * openSupport)
        let supportMask = MLX.broadcast(openSupport, to: [1, config.sx, config.sy, parameterCount])
        paramState = paramState * (MLXArray(1.0) - supportMask) + patch.params * supportMask
        eval(state, paramState)
        metricsDirty = true
    }

    public func snapshot(includeBytes: Bool = false, refreshMetrics: Bool = false) -> FlowSandboxSnapshot {
        if let metalState {
            if refreshMetrics {
                cachedMetrics = metalState.materializeMetrics()
                metricsDirty = false
            }
            return FlowSandboxSnapshot(
                step: stepCount,
                width: config.sx,
                height: config.sy,
                bytes: includeBytes ? metalState.frameBytes() : nil,
                sharedField: metalState.displaySurface(),
                metrics: cachedMetrics
            )
        }
        let displayField = sandboxDisplayField(
            mass: state[0, 0..., 0..., 0],
            food: foodState[0, 0..., 0...],
            walls: wallMask[0, 0..., 0..., 0]
        )
        let displaySnapshot = includeBytes || refreshMetrics ? materializeDisplaySnapshot() : nil
        if refreshMetrics, let displaySnapshot {
            cachedMetrics = computeMetrics(
                mass: displaySnapshot.mass,
                food: displaySnapshot.food,
                walls: displaySnapshot.walls
            )
            metricsDirty = false
        }
        return FlowSandboxSnapshot(
            step: stepCount,
            width: config.sx,
            height: config.sy,
            bytes: displaySnapshot.map { frameBytes(mass: $0.mass, food: $0.food, walls: $0.walls) },
            sharedField: LeniaMetalFieldSurface(
                field: displayField,
                width: config.sx,
                height: config.sy
            ),
            metrics: cachedMetrics
        )
    }

    public func materializeStateSnapshot() -> FlowSandboxStateSnapshot {
        if let metalState {
            return metalState.materializeStateSnapshot(step: stepCount)
        }
        eval(state, paramState, foodState, wallMask)
        return FlowSandboxStateSnapshot(
            step: stepCount,
            width: config.sx,
            height: config.sy,
            mass: state[0, 0..., 0..., 0].asArray(Float.self),
            params: paramState[0, 0..., 0..., 0...].asArray(Float.self),
            food: foodState[0, 0..., 0...].asArray(Float.self),
            walls: wallMask[0, 0..., 0..., 0].asArray(Float.self)
        )
    }

    func benchmarkSynchronize() {
        guard metalState == nil else { return }
        eval(state, paramState, foodState, wallMask)
    }

    private func runLoop() async {
        while !Task.isCancelled {
            if isPaused {
                try? await Task.sleep(for: .milliseconds(25))
                continue
            }

            let start = ContinuousClock.now
            step()
            let elapsed = ContinuousClock.now - start
            lastStepDurationMs = flowSandboxDurationMs(elapsed)
            let remaining = targetFrameDuration - elapsed
            if remaining > .zero {
                try? await Task.sleep(for: remaining)
            }
        }
    }

    private func resetState() {
        if let metalState {
            metalState.reset(initialStamp: initialStamp)
            stepCount = 0
            metricsDirty = true
            return
        }
        let size = config.sx
        state = MLX.zeros([1, size, size, 1])
        paramState = MLX.zeros([1, size, size, parameterCount])
        foodState = MLX.zeros([1, size, size])
        wallMask = MLX.ones([1, size, size, 1])
        stepCount = 0
        lastStepDurationMs = 0
        metricsDirty = true

        if let initialStamp {
            applyCreatureStamp(initialStamp, center: SIMD2<Int>(size / 2, size / 2))
        }
        eval(state, paramState, foodState, wallMask)
    }

    private func updateFoodField() {
        let massMap = state[0..., 0..., 0..., 0]
        foodState = MLX.maximum(foodState * MLXArray(0.996) - massMap * MLXArray(0.003), MLXArray(0.0))
        if autoFoodEnabled {
            foodState = spawnFoodPatch(
                food: foodState,
                probability: autoFoodProbability,
                patchSize: autoFoodPatchSize,
                value: autoFoodValue,
                step: stepCount,
                seed: autoFoodSeed
            )
        }
        foodState = sandboxApplyWallMaskToField(foodState, mask: wallMask)
    }

    private func materializeState(mass: [Float], params: [Float], food: [Float], walls: [Float]) {
        state = MLXArray(mass).reshaped([1, config.sx, config.sy, 1])
        paramState = MLXArray(params).reshaped([1, config.sx, config.sy, parameterCount])
        foodState = MLXArray(food).reshaped([1, config.sx, config.sy])
        wallMask = MLXArray(walls).reshaped([1, config.sx, config.sy, 1])
        eval(state, paramState, foodState, wallMask)
        metricsDirty = true
    }

    private func refreshCachedMetrics() {
        if let metalState {
            cachedMetrics = metalState.materializeMetrics()
            metricsDirty = false
            return
        }
        let displaySnapshot = materializeDisplaySnapshot()
        cachedMetrics = computeMetrics(
            mass: displaySnapshot.mass,
            food: displaySnapshot.food,
            walls: displaySnapshot.walls
        )
        metricsDirty = false
    }

    private func materializeDisplaySnapshot() -> (mass: [Float], food: [Float], walls: [Float]) {
        eval(state, foodState, wallMask)
        return (
            mass: state[0, 0..., 0..., 0].asArray(Float.self),
            food: foodState[0, 0..., 0...].asArray(Float.self),
            walls: wallMask[0, 0..., 0..., 0].asArray(Float.self)
        )
    }
}

private func sandboxExecutionSummary(for backend: FlowSandboxBackend) -> String {
    switch backend {
    case .mlx:
        return "MLX FlowLeniaParamsBatched"
    case .metalFull:
        return "Full Metal pipeline with GPU reintegration"
    }
}

func flowSandboxConfig(gridSize: Int, nbK: Int) -> BatchedConfig {
    BatchedConfig(
        sx: gridSize,
        sy: gridSize,
        channels: 1,
        nbK: nbK,
        dt: 0.2,
        dd: 5,
        sigma: 0.65,
        n: 2,
        thetaA: 2.0,
        border: "torus",
        implementation: ImplementationSettings(
            mode: "flowlenia_2022_paper_equations",
            border: "torus",
            gradientBoundary: "periodic",
            alphaMode: "mass",
            kernelProfile: "flowlenia_2022_paper_equations",
            flowClip: "none"
        ),
        chemChannel: nil,
        chemIncludeInMass: true
    )
}

func flowSandboxSeedStateValues(seed: Int, gridSize: Int) -> [Float] {
    var rng = SeededRandomNumberGenerator(seed: UInt64(seed + 1000))
    var data = [Float](repeating: 0, count: gridSize * gridSize)
    let center = gridSize / 2
    let radius = max(6, gridSize / 6)

    for x in 0..<gridSize {
        for y in 0..<gridSize {
            let dx = x - center
            let dy = y - center
            if dx * dx + dy * dy < radius * radius {
                data[x * gridSize + y] = Float.random(in: 0.5...1.0, using: &rng)
            }
        }
    }

    return data
}

func flowSandboxSeedState(seed: Int, gridSize: Int) -> MLXArray {
    let data = flowSandboxSeedStateValues(seed: seed, gridSize: gridSize)
    return MLXArray(data).reshaped([1, gridSize, gridSize, 1])
}

private func creatureStampBounds(
    mass: [Float],
    width: Int,
    height: Int,
    threshold: Float,
    padding: Int
) -> (minX: Int, maxX: Int, minY: Int, maxY: Int) {
    var minX = width - 1
    var maxX = 0
    var minY = height - 1
    var maxY = 0
    var found = false

    for x in 0..<width {
        for y in 0..<height {
            if mass[x * height + y] > threshold {
                minX = min(minX, x)
                maxX = max(maxX, x)
                minY = min(minY, y)
                maxY = max(maxY, y)
                found = true
            }
        }
    }

    if !found {
        return (0, width - 1, 0, height - 1)
    }

    return (
        max(0, minX - padding),
        min(width - 1, maxX + padding),
        max(0, minY - padding),
        min(height - 1, maxY + padding)
    )
}

private func sandboxApplyWallMask(_ array: MLXArray, mask: MLXArray) -> MLXArray {
    array * MLX.broadcast(mask, to: array.shape)
}

private func sandboxApplyWallMaskToField(_ field: MLXArray, mask: MLXArray) -> MLXArray {
    field * MLX.broadcast(mask.squeezed(axis: 3), to: field.shape)
}

private func sandboxInjectFood(into state: MLXArray, food: MLXArray) -> MLXArray {
    let foodExpanded = food.expandedDimensions(axis: -1)
    return MLX.clip(state + foodExpanded * MLXArray(0.12), min: MLXArray(0.0), max: MLXArray(1.0))
}

private func spawnFoodPatch(
    food: MLXArray,
    probability: Float,
    patchSize: Int,
    value: Float,
    step: Int,
    seed: Int
) -> MLXArray {
    let batch = food.shape[0]
    let sx = food.shape[1]
    let sy = food.shape[2]
    eval(food)
    var values = food.asArray(Float.self)
    var rng = SeededRandomNumberGenerator(seed: UInt64(seed) + UInt64(step))
    let maxX = max(0, sx - patchSize)
    let maxY = max(0, sy - patchSize)
    for b in 0..<batch {
        if Float.random(in: 0..<1, using: &rng) >= probability {
            continue
        }
        let x0 = Int.random(in: 0...maxX, using: &rng)
        let y0 = Int.random(in: 0...maxY, using: &rng)
        for x in x0..<(x0 + patchSize) {
            for y in y0..<(y0 + patchSize) {
                let index = b * sx * sy + x * sy + y
                values[index] = max(values[index], value)
            }
        }
    }
    return MLXArray(values).reshaped([batch, sx, sy])
}

private func sandboxStrokeMask(points: [SIMD2<Int>], radius: Int, size: Int) -> MLXArray {
    var values = [Float](repeating: 0, count: size * size)
    for point in points {
        for cell in rasterizedCells(around: point, radius: radius) {
            guard sandboxContains(cell: cell, size: size) else { continue }
            values[cell.x * size + cell.y] = 1
        }
    }
    return MLXArray(values).reshaped([1, size, size, 1])
}

private func sandboxMutationNoise(
    points: [SIMD2<Int>],
    radius: Int,
    strength: Float,
    step: Int,
    size: Int,
    parameterCount: Int
) -> MLXArray {
    var values = [Float](repeating: 0, count: size * size * parameterCount)
    for point in points {
        for cell in rasterizedCells(around: point, radius: radius) {
            guard sandboxContains(cell: cell, size: size) else { continue }
            var generator = SeededRandomNumberGenerator(
                seed: UInt64(step &* 131) ^ UInt64((cell.x + 1) &* 977) ^ UInt64((cell.y + 1) &* 6151)
            )
            let baseIndex = (cell.x * size + cell.y) * parameterCount
            for k in 0..<parameterCount {
                values[baseIndex + k] += gaussian(mean: 0, std: strength * 0.15, rng: &generator)
            }
        }
    }
    return MLXArray(values).reshaped([1, size, size, parameterCount])
}

private func sandboxStampPatch(
    stamp: CreatureStamp,
    center: SIMD2<Int>,
    size: Int,
    parameterCount: Int
) -> (mass: MLXArray, params: MLXArray, support: MLXArray) {
    var massValues = [Float](repeating: 0, count: size * size)
    var paramValues = [Float](repeating: 0, count: size * size * parameterCount)
    var supportValues = [Float](repeating: 0, count: size * size)

    let originX = center.x - (stamp.width / 2)
    let originY = center.y - (stamp.height / 2)
    for localX in 0..<stamp.width {
        for localY in 0..<stamp.height {
            let worldX = originX + localX
            let worldY = originY + localY
            guard sandboxContains(x: worldX, y: worldY, size: size) else { continue }
            let stampIndex = localX * stamp.height + localY
            let massValue = stamp.mass[stampIndex]
            guard massValue > 0 else { continue }

            let cellIndex = worldX * size + worldY
            massValues[cellIndex] = max(massValues[cellIndex], massValue)
            if massValue > 0.01 {
                supportValues[cellIndex] = 1
                let paramBase = cellIndex * parameterCount
                let stampParamBase = stampIndex * parameterCount
                for k in 0..<parameterCount {
                    paramValues[paramBase + k] = stamp.params[stampParamBase + k]
                }
            }
        }
    }

    return (
        mass: MLXArray(massValues).reshaped([1, size, size, 1]),
        params: MLXArray(paramValues).reshaped([1, size, size, parameterCount]),
        support: MLXArray(supportValues).reshaped([1, size, size, 1])
    )
}

private func rasterizedCells(around point: SIMD2<Int>, radius: Int) -> [GridCell] {
    guard radius > 0 else {
        return [GridCell(x: point.x, y: point.y)]
    }
    var cells: [GridCell] = []
    let radiusSquared = radius * radius
    for dx in -radius...radius {
        for dy in -radius...radius where (dx * dx + dy * dy) <= radiusSquared {
            cells.append(GridCell(x: point.x + dx, y: point.y + dy))
        }
    }
    return cells
}

private func computeMetrics(mass: [Float], food: [Float], walls: [Float]) -> FlowSandboxMetrics {
    let count = Float(max(1, mass.count))
    let finiteMass = mass.filter(\.isFinite)
    let finiteFood = food.filter(\.isFinite)
    let nonFiniteCount = mass.count - finiteMass.count + food.count - finiteFood.count
    let occupied = Float(finiteMass.filter { $0 > 0.05 }.count)
    let wallCount = Float(walls.filter { $0 < 0.5 }.count)
    return FlowSandboxMetrics(
        massMean: finiteMass.reduce(0, +) / count,
        occupancy: occupied / count,
        foodMean: finiteFood.reduce(0, +) / count,
        wallFraction: wallCount / count,
        massPeak: finiteMass.max() ?? 0,
        foodPeak: finiteFood.max() ?? 0,
        nonFiniteFraction: Float(nonFiniteCount) / max(1.0, Float(mass.count + food.count))
    )
}

private func frameBytes(mass: [Float], food: [Float], walls: [Float]) -> Data {
    var bytes = [UInt8](repeating: 0, count: mass.count)
    for index in 0..<mass.count {
        if walls[index] < 0.5 {
            bytes[index] = 0
            continue
        }
        let displayValue = min(1.0, max(0.0, mass[index] + food[index] * 0.55))
        bytes[index] = UInt8(displayValue * 255.0)
    }
    return Data(bytes)
}

private func sandboxDisplayField(mass: MLXArray, food: MLXArray, walls: MLXArray) -> MLXArray {
    let display = MLX.clip(
        mass + food * MLXArray(0.55),
        min: MLXArray(0.0),
        max: MLXArray(1.0)
    )
    return (display * walls).contiguous()
}

private struct GridCell {
    let x: Int
    let y: Int
}

private func sandboxContains(cell: GridCell, size: Int) -> Bool {
    sandboxContains(x: cell.x, y: cell.y, size: size)
}

private func sandboxContains(x: Int, y: Int, size: Int) -> Bool {
    x >= 0 && y >= 0 && x < size && y < size
}

private func gaussian(mean: Float, std: Float, rng: inout SeededRandomNumberGenerator) -> Float {
    mean + gaussianSample(std: std, rng: &rng)
}
