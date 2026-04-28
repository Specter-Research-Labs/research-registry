import ArgumentParser
import Foundation
import LeniaCore
import Logging

private struct HolonomyLoopSpec: Codable {
    let version: Int
    let name: String?
    let closed: Bool
    let coordinates: [String]
    let vertices: [[Float]]
    let samplesPerSegment: Int

    enum CodingKeys: String, CodingKey {
        case version
        case name
        case closed
        case coordinates
        case vertices
        case samplesPerSegment = "samples_per_segment"
    }
}

private struct HolonomyLoopPoint {
    let sequenceIndex: Int
    let segmentIndex: Int
    let segmentT: Float
    let values: [Float]
}

private struct HolonomyBundle {
    let exportDir: URL
    let baseConfig: LeniaBaseConfig
    let searchConfig: ParsedSearchConfig
    let metadata: CreatureExportMetadata
}

private struct HolonomyStepManifest: Codable {
    let sequenceIndex: Int
    let segmentIndex: Int
    let segmentT: Float
    let coordinateValues: [String: Float]
    let configHash: String
    let configTopologyHash: String
    let configPath: String
    let searchPath: String
    let resultsPath: String
    let libraryPath: String
    let activityPath: String?
    let exportIndexPath: String?
    let replayedAt: Date

    enum CodingKeys: String, CodingKey {
        case sequenceIndex = "sequence_index"
        case segmentIndex = "segment_index"
        case segmentT = "segment_t"
        case coordinateValues = "coordinate_values"
        case configHash = "config_hash"
        case configTopologyHash = "config_topology_hash"
        case configPath = "config_path"
        case searchPath = "search_path"
        case resultsPath = "results_path"
        case libraryPath = "library_path"
        case activityPath = "activity_path"
        case exportIndexPath = "export_index_path"
        case replayedAt = "replayed_at"
    }
}

private struct HolonomySummary: Codable {
    let runId: String
    let bundlePath: String
    let loopPath: String
    let loopName: String?
    let loopClosed: Bool
    let coordinatePaths: [String]
    let pointCount: Int
    let campaignCount: Int
    let configTopologyHash: String
    let phenotypeClosureDistance: Float?
    let transportedStateClosureDistance: Float?
    let replayedAt: Date
    let outputDir: String
    let exportCount: Int

    enum CodingKeys: String, CodingKey {
        case runId = "run_id"
        case bundlePath = "bundle_path"
        case loopPath = "loop_path"
        case loopName = "loop_name"
        case loopClosed = "loop_closed"
        case coordinatePaths = "coordinate_paths"
        case pointCount = "point_count"
        case campaignCount = "campaign_count"
        case configTopologyHash = "config_topology_hash"
        case phenotypeClosureDistance = "phenotype_closure_distance"
        case transportedStateClosureDistance = "transported_state_closure_distance"
        case replayedAt = "replayed_at"
        case outputDir = "output_dir"
        case exportCount = "export_count"
    }
}

private struct HolonomyRunManifest: Codable {
    let version: Int
    let runId: String
    let bundlePath: String
    let loopPath: String
    let loopName: String?
    let loopClosed: Bool
    let coordinatePaths: [String]
    let configTopologyHash: String
    let campaignsDir: String
    let summaryPath: String
    let stepManifestPaths: [String]
    let campaignDirs: [String]
    let exportEnabled: Bool
    let replayedAt: Date

    enum CodingKeys: String, CodingKey {
        case version
        case runId = "run_id"
        case bundlePath = "bundle_path"
        case loopPath = "loop_path"
        case loopName = "loop_name"
        case loopClosed = "loop_closed"
        case coordinatePaths = "coordinate_paths"
        case configTopologyHash = "config_topology_hash"
        case campaignsDir = "campaigns_dir"
        case summaryPath = "summary_path"
        case stepManifestPaths = "step_manifest_paths"
        case campaignDirs = "campaign_dirs"
        case exportEnabled = "export_enabled"
        case replayedAt = "replayed_at"
    }
}

