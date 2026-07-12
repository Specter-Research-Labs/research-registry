import AppKit
import LeniaArchive
import LeniaCore
import SwiftUI

private typealias CompendiumQuery = CompendiumBrowseQuery
private typealias CompendiumCreature = CompendiumBrowseEntry

private extension CompendiumCreature {
    var liveCreature: LeniaCreature {
        LeniaCreature(
            seed: previewSeed,
            score: score ?? 0,
            params: previewParams,
            sourceNode: ownerId
        )
    }

    var replayReference: StudioReplayReference? {
        guard let baseConfigPath = resolvedReplayBaseConfigPath(for: self) else { return nil }
        return StudioReplayReference(
            baseConfigPath: baseConfigPath,
            searchConfigPath: resolvedReplaySearchConfigPath(for: self),
            runtimeFamily: runtimeFamily
        )
    }

    var studioEntry: StudioCompareEntry {
        StudioCompareEntry.saved(
            creature,
            replayReference: replayReference,
            taxonomy: taxonomy,
            traitLabels: traitLabels,
            runtimeFamily: runtimeFamily,
            sourceMode: sourceMode,
            sourceAlgorithm: sourceAlgorithm,
            runtimeCapabilities: runtimeCapabilities
        )
    }
}

private enum CompendiumViewMode: String, CaseIterable {
    case list = "List"
    case grid = "Grid"
}

private struct CompendiumReplayContract: Sendable {
    let backend: String
    let gridLabel: String
    let channels: Int
    let kernelCount: Int
    let profile: String
    let kernelProfile: String
    let flowSummary: String
    let borderSummary: String
    let connectivityRows: [String]
    let featureSummary: String
    let seed: Int
    let runSteps: Int
    let baseConfigPath: String
    let searchConfigPath: String?
}

@MainActor
private final class CompendiumStore: ObservableObject {
    @Published var creatures: [CompendiumCreature] = []
    @Published var isLoading = false
    @Published var status: String = "No compendium loaded"
    @Published var error: String?
    @Published var warehousePath: String?

    private var loadTask: Task<Void, Never>?
    private var requestID = 0

    deinit {
        loadTask?.cancel()
    }

    func load(path: String, query: CompendiumQuery) {
        loadTask?.cancel()
        requestID += 1
        let activeRequestID = requestID
        let trimmed = path.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            creatures = []
            isLoading = false
            status = "Choose a compendium database"
            error = nil
            warehousePath = nil
            return
        }

        guard FileManager.default.fileExists(atPath: trimmed) else {
            creatures = []
            isLoading = false
            status = "Compendium not found"
            error = "Missing file: \(trimmed)"
            warehousePath = nil
            return
        }

        if compendiumFileSize(at: trimmed) == 0 {
            creatures = []
            isLoading = false
            status = "Compendium is empty"
            error = "DB file exists but is zero bytes: \(trimmed)"
            warehousePath = nil
            return
        }

        isLoading = true
        status = creatures.isEmpty ? "Loading..." : "Refreshing..."
        error = nil
        let siblingWarehouse = defaultWarehousePath(compendiumPath: trimmed)
        warehousePath = FileManager.default.fileExists(atPath: siblingWarehouse) ? siblingWarehouse : nil

        loadTask = Task.detached(priority: .userInitiated) {
            do {
                let results = try browseCompendium(path: trimmed, query: query)
                guard !Task.isCancelled else { return }
                await MainActor.run {
                    guard activeRequestID == self.requestID else { return }
                    self.creatures = results.entries
                    self.status = results.status
                    self.error = results.error
                    self.isLoading = false
                }
            } catch {
                guard !Task.isCancelled else { return }
                await MainActor.run {
                    guard activeRequestID == self.requestID else { return }
                    self.creatures = []
                    self.status = "Failed to load compendium"
                    self.error = error.localizedDescription
                    self.isLoading = false
                }
            }
        }
    }

    private func compendiumFileSize(at path: String) -> Int64? {
        guard
            let attributes = try? FileManager.default.attributesOfItem(atPath: path),
            let fileSize = attributes[.size] as? NSNumber
        else {
            return nil
        }
        return fileSize.int64Value
    }
}

