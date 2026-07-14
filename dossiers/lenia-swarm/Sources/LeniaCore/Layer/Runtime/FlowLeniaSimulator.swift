import Foundation
import Logging
import MLX

public struct LeniaRolloutResult: Sendable {
    public let finalMassMap: [Float]
    public let width: Int
    public let height: Int
    public let finalMass: Float
    public let finalCenterX: Float
    public let finalCenterY: Float
    public let activitySnapshots: [ActivitySnapshot]
    public let activitySummary: ActivitySummary?
    public let recordedFrames: [LeniaTrajectoryFrame]
    // Per captured frame, a normalized 2D projection of the local parameter
    // vector (row-major, 2 components per cell). Populated only when
    // captureParameters is set. Transient (not persisted); drives the species map.
    public let parameterSeeds: [[Float]]?

    public init(
        finalMassMap: [Float],
        width: Int,
        height: Int,
        finalMass: Float,
        finalCenterX: Float,
        finalCenterY: Float,
        activitySnapshots: [ActivitySnapshot],
        activitySummary: ActivitySummary?,
        recordedFrames: [LeniaTrajectoryFrame],
        parameterSeeds: [[Float]]? = nil
    ) {
        self.finalMassMap = finalMassMap
        self.width = width
        self.height = height
        self.finalMass = finalMass
        self.finalCenterX = finalCenterX
        self.finalCenterY = finalCenterY
        self.activitySnapshots = activitySnapshots
        self.activitySummary = activitySummary
        self.recordedFrames = recordedFrames
        self.parameterSeeds = parameterSeeds
    }
}

public struct FlowLeniaFoodSpawnConfig: Codable, Sendable {
    public let probability: Float
    public let patchSize: Int
    public let seed: Int
    public let value: Float

    enum CodingKeys: String, CodingKey {
        case probability
        case patchSize = "patch_size"
        case seed
        case value
    }

    public init(probability: Float, patchSize: Int, seed: Int, value: Float) {
        self.probability = probability
        self.patchSize = patchSize
        self.seed = seed
        self.value = value
    }
}

public struct FlowLeniaDissipationConfig: Codable, Sendable {
    public let probability: Float
    public let patchSize: Int
    public let insertionZoneOrigin: [Int]
    public let insertionZoneSize: Int
    public let seed: Int

    enum CodingKeys: String, CodingKey {
        case probability
        case patchSize = "patch_size"
        case insertionZoneOrigin = "insertion_zone_origin"
        case insertionZoneSize = "insertion_zone_size"
        case seed
    }

    public init(
        probability: Float,
        patchSize: Int,
        insertionZoneOrigin: [Int],
        insertionZoneSize: Int,
        seed: Int
    ) {
        self.probability = probability
        self.patchSize = patchSize
        self.insertionZoneOrigin = insertionZoneOrigin
        self.insertionZoneSize = insertionZoneSize
        self.seed = seed
    }
}

public struct FlowLeniaRolloutConfig: Sendable {
    public let steps: Int
    public let recordEverySteps: Int
    public let captureEverySteps: Int?
    public let activityConfig: ActivityConfig?
    public let foodSpawn: FlowLeniaFoodSpawnConfig?
    public let dissipation: FlowLeniaDissipationConfig?
    public let logger: Logger?
    public let captureParameters: Bool

    public init(
        steps: Int,
        recordEverySteps: Int,
        captureEverySteps: Int?,
        activityConfig: ActivityConfig?,
        foodSpawn: FlowLeniaFoodSpawnConfig?,
        dissipation: FlowLeniaDissipationConfig?,
        logger: Logger? = nil,
        captureParameters: Bool = false
    ) {
        self.steps = steps
        self.recordEverySteps = recordEverySteps
        self.captureEverySteps = captureEverySteps
        self.activityConfig = activityConfig
        self.foodSpawn = foodSpawn
        self.dissipation = dissipation
        self.logger = logger
        self.captureParameters = captureParameters
    }
}

public final class FlowLeniaSimulator {
    private enum Stepper {
        case mlx(FlowLeniaBatched)
        case mlxParams(FlowLeniaParamsBatched)

        func step(_ mass: MLXArray, _ params: MLXArray?) -> (MLXArray, MLXArray?) {
            switch self {
            case .mlx(let engine):
                return (engine.step(mass), nil)
            case .mlxParams(let engine):
                guard let params else {
                    preconditionFailure("FlowLeniaSimulator mlx parameter backend requires an embedded parameter field.")
                }
                let stepped = engine.step(mass, params)
                return (stepped.0, stepped.1)
            }
        }
    }

    private struct RuntimePlan {
        let backend: FlowLeniaComputeBackend
        let parameterFieldMode: FlowLeniaParameterFieldMode
        let parameterMix: String
        let parameterMixSeed: Int?

        init(runtimeConfig: LeniaRuntimeConfig) {
            self.backend = runtimeConfig.backend
            self.parameterFieldMode = FlowLeniaParameterFieldMode.fromEmbeddingEnabled(
                runtimeConfig.parameterEmbedding.enabled
            )
            self.parameterMix = runtimeConfig.parameterEmbedding.mix
            self.parameterMixSeed = runtimeConfig.parameterEmbedding.mix_seed
            if runtimeConfig.backend == .metalFull {
                FlowLeniaSimulator.validateMetalBackendCompatibility(runtimeConfig: runtimeConfig)
            }
        }

        func makeStepper(
            context: FlowLeniaRuntimeContext,
            kernels: CompiledKernels,
            crossMapPotential: MLXArray?
        ) -> Stepper? {
            switch backend {
            case .mlx:
                if parameterFieldMode != .none {
                    return .mlxParams(
                        FlowLeniaParamsBatched(
                            config: context.batchedConfig,
                            kernels: kernels,
                            mixMode: parameterMix,
                            mixSeed: parameterMixSeed,
                            wallPotential: crossMapPotential
                        )
                    )
                }
                return .mlx(
                    FlowLeniaBatched(
                        config: context.batchedConfig,
                        kernels: kernels,
                        wallPotential: crossMapPotential
                    )
                )
            case .metalFull:
                return nil
            }
        }

        func makeCachedMetalRunner(
            context: FlowLeniaRuntimeContext,
            kernels: CompiledKernels,
            crossMapPotential: MLXArray?
        ) -> FlowLeniaMetalFullStateRunner? {
            guard backend == .metalFull else {
                return nil
            }
            return FlowLeniaMetalFullStateRunner(
                config: context.batchedConfig,
                kernels: kernels,
                batchCount: 1,
                wallPotential: crossMapPotential,
                parameterFieldMode: parameterFieldMode,
                parameterMix: parameterMix,
                mixSeed: parameterMixSeed
            )
        }
    }

    private let runtimeConfig: LeniaRuntimeConfig
    private let context: FlowLeniaRuntimeContext
    private let stepper: Stepper?
    private let cachedMetalFullRunner: FlowLeniaMetalFullStateRunner?

    public init(runtimeConfig: LeniaRuntimeConfig) {
        self.runtimeConfig = runtimeConfig
        let context = FlowLeniaRuntimeContext(runtimeConfig: runtimeConfig)
        self.context = context
        let kernels = context.kernels
        let crossMapPotential = context.preparedFields.environmentPotential
        let runtimePlan = RuntimePlan(runtimeConfig: runtimeConfig)
        self.cachedMetalFullRunner = runtimePlan.makeCachedMetalRunner(
            context: context,
            kernels: kernels,
            crossMapPotential: crossMapPotential
        )
        self.stepper = runtimePlan.makeStepper(
            context: context,
            kernels: kernels,
            crossMapPotential: crossMapPotential
        )
    }

