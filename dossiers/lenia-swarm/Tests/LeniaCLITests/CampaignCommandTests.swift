import Foundation
import Logging
import SQLite3
import XCTest
@testable import LeniaCLIKit
@testable import LeniaCore

final class CampaignCommandTests: XCTestCase {
    func testCampaignCentralCompendiumResolvesPlainRelativePathFromConfigDirectoryWhenPresent() throws {
        let root = try makeTempDirectory(prefix: "lenia-campaign-central-db")
        defer { try? FileManager.default.removeItem(at: root) }

        let configDirectory = root.appendingPathComponent("configs/campaigns", isDirectory: true)
        let dossierRoot = root.appendingPathComponent("dossier", isDirectory: true)
        let outputURL = root.appendingPathComponent("output", isDirectory: true)
        try FileManager.default.createDirectory(at: configDirectory, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: dossierRoot, withIntermediateDirectories: true)
        _ = FileManager.default.createFile(
            atPath: configDirectory.appendingPathComponent("central.sqlite").path,
            contents: Data()
        )

        let resolved = try resolveCampaignCentralCompendiumPath(
            promotedPath: nil,
            configuredPath: "central.sqlite",
            outputURL: outputURL,
            campaignConfigDirectory: configDirectory,
            dossierRoot: dossierRoot
        )

        XCTAssertEqual(resolved, configDirectory.appendingPathComponent("central.sqlite").path)
    }

    func testCampaignCentralCompendiumUsesArtifactRootForCanonicalOutputPath() throws {
        let root = try makeTempDirectory(prefix: "lenia-campaign-central-canonical")
        defer { try? FileManager.default.removeItem(at: root) }
        let artifactRoot = root.appendingPathComponent("artifacts-root", isDirectory: true)
        setenv("SPCTR_LOCAL_ARTIFACT_ROOT", artifactRoot.path, 1)
        defer { unsetenv("SPCTR_LOCAL_ARTIFACT_ROOT") }

        let resolved = try resolveCampaignCentralCompendiumPath(
            promotedPath: nil,
            configuredPath: "outputs/compendium.sqlite",
            outputURL: root.appendingPathComponent("output", isDirectory: true),
            campaignConfigDirectory: root,
            dossierRoot: root.appendingPathComponent("dossier", isDirectory: true)
        )

        XCTAssertEqual(
            resolved,
            artifactRoot
                .appendingPathComponent(dossierName, isDirectory: true)
                .appendingPathComponent("outputs/compendium.sqlite")
                .path
        )
    }

