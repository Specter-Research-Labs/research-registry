import Distributed
import DistributedCluster
import Foundation
import Logging
import Metal

// MARK: - Worker Events

public enum WorkerEvent: Sendable {
    case localResult(SimulationResultData)
    case globalUpdate(GlobalUpdate)
    case clusterSummary(ClusterSummary)
    case libraryUpdate(LibraryUpdate)
    case arenaInvite(ArenaConfig)
    case arenaState(ArenaState)
    case arenaFrame(ArenaFrame)
    case campaignUpdate([CampaignStatus])
}

// MARK: - Callback Registry

public final class WorkerCallbackRegistry: @unchecked Sendable {
    public static let shared = WorkerCallbackRegistry()
    private var callbacks: [ObjectIdentifier: @Sendable (WorkerEvent) -> Void] = [:]
    private let lock = NSLock()

    private init() {}

    public func register(for worker: LeniaWorker, handler: @escaping @Sendable (WorkerEvent) -> Void) {
        lock.lock()
        defer { lock.unlock() }
        callbacks[ObjectIdentifier(worker)] = handler
    }

    public func unregister(for worker: LeniaWorker) {
        lock.lock()
        defer { lock.unlock() }
        callbacks.removeValue(forKey: ObjectIdentifier(worker))
    }

    func notify(from worker: LeniaWorker, event: WorkerEvent) {
        lock.lock()
        let handler = callbacks[ObjectIdentifier(worker)]
        lock.unlock()
        handler?(event)
    }
}

// MARK: - Worker Actor

