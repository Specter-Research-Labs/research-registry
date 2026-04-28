import ArgumentParser
import DistributedCluster
import Foundation
import LeniaCore
import Logging

struct WorkerCommand: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "worker",
        abstract: "Run as worker - executes simulation jobs"
    )

    @Option(name: .shortAndLong, help: "Host IP to bind to")
    var host: String = "0.0.0.0"

    @Option(name: .shortAndLong, help: "Port to bind to")
    var port: Int

    @Option(name: .long, help: "Controller IP address")
    var controller: String

    @Option(name: .long, help: "Controller port")
    var controllerPort: Int = 7337

    @OptionGroup
    var logOptions: LogOptions

    func run() async throws {
        let hostname = ProcessInfo.processInfo.hostName
        let workerId = LeniaWorker.generateWorkerId()
        let resolvedRunId = resolveRunID(prefix: "run", logOptions: logOptions)
        let nodeId = "\(hostname):\(port)"
        let logging = try bootstrapRunLogging(
            runID: resolvedRunId,
            role: "worker",
            loggerLabel: "LeniaSwarm.Worker",
            logStem: "worker",
            outputForLogs: nil,
            logOptions: logOptions,
            dossier: dossierName,
            nodeID: nodeId,
            logFileName: "worker-\(workerId).log.jsonl",
            metricsFileName: "worker-\(workerId).metrics.jsonl",
            extraMetadata: ["worker_id": .string(workerId)]
        )
        let logger = logging.logger

        logger.info("Starting Lenia Swarm Worker")
        logger.info("Hostname: \(hostname)")
        logger.info("Binding to \(host):\(port)")
        logger.info("Controller: \(controller):\(controllerPort)")
        logLoggingInitialized(logger, runID: resolvedRunId, logging: logging)

        let system = await ClusterSystem("LeniaHive") { settings in
            settings.bindHost = host
            settings.bindPort = port
            settings.swim.probeInterval = .seconds(1)
            settings.swim.pingTimeout = .milliseconds(500)
            settings.remoteCall.defaultTimeout = .seconds(600)
        }

        logger.info("Cluster system created")

        let worker = LeniaWorker(actorSystem: system, workerId: workerId)
        logger.info("Worker actor created")

        await system.receptionist.checkIn(worker, with: .leniaWorkers)
        logger.info("Registered with receptionist")

        let controllerEndpoint = Cluster.Endpoint(host: controller, port: controllerPort)
        system.cluster.join(endpoint: controllerEndpoint)

        logger.info("Joined cluster, waiting for jobs...")

        while true {
            try await Task.sleep(for: .seconds(3600))
        }
    }
}
