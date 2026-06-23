import ArgumentParser
import Foundation
import LeniaCore
import Logging

struct SensorimotorFlowLeniaCommand: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "sensorimotor-flowlenia",
        abstract: "Run the sensorimotor agency search on the mass-conserving Flow-Lenia integrator"
    )

    @Option(name: .long, help: "Path to the config.json for the run")
    var configFile: String

    @Option(name: .shortAndLong, help: "Output directory for run artifacts")
    var output: String?

    @Option(name: .long, help: "Random seed")
    var seed: Int = 0

    @Flag(name: .long, help: "Validate the config and exit without running")
    var validateOnly: Bool = false

    @OptionGroup
    var logOptions: LogOptions

    func run() async throws {
        guard seed >= 0 else {
            throw ValidationError("Seed must be non-negative.")
        }

        let resolvedRunId = resolveRunID(prefix: "sensorimotor-flowlenia", logOptions: logOptions)
        let resolvedConfigFile = try resolvePath(configFile, dossier: dossierName)
        let resolvedOutput = try output.map { try resolvePath($0, dossier: dossierName) }
        let logging = try bootstrapRunLogging(
            runID: resolvedRunId,
            role: "sensorimotor-flowlenia",
            loggerLabel: "LeniaSwarm.SensorimotorFlowLenia",
            logStem: "sensorimotor-flowlenia",
            outputForLogs: resolvedOutput,
            logOptions: logOptions,
            dossier: dossierName
        )
        let logger = logging.logger
        logLoggingInitialized(logger, runID: resolvedRunId, logging: logging)

        logger.info("Loading Flow-Lenia sensorimotor config from \(resolvedConfigFile)")
        let config = try loadFlowSensorimotorConfig(configFile: URL(fileURLWithPath: resolvedConfigFile))

        if validateOnly {
            logger.info("Flow-Lenia sensorimotor config validated successfully")
            return
        }

        guard let resolvedOutput else {
            throw ValidationError("--output is required unless --validate-only is set.")
        }
        let outputDirectoryURL = URL(fileURLWithPath: resolvedOutput, isDirectory: true)

        logger.info("============================================================")
        logger.info("Sensorimotor Flow-Lenia")
        logger.info("============================================================")
        logger.info("Seed: \(seed)")
        logger.info("Output: \(resolvedOutput)")
        logger.info("Outer steps: \(config.outerSteps)")
        logger.info("Random initialization trials: \(config.historyInitializationTrials)")
        logger.info("Rollout steps: \(config.rolloutSteps)")
        logger.info("============================================================")

        let runner = FlowSensorimotorRunner(config: config, logger: logger)
        let summary = try runner.run(seed: UInt64(seed), outputDirectory: outputDirectoryURL, runId: resolvedRunId)

        logger.info("Sensorimotor Flow-Lenia complete")
        logger.info("History count: \(summary.historyCount)")
        logger.info("Restart count: \(summary.restartCount)")
        logger.info("Best step: \(summary.bestStep)")
        logger.info("Best reached: \(summary.bestReached)")
        logger.info("Nominal viable: \(summary.agency.nominalViable)")
        logger.info("Nominal displacement: \(summary.agency.nominalDisplacement)")
        logger.info("Moving: \(summary.agency.moving)")
        logger.info("Obstacle robustness: \(summary.agency.obstacleRobustness)")
    }
}
