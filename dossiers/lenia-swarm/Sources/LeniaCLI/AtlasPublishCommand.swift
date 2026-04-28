import ArgumentParser
import Foundation
import LeniaCore
import SQLite3

struct AtlasPublishCommand: ParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "atlas",
        abstract: "Publish a read-optimized Lenia atlas catalog and replay packs"
    )

    @Option(name: [.customLong("db"), .customLong("db-path")], help: "SQLite compendium DB path")
    var dbPath: String

    @Option(name: .shortAndLong, help: "Output directory for atlas catalog and media")
    var output: String = "site/atlas/public/published"

    @Option(name: .long, help: "Limit number of creatures to publish")
    var limit: Int?

    @Flag(name: .long, help: "Include unstable creatures in the published atlas")
    var includeUnstable: Bool = false

    @Flag(name: .long, help: "Allow publish even when taxonomy is still pending")
    var allowPendingTaxonomy: Bool = false

    @Option(name: .long, help: "Approximate number of replay frames per creature")
    var frameBudget: Int = 48

    @Option(name: .long, help: "Playback FPS for replay packs")
    var fps: Int = 18

    @Flag(name: .long, help: "Skip media rendering and publish metadata only")
    var skipMedia: Bool = false

    func run() throws {
        let resolvedDb = (dbPath as NSString).expandingTildeInPath
        let resolvedOutput = try resolveArtifactPath(output, dossier: dossierName)
        let outputURL = URL(fileURLWithPath: resolvedOutput, isDirectory: true)
        try FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)

        _ = try SQLiteIndexer(path: resolvedDb, rebuild: false)
        let db = try SQLiteDB(path: resolvedDb)

        let schemaVersion = try db.scalarInt("SELECT schema_version FROM compendium_meta LIMIT 1")
        if schemaVersion != compendiumSchemaVersion {
            throw ValidationError("Compendium schema version \(schemaVersion) does not match expected \(compendiumSchemaVersion).")
        }

        let rows = try loadRows(db: db)
        if rows.isEmpty {
            throw ValidationError("No creatures available for atlas publish.")
        }

        if !allowPendingTaxonomy {
            let pending = rows.filter { $0.familyId == nil || $0.genusId == nil || $0.speciesId == nil }.count
            if pending > 0 {
                throw ValidationError("Atlas publish requires taxonomy. \(pending) creatures still have pending taxonomy IDs.")
            }
        }

        let mediaRoot = outputURL.appendingPathComponent("media", isDirectory: true)
        try FileManager.default.createDirectory(at: mediaRoot, withIntermediateDirectories: true)

        var creatures: [AtlasCreature] = []
        creatures.reserveCapacity(rows.count)

        var runCounts: [String: Int] = [:]
        let createdAt = ISO8601DateFormatter().string(from: Date())

        for row in rows {
            runCounts[row.runId, default: 0] += 1
            let rendered = skipMedia ? nil : try renderMedia(row: row, mediaRoot: mediaRoot)
            creatures.append(makeCreatureRecord(row: row, rendered: rendered))
        }

        let taxa = buildTaxa(from: creatures)
        let runs = buildRuns(rows: rows, runCounts: runCounts)

        let catalog = AtlasCatalog(
            revision: CatalogRevision(
                id: revisionId(),
                createdAt: createdAt,
                sourceDb: resolvedDb,
                creatureCount: creatures.count,
                taxonCount: taxa.count
            ),
            taxa: taxa,
            creatures: creatures,
            runs: runs
        )

        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let catalogURL = outputURL.appendingPathComponent("catalog.json")
        try encoder.encode(catalog).write(to: catalogURL)
        let sqliteURL = outputURL.appendingPathComponent("catalog.sqlite")
        try writeSQLiteCatalog(catalog: catalog, url: sqliteURL)

        print("Atlas publish: creatures=\(creatures.count) taxa=\(taxa.count) runs=\(runs.count) output=\(catalogURL.path) sqlite=\(sqliteURL.path)")
    }

    private func loadRows(db: SQLiteDB) throws -> [AtlasSourceRow] {
        var sql = """
        SELECT
            c.id,
            c.name,
            c.run_id,
            c.campaign_id,
            c.recorded_at,
            c.score,
            c.is_stable,
            c.mass_mean,
            c.gyration,
            c.center_velocity,
            c.velocity_x,
            c.velocity_y,
            c.heading_rad,
            c.taxonomy_family_id,
            c.taxonomy_genus_id,
            c.taxonomy_species_id,
            c.taxonomy_confidence,
            c.taxonomy_method,
            c.taxonomy_version,
            c.morphometrics_json,
            c.genotype_json,
            c.initial_condition_json,
            c.metrics_json,
            r.run_name,
            r.host_id,
            r.output_root,
            r.run_dir,
            (SELECT base_config_path FROM exports e WHERE e.creature_id = c.id ORDER BY exported_at DESC LIMIT 1) AS base_config_path,
            (SELECT search_config_path FROM exports e WHERE e.creature_id = c.id ORDER BY exported_at DESC LIMIT 1) AS search_config_path
        FROM creatures c
        LEFT JOIN runs r ON r.run_id = c.run_id
        """
        if !includeUnstable {
            sql += " WHERE c.is_stable = 1"
        }
        sql += " ORDER BY COALESCE(c.score, -1.0e30) DESC, c.id ASC"
        if let limit {
            sql += " LIMIT \(limit)"
        }

        let stmt = try db.prepare(sql)
        defer { sqlite3_finalize(stmt) }
        let decoder = JSONDecoder()
        var rows: [AtlasSourceRow] = []
        while sqlite3_step(stmt) == SQLITE_ROW {
            guard let idC = sqlite3_column_text(stmt, 0),
                  let nameC = sqlite3_column_text(stmt, 1),
                  let runIdC = sqlite3_column_text(stmt, 2),
                  let recordedAtC = sqlite3_column_text(stmt, 4),
                  let genotypeC = sqlite3_column_text(stmt, 20),
                  let initialConditionC = sqlite3_column_text(stmt, 21),
                  let metricsC = sqlite3_column_text(stmt, 22) else {
                continue
            }

            let morphometrics: Morphometrics?
            if let morphC = sqlite3_column_text(stmt, 19) {
                morphometrics = try decoder.decode(Morphometrics.self, from: Data(String(cString: morphC).utf8))
            } else {
                morphometrics = nil
            }

            let id = String(cString: idC)
            let name = String(cString: nameC)
            let runId = String(cString: runIdC)
            let genotype = try decoder.decode(KernelParams.self, from: Data(String(cString: genotypeC).utf8))
            let initialCondition = try decoder.decode(InitConfig.self, from: Data(String(cString: initialConditionC).utf8))
            let metrics = try decoder.decode(SimulationMetrics.self, from: Data(String(cString: metricsC).utf8))

            let row = AtlasSourceRow(
                id: id,
                name: name,
                runId: runId,
                campaignId: columnText(stmt, index: 3),
                recordedAt: String(cString: recordedAtC),
                score: columnDouble(stmt, index: 5).map(Float.init),
                isStable: sqlite3_column_int(stmt, 6) != 0,
                massMean: columnDouble(stmt, index: 7).map(Float.init),
                gyration: columnDouble(stmt, index: 8).map(Float.init),
                centerVelocity: columnDouble(stmt, index: 9).map(Float.init),
                velocityX: columnDouble(stmt, index: 10).map(Float.init) ?? 0,
                velocityY: columnDouble(stmt, index: 11).map(Float.init) ?? 0,
                headingRad: columnDouble(stmt, index: 12).map(Float.init) ?? 0,
                familyId: columnText(stmt, index: 13),
                genusId: columnText(stmt, index: 14),
                speciesId: columnText(stmt, index: 15),
                taxonomyConfidence: columnDouble(stmt, index: 16).map(Float.init),
                taxonomyMethod: columnText(stmt, index: 17),
                taxonomyVersion: sqlite3_column_type(stmt, 18) == SQLITE_NULL ? nil : Int(sqlite3_column_int(stmt, 18)),
                morphometrics: morphometrics,
                genotype: genotype,
                initialCondition: initialCondition,
                metrics: metrics,
                runName: columnText(stmt, index: 23) ?? runId,
                hostId: columnText(stmt, index: 24),
                outputRoot: columnText(stmt, index: 25),
                runDir: columnText(stmt, index: 26),
                baseConfigPath: columnText(stmt, index: 27),
                searchConfigPath: columnText(stmt, index: 28)
            )
            rows.append(row)
        }
        return rows
    }

    private func makeCreatureRecord(row: AtlasSourceRow, rendered: AtlasRenderedMedia?) -> AtlasCreature {
        let slug = slugify(row.name).isEmpty ? row.id.lowercased() : "\(slugify(row.name))-\(row.id.prefix(8).lowercased())"
        return AtlasCreature(
            id: row.id,
            slug: slug,
            name: row.name,
            runId: row.runId,
            campaignId: row.campaignId,
            recordedAt: row.recordedAt,
            score: row.score,
            isStable: row.isStable,
            familyId: row.familyId,
            genusId: row.genusId,
            speciesId: row.speciesId,
            metrics: AtlasMetricSnapshot(
                massMean: row.metrics.massMean,
                gyration: row.metrics.gyration,
                centerVelocity: row.metrics.centerVelocity,
                velocityX: row.metrics.velocityX,
                velocityY: row.metrics.velocityY,
                headingRad: row.metrics.headingRad,
                complexityMean: row.metrics.complexityMean,
                pathLength: row.metrics.pathLength,
                displacement: row.metrics.displacement
            ),
            morphometrics: row.morphometrics,
            telemetry: rendered?.telemetry ?? syntheticTelemetrySummary(metrics: row.metrics),
            media: rendered?.media,
            provenance: AtlasProvenance(
                runName: row.runName,
                hostId: row.hostId,
                outputRoot: row.outputRoot,
                runDir: row.runDir,
                baseConfigPath: row.baseConfigPath,
                searchConfigPath: row.searchConfigPath
            )
        )
    }

    private func buildRuns(rows: [AtlasSourceRow], runCounts: [String: Int]) -> [AtlasRun] {
        var seen: Set<String> = []
        var runs: [AtlasRun] = []
        for row in rows {
            if seen.contains(row.runId) { continue }
            seen.insert(row.runId)
            runs.append(AtlasRun(
                id: row.runId,
                name: row.runName,
                hostId: row.hostId,
                creatureCount: runCounts[row.runId] ?? 0,
                slug: slugify(row.runName.isEmpty ? row.runId : row.runName),
                outputRoot: row.outputRoot,
                runDir: row.runDir
            ))
        }
        return runs.sorted { $0.id < $1.id }
    }

    private func buildTaxa(from creatures: [AtlasCreature]) -> [AtlasTaxon] {
        var taxaById: [String: AtlasTaxonBuilder] = [:]

        for creature in creatures {
            if let familyId = creature.familyId {
                taxaById[familyId, default: AtlasTaxonBuilder(
                    id: familyId,
                    rank: "family",
                    slug: slugify(familyId),
                    label: prettifyTaxonLabel(familyId),
                    parentId: nil
                )].consume(creature: creature)
            }
            if let genusId = creature.genusId {
                taxaById[genusId, default: AtlasTaxonBuilder(
                    id: genusId,
                    rank: "genus",
                    slug: slugify(genusId),
                    label: prettifyTaxonLabel(genusId),
                    parentId: creature.familyId
                )].consume(creature: creature)
            }
            if let speciesId = creature.speciesId {
                taxaById[speciesId, default: AtlasTaxonBuilder(
                    id: speciesId,
                    rank: "species",
                    slug: slugify(speciesId),
                    label: prettifyTaxonLabel(speciesId),
                    parentId: creature.genusId
                )].consume(creature: creature)
            }
        }

        return taxaById.values
            .map { $0.build() }
            .sorted { lhs, rhs in
                if lhs.rank == rhs.rank { return lhs.label < rhs.label }
                return lhs.rank < rhs.rank
            }
    }

    private func renderMedia(row: AtlasSourceRow, mediaRoot: URL) throws -> AtlasRenderedMedia {
        let creatureDir = mediaRoot
            .appendingPathComponent("creatures", isDirectory: true)
            .appendingPathComponent(row.id.lowercased(), isDirectory: true)
        try FileManager.default.createDirectory(at: creatureDir, withIntermediateDirectories: true)

        let baseConfigURL = try resolveConfigPath(row: row, preferred: row.baseConfigPath, fallbackName: "config.json")
        let searchConfigURL = try resolveConfigPath(row: row, preferred: row.searchConfigPath, fallbackName: "search.json")

        let baseConfigData = try Data(contentsOf: baseConfigURL)
        let baseConfig = try JSONDecoder().decode(LeniaBaseConfig.self, from: baseConfigData)
        let resolvedBackend = try resolveReplaySearchBackend(baseConfig: baseConfig)
        let replayBaseConfigData = try baseConfigDataBySettingBackend(baseConfigData, backend: resolvedBackend)
        let parsedSearch = try JSONDecoder().decode(ParsedSearchConfig.self, from: Data(contentsOf: searchConfigURL))
        let runtimeConfig = try loadRuntimeConfig(from: replayBaseConfigData, overrides: buildOverrides(row: row))
        let selected = try captureReplayFrames(
            runtimeConfig: runtimeConfig,
            seed: row.initialCondition.seed,
            parsedSearch: parsedSearch,
            frameBudget: frameBudget
        )
        return try writeAtlasRenderedMedia(
            creatureId: row.id,
            genotype: row.genotype,
            runtimeConfig: runtimeConfig,
            selectedFrames: selected,
            mediaRoot: mediaRoot,
            creatureDir: creatureDir,
            fps: fps
        )
    }

    func writeAtlasRenderedMedia(
        creatureId: String,
        genotype: KernelParams,
        runtimeConfig: LeniaRuntimeConfig,
        selectedFrames: [Data],
        mediaRoot: URL,
        creatureDir: URL,
        fps: Int
    ) throws -> AtlasRenderedMedia {
        try writeRenderedMediaAssets(
            creatureId: creatureId,
            genotype: genotype,
            runtimeConfig: runtimeConfig,
            selectedFrames: selectedFrames,
            assetBaseURL: mediaRoot.deletingLastPathComponent(),
            creatureDir: creatureDir,
            fps: fps,
            includeReplay: true
        )
    }

    private func resolveConfigPath(row: AtlasSourceRow, preferred: String?, fallbackName: String) throws -> URL {
        let fm = FileManager.default
        if let resolved = resolveRunPath(outputRoot: row.outputRoot, runDir: row.runDir, path: preferred) {
            let url = URL(fileURLWithPath: resolved)
            var isDirectory: ObjCBool = false
            if fm.fileExists(atPath: url.path, isDirectory: &isDirectory), !isDirectory.boolValue {
                return url
            }
        }

        guard let runRoot = resolveRunPath(outputRoot: row.outputRoot, runDir: row.runDir, path: nil) else {
            throw ValidationError("Could not resolve run root for creature \(row.id).")
        }
        let url = URL(fileURLWithPath: runRoot, isDirectory: true).appendingPathComponent(fallbackName)
        var isDirectory: ObjCBool = false
        guard fm.fileExists(atPath: url.path, isDirectory: &isDirectory), !isDirectory.boolValue else {
            throw ValidationError("Missing \(fallbackName) for creature \(row.id) at \(url.path).")
        }
        return url
    }

    private func buildOverrides(row: AtlasSourceRow) throws -> [String: Any] {
        var overrides: [String: Any] = [:]
        overrides["params.mode"] = "explicit"
        overrides["params.seed"] = row.initialCondition.seed
        overrides["params.r"] = row.genotype.r.map(Double.init)
        overrides["params.b"] = row.genotype.b.map { $0.map(Double.init) }
        overrides["params.w"] = row.genotype.w.map { $0.map(Double.init) }
        overrides["params.a"] = row.genotype.a.map { $0.map(Double.init) }
        overrides["params.m"] = row.genotype.m.map(Double.init)
        overrides["params.s"] = row.genotype.s.map(Double.init)
        overrides["params.h"] = row.genotype.h.map(Double.init)
        overrides["params.R"] = Double(row.genotype.R)
        overrides["init.seed"] = row.initialCondition.seed
        overrides["init.patches"] = try jsonObject(row.initialCondition.patches)
        overrides["init.a_uniform"] = try jsonObject(row.initialCondition.a_uniform)
        if let pUniform = row.initialCondition.p_uniform {
            overrides["init.p_uniform"] = try jsonObject(pUniform)
        } else {
            overrides["init.p_uniform"] = NSNull()
        }
        return overrides
    }

    private func jsonObject<T: Encodable>(_ value: T) throws -> Any {
        let data = try JSONEncoder().encode(value)
        return try JSONSerialization.jsonObject(with: data)
    }

    private func syntheticTelemetrySummary(metrics: SimulationMetrics) -> AtlasTelemetrySummary {
        let centerX = clamp(0.5 + cos(metrics.headingRad) * 0.08, lower: 0.12, upper: 0.88)
        let centerY = clamp(0.5 - sin(metrics.headingRad) * 0.08, lower: 0.12, upper: 0.88)
        let trail = [3, 2, 1].map { step in
            AtlasPoint(
                x: clamp(centerX - metrics.velocityX * 10.0 * Float(step), lower: 0.08, upper: 0.92),
                y: clamp(centerY + metrics.velocityY * 10.0 * Float(step), lower: 0.08, upper: 0.92)
            )
        }
        return AtlasTelemetrySummary(
            centroid: AtlasPoint(x: centerX, y: centerY),
            trail: trail,
            vx: metrics.velocityX,
            vy: metrics.velocityY,
            speed: max(metrics.centerVelocity, sqrt(metrics.velocityX * metrics.velocityX + metrics.velocityY * metrics.velocityY)),
            headingRad: metrics.headingRad
        )
    }

    private func resolveRunPath(outputRoot: String?, runDir: String?, path: String?) -> String? {
        if let path, path.hasPrefix("/") || path.hasPrefix("~") {
            return (path as NSString).expandingTildeInPath
        }

        if let path, let runPath = resolveRunPath(outputRoot: outputRoot, runDir: runDir, path: nil) {
            return URL(fileURLWithPath: runPath, isDirectory: true)
                .appendingPathComponent(path)
                .path
        }

        guard let runDir else { return nil }
        if runDir.hasPrefix("/") || runDir.hasPrefix("~") {
            return (runDir as NSString).expandingTildeInPath
        }

        guard let outputRoot else { return nil }
        let root = (outputRoot as NSString).expandingTildeInPath
        return URL(fileURLWithPath: root, isDirectory: true)
            .appendingPathComponent(runDir)
            .path
    }

    private func writeSQLiteCatalog(catalog: AtlasCatalog, url: URL) throws {
        let fm = FileManager.default
        if fm.fileExists(atPath: url.path) {
            try fm.removeItem(at: url)
        }

        let db = try SQLiteDB(path: url.path)
        try db.exec("PRAGMA foreign_keys = ON")
        try db.exec("""
        CREATE TABLE catalog_revision (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            source_db TEXT NOT NULL,
            creature_count INTEGER NOT NULL,
            taxon_count INTEGER NOT NULL
        );
        CREATE TABLE taxa (
            id TEXT PRIMARY KEY,
            rank TEXT NOT NULL,
            slug TEXT NOT NULL,
            label TEXT NOT NULL,
            parent_id TEXT,
            creature_count INTEGER NOT NULL,
            hero_creature_id TEXT,
            average_score REAL
        );
        CREATE TABLE runs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            host_id TEXT,
            creature_count INTEGER NOT NULL,
            slug TEXT NOT NULL,
            output_root TEXT,
            run_dir TEXT
        );
        CREATE TABLE creatures (
            id TEXT PRIMARY KEY,
            slug TEXT NOT NULL,
            name TEXT NOT NULL,
            run_id TEXT NOT NULL,
            campaign_id TEXT,
            recorded_at TEXT NOT NULL,
            score REAL,
            is_stable INTEGER NOT NULL,
            family_id TEXT,
            genus_id TEXT,
            species_id TEXT,
            metrics_json TEXT NOT NULL,
            morphometrics_json TEXT,
            telemetry_json TEXT NOT NULL,
            media_json TEXT,
            provenance_json TEXT NOT NULL
        );
        CREATE INDEX idx_taxa_rank_slug ON taxa(rank, slug);
        CREATE INDEX idx_runs_slug ON runs(slug);
        CREATE INDEX idx_creatures_slug ON creatures(slug);
        CREATE INDEX idx_creatures_run_id ON creatures(run_id);
        CREATE INDEX idx_creatures_family_id ON creatures(family_id);
        CREATE INDEX idx_creatures_genus_id ON creatures(genus_id);
        CREATE INDEX idx_creatures_species_id ON creatures(species_id);
        """)

        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        try db.withImmediateTransaction {
            let revisionStmt = try db.prepare("""
                INSERT INTO catalog_revision (id, created_at, source_db, creature_count, taxon_count)
                VALUES (?, ?, ?, ?, ?)
            """)
            defer { sqlite3_finalize(revisionStmt) }
            db.bindText(revisionStmt, index: 1, value: catalog.revision.id)
            db.bindText(revisionStmt, index: 2, value: catalog.revision.createdAt)
            db.bindText(revisionStmt, index: 3, value: catalog.revision.sourceDb)
            db.bindInt(revisionStmt, index: 4, value: catalog.revision.creatureCount)
            db.bindInt(revisionStmt, index: 5, value: catalog.revision.taxonCount)
            try db.step(revisionStmt)

            let taxonStmt = try db.prepare("""
                INSERT INTO taxa (id, rank, slug, label, parent_id, creature_count, hero_creature_id, average_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """)
            defer { sqlite3_finalize(taxonStmt) }
            for taxon in catalog.taxa {
                sqlite3_reset(taxonStmt)
                sqlite3_clear_bindings(taxonStmt)
                db.bindText(taxonStmt, index: 1, value: taxon.id)
                db.bindText(taxonStmt, index: 2, value: taxon.rank)
                db.bindText(taxonStmt, index: 3, value: taxon.slug)
                db.bindText(taxonStmt, index: 4, value: taxon.label)
                db.bindText(taxonStmt, index: 5, value: taxon.parentId)
                db.bindInt(taxonStmt, index: 6, value: taxon.creatureCount)
                db.bindText(taxonStmt, index: 7, value: taxon.heroCreatureId)
                db.bindDouble(taxonStmt, index: 8, value: taxon.averageScore.map(Double.init))
                try db.step(taxonStmt)
            }

            let runStmt = try db.prepare("""
                INSERT INTO runs (id, name, host_id, creature_count, slug, output_root, run_dir)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """)
            defer { sqlite3_finalize(runStmt) }
            for run in catalog.runs {
                sqlite3_reset(runStmt)
                sqlite3_clear_bindings(runStmt)
                db.bindText(runStmt, index: 1, value: run.id)
                db.bindText(runStmt, index: 2, value: run.name)
                db.bindText(runStmt, index: 3, value: run.hostId)
                db.bindInt(runStmt, index: 4, value: run.creatureCount)
                db.bindText(runStmt, index: 5, value: run.slug)
                db.bindText(runStmt, index: 6, value: run.outputRoot)
                db.bindText(runStmt, index: 7, value: run.runDir)
                try db.step(runStmt)
            }

            let creatureStmt = try db.prepare("""
                INSERT INTO creatures (
                    id, slug, name, run_id, campaign_id, recorded_at, score, is_stable,
                    family_id, genus_id, species_id, metrics_json, morphometrics_json,
                    telemetry_json, media_json, provenance_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """)
            defer { sqlite3_finalize(creatureStmt) }
            for creature in catalog.creatures {
                sqlite3_reset(creatureStmt)
                sqlite3_clear_bindings(creatureStmt)
                db.bindText(creatureStmt, index: 1, value: creature.id)
                db.bindText(creatureStmt, index: 2, value: creature.slug)
                db.bindText(creatureStmt, index: 3, value: creature.name)
                db.bindText(creatureStmt, index: 4, value: creature.runId)
                db.bindText(creatureStmt, index: 5, value: creature.campaignId)
                db.bindText(creatureStmt, index: 6, value: creature.recordedAt)
                db.bindDouble(creatureStmt, index: 7, value: creature.score.map(Double.init))
                db.bindBool(creatureStmt, index: 8, value: creature.isStable)
                db.bindText(creatureStmt, index: 9, value: creature.familyId)
                db.bindText(creatureStmt, index: 10, value: creature.genusId)
                db.bindText(creatureStmt, index: 11, value: creature.speciesId)
                db.bindText(creatureStmt, index: 12, value: try encodeJSONString(creature.metrics, encoder: encoder))
                db.bindText(creatureStmt, index: 13, value: try encodeOptionalJSONString(creature.morphometrics, encoder: encoder))
                db.bindText(creatureStmt, index: 14, value: try encodeJSONString(creature.telemetry, encoder: encoder))
                db.bindText(creatureStmt, index: 15, value: try encodeOptionalJSONString(creature.media, encoder: encoder))
                db.bindText(creatureStmt, index: 16, value: try encodeJSONString(creature.provenance, encoder: encoder))
                try db.step(creatureStmt)
            }
        }
    }

    private func encodeJSONString<T: Encodable>(_ value: T, encoder: JSONEncoder) throws -> String {
        let data = try encoder.encode(value)
        guard let string = String(data: data, encoding: .utf8) else {
            throw SQLiteIndexError.invalidUTF8("atlas-catalog")
        }
        return string
    }

    private func encodeOptionalJSONString<T: Encodable>(_ value: T?, encoder: JSONEncoder) throws -> String? {
        guard let value else { return nil }
        return try encodeJSONString(value, encoder: encoder)
    }

    private func slugify(_ raw: String) -> String {
        let lower = raw.lowercased()
        let mapped = lower.map { char -> Character in
            if char.isLetter || char.isNumber { return char }
            return "-"
        }
        let compact = String(mapped)
            .split(separator: "-", omittingEmptySubsequences: true)
            .joined(separator: "-")
        return compact
    }

    private func prettifyTaxonLabel(_ id: String) -> String {
        let core = id
            .replacingOccurrences(of: "fam-", with: "")
            .replacingOccurrences(of: "speed-", with: "")
            .replacingOccurrences(of: "path-", with: "")
            .replacingOccurrences(of: "cx-", with: "")
            .replacingOccurrences(of: "mass-", with: "")
            .replacingOccurrences(of: ".", with: " ")
            .replacingOccurrences(of: "-", with: " ")
        return core
            .split(separator: " ")
            .map { $0.prefix(1).uppercased() + $0.dropFirst() }
            .joined(separator: " ")
    }

    private func revisionId() -> String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .iso8601)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        return "atlas-\(formatter.string(from: Date()))"
    }
}

