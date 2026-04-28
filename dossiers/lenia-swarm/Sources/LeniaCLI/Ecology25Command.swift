import ArgumentParser
import Foundation
import LeniaCore
import Logging

struct Ecology25Command: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "ecology-2025",
        abstract: "Run the 2025 Flow-Lenia intrinsic-evolution ecology experiments"
    )

    @Option(name: .long, help: "Path to the paper-locked config directory")
    var configDir: String

    @Option(name: .shortAndLong, help: "Output directory for run artifacts")
    var output: String?

    @Option(name: .long, help: "Path to library/index.jsonl, exports/index.jsonl, or patches.jsonl used to seed curated ecology mixtures")
    var seedLibrary: String?

    @Option(name: .long, help: "Optional qd-2024 config directory when the seed library comes from qd-2024 and pattern assets are missing")
    var seedQDConfigDir: String?

    @Option(name: .long, parsing: .upToNextOption, help: "QD cell ids to use when the seed library comes from qd-2024")
    var seedCell: [Int] = []

    @Option(name: .long, help: "Requested backend: auto|metal-full|mlx")
    var backend: String = "auto"

    @Option(name: .long, help: "Override reintegration.border for ecology runs: wall|torus")
    var border: String?

    @Option(name: .long, help: "Override parameter_embedding.mix for ecology runs")
    var parameterMix: String?

    @Option(name: .long, help: "Override parameter_embedding.mix_seed for ecology runs")
    var parameterMixSeed: Int?

    @OptionGroup
    var seedSelection: ResearchSeedSelectionOptions

    @Flag(name: .long, help: "Validate configs and exit without running")
    var validateOnly: Bool = false

    @Flag(name: .long, help: "Allow short diagnostic ecology configs that preserve equations but relax paper-scale run sizes and topology.")
    var diagnosticConfig: Bool = false

    @Flag(name: .long, help: "Evaluate each selected seed as its own exact ecology run instead of placing all selected seeds in one arena.")
    var evaluateSeedsIndividually: Bool = false

    @OptionGroup
    var logOptions: LogOptions

    func run() async throws {
        let resolvedRunId = resolveRunID(prefix: "ecology-2025", logOptions: logOptions)
        let resolvedConfigDir = try resolvePath(configDir, dossier: dossierName)
        let resolvedOutput = try output.map { try resolvePath($0, dossier: dossierName) }
        let resolvedSeedLibrary = try seedLibrary.map { try resolveArtifactPath($0, dossier: dossierName) }
        let resolvedQDConfigDir = try seedQDConfigDir.map { try resolvePath($0, dossier: dossierName) }
        let logging = try bootstrapRunLogging(
            runID: resolvedRunId,
            role: "ecology-2025",
            loggerLabel: "LeniaSwarm.Ecology2025",
            logStem: "ecology-2025",
            outputForLogs: resolvedOutput,
            logOptions: logOptions,
            dossier: dossierName
        )
        let logger = logging.logger
        let bundle = try loadFlowLeniaEcology2025ConfigBundle(
            configDirectory: URL(fileURLWithPath: resolvedConfigDir, isDirectory: true),
            strictPaperInvariants: !diagnosticConfig
        )
        let backendlessRuntimeOverrides = try ecologyRuntimeOverrides(
            backend: nil,
            border: border,
            parameterMix: parameterMix,
            parameterMixSeed: parameterMixSeed
        )
        let resolvedBackend = try resolveEcology25Backend(
            requestValue: backend,
            bundle: bundle,
            runtimeOverrides: backendlessRuntimeOverrides
        )
        let runtimeOverrides = try ecologyRuntimeOverrides(
            backend: resolvedBackend.rawValue,
            border: border,
            parameterMix: parameterMix,
            parameterMixSeed: parameterMixSeed
        )
        let ecologySeeds: [ResearchSeedPatch]
        if let resolvedSeedLibrary {
            let selection = try seedSelection.resolvedSelection()
            ecologySeeds = try loadResearchSeedPatches(
                libraryURL: URL(fileURLWithPath: resolvedSeedLibrary),
                qdConfigDirectoryOverride: resolvedQDConfigDir.map { URL(fileURLWithPath: $0, isDirectory: true) },
                cells: seedCell.isEmpty ? nil : seedCell,
                selection: selection
            )
            guard !ecologySeeds.isEmpty else {
                throw ValidationError("No research seeds resolved from \(resolvedSeedLibrary).")
            }
            logger.info("Using \(ecologySeeds.count) curated seeds to seed ecology mixtures")
        } else {
            ecologySeeds = []
        }
        if validateOnly {
            try validateFlowLeniaEcology2025RuntimeOverrides(
                bundle: bundle,
                runtimeOverrides: runtimeOverrides
            )
            logger.info("Flow-Lenia Ecology 2025 configs validated successfully (backend=\(resolvedBackend.rawValue))")
            return
        }
        guard let resolvedOutput else {
            throw ValidationError("--output is required unless --validate-only is set.")
        }
        if evaluateSeedsIndividually {
            guard !ecologySeeds.isEmpty else {
                throw ValidationError("--evaluate-seeds-individually requires --seed-library.")
            }
            try runExactSeedEvaluations(
                seeds: ecologySeeds,
                bundle: bundle,
                outputDirectory: URL(fileURLWithPath: resolvedOutput, isDirectory: true),
                runtimeOverrides: runtimeOverrides,
                logger: logger
            )
            return
        }
        let runner = FlowLeniaEcology2025Runner(
            configs: bundle,
            logger: logger,
            curatedSeeds: ecologySeeds,
            runtimeOverrides: runtimeOverrides
        )
        _ = try runner.run(outputDirectory: URL(fileURLWithPath: resolvedOutput, isDirectory: true))
    }
}

