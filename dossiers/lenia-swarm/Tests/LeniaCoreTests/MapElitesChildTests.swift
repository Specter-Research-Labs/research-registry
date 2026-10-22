import Foundation
import XCTest
@testable import LeniaCore

final class MapElitesChildTests: XCTestCase {
    private let first: [Float] = (0..<12).map { Float($0) * 0.37 - 1.5 }
    private let second: [Float] = (0..<12).map { 2.0 - Float($0) * 0.21 }

    func testFullRangeChildMatchesTheOriginalVariationLoop() {
        var reference = SeededRandomNumberGenerator(seed: 41)
        let expected = (0..<first.count).map { dimension in
            let isotropic = Float(0.05) * gaussianSample(rng: &reference)
            let directional = Float(0.1) * gaussianSample(rng: &reference) * (second[dimension] - first[dimension])
            return first[dimension] + isotropic + directional
        }
        var rng = SeededRandomNumberGenerator(seed: 41)
        let child = EvolutionEngine.mapElitesChild(
            first: first, second: second, sigma: 0.05, lineSigma: 0.1, mutated: 0..<first.count, rng: &rng
        )
        XCTAssertEqual(child.map(\.bitPattern), expected.map(\.bitPattern))
        XCTAssertEqual(rng.next(), reference.next())
    }

    func testZeroSigmaChildIsTheFirstParentBitwise() {
        var rng = SeededRandomNumberGenerator(seed: 7)
        let child = EvolutionEngine.mapElitesChild(
            first: first, second: second, sigma: 0, lineSigma: 0, mutated: 0..<first.count, rng: &rng
        )
        XCTAssertEqual(child.map(\.bitPattern), first.map(\.bitPattern))
    }

    func testMaskedChildKeepsUnmutatedDimensionsAndSharesDraws() {
        var fullRNG = SeededRandomNumberGenerator(seed: 99)
        let full = EvolutionEngine.mapElitesChild(
            first: first, second: second, sigma: 0.3, lineSigma: 0.2, mutated: 0..<first.count, rng: &fullRNG
        )
        var maskedRNG = SeededRandomNumberGenerator(seed: 99)
        let masked = EvolutionEngine.mapElitesChild(
            first: first, second: second, sigma: 0.3, lineSigma: 0.2, mutated: 4..<9, rng: &maskedRNG
        )
        for dimension in 0..<first.count {
            let expected = (4..<9).contains(dimension) ? full[dimension] : first[dimension]
            XCTAssertEqual(masked[dimension].bitPattern, expected.bitPattern, "dimension \(dimension)")
        }
        XCTAssertEqual(maskedRNG.next(), fullRNG.next())
    }

    func testResearchExportGenomeMatchesTheSimulatedExport() throws {
        let runtimeConfig = makeRuntimeConfigForSearchEngine(
            sx: 32,
            sy: 32,
            channels: 2,
            parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
            pUniform: nil,
            chemotaxis: nil,
            patches: [],
            aUniform: UniformRange(low: 0.0, high: 0.0)
        )
        let initPatch = InitPatchConfig(enabled: true, size: 6, center: [16, 16], valueLow: 0.0, valueHigh: 1.0)
        let esConfig = ESConfig(
            outputDir: "/tmp/map-elites-child-export-test",
            generations: 1,
            population: 2,
            sigma: 0.01,
            learningRate: 0.01,
            seed: 5,
            steps: 4,
            fitness: FitnessConfig(objective: "body_locomotion", targetStep: 4, angleThreshold: 0.0),
            fitnessShaping: "raw",
            initPatch: initPatch,
            initialInitPatchValues: nil,
            paramRanges: nil,
            obstacleField: nil
        )
        let ranges: [String: (Float, Float)] = [
            "r": (0.2, 1.0), "b": (0.001, 1.0), "w": (0.01, 0.5), "a": (0.0, 1.0),
            "m": (0.05, 0.5), "s": (0.001, 0.18), "h": (0.01, 1.0), "R": (2.0, 12.0),
        ]
        let engine = EvolutionEngine(runtimeConfig: runtimeConfig, esConfig: esConfig, ranges: ranges)
        var rng = SeededRandomNumberGenerator(seed: 3)
        let candidate = (0..<(engine.thetaParamsDim + engine.initPatchDim)).map { _ in gaussianSample(rng: &rng) }

        let genome = engine.researchExportGenome(candidate)
        let export = engine.evaluateCandidateForResearchExport(candidate)

        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        XCTAssertEqual(try encoder.encode(genome.params), try encoder.encode(export.resultData.params))
        XCTAssertEqual(try encoder.encode(genome.initConfig), try encoder.encode(export.initConfig))
    }

    func testMaterializedStatePatchRebuildsOnePatchBitwise() throws {
        try assertMaterializedStatePatchRoundTrips(patches: [PatchConfig(center: [20, 13], size: 7)], seed: 104_000_017)
    }

    func testMaterializedStatePatchRebuildsOverlappingPatchesBitwise() throws {
        try assertMaterializedStatePatchRoundTrips(
            patches: [PatchConfig(center: [16, 16], size: 8), PatchConfig(center: [21, 12], size: 5)],
            seed: 3
        )
    }

    func testMaterializationRefusesAnExistingStatePatch() {
        let statePatch = InitStatePatchConfig(center: [8, 8], width: 2, height: 2, channels: 2, values: Array(repeating: 0.5, count: 8))
        let runtimeConfig = makeRuntimeConfigForSearchEngine(
            sx: 16,
            sy: 16,
            channels: 2,
            parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
            pUniform: nil,
            chemotaxis: nil,
            patches: [],
            aUniform: UniformRange(low: 0.0, high: 0.0),
            statePatch: statePatch
        )
        XCTAssertThrowsError(try materializedInitialStatePatch(runtimeConfig: runtimeConfig, seed: 0))
    }

    private func assertMaterializedStatePatchRoundTrips(patches: [PatchConfig], seed: Int) throws {
        let parameterEmbedding = ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil)
        let seeded = makeRuntimeConfigForSearchEngine(
            sx: 40,
            sy: 32,
            channels: 2,
            parameterEmbedding: parameterEmbedding,
            pUniform: nil,
            chemotaxis: nil,
            patches: patches,
            aUniform: UniformRange(low: 0.1, high: 0.9)
        )
        let statePatch = try materializedInitialStatePatch(runtimeConfig: seeded, seed: seed)
        let explicit = makeRuntimeConfigForSearchEngine(
            sx: 40,
            sy: 32,
            channels: 2,
            parameterEmbedding: parameterEmbedding,
            pUniform: nil,
            chemotaxis: nil,
            patches: [],
            aUniform: UniformRange(low: 0.0, high: 0.0),
            statePatch: statePatch
        )
        let original = searchInitialState(runtimeConfig: seeded, seed: seed)
        XCTAssertGreaterThan(original.reduce(0, +), 0)
        XCTAssertEqual(
            searchInitialState(runtimeConfig: explicit, seed: seed).map(\.bitPattern),
            original.map(\.bitPattern)
        )
    }
}
