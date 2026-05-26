import SwiftUI
import LeniaCore
import LeniaVisuals

struct WorkerArenaView: View {
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var node: LeniaNode
    @State private var renderMode: LeniaRenderMode = .smoothMagma
    @State private var zoom: CGFloat = 1.0
    @State private var stageOffset: CGSize = .zero
    @FocusState private var isFocused: Bool

    private static let renderModes = LeniaRenderMode.allCases

    var body: some View {
        VStack(spacing: 0) {
            if let frame = appState.currentArenaFrame {
                ArenaFrameView(
                    frame: frame,
                    renderMode: renderMode,
                    zoom: $zoom,
                    offset: $stageOffset
                )
                    .aspectRatio(1, contentMode: .fit)
                    .padding()
            } else {
                ContentUnavailableView(
                    "Arena Lobby",
                    systemImage: "person.3.fill",
                    description: Text("Waiting for arena to start...")
                )
                .frame(maxHeight: .infinity)
            }
        }
        .focusable()
        .focused($isFocused)
        .focusEffectDisabled()
        .onKeyPress { handleKey($0) }
        .onAppear { isFocused = true }
        .navigationTitle("Arena")
        .toolbar {
            ToolbarItem(placement: .principal) {
                RenderModePicker(renderMode: $renderMode)
            }
            if let config = appState.activeArenaConfig {
                ToolbarItem(placement: .status) {
                    HStack(spacing: 8) {
                        if zoom > 1.01 {
                            Text(String(format: "%.1fx", zoom))
                                .monospacedDigit()
                        }
                        Text("\(config.size)x\(config.size)")
                    }
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }
            }
        }
    }

    private func handleKey(_ press: KeyPress) -> KeyPress.Result {
        switch press.characters {
        case "0":
            zoom = 1.0
            stageOffset = .zero
            return .handled
        case "1":
            renderMode = Self.renderModes[0]
            return .handled
        case "2":
            renderMode = Self.renderModes[1]
            return .handled
        case "3":
            renderMode = Self.renderModes[2]
            return .handled
        case "4":
            renderMode = Self.renderModes[3]
            return .handled
        case "5":
            renderMode = Self.renderModes[4]
            return .handled
        default:
            return .ignored
        }
    }
}

struct ArenaFrameView: View {
    let frame: ArenaFrame
    let renderMode: LeniaRenderMode
    @Binding var zoom: CGFloat
    @Binding var offset: CGSize

    var body: some View {
        LeniaLabStageView(
            frame: LeniaFieldFrame(
                step: frame.step,
                width: frame.width,
                height: frame.height,
                bytes: frame.data
            ),
            renderMode: renderMode,
            zoom: zoom,
            offset: offset,
            onTransformChange: { transform in
                zoom = transform.zoom
                offset = transform.offset
            },
            onPrimaryPoint: { _ in },
            onSecondaryPoint: { _ in },
            onHoverPointChange: { _ in },
            onBrushRadiusDelta: nil
        )
    }
}
