import ArgumentParser
import Foundation
import LeniaCore
import Logging

struct Curiosity25Command: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "curiosity-2025",
        abstract: "Run the 2025 curiosity-driven Flow-Lenia universe exploration experiments"
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
        let resolvedRunId = resolveRunID(prefix: "curiosity-2025", logOptions: logOptions)
        let resolvedConfigDir = try resolvePath(configDir, dossier: dossierName)
        let resolvedOutput = try output.map { try resolvePath($0, dossier: dossierName) }
        let logging = try bootstrapRunLogging(
            runID: resolvedRunId,
            role: "curiosity-2025",
            loggerLabel: "LeniaSwarm.Curiosity2025",
            logStem: "curiosity-2025",
            outputForLogs: resolvedOutput,
            logOptions: logOptions,
            dossier: dossierName
        )
        let logger = logging.logger
        let bundle = try loadAIScientist2025ConfigBundle(configDirectory: URL(fileURLWithPath: resolvedConfigDir, isDirectory: true))
        if validateOnly {
            logger.info("AI Scientist 2025 configs validated successfully")
            return
        }
        guard let resolvedOutput else {
            throw ValidationError("--output is required unless --validate-only is set.")
        }
        let runner = AIScientist2025Runner(configs: bundle, logger: logger)
        _ = try runner.run(outputDirectory: URL(fileURLWithPath: resolvedOutput, isDirectory: true))
    }
}
