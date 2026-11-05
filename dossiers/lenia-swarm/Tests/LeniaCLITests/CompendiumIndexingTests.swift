import ArgumentParser
import Foundation
import DistributedCluster
import Logging
import SQLite3
import XCTest
@testable import LeniaCLIKit
import LeniaArchive
import LeniaCore

private func testLibraryEntry(creature: SavedCreature, campaign_id: String?, run_id: String, recorded_at: Date) -> ResearchLibraryEntry {
    ResearchLibraryEntry(creature: creature, campaignId: campaign_id, runId: run_id, recordedAt: recorded_at, configHash: nil)
}

final class CompendiumIndexingTests: XCTestCase {
    func testIndexPlanAcceptsMultipleRunDirs() throws {
        let root = try makeTempDirectory(prefix: "lenia-multi-run-ingest")
        defer { try? FileManager.default.removeItem(at: root) }

        let runA = root.appendingPathComponent("run-a", isDirectory: true)
        let runB = root.appendingPathComponent("run-b", isDirectory: true)
        try makeRunLayout(at: runA)
        try makeRunLayout(at: runB)

        let plan = try resolveCompendiumIngestPlan(
            outputRoots: [],
            runDirs: [runA.path, runB.path],
            dbPath: root.appendingPathComponent("compendium.sqlite").path
        )

        XCTAssertEqual(plan.runInputs.map(\.runId), ["run-a", "run-b"])
    }

    func testIndexIngestsEcologyArenaRuns() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-cli-ecology-index-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let packageRoot = leniaCLIPackageRoot
        let sourceDirectory = packageRoot.appendingPathComponent("configs/papers/flowlenia-ecology-2025", isDirectory: true)
        let configDirectory = root.appendingPathComponent("configs", isDirectory: true)
        let runDir = root.appendingPathComponent("run-ecology-001", isDirectory: true)
        try fm.createDirectory(at: root, withIntermediateDirectories: true)
        try fm.copyItem(at: sourceDirectory, to: configDirectory)
        try fm.createDirectory(at: runDir, withIntermediateDirectories: true)

        try rewriteJSONFile(at: configDirectory.appendingPathComponent("vanilla-base.json")) { json in
            json["grid"] = ["sx": 32, "sy": 32]
            json["run"] = ["steps": 20]
            json["init"] = [
                "seed": 0,
                "patches": [["center": [16, 16], "size": 8]],
                "a_uniform": ["low": 0.0, "high": 1.0],
                "p_uniform": ["low": 0.0, "high": 1.0]
            ]
            json["beam_mutation"] = [
                "enabled": true,
                "probability": 0.01,
                "patch_size": 4,
                "std": 1.0,
                "seed": 11
            ]
        }

        try rewriteJSONFile(at: configDirectory.appendingPathComponent("simulation.json")) { json in
            json["grid_size"] = 32
            json["total_steps"] = 20
            json["record_every_steps"] = 5
            json["repeats"] = 1
            json["mutation_probabilities"] = [0.01]
            json["variants"] = ["vanilla"]
            json["activity"] = [
                "enabled": true,
                "interval": 5,
                "threshold": 0.05,
                "maxComponents": 64,
                "matchThreshold": 1.5,
                "paramWeight": 1.0,
                "positionWeight": 0.05,
            ]
        }

        try rewriteJSONFile(at: configDirectory.appendingPathComponent("vanilla.json")) { json in
            json["init_patch_count"] = 4
            json["init_patch_size"] = 4
            json["init_param_mean"] = 0.0
            json["init_param_std"] = 1.0
        }

        let bundle = try loadFlowLeniaEcology2025ConfigBundle(
            configDirectory: configDirectory,
            strictPaperInvariants: false
        )
        let runner = FlowLeniaEcology2025Runner(
            configs: bundle,
            logger: Logger(label: "CompendiumIndexingTests.Ecology")
        )
        _ = try runner.run(outputDirectory: runDir)

        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        var command = try IndexCommand.parseAsRoot([
            "--run-dir", runDir.path,
            "--db", dbPath,
            "--rebuild",
        ])
        try command.run()

