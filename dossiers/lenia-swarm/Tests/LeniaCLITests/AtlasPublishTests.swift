import Foundation
import SQLite3
import XCTest
@testable import LeniaCLIKit
import LeniaArchive
import LeniaCore

final class AtlasPublishTests: XCTestCase {
    func testAtlasPublishRejectsPendingTaxonomyByDefault() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-atlas-pending-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let runDir = root.appendingPathComponent("run-001", isDirectory: true)
        try makeAtlasRunLayout(at: runDir)
        try writeAtlasJSONL([
            makeAtlasLibraryEntry(
                creature: makeAtlasCreature(
                    id: UUID(uuidString: "41414141-4141-4141-4141-414141414141")!,
                    name: "pending-taxonomy",
                    seed: 7
                ),
                runID: "run-001"
            ),
        ], to: runDir.appendingPathComponent("library/index.jsonl"))

        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        var index = try IndexCommand.parseAsRoot([
            "--run-dir", runDir.path,
            "--db", dbPath,
            "--rebuild",
        ])
        try index.run()

        let outputDir = root.appendingPathComponent("atlas-published", isDirectory: true)
        var publish = try AtlasPublishCommand.parseAsRoot([
            "--db", dbPath,
            "--output", outputDir.path,
            "--skip-media",
        ])

