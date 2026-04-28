import SwiftUI
import LeniaVisuals

struct RenderModePicker: View {
    @Binding var renderMode: LeniaRenderMode

    var body: some View {
        Picker("Render", selection: $renderMode) {
            ForEach(LeniaRenderMode.allCases) { mode in
                Text(mode.rawValue).tag(mode)
            }
        }
        .pickerStyle(.segmented)
    }
}
