import XCTest
@testable import LeniaCore

final class CapacityPilotTests: XCTestCase {
    func testSpatialTransformsPreserveChannelsAndInvertExactly() {
        let original = (0..<32).map(Float.init)
        var rotated = original
        for _ in 0..<4 { rotated = capacityPilotTransform(rotated, side: 4, transpose: false) }
        XCTAssertEqual(rotated, original)
        let transposed = capacityPilotTransform(original, side: 4, transpose: true)
        XCTAssertEqual(capacityPilotTransform(transposed, side: 4, transpose: true), original)
        let once = capacityPilotTransform(original, side: 4, transpose: false)
        XCTAssertEqual(once[(3 * 4) * 2], original[0])
        XCTAssertEqual(once[(3 * 4) * 2 + 1], original[1])
        for c in 0..<2 {
            XCTAssertEqual(stride(from: c, to: 32, by: 2).map { once[$0] }.sorted(),
                           stride(from: c, to: 32, by: 2).map { original[$0] }.sorted())
        }
    }
    func testBalancedWritePreservesVisibleMatterAndInventoriesAtRequestedDose() {
        let original: [Float] = (0..<128).map { Float(($0 * 17) % 29 + 1) / 29 }
        for mode in ["positive", "negative", "scrambled"] {
            let edited = capacityPilotWrite(original, width: 8, height: 8, centerX: 3.5, mode: mode, dose: 0.04)
            var delta0 = 0.0, delta1 = 0.0, l1 = 0.0
            for i in stride(from: 0, to: original.count, by: 2) {
                XCTAssertEqual(edited[i] + edited[i + 1], original[i] + original[i + 1], accuracy: 1e-6)
                XCTAssertGreaterThanOrEqual(edited[i], 0)
                XCTAssertGreaterThanOrEqual(edited[i + 1], 0)
                delta0 += Double(edited[i] - original[i])
                delta1 += Double(edited[i + 1] - original[i + 1])
                l1 += abs(Double(edited[i] - original[i])) + abs(Double(edited[i + 1] - original[i + 1]))
            }
            XCTAssertEqual(delta0, 0, accuracy: 1e-5)
            XCTAssertEqual(delta1, 0, accuracy: 1e-5)
            XCTAssertEqual(l1 / original.reduce(0.0) { $0 + Double($1) }, 0.04, accuracy: 1e-6)
        }
    }

    func testShearIsInvertibleAndPreservesEveryChannelValue() {
        let original = (0..<128).map { Float($0) / 128 }
        let edited = capacityPilotShear(original, width: 8, height: 8, centerX: 3.5, amount: 0.3)
        let reversed = capacityPilotShear(edited, width: 8, height: 8, centerX: 3.5, amount: -0.3)
        XCTAssertEqual(original, reversed)
        XCTAssertNotEqual(original, edited)
    }
}
