import Foundation
import Metal
import MetalPerformanceShaders
import MetalPerformanceShadersGraph
import MLX

final class FlowLeniaMetalFullPipeline {
    enum ParameterMixMode: Int {
        case average = 0
        case stochastic = 1

        init(configValue: String) {
            switch configValue {
            case "avg":
                self = .average
            case "stoch":
                self = .stochastic
            default:
                preconditionFailure("Flow Metal full pipeline supports parameter mix avg or stoch, got \(configValue).")
            }
        }
    }

    private struct ReintegrateUniforms {
        var mixSeed: UInt32
        var mixStep: UInt32
    }

    struct StageProfile {
        let fftMs: Double
        let growthReduceMs: Double
        let flowMs: Double
        let reintegrateMs: Double
        let totalMs: Double
    }

    static let summaryThreadCount = 256
    static let summaryChunkFactor = 8
    static let summaryChunkSpan = summaryThreadCount * summaryChunkFactor

    let config: BatchedConfig
    let parameterCount: Int
    let batchCount: Int
    let channelCount: Int
    let device: MTLDevice
    let commandQueue: MTLCommandQueue
    let library: MTLLibrary

    let kernelCount: Int
    private let kernelBatchCount: Int
    private let parameterFieldMode: FlowLeniaParameterFieldMode
    private let parameterMixMode: ParameterMixMode
    private let mixSeed: UInt32
    private let spectrumGatherPipeline: MTLComputePipelineState
    private let growthReducePipeline: MTLComputePipelineState
    private let wallPotentialPipeline: MTLComputePipelineState
    private let flowPipeline: MTLComputePipelineState
    private let reintegratePipeline: MTLComputePipelineState

    private let forwardFFTExecutable: MPSGraphExecutable
    private let forwardFFTInputShape: [NSNumber]
    private let forwardFFTOutputShape: [NSNumber]
    private let inverseFFTExecutable: MPSGraphExecutable
    private let inverseFFTInputShape: [NSNumber]
    private let inverseFFTOutputShape: [NSNumber]

    private let kernelBuffer: MTLBuffer
    private let c0IdxBuffer: MTLBuffer
    private let mBuffer: MTLBuffer
    private let sBuffer: MTLBuffer
    private let matterWeightsBuffer: MTLBuffer
    private let outputWeightsBuffer: MTLBuffer
    private let channelSpectrumBuffer: MTLBuffer
    private let gatheredSpectrumBuffer: MTLBuffer
    private let ukBuffer: MTLBuffer
    private let matterBuffer: MTLBuffer
    private let uBuffer: MTLBuffer
    private let flowBuffer: MTLBuffer
    private let wallPotentialBuffer: MTLBuffer

    private let c0IdxTransferBuffer: MTLBuffer
    private let mTransferBuffer: MTLBuffer
    private let sTransferBuffer: MTLBuffer
    private let matterWeightsTransferBuffer: MTLBuffer
    private let outputWeightsTransferBuffer: MTLBuffer
    private let wallPotentialTransferBuffer: MTLBuffer
    private var wallPotentialEnabled = false

    init(
        config: BatchedConfig,
        kernels: CompiledKernels,
        batchCount: Int,
        device: MTLDevice,
        commandQueue: MTLCommandQueue,
        wallPotential: MLXArray? = nil,
        matterWeights: [Float]? = nil,
        parameterFieldMode: FlowLeniaParameterFieldMode = .kernelGain,
        reintegrateParams: Bool = true,
        parameterMix: String = "avg",
        mixSeed: Int? = nil
    ) {
        self.config = config
        self.kernelCount = Self.parameterCount(for: kernels)
        guard parameterFieldMode != .none else {
            preconditionFailure("Flow Metal full pipeline requires an embedded parameter field mode.")
        }
        self.parameterFieldMode = parameterFieldMode
        self.parameterCount = parameterFieldMode.parameterCount(kernelCount: self.kernelCount)
        self.batchCount = batchCount
        self.channelCount = config.channels
        self.device = device
        self.commandQueue = commandQueue
        self.kernelBatchCount = Self.kernelBatchCount(for: kernels)
        self.parameterMixMode = ParameterMixMode(configValue: parameterMix)
        self.mixSeed = UInt32(bitPattern: Int32(mixSeed ?? 42))
        guard self.kernelBatchCount == 1 || self.kernelBatchCount == batchCount else {
            preconditionFailure("Flow Metal full pipeline requires either one shared kernel set or one kernel set per batch element.")
        }

        self.library = Self.makeLibrary(
            device: device,
            source: Self.kernelSource(
                kernelCount: self.kernelCount,
                parameterCount: self.parameterCount,
                batchCount: batchCount,
                channelCount: self.channelCount,
                kernelBatchCount: self.kernelBatchCount,
                summaryPartialGroupCount: Self.summaryPartialGroupCount(sx: config.sx, sy: config.sy),
                sx: config.sx,
                sy: config.sy,
                dt: config.dt,
                dd: config.dd,
                sigma: config.sigma,
                thetaA: config.thetaA,
                n: config.n,
                useTorus: config.border == "torus",
                alphaMode: config.implementation.alphaMode,
                flowClip: config.implementation.flowClip,
                parameterFieldMode: self.parameterFieldMode,
                reintegrateParams: reintegrateParams,
                parameterMixMode: self.parameterMixMode
            )
        )
        self.spectrumGatherPipeline = Self.makePipeline(device: device, library: self.library, name: "flowMetalGatherKernelSpectra")
        self.growthReducePipeline = Self.makePipeline(device: device, library: self.library, name: "flowMetalGrowthReduce")
        self.wallPotentialPipeline = Self.makePipeline(device: device, library: self.library, name: "flowMetalAddWallPotential")
        self.flowPipeline = Self.makePipeline(device: device, library: self.library, name: "flowMetalFlowFromScalarField")
        self.reintegratePipeline = Self.makePipeline(device: device, library: self.library, name: "flowMetalReintegrateAverage")

        let cellCount = batchCount * config.sx * config.sy
        let reducedY = (config.sy / 2) + 1
        let scalarBytes = cellCount * MemoryLayout<Float>.stride
        let channelScalarBytes = cellCount * self.channelCount * MemoryLayout<Float>.stride
        let ukBytes = cellCount * self.kernelCount * MemoryLayout<Float>.stride
        let flowBytes = cellCount * self.channelCount * 2 * MemoryLayout<Float>.stride
        let kernelBytes = self.kernelBatchCount * config.sx * reducedY * self.kernelCount * MemoryLayout<SIMD2<Float>>.stride
        let channelSpectrumBytes = cellCount / config.sy * reducedY * self.channelCount * MemoryLayout<SIMD2<Float>>.stride
        let gatheredSpectrumBytes = cellCount / config.sy * reducedY * self.kernelCount * MemoryLayout<SIMD2<Float>>.stride
        let c0IdxBytes = self.kernelCount * MemoryLayout<Int32>.stride
        let kernelScalarBytes = batchCount * self.kernelCount * MemoryLayout<Float>.stride
        let matterWeightsBytes = self.channelCount * MemoryLayout<Float>.stride
        let outputWeightsBytes = self.channelCount * self.kernelCount * MemoryLayout<Float>.stride

        self.kernelBuffer = Self.makePrivateBuffer(
            device: device,
            length: kernelBytes,
            label: "flow-metal.kernel-spectrum"
        )
        self.c0IdxBuffer = Self.makePrivateBuffer(
            device: device,
            length: c0IdxBytes,
            label: "flow-metal.c0Idx"
        )
        self.mBuffer = Self.makePrivateBuffer(
            device: device,
            length: kernelScalarBytes,
            label: "flow-metal.m"
        )
        self.sBuffer = Self.makePrivateBuffer(
            device: device,
            length: kernelScalarBytes,
            label: "flow-metal.s"
        )
        self.matterWeightsBuffer = Self.makePrivateBuffer(
            device: device,
            length: matterWeightsBytes,
            label: "flow-metal.matterWeights"
        )
        self.outputWeightsBuffer = Self.makePrivateBuffer(
            device: device,
            length: outputWeightsBytes,
            label: "flow-metal.outputWeights"
        )
        self.channelSpectrumBuffer = Self.makePrivateBuffer(
            device: device,
            length: channelSpectrumBytes,
            label: "flow-metal.channelSpectra"
        )
        self.gatheredSpectrumBuffer = Self.makePrivateBuffer(
            device: device,
            length: gatheredSpectrumBytes,
            label: "flow-metal.gatheredSpectra"
        )
        self.ukBuffer = Self.makePrivateBuffer(device: device, length: ukBytes, label: "flow-metal.uk")
        self.matterBuffer = Self.makePrivateBuffer(device: device, length: scalarBytes, label: "flow-metal.matter")
        self.uBuffer = Self.makePrivateBuffer(device: device, length: channelScalarBytes, label: "flow-metal.u")
        self.flowBuffer = Self.makePrivateBuffer(device: device, length: flowBytes, label: "flow-metal.flow")
        self.wallPotentialBuffer = Self.makePrivateBuffer(
            device: device,
            length: scalarBytes,
            label: "flow-metal.wallPotential"
        )

        self.c0IdxTransferBuffer = Self.makeSharedBuffer(
            device: device,
            length: c0IdxBytes,
            label: "flow-metal.c0Idx-transfer"
        )
        self.mTransferBuffer = Self.makeSharedBuffer(
            device: device,
            length: kernelScalarBytes,
            label: "flow-metal.m-transfer"
        )
        self.sTransferBuffer = Self.makeSharedBuffer(
            device: device,
            length: kernelScalarBytes,
            label: "flow-metal.s-transfer"
        )
        self.matterWeightsTransferBuffer = Self.makeSharedBuffer(
            device: device,
            length: matterWeightsBytes,
            label: "flow-metal.matterWeights-transfer"
        )
        self.outputWeightsTransferBuffer = Self.makeSharedBuffer(
            device: device,
            length: outputWeightsBytes,
            label: "flow-metal.outputWeights-transfer"
        )
        self.wallPotentialTransferBuffer = Self.makeSharedBuffer(
            device: device,
            length: scalarBytes,
            label: "flow-metal.wallPotential-transfer"
        )

        let forwardPlan = try! Self.buildForwardFFTExecutable(
            device: device,
            batchCount: batchCount,
            channelCount: self.channelCount,
            sx: config.sx,
            sy: config.sy
        )
        self.forwardFFTExecutable = forwardPlan.executable
        self.forwardFFTInputShape = forwardPlan.inputShape
        self.forwardFFTOutputShape = forwardPlan.outputShape

        let inversePlan = try! Self.buildInverseFFTExecutable(
            device: device,
            batchCount: batchCount,
            parameterCount: self.kernelCount,
            sx: config.sx,
            sy: config.sy
        )
        self.inverseFFTExecutable = inversePlan.executable
        self.inverseFFTInputShape = inversePlan.inputShape
        self.inverseFFTOutputShape = inversePlan.outputShape

        updateKernels(kernels)
        updateMatterWeights(matterWeights)
        updateWallPotential(wallPotential)
    }