        XCTAssertThrowsError(try publish.run()) { error in
            XCTAssertTrue(String(describing: error).contains("requires taxonomy"))
        }
    }

    func testTaxonomyAndAtlasPublishWriteCatalogWithMotionMetrics() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-atlas-publish-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let runDir = root.appendingPathComponent("run-001", isDirectory: true)
        try makeAtlasRunLayout(at: runDir)

        try writeAtlasJSONL([
            makeAtlasLibraryEntry(
                creature: makeAtlasCreature(
                    id: UUID(uuidString: "51515151-5151-5151-5151-515151515151")!,
                    name: "atlas-glider",
                    seed: 13
                ),
                runID: "run-001"
            ),
        ], to: runDir.appendingPathComponent("library/index.jsonl"))

        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        var index = try IndexCommand.parseAsRoot([
            "--run-dir", runDir.path,
            "--db", dbPath,
            "--rebuild",
        ])
        try index.run()

        var taxonomy = try TaxonomyCommand.parseAsRoot([
            "--db", dbPath,
        ])
        try taxonomy.run()

        let db = try SQLiteDB(path: dbPath)
        let stmt = try db.prepare("""
            SELECT taxonomy_family_id, taxonomy_genus_id, taxonomy_species_id,
                   taxonomy_method, taxonomy_version, velocity_x, velocity_y, heading_rad
            FROM creatures
            LIMIT 1
        """)
        defer { sqlite3_finalize(stmt) }
        XCTAssertEqual(sqlite3_step(stmt), SQLITE_ROW)
        XCTAssertEqual(String(cString: sqlite3_column_text(stmt, 0)), "fam-translator-soliton")
        XCTAssertNotNil(sqlite3_column_text(stmt, 1))
        XCTAssertNotNil(sqlite3_column_text(stmt, 2))
        XCTAssertEqual(String(cString: sqlite3_column_text(stmt, 3)), "lenia-swarm:taxonomy-heuristic")
        XCTAssertEqual(sqlite3_column_int(stmt, 4), 1)
        XCTAssertEqual(sqlite3_column_double(stmt, 5), 0.012, accuracy: 1e-6)
        XCTAssertEqual(sqlite3_column_double(stmt, 6), -0.004, accuracy: 1e-6)
        XCTAssertEqual(sqlite3_column_double(stmt, 7), -0.32175055, accuracy: 1e-6)

        let outputDir = root.appendingPathComponent("atlas-published", isDirectory: true)
        var publish = try AtlasPublishCommand.parseAsRoot([
            "--db", dbPath,
            "--output", outputDir.path,
            "--skip-media",
        ])
        try publish.run()

        let catalogURL = outputDir.appendingPathComponent("catalog.json")
        XCTAssertTrue(fm.fileExists(atPath: outputDir.appendingPathComponent("catalog.sqlite").path))
        let rawCatalog = try Data(contentsOf: catalogURL)
        let catalog = try XCTUnwrap(JSONSerialization.jsonObject(with: rawCatalog) as? [String: Any])
        let revision = try XCTUnwrap(catalog["revision"] as? [String: Any])
        XCTAssertEqual(revision["creatureCount"] as? Int, 1)

        let taxa = try XCTUnwrap(catalog["taxa"] as? [[String: Any]])
        XCTAssertEqual(taxa.count, 3)

        let runs = try XCTUnwrap(catalog["runs"] as? [[String: Any]])
        XCTAssertEqual(runs.count, 1)

        let creatures = try XCTUnwrap(catalog["creatures"] as? [[String: Any]])
        XCTAssertEqual(creatures.count, 1)
        let creature = try XCTUnwrap(creatures.first)
        XCTAssertEqual(creature["id"] as? String, "51515151-5151-5151-5151-515151515151")
        XCTAssertEqual(creature["familyId"] as? String, "fam-translator-soliton")
        XCTAssertEqual(creature["genusId"] as? String, "fam-translator-soliton.speed-fast.path-meander.cx-mid.mass-small")

        let metrics = try XCTUnwrap(creature["metrics"] as? [String: Any])
        let velocityX = try XCTUnwrap(metrics["velocityX"] as? Double)
        let velocityY = try XCTUnwrap(metrics["velocityY"] as? Double)
        let headingRad = try XCTUnwrap(metrics["headingRad"] as? Double)
        XCTAssertEqual(velocityX, 0.012, accuracy: 1e-6)
        XCTAssertEqual(velocityY, -0.004, accuracy: 1e-6)
        XCTAssertEqual(headingRad, -0.32175055, accuracy: 1e-6)
    }

    func testAtlasPublishWithMediaWritesSQLiteCatalogAndAnatomyAssets() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-atlas-media-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let runDir = root.appendingPathComponent("run-001", isDirectory: true)
        try makeAtlasRunLayout(at: runDir)
        try installAtlasRenderConfigs(at: runDir)

        try writeAtlasJSONL([
            makeAtlasLibraryEntry(
                creature: makeAtlasCreature(
                    id: UUID(uuidString: "61616161-6161-6161-6161-616161616161")!,
                    name: "atlas-render",
                    seed: 17,
                    patches: [PatchConfig(center: [64, 64], size: 40)],
                    aUniform: UniformRange(low: 0, high: 1)
                ),
                runID: "run-001"
            ),
        ], to: runDir.appendingPathComponent("library/index.jsonl"))

        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        var index = try IndexCommand.parseAsRoot([
            "--run-dir", runDir.path,
            "--db", dbPath,
            "--rebuild",
        ])
        try index.run()

        var taxonomy = try TaxonomyCommand.parseAsRoot([
            "--db", dbPath,
        ])
        try taxonomy.run()

        let outputDir = root.appendingPathComponent("atlas-published", isDirectory: true)
        let creatureDir = outputDir
            .appendingPathComponent("media/creatures", isDirectory: true)
            .appendingPathComponent("61616161-6161-6161-6161-616161616161", isDirectory: true)
        let mediaRoot = outputDir.appendingPathComponent("media", isDirectory: true)
        try fm.createDirectory(at: creatureDir, withIntermediateDirectories: true)

        let baseConfigData = try Data(contentsOf: runDir.appendingPathComponent("config.json"))
        let runtimeConfig = try loadRuntimeConfig(from: baseConfigData)
        let frames = makeSyntheticFrames(width: runtimeConfig.sx, height: runtimeConfig.sy, count: 6)
        let creature = makeAtlasCreature(
            id: UUID(uuidString: "61616161-6161-6161-6161-616161616161")!,
            name: "atlas-render",
            seed: 17,
            patches: [PatchConfig(center: [64, 64], size: 40)],
            aUniform: UniformRange(low: 0, high: 1)
        )
        let parsedPublisher = try AtlasPublishCommand.parseAsRoot([
            "--db", dbPath,
            "--output", outputDir.path,
            "--frame-budget", "6",
            "--fps", "12",
        ])
        let publisher = try XCTUnwrap(parsedPublisher as? AtlasPublishCommand)
        let rendered = try publisher.writeAtlasRenderedMedia(
            creatureId: creature.id.uuidString,
            genotype: creature.genotype,
            runtimeConfig: runtimeConfig,
            selectedFrames: frames,
            mediaRoot: mediaRoot,
            creatureDir: creatureDir,
            fps: 12
        )

        for fileName in [
            "poster.png",
            "field.png",
            "delta.png",
            "neighbor.png",
            "kernel.png",
            "frames.bin",
            "replay.json",
        ] {
            XCTAssertTrue(fm.fileExists(atPath: creatureDir.appendingPathComponent(fileName).path), "Missing \(fileName)")
        }
        XCTAssertEqual(rendered.media.anatomy.fieldPath, "media/creatures/61616161-6161-6161-6161-616161616161/field.png")
        XCTAssertEqual(rendered.media.anatomy.kernelPath, "media/creatures/61616161-6161-6161-6161-616161616161/kernel.png")
        XCTAssertFalse(rendered.telemetry.trail.isEmpty)
        XCTAssertGreaterThan(rendered.telemetry.centroid.x, 0)
        XCTAssertLessThan(rendered.telemetry.centroid.x, 1)
    }

    func testCompendiumPublishWritesStageMediaAndReplayPayloads() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-compendium-media-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let runDir = root.appendingPathComponent("run-001", isDirectory: true)
        try makeAtlasRunLayout(at: runDir)
        try installAtlasRenderConfigs(at: runDir)

        let creatureId = UUID(uuidString: "71717171-7171-7171-7171-717171717171")!
        try writeAtlasJSONL([
            makeAtlasLibraryEntry(
                creature: makeAtlasCreature(
                    id: creatureId,
                    name: "compendium-render",
                    seed: 29,
                    patches: [PatchConfig(center: [64, 64], size: 40)],
                    aUniform: UniformRange(low: 0, high: 1)
                ),
                runID: "run-001"
            ),
        ], to: runDir.appendingPathComponent("library/index.jsonl"))

        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        var index = try IndexCommand.parseAsRoot([
            "--run-dir", runDir.path,
            "--db", dbPath,
            "--rebuild",
        ])
        try index.run()

        let outputDir = root.appendingPathComponent("compendium-published", isDirectory: true)
        var publish = try CompendiumPublishCommand.parseAsRoot([
            "--db", dbPath,
            "--output", outputDir.path,
            "--release-id", "specimens-v1",
            "--frame-budget", "6",
            "--fps", "12",
            "--include-replay",
        ])
        try publish.run()

        let creatureDir = outputDir
            .appendingPathComponent("releases/specimens-v1/runs/run-001", isDirectory: true)
            .appendingPathComponent(creatureId.uuidString.lowercased(), isDirectory: true)
        for fileName in [
            "base.json",
            "search.json",
            "poster.png",
            "field.png",
            "delta.png",
            "neighbor.png",
            "kernel.png",
            "frames.bin",
            "replay.json",
        ] {
            XCTAssertTrue(fm.fileExists(atPath: creatureDir.appendingPathComponent(fileName).path), "Missing \(fileName)")
        }

        let indexURL = outputDir.appendingPathComponent("releases/specimens-v1/index.json")
        let rawIndex = try Data(contentsOf: indexURL)
        let entries = try XCTUnwrap(JSONSerialization.jsonObject(with: rawIndex) as? [[String: Any]])
        XCTAssertEqual(entries.count, 1)
        let entry = try XCTUnwrap(entries.first)
        let telemetry = try XCTUnwrap(entry["telemetry"] as? [String: Any])
        XCTAssertNotNil(telemetry["centroid"])
        XCTAssertNotNil(telemetry["trail"])
        XCTAssertNotNil(telemetry["headingRad"])

        let metrics = try XCTUnwrap(entry["metrics"] as? [String: Any])
        XCTAssertEqual(try XCTUnwrap(metrics["center_velocity"] as? Double), 0.01264911, accuracy: 1e-6)
        XCTAssertEqual(try XCTUnwrap(metrics["displacement"] as? Double), 2.0, accuracy: 1e-6)
        XCTAssertEqual(try XCTUnwrap(metrics["path_length"] as? Double), 10.0, accuracy: 1e-6)
        XCTAssertEqual(try XCTUnwrap(metrics["translation_ratio"] as? Double), 0.2, accuracy: 1e-6)

        let media = try XCTUnwrap(entry["media"] as? [String: Any])
        XCTAssertEqual(media["posterPath"] as? String, "releases/specimens-v1/runs/run-001/\(creatureId.uuidString.lowercased())/poster.png")
        XCTAssertEqual(media["replayPath"] as? String, "releases/specimens-v1/runs/run-001/\(creatureId.uuidString.lowercased())/replay.json")

        let detailURL = outputDir.appendingPathComponent("releases/specimens-v1/details/\(creatureId.uuidString.lowercased()).json")
        let rawDetail = try Data(contentsOf: detailURL)
        let detail = try XCTUnwrap(JSONSerialization.jsonObject(with: rawDetail) as? [String: Any])
        XCTAssertEqual(detail["artifact_source"] as? String, "rendered_stage_media_with_replay")
        XCTAssertEqual(detail["source_db"] as? String, "compendium.sqlite")
        XCTAssertNotNil(detail["media"])
        XCTAssertNotNil(detail["telemetry"])
    }

    func testCompendiumPublishFiltersCompactSinglePatchCandidates() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-compendium-gliders-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let runDir = root.appendingPathComponent("run-001", isDirectory: true)
        try makeAtlasRunLayout(at: runDir)
        try installAtlasRenderConfigs(at: runDir)

        let compactId = UUID(uuidString: "81818181-8181-8181-8181-818181818181")!
        let distributedId = UUID(uuidString: "91919191-9191-9191-9191-919191919191")!
        try writeAtlasJSONL([
            makeAtlasLibraryEntry(
                creature: makeAtlasCreature(
                    id: compactId,
                    name: "compact-glider",
                    seed: 41,
                    patches: [PatchConfig(center: [64, 64], size: 40)],
                    aUniform: UniformRange(low: 0, high: 1),
                    occupancyMean: 0.08,
                    pathLength: 3.0,
                    displacement: 2.7,
                    gyration: 640,
                    centerVelocity: 0.0042,
                    velocityX: 0.0038,
                    velocityY: 0.0012,
                    headingRad: 0.30587888
                ),
                runID: "run-001"
            ),
            makeAtlasLibraryEntry(
                creature: makeAtlasCreature(
                    id: distributedId,
                    name: "distributed-pattern",
                    seed: 43,
                    patches: [
                        PatchConfig(center: [32, 32], size: 20),
                        PatchConfig(center: [96, 32], size: 20),
                        PatchConfig(center: [32, 96], size: 20),
                        PatchConfig(center: [96, 96], size: 20),
                    ],
                    aUniform: UniformRange(low: 0, high: 1),
                    occupancyMean: 0.24,
                    pathLength: 4.0,
                    displacement: 1.6,
                    gyration: 2400,
                    centerVelocity: 0.0051,
                    velocityX: 0.0046,
                    velocityY: 0.0022,
                    headingRad: 0.44610554
                ),
                runID: "run-001"
            ),
        ], to: runDir.appendingPathComponent("library/index.jsonl"))

        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        var index = try IndexCommand.parseAsRoot([
            "--run-dir", runDir.path,
            "--db", dbPath,
            "--rebuild",
        ])
        try index.run()

        let outputDir = root.appendingPathComponent("compendium-published", isDirectory: true)
        var publish = try CompendiumPublishCommand.parseAsRoot([
            "--db", dbPath,
            "--output", outputDir.path,
            "--release-id", "glider-candidates-v1",
            "--skip-media",
            "--max-patches", "1",
            "--max-occupancy", "0.15",
            "--max-gyration", "1200",
            "--min-center-velocity", "0.003",
            "--min-translation-ratio", "0.8",
        ])
        try publish.run()

        let indexURL = outputDir.appendingPathComponent("releases/glider-candidates-v1/index.json")
        let rawIndex = try Data(contentsOf: indexURL)
        let entries = try XCTUnwrap(JSONSerialization.jsonObject(with: rawIndex) as? [[String: Any]])
        XCTAssertEqual(entries.count, 1)
        let entry = try XCTUnwrap(entries.first)
        XCTAssertEqual(entry["id"] as? String, compactId.uuidString)
        XCTAssertEqual(entry["name"] as? String, "compact-glider")

        let manifestURL = outputDir.appendingPathComponent("manifest.json")
        let rawManifest = try Data(contentsOf: manifestURL)
        let manifest = try XCTUnwrap(JSONSerialization.jsonObject(with: rawManifest) as? [String: Any])
        let releases = try XCTUnwrap(manifest["releases"] as? [[String: Any]])
        let release = try XCTUnwrap(releases.first(where: { ($0["id"] as? String) == "glider-candidates-v1" }))
        XCTAssertEqual(release["creature_count"] as? Int, 1)
        XCTAssertEqual(release["source_db"] as? String, "compendium.sqlite")
    }

    func testBrowseCompendiumPrefersCanonicalSpecimenSnapshots() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-compendium-browse-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let runDir = root.appendingPathComponent("run-001", isDirectory: true)
        try makeAtlasRunLayout(at: runDir)

        let creature = makeAtlasCreature(
            id: UUID(uuidString: "73737373-7373-7373-7373-737373737373")!,
            name: "browser-canonical",
            seed: 17
        )
        try writeAtlasJSONL(
            [makeAtlasLibraryEntry(creature: creature, runID: "run-001")],
            to: runDir.appendingPathComponent("library/index.jsonl")
        )

        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        var index = try IndexCommand.parseAsRoot([
            "--run-dir", runDir.path,
            "--db", dbPath,
            "--rebuild",
        ])
        try index.run()

        let mutatedInitialCondition = InitConfig(
            seed: 99,
            patches: creature.initialCondition.patches,
            a_uniform: creature.initialCondition.a_uniform,
            p_uniform: creature.initialCondition.p_uniform,
            state_patch: creature.initialCondition.state_patch,
            p_state_patch: creature.initialCondition.p_state_patch
        )
        let mutatedGenotype = KernelParams(
            r: [9.0],
            b: creature.genotype.b,
            w: creature.genotype.w,
            a: creature.genotype.a,
            m: creature.genotype.m,
            s: creature.genotype.s,
            h: creature.genotype.h,
            R: 99.0
        )

        let encoder = JSONEncoder()
        let db = try SQLiteDB(path: dbPath)
        let stmt = try db.prepare("""
            UPDATE creatures
            SET genotype_json = ?, initial_condition_json = ?, trait_labels_json = '["drifted"]'
            WHERE id = ?
            """)
        defer { sqlite3_finalize(stmt) }
        db.bindText(stmt, index: 1, value: String(data: try encoder.encode(mutatedGenotype), encoding: .utf8))
        db.bindText(stmt, index: 2, value: String(data: try encoder.encode(mutatedInitialCondition), encoding: .utf8))
        db.bindText(stmt, index: 3, value: creature.id.uuidString)
        try db.step(stmt)

        let result = try browseCompendium(path: dbPath, query: CompendiumBrowseQuery(limit: 10))
        let entry = try XCTUnwrap(result.entries.first)

        XCTAssertEqual(entry.creature.initialCondition.seed, creature.initialCondition.seed)
        XCTAssertEqual(entry.previewSeed, creature.initialCondition.seed)
        XCTAssertEqual(entry.creature.genotype.R, creature.genotype.R)
        XCTAssertNotEqual(entry.creature.initialCondition.seed, mutatedInitialCondition.seed)
        XCTAssertNotEqual(entry.creature.genotype.R, mutatedGenotype.R)
    }
}

