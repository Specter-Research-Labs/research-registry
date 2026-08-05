import Foundation
import MLX
import MLXRandom

private func durationMs(_ duration: Duration) -> Double {
    Double(duration.components.seconds) * 1_000.0 + Double(duration.components.attoseconds) / 1e15
}

private struct SearchBatchSetup {
    let resolvedParamsBySample: [ResolvedParams]?
    let initialConditionFamily: String
    let activityConfig: ActivityConfig?
    let stabilityConfig: StabilityConfig
    let usesActivityMetrics: Bool
    let captureConfig: FrameCapture?
    let massBatch: MLXArray
    let paramBatch: MLXArray?
    let foodBatch: MLXArray?
    let initialFoodMass: [Float]?
    let wallMask: MLXArray?
    let chemField: MLXArray?
    let persistentMetalRunner: FlowLeniaMetalFullStateRunner?
    let interventionsByStep: [Int: [InterventionConfig]]
}

public final class SearchEngine {
    private struct MetalRunnerCacheKey: Hashable {
        let batchSize: Int
        let kernelBatchCount: Int
    }

    private enum Stepper {
        case mlx(FlowLeniaBatched, FlowLeniaParamsBatched?)

        func step(_ mass: MLXArray, _ params: MLXArray?) -> (MLXArray, MLXArray?) {
            switch self {
            case .mlx(let engine, let paramsEngine):
                if let params, let paramsEngine {
                    let stepped = paramsEngine.step(mass, params)
                    return (stepped.0, stepped.1)
                }
                return (engine.step(mass), nil)
            }
        }
    }

    private let stepper: Stepper?
    private let batchedConfig: BatchedConfig
    private let runtimeConfig: LeniaRuntimeConfig
    private let useParamEmbedding: Bool
    private let profile: RuntimeProfile
    private let environmentPotential: MLXArray?
    private let metalFullKernels: CompiledKernels?
    private let staticParamTemplate: MLXArray?
    private var persistentMetalRunnerCache: [MetalRunnerCacheKey: FlowLeniaMetalFullStateRunner] = [:]
    private(set) var lastBatchProfile: SearchBatchProfile?

    public init(runtimeConfig: LeniaRuntimeConfig) {
        self.runtimeConfig = runtimeConfig
        self.batchedConfig = batchedConfigFromRuntime(runtimeConfig)
        self.useParamEmbedding = runtimeConfig.parameterEmbedding.enabled
        self.profile = runtimeConfig.profile

        if useParamEmbedding && runtimeConfig.pUniform == nil && runtimeConfig.paramPatch == nil {
            fatalError("parameter_embedding.enabled requires init.p_uniform or init.p_state_patch.")
        }

        let kernels = compileKernels(
            params: runtimeConfig.params,
            config: batchedConfig,
            c0: runtimeConfig.c0,
            c1: runtimeConfig.c1
        )
        self.metalFullKernels = runtimeConfig.backend == .metalFull ? kernels : nil

        if !useParamEmbedding && runtimeConfig.backend == .metalFull {
            let nbK = FlowLeniaMetalFullPipeline.parameterCount(for: kernels)
            self.staticParamTemplate = MLX.broadcast(
                kernels.h.reshaped([1, 1, 1, nbK]),
                to: [1, runtimeConfig.sx, runtimeConfig.sy, nbK]
            )
        } else {
            self.staticParamTemplate = nil
        }

        let initializationBuilder = SearchInitializationBuilder(
            runtimeConfig: runtimeConfig,
            useParamEmbedding: useParamEmbedding,
            constantPerPatchParameters: profile == .paper || runtimeConfig.implementation.mode == "flowlenia_2022_colab"
        )
        let crossMapPotential = initializationBuilder.environmentPotential()
        self.environmentPotential = crossMapPotential

        switch runtimeConfig.backend {
        case .mlx:
            let engine = FlowLeniaBatched(
                config: batchedConfig,
                kernels: kernels,
                wallPotential: crossMapPotential
            )

            if useParamEmbedding {
                let mixMode = runtimeConfig.parameterEmbedding.mix
                let allowedMix = ["avg", "softmax", "stoch", "argmax", "stoch_gene_wise", "energy"]
                if !allowedMix.contains(mixMode) {
                    fatalError("parameter_embedding.mix must be one of: \(allowedMix.joined(separator: ", "))")
                }
                let stochasticModes: Set<String> = ["stoch", "softmax", "stoch_gene_wise", "energy"]
                if stochasticModes.contains(mixMode) {
                    if runtimeConfig.implementation.mode == "flowlenia_2022_colab" {
                        if runtimeConfig.parameterEmbedding.mix_seed != nil {
                            fatalError("parameter_embedding.mix_seed must be omitted when implementation.mode == \"flowlenia_2022_colab\".")
                        }
                    } else if runtimeConfig.parameterEmbedding.mix_seed == nil {
                        fatalError("parameter_embedding.mix_seed is required for \(mixMode) mixing when implementation.mode != \"flowlenia_2022_colab\".")
                    }
                }
                self.stepper = .mlx(
                    engine,
                    FlowLeniaParamsBatched(
                        config: batchedConfig,
                        kernels: kernels,
                        mixMode: mixMode,
                        mixSeed: runtimeConfig.parameterEmbedding.mix_seed,
                        wallPotential: crossMapPotential
                    )
                )
            } else {
                self.stepper = .mlx(engine, nil)
            }
        case .metalFull:
            SearchRuntimePreflight.validateMetalBackendCompatibility(
                runtimeConfig: runtimeConfig,
                hasEnvironmentPotential: crossMapPotential != nil
            )
            self.stepper = nil
        }

        SearchRuntimePreflight.validateRuntimeConfig(runtimeConfig: runtimeConfig, profile: profile)
    }