    func updateKernels(_ kernels: CompiledKernels) {
        guard Self.parameterCount(for: kernels) == kernelCount else {
            preconditionFailure("Flow Metal full pipeline requires a stable parameter count across kernel updates.")
        }
        guard Self.kernelBatchCount(for: kernels) == kernelBatchCount else {
            preconditionFailure("Flow Metal full pipeline requires a stable kernel batch count across kernel updates.")
        }
        guard kernels.c1Mask.shape == [channelCount, kernelCount] else {
            preconditionFailure("Flow Metal full pipeline requires c1Mask to match the configured channels and parameter count.")
        }
        guard kernels.c0Idxs.shape[0] == kernelCount else {
            preconditionFailure("Flow Metal full pipeline requires c0Idxs to match the parameter count.")
        }

        let reducedY = (config.sy / 2) + 1
        let packedKernel = kernels.fK[0..., 0..., 0..<reducedY, 0...].contiguous()
        guard packedKernel.shape == [kernelBatchCount, config.sx, reducedY, kernelCount] else {
            preconditionFailure("Flow Metal full pipeline requires kernel spectra to match its batch, grid, and parameter dimensions.")
        }
        guard let sourceKernelBuffer = packedKernel.asMTLBuffer(device: device, noCopy: true)
            ?? packedKernel.asMTLBuffer(device: device, noCopy: false) else {
            preconditionFailure("Flow Metal full pipeline could not materialize kernel spectra as an MTLBuffer.")
        }
        let c0IdxValues = kernels.c0Idxs.asArray(Int32.self)
        _ = c0IdxValues.withUnsafeBytes { rawValues in
            memcpy(c0IdxTransferBuffer.contents(), rawValues.baseAddress, rawValues.count)
        }
        let mValues = Self.expandedKernelScalars(
            from: kernels.m,
            batchCount: batchCount,
            parameterCount: kernelCount,
            label: "m"
        )
        let sValues = Self.expandedKernelScalars(
            from: kernels.s,
            batchCount: batchCount,
            parameterCount: kernelCount,
            label: "s"
        )
        Self.writeFloats(mValues, to: mTransferBuffer)
        Self.writeFloats(sValues, to: sTransferBuffer)
        Self.writeFloats(kernels.c1Mask.asArray(Float.self), to: outputWeightsTransferBuffer)

        let uploads: [(source: MTLBuffer, destination: MTLBuffer, length: Int)] = [
            (sourceKernelBuffer, kernelBuffer, kernelBuffer.length),
            (c0IdxTransferBuffer, c0IdxBuffer, c0IdxBuffer.length),
            (mTransferBuffer, mBuffer, mBuffer.length),
            (sTransferBuffer, sBuffer, sBuffer.length),
            (outputWeightsTransferBuffer, outputWeightsBuffer, outputWeightsBuffer.length),
        ]
        guard let commandBuffer = commandQueue.makeCommandBuffer(),
              let encoder = commandBuffer.makeBlitCommandEncoder() else {
            preconditionFailure("Failed to create Flow Metal kernel upload command buffer.")
        }
        commandBuffer.label = "flow-metal.kernels.upload"
        for upload in uploads {
            guard upload.source.length >= upload.length else {
                preconditionFailure("Flow Metal kernel upload source is smaller than its destination.")
            }
            encoder.copy(
                from: upload.source,
                sourceOffset: 0,
                to: upload.destination,
                destinationOffset: 0,
                size: upload.length
            )
        }
        encoder.endEncoding()
        Self.commitAndWait(commandBuffer, label: "flow-metal.kernels.upload")
    }

    func updateMatterWeights(_ weights: [Float]?) {
        let resolved = weights ?? Self.defaultMatterWeights(channelCount: channelCount)
        guard resolved.count == channelCount else {
            preconditionFailure("Flow Metal matter weights must match the configured channel count.")
        }
        Self.uploadFloats(
            resolved,
            toPrivate: matterWeightsBuffer,
            stagingBuffer: matterWeightsTransferBuffer,
            commandQueue: commandQueue,
            label: "flow-metal.matterWeights"
        )
    }

    func updateWallPotential(_ wallPotential: MLXArray?) {
        guard let wallPotential else {
            wallPotentialEnabled = false
            return
        }
        wallPotentialEnabled = true
        let values = Self.expandedScalarField(
            from: wallPotential,
            batchCount: batchCount,
            sx: config.sx,
            sy: config.sy,
            label: "wallPotential"
        )
        Self.uploadFloats(
            values,
            toPrivate: wallPotentialBuffer,
            stagingBuffer: wallPotentialTransferBuffer,
            commandQueue: commandQueue,
            label: "flow-metal.wallPotential"
        )
    }

    func encodeStep(
        on commandBuffer: MTLCommandBuffer,
        preparedMassBuffer: MTLBuffer,
        paramsBuffer: MTLBuffer,
        nextMassBuffer: MTLBuffer,
        nextParamsBuffer: MTLBuffer,
        mixStep: Int = 0
    ) {
        encodeFFT(on: commandBuffer, preparedMassBuffer: preparedMassBuffer)
        encodeGrowthReduce(on: commandBuffer, preparedMassBuffer: preparedMassBuffer, paramsBuffer: paramsBuffer)
        encodeWallPotential(on: commandBuffer)
        encodeFlow(on: commandBuffer, preparedMassBuffer: preparedMassBuffer)
        encodeReintegrate(
            on: commandBuffer,
            preparedMassBuffer: preparedMassBuffer,
            paramsBuffer: paramsBuffer,
            nextMassBuffer: nextMassBuffer,
            nextParamsBuffer: nextParamsBuffer,
            mixStep: mixStep
        )
    }

    var requiresSegmentedStepEncoding: Bool {
        let reducedY = (config.sy / 2) + 1
        let inverseFFTComplexElements = batchCount * config.sx * reducedY * kernelCount
        return inverseFFTComplexElements > 16_000_000
    }

    func runStep(
        preparedMassBuffer: MTLBuffer,
        paramsBuffer: MTLBuffer,
        nextMassBuffer: MTLBuffer,
        nextParamsBuffer: MTLBuffer,
        mixStep: Int = 0
    ) {
        if requiresSegmentedStepEncoding {
            runSegmentedStep(
                preparedMassBuffer: preparedMassBuffer,
                paramsBuffer: paramsBuffer,
                nextMassBuffer: nextMassBuffer,
                nextParamsBuffer: nextParamsBuffer,
                mixStep: mixStep
            )
            return
        }

        let commandBuffer = makeCommandBuffer(label: "flow-metal.step")
        encodeStep(
            on: commandBuffer,
            preparedMassBuffer: preparedMassBuffer,
            paramsBuffer: paramsBuffer,
            nextMassBuffer: nextMassBuffer,
            nextParamsBuffer: nextParamsBuffer,
            mixStep: mixStep
        )
        Self.commitAndWait(commandBuffer, label: "flow-metal.step")
    }

    func runSegmentedStep(
        preparedMassBuffer: MTLBuffer,
        paramsBuffer: MTLBuffer,
        nextMassBuffer: MTLBuffer,
        nextParamsBuffer: MTLBuffer,
        mixStep: Int = 0
    ) {
        let forwardCommandBuffer = makeCommandBuffer(label: "flow-metal.segment.forward-fft")
        encodeForwardFFT(on: forwardCommandBuffer, preparedMassBuffer: preparedMassBuffer)
        Self.commitAndWait(forwardCommandBuffer, label: "flow-metal.segment.forward-fft")

        let gatherCommandBuffer = makeCommandBuffer(label: "flow-metal.segment.gather-spectrum")
        encodeGatherSpectrum(on: gatherCommandBuffer)
        Self.commitAndWait(gatherCommandBuffer, label: "flow-metal.segment.gather-spectrum")

        let inverseCommandBuffer = makeCommandBuffer(label: "flow-metal.segment.inverse-fft")
        encodeInverseFFT(on: inverseCommandBuffer)
        Self.commitAndWait(inverseCommandBuffer, label: "flow-metal.segment.inverse-fft")

        let computeCommandBuffer = makeCommandBuffer(label: "flow-metal.segment.compute")
        encodeGrowthReduce(on: computeCommandBuffer, preparedMassBuffer: preparedMassBuffer, paramsBuffer: paramsBuffer)
        encodeWallPotential(on: computeCommandBuffer)
        encodeFlow(on: computeCommandBuffer, preparedMassBuffer: preparedMassBuffer)
        encodeReintegrate(
            on: computeCommandBuffer,
            preparedMassBuffer: preparedMassBuffer,
            paramsBuffer: paramsBuffer,
            nextMassBuffer: nextMassBuffer,
            nextParamsBuffer: nextParamsBuffer,
            mixStep: mixStep
        )
        Self.commitAndWait(computeCommandBuffer, label: "flow-metal.segment.compute")
    }

    func profileStep(
        preparedMassBuffer: MTLBuffer,
        paramsBuffer: MTLBuffer,
        nextMassBuffer: MTLBuffer,
        nextParamsBuffer: MTLBuffer
    ) -> StageProfile {
        if requiresSegmentedStepEncoding {
            return profileSegmentedStep(
                preparedMassBuffer: preparedMassBuffer,
                paramsBuffer: paramsBuffer,
                nextMassBuffer: nextMassBuffer,
                nextParamsBuffer: nextParamsBuffer
            )
        }

        let totalStart = ContinuousClock.now

        let fftStart = totalStart
        let fftCommandBuffer = makeCommandBuffer(label: "flow-metal.profile.fft")
        encodeFFT(on: fftCommandBuffer, preparedMassBuffer: preparedMassBuffer)
        Self.commitAndWait(fftCommandBuffer, label: "flow-metal.profile.fft")
        let fftMs = flowSandboxDurationMs(fftStart.duration(to: ContinuousClock.now))

        let growthReduceStart = ContinuousClock.now
        let growthCommandBuffer = makeCommandBuffer(label: "flow-metal.profile.growth")
        encodeGrowthReduce(on: growthCommandBuffer, preparedMassBuffer: preparedMassBuffer, paramsBuffer: paramsBuffer)
        encodeWallPotential(on: growthCommandBuffer)
        Self.commitAndWait(growthCommandBuffer, label: "flow-metal.profile.growth")
        let growthReduceMs = flowSandboxDurationMs(growthReduceStart.duration(to: ContinuousClock.now))

        let flowStart = ContinuousClock.now
        let flowCommandBuffer = makeCommandBuffer(label: "flow-metal.profile.flow")
        encodeFlow(on: flowCommandBuffer, preparedMassBuffer: preparedMassBuffer)
        Self.commitAndWait(flowCommandBuffer, label: "flow-metal.profile.flow")
        let flowMs = flowSandboxDurationMs(flowStart.duration(to: ContinuousClock.now))

        let reintegrateStart = ContinuousClock.now
        let reintegrateCommandBuffer = makeCommandBuffer(label: "flow-metal.profile.reintegrate")
        encodeReintegrate(
            on: reintegrateCommandBuffer,
            preparedMassBuffer: preparedMassBuffer,
            paramsBuffer: paramsBuffer,
            nextMassBuffer: nextMassBuffer,
            nextParamsBuffer: nextParamsBuffer,
            mixStep: 0
        )
        Self.commitAndWait(reintegrateCommandBuffer, label: "flow-metal.profile.reintegrate")
        let reintegrateMs = flowSandboxDurationMs(reintegrateStart.duration(to: ContinuousClock.now))

        let totalMs = flowSandboxDurationMs(totalStart.duration(to: ContinuousClock.now))
        return StageProfile(
            fftMs: fftMs,
            growthReduceMs: growthReduceMs,
            flowMs: flowMs,
            reintegrateMs: reintegrateMs,
            totalMs: totalMs
        )
    }

