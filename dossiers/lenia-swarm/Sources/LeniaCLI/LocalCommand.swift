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

        let selectedSeeds = parsedSearchConfig.seeds
        if selectedSeeds != nil && (seed != nil || count != nil) {
            throw ValidationError("search.seeds cannot be combined with --seed or --count overrides.")
        }
        if let selectedSeeds, selectedSeeds.isEmpty {
            throw ValidationError("search.seeds must not be empty.")
        }
        if let selectedSeeds, selectedSeeds.count != parsedSearchConfig.count {
            throw ValidationError("search.count must equal search.seeds.count when search.seeds is set.")
        }
        let runCount = selectedSeeds?.count ?? count ?? parsedSearchConfig.count
        if runCount <= 0 {
            throw ValidationError("count must be > 0")
        }
        if parsedSearchConfig.batchSize <= 0 {
            throw ValidationError("batch_size must be > 0")
        }
        let seedStart = selectedSeeds?.first ?? seed ?? parsedSearchConfig.seedStart
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

        let seeds: [Int]
        if let selectedSeeds {
            seeds = selectedSeeds
        } else {
            var rangeSeeds: [Int] = []
            rangeSeeds.reserveCapacity(runCount)
            for i in 0..<runCount {
                let seedValue = seedStart + i * parsedSearchConfig.seedStride
                rangeSeeds.append(seedValue)
            }
            seeds = rangeSeeds
        }

        let simSearchConfig = parsedSearchConfig.toSearchConfig()

        if validateOnly {
            logger.info("Configs validated successfully (backend=\(resolvedBackend.rawValue))")
            return
        }

        try FileManager.default.createDirectory(at: runDirURL, withIntermediateDirectories: true)

        let inputHash = researchConfigHash([
            ("config", baseConfigData),
            ("search", searchConfigData),
        ])
        let checkpointURL = runDirURL.appendingPathComponent("checkpoint.json")
        let summaryURL = runDirURL.appendingPathComponent("summary.json")
        let resultsURL = runDirURL.appendingPathComponent("results.jsonl")
        let topURL = runDirURL.appendingPathComponent("top.json")
        let libraryURL = runDirURL.appendingPathComponent("library/index.jsonl")
        let exportRootURL = runDirURL.appendingPathComponent("exports", isDirectory: true)
        let exportIndexURL = exportRootURL.appendingPathComponent("index.jsonl")

        if let existingSummary = try loadCompletedLocalRunSummary(
            at: summaryURL,
            runId: resolvedRunId,
            expectedCount: runCount
        ) {
            try validateExistingLocalRunInputs(
                runDir: runDirURL,
                baseConfigData: baseConfigData,
                searchConfigData: searchConfigData
            )
            logger.info("Existing completed run found; skipping simulation and retrying promotion from \(runDirURL.path)")
            try promoteLocalRunIfConfigured(
                promotion: promotion,
                runID: resolvedRunId,
                runDirURL: runDirURL,
                logger: logger
            )
            logger.info(
                "Local run already complete (results=\(existingSummary.resultsCount), collected=\(existingSummary.collectedCount), exported=\(existingSummary.exportedCount))"
            )
            return
        }

        let loadedCheckpoint = try loadLocalRunCheckpoint(
            at: checkpointURL,
            runId: resolvedRunId,
            inputHash: inputHash,
            seedStart: seedStart,
            seedStride: parsedSearchConfig.seedStride,
            count: runCount,
            batchSize: parsedSearchConfig.batchSize,
            steps: parsedSearchConfig.steps
        )
        let isResuming = loadedCheckpoint != nil
        if !isResuming {
            try validateFreshLocalRunDirectory(runDirURL)
        }

        try prepareLocalRunInputFiles(
            runDir: runDirURL,
            baseConfigData: baseConfigData,
            searchConfigData: searchConfigData,
            isResuming: isResuming
        )

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

        var checkpoint = loadedCheckpoint ?? LocalRunCheckpoint(
            runId: resolvedRunId,
            inputHash: inputHash,
            seedStart: seedStart,
            seedStride: parsedSearchConfig.seedStride,
            count: runCount,
            batchSize: parsedSearchConfig.batchSize,
            steps: parsedSearchConfig.steps
        )
        var completedBatchKeys = Set(checkpoint.completedBatches.map(\.key))
        var topResults = try loadLocalTopResults(at: topURL)
        var resultCount = checkpoint.resultsCount
        var collectedCount = checkpoint.collectedCount
        var exportedCount = checkpoint.exportedCount
        var currentIdx = 0
        let collectionConfig = parsedSearchConfig.collection ?? CollectionConfig.defaultConfig

        if !isResuming {
            try resetLocalRunStreams(
                resultsURL: resultsURL,
                libraryURL: collectionConfig.enabled ? libraryURL : nil,
                exportIndexURL: collectionConfig.enabled && collectionConfig.exportEnabled ? exportIndexURL : nil
            )
        }

        let resultsHandle = try openLocalAppendHandle(resultsURL)
        defer { try? resultsHandle.close() }
        let libraryHandle = collectionConfig.enabled ? try openLocalAppendHandle(libraryURL) : nil
        defer { try? libraryHandle?.close() }
        let exportIndexHandle = collectionConfig.enabled && collectionConfig.exportEnabled
            ? try openLocalAppendHandle(exportIndexURL)
            : nil
        defer { try? exportIndexHandle?.close() }

        let startTime = Date()
        let checkpointDurationAtStart = checkpoint.durationSeconds
        while currentIdx < seeds.count {
            let chunkEnd = min(currentIdx + parsedSearchConfig.batchSize, seeds.count)
            let chunkSeeds = Array(seeds[currentIdx..<chunkEnd])
            let batchKey = LocalRunCheckpointBatch.key(startIndex: currentIdx, endIndex: chunkEnd)
            if completedBatchKeys.contains(batchKey) {
                currentIdx = chunkEnd
                continue
            }

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

            let batchResultData = batchResults.map { result in
                materializeSearchResultData(
                    result,
                    backend: runtimeConfig.backend.rawValue,
                    implementation: runtimeConfig.implementation,
                    searchConfig: simSearchConfig
                )
            }
            try appendResearchJSONLines(batchResultData, to: resultsHandle)
            try resultsHandle.synchronize()
            mergeTopSimulationResults(batchResultData, into: &topResults, limit: parsedSearchConfig.topK)
            try writeTopSimulationResultsSnapshot(topResults, to: topURL)

            let batchArchive = try appendLocalArchiveArtifacts(
                results: batchResultData,
                collectionConfig: collectionConfig,
                refConfig: refConfig,
                baseConfig: baseConfig,
                searchConfig: parsedSearchConfig,
                topologyHash: topologyHash,
                ownerId: nodeId,
                runId: resolvedRunId,
                exportRoot: exportRootURL,
                libraryHandle: libraryHandle,
                exportIndexHandle: exportIndexHandle
            )
            try libraryHandle?.synchronize()
            try exportIndexHandle?.synchronize()

            resultCount += batchResultData.count
            collectedCount += batchArchive.collectedCount
            exportedCount += batchArchive.exportedCount
            checkpoint.resultsCount = resultCount
            checkpoint.collectedCount = collectedCount
            checkpoint.exportedCount = exportedCount
            checkpoint.topCount = topResults.count
            checkpoint.durationSeconds = checkpointDurationAtStart + Date().timeIntervalSince(startTime)
            checkpoint.updatedAt = Date()
            checkpoint.completedBatches.append(LocalRunCheckpointBatch(
                startIndex: currentIdx,
                endIndex: chunkEnd,
                seedStart: chunkSeeds[0],
                seedEnd: chunkSeeds[chunkSeeds.count - 1],
                resultsCount: batchResultData.count,
                collectedCount: batchArchive.collectedCount,
                exportedCount: batchArchive.exportedCount
            ))
            try writeResearchJSON(checkpoint, to: checkpointURL, prettyPrinted: true)
            completedBatchKeys.insert(batchKey)
            logger.info(
                "Completed batch \(currentIdx)..<\(chunkEnd) (results=\(resultCount)/\(runCount), collected=\(collectedCount), exported=\(exportedCount))"
            )

            currentIdx = chunkEnd
        }

        if let writer = frameWriter, let error = writer.error {
            throw error
        }
        if let writer = colorFrameWriter, let error = writer.error {
            throw error
        }

        let summary = LocalRunSummary(
            runId: resolvedRunId,
            seedStart: seedStart,
            count: runCount,
            seeds: selectedSeeds,
            steps: parsedSearchConfig.steps,
            durationSeconds: checkpoint.durationSeconds,
            resultsCount: resultCount,
            topCount: topResults.count,
            collectedCount: collectedCount,
            exportedCount: exportedCount,
            framesDir: framesDirPath,
            framesColorDir: framesColorDirPath,
            frameStride: framesEnabled ? frameStride : nil,
            includeWarmupFrames: framesEnabled ? includeWarmupFrames : nil
        )
        try writeResearchJSON(summary, to: summaryURL, prettyPrinted: true)

        logger.info("Local run complete (duration=\(String(format: "%.2f", checkpoint.durationSeconds))s, results=\(resultCount))")

        try promoteLocalRunIfConfigured(
            promotion: promotion,
            runID: resolvedRunId,
            runDirURL: runDirURL,
            logger: logger
        )
    }

}

