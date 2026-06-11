import Foundation
import LeniaCore
import SQLite3

public enum CompendiumCatalogFilter: String, CaseIterable, Sendable {
    case active = "Active"
    case quarantine = "Quarantine"
    case all = "All"
}

public struct CompendiumBrowseQuery: Equatable, Sendable {
    public var search: String
    public var stableOnly: Bool
    public var catalogFilter: CompendiumCatalogFilter
    public var minScore: Float?
    public var limit: Int

    public init(
        search: String = "",
        stableOnly: Bool = false,
        catalogFilter: CompendiumCatalogFilter = .active,
        minScore: Float? = nil,
        limit: Int = 200
    ) {
        self.search = search
        self.stableOnly = stableOnly
        self.catalogFilter = catalogFilter
        self.minScore = minScore
        self.limit = limit
    }
}

private struct CompendiumBrowseRow: Sendable {
    let id: UUID
    let name: String
    let ownerID: String
    let runID: String
    let campaignID: String?
    let recordedAt: String
    let score: Float?
    let isStable: Bool
    let scoreWeightsJSON: String?
    let genotypeJSON: String?
    let initialConditionJSON: String?
    let sweepJSON: String?
    let metricsJSON: String?
    let hostID: String?
    let runName: String
    let outputRoot: String?
    let runDir: String?
    let exportDir: String?
    let baseConfigPath: String?
    let searchConfigPath: String?
    let runtimeFamily: String?
    let runtimeCapabilitiesJSON: String?
    let specimenManifestJSON: String?
    let sourceMode: String?
    let sourceAlgorithm: String?
    let traitLabelsJSON: String?
    let taxonomyFamilyID: String?
    let taxonomyGenusID: String?
    let taxonomySpeciesID: String?
    let taxonomyConfidence: Double?
    let taxonomyMethod: String?
    let taxonomyVersion: Int?
    let catalogStatus: String
    let qualityFlagsJSON: String?
    let specimenRecordID: String
    let specimenSourceKind: String
}

public struct CompendiumBrowseEntry: Identifiable, Hashable, Sendable {
    public let id: UUID
    public let name: String
    public let ownerId: String
    public let score: Float?
    public let isStable: Bool
    public let runId: String
    public let runName: String
    public let hostId: String?
    public let campaignId: String?
    public let recordedAt: String
    public let outputRoot: String?
    public let runDir: String?
    public let exportDir: String?
    public let baseConfigPath: String?
    public let searchConfigPath: String?
    public let runtimeFamily: String?
    public let sourceMode: String?
    public let sourceAlgorithm: String?
    public let catalogStatus: String
    public let qualityFlags: [String]
    public let specimenRecordID: String
    public let specimenSourceKind: String

    private let storage: CreatureStorage

    public var runtimeCapabilities: [String] {
        storage.runtimeCapabilities
    }

    public var specimenManifest: SpecimenManifest? {
        storage.specimenManifest
    }

    public var traitLabels: [String] {
        storage.traitLabels
    }

    public var taxonomy: SpecimenTaxonomyRecord? {
        storage.taxonomy
    }

    public var previewSeed: Int {
        storage.previewSeed
    }

    public var previewParams: ResolvedParams {
        storage.previewParams
    }

    public var creature: SavedCreature {
        storage.creature
    }

