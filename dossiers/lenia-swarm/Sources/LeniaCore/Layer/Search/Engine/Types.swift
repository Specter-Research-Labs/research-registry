import Foundation

public struct SearchConfig: Sendable {
    public let steps: Int
    public let recordInterval: Int
    public let warmupSteps: Int
    public let occupancyThreshold: Float
    public let componentThreshold: Float?
    public let massChannel: Int
    public let scoreWeights: [String: Float]
    public let filters: [String: Float]
    public let complexity: ComplexityConfig?
    public let activity: ActivityConfig?
    public let stability: StabilityConfig?
    public let kSurvival: KSurvivalConfig?
    public let moments: MomentsConfig?
    public let captureTerminalPatches: Bool

    public init(
        steps: Int,
        recordInterval: Int,
        warmupSteps: Int,
        occupancyThreshold: Float,
        componentThreshold: Float? = nil,
        massChannel: Int,
        scoreWeights: [String: Float],
        filters: [String: Float],
        complexity: ComplexityConfig?,
        activity: ActivityConfig?,
        stability: StabilityConfig?,
        kSurvival: KSurvivalConfig? = nil,
        moments: MomentsConfig? = nil,
        captureTerminalPatches: Bool = false
    ) {
        self.steps = steps
        self.recordInterval = recordInterval
        self.warmupSteps = warmupSteps
        self.occupancyThreshold = occupancyThreshold
        self.componentThreshold = componentThreshold
        self.massChannel = massChannel
        self.scoreWeights = scoreWeights
        self.filters = filters
        self.complexity = complexity
        self.activity = activity
        self.stability = stability
        self.kSurvival = kSurvival
        self.moments = moments
        self.captureTerminalPatches = captureTerminalPatches
    }
}

public struct FrameCapture {
    public let stride: Int
    public let includeWarmup: Bool
    public let sampleIndex: Int
    public let handler: (_ step: Int, _ width: Int, _ height: Int, _ data: Data) -> Void
    public let stateHandler: ((_ step: Int, _ width: Int, _ height: Int, _ channels: Int, _ values: [Float]) -> Void)?
    // When set, the engine recomputes the velocity and growth fields from the
    // captured state and forwards them. Off by default so search is unaffected.
    public let flowHandler: ((_ step: Int, _ width: Int, _ height: Int, _ flow: [Float], _ growth: [Float]) -> Void)?

    public init(
        stride: Int,
        includeWarmup: Bool = false,
        sampleIndex: Int = 0,
        handler: @escaping (_ step: Int, _ width: Int, _ height: Int, _ data: Data) -> Void,
        stateHandler: ((_ step: Int, _ width: Int, _ height: Int, _ channels: Int, _ values: [Float]) -> Void)? = nil,
        flowHandler: ((_ step: Int, _ width: Int, _ height: Int, _ flow: [Float], _ growth: [Float]) -> Void)? = nil
    ) {
        self.stride = stride
        self.includeWarmup = includeWarmup
        self.sampleIndex = sampleIndex
        self.handler = handler
        self.stateHandler = stateHandler
        self.flowHandler = flowHandler
    }
}

public struct BatchSimulationResult: Sendable {
    public let seed: Int
    public let initSeed: Int
    public let metrics: SimulationMetrics
    public let params: ResolvedParams
    public let activity: [ActivitySnapshot]?
    public let initialConditionFamily: String
    public let descriptorBundle: MorphospaceDescriptorBundle
    public let terminalStatePatch: InitStatePatchConfig?
    public let terminalParamPatch: InitStatePatchConfig?

    public init(
        seed: Int,
        initSeed: Int,
        metrics: SimulationMetrics,
        params: ResolvedParams,
        activity: [ActivitySnapshot]?,
        initialConditionFamily: String,
        descriptorBundle: MorphospaceDescriptorBundle,
        terminalStatePatch: InitStatePatchConfig?,
        terminalParamPatch: InitStatePatchConfig?
    ) {
        self.seed = seed
        self.initSeed = initSeed
        self.metrics = metrics
        self.params = params
        self.activity = activity
        self.initialConditionFamily = initialConditionFamily
        self.descriptorBundle = descriptorBundle
        self.terminalStatePatch = terminalStatePatch
        self.terminalParamPatch = terminalParamPatch
    }
}

public struct SearchBatchProfile: Sendable {
    public let stateBuildMs: Double
    public let parameterBuildMs: Double
    public let foodBuildMs: Double
    public let wallBuildMs: Double
    public let chemFieldBuildMs: Double
    public let runnerSetupMs: Double
    public let rolloutMs: Double
    public let summaryReductionMs: Double
    public let combinedObservationMs: Double
    public let materializationMs: Double
    public let massObservationSynchronizations: Int
    public let postprocessMs: Double
    public let totalMs: Double

    public init(
        stateBuildMs: Double,
        parameterBuildMs: Double,
        foodBuildMs: Double,
        wallBuildMs: Double,
        chemFieldBuildMs: Double,
        runnerSetupMs: Double,
        rolloutMs: Double,
        summaryReductionMs: Double,
        combinedObservationMs: Double,
        materializationMs: Double,
        massObservationSynchronizations: Int,
        postprocessMs: Double,
        totalMs: Double
    ) {
        self.stateBuildMs = stateBuildMs
        self.parameterBuildMs = parameterBuildMs
        self.foodBuildMs = foodBuildMs
        self.wallBuildMs = wallBuildMs
        self.chemFieldBuildMs = chemFieldBuildMs
        self.runnerSetupMs = runnerSetupMs
        self.rolloutMs = rolloutMs
        self.summaryReductionMs = summaryReductionMs
        self.combinedObservationMs = combinedObservationMs
        self.materializationMs = materializationMs
        self.massObservationSynchronizations = massObservationSynchronizations
        self.postprocessMs = postprocessMs
        self.totalMs = totalMs
    }
}

public struct SearchBenchmarkResult: Sendable {
    public let backend: FlowLeniaComputeBackend
    public let gridSize: Int
    public let steps: Int
    public let batchSize: Int
    public let duration: TimeInterval
    public let seedsPerSecond: Double
    public let simStepsPerSecond: Double
    public let profile: SearchBatchProfile
    public let stageTimings: FlowSandboxMetalStageTimings?

    public init(
        backend: FlowLeniaComputeBackend,
        gridSize: Int,
        steps: Int,
        batchSize: Int,
        duration: TimeInterval,
        seedsPerSecond: Double,
        simStepsPerSecond: Double,
        profile: SearchBatchProfile,
        stageTimings: FlowSandboxMetalStageTimings? = nil
    ) {
        self.backend = backend
        self.gridSize = gridSize
        self.steps = steps
        self.batchSize = batchSize
        self.duration = duration
        self.seedsPerSecond = seedsPerSecond
        self.simStepsPerSecond = simStepsPerSecond
        self.profile = profile
        self.stageTimings = stageTimings
    }
}
