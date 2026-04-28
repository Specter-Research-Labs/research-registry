import Foundation

// Persisted artifacts must never carry non-finite scores because JSONEncoder rejects them.
public func persistedFiniteScore(_ score: Float?) -> Float? {
    guard let score else { return nil }
    return score.isFinite ? score : nil
}

public func normalizedPersistedDescriptorBundle(
    _ descriptorBundle: MorphospaceDescriptorBundle?,
    metrics: SimulationMetrics
) -> MorphospaceDescriptorBundle? {
    guard let descriptorBundle, let trajectory = descriptorBundle.trajectory else {
        return descriptorBundle
    }

    let pathLength = finiteOrFallback(trajectory.pathLength, fallback: metrics.pathLength)
    let displacement = finiteOrFallback(trajectory.displacement, fallback: metrics.displacement)
    let safeTortuosity = finiteOptional(
        trajectory.pathTortuosity,
        fallback: fallbackTortuosity(pathLength: pathLength, displacement: displacement)
    )
    let safeEfficiency = finiteOptional(
        trajectory.movementEfficiency,
        fallback: fallbackMovementEfficiency(pathLength: pathLength, displacement: displacement)
    )
    let safeHeadingVariance = finiteOptional(trajectory.headingCircularVariance, fallback: 0.0)
    let safeAccumulatedTurn = finiteOptional(trajectory.accumulatedTurnAbs, fallback: 0.0)

    if trajectory.pathLength == pathLength,
       trajectory.displacement == displacement,
       trajectory.pathTortuosity == safeTortuosity,
       trajectory.movementEfficiency == safeEfficiency,
       trajectory.headingCircularVariance == safeHeadingVariance,
       trajectory.accumulatedTurnAbs == safeAccumulatedTurn {
        return descriptorBundle
    }

    return MorphospaceDescriptorBundle(
        descriptorVersion: descriptorBundle.descriptorVersion,
        symmetryPolicy: descriptorBundle.symmetryPolicy,
        genotype: descriptorBundle.genotype,
        terminal: descriptorBundle.terminal,
        trajectory: MorphospaceTrajectoryDescriptor(
            version: trajectory.version,
            recordInterval: trajectory.recordInterval,
            warmupSteps: trajectory.warmupSteps,
            sampleCount: trajectory.sampleCount,
            pathLength: pathLength,
            displacement: displacement,
            pathTortuosity: safeTortuosity,
            movementEfficiency: safeEfficiency,
            speedMean: finiteOrFallback(trajectory.speedMean, fallback: metrics.speedMean),
            centerVelocity: finiteOrFallback(trajectory.centerVelocity, fallback: metrics.centerVelocity),
            velocityX: finiteOrFallback(trajectory.velocityX, fallback: metrics.velocityX),
            velocityY: finiteOrFallback(trajectory.velocityY, fallback: metrics.velocityY),
            headingRad: finiteOrFallback(trajectory.headingRad, fallback: metrics.headingRad),
            headingCircularVariance: safeHeadingVariance,
            accumulatedTurnAbs: safeAccumulatedTurn,
            survivalSteps: trajectory.survivalSteps,
            activityEacMean: finiteOptionalOrNil(trajectory.activityEacMean, fallback: metrics.activityEacMean),
            activityEanMean: finiteOptionalOrNil(trajectory.activityEanMean, fallback: metrics.activityEanMean),
            activityDiversityMean: finiteOptionalOrNil(trajectory.activityDiversityMean, fallback: metrics.activityDiversityMean),
            activitySpeciesMean: finiteOptionalOrNil(trajectory.activitySpeciesMean, fallback: metrics.activitySpeciesMean),
            activitySpeciesMax: trajectory.activitySpeciesMax,
            activitySpeciesStd: trajectory.activitySpeciesStd,
            activityDiversityStd: trajectory.activityDiversityStd,
            activityEacMax: trajectory.activityEacMax,
            activityEanMax: trajectory.activityEanMax,
            componentSeriesMean: trajectory.componentSeriesMean,
            componentSeriesStd: trajectory.componentSeriesStd,
            componentSeriesMax: trajectory.componentSeriesMax
        )
    )
}

