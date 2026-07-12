import ArgumentParser
import Foundation
import LeniaArchive
import LeniaCore
import SQLite3

private typealias RunSnapshot = (base: LeniaBaseConfig, search: ParsedSearchConfig)
private typealias PublishedArtifacts = (rendered: AtlasRenderedMedia?, artifactSource: String)

struct CompendiumPublishCommand: ParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "compendium",
        abstract: "Publish a static Lenia compendium release from the indexed SQLite database"
    )

    @Option(name: [.customLong("db"), .customLong("db-path")], help: "SQLite compendium DB path")
    var dbPath: String

    @Option(name: .long, help: "Output directory for manifest and published releases")
    var output: String = "dossiers/lenia-swarm/artifacts/compendium"

    @Option(name: .long, help: "Release identifier written into the manifest and output paths")
    var releaseId: String

    @Option(name: .long, help: "Human-readable release label")
    var label: String?

    @Option(name: .long, help: "Limit the number of published creatures")
    var limit: Int?

    @Option(name: .long, help: "Limit publish to creatures whose run_id begins with this prefix (repeatable)")
    var runPrefix: [String] = []

    @Option(name: .long, help: "Publish only creatures whose initial condition has at most this many init patches")
    var maxPatches: Int?

    @Option(name: .long, help: "Publish only creatures with occupancy_mean at or below this threshold")
    var maxOccupancy: Double?

    @Option(name: .long, help: "Publish only creatures with gyration at or below this threshold")
    var maxGyration: Double?

    @Option(name: .long, help: "Publish only creatures with center_velocity at or above this threshold")
    var minCenterVelocity: Double?

    @Option(name: .long, help: "Publish only creatures with displacement/path_length at or above this threshold")
    var minTranslationRatio: Double?

    @Flag(name: .long, help: "Publish only stable creatures")
    var stableOnly: Bool = false

    @Option(name: .long, help: "Approximate number of capture frames used to derive stage media")
    var frameBudget: Int = 36

    @Option(name: .long, help: "Playback FPS for optional replay payloads")
    var fps: Int = 12

    @Flag(name: .long, help: "Skip rendered stage media and publish only metadata plus replay configs")
    var skipMedia: Bool = false

    @Option(name: .long, help: "Render stage media only for the first N published creatures (all when omitted)")
    var mediaLimit: Int?

    @Flag(name: .long, help: "Write replay.json and frames.bin alongside stage media")
    var includeReplay: Bool = false

    func run() throws {
        try validateInputs()

        let resolvedDb = (dbPath as NSString).expandingTildeInPath
        let normalizedReleaseId = try validateReleaseId(releaseId)
        let publicSourceDb = publicSourceDbLabel(resolvedDb)
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
            throw ValidationError("No creatures available for compendium publish.")
        }

        let runCount = Set(rows.map(\.runId)).count
        let releaseRootURL = outputURL
            .appendingPathComponent("releases", isDirectory: true)
            .appendingPathComponent(normalizedReleaseId, isDirectory: true)

        if FileManager.default.fileExists(atPath: releaseRootURL.path) {
            try FileManager.default.removeItem(at: releaseRootURL)
        }
        try FileManager.default.createDirectory(
            at: releaseRootURL.appendingPathComponent("details", isDirectory: true),
            withIntermediateDirectories: true
        )
        try FileManager.default.createDirectory(
            at: releaseRootURL.appendingPathComponent("runs", isDirectory: true),
            withIntermediateDirectories: true
        )

        let standardRunSnapshots = try loadRunSnapshots(for: rows.filter { !$0.isQD2024 })
        let publishedAtString = formatISO8601(Date())
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]

        var entries: [PublishedIndexEntry] = []
        entries.reserveCapacity(rows.count)

        for (index, row) in rows.enumerated() {
            let creatureDirRelative = "releases/\(normalizedReleaseId)/runs/\(row.runId)/\(row.creature.id.uuidString.lowercased())"
            let creatureDirURL = outputURL.appendingPathComponent(creatureDirRelative, isDirectory: true)
            try FileManager.default.createDirectory(at: creatureDirURL, withIntermediateDirectories: true)

            let baseRelativePath = "\(creatureDirRelative)/base.json"
            let searchRelativePath = "\(creatureDirRelative)/search.json"
            let shouldRenderMedia = !skipMedia && (mediaLimit.map { index < $0 } ?? true)
            let publication = try publishCreatureArtifacts(
                row: row,
                standardRunSnapshots: standardRunSnapshots,
                outputURL: outputURL,
                creatureDirURL: creatureDirURL,
                baseRelativePath: baseRelativePath,
                searchRelativePath: searchRelativePath,
                shouldRenderMedia: shouldRenderMedia,
                encoder: encoder
            )

            let detailRelativePath = "releases/\(normalizedReleaseId)/details/\(detailFileName(for: row.creature.id.uuidString))"
            let detail = PublishedDetail(
                creature: PublishedCreaturePayload(
                    id: row.creature.id.uuidString,
                    name: row.creature.name,
                    timestamp: row.recordedAt,
                    ownerId: sanitizeOwnerId(row.creature.ownerId),
                    genotype: row.creature.genotype,
                    initialCondition: row.creature.initialCondition,
                    metrics: row.creature.metrics,
                    sweep: row.creature.sweep,
                    score: row.creature.score,
                    scoreWeights: row.creature.scoreWeights,
                    configHash: row.creature.configHash
                ),
                runId: row.runId,
                runName: row.runName,
                campaignId: row.campaignId,
                recordedAt: row.recordedAt,
                publishedAt: publishedAtString,
                sourceDb: publicSourceDb,
                artifactSource: publication.artifactSource,
                reason: nil,
                filtersPassed: nil,
                telemetry: publication.rendered?.telemetry,
                media: publication.rendered?.media
            )
            try encoder.encode(detail).write(to: outputURL.appendingPathComponent(detailRelativePath))

            entries.append(
                PublishedIndexEntry(
                    id: row.creature.id.uuidString,
                    name: row.creature.name,
                    detail: detailRelativePath,
                    baseConfig: baseRelativePath,
                    searchConfig: searchRelativePath,
                    score: row.creature.score,
                    seed: row.creature.initialCondition.seed,
                    isStable: row.isStable,
                    runId: row.runId,
                    runName: row.runName,
                    campaignId: row.campaignId,
                    recordedAt: row.recordedAt,
                    metrics: PublishedMetricSummary(metrics: row.creature.metrics),
                    telemetry: publication.rendered?.telemetry,
                    media: publication.rendered?.media
                )
            )
        }

        let indexRelativePath = "releases/\(normalizedReleaseId)/index.json"
        try encoder.encode(entries).write(to: outputURL.appendingPathComponent(indexRelativePath))

        var manifest = try loadManifest(at: outputURL.appendingPathComponent("manifest.json"))
        manifest.defaultRelease = normalizedReleaseId
        manifest.upsert(
            PublishedManifestRelease(
                id: normalizedReleaseId,
                label: normalized(label) ?? "Lenia compendium | \(rows.count) creatures | \(runCount) runs",
                index: indexRelativePath,
                creatureCount: rows.count,
                runCount: runCount,
                publishedAt: publishedAtString,
                firstRecordedAt: rows.map(\.recordedAt).min(),
                lastRecordedAt: rows.map(\.recordedAt).max(),
                sourceDb: publicSourceDb
            )
        )
        let manifestURL = outputURL.appendingPathComponent("manifest.json")
        try encoder.encode(manifest).write(to: manifestURL)

        print(
            "Compendium publish: creatures=\(rows.count) runs=\(runCount) release=\(normalizedReleaseId) output=\(manifestURL.path)"
        )
    }

    private func validateInputs() throws {
        if frameBudget <= 0 {
            throw ValidationError("--frame-budget must be greater than zero.")
        }
        if fps <= 0 {
            throw ValidationError("--fps must be greater than zero.")
        }
        if let mediaLimit, mediaLimit < 0 {
            throw ValidationError("--media-limit must be zero or greater.")
        }
        if let limit, limit <= 0 {
            throw ValidationError("--limit must be greater than zero.")
        }
        if let maxPatches, maxPatches <= 0 {
            throw ValidationError("--max-patches must be greater than zero.")
        }
        if let maxOccupancy, maxOccupancy < 0 {
            throw ValidationError("--max-occupancy must be zero or greater.")
        }
        if let maxGyration, maxGyration < 0 {
            throw ValidationError("--max-gyration must be zero or greater.")
        }
        if let minCenterVelocity, minCenterVelocity < 0 {
            throw ValidationError("--min-center-velocity must be zero or greater.")
        }
        if let minTranslationRatio, minTranslationRatio < 0 {
            throw ValidationError("--min-translation-ratio must be zero or greater.")
        }
    }

    private func loadRows(db: SQLiteDB) throws -> [CompendiumPublishRow] {
        var sql = """
        SELECT
            c.id,
            c.name,
            c.owner_id,
            c.run_id,
            c.campaign_id,
            c.recorded_at,
            c.is_stable,
            c.score,
            c.score_weights_json,
            c.genotype_json,
            c.initial_condition_json,
            c.sweep_json,
            c.metrics_json,
            c.config_hash,
            c.source_mode,
            c.source_algorithm,
            c.research_metadata_json,
            s.specimen_manifest_json,
            r.run_name,
            r.output_root,
            r.run_dir
        FROM creatures c
        LEFT JOIN specimens s ON s.id = c.canonical_specimen_id
        LEFT JOIN runs r ON r.run_id = c.run_id
        """
        if stableOnly {
            sql += " WHERE c.is_stable = 1"
        }
        sql += " ORDER BY COALESCE(c.score, -1.0e30) DESC, c.recorded_at DESC, c.id ASC"

        let stmt = try db.prepare(sql)
        defer { sqlite3_finalize(stmt) }

        let decoder = JSONDecoder()
        var rows: [CompendiumPublishRow] = []
        rows.reserveCapacity(limit ?? 256)

        while sqlite3_step(stmt) == SQLITE_ROW {
            guard let idText = columnText(stmt, index: 0),
                  let creatureId = UUID(uuidString: idText),
                  let name = columnText(stmt, index: 1),
                  let ownerId = columnText(stmt, index: 2),
                  let runId = columnText(stmt, index: 3),
                  let recordedAt = columnText(stmt, index: 5),
                  let genotypeJSON = columnText(stmt, index: 9),
                  let initialConditionJSON = columnText(stmt, index: 10),
                  let metricsJSON = columnText(stmt, index: 12) else {
                continue
            }
            let manifest = try decodeOptionalJSONString(
                columnText(stmt, index: 17),
                as: SpecimenManifest.self,
                decoder: decoder
            )
            let fallbackResearchMetadata = try decodeOptionalJSONString(
                columnText(stmt, index: 16),
                as: [String: AnyCodable].self,
                decoder: decoder
            )
            let projection = resolveSpecimenProjection(
                id: creatureId,
                name: name,
                ownerId: ownerId,
                manifest: manifest,
                fallbackGenotype: try decoder.decode(KernelParams.self, from: Data(genotypeJSON.utf8)),
                fallbackInitialCondition: try decoder.decode(InitConfig.self, from: Data(initialConditionJSON.utf8)),
                fallbackMetrics: try decoder.decode(SimulationMetrics.self, from: Data(metricsJSON.utf8)),
                sweep: try decodeOptionalJSONString(columnText(stmt, index: 11), as: [String: Double].self, decoder: decoder),
                score: columnDouble(stmt, index: 7).map(Float.init),
                scoreWeights: try decodeOptionalJSONString(columnText(stmt, index: 8), as: [String: Float].self, decoder: decoder),
                fallbackConfigHash: columnText(stmt, index: 13),
                fallbackSourceMode: columnText(stmt, index: 14),
                fallbackSourceAlgorithm: columnText(stmt, index: 15),
                fallbackResearchMetadata: fallbackResearchMetadata
            )

            rows.append(
                CompendiumPublishRow(
                    creature: projection.creature,
                    runId: runId,
                    runName: columnText(stmt, index: 18) ?? runId,
                    campaignId: columnText(stmt, index: 4),
                    recordedAt: recordedAt,
                    isStable: sqlite3_column_int(stmt, 6) != 0,
                    outputRoot: columnText(stmt, index: 19),
                    runDir: columnText(stmt, index: 20),
                    sourceMode: projection.sourceMode,
                    sourceAlgorithm: projection.sourceAlgorithm,
                    researchMetadata: projection.researchMetadata
                )
            )
        }

        let filtered = rows.filter { matchesPublishFilters(for: $0, runPrefixes: runPrefix.compactMap(normalized)) }
        if filtered.isEmpty {
            throw ValidationError("No creatures matched the requested publish filters.")
        }
        return limit.map { Array(filtered.prefix($0)) } ?? filtered
    }

    private func matchesPublishFilters(
        for row: CompendiumPublishRow,
        runPrefixes: [String]
    ) -> Bool {
        if !runPrefixes.isEmpty && !runPrefixes.contains(where: { row.runId.hasPrefix($0) }) {
            return false
        }

        let creature = row.creature
        let metrics = creature.metrics

        if let maxPatches, creature.initialCondition.patches.count > maxPatches {
            return false
        }
        if let maxOccupancy, Double(metrics.occupancyMean) > maxOccupancy {
            return false
        }
        if let maxGyration, Double(metrics.gyration) > maxGyration {
            return false
        }
        if let minCenterVelocity, Double(metrics.centerVelocity) < minCenterVelocity {
            return false
        }
        if let minTranslationRatio, Double(publishedTranslationRatio(for: metrics)) < minTranslationRatio {
            return false
        }
        return true
    }

    private func publishCreatureArtifacts(
        row: CompendiumPublishRow,
        standardRunSnapshots: [String: RunSnapshot],
        outputURL: URL,
        creatureDirURL: URL,
        baseRelativePath: String,
        searchRelativePath: String,
        shouldRenderMedia: Bool,
        encoder: JSONEncoder
    ) throws -> PublishedArtifacts {
        if row.isQD2024 {
            return try publishQD2024Artifacts(
                row: row,
                outputURL: outputURL,
                creatureDirURL: creatureDirURL,
                baseRelativePath: baseRelativePath,
                searchRelativePath: searchRelativePath,
                shouldRenderMedia: shouldRenderMedia,
                encoder: encoder
            )
        }

        guard let snapshot = standardRunSnapshots[row.runId] else {
            throw ValidationError("Missing run snapshot for \(row.runId).")
        }

        let replayBaseConfig = try buildReplayBaseConfig(
            baseConfig: snapshot.base,
            searchConfig: snapshot.search,
            creature: row.creature
        )
        let replaySearchConfig = buildReplaySearchConfig(from: snapshot.search)
        try encoder.encode(replayBaseConfig).write(to: outputURL.appendingPathComponent(baseRelativePath))
        try encoder.encode(replaySearchConfig).write(to: outputURL.appendingPathComponent(searchRelativePath))

        if !shouldRenderMedia {
            return (rendered: nil, artifactSource: "computed_replay_configs")
        }

        return (
            rendered: try renderMedia(
                creature: row.creature,
                baseConfig: replayBaseConfig,
                searchConfig: replaySearchConfig,
                outputURL: outputURL,
                creatureDirURL: creatureDirURL
            ),
            artifactSource: includeReplay ? "rendered_stage_media_with_replay" : "rendered_stage_media"
        )
    }

    private func publishQD2024Artifacts(
        row: CompendiumPublishRow,
        outputURL: URL,
        creatureDirURL: URL,
        baseRelativePath: String,
        searchRelativePath: String,
        shouldRenderMedia: Bool,
        encoder: JSONEncoder
    ) throws -> PublishedArtifacts {
        let runDirectory = try resolveRunDir(for: row)
        let qdRun = try loadLeniaBreeder2024ResolvedRun(
            runDirectory: runDirectory,
            configDirectoryOverride: URL(fileURLWithPath: defaultQD2024ConfigDirectory(), isDirectory: true)
        )
        let algorithm = row.sourceAlgorithm ?? qdRun.defaultAlgorithm

        try encoder.encode(qdRun.base).write(to: outputURL.appendingPathComponent(baseRelativePath))
        let searchConfigURL = outputURL.appendingPathComponent(searchRelativePath)
        if algorithm == "aurora" {
            try encoder.encode(qdRun.aurora).write(to: searchConfigURL)
        } else {
            try encoder.encode(qdRun.mapElites).write(to: searchConfigURL)
        }

        if !shouldRenderMedia {
            return (rendered: nil, artifactSource: "qd_2024_configs_only")
        }

        let elite = try resolveQD2024Elite(row: row, runDirectory: runDirectory)
        let frames = try captureLeniaBreeder2024ReplayFrames(
            run: qdRun,
            elite: elite,
            algorithmOverride: algorithm,
            frameBudget: frameBudget
        )
        let rendered = try writeRenderedMediaAssets(
            creatureId: row.creature.id.uuidString,
            genotype: row.creature.genotype,
            runtimeConfig: leniaBreeder2024VisualizationRuntimeConfig(
                run: qdRun,
                kernelParams: row.creature.genotype,
                algorithmOverride: algorithm
            ),
            selectedFrames: frames,
            assetBaseURL: outputURL,
            creatureDir: creatureDirURL,
            fps: fps,
            includeReplay: includeReplay
        )
        return (
            rendered: rendered,
            artifactSource: includeReplay ? "qd_2024_stage_media_with_replay" : "qd_2024_stage_media"
        )
    }

    private func renderMedia(
        creature: SavedCreature,
        baseConfig: LeniaBaseConfig,
        searchConfig: ParsedSearchConfig,
        outputURL: URL,
        creatureDirURL: URL
    ) throws -> AtlasRenderedMedia {
        let resolvedBackend = try resolveReplaySearchBackend(baseConfig: baseConfig)
        let replayBaseConfig = baseConfigBySettingBackend(baseConfig, backend: resolvedBackend)
        let runtimeConfig = try loadRuntimeConfig(from: JSONEncoder().encode(replayBaseConfig))
        let frames = try captureReplayFrames(
            runtimeConfig: runtimeConfig,
            seed: creature.initialCondition.seed,
            parsedSearch: searchConfig,
            frameBudget: frameBudget
        )
        return try writeRenderedMediaAssets(
            creatureId: creature.id.uuidString,
            genotype: creature.genotype,
            runtimeConfig: runtimeConfig,
            selectedFrames: frames,
            assetBaseURL: outputURL,
            creatureDir: creatureDirURL,
            fps: fps,
            includeReplay: includeReplay
        )
    }

    private func loadRunSnapshots(for rows: [CompendiumPublishRow]) throws -> [String: RunSnapshot] {
        var snapshots: [String: RunSnapshot] = [:]
        snapshots.reserveCapacity(Set(rows.map(\.runId)).count)

        for row in rows where snapshots[row.runId] == nil {
            let runDir = try resolveRunDir(for: row)
            let baseConfigURL = runDir.appendingPathComponent("config.json")
            let searchConfigURL = runDir.appendingPathComponent("search.json")

            guard FileManager.default.fileExists(atPath: baseConfigURL.path) else {
                throw ValidationError("Missing run config.json for \(row.runId): \(baseConfigURL.path)")
            }
            guard FileManager.default.fileExists(atPath: searchConfigURL.path) else {
                throw ValidationError("Missing run search.json for \(row.runId): \(searchConfigURL.path)")
            }

            snapshots[row.runId] = (
                base: try JSONDecoder().decode(LeniaBaseConfig.self, from: Data(contentsOf: baseConfigURL)),
                search: try JSONDecoder().decode(ParsedSearchConfig.self, from: Data(contentsOf: searchConfigURL))
            )
        }

        return snapshots
    }

    private func resolveQD2024Elite(
        row: CompendiumPublishRow,
        runDirectory: URL
    ) throws -> LeniaBreeder2024EliteSummary {
        if let metadata = row.researchMetadata,
           let genotype = qdFloatArray(metadata["genotype"]?.value) {
            return LeniaBreeder2024EliteSummary(
                cell: qdInt(metadata["cell"]?.value) ?? row.creature.initialCondition.seed,
                generation: qdInt(metadata["generation"]?.value) ?? 0,
                centroid: qdFloatArray(metadata["centroid"]?.value) ?? [],
                descriptor: qdFloatArray(metadata["descriptor"]?.value) ?? [],
                fitness: qdFloat(metadata["fitness"]?.value) ?? row.creature.score ?? 0,
                genotype: genotype
            )
        }

        if let fallback = try loadLeniaBreeder2024EliteSummaries(runDirectory: runDirectory)
            .first(where: { $0.cell == row.creature.initialCondition.seed }) {
            return fallback
        }
        throw ValidationError("Missing qd-2024 genotype for creature \(row.creature.id.uuidString).")
    }

    private func loadManifest(at url: URL) throws -> PublishedManifest {
        guard FileManager.default.fileExists(atPath: url.path) else {
            return PublishedManifest(schemaVersion: 1, defaultRelease: nil, releases: [])
        }
        return try JSONDecoder().decode(PublishedManifest.self, from: Data(contentsOf: url))
    }

    private func resolveRunDir(for row: CompendiumPublishRow) throws -> URL {
        guard let runDir = resolveRunArtifactPath(outputRoot: row.outputRoot, runDir: row.runDir, path: nil) else {
            throw ValidationError("Run directory is missing for \(row.runId).")
        }
        return URL(fileURLWithPath: runDir, isDirectory: true)
    }

    private func validateReleaseId(_ value: String) throws -> String {
        guard let trimmed = normalized(value) else {
            throw ValidationError("--release-id must not be empty.")
        }
        if trimmed.range(of: #"^[A-Za-z0-9][A-Za-z0-9._-]*$"#, options: .regularExpression) == nil {
            throw ValidationError("Invalid --release-id '\(trimmed)'. Use letters, numbers, dot, dash, or underscore.")
        }
        return trimmed
    }

    private func detailFileName(for creatureId: String) -> String {
        "\(creatureId.lowercased()).json"
    }

    private func sanitizeOwnerId(_ ownerId: String) -> String {
        let trimmed = ownerId.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            return "unknown"
        }
        if trimmed.hasSuffix(".local") || trimmed == "localhost" {
            return "local-node"
        }
        return trimmed
    }

    private func formatISO8601(_ date: Date) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.string(from: date)
    }

    private func decodeOptionalJSONString<T: Decodable>(
        _ value: String?,
        as _: T.Type,
        decoder: JSONDecoder
    ) throws -> T? {
        guard let value else { return nil }
        return try decoder.decode(T.self, from: Data(value.utf8))
    }

    private func columnText(_ stmt: OpaquePointer, index: Int32) -> String? {
        guard let text = sqlite3_column_text(stmt, index) else { return nil }
        return String(cString: text)
    }

    private func columnDouble(_ stmt: OpaquePointer, index: Int32) -> Double? {
        guard sqlite3_column_type(stmt, index) != SQLITE_NULL else { return nil }
        return sqlite3_column_double(stmt, index)
    }
}

