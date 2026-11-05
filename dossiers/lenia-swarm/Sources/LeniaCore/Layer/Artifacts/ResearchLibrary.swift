import Crypto
import Foundation

public struct ResearchLibraryEntry: Codable, Sendable {
    public let creature: SavedCreature
    public let campaignId: String?
    public let runId: String
    public let recordedAt: Date
    public let configHash: String?
    public let sourceMode: String?
    public let sourceAlgorithm: String?
    public let researchMetadata: [String: AnyCodable]?
    public let runtimeFamily: String
    public let runtimeCapabilities: [String]
    public let specimenManifest: SpecimenManifest

    enum CodingKeys: String, CodingKey {
        case creature
        case campaignId = "campaign_id"
        case runId = "run_id"
        case recordedAt = "recorded_at"
        case configHash = "config_hash"
        case sourceMode = "source_mode"
        case sourceAlgorithm = "source_algorithm"
        case researchMetadata = "research_metadata"
        case runtimeFamily = "runtime_family"
        case runtimeCapabilities = "runtime_capabilities"
        case specimenManifest = "specimen_manifest"
    }

    public init(
        creature: SavedCreature,
        campaignId: String?,
        runId: String,
        recordedAt: Date,
        configHash: String?,
        sourceMode: String? = nil,
        sourceAlgorithm: String? = nil,
        researchMetadata: [String: AnyCodable]? = nil,
        runtimeFamily: String? = nil,
        runtimeCapabilities: [String]? = nil,
        specimenManifest: SpecimenManifest? = nil
    ) {
        self.creature = creature
        self.campaignId = campaignId
        self.runId = runId
        self.recordedAt = recordedAt
        self.configHash = configHash
        self.sourceMode = sourceMode
        self.sourceAlgorithm = sourceAlgorithm
        self.researchMetadata = researchMetadata
        let resolvedManifest = specimenManifest ?? buildLibrarySpecimenManifest(
            creature: creature,
            campaignID: campaignId,
            runID: runId,
            recordedAt: recordedAt,
            configHash: configHash,
            sourceMode: sourceMode,
            sourceAlgorithm: sourceAlgorithm,
            researchMetadata: researchMetadata
        )
        self.runtimeFamily = runtimeFamily ?? resolvedManifest.runtimeFamily
        self.runtimeCapabilities = (runtimeCapabilities ?? resolvedManifest.runtimeCapabilities).sorted()
        self.specimenManifest = resolvedManifest
    }
}

public enum ResearchLibraryWriter {
    public static func write(entries: [ResearchLibraryEntry], runDirectory: URL) throws -> URL {
        let libraryDirectory = runDirectory.appendingPathComponent("library", isDirectory: true)
        try FileManager.default.createDirectory(at: libraryDirectory, withIntermediateDirectories: true)
        let indexURL = libraryDirectory.appendingPathComponent("index.jsonl")
        try writeResearchJSONLines(entries, to: indexURL)
        return indexURL
    }
}

public func archiveResearchLibraryEntry(
    creature: SavedCreature,
    runId: String,
    configHash: String?,
    sourceMode: String? = nil,
    sourceAlgorithm: String? = nil,
    researchMetadata: [String: AnyCodable]? = nil,
    recordedAt: Date = Date(),
    campaignId: String? = nil
) -> ResearchLibraryEntry {
    ResearchLibraryEntry(
        creature: creature,
        campaignId: campaignId,
        runId: runId,
        recordedAt: recordedAt,
        configHash: configHash,
        sourceMode: sourceMode,
        sourceAlgorithm: sourceAlgorithm,
        researchMetadata: researchMetadata
    )
}

public func writeResearchJSONLines<T: Encodable>(_ values: [T], to url: URL) throws {
    let encoder = researchJSONEncoder()
    let content = try values.reduce(into: Data()) { data, value in
        data.append(try researchJSONLine(value, encoder: encoder))
    }
    try content.write(to: url, options: .atomic)
}