private let atlasFixedDate = Date(timeIntervalSince1970: 1_700_000_000)

private func makeAtlasRunLayout(at runDir: URL) throws {
    let fm = FileManager.default
    try fm.createDirectory(at: runDir.appendingPathComponent("library", isDirectory: true), withIntermediateDirectories: true)
    try fm.createDirectory(at: runDir.appendingPathComponent("overall", isDirectory: true), withIntermediateDirectories: true)
    try fm.createDirectory(at: runDir.appendingPathComponent("exports", isDirectory: true), withIntermediateDirectories: true)
}

private func installAtlasRenderConfigs(at runDir: URL) throws {
    let fm = FileManager.default
    let configsDir = leniaSwarmPackageRoot.appendingPathComponent("configs", isDirectory: true)
    try fm.copyItem(
        at: configsDir.appendingPathComponent("base/paper_base_1c_128.json"),
        to: runDir.appendingPathComponent("config.json")
    )
    try fm.copyItem(
        at: configsDir.appendingPathComponent("base/paper_search_random.json"),
        to: runDir.appendingPathComponent("search.json")
    )
}

private func makeAtlasLibraryEntry(
    creature: SavedCreature,
    runID: String
) -> ResearchLibraryEntry {
    ResearchLibraryEntry(
        creature: creature,
        campaignId: nil,
        runId: runID,
        recordedAt: atlasFixedDate,
        configHash: "atlas-fixture",
        sourceMode: "search",
        sourceAlgorithm: "fixture"
    )
}

