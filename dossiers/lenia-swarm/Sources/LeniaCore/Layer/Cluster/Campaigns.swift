import Foundation
import Logging

// MARK: - Declarative Campaign Config

public enum LeniaCampaignPhaseType: String, Codable, Sendable {
    case qd
    case imgep
    case sweep
    case interventionBattery = "intervention-battery"
    case ecology
    case curiosity
}

public struct LeniaCampaignPhaseTarget: Codable, Sendable {
    public let minCoverage: Float?
    public let iterations: Int?
    public let creatures: Int?
    public let maxCycles: Int?

    enum CodingKeys: String, CodingKey {
        case minCoverage = "min_coverage"
        case iterations
        case creatures
        case maxCycles = "max_cycles"
    }
}

public struct LeniaCampaignPhaseConfig: Codable, Sendable {
    public let name: String
    public let type: LeniaCampaignPhaseType
    public let algorithm: String?
    public let configDir: String?
    public let config: String?
    public let baseConfig: String?
    public let searchConfig: String?
    public let manifest: String?
    public let seeds: [Int]?
    public let seedLibrary: String?
    public let seedTop: Int?
    public let seedRankBy: String?
    public let mode: String?
    public let target: LeniaCampaignPhaseTarget?

    enum CodingKeys: String, CodingKey {
        case name, type, algorithm, config, manifest, seeds, mode, target
        case configDir = "config_dir"
        case baseConfig = "base_config"
        case searchConfig = "search_config"
        case seedLibrary = "seed_library"
        case seedTop = "seed_top"
        case seedRankBy = "seed_rank_by"
    }

    public init(
        name: String, type: LeniaCampaignPhaseType, algorithm: String? = nil,
        configDir: String? = nil, config: String? = nil, baseConfig: String? = nil,
        searchConfig: String? = nil, manifest: String? = nil, seeds: [Int]? = nil,
        seedLibrary: String? = nil, seedTop: Int? = nil, seedRankBy: String? = nil,
        mode: String? = nil, target: LeniaCampaignPhaseTarget? = nil
    ) {
        self.name = name; self.type = type; self.algorithm = algorithm
        self.configDir = configDir; self.config = config; self.baseConfig = baseConfig
        self.searchConfig = searchConfig; self.manifest = manifest; self.seeds = seeds
        self.seedLibrary = seedLibrary; self.seedTop = seedTop; self.seedRankBy = seedRankBy
        self.mode = mode; self.target = target
    }
}

public struct LeniaCampaignCompendiumConfig: Codable, Sendable {
    public let mergePhases: Bool
    public let centralDB: String?

    enum CodingKeys: String, CodingKey {
        case mergePhases = "merge_phases"
        case centralDB = "central_db"
    }
}

public struct LeniaCampaignConfig: Codable, Sendable {
    public let name: String
    public let phases: [LeniaCampaignPhaseConfig]
    public let compendium: LeniaCampaignCompendiumConfig?
    public let phaseIsolation: Bool?

    enum CodingKeys: String, CodingKey {
        case name, phases, compendium
        case phaseIsolation = "phase_isolation"
    }
}

public struct LeniaCampaignPhaseResult: Sendable {
    public let phaseName: String
    public let phaseType: LeniaCampaignPhaseType
    public let creaturesFound: Int
    public let coverage: Float?
    public let elapsedSeconds: Double
    public let error: String?
    public let outputDirectory: URL

    public init(
        phaseName: String,
        phaseType: LeniaCampaignPhaseType,
        creaturesFound: Int,
        coverage: Float?,
        elapsedSeconds: Double,
        error: String?,
        outputDirectory: URL
    ) {
        self.phaseName = phaseName
        self.phaseType = phaseType
        self.creaturesFound = creaturesFound
        self.coverage = coverage
        self.elapsedSeconds = elapsedSeconds
        self.error = error
        self.outputDirectory = outputDirectory
    }
}

// MARK: - Legacy Preset System

public enum LeniaCampaignPreset: String, Codable, CaseIterable, Sendable {
    case discovery
    case foodDiscovery = "food-discovery"
    case seededEcology = "seeded-ecology"
    case interventionBattery = "intervention-battery"
}

