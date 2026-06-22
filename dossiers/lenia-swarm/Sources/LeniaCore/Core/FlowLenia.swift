import Foundation
import MLX
import MLXFFT
import MLXRandom

public struct CompiledKernels: @unchecked Sendable {
    public let fK: MLXArray
    public let m: MLXArray
    public let s: MLXArray
    public let h: MLXArray
    public let c0Idxs: MLXArray
    public let c1Mask: MLXArray

    public init(fK: MLXArray, m: MLXArray, s: MLXArray, h: MLXArray, c0Idxs: MLXArray, c1Mask: MLXArray) {
        self.fK = fK
        self.m = m
        self.s = s
        self.h = h
        self.c0Idxs = c0Idxs
        self.c1Mask = c1Mask
    }
}

public struct BatchedConfig: Sendable {
    public let sx: Int
    public let sy: Int
    public let channels: Int
    public let nbK: Int
    public let dt: Float
    public let dd: Int
    public let sigma: Float
    public let n: Int
    public let thetaA: Float
    public let border: String
    public let implementation: ImplementationSettings
    public let chemChannel: Int?
    public let chemIncludeInMass: Bool

    public init(
        sx: Int,
        sy: Int,
        channels: Int,
        nbK: Int,
        dt: Float,
        dd: Int,
        sigma: Float,
        n: Int,
        thetaA: Float,
        border: String,
        implementation: ImplementationSettings,
        chemChannel: Int?,
        chemIncludeInMass: Bool
    ) {
        self.sx = sx
        self.sy = sy
        self.channels = channels
        self.nbK = nbK
        self.dt = dt
        self.dd = dd
        self.sigma = sigma
        self.n = n
        self.thetaA = thetaA
        self.border = border
        self.implementation = implementation
        self.chemChannel = chemChannel
        self.chemIncludeInMass = chemIncludeInMass
    }
}

public func batchedConfigFromRuntime(_ config: LeniaRuntimeConfig) -> BatchedConfig {
    let chemChannel = (config.chemotaxis?.enabled ?? false) ? config.chemotaxis?.channel_index : nil
    let chemInclude = config.chemotaxis?.include_in_mass ?? true
    return BatchedConfig(
        sx: config.sx,
        sy: config.sy,
        channels: config.channels,
        nbK: config.nbK,
        dt: config.dt,
        dd: config.dd,
        sigma: config.sigma,
        n: config.n,
        thetaA: config.thetaA,
        border: config.border,
        implementation: config.implementation,
        chemChannel: chemChannel,
        chemIncludeInMass: chemInclude
    )
}

public func meshgrid(_ x: MLXArray, _ y: MLXArray) -> (MLXArray, MLXArray) {
    let xLen = x.shape[0]
    let yLen = y.shape[0]
    let X = MLX.broadcast(x.reshaped([xLen, 1]), to: [xLen, yLen])
    let Y = MLX.broadcast(y.reshaped([1, yLen]), to: [xLen, yLen])
    return (X, Y)
}

private func validateFlowLeniaConfig(_ config: BatchedConfig) {
    let validBorders = ["wall", "torus"]
    if !validBorders.contains(config.border) {
        fatalError("reintegration.border must be one of: \(validBorders.joined(separator: ", ")).")
    }
    if config.chemChannel != nil && config.chemIncludeInMass {
        fatalError("chemotaxis.include_in_mass must be false for Flow Lenia; the chemotaxis field is external and should not contribute to mass.")
    }
}

public func rollMultiAxis(_ arr: MLXArray, shifts: [Int], axes: [Int]) -> MLXArray {
    var result = arr
    for (shift, axis) in zip(shifts, axes) {
        result = MLX.roll(result, shift: shift, axis: axis)
    }
    return result
}

private func pad2d(_ A: MLXArray, pad: Int) -> MLXArray {
    if pad == 0 {
        return A
    }
    let batch = A.shape[0]
    let sx = A.shape[1]
    let sy = A.shape[2]
    let channels = A.shape[3]

    let zerosRow = MLX.zeros([batch, pad, sy, channels])
    let paddedY = MLX.concatenated([zerosRow, A, zerosRow], axis: 1)
    let zerosCol = MLX.zeros([batch, sx + pad + pad, pad, channels])
    return MLX.concatenated([zerosCol, paddedY, zerosCol], axis: 2)
}

func fftshift2(_ x: MLXArray) -> MLXArray {
    let shiftX = x.shape[0] / 2
    let shiftY = x.shape[1] / 2
    var result = MLX.roll(x, shift: shiftX, axis: 0)
    result = MLX.roll(result, shift: shiftY, axis: 1)
    return result
}

func sigmoid(_ x: MLXArray) -> MLXArray {
    let one = MLXArray(Float(1.0))
    return one / (one + MLX.exp(-x))
}

func kernelProfile(_ D: MLXArray, a: MLXArray, w: MLXArray, b: MLXArray, kernelProfile: String) -> MLXArray {
    let DExpanded = D.expandedDimensions(axis: -1)
    let diff = DExpanded - a
    let exponent: MLXArray
    if kernelProfile == "flowlenia_2022_colab" {
        exponent = -(diff * diff) / w
    } else {
        exponent = -(diff * diff) / (MLXArray(2.0) * w * w)
    }
    let gaussian = b * MLX.exp(exponent)
    return gaussian.sum(axis: -1)
}

func normalizedSpatialKernelStack(params: ResolvedParams, config: BatchedConfig) -> MLXArray {
    let midX = config.sx / 2
    let midY = config.sy / 2

    let coordsX = MLXArray(Array(0..<config.sx).map { Float($0 - midX) })
    let coordsY = MLXArray(Array(0..<config.sy).map { Float($0 - midY) })

    let (X, Y) = meshgrid(coordsX, coordsY)
    let XY = X * X
    let YY = Y * Y
    let DBase = MLX.sqrt(XY + YY)

    var kernels: [MLXArray] = []
    kernels.reserveCapacity(config.nbK)
    for k in 0..<config.nbK {
        let rK = params.r[k]
        let kernel: MLXArray
        if config.implementation.kernelProfile.hasPrefix("qd24_") {
            kernel = qd24Kernel(DBase: DBase, beta: params.b[k], r: rK, R: params.R, profile: config.implementation.kernelProfile)
        } else {
            let aK = MLXArray(params.a[k])
            let wK = MLXArray(params.w[k])
            let bK = MLXArray(params.b[k])

            let radiusBase = config.implementation.kernelProfile == "flowlenia_2022_colab" ? (params.R + 15.0) : params.R
            let divisor = MLXArray(radiusBase * rK)
            let D = DBase / divisor
            var profiled = kernelProfile(D, a: aK, w: wK, b: bK, kernelProfile: config.implementation.kernelProfile)
            if config.implementation.kernelProfile == "flowlenia_2022_colab" {
                let gate = sigmoid(-(D - MLXArray(Float(1.0))) * MLXArray(Float(10.0)))
                profiled = gate * profiled
            }
            kernel = profiled
        }
        kernels.append(kernel)
    }

    let stacked = MLX.stacked(kernels, axis: 2)
    let sumK = stacked.sum(axes: [0, 1], keepDims: true)
    return stacked / sumK
}

private func qd24BucketedKernel(DBase: MLXArray, beta: [Float], r: Float, R: Float) -> MLXArray {
    let betaCount = beta.count
    let normalizedDistance = DBase / MLXArray(R)
    let scaled = normalizedDistance * MLXArray(Float(betaCount) / r)
    let gate = MLXArray((scaled .< MLXArray(Float(betaCount))).asArray(Bool.self).map { $0 ? Float(1) : Float(0) })
        .reshaped(scaled.shape)
    let buckets = scaled.asArray(Float.self).map { value -> Float in
        let index = min(max(Int(floor(value)), 0), betaCount - 1)
        return beta[index]
    }
    let bucketArray = MLXArray(buckets).reshaped(scaled.shape)
    let fractional = scaled - MLX.floor(scaled)
    let bellInput = (fractional - MLXArray(Float(0.5))) / MLXArray(Float(0.15))
    let bell = MLX.exp(-(bellInput * bellInput) / MLXArray(Float(2.0)))
    return gate * bucketArray * bell
}

