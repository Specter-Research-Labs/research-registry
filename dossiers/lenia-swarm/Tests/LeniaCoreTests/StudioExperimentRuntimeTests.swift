import XCTest
@testable import LeniaCore

final class StudioExperimentRuntimeTests: XCTestCase {
    override func setUpWithError() throws {
        try LeniaMetalLibrarySupport.ensureAvailable()
    }

    func testSandboxCheckpointRestoresEveryEditableField() async throws {
        let runtime = FlowSandboxRuntime(
            params: experimentParams(),
            gridPreset: .compact128,
            initialStamp: experimentStamp(),
            backend: .metalFull
        )
        await runtime.step()
        await runtime.applyStroke(
            SandboxStroke(
                tool: .food,
                points: [SIMD2<Int>(12, 12)],
                radius: 2,
                strength: 0.6
            )
        )
        await runtime.applyStroke(
            SandboxStroke(
                tool: .wall,
                points: [SIMD2<Int>(18, 18)],
                radius: 1,
                strength: 1
            )
        )
        let checkpoint = await runtime.materializeStateSnapshot()

        await runtime.step()
        await runtime.applyStroke(
            SandboxStroke(
                tool: .erase,
                points: [SIMD2<Int>(18, 18)],
                radius: 3,
                strength: 1
            )
        )
        try await runtime.restoreStateSnapshot(checkpoint)

        let restored = await runtime.materializeStateSnapshot()
        XCTAssertEqual(restored.step, checkpoint.step)
        XCTAssertEqual(restored.channels, checkpoint.channels)
        XCTAssertEqual(restored.parameterCount, checkpoint.parameterCount)
        XCTAssertEqual(restored.mass, checkpoint.mass)
        XCTAssertEqual(restored.params, checkpoint.params)
        XCTAssertEqual(restored.food, checkpoint.food)
        XCTAssertEqual(restored.walls, checkpoint.walls)
    }

    func testSandboxCheckpointRejectsMismatchedDimensions() async {
        let runtime = FlowSandboxRuntime(
            params: experimentParams(),
            gridPreset: .compact128,
            backend: .metalFull
        )
        let invalid = FlowSandboxStateSnapshot(
            step: 0,
            width: 64,
            height: 64,
            channels: 1,
            parameterCount: 1,
            mass: Array(repeating: 0, count: 64 * 64),
            params: Array(repeating: 0, count: 64 * 64),
            food: Array(repeating: 0, count: 64 * 64),
            walls: Array(repeating: 1, count: 64 * 64)
        )

        do {
            try await runtime.restoreStateSnapshot(invalid)
            XCTFail("Expected mismatched checkpoint dimensions to fail")
        } catch let error as FlowSandboxStateRestoreError {
            guard case .invalidDimensions = error else {
                return XCTFail("Unexpected restore error: \(error)")
            }
        } catch {
            XCTFail("Unexpected restore error: \(error)")
        }
    }

}

private func experimentParams() -> ResolvedParams {
    ResolvedParams(
        r: [0.5],
        b: [[1, 0, 0]],
        w: [[0.2, 0.2, 0.2]],
        a: [[0.5, 0.5, 0.5]],
        m: [0.15],
        s: [0.05],
        h: [0.5],
        R: 6,
        seed: 7
    )
}

private func experimentStamp() -> CreatureStamp {
    CreatureStamp(
        name: "Checkpoint",
        width: 3,
        height: 3,
        mass: [
            0, 0.2, 0,
            0.3, 0.9, 0.3,
            0, 0.2, 0,
        ],
        params: Array(repeating: 0.5, count: 9),
        parameterCount: 1
    )
}