struct CompendiumLayoutView: View {
    @StateObject private var store = CompendiumStore()
    @AppStorage("lastCompendiumPath") private var compendiumPath = ""
    @State private var searchText = ""
    @State private var stableOnly = false
    @State private var catalogFilter: CompendiumCatalogFilter = .active
    @State private var minScoreText = ""
    @State private var limit = 200
    @State private var selectedCreatureIds: Set<UUID> = []
    @State private var showPicker = false
    @State private var viewMode: CompendiumViewMode = .list
    @State private var showComparison = false
    @FocusState private var isSearchFocused: Bool
    @State private var refreshTask: Task<Void, Never>?

    private var selectedCreature: CompendiumCreature? {
        guard let first = selectedCreatureIds.first else { return nil }
        return store.creatures.first(where: { $0.id == first })
    }

    private var selectedComparisonPair: (CompendiumCreature, CompendiumCreature)? {
        guard selectedCreatureIds.count == 2 else { return nil }
        let selected = store.creatures.filter { selectedCreatureIds.contains($0.id) }
        guard selected.count == 2 else { return nil }
        return (selected[0], selected[1])
    }

    private var comparisonPair: (CompendiumCreature, CompendiumCreature)? {
        if let selectedComparisonPair {
            return selectedComparisonPair
        }
        guard store.creatures.count >= 2 else { return nil }
        return (store.creatures[0], store.creatures[1])
    }

    private var comparisonButtonTitle: String {
        selectedComparisonPair == nil ? "Compare Top 2 Results" : "Compare Selected"
    }

