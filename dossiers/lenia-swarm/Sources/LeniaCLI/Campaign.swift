import ArgumentParser
import DistributedCluster
import Darwin
import Foundation
import LeniaCore
import Logging
import Metal
import SQLite3

struct CampaignCommand: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "campaign",
        abstract: "Run declarative multi-phase Lenia campaigns"
    )

    @Option(name: .long, help: "Path to a declarative campaign JSON (multi-phase pipeline)")
    var campaign: String

    @Option(name: .shortAndLong, help: "Output directory for campaign artifacts")
    var output: String

    @Option(name: .long, help: "Requested backend: auto|metal-full|mlx")
    var backend: String = "auto"

    @OptionGroup
    var promotion: ArchivePromotionOptions

    @Flag(name: .long, help: "Parse and validate the campaign config without running")
    var validateOnly: Bool = false

    @OptionGroup
    var logOptions: LogOptions

    mutating func run() async throws {
        try await runDeclarativeCampaign(campaignPath: campaign)
    }

    private mutating func runDeclarativeCampaign(campaignPath: String) async throws {
        let resolvedRunId = resolveRunID(prefix: "campaign", logOptions: logOptions)
        let resolvedOutput = try resolveArtifactPath(output, dossier: dossierName)
        let resolvedCampaignPath = try resolvePath(campaignPath, dossier: dossierName)
        let logging = try bootstrapRunLogging(
            runID: resolvedRunId,
            role: "campaign",
            loggerLabel: "LeniaSwarm.Campaign",
            logStem: "campaign",
            outputForLogs: resolvedOutput,
            logOptions: logOptions,
            dossier: dossierName
        )
        let logger = logging.logger

        let campaignConfigURL = URL(fileURLWithPath: resolvedCampaignPath)
        let campaignConfig = try JSONDecoder().decode(
            LeniaCampaignConfig.self,
            from: Data(contentsOf: campaignConfigURL)
        )
        logger.info("Loaded campaign '\(campaignConfig.name)' with \(campaignConfig.phases.count) phases")

        let outputURL = URL(fileURLWithPath: resolvedOutput, isDirectory: true)
        let defaultCompendiumPath = outputURL.appendingPathComponent("compendium.sqlite").path
        let resolvedPromotion = try promotion.resolvedConfig(
            defaultCompendiumPath: defaultCompendiumPath,
            dossier: dossierName,
            defaultEnabled: campaignConfig.compendium?.mergePhases == true
        )
        if resolvedPromotion.isEnabled, campaignConfig.compendium?.mergePhases != true {
            throw ValidationError(
                "Declarative campaign promotion requires compendium.merge_phases = true so one canonical compendium can feed the warehouse."
            )
        }

        if validateOnly {
            for (index, phase) in campaignConfig.phases.enumerated() {
                logger.info("  Phase \(index + 1): \(phase.name) (type=\(phase.type.rawValue))")
            }
            logger.info("Campaign config validated successfully")
            return
        }

        try FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)

        let dossierRoot = campaignDossierRoot()
        let campaignConfigDirectory = campaignConfigURL.deletingLastPathComponent()
        let phaseIsolation = campaignConfig.phaseIsolation ?? true

        var phaseResults: [LeniaCampaignPhaseResult] = []
        var phaseCompendiumPaths: [URL] = []
        var completedPhaseOutputs: [String: URL] = [:]

        for (index, phase) in campaignConfig.phases.enumerated() {
            let phaseOutputURL = outputURL.appendingPathComponent(phase.name, isDirectory: true)
            try FileManager.default.createDirectory(at: phaseOutputURL, withIntermediateDirectories: true)

            logger.info("Phase \(index + 1)/\(campaignConfig.phases.count): \(phase.name) (type=\(phase.type.rawValue))")
            let phaseStart = Date()

            do {
                let resolvedPhase = resolvePhaseReferences(phase, completedPhaseOutputs: completedPhaseOutputs)
                let result = try executeDeclarativePhase(
                    phase: resolvedPhase,
                    phaseOutputURL: phaseOutputURL,
                    dossierRoot: dossierRoot,
                    campaignConfigDirectory: campaignConfigDirectory,
                    runID: resolvedRunId,
                    backendRequest: backend,
                    logger: logger
                )
                phaseResults.append(result)
                completedPhaseOutputs[phase.name] = phaseOutputURL

                phaseCompendiumPaths.append(contentsOf: collectCompendiumPaths(under: phaseOutputURL))
            } catch {
                let elapsed = Date().timeIntervalSince(phaseStart)
                logger.error("Phase '\(phase.name)' failed: \(error)")
                phaseResults.append(LeniaCampaignPhaseResult(
                    phaseName: phase.name,
                    phaseType: phase.type,
                    creaturesFound: 0,
                    coverage: nil,
                    elapsedSeconds: elapsed,
                    error: String(describing: error),
                    outputDirectory: phaseOutputURL
                ))
                if !phaseIsolation {
                    throw error
                }
            }
        }

        if let compendiumConfig = campaignConfig.compendium,
           compendiumConfig.mergePhases,
           !phaseCompendiumPaths.isEmpty {
            let centralPath = try resolveCampaignCentralCompendiumPath(
                promotedPath: resolvedPromotion.compendiumPath,
                configuredPath: compendiumConfig.centralDB,
                outputURL: outputURL,
                campaignConfigDirectory: campaignConfigDirectory,
                dossierRoot: dossierRoot
            )
            try mergeCompendiumDatabases(sources: phaseCompendiumPaths, into: centralPath, logger: logger)
            if let warehouseResult = try refreshWarehouseProjection(
                compendiumPath: centralPath,
                warehousePath: resolvedPromotion.warehousePath,
                warehouseTopology: resolvedPromotion.warehouseTopology
            ) {
                logger.info(
                    "Refreshed warehouse from merged campaign compendium (study=\(warehouseResult.studyId), warehouse=\(warehouseResult.warehousePath))"
                )
            }
        }

        let summaryEncoder = JSONEncoder()
        summaryEncoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let phaseSummaries = phaseResults.map { result in
            DeclarativeCampaignPhaseSummary(
                name: result.phaseName,
                type: result.phaseType,
                creaturesFound: result.creaturesFound,
                coverage: result.coverage,
                elapsedSeconds: result.elapsedSeconds,
                error: result.error
            )
        }
        let campaignSummary = DeclarativeCampaignSummary(
            name: campaignConfig.name,
            runID: resolvedRunId,
            phases: phaseSummaries,
            totalCreatures: phaseResults.reduce(0) { $0 + $1.creaturesFound },
            totalElapsedSeconds: phaseResults.reduce(0) { $0 + $1.elapsedSeconds },
            failedPhases: phaseResults.filter { $0.error != nil }.count
        )
        try summaryEncoder.encode(campaignSummary)
            .write(to: outputURL.appendingPathComponent("campaign-summary.json"))

        logger.info("Campaign '\(campaignConfig.name)' complete: \(campaignSummary.totalCreatures) creatures, \(campaignSummary.failedPhases) failed phases, \(String(format: "%.1f", campaignSummary.totalElapsedSeconds))s total")
    }
}