public enum LeniaCampaignExecutor: String, Codable, Sendable {
    case search
    case ecology2025 = "ecology-2025"
}

public enum LeniaCampaignExecutionMode: String, Codable, Sendable {
    case local
    case distributed
}

public enum LeniaCampaignRunStatus: String, Codable, Sendable {
    case completed
    case failed
}

public struct LeniaCampaignSeedReference: Codable, Sendable {
    public let sourceID: String
    public let name: String
    public let runID: String?
    public let campaignID: String?

    public init(sourceID: String, name: String, runID: String? = nil, campaignID: String? = nil) {
        self.sourceID = sourceID
        self.name = name
        self.runID = runID
        self.campaignID = campaignID
    }

    public init?(patch: ResearchSeedPatch?) {
        guard let patch else { return nil }
        self.init(
            sourceID: patch.sourceID,
            name: patch.name,
            runID: patch.runID,
            campaignID: patch.campaignID
        )
    }
}

public struct LeniaCampaignEventSpec: Codable, Sendable {
    public let label: String
    public let family: String
    public let payload: [String: AnyCodable]

    public init(label: String, family: String, payload: [String: AnyCodable] = [:]) {
        self.label = label
        self.family = family
        self.payload = payload
    }
}

public struct LeniaCampaignSearchJobPayload: Codable, Sendable {
    public let simulationJob: SimulationJob
    public let configHash: String
    public let exportEligible: Bool
    public let eventSpecs: [LeniaCampaignEventSpec]

    public init(
        simulationJob: SimulationJob,
        configHash: String,
        exportEligible: Bool,
        eventSpecs: [LeniaCampaignEventSpec] = []
    ) {
        self.simulationJob = simulationJob
        self.configHash = configHash
        self.exportEligible = exportEligible
        self.eventSpecs = eventSpecs
    }
}

public struct LeniaCampaignEcologyJobPayload: Codable, Sendable {
    public let simulation: FlowLeniaEcology2025SimulationConfig
    public let variant: FlowLeniaEcology2025VariantConfig
    public let baseConfig: LeniaBaseConfig
    public let mutationProbability: Float
    public let curatedSeeds: [ResearchSeedPatch]
    public let configHash: String
    public let eventSpecs: [LeniaCampaignEventSpec]

    public init(
        simulation: FlowLeniaEcology2025SimulationConfig,
        variant: FlowLeniaEcology2025VariantConfig,
        baseConfig: LeniaBaseConfig,
        mutationProbability: Float,
        curatedSeeds: [ResearchSeedPatch],
        configHash: String,
        eventSpecs: [LeniaCampaignEventSpec] = []
    ) {
        self.simulation = simulation
        self.variant = variant
        self.baseConfig = baseConfig
        self.mutationProbability = mutationProbability
        self.curatedSeeds = curatedSeeds
        self.configHash = configHash
        self.eventSpecs = eventSpecs
    }
}

public struct LeniaCampaignJob: Codable, Sendable {
    public let campaignID: String
    public let runID: String
    public let preset: LeniaCampaignPreset
    public let executor: LeniaCampaignExecutor
    public let backendRequest: String
    public let executionMode: LeniaCampaignExecutionMode
    public let repeatIndex: Int
    public let environmentLabel: String?
    public let perturbationLabel: String?
    public let comparisonGroup: String?
    public let seedReference: LeniaCampaignSeedReference?
    public let search: LeniaCampaignSearchJobPayload?
    public let ecology: LeniaCampaignEcologyJobPayload?

    public init(
        campaignID: String,
        runID: String,
        preset: LeniaCampaignPreset,
        executor: LeniaCampaignExecutor,
        backendRequest: String,
        executionMode: LeniaCampaignExecutionMode,
        repeatIndex: Int,
        environmentLabel: String? = nil,
        perturbationLabel: String? = nil,
        comparisonGroup: String? = nil,
        seedReference: LeniaCampaignSeedReference? = nil,
        search: LeniaCampaignSearchJobPayload? = nil,
        ecology: LeniaCampaignEcologyJobPayload? = nil
    ) {
        self.campaignID = campaignID
        self.runID = runID
        self.preset = preset
        self.executor = executor
        self.backendRequest = backendRequest
        self.executionMode = executionMode
        self.repeatIndex = repeatIndex
        self.environmentLabel = environmentLabel
        self.perturbationLabel = perturbationLabel
        self.comparisonGroup = comparisonGroup
        self.seedReference = seedReference
        self.search = search
        self.ecology = ecology
    }
}

