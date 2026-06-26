import XCTest
@testable import LeniaCLIKit

final class ReplayMaterializerTests: XCTestCase {
    func testDevelopmentTraceStrideClampsToReplayLength() {
        XCTAssertEqual(developmentTraceStride(interval: 25, steps: 3), 3)
        XCTAssertEqual(developmentTraceStride(interval: 2, steps: 5), 2)
        XCTAssertEqual(developmentTraceStride(interval: 0, steps: 5), 1)
        XCTAssertEqual(developmentTraceStride(interval: 25, steps: 0), 1)
    }
}