    private func reusableMetalFullRunner(
        batchSize: Int,
        kernels: CompiledKernels
    ) -> FlowLeniaMetalFullStateRunner {
        let runtimeOperators = makeRuntimeOperators()
        let cacheKey = MetalRunnerCacheKey(
            batchSize: batchSize,
            kernelBatchCount: FlowLeniaMetalFullPipeline.kernelBatchCount(for: kernels)
        )
        if let runner = persistentMetalRunnerCache[cacheKey] {
            runner.setMatterWeights(runtimeOperators.matterWeights())
            runner.updateKernels(kernels)
            return runner
        }
        let runner = FlowLeniaMetalFullStateRunner(
            config: batchedConfig,
            kernels: kernels,
            batchCount: batchSize,
            wallPotential: environmentPotential,
            matterWeights: runtimeOperators.matterWeights(),
            reintegrateParams: useParamEmbedding,
            parameterMix: runtimeConfig.parameterEmbedding.mix,
            mixSeed: runtimeConfig.parameterEmbedding.mix_seed
        )
        persistentMetalRunnerCache[cacheKey] = runner
        return runner
    }

    private func flushPendingMetalSteps(
        runner: FlowLeniaMetalFullStateRunner,
        pendingMetalSteps: inout Int,
        pendingMetalStartStep: Int,
        batchSize: Int
    ) {
        guard pendingMetalSteps > 0 else {
            return
        }
        let runtimeOperators = makeRuntimeOperators()
        runner.step(
            count: pendingMetalSteps,
            preStepParameterPatches: [:],
            postStepParameterPatches: runtimeOperators.searchBeamMutationPatchSchedule(
                startStep: pendingMetalStartStep,
                count: pendingMetalSteps,
                batchSize: batchSize,
                parameterCount: runtimeConfig.nbK
            )
        )
        pendingMetalSteps = 0
    }

    private func makeInitializationBuilder() -> SearchInitializationBuilder {
        SearchInitializationBuilder(
            runtimeConfig: runtimeConfig,
            useParamEmbedding: useParamEmbedding,
            constantPerPatchParameters: profile == .paper || runtimeConfig.implementation.mode == "flowlenia_2022_colab"
        )
    }

    private func makeRuntimeOperators() -> SearchRuntimeOperators {
        SearchRuntimeOperators(runtimeConfig: runtimeConfig)
    }

    private func summaryChannelWeights(searchConfig: SearchConfig) -> [Float]? {
        if searchConfig.massChannel == -1 {
            return flowMatterWeights(
                channels: runtimeConfig.channels,
                excludedChannels: makeRuntimeOperators().excludedMassChannels()
            )
        }
        guard searchConfig.massChannel >= 0, searchConfig.massChannel < runtimeConfig.channels else {
            preconditionFailure("Search massChannel \(searchConfig.massChannel) is outside configured channel count \(runtimeConfig.channels).")
        }
        return (0..<runtimeConfig.channels).map { $0 == searchConfig.massChannel ? 1.0 : 0.0 }
    }

    private func advanceBatch(
        step: Int,
        stepper: Stepper,
        runtimeOperators: SearchRuntimeOperators,
        massBatch: inout MLXArray,
        paramBatch: inout MLXArray?,
        foodBatch: inout MLXArray?,
        wallMask: MLXArray?,
        chemField: MLXArray?,
        includeInterventions: Bool,
        includeBeamMutation: Bool
    ) {
        if includeInterventions {
            runtimeOperators.applyPreStepOperators(
                step: step,
                massBatch: &massBatch,
                paramBatch: &paramBatch,
                chemField: chemField,
                foodBatch: foodBatch
            )
        } else {
            runtimeOperators.applyPreStepFields(
                massBatch: &massBatch,
                foodBatch: foodBatch,
                chemField: chemField
            )
        }

        let stepped = stepper.step(massBatch, paramBatch)
        massBatch = stepped.0
        if useParamEmbedding {
            paramBatch = stepped.1
        }

        if includeBeamMutation,
           let beamConfig = runtimeConfig.beamMutation,
           beamConfig.enabled,
           let paramsBatch = paramBatch {
            paramBatch = runtimeOperators.applySearchBeamMutation(paramsBatch, config: beamConfig, step: step)
        }

        runtimeOperators.applyPostStepOperators(
            massBatch: &massBatch,
            paramBatch: &paramBatch,
            foodBatch: &foodBatch,
            wallMask: wallMask
        )
    }

