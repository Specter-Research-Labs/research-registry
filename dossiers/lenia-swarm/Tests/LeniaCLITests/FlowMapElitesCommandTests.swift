import Foundation
import XCTest

final class FlowMapElitesCommandTests: XCTestCase {
    private let paperConfigNames = [
        "map_elites_coherent_biomorph_2c_20k_128",
        "screen_body_locomotion_2c_128",
        "screen_coherent_strict_2c_128",
        "screen_curriculum_fish_near_coherent_2c_128_long",
        "screen_embryomaker_near_coherent_2c_128",
        "screen_fish_near_coherent_2c_128",
        "screen_fish_near_coherent_2c_128_seeded_refine",
        "screen_persistent_body_curriculum_2c_128",
    ]

    func testPaperMapElitesConfigsValidate() throws {
        let root = try makeTempDirectory(prefix: "lenia-map-elites-paper")
        defer { try? FileManager.default.removeItem(at: root) }

        for name in paperConfigNames {
            let mapConfigURL = dossierConfigsRoot()
                .appendingPathComponent("papers/flowlenia-2022/\(name).json")
            _ = try runMapElitesValidation(mapConfigURL: mapConfigURL, root: root, name: name)
        }
    }

    func testBodyLocomotionRequiresExportOverlapMinimum() throws {
        let root = try makeTempDirectory(prefix: "lenia-map-elites-overlap")
        defer { try? FileManager.default.removeItem(at: root) }

        let mapConfigURL = root.appendingPathComponent("map_elites.json")
        try FileManager.default.copyItem(
            at: dossierConfigsRoot().appendingPathComponent("papers/flowlenia-2022/screen_body_locomotion_2c_128.json"),
            to: mapConfigURL
        )
        try rewriteJSONFile(at: mapConfigURL) { config in
            XCTAssertNotNil(config.removeValue(forKey: "export_translated_shape_overlap_min"))
        }

        XCTAssertThrowsError(
            try runMapElitesValidation(mapConfigURL: mapConfigURL, root: root, name: "body")
        ) { error in
            guard case let TestCLIProcessError.failed(_, _, _, stderr) = error else {
                return XCTFail("Unexpected error: \(error)")
            }
            XCTAssertTrue(stderr.contains("requires export_translated_shape_overlap_min"), stderr)
        }
    }

    private func runMapElitesValidation(mapConfigURL: URL, root: URL, name: String) throws -> String {
        try runLeniaCLI(arguments: [
            "discover",
            "map-elites",
            "--config", dossierConfigsRoot().appendingPathComponent("base/paper_base_2c_128.json").path,
            "--map-elites", mapConfigURL.path,
            "--output", root.appendingPathComponent(name, isDirectory: true).path,
            "--validate-only",
        ])
    }
}
