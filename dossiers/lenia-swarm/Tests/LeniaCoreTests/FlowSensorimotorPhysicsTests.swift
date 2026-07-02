import Foundation
import XCTest
@testable import LeniaCore
import MLX
import MLXFFT

// Locks the three properties the Flow-Lenia sensorimotor inner loop depends on:
// reintegration conserves the body mass (so viability must be dispersal-based,
// not mass-decay-based), the rollout is GPU-differentiable through the rule
// parameters, and a negative wall potential steers mass away from it.
private final class FlowSensorimotorPhysicsMarker {}

final class FlowSensorimotorPhysicsTests: XCTestCase {
    override func setUp() {
        super.setUp()
        do {
            try LeniaMetalLibrarySupport.ensureAvailable(
                executableURL: Bundle(for: FlowSensorimotorPhysicsMarker.self).executableURL
            )
        } catch {
            XCTFail("Failed to prepare MLX metallib: \(error)")
        }
    }

    private let sx = 64
    private let sy = 64
    private let nbK = 3

    private func config() -> FlowSensorimotorStepConfig {
        FlowSensorimotorStepConfig(
            sx: sx, sy: sy, nbK: nbK, channels: 1, learnableChannels: 1,
            dd: 3, sigma: 0.65, dt: 0.1, n: 2, thetaA: 1.0, R: 13.0,
            kernelProfile: "flowlenia_2022_colab",
            gradientBoundary: "zero_pad", alphaMode: "mass", flowClip: "none",
            growthProfile: "gaussian", useTorus: false
        )
    }

    private func ruleParams() -> (a: MLXArray, w: MLXArray, b: MLXArray, r: MLXArray, m: MLXArray, s: MLXArray, h: MLXArray) {
        let a = MLXArray([Float](repeating: 0.5, count: nbK)).reshaped([nbK, 1])
        let w = MLXArray([Float](repeating: 0.15, count: nbK)).reshaped([nbK, 1])
        let b = MLXArray([Float](repeating: 0.6, count: nbK)).reshaped([nbK, 1])
        let r = MLXArray([Float](repeating: 0.7, count: nbK))
        let m = MLXArray([Float](repeating: 0.15, count: nbK))
        let s = MLXArray([Float](repeating: 0.015, count: nbK))
        let h = MLXArray([Float](repeating: 0.3, count: nbK))
        return (a, w, b, r, m, s, h)
    }

    private func centeredBlob() -> MLXArray {
        var values = [Float](repeating: 0.0, count: sx * sy)
        let half = 4
        for row in (sx / 2 - half)..<(sx / 2 + half) {
            for col in (sy / 2 - half)..<(sy / 2 + half) {
                values[row * sy + col] = 0.5
            }
        }
        return MLXArray(values).reshaped([1, sx, sy, 1])
    }

    private func channelMaps() -> (c0Idxs: MLXArray, c1Mask: MLXArray) {
        let c0Idxs = MLXArray((0..<nbK).map { _ in Int32(0) })
        let c1Mask = MLXArray([Float](repeating: 1.0, count: nbK)).reshaped([1, nbK])
        return (c0Idxs, c1Mask)
    }

    func testReintegrationConservesMass() {
        let cfg = config()
        let p = ruleParams()
        let maps = channelMaps()
        let initial = centeredBlob()
        let pos = flowSensorimotorPosGrid(sx: sx, sy: sy)

        let initialMass = flowSensorimotorMass(initial, config: cfg).item(Float.self)
        let final = flowSensorimotorRollout(
            initial: initial, a: p.a, w: p.w, b: p.b, r: p.r, m: p.m, s: p.s, h: p.h,
            c0Idxs: maps.c0Idxs, c1Mask: maps.c1Mask, posGrid: pos,
            wallPotential: nil, steps: 20, config: cfg
        )
        let finalMass = flowSensorimotorMass(final, config: cfg).item(Float.self)

        XCTAssertGreaterThan(initialMass, 0)
        let relativeChange = abs(finalMass - initialMass) / initialMass
        XCTAssertLessThan(relativeChange, 0.01, "reintegration must conserve body mass; drifted \(relativeChange)")
    }

