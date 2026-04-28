import ArgumentParser
import Foundation
import LeniaCore

struct InterventionBatteryCommand: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "battery",
        abstract: "Run the intervention-battery campaign through the orchestrated promotion pipeline"
    )

    @Option(name: .long, help: "Path to the intervention-battery config JSON file")
    var config: String

    @Option(name: .shortAndLong, help: "Output directory for intervention artifacts")
    var output: String

    @Option(name: .long, help: "Optional path to library/index.jsonl or exports/index.jsonl for seeded runs")
    var seedLibrary: String?

    @OptionGroup
    var seedSelection: ResearchSeedSelectionOptions

    @Option(name: .long, help: "Requested backend: auto|metal-full|mlx")
    var backend: String = "auto"

    @OptionGroup
    var promotion: ArchivePromotionOptions

    @Flag(name: .long, help: "Parse and validate the intervention config without running")
    var validateOnly: Bool = false

    @OptionGroup
    var logOptions: LogOptions

    mutating func run() async throws {
        let resolvedConfig = try resolvePath(config, dossier: dossierName)
        let resolvedSeedLibrary = try seedLibrary.map { try resolveArtifactPath($0, dossier: dossierName) }
        let resolvedSeedSelection = try seedSelection.resolvedSelection()
        if let resolvedSeedSelection,
           !resolvedSeedSelection.names.isEmpty || !resolvedSeedSelection.sourceIDs.isEmpty || resolvedSeedSelection.ascending {
            throw ValidationError(
                "intervene battery supports only --seed-top and --seed-rank-by selectors on the declarative campaign path."
            )
        }

        var phase: [String: Any] = [
            "name": "battery",
            "type": "intervention-battery",
            "config": resolvedConfig,
        ]
        if let resolvedSeedLibrary {
            phase["seed_library"] = resolvedSeedLibrary
        }
        if let top = resolvedSeedSelection?.top {
            phase["seed_top"] = top
        }
        if let rankBy = resolvedSeedSelection?.rankBy?.rawValue {
            phase["seed_rank_by"] = rankBy
        }

        let payload: [String: Any] = [
            "name": "intervention-battery",
            "phase_isolation": false,
            "compendium": ["merge_phases": true],
            "phases": [phase],
        ]
        let campaignURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("lenia-intervention-battery-\(UUID().uuidString).json")
        let encoded = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
        try encoded.write(to: campaignURL, options: .atomic)

        var command = CampaignCommand()
        command.campaign = campaignURL.path
        command.output = output
        command.backend = backend
        command.promotion = promotion
        command.validateOnly = validateOnly
        command.logOptions = logOptions
        try await command.run()
    }
}