private struct CompendiumPublishRow {
    let creature: SavedCreature
    let runId: String
    let runName: String
    let campaignId: String?
    let recordedAt: String
    let isStable: Bool
    let outputRoot: String?
    let runDir: String?
    let sourceMode: String?
    let sourceAlgorithm: String?
    let researchMetadata: [String: AnyCodable]?

    var isQD2024: Bool {
        sourceMode == "qd-2024"
    }
}

private struct PublishedManifest: Codable {
    let schemaVersion: Int
    var defaultRelease: String?
    var releases: [PublishedManifestRelease]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case defaultRelease = "default_release"
        case releases
    }

    mutating func upsert(_ release: PublishedManifestRelease) {
        if let index = releases.firstIndex(where: { $0.id == release.id }) {
            releases[index] = release
        } else {
            releases.append(release)
        }
    }
}

private struct PublishedManifestRelease: Codable {
    let id: String
    let label: String
    let index: String
    let creatureCount: Int
    let runCount: Int
    let publishedAt: String
    let firstRecordedAt: String?
    let lastRecordedAt: String?
    let sourceDb: String

    enum CodingKeys: String, CodingKey {
        case id
        case label
        case index
        case creatureCount = "creature_count"
        case runCount = "run_count"
        case publishedAt = "published_at"
        case firstRecordedAt = "first_recorded_at"
        case lastRecordedAt = "last_recorded_at"
        case sourceDb = "source_db"
    }
}