struct HolonomyCommand: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "holonomy",
        abstract: "Transport a strict Flow Lenia replay bundle around a parameter loop and record closure"
    )

    @Option(name: .long, help: "Path to a strict Flow Lenia replay bundle directory containing base.json/search.json/meta.json")
    var bundle: String

    @Option(name: .long, help: "Path to a holonomy loop JSON spec")
    var loop: String

    @Option(name: .shortAndLong, help: "Holonomy batch output directory")
    var output: String?

    @Flag(name: .long, help: "Write replay export bundles for each holonomy step")
    var exportEnabled: Bool = false

    @OptionGroup
    var promotion: ArchivePromotionOptions

    @Flag(name: .long, help: "Validate the bundle and loop without running")
    var validateOnly: Bool = false

    @OptionGroup
    var logOptions: LogOptions

    func run() async throws {
        let resolvedRunId = resolveRunID(prefix: "holonomy", logOptions: logOptions)
        let resolvedOutput = try resolveArtifactRunOutput(
            explicitOutput: output,
            defaultSubpath: "outputs/holonomy",
            runID: resolvedRunId,
            dossier: dossierName
        )
        let outputURL = URL(fileURLWithPath: resolvedOutput, isDirectory: true)
        if FileManager.default.fileExists(atPath: outputURL.path) {
            let existing = try FileManager.default.contentsOfDirectory(
                at: outputURL,
                includingPropertiesForKeys: nil,
                options: [.skipsHiddenFiles]
            )
            if !existing.isEmpty {
                throw ValidationError("Holonomy output directory is not empty: \(outputURL.path)")
            }
        }

        let logging = try bootstrapRunLogging(
            runID: resolvedRunId,
            role: "holonomy",
            loggerLabel: "LeniaSwarm.Holonomy",
            logStem: "holonomy",
            outputForLogs: resolvedOutput,
            logOptions: logOptions,
            dossier: dossierName
        )
        let logger = logging.logger

        let bundleURL = URL(fileURLWithPath: try resolveArtifactPath(bundle, dossier: dossierName), isDirectory: true)
        let loopURL = URL(fileURLWithPath: try resolvePath(loop, dossier: dossierName))
        let holonomyBundle = try loadHolonomyBundle(from: bundleURL)
        let loopSpec = try loadHolonomyLoopSpec(from: loopURL)
        let loopPoints = try buildHolonomyLoopPoints(loopSpec)
        _ = try validateHolonomyParams(
            baseParams: holonomyBundle.baseConfig.params,
            coordinates: loopSpec.coordinates,
            vertices: loopSpec.vertices
        )
        let topologyHash = configTopologyHash(holonomyBundle.baseConfig)

        logger.info("Resolved holonomy loop with \(loopPoints.count) transport steps from \(bundleURL.path)")
        if validateOnly {
            logger.info("Holonomy bundle and loop validated successfully")
            return
        }

        try FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)
        try Data(contentsOf: loopURL).write(to: outputURL.appendingPathComponent("loop-spec.json"))
        let campaignsDir = outputURL.appendingPathComponent("campaigns", isDirectory: true)
        try FileManager.default.createDirectory(at: campaignsDir, withIntermediateDirectories: true)

        var transportInit = holonomyBundle.baseConfig.`init`
        let replayedAt = Date()
        var manifests: [HolonomyStepManifest] = []
        var stepManifestPaths: [String] = []
        var campaignDirs: [String] = []
        var exportCount = 0
        var firstFingerprint: [UInt8]?
        var lastFingerprint: [UInt8]?
        var firstStatePatch: InitStatePatchConfig?
        var lastStatePatch: InitStatePatchConfig?

        for point in loopPoints {
            let pointParams = try applyHolonomyCoordinateValues(
                values: point.values,
                coordinates: loopSpec.coordinates,
                to: holonomyBundle.baseConfig.params
            )
            let pointBaseConfig = makeHolonomyBaseConfig(
                baseConfig: holonomyBundle.baseConfig,
                params: pointParams,
                initConfig: transportInit
            )
            let pointTopologyHash = configTopologyHash(pointBaseConfig)
            guard pointTopologyHash == topologyHash else {
                throw ValidationError(
                    "Holonomy point \(point.sequenceIndex) changed config topology hash from \(topologyHash) to \(pointTopologyHash)."
                )
            }

            let pointSearchConfig = buildReplaySearchConfig(
                from: holonomyBundle.searchConfig,
                initSeedOffset: transportInit.seed,
                enableMorphospaceSignals: true,
                supportsActivity: holonomySupportsActivity(baseConfig: pointBaseConfig)
            )
            let configHash = try researchConfigHash([
                ("base", researchEncodedJSON(pointBaseConfig)),
                ("search", researchEncodedJSON(pointSearchConfig)),
            ])

            let campaignID = holonomyCampaignID(point.sequenceIndex)
            let campaignDir = campaignsDir.appendingPathComponent(campaignID, isDirectory: true)
            try FileManager.default.createDirectory(at: campaignDir, withIntermediateDirectories: true)

            let runtimeConfig = try loadRuntimeConfig(from: researchEncodedJSON(pointBaseConfig))
            let engine = SearchEngine(runtimeConfig: runtimeConfig)
            guard let batchResult = engine.runBatch(
                seeds: [pointSearchConfig.seedStart],
                initSeedOffset: pointSearchConfig.initSeedOffset ?? 0,
                searchConfig: pointSearchConfig.toSearchConfig(captureTerminalPatches: true)
            ).first else {
                throw ValidationError("Holonomy point \(point.sequenceIndex) produced no result.")
            }

            let resultData = materializeReplayResultData(
                batchResult,
                backend: pointBaseConfig.backend,
                implementation: runtimeConfig.implementation,
                scoreWeights: pointSearchConfig.scoreWeights,
                filters: pointSearchConfig.filters,
                sweep: [:]
            )
            let creature = archivedCreatureFromResult(
                stableKey: "\(resolvedRunId)|\(point.sequenceIndex)|\(holonomyBundle.metadata.creature.id.uuidString)",
                name: "\(holonomyBundle.metadata.creature.name)-holonomy-\(String(format: "%03d", point.sequenceIndex))",
                ownerId: holonomyBundle.metadata.creature.ownerId,
                result: resultData,
                initialCondition: transportInit,
                configHash: configHash,
                scoreWeights: holonomyBundle.metadata.creature.scoreWeights
            )
            let metadata = try holonomyResearchMetadata(
                sourceBundle: bundleURL,
                loopSpec: loopSpec,
                point: point,
                configHash: configHash
            )
            let libraryEntry = archiveResearchLibraryEntry(
                creature: creature,
                runId: resolvedRunId,
                configHash: configHash,
                sourceMode: "holonomy",
                sourceAlgorithm: "parameter_loop_v1",
                researchMetadata: metadata,
                recordedAt: replayedAt,
                campaignId: campaignID
            )
            let activityRecord = pointSearchConfig.activity.flatMap { activitySummaryRecord(for: resultData, config: $0) }
            let persistedArtifacts: PersistedResearchRunArtifacts
            if exportEnabled {
                persistedArtifacts = try persistResearchRunArtifacts(
                    directory: campaignDir,
                    baseConfig: pointBaseConfig,
                    searchConfig: pointSearchConfig,
                    resultData: resultData,
                    activityRecord: activityRecord,
                    libraryEntries: [libraryEntry],
                    exportRoot: campaignDir.appendingPathComponent("exports", isDirectory: true),
                    exportItems: [creature],
                    emptyExportMessage: "Holonomy export bundle already exists for \(creature.name)."
                ) { creature in
                    (
                        baseConfig: pointBaseConfig,
                        searchConfig: pointSearchConfig,
                        creature: creature,
                        runId: resolvedRunId,
                        campaignId: nil,
                        score: nil,
                        filtersPassed: true,
                        reason: "holonomy"
                    )
                }
            } else {
                persistedArtifacts = try persistResearchRunArtifacts(
                    directory: campaignDir,
                    baseConfig: pointBaseConfig,
                    searchConfig: pointSearchConfig,
                    resultData: resultData,
                    activityRecord: activityRecord,
                    libraryEntries: [libraryEntry]
                )
            }
            let executionArtifacts = persistedArtifacts.execution
            let archiveArtifacts = persistedArtifacts.archive
            exportCount += archiveArtifacts.exportCount
            guard let configURL = executionArtifacts.configURL,
                  let searchURL = executionArtifacts.searchURL else {
                throw ValidationError("Holonomy point \(point.sequenceIndex) did not persist flow config artifacts.")
            }

            let stepManifest = HolonomyStepManifest(
                sequenceIndex: point.sequenceIndex,
                segmentIndex: point.segmentIndex,
                segmentT: point.segmentT,
                coordinateValues: Dictionary(uniqueKeysWithValues: zip(loopSpec.coordinates, point.values)),
                configHash: configHash,
                configTopologyHash: pointTopologyHash,
                configPath: configURL.path,
                searchPath: searchURL.path,
                resultsPath: executionArtifacts.resultsURL.path,
                libraryPath: archiveArtifacts.libraryURL.path,
                activityPath: executionArtifacts.activityURL?.path,
                exportIndexPath: archiveArtifacts.exportIndexURL?.path,
                replayedAt: replayedAt
            )
            let stepManifestURL = campaignDir.appendingPathComponent("holonomy-step.json")
            try holonomyEncoder().encode(stepManifest).write(to: stepManifestURL)
            manifests.append(stepManifest)
            stepManifestPaths.append(stepManifestURL.path)
            campaignDirs.append(campaignDir.path)

            let terminalFingerprint = [UInt8](batchResult.descriptorBundle.terminal.fingerprintU8)
            if firstFingerprint == nil {
                firstFingerprint = terminalFingerprint
                firstStatePatch = batchResult.terminalStatePatch
            }
            lastFingerprint = terminalFingerprint
            lastStatePatch = batchResult.terminalStatePatch
            guard let terminalStatePatch = batchResult.terminalStatePatch else {
                throw ValidationError("Holonomy point \(point.sequenceIndex) did not capture terminal state.")
            }
            try holonomyEncoder().encode(terminalStatePatch).write(
                to: campaignDir.appendingPathComponent("terminal-state.json")
            )
            if let terminalParamPatch = batchResult.terminalParamPatch {
                try holonomyEncoder().encode(terminalParamPatch).write(
                    to: campaignDir.appendingPathComponent("terminal-params.json")
                )
            }

            transportInit = makeTransportInitConfig(
                seed: transportInit.seed,
                statePatch: terminalStatePatch,
                paramPatch: batchResult.terminalParamPatch
            )
        }

        let phenotypeClosureDistance = loopSpec.closed
            ? holonomyFingerprintDistance(firstFingerprint, lastFingerprint)
            : nil
        let transportedStateClosureDistance = loopSpec.closed
            ? holonomyStatePatchDistance(firstStatePatch, lastStatePatch)
            : nil

        let summary = HolonomySummary(
            runId: resolvedRunId,
            bundlePath: bundleURL.path,
            loopPath: loopURL.path,
            loopName: loopSpec.name,
            loopClosed: loopSpec.closed,
            coordinatePaths: loopSpec.coordinates,
            pointCount: manifests.count,
            campaignCount: manifests.count,
            configTopologyHash: topologyHash,
            phenotypeClosureDistance: phenotypeClosureDistance,
            transportedStateClosureDistance: transportedStateClosureDistance,
            replayedAt: replayedAt,
            outputDir: outputURL.path,
            exportCount: exportCount
        )
        let summaryURL = outputURL.appendingPathComponent("summary.json")
        try holonomyEncoder().encode(summary).write(to: summaryURL)
        let runManifest = HolonomyRunManifest(
            version: 1,
            runId: resolvedRunId,
            bundlePath: bundleURL.path,
            loopPath: loopURL.path,
            loopName: loopSpec.name,
            loopClosed: loopSpec.closed,
            coordinatePaths: loopSpec.coordinates,
            configTopologyHash: topologyHash,
            campaignsDir: campaignsDir.path,
            summaryPath: summaryURL.path,
            stepManifestPaths: stepManifestPaths,
            campaignDirs: campaignDirs,
            exportEnabled: exportEnabled,
            replayedAt: replayedAt
        )
        try holonomyEncoder().encode(runManifest).write(to: outputURL.appendingPathComponent("holonomy-manifest.json"))

        try promoteIfConfigured(
            options: promotion,
            defaultCompendiumPath: nil,
            dossier: dossierName,
            runDir: outputURL.path,
            includeResults: true
        )

        logger.info("Holonomy completed (points=\(manifests.count), exports=\(exportCount), output=\(outputURL.path))")
    }
}