    func testRolloutDifferentiableOnGPU() {
        let cfg = config()
        let p = ruleParams()
        let maps = channelMaps()
        let initial = centeredBlob()
        let pos = flowSensorimotorPosGrid(sx: sx, sy: sy)

        let inputs = [p.a, p.w, p.b, p.r, p.m, p.s, p.h, initial]
        let labels = ["a", "w", "b", "r", "m", "s", "h", "init"]

        let objective: ([MLXArray]) -> [MLXArray] = { arrays in
            let final = flowSensorimotorRollout(
                initial: arrays[7], a: arrays[0], w: arrays[1], b: arrays[2], r: arrays[3],
                m: arrays[4], s: arrays[5], h: arrays[6],
                c0Idxs: maps.c0Idxs, c1Mask: maps.c1Mask, posGrid: pos,
                wallPotential: nil, steps: 8, config: cfg
            )
            return [flowSensorimotorGyration(final, config: cfg)]
        }

        let valueAndGradFn = valueAndGrad(objective, argumentNumbers: Array(inputs.indices))
        let (value, grads) = valueAndGradFn(inputs)
        MLX.eval(grads + value)

        XCTAssertTrue(value[0].item(Float.self).isFinite)
        for (index, grad) in grads.enumerated() {
            let flat = grad.flattened().asArray(Float.self)
            XCTAssertTrue(flat.allSatisfy { $0.isFinite }, "gradient for \(labels[index]) has non-finite entries")
            let norm = flat.reduce(Float(0)) { $0 + $1 * $1 }
            XCTAssertGreaterThan(norm, 0.0, "gradient for \(labels[index]) is identically zero")
        }
    }

    func testPositiveWallPotentialProducesRepulsiveFlow() {
        let cfg = config()
        let p = ruleParams()
        let maps = channelMaps()
        let fK = flowSensorimotorKernelStack(a: p.a, w: p.w, b: p.b, r: p.r, config: cfg)

        // Uniform low-density field so the alpha gate is near zero and the flow is
        // driven by the growth/wall potential gradient rather than the body's own
        // mass gradient.
        let field = MLXArray([Float](repeating: 0.02, count: sx * sy)).reshaped([1, sx, sy, 1])

        // Positive Gaussian hill at the center. Mass flows down the potential (a
        // negative well attracts), so an obstacle must be a positive potential
        // hill: flow near it points outward, away from the obstacle. This is the
        // repulsion the runner relies on.
        let cx = Float(sx / 2)
        let cy = Float(sy / 2)
        var hill = [Float](repeating: 0.0, count: sx * sy)
        for row in 0..<sx {
            for col in 0..<sy {
                let dr = Float(row) - cx
                let dc = Float(col) - cy
                hill[row * sy + col] = 30.0 * exp(-(dr * dr + dc * dc) / (2.0 * 8.0 * 8.0))
            }
        }
        let wallPotential = MLXArray(hill).reshaped([1, sx, sy, 1])

        let flow = computeFlow(
            field,
            fK: fK, m: p.m, s: p.s, h: p.h,
            c0Idxs: maps.c0Idxs, c1Mask: maps.c1Mask,
            thetaA: cfg.thetaA, n: cfg.n,
            gradientBoundary: cfg.gradientBoundary,
            alphaMode: cfg.alphaMode,
            flowClip: cfg.flowClip,
            growthProfile: cfg.growthProfile,
            chemChannel: nil, chemIncludeInMass: true,
            dd: cfg.dd, sigma: cfg.sigma,
            wallPotential: wallPotential,
            gatherBeforeFFT: true
        )
        // Flow axis 3 is [dy, dx]; channel axis is last.
        let dx = flow[0, 0..., 0..., 1, 0]
        let dy = flow[0, 0..., 0..., 0, 0]
        let offset = 10
        let rightDx = dx[sx / 2, sy / 2 + offset].item(Float.self)
        let leftDx = dx[sx / 2, sy / 2 - offset].item(Float.self)
        let belowDy = dy[sx / 2 + offset, sy / 2].item(Float.self)
        let aboveDy = dy[sx / 2 - offset, sy / 2].item(Float.self)

        XCTAssertGreaterThan(rightDx, 0.0, "flow right of a positive obstacle must point right (outward)")
        XCTAssertLessThan(leftDx, 0.0, "flow left of a positive obstacle must point left (outward)")
        XCTAssertGreaterThan(belowDy, 0.0, "flow below a positive obstacle must point down (outward)")
        XCTAssertLessThan(aboveDy, 0.0, "flow above a positive obstacle must point up (outward)")
    }

    private func blob(value: Float, centerRow: Int, centerCol: Int, half: Int) -> MLXArray {
        var values = [Float](repeating: 0.0, count: sx * sy)
        for row in (centerRow - half)..<(centerRow + half) {
            for col in (centerCol - half)..<(centerCol + half) {
                values[row * sy + col] = value
            }
        }
        return MLXArray(values).reshaped([1, sx, sy, 1])
    }