    public init(
        id: UUID,
        creature: SavedCreature,
        runId: String,
        runName: String,
        hostId: String?,
        campaignId: String?,
        recordedAt: String,
        outputRoot: String?,
        runDir: String?,
        exportDir: String?,
        baseConfigPath: String?,
        searchConfigPath: String?,
        runtimeFamily: String?,
        runtimeCapabilities: [String],
        specimenManifest: SpecimenManifest?,
        sourceMode: String?,
        sourceAlgorithm: String?,
        traitLabels: [String],
        taxonomy: SpecimenTaxonomyRecord? = nil,
        catalogStatus: String = "active",
        qualityFlags: [String] = [],
        specimenRecordID: String,
        specimenSourceKind: String
    ) {
        self.id = id
        self.name = creature.name
        self.ownerId = creature.ownerId
        self.score = creature.score
        self.isStable = creature.metrics.isStable
        self.runId = runId
        self.runName = runName
        self.hostId = hostId
        self.campaignId = campaignId
        self.recordedAt = recordedAt
        self.outputRoot = outputRoot
        self.runDir = runDir
        self.exportDir = exportDir
        self.baseConfigPath = baseConfigPath
        self.searchConfigPath = searchConfigPath
        self.runtimeFamily = runtimeFamily
        self.sourceMode = sourceMode
        self.sourceAlgorithm = sourceAlgorithm
        self.catalogStatus = catalogStatus
        self.qualityFlags = qualityFlags
        self.specimenRecordID = specimenRecordID
        self.specimenSourceKind = specimenSourceKind
        self.storage = .eager(
            creature: creature,
            previewSeed: creature.initialCondition.seed,
            previewParams: ResolvedParams(
                r: creature.genotype.r,
                b: creature.genotype.b,
                w: creature.genotype.w,
                a: creature.genotype.a,
                m: creature.genotype.m,
                s: creature.genotype.s,
                h: creature.genotype.h,
                R: creature.genotype.R,
                seed: creature.initialCondition.seed
            ),
            runtimeCapabilities: runtimeCapabilities,
            specimenManifest: specimenManifest,
            traitLabels: traitLabels,
            taxonomy: taxonomy
        )
    }

    fileprivate init(row: CompendiumBrowseRow) {
        self.id = row.id
        self.name = row.name
        self.ownerId = row.ownerID
        self.score = row.score
        self.isStable = row.isStable
        self.runId = row.runID
        self.runName = row.runName
        self.hostId = row.hostID
        self.campaignId = row.campaignID
        self.recordedAt = row.recordedAt
        self.outputRoot = row.outputRoot
        self.runDir = row.runDir
        self.exportDir = row.exportDir
        self.baseConfigPath = row.baseConfigPath
        self.searchConfigPath = row.searchConfigPath
        self.runtimeFamily = row.runtimeFamily
        self.sourceMode = row.sourceMode
        self.sourceAlgorithm = row.sourceAlgorithm
        self.catalogStatus = row.catalogStatus
        self.qualityFlags = decodeStringList(row.qualityFlagsJSON)
        self.specimenRecordID = row.specimenRecordID
        self.specimenSourceKind = row.specimenSourceKind
        self.storage = .deferred(DeferredCreatureStorage(row: row))
    }

    public var displayRun: String {
        if let hostId, !hostId.isEmpty {
            return "\(hostId) / \(runName)"
        }
        return runName
    }

    public var resolvedRunPath: String? {
        resolveCompendiumArtifactPath(outputRoot: outputRoot, runDir: runDir, path: nil)
    }

    public var resolvedExportPath: String? {
        resolveCompendiumArtifactPath(outputRoot: outputRoot, runDir: runDir, path: exportDir)
    }

    public static func == (lhs: CompendiumBrowseEntry, rhs: CompendiumBrowseEntry) -> Bool {
        lhs.id == rhs.id
    }

    public func hash(into hasher: inout Hasher) {
        hasher.combine(id)
    }
}

private enum CreatureStorage: Sendable {
    case eager(
        creature: SavedCreature,
        previewSeed: Int,
        previewParams: ResolvedParams,
        runtimeCapabilities: [String],
        specimenManifest: SpecimenManifest?,
        traitLabels: [String],
        taxonomy: SpecimenTaxonomyRecord?
    )
    case deferred(DeferredCreatureStorage)

    var creature: SavedCreature {
        switch self {
        case .eager(let creature, _, _, _, _, _, _):
            return creature
        case .deferred(let storage):
            return storage.creature
        }
    }