    /// Explicit batches supply one rule and, optionally, one state patch per seed for fixed-corpus
    /// Metal evaluation without parameter embedding.
    public func runBatch(
        seeds: [Int],
        initSeedOffset: Int,
        searchConfig: SearchConfig,
        frameCapture: FrameCapture? = nil,
        explicitParamsBatch: [ResolvedParams]? = nil,
        explicitInitialStateBatch: [InitStatePatchConfig?]? = nil
    ) -> [BatchSimulationResult] {
        let totalStart = ContinuousClock.now
        lastBatchProfile = nil
        let batchSize = seeds.count
        let runtimeOperators = makeRuntimeOperators()
        let resultBuilder = SearchBatchResultBuilder(
            runtimeConfig: runtimeConfig,
            excludedMassChannels: runtimeOperators.excludedMassChannels()
        )
        var timings = SearchBatchProfile()
        let preflight = SearchConfigPreflight(
            searchConfig: searchConfig,
            useParamEmbedding: useParamEmbedding
        )
        let batchSetup = buildBatchSetup(
            seeds: seeds,
            initSeedOffset: initSeedOffset,
            searchConfig: searchConfig,
            frameCapture: frameCapture,
            preflight: preflight,
            explicitParamsBatch: explicitParamsBatch,
            explicitInitialStateBatch: explicitInitialStateBatch,
            timings: &timings
        )
        let initialConditionFamily = batchSetup.initialConditionFamily
        let activityConfig = batchSetup.activityConfig
        let stabilityConfig = batchSetup.stabilityConfig
        let usesActivityMetrics = batchSetup.usesActivityMetrics
        let captureConfig = batchSetup.captureConfig
        var ABatch = batchSetup.massBatch
        var PBatch = batchSetup.paramBatch
        var foodBatch = batchSetup.foodBatch
        let wallMask = batchSetup.wallMask
        let chemField = batchSetup.chemField
        let persistentMetalRunner = batchSetup.persistentMetalRunner
        let massObservationSyncStart = persistentMetalRunner?.massObservationSynchronizationCount ?? 0
        let metalSummaryChannelWeights = summaryChannelWeights(searchConfig: searchConfig)
        let interventionsByStep = batchSetup.interventionsByStep
        let rolloutContext = SearchRolloutSampleContext(
            batchSize: batchSize,
            runtimeConfig: runtimeConfig,
            searchConfig: searchConfig,
            stabilityConfig: stabilityConfig
        )
        var rolloutAccumulator = SearchRolloutAccumulator(
            context: rolloutContext,
            activityConfig: activityConfig,
            usesActivityMetrics: usesActivityMetrics
        )
        var pendingMetalSteps = 0
        var pendingMetalStartStep = 1
        var capturedCoherentTransportReference = false
        var finalObservedMassMap: MLXArray?
        let rolloutStart = ContinuousClock.now
        for step in 1...searchConfig.steps {
            if let runner = persistentMetalRunner {
                if let stepInterventions = interventionsByStep[step], !stepInterventions.isEmpty {
                    flushPendingMetalSteps(
                        runner: runner,
                        pendingMetalSteps: &pendingMetalSteps,
                        pendingMetalStartStep: pendingMetalStartStep,
                        batchSize: batchSize
                    )
                    for intervention in stepInterventions {
                        runtimeOperators.applyIntervention(runner: runner, intervention: intervention)
                    }
                }
                if pendingMetalSteps == 0 {
                    pendingMetalStartStep = step
                }
                pendingMetalSteps += 1
            } else {
                guard let stepper else {
                    fatalError("SearchEngine backend=metal-full requires the persistent Metal runner path.")
                }
                advanceBatch(
                    step: step,
                    stepper: stepper,
                    runtimeOperators: runtimeOperators,
                    massBatch: &ABatch,
                    paramBatch: &PBatch,
                    foodBatch: &foodBatch,
                    wallMask: wallMask,
                    chemField: chemField,
                    includeInterventions: true,
                    includeBeamMutation: true
                )

                if step % 20 == 0 {
                    eval(ABatch)
                    if let P = PBatch { eval(P) }
                }
            }

            let shouldCaptureFrame = if let capture = captureConfig {
                (capture.includeWarmup || step > searchConfig.warmupSteps) && step % capture.stride == 0
            } else {
                false
            }
            let shouldCaptureActivity = activityConfig?.enabled == true &&
                step > searchConfig.warmupSteps &&
                step % (activityConfig?.interval ?? 1) == 0
            let shouldRecordSample = step > searchConfig.warmupSteps &&
                (step - searchConfig.warmupSteps) % searchConfig.recordInterval == 0
            let shouldCaptureCoherentTransportReference = shouldRecordSample &&
                !capturedCoherentTransportReference &&
                rolloutContext.shouldCaptureCoherentTransportReference(step: step)
            let needsRunnerState = shouldCaptureFrame
                || shouldCaptureActivity
                || shouldRecordSample
            if needsRunnerState, let runner = persistentMetalRunner, pendingMetalSteps > 0 {
                flushPendingMetalSteps(
                    runner: runner,
                    pendingMetalSteps: &pendingMetalSteps,
                    pendingMetalStartStep: pendingMetalStartStep,
                    batchSize: batchSize
                )
            }
            let needsMaterializedMassMap = shouldCaptureFrame
                || shouldCaptureActivity
                || shouldCaptureCoherentTransportReference
            var summarySample: FlowLeniaMetalMassSummary?
            var massMap: MLXArray?
            if let runner = persistentMetalRunner {
                if shouldRecordSample {
                    let observationStart = ContinuousClock.now
                    let observation = runner.observeMass(
                        occupancyThreshold: searchConfig.occupancyThreshold,
                        includeGyration: true,
                        channelWeights: metalSummaryChannelWeights,
                        materializeMap: needsMaterializedMassMap
                    )
                    summarySample = observation.summary
                    massMap = observation.massMap
                    let elapsed = durationMs(observationStart.duration(to: ContinuousClock.now))
                    if needsMaterializedMassMap {
                        timings.combinedObservationMs += elapsed
                    } else {
                        timings.summaryReductionMs += elapsed
                    }
                } else if needsMaterializedMassMap {
                    let materializationStart = ContinuousClock.now
                    massMap = runner.materializeMassMap(channelWeights: metalSummaryChannelWeights)
                    timings.materializationMs += durationMs(materializationStart.duration(to: ContinuousClock.now))
                }
                if shouldCaptureActivity {
                    let materializationStart = ContinuousClock.now
                    PBatch = runner.materializeParams()
                    timings.materializationMs += durationMs(materializationStart.duration(to: ContinuousClock.now))
                }
            } else if shouldCaptureFrame || shouldCaptureActivity || shouldRecordSample {
                massMap = resultBuilder.massMapFromBatch(ABatch, searchConfig: searchConfig)
            }
            if step == searchConfig.steps, persistentMetalRunner != nil {
                finalObservedMassMap = massMap
            }

            if shouldCaptureFrame {
                guard let capture = captureConfig, let massMap else {
                    fatalError("Frame capture requested but inputs are missing.")
                }
                let sampleMap = massMap[capture.sampleIndex, 0..., 0...]
                let data = frameDataFromMassMap(sampleMap)
                capture.handler(step, runtimeConfig.sx, runtimeConfig.sy, data)
                if capture.stateHandler != nil || capture.flowHandler != nil {
                    let massState: MLXArray
                    if let runner = persistentMetalRunner {
                        massState = runner.materializeMass()
                    } else {
                        massState = ABatch
                    }
                    if let stateHandler = capture.stateHandler {
                        let sampleState = massState[capture.sampleIndex, 0..., 0..., 0...]
                        let flatState = sampleState.flattened()
                        eval(flatState)
                        stateHandler(
                            step,
                            runtimeConfig.sx,
                            runtimeConfig.sy,
                            runtimeConfig.channels,
                            flatState.asArray(Float.self)
                        )
                    }
                    if let flowHandler = capture.flowHandler {
                        let vizKernels: CompiledKernels?
                        if let metalFullKernels {
                            vizKernels = metalFullKernels
                        } else if case let .mlx(batched, _)? = stepper {
                            vizKernels = batched.kernels
                        } else {
                            vizKernels = nil
                        }
                        guard let vizKernels else {
                            fatalError("Flow capture requested but no compiled kernels are available for this backend.")
                        }
                        let fields = flowGrowthVizFields(
                            state: massState,
                            sampleIndex: capture.sampleIndex,
                            kernels: vizKernels,
                            config: batchedConfigFromRuntime(runtimeConfig),
                            wallPotential: environmentPotential
                        )
                        flowHandler(step, runtimeConfig.sx, runtimeConfig.sy, fields.flow, fields.growth)
                    }
                }
            }

            if shouldCaptureActivity {
                guard let P = PBatch else {
                    fatalError("Activity tracking requires parameter embedding.")
                }
                guard let activityConfig, let massMap else {
                    fatalError("Activity tracking requested but inputs are missing.")
                }
                rolloutAccumulator.recordActivity(
                    massMap: massMap,
                    paramMap: P,
                    step: step,
                    config: activityConfig,
                    border: runtimeConfig.border
                )
            }

            if shouldRecordSample {
                rolloutAccumulator.recordSample(
                    step: step,
                    summarySample: summarySample,
                    massMap: massMap,
                    energyPerSample: summarySample == nil && massMap != nil ? runtimeOperators.energyFromBatch(ABatch) : nil
                )
                if shouldCaptureCoherentTransportReference {
                    capturedCoherentTransportReference = true
                }
            }
        }

        if let runner = persistentMetalRunner {
            flushPendingMetalSteps(
                runner: runner,
                pendingMetalSteps: &pendingMetalSteps,
                pendingMetalStartStep: pendingMetalStartStep,
                batchSize: batchSize
            )
        }
        timings.rolloutMs = durationMs(rolloutStart.duration(to: ContinuousClock.now))

        let postprocessStart = ContinuousClock.now
        let rolloutSummary = rolloutAccumulator.finalize(recordInterval: searchConfig.recordInterval)

        let terminalMassMap: MLXArray?
        let terminalStateBatch: MLXArray?
        let terminalParamBatch: MLXArray?
        let terminalFoodMass: [Float]?
        if let runner = persistentMetalRunner {
            let materializationStart = ContinuousClock.now
            if searchConfig.captureTerminalPatches {
                terminalMassMap = nil
                if useParamEmbedding {
                    let state = runner.materializeState()
                    terminalStateBatch = state.mass
                    terminalParamBatch = state.params
                } else {
                    terminalStateBatch = runner.materializeMass()
                    terminalParamBatch = nil
                }
            } else {
                terminalMassMap = finalObservedMassMap
                    ?? runner.materializeMassMap(channelWeights: metalSummaryChannelWeights)
                terminalStateBatch = nil
                terminalParamBatch = nil
            }
            terminalFoodMass = runner.summarizeFoodMass()
            timings.materializationMs += durationMs(materializationStart.duration(to: ContinuousClock.now))
        } else {
            terminalMassMap = nil
            terminalStateBatch = ABatch
            terminalParamBatch = PBatch
            terminalFoodMass = foodBatch.map(foodMassBySample)
        }
        if let runner = persistentMetalRunner {
            timings.massObservationSynchronizations =
                runner.massObservationSynchronizationCount - massObservationSyncStart
        }

        let results = resultBuilder.build(
            seeds: seeds,
            initSeedOffset: initSeedOffset,
            searchConfig: searchConfig,
            initialConditionFamily: initialConditionFamily,
            activityConfig: activityConfig,
            stabilityConfig: stabilityConfig,
            usesActivityMetrics: usesActivityMetrics,
            rolloutSummary: rolloutSummary,
            terminalMassMap: terminalMassMap,
            terminalStateBatch: terminalStateBatch,
            terminalParamBatch: terminalParamBatch,
            paramsBySample: batchSetup.resolvedParamsBySample,
            foodInitialMass: batchSetup.initialFoodMass,
            foodFinalMass: terminalFoodMass
        )
        timings.postprocessMs = durationMs(postprocessStart.duration(to: ContinuousClock.now))
        timings.totalMs = durationMs(totalStart.duration(to: ContinuousClock.now))
        lastBatchProfile = timings
        return results
    }