struct CampaignExecutionRequest {
    let runID: String
    let preset: LeniaCampaignPreset
    let configURL: URL
    let outputURL: URL
    let seedLibraryURL: URL?
    let seedQDConfigDirURL: URL?
    let seedSelection: ResearchSeedSelection?
    let backendRequest: String
    let executionMode: LeniaCampaignExecutionMode
    let distributedControllerHost: String?
    let distributedControllerPort: Int
    let distributedBindHost: String
    let distributedBindPort: Int
    let exportBest: Int?
    let promotion: ArchivePromotionConfig
}

struct CampaignSummaryFile: Codable {
    let schemaVersion: Int
    let runID: String
    let preset: LeniaCampaignPreset
    let executionMode: LeniaCampaignExecutionMode
    let totalJobs: Int
    let completedRuns: Int
    let failedRuns: Int
    let metricRows: Int
    let eventRows: Int
    let exportedCreatures: Int
    let backends: [String: Int]
}

struct CampaignExecutionResult {
    let jobs: [LeniaCampaignJob]
    let runs: [LeniaCampaignRunRecord]
    let metrics: [LeniaCampaignMetricRecord]
    let events: [LeniaCampaignEventRecord]
    let results: [SimulationResultData]
    let ecologyArtifacts: [LeniaCampaignEcologyArtifact]
    let exportCandidates: [LeniaCampaignExportCandidate]
    let summary: CampaignSummaryFile
}

