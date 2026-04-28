import ArgumentParser
import CryptoKit
import Foundation
import LeniaCore
import SQLite3

private let portfolioSchemaVersion = 1
private let portfolioKernelVersion = "lenia-swarm-search-v1"

enum PortfolioArmKind: String, Codable {
    case priorSearch = "prior_search"
    case openES = "openes"
}

struct PortfolioCommand: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "portfolio",
        abstract: "Run pull-lease Lenia search campaigns with canonical candidate bundles",
        subcommands: [
            PortfolioInitCommand.self,
            PortfolioLeaseCommand.self,
            PortfolioWorkerCommand.self,
            PortfolioExportSeedsCommand.self,
            PortfolioRebuildCommand.self,
            PortfolioStatusCommand.self,
        ]
    )
}

struct PortfolioInitCommand: ParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "init",
        abstract: "Create a fixed-universe portfolio campaign with deterministic prior or seed-library shards"
    )

    @Option(name: .long, help: "Campaign id. Defaults to portfolio-<universe hash prefix>.")
    var campaignId: String?

    @Option(name: .long, help: "Universe id. Defaults to the base config hash.")
    var universeId: String?

    @Option(name: .long, help: "Sampler id recorded in shard and candidate manifests.")
    var samplerId: String = "prior-random"

    @Option(name: .long, help: "Path to fixed universe base config.json")
    var config: String

    @Option(name: .long, help: "Path to search config.json for prior-search campaigns")
    var search: String?

    @Option(name: .long, help: "Optional ES config.json. When present, each shard runs one OpenES search and bundles the best candidate.")
    var es: String?

    @Option(name: .shortAndLong, help: "Portfolio host root")
    var output: String

    @Option(name: .long, help: "Number of shards to materialize")
    var shards: Int

    @Option(name: .long, help: "Candidates per shard")
    var shardSize: Int

    @Option(name: .long, help: "Precision/runtime class. Defaults to backend:<base backend>.")
    var precisionClass: String?

    @Option(name: .long, help: "Path to library/index.jsonl, exports/index.jsonl, or patches.jsonl used to seed shard warm starts")
    var seedLibrary: String?

    @Option(name: .long, help: "Optional qd-2024 config directory when the seed library comes from qd-2024 and pattern assets are missing")
    var seedQDConfigDir: String?

    @Option(name: .long, parsing: .upToNextOption, help: "QD cell ids to use for warm starts when the seed library comes from qd-2024")
    var seedCell: [Int] = []

    @OptionGroup
    var seedSelection: ResearchSeedSelectionOptions

    @Flag(name: .long, help: "Also warm-start kernel parameters from each selected research seed when available")
    var seedKernelParams: Bool = false

    func run() throws {
        guard shards > 0 else { throw ValidationError("--shards must be > 0.") }
        guard shardSize > 0 else { throw ValidationError("--shard-size must be > 0.") }
        guard search != nil || es != nil else {
            throw ValidationError("portfolio init requires exactly one arm: --search for prior-search or --es for OpenES.")
        }
        if search != nil, es != nil {
            throw ValidationError("portfolio init accepts exactly one arm; use --search or --es, not both.")
        }
        if es != nil, shardSize != 1 {
            throw ValidationError("--es requires --shard-size 1 because each shard is one OpenES run.")
        }
        if seedKernelParams, seedLibrary == nil {
            throw ValidationError("--seed-kernel-params requires --seed-library.")
        }

        let resolvedOutput = try resolveArtifactPath(output, dossier: dossierName)
        let root = URL(fileURLWithPath: resolvedOutput, isDirectory: true)
        let baseURL = URL(fileURLWithPath: try resolvePath(config, dossier: dossierName))
        let searchURL = try search.map { URL(fileURLWithPath: try resolvePath($0, dossier: dossierName)) }
        let baseData = try Data(contentsOf: baseURL)
        let searchData = try searchURL.map { try Data(contentsOf: $0) }
        let esURL = try es.map { URL(fileURLWithPath: try resolvePath($0, dossier: dossierName)) }
        let esData = try esURL.map { try Data(contentsOf: $0) }
        let baseConfig = try JSONDecoder().decode(LeniaBaseConfig.self, from: baseData)
        let searchConfig = try searchData.map { try JSONDecoder().decode(ParsedSearchConfig.self, from: $0) }
        let esConfig = try esData.map { try JSONDecoder().decode(ESConfig.self, from: $0) }
        if let searchConfig, searchConfig.seedStride <= 0 {
            throw ValidationError("search.seed_stride must be > 0.")
        }

        let resolvedUniverseID = normalized(universeId) ?? researchConfigHash([("base", baseData)])
        let resolvedCampaignID = normalized(campaignId) ?? "portfolio-\(String(resolvedUniverseID.prefix(12)))"
        let resolvedPrecisionClass = normalized(precisionClass) ?? "backend:\(baseConfig.backend)"
        let resolvedSeedLibrary = try seedLibrary.map { try resolveArtifactPath($0, dossier: dossierName) }
        let resolvedQDConfigDir = try seedQDConfigDir.map { try resolvePath($0, dossier: dossierName) }
        let resolvedSeedSelection = try seedSelection.resolvedSelection()
        let seedPatches = try PortfolioSeedPatchCatalog.load(
            libraryPath: resolvedSeedLibrary,
            qdConfigDirectory: resolvedQDConfigDir,
            cells: seedCell,
            selection: resolvedSeedSelection
        )
        let arm: PortfolioArmKind = esConfig == nil ? .priorSearch : .openES
        let samplerKind: String
        if arm == .openES {
            samplerKind = seedPatches.isEmpty ? "openes" : "openes-seed-library"
        } else {
            samplerKind = seedPatches.isEmpty ? "prior-random" : "seed-library-prior"
        }
        let manifest = PortfolioCampaignManifest(
            campaignID: resolvedCampaignID,
            universeID: resolvedUniverseID,
            samplerID: samplerId,
            samplerKind: samplerKind,
            arm: arm,
            precisionClass: resolvedPrecisionClass,
            leniaKernelVersion: portfolioKernelVersion,
            baseConfigPath: baseURL.path,
            searchConfigPath: searchURL?.path,
            esConfigPath: esURL?.path,
            seedLibraryPath: resolvedSeedLibrary,
            seedQDConfigDirectory: resolvedQDConfigDir,
            seedCells: seedCell,
            seedSelection: resolvedSeedSelection,
            seedKernelParams: seedKernelParams,
            seedPatchCount: seedPatches.count,
            artifactRoot: root.appendingPathComponent("artifacts", isDirectory: true).path,
            shardCount: shards,
            shardSize: shardSize,
            baseConfig: baseConfig,
            searchConfig: searchConfig,
            esConfig: esConfig,
            configHash: researchConfigHash([
                ("base", baseData),
                ("search", searchData ?? Data()),
                ("es", esData ?? Data()),
                ("sampler", Data(samplerId.utf8)),
            ])
        )

        let store = try PortfolioHostStore(root: root)
        try store.initialize(manifest: manifest, seedPatches: seedPatches)
        print("portfolio campaign \(resolvedCampaignID) initialized at \(root.path)")
    }
}

struct PortfolioLeaseCommand: ParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "lease",
        abstract: "Lease the next available deterministic shard"
    )

    @Option(name: .shortAndLong, help: "Portfolio host root")
    var host: String

    @Option(name: .long, help: "Worker id recorded in lease and candidate provenance")
    var workerId: String

    @Option(name: .long, help: "Lease TTL in seconds")
    var ttlSeconds: Int = 900

    func run() throws {
        guard ttlSeconds > 0 else { throw ValidationError("--ttl-seconds must be > 0.") }
        let store = try PortfolioHostStore(root: URL(fileURLWithPath: try resolveArtifactPath(host, dossier: dossierName), isDirectory: true))
        guard let lease = try store.lease(workerID: workerId, ttlSeconds: ttlSeconds) else {
            print("{}")
            return
        }
        try printJSON(lease)
    }
}

