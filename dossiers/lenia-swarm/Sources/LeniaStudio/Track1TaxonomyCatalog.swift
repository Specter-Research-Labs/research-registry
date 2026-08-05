import Foundation
import LeniaCore
import SwiftUI

enum OrganismCatalogCollection: String, Equatable, Sendable {
    case flowNative
    case classicalReference

    var title: String {
        switch self {
        case .flowNative: "Flow life"
        case .classicalReference: "Classical reference"
        }
    }
}

enum OrganismCatalogTier: String, Equatable, Sendable {
    case primary
    case experimental
    case reference

    var title: String {
        rawValue.capitalized
    }
}

struct Track1TaxonomyConfig: Identifiable, Hashable, Sendable {
    let path: String
    let family: String
    let genus: String
    let species: String
    let patternID: String
    let backend: String
    let implementationMode: String
    let kernelProfile: String
    let channels: Int
    let kernelCount: Int
    let gridSize: Int
    let runSteps: Int
    let provenanceBundleKind: String?
    let isBundled: Bool

    var id: String { path }

    var displayName: String {
        species.isEmpty ? patternID : species
    }

    var compactLineage: String {
        "\(family) / \(genus) / \(displayName)"
    }

    var runtimeSummary: String {
        "\(channels)m · \(kernelCount)k · \(gridSize)x\(gridSize) · \(backend)"
    }

    var isLabLoadable: Bool {
        switch implementationMode {
        case "flowlenia_2022_paper_equations", "flowlenia_2022_colab", "qd24_additive_v1":
            true
        case "custom":
            ["flowlenia_2022_paper_equations", "flowlenia_2022_colab", "qd24_bucketed_v1"].contains(kernelProfile)
        default:
            false
        }
    }

    var requiredLabBackend: FlowSandboxBackend? {
        switch catalogCollection {
        case .flowNative:
            .metalFull
        case .classicalReference:
            .mlx
        }
    }

    var catalogCollection: OrganismCatalogCollection {
        implementationMode == "qd24_additive_v1" ? .classicalReference : .flowNative
    }

    var catalogTier: OrganismCatalogTier {
        guard catalogCollection == .flowNative else { return .reference }
        return provenanceBundleKind == "strict_replay_bundle_v1" ? .primary : .experimental
    }

    var catalogHierarchy: String {
        "\(compactLineage) / \(patternID)"
    }

    var variantLabel: String {
        let sourceName = URL(fileURLWithPath: path).deletingPathExtension().lastPathComponent
        return "\(patternID) · \(runtimeSummary) · \(sourceName)"
    }

    var taxonomyRecord: SpecimenTaxonomyRecord {
        SpecimenTaxonomyRecord(
            familyID: family,
            genusID: genus,
            speciesID: displayName,
            confidence: 1.0,
            method: "track1-config-provenance",
            version: 1
        )
    }

    func studioEntry(runtimeConfig: LeniaRuntimeConfig? = nil) -> StudioCompareEntry {
        let resolvedParams = runtimeConfig?.params ?? ResolvedParams(
            r: [1.0],
            b: [[1.0]],
            w: [[1.0]],
            a: [[0.5]],
            m: [0.15],
            s: [0.02],
            h: [1.0],
            R: 13.0,
            seed: 0
        )
        let creature = LeniaCreature(
            seed: runtimeConfig?.initSeed ?? 0,
            score: 0,
            params: resolvedParams,
            sourceNode: "track1"
        )
        let labels = [family, genus, patternID, catalogTier.title]
        let runtimeFamily = catalogCollection == .flowNative
            ? "flow-lenia-native"
            : "classical-lenia-additive"
        let sourceMode = catalogCollection == .flowNative
            ? "flow-organism"
            : "classical-reference"
        return StudioCompareEntry(
            id: "track1:\(path)",
            creature: creature,
            name: displayName,
            subtitle: "\(family) · \(patternID)",
            replayReference: StudioReplayReference(
                baseConfigPath: path,
                runtimeFamily: runtimeFamily
            ),
            taxonomy: taxonomyRecord,
            traitLabels: labels,
            runtimeFamily: runtimeFamily,
            sourceMode: sourceMode,
            sourceAlgorithm: implementationMode,
            runtimeCapabilities: ["runtime-config", backend, kernelProfile]
        )
    }
}

struct Track1TaxonomyGenus: Identifiable, Sendable {
    let id: String
    let name: String
    let configs: [Track1TaxonomyConfig]
}

struct Track1TaxonomyFamily: Identifiable, Sendable {
    let id: String
    let name: String
    let genera: [Track1TaxonomyGenus]