private struct AtlasSourceRow {
    let id: String
    let name: String
    let runId: String
    let campaignId: String?
    let recordedAt: String
    let score: Float?
    let isStable: Bool
    let massMean: Float?
    let gyration: Float?
    let centerVelocity: Float?
    let velocityX: Float
    let velocityY: Float
    let headingRad: Float
    let familyId: String?
    let genusId: String?
    let speciesId: String?
    let taxonomyConfidence: Float?
    let taxonomyMethod: String?
    let taxonomyVersion: Int?
    let morphometrics: Morphometrics?
    let genotype: KernelParams
    let initialCondition: InitConfig
    let metrics: SimulationMetrics
    let runName: String
    let hostId: String?
    let outputRoot: String?
    let runDir: String?
    let baseConfigPath: String?
    let searchConfigPath: String?
}

private struct AtlasCatalog: Codable {
    let revision: CatalogRevision
    let taxa: [AtlasTaxon]
    let creatures: [AtlasCreature]
    let runs: [AtlasRun]
}

private struct CatalogRevision: Codable {
    let id: String
    let createdAt: String
    let sourceDb: String
    let creatureCount: Int
    let taxonCount: Int
}

private struct AtlasTaxon: Codable {
    let id: String
    let rank: String
    let slug: String
    let label: String
    let parentId: String?
    let creatureCount: Int
    let heroCreatureId: String?
    let averageScore: Float?
}

