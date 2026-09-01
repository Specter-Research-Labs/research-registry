import XCTest
@testable import LeniaCore

// Characterization net for the ES fitness adjusters. `fitnessValue` is a pure
// function of `esConfig.fitness` + a CandidateMeasurement, so we lock its output
// for each objective with the full penalty/reward battery configured and every
// measurement field populated. This guards the `requireMetric` dedup: any
// field/name swap across the ~70 penalty blocks changes a golden.
final class FitnessAdjusterCharacterizationTests: XCTestCase {
    private func batteryFitness(objective: String) -> FitnessConfig {
        FitnessConfig(
            objective: objective,
            targetStep: 1,
            angleThreshold: 0.01,
            minimumDisplacement: 0.02,
            gyrationPenalty: 0.011,
            componentCountPenalty: 0.012,
            componentCountTarget: 2.0,
            componentCountTargetPenalty: 0.013,
            minimumComponentCount: 1.0,
            maximumComponentCount: 6.0,
            componentCountLimitPenalty: 0.014,
            largestComponentFractionReward: 0.21,
            minimumLargestComponentFraction: 0.5,
            maximumLargestComponentFraction: 0.95,
            largestComponentFractionPenalty: 0.015,
            largestComponentFractionLimitPenalty: 0.016,
            maximumLargestComponentAnisotropy: 0.9,
            largestComponentAnisotropyPenalty: 0.017,
            componentMassEvennessReward: 0.22,
            minimumComponentMassEvenness: 0.4,
            componentMassEvennessPenalty: 0.018,
            minimumMomentMass: 0.5,
            maximumMomentMass: 5.0,
            largestComponentSolidityReward: 0.23,
            largestComponentMeanThicknessReward: 0.24,
            largestComponentFilamentarityPenalty: 0.019,
            momentDensityReward: 0.25,
            minimumMomentDensity: 0.3,
            maximumMomentDensity: 1.5,
            momentDensityPenalty: 0.026,
            momentAnisotropyPenalty: 0.027,
            maximumMomentAnisotropy: 0.8,
            momentAnisotropyLimitPenalty: 0.028,
            morphologyGuardFailureFitness: -999.0,
            internalStripePenalty: 0.029,
            orientedRidgePenalty: 0.031,
            largestComponentInternalStripePenalty: 0.032,
            largestComponentOrientedRidgePenalty: 0.033,
            templateSimilarityReward: 0.26,
            templateSequenceReward: 0.27,
            templateSequenceMassPenalty: 0.034,
            templateSequenceSupportPenalty: 0.035,
            templateSequenceChangePenalty: 0.036,
            templateSequenceDeltaReward: 0.28,
            templateSequenceSignedDeltaReward: 0.29,
            templateSequenceSteps: [0, 2],
            orientationPhaseMotionReward: 0.31,
            minimumOrientationPhaseMotion: 0.3,
            orientationPhaseMotionPenalty: 0.037,
            angularPhaseMotionReward: 0.32,
            angularPhaseMotionOrder: 2,
            minimumAngularPhaseMotion: 0.3,
            angularPhaseMotionPenalty: 0.038,
            sectorTransportReward: 0.33,
            sectorTransportBinCount: 8,
            minimumSectorTransport: 0.3,
            sectorTransportPenalty: 0.039,
            minimumTrajectoryPathLength: 5.0,
            trajectoryPathLengthPenalty: 0.041,
            trajectoryPathLengthReward: 0.34,
            minimumTrajectoryDisplacement: 4.0,
            trajectoryDisplacementPenalty: 0.042,
            trajectoryDisplacementReward: 0.35,
            minimumMovementEfficiency: 0.5,
            movementEfficiencyPenalty: 0.043,
            movementEfficiencyReward: 0.36,
            minimumCenterVelocity: 0.5,
            centerVelocityPenalty: 0.044,
            centerVelocityReward: 0.37,
            translatedShapeOverlapMin: 0.8,
            componentCountMax: 2.5,
            largestComponentFractionMin: 0.7,
            largestComponentSolidityMin: 0.7,
            largestComponentMeanThicknessMin: 2.0,
            largestComponentFilamentarityMax: 0.4,
            occupiedFractionMin: 0.4,
            occupiedFractionMax: 0.3,
            occupiedGrowthMax: 1.1,
            constraintPenalty: 0.12,
            morphologyThreshold: 0.03
        )
    }