        let db = try SQLiteDB(path: dbPath)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM ecology_runs"), 1)
        let stmt = try db.prepare("SELECT variant, bundle_kind, final_mass FROM ecology_runs LIMIT 1")
        defer { sqlite3_finalize(stmt) }
        XCTAssertEqual(sqlite3_step(stmt), SQLITE_ROW)
        XCTAssertEqual(String(cString: sqlite3_column_text(stmt, 0)), "vanilla")
        XCTAssertEqual(String(cString: sqlite3_column_text(stmt, 1)), LeniaArtifactBundleKind.flowLeniaEcology2025ArenaReplayBundleV1.rawValue)
        XCTAssertGreaterThan(sqlite3_column_double(stmt, 2), 0)
    }

    func testIndexCreatesCurrentSchemaAndMorphometrics() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-cli-tests-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let runDir = root.appendingPathComponent("run-001", isDirectory: true)
        try makeRunLayout(at: runDir)

        let seed = 42
        try writeJSONL([
            testLibraryEntry(
                creature: makeCreature(id: UUID(uuidString: "11111111-1111-1111-1111-111111111111")!, name: "test-creature", seed: seed),
                campaign_id: nil,
                run_id: "run-001",
                recorded_at: fixedDate
            ),
        ], to: runDir.appendingPathComponent("library/index.jsonl"))

        try writeJSONL([
            makeActivityRecord(seed: seed, speciesCount: [1, 3, 2]),
        ], to: runDir.appendingPathComponent("overall/activity.jsonl"))

        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        var command = try IndexCommand.parseAsRoot([
            "--run-dir", runDir.path,
            "--db", dbPath,
            "--rebuild",
        ])
        try command.run()

        let db = try SQLiteDB(path: dbPath)
        let schema = try db.scalarInt("SELECT schema_version FROM compendium_meta LIMIT 1")
        XCTAssertEqual(schema, compendiumSchemaVersion)

        let creatureCols = try db.tableColumns("creatures")
        let runCols = try db.tableColumns("runs")
        XCTAssertTrue(runCols.contains("source_mode"))
        XCTAssertTrue(runCols.contains("source_algorithm"))
        XCTAssertTrue(creatureCols.contains("velocity_x"))
        XCTAssertTrue(creatureCols.contains("velocity_y"))
        XCTAssertTrue(creatureCols.contains("heading_rad"))
        XCTAssertTrue(creatureCols.contains("taxonomy_family_id"))
        XCTAssertTrue(creatureCols.contains("morphometrics_json"))
        XCTAssertTrue(creatureCols.contains("source_mode"))
        XCTAssertTrue(creatureCols.contains("source_algorithm"))
        XCTAssertTrue(creatureCols.contains("research_metadata_json"))
        XCTAssertTrue(creatureCols.contains("catalog_status"))
        XCTAssertTrue(creatureCols.contains("quality_flags_json"))

        let motionStmt = try db.prepare("SELECT velocity_x, velocity_y, heading_rad FROM creatures LIMIT 1")
        defer { sqlite3_finalize(motionStmt) }
        XCTAssertEqual(sqlite3_step(motionStmt), SQLITE_ROW)
        XCTAssertEqual(sqlite3_column_double(motionStmt, 0), 0.012, accuracy: 1e-6)
        XCTAssertEqual(sqlite3_column_double(motionStmt, 1), -0.004, accuracy: 1e-6)
        XCTAssertEqual(sqlite3_column_double(motionStmt, 2), -0.32175055, accuracy: 1e-6)

        let morphStmt = try db.prepare("SELECT morphometrics_json FROM creatures LIMIT 1")
        defer { sqlite3_finalize(morphStmt) }
        XCTAssertEqual(sqlite3_step(morphStmt), SQLITE_ROW)
        guard let morphC = sqlite3_column_text(morphStmt, 0) else {
            XCTFail("morphometrics_json is NULL")
            return
        }
        let morphRaw = String(cString: morphC)
        let morph = try JSONDecoder().decode(Morphometrics.self, from: Data(morphRaw.utf8))

        XCTAssertEqual(morph.pathTortuosity ?? -1, 5, accuracy: 1e-6)
        XCTAssertEqual(morph.activitySpeciesMax, 3)
    }

    func testIndexKeepsCampaignsAndExportsScopedPerRun() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-cli-multi-run-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let outputRoot = root.appendingPathComponent("output-root", isDirectory: true)
        let runA = outputRoot.appendingPathComponent("hosts/host-a/runs/run-001", isDirectory: true)
        let runB = outputRoot.appendingPathComponent("hosts/host-b/runs/run-001", isDirectory: true)
        try makeRunLayout(at: runA)
        try makeRunLayout(at: runB)

        try writeJSONL([
            testLibraryEntry(
                creature: makeCreature(id: UUID(uuidString: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")!, name: "alpha-run-a", seed: 7),
                campaign_id: "campaign-001",
                run_id: "run-001",
                recorded_at: fixedDate
            ),
        ], to: runA.appendingPathComponent("library/index.jsonl"))

        try writeJSONL([
            testLibraryEntry(
                creature: makeCreature(id: UUID(uuidString: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")!, name: "alpha-run-b", seed: 8),
                campaign_id: "campaign-001",
                run_id: "run-001",
                recorded_at: fixedDate
            ),
        ], to: runB.appendingPathComponent("library/index.jsonl"))

        try writeJSONL([
            makeExportRecord(
                creatureId: UUID(uuidString: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")!,
                runId: "run-001",
                campaignId: "campaign-001",
                exportDir: runA.appendingPathComponent("exports/shared").path
            ),
        ], to: runA.appendingPathComponent("exports/index.jsonl"))

        try writeJSONL([
            makeExportRecord(
                creatureId: UUID(uuidString: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")!,
                runId: "run-001",
                campaignId: "campaign-001",
                exportDir: runB.appendingPathComponent("exports/shared").path
            ),
        ], to: runB.appendingPathComponent("exports/index.jsonl"))

        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        var command = try IndexCommand.parseAsRoot([
            "--output-root", outputRoot.path,
            "--db", dbPath,
            "--rebuild",
        ])
        try command.run()

        let db = try SQLiteDB(path: dbPath)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM campaigns"), 2)
        XCTAssertEqual(
            try db.scalarInt("SELECT COUNT(DISTINCT run_id) FROM campaigns WHERE campaign_id = 'campaign-001'"),
            2
        )
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM exports"), 2)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM exports WHERE export_dir = 'exports/shared'"), 2)

        let exportCols = try db.tableColumns("exports")
        XCTAssertTrue(exportCols.contains("id"))
    }

    func testReplayExportWriterProducesIndexableBundle() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-cli-export-bundle-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let runDir = root.appendingPathComponent("run-001", isDirectory: true)
        try makeRunLayout(at: runDir)

        let creature = makeCreature(
            id: UUID(uuidString: "abababab-abab-abab-abab-abababababab")!,
            name: "indexable-export",
            seed: 23
        )
        try writeJSONL([
            testLibraryEntry(
                creature: creature,
                campaign_id: nil,
                run_id: "run-001",
                recorded_at: fixedDate
            ),
        ], to: runDir.appendingPathComponent("library/index.jsonl"))

        let configsDir = leniaCLIPackageRoot.appendingPathComponent("configs/base", isDirectory: true)
        let baseConfig = try JSONDecoder().decode(
            LeniaBaseConfig.self,
            from: Data(contentsOf: configsDir.appendingPathComponent("paper_base_1c_128.json"))
        )
        let searchConfig = try JSONDecoder().decode(
            ParsedSearchConfig.self,
            from: Data(contentsOf: configsDir.appendingPathComponent("paper_search_random.json"))
        )
        let exportRoot = runDir.appendingPathComponent("exports", isDirectory: true)
        let artifacts = try XCTUnwrap(writeReplayExportArtifacts(
            exportRoot: exportRoot,
            baseConfig: baseConfig,
            searchConfig: searchConfig,
            creature: creature,
            runId: "run-001",
            campaignId: nil,
            score: creature.score,
            filtersPassed: true,
            reason: "test"
        ))

        XCTAssertEqual(artifacts.record.bundleKind, .strictReplayBundleV1)
        XCTAssertTrue(fm.fileExists(atPath: try XCTUnwrap(artifacts.baseConfigURL).path))
        XCTAssertTrue(fm.fileExists(atPath: try XCTUnwrap(artifacts.searchConfigURL).path))
        XCTAssertTrue(fm.fileExists(atPath: artifacts.metadataURL.path))

        try writeJSONL([artifacts.record], to: exportRoot.appendingPathComponent("index.jsonl"))

        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        var command = try IndexCommand.parseAsRoot([
            "--run-dir", runDir.path,
            "--db", dbPath,
            "--rebuild",
        ])
        try command.run()

        let db = try SQLiteDB(path: dbPath)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM creatures"), 1)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM exports"), 1)

        let exportStmt = try db.prepare("SELECT export_dir, base_config_path, search_config_path FROM exports LIMIT 1")
        defer { sqlite3_finalize(exportStmt) }
        XCTAssertEqual(sqlite3_step(exportStmt), SQLITE_ROW)

        let exportDir = String(cString: sqlite3_column_text(exportStmt, 0))
        let basePath = String(cString: sqlite3_column_text(exportStmt, 1))
        let searchPath = String(cString: sqlite3_column_text(exportStmt, 2))
        let expectedDir = "exports/\(artifacts.exportDir.lastPathComponent)"
        XCTAssertEqual(exportDir, expectedDir)
        XCTAssertEqual(basePath, "\(expectedDir)/base.json")
        XCTAssertEqual(searchPath, "\(expectedDir)/search.json")
    }

    func testReplaySpecimensCommandReplaysExportBundleIntoCampaignRun() async throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-cli-replay-batch-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let sourceRunDir = root.appendingPathComponent("source-run", isDirectory: true)
        try makeRunLayout(at: sourceRunDir)

        let configsDir = leniaCLIPackageRoot.appendingPathComponent("configs/base", isDirectory: true)
        let baseConfig = try JSONDecoder().decode(
            LeniaBaseConfig.self,
            from: Data(contentsOf: configsDir.appendingPathComponent("paper_base_1c_128.json"))
        )
        let searchConfig = try JSONDecoder().decode(
            ParsedSearchConfig.self,
            from: Data(contentsOf: configsDir.appendingPathComponent("paper_search_random.json"))
        )
        let runtimeConfig = try loadRuntimeConfig(from: Data(contentsOf: configsDir.appendingPathComponent("paper_base_1c_128.json")))
        let creature = SavedCreature(
            id: UUID(uuidString: "cdcdcdcd-cdcd-cdcd-cdcd-cdcdcdcdcdcd")!,
            name: "replayable-export",
            ownerId: "tester",
            genotype: runtimeConfig.params.toKernelParams(),
            initialCondition: InitConfig(
                seed: runtimeConfig.initSeed,
                patches: runtimeConfig.patches,
                a_uniform: runtimeConfig.aUniform,
                p_uniform: runtimeConfig.pUniform
            ),
            metrics: SimulationMetrics(
                massMean: 1,
                massStd: 0.1,
                massMin: 0,
                massMax: 2,
                occupancyMean: 0.2,
                varianceMean: 0.01,
                energyMean: 0.3,
                speedMean: 0.4,
                pathLength: 10,
                displacement: 2,
                sampleCount: 2,
                speedCount: 1,
                gyration: 3,
                centerVelocity: 0.5,
                velocityX: 0.012,
                velocityY: -0.004,
                headingRad: -0.32175055,
                isStable: true
            ),
            score: 0.99,
            scoreWeights: ["mass_mean": 1.0]
        )
        let exportRoot = sourceRunDir.appendingPathComponent("exports", isDirectory: true)
        let artifacts = try XCTUnwrap(writeReplayExportArtifacts(
            exportRoot: exportRoot,
            baseConfig: baseConfig,
            searchConfig: searchConfig,
            creature: creature,
            runId: "source-run",
            campaignId: nil,
            score: creature.score,
            filtersPassed: true,
            reason: "test"
        ))
        try writeJSONL([artifacts.record], to: exportRoot.appendingPathComponent("index.jsonl"))

        let replayOutput = root.appendingPathComponent("replay-output", isDirectory: true)
        let dbPath = root.appendingPathComponent("replay-compendium.sqlite").path
        _ = try runLeniaCLI(arguments: [
            "publish",
            "replay",
            "--input", exportRoot.appendingPathComponent("index.jsonl").path,
            "--output", replayOutput.path,
            "--run-id", "test-replay-batch",
            "--db", dbPath,
        ])

        let campaignsDir = replayOutput.appendingPathComponent("campaigns", isDirectory: true)
        let campaigns = try fm.contentsOfDirectory(
            at: campaignsDir,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: .skipsHiddenFiles
        ).filter(\.hasDirectoryPath)
        XCTAssertEqual(campaigns.count, 1)

        let specimenDir = try XCTUnwrap(campaigns.first)
        XCTAssertTrue(fm.fileExists(atPath: specimenDir.appendingPathComponent("config.json").path))
        XCTAssertTrue(fm.fileExists(atPath: specimenDir.appendingPathComponent("search.json").path))
        XCTAssertTrue(fm.fileExists(atPath: specimenDir.appendingPathComponent("results.jsonl").path))
        XCTAssertTrue(fm.fileExists(atPath: specimenDir.appendingPathComponent("library/index.jsonl").path))
        XCTAssertTrue(fm.fileExists(atPath: specimenDir.appendingPathComponent("replay-manifest.json").path))
        XCTAssertTrue(fm.fileExists(atPath: replayOutput.appendingPathComponent("summary.json").path))

        let result = try decodeSingleJSONL(
            SimulationResultData.self,
            from: specimenDir.appendingPathComponent("results.jsonl")
        )
        XCTAssertNotNil(result.initialConditionFamily)
        XCTAssertNotNil(result.descriptorBundle)

        let entry = try decodeSingleJSONL(
            ResearchLibraryEntry.self,
            from: specimenDir.appendingPathComponent("library/index.jsonl")
        )
        XCTAssertEqual(entry.sourceMode, "replay")
        XCTAssertEqual(entry.sourceAlgorithm, "canonical-replay")
        XCTAssertEqual(entry.creature.name, creature.name)
        XCTAssertNotEqual(entry.creature.id, creature.id)
        XCTAssertEqual(entry.researchMetadata?["source_kind"]?.value as? String, "export_index")

        let db = try SQLiteDB(path: dbPath)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM creatures"), 1)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM results"), 1)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM specimens"), 1)
        XCTAssertEqual(
            try db.scalarInt("SELECT COUNT(*) FROM specimens WHERE source_kind = 'result'"),
            1
        )
        XCTAssertEqual(
            try db.scalarInt("SELECT COUNT(*) FROM specimens WHERE source_kind = 'library'"),
            0
        )
    }

    func testOverallActivityUpdatesOnlyOverallCreatures() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-cli-activity-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let runDir = root.appendingPathComponent("run-001", isDirectory: true)
        try makeRunLayout(at: runDir)

        let seed = 17
        try writeJSONL([
            testLibraryEntry(
                creature: makeCreature(id: UUID(uuidString: "cccccccc-cccc-cccc-cccc-cccccccccccc")!, name: "overall", seed: seed),
                campaign_id: nil,
                run_id: "run-001",
                recorded_at: fixedDate
            ),
            testLibraryEntry(
                creature: makeCreature(id: UUID(uuidString: "dddddddd-dddd-dddd-dddd-dddddddddddd")!, name: "campaign", seed: seed),
                campaign_id: "campaign-001",
                run_id: "run-001",
                recorded_at: fixedDate
            ),
        ], to: runDir.appendingPathComponent("library/index.jsonl"))

        try writeJSONL([
            makeActivityRecord(seed: seed, speciesCount: [2, 4, 1]),
        ], to: runDir.appendingPathComponent("overall/activity.jsonl"))

        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        var command = try IndexCommand.parseAsRoot([
            "--run-dir", runDir.path,
            "--db", dbPath,
            "--rebuild",
        ])
        try command.run()

        let db = try SQLiteDB(path: dbPath)
        let stmt = try db.prepare("""
            SELECT campaign_id, morphometrics_json
            FROM creatures
            ORDER BY campaign_id IS NOT NULL, COALESCE(campaign_id, '')
        """)
        defer { sqlite3_finalize(stmt) }

        var rows: [(String?, Morphometrics)] = []
        while sqlite3_step(stmt) == SQLITE_ROW {
            let campaignId = sqlite3_column_text(stmt, 0).map { String(cString: $0) }
            guard let morphC = sqlite3_column_text(stmt, 1) else {
                XCTFail("morphometrics_json is NULL")
                return
            }
            let morph = try JSONDecoder().decode(Morphometrics.self, from: Data(String(cString: morphC).utf8))
            rows.append((campaignId, morph))
        }

        XCTAssertEqual(rows.count, 2)
        XCTAssertNil(rows[0].0)
        XCTAssertEqual(rows[0].1.activitySpeciesMax, 4)
        XCTAssertEqual(rows[1].0, "campaign-001")
        XCTAssertNil(rows[1].1.activitySpeciesMax)
    }

    func testIncrementalIngestResetsWhenLibraryIndexIsRewrittenWithSameSize() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-cli-rewrite-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let runDir = root.appendingPathComponent("run-001", isDirectory: true)
        try makeRunLayout(at: runDir)

        let creatureId = UUID(uuidString: "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")!
        let originalEntry = testLibraryEntry(
            creature: makeCreature(id: creatureId, name: "alpha", seed: 99),
            campaign_id: nil,
            run_id: "run-001",
            recorded_at: fixedDate
        )
        let originalLine = try jsonlLine(originalEntry)
        var rewrittenName = "bravo"
        var rewrittenEntry = testLibraryEntry(
            creature: makeCreature(id: creatureId, name: rewrittenName, seed: 99),
            campaign_id: nil,
            run_id: "run-001",
            recorded_at: fixedDate
        )
        var rewrittenLine = try jsonlLine(rewrittenEntry)
        let lineDelta = originalLine.utf8.count - rewrittenLine.utf8.count
        if lineDelta != 0 {
            if lineDelta > 0 {
                rewrittenName += String(repeating: "x", count: lineDelta)
            } else {
                rewrittenName = String(rewrittenName.dropLast(-lineDelta))
            }
            rewrittenEntry = testLibraryEntry(
                creature: makeCreature(id: creatureId, name: rewrittenName, seed: 99),
                campaign_id: nil,
                run_id: "run-001",
                recorded_at: fixedDate
            )
            rewrittenLine = try jsonlLine(rewrittenEntry)
        }
        let paddedSize = max(originalLine.utf8.count, rewrittenLine.utf8.count)
        let originalPaddedLine = padJSONLLine(originalLine, toUTF8Count: paddedSize)
        let rewrittenPaddedLine = padJSONLLine(rewrittenLine, toUTF8Count: paddedSize)
        XCTAssertEqual(originalPaddedLine.utf8.count, rewrittenPaddedLine.utf8.count)

        let libraryPath = runDir.appendingPathComponent("library/index.jsonl")
        try originalPaddedLine.write(to: libraryPath, atomically: true, encoding: .utf8)
        try fm.setAttributes([.modificationDate: Date(timeIntervalSince1970: 1_700_000_000)], ofItemAtPath: libraryPath.path)

        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        var command = try IndexCommand.parseAsRoot([
            "--run-dir", runDir.path,
            "--db", dbPath,
            "--rebuild",
        ])
        try command.run()

        try rewrittenPaddedLine.write(to: libraryPath, atomically: true, encoding: .utf8)
        try fm.setAttributes([.modificationDate: Date(timeIntervalSince1970: 1_700_000_100)], ofItemAtPath: libraryPath.path)

        command = try IndexCommand.parseAsRoot([
            "--run-dir", runDir.path,
            "--db", dbPath,
        ])
        try command.run()

        let db = try SQLiteDB(path: dbPath)
        let stmt = try db.prepare("SELECT name FROM creatures WHERE id = ?")
        defer { sqlite3_finalize(stmt) }
        db.bindText(stmt, index: 1, value: creatureId.uuidString)
        XCTAssertEqual(sqlite3_step(stmt), SQLITE_ROW)
        XCTAssertEqual(String(cString: sqlite3_column_text(stmt, 0)!), rewrittenName)
    }

    func testIndexRejectsCompendiumWithOtherSchemaVersion() throws {
        let root = try makeTempDirectory(prefix: "lenia-compendium-schema-mismatch")
        defer { try? FileManager.default.removeItem(at: root) }
        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        _ = try SQLiteIndexer(path: dbPath, rebuild: false)
        try SQLiteDB(path: dbPath).exec("UPDATE compendium_meta SET schema_version = \(compendiumSchemaVersion - 1)")

        XCTAssertThrowsError(try SQLiteIndexer(path: dbPath, rebuild: false))
        XCTAssertNoThrow(try SQLiteIndexer(path: dbPath, rebuild: true))
    }

    func testCanonicalCoverageRepairClonesDuplicateResultLinksPerCreature() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-cli-duplicate-canonical-links-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }
        try fm.createDirectory(at: root, withIntermediateDirectories: true)

        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        _ = try SQLiteIndexer(path: dbPath, rebuild: false)

        let db = try SQLiteDB(path: dbPath)
        let runID = "replay"
        let campaignID = "0001-qd-me-cell-23-79b16b7f"
        try db.exec("""
            INSERT INTO runs (
                run_id, run_name, host_id, output_root, run_dir, indexed_at, config_hash, source_mode, source_algorithm
            ) VALUES (
                '\(runID)', '\(runID)', NULL, NULL, 'runs/\(runID)', '2026-03-12T00:00:00Z', 'cfg-dup', 'replay', 'paper-replay'
            )
        """)

        let creatures = [
            makeMorphospaceReadyCreature(
                id: UUID(uuidString: "81A8B0F9-8047-5C99-8112-FF9587CF7F77")!,
                name: "qd-me-cell-23",
                seed: 23,
                isStable: true,
                fingerprintByte: 0x21
            ),
            makeMorphospaceReadyCreature(
                id: UUID(uuidString: "8A4409F0-CAD6-5026-B814-E38BEBD6838F")!,
                name: "qd-me-cell-23",
                seed: 23,
                isStable: true,
                fingerprintByte: 0x22
            ),
            makeMorphospaceReadyCreature(
                id: UUID(uuidString: "5F6C86D4-0D89-5EB8-924E-BB56F1D31D86")!,
                name: "qd-me-cell-23",
                seed: 23,
                isStable: true,
                fingerprintByte: 0x23
            ),
        ]
        for creature in creatures {
            try insertCreatureRow(creature, runId: runID, db: db)
            try db.exec("""
                UPDATE creatures
                SET campaign_id = '\(campaignID)',
                    source_mode = 'replay',
                    source_algorithm = 'paper-replay',
                    research_metadata_json = '{"mode":"replay","algorithm":"paper-replay"}',
                    runtime_family = 'flow_lenia',
                    runtime_capabilities_json = '["replay","warehouse_ingest"]',
                    canonical_specimen_id = 'result:\(runID)|\(campaignID)|23'
                WHERE id = '\(creature.id.uuidString)'
            """)
        }

        let encoder = JSONEncoder()
        let sourceCreature = try XCTUnwrap(creatures.first)
        let descriptorBundle = try XCTUnwrap(sourceCreature.descriptorBundle)
        let manifest = buildLibrarySpecimenManifest(
            creature: sourceCreature,
            campaignID: campaignID,
            runID: runID,
            recordedAt: fixedDate,
            configHash: "cfg-dup",
            sourceMode: "replay",
            sourceAlgorithm: "paper-replay",
            researchMetadata: ["mode": AnyCodable("replay")],
            morphometrics: Morphometrics.from(metrics: sourceCreature.metrics, activity: nil)
        )
        let genotypeDescriptorJSON = String(data: try encoder.encode(descriptorBundle.genotype), encoding: .utf8)!
        let terminalDescriptorJSON = String(data: try encoder.encode(descriptorBundle.terminal), encoding: .utf8)!
        let trajectoryDescriptorJSON = String(data: try encoder.encode(descriptorBundle.trajectory), encoding: .utf8)!
        let manifestJSON = String(data: try encoder.encode(manifest), encoding: .utf8)!
        try db.exec("""
            INSERT INTO specimens (
                id, result_id, creature_id, run_id, campaign_id, source_kind, recorded_at, seed, init_seed,
                source_mode, source_algorithm, config_hash, initial_condition_family, descriptor_version,
                symmetry_policy, genotype_descriptor_json, terminal_descriptor_json, trajectory_descriptor_json,
                activity_path, fingerprint_path, provenance_json, runtime_family, runtime_capabilities_json, specimen_manifest_json
            ) VALUES (
                'result:\(runID)|\(campaignID)|23', 'result:\(runID)|\(campaignID)|23', NULL, '\(runID)', '\(campaignID)', 'result',
                '2026-03-12T00:00:00Z', 23, 23, 'replay', 'paper-replay', 'cfg-dup', 'centered_patch',
                \(descriptorBundle.descriptorVersion), 'translation_kernel_permutation_v1',
                '\(genotypeDescriptorJSON.replacingOccurrences(of: "'", with: "''"))',
                '\(terminalDescriptorJSON.replacingOccurrences(of: "'", with: "''"))',
                '\(trajectoryDescriptorJSON.replacingOccurrences(of: "'", with: "''"))',
                NULL, NULL, '{"sourceKind":"result","sourceRef":"result:\(runID)|\(campaignID)|23"}',
                'flow_lenia', '["replay","warehouse_ingest"]',
                '\(manifestJSON.replacingOccurrences(of: "'", with: "''"))'
            )
        """)

        let indexer = try SQLiteIndexer(path: dbPath, rebuild: false)
        try indexer.ensureCanonicalSpecimenCoverage()

        XCTAssertEqual(
            try db.scalarInt("""
                SELECT COUNT(*)
                FROM (
                    SELECT canonical_specimen_id
                    FROM creatures
                    GROUP BY canonical_specimen_id
                    HAVING COUNT(*) > 1
                )
            """),
            0
        )
        XCTAssertEqual(
            try db.scalarInt("""
                SELECT COUNT(*)
                FROM creatures c
                LEFT JOIN specimens s ON s.id = c.canonical_specimen_id
                WHERE s.id IS NULL
            """),
            0
        )
        XCTAssertEqual(
            try db.scalarInt("SELECT COUNT(*) FROM specimens WHERE id LIKE 'creature:%'"),
            creatures.count
        )
        XCTAssertEqual(
            try db.scalarInt("SELECT COUNT(*) FROM specimens WHERE id LIKE 'creature:%' AND result_id IS NOT NULL"),
            0
        )
        XCTAssertEqual(
            try db.scalarInt("SELECT COUNT(*) FROM specimens WHERE id = 'result:\(runID)|\(campaignID)|23'"),
            1
        )
    }

    func testIndexIngestsResearchLibraryEntryWithProvenance() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-cli-research-entry-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let runDir = root.appendingPathComponent("run-001", isDirectory: true)
        try makeRunLayout(at: runDir)

        let entry = ResearchLibraryEntry(
            creature: makeCreature(
                id: UUID(uuidString: "12121212-3434-5656-7878-909090909090")!,
                name: "qd-me-cell-1",
                seed: 12
            ),
            campaignId: nil,
            runId: "run-001",
            recordedAt: fixedDate,
            configHash: "cfg-qd-001",
            sourceMode: "qd-2024",
            sourceAlgorithm: "me",
            researchMetadata: [
                "version": AnyCodable(1),
                "mode": AnyCodable("qd-2024"),
                "algorithm": AnyCodable("me"),
                "generation": AnyCodable(3),
                "cell": AnyCodable(1),
                "descriptor": AnyCodable([0.2, 0.4]),
                "centroid": AnyCodable([0.25, 0.5]),
                "fitness": AnyCodable(-0.1),
            ]
        )
        _ = try ResearchLibraryWriter.write(entries: [entry], runDirectory: runDir)

        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        var command = try IndexCommand.parseAsRoot([
            "--run-dir", runDir.path,
            "--db", dbPath,
            "--rebuild",
        ])
        try command.run()

        let db = try SQLiteDB(path: dbPath)
        let creatureStmt = try db.prepare("""
            SELECT source_mode, source_algorithm, research_metadata_json, config_hash
            FROM creatures LIMIT 1
        """)
        defer { sqlite3_finalize(creatureStmt) }
        XCTAssertEqual(sqlite3_step(creatureStmt), SQLITE_ROW)
        XCTAssertEqual(sqliteText(creatureStmt, 0), "qd-2024")
        XCTAssertEqual(sqliteText(creatureStmt, 1), "me")
        XCTAssertEqual(sqliteText(creatureStmt, 3), "cfg-qd-001")
        let researchMetadata = try XCTUnwrap(sqliteOptionalText(creatureStmt, 2))
        XCTAssertTrue(researchMetadata.contains("\"mode\":\"qd-2024\""))
        XCTAssertTrue(researchMetadata.contains("\"algorithm\":\"me\""))

        let runStmt = try db.prepare("""
            SELECT source_mode, source_algorithm, config_hash
            FROM runs WHERE run_id = 'run-001'
        """)
        defer { sqlite3_finalize(runStmt) }
        XCTAssertEqual(sqlite3_step(runStmt), SQLITE_ROW)
        XCTAssertEqual(sqliteText(runStmt, 0), "qd-2024")
        XCTAssertEqual(sqliteText(runStmt, 1), "me")
        XCTAssertEqual(sqliteText(runStmt, 2), "cfg-qd-001")
    }

    func testQD2024LocalRunEmitsIndexableLibraryEntries() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-cli-qd-local-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let configDirectory = root.appendingPathComponent("configs", isDirectory: true)
        let runDir = root.appendingPathComponent("test-qd-me", isDirectory: true)
        try makeTinyLeniaBreederConfigDirectory(at: configDirectory)
        try fm.createDirectory(at: runDir, withIntermediateDirectories: true)

        let bundle = try loadLeniaBreeder2024ConfigBundle(configDirectory: configDirectory)
        let runner = LeniaBreeder2024Runner(
            configs: bundle,
            logger: Logger(label: "CompendiumIndexingTests.QDLocal"),
            seed: 7
        )
        let summary = try runner.runMAPElites(outputDirectory: runDir, runId: "test-qd-me")
        XCTAssertEqual(summary.algorithm, "me")

        let libraryURL = runDir.appendingPathComponent("library/index.jsonl")
        XCTAssertTrue(fm.fileExists(atPath: libraryURL.path))
        XCTAssertGreaterThan(try countJSONLLines(at: libraryURL), 0)
        let exportsURL = runDir.appendingPathComponent("exports/index.jsonl")
        XCTAssertTrue(fm.fileExists(atPath: exportsURL.path))
        XCTAssertGreaterThan(try countJSONLLines(at: exportsURL), 0)
        let exportRecord = try decodeSingleJSONL(CreatureExportRecord.self, from: exportsURL)
        XCTAssertEqual(exportRecord.bundleKind, .qd24PaperReplayBundleV1)
        XCTAssertNil(exportRecord.baseConfigPath)
        XCTAssertNil(exportRecord.searchConfigPath)
        let payloadPath = try XCTUnwrap(exportRecord.payloadPath)
        XCTAssertTrue(fm.fileExists(atPath: payloadPath))
        let replayPayload = try JSONDecoder().decode(
            LeniaBreeder2024ReplayPayload.self,
            from: Data(contentsOf: URL(fileURLWithPath: payloadPath))
        )
        XCTAssertEqual(replayPayload.algorithm, "me")
        XCTAssertGreaterThanOrEqual(replayPayload.elite.cell, 0)
        XCTAssertFalse(replayPayload.elite.genotype.isEmpty)
        let exportMeta = try JSONDecoder().decode(
            CreatureExportMetadata.self,
            from: Data(contentsOf: URL(fileURLWithPath: exportRecord.exportDir).appendingPathComponent("meta.json"))
        )
        XCTAssertEqual(exportMeta.bundleKind, .qd24PaperReplayBundleV1)
        XCTAssertNotNil(exportMeta.creature.initialCondition.state_patch)

        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        var command = try IndexCommand.parseAsRoot([
            "--run-dir", runDir.path,
            "--db", dbPath,
            "--rebuild",
        ])
        try command.run()

        let db = try SQLiteDB(path: dbPath)
        XCTAssertGreaterThan(try db.scalarInt("SELECT COUNT(*) FROM creatures"), 0)
        let stmt = try db.prepare("""
            SELECT source_mode, source_algorithm, research_metadata_json
            FROM creatures ORDER BY id LIMIT 1
        """)
        defer { sqlite3_finalize(stmt) }
        XCTAssertEqual(sqlite3_step(stmt), SQLITE_ROW)
        XCTAssertEqual(sqliteText(stmt, 0), "qd-2024")
        XCTAssertEqual(sqliteText(stmt, 1), "me")
        let metadata = try XCTUnwrap(sqliteOptionalText(stmt, 2))
        XCTAssertTrue(metadata.contains("\"mode\":\"qd-2024\""))
        XCTAssertTrue(metadata.contains("\"cell\":"))
        XCTAssertTrue(metadata.contains("\"canonical_export_available\":true"))
    }

    func testQD2024DistributedRunEmitsIndexableLibraryEntries() async throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-cli-qd-distributed-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let configDirectory = root.appendingPathComponent("configs", isDirectory: true)
        let runDir = root.appendingPathComponent("test-qd-me-distributed", isDirectory: true)
        try makeTinyLeniaBreederConfigDirectory(at: configDirectory, distributed: true)
        try fm.createDirectory(at: runDir, withIntermediateDirectories: true)

        let bundle = try loadLeniaBreeder2024ConfigBundle(configDirectory: configDirectory)
        let runner = LeniaBreeder2024Runner(
            configs: bundle,
            logger: Logger(label: "CompendiumIndexingTests.QDDistributed"),
            seed: 11
        )

        let system = await ClusterSystem("LeniaCLITestsQD") { settings in
            settings.swim.probeInterval = .seconds(1)
            settings.swim.pingTimeout = .milliseconds(500)
            settings.remoteCall.defaultTimeout = .seconds(60)
        }
        let controller = LeniaBreeder2024DistributedController(
            system: system,
            logger: Logger(label: "CompendiumIndexingTests.QDDistributed.Controller"),
            runContext: RunContext(runId: "test-qd-me-distributed", controllerId: "test-controller")
        )
        let worker = LeniaWorker(actorSystem: system, workerId: "worker-test")

        do {
            async let startTask: Void = controller.start(minCount: 1)
            await system.receptionist.checkIn(worker, with: .leniaWorkers)
            _ = try await startTask

            let summary = try await runner.runDistributedMAPElites(
                outputDirectory: runDir,
                controller: controller,
                runId: "test-qd-me-distributed",
                controllerId: "test-controller",
                minWorkers: 1
            )
            XCTAssertEqual(summary.algorithm, "me-distributed")
        } catch {
            _ = try? system.shutdown()
            throw error
        }
        try system.shutdown()

        let libraryURL = runDir.appendingPathComponent("library/index.jsonl")
        XCTAssertTrue(fm.fileExists(atPath: libraryURL.path))
        XCTAssertGreaterThan(try countJSONLLines(at: libraryURL), 0)
        let exportsURL = runDir.appendingPathComponent("exports/index.jsonl")
        XCTAssertTrue(fm.fileExists(atPath: exportsURL.path))
        XCTAssertGreaterThan(try countJSONLLines(at: exportsURL), 0)

        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        var command = try IndexCommand.parseAsRoot([
            "--run-dir", runDir.path,
            "--db", dbPath,
            "--rebuild",
        ])
        try command.run()

        let db = try SQLiteDB(path: dbPath)
        let stmt = try db.prepare("""
            SELECT source_mode, source_algorithm, research_metadata_json
            FROM creatures ORDER BY id LIMIT 1
        """)
        defer { sqlite3_finalize(stmt) }
        XCTAssertEqual(sqlite3_step(stmt), SQLITE_ROW)
        XCTAssertEqual(sqliteText(stmt, 0), "qd-2024")
        XCTAssertEqual(sqliteText(stmt, 1), "me")
        let metadata = try XCTUnwrap(sqliteOptionalText(stmt, 2))
        XCTAssertTrue(metadata.contains("\"distributed\":true"))
        XCTAssertTrue(metadata.contains("\"canonical_export_available\":true"))
    }

    func testQD2024ExportIndexLoadsSeedPatches() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-cli-qd-export-seeds-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let configDirectory = root.appendingPathComponent("configs", isDirectory: true)
        let runDir = root.appendingPathComponent("test-qd-me", isDirectory: true)
        try makeTinyLeniaBreederConfigDirectory(at: configDirectory)
        try fm.createDirectory(at: runDir, withIntermediateDirectories: true)

        let bundle = try loadLeniaBreeder2024ConfigBundle(configDirectory: configDirectory)
        let runner = LeniaBreeder2024Runner(
            configs: bundle,
            logger: Logger(label: "CompendiumIndexingTests.QDExportSeeds"),
            seed: 7
        )
        _ = try runner.runMAPElites(outputDirectory: runDir, runId: "test-qd-me")

        let patches = try loadResearchSeedPatches(
            libraryURL: runDir.appendingPathComponent("exports/index.jsonl")
        )
        XCTAssertFalse(patches.isEmpty)
        XCTAssertGreaterThan(patches[0].world.width, 0)
        XCTAssertGreaterThan(patches[0].world.height, 0)
        XCTAssertGreaterThan(patches[0].world.channels, 0)
    }

    func testQD2024ReplaySpecimensCommandReplaysCanonicalExport() async throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-cli-qd-replay-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let configDirectory = root.appendingPathComponent("configs", isDirectory: true)
        let runDir = root.appendingPathComponent("test-qd-me", isDirectory: true)
        let replayInputDir = root.appendingPathComponent("replay-input", isDirectory: true)
        let replayOutput = root.appendingPathComponent("replay-output", isDirectory: true)
        try makeTinyLeniaBreederConfigDirectory(at: configDirectory)
        try fm.createDirectory(at: runDir, withIntermediateDirectories: true)
        try fm.createDirectory(at: replayInputDir, withIntermediateDirectories: true)

        let bundle = try loadLeniaBreeder2024ConfigBundle(configDirectory: configDirectory)
        let runner = LeniaBreeder2024Runner(
            configs: bundle,
            logger: Logger(label: "CompendiumIndexingTests.QDReplay"),
            seed: 13
        )
        _ = try runner.runMAPElites(outputDirectory: runDir, runId: "test-qd-me")

        let exportsURL = runDir.appendingPathComponent("exports/index.jsonl")
        let exportRecord = try decodeSingleJSONL(CreatureExportRecord.self, from: exportsURL)
        let fakeCreatureID = UUID().uuidString.lowercased()
        try overwriteExportMetadataCreatureID(
            metaURL: URL(fileURLWithPath: exportRecord.exportDir).appendingPathComponent("meta.json"),
            creatureID: fakeCreatureID
        )
        let firstExportLine = try XCTUnwrap(
            String(contentsOf: exportsURL, encoding: .utf8)
                .split(whereSeparator: \.isNewline)
                .first
        )
        let replayIndexURL = replayInputDir.appendingPathComponent("index.jsonl")
        try Data(firstExportLine.utf8).write(to: replayIndexURL)

        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        _ = try runLeniaCLI(arguments: [
            "publish",
            "replay",
            "--input", replayIndexURL.path,
            "--output", replayOutput.path,
            "--run-id", "test-qd-replay",
            "--db", dbPath,
        ])

        let campaignsDir = replayOutput.appendingPathComponent("campaigns", isDirectory: true)
        let campaigns = try fm.contentsOfDirectory(
            at: campaignsDir,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: .skipsHiddenFiles
        ).filter(\.hasDirectoryPath)
        XCTAssertEqual(campaigns.count, 1)

        let specimenDir = try XCTUnwrap(campaigns.first)
        let result = try decodeSingleJSONL(
            SimulationResultData.self,
            from: specimenDir.appendingPathComponent("results.jsonl")
        )
        XCTAssertNotNil(result.initialConditionFamily)
        XCTAssertNotNil(result.descriptorBundle)
        let replayManifest = try JSONDecoder().decode(
            ReplaySpecimenManifest.self,
            from: Data(contentsOf: specimenDir.appendingPathComponent("replay-manifest.json"))
        )
        XCTAssertEqual(replayManifest.sourceCreatureId.lowercased(), exportRecord.creatureId.uuidString.lowercased())
        XCTAssertNotEqual(replayManifest.sourceCreatureId.lowercased(), fakeCreatureID)

        let db = try SQLiteDB(path: dbPath)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM creatures"), 1)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM results"), 1)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM specimens"), 1)
        XCTAssertEqual(
            try db.scalarInt("SELECT COUNT(*) FROM specimens WHERE source_kind = 'result'"),
            1
        )
        XCTAssertEqual(
            try db.scalarInt("SELECT COUNT(*) FROM specimens WHERE source_kind = 'library'"),
            0
        )
    }

    func testSensorimotor2024RunEmitsIndexableLibraryEntries() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-cli-sensorimotor-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let configDirectory = root.appendingPathComponent("configs", isDirectory: true)
        let runDir = root.appendingPathComponent("test-sensorimotor-2024", isDirectory: true)
        try makeTinySensorimotorConfigDirectory(at: configDirectory)
        try fm.createDirectory(at: runDir, withIntermediateDirectories: true)

        let bundle = try loadSensorimotorLenia2024ConfigBundle(configDirectory: configDirectory)
        let runner = SensorimotorLenia2024Runner(
            configs: bundle,
            logger: Logger(label: "CompendiumIndexingTests.Sensorimotor")
        )
        let summary = try runner.run(seed: 7, outputDirectory: runDir, runId: "test-sensorimotor-2024")
        XCTAssertGreaterThan(summary.historyCount, 0)

        let libraryURL = runDir.appendingPathComponent("library/index.jsonl")
        XCTAssertTrue(fm.fileExists(atPath: libraryURL.path))
        XCTAssertGreaterThan(try countJSONLLines(at: libraryURL), 0)
        let exportsURL = runDir.appendingPathComponent("exports/index.jsonl")
        XCTAssertTrue(fm.fileExists(atPath: exportsURL.path))
        XCTAssertGreaterThan(try countJSONLLines(at: exportsURL), 0)
        let exportRecord = try decodeSingleJSONL(CreatureExportRecord.self, from: exportsURL)
        XCTAssertEqual(exportRecord.bundleKind, .sensorimotor24PaperReplayBundleV1)
        XCTAssertNil(exportRecord.baseConfigPath)
        XCTAssertNil(exportRecord.searchConfigPath)
        let payloadPath = try XCTUnwrap(exportRecord.payloadPath)
        XCTAssertTrue(fm.fileExists(atPath: payloadPath))
        let replayPayload = try JSONDecoder().decode(
            SensorimotorLenia2024ReplayPayload.self,
            from: Data(contentsOf: URL(fileURLWithPath: payloadPath))
        )
        XCTAssertEqual(replayPayload.replaySeed, 7)
        XCTAssertFalse(replayPayload.entry.candidate.initialization.isEmpty)
        let exportMeta = try JSONDecoder().decode(
            CreatureExportMetadata.self,
            from: Data(contentsOf: URL(fileURLWithPath: exportRecord.exportDir).appendingPathComponent("meta.json"))
        )
        XCTAssertEqual(exportMeta.bundleKind, .sensorimotor24PaperReplayBundleV1)
        XCTAssertNotNil(exportMeta.creature.initialCondition.state_patch)
        XCTAssertEqual(replayPayload.archiveSlot, exportMeta.creature.initialCondition.seed)

        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        var command = try IndexCommand.parseAsRoot([
            "--run-dir", runDir.path,
            "--db", dbPath,
            "--rebuild",
        ])
        try command.run()

        let db = try SQLiteDB(path: dbPath)
        XCTAssertGreaterThan(try db.scalarInt("SELECT COUNT(*) FROM creatures"), 0)
        let stmt = try db.prepare("""
            SELECT source_mode, source_algorithm, research_metadata_json
            FROM creatures ORDER BY id LIMIT 1
        """)
        defer { sqlite3_finalize(stmt) }
        XCTAssertEqual(sqlite3_step(stmt), SQLITE_ROW)
        XCTAssertEqual(sqliteText(stmt, 0), "sensorimotor-2024")
        XCTAssertEqual(sqliteText(stmt, 1), "imgep")
        let metadata = try XCTUnwrap(sqliteOptionalText(stmt, 2))
        XCTAssertTrue(metadata.contains("\"mode\":\"sensorimotor-2024\""))
        XCTAssertTrue(metadata.contains("\"archive_slot\":"))
        XCTAssertTrue(metadata.contains("\"canonical_export_available\":true"))
    }

    func testSensorimotor2024ExportIndexLoadsSeedPatches() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-cli-sensorimotor-export-seeds-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let configDirectory = root.appendingPathComponent("configs", isDirectory: true)
        let runDir = root.appendingPathComponent("test-sensorimotor-2024", isDirectory: true)
        try makeTinySensorimotorConfigDirectory(at: configDirectory)
        try fm.createDirectory(at: runDir, withIntermediateDirectories: true)

        let bundle = try loadSensorimotorLenia2024ConfigBundle(configDirectory: configDirectory)
        let runner = SensorimotorLenia2024Runner(
            configs: bundle,
            logger: Logger(label: "CompendiumIndexingTests.SensorimotorExportSeeds")
        )
        _ = try runner.run(seed: 7, outputDirectory: runDir, runId: "test-sensorimotor-2024")

        let patches = try loadResearchSeedPatches(
            libraryURL: runDir.appendingPathComponent("exports/index.jsonl")
        )
        XCTAssertFalse(patches.isEmpty)
        XCTAssertGreaterThan(patches[0].world.width, 0)
        XCTAssertGreaterThan(patches[0].world.height, 0)
        XCTAssertEqual(patches[0].world.channels, 1)
    }

    func testSensorimotor2024ReplaySpecimensCommandReplaysCanonicalExport() async throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-cli-sensorimotor-replay-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let configDirectory = root.appendingPathComponent("configs", isDirectory: true)
        let runDir = root.appendingPathComponent("test-sensorimotor-2024", isDirectory: true)
        let replayInputDir = root.appendingPathComponent("replay-input", isDirectory: true)
        let replayOutput = root.appendingPathComponent("replay-output", isDirectory: true)
        try makeTinySensorimotorConfigDirectory(at: configDirectory)
        try fm.createDirectory(at: runDir, withIntermediateDirectories: true)
        try fm.createDirectory(at: replayInputDir, withIntermediateDirectories: true)

        let bundle = try loadSensorimotorLenia2024ConfigBundle(configDirectory: configDirectory)
        let runner = SensorimotorLenia2024Runner(
            configs: bundle,
            logger: Logger(label: "CompendiumIndexingTests.SensorimotorReplay")
        )
        _ = try runner.run(seed: 7, outputDirectory: runDir, runId: "test-sensorimotor-2024")

        let exportsURL = runDir.appendingPathComponent("exports/index.jsonl")
        let firstExportLine = try XCTUnwrap(
            String(contentsOf: exportsURL, encoding: .utf8)
                .split(whereSeparator: \.isNewline)
                .first
        )
        let replayIndexURL = replayInputDir.appendingPathComponent("index.jsonl")
        try Data(firstExportLine.utf8).write(to: replayIndexURL)

        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        _ = try runLeniaCLI(arguments: [
            "publish",
            "replay",
            "--input", replayIndexURL.path,
            "--output", replayOutput.path,
            "--run-id", "test-sensorimotor-replay",
            "--db", dbPath,
        ])

        let campaignsDir = replayOutput.appendingPathComponent("campaigns", isDirectory: true)
        let campaigns = try fm.contentsOfDirectory(
            at: campaignsDir,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: .skipsHiddenFiles
        ).filter(\.hasDirectoryPath)
        XCTAssertEqual(campaigns.count, 1)

        let specimenDir = try XCTUnwrap(campaigns.first)
        let result = try decodeSingleJSONL(
            SimulationResultData.self,
            from: specimenDir.appendingPathComponent("results.jsonl")
        )
        XCTAssertEqual(result.backend, "sensorimotor24-paper")
        XCTAssertNotNil(result.initialConditionFamily)
        XCTAssertNotNil(result.descriptorBundle)
        XCTAssertEqual(result.descriptorBundle?.genotype.canonicalizer, "sensorimotor24_candidate_identity_v1")

        let db = try SQLiteDB(path: dbPath)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM creatures"), 1)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM results"), 1)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM specimens"), 1)
        XCTAssertEqual(
            try db.scalarInt("SELECT COUNT(*) FROM specimens WHERE source_kind = 'result'"),
            1
        )
        XCTAssertEqual(
            try db.scalarInt("SELECT COUNT(*) FROM specimens WHERE source_kind = 'library'"),
            0
        )
    }

    func testFlowTasksEvolveRunEmitsIndexableLibraryEntries() async throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-cli-flow-tasks-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let configRoot = root.appendingPathComponent("configs", isDirectory: true)
        let runDir = root.appendingPathComponent("test-flow-tasks", isDirectory: true)
        let logsDir = root.appendingPathComponent("logs", isDirectory: true)
        try fm.createDirectory(at: configRoot, withIntermediateDirectories: true)
        try fm.createDirectory(at: runDir, withIntermediateDirectories: true)
        try fm.createDirectory(at: logsDir, withIntermediateDirectories: true)

        let flowSource = leniaCLIPackageRoot.appendingPathComponent("configs/papers/flowlenia-2022", isDirectory: true)
        let baseConfigURL = configRoot.appendingPathComponent("task_directed_motion_2c_20k_128.json")
        let esConfigURL = configRoot.appendingPathComponent("es_directed_motion_openes.json")
        try fm.copyItem(at: flowSource.appendingPathComponent("task_directed_motion_2c_20k_128.json"), to: baseConfigURL)
        try fm.copyItem(at: flowSource.appendingPathComponent("es_directed_motion_openes.json"), to: esConfigURL)

        try rewriteJSONFile(at: baseConfigURL) { root in
            var run = root["run"] as! [String: Any]
            run["steps"] = 24
            root["run"] = run
        }
        try rewriteJSONFile(at: esConfigURL) { root in
            root["output_dir"] = runDir.path
            root["generations"] = 1
            root["population"] = 4
            root["steps"] = 24
            var fitness = root["fitness"] as! [String: Any]
            fitness["target_step"] = 12
            root["fitness"] = fitness
        }

        _ = try runLeniaCLI(arguments: [
            "discover",
            "evolve",
            "--config", baseConfigURL.path,
            "--es", esConfigURL.path,
            "--output", runDir.path,
            "--run-id", "test-flow-tasks",
            "--log-dir", logsDir.path,
        ])

        let libraryURL = runDir.appendingPathComponent("library/index.jsonl")
        XCTAssertTrue(fm.fileExists(atPath: libraryURL.path))
        XCTAssertGreaterThan(try countJSONLLines(at: libraryURL), 0)
        let exportsURL = runDir.appendingPathComponent("exports/index.jsonl")
        XCTAssertTrue(fm.fileExists(atPath: exportsURL.path))
        XCTAssertEqual(try countJSONLLines(at: exportsURL), 1)
        let exportRecord = try decodeSingleJSONL(CreatureExportRecord.self, from: exportsURL)
        XCTAssertEqual(exportRecord.bundleKind, .strictReplayBundleV1)
        let baseConfigPath = try XCTUnwrap(exportRecord.baseConfigPath)
        let searchConfigPath = try XCTUnwrap(exportRecord.searchConfigPath)
        XCTAssertTrue(fm.fileExists(atPath: baseConfigPath))
        XCTAssertTrue(fm.fileExists(atPath: searchConfigPath))
        let exportBase = try JSONDecoder().decode(
            LeniaBaseConfig.self,
            from: Data(contentsOf: URL(fileURLWithPath: baseConfigPath))
        )
        let bestConfig = try JSONDecoder().decode(
            LeniaBaseConfig.self,
            from: Data(contentsOf: runDir.appendingPathComponent("best_config.json"))
        )
        let bestJSON = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(contentsOf: runDir.appendingPathComponent("best.json")))
                as? [String: Any]
        )
        let bestFitness = try XCTUnwrap(bestJSON["fitness"] as? Double)
        XCTAssertEqual(exportBase.params.mode, "explicit")
        XCTAssertEqual(exportBase.params.R, bestConfig.params.R)
        XCTAssertEqual(exportBase.params.r, bestConfig.params.r)
        XCTAssertEqual(exportBase.params.m, bestConfig.params.m)
        XCTAssertEqual(exportBase.params.s, bestConfig.params.s)
        XCTAssertNil(exportBase.params.ranges)
        XCTAssertEqual(try XCTUnwrap(exportRecord.score), Float(bestFitness), accuracy: 1e-5)
        let replaySearch = try JSONDecoder().decode(
            ParsedSearchConfig.self,
            from: Data(contentsOf: URL(fileURLWithPath: searchConfigPath))
        )
        XCTAssertEqual(replaySearch.steps, 24)
        XCTAssertNil(replaySearch.activity)
        XCTAssertTrue(replaySearch.moments?.enabled == true)
        XCTAssertTrue(replaySearch.stability?.enabled == true)

        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        var index = try IndexCommand.parseAsRoot([
            "--run-dir", runDir.path,
            "--db", dbPath,
            "--rebuild",
        ])
        try index.run()

        let db = try SQLiteDB(path: dbPath)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM creatures"), 1)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM exports"), 1)
        let stmt = try db.prepare("""
            SELECT source_mode, source_algorithm, research_metadata_json
            FROM creatures LIMIT 1
        """)
        defer { sqlite3_finalize(stmt) }
        XCTAssertEqual(sqlite3_step(stmt), SQLITE_ROW)
        XCTAssertEqual(sqliteText(stmt, 0), "flow-tasks")
        XCTAssertEqual(sqliteText(stmt, 1), "openes")
        let metadata = try XCTUnwrap(sqliteOptionalText(stmt, 2))
        XCTAssertTrue(metadata.contains("\"mode\":\"flow-tasks\""))
        XCTAssertTrue(metadata.contains("\"task\":\"directed_motion\""))
        XCTAssertTrue(metadata.contains("\"canonical_export_available\":true"))
    }

    func testFlowTasksObstacleNavigationExportPreservesObstacleField() async throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-cli-flow-obstacle-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let configRoot = root.appendingPathComponent("configs", isDirectory: true)
        let runDir = root.appendingPathComponent("test-flow-obstacle", isDirectory: true)
        let logsDir = root.appendingPathComponent("logs", isDirectory: true)
        try fm.createDirectory(at: configRoot, withIntermediateDirectories: true)
        try fm.createDirectory(at: runDir, withIntermediateDirectories: true)
        try fm.createDirectory(at: logsDir, withIntermediateDirectories: true)

        let flowSource = leniaCLIPackageRoot.appendingPathComponent("configs/papers/flowlenia-2022", isDirectory: true)
        let baseConfigURL = configRoot.appendingPathComponent("task_obstacle_navigation_3c_25k_128.json")
        let esConfigURL = configRoot.appendingPathComponent("es_obstacle_navigation_openes.json")
        try fm.copyItem(at: flowSource.appendingPathComponent("task_obstacle_navigation_3c_25k_128.json"), to: baseConfigURL)
        try fm.copyItem(at: flowSource.appendingPathComponent("es_obstacle_navigation_openes.json"), to: esConfigURL)

        try rewriteJSONFile(at: baseConfigURL) { root in
            var run = root["run"] as! [String: Any]
            run["steps"] = 16
            root["run"] = run
        }
        try rewriteJSONFile(at: esConfigURL) { root in
            root["output_dir"] = runDir.path
            root["generations"] = 1
            root["population"] = 2
            root["steps"] = 16
            var fitness = root["fitness"] as! [String: Any]
            fitness["target_step"] = 8
            root["fitness"] = fitness
        }

        _ = try runLeniaCLI(arguments: [
            "discover",
            "evolve",
            "--config", baseConfigURL.path,
            "--es", esConfigURL.path,
            "--output", runDir.path,
            "--run-id", "test-flow-obstacle",
            "--log-dir", logsDir.path,
        ])

        let exportsURL = runDir.appendingPathComponent("exports/index.jsonl")
        XCTAssertTrue(fm.fileExists(atPath: exportsURL.path))
        XCTAssertEqual(try countJSONLLines(at: exportsURL), 1)

        let exportRecord = try decodeSingleJSONL(CreatureExportRecord.self, from: exportsURL)
        XCTAssertEqual(exportRecord.bundleKind, .strictReplayBundleV1)
        let baseConfigPath = try XCTUnwrap(exportRecord.baseConfigPath)
        let searchConfigPath = try XCTUnwrap(exportRecord.searchConfigPath)
        let exportBase = try JSONDecoder().decode(
            LeniaBaseConfig.self,
            from: Data(contentsOf: URL(fileURLWithPath: baseConfigPath))
        )
        let replaySearch = try JSONDecoder().decode(
            ParsedSearchConfig.self,
            from: Data(contentsOf: URL(fileURLWithPath: searchConfigPath))
        )

        XCTAssertTrue(exportBase.obstacle_field?.enabled == true)
        XCTAssertEqual(exportBase.obstacle_field?.mode, "random_on_circle")
        XCTAssertEqual(exportBase.obstacle_field?.channel_index, 2)
        XCTAssertEqual(exportBase.obstacle_field?.count, 12)
        XCTAssertEqual(exportBase.run.steps, 16)
        XCTAssertEqual(replaySearch.initSeedOffset, exportBase.`init`.seed)
        XCTAssertNil(replaySearch.activity)
        XCTAssertTrue(replaySearch.moments?.enabled == true)
        XCTAssertTrue(replaySearch.stability?.enabled == true)
    }

    func testResearchModeReindexIsIdempotent() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-cli-reindex-idempotent-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let runDir = root.appendingPathComponent("run-001", isDirectory: true)
        try makeRunLayout(at: runDir)

        let entry = ResearchLibraryEntry(
            creature: makeCreature(
                id: deterministicResearchUUID("run-001|me|3"),
                name: "qd-me-cell-3",
                seed: 3
            ),
            campaignId: nil,
            runId: "run-001",
            recordedAt: fixedDate,
            configHash: "cfg-reindex",
            sourceMode: "qd-2024",
            sourceAlgorithm: "me",
            researchMetadata: [
                "version": AnyCodable(1),
                "mode": AnyCodable("qd-2024"),
                "algorithm": AnyCodable("me"),
                "generation": AnyCodable(1),
                "cell": AnyCodable(3),
                "descriptor": AnyCodable([0.1, 0.2]),
                "centroid": AnyCodable([0.15, 0.25]),
                "fitness": AnyCodable(-0.25),
            ]
        )
        _ = try ResearchLibraryWriter.write(entries: [entry], runDirectory: runDir)

        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        var command = try IndexCommand.parseAsRoot([
            "--run-dir", runDir.path,
            "--db", dbPath,
            "--rebuild",
        ])
        try command.run()

        command = try IndexCommand.parseAsRoot([
            "--run-dir", runDir.path,
            "--db", dbPath,
        ])
        try command.run()

        let db = try SQLiteDB(path: dbPath)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM creatures"), 1)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM runs"), 1)
    }
}

