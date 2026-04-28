import Foundation

public struct CollectionConfig: Codable, Sendable {
    public let enabled: Bool
    public let requireStable: Bool
    public let requireFiltersPassed: Bool
    public let minScore: Float?
    public let exportEnabled: Bool

    enum CodingKeys: String, CodingKey {
        case enabled
        case requireStable = "require_stable"
        case requireFiltersPassed = "require_filters_passed"
        case minScore = "min_score"
        case exportEnabled = "export_enabled"
    }

    public init(
        enabled: Bool,
        requireStable: Bool,
        requireFiltersPassed: Bool,
        minScore: Float?,
        exportEnabled: Bool
    ) {
        self.enabled = enabled
        self.requireStable = requireStable
        self.requireFiltersPassed = requireFiltersPassed
        self.minScore = minScore
        self.exportEnabled = exportEnabled
    }

    public static let defaultConfig = CollectionConfig(
        enabled: true,
        requireStable: false,
        requireFiltersPassed: false,
        minScore: nil,
        exportEnabled: true
    )
}
