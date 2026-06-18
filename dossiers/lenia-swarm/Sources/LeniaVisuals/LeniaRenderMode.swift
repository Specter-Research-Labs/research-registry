import Foundation

public enum LeniaRenderMode: String, CaseIterable, Identifiable, Sendable {
    case truth = "Truth"
    case body = "Body"
    case smoothMagma = "Magma"
    case viridis = "Viridis"
    case inferno = "Inferno"
    case plasma = "Plasma"
    case turbo = "Turbo"
    case tol = "Tol Rainbow"
    case flux = "Flux"
    case flowHue = "Flow"
    case flowLIC = "Flow Lines"
    case tolDepth = "Tol Depth"
    case species = "Species"

    public var id: String { rawValue }

    /// Index handed to the Metal colorizer. Must stay in sync with the
    /// `switch (uniforms.renderMode)` cases in LeniaShaders.metal `labStageFragment`.
    var shaderIndex: UInt32 {
        switch self {
        case .truth: return 0
        case .body: return 1
        case .smoothMagma: return 2
        case .viridis: return 3
        case .inferno: return 4
        case .plasma: return 5
        case .turbo: return 6
        case .flux: return 7
        case .tol: return 8
        case .flowHue: return 9
        case .flowLIC: return 10
        case .tolDepth: return 11
        case .species: return 12
        }
    }
}

public enum LeniaVisualResources {
    public static func shaderLibraryURL() -> URL {
        guard let url = Bundle.module.url(forResource: "LeniaShaders", withExtension: "metallib") else {
            fatalError("LeniaShaders.metallib not found in resource bundle")
        }
        return url
    }
}