public struct SimulationResultData: Codable, Sendable {
    public let seed: Int
    public let initSeed: Int
    public let mixSeed: Int?
    public let backend: String
    public let implementation: ImplementationSettings
    public let initialConditionFamily: String?
    public let descriptorBundle: MorphospaceDescriptorBundle?
    public let score: Float?
    public let scoreWeights: [String: Float]?
    public let filtersPassed: Bool
    public let filters: [String: Float]
    public let metrics: SimulationMetrics
    public let activity: [ActivitySnapshot]?
    public let params: KernelParams
    public let sweep: [String: Double]
    public var workerId: String?

    enum CodingKeys: String, CodingKey {
        case seed
        case initSeed = "init_seed"
        case mixSeed = "mix_seed"
        case backend
        case implementation
        case initialConditionFamily = "initial_condition_family"
        case descriptorBundle = "descriptor_bundle"
        case score
        case scoreWeights = "score_weights"
        case filtersPassed = "filters_passed"
        case filters
        case metrics
        case activity
        case params
        case sweep
        case workerId = "worker_id"
    }

    public init(
        seed: Int,
        initSeed: Int,
        mixSeed: Int?,
        backend: String,
        implementation: ImplementationSettings,
        initialConditionFamily: String? = nil,
        descriptorBundle: MorphospaceDescriptorBundle? = nil,
        score: Float?,
        scoreWeights: [String: Float]? = nil,
        filtersPassed: Bool,
        filters: [String: Float],
        metrics: SimulationMetrics,
        activity: [ActivitySnapshot]?,
        params: KernelParams,
        sweep: [String: Double],
        workerId: String? = nil
    ) {
        self.seed = seed
        self.initSeed = initSeed
        self.mixSeed = mixSeed
        self.backend = backend
        self.implementation = implementation
        self.initialConditionFamily = initialConditionFamily
        self.descriptorBundle = descriptorBundle
        self.score = persistedFiniteScore(score)
        self.scoreWeights = scoreWeights
        self.filtersPassed = filtersPassed
        self.filters = filters
        self.metrics = metrics
        self.activity = activity
        self.params = params
        self.sweep = sweep
        self.workerId = workerId
    }
}

public func decodeSimulationResultLines(_ json: String, workerId: String? = nil) -> [SimulationResultData] {
    json.split(separator: "\n").compactMap { line in
        guard let data = line.data(using: .utf8),
              var result = try? JSONDecoder().decode(SimulationResultData.self, from: data)
        else {
            return nil
        }
        if let workerId {
            result.workerId = workerId
        }
        return result
    }
}

public func topSimulationResults(from results: [SimulationResultData], limit: Int) -> [SimulationResultData] {
    guard limit > 0 else { return [] }
    return Array(
        results
            .filter { $0.filtersPassed && $0.score != nil }
            .sorted { ($0.score ?? 0) > ($1.score ?? 0) }
            .prefix(limit)
    )
}

public func materializeSearchResultData(
    _ result: BatchSimulationResult,
    backend: String,
    implementation: ImplementationSettings,
    searchConfig: SearchConfig,
    sweep: [String: Double] = [:],
    mixSeed: Int? = nil,
    workerId: String? = nil
) -> SimulationResultData {
    let passed = passesFilters(result.metrics, filters: searchConfig.filters)
    let score: Float? = passed ? scoreMetrics(result.metrics, weights: searchConfig.scoreWeights) : nil
    return SimulationResultData(
        seed: result.seed,
        initSeed: result.initSeed,
        mixSeed: mixSeed,
        backend: backend,
        implementation: implementation,
        initialConditionFamily: result.initialConditionFamily,
        descriptorBundle: normalizedPersistedDescriptorBundle(result.descriptorBundle, metrics: result.metrics),
        score: score,
        scoreWeights: searchConfig.scoreWeights,
        filtersPassed: passed,
        filters: searchConfig.filters,
        metrics: result.metrics,
        activity: result.activity,
        params: result.params.toKernelParams(),
        sweep: sweep,
        workerId: workerId
    )
}

