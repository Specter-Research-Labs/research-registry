import XCTest
@testable import LeniaCore

// Characterization tests for the shared body-locomotion scoring heuristic.
// These pin the exact formula (a Specter-internal screening heuristic, not a
// paper-defined metric) so the single shared core stays behavior-identical to
// the two former copies in Evolution and Scoring.
final class FitnessTermsTests: XCTestCase {
    func testUnitIntervalClampsAndRejectsNonFinite() {
        XCTAssertEqual(unitInterval(0.5), 0.5, accuracy: 1e-6)
        XCTAssertEqual(unitInterval(-1), 0, accuracy: 1e-6)
        XCTAssertEqual(unitInterval(2), 1, accuracy: 1e-6)
        XCTAssertEqual(unitInterval(.nan), 0, accuracy: 1e-6)
    }

    func testGrowthTermPeaksAtUnitMassAndDecaysWithLogDeviation() {
        XCTAssertEqual(bodyLocomotionGrowthTerm(1.0), 1.0, accuracy: 1e-6)
        // |log(e)| = 1 -> 1 / (1 + 2) = 1/3
        XCTAssertEqual(bodyLocomotionGrowthTerm(Float(M_E)), 1.0 / 3.0, accuracy: 1e-5)
        XCTAssertEqual(bodyLocomotionGrowthTerm(0), 0, accuracy: 1e-6)
        XCTAssertEqual(bodyLocomotionGrowthTerm(-1), 0, accuracy: 1e-6)
    }

    func testBodyLocomotionScorePerfectBodyEqualsDisplacement() {
        let score = bodyLocomotionScore(
            displacement: 2.0,
            translatedShapeOverlap: 1.0,
            occupiedGrowth: 1.0,
            largestComponentFraction: 1.0,
            largestComponentSolidity: 1.0,
            largestComponentAnisotropy: 0.0,
            largestComponentFilamentarity: 0.0
        )
        // All shaping terms saturate to 1 -> score == displacement.
        XCTAssertEqual(score, 2.0, accuracy: 1e-5)
    }

    func testBodyLocomotionScoreWorstMorphologyGolden() {
        let score = bodyLocomotionScore(
            displacement: 1.0,
            translatedShapeOverlap: 0.0,
            occupiedGrowth: 1.0,
            largestComponentFraction: 0.0,
            largestComponentSolidity: 0.0,
            largestComponentAnisotropy: 1.0,
            largestComponentFilamentarity: 1.0
        )
        // overlap 0.2; growth 1; morphology (0.25+0.35+0.35+0.35)/4 = 0.325 -> 0.2*0.325
        XCTAssertEqual(score, 0.065, accuracy: 1e-5)
    }

    func testBodyLocomotionScoreNonMoverIsZero() {
        let score = bodyLocomotionScore(
            displacement: -3.0,
            translatedShapeOverlap: 1.0,
            occupiedGrowth: 1.0,
            largestComponentFraction: 1.0,
            largestComponentSolidity: 1.0,
            largestComponentAnisotropy: 0.0,
            largestComponentFilamentarity: 0.0
        )
        XCTAssertEqual(score, 0, accuracy: 1e-6)
    }
}
