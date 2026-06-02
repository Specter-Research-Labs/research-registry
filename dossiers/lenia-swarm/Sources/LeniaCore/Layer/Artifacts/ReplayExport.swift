import Foundation

public struct CreatureExportRecord: Codable {
    public let creatureId: UUID
    public let name: String
    public let ownerId: String
    public let runId: String
    public let campaignId: String?
    public let bundleKind: LeniaArtifactBundleKind
    public let exportDir: String
    public let baseConfigPath: String?
    public let searchConfigPath: String?
    public let payloadPath: String?
    public let exportedAt: Date
    public let reason: String
    public let score: Float?
    public let filtersPassed: Bool?
    public let runtimeFamily: String
    public let runtimeCapabilities: [String]
    public let specimenManifest: SpecimenManifest

    enum CodingKeys: String, CodingKey {
        case creatureId
        case name
        case ownerId
        case runId
        case campaignId
        case bundleKind
        case exportDir
        case baseConfigPath
        case searchConfigPath
        case payloadPath
        case exportedAt
        case reason
        case score
        case filtersPassed
        case runtimeFamily
        case runtimeCapabilities
        case specimenManifest
    }

    public init(
        creatureId: UUID,
        name: String,
        ownerId: String,
        runId: String,
        campaignId: String?,
        bundleKind: LeniaArtifactBundleKind,
        exportDir: String,
        baseConfigPath: String?,
        searchConfigPath: String?,
        payloadPath: String? = nil,
        exportedAt: Date,
        reason: String,
        score: Float?,
        filtersPassed: Bool?,
        runtimeFamily: String? = nil,
        runtimeCapabilities: [String]? = nil,
        specimenManifest: SpecimenManifest? = nil
    ) {
        self.creatureId = creatureId
        self.name = name
        self.ownerId = ownerId
        self.runId = runId
        self.campaignId = campaignId
        self.bundleKind = bundleKind
        self.exportDir = exportDir
        self.baseConfigPath = baseConfigPath
        self.searchConfigPath = searchConfigPath
        self.payloadPath = payloadPath
        self.exportedAt = exportedAt
        self.reason = reason
        self.score = persistedFiniteScore(score)
        self.filtersPassed = filtersPassed
        let resolvedManifest = specimenManifest ?? buildExportSpecimenManifest(
            creatureID: creatureId.uuidString,
            runID: runId,
            campaignID: campaignId,
            recordedAt: exportedAt,
            sourceMode: nil,
            sourceAlgorithm: nil,
            configHash: nil,
            bundleKind: bundleKind,
            exportDir: exportDir,
            baseConfigPath: baseConfigPath,
            searchConfigPath: searchConfigPath,
            payloadPath: payloadPath
        )
        self.runtimeFamily = runtimeFamily ?? resolvedManifest.runtimeFamily
        self.runtimeCapabilities = (runtimeCapabilities ?? resolvedManifest.runtimeCapabilities).sorted()
        self.specimenManifest = resolvedManifest
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        creatureId = try container.decode(UUID.self, forKey: .creatureId)
        name = try container.decode(String.self, forKey: .name)
        ownerId = try container.decode(String.self, forKey: .ownerId)
        runId = try container.decode(String.self, forKey: .runId)
        campaignId = try container.decodeIfPresent(String.self, forKey: .campaignId)
        bundleKind = try container.decode(LeniaArtifactBundleKind.self, forKey: .bundleKind)
        exportDir = try container.decode(String.self, forKey: .exportDir)
        baseConfigPath = try container.decodeIfPresent(String.self, forKey: .baseConfigPath)
        searchConfigPath = try container.decodeIfPresent(String.self, forKey: .searchConfigPath)
        payloadPath = try container.decodeIfPresent(String.self, forKey: .payloadPath)
        exportedAt = try container.decode(Date.self, forKey: .exportedAt)
        reason = try container.decode(String.self, forKey: .reason)
        score = persistedFiniteScore(try container.decodeIfPresent(Float.self, forKey: .score))
        filtersPassed = try container.decodeIfPresent(Bool.self, forKey: .filtersPassed)
        let decodedManifest = try container.decodeIfPresent(SpecimenManifest.self, forKey: .specimenManifest)
        let backfilledManifest = decodedManifest ?? buildExportSpecimenManifest(
            creatureID: creatureId.uuidString,
            runID: runId,
            campaignID: campaignId,
            recordedAt: exportedAt,
            sourceMode: nil,
            sourceAlgorithm: nil,
            configHash: nil,
            bundleKind: bundleKind,
            exportDir: exportDir,
            baseConfigPath: baseConfigPath,
            searchConfigPath: searchConfigPath,
            payloadPath: payloadPath
        )
        runtimeFamily = try container.decodeIfPresent(String.self, forKey: .runtimeFamily)
            ?? backfilledManifest.runtimeFamily
        runtimeCapabilities = (
            try container.decodeIfPresent([String].self, forKey: .runtimeCapabilities)
                ?? backfilledManifest.runtimeCapabilities
        ).sorted()
        specimenManifest = backfilledManifest
    }
}

