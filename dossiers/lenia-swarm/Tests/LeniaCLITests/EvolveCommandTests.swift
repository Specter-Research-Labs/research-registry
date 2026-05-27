import Foundation
import XCTest

final class EvolveCommandTests: XCTestCase {
    func testValidateOnlyRejectsSequenceMetricsWithoutSequenceSteps() throws {
        let tempRoot = try makeTempDirectory(prefix: "lenia-evolve-validation")
        defer { try? FileManager.default.removeItem(at: tempRoot) }

        let baseURL = tempRoot.appendingPathComponent("base.json")
        let esURL = tempRoot.appendingPathComponent("es.json")
        try copyConfigFixture(
            relativePath: "papers/flowlenia-2022/task_directed_motion_1c_10k_128.json",
            to: baseURL
        )
        try copyConfigFixture(
            relativePath: "papers/flowlenia-2022/es_directed_motion_openes.json",
            to: esURL
        ) { root in
            root["output_dir"] = tempRoot.appendingPathComponent("out", isDirectory: true).path
            root["generations"] = 1
            root["population"] = 4
            root["steps"] = 8
            var fitness = root["fitness"] as! [String: Any]
            fitness["target_step"] = 8
            fitness["center_velocity_reward"] = 1.0
            fitness.removeValue(forKey: "template_sequence_steps")
            root["fitness"] = fitness
        }

        do {
            _ = try runLeniaCLI(arguments: [
                "discover", "evolve",
                "--config", baseURL.path,
                "--es", esURL.path,
                "--backend", "mlx",
                "--validate-only",
            ])
            XCTFail("Expected validate-only to reject trajectory metrics without explicit sequence steps.")
        } catch TestCLIProcessError.failed(_, let status, _, let stderr) {
            XCTAssertNotEqual(status, SIGABRT)
            XCTAssertTrue(
                stderr.contains("at least two unique template_sequence_steps"),
                "Unexpected stderr: \(stderr)"
            )
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }
}