    public func rollout(
        initialState: MLXArray,
        initialParams: MLXArray?,
        initialFood: MLXArray?,
        config: FlowLeniaRolloutConfig
    ) -> LeniaRolloutResult {
        let runtimeOperators = context.runtimeOperators
        var ABatch = initialState.expandedDimensions(axis: 0)
        var PBatch = initialParams?.expandedDimensions(axis: 0)
        var foodBatch = initialFood?.expandedDimensions(axis: 0)
        let wallMask = context.preparedFields.wallMask
        let chemField = context.preparedFields.chemField

        let persistentMetalRunner: FlowLeniaMetalFullStateRunner?
        if runtimeConfig.backend == .metalFull {
            if config.foodSpawn != nil && foodBatch == nil {
                fatalError("FlowLeniaSimulator backend=metal-full requires an initial food field when foodSpawn is configured.")
            }
            guard let params = PBatch else {
                fatalError("FlowLeniaSimulator full-metal runner requires embedded parameter fields.")
            }
            let parameterFieldCount = params.shape[3]
            let runner: FlowLeniaMetalFullStateRunner
            if let cachedMetalFullRunner,
               cachedMetalFullRunner.parameterCount == parameterFieldCount {
                runner = cachedMetalFullRunner
            } else {
                let parameterFieldMode = FlowLeniaParameterFieldMode.resolve(
                    parameterFieldCount: parameterFieldCount,
                    kernelCount: context.runtimeConfig.nbK
                )
                runner = FlowLeniaMetalFullStateRunner(
                    config: context.batchedConfig,
                    kernels: context.kernels,
                    batchCount: 1,
                    wallPotential: context.preparedFields.environmentPotential,
                    parameterFieldMode: parameterFieldMode,
                    parameterMix: runtimeConfig.parameterEmbedding.mix,
                    mixSeed: runtimeConfig.parameterEmbedding.mix_seed
                )
            }
            runner.setMatterWeights(runtimeOperators.matterWeights())
            runner.reset(
                mass: ABatch,
                params: params,
                wallMask: wallMask,
                staticChannelFields: runtimeOperators.metalStaticChannelFields(chemField: chemField),
                food: runtimeOperators.metalFoodState(foodBatch: foodBatch)
            )
            persistentMetalRunner = runner
        } else {
            runtimeOperators.applyWallMaskIfNeeded(
                massBatch: &ABatch,
                paramBatch: &PBatch,
                foodBatch: &foodBatch,
                wallMask: wallMask
            )
            persistentMetalRunner = nil
        }

        var recordedFrames: [LeniaTrajectoryFrame] = []
        var parameterSeeds: [[Float]] = []
        var parameterProjection: MLXArray?
        var summarizer = ActivitySummarizer()
        let progressInterval = max(config.recordEverySteps * 100, 10_000)
        var pendingMetalSteps = 0
        var pendingMetalStartStep = 1
        var finalObservedMassMap: MLXArray?

        for step in 1...config.steps {
            if persistentMetalRunner != nil {
                if pendingMetalSteps == 0 {
                    pendingMetalStartStep = step
                }
                pendingMetalSteps += 1
            } else {
                guard let stepper else {
                    fatalError("FlowLeniaSimulator backend=metal-full requires the persistent Metal runner path.")
                }
                runtimeOperators.applyPreStepFields(
                    massBatch: &ABatch,
                    foodBatch: foodBatch,
                    chemField: chemField
                )

                let stepped = stepper.step(ABatch, PBatch)
                ABatch = stepped.0
                PBatch = stepped.1

                runtimeOperators.applyBeamMutationIfNeeded(paramBatch: &PBatch, step: step)
                runtimeOperators.applyDissipationIfNeeded(
                    massBatch: &ABatch,
                    paramBatch: &PBatch,
                    config: config.dissipation,
                    step: step
                )
                runtimeOperators.applyFoodStepIfNeeded(
                    massBatch: &ABatch,
                    foodBatch: &foodBatch,
                    foodSpawn: config.foodSpawn,
                    step: step
                )
                runtimeOperators.applyWallMaskIfNeeded(
                    massBatch: &ABatch,
                    paramBatch: &PBatch,
                    foodBatch: &foodBatch,
                    wallMask: wallMask
                )

                if step % 20 == 0 {
                    eval(ABatch)
                    if let params = PBatch {
                        eval(params)
                    }
                    if let food = foodBatch {
                        eval(food)
                    }
                }
            }

            if let logger = config.logger,
               (step == 1 || step % progressInterval == 0 || step == config.steps) {
                logger.info("FlowLenia rollout progress step=\(step)/\(config.steps)")
            }

            let shouldRecord = step % config.recordEverySteps == 0 || step == config.steps
            let shouldCapture = config.captureEverySteps.map { step % $0 == 0 || step == config.steps } ?? false
            let shouldMeasureActivity = shouldRecord && config.activityConfig != nil
            if !shouldCapture && !shouldMeasureActivity {
                continue
            }

            if let runner = persistentMetalRunner {
                flushPendingMetalSteps(
                    runner: runner,
                    pendingMetalSteps: &pendingMetalSteps,
                    pendingMetalStartStep: pendingMetalStartStep,
                    config: config,
                    runtimeOperators: runtimeOperators
                )
                if shouldMeasureActivity {
                    PBatch = runner.materializeParams()
                }
            }

            let massMap: MLXArray
            let capturedFood: MLXArray?
            if let runner = persistentMetalRunner {
                massMap = runner.materializeMassMap(channelWeights: runtimeOperators.matterWeights())
                capturedFood = shouldCapture ? runner.materializeFood() : nil
            } else {
                massMap = runtimeOperators.matterMapFromBatch(ABatch)
                capturedFood = shouldCapture ? foodBatch : nil
            }
            if step == config.steps {
                finalObservedMassMap = massMap
            }

            if shouldCapture {
                let massCPU = massMap.asArray(Float.self)
                let bytes = runtimeOperators.frameDataFromMassMap(massCPU)
                let foodBytes = capturedFood.map { runtimeOperators.frameDataFromScalarField($0[0, 0..., 0...].asArray(Float.self)) }
                recordedFrames.append(LeniaTrajectoryFrame(
                    step: step,
                    width: runtimeConfig.sx,
                    height: runtimeConfig.sy,
                    bytes: bytes,
                    foodBytes: foodBytes
                ))
                if config.captureParameters {
                    let paramField: MLXArray
                    if let runner = persistentMetalRunner {
                        paramField = runner.materializeParams()
                    } else if let params = PBatch {
                        paramField = params
                    } else {
                        fatalError("captureParameters requires embedded parameter fields.")
                    }
                    parameterSeeds.append(projectParameterSeed(
                        paramField,
                        cellCount: runtimeConfig.sx * runtimeConfig.sy,
                        projection: &parameterProjection
                    ))
                }
            }

            if shouldMeasureActivity, let params = PBatch, let activityConfig = config.activityConfig {
                let activity = computeActivitySnapshots(
                    massMap: massMap,
                    paramMap: params,
                    step: step,
                    config: activityConfig,
                    border: runtimeConfig.border
                )
                if let snapshot = activity.first {
                    summarizer.record(snapshot: snapshot, config: activityConfig)
                }
            }
        }

        if let runner = persistentMetalRunner {
            flushPendingMetalSteps(
                runner: runner,
                pendingMetalSteps: &pendingMetalSteps,
                pendingMetalStartStep: pendingMetalStartStep,
                config: config,
                runtimeOperators: runtimeOperators
            )
        }
        let finalMassMap = if let finalObservedMassMap {
            finalObservedMassMap
        } else if let runner = persistentMetalRunner {
            runner.materializeMassMap(channelWeights: runtimeOperators.matterWeights())
        } else {
            runtimeOperators.matterMapFromBatch(ABatch)
        }
        eval(finalMassMap)
        let finalMassCPU = finalMassMap.asArray(Float.self)
        let finalCenter = runtimeOperators.centerOfMass(finalMassCPU, width: runtimeConfig.sx, height: runtimeConfig.sy)
        let finalMass = finalMassCPU.reduce(0, +)
        let activitySummary = config.activityConfig.map { _ in summarizer.summary() }

        return LeniaRolloutResult(
            finalMassMap: finalMassCPU,
            width: runtimeConfig.sx,
            height: runtimeConfig.sy,
            finalMass: finalMass,
            finalCenterX: finalCenter.x,
            finalCenterY: finalCenter.y,
            activitySnapshots: [],
            activitySummary: activitySummary,
            recordedFrames: recordedFrames,
            parameterSeeds: config.captureParameters ? parameterSeeds : nil
        )
    }

    private func flushPendingMetalSteps(
        runner: FlowLeniaMetalFullStateRunner,
        pendingMetalSteps: inout Int,
        pendingMetalStartStep: Int,
        config: FlowLeniaRolloutConfig,
        runtimeOperators: FlowLeniaRuntimeOperators
    ) {
        guard pendingMetalSteps > 0 else {
            return
        }

        runner.step(
            count: pendingMetalSteps,
            preStepParameterPatches: [:],
            postStepParameterPatches: runtimeOperators.beamMutationPatchSchedule(
                startStep: pendingMetalStartStep,
                count: pendingMetalSteps,
                batch: runner.batchCount,
                parameterCount: runner.parameterCount,
                config: runtimeConfig.beamMutation,
                sx: runtimeConfig.sx,
                sy: runtimeConfig.sy
            ),
            postStepScalarPatches: runtimeOperators.foodSpawnPatchSchedule(
                startStep: pendingMetalStartStep,
                count: pendingMetalSteps,
                batch: runner.batchCount,
                config: config.foodSpawn,
                sx: runtimeConfig.sx,
                sy: runtimeConfig.sy
            ),
            postStepDissipationPatches: runtimeOperators.dissipationPatchSchedule(
                startStep: pendingMetalStartStep,
                count: pendingMetalSteps,
                batch: runner.batchCount,
                massChannels: runtimeConfig.channels,
                parameterCount: runner.parameterCount,
                config: config.dissipation,
                sx: runtimeConfig.sx,
                sy: runtimeConfig.sy
            )
        )
        pendingMetalSteps = 0
    }

