import Foundation
import XCTest
@testable import LeniaCLIKit
import LeniaCore

final class GoldenWorkflowTests: XCTestCase {
    func testDiscoverLocalPromotesArtifactsAndRefreshesWarehouse() throws {
        let root = try makeTempDirectory(prefix: "lenia-golden-local")
        defer { try? FileManager.default.removeItem(at: root) }

        let fixture = try makeLocalWorkflowFixture(at: root, runID: "golden-local-promotion")
        try runDiscoverLocal(fixture: fixture, extraArguments: [
            "--db", fixture.compendiumURL.path,
            "--warehouse", fixture.warehouseURL.path,
        ])

        let fm = FileManager.default
        XCTAssertTrue(fm.fileExists(atPath: fixture.runDir.appendingPathComponent("config.json").path))
        XCTAssertTrue(fm.fileExists(atPath: fixture.runDir.appendingPathComponent("search.json").path))
        XCTAssertTrue(fm.fileExists(atPath: fixture.runDir.appendingPathComponent("results.jsonl").path))
        XCTAssertTrue(fm.fileExists(atPath: fixture.runDir.appendingPathComponent("library/index.jsonl").path))
        XCTAssertTrue(fm.fileExists(atPath: fixture.runDir.appendingPathComponent("exports/index.jsonl").path))
        XCTAssertTrue(fm.fileExists(atPath: fixture.runDir.appendingPathComponent("summary.json").path))
        XCTAssertTrue(fm.fileExists(atPath: fixture.compendiumURL.path))
        XCTAssertTrue(fm.fileExists(atPath: fixture.warehouseURL.path))

        XCTAssertEqual(try countJSONLLines(at: fixture.runDir.appendingPathComponent("results.jsonl")), 1)
        XCTAssertEqual(try countJSONLLines(at: fixture.runDir.appendingPathComponent("library/index.jsonl")), 1)
        XCTAssertEqual(try countJSONLLines(at: fixture.runDir.appendingPathComponent("exports/index.jsonl")), 1)

        let summary = try JSONDecoder().decode(
            LocalWorkflowSummaryFixture.self,
            from: Data(contentsOf: fixture.runDir.appendingPathComponent("summary.json"))
        )
        XCTAssertEqual(summary.runId, fixture.runID)
        XCTAssertEqual(summary.resultsCount, 1)
        XCTAssertEqual(summary.collectedCount, 1)
        XCTAssertEqual(summary.exportedCount, 1)

        let entry = try decodeSingleJSONL(
            ResearchLibraryEntry.self,
            from: fixture.runDir.appendingPathComponent("library/index.jsonl")
        )
        XCTAssertEqual(entry.runId, fixture.runID)
        XCTAssertNil(entry.campaignId)
        XCTAssertNotNil(entry.configHash)

        let exportRecord = try decodeSingleJSONL(
            CreatureExportRecord.self,
            from: fixture.runDir.appendingPathComponent("exports/index.jsonl")
        )
        XCTAssertEqual(exportRecord.runId, fixture.runID)
        XCTAssertEqual(exportRecord.bundleKind, .strictReplayBundleV1)
        XCTAssertTrue(fm.fileExists(atPath: exportRecord.exportDir))

        let db = try SQLiteDB(path: fixture.compendiumURL.path)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM runs WHERE run_id = 'golden-local-promotion'"), 1)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM results WHERE run_id = 'golden-local-promotion'"), 1)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM exports WHERE run_id = 'golden-local-promotion'"), 1)
        XCTAssertGreaterThanOrEqual(try db.scalarInt("SELECT COUNT(*) FROM creatures WHERE run_id = 'golden-local-promotion'"), 1)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM specimens WHERE run_id = 'golden-local-promotion'"), 2)
    }

    func testLibraryFromResultsUsesDeterministicCreatureIDsForScoutArtifacts() throws {
        let root = try makeTempDirectory(prefix: "lenia-library-from-results")
        defer { try? FileManager.default.removeItem(at: root) }

        let fixture = try makeLocalWorkflowFixture(at: root, runID: "stable-library-from-results")
        try runDiscoverLocal(fixture: fixture, extraArguments: ["--no-promotion"])

        let firstOutput = try runLeniaCLI(arguments: [
            "publish",
            "library-from-results",
            "--scout-dir", fixture.runDir.path,
        ])
        let firstEntry = try decodeSingleJSONL(
            ResearchLibraryEntry.self,
            from: fixture.runDir.appendingPathComponent("library/index.jsonl")
        )

        let secondOutput = try runLeniaCLI(arguments: [
            "publish",
            "library-from-results",
            "--scout-dir", fixture.runDir.path,
        ])
        let secondEntry = try decodeSingleJSONL(
            ResearchLibraryEntry.self,
            from: fixture.runDir.appendingPathComponent("library/index.jsonl")
        )
        let result = try decodeSingleJSONL(
            SimulationResultData.self,
            from: fixture.runDir.appendingPathComponent("results.jsonl")
        )
        let stableKey = libraryResultStableKey(runId: fixture.runID, result: result)

        XCTAssertEqual(firstEntry.creature.id, secondEntry.creature.id)
        XCTAssertEqual(firstEntry.creature.id, deterministicResearchUUID(stableKey))
        XCTAssertTrue(firstOutput.contains(stableKey))
        XCTAssertTrue(secondOutput.contains(stableKey))
    }

    func testAnalyzeWarehouseRefreshesExplicitWarehouseFromIndexedLocalRun() throws {
        let root = try makeTempDirectory(prefix: "lenia-golden-warehouse")
        defer { try? FileManager.default.removeItem(at: root) }

        let fixture = try makeLocalWorkflowFixture(at: root, runID: "golden-warehouse-analysis")
        try runDiscoverLocal(fixture: fixture, extraArguments: ["--no-promotion"])

        _ = try runLeniaCLI(arguments: [
            "index",
            "--run-dir", fixture.runDir.path,
            "--db", fixture.compendiumURL.path,
            "--rebuild",
        ])

        let output = try runLeniaCLI(arguments: [
            "analyze",
            "warehouse",
            "--db", fixture.compendiumURL.path,
            "--warehouse", fixture.warehouseURL.path,
            "--json",
        ])

        let result = try JSONDecoder().decode(WarehouseRefreshFixture.self, from: Data(output.utf8))
        XCTAssertEqual(
            URL(fileURLWithPath: result.compendiumPath).resolvingSymlinksInPath().path,
            fixture.compendiumURL.resolvingSymlinksInPath().path
        )
        XCTAssertEqual(
            URL(fileURLWithPath: result.warehousePath).resolvingSymlinksInPath().path,
            fixture.warehouseURL.resolvingSymlinksInPath().path
        )
        XCTAssertFalse(result.studyId.isEmpty)
        XCTAssertGreaterThanOrEqual(result.axesUpdated, 1)
        XCTAssertGreaterThanOrEqual(result.statusUpdated, 1)
        XCTAssertGreaterThanOrEqual(result.anatomyUpdated, 1)
        XCTAssertTrue(FileManager.default.fileExists(atPath: fixture.warehouseURL.path))
    }
}

