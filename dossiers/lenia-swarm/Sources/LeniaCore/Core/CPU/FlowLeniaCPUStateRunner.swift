import CFlowLeniaCPU
import Foundation
import MLX

/// Steps the metal-full equations on CPU threads in fp32. It covers the torus search and
/// replay runtime: fixed kernel-gain parameter fields, per-body kernels, matter weights, an
/// environment potential, and parameter and zero-state patches.
final class FlowLeniaCPUStateRunner: FlowLeniaFieldRunner {
    let config: BatchedConfig
    let batchCount: Int
    let channelCount: Int
    let kernelCount: Int
    private let kernelBatchCount: Int
    private let engine: OpaquePointer
    private(set) var massObservationSynchronizationCount = 0

    init(
        config: BatchedConfig,
        kernels: CompiledKernels,
        batchCount: Int,
        wallPotential: MLXArray?,
        matterWeights: [Float]?
    ) {
        guard config.border == "torus" else {
            preconditionFailure("Backend cpu supports torus borders only, got \(config.border).")
        }
        let maxAdvection = Float(config.dd) - config.sigma
        guard FlowLeniaFieldLayout.usesLocalTorusDistance(
            sx: config.sx,
            sy: config.sy,
            dd: config.dd,
            maxAdvection: maxAdvection,
            useTorus: true
        ) else {
            preconditionFailure("Backend cpu needs a torus whose half side exceeds dd + max advection, got \(config.sx) x \(config.sy) with dd \(config.dd).")
        }
        guard (0...4).contains(config.n) else {
            preconditionFailure("Backend cpu supports alpha exponents n in 0...4, got \(config.n).")
        }
        for side in [config.sx, config.sy] where side < 16 || side & (side - 1) != 0 {
            preconditionFailure("Backend cpu needs power-of-two grid sides of at least 16, got \(config.sx) x \(config.sy).")
        }
        let kernelCount = FlowLeniaFieldLayout.parameterCount(for: kernels)
        let kernelBatchCount = FlowLeniaFieldLayout.kernelBatchCount(for: kernels)
        self.config = config
        self.batchCount = batchCount
        self.channelCount = config.channels
        self.kernelCount = kernelCount
        self.kernelBatchCount = kernelBatchCount
        guard kernelBatchCount == 1 || kernelBatchCount == batchCount else {
            preconditionFailure("Backend cpu requires either shared kernels or one kernel set per batch element.")
        }

        let sigma = config.sigma
        let radicesX = FlowLeniaSpectralPlan.radices(config.sx)!.map { Int32($0) }
        let radicesY = FlowLeniaSpectralPlan.radices(config.sy)!.map { Int32($0) }
        let twiddleX = FlowLeniaSpectralPlan.twiddles(length: config.sx)
        let twiddleY = FlowLeniaSpectralPlan.twiddles(length: config.sy)
        // Derived constants are formed exactly as the Metal kernel source forms them.
        let clipMax = min(1.0 as Float, sigma * 2.0)
        let areaScale = Float(1.0 / Double(4.0 * sigma * sigma))
        let inverseScale = Float(1.0 / (Double(config.sx) * Double(config.sy)))
        self.engine = twiddleX.withUnsafeBufferPointer { twiddleXPointer in
            twiddleY.withUnsafeBufferPointer { twiddleYPointer in
                radicesX.withUnsafeBufferPointer { radicesXPointer in
                    radicesY.withUnsafeBufferPointer { radicesYPointer in
                        var engineConfig = FLCPUConfig(
                            batchCount: Int32(batchCount),
                            sx: Int32(config.sx),
                            sy: Int32(config.sy),
                            channelCount: Int32(config.channels),
                            kernelCount: Int32(kernelCount),
                            kernelBatchCount: Int32(kernelBatchCount),
                            dd: Int32(config.dd),
                            n: Int32(config.n),
                            alphaPerChannel: config.implementation.alphaMode == "per_channel" ? 1 : 0,
                            clipFlow: config.implementation.flowClip == "always" ? 1 : 0,
                            threadCount: flcpu_available_threads(),
                            dt: config.dt,
                            sigma: sigma,
                            thetaA: config.thetaA,
                            clipMax: clipMax,
                            maxAdvection: maxAdvection,
                            areaScale: areaScale,
                            inverseScale: inverseScale,
                            twiddleX: twiddleXPointer.baseAddress,
                            twiddleY: twiddleYPointer.baseAddress,
                            radicesX: radicesXPointer.baseAddress,
                            radixCountX: Int32(radicesX.count),
                            radicesY: radicesYPointer.baseAddress,
                            radixCountY: Int32(radicesY.count)
                        )
                        return flcpu_create(&engineConfig)
                    }
                }
            }
        }
        updateKernels(kernels)
        setMatterWeights(matterWeights)
        if let wallPotential {
            let values = FlowLeniaFieldLayout.expandedScalarField(
                from: wallPotential,
                batchCount: batchCount,
                sx: config.sx,
                sy: config.sy,
                label: "wallPotential"
            )
            flcpu_set_potential(engine, values)
        }
    }

