import Foundation
import MLX

struct FlowLeniaMassSummary: Sendable {
    let totalMass: [Float]
    let sumSquares: [Float]
    let energy: [Float]
    let occupancyCount: [Float]
    let centerXIndex: [Float]
    let centerYIndex: [Float]
    let rawGyration: [Float]?
}

struct FlowLeniaParameterPatchBatch {
    let origins: [SIMD2<Int32>]
    let size: Int
    let deltas: [Float]
    let clip: [Float]?
}

struct FlowLeniaChannelField {
    let channelIndex: Int
    let field: MLXArray
}

struct FlowLeniaFoodState {
    let channelIndex: Int
    let field: MLXArray
    let decayRate: Float
    let digestRate: Float
}

struct FlowLeniaScalarPatchBatch {
    let origins: [SIMD2<Int32>]
    let size: Int
    let value: Float
}

struct FlowLeniaDissipationBatch {
    let removalOrigins: [SIMD2<Int32>]
    let insertionOrigins: [SIMD2<Int32>]
    let size: Int
    let insertedMass: [Float]
    let insertedParams: [Float]
}

/// A sensed-only field added to real mass before convolution. It never moves
/// real matter, never receives it, and carries no parameters.
public struct FlowLeniaPhantomSpec {
    public enum Source: String {
        case fixed = "static"
        case replay
    }

    public let source: Source
    /// When true the phantom also enters the matter map that sets alpha and the
    /// mass-gradient term; when false only the growth convolution senses it.
    public let pressure: Bool
    /// Float32 field with shape [sx, sy, channels], in the mass layout.
    public let field: [Float]

    public init(source: Source, pressure: Bool, field: [Float]) {
        self.source = source
        self.pressure = pressure
        self.field = field
    }
}

/// A resident batch of Flow Lenia fields stepped by a compiled backend. Shapes follow the
/// MLX layout: mass [batch, sx, sy, channels], params [batch, sx, sy, parameterCount].
protocol FlowLeniaFieldRunner: AnyObject {
    var batchCount: Int { get }
    var massObservationSynchronizationCount: Int { get }

    func setMatterWeights(_ weights: [Float]?)
    func updateKernels(_ kernels: CompiledKernels)
    func reset(
        mass: MLXArray,
        params: MLXArray,
        wallMask: MLXArray?,
        staticChannelFields: [FlowLeniaChannelField],
        food: FlowLeniaFoodState?,
        mixStep: Int
    )
    func step(count: Int)
    func step(count: Int, postStepParameterPatches: [Int: [FlowLeniaParameterPatchBatch]])
    func applyParameterPatch(origins: [SIMD2<Int32>], size: Int, deltas: [Float], clip: [Float]?)
    func applyZeroStatePatch(origins: [SIMD2<Int32>], size: Int)
    func observeMass(
        occupancyThreshold: Float,
        includeGyration: Bool,
        channelWeights: [Float]?,
        materializeMap: Bool
    ) -> (summary: FlowLeniaMassSummary, massMap: MLXArray?)
    func materializeMassMap(channelWeights: [Float]?) -> MLXArray
    func materializeMass() -> MLXArray
    func materializeParams() -> MLXArray
    func materializeState() -> (mass: MLXArray, params: MLXArray)
    func summarizeFoodMass() -> [Float]?
}

