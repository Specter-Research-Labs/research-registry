import Foundation
import Logging
import MLX
import MLXFFT

// Sensorimotor-agency discovery on Flow-Lenia: the same IMGEP diversity search +
// gradient descent + curriculum as the Hamon 2024 sensorimotor protocol, but the
// inner physics is the mass-conserving Flow-Lenia integrator (flow field +
// reintegration transport) instead of asymptotic Lenia. Because mass is
// conserved, "death" is dispersal (the body spreads thin or fragments), not the
// mass decay used by the asymptotic runner, so viability and the behavior
// embedding are built from gyration and fragmentation rather than mass collapse.
// Obstacles are positive wall potentials: mass flows down the growth potential
// (a negative well attracts), so a positive hill repels mass and acts as a wall.
// CLI: discover sensorimotor-flowlenia.

// MARK: - Physics core

// Resolved, physics-only knobs for one Flow-Lenia rollout. Rule parameters
// (a/w/b/r/m/s/h) and the initial state are passed separately because the
// gradient inner loop differentiates through them.
struct FlowSensorimotorStepConfig {
    let sx: Int
    let sy: Int
    let nbK: Int
    let channels: Int
    let learnableChannels: Int
    let dd: Int
    let sigma: Float
    let dt: Float
    let n: Int
    let thetaA: Float
    let R: Float
    let kernelProfile: String
    let gradientBoundary: String
    let alphaMode: String
    let flowClip: String
    let growthProfile: String
    let useTorus: Bool
}

// Differentiable kernel stack fK [1, sx, sy, nbK] built from MLXArray rule
// parameters so gradients reach the kernel-shape parameters. Mirrors the
// flowlenia_2022_colab branch of normalizedSpatialKernelStack, but kept as a
// pure-MLXArray path (the forward builder consumes plain-Float ResolvedParams and
// is not differentiable). a/w/b are [nbK, bumps]; r is [nbK].
func flowSensorimotorKernelStack(
    a: MLXArray,
    w: MLXArray,
    b: MLXArray,
    r: MLXArray,
    config: FlowSensorimotorStepConfig
) -> MLXArray {
    guard config.kernelProfile == "flowlenia_2022_colab" else {
        fatalError("flow-lenia sensorimotor kernel stack requires the flowlenia_2022_colab profile, got \(config.kernelProfile)")
    }
    let midX = config.sx / 2
    let midY = config.sy / 2
    let coordsX = MLXArray(Array(0..<config.sx).map { Float($0 - midX) })
    let coordsY = MLXArray(Array(0..<config.sy).map { Float($0 - midY) })
    let (X, Y) = meshgrid(coordsX, coordsY)
    let DBase = MLX.sqrt(X * X + Y * Y)

    let radiusBase = config.R + 15.0
    var kernels: [MLXArray] = []
    kernels.reserveCapacity(config.nbK)
    for k in 0..<config.nbK {
        let divisor = r[k] * MLXArray(radiusBase)
        let D = DBase / divisor
        let profiled = kernelProfile(D, a: a[k], w: w[k], b: b[k], kernelProfile: "flowlenia_2022_colab")
        let gate = sigmoid(-(D - MLXArray(Float(1.0))) * MLXArray(Float(10.0)))
        kernels.append(gate * profiled)
    }
    let stacked = MLX.stacked(kernels, axis: 2)
    let sumK = stacked.sum(axes: [0, 1], keepDims: true)
    let normalized = stacked / (sumK + MLXArray(Float(1e-10)))
    let shifted = fftshift2(normalized)
    let fK = MLXFFT.fft2(shifted, axes: [0, 1])
    return fK.expandedDimensions(axis: 0)
}

// Reintegration position grid [1, sx, sy, 2, 1] in (row, col) order, cell-centered.
func flowSensorimotorPosGrid(sx: Int, sy: Int) -> MLXArray {
    let coordsX = MLXArray((0..<sx).map { Float($0) })
    let coordsY = MLXArray((0..<sy).map { Float($0) })
    let (X, Y) = meshgrid(coordsX, coordsY)
    var pos = MLX.stacked([Y, X], axis: -1) + MLXArray(Float(0.5))
    pos = pos.expandedDimensions(axis: 0)
    return pos.expandedDimensions(axis: -1)
}