private func qd24Kernel(DBase: MLXArray, beta: [Float], r: Float, R: Float, profile: String) -> MLXArray {
    if profile == "qd24_bucketed_v1" {
        return qd24BucketedKernel(DBase: DBase, beta: beta, r: r, R: R)
    }

    let betaCount = beta.count
    let normalizedDistance = DBase / MLXArray(R)
    let scaled = normalizedDistance * MLXArray(Float(betaCount) / r)
    let values = scaled.asArray(Float.self).map { value -> Float in
        guard value >= 0, value < Float(betaCount) else {
            return 0
        }
        let index = min(max(Int(floor(value)), 0), betaCount - 1)
        let fractional = value - floor(value)
        return beta[index] * qd24NativeCore(fractional, profile: profile)
    }
    return MLXArray(values).reshaped(scaled.shape)
}

private func qd24NativeCore(_ value: Float, profile: String) -> Float {
    if profile == "qd24_life_v1" {
        guard value >= 0, value <= 1 else {
            return 0
        }
        if value < 0.25 {
            return 0.5
        }
        if value <= 0.75 {
            return 1
        }
        return 0
    }

    guard value > 0, value < 1 else {
        return 0
    }
    let alpha: Float = 4
    switch profile {
    case "qd24_bump4_v1":
        return exp(alpha - alpha / (4 * value * (1 - value)))
    case "qd24_quad4_v1":
        return pow(max(0, 4 * value * (1 - value)), alpha)
    case "qd24_step_v1":
        return value >= 0.25 && value <= 0.75 ? 1 : 0
    default:
        fatalError("Unsupported qd24 kernel profile: \(profile)")
    }
}

public func compileKernels(
    params: ResolvedParams,
    config: BatchedConfig,
    c0: [Int],
    c1: [[Int]]
) -> CompiledKernels {
    let nK = normalizedSpatialKernelStack(params: params, config: config)

    let shifted = fftshift2(nK)
    var fK = MLXFFT.fft2(shifted, axes: [0, 1])
    fK = fK.expandedDimensions(axis: 0)

    let c0Idxs = MLXArray(c0.map { Int32($0) })

    var maskFlat: [Float] = []
    for c in 0..<config.channels {
        for k in 0..<config.nbK {
            if c1[c].contains(k) {
                maskFlat.append(1.0)
            } else {
                maskFlat.append(0.0)
            }
        }
    }
    let c1Mask = MLXArray(maskFlat).reshaped([config.channels, config.nbK])

    let mArr = MLXArray(params.m)
    let sArr = MLXArray(params.s)
    let hArr = MLXArray(params.h)

    return CompiledKernels(
        fK: fK,
        m: mArr,
        s: sArr,
        h: hArr,
        c0Idxs: c0Idxs,
        c1Mask: c1Mask
    )
}

public func compilePopulationKernels(
    paramsBatch: [ResolvedParams],
    config: BatchedConfig,
    c0: [Int],
    c1: [[Int]]
) -> CompiledKernels {
    guard !paramsBatch.isEmpty else {
        fatalError("compilePopulationKernels requires at least one parameter set.")
    }

    var spectralKernels: [MLXArray] = []
    spectralKernels.reserveCapacity(paramsBatch.count)
    var flatM: [Float] = []
    var flatS: [Float] = []
    var flatH: [Float] = []
    flatM.reserveCapacity(paramsBatch.count * config.nbK)
    flatS.reserveCapacity(paramsBatch.count * config.nbK)
    flatH.reserveCapacity(paramsBatch.count * config.nbK)

    for params in paramsBatch {
        let nK = normalizedSpatialKernelStack(params: params, config: config)
        let shifted = fftshift2(nK)
        spectralKernels.append(MLXFFT.fft2(shifted, axes: [0, 1]))
        flatM.append(contentsOf: params.m)
        flatS.append(contentsOf: params.s)
        flatH.append(contentsOf: params.h)
    }

    let fK = MLX.stacked(spectralKernels, axis: 0)
    let c0Idxs = MLXArray(c0.map { Int32($0) })

    var maskFlat: [Float] = []
    for c in 0..<config.channels {
        for k in 0..<config.nbK {
            if c1[c].contains(k) {
                maskFlat.append(1.0)
            } else {
                maskFlat.append(0.0)
            }
        }
    }
    let c1Mask = MLXArray(maskFlat).reshaped([config.channels, config.nbK])

    return CompiledKernels(
        fK: fK,
        m: MLXArray(flatM).reshaped([paramsBatch.count, config.nbK]),
        s: MLXArray(flatS).reshaped([paramsBatch.count, config.nbK]),
        h: MLXArray(flatH).reshaped([paramsBatch.count, config.nbK]),
        c0Idxs: c0Idxs,
        c1Mask: c1Mask
    )
}

func growth(_ U: MLXArray, m: MLXArray, s: MLXArray, h: MLXArray, profile: String = "gaussian") -> MLXArray {
    let mB = reshapeKernelParams(m)
    let sB = reshapeKernelParams(s)
    let hB = reshapeKernelParams(h)
    let diff = (U - mB) / sB
    if profile == "stpz" {
        let inside = (MLX.abs(diff) .<= MLXArray(Float(1.0))).asType(.float32)
        let stepped = inside * MLXArray(Float(2.0)) - MLXArray(Float(1.0))
        return stepped * hB
    }
    if profile == "quad4" {
        let radius = MLXArray(Float(3.0)) * sB
        let scaled = (U - mB) / radius
        let body = MLX.pow(MLX.maximum(MLXArray(0.0), MLXArray(Float(1.0)) - scaled * scaled), Float(4.0))
        return (body * MLXArray(Float(2.0)) - MLXArray(Float(1.0))) * hB
    }
    guard profile == "gaussian" else {
        fatalError("Unsupported growth profile: \(profile)")
    }
    let exponent = -(diff * diff) / MLXArray(2.0)
    let bell = MLX.exp(exponent)
    let bellScaled = bell * MLXArray(2.0)
    let bellShifted = bellScaled - MLXArray(1.0)
    return bellShifted * hB
}

private func reshapeKernelParams(_ values: MLXArray) -> MLXArray {
    switch values.shape.count {
    case 1:
        return values.reshaped([1, 1, 1, -1])
    case 2:
        return values.reshaped([values.shape[0], 1, 1, values.shape[1]])
    default:
        fatalError("kernel parameters must have rank 1 or 2")
    }
}

private func sobelBatchedPeriodic(_ A: MLXArray) -> MLXArray {
    let a00 = rollMultiAxis(A, shifts: [1, 1], axes: [1, 2])
    let a01 = rollMultiAxis(A, shifts: [1, 0], axes: [1, 2])
    let a02 = rollMultiAxis(A, shifts: [1, -1], axes: [1, 2])
    let a10 = rollMultiAxis(A, shifts: [0, 1], axes: [1, 2])
    let a12 = rollMultiAxis(A, shifts: [0, -1], axes: [1, 2])
    let a20 = rollMultiAxis(A, shifts: [-1, 1], axes: [1, 2])
    let a21 = rollMultiAxis(A, shifts: [-1, 0], axes: [1, 2])
    let a22 = rollMultiAxis(A, shifts: [-1, -1], axes: [1, 2])

    let two = MLXArray(Float(2.0))
    let a10Scaled = two * a10
    let a12Scaled = two * a12
    let a01Scaled = two * a01
    let a21Scaled = two * a21

    let gxLeft = a00 + a10Scaled
    let gxLeft2 = gxLeft + a20
    let gxRight = a02 + a12Scaled
    let gxRight2 = gxRight + a22
    let gx = gxLeft2 - gxRight2

    let gyLeft = a00 + a01Scaled
    let gyLeft2 = gyLeft + a02
    let gyRight = a20 + a21Scaled
    let gyRight2 = gyRight + a22
    let gy = gyLeft2 - gyRight2

    return MLX.stacked([gy, gx], axis: 3)
}

