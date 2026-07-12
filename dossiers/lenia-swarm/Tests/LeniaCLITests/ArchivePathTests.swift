import Foundation
import XCTest
import LeniaArchive

final class ArchivePathTests: XCTestCase {
    func testResolveRunArtifactPathCoversCanonicalPathForms() {
        XCTAssertEqual(
            resolveRunArtifactPath(outputRoot: "/tmp/runs", runDir: "run-1", path: "frames/final.r8"),
            "/tmp/runs/run-1/frames/final.r8"
        )
        XCTAssertEqual(
            resolveRunArtifactPath(outputRoot: nil, runDir: "/tmp/run-2", path: "summary.json"),
            "/tmp/run-2/summary.json"
        )
        XCTAssertEqual(
            resolveRunArtifactPath(outputRoot: nil, runDir: nil, path: "/tmp/direct.json"),
            "/tmp/direct.json"
        )
        XCTAssertEqual(
            resolveRunArtifactPath(outputRoot: nil, runDir: nil, path: "~/direct.json"),
            URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent("direct.json").path
        )
        XCTAssertNil(
            resolveRunArtifactPath(outputRoot: nil, runDir: "relative-run", path: "summary.json")
        )
    }
}
