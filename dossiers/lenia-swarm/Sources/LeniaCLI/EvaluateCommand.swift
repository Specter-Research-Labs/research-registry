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

struct CorpusRow: Decodable {
    let specimenId: String?
    let lifeId: String?
    let family: String?
    let mapId: String?
    let ruleId: String?
    let params: CorpusParams
    let initialCondition: InitConfig?
    let initSeed: Int?

    enum CodingKeys: String, CodingKey {
        case specimenId = "specimen_id"
        case lifeId = "life_id"
        case family
        case mapId = "map_id"
        case ruleId = "rule_id"
        case params
        case genotypeJSON = "genotype_json"
        case initialConditionJSON = "initial_condition_json"
        case initSeed = "init_seed"
        case replay
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        specimenId = try container.decodeIfPresent(String.self, forKey: .specimenId)
        lifeId = try container.decodeIfPresent(String.self, forKey: .lifeId)
        family = try container.decodeIfPresent(String.self, forKey: .family)
        mapId = try container.decodeIfPresent(String.self, forKey: .mapId)
        ruleId = try container.decodeIfPresent(String.self, forKey: .ruleId)
        let replay = try container.decodeIfPresent(CorpusReplayPayload.self, forKey: .replay)
        if let directParams = try container.decodeIfPresent(CorpusParams.self, forKey: .params) {
            params = directParams
        } else if let embeddedParams = try Self.decodeOptionalEmbedded(
            CorpusParams.self,
            key: .genotypeJSON,
            container: container
        ) {
            params = embeddedParams
        } else if let replay {
            params = replay.genotype
        } else {
            throw DecodingError.keyNotFound(
                CodingKeys.params,
                DecodingError.Context(
                    codingPath: container.codingPath,
                    debugDescription: "Expected params, genotype_json, or replay.genotype"
                )
            )
        }
        initialCondition = try Self.decodeOptionalEmbedded(
            InitConfig.self,
            key: .initialConditionJSON,
            container: container
        ) ?? replay?.initialCondition
        let explicitSeed = try container.decodeIfPresent(Int.self, forKey: .initSeed)
        if let explicitSeed, let initialCondition, explicitSeed != initialCondition.seed {
            throw DecodingError.dataCorruptedError(
                forKey: .initSeed,
                in: container,
                debugDescription: "init_seed does not match initial_condition_json.seed"
            )
        }
        initSeed = explicitSeed ?? initialCondition?.seed
    }

    private static func decodeOptionalEmbedded<T: Decodable>(
        _ type: T.Type,
        key: CodingKeys,
        container: KeyedDecodingContainer<CodingKeys>
    ) throws -> T? {
        if let value = try? container.decodeIfPresent(T.self, forKey: key) {
            return value
        }
        guard let JSON = try container.decodeIfPresent(String.self, forKey: key) else {
            return nil
        }
        return try JSONDecoder().decode(T.self, from: Data(JSON.utf8))
    }
}

private struct CorpusReplayPayload: Decodable {
    let genotype: CorpusParams
    let initialCondition: InitConfig

    enum CodingKeys: String, CodingKey {
        case genotype
        case initialCondition = "initial_condition"
    }
}

struct CorpusParams: Decodable {
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

    func explicitOverrides(seed: Int) -> [String: Any] {
        [
            "params.mode": "explicit",
            "params.seed": seed,
            "params.r": r.map(Double.init),
            "params.b": b.map { $0.map(Double.init) },
            "params.w": w.map { $0.map(Double.init) },
            "params.a": a.map { $0.map(Double.init) },
            "params.m": m.map(Double.init),
            "params.s": s.map(Double.init),
            "params.h": h.map(Double.init),
            "params.R": Double(R),
        ]
    }
}
