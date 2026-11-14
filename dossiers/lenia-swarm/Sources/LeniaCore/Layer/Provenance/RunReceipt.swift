import Foundation

/// Immutable start record of a research run. Its file sha256 is the run's `receipt_sha256`, so it is
/// never rewritten; outputs are recorded at the end in `receipt.completion.json`.
public struct RunReceipt: Codable, Sendable {
    public static let fileName = "receipt.json"
    public static let completionFileName = "receipt.completion.json"
    public static let currentVersion = 1

    public let receiptVersion: Int
    public let argv: [String]
    public let startedAt: String
    public let build: LeniaBuildInfo
    public let binarySha256: String
    public let engineID: String
    public let engine: LeniaEngineIdentity
    public let host: LeniaHostIdentity
    public let config: AnyCodable
    public let configSha256: String
    public let seeds: [Int]
    public let inputs: [String: String]
    public let sourcePatch: String?

    enum CodingKeys: String, CodingKey {
        case receiptVersion = "receipt_version"
        case argv
        case startedAt = "started_at"
        case build
        case binarySha256 = "binary_sha256"
        case engineID = "engine_id"
        case engine
        case host
        case config
        case configSha256 = "config_sha256"
        case seeds
        case inputs
        case sourcePatch = "source_patch"
    }

    init(
        argv: [String],
        startedAt: String,
        build: LeniaBuildInfo,
        engine: LeniaEngineIdentity,
        host: LeniaHostIdentity,
        config: AnyCodable,
        configSha256: String,
        seeds: [Int],
        inputs: [String: String],
        sourcePatch: String?
    ) {
        self.receiptVersion = Self.currentVersion
        self.argv = argv
        self.startedAt = startedAt
        self.build = build
        self.binarySha256 = build.binarySha256
        self.engineID = engine.engineID
        self.engine = engine
        self.host = host
        self.config = config
        self.configSha256 = configSha256
        self.seeds = seeds
        self.inputs = inputs
        self.sourcePatch = sourcePatch
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        receiptVersion = try container.decode(Int.self, forKey: .receiptVersion)
        guard receiptVersion == Self.currentVersion else {
            throw ProvenanceError.invalidReceipt("receipt_version \(receiptVersion) is not \(Self.currentVersion)")
        }
        argv = try container.decode([String].self, forKey: .argv)
        startedAt = try container.decode(String.self, forKey: .startedAt)
        build = try container.decode(LeniaBuildInfo.self, forKey: .build)
        binarySha256 = try container.decode(String.self, forKey: .binarySha256)
        engineID = try container.decode(String.self, forKey: .engineID)
        engine = try container.decode(LeniaEngineIdentity.self, forKey: .engine)
        host = try container.decode(LeniaHostIdentity.self, forKey: .host)
        config = try container.decode(AnyCodable.self, forKey: .config)
        configSha256 = try container.decode(String.self, forKey: .configSha256)
        seeds = try container.decode([Int].self, forKey: .seeds)
        inputs = try container.decode([String: String].self, forKey: .inputs)
        sourcePatch = try container.decodeNullable(String.self, forKey: .sourcePatch)
        guard engine.engineID == engineID else {
            throw ProvenanceError.invalidReceipt("engine_id \(engineID) disagrees with engine.engine_id \(engine.engineID)")
        }
        guard build.binarySha256 == binarySha256 else {
            throw ProvenanceError.invalidReceipt("binary_sha256 disagrees with build.binary_sha256")
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(receiptVersion, forKey: .receiptVersion)
        try container.encode(argv, forKey: .argv)
        try container.encode(startedAt, forKey: .startedAt)
        try container.encode(build, forKey: .build)
        try container.encode(binarySha256, forKey: .binarySha256)
        try container.encode(engineID, forKey: .engineID)
        try container.encode(engine, forKey: .engine)
        try container.encode(host, forKey: .host)
        try container.encode(config, forKey: .config)
        try container.encode(configSha256, forKey: .configSha256)
        try container.encode(seeds, forKey: .seeds)
        try container.encode(inputs, forKey: .inputs)
        try container.encode(sourcePatch, forKey: .sourcePatch)
    }
}

public struct RunReceiptCompletion: Codable, Sendable {
    public let receiptSha256: String
    public let finishedAt: String
    public let outputs: [String: String]
    public let compiledMetalSourceSha256s: [String]

    enum CodingKeys: String, CodingKey {
        case receiptSha256 = "receipt_sha256"
        case finishedAt = "finished_at"
        case outputs
        case compiledMetalSourceSha256s = "compiled_metal_source_sha256s"
    }
}

/// The provenance a record carries into summaries, the compendium and the warehouse.
public struct RunProvenance: Codable, Sendable, Equatable {
    public let engineID: String
    public let sourceCommit: String
    public let receiptSha256: String

    enum CodingKeys: String, CodingKey {
        case engineID = "engine_id"
        case sourceCommit = "source_commit"
        case receiptSha256 = "receipt_sha256"
    }

    public init(engineID: String, sourceCommit: String, receiptSha256: String) {
        self.engineID = engineID
        self.sourceCommit = sourceCommit
        self.receiptSha256 = receiptSha256
    }
}

public struct RunReceiptSession: Sendable {
    public let directory: URL
    public let receipt: RunReceipt
    public let receiptSha256: String

    public var provenance: RunProvenance {
        RunProvenance(engineID: receipt.engineID, sourceCommit: receipt.build.sourceCommit, receiptSha256: receiptSha256)
    }

    static func encoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        return encoder
    }