private struct PublishedIndexEntry: Codable {
    let id: String
    let name: String
    let detail: String
    let baseConfig: String
    let searchConfig: String
    let score: Float?
    let seed: Int
    let isStable: Bool
    let runId: String
    let runName: String
    let campaignId: String?
    let recordedAt: String
    let metrics: PublishedMetricSummary
    let telemetry: AtlasTelemetrySummary?
    let media: AtlasMedia?

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case detail
        case baseConfig = "base_config"
        case searchConfig = "search_config"
        case score
        case seed
        case isStable = "is_stable"
        case runId = "run_id"
        case runName = "run_name"
        case campaignId = "campaign_id"
        case recordedAt = "recorded_at"
        case metrics
        case telemetry
        case media
    }
}

private struct PublishedMetricSummary: Codable {
    let centerVelocity: Float
    let displacement: Float
    let pathLength: Float
    let gyration: Float
    let occupancyMean: Float
    let velocityX: Float
    let velocityY: Float
    let headingRad: Float
    let translationRatio: Float

    init(metrics: SimulationMetrics) {
        centerVelocity = metrics.centerVelocity
        displacement = metrics.displacement
        pathLength = metrics.pathLength
        gyration = metrics.gyration
        occupancyMean = metrics.occupancyMean
        velocityX = metrics.velocityX
        velocityY = metrics.velocityY
        headingRad = metrics.headingRad
        translationRatio = publishedTranslationRatio(for: metrics)
    }

