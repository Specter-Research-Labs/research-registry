import ArgumentParser
import Foundation
import LeniaCore
import Logging

/// Batch-evaluate a FIXED corpus of genotypes through metal-full under one condition, the
/// measurement primitive for the functional morphospace. Each line of the corpus JSONL is a
/// rule; they run together in batched Metal rollouts and every metric is written to
/// results.jsonl. The condition (an ablation intervention, a chemotaxis/obstacle environment)
/// lives in the base config, so the same command runs every assay.
struct EvaluateCommand: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "evaluate",
        abstract: "Batch-evaluate a fixed corpus of genotypes under one condition"
    )

    @Option(name: .long, help: "Base config.json (the universe plus any interventions/environment)")
    var config: String

    @Option(name: .long, help: "Search config.json (steps, metrics, filters)")
    var search: String

    @Option(name: .long, help: "Corpus JSONL: one {\"params\": {R,r,b,w,a,m,s,h}, \"init_seed\": N} per line; init_seed is optional")
    var corpus: String

    @Option(name: .long, help: "Default init seed for corpus rows that omit their own init_seed")
    var initSeed: Int = 0

    @Option(name: .shortAndLong, help: "Output directory for results.jsonl")
    var output: String

    @OptionGroup
    var logOptions: LogOptions

    func run() async throws {
        let runId = resolveRunID(prefix: "evaluate", logOptions: logOptions)
        let outputRoot = try resolvePath(output, dossier: dossierName)
        let runDir = makeRunOutputDirectory(outputRoot: outputRoot, runID: runId)
        let logging = try bootstrapRunLogging(
            runID: runId, role: "evaluate", loggerLabel: "LeniaSwarm.Evaluate",
            logStem: "evaluate", outputForLogs: outputRoot, logOptions: logOptions,
            dossier: dossierName, fallbackOutputLogDir: true
        )
        let logger = logging.logger
        logger.info("Output: \(runDir.path)")

        let configPath = try resolvePath(config, dossier: dossierName)
        let searchPath = try resolvePath(search, dossier: dossierName)
        let corpusPath = try resolvePath(corpus, dossier: dossierName)
        let sourceBaseConfigData = try Data(contentsOf: URL(fileURLWithPath: configPath))
        let searchConfigData = try Data(contentsOf: URL(fileURLWithPath: searchPath))
        let parsedSearch = try JSONDecoder().decode(ParsedSearchConfig.self, from: searchConfigData)
        let baseOverrides = parsedSearch.overridesAsDict()
        let effectiveBaseData = try baseConfigDataByApplyingOverrides(sourceBaseConfigData, overrides: baseOverrides)
        let effectiveBaseConfig = try JSONDecoder().decode(LeniaBaseConfig.self, from: effectiveBaseData)
        let backend = try resolveMetalFirstSearchBackend(requestValue: "metal-full", baseConfig: effectiveBaseConfig)
        let baseConfigData = try baseConfigDataBySettingBackend(sourceBaseConfigData, backend: backend)

        let corpusText = try String(contentsOf: URL(fileURLWithPath: corpusPath), encoding: .utf8)
        let decoder = JSONDecoder()
        var rules: [ResolvedParams] = []
        var rowSeeds: [Int] = []
        for line in corpusText.split(separator: "\n") {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.isEmpty { continue }
            let row = try decoder.decode(CorpusRow.self, from: Data(trimmed.utf8))
            rules.append(row.params.resolved())
            rowSeeds.append(row.initSeed ?? initSeed)
        }
        if rules.isEmpty {
            throw ValidationError("corpus contains no genotypes")
        }
        logger.info("Loaded \(rules.count) genotypes from corpus")

        let simSearch = parsedSearch.toSearchConfig()
        try FileManager.default.createDirectory(at: runDir, withIntermediateDirectories: true)
        let resultsURL = runDir.appendingPathComponent("results.jsonl")
        try Data().write(to: resultsURL, options: .atomic)
        let handle = try FileHandle(forWritingTo: resultsURL)
        defer { try? handle.close() }

        var overrides = baseOverrides
        overrides["run.steps"] = parsedSearch.steps
        let runtimeConfig = try loadRuntimeConfig(from: baseConfigData, overrides: overrides)
        let engine = SearchEngine(runtimeConfig: runtimeConfig)
        let batchSize = max(1, parsedSearch.batchSize)
        let start = Date()
        var idx = 0
        while idx < rules.count {
            let end = min(idx + batchSize, rules.count)
            let chunk = Array(rules[idx..<end])
            let seeds = Array(rowSeeds[idx..<end])

            let batchResults = engine.runBatch(
                seeds: seeds,
                initSeedOffset: 0,
                searchConfig: simSearch,
                explicitParamsBatch: chunk
            )
            let data = batchResults.map {
                materializeSearchResultData(
                    $0, backend: runtimeConfig.backend.rawValue,
                    implementation: runtimeConfig.implementation, searchConfig: simSearch
                )
            }
            try appendResearchJSONLines(data, to: handle)
            try handle.synchronize()
            idx = end
            logger.info("Evaluated \(idx)/\(rules.count)")
        }
        logger.info(
            "Done (\(rules.count) creatures, \(String(format: "%.2f", Date().timeIntervalSince(start)))s) -> \(resultsURL.path)"
        )
    }
}

private struct CorpusRow: Decodable {
    let params: CorpusParams
    let initSeed: Int?

    enum CodingKeys: String, CodingKey {
        case params
        case initSeed = "init_seed"
    }
}

private struct CorpusParams: Decodable {
    let R: Float
    let r: [Float]
    let b: [[Float]]
    let w: [[Float]]
    let a: [[Float]]
    let m: [Float]
    let s: [Float]
    let h: [Float]

    func resolved() -> ResolvedParams {
        ResolvedParams(r: r, b: b, w: w, a: a, m: m, s: s, h: h, R: R, seed: 0)
    }
}