private func sobelBatched(_ A: MLXArray, useTorus: Bool) -> MLXArray {
    if useTorus {
        return sobelBatchedPeriodic(A)
    }

    let padded = pad2d(A, pad: 1)
    let xEnd = padded.shape[1] - 2
    let yEnd = padded.shape[2] - 2

    let x0 = 0..<xEnd
    let x1 = 1..<(xEnd + 1)
    let x2 = 2..<(xEnd + 2)
    let y0 = 0..<yEnd
    let y1 = 1..<(yEnd + 1)
    let y2 = 2..<(yEnd + 2)

    let a00 = padded[0..., x0, y0, 0...]
    let a01 = padded[0..., x0, y1, 0...]
    let a02 = padded[0..., x0, y2, 0...]
    let a10 = padded[0..., x1, y0, 0...]
    let a12 = padded[0..., x1, y2, 0...]
    let a20 = padded[0..., x2, y0, 0...]
    let a21 = padded[0..., x2, y1, 0...]
    let a22 = padded[0..., x2, y2, 0...]

    let two = MLXArray(Float(2.0))
    let a10Scaled = two * a10
    let a12Scaled = two * a12
    let a01Scaled = two * a01
    let a21Scaled = two * a21

    let gxLeft = a00 + a10Scaled
    let gxLeft2 = gxLeft + a20
    let gxRight = a02 + a12Scaled
    let gxRight2 = gxRight + a22
    let gx = gxLeft2 - gxRight2

    let gyLeft = a00 + a01Scaled
    let gyLeft2 = gyLeft + a02
    let gyRight = a20 + a21Scaled
    let gyRight2 = gyRight + a22
    let gy = gyLeft2 - gyRight2

    return MLX.stacked([gy, gx], axis: 3)
}

private func sobelBatched(_ A: MLXArray, gradientBoundary: String) -> MLXArray {
    switch gradientBoundary {
    case "periodic":
        return sobelBatchedPeriodic(A)
    case "zero_pad":
        return sobelBatched(A, useTorus: false)
    default:
        fatalError("implementation.gradient_boundary must be one of: periodic, zero_pad.")
    }
}

private func massField(_ A: MLXArray, chemChannel: Int?, includeInMass: Bool) -> MLXArray {
    let total = A.sum(axis: -1, keepDims: true)
    guard let channel = chemChannel, !includeInMass else {
        return total
    }
    let chem = A[0..., 0..., 0..., channel].expandedDimensions(axis: -1)
    return total - chem
}

private func clipFlow(_ F: MLXArray, dd: Int, sigma: Float) -> MLXArray {
    let maxFlow = Float(dd) - sigma
    let limit = MLXArray(maxFlow)
    return MLX.clip(F, min: -limit, max: limit)
}

func computeFlow(
    _ A: MLXArray,
    fK: MLXArray,
    m: MLXArray,
    s: MLXArray,
    h: MLXArray,
    c0Idxs: MLXArray,
    c1Mask: MLXArray,
    thetaA: Float,
    n: Int,
    gradientBoundary: String,
    alphaMode: String,
    flowClip: String,
    growthProfile: String = "gaussian",
    chemChannel: Int?,
    chemIncludeInMass: Bool,
    dd: Int,
    sigma: Float,
    wallPotential: MLXArray? = nil
) -> MLXArray {
    return computeFlowAndGrowth(
        A,
        fK: fK, m: m, s: s, h: h, c0Idxs: c0Idxs, c1Mask: c1Mask,
        thetaA: thetaA, n: n,
        gradientBoundary: gradientBoundary, alphaMode: alphaMode, flowClip: flowClip,
        growthProfile: growthProfile,
        chemChannel: chemChannel, chemIncludeInMass: chemIncludeInMass,
        dd: dd, sigma: sigma, wallPotential: wallPotential
    ).flow
}

// Same math as the step's flow stage, but also returns the per-channel growth
// field (the reaction term, before wall potential). Visualization reads both;
// computeFlow delegates here so there is a single source of the flow math.
func computeFlowAndGrowth(
    _ A: MLXArray,
    fK: MLXArray,
    m: MLXArray,
    s: MLXArray,
    h: MLXArray,
    c0Idxs: MLXArray,
    c1Mask: MLXArray,
    thetaA: Float,
    n: Int,
    gradientBoundary: String,
    alphaMode: String,
    flowClip: String,
    growthProfile: String = "gaussian",
    chemChannel: Int?,
    chemIncludeInMass: Bool,
    dd: Int,
    sigma: Float,
    wallPotential: MLXArray? = nil
) -> (flow: MLXArray, growth: MLXArray) {
    let fA = MLXFFT.fft2(A, axes: [1, 2])
    let fAK = fA.take(c0Idxs, axis: 3)
    let fAKfK = fAK * fK
    let UK = MLXFFT.ifft2(fAKfK, axes: [1, 2]).realPart()

    let G = growth(UK, m: m, s: s, h: h, profile: growthProfile)
    let growthField = MLX.matmul(G, c1Mask.T)
    var U = growthField
    if let wp = wallPotential {
        U = U + wp
    }

    let nablaU = sobelBatched(U, gradientBoundary: gradientBoundary)
    let mass = massField(A, chemChannel: chemChannel, includeInMass: chemIncludeInMass)
    let nablaA = sobelBatched(mass, gradientBoundary: gradientBoundary)

    let thetaArr = MLXArray(thetaA)
    let nFloat = Float(n)
    let alpha: MLXArray
    switch alphaMode {
    case "mass":
        let massOverTheta = mass / thetaArr
        let powered = MLX.pow(massOverTheta, nFloat)
        alpha = MLX.clip(powered, min: MLXArray(0.0), max: MLXArray(1.0))
    case "per_channel":
        let powered = MLX.pow(A / thetaArr, nFloat)
        alpha = MLX.clip(powered, min: MLXArray(0.0), max: MLXArray(1.0))
    default:
        fatalError("implementation.alpha_mode must be one of: mass, per_channel.")
    }
    let alphaExpanded = alpha.expandedDimensions(axis: 3)

    let oneMinusAlpha = MLXArray(1.0) - alphaExpanded
    let term1 = nablaU * oneMinusAlpha
    let term2 = nablaA * alphaExpanded
    var F = term1 - term2
    if flowClip == "always" {
        F = clipFlow(F, dd: dd, sigma: sigma)
    }
    return (F, growthField)
}

public struct FlowGrowthVizFields {
    public let width: Int
    public let height: Int
    // Row-major per cell. flow has 2 components ordered [dy, dx] (matching the
    // step's flow axis); growth is a signed scalar.
    public let flow: [Float]
    public let growth: [Float]
}

