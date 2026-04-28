import ArgumentParser
import Foundation
import LeniaCore
import Logging

enum ReplayInputKind: String, Codable {
    case exportIndex = "export_index"
    case libraryIndex = "library_index"
    case canonicalization = "canonicalization"
}

enum ReplayExecutionPlan {
    case flow(baseConfig: LeniaBaseConfig, searchConfig: ParsedSearchConfig)
    case qd24(payload: LeniaBreeder2024ReplayPayload)
    case sensorimotor24(payload: SensorimotorLenia2024ReplayPayload)
}

extension ReplayExecutionPlan {
    var isFlow: Bool {
        switch self {
        case .flow:
            return true
        case .qd24, .sensorimotor24:
            return false
        }
    }
}

struct ReplayResolvedInput {
    let inputKind: ReplayInputKind
    let inputPath: URL
    let sourceRunId: String
    let sourceCampaignId: String?
    let sourceMode: String?
    let sourceAlgorithm: String?
    let projection: ResolvedSpecimenProjection
    let executionPlan: ReplayExecutionPlan
    let sourceScore: Float?
    let sourceFiltersPassed: Bool?
    let sourceExportDir: String?
    let sourceReason: String?

    var sourceResearchMetadata: [String: AnyCodable]? {
        projection.researchMetadata
    }

    var sourceCreature: SavedCreature {
        projection.creature
    }
}

struct ReplaySpecimenManifest: Codable {
    let inputKind: String
    let inputPath: String
    let sourceRunId: String
    let sourceCampaignId: String?
    let sourceCreatureId: String
    let sourceExportDir: String?
    let sourceReason: String?
    let replayRunId: String
    let campaignId: String
    let configHash: String
    let configPath: String?
    let searchPath: String?
    let resultsPath: String
    let libraryPath: String
    let activityPath: String?
    let exportIndexPath: String?
    let replayedAt: Date
}

struct ReplayBatchSummary: Codable {
    let runId: String
    let inputPath: String
    let outputDir: String
    let specimenCount: Int
    let exportCount: Int
    let replayedAt: Date
}

struct ReplayExecutionOutcome {
    let configHash: String
    let baseConfig: LeniaBaseConfig?
    let searchConfig: ParsedSearchConfig?
    let resultData: SimulationResultData
    let replayCreature: SavedCreature
    let activityRecord: ActivitySummaryRecord?
}

private func replaySourceCreatureID(
    manifest: SpecimenManifest?,
    fallback: UUID
) -> UUID {
    guard let raw = manifest?.creatureID ?? manifest?.specimenID,
          let id = UUID(uuidString: raw) else {
        return fallback
    }
    return id
}

private func replayLibraryProjection(_ entry: ResearchLibraryEntry) -> ResolvedSpecimenProjection {
    resolveSpecimenProjection(
        id: replaySourceCreatureID(manifest: entry.specimenManifest, fallback: entry.creature.id),
        name: entry.creature.name,
        ownerId: entry.creature.ownerId,
        manifest: entry.specimenManifest,
        fallbackGenotype: entry.creature.genotype,
        fallbackInitialCondition: entry.creature.initialCondition,
        fallbackMetrics: entry.creature.metrics,
        sweep: entry.creature.sweep,
        score: entry.creature.score,
        scoreWeights: entry.creature.scoreWeights,
        fallbackInitialConditionFamily: entry.creature.initialConditionFamily,
        fallbackDescriptorBundle: entry.creature.descriptorBundle,
        fallbackConfigHash: entry.configHash,
        fallbackRuntimeFamily: entry.runtimeFamily,
        fallbackRuntimeCapabilities: entry.runtimeCapabilities,
        fallbackSourceMode: entry.sourceMode,
        fallbackSourceAlgorithm: entry.sourceAlgorithm,
        fallbackResearchMetadata: entry.researchMetadata
    )
}

