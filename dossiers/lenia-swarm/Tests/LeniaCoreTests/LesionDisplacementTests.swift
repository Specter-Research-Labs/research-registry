import MLX
import XCTest
@testable import LeniaCore

final class LesionDisplacementTests: XCTestCase {
    private let lesion = FlowMAPElitesLesionConfig(step: 40, size: 4, window: 40)

    private func makeEngine() -> EvolutionEngine {
        let statePatch = InitStatePatchConfig(
            center: [16, 16], width: 6, height: 6, channels: 1,
            values: (0..<36).map { 0.4 + 0.5 * Float(($0 * 7) % 11) / 10 }
        )
        let runtimeConfig = makeRuntimeConfigForSearchEngine(
            sx: 32, sy: 32, channels: 1,
            parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
            pUniform: nil, chemotaxis: nil, patches: [],
            aUniform: UniformRange(low: 0.0, high: 0.0), statePatch: statePatch
        )
        let esConfig = ESConfig(
            outputDir: "/tmp/lesion-displacement",
            generations: 1, population: 4, sigma: 0.3, learningRate: 0.0,
            seed: 7, steps: 4,
            fitness: FitnessConfig(objective: "directed_motion", targetStep: 4, angleThreshold: 0.0),
            fitnessShaping: "raw", initPatch: nil, initialInitPatchValues: nil,
            paramRanges: nil, obstacleField: nil
        )
        let ranges: [String: (Float, Float)] = [
            "r": (0.1, 1.0), "b": (0.0, 1.0), "w": (0.0, 1.0), "a": (0.0, 1.0),
            "m": (0.0, 1.0), "s": (0.01, 0.2), "h": (0.0, 1.0), "R": (1.0, 10.0),
        ]
        return EvolutionEngine(runtimeConfig: runtimeConfig, esConfig: esConfig, ranges: ranges)
    }

    func testTorusMassCentreFollowsABodyAcrossTheSeam() {
        var values = [Float](repeating: 0, count: 2 * 16 * 16)
        for x in [15, 0, 1] {
            values[(0 * 16 + x) * 16 + 4] = 1
        }
        values[(1 * 16 + 8) * 16 + 8] = 1
        let centres = EvolutionEngine.torusMassCentres(MLXArray(values).reshaped([2, 16, 16]))
        XCTAssertEqual(min(centres[0]!.x, 16 - centres[0]!.x), 0, accuracy: 1e-9)
        XCTAssertEqual(centres[0]!.y, 4, accuracy: 1e-9)
        XCTAssertEqual(centres[1]!.x, 8, accuracy: 1e-9)
        XCTAssertNil(EvolutionEngine.torusMassCentres(MLXArray.zeros([1, 16, 16]))[0])
    }

    func testLesionDisplacementIsDeterministicAndIndependentOfTheBatch() throws {
        let engine = makeEngine()
        let candidates = engine.sampleMAPElitesInitialCandidates(count: 4, sigma: 0.3, includeParent: true)
        let first = try engine.evaluateMAPElitesCandidates(
            candidates, descriptorNames: ["lesion_displacement"], lesion: lesion
        ).map { $0.descriptors["lesion_displacement"]! }
        let again = try engine.evaluateMAPElitesCandidates(
            candidates, descriptorNames: ["lesion_displacement"], lesion: lesion
        ).map { $0.descriptors["lesion_displacement"]! }
        let alone = try engine.evaluateMAPElitesCandidates(
            [candidates[2]], descriptorNames: ["lesion_displacement"], lesion: lesion
        ).map { $0.descriptors["lesion_displacement"]! }
        XCTAssertEqual(first, again)
        XCTAssertEqual(alone, [first[2]])
        XCTAssertTrue(first.allSatisfy { $0.isFinite && $0 >= 0 })
        XCTAssertGreaterThan(Set(first).count, 1)
    }

    func testLesionConfigAndDescriptorMustComeTogether() {
        let engine = makeEngine()
        let candidates = engine.sampleMAPElitesInitialCandidates(count: 2, sigma: 0.3, includeParent: true)
        XCTAssertThrowsError(try engine.evaluateMAPElitesCandidates(
            candidates, descriptorNames: ["lesion_displacement"], lesion: nil
        ))
        XCTAssertThrowsError(try engine.evaluateMAPElitesCandidates(
            candidates, descriptorNames: ["fitness"], lesion: lesion
        ))
    }

    func testLesionLargerThanTheGridIsRefused() {
        let engine = makeEngine()
        let candidates = engine.sampleMAPElitesInitialCandidates(count: 2, sigma: 0.3, includeParent: true)
        XCTAssertThrowsError(try engine.evaluateMAPElitesCandidates(
            candidates,
            descriptorNames: ["lesion_displacement"],
            lesion: FlowMAPElitesLesionConfig(step: 4, size: 32, window: 4)
        ))
    }
}