    private func buildBatchSetup(
        seeds: [Int],
        initSeedOffset: Int,
        searchConfig: SearchConfig,
        frameCapture: FrameCapture?,
        preflight: SearchConfigPreflight,
        explicitParamsBatch: [ResolvedParams]?,
        explicitInitialStateBatch: [InitStatePatchConfig?]?,
        timings: inout SearchBatchProfile
    ) -> SearchBatchSetup {
        let batchSize = seeds.count
        let initializationBuilder = makeInitializationBuilder()
        let runtimeOperators = makeRuntimeOperators()
        let randomParamsBySample: [ResolvedParams]?
        let activeMetalKernels: CompiledKernels?
        if let corpus = explicitParamsBatch {
            precondition(
                corpus.count == batchSize,
                "explicitParamsBatch count (\(corpus.count)) must equal batch size (\(batchSize))"
            )
            precondition(
                !useParamEmbedding && runtimeConfig.backend == .metalFull,
                "explicitParamsBatch requires metal-full backend without parameter embedding"
            )
            randomParamsBySample = corpus
            activeMetalKernels = compilePopulationKernels(
                paramsBatch: corpus,
                config: batchedConfig,
                c0: runtimeConfig.c0,
                c1: runtimeConfig.c1
            )
        } else if !useParamEmbedding,
           runtimeConfig.backend == .metalFull,
           let ranges = runtimeConfig.randomParamRanges {
            randomParamsBySample = seeds.map {
                generateRandomParams(seed: $0, nbK: runtimeConfig.nbK, ranges: ranges)
            }
            activeMetalKernels = compilePopulationKernels(
                paramsBatch: randomParamsBySample!,
                config: batchedConfig,
                c0: runtimeConfig.c0,
                c1: runtimeConfig.c1
            )
        } else {
            randomParamsBySample = nil
            activeMetalKernels = metalFullKernels
        }
        let initialConditionFamily: String
        if explicitInitialStateBatch != nil {
            initialConditionFamily = "explicit_corpus_state_batch_v1"
        } else {
            initialConditionFamily = morphospaceInitialConditionFamily(
                InitConfig(
                    seed: runtimeConfig.initSeed,
                    patches: runtimeConfig.patches,
                    a_uniform: runtimeConfig.aUniform,
                    p_uniform: runtimeConfig.pUniform,
                    state_patch: runtimeConfig.statePatch,
                    p_state_patch: runtimeConfig.paramPatch
                )
            )
        }
        let activityConfig = preflight.activityConfig
        let stabilityConfig = preflight.stabilityConfig
        let usesActivityMetrics = preflight.metricRequirements.usesActivity
        let captureConfig = SearchConfigPreflight.captureConfig(frameCapture, batchSize: batchSize)

        let stateBuildStart = ContinuousClock.now
        let initialArrays: [MLXArray]
        if let stateBatch = explicitInitialStateBatch {
            precondition(
                stateBatch.count == batchSize,
                "explicitInitialStateBatch count (\(stateBatch.count)) must equal batch size (\(batchSize))"
            )
            initialArrays = stateBatch.enumerated().map { index, statePatch in
                if let statePatch {
                    return initializationBuilder.buildInitialState(statePatch: statePatch)
                }
                return initializationBuilder.buildInitialState(seed: seeds[index] + initSeedOffset)
            }
        } else {
            initialArrays = seeds.map { seed in
                initializationBuilder.buildInitialState(seed: seed + initSeedOffset)
            }
        }
        timings.stateBuildMs = durationMs(stateBuildStart.duration(to: ContinuousClock.now))

        var massBatch = MLX.stacked(initialArrays)

        var paramBatch: MLXArray?
        if useParamEmbedding {
            let parameterBuildStart = ContinuousClock.now
            let initialParams = seeds.map { seed in
                initializationBuilder.buildInitialParameterState(seed: seed + initSeedOffset + 1_000_000)!
            }
            paramBatch = MLX.stacked(initialParams)
            timings.parameterBuildMs = durationMs(parameterBuildStart.duration(to: ContinuousClock.now))
        } else if let kernels = activeMetalKernels {
            let parameterBuildStart = ContinuousClock.now
            let h = kernels.h
            if h.shape.count == 2 {
                paramBatch = MLX.broadcast(
                    h.reshaped([batchSize, 1, 1, runtimeConfig.nbK]),
                    to: [batchSize, runtimeConfig.sx, runtimeConfig.sy, runtimeConfig.nbK]
                )
            } else if let template = staticParamTemplate {
                paramBatch = MLX.broadcast(
                    template,
                    to: [batchSize, runtimeConfig.sx, runtimeConfig.sy, template.shape[3]]
                )
            } else {
                fatalError("Metal full static parameter template is unavailable.")
            }
            timings.parameterBuildMs = durationMs(parameterBuildStart.duration(to: ContinuousClock.now))
        }

        var foodBatch: MLXArray?
        var initialFoodMass: [Float]?
        if let foodConfig = runtimeConfig.food, foodConfig.enabled {
            let foodBuildStart = ContinuousClock.now
            let initialFood = seeds.map { seed in
                initializationBuilder.buildInitialFoodFieldIfEnabled(seed: seed + initSeedOffset + 2_000_000)!
            }
            foodBatch = MLX.stacked(initialFood)
            initialFoodMass = foodBatch.map(foodMassBySample)
            timings.foodBuildMs = durationMs(foodBuildStart.duration(to: ContinuousClock.now))
        }

        let wallBuildStart = ContinuousClock.now
        let wallMask = initializationBuilder.runtimeWallMask()
        timings.wallBuildMs = durationMs(wallBuildStart.duration(to: ContinuousClock.now))

        let chemFieldBuildStart = ContinuousClock.now
        let chemField = initializationBuilder.runtimeChemotaxisField()
        timings.chemFieldBuildMs = durationMs(chemFieldBuildStart.duration(to: ContinuousClock.now))

        let persistentMetalRunner: FlowLeniaMetalFullStateRunner?
        if let kernels = activeMetalKernels {
            let runnerSetupStart = ContinuousClock.now
            let runner = reusableMetalFullRunner(batchSize: batchSize, kernels: kernels)
            runner.reset(
                mass: massBatch,
                params: paramBatch!,
                wallMask: wallMask,
                staticChannelFields: runtimeOperators.metalStaticChannelFields(chemField: chemField),
                food: runtimeOperators.metalFoodState(foodBatch: foodBatch)
            )
            persistentMetalRunner = runner
            timings.runnerSetupMs = durationMs(runnerSetupStart.duration(to: ContinuousClock.now))
        } else {
            runtimeOperators.applyWallMaskIfNeeded(
                massBatch: &massBatch,
                paramBatch: &paramBatch,
                foodBatch: &foodBatch,
                wallMask: wallMask
            )
            persistentMetalRunner = nil
        }

        return SearchBatchSetup(
            resolvedParamsBySample: randomParamsBySample,
            initialConditionFamily: initialConditionFamily,
            activityConfig: activityConfig,
            stabilityConfig: stabilityConfig,
            usesActivityMetrics: usesActivityMetrics,
            captureConfig: captureConfig,
            massBatch: massBatch,
            paramBatch: paramBatch,
            foodBatch: foodBatch,
            initialFoodMass: initialFoodMass,
            wallMask: wallMask,
            chemField: chemField,
            persistentMetalRunner: persistentMetalRunner,
            interventionsByStep: Dictionary(grouping: runtimeConfig.interventions, by: \.step)
        )
    }

