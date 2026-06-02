import ArgumentParser
import Foundation
import LeniaArchive
import LeniaCore
import SQLite3

struct IndexCommand: ParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "ingest",
        abstract: "Build or update a SQLite compendium from run outputs"
    )

    @Option(name: [.customLong("output-root"), .customLong("output-roots")], parsing: .upToNextOption, help: "Output root path(s) containing hosts/<node>/runs/<runId>")
    var outputRoots: [String] = []

    @Option(name: .customLong("run-dir"), parsing: .upToNextOption, help: "Run directory/directories to index")
    var runDirs: [String] = []

    @Option(name: [.customLong("db"), .customLong("db-path")], help: "SQLite database path (default: <output-root>/compendium.sqlite or <run-dir>/compendium.sqlite)")
    var dbPath: String?

    @Flag(name: .long, help: "Rebuild database from scratch")
    var rebuild: Bool = false

    @Flag(name: .long, help: "Include results.jsonl (not just library/exports)")
    var includeResults: Bool = false

    @Flag(name: .long, help: "Repair schema and backfill specimen contracts without ingesting run outputs")
    var repairOnly: Bool = false

    @OptionGroup
    var warehouseRefresh: WarehouseRefreshOptions

    @Flag(name: .long, help: "Print summary stats after indexing")
    var stats: Bool = false

    func run() throws {
        let resolvedPlan = try resolveCompendiumIngestPlan(
            outputRoots: outputRoots,
            runDirs: runDirs,
            dbPath: dbPath,
            repairOnly: repairOnly
        )
        let plan = CompendiumIngestPlan(
            runInputs: resolvedPlan.runInputs,
            resolvedDBPath: try resolveArtifactPath(resolvedPlan.resolvedDBPath, dossier: dossierName)
        )
        let indexer = try executeCompendiumIngest(
            plan: plan,
            rebuild: rebuild,
            includeResults: includeResults,
            repairOnly: repairOnly
        )
        let warehouseResult = try refreshWarehouseProjection(
            compendiumPath: plan.resolvedDBPath,
            warehousePath: try warehouseRefresh.warehouse.map {
                try resolveArtifactPath($0, dossier: dossierName)
            },
            warehouseTopology: warehouseRefresh.warehouseTopology,
            defaultEnabled: false
        )

        if stats {
            let summary = try indexer.stats()
            print("Compendium: \(summary)")
            if let warehouseResult {
                print(
                    "Warehouse: study=\(warehouseResult.studyId) axes=\(warehouseResult.axesUpdated) status=\(warehouseResult.statusUpdated) anatomy=\(warehouseResult.anatomyUpdated)"
                )
            }
        }
    }
}

final class SQLiteIndexer {
    private static let schemaVersion = compendiumSchemaVersion
    private let path: String
    private let db: SQLiteDB
    private let encoder: JSONEncoder
    private let formatter: ISO8601DateFormatter

    private static func exportRecordId(runKey: String, exportDir: String) -> String {
        "\(runKey)|export|\(exportDir)"
    }

    private static func ecologyRunRecordId(runKey: String, campaignId: String?, trialId: String) -> String {
        if let campaignId {
            return "\(runKey)|ecology|\(campaignId)|\(trialId)"
        }
        return "\(runKey)|ecology|\(trialId)"
    }

    init(path: String, rebuild: Bool) throws {
        self.path = path
        self.db = try SQLiteDB(path: path)
        self.encoder = JSONEncoder()
        self.encoder.outputFormatting = [.sortedKeys]
        self.formatter = ISO8601DateFormatter()
        self.formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

        if rebuild {
            try db.exec("DROP TABLE IF EXISTS ingest_state")
            try db.exec("DROP TABLE IF EXISTS ecology_runs")
            try db.exec("DROP TABLE IF EXISTS transition_edges")
            try db.exec("DROP TABLE IF EXISTS perturbation_trials")
            try db.exec("DROP TABLE IF EXISTS attractor_memberships")
            try db.exec("DROP TABLE IF EXISTS attractor_nodes")
            try db.exec("DROP TABLE IF EXISTS specimens")
            try db.exec("DROP TABLE IF EXISTS exports")
            try db.exec("DROP TABLE IF EXISTS results")
            try db.exec("DROP TABLE IF EXISTS creatures")
            try db.exec("DROP TABLE IF EXISTS runs")
            try db.exec("DROP TABLE IF EXISTS campaigns")
            try db.exec("DROP TABLE IF EXISTS compendium_meta")
        }

        try db.exec("PRAGMA foreign_keys = ON")
        try db.exec("PRAGMA journal_mode = WAL")
        try db.exec("PRAGMA synchronous = NORMAL")

        try ensureSchema()
    }

    func ingestRun(input: RunInput, includeResults: Bool) throws {
        let runDir = input.runDir
        let runDirStored = input.runDirRelative ?? runDir.path
        try upsertRun(
            runKey: input.runKey,
            runName: input.runId,
            runDir: runDirStored,
            hostId: input.hostId,
            outputRoot: input.outputRoot?.path
        )

        try ingestRunArtifacts(
            directory: runDir,
            runKey: input.runKey,
            campaignId: nil,
            runDir: runDir,
            includeResults: includeResults,
            resultsCandidates: ["overall/results.jsonl", "results.jsonl"],
            activityPath: "overall/activity.jsonl"
        )

        let campaignsDir = runDir.appendingPathComponent("campaigns", isDirectory: true)
        var isDir: ObjCBool = false
        if FileManager.default.fileExists(atPath: campaignsDir.path, isDirectory: &isDir), isDir.boolValue {
            let campaignDirs = try FileManager.default.contentsOfDirectory(
                at: campaignsDir,
                includingPropertiesForKeys: [.isDirectoryKey],
                options: .skipsHiddenFiles
            )
            for campaign in campaignDirs where campaign.hasDirectoryPath {
                try ingestRunArtifacts(
                    directory: campaign,
                    runKey: input.runKey,
                    campaignId: campaign.lastPathComponent,
                    runDir: runDir,
                    includeResults: includeResults,
                    resultsCandidates: ["results.jsonl"],
                    activityPath: "activity.jsonl"
                )
            }
        }
    }

    func stats() throws -> String {
        let runs = try db.scalarInt("SELECT COUNT(*) FROM runs")
        let creatures = try db.scalarInt("SELECT COUNT(*) FROM creatures")
        let exports = try db.scalarInt("SELECT COUNT(*) FROM exports")
        let results = try db.scalarInt("SELECT COUNT(*) FROM results")
        let ecologyRuns = try db.scalarInt("SELECT COUNT(*) FROM ecology_runs")
        let specimens = try db.scalarInt("SELECT COUNT(*) FROM specimens")
        let attractorNodes = try db.scalarInt("SELECT COUNT(*) FROM attractor_nodes")
        let perturbationTrials = try db.scalarInt("SELECT COUNT(*) FROM perturbation_trials")
        let transitionEdges = try db.scalarInt("SELECT COUNT(*) FROM transition_edges")
        return "runs=\(runs) creatures=\(creatures) specimens=\(specimens) exports=\(exports) results=\(results) ecology_runs=\(ecologyRuns) attractors=\(attractorNodes) trials=\(perturbationTrials) edges=\(transitionEdges)"
    }

    func ensureCanonicalSpecimenCoverage() throws {
        try repairCurrentSchema()
        try repairCanonicalCreatureLinks()
        let unresolvedGaps = try backfillStrictSpecimensFromIndexedArtifacts()
        if !unresolvedGaps.isEmpty {
            try backfillMissingStrictSpecimens(gaps: unresolvedGaps)
        }
        try repairCanonicalCreatureLinks()
        try validateCanonicalSpecimenCoverage()
    }

    private func ingestRunArtifacts(
        directory: URL,
        runKey: String,
        campaignId: String?,
        runDir: URL,
        includeResults: Bool,
        resultsCandidates: [String],
        activityPath: String?
    ) throws {
        if let libraryIndex = existingArtifact(in: directory, relativePath: "library/index.jsonl") {
            try ingestLibraryIndex(path: libraryIndex, runKey: runKey, runDir: runDir)
        }
        if let exportsIndex = existingArtifact(in: directory, relativePath: "exports/index.jsonl") {
            try ingestExportIndex(path: exportsIndex, runKey: runKey, runDir: runDir)
        }
        if let ecologyRunsIndex = existingArtifact(in: directory, relativePath: "ecology-runs/index.jsonl") {
            try ingestEcologyRuns(path: ecologyRunsIndex, runKey: runKey, campaignId: campaignId, runDir: runDir)
        }
        if includeResults,
           let resultsURL = firstExistingArtifact(in: directory, relativePaths: resultsCandidates) {
            try ingestResults(path: resultsURL, runKey: runKey, campaignId: campaignId, runDir: runDir)
        }
        if let activityPath,
           let activityURL = existingArtifact(in: directory, relativePath: activityPath) {
            try ingestActivitySummary(path: activityURL, runKey: runKey, campaignId: campaignId, runDir: runDir)
        }
    }

    private func existingArtifact(in directory: URL, relativePath: String) -> URL? {
        let artifactURL = directory.appendingPathComponent(relativePath)
        return FileManager.default.fileExists(atPath: artifactURL.path) ? artifactURL : nil
    }

    private func firstExistingArtifact(in directory: URL, relativePaths: [String]) -> URL? {
        for relativePath in relativePaths {
            if let artifactURL = existingArtifact(in: directory, relativePath: relativePath) {
                return artifactURL
            }
        }
        return nil
    }

    private func repairCanonicalCreatureLinks() throws {
        try db.withImmediateTransaction {
            try backfillCanonicalCreatureLinks()
            try repairDuplicateCanonicalCreatureLinks()
        }
    }

    private func validateCanonicalSpecimenCoverage() throws {
        let residual = try missingCanonicalCreatureGaps()
        guard residual.isEmpty else {
            throw ValidationError(canonicalGapReport(for: residual))
        }
        let duplicateLinks = try duplicateCanonicalCreatureLinkCount()
        guard duplicateLinks == 0 else {
            throw ValidationError(
                "Canonical specimen repair left \(duplicateLinks) duplicate creature->specimen links. Repair failed because every indexed creature must resolve to a unique strict specimen."
            )
        }
    }

    private func backfillCanonicalCreatureLinks() throws {
        try db.exec("""
            UPDATE creatures
            SET canonical_specimen_id = NULL
            WHERE canonical_specimen_id IS NOT NULL
              AND canonical_specimen_id NOT IN (SELECT id FROM specimens)
        """)
        try db.exec("""
            WITH canonical_candidates AS (
                SELECT
                    c.id AS creature_id,
                    s.id AS specimen_id,
                    0 AS match_rank,
                    CASE s.source_kind
                        WHEN 'result' THEN 0
                        WHEN 'backfill' THEN 1
                        WHEN 'library' THEN 2
                        ELSE 3
                    END AS source_rank,
                    CASE WHEN s.creature_id = c.id THEN 0 ELSE 1 END AS provenance_rank,
                    COALESCE(s.recorded_at, '') AS recorded_at
                FROM creatures c
                JOIN specimens s
                  ON s.run_id = c.run_id
                 AND COALESCE(s.campaign_id, '') = COALESCE(c.campaign_id, '')
                 AND COALESCE(s.init_seed, -1) = COALESCE(c.init_seed, -1)
                WHERE c.canonical_specimen_id IS NULL

                UNION ALL

                SELECT
                    c.id AS creature_id,
                    s.id AS specimen_id,
                    1 AS match_rank,
                    CASE s.source_kind
                        WHEN 'backfill' THEN 0
                        WHEN 'library' THEN 1
                        WHEN 'result' THEN 2
                        ELSE 3
                    END AS source_rank,
                    0 AS provenance_rank,
                    COALESCE(s.recorded_at, '') AS recorded_at
                FROM creatures c
                JOIN specimens s
                  ON s.creature_id = c.id
                WHERE c.canonical_specimen_id IS NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM specimens seed
                      WHERE seed.run_id = c.run_id
                        AND COALESCE(seed.campaign_id, '') = COALESCE(c.campaign_id, '')
                        AND COALESCE(seed.init_seed, -1) = COALESCE(c.init_seed, -1)
                  )
            ),
            best_links AS (
                SELECT creature_id, specimen_id
                FROM (
                    SELECT
                        creature_id,
                        specimen_id,
                        ROW_NUMBER() OVER (
                            PARTITION BY creature_id
                            ORDER BY
                                match_rank,
                                source_rank,
                                provenance_rank,
                                recorded_at DESC,
                                specimen_id ASC
                        ) AS rank
                    FROM canonical_candidates
                )
                WHERE rank = 1
            )
            UPDATE creatures
            SET canonical_specimen_id = best_links.specimen_id
            FROM best_links
            WHERE creatures.id = best_links.creature_id
        """)
    }

    private func repairDuplicateCanonicalCreatureLinks() throws {
        try db.exec("""
            UPDATE specimens
            SET result_id = NULL
            WHERE id LIKE 'creature:%'
              AND result_id IS NOT NULL
        """)
        try db.exec("""
            INSERT OR REPLACE INTO specimens (
                id,
                result_id,
                creature_id,
                run_id,
                campaign_id,
                source_kind,
                recorded_at,
                seed,
                init_seed,
                source_mode,
                source_algorithm,
                config_hash,
                initial_condition_family,
                descriptor_version,
                symmetry_policy,
                genotype_descriptor_json,
                terminal_descriptor_json,
                trajectory_descriptor_json,
                activity_path,
                fingerprint_path,
                provenance_json,
                runtime_family,
                runtime_capabilities_json,
                specimen_manifest_json
            )
            SELECT
                'creature:' || c.id,
                NULL,
                c.id,
                s.run_id,
                s.campaign_id,
                'backfill',
                COALESCE(c.recorded_at, s.recorded_at),
                s.seed,
                s.init_seed,
                COALESCE(c.source_mode, s.source_mode),
                COALESCE(c.source_algorithm, s.source_algorithm),
                COALESCE(c.config_hash, s.config_hash),
                s.initial_condition_family,
                s.descriptor_version,
                s.symmetry_policy,
                s.genotype_descriptor_json,
                s.terminal_descriptor_json,
                s.trajectory_descriptor_json,
                s.activity_path,
                s.fingerprint_path,
                CASE
                    WHEN COALESCE(s.provenance_json, '') != '' AND json_valid(s.provenance_json)
                    THEN json_set(
                        s.provenance_json,
                        '$.sourceKind', 'backfill',
                        '$.sourceRef', 'creature:' || c.id
                    )
                    ELSE s.provenance_json
                END,
                s.runtime_family,
                s.runtime_capabilities_json,
                CASE
                    WHEN COALESCE(s.specimen_manifest_json, '') != '' AND json_valid(s.specimen_manifest_json)
                    THEN json_set(
                        s.specimen_manifest_json,
                        '$.specimenID', 'creature:' || c.id,
                        '$.creatureID', c.id,
                        '$.sourceKind', 'backfill'
                    )
                    ELSE s.specimen_manifest_json
                END
            FROM creatures c
            JOIN specimens s
              ON s.id = c.canonical_specimen_id
            WHERE c.canonical_specimen_id IN (
                SELECT canonical_specimen_id
                FROM creatures
                WHERE canonical_specimen_id IS NOT NULL
                GROUP BY canonical_specimen_id
                HAVING COUNT(*) > 1
            )
        """)
        try db.exec("""
            UPDATE creatures
            SET canonical_specimen_id = 'creature:' || id
            WHERE canonical_specimen_id IN (
                SELECT canonical_specimen_id
                FROM creatures
                WHERE canonical_specimen_id IS NOT NULL
                GROUP BY canonical_specimen_id
                HAVING COUNT(*) > 1
            )
        """)
    }

    private func duplicateCanonicalCreatureLinkCount() throws -> Int {
        try db.scalarInt("""
            SELECT COUNT(*)
            FROM (
                SELECT canonical_specimen_id
                FROM creatures
                WHERE canonical_specimen_id IS NOT NULL
                GROUP BY canonical_specimen_id
                HAVING COUNT(*) > 1
            )
        """)
    }

    private func missingCanonicalCreatureGaps() throws -> [CanonicalCreatureGap] {
        guard try db.tableExists("creatures") else {
            return []
        }
        let sql = """
            SELECT
                c.id,
                c.name,
                c.owner_id,
                c.run_id,
                c.campaign_id,
                c.recorded_at,
                c.init_seed,
                c.score,
                c.config_hash,
                c.source_mode,
                c.source_algorithm,
                c.research_metadata_json,
                c.genotype_json,
                c.initial_condition_json,
                c.metrics_json,
                c.sweep_json,
                c.score_weights_json,
                c.specimen_manifest_json
            FROM creatures c
            WHERE c.canonical_specimen_id IS NULL
              AND c.genotype_json IS NOT NULL
              AND c.initial_condition_json IS NOT NULL
              AND c.metrics_json IS NOT NULL
            ORDER BY c.run_id, COALESCE(c.campaign_id, ''), c.init_seed, c.id
        """
        let stmt = try db.prepare(sql)
        defer { sqlite3_finalize(stmt) }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .deferredToDate
        var gaps: [CanonicalCreatureGap] = []
        while sqlite3_step(stmt) == SQLITE_ROW {
            guard let creatureID = columnText(stmt, index: 0),
                  let name = columnText(stmt, index: 1),
                  let ownerID = columnText(stmt, index: 2),
                  let runID = columnText(stmt, index: 3) else {
                throw SQLiteIndexError.sqliteError(message: "Invalid creature row while resolving canonical specimen gaps.")
            }
            let score = sqlite3_column_type(stmt, 7) == SQLITE_NULL ? nil : Float(sqlite3_column_double(stmt, 7))
            let manifest = try decodeOptionalJSONString(
                columnText(stmt, index: 17),
                as: SpecimenManifest.self,
                decoder: decoder
            )
            let researchMetadata = try decodeOptionalJSONString(
                columnText(stmt, index: 11),
                as: [String: AnyCodable].self,
                decoder: decoder
            )
            guard let genotypeJSON = columnText(stmt, index: 12),
                  let initialConditionJSON = columnText(stmt, index: 13),
                  let metricsJSON = columnText(stmt, index: 14) else {
                if manifest == nil {
                    continue
                }
                throw SQLiteIndexError.sqliteError(message: "Invalid creature row while resolving canonical specimen gaps.")
            }
            let projection = resolveSpecimenProjection(
                id: UUID(uuidString: creatureID) ?? deterministicResearchUUID(creatureID),
                name: name,
                ownerId: ownerID,
                manifest: manifest,
                fallbackGenotype: try decodeJSONString(genotypeJSON, as: KernelParams.self, decoder: decoder),
                fallbackInitialCondition: try decodeJSONString(initialConditionJSON, as: InitConfig.self, decoder: decoder),
                fallbackMetrics: try decodeJSONString(metricsJSON, as: SimulationMetrics.self, decoder: decoder),
                sweep: try decodeOptionalJSONString(columnText(stmt, index: 15), as: [String: Double].self, decoder: decoder),
                score: score,
                scoreWeights: try decodeOptionalJSONString(columnText(stmt, index: 16), as: [String: Float].self, decoder: decoder),
                fallbackConfigHash: columnText(stmt, index: 8),
                fallbackSourceMode: columnText(stmt, index: 9),
                fallbackSourceAlgorithm: columnText(stmt, index: 10),
                fallbackResearchMetadata: researchMetadata
            )
            guard let recordedAt = columnText(stmt, index: 5)
                ?? manifest?.recordedAt.map(formatter.string(from:)) else {
                throw SQLiteIndexError.sqliteError(message: "Invalid creature row while resolving canonical specimen gaps.")
            }
            gaps.append(CanonicalCreatureGap(
                creatureID: creatureID,
                runID: runID,
                campaignID: columnText(stmt, index: 4),
                recordedAt: recordedAt,
                configHash: projection.creature.configHash,
                sourceMode: projection.sourceMode,
                sourceAlgorithm: projection.sourceAlgorithm,
                researchMetadata: projection.researchMetadata,
                creature: projection.creature
            ))
        }
        return gaps
    }

    private struct ResolvableCanonicalGap {
        let gap: CanonicalCreatureGap
        let runDir: URL
    }

    private func resolvableCanonicalGaps(
        recheckCanonicalNeed: Bool = false,
    ) throws -> [ResolvableCanonicalGap] {
        let gaps = try missingCanonicalCreatureGaps()
        guard !gaps.isEmpty else {
            return []
        }

        var resolved: [ResolvableCanonicalGap] = []
        resolved.reserveCapacity(gaps.count)
        var runCache: [String: CanonicalRunArtifactRecord] = [:]
        for gap in gaps {
            if recheckCanonicalNeed, try !creatureNeedsCanonicalSpecimen(gap.creatureID) {
                continue
            }
            guard let runRecord = try runArtifactRecord(runID: gap.runID, cache: &runCache),
                  let resolvedRunDir = resolveCompendiumArtifactPath(
                    outputRoot: runRecord.outputRoot,
                    runDir: runRecord.runDir,
                    path: nil
                  ) else {
                continue
            }
            resolved.append(
                ResolvableCanonicalGap(
                    gap: gap,
                    runDir: URL(fileURLWithPath: resolvedRunDir, isDirectory: true)
                )
            )
        }
        return resolved
    }

    private func backfillStrictSpecimensFromIndexedArtifacts() throws -> [CanonicalCreatureGap] {
        var runCache: [String: CanonicalRunArtifactRecord] = [:]
        var libraryCache: [String: [String: ResearchLibraryEntry]] = [:]
        var unresolved: [CanonicalCreatureGap] = []

        for target in try resolvableCanonicalGaps(recheckCanonicalNeed: true) {
            if let specimenID = try backfillStrictSpecimenFromExportMetadata(
                target,
                cache: &runCache
            ) ?? backfillStrictSpecimenFromLibraryArtifact(
                target,
                cache: &runCache,
                libraryCache: &libraryCache
            ) {
                try setCanonicalSpecimenLink(creatureID: target.gap.creatureID, specimenID: specimenID)
            } else {
                unresolved.append(target.gap)
            }
        }

        return unresolved
    }

