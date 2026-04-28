import Foundation
import DistributedCluster
import LeniaCore
import Logging

// MARK: - Node Configuration

public struct NodeConfig {
    public let bindHost: String
    public let bindPort: Int
    public let mode: NodeMode
    public let baseConfigPath: String?
    public let searchConfigPath: String?
    public let outputRootPath: String?

    public init(
        bindHost: String = "0.0.0.0",
        bindPort: Int,
        mode: NodeMode,
        baseConfigPath: String? = nil,
        searchConfigPath: String? = nil,
        outputRootPath: String? = nil
    ) {
        self.bindHost = bindHost
        self.bindPort = bindPort
        self.mode = mode
        self.baseConfigPath = baseConfigPath
        self.searchConfigPath = searchConfigPath
        self.outputRootPath = outputRootPath
    }
}

public enum NodeMode {
    case host
    case join(controllerHost: String, controllerPort: Int)
}

// MARK: - Lenia Node

@MainActor
public class LeniaNode: ObservableObject {
    private var system: ClusterSystem?
    private var controller: SwarmController?
    private var worker: LeniaWorker?
    private weak var appState: AppState?
    private let logger: Logger

    public init(appState: AppState) {
        self.appState = appState
        self.logger = LeniaLogging.makeLogger(label: "LeniaStudio")
    }

    public func start(config: NodeConfig) async {
        appState?.connectionState = .connecting

        let logger = self.logger

        // Extract values to avoid capturing main-actor isolated config in closure
        let bindHost = config.bindHost
        let bindPort = config.bindPort
        let baseConfigPath = config.baseConfigPath
        let searchConfigPath = config.searchConfigPath
        let outputRootPath = config.outputRootPath

        // Start Cluster System
        let system = await ClusterSystem("LeniaHive") { settings in
            settings.bindHost = bindHost
            settings.bindPort = bindPort
            settings.swim.probeInterval = .seconds(1)
            settings.swim.pingTimeout = .milliseconds(500)
            settings.remoteCall.defaultTimeout = .seconds(600)
            settings.autoLeaderElection = .lowestReachable(minNumberOfMembers: 1)
        }
        self.system = system

        // Mode-specific logic
        switch config.mode {
        case .host:
            // Host mode: controller only, no local worker
            let started = await startController(
                system: system,
                logger: LeniaLogging.makeLogger(label: "LeniaStudio.Controller"),
                baseConfigPath: baseConfigPath,
                searchConfigPath: searchConfigPath,
                outputRootPath: outputRootPath
            )
            if started {
                appState?.connectionState = .connected(role: .host)
                appState?.workersConnected = 0
            }

        case .join(let controllerHost, let controllerPort):
            // Worker mode: create worker and join cluster
            let localWorkerId = LeniaWorker.generateWorkerId()
            let worker = LeniaWorker(actorSystem: system, workerId: localWorkerId)
            self.worker = worker

            appState?.localWorkerId = localWorkerId
            logger.info("Local worker ID: \(localWorkerId)")

            WorkerCallbackRegistry.shared.register(for: worker) { [weak self] event in
                Task { @MainActor in
                    self?.handleWorkerEvent(event)
                }
            }

            await system.receptionist.checkIn(worker, with: .leniaWorkers)

            let endpoint = Cluster.Endpoint(host: controllerHost, port: controllerPort)
            system.cluster.join(endpoint: endpoint)

            // Discover remote controller via receptionist
            Task {
                logger.info("Looking for Controller...")
                for await ctrl in await system.receptionist.listing(of: .leniaController) {
                    self.controller = ctrl
                    logger.info("Controller discovered!")
                    break
                }
            }

            // Start worker's controller discovery for creature submission
            do {
                try await worker.startControllerDiscovery()
            } catch {
                logger.error("Failed to start controller discovery: \(error)")
            }

            appState?.connectionState = .connected(role: .worker)
            appState?.workersConnected = 1
            logger.info("Joined cluster at \(controllerHost):\(controllerPort)")
        }
    }

