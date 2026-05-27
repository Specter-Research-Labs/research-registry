import Foundation
import XCTest
@testable import LeniaCLIKit

final class FrameExportTests: XCTestCase {
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