private let fixedDate = Date(timeIntervalSince1970: 1_700_000_000)
private let leniaCLIPackageRoot = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent()
    .deletingLastPathComponent()
    .deletingLastPathComponent()

private func makeTinyLeniaBreederConfigDirectory(at configDirectory: URL, distributed: Bool = false) throws {
    let fm = FileManager.default
    let sourceDirectory = leniaCLIPackageRoot.appendingPathComponent("configs/papers/leniabreeder-2024", isDirectory: true)
    try fm.createDirectory(at: configDirectory, withIntermediateDirectories: true)
    for filename in ["base.json", "me.json", "aurora.json"] {
        try fm.copyItem(
            at: sourceDirectory.appendingPathComponent(filename),
            to: configDirectory.appendingPathComponent(filename)
        )
    }
    try fm.copyItem(
        at: sourceDirectory.appendingPathComponent("patterns", isDirectory: true),
        to: configDirectory.appendingPathComponent("patterns", isDirectory: true)
    )

    try rewriteJSONFile(at: configDirectory.appendingPathComponent("base.json")) { root in
        root["world_size"] = distributed ? 64 : 128
        root["n_step"] = distributed ? 12 : 20
    }
    try rewriteJSONFile(at: configDirectory.appendingPathComponent("me.json")) { root in
        root["phenotype_size"] = distributed ? 32 : 64
        root["n_generations"] = 1
        root["log_interval"] = 1
        root["batch_size"] = 4
        root["repertoire_size"] = 8
        root["n_init_cvt_samples"] = 64
        root["n_keep"] = 4
        root["iso_sigma"] = 0.001
        root["line_sigma"] = 0.01
    }
}

