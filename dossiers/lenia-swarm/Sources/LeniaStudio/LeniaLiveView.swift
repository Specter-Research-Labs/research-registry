import SwiftUI
import LeniaCore
import LeniaVisuals
import MLX

private enum LiveDisplayMode: String, CaseIterable, Identifiable {
    case render = "Render"
    case diagnostics = "Diagnostics"

    var id: String { rawValue }
}

struct LeniaLiveView: View {
    let creature: LeniaCreature
    var savedCreature: SavedCreature? = nil
    var replaySource: StudioReplayReference? = nil

    @StateObject private var simulationModel = LiveSimulationModel()
    @State private var displayMode: LiveDisplayMode = .render
    @State private var fieldProjection: LabFieldProjection = .matter
    @State private var useFluidVisuals = true
    @State private var renderMode: LeniaRenderMode = .smoothMagma
    @State private var zoom: CGFloat = 1.0
    @State private var stageOffset: CGSize = .zero
    @State private var showCharts = false
    @FocusState private var isFocused: Bool

    private static let renderModes = LeniaRenderMode.allCases

    private var savedMetrics: SimulationMetrics? {
        savedCreature?.metrics
    }

    var body: some View {
        VStack(spacing: 0) {
            Group {
                switch displayMode {
                case .render:
                    renderStage
                case .diagnostics:
                    diagnosticStage
                }
            }

            controlBar

            if showCharts || displayMode == .diagnostics {
                MetricChartPanel(metricHistory: simulationModel.metricHistory)
            }
        }
        .focusable()
        .focused($isFocused)
        .focusEffectDisabled()
        .onKeyPress { handleKey($0) }
        .onAppear {
            simulationModel.setDiagnosticsEnabled(displayMode == .diagnostics)
            simulationModel.start(creature: creature, savedCreature: savedCreature, replaySource: replaySource)
            isFocused = true
        }
        .onDisappear {
            simulationModel.stop()
        }
        .onChange(of: creature.id) { _, _ in
            simulationModel.restart(creature: creature, savedCreature: savedCreature, replaySource: replaySource)
        }
        .onChange(of: replaySource) { _, newReplaySource in
            simulationModel.restart(creature: creature, savedCreature: savedCreature, replaySource: newReplaySource)
        }
        .onChange(of: displayMode) { _, newMode in
            simulationModel.setDiagnosticsEnabled(newMode == .diagnostics)
        }
        .onChange(of: fieldProjection) { _, newProjection in
            simulationModel.setFieldProjection(newProjection)
        }
        .onChange(of: simulationModel.availableProjections) { _, projections in
            if !projections.contains(fieldProjection) {
                fieldProjection = .matter
                simulationModel.setFieldProjection(.matter)
            }
        }
        .navigationTitle("Seed \(creature.seed)")
        .toolbar {
            ToolbarItem(placement: .principal) {
                RenderModePicker(renderMode: $renderMode)
            }
            ToolbarItem(placement: .primaryAction) {
                HStack(spacing: 12) {
                    if let saved = savedCreature {
                        Menu("Export") {
                            Button("Copy Config") {
                                CreatureExport.copyConfigToClipboard(for: saved)
                            }
                            Button("Save Config...") {
                                _ = CreatureExport.saveConfigToFile(for: saved)
                            }
                        }
                    }
                    Text(String(format: "Score: %.3f", creature.score))
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private var renderStage: some View {
        GeometryReader { _ in
            if let frame = simulationModel.displayFrame {
                ZStack {
                    Color.black.ignoresSafeArea()

                    LeniaLabStageView(
                        frame: frame,
                        renderMode: renderMode,
                        zoom: zoom,
                        offset: stageOffset,
                        onTransformChange: { transform in
                            zoom = transform.zoom
                            stageOffset = transform.offset
                        },
                        onPrimaryPoint: { _ in },
                        onSecondaryPoint: { _ in },
                        onHoverPointChange: { _ in },
                        onBrushRadiusDelta: nil
                    )
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ZStack {
                    Color.black
                    ProgressView().controlSize(.large)
                }
            }
        }
    }

    private var diagnosticStage: some View {
        ScrollView {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 16) {
                    diagnosticPanels
                    diagnosticSidebar
                        .frame(width: 340)
                }

                VStack(spacing: 16) {
                    diagnosticPanels
                    diagnosticSidebar
                }
            }
            .padding(16)
        }
        .background(
            StudioSceneBackground()
        )
    }

    private var diagnosticPanels: some View {
        StudioSurface(
            title: "Diagnostic View",
            subtitle: "Field, neighborhood potential, growth field, and mean kernel"
        ) {
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 12), count: 2), spacing: 12) {
                DiagnosticFramePanel(
                    title: "Field",
                    equation: "A_t(x)",
                    fieldFrame: simulationModel.displayFrame,
                    image: simulationModel.diagnosticImages?.field,
                    palette: renderMode,
                    useFluidVisuals: useFluidVisuals
                )
                DiagnosticFramePanel(
                    title: "Neighbor Sum",
                    equation: "U(x) = mean_k (K_k * A_t)(x)",
                    fieldFrame: nil,
                    image: simulationModel.diagnosticImages?.neighborSum,
                    palette: .viridis,
                    useFluidVisuals: useFluidVisuals
                )
                DiagnosticFramePanel(
                    title: "Growth",
                    equation: "Phi(x) = sum_k h_k [2 exp(-((U_k-m_k)^2)/(2 s_k^2)) - 1]",
                    fieldFrame: nil,
                    image: simulationModel.diagnosticImages?.growthField,
                    palette: nil,
                    useFluidVisuals: useFluidVisuals
                )
                DiagnosticFramePanel(
                    title: "Kernel",
                    equation: "K(x) = mean_k K_k(x)",
                    fieldFrame: nil,
                    image: simulationModel.diagnosticImages?.kernel,
                    palette: .plasma,
                    useFluidVisuals: false
                )
            }
        }
    }