private func replayExportProjection(
    record: CreatureExportRecord,
    metadata: CreatureExportMetadata?,
    fallbackCreature: SavedCreature?,
    fallbackMode: String?,
    fallbackAlgorithm: String?,
    fallbackResearchMetadata: [String: AnyCodable]?
) throws -> ResolvedSpecimenProjection {
    guard let creature = metadata?.creature ?? fallbackCreature else {
        let metaURL = URL(fileURLWithPath: record.exportDir, isDirectory: true).appendingPathComponent("meta.json")
        throw ValidationError("Missing export meta.json for replay bundle: \(metaURL.path)")
    }
    let manifest = metadata?.specimenManifest ?? record.specimenManifest
    return resolveSpecimenProjection(
        id: replaySourceCreatureID(manifest: manifest, fallback: record.creatureId),
        name: creature.name,
        ownerId: creature.ownerId,
        manifest: manifest,
        fallbackGenotype: creature.genotype,
        fallbackInitialCondition: creature.initialCondition,
        fallbackMetrics: creature.metrics,
        sweep: creature.sweep,
        score: metadata?.score ?? record.score ?? creature.score,
        scoreWeights: creature.scoreWeights,
        fallbackInitialConditionFamily: creature.initialConditionFamily,
        fallbackDescriptorBundle: creature.descriptorBundle,
        fallbackConfigHash: creature.configHash,
        fallbackRuntimeFamily: metadata?.runtimeFamily ?? record.runtimeFamily,
        fallbackRuntimeCapabilities: metadata?.runtimeCapabilities ?? record.runtimeCapabilities,
        fallbackSourceMode: fallbackMode,
        fallbackSourceAlgorithm: fallbackAlgorithm,
        fallbackResearchMetadata: metadata?.specimenManifest.researchMetadata ?? fallbackResearchMetadata
    )
}

func executeReplayResolvedInput(
    _ resolvedInput: ReplayResolvedInput,
    runID: String
) throws -> ReplayExecutionOutcome {
    switch resolvedInput.executionPlan {
    case let .flow(baseConfig, searchConfig):
        let sourceReplayBaseConfig: LeniaBaseConfig
        let replaySearchConfig: ParsedSearchConfig
        switch resolvedInput.inputKind {
        case .exportIndex, .canonicalization:
            sourceReplayBaseConfig = baseConfig
            replaySearchConfig = searchConfig
        case .libraryIndex:
            sourceReplayBaseConfig = try buildReplayBaseConfig(
                baseConfig: baseConfig,
                searchConfig: searchConfig,
                creature: resolvedInput.sourceCreature
            )
            replaySearchConfig = buildReplaySearchConfig(
                from: searchConfig,
                initSeedOffset: resolvedInput.sourceCreature.initialCondition.seed,
                enableMorphospaceSignals: true,
                supportsActivity: replaySupportsReplayActivity(baseConfig: sourceReplayBaseConfig)
            )
        }
        let resolvedBackend = try resolveReplaySearchBackend(baseConfig: sourceReplayBaseConfig)
        let replayBaseConfig = baseConfigBySettingBackend(sourceReplayBaseConfig, backend: resolvedBackend)

        let configHash = try researchConfigHash([
            ("base", researchEncodedJSON(replayBaseConfig)),
            ("search", researchEncodedJSON(replaySearchConfig)),
        ])
        let runtimeConfig = try loadRuntimeConfig(from: researchEncodedJSON(replayBaseConfig))
        let engine = SearchEngine(runtimeConfig: runtimeConfig)
        let batchResult = try unwrapReplayValue(
            engine.runBatch(
                seeds: [replaySearchConfig.seedStart],
                initSeedOffset: replaySearchConfig.initSeedOffset ?? 0,
                searchConfig: replaySearchConfig.toSearchConfig()
            ).first,
            message: "Replay batch produced no result for \(resolvedInput.sourceCreature.name)."
        )
        let resultData = materializeReplayResultData(
            batchResult,
            backend: replayBaseConfig.backend,
            implementation: runtimeConfig.implementation,
            scoreWeights: replaySearchConfig.scoreWeights,
            filters: replaySearchConfig.filters,
            sweep: [:]
        )
        let replayCreature = archivedCreatureFromResult(
            stableKey: "\(runID)|\(resolvedInput.sourceCreature.id.uuidString)",
            name: resolvedInput.sourceCreature.name,
            ownerId: resolvedInput.sourceCreature.ownerId,
            result: resultData,
            initialCondition: resolvedInput.sourceCreature.initialCondition,
            configHash: configHash,
            score: resolvedInput.sourceCreature.score,
            scoreWeights: resolvedInput.sourceCreature.scoreWeights
        )
        let activityRecord = activitySummaryRecord(for: resultData, config: replaySearchConfig.activity)
        return ReplayExecutionOutcome(
            configHash: configHash,
            baseConfig: replayBaseConfig,
            searchConfig: replaySearchConfig,
            resultData: resultData,
            replayCreature: replayCreature,
            activityRecord: activityRecord
        )
    case let .qd24(payload):
        let configHash = try researchConfigHash([
            ("qd24-replay", researchEncodedJSON(payload)),
        ])
        let outcome = try replayLeniaBreeder2024Payload(
            payload,
            runId: runID,
            configHash: configHash
        )
        return ReplayExecutionOutcome(
            configHash: configHash,
            baseConfig: nil,
            searchConfig: nil,
            resultData: normalizedPersistedResultData(outcome.resultData),
            replayCreature: normalizedPersistedCreature(outcome.creature),
            activityRecord: nil
        )
    case let .sensorimotor24(payload):
        let configHash = try researchConfigHash([
            ("sensorimotor24-replay", researchEncodedJSON(payload)),
        ])
        let outcome = try replaySensorimotorLenia2024Payload(
            payload,
            runId: runID,
            configHash: configHash
        )
        return ReplayExecutionOutcome(
            configHash: configHash,
            baseConfig: nil,
            searchConfig: nil,
            resultData: normalizedPersistedResultData(outcome.resultData),
            replayCreature: normalizedPersistedCreature(outcome.creature),
            activityRecord: nil
        )
    }
}

