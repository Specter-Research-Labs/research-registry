import ArgumentParser
import Foundation
import LeniaCore
import Logging

struct LocalCommand: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "local",
        abstract: "Run a local single-run simulation with optional frame export"
    )

    @Option(name: .long, help: "Path to base config.json")
    var config: String

    @Option(name: .long, help: "Path to search config.json")
    var search: String

    @Option(name: .long, help: "Requested backend: auto|metal-full|mlx")
    var backend: String = "auto"

    @Option(name: .shortAndLong, help: "Output directory for run artifacts")
    var output: String

    @Option(name: .long, help: "Override seed_start from search config")
    var seed: Int?

    @Option(name: .long, help: "Override count from search config")
    var count: Int?

    @Flag(name: .long, help: "Enable frame export to <output>/<run_id>/frames")
    var frames: Bool = false

    @Option(name: .long, help: "Frame output directory (relative paths resolved under <output>/<run_id>)")
    var framesDir: String?

    @Flag(name: .long, help: "Also export colorized frames derived from grayscale truth frames")
    var framesColor: Bool = false

    @Option(name: .long, help: "Color frame output directory (relative paths resolved under <output>/<run_id>)")
    var framesColorDir: String?

    @Option(name: .long, help: "Frame stride (steps between frames)")
    var frameStride: Int = 1

    @Flag(name: .long, help: "Capture frames during warmup steps")
    var includeWarmupFrames: Bool = false

    @Option(name: .long, help: "Sample index to render when batch_size > 1")
    var sampleIndex: Int = 0

    @Flag(name: .long, help: "Validate configs and exit without running")
    var validateOnly: Bool = false

    @OptionGroup
    var promotion: ArchivePromotionOptions

    @OptionGroup
    var logOptions: LogOptions

    func run() async throws {
        let resolvedRunId = resolveRunID(prefix: "local", logOptions: logOptions)
        let resolvedOutputRoot = try resolvePath(output, dossier: dossierName)
        let runDirURL = makeRunOutputDirectory(outputRoot: resolvedOutputRoot, runID: resolvedRunId)
        let logging = try bootstrapRunLogging(
            runID: resolvedRunId,
            role: "local",
            loggerLabel: "LeniaSwarm.Local",
            logStem: "local",
            outputForLogs: resolvedOutputRoot,
            logOptions: logOptions,
            dossier: dossierName,
            fallbackOutputLogDir: true
        )

        let nodeId = logging.nodeID
        let logger = logging.logger

        logLoggingInitialized(logger, runID: resolvedRunId, logging: logging)
        logger.info("Output: \(runDirURL.path)")

        let baseConfigURL = URL(fileURLWithPath: config)
        let sourceBaseConfigData = try Data(contentsOf: baseConfigURL)
        let searchConfigURL = URL(fileURLWithPath: search)
        let searchConfigData = try Data(contentsOf: searchConfigURL)
        let parsedSearchConfig = try JSONDecoder().decode(ParsedSearchConfig.self, from: searchConfigData)
        let baseOverrides: [String: Any] = parsedSearchConfig.overridesAsDict()

        let effectiveBaseConfigData = try baseConfigDataByApplyingOverrides(
            sourceBaseConfigData,
            overrides: baseOverrides
        )
        let effectiveBaseConfig = try JSONDecoder().decode(LeniaBaseConfig.self, from: effectiveBaseConfigData)
        let resolvedBackend = try resolveMetalFirstSearchBackend(requestValue: backend, baseConfig: effectiveBaseConfig)
        let baseConfigData = try baseConfigDataBySettingBackend(
            sourceBaseConfigData,
            backend: resolvedBackend
        )
        let baseConfig = try JSONDecoder().decode(LeniaBaseConfig.self, from: baseConfigData)
        let topologyHash = configTopologyHash(baseConfig)

        let runCount = count ?? parsedSearchConfig.count
        if runCount <= 0 {
            throw ValidationError("count must be > 0")
        }
        if parsedSearchConfig.batchSize <= 0 {
            throw ValidationError("batch_size must be > 0")
        }
        let seedStart = seed ?? parsedSearchConfig.seedStart
        let initSeedOffset = parsedSearchConfig.initSeedOffset ?? 0

        let framesColorEnabled = framesColor || framesColorDir != nil
        let framesEnabled = frames || framesDir != nil || framesColorEnabled
        if framesEnabled {
            if runCount != 1 {
                throw ValidationError("frame export requires count=1")
            }
            if frameStride <= 0 {
                throw ValidationError("frame_stride must be > 0")
            }
            if sampleIndex != 0 {
                throw ValidationError("sample_index must be 0 when count=1")
            }
        }

        var seeds: [Int] = []
        seeds.reserveCapacity(runCount)
        for i in 0..<runCount {
            let seedValue = seedStart + i * parsedSearchConfig.seedStride
            seeds.append(seedValue)
        }

        let simSearchConfig = parsedSearchConfig.toSearchConfig()

        if validateOnly {
            logger.info("Configs validated successfully (backend=\(resolvedBackend.rawValue))")
            return
        }

        try FileManager.default.createDirectory(at: runDirURL, withIntermediateDirectories: true)
        try baseConfigData.write(to: runDirURL.appendingPathComponent("config.json"))
        try searchConfigData.write(to: runDirURL.appendingPathComponent("search.json"))

        var frameWriter: FrameWriter?
        var colorFrameWriter: ColorFrameWriter?
        var frameCapture: FrameCapture?
        var framesDirPath: String? = nil
        var framesColorDirPath: String? = nil
        if framesEnabled {
            let resolvedFramesDir = resolveFramesDir(
                framesDir: framesDir,
                runDir: runDirURL
            )
            try FileManager.default.createDirectory(at: resolvedFramesDir, withIntermediateDirectories: true)
            let writer = FrameWriter(outputDir: resolvedFramesDir)
            frameWriter = writer

            var captureHandler: (_ step: Int, _ width: Int, _ height: Int, _ data: Data) -> Void = { step, width, height, data in
                writer.write(step: step, width: width, height: height, data: data)
            }
            if framesColorEnabled {
                let resolvedColorDir = resolveFramesColorDir(
                    framesDir: framesColorDir,
                    runDir: runDirURL
                )
                try FileManager.default.createDirectory(at: resolvedColorDir, withIntermediateDirectories: true)
                let colorWriter = ColorFrameWriter(outputDir: resolvedColorDir)
                colorFrameWriter = colorWriter
                framesColorDirPath = resolvedColorDir.path
                captureHandler = { step, width, height, data in
                    writer.write(step: step, width: width, height: height, data: data)
                    colorWriter.write(step: step, width: width, height: height, grayscale: data)
                }
            }

            frameCapture = FrameCapture(
                stride: frameStride,
                includeWarmup: includeWarmupFrames,
                sampleIndex: sampleIndex
            ) { step, width, height, data in captureHandler(step, width, height, data) }
            framesDirPath = resolvedFramesDir.path
            logger.info("Frame export enabled (stride=\(frameStride), dir=\(resolvedFramesDir.path))")
            if let framesColorDirPath {
                logger.info("Color frame export enabled (dir=\(framesColorDirPath))")
            }
        }

        var refOverrides = baseOverrides
        refOverrides["run.steps"] = parsedSearchConfig.steps
        let refConfig = try loadRuntimeConfig(from: baseConfigData, overrides: refOverrides)

        var allResults: [SimulationResultData] = []
        var currentIdx = 0

        let startTime = Date()
        while currentIdx < seeds.count {
            let chunkEnd = min(currentIdx + parsedSearchConfig.batchSize, seeds.count)
            let chunkSeeds = Array(seeds[currentIdx..<chunkEnd])

            var overrides = baseOverrides
            overrides["params.seed"] = chunkSeeds[0]
            overrides["run.steps"] = parsedSearchConfig.steps
            let runtimeConfig = try loadRuntimeConfig(from: baseConfigData, overrides: overrides)
            let engine = SearchEngine(runtimeConfig: runtimeConfig)

            let batchResults = engine.runBatch(
                seeds: chunkSeeds,
                initSeedOffset: initSeedOffset,
                searchConfig: simSearchConfig,
                frameCapture: frameCapture
            )

            for result in batchResults {
                let resultData = materializeSearchResultData(
                    result,
                    backend: runtimeConfig.backend.rawValue,
                    implementation: runtimeConfig.implementation,
                    searchConfig: simSearchConfig
                )
                allResults.append(resultData)
            }

            currentIdx = chunkEnd
        }

        if let writer = frameWriter, let error = writer.error {
            throw error
        }
        if let writer = colorFrameWriter, let error = writer.error {
            throw error
        }

        let duration = Date().timeIntervalSince(startTime)
        let resultsURL = runDirURL.appendingPathComponent("results.jsonl")
        try writeResearchJSONLines(allResults, to: resultsURL)
        let topResults = try writeTopSimulationResults(
            from: allResults,
            limit: parsedSearchConfig.topK,
            to: runDirURL.appendingPathComponent("top.json")
        )

        let collectionConfig = parsedSearchConfig.collection ?? CollectionConfig.defaultConfig
        var collectedCount = 0
        var exportedCount = 0

        if collectionConfig.enabled {
            let collected = allResults.filter { shouldCollect($0, config: collectionConfig) }
            if !collected.isEmpty {
                var libraryEntries: [ResearchLibraryEntry] = []
                libraryEntries.reserveCapacity(collected.count)
                var exportArtifacts: [(SavedCreature, SimulationResultData)] = []
                exportArtifacts.reserveCapacity(collected.count)

                for result in collected {
                    let initialCondition = InitConfig(
                        seed: result.initSeed,
                        patches: refConfig.patches,
                        a_uniform: refConfig.aUniform,
                        p_uniform: refConfig.pUniform,
                        state_patch: refConfig.statePatch,
                        p_state_patch: refConfig.paramPatch
                    )
                    let creature = savedCreatureFromResult(
                        name: generateCreatureName(),
                        ownerId: nodeId,
                        result: result,
                        initialCondition: initialCondition,
                        configHash: topologyHash
                    )
                    let entry = archiveResearchLibraryEntry(
                        creature: creature,
                        runId: resolvedRunId,
                        configHash: topologyHash
                    )
                    libraryEntries.append(entry)
                    exportArtifacts.append((creature, result))
                }
                let archiveArtifacts = try persistResearchArchiveArtifacts(
                    runDirectory: runDirURL,
                    libraryEntries: libraryEntries,
                    exportRoot: collectionConfig.exportEnabled
                        ? runDirURL.appendingPathComponent("exports", isDirectory: true)
                        : nil,
                    exportItems: collectionConfig.exportEnabled ? exportArtifacts : [],
                    buildExportPayload: { item in
                        let creature = item.0
                        let result = item.1
                        return (
                            baseConfig: baseConfig,
                            searchConfig: parsedSearchConfig,
                            creature: creature,
                            runId: resolvedRunId,
                            campaignId: Optional<UUID>.none,
                            score: result.score,
                            filtersPassed: result.filtersPassed,
                            reason: "auto"
                        )
                    }
                )
                collectedCount = libraryEntries.count
                logger.info("Collected \(collectedCount) creatures to library/index.jsonl")

                if collectionConfig.exportEnabled {
                    exportedCount = archiveArtifacts.exportCount
                    logger.info("Exported \(exportedCount) creatures to exports/index.jsonl")
                }
            }
        }

        let summary = LocalRunSummary(
            runId: resolvedRunId,
            seedStart: seedStart,
            count: runCount,
            steps: parsedSearchConfig.steps,
            durationSeconds: duration,
            resultsCount: allResults.count,
            topCount: topResults.count,
            collectedCount: collectedCount,
            exportedCount: exportedCount,
            framesDir: framesDirPath,
            framesColorDir: framesColorDirPath,
            frameStride: framesEnabled ? frameStride : nil,
            includeWarmupFrames: framesEnabled ? includeWarmupFrames : nil
        )
        try writeResearchJSON(summary, to: runDirURL.appendingPathComponent("summary.json"), prettyPrinted: true)

        logger.info("Local run complete (duration=\(String(format: "%.2f", duration))s, results=\(allResults.count))")

        let resolvedPromotion = try promoteIfConfigured(
            options: promotion,
            defaultCompendiumPath: try resolveCompendiumPath(),
            dossier: dossierName,
            defaultEnabled: true,
            runDir: runDirURL.path,
            includeResults: true,
            stats: true
        )
        if let compendiumPath = resolvedPromotion.compendiumPath {
            logger.info("Promoted local run into compendium: \(compendiumPath)")
        }
    }

    private func resolveCompendiumPath() throws -> String {
        try resolveArtifactPath("artifacts/compendium.sqlite", dossier: dossierName)
    }
}