    private func profileSegmentedStep(
        preparedMassBuffer: MTLBuffer,
        paramsBuffer: MTLBuffer,
        nextMassBuffer: MTLBuffer,
        nextParamsBuffer: MTLBuffer
    ) -> StageProfile {
        let totalStart = ContinuousClock.now

        let fftStart = totalStart
        let forwardCommandBuffer = makeCommandBuffer(label: "flow-metal.profile.segment.forward-fft")
        encodeForwardFFT(on: forwardCommandBuffer, preparedMassBuffer: preparedMassBuffer)
        Self.commitAndWait(forwardCommandBuffer, label: "flow-metal.profile.segment.forward-fft")

        let gatherCommandBuffer = makeCommandBuffer(label: "flow-metal.profile.segment.gather-spectrum")
        encodeGatherSpectrum(on: gatherCommandBuffer)
        Self.commitAndWait(gatherCommandBuffer, label: "flow-metal.profile.segment.gather-spectrum")

        let inverseCommandBuffer = makeCommandBuffer(label: "flow-metal.profile.segment.inverse-fft")
        encodeInverseFFT(on: inverseCommandBuffer)
        Self.commitAndWait(inverseCommandBuffer, label: "flow-metal.profile.segment.inverse-fft")
        let fftMs = flowSandboxDurationMs(fftStart.duration(to: ContinuousClock.now))

        let growthReduceStart = ContinuousClock.now
        let growthCommandBuffer = makeCommandBuffer(label: "flow-metal.profile.segment.growth")
        encodeGrowthReduce(on: growthCommandBuffer, preparedMassBuffer: preparedMassBuffer, paramsBuffer: paramsBuffer)
        encodeWallPotential(on: growthCommandBuffer)
        Self.commitAndWait(growthCommandBuffer, label: "flow-metal.profile.segment.growth")
        let growthReduceMs = flowSandboxDurationMs(growthReduceStart.duration(to: ContinuousClock.now))

        let flowStart = ContinuousClock.now
        let flowCommandBuffer = makeCommandBuffer(label: "flow-metal.profile.segment.flow")
        encodeFlow(on: flowCommandBuffer, preparedMassBuffer: preparedMassBuffer)
        Self.commitAndWait(flowCommandBuffer, label: "flow-metal.profile.segment.flow")
        let flowMs = flowSandboxDurationMs(flowStart.duration(to: ContinuousClock.now))

        let reintegrateStart = ContinuousClock.now
        let reintegrateCommandBuffer = makeCommandBuffer(label: "flow-metal.profile.segment.reintegrate")
        encodeReintegrate(
            on: reintegrateCommandBuffer,
            preparedMassBuffer: preparedMassBuffer,
            paramsBuffer: paramsBuffer,
            nextMassBuffer: nextMassBuffer,
            nextParamsBuffer: nextParamsBuffer,
            mixStep: 0
        )
        Self.commitAndWait(reintegrateCommandBuffer, label: "flow-metal.profile.segment.reintegrate")
        let reintegrateMs = flowSandboxDurationMs(reintegrateStart.duration(to: ContinuousClock.now))

        return StageProfile(
            fftMs: fftMs,
            growthReduceMs: growthReduceMs,
            flowMs: flowMs,
            reintegrateMs: reintegrateMs,
            totalMs: flowSandboxDurationMs(totalStart.duration(to: ContinuousClock.now))
        )
    }

    func readUK(batchCount: Int) -> [Float] {
        Self.copyFloatsFromGPUBuffer(
            ukBuffer,
            count: batchCount * kernelCount * config.sx * config.sy,
            device: device,
            commandQueue: commandQueue,
            label: "flow-metal.uk"
        )
    }

    func readScalarField(batchCount: Int) -> [Float] {
        let values = Self.copyFloatsFromGPUBuffer(
            uBuffer,
            count: batchCount * config.sx * config.sy * channelCount,
            device: device,
            commandQueue: commandQueue,
            label: "flow-metal.u"
        )
        guard channelCount > 0 else {
            return []
        }
        if channelCount == 1 {
            return values
        }
        var firstChannel = [Float](repeating: 0, count: batchCount * config.sx * config.sy)
        for batch in 0..<batchCount {
            for x in 0..<config.sx {
                for y in 0..<config.sy {
                    let cellIndex = (batch * config.sx + x) * config.sy + y
                    firstChannel[cellIndex] = values[cellIndex * channelCount]
                }
            }
        }
        return firstChannel
    }

    func readFlow(batchCount: Int) -> [Float] {
        let values = Self.copyFloatsFromGPUBuffer(
            flowBuffer,
            count: batchCount * config.sx * config.sy * channelCount * 2,
            device: device,
            commandQueue: commandQueue,
            label: "flow-metal.flow"
        )
        if channelCount == 1 {
            return values
        }
        var firstChannel = [Float](repeating: 0, count: batchCount * config.sx * config.sy * 2)
        for batch in 0..<batchCount {
            for x in 0..<config.sx {
                for y in 0..<config.sy {
                    let cellIndex = (batch * config.sx + x) * config.sy + y
                    let srcBase = cellIndex * channelCount * 2
                    let dstBase = cellIndex * 2
                    firstChannel[dstBase] = values[srcBase]
                    firstChannel[dstBase + 1] = values[srcBase + 1]
                }
            }
        }
        return firstChannel
    }

    private func encodeFFT(on commandBuffer: MTLCommandBuffer, preparedMassBuffer: MTLBuffer) {
        encodeForwardFFT(on: commandBuffer, preparedMassBuffer: preparedMassBuffer)
        encodeGatherSpectrum(on: commandBuffer)
        encodeInverseFFT(on: commandBuffer)
    }

    private func encodeForwardFFT(on commandBuffer: MTLCommandBuffer, preparedMassBuffer: MTLBuffer) {
        let forwardCommandBuffer = MPSCommandBuffer(commandBuffer: commandBuffer)
        let inputData = MPSGraphTensorData(preparedMassBuffer, shape: forwardFFTInputShape, dataType: .float32)
        let spectrumData = MPSGraphTensorData(channelSpectrumBuffer, shape: forwardFFTOutputShape, dataType: .complexFloat32)
        _ = forwardFFTExecutable.encode(
            to: forwardCommandBuffer,
            inputs: [inputData],
            results: [spectrumData],
            executionDescriptor: nil
        )
    }

    private func encodeInverseFFT(on commandBuffer: MTLCommandBuffer) {
        let inverseCommandBuffer = MPSCommandBuffer(commandBuffer: commandBuffer)
        let gatheredData = MPSGraphTensorData(gatheredSpectrumBuffer, shape: inverseFFTInputShape, dataType: .complexFloat32)
        let outputData = MPSGraphTensorData(ukBuffer, shape: inverseFFTOutputShape, dataType: .float32)
        _ = inverseFFTExecutable.encode(
            to: inverseCommandBuffer,
            inputs: [gatheredData],
            results: [outputData],
            executionDescriptor: nil
        )
    }

    private func encodeGrowthReduce(
        on commandBuffer: MTLCommandBuffer,
        preparedMassBuffer: MTLBuffer,
        paramsBuffer: MTLBuffer
    ) {
        encode(growthReducePipeline, on: commandBuffer) { encoder in
            encoder.setBuffer(ukBuffer, offset: 0, index: 0)
            encoder.setBuffer(paramsBuffer, offset: 0, index: 1)
            encoder.setBuffer(mBuffer, offset: 0, index: 2)
            encoder.setBuffer(sBuffer, offset: 0, index: 3)
            encoder.setBuffer(outputWeightsBuffer, offset: 0, index: 4)
            encoder.setBuffer(uBuffer, offset: 0, index: 5)
            encoder.setBuffer(preparedMassBuffer, offset: 0, index: 6)
            encoder.setBuffer(matterWeightsBuffer, offset: 0, index: 7)
            encoder.setBuffer(matterBuffer, offset: 0, index: 8)
        }
    }

    private func encodeFlow(on commandBuffer: MTLCommandBuffer, preparedMassBuffer: MTLBuffer) {
        encode(flowPipeline, on: commandBuffer) { encoder in
            encoder.setBuffer(uBuffer, offset: 0, index: 0)
            encoder.setBuffer(matterBuffer, offset: 0, index: 1)
            encoder.setBuffer(flowBuffer, offset: 0, index: 2)
            encoder.setBuffer(preparedMassBuffer, offset: 0, index: 3)
        }
    }

    private func encodeWallPotential(on commandBuffer: MTLCommandBuffer) {
        guard wallPotentialEnabled else {
            return
        }
        encode(wallPotentialPipeline, on: commandBuffer) { encoder in
            encoder.setBuffer(uBuffer, offset: 0, index: 0)
            encoder.setBuffer(wallPotentialBuffer, offset: 0, index: 1)
        }
    }

    private func encodeReintegrate(
        on commandBuffer: MTLCommandBuffer,
        preparedMassBuffer: MTLBuffer,
        paramsBuffer: MTLBuffer,
        nextMassBuffer: MTLBuffer,
        nextParamsBuffer: MTLBuffer,
        mixStep: Int
    ) {
        var uniforms = ReintegrateUniforms(
            mixSeed: mixSeed,
            mixStep: UInt32(max(0, mixStep))
        )
        encode(reintegratePipeline, on: commandBuffer) { encoder in
            encoder.setBuffer(preparedMassBuffer, offset: 0, index: 0)
            encoder.setBuffer(paramsBuffer, offset: 0, index: 1)
            encoder.setBuffer(flowBuffer, offset: 0, index: 2)
            encoder.setBuffer(nextMassBuffer, offset: 0, index: 3)
            encoder.setBuffer(nextParamsBuffer, offset: 0, index: 4)
            withUnsafeBytes(of: &uniforms) { rawUniforms in
                encoder.setBytes(rawUniforms.baseAddress!, length: rawUniforms.count, index: 5)
            }
        }
    }

    private func encodeGatherSpectrum(on commandBuffer: MTLCommandBuffer) {
        guard let encoder = commandBuffer.makeComputeCommandEncoder() else {
            preconditionFailure("Failed to create Flow Metal gather-spectrum encoder.")
        }
        encoder.setComputePipelineState(spectrumGatherPipeline)
        encoder.setBuffer(channelSpectrumBuffer, offset: 0, index: 0)
        encoder.setBuffer(kernelBuffer, offset: 0, index: 1)
        encoder.setBuffer(c0IdxBuffer, offset: 0, index: 2)
        encoder.setBuffer(gatheredSpectrumBuffer, offset: 0, index: 3)
        let threadWidth = max(1, spectrumGatherPipeline.threadExecutionWidth)
        let maxHeight = max(1, spectrumGatherPipeline.maxTotalThreadsPerThreadgroup / threadWidth)
        let threadHeight = min(8, maxHeight)
        let threadsPerGroup = MTLSize(width: threadWidth, height: threadHeight, depth: 1)
        let threads = MTLSize(width: ((config.sy / 2) + 1) * kernelCount, height: config.sx, depth: batchCount)
        encoder.dispatchThreads(threads, threadsPerThreadgroup: threadsPerGroup)
        encoder.endEncoding()
    }

