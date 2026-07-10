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
    public var cursor: CompendiumBrowseCursor?

    public init(
        search: String = "",
        stableOnly: Bool = false,
        catalogFilter: CompendiumCatalogFilter = .active,
        minScore: Float? = nil,
        limit: Int = 200,
        cursor: CompendiumBrowseCursor? = nil
    ) {
        self.search = search
        self.stableOnly = stableOnly
        self.catalogFilter = catalogFilter
        self.minScore = minScore
        self.limit = limit
        self.cursor = cursor
    }
}

public struct CompendiumBrowseCursor: Equatable, Sendable {
    public let score: Double?
    public let recordedAt: String
    public let databaseID: String

    public init(score: Double?, recordedAt: String, databaseID: String) {
        self.score = score
        self.recordedAt = recordedAt
        self.databaseID = databaseID
    }
}

public struct CompendiumBrowseIssue: Equatable, Sendable {
    public let databaseID: String?
    public let reason: String

    public init(databaseID: String?, reason: String) {
        self.databaseID = databaseID
        self.reason = reason
    }
}

public final class CompendiumBrowseCancellation: @unchecked Sendable {
    private let lock = NSLock()
    private var handle: OpaquePointer?
    private var cancelled = false

    public init() {}

    public func cancel() {
        lock.lock()
        cancelled = true
        if let handle {
            sqlite3_interrupt(handle)
        }
        lock.unlock()
    }

    fileprivate var isCancelled: Bool {
        lock.lock()
        defer { lock.unlock() }
        return cancelled
    }

    fileprivate func attach(_ handle: OpaquePointer) throws {
        lock.lock()
        defer { lock.unlock() }
        guard !cancelled else {
            throw CompendiumBrowseError.cancelled
        }
        self.handle = handle
    }

    fileprivate func detach(_ handle: OpaquePointer) {
        lock.lock()
        if self.handle == handle {
            self.handle = nil
        }
        lock.unlock()
    }
}

private let compendiumBrowseProgressHandler: @convention(c) (UnsafeMutableRawPointer?) -> Int32 = { context in
    guard let context else { return 1 }
    let cancellation = Unmanaged<CompendiumBrowseCancellation>
        .fromOpaque(context)
        .takeUnretainedValue()
    return cancellation.isCancelled ? 1 : 0
}

private struct CompendiumBrowseRow: Sendable {
    let databaseID: String
    let id: UUID
    let name: String
    let ownerID: String
    let runID: String
    let campaignID: String?
    let recordedAt: String
    let databaseScore: Double?
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

    private let databaseID: String
    private let databaseScore: Double?
    private let projection: ResolvedSpecimenProjection
    private let taxonomyValue: SpecimenTaxonomyRecord?

    public var runtimeCapabilities: [String] {
        projection.runtimeCapabilities
    }

    public var specimenManifest: SpecimenManifest? {
        projection.manifest
    }

    public var traitLabels: [String] {
        projection.traitLabels
    }

    public var taxonomy: SpecimenTaxonomyRecord? {
        taxonomyValue
    }

    public var previewSeed: Int {
        projection.creature.initialCondition.seed
    }

