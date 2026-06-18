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
}

public enum LeniaVisualResources {
    public static func shaderLibraryURL() -> URL {
        guard let url = Bundle.module.url(forResource: "LeniaShaders", withExtension: "metallib") else {
            fatalError("LeniaShaders.metallib not found in resource bundle")
        }
        return url
    }
}