    private func encode(
        _ pipeline: MTLComputePipelineState,
        on commandBuffer: MTLCommandBuffer,
        configure: (MTLComputeCommandEncoder) -> Void
    ) {
        guard let encoder = commandBuffer.makeComputeCommandEncoder() else {
            preconditionFailure("Failed to create Flow Metal compute encoder.")
        }
        encoder.setComputePipelineState(pipeline)
        configure(encoder)
        let threadWidth = max(1, pipeline.threadExecutionWidth)
        let maxHeight = max(1, pipeline.maxTotalThreadsPerThreadgroup / threadWidth)
        let threadHeight = min(8, maxHeight)
        let threadsPerGroup = MTLSize(width: threadWidth, height: threadHeight, depth: 1)
        let threads = MTLSize(width: config.sy, height: config.sx, depth: batchCount)
        encoder.dispatchThreads(threads, threadsPerThreadgroup: threadsPerGroup)
        encoder.endEncoding()
    }

    private func makeCommandBuffer(label: String) -> MTLCommandBuffer {
        guard let commandBuffer = commandQueue.makeCommandBuffer() else {
            preconditionFailure("Failed to create Flow Metal command buffer.")
        }
        commandBuffer.label = label
        return commandBuffer
    }

    static func makeDeviceAndQueue() -> (MTLDevice, MTLCommandQueue) {
        guard let device = MTLCreateSystemDefaultDevice(),
              let commandQueue = device.makeCommandQueue() else {
            preconditionFailure("Full-metal Flow backend requires a Metal device and command queue.")
        }
        return (device, commandQueue)
    }

    static func makeSharedBuffer(device: MTLDevice, length: Int, label: String) -> MTLBuffer {
        guard let buffer = device.makeBuffer(length: length, options: .storageModeShared) else {
            preconditionFailure("Failed to allocate Flow Metal buffer \(label).")
        }
        buffer.label = label
        return buffer
    }

    static func makePrivateBuffer(device: MTLDevice, length: Int, label: String) -> MTLBuffer {
        guard let buffer = device.makeBuffer(length: length, options: .storageModePrivate) else {
            preconditionFailure("Failed to allocate Flow Metal private buffer \(label).")
        }
        buffer.label = label
        return buffer
    }

    static func writeFloats(_ values: [Float], to buffer: MTLBuffer) {
        values.withUnsafeBytes { raw in
            guard let baseAddress = raw.baseAddress else { return }
            memcpy(buffer.contents(), baseAddress, raw.count)
        }
    }

    static func copyBuffer(
        _ source: MTLBuffer,
        to destination: MTLBuffer,
        length: Int,
        commandQueue: MTLCommandQueue,
        label: String
    ) {
        guard let commandBuffer = commandQueue.makeCommandBuffer(),
              let encoder = commandBuffer.makeBlitCommandEncoder() else {
            preconditionFailure("Failed to create Flow Metal blit command buffer \(label).")
        }
        commandBuffer.label = label
        encoder.copy(from: source, sourceOffset: 0, to: destination, destinationOffset: 0, size: length)
        encoder.endEncoding()
        commitAndWait(commandBuffer, label: label)
    }

    static func commitAndWait(_ commandBuffer: MTLCommandBuffer, label: String) {
        switch commandBuffer.status {
        case .notEnqueued, .enqueued:
            commandBuffer.commit()
        default:
            break
        }
        commandBuffer.waitUntilCompleted()
        if let error = commandBuffer.error {
            preconditionFailure("Flow Metal command buffer \(label) failed: \(error)")
        }
    }

    static func uploadFloats(
        _ values: [Float],
        toPrivate buffer: MTLBuffer,
        stagingBuffer: MTLBuffer,
        commandQueue: MTLCommandQueue,
        label: String
    ) {
        let byteCount = values.count * MemoryLayout<Float>.stride
        guard stagingBuffer.length >= byteCount else {
            preconditionFailure("Flow Metal staging buffer \(label) is too small for uploaded floats.")
        }
        writeFloats(values, to: stagingBuffer)
        copyBuffer(stagingBuffer, to: buffer, length: byteCount, commandQueue: commandQueue, label: "\(label).upload")
    }

    static func uploadFloats(
        _ values: [Float],
        toPrivate buffer: MTLBuffer,
        device: MTLDevice,
        commandQueue: MTLCommandQueue,
        label: String
    ) {
        let staging = makeSharedBuffer(device: device, length: values.count * MemoryLayout<Float>.stride, label: "\(label).staging")
        uploadFloats(
            values,
            toPrivate: buffer,
            stagingBuffer: staging,
            commandQueue: commandQueue,
            label: label
        )
    }

    static func readFloats(from buffer: MTLBuffer, count: Int) -> [Float] {
        let pointer = buffer.contents().bindMemory(to: Float.self, capacity: count)
        return Array(UnsafeBufferPointer(start: pointer, count: count))
    }

    static func copyFloatsFromGPUBuffer(
        _ buffer: MTLBuffer,
        count: Int,
        device: MTLDevice,
        commandQueue: MTLCommandQueue,
        label: String
    ) -> [Float] {
        let staging = makeSharedBuffer(device: device, length: count * MemoryLayout<Float>.stride, label: "\(label).staging")
        copyBuffer(buffer, to: staging, length: count * MemoryLayout<Float>.stride, commandQueue: commandQueue, label: "\(label).readback")
        return readFloats(from: staging, count: count)
    }

    static func makePipeline(device: MTLDevice, library: MTLLibrary, name: String) -> MTLComputePipelineState {
        guard let function = library.makeFunction(name: name) else {
            preconditionFailure("Missing Flow Metal function \(name).")
        }
        do {
            return try device.makeComputePipelineState(function: function)
        } catch {
            preconditionFailure("Failed to build Flow Metal pipeline \(name): \(error)")
        }
    }

    static func makeLibrary(device: MTLDevice, source: String) -> MTLLibrary {
        do {
            return try device.makeLibrary(source: source, options: nil)
        } catch {
            preconditionFailure("Failed to compile Flow Metal library: \(error)")
        }
    }

    static func parameterCount(for kernels: CompiledKernels) -> Int {
        guard kernels.c1Mask.shape.count == 2 else {
            preconditionFailure("Flow Metal kernels require c1Mask with shape [channels, nbK].")
        }
        return kernels.c1Mask.shape[1]
    }