    private func foodMassBySample(_ food: MLXArray) -> [Float] {
        let sum = food.sum(axes: [1, 2])
        eval(sum)
        return sum.asArray(Float.self)
    }

    func expressedSeedPatch(
        name: String,
        sourceID: String,
        runID: String?,
        campaignID: String?,
        recordedAt: Date?,
        score: Float?,
        metrics: SimulationMetrics,
        warmupSteps: Int,
        cropThreshold: Float,
        padding: Int
    ) -> ResearchSeedPatch {
        let kernels = compileKernels(
            params: runtimeConfig.params,
            config: batchedConfig,
            c0: runtimeConfig.c0,
            c1: runtimeConfig.c1
        )
        let massEngine = FlowLeniaBatched(
            config: batchedConfig,
            kernels: kernels,
            wallPotential: environmentPotential
        )
        let paramsEngine: FlowLeniaParamsBatched? = useParamEmbedding
            ? FlowLeniaParamsBatched(
                config: batchedConfig,
                kernels: kernels,
                mixMode: runtimeConfig.parameterEmbedding.mix,
                mixSeed: runtimeConfig.parameterEmbedding.mix_seed,
                wallPotential: environmentPotential
            )
            : nil

        let initializationBuilder = makeInitializationBuilder()
        let runtimeOperators = makeRuntimeOperators()
        let warmupStepper = Stepper.mlx(massEngine, paramsEngine)
        var ABatch = initializationBuilder.buildInitialState(seed: runtimeConfig.initSeed)
            .expandedDimensions(axis: 0)

        var PBatch = initializationBuilder.buildInitialParameterState(seed: runtimeConfig.initSeed + 1_000_000)?
            .expandedDimensions(axis: 0)

        var foodBatch = initializationBuilder.buildInitialFoodFieldIfEnabled(seed: runtimeConfig.initSeed + 2_000_000)?
            .expandedDimensions(axis: 0)

        let wallMask = initializationBuilder.runtimeWallMask(includeEnvironmentMask: true)
        let chemField = initializationBuilder.runtimeChemotaxisField()

        runtimeOperators.applyWallMaskIfNeeded(
            massBatch: &ABatch,
            paramBatch: &PBatch,
            foodBatch: &foodBatch,
            wallMask: wallMask
        )

        for stepIndex in 0..<max(0, warmupSteps) {
            advanceBatch(
                step: stepIndex + 1,
                stepper: warmupStepper,
                runtimeOperators: runtimeOperators,
                massBatch: &ABatch,
                paramBatch: &PBatch,
                foodBatch: &foodBatch,
                wallMask: wallMask,
                chemField: chemField,
                includeInterventions: false,
                includeBeamMutation: false
            )
        }

        eval(ABatch)
        let worldState = WorldState(
            width: runtimeConfig.sx,
            height: runtimeConfig.sy,
            channels: runtimeConfig.channels,
            values: ABatch[0, 0..., 0..., 0...].asArray(Float.self)
        )
        let excluded = runtimeOperators.excludedMassChannels()
        let mass = expressedSeedMassMap(
            world: worldState,
            excludedChannels: excluded
        )
        let bounds = researchSeedActiveBoundingBox(
            massMap: mass,
            width: runtimeConfig.sx,
            height: runtimeConfig.sy,
            threshold: cropThreshold
        )
        let paddedBounds = expandedSeedBounds(
            bounds: bounds,
            width: runtimeConfig.sx,
            height: runtimeConfig.sy,
            padding: padding
        )

        let patchWidth = paddedBounds.maxX - paddedBounds.minX + 1
        let patchHeight = paddedBounds.maxY - paddedBounds.minY + 1
        var patch = [Float](repeating: 0, count: patchWidth * patchHeight * runtimeConfig.channels)
        for x in paddedBounds.minX...paddedBounds.maxX {
            for y in paddedBounds.minY...paddedBounds.maxY {
                let sourceBase = ((x * runtimeConfig.sy) + y) * runtimeConfig.channels
                let targetX = x - paddedBounds.minX
                let targetY = y - paddedBounds.minY
                let targetBase = ((targetX * patchHeight) + targetY) * runtimeConfig.channels
                for channel in 0..<runtimeConfig.channels {
                    patch[targetBase + channel] = worldState.values[sourceBase + channel]
                }
            }
        }

        return ResearchSeedPatch(
            sourceID: sourceID,
            name: name,
            width: patchWidth,
            height: patchHeight,
            channels: runtimeConfig.channels,
            data: patch,
            runID: runID,
            campaignID: campaignID,
            recordedAt: recordedAt,
            score: score,
            metrics: metrics,
            kernelParams: KernelParams(
                r: runtimeConfig.params.r,
                b: runtimeConfig.params.b,
                w: runtimeConfig.params.w,
                a: runtimeConfig.params.a,
                m: runtimeConfig.params.m,
                s: runtimeConfig.params.s,
                h: runtimeConfig.params.h,
                R: runtimeConfig.params.R
            )
        )
    }