struct PortfolioWorkerCommand: ParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "worker",
        abstract: "Lease, evaluate, ingest, and complete portfolio shards"
    )

    @Option(name: .shortAndLong, help: "Portfolio host root")
    var host: String

    @Option(name: .long, help: "Worker id recorded in lease and candidate provenance")
    var workerId: String

    @Option(name: .long, help: "Lease TTL in seconds")
    var ttlSeconds: Int = 900

    @Option(name: .long, help: "Maximum shards to process before exiting. Defaults to draining currently available work.")
    var maxShards: Int?

    @Option(name: .long, help: "Seconds to wait for new work after the queue is empty. Defaults to 0.")
    var idleTimeoutSeconds: Double = 0

    @Option(name: .long, help: "Polling interval in seconds while waiting for work")
    var pollSeconds: Double = 2

    func run() throws {
        guard ttlSeconds > 0 else { throw ValidationError("--ttl-seconds must be > 0.") }
        if let maxShards, maxShards <= 0 {
            throw ValidationError("--max-shards must be > 0.")
        }
        guard idleTimeoutSeconds >= 0 else { throw ValidationError("--idle-timeout-seconds must be >= 0.") }
        guard pollSeconds > 0 else { throw ValidationError("--poll-seconds must be > 0.") }
        let store = try PortfolioHostStore(root: URL(fileURLWithPath: try resolveArtifactPath(host, dossier: dossierName), isDirectory: true))
        var completed = 0
        var idleStartedAt: Date?
        while maxShards.map({ completed < $0 }) ?? true {
            guard let lease = try store.lease(workerID: workerId, ttlSeconds: ttlSeconds) else {
                if idleTimeoutSeconds <= 0 { break }
                let now = Date()
                if idleStartedAt == nil {
                    idleStartedAt = now
                }
                if let idleStartedAt, now.timeIntervalSince(idleStartedAt) >= idleTimeoutSeconds {
                    break
                }
                let remainingIdleSeconds = idleTimeoutSeconds - (idleStartedAt.map { now.timeIntervalSince($0) } ?? 0)
                Thread.sleep(forTimeInterval: min(pollSeconds, max(0.1, remainingIdleSeconds)))
                continue
            }
            idleStartedAt = nil
            let bundles = try PortfolioShardEvaluator.evaluate(lease: lease, workerID: workerId)
            for bundle in bundles {
                try store.ingest(bundle: bundle, workerID: workerId)
            }
            try store.complete(campaignID: lease.campaignID, shardIndex: lease.shardIndex, workerID: workerId)
            completed += 1
            print("completed shard \(lease.shardIndex) with \(bundles.count) candidate bundles")
        }
        print("worker \(workerId) completed \(completed) shards")
    }
}

struct PortfolioRebuildCommand: ParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "rebuild",
        abstract: "Rebuild the SQLite candidate index from artifact bundles"
    )

    @Option(name: .shortAndLong, help: "Portfolio host root")
    var host: String

    func run() throws {
        let store = try PortfolioHostStore(root: URL(fileURLWithPath: try resolveArtifactPath(host, dossier: dossierName), isDirectory: true))
        let count = try store.rebuildCandidateIndex()
        print("rebuilt candidate index: \(count) bundles")
    }
}

struct PortfolioExportSeedsCommand: ParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "export-seeds",
        abstract: "Export descriptor-representative portfolio terminal states as a research seed patch library"
    )

    @Option(name: .shortAndLong, help: "Portfolio host root")
    var host: String

    @Option(name: .shortAndLong, help: "Output patches.jsonl path")
    var output: String

    @Option(name: .long, help: "Maximum seed patches to export")
    var limit: Int = 64

    func run() throws {
        guard limit > 0 else { throw ValidationError("--limit must be > 0.") }
        let store = try PortfolioHostStore(root: URL(fileURLWithPath: try resolveArtifactPath(host, dossier: dossierName), isDirectory: true))
        let outputURL = URL(fileURLWithPath: try resolveArtifactPath(output, dossier: dossierName))
        let count = try store.exportSeedPatches(limit: limit, to: outputURL)
        print("exported \(count) portfolio seed patches to \(outputURL.path)")
    }
}

struct PortfolioStatusCommand: ParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "status",
        abstract: "Print portfolio campaign shard, candidate, and diversity counts"
    )

    @Option(name: .shortAndLong, help: "Portfolio host root")
    var host: String

    func run() throws {
        let store = try PortfolioHostStore(root: URL(fileURLWithPath: try resolveArtifactPath(host, dossier: dossierName), isDirectory: true))
        try printJSON(store.status())
    }
}

struct PortfolioCampaignManifest: Codable {
    let schemaVersion: Int
    let campaignID: String
    let universeID: String
    let samplerID: String
    let samplerKind: String
    let arm: PortfolioArmKind
    let precisionClass: String
    let leniaKernelVersion: String
    let baseConfigPath: String
    let searchConfigPath: String?
    let esConfigPath: String?
    let seedLibraryPath: String?
    let seedQDConfigDirectory: String?
    let seedCells: [Int]
    let seedSelection: ResearchSeedSelection?
    let seedKernelParams: Bool
    let seedPatchCount: Int
    let artifactRoot: String
    let shardCount: Int
    let shardSize: Int
    let baseConfig: LeniaBaseConfig
    let searchConfig: ParsedSearchConfig?
    let esConfig: ESConfig?
    let configHash: String
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case campaignID = "campaign_id"
        case universeID = "universe_id"
        case samplerID = "sampler_id"
        case samplerKind = "sampler_kind"
        case arm
        case precisionClass = "precision_class"
        case leniaKernelVersion = "lenia_kernel_version"
        case baseConfigPath = "base_config_path"
        case searchConfigPath = "search_config_path"
        case esConfigPath = "es_config_path"
        case seedLibraryPath = "seed_library_path"
        case seedQDConfigDirectory = "seed_qd_config_directory"
        case seedCells = "seed_cells"
        case seedSelection = "seed_selection"
        case seedKernelParams = "seed_kernel_params"
        case seedPatchCount = "seed_patch_count"
        case artifactRoot = "artifact_root"
        case shardCount = "shard_count"
        case shardSize = "shard_size"
        case baseConfig = "base_config"
        case searchConfig = "search_config"
        case esConfig = "es_config"
        case configHash = "config_hash"
        case createdAt = "created_at"
    }

    init(
        campaignID: String,
        universeID: String,
        samplerID: String,
        samplerKind: String,
        arm: PortfolioArmKind,
        precisionClass: String,
        leniaKernelVersion: String,
        baseConfigPath: String,
        searchConfigPath: String? = nil,
        esConfigPath: String? = nil,
        seedLibraryPath: String? = nil,
        seedQDConfigDirectory: String? = nil,
        seedCells: [Int] = [],
        seedSelection: ResearchSeedSelection? = nil,
        seedKernelParams: Bool = false,
        seedPatchCount: Int = 0,
        artifactRoot: String,
        shardCount: Int,
        shardSize: Int,
        baseConfig: LeniaBaseConfig,
        searchConfig: ParsedSearchConfig? = nil,
        esConfig: ESConfig? = nil,
        configHash: String,
        createdAt: Date = Date()
    ) {
        self.schemaVersion = portfolioSchemaVersion
        self.campaignID = campaignID
        self.universeID = universeID
        self.samplerID = samplerID
        self.samplerKind = samplerKind
        self.arm = arm
        self.precisionClass = precisionClass
        self.leniaKernelVersion = leniaKernelVersion
        self.baseConfigPath = baseConfigPath
        self.searchConfigPath = searchConfigPath
        self.esConfigPath = esConfigPath
        self.seedLibraryPath = seedLibraryPath
        self.seedQDConfigDirectory = seedQDConfigDirectory
        self.seedCells = seedCells
        self.seedSelection = seedSelection
        self.seedKernelParams = seedKernelParams
        self.seedPatchCount = seedPatchCount
        self.artifactRoot = artifactRoot
        self.shardCount = shardCount
        self.shardSize = shardSize
        self.baseConfig = baseConfig
        self.searchConfig = searchConfig
        self.esConfig = esConfig
        self.configHash = configHash
        self.createdAt = createdAt
    }
}