    deinit {
        flcpu_destroy(engine)
    }

    func updateKernels(_ kernels: CompiledKernels) {
        guard FlowLeniaFieldLayout.parameterCount(for: kernels) == kernelCount,
              FlowLeniaFieldLayout.kernelBatchCount(for: kernels) == kernelBatchCount else {
            preconditionFailure("Backend cpu requires a stable kernel count and kernel batch count across kernel updates.")
        }
        guard kernels.c1Mask.shape == [channelCount, kernelCount], kernels.c0Idxs.shape[0] == kernelCount else {
            preconditionFailure("Backend cpu requires c1Mask and c0Idxs to match the configured channels and kernel count.")
        }
        let reducedY = config.sy / 2 + 1
        let spectra = kernels.fK[0..., 0..., 0..<reducedY, 0...]
        let largestReal = MLX.abs(spectra.realPart()).max().item(Float.self)
        let largestImaginary = MLX.abs(spectra.imaginaryPart()).max().item(Float.self)
        guard largestImaginary <= 1e-5 * largestReal else {
            preconditionFailure("Backend cpu requires point-symmetric kernels with real spectra, got imaginary parts up to \(largestImaginary) against \(largestReal).")
        }
        let packed = spectra.realPart().transposed(axes: [0, 2, 3, 1]).contiguous()
        guard packed.shape == [kernelBatchCount, reducedY, kernelCount, config.sx] else {
            preconditionFailure("Backend cpu requires kernel spectra to match its batch, grid, and kernel dimensions.")
        }
        let spectrumValues = packed.asArray(Float.self)
        let c0Values = kernels.c0Idxs.asArray(Int32.self)
        let mValues = FlowLeniaFieldLayout.expandedKernelScalars(
            from: kernels.m,
            batchCount: batchCount,
            parameterCount: kernelCount,
            label: "m"
        )
        let sValues = FlowLeniaFieldLayout.expandedKernelScalars(
            from: kernels.s,
            batchCount: batchCount,
            parameterCount: kernelCount,
            label: "s"
        )
        let outputWeights = kernels.c1Mask.asArray(Float.self)
        flcpu_set_kernels(engine, spectrumValues, c0Values, mValues, sValues, outputWeights)
    }

    func setMatterWeights(_ weights: [Float]?) {
        let resolved = weights ?? Array(repeating: 1.0, count: channelCount)
        guard resolved.count == channelCount else {
            preconditionFailure("Backend cpu matter weights must match the configured channel count.")
        }
        flcpu_set_matter_weights(engine, resolved)
    }

    func reset(
        mass: MLXArray,
        params: MLXArray,
        wallMask: MLXArray?,
        staticChannelFields: [FlowLeniaChannelField],
        food: FlowLeniaFoodState?,
        mixStep: Int
    ) {
        guard wallMask == nil, staticChannelFields.isEmpty, food == nil else {
            preconditionFailure("Backend cpu does not support wall masks, static channel fields, or food; use metal-full.")
        }
        guard mass.shape == [batchCount, config.sx, config.sy, channelCount] else {
            preconditionFailure("Backend cpu expects mass with shape [batch, sx, sy, channels], got \(mass.shape).")
        }
        guard params.shape == [batchCount, config.sx, config.sy, kernelCount] else {
            preconditionFailure("Backend cpu expects params with shape [batch, sx, sy, kernels], got \(params.shape).")
        }
        let massValues = mass.asType(Float.self).asArray(Float.self)
        let paramValues = params.asType(Float.self).asArray(Float.self)
        flcpu_set_state(engine, massValues, paramValues)
    }

    func step(count: Int) {
        guard count > 0 else {
            return
        }
        flcpu_step(engine, Int32(count))
    }