public func researchJSONEncoder(prettyPrinted: Bool = false) -> JSONEncoder {
    let encoder = JSONEncoder()
    var formatting: JSONEncoder.OutputFormatting = [.sortedKeys]
    if prettyPrinted {
        formatting.insert(.prettyPrinted)
    }
    encoder.outputFormatting = formatting
    encoder.dateEncodingStrategy = .deferredToDate
    return encoder
}

public func writeResearchJSON<T: Encodable>(
    _ value: T,
    to url: URL,
    prettyPrinted: Bool = false
) throws {
    try researchJSONEncoder(prettyPrinted: prettyPrinted)
        .encode(value)
        .write(to: url, options: .atomic)
}

public func researchJSONLine<T: Encodable>(
    _ value: T,
    encoder: JSONEncoder? = nil
) throws -> Data {
    let resolvedEncoder: JSONEncoder
    if let encoder {
        resolvedEncoder = encoder
    } else {
        resolvedEncoder = researchJSONEncoder()
    }
    var data = try resolvedEncoder.encode(value)
    data.append(0x0A)
    return data
}

public func researchEncodedJSON<T: Encodable>(
    _ value: T,
    prettyPrinted: Bool = false
) throws -> Data {
    try researchJSONEncoder(prettyPrinted: prettyPrinted).encode(value)
}

public func researchConfigHash(_ components: [(String, Data)]) -> String {
    var data = Data()
    for (label, payload) in components.sorted(by: { $0.0 < $1.0 }) {
        data.append(Data(label.utf8))
        data.append(0x00)
        data.append(payload)
        data.append(0x00)
    }
    let digest = SHA256.hash(data: data)
    return digest.prefix(12).map { String(format: "%02x", $0) }.joined()
}

public func deterministicResearchUUID(_ stableKey: String) -> UUID {
    let digest = SHA256.hash(data: Data(stableKey.utf8))
    var bytes = Array(digest.prefix(16))
    bytes[6] = (bytes[6] & 0x0F) | 0x50
    bytes[8] = (bytes[8] & 0x3F) | 0x80
    return UUID(uuid: (
        bytes[0], bytes[1], bytes[2], bytes[3],
        bytes[4], bytes[5], bytes[6], bytes[7],
        bytes[8], bytes[9], bytes[10], bytes[11],
        bytes[12], bytes[13], bytes[14], bytes[15]
    ))
}

public func researchMetadataValue(_ value: Any) throws -> AnyCodable {
    try AnyCodable(researchMetadataNormalize(value))
}

private func researchMetadataNormalize(_ value: Any) throws -> Any {
    switch value {
    case is NSNull:
        return NSNull()
    case let bool as Bool:
        return bool
    case let int as Int:
        return int
    case let float as Float:
        return Double(float)
    case let double as Double:
        return double
    case let string as String:
        return string
    case let anyCodable as AnyCodable:
        return try researchMetadataNormalize(anyCodable.value)
    case let array as [Float]:
        return array.map(Double.init)
    case let matrix as [[Float]]:
        return matrix.map { $0.map(Double.init) }
    case let array as [Double]:
        return array
    case let matrix as [[Double]]:
        return matrix
    case let array as [Int]:
        return array
    case let array as [Any]:
        return try array.map(researchMetadataNormalize)
    case let dict as [String: Float]:
        return dict.mapValues(Double.init)
    case let dict as [String: Double]:
        return dict
    case let dict as [String: Int]:
        return dict
    case let dict as [String: AnyCodable]:
        return try dict.mapValues { try researchMetadataNormalize($0.value) }
    case let dict as [String: Any]:
        return try dict.mapValues(researchMetadataNormalize)
    default:
        throw EncodingError.invalidValue(
            value,
            .init(codingPath: [], debugDescription: "Unsupported research metadata type: \(type(of: value))")
        )
    }
}
