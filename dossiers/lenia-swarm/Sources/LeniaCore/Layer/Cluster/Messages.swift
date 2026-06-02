import Distributed
import Foundation

// MARK: - Search Config (Codable version)

public struct ParsedSearchConfig: Codable, Sendable {
    public let count: Int
    public let seedStart: Int
    public let seeds: [Int]?
    public let seedStride: Int
    public let initSeedOffset: Int?
    public let steps: Int
    public let recordInterval: Int
    public let warmupSteps: Int
    public let occupancyThreshold: Float
    public let componentThreshold: Float?
    public let massChannel: Int
    public let scoreWeights: [String: Float]
    public let filters: [String: Float]
    public let overrides: [String: AnyCodable]
    public let topK: Int
    public let batchSize: Int
    public let seedsPerJob: Int?
    public let complexity: ComplexityConfig?
    public let activity: ActivityConfig?
    public let stability: StabilityConfig?
    public let kSurvival: KSurvivalConfig?
    public let moments: MomentsConfig?
    public let collection: CollectionConfig?

    public enum CodingKeys: String, CodingKey {
        case count
        case seedStart = "seed_start"
        case seeds
        case seedStride = "seed_stride"
        case initSeedOffset = "init_seed_offset"
        case steps
        case recordInterval = "record_interval"
        case warmupSteps = "warmup_steps"
        case occupancyThreshold = "occupancy_threshold"
        case componentThreshold = "component_threshold"
        case massChannel = "mass_channel"
        case scoreWeights = "score_weights"
        case filters
        case overrides
        case topK = "top_k"
        case batchSize = "batch_size"
        case seedsPerJob = "seeds_per_job"
        case complexity
        case activity
        case stability
        case kSurvival = "k_survival"
        case moments
        case collection
    }

    public init(
        count: Int,
        seedStart: Int,
        seeds: [Int]? = nil,
        seedStride: Int = 1,
        initSeedOffset: Int? = nil,
        steps: Int,
        recordInterval: Int,
        warmupSteps: Int,
        occupancyThreshold: Float = 0.1,
        componentThreshold: Float? = nil,
        massChannel: Int = -1,
        scoreWeights: [String: Float] = [:],
        filters: [String: Float] = [:],
        overrides: [String: AnyCodable] = [:],
        topK: Int,
        batchSize: Int = 1,
        seedsPerJob: Int? = nil,
        complexity: ComplexityConfig? = nil,
        activity: ActivityConfig? = nil,
        stability: StabilityConfig? = nil,
        kSurvival: KSurvivalConfig? = nil,
        moments: MomentsConfig? = nil,
        collection: CollectionConfig? = nil
    ) {
        self.count = count
        self.seedStart = seedStart
        self.seeds = seeds
        self.seedStride = seedStride
        self.initSeedOffset = initSeedOffset
        self.steps = steps
        self.recordInterval = recordInterval
        self.warmupSteps = warmupSteps
        self.occupancyThreshold = occupancyThreshold
        self.componentThreshold = componentThreshold
        self.massChannel = massChannel
        self.scoreWeights = scoreWeights
        self.filters = filters
        self.overrides = overrides
        self.topK = topK
        self.batchSize = batchSize
        self.seedsPerJob = seedsPerJob
        self.complexity = complexity
        self.activity = activity
        self.stability = stability
        self.kSurvival = kSurvival
        self.moments = moments
        self.collection = collection
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        count = try container.decode(Int.self, forKey: .count)
        seedStart = try container.decode(Int.self, forKey: .seedStart)
        seeds = try container.decodeIfPresent([Int].self, forKey: .seeds)
        seedStride = try container.decode(Int.self, forKey: .seedStride)
        initSeedOffset = try container.decodeIfPresent(Int.self, forKey: .initSeedOffset)
        steps = try container.decode(Int.self, forKey: .steps)
        recordInterval = try container.decode(Int.self, forKey: .recordInterval)
        warmupSteps = try container.decode(Int.self, forKey: .warmupSteps)
        occupancyThreshold = try container.decodeIfPresent(Float.self, forKey: .occupancyThreshold) ?? 0.1
        componentThreshold = try container.decodeIfPresent(Float.self, forKey: .componentThreshold)
        massChannel = try container.decodeIfPresent(Int.self, forKey: .massChannel) ?? -1
        scoreWeights = try container.decodeIfPresent([String: Float].self, forKey: .scoreWeights) ?? [:]
        filters = try container.decodeIfPresent([String: Float].self, forKey: .filters) ?? [:]
        overrides = try container.decodeIfPresent([String: AnyCodable].self, forKey: .overrides) ?? [:]
        topK = try container.decode(Int.self, forKey: .topK)
        batchSize = try container.decodeIfPresent(Int.self, forKey: .batchSize) ?? 1
        seedsPerJob = try container.decodeIfPresent(Int.self, forKey: .seedsPerJob)
        complexity = try container.decodeIfPresent(ComplexityConfig.self, forKey: .complexity)
        activity = try container.decodeIfPresent(ActivityConfig.self, forKey: .activity)
        stability = try container.decodeIfPresent(StabilityConfig.self, forKey: .stability)
        kSurvival = try container.decodeIfPresent(KSurvivalConfig.self, forKey: .kSurvival)
        moments = try container.decodeIfPresent(MomentsConfig.self, forKey: .moments)
        collection = try container.decodeIfPresent(CollectionConfig.self, forKey: .collection)
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(count, forKey: .count)
        try container.encode(seedStart, forKey: .seedStart)
        try container.encodeIfPresent(seeds, forKey: .seeds)
        try container.encode(seedStride, forKey: .seedStride)
        try container.encodeIfPresent(initSeedOffset, forKey: .initSeedOffset)
        try container.encode(steps, forKey: .steps)
        try container.encode(recordInterval, forKey: .recordInterval)
        try container.encode(warmupSteps, forKey: .warmupSteps)
        try container.encode(occupancyThreshold, forKey: .occupancyThreshold)
        try container.encodeIfPresent(componentThreshold, forKey: .componentThreshold)
        try container.encode(massChannel, forKey: .massChannel)
        try container.encode(scoreWeights, forKey: .scoreWeights)
        try container.encode(filters, forKey: .filters)
        try container.encode(overrides, forKey: .overrides)
        try container.encode(topK, forKey: .topK)
        try container.encode(batchSize, forKey: .batchSize)
        try container.encodeIfPresent(seedsPerJob, forKey: .seedsPerJob)
        try container.encodeIfPresent(complexity, forKey: .complexity)
        try container.encodeIfPresent(activity, forKey: .activity)
        try container.encodeIfPresent(stability, forKey: .stability)
        try container.encodeIfPresent(kSurvival, forKey: .kSurvival)
        try container.encodeIfPresent(moments, forKey: .moments)
        try container.encodeIfPresent(collection, forKey: .collection)
    }

