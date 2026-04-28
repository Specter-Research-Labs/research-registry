import ArgumentParser
import Foundation
import LeniaCore
import Logging

struct Sensorimotor24Command: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "sensorimotor-2024",
        abstract: "Run the Hamon 2024 sensorimotor agency search protocol"
    )

    @Option(name: .long, help: "Path to the paper-locked config directory")
    var configDir: String

    @Option(name: .shortAndLong, help: "Output directory for run artifacts")
    var output: String?

    @Option(name: .long, help: "Random seed")
    var seed: Int = 0

    @Option(name: .long, help: "Path to library/index.jsonl or exports/index.jsonl used to seed the first initialization trial")
    var seedLibrary: String?

    @Option(name: .long, help: "Optional qd-2024 config directory when the seed library comes from qd-2024 and pattern assets are missing")
    var seedQDConfigDir: String?

    @Option(name: .long, parsing: .upToNextOption, help: "QD cell ids to use for warm starts when the seed library comes from qd-2024")
    var seedCell: [Int] = []

    @OptionGroup
    var seedSelection: ResearchSeedSelectionOptions

    @Flag(name: .long, help: "Validate configs and exit without running")
    var validateOnly: Bool = false

    @OptionGroup
    var promotion: ArchivePromotionOptions

    @OptionGroup
    var logOptions: LogOptions

    func run() async throws {
        guard seed >= 0 else {
            throw ValidationError("Seed must be non-negative.")
        }

        let resolvedRunId = resolveRunID(prefix: "sensorimotor-2024", logOptions: logOptions)
        let resolvedConfigDir = try resolvePath(configDir, dossier: dossierName)
        let resolvedOutput = try output.map { try resolvePath($0, dossier: dossierName) }
        let resolvedSeedLibrary = try seedLibrary.map { try resolveArtifactPath($0, dossier: dossierName) }
        let resolvedQDConfigDir = try seedQDConfigDir.map { try resolvePath($0, dossier: dossierName) }
        let logging = try bootstrapRunLogging(
            runID: resolvedRunId,
            role: "sensorimotor-2024",
            loggerLabel: "LeniaSwarm.Sensorimotor2024",
            logStem: "sensorimotor-2024",
            outputForLogs: resolvedOutput,
            logOptions: logOptions,
            dossier: dossierName
        )
        let logger = logging.logger

        logLoggingInitialized(logger, runID: resolvedRunId, logging: logging)

        logger.info("Loading Sensorimotor 2024 configs from \(resolvedConfigDir)")
        let configDirectoryURL = URL(fileURLWithPath: resolvedConfigDir, isDirectory: true)
        let bundle = try loadSensorimotorLenia2024ConfigBundle(configDirectory: configDirectoryURL)
        let seedInitialization: [[Float]]?
        if let resolvedSeedLibrary {
            let selection = try seedSelection.resolvedSelection()
            let patches = try loadResearchSeedPatches(
                libraryURL: URL(fileURLWithPath: resolvedSeedLibrary),
                qdConfigDirectoryOverride: resolvedQDConfigDir.map { URL(fileURLWithPath: $0, isDirectory: true) },
                cells: seedCell.isEmpty ? nil : seedCell,
                selection: selection
            )
            let patch = try resolveSingleResearchSeedPatch(
                patches: patches,
                libraryPath: resolvedSeedLibrary,
                commandName: "sensorimotor-2024",
                selection: selection
            )
            seedInitialization = try researchSeedResizedMassInitialization(
                patch: patch,
                size: bundle.ruleSpace.initialization.size
            )
            logger.info("Using research seed initialization warm start '\(patch.name)'")
        } else {
            seedInitialization = nil
        }

        if validateOnly {
            logger.info("Sensorimotor 2024 configs validated successfully")
            return
        }

        guard let resolvedOutput else {
            throw ValidationError("--output is required unless --validate-only is set.")
        }

        let outputDirectoryURL = URL(fileURLWithPath: resolvedOutput, isDirectory: true)
        try FileManager.default.createDirectory(at: outputDirectoryURL, withIntermediateDirectories: true)

        logger.info("============================================================")
        logger.info("Sensorimotor Lenia 2024")
        logger.info("============================================================")
        logger.info("Seed: \(seed)")
        logger.info("Output: \(resolvedOutput)")
        logger.info("Outer steps: \(bundle.training.outerSteps)")
        logger.info("Random initialization trials: \(bundle.training.historyInitializationTrials)")
        logger.info("Training rollout steps: \(bundle.training.rolloutSteps)")
        logger.info("Evaluation rollouts: \(bundle.training.evaluationAfterStep.rollouts)")
        logger.info("============================================================")

        let runner = SensorimotorLenia2024Runner(
            configs: bundle,
            logger: logger,
            seedInitialization: seedInitialization
        )
        let summary = try runner.run(seed: UInt64(seed), outputDirectory: outputDirectoryURL, runId: resolvedRunId)

        logger.info("Sensorimotor 2024 complete")
        logger.info("History count: \(summary.historyCount)")
        logger.info("Restart count: \(summary.restartCount)")
        logger.info("Best collapse: \(summary.bestReached.collapse)")
        logger.info("Best centroid: (\(summary.bestReached.centroidX), \(summary.bestReached.centroidY))")
        logger.info("Agency passed: \(summary.bestEvaluation.agency.agencyPassed)")
        logger.info("Moving passed: \(summary.bestEvaluation.agency.movingPassed)")
        logger.info("Basic obstacle robustness: \(summary.bestEvaluation.basicObstacleRobustness)")
        logger.info("Generalization scenarios: \(summary.bestEvaluation.scenarios.count)")

        let resolvedPromotion = try promoteIfConfigured(
            options: promotion,
            defaultCompendiumPath: outputDirectoryURL.appendingPathComponent("compendium.sqlite").path,
            dossier: dossierName,
            defaultEnabled: true,
            runDir: outputDirectoryURL.path,
            includeResults: true
        )
        if let compendiumPath = resolvedPromotion.compendiumPath {
            logger.info("Promoted sensorimotor-2024 run into compendium: \(compendiumPath)")
        }
    }
}
