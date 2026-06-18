import Foundation
import XCTest
@testable import LeniaCore
import MLX
import MLXFFT

// Spike: confirm the Flow-Lenia step (FFT growth + sobel flow + reintegration
// transport) is differentiable end to end via MLX valueAndGrad, so the
// gradient-descent inner loop of the sensorimotor IMGEP search can be ported
// from asymptotic Lenia onto the mass-conserving Flow-Lenia integrator.
//
// The rollout goes through the public uncompiled `leniaStepBatched` (compute
// flow + reintegration), and `fK` is built from MLXArray rule parameters inside
// the traced closure so gradients reach the kernel-shape parameters, not just
// the initial state.
private final class FlowLeniaDiffMarker {}

final class FlowLeniaDifferentiabilityTests: XCTestCase {
    override func setUp() {
        super.setUp()
        do {
            try LeniaMetalLibrarySupport.ensureAvailable(
                executableURL: Bundle(for: FlowLeniaDiffMarker.self).executableURL
            )
        } catch {
            XCTFail("Failed to prepare MLX metallib: \(error)")
        }
    }

    private let sx = 64
    private let sy = 64
    private let nbK = 3
    private let channels = 1
    private let dd = 3
    private let sigma: Float = 0.65
    private let dt: Float = 0.1
    private let n = 2
    private let thetaA: Float = 1.0
    private let rolloutSteps = 12

    private func centeredCoords() -> (MLXArray, MLXArray) {
        let coordsX = MLXArray((0..<sx).map { Float($0 - sx / 2) })
        let coordsY = MLXArray((0..<sy).map { Float($0 - sy / 2) })
        return meshgrid(coordsX, coordsY)
    }

    private func posGrid() -> MLXArray {
        let coordsX = MLXArray((0..<sx).map { Float($0) })
        let coordsY = MLXArray((0..<sy).map { Float($0) })
        let (X, Y) = meshgrid(coordsX, coordsY)
        var pos = MLX.stacked([Y, X], axis: -1) + MLXArray(Float(0.5))
        pos = pos.expandedDimensions(axis: 0)
        return pos.expandedDimensions(axis: -1)
    }

    // Centered concentration target reused as the goal-mask loss, mirroring the
    // paper's collapse/centroid embedding.
    private func goalMask() -> MLXArray {
        let (X, Y) = centeredCoords()
        let D = MLX.sqrt(X * X + Y * Y) / MLXArray(Float(10.0))
        let inner = (D .< MLXArray(Float(0.5))).asType(.float32) * MLXArray(Float(0.85))
        let outer = (D .< MLXArray(Float(1.0))).asType(.float32) * MLXArray(Float(0.15))
        return (inner + outer) * MLXArray(Float(0.9))
    }

    private func initialState() -> MLXArray {
        var values = [Float](repeating: 0.0, count: sx * sy)
        let half = 4
        for row in (sx / 2 - half)..<(sx / 2 + half) {
            for col in (sy / 2 - half)..<(sy / 2 + half) {
                values[row * sy + col] = 0.5
            }
        }
        return MLXArray(values).reshaped([1, sx, sy, 1])
    }

    private func buildFK(a: MLXArray, w: MLXArray, b: MLXArray, r: MLXArray) -> MLXArray {
        let (X, Y) = centeredCoords()
        let DBase = MLX.sqrt(X * X + Y * Y)
        var kernels: [MLXArray] = []
        kernels.reserveCapacity(nbK)
        for k in 0..<nbK {
            let divisor = r[k] * MLXArray(Float(28.0)) // (R + 15) with R = 13, the flowlenia_2022_colab scaling
            let D = DBase / divisor
            let profiled = kernelProfile(D, a: a[k], w: w[k], b: b[k], kernelProfile: "flowlenia_2022_colab")
            let gate = sigmoid(-(D - MLXArray(Float(1.0))) * MLXArray(Float(10.0)))
            kernels.append(gate * profiled)
        }
        let stacked = MLX.stacked(kernels, axis: 2)
        let sumK = stacked.sum(axes: [0, 1], keepDims: true)
        let normalized = stacked / (sumK + MLXArray(Float(1e-10)))
        let shifted = fftshift2For(normalized)
        let fK = MLXFFT.fft2(shifted, axes: [0, 1])
        return fK.expandedDimensions(axis: 0)
    }