private struct CampaignResolvedConfigFile: Codable {
    let schemaVersion: Int
    let runID: String
    let preset: LeniaCampaignPreset
    let executionMode: LeniaCampaignExecutionMode
    let backendRequest: String
    let configPath: String
    let seedLibraryPath: String?
    let exportBest: Int?
    let promotedCompendiumPath: String?
    let promotedWarehousePath: String?
    let promotedWarehouseTopology: Bool
    let jobs: [LeniaCampaignJob]
}

private func aggregateCampaignExecutions(
    _ executions: [LeniaCampaignJobExecution],
    metricsTransform: ((inout [LeniaCampaignMetricRecord]) -> Void)? = nil
) -> LeniaCampaignJobExecution {
    var metrics = executions.flatMap(\.metrics)
    metricsTransform?(&metrics)
    return LeniaCampaignJobExecution(
        runs: executions.flatMap(\.runs),
        metrics: metrics,
        events: executions.flatMap(\.events),
        results: executions.flatMap(\.results),
        ecologyArtifacts: executions.flatMap(\.ecologyArtifacts),
        exportCandidates: executions.flatMap(\.exportCandidates)
    )
}

private func executeLocalCampaignJobs(
    _ jobs: [LeniaCampaignJob],
    logger: Logger,
    metricsTransform: ((inout [LeniaCampaignMetricRecord]) -> Void)? = nil
) throws -> LeniaCampaignJobExecution {
    let capabilities = localCampaignCapabilities()
    let executions = try jobs.map { job in
        try executeLeniaCampaignJob(job, logger: logger, localCapabilities: capabilities)
    }
    return aggregateCampaignExecutions(executions, metricsTransform: metricsTransform)
}

func executeLocalCampaignPhase(
    request: CampaignExecutionRequest,
    jobs: [LeniaCampaignJob],
    logger: Logger,
    metricsTransform: ((inout [LeniaCampaignMetricRecord]) -> Void)? = nil
) throws -> LeniaCampaignJobExecution {
    let execution = try executeLocalCampaignJobs(jobs, logger: logger, metricsTransform: metricsTransform)
    try writeCampaignBundle(
        request: request,
        jobs: jobs,
        execution: execution,
        outputURL: request.outputURL,
        logger: logger
    )
    try runCampaignCompendiumIndex(outputURL: request.outputURL)
    return execution
}

func runCampaign(
    request: CampaignExecutionRequest,
    logger: Logger
) async throws -> CampaignExecutionResult {
    let dossierRoot = campaignDossierRoot()
    let configDirectory = request.configURL.deletingLastPathComponent()
    let outputURL = request.outputURL.standardizedFileURL
    try FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)

    let jobs = try buildCampaignJobs(
        request: request,
        dossierRoot: dossierRoot,
        configDirectory: configDirectory,
        logger: logger
    )
    let metricsTransform: ((inout [LeniaCampaignMetricRecord]) -> Void)? =
        request.preset == .interventionBattery
        ? { metrics in applyBaselineComparisons(to: &metrics) }
        : nil

    let execution: LeniaCampaignJobExecution
    switch request.executionMode {
    case .local:
        execution = try executeLocalCampaignJobs(jobs, logger: logger, metricsTransform: metricsTransform)
    case .distributed:
        guard let controllerHost = request.distributedControllerHost, !controllerHost.isEmpty else {
            throw ValidationError("--controller is required with --distributed.")
        }
        execution = aggregateCampaignExecutions(
            try await executeDistributedCampaignJobs(
                jobs: jobs,
                controllerHost: controllerHost,
                controllerPort: request.distributedControllerPort,
                bindHost: request.distributedBindHost,
                bindPort: request.distributedBindPort,
                logger: logger
            ),
            metricsTransform: metricsTransform
        )
    }

    try writeCampaignBundle(
        request: request,
        jobs: jobs,
        execution: execution,
        outputURL: outputURL,
        logger: logger
    )

    let summary = summarizeCampaign(
        runID: request.runID,
        preset: request.preset,
        executionMode: request.executionMode,
        jobs: jobs,
        runs: execution.runs,
        metrics: execution.metrics,
        events: execution.events,
        exportedCreatures: request.exportBest == nil ? 0 : min(execution.exportCandidates.count, request.exportBest ?? 0)
    )
    try writeResearchJSON(summary, to: outputURL.appendingPathComponent("summary.json"), prettyPrinted: true)
    try applyPromotionIfEnabled(
        config: request.promotion,
        runDir: outputURL.path,
        includeResults: true
    )

    return CampaignExecutionResult(
        jobs: jobs,
        runs: execution.runs,
        metrics: execution.metrics,
        events: execution.events,
        results: execution.results,
        ecologyArtifacts: execution.ecologyArtifacts,
        exportCandidates: execution.exportCandidates,
        summary: summary
    )
}