// Reduce the per-channel flow/growth to a single representative field per cell,
// mass-weighted so the vectors track where the substance actually is. Returns
// CPU arrays ready to upload as textures.
public func flowGrowthVizFields(
    state A: MLXArray,
    sampleIndex: Int,
    kernels: CompiledKernels,
    config: BatchedConfig,
    wallPotential: MLXArray?
) -> FlowGrowthVizFields {
    let (F, growthField) = computeFlowAndGrowth(
        A,
        fK: kernels.fK, m: kernels.m, s: kernels.s, h: kernels.h,
        c0Idxs: kernels.c0Idxs, c1Mask: kernels.c1Mask,
        thetaA: config.thetaA, n: config.n,
        gradientBoundary: config.implementation.gradientBoundary,
        alphaMode: config.implementation.alphaMode,
        flowClip: config.implementation.flowClip,
        growthProfile: config.implementation.growthProfile,
        chemChannel: config.chemChannel, chemIncludeInMass: config.chemIncludeInMass,
        dd: config.dd, sigma: config.sigma, wallPotential: wallPotential
    )

    let sampleA = A[sampleIndex]                              // [h, w, c]
    let massPerCell = sampleA.sum(axis: -1)                   // [h, w]
    let denom = massPerCell + MLXArray(Float(1e-5))
    let weight = sampleA.expandedDimensions(axis: 2)          // [h, w, 1, c]
    // F axis 3 is [dy, dx]; reduce over channels weighted by mass.
    let flowWeighted = (F[sampleIndex] * weight).sum(axis: -1) / denom.expandedDimensions(axis: -1)
    let growthWeighted = (growthField[sampleIndex] * sampleA).sum(axis: -1) / denom

    eval(flowWeighted, growthWeighted)
    return FlowGrowthVizFields(
        width: config.sx,
        height: config.sy,
        flow: flowWeighted.asArray(Float.self),
        growth: growthWeighted.asArray(Float.self)
    )
}

private func reintegrationBatched(
    _ X: MLXArray,
    F: MLXArray,
    posGrid: MLXArray,
    dt: Float,
    dd: Int,
    sigma: Float,
    useTorus: Bool,
    sx: Int,
    sy: Int
) -> MLXArray {
    let ma = Float(dd) - sigma
    let clipMax = min(1.0, 2.0 * sigma)
    let areaScale = 1.0 / (4.0 * sigma * sigma)

    var out = MLX.zeros(like: X)
    let dtArr = MLXArray(dt)
    let maArr = MLXArray(ma)
    let negMaArr = MLXArray(-ma)
    let sigmaArr = MLXArray(sigma)
    let clipMaxArr = MLXArray(clipMax)
    let zeroArr = MLXArray(Float(0.0))
    let halfArr = MLXArray(Float(0.5))
    let minArr = MLXArray([Float(sigma), Float(sigma)]).reshaped([1, 1, 1, 2, 1])
    let maxArr = MLXArray([Float(sy) - sigma, Float(sx) - sigma]).reshaped([1, 1, 1, 2, 1])

    for dx in -dd...dd {
        for dy in -dd...dd {
            let Xr = rollMultiAxis(X, shifts: [dx, dy], axes: [1, 2])
            let pgr = rollMultiAxis(posGrid, shifts: [dx, dy], axes: [1, 2])
            let Fr = rollMultiAxis(F, shifts: [dx, dy], axes: [1, 2])

            let dtF = dtArr * Fr
            let clipped = MLX.clip(dtF, min: negMaArr, max: maArr)
            var mur = pgr + clipped
            if !useTorus {
                mur = MLX.clip(mur, min: minArr, max: maxArr)
            }

            var dMin = MLX.abs(posGrid - mur)

            if useTorus {
                for ix in [-sx, 0, sx] {
                    for iy in [-sy, 0, sy] {
                        if ix == 0 && iy == 0 { continue }
                        let shiftArr = MLXArray([Float(iy), Float(ix)]).reshaped([1, 1, 1, 2, 1])
                        let murShifted = mur + shiftArr
                        let dCandidate = MLX.abs(posGrid - murShifted)
                        dMin = MLX.minimum(dMin, dCandidate)
                    }
                }
            }

            let sz1 = halfArr - dMin
            let sz2 = sz1 + sigmaArr
            let sz = MLX.clip(sz2, min: zeroArr, max: clipMaxArr)

            let szY = sz[0..., 0..., 0..., 0, 0...]
            let szX = sz[0..., 0..., 0..., 1, 0...]
            let area = szY * szX

            let contribution = Xr * area
            out = out + contribution
        }
    }

    let areaScaleArr = MLXArray(areaScale)
    return out * areaScaleArr
}

public func leniaStepBatched(
    _ A: MLXArray,
    fK: MLXArray,
    m: MLXArray,
    s: MLXArray,
    h: MLXArray,
    c0Idxs: MLXArray,
    c1Mask: MLXArray,
    posGrid: MLXArray,
    dt: Float,
    dd: Int,
    sigma: Float,
    n: Int,
    thetaA: Float,
    gradientBoundary: String,
    alphaMode: String,
    flowClip: String,
    growthProfile: String = "gaussian",
    useTorus: Bool,
    chemChannel: Int?,
    chemIncludeInMass: Bool,
    sx: Int,
    sy: Int,
    wallPotential: MLXArray? = nil
) -> MLXArray {
    let F = computeFlow(
        A,
        fK: fK,
        m: m,
        s: s,
        h: h,
        c0Idxs: c0Idxs,
        c1Mask: c1Mask,
        thetaA: thetaA,
        n: n,
        gradientBoundary: gradientBoundary,
        alphaMode: alphaMode,
        flowClip: flowClip,
        growthProfile: growthProfile,
        chemChannel: chemChannel,
        chemIncludeInMass: chemIncludeInMass,
        dd: dd,
        sigma: sigma,
        wallPotential: wallPotential
    )
    return reintegrationBatched(A, F: F, posGrid: posGrid,
                                dt: dt, dd: dd, sigma: sigma, useTorus: useTorus, sx: sx, sy: sy)
}

public func additiveLeniaStepBatched(
    _ A: MLXArray,
    fK: MLXArray,
    m: MLXArray,
    s: MLXArray,
    h: MLXArray,
    c0Idxs: MLXArray,
    c1Mask: MLXArray,
    dt: Float,
    growthProfile: String = "gaussian",
    wallPotential: MLXArray? = nil
) -> MLXArray {
    let fA = MLXFFT.fft2(A, axes: [1, 2])
    let fAK = fA.take(c0Idxs, axis: 3)
    let UK = MLXFFT.ifft2(fAK * fK, axes: [1, 2]).realPart()
    let GK = growth(UK, m: m, s: s, h: h, profile: growthProfile)
    var G = MLX.matmul(GK, c1Mask.T)
    if let wallPotential {
        G = G + wallPotential
    }
    return MLX.clip(A + MLXArray(dt) * G, min: MLXArray(0.0), max: MLXArray(1.0))
}

public final class FlowLeniaBatched: @unchecked Sendable {
    public let config: BatchedConfig
    public var kernels: CompiledKernels
    public let posGrid: MLXArray
    public var wallPotential: MLXArray?
    private let useTorus: Bool

    // Compiled functions (split compilation like Python version)
    private let flowFn: ([MLXArray]) -> [MLXArray]
    private let reintFn: (MLXArray, MLXArray, MLXArray) -> MLXArray
    private var additiveLastShift: [(row: Int, col: Int)] = []

