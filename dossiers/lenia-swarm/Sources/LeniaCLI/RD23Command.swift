import ArgumentParser
import Foundation
import LeniaCore
import Logging

struct RD23Command: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "rd-2023",
        abstract: "Run the 2023 reaction-diffusion Lenia validation and kernel-emulation protocol"
    )

    @Option(name: .long, help: "Path to the paper-locked config directory")
    var configDir: String

    @Option(name: .shortAndLong, help: "Output directory for run artifacts")
    var output: String?

    @Flag(name: .long, help: "Validate configs and exit without running")
    var validateOnly: Bool = false

    @OptionGroup
    var logOptions: LogOptions

    func run() async throws {
        let resolvedRunId = resolveRunID(prefix: "reaction-diffusion-2023", logOptions: logOptions)
        let resolvedConfigDir = try resolvePath(configDir, dossier: dossierName)
        let resolvedOutput = try output.map { try resolvePath($0, dossier: dossierName) }
        let logging = try bootstrapRunLogging(
            runID: resolvedRunId,
            role: "reaction-diffusion-2023",
            loggerLabel: "LeniaSwarm.ReactionDiffusion2023",
            logStem: "reaction-diffusion-2023",
            outputForLogs: resolvedOutput,
            logOptions: logOptions,
            dossier: dossierName
        )
        let logger = logging.logger
        logLoggingInitialized(logger, runID: resolvedRunId, logging: logging)

        logger.info("Loading Reaction-Diffusion 2023 configs from \(resolvedConfigDir)")
        let configDirectoryURL = URL(fileURLWithPath: resolvedConfigDir, isDirectory: true)
        let bundle = try loadReactionDiffusionLenia2023ConfigBundle(configDirectory: configDirectoryURL)

        if validateOnly {
            logger.info("Reaction-Diffusion 2023 configs validated successfully")
            return
        }

        guard let resolvedOutput else {
            throw ValidationError("--output is required unless --validate-only is set.")
        }

        let outputDirectoryURL = URL(fileURLWithPath: resolvedOutput, isDirectory: true)
        try FileManager.default.createDirectory(at: outputDirectoryURL, withIntermediateDirectories: true)

        logger.info("============================================================")
        logger.info("Reaction-Diffusion Lenia 2023")
        logger.info("============================================================")
        logger.info("Output: \(resolvedOutput)")
        logger.info("dt values: \(bundle.asymptotic.dtValues)")
        logger.info("Orbium config: \(bundle.asymptotic.orbiumConfig)")
        logger.info("Auxiliary variables: \(bundle.emulation.auxiliaryVariableCount)")
        logger.info("============================================================")

        let runner = ReactionDiffusionLenia2023Runner(configs: bundle, logger: logger)
        let summary = try runner.run(outputDirectory: outputDirectoryURL)

        logger.info("Reaction-Diffusion 2023 complete")
        logger.info("Original runs: \(summary.original.count)")
        logger.info("Asymptotic runs: \(summary.asymptotic.count)")
        logger.info("Kernel fit RMSE: \(summary.kernelEmulation.rmse)")
    }
}
