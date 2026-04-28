import MLX
import MLXFFT

public struct LeniaDiagnosticsFrame: @unchecked Sendable {
    public let field: MLXArray
    public let neighborSum: MLXArray
    public let growthField: MLXArray
    public let kernel: MLXArray
    public let kernelCount: Int

    public init(field: MLXArray, neighborSum: MLXArray, growthField: MLXArray, kernel: MLXArray, kernelCount: Int) {
        self.field = field
        self.neighborSum = neighborSum
        self.growthField = growthField
        self.kernel = kernel
        self.kernelCount = kernelCount
    }
}

public func computeLeniaDiagnostics(
    state: MLXArray,
    params: ResolvedParams,
    config: BatchedConfig,
    kernels: CompiledKernels
) -> LeniaDiagnosticsFrame {
    let batchedState: MLXArray
    switch state.shape.count {
    case 3:
        batchedState = state.expandedDimensions(axis: 0)
    case 4:
        batchedState = state
    default:
        fatalError("Lenia diagnostics expect a 3D or 4D state tensor.")
    }

    let fA = MLXFFT.fft2(batchedState, axes: [1, 2])
    let fAK = fA.take(kernels.c0Idxs, axis: 3)
    let fAKfK = fAK * kernels.fK
    let uk = MLXFFT.ifft2(fAKfK, axes: [1, 2]).realPart()
    let growthByKernel = growth(uk, m: kernels.m, s: kernels.s, h: kernels.h)
    let aggregateGrowth = MLX.matmul(growthByKernel, kernels.c1Mask.T)

    let field = batchedState[0, 0..., 0..., 0]
    let neighborSlice = uk[0, 0..., 0..., 0...]
    let neighborSum: MLXArray
    if config.nbK == 1 {
        neighborSum = neighborSlice.squeezed(axis: 2)
    } else {
        neighborSum = neighborSlice.sum(axis: 2) / MLXArray(Float(config.nbK))
    }

    let kernelStack = normalizedSpatialKernelStack(params: params, config: config)
    let kernel: MLXArray
    if config.nbK == 1 {
        kernel = kernelStack[0..., 0..., 0]
    } else {
        kernel = kernelStack.sum(axis: 2) / MLXArray(Float(config.nbK))
    }

    return LeniaDiagnosticsFrame(
        field: field,
        neighborSum: neighborSum,
        growthField: aggregateGrowth[0, 0..., 0..., 0],
        kernel: kernel,
        kernelCount: config.nbK
    )
}