private func loadHolonomyBundle(from bundleURL: URL) throws -> HolonomyBundle {
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .deferredToDate
    let baseURL = bundleURL.appendingPathComponent("base.json")
    let searchURL = bundleURL.appendingPathComponent("search.json")
    let metaURL = bundleURL.appendingPathComponent("meta.json")
    guard FileManager.default.fileExists(atPath: baseURL.path) else {
        throw ValidationError("Missing base.json in holonomy bundle: \(bundleURL.path)")
    }
    guard FileManager.default.fileExists(atPath: searchURL.path) else {
        throw ValidationError("Missing search.json in holonomy bundle: \(bundleURL.path)")
    }
    guard FileManager.default.fileExists(atPath: metaURL.path) else {
        throw ValidationError("Missing meta.json in holonomy bundle: \(bundleURL.path)")
    }
    let metadata = try decodeCreatureExportMetadata(
        Data(contentsOf: metaURL),
        decoder: decoder,
        fallbackBundleKind: .strictReplayBundleV1
    )
    guard metadata.bundleKind == .strictReplayBundleV1 else {
        throw ValidationError("holonomy only supports strict Flow Lenia replay bundles in v1.")
    }
    return HolonomyBundle(
        exportDir: bundleURL,
        baseConfig: try decoder.decode(LeniaBaseConfig.self, from: Data(contentsOf: baseURL)),
        searchConfig: try decoder.decode(ParsedSearchConfig.self, from: Data(contentsOf: searchURL)),
        metadata: metadata
    )
}

