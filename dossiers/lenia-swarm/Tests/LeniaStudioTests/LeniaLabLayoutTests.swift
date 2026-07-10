import XCTest
@testable import LeniaStudio

final class LeniaLabLayoutTests: XCTestCase {
    func testWorkspaceStacksBeforeSplitLayoutWouldCrowdTheCanvas() {
        XCTAssertEqual(labWorkspaceLayout(for: 800), .stacked)
        XCTAssertEqual(labWorkspaceLayout(for: 1_179), .stacked)
        XCTAssertEqual(labWorkspaceLayout(for: 1_180), .split)
        XCTAssertEqual(labWorkspaceLayout(for: 1_600), .split)
    }
}