    private func fftshift2For(_ x: MLXArray) -> MLXArray {
        var result = MLX.roll(x, shift: x.shape[0] / 2, axis: 0)
        result = MLX.roll(result, shift: x.shape[1] / 2, axis: 1)
        return result
    }

    private func rollout(initial: MLXArray, fK: MLXArray, m: MLXArray, s: MLXArray, h: MLXArray,
                         c0Idxs: MLXArray, c1Mask: MLXArray, posGrid: MLXArray) -> MLXArray {
        var state = initial
        for _ in 0..<rolloutSteps {
            state = leniaStepBatched(
                state,
                fK: fK, m: m, s: s, h: h,
                c0Idxs: c0Idxs, c1Mask: c1Mask,
                posGrid: posGrid,
                dt: dt, dd: dd, sigma: sigma,
                n: n, thetaA: thetaA,
                gradientBoundary: "zero_pad",
                alphaMode: "mass",
                flowClip: "none",
                growthProfile: "gaussian",
                useTorus: false,
                chemChannel: nil,
                chemIncludeInMass: true,
                sx: sx, sy: sy
            )
        }
        return state
    }

    private func gradNorm(_ g: MLXArray) -> Float {
        let values = g.flattened().asArray(Float.self)
        var sumSq: Float = 0
        for v in values { sumSq += v * v }
        return sumSq.squareRoot()
    }

    private func allFinite(_ g: MLXArray) -> Bool {
        g.flattened().asArray(Float.self).allSatisfy { $0.isFinite }
    }

    // Full chain: gradients of a goal-mask loss w.r.t. kernel-shape params
    // (a, w, b, r), growth params (m, s, h), and the initial state.
    func testFlowLeniaRolloutDifferentiableThroughKernelConstruction() {
        let c0Idxs = MLXArray((0..<nbK).map { _ in Int32(0) })
        let c1Mask = MLXArray([Float](repeating: 1.0, count: channels * nbK)).reshaped([channels, nbK])
        let pos = posGrid()
        let target = goalMask()

        let a0 = MLXArray([Float](repeating: 0.5, count: nbK * 3)).reshaped([nbK, 3])
        let w0 = MLXArray([Float](repeating: 0.15, count: nbK * 3)).reshaped([nbK, 3])
        let b0 = MLXArray([Float](repeating: 0.6, count: nbK * 3)).reshaped([nbK, 3])
        let r0 = MLXArray([Float](repeating: 0.7, count: nbK))
        let m0 = MLXArray([Float](repeating: 0.15, count: nbK))
        let s0 = MLXArray([Float](repeating: 0.015, count: nbK))
        let h0 = MLXArray([Float](repeating: 0.3, count: nbK))
        let init0 = initialState()

        let inputs = [a0, w0, b0, r0, m0, s0, h0, init0]
        let labels = ["a", "w", "b", "r", "m", "s", "h", "init"]

        let differentiate: ([MLXArray]) -> [MLXArray] = { (arrays: [MLXArray]) -> [MLXArray] in
            let fK = self.buildFK(a: arrays[0], w: arrays[1], b: arrays[2], r: arrays[3])
            let finalState = self.rollout(
                initial: arrays[7], fK: fK, m: arrays[4], s: arrays[5], h: arrays[6],
                c0Idxs: c0Idxs, c1Mask: c1Mask, posGrid: pos
            )
            let field = finalState[0, 0..., 0..., 0]
            let diff = target - field
            let loss = MLX.sqrt((diff * diff).sum())
            return [loss]
        }

        let objective = valueAndGrad(differentiate, argumentNumbers: Array(inputs.indices))
        let (value, grads): ([MLXArray], [MLXArray]) = Device.withDefaultDevice(Device(.cpu)) {
            let (v, g) = objective(inputs)
            MLX.eval(g + v)
            return (v, g)
        }

        let lossValue = value[0].item(Float.self)
        XCTAssertTrue(lossValue.isFinite, "loss must be finite, got \(lossValue)")
        XCTAssertEqual(grads.count, inputs.count, "one gradient per differentiated input")

        for (index, grad) in grads.enumerated() {
            let norm = gradNorm(grad)
            print("grad[\(labels[index])] norm = \(norm)")
            XCTAssertTrue(allFinite(grad), "gradient for \(labels[index]) has non-finite entries")
            XCTAssertGreaterThan(norm, 0.0, "gradient for \(labels[index]) is identically zero")
        }
    }

