import ArgumentParser
import CryptoKit
import Foundation
import LeniaCore
import Logging

/// Evaluate an identity-preserving corpus under one named experimental condition.
struct EvaluateCommand: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "evaluate",
        abstract: "Batch-evaluate a fixed corpus under one named condition"
    )

    @Option(name: .long, help: "Base config.json (the universe plus interventions/environment)")
    var config: String

    @Option(name: .long, help: "Search config.json (steps, metrics, filters)")
    var search: String

    @Option(
        name: .long,
        help: "Corpus JSONL with a stable id, params, optional init_seed, and optional initial_state per row"
    )
    var corpus: String

    @Option(name: .long, help: "Stable identifier for this assay condition")
    var conditionId: String

    @Option(name: .long, help: "Default init seed for corpus rows that omit init_seed")
    var initSeed: Int = 0

    @Option(name: .shortAndLong, help: "Output directory for the reproducible evaluation bundle")
    var output: String

    @OptionGroup
    var logOptions: LogOptions

    func run() async throws {
        let resolvedConditionId = conditionId.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !resolvedConditionId.isEmpty else {
            throw ValidationError("--condition-id must not be empty")
        }

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
        let corpusData = try Data(contentsOf: URL(fileURLWithPath: corpusPath))

        let parsedSearch = try JSONDecoder().decode(ParsedSearchConfig.self, from: searchConfigData)
        let baseOverrides = parsedSearch.overridesAsDict()
        let effectiveBaseData = try baseConfigDataByApplyingOverrides(sourceBaseConfigData, overrides: baseOverrides)
        let effectiveBaseConfig = try JSONDecoder().decode(LeniaBaseConfig.self, from: effectiveBaseData)
        let backend = try resolveMetalFirstSearchBackend(requestValue: "metal-full", baseConfig: effectiveBaseConfig)

        let entries = try decodeEvaluationCorpus(corpusData, defaultInitSeed: initSeed)
        var executionOverrides = baseOverrides
        executionOverrides["run.steps"] = parsedSearch.steps
        executionOverrides["backend"] = backend.rawValue
        let executionConfigData = try baseConfigDataByApplyingOverrides(
            sourceBaseConfigData,
            overrides: executionOverrides
        )
        let runtimeConfig = try loadRuntimeConfig(from: executionConfigData)
        try validateEvaluationCorpus(entries, runtimeConfig: runtimeConfig)

        logger.info("Loaded \(entries.count) identified corpus rows")
        try FileManager.default.createDirectory(at: runDir, withIntermediateDirectories: true)
        try sourceBaseConfigData.write(to: runDir.appendingPathComponent("config.json"), options: .atomic)
        try searchConfigData.write(to: runDir.appendingPathComponent("search.json"), options: .atomic)
        try corpusData.write(to: runDir.appendingPathComponent("corpus.jsonl"), options: .atomic)
        try executionConfigData.write(
            to: runDir.appendingPathComponent("effective-config.json"),
            options: .atomic
        )

        let resultsURL = runDir.appendingPathComponent("results.jsonl")
        try Data().write(to: resultsURL, options: .atomic)
        let handle = try FileHandle(forWritingTo: resultsURL)
        defer { try? handle.close() }

        let simSearch = parsedSearch.toSearchConfig()
        let engine = SearchEngine(runtimeConfig: runtimeConfig)
        let batchSize = max(1, parsedSearch.batchSize)
        let startedAt = Date()
        var resultCount = 0
        var index = 0
        while index < entries.count {
            let end = min(index + batchSize, entries.count)
            let chunk = Array(entries[index..<end])
            let batchResults = engine.runBatch(
                seeds: chunk.map(\.initSeed),
                initSeedOffset: 0,
                searchConfig: simSearch,
                explicitParamsBatch: chunk.map(\.params),
                explicitInitialStateBatch: chunk.map(\.statePatch)
            )
            guard batchResults.count == chunk.count else {
                throw ValidationError(
                    "evaluation returned \(batchResults.count) results for \(chunk.count) corpus rows"
                )
            }
            let records = zip(chunk, batchResults).map { entry, result in
                FunctionalEvaluationRecord(
                    corpusId: entry.id,
                    groupId: entry.groupId,
                    conditionId: resolvedConditionId,
                    corpusRowSha256: entry.rowSha256,
                    result: materializeSearchResultData(
                        result,
                        backend: runtimeConfig.backend.rawValue,
                        implementation: runtimeConfig.implementation,
                        searchConfig: simSearch
                    )
                )
            }
            try appendResearchJSONLines(records, to: handle)
            resultCount += records.count
            index = end
            logger.info("Evaluated \(index)/\(entries.count)")
        }
        try handle.synchronize()

        let finishedAt = Date()
        let summary = FunctionalEvaluationSummary(
            runId: runId,
            conditionId: resolvedConditionId,
            startedAt: startedAt,
            finishedAt: finishedAt,
            durationSeconds: finishedAt.timeIntervalSince(startedAt),
            corpusCount: entries.count,
            resultCount: resultCount,
            batchSize: batchSize,
            batchCount: (entries.count + batchSize - 1) / batchSize,
            backend: runtimeConfig.backend.rawValue,
            implementation: runtimeConfig.implementation.mode,
            inputHash: researchConfigHash([
                ("config", sourceBaseConfigData),
                ("search", searchConfigData),
                ("corpus", corpusData),
            ]),
            inputHashes: FunctionalEvaluationInputHashes(
                configSha256: evaluationSHA256(sourceBaseConfigData),
                searchSha256: evaluationSHA256(searchConfigData),
                corpusSha256: evaluationSHA256(corpusData),
                executionConfigSha256: evaluationSHA256(executionConfigData)
            )
        )
        try writeResearchJSON(summary, to: runDir.appendingPathComponent("summary.json"), prettyPrinted: true)
        logger.info(
            "Done (\(resultCount) creatures, \(String(format: "%.2f", summary.durationSeconds))s) -> \(resultsURL.path)"
        )
    }
}