private struct LocalRunSummary: Codable {
    let runId: String
    let seedStart: Int
    let count: Int
    let steps: Int
    let durationSeconds: Double
    let resultsCount: Int
    let topCount: Int
    let collectedCount: Int
    let exportedCount: Int
    let framesDir: String?
    let framesColorDir: String?
    let frameStride: Int?
    let includeWarmupFrames: Bool?
}

private func shouldCollect(_ result: SimulationResultData, config: CollectionConfig) -> Bool {
    if config.requireStable && !result.metrics.isStable { return false }
    if config.requireFiltersPassed && !result.filtersPassed { return false }
    if let minScore = config.minScore {
        guard let score = result.score, score >= minScore else { return false }
    }
    return true
}

private func generateCreatureName() -> String {
    let adjectives = ["ancient", "crystal", "ethereal", "flowing", "glowing", "harmonic",
                      "luminous", "mystic", "pulsing", "radiant", "serene", "vibrant"]
    let nouns = ["amoeba", "blob", "cell", "dancer", "entity", "form",
                 "glider", "orbiter", "pattern", "pulse", "spiral", "walker"]
    let adj = adjectives.randomElement() ?? "unknown"
    let noun = nouns.randomElement() ?? "creature"
    let id = String(format: "%04d", Int.random(in: 0...9999))
    return "\(adj)-\(noun)-\(id)"
}