private struct Ecology25SeedEvaluationRecord: Codable {
    let sourceID: String
    let name: String
    let runID: String?
    let campaignID: String?
    let score: Float?
    let outputDirectory: String
    let totalRuns: Int
    let bestFinalNonNeutralActivity: Float
    let bestFinalPresenceActivity: Float
    let bestFinalDiversity: Float
    let bestFinalSpeciesCount: Int
    let bestFinalMass: Float

    enum CodingKeys: String, CodingKey {
        case sourceID = "source_id"
        case name
        case runID = "run_id"
        case campaignID = "campaign_id"
        case score
        case outputDirectory = "output_directory"
        case totalRuns = "total_runs"
        case bestFinalNonNeutralActivity = "best_final_non_neutral_activity"
        case bestFinalPresenceActivity = "best_final_presence_activity"
        case bestFinalDiversity = "best_final_diversity"
        case bestFinalSpeciesCount = "best_final_species_count"
        case bestFinalMass = "best_final_mass"
    }
}

private func runExactSeedEvaluations(
    seeds: [ResearchSeedPatch],
    bundle: FlowLeniaEcology2025ConfigBundle,
    outputDirectory: URL,
    runtimeOverrides: FlowLeniaEcology2025RuntimeOverrides,
    logger: Logger
) throws {
    let root = outputDirectory.appendingPathComponent("seed-evaluations", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    var records: [Ecology25SeedEvaluationRecord] = []
    records.reserveCapacity(seeds.count)

    for (index, seed) in seeds.enumerated() {
        let seedDirectory = root.appendingPathComponent(
            "\(String(format: "%04d", index))-\(ecology25PathComponent(seed.sourceID))",
            isDirectory: true
        )
        logger.info("Flow-Lenia Ecology 2025 exact seed evaluation \(index + 1)/\(seeds.count): \(seed.sourceID)")
        let runner = FlowLeniaEcology2025Runner(
            configs: bundle,
            logger: logger,
            curatedSeeds: [seed],
            runtimeOverrides: runtimeOverrides
        )
        let summary = try runner.run(outputDirectory: seedDirectory)
        records.append(ecology25SeedEvaluationRecord(seed: seed, outputDirectory: seedDirectory, summary: summary))
    }

    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    let indexURL = outputDirectory.appendingPathComponent("seed-evaluations/index.jsonl")
    FileManager.default.createFile(atPath: indexURL.path, contents: nil)
    let handle = try FileHandle(forWritingTo: indexURL)
    defer { try? handle.close() }
    for record in records.sorted(by: ecology25SeedEvaluationSort) {
        handle.write(try encoder.encode(record))
        handle.write(Data([0x0A]))
    }
}

private func ecology25SeedEvaluationRecord(
    seed: ResearchSeedPatch,
    outputDirectory: URL,
    summary: FlowLeniaEcology2025Summary
) -> Ecology25SeedEvaluationRecord {
    let best = summary.runs.max { lhs, rhs in
        if lhs.finalNonNeutralActivity == rhs.finalNonNeutralActivity {
            return lhs.finalPresenceActivity < rhs.finalPresenceActivity
        }
        return lhs.finalNonNeutralActivity < rhs.finalNonNeutralActivity
    }
    return Ecology25SeedEvaluationRecord(
        sourceID: seed.sourceID,
        name: seed.name,
        runID: seed.runID,
        campaignID: seed.campaignID,
        score: seed.score,
        outputDirectory: outputDirectory.path,
        totalRuns: summary.totalRuns,
        bestFinalNonNeutralActivity: best?.finalNonNeutralActivity ?? 0,
        bestFinalPresenceActivity: best?.finalPresenceActivity ?? 0,
        bestFinalDiversity: best?.finalDiversity ?? 0,
        bestFinalSpeciesCount: best?.finalSpeciesCount ?? 0,
        bestFinalMass: best?.finalMass ?? 0
    )
}

private func ecology25SeedEvaluationSort(_ lhs: Ecology25SeedEvaluationRecord, _ rhs: Ecology25SeedEvaluationRecord) -> Bool {
    if lhs.bestFinalNonNeutralActivity == rhs.bestFinalNonNeutralActivity {
        if lhs.bestFinalPresenceActivity == rhs.bestFinalPresenceActivity {
            return lhs.sourceID < rhs.sourceID
        }
        return lhs.bestFinalPresenceActivity > rhs.bestFinalPresenceActivity
    }
    return lhs.bestFinalNonNeutralActivity > rhs.bestFinalNonNeutralActivity
}

private func ecology25PathComponent(_ raw: String) -> String {
    let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_."))
    let scalars = raw.unicodeScalars.map { scalar -> Character in
        allowed.contains(scalar) ? Character(String(scalar)) : "-"
    }
    let component = String(scalars).trimmingCharacters(in: CharacterSet(charactersIn: "-_."))
    return component.isEmpty ? "seed" : String(component.prefix(80))
}

private func ecologyRuntimeOverrides(
    backend: String?,
    border: String?,
    parameterMix: String?,
    parameterMixSeed: Int?
) throws -> FlowLeniaEcology2025RuntimeOverrides {
    var resolvedBackend: String?
    var resolvedBorder: String?
    var resolvedParameterMix: String?
    var clearsParameterMixSeed = false
    if let backend = normalized(backend) {
        let resolved = try FlowLeniaComputeBackend(configValue: backend)
        resolvedBackend = resolved.rawValue
    }
    if let border = normalized(border) {
        let normalizedBorder = border.lowercased()
        guard normalizedBorder == "wall" || normalizedBorder == "torus" else {
            throw ValidationError("Invalid --border '\(border)'. Expected wall or torus.")
        }
        resolvedBorder = normalizedBorder
    }
    if let parameterMix = normalized(parameterMix) {
        let normalizedMix = parameterMix.lowercased()
        let allowedMixes: Set<String> = ["avg", "stoch", "softmax", "stoch_gene_wise", "energy", "argmax"]
        guard allowedMixes.contains(normalizedMix) else {
            throw ValidationError("Invalid --parameter-mix '\(parameterMix)'. Expected one of: \(allowedMixes.sorted().joined(separator: ", ")).")
        }
        resolvedParameterMix = normalizedMix
        if parameterMixSeed == nil, normalizedMix == "avg" || normalizedMix == "argmax" {
            clearsParameterMixSeed = true
        }
    }
    return FlowLeniaEcology2025RuntimeOverrides(
        backend: resolvedBackend,
        border: resolvedBorder,
        parameterMix: resolvedParameterMix,
        parameterMixSeed: parameterMixSeed,
        clearsParameterMixSeed: clearsParameterMixSeed
    )
}

private func resolveEcology25Backend(
    requestValue: String,
    bundle: FlowLeniaEcology2025ConfigBundle,
    runtimeOverrides: FlowLeniaEcology2025RuntimeOverrides
) throws -> FlowLeniaComputeBackend {
    let overrides = runtimeOverrides.runtimeConfigOverrides()
    var runtimes: [LeniaRuntimeConfig] = []
    runtimes.reserveCapacity(bundle.variants.count)
    for variant in bundle.variants {
        let baseURL = bundle.configDirectory.appendingPathComponent(variant.baseConfig)
        let baseData = try Data(contentsOf: baseURL)
        runtimes.append(try loadRuntimeConfig(from: baseData, overrides: overrides))
    }
    return try resolveMetalFirstSimulatorBackend(requestValue: requestValue, runtimeConfigs: runtimes)
}
