import XCTest
@testable import LeniaCore

final class MorphospaceGeometryTests: XCTestCase {
    private func translated(
        _ field: [Float],
        width: Int,
        height: Int,
        shiftX: Int,
        shiftY: Int
    ) -> [Float] {
        var result = [Float](repeating: 0, count: field.count)
        for y in 0..<height {
            for x in 0..<width {
                let targetX = ((x + shiftX) % width + width) % width
                let targetY = ((y + shiftY) % height + height) % height
                result[targetY * width + targetX] = field[y * width + x]
            }
        }
        return result
    }

    private func summary(
        _ field: [Float],
        width: Int,
        height: Int,
        useTorus: Bool
    ) -> (
        fingerprintU8: Data,
        fingerprintHash12: String,
        finalGyration: Float,
        centerX: Float,
        centerY: Float
    ) {
        let value = morphospaceFinalSampleSummary(
            materialized: MassBatchCPU(
                flat: field,
                batch: 1,
                height: height,
                width: width,
                sampleSize: width * height
            ),
            sampleIndex: 0,
            occupancyThreshold: 0.1,
            useTorus: useTorus
        )
        return (
            value.fingerprintU8,
            value.fingerprintHash12,
            value.finalGyration,
            value.centerX,
            value.centerY
        )
    }

    func testTorusFingerprintAndGyrationIgnoreBoundaryCrossingTranslation() throws {
        let width = 16
        let height = 16
        var field = [Float](repeating: 0, count: width * height)
        field[7 * width + 15] = 0.5
        field[7 * width + 0] = 1.0
        field[7 * width + 1] = 0.75
        field[8 * width + 0] = 0.25
        let shifted = translated(field, width: width, height: height, shiftX: 5, shiftY: -3)

        let original = summary(field, width: width, height: height, useTorus: true)
        let moved = summary(shifted, width: width, height: height, useTorus: true)

        XCTAssertEqual(original.fingerprintU8, moved.fingerprintU8)
        XCTAssertEqual(original.fingerprintHash12, moved.fingerprintHash12)
        XCTAssertEqual(original.finalGyration, moved.finalGyration, accuracy: 1e-5)
    }

    func testCircularCenterKeepsSeamBodyCompact() {
        let width = 16
        let height = 8
        var field = [Float](repeating: 0, count: width * height)
        field[3 * width + 15] = 1
        field[3 * width + 0] = 2
        field[3 * width + 1] = 1

        let torus = summary(field, width: width, height: height, useTorus: true)
        let wall = summary(field, width: width, height: height, useTorus: false)

        XCTAssertTrue(torus.centerX < 2 || torus.centerX > 14)
        XCTAssertLessThan(torus.finalGyration, 2)
        XCTAssertGreaterThan(wall.finalGyration, 20)
    }

    func testPeakScaledFingerprintKeepsDiffuseFieldsVisible() {
        let width = 32
        let height = 32
        let field = [Float](repeating: 0.01, count: width * height)

        let value = summary(field, width: width, height: height, useTorus: true)

        XCTAssertEqual(value.fingerprintU8.count, width * height)
        XCTAssertEqual(value.fingerprintU8.min(), 255)
        XCTAssertEqual(value.fingerprintU8.max(), 255)
    }

    func testDevelopmentTraceCarriesV2FingerprintPolicyAndCircularCenter() {
        let width = 16
        let height = 8
        var field = [Float](repeating: 0, count: width * height)
        field[3 * width + 15] = 1
        field[3 * width + 0] = 2
        field[3 * width + 1] = 1

        let sample = morphospaceDevelopmentSample(
            step: 10,
            channels: 1,
            width: width,
            height: height,
            values: field,
            massChannel: 0,
            occupancyThreshold: 0.1,
            useTorus: true,
            borderMode: "torus",
            fieldResolution: 16
        )

        XCTAssertEqual(sample.terminal.version, 2)
        XCTAssertEqual(
            sample.terminal.normalizationPolicy,
            "border_aware_com_center_peak_q32_u8_v2"
        )
        XCTAssertTrue(sample.centerX < 2 || sample.centerX > 14)
        XCTAssertEqual(sample.fieldResolution, 16)
        XCTAssertNotNil(sample.fieldF16Base64)
    }
}