private struct LocalWorkflowFixturePaths {
    let runID: String
    let outputRoot: URL
    let runDir: URL
    let baseConfigURL: URL
    let searchConfigURL: URL
    let compendiumURL: URL
    let warehouseURL: URL
}

private struct LocalWorkflowSummaryFixture: Decodable {
    let runId: String
    let resultsCount: Int
    let collectedCount: Int
    let exportedCount: Int
}

private struct WarehouseRefreshFixture: Decodable {
    let warehousePath: String
    let compendiumPath: String
    let studyId: String
    let axesUpdated: Int
    let statusUpdated: Int
    let anatomyUpdated: Int
    let topologyStudyId: String?
}

private func makeLocalWorkflowFixture(at root: URL, runID: String) throws -> LocalWorkflowFixturePaths {
    let baseConfigURL = root.appendingPathComponent("base.json")
    try copyConfigFixture(relativePath: "base/paper_base_1c_128.json", to: baseConfigURL) { json in
        json["profile"] = "experimental"
        json["grid"] = ["sx": 16, "sy": 16]
        json["run"] = ["steps": 2]
        json["init"] = [
            "seed": 13,
            "patches": [["center": [8, 8], "size": 4]],
            "a_uniform": ["low": 0, "high": 1],
            "p_uniform": NSNull(),
        ]
    }

    let searchConfigURL = root.appendingPathComponent("search.json")
    try copyConfigFixture(relativePath: "search/search_smoke.json", to: searchConfigURL) { json in
        json["steps"] = 2
        json["record_interval"] = 1
        json["warmup_steps"] = 0
        json["count"] = 1
        json["seed_start"] = 7
        json["batch_size"] = 1
        json["seeds_per_job"] = 1
        json["collection"] = [
            "enabled": true,
            "require_stable": false,
            "require_filters_passed": false,
            "export_enabled": true,
        ]
    }

    let outputRoot = root.appendingPathComponent("output", isDirectory: true)
    return LocalWorkflowFixturePaths(
        runID: runID,
        outputRoot: outputRoot,
        runDir: outputRoot.appendingPathComponent(runID, isDirectory: true),
        baseConfigURL: baseConfigURL,
        searchConfigURL: searchConfigURL,
        compendiumURL: root.appendingPathComponent("compendium.sqlite"),
        warehouseURL: root.appendingPathComponent("morphospace.duckdb")
    )
}

private func runDiscoverLocal(
    fixture: LocalWorkflowFixturePaths,
    extraArguments: [String]
) throws {
    _ = try runLeniaCLI(arguments: [
        "discover",
        "local",
        "--config", fixture.baseConfigURL.path,
        "--search", fixture.searchConfigURL.path,
        "--output", fixture.outputRoot.path,
        "--run-id", fixture.runID,
        "--no-log-console",
    ] + extraArguments)
}