private func executeDistributedCampaignJobs(
    jobs: [LeniaCampaignJob],
    controllerHost: String,
    controllerPort: Int,
    bindHost: String,
    bindPort: Int,
    logger: Logger
) async throws -> [LeniaCampaignJobExecution] {
    let clientPort = try campaignBindPort(bindPort)
    let system = await ClusterSystem("LeniaHive") { settings in
        settings.bindHost = bindHost
        settings.bindPort = clientPort
        settings.swim.probeInterval = .seconds(1)
        settings.swim.pingTimeout = .milliseconds(500)
        settings.remoteCall.defaultTimeout = .seconds(600)
        settings.autoLeaderElection = .lowestReachable(minNumberOfMembers: 1)
    }
    system.cluster.join(endpoint: Cluster.Endpoint(host: controllerHost, port: controllerPort))

    let workers = try await discoverCampaignWorkers(system: system)
    guard !workers.isEmpty else {
        try system.shutdown()
        throw ValidationError("No workers discovered from controller \(controllerHost):\(controllerPort).")
    }
    let statuses = try await workers.asyncMap { try await $0.getStatus() }

    var executions: [LeniaCampaignJobExecution] = []
    for (index, job) in jobs.enumerated() {
        guard let selected = zip(workers, statuses).first(where: { workerSupportsCampaignJob($0.1, job: job) }) else {
            executions.append(failedCampaignExecution(job: job, message: "No worker supports requested backend \(job.backendRequest)."))
            continue
        }
        let worker = selected.0
        let status = selected.1
        guard let materialized = materializeCampaignJob(job, for: status.capabilities) else {
            executions.append(failedCampaignExecution(job: job, message: "Failed to materialize campaign backend \(job.backendRequest)."))
            continue
        }
        logger.info("Dispatching campaign job \(index + 1)/\(jobs.count) \(job.runID) to \(status.workerId)")
        do {
            let execution = try await worker.processCampaignJob(materialized)
            executions.append(execution)
        } catch {
            executions.append(failedCampaignExecution(job: materialized, message: String(describing: error), workerID: status.workerId))
        }
    }
    try system.shutdown()
    return executions
}

private func failedCampaignExecution(
    job: LeniaCampaignJob,
    message: String,
    workerID: String? = nil
) -> LeniaCampaignJobExecution {
    LeniaCampaignJobExecution(
        runs: [
            LeniaCampaignRunRecord(
                campaignID: job.campaignID,
                runID: job.runID,
                preset: job.preset,
                executor: job.executor,
                status: .failed,
                requestedBackend: job.backendRequest,
                actualBackend: nil,
                executionMode: job.executionMode,
                repeatIndex: job.repeatIndex,
                environmentLabel: job.environmentLabel,
                perturbationLabel: job.perturbationLabel,
                comparisonGroup: job.comparisonGroup,
                seedReference: job.seedReference,
                workerID: workerID,
                errorMessage: message
            )
        ],
        metrics: [],
        events: [],
        results: [],
        ecologyArtifacts: [],
        exportCandidates: []
    )
}

private func discoverCampaignWorkers(system: ClusterSystem) async throws -> [LeniaWorker] {
    actor WorkerCollector {
        var workers: [LeniaWorker] = []
        func add(_ worker: LeniaWorker) {
            workers.append(worker)
        }

        func snapshot() -> [LeniaWorker] {
            workers
        }
    }

    let collector = WorkerCollector()
    let task = Task {
        for await worker in await system.receptionist.listing(of: .leniaWorkers) {
            await collector.add(worker)
        }
    }
    defer { task.cancel() }
    for _ in 0..<30 {
        let discovered = await collector.snapshot()
        if !discovered.isEmpty {
            return discovered
        }
        try? await Task.sleep(for: .milliseconds(200))
    }
    return await collector.snapshot()
}