public struct CreatureExportMetadata: Codable {
    public let creature: SavedCreature
    public let runId: String
    public let campaignId: String?
    public let bundleKind: LeniaArtifactBundleKind
    public let exportedAt: Date
    public let reason: String
    public let score: Float?
    public let filtersPassed: Bool?
    public let runtimeFamily: String
    public let runtimeCapabilities: [String]
    public let specimenManifest: SpecimenManifest

    enum CodingKeys: String, CodingKey {
        case creature
        case runId
        case campaignId
        case bundleKind
        case exportedAt
        case reason
        case score
        case filtersPassed
        case runtimeFamily
        case runtimeCapabilities
        case specimenManifest
    }

    public init(
        creature: SavedCreature,
        runId: String,
        campaignId: String?,
        bundleKind: LeniaArtifactBundleKind,
        exportedAt: Date,
        reason: String,
        score: Float?,
        filtersPassed: Bool?,
        runtimeFamily: String? = nil,
        runtimeCapabilities: [String]? = nil,
        specimenManifest: SpecimenManifest? = nil
    ) {
        self.creature = creature
        self.runId = runId
        self.campaignId = campaignId
        self.bundleKind = bundleKind
        self.exportedAt = exportedAt
        self.reason = reason
        self.score = persistedFiniteScore(score)
        self.filtersPassed = filtersPassed
        let replay = SpecimenReplayRecord(bundleKind: bundleKind)
        let resolvedManifest = specimenManifest ?? SpecimenManifest(
            specimenID: creature.id.uuidString,
            creatureID: creature.id.uuidString,
            runID: runId,
            campaignID: campaignId,
            sourceKind: "export_metadata",
            sourceMode: nil,
            sourceAlgorithm: nil,
            runtimeFamily: specimenRuntimeFamily(sourceMode: nil, bundleKind: bundleKind).rawValue,
            runtimeCapabilities: specimenRuntimeCapabilities(
                descriptorBundle: creature.descriptorBundle,
                bundleKind: bundleKind,
                researchMetadata: nil
            ),
            configHash: creature.configHash,
            recordedAt: exportedAt,
            initialConditionFamily: creature.initialConditionFamily ?? morphospaceInitialConditionFamily(creature.initialCondition),
            replay: replay,
            snapshots: SpecimenSnapshotRecord(
                genotype: creature.genotype,
                initialCondition: creature.initialCondition,
                metrics: creature.metrics,
                descriptorBundle: creature.descriptorBundle
            )
        )
        self.runtimeFamily = runtimeFamily ?? resolvedManifest.runtimeFamily
        self.runtimeCapabilities = (runtimeCapabilities ?? resolvedManifest.runtimeCapabilities).sorted()
        self.specimenManifest = resolvedManifest
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        creature = try container.decode(SavedCreature.self, forKey: .creature)
        runId = try container.decode(String.self, forKey: .runId)
        campaignId = try container.decodeIfPresent(String.self, forKey: .campaignId)
        bundleKind = try container.decode(LeniaArtifactBundleKind.self, forKey: .bundleKind)
        exportedAt = try container.decode(Date.self, forKey: .exportedAt)
        reason = try container.decode(String.self, forKey: .reason)
        score = persistedFiniteScore(try container.decodeIfPresent(Float.self, forKey: .score))
        filtersPassed = try container.decodeIfPresent(Bool.self, forKey: .filtersPassed)
        let decodedManifest = try container.decodeIfPresent(SpecimenManifest.self, forKey: .specimenManifest)
        let backfilledManifest = decodedManifest ?? SpecimenManifest(
            specimenID: creature.id.uuidString,
            creatureID: creature.id.uuidString,
            runID: runId,
            campaignID: campaignId,
            sourceKind: "export_metadata",
            sourceMode: nil,
            sourceAlgorithm: nil,
            runtimeFamily: specimenRuntimeFamily(sourceMode: nil, bundleKind: bundleKind).rawValue,
            runtimeCapabilities: specimenRuntimeCapabilities(
                descriptorBundle: creature.descriptorBundle,
                bundleKind: bundleKind,
                researchMetadata: nil
            ),
            configHash: creature.configHash,
            recordedAt: exportedAt,
            initialConditionFamily: creature.initialConditionFamily ?? morphospaceInitialConditionFamily(creature.initialCondition),
            replay: SpecimenReplayRecord(bundleKind: bundleKind),
            snapshots: SpecimenSnapshotRecord(
                genotype: creature.genotype,
                initialCondition: creature.initialCondition,
                metrics: creature.metrics,
                descriptorBundle: creature.descriptorBundle
            )
        )
        runtimeFamily = try container.decodeIfPresent(String.self, forKey: .runtimeFamily)
            ?? backfilledManifest.runtimeFamily
        runtimeCapabilities = (
            try container.decodeIfPresent([String].self, forKey: .runtimeCapabilities)
                ?? backfilledManifest.runtimeCapabilities
        ).sorted()
        specimenManifest = backfilledManifest
    }
}