public struct LeniaCampaignRunRecord: Codable, Sendable {
    public let campaignID: String
    public let runID: String
    public let preset: LeniaCampaignPreset
    public let executor: LeniaCampaignExecutor
    public let status: LeniaCampaignRunStatus
    public let requestedBackend: String
    public let actualBackend: String?
    public let executionMode: LeniaCampaignExecutionMode
    public let repeatIndex: Int
    public let environmentLabel: String?
    public let perturbationLabel: String?
    public let comparisonGroup: String?
    public let seedReference: LeniaCampaignSeedReference?
    public let workerID: String?
    public let errorMessage: String?

    public init(
        campaignID: String,
        runID: String,
        preset: LeniaCampaignPreset,
        executor: LeniaCampaignExecutor,
        status: LeniaCampaignRunStatus,
        requestedBackend: String,
        actualBackend: String?,
        executionMode: LeniaCampaignExecutionMode,
        repeatIndex: Int,
        environmentLabel: String?,
        perturbationLabel: String?,
        comparisonGroup: String?,
        seedReference: LeniaCampaignSeedReference?,
        workerID: String? = nil,
        errorMessage: String? = nil
    ) {
        self.campaignID = campaignID
        self.runID = runID
        self.preset = preset
        self.executor = executor
        self.status = status
        self.requestedBackend = requestedBackend
        self.actualBackend = actualBackend
        self.executionMode = executionMode
        self.repeatIndex = repeatIndex
        self.environmentLabel = environmentLabel
        self.perturbationLabel = perturbationLabel
        self.comparisonGroup = comparisonGroup
        self.seedReference = seedReference
        self.workerID = workerID
        self.errorMessage = errorMessage
    }
}

public struct LeniaCampaignMetricRecord: Codable, Sendable {
    public let campaignID: String
    public let runID: String
    public let preset: LeniaCampaignPreset
    public let executor: LeniaCampaignExecutor
    public let actualBackend: String
    public let executionMode: LeniaCampaignExecutionMode
    public let environmentLabel: String?
    public let perturbationLabel: String?
    public let comparisonGroup: String?
    public let seedSourceID: String?
    public let seedName: String?
    public let seedRunID: String?
    public let seedCampaignID: String?
    public let seed: Int?
    public let score: Float?
    public let finalMass: Float?
    public let finalCenterX: Float?
    public let finalCenterY: Float?
    public let survivalSteps: Int?
    public let displacement: Float?
    public let pathLength: Float?
    public let occupancyMean: Float?
    public let varianceMean: Float?
    public let energyMean: Float?
    public let speedMean: Float?
    public let massMean: Float?
    public let massStd: Float?
    public let gyration: Float?
    public let centerVelocity: Float?
    public let activityDiversityMean: Float?
    public let activitySpeciesMean: Float?
    public let activityEacMean: Float?
    public let activityEanMean: Float?
    public var massRetentionRatio: Float?
    public var displacementRatio: Float?
    public var occupancyDelta: Float?
    public var varianceDelta: Float?
    public var recoveryLagSteps: Int?
    public var postPerturbationDivergence: Float?
    public var returnToBaselineScore: Float?
    public var redirectedBehaviorScore: Float?
    public var pursuitScore: Float?