    public func overridesAsDict() -> [String: Any] {
        var result: [String: Any] = [:]
        for (key, value) in overrides {
            result[key] = value.value
        }
        return result
    }

    public func toSearchConfig(captureTerminalPatches: Bool = false) -> SearchConfig {
        SearchConfig(
            steps: steps,
            recordInterval: recordInterval,
            warmupSteps: warmupSteps,
            occupancyThreshold: occupancyThreshold,
            componentThreshold: componentThreshold,
            massChannel: massChannel,
            scoreWeights: scoreWeights,
            filters: filters,
            complexity: complexity,
            activity: activity,
            stability: stability,
            kSurvival: kSurvival,
            moments: moments,
            captureTerminalPatches: captureTerminalPatches
        )
    }
}

// MARK: - Job and Result Messages

public struct SimulationJob: Codable, Sendable {
    public let id: String
    public let seedStart: Int
    public let count: Int
    public let baseConfig: LeniaBaseConfig
    public let requestedBackend: String?
    public let searchConfig: ParsedSearchConfig
    public let sweepOverrides: [String: Double]?

    public init(
        id: String,
        seedStart: Int,
        count: Int,
        baseConfig: LeniaBaseConfig,
        requestedBackend: String? = nil,
        searchConfig: ParsedSearchConfig,
        sweepOverrides: [String: Double]?
    ) {
        self.id = id
        self.seedStart = seedStart
        self.count = count
        self.baseConfig = baseConfig
        self.requestedBackend = requestedBackend
        self.searchConfig = searchConfig
        self.sweepOverrides = sweepOverrides
    }
}

public struct RunContext: Codable, Sendable {
    public let runId: String
    public let controllerId: String

    public init(runId: String, controllerId: String) {
        self.runId = runId
        self.controllerId = controllerId
    }
}

public struct SimulationResult: Codable, Sendable {
    public let jobId: String
    public let workerId: String
    public let success: Bool
    public let seedStart: Int
    public let count: Int
    public let results: [SimulationResultData]
    public let errorMessage: String?
    public let durationSeconds: Double