    public init(config: BatchedConfig, kernels: CompiledKernels, wallPotential: MLXArray? = nil) {
        validateFlowLeniaConfig(config)
        self.config = config
        self.kernels = kernels
        self.wallPotential = wallPotential
        self.useTorus = config.border == "torus"

        let coordsX = MLXArray(Array(0..<config.sx).map { Float($0) })
        let coordsY = MLXArray(Array(0..<config.sy).map { Float($0) })
        let (X, Y) = meshgrid(coordsX, coordsY)
        let halfArr = MLXArray(Float(0.5))
        var pos = MLX.stacked([Y, X], axis: -1) + halfArr
        pos = pos.expandedDimensions(axis: 0)
        self.posGrid = pos.expandedDimensions(axis: -1)

        // Split compilation: MLX compiler has issues combining FFT operations
        // with nested loops in a single compiled function. We compile them
        // separately for better compatibility.

        // Capture config constants in closures so compiler sees static loop bounds
        let thetaA = config.thetaA
        let n = config.n
        let dt = config.dt
        let dd = config.dd
        let sigma = config.sigma
        let sx = config.sx
        let sy = config.sy
        let useTorus = self.useTorus
        let gradientBoundary = config.implementation.gradientBoundary
        let alphaMode = config.implementation.alphaMode
        let flowClip = config.implementation.flowClip
        let growthProfile = config.implementation.growthProfile
        let chemChannel = config.chemChannel
        let chemIncludeInMass = config.chemIncludeInMass

        if config.implementation.mode == "qd24_additive_v1" {
            self.flowFn = compile { (inputs: [MLXArray]) -> [MLXArray] in
                let A = inputs[0]
                let fK = inputs[1]
                let m = inputs[2]
                let s = inputs[3]
                let h = inputs[4]
                let c0Idxs = inputs[5]
                let c1Mask = inputs[6]
                return [
                    additiveLeniaStepBatched(
                        A,
                        fK: fK,
                        m: m,
                        s: s,
                        h: h,
                        c0Idxs: c0Idxs,
                        c1Mask: c1Mask,
                        dt: dt,
                        growthProfile: growthProfile,
                        wallPotential: wallPotential
                    )
                ]
            }
            self.reintFn = { nextA, _, _ in nextA }
            return
        }

        // 1. Compile flow computation (FFT, growth, sobel)
        // Uses array-based compile for 7 inputs: [A, fK, m, s, h, c0Idxs, c1Mask]
        if let wallPotential {
            self.flowFn = compile { (inputs: [MLXArray]) -> [MLXArray] in
                let A = inputs[0]
                let fK = inputs[1]
                let m = inputs[2]
                let s = inputs[3]
                let h = inputs[4]
                let c0Idxs = inputs[5]
                let c1Mask = inputs[6]
                let result = computeFlow(
                    A,
                    fK: fK,
                    m: m,
                    s: s,
                    h: h,
                    c0Idxs: c0Idxs,
                    c1Mask: c1Mask,
                    thetaA: thetaA,
                    n: n,
                    gradientBoundary: gradientBoundary,
                    alphaMode: alphaMode,
                    flowClip: flowClip,
                    growthProfile: growthProfile,
                    chemChannel: chemChannel,
                    chemIncludeInMass: chemIncludeInMass,
                    dd: dd,
                    sigma: sigma,
                    wallPotential: wallPotential
                )
                return [result]
            }
        } else {
            self.flowFn = compile { (inputs: [MLXArray]) -> [MLXArray] in
                let A = inputs[0]
                let fK = inputs[1]
                let m = inputs[2]
                let s = inputs[3]
                let h = inputs[4]
                let c0Idxs = inputs[5]
                let c1Mask = inputs[6]
                let result = computeFlow(
                    A,
                    fK: fK,
                    m: m,
                    s: s,
                    h: h,
                    c0Idxs: c0Idxs,
                    c1Mask: c1Mask,
                    thetaA: thetaA,
                    n: n,
                    gradientBoundary: gradientBoundary,
                    alphaMode: alphaMode,
                    flowClip: flowClip,
                    growthProfile: growthProfile,
                    chemChannel: chemChannel,
                    chemIncludeInMass: chemIncludeInMass,
                    dd: dd,
                    sigma: sigma
                )
                return [result]
            }
        }

        // 2. Compile reintegration (nested loops)
        // Uses 3-argument compile overload
        self.reintFn = compile { (A: MLXArray, F: MLXArray, posGrid: MLXArray) -> MLXArray in
            reintegrationBatched(A, F: F, posGrid: posGrid,
                                 dt: dt, dd: dd, sigma: sigma, useTorus: useTorus, sx: sx, sy: sy)
        }
    }

    public func step(_ ABatch: MLXArray) -> MLXArray {
        if config.implementation.mode == "qd24_additive_v1" {
            let centered = applyAdditiveLastShift(ABatch)
            let flowInputs = [centered, kernels.fK, kernels.m, kernels.s,
                              kernels.h, kernels.c0Idxs, kernels.c1Mask]
            let next = flowFn(flowInputs)[0]
            updateAdditiveLastShift(from: next)
            return next
        }

        // Run compiled flow computation
        let flowInputs = [ABatch, kernels.fK, kernels.m, kernels.s,
                          kernels.h, kernels.c0Idxs, kernels.c1Mask]
        let F = flowFn(flowInputs)[0]

        // Run compiled reintegration
        return reintFn(ABatch, F, posGrid)
    }

    public func stepUncompiled(_ ABatch: MLXArray) -> MLXArray {
        if config.implementation.mode == "qd24_additive_v1" {
            let centered = applyAdditiveLastShift(ABatch)
            let next = additiveLeniaStepBatched(
                centered,
                fK: kernels.fK,
                m: kernels.m,
                s: kernels.s,
                h: kernels.h,
                c0Idxs: kernels.c0Idxs,
                c1Mask: kernels.c1Mask,
                dt: config.dt,
                growthProfile: config.implementation.growthProfile,
                wallPotential: wallPotential
            )
            updateAdditiveLastShift(from: next)
            return next
        }
        return leniaStepBatched(
            ABatch,
            fK: kernels.fK,
            m: kernels.m,
            s: kernels.s,
            h: kernels.h,
            c0Idxs: kernels.c0Idxs,
            c1Mask: kernels.c1Mask,
            posGrid: posGrid,
            dt: config.dt,
            dd: config.dd,
            sigma: config.sigma,
            n: config.n,
            thetaA: config.thetaA,
            gradientBoundary: config.implementation.gradientBoundary,
            alphaMode: config.implementation.alphaMode,
            flowClip: config.implementation.flowClip,
            growthProfile: config.implementation.growthProfile,
            useTorus: useTorus,
            chemChannel: config.chemChannel,
            chemIncludeInMass: config.chemIncludeInMass,
            sx: config.sx,
            sy: config.sy,
            wallPotential: wallPotential
        )
    }

    private func applyAdditiveLastShift(_ ABatch: MLXArray) -> MLXArray {
        let batchSize = ABatch.shape[0]
        if additiveLastShift.count != batchSize {
            additiveLastShift = Array(repeating: (row: 0, col: 0), count: batchSize)
        }
        guard additiveLastShift.contains(where: { $0.row != 0 || $0.col != 0 }) else {
            return ABatch
        }
        let rolled = (0..<batchSize).map { index in
            let shift = additiveLastShift[index]
            return rollMultiAxis(
                ABatch[index, 0..., 0..., 0...],
                shifts: [-shift.row, -shift.col],
                axes: [0, 1]
            )
        }
        return MLX.stacked(rolled, axis: 0)
    }

    private func updateAdditiveLastShift(from state: MLXArray) {
        let batchSize = state.shape[0]
        let massMap = state.sum(axis: -1)
        eval(massMap)
        let flat = massMap.asArray(Float.self)
        let sampleSize = config.sx * config.sy
        let midRow = Float(config.sx) / 2.0
        let midCol = Float(config.sy) / 2.0
        var shifts: [(row: Int, col: Int)] = []
        shifts.reserveCapacity(batchSize)
        for sampleIndex in 0..<batchSize {
            let base = sampleIndex * sampleSize
            var total: Float = 0
            var rowWeighted: Float = 0
            var colWeighted: Float = 0
            for row in 0..<config.sx {
                for col in 0..<config.sy {
                    let mass = flat[base + row * config.sy + col]
                    total += mass
                    rowWeighted += mass * Float(row)
                    colWeighted += mass * Float(col)
                }
            }
            guard total > 1e-8 else {
                shifts.append((row: 0, col: 0))
                continue
            }
            shifts.append((
                row: Int(rowWeighted / total - midRow),
                col: Int(colWeighted / total - midCol)
            ))
        }
        additiveLastShift = shifts
    }
}