    // Project the per-cell parameter vector onto a fixed 2D basis and
    // standardize, so distinct local rules (species) land at distinct angles.
    // The species map colors by this angle. Returns row-major [cellCount * 2].
    private func projectParameterSeed(
        _ paramField: MLXArray,
        cellCount: Int,
        projection: inout MLXArray?
    ) -> [Float] {
        let parameterCount = paramField.shape[3]
        if projection == nil {
            var basis = [Float](repeating: 0, count: parameterCount * 2)
            for i in 0..<parameterCount {
                basis[i * 2 + 0] = sin(Float(i) * 12.9898 + 0.5)
                basis[i * 2 + 1] = cos(Float(i) * 78.233 + 1.3)
            }
            projection = MLXArray(basis).reshaped([parameterCount, 2])
        }
        let flat = paramField[0].reshaped([cellCount, parameterCount])
        var seed = MLX.matmul(flat, projection!)
        let mean = seed.mean(axes: [0])
        let centered = seed - mean
        let std = MLX.sqrt((centered * centered).mean(axes: [0])) + MLXArray(Float(1e-5))
        seed = centered / std
        eval(seed)
        return seed.asArray(Float.self)
    }

    private static func validateMetalBackendCompatibility(
        runtimeConfig: LeniaRuntimeConfig
    ) {
        guard runtimeConfig.parameterEmbedding.enabled else {
            fatalError("FlowLeniaSimulator Metal backends require parameter_embedding.enabled=true.")
        }
        let allowedMetalMixes: Set<String> = ["avg", "stoch"]
        guard allowedMetalMixes.contains(runtimeConfig.parameterEmbedding.mix) else {
            fatalError("FlowLeniaSimulator Metal backends currently require parameter_embedding.mix avg or stoch.")
        }
        guard runtimeConfig.border == "torus" || runtimeConfig.border == "wall" else {
            fatalError("FlowLeniaSimulator Metal backends require border torus or wall.")
        }
        guard runtimeConfig.implementation.gradientBoundary == "periodic" || runtimeConfig.implementation.gradientBoundary == "zero_pad" else {
            fatalError("FlowLeniaSimulator Metal backends require implementation.gradientBoundary periodic or zero_pad.")
        }
    }

}

public struct FlowLeniaInteractiveState {
    public let step: Int
    public let mass: MLXArray
    public let params: MLXArray?
    public let food: MLXArray?

    public init(
        step: Int,
        mass: MLXArray,
        params: MLXArray?,
        food: MLXArray?
    ) {
        self.step = step
        self.mass = mass
        self.params = params
        self.food = food
    }
}

public final class FlowLeniaInteractiveSimulator {
    public let runtimeConfig: LeniaRuntimeConfig
    public let batchedConfig: BatchedConfig
    public let kernels: CompiledKernels

    private let massEngine: FlowLeniaBatched
    private let paramsEngine: FlowLeniaParamsBatched?
    private let wallMask: MLXArray?
    private let chemField: MLXArray?
    private let runtimeOperators: FlowLeniaRuntimeOperators

    public init(runtimeConfig: LeniaRuntimeConfig) {
        self.runtimeConfig = runtimeConfig
        let context = FlowLeniaRuntimeContext(runtimeConfig: runtimeConfig)
        self.batchedConfig = context.batchedConfig
        self.runtimeOperators = context.runtimeOperators
        self.kernels = context.kernels
        let environmentPotential = context.preparedFields.environmentPotential

        self.massEngine = FlowLeniaBatched(
            config: batchedConfig,
            kernels: kernels,
            wallPotential: environmentPotential
        )
        self.paramsEngine = runtimeConfig.parameterEmbedding.enabled
            ? FlowLeniaParamsBatched(
                config: batchedConfig,
                kernels: kernels,
                mixMode: runtimeConfig.parameterEmbedding.mix,
                mixSeed: runtimeConfig.parameterEmbedding.mix_seed,
                wallPotential: environmentPotential
            )
            : nil

        self.wallMask = context.preparedFields.wallMask
        self.chemField = context.preparedFields.chemField
    }

    public func makeInitialState(seedOverride: Int? = nil) -> FlowLeniaInteractiveState {
        let seed = seedOverride ?? runtimeConfig.initSeed
        var mass = flowLeniaBuildInteractiveInitialState(runtimeConfig: runtimeConfig, seed: seed)
        var params = flowLeniaBuildInteractiveInitialParams(runtimeConfig: runtimeConfig, seed: seed + 1_000_000)
        var food = flowLeniaBuildInteractiveInitialFoodState(runtimeConfig: runtimeConfig, seed: seed + 2_000_000)

        var massBatch = mass.expandedDimensions(axis: 0)
        var paramsBatch = params?.expandedDimensions(axis: 0)
        var foodBatch = food?.expandedDimensions(axis: 0)
        runtimeOperators.applyWallMaskIfNeeded(
            massBatch: &massBatch,
            paramBatch: &paramsBatch,
            foodBatch: &foodBatch,
            wallMask: wallMask
        )
        mass = massBatch.squeezed(axis: 0)
        params = paramsBatch?.squeezed(axis: 0)
        food = foodBatch?.squeezed(axis: 0)

        eval(mass)
        if let params { eval(params) }
        if let food { eval(food) }

        return FlowLeniaInteractiveState(
            step: 0,
            mass: mass,
            params: params,
            food: food
        )
    }

    public func step(_ state: FlowLeniaInteractiveState) -> FlowLeniaInteractiveState {
        var massBatch = state.mass.expandedDimensions(axis: 0)
        var paramsBatch = state.params?.expandedDimensions(axis: 0)
        var foodBatch = state.food?.expandedDimensions(axis: 0)
        let step = state.step + 1

        runtimeOperators.applyPreStepFields(
            massBatch: &massBatch,
            foodBatch: foodBatch,
            chemField: chemField
        )

        if let paramsEngine {
            guard let currentParamsBatch = paramsBatch else {
                fatalError("FlowLeniaInteractiveSimulator parameter embedding requires an initial parameter field.")
            }
            let stepped = paramsEngine.step(massBatch, currentParamsBatch)
            massBatch = stepped.0
            paramsBatch = stepped.1
        } else {
            massBatch = massEngine.step(massBatch)
        }

        runtimeOperators.applyBeamMutationIfNeeded(paramBatch: &paramsBatch, step: step)
        runtimeOperators.applyFoodStepIfNeeded(
            massBatch: &massBatch,
            foodBatch: &foodBatch,
            foodSpawn: nil,
            step: step
        )
        runtimeOperators.applyWallMaskIfNeeded(
            massBatch: &massBatch,
            paramBatch: &paramsBatch,
            foodBatch: &foodBatch,
            wallMask: wallMask
        )

        eval(massBatch)
        if let paramsBatch { eval(paramsBatch) }
        if let foodBatch { eval(foodBatch) }

        return FlowLeniaInteractiveState(
            step: step,
            mass: massBatch.squeezed(axis: 0),
            params: paramsBatch?.squeezed(axis: 0),
            food: foodBatch?.squeezed(axis: 0)
        )
    }

    public func matterMap(for state: FlowLeniaInteractiveState) -> MLXArray {
        runtimeOperators.matterMapFromBatch(state.mass.expandedDimensions(axis: 0))
    }

    public func channelMap(for state: FlowLeniaInteractiveState, channel: Int) -> MLXArray {
        precondition(channel >= 0 && channel < runtimeConfig.channels, "Channel \(channel) is out of bounds for \(runtimeConfig.channels)-channel runtime.")
        return state.mass[0..., 0..., channel].contiguous()
    }

    public func wallMaskMap() -> MLXArray? {
        wallMask?[0, 0..., 0..., 0].contiguous()
    }

    public func diagnostics(for state: FlowLeniaInteractiveState) -> LeniaDiagnosticsFrame {
        computeLeniaDiagnostics(
            state: state.mass.expandedDimensions(axis: 0),
            params: runtimeConfig.params,
            config: batchedConfig,
            kernels: kernels
        )
    }
}