    var configCount: Int {
        genera.reduce(0) { $0 + $1.configs.count }
    }

    var speciesCount: Int {
        Set(genera.flatMap { genus in genus.configs.map(\.displayName) }).count
    }
}

struct FlowOrganismFamily: Identifiable, Sendable {
    let id: String
    let name: String
    let configs: [Track1TaxonomyConfig]
}

struct Track1TaxonomyCatalog: Sendable {
    let rootPath: String
    let configs: [Track1TaxonomyConfig]
    let families: [Track1TaxonomyFamily]

    static let empty = Track1TaxonomyCatalog(rootPath: "", configs: [], families: [])

    var genusCount: Int {
        Set(configs.map(\.genus)).count
    }

    var speciesCount: Int {
        Set(configs.map(\.displayName)).count
    }

    var labLoadableCount: Int {
        configs.filter(\.isLabLoadable).count
    }

    var featuredFlowConfigs: [Track1TaxonomyConfig] {
        configs.filter { $0.isBundled && $0.catalogCollection == .flowNative }
    }

    var primaryFlowConfigs: [Track1TaxonomyConfig] {
        featuredFlowConfigs.filter { $0.catalogTier == .primary }
    }

    var experimentalFlowConfigs: [Track1TaxonomyConfig] {
        featuredFlowConfigs.filter { $0.catalogTier == .experimental }
    }

    var classicalReferenceConfigs: [Track1TaxonomyConfig] {
        configs.filter { $0.isBundled && $0.catalogCollection == .classicalReference }
    }

    func config(path: String) -> Track1TaxonomyConfig? {
        configs.first { $0.path == path }
    }
}

func flowOrganismFamilies(from configs: [Track1TaxonomyConfig]) -> [FlowOrganismFamily] {
    Dictionary(grouping: configs.filter { $0.catalogCollection == .flowNative }) {
        $0.family
    }
    .map { family, familyConfigs in
        FlowOrganismFamily(
            id: family,
            name: family,
            configs: familyConfigs.sorted { lhs, rhs in
                let leftKey = "\(lhs.genus)/\(lhs.patternID)/\(lhs.displayName)"
                let rightKey = "\(rhs.genus)/\(rhs.patternID)/\(rhs.displayName)"
                return leftKey.localizedStandardCompare(rightKey) == .orderedAscending
            }
        )
    }
    .sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
}

@MainActor
final class Track1TaxonomyCatalogStore: ObservableObject {
    @Published private(set) var catalog: Track1TaxonomyCatalog = .empty
    @Published private(set) var isLoading = false
    @Published private(set) var status = "No Track 1 root loaded"
    @Published private(set) var error: String?

    private var loadTask: Task<Void, Never>?
    private var requestID = 0

    init() {
        guard let featured = try? bundledFeaturedOrganisms() else { return }
        catalog = Track1TaxonomyCatalog(
            rootPath: featured.first.map { URL(fileURLWithPath: $0.path).deletingLastPathComponent().path } ?? "",
            configs: featured,
            families: track1Families(from: featured)
        )
        status = "\(featured.count) featured lifeforms"
    }

    deinit {
        loadTask?.cancel()
    }

    func load(rootPath: String) {
        loadTask?.cancel()
        requestID += 1
        let activeRequestID = requestID
        let trimmed = rootPath.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            catalog = .empty
            isLoading = false
            status = "Choose a Track 1 config root"
            error = nil
            return
        }
        guard FileManager.default.fileExists(atPath: trimmed) else {
            catalog = .empty
            isLoading = false
            status = "Track 1 root missing"
            error = trimmed
            return
        }

        isLoading = true
        status = "Scanning Track 1 configs..."
        error = nil

        loadTask = Task.detached(priority: .userInitiated) {
            do {
                let scannedCatalog = try loadTrack1TaxonomyCatalog(rootPath: trimmed)
                let nextCatalog = try catalogIncludingBundledOrganisms(scannedCatalog)
                guard !Task.isCancelled else { return }
                await MainActor.run {
                    guard activeRequestID == self.requestID else { return }
                    self.catalog = nextCatalog
                    self.status = "\(nextCatalog.configs.count) configs · \(nextCatalog.families.count) families"
                    self.error = nextCatalog.configs.isEmpty ? "No usable Track 1 runtime configs found under \(trimmed)" : nil
                    self.isLoading = false
                }
            } catch {
                guard !Task.isCancelled else { return }
                await MainActor.run {
                    guard activeRequestID == self.requestID else { return }
                    self.catalog = .empty
                    self.status = "Failed to load Track 1 configs"
                    self.error = error.localizedDescription
                    self.isLoading = false
                }
            }
        }
    }
}