private func makeTinySensorimotorConfigDirectory(at configDirectory: URL) throws {
    let fm = FileManager.default
    let sourceDirectory = leniaCLIPackageRoot.appendingPathComponent("configs/papers/sensorimotor-lenia-2024", isDirectory: true)
    try fm.createDirectory(at: configDirectory, withIntermediateDirectories: true)
    for filename in ["rule_space_and_init.json", "train_curriculum.json", "evaluation_battery.json"] {
        try fm.copyItem(
            at: sourceDirectory.appendingPathComponent(filename),
            to: configDirectory.appendingPathComponent(filename)
        )
    }

    try rewriteJSONFile(at: configDirectory.appendingPathComponent("train_curriculum.json")) { root in
        root["outer_steps"] = 2
        root["history_initialization_trials"] = 1
        root["rollout_steps"] = 8
        var optimization = root["optimization"] as! [String: Any]
        optimization["steps_unmutated"] = 1
        optimization["steps_mutated"] = 1
        root["optimization"] = optimization
        var restart = root["restart"] as! [String: Any]
        restart["max_attempts"] = 1
        restart["min_alive_random_initializations"] = 0
        restart["max_loss"] = 1000.0
        root["restart"] = restart
        var evaluationAfterStep = root["evaluation_after_step"] as! [String: Any]
        evaluationAfterStep["rollouts"] = 1
        root["evaluation_after_step"] = evaluationAfterStep
    }

    try rewriteJSONFile(at: configDirectory.appendingPathComponent("evaluation_battery.json")) { root in
        var prefilter = root["prefilter"] as! [String: Any]
        prefilter["rollout_steps"] = 20
        root["prefilter"] = prefilter

        var moving = root["moving"] as! [String: Any]
        moving["window_end"] = 20
        moving["speed_start"] = 10
        root["moving"] = moving

        var agency = root["agency"] as! [String: Any]
        agency["rollout_steps"] = 24
        agency["mass_window_a"] = [0, 8]
        agency["mass_window_b"] = [16, 24]
        root["agency"] = agency

        var basicObstacleTest = root["basic_obstacle_test"] as! [String: Any]
        basicObstacleTest["rollouts"] = 1
        basicObstacleTest["rollout_steps"] = 24
        basicObstacleTest["forced_obstacle_reference_step"] = 12
        root["basic_obstacle_test"] = basicObstacleTest

        var generalization = root["generalization"] as! [String: Any]
        generalization["trials_per_setting"] = 1
        generalization["obstacle_radius"] = [10]
        generalization["obstacle_count"] = [24]
        generalization["obstacle_speed"] = [1.0]
        generalization["update_mask_rate"] = [1.0]
        generalization["update_noise_std"] = [1.0]
        generalization["update_noise_rate"] = [1.0]
        generalization["init_noise_rate"] = [1.0]
        generalization["init_noise_std"] = [1.0]
        generalization["scale"] = [1.0]
        root["generalization"] = generalization
    }
}

