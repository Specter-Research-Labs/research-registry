import ArgumentParser
import DistributedCluster
import Foundation
import Logging
import XCTest
@testable import LeniaCLIKit
@testable import LeniaCore

final class DistributedCampaignTests: XCTestCase {
    func testClusterOptionsRequireDistributed() throws {
        for extra in [["--host", "127.0.0.1"], ["--port", "7400"], ["--min-workers", "2"]] {
            XCTAssertThrowsError(try CampaignCommand.parse(["--campaign", "c.json", "-o", "out"] + extra)) { error in
                XCTAssertTrue(CampaignCommand.message(for: error).contains("require --distributed"))
            }
        }
        XCTAssertThrowsError(try CampaignCommand.parse(["--campaign", "c.json", "-o", "out", "--distributed", "--min-workers", "0"]))
        XCTAssertThrowsError(try CampaignCommand.parse(["--campaign", "c.json", "-o", "out", "--distributed", "--port", "70000"]))
        let command = try CampaignCommand.parse([
            "--campaign", "c.json", "-o", "out", "--distributed", "--host", "127.0.0.1", "--port", "7400", "--min-workers", "2",
        ])
        XCTAssertTrue(command.distributed)
        XCTAssertEqual(command.port, 7400)
        XCTAssertEqual(command.minWorkers, 2)
    }

    func testDistributedRejectsPhasesThatRunInProcess() throws {
        let phases = try JSONDecoder().decode([LeniaCampaignPhaseConfig].self, from: Data("""
        [
          {"name": "sweep-phase", "type": "sweep", "manifest": "m.json"},
          {"name": "qd-phase", "type": "qd", "config_dir": "q"},
          {"name": "curiosity-phase", "type": "curiosity", "config_dir": "c"}
        ]
        """.utf8))
        XCTAssertThrowsError(try validateDistributedCampaignPhases(phases)) { error in
            let message = String(describing: error)
            XCTAssertTrue(message.contains("qd-phase"))
            XCTAssertTrue(message.contains("curiosity-phase"))
            XCTAssertFalse(message.contains("sweep-phase"))
        }
        XCTAssertNoThrow(try validateDistributedCampaignPhases([phases[0]]))
    }

    func testDistributedSweepMatchesLocalRun() async throws {
        let root = try makeTempDirectory(prefix: "lenia-campaign-distributed")
        defer { try? FileManager.default.removeItem(at: root) }

        let searchConfigURL = root.appendingPathComponent("search.json")
        try writeJSON(
            [
                "count": 2,
                "seed_start": 41,
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
                "top_k": 2,
                "batch_size": 1,
                "seeds_per_job": 1,
            ],
            to: searchConfigURL
        )
        let baseConfigPath = dossierConfigsRoot().appendingPathComponent("base/paper_base_1c_128.json").path
        let manifestURL = root.appendingPathComponent("sweep.json")
        try writeJSON(
            [
                "variants": [
                    ["id": "a", "config": baseConfigPath, "search": searchConfigURL.path, "count": 2],
                    ["id": "b", "config": baseConfigPath, "search": searchConfigURL.path, "count": 2],
                ],
                "target_creatures": 2,
                "max_cycles": 1,
                "keep_best": 2,
                "rank_by": "score",
            ],
            to: manifestURL
        )
        let phase: [String: Any] = ["name": "sweep", "type": "sweep", "manifest": manifestURL.path]

        let localURL = root.appendingPathComponent("local", isDirectory: true)
        _ = try await runTinyCampaignPhase(phase, root: root, outputURL: localURL, runID: "campaign-distributed-test")

        let port = try unusedLocalPort()
        let system = await ClusterSystem("LeniaCLITestsCampaign") { settings in
            settings.bindPort = port
            settings.swim.probeInterval = .seconds(1)
            settings.swim.pingTimeout = .milliseconds(500)
            settings.remoteCall.defaultTimeout = .seconds(120)
        }
        let pool = CampaignWorkerPool(
            system: system,
            logger: Logger(label: "DistributedCampaignTests.Pool"),
            runContext: RunContext(runId: "campaign-distributed-test", controllerId: "test-controller")
        )
        let worker = LeniaWorker(actorSystem: system, workerId: "campaign-test-worker")
        let distributedURL = root.appendingPathComponent("distributed", isDirectory: true)
        do {
            async let started: Void = pool.start(minWorkers: 1)
            await system.receptionist.checkIn(worker, with: .leniaWorkers)
            try await started
            _ = try await runTinyCampaignPhase(
                phase,
                root: root,
                outputURL: distributedURL,
                runID: "campaign-distributed-test",
                executionMode: .distributed(pool)
            )
        } catch {
            await pool.stop()
            try system.shutdown()
            throw error
        }
        await pool.stop()
        try system.shutdown()

        let runs = try readCampaignJSONLines(LeniaCampaignRunRecord.self, at: distributedURL.appendingPathComponent("runs.jsonl"))
        XCTAssertEqual(runs.count, 4)
        XCTAssertEqual(Set(runs.compactMap(\.workerID)), ["campaign-test-worker"])
        XCTAssertTrue(runs.allSatisfy { $0.status == .completed })

        // Export directories and index rows carry a fresh creature UUID and export timestamp on
        // every run, local or not, so they are compared by count; the smoke script masks them.
        for name in ["runs.jsonl", "metrics.jsonl", "results.jsonl", "resolved-config.json"] {
            let local = try String(contentsOf: localURL.appendingPathComponent(name), encoding: .utf8)
            var distributed = try String(contentsOf: distributedURL.appendingPathComponent(name), encoding: .utf8)
            distributed = distributed
                .replacingOccurrences(of: distributedURL.path, with: localURL.path)
                .replacingOccurrences(
                    of: distributedURL.path.replacingOccurrences(of: "/", with: "\\/"),
                    with: localURL.path.replacingOccurrences(of: "/", with: "\\/")
                )
            if name == "runs.jsonl" {
                distributed = distributed.replacingOccurrences(of: ",\"workerID\":\"campaign-test-worker\"", with: "")
            }
            XCTAssertEqual(distributed, local, name)
        }
        let exportIndex = "exports/index.jsonl"
        XCTAssertEqual(
            try String(contentsOf: distributedURL.appendingPathComponent(exportIndex), encoding: .utf8).split(separator: "\n").count,
            try String(contentsOf: localURL.appendingPathComponent(exportIndex), encoding: .utf8).split(separator: "\n").count
        )
    }
}

private func unusedLocalPort() throws -> Int {
    let fd = socket(AF_INET, SOCK_STREAM, 0)
    guard fd >= 0 else {
        throw POSIXError(.EIO)
    }
    defer { close(fd) }
    var address = sockaddr_in()
    address.sin_family = sa_family_t(AF_INET)
    address.sin_addr.s_addr = inet_addr("127.0.0.1")
    address.sin_port = 0
    var length = socklen_t(MemoryLayout<sockaddr_in>.size)
    let bound = withUnsafeMutablePointer(to: &address) { pointer in
        pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { socketAddress in
            bind(fd, socketAddress, length) == 0 && getsockname(fd, socketAddress, &length) == 0
        }
    }
    guard bound else {
        throw POSIXError(.EADDRINUSE)
    }
    return Int(UInt16(bigEndian: address.sin_port))
}