    var runtimeCapabilities: [String] {
        switch self {
        case .eager(_, _, _, let runtimeCapabilities, _, _, _):
            return runtimeCapabilities
        case .deferred(let storage):
            return storage.runtimeCapabilities
        }
    }

    var specimenManifest: SpecimenManifest? {
        switch self {
        case .eager(_, _, _, _, let specimenManifest, _, _):
            return specimenManifest
        case .deferred(let storage):
            return storage.specimenManifest
        }
    }

    var traitLabels: [String] {
        switch self {
        case .eager(_, _, _, _, _, let traitLabels, _):
            return traitLabels
        case .deferred(let storage):
            return storage.traitLabels
        }
    }

    var taxonomy: SpecimenTaxonomyRecord? {
        switch self {
        case .eager(_, _, _, _, _, _, let taxonomy):
            return taxonomy
        case .deferred(let storage):
            return storage.taxonomy
        }
    }

    var previewSeed: Int {
        switch self {
        case .eager(_, let previewSeed, _, _, _, _, _):
            return previewSeed
        case .deferred(let storage):
            return storage.previewSeed
        }
    }

    var previewParams: ResolvedParams {
        switch self {
        case .eager(_, _, let previewParams, _, _, _, _):
            return previewParams
        case .deferred(let storage):
            return storage.previewParams
        }
    }
}

private final class DeferredCreatureStorage: @unchecked Sendable {
    private struct PreviewData {
        let seed: Int
        let params: ResolvedParams
    }

    private let row: CompendiumBrowseRow
    private let decoder = JSONDecoder()
    private let lock = NSLock()
    private var cachedProjection: ResolvedSpecimenProjection?
    private var cachedPreviewData: PreviewData?

    init(row: CompendiumBrowseRow) {
        self.row = row
    }

    var creature: SavedCreature {
        projection.creature
    }

    var previewSeed: Int {
        previewData.seed
    }

    var previewParams: ResolvedParams {
        previewData.params
    }

    var specimenManifest: SpecimenManifest? {
        projection.manifest
    }

    var runtimeCapabilities: [String] {
        projection.runtimeCapabilities
    }

    var traitLabels: [String] {
        projection.traitLabels
    }

    var taxonomy: SpecimenTaxonomyRecord? {
        row.taxonomyRecord ?? projection.manifest?.taxonomy
    }

    private var projection: ResolvedSpecimenProjection {
        lock.lock()
        if let cachedProjection {
            lock.unlock()
            return cachedProjection
        }
        lock.unlock()

        let projection = resolveSpecimenProjection(
            id: row.id,
            name: row.name,
            ownerId: row.ownerID,
            manifest: decodeOptional(SpecimenManifest.self, from: row.specimenManifestJSON),
            fallbackGenotype: try! decoder.decode(KernelParams.self, from: Data((row.genotypeJSON ?? "{}").utf8)),
            fallbackInitialCondition: try! decoder.decode(InitConfig.self, from: Data((row.initialConditionJSON ?? "{}").utf8)),
            fallbackMetrics: try! decoder.decode(SimulationMetrics.self, from: Data((row.metricsJSON ?? "{}").utf8)),
            sweep: decodeOptional([String: Double].self, from: row.sweepJSON),
            score: row.score,
            scoreWeights: decodeOptional([String: Float].self, from: row.scoreWeightsJSON),
            fallbackRuntimeFamily: row.runtimeFamily,
            fallbackRuntimeCapabilities: decodeOptional([String].self, from: row.runtimeCapabilitiesJSON),
            fallbackSourceMode: row.sourceMode,
            fallbackSourceAlgorithm: row.sourceAlgorithm,
            fallbackTraitLabels: decodeOptional([String].self, from: row.traitLabelsJSON)
        )

        lock.lock()
        cachedProjection = projection
        lock.unlock()
        return projection
    }

