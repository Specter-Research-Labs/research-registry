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
            "center": [22, 16], "data": "eNpjYGiwBwABQwDA", "encoding": FieldCodec.encoding,
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

    func testSpecimenMediaKeepsOnlyTheVideoUnlessFramesAreRequested() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("specimen-media-\(UUID().uuidString)", isDirectory: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: root) }
        let directory = root.appendingPathComponent("specimen", isDirectory: true)
        let renderer = try GrayscaleColorRenderer(renderMode: .body)
        let render: (Int) throws -> SpecimenFrame = { index in
            var truth = Data(repeating: 0, count: 32 * 32)
            for cell in (10 * 32 + index)..<(10 * 32 + index + 8) {
                truth[cell] = 200
            }
            return SpecimenFrame(
                step: index * 5,
                truth: truth,
                truthWidth: 32,
                truthHeight: 32,
                color: try renderer.render(width: 32, height: 32, grayscale: truth)
            )
        }

        let exported = try writeSpecimenMedia(
            directory: directory,
            videoName: "clip.mp4",
            frameCount: 5,
            output: MediaOutputOptions(fps: 6, ffmpeg: "ffmpeg", exportFrames: true),
            frame: render
        )
        let colorFramesURL = try XCTUnwrap(exported.colorFramesURL)
        let framesURL = try XCTUnwrap(exported.framesURL)
        XCTAssertEqual(
            try FileManager.default.contentsOfDirectory(atPath: framesURL.path).sorted(),
            (0..<5).map { String(format: "frame_%06d.png", $0 * 5) }
        )
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: colorFramesURL.path).count, 5)
        XCTAssertEqual(exported.contactRow.color.count, 3)
        XCTAssertEqual(exported.contactRow.truth.map(\.width), [32, 32, 32])

        let streamed = try writeSpecimenMedia(
            directory: directory,
            videoName: "clip.mp4",
            frameCount: 5,
            output: MediaOutputOptions(fps: 6, ffmpeg: "ffmpeg", exportFrames: false),
            frame: render
        )
        XCTAssertNil(streamed.framesURL)
        XCTAssertNil(streamed.colorFramesURL)
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: directory.path), ["clip.mp4"])
    }
}