private struct LocalRunSummary: Codable {
    let runId: String
    let seedStart: Int
    let count: Int
    let seeds: [Int]?
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

private struct LocalRunCheckpoint: Codable {
    let version: Int
    let runId: String
    let inputHash: String
    let seedStart: Int
    let seedStride: Int
    let count: Int
    let batchSize: Int
    let steps: Int
    var completedBatches: [LocalRunCheckpointBatch]
    var resultsCount: Int
    var collectedCount: Int
    var exportedCount: Int
    var topCount: Int
    var durationSeconds: Double
    var updatedAt: Date

    init(
        runId: String,
        inputHash: String,
        seedStart: Int,
        seedStride: Int,
        count: Int,
        batchSize: Int,
        steps: Int
    ) {
        self.version = 1
        self.runId = runId
        self.inputHash = inputHash
        self.seedStart = seedStart
        self.seedStride = seedStride
        self.count = count
        self.batchSize = batchSize
        self.steps = steps
        self.completedBatches = []
        self.resultsCount = 0
        self.collectedCount = 0
        self.exportedCount = 0
        self.topCount = 0
        self.durationSeconds = 0
        self.updatedAt = Date()
    }
}

private struct LocalRunCheckpointBatch: Codable {
    let startIndex: Int
    let endIndex: Int
    let seedStart: Int
    let seedEnd: Int
    let resultsCount: Int
    let collectedCount: Int
    let exportedCount: Int

