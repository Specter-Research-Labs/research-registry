import ArgumentParser
import Foundation
import XCTest
@testable import LeniaCLIKit
import LeniaCore

final class HolonomyCommandTests: XCTestCase {
    func testHolonomyCommandReplaysStrictBundleAcrossClosedLoop() async throws {
        let root = try makeTempDirectory(prefix: "lenia-holonomy")
        defer { try? FileManager.default.removeItem(at: root) }

        let bundleDir = root.appendingPathComponent("bundle", isDirectory: true)
        try FileManager.default.createDirectory(at: bundleDir, withIntermediateDirectories: true)

        let baseConfigURL = root.appendingPathComponent("base.json")
        try FileManager.default.copyItem(
            at: dossierConfigsRoot().appendingPathComponent("base/paper_base_1c_128.json"),
            to: baseConfigURL
        )
        try rewriteJSONFile(at: baseConfigURL) { root in
            root["profile"] = "experimental"
            root["grid"] = ["sx": 16, "sy": 16]
            root["run"] = ["steps": 2]
            root["init"] = [
                "seed": 13,
                "patches": [["center": [8, 8], "size": 4]],
                "a_uniform": ["low": 0, "high": 1],
                "p_uniform": NSNull(),
            ]
        }

        let searchConfigURL = root.appendingPathComponent("search.json")
        try FileManager.default.copyItem(
            at: dossierConfigsRoot().appendingPathComponent("search/search_smoke.json"),
            to: searchConfigURL
        )
        try rewriteJSONFile(at: searchConfigURL) { root in
            root["steps"] = 2
            root["record_interval"] = 1
            root["warmup_steps"] = 0
            root["count"] = 1
            root["seed_start"] = 7
            root["batch_size"] = 1
            root["seeds_per_job"] = 1
        }

        let baseConfigData = try Data(contentsOf: baseConfigURL)
        let baseConfig = try JSONDecoder().decode(LeniaBaseConfig.self, from: baseConfigData)
        let searchConfig = try JSONDecoder().decode(ParsedSearchConfig.self, from: Data(contentsOf: searchConfigURL))
        let runtimeConfig = try loadRuntimeConfig(from: baseConfigData)
        let creature = SavedCreature(
            id: UUID(uuidString: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")!,
            name: "holonomy-seed",
            ownerId: "tester",
            genotype: runtimeConfig.params.toKernelParams(),
            initialCondition: InitConfig(
                seed: runtimeConfig.initSeed,
                patches: [],
                a_uniform: UniformRange(low: 0, high: 0),
                p_uniform: nil,
                state_patch: InitStatePatchConfig(
                    center: [8, 8],
                    width: 16,
                    height: 16,
                    channels: 1,
                    values: Array(repeating: 0.25, count: 16 * 16)
                )
            ),
            metrics: SimulationMetrics(
                massMean: 1.0,
                massStd: 0.1,
                massMin: 0.9,
                massMax: 1.1,
                occupancyMean: 0.2,
                varianceMean: 0.01,
                energyMean: 0.03,
                speedMean: 0.02,
                pathLength: 1.0,
                displacement: 1.0,
                sampleCount: 4,
                speedCount: 4,
                gyration: 1.0,
                centerVelocity: 0.01,
                velocityX: 0.0,
                velocityY: 0.0,
                headingRad: 0.0,
                isStable: true
            ),
            score: 0.5,
            scoreWeights: [:],
            configHash: "seed"
        )

        guard let artifact = try writeReplayExportArtifacts(
            exportRoot: bundleDir,
            baseConfig: baseConfig,
            searchConfig: searchConfig,
            creature: creature,
            runId: "holonomy-bundle",
            campaignId: nil,
            score: creature.score,
            filtersPassed: true,
            reason: "test"
        ) else {
            XCTFail("Expected strict replay bundle artifacts to be written.")
            return
        }
        try writeJSONL([artifact.record], to: bundleDir.appendingPathComponent("index.jsonl"))

        let loopURL = root.appendingPathComponent("loop.json")
        try writeJSON(
            [
                "version": 1,
                "name": "m-loop",
                "closed": true,
                "coordinates": ["m.0"],
                "vertices": [[0.12], [0.18]],
                "samples_per_segment": 1,
            ],
            to: loopURL
        )

        let outputURL = root.appendingPathComponent("output", isDirectory: true)
        let dbURL = root.appendingPathComponent("compendium.sqlite")
        _ = try runLeniaCLI(arguments: [
            "intervene",
            "holonomy",
            "--run-id", "holonomy-test-run",
            "--bundle", artifact.exportDir.path,
            "--loop", loopURL.path,
            "--output", outputURL.path,
            "--db", dbURL.path,
            "--export-enabled",
        ])

        let manifestURL = outputURL.appendingPathComponent("holonomy-manifest.json")
        let summaryURL = outputURL.appendingPathComponent("summary.json")
        XCTAssertTrue(FileManager.default.fileExists(atPath: manifestURL.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: summaryURL.path))

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .deferredToDate
        let manifest = try decoder.decode(HolonomyManifestFixture.self, from: Data(contentsOf: manifestURL))
        let summary = try decoder.decode(HolonomySummaryFixture.self, from: Data(contentsOf: summaryURL))

        XCTAssertEqual(manifest.version, 1)
        XCTAssertTrue(manifest.loopClosed)
        XCTAssertEqual(manifest.coordinatePaths, ["m.0"])
        XCTAssertEqual(manifest.stepManifestPaths.count, 3)
        XCTAssertEqual(manifest.campaignDirs.count, 3)
        XCTAssertTrue(manifest.exportEnabled)
        XCTAssertEqual(summary.loopName, "m-loop")
        XCTAssertTrue(summary.loopClosed)
        XCTAssertEqual(summary.coordinatePaths, ["m.0"])
        XCTAssertEqual(summary.pointCount, 3)
        XCTAssertEqual(summary.campaignCount, 3)
        XCTAssertEqual(summary.exportCount, 3)
        XCTAssertNotNil(summary.phenotypeClosureDistance)
        XCTAssertNotNil(summary.transportedStateClosureDistance)

        let firstCampaignDir = URL(fileURLWithPath: manifest.campaignDirs[0], isDirectory: true)
        XCTAssertTrue(FileManager.default.fileExists(atPath: firstCampaignDir.appendingPathComponent("config.json").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: firstCampaignDir.appendingPathComponent("search.json").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: firstCampaignDir.appendingPathComponent("results.jsonl").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: firstCampaignDir.appendingPathComponent("library/index.jsonl").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: firstCampaignDir.appendingPathComponent("holonomy-step.json").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: firstCampaignDir.appendingPathComponent("terminal-state.json").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputURL.appendingPathComponent("loop-spec.json").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: firstCampaignDir.appendingPathComponent("exports/index.jsonl").path))

        let db = try SQLiteDB(path: dbURL.path)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM runs WHERE run_id = 'holonomy-test-run'"), 1)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM specimens WHERE run_id = 'holonomy-test-run'"), 6)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM specimens WHERE run_id = 'holonomy-test-run' AND source_kind = 'result'"), 3)
        XCTAssertEqual(try db.scalarInt("SELECT COUNT(*) FROM specimens WHERE run_id = 'holonomy-test-run' AND source_kind = 'library'"), 3)
    }
}