    public func stop() {
        if let worker = worker {
            WorkerCallbackRegistry.shared.unregister(for: worker)
        }
        if let system = system {
            do {
                try system.shutdown()
            } catch {
                logger.error("Failed to shutdown cluster system: \(error)")
            }
        }
        system = nil
        controller = nil
        worker = nil
        appState?.connectionState = .disconnected
        appState?.clearCreatures()
    }

    private func handleWorkerEvent(_ event: WorkerEvent) {
        switch event {
        case .localResult(let result):
            let creature = result.toCreature(source: "Local")
            appState?.addCreature(creature)
            logger.info("Local result: seed \(result.seed), score \(result.score ?? 0)")

            let metrics = result.metrics
            let isStableCreature = metrics.isStable

            if isStableCreature, let workerId = appState?.localWorkerId {
                let initialCondition = InitConfig(
                    seed: result.initSeed,
                    patches: [],
                    a_uniform: UniformRange(low: 0, high: 1),
                    p_uniform: nil
                )
                let savedCreature = savedCreatureFromResult(
                    name: generateCreatureName(),
                    ownerId: workerId,
                    result: result,
                    initialCondition: initialCondition,
                    score: result.score,
                    scoreWeights: result.scoreWeights
                )
                appState?.addToLocalLibrary(savedCreature)
                logger.info("Local creature discovered: \(savedCreature.name)")
            }

        case .globalUpdate(let update):
            logger.info("Received global update in LeniaNode: \(update.topCreatures.count) creatures")
            let globalCreatures = update.topCreatures.map { $0.toCreature(source: "Cluster") }
            appState?.updateGlobalList(globalCreatures)
            logger.info("Updated globalBestCreatures: \(appState?.globalBestCreatures.count ?? 0) creatures")

            // Update progress for worker-only nodes
            if case .connected(let role) = appState?.connectionState, role == .worker {
                appState?.seedsProcessed = update.totalSeedsProcessed
            }

        case .clusterSummary(let summary):
            appState?.applyClusterSummary(summary)

        case .libraryUpdate(let update):
            appState?.updateLibrary(update)

        case .arenaInvite(let config):
            logger.info("Received arena invite: \(config.id)")
            appState?.updateArenaInvite(config)

        case .arenaState(let state):
            logger.info("Received arena state: \(state.status)")
            if state.status == .ended {
                appState?.clearArena()
            } else {
                appState?.updateArenaState(state)
            }

        case .arenaFrame(let frame):
            appState?.updateArenaFrame(frame)

        case .campaignUpdate(let campaigns):
            logger.info("Received campaign update: \(campaigns.count) campaigns")
            appState?.updateCampaigns(campaigns)
        }
    }

