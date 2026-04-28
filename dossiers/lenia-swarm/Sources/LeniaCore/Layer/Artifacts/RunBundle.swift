import Foundation

public struct LeniaRunBundle: Sendable {
    public let bundleKind: LeniaArtifactBundleKind
    public let bundleDirectory: URL
    public let baseConfigURL: URL?
    public let searchConfigURL: URL?
    public let payloadURL: URL?
    public let metadataURL: URL?
    public let trajectoryFramesURL: URL?

    public init(
        bundleKind: LeniaArtifactBundleKind,
        bundleDirectory: URL,
        baseConfigURL: URL?,
        searchConfigURL: URL?,
        payloadURL: URL?,
        metadataURL: URL?,
        trajectoryFramesURL: URL?
    ) {
        self.bundleKind = bundleKind
        self.bundleDirectory = bundleDirectory
        self.baseConfigURL = baseConfigURL
        self.searchConfigURL = searchConfigURL
        self.payloadURL = payloadURL
        self.metadataURL = metadataURL
        self.trajectoryFramesURL = trajectoryFramesURL
    }

    public func requireBaseConfig() throws -> URL {
        try require(baseConfigURL, role: "base config")
    }

    public func requirePayload() throws -> URL {
        try require(payloadURL, role: "payload")
    }

    private func require(_ url: URL?, role: String) throws -> URL {
        guard let url else {
            throw ConfigError.invalidConfig("Run bundle \(bundleDirectory.path) does not declare a \(role) artifact.")
        }
        guard FileManager.default.fileExists(atPath: url.path) else {
            throw ConfigError.invalidConfig("Run bundle \(bundleDirectory.path) declares missing \(role) artifact: \(url.path).")
        }
        return url
    }
}

public func loadLeniaRunBundle(from directory: URL) throws -> LeniaRunBundle? {
    var isDirectory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: directory.path, isDirectory: &isDirectory),
          isDirectory.boolValue else {
        return nil
    }
    let metadataURL = directory.appendingPathComponent("meta.json")
    guard FileManager.default.fileExists(atPath: metadataURL.path) else {
        return nil
    }
    let metadata = try decodeLeniaRunBundleMetadata(from: metadataURL)
    return LeniaRunBundle(
        bundleKind: metadata.bundleKind,
        bundleDirectory: directory,
        baseConfigURL: existingBundleArtifact(directory.appendingPathComponent("base.json")),
        searchConfigURL: existingBundleArtifact(directory.appendingPathComponent("search.json")),
        payloadURL: existingBundleArtifact(directory.appendingPathComponent("payload.json")),
        metadataURL: metadataURL,
        trajectoryFramesURL: existingTrajectoryFramesURL(in: directory)
    )
}

public func loadLeniaRunBundles(from indexURL: URL) throws -> [LeniaRunBundle] {
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .deferredToDate
    let lines = try String(contentsOf: indexURL, encoding: .utf8)
        .split(separator: "\n")
        .map(String.init)
    return try lines.map { line in
        let record = try decoder.decode(LeniaRunBundleIndexRecord.self, from: Data(line.utf8))
        return LeniaRunBundle(
            bundleKind: record.bundleKind,
            bundleDirectory: record.bundleDirectory,
            baseConfigURL: record.baseConfigURL,
            searchConfigURL: record.searchConfigURL,
            payloadURL: record.payloadURL,
            metadataURL: record.metadataURL,
            trajectoryFramesURL: record.trajectoryFramesURL
        )
    }
}

public func discoverLeniaRunBundles(from inputURL: URL) throws -> [LeniaRunBundle] {
    var isDirectory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: inputURL.path, isDirectory: &isDirectory) else {
        return []
    }

    if !isDirectory.boolValue {
        guard inputURL.lastPathComponent == "index.jsonl" else {
            return []
        }
        return try loadLeniaRunBundles(from: inputURL)
    }

    let indexURL = inputURL.appendingPathComponent("index.jsonl")
    if FileManager.default.fileExists(atPath: indexURL.path) {
        return try loadLeniaRunBundles(from: indexURL)
    }

    let ecologyRunsIndexURL = inputURL.appendingPathComponent("ecology-runs/index.jsonl")
    if FileManager.default.fileExists(atPath: ecologyRunsIndexURL.path) {
        return try loadLeniaRunBundles(from: ecologyRunsIndexURL)
    }

    if let bundle = try loadLeniaRunBundle(from: inputURL) {
        return [bundle]
    }

    let children = try FileManager.default.contentsOfDirectory(
        at: inputURL,
        includingPropertiesForKeys: [.isDirectoryKey],
        options: [.skipsHiddenFiles]
    )
    var bundles: [LeniaRunBundle] = []
    for child in children.sorted(by: { $0.lastPathComponent < $1.lastPathComponent }) {
        if let bundle = try loadLeniaRunBundle(from: child) {
            bundles.append(bundle)
        }
    }
    return bundles
}