private struct HolonomyManifestFixture: Codable {
    let version: Int
    let runId: String
    let bundlePath: String
    let loopPath: String
    let loopName: String?
    let loopClosed: Bool
    let coordinatePaths: [String]
    let configTopologyHash: String
    let campaignsDir: String
    let summaryPath: String
    let campaignDirs: [String]
    let stepManifestPaths: [String]
    let exportEnabled: Bool
    let replayedAt: Date

    enum CodingKeys: String, CodingKey {
        case version
        case runId = "run_id"
        case bundlePath = "bundle_path"
        case loopPath = "loop_path"
        case loopName = "loop_name"
        case loopClosed = "loop_closed"
        case coordinatePaths = "coordinate_paths"
        case configTopologyHash = "config_topology_hash"
        case campaignsDir = "campaigns_dir"
        case summaryPath = "summary_path"
        case campaignDirs = "campaign_dirs"
        case stepManifestPaths = "step_manifest_paths"
        case exportEnabled = "export_enabled"
        case replayedAt = "replayed_at"
    }
}

private struct HolonomySummaryFixture: Codable {
    let runId: String
    let bundlePath: String
    let loopPath: String
    let loopName: String?
    let loopClosed: Bool
    let coordinatePaths: [String]
    let pointCount: Int
    let outputDir: String
    let configTopologyHash: String
    let campaignCount: Int
    let exportCount: Int
    let phenotypeClosureDistance: Float?
    let transportedStateClosureDistance: Float?
    let replayedAt: Date

    enum CodingKeys: String, CodingKey {
        case runId = "run_id"
        case bundlePath = "bundle_path"
        case loopPath = "loop_path"
        case loopName = "loop_name"
        case loopClosed = "loop_closed"
        case coordinatePaths = "coordinate_paths"
        case pointCount = "point_count"
        case outputDir = "output_dir"
        case configTopologyHash = "config_topology_hash"
        case campaignCount = "campaign_count"
        case exportCount = "export_count"
        case phenotypeClosureDistance = "phenotype_closure_distance"
        case transportedStateClosureDistance = "transported_state_closure_distance"
        case replayedAt = "replayed_at"
    }
}