    enum CodingKeys: String, CodingKey {
        case centerVelocity = "center_velocity"
        case displacement
        case pathLength = "path_length"
        case gyration
        case occupancyMean = "occupancy_mean"
        case velocityX = "velocity_x"
        case velocityY = "velocity_y"
        case headingRad = "heading_rad"
        case translationRatio = "translation_ratio"
    }
}

private struct PublishedDetail: Codable {
    let creature: PublishedCreaturePayload
    let runId: String
    let runName: String
    let campaignId: String?
    let recordedAt: String
    let publishedAt: String
    let sourceDb: String
    let artifactSource: String
    let reason: String?
    let filtersPassed: Bool?
    let telemetry: AtlasTelemetrySummary?
    let media: AtlasMedia?

    enum CodingKeys: String, CodingKey {
        case creature
        case runId = "run_id"
        case runName = "run_name"
        case campaignId = "campaign_id"
        case recordedAt = "recorded_at"
        case publishedAt = "published_at"
        case sourceDb = "source_db"
        case artifactSource = "artifact_source"
        case reason
        case filtersPassed = "filters_passed"
        case telemetry
        case media
    }
}

private struct PublishedCreaturePayload: Codable {
    let id: String
    let name: String
    let timestamp: String
    let ownerId: String
    let genotype: KernelParams
    let initialCondition: InitConfig
    let metrics: SimulationMetrics
    let sweep: [String: Double]?
    let score: Float?
    let scoreWeights: [String: Float]?
    let configHash: String?

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case timestamp
        case ownerId = "owner_id"
        case genotype
        case initialCondition = "phenotype"
        case metrics
        case sweep
        case score
        case scoreWeights = "score_weights"
        case configHash = "config_hash"
    }
}