private func makeCreature(id: UUID, name: String, seed: Int) -> SavedCreature {
    let creature = makeMorphospaceReadyCreature(
        id: id,
        name: name,
        seed: seed,
        isStable: true,
        fingerprintByte: UInt8(truncatingIfNeeded: seed)
    )
    return SavedCreature(
        id: creature.id,
        name: creature.name,
        ownerId: creature.ownerId,
        genotype: creature.genotype,
        initialCondition: InitConfig(
            seed: seed,
            patches: [PatchConfig(center: [64, 64], size: 12)],
            a_uniform: UniformRange(low: 0, high: 1),
            p_uniform: nil
        ),
        descriptorBundle: creature.descriptorBundle,
        metrics: creature.metrics,
        sweep: creature.sweep,
        score: creature.score,
        scoreWeights: creature.scoreWeights,
        configHash: creature.configHash
    )
}

private func makeMorphospaceReadyCreature(
    id: UUID,
    name: String,
    seed: Int,
    isStable: Bool,
    fingerprintByte: UInt8,
    genotypeCanonicalizer: String = "kernel_permutation_sort_v1"
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
    let initialCondition = InitConfig(
        seed: seed,
        patches: [],
        a_uniform: UniformRange(low: 0, high: 0),
        p_uniform: nil
    )
    let baseGenotypeDescriptor = morphospaceGenotypeDescriptor(genotype)
    let genotypeDescriptor = MorphospaceGenotypeDescriptor(
        version: baseGenotypeDescriptor.version,
        canonicalizer: genotypeCanonicalizer,
        kernelCount: baseGenotypeDescriptor.kernelCount,
        vectorLength: baseGenotypeDescriptor.vectorLength,
        vector: baseGenotypeDescriptor.vector,
        hash12: baseGenotypeDescriptor.hash12
    )
    let descriptorBundle = MorphospaceDescriptorBundle(
        symmetryPolicy: "translation_kernel_permutation_v1",
        genotype: genotypeDescriptor,
        terminal: MorphospaceTerminalDescriptor(
            massChannel: 0,
            borderMode: "wall",
            symmetryPolicy: "translation_kernel_permutation_v1",
            fingerprintResolution: 32,
            fingerprintU8: Data(repeating: fingerprintByte, count: 32 * 32),
            angularSymmetry: MorphospaceAngularSymmetryDescriptor(
                binCount: 32,
                maxOrder: 8,
                harmonics: Array(repeating: 0.1, count: 8),
                dominantOrder: 2,
                dominantAmplitude: 0.2,
                normalizedEntropy: 0.5
            ),
            fingerprintHash12: String(repeating: String(fingerprintByte, radix: 16), count: 12).prefix(12).description,
            finalMass: 1,
            finalOccupancy: 0.2,
            finalGyration: 3,
            momentMass: 1,
            momentVolume: 1,
            momentDensity: 1,
            momentAnisotropy: 0.1,
            componentCount: 1,
            largestComponentFraction: 1,
            largestComponentAnisotropy: 0.1,
            hu1: 0.1,
            hu2: 0.1,
            hu3: 0.1,
            hu4: 0.1,
            hu5: 0.1,
            hu6: 0.1,
            hu7: 0.1,
            flusser1: 0.1,
            flusser2: 0.1,
            flusser3: 0.1,
            flusser4: 0.1,
            windowMassStd: 0.01,
            windowOccupancyStd: 0.01,
            windowGyrationStd: 0.01,
            isStable: isStable
        ),
        trajectory: MorphospaceTrajectoryDescriptor(
            recordInterval: 1,
            warmupSteps: 0,
            sampleCount: 4,
            pathLength: 1,
            displacement: 1,
            pathTortuosity: 1,
            movementEfficiency: 1,
            speedMean: 0.4,
            centerVelocity: 0.5,
            velocityX: 0.012,
            velocityY: -0.004,
            headingRad: -0.32175055,
            headingCircularVariance: 0.1,
            accumulatedTurnAbs: 0.2,
            survivalSteps: 20,
            activityEacMean: 0.1,
            activityEanMean: 0.2,
            activityDiversityMean: 0.3,
            activitySpeciesMean: 1.0,
            activitySpeciesMax: 2,
            activitySpeciesStd: 0.1,
            activityDiversityStd: 0.1,
            activityEacMax: 0.3,
            activityEanMax: 0.4,
            componentSeriesMean: 1.0,
            componentSeriesStd: 0.0,
            componentSeriesMax: 1
        )
    )

    return SavedCreature(
        id: id,
        name: name,
        ownerId: "tester",
        genotype: genotype,
        initialCondition: initialCondition,
        descriptorBundle: descriptorBundle,
        metrics: SimulationMetrics(
            massMean: 1,
            massStd: 0.1,
            massMin: 0,
            massMax: 2,
            occupancyMean: 0.2,
            varianceMean: 0.01,
            energyMean: 0.3,
            speedMean: 0.4,
            pathLength: 10,
            displacement: 2,
            sampleCount: 2,
            speedCount: 1,
            gyration: 3,
            centerVelocity: 0.5,
            velocityX: 0.012,
            velocityY: -0.004,
            headingRad: -0.32175055,
            isStable: isStable
        ),
        sweep: nil,
        score: 0.99,
        scoreWeights: ["mass_mean": 1.0]
    )
}