    private func backfillStrictSpecimenFromExportMetadata(
        _ target: ResolvableCanonicalGap,
        cache: inout [String: CanonicalRunArtifactRecord]
    ) throws -> String? {
        guard let exportRecord = try exportReplayRecord(for: target.gap, cache: &cache),
              let metadataURL = exportMetadataURL(for: exportRecord),
              FileManager.default.fileExists(atPath: metadataURL.path) else {
            return nil
        }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .deferredToDate
        let metadata = try decodeCreatureExportMetadata(
            Data(contentsOf: metadataURL),
            decoder: decoder,
            fallbackBundleKind: exportRecord.bundleKind
        )
        return try upsertSpecimenFromExportMetadata(
            metadata: metadata,
            gap: target.gap,
            runDir: target.runDir,
            sourcePath: metadataURL
        )
    }

    private func backfillStrictSpecimenFromLibraryArtifact(
        _ target: ResolvableCanonicalGap,
        cache: inout [String: CanonicalRunArtifactRecord],
        libraryCache: inout [String: [String: ResearchLibraryEntry]]
    ) throws -> String? {
        guard let indexURL = try libraryIndexURL(for: target.gap, cache: &cache) else {
            return nil
        }

        let key = indexURL.path
        let entries: [String: ResearchLibraryEntry]
        if let cached = libraryCache[key] {
            entries = cached
        } else {
            let resolved = try loadResearchLibraryEntries(at: indexURL)
            libraryCache[key] = resolved
            entries = resolved
        }

        guard let entry = entries[target.gap.creatureID],
              entry.creature.descriptorBundle != nil else {
            return nil
        }

        return try upsertSpecimenFromCreature(
            creature: entry.creature,
            entry: entry,
            runKey: target.gap.runID,
            runDir: target.runDir,
            sourcePath: indexURL
        )
    }

    private func backfillMissingStrictSpecimens(gaps: [CanonicalCreatureGap]) throws {
        let backfillRoot = try canonicalizationBackfillRoot()
        var runCache: [String: CanonicalRunArtifactRecord] = [:]
        var pending: [CanonicalizationPendingReplay] = []
        pending.reserveCapacity(gaps.count)
        for gap in gaps {
            guard try creatureNeedsCanonicalSpecimen(gap.creatureID) else {
                continue
            }
            let resolvedInput = try canonicalizationReplayInput(for: gap, cache: &runCache)
            let backfillRunID = canonicalizationRunID(for: gap)
            let artifactDirectory = backfillRoot.appendingPathComponent(backfillRunID, isDirectory: true)
            pending.append(CanonicalizationPendingReplay(
                gap: gap,
                resolvedInput: resolvedInput,
                backfillRunID: backfillRunID,
                artifactDirectory: artifactDirectory
            ))
        }
        guard !pending.isEmpty else {
            return
        }

        let allFlowReplays = pending.allSatisfy { $0.resolvedInput.executionPlan.isFlow }
        let maxConcurrency = allFlowReplays ? 1 : min(max(ProcessInfo.processInfo.activeProcessorCount / 2, 1), 4)
        if maxConcurrency == 1 || pending.count == 1 {
            for item in pending {
                let execution = try executeReplayResolvedInput(item.resolvedInput, runID: item.backfillRunID)
                try FileManager.default.createDirectory(at: item.artifactDirectory, withIntermediateDirectories: true)
                try Self.persistCanonicalizationArtifacts(
                    directory: item.artifactDirectory,
                    execution: execution,
                    resolvedInput: item.resolvedInput
                )
                if let specimenID = try upsertBackfilledSpecimen(
                    gap: item.gap,
                    resolvedInput: item.resolvedInput,
                    execution: execution,
                    artifactDirectory: item.artifactDirectory
                ) {
                    try setCanonicalSpecimenLink(creatureID: item.gap.creatureID, specimenID: specimenID)
                }
            }
            return
        }

        for chunkStart in stride(from: 0, to: pending.count, by: maxConcurrency) {
            let chunk = Array(pending[chunkStart ..< min(chunkStart + maxConcurrency, pending.count)])
            let group = DispatchGroup()
            let state = CanonicalizationChunkState(resultCount: chunk.count)

            for (index, item) in chunk.enumerated() {
                group.enter()
                DispatchQueue.global(qos: .userInitiated).async {
                    defer { group.leave() }

                    if state.shouldSkip {
                        return
                    }

                    do {
                        let execution = try executeReplayResolvedInput(item.resolvedInput, runID: item.backfillRunID)
                        try FileManager.default.createDirectory(at: item.artifactDirectory, withIntermediateDirectories: true)
                        try Self.persistCanonicalizationArtifacts(
                            directory: item.artifactDirectory,
                            execution: execution,
                            resolvedInput: item.resolvedInput
                        )
                        state.record(
                            CanonicalizationBackfillProduct(
                            gap: item.gap,
                            resolvedInput: item.resolvedInput,
                            execution: execution,
                            artifactDirectory: item.artifactDirectory
                            ),
                            at: index
                        )
                    } catch {
                        state.record(error: error)
                    }
                }
            }

            group.wait()
            if let firstError = state.firstError {
                throw firstError
            }
            for result in state.results {
                if let specimenID = try upsertBackfilledSpecimen(
                    gap: result.gap,
                    resolvedInput: result.resolvedInput,
                    execution: result.execution,
                    artifactDirectory: result.artifactDirectory
                ) {
                    try setCanonicalSpecimenLink(creatureID: result.gap.creatureID, specimenID: specimenID)
                }
            }
        }
    }

    private func creatureNeedsCanonicalSpecimen(_ creatureID: String) throws -> Bool {
        let stmt = try db.prepare("SELECT canonical_specimen_id FROM creatures WHERE id = ? LIMIT 1")
        defer { sqlite3_finalize(stmt) }
        db.bindText(stmt, index: 1, value: creatureID)
        guard sqlite3_step(stmt) == SQLITE_ROW else {
            return false
        }
        return columnText(stmt, index: 0) == nil
    }

    private func canonicalizationReplayInput(
        for gap: CanonicalCreatureGap,
        cache: inout [String: CanonicalRunArtifactRecord]
    ) throws -> ReplayResolvedInput {
        if let exportRecord = try exportReplayRecord(for: gap, cache: &cache) {
            return try canonicalizationReplayInput(from: exportRecord, gap: gap)
        }
        if let metadataReplayInput = try replayInputFromResearchMetadata(for: gap) {
            return metadataReplayInput
        }
        if let flowReplayInput = try canonicalizationFlowReplayInput(for: gap) {
            return flowReplayInput
        }
        let mode = normalized(gap.sourceMode) ?? "unknown"
        if mode == "qd-2024" {
            return try qd24ReplayInput(for: gap, cache: &cache)
        }
        throw ValidationError("Cannot backfill strict specimen for \(gap.creature.name) (\(mode)); no replay export bundle or dedicated adapter is available.")
    }

    private func exportReplayRecord(
        for gap: CanonicalCreatureGap,
        cache: inout [String: CanonicalRunArtifactRecord]
    ) throws -> CreatureExportRecord? {
        let stmt = try db.prepare("""
            SELECT
                e.creature_id,
                e.name,
                e.owner_id,
                e.run_id,
                e.campaign_id,
                e.export_dir,
                e.bundle_kind,
                e.base_config_path,
                e.search_config_path,
                e.payload_path,
                e.exported_at,
                e.reason,
                e.score,
                e.filters_passed
            FROM exports e
            WHERE e.creature_id = ?
            ORDER BY e.exported_at DESC
            LIMIT 1
        """)
        defer { sqlite3_finalize(stmt) }
        db.bindText(stmt, index: 1, value: gap.creatureID)
        if sqlite3_step(stmt) == SQLITE_ROW {
            return try decodeExportReplayRecord(stmt, cache: &cache)
        }
        guard normalized(gap.sourceMode) == "sensorimotor-2024" else {
            return nil
        }

        let fallbackStmt = try db.prepare("""
            SELECT
                e.creature_id,
                e.name,
                e.owner_id,
                e.run_id,
                e.campaign_id,
                e.export_dir,
                e.bundle_kind,
                e.base_config_path,
                e.search_config_path,
                e.payload_path,
                e.exported_at,
                e.reason,
                e.score,
                e.filters_passed
            FROM exports e
            WHERE e.run_id = ?
              AND e.name = ?
              AND e.bundle_kind = ?
            ORDER BY e.exported_at DESC
            LIMIT 1
        """)
        defer { sqlite3_finalize(fallbackStmt) }
        db.bindText(fallbackStmt, index: 1, value: gap.runID)
        db.bindText(fallbackStmt, index: 2, value: gap.creature.name)
        db.bindText(fallbackStmt, index: 3, value: LeniaArtifactBundleKind.sensorimotor24PaperReplayBundleV1.rawValue)
        guard sqlite3_step(fallbackStmt) == SQLITE_ROW else {
            return nil
        }
        return try decodeExportReplayRecord(fallbackStmt, cache: &cache)
    }

    private func decodeExportReplayRecord(
        _ stmt: OpaquePointer?,
        cache: inout [String: CanonicalRunArtifactRecord]
    ) throws -> CreatureExportRecord? {
        guard let stmt,
              let creatureID = columnText(stmt, index: 0),
              let name = columnText(stmt, index: 1),
              let ownerID = columnText(stmt, index: 2),
              let runID = columnText(stmt, index: 3),
              let exportDir = columnText(stmt, index: 5),
              let bundleKindRaw = columnText(stmt, index: 6),
              let exportedAtText = columnText(stmt, index: 10),
              let reason = columnText(stmt, index: 11),
              let bundleKind = LeniaArtifactBundleKind(rawValue: bundleKindRaw),
              let runRecord = try runArtifactRecord(runID: runID, cache: &cache) else {
            return nil
        }
        let exportedAt = formatter.date(from: exportedAtText) ?? Date()
        let resolvedExportDir = resolveCompendiumArtifactPath(
            outputRoot: runRecord.outputRoot,
            runDir: runRecord.runDir,
            path: exportDir
        ) ?? exportDir
        let resolvedBaseConfigPath = columnText(stmt, index: 7).flatMap {
            resolveCompendiumArtifactPath(outputRoot: runRecord.outputRoot, runDir: runRecord.runDir, path: $0) ?? $0
        }
        let resolvedSearchConfigPath = columnText(stmt, index: 8).flatMap {
            resolveCompendiumArtifactPath(outputRoot: runRecord.outputRoot, runDir: runRecord.runDir, path: $0) ?? $0
        }
        let resolvedPayloadPath = columnText(stmt, index: 9).flatMap {
            resolveCompendiumArtifactPath(outputRoot: runRecord.outputRoot, runDir: runRecord.runDir, path: $0) ?? $0
        }
        return CreatureExportRecord(
            creatureId: UUID(uuidString: creatureID) ?? deterministicResearchUUID(creatureID),
            name: name,
            ownerId: ownerID,
            runId: runID,
            campaignId: columnText(stmt, index: 4),
            bundleKind: bundleKind,
            exportDir: resolvedExportDir,
            baseConfigPath: resolvedBaseConfigPath,
            searchConfigPath: resolvedSearchConfigPath,
            payloadPath: resolvedPayloadPath,
            exportedAt: exportedAt,
            reason: reason,
            score: sqlite3_column_type(stmt, 12) == SQLITE_NULL ? nil : Float(sqlite3_column_double(stmt, 12)),
            filtersPassed: sqlite3_column_type(stmt, 13) == SQLITE_NULL ? nil : sqlite3_column_int(stmt, 13) != 0
        )
    }

    private func exportMetadataURL(for record: CreatureExportRecord) -> URL? {
        let exportDirectory = URL(fileURLWithPath: record.exportDir, isDirectory: true)
        let metadataURL = exportDirectory.appendingPathComponent("meta.json")
        return FileManager.default.fileExists(atPath: metadataURL.path) ? metadataURL : nil
    }

    private func canonicalizationReplayInput(
        from exportRecord: CreatureExportRecord,
        gap: CanonicalCreatureGap
    ) throws -> ReplayResolvedInput {
        if !exportReplayRecordHasRequiredArtifacts(exportRecord),
           let flowReplayInput = try canonicalizationFlowReplayInput(for: gap) {
            return flowReplayInput
        }
        return try replayResolvedInput(
            from: exportRecord,
            fallbackCreature: gap.creature,
            fallbackMode: gap.sourceMode,
            fallbackAlgorithm: gap.sourceAlgorithm,
            fallbackResearchMetadata: gap.researchMetadata,
            fallbackReason: "canonicalization-backfill"
        )
    }

    private func exportReplayRecordHasRequiredArtifacts(_ record: CreatureExportRecord) -> Bool {
        switch record.bundleKind {
        case .strictReplayBundleV1:
            guard let baseConfigPath = record.baseConfigPath,
                  let searchConfigPath = record.searchConfigPath else {
                return false
            }
            return FileManager.default.fileExists(atPath: baseConfigPath)
                && FileManager.default.fileExists(atPath: searchConfigPath)
        case .qd24PaperReplayBundleV1, .sensorimotor24PaperReplayBundleV1:
            guard let payloadPath = record.payloadPath else {
                return false
            }
            return FileManager.default.fileExists(atPath: payloadPath)
        case .flowLeniaEcology2025ArenaReplayBundleV1:
            return false
        }
    }

    private func canonicalizationFlowReplayInput(for gap: CanonicalCreatureGap) throws -> ReplayResolvedInput? {
        guard let variant = try canonicalizationFlowSweepVariant(for: gap) else {
            return nil
        }

        let decoder = JSONDecoder()
        let baseConfig = try decoder.decode(LeniaBaseConfig.self, from: Data(contentsOf: variant.baseConfigURL))
        let searchConfig = try decoder.decode(ParsedSearchConfig.self, from: Data(contentsOf: variant.searchConfigURL))
        let replayBaseConfig = try buildReplayBaseConfig(
            baseConfig: baseConfig,
            searchConfig: searchConfig,
            creature: gap.creature
        )
        let replaySearchConfig = buildReplaySearchConfig(
            from: searchConfig,
            initSeedOffset: gap.creature.initialCondition.seed,
            enableMorphospaceSignals: true,
            supportsActivity: replaySupportsReplayActivity(baseConfig: replayBaseConfig)
        )
        let projection = canonicalGapProjection(gap)
        return ReplayResolvedInput(
            inputKind: .canonicalization,
            inputPath: variant.manifestURL,
            sourceRunId: gap.runID,
            sourceCampaignId: gap.campaignID,
            sourceMode: gap.sourceMode,
            sourceAlgorithm: gap.sourceAlgorithm,
            projection: projection,
            executionPlan: .flow(baseConfig: replayBaseConfig, searchConfig: replaySearchConfig),
            sourceScore: projection.creature.score,
            sourceFiltersPassed: nil,
            sourceExportDir: nil,
            sourceReason: "canonicalization-backfill"
        )
    }

    private func canonicalizationFlowSweepVariant(for gap: CanonicalCreatureGap) throws -> CanonicalFlowSweepVariant? {
        let candidates = canonicalizationFlowVariantCandidates(for: gap)
        guard !candidates.isEmpty else {
            return nil
        }

        let sweepRoot = URL(fileURLWithPath: try resolvePath("configs/sweeps", dossier: dossierName), isDirectory: true)
        let manifestURLs = try FileManager.default.contentsOfDirectory(
            at: sweepRoot,
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        )
            .filter { $0.pathExtension == "json" }
            .sorted { $0.lastPathComponent < $1.lastPathComponent }

        let decoder = JSONDecoder()
        for manifestURL in manifestURLs {
            let manifest = try decoder.decode(CanonicalFlowSweepManifest.self, from: Data(contentsOf: manifestURL))
            for variant in manifest.variants where candidates.contains(variant.id) {
                return CanonicalFlowSweepVariant(
                    manifestURL: manifestURL,
                    baseConfigURL: URL(fileURLWithPath: try resolvePath(variant.config, dossier: dossierName)),
                    searchConfigURL: URL(fileURLWithPath: try resolvePath(variant.search, dossier: dossierName))
                )
            }
        }
        return nil
    }

    private func canonicalizationFlowVariantCandidates(for gap: CanonicalCreatureGap) -> Set<String> {
        var candidates = Set<String>()
        if let range = gap.runID.range(of: "-c\\d+-s\\d+$", options: .regularExpression) {
            candidates.insert(String(gap.runID[..<range.lowerBound]))
        } else {
            candidates.insert(gap.runID)
        }
        if let algorithm = normalized(gap.sourceAlgorithm) {
            candidates.insert(algorithm)
        }
        return candidates.filter { !$0.isEmpty }.reduce(into: Set<String>()) { partial, value in
            partial.insert(value)
        }
    }

    private func qd24ReplayInput(
        for gap: CanonicalCreatureGap,
        cache: inout [String: CanonicalRunArtifactRecord]
    ) throws -> ReplayResolvedInput {
        guard let runRecord = try runArtifactRecord(runID: gap.runID, cache: &cache),
              let runDir = resolveCompendiumArtifactPath(outputRoot: runRecord.outputRoot, runDir: runRecord.runDir, path: nil) else {
            throw ValidationError("qd-2024 backfill could not resolve source run directory for \(gap.runID).")
        }
        let configDirectoryOverride = URL(
            fileURLWithPath: try resolvePath("configs/papers/leniabreeder-2024", dossier: dossierName),
            isDirectory: true
        )
        let resolvedRun = try loadLeniaBreeder2024ResolvedRun(
            runDirectory: URL(fileURLWithPath: runDir, isDirectory: true),
            configDirectoryOverride: configDirectoryOverride
        )
        let researchMetadata = gap.researchMetadata ?? [:]
        guard let cell = anyInt(researchMetadata["cell"]?.value),
              let generation = anyInt(researchMetadata["generation"]?.value),
              let centroid = anyFloatArray(researchMetadata["centroid"]?.value),
              let descriptor = anyFloatArray(researchMetadata["descriptor"]?.value),
              let fitness = anyFloat(researchMetadata["fitness"]?.value),
              let genotype = anyFloatArray(researchMetadata["genotype"]?.value) else {
            throw ValidationError("qd-2024 backfill is missing elite metadata for \(gap.creature.name).")
        }
        let elite = LeniaBreeder2024EliteSummary(
            cell: cell,
            generation: generation,
            centroid: centroid,
            descriptor: descriptor,
            fitness: fitness,
            genotype: genotype
        )
        let payload = LeniaBreeder2024ReplayPayload(
            algorithm: gap.sourceAlgorithm ?? resolvedRun.defaultAlgorithm,
            base: resolvedRun.base,
            mapElites: resolvedRun.mapElites,
            aurora: resolvedRun.aurora,
            pattern: resolvedRun.pattern,
            elite: elite
        )
        let inputPath = URL(fileURLWithPath: runDir, isDirectory: true)
            .appendingPathComponent("library/index.jsonl")
        let projection = canonicalGapProjection(gap)
        return ReplayResolvedInput(
            inputKind: .canonicalization,
            inputPath: inputPath,
            sourceRunId: gap.runID,
            sourceCampaignId: gap.campaignID,
            sourceMode: gap.sourceMode,
            sourceAlgorithm: gap.sourceAlgorithm,
            projection: projection,
            executionPlan: .qd24(payload: payload),
            sourceScore: projection.creature.score,
            sourceFiltersPassed: nil,
            sourceExportDir: nil,
            sourceReason: "canonicalization-backfill"
        )
    }

    private func replayInputFromResearchMetadata(
        for gap: CanonicalCreatureGap
    ) throws -> ReplayResolvedInput? {
        guard let sourceInputPath = researchMetadataString("source_input_path", in: gap.researchMetadata) else {
            return nil
        }
        let resolvedPath = NSString(string: sourceInputPath).expandingTildeInPath
        guard FileManager.default.fileExists(atPath: resolvedPath) else {
            return nil
        }
        let sourceURL = URL(fileURLWithPath: resolvedPath)
        let candidates = try loadReplayResolvedInputs(from: sourceURL)
        guard !candidates.isEmpty else {
            return nil
        }
        let sourceCreatureID = researchMetadataString("source_creature_id", in: gap.researchMetadata)
        let sourceExportDir = researchMetadataString("source_export_dir", in: gap.researchMetadata)
        let selected = try selectReplayMetadataInput(
            candidates: candidates,
            gap: gap,
            sourceCreatureID: sourceCreatureID,
            sourceExportDir: sourceExportDir
        )
        let projection = canonicalGapProjection(gap)
        return ReplayResolvedInput(
            inputKind: .canonicalization,
            inputPath: sourceURL,
            sourceRunId: gap.runID,
            sourceCampaignId: gap.campaignID,
            sourceMode: gap.sourceMode,
            sourceAlgorithm: gap.sourceAlgorithm ?? selected.sourceAlgorithm,
            projection: projection,
            executionPlan: selected.executionPlan,
            sourceScore: projection.creature.score,
            sourceFiltersPassed: selected.sourceFiltersPassed,
            sourceExportDir: sourceExportDir ?? selected.sourceExportDir,
            sourceReason: researchMetadataString("source_reason", in: gap.researchMetadata) ?? selected.sourceReason
        )
    }

