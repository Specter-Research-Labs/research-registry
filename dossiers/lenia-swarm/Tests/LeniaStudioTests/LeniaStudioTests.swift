import XCTest
import Metal
import LeniaVisuals
@testable import LeniaStudio

final class LeniaStudioTests: XCTestCase {
    func testPreferredStudioSurfaceFollowsProductRouting() {
        XCTAssertEqual(
            preferredStudioSurface(currentSelection: .lab, connectionState: .connected(role: .host)),
            .cluster
        )
        XCTAssertEqual(
            preferredStudioSurface(currentSelection: .lab, connectionState: .connected(role: .worker)),
            .cluster
        )
        XCTAssertEqual(
            preferredStudioSurface(currentSelection: .lab, connectionState: .connecting),
            .cluster
        )
        XCTAssertEqual(
            preferredStudioSurface(currentSelection: .cluster, connectionState: .error("boom")),
            .cluster
        )
        XCTAssertEqual(
            preferredStudioSurface(currentSelection: .lab, connectionState: .connected(role: .compendium)),
            .compendium
        )
        XCTAssertEqual(
            preferredStudioSurface(currentSelection: .compendium, connectionState: .disconnected),
            .compendium
        )
    }

    func testLeniaLabStageTransformMapsPointsUnderZoomAndOffset() {
        let transform = LeniaLabStageTransform(
            zoom: 1.5,
            offset: CGSize(width: 30, height: -20)
        )
        let viewSize = CGSize(width: 900, height: 700)
        let rect = transform.imageRect(
            viewSize: viewSize,
            gridSize: CGSize(width: 256, height: 256)
        )

        XCTAssertEqual(
            transform.gridPoint(
                for: CGPoint(x: rect.midX, y: rect.midY),
                viewSize: viewSize,
                gridSize: 256
            ),
            SIMD2<Int>(128, 128)
        )
        XCTAssertEqual(
            transform.gridPoint(
                for: CGPoint(x: rect.minX + 1, y: rect.minY + 1),
                viewSize: viewSize,
                gridSize: 256
            ),
            SIMD2<Int>(0, 0)
        )
        XCTAssertNil(
            transform.gridPoint(
                for: CGPoint(x: rect.maxX + 5, y: rect.maxY + 5),
                viewSize: viewSize,
                gridSize: 256
            )
        )
    }

    func testLeniaLabStageTransformZoomKeepsAnchorStable() {
        let transform = LeniaLabStageTransform()
        let viewSize = CGSize(width: 800, height: 600)
        let anchor = CGPoint(x: 400, y: 300)

        let zoomed = transform.zoomed(
            to: 2.0,
            around: anchor,
            viewSize: viewSize,
            gridSize: 256
        )

        XCTAssertEqual(
            transform.gridPoint(for: anchor, viewSize: viewSize, gridSize: 256),
            zoomed.gridPoint(for: anchor, viewSize: viewSize, gridSize: 256)
        )
        XCTAssertEqual(zoomed.zoom, 2.0, accuracy: 1e-6)
    }

    func testLeniaMetalFieldRendererProducesOffscreenImage() {
        guard let device = MTLCreateSystemDefaultDevice() else {
            XCTFail("Metal device unavailable")
            return
        }

        let renderer = LeniaMetalFieldRenderer(device: device)
        let bytes = Data((0..<64).map { UInt8(($0 * 4) % 255) })
        let frame = LeniaFieldFrame(
            step: 0,
            width: 8,
            height: 8,
            bytes: bytes
        )

        let image = renderer.renderImage(
            frame: frame,
            renderMode: .smoothMagma,
            outputSize: CGSize(width: 64, height: 64)
        )

        XCTAssertEqual(image?.width, 64)
        XCTAssertEqual(image?.height, 64)
    }

    func testTTFrameSequenceLoadsRawFrames() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("tt-frame-sequence-\(UUID().uuidString)")
        let frames = root.appendingPathComponent("frames")
        try FileManager.default.createDirectory(at: frames, withIntermediateDirectories: true)
        try Data([0, 64, 128, 255]).write(to: frames.appendingPathComponent("frame_000000.r8"))

        let manifest = """
        {
          "manifest_version": 1,
          "kind": "lenia_tt_frame_sequence",
          "backend": "tt",
          "config_path": "configs/base/paper_base_2c_128.json",
          "steps": 4,
          "frame_every": 2,
          "width": 2,
          "height": 2,
          "channels": 2,
          "projection": "matter",
          "batch_index": 0,
          "dtype": "uint8",
          "storage": "raw_r8",
          "final_mass_path": "mass_final.npy",
          "metadata": {
            "dt": 0.1,
            "dd": 5,
            "sigma": 0.65,
            "n": 2,
            "theta_a": 1.0,
            "border": "torus",
            "kernel_profile": "gaussian",
            "kernel_count": 3,
            "radius": 12.0
          },
          "frames": [
            {"step": 0, "path": "frames/frame_000000.r8"}
          ]
        }
        """
        let manifestURL = root.appendingPathComponent("manifest.json")
        try manifest.write(to: manifestURL, atomically: true, encoding: .utf8)
        defer { try? FileManager.default.removeItem(at: root) }

        let sequence = try TTFrameSequence.load(manifestURL: manifestURL)
        let frame = try sequence.frame(at: 0)

        XCTAssertEqual(sequence.frameCount, 1)
        XCTAssertEqual(frame.step, 0)
        XCTAssertEqual(frame.width, 2)
        XCTAssertEqual(frame.height, 2)
        XCTAssertEqual(frame.bytes, Data([0, 64, 128, 255]))
    }

    func testTTFrameSequenceRejectsWrongSizedFrameAtLoad() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("tt-frame-sequence-bad-\(UUID().uuidString)")
        let frames = root.appendingPathComponent("frames")
        try FileManager.default.createDirectory(at: frames, withIntermediateDirectories: true)
        try Data([0, 64, 128]).write(to: frames.appendingPathComponent("frame_000000.r8"))

        let manifest = """
        {
          "manifest_version": 1,
          "kind": "lenia_tt_frame_sequence",
          "backend": "tt",
          "config_path": "configs/base/paper_base_2c_128.json",
          "steps": 4,
          "frame_every": 2,
          "width": 2,
          "height": 2,
          "channels": 2,
          "projection": "matter",
          "batch_index": 0,
          "dtype": "uint8",
          "storage": "raw_r8",
          "final_mass_path": "mass_final.npy",
          "frames": [
            {"step": 0, "path": "frames/frame_000000.r8"}
          ]
        }
        """
        let manifestURL = root.appendingPathComponent("manifest.json")
        try manifest.write(to: manifestURL, atomically: true, encoding: .utf8)
        defer { try? FileManager.default.removeItem(at: root) }

        XCTAssertThrowsError(try TTFrameSequence.load(manifestURL: manifestURL)) { error in
            guard case TTFrameSequenceError.invalidFrameSize = error else {
                return XCTFail("Expected invalidFrameSize, got \(error)")
            }
        }
    }
}