private func makeAtlasCreature(
    id: UUID,
    name: String,
    seed: Int,
    patches: [PatchConfig] = [],
    aUniform: UniformRange = UniformRange(low: 0, high: 0),
    occupancyMean: Float = 0.2,
    pathLength: Float = 10,
    displacement: Float = 2,
    gyration: Float = 3,
    centerVelocity: Float = 0.01264911,
    velocityX: Float = 0.012,
    velocityY: Float = -0.004,
    headingRad: Float = -0.32175055,
    complexityMean: Float = 0.08
) -> SavedCreature {
    let genotype = KernelParams(
        r: [1.0],
        b: [[0.1, 0.2, 0.3]],
        w: [[0.4, 0.5, 0.6]],
        a: [[0.7, 0.8, 0.9]],
        m: [0.15],
        s: [0.03],
        h: [1.0],
        R: 10.0
    )
    let metrics = SimulationMetrics(
        massMean: 120,
        massStd: 0.1,
        massMin: 0,
        massMax: 140,
        occupancyMean: occupancyMean,
        varianceMean: 0.01,
        energyMean: 0.3,
        speedMean: 0.4,
        pathLength: pathLength,
        displacement: displacement,
        sampleCount: 2,
        speedCount: 1,
        gyration: gyration,
        centerVelocity: centerVelocity,
        velocityX: velocityX,
        velocityY: velocityY,
        headingRad: headingRad,
        isStable: true,
        complexityMean: complexityMean
    )
    return SavedCreature(
        id: id,
        name: name,
        ownerId: "tester",
        genotype: genotype,
        initialCondition: InitConfig(
            seed: seed,
            patches: patches,
            a_uniform: aUniform,
            p_uniform: nil
        ),
        descriptorBundle: makeAtlasDescriptorBundle(genotype: genotype, metrics: metrics),
        metrics: metrics,
        sweep: nil,
        score: 0.99,
        scoreWeights: ["mass_mean": 1.0]
    )
}