public func decodeCreatureExportMetadata(
    _ data: Data,
    decoder: JSONDecoder,
    fallbackBundleKind: LeniaArtifactBundleKind? = nil
) throws -> CreatureExportMetadata {
    do {
        return try decoder.decode(CreatureExportMetadata.self, from: data)
    } catch DecodingError.keyNotFound(let key, let context)
        where (context.codingPath.map(\.stringValue) == ["creature"] && key.stringValue == "initialCondition")
            || (context.codingPath.isEmpty && key.stringValue == "bundleKind") {
        let normalized = try normalizeLegacyCreatureExportMetadataData(
            data,
            fallbackBundleKind: fallbackBundleKind
        )
        return try decoder.decode(CreatureExportMetadata.self, from: normalized)
    }
}

private func normalizeLegacyCreatureExportMetadataData(
    _ data: Data,
    fallbackBundleKind: LeniaArtifactBundleKind?
) throws -> Data {
    guard var root = try JSONSerialization.jsonObject(with: data) as? [String: Any],
          var creature = root["creature"] as? [String: Any] else {
        return data
    }
    if root["bundleKind"] == nil, let fallbackBundleKind {
        root["bundleKind"] = fallbackBundleKind.rawValue
    }
    if creature["initialCondition"] == nil, let legacy = creature["phenotype"] {
        creature["initialCondition"] = legacy
    }
    root["creature"] = creature
    return try JSONSerialization.data(withJSONObject: root, options: [.sortedKeys])
}

public struct CreatureExportArtifacts {
    public let exportDir: URL
    public let baseConfigURL: URL?
    public let searchConfigURL: URL?
    public let payloadURL: URL?
    public let metadataURL: URL
    public let metadata: CreatureExportMetadata
    public let record: CreatureExportRecord

    public init(
        exportDir: URL,
        baseConfigURL: URL?,
        searchConfigURL: URL?,
        payloadURL: URL? = nil,
        metadataURL: URL,
        metadata: CreatureExportMetadata,
        record: CreatureExportRecord
    ) {
        self.exportDir = exportDir
        self.baseConfigURL = baseConfigURL
        self.searchConfigURL = searchConfigURL
        self.payloadURL = payloadURL
        self.metadataURL = metadataURL
        self.metadata = metadata
        self.record = record
    }
}