// Single-sample (non-batched) step for Evolution Strategy
// Runs without batch dimension for simpler CoM tracking
public func leniaStepSingle(
    _ A: MLXArray,
    fK: MLXArray,
    m: MLXArray,
    s: MLXArray,
    h: MLXArray,
    c0Idxs: MLXArray,
    c1Mask: MLXArray,
    posGrid: MLXArray,
    dt: Float,
    dd: Int,
    sigma: Float,
    n: Int,
    thetaA: Float,
    gradientBoundary: String,
    alphaMode: String,
    flowClip: String,
    growthProfile: String = "gaussian",
    useTorus: Bool,
    chemChannel: Int?,
    chemIncludeInMass: Bool,
    sx: Int,
    sy: Int,
    implementationMode: String = "flowlenia_2022_paper_equations",
    wallPotential: MLXArray? = nil
) -> MLXArray {
    // Add batch dimension, run step, remove batch dimension
    let ABatched = A.expandedDimensions(axis: 0)
    if implementationMode == "qd24_additive_v1" {
        let result = additiveLeniaStepBatched(
            ABatched,
            fK: fK,
            m: m,
            s: s,
            h: h,
            c0Idxs: c0Idxs,
            c1Mask: c1Mask,
            dt: dt,
            growthProfile: growthProfile,
            wallPotential: wallPotential
        )
        return result.squeezed(axis: 0)
    }
    let result = leniaStepBatched(
        ABatched,
        fK: fK,
        m: m,
        s: s,
        h: h,
        c0Idxs: c0Idxs,
        c1Mask: c1Mask,
        posGrid: posGrid,
        dt: dt,
        dd: dd,
        sigma: sigma,
        n: n,
        thetaA: thetaA,
        gradientBoundary: gradientBoundary,
        alphaMode: alphaMode,
        flowClip: flowClip,
        growthProfile: growthProfile,
        useTorus: useTorus,
        chemChannel: chemChannel,
        chemIncludeInMass: chemIncludeInMass,
        sx: sx,
        sy: sy,
        wallPotential: wallPotential
    )
    return result.squeezed(axis: 0)
}

// Simple simulation runner for ES (creates fresh kernels per evaluation)
public final class FlowLeniaSimple {
    public let config: BatchedConfig
    public let c0: [Int]
    public let c1: [[Int]]
    public let posGrid: MLXArray

    public init(config: BatchedConfig, c0: [Int], c1: [[Int]]) {
        validateFlowLeniaConfig(config)
        self.config = config
        self.c0 = c0
        self.c1 = c1

        let coordsX = MLXArray(Array(0..<config.sx).map { Float($0) })
        let coordsY = MLXArray(Array(0..<config.sy).map { Float($0) })
        let (X, Y) = meshgrid(coordsX, coordsY)
        let halfArr = MLXArray(Float(0.5))
        var pos = MLX.stacked([Y, X], axis: -1) + halfArr
        pos = pos.expandedDimensions(axis: 0)
        self.posGrid = pos.expandedDimensions(axis: -1)
    }

    public func step(_ A: MLXArray, kernels: CompiledKernels, wallPotential: MLXArray? = nil) -> MLXArray {
        let ABatched = A.expandedDimensions(axis: 0)
        if config.implementation.mode == "qd24_additive_v1" {
            let result = additiveLeniaStepBatched(
                ABatched,
                fK: kernels.fK,
                m: kernels.m,
                s: kernels.s,
                h: kernels.h,
                c0Idxs: kernels.c0Idxs,
                c1Mask: kernels.c1Mask,
                dt: config.dt,
                growthProfile: config.implementation.growthProfile,
                wallPotential: wallPotential
            )
            return result.squeezed(axis: 0)
        }
        let result = leniaStepBatched(
            ABatched,
            fK: kernels.fK,
            m: kernels.m,
            s: kernels.s,
            h: kernels.h,
            c0Idxs: kernels.c0Idxs,
            c1Mask: kernels.c1Mask,
            posGrid: posGrid,
            dt: config.dt,
            dd: config.dd,
            sigma: config.sigma,
            n: config.n,
            thetaA: config.thetaA,
            gradientBoundary: config.implementation.gradientBoundary,
            alphaMode: config.implementation.alphaMode,
            flowClip: config.implementation.flowClip,
            growthProfile: config.implementation.growthProfile,
            useTorus: config.border == "torus",
            chemChannel: config.chemChannel,
            chemIncludeInMass: config.chemIncludeInMass,
            sx: config.sx,
            sy: config.sy,
            wallPotential: wallPotential
        )
        return result.squeezed(axis: 0)
    }
}

// Parameter Advection for Embedded Lenia
// Moves parameters (P) along with mass (A) based on the flow field

func computeFlowWithParams(
    _ A: MLXArray,
    _ P: MLXArray,
    fK: MLXArray,
    m: MLXArray,
    s: MLXArray,
    c0Idxs: MLXArray,
    c1Mask: MLXArray,
    thetaA: Float,
    n: Int,
    gradientBoundary: String,
    alphaMode: String,
    flowClip: String,
    chemChannel: Int?,
    chemIncludeInMass: Bool,
    dd: Int,
    sigma: Float,
    wallPotential: MLXArray? = nil
) -> MLXArray {
    // FFT convolution
    let fA = MLXFFT.fft2(A, axes: [1, 2])
    let fAK = fA.take(c0Idxs, axis: 3)
    let fAKfK = fAK * fK
    let UK = MLXFFT.ifft2(fAKfK, axes: [1, 2]).realPart()

    // Growth uses either a legacy local h field with global m/s, or a richer
    // local [m, s, h] field packed as 3*K channels for ecology experiments.
    let parameterWidth = P.shape[3]
    let kernelCount = m.shape.last ?? 0
    let localM: MLXArray
    let localS: MLXArray
    let localH: MLXArray
    if parameterWidth == kernelCount {
        localM = reshapeKernelParams(m)
        localS = reshapeKernelParams(s)
        localH = P
    } else if parameterWidth == kernelCount * 3 {
        localM = MLX.clip(P[0..., 0..., 0..., 0..<kernelCount], min: MLXArray(0.0), max: MLXArray(1.0))
        localS = MLX.maximum(P[0..., 0..., 0..., kernelCount..<(2 * kernelCount)], MLXArray(Float(1e-3)))
        localH = P[0..., 0..., 0..., (2 * kernelCount)..<(3 * kernelCount)]
    } else {
        fatalError("Embedded parameter field width must be nbK or 3*nbK.")
    }
    let mB = localM
    let sB = localS
    let diff = (UK - mB) / sB
    let exponent = -(diff * diff) / MLXArray(2.0)
    let bell = MLX.exp(exponent)
    let bellScaled = bell * MLXArray(2.0)
    let bellShifted = bellScaled - MLXArray(1.0)

    let G = bellShifted * localH
    var U = MLX.matmul(G, c1Mask.T)

    if let wp = wallPotential {
        U = U + wp
    }

    let nablaU = sobelBatched(U, gradientBoundary: gradientBoundary)
    let mass = massField(A, chemChannel: chemChannel, includeInMass: chemIncludeInMass)
    let nablaA = sobelBatched(mass, gradientBoundary: gradientBoundary)

    let thetaArr = MLXArray(thetaA)
    let nFloat = Float(n)
    let alpha: MLXArray
    switch alphaMode {
    case "mass":
        let massOverTheta = mass / thetaArr
        let powered = MLX.pow(massOverTheta, nFloat)
        alpha = MLX.clip(powered, min: MLXArray(0.0), max: MLXArray(1.0))
    case "per_channel":
        let powered = MLX.pow(A / thetaArr, nFloat)
        alpha = MLX.clip(powered, min: MLXArray(0.0), max: MLXArray(1.0))
    default:
        fatalError("implementation.alpha_mode must be one of: mass, per_channel.")
    }
    let alphaExpanded = alpha.expandedDimensions(axis: 3)

    let oneMinusAlpha = MLXArray(1.0) - alphaExpanded
    var F = nablaU * oneMinusAlpha - nablaA * alphaExpanded
    if flowClip == "always" || flowClip == "params_only" {
        F = clipFlow(F, dd: dd, sigma: sigma)
    }
    return F
}