func materializeReplayBatch(
    inputs: [ReplayResolvedInput],
    inputPath: String,
    outputURL: URL,
    runID: String,
    exportEnabled: Bool,
    logger: Logger
) throws -> ReplayBatchSummary {
    guard !inputs.isEmpty else {
        throw ValidationError("No replayable specimens found in \(inputPath).")
    }
    if FileManager.default.fileExists(atPath: outputURL.path) {
        let existing = try FileManager.default.contentsOfDirectory(
            at: outputURL,
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        )
        let userVisibleEntries = existing.filter { $0.lastPathComponent != "logs" }
        if !userVisibleEntries.isEmpty {
            throw ValidationError("Replay output directory is not empty: \(outputURL.path)")
        }
    }

    logger.info("Resolved \(inputs.count) replay inputs from \(inputPath)")

    try FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)
    let campaignsDir = outputURL.appendingPathComponent("campaigns", isDirectory: true)
    try FileManager.default.createDirectory(at: campaignsDir, withIntermediateDirectories: true)

    let replayedAt = Date()
    var exportCount = 0
    var manifests: [ReplaySpecimenManifest] = []
    manifests.reserveCapacity(inputs.count)

    for (index, resolvedInput) in inputs.enumerated() {
        let campaignId = replayCampaignID(index: index, creature: resolvedInput.sourceCreature)
        let campaignDir = campaignsDir.appendingPathComponent(campaignId, isDirectory: true)
        try FileManager.default.createDirectory(at: campaignDir, withIntermediateDirectories: true)
        let execution = try executeReplayResolvedInput(resolvedInput, runID: runID)
        let configHash = execution.configHash
        let replayCreature = execution.replayCreature
        let resultData = execution.resultData
        let libraryEntry = archiveResearchLibraryEntry(
            creature: replayCreature,
            runId: runID,
            configHash: configHash,
            sourceMode: "replay",
            sourceAlgorithm: resolvedInput.executionPlan.isFlow ? "canonical-replay" : "paper-replay",
            researchMetadata: try replayResearchMetadata(
                resolvedInput: resolvedInput,
                configHash: configHash
            ),
            recordedAt: replayedAt,
            campaignId: campaignId
        )
        let persistedArtifacts: PersistedResearchRunArtifacts
        if exportEnabled {
            switch resolvedInput.executionPlan {
            case .flow:
                guard let replayBaseConfig = execution.baseConfig,
                      let replaySearchConfig = execution.searchConfig else {
                    throw ValidationError("Replay execution did not preserve flow config for \(resolvedInput.sourceCreature.name).")
                }
                persistedArtifacts = try persistResearchRunArtifacts(
                    directory: campaignDir,
                    baseConfig: execution.baseConfig,
                    searchConfig: execution.searchConfig,
                    resultData: resultData,
                    activityRecord: execution.activityRecord,
                    libraryEntries: [libraryEntry],
                    exportRoot: campaignDir.appendingPathComponent("exports", isDirectory: true),
                    exportItems: [replayCreature],
                    emptyExportMessage: "Replay export bundle already exists for \(replayCreature.name)."
                ) { creature in
                    (
                        baseConfig: replayBaseConfig,
                        searchConfig: replaySearchConfig,
                        creature: creature,
                        runId: runID,
                        campaignId: nil,
                        score: creature.score,
                        filtersPassed: resolvedInput.sourceFiltersPassed,
                        reason: "replay"
                    )
                }
            case .qd24, .sensorimotor24:
                throw ValidationError("replay --export is only supported for strict Flow Lenia replay bundles.")
            }
        } else {
            persistedArtifacts = try persistResearchRunArtifacts(
                directory: campaignDir,
                baseConfig: execution.baseConfig,
                searchConfig: execution.searchConfig,
                resultData: resultData,
                activityRecord: execution.activityRecord,
                libraryEntries: [libraryEntry]
            )
        }
        let executionArtifacts = persistedArtifacts.execution
        let archiveArtifacts = persistedArtifacts.archive
        exportCount += archiveArtifacts.exportCount

        let manifest = ReplaySpecimenManifest(
            inputKind: resolvedInput.inputKind.rawValue,
            inputPath: resolvedInput.inputPath.path,
            sourceRunId: resolvedInput.sourceRunId,
            sourceCampaignId: resolvedInput.sourceCampaignId,
            sourceCreatureId: resolvedInput.sourceCreature.id.uuidString,
            sourceExportDir: resolvedInput.sourceExportDir,
            sourceReason: resolvedInput.sourceReason,
            replayRunId: runID,
            campaignId: campaignId,
            configHash: configHash,
            configPath: executionArtifacts.configURL?.path,
            searchPath: executionArtifacts.searchURL?.path,
            resultsPath: executionArtifacts.resultsURL.path,
            libraryPath: archiveArtifacts.libraryURL.path,
            activityPath: executionArtifacts.activityURL?.path,
            exportIndexPath: archiveArtifacts.exportIndexURL?.path,
            replayedAt: replayedAt
        )
        try replayEncoder().encode(manifest).write(to: campaignDir.appendingPathComponent("replay-manifest.json"))
        manifests.append(manifest)
    }

    let summary = ReplayBatchSummary(
        runId: runID,
        inputPath: inputPath,
        outputDir: outputURL.path,
        specimenCount: manifests.count,
        exportCount: exportCount,
        replayedAt: replayedAt
    )
    try replayEncoder().encode(summary).write(to: outputURL.appendingPathComponent("summary.json"))
    logger.info("Replay completed (specimens=\(manifests.count), exports=\(exportCount), output=\(outputURL.path))")
    return summary
}

