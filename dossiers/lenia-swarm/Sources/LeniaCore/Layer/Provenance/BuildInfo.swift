import Crypto
import Foundation

public enum ProvenanceError: Error, LocalizedError, Equatable {
    case missingExecutableURL
    case missingBuildInfo(String)
    case binaryMismatch(path: String, expected: String, actual: String)
    case inconsistentBuildInfo(String)
    case missingSourcePatch(String)
    case sourcePatchMismatch(path: String, expected: String, actual: String)
    case receiptExists(String)
    case missingReceipt(String)
    case receiptMismatch(String)
    case invalidReceipt(String)

    public var errorDescription: String? {
        switch self {
        case .missingExecutableURL:
            return "Cannot locate the running executable, so its build info cannot be verified."
        case .missingBuildInfo(let path):
            return "Build info missing at \(path). Build with `make build` (or `make build-debug`), which writes it next to the binary."
        case .binaryMismatch(let path, let expected, let actual):
            return "Binary at \(path) does not match its build info (expected sha256 \(expected), found \(actual)). Rebuild with `make build` so the build info describes this binary."
        case .inconsistentBuildInfo(let detail):
            return "Build info is inconsistent: \(detail)"
        case .missingSourcePatch(let path):
            return "Build info marks a dirty build but its source patch is missing at \(path). Rebuild with `make build`."
        case .sourcePatchMismatch(let path, let expected, let actual):
            return "Source patch at \(path) does not match its build info (expected sha256 \(expected), found \(actual)). Rebuild with `make build`."
        case .receiptExists(let path):
            return "A run receipt already exists at \(path); write into a fresh output directory."
        case .missingReceipt(let path):
            return "Run receipt missing at \(path)."
        case .receiptMismatch(let detail):
            return "Run receipt mismatch: \(detail)"
        case .invalidReceipt(let detail):
            return "Invalid run receipt: \(detail)"
        }
    }
}

public enum ProvenanceDigest {
    public static func sha256Hex(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    public static func sha256Hex(_ string: String) -> String {
        sha256Hex(Data(string.utf8))
    }

    public static func sha256Hex(fileAt url: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        var hasher = SHA256()
        while let chunk = try handle.read(upToCount: 1 << 22), !chunk.isEmpty {
            hasher.update(data: chunk)
        }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }
}

extension KeyedDecodingContainer {
    /// Decodes a nullable field whose key must be present, so a missing key is an error rather than nil.
    func decodeNullable<T: Decodable>(_ type: T.Type, forKey key: Key) throws -> T? {
        guard contains(key) else {
            throw DecodingError.keyNotFound(
                key,
                DecodingError.Context(codingPath: codingPath, debugDescription: "Required key \(key.stringValue) is missing; write null explicitly.")
            )
        }
        return try decode(T?.self, forKey: key)
    }
}

/// Written next to the binary by `ops/write-buildinfo.sh`; describes exactly which sources produced it.
public struct LeniaBuildInfo: Codable, Sendable, Equatable {
    public let sourceCommit: String
    public let dirty: Bool
    public let binarySha256: String
    public let swiftVersion: String
    public let cEngineSha256: String
    public let sourcePatchSha256: String?

    enum CodingKeys: String, CodingKey {
        case sourceCommit = "source_commit"
        case dirty
        case binarySha256 = "binary_sha256"
        case swiftVersion = "swift_version"
        case cEngineSha256 = "c_engine_sha256"
        case sourcePatchSha256 = "source_patch_sha256"
    }

    public init(
        sourceCommit: String,
        dirty: Bool,
        binarySha256: String,
        swiftVersion: String,
        cEngineSha256: String,
        sourcePatchSha256: String?
    ) {
        self.sourceCommit = sourceCommit
        self.dirty = dirty
        self.binarySha256 = binarySha256
        self.swiftVersion = swiftVersion
        self.cEngineSha256 = cEngineSha256
        self.sourcePatchSha256 = sourcePatchSha256
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        sourceCommit = try container.decode(String.self, forKey: .sourceCommit)
        dirty = try container.decode(Bool.self, forKey: .dirty)
        binarySha256 = try container.decode(String.self, forKey: .binarySha256)
        swiftVersion = try container.decode(String.self, forKey: .swiftVersion)
        cEngineSha256 = try container.decode(String.self, forKey: .cEngineSha256)
        sourcePatchSha256 = try container.decodeNullable(String.self, forKey: .sourcePatchSha256)
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(sourceCommit, forKey: .sourceCommit)
        try container.encode(dirty, forKey: .dirty)
        try container.encode(binarySha256, forKey: .binarySha256)
        try container.encode(swiftVersion, forKey: .swiftVersion)
        try container.encode(cEngineSha256, forKey: .cEngineSha256)
        try container.encode(sourcePatchSha256, forKey: .sourcePatchSha256)
    }

    public static func buildInfoURL(executableURL: URL) -> URL {
        executableURL.deletingLastPathComponent()
            .appendingPathComponent("\(executableURL.lastPathComponent).buildinfo.json")
    }

    public static func sourcePatchURL(executableURL: URL) -> URL {
        executableURL.deletingLastPathComponent()
            .appendingPathComponent("\(executableURL.lastPathComponent).source.patch")
    }

    public static func runningExecutableURL() throws -> URL {
        guard let url = Bundle.main.executableURL else {
            throw ProvenanceError.missingExecutableURL
        }
        return url.resolvingSymlinksInPath()
    }

    /// Loads the build info and refuses a binary or source patch that no longer matches it.
    public static func loadVerified(executableURL: URL) throws -> LeniaBuildInfo {
        let infoURL = buildInfoURL(executableURL: executableURL)
        guard FileManager.default.fileExists(atPath: infoURL.path) else {
            throw ProvenanceError.missingBuildInfo(infoURL.path)
        }
        let info = try JSONDecoder().decode(LeniaBuildInfo.self, from: Data(contentsOf: infoURL))
        let binarySha = try ProvenanceDigest.sha256Hex(fileAt: executableURL)
        guard binarySha == info.binarySha256 else {
            throw ProvenanceError.binaryMismatch(path: executableURL.path, expected: info.binarySha256, actual: binarySha)
        }
        switch (info.dirty, info.sourcePatchSha256) {
        case (false, nil):
            break
        case (true, let expected?):
            let patchURL = sourcePatchURL(executableURL: executableURL)
            guard FileManager.default.fileExists(atPath: patchURL.path) else {
                throw ProvenanceError.missingSourcePatch(patchURL.path)
            }
            let patchSha = try ProvenanceDigest.sha256Hex(fileAt: patchURL)
            guard patchSha == expected else {
                throw ProvenanceError.sourcePatchMismatch(path: patchURL.path, expected: expected, actual: patchSha)
            }
        case (false, .some):
            throw ProvenanceError.inconsistentBuildInfo("a clean build must not record a source patch")
        case (true, nil):
            throw ProvenanceError.inconsistentBuildInfo("a dirty build must record its source patch sha256")
        }
        return info
    }
}
