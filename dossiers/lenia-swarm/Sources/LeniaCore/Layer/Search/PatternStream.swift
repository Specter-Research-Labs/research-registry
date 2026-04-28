import Foundation

public struct PatternStreamConfig: Codable, Sendable {
    public let source: String
    public let labelCount: Int
    public let length: Int?
    public let labels: [Int]?
    public let labelsPath: String?
    public let seed: Int?
    public let shuffleSeed: Int?
    public let stride: Int
    public let offset: Int

    public init(
        source: String,
        labelCount: Int,
        length: Int?,
        labels: [Int]?,
        labelsPath: String?,
        seed: Int?,
        shuffleSeed: Int?,
        stride: Int,
        offset: Int
    ) {
        self.source = source
        self.labelCount = labelCount
        self.length = length
        self.labels = labels
        self.labelsPath = labelsPath
        self.seed = seed
        self.shuffleSeed = shuffleSeed
        self.stride = stride
        self.offset = offset
    }
}

public struct IMGEPMutationProfile: Codable, Sendable {
    public let std: Float
    public let clip: Bool

    public init(std: Float, clip: Bool) {
        self.std = std
        self.clip = clip
    }
}

public struct IMGEPMutationScheduleConfig: Codable, Sendable {
    public let profiles: [IMGEPMutationProfile]

    public init(profiles: [IMGEPMutationProfile]) {
        self.profiles = profiles
    }
}

public struct IMGEPExperimentConfig: Codable, Sendable {
    public let patternStream: PatternStreamConfig
    public let mutationSchedule: IMGEPMutationScheduleConfig

    public init(patternStream: PatternStreamConfig, mutationSchedule: IMGEPMutationScheduleConfig) {
        self.patternStream = patternStream
        self.mutationSchedule = mutationSchedule
    }
}

public final class PatternStream: @unchecked Sendable {
    private let labels: [Int]
    private let stride: Int
    private let offset: Int

    public init(config: PatternStreamConfig) {
        guard config.labelCount > 0 else {
            fatalError("patternStream.labelCount must be > 0.")
        }
        guard config.stride > 0 else {
            fatalError("patternStream.stride must be > 0.")
        }
        guard config.offset >= 0 else {
            fatalError("patternStream.offset must be >= 0.")
        }

        var labels = Self.loadLabels(config: config)
        if let shuffleSeed = config.shuffleSeed {
            var rng = SeededRandomNumberGenerator(seed: UInt64(shuffleSeed))
            labels.shuffle(using: &rng)
        }
        Self.validateLabels(labels, labelCount: config.labelCount)

        self.labels = labels
        self.stride = config.stride
        self.offset = config.offset
    }

    public func label(atIndex index: Int) -> Int {
        let idx = (offset + index * stride) % labels.count
        return labels[idx]
    }

    private static func loadLabels(config: PatternStreamConfig) -> [Int] {
        switch config.source {
        case "labels":
            let explicit = config.labels
            let path = config.labelsPath
            if explicit != nil && path != nil {
                fatalError("patternStream.labels and patternStream.labelsPath cannot both be set.")
            }
            if let explicit = explicit {
                guard !explicit.isEmpty else {
                    fatalError("patternStream.labels must be non-empty.")
                }
                return explicit
            }
            if let path = path {
                return loadLabelsFromPath(path)
            }
            fatalError("patternStream.source=labels requires labels or labelsPath.")
        case "noise":
            guard let length = config.length, length > 0 else {
                fatalError("patternStream.length must be > 0 for source=noise.")
            }
            guard let seed = config.seed else {
                fatalError("patternStream.seed is required for source=noise.")
            }
            var rng = SeededRandomNumberGenerator(seed: UInt64(seed))
            return (0..<length).map { _ in
                Int.random(in: 0..<config.labelCount, using: &rng)
            }
        default:
            fatalError("patternStream.source must be one of: labels, noise.")
        }
    }

    private static func loadLabelsFromPath(_ path: String) -> [Int] {
        let url = URL(fileURLWithPath: path)
        guard let data = try? Data(contentsOf: url) else {
            fatalError("patternStream.labelsPath could not be read: \(path)")
        }
        guard let json = try? JSONSerialization.jsonObject(with: data) else {
            fatalError("patternStream.labelsPath is not valid JSON: \(path)")
        }
        if let flat = json as? [Int] {
            guard !flat.isEmpty else {
                fatalError("patternStream.labelsPath must contain at least one label.")
            }
            return flat
        }
        if let nested = json as? [[Int]] {
            let flat = nested.flatMap { $0 }
            guard !flat.isEmpty else {
                fatalError("patternStream.labelsPath must contain at least one label.")
            }
            return flat
        }
        fatalError("patternStream.labelsPath must be a JSON array of Int or array of arrays.")
    }

    private static func validateLabels(_ labels: [Int], labelCount: Int) {
        guard !labels.isEmpty else {
            fatalError("patternStream labels must be non-empty.")
        }
        for label in labels {
            if label < 0 || label >= labelCount {
                fatalError("patternStream labels must be in 0..<labelCount.")
            }
        }
    }
}