    static func summaryPartialGroupCount(sx: Int, sy: Int) -> Int {
        let spatialCount = max(1, sx * sy)
        return max(1, (spatialCount + summaryChunkSpan - 1) / summaryChunkSpan)
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

    private static func defaultMatterWeights(channelCount: Int) -> [Float] {
        Array(repeating: 1.0, count: channelCount)
    }

    private static func expandedKernelScalars(
        from values: MLXArray,
        batchCount: Int,
        parameterCount: Int,
        label: String
    ) -> [Float] {
        switch values.shape.count {
        case 1:
            guard values.shape[0] == parameterCount else {
                preconditionFailure("Flow Metal \(label) values must match the kernel count.")
            }
            let row = values.asArray(Float.self)
            return Array(repeating: row, count: batchCount).flatMap { $0 }
        case 2:
            guard values.shape[1] == parameterCount else {
                preconditionFailure("Flow Metal \(label) values must match the kernel count.")
            }
            guard values.shape[0] == 1 || values.shape[0] == batchCount else {
                preconditionFailure("Flow Metal \(label) values must be shared across the batch or provided per batch element.")
            }
            let raw = values.asArray(Float.self)
            if values.shape[0] == batchCount {
                return raw
            }
            let row = Array(raw[0..<parameterCount])
            return Array(repeating: row, count: batchCount).flatMap { $0 }
        default:
            preconditionFailure("Flow Metal \(label) values must have rank 1 or 2.")
        }
    }

    private static func expandedScalarField(
        from values: MLXArray,
        batchCount: Int,
        sx: Int,
        sy: Int,
        label: String
    ) -> [Float] {
        guard values.shape.count == 4 else {
            preconditionFailure("Flow Metal \(label) must have rank 4 with shape [batch, sx, sy, 1].")
        }
        guard values.shape[1] == sx, values.shape[2] == sy, values.shape[3] == 1 else {
            preconditionFailure("Flow Metal \(label) must have shape [batch, \(sx), \(sy), 1].")
        }
        guard values.shape[0] == 1 || values.shape[0] == batchCount else {
            preconditionFailure("Flow Metal \(label) must be shared across the batch or provided per batch element.")
        }
        let contiguous = values.contiguous()
        let raw = contiguous.asArray(Float.self)
        if values.shape[0] == batchCount {
            return raw
        }
        return Array(repeating: raw, count: batchCount).flatMap { $0 }
    }

    private static func buildForwardFFTExecutable(
        device: MTLDevice,
        batchCount: Int,
        channelCount: Int,
        sx: Int,
        sy: Int
    ) throws -> (
        executable: MPSGraphExecutable,
        inputShape: [NSNumber],
        outputShape: [NSNumber]
    ) {
        let graph = MPSGraph()
        let inputShape: [NSNumber] = [
            NSNumber(value: batchCount),
            NSNumber(value: sx),
            NSNumber(value: sy),
            NSNumber(value: channelCount),
        ]
        let outputShape: [NSNumber] = [
            NSNumber(value: batchCount),
            NSNumber(value: sx),
            NSNumber(value: (sy / 2) + 1),
            NSNumber(value: channelCount),
        ]
        let input = graph.placeholder(shape: inputShape, dataType: .float32, name: "preparedMass")

        let forwardDescriptor = MPSGraphFFTDescriptor()
        forwardDescriptor.inverse = false
        forwardDescriptor.scalingMode = .none
        let output = graph.realToHermiteanFFT(input, axes: [1, 2], descriptor: forwardDescriptor, name: "flowForwardFFT")

        let deviceDescriptor = MPSGraphDevice(mtlDevice: device)
        let shapedType = MPSGraphShapedType(shape: inputShape, dataType: .float32)
        let executable = graph.compile(
            with: deviceDescriptor,
            feeds: [input: shapedType],
            targetTensors: [output],
            targetOperations: nil,
            compilationDescriptor: nil
        )
        return (executable, inputShape, outputShape)
    }

    private static func buildInverseFFTExecutable(
        device: MTLDevice,
        batchCount: Int,
        parameterCount: Int,
        sx: Int,
        sy: Int
    ) throws -> (
        executable: MPSGraphExecutable,
        inputShape: [NSNumber],
        outputShape: [NSNumber]
    ) {
        let graph = MPSGraph()
        let inputShape: [NSNumber] = [
            NSNumber(value: batchCount),
            NSNumber(value: sx),
            NSNumber(value: (sy / 2) + 1),
            NSNumber(value: parameterCount),
        ]
        let outputShape: [NSNumber] = [
            NSNumber(value: batchCount),
            NSNumber(value: sx),
            NSNumber(value: sy),
            NSNumber(value: parameterCount),
        ]
        let input = graph.placeholder(shape: inputShape, dataType: .complexFloat32, name: "kernelResponse")
        let inverseDescriptor = MPSGraphFFTDescriptor()
        inverseDescriptor.inverse = true
        inverseDescriptor.scalingMode = .size
        let output = graph.HermiteanToRealFFT(input, axes: [1, 2], descriptor: inverseDescriptor, name: "flowInverseFFT")
        let deviceDescriptor = MPSGraphDevice(mtlDevice: device)
        let shapedType = MPSGraphShapedType(shape: inputShape, dataType: .complexFloat32)
        let executable = graph.compile(
            with: deviceDescriptor,
            feeds: [input: shapedType],
            targetTensors: [output],
            targetOperations: nil,
            compilationDescriptor: nil
        )
        return (executable, inputShape, outputShape)
    }

    static func kernelSource(
        kernelCount: Int,
        parameterCount: Int,
        batchCount: Int,
        channelCount: Int,
        kernelBatchCount: Int,
        summaryPartialGroupCount: Int,
        sx: Int,
        sy: Int,
        dt: Float,
        dd: Int,
        sigma: Float,
        thetaA: Float,
        n: Int,
        useTorus: Bool,
        alphaMode: String,
        flowClip: String,
        parameterFieldMode: FlowLeniaParameterFieldMode,
        reintegrateParams: Bool,
        parameterMixMode: ParameterMixMode
    ) -> String {
        let clipMax = min(1.0 as Float, sigma * 2.0)
        let maxAdvection = Float(dd) - sigma
        let areaScale = Float(1.0 / Double(4.0 * sigma * sigma))
        let alphaPerChannel = alphaMode == "per_channel"
        let clipFlow = flowClip == "always" ||
            (flowClip == "params_only" && parameterFieldMode == .localizedGrowthParameters)
        let alphaPowerExpression: String
        switch n {
        case 0:
            alphaPowerExpression = "1.0f"
        case 1:
            alphaPowerExpression = "alphaBase"
        case 2:
            alphaPowerExpression = "alphaBase * alphaBase"
        case 3:
            alphaPowerExpression = "alphaBase * alphaBase * alphaBase"
        case 4:
            alphaPowerExpression = "alphaBase * alphaBase * alphaBase * alphaBase"
        default:
            alphaPowerExpression = "metal::pow(alphaBase, \(Float(n))f)"
        }
        let channelIndices = Array(0..<channelCount)
        let matterMapAccumulation = channelIndices.map { channel in
            "            total += mass[massBase + \(channel)] * matterWeights[\(channel)];"
        }.joined(separator: "\n")
        let growthChannelDeclarations = channelIndices.map { channel in
            "            float channelSum\(channel) = 0.0f;"
        }.joined(separator: "\n")
        let growthChannelAccumulations = channelIndices.map { channel in
            "                channelSum\(channel) += contribution * outputWeights[\(channel) * kKernelCount + k];"
        }.joined(separator: "\n")
        let growthChannelWrites = channelIndices.map { channel in
            "            u[outputBase + \(channel)] = channelSum\(channel);"
        }.joined(separator: "\n")
        let wallPotentialWrites = channelIndices.map { channel in
            "            u[outputBase + \(channel)] += potential;"
        }.joined(separator: "\n")
        let totalMassDeclarations = channelIndices.map { channel in
            "            float totalMass\(channel) = 0.0f;"
        }.joined(separator: "\n")
        let reintegrateMassWrites = channelIndices.map { channel in
            "            nextMass[outputMassBase + \(channel)] = totalMass\(channel) * kAreaScale;"
        }.joined(separator: "\n")
        let usesLocalTorusDistance = useTorus && maxAdvection >= 0
            && Float(min(sx, sy)) * 0.5 > Float(dd) + maxAdvection
        let reintegrateDistanceBody = if usesLocalTorusDistance {
            """
                                float dY = metal::fabs(float(dy) - clippedY);
                                float dX = metal::fabs(float(dx) - clippedX);
            """
        } else if useTorus {
            """
                                float murY = float(srcY) + 0.5f + clippedY;
                                float murX = float(srcX) + 0.5f + clippedX;
                                float dY = metal::fabs(targetY - murY);
                                float dX = metal::fabs(targetX - murX);
                                dY = metal::fmin(dY, metal::fabs(targetY - (murY - float(kSY))));
                                dY = metal::fmin(dY, metal::fabs(targetY - (murY + float(kSY))));
                                dX = metal::fmin(dX, metal::fabs(targetX - (murX - float(kSX))));
                                dX = metal::fmin(dX, metal::fabs(targetX - (murX + float(kSX))));
            """
        } else {
            """
                                float murY = metal::fmin(
                                    metal::fmax(float(srcY) + 0.5f + clippedY, kSigma),
                                    float(kSY) - kSigma
                                );
                                float murX = metal::fmin(
                                    metal::fmax(float(srcX) + 0.5f + clippedX, kSigma),
                                    float(kSX) - kSigma
                                );
                                float dY = metal::fabs(targetY - murY);
                                float dX = metal::fabs(targetX - murX);
            """
        }
        let flowChannelBodies = channelIndices.map { channel in
            """
            {
                float u00 = sampleU(u, batch, x - 1, y - 1, \(channel));
                float u01 = sampleU(u, batch, x - 1, y, \(channel));
                float u02 = sampleU(u, batch, x - 1, y + 1, \(channel));
                float u10 = sampleU(u, batch, x, y - 1, \(channel));
                float u12 = sampleU(u, batch, x, y + 1, \(channel));
                float u20 = sampleU(u, batch, x + 1, y - 1, \(channel));
                float u21 = sampleU(u, batch, x + 1, y, \(channel));
                float u22 = sampleU(u, batch, x + 1, y + 1, \(channel));
                float gxU = (u00 + 2.0f * u10 + u20) - (u02 + 2.0f * u12 + u22);
                float gyU = (u00 + 2.0f * u01 + u02) - (u20 + 2.0f * u21 + u22);
                float alphaSource = kAlphaPerChannel ? mass[massBase + \(channel)] : matterCenter;
                float alphaBase = alphaSource / kThetaA;
                float alpha = \(alphaPowerExpression);
                alpha = metal::fmin(metal::fmax(alpha, 0.0f), 1.0f);
                float flowY = gyU * (1.0f - alpha) - gyA * alpha;
                float flowX = gxU * (1.0f - alpha) - gxA * alpha;
                if (kClipFlow) {
                    flowY = metal::fmin(metal::fmax(flowY, -kMaxAdvection), kMaxAdvection);
                    flowX = metal::fmin(metal::fmax(flowX, -kMaxAdvection), kMaxAdvection);
                }
                int outputBase = flowIndex(batch, x, y, \(channel));
                flow[outputBase] = flowY;
                flow[outputBase + 1] = flowX;
            }
            """
        }.joined(separator: "\n")
        let reintegrateMassChannelBodies = channelIndices.map { channel in
            """
                        {
                            float sourceMass = mass[sourceMassBase + \(channel)];
                            if (sourceMass > 0.0f) {
                                int sourceFlowIndex = sourceFlowBase + \(channel * 2);
                                float flowY = flow[sourceFlowIndex];
                                float flowX = flow[sourceFlowIndex + 1];
                                float clippedY = metal::fmin(metal::fmax(flowY * kDt, -kMaxAdvection), kMaxAdvection);
                                float clippedX = metal::fmin(metal::fmax(flowX * kDt, -kMaxAdvection), kMaxAdvection);

            \(reintegrateDistanceBody)

                                float szY = metal::fmin(metal::fmax(0.5f - dY + kSigma, 0.0f), kClipMax);
                                float szX = metal::fmin(metal::fmax(0.5f - dX + kSigma, 0.0f), kClipMax);
                                float transportedMass = sourceMass * szY * szX;
                                totalMass\(channel) += transportedMass;
                                if (kReintegrateParams) {
                                    candidateWeight += transportedMass;
                                }
                            }
                        }
            """
        }.joined(separator: "\n")
        let reintegrateCandidateChannelBodies = channelIndices.map { channel in
            """
                        {
                            float sourceMass = mass[sourceMassBase + \(channel)];
                            if (sourceMass > 0.0f) {
                                int sourceFlowIndex = sourceFlowBase + \(channel * 2);
                                float flowY = flow[sourceFlowIndex];
                                float flowX = flow[sourceFlowIndex + 1];
                                float clippedY = metal::fmin(metal::fmax(flowY * kDt, -kMaxAdvection), kMaxAdvection);
                                float clippedX = metal::fmin(metal::fmax(flowX * kDt, -kMaxAdvection), kMaxAdvection);
            \(reintegrateDistanceBody)
                                float szY = metal::fmin(metal::fmax(0.5f - dY + kSigma, 0.0f), kClipMax);
                                float szX = metal::fmin(metal::fmax(0.5f - dX + kSigma, 0.0f), kClipMax);
                                candidateWeight += sourceMass * szY * szX;
                            }
                        }
            """
        }.joined(separator: "\n")

        return """
        #include <metal_stdlib>
        using namespace metal;

        constant int kBatchCount = \(batchCount);
        constant int kKernelCount = \(kernelCount);
        constant int kParamCount = \(parameterCount);
        constant int kChannelCount = \(channelCount);
        constant int kReducedY = \((sy / 2) + 1);
        constant int kKernelBatchCount = \(kernelBatchCount);
        constant int kSX = \(sx);
        constant int kSY = \(sy);
        constant float kThetaA = \(thetaA)f;
        constant float kDt = \(dt)f;
        constant float kSigma = \(sigma)f;
        constant float kClipMax = \(clipMax)f;
        constant float kMaxAdvection = \(maxAdvection)f;
        constant float kAreaScale = \(areaScale)f;
        constant bool kUseTorus = \(useTorus ? "true" : "false");
        constant bool kAlphaPerChannel = \(alphaPerChannel ? "true" : "false");
        constant bool kClipFlow = \(clipFlow ? "true" : "false");
        constant bool kUsesLocalizedGrowthParameters = \(parameterFieldMode == .localizedGrowthParameters ? "true" : "false");
        constant bool kReintegrateParams = \(reintegrateParams ? "true" : "false");
        constant int kParameterMixMode = \(parameterMixMode.rawValue);
        constant uint kSummaryThreads = \(summaryThreadCount)u;
        constant uint kSummaryChunkSpan = \(Self.summaryChunkSpan)u;
        constant uint kSummaryPartialGroups = \(summaryPartialGroupCount)u;

        struct ReintegrateUniforms {
            uint mixSeed;
            uint mixStep;
        };

        inline int massIndex(int batch, int x, int y, int channel) {
            return (((batch * kSX) + x) * kSY + y) * kChannelCount + channel;
        }

        inline int paramIndex(int batch, int x, int y, int k) {
            return (((batch * kSX) + x) * kSY + y) * kParamCount + k;
        }

        inline int scalarIndex(int batch, int x, int y) {
            return (batch * kSX + x) * kSY + y;
        }

        inline int uIndex(int batch, int x, int y, int channel) {
            return (((batch * kSX) + x) * kSY + y) * kChannelCount + channel;
        }

        inline int flowIndex(int batch, int x, int y, int channel) {
            return ((((batch * kSX) + x) * kSY + y) * kChannelCount + channel) * 2;
        }

        inline int spectrumIndex(int batch, int x, int y, int channel) {
            return (((batch * kSX) + x) * kReducedY + y) * kChannelCount + channel;
        }

        inline int gatheredSpectrumIndex(int batch, int x, int y, int k) {
            return (((batch * kSX) + x) * kReducedY + y) * kKernelCount + k;
        }

        inline int kernelSpectrumIndex(int kernelBatch, int x, int y, int k) {
            return (((kernelBatch * kSX) + x) * kReducedY + y) * kKernelCount + k;
        }

        inline int ukIndex(int batch, int x, int y, int k) {
            return (((batch * kSX) + x) * kSY + y) * kKernelCount + k;
        }

        inline bool inBounds(int x, int y) {
            return x >= 0 && x < kSX && y >= 0 && y < kSY;
        }

        inline int wrappedX(int x) {
            if (x < 0) {
                return x + kSX;
            }
            if (x >= kSX) {
                return x - kSX;
            }
            return x;
        }

        inline int wrappedY(int y) {
            if (y < 0) {
                return y + kSY;
            }
            if (y >= kSY) {
                return y - kSY;
            }
            return y;
        }

        inline float sampleMatter(device const float *matter, int batch, int x, int y) {
            if (kUseTorus) {
                return matter[scalarIndex(batch, wrappedX(x), wrappedY(y))];
            }
            if (!inBounds(x, y)) {
                return 0.0f;
            }
            return matter[scalarIndex(batch, x, y)];
        }

        inline float sampleU(device const float *u, int batch, int x, int y, int channel) {
            if (kUseTorus) {
                return u[uIndex(batch, wrappedX(x), wrappedY(y), channel)];
            }
            if (!inBounds(x, y)) {
                return 0.0f;
            }
            return u[uIndex(batch, x, y, channel)];
        }

        inline uint splitmix32(uint value) {
            value += 0x9e3779b9u;
            value = (value ^ (value >> 16)) * 0x85ebca6bu;
            value = (value ^ (value >> 13)) * 0xc2b2ae35u;
            return value ^ (value >> 16);
        }

        inline float randomUnit(uint seed, uint step, int batch, int x, int y) {
            uint value = seed;
            value ^= step * 0x632be5abu;
            value ^= uint(batch + 1) * 0x85157af5u;
            value ^= uint(x + 1) * 0x58f38dedu;
            value ^= uint(y + 1) * 0x9e3779b9u;
            return max(float(splitmix32(value) & 0x00ffffffu) / 16777216.0f, 1.0e-7f);
        }

        kernel void flowMetalGatherKernelSpectra(
            device const float2 *channelSpectra [[buffer(0)]],
            device const float2 *kernelSpectrum [[buffer(1)]],
            device const int *c0Idxs [[buffer(2)]],
            device float2 *gatheredSpectra [[buffer(3)]],
            uint3 gid [[thread_position_in_grid]]
        ) {
            int packedY = int(gid.x);
            int batch = int(gid.z);
            if (int(gid.y) >= kSX || packedY >= kReducedY * kKernelCount || batch >= kBatchCount) {
                return;
            }
            int x = int(gid.y);
            int y = packedY / kKernelCount;
            int k = packedY - y * kKernelCount;
            int sourceChannel = c0Idxs[k];
            int kernelBatch = kKernelBatchCount == 1 ? 0 : batch;
            float2 source = channelSpectra[spectrumIndex(batch, x, y, sourceChannel)];
            float2 kernelValue = kernelSpectrum[kernelSpectrumIndex(kernelBatch, x, y, k)];
            gatheredSpectra[gatheredSpectrumIndex(batch, x, y, k)] = float2(
                source.x * kernelValue.x - source.y * kernelValue.y,
                source.x * kernelValue.y + source.y * kernelValue.x
            );
        }

        kernel void flowMetalGrowthReduce(
            device const float *uk [[buffer(0)]],
            device const float *params [[buffer(1)]],
            device const float *m [[buffer(2)]],
            device const float *s [[buffer(3)]],
            device const float *outputWeights [[buffer(4)]],
            device float *u [[buffer(5)]],
            device const float *mass [[buffer(6)]],
            device const float *matterWeights [[buffer(7)]],
            device float *matter [[buffer(8)]],
            uint3 gid [[thread_position_in_grid]]
        ) {
            if (int(gid.y) >= kSX || int(gid.x) >= kSY || int(gid.z) >= kBatchCount) {
                return;
            }
            int batch = int(gid.z);
            int x = int(gid.y);
            int y = int(gid.x);
        \(growthChannelDeclarations)
            int paramBase = paramIndex(batch, x, y, 0);
            for (int k = 0; k < kKernelCount; ++k) {
                int kernelIndex = batch * kKernelCount + k;
                float localM = kUsesLocalizedGrowthParameters ? params[paramBase + k] : m[kernelIndex];
                float localS = kUsesLocalizedGrowthParameters ? params[paramBase + kKernelCount + k] : s[kernelIndex];
                float localH = kUsesLocalizedGrowthParameters ? params[paramBase + 2 * kKernelCount + k] : params[paramBase + k];
                float diff = (uk[ukIndex(batch, x, y, k)] - localM) / localS;
                float contribution = (2.0f * metal::exp(-0.5f * diff * diff) - 1.0f) * localH;
        \(growthChannelAccumulations)
            }
            int outputBase = uIndex(batch, x, y, 0);
        \(growthChannelWrites)
            float total = 0.0f;
            int massBase = massIndex(batch, x, y, 0);
        \(matterMapAccumulation)
            matter[scalarIndex(batch, x, y)] = total;
        }

        kernel void flowMetalAddWallPotential(
            device float *u [[buffer(0)]],
            device const float *wallPotential [[buffer(1)]],
            uint3 gid [[thread_position_in_grid]]
        ) {
            if (int(gid.y) >= kSX || int(gid.x) >= kSY || int(gid.z) >= kBatchCount) {
                return;
            }
            int batch = int(gid.z);
            int x = int(gid.y);
            int y = int(gid.x);
            float potential = wallPotential[scalarIndex(batch, x, y)];
            int outputBase = uIndex(batch, x, y, 0);
        \(wallPotentialWrites)
        }

        kernel void flowMetalFlowFromScalarField(
            device const float *u [[buffer(0)]],
            device const float *matter [[buffer(1)]],
            device float *flow [[buffer(2)]],
            device const float *mass [[buffer(3)]],
            uint3 gid [[thread_position_in_grid]]
        ) {
            if (int(gid.y) >= kSX || int(gid.x) >= kSY || int(gid.z) >= kBatchCount) {
                return;
            }
            int batch = int(gid.z);
            int x = int(gid.y);
            int y = int(gid.x);

            float matterGrid[3][3];
            for (int ox = 0; ox < 3; ++ox) {
                int sampleX = x + ox - 1;
                for (int oy = 0; oy < 3; ++oy) {
                    int sampleY = y + oy - 1;
                    matterGrid[ox][oy] = sampleMatter(matter, batch, sampleX, sampleY);
                }
            }

            float gxA = (matterGrid[0][0] + 2.0f * matterGrid[1][0] + matterGrid[2][0]) - (matterGrid[0][2] + 2.0f * matterGrid[1][2] + matterGrid[2][2]);
            float gyA = (matterGrid[0][0] + 2.0f * matterGrid[0][1] + matterGrid[0][2]) - (matterGrid[2][0] + 2.0f * matterGrid[2][1] + matterGrid[2][2]);
            int massBase = massIndex(batch, x, y, 0);
            float matterCenter = matterGrid[1][1];
        \(flowChannelBodies)
        }

        kernel void flowMetalReintegrateAverage(
            device const float *mass [[buffer(0)]],
            device const float *params [[buffer(1)]],
            device const float *flow [[buffer(2)]],
            device float *nextMass [[buffer(3)]],
            device float *nextParams [[buffer(4)]],
            constant ReintegrateUniforms &uniforms [[buffer(5)]],
            uint3 gid [[thread_position_in_grid]]
        ) {
            if (int(gid.y) >= kSX || int(gid.x) >= kSY || int(gid.z) >= kBatchCount) {
                return;
            }
            int batch = int(gid.z);
            int x = int(gid.y);
            int y = int(gid.x);
            float paramSum[kParamCount];
            if (kReintegrateParams) {
                for (int k = 0; k < kParamCount; ++k) {
                    paramSum[k] = 0.0f;
                }
            }
        \(totalMassDeclarations)

            float totalWeight = 0.0f;
            float maxCandidateWeight = kParameterMixMode == 0 ? 0.0f : -1.0e30f;
            float targetY = float(y) + 0.5f;
            float targetX = float(x) + 0.5f;

            for (int dx = -\(dd); dx <= \(dd); ++dx) {
                for (int dy = -\(dd); dy <= \(dd); ++dy) {
                    int srcX = x - dx;
                    int srcY = y - dy;
                    srcX = wrappedX(srcX);
                    srcY = wrappedY(srcY);

                    float candidateWeight = 0.0f;
                    int sourceMassBase = massIndex(batch, srcX, srcY, 0);
                    int sourceFlowBase = flowIndex(batch, srcX, srcY, 0);
        \(reintegrateMassChannelBodies)
                    if (kReintegrateParams) {
                        totalWeight += candidateWeight;
                        if (kParameterMixMode == 0 && candidateWeight > 0.0f) {
                            int paramBase = paramIndex(batch, srcX, srcY, 0);
                            for (int k = 0; k < kParamCount; ++k) {
                                paramSum[k] += params[paramBase + k] * candidateWeight;
                            }
                        }
                        if (kParameterMixMode != 0) {
                            maxCandidateWeight = metal::fmax(maxCandidateWeight, candidateWeight);
                        }
                    }
                }
            }

            int outputMassBase = massIndex(batch, x, y, 0);
        \(reintegrateMassWrites)
            if (!kReintegrateParams) {
                return;
            }

            int outputScalarIndex = scalarIndex(batch, x, y);
            float denom = totalWeight > 1.0e-10f ? totalWeight : 1.0e-10f;
            int outputParamBase = outputScalarIndex * kParamCount;
            if (kParameterMixMode == 0) {
                for (int k = 0; k < kParamCount; ++k) {
                    nextParams[outputParamBase + k] = paramSum[k] / denom;
                }
                return;
            }

            float expTotal = 0.0f;
            for (int dx = -\(dd); dx <= \(dd); ++dx) {
                for (int dy = -\(dd); dy <= \(dd); ++dy) {
                    int srcX = x - dx;
                    int srcY = y - dy;
                    srcX = wrappedX(srcX);
                    srcY = wrappedY(srcY);
                    float candidateWeight = 0.0f;
                    int sourceMassBase = massIndex(batch, srcX, srcY, 0);
                    int sourceFlowBase = flowIndex(batch, srcX, srcY, 0);
        \(reintegrateCandidateChannelBodies)
                    expTotal += metal::exp(candidateWeight - maxCandidateWeight);
                }
            }

            float threshold = randomUnit(uniforms.mixSeed, uniforms.mixStep, batch, x, y) * expTotal;
            float cumulative = 0.0f;
            int chosenX = x;
            int chosenY = y;
            bool chosen = false;
            for (int dx = -\(dd); dx <= \(dd); ++dx) {
                for (int dy = -\(dd); dy <= \(dd); ++dy) {
                    int srcX = x - dx;
                    int srcY = y - dy;
                    srcX = wrappedX(srcX);
                    srcY = wrappedY(srcY);
                    float candidateWeight = 0.0f;
                    int sourceMassBase = massIndex(batch, srcX, srcY, 0);
                    int sourceFlowBase = flowIndex(batch, srcX, srcY, 0);
        \(reintegrateCandidateChannelBodies)
                    cumulative += metal::exp(candidateWeight - maxCandidateWeight);
                    if (!chosen && cumulative >= threshold) {
                        chosenX = srcX;
                        chosenY = srcY;
                        chosen = true;
                    }
                }
            }
            int chosenParamBase = paramIndex(batch, chosenX, chosenY, 0);
            for (int k = 0; k < kParamCount; ++k) {
                nextParams[outputParamBase + k] = params[chosenParamBase + k];
            }
        }

        kernel void flowMetalMassSummaryPass1Partial(
            device const float *mass [[buffer(0)]],
            device const float *occupancyThresholdPtr [[buffer(1)]],
            device float *partialTotalMass [[buffer(2)]],
            device float *partialSumSquares [[buffer(3)]],
            device float *partialEnergy [[buffer(4)]],
            device float *partialWeightedX [[buffer(5)]],
            device float *partialWeightedY [[buffer(6)]],
            device float *partialOccupancyCount [[buffer(7)]],
            device const float *channelWeights [[buffer(8)]],
            uint tid [[thread_index_in_threadgroup]],
            uint lane [[thread_index_in_simdgroup]],
            uint simdGroup [[simdgroup_index_in_threadgroup]],
            uint threadsPerSimdgroup [[threads_per_simdgroup]],
            uint3 groupPos [[threadgroup_position_in_grid]]
        ) {
            int batch = int(groupPos.z);
            uint partialGroup = groupPos.x;
            if (batch >= kBatchCount || partialGroup >= kSummaryPartialGroups) {
                return;
            }

            float occupancyThreshold = occupancyThresholdPtr[0];
            threadgroup float totalScratch[kSummaryThreads];
            threadgroup float sumSqScratch[kSummaryThreads];
            threadgroup float energyScratch[kSummaryThreads];
            threadgroup float weightedXScratch[kSummaryThreads];
            threadgroup float weightedYScratch[kSummaryThreads];
            threadgroup float occupancyScratch[kSummaryThreads];

            float localTotal = 0.0f;
            float localSumSq = 0.0f;
            float localEnergy = 0.0f;
            float localWeightedX = 0.0f;
            float localWeightedY = 0.0f;
            float localOccupancy = 0.0f;
            int spatialCount = kSX * kSY;
            uint chunkStart = partialGroup * kSummaryChunkSpan;
            uint chunkEnd = min(chunkStart + kSummaryChunkSpan, uint(spatialCount));
            for (uint linear = chunkStart + tid; linear < chunkEnd; linear += kSummaryThreads) {
                int x = int(linear) / kSY;
                int y = int(linear) - x * kSY;
                float value = 0.0f;
                for (int channel = 0; channel < kChannelCount; ++channel) {
                    float weight = channelWeights[channel];
                    float channelMass = mass[massIndex(batch, x, y, channel)];
                    value += channelMass * weight;
                    localEnergy += channelMass * channelMass * weight;
                }
                localTotal += value;
                localSumSq += value * value;
                localWeightedX += value * float(x);
                localWeightedY += value * float(y);
                localOccupancy += value > occupancyThreshold ? 1.0f : 0.0f;
            }

            localTotal = simd_sum(localTotal);
            localSumSq = simd_sum(localSumSq);
            localEnergy = simd_sum(localEnergy);
            localWeightedX = simd_sum(localWeightedX);
            localWeightedY = simd_sum(localWeightedY);
            localOccupancy = simd_sum(localOccupancy);
            if (lane == 0u) {
                totalScratch[simdGroup] = localTotal;
                sumSqScratch[simdGroup] = localSumSq;
                energyScratch[simdGroup] = localEnergy;
                weightedXScratch[simdGroup] = localWeightedX;
                weightedYScratch[simdGroup] = localWeightedY;
                occupancyScratch[simdGroup] = localOccupancy;
            }
            threadgroup_barrier(mem_flags::mem_threadgroup);

            uint simdGroupCount = (kSummaryThreads + threadsPerSimdgroup - 1u) / threadsPerSimdgroup;
            float reducedTotal = tid < simdGroupCount ? totalScratch[tid] : 0.0f;
            float reducedSumSq = tid < simdGroupCount ? sumSqScratch[tid] : 0.0f;
            float reducedEnergy = tid < simdGroupCount ? energyScratch[tid] : 0.0f;
            float reducedWeightedX = tid < simdGroupCount ? weightedXScratch[tid] : 0.0f;
            float reducedWeightedY = tid < simdGroupCount ? weightedYScratch[tid] : 0.0f;
            float reducedOccupancy = tid < simdGroupCount ? occupancyScratch[tid] : 0.0f;
            reducedTotal = simd_sum(reducedTotal);
            reducedSumSq = simd_sum(reducedSumSq);
            reducedEnergy = simd_sum(reducedEnergy);
            reducedWeightedX = simd_sum(reducedWeightedX);
            reducedWeightedY = simd_sum(reducedWeightedY);
            reducedOccupancy = simd_sum(reducedOccupancy);

            if (tid == 0u) {
                int partialIndex = batch * int(kSummaryPartialGroups) + int(partialGroup);
                partialTotalMass[partialIndex] = reducedTotal;
                partialSumSquares[partialIndex] = reducedSumSq;
                partialEnergy[partialIndex] = reducedEnergy;
                partialWeightedX[partialIndex] = reducedWeightedX;
                partialWeightedY[partialIndex] = reducedWeightedY;
                partialOccupancyCount[partialIndex] = reducedOccupancy;
            }
        }

        kernel void flowMetalMassSummaryPass1Finalize(
            device const float *partialTotalMass [[buffer(0)]],
            device const float *partialSumSquares [[buffer(1)]],
            device const float *partialEnergy [[buffer(2)]],
            device const float *partialWeightedX [[buffer(3)]],
            device const float *partialWeightedY [[buffer(4)]],
            device const float *partialOccupancyCount [[buffer(5)]],
            device float *totalMass [[buffer(6)]],
            device float *sumSquares [[buffer(7)]],
            device float *energy [[buffer(8)]],
            device float *weightedX [[buffer(9)]],
            device float *weightedY [[buffer(10)]],
            device float *occupancyCount [[buffer(11)]],
            uint tid [[thread_index_in_threadgroup]],
            uint lane [[thread_index_in_simdgroup]],
            uint simdGroup [[simdgroup_index_in_threadgroup]],
            uint threadsPerSimdgroup [[threads_per_simdgroup]],
            uint3 groupPos [[threadgroup_position_in_grid]]
        ) {
            int batch = int(groupPos.z);
            if (batch >= kBatchCount) {
                return;
            }

            threadgroup float totalScratch[kSummaryThreads];
            threadgroup float sumSqScratch[kSummaryThreads];
            threadgroup float energyScratch[kSummaryThreads];
            threadgroup float weightedXScratch[kSummaryThreads];
            threadgroup float weightedYScratch[kSummaryThreads];
            threadgroup float occupancyScratch[kSummaryThreads];

            float localTotal = 0.0f;
            float localSumSq = 0.0f;
            float localEnergy = 0.0f;
            float localWeightedX = 0.0f;
            float localWeightedY = 0.0f;
            float localOccupancy = 0.0f;
            for (uint partialIndex = tid; partialIndex < kSummaryPartialGroups; partialIndex += kSummaryThreads) {
                int index = batch * int(kSummaryPartialGroups) + int(partialIndex);
                localTotal += partialTotalMass[index];
                localSumSq += partialSumSquares[index];
                localEnergy += partialEnergy[index];
                localWeightedX += partialWeightedX[index];
                localWeightedY += partialWeightedY[index];
                localOccupancy += partialOccupancyCount[index];
            }

            localTotal = simd_sum(localTotal);
            localSumSq = simd_sum(localSumSq);
            localEnergy = simd_sum(localEnergy);
            localWeightedX = simd_sum(localWeightedX);
            localWeightedY = simd_sum(localWeightedY);
            localOccupancy = simd_sum(localOccupancy);
            if (lane == 0u) {
                totalScratch[simdGroup] = localTotal;
                sumSqScratch[simdGroup] = localSumSq;
                energyScratch[simdGroup] = localEnergy;
                weightedXScratch[simdGroup] = localWeightedX;
                weightedYScratch[simdGroup] = localWeightedY;
                occupancyScratch[simdGroup] = localOccupancy;
            }
            threadgroup_barrier(mem_flags::mem_threadgroup);

            uint simdGroupCount = (kSummaryThreads + threadsPerSimdgroup - 1u) / threadsPerSimdgroup;
            float reducedTotal = tid < simdGroupCount ? totalScratch[tid] : 0.0f;
            float reducedSumSq = tid < simdGroupCount ? sumSqScratch[tid] : 0.0f;
            float reducedEnergy = tid < simdGroupCount ? energyScratch[tid] : 0.0f;
            float reducedWeightedX = tid < simdGroupCount ? weightedXScratch[tid] : 0.0f;
            float reducedWeightedY = tid < simdGroupCount ? weightedYScratch[tid] : 0.0f;
            float reducedOccupancy = tid < simdGroupCount ? occupancyScratch[tid] : 0.0f;
            reducedTotal = simd_sum(reducedTotal);
            reducedSumSq = simd_sum(reducedSumSq);
            reducedEnergy = simd_sum(reducedEnergy);
            reducedWeightedX = simd_sum(reducedWeightedX);
            reducedWeightedY = simd_sum(reducedWeightedY);
            reducedOccupancy = simd_sum(reducedOccupancy);

            if (tid == 0u) {
                totalMass[batch] = reducedTotal;
                sumSquares[batch] = reducedSumSq;
                energy[batch] = reducedEnergy;
                weightedX[batch] = reducedWeightedX;
                weightedY[batch] = reducedWeightedY;
                occupancyCount[batch] = reducedOccupancy;
            }
        }

        kernel void flowMetalMassSummaryGyrationPartial(
            device const float *mass [[buffer(0)]],
            device const float *totalMass [[buffer(1)]],
            device const float *weightedX [[buffer(2)]],
            device const float *weightedY [[buffer(3)]],
            device float *partialGyration [[buffer(4)]],
            device const float *channelWeights [[buffer(5)]],
            uint tid [[thread_index_in_threadgroup]],
            uint lane [[thread_index_in_simdgroup]],
            uint simdGroup [[simdgroup_index_in_threadgroup]],
            uint threadsPerSimdgroup [[threads_per_simdgroup]],
            uint3 groupPos [[threadgroup_position_in_grid]]
        ) {
            int batch = int(groupPos.z);
            uint partialGroup = groupPos.x;
            if (batch >= kBatchCount || partialGroup >= kSummaryPartialGroups) {
                return;
            }

            float total = metal::max(totalMass[batch], 1.0e-6f);
            float centerX = weightedX[batch] / total;
            float centerY = weightedY[batch] / total;
            threadgroup float gyrationScratch[kSummaryThreads];
            float localGyration = 0.0f;
            int spatialCount = kSX * kSY;
            uint chunkStart = partialGroup * kSummaryChunkSpan;
            uint chunkEnd = min(chunkStart + kSummaryChunkSpan, uint(spatialCount));
            for (uint linear = chunkStart + tid; linear < chunkEnd; linear += kSummaryThreads) {
                int x = int(linear) / kSY;
                int y = int(linear) - x * kSY;
                float value = 0.0f;
                for (int channel = 0; channel < kChannelCount; ++channel) {
                    value += mass[massIndex(batch, x, y, channel)] * channelWeights[channel];
                }
                float dx = metal::fabs(float(x) - centerX);
                float dy = metal::fabs(float(y) - centerY);
                dx = metal::fmin(dx, float(kSX) - dx);
                dy = metal::fmin(dy, float(kSY) - dy);
                localGyration += value * (dx * dx + dy * dy);
            }

            localGyration = simd_sum(localGyration);
            if (lane == 0u) {
                gyrationScratch[simdGroup] = localGyration;
            }
            threadgroup_barrier(mem_flags::mem_threadgroup);

            uint simdGroupCount = (kSummaryThreads + threadsPerSimdgroup - 1u) / threadsPerSimdgroup;
            float reducedGyration = tid < simdGroupCount ? gyrationScratch[tid] : 0.0f;
            reducedGyration = simd_sum(reducedGyration);
            if (tid == 0u) {
                int partialIndex = batch * int(kSummaryPartialGroups) + int(partialGroup);
                partialGyration[partialIndex] = reducedGyration;
            }
        }

        kernel void flowMetalMassSummaryGyrationFinalize(
            device const float *partialGyration [[buffer(0)]],
            device const float *totalMass [[buffer(1)]],
            device float *gyration [[buffer(2)]],
            uint tid [[thread_index_in_threadgroup]],
            uint lane [[thread_index_in_simdgroup]],
            uint simdGroup [[simdgroup_index_in_threadgroup]],
            uint threadsPerSimdgroup [[threads_per_simdgroup]],
            uint3 groupPos [[threadgroup_position_in_grid]]
        ) {
            int batch = int(groupPos.z);
            if (batch >= kBatchCount) {
                return;
            }

            threadgroup float gyrationScratch[kSummaryThreads];
            float localGyration = 0.0f;
            for (uint partialIndex = tid; partialIndex < kSummaryPartialGroups; partialIndex += kSummaryThreads) {
                int index = batch * int(kSummaryPartialGroups) + int(partialIndex);
                localGyration += partialGyration[index];
            }

            localGyration = simd_sum(localGyration);
            if (lane == 0u) {
                gyrationScratch[simdGroup] = localGyration;
            }
            threadgroup_barrier(mem_flags::mem_threadgroup);

            uint simdGroupCount = (kSummaryThreads + threadsPerSimdgroup - 1u) / threadsPerSimdgroup;
            float reducedGyration = tid < simdGroupCount ? gyrationScratch[tid] : 0.0f;
            reducedGyration = simd_sum(reducedGyration);
            if (tid == 0u) {
                float total = metal::max(totalMass[batch], 1.0e-6f);
                gyration[batch] = reducedGyration / total;
            }
        }
        """
    }
}

final class FlowLeniaMetalFullBridge: @unchecked Sendable {
    private let config: BatchedConfig
    private let kernels: CompiledKernels
    private let wallPotential: MLXArray?
    private let parameterFieldMode: FlowLeniaParameterFieldMode
    private let parameterCount: Int
    private let kernelBatchCount: Int
    private let device: MTLDevice
    private let commandQueue: MTLCommandQueue

