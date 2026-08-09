import XCTest
@testable import LeniaCore

final class SpecimenCaptureTests: XCTestCase {
    func testCaptureSelectsOnlyConnectedComponentNearCursor() throws {
        var mass = [Float](repeating: 0, count: 8 * 8)
        mass[index(1, 1)] = 0.8
        mass[index(1, 2)] = 0.7
        mass[index(2, 1)] = 0.6
        mass[index(6, 6)] = 1
        let captured = try captureSpecimenComponent(
            from: snapshot(mass: mass),
            near: SIMD2<Int>(1, 1),
            padding: 0,
            wraps: false
        )

        XCTAssertEqual(captured.width, 2)
        XCTAssertEqual(captured.height, 2)
        XCTAssertEqual(captured.mass.reduce(0, +), 2.1, accuracy: 1e-6)
        XCTAssertEqual(captured.previewStamp.mass.max(), 0.8)
    }

    func testCaptureJoinsComponentAcrossTorusBoundary() throws {
        var mass = [Float](repeating: 0, count: 8 * 8)
        mass[index(0, 3)] = 0.9
        mass[index(7, 3)] = 0.8
        let captured = try captureSpecimenComponent(
            from: snapshot(mass: mass),
            near: SIMD2<Int>(0, 3),
            padding: 0,
            wraps: true
        )

        XCTAssertEqual(captured.width, 2)
        XCTAssertEqual(captured.height, 1)
        XCTAssertEqual(captured.mass.reduce(0, +), 1.7, accuracy: 1e-6)
    }

    func testCaptureFingerprintIsTranslationInvariant() throws {
        var first = [Float](repeating: 0, count: 8 * 8)
        first[index(1, 1)] = 0.7
        first[index(1, 2)] = 0.5
        var second = [Float](repeating: 0, count: 8 * 8)
        second[index(4, 5)] = 0.7
        second[index(4, 6)] = 0.5

        let a = try captureSpecimenComponent(
            from: snapshot(mass: first),
            near: SIMD2<Int>(1, 1),
            padding: 1
        )
        let b = try captureSpecimenComponent(
            from: snapshot(mass: second),
            near: SIMD2<Int>(4, 5),
            padding: 1
        )
        XCTAssertEqual(a.fingerprint, b.fingerprint)
    }

    func testCapturePreservesParameterContextAcrossPadding() throws {
        var mass = [Float](repeating: 0, count: 8 * 8)
        mass[index(3, 3)] = 1
        let params = (0..<(8 * 8)).map(Float.init)
        let captured = try captureSpecimenComponent(
            from: snapshot(mass: mass, params: params),
            near: SIMD2<Int>(3, 3),
            padding: 1,
            wraps: false
        )

        XCTAssertEqual(captured.width, 3)
        XCTAssertEqual(captured.height, 3)
        XCTAssertEqual(captured.params, [18, 19, 20, 26, 27, 28, 34, 35, 36])
    }

    private func snapshot(mass: [Float], params: [Float]? = nil) -> FlowSandboxStateSnapshot {
        FlowSandboxStateSnapshot(
            step: 42,
            width: 8,
            height: 8,
            channels: 1,
            parameterCount: 1,
            mass: mass,
            params: params ?? mass.map { $0 > 0 ? 0.5 : 0 },
            food: Array(repeating: 0, count: 64),
            walls: Array(repeating: 1, count: 64)
        )
    }

    private func index(_ x: Int, _ y: Int) -> Int {
        x * 8 + y
    }
}