private func loadHolonomyLoopSpec(from url: URL) throws -> HolonomyLoopSpec {
    let spec = try JSONDecoder().decode(HolonomyLoopSpec.self, from: Data(contentsOf: url))
    guard spec.version == 1 else {
        throw ValidationError("Unsupported holonomy loop spec version \(spec.version); expected 1.")
    }
    return spec
}

private func buildHolonomyLoopPoints(_ spec: HolonomyLoopSpec) throws -> [HolonomyLoopPoint] {
    guard !spec.coordinates.isEmpty else {
        throw ValidationError("Holonomy loop spec must define at least one coordinate path.")
    }
    guard spec.vertices.count >= 2 else {
        throw ValidationError("Holonomy loop spec must define at least two vertices.")
    }
    guard spec.samplesPerSegment > 0 else {
        throw ValidationError("Holonomy loop spec samples_per_segment must be > 0.")
    }
    for (index, vertex) in spec.vertices.enumerated() {
        guard vertex.count == spec.coordinates.count else {
            throw ValidationError("Holonomy vertex \(index) does not match coordinates count \(spec.coordinates.count).")
        }
    }

    var pathVertices = spec.vertices
    if spec.closed, let first = spec.vertices.first, let last = spec.vertices.last, first != last {
        pathVertices.append(first)
    }

    var points: [HolonomyLoopPoint] = []
    var sequenceIndex = 0
    for segmentIndex in 0..<(pathVertices.count - 1) {
        let start = pathVertices[segmentIndex]
        let end = pathVertices[segmentIndex + 1]
        for sampleIndex in 0..<spec.samplesPerSegment {
            let t = Float(sampleIndex) / Float(spec.samplesPerSegment)
            let values = zip(start, end).map { lhs, rhs in lhs + (rhs - lhs) * t }
            points.append(
                HolonomyLoopPoint(
                    sequenceIndex: sequenceIndex,
                    segmentIndex: segmentIndex,
                    segmentT: t,
                    values: values
                )
            )
            sequenceIndex += 1
        }
    }
    guard let finalVertex = pathVertices.last else {
        throw ValidationError("Holonomy loop spec produced no final vertex.")
    }
    points.append(
        HolonomyLoopPoint(
            sequenceIndex: sequenceIndex,
            segmentIndex: max(0, pathVertices.count - 2),
            segmentT: 1.0,
            values: finalVertex
        )
    )
    return points
}