    public init(
        campaignID: String,
        runID: String,
        preset: LeniaCampaignPreset,
        executor: LeniaCampaignExecutor,
        actualBackend: String,
        executionMode: LeniaCampaignExecutionMode,
        environmentLabel: String?,
        perturbationLabel: String?,
        comparisonGroup: String?,
        seedSourceID: String?,
        seedName: String?,
        seedRunID: String?,
        seedCampaignID: String?,
        seed: Int?,
        score: Float?,
        finalMass: Float?,
        finalCenterX: Float?,
        finalCenterY: Float?,
        survivalSteps: Int?,
        displacement: Float?,
        pathLength: Float?,
        occupancyMean: Float?,
        varianceMean: Float?,
        energyMean: Float?,
        speedMean: Float?,
        massMean: Float?,
        massStd: Float?,
        gyration: Float?,
        centerVelocity: Float?,
        activityDiversityMean: Float?,
        activitySpeciesMean: Float?,
        activityEacMean: Float?,
        activityEanMean: Float?
    ) {
        self.campaignID = campaignID
        self.runID = runID
        self.preset = preset
        self.executor = executor
        self.actualBackend = actualBackend
        self.executionMode = executionMode
        self.environmentLabel = environmentLabel
        self.perturbationLabel = perturbationLabel
        self.comparisonGroup = comparisonGroup
        self.seedSourceID = seedSourceID
        self.seedName = seedName
        self.seedRunID = seedRunID
        self.seedCampaignID = seedCampaignID
        self.seed = seed
        self.score = score
        self.finalMass = finalMass
        self.finalCenterX = finalCenterX
        self.finalCenterY = finalCenterY
        self.survivalSteps = survivalSteps
        self.displacement = displacement
        self.pathLength = pathLength
        self.occupancyMean = occupancyMean
        self.varianceMean = varianceMean
        self.energyMean = energyMean
        self.speedMean = speedMean
        self.massMean = massMean
        self.massStd = massStd
        self.gyration = gyration
        self.centerVelocity = centerVelocity
        self.activityDiversityMean = activityDiversityMean
        self.activitySpeciesMean = activitySpeciesMean
        self.activityEacMean = activityEacMean
        self.activityEanMean = activityEanMean
    }
}

public struct LeniaCampaignEventRecord: Codable, Sendable {
    public let campaignID: String
    public let runID: String
    public let preset: LeniaCampaignPreset
    public let executionMode: LeniaCampaignExecutionMode
    public let label: String
    public let family: String
    public let payload: [String: AnyCodable]
}

public struct LeniaCampaignEcologyArtifact: Codable, Sendable {
    public let runID: String
    public let summary: FlowLeniaEcology2025RunSummary
    public let frames: [FlowLeniaEcology2025FrameMetrics]
    public let trajectoryFrames: [LeniaTrajectoryFrame]
    public let activitySummary: ActivitySummary?
    public let replayBaseConfig: LeniaBaseConfig
    public let replayPayload: FlowLeniaEcology2025ReplayPayload
}

public struct LeniaCampaignExportCandidate: Codable, Sendable {
    public let runID: String
    public let creature: SavedCreature
    public let result: SimulationResultData
    public let baseConfig: LeniaBaseConfig
    public let searchConfig: ParsedSearchConfig
    public let configHash: String
}

public struct LeniaCampaignJobExecution: Codable, Sendable {
    public let runs: [LeniaCampaignRunRecord]
    public let metrics: [LeniaCampaignMetricRecord]
    public let events: [LeniaCampaignEventRecord]
    public let results: [SimulationResultData]
    public let ecologyArtifacts: [LeniaCampaignEcologyArtifact]
    public let exportCandidates: [LeniaCampaignExportCandidate]

    public init(
        runs: [LeniaCampaignRunRecord],
        metrics: [LeniaCampaignMetricRecord],
        events: [LeniaCampaignEventRecord],
        results: [SimulationResultData],
        ecologyArtifacts: [LeniaCampaignEcologyArtifact],
        exportCandidates: [LeniaCampaignExportCandidate]
    ) {
        self.runs = runs
        self.metrics = metrics
        self.events = events
        self.results = results
        self.ecologyArtifacts = ecologyArtifacts
        self.exportCandidates = exportCandidates
    }
}

private extension LeniaCampaignJob {
    func with(search payload: LeniaCampaignSearchJobPayload) -> LeniaCampaignJob {
        LeniaCampaignJob(
            campaignID: campaignID,
            runID: runID,
            preset: preset,
            executor: executor,
            backendRequest: backendRequest,
            executionMode: executionMode,
            repeatIndex: repeatIndex,
            environmentLabel: environmentLabel,
            perturbationLabel: perturbationLabel,
            comparisonGroup: comparisonGroup,
            seedReference: seedReference,
            search: payload,
            ecology: nil
        )
    }