    func testEmbeddingTracksCentroidDisplacement() {
        let cfg = config()
        let centered = blob(value: 0.5, centerRow: sx / 2, centerCol: sy / 2, half: 4)
        let shifted = blob(value: 0.5, centerRow: sx / 2, centerCol: 3 * sy / 4, half: 4)

        let centeredEmbedding = flowSensorimotorEmbedding(centered, config: cfg)
        let shiftedEmbedding = flowSensorimotorEmbedding(shifted, config: cfg)

        XCTAssertEqual(centeredEmbedding.x, 0.0, accuracy: 0.02)
        XCTAssertEqual(centeredEmbedding.y, 0.0, accuracy: 0.02)
        XCTAssertEqual(shiftedEmbedding.x, 0.25, accuracy: 0.02, "blob at 3/4 width sits a quarter-grid right of center")
        XCTAssertGreaterThan(centeredEmbedding.compactness, 0.0)
    }

    func testViabilityDistinguishesCoherentDispersedFragmented() {
        let cfg = config()
        let thresholds = FlowSensorimotorViabilityThresholds(
            componentMassThreshold: 0.01, maxGyration: 12.0,
            minLargestComponentFraction: 0.6, maxComponentCount: 1
        )

        let coherent = blob(value: 0.5, centerRow: sx / 2, centerCol: sy / 2, half: 4)
        let dispersed = MLXArray([Float](repeating: 0.02, count: sx * sy)).reshaped([1, sx, sy, 1])
        let twoBodies = blob(value: 0.5, centerRow: sx / 2, centerCol: sy / 4, half: 4)
            + blob(value: 0.5, centerRow: sx / 2, centerCol: 3 * sy / 4, half: 4)

        XCTAssertTrue(flowSensorimotorViability(coherent, config: cfg, thresholds: thresholds).alive)

        let dispersedViability = flowSensorimotorViability(dispersed, config: cfg, thresholds: thresholds)
        XCTAssertFalse(dispersedViability.alive, "a field spread across the grid disperses past the gyration bound")
        XCTAssertGreaterThan(dispersedViability.gyration, thresholds.maxGyration)

        let fragmentedViability = flowSensorimotorViability(twoBodies, config: cfg, thresholds: thresholds)
        XCTAssertFalse(fragmentedViability.alive, "two separated bodies fail the single-component requirement")
        XCTAssertGreaterThan(fragmentedViability.componentCount, 1.0)
    }

    func testGoalLossRewardsMatchingGoalAndIsDifferentiable() {
        let cfg = config()
        let p = ruleParams()
        let maps = channelMaps()
        let pos = flowSensorimotorPosGrid(sx: sx, sy: sy)
        let initial = centeredBlob()

        let final = flowSensorimotorRollout(
            initial: initial, a: p.a, w: p.w, b: p.b, r: p.r, m: p.m, s: p.s, h: p.h,
            c0Idxs: maps.c0Idxs, c1Mask: maps.c1Mask, posGrid: pos,
            wallPotential: nil, steps: 8, config: cfg
        )
        let reached = flowSensorimotorEmbedding(final, config: cfg)
        let matchingGoal = FlowSensorimotorGoal(compactness: reached.compactness, x: reached.x, y: reached.y)
        let farGoal = FlowSensorimotorGoal(compactness: reached.compactness, x: reached.x + 0.4, y: reached.y)

        let matchingLoss = flowSensorimotorGoalLoss(finalState: final, goal: matchingGoal, config: cfg).item(Float.self)
        let farLoss = flowSensorimotorGoalLoss(finalState: final, goal: farGoal, config: cfg).item(Float.self)
        XCTAssertLessThan(matchingLoss, farLoss, "a goal at the reached behavior must score better than a distant one")

        let inputs = [p.a, p.w, p.b, p.r, p.m, p.s, p.h, initial]
        let objective: ([MLXArray]) -> [MLXArray] = { arrays in
            let rolled = flowSensorimotorRollout(
                initial: arrays[7], a: arrays[0], w: arrays[1], b: arrays[2], r: arrays[3],
                m: arrays[4], s: arrays[5], h: arrays[6],
                c0Idxs: maps.c0Idxs, c1Mask: maps.c1Mask, posGrid: pos,
                wallPotential: nil, steps: 8, config: cfg
            )
            return [flowSensorimotorGoalLoss(finalState: rolled, goal: farGoal, config: cfg)]
        }
        let valueAndGradFn = valueAndGrad(objective, argumentNumbers: Array(inputs.indices))
        let (value, grads) = valueAndGradFn(inputs)
        MLX.eval(grads + value)

        XCTAssertTrue(value[0].item(Float.self).isFinite)
        let initGrad = grads[7].flattened().asArray(Float.self)
        XCTAssertTrue(initGrad.allSatisfy { $0.isFinite })
        XCTAssertGreaterThan(initGrad.reduce(Float(0)) { $0 + abs($1) }, 0.0, "goal loss must produce a gradient on the initial state")
    }
}