private func validateHolonomyParams(
    baseParams: ParamsConfig,
    coordinates: [String],
    vertices: [[Float]]
) throws -> ParamsConfig {
    var params = baseParams
    for vertex in vertices {
        params = try applyHolonomyCoordinateValues(values: vertex, coordinates: coordinates, to: params)
    }
    return params
}

private func applyHolonomyCoordinateValues(
    values: [Float],
    coordinates: [String],
    to params: ParamsConfig
) throws -> ParamsConfig {
    guard params.mode == "explicit" else {
        throw ValidationError("Holonomy requires params.mode == \"explicit\".")
    }
    guard values.count == coordinates.count else {
        throw ValidationError("Holonomy coordinate/value count mismatch.")
    }
    var updated = params
    for (coordinate, value) in zip(coordinates, values) {
        updated = try setHolonomyParam(path: coordinate, value: value, params: updated)
    }
    return updated
}

private func setHolonomyParam(path: String, value: Float, params: ParamsConfig) throws -> ParamsConfig {
    let parts = path.split(separator: ".").map(String.init)
    guard let root = parts.first else {
        throw ValidationError("Holonomy parameter path cannot be empty.")
    }
    switch root {
    case "R":
        guard parts.count == 1 else {
            throw ValidationError("Holonomy path R must not have indices.")
        }
        return ParamsConfig(
            mode: params.mode,
            seed: params.seed,
            ranges: params.ranges,
            r: params.r,
            b: params.b,
            w: params.w,
            a: params.a,
            m: params.m,
            s: params.s,
            h: params.h,
            R: value
        )
    case "r":
        let updated = try holonomySet1D(path: path, values: params.r, value: value)
        return ParamsConfig(mode: params.mode, seed: params.seed, ranges: params.ranges, r: updated, b: params.b, w: params.w, a: params.a, m: params.m, s: params.s, h: params.h, R: params.R)
    case "m":
        let updated = try holonomySet1D(path: path, values: params.m, value: value)
        return ParamsConfig(mode: params.mode, seed: params.seed, ranges: params.ranges, r: params.r, b: params.b, w: params.w, a: params.a, m: updated, s: params.s, h: params.h, R: params.R)
    case "s":
        let updated = try holonomySet1D(path: path, values: params.s, value: value)
        return ParamsConfig(mode: params.mode, seed: params.seed, ranges: params.ranges, r: params.r, b: params.b, w: params.w, a: params.a, m: params.m, s: updated, h: params.h, R: params.R)
    case "h":
        let updated = try holonomySet1D(path: path, values: params.h, value: value)
        return ParamsConfig(mode: params.mode, seed: params.seed, ranges: params.ranges, r: params.r, b: params.b, w: params.w, a: params.a, m: params.m, s: params.s, h: updated, R: params.R)
    case "b":
        let updated = try holonomySet2D(path: path, values: params.b, value: value)
        return ParamsConfig(mode: params.mode, seed: params.seed, ranges: params.ranges, r: params.r, b: updated, w: params.w, a: params.a, m: params.m, s: params.s, h: params.h, R: params.R)
    case "w":
        let updated = try holonomySet2D(path: path, values: params.w, value: value)
        return ParamsConfig(mode: params.mode, seed: params.seed, ranges: params.ranges, r: params.r, b: params.b, w: updated, a: params.a, m: params.m, s: params.s, h: params.h, R: params.R)
    case "a":
        let updated = try holonomySet2D(path: path, values: params.a, value: value)
        return ParamsConfig(mode: params.mode, seed: params.seed, ranges: params.ranges, r: params.r, b: params.b, w: params.w, a: updated, m: params.m, s: params.s, h: params.h, R: params.R)
    default:
        throw ValidationError("Unsupported holonomy parameter path root '\(root)'.")
    }
}