    var body: some View {
        NavigationSplitView {
            VStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        TextField("DB path", text: $compendiumPath)
                            .textFieldStyle(.roundedBorder)
                            .font(.caption)
                        Button("Choose") { showPicker = true }
                            .controlSize(.small)
                        Button("Refresh") { refresh() }
                            .controlSize(.small)
                    }

                    HStack(spacing: 6) {
                        TextField("Search", text: $searchText)
                            .textFieldStyle(.roundedBorder)
                            .focused($isSearchFocused)
                        Toggle("Stable", isOn: $stableOnly)
                            .toggleStyle(.switch)
                            .fixedSize()
                    }
                    .font(.caption)

                    HStack(spacing: 6) {
                        TextField("Min", text: $minScoreText)
                            .textFieldStyle(.roundedBorder)
                            .frame(width: 60)
                        Picker("", selection: $catalogFilter) {
                            ForEach(CompendiumCatalogFilter.allCases, id: \.self) { filter in
                                Text(filter.rawValue).tag(filter)
                            }
                        }
                        .pickerStyle(.segmented)
                        .fixedSize()
                        Stepper("Limit \(limit)", value: $limit, in: 25...2000, step: 25)
                            .fixedSize()

                        Spacer()

                        Picker("", selection: $viewMode) {
                            ForEach(CompendiumViewMode.allCases, id: \.self) { mode in
                                Text(mode.rawValue).tag(mode)
                            }
                        }
                        .pickerStyle(.segmented)
                        .fixedSize()
                    }
                    .font(.caption)

                    if comparisonPair != nil {
                        Button(comparisonButtonTitle) {
                            showComparison = true
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                        .accessibilityLabel(comparisonButtonTitle)
                    }
                }
                .padding([.top, .horizontal])

                if store.isLoading {
                    ProgressView()
                        .padding(.vertical, 4)
                } else {
                    VStack(spacing: 6) {
                        Text(store.status)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        if store.warehousePath != nil {
                            Label("Warehouse sibling detected", systemImage: "circle.grid.2x2")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                        if let error = store.error {
                            Label(error, systemImage: "exclamationmark.triangle.fill")
                                .font(.caption2)
                                .foregroundStyle(store.creatures.isEmpty ? StudioPalette.ember : StudioPalette.mutedInk)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 6)
                                .background(
                                    Capsule(style: .continuous)
                                        .fill(store.creatures.isEmpty ? StudioPalette.ember.opacity(0.12) : StudioPalette.surfaceSoft)
                                )
                        }
                    }
                    .padding(.bottom, 4)
                }

                switch viewMode {
                case .list:
                    List(store.creatures, selection: $selectedCreatureIds) { entry in
                        CompendiumRow(entry: entry)
                            .tag(entry.id)
                            .contextMenu { compendiumContextMenu(for: entry) }
                    }
                case .grid:
                    ScrollView {
                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 100))], spacing: 12) {
                            ForEach(store.creatures) { entry in
                                CompendiumGridCell(entry: entry, isSelected: selectedCreatureIds.contains(entry.id))
                                    .onTapGesture {
                                        if NSEvent.modifierFlags.contains(.command) {
                                            if selectedCreatureIds.contains(entry.id) {
                                                selectedCreatureIds.remove(entry.id)
                                            } else if selectedCreatureIds.count < 2 {
                                                selectedCreatureIds.insert(entry.id)
                                            }
                                        } else {
                                            selectedCreatureIds = [entry.id]
                                        }
                                    }
                                    .contextMenu { compendiumContextMenu(for: entry) }
                            }
                        }
                        .padding(.horizontal)
                    }
                }
            }
        } detail: {
            if let entry = selectedCreature {
                CompendiumDetailView(entry: entry)
            } else {
                ContentUnavailableView(
                    "Select an entry",
                    systemImage: "sparkles",
                    description: Text("Choose an entry from the compendium list")
                )
            }
        }
        .onAppear {
            if compendiumPath.isEmpty, let defaultPath = defaultCompendiumPath() {
                compendiumPath = defaultPath
            }
            refresh()
        }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button("Search") { isSearchFocused = true }
                    .keyboardShortcut("f", modifiers: .command)
                    .hidden()
            }
            ToolbarItem(placement: .primaryAction) {
                Button("Toggle View") {
                    viewMode = viewMode == .list ? .grid : .list
                }
                .keyboardShortcut("g", modifiers: .command)
                .hidden()
            }
        }
        .onChange(of: compendiumPath) { _, _ in scheduleRefresh() }
        .onChange(of: searchText) { _, _ in scheduleRefresh() }
        .onChange(of: stableOnly) { _, _ in scheduleRefresh() }
        .onChange(of: catalogFilter) { _, _ in scheduleRefresh() }
        .onChange(of: minScoreText) { _, _ in scheduleRefresh() }
        .onChange(of: limit) { _, _ in scheduleRefresh() }
        .onChange(of: store.creatures.map(\.id)) { _, _ in
            syncSelectionToResults()
        }
        .fileImporter(isPresented: $showPicker, allowedContentTypes: [.data], allowsMultipleSelection: false) { result in
            if case .success(let urls) = result, let url = urls.first {
                compendiumPath = url.path
            }
        }
        .sheet(isPresented: $showComparison) {
            if let pair = comparisonPair {
                NavigationStack {
                    ComparisonView(entries: [
                        pair.0.studioEntry,
                        pair.1.studioEntry
                    ])
                }
                .frame(minWidth: 920, minHeight: 680)
            }
        }
        .onDisappear {
            refreshTask?.cancel()
        }
    }

    @ViewBuilder
    private func compendiumContextMenu(for entry: CompendiumCreature) -> some View {
        CreatureContextMenu(
            seed: entry.previewSeed,
            savedCreature: entry.creature,
            onPreview: { selectedCreatureIds = [entry.id] },
            revealPath: entry.resolvedRunPath
        )
    }

    private func refresh() {
        refreshTask?.cancel()
        let minScore = Float(minScoreText)
        let query = CompendiumQuery(
            search: searchText,
            stableOnly: stableOnly,
            catalogFilter: catalogFilter,
            minScore: minScore,
            limit: limit
        )
        store.load(path: compendiumPath, query: query)
    }

    private func scheduleRefresh(delayMs: Int = 180) {
        refreshTask?.cancel()
        refreshTask = Task {
            try? await Task.sleep(for: .milliseconds(delayMs))
            guard !Task.isCancelled else { return }
            await MainActor.run {
                refresh()
            }
        }
    }

    private func defaultCompendiumPath() -> String? {
        defaultStudioCompendiumPath(anchorFilePath: #filePath)
    }

    private func syncSelectionToResults() {
        let available = Set(store.creatures.map(\.id))
        let retained = selectedCreatureIds.intersection(available)
        if !retained.isEmpty {
            if retained != selectedCreatureIds {
                selectedCreatureIds = retained
            }
            return
        }
        if let first = store.creatures.first?.id {
            selectedCreatureIds = [first]
        } else {
            selectedCreatureIds = []
        }
    }

}

