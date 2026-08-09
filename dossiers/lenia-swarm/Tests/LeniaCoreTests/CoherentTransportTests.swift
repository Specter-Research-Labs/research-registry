import XCTest
@testable import LeniaCore

final class CoherentTransportTests: XCTestCase {
    func testTorusAlignmentUsesCircularMassCentersAcrossBoundary() {
        let source = massBatch(
            height: 8,
            width: 8,
            occupied: [(7, 2), (0, 2), (0, 3)]
        )
        let target = massBatch(
            height: 8,
            width: 8,
            occupied: [(0, 2), (1, 2), (1, 3)]
        )

        let result = computeCoherentTransportBatch(
            source: source,
            target: target,
            threshold: 0.5,
            useTorus: true
        )

        XCTAssertEqual(result.displacement[0], 1, accuracy: 1e-5)
        XCTAssertEqual(result.translatedShapeOverlap[0], 1, accuracy: 1e-6)
        XCTAssertEqual(result.coherentTransport[0], 1, accuracy: 1e-5)
    }

    func testWallAlignmentCountsShiftedOutSourcePixelsInUnion() {
        let source = massBatch(
            height: 6,
            width: 6,
            occupied: [(2, 3), (3, 3), (4, 3), (5, 3)]
        )
        let target = massBatch(
            height: 6,
            width: 6,
            occupied: [(0, 3), (1, 3)]
        )

        let result = computeCoherentTransportBatch(
            source: source,
            target: target,
            threshold: 0.5,
            useTorus: false
        )

        XCTAssertEqual(result.displacement[0], 3, accuracy: 1e-6)
        XCTAssertEqual(result.translatedShapeOverlap[0], 0.5, accuracy: 1e-6)
        XCTAssertEqual(result.coherentTransport[0], 1.5, accuracy: 1e-6)
    }

    private func massBatch(
        height: Int,
        width: Int,
        occupied: [(row: Int, col: Int)]
    ) -> MassBatchCPU {
        var flat = [Float](repeating: 0, count: height * width)
        for cell in occupied {
            flat[cell.row * width + cell.col] = 1
        }
        return MassBatchCPU(
            flat: flat,
            batch: 1,
            height: height,
            width: width,
            sampleSize: height * width
        )
    }
}