    private var previewData: PreviewData {
        lock.lock()
        if let cachedPreviewData {
            lock.unlock()
            return cachedPreviewData
        }
        lock.unlock()

        let creature = creature
        let preview = PreviewData(
            seed: creature.initialCondition.seed,
            params: ResolvedParams(
                r: creature.genotype.r,
                b: creature.genotype.b,
                w: creature.genotype.w,
                a: creature.genotype.a,
                m: creature.genotype.m,
                s: creature.genotype.s,
                h: creature.genotype.h,
                R: creature.genotype.R,
                seed: creature.initialCondition.seed
            )
        )

        lock.lock()
        cachedPreviewData = preview
        lock.unlock()
        return preview
    }

    private func decodeOptional<T: Decodable>(
        _ type: T.Type,
        from value: String?
    ) -> T? {
        guard let value, !value.isEmpty else {
            return nil
        }
        return try? decoder.decode(type, from: Data(value.utf8))
    }
}

private extension CompendiumBrowseRow {
    var taxonomyRecord: SpecimenTaxonomyRecord? {
        let hasAnyValue = [
            taxonomyFamilyID,
            taxonomyGenusID,
            taxonomySpeciesID,
            taxonomyMethod,
        ].contains { value in
            guard let value else { return false }
            return !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        } || taxonomyConfidence != nil || taxonomyVersion != nil

        guard hasAnyValue else { return nil }
        return SpecimenTaxonomyRecord(
            familyID: taxonomyFamilyID,
            genusID: taxonomyGenusID,
            speciesID: taxonomySpeciesID,
            confidence: taxonomyConfidence,
            method: taxonomyMethod,
            version: taxonomyVersion
        )
    }
}

public struct CompendiumBrowseResult: Sendable {
    public let entries: [CompendiumBrowseEntry]
    public let status: String
    public let error: String?

    public init(entries: [CompendiumBrowseEntry], status: String, error: String?) {
        self.entries = entries
        self.status = status
        self.error = error
    }
}

public enum CompendiumBrowseError: LocalizedError {
    case openFailed(String)
    case queryFailed(String)
    case invalidDatabase(String)

    public var errorDescription: String? {
        switch self {
        case .openFailed(let message), .queryFailed(let message), .invalidDatabase(let message):
            return message
        }
    }
}