    var key: String { Self.key(startIndex: startIndex, endIndex: endIndex) }

    static func key(startIndex: Int, endIndex: Int) -> String {
        "\(startIndex)..<\(endIndex)"
    }
}

private struct LocalArchiveAppendResult {
    let collectedCount: Int
    let exportedCount: Int
}

private struct LocalPromotionFailure: Codable {
    let runId: String
    let runDir: String
    let failedAt: Date
    let message: String
    let retryCommand: String
}

private func loadCompletedLocalRunSummary(
    at url: URL,
    runId: String,
    expectedCount: Int
) throws -> LocalRunSummary? {
    guard FileManager.default.fileExists(atPath: url.path) else {
        return nil
    }
    let summary = try JSONDecoder().decode(LocalRunSummary.self, from: Data(contentsOf: url))
    guard summary.runId == runId, summary.resultsCount >= expectedCount else {
        return nil
    }
    return summary
}

private func loadLocalRunCheckpoint(
    at url: URL,
    runId: String,
    inputHash: String,
    seedStart: Int,
    seedStride: Int,
    count: Int,
    batchSize: Int,
    steps: Int
) throws -> LocalRunCheckpoint? {
    guard FileManager.default.fileExists(atPath: url.path) else {
        return nil
    }
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .deferredToDate
    let checkpoint = try decoder.decode(LocalRunCheckpoint.self, from: Data(contentsOf: url))
    guard checkpoint.version == 1,
          checkpoint.runId == runId,
          checkpoint.inputHash == inputHash,
          checkpoint.seedStart == seedStart,
          checkpoint.seedStride == seedStride,
          checkpoint.count == count,
          checkpoint.batchSize == batchSize,
          checkpoint.steps == steps else {
        throw ValidationError("Existing checkpoint.json does not match this local run request.")
    }
    return checkpoint
}

private func loadLocalTopResults(at url: URL) throws -> [SimulationResultData] {
    guard FileManager.default.fileExists(atPath: url.path) else {
        return []
    }
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .deferredToDate
    return try decoder.decode([SimulationResultData].self, from: Data(contentsOf: url))
}

private func validateExistingLocalRunInputs(
    runDir: URL,
    baseConfigData: Data,
    searchConfigData: Data
) throws {
    let existingConfigURL = runDir.appendingPathComponent("config.json")
    let existingSearchURL = runDir.appendingPathComponent("search.json")
    guard FileManager.default.fileExists(atPath: existingConfigURL.path),
          FileManager.default.fileExists(atPath: existingSearchURL.path) else {
        throw ValidationError("Existing completed run is missing config.json or search.json.")
    }
    guard try Data(contentsOf: existingConfigURL) == baseConfigData,
          try Data(contentsOf: existingSearchURL) == searchConfigData else {
        throw ValidationError("Existing completed run inputs do not match this local run request.")
    }
}

private func validateFreshLocalRunDirectory(_ runDir: URL) throws {
    let guardedPaths = [
        "results.jsonl",
        "library/index.jsonl",
        "exports/index.jsonl",
        "checkpoint.json",
    ]
    for relativePath in guardedPaths {
        if FileManager.default.fileExists(atPath: runDir.appendingPathComponent(relativePath).path) {
            throw ValidationError(
                "Run directory already contains \(relativePath) without a compatible checkpoint. Use a new --run-id or retry the exact completed run."
            )
        }
    }
}

private func prepareLocalRunInputFiles(
    runDir: URL,
    baseConfigData: Data,
    searchConfigData: Data,
    isResuming: Bool
) throws {
    if isResuming {
        try validateExistingLocalRunInputs(
            runDir: runDir,
            baseConfigData: baseConfigData,
            searchConfigData: searchConfigData
        )
        return
    }
    try baseConfigData.write(to: runDir.appendingPathComponent("config.json"))
    try searchConfigData.write(to: runDir.appendingPathComponent("search.json"))
}

private func resetLocalRunStreams(
    resultsURL: URL,
    libraryURL: URL?,
    exportIndexURL: URL?
) throws {
    try resetLocalRunStream(resultsURL)
    if let libraryURL {
        try resetLocalRunStream(libraryURL)
    }
    if let exportIndexURL {
        try resetLocalRunStream(exportIndexURL)
    }
}

private func resetLocalRunStream(_ url: URL) throws {
    try FileManager.default.createDirectory(
        at: url.deletingLastPathComponent(),
        withIntermediateDirectories: true
    )
    try Data().write(to: url, options: .atomic)
}

private func openLocalAppendHandle(_ url: URL) throws -> FileHandle {
    try FileManager.default.createDirectory(
        at: url.deletingLastPathComponent(),
        withIntermediateDirectories: true
    )
    if !FileManager.default.fileExists(atPath: url.path) {
        FileManager.default.createFile(atPath: url.path, contents: nil)
    }
    let handle = try FileHandle(forWritingTo: url)
    try handle.seekToEnd()
    return handle
}

private func appendLocalArchiveArtifacts(
    results: [SimulationResultData],
    collectionConfig: CollectionConfig,
    refConfig: LeniaRuntimeConfig,
    baseConfig: LeniaBaseConfig,
    searchConfig: ParsedSearchConfig,
    topologyHash: String,
    ownerId: String,
    runId: String,
    exportRoot: URL,
    libraryHandle: FileHandle?,
    exportIndexHandle: FileHandle?
) throws -> LocalArchiveAppendResult {
    guard collectionConfig.enabled else {
        return LocalArchiveAppendResult(collectedCount: 0, exportedCount: 0)
    }

    let collected = results.filter { shouldCollect($0, config: collectionConfig) }
    guard !collected.isEmpty else {
        return LocalArchiveAppendResult(collectedCount: 0, exportedCount: 0)
    }

    var libraryEntries: [ResearchLibraryEntry] = []
    libraryEntries.reserveCapacity(collected.count)
    var exportItems: [(SavedCreature, SimulationResultData)] = []
    exportItems.reserveCapacity(collected.count)

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
            id: deterministicResearchUUID(localCreatureStableKey(runId: runId, result: result)),
            name: generateCreatureName(runId: runId, result: result),
            ownerId: ownerId,
            result: result,
            initialCondition: initialCondition,
            configHash: topologyHash
        )
        libraryEntries.append(archiveResearchLibraryEntry(
            creature: creature,
            runId: runId,
            configHash: topologyHash
        ))
        exportItems.append((creature, result))
    }

    if let libraryHandle {
        try appendResearchJSONLines(libraryEntries, to: libraryHandle)
    }

    var exportCount = 0
    if collectionConfig.exportEnabled, let exportIndexHandle {
        let exportRecords = try writeLocalReplayExportRecords(
            exportRoot: exportRoot,
            items: exportItems,
            baseConfig: baseConfig,
            searchConfig: searchConfig,
            runId: runId
        )
        try appendResearchJSONLines(exportRecords, to: exportIndexHandle)
        exportCount = exportRecords.count
    }

    return LocalArchiveAppendResult(
        collectedCount: libraryEntries.count,
        exportedCount: exportCount
    )
}