private func flowLeniaBuildInteractiveInitialState(
    runtimeConfig: LeniaRuntimeConfig,
    seed: Int
) -> MLXArray {
    if let statePatch = runtimeConfig.statePatch {
        return flowLeniaBuildExplicitState(
            sx: runtimeConfig.sx,
            sy: runtimeConfig.sy,
            channels: runtimeConfig.channels,
            statePatch: statePatch
        )
    }

    var rng = SeededRandomNumberGenerator(seed: UInt64(seed))
    var values = [Float](repeating: 0.0, count: runtimeConfig.sx * runtimeConfig.sy * runtimeConfig.channels)

    for patch in runtimeConfig.patches {
        let size = patch.size
        let cx = patch.center[0]
        let cy = patch.center[1]
        let half = size / 2
        let x0 = cx - half
        let x1 = cx + (size - half)
        let y0 = cy - half
        let y1 = cy + (size - half)

        if x0 < 0 || y0 < 0 || x1 > runtimeConfig.sx || y1 > runtimeConfig.sy {
            fatalError("Patch out of bounds: center=(\(cx),\(cy)) size=\(size) grid=\(runtimeConfig.sx)x\(runtimeConfig.sy)")
        }

        for x in x0..<x1 {
            for y in y0..<y1 {
                for channel in 0..<runtimeConfig.channels {
                    let index = x * runtimeConfig.sy * runtimeConfig.channels + y * runtimeConfig.channels + channel
                    values[index] = Float.random(in: runtimeConfig.aUniform.low...runtimeConfig.aUniform.high, using: &rng)
                }
            }
        }
    }

    return MLXArray(values).reshaped([runtimeConfig.sx, runtimeConfig.sy, runtimeConfig.channels])
}

private func flowLeniaBuildInteractiveInitialParams(
    runtimeConfig: LeniaRuntimeConfig,
    seed: Int
) -> MLXArray? {
    guard runtimeConfig.parameterEmbedding.enabled else {
        return nil
    }
    if let paramPatch = runtimeConfig.paramPatch {
        return flowLeniaBuildExplicitState(
            sx: runtimeConfig.sx,
            sy: runtimeConfig.sy,
            channels: runtimeConfig.nbK,
            statePatch: paramPatch
        )
    }
    guard let pUniform = runtimeConfig.pUniform else {
        fatalError("parameter_embedding.enabled=true requires init.p_uniform or init.p_state_patch.")
    }
    if let environment = runtimeConfig.environment {
        return flowLeniaBuildCrossMapInitialParams(
            sx: runtimeConfig.sx,
            sy: runtimeConfig.sy,
            nbK: runtimeConfig.nbK,
            seed: seed,
            patches: runtimeConfig.patches,
            pUniform: pUniform,
            environment: environment
        )
    }
    return flowLeniaBuildInitialParams(
        sx: runtimeConfig.sx,
        sy: runtimeConfig.sy,
        nbK: runtimeConfig.nbK,
        seed: seed,
        patches: runtimeConfig.patches,
        pUniform: pUniform,
        constantPerPatch: runtimeConfig.backend == .metalFull
    )
}

private func flowLeniaBuildInteractiveInitialFoodState(
    runtimeConfig: LeniaRuntimeConfig,
    seed: Int
) -> MLXArray? {
    guard let food = runtimeConfig.food, food.enabled else {
        return nil
    }
    return flowLeniaBuildInitialFoodField(
        sx: runtimeConfig.sx,
        sy: runtimeConfig.sy,
        seed: seed,
        config: food
    )
}

private func flowLeniaBuildExplicitState(
    sx: Int,
    sy: Int,
    channels: Int,
    statePatch: InitStatePatchConfig
) -> MLXArray {
    let values = statePatch.decodedValues()
    var field = [Float](repeating: 0.0, count: sx * sy * channels)

    let cx = statePatch.center[0]
    let cy = statePatch.center[1]
    let halfWidth = statePatch.width / 2
    let halfHeight = statePatch.height / 2
    let x0 = cx - halfWidth
    let x1 = cx + (statePatch.width - halfWidth)
    let y0 = cy - halfHeight
    let y1 = cy + (statePatch.height - halfHeight)

    if x0 < 0 || y0 < 0 || x1 > sx || y1 > sy {
        fatalError("state_patch out of bounds: center=(\(cx),\(cy)) size=\(statePatch.width)x\(statePatch.height) grid=\(sx)x\(sy)")
    }

    var patchIndex = 0
    for x in x0..<x1 {
        for y in y0..<y1 {
            for channel in 0..<channels {
                let index = x * sy * channels + y * channels + channel
                field[index] = values[patchIndex]
                patchIndex += 1
            }
        }
    }

    return MLXArray(field).reshaped([sx, sy, channels])
}

struct FlowLeniaPatchRect {
    let x0: Int
    let x1: Int
    let y0: Int
    let y1: Int
}

/// Centered square patch rect with shared out-of-bounds validation, so the
/// patch-based initial-field builders share one geometry + bounds check.
func flowLeniaCenteredPatchRect(center: [Int], size: Int, sx: Int, sy: Int, label: String) -> FlowLeniaPatchRect {
    let cx = center[0]
    let cy = center[1]
    let half = size / 2
    let x0 = cx - half
    let x1 = cx + (size - half)
    let y0 = cy - half
    let y1 = cy + (size - half)
    if x0 < 0 || y0 < 0 || x1 > sx || y1 > sy {
        fatalError("\(label) out of bounds: center=(\(cx),\(cy)) size=\(size) grid=\(sx)x\(sy)")
    }
    return FlowLeniaPatchRect(x0: x0, x1: x1, y0: y0, y1: y1)
}

private func flowLeniaBuildInitialParams(
    sx: Int,
    sy: Int,
    nbK: Int,
    seed: Int,
    patches: [PatchConfig],
    pUniform: UniformRange,
    constantPerPatch: Bool
) -> MLXArray {
    var rng = SeededRandomNumberGenerator(seed: UInt64(seed))
    var params = [Float](repeating: 0.0, count: sx * sy * nbK)

    for patch in patches {
        let rect = flowLeniaCenteredPatchRect(center: patch.center, size: patch.size, sx: sx, sy: sy, label: "Patch")

        let patchParams = constantPerPatch
            ? (0..<nbK).map { _ in Float.random(in: pUniform.low...pUniform.high, using: &rng) }
            : []

        for x in rect.x0..<rect.x1 {
            for y in rect.y0..<rect.y1 {
                for kernel in 0..<nbK {
                    let index = x * sy * nbK + y * nbK + kernel
                    params[index] = constantPerPatch
                        ? patchParams[kernel]
                        : Float.random(in: pUniform.low...pUniform.high, using: &rng)
                }
            }
        }
    }

    return MLXArray(params).reshaped([sx, sy, nbK])
}

private func flowLeniaBuildCrossMapInitialParams(
    sx: Int,
    sy: Int,
    nbK: Int,
    seed: Int,
    patches: [PatchConfig],
    pUniform: UniformRange,
    environment: EnvironmentConfig
) -> MLXArray {
    var rng = SeededRandomNumberGenerator(seed: UInt64(seed))
    let numCells = 1 << (2 * environment.depth)
    let cellParams = (0..<numCells).map { _ in
        (0..<nbK).map { _ in Float.random(in: pUniform.low...pUniform.high, using: &rng) }
    }
    var params = [Float](repeating: 0.0, count: sx * sy * nbK)

    for patch in patches {
        let rect = flowLeniaCenteredPatchRect(center: patch.center, size: patch.size, sx: sx, sy: sy, label: "Patch")

        for x in rect.x0..<rect.x1 {
            for y in rect.y0..<rect.y1 {
                let cellIndex = flowLeniaCrossMapCellIndex(x: x, y: y, sx: sx, sy: sy, depth: environment.depth)
                let patchParams = cellParams[cellIndex]
                for kernel in 0..<nbK {
                    let index = x * sy * nbK + y * nbK + kernel
                    params[index] = patchParams[kernel]
                }
            }
        }
    }

    return MLXArray(params).reshaped([sx, sy, nbK])
}

private func flowLeniaBuildInitialFoodField(
    sx: Int,
    sy: Int,
    seed: Int,
    config: FoodConfig
) -> MLXArray {
    var rng = SeededRandomNumberGenerator(seed: UInt64(seed))
    var field = [Float](repeating: 0.0, count: sx * sy)

    switch config.mode {
    case "full":
        for index in field.indices {
            field[index] = Float.random(in: config.uniform.low...config.uniform.high, using: &rng)
        }
    case "patches":
        guard let patches = config.patches, !patches.isEmpty else {
            fatalError("food.mode=\"patches\" requires non-empty food.patches.")
        }
        for patch in patches {
            let rect = flowLeniaCenteredPatchRect(center: patch.center, size: patch.size, sx: sx, sy: sy, label: "Food patch")
            for x in rect.x0..<rect.x1 {
                for y in rect.y0..<rect.y1 {
                    field[x * sy + y] = Float.random(in: config.uniform.low...config.uniform.high, using: &rng)
                }
            }
        }
    default:
        fatalError("food.mode must be \"full\" or \"patches\".")
    }

    return MLXArray(field).reshaped([sx, sy])
}

