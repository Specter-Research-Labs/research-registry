import Foundation
import XCTest

final class LocalCommandTests: XCTestCase {
    func testAutoBackendValidationUsesSearchOverrides() throws {
        let root = try makeTempDirectory(prefix: "lenia-local-backend")
        defer { try? FileManager.default.removeItem(at: root) }

        let searchURL = root.appendingPathComponent("search.json")
        try writeJSON(
            [
                "count": 1,
                "seed_start": 0,
                "seed_stride": 1,
                "init_seed_offset": 0,
                "steps": 2,
                "record_interval": 1,
                "warmup_steps": 0,
                "occupancy_threshold": 0.05,
                "mass_channel": -1,
                "score_weights": [:] as [String: Double],
                "filters": [:] as [String: Double],
                "overrides": [
                    "parameter_embedding.mix": "softmax",
                ],
                "top_k": 1,
                "batch_size": 1,
                "seeds_per_job": 1,
            ],
            to: searchURL
        )

        do {
            _ = try runLeniaCLI(arguments: [
                "discover", "local",
                "--config", dossierConfigsRoot().appendingPathComponent("base/paper_base_pe_1c_128.json").path,
                "--search", searchURL.path,
                "--output", root.appendingPathComponent("out", isDirectory: true).path,
                "--validate-only",
            ])
            XCTFail("Expected auto backend validation to reject the effective overridden config.")
        } catch TestCLIProcessError.failed(_, let status, _, let stderr) {
            XCTAssertNotEqual(status, SIGABRT)
            XCTAssertTrue(
                stderr.contains("Auto backend requires a Metal-compatible search config"),
                "Unexpected stderr: \(stderr)"
            )
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }
}