private func writeLocalReplayExportRecords(
    exportRoot: URL,
    items: [(SavedCreature, SimulationResultData)],
    baseConfig: LeniaBaseConfig,
    searchConfig: ParsedSearchConfig,
    runId: String
) throws -> [CreatureExportRecord] {
    guard !items.isEmpty else { return [] }
    try FileManager.default.createDirectory(at: exportRoot, withIntermediateDirectories: true)

    var records: [CreatureExportRecord] = []
    records.reserveCapacity(items.count)
    for (creature, result) in items {
        if let artifacts = try writeReplayExportArtifacts(
            exportRoot: exportRoot,
            baseConfig: baseConfig,
            searchConfig: searchConfig,
            creature: creature,
            runId: runId,
            campaignId: nil,
            score: result.score,
            filtersPassed: result.filtersPassed,
            reason: "auto"
        ) {
            records.append(artifacts.record)
        } else if let record = try existingLocalReplayExportRecord(
            exportRoot: exportRoot,
            creature: creature
        ) {
            records.append(record)
        }
    }
    return records
}

private func existingLocalReplayExportRecord(
    exportRoot: URL,
    creature: SavedCreature
) throws -> CreatureExportRecord? {
    let exportDir = replayExportDirectory(root: exportRoot, creature: creature)
    let metadataURL = exportDir.appendingPathComponent("meta.json")
    guard FileManager.default.fileExists(atPath: metadataURL.path) else {
        return nil
    }
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .deferredToDate
    let metadata = try decodeCreatureExportMetadata(Data(contentsOf: metadataURL), decoder: decoder)
    let baseURL = exportDir.appendingPathComponent("base.json")
    let searchURL = exportDir.appendingPathComponent("search.json")
    return CreatureExportRecord(
        creatureId: metadata.creature.id,
        name: metadata.creature.name,
        ownerId: metadata.creature.ownerId,
        runId: metadata.runId,
        campaignId: metadata.campaignId,
        bundleKind: metadata.bundleKind,
        exportDir: exportDir.path,
        baseConfigPath: FileManager.default.fileExists(atPath: baseURL.path) ? baseURL.path : nil,
        searchConfigPath: FileManager.default.fileExists(atPath: searchURL.path) ? searchURL.path : nil,
        exportedAt: metadata.exportedAt,
        reason: metadata.reason,
        score: metadata.score,
        filtersPassed: metadata.filtersPassed,
        runtimeFamily: metadata.runtimeFamily,
        runtimeCapabilities: metadata.runtimeCapabilities,
        specimenManifest: metadata.specimenManifest
    )
}

