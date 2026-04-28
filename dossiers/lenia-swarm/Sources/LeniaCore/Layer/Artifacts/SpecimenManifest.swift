import Foundation

public struct SpecimenTaxonomyRecord: Codable, Sendable {
    public let familyID: String?
    public let genusID: String?
    public let speciesID: String?
    public let confidence: Double?
    public let method: String?
    public let version: Int?

    public init(
        familyID: String? = nil,
        genusID: String? = nil,
        speciesID: String? = nil,
        confidence: Double? = nil,
        method: String? = nil,
        version: Int? = nil
    ) {
        self.familyID = familyID
        self.genusID = genusID
        self.speciesID = speciesID
        self.confidence = confidence
        self.method = method
        self.version = version
    }
}

public struct SpecimenReplayRecord: Codable, Sendable {
    public let bundleKind: LeniaArtifactBundleKind?
    public let exportDir: String?
    public let baseConfigPath: String?
    public let searchConfigPath: String?
    public let payloadPath: String?

    public init(
        bundleKind: LeniaArtifactBundleKind? = nil,
        exportDir: String? = nil,
        baseConfigPath: String? = nil,
        searchConfigPath: String? = nil,
        payloadPath: String? = nil
    ) {
        self.bundleKind = bundleKind
        self.exportDir = exportDir
        self.baseConfigPath = baseConfigPath
        self.searchConfigPath = searchConfigPath
        self.payloadPath = payloadPath
    }
}

public struct SpecimenSnapshotRecord: Codable, Sendable {
    public let genotype: KernelParams?
    public let initialCondition: InitConfig?
    public let metrics: SimulationMetrics?
    public let descriptorBundle: MorphospaceDescriptorBundle?
    public let morphometrics: Morphometrics?

    public init(
        genotype: KernelParams? = nil,
        initialCondition: InitConfig? = nil,
        metrics: SimulationMetrics? = nil,
        descriptorBundle: MorphospaceDescriptorBundle? = nil,
        morphometrics: Morphometrics? = nil
    ) {
        self.genotype = genotype
        self.initialCondition = initialCondition
        self.metrics = metrics
        self.descriptorBundle = descriptorBundle
        self.morphometrics = morphometrics
    }
}

public struct SpecimenManifest: Codable, Sendable {
    public var version: Int
    public var specimenID: String?
    public var creatureID: String?
    public var runID: String
    public var campaignID: String?
    public var sourceKind: String
    public var sourceMode: String?
    public var sourceAlgorithm: String?
    public var runtimeFamily: String
    public var runtimeCapabilities: [String]
    public var configHash: String?
    public var recordedAt: Date?
    public var initialConditionFamily: String?
    public var taxonomy: SpecimenTaxonomyRecord?
    public var traitLabels: [String]?
    public var replay: SpecimenReplayRecord?
    public var snapshots: SpecimenSnapshotRecord
    public var researchMetadata: [String: AnyCodable]?

    public init(
        version: Int = 1,
        specimenID: String? = nil,
        creatureID: String? = nil,
        runID: String,
        campaignID: String?,
        sourceKind: String,
        sourceMode: String? = nil,
        sourceAlgorithm: String? = nil,
        runtimeFamily: String,
        runtimeCapabilities: [String],
        configHash: String? = nil,
        recordedAt: Date? = nil,
        initialConditionFamily: String? = nil,
        taxonomy: SpecimenTaxonomyRecord? = nil,
        traitLabels: [String]? = nil,
        replay: SpecimenReplayRecord? = nil,
        snapshots: SpecimenSnapshotRecord,
        researchMetadata: [String: AnyCodable]? = nil
    ) {
        self.version = version
        self.specimenID = specimenID
        self.creatureID = creatureID
        self.runID = runID
        self.campaignID = campaignID
        self.sourceKind = sourceKind
        self.sourceMode = sourceMode
        self.sourceAlgorithm = sourceAlgorithm
        self.runtimeFamily = runtimeFamily
        self.runtimeCapabilities = runtimeCapabilities.sorted()
        self.configHash = configHash
        self.recordedAt = recordedAt
        self.initialConditionFamily = initialConditionFamily
        self.taxonomy = taxonomy
        self.traitLabels = traitLabels?.sorted()
        self.replay = replay
        self.snapshots = snapshots
        self.researchMetadata = researchMetadata
    }
}

public struct ResolvedSpecimenProjection: Sendable {
    public let manifest: SpecimenManifest?
    public let creature: SavedCreature
    public let runtimeFamily: String?
    public let runtimeCapabilities: [String]
    public let sourceMode: String?
    public let sourceAlgorithm: String?
    public let researchMetadata: [String: AnyCodable]?
    public let traitLabels: [String]

