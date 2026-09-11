import Foundation
import XCTest
import LeniaCore
@testable import LeniaCLIKit

final class FrameExportTests: XCTestCase {
    func testReplayCapturePreservesOffCenterAdditiveState() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let source = root.appendingPathComponent(
            "Sources/LeniaStudio/Resources/Organisms/track1_orbium_unicaudatus.json"
        )
        var config = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: source)) as? [String: Any])
        config["grid"] = ["sx": 32, "sy": 32]
        var params = try XCTUnwrap(config["params"] as? [String: Any])
        params["h"] = [0.0]
        config["params"] = params
        var initial = try XCTUnwrap(config["init"] as? [String: Any])
        initial["state_patch"] = [
            "width": 1, "height": 1, "channels": 1,
            "center": [22, 16], "data": "AACAPw==", "encoding": "f32le",
        ]
        config["init"] = initial
        let runtime = try loadRuntimeConfig(from: JSONSerialization.data(withJSONObject: config))
        let search = SearchConfig(
            steps: 3, recordInterval: 1, warmupSteps: 0, occupancyThreshold: 0.05,
            massChannel: -1, scoreWeights: [:], filters: [:], complexity: nil,
            activity: nil, stability: nil
        )
        let frames = try captureReplayStateFrames(
            runtimeConfig: runtime, seed: 0, initSeedOffset: 0, searchConfig: search,
            frameBudget: 3, emptyCaptureMessage: "Expected captured frames"
        )
        XCTAssertEqual(frames.count, 3)
        let first = try XCTUnwrap(frames.first)
        let last = try XCTUnwrap(frames.last)
        XCTAssertEqual(first.values.reduce(0, +), 1, accuracy: 0.00001)
        XCTAssertEqual(last.values, first.values, "Media must not shift a static off-center specimen")
    }

    func testRobustPositiveScaleIgnoresExtremeTailSpike() {
        let values = Array(repeating: Float(0.2), count: 1_000) + [100]

        XCTAssertEqual(robustPositiveScale(values), 0.2, accuracy: 1e-6)
    }

    func testSupportMaskUsesRelativeMatterScale() {
        let frame = CapturedStateFrame(
            step: 0,
            width: 3,
            height: 1,
            channels: 2,
            values: [
                0.002, 0.001,
                0.008, 0.0,
                0.2, 0.0,
            ]
        )

        let mask = [UInt8](frame.supportMaskBytes(scale: 0.2))

        XCTAssertEqual(mask, [0, 255, 255])
    }
}