    func with(ecology payload: LeniaCampaignEcologyJobPayload) -> LeniaCampaignJob {
        LeniaCampaignJob(
            campaignID: campaignID,
            runID: runID,
            preset: preset,
            executor: executor,
            backendRequest: backendRequest,
            executionMode: executionMode,
            repeatIndex: repeatIndex,
            environmentLabel: environmentLabel,
            perturbationLabel: perturbationLabel,
            comparisonGroup: comparisonGroup,
            seedReference: seedReference,
            search: nil,
            ecology: payload
        )
    }

    func runRecord(
        runID overrideRunID: String? = nil,
        status: LeniaCampaignRunStatus,
        actualBackend: String,
        workerID: String?
    ) -> LeniaCampaignRunRecord {
        LeniaCampaignRunRecord(
            campaignID: campaignID,
            runID: overrideRunID ?? runID,
            preset: preset,
            executor: executor,
            status: status,
            requestedBackend: backendRequest,
            actualBackend: actualBackend,
            executionMode: executionMode,
            repeatIndex: repeatIndex,
            environmentLabel: environmentLabel,
            perturbationLabel: perturbationLabel,
            comparisonGroup: comparisonGroup,
            seedReference: seedReference,
            workerID: workerID
        )
    }

    func eventRecords(
        runID overrideRunID: String? = nil,
        specs: [LeniaCampaignEventSpec]
    ) -> [LeniaCampaignEventRecord] {
        specs.map { spec in
            LeniaCampaignEventRecord(
                campaignID: campaignID,
                runID: overrideRunID ?? runID,
                preset: preset,
                executionMode: executionMode,
                label: spec.label,
                family: spec.family,
                payload: spec.payload
            )
        }
    }
}