private struct AtlasCreature: Codable {
    let id: String
    let slug: String
    let name: String
    let runId: String
    let campaignId: String?
    let recordedAt: String
    let score: Float?
    let isStable: Bool
    let familyId: String?
    let genusId: String?
    let speciesId: String?
    let metrics: AtlasMetricSnapshot
    let morphometrics: Morphometrics?
    let telemetry: AtlasTelemetrySummary
    let media: AtlasMedia?
    let provenance: AtlasProvenance
}

private struct AtlasMetricSnapshot: Codable {
    let massMean: Float
    let gyration: Float
    let centerVelocity: Float
    let velocityX: Float
    let velocityY: Float
    let headingRad: Float
    let complexityMean: Float?
    let pathLength: Float
    let displacement: Float
}

private struct AtlasProvenance: Codable {
    let runName: String
    let hostId: String?
    let outputRoot: String?
    let runDir: String?
    let baseConfigPath: String?
    let searchConfigPath: String?
}

private struct AtlasRun: Codable {
    let id: String
    let name: String
    let hostId: String?
    let creatureCount: Int
    let slug: String
    let outputRoot: String?
    let runDir: String?
}

struct AtlasRenderedMedia {
    let media: AtlasMedia
    let telemetry: AtlasTelemetrySummary
}