    private func fullMeasurement() -> EvolutionEngine.CandidateMeasurement {
        EvolutionEngine.CandidateMeasurement(
            initial: .init(alive: true, x: 10, y: 12),
            mid: .init(alive: true, x: 20, y: 18),
            target: .init(alive: true, x: 30, y: 26),
            translatedShapeOverlap: 0.7,
            midOccupiedFraction: 0.3,
            targetOccupiedFraction: 0.4,
            occupiedGrowth: 1.2,
            gyration: 5.0,
            componentCount: 3.0,
            largestComponentFraction: 0.6,
            largestComponentAnisotropy: 0.5,
            componentMassEvenness: 0.55,
            momentMass: 2.0,
            largestComponentSolidity: 0.65,
            largestComponentMeanThickness: 1.5,
            largestComponentMaxThickness: 2.5,
            largestComponentFilamentarity: 0.45,
            momentDensity: 0.8,
            occupiedFraction: 0.35,
            momentAnisotropy: 0.4,
            internalStripe: 0.1,
            orientedRidge: 0.15,
            largestComponentInternalStripe: 0.12,
            largestComponentOrientedRidge: 0.18,
            templateSimilarity: 0.7,
            templateSequenceSimilarity: 0.6,
            templateSequenceMassMismatch: 0.2,
            templateSequenceSupportMismatch: 0.25,
            templateSequenceChangeMismatch: 0.3,
            templateSequenceDeltaSimilarity: 0.5,
            templateSequenceSignedDeltaSimilarity: 0.4,
            orientationPhaseMotion: 0.55,
            angularPhaseMotion: 0.5,
            sectorTransport: 0.45,
            trajectoryPathLength: 8.0,
            trajectoryDisplacement: 6.0,
            movementEfficiency: 0.75,
            centerVelocity: 1.1,
            chemotaxisScore: 0.9
        )
    }

    private func makeEngine(objective: String, fitness: FitnessConfig? = nil) -> EvolutionEngine {
        let statePatch = InitStatePatchConfig(
            center: [16, 16], width: 4, height: 4, channels: 1,
            values: [Float](repeating: 0.0, count: 4 * 4)
        )
        let runtimeConfig = makeRuntimeConfigForSearchEngine(
            sx: 32, sy: 32, channels: 1,
            parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
            pUniform: nil, chemotaxis: nil, patches: [],
            aUniform: UniformRange(low: 0.0, high: 0.0), statePatch: statePatch
        )
        let esConfig = ESConfig(
            outputDir: "/tmp/fitness-characterization",
            generations: 1, population: 2, sigma: 0.01, learningRate: 0.01,
            seed: 123, steps: 2, fitness: fitness ?? batteryFitness(objective: objective),
            fitnessShaping: "raw", initPatch: nil, initialInitPatchValues: nil,
            paramRanges: nil, obstacleField: nil
        )
        let ranges: [String: (Float, Float)] = [
            "r": (0.1, 1.0), "b": (0.0, 1.0), "w": (0.0, 1.0), "a": (0.0, 1.0),
            "m": (0.0, 1.0), "s": (0.01, 0.2), "h": (0.0, 1.0), "R": (1.0, 10.0),
        ]
        return EvolutionEngine(runtimeConfig: runtimeConfig, esConfig: esConfig, ranges: ranges)
    }

    func testFitnessAdjusterGoldens() {
        let directed = makeEngine(objective: "directed_motion").fitnessValue(from: fullMeasurement())
        let bodyLoco = makeEngine(objective: "body_locomotion").fitnessValue(from: fullMeasurement())
        let coherent = makeEngine(objective: "coherent_transport").fitnessValue(from: fullMeasurement())

        // Goldens captured from the pre-refactor implementation.
        XCTAssertEqual(directed, GOLDEN_DIRECTED, accuracy: 1e-4)
        XCTAssertEqual(bodyLoco, GOLDEN_BODY, accuracy: 1e-4)
        XCTAssertEqual(coherent, GOLDEN_COHERENT, accuracy: 1e-4)
    }

    func testCoherentTransportConstraintGuardsCaptureRequiredMeasurements() throws {
        let fitness = FitnessConfig(
            objective: "coherent_transport",
            targetStep: 2,
            angleThreshold: 0.0,
            translatedShapeOverlapMin: 0.0,
            occupiedGrowthMax: 10.0,
            constraintPenalty: 1.0,
            morphologyThreshold: 0.03
        )
        let engine = makeEngine(objective: "coherent_transport", fitness: fitness)
        let candidates = engine.sampleMAPElitesInitialCandidates(
            count: 1,
            sigma: 0.0,
            includeParent: true
        )

        let evaluations = try engine.evaluateMAPElitesCandidates(candidates, descriptorNames: [])

        XCTAssertEqual(evaluations.count, 1)
        XCTAssertTrue(evaluations[0].fitness.isFinite)
    }
}

private let GOLDEN_DIRECTED: Float = 31.602081
private let GOLDEN_BODY: Float = 4.8315244
private let GOLDEN_COHERENT: Float = 9.513022