public func browseCompendium(
    path: String,
    query: CompendiumBrowseQuery
) throws -> CompendiumBrowseResult {
    var db: OpaquePointer?
    let openFlags = SQLITE_OPEN_READONLY | SQLITE_OPEN_NOMUTEX
    if sqlite3_open_v2(path, &db, openFlags, nil) != SQLITE_OK {
        let message = db.flatMap { String(cString: sqlite3_errmsg($0)) } ?? "Failed to open compendium"
        sqlite3_close(db)
        throw CompendiumBrowseError.openFailed(message)
    }
    guard let handle = db else {
        throw CompendiumBrowseError.invalidDatabase("Failed to open compendium database.")
    }
    defer { sqlite3_close(handle) }

    let creatureColumns = try tableColumns(handle: handle, tableName: "creatures")
    guard creatureColumns.contains("canonical_specimen_id") else {
        throw CompendiumBrowseError.invalidDatabase(
            "Compendium is missing creatures.canonical_specimen_id. Rebuild the canonical compendium before browsing."
        )
    }
    guard try tableExists(handle: handle, tableName: "specimens") else {
        throw CompendiumBrowseError.invalidDatabase(
            "Compendium is missing specimens. Rebuild the canonical compendium before browsing."
        )
    }

    let trimmedSearch = query.search.trimmingCharacters(in: .whitespacesAndNewlines)
    let limit = max(1, min(query.limit, 5_000))
    let startedAt = Date()

    let whereClauses: [String] = {
        var clauses: [String] = []
        if !trimmedSearch.isEmpty {
            clauses.append("c.name LIKE ?")
        }
        if query.stableOnly {
            clauses.append("c.is_stable = 1")
        }
        if query.minScore != nil {
            clauses.append("COALESCE(c.score, 0) >= ?")
        }
        if creatureColumns.contains("catalog_status") {
            switch query.catalogFilter {
            case .active:
                clauses.append("c.catalog_status IN ('active', 'protected')")
            case .quarantine:
                clauses.append("c.catalog_status = 'quarantine'")
            case .all:
                break
            }
        }
        clauses.append("c.genotype_json IS NOT NULL AND json_valid(c.genotype_json) = 1")
        clauses.append("c.initial_condition_json IS NOT NULL AND json_valid(c.initial_condition_json) = 1")
        clauses.append("c.metrics_json IS NOT NULL AND json_valid(c.metrics_json) = 1")
        clauses.append("(c.score_weights_json IS NULL OR json_valid(c.score_weights_json) = 1)")
        clauses.append("(c.sweep_json IS NULL OR json_valid(c.sweep_json) = 1)")
        clauses.append("(c.trait_labels_json IS NULL OR json_valid(c.trait_labels_json) = 1)")
        return clauses
    }()

    let indexHint = trimmedSearch.isEmpty ? " INDEXED BY creatures_score" : ""
    let whereSQL = whereClauses.isEmpty ? "" : "WHERE \(whereClauses.joined(separator: " AND "))"
    let filteredCTE = """
    WITH latest_exports AS (
        SELECT creature_id, export_dir, base_config_path, search_config_path
        FROM (
            SELECT
                creature_id,
                export_dir,
                base_config_path,
                search_config_path,
                ROW_NUMBER() OVER (PARTITION BY creature_id ORDER BY exported_at DESC) AS rn
            FROM exports
        )
        WHERE rn = 1
    ),
    filtered AS (
        SELECT
            c.id,
            c.name,
            c.owner_id,
            c.run_id,
            c.campaign_id,
            c.recorded_at,
            c.score,
            c.is_stable,
            c.score_weights_json,
            c.genotype_json,
            c.initial_condition_json,
            c.sweep_json,
            c.metrics_json,
            c.canonical_specimen_id,
            COALESCE(c.trait_labels_json, '') AS trait_labels_json,
            c.taxonomy_family_id,
            c.taxonomy_genus_id,
            c.taxonomy_species_id,
            c.taxonomy_confidence,
            c.taxonomy_method,
            c.taxonomy_version,
            \(creatureColumns.contains("catalog_status") ? "c.catalog_status" : "'active'") AS catalog_status,
            \(creatureColumns.contains("quality_flags_json") ? "COALESCE(c.quality_flags_json, '[]')" : "'[]'") AS quality_flags_json
        FROM creatures c\(indexHint)
        \(whereSQL)
        ORDER BY c.score DESC, c.recorded_at DESC
        LIMIT ?
    )
    SELECT
        c.id,
        c.name,
        c.owner_id,
        c.run_id,
        c.campaign_id,
        c.recorded_at,
        c.score,
        c.is_stable,
        c.score_weights_json,
        c.genotype_json,
        c.initial_condition_json,
        c.sweep_json,
        c.metrics_json,
        r.host_id,
        r.run_name,
        r.output_root,
        r.run_dir,
        lx.export_dir,
        lx.base_config_path,
        lx.search_config_path,
        s.runtime_family AS runtime_family,
        s.runtime_capabilities_json AS runtime_capabilities_json,
        s.specimen_manifest_json AS specimen_manifest_json,
        s.source_mode AS source_mode,
        s.source_algorithm AS source_algorithm,
        c.trait_labels_json,
        c.taxonomy_family_id,
        c.taxonomy_genus_id,
        c.taxonomy_species_id,
        c.taxonomy_confidence,
        c.taxonomy_method,
        c.taxonomy_version,
        c.catalog_status,
        c.quality_flags_json,
        s.id AS specimen_record_id,
        s.source_kind AS specimen_source_kind
    FROM filtered c
    LEFT JOIN runs r ON r.run_id = c.run_id
    JOIN specimens s ON s.id = c.canonical_specimen_id
    LEFT JOIN latest_exports lx ON lx.creature_id = c.id
    ORDER BY COALESCE(c.score, 0) DESC, c.recorded_at DESC
    """

    var stmt: OpaquePointer?
    if sqlite3_prepare_v2(handle, filteredCTE, -1, &stmt, nil) != SQLITE_OK {
        let message = String(cString: sqlite3_errmsg(handle))
        throw CompendiumBrowseError.queryFailed(message)
    }
    guard let statement = stmt else {
        throw CompendiumBrowseError.queryFailed("Failed to prepare compendium browse query.")
    }
    defer { sqlite3_finalize(statement) }

    var binds: [SQLiteBindValue] = []
    if !trimmedSearch.isEmpty {
        binds.append(.text("%\(trimmedSearch)%"))
    }
    if let minScore = query.minScore {
        binds.append(.double(Double(minScore)))
    }
    binds.append(.int(Int32(limit)))

    for (offset, value) in binds.enumerated() {
        try bindSQLiteValue(value, to: statement, index: Int32(offset + 1), handle: handle)
    }

    var entries: [CompendiumBrowseEntry] = []
    var skipped = 0

    while sqlite3_step(statement) == SQLITE_ROW {
        guard let idText = sqlite3_column_text(statement, 0) else {
            skipped += 1
            continue
        }
        guard
            let specimenRecordID = columnText(statement, index: 34),
            let specimenSourceKind = columnText(statement, index: 35)
        else {
            skipped += 1
            continue
        }

        let idString = String(cString: idText)
        let id = UUID(uuidString: idString) ?? UUID()
        let row = CompendiumBrowseRow(
            id: id,
            name: columnText(statement, index: 1) ?? "Unnamed",
            ownerID: columnText(statement, index: 2) ?? "unknown",
            runID: columnText(statement, index: 3) ?? "unknown",
            campaignID: columnText(statement, index: 4),
            recordedAt: columnText(statement, index: 5) ?? "",
            score: columnFloat(statement, index: 6),
            isStable: sqlite3_column_int(statement, 7) != 0,
            scoreWeightsJSON: columnText(statement, index: 8),
            genotypeJSON: columnText(statement, index: 9),
            initialConditionJSON: columnText(statement, index: 10),
            sweepJSON: columnText(statement, index: 11),
            metricsJSON: columnText(statement, index: 12),
            hostID: columnText(statement, index: 13),
            runName: columnText(statement, index: 14) ?? columnText(statement, index: 3) ?? "unknown",
            outputRoot: columnText(statement, index: 15),
            runDir: columnText(statement, index: 16),
            exportDir: columnText(statement, index: 17),
            baseConfigPath: columnText(statement, index: 18),
            searchConfigPath: columnText(statement, index: 19),
            runtimeFamily: columnText(statement, index: 20),
            runtimeCapabilitiesJSON: columnText(statement, index: 21),
            specimenManifestJSON: columnText(statement, index: 22),
            sourceMode: columnText(statement, index: 23),
            sourceAlgorithm: columnText(statement, index: 24),
            traitLabelsJSON: columnText(statement, index: 25),
            taxonomyFamilyID: columnText(statement, index: 26),
            taxonomyGenusID: columnText(statement, index: 27),
            taxonomySpeciesID: columnText(statement, index: 28),
            taxonomyConfidence: columnDouble(statement, index: 29),
            taxonomyMethod: columnText(statement, index: 30),
            taxonomyVersion: columnInt(statement, index: 31),
            catalogStatus: columnText(statement, index: 32) ?? "active",
            qualityFlagsJSON: columnText(statement, index: 33),
            specimenRecordID: specimenRecordID,
            specimenSourceKind: specimenSourceKind
        )

        entries.append(CompendiumBrowseEntry(row: row))
    }

    let status = "Loaded \(entries.count) creatures in \(formatBrowseDuration(Date().timeIntervalSince(startedAt)))"
    let warning: String?
    if skipped > 0 {
        warning = "Skipped \(skipped) malformed canonical row\(skipped == 1 ? "" : "s")."
    } else {
        warning = nil
    }
    return CompendiumBrowseResult(entries: entries, status: status, error: warning)
}

