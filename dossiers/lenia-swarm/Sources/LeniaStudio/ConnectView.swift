import Dispatch
import LeniaCore
import SwiftUI
import UniformTypeIdentifiers

struct ConnectView: View {
    @ObservedObject var node: LeniaNode
    @EnvironmentObject var appState: AppState
    @Environment(\.dismiss) var dismiss

    @AppStorage("lastControllerIP") private var controllerIP = "127.0.0.1"
    @AppStorage("lastControllerPort") private var controllerPort = 7337
    @AppStorage("lastBindPort") private var bindPort = 7338
    @AppStorage("lastBaseConfigPath") private var baseConfigPath = ""
    @AppStorage("lastSearchConfigPath") private var searchConfigPath = ""
    @AppStorage("lastOutputRootPath") private var outputRootPath = ""
    @AppStorage("lastCompendiumPath") private var compendiumPath = ""
    @AppStorage("lastConfigPresetId") private var configPresetId = "custom"

    @State private var mode: Mode = .host
    @State private var showBasePicker = false
    @State private var showSearchPicker = false
    @State private var showOutputPicker = false
    @State private var showCompendiumPicker = false
    @State private var presetError: String?
    @State private var isApplyingPreset = false

    enum Mode: String, CaseIterable, Identifiable {
        case host = "Host"
        case worker = "Worker"
        case compendium = "Compendium"

        var id: Self { self }

        var title: String {
            switch self {
            case .host: return "Host The Cluster"
            case .worker: return "Join As Worker"
            case .compendium: return "Open Compendium"
            }
        }

        var systemImage: String {
            switch self {
            case .host: return "server.rack"
            case .worker: return "sparkles.tv"
            case .compendium: return "books.vertical"
            }
        }

        var subtitle: String {
            switch self {
            case .host:
                return "Launch controller mode, pick a preset, and route outputs to a run directory."
            case .worker:
                return "Attach to an existing controller and contribute search, qualification, and arena participation."
            case .compendium:
                return "Browse an indexed SQLite compendium without connecting to a live cluster."
            }
        }
    }

    private struct ConfigPreset: Identifiable {
        let id: String
        let name: String
        let baseResource: String
        let searchResource: String
        let summary: String
    }

    private let configPresets: [ConfigPreset] = [
        ConfigPreset(
            id: "paper-1c-random",
            name: "Paper 1c 128 - Random",
            baseResource: "paper_base_1c_128",
            searchResource: "paper_search_random",
            summary: "Baseline single-channel search with the paper grid and random score emphasis."
        ),
        ConfigPreset(
            id: "paper-1c-complexity",
            name: "Paper 1c 128 - Complexity",
            baseResource: "paper_base_1c_128",
            searchResource: "search_complexity",
            summary: "Bias the search toward richer morphology and more structurally interesting discoveries."
        ),
        ConfigPreset(
            id: "paper-1c-activity",
            name: "Paper 1c 128 - Activity",
            baseResource: "paper_base_1c_128",
            searchResource: "search_activity",
            summary: "Favor more animated motion regimes while keeping the paper-scale topology."
        ),
        ConfigPreset(
            id: "paper-2c-random",
            name: "Paper 2c 128 - Random",
            baseResource: "paper_base_2c_128",
            searchResource: "paper_search_random",
            summary: "Two-channel paper configuration for broader dynamics at the same grid scale."
        )
    ]

    private var selectedPreset: ConfigPreset? {
        configPresets.first(where: { $0.id == configPresetId })
    }

