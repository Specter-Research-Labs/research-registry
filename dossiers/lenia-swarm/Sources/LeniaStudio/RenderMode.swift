import SwiftUI
import LeniaVisuals

private let leniaShaderLibrary: ShaderLibrary = {
    ShaderLibrary(url: LeniaVisualResources.shaderLibraryURL())
}()

extension View {
    @ViewBuilder
    func leniaColorEffect(mode: LeniaRenderMode) -> some View {
        switch mode {
        case .truth:
            self
        case .body:
            self.colorEffect(leniaShaderLibrary.bodyLenia())
        case .smoothMagma:
            self.colorEffect(leniaShaderLibrary.smoothLenia())
        case .viridis:
            self.colorEffect(leniaShaderLibrary.viridisLenia())
        case .inferno:
            self.colorEffect(leniaShaderLibrary.infernoLenia())
        case .plasma:
            self.colorEffect(leniaShaderLibrary.plasmaLenia())
        case .turbo:
            self.colorEffect(leniaShaderLibrary.turboLenia())
        case .tol, .tolDepth:
            self.colorEffect(leniaShaderLibrary.tolLenia())
        case .flux, .flowHue, .flowLIC, .species:
            // Flux/flow/species need per-frame fields the per-pixel color effect
            // cannot see. Aux diagnostic images fall back to the body look.
            self.colorEffect(leniaShaderLibrary.bodyLenia())
        }
    }
}