    private var batchCount = 0
    private var pipeline: FlowLeniaMetalFullPipeline?
    private var preparedMassBuffer: MTLBuffer?
    private var paramsBuffer: MTLBuffer?
    private var nextMassBuffer: MTLBuffer?
    private var nextParamsBuffer: MTLBuffer?

    init(
        config: BatchedConfig,
        kernels: CompiledKernels,
        wallPotential: MLXArray? = nil,
        parameterFieldMode: FlowLeniaParameterFieldMode = .kernelGain
    ) {
        self.config = config
        self.kernels = kernels
        self.wallPotential = wallPotential
        self.parameterFieldMode = parameterFieldMode
        self.parameterCount = parameterFieldMode.parameterCount(
            kernelCount: FlowLeniaMetalFullPipeline.parameterCount(for: kernels)
        )
        self.kernelBatchCount = FlowLeniaMetalFullPipeline.kernelBatchCount(for: kernels)
        let metal = FlowLeniaMetalFullPipeline.makeDeviceAndQueue()
        self.device = metal.0
        self.commandQueue = metal.1
    }

    func stagedStep(
        mass: MLXArray,
        params: MLXArray,
        captureStages: Bool = false,
        profileStages: Bool = false
    ) -> FlowSandboxMetalStagedStepResult {
        let totalStart = ContinuousClock.now
        let batchSize = mass.shape[0]
        guard kernelBatchCount == 1 || kernelBatchCount == batchSize else {
            preconditionFailure("Flow Metal full bridge requires either shared kernels or one kernel set per batch element.")
        }
        ensureResources(batchCount: batchSize)
        guard let pipeline,
              let preparedMassBuffer,
              let paramsBuffer,
              let nextMassBuffer,
              let nextParamsBuffer else {
            preconditionFailure("Expected Flow Metal full bridge resources.")
        }

        let prepareStart = totalStart
        let preparedMass = mass.contiguous()
        let paramField = params.contiguous()
        let preparedMassValues = preparedMass.asArray(Float.self)
        let paramValues = paramField.asArray(Float.self)
        FlowLeniaMetalFullPipeline.writeFloats(preparedMassValues, to: preparedMassBuffer)
        FlowLeniaMetalFullPipeline.writeFloats(paramValues, to: paramsBuffer)
        let prepareMs = flowSandboxDurationMs(prepareStart.duration(to: ContinuousClock.now))

        let stageProfile: FlowLeniaMetalFullPipeline.StageProfile?
        if profileStages {
            stageProfile = pipeline.profileStep(
                preparedMassBuffer: preparedMassBuffer,
                paramsBuffer: paramsBuffer,
                nextMassBuffer: nextMassBuffer,
                nextParamsBuffer: nextParamsBuffer
            )
        } else {
            pipeline.runStep(
                preparedMassBuffer: preparedMassBuffer,
                paramsBuffer: paramsBuffer,
                nextMassBuffer: nextMassBuffer,
                nextParamsBuffer: nextParamsBuffer
            )
            stageProfile = nil
        }

        let nextMassValues = FlowLeniaMetalFullPipeline.readFloats(
            from: nextMassBuffer,
            count: batchSize * config.sx * config.sy * config.channels
        )
        let nextParamValues = FlowLeniaMetalFullPipeline.readFloats(
            from: nextParamsBuffer,
            count: batchSize * config.sx * config.sy * parameterCount
        )

        let nextMass = MLXArray(nextMassValues).reshaped([batchSize, config.sx, config.sy, config.channels])
        let nextParams = MLXArray(nextParamValues).reshaped([batchSize, config.sx, config.sy, parameterCount])

        let capturedStages: FlowSandboxMetalStageOutputs?
        if captureStages {
            let ukValues = pipeline.readUK(batchCount: batchSize)
            let scalarValues = pipeline.readScalarField(batchCount: batchSize)
            let flowValues = pipeline.readFlow(batchCount: batchSize)
            capturedStages = FlowSandboxMetalStageOutputs(
                preparedMass: preparedMass,
                uk: MLXArray(ukValues).reshaped([batchSize, config.sx, config.sy, pipeline.kernelCount]),
                scalarField: MLXArray(scalarValues).reshaped([batchSize, config.sx, config.sy]),
                flow: MLXArray(flowValues).reshaped([batchSize, config.sx, config.sy, 2]).expandedDimensions(axis: -1)
            )
        } else {
            capturedStages = nil
        }

        let timings: FlowSandboxMetalStageTimings?
        if let stageProfile {
            timings = FlowSandboxMetalStageTimings(
                prepareMs: prepareMs,
                fftMs: stageProfile.fftMs,
                growthReduceMs: stageProfile.growthReduceMs,
                flowMs: stageProfile.flowMs,
                reintegrateMs: stageProfile.reintegrateMs,
                totalMs: max(
                    flowSandboxDurationMs(totalStart.duration(to: ContinuousClock.now)),
                    prepareMs + stageProfile.totalMs
                )
            )
        } else if profileStages {
            timings = FlowSandboxMetalStageTimings(
                prepareMs: prepareMs,
                fftMs: 0,
                growthReduceMs: 0,
                flowMs: 0,
                reintegrateMs: 0,
                totalMs: flowSandboxDurationMs(totalStart.duration(to: ContinuousClock.now))
            )
        } else {
            timings = nil
        }

        return FlowSandboxMetalStagedStepResult(
            nextMass: nextMass,
            nextParams: nextParams,
            stages: capturedStages,
            timings: timings
        )
    }

    private func ensureResources(batchCount: Int) {
        guard self.batchCount != batchCount else {
            return
        }
        self.batchCount = batchCount
        self.pipeline = FlowLeniaMetalFullPipeline(
            config: config,
            kernels: kernels,
            batchCount: batchCount,
            device: device,
            commandQueue: commandQueue,
            wallPotential: wallPotential,
            parameterFieldMode: parameterFieldMode
        )

        let cellCount = batchCount * config.sx * config.sy
        let massBytes = cellCount * config.channels * MemoryLayout<Float>.stride
        let paramBytes = cellCount * parameterCount * MemoryLayout<Float>.stride
        preparedMassBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
            device: device,
            length: massBytes,
            label: "flow-metal.bridge.mass.\(batchCount)"
        )
        paramsBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
            device: device,
            length: paramBytes,
            label: "flow-metal.bridge.params.\(batchCount)"
        )
        nextMassBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
            device: device,
            length: massBytes,
            label: "flow-metal.bridge.nextMass.\(batchCount)"
        )
        nextParamsBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
            device: device,
            length: paramBytes,
            label: "flow-metal.bridge.nextParams.\(batchCount)"
        )
    }
}