    private var diagnosticSidebar: some View {
        VStack(spacing: 16) {
            StudioSurface(title: "Telemetry", subtitle: "Live dynamics sampled from the running state") {
                VStack(alignment: .leading, spacing: 10) {
                    HStack(spacing: 8) {
                        StudioMetricPill(label: "Step", value: "\(simulationModel.stepCount)", accent: StudioPalette.ember)
                        StudioMetricPill(label: "FPS", value: String(format: "%.1f", simulationModel.displayFps), accent: StudioPalette.ocean)
                    }

                    HStack(spacing: 8) {
                        StudioMetricPill(
                            label: "Mass",
                            value: simulationModel.latestSample.map { String(format: "%.4f", $0.mass) } ?? "..."
                        )
                        StudioMetricPill(
                            label: "Occ",
                            value: simulationModel.latestSample.map { String(format: "%.4f", $0.occupancy) } ?? "..."
                        )
                    }

                    HStack(spacing: 8) {
                        StudioMetricPill(
                            label: "Vel",
                            value: simulationModel.latestSample.map { String(format: "%.4f", $0.velocity) } ?? "...",
                            accent: StudioPalette.moss
                        )
                        StudioMetricPill(
                            label: "Growth",
                            value: simulationModel.diagnosticTelemetry.map { String(format: "%+.4f", $0.growthMean) } ?? "...",
                            accent: StudioPalette.ember
                        )
                    }

                    if let telemetry = simulationModel.diagnosticTelemetry {
                        VStack(spacing: 8) {
                            StudioKeyValueRow(label: "Neighbor Mean", value: String(format: "%.4f", telemetry.neighborMean))
                            StudioKeyValueRow(label: "Kernel Peak", value: String(format: "%.4f", telemetry.kernelPeak))
                            StudioKeyValueRow(label: "Kernel Count", value: "\(telemetry.kernelCount)")
                        }
                    }
                }
            }

            StudioSurface(title: "Equations", subtitle: "Parameters next to behavior") {
                VStack(alignment: .leading, spacing: 12) {
                    EquationCard(
                        title: "Kernel Family",
                        equation: "K_k(r) = sum_i b_{k,i} exp(-((r-a_{k,i})^2)/(2 w_{k,i}^2))",
                        details: [
                            "R = \(format(creature.params.R, precision: 2))",
                            "r = \(format(creature.params.r, precision: 2))",
                            "a = \(formatNested(creature.params.a, precision: 2))",
                            "w = \(formatNested(creature.params.w, precision: 2))",
                            "b = \(formatNested(creature.params.b, precision: 2))",
                        ]
                    )

                    EquationCard(
                        title: "Growth Law",
                        equation: "g_k(u) = h_k [2 exp(-((u-m_k)^2)/(2 s_k^2)) - 1]",
                        details: [
                            "m = \(format(creature.params.m, precision: 2))",
                            "s = \(format(creature.params.s, precision: 3))",
                            "h = \(format(creature.params.h, precision: 2))",
                        ]
                    )
                }
            }

            if let metrics = savedMetrics {
                StudioSurface(title: "Morphometrics", subtitle: "Saved invariants for this creature") {
                    VStack(spacing: 8) {
                        StudioKeyValueRow(label: "Stable", value: metrics.isStable ? "Yes" : "No")
                        StudioKeyValueRow(label: "Gyration", value: String(format: "%.3f", metrics.gyration))
                        StudioKeyValueRow(label: "Center Velocity", value: String(format: "%.3f", metrics.centerVelocity))
                        if let complexity = metrics.complexityMean {
                            StudioKeyValueRow(label: "Complexity", value: String(format: "%.3f", complexity))
                        }
                        if let momentMass = metrics.momentMass {
                            StudioKeyValueRow(label: "Moment Mass", value: String(format: "%.3f", momentMass))
                        }
                        if let momentVolume = metrics.momentVolume {
                            StudioKeyValueRow(label: "Moment Volume", value: String(format: "%.3f", momentVolume))
                        }
                        if let momentDensity = metrics.momentDensity {
                            StudioKeyValueRow(label: "Moment Density", value: String(format: "%.3f", momentDensity))
                        }
                        if let hu1 = metrics.hu1 {
                            StudioKeyValueRow(label: "Hu 1", value: String(format: "%.3f", hu1))
                        }
                        if let hu2 = metrics.hu2 {
                            StudioKeyValueRow(label: "Hu 2", value: String(format: "%.3f", hu2))
                        }
                        if let flusser1 = metrics.flusser1 {
                            StudioKeyValueRow(label: "Flusser 1", value: String(format: "%.3f", flusser1))
                        }
                        if let flusser2 = metrics.flusser2 {
                            StudioKeyValueRow(label: "Flusser 2", value: String(format: "%.3f", flusser2))
                        }
                    }
                }
            }
        }
    }