private struct CompendiumGridCell: View {
    let entry: CompendiumCreature
    let isSelected: Bool

    var body: some View {
        VStack(spacing: 4) {
            CreatureThumbnailView(creature: entry.liveCreature, size: 80)

            Text(entry.name)
                .font(.caption2)
                .lineLimit(1)

            if let score = entry.score {
                Text(String(format: "%.3f", score))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(6)
        .background(isSelected ? Color.accentColor.opacity(0.2) : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(isSelected ? Color.accentColor : Color.clear, lineWidth: 2)
        )
    }
}

private struct CompendiumRow: View {
    let entry: CompendiumCreature

    var body: some View {
        HStack {
            CompendiumRowBadge(entry: entry)

            if entry.isStable {
                Image(systemName: "star.fill")
                    .foregroundStyle(.yellow)
                    .font(.caption)
            } else {
                Image(systemName: "circle")
                    .foregroundStyle(.secondary)
                    .font(.caption)
            }

            Image(systemName: "shippingbox.fill")
                .foregroundStyle(Color.secondary)
                .font(.caption)

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(entry.name)
                        .font(.subheadline)
                    if entry.catalogStatus != "active" {
                        Text(entry.catalogStatus.capitalized)
                            .font(.caption2)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(
                                Capsule(style: .continuous)
                                    .fill(qcStatusColor(entry.catalogStatus).opacity(0.14))
                            )
                            .foregroundStyle(qcStatusColor(entry.catalogStatus))
                    }
                }
                Text(entry.displayRun)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                CompendiumTaxonomyLine(entry: entry)
            }

            Spacer()

            if let score = entry.score {
                Text(String(format: "%.4f", score))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                Text("--")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 2)
    }
}

private struct CompendiumRowBadge: View {
    let entry: CompendiumCreature

    private var initial: String {
        let name = entry.name.trimmingCharacters(in: .whitespacesAndNewlines)
        return String(name.first ?? "L").uppercased()
    }

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [StudioPalette.stageTop, StudioPalette.stageBottom],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
            Text(initial)
                .font(.system(.caption, design: .monospaced, weight: .bold))
                .foregroundStyle(.white.opacity(0.92))
        }
        .frame(width: 32, height: 32)
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(entry.isStable ? StudioPalette.ocean.opacity(0.6) : StudioPalette.hairline, lineWidth: 1)
        )
    }
}

private func qcStatusColor(_ status: String) -> Color {
    switch status {
    case "protected":
        return StudioPalette.moss
    case "quarantine":
        return StudioPalette.ember
    default:
        return StudioPalette.ocean
    }
}

private struct CompendiumTaxonomyLine: View {
    let entry: CompendiumCreature

    private var label: String? {
        if let taxonomy = entry.taxonomy {
            let value = taxonomyValue(from: taxonomy)
            if value != "--" {
                return value
            }
        }
        if !entry.traitLabels.isEmpty {
            return entry.traitLabels.prefix(3).joined(separator: " · ")
        }
        let source = [entry.sourceMode, entry.sourceAlgorithm]
            .compactMap { value in
                value?.trimmingCharacters(in: .whitespacesAndNewlines)
            }
            .filter { !$0.isEmpty }
        return source.isEmpty ? nil : source.joined(separator: " · ")
    }

    var body: some View {
        if let label {
            Text(label)
                .font(.caption2)
                .foregroundStyle(StudioPalette.mutedInk)
                .lineLimit(1)
        }
    }
}

private struct CompendiumDetailView: View {
    let entry: CompendiumCreature

    private static let metricsColumns = [
        GridItem(.flexible(), spacing: 8),
        GridItem(.flexible(), spacing: 8)
    ]