private func localCampaignCapabilities() -> WorkerBackendCapabilities {
    if MTLCreateSystemDefaultDevice() != nil {
        return WorkerBackendCapabilities(
            canonicalSearchBackends: [.mlx, .metalFull],
            canonicalFlowLeniaBackends: [.mlx, .metalFull],
            canonicalSearchPreferredBackend: .metalFull,
            canonicalFlowLeniaPreferredBackend: .metalFull
        )
    }
    return WorkerBackendCapabilities(
        canonicalSearchBackends: [.mlx],
        canonicalFlowLeniaBackends: [.mlx],
        canonicalSearchPreferredBackend: .mlx,
        canonicalFlowLeniaPreferredBackend: .mlx
    )
}

private func campaignBindPort(_ requestedPort: Int) throws -> Int {
    if requestedPort != 0 {
        return requestedPort
    }
    let socketFD = socket(AF_INET, SOCK_STREAM, 0)
    guard socketFD >= 0 else {
        throw ValidationError("Failed to allocate an ephemeral campaign client port.")
    }
    defer { close(socketFD) }

    var address = sockaddr_in()
    address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
    address.sin_family = sa_family_t(AF_INET)
    address.sin_port = in_port_t(0).bigEndian
    address.sin_addr = in_addr(s_addr: INADDR_ANY.bigEndian)

    let bindResult = withUnsafePointer(to: &address) { pointer -> Int32 in
        pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { sockaddrPointer in
            bind(socketFD, sockaddrPointer, socklen_t(MemoryLayout<sockaddr_in>.size))
        }
    }
    guard bindResult == 0 else {
        throw ValidationError("Failed to bind an ephemeral campaign client port.")
    }

    var boundAddress = sockaddr_in()
    var length = socklen_t(MemoryLayout<sockaddr_in>.size)
    let nameResult = withUnsafeMutablePointer(to: &boundAddress) { pointer -> Int32 in
        pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { sockaddrPointer in
            getsockname(socketFD, sockaddrPointer, &length)
        }
    }
    guard nameResult == 0 else {
        throw ValidationError("Failed to read the ephemeral campaign client port.")
    }
    return Int(UInt16(bigEndian: boundAddress.sin_port))
}

func summarizeCampaign(
    runID: String,
    preset: LeniaCampaignPreset,
    executionMode: LeniaCampaignExecutionMode,
    jobs: [LeniaCampaignJob],
    runs: [LeniaCampaignRunRecord],
    metrics: [LeniaCampaignMetricRecord],
    events: [LeniaCampaignEventRecord],
    exportedCreatures: Int
) -> CampaignSummaryFile {
    let backends = runs.reduce(into: [String: Int]()) { partial, run in
        guard let actualBackend = run.actualBackend else { return }
        partial[actualBackend, default: 0] += 1
    }
    return CampaignSummaryFile(
        schemaVersion: 1,
        runID: runID,
        preset: preset,
        executionMode: executionMode,
        totalJobs: jobs.count,
        completedRuns: runs.filter { $0.status == .completed }.count,
        failedRuns: runs.filter { $0.status == .failed }.count,
        metricRows: metrics.count,
        eventRows: events.count,
        exportedCreatures: exportedCreatures,
        backends: backends
    )
}

