import SwiftUI
import LeniaCore
import DistributedCluster

// MARK: - Connection State

public enum ConnectionState: Equatable {
    case disconnected
    case connecting
    case connected(role: NodeRole)
    case error(String)

    public static func == (lhs: ConnectionState, rhs: ConnectionState) -> Bool {
        switch (lhs, rhs) {
        case (.disconnected, .disconnected): return true
        case (.connecting, .connecting): return true
        case (.connected(let a), .connected(let b)): return a == b
        case (.error(let a), .error(let b)): return a == b
        default: return false
        }
    }
}

public enum NodeRole: String, Equatable {
    case host = "Host"
    case worker = "Worker"
    case compendium = "Compendium"
}

public enum WorkerDiscoveryLens: String, CaseIterable, Identifiable {
    case now = "Now"
    case stable = "Stable"
    case fast = "Fast"
    case strange = "Strange"
    case byWorker = "By Worker"

    public var id: String { rawValue }
}

public enum WorkerActivityKind: String, Sendable {
    case localDiscovery
    case clusterUpdate
    case campaign
    case arena
    case system
}

public struct WorkerActivityItem: Identifiable, Sendable {
    public let id: UUID
    public let kind: WorkerActivityKind
    public let title: String
    public let detail: String
    public let timestamp: Date

    public init(
        id: UUID = UUID(),
        kind: WorkerActivityKind,
        title: String,
        detail: String,
        timestamp: Date = Date()
    ) {
        self.id = id
        self.kind = kind
        self.title = title
        self.detail = detail
        self.timestamp = timestamp
    }
}

public struct StudioReplayReference: Equatable, Hashable, Sendable {
    public let baseConfigPath: String
    public let searchConfigPath: String?
    public let runtimeFamily: String?

    public init(
        baseConfigPath: String,
        searchConfigPath: String? = nil,
        runtimeFamily: String? = nil
    ) {
        self.baseConfigPath = baseConfigPath
        self.searchConfigPath = searchConfigPath
        self.runtimeFamily = runtimeFamily
    }
}

public struct StudioCompareEntry: Identifiable, Hashable, Sendable {
    public let id: String
    public let creature: LeniaCreature
    public let savedCreature: SavedCreature?
    public let name: String
    public let subtitle: String
    public let metrics: SimulationMetrics?
    public let replayReference: StudioReplayReference?
    public let taxonomy: SpecimenTaxonomyRecord?
    public let traitLabels: [String]
    public let runtimeFamily: String?
    public let sourceMode: String?
    public let sourceAlgorithm: String?
    public let runtimeCapabilities: [String]

    public init(
        id: String,
        creature: LeniaCreature,
        savedCreature: SavedCreature? = nil,
        name: String,
        subtitle: String,
        metrics: SimulationMetrics? = nil,
        replayReference: StudioReplayReference? = nil,
        taxonomy: SpecimenTaxonomyRecord? = nil,
        traitLabels: [String] = [],
        runtimeFamily: String? = nil,
        sourceMode: String? = nil,
        sourceAlgorithm: String? = nil,
        runtimeCapabilities: [String] = []
    ) {
        self.id = id
        self.creature = creature
        self.savedCreature = savedCreature
        self.name = name
        self.subtitle = subtitle
        self.metrics = metrics
        self.replayReference = replayReference
        self.taxonomy = taxonomy
        self.traitLabels = traitLabels.sorted()
        self.runtimeFamily = runtimeFamily
        self.sourceMode = sourceMode
        self.sourceAlgorithm = sourceAlgorithm
        self.runtimeCapabilities = runtimeCapabilities.sorted()
    }

    public static func live(
        creature: LeniaCreature,
        name: String,
        subtitle: String? = nil,
        metrics: SimulationMetrics? = nil,
        replayReference: StudioReplayReference? = nil
    ) -> StudioCompareEntry {
        StudioCompareEntry(
            id: "live:\(creature.sourceNode):\(creature.seed)",
            creature: creature,
            name: name,
            subtitle: subtitle ?? creature.sourceNode,
            metrics: metrics,
            replayReference: replayReference
        )
    }

    public static func saved(
        _ creature: SavedCreature,
        replayReference: StudioReplayReference? = nil,
        taxonomy: SpecimenTaxonomyRecord? = nil,
        traitLabels: [String] = [],
        runtimeFamily: String? = nil,
        sourceMode: String? = nil,
        sourceAlgorithm: String? = nil,
        runtimeCapabilities: [String] = []
    ) -> StudioCompareEntry {
        StudioCompareEntry(
            id: "saved:\(creature.id.uuidString)",
            creature: creature.toLeniaCreature(),
            savedCreature: creature,
            name: creature.name,
            subtitle: creature.ownerId,
            metrics: creature.metrics,
            replayReference: replayReference,
            taxonomy: taxonomy,
            traitLabels: traitLabels,
            runtimeFamily: runtimeFamily,
            sourceMode: sourceMode,
            sourceAlgorithm: sourceAlgorithm,
            runtimeCapabilities: runtimeCapabilities
        )
    }

