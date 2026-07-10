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

    var browserClassification: String? {
        if let taxonomy {
            let value = taxonomyValue(from: taxonomy)
            if value != "--" {
                return value
            }
        }
        if !traitLabels.isEmpty {
            return traitLabels.prefix(3).joined(separator: " · ")
        }
        let source = [sourceMode, sourceAlgorithm]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        return source.isEmpty ? nil : source.joined(separator: " · ")
    }
}

private enum CompendiumViewMode: String, CaseIterable {
    case list = "List"
    case grid = "Grid"
    case morphospace = "Map"
}

func reconciledCompendiumSelection(
    selectedIDs: Set<UUID>,
    displayedIDs: [UUID]
) -> Set<UUID> {
    let available = Set(displayedIDs)
    let retained = selectedIDs.intersection(available)
    if !retained.isEmpty {
        return retained
    }
    return displayedIDs.first.map { [$0] } ?? []
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
    @Published var nextCursor: CompendiumBrowseCursor?

    private var loadTask: Task<Void, Never>?
    private var browseCancellation: CompendiumBrowseCancellation?
    private var requestID = 0

    deinit {
        browseCancellation?.cancel()
        loadTask?.cancel()
    }

    func load(path: String, query: CompendiumQuery, appending: Bool = false) {
        browseCancellation?.cancel()
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
            nextCursor = nil
            return
        }

        guard FileManager.default.fileExists(atPath: trimmed) else {
            creatures = []
            isLoading = false
            status = "Compendium not found"
            error = "Missing file: \(trimmed)"
            warehousePath = nil
            nextCursor = nil
            return
        }

        if compendiumFileSize(at: trimmed) == 0 {
            creatures = []
            isLoading = false
            status = "Compendium is empty"
            error = "DB file exists but is zero bytes: \(trimmed)"
            warehousePath = nil
            nextCursor = nil
            return
        }

        isLoading = true
        status = appending ? "Loading more..." : (creatures.isEmpty ? "Loading..." : "Refreshing...")
        error = nil
        let siblingWarehouse = defaultWarehousePath(compendiumPath: trimmed)
        warehousePath = FileManager.default.fileExists(atPath: siblingWarehouse) ? siblingWarehouse : nil
        let cancellation = CompendiumBrowseCancellation()
        browseCancellation = cancellation

        loadTask = Task.detached(priority: .userInitiated) {
            do {
                let results = try await withTaskCancellationHandler {
                    try browseCompendium(
                        path: trimmed,
                        query: query,
                        cancellation: cancellation
                    )
                } onCancel: {
                    cancellation.cancel()
                }
                guard !Task.isCancelled else { return }
                await MainActor.run {
                    guard activeRequestID == self.requestID else { return }
                    if appending {
                        let known = Set(self.creatures.map(\.id))
                        self.creatures.append(contentsOf: results.entries.filter { !known.contains($0.id) })
                    } else {
                        self.creatures = results.entries
                    }
                    self.status = results.status
                    self.error = results.error
                    self.nextCursor = results.nextCursor
                    self.isLoading = false
                }
            } catch CompendiumBrowseError.cancelled {
                return
            } catch {
                guard !Task.isCancelled else { return }
                await MainActor.run {
                    guard activeRequestID == self.requestID else { return }
                    if !appending {
                        self.creatures = []
                        self.nextCursor = nil
                    }
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
    @EnvironmentObject private var appState: AppState
    @StateObject private var store = CompendiumStore()
    @AppStorage("lastCompendiumPath") private var compendiumPath = ""
    @AppStorage("studioFavoriteSpecimenIDs") private var favoriteSpecimenIDs = ""
    @State private var searchText = ""
    @State private var stableOnly = false
    @State private var catalogFilter: CompendiumCatalogFilter = .active
    @State private var minScoreText = ""
    @State private var limit = 200
    @State private var selectedCreatureIds: Set<UUID> = []
    @State private var showPicker = false
    @State private var viewMode: CompendiumViewMode = .list
    @State private var showComparison = false
    @State private var showCreateSweep = false
    @State private var favoritesOnly = false
    @State private var showSourceControls = false
    @FocusState private var isSearchFocused: Bool
    @State private var refreshTask: Task<Void, Never>?

    private var favoriteIDs: Set<UUID> {
        Set(favoriteSpecimenIDs.split(separator: ",").compactMap { UUID(uuidString: String($0)) })
    }

    private var unifiedEntries: [CompendiumCreature] {
        studioUnifiedLibraryEntries(
            local: appState.library,
            remote: store.creatures,
            replayReference: appState.replayReference(for:)
        )
    }

    private var displayedEntries: [CompendiumCreature] {
        unifiedEntries.filter { entry in
            if favoritesOnly, !favoriteIDs.contains(entry.id) {
                return false
            }
            guard entry.runId == "local-library" else { return true }
            guard catalogFilter != .quarantine else { return false }
            return studioLibraryEntryMatches(
                entry,
                search: searchText,
                stableOnly: stableOnly,
                minimumScore: Float(minScoreText),
                favoritesOnly: favoritesOnly,
                favoriteIDs: favoriteIDs
            )
        }
    }

    private var connectedAsHost: Bool {
        if case .connected(role: .host) = appState.connectionState {
            return true
        }
        return false
    }

    private var selectedCreature: CompendiumCreature? {
        displayedEntries.first(where: { selectedCreatureIds.contains($0.id) })
    }

    private var selectedComparisonEntries: [CompendiumCreature]? {
        guard (2...4).contains(selectedCreatureIds.count) else { return nil }
        let selected = displayedEntries.filter { selectedCreatureIds.contains($0.id) }
        guard selected.count == selectedCreatureIds.count else { return nil }
        return selected
    }

    private var comparisonEntries: [CompendiumCreature] {
        if let selectedComparisonEntries {
            return selectedComparisonEntries
        }
        return Array(displayedEntries.prefix(2))
    }

    private var comparisonButtonTitle: String {
        selectedComparisonEntries == nil ? "Compare Top 2" : "Compare \(selectedComparisonEntries?.count ?? 2) Selected"
    }

    private var sourceDisplayName: String {
        let trimmed = compendiumPath.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return "No indexed source" }
        return URL(fileURLWithPath: trimmed).lastPathComponent
    }

    private var isInitialLoading: Bool {
        store.isLoading && unifiedEntries.isEmpty
    }

    var body: some View {
        NavigationSplitView {
            VStack(spacing: 0) {
                libraryControls

                if store.isLoading, !isInitialLoading {
                    ProgressView()
                        .progressViewStyle(.linear)
                }

                if let error = store.error, !unifiedEntries.isEmpty {
                    libraryErrorBanner(error)
                }

                Divider()

                libraryContent
            }
            .background(StudioPalette.surface)
            .navigationSplitViewColumnWidth(
                min: viewMode == .morphospace ? 500 : 360,
                ideal: viewMode == .morphospace ? 700 : 440,
                max: viewMode == .morphospace ? 900 : 620
            )
        } detail: {
            if let entry = selectedCreature {
                CompendiumDetailView(entry: entry)
                    .frame(minWidth: 360)
            } else {
                ContentUnavailableView(
                    "Select a Specimen",
                    systemImage: "circle.hexagongrid"
                )
            }
        }
        .navigationSplitViewStyle(.balanced)
        .background {
            HStack(spacing: 0) {
                Button("Search") { isSearchFocused = true }
                    .keyboardShortcut("f", modifiers: .command)
                Button("Toggle View") {
                    let modes = CompendiumViewMode.allCases
                    let index = modes.firstIndex(of: viewMode) ?? 0
                    viewMode = modes[(index + 1) % modes.count]
                }
                .keyboardShortcut("g", modifiers: .command)
            }
            .frame(width: 0, height: 0)
            .clipped()
            .opacity(0)
            .accessibilityHidden(true)
        }
        .onAppear {
            if compendiumPath.isEmpty, let defaultPath = defaultCompendiumPath() {
                compendiumPath = defaultPath
            }
            refresh()
        }
        .onChange(of: compendiumPath) { _, _ in scheduleRefresh() }
        .onChange(of: searchText) { _, _ in scheduleRefresh() }
        .onChange(of: stableOnly) { _, _ in scheduleRefresh() }
        .onChange(of: catalogFilter) { _, _ in scheduleRefresh() }
        .onChange(of: minScoreText) { _, _ in scheduleRefresh() }
        .onChange(of: limit) { _, _ in scheduleRefresh() }
        .onChange(of: displayedEntries.map(\.id), initial: true) { _, displayedIDs in
            selectedCreatureIds = reconciledCompendiumSelection(
                selectedIDs: selectedCreatureIds,
                displayedIDs: displayedIDs
            )
        }
        .onChange(of: selectedCreatureIds) { oldValue, newValue in
            if newValue.count > appState.compareTrayCapacity {
                selectedCreatureIds = oldValue
            }
        }
        .fileImporter(isPresented: $showPicker, allowedContentTypes: [.data], allowsMultipleSelection: false) { result in
            if case .success(let urls) = result, let url = urls.first {
                compendiumPath = url.path
            }
        }
        .sheet(isPresented: $showComparison) {
            if comparisonEntries.count >= 2 {
                NavigationStack {
                    ComparisonView(entries: comparisonEntries.map(\.studioEntry))
                }
                .frame(minWidth: 920, minHeight: 680)
            }
        }
        .sheet(isPresented: $showCreateSweep) {
            CreateSweepSheet()
        }
        .onDisappear {
            refreshTask?.cancel()
        }
    }

    private var libraryControls: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                TextField("Search specimens", text: $searchText)
                    .textFieldStyle(.roundedBorder)
                    .font(StudioType.body)
                    .focused($isSearchFocused)
                    .accessibilityLabel("Search specimens")

                Picker("View", selection: $viewMode) {
                    ForEach(CompendiumViewMode.allCases, id: \.self) { mode in
                        Text(mode.rawValue).tag(mode)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .frame(width: 170)
            }

            HStack(spacing: 8) {
                Picker("Catalog", selection: $catalogFilter) {
                    ForEach(CompendiumCatalogFilter.allCases, id: \.self) { filter in
                        Text(filter.rawValue).tag(filter)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .frame(maxWidth: 230)

                Toggle(isOn: $stableOnly) {
                    Label("Stable", systemImage: "checkmark.seal")
                }
                .toggleStyle(.button)
                .controlSize(.small)

                Toggle(isOn: $favoritesOnly) {
                    Image(systemName: favoritesOnly ? "star.fill" : "star")
                }
                .toggleStyle(.button)
                .controlSize(.small)
                .accessibilityLabel("Favorites only")
                .help("Show favorites only")

                Spacer(minLength: 0)
            }

            HStack(spacing: 8) {
                HStack(spacing: 5) {
                    Text("MIN SCORE")
                        .font(StudioType.label)
                        .foregroundStyle(StudioPalette.mutedInk)
                    TextField("Any", text: $minScoreText)
                        .textFieldStyle(.roundedBorder)
                        .font(StudioType.dataSmall)
                        .frame(width: 68)
                }

                Text("\(displayedEntries.count.formatted()) shown")
                    .font(StudioType.dataSmall)
                    .foregroundStyle(StudioPalette.mutedInk)

                Spacer(minLength: 8)

                if comparisonEntries.count >= 2 {
                    Button {
                        showComparison = true
                    } label: {
                        Label(comparisonButtonTitle, systemImage: "rectangle.split.2x1")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .accessibilityLabel(comparisonButtonTitle)
                }
            }

            sourceDisclosure
        }
        .padding(12)
        .background(StudioPalette.surface)
    }

    private var sourceDisclosure: some View {
        DisclosureGroup(isExpanded: $showSourceControls) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    TextField("Compendium database path", text: $compendiumPath)
                        .textFieldStyle(.roundedBorder)
                        .font(StudioType.dataSmall)
                    Button { showPicker = true } label: {
                        Image(systemName: "folder")
                    }
                    .help("Choose compendium database")
                    Button { refresh() } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .help("Refresh source")
                }

                HStack(spacing: 10) {
                    Stepper("Page \(limit)", value: $limit, in: 25...2000, step: 25)
                        .font(StudioType.dataSmall)
                    Spacer()
                    if store.warehousePath != nil {
                        Label("Warehouse available", systemImage: "circle.grid.2x2")
                            .font(StudioType.dataSmall)
                            .foregroundStyle(StudioPalette.mutedInk)
                    }
                }
            }
            .padding(.top, 8)
        } label: {
            HStack(spacing: 7) {
                Image(systemName: "externaldrive")
                    .foregroundStyle(StudioPalette.mutedInk)
                VStack(alignment: .leading, spacing: 1) {
                    Text(sourceDisplayName)
                        .font(StudioType.labelStrong)
                        .foregroundStyle(StudioPalette.ink)
                        .lineLimit(1)
                    Text("\(appState.library.count) local · \(store.creatures.count) indexed · \(store.status)")
                        .font(StudioType.dataSmall)
                        .foregroundStyle(StudioPalette.mutedInk)
                        .lineLimit(1)
                }
                Spacer(minLength: 6)
                if store.isLoading {
                    ProgressView()
                        .controlSize(.small)
                }
            }
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 7)
        .background(StudioPalette.surfaceSoft.opacity(0.55), in: RoundedRectangle(cornerRadius: 6, style: .continuous))
        .tint(StudioPalette.mutedInk)
    }

    @ViewBuilder
    private var libraryContent: some View {
        if isInitialLoading {
            VStack(spacing: 12) {
                ProgressView()
                    .controlSize(.regular)
                Text("Loading specimens")
                    .font(StudioType.bodySmall)
                    .foregroundStyle(StudioPalette.mutedInk)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = store.error, unifiedEntries.isEmpty {
            ContentUnavailableView {
                Label("Source Unavailable", systemImage: "exclamationmark.triangle")
            } description: {
                Text(error)
            } actions: {
                Button("Retry") { refresh() }
            }
        } else if displayedEntries.isEmpty {
            ContentUnavailableView(
                "No Matching Specimens",
                systemImage: "line.3.horizontal.decrease.circle"
            )
        } else {
            VStack(spacing: 0) {
                switch viewMode {
                case .list:
                    List(displayedEntries, selection: $selectedCreatureIds) { entry in
                        CompendiumRow(entry: entry)
                            .tag(entry.id)
                            .contextMenu { compendiumContextMenu(for: entry) }
                    }
                    .listStyle(.inset)
                case .grid:
                    ScrollView {
                        LazyVGrid(
                            columns: [GridItem(.adaptive(minimum: 148, maximum: 190), spacing: 10)],
                            spacing: 10
                        ) {
                            ForEach(displayedEntries) { entry in
                                let isSelected = selectedCreatureIds.contains(entry.id)
                                Button {
                                    selectGridEntry(entry)
                                } label: {
                                    CompendiumGridCell(entry: entry, isSelected: isSelected)
                                }
                                    .buttonStyle(.plain)
                                    .accessibilityLabel(entry.name)
                                    .accessibilityValue(gridAccessibilityValue(entry))
                                    .accessibilityAddTraits(isSelected ? .isSelected : [])
                                    .accessibilityAction(named: "Open Specimen") {
                                        selectedCreatureIds = [entry.id]
                                    }
                                    .contextMenu { compendiumContextMenu(for: entry) }
                            }
                        }
                        .padding(12)
                    }
                case .morphospace:
                    StudioMorphospaceView(
                        entries: displayedEntries,
                        selectedID: Binding(
                            get: { selectedCreatureIds.first },
                            set: { selectedCreatureIds = $0.map { [$0] } ?? [] }
                        ),
                        canLaunchSweep: connectedAsHost,
                        onOpen: { selectedCreatureIds = [$0.id] },
                        onLaunchSweep: { entry, _, _ in
                            selectedCreatureIds = [entry.id]
                            if case .connected(role: .host) = appState.connectionState {
                                showCreateSweep = true
                            }
                        }
                    )
                }

                if let cursor = store.nextCursor {
                    Divider()
                    Button {
                        loadMore(after: cursor)
                    } label: {
                        Label(store.isLoading ? "Loading More" : "Load More", systemImage: "arrow.down.circle")
                    }
                    .buttonStyle(.borderless)
                    .controlSize(.small)
                    .disabled(store.isLoading)
                    .padding(.vertical, 8)
                }
            }
        }
    }

    private func libraryErrorBanner(_ error: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(StudioPalette.ember)
            Text(error)
                .font(StudioType.bodySmall)
                .foregroundStyle(StudioPalette.ink)
                .lineLimit(2)
            Spacer(minLength: 8)
            Button { refresh() } label: {
                Image(systemName: "arrow.clockwise")
            }
            .buttonStyle(.borderless)
            .help("Retry source")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(StudioPalette.ember.opacity(0.08))
    }

    @ViewBuilder
    private func compendiumContextMenu(for entry: CompendiumCreature) -> some View {
        CreatureContextMenu(
            seed: entry.previewSeed,
            savedCreature: entry.creature,
            onPreview: { selectedCreatureIds = [entry.id] },
            revealPath: entry.resolvedRunPath
        )
        Divider()
        Button {
            toggleFavorite(entry.id)
        } label: {
            Label(
                favoriteIDs.contains(entry.id) ? "Remove Favorite" : "Favorite",
                systemImage: favoriteIDs.contains(entry.id) ? "star.slash" : "star"
            )
        }
        Button {
            _ = appState.addCompareEntry(entry.studioEntry)
        } label: {
            Label("Add to Compare", systemImage: "rectangle.split.2x1")
        }
        .disabled(appState.compareTrayIsFull && !appState.compareTray.contains(where: { $0.id == entry.studioEntry.id }))
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

    private func loadMore(after cursor: CompendiumBrowseCursor) {
        let query = CompendiumQuery(
            search: searchText,
            stableOnly: stableOnly,
            catalogFilter: catalogFilter,
            minScore: Float(minScoreText),
            limit: limit,
            cursor: cursor
        )
        store.load(path: compendiumPath, query: query, appending: true)
    }

    private func toggleFavorite(_ id: UUID) {
        var ids = favoriteIDs
        if ids.contains(id) {
            ids.remove(id)
        } else {
            ids.insert(id)
        }
        favoriteSpecimenIDs = ids.map(\.uuidString).sorted().joined(separator: ",")
    }

    private func defaultCompendiumPath() -> String? {
        defaultStudioCompendiumPath(anchorFilePath: #filePath)
    }

    private func selectGridEntry(_ entry: CompendiumCreature) {
        if NSEvent.modifierFlags.contains(.command) {
            if selectedCreatureIds.contains(entry.id) {
                selectedCreatureIds.remove(entry.id)
            } else if selectedCreatureIds.count < appState.compareTrayCapacity {
                selectedCreatureIds.insert(entry.id)
            }
        } else {
            selectedCreatureIds = [entry.id]
        }
    }

    private func gridAccessibilityValue(_ entry: CompendiumCreature) -> String {
        let score = entry.score.map { String(format: "score %.4f", $0) } ?? "score unavailable"
        let stability = entry.isStable ? "stable" : "not stable"
        let classification = entry.browserClassification.map { ", \($0)" } ?? ""
        return "\(score), \(stability)\(classification)"
    }

}

private struct CompendiumGridCell: View {
    let entry: CompendiumCreature
    let isSelected: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ZStack(alignment: .topTrailing) {
                CreatureThumbnailView(creature: entry.liveCreature, size: 112)
                    .frame(maxWidth: .infinity)
                if entry.isStable {
                    Image(systemName: "checkmark.seal.fill")
                        .font(StudioType.labelStrong)
                        .foregroundStyle(StudioPalette.moss)
                        .padding(6)
                        .background(.thinMaterial, in: Circle())
                        .padding(5)
                }
            }
            Text(entry.name)
                .font(StudioType.body)
                .foregroundStyle(StudioPalette.ink)
                .lineLimit(2)
                .frame(height: 34, alignment: .topLeading)

            Text(entry.browserClassification ?? entry.displayRun)
                .font(StudioType.dataSmall)
                .foregroundStyle(StudioPalette.mutedInk)
                .lineLimit(1)

            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text("SCORE")
                    .font(StudioType.label)
                    .foregroundStyle(StudioPalette.mutedInk)
                Text(entry.score.map { String(format: "%.4f", $0) } ?? "--")
                    .font(StudioType.data)
                    .foregroundStyle(StudioPalette.ink)
                    .monospacedDigit()
                Spacer(minLength: 0)
                if entry.catalogStatus != "active" {
                    Circle()
                        .fill(qcStatusColor(entry.catalogStatus))
                        .frame(width: 6, height: 6)
                        .help(entry.catalogStatus.capitalized)
                }
            }
        }
        .padding(9)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 6, style: .continuous)
                .fill(isSelected ? StudioPalette.surfaceSoft : StudioPalette.surfaceRaised)
        )
        .overlay {
            RoundedRectangle(cornerRadius: 6, style: .continuous)
                .stroke(isSelected ? StudioPalette.ocean : StudioPalette.hairline, lineWidth: isSelected ? 1.5 : 1)
        }
        .contentShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
    }
}