    /// Writes `receipt.json` before any record exists. Refuses a directory that already holds one.
    public static func begin<Config: Encodable>(
        directory: URL,
        executableURL: URL,
        argv: [String],
        backend: FlowLeniaComputeBackend,
        config: Config,
        seeds: [Int],
        inputs: [URL]
    ) throws -> RunReceiptSession {
        let receiptURL = directory.appendingPathComponent(RunReceipt.fileName)
        guard !FileManager.default.fileExists(atPath: receiptURL.path) else {
            throw ProvenanceError.receiptExists(receiptURL.path)
        }
        let build = try LeniaBuildInfo.loadVerified(executableURL: executableURL)
        let configEncoder = JSONEncoder()
        configEncoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        let configData = try configEncoder.encode(config)
        var inputDigests: [String: String] = [:]
        for input in inputs {
            let path = input.standardizedFileURL.path
            guard FileManager.default.fileExists(atPath: path) else {
                throw ProvenanceError.invalidReceipt("input \(path) does not exist")
            }
            inputDigests[path] = try ProvenanceDigest.sha256Hex(fileAt: input)
        }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let sourcePatch: String?
        if build.dirty {
            let patchURL = LeniaBuildInfo.sourcePatchURL(executableURL: executableURL)
            let copyURL = directory.appendingPathComponent(patchURL.lastPathComponent)
            try FileManager.default.copyItem(at: patchURL, to: copyURL)
            sourcePatch = patchURL.lastPathComponent
        } else {
            sourcePatch = nil
        }
        let receipt = RunReceipt(
            argv: argv,
            startedAt: ISO8601DateFormatter().string(from: Date()),
            build: build,
            engine: LeniaEngineIdentity(backend: backend, buildInfo: build),
            host: try LeniaHostIdentity.current(backend: backend),
            config: try JSONDecoder().decode(AnyCodable.self, from: configData),
            configSha256: ProvenanceDigest.sha256Hex(configData),
            seeds: seeds,
            inputs: inputDigests,
            sourcePatch: sourcePatch
        )
        let data = try encoder().encode(receipt)
        try data.write(to: receiptURL, options: .withoutOverwriting)
        return RunReceiptSession(directory: directory, receipt: receipt, receiptSha256: ProvenanceDigest.sha256Hex(data))
    }

    /// Reopens a run directory for resume, refusing it unless this binary and engine wrote its receipt.
    public static func resume(
        directory: URL,
        executableURL: URL,
        backend: FlowLeniaComputeBackend
    ) throws -> RunReceiptSession {
        let session = try load(directory: directory)
        let build = try LeniaBuildInfo.loadVerified(executableURL: executableURL)
        guard session.receipt.binarySha256 == build.binarySha256 else {
            throw ProvenanceError.receiptMismatch(
                "\(directory.path) was started by binary \(session.receipt.binarySha256), not \(build.binarySha256); resume it with that binary or start a new run"
            )
        }
        let engineID = LeniaEngineIdentity(backend: backend, buildInfo: build).engineID
        guard session.receipt.engineID == engineID else {
            throw ProvenanceError.receiptMismatch(
                "\(directory.path) was started on engine \(session.receipt.engineID), not \(engineID); resume it with backend \(session.receipt.engine.backend.rawValue) or start a new run"
            )
        }
        return session
    }

    public static func load(directory: URL) throws -> RunReceiptSession {
        let receiptURL = directory.appendingPathComponent(RunReceipt.fileName)
        guard FileManager.default.fileExists(atPath: receiptURL.path) else {
            throw ProvenanceError.missingReceipt(receiptURL.path)
        }
        let data = try Data(contentsOf: receiptURL)
        let receipt = try JSONDecoder().decode(RunReceipt.self, from: data)
        return RunReceiptSession(directory: directory, receipt: receipt, receiptSha256: ProvenanceDigest.sha256Hex(data))
    }

    /// Hashes every file the run left in its directory except the receipt pair and logs.
    @discardableResult
    public func finish() throws -> RunReceiptCompletion {
        let completion = RunReceiptCompletion(
            receiptSha256: receiptSha256,
            finishedAt: ISO8601DateFormatter().string(from: Date()),
            outputs: try Self.outputDigests(in: directory),
            compiledMetalSourceSha256s: CompiledMetalSources.sha256s()
        )
        try Self.encoder().encode(completion)
            .write(to: directory.appendingPathComponent(RunReceipt.completionFileName), options: .atomic)
        return completion
    }

    static func outputDigests(in directory: URL) throws -> [String: String] {
        let excluded: Set<String> = [RunReceipt.fileName, RunReceipt.completionFileName]
        let root = directory.standardizedFileURL.resolvingSymlinksInPath()
        guard let enumerator = FileManager.default.enumerator(
            at: root,
            includingPropertiesForKeys: [.isRegularFileKey],
            options: []
        ) else {
            throw ProvenanceError.invalidReceipt("cannot enumerate \(root.path)")
        }
        var digests: [String: String] = [:]
        let prefix = root.path.hasSuffix("/") ? root.path : root.path + "/"
        for case let url as URL in enumerator {
            let path = url.standardizedFileURL.path
            guard path.hasPrefix(prefix) else {
                throw ProvenanceError.invalidReceipt("enumerated \(path) outside \(root.path)")
            }
            let relative = String(path.dropFirst(prefix.count))
            if relative == "logs" || relative.hasPrefix("logs/") {
                enumerator.skipDescendants()
                continue
            }
            guard try url.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile == true,
                  !excluded.contains(relative) else { continue }
            digests[relative] = try ProvenanceDigest.sha256Hex(fileAt: url)
        }
        return digests
    }
}