private func promoteLocalRunIfConfigured(
    promotion: ArchivePromotionOptions,
    runID: String,
    runDirURL: URL,
    logger: Logger
) throws {
    do {
        let resolvedPromotion = try promoteIfConfigured(
            options: promotion,
            defaultCompendiumPath: try resolveArtifactPath("artifacts/compendium.sqlite", dossier: dossierName),
            dossier: dossierName,
            defaultEnabled: true,
            runDir: runDirURL.path,
            includeResults: true,
            stats: true
        )
        if let compendiumPath = resolvedPromotion.compendiumPath {
            logger.info("Promoted local run into compendium: \(compendiumPath)")
        }
        let failureURL = runDirURL.appendingPathComponent("promotion-error.json")
        if FileManager.default.fileExists(atPath: failureURL.path) {
            try FileManager.default.removeItem(at: failureURL)
        }
    } catch {
        let retryCommand = "LeniaCLI index --run-dir \(runDirURL.path) --include-results"
        try writeResearchJSON(
            LocalPromotionFailure(
                runId: runID,
                runDir: runDirURL.path,
                failedAt: Date(),
                message: String(describing: error),
                retryCommand: retryCommand
            ),
            to: runDirURL.appendingPathComponent("promotion-error.json"),
            prettyPrinted: true
        )
        logger.error("Promotion failed; retry with: \(retryCommand)")
        throw error
    }
}