    public static func == (lhs: StudioCompareEntry, rhs: StudioCompareEntry) -> Bool {
        lhs.id == rhs.id
    }

    public func hash(into hasher: inout Hasher) {
        hasher.combine(id)
    }
}

// MARK: - App State

@MainActor
public final class AppState: ObservableObject {
    // Local discoveries
    @Published public var recentCreatures: [LeniaCreature] = []
    @Published public var topCreatures: [LeniaCreature] = []

    // Global cluster discoveries
    @Published public var globalBestCreatures: [LeniaCreature] = []

    // Creature library (persistent collection)
    @Published public var library: [SavedCreature] = []

    // Search state
    @Published public var isSearching: Bool = false
    @Published public var searchComplete: Bool = false

    // Arena state
    @Published public var activeArenaConfig: ArenaConfig?
    @Published public var arenaState: ArenaState?
    @Published public var currentArenaFrame: ArenaFrame?
    @Published public var connectedWorkers: [WorkerStatus] = []
    @Published public var availableArenas: [ArenaConfig] = []
    @Published public var arenaStates: [UUID: ArenaState] = [:]

    // Campaign state
    @Published public var activeCampaigns: [CampaignStatus] = []
    @Published public var latestDiscovery: StudioCompareEntry?
    @Published public var compareTray: [StudioCompareEntry] = []
    @Published public var activityFeed: [WorkerActivityItem] = []
    @Published public var workerDiscoveryLens: WorkerDiscoveryLens = .now
    @Published public var workerSearchText: String = ""
    @Published public var selectedCampaignId: UUID?
    @Published public var clusterSnapshot: ClusterSummary?

    // Connection state
    @Published public var connectionState: ConnectionState = .disconnected

    // Local worker identifier (to filter from explore section)
    @Published public var localWorkerId: String = ""

    // Progress
    @Published public var workersConnected: Int = 0
    @Published public var jobsCompleted: Int = 0
    @Published public var totalJobs: Int = 0
    @Published public var seedsProcessed: Int = 0
    @Published public var totalSeeds: Int = 0
    @Published public var currentRate: Double = 0
    @Published public var outputRootPath: String?
    @Published public var outputRunPath: String?
    @Published public var logFilePath: String?

    private let maxRecent = 50
    private let maxTop = 20
    private let maxCompare = 4
    private let maxActivity = 16

    public init() {}

    public func addCreature(_ creature: LeniaCreature) {
        // Add to recent (chronological, newest first)
        recentCreatures.insert(creature, at: 0)
        if recentCreatures.count > maxRecent {
            recentCreatures.removeLast()
        }

        // Add to top if it qualifies (sorted by score, highest first)
        if topCreatures.count < maxTop {
            topCreatures.append(creature)
            topCreatures.sort { $0.score > $1.score }
        } else if creature.score > (topCreatures.last?.score ?? 0) {
            topCreatures.removeLast()
            topCreatures.append(creature)
            topCreatures.sort { $0.score > $1.score }
        }

        latestDiscovery = studioEntry(for: creature)
        appendActivity(
            .init(
                kind: .localDiscovery,
                title: "Local discovery",
                detail: "Seed \(creature.seed) scored \(String(format: "%.3f", creature.score))"
            )
        )
    }

    public func updateGlobalList(_ creatures: [LeniaCreature]) {
        globalBestCreatures = creatures
    }

    public func updateLibrary(_ update: LibraryUpdate) {
        switch update {
        case .fullSync(let creatures):
            library = creatures
        case .creatureAdded(let creature):
            if !library.contains(where: { $0.id == creature.id }) {
                library.append(creature)
                if creature.ownerId == localWorkerId {
                    latestDiscovery = studioEntry(for: creature)
                }
            }
        }
    }

    public func addToLocalLibrary(_ creature: SavedCreature) {
        guard !library.contains(where: { $0.id == creature.id }) else { return }
        library.append(creature)
        latestDiscovery = studioEntry(for: creature)
        appendActivity(
            .init(
                kind: .localDiscovery,
                title: "Pinned to collection",
                detail: creature.name
            )
        )
    }

    public func clearCreatures() {
        recentCreatures.removeAll()
        topCreatures.removeAll()
        globalBestCreatures.removeAll()
        library.removeAll()
        activeCampaigns.removeAll()
        latestDiscovery = nil
        compareTray.removeAll()
        activityFeed.removeAll()
        clusterSnapshot = nil
        selectedCampaignId = nil
        searchComplete = false
        outputRootPath = nil
        outputRunPath = nil
        clearArena()
    }