    private func selectReplayMetadataInput(
        candidates: [ReplayResolvedInput],
        gap: CanonicalCreatureGap,
        sourceCreatureID: String?,
        sourceExportDir: String?
    ) throws -> ReplayResolvedInput {
        if let sourceCreatureID {
            let matching = candidates.filter {
                $0.sourceCreature.id.uuidString.caseInsensitiveCompare(sourceCreatureID) == .orderedSame
            }
            if matching.count == 1, let selected = matching.first {
                return selected
            }
            if matching.count > 1 {
                throw ValidationError(
                    "Canonicalization source metadata for \(gap.creature.name) matched multiple source creatures in \(gap.runID)."
                )
            }
        }
        if let sourceExportDir {
            let matching = candidates.filter { candidate in
                guard let candidateExportDir = candidate.sourceExportDir else {
                    return false
                }
                return candidateExportDir == sourceExportDir
            }
            if matching.count == 1, let selected = matching.first {
                return selected
            }
            if matching.count > 1 {
                throw ValidationError(
                    "Canonicalization source metadata for \(gap.creature.name) matched multiple source exports in \(gap.runID)."
                )
            }
        }
        if candidates.count == 1, let selected = candidates.first {
            return selected
        }
        throw ValidationError(
            "Canonicalization source metadata for \(gap.creature.name) is ambiguous; \(candidates.count) replay inputs were discovered in \(gap.runID)."
        )
    }

    private func canonicalGapProjection(_ gap: CanonicalCreatureGap) -> ResolvedSpecimenProjection {
        resolveSpecimenProjection(
            id: UUID(uuidString: gap.creatureID) ?? gap.creature.id,
            name: gap.creature.name,
            ownerId: gap.creature.ownerId,
            manifest: nil,
            fallbackGenotype: gap.creature.genotype,
            fallbackInitialCondition: gap.creature.initialCondition,
            fallbackMetrics: gap.creature.metrics,
            sweep: gap.creature.sweep,
            score: gap.creature.score,
            scoreWeights: gap.creature.scoreWeights,
            fallbackInitialConditionFamily: gap.creature.initialConditionFamily,
            fallbackDescriptorBundle: gap.creature.descriptorBundle,
            fallbackConfigHash: gap.configHash ?? gap.creature.configHash,
            fallbackSourceMode: gap.sourceMode,
            fallbackSourceAlgorithm: gap.sourceAlgorithm,
            fallbackResearchMetadata: gap.researchMetadata
        )
    }

    private func upsertBackfilledSpecimen(
        gap: CanonicalCreatureGap,
        resolvedInput: ReplayResolvedInput,
        execution: ReplayExecutionOutcome,
        artifactDirectory: URL
    ) throws -> String? {
        guard let descriptorBundle = execution.resultData.descriptorBundle else {
            throw ValidationError("Canonicalization replay for \(gap.creature.name) did not produce a descriptor bundle.")
        }
        let activityPath = FileManager.default.fileExists(atPath: artifactDirectory.appendingPathComponent("activity.jsonl").path)
            ? artifactDirectory.appendingPathComponent("activity.jsonl").path
            : nil
        let replayInitialConditionFamily = execution.replayCreature.initialConditionFamily
            ?? morphospaceInitialConditionFamily(execution.replayCreature.initialCondition)
        let specimenID = "creature:\(gap.creatureID)"
        _ = try upsertLibraryLikeSpecimen(
            creature: execution.replayCreature,
            specimenID: specimenID,
            creatureID: gap.creatureID,
            runId: gap.runID,
            campaignId: gap.campaignID,
            sourceKind: "backfill",
            provenanceKind: "backfill",
            recordedAt: gap.recordedAt,
            sourceMode: gap.sourceMode,
            sourceAlgorithm: gap.sourceAlgorithm,
            configHash: gap.configHash ?? execution.configHash,
            researchMetadata: gap.researchMetadata,
            manifestRecordedAt: formatter.date(from: gap.recordedAt) ?? Date(),
            sourcePath: resolvedInput.inputPath.path,
            activityPath: activityPath,
            descriptorBundle: descriptorBundle,
            seed: execution.resultData.seed,
            initSeed: execution.resultData.initSeed,
            initialConditionFamily: execution.resultData.initialConditionFamily ?? replayInitialConditionFamily
        )
        return specimenID
    }

    private func setCanonicalSpecimenLink(creatureID: String, specimenID: String) throws {
        let stmt = try db.prepare("UPDATE creatures SET canonical_specimen_id = ? WHERE id = ?")
        defer { sqlite3_finalize(stmt) }
        db.bindText(stmt, index: 1, value: specimenID)
        db.bindText(stmt, index: 2, value: creatureID)
        guard sqlite3_step(stmt) == SQLITE_DONE else {
            throw SQLiteIndexError.sqliteError(message: "Failed to update canonical specimen link for creature \(creatureID).")
        }
    }

    private static func persistCanonicalizationArtifacts(
        directory: URL,
        execution: ReplayExecutionOutcome,
        resolvedInput: ReplayResolvedInput
    ) throws {
        _ = try persistResearchExecutionArtifacts(
            directory: directory,
            baseConfig: execution.baseConfig,
            searchConfig: execution.searchConfig,
            resultData: execution.resultData,
            activityRecord: execution.activityRecord
        )
        let manifest: [String: AnyCodable] = try [
            "source_kind": researchMetadataValue(resolvedInput.inputKind.rawValue),
            "source_input_path": researchMetadataValue(resolvedInput.inputPath.path),
            "source_run_id": researchMetadataValue(resolvedInput.sourceRunId),
            "source_creature_id": researchMetadataValue(resolvedInput.sourceCreature.id.uuidString),
            "source_mode": researchMetadataValue(resolvedInput.sourceMode ?? "unknown"),
            "source_algorithm": researchMetadataValue(resolvedInput.sourceAlgorithm ?? "unknown"),
            "config_hash": researchMetadataValue(execution.configHash),
        ]
        try replayEncoder().encode(manifest).write(to: directory.appendingPathComponent("canonicalization.json"))
    }