private func shouldCollect(_ result: SimulationResultData, config: CollectionConfig) -> Bool {
    if config.requireStable && !result.metrics.isStable { return false }
    if config.requireFiltersPassed && !result.filtersPassed { return false }
    if let minScore = config.minScore {
        guard let score = result.score, score >= minScore else { return false }
    }
    return true
}

private func localCreatureStableKey(runId: String, result: SimulationResultData) -> String {
    "\(runId)|local|\(result.seed)|\(result.initSeed)"
}

private func generateCreatureName(runId: String, result: SimulationResultData) -> String {
    let adjectives = ["ancient", "crystal", "ethereal", "flowing", "glowing", "harmonic",
                      "luminous", "mystic", "pulsing", "radiant", "serene", "vibrant"]
    let nouns = ["amoeba", "blob", "cell", "dancer", "entity", "form",
                 "glider", "orbiter", "pattern", "pulse", "spiral", "walker"]
    let digest = stableLocalNameHash(localCreatureStableKey(runId: runId, result: result))
    let adj = adjectives[digest % adjectives.count]
    let noun = nouns[(digest / adjectives.count) % nouns.count]
    let id = String(format: "%04d", result.seed % 10000)
    return "\(adj)-\(noun)-\(id)"
}

private func stableLocalNameHash(_ value: String) -> Int {
    var hash = UInt64(14_695_981_039_346_656_037)
    for byte in value.utf8 {
        hash ^= UInt64(byte)
        hash &*= 1_099_511_628_211
    }
    return Int(hash % UInt64(Int.max))
}