struct AtlasPoint: Codable {
    let x: Float
    let y: Float
}

struct AtlasTelemetrySummary: Codable {
    let centroid: AtlasPoint
    let trail: [AtlasPoint]
    let vx: Float
    let vy: Float
    let speed: Float
    let headingRad: Float
}

struct AtlasAnatomyMedia: Codable {
    let fieldPath: String
    let deltaPath: String
    let neighborPath: String
    let kernelPath: String
}

struct AtlasMedia: Codable {
    let posterPath: String
    let replayPath: String?
    let width: Int
    let height: Int
    let anatomy: AtlasAnatomyMedia
}

struct AtlasReplay: Codable {
    let width: Int
    let height: Int
    let frameCount: Int
    let fps: Int
    let framesPath: String
    let centroids: [[Float]]
    let velocities: [[Float]]
    let palette: String
}

private struct AtlasTaxonBuilder {
    let id: String
    let rank: String
    let slug: String
    let label: String
    let parentId: String?
    private(set) var creatureCount: Int = 0
    private(set) var heroCreatureId: String?
    private(set) var heroScore: Float = -.greatestFiniteMagnitude
    private(set) var scoreSum: Float = 0
    private(set) var scoreCount: Int = 0

    mutating func consume(creature: AtlasCreature) {
        creatureCount += 1
        if let score = creature.score {
            scoreSum += score
            scoreCount += 1
            if score > heroScore {
                heroScore = score
                heroCreatureId = creature.id
            }
        } else if heroCreatureId == nil {
            heroCreatureId = creature.id
        }
    }

    func build() -> AtlasTaxon {
        AtlasTaxon(
            id: id,
            rank: rank,
            slug: slug,
            label: label,
            parentId: parentId,
            creatureCount: creatureCount,
            heroCreatureId: heroCreatureId,
            averageScore: scoreCount > 0 ? scoreSum / Float(scoreCount) : nil
        )
    }
}

private func columnDouble(_ stmt: OpaquePointer, index: Int) -> Double? {
    let idx = Int32(index)
    if sqlite3_column_type(stmt, idx) == SQLITE_NULL {
        return nil
    }
    return sqlite3_column_double(stmt, idx)
}

private func columnText(_ stmt: OpaquePointer, index: Int) -> String? {
    let idx = Int32(index)
    guard sqlite3_column_type(stmt, idx) != SQLITE_NULL,
          let text = sqlite3_column_text(stmt, idx) else {
        return nil
    }
    return String(cString: text)
}

private func clamp(_ value: Float, lower: Float, upper: Float) -> Float {
    max(lower, min(upper, value))
}