private struct CompendiumRow: View {
    let entry: CompendiumCreature

    var body: some View {
        HStack(spacing: 10) {
            ZStack(alignment: .bottomTrailing) {
                CreatureThumbnailView(creature: entry.liveCreature, size: 48)
                Circle()
                    .fill(entry.isStable ? StudioPalette.moss : StudioPalette.ocean)
                    .frame(width: 8, height: 8)
                    .overlay(Circle().stroke(StudioPalette.surface, lineWidth: 1.5))
                    .padding(3)
            }

            VStack(alignment: .leading, spacing: 3) {
                HStack(alignment: .firstTextBaseline, spacing: 7) {
                    Text(entry.name)
                        .font(StudioType.body)
                        .foregroundStyle(StudioPalette.ink)
                        .lineLimit(1)
                    if entry.catalogStatus != "active" {
                        Text(entry.catalogStatus.capitalized)
                            .font(StudioType.label)
                            .foregroundStyle(qcStatusColor(entry.catalogStatus))
                    }
                }
                CompendiumTaxonomyLine(entry: entry)
                Text(entry.displayRun)
                    .font(StudioType.dataSmall)
                    .foregroundStyle(StudioPalette.mutedInk)
                    .lineLimit(1)
            }

            Spacer(minLength: 8)

            VStack(alignment: .trailing, spacing: 2) {
                Text("SCORE")
                    .font(StudioType.label)
                    .foregroundStyle(StudioPalette.mutedInk)
                Text(entry.score.map { String(format: "%.4f", $0) } ?? "--")
                    .font(StudioType.data)
                    .foregroundStyle(StudioPalette.ink)
                    .monospacedDigit()
            }
        }
        .padding(.vertical, 5)
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

    var body: some View {
        if let label = entry.browserClassification {
            Text(label)
                .font(StudioType.dataSmall)
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
                            .font(StudioType.title)
                            .foregroundStyle(StudioPalette.ink)
                        Spacer()
                        if let score = entry.score {
                            Text(String(format: "%.4f", score))
                                .font(StudioType.data)
                                .monospacedDigit()
                                .foregroundStyle(StudioPalette.ember)
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
                    .font(StudioType.labelStrong)

                    DisclosureGroup("Genotype") {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("R: \(String(format: "%.1f", creature.genotype.R))")
                            Text("r: \(creature.genotype.r.map { String(format: "%.2f", $0) }.joined(separator: ", "))")
                            Text("m: \(creature.genotype.m.map { String(format: "%.2f", $0) }.joined(separator: ", "))")
                            Text("s: \(creature.genotype.s.map { String(format: "%.3f", $0) }.joined(separator: ", "))")
                            Text("h: \(creature.genotype.h.map { String(format: "%.2f", $0) }.joined(separator: ", "))")
                        }
                        .font(StudioType.dataSmall)
                        .foregroundStyle(StudioPalette.mutedInk)
                        .padding(.top, 4)
                    }
                    .font(StudioType.labelStrong)

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
                    .font(StudioType.labelStrong)

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
                    .font(StudioType.labelStrong)

                    replayContractSection

                    HStack(spacing: 8) {
                        Button {
                            CreatureExport.copyConfigToClipboard(for: creature)
                        } label: {
                            Label("Copy Config", systemImage: "doc.on.doc")
                        }
                        Button {
                            _ = CreatureExport.saveConfigToFile(for: creature)
                        } label: {
                            Label("Save Config", systemImage: "square.and.arrow.down")
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
                        .font(StudioType.bodySmall)
                        .foregroundStyle(StudioPalette.mutedInk)
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
                                .font(StudioType.labelStrong)
                                .foregroundStyle(StudioPalette.mutedInk)
                            ForEach(replayContract.connectivityRows, id: \.self) { row in
                                Text(row)
                                    .font(StudioType.dataSmall)
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
                    .font(StudioType.bodySmall)
                    .foregroundStyle(StudioPalette.mutedInk)
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
                .font(StudioType.label)
                .foregroundStyle(StudioPalette.mutedInk)
            Text(value)
                .font(StudioType.data)
                .foregroundStyle(StudioPalette.ink)
                .monospacedDigit()
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(StudioPalette.surfaceSoft.opacity(0.5), in: RoundedRectangle(cornerRadius: 4, style: .continuous))
    }
}

private struct MetadataRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack {
            Text(label)
                .foregroundStyle(StudioPalette.mutedInk)
            Spacer()
            Text(value)
                .multilineTextAlignment(.trailing)
                .foregroundStyle(StudioPalette.ink)
        }
        .font(StudioType.dataSmall)
    }
}
