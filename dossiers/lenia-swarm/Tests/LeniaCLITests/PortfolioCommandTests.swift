import CryptoKit
import Foundation
import LeniaCore
import XCTest
@testable import LeniaCLIKit

final class PortfolioCommandTests: XCTestCase {
    func testPortfolioInitLeaseAndStatus() throws {
        let root = try makeTempDirectory(prefix: "lenia-portfolio")
        defer { try? FileManager.default.removeItem(at: root) }

        let searchURL = root.appendingPathComponent("search.json")
        try writePortfolioSearchConfig(to: searchURL, steps: 2)

        let hostURL = root.appendingPathComponent("host", isDirectory: true)
        try runPortfolioInit(hostURL: hostURL, searchURL: searchURL, shards: 2, shardSize: 3)

        let leaseA = try runPortfolioLease(hostURL: hostURL, workerID: "worker-a")
        XCTAssertEqual(leaseA["campaign_id"] as? String, "portfolio-test")
        XCTAssertEqual(leaseA["universe_id"] as? String, "universe-test")
        XCTAssertEqual(leaseA["sampler_id"] as? String, "prior-random")
        XCTAssertEqual(leaseA["shard_index"] as? Int, 0)
        XCTAssertEqual((leaseA["seeds"] as? [Int])?.count, 3)

        let leaseB = try runPortfolioLease(hostURL: hostURL, workerID: "worker-b")
        XCTAssertEqual(leaseB["shard_index"] as? Int, 1)
        XCTAssertNotEqual(leaseA["seeds"] as? [Int], leaseB["seeds"] as? [Int])

        let status = try runPortfolioStatus(hostURL: hostURL)
        XCTAssertEqual(status["campaigns"] as? Int, 1)
        XCTAssertEqual(status["pending_shards"] as? Int, 0)
        XCTAssertEqual(status["leased_shards"] as? Int, 2)
        XCTAssertEqual(status["done_shards"] as? Int, 0)
        XCTAssertEqual(status["candidate_count"] as? Int, 0)
        XCTAssertEqual(status["genotype_count"] as? Int, 0)
        XCTAssertEqual(status["fingerprint_count"] as? Int, 0)
        let emptyArchive = try XCTUnwrap(status["archive"] as? [String: Any])
        XCTAssertEqual(emptyArchive["representative_count"] as? Int, 0)
        XCTAssertEqual(emptyArchive["representative_niches"] as? [String], [])
    }