public func replayExportDirectory(root: URL, creature: SavedCreature) -> URL {
    let slug = sanitizeExportPathComponent(creature.name)
    let shortId = String(creature.id.uuidString.prefix(8))
    return root.appendingPathComponent("\(slug)-\(shortId)", isDirectory: true)
}

public func buildReplayBaseConfig(
    baseConfig: LeniaBaseConfig,
    searchConfig: ParsedSearchConfig,
    creature: SavedCreature
) throws -> LeniaBaseConfig {
    var overrides = searchConfig.overridesAsDict()
    if let sweepOverrides = creature.sweep {
        for (key, value) in sweepOverrides {
            overrides[key] = value
        }
    }
    overrides["run.steps"] = Double(searchConfig.steps)

    let baseData = try JSONEncoder().encode(baseConfig)
    guard var json = try JSONSerialization.jsonObject(with: baseData) as? [String: Any] else {
        throw ConfigError.invalidConfig("Base config JSON must be an object.")
    }
    applyOverrides(&json, overrides: overrides)

    let modified = try JSONSerialization.data(withJSONObject: json)
    let overridden = try JSONDecoder().decode(LeniaBaseConfig.self, from: modified)

    let explicitParams = ParamsConfig(
        mode: "explicit",
        seed: nil,
        ranges: nil,
        r: creature.genotype.r,
        b: creature.genotype.b,
        w: creature.genotype.w,
        a: creature.genotype.a,
        m: creature.genotype.m,
        s: creature.genotype.s,
        h: creature.genotype.h,
        R: creature.genotype.R
    )

    let exportInit = InitConfig(
        seed: creature.initialCondition.seed,
        patches: creature.initialCondition.patches,
        a_uniform: creature.initialCondition.a_uniform,
        p_uniform: creature.initialCondition.p_uniform,
        state_patch: creature.initialCondition.state_patch,
        p_state_patch: creature.initialCondition.p_state_patch
    )

    return LeniaBaseConfig(
        backend: overridden.backend,
        profile: overridden.profile,
        grid: overridden.grid,
        channels: overridden.channels,
        connectivity: overridden.connectivity,
        flow: overridden.flow,
        implementation: overridden.implementation,
        reintegration: overridden.reintegration,
        parameter_embedding: overridden.parameter_embedding,
        chemotaxis: overridden.chemotaxis,
        obstacle_field: overridden.obstacle_field,
        food: overridden.food,
        walls: overridden.walls,
        environment: overridden.environment,
        beam_mutation: overridden.beam_mutation,
        params: explicitParams,
        init: exportInit,
        run: RunConfig(steps: searchConfig.steps),
        interventions: overridden.interventions
    )
}

private func replayRecordInterval(steps: Int, warmupSteps: Int, preferred: Int) -> Int {
    let cappedWarmup = min(max(warmupSteps, 0), max(steps - 1, 0))
    let available = max(1, steps - cappedWarmup)
    return max(1, min(preferred, available))
}

private func replaySupportsActivity(baseConfig: LeniaBaseConfig) -> Bool {
    baseConfig.parameter_embedding.enabled &&
        (baseConfig.`init`.p_uniform != nil || baseConfig.`init`.p_state_patch != nil)
}

private func strictReplayActivityConfig(steps: Int) -> ActivityConfig {
    ActivityConfig(
        enabled: true,
        interval: max(1, steps / 8),
        threshold: 0.05,
        maxComponents: 64,
        matchThreshold: 1.5,
        paramWeight: 1.0,
        positionWeight: 0.05
    )
}

private func strictReplayMomentsConfig(existing: MomentsConfig?) -> MomentsConfig {
    MomentsConfig(
        enabled: true,
        threshold: existing?.threshold ?? 0.01
    )
}