    public init(
        manifest: SpecimenManifest?,
        creature: SavedCreature,
        runtimeFamily: String?,
        runtimeCapabilities: [String],
        sourceMode: String?,
        sourceAlgorithm: String?,
        researchMetadata: [String: AnyCodable]?,
        traitLabels: [String]
    ) {
        self.manifest = manifest
        self.creature = creature
        self.runtimeFamily = runtimeFamily
        self.runtimeCapabilities = runtimeCapabilities
        self.sourceMode = sourceMode
        self.sourceAlgorithm = sourceAlgorithm
        self.researchMetadata = researchMetadata
        self.traitLabels = traitLabels
    }
}

public func canonicalExportBundleKind(from researchMetadata: [String: AnyCodable]?) -> LeniaArtifactBundleKind? {
    guard let researchMetadata else {
        return nil
    }
    if let rawValue = researchMetadata["canonical_export_kind"]?.value as? String {
        return LeniaArtifactBundleKind(rawValue: rawValue)
    }
    if let sourceResearchMetadata = researchMetadata["source_research_metadata"]?.value as? [String: Any],
       let rawValue = sourceResearchMetadata["canonical_export_kind"] as? String {
        return LeniaArtifactBundleKind(rawValue: rawValue)
    }
    return nil
}

public func specimenRuntimeFamily(
    sourceMode: String?,
    bundleKind: LeniaArtifactBundleKind? = nil,
    backend: String? = nil,
    researchMetadata: [String: AnyCodable]? = nil
) -> LeniaRuntimeFamily {
    if let bundleKind {
        switch bundleKind {
        case .strictReplayBundleV1:
            return .flowLenia
        case .flowLeniaEcology2025ArenaReplayBundleV1:
            return .flowLenia
        case .qd24PaperReplayBundleV1:
            return .qd24Paper
        case .sensorimotor24PaperReplayBundleV1:
            return .sensorimotor24Paper
        }
    }

    if let bundleKind = canonicalExportBundleKind(from: researchMetadata) {
        return specimenRuntimeFamily(sourceMode: sourceMode, bundleKind: bundleKind, backend: backend)
    }

    if let sourceMode = normalizedSpecimenSourceMode(sourceMode) {
        switch sourceMode {
        case "qd-2024":
            return .qd24Paper
        case "sensorimotor-2024":
            return .sensorimotor24Paper
        case "replay":
            if let sourceMode = researchMetadata?["source_mode"]?.value as? String {
                return specimenRuntimeFamily(sourceMode: sourceMode, bundleKind: nil, backend: backend)
            }
        default:
            break
        }
    }

    if let backend = normalizedSpecimenText(backend) {
        switch backend {
        case "qd24-paper":
            return .qd24Paper
        case "sensorimotor24-paper":
            return .sensorimotor24Paper
        default:
            break
        }
    }

    return .flowLenia
}

public func specimenRuntimeCapabilities(
    descriptorBundle: MorphospaceDescriptorBundle?,
    bundleKind: LeniaArtifactBundleKind? = nil,
    researchMetadata: [String: AnyCodable]? = nil
) -> [String] {
    var capabilities: Set<LeniaArtifactCapability> = [.archive, .warehouseIngest]

    let replayable = bundleKind != nil || researchMetadataBool("canonical_export_available", in: researchMetadata)
    if replayable {
        capabilities.insert(.replay)
        capabilities.insert(.intervention)
        capabilities.insert(.media)
    }

    let topologyReady = descriptorBundle != nil || researchMetadataBool("morphospace_ready", in: researchMetadata)
    if topologyReady {
        capabilities.insert(.topology)
    }

    return capabilities.map(\.rawValue).sorted()
}