    /// Fixed parameter fields do not move with the mass, so a patch after step i is the same as
    /// stepping i times, patching, and continuing.
    func step(count: Int, postStepParameterPatches: [Int: [FlowLeniaParameterPatchBatch]]) {
        var completed = 0
        for patchStep in postStepParameterPatches.keys.sorted() where patchStep >= 1 && patchStep <= count {
            step(count: patchStep - completed)
            completed = patchStep
            for patch in postStepParameterPatches[patchStep]! {
                applyParameterPatch(origins: patch.origins, size: patch.size, deltas: patch.deltas, clip: patch.clip)
            }
        }
        step(count: count - completed)
    }

    func applyParameterPatch(origins: [SIMD2<Int32>], size: Int, deltas: [Float], clip: [Float]?) {
        guard size > 0 else {
            return
        }
        guard origins.count == batchCount, deltas.count == batchCount * size * size * kernelCount else {
            preconditionFailure("Backend cpu parameter patch needs one origin per batch element and [batch, size, size, kernels] deltas.")
        }
        if let clip {
            guard clip.count == 2 else {
                preconditionFailure("Backend cpu parameter patch clip must be [low, high].")
            }
        }
        flcpu_parameter_patch(
            engine,
            origins.flatMap { [$0.x, $0.y] },
            Int32(size),
            deltas,
            clip == nil ? 0 : 1,
            clip?[0] ?? 0,
            clip?[1] ?? 0
        )
    }

    func applyZeroStatePatch(origins: [SIMD2<Int32>], size: Int) {
        guard size > 0 else {
            return
        }
        guard origins.count == batchCount else {
            preconditionFailure("Backend cpu zero-state patch needs one origin per batch element.")
        }
        flcpu_zero_state_patch(engine, origins.flatMap { [$0.x, $0.y] }, Int32(size))
    }

    func observeMass(
        occupancyThreshold: Float,
        includeGyration: Bool,
        channelWeights: [Float]? = nil,
        materializeMap: Bool
    ) -> (summary: FlowLeniaMassSummary, massMap: MLXArray?) {
        let weights = resolvedChannelWeights(channelWeights)
        var sums = [FLCPUMassSummary](repeating: FLCPUMassSummary(), count: batchCount)
        flcpu_summarize(engine, occupancyThreshold, weights, includeGyration ? 1 : 0, &sums)
        massObservationSynchronizationCount += 1
        let summary = FlowLeniaMassSummary(
            totalMass: sums.map(\.totalMass),
            sumSquares: sums.map(\.sumSquares),
            energy: sums.map(\.energy),
            occupancyCount: sums.map(\.occupancyCount),
            centerXIndex: sums.map { $0.totalMass > 1e-6 ? $0.weightedX / $0.totalMass : 0.0 },
            centerYIndex: sums.map { $0.totalMass > 1e-6 ? $0.weightedY / $0.totalMass : 0.0 },
            rawGyration: includeGyration ? sums.map(\.rawGyration) : nil
        )
        return (summary, materializeMap ? readMassMap(weights: weights) : nil)
    }

    func materializeMassMap(channelWeights: [Float]? = nil) -> MLXArray {
        massObservationSynchronizationCount += 1
        return readMassMap(weights: resolvedChannelWeights(channelWeights))
    }

    func materializeMass() -> MLXArray {
        var values = [Float](repeating: 0, count: batchCount * config.sx * config.sy * channelCount)
        flcpu_get_mass(engine, &values)
        return MLXArray(values).reshaped([batchCount, config.sx, config.sy, channelCount])
    }

    func materializeParams() -> MLXArray {
        var values = [Float](repeating: 0, count: batchCount * config.sx * config.sy * kernelCount)
        flcpu_get_params(engine, &values)
        return MLXArray(values).reshaped([batchCount, config.sx, config.sy, kernelCount])
    }

    func materializeState() -> (mass: MLXArray, params: MLXArray) {
        (materializeMass(), materializeParams())
    }

    func materializeLastPotential() -> [Float] {
        var values = [Float](repeating: 0, count: batchCount * config.sx * config.sy * channelCount)
        flcpu_get_last_potential(engine, &values)
        return values
    }

    func summarizeFoodMass() -> [Float]? {
        nil
    }

    private func resolvedChannelWeights(_ weights: [Float]?) -> [Float] {
        let resolved = weights ?? Array(repeating: 1.0, count: channelCount)
        guard resolved.count == channelCount else {
            preconditionFailure("Backend cpu mass weights must match the configured channel count.")
        }
        return resolved
    }

    private func readMassMap(weights: [Float]) -> MLXArray {
        var values = [Float](repeating: 0, count: batchCount * config.sx * config.sy)
        flcpu_mass_map(engine, weights, &values)
        return MLXArray(values).reshaped([batchCount, config.sx, config.sy])
    }
}