    var body: some View {
        GeometryReader { proxy in
            VStack(spacing: 0) {
                header

                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        StudioSurface(title: "Choose A Role", subtitle: "LeniaStudio can host the session, contribute worker compute, or inspect a saved compendium.") {
                            rolePicker(compact: proxy.size.width < 900)
                        }

                        StudioSurface(title: "Connection", subtitle: connectionSubtitle) {
                            connectionContent
                        }

                        if mode == .host {
                            StudioSurface(title: "Sweep Preset", subtitle: "Preset bundles keep the controller path explicit while reducing setup friction.") {
                                hostConfigContent
                            }
                        }

                        if mode == .compendium {
                            StudioSurface(title: "Compendium", subtitle: "Point the studio at an indexed SQLite database.") {
                                compendiumContent
                            }
                        }

                        StudioSurface(title: "Readiness", subtitle: validationMessage) {
                            HStack(spacing: 12) {
                                Image(systemName: validationSystemImage)
                                    .foregroundStyle(validationColor)
                                Text(validationMessage)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Spacer()
                            }
                        }
                    }
                    .padding(20)
                }

                footer(compact: proxy.size.width < 820)
            }
        }
        .background(
            StudioSceneBackground()
        )
        .onAppear {
            if outputRootPath.isEmpty, let defaultPath = defaultOutputRootPath() {
                outputRootPath = defaultPath
            }
            if compendiumPath.isEmpty, let defaultPath = defaultCompendiumPath() {
                compendiumPath = defaultPath
            }
            if configPresetId != "custom" {
                applyPresetIfNeeded(configPresetId)
            }
        }
        .onChange(of: configPresetId) { _, newValue in
            applyPresetIfNeeded(newValue)
        }
        .onChange(of: baseConfigPath) { _, _ in
            if !isApplyingPreset {
                configPresetId = "custom"
            }
        }
        .onChange(of: searchConfigPath) { _, _ in
            if !isApplyingPreset {
                configPresetId = "custom"
            }
        }
        .fileImporter(isPresented: $showBasePicker, allowedContentTypes: [.json], allowsMultipleSelection: false) { result in
            if case .success(let urls) = result, let url = urls.first {
                baseConfigPath = url.path
            }
        }
        .fileImporter(isPresented: $showSearchPicker, allowedContentTypes: [.json], allowsMultipleSelection: false) { result in
            if case .success(let urls) = result, let url = urls.first {
                searchConfigPath = url.path
            }
        }
        .fileImporter(isPresented: $showOutputPicker, allowedContentTypes: [.folder], allowsMultipleSelection: false) { result in
            if case .success(let urls) = result, let url = urls.first {
                outputRootPath = url.path
            }
        }
        .fileImporter(isPresented: $showCompendiumPicker, allowedContentTypes: [.data], allowsMultipleSelection: false) { result in
            if case .success(let urls) = result, let url = urls.first {
                compendiumPath = url.path
            }
        }
        .frame(minWidth: 700, minHeight: 620)
    }

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text("LeniaStudio Session Setup")
                    .font(.system(.title2, design: .serif, weight: .semibold))
                Text("Guided entry for host, worker, and compendium workflows.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button("Cancel") { dismiss() }
                .buttonStyle(.bordered)
        }
        .padding(20)
        .background(.thinMaterial)
    }

    private func rolePicker(compact: Bool) -> some View {
        Group {
            if compact {
                VStack(spacing: 14) {
                    roleCards
                }
            } else {
                HStack(spacing: 14) {
                    roleCards
                }
            }
        }
    }

    private var roleCards: some View {
        ForEach(Mode.allCases) { option in
            Button {
                mode = option
            } label: {
                VStack(alignment: .leading, spacing: 10) {
                    Label(option.title, systemImage: option.systemImage)
                        .font(.headline)
                        .foregroundStyle(StudioPalette.ink)
                    Text(option.subtitle)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(
                    RoundedRectangle(cornerRadius: 22, style: .continuous)
                        .fill(mode == option ? StudioPalette.surfaceRaised : StudioPalette.surfaceSoft)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 22, style: .continuous)
                        .stroke(mode == option ? StudioPalette.ember.opacity(0.6) : StudioPalette.hairline, lineWidth: 1)
                )
            }
            .buttonStyle(.plain)
        }
    }

    @ViewBuilder
    private var connectionContent: some View {
        switch mode {
        case .host:
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 12) {
                    labeledNumberField("Bind Port", value: $controllerPort, width: 110)
                    Spacer()
                }
                Text("Workers will connect to this machine on port \(controllerPort). Pick an output root so every run captures provenance in one obvious place.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        case .worker:
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 12) {
                    labeledTextField("Controller IP", text: $controllerIP, width: 180)
                    labeledNumberField("Controller Port", value: $controllerPort, width: 110)
                    labeledNumberField("Local Port", value: $bindPort, width: 110)
                }

                HStack(spacing: 8) {
                    Button("Use Loopback") {
                        controllerIP = "127.0.0.1"
                        controllerPort = 7337
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    Text("Recent endpoint: \(controllerIP):\(controllerPort)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Text("Worker mode keeps the cluster workflow explicit: join a live controller, contribute search, inspect results, and opt into sweeps or arena play.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        case .compendium:
            Text("Compendium mode is offline. No cluster connection is attempted.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private var hostConfigContent: some View {
        VStack(alignment: .leading, spacing: 14) {
            Picker("Preset", selection: $configPresetId) {
                Text("Custom (manual paths)").tag("custom")
                ForEach(configPresets) { preset in
                    Text(preset.name).tag(preset.id)
                }
            }
            .pickerStyle(.menu)

            if let selectedPreset {
                Text(selectedPreset.summary)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                Text("Pick manual paths if you want full control over the base and search config pair.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            VStack(spacing: 10) {
                pathRow(label: "Base Config", path: $baseConfigPath) { showBasePicker = true }
                pathRow(label: "Search Config", path: $searchConfigPath) { showSearchPicker = true }
                pathRow(label: "Output Root", path: $outputRootPath) { showOutputPicker = true }
            }

            if let presetError {
                Text(presetError)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        }
    }

    private var compendiumContent: some View {
        VStack(alignment: .leading, spacing: 14) {
            pathRow(label: "Compendium DB", path: $compendiumPath) { showCompendiumPicker = true }
            Text("Choose a `compendium.sqlite` created by the indexer or the studio output pipeline.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private func footer(compact: Bool) -> some View {
        Group {
            if compact {
                VStack(alignment: .leading, spacing: 12) {
                    Button("Cancel") { dismiss() }
                        .buttonStyle(.bordered)
                    Button(action: startNode) {
                        Label(startButtonLabel, systemImage: mode.systemImage)
                            .font(.headline)
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .disabled(!isReady)
                    .keyboardShortcut(.defaultAction)
                }
            } else {
                HStack {
                    Button("Cancel") { dismiss() }
                        .buttonStyle(.bordered)
                    Spacer()
                    Button(action: startNode) {
                        Label(startButtonLabel, systemImage: mode.systemImage)
                            .font(.headline)
                            .frame(minWidth: 220)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .disabled(!isReady)
                    .keyboardShortcut(.defaultAction)
                }
            }
        }
        .padding(20)
        .background(.thinMaterial)
    }

    private func labeledTextField(_ label: String, text: Binding<String>, width: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            TextField(label, text: text)
                .textFieldStyle(.roundedBorder)
                .frame(width: width)
        }
    }

    private func labeledNumberField(_ label: String, value: Binding<Int>, width: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            TextField(label, value: value, format: .number.grouping(.never))
                .textFieldStyle(.roundedBorder)
                .frame(width: width)
        }
    }

    private func pathRow(label: String, path: Binding<String>, onChoose: @escaping () -> Void) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            HStack(spacing: 10) {
                TextField("Path", text: path)
                    .textFieldStyle(.roundedBorder)
                Button("Choose", action: onChoose)
                    .buttonStyle(.bordered)
            }
        }
    }

    private var connectionSubtitle: String {
        switch mode {
        case .host:
            return "This machine becomes the controller and run provenance root."
        case .worker:
            return "Point the worker at a live controller and reserve a local listening port."
        case .compendium:
            return "Offline mode for browsing indexed runs."
        }
    }

    private var validationMessage: String {
        if let presetError {
            return presetError
        }

        switch mode {
        case .host:
            if outputRootPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return "Host mode needs an output root before it can start."
            }
            if baseConfigPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != searchConfigPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return "Provide both base and search config paths or leave both empty to use defaults."
            }
            return "Ready to start a controller-backed studio session."
        case .worker:
            if controllerIP.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return "Worker mode needs a controller IP."
            }
            return "Ready to join \(controllerIP):\(controllerPort) as a worker."
        case .compendium:
            if compendiumPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return "Choose a compendium database to open offline."
            }
            return "Ready to open the selected compendium."
        }
    }

    private var validationColor: Color {
        if !isReady {
            return presetError != nil ? .red : .orange
        }

        return StudioPalette.moss
    }

    private var isReady: Bool {
        if presetError != nil {
            return false
        }

        switch mode {
        case .host:
            return !outputRootPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                && (baseConfigPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == searchConfigPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        case .worker:
            return !controllerIP.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        case .compendium:
            return !compendiumPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
    }

    private var validationSystemImage: String {
        isReady ? "checkmark.circle.fill" : "exclamationmark.triangle.fill"
    }

    private func startNode() {
        Task {
            if mode == .host {
                let basePath = baseConfigPath.trimmingCharacters(in: .whitespacesAndNewlines)
                let searchPath = searchConfigPath.trimmingCharacters(in: .whitespacesAndNewlines)
                let outputRoot = outputRootPath.trimmingCharacters(in: .whitespacesAndNewlines)
                await node.start(config: NodeConfig(
                    bindHost: "0.0.0.0",
                    bindPort: controllerPort,
                    mode: .host,
                    baseConfigPath: basePath.isEmpty ? nil : basePath,
                    searchConfigPath: searchPath.isEmpty ? nil : searchPath,
                    outputRootPath: outputRoot.isEmpty ? nil : outputRoot
                ))
            } else if mode == .worker {
                await node.start(config: NodeConfig(
                    bindHost: "0.0.0.0",
                    bindPort: bindPort,
                    mode: .join(controllerHost: controllerIP, controllerPort: controllerPort)
                ))
            } else {
                let path = compendiumPath.trimmingCharacters(in: .whitespacesAndNewlines)
                if path.isEmpty {
                    appState.connectionState = .error("Compendium DB path required")
                    return
                }
                appState.connectionState = .connected(role: .compendium)
            }
            dismiss()
        }
    }

    private var startButtonLabel: String {
        switch mode {
        case .host:
            return "Start Host"
        case .worker:
            return "Join Worker Session"
        case .compendium:
            return "Open Compendium"
        }
    }

    private func defaultOutputRootPath() -> String? {
#if DEBUG
        let sourceURL = URL(fileURLWithPath: #filePath).standardizedFileURL
        if let swarmRoot = findLeniaSwarmRoot(from: sourceURL) {
            return swarmRoot.appendingPathComponent("outputs").path
        }
#endif

        if let supportRoot = localSupportRoot() {
            return supportRoot.appendingPathComponent("outputs").path
        }

        return nil
    }

    private func defaultCompendiumPath() -> String? {
        defaultStudioCompendiumPath(anchorFilePath: #filePath)
    }

    private func localSupportRoot() -> URL? {
        defaultStudioSupportRoot()
    }

    private func applyPresetIfNeeded(_ presetId: String) {
        guard presetId != "custom" else {
            presetError = nil
            return
        }
        guard let preset = configPresets.first(where: { $0.id == presetId }) else {
            presetError = "Unknown preset: \(presetId)"
            return
        }
        guard let basePath = bundlePresetPath(preset.baseResource) else {
            presetError = "Preset base config not found: \(preset.baseResource).json"
            return
        }
        guard let searchPath = bundlePresetPath(preset.searchResource) else {
            presetError = "Preset search config not found: \(preset.searchResource).json"
            return
        }
        presetError = nil
        isApplyingPreset = true
        baseConfigPath = basePath
        searchConfigPath = searchPath
        DispatchQueue.main.async {
            isApplyingPreset = false
        }
    }

    private func bundlePresetPath(_ resourceName: String) -> String? {
        Bundle.module.url(forResource: resourceName, withExtension: "json", subdirectory: "Presets")?.path
    }
}