    private func startController(
        system: ClusterSystem,
        logger: Logger,
        baseConfigPath: String?,
        searchConfigPath: String?,
        outputRootPath: String?
    ) async -> Bool {
        let trimmedBase = baseConfigPath?.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedSearch = searchConfigPath?.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedOutputRoot = outputRootPath?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let hasBase = trimmedBase != nil && !(trimmedBase?.isEmpty ?? true)
        let hasSearch = trimmedSearch != nil && !(trimmedSearch?.isEmpty ?? true)

        if hasBase != hasSearch {
            appState?.connectionState = .error("Provide both base and search config paths or leave both empty.")
            do {
                try system.shutdown()
            } catch {
                logger.error("Failed to shutdown cluster system: \(error)")
            }
            self.system = nil
            return false
        }

        if hasBase {
            guard let basePath = trimmedBase,
                  let searchPath = trimmedSearch,
                  FileManager.default.fileExists(atPath: basePath),
                  FileManager.default.fileExists(atPath: searchPath) else {
                appState?.connectionState = .error("Config paths are invalid or missing.")
                do {
                    try system.shutdown()
                } catch {
                    logger.error("Failed to shutdown cluster system: \(error)")
                }
                self.system = nil
                return false
            }
        }

        guard !trimmedOutputRoot.isEmpty else {
            appState?.connectionState = .error("Output root path is required for host mode.")
            do {
                try system.shutdown()
            } catch {
                logger.error("Failed to shutdown cluster system: \(error)")
            }
            self.system = nil
            return false
        }

        let outputRootURL: URL
        do {
            outputRootURL = try ensureOutputRoot(path: trimmedOutputRoot)
        } catch {
            appState?.connectionState = .error("Failed to create output root: \(error.localizedDescription)")
            do {
                try system.shutdown()
            } catch {
                logger.error("Failed to shutdown cluster system: \(error)")
            }
            self.system = nil
            return false
        }

        let runContext = RunContext(
            runId: LeniaLogging.currentRunId(),
            controllerId: LeniaLogging.currentNodeId()
        )
        let outputDir: String
        do {
            outputDir = try makeRunOutputDir(root: outputRootURL, runContext: runContext)
        } catch {
            appState?.connectionState = .error("Failed to create run output directory: \(error.localizedDescription)")
            do {
                try system.shutdown()
            } catch {
                logger.error("Failed to shutdown cluster system: \(error)")
            }
            self.system = nil
            return false
        }
        appState?.outputRootPath = outputRootURL.path
        appState?.outputRunPath = outputDir

        // Create event stream locally - host owns the read-end
        let (eventStream, eventContinuation) = AsyncStream<ControllerEvent>.makeStream()

        do {
            let controller: SwarmController
            if hasBase, let basePath = trimmedBase, let searchPath = trimmedSearch {
                controller = try SwarmController(
                    system: system,
                    baseConfigPath: basePath,
                    searchConfigPath: searchPath,
                    outputDir: outputDir,
                    seedsPerJob: 5,
                    runContext: runContext,
                    logger: logger,
                    eventContinuation: eventContinuation
                )
            } else {
                let baseConfig = createDefaultBaseConfig()
                let searchConfig = createDefaultSearchConfig()
                controller = try SwarmController(
                    system: system,
                    baseConfig: baseConfig,
                    searchConfig: searchConfig,
                    outputDir: outputDir,
                    seedsPerJob: 5,
                    runContext: runContext,
                    logger: logger,
                    eventContinuation: eventContinuation
                )
            }

            self.controller = controller

            // Listen for controller events on the local stream
            Task {
                for await event in eventStream {
                    handleControllerEvent(event)
                }
            }

            try await controller.start()
            return true
        } catch {
            appState?.connectionState = .error("Failed to start: \(error.localizedDescription)")
            do {
                try system.shutdown()
            } catch {
                logger.error("Failed to shutdown cluster system: \(error)")
            }
            self.system = nil
            return false
        }
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

    private func handleControllerEvent(_ event: ControllerEvent) {
        switch event {
        case .progress(let completed, let total, let seeds, let totalSeeds, let rate):
            appState?.updateProgress(jobs: completed, totalJobs: total, seeds: seeds, totalSeeds: totalSeeds, rate: rate)
        case .finished:
            appState?.markSearchComplete()
        case .workerListUpdated(let workers):
            appState?.updateWorkerList(workers)
        case .creatureDiscovered(let creature):
            appState?.updateLibrary(.creatureAdded(creature))
        case .campaignsUpdated(let campaigns):
            appState?.updateCampaigns(campaigns)
        }
    }

    // MARK: - Arena Control (Host only)

    public func createArena(size: Int, maxPlayers: Int = 4) async {
        guard let controller = controller else {
            logger.warning("Cannot create arena: not a host")
            return
        }
        do {
            let arenaId = try await controller.createArena(size: size, maxPlayers: maxPlayers)
            let config = ArenaConfig(id: arenaId, size: size, maxPlayers: maxPlayers)
            appState?.addArena(config)
            logger.info("Created arena: \(arenaId)")
        } catch {
            logger.error("Failed to create arena: \(error)")
        }
    }

    public func startArena(id: UUID? = nil) async {
        guard let controller = controller else {
            logger.warning("Cannot start arena: not a host")
            return
        }
        let arenaId = id ?? appState?.activeArenaConfig?.id
        guard let arenaId = arenaId else {
            logger.warning("Cannot start arena: no arena specified")
            return
        }
        do {
            try await controller.startArena(id: arenaId)
        } catch {
            logger.error("Failed to start arena \(arenaId): \(error)")
        }
    }

    public func stopArena(id: UUID? = nil) async {
        guard let controller = controller else { return }
        let arenaId = id ?? appState?.activeArenaConfig?.id
        guard let arenaId = arenaId else { return }
        do {
            try await controller.stopArena(id: arenaId)
        } catch {
            logger.error("Failed to stop arena \(arenaId): \(error)")
        }
        appState?.removeArena(arenaId)
    }

    // MARK: - Sweep Control

    public func startSweep(name: String, totalSeeds: Int, steps: Int, gridSize: Int) async {
        guard let controller = controller else {
            logger.warning("Cannot start sweep: not a host")
            return
        }

        let config = SweepJobConfig(
            name: name,
            totalSeeds: totalSeeds,
            steps: steps,
            seedsPerChunk: 5,
            gridHeight: gridSize,
            gridWidth: gridSize
        )

        do {
            let campaignId = try await controller.startSweep(config: config)
            logger.info("Created sweep: \(name) with ID \(campaignId)")
        } catch {
            logger.error("Failed to create sweep: \(error)")
        }
    }

    public func joinCampaign(campaignId: UUID) async {
        guard let controller = controller,
              let workerId = appState?.localWorkerId else {
            logger.warning("Cannot join campaign: missing controller or worker ID")
            return
        }

        do {
            let success = try await controller.joinCampaign(workerId: workerId, campaignId: campaignId)
            if success {
                logger.info("Successfully joined campaign \(campaignId)")
            } else {
                logger.warning("Failed to join campaign \(campaignId)")
            }
        } catch {
            logger.error("Error joining campaign: \(error)")
        }
    }

    public func exportCreature(_ creature: SavedCreature) async -> String? {
        guard let controller = controller else {
            logger.error("Cannot export creature: controller unavailable")
            return nil
        }
        do {
            return try await controller.exportCreature(creature, reason: "manual")
        } catch {
            logger.error("Failed to export creature: \(error)")
            return nil
        }
    }

    public func triggerArenaMutation(id: UUID? = nil, strength: Float = 0.05) async {
        guard let controller = controller else {
            logger.warning("Cannot trigger mutation: not a host")
            return
        }
        let arenaId = id ?? appState?.activeArenaConfig?.id ?? appState?.availableArenas.first?.id
        guard let arenaId = arenaId else {
            logger.warning("Cannot trigger mutation: no arena specified")
            return
        }
        logger.info("Triggering radiation storm in arena \(arenaId)")
        do {
            try await controller.triggerMutationInArena(id: arenaId, strength: strength)
        } catch {
            logger.error("Failed to trigger mutation in arena \(arenaId): \(error)")
        }
    }

    public func joinArena(with creature: SavedCreature, qualify: Bool = false) async {
        guard let controller = controller,
              let arenaId = appState?.activeArenaConfig?.id,
              let workerId = appState?.localWorkerId,
              let worker = worker else {
            logger.warning("Cannot join arena: missing controller, arena, worker ID, or worker")
            return
        }

        var candidate = creature

        if qualify {
            logger.info("Entering Training Camp...")
            do {
                candidate = try await worker.evolveForArena(creature: creature, generations: 5)
                logger.info("Qualification complete. Submitting \(candidate.name)")
            } catch {
                logger.error("Qualification failed: \(error)")
                return
            }
        }

        // Distributed call - can throw
        do {
            let success = try await controller.requestJoinArena(workerId: workerId, arenaId: arenaId, creature: candidate)
            if success {
                logger.info("Successfully joined arena")
            } else {
                logger.warning("Failed to join arena")
            }
        } catch {
            logger.error("Join arena request failed: \(error)")
            logger.warning("Failed to join arena")
        }
    }

    public func refreshWorkerList() async {
        guard let controller = controller else { return }
        do {
            try await controller.requestWorkerListUpdate()
        } catch {
            logger.error("Failed to request worker list update: \(error)")
        }
    }

    private func createDefaultBaseConfig() -> LeniaBaseConfig {
        let gridSize = 128
        return LeniaBaseConfig(
            backend: "mlx",
            profile: .paper,
            grid: GridConfig(sx: gridSize, sy: gridSize),
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
                mode: "random",
                seed: 42,
                ranges: KernelParamRanges(
                    r: [0.2, 1.0], b: [0.0, 1.0], w: [0.01, 0.5], a: [0.0, 1.0],
                    m: [0.05, 0.5], s: [0.001, 0.2], h: [0.0, 1.0], R: [2.0, 25.0]
                ),
                r: nil, b: nil, w: nil, a: nil, m: nil, s: nil, h: nil, R: nil
            ),
            init: InitConfig(
                seed: 0,
                patches: [PatchConfig(center: [gridSize/2, gridSize/2], size: 40)],
                a_uniform: UniformRange(low: 0, high: 1),
                p_uniform: nil
            ),
            run: RunConfig(steps: 200),
            interventions: []
        )
    }