    private var controlBar: some View {
        HStack(spacing: 12) {
            Button(action: { simulationModel.togglePause() }) {
                Label(
                    simulationModel.isPaused ? "Play" : "Pause",
                    systemImage: simulationModel.isPaused ? "play.fill" : "pause.fill"
                )
            }
            .buttonStyle(.bordered)

            Button(action: {
                simulationModel.restart(
                    creature: creature,
                    savedCreature: savedCreature,
                    replaySource: replaySource
                )
            }) {
                Label("Reset", systemImage: "arrow.counterclockwise")
            }
            .buttonStyle(.bordered)

            if simulationModel.availableProjections.count > 1 {
                Picker("Projection", selection: $fieldProjection) {
                    ForEach(simulationModel.availableProjections) { projection in
                        Text(projection.label).tag(projection)
                    }
                }
                .pickerStyle(.segmented)
                .frame(width: min(CGFloat(simulationModel.availableProjections.count) * 110, 420))
            }

            Picker("View", selection: $displayMode) {
                ForEach(LiveDisplayMode.allCases) { mode in
                    Text(mode.rawValue).tag(mode)
                }
            }
            .pickerStyle(.segmented)
            .frame(width: 220)

            Toggle(isOn: $useFluidVisuals) {
                Label("Fluid", systemImage: "drop.fill")
            }
            .toggleStyle(.button)

            if displayMode == .render {
                Toggle(isOn: $showCharts) {
                    Label("Charts", systemImage: "chart.xyaxis.line")
                }
                .toggleStyle(.button)
            }

            Spacer()

            if simulationModel.runtimeLabel != "Synthetic preview" {
                Text(simulationModel.runtimeLabel)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if displayMode == .render, zoom > 1.01 {
                Text(String(format: "%.1fx", zoom))
                    .monospacedDigit()
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Text(simulationModel.stats)
                .monospacedDigit()
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .controlSize(.small)
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(.bar)
    }

    private func handleKey(_ press: KeyPress) -> KeyPress.Result {
        switch press.characters {
        case " ":
            simulationModel.togglePause()
            return .handled
        case "r":
            simulationModel.restart(creature: creature, savedCreature: savedCreature, replaySource: replaySource)
            return .handled
        case "d":
            displayMode = displayMode == .render ? .diagnostics : .render
            return .handled
        case "f":
            useFluidVisuals.toggle()
            return .handled
        case "c":
            if displayMode == .render {
                showCharts.toggle()
                return .handled
            }
            return .ignored
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

struct DiagnosticImageSet: @unchecked Sendable {
    let field: CGImage?
    let neighborSum: CGImage?
    let growthField: CGImage?
    let kernel: CGImage?
}

struct DiagnosticTelemetry: Sendable {
    let growthMean: Float
    let neighborMean: Float
    let kernelPeak: Float
    let kernelCount: Int
}

struct MetricSample: Sendable {
    let mass: Float
    let occupancy: Float
    let velocity: Float
}

struct MetricHistory {
    static let capacity = 200
    var mass: [Float] = []
    var occupancy: [Float] = []
    var velocity: [Float] = []

    mutating func append(_ sample: MetricSample) {
        mass.append(sample.mass)
        occupancy.append(sample.occupancy)
        velocity.append(sample.velocity)

        if mass.count > Self.capacity {
            mass.removeFirst()
            occupancy.removeFirst()
            velocity.removeFirst()
        }
    }
}

struct MetricComputer {
    private var prevCenterX: Float?
    private var prevCenterY: Float?

    mutating func compute(data: [Float], width: Int, height: Int) -> MetricSample {
        let totalCells = Float(width * height)

        var totalMass: Float = 0
        var occupied: Float = 0
        var cx: Float = 0
        var cy: Float = 0
        let threshold: Float = 0.05

        for y in 0..<height {
            for x in 0..<width {
                let v = data[y * width + x]
                totalMass += v
                if v > threshold {
                    occupied += 1
                    cx += Float(x) * v
                    cy += Float(y) * v
                }
            }
        }

        if totalMass > 0 {
            cx /= totalMass
            cy /= totalMass
        }

        var vel: Float = 0
        if let px = prevCenterX, let py = prevCenterY {
            let dx = cx - px
            let dy = cy - py
            vel = (dx * dx + dy * dy).squareRoot()
        }
        prevCenterX = cx
        prevCenterY = cy

        return MetricSample(
            mass: totalMass / totalCells,
            occupancy: occupied / totalCells,
            velocity: vel
        )
    }
}

@MainActor
class LiveSimulationModel: ObservableObject, @unchecked Sendable {
    @Published var displayFrame: LeniaFieldFrame?
    @Published var diagnosticImages: DiagnosticImageSet?
    @Published var diagnosticTelemetry: DiagnosticTelemetry?
    @Published var latestSample: MetricSample?
    @Published var stats = "Initializing..."
    @Published var isPaused = false
    @Published var metricHistory = MetricHistory()
    @Published var stepCount = 0
    @Published var displayFps = 0.0
    @Published var availableProjections: [LabFieldProjection] = [.matter]
    @Published var runtimeLabel = "Synthetic preview"

    private var task: Task<Void, Never>?
    private let gridSize = 128
    private let diagnosticCadence = 4
    private var diagnosticsEnabled = false
    private var currentProjection: LabFieldProjection = .matter

    func togglePause() {
        isPaused.toggle()
    }

    func setDiagnosticsEnabled(_ enabled: Bool) {
        diagnosticsEnabled = enabled
    }

    func setFieldProjection(_ projection: LabFieldProjection) {
        currentProjection = projection
    }

    func stop() {
        task?.cancel()
        task = nil
    }

    func restart(
        creature: LeniaCreature,
        savedCreature: SavedCreature? = nil,
        replaySource: StudioReplayReference? = nil
    ) {
        stop()
        displayFrame = nil
        diagnosticImages = nil
        diagnosticTelemetry = nil
        latestSample = nil
        stats = "Initializing..."
        metricHistory = MetricHistory()
        stepCount = 0
        displayFps = 0
        availableProjections = [.matter]
        runtimeLabel = replaySource == nil ? "Synthetic preview" : "Loading replay"
        start(creature: creature, savedCreature: savedCreature, replaySource: replaySource)
    }

    func start(
        creature: LeniaCreature,
        savedCreature: SavedCreature? = nil,
        replaySource: StudioReplayReference? = nil
    ) {
        stop()

        let gridSize = self.gridSize
        let diagnosticCadence = self.diagnosticCadence

        task = Task.detached(priority: .userInitiated) { [weak self] in
            let renderer = LeniaRenderer()
            let fpsBufferSize = 30
            var fpsTimestamps = [Date]()
            fpsTimestamps.reserveCapacity(fpsBufferSize)
            var displayFps: Double = 0
            var metricComputer = MetricComputer()
            let targetFrameInterval: Duration = .milliseconds(33)
            var latestMatterData: [Float]?
            var renderedProjection: LabFieldProjection = .matter

            func updateDisplayFps(step: Int) {
                let now = Date()
                fpsTimestamps.append(now)
                if fpsTimestamps.count > fpsBufferSize {
                    fpsTimestamps.removeFirst()
                }

                if step % 10 == 0, fpsTimestamps.count >= 2 {
                    let span = fpsTimestamps.last!.timeIntervalSince(fpsTimestamps.first!)
                    if span > 0 {
                        displayFps = Double(fpsTimestamps.count - 1) / span
                    }
                }
            }

            do {
                let runtimeConfig: LeniaRuntimeConfig
                let runtimeLabelPrefix: String
                if let replaySource {
                    let baseData = try Data(contentsOf: URL(fileURLWithPath: replaySource.baseConfigPath))
                    let baseRuntimeConfig = try loadRuntimeConfig(from: baseData)
                    runtimeConfig = try studioRuntimeConfig(
                        base: baseRuntimeConfig,
                        creature: creature,
                        savedCreature: savedCreature
                    )
                    runtimeLabelPrefix = savedCreature == nil ? "Canonical replay" : "Selected replay"
                } else {
                    runtimeConfig = try studioFallbackRuntimeConfig(
                        creature: creature,
                        savedCreature: savedCreature,
                        gridSize: gridSize
                    )
                    runtimeLabelPrefix = savedCreature == nil ? "Synthetic preview" : "Saved runtime"
                }

                let runtime = FlowLeniaInteractiveSimulator(runtimeConfig: runtimeConfig)
                var state = runtime.makeInitialState()
                let runtimeLabel = "\(runtimeLabelPrefix) · \(runtimeConfig.channels)c · \(runtimeConfig.nbK)k"
                let projections = LabFieldProjection.options(channelCount: runtimeConfig.channels)

                while !Task.isCancelled {
                    let paused = await self?.pausedValue() ?? false
                    if paused {
                        let selectedProjection = await self?.currentProjectionValue() ?? .matter
                        if let latestMatterData,
                           selectedProjection != renderedProjection {
                            let frame = liveProjectionFrame(
                                matterData: latestMatterData,
                                selectedProjection: selectedProjection,
                                step: state.step,
                                width: runtimeConfig.sx,
                                height: runtimeConfig.sy,
                                channelCount: runtimeConfig.channels,
                                channelData: { channel in
                                    let channelMap = runtime.channelMap(for: state, channel: channel)
                                    eval(channelMap)
                                    return channelMap.asArray(Float.self)
                                }
                            )
                            await self?.applyDisplayFrame(frame, projection: selectedProjection)
                            renderedProjection = selectedProjection
                        }
                        try? await Task.sleep(for: .milliseconds(100))
                        continue
                    }

                    let frameStart = ContinuousClock.now
                    state = runtime.step(state)

                    let matterMap = runtime.matterMap(for: state).contiguous()
                    eval(matterMap)
                    let matterData = matterMap.asArray(Float.self)
                    let sample = metricComputer.compute(
                        data: matterData,
                        width: runtimeConfig.sx,
                        height: runtimeConfig.sy
                    )
                    let selectedProjection = await self?.currentProjectionValue() ?? .matter
                    let frame = liveProjectionFrame(
                        matterData: matterData,
                        selectedProjection: selectedProjection,
                        step: state.step,
                        width: runtimeConfig.sx,
                        height: runtimeConfig.sy,
                        channelCount: runtimeConfig.channels
                    ) { channel in
                        let channelMap = runtime.channelMap(for: state, channel: channel)
                        eval(channelMap)
                        return channelMap.asArray(Float.self)
                    }
                    latestMatterData = matterData
                    renderedProjection = selectedProjection

                    var diagnosticImages: DiagnosticImageSet?
                    var diagnosticTelemetry: DiagnosticTelemetry?
                    let diagnosticsEnabled = await self?.diagnosticsEnabledValue() ?? false
                    if diagnosticsEnabled && (state.step == 1 || state.step % diagnosticCadence == 0) {
                        let diagnostics = runtime.diagnostics(for: state)
                        let neighborImage = renderer.renderToImage(mass: diagnostics.neighborSum)
                        let growthImage = renderer.renderToSignedImage(field: diagnostics.growthField)
                        let kernelImage = renderer.renderToImage(mass: diagnostics.kernel)

                        let neighborData = diagnostics.neighborSum.asArray(Float.self)
                        let growthData = diagnostics.growthField.asArray(Float.self)
                        let kernelData = diagnostics.kernel.asArray(Float.self)

                        diagnosticImages = DiagnosticImageSet(
                            field: nil,
                            neighborSum: neighborImage,
                            growthField: growthImage,
                            kernel: kernelImage
                        )
                        diagnosticTelemetry = DiagnosticTelemetry(
                            growthMean: mean(growthData),
                            neighborMean: mean(neighborData),
                            kernelPeak: kernelData.max() ?? 0,
                            kernelCount: diagnostics.kernelCount
                        )
                    }

                    updateDisplayFps(step: state.step)

                    await self?.applyFrame(
                        frame,
                        projection: selectedProjection,
                        projections: projections,
                        runtimeLabel: runtimeLabel,
                        step: state.step,
                        displayFps: displayFps,
                        sample: sample,
                        diagnostics: diagnosticImages,
                        telemetry: diagnosticTelemetry
                    )

                    let elapsed = ContinuousClock.now - frameStart
                    let remaining = targetFrameInterval - elapsed
                    if remaining > .zero { try? await Task.sleep(for: remaining) }
                }
            } catch {
                await self?.applyFailure("Runtime load failed: \(error.localizedDescription)")
            }
        }
    }

    private func pausedValue() -> Bool {
        isPaused
    }

    private func diagnosticsEnabledValue() -> Bool {
        diagnosticsEnabled
    }

    private func currentProjectionValue() -> LabFieldProjection {
        currentProjection
    }

    private func applyFrame(
        _ frame: LeniaFieldFrame,
        projection: LabFieldProjection,
        projections: [LabFieldProjection],
        runtimeLabel: String,
        step: Int,
        displayFps: Double,
        sample: MetricSample,
        diagnostics: DiagnosticImageSet?,
        telemetry: DiagnosticTelemetry?
    ) {
        applyDisplayFrame(frame, projection: projection)
        availableProjections = projections
        self.runtimeLabel = runtimeLabel
        stepCount = step
        self.displayFps = displayFps
        latestSample = sample
        stats = String(format: "Step %d | %.1f FPS", step, displayFps)
        metricHistory.append(sample)
        if let diagnostics {
            diagnosticImages = diagnostics
        }
        if let telemetry {
            diagnosticTelemetry = telemetry
        }
    }

    private func applyDisplayFrame(_ frame: LeniaFieldFrame, projection: LabFieldProjection) {
        guard projection == currentProjection else { return }
        displayFrame = frame
    }

    private func applyFailure(_ message: String) {
        displayFrame = nil
        availableProjections = [.matter]
        runtimeLabel = "Replay failed"
        stats = message
    }
}

func liveProjectionFrame(
    matterData: [Float],
    selectedProjection: LabFieldProjection,
    step: Int,
    width: Int,
    height: Int,
    channelCount: Int,
    channelData: (Int) -> [Float]
) -> LeniaFieldFrame {
    let values: [Float]
    switch selectedProjection {
    case .matter:
        values = matterData
    case .channel(let channel) where channel >= 0 && channel < channelCount:
        values = channelData(channel)
    case .channel:
        values = matterData
    }

    return LeniaFieldFrame(
        step: step,
        width: width,
        height: height,
        bytes: liveFieldBytes(from: values)
    )
}

private func liveFieldBytes(from values: [Float]) -> Data {
    var bytes = [UInt8](repeating: 0, count: values.count)
    for (index, value) in values.enumerated() {
        bytes[index] = UInt8(max(0, min(255, Int(max(0, min(1, value)) * 255.0))))
    }
    return Data(bytes)
}

private struct DiagnosticFramePanel: View {
    let title: String
    let equation: String
    let fieldFrame: LeniaFieldFrame?
    let image: CGImage?
    let palette: LeniaRenderMode?
    let useFluidVisuals: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(StudioPalette.ink)
                Text(equation)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.secondary)
            }

            ZStack {
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [StudioPalette.stageTop, StudioPalette.stageBottom],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )

                if let fieldFrame {
                    LeniaLabStageView(
                        frame: fieldFrame,
                        renderMode: palette ?? .truth,
                        zoom: 1.0,
                        offset: .zero,
                        onTransformChange: { _ in },
                        onPrimaryPoint: { _ in },
                        onSecondaryPoint: { _ in },
                        onHoverPointChange: { _ in },
                        onBrushRadiusDelta: nil
                    )
                    .padding(10)
                } else if let image {
                    diagnosticImage(image)
                        .padding(10)
                } else {
                    ProgressView()
                        .controlSize(.large)
                        .tint(.white)
                }
            }
            .frame(minHeight: 220)
            .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        }
    }

    @ViewBuilder
    private func diagnosticImage(_ image: CGImage) -> some View {
        let baseImage = Image(decorative: image, scale: 1.0)
            .resizable()
            .interpolation(useFluidVisuals ? .high : .none)
            .aspectRatio(1, contentMode: .fit)

        if let palette {
            baseImage.leniaColorEffect(mode: palette)
        } else {
            baseImage
        }
    }
}

private struct EquationCard: View {
    let title: String
    let equation: String
    let details: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(.headline, design: .serif, weight: .semibold))
                .foregroundStyle(StudioPalette.ink)

            Text(equation)
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(StudioPalette.ocean)

            ForEach(details, id: \.self) { detail in
                Text(detail)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(StudioPalette.surfaceSoft)
        )
    }
}

private func format(_ values: [Float], precision: Int) -> String {
    values.map { format($0, precision: precision) }.joined(separator: ", ")
}

private func formatNested(_ values: [[Float]], precision: Int) -> String {
    values.map { "[\($0.map { format($0, precision: precision) }.joined(separator: ", "))]" }
        .joined(separator: " ")
}

private func format(_ value: Float, precision: Int) -> String {
    String(format: "%.\(precision)f", value)
}

private func mean(_ values: [Float]) -> Float {
    guard !values.isEmpty else { return 0 }
    let total = values.reduce(Float(0), +)
    return total / Float(values.count)
}