func loadReplayResolvedInputs(from inputURL: URL) throws -> [ReplayResolvedInput] {
    let lines = try replayReadJSONLines(inputURL)
    guard let first = lines.first else {
        return []
    }
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .deferredToDate

    if let firstData = first.data(using: .utf8),
       (try? decoder.decode(CreatureExportRecord.self, from: firstData)) != nil {
        return try lines.map { line in
            guard let data = line.data(using: .utf8) else {
                throw ValidationError("Invalid UTF-8 line in \(inputURL.path)")
            }
            let record = try decoder.decode(CreatureExportRecord.self, from: data)
            return try replayResolvedInput(from: record)
        }
    }

    if let firstData = first.data(using: .utf8),
       (try? decodeResearchLibraryEntry(firstData, decoder: decoder)) != nil {
        let runDir = inputURL.deletingLastPathComponent().deletingLastPathComponent()
        let baseURL = runDir.appendingPathComponent("config.json")
        let searchURL = runDir.appendingPathComponent("search.json")
        guard FileManager.default.fileExists(atPath: baseURL.path) else {
            throw ValidationError("Missing config.json next to library input: \(baseURL.path)")
        }
        guard FileManager.default.fileExists(atPath: searchURL.path) else {
            throw ValidationError("Missing search.json next to library input: \(searchURL.path)")
        }
        let baseConfig = try decoder.decode(LeniaBaseConfig.self, from: Data(contentsOf: baseURL))
        let searchConfig = try decoder.decode(ParsedSearchConfig.self, from: Data(contentsOf: searchURL))

        return try lines.map { line in
            guard let data = line.data(using: .utf8) else {
                throw ValidationError("Invalid UTF-8 line in \(inputURL.path)")
            }
            let entry = try decodeResearchLibraryEntry(data, decoder: decoder)
            try validateReplayLibraryEntry(entry)
            let projection = replayLibraryProjection(entry)
            return ReplayResolvedInput(
                inputKind: .libraryIndex,
                inputPath: inputURL,
                sourceRunId: projection.manifest?.runID ?? entry.runId,
                sourceCampaignId: projection.manifest?.campaignID ?? entry.campaignId,
                sourceMode: projection.sourceMode,
                sourceAlgorithm: projection.sourceAlgorithm,
                projection: projection,
                executionPlan: .flow(baseConfig: baseConfig, searchConfig: searchConfig),
                sourceScore: projection.creature.score,
                sourceFiltersPassed: nil,
                sourceExportDir: projection.manifest?.replay?.exportDir,
                sourceReason: nil
            )
        }
    }

    throw ValidationError("Unsupported replay input format: \(inputURL.path)")
}