struct PortfolioShardLease: Codable {
    let schemaVersion: Int
    let campaignID: String
    let universeID: String
    let samplerID: String
    let samplerKind: String
    let arm: PortfolioArmKind
    let shardIndex: Int
    let shardSize: Int
    let seeds: [Int]
    let seedPatchIndex: Int?
    let seedPatchHash: String?
    let seedPatch: ResearchSeedPatch?
    let seedKernelParams: Bool
    let workerID: String
    let leasedAt: Date
    let expiresAt: Date
    let precisionClass: String
    let leniaKernelVersion: String
    let artifactRoot: String
    let baseConfig: LeniaBaseConfig
    let searchConfig: ParsedSearchConfig?
    let esConfig: ESConfig?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case campaignID = "campaign_id"
        case universeID = "universe_id"
        case samplerID = "sampler_id"
        case samplerKind = "sampler_kind"
        case arm
        case shardIndex = "shard_index"
        case shardSize = "shard_size"
        case seeds
        case seedPatchIndex = "seed_patch_index"
        case seedPatchHash = "seed_patch_hash"
        case seedPatch = "seed_patch"
        case seedKernelParams = "seed_kernel_params"
        case workerID = "worker_id"
        case leasedAt = "leased_at"
        case expiresAt = "expires_at"
        case precisionClass = "precision_class"
        case leniaKernelVersion = "lenia_kernel_version"
        case artifactRoot = "artifact_root"
        case baseConfig = "base_config"
        case searchConfig = "search_config"
        case esConfig = "es_config"
    }

    fileprivate init(
        manifest: PortfolioCampaignManifest,
        shardIndex: Int,
        spec: PortfolioShardSpec,
        seedPatch: ResearchSeedPatch?,
        workerID: String,
        leasedAt: Date,
        expiresAt: Date
    ) {
        self.schemaVersion = portfolioSchemaVersion
        self.campaignID = manifest.campaignID
        self.universeID = manifest.universeID
        self.samplerID = manifest.samplerID
        self.samplerKind = manifest.samplerKind
        self.arm = manifest.arm
        self.shardIndex = shardIndex
        self.shardSize = spec.seeds.count
        self.seeds = spec.seeds
        self.seedPatchIndex = spec.seedPatchIndex
        self.seedPatchHash = spec.seedPatchHash
        self.seedPatch = seedPatch
        self.seedKernelParams = manifest.seedKernelParams
        self.workerID = workerID
        self.leasedAt = leasedAt
        self.expiresAt = expiresAt
        self.precisionClass = manifest.precisionClass
        self.leniaKernelVersion = manifest.leniaKernelVersion
        self.artifactRoot = manifest.artifactRoot
        self.baseConfig = manifest.baseConfig
        self.searchConfig = manifest.searchConfig
        self.esConfig = manifest.esConfig
    }
}

struct PortfolioCandidateBundleRecord: Codable {
    let contentHash: String
    let bundlePath: String
    let campaignID: String
    let universeID: String
    let samplerID: String
    let shardIndex: Int
    let localIndex: Int
    let seed: Int
    let initSeed: Int
    let score: Float?
    let filtersPassed: Bool
    let genotypeHash: String?
    let fingerprintHash: String?

    enum CodingKeys: String, CodingKey {
        case contentHash = "content_hash"
        case bundlePath = "bundle_path"
        case campaignID = "campaign_id"
        case universeID = "universe_id"
        case samplerID = "sampler_id"
        case shardIndex = "shard_index"
        case localIndex = "local_index"
        case seed
        case initSeed = "init_seed"
        case score
        case filtersPassed = "filters_passed"
        case genotypeHash = "genotype_hash"
        case fingerprintHash = "fingerprint_hash"
    }
}

private struct PortfolioShardSpec: Codable {
    let schemaVersion: Int
    let seeds: [Int]
    let seedPatchIndex: Int?
    let seedPatchHash: String?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case seeds
        case seedPatchIndex = "seed_patch_index"
        case seedPatchHash = "seed_patch_hash"
    }

    init(seeds: [Int], seedPatchIndex: Int? = nil, seedPatchHash: String? = nil) {
        self.schemaVersion = portfolioSchemaVersion
        self.seeds = seeds
        self.seedPatchIndex = seedPatchIndex
        self.seedPatchHash = seedPatchHash
    }
}

private struct PortfolioSeedPatchRecord: Codable {
    let index: Int
    let contentHash: String
    let patch: ResearchSeedPatch

    enum CodingKeys: String, CodingKey {
        case index
        case contentHash = "content_hash"
        case patch
    }
}

struct PortfolioUniverseBundle: Codable {
    let schemaVersion: Int
    let universeID: String
    let precisionClass: String
    let leniaKernelVersion: String
    let topologyHash: String
    let baseConfig: LeniaBaseConfig

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case universeID = "universe_id"
        case precisionClass = "precision_class"
        case leniaKernelVersion = "lenia_kernel_version"
        case topologyHash = "topology_hash"
        case baseConfig = "base_config"
    }
}

struct PortfolioSamplerBundle: Codable {
    let schemaVersion: Int
    let samplerID: String
    let samplerKind: String
    let seedDerivation: String
    let seedPatchIndex: Int?
    let seedPatchHash: String?
    let seedPatchSourceID: String?
    let seedPatchName: String?
    let seedKernelParams: Bool
    let searchConfig: ParsedSearchConfig?
    let esConfig: ESConfig?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case samplerID = "sampler_id"
        case samplerKind = "sampler_kind"
        case seedDerivation = "seed_derivation"
        case seedPatchIndex = "seed_patch_index"
        case seedPatchHash = "seed_patch_hash"
        case seedPatchSourceID = "seed_patch_source_id"
        case seedPatchName = "seed_patch_name"
        case seedKernelParams = "seed_kernel_params"
        case searchConfig = "search_config"
        case esConfig = "es_config"
    }
}

struct PortfolioCandidateCore: Codable {
    let schemaVersion: Int
    let campaignID: String
    let universeID: String
    let samplerID: String
    let shardIndex: Int
    let localIndex: Int
    let seed: Int
    let initSeed: Int
    let backend: String
    let implementation: ImplementationSettings
    let score: Float?
    let scoreWeights: [String: Float]?
    let filtersPassed: Bool
    let filters: [String: Float]
    let params: KernelParams
    let descriptorBundle: MorphospaceDescriptorBundle?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case campaignID = "campaign_id"
        case universeID = "universe_id"
        case samplerID = "sampler_id"
        case shardIndex = "shard_index"
        case localIndex = "local_index"
        case seed
        case initSeed = "init_seed"
        case backend
        case implementation
        case score
        case scoreWeights = "score_weights"
        case filtersPassed = "filters_passed"
        case filters
        case params
        case descriptorBundle = "descriptor_bundle"
    }
}