    private func frameDataFromMassMap(_ massMap: MLXArray) -> Data {
        let flat = massMap.flattened()
        eval(flat)
        let floatData: [Float] = flat.asArray(Float.self)
        var bytes = [UInt8](repeating: 0, count: floatData.count)
        for (i, value) in floatData.enumerated() {
            let clamped = max(0.0, min(1.0, value))
            bytes[i] = UInt8(clamped * 255.0)
        }
        return Data(bytes)
    }

}

extension SearchEngine {
    func benchmarkRolloutStageTimings(
        seeds: [Int],
        initSeedOffset: Int,
        searchConfig: SearchConfig
    ) -> FlowSandboxMetalStageTimings? {
        guard runtimeConfig.backend == .metalFull,
              metalFullKernels != nil else {
            return nil
        }
        let preflight = SearchConfigPreflight(
            searchConfig: searchConfig,
            useParamEmbedding: useParamEmbedding
        )
        var timings = SearchBatchProfile()
        let batchSetup = buildBatchSetup(
            seeds: seeds,
            initSeedOffset: initSeedOffset,
            searchConfig: searchConfig,
            frameCapture: nil,
            preflight: preflight,
            explicitParamsBatch: nil,
            explicitInitialStateBatch: nil,
            timings: &timings
        )
        guard let runner = batchSetup.persistentMetalRunner else {
            return nil
        }
        let preProfileSteps = min(max(searchConfig.warmupSteps, 0), max(searchConfig.steps - 1, 0))
        if preProfileSteps > 0 {
            runner.step(count: preProfileSteps)
        }
        return runner.profileCurrentStep()
    }
}

