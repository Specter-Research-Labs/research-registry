import ArgumentParser
import DistributedCluster
import Foundation
import LeniaCore
import Logging

struct ControllerCommand: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "controller",
        abstract: "Run as controller - distributes jobs to workers"
    )

    @Option(name: .shortAndLong, help: "Host IP to bind to")
    var host: String = "0.0.0.0"

    @Option(name: .shortAndLong, help: "Port to bind to")
    var port: Int = 7337

    @Option(name: .long, help: "Path to base config.json")
    var config: String

    @Option(name: .long, help: "Path to search config.json")
    var search: String

    @Option(name: .shortAndLong, help: "Output directory for aggregated results")
    var output: String

    @Option(name: .long, help: "Number of seeds per job chunk")
    var seedsPerJob: Int = 10

    @Flag(name: .long, help: "Exit after all jobs complete")
    var autoExit: Bool = false

    @OptionGroup
    var logOptions: LogOptions

    mutating func run() async throws {
        let resolvedRunId = resolveRunID(prefix: "run", logOptions: logOptions)
        let resolvedOutput = try resolvePath(output, dossier: dossierName)
        let outputURL = URL(fileURLWithPath: resolvedOutput, isDirectory: true)
        if outputURL.lastPathComponent == "overall" {
            throw ValidationError("Output directory should be the run root (hosts/<node>/runs/<runId>), not a nested overall/. The controller writes overall/ itself.")
        }
        let nodeId = "\(ProcessInfo.processInfo.hostName):\(port)"
        let logging = try bootstrapRunLogging(
            runID: resolvedRunId,
            role: "controller",
            loggerLabel: "LeniaSwarm.Controller",
            logStem: "controller",
            outputForLogs: resolvedOutput,
            logOptions: logOptions,
            dossier: dossierName,
            fallbackOutputLogDir: true,
            nodeID: nodeId,
            metricsFileName: "metrics.jsonl"
        )

        let logger = logging.logger

        logger.info("Starting Lenia Swarm Controller")
        logLoggingInitialized(logger, runID: resolvedRunId, logging: logging)
        logger.info("Binding to \(host):\(port)")
        logger.info("Config: \(config)")
        logger.info("Search: \(search)")
        logger.info("Output: \(resolvedOutput)")
        logger.info("Seeds per job: \(seedsPerJob)")
        logger.info("Auto-exit: \(autoExit)")

        let system = await ClusterSystem("LeniaHive") { settings in
            settings.bindHost = host
            settings.bindPort = port
            settings.swim.probeInterval = .seconds(1)
            settings.swim.pingTimeout = .milliseconds(500)
            settings.remoteCall.defaultTimeout = .seconds(600)
        }

        let (eventStream, eventContinuation) = AsyncStream<ControllerEvent>.makeStream()

        let runContext = RunContext(runId: resolvedRunId, controllerId: nodeId)

        let controller = try SwarmController(
            system: system,
            baseConfigPath: config,
            searchConfigPath: search,
            outputDir: resolvedOutput,
            seedsPerJob: seedsPerJob,
            runContext: runContext,
            logger: logger,
            eventContinuation: eventContinuation
        )

        try await controller.start()

        var didAutoExit = false

        for await event in eventStream {
            switch event {
            case .progress(let completed, let total, let seeds, let totalSeeds, let rate):
                logger.info("Progress: \(completed)/\(total) jobs | \(seeds)/\(totalSeeds) seeds | \(String(format: "%.1f", rate)) seeds/s")
            case .finished(let elapsed):
                logger.info("All jobs completed in \(String(format: "%.1f", elapsed))s")
                if autoExit {
                    logger.info("Auto-exit enabled; shutting down")
                    didAutoExit = true
                    eventContinuation.finish()
                }
            case .workerListUpdated(let workers):
                logger.info("Workers: \(workers.count) connected")
            case .creatureDiscovered(let creature):
                logger.info("Creature discovered: \(creature.name) by \(creature.ownerId)")
            case .campaignsUpdated(let campaigns):
                logger.info("Campaigns updated: \(campaigns.count)")
            }

            if didAutoExit {
                break
            }
        }

        if didAutoExit {
            try system.shutdown()
        }

        logger.info("Controller shutting down")
    }
}