private func makeActivityRecord(seed: Int, speciesCount: [Int]) -> ActivitySummaryRecord {
    ActivitySummaryRecord(
        seed: seed,
        workerId: nil,
        summary: ActivitySummary(
            steps: [0, 10, 20],
            eap: [1, 2, 2],
            eac: [1, 2, 3],
            ean: [0.5, 0.25, 0.75],
            diversity: [0.1, 0.2, 0.3],
            speciesCount: speciesCount
        ),
        implementation: ImplementationSettings(
            mode: "test",
            border: "torus",
            gradientBoundary: "wrap",
            alphaMode: "none",
            kernelProfile: "test",
            flowClip: "none"
        )
    )
}

private func makeExportRecord(
    creatureId: UUID,
    runId: String,
    campaignId: String?,
    exportDir: String
) -> CreatureExportRecord {
    CreatureExportRecord(
        creatureId: creatureId,
        name: "exported",
        ownerId: "tester",
        runId: runId,
        campaignId: campaignId,
        bundleKind: .strictReplayBundleV1,
        exportDir: exportDir,
        baseConfigPath: exportDir + "/base.json",
        searchConfigPath: exportDir + "/search.json",
        exportedAt: fixedDate,
        reason: "test",
        score: 0.99,
        filtersPassed: true
    )
}