func writeCampaignBundle(
    request: CampaignExecutionRequest,
    jobs: [LeniaCampaignJob],
    execution: LeniaCampaignJobExecution,
    outputURL: URL,
    logger: Logger
) throws {
    let resolvedConfig = CampaignResolvedConfigFile(
        schemaVersion: 1,
        runID: request.runID,
        preset: request.preset,
        executionMode: request.executionMode,
        backendRequest: request.backendRequest,
        configPath: request.configURL.path,
        seedLibraryPath: request.seedLibraryURL?.path,
        exportBest: request.exportBest,
        promotedCompendiumPath: request.promotion.compendiumPath,
        promotedWarehousePath: request.promotion.warehousePath,
        promotedWarehouseTopology: request.promotion.warehouseTopology,
        jobs: jobs
    )
    try writeResearchJSON(resolvedConfig, to: outputURL.appendingPathComponent("resolved-config.json"), prettyPrinted: true)
    try writeResearchJSONLines(execution.runs, to: outputURL.appendingPathComponent("runs.jsonl"))
    try writeResearchJSONLines(execution.metrics, to: outputURL.appendingPathComponent("metrics.jsonl"))
    if !execution.events.isEmpty {
        try writeResearchJSONLines(execution.events, to: outputURL.appendingPathComponent("events.jsonl"))
    }
    if !execution.results.isEmpty {
        try writeResearchJSONLines(execution.results, to: outputURL.appendingPathComponent("results.jsonl"))
        let activityRecords = activitySummaryRecords(from: execution.results) { activity in
            guard !activity.isEmpty else { return nil }
            return summarizeCampaignActivity(activity)
        }
        if !activityRecords.isEmpty {
            try writeResearchJSONLines(activityRecords, to: outputURL.appendingPathComponent("activity.jsonl"))
        }
    }

    if !execution.ecologyArtifacts.isEmpty {
        let ecologyRunsDir = outputURL.appendingPathComponent("ecology-runs", isDirectory: true)
        try FileManager.default.createDirectory(at: ecologyRunsDir, withIntermediateDirectories: true)
        let encoder = campaignEncoder()
        var records: [FlowLeniaEcology2025RunRecord] = []
        for artifact in execution.ecologyArtifacts {
            let runDir = ecologyRunsDir.appendingPathComponent(artifact.runID, isDirectory: true)
            try FileManager.default.createDirectory(at: runDir, withIntermediateDirectories: true)
            try writeResearchJSON(artifact.summary, to: runDir.appendingPathComponent("summary.json"), prettyPrinted: true)
            try writeResearchJSONLines(artifact.frames, to: runDir.appendingPathComponent("frames.jsonl"))
            if let activitySummary = artifact.activitySummary {
                try writeResearchJSON(activitySummary, to: runDir.appendingPathComponent("activity-summary.json"), prettyPrinted: true)
            }
            records.append(try writeFlowLeniaEcology2025RunArtifacts(
                runDirectory: runDir,
                runID: artifact.runID,
                campaignID: request.runID,
                replayBaseConfig: artifact.replayBaseConfig,
                replayPayload: artifact.replayPayload,
                runSummary: artifact.summary,
                trajectoryFrames: artifact.trajectoryFrames,
                activitySummary: artifact.activitySummary,
                exportedAt: Date(),
                encoder: encoder
            ))
        }
        try writeFlowLeniaEcology2025RunIndex(
            records: records,
            to: ecologyRunsDir.appendingPathComponent("index.jsonl")
        )
    }

    if let exportBest = request.exportBest, exportBest > 0 {
        let selected = execution.exportCandidates
            .sorted { ($0.result.score ?? -.infinity) > ($1.result.score ?? -.infinity) }
            .prefix(exportBest)
        let selectedCandidates = Array(selected)
        if !selectedCandidates.isEmpty {
            let entries = selectedCandidates.map { candidate in
                archiveResearchLibraryEntry(
                    creature: candidate.creature,
                    runId: candidate.runID,
                    configHash: candidate.configHash,
                    campaignId: request.runID
                )
            }
            let archiveArtifacts = try persistResearchArchiveArtifacts(
                runDirectory: outputURL,
                libraryEntries: entries,
                exportRoot: outputURL.appendingPathComponent("exports", isDirectory: true),
                exportItems: selectedCandidates,
                emptyExportMessage: "Replay export bundle already exists for the selected campaign artifacts."
            ) { candidate in
                (
                    baseConfig: candidate.baseConfig,
                    searchConfig: candidate.searchConfig,
                    creature: candidate.creature,
                    runId: candidate.runID,
                    campaignId: nil,
                    score: candidate.result.score,
                    filtersPassed: candidate.result.filtersPassed,
                    reason: "campaign"
                )
            }
            logger.info("Campaign exported \(archiveArtifacts.exportCount) creatures")
        }
    }
}

func runCampaignCompendiumIndex(
    outputURL: URL,
    compendiumPath: String? = nil,
    warehousePath: String? = nil,
    warehouseTopology: Bool = false
) throws {
    try applyPromotionIfEnabled(
        config: ArchivePromotionConfig(
            compendiumPath: compendiumPath ?? outputURL.appendingPathComponent("compendium.sqlite").path,
            warehousePath: warehousePath,
            warehouseTopology: warehouseTopology
        ),
        runDir: outputURL.path,
        includeResults: true
    )
}

func phasePromotionConfig(outputURL: URL) -> ArchivePromotionConfig {
    ArchivePromotionConfig(
        compendiumPath: outputURL.appendingPathComponent("compendium.sqlite").path,
        warehousePath: nil,
        warehouseTopology: false
    )
}

