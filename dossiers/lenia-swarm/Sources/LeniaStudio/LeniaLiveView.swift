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
                        scrollPolicy: .transformCanvas,
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
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 10) {
                playbackControls
                projectionPicker(compact: false)
                displayModePicker(compact: false)
                optionToggles(compact: false)
                Spacer(minLength: 8)
                statusReadout
            }

            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 8) {
                    playbackControls
                    Spacer(minLength: 8)
                    optionToggles(compact: true)
                }

                HStack(spacing: 8) {
                    projectionPicker(compact: true)
                    displayModePicker(compact: true)
                }

                statusReadout
            }
        }
        .controlSize(.small)
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(.bar)
    }

    private var playbackControls: some View {
        HStack(spacing: 6) {
            Button {
                simulationModel.stepBackward()
            } label: {
                Image(systemName: "backward.frame.fill")
                    .frame(width: 14)
            }
            .buttonStyle(.bordered)
            .disabled(!simulationModel.canStepBackward)
            .help("Previous frame")

            Button(action: { simulationModel.togglePause() }) {
                Image(systemName: simulationModel.isPaused ? "play.fill" : "pause.fill")
                    .frame(width: 14)
            }
            .buttonStyle(.borderedProminent)
            .disabled(simulationModel.frameCount < 2)
            .help(simulationModel.isPaused ? "Play" : "Pause")
            .accessibilityLabel(simulationModel.isPaused ? "Play" : "Pause")

            Button {
                simulationModel.stepForward()
            } label: {
                Image(systemName: "forward.frame.fill")
                    .frame(width: 14)
            }
            .buttonStyle(.bordered)
            .disabled(!simulationModel.canStepForward)
            .help("Next frame")

            Button {
                simulationModel.resetPlayback()
            } label: {
                Image(systemName: "arrow.counterclockwise")
                    .frame(width: 14)
            }
            .buttonStyle(.bordered)
            .disabled(simulationModel.frameCount == 0 || simulationModel.currentFrameIndex == 0)
            .help("Return to first frame")

            Slider(
                value: Binding(
                    get: { simulationModel.playbackProgress },
                    set: { value in simulationModel.seek(toProgress: value) }
                ),
                in: 0...1
            )
            .frame(minWidth: 110, idealWidth: 190, maxWidth: 260)
            .disabled(simulationModel.frameCount < 2)
            .accessibilityLabel("Observation timeline")

            Text(simulationModel.frameCount > 0
                ? "\(simulationModel.currentFrameIndex + 1)/\(simulationModel.frameCount)"
                : "--/--")
                .font(StudioType.dataSmall)
                .foregroundStyle(StudioPalette.mutedInk)
                .monospacedDigit()
                .frame(minWidth: 54, alignment: .trailing)

            Menu {
                ForEach([0.25, 0.5, 1, 2, 4], id: \.self) { rate in
                    Button {
                        simulationModel.setPlaybackRate(rate)
                    } label: {
                        if simulationModel.playbackRate == rate {
                            Label(formatPlaybackRate(rate), systemImage: "checkmark")
                        } else {
                            Text(formatPlaybackRate(rate))
                        }
                    }
                }
            } label: {
                Text(formatPlaybackRate(simulationModel.playbackRate))
                    .monospacedDigit()
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .help("Playback rate")

            Toggle(isOn: Binding(
                get: { simulationModel.isLooping },
                set: { looping in simulationModel.setLooping(looping) }
            )) {
                Image(systemName: "repeat")
            }
            .toggleStyle(.button)
            .help("Loop observation")
        }
    }

    @ViewBuilder
    private func projectionPicker(compact: Bool) -> some View {
        if simulationModel.availableProjections.count > 1 {
            if compact {
                Picker("Field", selection: $fieldProjection) {
                    ForEach(simulationModel.availableProjections) { projection in
                        Text(projection.label).tag(projection)
                    }
                }
                .pickerStyle(.menu)
                .fixedSize()
            } else {
                Picker("Projection", selection: $fieldProjection) {
                    ForEach(simulationModel.availableProjections) { projection in
                        Text(projection.label).tag(projection)
                    }
                }
                .pickerStyle(.segmented)
                .frame(width: min(CGFloat(simulationModel.availableProjections.count) * 110, 420))
            }
        }
    }

    @ViewBuilder
    private func displayModePicker(compact: Bool) -> some View {
        if compact {
            Picker("View", selection: $displayMode) {
                ForEach(LiveDisplayMode.allCases) { mode in
                    Text(mode.rawValue).tag(mode)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .frame(maxWidth: .infinity)
        } else {
            Picker("View", selection: $displayMode) {
                ForEach(LiveDisplayMode.allCases) { mode in
                    Text(mode.rawValue).tag(mode)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .frame(width: 220)
        }
    }

    private func optionToggles(compact: Bool) -> some View {
        HStack(spacing: 6) {
            Toggle(isOn: $useFluidVisuals) {
                if compact {
                    Image(systemName: "drop.fill")
                } else {
                    Label("Fluid", systemImage: "drop.fill")
                }
            }
            .toggleStyle(.button)
            .help("Fluid interpolation")
            .accessibilityLabel("Fluid interpolation")

            if displayMode == .render {
                Toggle(isOn: $showCharts) {
                    if compact {
                        Image(systemName: "chart.xyaxis.line")
                    } else {
                        Label("Charts", systemImage: "chart.xyaxis.line")
                    }
                }
                .toggleStyle(.button)
                .help("Metric charts")
                .accessibilityLabel("Metric charts")
            }
        }
    }

    private var statusReadout: some View {
        HStack(spacing: 8) {
            if simulationModel.runtimeLabel != "Synthetic preview" {
                Text(simulationModel.runtimeLabel)
            }

            if displayMode == .render, zoom > 1.01 {
                Text(String(format: "%.1fx", zoom))
                    .monospacedDigit()
            }

            Text(simulationModel.stats)
                .monospacedDigit()
        }
        .font(StudioType.dataSmall)
        .foregroundStyle(StudioPalette.mutedInk)
        .lineLimit(1)
        .minimumScaleFactor(0.75)
    }

    private func handleKey(_ press: KeyPress) -> KeyPress.Result {
        switch press.characters {
        case " ":
            simulationModel.togglePause()
            return .handled
        case "r":
            simulationModel.resetPlayback()
            return .handled
        case "[":
            simulationModel.stepBackward()
            return .handled
        case "]":
            simulationModel.stepForward()
            return .handled
        case "l":
            simulationModel.setLooping(!simulationModel.isLooping)
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

private struct LiveDiagnosticsRecipe: @unchecked Sendable {
    let runtimeConfig: LeniaRuntimeConfig
    let totalSteps: Int
    let stepStride: Int
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
    @Published var isPaused = true
    @Published var metricHistory = MetricHistory()
    @Published var stepCount = 0
    @Published var displayFps = 0.0
    @Published var availableProjections: [LabFieldProjection] = [.matter]
    @Published var runtimeLabel = "Synthetic preview"
    @Published var currentFrameIndex = 0
    @Published var frameCount = 0
    @Published var playbackRate = 1.0
    @Published var isLooping = true
    @Published var captureProgress = 0.0

    private var captureTask: Task<Void, Never>?
    private var diagnosticsTask: Task<Void, Never>?
    private var playbackTask: Task<Void, Never>?
    private let gridSize = 128
    private var currentProjection: LabFieldProjection = .matter
    private var projectionClips: [LabFieldProjection: StudioObservationClip] = [:]
    private var samples: [MetricSample] = []
    private var diagnosticFrames: [Int: DiagnosticImageSet] = [:]
    private var diagnosticTelemetryFrames: [Int: DiagnosticTelemetry] = [:]
    private var playback: StudioObservationPlayback?
    private var diagnosticsRecipe: LiveDiagnosticsRecipe?
    private var diagnosticsEnabled = false
    private var diagnosticsCaptureComplete = false
    private var sessionGeneration = 0
    private var lastSyncedFrameIndex = -1

    var playbackProgress: Double {
        playback?.progress ?? 0
    }

    var canStepBackward: Bool {
        playback?.canStepBackward == true
    }

    var canStepForward: Bool {
        playback?.canStepForward == true
    }

    var isDiagnosticsCaptureActive: Bool {
        diagnosticsTask != nil
    }

    var isDiagnosticsCaptureComplete: Bool {
        diagnosticsCaptureComplete
    }

    func togglePause() {
        guard let playback else { return }
        do {
            try playback.togglePlayback()
            syncPlaybackState()
        } catch {
            stats = error.localizedDescription
        }
    }

    func setPaused(_ paused: Bool) {
        guard let playback else { return }
        if paused {
            playback.pause()
        } else {
            try? playback.play()
        }
        syncPlaybackState()
    }

    func setDiagnosticsEnabled(_ enabled: Bool) {
        guard diagnosticsEnabled != enabled else { return }
        diagnosticsEnabled = enabled
        if enabled {
            startDiagnosticsCaptureIfNeeded()
        } else {
            diagnosticsTask?.cancel()
        }
    }

    func setFieldProjection(_ projection: LabFieldProjection) {
        currentProjection = projection
        syncPlaybackFrame()
    }

    func seek(toProgress progress: Double) {
        do {
            try playback?.seek(toProgress: progress)
            syncPlaybackState()
        } catch {
            stats = error.localizedDescription
        }
    }

    func stepBackward() {
        do {
            try playback?.stepBackward()
            syncPlaybackState()
        } catch {
            stats = error.localizedDescription
        }
    }

    func stepForward() {
        do {
            try playback?.stepForward()
            syncPlaybackState()
        } catch {
            stats = error.localizedDescription
        }
    }

    func resetPlayback() {
        do {
            playback?.pause()
            try playback?.seek(to: 0)
            syncPlaybackState()
        } catch {
            stats = error.localizedDescription
        }
    }

    func setPlaybackRate(_ rate: Double) {
        do {
            try playback?.setPlaybackRate(rate)
            playbackRate = rate
            syncPlaybackState()
        } catch {
            stats = error.localizedDescription
        }
    }

    func setLooping(_ looping: Bool) {
        playback?.setLooping(looping)
        isLooping = looping
        syncPlaybackState()
    }

    func stop() {
        sessionGeneration &+= 1
        captureTask?.cancel()
        captureTask = nil
        diagnosticsTask?.cancel()
        diagnosticsTask = nil
        playbackTask?.cancel()
        playbackTask = nil
        playback = nil
        diagnosticsRecipe = nil
        diagnosticsCaptureComplete = false
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
        isPaused = true
        metricHistory = MetricHistory()
        stepCount = 0
        displayFps = 0
        availableProjections = [.matter]
        runtimeLabel = replaySource == nil ? "Synthetic preview" : "Loading replay"
        currentFrameIndex = 0
        frameCount = 0
        playbackRate = 1
        isLooping = true
        captureProgress = 0
        lastSyncedFrameIndex = -1
        projectionClips = [:]
        samples = []
        diagnosticFrames = [:]
        diagnosticTelemetryFrames = [:]
        start(creature: creature, savedCreature: savedCreature, replaySource: replaySource)
    }

    func start(
        creature: LeniaCreature,
        savedCreature: SavedCreature? = nil,
        replaySource: StudioReplayReference? = nil
    ) {
        stop()
        let generation = sessionGeneration

        let gridSize = self.gridSize
        captureTask = Task.detached(priority: .userInitiated) { [weak self] in
            var metricComputer = MetricComputer()

            do {
                try await Task.sleep(for: .milliseconds(75))
                try Task.checkCancellation()
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

                try Task.checkCancellation()
                let runtime = FlowLeniaInteractiveSimulator(runtimeConfig: runtimeConfig)
                try Task.checkCancellation()
                var state = runtime.makeInitialState()
                try Task.checkCancellation()
                let projections = LabFieldProjection.options(channelCount: runtimeConfig.channels)
                let totalSteps = min(480, max(240, runtimeConfig.steps / 4))
                let targetFrameCount = 60
                let stepStride = max(1, Int(ceil(Double(totalSteps) / Double(targetFrameCount - 1))))
                let excludedMassChannels = flowExcludedMassChannels(
                    channels: runtimeConfig.channels,
                    chemotaxis: runtimeConfig.chemotaxis,
                    food: runtimeConfig.food
                )
                var framesByProjection = Dictionary(
                    uniqueKeysWithValues: projections.map { ($0, [LeniaFieldFrame]()) }
                )
                var capturedSamples: [MetricSample] = []
                var frameIndex = 0

                while state.step <= totalSteps, !Task.isCancelled {
                    let mass = state.mass.contiguous()
                    eval(mass)
                    let projectionSnapshot = liveProjectionFrames(
                        massData: mass.asArray(Float.self),
                        width: runtimeConfig.sx,
                        height: runtimeConfig.sy,
                        channels: runtimeConfig.channels,
                        excludedMassChannels: excludedMassChannels,
                        step: state.step
                    )
                    let sample = metricComputer.compute(
                        data: projectionSnapshot.matterData,
                        width: runtimeConfig.sx,
                        height: runtimeConfig.sy
                    )
                    let frames = projectionSnapshot.frames
                    for projection in projections {
                        if let frame = frames[projection] {
                            framesByProjection[projection, default: []].append(frame)
                        }
                    }
                    capturedSamples.append(sample)

                    frameIndex += 1
                    if frameIndex == 1 || frameIndex % 10 == 0 {
                        await self?.applyCaptureProgress(
                            frame: frames[.matter],
                            progress: min(1, Double(state.step) / Double(totalSteps)),
                            generation: generation
                        )
                    }
                    guard state.step < totalSteps else { break }
                    state = runtime.step(state, count: min(stepStride, totalSteps - state.step))
                }

                try Task.checkCancellation()
                let clips = try Dictionary(uniqueKeysWithValues: framesByProjection.map { projection, frames in
                    (projection, try StudioObservationClip(frames: frames, nominalFramesPerSecond: 20))
                })
                let runtimeLabel = "\(runtimeLabelPrefix) · \(runtime.effectiveBackend.displayName) · \(runtimeConfig.channels)c/\(runtimeConfig.nbK)k"
                await self?.installCapture(
                    clips: clips,
                    samples: capturedSamples,
                    runtimeLabel: runtimeLabel,
                    diagnosticsRecipe: LiveDiagnosticsRecipe(
                        runtimeConfig: runtimeConfig,
                        totalSteps: totalSteps,
                        stepStride: stepStride
                    ),
                    generation: generation
                )
            } catch {
                await self?.applyFailure(
                    "Runtime load failed: \(error.localizedDescription)",
                    generation: generation
                )
            }
        }
    }

    private func applyCaptureProgress(
        frame: LeniaFieldFrame?,
        progress: Double,
        generation: Int
    ) {
        guard generation == sessionGeneration else { return }
        displayFrame = frame ?? displayFrame
        captureProgress = progress
        stats = "Preparing trajectory · \(Int((progress * 100).rounded()))%"
    }

    private func installCapture(
        clips: [LabFieldProjection: StudioObservationClip],
        samples: [MetricSample],
        runtimeLabel: String,
        diagnosticsRecipe: LiveDiagnosticsRecipe,
        generation: Int
    ) {
        guard generation == sessionGeneration, let matterClip = clips[.matter] else { return }
        do {
            let playback = try StudioObservationPlayback(source: matterClip, isLooping: true)
            try playback.play()
            self.playback = playback
            projectionClips = clips
            self.samples = samples
            self.diagnosticsRecipe = diagnosticsRecipe
            diagnosticsCaptureComplete = false
            availableProjections = clips.keys.sorted { $0.id < $1.id }
            self.runtimeLabel = runtimeLabel
            captureProgress = 1
            frameCount = matterClip.frameCount
            syncPlaybackState()
            startPlaybackClock(generation: generation)
            startDiagnosticsCaptureIfNeeded()
            captureTask = nil
        } catch {
            applyFailure(error.localizedDescription, generation: generation)
        }
    }

    private func startDiagnosticsCaptureIfNeeded() {
        guard diagnosticsEnabled,
              !diagnosticsCaptureComplete,
              diagnosticsTask == nil,
              let recipe = diagnosticsRecipe else {
            return
        }
        let generation = sessionGeneration
        diagnosticsTask = Task.detached(priority: .utility) { [weak self] in
            let renderer = LeniaRenderer()
            let runtime = FlowLeniaInteractiveSimulator(runtimeConfig: recipe.runtimeConfig)
            var state = runtime.makeInitialState()
            var frameIndex = 0

            while state.step <= recipe.totalSteps, !Task.isCancelled {
                if frameIndex % 12 == 0 {
                    let diagnostics = runtime.diagnostics(for: state)
                    let neighborImage = renderer.renderToImage(mass: diagnostics.neighborSum)
                    let growthImage = renderer.renderToSignedImage(field: diagnostics.growthField)
                    let kernelImage = renderer.renderToImage(mass: diagnostics.kernel)
                    let neighborData = diagnostics.neighborSum.asArray(Float.self)
                    let growthData = diagnostics.growthField.asArray(Float.self)
                    let kernelData = diagnostics.kernel.asArray(Float.self)
                    await self?.applyDiagnosticCapture(
                        frameIndex: frameIndex,
                        images: DiagnosticImageSet(
                            field: nil,
                            neighborSum: neighborImage,
                            growthField: growthImage,
                            kernel: kernelImage
                        ),
                        telemetry: DiagnosticTelemetry(
                            growthMean: mean(growthData),
                            neighborMean: mean(neighborData),
                            kernelPeak: kernelData.max() ?? 0,
                            kernelCount: diagnostics.kernelCount
                        ),
                        generation: generation
                    )
                }
                frameIndex += 1
                guard state.step < recipe.totalSteps else { break }
                state = runtime.step(
                    state,
                    count: min(recipe.stepStride, recipe.totalSteps - state.step)
                )
            }

            await self?.finishDiagnosticsCapture(
                generation: generation,
                completed: !Task.isCancelled
            )
        }
    }

    private func applyDiagnosticCapture(
        frameIndex: Int,
        images: DiagnosticImageSet,
        telemetry: DiagnosticTelemetry,
        generation: Int
    ) {
        guard generation == sessionGeneration, diagnosticsEnabled else { return }
        diagnosticFrames[frameIndex] = images
        diagnosticTelemetryFrames[frameIndex] = telemetry
        syncPlaybackDiagnostics()
    }

    private func finishDiagnosticsCapture(generation: Int, completed: Bool) {
        guard generation == sessionGeneration else { return }
        diagnosticsTask = nil
        diagnosticsCaptureComplete = completed
        if diagnosticsEnabled, !completed {
            startDiagnosticsCaptureIfNeeded()
        }
    }

    private func startPlaybackClock(generation: Int) {
        playbackTask?.cancel()
        playbackTask = Task { [weak self] in
            var previous = ContinuousClock.now
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(16))
                guard let self, self.sessionGeneration == generation, let playback = self.playback else { return }
                let now = ContinuousClock.now
                let elapsed = now - previous
                previous = now
                do {
                    try playback.advance(by: elapsed)
                    self.syncPlaybackState()
                } catch {
                    self.stats = error.localizedDescription
                    playback.pause()
                    self.syncPlaybackState()
                }
            }
        }
    }

    private func syncPlaybackState() {
        guard let playback else { return }
        let frameChanged = playback.currentFrameIndex != lastSyncedFrameIndex
        if currentFrameIndex != playback.currentFrameIndex { currentFrameIndex = playback.currentFrameIndex }
        if frameCount != playback.frameCount { frameCount = playback.frameCount }
        if playbackRate != playback.playbackRate { playbackRate = playback.playbackRate }
        if isLooping != playback.isLooping { isLooping = playback.isLooping }
        if isPaused == playback.isPlaying { isPaused = !playback.isPlaying }
        let nextDisplayFps = playback.nominalFramesPerSecond * playback.playbackRate
        if displayFps != nextDisplayFps { displayFps = nextDisplayFps }
        if stepCount != playback.currentStep { stepCount = playback.currentStep }
        stats = "Frame \(playback.currentFrameIndex + 1)/\(playback.frameCount) · Step \(playback.currentStep) · \(formatPlaybackRate(playback.playbackRate))"
        guard frameChanged else { return }
        lastSyncedFrameIndex = playback.currentFrameIndex
        syncPlaybackFrame()
        if samples.indices.contains(currentFrameIndex) {
            latestSample = samples[currentFrameIndex]
            var history = MetricHistory()
            let lowerBound = max(0, currentFrameIndex - MetricHistory.capacity + 1)
            for sample in samples[lowerBound...currentFrameIndex] {
                history.append(sample)
            }
            metricHistory = history
        }
        syncPlaybackDiagnostics()
    }

    private func syncPlaybackDiagnostics() {
        let diagnosticIndex = diagnosticFrames.keys
            .filter { $0 <= currentFrameIndex }
            .max()
            ?? diagnosticFrames.keys.min()
        if let diagnosticIndex {
            diagnosticImages = diagnosticFrames[diagnosticIndex]
            diagnosticTelemetry = diagnosticTelemetryFrames[diagnosticIndex]
        }
    }

    private func syncPlaybackFrame() {
        guard let playback else { return }
        let clip = projectionClips[currentProjection] ?? projectionClips[.matter]
        displayFrame = try? clip?.frame(at: playback.currentFrameIndex)
    }

    private func applyFailure(_ message: String, generation: Int) {
        guard generation == sessionGeneration else { return }
        displayFrame = nil
        projectionClips = [:]
        availableProjections = [.matter]
        runtimeLabel = "Replay failed"
        stats = message
        isPaused = true
        playback = nil
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

private func formatPlaybackRate(_ rate: Double) -> String {
    rate == rate.rounded()
        ? "\(Int(rate))×"
        : String(format: "%.2g×", rate)
}

func liveProjectionFrames(
    massData: [Float],
    width: Int,
    height: Int,
    channels: Int,
    excludedMassChannels: Set<Int>,
    step: Int
) -> (matterData: [Float], frames: [LabFieldProjection: LeniaFieldFrame]) {
    let cellCount = width * height
    precondition(channels > 0 && massData.count == cellCount * channels)

    var matterData = [Float](repeating: 0, count: cellCount)
    var matterBytes = [UInt8](repeating: 0, count: cellCount)
    var channelBytes = channels > 1
        ? Array(repeating: [UInt8](repeating: 0, count: cellCount), count: channels)
        : []

    for cell in 0..<cellCount {
        let base = cell * channels
        var matter: Float = 0
        for channel in 0..<channels {
            let value = massData[base + channel]
            if channels > 1 {
                channelBytes[channel][cell] = liveFieldByte(value)
            }
            if !excludedMassChannels.contains(channel) {
                matter += value
            }
        }
        matterData[cell] = matter
        matterBytes[cell] = liveFieldByte(matter)
    }

    var frames: [LabFieldProjection: LeniaFieldFrame] = [
        .matter: LeniaFieldFrame(
            step: step,
            width: width,
            height: height,
            bytes: Data(matterBytes)
        )
    ]
    for channel in channelBytes.indices {
        frames[.channel(channel)] = LeniaFieldFrame(
            step: step,
            width: width,
            height: height,
            bytes: Data(channelBytes[channel])
        )
    }
    return (matterData, frames)
}

private func liveFieldByte(_ value: Float) -> UInt8 {
    UInt8(max(0, min(255, Int(max(0, min(1, value)) * 255))))
}

private func liveFieldBytes(from values: [Float]) -> Data {
    Data(values.map(liveFieldByte))
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
                RoundedRectangle(cornerRadius: StudioLayout.panelRadius, style: .continuous)
                    .fill(StudioPalette.stageBottom)

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
            .clipShape(RoundedRectangle(cornerRadius: StudioLayout.panelRadius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: StudioLayout.panelRadius, style: .continuous)
                    .stroke(.white.opacity(0.10), lineWidth: StudioLayout.hairline)
            }
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
                .font(StudioType.panelTitle)
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
            RoundedRectangle(cornerRadius: StudioLayout.panelRadius, style: .continuous)
                .fill(StudioPalette.surfaceSoft.opacity(0.66))
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
