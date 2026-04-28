import Foundation

public struct GridConfig: Codable, Sendable {
    public let sx: Int
    public let sy: Int

    public init(sx: Int, sy: Int) {
        self.sx = sx
        self.sy = sy
    }
}

public struct FlowConfig: Codable, Sendable {
    public let dt: Float
    public let n: Int
    public let theta_A: Float

    public init(dt: Float, n: Int, theta_A: Float) {
        self.dt = dt
        self.n = n
        self.theta_A = theta_A
    }
}

public enum RuntimeProfile: String, Codable, Sendable {
    case paper
    case colab
    case experimental
}

public struct ImplementationConfig: Codable, Sendable {
    public let mode: String
    public let gradient_boundary: String?
    public let alpha_mode: String?
    public let kernel_profile: String?
    public let flow_clip: String?

    public init(
        mode: String,
        gradient_boundary: String? = nil,
        alpha_mode: String? = nil,
        kernel_profile: String? = nil,
        flow_clip: String? = nil
    ) {
        self.mode = mode
        self.gradient_boundary = gradient_boundary
        self.alpha_mode = alpha_mode
        self.kernel_profile = kernel_profile
        self.flow_clip = flow_clip
    }
}

public struct ReintegrationConfig: Codable, Sendable {
    public let dd: Int
    public let sigma: Float
    public let border: String

    public init(dd: Int, sigma: Float, border: String) {
        self.dd = dd
        self.sigma = sigma
        self.border = border
    }
}

public struct ImplementationSettings: Codable, Sendable {
    public let mode: String
    public let border: String
    public let gradientBoundary: String
    public let alphaMode: String
    public let kernelProfile: String
    public let flowClip: String

    public init(
        mode: String,
        border: String,
        gradientBoundary: String,
        alphaMode: String,
        kernelProfile: String,
        flowClip: String
    ) {
        self.mode = mode
        self.border = border
        self.gradientBoundary = gradientBoundary
        self.alphaMode = alphaMode
        self.kernelProfile = kernelProfile
        self.flowClip = flowClip
    }
}

public struct ParameterEmbeddingConfig: Codable, Sendable {
    public let enabled: Bool
    public let mix: String
    public let mix_seed: Int?

    public init(enabled: Bool, mix: String, mix_seed: Int?) {
        self.enabled = enabled
        self.mix = mix
        self.mix_seed = mix_seed
    }
}

public struct KernelParamRanges: Codable, Sendable {
    public let r: [Float]
    public let b: [Float]
    public let w: [Float]
    public let a: [Float]
    public let m: [Float]
    public let s: [Float]
    public let h: [Float]
    public let R: [Float]

    public init(
        r: [Float],
        b: [Float],
        w: [Float],
        a: [Float],
        m: [Float],
        s: [Float],
        h: [Float],
        R: [Float]
    ) {
        self.r = r
        self.b = b
        self.w = w
        self.a = a
        self.m = m
        self.s = s
        self.h = h
        self.R = R
    }
}

public struct ParamsConfig: Codable, Sendable {
    public let mode: String
    public let seed: Int?
    public let ranges: KernelParamRanges?
    public let r: [Float]?
    public let b: [[Float]]?
    public let w: [[Float]]?
    public let a: [[Float]]?
    public let m: [Float]?
    public let s: [Float]?
    public let h: [Float]?
    public let R: Float?

    public init(
        mode: String,
        seed: Int?,
        ranges: KernelParamRanges?,
        r: [Float]?,
        b: [[Float]]?,
        w: [[Float]]?,
        a: [[Float]]?,
        m: [Float]?,
        s: [Float]?,
        h: [Float]?,
        R: Float?
    ) {
        self.mode = mode
        self.seed = seed
        self.ranges = ranges
        self.r = r
        self.b = b
        self.w = w
        self.a = a
        self.m = m
        self.s = s
        self.h = h
        self.R = R
    }
}