private func reintegrationParamsBatched(
    _ A: MLXArray,
    _ P: MLXArray,
    F: MLXArray,
    posGrid: MLXArray,
    dt: Float,
    dd: Int,
    sigma: Float,
    mixMode: String,
    mixSeed: Int?,
    mixStep: Int,
    useTorus: Bool,
    sx: Int,
    sy: Int,
    flowLenia2022ColabCompat: Bool
) -> (MLXArray, MLXArray) {
    let ma = Float(dd) - sigma
    let clipMax = min(1.0, 2.0 * sigma)
    let areaScale = 1.0 / (4.0 * sigma * sigma)
    let usesStreamingAverage = mixMode == "avg"
    let usesStreamingColabSoftmax = mixMode == "softmax" && flowLenia2022ColabCompat
    let usesStreamingArgmax = mixMode == "argmax"

    var accumulatedA = MLX.zeros(like: A)
    var accumulatedPWeights = (usesStreamingAverage || usesStreamingColabSoftmax) ? MLX.zeros([A.shape[0], sx, sy, 1]) : nil
    var accumulatedP = (usesStreamingAverage || usesStreamingColabSoftmax) ? MLX.zeros(like: P) : nil
    var bestArgmaxLogits = usesStreamingArgmax ? MLX.full([A.shape[0], sx, sy], values: MLXArray(Float(-1e30))) : nil
    var argmaxParams = usesStreamingArgmax ? MLX.zeros(like: P) : nil
    var logitList: [MLXArray] = []
    var nPList: [MLXArray] = []
    var velocityLogitList: [MLXArray]? = mixMode == "energy" ? [] : nil
    let neighborhoodCount = (2 * dd + 1) * (2 * dd + 1)
    logitList.reserveCapacity(neighborhoodCount)
    nPList.reserveCapacity(neighborhoodCount)
    velocityLogitList?.reserveCapacity(neighborhoodCount)

    let dtArr = MLXArray(dt)
    let maArr = MLXArray(ma)
    let negMaArr = MLXArray(-ma)
    let sigmaArr = MLXArray(sigma)
    let clipMaxArr = MLXArray(clipMax)
    let zeroArr = MLXArray(Float(0.0))
    let oneArr = MLXArray(Float(1.0))
    let halfArr = MLXArray(Float(0.5))
    let eps = MLXArray(Float(1e-10))
    let minArr = MLXArray([Float(sigma), Float(sigma)]).reshaped([1, 1, 1, 2, 1])
    let maxArr = MLXArray([Float(sy) - sigma, Float(sx) - sigma]).reshaped([1, 1, 1, 2, 1])

    for dx in -dd...dd {
        for dy in -dd...dd {
            let Ar = rollMultiAxis(A, shifts: [dx, dy], axes: [1, 2])
            let Pr = rollMultiAxis(P, shifts: [dx, dy], axes: [1, 2])
            let pgr = rollMultiAxis(posGrid, shifts: [dx, dy], axes: [1, 2])
            let Fr = rollMultiAxis(F, shifts: [dx, dy], axes: [1, 2])

            let dtF = dtArr * Fr
            let clipped = MLX.clip(dtF, min: negMaArr, max: maArr)
            var mur = pgr + clipped
            if !useTorus {
                mur = MLX.clip(mur, min: minArr, max: maxArr)
            }

            var dMin = MLX.abs(posGrid - mur)

            if useTorus {
                for ix in [-sx, 0, sx] {
                    for iy in [-sy, 0, sy] {
                        if ix == 0 && iy == 0 { continue }
                        let shiftArr = MLXArray([Float(iy), Float(ix)]).reshaped([1, 1, 1, 2, 1])
                        let murShifted = mur + shiftArr
                        let dCandidate = MLX.abs(posGrid - murShifted)
                        dMin = MLX.minimum(dMin, dCandidate)
                    }
                }
            }

            let sz1 = halfArr - dMin
            let sz2 = sz1 + sigmaArr
            let sz = MLX.clip(sz2, min: zeroArr, max: clipMaxArr)

            let szY = sz[0..., 0..., 0..., 0, 0...]
            let szX = sz[0..., 0..., 0..., 1, 0...]
            let area = szY * szX

            let nX = Ar * area
            accumulatedA = accumulatedA + nX
            let massWeights = nX.sum(axis: -1, keepDims: true)
            if usesStreamingAverage {
                accumulatedPWeights = accumulatedPWeights! + massWeights
                accumulatedP = accumulatedP! + Pr * massWeights
            } else if usesStreamingColabSoftmax {
                let softmaxWeights = MLX.exp(massWeights) - MLXArray(1.0)
                accumulatedPWeights = accumulatedPWeights! + softmaxWeights
                accumulatedP = accumulatedP! + Pr * softmaxWeights
            } else {
                let candidateLogit: MLXArray
                if velocityLogitList != nil {
                    let vSq = (Fr * Fr).sum(axis: 3)
                    candidateLogit = (nX * vSq).sum(axis: -1)
                } else {
                    candidateLogit = massWeights.squeezed(axis: -1)
                }
                if usesStreamingArgmax {
                    guard let currentBest = bestArgmaxLogits, let currentParams = argmaxParams else {
                        fatalError("argmax mixing requires best-logit state.")
                    }
                    let betterMask = MLX.greater(candidateLogit, currentBest).asType(.float32)
                    let keepMask = oneArr - betterMask
                    let betterMaskExpanded = betterMask.expandedDimensions(axis: -1)
                    let keepMaskExpanded = oneArr - betterMaskExpanded
                    bestArgmaxLogits = candidateLogit * betterMask + currentBest * keepMask
                    argmaxParams = Pr * betterMaskExpanded + currentParams * keepMaskExpanded
                } else {
                    nPList.append(Pr)
                    if velocityLogitList != nil {
                        velocityLogitList!.append(candidateLogit)
                    } else {
                        logitList.append(candidateLogit)
                    }
                }
            }
        }
    }

    let finalA = accumulatedA * MLXArray(areaScale)

    let finalP: MLXArray
    switch mixMode {
    case "avg":
        let denom = accumulatedPWeights! + eps
        finalP = accumulatedP! / denom
    case "softmax":
        if flowLenia2022ColabCompat {
            let denom = accumulatedPWeights! + eps
            finalP = accumulatedP! / denom
            break
        }
        let logitStack = MLX.stacked(logitList, axis: 0)
        let nPStack = MLX.stacked(nPList, axis: 0)
        let seed = mixSeed ?? 42
        var logits = logitStack
        logits = logits - logits.max(axis: 0, keepDims: true)
        let key = MLXRandom.key(UInt64(seed) + UInt64(mixStep))
        let choice = MLXRandom.categorical(logits, axis: 0, key: key)
        finalP = selectParamsFromNeighborhoodStack(nPStack, choice: choice)
    case "stoch":
        let logitStack = MLX.stacked(logitList, axis: 0)
        let nPStack = MLX.stacked(nPList, axis: 0)
        let seed = mixSeed ?? 42
        var logits = logitStack
        if flowLenia2022ColabCompat {
            logits = MLX.log(logits + eps)
        }
        logits = logits - logits.max(axis: 0, keepDims: true)
        let key = flowLenia2022ColabCompat ? MLXRandom.key(UInt64(seed)) : MLXRandom.key(UInt64(seed) + UInt64(mixStep))
        let choice = MLXRandom.categorical(logits, axis: 0, key: key)
        finalP = selectParamsFromNeighborhoodStack(nPStack, choice: choice)
    case "argmax":
        guard let argmaxParams else {
            fatalError("argmax mixing requires selected parameters.")
        }
        finalP = argmaxParams
    case "stoch_gene_wise":
        let logitStack = MLX.stacked(logitList, axis: 0)
        let nPStack = MLX.stacked(nPList, axis: 0)
        let seed = mixSeed ?? 42
        var logits = logitStack
        logits = logits - logits.max(axis: 0, keepDims: true)
        finalP = selectParamsGeneWiseFromNeighborhoodStack(
            nPStack,
            logits: logits,
            seed: seed,
            mixStep: mixStep
        )
    case "energy":
        let nPStack = MLX.stacked(nPList, axis: 0)
        let seed = mixSeed ?? 42
        var logits = MLX.stacked(velocityLogitList!, axis: 0)
        logits = logits - logits.max(axis: 0, keepDims: true)
        let key = MLXRandom.key(UInt64(seed) + UInt64(mixStep))
        let choice = MLXRandom.categorical(logits, axis: 0, key: key)
        finalP = selectParamsFromNeighborhoodStack(nPStack, choice: choice)
    default:
        fatalError("Unsupported parameter_embedding.mix: \(mixMode)")
    }

    return (finalA, finalP)
}