    @State private var replayContract: CompendiumReplayContract?
    @State private var replayContractError: String?
    @State private var isLoadingReplayContract = false

    var body: some View {
        let creature = entry.creature
        let studioEntry = entry.studioEntry

        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                LeniaLiveView(
                    creature: entry.liveCreature,
                    savedCreature: creature,
                    replaySource: entry.replayReference
                )
                .frame(minHeight: 280)

                VStack(alignment: .leading, spacing: 12) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(entry.name)
                            .font(.title3)
                            .fontWeight(.semibold)
                        Spacer()
                        if let score = entry.score {
                            Text(String(format: "%.4f", score))
                                .font(.title3)
                                .monospacedDigit()
                                .foregroundStyle(.secondary)
                        }
                    }

                    LazyVGrid(columns: Self.metricsColumns, alignment: .leading, spacing: 6) {
                        MetricCell(label: "Gyration", value: String(format: "%.2f", creature.metrics.gyration))
                        MetricCell(label: "Velocity", value: String(format: "%.3f", creature.metrics.centerVelocity))
                        MetricCell(label: "Mass", value: String(format: "%.2f", creature.metrics.massMean))
                        MetricCell(label: "Complexity", value: String(format: "%.3f", creature.metrics.complexityMean ?? 0))
                        MetricCell(label: "Mass Std", value: String(format: "%.3f", creature.metrics.massStd))
                        MetricCell(label: "Stable", value: creature.metrics.isStable ? "Yes" : "No")
                    }

                    StudioClassificationPanel(entry: studioEntry)
                    StudioComputationPanel(metrics: creature.metrics)

                    DisclosureGroup("Score Breakdown") {
                        ScoreBreakdownView(creature: creature)
                            .padding(.top, 4)
                    }
                    .font(.caption)