private func strictReplayStabilityConfig(existing: StabilityConfig?) -> StabilityConfig {
    StabilityConfig(
        enabled: true,
        massMinFraction: existing?.massMinFraction ?? 0.001,
        massMaxFraction: existing?.massMaxFraction ?? StabilityConfig.defaultConfig.massMaxFraction,
        requireSurvival: existing?.requireSurvival ?? StabilityConfig.defaultConfig.requireSurvival,
        windowSamples: existing?.windowSamples ?? StabilityConfig.defaultConfig.windowSamples,
        windowMassStdMax: existing?.windowMassStdMax ?? StabilityConfig.defaultConfig.windowMassStdMax,
        windowOccupancyStdMax: existing?.windowOccupancyStdMax ?? StabilityConfig.defaultConfig.windowOccupancyStdMax,
        windowGyrationStdMax: existing?.windowGyrationStdMax ?? StabilityConfig.defaultConfig.windowGyrationStdMax,
        filters: existing?.filters ?? StabilityConfig.defaultConfig.filters
    )
}

public func buildStrictReplaySearchConfig(
    steps: Int,
    initSeedOffset: Int,
    supportsActivity: Bool = true,
    morphologyThreshold: Float = 0.01
) -> ParsedSearchConfig {
    let clampedSteps = max(1, steps)
    let threshold = max(morphologyThreshold, 0)
    return ParsedSearchConfig(
        count: 1,
        seedStart: 0,
        seedStride: 1,
        initSeedOffset: initSeedOffset,
        steps: clampedSteps,
        recordInterval: max(1, clampedSteps / 8),
        warmupSteps: 0,
        occupancyThreshold: threshold,
        massChannel: 0,
        scoreWeights: [:],
        filters: [:],
        overrides: [:],
        topK: 1,
        batchSize: 1,
        seedsPerJob: 1,
        complexity: nil,
        activity: supportsActivity ? strictReplayActivityConfig(steps: clampedSteps) : nil,
        stability: strictReplayStabilityConfig(existing: nil),
        moments: MomentsConfig(enabled: true, threshold: threshold),
        collection: CollectionConfig(
            enabled: false,
            requireStable: false,
            requireFiltersPassed: false,
            minScore: nil,
            exportEnabled: false
        )
    )
}

public func buildReplaySearchConfig(
    from searchConfig: ParsedSearchConfig,
    initSeedOffset: Int? = nil,
    enableMorphospaceSignals: Bool = false,
    supportsActivity: Bool = false
) -> ParsedSearchConfig {
    let resolvedInitSeedOffset = initSeedOffset ?? searchConfig.initSeedOffset ?? 0
    let exportCollection = CollectionConfig(
        enabled: false,
        requireStable: false,
        requireFiltersPassed: false,
        minScore: nil,
        exportEnabled: false
    )
    let steps = max(1, searchConfig.steps)
    let warmupSteps = min(max(searchConfig.warmupSteps, 0), max(steps - 1, 0))
    let recordInterval = replayRecordInterval(
        steps: steps,
        warmupSteps: warmupSteps,
        preferred: max(1, searchConfig.recordInterval)
    )
    let activity: ActivityConfig?
    if enableMorphospaceSignals {
        if supportsActivity {
            let existing = searchConfig.activity
            activity = ActivityConfig(
                enabled: true,
                interval: existing?.interval ?? max(1, steps / 8),
                threshold: existing?.threshold ?? 0.05,
                maxComponents: existing?.maxComponents ?? 64,
                matchThreshold: existing?.matchThreshold ?? 1.5,
                paramWeight: existing?.paramWeight ?? 1.0,
                positionWeight: existing?.positionWeight ?? 0.05
            )
        } else {
            activity = nil
        }
    } else {
        activity = searchConfig.activity
    }
    let stability = enableMorphospaceSignals
        ? strictReplayStabilityConfig(existing: searchConfig.stability)
        : searchConfig.stability
    let moments = enableMorphospaceSignals
        ? strictReplayMomentsConfig(existing: searchConfig.moments)
        : searchConfig.moments
    return ParsedSearchConfig(
        count: 1,
        seedStart: 0,
        seedStride: 1,
        initSeedOffset: resolvedInitSeedOffset,
        steps: steps,
        recordInterval: recordInterval,
        warmupSteps: warmupSteps,
        occupancyThreshold: searchConfig.occupancyThreshold,
        massChannel: searchConfig.massChannel,
        scoreWeights: searchConfig.scoreWeights,
        filters: searchConfig.filters,
        overrides: [:],
        topK: 1,
        batchSize: 1,
        seedsPerJob: 1,
        complexity: searchConfig.complexity,
        activity: activity,
        stability: stability,
        moments: moments,
        collection: exportCollection
    )
}