struct PortfolioBundleManifest: Codable {
    let schemaVersion: Int
    let bundleKind: String
    let contentHash: String
    let contentHashInputs: [String]
    let campaignID: String
    let universeID: String
    let samplerID: String
    let shardIndex: Int
    let localIndex: Int
    let workerID: String
    let createdAt: Date
    let files: [String]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case bundleKind = "bundle_kind"
        case contentHash = "content_hash"
        case contentHashInputs = "content_hash_inputs"
        case campaignID = "campaign_id"
        case universeID = "universe_id"
        case samplerID = "sampler_id"
        case shardIndex = "shard_index"
        case localIndex = "local_index"
        case workerID = "worker_id"
        case createdAt = "created_at"
        case files
    }
}

private struct PortfolioStatus: Codable {
    let campaigns: Int
    let pendingShards: Int
    let leasedShards: Int
    let doneShards: Int
    let candidateCount: Int
    let genotypeCount: Int
    let fingerprintCount: Int
    let archive: PortfolioArchiveSummary
    let seedPatchCount: Int

    enum CodingKeys: String, CodingKey {
        case campaigns
        case pendingShards = "pending_shards"
        case leasedShards = "leased_shards"
        case doneShards = "done_shards"
        case candidateCount = "candidate_count"
        case genotypeCount = "genotype_count"
        case fingerprintCount = "fingerprint_count"
        case archive
        case seedPatchCount = "seed_patch_count"
    }
}

