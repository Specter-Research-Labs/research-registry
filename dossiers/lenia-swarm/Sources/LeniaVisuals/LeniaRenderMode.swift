import Foundation

public enum LeniaRenderMode: String, CaseIterable, Identifiable, Sendable {
    case truth = "Truth"
    case smoothMagma = "Magma"
    case viridis = "Viridis"
    case inferno = "Inferno"
    case plasma = "Plasma"

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