private func makeAtlasDescriptorBundle(
    genotype: KernelParams,
    metrics: SimulationMetrics
) -> MorphospaceDescriptorBundle {
    MorphospaceDescriptorBundle(
        symmetryPolicy: "translation_kernel_permutation_v1",
        genotype: MorphospaceGenotypeDescriptor(
            kernelCount: genotype.r.count,
            vectorLength: 8,
            vector: [genotype.r.first ?? 0, genotype.m.first ?? 0, genotype.s.first ?? 0, genotype.h.first ?? 0, metrics.massMean, metrics.occupancyMean, metrics.gyration, metrics.centerVelocity],
            hash12: "atlasfixture"
        ),
        terminal: MorphospaceTerminalDescriptor(
            massChannel: 0,
            borderMode: "wall",
            symmetryPolicy: "translation_kernel_permutation_v1",
            fingerprintResolution: 32,
            fingerprintU8: Data(repeating: 3, count: 32 * 32),
            angularSymmetry: MorphospaceAngularSymmetryDescriptor(
                binCount: 32,
                maxOrder: 8,
                harmonics: [0.05, 0.15, 0.75, 0.1, 0.0, 0.0, 0.0, 0.0],
                dominantOrder: 3,
                dominantAmplitude: 0.75,
                normalizedEntropy: 0.28
            ),
            fingerprintHash12: "atlasfixture",
            finalMass: metrics.massMean,
            finalOccupancy: metrics.occupancyMean,
            finalGyration: metrics.gyration,
            momentMass: metrics.massMean,
            momentVolume: 3.0,
            momentDensity: 0.4,
            momentAnisotropy: 0.35,
            componentCount: 1.0,
            largestComponentFraction: 1.0,
            largestComponentAnisotropy: 0.42,
            hu1: 0.1,
            hu2: 0.2,
            hu3: 0.3,
            hu4: 0.4,
            hu5: 0.5,
            hu6: 0.6,
            hu7: 0.7,
            flusser1: 0.11,
            flusser2: 0.12,
            flusser3: 0.13,
            flusser4: 0.14,
            windowMassStd: 0.02,
            windowOccupancyStd: 0.03,
            windowGyrationStd: 0.04,
            isStable: metrics.isStable
        ),
        trajectory: MorphospaceTrajectoryDescriptor(
            recordInterval: 1,
            warmupSteps: 0,
            sampleCount: max(metrics.sampleCount, 1),
            pathLength: metrics.pathLength,
            displacement: metrics.displacement,
            pathTortuosity: 1.1,
            movementEfficiency: 0.8,
            speedMean: metrics.speedMean,
            centerVelocity: metrics.centerVelocity,
            velocityX: metrics.velocityX,
            velocityY: metrics.velocityY,
            headingRad: metrics.headingRad,
            headingCircularVariance: 0.2,
            accumulatedTurnAbs: 0.3,
            survivalSteps: nil,
            activityEacMean: metrics.activityEacMean,
            activityEanMean: metrics.activityEanMean,
            activityDiversityMean: metrics.activityDiversityMean,
            activitySpeciesMean: metrics.activitySpeciesMean,
            activitySpeciesMax: nil,
            activitySpeciesStd: nil,
            activityDiversityStd: nil,
            activityEacMax: nil,
            activityEanMax: nil,
            componentSeriesMean: nil,
            componentSeriesStd: nil,
            componentSeriesMax: nil
        )
    )
}

