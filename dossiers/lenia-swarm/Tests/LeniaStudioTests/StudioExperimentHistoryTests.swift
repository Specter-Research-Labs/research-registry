import XCTest
import LeniaCore
@testable import LeniaStudio

@MainActor
final class StudioExperimentHistoryTests: XCTestCase {
    func testUndoRedoAndBranchUseExactCheckpoints() {
        let history = StudioExperimentHistory(maximumBytes: 1_024 * 1_024)
        history.reset(initial: snapshot(step: 0, value: 0), label: "Initial")
        history.checkpoint(snapshot(step: 10, value: 0.1), label: "Ten")
        history.checkpoint(snapshot(step: 20, value: 0.2), label: "Twenty")

        XCTAssertEqual(history.undo()?.step, 10)
        XCTAssertEqual(history.redo()?.step, 20)
        XCTAssertEqual(history.undo()?.step, 10)

        history.checkpoint(snapshot(step: 15, value: 0.15), label: "Branch")
        XCTAssertEqual(history.checkpoints.map(\.snapshot.step), [0, 10, 15])
        XCTAssertFalse(history.canRedo)
        XCTAssertTrue(history.actions.contains(where: { $0.kind == .branch }))
    }

    func testHistoryPrunesOldCheckpointsToMemoryBudget() {
        let bytesPerSnapshot = 4 * 4 * MemoryLayout<Float>.stride * 4
        let history = StudioExperimentHistory(maximumBytes: bytesPerSnapshot * 2)
        history.reset(initial: snapshot(step: 0, value: 0))
        history.checkpoint(snapshot(step: 1, value: 1), label: "One")
        history.checkpoint(snapshot(step: 2, value: 2), label: "Two")

        XCTAssertEqual(history.checkpoints.map(\.snapshot.step), [1, 2])
        XCTAssertLessThanOrEqual(history.retainedBytes, history.maximumBytes)
    }

    func testBundleWritesVersionedStateAndReviewMedia() throws {
        let history = StudioExperimentHistory(maximumBytes: 1_024 * 1_024)
        history.reset(initial: snapshot(step: 0, value: 0.1))
        history.checkpoint(snapshot(step: 10, value: 0.8), label: "Ten")
        let destination = FileManager.default.temporaryDirectory
            .appendingPathComponent("\(UUID().uuidString).leniaexperiment", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: destination) }

        try StudioExperimentBundleWriter.write(
            title: "Bundle test",
            sourceName: "Fixture",
            contract: worldContract(),
            history: history,
            to: destination
        )

        let manifestData = try Data(contentsOf: destination.appendingPathComponent("manifest.json"))
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let manifest = try decoder.decode(StudioExperimentManifest.self, from: manifestData)
        XCTAssertEqual(manifest.schemaVersion, 2)
        XCTAssertEqual(manifest.checkpoints.count, 2)
        XCTAssertEqual(manifest.previewFile, "preview.png")
        XCTAssertEqual(manifest.timelineFile, "timeline.gif")
        XCTAssertGreaterThan(try fileSize(destination.appendingPathComponent("preview.png")), 0)
        XCTAssertGreaterThan(try fileSize(destination.appendingPathComponent("timeline.gif")), 0)
        for checkpoint in manifest.checkpoints {
            XCTAssertTrue(FileManager.default.fileExists(
                atPath: destination.appendingPathComponent(checkpoint.file).path
            ))
        }
    }

    private func snapshot(step: Int, value: Float) -> FlowSandboxStateSnapshot {
        FlowSandboxStateSnapshot(
            step: step,
            width: 4,
            height: 4,
            channels: 1,
            parameterCount: 1,
            mass: Array(repeating: value, count: 16),
            params: Array(repeating: value, count: 16),
            food: Array(repeating: value, count: 16),
            walls: Array(repeating: 1, count: 16)
        )
    }

    private func worldContract() -> FlowSandboxWorldContract {
        FlowSandboxWorldContract(
            backend: .mlx,
            gridSize: 4,
            channels: 1,
            parameterFieldMode: .kernelGain,
            parameterFieldCount: 1,
            kernelCount: 1,
            dt: 0.2,
            dd: 5,
            sigma: 0.65,
            n: 2,
            thetaA: 2,
            border: "torus",
            kernelProfile: "test",
            seed: 1,
            radius: 13,
            executionSummary: "test",
            fieldSummary: "test",
            featureSummary: "test",
            connectivitySummary: "c0 -> c0",
            kernels: [
                FlowSandboxKernelContract(
                    id: 0,
                    radius: 0.5,
                    center: 0.15,
                    sigma: 0.017,
                    gain: 0.1,
                    beta: [1, 0, 0],
                    weights: [0.2, 0.2, 0.2],
                    anchors: [0.5, 0.5, 0.5]
                )
            ]
        )
    }

    private func fileSize(_ url: URL) throws -> Int64 {
        let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
        return (attributes[.size] as? NSNumber)?.int64Value ?? 0
    }
}