    private func createDefaultSearchConfig() -> ParsedSearchConfig {
        return ParsedSearchConfig(
            count: 0,
            seedStart: 0,
            seedStride: 1,
            initSeedOffset: 0,
            steps: 200,
            recordInterval: 50,
            warmupSteps: 100,
            occupancyThreshold: 0.05,
            massChannel: -1,
            scoreWeights: ["mass_mean": 1.0],
            filters: ["mass_min": 0.01],
            overrides: [:],
            topK: 10,
            batchSize: 4,
            seedsPerJob: nil,
            stability: StabilityConfig.defaultConfig,
            collection: CollectionConfig.defaultConfig
        )
    }

    private func ensureOutputRoot(path: String) throws -> URL {
        let expanded = (path as NSString).expandingTildeInPath
        let url = URL(fileURLWithPath: expanded, isDirectory: true)
        var isDir: ObjCBool = false
        if FileManager.default.fileExists(atPath: url.path, isDirectory: &isDir) {
            if !isDir.boolValue {
                throw NSError(domain: "LeniaStudio", code: 1, userInfo: [NSLocalizedDescriptionKey: "Output root path is not a directory."])
            }
        } else {
            try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        }
        return url
    }

    private func makeRunOutputDir(root: URL, runContext: RunContext) throws -> String {
        let hostId = sanitizePathComponent(runContext.controllerId)
        let runRoot = root
            .appendingPathComponent("hosts")
            .appendingPathComponent(hostId)
            .appendingPathComponent("runs")
            .appendingPathComponent(runContext.runId)
        try FileManager.default.createDirectory(at: runRoot, withIntermediateDirectories: true)
        return runRoot.path
    }

    private func sanitizePathComponent(_ value: String) -> String {
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_."))
        let scalars = value.unicodeScalars.map { allowed.contains($0) ? Character($0) : "-" }
        let sanitized = String(scalars).trimmingCharacters(in: CharacterSet(charactersIn: "-"))
        return sanitized.isEmpty ? "host" : sanitized
    }
}

// MARK: - Helper Extension

extension SimulationResultData {
    func toCreature(source: String) -> LeniaCreature {
        // Use workerId if available, otherwise fall back to provided source
        let nodeSource = self.workerId ?? source
        return LeniaCreature(
            seed: self.seed,
            score: self.score ?? 0.0,
            params: ResolvedParams(
                r: self.params.r,
                b: self.params.b,
                w: self.params.w,
                a: self.params.a,
                m: self.params.m,
                s: self.params.s,
                h: self.params.h,
                R: self.params.R,
                seed: self.seed
            ),
            sourceNode: nodeSource
        )
    }
}
