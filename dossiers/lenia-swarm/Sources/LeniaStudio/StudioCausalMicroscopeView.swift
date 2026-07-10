import CoreGraphics
import Foundation
import MLX
import SwiftUI
import LeniaCore

struct StudioCausalField: Identifiable, @unchecked Sendable {
    enum Kind: String, Sendable {
        case matter
        case neighborhood
        case growth
        case kernel
    }

    let kind: Kind
    let title: String
    let equation: String
    let width: Int
    let height: Int
    let values: [Float]
    let image: CGImage?
    let isSigned: Bool

    var id: Kind { kind }

    func value(x: Int, y: Int) -> Float? {
        guard x >= 0, x < width, y >= 0, y < height else { return nil }
        let index = y * width + x
        guard values.indices.contains(index) else { return nil }
        return values[index]
    }
}

struct StudioCausalFrame: @unchecked Sendable {
    let step: Int
    let kernelCount: Int
    let fields: [StudioCausalField]

    init(step: Int, diagnostics: LeniaDiagnosticsFrame) {
        let renderer = LeniaRenderer()
        let sources: [(StudioCausalField.Kind, String, String, MLXArray, Bool)] = [
            (.matter, "Matter", "A", diagnostics.field, false),
            (.neighborhood, "Neighborhood", "U = K * A", diagnostics.neighborSum, false),
            (.growth, "Growth", "G(U)", diagnostics.growthField, true),
            (.kernel, "Kernel", "K", diagnostics.kernel, false),
        ]

        self.step = step
        self.kernelCount = diagnostics.kernelCount
        fields = sources.compactMap { kind, title, equation, array, isSigned in
            eval(array)
            let shape = array.shape
            guard shape.count >= 2 else { return nil }
            let height = shape[shape.count - 2]
            let width = shape[shape.count - 1]
            let values = array.asArray(Float.self)
            guard values.count >= width * height else { return nil }
            let image = isSigned
                ? renderer.renderToSignedImage(field: array)
                : renderer.renderToImage(mass: array)
            return StudioCausalField(
                kind: kind,
                title: title,
                equation: equation,
                width: width,
                height: height,
                values: Array(values.prefix(width * height)),
                image: image,
                isSigned: isSigned
            )
        }
    }
}

struct StudioCausalMicroscopeView: View {
    let frame: StudioCausalFrame?
    var compact = false
    var isLoading = false
    var onRefresh: (() -> Void)?
    var refreshDisabled = false

    @State private var probe: SIMD2<Int>?