public func writeReplayExportArtifacts(
    exportRoot: URL,
    baseConfig: LeniaBaseConfig,
    searchConfig: ParsedSearchConfig,
    creature: SavedCreature,
    runId: String,
    campaignId: UUID?,
    score: Float?,
    filtersPassed: Bool?,
    reason: String,
    exportedAt: Date = Date()
) throws -> CreatureExportArtifacts? {
    let exportDir = replayExportDirectory(root: exportRoot, creature: creature)
    if FileManager.default.fileExists(atPath: exportDir.path) {
        return nil
    }

    try FileManager.default.createDirectory(at: exportDir, withIntermediateDirectories: true)

    let replayBaseConfig = try buildReplayBaseConfig(
        baseConfig: baseConfig,
        searchConfig: searchConfig,
        creature: creature
    )
    let replaySearchConfig = buildReplaySearchConfig(
        from: searchConfig,
        initSeedOffset: creature.initialCondition.seed,
        enableMorphospaceSignals: true,
        supportsActivity: replaySupportsActivity(baseConfig: replayBaseConfig)
    )

    let baseURL = exportDir.appendingPathComponent("base.json")
    let searchURL = exportDir.appendingPathComponent("search.json")
    let metaURL = exportDir.appendingPathComponent("meta.json")

    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    try encoder.encode(replayBaseConfig).write(to: baseURL)
    try encoder.encode(replaySearchConfig).write(to: searchURL)

    let metadata = CreatureExportMetadata(
        creature: creature,
        runId: runId,
        campaignId: campaignId?.uuidString,
        bundleKind: .strictReplayBundleV1,
        exportedAt: exportedAt,
        reason: reason,
        score: score,
        filtersPassed: filtersPassed
    )
    try encoder.encode(metadata).write(to: metaURL)

    let record = CreatureExportRecord(
        creatureId: creature.id,
        name: creature.name,
        ownerId: creature.ownerId,
        runId: runId,
        campaignId: campaignId?.uuidString,
        bundleKind: .strictReplayBundleV1,
        exportDir: exportDir.path,
        baseConfigPath: baseURL.path,
        searchConfigPath: searchURL.path,
        payloadPath: nil,
        exportedAt: exportedAt,
        reason: reason,
        score: score,
        filtersPassed: filtersPassed
    )
    return CreatureExportArtifacts(
        exportDir: exportDir,
        baseConfigURL: baseURL,
        searchConfigURL: searchURL,
        payloadURL: nil,
        metadataURL: metaURL,
        metadata: metadata,
        record: record
    )
}

public func writePayloadReplayExportArtifacts<Payload: Encodable>(
    exportRoot: URL,
    creature: SavedCreature,
    runId: String,
    campaignId: String?,
    bundleKind: LeniaArtifactBundleKind,
    payload: Payload,
    reason: String,
    score: Float?,
    filtersPassed: Bool?,
    exportedAt: Date = Date()
) throws -> CreatureExportArtifacts? {
    let exportDir = replayExportDirectory(root: exportRoot, creature: creature)
    if FileManager.default.fileExists(atPath: exportDir.path) {
        return nil
    }

    try FileManager.default.createDirectory(at: exportDir, withIntermediateDirectories: true)

    let payloadURL = exportDir.appendingPathComponent("payload.json")
    let metaURL = exportDir.appendingPathComponent("meta.json")

    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    encoder.dateEncodingStrategy = .deferredToDate
    try encoder.encode(payload).write(to: payloadURL)

    let metadata = CreatureExportMetadata(
        creature: creature,
        runId: runId,
        campaignId: campaignId,
        bundleKind: bundleKind,
        exportedAt: exportedAt,
        reason: reason,
        score: score,
        filtersPassed: filtersPassed
    )
    try encoder.encode(metadata).write(to: metaURL)

    let record = CreatureExportRecord(
        creatureId: creature.id,
        name: creature.name,
        ownerId: creature.ownerId,
        runId: runId,
        campaignId: campaignId,
        bundleKind: bundleKind,
        exportDir: exportDir.path,
        baseConfigPath: nil,
        searchConfigPath: nil,
        payloadPath: payloadURL.path,
        exportedAt: exportedAt,
        reason: reason,
        score: score,
        filtersPassed: filtersPassed
    )
    return CreatureExportArtifacts(
        exportDir: exportDir,
        baseConfigURL: nil,
        searchConfigURL: nil,
        payloadURL: payloadURL,
        metadataURL: metaURL,
        metadata: metadata,
        record: record
    )
}