    func testDiscoveryCampaignWritesBundleAndExportsBest() async throws {
        let root = try makeTempDirectory(prefix: "lenia-campaign-discovery")
        defer { try? FileManager.default.removeItem(at: root) }

        let searchConfigURL = root.appendingPathComponent("search-smoke.json")
        try writeJSON(
            [
                "count": 1,
                "seed_start": 17,
                "seed_stride": 1,
                "init_seed_offset": 0,
                "steps": 6,
                "record_interval": 3,
                "warmup_steps": 0,
                "occupancy_threshold": 0.05,
                "mass_channel": -1,
                "score_weights": [:] as [String: Double],
                "filters": [:] as [String: Double],
                "overrides": [:] as [String: Double],
                "top_k": 1,
                "batch_size": 1,
                "seeds_per_job": 1,
            ],
            to: searchConfigURL
        )

        let discoveryConfigURL = root.appendingPathComponent("discovery.json")
        try writeJSON(
            [
                "variants": [
                    [
                        "id": "smoke",
                        "config": dossierConfigsRoot().appendingPathComponent("base/paper_base_1c_128.json").path,
                        "search": searchConfigURL.path,
                        "count": 1,
                    ],
                ],
                "target_creatures": 1,
                "max_cycles": 1,
                "keep_best": 1,
                "rank_by": "score",
            ],
            to: discoveryConfigURL
        )

        let outputURL = root.appendingPathComponent("discovery-output", isDirectory: true)
        let result = try await runCampaign(
            request: CampaignExecutionRequest(
                runID: "campaign-discovery-test",
                preset: .discovery,
                configURL: discoveryConfigURL,
                outputURL: outputURL,
                seedLibraryURL: nil,
                seedQDConfigDirURL: nil,
                seedSelection: nil,
                backendRequest: "mlx",
                executionMode: .local,
                distributedControllerHost: nil,
                distributedControllerPort: 7337,
                distributedBindHost: "0.0.0.0",
                distributedBindPort: 0,
                exportBest: 1,
                promotion: ArchivePromotionConfig(compendiumPath: nil, warehousePath: nil, warehouseTopology: false)
            ),
            logger: Logger(label: "CampaignCommandTests.Discovery")
        )

        XCTAssertEqual(result.summary.totalJobs, 1)
        XCTAssertEqual(result.summary.completedRuns, 1)
        XCTAssertEqual(result.runs.count, 1)
        XCTAssertEqual(result.metrics.count, 1)
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputURL.appendingPathComponent("resolved-config.json").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputURL.appendingPathComponent("runs.jsonl").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputURL.appendingPathComponent("metrics.jsonl").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputURL.appendingPathComponent("summary.json").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputURL.appendingPathComponent("exports/index.jsonl").path))
    }

    func testSeededEcologyCampaignUsesExportedDiscoverySeeds() async throws {
        let root = try makeTempDirectory(prefix: "lenia-campaign-ecology")
        defer { try? FileManager.default.removeItem(at: root) }

        let ecologyConfigDirectory = try makeTinyEcologyConfigDirectory(at: root.appendingPathComponent("ecology-config", isDirectory: true))
        // Seed from the same base config the ecology runtime uses so the exported
        // creature's kernel routes match the runtime kernel routes; embedding is strict.
        let discoveryOutputURL = try await runTinyDiscoveryCampaign(
            at: root,
            baseConfigURL: ecologyConfigDirectory.appendingPathComponent("vanilla-base.json")
        )
        let ecologyConfigURL = root.appendingPathComponent("seeded-ecology.json")
        try writeJSON(
            [
                "config_dir": ecologyConfigDirectory.path,
                "variant_names": ["vanilla"],
                "mutation_probabilities": [0.1],
                "repeats": 1,
                "cohort_mode": "single-seed",
                "max_seeds_per_run": 1,
            ],
            to: ecologyConfigURL
        )

        let outputURL = root.appendingPathComponent("ecology-output", isDirectory: true)
        let result = try await runCampaign(
            request: CampaignExecutionRequest(
                runID: "campaign-ecology-test",
                preset: .seededEcology,
                configURL: ecologyConfigURL,
                outputURL: outputURL,
                seedLibraryURL: discoveryOutputURL.appendingPathComponent("exports/index.jsonl"),
                seedQDConfigDirURL: nil,
                seedSelection: ResearchSeedSelection(top: 1, rankBy: .score),
                backendRequest: "mlx",
                executionMode: .local,
                distributedControllerHost: nil,
                distributedControllerPort: 7337,
                distributedBindHost: "0.0.0.0",
                distributedBindPort: 0,
                exportBest: nil,
                promotion: ArchivePromotionConfig(compendiumPath: nil, warehousePath: nil, warehouseTopology: false)
            ),
            logger: Logger(label: "CampaignCommandTests.SeededEcology")
        )

        XCTAssertEqual(result.summary.totalJobs, 1)
        XCTAssertEqual(result.summary.completedRuns, 1)
        XCTAssertEqual(result.runs.count, 1)
        XCTAssertEqual(result.metrics.count, 1)
        XCTAssertEqual(result.runs.first?.executor, .ecology2025)
        let run = try XCTUnwrap(result.runs.first)
        let seedReference = try XCTUnwrap(run.seedReference)
        XCTAssertFalse(seedReference.name.isEmpty)
        XCTAssertTrue(run.runID.contains(sanitizeSeedComponent(seedReference.sourceID)))
        let ecologyIndexURL = outputURL.appendingPathComponent("ecology-runs/index.jsonl")
        XCTAssertTrue(FileManager.default.fileExists(atPath: ecologyIndexURL.path))
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .deferredToDate
        let lines = try String(contentsOf: ecologyIndexURL, encoding: .utf8)
            .split(separator: "\n")
            .map(String.init)
        XCTAssertEqual(lines.count, 1)
        let record = try decoder.decode(FlowLeniaEcology2025RunRecord.self, from: Data(lines[0].utf8))
        XCTAssertEqual(record.runID, run.runID)
        XCTAssertEqual(record.campaignID, "campaign-ecology-test")
        XCTAssertTrue(FileManager.default.fileExists(atPath: record.framesPath))
        XCTAssertTrue(FileManager.default.fileExists(atPath: record.payloadPath))
    }

    func testSeededEcologyCampaignRejectsUnknownVariantNames() async throws {
        let root = try makeTempDirectory(prefix: "lenia-campaign-variant-validation")
        defer { try? FileManager.default.removeItem(at: root) }

        let discoveryOutputURL = try await runTinyDiscoveryCampaign(at: root)
        let ecologyConfigDirectory = try makeTinyEcologyConfigDirectory(at: root.appendingPathComponent("ecology-config", isDirectory: true))
        let ecologyConfigURL = root.appendingPathComponent("invalid-seeded-ecology.json")
        try writeJSON(
            [
                "config_dir": ecologyConfigDirectory.path,
                "variant_names": ["vanilla", "ghost"],
                "mutation_probabilities": [0.1],
                "repeats": 1,
                "cohort_mode": "single-seed",
                "max_seeds_per_run": 1,
            ],
            to: ecologyConfigURL
        )

        await XCTAssertThrowsErrorAsync(
            try await runCampaign(
                request: CampaignExecutionRequest(
                    runID: "campaign-invalid-variant-test",
                    preset: .seededEcology,
                    configURL: ecologyConfigURL,
                    outputURL: root.appendingPathComponent("invalid-output", isDirectory: true),
                    seedLibraryURL: discoveryOutputURL.appendingPathComponent("exports/index.jsonl"),
                    seedQDConfigDirURL: nil,
                    seedSelection: ResearchSeedSelection(top: 1, rankBy: .score),
                    backendRequest: "mlx",
                    executionMode: .local,
                    distributedControllerHost: nil,
                    distributedControllerPort: 7337,
                    distributedBindHost: "0.0.0.0",
                    distributedBindPort: 0,
                    exportBest: nil,
                    promotion: ArchivePromotionConfig(compendiumPath: nil, warehousePath: nil, warehouseTopology: false)
                ),
                logger: Logger(label: "CampaignCommandTests.InvalidVariant")
            )
        ) { error in
            XCTAssertTrue(String(describing: error).contains("ghost"))
        }
    }

    func testInterventionBatteryWritesBaselineComparisons() async throws {
        let root = try makeTempDirectory(prefix: "lenia-campaign-intervention")
        defer { try? FileManager.default.removeItem(at: root) }

        let searchConfigURL = root.appendingPathComponent("search-intervention.json")
        try writeJSON(
            [
                "count": 1,
                "seed_start": 31,
                "seed_stride": 1,
                "init_seed_offset": 0,
                "steps": 10,
                "record_interval": 5,
                "warmup_steps": 0,
                "occupancy_threshold": 0.05,
                "mass_channel": -1,
                "score_weights": [:] as [String: Double],
                "filters": [:] as [String: Double],
                "overrides": [:] as [String: Double],
                "top_k": 1,
                "batch_size": 1,
                "seeds_per_job": 1,
            ],
            to: searchConfigURL
        )

        let interventionConfigURL = root.appendingPathComponent("intervention.json")
        try writeJSON(
            [
                "mode": "search",
                "base_config": dossierConfigsRoot().appendingPathComponent("base/paper_base_1c_128.json").path,
                "search_config": searchConfigURL.path,
                "warmup_steps": 2,
                "observation_steps": 6,
                "record_every_steps": 2,
                "repeats": 1,
                "environments": [
                    [
                        "id": "plain",
                        "overrides": [:] as [String: Double],
                    ],
                ],
                "perturbations": [
                    [
                        "id": "chem-shift",
                        "family": "chem_field_variant",
                        "overrides": ["params.seed": 99.0],
                        "payload": ["target_shift": 1.0],
                    ],
                ],
            ],
            to: interventionConfigURL
        )

        let outputURL = root.appendingPathComponent("intervention-output", isDirectory: true)
        let result = try await runCampaign(
            request: CampaignExecutionRequest(
                runID: "campaign-intervention-test",
                preset: .interventionBattery,
                configURL: interventionConfigURL,
                outputURL: outputURL,
                seedLibraryURL: nil,
                seedQDConfigDirURL: nil,
                seedSelection: nil,
                backendRequest: "mlx",
                executionMode: .local,
                distributedControllerHost: nil,
                distributedControllerPort: 7337,
                distributedBindHost: "0.0.0.0",
                distributedBindPort: 0,
                exportBest: nil,
                promotion: ArchivePromotionConfig(compendiumPath: nil, warehousePath: nil, warehouseTopology: false)
            ),
            logger: Logger(label: "CampaignCommandTests.Intervention")
        )

        XCTAssertEqual(result.summary.totalJobs, 2)
        XCTAssertEqual(result.summary.completedRuns, 2)
        XCTAssertEqual(result.events.count, 1)

        let baseline = try XCTUnwrap(result.metrics.first { $0.perturbationLabel == "baseline" })
        let intervention = try XCTUnwrap(result.metrics.first { $0.perturbationLabel == "chem-shift" })
        XCTAssertNil(baseline.massRetentionRatio)
        XCTAssertNotNil(intervention.massRetentionRatio)
        XCTAssertNotNil(intervention.postPerturbationDivergence)
        XCTAssertNotNil(intervention.returnToBaselineScore)
        XCTAssertNotNil(intervention.redirectedBehaviorScore)
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputURL.appendingPathComponent("events.jsonl").path))
    }
}

