import ArgumentParser
import DistributedCluster
import Foundation
import LeniaCore
import Logging

struct QD24Command: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "qd-2024",
        abstract: "Run the 2024 quality-diversity repertoire discovery protocol"
    )

    @Option(name: .long, help: "Path to the paper-locked config directory")
    var configDir: String

    @Option(name: .long, help: "Optional base config JSON override")
    var baseConfig: String?

    @Option(name: .long, help: "Optional MAP-Elites config JSON override")
    var mapElitesConfig: String?

    @Option(name: .long, help: "Optional AURORA config JSON override")
    var auroraConfig: String?

    @Option(name: .shortAndLong, help: "Output directory for run artifacts")
    var output: String?

    @Option(name: .long, help: "Algorithm to run: me|aurora")
    var algorithm: String = "me"

    @Option(name: .long, help: "Deterministic run seed")
    var seed: Int = 0

    @Flag(name: .long, help: "Evaluate MAP-Elites batches on distributed workers")
    var distributed: Bool = false

    @Flag(name: .long, help: "Evaluate each genotype as multiple interacting copies in one shared arena")
    var localizedSharedArena: Bool = false

    @Option(name: .long, help: "Number of copies per genotype when --localized-shared-arena")
    var arenaCopies: Int = 4

    @Option(name: .long, help: "Canvas size for --localized-shared-arena")
    var arenaCanvasSize: Int = 512

    @Option(name: .long, help: "Host IP to bind to when --distributed")
    var host: String = "0.0.0.0"

    @Option(name: .long, help: "Port to bind to when --distributed")
    var port: Int = 7337

    @Option(name: .long, help: "Minimum connected workers required when --distributed")
    var minWorkers: Int = 1

    @Flag(name: .long, help: "Validate configs and exit without running")
    var validateOnly: Bool = false

    @OptionGroup
    var promotion: ArchivePromotionOptions

    @OptionGroup
    var logOptions: LogOptions

    func run() async throws {
        let resolvedRunId = resolveRunID(prefix: "qd-2024", logOptions: logOptions)
        let resolvedConfigDir = try resolvePath(configDir, dossier: dossierName)
        let resolvedOutput = try output.map { try resolvePath($0, dossier: dossierName) }
        let logging = try bootstrapRunLogging(
            runID: resolvedRunId,
            role: "qd-2024",
            loggerLabel: "LeniaSwarm.QD2024",
            logStem: "qd-2024",
            outputForLogs: resolvedOutput,
            logOptions: logOptions,
            dossier: dossierName
        )
        let logger = logging.logger
        logger.info("Loading LeniaBreeder 2024 configs from \(resolvedConfigDir)")
        let configDirectoryURL = URL(fileURLWithPath: resolvedConfigDir, isDirectory: true)
        func optionalConfigURL(_ path: String?) throws -> URL? {
            guard let path else { return nil }
            return URL(fileURLWithPath: try resolvePath(path, dossier: dossierName))
        }
        let bundle = try loadLeniaBreeder2024ConfigBundle(
            configDirectory: configDirectoryURL,
            baseURL: try optionalConfigURL(baseConfig),
            mapElitesURL: try optionalConfigURL(mapElitesConfig),
            auroraURL: try optionalConfigURL(auroraConfig)
        )

        if validateOnly {
            logger.info("LeniaBreeder 2024 configs validated successfully")
            return
        }

        guard let resolvedOutput else {
            throw ValidationError("--output is required unless --validate-only is set.")
        }

        let outputDirectoryURL = URL(fileURLWithPath: resolvedOutput, isDirectory: true)
        try FileManager.default.createDirectory(at: outputDirectoryURL, withIntermediateDirectories: true)

        logger.info("============================================================")
        logger.info("LeniaBreeder 2024")
        logger.info("============================================================")
        logger.info("Output: \(resolvedOutput)")
        logger.info("Algorithm: \(algorithm)")
        logger.info("Seed: \(seed)")
        logger.info("Distributed: \(distributed)")
        logger.info("Localized shared arena: \(localizedSharedArena)")
        logger.info("Pattern: \(bundle.base.patternID)")
        logger.info("============================================================")

        if localizedSharedArena {
            guard algorithm == "me" else {
                throw ValidationError("--localized-shared-arena currently supports only --algorithm me.")
            }
            guard !distributed else {
                throw ValidationError("--localized-shared-arena currently does not support --distributed.")
            }
            guard arenaCopies > 1 else {
                throw ValidationError("--arena-copies must be > 1 when --localized-shared-arena is set.")
            }
            guard arenaCanvasSize >= bundle.base.worldSize else {
                throw ValidationError("--arena-canvas-size must be >= base.world_size.")
            }
        }

        let runner = LeniaBreeder2024Runner(
            configs: bundle,
            logger: logger,
            seed: seed,
            arenaMode: localizedSharedArena
                ? .localizedSharedCopies(copyCount: arenaCopies, canvasSize: arenaCanvasSize)
                : .paperIsolated
        )
        switch algorithm {
        case "me":
            let summary: LeniaBreeder2024RunSummary
            if distributed {
                let nodeId = "\(ProcessInfo.processInfo.hostName):\(port)"
                let system = await ClusterSystem("LeniaHive") { settings in
                    settings.bindHost = host
                    settings.bindPort = port
                    settings.swim.probeInterval = .seconds(1)
                    settings.swim.pingTimeout = .milliseconds(500)
                    settings.remoteCall.defaultTimeout = .seconds(1800)
                }
                logger.info("Starting distributed qd-2024 host on \(host):\(port)")
                let controller = LeniaBreeder2024DistributedController(
                    system: system,
                    logger: logger,
                    runContext: RunContext(runId: resolvedRunId, controllerId: nodeId)
                )
                do {
                    try await controller.start(minCount: minWorkers)
                    summary = try await runner.runDistributedMAPElites(
                        outputDirectory: outputDirectoryURL,
                        controller: controller,
                        runId: resolvedRunId,
                        controllerId: nodeId,
                        minWorkers: minWorkers
                    )
                    try system.shutdown()
                } catch {
                    _ = try? system.shutdown()
                    throw error
                }
            } else {
                summary = try runner.runMAPElites(outputDirectory: outputDirectoryURL, runId: resolvedRunId)
            }
            logger.info("LeniaBreeder 2024 complete")
            logger.info("Coverage: \(summary.coverage)")
            logger.info("QD score: \(summary.qdScore)")
            logger.info("Max fitness: \(summary.maxFitness)")
        case "aurora":
            if distributed {
                throw ValidationError("--distributed currently supports only --algorithm me.")
            }
            let summary = try runner.runAURORA(outputDirectory: outputDirectoryURL, runId: resolvedRunId)
            logger.info("LeniaBreeder 2024 complete")
            logger.info("Coverage: \(summary.coverage)")
            logger.info("QD score: \(summary.qdScore)")
            logger.info("Max fitness: \(summary.maxFitness)")
        default:
            throw ValidationError("--algorithm must be one of: me, aurora")
        }

        let resolvedPromotion = try promoteIfConfigured(
            options: promotion,
            defaultCompendiumPath: outputDirectoryURL.appendingPathComponent("compendium.sqlite").path,
            dossier: dossierName,
            defaultEnabled: true,
            runDir: outputDirectoryURL.path,
            includeResults: true
        )
        if let compendiumPath = resolvedPromotion.compendiumPath {
            logger.info("Promoted qd-2024 run into compendium: \(compendiumPath)")
        }
    }
}