private func flowLeniaCrossMapCellIndex(x: Int, y: Int, sx: Int, sy: Int, depth: Int) -> Int {
    var cellIndex = 0
    var x0 = 0
    var y0 = 0
    var x1 = sx
    var y1 = sy

    for _ in 0..<depth {
        let midX = (x0 + x1) / 2
        let midY = (y0 + y1) / 2
        let quadrant: Int
        if x < midX && y < midY {
            quadrant = 0
            x1 = midX
            y1 = midY
        } else if x >= midX && y < midY {
            quadrant = 1
            x0 = midX
            y1 = midY
        } else if x < midX && y >= midY {
            quadrant = 2
            x1 = midX
            y0 = midY
        } else {
            quadrant = 3
            x0 = midX
            y0 = midY
        }
        cellIndex = cellIndex * 4 + quadrant
    }

    return cellIndex
}

func flowLeniaBuildRandomPatchState(
    sx: Int,
    sy: Int,
    channels: Int,
    patchCount: Int,
    patchSize: Int,
    seed: Int,
    valueRange: UniformRange,
    zoneOrigin: [Int]? = nil,
    zoneSize: Int? = nil
) -> MLXArray {
    var rng = SeededRandomNumberGenerator(seed: UInt64(seed))
    var values = [Float](repeating: 0, count: sx * sy * channels)
    let originX = zoneOrigin?[0] ?? 0
    let originY = zoneOrigin?[1] ?? 0
    let usableWidth = zoneSize ?? sx
    let usableHeight = zoneSize ?? sy
    let maxX = max(originX, originX + usableWidth - patchSize)
    let maxY = max(originY, originY + usableHeight - patchSize)

    for _ in 0..<patchCount {
        let x0 = Int.random(in: originX...maxX, using: &rng)
        let y0 = Int.random(in: originY...maxY, using: &rng)
        for x in x0..<(x0 + patchSize) {
            for y in y0..<(y0 + patchSize) {
                for c in 0..<channels {
                    let idx = x * sy * channels + y * channels + c
                    values[idx] = Float.random(in: valueRange.low...valueRange.high, using: &rng)
                }
            }
        }
    }
    return MLXArray(values).reshaped([sx, sy, channels])
}

func flowLeniaBuildRandomPatchParamsNormal(
    sx: Int,
    sy: Int,
    parameterCount: Int,
    patchCount: Int,
    patchSize: Int,
    seed: Int,
    mean: Float,
    std: Float,
    zoneOrigin: [Int]? = nil,
    zoneSize: Int? = nil
) -> MLXArray {
    var rng = SeededRandomNumberGenerator(seed: UInt64(seed))
    var values = [Float](repeating: 0, count: sx * sy * parameterCount)
    let originX = zoneOrigin?[0] ?? 0
    let originY = zoneOrigin?[1] ?? 0
    let usableWidth = zoneSize ?? sx
    let usableHeight = zoneSize ?? sy
    let maxX = max(originX, originX + usableWidth - patchSize)
    let maxY = max(originY, originY + usableHeight - patchSize)

    for _ in 0..<patchCount {
        let patchParams = (0..<parameterCount).map { _ in
            flowLeniaGaussian(mean: mean, std: std, rng: &rng)
        }
        let x0 = Int.random(in: originX...maxX, using: &rng)
        let y0 = Int.random(in: originY...maxY, using: &rng)
        for x in x0..<(x0 + patchSize) {
            for y in y0..<(y0 + patchSize) {
                let base = x * sy * parameterCount + y * parameterCount
                for k in 0..<parameterCount {
                    values[base + k] = patchParams[k]
                }
            }
        }
    }
    return MLXArray(values).reshaped([sx, sy, parameterCount])
}

func flowLeniaBuildFoodField(
    sx: Int,
    sy: Int,
    patchCount: Int,
    patchSize: Int,
    seed: Int,
    value: Float
) -> MLXArray {
    var rng = SeededRandomNumberGenerator(seed: UInt64(seed))
    var values = [Float](repeating: 0, count: sx * sy)
    let maxX = max(0, sx - patchSize)
    let maxY = max(0, sy - patchSize)

    for _ in 0..<patchCount {
        let x0 = Int.random(in: 0...maxX, using: &rng)
        let y0 = Int.random(in: 0...maxY, using: &rng)
        for x in x0..<(x0 + patchSize) {
            for y in y0..<(y0 + patchSize) {
                values[x * sy + y] = value
            }
        }
    }
    return MLXArray(values).reshaped([sx, sy])
}

func flowLeniaGaussian(mean: Float, std: Float, rng: inout SeededRandomNumberGenerator) -> Float {
    mean + gaussianSample(std: std, rng: &rng)
}

public struct FlowLeniaBenchmarkResult: Sendable {
    public let backend: FlowLeniaComputeBackend
    public let gridSize: Int
    public let steps: Int
    public let duration: TimeInterval
    public let stepsPerSecond: Double
    public let stageTimings: FlowSandboxMetalStageTimings?

    public init(
        backend: FlowLeniaComputeBackend,
        gridSize: Int,
        steps: Int,
        duration: TimeInterval,
        stepsPerSecond: Double,
        stageTimings: FlowSandboxMetalStageTimings? = nil
    ) {
        self.backend = backend
        self.gridSize = gridSize
        self.steps = steps
        self.duration = duration
        self.stepsPerSecond = stepsPerSecond
        self.stageTimings = stageTimings
    }
}

public func benchmarkFlowLeniaSimulatorBackend(
    gridSize: Int,
    steps: Int,
    params: ResolvedParams,
    backend: FlowLeniaComputeBackend
) -> FlowLeniaBenchmarkResult {
    let c0 = Array(repeating: 0, count: params.r.count)
    let c1 = [Array(0..<params.r.count)]
    let runtimeConfig = LeniaRuntimeConfig(
        backend: backend,
        sx: gridSize,
        sy: gridSize,
        channels: 1,
        nbK: params.r.count,
        profile: .paper,
        c0: c0,
        c1: c1,
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
        params: params,
        initSeed: 17,
        patches: [PatchConfig(center: [gridSize / 2, gridSize / 2], size: max(4, gridSize / 8))],
        aUniform: UniformRange(low: 0.0, high: 1.0),
        pUniform: UniformRange(low: 0.0, high: 1.0),
        steps: steps,
        parameterEmbedding: ParameterEmbeddingConfig(enabled: true, mix: "avg", mix_seed: nil),
        chemotaxis: nil,
        food: nil,
        walls: nil,
        environment: nil,
        beamMutation: nil,
        interventions: []
    )

    let initialMassBatch = flowSandboxSeedState(seed: 17, gridSize: gridSize)
    let initialState = initialMassBatch[0, 0..., 0..., 0].expandedDimensions(axis: -1)
    let initialParams = flowSandboxParameterField(
        mass: initialMassBatch,
        parameterValues: params.h,
        threshold: 0.05
    )[0, 0..., 0..., 0...]
    let rolloutConfig = FlowLeniaRolloutConfig(
        steps: max(1, steps),
        recordEverySteps: max(1, steps),
        captureEverySteps: nil,
        activityConfig: nil,
        foodSpawn: nil,
        dissipation: nil
    )

    let runtime = FlowLeniaSimulator(runtimeConfig: runtimeConfig)
    _ = runtime.rollout(
        initialState: initialState,
        initialParams: initialParams,
        initialFood: nil,
        config: FlowLeniaRolloutConfig(
            steps: 1,
            recordEverySteps: 1,
            captureEverySteps: nil,
            activityConfig: nil,
            foodSpawn: nil,
            dissipation: nil
        )
    )

    let start = Date()
    _ = runtime.rollout(
        initialState: initialState,
        initialParams: initialParams,
        initialFood: nil,
        config: rolloutConfig
    )
    let duration = Date().timeIntervalSince(start)
    let stageTimings: FlowSandboxMetalStageTimings?
    if backend == .metalFull {
        let kernels = compileKernels(params: params, config: batchedConfigFromRuntime(runtimeConfig), c0: c0, c1: c1)
        stageTimings = profileFlowSandboxMetalStages(
            config: batchedConfigFromRuntime(runtimeConfig),
            kernels: kernels,
            initialMass: initialMassBatch,
            initialParams: initialParams.expandedDimensions(axis: 0)
        )
    } else {
        stageTimings = nil
    }

    return FlowLeniaBenchmarkResult(
        backend: backend,
        gridSize: gridSize,
        steps: steps,
        duration: duration,
        stepsPerSecond: Double(steps) / duration,
        stageTimings: stageTimings
    )
}