func replayResolvedInput(
    from record: CreatureExportRecord,
    fallbackCreature: SavedCreature? = nil,
    fallbackMode: String? = nil,
    fallbackAlgorithm: String? = nil,
    fallbackResearchMetadata: [String: AnyCodable]? = nil,
    fallbackReason: String? = nil
) throws -> ReplayResolvedInput {
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .deferredToDate
    let metaURL = URL(fileURLWithPath: record.exportDir, isDirectory: true).appendingPathComponent("meta.json")
    let metadata: CreatureExportMetadata?
    if FileManager.default.fileExists(atPath: metaURL.path) {
        metadata = try decodeCreatureExportMetadata(
            Data(contentsOf: metaURL),
            decoder: decoder,
            fallbackBundleKind: record.bundleKind
        )
    } else {
        metadata = nil
    }
    let projection = try replayExportProjection(
        record: record,
        metadata: metadata,
        fallbackCreature: fallbackCreature,
        fallbackMode: fallbackMode,
        fallbackAlgorithm: fallbackAlgorithm,
        fallbackResearchMetadata: fallbackResearchMetadata
    )
    let executionPlan: ReplayExecutionPlan
    let sourceMode: String?
    let sourceAlgorithm: String?
    switch record.bundleKind {
    case .strictReplayBundleV1:
        guard let baseConfigPath = record.baseConfigPath,
              let searchConfigPath = record.searchConfigPath else {
            throw ValidationError("Strict replay export bundle is missing base/search config paths: \(record.exportDir)")
        }
        let baseConfig = try decoder.decode(
            LeniaBaseConfig.self,
            from: Data(contentsOf: URL(fileURLWithPath: baseConfigPath))
        )
        let searchConfig = try decoder.decode(
            ParsedSearchConfig.self,
            from: Data(contentsOf: URL(fileURLWithPath: searchConfigPath))
        )
        executionPlan = .flow(baseConfig: baseConfig, searchConfig: searchConfig)
        sourceMode = projection.sourceMode ?? fallbackMode ?? metadata?.creature.ownerId
        sourceAlgorithm = projection.sourceAlgorithm ?? fallbackAlgorithm
    case .qd24PaperReplayBundleV1:
        guard let payloadPath = record.payloadPath else {
            throw ValidationError("qd-2024 replay bundle is missing payload path: \(record.exportDir)")
        }
        let payload = try decoder.decode(
            LeniaBreeder2024ReplayPayload.self,
            from: Data(contentsOf: URL(fileURLWithPath: payloadPath))
        )
        executionPlan = .qd24(payload: payload)
        sourceMode = projection.sourceMode ?? fallbackMode ?? "qd-2024"
        sourceAlgorithm = projection.sourceAlgorithm ?? fallbackAlgorithm ?? payload.algorithm
    case .sensorimotor24PaperReplayBundleV1:
        guard let payloadPath = record.payloadPath else {
            throw ValidationError("sensorimotor-2024 replay bundle is missing payload path: \(record.exportDir)")
        }
        let payload = try decoder.decode(
            SensorimotorLenia2024ReplayPayload.self,
            from: Data(contentsOf: URL(fileURLWithPath: payloadPath))
        )
        executionPlan = .sensorimotor24(payload: payload)
        sourceMode = projection.sourceMode ?? fallbackMode ?? "sensorimotor-2024"
        sourceAlgorithm = projection.sourceAlgorithm ?? fallbackAlgorithm ?? "imgep"
    case .flowLeniaEcology2025ArenaReplayBundleV1:
        throw ValidationError("Flow Lenia ecology arena bundles are rendered as trajectories, not materialized as specimen replay bundles: \(record.exportDir)")
    }
    return ReplayResolvedInput(
        inputKind: .exportIndex,
        inputPath: metaURL.deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("index.jsonl"),
        sourceRunId: projection.manifest?.runID ?? metadata?.runId ?? record.runId,
        sourceCampaignId: projection.manifest?.campaignID ?? metadata?.campaignId ?? record.campaignId,
        sourceMode: sourceMode,
        sourceAlgorithm: sourceAlgorithm,
        projection: projection,
        executionPlan: executionPlan,
        sourceScore: metadata?.score ?? record.score,
        sourceFiltersPassed: metadata?.filtersPassed ?? record.filtersPassed,
        sourceExportDir: projection.manifest?.replay?.exportDir ?? record.exportDir,
        sourceReason: metadata?.reason ?? fallbackReason ?? record.reason
    )
}