private func jsonlLine<T: Encodable>(_ value: T) throws -> String {
    let data = try JSONEncoder().encode(value)
    return String(data: data, encoding: .utf8)! + "\n"
}

private func padJSONLLine(_ line: String, toUTF8Count targetCount: Int) -> String {
    let currentCount = line.utf8.count
    if currentCount > targetCount {
        fatalError("Cannot shrink JSONL fixture from \(currentCount) to \(targetCount) bytes.")
    }
    if currentCount == targetCount {
        return line
    }
    guard line.hasSuffix("\n") else {
        fatalError("JSONL fixture must end with a newline.")
    }
    return String(line.dropLast()) + String(repeating: " ", count: targetCount - currentCount) + "\n"
}

private func sqliteText(_ stmt: OpaquePointer, _ index: Int32) -> String {
    String(cString: sqlite3_column_text(stmt, index))
}

private func sqliteOptionalText(_ stmt: OpaquePointer, _ index: Int32) -> String? {
    sqlite3_column_text(stmt, index).map { String(cString: $0) }
}

private func insertCreatureRow(
    _ creature: SavedCreature,
    runId: String,
    db: SQLiteDB
) throws {
    let encoder = JSONEncoder()
    let recordedAt = ISO8601DateFormatter().string(from: fixedDate)
    let genotypeJSON = String(data: try encoder.encode(creature.genotype), encoding: .utf8)!
    let initialConditionJSON = String(data: try encoder.encode(creature.initialCondition), encoding: .utf8)!
    let metricsJSON = String(data: try encoder.encode(creature.metrics), encoding: .utf8)!
    let scoreWeightsJSON = String(data: try encoder.encode(creature.scoreWeights), encoding: .utf8)!
    let morphometrics = Morphometrics.from(metrics: creature.metrics, activity: nil)
    let morphometricsJSON = String(data: try encoder.encode(morphometrics), encoding: .utf8)!
    let placeholders = Array(repeating: "?", count: 45).joined(separator: ",")
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
            config_hash, score_weights_json, genotype_json, initial_condition_json, sweep_json, metrics_json
        ) VALUES (\(placeholders))
    """)
    defer { sqlite3_finalize(stmt) }
    db.bindText(stmt, index: 1, value: creature.id.uuidString)
    db.bindText(stmt, index: 2, value: creature.name)
    db.bindText(stmt, index: 3, value: creature.ownerId)
    db.bindText(stmt, index: 4, value: runId)
    db.bindText(stmt, index: 5, value: nil)
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
    db.bindDouble(stmt, index: 34, value: nil as Double?)
    db.bindText(stmt, index: 35, value: nil)
    db.bindInt(stmt, index: 36, value: nil)
    db.bindText(stmt, index: 37, value: morphometricsJSON)
    db.bindText(stmt, index: 38, value: "lenia-swarm:morphometrics")
    db.bindInt(stmt, index: 39, value: morphometrics.version)
    db.bindText(stmt, index: 40, value: creature.configHash)
    db.bindText(stmt, index: 41, value: scoreWeightsJSON)
    db.bindText(stmt, index: 42, value: genotypeJSON)
    db.bindText(stmt, index: 43, value: initialConditionJSON)
    db.bindText(stmt, index: 44, value: nil)
    db.bindText(stmt, index: 45, value: metricsJSON)
    try db.step(stmt)
}

private func overwriteExportMetadataCreatureID(
    metaURL: URL,
    creatureID: String
) throws {
    guard var root = try JSONSerialization.jsonObject(with: Data(contentsOf: metaURL)) as? [String: Any],
          var creature = root["creature"] as? [String: Any] else {
        XCTFail("Expected creature export metadata object at \(metaURL.path)")
        return
    }
    creature["id"] = creatureID
    root["creature"] = creature
    let data = try JSONSerialization.data(withJSONObject: root, options: [.sortedKeys])
    try data.write(to: metaURL)
}