public func buildSpecimenManifest(
    specimenID: String?,
    creatureID: String?,
    runID: String,
    campaignID: String?,
    sourceKind: String,
    sourceMode: String?,
    sourceAlgorithm: String?,
    configHash: String?,
    recordedAt: Date?,
    initialConditionFamily: String? = nil,
    taxonomy: SpecimenTaxonomyRecord? = nil,
    traitLabels: [String]? = nil,
    replay: SpecimenReplayRecord? = nil,
    snapshots: SpecimenSnapshotRecord,
    backend: String? = nil,
    researchMetadata: [String: AnyCodable]? = nil
) -> SpecimenManifest {
    let canonicalSourceMode = normalizedSpecimenSourceMode(sourceMode)
    let bundleKind = replay?.bundleKind
    let runtimeFamily = specimenRuntimeFamily(
        sourceMode: canonicalSourceMode,
        bundleKind: bundleKind,
        backend: backend,
        researchMetadata: researchMetadata
    )
    let runtimeCapabilities = specimenRuntimeCapabilities(
        descriptorBundle: snapshots.descriptorBundle,
        bundleKind: bundleKind,
        researchMetadata: researchMetadata
    )
    return SpecimenManifest(
        specimenID: specimenID,
        creatureID: creatureID,
        runID: runID,
        campaignID: campaignID,
        sourceKind: sourceKind,
        sourceMode: canonicalSourceMode,
        sourceAlgorithm: sourceAlgorithm,
        runtimeFamily: runtimeFamily.rawValue,
        runtimeCapabilities: runtimeCapabilities,
        configHash: configHash,
        recordedAt: recordedAt,
        initialConditionFamily: initialConditionFamily,
        taxonomy: taxonomy,
        traitLabels: traitLabels,
        replay: replay,
        snapshots: snapshots,
        researchMetadata: researchMetadata
    )
}

public func buildLibrarySpecimenManifest(
    creature: SavedCreature,
    campaignID: String?,
    runID: String,
    recordedAt: Date,
    configHash: String?,
    sourceMode: String?,
    sourceAlgorithm: String?,
    researchMetadata: [String: AnyCodable]?,
    taxonomy: SpecimenTaxonomyRecord? = nil,
    traitLabels: [String]? = nil,
    morphometrics: Morphometrics? = nil
) -> SpecimenManifest {
    let bundleKind = canonicalExportBundleKind(from: researchMetadata)
    return buildSpecimenManifest(
        specimenID: creature.id.uuidString,
        creatureID: creature.id.uuidString,
        runID: runID,
        campaignID: campaignID,
        sourceKind: "library",
        sourceMode: sourceMode,
        sourceAlgorithm: sourceAlgorithm,
        configHash: configHash ?? creature.configHash,
        recordedAt: recordedAt,
        initialConditionFamily: creature.initialConditionFamily ?? morphospaceInitialConditionFamily(creature.initialCondition),
        taxonomy: taxonomy,
        traitLabels: traitLabels,
        replay: SpecimenReplayRecord(bundleKind: bundleKind),
        snapshots: SpecimenSnapshotRecord(
            genotype: creature.genotype,
            initialCondition: creature.initialCondition,
            metrics: creature.metrics,
            descriptorBundle: creature.descriptorBundle,
            morphometrics: morphometrics
        ),
        researchMetadata: researchMetadata
    )
}

public func buildExportSpecimenManifest(
    creatureID: String,
    runID: String,
    campaignID: String?,
    recordedAt: Date,
    sourceMode: String?,
    sourceAlgorithm: String?,
    configHash: String?,
    bundleKind: LeniaArtifactBundleKind,
    exportDir: String,
    baseConfigPath: String?,
    searchConfigPath: String?,
    payloadPath: String?,
    researchMetadata: [String: AnyCodable]? = nil
) -> SpecimenManifest {
    return buildSpecimenManifest(
        specimenID: creatureID,
        creatureID: creatureID,
        runID: runID,
        campaignID: campaignID,
        sourceKind: "export",
        sourceMode: sourceMode,
        sourceAlgorithm: sourceAlgorithm,
        configHash: configHash,
        recordedAt: recordedAt,
        replay: SpecimenReplayRecord(
            bundleKind: bundleKind,
            exportDir: exportDir,
            baseConfigPath: baseConfigPath,
            searchConfigPath: searchConfigPath,
            payloadPath: payloadPath
        ),
        snapshots: SpecimenSnapshotRecord(),
        researchMetadata: researchMetadata
    )
}

public func buildResultSpecimenManifest(
    specimenID: String,
    runID: String,
    campaignID: String?,
    sourceMode: String?,
    sourceAlgorithm: String?,
    configHash: String?,
    initialConditionFamily: String?,
    result: SimulationResultData
) -> SpecimenManifest {
    return buildSpecimenManifest(
        specimenID: specimenID,
        creatureID: nil,
        runID: runID,
        campaignID: campaignID,
        sourceKind: "result",
        sourceMode: sourceMode,
        sourceAlgorithm: sourceAlgorithm,
        configHash: configHash,
        recordedAt: nil,
        initialConditionFamily: initialConditionFamily,
        snapshots: SpecimenSnapshotRecord(
            metrics: result.metrics,
            descriptorBundle: result.descriptorBundle
        ),
        backend: result.backend
    )
}