struct FunctionalEvaluationRecord: Codable {
    let schemaVersion = "functional-evaluation-v2"
    let corpusId: String
    let groupId: String?
    let conditionId: String
    let corpusRowSha256: String
    let result: SimulationResultData

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case corpusId = "corpus_id"
        case groupId = "group_id"
        case conditionId = "condition_id"
        case corpusRowSha256 = "corpus_row_sha256"
        case result
    }
}

struct FunctionalEvaluationInputHashes: Codable {
    let configSha256: String
    let searchSha256: String
    let corpusSha256: String
    let executionConfigSha256: String

    enum CodingKeys: String, CodingKey {
        case configSha256 = "config_sha256"
        case searchSha256 = "search_sha256"
        case corpusSha256 = "corpus_sha256"
        case executionConfigSha256 = "execution_config_sha256"
    }
}

struct FunctionalEvaluationSummary: Codable {
    let schemaVersion = "functional-evaluation-summary-v2"
    let runId: String
    let conditionId: String
    let startedAt: Date
    let finishedAt: Date
    let durationSeconds: Double
    let corpusCount: Int
    let resultCount: Int
    let batchSize: Int
    let batchCount: Int
    let backend: String
    let implementation: String
    let inputHash: String
    let inputHashes: FunctionalEvaluationInputHashes

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case runId = "run_id"
        case conditionId = "condition_id"
        case startedAt = "started_at"
        case finishedAt = "finished_at"
        case durationSeconds = "duration_seconds"
        case corpusCount = "corpus_count"
        case resultCount = "result_count"
        case batchSize = "batch_size"
        case batchCount = "batch_count"
        case backend
        case implementation
        case inputHash = "input_hash"
        case inputHashes = "input_hashes"
    }
}

struct EvaluationCorpusEntry {
    let id: String
    let groupId: String?
    let params: ResolvedParams
    let initSeed: Int
    let statePatch: InitStatePatchConfig?
    let rowSha256: String
}

func decodeEvaluationCorpus(_ data: Data, defaultInitSeed: Int) throws -> [EvaluationCorpusEntry] {
    guard let text = String(data: data, encoding: .utf8) else {
        throw ValidationError("corpus must be UTF-8 JSONL")
    }

    let decoder = JSONDecoder()
    var ids = Set<String>()
    var entries: [EvaluationCorpusEntry] = []
    for (lineIndex, line) in text.split(separator: "\n", omittingEmptySubsequences: false).enumerated() {
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { continue }
        let rowData = Data(trimmed.utf8)
        let row: CorpusRow
        do {
            row = try decoder.decode(CorpusRow.self, from: rowData)
        } catch {
            throw ValidationError("corpus line \(lineIndex + 1) is invalid: \(error)")
        }
        let id = row.id.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !id.isEmpty else {
            throw ValidationError("corpus line \(lineIndex + 1) has an empty id")
        }
        guard ids.insert(id).inserted else {
            throw ValidationError("corpus id '\(id)' is duplicated")
        }
        let trimmedGroupId = row.groupId?.trimmingCharacters(in: .whitespacesAndNewlines)
        entries.append(EvaluationCorpusEntry(
            id: id,
            groupId: trimmedGroupId?.isEmpty == false ? trimmedGroupId : nil,
            params: row.params.resolved(),
            initSeed: row.initSeed ?? defaultInitSeed,
            statePatch: row.initialState?.statePatch,
            rowSha256: evaluationSHA256(rowData)
        ))
    }
    guard !entries.isEmpty else {
        throw ValidationError("corpus contains no rows")
    }
    return entries
}