public func writeReplayExportBatch<T>(
    exportRoot: URL,
    items: [T],
    resolve: (T) throws -> (
        baseConfig: LeniaBaseConfig,
        searchConfig: ParsedSearchConfig,
        creature: SavedCreature,
        runId: String,
        campaignId: UUID?,
        score: Float?,
        filtersPassed: Bool?,
        reason: String
    )
) throws -> [CreatureExportRecord] {
    guard !items.isEmpty else { return [] }
    try FileManager.default.createDirectory(at: exportRoot, withIntermediateDirectories: true)

    var records: [CreatureExportRecord] = []
    records.reserveCapacity(items.count)
    for item in items {
        let request = try resolve(item)
        guard let artifacts = try writeReplayExportArtifacts(
            exportRoot: exportRoot,
            baseConfig: request.baseConfig,
            searchConfig: request.searchConfig,
            creature: request.creature,
            runId: request.runId,
            campaignId: request.campaignId,
            score: request.score,
            filtersPassed: request.filtersPassed,
            reason: request.reason
        ) else {
            continue
        }
        records.append(artifacts.record)
    }

    if !records.isEmpty {
        _ = try writeCreatureExportIndex(records, to: exportRoot)
    }
    return records
}

public func writePayloadReplayExportBatch<T, Payload: Encodable>(
    exportRoot: URL,
    items: [T],
    resolve: (T) throws -> (
        creature: SavedCreature,
        runId: String,
        campaignId: String?,
        bundleKind: LeniaArtifactBundleKind,
        payload: Payload,
        reason: String,
        score: Float?,
        filtersPassed: Bool?,
        exportedAt: Date
    )
) throws -> [CreatureExportRecord] {
    guard !items.isEmpty else { return [] }
    try FileManager.default.createDirectory(at: exportRoot, withIntermediateDirectories: true)

    var records: [CreatureExportRecord] = []
    records.reserveCapacity(items.count)
    for item in items {
        let request = try resolve(item)
        guard let artifacts = try writePayloadReplayExportArtifacts(
            exportRoot: exportRoot,
            creature: request.creature,
            runId: request.runId,
            campaignId: request.campaignId,
            bundleKind: request.bundleKind,
            payload: request.payload,
            reason: request.reason,
            score: request.score,
            filtersPassed: request.filtersPassed,
            exportedAt: request.exportedAt
        ) else {
            continue
        }
        records.append(artifacts.record)
    }

    if !records.isEmpty {
        _ = try writeCreatureExportIndex(records, to: exportRoot)
    }
    return records
}

public func writeCreatureExportIndex(
    _ records: [CreatureExportRecord],
    to exportsDirectory: URL
) throws -> URL {
    let indexURL = exportsDirectory.appendingPathComponent("index.jsonl")
    try writeResearchJSONLines(records, to: indexURL)
    return indexURL
}
private func sanitizeExportPathComponent(_ value: String) -> String {
    let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_"))
    let lower = value.lowercased()
    let mapped = lower.unicodeScalars.map { allowed.contains($0) ? Character($0) : "-" }
    let raw = String(mapped)
    let collapsed = raw.replacingOccurrences(of: "-+", with: "-", options: .regularExpression)
    let trimmed = collapsed.trimmingCharacters(in: CharacterSet(charactersIn: "-"))
    return trimmed.isEmpty ? "creature" : trimmed
}