private func publicSourceDbLabel(_ path: String) -> String {
    let name = URL(fileURLWithPath: path).lastPathComponent
    return name.isEmpty ? path : name
}

private func qdInt(_ value: Any?) -> Int? {
    switch value {
    case let int as Int:
        return int
    case let double as Double:
        return Int(double)
    case let float as Float:
        return Int(float)
    default:
        return nil
    }
}

private func qdFloat(_ value: Any?) -> Float? {
    switch value {
    case let float as Float:
        return float
    case let double as Double:
        return Float(double)
    case let int as Int:
        return Float(int)
    default:
        return nil
    }
}

private func qdFloatArray(_ value: Any?) -> [Float]? {
    guard let array = value as? [Any] else { return nil }
    return array.compactMap(qdFloat)
}

private func defaultQD2024ConfigDirectory(filePath: String = #filePath) -> String {
    let packageRoot = URL(fileURLWithPath: filePath)
        .deletingLastPathComponent() // Compendium
        .deletingLastPathComponent() // LeniaCLI
        .deletingLastPathComponent() // Sources
        .deletingLastPathComponent() // package root
    return packageRoot.appendingPathComponent("configs/papers/leniabreeder-2024", isDirectory: true).path
}

private func publishedTranslationRatio(for metrics: SimulationMetrics) -> Float {
    guard metrics.pathLength > 1e-6 else { return 0 }
    return metrics.displacement / metrics.pathLength
}