    public func updateProgress(jobs: Int, totalJobs: Int, seeds: Int, totalSeeds: Int, rate: Double) {
        jobsCompleted = jobs
        self.totalJobs = totalJobs
        seedsProcessed = seeds
        self.totalSeeds = totalSeeds
        currentRate = rate
    }

    public func markSearchComplete() {
        isSearching = false
        searchComplete = true
    }

    public var progressFraction: Double {
        guard totalSeeds > 0 else { return 0 }
        return Double(seedsProcessed) / Double(totalSeeds)
    }

    public var progressText: String {
        if searchComplete {
            return "Complete: \(seedsProcessed) seeds"
        } else if isSearching {
            return "\(seedsProcessed)/\(totalSeeds) seeds (\(String(format: "%.1f", currentRate))/s)"
        } else {
            return "Idle"
        }
    }

    // MARK: - Arena Methods

    public func updateArenaInvite(_ config: ArenaConfig) {
        activeArenaConfig = config
        appendActivity(
            .init(
                kind: .arena,
                title: "Arena invite",
                detail: "\(config.size)x\(config.size), \(config.maxPlayers) players"
            )
        )
    }

    public func updateArenaState(_ state: ArenaState) {
        arenaState = state
        appendActivity(
            .init(
                kind: .arena,
                title: "Arena \(state.status.rawValue.capitalized)",
                detail: "\(state.participants.count) participant(s)"
            )
        )
    }

    public func updateArenaFrame(_ frame: ArenaFrame) {
        currentArenaFrame = frame
    }

    public func updateWorkerList(_ workers: [WorkerStatus]) {
        connectedWorkers = workers
        workersConnected = workers.count
    }

    public func clearArena() {
        activeArenaConfig = nil
        arenaState = nil
        currentArenaFrame = nil
    }

    public func addArena(_ config: ArenaConfig) {
        if !availableArenas.contains(where: { $0.id == config.id }) {
            availableArenas.append(config)
        }
        activeArenaConfig = config
    }

    public func removeArena(_ id: UUID) {
        availableArenas.removeAll { $0.id == id }
        arenaStates.removeValue(forKey: id)
        if activeArenaConfig?.id == id {
            activeArenaConfig = nil
            arenaState = nil
        }
    }

    public func updateArenaStateForId(_ id: UUID, state: ArenaState) {
        arenaStates[id] = state
        if activeArenaConfig?.id == id {
            arenaState = state
        }
    }

    // MARK: - Campaign Methods

    public func updateCampaigns(_ campaigns: [CampaignStatus]) {
        activeCampaigns = campaigns
        if let selectedCampaignId,
           !campaigns.contains(where: { $0.id == selectedCampaignId }) {
            self.selectedCampaignId = campaigns.first?.id
        } else if self.selectedCampaignId == nil {
            self.selectedCampaignId = campaigns.first?.id
        }
        if let campaign = campaigns.first {
            appendActivity(
                .init(
                    kind: .campaign,
                    title: "Campaign update",
                    detail: "\(campaign.name): \(campaign.processedSeeds)/\(campaign.totalSeeds) seeds"
                )
            )
        }
    }

    public func applyClusterSummary(_ snapshot: ClusterSummary) {
        let previousWorkerCount = connectedWorkers.count
        let previousCampaignCount = activeCampaigns.count
        clusterSnapshot = snapshot
        connectedWorkers = snapshot.workers
        activeCampaigns = snapshot.campaigns
        seedsProcessed = snapshot.totalSeedsProcessed
        currentRate = snapshot.clusterRate
        jobsCompleted = snapshot.completedJobs
        totalJobs = snapshot.totalJobs
        workersConnected = snapshot.workers.count
        if selectedCampaignId == nil || !snapshot.campaigns.contains(where: { $0.id == selectedCampaignId }) {
            selectedCampaignId = snapshot.campaigns.first?.id
        }
        if snapshot.workers.count != previousWorkerCount || snapshot.campaigns.count != previousCampaignCount {
            appendActivity(
                .init(
                    kind: .clusterUpdate,
                    title: "Cluster pulse",
                    detail: "\(snapshot.workers.count) workers, \(snapshot.campaigns.count) campaigns, \(snapshot.totalSeedsProcessed) seeds"
                )
            )
        }
    }

    public func addCompareEntry(_ entry: StudioCompareEntry) {
        guard !compareTray.contains(where: { $0.id == entry.id }) else { return }
        compareTray.append(entry)
        if compareTray.count > maxCompare {
            compareTray.removeFirst(compareTray.count - maxCompare)
        }
    }

    public func removeCompareEntry(id: String) {
        compareTray.removeAll { $0.id == id }
    }

