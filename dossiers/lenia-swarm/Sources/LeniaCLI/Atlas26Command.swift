import ArgumentParser
import Foundation
import LeniaCore
import Logging

struct Atlas26Command: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "atlas-2026",
        abstract: "Run the Hudcova et al. 2026 classical Lenia parameter-space atlas protocol"
    )

    @Option(name: .long, help: "Path to the paper-locked config directory")
    var configDir: String

    @Option(name: .shortAndLong, help: "Output directory for atlas artifacts")
    var output: String?

    @Flag(name: .long, help: "Validate configs and exit without running")
    var validateOnly: Bool = false

    @OptionGroup
    var logOptions: LogOptions

    func run() async throws {
        let resolvedRunId = resolveRunID(prefix: "atlas-2026", logOptions: logOptions)
        let resolvedConfigDir = try resolvePath(configDir, dossier: dossierName)
        let resolvedOutput = try output.map { try resolvePath($0, dossier: dossierName) }
        let logging = try bootstrapRunLogging(
            runID: resolvedRunId,
            role: "atlas-2026",
            loggerLabel: "LeniaSwarm.Atlas2026",
            logStem: "atlas-2026",
            outputForLogs: resolvedOutput,
            logOptions: logOptions,
            dossier: dossierName
        )
        let logger = logging.logger
        logLoggingInitialized(logger, runID: resolvedRunId, logging: logging)

        let configDirectoryURL = URL(fileURLWithPath: resolvedConfigDir, isDirectory: true)
        logger.info("Loading Atlas 2026 configs from \(resolvedConfigDir)")
        let bundle = try loadAtlas2026ConfigBundle(configDirectory: configDirectoryURL)

        if validateOnly {
            logger.info("Atlas 2026 configs validated successfully")
            return
        }

        guard let resolvedOutput else {
            throw ValidationError("--output is required unless --validate-only is set.")
        }

        let outputDirectoryURL = URL(fileURLWithPath: resolvedOutput, isDirectory: true)
        try FileManager.default.createDirectory(at: outputDirectoryURL, withIntermediateDirectories: true)

        logger.info("============================================================")
        logger.info("Lenia Atlas 2026")
        logger.info("============================================================")
        logger.info("Output: \(resolvedOutput)")
        logger.info("Array size: \(bundle.kernel.arraySize)")
        logger.info("Kernel: \(bundle.kernel.function)")
        logger.info("Radius: \(bundle.kernel.radius)")
        logger.info("Polygon sizes: \(bundle.sweep.polygonSizes)")
        logger.info("Samples per polygon: \(bundle.sweep.samplesPerPolygon)")
        logger.info("============================================================")

        let runner = Atlas2026Runner(configs: bundle, logger: logger)
        let summary = try runner.run(outputDirectory: outputDirectoryURL)

        logger.info("Atlas 2026 complete")
        logger.info("Systems: \(summary.systems)")
        logger.info("Kernel key: \(summary.kernelKey)")
        logger.info("Mu count: \(summary.muCount)")
        logger.info("Sigma count: \(summary.sigmaCount)")
    }
}