                    DisclosureGroup("Genotype") {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("R: \(String(format: "%.1f", creature.genotype.R))")
                            Text("r: \(creature.genotype.r.map { String(format: "%.2f", $0) }.joined(separator: ", "))")
                            Text("m: \(creature.genotype.m.map { String(format: "%.2f", $0) }.joined(separator: ", "))")
                            Text("s: \(creature.genotype.s.map { String(format: "%.3f", $0) }.joined(separator: ", "))")
                            Text("h: \(creature.genotype.h.map { String(format: "%.2f", $0) }.joined(separator: ", "))")
                        }
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .padding(.top, 4)
                    }
                    .font(.caption)

                    DisclosureGroup("Origin") {
                        VStack(alignment: .leading, spacing: 4) {
                            MetadataRow(label: "Run", value: entry.runName)
                            MetadataRow(label: "Host", value: entry.hostId ?? "--")
                            MetadataRow(label: "Campaign", value: entry.campaignId ?? "--")
                            MetadataRow(label: "Recorded", value: entry.recordedAt.isEmpty ? "--" : entry.recordedAt)
                            MetadataRow(label: "Seed", value: String(creature.initialCondition.seed))
                        }
                        .padding(.top, 4)
                    }
                    .font(.caption)

                    DisclosureGroup("Specimen Contract") {
                        VStack(alignment: .leading, spacing: 4) {
                            MetadataRow(label: "Contract", value: "Specimen-backed")
                            MetadataRow(label: "Specimen ID", value: entry.specimenRecordID)
                            MetadataRow(label: "Source Kind", value: entry.specimenSourceKind)
                            MetadataRow(label: "Runtime Family", value: entry.runtimeFamily ?? "--")
                            MetadataRow(label: "Catalog Status", value: entry.catalogStatus)
                            if !entry.qualityFlags.isEmpty {
                                MetadataRow(label: "Quality Flags", value: entry.qualityFlags.joined(separator: ", "))
                            }
                            MetadataRow(
                                label: "Capabilities",
                                value: entry.runtimeCapabilities.isEmpty
                                    ? "--"
                                    : entry.runtimeCapabilities.joined(separator: ", ")
                            )
                            MetadataRow(label: "Source Mode", value: entry.sourceMode ?? "--")
                            MetadataRow(label: "Algorithm", value: entry.sourceAlgorithm ?? "--")
                            if let taxonomy = entry.taxonomy {
                                MetadataRow(
                                    label: "Taxonomy",
                                    value: taxonomyValue(from: taxonomy)
                                )
                            }
                            if !entry.traitLabels.isEmpty {
                                MetadataRow(label: "Traits", value: entry.traitLabels.joined(separator: ", "))
                            }
                        }
                        .padding(.top, 4)
                    }
                    .font(.caption)

                    replayContractSection

                    HStack(spacing: 8) {
                        Button("Copy Config") {
                            CreatureExport.copyConfigToClipboard(for: creature)
                        }
                        Button("Save Config...") {
                            _ = CreatureExport.saveConfigToFile(for: creature)
                        }
                    }
                    .controlSize(.small)
                }
            }
            .padding()
        }
        .task(id: entry.id) {
            await refreshReplayContract()
        }
    }

    @ViewBuilder
    private var replayContractSection: some View {
        if isLoadingReplayContract {
            StudioSurface(
                title: "Replay Contract",
                subtitle: "Loading canonical runtime and topology from the export bundle"
            ) {
                HStack(spacing: 10) {
                    ProgressView()
                        .controlSize(.small)
                    Text("Reading base config...")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        } else if let replayContract {
            StudioSurface(
                title: "Replay Contract",
                subtitle: "Canonical runtime, topology, and field layout from the specimen export bundle"
            ) {
                VStack(alignment: .leading, spacing: 14) {
                    HStack(spacing: 10) {
                        StudioMetricPill(label: "Channels", value: "\(replayContract.channels)", accent: StudioPalette.ocean)
                        StudioMetricPill(label: "Kernels", value: "\(replayContract.kernelCount)", accent: StudioPalette.ember)
                        StudioMetricPill(label: "Seed", value: "\(replayContract.seed)", accent: StudioPalette.moss)
                        Spacer()
                    }

                    Group {
                        StudioKeyValueRow(label: "Backend", value: replayContract.backend)
                        StudioKeyValueRow(label: "Grid", value: replayContract.gridLabel)
                        StudioKeyValueRow(label: "Profile", value: "\(replayContract.profile) · \(replayContract.kernelProfile)")
                        StudioKeyValueRow(label: "Flow", value: replayContract.flowSummary)
                        StudioKeyValueRow(label: "Boundary", value: replayContract.borderSummary)
                        StudioKeyValueRow(label: "Setup", value: replayContract.featureSummary)
                        StudioKeyValueRow(label: "Run", value: "\(replayContract.runSteps) steps")
                    }

                    if !replayContract.connectivityRows.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Connectivity")
                                .font(.system(.caption, design: .monospaced))
                                .foregroundStyle(.secondary)
                            ForEach(replayContract.connectivityRows, id: \.self) { row in
                                Text(row)
                                    .font(.system(.caption, design: .monospaced))
                                    .foregroundStyle(StudioPalette.ink)
                            }
                        }
                    }

                    VStack(alignment: .leading, spacing: 4) {
                        StudioKeyValueRow(label: "Base Config", value: replayContract.baseConfigPath)
                        if let searchConfigPath = replayContract.searchConfigPath {
                            StudioKeyValueRow(label: "Search Config", value: searchConfigPath)
                        }
                    }
                }
            }
        } else if let replayContractError {
            StudioSurface(
                title: "Replay Contract",
                subtitle: "Canonical runtime metadata is unavailable for this specimen"
            ) {
                Text(replayContractError)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func refreshReplayContract() async {
        isLoadingReplayContract = true
        replayContract = nil
        replayContractError = nil

        do {
            let snapshot = try await Task.detached(priority: .userInitiated) {
                try loadReplayContract(for: entry)
            }.value
            replayContract = snapshot
            if snapshot == nil {
                replayContractError = "No resolved replay base config is attached to this specimen yet."
            }
        } catch {
            replayContractError = error.localizedDescription
        }

        isLoadingReplayContract = false
    }
}

private func taxonomyValue(from taxonomy: SpecimenTaxonomyRecord) -> String {
    let labels = [taxonomy.familyID, taxonomy.genusID, taxonomy.speciesID]
        .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
        .filter { !$0.isEmpty }
    return labels.isEmpty ? "--" : labels.joined(separator: " / ")
}

private func loadReplayContract(for entry: CompendiumCreature) throws -> CompendiumReplayContract? {
    let baseConfigPath = resolvedReplayBaseConfigPath(for: entry)
    guard let baseConfigPath else {
        return nil
    }

    let baseData = try Data(contentsOf: URL(fileURLWithPath: baseConfigPath))
    let runtime = try loadRuntimeConfig(from: baseData)
    let decoder = JSONDecoder()
    let baseConfig = try decoder.decode(LeniaBaseConfig.self, from: baseData)
    let searchConfigPath = resolvedReplaySearchConfigPath(for: entry)

    return CompendiumReplayContract(
        backend: runtime.backend.displayName,
        gridLabel: "\(runtime.sx)x\(runtime.sy)",
        channels: runtime.channels,
        kernelCount: runtime.nbK,
        profile: runtime.profile.rawValue,
        kernelProfile: runtime.implementation.kernelProfile,
        flowSummary: "dt \(formatReplayNumber(runtime.dt)) · dd \(runtime.dd) · sigma \(formatReplayNumber(runtime.sigma)) · n \(runtime.n) · thetaA \(formatReplayNumber(runtime.thetaA))",
        borderSummary: "\(runtime.border) boundary",
        connectivityRows: replayConnectivityRows(baseConfig.connectivity),
        featureSummary: replayFeatureSummary(runtime: runtime),
        seed: runtime.initSeed,
        runSteps: runtime.steps,
        baseConfigPath: baseConfigPath,
        searchConfigPath: searchConfigPath
    )
}

private func resolvedReplayBaseConfigPath(for entry: CompendiumCreature) -> String? {
    resolveRunArtifactPath(
        outputRoot: entry.outputRoot,
        runDir: entry.runDir,
        path: entry.baseConfigPath ?? entry.specimenManifest?.replay?.baseConfigPath
    )
}

private func resolvedReplaySearchConfigPath(for entry: CompendiumCreature) -> String? {
    resolveRunArtifactPath(
        outputRoot: entry.outputRoot,
        runDir: entry.runDir,
        path: entry.searchConfigPath ?? entry.specimenManifest?.replay?.searchConfigPath
    )
}

private func replayConnectivityRows(_ matrix: [[Int]]) -> [String] {
    var rows: [String] = []
    for source in matrix.indices {
        for target in matrix[source].indices {
            let count = matrix[source][target]
            if count > 0 {
                rows.append("c\(source) -> c\(target) × \(count)")
            }
        }
    }
    return rows.isEmpty ? ["No active edges"] : rows
}

private func replayFeatureSummary(runtime: LeniaRuntimeConfig) -> String {
    var features: [String] = []
    if runtime.parameterEmbedding.enabled {
        features.append("param field")
    }
    if let chemotaxis = runtime.chemotaxis, chemotaxis.enabled {
        features.append("chem c\(chemotaxis.channel_index)")
    }
    if let obstacleField = runtime.obstacleField, obstacleField.enabled {
        features.append("obstacle c\(obstacleField.channel_index)")
    }
    if let food = runtime.food, food.enabled {
        features.append("food c\(food.channel_index)")
    }
    if let walls = runtime.walls, walls.enabled {
        features.append("walls")
    }
    if runtime.environment != nil {
        features.append("environment")
    }
    if features.isEmpty {
        return "pure field"
    }
    return features.joined(separator: " · ")
}

private func formatReplayNumber(_ value: Float) -> String {
    let rounded = (value * 1000).rounded() / 1000
    if rounded.rounded() == rounded {
        return String(format: "%.0f", rounded)
    }
    if (rounded * 10).rounded() / 10 == rounded {
        return String(format: "%.1f", rounded)
    }
    return String(format: "%.3f", rounded)
}

private struct MetricCell: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption2)
                .foregroundStyle(.tertiary)
            Text(value)
                .font(.caption)
                .monospacedDigit()
        }
    }
}

private struct MetadataRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack {
            Text(label)
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .multilineTextAlignment(.trailing)
        }
        .font(.caption)
    }
}