    func testPortfolioWorkerWritesBundlesAndRebuildsIndex() throws {
        let root = try makeTempDirectory(prefix: "lenia-portfolio-worker")
        defer { try? FileManager.default.removeItem(at: root) }

        let searchURL = root.appendingPathComponent("search.json")
        try writePortfolioSearchConfig(to: searchURL, steps: 2)
        let hostURL = root.appendingPathComponent("host", isDirectory: true)
        try runPortfolioInit(hostURL: hostURL, searchURL: searchURL, shards: 1, shardSize: 1)

        _ = try runLeniaCLI(arguments: [
            "orchestrate", "portfolio", "worker",
            "--host", hostURL.path,
            "--worker-id", "worker-a",
            "--ttl-seconds", "60",
            "--max-shards", "1",
        ])

        let status = try runPortfolioStatus(hostURL: hostURL)
        XCTAssertEqual(status["done_shards"] as? Int, 1)
        XCTAssertEqual(status["candidate_count"] as? Int, 1)
        XCTAssertEqual(status["genotype_count"] as? Int, 1)
        XCTAssertEqual(status["fingerprint_count"] as? Int, 1)
        let archive = try XCTUnwrap(status["archive"] as? [String: Any])
        XCTAssertEqual(archive["representative_count"] as? Int, 1)
        XCTAssertEqual(archive["representative_niches"] as? [String], ["single-compact"])
        let representatives = try XCTUnwrap(archive["representatives"] as? [[String: Any]])
        XCTAssertEqual(representatives.count, 1)
        XCTAssertEqual(representatives[0]["niche"] as? String, "single-compact")
        XCTAssertNotNil(representatives[0]["source_id"] as? String)

        let candidatesRoot = hostURL.appendingPathComponent("artifacts/candidates", isDirectory: true)
        let manifests = try findPortfolioBundleManifests(under: candidatesRoot)
        XCTAssertEqual(manifests.count, 1)
        let manifest = try readJSONObject(from: manifests[0])
        XCTAssertEqual(manifest["bundle_kind"] as? String, "portfolio_candidate_bundle_v1")
        XCTAssertEqual(manifest["worker_id"] as? String, "worker-a")
        XCTAssertEqual((manifest["content_hash_inputs"] as? [String]) ?? [], [
            "universe.json",
            "sampler.json",
            "candidate.json",
            "metrics.json",
            "terminal_state_patch.json",
        ])
        let terminalPatchURL = manifests[0]
            .deletingLastPathComponent()
            .appendingPathComponent("terminal_state_patch.json")
        XCTAssertTrue(FileManager.default.fileExists(atPath: terminalPatchURL.path))

        let seedExportURL = root.appendingPathComponent("exported-patches.jsonl")
        _ = try runLeniaCLI(arguments: [
            "orchestrate", "portfolio", "export-seeds",
            "--host", hostURL.path,
            "--output", seedExportURL.path,
            "--limit", "4",
        ])
        let exportedSeeds = try String(contentsOf: seedExportURL, encoding: .utf8)
            .split(separator: "\n")
        XCTAssertEqual(exportedSeeds.count, 1)
        let exportedSeed = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(String(exportedSeeds[0]).utf8)) as? [String: Any]
        )
        XCTAssertEqual(exportedSeed["channels"] as? Int, 1)
        XCTAssertEqual(exportedSeed["sourceID"] as? String, "portfolio-\((manifest["content_hash"] as? String ?? "").prefix(16))")

        let warmStartedHostURL = root.appendingPathComponent("warm-started-host", isDirectory: true)
        _ = try runLeniaCLI(arguments: [
            "orchestrate", "portfolio", "init",
            "--campaign-id", "portfolio-export-warm-start-test",
            "--universe-id", "universe-test",
            "--sampler-id", "exported-seed-prior",
            "--config", dossierConfigsRoot().appendingPathComponent("base/paper_base_1c_128.json").path,
            "--search", searchURL.path,
            "--output", warmStartedHostURL.path,
            "--shards", "1",
            "--shard-size", "1",
            "--seed-library", seedExportURL.path,
            "--seed-top", "1",
        ])
        let warmStartedStatus = try runPortfolioStatus(hostURL: warmStartedHostURL)
        XCTAssertEqual(warmStartedStatus["seed_patch_count"] as? Int, 1)

        _ = try runLeniaCLI(arguments: [
            "orchestrate", "portfolio", "rebuild",
            "--host", hostURL.path,
        ])
        let rebuiltStatus = try runPortfolioStatus(hostURL: hostURL)
        XCTAssertEqual(rebuiltStatus["candidate_count"] as? Int, 1)
        XCTAssertEqual(rebuiltStatus["genotype_count"] as? Int, 1)
        XCTAssertEqual(rebuiltStatus["fingerprint_count"] as? Int, 1)
        let rebuiltArchive = try XCTUnwrap(rebuiltStatus["archive"] as? [String: Any])
        XCTAssertEqual(rebuiltArchive["representative_count"] as? Int, 1)

        let mediaURL = root.appendingPathComponent("media", isDirectory: true)
        let fakeFFmpeg = try writeFakeFFmpeg(to: root)
        _ = try runLeniaCLI(arguments: [
            "publish", "media",
            "--input", hostURL.path,
            "--output", mediaURL.path,
            "--top", "1",
            "--frame-budget", "2",
            "--steps", "3",
            "--ffmpeg", fakeFFmpeg.path,
        ])
        let mediaIndex = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(contentsOf: mediaURL.appendingPathComponent("index.json"))) as? [[String: Any]]
        )
        XCTAssertEqual(mediaIndex.count, 1)
        XCTAssertEqual(mediaIndex[0]["sourceMode"] as? String, "portfolio-candidate")
        XCTAssertEqual(mediaIndex[0]["selectionReason"] as? String, "single-compact")
        let framesPath = try XCTUnwrap(mediaIndex[0]["framesPath"] as? String)
        let colorFramesPath = try XCTUnwrap(mediaIndex[0]["framesColorPath"] as? String)
        XCTAssertNotEqual(framesPath, colorFramesPath)
        XCTAssertFalse(try FileManager.default.contentsOfDirectory(atPath: framesPath).isEmpty)
        XCTAssertFalse(try FileManager.default.contentsOfDirectory(atPath: colorFramesPath).isEmpty)
        let videoPath = try XCTUnwrap(mediaIndex[0]["videoPath"] as? String)
        XCTAssertTrue(FileManager.default.fileExists(atPath: videoPath))
    }

    func testPortfolioWorkerDrainsMultipleShards() throws {
        let root = try makeTempDirectory(prefix: "lenia-portfolio-worker-drain")
        defer { try? FileManager.default.removeItem(at: root) }

        let searchURL = root.appendingPathComponent("search.json")
        try writePortfolioSearchConfig(to: searchURL, steps: 2)
        let hostURL = root.appendingPathComponent("host", isDirectory: true)
        try runPortfolioInit(hostURL: hostURL, searchURL: searchURL, shards: 2, shardSize: 1)

        _ = try runLeniaCLI(arguments: [
            "orchestrate", "portfolio", "worker",
            "--host", hostURL.path,
            "--worker-id", "worker-drain",
            "--ttl-seconds", "60",
            "--max-shards", "2",
        ])

        let status = try runPortfolioStatus(hostURL: hostURL)
        XCTAssertEqual(status["pending_shards"] as? Int, 0)
        XCTAssertEqual(status["leased_shards"] as? Int, 0)
        XCTAssertEqual(status["done_shards"] as? Int, 2)
        XCTAssertEqual(status["candidate_count"] as? Int, 2)
    }

    func testPortfolioWorkersLeaseDistinctShardsConcurrently() throws {
        let root = try makeTempDirectory(prefix: "lenia-portfolio-worker-concurrent")
        defer { try? FileManager.default.removeItem(at: root) }

        let searchURL = root.appendingPathComponent("search.json")
        try writePortfolioSearchConfig(to: searchURL, steps: 2)
        let hostURL = root.appendingPathComponent("host", isDirectory: true)
        try runPortfolioInit(hostURL: hostURL, searchURL: searchURL, shards: 6, shardSize: 1)

        let group = DispatchGroup()
        let results = ConcurrentWorkerResults()
        for workerIndex in 0..<4 {
            group.enter()
            DispatchQueue.global(qos: .userInitiated).async {
                defer { group.leave() }
                do {
                    let output = try runLeniaCLI(arguments: [
                        "orchestrate", "portfolio", "worker",
                        "--host", hostURL.path,
                        "--worker-id", "worker-\(workerIndex)",
                        "--ttl-seconds", "60",
                        "--max-shards", "2",
                    ])
                    results.appendOutput(output)
                } catch {
                    results.appendError(String(describing: error))
                }
            }
        }

        XCTAssertEqual(group.wait(timeout: .now() + 30), .success)
        let snapshot = results.snapshot()
        XCTAssertEqual(snapshot.errors, [])
        XCTAssertEqual(snapshot.outputs.count, 4)

        let status = try runPortfolioStatus(hostURL: hostURL)
        XCTAssertEqual(status["pending_shards"] as? Int, 0)
        XCTAssertEqual(status["leased_shards"] as? Int, 0)
        XCTAssertEqual(status["done_shards"] as? Int, 6)
        XCTAssertEqual(status["candidate_count"] as? Int, 6)
        XCTAssertGreaterThanOrEqual(status["genotype_count"] as? Int ?? 0, 1)
        XCTAssertGreaterThanOrEqual(status["fingerprint_count"] as? Int ?? 0, 1)
        let archive = try XCTUnwrap(status["archive"] as? [String: Any])
        XCTAssertEqual(archive["representative_count"] as? Int, 6)
        XCTAssertGreaterThanOrEqual((archive["representative_niches"] as? [String])?.count ?? 0, 1)

        let manifests = try findPortfolioBundleManifests(under: hostURL.appendingPathComponent("artifacts/candidates", isDirectory: true))
        let shardIndexes = try manifests.map { try XCTUnwrap(readJSONObject(from: $0)["shard_index"] as? Int) }
        XCTAssertEqual(Set(shardIndexes), Set(0..<6))
    }

    func testPortfolioSeedLibraryCyclesWarmStartsAcrossShards() throws {
        let root = try makeTempDirectory(prefix: "lenia-portfolio-seeds")
        defer { try? FileManager.default.removeItem(at: root) }

        let searchURL = root.appendingPathComponent("search.json")
        try writePortfolioSearchConfig(to: searchURL, steps: 2)
        let seedURL = root.appendingPathComponent("patches.jsonl")
        try writeSeedPatchLibrary(to: seedURL)
        let hostURL = root.appendingPathComponent("host", isDirectory: true)

        _ = try runLeniaCLI(arguments: [
            "orchestrate", "portfolio", "init",
            "--campaign-id", "portfolio-seeded-test",
            "--universe-id", "universe-test",
            "--sampler-id", "seeded-prior",
            "--config", dossierConfigsRoot().appendingPathComponent("base/paper_base_1c_128.json").path,
            "--search", searchURL.path,
            "--output", hostURL.path,
            "--shards", "3",
            "--shard-size", "1",
            "--seed-library", seedURL.path,
            "--seed-top", "2",
            "--seed-rank-by", "score",
        ])

        let leaseA = try runPortfolioLease(hostURL: hostURL, workerID: "worker-a")
        let leaseB = try runPortfolioLease(hostURL: hostURL, workerID: "worker-b")
        let leaseC = try runPortfolioLease(hostURL: hostURL, workerID: "worker-c")

        XCTAssertEqual(leaseA["sampler_id"] as? String, "seeded-prior")
        XCTAssertEqual(leaseA["sampler_kind"] as? String, "seed-library-prior")
        XCTAssertEqual(leaseA["seed_patch_index"] as? Int, 0)
        XCTAssertEqual(leaseB["seed_patch_index"] as? Int, 1)
        XCTAssertEqual(leaseC["seed_patch_index"] as? Int, 0)
        XCTAssertEqual((leaseA["seed_patch"] as? [String: Any])?["sourceID"] as? String, "seed-b")

        let status = try runPortfolioStatus(hostURL: hostURL)
        XCTAssertEqual(status["seed_patch_count"] as? Int, 2)
    }

    func testPortfolioSeededWorkerEmbedsSeedPatchInCandidateBundle() throws {
        let root = try makeTempDirectory(prefix: "lenia-portfolio-seeded-bundle")
        defer { try? FileManager.default.removeItem(at: root) }

        let searchURL = root.appendingPathComponent("search.json")
        try writePortfolioSearchConfig(to: searchURL, steps: 2)
        let seedURL = root.appendingPathComponent("patches.jsonl")
        try writeSeedPatchLibrary(to: seedURL)
        let hostURL = root.appendingPathComponent("host", isDirectory: true)

        _ = try runLeniaCLI(arguments: [
            "orchestrate", "portfolio", "init",
            "--campaign-id", "portfolio-seeded-bundle-test",
            "--universe-id", "universe-test",
            "--sampler-id", "seeded-prior",
            "--config", dossierConfigsRoot().appendingPathComponent("base/paper_base_1c_128.json").path,
            "--search", searchURL.path,
            "--output", hostURL.path,
            "--shards", "1",
            "--shard-size", "1",
            "--seed-library", seedURL.path,
            "--seed-top", "1",
        ])
        _ = try runLeniaCLI(arguments: [
            "orchestrate", "portfolio", "worker",
            "--host", hostURL.path,
            "--worker-id", "worker-seeded",
            "--ttl-seconds", "60",
            "--max-shards", "1",
        ])

        let manifests = try findPortfolioBundleManifests(under: hostURL.appendingPathComponent("artifacts/candidates", isDirectory: true))
        XCTAssertEqual(manifests.count, 1)
        let bundleDir = manifests[0].deletingLastPathComponent()
        XCTAssertTrue(FileManager.default.fileExists(atPath: bundleDir.appendingPathComponent("seed_patch.json").path))
        let manifest = try readJSONObject(from: manifests[0])
        XCTAssertTrue(((manifest["content_hash_inputs"] as? [String]) ?? []).contains("seed_patch.json"))
    }

    func testPortfolioMediaClampsWarmupForShortReplaySteps() throws {
        let root = try makeTempDirectory(prefix: "lenia-portfolio-media-warmup")
        defer { try? FileManager.default.removeItem(at: root) }

        let searchURL = root.appendingPathComponent("search.json")
        try writePortfolioSearchConfig(to: searchURL, steps: 4, warmupSteps: 3)
        let hostURL = root.appendingPathComponent("host", isDirectory: true)
        try runPortfolioInit(hostURL: hostURL, searchURL: searchURL, shards: 1, shardSize: 1)
        _ = try runLeniaCLI(arguments: [
            "orchestrate", "portfolio", "worker",
            "--host", hostURL.path,
            "--worker-id", "worker-warmup",
            "--ttl-seconds", "60",
            "--max-shards", "1",
        ])
        let bundle = try XCTUnwrap(discoverPortfolioCandidateBundles(from: hostURL, top: 1).first)
        let replaySearch = portfolioReplaySearchConfig(bundle: bundle, steps: 100, frameBudget: 6)
        XCTAssertEqual(replaySearch.recordInterval, 16)

        let mediaURL = root.appendingPathComponent("media", isDirectory: true)
        let fakeFFmpeg = try writeFakeFFmpeg(to: root)
        _ = try runLeniaCLI(arguments: [
            "publish", "media",
            "--input", hostURL.path,
            "--output", mediaURL.path,
            "--top", "1",
            "--frame-budget", "2",
            "--steps", "2",
            "--ffmpeg", fakeFFmpeg.path,
        ])
        let mediaIndex = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(contentsOf: mediaURL.appendingPathComponent("index.json"))) as? [[String: Any]]
        )
        XCTAssertEqual(mediaIndex.count, 1)
        XCTAssertEqual(mediaIndex[0]["frames"] as? Int, 2)
        let framesPath = try XCTUnwrap(mediaIndex[0]["framesPath"] as? String)
        let colorFramesPath = try XCTUnwrap(mediaIndex[0]["framesColorPath"] as? String)
        XCTAssertNotEqual(framesPath, colorFramesPath)
        XCTAssertFalse(try FileManager.default.contentsOfDirectory(atPath: framesPath).isEmpty)
        XCTAssertFalse(try FileManager.default.contentsOfDirectory(atPath: colorFramesPath).isEmpty)
    }

    func testPortfolioReplayPreservesParameterEmbeddingPatches() throws {
        let root = try makeTempDirectory(prefix: "lenia-portfolio-media-pe")
        defer { try? FileManager.default.removeItem(at: root) }

        let searchURL = root.appendingPathComponent("search.json")
        try writePortfolioSearchConfig(to: searchURL, steps: 2)
        let seedURL = root.appendingPathComponent("patches.jsonl")
        try writeSeedPatchLibrary(to: seedURL)
        let hostURL = root.appendingPathComponent("host", isDirectory: true)

        _ = try runLeniaCLI(arguments: [
            "orchestrate", "portfolio", "init",
            "--campaign-id", "portfolio-pe-replay-test",
            "--universe-id", "universe-test",
            "--sampler-id", "seeded-prior",
            "--config", dossierConfigsRoot().appendingPathComponent("base/paper_base_pe_1c_128.json").path,
            "--search", searchURL.path,
            "--output", hostURL.path,
            "--shards", "1",
            "--shard-size", "1",
            "--seed-library", seedURL.path,
            "--seed-top", "1",
        ])
        _ = try runLeniaCLI(arguments: [
            "orchestrate", "portfolio", "worker",
            "--host", hostURL.path,
            "--worker-id", "worker-pe",
            "--ttl-seconds", "60",
            "--max-shards", "1",
        ])

        let bundle = try XCTUnwrap(discoverPortfolioCandidateBundles(from: hostURL, top: 1).first)
        let replayBase = try portfolioReplayBaseConfig(bundle: bundle, steps: 2)
        XCTAssertTrue(replayBase.parameter_embedding.enabled)
        XCTAssertEqual(replayBase.`init`.patches.count, 1)
        XCTAssertNotNil(replayBase.`init`.state_patch)
    }

    func testPortfolioOpenESWorkerWritesBestCandidateBundle() throws {
        let root = try makeTempDirectory(prefix: "lenia-portfolio-openes")
        defer { try? FileManager.default.removeItem(at: root) }

        let esURL = root.appendingPathComponent("es.json")
        try writeTinyESConfig(to: esURL, outputDir: root.appendingPathComponent("unused-es-output").path)
        let hostURL = root.appendingPathComponent("host", isDirectory: true)

        _ = try runLeniaCLI(arguments: [
            "orchestrate", "portfolio", "init",
            "--campaign-id", "portfolio-openes-test",
            "--universe-id", "universe-test",
            "--sampler-id", "openes-test",
            "--config", dossierConfigsRoot().appendingPathComponent("base/paper_base_1c_128.json").path,
            "--es", esURL.path,
            "--output", hostURL.path,
            "--shards", "1",
            "--shard-size", "1",
        ])

        _ = try runLeniaCLI(arguments: [
            "orchestrate", "portfolio", "worker",
            "--host", hostURL.path,
            "--worker-id", "worker-openes",
            "--ttl-seconds", "60",
            "--max-shards", "1",
        ])

        let status = try runPortfolioStatus(hostURL: hostURL)
        XCTAssertEqual(status["done_shards"] as? Int, 1)
        XCTAssertEqual(status["candidate_count"] as? Int, 1)
        let manifests = try findPortfolioBundleManifests(under: hostURL.appendingPathComponent("artifacts/candidates", isDirectory: true))
        XCTAssertEqual(manifests.count, 1)
        let sampler = try readJSONObject(from: manifests[0].deletingLastPathComponent().appendingPathComponent("sampler.json"))
        XCTAssertEqual(sampler["sampler_kind"] as? String, "openes")
        let candidate = try readJSONObject(from: manifests[0].deletingLastPathComponent().appendingPathComponent("candidate.json"))
        XCTAssertEqual(
            candidate["seed"] as? Int,
            expectedPortfolioSeed(
                universeID: "universe-test",
                campaignID: "portfolio-openes-test",
                samplerID: "openes-test",
                shardIndex: 0,
                localIndex: 0
            )
        )
    }

    private func runPortfolioInit(hostURL: URL, searchURL: URL, shards: Int, shardSize: Int) throws {
        _ = try runLeniaCLI(arguments: [
            "orchestrate", "portfolio", "init",
            "--campaign-id", "portfolio-test",
            "--universe-id", "universe-test",
            "--sampler-id", "prior-random",
            "--config", dossierConfigsRoot().appendingPathComponent("base/paper_base_1c_128.json").path,
            "--search", searchURL.path,
            "--output", hostURL.path,
            "--shards", String(shards),
            "--shard-size", String(shardSize),
        ])
    }

    private func runPortfolioLease(hostURL: URL, workerID: String) throws -> [String: Any] {
        let output = try runLeniaCLI(arguments: [
            "orchestrate", "portfolio", "lease",
            "--host", hostURL.path,
            "--worker-id", workerID,
            "--ttl-seconds", "60",
        ])
        return try parseJSONObject(output)
    }

    private func runPortfolioStatus(hostURL: URL) throws -> [String: Any] {
        let output = try runLeniaCLI(arguments: [
            "orchestrate", "portfolio", "status",
            "--host", hostURL.path,
        ])
        return try parseJSONObject(output)
    }

    private func writePortfolioSearchConfig(to url: URL, steps: Int, warmupSteps: Int = 0) throws {
        try writeJSON(
            [
                "count": 1,
                "seed_start": 0,
                "seed_stride": 1,
                "init_seed_offset": 0,
                "steps": steps,
                "record_interval": 1,
                "warmup_steps": warmupSteps,
                "occupancy_threshold": 0.05,
                "mass_channel": -1,
                "score_weights": [:] as [String: Double],
                "filters": [:] as [String: Double],
                "overrides": [:] as [String: Double],
                "top_k": 1,
                "batch_size": 1,
                "seeds_per_job": 1,
            ],
            to: url
        )
    }

    private func writeSeedPatchLibrary(to url: URL) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let patches = [
            ResearchSeedPatch(
                sourceID: "seed-a",
                name: "seed-a",
                width: 8,
                height: 8,
                channels: 1,
                data: Array(repeating: Float(0.2), count: 64),
                score: 1.0
            ),
            ResearchSeedPatch(
                sourceID: "seed-b",
                name: "seed-b",
                width: 8,
                height: 8,
                channels: 1,
                data: Array(repeating: Float(0.4), count: 64),
                score: 2.0
            ),
        ]
        let payload = try patches
            .map { String(decoding: try encoder.encode($0), as: UTF8.self) }
            .joined(separator: "\n")
        try Data((payload + "\n").utf8).write(to: url)
    }

    private func writeTinyESConfig(to url: URL, outputDir: String) throws {
        try writeJSON(
            [
                "output_dir": outputDir,
                "generations": 1,
                "population": 2,
                "sigma": 0.05,
                "learning_rate": 0.01,
                "seed": 17,
                "steps": 2,
                "fitness": [
                    "objective": "directed_motion",
                    "target_step": 1,
                    "angle_threshold": 0.01,
                    "gyration_penalty": 0.5,
                ] as [String: Any],
                "fitness_shaping": "raw",
                "init_patch": [
                    "enabled": true,
                    "size": 40,
                    "center": [64, 64],
                    "value_low": 0.0,
                    "value_high": 1.0,
                ] as [String: Any],
                "param_ranges": NSNull(),
            ] as [String: Any],
            to: url
        )
    }

    private func writeFakeFFmpeg(to root: URL) throws -> URL {
        let url = root.appendingPathComponent("fake-ffmpeg")
        let script = """
        #!/bin/sh
        for output_path do
          :
        done
        printf 'fake mp4\\n' > "$output_path"
        """
        try Data(script.utf8).write(to: url)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: url.path)
        return url
    }

    private func parseJSONObject(_ output: String) throws -> [String: Any] {
        let start = try XCTUnwrap(output.firstIndex(of: "{"))
        let end = try XCTUnwrap(output.lastIndex(of: "}"))
        let jsonText = String(output[start...end])
        return try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(jsonText.utf8)) as? [String: Any]
        )
    }

    private func readJSONObject(from url: URL) throws -> [String: Any] {
        try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
    }

    private func findPortfolioBundleManifests(under root: URL) throws -> [URL] {
        guard let enumerator = FileManager.default.enumerator(
            at: root,
            includingPropertiesForKeys: [.isRegularFileKey],
            options: [.skipsHiddenFiles]
        ) else {
            return []
        }
        return enumerator.compactMap { item in
            guard let url = item as? URL, url.lastPathComponent == "manifest.json" else { return nil }
            return url
        }
    }

    private func expectedPortfolioSeed(
        universeID: String,
        campaignID: String,
        samplerID: String,
        shardIndex: Int,
        localIndex: Int
    ) -> Int {
        let key = "\(universeID)\u{0}\(campaignID)\u{0}\(samplerID)\u{0}\(shardIndex)\u{0}\(localIndex)"
        let digest = SHA256.hash(data: Data(key.utf8))
        var value: UInt64 = 0
        for byte in digest.prefix(8) {
            value = (value << 8) | UInt64(byte)
        }
        return Int(value & 0x7FFF_FFFF_FFFF_FFFF)
    }
}

private final class ConcurrentWorkerResults: @unchecked Sendable {
    private let lock = NSLock()
    private var outputs: [String] = []
    private var errors: [String] = []

    func appendOutput(_ output: String) {
        lock.lock()
        defer { lock.unlock() }
        outputs.append(output)
    }

    func appendError(_ error: String) {
        lock.lock()
        defer { lock.unlock() }
        errors.append(error)
    }

    func snapshot() -> (outputs: [String], errors: [String]) {
        lock.lock()
        defer { lock.unlock() }
        return (outputs, errors)
    }
}