    public var previewParams: ResolvedParams {
        let creature = projection.creature
        return ResolvedParams(
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
    }

    public var creature: SavedCreature {
        projection.creature
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
        self.databaseID = id.uuidString
        self.databaseScore = score.map(Double.init)
        self.projection = ResolvedSpecimenProjection(
            manifest: specimenManifest,
            creature: creature,
            runtimeFamily: runtimeFamily,
            runtimeCapabilities: runtimeCapabilities,
            sourceMode: sourceMode,
            sourceAlgorithm: sourceAlgorithm,
            researchMetadata: specimenManifest?.researchMetadata,
            traitLabels: traitLabels,
        )
        self.taxonomyValue = taxonomy ?? specimenManifest?.taxonomy
    }

    fileprivate init(
        row: CompendiumBrowseRow,
        projection: ResolvedSpecimenProjection,
        qualityFlags: [String]
    ) {
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
        self.qualityFlags = qualityFlags
        self.specimenRecordID = row.specimenRecordID
        self.specimenSourceKind = row.specimenSourceKind
        self.databaseID = row.databaseID
        self.databaseScore = row.databaseScore
        self.projection = projection
        self.taxonomyValue = row.taxonomyRecord ?? projection.manifest?.taxonomy
    }

    fileprivate var browseCursor: CompendiumBrowseCursor {
        CompendiumBrowseCursor(
            score: databaseScore,
            recordedAt: recordedAt,
            databaseID: databaseID
        )
    }

    public var displayRun: String {
        if let hostId, !hostId.isEmpty {
            return "\(hostId) / \(runName)"
        }
        return runName
    }

    public var resolvedRunPath: String? {
        resolveRunArtifactPath(outputRoot: outputRoot, runDir: runDir, path: nil)
    }

    public var resolvedExportPath: String? {
        resolveRunArtifactPath(outputRoot: outputRoot, runDir: runDir, path: exportDir)
    }

    public static func == (lhs: CompendiumBrowseEntry, rhs: CompendiumBrowseEntry) -> Bool {
        lhs.id == rhs.id
    }

    public func hash(into hasher: inout Hasher) {
        hasher.combine(id)
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
    public let issues: [CompendiumBrowseIssue]
    public let skippedRowCount: Int
    public let nextCursor: CompendiumBrowseCursor?

    public init(
        entries: [CompendiumBrowseEntry],
        status: String,
        error: String?,
        issues: [CompendiumBrowseIssue] = [],
        skippedRowCount: Int = 0,
        nextCursor: CompendiumBrowseCursor? = nil
    ) {
        self.entries = entries
        self.status = status
        self.error = error
        self.issues = issues
        self.skippedRowCount = skippedRowCount
        self.nextCursor = nextCursor
    }
}

public enum CompendiumBrowseError: LocalizedError {
    case openFailed(String)
    case queryFailed(String)
    case invalidDatabase(String)
    case cancelled

    public var errorDescription: String? {
        switch self {
        case .openFailed(let message), .queryFailed(let message), .invalidDatabase(let message):
            return message
        case .cancelled:
            return "Compendium browse cancelled."
        }
    }
}

public func browseCompendium(
    path: String,
    query: CompendiumBrowseQuery,
    cancellation: CompendiumBrowseCancellation? = nil
) throws -> CompendiumBrowseResult {
    try throwIfBrowseCancelled(cancellation)
    var db: OpaquePointer?
    let openFlags = SQLITE_OPEN_READONLY | SQLITE_OPEN_FULLMUTEX
    if sqlite3_open_v2(path, &db, openFlags, nil) != SQLITE_OK {
        let message = db.flatMap { String(cString: sqlite3_errmsg($0)) } ?? "Failed to open compendium"
        sqlite3_close(db)
        throw CompendiumBrowseError.openFailed(message)
    }
    guard let handle = db else {
        throw CompendiumBrowseError.invalidDatabase("Failed to open compendium database.")
    }
    do {
        try cancellation?.attach(handle)
    } catch {
        sqlite3_close(handle)
        throw error
    }
    if let cancellation {
        sqlite3_progress_handler(
            handle,
            1_000,
            compendiumBrowseProgressHandler,
            Unmanaged.passUnretained(cancellation).toOpaque()
        )
    }
    defer {
        sqlite3_progress_handler(handle, 0, nil, nil)
        cancellation?.detach(handle)
        sqlite3_close(handle)
    }

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
    guard try tableExists(handle: handle, tableName: "exports") else {
        throw CompendiumBrowseError.invalidDatabase(
            "Compendium is missing exports. Rebuild the canonical compendium before browsing."
        )
    }
    try throwIfBrowseCancelled(cancellation)

    let trimmedSearch = query.search.trimmingCharacters(in: .whitespacesAndNewlines)
    let searchExpression = compendiumFTSQuery(trimmedSearch)
    if searchExpression != nil,
       try !tableExists(handle: handle, tableName: "creature_search") {
        throw CompendiumBrowseError.invalidDatabase(
            "Compendium search index is missing. Run the indexer once to migrate this database before searching."
        )
    }
    let limit = max(1, min(query.limit, 5_000))
    let fetchLimit = min(5_001, limit + 32)
    let startedAt = Date()

    var whereClauses: [String] = []
    var binds: [SQLiteBindValue] = []
    if let searchExpression {
        whereClauses.append("creature_search MATCH ?")
        binds.append(.text(searchExpression))
    }
    if query.stableOnly {
        whereClauses.append("c.is_stable = 1")
    }
    if let minScore = query.minScore {
        whereClauses.append("c.score >= ?")
        binds.append(.double(Double(minScore)))
    }
    if creatureColumns.contains("catalog_status") {
        switch query.catalogFilter {
        case .active:
            whereClauses.append("c.catalog_status IN ('active', 'protected')")
        case .quarantine:
            whereClauses.append("c.catalog_status = 'quarantine'")
        case .all:
            break
        }
    }
    whereClauses.append("EXISTS (SELECT 1 FROM specimens sx WHERE sx.id = c.canonical_specimen_id)")
    if let cursor = query.cursor {
        if let score = cursor.score {
            whereClauses.append("""
                (
                    c.score < ? OR c.score IS NULL OR
                    (c.score = ? AND (
                        c.recorded_at < ? OR
                        (c.recorded_at = ? AND c.id > ?)
                    ))
                )
                """)
            binds.append(contentsOf: [
                .double(score),
                .double(score),
                .text(cursor.recordedAt),
                .text(cursor.recordedAt),
                .text(cursor.databaseID),
            ])
        } else {
            whereClauses.append("""
                (
                    c.score IS NULL AND (
                        c.recorded_at < ? OR
                        (c.recorded_at = ? AND c.id > ?)
                    )
                )
                """)
            binds.append(contentsOf: [
                .text(cursor.recordedAt),
                .text(cursor.recordedAt),
                .text(cursor.databaseID),
            ])
        }
    }

    let searchJoin = searchExpression == nil
        ? ""
        : "JOIN creature_search ON creature_search.rowid = c.rowid"
    let whereSQL = whereClauses.isEmpty ? "" : "WHERE \(whereClauses.joined(separator: " AND "))"
    let filteredCTE = """
    WITH filtered AS (
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
        FROM creatures c
        \(searchJoin)
        \(whereSQL)
        ORDER BY c.score DESC, c.recorded_at DESC, c.id ASC
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
    LEFT JOIN exports lx ON lx.rowid = (
        SELECT e.rowid
        FROM exports e
        WHERE e.creature_id = c.id
        ORDER BY e.exported_at DESC, e.id DESC
        LIMIT 1
    )
    ORDER BY c.score DESC, c.recorded_at DESC, c.id ASC
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

    binds.append(.int(Int32(fetchLimit)))

    for (offset, value) in binds.enumerated() {
        try bindSQLiteValue(value, to: statement, index: Int32(offset + 1), handle: handle)
    }

    var entries: [CompendiumBrowseEntry] = []
    var issues: [CompendiumBrowseIssue] = []
    var skippedRowCount = 0
    var rawRowCount = 0
    var lastScannedCursor: CompendiumBrowseCursor?

    while true {
        let stepResult = sqlite3_step(statement)
        if stepResult == SQLITE_DONE {
            break
        }
        if stepResult == SQLITE_INTERRUPT || cancellation?.isCancelled == true {
            throw CompendiumBrowseError.cancelled
        }
        guard stepResult == SQLITE_ROW else {
            throw CompendiumBrowseError.queryFailed(String(cString: sqlite3_errmsg(handle)))
        }
        rawRowCount += 1
        guard let idText = sqlite3_column_text(statement, 0) else {
            recordBrowseIssue(
                CompendiumBrowseIssue(databaseID: nil, reason: "Missing creatures.id."),
                issues: &issues,
                skippedRowCount: &skippedRowCount
            )
            continue
        }
        let idString = String(cString: idText)
        lastScannedCursor = CompendiumBrowseCursor(
            score: columnDouble(statement, index: 6),
            recordedAt: columnText(statement, index: 5) ?? "",
            databaseID: idString
        )
        guard
            let specimenRecordID = columnText(statement, index: 34),
            let specimenSourceKind = columnText(statement, index: 35)
        else {
            recordBrowseIssue(
                CompendiumBrowseIssue(
                    databaseID: idString,
                    reason: "Missing canonical specimen identity."
                ),
                issues: &issues,
                skippedRowCount: &skippedRowCount
            )
            continue
        }

        guard let id = UUID(uuidString: idString) else {
            recordBrowseIssue(
                CompendiumBrowseIssue(databaseID: idString, reason: "creatures.id is not a UUID."),
                issues: &issues,
                skippedRowCount: &skippedRowCount
            )
            continue
        }
        let row = CompendiumBrowseRow(
            databaseID: idString,
            id: id,
            name: columnText(statement, index: 1) ?? "Unnamed",
            ownerID: columnText(statement, index: 2) ?? "unknown",
            runID: columnText(statement, index: 3) ?? "unknown",
            campaignID: columnText(statement, index: 4),
            recordedAt: columnText(statement, index: 5) ?? "",
            databaseScore: columnDouble(statement, index: 6),
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

        do {
            let decoded = try decodeCompendiumBrowseRow(row)
            entries.append(
                CompendiumBrowseEntry(
                    row: row,
                    projection: decoded.projection,
                    qualityFlags: decoded.qualityFlags
                )
            )
        } catch {
            recordBrowseIssue(
                CompendiumBrowseIssue(databaseID: idString, reason: error.localizedDescription),
                issues: &issues,
                skippedRowCount: &skippedRowCount
            )
        }
    }

    let hasUnreturnedEntries = entries.count > limit
    if hasUnreturnedEntries {
        entries.removeLast(entries.count - limit)
    }
    let nextCursor = hasUnreturnedEntries
        ? entries.last?.browseCursor
        : (rawRowCount == fetchLimit ? lastScannedCursor : nil)
    let status = "Loaded \(entries.count) creatures in \(formatBrowseDuration(Date().timeIntervalSince(startedAt)))"
    let warning: String?
    if skippedRowCount > 0 {
        let firstReason = issues.first.map { " First issue: \($0.reason)" } ?? ""
        warning = "Quarantined \(skippedRowCount) malformed canonical row\(skippedRowCount == 1 ? "" : "s") from this result.\(firstReason)"
    } else {
        warning = nil
    }
    return CompendiumBrowseResult(
        entries: entries,
        status: status,
        error: warning,
        issues: issues,
        skippedRowCount: skippedRowCount,
        nextCursor: nextCursor
    )
}

private struct DecodedCompendiumBrowseRow {
    let projection: ResolvedSpecimenProjection
    let qualityFlags: [String]
}

private struct CompendiumRowDecodeError: LocalizedError {
    let field: String
    let underlying: Error

    var errorDescription: String? {
        "Invalid \(field): \(underlying.localizedDescription)"
    }
}

private func decodeCompendiumBrowseRow(_ row: CompendiumBrowseRow) throws -> DecodedCompendiumBrowseRow {
    let decoder = JSONDecoder()
    let genotype: KernelParams = try decodeRequiredJSON(
        row.genotypeJSON,
        field: "creatures.genotype_json",
        decoder: decoder
    )
    let initialCondition: InitConfig = try decodeRequiredJSON(
        row.initialConditionJSON,
        field: "creatures.initial_condition_json",
        decoder: decoder
    )
    let metrics: SimulationMetrics = try decodeRequiredJSON(
        row.metricsJSON,
        field: "creatures.metrics_json",
        decoder: decoder
    )
    let manifest: SpecimenManifest? = try decodeOptionalJSON(
        row.specimenManifestJSON,
        field: "specimens.specimen_manifest_json",
        decoder: decoder
    )
    let sweep: [String: Double]? = try decodeOptionalJSON(
        row.sweepJSON,
        field: "creatures.sweep_json",
        decoder: decoder
    )
    let scoreWeights: [String: Float]? = try decodeOptionalJSON(
        row.scoreWeightsJSON,
        field: "creatures.score_weights_json",
        decoder: decoder
    )
    let runtimeCapabilities: [String]? = try decodeOptionalJSON(
        row.runtimeCapabilitiesJSON,
        field: "specimens.runtime_capabilities_json",
        decoder: decoder
    )
    let traitLabels: [String]? = try decodeOptionalJSON(
        row.traitLabelsJSON,
        field: "creatures.trait_labels_json",
        decoder: decoder
    )
    let qualityFlags: [String] = try decodeOptionalJSON(
        row.qualityFlagsJSON,
        field: "creatures.quality_flags_json",
        decoder: decoder
    ) ?? []

    return DecodedCompendiumBrowseRow(
        projection: resolveSpecimenProjection(
            id: row.id,
            name: row.name,
            ownerId: row.ownerID,
            manifest: manifest,
            fallbackGenotype: genotype,
            fallbackInitialCondition: initialCondition,
            fallbackMetrics: metrics,
            sweep: sweep,
            score: row.score,
            scoreWeights: scoreWeights,
            fallbackRuntimeFamily: row.runtimeFamily,
            fallbackRuntimeCapabilities: runtimeCapabilities,
            fallbackSourceMode: row.sourceMode,
            fallbackSourceAlgorithm: row.sourceAlgorithm,
            fallbackTraitLabels: traitLabels
        ),
        qualityFlags: qualityFlags
    )
}

private func decodeRequiredJSON<T: Decodable>(
    _ value: String?,
    field: String,
    decoder: JSONDecoder
) throws -> T {
    guard let value, !value.isEmpty else {
        throw CompendiumRowDecodeError(
            field: field,
            underlying: CompendiumBrowseError.invalidDatabase("Required value is missing.")
        )
    }
    do {
        return try decoder.decode(T.self, from: Data(value.utf8))
    } catch {
        throw CompendiumRowDecodeError(field: field, underlying: error)
    }
}

private func decodeOptionalJSON<T: Decodable>(
    _ value: String?,
    field: String,
    decoder: JSONDecoder
) throws -> T? {
    guard let value, !value.isEmpty else { return nil }
    do {
        return try decoder.decode(T.self, from: Data(value.utf8))
    } catch {
        throw CompendiumRowDecodeError(field: field, underlying: error)
    }
}

private func recordBrowseIssue(
    _ issue: CompendiumBrowseIssue,
    issues: inout [CompendiumBrowseIssue],
    skippedRowCount: inout Int
) {
    skippedRowCount += 1
    if issues.count < 8 {
        issues.append(issue)
    }
}

private func compendiumFTSQuery(_ value: String) -> String? {
    let tokens = value
        .split { !$0.isLetter && !$0.isNumber }
        .prefix(8)
        .map { String($0.prefix(64)) }
        .filter { !$0.isEmpty }
    guard !tokens.isEmpty else { return nil }
    return tokens.map { "\"\($0)\"*" }.joined(separator: " AND ")
}

private func throwIfBrowseCancelled(_ cancellation: CompendiumBrowseCancellation?) throws {
    if cancellation?.isCancelled == true {
        throw CompendiumBrowseError.cancelled
    }
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