public func savedCreatureFromSpecimenManifest(
    id: UUID,
    name: String,
    ownerId: String,
    manifest: SpecimenManifest?,
    fallbackGenotype: KernelParams,
    fallbackInitialCondition: InitConfig,
    fallbackMetrics: SimulationMetrics,
    sweep: [String: Double]? = nil,
    score: Float? = nil,
    scoreWeights: [String: Float]? = nil,
    fallbackInitialConditionFamily: String? = nil,
    fallbackDescriptorBundle: MorphospaceDescriptorBundle? = nil,
    fallbackConfigHash: String? = nil
) -> SavedCreature {
    resolveSpecimenProjection(
        id: id,
        name: name,
        ownerId: ownerId,
        manifest: manifest,
        fallbackGenotype: fallbackGenotype,
        fallbackInitialCondition: fallbackInitialCondition,
        fallbackMetrics: fallbackMetrics,
        sweep: sweep,
        score: score,
        scoreWeights: scoreWeights,
        fallbackInitialConditionFamily: fallbackInitialConditionFamily,
        fallbackDescriptorBundle: fallbackDescriptorBundle,
        fallbackConfigHash: fallbackConfigHash
    ).creature
}

public func resolveSpecimenProjection(
    id: UUID,
    name: String,
    ownerId: String,
    manifest: SpecimenManifest?,
    fallbackGenotype: KernelParams,
    fallbackInitialCondition: InitConfig,
    fallbackMetrics: SimulationMetrics,
    sweep: [String: Double]? = nil,
    score: Float? = nil,
    scoreWeights: [String: Float]? = nil,
    fallbackInitialConditionFamily: String? = nil,
    fallbackDescriptorBundle: MorphospaceDescriptorBundle? = nil,
    fallbackConfigHash: String? = nil,
    fallbackRuntimeFamily: String? = nil,
    fallbackRuntimeCapabilities: [String]? = nil,
    fallbackSourceMode: String? = nil,
    fallbackSourceAlgorithm: String? = nil,
    fallbackResearchMetadata: [String: AnyCodable]? = nil,
    fallbackTraitLabels: [String]? = nil
) -> ResolvedSpecimenProjection {
    let snapshots = manifest?.snapshots
    let genotype = snapshots?.genotype ?? fallbackGenotype
    let initialCondition = snapshots?.initialCondition ?? fallbackInitialCondition
    let metrics = snapshots?.metrics ?? fallbackMetrics
    return ResolvedSpecimenProjection(
        manifest: manifest,
        creature: SavedCreature(
            id: id,
            name: name,
            ownerId: ownerId,
            genotype: genotype,
            initialCondition: initialCondition,
            initialConditionFamily: manifest?.initialConditionFamily ?? fallbackInitialConditionFamily,
            descriptorBundle: snapshots?.descriptorBundle ?? fallbackDescriptorBundle,
            metrics: metrics,
            sweep: sweep,
            score: score ?? metrics.massMean,
            scoreWeights: scoreWeights,
            configHash: manifest?.configHash ?? fallbackConfigHash
        ),
        runtimeFamily: manifest?.runtimeFamily ?? fallbackRuntimeFamily,
        runtimeCapabilities: manifest?.runtimeCapabilities ?? fallbackRuntimeCapabilities ?? [],
        sourceMode: manifest?.sourceMode ?? fallbackSourceMode,
        sourceAlgorithm: manifest?.sourceAlgorithm ?? fallbackSourceAlgorithm,
        researchMetadata: manifest?.researchMetadata ?? fallbackResearchMetadata,
        traitLabels: manifest?.traitLabels ?? fallbackTraitLabels ?? []
    )
}

private func researchMetadataBool(_ key: String, in researchMetadata: [String: AnyCodable]?) -> Bool {
    if let value = researchMetadata?[key]?.value as? Bool {
        return value
    }
    if let nested = researchMetadata?["source_research_metadata"]?.value as? [String: Any],
       let value = nested[key] as? Bool {
        return value
    }
    return false
}

private func normalizedSpecimenText(_ value: String?) -> String? {
    guard let value else {
        return nil
    }
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else {
        return nil
    }
    return trimmed.lowercased()
}

public func normalizedSpecimenSourceMode(_ value: String?) -> String? {
    guard let normalized = normalizedSpecimenText(value) else {
        return nil
    }
    if normalized == "replay-specimens" {
        return "replay"
    }
    return normalized
}