struct FlowLeniaPreparedFields {
    let environmentPotential: MLXArray?
    let wallMask: MLXArray?
    let chemField: MLXArray?

    init(runtimeConfig: LeniaRuntimeConfig) {
        let crossMapMask: MLXArray?
        if let environment = runtimeConfig.environment {
            crossMapMask = flowLeniaBuildCrossMapMask(
                sx: runtimeConfig.sx,
                sy: runtimeConfig.sy,
                config: environment
            ).expandedDimensions(axes: [0, 3])
        } else {
            crossMapMask = nil
        }

        self.environmentPotential = crossMapMask
        if let crossMapMask {
            self.wallMask = crossMapMask
        } else if let wallsConfig = runtimeConfig.walls, wallsConfig.enabled {
            self.wallMask = flowLeniaBuildWallMask(
                sx: runtimeConfig.sx,
                sy: runtimeConfig.sy,
                config: wallsConfig
            ).expandedDimensions(axes: [0, 3])
        } else {
            self.wallMask = nil
        }

        if let chemotaxis = runtimeConfig.chemotaxis, chemotaxis.enabled {
            self.chemField = flowLeniaBuildChemotaxisField(
                sx: runtimeConfig.sx,
                sy: runtimeConfig.sy,
                config: chemotaxis
            ).expandedDimensions(axes: [0, 3])
        } else {
            self.chemField = nil
        }
    }
}

struct FlowLeniaRuntimeContext {
    let runtimeConfig: LeniaRuntimeConfig
    let batchedConfig: BatchedConfig
    let kernels: CompiledKernels
    let preparedFields: FlowLeniaPreparedFields
    let runtimeOperators: FlowLeniaRuntimeOperators

    init(runtimeConfig: LeniaRuntimeConfig) {
        let batchedConfig = batchedConfigFromRuntime(runtimeConfig)
        self.runtimeConfig = runtimeConfig
        self.batchedConfig = batchedConfig
        self.kernels = compileKernels(
            params: runtimeConfig.params,
            config: batchedConfig,
            c0: runtimeConfig.c0,
            c1: runtimeConfig.c1
        )
        self.preparedFields = FlowLeniaPreparedFields(runtimeConfig: runtimeConfig)
        self.runtimeOperators = FlowLeniaRuntimeOperators(runtimeConfig: runtimeConfig)
    }
}

private func flowLeniaBuildWallMask(sx: Int, sy: Int, config: WallsConfig) -> MLXArray {
    var values = [Float](repeating: 1, count: sx * sy)
    for patch in config.patches {
        let half = patch.size / 2
        let x0 = patch.center[0] - half
        let x1 = patch.center[0] + (patch.size - half)
        let y0 = patch.center[1] - half
        let y1 = patch.center[1] + (patch.size - half)
        for x in x0..<x1 {
            for y in y0..<y1 {
                values[x * sy + y] = 0
            }
        }
    }
    return MLXArray(values).reshaped([sx, sy])
}

private func flowLeniaBuildCrossMapMask(sx: Int, sy: Int, config: EnvironmentConfig) -> MLXArray {
    var mask = [[Float]](repeating: [Float](repeating: 0, count: sy), count: sx)
    let wallThickness = config.wallThickness
    let wallValue = config.wallValue

    func bisect(x0: Int, y0: Int, x1: Int, y1: Int, depth: Int) {
        guard depth > 0 else { return }
        let midX = (x0 + x1) / 2
        let midY = (y0 + y1) / 2
        let halfWall = wallThickness / 2

        for x in max(0, midX - halfWall)..<min(sx, midX - halfWall + wallThickness) {
            for y in y0..<y1 {
                mask[x][y] = wallValue
            }
        }
        for x in x0..<x1 {
            for y in max(0, midY - halfWall)..<min(sy, midY - halfWall + wallThickness) {
                mask[x][y] = wallValue
            }
        }

        if let passageWidth = config.passageWidth, passageWidth > 0 {
            let halfPassage = passageWidth / 2
            for x in max(0, midX - halfWall)..<min(sx, midX - halfWall + wallThickness) {
                for y in max(y0, midY - halfPassage)..<min(y1, midY - halfPassage + passageWidth) {
                    mask[x][y] = 0
                }
            }
            for y in max(0, midY - halfWall)..<min(sy, midY - halfWall + wallThickness) {
                for x in max(x0, midX - halfPassage)..<min(x1, midX - halfPassage + passageWidth) {
                    mask[x][y] = 0
                }
            }
        }

        bisect(x0: x0, y0: y0, x1: midX - halfWall, y1: midY - halfWall, depth: depth - 1)
        bisect(x0: midX - halfWall + wallThickness, y0: y0, x1: x1, y1: midY - halfWall, depth: depth - 1)
        bisect(x0: x0, y0: midY - halfWall + wallThickness, x1: midX - halfWall, y1: y1, depth: depth - 1)
        bisect(x0: midX - halfWall + wallThickness, y0: midY - halfWall + wallThickness, x1: x1, y1: y1, depth: depth - 1)
    }

    bisect(x0: 0, y0: 0, x1: sx, y1: sy, depth: config.depth)
    return MLXArray(mask.flatMap { $0 }).reshaped([sx, sy])
}

private func flowLeniaBuildChemotaxisField(sx: Int, sy: Int, config: ChemotaxisConfig) -> MLXArray {
    let coordsX = MLXArray(Array(0..<sx).map(Float.init))
    let coordsY = MLXArray(Array(0..<sy).map(Float.init))
    let (gridX, gridY) = meshgrid(coordsX, coordsY)

    var centerX = config.center[0]
    var centerY = config.center[1]
    if config.mode == "random_on_circle", let radius = config.circle_radius, let seed = config.seed {
        var rng = SeededRandomNumberGenerator(seed: UInt64(seed))
        let angle = Float.random(in: 0...(2 * .pi), using: &rng)
        centerX += radius * Float(cos(Double(angle)))
        centerY += radius * Float(sin(Double(angle)))
    }

    let dx = gridX - MLXArray(centerX)
    let dy = gridY - MLXArray(centerY)
    let distSq = dx * dx + dy * dy
    let sigma = config.sigma
    let exponent = -distSq / MLXArray(2 * sigma * sigma)
    return MLXArray(config.amplitude) * MLX.exp(exponent)
}

struct FlowLeniaRuntimeOperators {
    let runtimeConfig: LeniaRuntimeConfig

    func applyPreStepFields(
        massBatch: inout MLXArray,
        foodBatch: MLXArray?,
        chemField: MLXArray?
    ) {
        if let field = chemField, let chemotaxis = runtimeConfig.chemotaxis {
            massBatch = applyExternalField(massBatch, field: field, channelIndex: chemotaxis.channel_index)
        }
        if let food = foodBatch, let foodConfig = runtimeConfig.food, foodConfig.enabled {
            massBatch = applyExternalField(
                massBatch,
                field: food.expandedDimensions(axis: -1),
                channelIndex: foodConfig.channel_index
            )
        }
    }

    func applyBeamMutationIfNeeded(paramBatch: inout MLXArray?, step: Int) {
        guard let beam = runtimeConfig.beamMutation, beam.enabled, let params = paramBatch else {
            return
        }
        paramBatch = applyBeamMutation(params, config: beam, step: step)
    }

    func applyDissipationIfNeeded(
        massBatch: inout MLXArray,
        paramBatch: inout MLXArray?,
        config: FlowLeniaDissipationConfig?,
        step: Int
    ) {
        guard let config, let params = paramBatch else {
            return
        }
        let updated = applyDissipation(
            A: massBatch,
            P: params,
            config: config,
            step: step,
            massChannels: runtimeConfig.channels,
            parameterCount: runtimeConfig.nbK
        )
        massBatch = updated.A
        paramBatch = updated.P
    }

    func applyFoodStepIfNeeded(
        massBatch: inout MLXArray,
        foodBatch: inout MLXArray?,
        foodSpawn: FlowLeniaFoodSpawnConfig?,
        step: Int
    ) {
        guard let foodConfig = runtimeConfig.food, foodConfig.enabled, let currentFood = foodBatch else {
            return
        }
        let updated = applyFoodDynamics(massBatch, food: currentFood, config: foodConfig)
        massBatch = updated.mass
        var nextFood = updated.food
        if let foodSpawn {
            nextFood = spawnFoodPatches(nextFood, config: foodSpawn, step: step)
        }
        foodBatch = nextFood
        massBatch = applyExternalField(
            massBatch,
            field: nextFood.expandedDimensions(axis: -1),
            channelIndex: foodConfig.channel_index
        )
    }