// One differentiable, mass-conserving Flow-Lenia rollout. `initial` is
// [1, sx, sy, channels]; `wallPotential` (positive inside obstacles) is added to
// the growth potential so advection steers mass away from it. Returns the final
// state [1, sx, sy, channels].
func flowSensorimotorRollout(
    initial: MLXArray,
    a: MLXArray,
    w: MLXArray,
    b: MLXArray,
    r: MLXArray,
    m: MLXArray,
    s: MLXArray,
    h: MLXArray,
    c0Idxs: MLXArray,
    c1Mask: MLXArray,
    posGrid: MLXArray,
    wallPotential: MLXArray?,
    steps: Int,
    config: FlowSensorimotorStepConfig
) -> MLXArray {
    let fK = flowSensorimotorKernelStack(a: a, w: w, b: b, r: r, config: config)
    var state = initial
    for _ in 0..<steps {
        state = leniaStepBatched(
            state,
            fK: fK, m: m, s: s, h: h,
            c0Idxs: c0Idxs, c1Mask: c1Mask,
            posGrid: posGrid,
            dt: config.dt, dd: config.dd, sigma: config.sigma,
            n: config.n, thetaA: config.thetaA,
            gradientBoundary: config.gradientBoundary,
            alphaMode: config.alphaMode,
            flowClip: config.flowClip,
            growthProfile: config.growthProfile,
            useTorus: config.useTorus,
            chemChannel: nil,
            chemIncludeInMass: true,
            sx: config.sx, sy: config.sy,
            wallPotential: wallPotential,
            gatherBeforeFFT: true
        )
    }
    return state
}

// MARK: - Differentiable behavior metrics

// Per-cell mass of the learnable body (obstacle channels excluded), [1, sx, sy].
func flowSensorimotorMassMap(_ state: MLXArray, config: FlowSensorimotorStepConfig) -> MLXArray {
    let body = state[0..., 0..., 0..., 0..<config.learnableChannels]
    return body.sum(axis: -1)
}

// Total conserved body mass (scalar MLXArray).
func flowSensorimotorMass(_ state: MLXArray, config: FlowSensorimotorStepConfig) -> MLXArray {
    return flowSensorimotorMassMap(state, config: config).sum()
}

// Mass-weighted centroid in (row, col), scalar MLXArrays. Floored mass avoids a
// divide-by-zero only when the body is numerically empty; callers gate on
// viability before trusting the value.
func flowSensorimotorCentroid(
    _ state: MLXArray,
    config: FlowSensorimotorStepConfig
) -> (row: MLXArray, col: MLXArray) {
    let massMap = flowSensorimotorMassMap(state, config: config)[0]
    let total = massMap.sum() + MLXArray(Float(1e-8))
    let rows = MLXArray((0..<config.sx).map { Float($0) }).reshaped([config.sx, 1])
    let cols = MLXArray((0..<config.sy).map { Float($0) }).reshaped([1, config.sy])
    let row = (massMap * rows).sum() / total
    let col = (massMap * cols).sum() / total
    return (row, col)
}

// Radius of gyration: sqrt of the mass-weighted mean squared distance from the
// centroid. Low gyration is a compact body; runaway gyration is dispersal, the
// mass-conserving analogue of the asymptotic runner's mass collapse.
func flowSensorimotorGyration(
    _ state: MLXArray,
    config: FlowSensorimotorStepConfig
) -> MLXArray {
    let massMap = flowSensorimotorMassMap(state, config: config)[0]
    let total = massMap.sum() + MLXArray(Float(1e-8))
    let rows = MLXArray((0..<config.sx).map { Float($0) }).reshaped([config.sx, 1])
    let cols = MLXArray((0..<config.sy).map { Float($0) }).reshaped([1, config.sy])
    let cr = (massMap * rows).sum() / total
    let cc = (massMap * cols).sum() / total
    let dr = rows - cr
    let dc = cols - cc
    let sq = dr * dr + dc * dc
    return MLX.sqrt((massMap * sq).sum() / total)
}