public distributed actor LeniaWorker {
    public typealias ActorSystem = ClusterSystem

    private let _workerId: String
    private let hostname: String
    private var logger: Logger
    private var controller: SwarmController?

    public var workerId: String { _workerId }
    private var jobsCompleted: Int = 0
    private var totalSeedsProcessed: Int = 0
    private var currentJobId: String?
    private var qd2024MAPElitesCache: [String: LeniaBreeder2024WorkerAssetCacheEntry] = [:]
    private let backendCapabilities: WorkerBackendCapabilities

    public init(actorSystem: ClusterSystem, workerId: String? = nil) {
        self.actorSystem = actorSystem
        self._workerId = workerId ?? Self.generateWorkerId()
        self.hostname = ProcessInfo.processInfo.hostName
        self.backendCapabilities = Self.detectBackendCapabilities()
        self.logger = LeniaLogging.makeLogger(
            label: "LeniaSwarm.Worker.\(self._workerId)",
            extraMetadata: ["worker_id": .string(self._workerId)]
        )
    }

    // Call this after init to start controller discovery
    public distributed func startControllerDiscovery() {
        let workerLogger = self.logger
        Task {
            for await ctrl in await self.actorSystem.receptionist.listing(of: .leniaController) {
                self.controller = ctrl
                workerLogger.info("Worker linked to Controller")
                break
            }
        }
    }

    public distributed func updateRunContext(_ context: RunContext) async {
        logger.info("Updating run context to \(context.runId)")
        let metadata: Logger.Metadata = [
            "run_id": .string(context.runId),
            "controller_id": .string(context.controllerId)
        ]
        LeniaLogging.updateMetadata(metadata)
        logger[metadataKey: "run_id"] = .string(context.runId)
        logger[metadataKey: "controller_id"] = .string(context.controllerId)
    }

    public static func generateWorkerId() -> String {
        let adjectives = [
            "swift", "bright", "cosmic", "stellar", "azure", "crimson", "golden", "silver",
            "crystal", "ember", "frost", "jade", "lunar", "nova", "prism", "quantum",
            "radiant", "solar", "thunder", "velvet", "wild", "zen", "atomic", "cyber"
        ]
        let creatures = [
            "specter", "wraith", "phantom", "banshee", "poltergeist", "revenant", "shade", "ghoul",
            "vampire", "werewolf", "zombie", "skeleton", "lich", "demon", "imp", "gremlin",
            "goblin", "troll", "ogre", "hydra", "chimera", "basilisk", "kraken", "leviathan"
        ]
        let adj = adjectives.randomElement() ?? "unknown"
        let creature = creatures.randomElement() ?? "worker"
        return "\(adj)-\(creature)"
    }

    // Receive global updates from Controller
    public distributed func receiveGlobalUpdate(_ update: GlobalUpdate) async {
        logger.info("Received GlobalUpdate: \(update.topCreatures.count) creatures, \(update.totalSeedsProcessed) seeds processed")
        WorkerCallbackRegistry.shared.notify(from: self, event: .globalUpdate(update))
    }

    public distributed func receiveClusterSummary(_ summary: ClusterSummary) async {
        logger.debug(
            "Received ClusterSummary: \(summary.workers.count) workers, \(summary.campaigns.count) campaigns, \(summary.totalSeedsProcessed) seeds"
        )
        WorkerCallbackRegistry.shared.notify(from: self, event: .clusterSummary(summary))
    }

    // Receive library updates from Controller
    public distributed func receiveLibraryUpdate(_ update: LibraryUpdate) async {
        switch update {
        case .fullSync(let creatures):
            logger.info("Received library sync: \(creatures.count) creatures")
        case .creatureAdded(let creature):
            logger.info("New creature added to library: \(creature.name)")
        }
        WorkerCallbackRegistry.shared.notify(from: self, event: .libraryUpdate(update))
    }

    // Receive arena invite from Controller
    public distributed func receiveArenaInvite(_ config: ArenaConfig) async {
        logger.info("Received arena invite: \(config.id)")
        WorkerCallbackRegistry.shared.notify(from: self, event: .arenaInvite(config))
    }

    // Receive arena state update
    public distributed func receiveArenaState(_ state: ArenaState) async {
        logger.info("Arena state update: \(state.status)")
        WorkerCallbackRegistry.shared.notify(from: self, event: .arenaState(state))
    }

    // Receive arena video frame
    public distributed func receiveArenaFrame(_ frame: ArenaFrame) async {
        WorkerCallbackRegistry.shared.notify(from: self, event: .arenaFrame(frame))
    }

    // Receive campaign status updates
    public distributed func receiveCampaignUpdate(_ campaigns: [CampaignStatus]) async {
        logger.info("Received campaign update: \(campaigns.count) campaigns")
        WorkerCallbackRegistry.shared.notify(from: self, event: .campaignUpdate(campaigns))
    }

    public distributed func process(job: SimulationJob) async throws -> SimulationResult {
        let startTime = Date()
        currentJobId = job.id

        logger.info("Received job \(job.id): seeds \(job.seedStart)..<\(job.seedStart + job.count)")
        LeniaMetrics.counter(
            "jobs_started_total",
            1.0,
            fields: [
                "job_id": job.id,
                "seed_start": String(job.seedStart),
                "seed_count": String(job.count)
            ]
        )

        do {
            guard let materializedJob = materializeSimulationJob(job, for: backendCapabilities) else {
                throw WorkerError.invalidConfig(
                    "Worker \(workerId) does not support requested backend '\(backendRequestValue(for: job))'."
                )
            }
            // Use searchConfig directly from job (no parsing needed)
            let searchConfig = materializedJob.searchConfig
            let batchSize = searchConfig.batchSize
            let initSeedOffset = searchConfig.initSeedOffset ?? 0

            guard materializedJob.count > 0 else {
                throw WorkerError.invalidConfig("Job count must be > 0")
            }
            guard batchSize > 0 else {
                throw WorkerError.invalidConfig("batch_size must be > 0")
            }

            var seeds: [Int] = []
            for i in 0..<materializedJob.count {
                let seed = materializedJob.seedStart + i * searchConfig.seedStride
                seeds.append(seed)
            }

            // Build overrides dict
            var overrides: [String: Any] = searchConfig.overridesAsDict()
            if let sweepOverrides = materializedJob.sweepOverrides {
                for (key, value) in sweepOverrides {
                    overrides[key] = value
                }
            }

            let firstSeed = seeds[0]
            overrides["params.seed"] = firstSeed
            overrides["run.steps"] = searchConfig.steps

            // Re-encode baseConfig to Data to apply overrides via loadRuntimeConfig
            let baseConfigData = try JSONEncoder().encode(materializedJob.baseConfig)
            let runtimeConfig = try loadRuntimeConfig(from: baseConfigData, overrides: overrides)
            let engine = SearchEngine(runtimeConfig: runtimeConfig)

            let simSearchConfig = SearchConfig(
                steps: searchConfig.steps,
                recordInterval: searchConfig.recordInterval,
                warmupSteps: searchConfig.warmupSteps,
                occupancyThreshold: searchConfig.occupancyThreshold,
                componentThreshold: searchConfig.componentThreshold,
                massChannel: searchConfig.massChannel,
                scoreWeights: searchConfig.scoreWeights,
                filters: searchConfig.filters,
                complexity: searchConfig.complexity,
                activity: searchConfig.activity,
                stability: searchConfig.stability,
                moments: searchConfig.moments
            )

            var allResults: [SimulationResultData] = []
            var currentIdx = 0

            while currentIdx < seeds.count {
                let chunkEnd = min(currentIdx + batchSize, seeds.count)
                let chunkSeeds = Array(seeds[currentIdx..<chunkEnd])

                let batchResults = engine.runBatch(
                    seeds: chunkSeeds,
                    initSeedOffset: initSeedOffset,
                    searchConfig: simSearchConfig
                )

                for result in batchResults {
                    let resultData = materializeSearchResultData(
                        result,
                        backend: runtimeConfig.backend.rawValue,
                        implementation: runtimeConfig.implementation,
                        searchConfig: simSearchConfig,
                        sweep: materializedJob.sweepOverrides?.mapValues { $0 } ?? [:]
                    )

                    // Notify UI if running locally and result passed filters
                    if resultData.filtersPassed {
                        WorkerCallbackRegistry.shared.notify(from: self, event: .localResult(resultData))
                    }

                    allResults.append(resultData)
                }

                currentIdx = chunkEnd
            }

            let duration = Date().timeIntervalSince(startTime)
            jobsCompleted += 1
            totalSeedsProcessed += materializedJob.count
            currentJobId = nil

            logger.info("Job \(job.id) completed in \(String(format: "%.1f", duration))s")
            LeniaMetrics.timing(
                "job_duration_seconds",
                duration,
                fields: [
                    "job_id": job.id,
                    "success": "true"
                ]
            )
            LeniaMetrics.counter(
                "jobs_completed_total",
                1.0,
                fields: ["job_id": job.id]
            )
            LeniaMetrics.counter(
                "seeds_processed_total",
                Double(job.count),
                fields: ["job_id": job.id]
            )

            return SimulationResult(
                jobId: job.id,
                workerId: workerId,
                success: true,
                seedStart: materializedJob.seedStart,
                count: materializedJob.count,
                results: allResults,
                errorMessage: nil,
                durationSeconds: duration
            )

        } catch {
            currentJobId = nil
            let duration = Date().timeIntervalSince(startTime)

            logger.error("Job \(job.id) ERROR: \(error)")
            LeniaMetrics.timing(
                "job_duration_seconds",
                duration,
                fields: [
                    "job_id": job.id,
                    "success": "false"
                ]
            )
            LeniaMetrics.counter(
                "jobs_failed_total",
                1.0,
                fields: ["job_id": job.id]
            )
            return SimulationResult(
                jobId: job.id,
                workerId: workerId,
                success: false,
                seedStart: job.seedStart,
                count: job.count,
                results: [],
                errorMessage: error.localizedDescription,
                durationSeconds: duration
            )
        }
    }

    public distributed func evaluateMAPElites(job: LeniaBreeder2024DistributedMAPElitesJob) async throws -> LeniaBreeder2024DistributedMAPElitesResult {
        logger.info(
            "Received qd-2024 MAP-Elites job \(job.id): generation=\(job.generation) offset=\(job.candidateOffset) count=\(job.genotypes.count)"
        )
        LeniaMetrics.counter(
            "qd2024_jobs_started_total",
            1.0,
            fields: [
                "job_id": job.id,
                "generation": String(job.generation),
                "candidate_count": String(job.genotypes.count)
            ]
        )

        do {
            let result = try leniaBreeder2024EvaluateMAPElitesJob(
                job: job,
                workerId: workerId,
                cache: &qd2024MAPElitesCache
            )
            jobsCompleted += 1
            LeniaMetrics.timing(
                "qd2024_job_duration_seconds",
                result.durationSeconds,
                fields: [
                    "job_id": job.id,
                    "generation": String(job.generation),
                    "worker_id": workerId
                ]
            )
            logger.info(
                "Completed qd-2024 MAP-Elites job \(job.id): duration=\(result.durationSeconds)s finite=\(result.evaluations.filter { $0.fitness.isFinite }.count)"
            )
            return result
        } catch {
            logger.error("Failed qd-2024 MAP-Elites job \(job.id): \(String(describing: error))")
            throw error
        }
    }

    public distributed func processCampaignJob(_ job: LeniaCampaignJob) async throws -> LeniaCampaignJobExecution {
        currentJobId = job.runID
        defer { currentJobId = nil }
        guard let materializedJob = materializeCampaignJob(job, for: backendCapabilities) else {
            throw WorkerError.invalidConfig(
                "Worker \(workerId) does not support requested campaign backend '\(job.backendRequest)' for \(job.runID)."
            )
        }
        return try executeLeniaCampaignJob(
            materializedJob,
            logger: logger,
            workerID: workerId
        )
    }

    public distributed func getStatus() async -> WorkerStatus {
        return WorkerStatus(
            capabilities: backendCapabilities,
            workerId: workerId,
            hostname: hostname,
            currentJob: currentJobId,
            jobsCompleted: jobsCompleted,
            totalSeedsProcessed: totalSeedsProcessed,
            isAvailable: currentJobId == nil
        )
    }

    private static func detectBackendCapabilities() -> WorkerBackendCapabilities {
        let hasMetal = MTLCreateSystemDefaultDevice() != nil
        if hasMetal {
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

    public distributed func evolveForArena(creature: SavedCreature, generations: Int = 10) async throws -> SavedCreature {
        logger.info("Evolving creature \(creature.name) for arena mobility...")

        // 1. Setup minimal configs for Evolution
        let baseConfig = LeniaBaseConfig(
            backend: "mlx",
            profile: .experimental,
            grid: GridConfig(sx: 128, sy: 128),
            channels: 1,
            connectivity: [[1]],
            flow: FlowConfig(dt: 0.2, n: 2, theta_A: 2.0),
            implementation: ImplementationConfig(mode: "flowlenia_2022_paper_equations"),
            reintegration: ReintegrationConfig(dd: 5, sigma: 0.65, border: "torus"),
            parameter_embedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
            chemotaxis: nil,
            food: nil,
            walls: nil,
            params: ParamsConfig(
                mode: "explicit",
                seed: nil,
                ranges: nil,
                r: creature.genotype.r,
                b: creature.genotype.b,
                w: creature.genotype.w,
                a: creature.genotype.a,
                m: creature.genotype.m,
                s: creature.genotype.s,
                h: creature.genotype.h,
                R: creature.genotype.R
            ),
            init: creature.initialCondition,
            run: RunConfig(steps: 200),
            interventions: nil
        )

        // 2. Setup ES Config targeting Velocity (directed_motion)
        let fitnessConfig = FitnessConfig(objective: "directed_motion", targetStep: 200, angleThreshold: 0.0)
        let esConfig = ESConfig(
            outputDir: try resolveRuntimeAwarePath("/tmp", dossier: "lenia-swarm"),
            generations: generations,
            population: 16,
            sigma: 0.02,
            learningRate: 0.1,
            seed: Int.random(in: 0...10000),
            steps: 200,
            fitness: fitnessConfig,
            fitnessShaping: "centered_rank",
            initPatch: nil,
            initialInitPatchValues: nil,
            paramRanges: nil,
            obstacleField: nil
        )

        // 3. Define standard ranges (required for param space encoding)
        let ranges: [String: (Float, Float)] = [
            "r": (0.2, 1.0), "b": (0.0, 1.0), "w": (0.01, 0.5), "a": (0.0, 1.0),
            "m": (0.05, 0.5), "s": (0.001, 0.2), "h": (0.0, 1.0), "R": (2.0, 25.0)
        ]

        // 4. Create Engine and Run
        let runtimeConfig = try loadRuntimeConfig(from: try JSONEncoder().encode(baseConfig))
        let engine = EvolutionEngine(runtimeConfig: runtimeConfig, esConfig: esConfig, ranges: ranges)

        var bestGenFitness: Float = -1000.0

        for g in 0..<generations {
            let result = engine.runGeneration(gen: g)
            bestGenFitness = result.bestFitness
        }

        // 5. Return evolved creature
        let bestParams = engine.getBestParams()

        logger.info("Evolution complete. Fitness (Velocity): \(bestGenFitness)")

        return derivedCreature(
            from: creature,
            name: "\(creature.name)-v2",
            genotype: bestParams.toKernelParams(),
            score: nil,
            scoreWeights: creature.scoreWeights
        )
    }
}

public enum WorkerError: Error {
    case invalidConfig(String)
}

public extension DistributedReception.Key {
    static var leniaWorkers: DistributedReception.Key<LeniaWorker> {
        "lenia-workers"
    }
}