private func columnText(_ statement: OpaquePointer, index: Int32) -> String? {
    guard let text = sqlite3_column_text(statement, index) else { return nil }
    return String(cString: text)
}

private func columnFloat(_ statement: OpaquePointer, index: Int32) -> Float? {
    guard sqlite3_column_type(statement, index) != SQLITE_NULL else { return nil }
    return Float(sqlite3_column_double(statement, index))
}

private func columnDouble(_ statement: OpaquePointer, index: Int32) -> Double? {
    guard sqlite3_column_type(statement, index) != SQLITE_NULL else { return nil }
    return sqlite3_column_double(statement, index)
}

private func columnInt(_ statement: OpaquePointer, index: Int32) -> Int? {
    guard sqlite3_column_type(statement, index) != SQLITE_NULL else { return nil }
    return Int(sqlite3_column_int(statement, index))
}

private func decodeStringList(_ value: String?) -> [String] {
    guard let value, let data = value.data(using: .utf8) else {
        return []
    }
    return (try? JSONDecoder().decode([String].self, from: data)) ?? []
}

private enum SQLiteBindValue {
    case text(String)
    case int(Int32)
    case double(Double)
}

private func bindSQLiteValue(
    _ value: SQLiteBindValue,
    to statement: OpaquePointer,
    index: Int32,
    handle: OpaquePointer
) throws {
    let result: Int32
    switch value {
    case .text(let string):
        result = sqlite3_bind_text(statement, index, string, -1, SQLITE_TRANSIENT)
    case .int(let number):
        result = sqlite3_bind_int(statement, index, number)
    case .double(let number):
        result = sqlite3_bind_double(statement, index, number)
    }
    guard result == SQLITE_OK else {
        throw CompendiumBrowseError.queryFailed(String(cString: sqlite3_errmsg(handle)))
    }
}