    public init(
        jobId: String,
        workerId: String,
        success: Bool,
        seedStart: Int,
        count: Int,
        results: [SimulationResultData],
        errorMessage: String?,
        durationSeconds: Double
    ) {
        self.jobId = jobId
        self.workerId = workerId
        self.success = success
        self.seedStart = seedStart
        self.count = count
        self.results = results
        self.errorMessage = errorMessage
        self.durationSeconds = durationSeconds
    }
}

public struct WorkerStatus: Codable, Sendable {
    public let capabilities: WorkerBackendCapabilities
    public let workerId: String
    public let hostname: String
    public let currentJob: String?
    public let jobsCompleted: Int
    public let totalSeedsProcessed: Int
    public let isAvailable: Bool

    public init(
        capabilities: WorkerBackendCapabilities,
        workerId: String,
        hostname: String,
        currentJob: String?,
        jobsCompleted: Int,
        totalSeedsProcessed: Int,
        isAvailable: Bool
    ) {
        self.capabilities = capabilities
        self.workerId = workerId
        self.hostname = hostname
        self.currentJob = currentJob
        self.jobsCompleted = jobsCompleted
        self.totalSeedsProcessed = totalSeedsProcessed
        self.isAvailable = isAvailable
    }
}

public struct WorkerBackendCapabilities: Codable, Sendable {
    public let canonicalSearchBackends: [FlowLeniaComputeBackend]
    public let canonicalFlowLeniaBackends: [FlowLeniaComputeBackend]
    public let canonicalSearchPreferredBackend: FlowLeniaComputeBackend
    public let canonicalFlowLeniaPreferredBackend: FlowLeniaComputeBackend

    public init(
        canonicalSearchBackends: [FlowLeniaComputeBackend],
        canonicalFlowLeniaBackends: [FlowLeniaComputeBackend],
        canonicalSearchPreferredBackend: FlowLeniaComputeBackend,
        canonicalFlowLeniaPreferredBackend: FlowLeniaComputeBackend
    ) {
        self.canonicalSearchBackends = canonicalSearchBackends
        self.canonicalFlowLeniaBackends = canonicalFlowLeniaBackends
        self.canonicalSearchPreferredBackend = canonicalSearchPreferredBackend
        self.canonicalFlowLeniaPreferredBackend = canonicalFlowLeniaPreferredBackend
    }
}

public enum SimulationJobBackendRequest: Equatable, Sendable {
    case explicit(FlowLeniaComputeBackend)
    case auto

    public init(configValue: String) throws {
        switch configValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "auto":
            self = .auto
        default:
            self = .explicit(try FlowLeniaComputeBackend(configValue: configValue))
        }
    }
}

public func isSearchBackendCompatible(backend: FlowLeniaComputeBackend, config: LeniaBaseConfig) -> Bool {
    switch backend {
    case .mlx:
        return true
    case .metalFull:
        let border = config.reintegration.border
        guard border == "torus" || border == "wall" else { return false }

        switch config.implementation.mode {
        case "flowlenia_2022_paper_equations":
            break
        case "flowlenia_2022_colab":
            break
        case "custom":
            let validBoundaryPair = (border == "torus" && config.implementation.gradient_boundary == "periodic") ||
                (border == "wall" && config.implementation.gradient_boundary == "zero_pad")
            guard validBoundaryPair else {
                return false
            }
        default:
            return false
        }

        let supportedMixModes = config.channels == 1 ? ["avg"] : ["avg", "stoch"]
        if config.parameter_embedding.enabled && !supportedMixModes.contains(config.parameter_embedding.mix) {
            return false
        }

        return true
    }
}

public func backendRequestValue(for job: SimulationJob) -> String {
    job.requestedBackend ?? job.baseConfig.backend
}

public func resolvedSearchBackend(for capabilities: WorkerBackendCapabilities, job: SimulationJob)
    -> FlowLeniaComputeBackend?
{
    guard let request = try? SimulationJobBackendRequest(configValue: backendRequestValue(for: job)) else {
        return nil
    }
    switch request {
    case .explicit(let backend):
        return capabilities.canonicalSearchBackends.contains(backend) ? backend : nil
    case .auto:
        if capabilities.canonicalSearchBackends.contains(.metalFull),
           isSearchBackendCompatible(backend: .metalFull, config: job.baseConfig) {
            return .metalFull
        }
        return nil
    }
}