private func writeAtlasJSONL<T: Encodable>(_ values: [T], to url: URL) throws {
    let encoder = JSONEncoder()
    let content = try values.map { value -> String in
        let data = try encoder.encode(value)
        return String(data: data, encoding: .utf8)! + "\n"
    }.joined()
    try content.write(to: url, atomically: true, encoding: .utf8)
}

private let leniaSwarmPackageRoot = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent()
    .deletingLastPathComponent()
    .deletingLastPathComponent()

private func makeSyntheticFrames(width: Int, height: Int, count: Int) -> [Data] {
    var frames: [Data] = []
    frames.reserveCapacity(count)

    for frameIndex in 0..<count {
        var bytes = [UInt8](repeating: 0, count: width * height)
        let centerX = Float(width) * (0.36 + 0.06 * Float(frameIndex))
        let centerY = Float(height) * (0.56 - 0.035 * Float(frameIndex))
        let tailX = centerX - 18
        let tailY = centerY + 10

        for y in 0..<height {
            let fy = Float(y)
            for x in 0..<width {
                let fx = Float(x)
                let core = exp(-((fx - centerX) * (fx - centerX) + (fy - centerY) * (fy - centerY)) / 180)
                let tail = exp(-((fx - tailX) * (fx - tailX) + (fy - tailY) * (fy - tailY)) / 320)
                let wake = exp(-((fx - (centerX - 10)) * (fx - (centerX - 10)) + (fy - (centerY - 12)) * (fy - (centerY - 12))) / 420)
                let value = min(core * 0.9 + tail * 0.45 + wake * 0.3, 1.0)
                bytes[y * width + x] = UInt8(max(0, min(255, Int(value * 255 + 0.5))))
            }
        }
        frames.append(Data(bytes))
    }

    return frames
}