public func materializeReplayResultData(
    seed: Int,
    initSeed: Int,
    backend: String,
    implementation: ImplementationSettings,
    initialConditionFamily: String?,
    descriptorBundle: MorphospaceDescriptorBundle?,
    score: Float?,
    scoreWeights: [String: Float]?,
    filtersPassed: Bool,
    filters: [String: Float],
    metrics: SimulationMetrics,
    activity: [ActivitySnapshot]? = nil,
    params: KernelParams,
    sweep: [String: Double] = [:],
    mixSeed: Int? = nil,
    workerId: String? = nil
) -> SimulationResultData {
    SimulationResultData(
        seed: seed,
        initSeed: initSeed,
        mixSeed: mixSeed,
        backend: backend,
        implementation: implementation,
        initialConditionFamily: initialConditionFamily,
        descriptorBundle: descriptorBundle,
        score: score,
        scoreWeights: scoreWeights,
        filtersPassed: filtersPassed,
        filters: filters,
        metrics: metrics,
        activity: activity,
        params: params,
        sweep: sweep,
        workerId: workerId
    )
}

public func materializeReplayResultData(
    _ result: BatchSimulationResult,
    backend: String,
    implementation: ImplementationSettings,
    scoreWeights: [String: Float],
    filters: [String: Float],
    sweep: [String: Double] = [:],
    mixSeed: Int? = nil,
    workerId: String? = nil
) -> SimulationResultData {
    materializeReplayResultData(
        seed: result.seed,
        initSeed: result.initSeed,
        backend: backend,
        implementation: implementation,
        initialConditionFamily: result.initialConditionFamily,
        descriptorBundle: normalizedPersistedDescriptorBundle(result.descriptorBundle, metrics: result.metrics),
        score: nil,
        scoreWeights: scoreWeights,
        filtersPassed: true,
        filters: filters,
        metrics: result.metrics,
        activity: result.activity,
        params: result.params.toKernelParams(),
        sweep: sweep,
        mixSeed: mixSeed,
        workerId: workerId
    )
}

public func normalizedPersistedResultData(_ result: SimulationResultData) -> SimulationResultData {
    SimulationResultData(
        seed: result.seed,
        initSeed: result.initSeed,
        mixSeed: result.mixSeed,
        backend: result.backend,
        implementation: result.implementation,
        initialConditionFamily: result.initialConditionFamily,
        descriptorBundle: normalizedPersistedDescriptorBundle(result.descriptorBundle, metrics: result.metrics),
        score: result.score,
        scoreWeights: result.scoreWeights,
        filtersPassed: result.filtersPassed,
        filters: result.filters,
        metrics: result.metrics,
        activity: result.activity,
        params: result.params,
        sweep: result.sweep,
        workerId: result.workerId
    )
}

public func normalizedPersistedCreature(_ creature: SavedCreature) -> SavedCreature {
    SavedCreature(
        id: creature.id,
        name: creature.name,
        ownerId: creature.ownerId,
        genotype: creature.genotype,
        initialCondition: creature.initialCondition,
        initialConditionFamily: creature.initialConditionFamily,
        descriptorBundle: normalizedPersistedDescriptorBundle(creature.descriptorBundle, metrics: creature.metrics),
        metrics: creature.metrics,
        sweep: creature.sweep,
        score: creature.score,
        scoreWeights: creature.scoreWeights,
        configHash: creature.configHash
    )
}

public func mergeTopSimulationResults(
    _ results: [SimulationResultData],
    into topResults: inout [SimulationResultData],
    limit: Int,
    headroomMultiplier: Int = 1
) {
    guard limit > 0 else {
        topResults.removeAll(keepingCapacity: true)
        return
    }
    topResults.append(contentsOf: results.filter { $0.filtersPassed && $0.score != nil })
    topResults.sort { ($0.score ?? 0) > ($1.score ?? 0) }
    let cappedLimit = max(limit, limit * max(1, headroomMultiplier))
    if topResults.count > cappedLimit {
        topResults = Array(topResults.prefix(cappedLimit))
    }
}

