import Foundation

public struct StabilityConfig: Codable, Sendable {
    public let enabled: Bool
    public let massMinFraction: Float
    public let massMaxFraction: Float
    public let requireSurvival: Bool
    public let windowSamples: Int
    public let windowMassStdMax: Float?
    public let windowOccupancyStdMax: Float?
    public let windowGyrationStdMax: Float?
    public let filters: [String: Float]

    enum CodingKeys: String, CodingKey {
        case enabled
        case massMinFraction = "mass_min_fraction"
        case massMaxFraction = "mass_max_fraction"
        case requireSurvival = "require_survival"
        case windowSamples = "window_samples"
        case windowMassStdMax = "window_mass_std_max"
        case windowOccupancyStdMax = "window_occupancy_std_max"
        case windowGyrationStdMax = "window_gyration_std_max"
        case filters
    }

    public init(
        enabled: Bool,
        massMinFraction: Float,
        massMaxFraction: Float,
        requireSurvival: Bool,
        windowSamples: Int,
        windowMassStdMax: Float?,
        windowOccupancyStdMax: Float?,
        windowGyrationStdMax: Float?,
        filters: [String: Float]
    ) {
        self.enabled = enabled
        self.massMinFraction = massMinFraction
        self.massMaxFraction = massMaxFraction
        self.requireSurvival = requireSurvival
        self.windowSamples = windowSamples
        self.windowMassStdMax = windowMassStdMax
        self.windowOccupancyStdMax = windowOccupancyStdMax
        self.windowGyrationStdMax = windowGyrationStdMax
        self.filters = filters
    }

    public static let defaultConfig = StabilityConfig(
        enabled: true,
        massMinFraction: 0.01,
        massMaxFraction: 0.4,
        requireSurvival: false,
        windowSamples: 0,
        windowMassStdMax: nil,
        windowOccupancyStdMax: nil,
        windowGyrationStdMax: nil,
        filters: [
            "gyration_min": 0.1,
            "gyration_max": 180.0
        ]
    )
}