private func runTinyDiscoveryCampaign(
    at root: URL,
    baseConfigURL: URL = dossierConfigsRoot().appendingPathComponent("base/paper_base_1c_128.json")
) async throws -> URL {
    let searchConfigURL = root.appendingPathComponent("search-discovery.json")
    try writeJSON(
        [
            "count": 1,
            "seed_start": 5,
            "seed_stride": 1,
            "init_seed_offset": 0,
            "steps": 6,
            "record_interval": 3,
            "warmup_steps": 0,
            "occupancy_threshold": 0.05,
            "mass_channel": -1,
            "score_weights": [:] as [String: Double],
            "filters": [:] as [String: Double],
            "overrides": [:] as [String: Double],
            "top_k": 1,
            "batch_size": 1,
            "seeds_per_job": 1,
        ],
        to: searchConfigURL
    )

    let configURL = root.appendingPathComponent("discovery-for-seeds.json")
    try writeJSON(
        [
            "variants": [
                [
                    "id": "seed-source",
                    "config": baseConfigURL.path,
                    "search": searchConfigURL.path,
                    "count": 1,
                ],
            ],
            "target_creatures": 1,
            "max_cycles": 1,
            "keep_best": 1,
            "rank_by": "score",
        ],
        to: configURL
    )

    let outputURL = root.appendingPathComponent("seed-source-output", isDirectory: true)
    _ = try await runCampaign(
        request: CampaignExecutionRequest(
            runID: "campaign-seed-source",
            preset: .discovery,
            configURL: configURL,
            outputURL: outputURL,
            seedLibraryURL: nil,
            seedQDConfigDirURL: nil,
            seedSelection: nil,
            backendRequest: "mlx",
            executionMode: .local,
            distributedControllerHost: nil,
            distributedControllerPort: 7337,
            distributedBindHost: "0.0.0.0",
            distributedBindPort: 0,
            exportBest: 1,
            promotion: ArchivePromotionConfig(compendiumPath: nil, warehousePath: nil, warehouseTopology: false)
        ),
        logger: Logger(label: "CampaignCommandTests.SeedSource")
    )
    return outputURL
}