private func copyBaseConfig(_ baseConfig: LeniaBaseConfig, backend: String) -> LeniaBaseConfig {
    LeniaBaseConfig(
        backend: backend,
        profile: baseConfig.profile,
        grid: baseConfig.grid,
        channels: baseConfig.channels,
        connectivity: baseConfig.connectivity,
        flow: baseConfig.flow,
        implementation: baseConfig.implementation,
        reintegration: baseConfig.reintegration,
        parameter_embedding: baseConfig.parameter_embedding,
        chemotaxis: baseConfig.chemotaxis,
        obstacle_field: baseConfig.obstacle_field,
        food: baseConfig.food,
        walls: baseConfig.walls,
        environment: baseConfig.environment,
        beam_mutation: baseConfig.beam_mutation,
        params: baseConfig.params,
        init: baseConfig.`init`,
        run: baseConfig.run,
        interventions: baseConfig.interventions
    )
}

public func materializeSimulationJob(_ job: SimulationJob, for status: WorkerStatus) -> SimulationJob? {
    materializeSimulationJob(job, for: status.capabilities)
}

public func materializeSimulationJob(_ job: SimulationJob, for capabilities: WorkerBackendCapabilities)
    -> SimulationJob?
{
    guard let backend = resolvedSearchBackend(for: capabilities, job: job) else {
        return nil
    }
    let requestValue = backendRequestValue(for: job)
    if job.baseConfig.backend == backend.rawValue && job.requestedBackend == nil {
        return job
    }
    if job.baseConfig.backend == backend.rawValue && job.requestedBackend == requestValue {
        return job
    }
    return SimulationJob(
        id: job.id,
        seedStart: job.seedStart,
        count: job.count,
        baseConfig: copyBaseConfig(job.baseConfig, backend: backend.rawValue),
        requestedBackend: requestValue,
        searchConfig: job.searchConfig,
        sweepOverrides: job.sweepOverrides
    )
}

public func restoreRequestedBackend(for job: SimulationJob) -> SimulationJob {
    guard let requestedBackend = job.requestedBackend else {
        return job
    }
    return SimulationJob(
        id: job.id,
        seedStart: job.seedStart,
        count: job.count,
        baseConfig: copyBaseConfig(job.baseConfig, backend: requestedBackend),
        requestedBackend: nil,
        searchConfig: job.searchConfig,
        sweepOverrides: job.sweepOverrides
    )
}

public func workerSupportsSimulationJob(_ status: WorkerStatus, job: SimulationJob) -> Bool {
    resolvedSearchBackend(for: status.capabilities, job: job) != nil
}

func reserveCompatibleSimulationJob(from jobs: inout [SimulationJob], for status: WorkerStatus?) -> SimulationJob? {
    guard !jobs.isEmpty else { return nil }
    guard let status else {
        return jobs.removeFirst()
    }
    guard let index = jobs.firstIndex(where: { workerSupportsSimulationJob(status, job: $0) }) else {
        return nil
    }
    let job = jobs.remove(at: index)
    return materializeSimulationJob(job, for: status)
}

// MARK: - Sweep Job Configuration

public struct SweepJobConfig: Codable, Sendable {
    public let name: String
    public let totalSeeds: Int
    public let steps: Int
    public let seedsPerChunk: Int
    public let gridHeight: Int
    public let gridWidth: Int

    public init(
        name: String,
        totalSeeds: Int,
        steps: Int,
        seedsPerChunk: Int = 10,
        gridHeight: Int = 128,
        gridWidth: Int = 128
    ) {
        self.name = name
        self.totalSeeds = totalSeeds
        self.steps = steps
        self.seedsPerChunk = seedsPerChunk
        self.gridHeight = gridHeight
        self.gridWidth = gridWidth
    }
}

public struct CampaignStatus: Codable, Sendable, Identifiable {
    public let id: UUID
    public let name: String
    public let totalJobs: Int
    public let completedJobs: Int
    public let totalSeeds: Int
    public let processedSeeds: Int
    public let isRunning: Bool
    public let joinedWorkers: [String]
    public let outputDir: String

    public init(
        id: UUID,
        name: String,
        totalJobs: Int,
        completedJobs: Int,
        totalSeeds: Int,
        processedSeeds: Int,
        isRunning: Bool,
        joinedWorkers: [String] = [],
        outputDir: String
    ) {
        self.id = id
        self.name = name
        self.totalJobs = totalJobs
        self.completedJobs = completedJobs
        self.totalSeeds = totalSeeds
        self.processedSeeds = processedSeeds
        self.isRunning = isRunning
        self.joinedWorkers = joinedWorkers
        self.outputDir = outputDir
    }
}