private func formatBrowseDuration(_ duration: TimeInterval) -> String {
    if duration < 1 {
        return String(format: "%.0f ms", duration * 1_000)
    }
    return String(format: "%.2f s", duration)
}

private func tableExists(handle: OpaquePointer, tableName: String) throws -> Bool {
    let sql = "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1"
    var stmt: OpaquePointer?
    guard sqlite3_prepare_v2(handle, sql, -1, &stmt, nil) == SQLITE_OK else {
        throw CompendiumBrowseError.queryFailed(String(cString: sqlite3_errmsg(handle)))
    }
    guard let statement = stmt else {
        throw CompendiumBrowseError.queryFailed("Failed to prepare sqlite_master table lookup.")
    }
    defer { sqlite3_finalize(statement) }
    sqlite3_bind_text(statement, 1, tableName, -1, SQLITE_TRANSIENT)
    return sqlite3_step(statement) == SQLITE_ROW
}

private func tableColumns(handle: OpaquePointer, tableName: String) throws -> Set<String> {
    var stmt: OpaquePointer?
    let sql = "PRAGMA table_info(\(tableName))"
    guard sqlite3_prepare_v2(handle, sql, -1, &stmt, nil) == SQLITE_OK else {
        throw CompendiumBrowseError.queryFailed(String(cString: sqlite3_errmsg(handle)))
    }
    guard let statement = stmt else {
        throw CompendiumBrowseError.queryFailed("Failed to prepare table_info for \(tableName).")
    }
    defer { sqlite3_finalize(statement) }

    var columns: Set<String> = []
    while sqlite3_step(statement) == SQLITE_ROW {
        if let name = sqlite3_column_text(statement, 1) {
            columns.insert(String(cString: name))
        }
    }
    return columns
}

private let SQLITE_TRANSIENT = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