private func makeTinyEcologyConfigDirectory(at directory: URL) throws -> URL {
    let fileManager = FileManager.default
    try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)

    let sourceBaseURL = dossierConfigsRoot()
        .appendingPathComponent("papers/flowlenia-ecology-2025/vanilla-base.json")
    let baseData = try Data(contentsOf: sourceBaseURL)
    guard var baseJSON = try JSONSerialization.jsonObject(with: baseData) as? [String: Any] else {
        throw XCTSkip("Failed to decode ecology base config fixture.")
    }
    baseJSON["backend"] = "mlx"
    baseJSON["grid"] = ["sx": 128, "sy": 128]
    baseJSON["run"] = ["steps": 6]
    baseJSON["init"] = [
        "seed": 0,
        "patches": [["center": [64, 64], "size": 12]],
        "a_uniform": ["low": 0.0, "high": 1.0],
        "p_uniform": ["low": 0.0, "high": 1.0],
    ]
    try writeJSONObject(baseJSON, to: directory.appendingPathComponent("vanilla-base.json"))

    try writeJSON(
        [
            "paper": "flow-lenia-emergent-evolutionary-dynamics-2025",
            "grid_size": 128,
            "total_steps": 6,
            "record_every_steps": 2,
            "channels": 3,
            "kernels_per_channel_pair": 5,
            "repeats": 1,
            "mutation_probabilities": [0.1],
            "variants": ["vanilla"],
            "activity": [
                "enabled": true,
                "interval": 2,
                "threshold": 0.05,
                "maxComponents": 64,
                "matchThreshold": 1.5,
                "paramWeight": 1.0,
                "positionWeight": 0.05,
            ],
        ],
        to: directory.appendingPathComponent("simulation.json")
    )

    try writeJSON(
        [
            "name": "vanilla",
            "base_config": "vanilla-base.json",
            "init_patch_count": 1,
            "init_patch_size": 8,
            "init_param_mean": 0.0,
            "init_param_std": 0.25,
        ],
        to: directory.appendingPathComponent("vanilla.json")
    )

    return directory
}