private func holonomySet1D(path: String, values: [Float]?, value: Float) throws -> [Float] {
    let parts = path.split(separator: ".").map(String.init)
    guard parts.count == 2, let index = Int(parts[1]) else {
        throw ValidationError("Holonomy 1D parameter path must have the form field.index, got '\(path)'.")
    }
    guard var updated = values, updated.indices.contains(index) else {
        throw ValidationError("Holonomy path '\(path)' is out of range.")
    }
    updated[index] = value
    return updated
}

private func holonomySet2D(path: String, values: [[Float]]?, value: Float) throws -> [[Float]] {
    let parts = path.split(separator: ".").map(String.init)
    guard parts.count == 3, let outer = Int(parts[1]), let inner = Int(parts[2]) else {
        throw ValidationError("Holonomy 2D parameter path must have the form field.i.j, got '\(path)'.")
    }
    guard var updated = values,
          updated.indices.contains(outer),
          updated[outer].indices.contains(inner) else {
        throw ValidationError("Holonomy path '\(path)' is out of range.")
    }
    updated[outer][inner] = value
    return updated
}

private func makeHolonomyBaseConfig(
    baseConfig: LeniaBaseConfig,
    params: ParamsConfig,
    initConfig: InitConfig
) -> LeniaBaseConfig {
    LeniaBaseConfig(
        backend: baseConfig.backend,
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
        params: params,
        init: initConfig,
        run: baseConfig.run,
        interventions: baseConfig.interventions
    )
}