    // Transport-only diagnostic: hold the kernel stack as the differentiated
    // variable. If kernel construction above ever fails, this localizes whether
    // the reintegration transport itself carries gradients.
    func testFlowLeniaReintegrationCarriesGradient() {
        let c0Idxs = MLXArray((0..<nbK).map { _ in Int32(0) })
        let c1Mask = MLXArray([Float](repeating: 1.0, count: channels * nbK)).reshaped([channels, nbK])
        let pos = posGrid()
        let target = goalMask()

        let a0 = MLXArray([Float](repeating: 0.5, count: nbK * 3)).reshaped([nbK, 3])
        let w0 = MLXArray([Float](repeating: 0.15, count: nbK * 3)).reshaped([nbK, 3])
        let b0 = MLXArray([Float](repeating: 0.6, count: nbK * 3)).reshaped([nbK, 3])
        let r0 = MLXArray([Float](repeating: 0.7, count: nbK))
        let kStack = buildFK(a: a0, w: w0, b: b0, r: r0) // [1, sx, sy, nbK]
        MLX.eval(kStack)

        let m0 = MLXArray([Float](repeating: 0.15, count: nbK))
        let s0 = MLXArray([Float](repeating: 0.015, count: nbK))
        let h0 = MLXArray([Float](repeating: 0.3, count: nbK))
        let init0 = initialState()

        let inputs = [kStack, m0, s0, h0, init0]
        let labels = ["fK", "m", "s", "h", "init"]

        let differentiate: ([MLXArray]) -> [MLXArray] = { (arrays: [MLXArray]) -> [MLXArray] in
            let finalState = self.rollout(
                initial: arrays[4], fK: arrays[0], m: arrays[1], s: arrays[2], h: arrays[3],
                c0Idxs: c0Idxs, c1Mask: c1Mask, posGrid: pos
            )
            let field = finalState[0, 0..., 0..., 0]
            let diff = target - field
            let loss = MLX.sqrt((diff * diff).sum())
            return [loss]
        }

        let objective = valueAndGrad(differentiate, argumentNumbers: Array(inputs.indices))
        let (value, grads): ([MLXArray], [MLXArray]) = Device.withDefaultDevice(Device(.cpu)) {
            let (v, g) = objective(inputs)
            MLX.eval(g + v)
            return (v, g)
        }

        XCTAssertTrue(value[0].item(Float.self).isFinite)
        for (index, grad) in grads.enumerated() {
            let norm = gradNorm(grad)
            print("grad[\(labels[index])] norm = \(norm)")
            XCTAssertTrue(allFinite(grad), "gradient for \(labels[index]) has non-finite entries")
            XCTAssertGreaterThan(norm, 0.0, "gradient for \(labels[index]) is identically zero")
        }
    }

    private func maxAbsDiff(_ a: MLXArray, _ b: MLXArray) -> Float {
        MLX.abs(a - b).max().item(Float.self)
    }