    public func clearCompareTray() {
        compareTray.removeAll()
    }

    public var selectedCampaignSummary: CampaignStatus? {
        let preferredId = selectedCampaignId ?? activeCampaigns.first?.id
        return activeCampaigns.first(where: { $0.id == preferredId })
    }

    public var activeArenaSummaryText: String {
        guard let config = activeArenaConfig else { return "No arena right now" }
        let status = arenaState?.status.rawValue.capitalized ?? "Lobby"
        let participants = arenaState?.participants.count ?? 0
        return "\(status) • \(participants)/\(config.maxPlayers) • \(config.size)x\(config.size)"
    }

    public var clusterPulseText: String {
        let workerCount = clusterSnapshot?.workers.count ?? connectedWorkers.count
        let rateText: String
        if currentRate > 0 {
            rateText = String(format: "%.1f seeds/s", currentRate)
        } else {
            rateText = "waiting"
        }
        return "\(workerCount) workers • \(seedsProcessed) seeds • \(rateText)"
    }

    public func studioEntry(for creature: LeniaCreature) -> StudioCompareEntry {
        let saved = savedMatch(for: creature)
        if let saved {
            return studioEntry(for: saved)
        }
        return .live(
            creature: creature,
            name: "Seed \(creature.seed)",
            subtitle: creature.sourceNode
        )
    }

    public func studioEntry(for creature: SavedCreature) -> StudioCompareEntry {
        .saved(creature, replayReference: replayReference(for: creature))
    }

    public func replayReference(for creature: LeniaCreature) -> StudioReplayReference? {
        guard let saved = savedMatch(for: creature) else { return nil }
        return replayReference(for: saved)
    }

    public func replayReference(for creature: SavedCreature) -> StudioReplayReference? {
        guard let outputRunPath else { return nil }
        let exportsRoot = URL(fileURLWithPath: outputRunPath, isDirectory: true)
            .appendingPathComponent("exports", isDirectory: true)
        let exportDir = replayExportDirectory(root: exportsRoot, creature: creature)
        let baseURL = exportDir.appendingPathComponent("base.json")
        guard FileManager.default.fileExists(atPath: baseURL.path) else { return nil }
        let searchURL = exportDir.appendingPathComponent("search.json")
        let metaURL = exportDir.appendingPathComponent("meta.json")
        let runtimeFamily = loadReplayRuntimeFamily(from: metaURL)
        return StudioReplayReference(
            baseConfigPath: baseURL.path,
            searchConfigPath: FileManager.default.fileExists(atPath: searchURL.path) ? searchURL.path : nil,
            runtimeFamily: runtimeFamily
        )
    }

    public func filteredGlobalCreatures() -> [LeniaCreature] {
        let search = workerSearchText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let filtered = globalBestCreatures.filter { creature in
            if search.isEmpty { return true }
            return String(creature.seed).contains(search) || creature.sourceNode.lowercased().contains(search)
        }

        switch workerDiscoveryLens {
        case .now:
            return filtered.sorted { $0.timestamp > $1.timestamp }
        case .stable:
            return filtered
                .filter { savedMatch(for: $0)?.metrics.isStable == true }
                .sorted { $0.score > $1.score }
        case .fast:
            return filtered.sorted { lhs, rhs in
                metricVelocity(for: lhs) > metricVelocity(for: rhs)
            }
        case .strange:
            return filtered.sorted { lhs, rhs in
                metricComplexity(for: lhs) > metricComplexity(for: rhs)
            }
        case .byWorker:
            return filtered.sorted {
                if $0.sourceNode == $1.sourceNode {
                    return $0.score > $1.score
                }
                return $0.sourceNode < $1.sourceNode
            }
        }
    }

    private func metricVelocity(for creature: LeniaCreature) -> Float {
        savedMatch(for: creature)?.metrics.centerVelocity ?? 0
    }

    private func metricComplexity(for creature: LeniaCreature) -> Float {
        savedMatch(for: creature)?.metrics.complexityMean ?? 0
    }

    private func savedMatch(for creature: LeniaCreature) -> SavedCreature? {
        library.first(where: { $0.ownerId == creature.sourceNode && $0.initialCondition.seed == creature.seed })
    }

    private func appendActivity(_ item: WorkerActivityItem) {
        activityFeed.insert(item, at: 0)
        if activityFeed.count > maxActivity {
            activityFeed.removeLast(activityFeed.count - maxActivity)
        }
    }
}

private func loadReplayRuntimeFamily(from metaURL: URL) -> String? {
    guard let data = try? Data(contentsOf: metaURL) else { return nil }
    let decoder = JSONDecoder()
    return try? decodeCreatureExportMetadata(data, decoder: decoder).runtimeFamily
}