private func catalogIncludingBundledOrganisms(
    _ catalog: Track1TaxonomyCatalog
) throws -> Track1TaxonomyCatalog {
    let featured = try bundledFeaturedOrganisms()
    var paths = Set(featured.map(\.path))
    let configs = featured + catalog.configs.filter { paths.insert($0.path).inserted }
    return Track1TaxonomyCatalog(
        rootPath: catalog.rootPath,
        configs: configs,
        families: track1Families(from: configs)
    )
}

func defaultTrack1ConfigRoot(fileManager: FileManager = .default) -> String? {
    let home = fileManager.homeDirectoryForCurrentUser.path
    let candidates = [
        "\(home)/dev/specter-labs/research-registry/dossiers/lenia-swarm/artifacts/configs",
        "\(home)/dev/specter-labs/research-registry-lenia-fiber-tda/dossiers/lenia-swarm/artifacts/configs",
        "\(home)/Library/Application Support/lenia-swarm/artifacts/configs",
    ]
    if let existing = candidates.first(where: { fileManager.fileExists(atPath: $0) }) {
        return existing
    }
    return bundledOrganismRoot(fileManager: fileManager)
}

func bundledFeaturedOrganisms() throws -> [Track1TaxonomyConfig] {
    guard let resourceRoot = Bundle.module.resourceURL else { return [] }
    let urls = try FileManager.default.contentsOfDirectory(
        at: resourceRoot,
        includingPropertiesForKeys: [.isRegularFileKey],
        options: [.skipsHiddenFiles]
    )
    return try urls
        .filter { $0.pathExtension == "json" }
        .compactMap { try track1TaxonomyConfig(url: $0, isBundled: true) }
        .sorted { $0.catalogHierarchy.localizedStandardCompare($1.catalogHierarchy) == .orderedAscending }
}

private func bundledOrganismRoot(fileManager: FileManager) -> String? {
    guard let root = Bundle.module.resourceURL,
          fileManager.fileExists(atPath: root.path) else {
        return nil
    }
    return root.path
}

func loadTrack1TaxonomyCatalog(rootPath: String) throws -> Track1TaxonomyCatalog {
    let rootURL = URL(fileURLWithPath: rootPath, isDirectory: true)
    let fileManager = FileManager.default
    guard let enumerator = fileManager.enumerator(
        at: rootURL,
        includingPropertiesForKeys: [.isRegularFileKey],
        options: [.skipsHiddenFiles]
    ) else {
        return .empty
    }

    let decoder = JSONDecoder()
    var configs: [Track1TaxonomyConfig] = []
    for case let url as URL in enumerator {
        guard url.pathExtension == "json", url.lastPathComponent.hasPrefix("track1") || url.path.contains("/track1_") else {
            continue
        }
        let values = try url.resourceValues(forKeys: [.isRegularFileKey])
        guard values.isRegularFile == true else { continue }
        guard let config = try track1TaxonomyConfig(url: url, decoder: decoder) else { continue }
        configs.append(config)
    }

    configs.sort { lhs, rhs in
        lhs.compactLineage.localizedStandardCompare(rhs.compactLineage) == .orderedAscending
    }
    return Track1TaxonomyCatalog(
        rootPath: rootPath,
        configs: configs,
        families: track1Families(from: configs)
    )
}

func track1TaxonomyConfig(
    url: URL,
    decoder: JSONDecoder = JSONDecoder(),
    isBundled: Bool = false
) throws -> Track1TaxonomyConfig? {
    let data = try Data(contentsOf: url)
    let raw = try decoder.decode(Track1RawRuntimeConfig.self, from: data)
    guard let provenance = raw.provenance else { return nil }
    let family = cleanTrack1Token(provenance.family) ?? cleanTrack1FamilyFromFilename(url)
    let species = cleanTrack1Token(provenance.species) ?? cleanTrack1Token(provenance.patternID) ?? url.deletingPathExtension().lastPathComponent
    let patternID = cleanTrack1Token(provenance.patternID) ?? track1PatternFromFilename(url) ?? species
    guard let family, !family.isEmpty else { return nil }

    return Track1TaxonomyConfig(
        path: url.path,
        family: family,
        genus: track1Genus(species: species, family: family),
        species: species,
        patternID: patternID,
        backend: raw.backend ?? "--",
        implementationMode: raw.implementation?.mode ?? "--",
        kernelProfile: raw.implementation?.kernelProfile ?? raw.implementation?.growthProfile ?? "--",
        channels: raw.channels ?? 1,
        kernelCount: raw.params?.r?.count ?? max(1, raw.connectivity?.flatMap { $0 }.reduce(0, +) ?? 1),
        gridSize: raw.grid?.sx ?? raw.grid?.sy ?? 0,
        runSteps: raw.run?.steps ?? 0,
        provenanceBundleKind: provenance.bundleKind,
        isBundled: isBundled
    )
}