private final class PortfolioHostStore {
    private let root: URL
    private let db: SQLiteDB
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    init(root: URL) throws {
        self.root = root
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: root.appendingPathComponent("artifacts", isDirectory: true), withIntermediateDirectories: true)
        db = try SQLiteDB(path: root.appendingPathComponent("portfolio.sqlite").path)
        decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .deferredToDate
        encoder = portfolioJSONEncoder(prettyPrinted: true)
        try createSchema()
    }

    func initialize(manifest: PortfolioCampaignManifest, seedPatches: [PortfolioSeedPatchRecord]) throws {
        try writeJSON(manifest, to: root.appendingPathComponent("campaign-manifest.json"), encoder: encoder)
        try writeJSON(manifest.baseConfig, to: root.appendingPathComponent("universe.json"), encoder: encoder)
        if let searchConfig = manifest.searchConfig {
            try writeJSON(searchConfig, to: root.appendingPathComponent("search.json"), encoder: encoder)
        }
        if let esConfig = manifest.esConfig {
            try writeJSON(esConfig, to: root.appendingPathComponent("es.json"), encoder: encoder)
        }
        try writeSeedPatchCatalog(seedPatches)
        try db.withImmediateTransaction {
            try upsertCampaign(manifest)
            try replaceShards(manifest, seedPatches: seedPatches)
        }
    }

    func lease(workerID: String, ttlSeconds: Int) throws -> PortfolioShardLease? {
        let now = Date()
        let nowValue = now.timeIntervalSince1970
        let expires = now.addingTimeInterval(TimeInterval(ttlSeconds))
        var lease: PortfolioShardLease?
        try db.withImmediateTransaction {
            try db.exec("""
                UPDATE shards
                SET status = 'pending', leased_by = NULL, leased_at = NULL, expires_at = NULL
                WHERE status = 'leased' AND expires_at <= \(nowValue)
            """)

            let select = try db.prepare("""
                SELECT campaign_id, shard_index, shard_json
                FROM shards
                WHERE status = 'pending'
                ORDER BY shard_index
                LIMIT 1
            """)
            defer { sqlite3_finalize(select) }
            guard sqlite3_step(select) == SQLITE_ROW,
                  let campaignID = columnText(select, index: 0),
                  let shardJSON = columnText(select, index: 2),
                  let shardData = shardJSON.data(using: .utf8)
            else {
                return
            }
            let shardIndex = Int(sqlite3_column_int64(select, 1))
            let manifest = try loadCampaignManifest(campaignID: campaignID)
            let spec = try decodeShardSpec(from: shardData)
            let seedPatch = try loadSeedPatch(index: spec.seedPatchIndex, expectedHash: spec.seedPatchHash)
            let selectedLease = PortfolioShardLease(
                manifest: manifest,
                shardIndex: shardIndex,
                spec: spec,
                seedPatch: seedPatch,
                workerID: workerID,
                leasedAt: now,
                expiresAt: expires
            )
            let update = try db.prepare("""
                UPDATE shards
                SET status = 'leased', leased_by = ?, leased_at = ?, expires_at = ?, attempts = attempts + 1
                WHERE campaign_id = ? AND shard_index = ? AND status = 'pending'
            """)
            defer { sqlite3_finalize(update) }
            db.bindText(update, index: 1, value: workerID)
            db.bindDouble(update, index: 2, value: nowValue)
            db.bindDouble(update, index: 3, value: expires.timeIntervalSince1970)
            db.bindText(update, index: 4, value: campaignID)
            db.bindInt(update, index: 5, value: shardIndex)
            try db.step(update)
            guard db.changes() == 1 else {
                throw ValidationError("Failed to lease portfolio shard \(shardIndex).")
            }
            lease = selectedLease
        }
        return lease
    }

    func ingest(bundle: PortfolioCandidateBundleRecord, workerID: String) throws {
        let stmt = try db.prepare("""
            INSERT INTO candidates (
                content_hash, campaign_id, universe_id, sampler_id, shard_index, local_index,
                seed, init_seed, score, filters_passed, genotype_hash, fingerprint_hash,
                bundle_path, worker_id, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(content_hash) DO UPDATE SET
                bundle_path = excluded.bundle_path,
                worker_id = excluded.worker_id,
                ingested_at = excluded.ingested_at
        """)
        defer { sqlite3_finalize(stmt) }
        db.bindText(stmt, index: 1, value: bundle.contentHash)
        db.bindText(stmt, index: 2, value: bundle.campaignID)
        db.bindText(stmt, index: 3, value: bundle.universeID)
        db.bindText(stmt, index: 4, value: bundle.samplerID)
        db.bindInt(stmt, index: 5, value: bundle.shardIndex)
        db.bindInt(stmt, index: 6, value: bundle.localIndex)
        db.bindInt(stmt, index: 7, value: bundle.seed)
        db.bindInt(stmt, index: 8, value: bundle.initSeed)
        db.bindDouble(stmt, index: 9, value: bundle.score)
        db.bindBool(stmt, index: 10, value: bundle.filtersPassed)
        db.bindText(stmt, index: 11, value: bundle.genotypeHash)
        db.bindText(stmt, index: 12, value: bundle.fingerprintHash)
        db.bindText(stmt, index: 13, value: bundle.bundlePath)
        db.bindText(stmt, index: 14, value: workerID)
        db.bindDouble(stmt, index: 15, value: Date().timeIntervalSince1970)
        try db.step(stmt)
    }

    func complete(campaignID: String, shardIndex: Int, workerID: String) throws {
        let stmt = try db.prepare("""
            UPDATE shards
            SET status = 'done', completed_at = ?
            WHERE campaign_id = ? AND shard_index = ? AND leased_by = ?
        """)
        defer { sqlite3_finalize(stmt) }
        db.bindDouble(stmt, index: 1, value: Date().timeIntervalSince1970)
        db.bindText(stmt, index: 2, value: campaignID)
        db.bindInt(stmt, index: 3, value: shardIndex)
        db.bindText(stmt, index: 4, value: workerID)
        try db.step(stmt)
        guard db.changes() == 1 else {
            throw ValidationError("Worker \(workerID) cannot complete unleased portfolio shard \(shardIndex).")
        }
    }

    func rebuildCandidateIndex() throws -> Int {
        try db.exec("DELETE FROM candidates")
        let artifactRoot = root.appendingPathComponent("artifacts/candidates", isDirectory: true)
        guard let enumerator = FileManager.default.enumerator(
            at: artifactRoot,
            includingPropertiesForKeys: [.isRegularFileKey],
            options: [.skipsHiddenFiles]
        ) else {
            return 0
        }
        var count = 0
        for case let manifestURL as URL in enumerator where manifestURL.lastPathComponent == "manifest.json" {
            let bundleDir = manifestURL.deletingLastPathComponent()
            let manifest = try decoder.decode(PortfolioBundleManifest.self, from: Data(contentsOf: manifestURL))
            let candidate = try decoder.decode(
                PortfolioCandidateCore.self,
                from: Data(contentsOf: bundleDir.appendingPathComponent("candidate.json"))
            )
            let record = PortfolioCandidateBundleRecord(
                contentHash: manifest.contentHash,
                bundlePath: bundleDir.path,
                campaignID: manifest.campaignID,
                universeID: manifest.universeID,
                samplerID: manifest.samplerID,
                shardIndex: manifest.shardIndex,
                localIndex: manifest.localIndex,
                seed: candidate.seed,
                initSeed: candidate.initSeed,
                score: candidate.score,
                filtersPassed: candidate.filtersPassed,
                genotypeHash: candidate.descriptorBundle?.genotype.hash12,
                fingerprintHash: candidate.descriptorBundle?.terminal.fingerprintHash12
            )
            try ingest(bundle: record, workerID: manifest.workerID)
            count += 1
        }
        return count
    }

    func exportSeedPatches(limit: Int, to outputURL: URL) throws -> Int {
        let bundles = try discoverPortfolioCandidateBundles(from: root, top: limit)
        let encoder = portfolioJSONEncoder()
        var lines: [String] = []
        lines.reserveCapacity(bundles.count)
        for bundle in bundles {
            let core = try decoder.decode(
                PortfolioCandidateCore.self,
                from: Data(contentsOf: bundle.directoryURL.appendingPathComponent("candidate.json"))
            )
            let statePatchURL = bundle.directoryURL.appendingPathComponent("terminal_state_patch.json")
            guard FileManager.default.fileExists(atPath: statePatchURL.path) else { continue }
            let statePatch = try decoder.decode(InitStatePatchConfig.self, from: Data(contentsOf: statePatchURL))
            let seedPatch = ResearchSeedPatch(
                sourceID: "portfolio-\(bundle.manifest.contentHash.prefix(16))",
                name: "portfolio-\(bundle.manifest.contentHash.prefix(12))",
                world: statePatch.toWorldState(),
                score: bundle.candidate.score,
                metrics: bundle.metrics,
                kernelParams: core.params
            )
            lines.append(String(decoding: try encoder.encode(seedPatch), as: UTF8.self))
        }
        try FileManager.default.createDirectory(at: outputURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        try Data((lines.joined(separator: "\n") + (lines.isEmpty ? "" : "\n")).utf8).write(to: outputURL, options: .atomic)
        return lines.count
    }

    func status() throws -> PortfolioStatus {
        let candidateCount = try db.scalarInt("SELECT COUNT(*) FROM candidates")
        let representativeLimit = 12
        return PortfolioStatus(
            campaigns: try db.scalarInt("SELECT COUNT(*) FROM campaigns"),
            pendingShards: try db.scalarInt("SELECT COUNT(*) FROM shards WHERE status = 'pending'"),
            leasedShards: try db.scalarInt("SELECT COUNT(*) FROM shards WHERE status = 'leased'"),
            doneShards: try db.scalarInt("SELECT COUNT(*) FROM shards WHERE status = 'done'"),
            candidateCount: candidateCount,
            genotypeCount: try db.scalarInt("SELECT COUNT(DISTINCT genotype_hash) FROM candidates WHERE genotype_hash IS NOT NULL"),
            fingerprintCount: try db.scalarInt("SELECT COUNT(DISTINCT fingerprint_hash) FROM candidates WHERE fingerprint_hash IS NOT NULL"),
            archive: candidateCount == 0
                ? PortfolioArchiveSummary.empty(limit: representativeLimit)
                : try summarizePortfolioArchive(from: root, representativeLimit: representativeLimit),
            seedPatchCount: try loadSeedPatchCatalog().count
        )
    }

    private func createSchema() throws {
        try db.exec("PRAGMA journal_mode=WAL")
        try db.exec("PRAGMA busy_timeout=30000")
        try db.exec("""
            CREATE TABLE IF NOT EXISTS campaigns (
                campaign_id TEXT PRIMARY KEY,
                universe_id TEXT NOT NULL,
                sampler_id TEXT NOT NULL,
                sampler_kind TEXT NOT NULL,
                arm TEXT NOT NULL,
                precision_class TEXT NOT NULL,
                lenia_kernel_version TEXT NOT NULL,
                base_config_path TEXT NOT NULL,
                search_config_path TEXT,
                es_config_path TEXT,
                artifact_root TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                manifest_json TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        try db.exec("""
            CREATE TABLE IF NOT EXISTS shards (
                campaign_id TEXT NOT NULL,
                shard_index INTEGER NOT NULL,
                status TEXT NOT NULL,
                shard_json TEXT NOT NULL,
                leased_by TEXT,
                leased_at REAL,
                expires_at REAL,
                completed_at REAL,
                attempts INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (campaign_id, shard_index)
            )
        """)
        try db.exec("""
            CREATE TABLE IF NOT EXISTS candidates (
                content_hash TEXT PRIMARY KEY,
                campaign_id TEXT NOT NULL,
                universe_id TEXT NOT NULL,
                sampler_id TEXT NOT NULL,
                shard_index INTEGER NOT NULL,
                local_index INTEGER NOT NULL,
                seed INTEGER NOT NULL,
                init_seed INTEGER NOT NULL,
                score REAL,
                filters_passed INTEGER NOT NULL,
                genotype_hash TEXT,
                fingerprint_hash TEXT,
                bundle_path TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                ingested_at REAL NOT NULL
            )
        """)
        try db.exec("CREATE INDEX IF NOT EXISTS portfolio_shards_status ON shards(status, expires_at)")
        try db.exec("DROP INDEX IF EXISTS portfolio_candidates_score")
        try db.exec("CREATE INDEX IF NOT EXISTS portfolio_candidates_genotype ON candidates(genotype_hash)")
        try db.exec("CREATE INDEX IF NOT EXISTS portfolio_candidates_fingerprint ON candidates(fingerprint_hash)")
    }

    private func upsertCampaign(_ manifest: PortfolioCampaignManifest) throws {
        let stmt = try db.prepare("""
            INSERT INTO campaigns (
                campaign_id, universe_id, sampler_id, sampler_kind, arm, precision_class,
                lenia_kernel_version, base_config_path, search_config_path, es_config_path, artifact_root,
                config_hash, manifest_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(campaign_id) DO UPDATE SET
                universe_id = excluded.universe_id,
                sampler_id = excluded.sampler_id,
                sampler_kind = excluded.sampler_kind,
                arm = excluded.arm,
                precision_class = excluded.precision_class,
                lenia_kernel_version = excluded.lenia_kernel_version,
                base_config_path = excluded.base_config_path,
                search_config_path = excluded.search_config_path,
                es_config_path = excluded.es_config_path,
                manifest_json = excluded.manifest_json,
                artifact_root = excluded.artifact_root,
                config_hash = excluded.config_hash,
                created_at = excluded.created_at
        """)
        defer { sqlite3_finalize(stmt) }
        db.bindText(stmt, index: 1, value: manifest.campaignID)
        db.bindText(stmt, index: 2, value: manifest.universeID)
        db.bindText(stmt, index: 3, value: manifest.samplerID)
        db.bindText(stmt, index: 4, value: manifest.samplerKind)
        db.bindText(stmt, index: 5, value: manifest.arm.rawValue)
        db.bindText(stmt, index: 6, value: manifest.precisionClass)
        db.bindText(stmt, index: 7, value: manifest.leniaKernelVersion)
        db.bindText(stmt, index: 8, value: manifest.baseConfigPath)
        db.bindText(stmt, index: 9, value: manifest.searchConfigPath)
        db.bindText(stmt, index: 10, value: manifest.esConfigPath)
        db.bindText(stmt, index: 11, value: manifest.artifactRoot)
        db.bindText(stmt, index: 12, value: manifest.configHash)
        db.bindText(stmt, index: 13, value: String(data: try encoder.encode(manifest), encoding: .utf8))
        db.bindDouble(stmt, index: 14, value: manifest.createdAt.timeIntervalSince1970)
        try db.step(stmt)
    }

    private func replaceShards(_ manifest: PortfolioCampaignManifest, seedPatches: [PortfolioSeedPatchRecord]) throws {
        let deleteCandidates = try db.prepare("DELETE FROM candidates WHERE campaign_id = ?")
        defer { sqlite3_finalize(deleteCandidates) }
        db.bindText(deleteCandidates, index: 1, value: manifest.campaignID)
        try db.step(deleteCandidates)

        let delete = try db.prepare("DELETE FROM shards WHERE campaign_id = ?")
        defer { sqlite3_finalize(delete) }
        db.bindText(delete, index: 1, value: manifest.campaignID)
        try db.step(delete)

        let insert = try db.prepare("""
            INSERT INTO shards (campaign_id, shard_index, status, shard_json)
            VALUES (?, ?, 'pending', ?)
        """)
        defer { sqlite3_finalize(insert) }

        for shardIndex in 0..<manifest.shardCount {
            sqlite3_reset(insert)
            sqlite3_clear_bindings(insert)
            let seeds = (0..<manifest.shardSize).map { localIndex in
                portfolioSeed(
                    universeID: manifest.universeID,
                    campaignID: manifest.campaignID,
                    samplerID: manifest.samplerID,
                    shardIndex: shardIndex,
                    localIndex: localIndex
                )
            }
            let selectedSeedPatch = seedPatches.isEmpty ? nil : seedPatches[shardIndex % seedPatches.count]
            let spec = PortfolioShardSpec(
                seeds: seeds,
                seedPatchIndex: selectedSeedPatch?.index,
                seedPatchHash: selectedSeedPatch?.contentHash
            )
            db.bindText(insert, index: 1, value: manifest.campaignID)
            db.bindInt(insert, index: 2, value: shardIndex)
            db.bindText(insert, index: 3, value: String(data: try portfolioJSONEncoder().encode(spec), encoding: .utf8))
            try db.step(insert)
        }
    }

    private func writeSeedPatchCatalog(_ records: [PortfolioSeedPatchRecord]) throws {
        let url = root.appendingPathComponent("seed-patches.jsonl")
        if records.isEmpty {
            try? FileManager.default.removeItem(at: url)
            return
        }
        let payload = try records
            .map { String(decoding: try portfolioJSONEncoder().encode($0), as: UTF8.self) }
            .joined(separator: "\n")
        try Data((payload + "\n").utf8).write(to: url, options: .atomic)
    }

    private func loadSeedPatchCatalog() throws -> [PortfolioSeedPatchRecord] {
        let url = root.appendingPathComponent("seed-patches.jsonl")
        guard FileManager.default.fileExists(atPath: url.path) else { return [] }
        let text = try String(contentsOf: url, encoding: .utf8)
        return try text
            .split(separator: "\n")
            .filter { !String($0).trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
            .map { line in
                try decoder.decode(PortfolioSeedPatchRecord.self, from: Data(String(line).utf8))
            }
    }

    private func loadSeedPatch(index: Int?, expectedHash: String?) throws -> ResearchSeedPatch? {
        guard let index else { return nil }
        guard let record = try loadSeedPatchCatalog().first(where: { $0.index == index }) else {
            throw ValidationError("Portfolio shard references missing seed patch index \(index).")
        }
        if let expectedHash, expectedHash != record.contentHash {
            throw ValidationError("Portfolio seed patch \(index) hash mismatch.")
        }
        return record.patch
    }

    private func decodeShardSpec(from data: Data) throws -> PortfolioShardSpec {
        if let spec = try? decoder.decode(PortfolioShardSpec.self, from: data) {
            return spec
        }
        return PortfolioShardSpec(seeds: try decoder.decode([Int].self, from: data))
    }

    private func loadCampaignManifest(campaignID: String) throws -> PortfolioCampaignManifest {
        let stmt = try db.prepare("SELECT manifest_json FROM campaigns WHERE campaign_id = ?")
        defer { sqlite3_finalize(stmt) }
        db.bindText(stmt, index: 1, value: campaignID)
        guard sqlite3_step(stmt) == SQLITE_ROW,
              let manifestJSON = columnText(stmt, index: 0),
              let data = manifestJSON.data(using: .utf8)
        else {
            throw ValidationError("Missing portfolio campaign \(campaignID).")
        }
        return try decoder.decode(PortfolioCampaignManifest.self, from: data)
    }
}

private enum PortfolioSeedPatchCatalog {
    static func load(
        libraryPath: String?,
        qdConfigDirectory: String?,
        cells: [Int],
        selection: ResearchSeedSelection?
    ) throws -> [PortfolioSeedPatchRecord] {
        guard let libraryPath else {
            guard cells.isEmpty else {
                throw ValidationError("--seed-cell requires --seed-library.")
            }
            guard qdConfigDirectory == nil else {
                throw ValidationError("--seed-qd-config-dir requires --seed-library.")
            }
            guard selection == nil else {
                throw ValidationError("Research seed selectors require --seed-library.")
            }
            return []
        }
        let patches = try loadResearchSeedPatches(
            libraryURL: URL(fileURLWithPath: libraryPath),
            qdConfigDirectoryOverride: qdConfigDirectory.map { URL(fileURLWithPath: $0, isDirectory: true) },
            cells: cells.isEmpty ? nil : cells,
            selection: selection
        )
        guard !patches.isEmpty else {
            throw ValidationError("No research seeds resolved from \(libraryPath).")
        }
        return try patches.enumerated().map { index, patch in
            let data = try portfolioJSONEncoder().encode(patch)
            return PortfolioSeedPatchRecord(
                index: index,
                contentHash: portfolioHash(data),
                patch: patch
            )
        }
    }
}

private enum PortfolioShardEvaluator {
    static func evaluate(lease: PortfolioShardLease, workerID: String) throws -> [PortfolioCandidateBundleRecord] {
        switch lease.arm {
        case .openES:
            return try evaluateOpenES(lease: lease, workerID: workerID)
        case .priorSearch:
            return try evaluatePriorSearch(lease: lease, workerID: workerID)
        }
    }

    private static func evaluatePriorSearch(lease: PortfolioShardLease, workerID: String) throws -> [PortfolioCandidateBundleRecord] {
        guard let parsedSearchConfig = lease.searchConfig else {
            throw ValidationError("prior_search portfolio lease is missing search_config.")
        }
        var overrides = parsedSearchConfig.overridesAsDict()
        overrides["params.seed"] = lease.seeds[0]
        overrides["run.steps"] = parsedSearchConfig.steps
        let effectiveBaseConfig = try portfolioBaseConfig(for: lease)
        let baseData = try portfolioJSONEncoder().encode(effectiveBaseConfig)
        let runtimeConfig = try loadRuntimeConfig(from: baseData, overrides: overrides)
        let engine = SearchEngine(runtimeConfig: runtimeConfig)
        let searchConfig = parsedSearchConfig.toSearchConfig(captureTerminalPatches: true)
        let batchResults = engine.runBatch(
            seeds: lease.seeds,
            initSeedOffset: parsedSearchConfig.initSeedOffset ?? 0,
            searchConfig: searchConfig
        )
        var bundles: [PortfolioCandidateBundleRecord] = []
        bundles.reserveCapacity(batchResults.count)
        for (localIndex, result) in batchResults.enumerated() {
            let resultData = materializeSearchResultData(
                result,
                backend: runtimeConfig.backend.rawValue,
                implementation: runtimeConfig.implementation,
                searchConfig: searchConfig,
                sweep: [
                    "portfolio_shard_index": Double(lease.shardIndex),
                    "portfolio_local_index": Double(localIndex),
                ],
                workerId: workerID
            )
            guard resultData.filtersPassed else { continue }
            bundles.append(try writeCandidateBundle(
                lease: lease,
                localIndex: localIndex,
                result: resultData,
                terminalStatePatch: result.terminalStatePatch,
                terminalParamPatch: result.terminalParamPatch,
                workerID: workerID
            ))
        }
        return bundles
    }

    private static func evaluateOpenES(lease: PortfolioShardLease, workerID: String) throws -> [PortfolioCandidateBundleRecord] {
        guard let baseESConfig = lease.esConfig else { return [] }
        let esOutputURL = URL(fileURLWithPath: lease.artifactRoot, isDirectory: true)
            .appendingPathComponent("es-shards", isDirectory: true)
            .appendingPathComponent("\(lease.campaignID)-\(lease.shardIndex)", isDirectory: true)
        let esConfig = try portfolioESConfig(
            base: baseESConfig,
            runtimeConfig: lease.baseConfig,
            seedPatch: lease.seedPatch,
            seedKernelParams: lease.seedKernelParams,
            seed: lease.seeds[0],
            outputDir: esOutputURL.path
        )
        try FileManager.default.createDirectory(at: esOutputURL, withIntermediateDirectories: true)
        let runtimeConfig = try loadRuntimeConfig(from: portfolioJSONEncoder().encode(lease.baseConfig))
        let ranges: [String: (Float, Float)]
        if let paramRanges = esConfig.paramRanges {
            ranges = paramRanges.mapValues { ($0[0], $0[1]) }
        } else {
            ranges = try extractRangesFromConfig(lease.baseConfig)
        }
        let engine = EvolutionEngine(runtimeConfig: runtimeConfig, esConfig: esConfig, ranges: ranges)
        var bestFitness: Float = -.infinity
        var bestCandidate: [Float]?
        for generation in 0..<esConfig.generations {
            let result = engine.runGeneration(gen: generation)
            if result.bestFitness > bestFitness {
                bestFitness = result.bestFitness
                bestCandidate = result.bestCandidate
            }
        }
        guard let bestCandidate else { return [] }
        let evaluation = engine.evaluateCandidateForResearchExport(bestCandidate, evaluationIndex: lease.seeds[0])
        guard evaluation.resultData.filtersPassed else { return [] }
        return [
            try writeCandidateBundle(
                lease: lease,
                localIndex: 0,
                result: evaluation.resultData,
                terminalStatePatch: nil,
                terminalParamPatch: nil,
                workerID: workerID
            )
        ]
    }

    private static func portfolioBaseConfig(for lease: PortfolioShardLease) throws -> LeniaBaseConfig {
        guard let seedPatch = lease.seedPatch else {
            return lease.baseConfig
        }
        let statePatch = try portfolioStatePatch(from: seedPatch, for: lease.baseConfig)
        let initConfig = InitConfig(
            seed: lease.baseConfig.`init`.seed,
            patches: lease.baseConfig.parameter_embedding.enabled ? lease.baseConfig.`init`.patches : [],
            a_uniform: UniformRange(low: 0, high: 0),
            p_uniform: lease.baseConfig.`init`.p_uniform,
            state_patch: statePatch,
            p_state_patch: lease.baseConfig.`init`.p_state_patch
        )
        let params = try portfolioParamsConfig(base: lease.baseConfig.params, seedPatch: seedPatch, enabled: lease.seedKernelParams)
        return LeniaBaseConfig(
            backend: lease.baseConfig.backend,
            profile: lease.baseConfig.profile,
            grid: lease.baseConfig.grid,
            channels: lease.baseConfig.channels,
            connectivity: lease.baseConfig.connectivity,
            flow: lease.baseConfig.flow,
            implementation: lease.baseConfig.implementation,
            reintegration: lease.baseConfig.reintegration,
            parameter_embedding: lease.baseConfig.parameter_embedding,
            chemotaxis: lease.baseConfig.chemotaxis,
            obstacle_field: lease.baseConfig.obstacle_field,
            food: lease.baseConfig.food,
            walls: lease.baseConfig.walls,
            environment: lease.baseConfig.environment,
            beam_mutation: lease.baseConfig.beam_mutation,
            params: params,
            init: initConfig,
            run: lease.baseConfig.run,
            interventions: lease.baseConfig.interventions
        )
    }

    private static func writeCandidateBundle(
        lease: PortfolioShardLease,
        localIndex: Int,
        result: SimulationResultData,
        terminalStatePatch: InitStatePatchConfig?,
        terminalParamPatch: InitStatePatchConfig?,
        workerID: String
    ) throws -> PortfolioCandidateBundleRecord {
        let universe = PortfolioUniverseBundle(
            schemaVersion: portfolioSchemaVersion,
            universeID: lease.universeID,
            precisionClass: lease.precisionClass,
            leniaKernelVersion: lease.leniaKernelVersion,
            topologyHash: configTopologyHash(lease.baseConfig),
            baseConfig: lease.baseConfig
        )
        let sampler = PortfolioSamplerBundle(
            schemaVersion: portfolioSchemaVersion,
            samplerID: lease.samplerID,
            samplerKind: lease.samplerKind,
            seedDerivation: "sha256(universe_id,campaign_id,sampler_id,shard_index,local_index) low63",
            seedPatchIndex: lease.seedPatchIndex,
            seedPatchHash: lease.seedPatchHash,
            seedPatchSourceID: lease.seedPatch?.sourceID,
            seedPatchName: lease.seedPatch?.name,
            seedKernelParams: lease.seedKernelParams,
            searchConfig: lease.searchConfig,
            esConfig: lease.esConfig
        )
        let candidate = PortfolioCandidateCore(
            schemaVersion: portfolioSchemaVersion,
            campaignID: lease.campaignID,
            universeID: lease.universeID,
            samplerID: lease.samplerID,
            shardIndex: lease.shardIndex,
            localIndex: localIndex,
            seed: result.seed,
            initSeed: result.initSeed,
            backend: result.backend,
            implementation: result.implementation,
            score: result.score,
            scoreWeights: result.scoreWeights,
            filtersPassed: result.filtersPassed,
            filters: result.filters,
            params: result.params,
            descriptorBundle: result.descriptorBundle
        )
        let encoder = portfolioJSONEncoder(prettyPrinted: true)
        var files = [
            "universe.json": try encoder.encode(universe),
            "sampler.json": try encoder.encode(sampler),
            "candidate.json": try encoder.encode(candidate),
            "metrics.json": try encoder.encode(result.metrics),
        ]
        if let terminalStatePatch {
            files["terminal_state_patch.json"] = try encoder.encode(terminalStatePatch)
        }
        if let seedPatch = lease.seedPatch {
            files["seed_patch.json"] = try encoder.encode(seedPatch)
        }
        var bundleFiles = files
        if let terminalParamPatch {
            bundleFiles["terminal_param_patch.json"] = try encoder.encode(terminalParamPatch)
        }
        let hashInputs = [
            "universe.json",
            "sampler.json",
            "candidate.json",
            "metrics.json",
        ] + (terminalStatePatch == nil ? [] : ["terminal_state_patch.json"])
            + (lease.seedPatch == nil ? [] : ["seed_patch.json"])
            + (terminalParamPatch == nil ? [] : ["terminal_param_patch.json"])
        let contentHash = portfolioContentHash(files: bundleFiles, orderedNames: hashInputs)
        let bundleDir = URL(fileURLWithPath: lease.artifactRoot, isDirectory: true)
            .appendingPathComponent("candidates", isDirectory: true)
            .appendingPathComponent(String(contentHash.prefix(2)), isDirectory: true)
            .appendingPathComponent(contentHash, isDirectory: true)
        try FileManager.default.createDirectory(at: bundleDir, withIntermediateDirectories: true)
        for (name, data) in bundleFiles {
            try data.write(to: bundleDir.appendingPathComponent(name), options: .atomic)
        }
        var manifestFiles = Array(bundleFiles.keys).sorted()
        if let activity = result.activity, !activity.isEmpty {
            try writeResearchJSONLines(activity, to: bundleDir.appendingPathComponent("activity.jsonl"))
            manifestFiles.append("activity.jsonl")
        }
        let manifest = PortfolioBundleManifest(
            schemaVersion: portfolioSchemaVersion,
            bundleKind: "portfolio_candidate_bundle_v1",
            contentHash: contentHash,
            contentHashInputs: hashInputs,
            campaignID: lease.campaignID,
            universeID: lease.universeID,
            samplerID: lease.samplerID,
            shardIndex: lease.shardIndex,
            localIndex: localIndex,
            workerID: workerID,
            createdAt: Date(),
            files: manifestFiles + ["manifest.json"]
        )
        try encoder.encode(manifest).write(to: bundleDir.appendingPathComponent("manifest.json"), options: .atomic)
        return PortfolioCandidateBundleRecord(
            contentHash: contentHash,
            bundlePath: bundleDir.path,
            campaignID: lease.campaignID,
            universeID: lease.universeID,
            samplerID: lease.samplerID,
            shardIndex: lease.shardIndex,
            localIndex: localIndex,
            seed: result.seed,
            initSeed: result.initSeed,
            score: result.score,
            filtersPassed: result.filtersPassed,
            genotypeHash: result.descriptorBundle?.genotype.hash12,
            fingerprintHash: result.descriptorBundle?.terminal.fingerprintHash12
        )
    }
}

private func portfolioSeed(
    universeID: String,
    campaignID: String,
    samplerID: String,
    shardIndex: Int,
    localIndex: Int
) -> Int {
    let key = "\(universeID)\u{0}\(campaignID)\u{0}\(samplerID)\u{0}\(shardIndex)\u{0}\(localIndex)"
    let digest = SHA256.hash(data: Data(key.utf8))
    var value: UInt64 = 0
    for byte in digest.prefix(8) {
        value = (value << 8) | UInt64(byte)
    }
    return Int(value & 0x7FFF_FFFF_FFFF_FFFF)
}

private func portfolioContentHash(files: [String: Data], orderedNames: [String]) -> String {
    var data = Data()
    for name in orderedNames {
        guard let payload = files[name] else {
            preconditionFailure("Missing portfolio content hash input \(name).")
        }
        data.append(Data(name.utf8))
        data.append(0)
        data.append(payload)
        data.append(0)
    }
    return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

private func portfolioHash(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

func portfolioStatePatch(from patch: ResearchSeedPatch, for baseConfig: LeniaBaseConfig) throws -> InitStatePatchConfig {
    guard patch.world.width <= baseConfig.grid.sx, patch.world.height <= baseConfig.grid.sy else {
        throw ValidationError(
            "Research seed patch '\(patch.name)' \(patch.world.width)x\(patch.world.height) exceeds portfolio grid \(baseConfig.grid.sx)x\(baseConfig.grid.sy)."
        )
    }
    var values: [Float] = []
    values.reserveCapacity(patch.world.width * patch.world.height * baseConfig.channels)
    for x in 0..<patch.world.width {
        for y in 0..<patch.world.height {
            let sourceBase = ((x * patch.world.height) + y) * patch.world.channels
            for channel in 0..<baseConfig.channels {
                values.append(channel < patch.world.channels ? patch.world.values[sourceBase + channel] : 0)
            }
        }
    }
    return InitStatePatchConfig(
        center: [baseConfig.grid.sx / 2, baseConfig.grid.sy / 2],
        width: patch.world.width,
        height: patch.world.height,
        channels: baseConfig.channels,
        values: values
    )
}

private func portfolioParamsConfig(base: ParamsConfig, seedPatch: ResearchSeedPatch, enabled: Bool) throws -> ParamsConfig {
    guard enabled else { return base }
    guard let params = seedPatch.kernelParams else {
        throw ValidationError("--seed-kernel-params requested, but seed '\(seedPatch.name)' has no kernel parameters.")
    }
    return ParamsConfig(
        mode: "explicit",
        seed: nil,
        ranges: nil,
        r: params.r,
        b: params.b,
        w: params.w,
        a: params.a,
        m: params.m,
        s: params.s,
        h: params.h,
        R: params.R
    )
}

private func portfolioESConfig(
    base: ESConfig,
    runtimeConfig: LeniaBaseConfig,
    seedPatch: ResearchSeedPatch?,
    seedKernelParams: Bool,
    seed: Int,
    outputDir: String
) throws -> ESConfig {
    var initialInitPatchValues = base.initialInitPatchValues
    var initialKernelParams = base.initialKernelParams
    if let seedPatch {
        guard let initPatch = base.initPatch, initPatch.enabled else {
            throw ValidationError("OpenES seed-library warm starts require init_patch.enabled in the ES config.")
        }
        initialInitPatchValues = try researchSeedCenterCropPatchValues(
            patch: seedPatch,
            size: initPatch.size,
            outputChannels: portfolioESCreatureChannelCount(baseConfig: runtimeConfig, obstacleField: base.obstacleField)
        )
        if seedKernelParams {
            guard let kernelParams = seedPatch.kernelParams else {
                throw ValidationError("--seed-kernel-params requested, but seed '\(seedPatch.name)' has no kernel parameters.")
            }
            initialKernelParams = kernelParams
        }
    }
    return ESConfig(
        outputDir: outputDir,
        generations: base.generations,
        population: base.population,
        sigma: base.sigma,
        learningRate: base.learningRate,
        seed: seed,
        steps: base.steps,
        fitness: base.fitness,
        fitnessShaping: base.fitnessShaping,
        initPatch: base.initPatch,
        initialInitPatchValues: initialInitPatchValues,
        initialKernelParams: initialKernelParams,
        paramRanges: base.paramRanges,
        obstacleField: base.obstacleField
    )
}

private func portfolioESCreatureChannelCount(baseConfig: LeniaBaseConfig, obstacleField: ESObstacleFieldConfig?) -> Int {
    flowCreatureChannels(
        channels: baseConfig.channels,
        chemotaxis: baseConfig.chemotaxis,
        food: baseConfig.food,
        additionalExcludedChannels: obstacleField.map { $0.enabled ? [$0.channelIndex] : [] } ?? []
    ).count
}

private func portfolioJSONEncoder(prettyPrinted: Bool = false) -> JSONEncoder {
    let encoder = JSONEncoder()
    var formatting: JSONEncoder.OutputFormatting = [.sortedKeys]
    if prettyPrinted {
        formatting.insert(.prettyPrinted)
    }
    encoder.outputFormatting = formatting
    encoder.dateEncodingStrategy = .deferredToDate
    return encoder
}

private func writeJSON<T: Encodable>(_ value: T, to url: URL, encoder: JSONEncoder) throws {
    try encoder.encode(value).write(to: url, options: .atomic)
}

private func printJSON<T: Encodable>(_ value: T) throws {
    let data = try portfolioJSONEncoder(prettyPrinted: true).encode(value)
    print(String(decoding: data, as: UTF8.self))
}

private func columnText(_ stmt: OpaquePointer, index: Int32) -> String? {
    guard let text = sqlite3_column_text(stmt, index) else { return nil }
    return String(cString: text)
}
