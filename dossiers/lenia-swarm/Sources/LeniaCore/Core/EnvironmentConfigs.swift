import Foundation

public struct ChemotaxisConfig: Codable, Sendable {
    public let enabled: Bool
    public let channel_index: Int
    public let mode: String
    public let sigma: Float
    public let amplitude: Float
    public let include_in_mass: Bool
    public let center: [Float]
    public let circle_radius: Float?
    public let seed: Int?
}

public struct ObstacleFieldConfig: Codable, Sendable {
    public let enabled: Bool
    public let channel_index: Int
    public let mode: String
    public let count: Int
    public let circle_radius: Float?
    public let sigma: Float
    public let amplitude: Float
    public let center: [Float]
    public let seed: Int

    public init(
        enabled: Bool,
        channel_index: Int,
        mode: String,
        count: Int,
        circle_radius: Float?,
        sigma: Float,
        amplitude: Float,
        center: [Float],
        seed: Int
    ) {
        self.enabled = enabled
        self.channel_index = channel_index
        self.mode = mode
        self.count = count
        self.circle_radius = circle_radius
        self.sigma = sigma
        self.amplitude = amplitude
        self.center = center
        self.seed = seed
    }
}

public struct FoodConfig: Codable, Sendable {
    public let enabled: Bool
    public let channel_index: Int
    public let mode: String
    public let uniform: UniformRange
    public let patches: [PatchConfig]?
    public let decay_rate: Float
    public let digest_rate: Float
    public let include_in_mass: Bool

    public init(
        enabled: Bool,
        channel_index: Int,
        mode: String,
        uniform: UniformRange,
        patches: [PatchConfig]? = nil,
        decay_rate: Float,
        digest_rate: Float,
        include_in_mass: Bool
    ) {
        self.enabled = enabled
        self.channel_index = channel_index
        self.mode = mode
        self.uniform = uniform
        self.patches = patches
        self.decay_rate = decay_rate
        self.digest_rate = digest_rate
        self.include_in_mass = include_in_mass
    }
}

public struct WallsConfig: Codable, Sendable {
    public let enabled: Bool
    public let patches: [PatchConfig]
}

public struct InterventionPatch: Codable, Sendable {
    public let center: [Int]
    public let size: Int
}

public struct InterventionConfig: Codable, Sendable {
    public let version: Int
    public let type: String
    public let step: Int
    public let patch: InterventionPatch
    public let std: Float?
    public let seed: Int?
    public let clip: [Float]?
    public let delta: [Float]?

    public init(
        version: Int = 1,
        type: String,
        step: Int,
        patch: InterventionPatch,
        std: Float? = nil,
        seed: Int? = nil,
        clip: [Float]? = nil,
        delta: [Float]? = nil
    ) {
        self.version = version
        self.type = type
        self.step = step
        self.patch = patch
        self.std = std
        self.seed = seed
        self.clip = clip
        self.delta = delta
    }
}

public struct EnvironmentConfig: Codable, Sendable {
    public let type: String
    public let depth: Int
    public let wallThickness: Int
    public let wallValue: Float
    public let passageWidth: Int?

    enum CodingKeys: String, CodingKey {
        case type
        case depth
        case wallThickness = "wall_thickness"
        case wallValue = "wall_value"
        case passageWidth = "passage_width"
    }

    public init(
        type: String,
        depth: Int,
        wallThickness: Int,
        wallValue: Float = -10.0,
        passageWidth: Int? = nil
    ) {
        self.type = type
        self.depth = depth
        self.wallThickness = wallThickness
        self.wallValue = wallValue
        self.passageWidth = passageWidth
    }
}

public struct BeamMutationConfig: Codable, Sendable {
    public let enabled: Bool
    public let probability: Float
    public let patchSize: Int
    public let std: Float
    public let seed: Int

    enum CodingKeys: String, CodingKey {
        case enabled
        case probability
        case patchSize = "patch_size"
        case std
        case seed
    }

    public init(
        enabled: Bool,
        probability: Float = 0.01,
        patchSize: Int = 20,
        std: Float = 0.1,
        seed: Int
    ) {
        self.enabled = enabled
        self.probability = probability
        self.patchSize = patchSize
        self.std = std
        self.seed = seed
    }
}