struct SearchParameterPatch {
    let origins: [SIMD2<Int32>]
    let size: Int
    let deltas: [Float]
    let clip: [Float]?

    func asMetalPatchBatch() -> FlowLeniaMetalParameterPatchBatch {
        FlowLeniaMetalParameterPatchBatch(
            origins: origins,
            size: size,
            deltas: deltas,
            clip: clip
        )
    }
}

struct SearchZeroStatePatch {
    let origins: [SIMD2<Int32>]
    let size: Int
}

public func benchmarkSearchEngineBackend(
    gridSize: Int,
    batchSize: Int,
    steps: Int,
    params: ResolvedParams,
    backend: FlowLeniaComputeBackend,
    warmupRuns: Int = 1,
    observationStride: Int? = nil
) -> SearchBenchmarkResult {
    if let observationStride {
        precondition(observationStride > 0, "Search benchmark observation stride must be positive.")
    }
    let runtimeConfig = flowLeniaBenchmarkRuntimeConfig(
        gridSize: gridSize,
        steps: steps,
        params: params,
        backend: backend
    )
    let engine = SearchEngine(runtimeConfig: runtimeConfig)
    let warmupSteps = steps > 1 ? max(1, steps / 5) : 0
    let measuredSteps = max(steps - warmupSteps, 1)
    let searchConfig = SearchConfig(
        steps: max(1, steps),
        recordInterval: max(1, measuredSteps / 8),
        warmupSteps: warmupSteps,
        occupancyThreshold: 1e-3,
        massChannel: 0,
        scoreWeights: [:],
        filters: [:],
        complexity: nil,
        activity: nil,
        stability: nil,
        kSurvival: nil,
        moments: nil
    )
    let seeds = Array(0..<batchSize)
    let frameCapture = observationStride.map { stride in
        FrameCapture(stride: stride) { _, _, _, _ in }
    }
    for run in 0..<max(warmupRuns, 0) {
        _ = engine.runBatch(
            seeds: seeds,
            initSeedOffset: (run + 1) * 100_000,
            searchConfig: searchConfig,
            frameCapture: frameCapture
        )
    }

    let measuredOffset = (max(warmupRuns, 0) + 1) * 100_000
    let stageTimings = backend == .metalFull
        ? engine.benchmarkRolloutStageTimings(
            seeds: seeds,
            initSeedOffset: measuredOffset,
            searchConfig: searchConfig
        )
        : nil
    let start = Date()
    _ = engine.runBatch(
        seeds: seeds,
        initSeedOffset: measuredOffset,
        searchConfig: searchConfig,
        frameCapture: frameCapture
    )
    let duration = Date().timeIntervalSince(start)
    guard let profile = engine.lastBatchProfile else {
        preconditionFailure("Search benchmark expected a batch profile.")
    }
    return SearchBenchmarkResult(
        backend: backend,
        gridSize: gridSize,
        steps: steps,
        batchSize: batchSize,
        duration: duration,
        seedsPerSecond: Double(batchSize) / duration,
        simStepsPerSecond: Double(batchSize * steps) / duration,
        profile: profile,
        stageTimings: stageTimings
    )
}