public struct ClusterSummary: Codable, Sendable {
    public let workers: [WorkerStatus]
    public let campaigns: [CampaignStatus]
    public let totalSeedsProcessed: Int
    public let clusterRate: Double
    public let completedJobs: Int
    public let totalJobs: Int
    public let topCreatureCount: Int
    public let bestScore: Float?

    public init(
        workers: [WorkerStatus],
        campaigns: [CampaignStatus],
        totalSeedsProcessed: Int,
        clusterRate: Double,
        completedJobs: Int,
        totalJobs: Int,
        topCreatureCount: Int,
        bestScore: Float?
    ) {
        self.workers = workers
        self.campaigns = campaigns
        self.totalSeedsProcessed = totalSeedsProcessed
        self.clusterRate = clusterRate
        self.completedJobs = completedJobs
        self.totalJobs = totalJobs
        self.topCreatureCount = topCreatureCount
        self.bestScore = bestScore
    }
}

// MARK: - Controller Events

public enum ControllerEvent: Sendable {
    case progress(completed: Int, total: Int, seeds: Int, totalSeeds: Int, rate: Double)
    case finished(elapsed: Double)
    case workerListUpdated([WorkerStatus])
    case creatureDiscovered(SavedCreature)
    case campaignsUpdated([CampaignStatus])
}

// MARK: - Arena Structures

public struct ArenaConfig: Codable, Sendable {
    public let id: UUID
    public let size: Int
    public let maxPlayers: Int

    public init(id: UUID = UUID(), size: Int = 256, maxPlayers: Int = 4) {
        self.id = id
        self.size = size
        self.maxPlayers = maxPlayers
    }
}

public struct ArenaState: Codable, Sendable {
    public let config: ArenaConfig
    public let status: ArenaStatus
    public let participants: [String]

    public init(config: ArenaConfig, status: ArenaStatus, participants: [String]) {
        self.config = config
        self.status = status
        self.participants = participants
    }
}

public enum ArenaStatus: String, Codable, Sendable {
    case lobby
    case running
    case ended
}

public struct ArenaFrame: Codable, Sendable {
    public let arenaId: UUID
    public let step: Int
    public let width: Int
    public let height: Int
    public let data: Data

    public init(arenaId: UUID, step: Int, width: Int, height: Int, data: Data) {
        self.arenaId = arenaId
        self.step = step
        self.width = width
        self.height = height
        self.data = data
    }
}

// MARK: - Global Update (Broadcast from Controller to Workers)

public struct GlobalUpdate: Codable, Sendable {
    public let topCreatures: [SimulationResultData]
    public let totalSeedsProcessed: Int

    public init(topCreatures: [SimulationResultData], totalSeedsProcessed: Int) {
        self.topCreatures = topCreatures
        self.totalSeedsProcessed = totalSeedsProcessed
    }
}

// MARK: - Saved Creature (Persistent storage format)

public struct SavedCreature: Codable, Sendable, Identifiable, Hashable {
    public let id: UUID
    public let name: String
    public let timestamp: Date
    public let ownerId: String
    public let genotype: KernelParams
    public let initialCondition: InitConfig
    public let initialConditionFamily: String?
    public let descriptorBundle: MorphospaceDescriptorBundle?
    public let metrics: SimulationMetrics
    public let sweep: [String: Double]?
    public let score: Float?
    public let scoreWeights: [String: Float]?
    public let configHash: String?

    public init(
        id: UUID = UUID(),
        name: String,
        ownerId: String,
        genotype: KernelParams,
        initialCondition: InitConfig,
        initialConditionFamily: String? = nil,
        descriptorBundle: MorphospaceDescriptorBundle? = nil,
        metrics: SimulationMetrics,
        sweep: [String: Double]? = nil,
        score: Float? = nil,
        scoreWeights: [String: Float]? = nil,
        configHash: String? = nil
    ) {
        self.id = id
        self.name = name
        self.timestamp = Date()
        self.ownerId = ownerId
        self.genotype = genotype
        self.initialCondition = initialCondition
        self.initialConditionFamily = initialConditionFamily ?? morphospaceInitialConditionFamily(initialCondition)
        self.descriptorBundle = descriptorBundle
        self.metrics = metrics
        self.sweep = sweep
        self.score = persistedFiniteScore(score)
        self.scoreWeights = scoreWeights
        self.configHash = configHash
    }