    func applyWallMaskIfNeeded(
        massBatch: inout MLXArray,
        paramBatch: inout MLXArray?,
        foodBatch: inout MLXArray?,
        wallMask: MLXArray?
    ) {
        guard let wallMask else {
            return
        }
        massBatch = applyWallMask(massBatch, mask: wallMask)
        if let params = paramBatch {
            paramBatch = applyWallMask(params, mask: wallMask)
        }
        if let food = foodBatch {
            foodBatch = applyWallMaskToField(food, mask: wallMask)
        }
    }

    func applyExternalField(_ A: MLXArray, field: MLXArray, channelIndex: Int) -> MLXArray {
        overwriteFieldChannel(A, field: field, channelIndex: channelIndex)
    }

    func applyWallMask(_ A: MLXArray, mask: MLXArray) -> MLXArray {
        A * MLX.broadcast(mask, to: A.shape)
    }

    func applyWallMaskToField(_ field: MLXArray, mask: MLXArray) -> MLXArray {
        let squeezed = mask.squeezed(axis: 3)
        return field * MLX.broadcast(squeezed, to: field.shape)
    }

    func applyFoodDynamics(
        _ A: MLXArray,
        food: MLXArray,
        config: FoodConfig
    ) -> (mass: MLXArray, food: MLXArray) {
        let massMap = matterMapFromBatch(A)
        let decayRate = MLXArray(config.decay_rate)
        let digestRate = MLXArray(config.digest_rate)
        let eps = MLXArray(Float(1e-6))

        let decay = massMap * decayRate
        let digestRaw = massMap * digestRate
        let digestClipped = MLX.clip(digestRaw, min: MLXArray(0.0), max: massMap)
        let delta = digestClipped * food
        let newMass = MLX.maximum(massMap + delta - decay, MLXArray(0.0))
        let scale = newMass / MLX.maximum(massMap, eps)
        let scaleExpanded = scale.expandedDimensions(axis: -1)

        let excluded = excludedMassChannels()
        var parts: [MLXArray] = []
        for c in 0..<runtimeConfig.channels {
            let channel = A[0..., 0..., 0..., c].expandedDimensions(axis: -1)
            if excluded.contains(c) {
                parts.append(channel)
            } else {
                parts.append(channel * scaleExpanded)
            }
        }
        let newA = MLX.concatenated(parts, axis: 3)
        let newFood = MLX.maximum(food - delta, MLXArray(0.0))
        return (newA, newFood)
    }

    func spawnFoodPatches(_ food: MLXArray, config: FlowLeniaFoodSpawnConfig, step: Int) -> MLXArray {
        let batch = food.shape[0]
        let sx = food.shape[1]
        let sy = food.shape[2]
        var rng = SeededRandomNumberGenerator(seed: UInt64(config.seed) + UInt64(step))
        let maxX = max(0, sx - config.patchSize)
        let maxY = max(0, sy - config.patchSize)
        var placements: [(batch: Int, x0: Int, y0: Int)] = []
        for b in 0..<batch {
            if Float.random(in: 0..<1, using: &rng) >= config.probability {
                continue
            }
            let x0 = Int.random(in: 0...maxX, using: &rng)
            let y0 = Int.random(in: 0...maxY, using: &rng)
            placements.append((b, x0, y0))
        }
        guard !placements.isEmpty else {
            return food
        }
        eval(food)
        var values = food.asArray(Float.self)
        for placement in placements {
            for x in placement.x0..<(placement.x0 + config.patchSize) {
                for y in placement.y0..<(placement.y0 + config.patchSize) {
                    values[placement.batch * sx * sy + x * sy + y] = config.value
                }
            }
        }
        return MLXArray(values).reshaped([batch, sx, sy])
    }

    func foodSpawnPatchSchedule(
        startStep: Int,
        count: Int,
        batch: Int,
        config: FlowLeniaFoodSpawnConfig?,
        sx: Int,
        sy: Int
    ) -> [Int: [FlowLeniaMetalScalarPatchBatch]] {
        guard let config else {
            return [:]
        }
        let inactiveOrigin = SIMD2<Int32>(-1, -1)
        let maxX = max(0, sx - config.patchSize)
        let maxY = max(0, sy - config.patchSize)
        var schedule: [Int: [FlowLeniaMetalScalarPatchBatch]] = [:]

        for offset in 0..<count {
            let step = startStep + offset
            var rng = SeededRandomNumberGenerator(seed: UInt64(config.seed) + UInt64(step))
            var origins = Array(repeating: inactiveOrigin, count: batch)
            var hasPlacement = false
            for b in 0..<batch {
                if Float.random(in: 0..<1, using: &rng) >= config.probability {
                    continue
                }
                let x0 = Int.random(in: 0...maxX, using: &rng)
                let y0 = Int.random(in: 0...maxY, using: &rng)
                origins[b] = SIMD2(Int32(x0), Int32(y0))
                hasPlacement = true
            }
            if hasPlacement {
                schedule[offset + 1] = [
                    FlowLeniaMetalScalarPatchBatch(
                        origins: origins,
                        size: config.patchSize,
                        value: config.value
                    )
                ]
            }
        }
        return schedule
    }

    func applyDissipation(
        A: MLXArray,
        P: MLXArray,
        config: FlowLeniaDissipationConfig,
        step: Int,
        massChannels: Int,
        parameterCount: Int
    ) -> (A: MLXArray, P: MLXArray) {
        let batch = A.shape[0]
        let sx = A.shape[1]
        let sy = A.shape[2]
        var rng = SeededRandomNumberGenerator(seed: UInt64(config.seed) + UInt64(step))
        let maxRemovalX = max(0, sx - config.patchSize)
        let maxRemovalY = max(0, sy - config.patchSize)
        let zoneX = config.insertionZoneOrigin[0]
        let zoneY = config.insertionZoneOrigin[1]
        let maxInsertionX = max(zoneX, zoneX + config.insertionZoneSize - config.patchSize)
        let maxInsertionY = max(zoneY, zoneY + config.insertionZoneSize - config.patchSize)
        var instructions: [(batch: Int, removeX: Int, removeY: Int, insertX: Int, insertY: Int, patchParams: [Float])] = []

        for b in 0..<batch {
            if Float.random(in: 0..<1, using: &rng) >= config.probability {
                continue
            }
            let removeX = Int.random(in: 0...maxRemovalX, using: &rng)
            let removeY = Int.random(in: 0...maxRemovalY, using: &rng)
            let patchParams = (0..<parameterCount).map { _ in
                flowLeniaGaussian(mean: 0, std: 1, rng: &rng)
            }
            let insertX = Int.random(in: zoneX...maxInsertionX, using: &rng)
            let insertY = Int.random(in: zoneY...maxInsertionY, using: &rng)
            instructions.append((b, removeX, removeY, insertX, insertY, patchParams))
        }
        guard !instructions.isEmpty else {
            return (A, P)
        }
        eval(A, P)
        var massValues = A.asArray(Float.self)
        var paramValues = P.asArray(Float.self)
        for instruction in instructions {
            for x in instruction.removeX..<(instruction.removeX + config.patchSize) {
                for y in instruction.removeY..<(instruction.removeY + config.patchSize) {
                    let massBase = instruction.batch * sx * sy * massChannels + x * sy * massChannels + y * massChannels
                    for c in 0..<massChannels {
                        massValues[massBase + c] = 0
                    }
                    let paramBase = instruction.batch * sx * sy * parameterCount + x * sy * parameterCount + y * parameterCount
                    for k in 0..<parameterCount {
                        paramValues[paramBase + k] = 0
                    }
                }
            }

            for x in instruction.insertX..<(instruction.insertX + config.patchSize) {
                for y in instruction.insertY..<(instruction.insertY + config.patchSize) {
                    let massBase = instruction.batch * sx * sy * massChannels + x * sy * massChannels + y * massChannels
                    for c in 0..<massChannels {
                        massValues[massBase + c] = Float.random(in: 0...1, using: &rng)
                    }
                    let paramBase = instruction.batch * sx * sy * parameterCount + x * sy * parameterCount + y * parameterCount
                    for k in 0..<parameterCount {
                        paramValues[paramBase + k] = instruction.patchParams[k]
                    }
                }
            }
        }
        return (
            MLXArray(massValues).reshaped(A.shape),
            MLXArray(paramValues).reshaped(P.shape)
        )
    }

