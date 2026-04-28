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
        case .smoothMagma:
            self.colorEffect(leniaShaderLibrary.smoothLenia())
        case .viridis:
            self.colorEffect(leniaShaderLibrary.viridisLenia())
        case .inferno:
            self.colorEffect(leniaShaderLibrary.infernoLenia())
        case .plasma:
            self.colorEffect(leniaShaderLibrary.plasmaLenia())
        }
    }
}