    private func canonicalizationBackfillRoot() throws -> URL {
        let directory = URL(fileURLWithPath: path)
            .deletingLastPathComponent()
            .appendingPathComponent("canonicalization-backfill", isDirectory: true)
            .appendingPathComponent(Self.timestampStamp(), isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        return directory
    }

    private static func timestampStamp() -> String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .iso8601)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        return formatter.string(from: Date())
    }

    private func canonicalizationRunID(for gap: CanonicalCreatureGap) -> String {
        let mode = (normalized(gap.sourceMode) ?? "specimen")
            .replacingOccurrences(of: "[^A-Za-z0-9_-]+", with: "-", options: .regularExpression)
        return "canonicalize-\(mode)-\(String(gap.creatureID.prefix(8)).lowercased())"
    }

    private func runArtifactRecord(
        runID: String,
        cache: inout [String: CanonicalRunArtifactRecord]
    ) throws -> CanonicalRunArtifactRecord? {
        if let cached = cache[runID] {
            return cached
        }
        let stmt = try db.prepare("SELECT run_dir, output_root FROM runs WHERE run_id = ? LIMIT 1")
        defer { sqlite3_finalize(stmt) }
        db.bindText(stmt, index: 1, value: runID)
        guard sqlite3_step(stmt) == SQLITE_ROW,
              let runDir = columnText(stmt, index: 0) else {
            return nil
        }
        let record = CanonicalRunArtifactRecord(
            runDir: runDir,
            outputRoot: columnText(stmt, index: 1)
        )
        cache[runID] = record
        return record
    }

    private func libraryIndexURL(
        for gap: CanonicalCreatureGap,
        cache: inout [String: CanonicalRunArtifactRecord]
    ) throws -> URL? {
        guard let runRecord = try runArtifactRecord(runID: gap.runID, cache: &cache) else {
            return nil
        }
        let relativePath = gap.campaignID.map { "campaigns/\($0)/library/index.jsonl" } ?? "library/index.jsonl"
        guard let resolved = resolveCompendiumArtifactPath(
            outputRoot: runRecord.outputRoot,
            runDir: runRecord.runDir,
            path: relativePath
        ), FileManager.default.fileExists(atPath: resolved) else {
            return nil
        }
        return URL(fileURLWithPath: resolved)
    }

    private func loadResearchLibraryEntries(at url: URL) throws -> [String: ResearchLibraryEntry] {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .deferredToDate
        return try replayReadJSONLines(url).reduce(into: [String: ResearchLibraryEntry]()) { partial, line in
            guard let data = line.data(using: .utf8) else {
                throw SQLiteIndexError.invalidUTF8(url.path)
            }
            let entry = try decodeResearchLibraryEntry(data, decoder: decoder)
            partial[entry.creature.id.uuidString] = entry
        }
    }

    private func canonicalGapReport(for gaps: [CanonicalCreatureGap]) -> String {
        let grouped = Dictionary(grouping: gaps, by: { normalized($0.sourceMode) ?? "unknown" })
        let summary = grouped.keys.sorted().map { key in
            "\(key)=\(grouped[key]?.count ?? 0)"
        }.joined(separator: ", ")
        return "Canonical specimen backfill left \(gaps.count) unlinked creatures (\(summary)). Repair failed because every indexed creature must resolve to a strict specimen."
    }

    private func anyInt(_ value: Any?) -> Int? {
        switch value {
        case let value as Int:
            return value
        case let value as Double:
            return Int(value)
        case let value as Float:
            return Int(value)
        case let value as NSNumber:
            return value.intValue
        default:
            return nil
        }
    }

    private func anyFloat(_ value: Any?) -> Float? {
        switch value {
        case let value as Float:
            return value
        case let value as Double:
            return Float(value)
        case let value as Int:
            return Float(value)
        case let value as NSNumber:
            return value.floatValue
        default:
            return nil
        }
    }

    private func anyFloatArray(_ value: Any?) -> [Float]? {
        switch value {
        case let value as [Float]:
            return value
        case let value as [Double]:
            return value.map(Float.init)
        case let value as [NSNumber]:
            return value.map(\.floatValue)
        default:
            return nil
        }
    }

    private func researchMetadataString(
        _ key: String,
        in researchMetadata: [String: AnyCodable]?
    ) -> String? {
        if let value = normalized(researchMetadata?[key]?.value as? String) {
            return value
        }
        if let nested = researchMetadata?["source_research_metadata"]?.value as? [String: Any],
           let value = normalized(nested[key] as? String) {
            return value
        }
        return nil
    }

    private func ensureSchema() throws {
        if try !db.tableExists("compendium_meta") {
            try createSchema()
            try db.exec("INSERT INTO compendium_meta (schema_version) VALUES (\(Self.schemaVersion))")
            try repairCurrentSchema()
            return
        }

        let rowCount = try db.scalarInt("SELECT COUNT(*) FROM compendium_meta")
        if rowCount == 0 {
            try db.exec("INSERT INTO compendium_meta (schema_version) VALUES (\(Self.schemaVersion))")
            try createSchema()
            try repairCurrentSchema()
            return
        }

        let version = try db.scalarInt("SELECT schema_version FROM compendium_meta LIMIT 1")
        if version > Self.schemaVersion {
            throw SQLiteIndexError.sqliteError(message: "Compendium schema version \(version) is newer than supported \(Self.schemaVersion)")
        }
        if version < 2 {
            try migrate1to2()
        }
        if version < 3 {
            try migrate2to3()
        }
        if version < 4 {
            try migrate3to4()
        }
        if version < 5 {
            try migrate4to5()
        }
        if version < 6 {
            try migrate5to6()
        }
        if version < 7 {
            try migrate6to7()
        }
        if version < 8 {
            try migrate7to8()
        }
        if version < 9 {
            try migrate8to9()
        }
        if version < 10 {
            try migrate9to10()
        }
        if version < 11 {
            try migrate10to11()
        }
        if version < 12 {
            try migrate11to12()
        }
        if version < 13 {
            try migrate12to13()
        }
        if version < 14 {
            try migrate13to14()
        }
        if version < 15 {
            try migrate14to15()
        }

        try createSchema()
        try repairCurrentSchema()
    }

    private func migrate1to2() throws {
        try db.withImmediateTransaction {
            try db.exec("ALTER TABLE runs ADD COLUMN run_name TEXT NOT NULL DEFAULT ''")
            try db.exec("ALTER TABLE runs ADD COLUMN host_id TEXT")
            try db.exec("ALTER TABLE runs ADD COLUMN output_root TEXT")
            try db.exec("ALTER TABLE runs ADD COLUMN indexed_at TEXT NOT NULL DEFAULT ''")
            try db.exec("UPDATE runs SET run_name = run_id WHERE run_name = ''")

            let select = try db.prepare("SELECT run_id, run_dir FROM runs")
            defer { sqlite3_finalize(select) }

            while sqlite3_step(select) == SQLITE_ROW {
                guard let runIdC = sqlite3_column_text(select, 0),
                      let runDirC = sqlite3_column_text(select, 1) else {
                    continue
                }
                let runId = String(cString: runIdC)
                let runDir = String(cString: runDirC)

                let inferred = inferRunDirMetadata(runDir)
                let hostId = inferred.hostId
                let outputRoot = inferred.outputRoot
                let runDirStored = inferred.runDirRelative ?? runDir
                let runName = runId
                let indexedAt = formatter.string(from: Date())

                var newRunId = runId
                if let hostId = hostId, !runId.contains("::") {
                    newRunId = "\(hostId)::\(runId)"
                }

                if newRunId != runId {
                    try updateRunId(table: "creatures", newRunId: newRunId, oldRunId: runId)
                    try updateRunId(table: "campaigns", newRunId: newRunId, oldRunId: runId)
                    try updateRunId(table: "exports", newRunId: newRunId, oldRunId: runId)
                    try updateRunId(table: "results", newRunId: newRunId, oldRunId: runId)
                }

                let update = try db.prepare("""
                    UPDATE runs
                    SET run_id = ?, run_name = ?, host_id = ?, output_root = ?, run_dir = ?, indexed_at = ?
                    WHERE run_id = ?
                """)
                db.bindText(update, index: 1, value: newRunId)
                db.bindText(update, index: 2, value: runName)
                db.bindText(update, index: 3, value: hostId)
                db.bindText(update, index: 4, value: outputRoot)
                db.bindText(update, index: 5, value: runDirStored)
                db.bindText(update, index: 6, value: indexedAt)
                db.bindText(update, index: 7, value: runId)
                try db.step(update)
                sqlite3_finalize(update)
            }

            try db.exec("UPDATE compendium_meta SET schema_version = 2")
        }
    }

    private func migrate2to3() throws {
        try db.withImmediateTransaction {
            let creatureColumns = try db.tableColumns("creatures")
            if !creatureColumns.contains("taxonomy_family_id") {
                try db.exec("ALTER TABLE creatures ADD COLUMN taxonomy_family_id TEXT")
            }
            if !creatureColumns.contains("taxonomy_genus_id") {
                try db.exec("ALTER TABLE creatures ADD COLUMN taxonomy_genus_id TEXT")
            }
            if !creatureColumns.contains("taxonomy_species_id") {
                try db.exec("ALTER TABLE creatures ADD COLUMN taxonomy_species_id TEXT")
            }
            if !creatureColumns.contains("taxonomy_confidence") {
                try db.exec("ALTER TABLE creatures ADD COLUMN taxonomy_confidence REAL")
            }
            if !creatureColumns.contains("taxonomy_method") {
                try db.exec("ALTER TABLE creatures ADD COLUMN taxonomy_method TEXT")
            }
            if !creatureColumns.contains("taxonomy_version") {
                try db.exec("ALTER TABLE creatures ADD COLUMN taxonomy_version INTEGER")
            }
            if !creatureColumns.contains("morphometrics_json") {
                try db.exec("ALTER TABLE creatures ADD COLUMN morphometrics_json TEXT")
            }
            if !creatureColumns.contains("morphometrics_method") {
                try db.exec("ALTER TABLE creatures ADD COLUMN morphometrics_method TEXT")
            }
            if !creatureColumns.contains("morphometrics_version") {
                try db.exec("ALTER TABLE creatures ADD COLUMN morphometrics_version INTEGER")
            }

            try db.exec("UPDATE compendium_meta SET schema_version = 3")
        }
    }

    private func migrate3to4() throws {
        try db.withImmediateTransaction {
            let creatureColumns = try db.tableColumns("creatures")
            if !creatureColumns.contains("config_hash") {
                try db.exec("ALTER TABLE creatures ADD COLUMN config_hash TEXT")
            }

            let runColumns = try db.tableColumns("runs")
            if !runColumns.contains("config_hash") {
                try db.exec("ALTER TABLE runs ADD COLUMN config_hash TEXT")
            }

            try db.exec("UPDATE compendium_meta SET schema_version = 4")
        }
    }

    private func migrate4to5() throws {
        try db.withImmediateTransaction {
            try db.exec("""
                CREATE TABLE campaigns_v5 (
                    run_id TEXT NOT NULL,
                    campaign_id TEXT NOT NULL,
                    PRIMARY KEY (run_id, campaign_id)
                )
            """)

            let selectCampaigns = try db.prepare("""
                SELECT DISTINCT run_id, campaign_id
                FROM (
                    SELECT run_id, campaign_id FROM campaigns
                    UNION
                    SELECT run_id, campaign_id FROM creatures WHERE campaign_id IS NOT NULL
                    UNION
                    SELECT run_id, campaign_id FROM exports WHERE campaign_id IS NOT NULL
                    UNION
                    SELECT run_id, campaign_id FROM results WHERE campaign_id IS NOT NULL
                )
                WHERE campaign_id IS NOT NULL
            """)
            defer { sqlite3_finalize(selectCampaigns) }

            let insertCampaign = try db.prepare("""
                INSERT OR REPLACE INTO campaigns_v5 (run_id, campaign_id)
                VALUES (?, ?)
            """)
            defer { sqlite3_finalize(insertCampaign) }

            while sqlite3_step(selectCampaigns) == SQLITE_ROW {
                guard let runIdC = sqlite3_column_text(selectCampaigns, 0),
                      let campaignIdC = sqlite3_column_text(selectCampaigns, 1) else {
                    continue
                }
                sqlite3_reset(insertCampaign)
                sqlite3_clear_bindings(insertCampaign)
                db.bindText(insertCampaign, index: 1, value: String(cString: runIdC))
                db.bindText(insertCampaign, index: 2, value: String(cString: campaignIdC))
                try db.step(insertCampaign)
            }

            try db.exec("""
                CREATE TABLE exports_v5 (
                    id TEXT PRIMARY KEY,
                    export_dir TEXT NOT NULL,
                    creature_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    campaign_id TEXT,
                    base_config_path TEXT NOT NULL,
                    search_config_path TEXT NOT NULL,
                    exported_at TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    score REAL,
                    filters_passed INTEGER
                )
            """)

            let selectExports = try db.prepare("""
                SELECT export_dir, creature_id, name, owner_id, run_id, campaign_id,
                       base_config_path, search_config_path, exported_at, reason,
                       score, filters_passed
                FROM exports
            """)
            defer { sqlite3_finalize(selectExports) }

            let insertExport = try db.prepare("""
                INSERT OR REPLACE INTO exports_v5 (
                    id, export_dir, creature_id, name, owner_id, run_id, campaign_id,
                    base_config_path, search_config_path, exported_at, reason,
                    score, filters_passed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """)
            defer { sqlite3_finalize(insertExport) }

            while sqlite3_step(selectExports) == SQLITE_ROW {
                guard let exportDirC = sqlite3_column_text(selectExports, 0),
                      let creatureIdC = sqlite3_column_text(selectExports, 1),
                      let nameC = sqlite3_column_text(selectExports, 2),
                      let ownerIdC = sqlite3_column_text(selectExports, 3),
                      let runIdC = sqlite3_column_text(selectExports, 4),
                      let baseConfigC = sqlite3_column_text(selectExports, 6),
                      let searchConfigC = sqlite3_column_text(selectExports, 7),
                      let exportedAtC = sqlite3_column_text(selectExports, 8),
                      let reasonC = sqlite3_column_text(selectExports, 9) else {
                    throw SQLiteIndexError.sqliteError(message: "Invalid exports row during schema v5 migration.")
                }

                let exportDir = String(cString: exportDirC)
                let runId = String(cString: runIdC)
                let campaignId = sqlite3_column_text(selectExports, 5).map { String(cString: $0) }
                let score = sqlite3_column_type(selectExports, 10) == SQLITE_NULL ? nil : sqlite3_column_double(selectExports, 10)
                let filtersPassed = sqlite3_column_type(selectExports, 11) == SQLITE_NULL ? nil : sqlite3_column_int(selectExports, 11) != 0

                sqlite3_reset(insertExport)
                sqlite3_clear_bindings(insertExport)
                db.bindText(insertExport, index: 1, value: Self.exportRecordId(runKey: runId, exportDir: exportDir))
                db.bindText(insertExport, index: 2, value: exportDir)
                db.bindText(insertExport, index: 3, value: String(cString: creatureIdC))
                db.bindText(insertExport, index: 4, value: String(cString: nameC))
                db.bindText(insertExport, index: 5, value: String(cString: ownerIdC))
                db.bindText(insertExport, index: 6, value: runId)
                db.bindText(insertExport, index: 7, value: campaignId)
                db.bindText(insertExport, index: 8, value: String(cString: baseConfigC))
                db.bindText(insertExport, index: 9, value: String(cString: searchConfigC))
                db.bindText(insertExport, index: 10, value: String(cString: exportedAtC))
                db.bindText(insertExport, index: 11, value: String(cString: reasonC))
                db.bindDouble(insertExport, index: 12, value: score)
                db.bindBool(insertExport, index: 13, value: filtersPassed)
                try db.step(insertExport)
            }

            try db.exec("DROP TABLE campaigns")
            try db.exec("ALTER TABLE campaigns_v5 RENAME TO campaigns")
            try db.exec("DROP TABLE exports")
            try db.exec("ALTER TABLE exports_v5 RENAME TO exports")
            try db.exec("UPDATE compendium_meta SET schema_version = 5")
        }
    }

    private func migrate5to6() throws {
        try db.withImmediateTransaction {
            let creatureColumns = try db.tableColumns("creatures")
            if !creatureColumns.contains("velocity_x") {
                try db.exec("ALTER TABLE creatures ADD COLUMN velocity_x REAL")
            }
            if !creatureColumns.contains("velocity_y") {
                try db.exec("ALTER TABLE creatures ADD COLUMN velocity_y REAL")
            }
            if !creatureColumns.contains("heading_rad") {
                try db.exec("ALTER TABLE creatures ADD COLUMN heading_rad REAL")
            }

            try db.exec("""
                UPDATE creatures
                SET velocity_x = COALESCE(velocity_x, 0.0),
                    velocity_y = COALESCE(velocity_y, 0.0),
                    heading_rad = COALESCE(heading_rad, 0.0)
            """)

            try db.exec("UPDATE compendium_meta SET schema_version = 6")
        }
    }

    private func migrate6to7() throws {
        try db.withImmediateTransaction {
            let runColumns = try db.tableColumns("runs")
            if !runColumns.contains("source_mode") {
                try db.exec("ALTER TABLE runs ADD COLUMN source_mode TEXT")
            }
            if !runColumns.contains("source_algorithm") {
                try db.exec("ALTER TABLE runs ADD COLUMN source_algorithm TEXT")
            }

            let creatureColumns = try db.tableColumns("creatures")
            if !creatureColumns.contains("source_mode") {
                try db.exec("ALTER TABLE creatures ADD COLUMN source_mode TEXT")
            }
            if !creatureColumns.contains("source_algorithm") {
                try db.exec("ALTER TABLE creatures ADD COLUMN source_algorithm TEXT")
            }
            if !creatureColumns.contains("research_metadata_json") {
                try db.exec("ALTER TABLE creatures ADD COLUMN research_metadata_json TEXT")
            }

            try db.exec("UPDATE compendium_meta SET schema_version = 7")
        }
    }

    private func migrate7to8() throws {
        try db.withImmediateTransaction {
            let creatureColumns = try db.tableColumns("creatures")
            if !creatureColumns.contains("trait_labels_json") {
                try db.exec("ALTER TABLE creatures ADD COLUMN trait_labels_json TEXT")
            }

            try db.exec("UPDATE compendium_meta SET schema_version = 8")
        }
    }

    private func migrate8to9() throws {
        try db.withImmediateTransaction {
            try createMorphospaceTables()
            try db.exec("UPDATE compendium_meta SET schema_version = 9")
        }
    }

    private func migrate9to10() throws {
        try db.withImmediateTransaction {
            try createEcologyRunTables()
            try db.exec("UPDATE compendium_meta SET schema_version = 10")
        }
    }

    private func migrate10to11() throws {
        try db.withImmediateTransaction {
            try rebuildExportsTableForReplayBundles()
            try db.exec("UPDATE compendium_meta SET schema_version = 11")
        }
    }

    private func migrate11to12() throws {
        try db.withImmediateTransaction {
            try rebuildExportsTableForReplayBundles()
            try db.exec("UPDATE compendium_meta SET schema_version = 12")
        }
    }

    private func migrate12to13() throws {
        try db.withImmediateTransaction {
            try ensureCanonicalCreatureSnapshotColumns()
            try ensureSpecimenContractColumns()
            try backfillSpecimenContracts()
            try db.exec("UPDATE compendium_meta SET schema_version = 13")
        }
    }

    private func migrate13to14() throws {
        try db.withImmediateTransaction {
            try ensureCanonicalCreatureSnapshotColumns()
            try ensureSpecimenContractColumns()
            try backfillSpecimenContracts()
            try db.exec("UPDATE compendium_meta SET schema_version = 14")
        }
    }

    private func migrate14to15() throws {
        try db.withImmediateTransaction {
            try ensureCreatureCatalogQCColumns()
            try db.exec("UPDATE compendium_meta SET schema_version = 15")
        }
    }

    private func repairCurrentSchema() throws {
        guard try db.tableExists("compendium_meta") else {
            return
        }
        try db.withImmediateTransaction {
            if try !currentSchemaNeedsRepair() {
                return
            }
            try ensureCanonicalCreatureSnapshotColumns()
            try ensureSpecimenContractColumns()
            try ensureCreatureCatalogQCColumns()
            try normalizeLegacyReplaySourceMode()
            try backfillSpecimenContracts()
            try db.exec("UPDATE compendium_meta SET schema_version = \(Self.schemaVersion)")
        }
    }

    private func currentSchemaNeedsRepair() throws -> Bool {
        try legacyCreatureSnapshotNeedsRepair()
            || specimenContractColumnsNeedRepair()
            || canonicalCreatureLinkNeedsRepair()
            || creatureCatalogQCColumnsNeedRepair()
            || legacyReplaySourceModeNeedsRepair()
    }

    private func creatureCatalogQCColumnsNeedRepair() throws -> Bool {
        guard try db.tableExists("creatures") else {
            return false
        }
        let columns = try db.tableColumns("creatures")
        return !columns.contains("catalog_status") || !columns.contains("quality_flags_json")
    }

    private func ensureCreatureCatalogQCColumns() throws {
        guard try db.tableExists("creatures") else {
            return
        }
        let columns = try db.tableColumns("creatures")
        if !columns.contains("catalog_status") {
            try db.exec("ALTER TABLE creatures ADD COLUMN catalog_status TEXT NOT NULL DEFAULT 'active'")
        }
        if !columns.contains("quality_flags_json") {
            try db.exec("ALTER TABLE creatures ADD COLUMN quality_flags_json TEXT NOT NULL DEFAULT '[]'")
        }
        try db.exec("""
            CREATE TABLE IF NOT EXISTS creature_qc_events (
                id TEXT PRIMARY KEY,
                creature_id TEXT NOT NULL,
                old_status TEXT,
                new_status TEXT NOT NULL,
                policy_id TEXT NOT NULL,
                reasons_json TEXT NOT NULL,
                metrics_snapshot_json TEXT,
                created_at TEXT NOT NULL
            )
        """)
        try db.exec("CREATE INDEX IF NOT EXISTS creatures_catalog_status ON creatures(catalog_status)")
        try db.exec("CREATE INDEX IF NOT EXISTS creature_qc_events_creature ON creature_qc_events(creature_id)")
    }

    private func legacyCreatureSnapshotNeedsRepair() throws -> Bool {
        guard try db.tableExists("creatures") else {
            return false
        }

        let creatureColumns = try db.tableColumns("creatures")
        guard creatureColumns.contains("phenotype_json") else {
            return !creatureColumns.contains("initial_condition_json")
        }
        guard creatureColumns.contains("initial_condition_json") else {
            return true
        }
        return try db.scalarInt("""
            SELECT COUNT(*)
            FROM creatures
            WHERE initial_condition_json IS NULL AND phenotype_json IS NOT NULL
        """) > 0
    }

    private func specimenContractColumnsNeedRepair() throws -> Bool {
        guard try db.tableExists("creatures"),
              try db.tableExists("exports") else {
            return false
        }
        if try !db.tableExists("specimens") {
            return true
        }

        let creatureColumns = try db.tableColumns("creatures")
        let exportColumns = try db.tableColumns("exports")
        let specimenColumns = try db.tableColumns("specimens")
        let requiredColumns = ["runtime_family", "runtime_capabilities_json", "specimen_manifest_json"]
        return requiredColumns.contains(where: { !creatureColumns.contains($0) })
            || requiredColumns.contains(where: { !exportColumns.contains($0) })
            || requiredColumns.contains(where: { !specimenColumns.contains($0) })
    }

    private func legacyReplaySourceModeNeedsRepair() throws -> Bool {
        for table in ["runs", "creatures", "exports", "specimens"] {
            guard try db.tableExists(table),
                  try db.tableColumns(table).contains("source_mode") else {
                continue
            }
            if try db.scalarInt("SELECT COUNT(*) FROM \(table) WHERE source_mode = 'replay-specimens'") > 0 {
                return true
            }
        }
        if try db.tableExists("creatures"),
           try db.tableColumns("creatures").contains("research_metadata_json"),
           try db.scalarInt("""
                SELECT COUNT(*)
                FROM creatures
                WHERE research_metadata_json LIKE '%replay-specimens%'
           """) > 0 {
            return true
        }
        for table in ["creatures", "exports", "specimens"] {
            guard try db.tableExists(table),
                  try db.tableColumns(table).contains("specimen_manifest_json") else {
                continue
            }
            if try db.scalarInt("""
                SELECT COUNT(*)
                FROM \(table)
                WHERE specimen_manifest_json LIKE '%replay-specimens%'
            """) > 0 {
                return true
            }
        }
        return false
    }

    private func normalizeLegacyReplaySourceMode() throws {
        for table in ["runs", "creatures", "exports", "specimens"] {
            guard try db.tableExists(table),
                  try db.tableColumns(table).contains("source_mode") else {
                continue
            }
            try db.exec("""
                UPDATE \(table)
                SET source_mode = 'replay'
                WHERE source_mode = 'replay-specimens'
            """)
        }
        if try db.tableExists("creatures"),
           try db.tableColumns("creatures").contains("research_metadata_json") {
            try db.exec("""
                UPDATE creatures
                SET research_metadata_json = REPLACE(research_metadata_json, 'replay-specimens', 'replay')
                WHERE research_metadata_json LIKE '%replay-specimens%'
            """)
        }
        for table in ["creatures", "exports", "specimens"] {
            guard try db.tableExists(table),
                  try db.tableColumns(table).contains("specimen_manifest_json") else {
                continue
            }
            try db.exec("""
                UPDATE \(table)
                SET specimen_manifest_json = REPLACE(specimen_manifest_json, 'replay-specimens', 'replay')
                WHERE specimen_manifest_json LIKE '%replay-specimens%'
            """)
        }
    }

    private func canonicalCreatureLinkNeedsRepair() throws -> Bool {
        guard try db.tableExists("creatures") else {
            return false
        }
        return try !db.tableColumns("creatures").contains("canonical_specimen_id")
    }

    private func ensureCanonicalCreatureSnapshotColumns() throws {
        guard try db.tableExists("creatures") else {
            return
        }

        let creatureColumns = try db.tableColumns("creatures")
        if !creatureColumns.contains("initial_condition_json") {
            try db.exec("ALTER TABLE creatures ADD COLUMN initial_condition_json TEXT")
        }
        if creatureColumns.contains("phenotype_json") {
            try db.exec("""
                UPDATE creatures
                SET initial_condition_json = COALESCE(initial_condition_json, phenotype_json)
                WHERE phenotype_json IS NOT NULL
            """)
        }
    }

    private func ensureSpecimenContractColumns() throws {
        guard try db.tableExists("creatures"),
              try db.tableExists("exports") else {
            return
        }

        try createMorphospaceTables()

        let creatureColumns = try db.tableColumns("creatures")
        if !creatureColumns.contains("runtime_family") {
            try db.exec("ALTER TABLE creatures ADD COLUMN runtime_family TEXT")
        }
        if !creatureColumns.contains("runtime_capabilities_json") {
            try db.exec("ALTER TABLE creatures ADD COLUMN runtime_capabilities_json TEXT")
        }
        if !creatureColumns.contains("specimen_manifest_json") {
            try db.exec("ALTER TABLE creatures ADD COLUMN specimen_manifest_json TEXT")
        }
        if !creatureColumns.contains("canonical_specimen_id") {
            try db.exec("ALTER TABLE creatures ADD COLUMN canonical_specimen_id TEXT")
        }

        let exportColumns = try db.tableColumns("exports")
        if !exportColumns.contains("runtime_family") {
            try db.exec("ALTER TABLE exports ADD COLUMN runtime_family TEXT")
        }
        if !exportColumns.contains("runtime_capabilities_json") {
            try db.exec("ALTER TABLE exports ADD COLUMN runtime_capabilities_json TEXT")
        }
        if !exportColumns.contains("specimen_manifest_json") {
            try db.exec("ALTER TABLE exports ADD COLUMN specimen_manifest_json TEXT")
        }

        let specimenColumns = try db.tableColumns("specimens")
        if !specimenColumns.contains("runtime_family") {
            try db.exec("ALTER TABLE specimens ADD COLUMN runtime_family TEXT")
        }
        if !specimenColumns.contains("runtime_capabilities_json") {
            try db.exec("ALTER TABLE specimens ADD COLUMN runtime_capabilities_json TEXT")
        }
        if !specimenColumns.contains("specimen_manifest_json") {
            try db.exec("ALTER TABLE specimens ADD COLUMN specimen_manifest_json TEXT")
        }
    }

    private func backfillSpecimenContracts() throws {
        try backfillCreatureSpecimenContracts()
        try backfillStrictSpecimenContracts()
        try backfillExportSpecimenContracts()
    }

    private func rebuildExportsTableForReplayBundles() throws {
        let exportColumns = try db.tableColumns("exports")
        let bundleKindExpr = exportColumns.contains("bundle_kind")
            ? "bundle_kind"
            : "'strict_replay_bundle_v1'"
        let payloadPathExpr = exportColumns.contains("payload_path")
            ? "payload_path"
            : "NULL"
        try db.exec("""
            CREATE TABLE exports_rebuilt (
                id TEXT PRIMARY KEY,
                export_dir TEXT NOT NULL,
                creature_id TEXT NOT NULL,
                name TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                campaign_id TEXT,
                bundle_kind TEXT NOT NULL,
                base_config_path TEXT,
                search_config_path TEXT,
                payload_path TEXT,
                exported_at TEXT NOT NULL,
                reason TEXT NOT NULL,
                score REAL,
                filters_passed INTEGER
            )
        """)
        try db.exec("""
            INSERT INTO exports_rebuilt (
                id, export_dir, creature_id, name, owner_id, run_id, campaign_id,
                bundle_kind, base_config_path, search_config_path, payload_path,
                exported_at, reason, score, filters_passed
            )
            SELECT
                id, export_dir, creature_id, name, owner_id, run_id, campaign_id,
                \(bundleKindExpr), base_config_path, search_config_path, \(payloadPathExpr),
                exported_at, reason, score, filters_passed
            FROM exports
        """)
        try db.exec("DROP TABLE exports")
        try db.exec("ALTER TABLE exports_rebuilt RENAME TO exports")
    }

    private func createSchema() throws {
        try db.exec("""
            CREATE TABLE IF NOT EXISTS compendium_meta (
                schema_version INTEGER NOT NULL
            )
        """)

        try db.exec("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                run_name TEXT NOT NULL,
                host_id TEXT,
                output_root TEXT,
                run_dir TEXT NOT NULL,
                indexed_at TEXT NOT NULL,
                config_hash TEXT,
                source_mode TEXT,
                source_algorithm TEXT
            )
        """)

        try db.exec("""
            CREATE TABLE IF NOT EXISTS campaigns (
                run_id TEXT NOT NULL,
                campaign_id TEXT NOT NULL,
                PRIMARY KEY (run_id, campaign_id)
            )
        """)

        try db.exec("""
            CREATE TABLE IF NOT EXISTS creatures (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                campaign_id TEXT,
                recorded_at TEXT NOT NULL,
                init_seed INTEGER,
                score REAL,
                is_stable INTEGER NOT NULL,
                mass_mean REAL,
                mass_std REAL,
                mass_min REAL,
                mass_max REAL,
                occupancy_mean REAL,
                variance_mean REAL,
                energy_mean REAL,
                speed_mean REAL,
                path_length REAL,
                displacement REAL,
                gyration REAL,
                center_velocity REAL,
                velocity_x REAL,
                velocity_y REAL,
                heading_rad REAL,
                complexity_mean REAL,
                complexity_target_score REAL,
                activity_eac_mean REAL,
                activity_ean_mean REAL,
                activity_diversity_mean REAL,
                activity_species_mean REAL,
                taxonomy_family_id TEXT,
                taxonomy_genus_id TEXT,
                taxonomy_species_id TEXT,
                taxonomy_confidence REAL,
                taxonomy_method TEXT,
                taxonomy_version INTEGER,
                morphometrics_json TEXT,
                morphometrics_method TEXT,
                morphometrics_version INTEGER,
                config_hash TEXT,
                source_mode TEXT,
                source_algorithm TEXT,
                research_metadata_json TEXT,
                runtime_family TEXT,
                runtime_capabilities_json TEXT,
                specimen_manifest_json TEXT,
                canonical_specimen_id TEXT,
                trait_labels_json TEXT,
                catalog_status TEXT NOT NULL DEFAULT 'active',
                quality_flags_json TEXT NOT NULL DEFAULT '[]',
                score_weights_json TEXT,
                genotype_json TEXT,
                initial_condition_json TEXT,
                sweep_json TEXT,
                metrics_json TEXT
            )
        """)

        try db.exec("""
            CREATE TABLE IF NOT EXISTS exports (
                id TEXT PRIMARY KEY,
                export_dir TEXT NOT NULL,
                creature_id TEXT NOT NULL,
                name TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                campaign_id TEXT,
                bundle_kind TEXT NOT NULL,
                base_config_path TEXT,
                search_config_path TEXT,
                payload_path TEXT,
                exported_at TEXT NOT NULL,
                reason TEXT NOT NULL,
                score REAL,
                filters_passed INTEGER,
                runtime_family TEXT,
                runtime_capabilities_json TEXT,
                specimen_manifest_json TEXT
            )
        """)

        try db.exec("""
            CREATE TABLE IF NOT EXISTS results (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                campaign_id TEXT,
                seed INTEGER NOT NULL,
                init_seed INTEGER NOT NULL,
                score REAL,
                filters_passed INTEGER NOT NULL,
                backend TEXT NOT NULL,
                implementation_json TEXT NOT NULL,
                score_weights_json TEXT,
                metrics_json TEXT NOT NULL,
                params_json TEXT NOT NULL,
                sweep_json TEXT,
                worker_id TEXT
            )
        """)

        try createEcologyRunTables()
        try createMorphospaceTables()

        try db.exec("""
            CREATE TABLE IF NOT EXISTS ingest_state (
                file_path TEXT PRIMARY KEY,
                offset INTEGER NOT NULL,
                size INTEGER NOT NULL,
                mtime REAL NOT NULL
            )
        """)

        try db.exec("CREATE INDEX IF NOT EXISTS campaigns_run_campaign ON campaigns(run_id, campaign_id)")
        try db.exec("CREATE INDEX IF NOT EXISTS creatures_run_campaign ON creatures(run_id, campaign_id)")
        try db.exec("CREATE INDEX IF NOT EXISTS creatures_score ON creatures(score DESC)")
        try db.exec("CREATE INDEX IF NOT EXISTS creatures_stable ON creatures(is_stable)")
        try db.exec("CREATE INDEX IF NOT EXISTS creatures_config_hash ON creatures(config_hash)")
        try db.exec("CREATE INDEX IF NOT EXISTS creatures_canonical_specimen ON creatures(canonical_specimen_id)")
        try db.exec("CREATE INDEX IF NOT EXISTS creatures_catalog_status ON creatures(catalog_status)")
        try db.exec("""
            CREATE TABLE IF NOT EXISTS creature_qc_events (
                id TEXT PRIMARY KEY,
                creature_id TEXT NOT NULL,
                old_status TEXT,
                new_status TEXT NOT NULL,
                policy_id TEXT NOT NULL,
                reasons_json TEXT NOT NULL,
                metrics_snapshot_json TEXT,
                created_at TEXT NOT NULL
            )
        """)
        try db.exec("CREATE INDEX IF NOT EXISTS creature_qc_events_creature ON creature_qc_events(creature_id)")
        try db.exec("CREATE INDEX IF NOT EXISTS exports_creature ON exports(creature_id)")
        try db.exec("CREATE INDEX IF NOT EXISTS exports_run_dir ON exports(run_id, export_dir)")
        try db.exec("CREATE INDEX IF NOT EXISTS results_score ON results(score DESC)")
    }

    private func createEcologyRunTables() throws {
        try db.exec("""
            CREATE TABLE IF NOT EXISTS ecology_runs (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                campaign_id TEXT,
                trial_id TEXT NOT NULL,
                variant TEXT NOT NULL,
                mutation_probability REAL NOT NULL,
                repeat_index INTEGER NOT NULL,
                bundle_kind TEXT NOT NULL,
                bundle_dir TEXT NOT NULL,
                base_config_path TEXT NOT NULL,
                payload_path TEXT NOT NULL,
                metadata_path TEXT NOT NULL,
                summary_path TEXT NOT NULL,
                frames_path TEXT NOT NULL,
                activity_summary_path TEXT,
                recorded_at TEXT NOT NULL,
                final_species_count INTEGER NOT NULL,
                final_diversity REAL NOT NULL,
                final_presence_activity REAL NOT NULL,
                final_count_activity REAL NOT NULL,
                final_non_neutral_activity REAL NOT NULL,
                final_mass REAL NOT NULL,
                summary_json TEXT NOT NULL
            )
        """)
        try db.exec("CREATE UNIQUE INDEX IF NOT EXISTS ecology_runs_trial_unique ON ecology_runs(run_id, campaign_id, trial_id)")
        try db.exec("CREATE INDEX IF NOT EXISTS ecology_runs_variant ON ecology_runs(variant, mutation_probability)")
        try db.exec("CREATE INDEX IF NOT EXISTS ecology_runs_run_campaign ON ecology_runs(run_id, campaign_id)")
    }

    private func createMorphospaceTables() throws {
        try db.exec("""
            CREATE TABLE IF NOT EXISTS specimens (
                id TEXT PRIMARY KEY,
                result_id TEXT,
                creature_id TEXT,
                run_id TEXT NOT NULL,
                campaign_id TEXT,
                source_kind TEXT NOT NULL,
                recorded_at TEXT,
                seed INTEGER,
                init_seed INTEGER,
                source_mode TEXT,
                source_algorithm TEXT,
                config_hash TEXT,
                initial_condition_family TEXT,
                descriptor_version INTEGER NOT NULL,
                symmetry_policy TEXT NOT NULL,
                genotype_descriptor_json TEXT NOT NULL,
                terminal_descriptor_json TEXT NOT NULL,
                trajectory_descriptor_json TEXT,
                activity_path TEXT,
                fingerprint_path TEXT,
                provenance_json TEXT,
                runtime_family TEXT,
                runtime_capabilities_json TEXT,
                specimen_manifest_json TEXT
            )
        """)

        try db.exec("""
            CREATE TABLE IF NOT EXISTS attractor_nodes (
                id TEXT PRIMARY KEY,
                initial_condition_family TEXT NOT NULL,
                descriptor_version INTEGER NOT NULL,
                symmetry_policy TEXT NOT NULL,
                assignment_method TEXT NOT NULL,
                exemplar_specimen_id TEXT NOT NULL,
                member_count INTEGER NOT NULL,
                prototype_json TEXT NOT NULL,
                dispersion_json TEXT NOT NULL,
                reconvergence_json TEXT,
                created_at TEXT NOT NULL
            )
        """)

        try db.exec("""
            CREATE TABLE IF NOT EXISTS attractor_memberships (
                id TEXT PRIMARY KEY,
                specimen_id TEXT NOT NULL,
                attractor_id TEXT NOT NULL,
                assignment_method TEXT NOT NULL,
                assignment_version INTEGER NOT NULL,
                confidence REAL NOT NULL,
                distance REAL,
                distance_json TEXT,
                support_kind TEXT NOT NULL,
                notes_json TEXT
            )
        """)

        try db.exec("""
            CREATE TABLE IF NOT EXISTS perturbation_trials (
                id TEXT PRIMARY KEY,
                source_specimen_id TEXT NOT NULL,
                source_attractor_id TEXT,
                target_specimen_id TEXT,
                target_attractor_id TEXT,
                run_id TEXT NOT NULL,
                campaign_id TEXT,
                recorded_at TEXT NOT NULL,
                trial_kind TEXT NOT NULL,
                intervention_family TEXT NOT NULL,
                protocol_json TEXT NOT NULL,
                norm_family TEXT NOT NULL,
                norm_value REAL,
                norm_json TEXT NOT NULL,
                success INTEGER NOT NULL,
                recovered INTEGER,
                recovery_steps INTEGER,
                late_distance REAL,
                outcome_json TEXT NOT NULL
            )
        """)

        try db.exec("""
            CREATE TABLE IF NOT EXISTS transition_edges (
                id TEXT PRIMARY KEY,
                source_attractor_id TEXT NOT NULL,
                target_attractor_id TEXT NOT NULL,
                intervention_family TEXT NOT NULL,
                norm_family TEXT NOT NULL,
                edge_method TEXT NOT NULL,
                edge_version INTEGER NOT NULL,
                evidence_count INTEGER NOT NULL,
                success_count INTEGER NOT NULL,
                success_rate REAL NOT NULL,
                best_cost REAL,
                median_success_cost REAL,
                confidence REAL,
                summary_json TEXT NOT NULL
            )
        """)

        try db.exec("CREATE UNIQUE INDEX IF NOT EXISTS specimens_result_id ON specimens(result_id) WHERE result_id IS NOT NULL")
        try db.exec("CREATE UNIQUE INDEX IF NOT EXISTS specimens_creature_id ON specimens(creature_id) WHERE creature_id IS NOT NULL")
        try db.exec("CREATE INDEX IF NOT EXISTS specimens_run_campaign_seed ON specimens(run_id, campaign_id, seed)")
        try db.exec("CREATE INDEX IF NOT EXISTS specimens_run_campaign_init_source ON specimens(run_id, campaign_id, init_seed, source_kind, source_mode)")
        try db.exec("CREATE INDEX IF NOT EXISTS specimens_init_family ON specimens(initial_condition_family, symmetry_policy, descriptor_version)")
        try db.exec("CREATE INDEX IF NOT EXISTS specimens_source_kind ON specimens(source_kind)")
        try db.exec("CREATE INDEX IF NOT EXISTS attractor_nodes_family_policy ON attractor_nodes(initial_condition_family, symmetry_policy, descriptor_version)")
        try db.exec("CREATE INDEX IF NOT EXISTS attractor_nodes_exemplar ON attractor_nodes(exemplar_specimen_id)")
        try db.exec("CREATE UNIQUE INDEX IF NOT EXISTS attractor_memberships_unique ON attractor_memberships(specimen_id, assignment_method, assignment_version)")
        try db.exec("CREATE INDEX IF NOT EXISTS attractor_memberships_attractor ON attractor_memberships(attractor_id)")
        try db.exec("CREATE INDEX IF NOT EXISTS perturbation_trials_source ON perturbation_trials(source_specimen_id, intervention_family)")
        try db.exec("CREATE INDEX IF NOT EXISTS perturbation_trials_target ON perturbation_trials(target_attractor_id)")
        try db.exec("CREATE INDEX IF NOT EXISTS perturbation_trials_attractor_pair ON perturbation_trials(source_attractor_id, target_attractor_id, intervention_family)")
        try db.exec("CREATE UNIQUE INDEX IF NOT EXISTS transition_edges_unique ON transition_edges(source_attractor_id, target_attractor_id, intervention_family, norm_family, edge_method, edge_version)")
        try db.exec("CREATE INDEX IF NOT EXISTS transition_edges_source ON transition_edges(source_attractor_id)")
        try db.exec("CREATE INDEX IF NOT EXISTS transition_edges_target ON transition_edges(target_attractor_id)")
    }

    private func backfillCreatureSpecimenContracts() throws {
        guard try db.tableExists("creatures") else {
            return
        }
        let select = try db.prepare("""
            SELECT
                id, name, owner_id, run_id, campaign_id, recorded_at, score,
                config_hash, source_mode, source_algorithm, research_metadata_json,
                trait_labels_json, genotype_json, initial_condition_json, sweep_json,
                metrics_json, score_weights_json, morphometrics_json, specimen_manifest_json,
                taxonomy_family_id, taxonomy_genus_id, taxonomy_species_id,
                taxonomy_confidence, taxonomy_method, taxonomy_version
            FROM creatures
        """)
        defer { sqlite3_finalize(select) }

        let update = try db.prepare("""
            UPDATE creatures
            SET runtime_family = ?, runtime_capabilities_json = ?, specimen_manifest_json = ?
            WHERE id = ?
        """)
        defer { sqlite3_finalize(update) }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .deferredToDate

        while sqlite3_step(select) == SQLITE_ROW {
            guard let id = columnText(select, index: 0),
                  let name = columnText(select, index: 1),
                  let ownerID = columnText(select, index: 2),
                  let runID = columnText(select, index: 3) else {
                throw SQLiteIndexError.sqliteError(message: "Invalid creature row while backfilling specimen contracts.")
            }

            let manifest = try decodeOptionalJSONString(
                columnText(select, index: 18),
                as: SpecimenManifest.self,
                decoder: decoder
            )
            let researchMetadata = try decodeOptionalJSONString(
                columnText(select, index: 10),
                as: [String: AnyCodable].self,
                decoder: decoder
            )
            guard let genotypeJSON = columnText(select, index: 12),
                  let initialConditionJSON = columnText(select, index: 13),
                  let metricsJSON = columnText(select, index: 15) else {
                if manifest == nil {
                    continue
                }
                throw SQLiteIndexError.sqliteError(message: "Invalid creature row while backfilling specimen contracts.")
            }
            let projection = resolveSpecimenProjection(
                id: UUID(uuidString: id) ?? deterministicResearchUUID(id),
                name: name,
                ownerId: ownerID,
                manifest: manifest,
                fallbackGenotype: try decodeJSONString(genotypeJSON, as: KernelParams.self, decoder: decoder),
                fallbackInitialCondition: try decodeJSONString(initialConditionJSON, as: InitConfig.self, decoder: decoder),
                fallbackMetrics: try decodeJSONString(metricsJSON, as: SimulationMetrics.self, decoder: decoder),
                sweep: try decodeOptionalJSONString(columnText(select, index: 14), as: [String: Double].self, decoder: decoder),
                score: sqlite3_column_type(select, 6) == SQLITE_NULL ? nil : Float(sqlite3_column_double(select, 6)),
                scoreWeights: try decodeOptionalJSONString(columnText(select, index: 16), as: [String: Float].self, decoder: decoder),
                fallbackConfigHash: columnText(select, index: 7),
                fallbackSourceMode: columnText(select, index: 8),
                fallbackSourceAlgorithm: columnText(select, index: 9),
                fallbackResearchMetadata: researchMetadata,
                fallbackTraitLabels: try decodeOptionalJSONString(columnText(select, index: 11), as: [String].self, decoder: decoder)
            )
            let traitLabels = try decodeOptionalJSONString(
                columnText(select, index: 11),
                as: [String].self,
                decoder: decoder
            ) ?? projection.traitLabels
            let morphometrics = try decodeOptionalJSONString(
                columnText(select, index: 17),
                as: Morphometrics.self,
                decoder: decoder
            ) ?? Morphometrics.from(metrics: projection.creature.metrics, activity: nil)
            let taxonomy = SpecimenTaxonomyRecord(
                familyID: columnText(select, index: 19),
                genusID: columnText(select, index: 20),
                speciesID: columnText(select, index: 21),
                confidence: sqlite3_column_type(select, 22) == SQLITE_NULL ? nil : sqlite3_column_double(select, 22),
                method: columnText(select, index: 23),
                version: sqlite3_column_type(select, 24) == SQLITE_NULL ? nil : Int(sqlite3_column_int(select, 24))
            )
            let recordedAt = columnText(select, index: 5)
                ?? manifest?.recordedAt.map(formatter.string(from:))
            let contract = librarySpecimenContract(
                creature: projection.creature,
                campaignID: columnText(select, index: 4),
                runID: runID,
                recordedAt: parsedRecordedAt(recordedAt),
                configHash: projection.creature.configHash,
                sourceMode: projection.sourceMode,
                sourceAlgorithm: projection.sourceAlgorithm,
                researchMetadata: projection.researchMetadata,
                taxonomy: taxonomy,
                traitLabels: traitLabels,
                morphometrics: morphometrics
            )
            let persistedContract = try persistedLibrarySpecimenContract(contract)

            sqlite3_reset(update)
            sqlite3_clear_bindings(update)
            db.bindText(update, index: 1, value: persistedContract.runtimeFamily)
            db.bindText(update, index: 2, value: persistedContract.runtimeCapabilitiesJSON)
            db.bindText(update, index: 3, value: persistedContract.specimenManifestJSON)
            db.bindText(update, index: 4, value: id)
            try db.step(update)
        }
    }

    private func backfillStrictSpecimenContracts() throws {
        guard try db.tableExists("specimens") else {
            return
        }
        let strictQuery: String
        if try db.tableExists("creatures") {
            strictQuery = """
            SELECT
                s.id, s.creature_id, s.run_id, s.campaign_id, s.source_kind, s.recorded_at,
                s.source_mode, s.source_algorithm, s.config_hash, s.initial_condition_family,
                s.descriptor_version, s.symmetry_policy, s.genotype_descriptor_json,
                s.terminal_descriptor_json, s.trajectory_descriptor_json,
                c.genotype_json, c.initial_condition_json, c.metrics_json,
                c.research_metadata_json, c.morphometrics_json, c.trait_labels_json,
                c.taxonomy_family_id, c.taxonomy_genus_id, c.taxonomy_species_id,
                c.taxonomy_confidence, c.taxonomy_method, c.taxonomy_version,
                s.specimen_manifest_json
            FROM specimens s
            LEFT JOIN creatures c ON c.id = s.creature_id
            """
        } else {
            strictQuery = """
            SELECT
                s.id, s.creature_id, s.run_id, s.campaign_id, s.source_kind, s.recorded_at,
                s.source_mode, s.source_algorithm, s.config_hash, s.initial_condition_family,
                s.descriptor_version, s.symmetry_policy, s.genotype_descriptor_json,
                s.terminal_descriptor_json, s.trajectory_descriptor_json,
                NULL AS genotype_json, NULL AS initial_condition_json, NULL AS metrics_json,
                NULL AS research_metadata_json, NULL AS morphometrics_json, NULL AS trait_labels_json,
                NULL AS taxonomy_family_id, NULL AS taxonomy_genus_id, NULL AS taxonomy_species_id,
                NULL AS taxonomy_confidence, NULL AS taxonomy_method, NULL AS taxonomy_version,
                s.specimen_manifest_json
            FROM specimens s
            """
        }
        let select = try db.prepare(strictQuery)
        defer { sqlite3_finalize(select) }

        let update = try db.prepare("""
            UPDATE specimens
            SET runtime_family = ?, runtime_capabilities_json = ?, specimen_manifest_json = ?
            WHERE id = ?
        """)
        defer { sqlite3_finalize(update) }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .deferredToDate

        while sqlite3_step(select) == SQLITE_ROW {
            guard let specimenID = columnText(select, index: 0),
                  let runID = columnText(select, index: 2),
                  let sourceKind = columnText(select, index: 4),
                  let symmetryPolicy = columnText(select, index: 11),
                  let genotypeDescriptorJSON = columnText(select, index: 12),
                  let terminalDescriptorJSON = columnText(select, index: 13) else {
                throw SQLiteIndexError.sqliteError(message: "Invalid strict specimen row while backfilling specimen contracts.")
            }

            let descriptorBundle = MorphospaceDescriptorBundle(
                descriptorVersion: Int(sqlite3_column_int(select, 10)),
                symmetryPolicy: symmetryPolicy,
                genotype: try decodeJSONString(genotypeDescriptorJSON, as: MorphospaceGenotypeDescriptor.self, decoder: decoder),
                terminal: try decodeJSONString(terminalDescriptorJSON, as: MorphospaceTerminalDescriptor.self, decoder: decoder),
                trajectory: try decodeOptionalJSONString(columnText(select, index: 14), as: MorphospaceTrajectoryDescriptor.self, decoder: decoder)
            )
            let researchMetadata = try decodeOptionalJSONString(
                columnText(select, index: 18),
                as: [String: AnyCodable].self,
                decoder: decoder
            )
            let existingManifest = try decodeOptionalJSONString(
                columnText(select, index: 27),
                as: SpecimenManifest.self,
                decoder: decoder
            )
            let manifest = buildSpecimenManifest(
                specimenID: specimenID,
                creatureID: columnText(select, index: 1),
                runID: runID,
                campaignID: columnText(select, index: 3),
                sourceKind: sourceKind,
                sourceMode: columnText(select, index: 6),
                sourceAlgorithm: columnText(select, index: 7),
                configHash: columnText(select, index: 8),
                recordedAt: parsedRecordedAt(columnText(select, index: 5)),
                initialConditionFamily: columnText(select, index: 9),
                taxonomy: SpecimenTaxonomyRecord(
                    familyID: columnText(select, index: 21),
                    genusID: columnText(select, index: 22),
                    speciesID: columnText(select, index: 23),
                    confidence: sqlite3_column_type(select, 24) == SQLITE_NULL ? nil : sqlite3_column_double(select, 24),
                    method: columnText(select, index: 25),
                    version: sqlite3_column_type(select, 26) == SQLITE_NULL ? nil : Int(sqlite3_column_int(select, 26))
                ),
                traitLabels: try decodeOptionalJSONString(columnText(select, index: 20), as: [String].self, decoder: decoder),
                snapshots: SpecimenSnapshotRecord(
                    genotype: try decodeOptionalJSONString(columnText(select, index: 15), as: KernelParams.self, decoder: decoder),
                    initialCondition: try decodeOptionalJSONString(columnText(select, index: 16), as: InitConfig.self, decoder: decoder),
                    metrics: try decodeOptionalJSONString(columnText(select, index: 17), as: SimulationMetrics.self, decoder: decoder),
                    descriptorBundle: descriptorBundle,
                    morphometrics: try decodeOptionalJSONString(columnText(select, index: 19), as: Morphometrics.self, decoder: decoder)
                ),
                researchMetadata: researchMetadata
            )
            let strictContract = try persistedStrictSpecimenContract(
                baseManifest: manifest,
                overlayManifest: existingManifest
            )

            sqlite3_reset(update)
            sqlite3_clear_bindings(update)
            db.bindText(update, index: 1, value: strictContract.runtimeFamily)
            db.bindText(update, index: 2, value: strictContract.runtimeCapabilitiesJSON)
            db.bindText(update, index: 3, value: strictContract.specimenManifestJSON)
            db.bindText(update, index: 4, value: specimenID)
            try db.step(update)
        }
    }

    private func backfillExportSpecimenContracts() throws {
        guard try db.tableExists("exports") else {
            return
        }
        let exportQuery: String
        if try db.tableExists("creatures") {
            exportQuery = """
            SELECT
                e.id, e.creature_id, e.run_id, e.campaign_id, e.bundle_kind,
                e.export_dir, e.base_config_path, e.search_config_path, e.payload_path,
                e.exported_at,
                c.source_mode, c.source_algorithm, c.config_hash, c.research_metadata_json
            FROM exports e
            LEFT JOIN creatures c ON c.id = e.creature_id
            """
        } else {
            exportQuery = """
            SELECT
                e.id, e.creature_id, e.run_id, e.campaign_id, e.bundle_kind,
                e.export_dir, e.base_config_path, e.search_config_path, e.payload_path,
                e.exported_at,
                NULL AS source_mode, NULL AS source_algorithm, NULL AS config_hash, NULL AS research_metadata_json
            FROM exports e
            """
        }
        let select = try db.prepare(exportQuery)
        defer { sqlite3_finalize(select) }

        let update = try db.prepare("""
            UPDATE exports
            SET runtime_family = ?, runtime_capabilities_json = ?, specimen_manifest_json = ?
            WHERE id = ?
        """)
        defer { sqlite3_finalize(update) }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .deferredToDate

        while sqlite3_step(select) == SQLITE_ROW {
            guard let exportID = columnText(select, index: 0),
                  let creatureID = columnText(select, index: 1),
                  let runID = columnText(select, index: 2),
                  let bundleKindRaw = columnText(select, index: 4),
                  let bundleKind = LeniaArtifactBundleKind(rawValue: bundleKindRaw),
                  let exportDir = columnText(select, index: 5) else {
                throw SQLiteIndexError.sqliteError(message: "Invalid export row while backfilling specimen contracts.")
            }

            let researchMetadata = try decodeOptionalJSONString(
                columnText(select, index: 13),
                as: [String: AnyCodable].self,
                decoder: decoder
            )
            let manifest = buildExportSpecimenManifest(
                creatureID: creatureID,
                runID: runID,
                campaignID: columnText(select, index: 3),
                recordedAt: parsedRecordedAt(columnText(select, index: 9)),
                sourceMode: columnText(select, index: 10),
                sourceAlgorithm: columnText(select, index: 11),
                configHash: columnText(select, index: 12),
                bundleKind: bundleKind,
                exportDir: exportDir,
                baseConfigPath: columnText(select, index: 6),
                searchConfigPath: columnText(select, index: 7),
                payloadPath: columnText(select, index: 8),
                researchMetadata: researchMetadata
            )

            try persistExportManifest(manifest, creatureID: creatureID) {
                runtimeFamily,
                runtimeCapabilitiesJSON,
                specimenManifestJSON in
                sqlite3_reset(update)
                sqlite3_clear_bindings(update)
                db.bindText(update, index: 1, value: runtimeFamily)
                db.bindText(update, index: 2, value: runtimeCapabilitiesJSON)
                db.bindText(update, index: 3, value: specimenManifestJSON)
                db.bindText(update, index: 4, value: exportID)
                try db.step(update)
            }
        }
    }

    private func persistExportManifest(
        _ manifest: SpecimenManifest,
        creatureID: String,
        persist: (_ runtimeFamily: String, _ runtimeCapabilitiesJSON: String, _ specimenManifestJSON: String) throws -> Void
    ) throws {
        try persist(
            manifest.runtimeFamily,
            try jsonString(manifest.runtimeCapabilities),
            try jsonString(manifest)
        )
        try applyExportManifestToStrictSpecimens(
            creatureID: creatureID,
            exportManifest: manifest
        )
    }

    private func applyExportManifestToStrictSpecimens(
        creatureID: String,
        exportManifest: SpecimenManifest
    ) throws {
        guard try db.tableExists("specimens") else {
            return
        }
        let select = try db.prepare("""
            SELECT id, specimen_manifest_json
            FROM specimens
            WHERE creature_id = ?
        """)
        defer { sqlite3_finalize(select) }
        db.bindText(select, index: 1, value: creatureID)

        let update = try db.prepare("""
            UPDATE specimens
            SET runtime_family = ?, runtime_capabilities_json = ?, specimen_manifest_json = ?
            WHERE id = ?
        """)
        defer { sqlite3_finalize(update) }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .deferredToDate

        while sqlite3_step(select) == SQLITE_ROW {
            guard let specimenID = columnText(select, index: 0) else {
                continue
            }

            let existingManifest = try decodeOptionalJSONString(
                columnText(select, index: 1),
                as: SpecimenManifest.self,
                decoder: decoder
            )
            let strictContract = try persistedStrictSpecimenContract(
                baseManifest: existingManifest ?? exportManifest,
                overlayManifest: exportManifest
            )

            sqlite3_reset(update)
            sqlite3_clear_bindings(update)
            db.bindText(update, index: 1, value: strictContract.runtimeFamily)
            db.bindText(update, index: 2, value: strictContract.runtimeCapabilitiesJSON)
            db.bindText(update, index: 3, value: strictContract.specimenManifestJSON)
            db.bindText(update, index: 4, value: specimenID)
            try db.step(update)
        }
    }

    private func parsedRecordedAt(_ value: String?) -> Date {
        if let value, let date = formatter.date(from: value) {
            return date
        }
        return Date(timeIntervalSince1970: 0)
    }

    private func decodeJSONString<T: Decodable>(
        _ text: String,
        as type: T.Type,
        decoder: JSONDecoder
    ) throws -> T {
        guard let data = text.data(using: .utf8) else {
            throw SQLiteIndexError.invalidUTF8("json")
        }
        return try decoder.decode(type, from: data)
    }

    private func decodeOptionalJSONString<T: Decodable>(
        _ text: String?,
        as type: T.Type,
        decoder: JSONDecoder
    ) throws -> T? {
        guard let text else {
            return nil
        }
        return try decodeJSONString(text, as: type, decoder: decoder)
    }

    private func upsertRun(
        runKey: String,
        runName: String,
        runDir: String,
        hostId: String?,
        outputRoot: String?,
        configHash: String? = nil,
        sourceMode: String? = nil,
        sourceAlgorithm: String? = nil
    ) throws {
        let indexedAt = formatter.string(from: Date())
        let stmt = try db.prepare("""
            INSERT INTO runs (
                run_id, run_name, host_id, output_root, run_dir, indexed_at, config_hash, source_mode, source_algorithm
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                run_name = excluded.run_name,
                host_id = excluded.host_id,
                output_root = excluded.output_root,
                run_dir = excluded.run_dir,
                indexed_at = excluded.indexed_at,
                config_hash = COALESCE(excluded.config_hash, runs.config_hash),
                source_mode = COALESCE(excluded.source_mode, runs.source_mode),
                source_algorithm = COALESCE(excluded.source_algorithm, runs.source_algorithm)
        """)
        defer { sqlite3_finalize(stmt) }
        db.bindText(stmt, index: 1, value: runKey)
        db.bindText(stmt, index: 2, value: runName)
        db.bindText(stmt, index: 3, value: hostId)
        db.bindText(stmt, index: 4, value: outputRoot)
        db.bindText(stmt, index: 5, value: runDir)
        db.bindText(stmt, index: 6, value: indexedAt)
        db.bindText(stmt, index: 7, value: configHash)
        db.bindText(stmt, index: 8, value: sourceMode)
        db.bindText(stmt, index: 9, value: sourceAlgorithm)
        try db.step(stmt)
    }

    private func ensureCampaign(_ campaignId: String, runKey: String) throws {
        let stmt = try db.prepare("INSERT OR REPLACE INTO campaigns (run_id, campaign_id) VALUES (?, ?)")
        defer { sqlite3_finalize(stmt) }
        db.bindText(stmt, index: 1, value: runKey)
        db.bindText(stmt, index: 2, value: campaignId)
        try db.step(stmt)
    }

    private func withDecodedJSONLLines<Record: Decodable>(
        path: URL,
        configureDecoder: (JSONDecoder) -> Void = { _ in },
        decodeRecord: ((Data, JSONDecoder) throws -> Record)? = nil,
        _ body: ([Record]) throws -> Void
    ) throws {
        let (lines, newOffset, attrs) = try readJSONLLines(path: path)
        guard !lines.isEmpty else {
            try updateIngestState(path: path, offset: newOffset, attrs: attrs)
            return
        }

        try db.withImmediateTransaction {
            let decoder = JSONDecoder()
            configureDecoder(decoder)
            let records = try lines.compactMap { line -> Record? in
                guard let data = line.data(using: .utf8) else { return nil }
                if let decodeRecord {
                    return try decodeRecord(data, decoder)
                }
                return try decoder.decode(Record.self, from: data)
            }
            try body(records)
            try updateIngestState(path: path, offset: newOffset, attrs: attrs)
        }
    }

    private func ingestLibraryIndex(path: URL, runKey: String, runDir: URL) throws {
        try withDecodedJSONLLines(
            path: path,
            configureDecoder: { $0.dateDecodingStrategy = .deferredToDate },
            decodeRecord: decodeResearchLibraryEntry
        ) { (entries: [ResearchLibraryEntry]) in
            let provenance = try resolvedLibraryProvenance(entries: entries, runKey: runKey, path: path)

            let creaturePlaceholders = Array(repeating: "?", count: 52).joined(separator: ",")
            let stmt = try db.prepare("""
                INSERT INTO creatures (
                    id, name, owner_id, run_id, campaign_id, recorded_at, init_seed, score, is_stable,
                    mass_mean, mass_std, mass_min, mass_max, occupancy_mean, variance_mean, energy_mean,
                    speed_mean, path_length, displacement, gyration, center_velocity,
                    velocity_x, velocity_y, heading_rad,
                    complexity_mean, complexity_target_score,
                    activity_eac_mean, activity_ean_mean, activity_diversity_mean, activity_species_mean,
                    taxonomy_family_id, taxonomy_genus_id, taxonomy_species_id, taxonomy_confidence, taxonomy_method, taxonomy_version,
                    morphometrics_json, morphometrics_method, morphometrics_version,
                    config_hash, source_mode, source_algorithm, research_metadata_json,
                    runtime_family, runtime_capabilities_json, specimen_manifest_json,
                    canonical_specimen_id,
                    score_weights_json, genotype_json, initial_condition_json, sweep_json, metrics_json
                ) VALUES (\(creaturePlaceholders))
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    owner_id = excluded.owner_id,
                    run_id = excluded.run_id,
                    campaign_id = excluded.campaign_id,
                    recorded_at = excluded.recorded_at,
                    init_seed = excluded.init_seed,
                    score = excluded.score,
                    is_stable = excluded.is_stable,
                    mass_mean = excluded.mass_mean,
                    mass_std = excluded.mass_std,
                    mass_min = excluded.mass_min,
                    mass_max = excluded.mass_max,
                    occupancy_mean = excluded.occupancy_mean,
                    variance_mean = excluded.variance_mean,
                    energy_mean = excluded.energy_mean,
                    speed_mean = excluded.speed_mean,
                    path_length = excluded.path_length,
                    displacement = excluded.displacement,
                    gyration = excluded.gyration,
                    center_velocity = excluded.center_velocity,
                    velocity_x = excluded.velocity_x,
                    velocity_y = excluded.velocity_y,
                    heading_rad = excluded.heading_rad,
                    complexity_mean = excluded.complexity_mean,
                    complexity_target_score = excluded.complexity_target_score,
                    activity_eac_mean = excluded.activity_eac_mean,
                    activity_ean_mean = excluded.activity_ean_mean,
                    activity_diversity_mean = excluded.activity_diversity_mean,
                    activity_species_mean = excluded.activity_species_mean,
                    morphometrics_json = excluded.morphometrics_json,
                    morphometrics_method = excluded.morphometrics_method,
                    morphometrics_version = excluded.morphometrics_version,
                    config_hash = COALESCE(excluded.config_hash, creatures.config_hash),
                    source_mode = COALESCE(excluded.source_mode, creatures.source_mode),
                    source_algorithm = COALESCE(excluded.source_algorithm, creatures.source_algorithm),
                    research_metadata_json = COALESCE(excluded.research_metadata_json, creatures.research_metadata_json),
                    runtime_family = COALESCE(excluded.runtime_family, creatures.runtime_family),
                    runtime_capabilities_json = COALESCE(excluded.runtime_capabilities_json, creatures.runtime_capabilities_json),
                    specimen_manifest_json = COALESCE(excluded.specimen_manifest_json, creatures.specimen_manifest_json),
                    canonical_specimen_id = COALESCE(creatures.canonical_specimen_id, excluded.canonical_specimen_id),
                    score_weights_json = excluded.score_weights_json,
                    genotype_json = excluded.genotype_json,
                    initial_condition_json = excluded.initial_condition_json,
                    sweep_json = excluded.sweep_json,
                    metrics_json = excluded.metrics_json
            """)
            defer { sqlite3_finalize(stmt) }

            for entry in entries {
                let creature = entry.creature

                if let campaignId = entry.campaignId {
                    try ensureCampaign(campaignId, runKey: runKey)
                }

                let recordedAt = formatter.string(from: entry.recordedAt)

                let genotypeJSON = try jsonString(creature.genotype)
                let initialConditionJSON = try jsonString(creature.initialCondition)
                let metricsJSON = try jsonString(creature.metrics)
                let sweepJSON = try jsonString(creature.sweep)
                let scoreWeightsJSON = try jsonString(creature.scoreWeights as [String: Float]?)
                let researchMetadataJSON = try jsonString(entry.researchMetadata)
                let contract = librarySpecimenContract(
                    creature: creature,
                    campaignID: entry.campaignId,
                    runID: runKey,
                    recordedAt: entry.recordedAt,
                    configHash: entry.configHash ?? creature.configHash,
                    sourceMode: entry.sourceMode,
                    sourceAlgorithm: entry.sourceAlgorithm,
                    researchMetadata: entry.researchMetadata
                )
                let persistedContract = try persistedLibrarySpecimenContract(contract)
                let taxonomyConfidence: Double? = nil
                let taxonomyVersion: Int? = nil

                sqlite3_reset(stmt)
                sqlite3_clear_bindings(stmt)

                db.bindText(stmt, index: 1, value: creature.id.uuidString)
                db.bindText(stmt, index: 2, value: creature.name)
                db.bindText(stmt, index: 3, value: creature.ownerId)
                db.bindText(stmt, index: 4, value: runKey)
                db.bindText(stmt, index: 5, value: entry.campaignId)
                db.bindText(stmt, index: 6, value: recordedAt)
                db.bindInt(stmt, index: 7, value: creature.initialCondition.seed)
                db.bindDouble(stmt, index: 8, value: creature.score)
                db.bindBool(stmt, index: 9, value: creature.metrics.isStable)

                db.bindDouble(stmt, index: 10, value: creature.metrics.massMean)
                db.bindDouble(stmt, index: 11, value: creature.metrics.massStd)
                db.bindDouble(stmt, index: 12, value: creature.metrics.massMin)
                db.bindDouble(stmt, index: 13, value: creature.metrics.massMax)
                db.bindDouble(stmt, index: 14, value: creature.metrics.occupancyMean)
                db.bindDouble(stmt, index: 15, value: creature.metrics.varianceMean)
                db.bindDouble(stmt, index: 16, value: creature.metrics.energyMean)
                db.bindDouble(stmt, index: 17, value: creature.metrics.speedMean)
                db.bindDouble(stmt, index: 18, value: creature.metrics.pathLength)
                db.bindDouble(stmt, index: 19, value: creature.metrics.displacement)
                db.bindDouble(stmt, index: 20, value: creature.metrics.gyration)
                db.bindDouble(stmt, index: 21, value: creature.metrics.centerVelocity)
                db.bindDouble(stmt, index: 22, value: creature.metrics.velocityX)
                db.bindDouble(stmt, index: 23, value: creature.metrics.velocityY)
                db.bindDouble(stmt, index: 24, value: creature.metrics.headingRad)
                db.bindDouble(stmt, index: 25, value: creature.metrics.complexityMean)
                db.bindDouble(stmt, index: 26, value: creature.metrics.complexityTargetScore)
                db.bindDouble(stmt, index: 27, value: creature.metrics.activityEacMean)
                db.bindDouble(stmt, index: 28, value: creature.metrics.activityEanMean)
                db.bindDouble(stmt, index: 29, value: creature.metrics.activityDiversityMean)
                db.bindDouble(stmt, index: 30, value: creature.metrics.activitySpeciesMean)
                db.bindText(stmt, index: 31, value: nil)
                db.bindText(stmt, index: 32, value: nil)
                db.bindText(stmt, index: 33, value: nil)
                db.bindDouble(stmt, index: 34, value: taxonomyConfidence)
                db.bindText(stmt, index: 35, value: nil)
                db.bindInt(stmt, index: 36, value: taxonomyVersion)
                db.bindText(stmt, index: 37, value: persistedContract.morphometricsJSON)
                db.bindText(stmt, index: 38, value: "lenia-swarm:morphometrics")
                db.bindInt(stmt, index: 39, value: persistedContract.morphometrics.version)
                db.bindText(stmt, index: 40, value: entry.configHash ?? creature.configHash)
                db.bindText(stmt, index: 41, value: persistedContract.sourceMode)
                db.bindText(stmt, index: 42, value: entry.sourceAlgorithm)
                db.bindText(stmt, index: 43, value: researchMetadataJSON)
                db.bindText(stmt, index: 44, value: persistedContract.runtimeFamily)
                db.bindText(stmt, index: 45, value: persistedContract.runtimeCapabilitiesJSON)
                db.bindText(stmt, index: 46, value: persistedContract.specimenManifestJSON)
                db.bindText(stmt, index: 47, value: nil)
                db.bindText(stmt, index: 48, value: scoreWeightsJSON)
                db.bindText(stmt, index: 49, value: genotypeJSON)
                db.bindText(stmt, index: 50, value: initialConditionJSON)
                db.bindText(stmt, index: 51, value: sweepJSON)
                db.bindText(stmt, index: 52, value: metricsJSON)

                try db.step(stmt)
                _ = try upsertSpecimenFromCreature(
                    creature: creature,
                    entry: entry,
                    runKey: runKey,
                    runDir: runDir,
                    sourcePath: path,
                    contract: contract
                )
            }

            try upsertRun(
                runKey: runKey,
                runName: provenance.runName,
                runDir: provenance.runDir,
                hostId: provenance.hostId,
                outputRoot: provenance.outputRoot,
                configHash: provenance.configHash,
                sourceMode: provenance.sourceMode,
                sourceAlgorithm: provenance.sourceAlgorithm
            )
        }
    }

    private func resolvedLibraryProvenance(
        entries: [ResearchLibraryEntry],
        runKey: String,
        path: URL
    ) throws -> (runName: String, runDir: String, hostId: String?, outputRoot: String?, configHash: String?, sourceMode: String?, sourceAlgorithm: String?) {
        var sourceMode: String?
        var sourceAlgorithm: String?
        var configHash: String?

        for entry in entries {
            if let entryMode = normalizedSpecimenSourceMode(entry.sourceMode) {
                if let sourceMode, sourceMode != entryMode {
                    throw SQLiteIndexError.sqliteError(
                        message: "Conflicting source_mode values in \(path.path) for run \(runKey): \(sourceMode) vs \(entryMode)"
                    )
                }
                sourceMode = entryMode
            }
            if let entryAlgorithm = normalized(entry.sourceAlgorithm) {
                if let sourceAlgorithm, sourceAlgorithm != entryAlgorithm {
                    throw SQLiteIndexError.sqliteError(
                        message: "Conflicting source_algorithm values in \(path.path) for run \(runKey): \(sourceAlgorithm) vs \(entryAlgorithm)"
                    )
                }
                sourceAlgorithm = entryAlgorithm
            }
            let entryConfigHash = normalized(entry.configHash ?? entry.creature.configHash)
            if let entryConfigHash {
                if let configHash, configHash != entryConfigHash {
                    throw SQLiteIndexError.sqliteError(
                        message: "Conflicting config_hash values in \(path.path) for run \(runKey): \(configHash) vs \(entryConfigHash)"
                    )
                }
                configHash = entryConfigHash
            }
        }

        let stmt = try db.prepare("""
            SELECT run_name, run_dir, host_id, output_root, config_hash, source_mode, source_algorithm
            FROM runs WHERE run_id = ?
        """)
        defer { sqlite3_finalize(stmt) }
        db.bindText(stmt, index: 1, value: runKey)
        let hasExisting = sqlite3_step(stmt) == SQLITE_ROW
        return (
            runName: hasExisting ? columnText(stmt, index: 0) ?? runKey : runKey,
            runDir: hasExisting ? columnText(stmt, index: 1) ?? runKey : runKey,
            hostId: hasExisting ? columnText(stmt, index: 2) : nil,
            outputRoot: hasExisting ? columnText(stmt, index: 3) : nil,
            configHash: configHash ?? (hasExisting ? columnText(stmt, index: 4) : nil),
            sourceMode: sourceMode ?? (hasExisting ? columnText(stmt, index: 5) : nil),
            sourceAlgorithm: sourceAlgorithm ?? (hasExisting ? columnText(stmt, index: 6) : nil)
        )
    }

    private func ingestExportIndex(path: URL, runKey: String, runDir: URL) throws {
        try withDecodedJSONLLines(path: path, configureDecoder: {
            $0.dateDecodingStrategy = .deferredToDate
        }) { (records: [ExportRecord]) in
            let exportPlaceholders = Array(repeating: "?", count: 18).joined(separator: ",")
            let stmt = try db.prepare("""
                INSERT OR REPLACE INTO exports (
                    id, export_dir, creature_id, name, owner_id, run_id, campaign_id,
                    bundle_kind, base_config_path, search_config_path, payload_path,
                    exported_at, reason, score, filters_passed,
                    runtime_family, runtime_capabilities_json, specimen_manifest_json
                ) VALUES (\(exportPlaceholders))
            """)
            defer { sqlite3_finalize(stmt) }
            for record in records {
                if let campaignId = record.campaignId {
                    try ensureCampaign(campaignId, runKey: runKey)
                }

                let exportDir = relativePath(record.exportDir, base: runDir)
                let baseConfigPath = record.baseConfigPath.map { relativePath($0, base: runDir) }
                let searchConfigPath = record.searchConfigPath.map { relativePath($0, base: runDir) }
                let payloadPath = record.payloadPath.map { relativePath($0, base: runDir) }
                let specimenManifest = buildExportSpecimenManifest(
                    creatureID: record.creatureId.uuidString,
                    runID: runKey,
                    campaignID: record.campaignId,
                    recordedAt: record.exportedAt,
                    sourceMode: record.specimenManifest?.sourceMode,
                    sourceAlgorithm: record.specimenManifest?.sourceAlgorithm,
                    configHash: record.specimenManifest?.configHash,
                    bundleKind: record.bundleKind,
                    exportDir: exportDir,
                    baseConfigPath: baseConfigPath,
                    searchConfigPath: searchConfigPath,
                    payloadPath: payloadPath,
                    researchMetadata: record.specimenManifest?.researchMetadata
                )
                try persistExportManifest(specimenManifest, creatureID: record.creatureId.uuidString) {
                    runtimeFamily,
                    runtimeCapabilitiesJSON,
                    specimenManifestJSON in
                    sqlite3_reset(stmt)
                    sqlite3_clear_bindings(stmt)

                    db.bindText(stmt, index: 1, value: Self.exportRecordId(runKey: runKey, exportDir: exportDir))
                    db.bindText(stmt, index: 2, value: exportDir)
                    db.bindText(stmt, index: 3, value: record.creatureId.uuidString)
                    db.bindText(stmt, index: 4, value: record.name)
                    db.bindText(stmt, index: 5, value: record.ownerId)
                    db.bindText(stmt, index: 6, value: runKey)
                    db.bindText(stmt, index: 7, value: record.campaignId)
                    db.bindText(stmt, index: 8, value: record.bundleKind.rawValue)
                    db.bindText(stmt, index: 9, value: baseConfigPath)
                    db.bindText(stmt, index: 10, value: searchConfigPath)
                    db.bindText(stmt, index: 11, value: payloadPath)
                    db.bindText(stmt, index: 12, value: formatter.string(from: record.exportedAt))
                    db.bindText(stmt, index: 13, value: record.reason)
                    db.bindDouble(stmt, index: 14, value: record.score)
                    db.bindBool(stmt, index: 15, value: record.filtersPassed)
                    db.bindText(stmt, index: 16, value: runtimeFamily)
                    db.bindText(stmt, index: 17, value: runtimeCapabilitiesJSON)
                    db.bindText(stmt, index: 18, value: specimenManifestJSON)

                    try db.step(stmt)
                }
            }
        }
    }

    private func ingestEcologyRuns(path: URL, runKey: String, campaignId: String?, runDir: URL) throws {
        try withDecodedJSONLLines(path: path, configureDecoder: {
            $0.dateDecodingStrategy = .deferredToDate
        }) { (records: [FlowLeniaEcology2025RunRecord]) in
            if let campaignId {
                try ensureCampaign(campaignId, runKey: runKey)
            }

            let stmt = try db.prepare("""
                INSERT OR REPLACE INTO ecology_runs (
                    id, run_id, campaign_id, trial_id, variant, mutation_probability, repeat_index,
                    bundle_kind, bundle_dir, base_config_path, payload_path, metadata_path,
                    summary_path, frames_path, activity_summary_path, recorded_at,
                    final_species_count, final_diversity, final_presence_activity,
                    final_count_activity, final_non_neutral_activity, final_mass, summary_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """)
            defer { sqlite3_finalize(stmt) }

            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .deferredToDate
            for record in records {
                let resolvedCampaignId = campaignId ?? record.campaignID
                if let resolvedCampaignId {
                    try ensureCampaign(resolvedCampaignId, runKey: runKey)
                }

                let summaryURL = URL(fileURLWithPath: record.summaryPath)
                let summary = try decoder.decode(
                    FlowLeniaEcology2025RunSummary.self,
                    from: Data(contentsOf: summaryURL)
                )

                sqlite3_reset(stmt)
                sqlite3_clear_bindings(stmt)

                db.bindText(
                    stmt,
                    index: 1,
                    value: Self.ecologyRunRecordId(
                        runKey: runKey,
                        campaignId: resolvedCampaignId,
                        trialId: record.trialID
                    )
                )
                db.bindText(stmt, index: 2, value: runKey)
                db.bindText(stmt, index: 3, value: resolvedCampaignId)
                db.bindText(stmt, index: 4, value: record.trialID)
                db.bindText(stmt, index: 5, value: record.variant)
                db.bindDouble(stmt, index: 6, value: record.mutationProbability)
                db.bindInt(stmt, index: 7, value: record.repeatIndex)
                db.bindText(stmt, index: 8, value: record.bundleKind.rawValue)
                db.bindText(stmt, index: 9, value: relativePath(record.bundleDir, base: runDir))
                db.bindText(stmt, index: 10, value: relativePath(record.baseConfigPath, base: runDir))
                db.bindText(stmt, index: 11, value: relativePath(record.payloadPath, base: runDir))
                db.bindText(stmt, index: 12, value: relativePath(record.metadataPath, base: runDir))
                db.bindText(stmt, index: 13, value: relativePath(record.summaryPath, base: runDir))
                db.bindText(stmt, index: 14, value: relativePath(record.framesPath, base: runDir))
                db.bindText(stmt, index: 15, value: record.activitySummaryPath.map { relativePath($0, base: runDir) })
                db.bindText(stmt, index: 16, value: formatter.string(from: record.exportedAt))
                db.bindInt(stmt, index: 17, value: summary.finalSpeciesCount)
                db.bindDouble(stmt, index: 18, value: summary.finalDiversity)
                db.bindDouble(stmt, index: 19, value: summary.finalPresenceActivity)
                db.bindDouble(stmt, index: 20, value: summary.finalCountActivity)
                db.bindDouble(stmt, index: 21, value: summary.finalNonNeutralActivity)
                db.bindDouble(stmt, index: 22, value: summary.finalMass)
                db.bindText(stmt, index: 23, value: try jsonString(summary))

                try db.step(stmt)
            }
        }
    }

    private func ingestResults(path: URL, runKey: String, campaignId: String?, runDir: URL) throws {
        try withDecodedJSONLLines(path: path) { (results: [SimulationResultData]) in
            if let campaignId = campaignId {
                try ensureCampaign(campaignId, runKey: runKey)
            }

            let stmt = try db.prepare("""
                INSERT OR REPLACE INTO results (
                    id, run_id, campaign_id, seed, init_seed, score, filters_passed,
                    backend, implementation_json, score_weights_json,
                    metrics_json, params_json, sweep_json, worker_id
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """)
            defer { sqlite3_finalize(stmt) }
            for result in results {
                let id = "\(runKey)|\(campaignId ?? "overall")|\(result.seed)"
                let metricsJSON = try jsonString(result.metrics)
                let paramsJSON = try jsonString(result.params)
                let sweepJSON = try jsonString(result.sweep)
                let implJSON = try jsonString(result.implementation)
                let weightsJSON = try jsonString(result.scoreWeights as [String: Float]?)

                sqlite3_reset(stmt)
                sqlite3_clear_bindings(stmt)

                db.bindText(stmt, index: 1, value: id)
                db.bindText(stmt, index: 2, value: runKey)
                db.bindText(stmt, index: 3, value: campaignId)
                db.bindInt(stmt, index: 4, value: result.seed)
                db.bindInt(stmt, index: 5, value: result.initSeed)
                db.bindDouble(stmt, index: 6, value: result.score)
                db.bindBool(stmt, index: 7, value: result.filtersPassed)
                db.bindText(stmt, index: 8, value: result.backend)
                db.bindText(stmt, index: 9, value: implJSON)
                db.bindText(stmt, index: 10, value: weightsJSON)
                db.bindText(stmt, index: 11, value: metricsJSON)
                db.bindText(stmt, index: 12, value: paramsJSON)
                db.bindText(stmt, index: 13, value: sweepJSON)
                db.bindText(stmt, index: 14, value: result.workerId)

                try db.step(stmt)
                try upsertSpecimenFromResult(
                    result: result,
                    runKey: runKey,
                    campaignId: campaignId,
                    runDir: runDir,
                    sourcePath: path
                )
            }
        }
    }

    private func ingestActivitySummary(path: URL, runKey: String, campaignId: String?, runDir: URL) throws {
        try withDecodedJSONLLines(path: path) { (records: [ActivitySummaryRecord]) in
            if let campaignId = campaignId {
                try ensureCampaign(campaignId, runKey: runKey)
            }

            let metricsDecoder = JSONDecoder()

            var selectSQL = """
            SELECT id, metrics_json, morphometrics_json
            FROM creatures
            WHERE run_id = ? AND init_seed = ?
            """
            if campaignId != nil {
                selectSQL += " AND campaign_id = ?"
            } else {
                selectSQL += " AND campaign_id IS NULL"
            }

            let select = try db.prepare(selectSQL)
            defer { sqlite3_finalize(select) }

            let update = try db.prepare("""
                UPDATE creatures
                SET morphometrics_json = ?, morphometrics_method = ?, morphometrics_version = ?
                WHERE id = ?
            """)
            defer { sqlite3_finalize(update) }

            for record in records {
                sqlite3_reset(select)
                sqlite3_clear_bindings(select)
                db.bindText(select, index: 1, value: runKey)
                db.bindInt(select, index: 2, value: record.seed)
                if let campaignId = campaignId {
                    db.bindText(select, index: 3, value: campaignId)
                }

                while sqlite3_step(select) == SQLITE_ROW {
                    guard let idC = sqlite3_column_text(select, 0),
                          let metricsC = sqlite3_column_text(select, 1) else {
                        throw SQLiteIndexError.sqliteError(message: "Invalid creatures row for activity upsert (missing id/metrics_json)")
                    }
                    let id = String(cString: idC)
                    let metricsJSON = String(cString: metricsC)

                    guard let metricsData = metricsJSON.data(using: .utf8) else {
                        throw SQLiteIndexError.invalidUTF8("creatures.metrics_json")
                    }
                    let metrics = try metricsDecoder.decode(SimulationMetrics.self, from: metricsData)

                    var morph = Morphometrics.from(metrics: metrics, activity: nil)
                    if let existingC = sqlite3_column_text(select, 2) {
                        let existingJSON = String(cString: existingC)
                        if let existingData = existingJSON.data(using: .utf8) {
                            if let decoded = try? metricsDecoder.decode(Morphometrics.self, from: existingData) {
                                morph = decoded
                            }
                        }
                    }

                    morph = morph.with(activity: record.summary)

                    let encoded = try jsonString(morph)

                    sqlite3_reset(update)
                    sqlite3_clear_bindings(update)
                    db.bindText(update, index: 1, value: encoded)
                    db.bindText(update, index: 2, value: "lenia-swarm:morphometrics")
                    db.bindInt(update, index: 3, value: morph.version)
                    db.bindText(update, index: 4, value: id)
                    try db.step(update)
                    try updateSpecimensFromActivitySummary(
                        runKey: runKey,
                        campaignId: campaignId,
                        seed: record.seed,
                        summary: record.summary,
                        runDir: runDir,
                        sourcePath: path
                    )
                }
            }
        }
    }

    private func upsertSpecimenFromResult(
        result: SimulationResultData,
        runKey: String,
        campaignId: String?,
        runDir: URL,
        sourcePath: URL
    ) throws {
        // Do not reconstruct morphospace specimens from summary metrics. If a lane did not emit a
        // real descriptor bundle, it is not eligible for attractor/transition indexing.
        guard let descriptorBundle = result.descriptorBundle,
              let initialConditionFamily = nonEmpty(result.initialConditionFamily) else {
            return
        }
        let provenance = specimenProvenance(
            sourceKind: "result",
            runKey: runKey,
            campaignId: campaignId,
            sourceMode: nil,
            sourceAlgorithm: nil,
            configHash: nil,
            initialConditionFamily: initialConditionFamily,
            sourceRef: "result:\(runKey)|\(campaignId ?? "overall")|\(result.seed)",
            sourcePath: relativePath(sourcePath.path, base: runDir)
        )

        try deleteRedundantReplayLibrarySpecimens(
            runKey: runKey,
            campaignId: campaignId,
            initSeed: result.initSeed
        )
        let specimenID = "result:\(runKey)|\(campaignId ?? "overall")|\(result.seed)"
        let specimenManifest = buildResultSpecimenManifest(
            specimenID: specimenID,
            runID: runKey,
            campaignID: campaignId,
            sourceMode: nil,
            sourceAlgorithm: nil,
            configHash: nil,
            initialConditionFamily: initialConditionFamily,
            result: result
        )
        try upsertSpecimen(try descriptorSpecimenRecord(
            id: specimenID,
            resultId: specimenID,
            creatureId: nil,
            runId: runKey,
            campaignId: campaignId,
            sourceKind: "result",
            recordedAt: nil,
            seed: result.seed,
            initSeed: result.initSeed,
            sourceMode: nil,
            sourceAlgorithm: nil,
            configHash: nil,
            initialConditionFamily: initialConditionFamily,
            descriptorBundle: descriptorBundle,
            provenance: provenance,
            manifest: specimenManifest
        ))
    }

    private func upsertSpecimenFromExportMetadata(
        metadata: CreatureExportMetadata,
        gap: CanonicalCreatureGap,
        runDir: URL,
        sourcePath: URL
    ) throws -> String? {
        let specimenID = "creature:\(gap.creatureID)"
        return try upsertLibraryLikeSpecimen(
            creature: metadata.creature,
            specimenID: specimenID,
            creatureID: gap.creatureID,
            runId: gap.runID,
            campaignId: gap.campaignID,
            sourceKind: "backfill",
            provenanceKind: "export_metadata",
            recordedAt: formatter.string(from: metadata.exportedAt),
            sourceMode: gap.sourceMode,
            sourceAlgorithm: gap.sourceAlgorithm,
            configHash: gap.configHash ?? metadata.creature.configHash,
            researchMetadata: gap.researchMetadata,
            manifestRecordedAt: metadata.exportedAt,
            sourcePath: relativePath(sourcePath.path, base: runDir)
        )
    }

    private func upsertSpecimenFromCreature(
        creature: SavedCreature,
        entry: ResearchLibraryEntry,
        runKey: String,
        runDir: URL,
        sourcePath: URL,
        contract: LibrarySpecimenContract? = nil
    ) throws -> String? {
        // Summary-only paper-lane exports stay in creatures but are excluded from specimens until
        // they preserve a real runtime descriptor bundle.
        let specimenID = "creature:\(creature.id.uuidString)"
        return try upsertLibraryLikeSpecimen(
            creature: creature,
            specimenID: specimenID,
            creatureID: creature.id.uuidString,
            runId: runKey,
            campaignId: entry.campaignId,
            sourceKind: "library",
            provenanceKind: "library",
            recordedAt: formatter.string(from: entry.recordedAt),
            sourceMode: entry.sourceMode,
            sourceAlgorithm: entry.sourceAlgorithm,
            configHash: entry.configHash ?? creature.configHash,
            researchMetadata: entry.researchMetadata,
            manifestRecordedAt: entry.recordedAt,
            sourcePath: relativePath(sourcePath.path, base: runDir),
            contract: contract
        )
    }

    private struct LibrarySpecimenContract {
        let sourceMode: String?
        let morphometrics: Morphometrics
        let manifest: SpecimenManifest
    }

    private struct PersistedLibrarySpecimenContract {
        let sourceMode: String?
        let morphometrics: Morphometrics
        let morphometricsJSON: String
        let runtimeFamily: String
        let runtimeCapabilitiesJSON: String
        let specimenManifestJSON: String
    }

    private struct PersistedStrictSpecimenContract {
        let manifest: SpecimenManifest
        let runtimeFamily: String
        let runtimeCapabilitiesJSON: String
        let specimenManifestJSON: String
    }

    private func mergeStrictSpecimenManifest(
        _ manifest: SpecimenManifest,
        replayOverlay: SpecimenManifest?
    ) -> SpecimenManifest {
        guard let replayOverlay else {
            return manifest
        }

        var merged = manifest
        let overlayAddsReplay = replayOverlay.replay != nil
            || replayOverlay.runtimeCapabilities.contains(LeniaArtifactCapability.replay.rawValue)
        if overlayAddsReplay {
            merged.runtimeFamily = replayOverlay.runtimeFamily
            merged.runtimeCapabilities = Array(
                Set(merged.runtimeCapabilities).union(replayOverlay.runtimeCapabilities)
            ).sorted()
            merged.replay = replayOverlay.replay ?? merged.replay
        }
        if merged.researchMetadata == nil {
            merged.researchMetadata = replayOverlay.researchMetadata
        }
        return merged
    }

    private func persistedStrictSpecimenContract(
        baseManifest: SpecimenManifest,
        overlayManifest: SpecimenManifest?
    ) throws -> PersistedStrictSpecimenContract {
        let manifest = mergeStrictSpecimenManifest(baseManifest, replayOverlay: overlayManifest)
        return PersistedStrictSpecimenContract(
            manifest: manifest,
            runtimeFamily: manifest.runtimeFamily,
            runtimeCapabilitiesJSON: try jsonString(manifest.runtimeCapabilities),
            specimenManifestJSON: try jsonString(manifest)
        )
    }

    private func persistedLibrarySpecimenContract(
        _ contract: LibrarySpecimenContract
    ) throws -> PersistedLibrarySpecimenContract {
        PersistedLibrarySpecimenContract(
            sourceMode: contract.sourceMode,
            morphometrics: contract.morphometrics,
            morphometricsJSON: try jsonString(contract.morphometrics),
            runtimeFamily: contract.manifest.runtimeFamily,
            runtimeCapabilitiesJSON: try jsonString(contract.manifest.runtimeCapabilities),
            specimenManifestJSON: try jsonString(contract.manifest)
        )
    }

    private func librarySpecimenContract(
        creature: SavedCreature,
        campaignID: String?,
        runID: String,
        recordedAt: Date,
        configHash: String?,
        sourceMode: String?,
        sourceAlgorithm: String?,
        researchMetadata: [String: AnyCodable]?,
        taxonomy: SpecimenTaxonomyRecord? = nil,
        traitLabels: [String]? = nil,
        morphometrics: Morphometrics? = nil
    ) -> LibrarySpecimenContract {
        let normalizedSourceMode = normalizedSpecimenSourceMode(sourceMode)
        let resolvedMorphometrics = morphometrics ?? Morphometrics.from(metrics: creature.metrics, activity: nil)
        return LibrarySpecimenContract(
            sourceMode: normalizedSourceMode,
            morphometrics: resolvedMorphometrics,
            manifest: buildLibrarySpecimenManifest(
                creature: creature,
                campaignID: campaignID,
                runID: runID,
                recordedAt: recordedAt,
                configHash: configHash,
                sourceMode: normalizedSourceMode,
                sourceAlgorithm: sourceAlgorithm,
                researchMetadata: researchMetadata,
                taxonomy: taxonomy,
                traitLabels: traitLabels,
                morphometrics: resolvedMorphometrics
            )
        )
    }

    private func specimenProvenance(
        sourceKind: String,
        runKey: String,
        campaignId: String?,
        sourceMode: String?,
        sourceAlgorithm: String?,
        configHash: String?,
        initialConditionFamily: String?,
        sourceRef: String?,
        sourcePath: String?,
        fingerprintPath: String? = nil,
        activityPath: String? = nil
    ) -> SpecimenProvenance {
        SpecimenProvenance(
            version: 1,
            sourceKind: sourceKind,
            runKey: runKey,
            campaignId: campaignId,
            sourceMode: sourceMode,
            sourceAlgorithm: sourceAlgorithm,
            configHash: configHash,
            initialConditionFamily: initialConditionFamily,
            sourceRef: sourceRef,
            sourcePath: sourcePath,
            fingerprintPath: fingerprintPath,
            activityPath: activityPath
        )
    }

    private func upsertLibraryLikeSpecimen(
        creature: SavedCreature,
        specimenID: String,
        creatureID: String,
        runId: String,
        campaignId: String?,
        sourceKind: String,
        provenanceKind: String,
        recordedAt: String,
        sourceMode: String?,
        sourceAlgorithm: String?,
        configHash: String?,
        researchMetadata: [String: AnyCodable]?,
        manifestRecordedAt: Date,
        sourcePath: String?,
        activityPath: String? = nil,
        descriptorBundle: MorphospaceDescriptorBundle? = nil,
        seed: Int? = nil,
        initSeed: Int? = nil,
        initialConditionFamily: String? = nil,
        contract: LibrarySpecimenContract? = nil
    ) throws -> String? {
        guard let descriptorBundle = descriptorBundle ?? creature.descriptorBundle else {
            return nil
        }

        let initialConditionFamily = initialConditionFamily
            ?? nonEmpty(creature.initialConditionFamily)
            ?? morphospaceInitialConditionFamily(creature.initialCondition)
        let contract = contract ?? librarySpecimenContract(
            creature: creature,
            campaignID: campaignId,
            runID: runId,
            recordedAt: manifestRecordedAt,
            configHash: configHash,
            sourceMode: sourceMode,
            sourceAlgorithm: sourceAlgorithm,
            researchMetadata: researchMetadata
        )
        let provenance = specimenProvenance(
            sourceKind: provenanceKind,
            runKey: runId,
            campaignId: campaignId,
            sourceMode: contract.sourceMode,
            sourceAlgorithm: sourceAlgorithm,
            configHash: configHash,
            initialConditionFamily: initialConditionFamily,
            sourceRef: "creature:\(creatureID)",
            sourcePath: sourcePath,
            activityPath: activityPath
        )
        let strictContract = try persistedStrictSpecimenContract(
            baseManifest: buildSpecimenManifest(
                specimenID: specimenID,
                creatureID: creatureID,
                runID: runId,
                campaignID: campaignId,
                sourceKind: sourceKind,
                sourceMode: contract.sourceMode,
                sourceAlgorithm: sourceAlgorithm,
                configHash: configHash,
                recordedAt: manifestRecordedAt,
                initialConditionFamily: initialConditionFamily,
                taxonomy: contract.manifest.taxonomy,
                traitLabels: contract.manifest.traitLabels,
                snapshots: SpecimenSnapshotRecord(
                    genotype: creature.genotype,
                    initialCondition: creature.initialCondition,
                    metrics: creature.metrics,
                    descriptorBundle: descriptorBundle,
                    morphometrics: contract.morphometrics
                ),
                researchMetadata: contract.manifest.researchMetadata ?? researchMetadata
            ),
            overlayManifest: contract.manifest
        )

        try upsertSpecimen(try descriptorSpecimenRecord(
            id: specimenID,
            resultId: nil,
            creatureId: creatureID,
            runId: runId,
            campaignId: campaignId,
            sourceKind: sourceKind,
            recordedAt: recordedAt,
            seed: seed ?? creature.initialCondition.seed,
            initSeed: initSeed ?? creature.initialCondition.seed,
            sourceMode: contract.sourceMode,
            sourceAlgorithm: sourceAlgorithm,
            configHash: configHash,
            initialConditionFamily: initialConditionFamily,
            descriptorBundle: descriptorBundle,
            activityPath: activityPath,
            provenance: provenance,
            manifest: strictContract.manifest
        ))
        return specimenID
    }

    private func descriptorSpecimenRecord(
        id: String,
        resultId: String?,
        creatureId: String?,
        runId: String,
        campaignId: String?,
        sourceKind: String,
        recordedAt: String?,
        seed: Int,
        initSeed: Int,
        sourceMode: String?,
        sourceAlgorithm: String?,
        configHash: String?,
        initialConditionFamily: String?,
        descriptorBundle: MorphospaceDescriptorBundle,
        activityPath: String? = nil,
        fingerprintPath: String? = nil,
        provenance: SpecimenProvenance,
        manifest: SpecimenManifest
    ) throws -> SpecimenRecord {
        SpecimenRecord(
            id: id,
            resultId: resultId,
            creatureId: creatureId,
            runId: runId,
            campaignId: campaignId,
            sourceKind: sourceKind,
            recordedAt: recordedAt,
            seed: seed,
            initSeed: initSeed,
            sourceMode: sourceMode,
            sourceAlgorithm: sourceAlgorithm,
            configHash: configHash,
            initialConditionFamily: initialConditionFamily,
            descriptorVersion: descriptorBundle.descriptorVersion,
            symmetryPolicy: descriptorBundle.symmetryPolicy,
            genotypeDescriptorJSON: try jsonString(descriptorBundle.genotype),
            terminalDescriptorJSON: try jsonString(descriptorBundle.terminal),
            trajectoryDescriptorJSON: try jsonString(descriptorBundle.trajectory),
            activityPath: activityPath,
            fingerprintPath: fingerprintPath,
            provenanceJSON: try jsonString(provenance),
            runtimeFamily: manifest.runtimeFamily,
            runtimeCapabilitiesJSON: try jsonString(manifest.runtimeCapabilities),
            specimenManifestJSON: try jsonString(manifest)
        )
    }

    private func deleteRedundantReplayLibrarySpecimens(
        runKey: String,
        campaignId: String?,
        initSeed: Int
    ) throws {
        let sql: String
        if campaignId == nil {
            sql = """
                DELETE FROM specimens
                WHERE run_id = ?
                  AND campaign_id IS NULL
                  AND source_kind = 'library'
                  AND source_mode = 'replay'
                  AND init_seed = ?
            """
        } else {
            sql = """
                DELETE FROM specimens
                WHERE run_id = ?
                  AND campaign_id = ?
                  AND source_kind = 'library'
                  AND source_mode = 'replay'
                  AND init_seed = ?
            """
        }
        let stmt = try db.prepare(sql)
        defer { sqlite3_finalize(stmt) }
        db.bindText(stmt, index: 1, value: runKey)
        if let campaignId {
            db.bindText(stmt, index: 2, value: campaignId)
            db.bindInt(stmt, index: 3, value: initSeed)
        } else {
            db.bindInt(stmt, index: 2, value: initSeed)
        }
        try db.step(stmt)
    }

    private func updateSpecimensFromActivitySummary(
        runKey: String,
        campaignId: String?,
        seed: Int,
        summary: ActivitySummary,
        runDir: URL,
        sourcePath: URL
    ) throws {
        let selectSQL = campaignId == nil
            ? """
                SELECT id, trajectory_descriptor_json
                FROM specimens
                WHERE run_id = ? AND init_seed = ? AND campaign_id IS NULL
            """
            : """
                SELECT id, trajectory_descriptor_json
                FROM specimens
                WHERE run_id = ? AND init_seed = ? AND campaign_id = ?
            """
        let select = try db.prepare(selectSQL)
        defer { sqlite3_finalize(select) }
        db.bindText(select, index: 1, value: runKey)
        db.bindInt(select, index: 2, value: seed)
        if let campaignId {
            db.bindText(select, index: 3, value: campaignId)
        }

        let update = try db.prepare("""
            UPDATE specimens
            SET trajectory_descriptor_json = COALESCE(?, trajectory_descriptor_json),
                activity_path = COALESCE(?, activity_path)
            WHERE id = ?
        """)
        defer { sqlite3_finalize(update) }
        let decoder = JSONDecoder()

        while sqlite3_step(select) == SQLITE_ROW {
            guard let idC = sqlite3_column_text(select, 0) else { continue }
            let id = String(cString: idC)
            let existingTrajectory: MorphospaceTrajectoryDescriptor?
            if let trajectoryC = sqlite3_column_text(select, 1) {
                existingTrajectory = try? decoder.decode(
                    MorphospaceTrajectoryDescriptor.self,
                    from: Data(String(cString: trajectoryC).utf8)
                )
            } else {
                existingTrajectory = nil
            }

            let updatedTrajectory = mergeTrajectoryDescriptor(existing: existingTrajectory, summary: summary)
            let trajectoryJSON = try jsonString(updatedTrajectory)
            let activityPath = relativePath(sourcePath.path, base: runDir)

            sqlite3_reset(update)
            sqlite3_clear_bindings(update)
            db.bindText(update, index: 1, value: trajectoryJSON)
            db.bindText(update, index: 2, value: activityPath)
            db.bindText(update, index: 3, value: id)
            try db.step(update)
        }
    }

    private func mergeTrajectoryDescriptor(
        existing: MorphospaceTrajectoryDescriptor?,
        summary: ActivitySummary
    ) -> MorphospaceTrajectoryDescriptor? {
        guard let existing else {
            return nil
        }
        let speciesSeries = summary.speciesCount.map(Float.init)
        return MorphospaceTrajectoryDescriptor(
            version: existing.version,
            recordInterval: existing.recordInterval,
            warmupSteps: existing.warmupSteps,
            sampleCount: existing.sampleCount,
            pathLength: existing.pathLength,
            displacement: existing.displacement,
            pathTortuosity: existing.pathTortuosity,
            movementEfficiency: existing.movementEfficiency,
            speedMean: existing.speedMean,
            centerVelocity: existing.centerVelocity,
            velocityX: existing.velocityX,
            velocityY: existing.velocityY,
            headingRad: existing.headingRad,
            headingCircularVariance: existing.headingCircularVariance,
            accumulatedTurnAbs: existing.accumulatedTurnAbs,
            survivalSteps: existing.survivalSteps,
            activityEacMean: mean(summary.eac) ?? existing.activityEacMean,
            activityEanMean: mean(summary.ean) ?? existing.activityEanMean,
            activityDiversityMean: mean(summary.diversity) ?? existing.activityDiversityMean,
            activitySpeciesMean: mean(speciesSeries) ?? existing.activitySpeciesMean,
            activitySpeciesMax: summary.speciesCount.max() ?? existing.activitySpeciesMax,
            activitySpeciesStd: std(speciesSeries) ?? existing.activitySpeciesStd,
            activityDiversityStd: std(summary.diversity) ?? existing.activityDiversityStd,
            activityEacMax: summary.eac.max() ?? existing.activityEacMax,
            activityEanMax: summary.ean.max() ?? existing.activityEanMax,
            componentSeriesMean: existing.componentSeriesMean,
            componentSeriesStd: existing.componentSeriesStd,
            componentSeriesMax: existing.componentSeriesMax
        )
    }

    private func upsertSpecimen(_ specimen: SpecimenRecord) throws {
        let stmt = try db.prepare("""
            INSERT INTO specimens (
                id, result_id, creature_id, run_id, campaign_id, source_kind, recorded_at, seed, init_seed,
                source_mode, source_algorithm, config_hash, initial_condition_family, descriptor_version,
                symmetry_policy, genotype_descriptor_json, terminal_descriptor_json, trajectory_descriptor_json,
                activity_path, fingerprint_path, provenance_json,
                runtime_family, runtime_capabilities_json, specimen_manifest_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                result_id = COALESCE(excluded.result_id, specimens.result_id),
                creature_id = COALESCE(excluded.creature_id, specimens.creature_id),
                run_id = excluded.run_id,
                campaign_id = excluded.campaign_id,
                source_kind = excluded.source_kind,
                recorded_at = COALESCE(excluded.recorded_at, specimens.recorded_at),
                seed = COALESCE(excluded.seed, specimens.seed),
                init_seed = COALESCE(excluded.init_seed, specimens.init_seed),
                source_mode = COALESCE(excluded.source_mode, specimens.source_mode),
                source_algorithm = COALESCE(excluded.source_algorithm, specimens.source_algorithm),
                config_hash = COALESCE(excluded.config_hash, specimens.config_hash),
                initial_condition_family = COALESCE(excluded.initial_condition_family, specimens.initial_condition_family),
                descriptor_version = excluded.descriptor_version,
                symmetry_policy = excluded.symmetry_policy,
                genotype_descriptor_json = excluded.genotype_descriptor_json,
                terminal_descriptor_json = excluded.terminal_descriptor_json,
                trajectory_descriptor_json = COALESCE(excluded.trajectory_descriptor_json, specimens.trajectory_descriptor_json),
                activity_path = COALESCE(excluded.activity_path, specimens.activity_path),
                fingerprint_path = COALESCE(excluded.fingerprint_path, specimens.fingerprint_path),
                provenance_json = COALESCE(excluded.provenance_json, specimens.provenance_json),
                runtime_family = COALESCE(excluded.runtime_family, specimens.runtime_family),
                runtime_capabilities_json = COALESCE(excluded.runtime_capabilities_json, specimens.runtime_capabilities_json),
                specimen_manifest_json = COALESCE(excluded.specimen_manifest_json, specimens.specimen_manifest_json)
        """)
        defer { sqlite3_finalize(stmt) }

        db.bindText(stmt, index: 1, value: specimen.id)
        db.bindText(stmt, index: 2, value: specimen.resultId)
        db.bindText(stmt, index: 3, value: specimen.creatureId)
        db.bindText(stmt, index: 4, value: specimen.runId)
        db.bindText(stmt, index: 5, value: specimen.campaignId)
        db.bindText(stmt, index: 6, value: specimen.sourceKind)
        db.bindText(stmt, index: 7, value: specimen.recordedAt)
        db.bindInt(stmt, index: 8, value: specimen.seed)
        db.bindInt(stmt, index: 9, value: specimen.initSeed)
        db.bindText(stmt, index: 10, value: specimen.sourceMode)
        db.bindText(stmt, index: 11, value: specimen.sourceAlgorithm)
        db.bindText(stmt, index: 12, value: specimen.configHash)
        db.bindText(stmt, index: 13, value: specimen.initialConditionFamily)
        db.bindInt(stmt, index: 14, value: specimen.descriptorVersion)
        db.bindText(stmt, index: 15, value: specimen.symmetryPolicy)
        db.bindText(stmt, index: 16, value: specimen.genotypeDescriptorJSON)
        db.bindText(stmt, index: 17, value: specimen.terminalDescriptorJSON)
        db.bindText(stmt, index: 18, value: specimen.trajectoryDescriptorJSON)
        db.bindText(stmt, index: 19, value: specimen.activityPath)
        db.bindText(stmt, index: 20, value: specimen.fingerprintPath)
        db.bindText(stmt, index: 21, value: specimen.provenanceJSON)
        db.bindText(stmt, index: 22, value: specimen.runtimeFamily)
        db.bindText(stmt, index: 23, value: specimen.runtimeCapabilitiesJSON)
        db.bindText(stmt, index: 24, value: specimen.specimenManifestJSON)
        try db.step(stmt)
    }

    private func readJSONLLines(path: URL) throws -> ([String], Int64, FileAttributes) {
        let fileHandle = try FileHandle(forReadingFrom: path)
        defer { try? fileHandle.close() }

        let attrs = try FileManager.default.attributesOfItem(atPath: path.path)
        let size = (attrs[.size] as? NSNumber)?.int64Value ?? 0
        let mtime = (attrs[.modificationDate] as? Date)?.timeIntervalSince1970 ?? 0

        let state = try ingestState(path: path)
        var offset = state?.offset ?? 0
        if let state, size < offset || (state.size == size && state.mtime != mtime) {
            offset = 0
        }

        try fileHandle.seek(toOffset: UInt64(offset))
        let data = fileHandle.readDataToEndOfFile()

        guard let content = String(data: data, encoding: .utf8) else {
            throw SQLiteIndexError.invalidUTF8(path.path)
        }

        var completeContent = content
        var unreadBytes = 0
        if let lastScalar = content.unicodeScalars.last,
           !CharacterSet.newlines.contains(lastScalar) {
            if let lastNewline = content.range(of: "\n", options: .backwards)
                ?? content.range(of: "\r", options: .backwards) {
                let remainder = String(content[lastNewline.upperBound...])
                unreadBytes = remainder.lengthOfBytes(using: .utf8)
                completeContent = String(content[..<lastNewline.upperBound])
            } else {
                unreadBytes = content.lengthOfBytes(using: .utf8)
                completeContent = ""
            }
        }

        let newOffset = offset + Int64(data.count - unreadBytes)
        let lines = completeContent.split(whereSeparator: \.isNewline).map(String.init)
        return (lines, newOffset, attrs)
    }

    private func ingestState(path: URL) throws -> IngestState? {
        let stmt = try db.prepare("SELECT offset, size, mtime FROM ingest_state WHERE file_path = ?")
        defer { sqlite3_finalize(stmt) }
        db.bindText(stmt, index: 1, value: path.path)
        if sqlite3_step(stmt) == SQLITE_ROW {
            let offset = sqlite3_column_int64(stmt, 0)
            let size = sqlite3_column_int64(stmt, 1)
            let mtime = sqlite3_column_double(stmt, 2)
            return IngestState(offset: offset, size: size, mtime: mtime)
        }
        return nil
    }

    private func updateIngestState(path: URL, offset: Int64, attrs: FileAttributes) throws {
        let size = (attrs[.size] as? NSNumber)?.int64Value ?? 0
        let mtime = (attrs[.modificationDate] as? Date)?.timeIntervalSince1970 ?? 0

        let stmt = try db.prepare("INSERT OR REPLACE INTO ingest_state (file_path, offset, size, mtime) VALUES (?, ?, ?, ?)")
        defer { sqlite3_finalize(stmt) }
        db.bindText(stmt, index: 1, value: path.path)
        sqlite3_bind_int64(stmt, 2, offset)
        sqlite3_bind_int64(stmt, 3, size)
        sqlite3_bind_double(stmt, 4, mtime)
        try db.step(stmt)
    }

    private func updateRunId(table: String, newRunId: String, oldRunId: String) throws {
        let stmt = try db.prepare("UPDATE \(table) SET run_id = ? WHERE run_id = ?")
        defer { sqlite3_finalize(stmt) }
        db.bindText(stmt, index: 1, value: newRunId)
        db.bindText(stmt, index: 2, value: oldRunId)
        try db.step(stmt)
    }

    private func inferRunDirMetadata(_ runDir: String) -> (outputRoot: String?, hostId: String?, runDirRelative: String?) {
        let expanded = (runDir as NSString).expandingTildeInPath
        let url = URL(fileURLWithPath: expanded).standardizedFileURL
        let parts = url.pathComponents

        if let hostsIndex = parts.lastIndex(of: "hosts"),
           hostsIndex + 2 < parts.count,
           parts[hostsIndex + 2] == "runs" {
            let hostId = parts[hostsIndex + 1]
            let rootParts = Array(parts[0..<hostsIndex])
            let outputRoot = rootParts.isEmpty ? nil : NSString.path(withComponents: rootParts)
            let runDirRelative = NSString.path(withComponents: Array(parts[hostsIndex...]))
            return (outputRoot, hostId, runDirRelative)
        }

        let relParts = (runDir as NSString).pathComponents
        if relParts.first == "hosts", relParts.count > 2 {
            let hostId = relParts[1]
            return (nil, hostId, runDir)
        }

        return (nil, nil, runDir)
    }

    private func relativePath(_ path: String, base: URL) -> String {
        let expanded = (path as NSString).expandingTildeInPath
        let fileURL = URL(fileURLWithPath: expanded).standardizedFileURL
        let baseURL = base.standardizedFileURL
        let basePath = baseURL.path.hasSuffix("/") ? baseURL.path : "\(baseURL.path)/"
        guard fileURL.path.hasPrefix(basePath) else {
            return path
        }
        return String(fileURL.path.dropFirst(basePath.count))
    }

    private func jsonString<T: Encodable>(_ value: T?) throws -> String? {
        guard let value = value else { return nil }
        let data = try encoder.encode(value)
        guard let string = String(data: data, encoding: .utf8) else {
            throw SQLiteIndexError.invalidUTF8("encoded JSON")
        }
        return string
    }

    private func jsonString<T: Encodable>(_ value: T) throws -> String {
        let data = try encoder.encode(value)
        guard let string = String(data: data, encoding: .utf8) else {
            throw SQLiteIndexError.invalidUTF8("encoded JSON")
        }
        return string
    }

    private func columnText(_ stmt: OpaquePointer, index: Int32) -> String? {
        guard let text = sqlite3_column_text(stmt, index) else { return nil }
        return String(cString: text)
    }
}

private func mean(_ values: [Float]) -> Float? {
    guard !values.isEmpty else { return nil }
    return values.reduce(0, +) / Float(values.count)
}

private func nonEmpty(_ value: String?) -> String? {
    guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else {
        return nil
    }
    return value
}

private func std(_ values: [Float]) -> Float? {
    guard !values.isEmpty else { return nil }
    if values.count == 1 { return 0 }
    guard let mean = mean(values) else { return nil }
    var sumSq: Float = 0
    for value in values {
        let delta = value - mean
        sumSq += delta * delta
    }
    return sqrt(sumSq / Float(values.count))
}

private typealias FileAttributes = [FileAttributeKey: Any]

private struct SpecimenRecord {
    let id: String
    let resultId: String?
    let creatureId: String?
    let runId: String
    let campaignId: String?
    let sourceKind: String
    let recordedAt: String?
    let seed: Int
    let initSeed: Int
    let sourceMode: String?
    let sourceAlgorithm: String?
    let configHash: String?
    let initialConditionFamily: String?
    let descriptorVersion: Int
    let symmetryPolicy: String
    let genotypeDescriptorJSON: String
    let terminalDescriptorJSON: String
    let trajectoryDescriptorJSON: String?
    let activityPath: String?
    let fingerprintPath: String?
    let provenanceJSON: String?
    let runtimeFamily: String?
    let runtimeCapabilitiesJSON: String?
    let specimenManifestJSON: String?
}

private struct SpecimenProvenance: Codable {
    let version: Int
    let sourceKind: String
    let runKey: String
    let campaignId: String?
    let sourceMode: String?
    let sourceAlgorithm: String?
    let configHash: String?
    let initialConditionFamily: String?
    let sourceRef: String?
    let sourcePath: String?
    let fingerprintPath: String?
    let activityPath: String?
}

private struct CanonicalCreatureGap {
    let creatureID: String
    let runID: String
    let campaignID: String?
    let recordedAt: String
    let configHash: String?
    let sourceMode: String?
    let sourceAlgorithm: String?
    let researchMetadata: [String: AnyCodable]?
    let creature: SavedCreature
}

private struct CanonicalRunArtifactRecord {
    let runDir: String
    let outputRoot: String?
}

private struct CanonicalFlowSweepManifest: Decodable {
    let variants: [CanonicalFlowSweepVariantEntry]
}

private struct CanonicalFlowSweepVariantEntry: Decodable {
    let id: String
    let config: String
    let search: String
}

private struct CanonicalFlowSweepVariant {
    let manifestURL: URL
    let baseConfigURL: URL
    let searchConfigURL: URL
}

private struct CanonicalizationPendingReplay {
    let gap: CanonicalCreatureGap
    let resolvedInput: ReplayResolvedInput
    let backfillRunID: String
    let artifactDirectory: URL
}

private struct CanonicalizationBackfillProduct {
    let gap: CanonicalCreatureGap
    let resolvedInput: ReplayResolvedInput
    let execution: ReplayExecutionOutcome
    let artifactDirectory: URL
}

private final class CanonicalizationChunkState: @unchecked Sendable {
    private let lock = NSLock()
    private var recordedError: Error?
    private var recordedResults: [CanonicalizationBackfillProduct?]

    init(resultCount: Int) {
        recordedResults = Array(repeating: nil, count: resultCount)
    }

    var shouldSkip: Bool {
        lock.lock()
        defer { lock.unlock() }
        return recordedError != nil
    }

    func record(_ result: CanonicalizationBackfillProduct, at index: Int) {
        lock.lock()
        recordedResults[index] = result
        lock.unlock()
    }

    func record(error: Error) {
        lock.lock()
        if recordedError == nil {
            recordedError = error
        }
        lock.unlock()
    }

    var firstError: Error? {
        lock.lock()
        defer { lock.unlock() }
        return recordedError
    }

    var results: [CanonicalizationBackfillProduct] {
        lock.lock()
        defer { lock.unlock() }
        return recordedResults.compactMap { $0 }
    }
}

private struct IngestState {
    let offset: Int64
    let size: Int64
    let mtime: Double
}

private struct ExportRecord: Decodable {
    let creatureId: UUID
    let name: String
    let ownerId: String
    let runId: String
    let campaignId: String?
    let exportDir: String
    let bundleKind: LeniaArtifactBundleKind
    let baseConfigPath: String?
    let searchConfigPath: String?
    let payloadPath: String?
    let exportedAt: Date
    let reason: String
    let score: Float?
    let filtersPassed: Bool?
    let runtimeFamily: String?
    let runtimeCapabilities: [String]?
    let specimenManifest: SpecimenManifest?

    enum CodingKeys: String, CodingKey {
        case creatureId = "creature_id"
        case name
        case ownerId = "owner_id"
        case runId = "run_id"
        case campaignId = "campaign_id"
        case exportDir = "export_dir"
        case bundleKind = "bundle_kind"
        case baseConfigPath = "base_config_path"
        case searchConfigPath = "search_config_path"
        case payloadPath = "payload_path"
        case exportedAt = "exported_at"
        case reason
        case score
        case filtersPassed = "filters_passed"
        case runtimeFamily = "runtime_family"
        case runtimeCapabilities = "runtime_capabilities"
        case specimenManifest = "specimen_manifest"
    }

    enum AltCodingKeys: String, CodingKey {
        case creatureId
        case name
        case ownerId
        case runId
        case campaignId
        case exportDir
        case bundleKind
        case baseConfigPath
        case searchConfigPath
        case payloadPath
        case exportedAt
        case reason
        case score
        case filtersPassed
        case runtimeFamily
        case runtimeCapabilities
        case specimenManifest
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let alt = try decoder.container(keyedBy: AltCodingKeys.self)

        creatureId = try container.decodeIfPresent(UUID.self, forKey: .creatureId)
            ?? alt.decode(UUID.self, forKey: .creatureId)
        name = try container.decodeIfPresent(String.self, forKey: .name)
            ?? alt.decode(String.self, forKey: .name)
        ownerId = try container.decodeIfPresent(String.self, forKey: .ownerId)
            ?? alt.decode(String.self, forKey: .ownerId)
        runId = try container.decodeIfPresent(String.self, forKey: .runId)
            ?? alt.decode(String.self, forKey: .runId)
        campaignId = try container.decodeIfPresent(String.self, forKey: .campaignId)
            ?? alt.decodeIfPresent(String.self, forKey: .campaignId)
        exportDir = try container.decodeIfPresent(String.self, forKey: .exportDir)
            ?? alt.decode(String.self, forKey: .exportDir)
        bundleKind = try container.decodeIfPresent(LeniaArtifactBundleKind.self, forKey: .bundleKind)
            ?? alt.decode(LeniaArtifactBundleKind.self, forKey: .bundleKind)
        baseConfigPath = try container.decodeIfPresent(String.self, forKey: .baseConfigPath)
            ?? alt.decodeIfPresent(String.self, forKey: .baseConfigPath)
        searchConfigPath = try container.decodeIfPresent(String.self, forKey: .searchConfigPath)
            ?? alt.decodeIfPresent(String.self, forKey: .searchConfigPath)
        payloadPath = try container.decodeIfPresent(String.self, forKey: .payloadPath)
            ?? alt.decodeIfPresent(String.self, forKey: .payloadPath)
        exportedAt = try container.decodeIfPresent(Date.self, forKey: .exportedAt)
            ?? alt.decode(Date.self, forKey: .exportedAt)
        reason = try container.decodeIfPresent(String.self, forKey: .reason)
            ?? alt.decode(String.self, forKey: .reason)
        score = try container.decodeIfPresent(Float.self, forKey: .score)
            ?? alt.decodeIfPresent(Float.self, forKey: .score)
        filtersPassed = try container.decodeIfPresent(Bool.self, forKey: .filtersPassed)
            ?? alt.decodeIfPresent(Bool.self, forKey: .filtersPassed)
        runtimeFamily = try container.decodeIfPresent(String.self, forKey: .runtimeFamily)
            ?? alt.decodeIfPresent(String.self, forKey: .runtimeFamily)
        runtimeCapabilities = try container.decodeIfPresent([String].self, forKey: .runtimeCapabilities)
            ?? alt.decodeIfPresent([String].self, forKey: .runtimeCapabilities)
        specimenManifest = try container.decodeIfPresent(SpecimenManifest.self, forKey: .specimenManifest)
            ?? alt.decodeIfPresent(SpecimenManifest.self, forKey: .specimenManifest)
    }
}