private func copyCampaignBaseConfig(_ baseConfig: LeniaBaseConfig, backend: String) -> LeniaBaseConfig {
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

private func resolvedEcologyBackend(
    for capabilities: WorkerBackendCapabilities,
    requestValue: String,
    config: LeniaBaseConfig
) -> FlowLeniaComputeBackend? {
    guard let request = try? SimulationJobBackendRequest(configValue: requestValue) else {
        return nil
    }
    switch request {
    case .explicit(let backend):
        return capabilities.canonicalFlowLeniaBackends.contains(backend) ? backend : nil
    case .auto:
        if capabilities.canonicalFlowLeniaBackends.contains(.metalFull),
           isSearchBackendCompatible(backend: .metalFull, config: config) {
            return .metalFull
        }
        return nil
    }
}

public func materializeCampaignJob(
    _ job: LeniaCampaignJob,
    for capabilities: WorkerBackendCapabilities
) -> LeniaCampaignJob? {
    switch job.executor {
    case .search:
        guard let payload = job.search,
              let materializedJob = materializeSimulationJob(payload.simulationJob, for: capabilities) else {
            return nil
        }
        let materializedPayload = LeniaCampaignSearchJobPayload(
            simulationJob: materializedJob,
            configHash: payload.configHash,
            exportEligible: payload.exportEligible,
            eventSpecs: payload.eventSpecs
        )
        return job.with(search: materializedPayload)
    case .ecology2025:
        guard let payload = job.ecology,
              let backend = resolvedEcologyBackend(for: capabilities, requestValue: job.backendRequest, config: payload.baseConfig) else {
            return nil
        }
        if payload.baseConfig.backend == backend.rawValue {
            return job
        }
        let materializedPayload = LeniaCampaignEcologyJobPayload(
            simulation: payload.simulation,
            variant: payload.variant,
            baseConfig: copyCampaignBaseConfig(payload.baseConfig, backend: backend.rawValue),
            mutationProbability: payload.mutationProbability,
            curatedSeeds: payload.curatedSeeds,
            configHash: payload.configHash,
            eventSpecs: payload.eventSpecs
        )
        return job.with(ecology: materializedPayload)
    }
}

public func workerSupportsCampaignJob(
    _ status: WorkerStatus,
    job: LeniaCampaignJob
) -> Bool {
    materializeCampaignJob(job, for: status.capabilities) != nil
}

public func executeLeniaCampaignJob(
    _ job: LeniaCampaignJob,
    logger: Logger,
    localCapabilities: WorkerBackendCapabilities? = nil,
    workerID: String? = nil
) throws -> LeniaCampaignJobExecution {
    try LeniaMetalLibrarySupport.ensureAvailable()
    let materializedJob: LeniaCampaignJob
    if let localCapabilities {
        guard let resolved = materializeCampaignJob(job, for: localCapabilities) else {
            throw WorkerError.invalidConfig("No compatible backend available for campaign job \(job.runID).")
        }
        materializedJob = resolved
    } else {
        materializedJob = job
    }
    switch materializedJob.executor {
    case .search:
        guard let payload = materializedJob.search else {
            throw WorkerError.invalidConfig("Search campaign job \(materializedJob.runID) is missing its payload.")
        }
        return try executeLeniaSearchCampaignJob(materializedJob, payload: payload, logger: logger, workerID: workerID)
    case .ecology2025:
        guard let payload = materializedJob.ecology else {
            throw WorkerError.invalidConfig("Ecology campaign job \(materializedJob.runID) is missing its payload.")
        }
        return try executeLeniaEcologyCampaignJob(materializedJob, payload: payload, logger: logger, workerID: workerID)
    }
}

private func executeLeniaSearchCampaignJob(
    _ job: LeniaCampaignJob,
    payload: LeniaCampaignSearchJobPayload,
    logger: Logger,
    workerID: String?
) throws -> LeniaCampaignJobExecution {
    let simulationJob = payload.simulationJob
    let searchConfig = simulationJob.searchConfig
    let batchSize = searchConfig.batchSize
    var initSeedOffset = searchConfig.initSeedOffset ?? 0
    guard simulationJob.count > 0 else {
        throw WorkerError.invalidConfig("Campaign search job \(job.runID) count must be > 0.")
    }
    guard batchSize > 0 else {
        throw WorkerError.invalidConfig("Campaign search job \(job.runID) batch_size must be > 0.")
    }

    var seeds: [Int] = []
    for index in 0..<simulationJob.count {
        seeds.append(simulationJob.seedStart + index * searchConfig.seedStride)
    }

    var overrides = searchConfig.overridesAsDict()
    if let sweepOverrides = simulationJob.sweepOverrides {
        for (key, value) in sweepOverrides {
            overrides[key] = value
        }
    }
    if overrides["params.seed"] == nil {
        overrides["params.seed"] = seeds[0]
    }
    if let initSeedOverride = overrides["init.seed"] {
        let asInt: Int? = {
            if let int = initSeedOverride as? Int { return int }
            if let double = initSeedOverride as? Double { return Int(double) }
            return nil
        }()
        guard let extra = asInt else {
            throw WorkerError.invalidConfig("Campaign search job \(job.runID) init.seed override must be an integer.")
        }
        initSeedOffset += extra
        overrides.removeValue(forKey: "init.seed")
    }
    overrides["run.steps"] = searchConfig.steps

    let baseConfigData = try JSONEncoder().encode(simulationJob.baseConfig)
    let runtimeConfig = try loadRuntimeConfig(from: baseConfigData, overrides: overrides)
    let engine = SearchEngine(runtimeConfig: runtimeConfig)
    let resolvedSearchConfig = searchConfig.toSearchConfig()
    let batchResults = engine.runBatch(
        seeds: seeds,
        initSeedOffset: initSeedOffset,
        searchConfig: resolvedSearchConfig
    )

    let eventSpecs = payload.eventSpecs
    var runs: [LeniaCampaignRunRecord] = []
    var metrics: [LeniaCampaignMetricRecord] = []
    var events: [LeniaCampaignEventRecord] = []
    var results: [SimulationResultData] = []
    var exportCandidates: [LeniaCampaignExportCandidate] = []
    let initialCondition = InitConfig(
        seed: simulationJob.baseConfig.`init`.seed,
        patches: simulationJob.baseConfig.`init`.patches,
        a_uniform: simulationJob.baseConfig.`init`.a_uniform,
        p_uniform: simulationJob.baseConfig.`init`.p_uniform,
        state_patch: simulationJob.baseConfig.`init`.state_patch,
        p_state_patch: simulationJob.baseConfig.`init`.p_state_patch
    )

    for result in batchResults {
        let resultData = materializeSearchResultData(
            result,
            backend: runtimeConfig.backend.rawValue,
            implementation: runtimeConfig.implementation,
            searchConfig: resolvedSearchConfig,
            sweep: simulationJob.sweepOverrides ?? [:],
            workerId: workerID
        )
        let filtersPassed = resultData.filtersPassed
        let score = resultData.score
        let runID = "\(job.runID)-seed-\(result.seed)"
        runs.append(job.runRecord(
            runID: runID,
            status: .completed,
            actualBackend: runtimeConfig.backend.rawValue,
            workerID: workerID
        ))
        metrics.append(campaignMetricRecord(
            job: job,
            runID: runID,
            actualBackend: runtimeConfig.backend.rawValue,
            result: resultData
        ))
        events.append(contentsOf: job.eventRecords(runID: runID, specs: eventSpecs))
        results.append(resultData)
        if payload.exportEligible, filtersPassed, score != nil {
            let creature = savedCreatureFromResult(
                name: campaignCreatureName(prefix: job.preset.rawValue, seed: result.seed),
                ownerId: workerID ?? "campaign",
                result: resultData,
                initialCondition: initialCondition,
                configHash: payload.configHash
            )
            exportCandidates.append(
                LeniaCampaignExportCandidate(
                    runID: runID,
                    creature: creature,
                    result: resultData,
                    baseConfig: simulationJob.baseConfig,
                    searchConfig: simulationJob.searchConfig,
                    configHash: payload.configHash
                )
            )
        }
    }

    logger.info("Campaign search job \(job.runID) completed with \(results.count) results")
    return LeniaCampaignJobExecution(
        runs: runs,
        metrics: metrics,
        events: events,
        results: results,
        ecologyArtifacts: [],
        exportCandidates: exportCandidates
    )
}

private func executeLeniaEcologyCampaignJob(
    _ job: LeniaCampaignJob,
    payload: LeniaCampaignEcologyJobPayload,
    logger: Logger,
    workerID: String?
) throws -> LeniaCampaignJobExecution {
    let baseConfigData = try JSONEncoder().encode(payload.baseConfig)
    let trial = try runFlowLeniaEcology2025Trial(
        simulation: payload.simulation,
        variant: payload.variant,
        baseConfigData: baseConfigData,
        mutationProbability: payload.mutationProbability,
        repeatIndex: job.repeatIndex,
        curatedSeeds: payload.curatedSeeds,
        logger: logger
    )

    let actualBackend = payload.baseConfig.backend
    let runRecord = job.runRecord(
        status: .completed,
        actualBackend: actualBackend,
        workerID: workerID
    )
    let metricRecord = campaignMetricRecord(
        job: job,
        runID: job.runID,
        actualBackend: actualBackend,
        values: campaignMetricValues(runSummary: trial.runSummary)
    )
    let events = job.eventRecords(specs: payload.eventSpecs)
    return LeniaCampaignJobExecution(
        runs: [runRecord],
        metrics: [metricRecord],
        events: events,
        results: [],
        ecologyArtifacts: [
            LeniaCampaignEcologyArtifact(
                runID: job.runID,
                summary: trial.runSummary,
                frames: trial.frameMetrics,
                trajectoryFrames: trial.trajectoryFrames,
                activitySummary: trial.activitySummary,
                replayBaseConfig: trial.replayBaseConfig,
                replayPayload: trial.replayPayload
            )
        ],
        exportCandidates: []
    )
}

private func campaignMetricRecord(
    job: LeniaCampaignJob,
    runID: String,
    actualBackend: String,
    result: SimulationResultData
) -> LeniaCampaignMetricRecord {
    campaignMetricRecord(
        job: job,
        runID: runID,
        actualBackend: actualBackend,
        values: campaignMetricValues(result: result)
    )
}

private func campaignMetricRecord(
    job: LeniaCampaignJob,
    runID: String,
    actualBackend: String,
    values: CampaignMetricValues
) -> LeniaCampaignMetricRecord {
    LeniaCampaignMetricRecord(
        campaignID: job.campaignID,
        runID: runID,
        preset: job.preset,
        executor: job.executor,
        actualBackend: actualBackend,
        executionMode: job.executionMode,
        environmentLabel: job.environmentLabel,
        perturbationLabel: job.perturbationLabel,
        comparisonGroup: job.comparisonGroup,
        seedSourceID: job.seedReference?.sourceID,
        seedName: job.seedReference?.name,
        seedRunID: job.seedReference?.runID,
        seedCampaignID: job.seedReference?.campaignID,
        seed: values.seed,
        score: values.score,
        finalMass: values.finalMass,
        finalCenterX: values.finalCenterX,
        finalCenterY: values.finalCenterY,
        survivalSteps: values.survivalSteps,
        displacement: values.displacement,
        pathLength: values.pathLength,
        occupancyMean: values.occupancyMean,
        varianceMean: values.varianceMean,
        energyMean: values.energyMean,
        speedMean: values.speedMean,
        massMean: values.massMean,
        massStd: values.massStd,
        gyration: values.gyration,
        centerVelocity: values.centerVelocity,
        activityDiversityMean: values.activityDiversityMean,
        activitySpeciesMean: values.activitySpeciesMean,
        activityEacMean: values.activityEacMean,
        activityEanMean: values.activityEanMean
    )
}

private struct CampaignMetricValues {
    let seed: Int?
    let score: Float?
    let finalMass: Float?
    let finalCenterX: Float?
    let finalCenterY: Float?
    let survivalSteps: Int?
    let displacement: Float?
    let pathLength: Float?
    let occupancyMean: Float?
    let varianceMean: Float?
    let energyMean: Float?
    let speedMean: Float?
    let massMean: Float?
    let massStd: Float?
    let gyration: Float?
    let centerVelocity: Float?
    let activityDiversityMean: Float?
    let activitySpeciesMean: Float?
    let activityEacMean: Float?
    let activityEanMean: Float?
}

private func campaignMetricValues(result: SimulationResultData) -> CampaignMetricValues {
    CampaignMetricValues(
        seed: result.seed,
        score: result.score,
        finalMass: result.metrics.massMean,
        finalCenterX: nil,
        finalCenterY: nil,
        survivalSteps: result.metrics.survivalSteps,
        displacement: result.metrics.displacement,
        pathLength: result.metrics.pathLength,
        occupancyMean: result.metrics.occupancyMean,
        varianceMean: result.metrics.varianceMean,
        energyMean: result.metrics.energyMean,
        speedMean: result.metrics.speedMean,
        massMean: result.metrics.massMean,
        massStd: result.metrics.massStd,
        gyration: result.metrics.gyration,
        centerVelocity: result.metrics.centerVelocity,
        activityDiversityMean: result.metrics.activityDiversityMean,
        activitySpeciesMean: result.metrics.activitySpeciesMean,
        activityEacMean: result.metrics.activityEacMean,
        activityEanMean: result.metrics.activityEanMean
    )
}

private func campaignMetricValues(runSummary: FlowLeniaEcology2025RunSummary) -> CampaignMetricValues {
    CampaignMetricValues(
        seed: nil,
        score: runSummary.finalNonNeutralActivity,
        finalMass: runSummary.finalMass,
        finalCenterX: nil,
        finalCenterY: nil,
        survivalSteps: nil,
        displacement: nil,
        pathLength: nil,
        occupancyMean: nil,
        varianceMean: nil,
        energyMean: nil,
        speedMean: nil,
        massMean: runSummary.finalMass,
        massStd: nil,
        gyration: nil,
        centerVelocity: nil,
        activityDiversityMean: runSummary.finalDiversity,
        activitySpeciesMean: Float(runSummary.finalSpeciesCount),
        activityEacMean: runSummary.finalCountActivity,
        activityEanMean: runSummary.finalNonNeutralActivity
    )
}

private func campaignCreatureName(prefix: String, seed: Int) -> String {
    "\(prefix)-\(seed)"
}