func makeTrack1WorldDraft(config: Track1TaxonomyConfig) throws -> LabWorldDraft {
    try makeTrack1WorldDraft(path: config.path, basisName: config.displayName)
}

func makeTrack1WorldDraft(path: String, basisName: String) throws -> LabWorldDraft {
    let data = try Data(contentsOf: URL(fileURLWithPath: path))
    let runtimeConfig = try loadRuntimeConfig(from: data)
    return LabWorldDraft(
        presetID: "track1:\(path)",
        basisName: basisName,
        sourceConfigPath: path,
        runtimeConfig: runtimeConfig
    )
}

func fallbackTrack1Entry(path: String) -> StudioCompareEntry {
    let name = URL(fileURLWithPath: path).deletingPathExtension().lastPathComponent
    let params = ResolvedParams(
        r: [1.0],
        b: [[1.0]],
        w: [[1.0]],
        a: [[0.5]],
        m: [0.15],
        s: [0.02],
        h: [1.0],
        R: 13.0,
        seed: 0
    )
    return StudioCompareEntry(
        id: "track1:\(path)",
        creature: LeniaCreature(seed: 0, score: 0, params: params, sourceNode: "track1"),
        name: name,
        subtitle: "Track 1 config",
        replayReference: StudioReplayReference(baseConfigPath: path, runtimeFamily: "flow-lenia-track1"),
        runtimeFamily: "flow-lenia-track1",
        sourceMode: "track1-ruleset"
    )
}

func track1Families(from configs: [Track1TaxonomyConfig]) -> [Track1TaxonomyFamily] {
    Dictionary(grouping: configs, by: \.family)
        .map { family, familyConfigs in
            let genera = Dictionary(grouping: familyConfigs, by: \.genus)
                .map { genus, genusConfigs in
                    Track1TaxonomyGenus(id: "\(family)/\(genus)", name: genus, configs: genusConfigs)
                }
                .sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
            return Track1TaxonomyFamily(id: family, name: family, genera: genera)
        }
        .sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
}

private func track1Genus(species: String, family: String) -> String {
    let token = species
        .split(whereSeparator: { $0.isWhitespace || $0 == "-" || $0 == "_" })
        .first
        .map(String.init)
    if let token, !token.isEmpty {
        return token
    }
    if family.hasSuffix("idae") {
        return String(family.dropLast(4)) + "ium"
    }
    return family
}

private func cleanTrack1Token(_ value: String?) -> String? {
    guard let value else { return nil }
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
}

private func cleanTrack1FamilyFromFilename(_ url: URL) -> String? {
    let name = url.deletingPathExtension().lastPathComponent
    guard let match = name.range(of: #"[A-Za-z]+idae"#, options: .regularExpression) else {
        return nil
    }
    return String(name[match])
}

private func track1PatternFromFilename(_ url: URL) -> String? {
    let pieces = url.deletingPathExtension().lastPathComponent.split(separator: "-").map(String.init)
    guard pieces.count >= 2 else { return nil }
    return pieces[1]
}

private struct Track1RawRuntimeConfig: Decodable {
    let backend: String?
    let channels: Int?
    let connectivity: [[Int]]?
    let grid: Track1RawGrid?
    let implementation: Track1RawImplementation?
    let params: Track1RawParams?
    let provenance: Track1RawProvenance?
    let run: Track1RawRun?
}

private struct Track1RawGrid: Decodable {
    let sx: Int?
    let sy: Int?
}

private struct Track1RawImplementation: Decodable {
    let mode: String?
    let kernelProfile: String?
    let growthProfile: String?

    enum CodingKeys: String, CodingKey {
        case mode
        case kernelProfile = "kernel_profile"
        case growthProfile = "growth_profile"
    }
}

private struct Track1RawParams: Decodable {
    let r: [Float]?
}

private struct Track1RawProvenance: Decodable {
    let family: String?
    let species: String?
    let patternID: String?
    let bundleKind: String?

    enum CodingKeys: String, CodingKey {
        case family
        case species
        case patternID = "pattern_id"
        case bundleKind = "bundle_kind"
    }
}

private struct Track1RawRun: Decodable {
    let steps: Int?
}