private func makeTransportInitConfig(
    seed: Int,
    statePatch: InitStatePatchConfig,
    paramPatch: InitStatePatchConfig?
) -> InitConfig {
    InitConfig(
        seed: seed,
        patches: [],
        a_uniform: UniformRange(low: 0.0, high: 0.0),
        p_uniform: nil,
        state_patch: statePatch,
        p_state_patch: paramPatch
    )
}

private func holonomySupportsActivity(baseConfig: LeniaBaseConfig) -> Bool {
    baseConfig.parameter_embedding.enabled &&
        (baseConfig.`init`.p_uniform != nil || baseConfig.`init`.p_state_patch != nil)
}

private func holonomyCampaignID(_ sequenceIndex: Int) -> String {
    String(format: "%04d", sequenceIndex + 1)
}

private func holonomyFingerprintDistance(_ lhs: [UInt8]?, _ rhs: [UInt8]?) -> Float? {
    guard let lhs, let rhs else { return nil }
    guard lhs.count == rhs.count else {
        fatalError("Holonomy fingerprint closure requires equal-length fingerprints.")
    }
    let sum = zip(lhs, rhs).reduce(Float.zero) { acc, pair in
        let delta = Float(pair.0) - Float(pair.1)
        return acc + delta * delta
    }
    return sqrt(sum) / max(1, Float(lhs.count))
}

private func holonomyStatePatchDistance(
    _ lhs: InitStatePatchConfig?,
    _ rhs: InitStatePatchConfig?
) -> Float? {
    guard let lhs, let rhs else { return nil }
    let lhsValues = lhs.decodedValues()
    let rhsValues = rhs.decodedValues()
    guard lhsValues.count == rhsValues.count else {
        fatalError("Holonomy state closure requires equal-length state patches.")
    }
    let sum = zip(lhsValues, rhsValues).reduce(Float.zero) { acc, pair in
        let delta = pair.0 - pair.1
        return acc + delta * delta
    }
    return sqrt(sum) / max(1, Float(lhsValues.count))
}

private func holonomyResearchMetadata(
    sourceBundle: URL,
    loopSpec: HolonomyLoopSpec,
    point: HolonomyLoopPoint,
    configHash: String
) throws -> [String: AnyCodable] {
    try [
        "version": researchMetadataValue(1),
        "mode": researchMetadataValue("holonomy"),
        "source_bundle_dir": researchMetadataValue(sourceBundle.path),
        "loop_name": researchMetadataValue(loopSpec.name ?? "unnamed"),
        "loop_closed": researchMetadataValue(loopSpec.closed),
        "coordinates": researchMetadataValue(loopSpec.coordinates),
        "values": researchMetadataValue(point.values),
        "sequence_index": researchMetadataValue(point.sequenceIndex),
        "segment_index": researchMetadataValue(point.segmentIndex),
        "segment_t": researchMetadataValue(point.segmentT),
        "holonomy_config_hash": researchMetadataValue(configHash),
    ]
}

private func holonomyEncoder() -> JSONEncoder {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    encoder.dateEncodingStrategy = .deferredToDate
    return encoder
}