func validateEvaluationCorpus(
    _ entries: [EvaluationCorpusEntry],
    runtimeConfig: LeniaRuntimeConfig
) throws {
    for entry in entries {
        let params = entry.params
        guard params.r.count == runtimeConfig.nbK,
              params.m.count == runtimeConfig.nbK,
              params.s.count == runtimeConfig.nbK,
              params.h.count == runtimeConfig.nbK,
              params.b.count == runtimeConfig.nbK,
              params.w.count == runtimeConfig.nbK,
              params.a.count == runtimeConfig.nbK else {
            throw ValidationError(
                "corpus id '\(entry.id)' parameter arrays must have nbK=\(runtimeConfig.nbK) entries"
            )
        }
        guard params.R.isFinite, params.R > 0 else {
            throw ValidationError("corpus id '\(entry.id)' params.R must be finite and > 0")
        }
        for kernel in 0..<runtimeConfig.nbK {
            guard !params.b[kernel].isEmpty,
                  params.w[kernel].count == params.b[kernel].count,
                  params.a[kernel].count == params.b[kernel].count else {
                throw ValidationError(
                    "corpus id '\(entry.id)' params.b/w/a kernel \(kernel) lengths must match"
                )
            }
            guard params.s[kernel].isFinite, params.s[kernel] > 0 else {
                throw ValidationError(
                    "corpus id '\(entry.id)' params.s[\(kernel)] must be finite and > 0"
                )
            }
            if !runtimeConfig.implementation.kernelProfile.hasPrefix("qd24_") {
                guard params.w[kernel].allSatisfy({ $0.isFinite && $0 > 0 }) else {
                    throw ValidationError(
                        "corpus id '\(entry.id)' params.w[\(kernel)] values must be finite and > 0"
                    )
                }
            }
        }
        let scalarValues = params.r + params.m + params.s + params.h
            + params.b.flatMap { $0 } + params.w.flatMap { $0 } + params.a.flatMap { $0 }
        guard scalarValues.allSatisfy(\.isFinite) else {
            throw ValidationError("corpus id '\(entry.id)' parameters must all be finite")
        }

        guard let patch = entry.statePatch else { continue }
        guard patch.center.count == 2 else {
            throw ValidationError("corpus id '\(entry.id)' initial_state.center must have two coordinates")
        }
        guard patch.width > 0, patch.height > 0 else {
            throw ValidationError("corpus id '\(entry.id)' initial_state dimensions must be positive")
        }
        guard patch.channels == runtimeConfig.channels else {
            throw ValidationError(
                "corpus id '\(entry.id)' initial_state.channels must equal \(runtimeConfig.channels)"
            )
        }
        let (cellCount, cellOverflow) = patch.width.multipliedReportingOverflow(by: patch.height)
        let (expectedValueCount, channelOverflow) = cellCount.multipliedReportingOverflow(by: patch.channels)
        guard !cellOverflow, !channelOverflow, patch.valueCount == expectedValueCount else {
            throw ValidationError(
                "corpus id '\(entry.id)' initial_state.values must contain width*height*channels entries"
            )
        }
        let cx = patch.center[0]
        let cy = patch.center[1]
        let x0 = cx - patch.width / 2
        let x1 = cx + (patch.width - patch.width / 2)
        let y0 = cy - patch.height / 2
        let y1 = cy + (patch.height - patch.height / 2)
        guard x0 >= 0, y0 >= 0, x1 <= runtimeConfig.sx, y1 <= runtimeConfig.sy else {
            throw ValidationError(
                "corpus id '\(entry.id)' initial_state is out of bounds for \(runtimeConfig.sx)x\(runtimeConfig.sy)"
            )
        }
    }
}

private struct CorpusRow: Decodable {
    let id: String
    let groupId: String?
    let params: CorpusParams
    let initSeed: Int?
    let initialState: CorpusInitialState?

    enum CodingKeys: String, CodingKey {
        case id
        case groupId = "group_id"
        case params
        case initSeed = "init_seed"
        case initialState = "initial_state"
    }
}

private struct CorpusInitialState: Decodable {
    let center: [Int]
    let width: Int
    let height: Int
    let channels: Int
    let values: [Float]

    var statePatch: InitStatePatchConfig {
        InitStatePatchConfig(
            center: center,
            width: width,
            height: height,
            channels: channels,
            values: values
        )
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

private func evaluationSHA256(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}
