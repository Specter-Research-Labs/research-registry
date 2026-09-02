import ArgumentParser
import Foundation
import LeniaCore

struct ObstacleResponseCommand: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "obstacle-response",
        abstract: "Run paired sham and heading-relative Flow-Lenia wall-potential continuations for a fixed corpus"
    )

    @Option(name: .long, help: "Base Flow Lenia config shared by the fixed corpus")
    var config: String

    @Option(name: .long, help: "Corpus JSONL with params plus specimen_id and optional life/family/map/rule join keys")
    var corpus: String

    @Option(name: .shortAndLong, help: "Output directory for protocol.json and results.jsonl")
    var output: String

    @Option(name: .long, help: "Requested backend: auto|metal-full|mlx")
    var backend: String = "auto"

    @Option(name: .long, help: "Default init seed for rows without init_seed")
    var initSeed: Int = 0

    @Option(name: .long, help: "Steps before the paired continuation checkpoint")
    var checkpointSteps: Int = 160

    @Option(name: .long, help: "Pre-checkpoint window used to estimate heading")
    var headingWindow: Int = 40

    @Option(name: .long, help: "Steps in each sham or obstacle continuation")
    var continuationSteps: Int = 400

    @Option(name: .long, help: "Geometry measurement stride; must be 1 so contact events are not skipped")
    var metricStride: Int = 1

    @Option(name: .long, help: "Circular wall-potential radius divided by largest-component r95")
    var obstacleRadiusBodyRatio: Float = 0.5

    @Option(name: .long, help: "Initial body-to-obstacle gap divided by measured body radius")
    var obstacleGapBodyRatio: Float = 0.15

    @Option(name: .long, help: "Left/right obstacle offset divided by measured body radius")
    var lateralOffsetBodyRatio: Float = 0.5

    @Option(name: .long, help: "Cell matter threshold used for body extent and clearance")
    var matterThreshold: Float = 0.05

    @Option(name: .long, help: "Clearance at or below which contact is recorded")
    var contactDistance: Float = 1.5

    @Option(name: .long, help: "Minimum retained-matter ratio used with component coherence and scale in the viability gate")
    var survivalMassFraction: Float = 0.8

    @Option(name: .long, help: "Minimum pre-checkpoint displacement required to orient an obstacle")
    var minimumHeadingDisplacement: Float = 2

    @Option(name: .long, help: "Minimum checkpoint-to-final displacement required to define a turn angle")
    var minimumPostDisplacement: Float = 2

    @Option(name: .long, help: "Minimum fraction of total matter in the largest thresholded component")
    var minimumLargestComponentMassFraction: Float = 0.8

    @Option(name: .long, help: "Maximum largest-component r99 as a fraction of the shorter grid side")
    var maximumBodyR99GridFraction: Float = 0.1875

    @Option(name: .long, help: "Maximum allowed r99 expansion or contraction ratio across viability checks")
    var maximumBodyScaleRatio: Float = 2

    @Option(name: .long, help: "Minimum body-to-obstacle clearance at the checkpoint in cells")
    var minimumInitialClearance: Float = 2

    @Option(name: .long, help: "Required obstacle footprint margin from a non-periodic arena boundary")
    var obstacleBoundaryMargin: Float = 2

    @Option(name: .long, help: "Positive Flow Lenia wall-potential height inside the circular obstacle")
    var obstaclePotentialHeight: Float = 30

    @OptionGroup
    var logOptions: LogOptions

    func run() async throws {
        let runId = resolveRunID(prefix: "obstacle-response", logOptions: logOptions)
        let outputRoot = try resolvePath(output, dossier: dossierName)
        let runDirectory = makeRunOutputDirectory(outputRoot: outputRoot, runID: runId)
        let logging = try bootstrapRunLogging(
            runID: runId,
            role: "obstacle-response",
            loggerLabel: "LeniaSwarm.ObstacleResponse",
            logStem: "obstacle-response",
            outputForLogs: outputRoot,
            logOptions: logOptions,
            dossier: dossierName,
            fallbackOutputLogDir: true
        )
        let logger = logging.logger

        let configPath = try resolvePath(config, dossier: dossierName)
        let corpusPath = try resolvePath(corpus, dossier: dossierName)
        let sourceConfigData = try Data(contentsOf: URL(fileURLWithPath: configPath))
        let rows = try decodeCorpus(at: corpusPath)
        guard !rows.isEmpty else {
            throw ValidationError("corpus contains no genotypes")
        }

        let protocolConfig = UnseenObstacleResponseProtocol(
            checkpointSteps: checkpointSteps,
            headingWindow: headingWindow,
            continuationSteps: continuationSteps,
            metricStride: metricStride,
            obstacleRadiusBodyRatio: obstacleRadiusBodyRatio,
            obstacleGapBodyRatio: obstacleGapBodyRatio,
            lateralOffsetBodyRatio: lateralOffsetBodyRatio,
            matterThreshold: matterThreshold,
            contactDistance: contactDistance,
            survivalMassFraction: survivalMassFraction,
            minimumHeadingDisplacement: minimumHeadingDisplacement,
            minimumPostDisplacement: minimumPostDisplacement,
            minimumLargestComponentMassFraction: minimumLargestComponentMassFraction,
            maximumBodyR99GridFraction: maximumBodyR99GridFraction,
            maximumBodyScaleRatio: maximumBodyScaleRatio,
            minimumInitialClearance: minimumInitialClearance,
            obstacleBoundaryMargin: obstacleBoundaryMargin,
            obstaclePotentialHeight: obstaclePotentialHeight
        )

        let firstSeed = rows[0].initSeed ?? initSeed
        let firstRuntime = try runtimeConfig(
            sourceConfigData: sourceConfigData,
            row: rows[0],
            seed: firstSeed,
            backendOverride: nil
        )
        let resolvedBackend = try resolveMetalFirstSimulatorBackend(
            requestValue: backend,
            runtimeConfigs: [firstRuntime]
        )

        try FileManager.default.createDirectory(at: runDirectory, withIntermediateDirectories: true)
        try writeResearchJSON(
            protocolConfig,
            to: runDirectory.appendingPathComponent("protocol.json"),
            prettyPrinted: true
        )
        let resultsURL = runDirectory.appendingPathComponent("results.jsonl")
        try Data().write(to: resultsURL, options: .atomic)
        let resultsHandle = try FileHandle(forWritingTo: resultsURL)
        defer { try? resultsHandle.close() }

        logger.info("Loaded \(rows.count) fixed-corpus rows; backend=\(resolvedBackend.rawValue)")
        logger.info("Output: \(runDirectory.path)")
        let startedAt = Date()
        for (index, row) in rows.enumerated() {
            let seed = row.initSeed ?? initSeed
            guard let specimenId = row.specimenId, !specimenId.isEmpty else {
                throw ValidationError("corpus row \(index) is missing specimen_id")
            }
            let resolvedRuntime = try runtimeConfig(
                sourceConfigData: sourceConfigData,
                row: row,
                seed: seed,
                backendOverride: resolvedBackend
            )
            try validateCleanBaseline(resolvedRuntime)
            let harness = try UnseenObstacleResponseHarness(
                runtimeConfig: resolvedRuntime,
                protocol: protocolConfig
            )
            let records = harness.run(specimen: UnseenObstacleSpecimen(
                specimenId: specimenId,
                lifeId: row.lifeId ?? "seed-\(seed)",
                family: row.family,
                mapId: row.mapId,
                ruleId: row.ruleId,
                initSeed: seed
            ))
            try appendResearchJSONLines(records, to: resultsHandle)
            try resultsHandle.synchronize()
            logger.info("Evaluated \(index + 1)/\(rows.count): \(specimenId)")
        }
        logger.info(
            "Done (\(rows.count) specimens, \(String(format: "%.2f", Date().timeIntervalSince(startedAt)))s) -> \(resultsURL.path)"
        )
    }

    private func decodeCorpus(at path: String) throws -> [CorpusRow] {
        let corpusText = try String(contentsOf: URL(fileURLWithPath: path), encoding: .utf8)
        let decoder = JSONDecoder()
        return try corpusText.split(separator: "\n").compactMap { line in
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            guard !trimmed.isEmpty else { return nil }
            return try decoder.decode(CorpusRow.self, from: Data(trimmed.utf8))
        }
    }

    private func runtimeConfig(
        sourceConfigData: Data,
        row: CorpusRow,
        seed: Int,
        backendOverride: FlowLeniaComputeBackend?
    ) throws -> LeniaRuntimeConfig {
        var overrides = row.params.explicitOverrides(seed: seed)
        if let initialCondition = row.initialCondition {
            let encoded = try JSONEncoder().encode(initialCondition)
            overrides["init"] = try JSONSerialization.jsonObject(with: encoded)
        } else {
            overrides["init.seed"] = seed
        }
        if let backendOverride {
            overrides["backend"] = backendOverride.rawValue
        }
        return try loadRuntimeConfig(from: sourceConfigData, overrides: overrides)
    }

    private func validateCleanBaseline(_ runtimeConfig: LeniaRuntimeConfig) throws {
        if runtimeConfig.walls?.enabled == true {
            throw ValidationError("obstacle-response requires a base config without enabled walls")
        }
        if runtimeConfig.environment != nil {
            throw ValidationError("obstacle-response requires a base config without an environment potential")
        }
        if runtimeConfig.obstacleField?.enabled == true {
            throw ValidationError("obstacle-response constructs its own heading-relative wall potential; disable obstacle_field")
        }
        if !runtimeConfig.interventions.isEmpty {
            throw ValidationError("obstacle-response requires a base config without scheduled interventions")
        }
    }
}
