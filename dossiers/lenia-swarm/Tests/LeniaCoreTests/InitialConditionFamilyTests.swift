import Foundation
import XCTest
@testable import LeniaCore

/// `lenia-swarm-analysis compact` writes `initialConditionFamily` into manifests it builds; the
/// shared fixture pins its Python port to this implementation.
final class InitialConditionFamilyTests: XCTestCase {
    private struct Fixture: Decodable {
        struct Case: Decodable {
            let initialCondition: InitConfig
            let family: String
        }
        let cases: [Case]
    }

    func testFixtureMatchesPythonPort() throws {
        let url = try XCTUnwrap(Bundle.module.url(forResource: "initial-condition-family", withExtension: "json"))
        let fixture = try JSONDecoder().decode(Fixture.self, from: Data(contentsOf: url))
        XCTAssertEqual(fixture.cases.count, 3)
        for testCase in fixture.cases {
            XCTAssertEqual(morphospaceInitialConditionFamily(testCase.initialCondition), testCase.family)
        }
    }
}