final class DeclarativeCampaignTests: XCTestCase {
    func testCampaignConfigParsesAllPhaseTypes() throws {
        let json = """
        {
          "name": "test-campaign",
          "phases": [
            {
              "name": "qd-phase",
              "type": "qd",
              "algorithm": "me",
              "config_dir": "configs/papers/leniabreeder-2024",
              "seeds": [0, 1],
              "target": { "min_coverage": 0.5 }
            },
            {
              "name": "imgep-phase",
              "type": "imgep",
              "config": "configs/imgep/imgep_motile.json",
              "base_config": "configs/base/paper_base_1c_128.json",
              "search_config": "configs/search/search_motile.json",
              "target": { "iterations": 128 }
            },
            {
              "name": "sweep-phase",
              "type": "sweep",
              "manifest": "configs/sweeps/glider_sweeps.json",
              "target": { "creatures": 200, "max_cycles": 4 }
            },
            {
              "name": "intervention-phase",
              "type": "intervention-battery",
              "mode": "search",
              "seed_library": "outputs/exports/index.jsonl",
              "seed_top": 50,
              "seed_rank_by": "center_velocity"
            },
            {
              "name": "ecology-phase",
              "type": "ecology",
              "config_dir": "configs/papers/flowlenia-ecology-2025"
            },
            {
              "name": "curiosity-phase",
              "type": "curiosity",
              "config_dir": "configs/papers/ai-scientist-2025"
            }
          ],
          "compendium": {
            "merge_phases": true,
            "central_db": "outputs/compendium.sqlite"
          },
          "phase_isolation": true
        }
        """.data(using: .utf8)!

        let config = try JSONDecoder().decode(LeniaCampaignConfig.self, from: json)
        XCTAssertEqual(config.name, "test-campaign")
        XCTAssertEqual(config.phases.count, 6)
        XCTAssertEqual(config.phaseIsolation, true)
        XCTAssertEqual(config.compendium?.mergePhases, true)
        XCTAssertEqual(config.compendium?.centralDB, "outputs/compendium.sqlite")

        XCTAssertEqual(config.phases[0].type, .qd)
        XCTAssertEqual(config.phases[0].algorithm, "me")
        XCTAssertEqual(config.phases[0].seeds, [0, 1])
        XCTAssertEqual(config.phases[0].target?.minCoverage, 0.5)

        XCTAssertEqual(config.phases[1].type, .imgep)
        XCTAssertEqual(config.phases[1].target?.iterations, 128)

        XCTAssertEqual(config.phases[2].type, .sweep)
        XCTAssertEqual(config.phases[2].target?.creatures, 200)
        XCTAssertEqual(config.phases[2].target?.maxCycles, 4)

        XCTAssertEqual(config.phases[3].type, .interventionBattery)
        XCTAssertEqual(config.phases[3].seedTop, 50)
        XCTAssertEqual(config.phases[3].seedRankBy, "center_velocity")

        XCTAssertEqual(config.phases[4].type, .ecology)
        XCTAssertEqual(config.phases[5].type, .curiosity)
    }