public func appendResearchJSONLines<T: Encodable>(
    _ values: [T],
    to handle: FileHandle,
    encoder: JSONEncoder? = nil
) throws {
    guard !values.isEmpty else { return }
    let resolvedEncoder = encoder ?? researchJSONEncoder()
    for value in values {
        handle.write(try researchJSONLine(value, encoder: resolvedEncoder))
    }
}

@discardableResult
public func writeTopSimulationResults(
    from results: [SimulationResultData],
    limit: Int,
    to url: URL
) throws -> [SimulationResultData] {
    let top = topSimulationResults(from: results, limit: limit)
    if !top.isEmpty {
        try writeTopSimulationResultsSnapshot(top, to: url)
    }
    return top
}

public func writeTopSimulationResultsSnapshot(
    _ topResults: [SimulationResultData],
    to url: URL
) throws {
    guard !topResults.isEmpty else { return }
    try writeResearchJSON(topResults, to: url, prettyPrinted: true)
}

public func activitySummaryRecord(
    for result: SimulationResultData,
    summarize: ([ActivitySnapshot]) -> ActivitySummary?
) -> ActivitySummaryRecord? {
    guard let snapshots = result.activity,
          let summary = summarize(snapshots)
    else {
        return nil
    }
    return ActivitySummaryRecord(
        seed: result.seed,
        workerId: result.workerId,
        summary: summary,
        implementation: result.implementation
    )
}

public func activitySummaryRecords(
    from results: [SimulationResultData],
    summarize: ([ActivitySnapshot]) -> ActivitySummary?
) -> [ActivitySummaryRecord] {
    results.compactMap { activitySummaryRecord(for: $0, summarize: summarize) }
}

public func activitySummaryRecord(
    for result: SimulationResultData,
    config: ActivityConfig?
) -> ActivitySummaryRecord? {
    guard let config, config.enabled else { return nil }
    return activitySummaryRecord(for: result) { summarizeActivity(snapshots: $0, config: config) }
}

public func activitySummaryRecords(
    from results: [SimulationResultData],
    config: ActivityConfig?
) -> [ActivitySummaryRecord] {
    guard let config, config.enabled else { return [] }
    return activitySummaryRecords(from: results) { summarizeActivity(snapshots: $0, config: config) }
}

private func finiteOrFallback(_ value: Float, fallback: Float) -> Float {
    value.isFinite ? value : fallback
}

private func finiteOptional(_ value: Float?, fallback: Float) -> Float {
    if let value, value.isFinite {
        return value
    }
    return fallback
}

private func finiteOptionalOrNil(_ value: Float?, fallback: Float?) -> Float? {
    if let value, value.isFinite {
        return value
    }
    if let fallback, fallback.isFinite {
        return fallback
    }
    return nil
}

private func fallbackTortuosity(pathLength: Float, displacement: Float) -> Float {
    let eps: Float = 1e-6
    guard displacement > eps else { return 0.0 }
    return pathLength / displacement
}

private func fallbackMovementEfficiency(pathLength: Float, displacement: Float) -> Float {
    let eps: Float = 1e-6
    guard pathLength > eps else { return 0.0 }
    return displacement / pathLength
}

public struct KernelParams: Codable, Sendable {
    public let r: [Float]
    public let b: [[Float]]
    public let w: [[Float]]
    public let a: [[Float]]
    public let m: [Float]
    public let s: [Float]
    public let h: [Float]
    public let R: Float

    public init(
        r: [Float],
        b: [[Float]],
        w: [[Float]],
        a: [[Float]],
        m: [Float],
        s: [Float],
        h: [Float],
        R: Float
    ) {
        self.r = r
        self.b = b
        self.w = w
        self.a = a
        self.m = m
        self.s = s
        self.h = h
        self.R = R
    }
}