    public func hash(into hasher: inout Hasher) {
        hasher.combine(id)
    }

    public static func == (lhs: SavedCreature, rhs: SavedCreature) -> Bool {
        lhs.id == rhs.id
    }
}

public func savedCreatureFromResult(
    id: UUID = UUID(),
    name: String,
    ownerId: String,
    result: SimulationResultData,
    initialCondition: InitConfig,
    configHash: String? = nil,
    sweep: [String: Double]? = nil,
    score: Float? = nil,
    scoreWeights: [String: Float]? = nil
) -> SavedCreature {
    SavedCreature(
        id: id,
        name: name,
        ownerId: ownerId,
        genotype: result.params,
        initialCondition: initialCondition,
        initialConditionFamily: result.initialConditionFamily,
        descriptorBundle: result.descriptorBundle,
        metrics: result.metrics,
        sweep: sweep ?? (result.sweep.isEmpty ? nil : result.sweep),
        score: score ?? result.score,
        scoreWeights: scoreWeights ?? result.scoreWeights,
        configHash: configHash
    )
}

public func derivedCreature(
    from creature: SavedCreature,
    id: UUID = UUID(),
    name: String? = nil,
    ownerId: String? = nil,
    genotype: KernelParams,
    initialCondition: InitConfig? = nil,
    initialConditionFamily: String? = nil,
    descriptorBundle: MorphospaceDescriptorBundle? = nil,
    metrics: SimulationMetrics? = nil,
    sweep: [String: Double]? = nil,
    score: Float? = nil,
    scoreWeights: [String: Float]? = nil,
    configHash: String? = nil
) -> SavedCreature {
    SavedCreature(
        id: id,
        name: name ?? creature.name,
        ownerId: ownerId ?? creature.ownerId,
        genotype: genotype,
        initialCondition: initialCondition ?? creature.initialCondition,
        initialConditionFamily: initialConditionFamily ?? creature.initialConditionFamily,
        descriptorBundle: descriptorBundle ?? creature.descriptorBundle,
        metrics: metrics ?? creature.metrics,
        sweep: sweep ?? creature.sweep,
        score: score,
        scoreWeights: scoreWeights ?? creature.scoreWeights,
        configHash: configHash ?? creature.configHash
    )
}

public func archivedCreature(
    stableKey: String,
    name: String,
    ownerId: String,
    genotype: KernelParams,
    initialCondition: InitConfig,
    initialConditionFamily: String? = nil,
    descriptorBundle: MorphospaceDescriptorBundle? = nil,
    metrics: SimulationMetrics,
    sweep: [String: Double]? = nil,
    score: Float? = nil,
    scoreWeights: [String: Float]? = nil,
    configHash: String? = nil
) -> SavedCreature {
    SavedCreature(
        id: deterministicResearchUUID(stableKey),
        name: name,
        ownerId: ownerId,
        genotype: genotype,
        initialCondition: initialCondition,
        initialConditionFamily: initialConditionFamily,
        descriptorBundle: descriptorBundle,
        metrics: metrics,
        sweep: sweep,
        score: score,
        scoreWeights: scoreWeights,
        configHash: configHash
    )
}

public func archivedCreatureFromResult(
    stableKey: String,
    name: String,
    ownerId: String,
    result: SimulationResultData,
    initialCondition: InitConfig,
    configHash: String? = nil,
    sweep: [String: Double]? = nil,
    score: Float? = nil,
    scoreWeights: [String: Float]? = nil
) -> SavedCreature {
    archivedCreature(
        stableKey: stableKey,
        name: name,
        ownerId: ownerId,
        genotype: result.params,
        initialCondition: initialCondition,
        initialConditionFamily: result.initialConditionFamily,
        descriptorBundle: result.descriptorBundle,
        metrics: result.metrics,
        sweep: sweep ?? (result.sweep.isEmpty ? nil : result.sweep),
        score: score ?? result.score,
        scoreWeights: scoreWeights ?? result.scoreWeights,
        configHash: configHash
    )
}

// MARK: - Library Update (Broadcast from Controller to Workers)

public enum LibraryUpdate: Codable, Sendable {
    case fullSync([SavedCreature])
    case creatureAdded(SavedCreature)
}

// MARK: - Receptionist Keys

import DistributedCluster

public extension DistributedReception.Key {
    static var leniaController: DistributedReception.Key<SwarmController> {
        "lenia-controller"
    }
}