    func testCampaignConfigParsesFromDisk() throws {
        let campaignsDir = dossierConfigsRoot()
            .deletingLastPathComponent()
            .appendingPathComponent("configs/campaigns", isDirectory: true)
        let fullDiscoveryURL = campaignsDir.appendingPathComponent("full-discovery.json")
        guard FileManager.default.fileExists(atPath: fullDiscoveryURL.path) else {
            throw XCTSkip("Campaign config not found at \(fullDiscoveryURL.path)")
        }
        let config = try JSONDecoder().decode(
            LeniaCampaignConfig.self,
            from: Data(contentsOf: fullDiscoveryURL)
        )
        XCTAssertEqual(config.name, "full-discovery-v2")
        XCTAssertEqual(config.phases.count, 4)
        XCTAssertEqual(config.phases[0].type, .qd)
        XCTAssertEqual(config.phases[1].type, .imgep)
        XCTAssertEqual(config.phases[2].type, .sweep)
        XCTAssertEqual(config.phases[3].type, .sweep)
    }

    func testCompendiumMergeDeduplicates() throws {
        let root = try makeTempDirectory(prefix: "lenia-compendium-merge")
        defer { try? FileManager.default.removeItem(at: root) }

        let db1Path = root.appendingPathComponent("phase1.sqlite").path
        let db2Path = root.appendingPathComponent("phase2.sqlite").path
        let centralPath = root.appendingPathComponent("central.sqlite").path

        let db1 = try SQLiteDB(path: db1Path)
        try db1.exec("""
            CREATE TABLE runs (
                run_id TEXT PRIMARY KEY,
                run_name TEXT NOT NULL,
                run_dir TEXT NOT NULL,
                indexed_at TEXT NOT NULL
            )
        """)
        try db1.exec("""
            INSERT INTO runs (run_id, run_name, run_dir, indexed_at)
            VALUES ('run-1', 'phase1-run', '/tmp/phase1', '2026-01-01')
        """)
        try db1.exec("""
            INSERT INTO runs (run_id, run_name, run_dir, indexed_at)
            VALUES ('run-shared', 'shared-run', '/tmp/shared', '2026-01-01')
        """)

        let db2 = try SQLiteDB(path: db2Path)
        try db2.exec("""
            CREATE TABLE runs (
                run_id TEXT PRIMARY KEY,
                run_name TEXT NOT NULL,
                run_dir TEXT NOT NULL,
                indexed_at TEXT NOT NULL
            )
        """)
        try db2.exec("""
            INSERT INTO runs (run_id, run_name, run_dir, indexed_at)
            VALUES ('run-2', 'phase2-run', '/tmp/phase2', '2026-01-02')
        """)
        try db2.exec("""
            INSERT INTO runs (run_id, run_name, run_dir, indexed_at)
            VALUES ('run-shared', 'shared-run-phase2', '/tmp/shared2', '2026-01-02')
        """)

        let logger = Logger(label: "CompendiumMergeTest")
        try mergeCompendiumDatabases(
            sources: [
                URL(fileURLWithPath: db1Path),
                URL(fileURLWithPath: db2Path),
            ],
            into: centralPath,
            logger: logger
        )

        let central = try SQLiteDB(path: centralPath)
        let rowCount = try central.scalarInt("SELECT count(*) FROM runs")
        XCTAssertEqual(rowCount, 3)

        let sharedName = try {
            let stmt = try central.prepare("SELECT run_name FROM runs WHERE run_id = 'run-shared'")
            defer { sqlite3_finalize(stmt) }
            guard sqlite3_step(stmt) == SQLITE_ROW,
                  let nameC = sqlite3_column_text(stmt, 0) else {
                XCTFail("Expected run-shared row")
                return ""
            }
            return String(cString: nameC)
        }()
        XCTAssertEqual(sharedName, "shared-run")
    }
}

private func sanitizeSeedComponent(_ value: String) -> String {
    value.lowercased().replacingOccurrences(of: "[^a-z0-9]+", with: "-", options: .regularExpression)
}

private func XCTAssertThrowsErrorAsync<T>(
    _ expression: @autoclosure () async throws -> T,
    _ verify: (Error) -> Void,
    file: StaticString = #filePath,
    line: UInt = #line
) async {
    do {
        _ = try await expression()
        XCTFail("Expected error to be thrown", file: file, line: line)
    } catch {
        verify(error)
    }
}