private struct LeniaRunBundleMetadata: Decodable {
    let bundleKind: LeniaArtifactBundleKind

    enum CodingKeys: String, CodingKey {
        case bundleKind
        case snakeBundleKind = "bundle_kind"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        if let bundleKind = try container.decodeIfPresent(LeniaArtifactBundleKind.self, forKey: .bundleKind) {
            self.bundleKind = bundleKind
            return
        }
        if let bundleKind = try container.decodeIfPresent(LeniaArtifactBundleKind.self, forKey: .snakeBundleKind) {
            self.bundleKind = bundleKind
            return
        }
        throw DecodingError.keyNotFound(
            CodingKeys.bundleKind,
            DecodingError.Context(codingPath: decoder.codingPath, debugDescription: "Run bundle metadata must declare bundleKind or bundle_kind.")
        )
    }
}

private struct LeniaRunBundleIndexRecord: Decodable {
    let bundleKind: LeniaArtifactBundleKind
    let bundleDirectory: URL
    let baseConfigURL: URL?
    let searchConfigURL: URL?
    let payloadURL: URL?
    let metadataURL: URL?
    let trajectoryFramesURL: URL?

    enum CodingKeys: String, CodingKey {
        case bundleKind
        case snakeBundleKind = "bundle_kind"
        case exportDir
        case bundleDir = "bundle_dir"
        case baseConfigPath
        case baseConfigSnakePath = "base_config_path"
        case searchConfigPath
        case searchConfigSnakePath = "search_config_path"
        case payloadPath
        case payloadSnakePath = "payload_path"
        case metadataPath
        case metadataSnakePath = "metadata_path"
        case trajectoryFramesPath
        case trajectoryFramesSnakePath = "trajectory_frames_path"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        if let bundleKind = try container.decodeIfPresent(LeniaArtifactBundleKind.self, forKey: .bundleKind) {
            self.bundleKind = bundleKind
        } else if let bundleKind = try container.decodeIfPresent(LeniaArtifactBundleKind.self, forKey: .snakeBundleKind) {
            self.bundleKind = bundleKind
        } else {
            throw DecodingError.keyNotFound(
                CodingKeys.bundleKind,
                DecodingError.Context(codingPath: decoder.codingPath, debugDescription: "Run bundle index record must declare bundleKind or bundle_kind.")
            )
        }

        let directoryPath = try decodeFirstString(container, keys: [.exportDir, .bundleDir], role: "bundle directory")
        bundleDirectory = URL(fileURLWithPath: directoryPath, isDirectory: true)
        baseConfigURL = decodeFirstOptionalURL(container, keys: [.baseConfigPath, .baseConfigSnakePath])
        searchConfigURL = decodeFirstOptionalURL(container, keys: [.searchConfigPath, .searchConfigSnakePath])
        payloadURL = decodeFirstOptionalURL(container, keys: [.payloadPath, .payloadSnakePath])
        metadataURL = decodeFirstOptionalURL(container, keys: [.metadataPath, .metadataSnakePath])
        trajectoryFramesURL = decodeFirstOptionalURL(container, keys: [.trajectoryFramesPath, .trajectoryFramesSnakePath])
    }
}

private func decodeLeniaRunBundleMetadata(from url: URL) throws -> LeniaRunBundleMetadata {
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .deferredToDate
    return try decoder.decode(LeniaRunBundleMetadata.self, from: Data(contentsOf: url))
}

private func decodeFirstString<K: CodingKey>(
    _ container: KeyedDecodingContainer<K>,
    keys: [K],
    role: String
) throws -> String {
    for key in keys {
        if let value = try container.decodeIfPresent(String.self, forKey: key) {
            return value
        }
    }
    throw DecodingError.keyNotFound(
        keys[0],
        DecodingError.Context(codingPath: container.codingPath, debugDescription: "Run bundle index record must declare \(role).")
    )
}

private func decodeFirstOptionalURL<K: CodingKey>(
    _ container: KeyedDecodingContainer<K>,
    keys: [K]
) -> URL? {
    for key in keys {
        guard let value = try? container.decodeIfPresent(String.self, forKey: key) else {
            continue
        }
        return URL(fileURLWithPath: value)
    }
    return nil
}

private func existingBundleArtifact(_ url: URL) -> URL? {
    FileManager.default.fileExists(atPath: url.path) ? url : nil
}

private func existingTrajectoryFramesURL(in directory: URL) -> URL? {
    let directoryURL = directory.appendingPathComponent("trajectory-frames", isDirectory: true)
    if FileManager.default.fileExists(atPath: directoryURL.path) {
        return directoryURL
    }
    let legacyJSONLURL = directory.appendingPathComponent("trajectory-frames.jsonl")
    return FileManager.default.fileExists(atPath: legacyJSONLURL.path) ? legacyJSONLURL : nil
}