func resolveCampaignCentralCompendiumPath(
    promotedPath: String?,
    configuredPath: String?,
    outputURL: URL,
    campaignConfigDirectory: URL,
    dossierRoot: URL
) throws -> String {
    if let promotedPath {
        return promotedPath
    }
    guard let configuredPath else {
        return outputURL.appendingPathComponent("compendium.sqlite").path
    }

    let rawPath = normalized(configuredPath) ?? configuredPath
    let artifactPath = try resolveArtifactPath(rawPath, dossier: dossierName)
    if artifactPath != rawPath || rawPath.hasPrefix("/") || rawPath.hasPrefix("~") {
        return artifactPath
    }
    return resolveCampaignRelativePath(
        rawPath,
        configDirectory: campaignConfigDirectory,
        dossierRoot: dossierRoot
    ).path
}

func mergeCompendiumDatabases(sources: [URL], into centralPath: String, logger: Logger) throws {
    let fileManager = FileManager.default
    let existingSources = sources.filter { fileManager.fileExists(atPath: $0.path) }
    guard !existingSources.isEmpty else {
        logger.info("No phase compendium databases to merge")
        return
    }

    let centralDir = URL(fileURLWithPath: centralPath).deletingLastPathComponent()
    try fileManager.createDirectory(at: centralDir, withIntermediateDirectories: true)

    let tables = ["runs", "campaigns", "creatures", "exports", "results", "ecology_runs"]

    if !fileManager.fileExists(atPath: centralPath) {
        try fileManager.copyItem(atPath: existingSources[0].path, toPath: centralPath)
        logger.info("Initialized central compendium from \(existingSources[0].lastPathComponent)")
    }

    let db = try SQLiteDB(path: centralPath)
    for source in existingSources {
        let alias = "phase_db"
        let escaped = source.path.replacingOccurrences(of: "'", with: "''")
        try db.exec("ATTACH DATABASE '\(escaped)' AS \(alias)")
        defer { try? db.exec("DETACH DATABASE \(alias)") }

        try db.withImmediateTransaction {
            for table in tables {
                let existsInSource = try db.scalarInt(
                    "SELECT count(*) FROM \(alias).sqlite_master WHERE type='table' AND name='\(table)'"
                )
                guard existsInSource > 0 else { continue }
                let existsInCentral = try db.tableExists(table)
                guard existsInCentral else { continue }

                let centralColumns = try db.tableColumns(table)
                let stmtHandle = try db.prepare("PRAGMA \(alias).table_info(\(table))")
                defer { sqlite3_finalize(stmtHandle) }
                var sourceColumns: [String] = []
                while sqlite3_step(stmtHandle) == SQLITE_ROW {
                    guard let nameC = sqlite3_column_text(stmtHandle, 1) else { continue }
                    sourceColumns.append(String(cString: nameC))
                }
                let shared = sourceColumns.filter { centralColumns.contains($0) }
                guard !shared.isEmpty else { continue }

                let columnList = shared.joined(separator: ", ")
                try db.exec("""
                    INSERT OR IGNORE INTO main.\(table) (\(columnList))
                    SELECT \(columnList) FROM \(alias).\(table)
                """)
            }
        }
        logger.info("Merged \(source.lastPathComponent) into central compendium")
    }
}

private func summarizeCampaignActivity(_ activity: [ActivitySnapshot]) -> ActivitySummary {
    let steps = activity.map(\.step)
    let speciesCount = activity.map { Float($0.components.count) }
    let eap = speciesCount.map { $0 > 0 ? Float(1) : Float(0) }
    let eac = speciesCount
    let ean = speciesCount.map { $0 > 0 ? Float(1) : Float(0) }
    let diversity = speciesCount.map { count in
        guard count > 0 else { return Float(0) }
        return log(Float(count) + 1)
    }
    return ActivitySummary(
        steps: steps,
        eap: eap,
        eac: eac,
        ean: ean,
        diversity: diversity,
        speciesCount: speciesCount.map(Int.init)
    )
}

private func campaignEncoder() -> JSONEncoder {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    return encoder
}

private extension Array {
    func asyncMap<T>(_ transform: @escaping (Element) async throws -> T) async rethrows -> [T] {
        var values: [T] = []
        values.reserveCapacity(count)
        for element in self {
            values.append(try await transform(element))
        }
        return values
    }
}
