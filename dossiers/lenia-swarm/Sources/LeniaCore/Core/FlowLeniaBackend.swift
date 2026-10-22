import Foundation

public enum FlowLeniaComputeBackend: String, CaseIterable, Identifiable, Sendable, Equatable, Hashable, Codable {
    case mlx = "mlx"
    case metalFull = "metal-full"
    case cpu = "cpu"

    public var id: String { rawValue }

    public var displayName: String {
        switch self {
        case .mlx:
            "MLX"
        case .metalFull:
            "Metal full"
        case .cpu:
            "CPU"
        }
    }

    /// Backends that keep the batch resident in a field runner instead of stepping MLX arrays.
    public var hasResidentFieldRunner: Bool {
        switch self {
        case .mlx:
            false
        case .metalFull, .cpu:
            true
        }
    }

    public init(configValue: String) throws {
        switch configValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "mlx", "mlx-swift":
            self = .mlx
        case "metal-full":
            self = .metalFull
        case "cpu":
            self = .cpu
        default:
            throw ConfigError.invalidConfig(
                "Unsupported backend '\(configValue)'. Expected one of mlx, metal-full or cpu."
            )
        }
    }
}

public enum FlowLeniaParameterFieldMode: String, CaseIterable, Identifiable, Sendable, Equatable, Hashable, Codable {
    case none
    case kernelGain = "kernel-gain"
    case localizedGrowthParameters = "localized-growth-parameters"

    public var id: String { rawValue }

    public var displayName: String {
        switch self {
        case .none:
            "none"
        case .kernelGain:
            "kernel gain"
        case .localizedGrowthParameters:
            "localized m/s/h"
        }
    }

    public var parameterMultiple: Int {
        switch self {
        case .none:
            0
        case .kernelGain:
            1
        case .localizedGrowthParameters:
            3
        }
    }

    public func parameterCount(kernelCount: Int) -> Int {
        kernelCount * parameterMultiple
    }

    public static func fromEmbeddingEnabled(_ enabled: Bool) -> FlowLeniaParameterFieldMode {
        enabled ? .kernelGain : .none
    }

    public static func resolve(parameterFieldCount: Int, kernelCount: Int) -> FlowLeniaParameterFieldMode {
        if parameterFieldCount == 0 {
            return .none
        }
        if parameterFieldCount == kernelCount {
            return .kernelGain
        }
        if parameterFieldCount == kernelCount * 3 {
            return .localizedGrowthParameters
        }
        preconditionFailure("Flow Lenia parameter field count must match none(0), kernelGain(nbK), or localizedGrowthParameters(3*nbK).")
    }
}