func validateReplayLibraryEntry(_ entry: ResearchLibraryEntry) throws {
    let payload = entry.researchMetadata?["morphospace_payload"]?.value as? String
    let ready = entry.researchMetadata?["morphospace_ready"]?.value as? Bool
    if payload == "summary_only_metrics_v1" || ready == false {
        throw ValidationError("Library input contains summary-only row '\(entry.creature.name)'; replay from exports or add a dedicated adapter instead.")
    }
}

func replaySupportsReplayActivity(baseConfig: LeniaBaseConfig) -> Bool {
    baseConfig.parameter_embedding.enabled &&
        (baseConfig.`init`.p_uniform != nil || baseConfig.`init`.p_state_patch != nil)
}

func replayCampaignID(index: Int, creature: SavedCreature) -> String {
    let ordinal = String(format: "%04d", index + 1)
    return "\(ordinal)-\(replayPathComponent(creature.name))-\(String(creature.id.uuidString.prefix(8)).lowercased())"
}

private func replayPathComponent(_ value: String) -> String {
    let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_"))
    let mapped = value.lowercased().unicodeScalars.map { allowed.contains($0) ? Character($0) : "-" }
    let raw = String(mapped)
    let collapsed = raw.replacingOccurrences(of: "-+", with: "-", options: .regularExpression)
    let trimmed = collapsed.trimmingCharacters(in: CharacterSet(charactersIn: "-"))
    return trimmed.isEmpty ? "specimen" : trimmed
}

func replayResearchMetadata(
    resolvedInput: ReplayResolvedInput,
    configHash: String
) throws -> [String: AnyCodable] {
    var metadata: [String: AnyCodable] = try [
        "version": researchMetadataValue(1),
        "mode": researchMetadataValue("replay"),
        "source_kind": researchMetadataValue(resolvedInput.inputKind.rawValue),
        "source_input_path": researchMetadataValue(resolvedInput.inputPath.path),
        "source_run_id": researchMetadataValue(resolvedInput.sourceRunId),
        "source_creature_id": researchMetadataValue(resolvedInput.sourceCreature.id.uuidString),
        "replay_config_hash": researchMetadataValue(configHash),
    ]
    if let sourceCampaignId = resolvedInput.sourceCampaignId {
        metadata["source_campaign_id"] = try researchMetadataValue(sourceCampaignId)
    }
    if let sourceMode = resolvedInput.sourceMode {
        metadata["source_mode"] = try researchMetadataValue(sourceMode)
    }
    if let sourceAlgorithm = resolvedInput.sourceAlgorithm {
        metadata["source_algorithm"] = try researchMetadataValue(sourceAlgorithm)
    }
    if let sourceScore = resolvedInput.sourceScore {
        metadata["source_score"] = try researchMetadataValue(sourceScore)
    }
    if let sourceFiltersPassed = resolvedInput.sourceFiltersPassed {
        metadata["source_filters_passed"] = try researchMetadataValue(sourceFiltersPassed)
    }
    if let sourceExportDir = resolvedInput.sourceExportDir {
        metadata["source_export_dir"] = try researchMetadataValue(sourceExportDir)
    }
    if let sourceReason = resolvedInput.sourceReason {
        metadata["source_reason"] = try researchMetadataValue(sourceReason)
    }
    if let sourceResearchMetadata = resolvedInput.sourceResearchMetadata {
        metadata["source_research_metadata"] = try researchMetadataValue(sourceResearchMetadata)
    }
    return metadata
}

func replayEncoder() -> JSONEncoder {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    encoder.dateEncodingStrategy = .deferredToDate
    return encoder
}

func replayReadJSONLines(_ url: URL) throws -> [String] {
    try String(contentsOf: url, encoding: .utf8)
        .split(whereSeparator: \.isNewline)
        .map(String.init)
        .filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
}

func unwrapReplayValue<T>(_ value: T?, message: String) throws -> T {
    if let value {
        return value
    }
    throw ValidationError(message)
}