    // Caveat 1: the GPU backward crash is `[scatter] complex64` from the VJP of
    // `take` on the complex FFT. Gathering the source channels BEFORE the FFT
    // makes the take VJP a real-valued scatter (GPU-supported) and is
    // mathematically identical because the channel gather commutes with the
    // spatial FFT. This confirms both: identical gradients, and GPU runs.
    func testTakeBeforeFFTIsIdenticalAndRunsOnGPU() {
        let a0 = MLXArray([Float](repeating: 0.5, count: nbK * 3)).reshaped([nbK, 3])
        let w0 = MLXArray([Float](repeating: 0.15, count: nbK * 3)).reshaped([nbK, 3])
        let b0 = MLXArray([Float](repeating: 0.6, count: nbK * 3)).reshaped([nbK, 3])
        let r0 = MLXArray([Float](repeating: 0.7, count: nbK))
        let fK = buildFK(a: a0, w: w0, b: b0, r: r0)
        MLX.eval(fK)
        let c0Idxs = MLXArray((0..<nbK).map { _ in Int32(0) })
        let A0 = initialState()

        // take AFTER fft (production order): complex scatter in the backward.
        let afterFFT: ([MLXArray]) -> [MLXArray] = { arrays in
            let A = arrays[0]
            let fA = MLXFFT.fft2(A, axes: [1, 2])
            let fAK = fA.take(c0Idxs, axis: 3)
            let U = MLXFFT.ifft2(fAK * fK, axes: [1, 2]).realPart()
            return [(U * U).sum()]
        }
        // take BEFORE fft (proposed fix): real scatter in the backward.
        let beforeFFT: ([MLXArray]) -> [MLXArray] = { arrays in
            let A = arrays[0]
            let Asel = A.take(c0Idxs, axis: 3)
            let fAK = MLXFFT.fft2(Asel, axes: [1, 2])
            let U = MLXFFT.ifft2(fAK * fK, axes: [1, 2]).realPart()
            return [(U * U).sum()]
        }

        let afterGrad = valueAndGrad(afterFFT, argumentNumbers: [0])
        let beforeGrad = valueAndGrad(beforeFFT, argumentNumbers: [0])

        // Production order only differentiates on CPU (GPU complex scatter aborts).
        let gAfterCPU = Device.withDefaultDevice(Device(.cpu)) { () -> MLXArray in
            let (_, g) = afterGrad([A0]); MLX.eval(g); return g[0]
        }
        // Fix order on CPU (math reference) and on GPU (must not crash).
        let gBeforeCPU = Device.withDefaultDevice(Device(.cpu)) { () -> MLXArray in
            let (_, g) = beforeGrad([A0]); MLX.eval(g); return g[0]
        }
        let (_, gpuGrads) = beforeGrad([A0]) // default device is GPU in the test process
        MLX.eval(gpuGrads)
        let gBeforeGPU = gpuGrads[0]

        XCTAssertLessThan(maxAbsDiff(gAfterCPU, gBeforeCPU), 1e-3,
                          "gather-before-FFT must match gather-after-FFT gradients")
        XCTAssertLessThan(maxAbsDiff(gBeforeCPU, gBeforeGPU), 1e-3,
                          "fixed order must produce the same gradient on GPU as CPU")
        XCTAssertTrue(allFinite(gBeforeGPU))
    }