    private var columns: [GridItem] {
        if compact {
            return [
                GridItem(.flexible(), spacing: 8),
                GridItem(.flexible(), spacing: 8),
            ]
        }
        return [GridItem(.adaptive(minimum: 190), spacing: 10)]
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            header

            if let frame, !frame.fields.isEmpty {
                LazyVGrid(columns: columns, spacing: compact ? 10 : 12) {
                    ForEach(frame.fields) { field in
                        causalPanel(field)
                    }
                }
                probeReadout(frame)
            } else {
                emptyState
            }
        }
        .padding(10)
        .background(StudioPalette.consoleSurface)
        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
    }

    private var header: some View {
        HStack(spacing: 8) {
            Label("Causal Microscope", systemImage: "scope")
                .font(StudioType.panelTitle)
                .foregroundStyle(StudioPalette.ink)

            if let frame {
                Text("t\(frame.step)")
                    .font(StudioType.dataSmall)
                    .foregroundStyle(StudioPalette.ember)
                Text("\(frame.kernelCount) kernels")
                    .font(StudioType.dataSmall)
                    .foregroundStyle(StudioPalette.mutedInk)
            }

            Spacer(minLength: 8)

            if let onRefresh {
                Button(action: onRefresh) {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(refreshDisabled)
                .help("Refresh causal fields")
            }
        }
    }

    private func causalPanel(_ field: StudioCausalField) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(field.title)
                    .font(StudioType.labelStrong)
                    .foregroundStyle(StudioPalette.ink)
                Spacer(minLength: 4)
                Text(field.equation)
                    .font(StudioType.dataSmall)
                    .foregroundStyle(
                        field.kind == .growth
                            ? StudioPalette.ember
                            : StudioPalette.mutedInk
                    )
                    .lineLimit(1)
            }

            GeometryReader { proxy in
                ZStack {
                    StudioPalette.stageBottom
                    if let image = field.image {
                        Image(decorative: image, scale: 1)
                            .resizable()
                            .interpolation(.none)
                            .aspectRatio(contentMode: .fit)
                    } else {
                        Image(systemName: "square.dashed")
                            .foregroundStyle(StudioPalette.mutedInk)
                    }
                    if let probe {
                        probeCrosshair(probe, field: field, size: proxy.size)
                    }
                }
                .contentShape(Rectangle())
                .onContinuousHover { phase in
                    switch phase {
                    case .active(let location):
                        probe = gridPoint(location, size: proxy.size, field: field)
                    case .ended:
                        probe = nil
                    }
                }
            }
            .aspectRatio(1, contentMode: .fit)
            .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .stroke(StudioPalette.hairline.opacity(0.5), lineWidth: 1)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(field.title)
            .accessibilityValue(accessibilityValue(field))
        }
    }

    @ViewBuilder
    private func probeCrosshair(
        _ point: SIMD2<Int>,
        field: StudioCausalField,
        size: CGSize
    ) -> some View {
        let x = (CGFloat(point.x) + 0.5) / CGFloat(max(1, field.width)) * size.width
        let y = (CGFloat(point.y) + 0.5) / CGFloat(max(1, field.height)) * size.height
        Path { path in
            path.move(to: CGPoint(x: x, y: 0))
            path.addLine(to: CGPoint(x: x, y: size.height))
            path.move(to: CGPoint(x: 0, y: y))
            path.addLine(to: CGPoint(x: size.width, y: y))
        }
        .stroke(
            Color.white.opacity(0.72),
            style: StrokeStyle(lineWidth: 0.75, dash: [3, 3])
        )

        Circle()
            .stroke(StudioPalette.ember, lineWidth: 1.5)
            .frame(width: 8, height: 8)
            .position(x: x, y: y)
    }

    private func probeReadout(_ frame: StudioCausalFrame) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text("CELL")
                    .font(StudioType.label)
                    .foregroundStyle(StudioPalette.mutedInk)
                Text(probe.map { "\($0.x),\($0.y)" } ?? "--,--")
                    .font(StudioType.dataSmall)
                    .foregroundStyle(StudioPalette.ink)
            }

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: compact ? 94 : 118), spacing: 10)],
                alignment: .leading,
                spacing: 6
            ) {
                ForEach(frame.fields) { field in
                    VStack(alignment: .leading, spacing: 1) {
                        Text(field.equation)
                            .font(StudioType.label)
                            .foregroundStyle(StudioPalette.mutedInk)
                        Text(formatted(probe.flatMap { field.value(x: $0.x, y: $0.y) }))
                            .font(StudioType.dataSmall)
                            .foregroundStyle(
                                field.kind == .growth
                                    ? StudioPalette.ember
                                    : StudioPalette.ink
                            )
                    }
                }
            }
        }
        .padding(.top, 2)
    }

    private var emptyState: some View {
        VStack(spacing: 9) {
            if isLoading {
                ProgressView()
                    .controlSize(.small)
            } else {
                Image(systemName: "scope")
                    .font(.title3)
                    .foregroundStyle(StudioPalette.mutedInk)
            }
            Text(isLoading ? "Preparing causal fields" : "Causal fields unavailable")
                .font(StudioType.bodySmall)
                .foregroundStyle(StudioPalette.mutedInk)
        }
        .frame(maxWidth: .infinity, minHeight: compact ? 190 : 250)
        .background(
            RoundedRectangle(cornerRadius: 5, style: .continuous)
                .fill(StudioPalette.surfaceSoft.opacity(0.22))
        )
    }

    private func gridPoint(
        _ location: CGPoint,
        size: CGSize,
        field: StudioCausalField
    ) -> SIMD2<Int> {
        let normalizedX = max(0, min(0.999_999, location.x / max(1, size.width)))
        let normalizedY = max(0, min(0.999_999, location.y / max(1, size.height)))
        return SIMD2(
            min(field.width - 1, Int(normalizedX * CGFloat(field.width))),
            min(field.height - 1, Int(normalizedY * CGFloat(field.height)))
        )
    }

    private func accessibilityValue(_ field: StudioCausalField) -> String {
        guard let probe, let value = field.value(x: probe.x, y: probe.y) else {
            return "No cell selected"
        }
        return "Cell \(probe.x), \(probe.y), value \(formatted(value))"
    }

    private func formatted(_ value: Float?) -> String {
        guard let value, value.isFinite else { return "--" }
        return String(format: "%+.4f", value)
    }
}
