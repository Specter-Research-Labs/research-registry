import ArgumentParser
import DistributedCluster
import Foundation
import LeniaCore
import Logging
import MLX

let dossierName = "lenia-swarm"

func resolvePath(_ path: String, dossier: String) throws -> String {
    try resolveRuntimeAwarePath(path, dossier: dossier)
}

func resolveArtifactPath(_ path: String, dossier: String) throws -> String {
    try resolveRuntimeAwareArtifactPath(path, dossier: dossier)
}

func resolveLogBase(explicit: String?, dossier: String, output: String? = nil) throws -> String? {
    try resolveRuntimeAwareLogBase(explicit: explicit, dossier: dossier, output: output)
}

func normalized(_ value: String?) -> String? {
    guard let value else { return nil }
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
}

struct LogOptions: ParsableArguments {
    @Option(name: .long, help: "Log level: trace|debug|info|notice|warning|error|critical")
    var logLevel: String = "info"

    @Option(name: .long, help: "Run id for log/metrics correlation")
    var runId: String?

    @Option(name: .long, help: "Directory for JSONL logs/metrics")
    var logDir: String?

    @Flag(name: .long, help: "Disable console logging")
    var noLogConsole: Bool = false

    func resolvedLogLevel() throws -> Logger.Level {
        switch logLevel.lowercased() {
        case "trace":
            return .trace
        case "debug":
            return .debug
        case "info":
            return .info
        case "notice":
            return .notice
        case "warning":
            return .warning
        case "error":
            return .error
        case "critical":
            return .critical
        default:
            throw ValidationError("Invalid log level: \(logLevel)")
        }
    }
}

struct ResearchSeedSelectionOptions: ParsableArguments {
    private static let rankMetricHelp = ResearchSeedRankMetric.allCases.map(\.rawValue).joined(separator: ", ")

    @Option(name: .long, parsing: .upToNextOption, help: "Exact research seed names to include")
    var seedName: [String] = []

    @Option(name: .long, parsing: .upToNextOption, help: "Research seed source IDs or ID prefixes to include")
    var seedId: [String] = []

    @Option(name: .long, help: "Take the top N resolved research seeds after filtering")
    var seedTop: Int?

    @Option(
        name: .long,
        help: "Rank research seeds by one of: \(rankMetricHelp)"
    )
    var seedRankBy: String?

    @Flag(name: .long, help: "Sort research seeds ascending instead of descending when ranking")
    var seedRankAscending: Bool = false

    func resolvedSelection() throws -> ResearchSeedSelection? {
        if let seedTop, seedTop <= 0 {
            throw ValidationError("--seed-top must be > 0.")
        }
        let normalizedNames = seedName
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        let normalizedIDs = seedId
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        let rankMetric: ResearchSeedRankMetric?
        if let seedRankBy = normalized(seedRankBy) {
            let normalizedMetric = seedRankBy.lowercased().replacingOccurrences(of: "-", with: "_")
            guard let parsed = ResearchSeedRankMetric(rawValue: normalizedMetric) else {
                throw ValidationError(
                    "Invalid --seed-rank-by '\(seedRankBy)'. Expected one of: \(Self.rankMetricHelp)."
                )
            }
            rankMetric = parsed
        } else {
            rankMetric = nil
        }
        if normalizedNames.isEmpty, normalizedIDs.isEmpty, seedTop == nil, rankMetric == nil, !seedRankAscending {
            return nil
        }
        return ResearchSeedSelection(
            sourceIDs: normalizedIDs,
            names: normalizedNames,
            top: seedTop,
            rankBy: rankMetric,
            ascending: seedRankAscending
        )
    }
}

func resolveSingleResearchSeedPatch(
    patches: [ResearchSeedPatch],
    libraryPath: String,
    commandName: String,
    selection: ResearchSeedSelection?
) throws -> ResearchSeedPatch {
    guard !patches.isEmpty else {
        throw ValidationError("No research seeds resolved from \(libraryPath).")
    }
    if let top = selection?.top, top > 1 {
        throw ValidationError("--seed-top \(top) is not supported by \(commandName); refine to --seed-top 1 or a single named/id seed.")
    }
    if selection != nil, patches.count != 1 {
        throw ValidationError("\(commandName) requires exactly one resolved research seed, but the current selector matched \(patches.count). Refine with --seed-name, --seed-id, or --seed-top 1.")
    }
    guard let patch = patches.first else {
        throw ValidationError("No research seeds resolved from \(libraryPath).")
    }
    return patch
}

@available(macOS 10.15, *)
public struct LeniaSwarm: AsyncParsableCommand {
    public static let configuration = CommandConfiguration(
        commandName: "lenia-swarm",
        abstract: "Distributed Lenia parameter search across Apple machines",
        subcommands: [
            DiscoverCommands.self,
            OrchestrateCommands.self,
            IndexCommands.self,
            AnalyzeCommands.self,
            InterveneCommands.self,
            PublishCommands.self,
            TTCommands.self,
            BenchmarkCommand.self,
            ExportReferenceCommand.self,
        ]
    )

    public init() {}
}

struct DiscoverCommands: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "discover",
        abstract: "Mode-specific search and discovery workflows",
        subcommands: [
            LocalCommand.self,
            EvaluateCommand.self,
            ObstacleResponseCommand.self,
            EvolveCommand.self,
            FlowMapElitesCommand.self,
            MutateCommand.self,
            Sensorimotor24Command.self,
            SensorimotorFlowLeniaCommand.self,
            Atlas26Command.self,
            RD23Command.self,
            QD24Command.self,
            Ecology25Command.self,
            Curiosity25Command.self,
        ]
    )
}

struct OrchestrateCommands: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "orchestrate",
        abstract: "Controller, worker, and campaign dispatch",
        subcommands: [
            ControllerCommand.self,
            WorkerCommand.self,
            CampaignCommand.self,
            PortfolioCommand.self,
        ]
    )
}

struct IndexCommands: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "index",
        abstract: "Compendium ingest, repair, and backfill",
        subcommands: [
            IndexCommand.self,
            CompendiumSanityCommand.self,
            CompendiumBackfillCommand.self,
        ],
        defaultSubcommand: IndexCommand.self
    )
}

struct AnalyzeCommands: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "analyze",
        abstract: "Warehouse refresh and derived analysis",
        subcommands: [
            AnalyzeWarehouseCommand.self,
            AnalyzeTopologyCommand.self,
            AnalyzeBiologicalCommand.self,
            AnalyzeDiscoveryCommand.self,
            EcologyCommand.self,
            TaxonomyCommand.self,
        ]
    )
}

struct InterveneCommands: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "intervene",
        abstract: "Intervention batteries and transport experiments",
        subcommands: [
            InterventionBatteryCommand.self,
            HolonomyCommand.self,
        ]
    )
}

struct PublishCommands: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "publish",
        abstract: "Replay, media, compendium, and atlas export surfaces",
        subcommands: [
            ReplayCommand.self,
            MediaCommand.self,
            LibraryFromResultsCommand.self,
            CompendiumPublishCommand.self,
            AtlasPublishCommand.self,
        ]
    )
}