    // Caveat 2: confirm the autograd is correct (so the tiny rule-parameter
    // gradients are genuine loss-insensitivity at a cold start, not a detached
    // graph). Central finite difference along the initial-state direction must
    // match the analytic directional derivative.
    func testInitGradientMatchesFiniteDifference() {
        let c0Idxs = MLXArray((0..<nbK).map { _ in Int32(0) })
        let c1Mask = MLXArray([Float](repeating: 1.0, count: channels * nbK)).reshaped([channels, nbK])
        let pos = posGrid()
        let target = goalMask()

        let a0 = MLXArray([Float](repeating: 0.5, count: nbK * 3)).reshaped([nbK, 3])
        let w0 = MLXArray([Float](repeating: 0.15, count: nbK * 3)).reshaped([nbK, 3])
        let b0 = MLXArray([Float](repeating: 0.6, count: nbK * 3)).reshaped([nbK, 3])
        let r0 = MLXArray([Float](repeating: 0.7, count: nbK))
        let fK = buildFK(a: a0, w: w0, b: b0, r: r0)
        let m0 = MLXArray([Float](repeating: 0.15, count: nbK))
        let s0 = MLXArray([Float](repeating: 0.015, count: nbK))
        let h0 = MLXArray([Float](repeating: 0.3, count: nbK))
        let init0 = initialState()

        func loss(_ initState: MLXArray) -> MLXArray {
            let finalState = self.rollout(
                initial: initState, fK: fK, m: m0, s: s0, h: h0,
                c0Idxs: c0Idxs, c1Mask: c1Mask, posGrid: pos
            )
            let field = finalState[0, 0..., 0..., 0]
            let diff = target - field
            return MLX.sqrt((diff * diff).sum())
        }

        let result: (analytic: Float, numeric: Float) = Device.withDefaultDevice(Device(.cpu)) {
            let gradFn = valueAndGrad({ (arrays: [MLXArray]) -> [MLXArray] in [loss(arrays[0])] },
                                      argumentNumbers: [0])
            let (_, grads) = gradFn([init0])
            let gInit = grads[0]
            // Directional derivative along the current init: d/dt loss(init * (1 + t)) at t = 0.
            let analytic = (gInit * init0).sum().item(Float.self)
            let eps: Float = 1e-2
            let lossPlus = loss(init0 * MLXArray(1.0 + eps)).item(Float.self)
            let lossMinus = loss(init0 * MLXArray(1.0 - eps)).item(Float.self)
            let numeric = (lossPlus - lossMinus) / (2 * eps)
            return (analytic, numeric)
        }

        print("init directional derivative: analytic = \(result.analytic), numeric = \(result.numeric)")
        XCTAssertNotEqual(result.numeric, 0.0, accuracy: 1e-6, "finite-difference signal must be resolvable")
        let relativeError = abs(result.analytic - result.numeric) / max(abs(result.numeric), 1e-6)
        XCTAssertLessThan(relativeError, 0.05, "analytic gradient must match finite difference within 5%")
    }

    // Incidental finding: a bare `valueAndGrad { ([MLXArray]) -> [MLXArray] }`
    // (as used at Sensorimotor24.swift:1647 and QD24.swift:3025) defaults to
    // `argumentNumbers: [0]`, so only the FIRST input array is differentiated;
    // the rest come back with no gradient. Confirm the semantics directly.
    func testDefaultArgumentNumbersDifferentiatesOnlyFirstInput() {
        let x0 = MLXArray([Float(2.0)])
        let x1 = MLXArray([Float(3.0)])
        let x2 = MLXArray([Float(4.0)])
        let sumOfSquares: ([MLXArray]) -> [MLXArray] = { a in
            [(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]).sum()]
        }

        let defaultGrad = valueAndGrad(sumOfSquares)
        let (_, gDefault) = defaultGrad([x0, x1, x2])
        MLX.eval(gDefault)
        XCTAssertEqual(gDefault.count, 1, "default argumentNumbers differentiates only the first input")
        XCTAssertEqual(gDefault[0].item(Float.self), 4.0, accuracy: 1e-5, "d/dx0 (x0^2) = 2*x0 = 4")

        let allGrad = valueAndGrad(sumOfSquares, argumentNumbers: [0, 1, 2])
        let (_, gAll) = allGrad([x0, x1, x2])
        MLX.eval(gAll)
        XCTAssertEqual(gAll.count, 3, "explicit argumentNumbers differentiates every input")
        XCTAssertEqual(gAll[1].item(Float.self), 6.0, accuracy: 1e-5)
        XCTAssertEqual(gAll[2].item(Float.self), 8.0, accuracy: 1e-5)
    }
}
