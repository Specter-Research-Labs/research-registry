import SwiftUI

struct ZoomableModifier: ViewModifier {
    @Binding var zoom: CGFloat
    @State private var offset: CGSize = .zero
    @GestureState private var gestureZoom: CGFloat = 1.0

    func body(content: Content) -> some View {
        content
            .scaleEffect(zoom * gestureZoom)
            .offset(offset)
            .gesture(magnifyGesture)
            .gesture(dragGesture)
            .onTapGesture(count: 2) {
                zoom = 1.0
                offset = .zero
            }
            .onChange(of: zoom) { _, newValue in
                if newValue <= 1.0 { offset = .zero }
            }
    }

    private var magnifyGesture: some Gesture {
        MagnifyGesture()
            .updating($gestureZoom) { value, state, _ in
                state = value.magnification
            }
            .onEnded { value in
                zoom = min(8.0, max(1.0, zoom * value.magnification))
            }
    }

    private var dragGesture: some Gesture {
        DragGesture()
            .onChanged { value in
                guard zoom > 1.0 else { return }
                offset = CGSize(
                    width: offset.width + value.translation.width,
                    height: offset.height + value.translation.height
                )
            }
    }
}

extension View {
    func zoomable(zoom: Binding<CGFloat>) -> some View {
        modifier(ZoomableModifier(zoom: zoom))
    }
}