private func selectParamsFromNeighborhoodStack(_ paramStack: MLXArray, choice: MLXArray) -> MLXArray {
    let indices = choice.expandedDimensions(axis: 0).expandedDimensions(axis: -1)
    let targetShape = [1] + choice.shape + [paramStack.shape[4]]
    let expanded = MLX.broadcast(indices, to: targetShape)
    let selected = MLX.takeAlong(paramStack, expanded, axis: 0)
    return selected.squeezed(axis: 0)
}

private func selectParamsGeneWiseFromNeighborhoodStack(
    _ paramStack: MLXArray,
    logits: MLXArray,
    seed: Int,
    mixStep: Int
) -> MLXArray {
    let geneCount = paramStack.shape[4]
    var selectedGenes: [MLXArray] = []
    selectedGenes.reserveCapacity(geneCount)
    for geneIndex in 0..<geneCount {
        let key = MLXRandom.key(UInt64(seed) + UInt64(mixStep * geneCount + geneIndex))
        let choice = MLXRandom.categorical(logits, axis: 0, key: key)
        let geneStack = paramStack[0..., 0..., 0..., 0..., geneIndex]
        let indices = choice.expandedDimensions(axis: 0)
        let selectedGene = MLX.takeAlong(geneStack, indices, axis: 0).squeezed(axis: 0)
        selectedGenes.append(selectedGene)
    }
    return MLX.stacked(selectedGenes, axis: -1)
}

public func leniaStepParamsBatched(
    _ A: MLXArray,
    _ P: MLXArray,
    fK: MLXArray,
    m: MLXArray,
    s: MLXArray,
    c0Idxs: MLXArray,
    c1Mask: MLXArray,
    posGrid: MLXArray,
    dt: Float,
    dd: Int,
    sigma: Float,
    n: Int,
    thetaA: Float,
    gradientBoundary: String,
    alphaMode: String,
    flowClip: String,
    mixMode: String,
    mixSeed: Int?,
    mixStep: Int,
    useTorus: Bool,
    implementationMode: String,
    chemChannel: Int?,
    chemIncludeInMass: Bool,
    sx: Int,
    sy: Int,
    wallPotential: MLXArray? = nil
) -> (MLXArray, MLXArray) {
    let alphaTheta: Float
    let alphaN: Int
    if implementationMode == "flowlenia_2022_colab" {
        alphaTheta = 2.0
        alphaN = 2
    } else {
        alphaTheta = thetaA
        alphaN = n
    }
    let F = computeFlowWithParams(A, P, fK: fK, m: m, s: s,
                                   c0Idxs: c0Idxs, c1Mask: c1Mask,
                                   thetaA: alphaTheta, n: alphaN,
                                   gradientBoundary: gradientBoundary,
                                   alphaMode: alphaMode,
                                   flowClip: flowClip,
                                   chemChannel: chemChannel,
                                   chemIncludeInMass: chemIncludeInMass,
                                   dd: dd, sigma: sigma,
                                   wallPotential: wallPotential)
    return reintegrationParamsBatched(A, P, F: F, posGrid: posGrid,
                                       dt: dt, dd: dd, sigma: sigma,
                                       mixMode: mixMode, mixSeed: mixSeed, mixStep: mixStep,
                                       useTorus: useTorus, sx: sx, sy: sy,
                                       flowLenia2022ColabCompat: implementationMode == "flowlenia_2022_colab")
}

// FlowLeniaParamsBatched: Handles parameter embedding (P moves with A)
public final class FlowLeniaParamsBatched: @unchecked Sendable {
    public let config: BatchedConfig
    public let kernels: CompiledKernels
    public let posGrid: MLXArray
    public let wallPotential: MLXArray?
    private let mixMode: String
    private let mixSeed: Int?
    private let useTorus: Bool
    private let implementationMode: String
    private var mixStep: Int = 0

    public init(config: BatchedConfig, kernels: CompiledKernels, mixMode: String, mixSeed: Int?, wallPotential: MLXArray? = nil) {
        validateFlowLeniaConfig(config)
        let stochasticModes: Set<String> = ["stoch", "softmax", "stoch_gene_wise", "energy"]
        if stochasticModes.contains(mixMode),
           config.implementation.mode != "flowlenia_2022_colab",
           mixSeed == nil {
            fatalError("parameter_embedding.mix_seed is required for \(mixMode) mixing when implementation.mode != \"flowlenia_2022_colab\".")
        }
        if stochasticModes.contains(mixMode),
           config.implementation.mode == "flowlenia_2022_colab",
           mixSeed != nil {
            fatalError("parameter_embedding.mix_seed must be omitted when implementation.mode == \"flowlenia_2022_colab\".")
        }
        if config.implementation.mode == "flowlenia_2022_colab" {
            let thetaDelta = abs(config.thetaA - 2.0)
            if config.n != 2 || thetaDelta > 1e-6 {
                fatalError("implementation.mode=flowlenia_2022_colab with parameter embedding uses fixed alpha parameters (n=2, theta_A=2.0). Set flow.n=2 and flow.theta_A=2.0 or use implementation.mode=custom.")
            }
        }
        self.config = config
        self.kernels = kernels
        self.mixMode = mixMode
        self.mixSeed = mixSeed
        self.wallPotential = wallPotential
        self.useTorus = config.border == "torus"
        self.implementationMode = config.implementation.mode

        let coordsX = MLXArray(Array(0..<config.sx).map { Float($0) })
        let coordsY = MLXArray(Array(0..<config.sy).map { Float($0) })
        let (X, Y) = meshgrid(coordsX, coordsY)
        let halfArr = MLXArray(Float(0.5))
        var pos = MLX.stacked([Y, X], axis: -1) + halfArr
        pos = pos.expandedDimensions(axis: 0)
        self.posGrid = pos.expandedDimensions(axis: -1)
    }

    public func step(_ ABatch: MLXArray, _ PBatch: MLXArray) -> (MLXArray, MLXArray) {
        let result = leniaStepParamsBatched(
            ABatch,
            PBatch,
            fK: kernels.fK,
            m: kernels.m,
            s: kernels.s,
            c0Idxs: kernels.c0Idxs,
            c1Mask: kernels.c1Mask,
            posGrid: posGrid,
            dt: config.dt,
            dd: config.dd,
            sigma: config.sigma,
            n: config.n,
            thetaA: config.thetaA,
            gradientBoundary: config.implementation.gradientBoundary,
            alphaMode: config.implementation.alphaMode,
            flowClip: config.implementation.flowClip,
            mixMode: mixMode,
            mixSeed: mixSeed,
            mixStep: mixStep,
            useTorus: useTorus,
            implementationMode: implementationMode,
            chemChannel: config.chemChannel,
            chemIncludeInMass: config.chemIncludeInMass,
            sx: config.sx,
            sy: config.sy,
            wallPotential: wallPotential
        )
        let stochasticModes: Set<String> = ["stoch", "softmax", "stoch_gene_wise", "energy"]
        if stochasticModes.contains(mixMode) && implementationMode != "flowlenia_2022_colab" {
            mixStep += 1
        }
        return result
    }
}
