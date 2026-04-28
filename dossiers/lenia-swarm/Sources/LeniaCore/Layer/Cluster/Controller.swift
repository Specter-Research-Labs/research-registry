import Distributed
@preconcurrency import DistributedCluster
import Foundation
import Logging

private struct CampaignRuntimeArtifacts {
    let outputDir: URL
    var topResults: [SimulationResultData]
    var resultCount: Int
    var failedJobs: Int
    let startTime: Date
}

private struct ResultArtifactSummary: Encodable {
    let totalSeeds: Int
    let totalJobs: Int
    let completedJobs: Int
    let failedJobs: Int
    let resultsCount: Int
    let topCount: Int
    let elapsedSeconds: Double
    let seedsPerSecond: Double
    let workersUsed: Int

    enum CodingKeys: String, CodingKey {
        case totalSeeds = "total_seeds"
        case totalJobs = "total_jobs"
        case completedJobs = "completed_jobs"
        case failedJobs = "failed_jobs"
        case resultsCount = "results_count"
        case topCount = "top_count"
        case elapsedSeconds = "elapsed_seconds"
        case seedsPerSecond = "seeds_per_second"
        case workersUsed = "workers_used"
    }
}

public distributed actor SwarmController {
    public typealias ActorSystem = ClusterSystem

    private let system: ClusterSystem
    private let baseConfig: LeniaBaseConfig
    private let searchConfig: ParsedSearchConfig
    private let outputDir: URL
    private let overallOutputDir: URL
    private let campaignOutputRoot: URL
    private let libraryOutputDir: URL
    private let exportOutputDir: URL
    private let seedsPerJob: Int
    private let totalSeeds: Int
    private let topK: Int
    private let logger: Logger
    private let runContext: RunContext
    private let collectionConfig: CollectionConfig

    private var jobQueue: [SimulationJob]
    private var pendingJobs: [String: SimulationJob] = [:]
    private var completedJobCount = 0
    private var failedJobCount = 0
    private var processedSeedCount = 0
    private var overallResultCount = 0
    private var workers: [LeniaWorker] = []
    private var workerIdMap: [String: LeniaWorker] = [:]
    private var lastKnownWorkerStatuses: [WorkerStatus] = []
    private var currentTopResults: [SimulationResultData] = []
    private var workerTasks: [ObjectIdentifier: Task<Void, Never>] = [:]
    private var isShuttingDown = false
    private var creatureLibrary: [SavedCreature] = []
    private var activeArenas: [UUID: ArenaHost] = [:]
    private var activeCampaigns: [UUID: CampaignStatus] = [:]
    private var campaignJobMapping: [String: UUID] = [:]
    private var campaignWorkers: [UUID: Set<String>] = [:]  // Campaign ID -> Worker IDs who joined
    private var workerCampaignAssignments: [String: UUID] = [:]
    private var campaignJobQueues: [UUID: [SimulationJob]] = [:]  // Separate job queues per campaign
    private var campaignArtifacts: [UUID: CampaignRuntimeArtifacts] = [:]
    private var appendJSONLHandles: [URL: FileHandle] = [:]

    private let startTime = Date()
    private let totalJobsCreated: Int

    // Event continuation (dependency injected from host for local event listening)
    private let eventContinuation: AsyncStream<ControllerEvent>.Continuation?

    public init(
        system: ClusterSystem,
        baseConfigPath: String,
        searchConfigPath: String,
        outputDir: String,
        seedsPerJob: Int,
        runContext: RunContext,
        logger: Logger,
        eventContinuation: AsyncStream<ControllerEvent>.Continuation? = nil
    ) throws {
        try self.init(
            system: system,
            bootstrap: try SwarmControllerBootstrap.load(
                baseConfigPath: baseConfigPath,
                searchConfigPath: searchConfigPath,
                seedsPerJob: seedsPerJob
            ),
            outputRoot: outputDir,
            runContext: runContext,
            logger: logger,
            eventContinuation: eventContinuation
        )
    }

    // Struct-based initializer for in-memory configuration (used by Studio)
    public init(
        system: ClusterSystem,
        baseConfig: LeniaBaseConfig,
        searchConfig: ParsedSearchConfig,
        outputDir: String,
        seedsPerJob: Int,
        runContext: RunContext,
        logger: Logger,
        eventContinuation: AsyncStream<ControllerEvent>.Continuation? = nil
    ) throws {
        try self.init(
            system: system,
            bootstrap: SwarmControllerBootstrap(
                baseConfig: baseConfig,
                searchConfig: searchConfig,
                seedsPerJob: seedsPerJob
            ),
            outputRoot: outputDir,
            runContext: runContext,
            logger: logger,
            eventContinuation: eventContinuation
        )
    }

    private init(
        system: ClusterSystem,
        bootstrap: SwarmControllerBootstrap,
        outputRoot: String,
        runContext: RunContext,
        logger: Logger,
        eventContinuation: AsyncStream<ControllerEvent>.Continuation?
    ) throws {
        self.actorSystem = system
        self.system = system

        let outputLayout = SwarmControllerOutputLayout(outputRoot: outputRoot)
        self.outputDir = outputLayout.outputDir
        self.overallOutputDir = outputLayout.overallOutputDir
        self.campaignOutputRoot = outputLayout.campaignOutputRoot
        self.libraryOutputDir = outputLayout.libraryOutputDir
        self.exportOutputDir = outputLayout.exportOutputDir
        self.baseConfig = bootstrap.baseConfig
        self.searchConfig = bootstrap.searchConfig
        self.seedsPerJob = bootstrap.seedsPerJob
        self.totalSeeds = bootstrap.totalSeeds
        self.topK = bootstrap.topK
        self.logger = logger
        self.runContext = runContext
        self.collectionConfig = bootstrap.collectionConfig
        self.eventContinuation = eventContinuation

        try outputLayout.createDirectories()

        self.jobQueue = bootstrap.jobQueue
        self.totalJobsCreated = bootstrap.jobQueue.count
        logger.info("Created \(bootstrap.jobQueue.count) jobs for \(bootstrap.totalSeeds) seeds")

        Task {
            await system.receptionist.checkIn(self, with: .leniaController)
        }
    }

    public distributed func start() async {
        logger.info("Waiting for workers...")

        // Load existing library from disk
        loadLibrary()

        // Capture system reference for Tasks
        let clusterSystem = self.system

        Task {
            for await worker in await clusterSystem.receptionist.listing(of: .leniaWorkers) {
                await self.workerJoined(worker)
            }
        }

        Task {
            for await event in clusterSystem.cluster.events {
                self.handleClusterEvent(event)
            }
        }
    }

    private func workerJoined(_ worker: LeniaWorker) async {
        guard !isShuttingDown else { return }

        workers.append(worker)

        // Get worker ID and store in lookup map
        let workerStatus = try? await worker.getStatus()
        if let status = workerStatus {
            workerIdMap[status.workerId] = worker
            logger.info("Worker \(status.workerId) joined. Total workers: \(workers.count)")
        } else {
            logger.info("Worker joined. Total workers: \(workers.count)")
        }

        do {
            try await worker.updateRunContext(runContext)
        } catch {
            logger.error("Failed to update run context for worker: \(error)")
        }

        // Send existing library to new worker
        if !creatureLibrary.isEmpty {
            await broadcastFullLibrary(to: worker)
        }

        // Send existing arenas to new worker
        for (_, host) in activeArenas {
            if let state = try? await host.getState() {
                try? await worker.receiveArenaInvite(state.config)
            }
        }

        // Broadcast updated worker list
        await broadcastWorkerList()

        let task = Task {
            await self.dispatchLoop(for: worker, status: workerStatus)
        }
        workerTasks[ObjectIdentifier(worker)] = task
    }

    private func dispatchLoop(for worker: LeniaWorker, status: WorkerStatus?) async {
        while !isShuttingDown {
            guard let job = reserveNextDispatchJob(for: status) else {
                if isDone() {
                    break
                }
                try? await Task.sleep(for: .milliseconds(500))
                continue
            }

            markJobPending(job)

            do {
                let result = try await worker.process(job: job)
                handleResult(result, for: job)
            } catch {
                logger.error("Worker error for job \(job.id): \(error)")
                requeueJob(job)

                if error is ClusterSystemError {
                    break
                }
            }
        }
    }

    private func reserveNextDispatchJob(for workerStatus: WorkerStatus?) -> SimulationJob? {
        if let workerId = workerStatus?.workerId,
           let campaignId = workerCampaignAssignments[workerId] {
            return reserveNextCampaignJob(campaignId: campaignId, for: workerStatus)
        }
        return reserveCompatibleSimulationJob(from: &jobQueue, for: workerStatus)
    }

    private func reserveNextCampaignJob(campaignId: UUID, for workerStatus: WorkerStatus?) -> SimulationJob? {
        guard var jobs = campaignJobQueues[campaignId] else { return nil }
        let job = reserveCompatibleSimulationJob(from: &jobs, for: workerStatus)
        campaignJobQueues[campaignId] = jobs
        return job
    }

    private func markJobPending(_ job: SimulationJob) {
        pendingJobs[job.id] = job
    }

    private func handleResult(_ result: SimulationResult, for job: SimulationJob) {
        pendingJobs.removeValue(forKey: job.id)

        LeniaMetrics.timing(
            "job_duration_seconds",
            result.durationSeconds,
            fields: [
                "job_id": job.id,
                "worker_id": result.workerId,
                "success": result.success ? "true" : "false"
            ]
        )

        let campaignId = campaignJobMapping[job.id]

        if result.success {
            if campaignId == nil {
                completedJobCount += 1
                processedSeedCount += job.count
            }
            LeniaMetrics.counter(
                "jobs_completed_total",
                1.0,
                fields: [
                    "job_id": job.id,
                    "worker_id": result.workerId
                ]
            )
            LeniaMetrics.counter(
                "seeds_processed_total",
                Double(job.count),
                fields: [
                    "job_id": job.id,
                    "worker_id": result.workerId
                ]
            )

            let results = result.results
            for obj in results {
                if shouldCollect(obj) {
                    let score = obj.score
                    let filtersPassed = obj.filtersPassed
                    let creature = savedCreatureFromResult(
                        name: generateCreatureName(),
                        ownerId: result.workerId,
                        result: obj,
                        initialCondition: InitConfig(
                            seed: obj.initSeed,
                            patches: job.baseConfig.`init`.patches,
                            a_uniform: job.baseConfig.`init`.a_uniform,
                            p_uniform: job.baseConfig.`init`.p_uniform,
                            state_patch: job.baseConfig.`init`.state_patch,
                            p_state_patch: job.baseConfig.`init`.p_state_patch
                        ),
                        scoreWeights: obj.scoreWeights ?? searchConfig.scoreWeights
                    )
                    Task {
                        let added = await self.addToLibrary(creature, campaignId: campaignId)
                        if added && self.collectionConfig.exportEnabled {
                            do {
                                _ = try self.exportCreatureInternal(
                                    creature,
                                    campaignId: campaignId,
                                    score: score,
                                    filtersPassed: filtersPassed,
                                    reason: "auto"
                                )
                            } catch {
                                self.logger.error("Auto-export failed: \(error)")
                            }
                        }
                    }
                }
            }

            if let campaignId = campaignId {
                recordCampaignResults(
                    campaignId: campaignId,
                    results: results
                )
            } else {
                recordOverallResults(results: results)
            }

            emitProgress()

            if isDone() {
                Task {
                    await aggregateResults()
                }
            }
        } else {
            logger.warning("Job \(job.id) failed: \(result.errorMessage ?? "unknown")")
            if let campaignId = campaignId {
                updateCampaignArtifacts(campaignId) { $0.failedJobs += 1 }
            } else {
                failedJobCount += 1
            }
            LeniaMetrics.counter(
                "jobs_failed_total",
                1.0,
                fields: [
                    "job_id": job.id,
                    "worker_id": result.workerId
                ]
            )
        }

        if let campaignId = campaignId {
            updateCampaignProgress(campaignId: campaignId, jobId: job.id, seedCount: job.count, success: result.success)
        }
    }

    private func addToLibrary(_ creature: SavedCreature, campaignId: UUID?) async -> Bool {
        // Deduplicate by checking if similar creature exists (same genotype seed)
        guard !creatureLibrary.contains(where: { $0.id == creature.id }) else { return false }

        creatureLibrary.append(creature)
        saveLibrary()
        recordLibraryEntry(creature, campaignId: campaignId)

        logger.info("Creature discovered: \(creature.name) (gyration: \(String(format: "%.1f", creature.metrics.gyration)), velocity: \(String(format: "%.2f", creature.metrics.centerVelocity)))")

        // Notify host UI via event stream
        eventContinuation?.yield(.creatureDiscovered(creature))

        // Broadcast to all workers
        for worker in workers {
            Task {
                do {
                    try await worker.receiveLibraryUpdate(.creatureAdded(creature))
                } catch {
                    self.logger.error("Failed to send library update: \(error)")
                }
            }
        }
        return true
    }

    private func generateCreatureName() -> String {
        let adjectives = ["ancient", "crystal", "ethereal", "flowing", "glowing", "harmonic",
                          "luminous", "mystic", "pulsing", "radiant", "serene", "vibrant"]
        let nouns = ["amoeba", "blob", "cell", "dancer", "entity", "form",
                     "glider", "orbiter", "pattern", "pulse", "spiral", "walker"]
        let adj = adjectives.randomElement() ?? "unknown"
        let noun = nouns.randomElement() ?? "creature"
        let id = String(format: "%04d", Int.random(in: 0...9999))
        return "\(adj)-\(noun)-\(id)"
    }

    private func requeueJob(_ job: SimulationJob) {
        pendingJobs.removeValue(forKey: job.id)
        let restoredJob = restoreRequestedBackend(for: job)
        if let campaignId = campaignJobMapping[job.id] {
            campaignJobQueues[campaignId, default: []].insert(restoredJob, at: 0)
        } else {
            jobQueue.insert(restoredJob, at: 0)
        }
        logger.info("Requeued job \(job.id)")
    }

    private func handleClusterEvent(_ event: Cluster.Event) {
        switch event {
        case .membershipChange(let change):
            if change.status == .down || change.status == .removed {
                if isShuttingDown { return }
                if change.member.node == system.cluster.node { return }
                logger.warning("Node went down: \(change.member.node)")
            }
        default:
            break
        }
    }

    private func isDone() -> Bool {
        guard jobQueue.isEmpty && pendingJobs.isEmpty else { return false }
        for (_, jobs) in campaignJobQueues {
            if !jobs.isEmpty { return false }
        }
        for (_, status) in activeCampaigns {
            if status.isRunning { return false }
        }
        return true
    }

    private func emitProgress() {
        let completed = completedJobCount
        let elapsed = Date().timeIntervalSince(startTime)
        let seedsCompleted = processedSeedCount
        let rate = elapsed > 0 ? Double(seedsCompleted) / elapsed : 0

        eventContinuation?.yield(.progress(
            completed: completed,
            total: totalJobsCreated,
            seeds: seedsCompleted,
            totalSeeds: totalSeeds,
            rate: rate
        ))

        LeniaMetrics.gauge("jobs_completed", Double(completed))
        LeniaMetrics.gauge("jobs_failed", Double(failedJobCount))
        LeniaMetrics.gauge("jobs_pending", Double(pendingJobs.count))
        LeniaMetrics.gauge("jobs_queued", Double(jobQueue.count))
        LeniaMetrics.gauge("seeds_processed", Double(seedsCompleted))
        LeniaMetrics.gauge("seeds_per_second", rate)
        LeniaMetrics.gauge("workers_connected", Double(workers.count))

        // Broadcast global update to all workers periodically
        Task { await broadcastGlobalUpdate() }
    }

    private func broadcastGlobalUpdate() async {
        guard !isShuttingDown else { return }
        // Use cached top results instead of re-parsing all completed results
        let top = Array(currentTopResults.prefix(topK))
        let totalProcessed = processedSeedCount

        let update = GlobalUpdate(topCreatures: top, totalSeedsProcessed: totalProcessed)

        logger.info("Broadcasting GlobalUpdate to \(workers.count) workers: \(top.count) creatures, \(totalProcessed) seeds")

        for worker in workers {
            if isShuttingDown { return }
            do {
                try await worker.receiveGlobalUpdate(update)
                self.logger.debug("Successfully sent GlobalUpdate to worker")
            } catch {
                if isShuttingDown {
                    self.logger.debug("Skipping GlobalUpdate during shutdown")
                    return
                }
                self.logger.error("Failed to send GlobalUpdate to worker: \(error)")
            }
        }

        await broadcastClusterSummary()
    }

    private func shouldCollect(_ result: SimulationResultData) -> Bool {
        guard collectionConfig.enabled else { return false }
        if collectionConfig.requireStable && !result.metrics.isStable { return false }
        if collectionConfig.requireFiltersPassed && !result.filtersPassed { return false }
        if let minScore = collectionConfig.minScore {
            guard let score = result.score, score >= minScore else { return false }
        }
        return true
    }

    // MARK: - Creature Library Management

    private func loadLibrary() {
        let url = libraryOutputDir.appendingPathComponent("library.json")
        if let data = try? Data(contentsOf: url),
           let saved = try? JSONDecoder().decode([SavedCreature].self, from: data) {
            self.creatureLibrary = saved
            logger.info("Loaded \(saved.count) creatures from library")
            rebuildLibraryIndexIfMissing()
        }
    }

    private func saveLibrary() {
        let url = libraryOutputDir.appendingPathComponent("library.json")
        if let data = try? JSONEncoder().encode(creatureLibrary) {
            try? data.write(to: url)
        }
    }

    private func recordLibraryEntry(_ creature: SavedCreature, campaignId: UUID?) {
        let entry = archiveResearchLibraryEntry(
            creature: creature,
            runId: runContext.runId,
            configHash: creature.configHash,
            campaignId: campaignId?.uuidString
        )
        appendJSONL(entry, to: libraryIndexURL())
        if let campaignId = campaignId,
           let outputDir = campaignArtifacts[campaignId]?.outputDir {
            let campaignURL = outputDir.appendingPathComponent("library.jsonl")
            appendJSONL(entry, to: campaignURL)
        }
    }

    private func libraryIndexURL() -> URL {
        libraryOutputDir.appendingPathComponent("index.jsonl")
    }

    private func rebuildLibraryIndexIfMissing() {
        let indexURL = libraryIndexURL()
        guard !FileManager.default.fileExists(atPath: indexURL.path) else { return }
        logger.info("Library index missing; rebuilding with campaign_id=null")
        for creature in creatureLibrary {
            recordLibraryEntry(creature, campaignId: nil)
        }
    }

    public distributed func submitCreature(_ creature: SavedCreature) async {
        let added = await addToLibrary(creature, campaignId: nil)
        if added {
            logger.info("New creature added: \(creature.name) by \(creature.ownerId)")
        } else {
            logger.debug("Creature \(creature.name) already in library")
        }
    }

    public func getLibrary() -> [SavedCreature] {
        return creatureLibrary
    }

    private func broadcastFullLibrary(to worker: LeniaWorker) async {
        do {
            try await worker.receiveLibraryUpdate(.fullSync(creatureLibrary))
            logger.debug("Sent full library sync to new worker")
        } catch {
            logger.error("Failed to send library sync to worker: \(error)")
        }
    }

    public distributed func exportCreature(_ creature: SavedCreature, reason: String = "manual") async throws -> String {
        return try exportCreatureInternal(
            creature,
            campaignId: nil,
            score: nil,
            filtersPassed: nil,
            reason: reason
        )
    }

    private func exportCreatureInternal(
        _ creature: SavedCreature,
        campaignId: UUID?,
        score: Float?,
        filtersPassed: Bool?,
        reason: String
    ) throws -> String {
        let exportRoot = try exportRoot(for: campaignId)
        let exportDir = replayExportDirectory(root: exportRoot, creature: creature)
        guard let artifacts = try writeReplayExportArtifacts(
            exportRoot: exportRoot,
            baseConfig: baseConfig,
            searchConfig: searchConfig,
            creature: creature,
            runId: runContext.runId,
            campaignId: campaignId,
            score: score,
            filtersPassed: filtersPassed,
            reason: reason
        ) else {
            return exportDir.path
        }

        appendJSONL(artifacts.record, to: exportIndexURL())
        if let campaignId = campaignId,
           let campaignDir = campaignArtifacts[campaignId]?.outputDir {
            let campaignIndex = campaignDir.appendingPathComponent("exports").appendingPathComponent("index.jsonl")
            appendJSONL(artifacts.record, to: campaignIndex)
        }

        return artifacts.exportDir.path
    }

    private func exportRoot(for campaignId: UUID?) throws -> URL {
        if let campaignId = campaignId,
           let campaignDir = campaignArtifacts[campaignId]?.outputDir {
            let campaignExportDir = campaignDir.appendingPathComponent("exports")
            try FileManager.default.createDirectory(at: campaignExportDir, withIntermediateDirectories: true)
            return campaignExportDir
        }
        return exportOutputDir
    }

    private func exportIndexURL() -> URL {
        exportOutputDir.appendingPathComponent("index.jsonl")
    }

    private func aggregateResults() async {
        logger.info("Aggregating results...")

        let elapsed = Date().timeIntervalSince(startTime)

        let resultsURL = overallOutputDir.appendingPathComponent("results.jsonl")
        if !FileManager.default.fileExists(atPath: resultsURL.path) {
            FileManager.default.createFile(atPath: resultsURL.path, contents: nil)
        }
        let top = Array(currentTopResults.prefix(topK))
        finalizeResultArtifacts(
            outputDir: overallOutputDir,
            topResults: top,
            summary: ResultArtifactSummary(
                totalSeeds: totalSeeds,
                totalJobs: totalJobsCreated,
                completedJobs: completedJobCount,
                failedJobs: failedJobCount,
                resultsCount: overallResultCount,
                topCount: top.count,
                elapsedSeconds: elapsed,
                seedsPerSecond: elapsed > 0 ? Double(totalSeeds) / elapsed : 0,
                workersUsed: workers.count
            ),
            closeHandles: [
                overallOutputDir.appendingPathComponent("results.jsonl"),
                overallOutputDir.appendingPathComponent("activity.jsonl"),
                libraryIndexURL(),
                exportIndexURL()
            ]
        )

        logger.info("Done! Total time: \(String(format: "%.1f", elapsed))s")
        logger.info("Results: \(resultsURL.path)")
        logger.info("Top \(topK): \(overallOutputDir.appendingPathComponent("top.json").path)")

        // Final broadcast before shutdown
        await broadcastGlobalUpdate()
        closeAllAppendJSONLHandles()

        isShuttingDown = true

        eventContinuation?.yield(.finished(elapsed: elapsed))
    }

    public func getStatus() -> (completed: Int, pending: Int, queued: Int, failed: Int, workers: Int) {
        return (
            completedJobCount, pendingJobs.count, jobQueue.count, failedJobCount,
            workers.count
        )
    }

    // MARK: - Arena Management

    public distributed func createArena(size: Int, maxPlayers: Int) async throws -> UUID {
        let config = ArenaConfig(size: size, maxPlayers: maxPlayers)
        let host = ArenaHost(system: system, config: config)
        activeArenas[config.id] = host

        logger.info("Created arena \(config.id) with size \(size)x\(size), max players: \(maxPlayers)")

        for worker in workers {
            Task {
                do {
                    try await worker.receiveArenaInvite(config)
                } catch {
                    self.logger.error("Failed to send arena invite: \(error)")
                }
            }
        }

        return config.id
    }

    public distributed func startArena(id: UUID) async {
        guard let host = activeArenas[id] else {
            logger.warning("Arena \(id) not found")
            return
        }
        logger.info("Starting arena \(id)")
        try? await host.start()
    }

    public distributed func stopArena(id: UUID) async {
        guard let host = activeArenas[id] else { return }
        let config = try? await host.getState().config
        try? await host.stop()
        activeArenas.removeValue(forKey: id)
        logger.info("Stopped arena \(id)")

        if let config = config {
            let endedState = ArenaState(config: config, status: .ended, participants: [])
            for worker in workers {
                Task {
                    try? await worker.receiveArenaState(endedState)
                }
            }
        }
    }

    public distributed func triggerMutationInArena(id: UUID, strength: Float = 0.05) async {
        guard let host = activeArenas[id] else {
            logger.warning("Arena \(id) not found for mutation event")
            return
        }
        logger.info("Triggering mutation in arena \(id)")
        try? await host.triggerMutationEvent(strength: strength)
    }

    public distributed func requestJoinArena(workerId: String, arenaId: UUID, creature: SavedCreature) async -> Bool {
        guard let host = activeArenas[arenaId] else {
            logger.warning("Arena \(arenaId) not found for join request")
            return false
        }
        guard let worker = workerIdMap[workerId] else {
            logger.warning("Worker \(workerId) not found for join request")
            return false
        }

        do {
            let success = try await host.join(worker: worker, workerId: workerId, creature: creature)
            if success {
                logger.info("Worker \(workerId) joined arena \(arenaId)")
            }
            return success
        } catch {
            logger.error("Failed to join arena: \(error)")
            return false
        }
    }

    public func getArenaState(id: UUID) async -> ArenaState? {
        guard let host = activeArenas[id] else { return nil }
        return try? await host.getState()
    }

    public func getActiveArenas() -> [UUID] {
        return Array(activeArenas.keys)
    }

    // MARK: - Campaign/Sweep Management

    public distributed func startSweep(config: SweepJobConfig) async throws -> UUID {
        isShuttingDown = false
        let campaignId = UUID()
        logger.info("Creating new sweep campaign: \(config.name) (waiting for workers to join)")

        let sweepBaseConfig = baseConfigForSweep(config: config)
        let campaignOutputDir: URL
        do {
            campaignOutputDir = try makeCampaignOutputDir(config: config, campaignId: campaignId)
            campaignArtifacts[campaignId] = CampaignRuntimeArtifacts(
                outputDir: campaignOutputDir,
                topResults: [],
                resultCount: 0,
                failedJobs: 0,
                startTime: Date()
            )
            try writeCampaignConfigSnapshots(
                baseConfig: sweepBaseConfig,
                searchConfig: searchConfig,
                config: config,
                outputDir: campaignOutputDir
            )
            try FileManager.default.createDirectory(
                at: campaignOutputDir.appendingPathComponent("exports"),
                withIntermediateDirectories: true
            )
        } catch {
            campaignArtifacts.removeValue(forKey: campaignId)
            throw ControllerError.outputDirFailed(error.localizedDescription)
        }

        let jobCount = (config.totalSeeds + config.seedsPerChunk - 1) / config.seedsPerChunk
        var currentSeed = Int.random(in: 0...100000)
        let seedStride = searchConfig.seedStride
        let sweepOverrides: [String: Double] = [
            "run.steps": Double(config.steps),
            "grid.sx": Double(config.gridWidth),
            "grid.sy": Double(config.gridHeight)
        ]

        var campaignJobs: [SimulationJob] = []
        for i in 0..<jobCount {
            let count = min(config.seedsPerChunk, config.totalSeeds - (i * config.seedsPerChunk))
            let jobId = "\(campaignId.uuidString.prefix(8))-\(i)"

            let job = SimulationJob(
                id: jobId,
                seedStart: currentSeed,
                count: count,
                baseConfig: sweepBaseConfig,
                searchConfig: searchConfig,
                sweepOverrides: sweepOverrides
            )
            campaignJobs.append(job)
            campaignJobMapping[jobId] = campaignId
            currentSeed += count * seedStride
        }

        campaignJobQueues[campaignId] = campaignJobs
        campaignWorkers[campaignId] = []

        let status = CampaignStatus(
            id: campaignId,
            name: config.name,
            totalJobs: jobCount,
            completedJobs: 0,
            totalSeeds: config.totalSeeds,
            processedSeeds: 0,
            isRunning: false,
            joinedWorkers: [],
            outputDir: campaignOutputDir.path
        )
        activeCampaigns[campaignId] = status

        broadcastCampaigns()

        return campaignId
    }

    private func baseConfigForSweep(config: SweepJobConfig) -> LeniaBaseConfig {
        if config.gridWidth == baseConfig.grid.sx && config.gridHeight == baseConfig.grid.sy {
            return baseConfig
        }

        let grid = GridConfig(sx: config.gridWidth, sy: config.gridHeight)
        var initConfig = baseConfig.`init`

        if baseConfig.profile == .paper {
            let center = [config.gridWidth / 2, config.gridHeight / 2]
            let patchSize = initConfig.patches.first?.size ?? 40
            initConfig = InitConfig(
                seed: initConfig.seed,
                patches: [PatchConfig(center: center, size: patchSize)],
                a_uniform: initConfig.a_uniform,
                p_uniform: initConfig.p_uniform,
                state_patch: initConfig.state_patch,
                p_state_patch: initConfig.p_state_patch
            )
        }

        let chemotaxis: ChemotaxisConfig? = {
            guard baseConfig.profile == .paper,
                  let chem = baseConfig.chemotaxis,
                  chem.enabled else {
                return baseConfig.chemotaxis
            }
            let center = [Float(config.gridWidth) / 2.0, Float(config.gridHeight) / 2.0]
            return ChemotaxisConfig(
                enabled: chem.enabled,
                channel_index: chem.channel_index,
                mode: chem.mode,
                sigma: chem.sigma,
                amplitude: chem.amplitude,
                include_in_mass: chem.include_in_mass,
                center: center,
                circle_radius: chem.circle_radius,
                seed: chem.seed
            )
        }()

        return LeniaBaseConfig(
            backend: baseConfig.backend,
            profile: baseConfig.profile,
            grid: grid,
            channels: baseConfig.channels,
            connectivity: baseConfig.connectivity,
            flow: baseConfig.flow,
            implementation: baseConfig.implementation,
            reintegration: baseConfig.reintegration,
            parameter_embedding: baseConfig.parameter_embedding,
            chemotaxis: chemotaxis,
            food: baseConfig.food,
            walls: baseConfig.walls,
            params: baseConfig.params,
            init: initConfig,
            run: baseConfig.run,
            interventions: baseConfig.interventions
        )
    }

    private func makeCampaignOutputDir(config: SweepJobConfig, campaignId: UUID) throws -> URL {
        let slug = sanitizePathComponent(config.name.lowercased())
        let dirName = slug.isEmpty ? campaignId.uuidString : "\(campaignId.uuidString)_\(slug)"
        let dir = campaignOutputRoot.appendingPathComponent(dirName)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private func writeCampaignConfigSnapshots(
        baseConfig: LeniaBaseConfig,
        searchConfig: ParsedSearchConfig,
        config: SweepJobConfig,
        outputDir: URL
    ) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted]
        let baseData = try encoder.encode(baseConfig)
        let searchData = try encoder.encode(searchConfig)
        let sweepData = try encoder.encode(config)

        try baseData.write(to: outputDir.appendingPathComponent("config.base.json"))
        try searchData.write(to: outputDir.appendingPathComponent("config.search.json"))
        try sweepData.write(to: outputDir.appendingPathComponent("config.sweep.json"))
    }

    private func updateCampaignArtifacts(
        _ campaignId: UUID,
        _ body: (inout CampaignRuntimeArtifacts) -> Void
    ) {
        guard var artifacts = campaignArtifacts[campaignId] else { return }
        body(&artifacts)
        campaignArtifacts[campaignId] = artifacts
    }

    private func recordCampaignResults(
        campaignId: UUID,
        results: [SimulationResultData]
    ) {
        updateCampaignArtifacts(campaignId) { artifacts in
            persistResults(
                results: results,
                outputDir: artifacts.outputDir,
                resultCount: &artifacts.resultCount,
                topResults: &artifacts.topResults
            )
        }
    }

    private func finalizeCampaignOutputs(campaignId: UUID) {
        guard let artifacts = campaignArtifacts[campaignId] else { return }
        let outputDir = artifacts.outputDir
        let topResults = artifacts.topResults
        let top = Array(topResults.prefix(topK))
        let status = activeCampaigns[campaignId]
        let elapsed = Date().timeIntervalSince(artifacts.startTime)
        let resultsCount = artifacts.resultCount
        let failedJobs = artifacts.failedJobs
        let processedSeeds = status?.processedSeeds ?? 0
        finalizeResultArtifacts(
            outputDir: outputDir,
            topResults: top,
            summary: ResultArtifactSummary(
                totalSeeds: status?.totalSeeds ?? 0,
                totalJobs: status?.totalJobs ?? 0,
                completedJobs: status?.completedJobs ?? 0,
                failedJobs: failedJobs,
                resultsCount: resultsCount,
                topCount: top.count,
                elapsedSeconds: elapsed,
                seedsPerSecond: elapsed > 0 ? Double(processedSeeds) / elapsed : 0,
                workersUsed: status?.joinedWorkers.count ?? 0
            ),
            closeHandles: [
                outputDir.appendingPathComponent("results.jsonl"),
                outputDir.appendingPathComponent("activity.jsonl"),
                outputDir.appendingPathComponent("library.jsonl"),
                outputDir.appendingPathComponent("exports").appendingPathComponent("index.jsonl")
            ]
        )
    }

    private func finalizeResultArtifacts(
        outputDir: URL,
        topResults: [SimulationResultData],
        summary: ResultArtifactSummary,
        closeHandles: [URL]
    ) {
        do {
            try writeTopSimulationResultsSnapshot(
                topResults,
                to: outputDir.appendingPathComponent("top.json")
            )
        } catch {
            logger.error("Failed to write top results for \(outputDir.lastPathComponent): \(error)")
        }

        do {
            try writeResearchJSON(
                summary,
                to: outputDir.appendingPathComponent("summary.json"),
                prettyPrinted: true
            )
        } catch {
            logger.error("Failed to write summary for \(outputDir.lastPathComponent): \(error)")
        }

        ensureActivityArtifact(in: outputDir)
        for url in closeHandles {
            closeAppendJSONLHandle(for: url)
        }
    }

    private func ensureActivityArtifact(in outputDir: URL) {
        guard let activityConfig = searchConfig.activity, activityConfig.enabled else { return }
        let activityURL = outputDir.appendingPathComponent("activity.jsonl")
        if !FileManager.default.fileExists(atPath: activityURL.path) {
            FileManager.default.createFile(atPath: activityURL.path, contents: nil)
        }
    }

    private func appendJSONL<T: Encodable>(_ value: T, to url: URL) {
        guard let handle = appendJSONLHandle(for: url) else { return }
        do {
            handle.write(try researchJSONLine(value))
        } catch {
            logger.error("Failed to append JSONL to \(url.lastPathComponent): \(error)")
        }
    }

    private func appendJSONLHandle(for url: URL) -> FileHandle? {
        if let handle = appendJSONLHandles[url] {
            return handle
        }
        if !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: nil)
        }
        guard let handle = try? FileHandle(forWritingTo: url) else { return nil }
        do {
            try handle.seekToEnd()
        } catch {
            try? handle.close()
            return nil
        }
        appendJSONLHandles[url] = handle
        return handle
    }

    private func closeAppendJSONLHandle(for url: URL) {
        guard let handle = appendJSONLHandles.removeValue(forKey: url) else { return }
        try? handle.close()
    }

    private func closeAllAppendJSONLHandles() {
        for handle in appendJSONLHandles.values {
            try? handle.close()
        }
        appendJSONLHandles.removeAll(keepingCapacity: true)
    }

    private func recordOverallResults(results: [SimulationResultData]) {
        persistResults(
            results: results,
            outputDir: overallOutputDir,
            resultCount: &overallResultCount,
            topResults: &currentTopResults
        )
    }

    private func persistResults(
        results: [SimulationResultData],
        outputDir: URL,
        resultCount: inout Int,
        topResults: inout [SimulationResultData]
    ) {
        appendSimulationResults(results, to: outputDir.appendingPathComponent("results.jsonl"))
        resultCount += results.count
        mergeTopSimulationResults(results, into: &topResults, limit: topK, headroomMultiplier: 2)
        appendActivitySummaries(results, to: outputDir)
    }

    private func appendSimulationResults(_ results: [SimulationResultData], to url: URL) {
        guard !results.isEmpty else { return }
        guard let handle = appendJSONLHandle(for: url) else { return }
        do {
            try appendResearchJSONLines(results, to: handle)
        } catch {
            logger.error("Failed to append simulation results to \(url.lastPathComponent): \(error)")
        }
    }

    private func appendActivitySummaries(_ results: [SimulationResultData], to outputDir: URL) {
        guard let activityConfig = searchConfig.activity, activityConfig.enabled else { return }
        ensureActivityArtifact(in: outputDir)
        let activityURL = outputDir.appendingPathComponent("activity.jsonl")
        let records = activitySummaryRecords(from: results, config: activityConfig)
        guard !records.isEmpty, let handle = appendJSONLHandle(for: activityURL) else { return }
        do {
            try appendResearchJSONLines(records, to: handle)
        } catch {
            logger.error("Failed to append activity summaries to \(activityURL.lastPathComponent): \(error)")
        }
    }

    private func sanitizePathComponent(_ value: String) -> String {
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_."))
        let scalars = value.unicodeScalars.map { allowed.contains($0) ? Character($0) : "-" }
        let sanitized = String(scalars).trimmingCharacters(in: CharacterSet(charactersIn: "-"))
        return sanitized.isEmpty ? "campaign" : sanitized
    }

    public distributed func joinCampaign(workerId: String, campaignId: UUID) async -> Bool {
        guard var workerSet = campaignWorkers[campaignId],
              workerIdMap[workerId] != nil else {
            logger.warning("Cannot join campaign: campaign \(campaignId) or worker \(workerId) not found")
            return false
        }

        workerSet.insert(workerId)
        campaignWorkers[campaignId] = workerSet
        workerCampaignAssignments[workerId] = campaignId

        logger.info("Worker \(workerId) joined campaign \(campaignId) (\(workerSet.count) workers)")

        if let status = activeCampaigns[campaignId] {
            activeCampaigns[campaignId] = CampaignStatus(
                id: status.id,
                name: status.name,
                totalJobs: status.totalJobs,
                completedJobs: status.completedJobs,
                totalSeeds: status.totalSeeds,
                processedSeeds: status.processedSeeds,
                isRunning: true,
                joinedWorkers: Array(workerSet),
                outputDir: status.outputDir
            )
        }

        broadcastCampaigns()

        return true
    }

    private func updateCampaignProgress(campaignId: UUID, jobId: String, seedCount: Int, success: Bool) {
        guard let status = activeCampaigns[campaignId] else { return }

        campaignJobMapping.removeValue(forKey: jobId)
        let newCompleted = status.completedJobs + 1
        let newSeeds = status.processedSeeds + (success ? seedCount : 0)
        let stillRunning = newCompleted < status.totalJobs

        activeCampaigns[campaignId] = CampaignStatus(
            id: status.id,
            name: status.name,
            totalJobs: status.totalJobs,
            completedJobs: newCompleted,
            totalSeeds: status.totalSeeds,
            processedSeeds: newSeeds,
            isRunning: stillRunning,
            joinedWorkers: status.joinedWorkers,
            outputDir: status.outputDir
        )

        if success {
            logger.info("Campaign \(status.name) progress: \(newCompleted)/\(status.totalJobs) jobs, \(newSeeds)/\(status.totalSeeds) seeds")
        } else {
            logger.warning("Campaign \(status.name) job \(jobId) failed; progress: \(newCompleted)/\(status.totalJobs) jobs")
        }
        if !stillRunning {
            for workerId in status.joinedWorkers {
                if workerCampaignAssignments[workerId] == status.id {
                    workerCampaignAssignments.removeValue(forKey: workerId)
                }
            }
            finalizeCampaignOutputs(campaignId: status.id)
        }

        broadcastCampaigns()

        Task {
            await broadcastWorkerList()
        }
    }

    private func broadcastCampaigns() {
        let statusList = Array(activeCampaigns.values)
        eventContinuation?.yield(.campaignsUpdated(statusList))

        // Broadcast to all workers
        for worker in workers {
            Task {
                do {
                    try await worker.receiveCampaignUpdate(statusList)
                } catch {
                    self.logger.error("Failed to send campaign update to worker: \(error)")
                }
            }
        }

        Task {
            await self.broadcastClusterSummary()
        }
    }

    public distributed func getCampaigns() async -> [CampaignStatus] {
        return Array(activeCampaigns.values)
    }

    // MARK: - Worker Registry

    public func getWorkerList() async -> [WorkerStatus] {
        var statuses: [WorkerStatus] = []
        for worker in workers {
            if let status = try? await worker.getStatus() {
                statuses.append(status)
            }
        }
        return statuses
    }

    public func broadcastWorkerList() async {
        let statuses = await getWorkerList()
        lastKnownWorkerStatuses = statuses
        eventContinuation?.yield(.workerListUpdated(statuses))
        await broadcastClusterSummary(workerStatuses: statuses)
    }

    // Distributed wrapper for worker list refresh (called from Host UI)
    public distributed func requestWorkerListUpdate() async {
        await broadcastWorkerList()
    }

    private func broadcastClusterSummary(workerStatuses: [WorkerStatus]? = nil) async {
        guard !isShuttingDown else { return }

        let statuses = workerStatuses ?? lastKnownWorkerStatuses
        let top = Array(currentTopResults.prefix(topK))
        let elapsed = Date().timeIntervalSince(startTime)
        let processedSeeds = processedSeedCount
        let rate = elapsed > 0 ? Double(processedSeeds) / elapsed : 0
        let summary = ClusterSummary(
            workers: statuses,
            campaigns: Array(activeCampaigns.values),
            totalSeedsProcessed: processedSeeds,
            clusterRate: rate,
            completedJobs: completedJobCount,
            totalJobs: totalJobsCreated,
            topCreatureCount: top.count,
            bestScore: top.compactMap(\.score).max()
        )

        for worker in workers {
            if isShuttingDown { return }
            do {
                try await worker.receiveClusterSummary(summary)
            } catch {
                if isShuttingDown { return }
                logger.error("Failed to send cluster summary to worker: \(error)")
            }
        }
    }
}

public enum ControllerError: Error, Codable {
    case invalidSearchConfig
    case invalidBaseConfig
    case outputDirFailed(String)
    case exportFailed(String)
}