    func dissipationPatchSchedule(
        startStep: Int,
        count: Int,
        batch: Int,
        massChannels: Int,
        parameterCount: Int,
        config: FlowLeniaDissipationConfig?,
        sx: Int,
        sy: Int
    ) -> [Int: [FlowLeniaMetalDissipationBatch]] {
        guard let config else {
            return [:]
        }
        let inactiveOrigin = SIMD2<Int32>(-1, -1)
        let maxRemovalX = max(0, sx - config.patchSize)
        let maxRemovalY = max(0, sy - config.patchSize)
        let zoneX = config.insertionZoneOrigin[0]
        let zoneY = config.insertionZoneOrigin[1]
        let maxInsertionX = max(zoneX, zoneX + config.insertionZoneSize - config.patchSize)
        let maxInsertionY = max(zoneY, zoneY + config.insertionZoneSize - config.patchSize)
        var schedule: [Int: [FlowLeniaMetalDissipationBatch]] = [:]

        for offset in 0..<count {
            let step = startStep + offset
            var rng = SeededRandomNumberGenerator(seed: UInt64(config.seed) + UInt64(step))
            var removalOrigins = Array(repeating: inactiveOrigin, count: batch)
            var insertionOrigins = Array(repeating: inactiveOrigin, count: batch)
            var insertedParams = [Float](repeating: 0, count: batch * parameterCount)
            var insertedMass = [Float](repeating: 0, count: batch * config.patchSize * config.patchSize * massChannels)
            var activeBatches: [Int] = []

            for b in 0..<batch {
                if Float.random(in: 0..<1, using: &rng) >= config.probability {
                    continue
                }
                let removeX = Int.random(in: 0...maxRemovalX, using: &rng)
                let removeY = Int.random(in: 0...maxRemovalY, using: &rng)
                removalOrigins[b] = SIMD2(Int32(removeX), Int32(removeY))
                let paramBase = b * parameterCount
                for k in 0..<parameterCount {
                    insertedParams[paramBase + k] = flowLeniaGaussian(mean: 0, std: 1, rng: &rng)
                }
                let insertX = Int.random(in: zoneX...maxInsertionX, using: &rng)
                let insertY = Int.random(in: zoneY...maxInsertionY, using: &rng)
                insertionOrigins[b] = SIMD2(Int32(insertX), Int32(insertY))
                activeBatches.append(b)
            }

            if activeBatches.isEmpty {
                continue
            }

            for b in activeBatches {
                for x in 0..<config.patchSize {
                    for y in 0..<config.patchSize {
                        let massBase = ((b * config.patchSize + x) * config.patchSize + y) * massChannels
                        for c in 0..<massChannels {
                            insertedMass[massBase + c] = Float.random(in: 0...1, using: &rng)
                        }
                    }
                }
            }

            schedule[offset + 1] = [
                FlowLeniaMetalDissipationBatch(
                    removalOrigins: removalOrigins,
                    insertionOrigins: insertionOrigins,
                    size: config.patchSize,
                    insertedMass: insertedMass,
                    insertedParams: insertedParams
                )
            ]
        }

        return schedule
    }

    func applyBeamMutation(_ P: MLXArray, config: BeamMutationConfig, step: Int) -> MLXArray {
        let patch = buildBeamMutationPatch(
            config: config,
            step: step,
            batch: P.shape[0],
            sx: P.shape[1],
            sy: P.shape[2],
            parameterCount: P.shape[3]
        )
        eval(P)
        var values = P.asArray(Float.self)
        for b in 0..<P.shape[0] {
            let origin = patch.origins[b]
            for localX in 0..<patch.size {
                let x = Int(origin.x) + localX
                guard x >= 0 && x < P.shape[1] else {
                    continue
                }
                for localY in 0..<patch.size {
                    let y = Int(origin.y) + localY
                    guard y >= 0 && y < P.shape[2] else {
                        continue
                    }
                    let base = b * P.shape[1] * P.shape[2] * P.shape[3] + x * P.shape[2] * P.shape[3] + y * P.shape[3]
                    let deltaBase = ((b * patch.size + localX) * patch.size + localY) * P.shape[3]
                    for k in 0..<P.shape[3] {
                        values[base + k] += patch.deltas[deltaBase + k]
                    }
                }
            }
        }
        return MLXArray(values).reshaped(P.shape)
    }

    func beamMutationPatchSchedule(
        startStep: Int,
        count: Int,
        batch: Int,
        parameterCount: Int,
        config: BeamMutationConfig?,
        sx: Int,
        sy: Int
    ) -> [Int: [FlowLeniaMetalParameterPatchBatch]] {
        guard count > 0 else {
            return [:]
        }
        guard let config, config.enabled else {
            return [:]
        }
        var schedule: [Int: [FlowLeniaMetalParameterPatchBatch]] = [:]
        for localStep in 1...count {
            let patch = buildBeamMutationPatch(
                config: config,
                step: startStep + localStep - 1,
                batch: batch,
                sx: sx,
                sy: sy,
                parameterCount: parameterCount
            )
            if patch.deltas.contains(where: { $0 != 0 }) {
                schedule[localStep] = [patch.asMetalPatchBatch()]
            }
        }
        return schedule
    }

    func matterMapFromBatch(_ A: MLXArray) -> MLXArray {
        flowMatterMap(A, excludedChannels: excludedMassChannels())
    }

    func excludedMassChannels() -> Set<Int> {
        flowExcludedMassChannels(
            channels: runtimeConfig.channels,
            chemotaxis: runtimeConfig.chemotaxis,
            food: runtimeConfig.food
        )
    }

    func matterWeights() -> [Float]? {
        flowMatterWeights(channels: runtimeConfig.channels, excludedChannels: excludedMassChannels())
    }

    func metalStaticChannelFields(chemField: MLXArray?) -> [FlowLeniaMetalChannelField] {
        guard let chemField,
              let chemotaxis = runtimeConfig.chemotaxis,
              chemotaxis.enabled else {
            return []
        }
        return [FlowLeniaMetalChannelField(channelIndex: chemotaxis.channel_index, field: chemField)]
    }

    func metalFoodState(foodBatch: MLXArray?) -> FlowLeniaMetalFoodState? {
        guard let field = foodBatch,
              let food = runtimeConfig.food,
              food.enabled else {
            return nil
        }
        return FlowLeniaMetalFoodState(
            channelIndex: food.channel_index,
            field: field,
            decayRate: food.decay_rate,
            digestRate: food.digest_rate
        )
    }

    func frameDataFromMassMap(_ massMap: [Float]) -> Data {
        frameDataFromScalarField(massMap)
    }

    func frameDataFromScalarField(_ field: [Float]) -> Data {
        var bytes = [UInt8](repeating: 0, count: field.count)
        for (idx, value) in field.enumerated() {
            let finite = value.isFinite ? value : 0
            let clamped = max(0, min(1, finite))
            bytes[idx] = UInt8(clamped * 255)
        }
        return Data(bytes)
    }

    func centerOfMass(_ massMap: [Float], width: Int, height: Int) -> (x: Float, y: Float) {
        let total = max(massMap.reduce(0, +), 1e-8)
        var sumX: Float = 0
        var sumY: Float = 0
        for x in 0..<width {
            for y in 0..<height {
                let mass = massMap[x * height + y]
                sumX += Float(x) * mass
                sumY += Float(y) * mass
            }
        }
        return (sumX / total, sumY / total)
    }

    private func buildBeamMutationPatch(
        config: BeamMutationConfig,
        step: Int,
        batch: Int,
        sx: Int,
        sy: Int,
        parameterCount: Int
    ) -> FlowLeniaBeamMutationPatch {
        var rng = SeededRandomNumberGenerator(seed: UInt64(config.seed) + UInt64(step))
        let maxX = max(0, sx - config.patchSize)
        let maxY = max(0, sy - config.patchSize)
        var origins = Array(repeating: SIMD2<Int32>(Int32(-config.patchSize), Int32(-config.patchSize)), count: batch)
        var deltas = [Float](repeating: 0, count: batch * config.patchSize * config.patchSize * parameterCount)
        for b in 0..<batch {
            if Float.random(in: 0..<1, using: &rng) >= config.probability {
                continue
            }
            let x0 = Int.random(in: 0...maxX, using: &rng)
            let y0 = Int.random(in: 0...maxY, using: &rng)
            origins[b] = SIMD2(Int32(x0), Int32(y0))
            let patchNoise = (0..<parameterCount).map { _ in
                flowLeniaGaussian(mean: 0, std: config.std, rng: &rng)
            }
            for localX in 0..<config.patchSize {
                for localY in 0..<config.patchSize {
                    let deltaBase = ((b * config.patchSize + localX) * config.patchSize + localY) * parameterCount
                    for k in 0..<parameterCount {
                        deltas[deltaBase + k] = patchNoise[k]
                    }
                }
            }
        }
        return FlowLeniaBeamMutationPatch(origins: origins, size: config.patchSize, deltas: deltas)
    }
}

private struct FlowLeniaBeamMutationPatch {
    let origins: [SIMD2<Int32>]
    let size: Int
    let deltas: [Float]

    func asMetalPatchBatch() -> FlowLeniaMetalParameterPatchBatch {
        FlowLeniaMetalParameterPatchBatch(origins: origins, size: size, deltas: deltas, clip: nil)
    }
}
