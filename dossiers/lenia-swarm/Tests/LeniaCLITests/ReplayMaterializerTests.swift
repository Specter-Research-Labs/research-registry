import XCTest
@testable import LeniaCLIKit

final class ReplayMaterializerTests: XCTestCase {
    func testDevelopmentTraceStrideClampsToReplayLength() {
        XCTAssertEqual(developmentTraceStride(interval: 25, steps: 3), 3)
        XCTAssertEqual(developmentTraceStride(interval: 2, steps: 5), 2)
        XCTAssertEqual(developmentTraceStride(interval: 0, steps: 5), 1)
        XCTAssertEqual(developmentTraceStride(interval: 25, steps: 0), 1)
    }

    func testDevelopmentRawStepsParseAllOrAStepList() throws {
        XCTAssertEqual(try parseDevelopmentRawSteps("all"), .all)
        XCTAssertEqual(try parseDevelopmentRawSteps("0, 500,1000"), .steps([0, 500, 1000]))
        for text in ["", "0,", "-5", "first", "0;500"] {
            XCTAssertThrowsError(try parseDevelopmentRawSteps(text), text)
        }
    }

    func testDeclaredRawStepsMustBeSampled() throws {
        let sampled = [0, 25, 50, 75]
        XCTAssertNoThrow(try checkDevelopmentRawSteps(.steps([0, 75]), sampledSteps: sampled))
        XCTAssertNoThrow(try checkDevelopmentRawSteps(.all, sampledSteps: sampled))
        XCTAssertNoThrow(try checkDevelopmentRawSteps(nil, sampledSteps: sampled))
        XCTAssertThrowsError(try checkDevelopmentRawSteps(.steps([0, 60]), sampledSteps: sampled))
    }
}