func makeFlowLeniaFieldRunner(
    backend: FlowLeniaComputeBackend,
    config: BatchedConfig,
    kernels: CompiledKernels,
    batchCount: Int,
    wallPotential: MLXArray?,
    matterWeights: [Float]?,
    reintegrateParams: Bool,
    parameterMix: String,
    mixSeed: Int?
) -> any FlowLeniaFieldRunner {
    switch backend {
    case .metalFull:
        #if canImport(Metal)
        return FlowLeniaMetalFullStateRunner(
            config: config,
            kernels: kernels,
            batchCount: batchCount,
            wallPotential: wallPotential,
            matterWeights: matterWeights,
            reintegrateParams: reintegrateParams,
            parameterMix: parameterMix,
            mixSeed: mixSeed
        )
        #else
        preconditionFailure("Backend metal-full requires Apple Metal; use backend cpu on this host.")
        #endif
    case .cpu:
        guard !reintegrateParams else {
            preconditionFailure("Backend cpu keeps parameter fields fixed; parameter_embedding.enabled needs metal-full.")
        }
        return FlowLeniaCPUStateRunner(
            config: config,
            kernels: kernels,
            batchCount: batchCount,
            wallPotential: wallPotential,
            matterWeights: matterWeights
        )
    case .mlx:
        preconditionFailure("Backend mlx steps MLX arrays and has no resident field runner.")
    }
}

/// Kernel and field layout rules shared by the compiled backends, so both read the same
/// CompiledKernels the same way.
enum FlowLeniaFieldLayout {
    static func parameterCount(for kernels: CompiledKernels) -> Int {
        guard kernels.c1Mask.shape.count == 2 else {
            preconditionFailure("Flow Lenia field runner kernels require c1Mask with shape [channels, nbK].")
        }
        return kernels.c1Mask.shape[1]
    }

    static func kernelBatchCount(for kernels: CompiledKernels) -> Int {
        if kernels.fK.shape.count == 4 {
            return kernels.fK.shape[0]
        }
        if kernels.m.shape.count == 2 {
            return kernels.m.shape[0]
        }
        return 1
    }

    static func expandedKernelScalars(
        from values: MLXArray,
        batchCount: Int,
        parameterCount: Int,
        label: String
    ) -> [Float] {
        switch values.shape.count {
        case 1:
            guard values.shape[0] == parameterCount else {
                preconditionFailure("Flow Lenia field runner \(label) values must match the kernel count.")
            }
            let row = values.asArray(Float.self)
            return Array(repeating: row, count: batchCount).flatMap { $0 }
        case 2:
            guard values.shape[1] == parameterCount else {
                preconditionFailure("Flow Lenia field runner \(label) values must match the kernel count.")
            }
            guard values.shape[0] == 1 || values.shape[0] == batchCount else {
                preconditionFailure("Flow Lenia field runner \(label) values must be shared across the batch or provided per batch element.")
            }
            let raw = values.asArray(Float.self)
            if values.shape[0] == batchCount {
                return raw
            }
            let row = Array(raw[0..<parameterCount])
            return Array(repeating: row, count: batchCount).flatMap { $0 }
        default:
            preconditionFailure("Flow Lenia field runner \(label) values must have rank 1 or 2.")
        }
    }

    static func expandedScalarField(
        from values: MLXArray,
        batchCount: Int,
        sx: Int,
        sy: Int,
        label: String
    ) -> [Float] {
        guard values.shape.count == 4 else {
            preconditionFailure("Flow Lenia field runner \(label) must have rank 4 with shape [batch, sx, sy, 1].")
        }
        guard values.shape[1] == sx, values.shape[2] == sy, values.shape[3] == 1 else {
            preconditionFailure("Flow Lenia field runner \(label) must have shape [batch, \(sx), \(sy), 1].")
        }
        guard values.shape[0] == 1 || values.shape[0] == batchCount else {
            preconditionFailure("Flow Lenia field runner \(label) must be shared across the batch or provided per batch element.")
        }
        let contiguous = values.contiguous()
        let raw = contiguous.asArray(Float.self)
        if values.shape[0] == batchCount {
            return raw
        }
        return Array(repeating: raw, count: batchCount).flatMap { $0 }
    }

    static func usesLocalTorusDistance(sx: Int, sy: Int, dd: Int, maxAdvection: Float, useTorus: Bool) -> Bool {
        useTorus && maxAdvection >= 0 && Float(min(sx, sy)) * 0.5 > Float(dd) + maxAdvection
    }

}
