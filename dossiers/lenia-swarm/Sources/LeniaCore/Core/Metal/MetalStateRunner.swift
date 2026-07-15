import Foundation
import Metal
import MLX

final class FlowLeniaMetalFullStateRunner {
    private typealias BufferCopy = (source: MTLBuffer, destination: MTLBuffer, length: Int)

    let config: BatchedConfig
    let parameterCount: Int
    let batchCount: Int
    let channelCount: Int

    private let device: MTLDevice
    private let commandQueue: MTLCommandQueue
    private let pipeline: FlowLeniaMetalFullPipeline
    private let summaryReducer: FlowLeniaMetalSummaryReducer
    private let scalarSummaryReducer: FlowLeniaMetalScalarSummaryReducer
    private let wallMaskPipeline: MTLComputePipelineState
    private let parameterPatchPipeline: MTLComputePipelineState
    private let channelFieldPipeline: MTLComputePipelineState
    private let scalarPatchPipeline: MTLComputePipelineState
    private let scalarFieldMaskPipeline: MTLComputePipelineState
    private let foodDynamicsPipeline: MTLComputePipelineState
    private let zeroStatePatchPipeline: MTLComputePipelineState
    private let insertStatePatchPipeline: MTLComputePipelineState
    private let massMapPipeline: MTLComputePipelineState

    private var currentMassBuffer: MTLBuffer
    private var currentParamsBuffer: MTLBuffer
    private var nextMassBuffer: MTLBuffer
    private var nextParamsBuffer: MTLBuffer
    private var wallMaskBuffers: FlowLeniaMetalFullPipeline.UploadBuffers?
    private let massMapBuffer: MTLBuffer
    private lazy var massTransferBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
        device: device,
        length: batchCount * config.sx * config.sy * channelCount * MemoryLayout<Float>.stride,
        label: "flow-metal.state.mass-transfer"
    )
    private lazy var paramsTransferBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
        device: device,
        length: batchCount * config.sx * config.sy * parameterCount * MemoryLayout<Float>.stride,
        label: "flow-metal.state.params-transfer"
    )
    private let massMapTransferBuffer: MTLBuffer
    private let massMapWeightsBuffer: MTLBuffer
    private var currentMatterWeights: [Float]
    private var wallMaskEnabled = false
    private let reintegrateParams: Bool
    private var currentMixStep = 0
    private var staticChannelFields: [FlowLeniaMetalChannelFieldBuffer] = []
    private var foodState: FlowLeniaMetalFoodStateBuffer?
    private(set) var massObservationSynchronizationCount = 0

    init(
        config: BatchedConfig,
        kernels: CompiledKernels,
        batchCount: Int,
        wallPotential: MLXArray? = nil,
        matterWeights: [Float]? = nil,
        reintegrateParams: Bool = true,
        parameterFieldMode: FlowLeniaParameterFieldMode = .kernelGain,
        parameterMix: String = "avg",
        mixSeed: Int? = nil
    ) {
        self.config = config
        let kernelCount = FlowLeniaMetalFullPipeline.parameterCount(for: kernels)
        self.parameterCount = parameterFieldMode.parameterCount(kernelCount: kernelCount)
        self.batchCount = batchCount
        self.channelCount = config.channels
        self.reintegrateParams = reintegrateParams
        let resolvedMatterWeights = Self.resolvedMatterWeights(
            weights: matterWeights,
            channelCount: config.channels
        )
        self.currentMatterWeights = resolvedMatterWeights
        let kernelBatchCount = FlowLeniaMetalFullPipeline.kernelBatchCount(for: kernels)
        guard kernelBatchCount == 1 || kernelBatchCount == batchCount else {
            preconditionFailure("FlowLeniaMetalFullStateRunner requires either shared kernels or one kernel set per batch element.")
        }
        let metal = FlowLeniaMetalFullPipeline.makeDeviceAndQueue()
        self.device = metal.0
        self.commandQueue = metal.1
        self.pipeline = FlowLeniaMetalFullPipeline(
            config: config,
            kernels: kernels,
            batchCount: batchCount,
            device: device,
            commandQueue: commandQueue,
            wallPotential: wallPotential,
            matterWeights: resolvedMatterWeights,
            parameterFieldMode: parameterFieldMode,
            reintegrateParams: reintegrateParams,
            parameterMix: parameterMix,
            mixSeed: mixSeed
        )
        self.summaryReducer = FlowLeniaMetalSummaryReducer(
            config: config,
            batchCount: batchCount,
            device: device,
            library: self.pipeline.library
        )
        let wallLibrary = FlowLeniaMetalFullPipeline.makeLibrary(
            device: device,
            source: Self.wallMaskKernelSource(
                parameterCount: self.parameterCount,
                channelCount: self.channelCount,
                batchCount: batchCount,
                sx: config.sx,
                sy: config.sy
            )
        )
        self.scalarSummaryReducer = FlowLeniaMetalScalarSummaryReducer(
            batchCount: batchCount,
            partialGroupCount: FlowLeniaMetalFullPipeline.summaryPartialGroupCount(sx: config.sx, sy: config.sy),
            device: device,
            commandQueue: commandQueue,
            library: wallLibrary
        )
        self.wallMaskPipeline = FlowLeniaMetalFullPipeline.makePipeline(
            device: device,
            library: wallLibrary,
            name: "flowMetalApplyWallMask"
        )
        self.parameterPatchPipeline = FlowLeniaMetalFullPipeline.makePipeline(
            device: device,
            library: wallLibrary,
            name: "flowMetalApplyParameterPatch"
        )
        self.channelFieldPipeline = FlowLeniaMetalFullPipeline.makePipeline(
            device: device,
            library: wallLibrary,
            name: "flowMetalOverwriteChannelField"
        )
        self.scalarPatchPipeline = FlowLeniaMetalFullPipeline.makePipeline(
            device: device,
            library: wallLibrary,
            name: "flowMetalApplyScalarPatch"
        )
        self.scalarFieldMaskPipeline = FlowLeniaMetalFullPipeline.makePipeline(
            device: device,
            library: wallLibrary,
            name: "flowMetalApplyScalarFieldMask"
        )
        self.foodDynamicsPipeline = FlowLeniaMetalFullPipeline.makePipeline(
            device: device,
            library: wallLibrary,
            name: "flowMetalApplyFoodDynamics"
        )
        self.zeroStatePatchPipeline = FlowLeniaMetalFullPipeline.makePipeline(
            device: device,
            library: wallLibrary,
            name: "flowMetalZeroStatePatch"
        )
        self.insertStatePatchPipeline = FlowLeniaMetalFullPipeline.makePipeline(
            device: device,
            library: wallLibrary,
            name: "flowMetalInsertStatePatch"
        )
        self.massMapPipeline = FlowLeniaMetalFullPipeline.makePipeline(
            device: device,
            library: wallLibrary,
            name: "flowMetalBuildMassMap"
        )

        let cellCount = batchCount * config.sx * config.sy
        let massBytes = cellCount * channelCount * MemoryLayout<Float>.stride
        let paramBytes = cellCount * parameterCount * MemoryLayout<Float>.stride
        let scalarBytes = cellCount * MemoryLayout<Float>.stride
        self.currentMassBuffer = FlowLeniaMetalFullPipeline.makePrivateBuffer(
            device: device,
            length: massBytes,
            label: "flow-metal.state.mass"
        )
        self.currentParamsBuffer = FlowLeniaMetalFullPipeline.makePrivateBuffer(
            device: device,
            length: paramBytes,
            label: "flow-metal.state.params"
        )
        self.nextMassBuffer = FlowLeniaMetalFullPipeline.makePrivateBuffer(
            device: device,
            length: massBytes,
            label: "flow-metal.state.nextMass"
        )
        self.nextParamsBuffer = FlowLeniaMetalFullPipeline.makePrivateBuffer(
            device: device,
            length: paramBytes,
            label: "flow-metal.state.nextParams"
        )
        self.massMapBuffer = FlowLeniaMetalFullPipeline.makePrivateBuffer(
            device: device,
            length: scalarBytes,
            label: "flow-metal.state.mass-map"
        )
        self.massMapTransferBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
            device: device,
            length: scalarBytes,
            label: "flow-metal.state.mass-map-transfer"
        )
        self.massMapWeightsBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
            device: device,
            length: channelCount * MemoryLayout<Float>.stride,
            label: "flow-metal.state.mass-map-weights"
        )
    }

    func setState(mass: MLXArray, params: MLXArray) {
        uploadState(mass: mass, params: params, configurationUploads: [])
    }

    func reset(
        mass: MLXArray,
        params: MLXArray,
        wallMask: MLXArray?,
        staticChannelFields: [FlowLeniaMetalChannelField],
        food: FlowLeniaMetalFoodState?
    ) {
        if wallMask == nil, staticChannelFields.isEmpty, food == nil {
            wallMaskEnabled = false
            self.staticChannelFields = []
            foodState = nil
            uploadState(mass: mass, params: params, configurationUploads: [])
            return
        }
        let wallMaskUpload = prepareWallMask(wallMask)
        let preparedFields = prepareStaticChannelFields(staticChannelFields)
        let preparedFood = prepareFoodState(food)

        wallMaskEnabled = wallMask != nil
        self.staticChannelFields = preparedFields.fields
        foodState = preparedFood.state

        var uploads = preparedFields.uploads
        if let wallMaskUpload {
            uploads.append(wallMaskUpload)
        }
        if let foodUpload = preparedFood.upload {
            uploads.append(foodUpload)
        }
        uploadState(mass: mass, params: params, configurationUploads: uploads)
    }

    private func uploadState(
        mass: MLXArray,
        params: MLXArray,
        configurationUploads: [BufferCopy]
    ) {
        guard mass.shape.count == 4, mass.shape[0] == batchCount, mass.shape[1] == config.sx, mass.shape[2] == config.sy, mass.shape[3] == channelCount else {
            preconditionFailure("FlowLeniaMetalFullStateRunner expects mass with shape [batch, sx, sy, channels].")
        }
        guard params.shape.count == 4, params.shape[0] == batchCount, params.shape[1] == config.sx, params.shape[2] == config.sy, params.shape[3] == parameterCount else {
            preconditionFailure("FlowLeniaMetalFullStateRunner expects params with shape [batch, sx, sy, parameterCount].")
        }

        let contiguousMass = mass.asType(Float.self).contiguous()
        let contiguousParams = params.asType(Float.self).contiguous()
        eval(contiguousMass, contiguousParams)
        let stateUploads: [BufferCopy]
        if let massSourceBuffer = contiguousMass.asMTLBuffer(device: device, noCopy: true),
           let paramsSourceBuffer = contiguousParams.asMTLBuffer(device: device, noCopy: true) {
            stateUploads = [
                (massSourceBuffer, currentMassBuffer, contiguousMass.nbytes),
                (paramsSourceBuffer, currentParamsBuffer, contiguousParams.nbytes),
            ]
        } else {
            let massValues = contiguousMass.asArray(Float.self)
            let paramValues = contiguousParams.asArray(Float.self)
            FlowLeniaMetalFullPipeline.writeFloats(massValues, to: massTransferBuffer)
            FlowLeniaMetalFullPipeline.writeFloats(paramValues, to: paramsTransferBuffer)
            stateUploads = [
                (massTransferBuffer, currentMassBuffer, contiguousMass.nbytes),
                (paramsTransferBuffer, currentParamsBuffer, contiguousParams.nbytes),
            ]
        }
        let uploads = configurationUploads.isEmpty
            ? stateUploads
            : stateUploads + configurationUploads
        withExtendedLifetime((contiguousMass, contiguousParams)) {
            submitAndWait(label: "flow-metal.state.upload") { commandBuffer in
                encodeCopies(uploads, on: commandBuffer)
                for field in staticChannelFields {
                    encodeChannelFieldOverwrite(
                        on: commandBuffer,
                        massBuffer: currentMassBuffer,
                        field: field
                    )
                }
                if foodState != nil {
                    encodeFoodFieldOverwrite(on: commandBuffer, massBuffer: currentMassBuffer)
                }
                if wallMaskEnabled {
                    encodeWallMask(
                        on: commandBuffer,
                        massBuffer: currentMassBuffer,
                        paramsBuffer: currentParamsBuffer
                    )
                    if foodState != nil {
                        encodeFoodMask(on: commandBuffer)
                    }
                }
            }
        }
        currentMixStep = 0
    }

    func updateKernels(_ kernels: CompiledKernels) {
        pipeline.updateKernels(kernels)
    }

    func setWallPotential(_ wallPotential: MLXArray?) {
        pipeline.updateWallPotential(wallPotential)
    }

    func setMatterWeights(_ weights: [Float]?) {
        let resolved = Self.resolvedMatterWeights(
            weights: weights,
            channelCount: channelCount
        )
        guard resolved != currentMatterWeights else {
            return
        }
        currentMatterWeights = resolved
        pipeline.updateMatterWeights(resolved)
    }

    func applyParameterPatch(
        x0: Int,
        y0: Int,
        size: Int,
        deltas: [Float],
        clip: [Float]?
    ) {
        applyParameterPatch(
            FlowLeniaMetalParameterPatchBatch(
                origins: Array(repeating: SIMD2<Int32>(Int32(x0), Int32(y0)), count: batchCount),
                size: size,
                deltas: deltas,
                clip: clip
            )
        )
    }

    func applyParameterPatch(
        origins: [SIMD2<Int32>],
        size: Int,
        deltas: [Float],
        clip: [Float]?
    ) {
        applyParameterPatch(
            FlowLeniaMetalParameterPatchBatch(
                origins: origins,
                size: size,
                deltas: deltas,
                clip: clip
            )
        )
    }

    func applyParameterPatch(_ patch: FlowLeniaMetalParameterPatchBatch) {
        guard patch.size > 0 else {
            return
        }
        submitAndWait(label: "flow-metal.state.paramPatch") { commandBuffer in
            encodeParameterPatch(
                on: commandBuffer,
                paramsBuffer: currentParamsBuffer,
                patch: patch
            )
        }
    }

    func applyZeroStatePatch(origins: [SIMD2<Int32>], size: Int) {
        guard size > 0 else {
            return
        }
        let insertionOrigins = Array(repeating: SIMD2<Int32>(Int32(-size), Int32(-size)), count: batchCount)
        applyDissipationPatch(
            FlowLeniaMetalDissipationBatch(
                removalOrigins: origins,
                insertionOrigins: insertionOrigins,
                size: size,
                insertedMass: [Float](repeating: 0, count: batchCount * size * size * channelCount),
                insertedParams: [Float](repeating: 0, count: batchCount * parameterCount)
            )
        )
    }

    private func applyDissipationPatch(_ patch: FlowLeniaMetalDissipationBatch) {
        guard patch.size > 0 else {
            return
        }
        submitAndWait(label: "flow-metal.state.dissipationPatch") { commandBuffer in
            encodeDissipationPatch(
                on: commandBuffer,
                massBuffer: currentMassBuffer,
                paramsBuffer: currentParamsBuffer,
                patch: patch
            )
        }
    }

    func step(count: Int = 1) {
        step(
            count: count,
            preStepParameterPatches: [:],
            postStepParameterPatches: [:],
            postStepScalarPatches: [:],
            postStepDissipationPatches: [:]
        )
    }

    func step(
        count: Int,
        preStepParameterPatches: [Int: [FlowLeniaMetalParameterPatchBatch]],
        postStepParameterPatches: [Int: [FlowLeniaMetalParameterPatchBatch]],
        postStepScalarPatches: [Int: [FlowLeniaMetalScalarPatchBatch]] = [:],
        postStepDissipationPatches: [Int: [FlowLeniaMetalDissipationBatch]] = [:]
    ) {
        let stepCount = max(count, 0)
        guard stepCount > 0 else {
            return
        }
        stepChunk(
            count: stepCount,
            preStepParameterPatches: preStepParameterPatches,
            postStepParameterPatches: postStepParameterPatches,
            postStepScalarPatches: postStepScalarPatches,
            postStepDissipationPatches: postStepDissipationPatches
        )
    }

    func materializeState() -> (mass: MLXArray, params: MLXArray) {
        let cellCount = batchCount * config.sx * config.sy
        let massCount = cellCount * channelCount
        let paramCount = cellCount * parameterCount
        submitAndWait(label: "flow-metal.state.readback") { commandBuffer in
            encodeCopies(
                [
                    (currentMassBuffer, massTransferBuffer, massCount * MemoryLayout<Float>.stride),
                    (currentParamsBuffer, paramsTransferBuffer, paramCount * MemoryLayout<Float>.stride),
                ],
                on: commandBuffer
            )
        }
        let massValues = FlowLeniaMetalFullPipeline.readFloats(from: massTransferBuffer, count: massCount)
        let paramValues = FlowLeniaMetalFullPipeline.readFloats(from: paramsTransferBuffer, count: paramCount)
        return (
            MLXArray(massValues).reshaped([batchCount, config.sx, config.sy, channelCount]),
            MLXArray(paramValues).reshaped([batchCount, config.sx, config.sy, parameterCount])
        )
    }

    func materializeMass() -> MLXArray {
        let cellCount = batchCount * config.sx * config.sy
        let massValues = readFloats(
            from: currentMassBuffer,
            into: massTransferBuffer,
            count: cellCount * channelCount,
            label: "flow-metal.state.mass"
        )
        return MLXArray(massValues).reshaped([batchCount, config.sx, config.sy, channelCount])
    }

    func materializeMassMap(channelWeights: [Float]? = nil) -> MLXArray {
        submitAndWait(label: "flow-metal.state.mass-map") { commandBuffer in
            encodeMassMap(on: commandBuffer, channelWeights: channelWeights)
        }
        massObservationSynchronizationCount += 1
        return readMassMap()
    }

    func observeMass(
        occupancyThreshold: Float,
        includeGyration: Bool,
        channelWeights: [Float]? = nil,
        materializeMap: Bool
    ) -> (summary: FlowLeniaMetalMassSummary, massMap: MLXArray?) {
        submitAndWait(label: "flow-metal.state.mass-observation") { commandBuffer in
            summaryReducer.encodeSummary(
                on: commandBuffer,
                massBuffer: currentMassBuffer,
                occupancyThreshold: occupancyThreshold,
                includeGyration: includeGyration,
                channelWeights: channelWeights
            )
            if materializeMap {
                encodeMassMap(on: commandBuffer, channelWeights: channelWeights)
            }
        }
        massObservationSynchronizationCount += 1
        return (
            summaryReducer.readSummary(includeGyration: includeGyration),
            materializeMap ? readMassMap() : nil
        )
    }

    private func encodeMassMap(on commandBuffer: MTLCommandBuffer, channelWeights: [Float]?) {
        let weights = channelWeights ?? Array(repeating: 1.0, count: channelCount)
        guard weights.count == channelCount else {
            preconditionFailure("FlowLeniaMetalFullStateRunner mass-map weights must match the configured channel count.")
        }
        FlowLeniaMetalFullPipeline.writeFloats(weights, to: massMapWeightsBuffer)

        guard let encoder = commandBuffer.makeComputeCommandEncoder() else {
            preconditionFailure("Failed to create Flow Metal mass-map encoder.")
        }
        encoder.setComputePipelineState(massMapPipeline)
        encoder.setBuffer(currentMassBuffer, offset: 0, index: 0)
        encoder.setBuffer(massMapBuffer, offset: 0, index: 1)
        encoder.setBuffer(massMapWeightsBuffer, offset: 0, index: 2)
        encoder.dispatchThreads(
            MTLSize(width: config.sx, height: config.sy, depth: batchCount),
            threadsPerThreadgroup: MTLSize(width: 16, height: 16, depth: 1)
        )
        encoder.endEncoding()

        guard let blit = commandBuffer.makeBlitCommandEncoder() else {
            preconditionFailure("Failed to create Flow Metal mass-map readback encoder.")
        }
        let byteCount = batchCount * config.sx * config.sy * MemoryLayout<Float>.stride
        blit.copy(from: massMapBuffer, sourceOffset: 0, to: massMapTransferBuffer, destinationOffset: 0, size: byteCount)
        blit.endEncoding()
    }

    private func readMassMap() -> MLXArray {
        let values = FlowLeniaMetalFullPipeline.readFloats(from: massMapTransferBuffer, count: batchCount * config.sx * config.sy)
        return MLXArray(values).reshaped([batchCount, config.sx, config.sy])
    }

    func materializeParams() -> MLXArray {
        let cellCount = batchCount * config.sx * config.sy
        let paramValues = readFloats(
            from: currentParamsBuffer,
            into: paramsTransferBuffer,
            count: cellCount * parameterCount,
            label: "flow-metal.state.params"
        )
        return MLXArray(paramValues).reshaped([batchCount, config.sx, config.sy, parameterCount])
    }

    func materializeFood() -> MLXArray? {
        guard let foodState else {
            return nil
        }
        let cellCount = batchCount * config.sx * config.sy
        let foodValues = readFloats(
            from: foodState.buffer,
            into: foodState.transferBuffer,
            count: cellCount,
            label: "flow-metal.state.food"
        )
        return MLXArray(foodValues).reshaped([batchCount, config.sx, config.sy])
    }

    func summarizeFoodMass() -> [Float]? {
        guard let foodState else {
            return nil
        }
        return scalarSummaryReducer.summarize(buffer: foodState.buffer)
    }

    func summarizeMass(
        occupancyThreshold: Float,
        includeGyration: Bool,
        channelWeights: [Float]? = nil
    ) -> FlowLeniaMetalMassSummary {
        observeMass(
            occupancyThreshold: occupancyThreshold,
            includeGyration: includeGyration,
            channelWeights: channelWeights,
            materializeMap: false
        ).summary
    }

    func profileCurrentStep() -> FlowSandboxMetalStageTimings {
        var wallMaskMs = 0.0
        let stageProfile = pipeline.profileStep(
            preparedMassBuffer: currentMassBuffer,
            paramsBuffer: currentParamsBuffer,
            nextMassBuffer: nextMassBuffer,
            nextParamsBuffer: nextParamsBuffer
        )
        if wallMaskEnabled {
            let wallMaskStart = ContinuousClock.now
            submitAndWait(label: "flow-metal.state.mask-profile") { commandBuffer in
                encodeWallMask(
                    on: commandBuffer,
                    massBuffer: nextMassBuffer,
                    paramsBuffer: nextParamsBuffer
                )
            }
            wallMaskMs = flowSandboxDurationMs(wallMaskStart.duration(to: ContinuousClock.now))
        }
        return FlowSandboxMetalStageTimings(
            prepareMs: 0.0,
            fftMs: stageProfile.fftMs,
            growthReduceMs: stageProfile.growthReduceMs,
            flowMs: stageProfile.flowMs,
            reintegrateMs: stageProfile.reintegrateMs + wallMaskMs,
            totalMs: stageProfile.totalMs + wallMaskMs
        )
    }

    private func stepChunk(
        count: Int,
        preStepParameterPatches: [Int: [FlowLeniaMetalParameterPatchBatch]],
        postStepParameterPatches: [Int: [FlowLeniaMetalParameterPatchBatch]],
        postStepScalarPatches: [Int: [FlowLeniaMetalScalarPatchBatch]],
        postStepDissipationPatches: [Int: [FlowLeniaMetalDissipationBatch]]
    ) {
        if pipeline.requiresSegmentedStepEncoding {
            stepChunkSegmented(
                count: count,
                preStepParameterPatches: preStepParameterPatches,
                postStepParameterPatches: postStepParameterPatches,
                postStepScalarPatches: postStepScalarPatches,
                postStepDissipationPatches: postStepDissipationPatches
            )
            return
        }

        guard let commandBuffer = commandQueue.makeCommandBuffer() else {
            preconditionFailure("Failed to create Flow Metal state runner command buffer.")
        }
        commandBuffer.label = "flow-metal.state.step.\(count)"
        var readMassBuffer = currentMassBuffer
        var readParamsBuffer = currentParamsBuffer
        var writeMassBuffer = nextMassBuffer
        var writeParamsBuffer = nextParamsBuffer
        for stepIndex in 1...count {
            for field in staticChannelFields {
                encodeChannelFieldOverwrite(
                    on: commandBuffer,
                    massBuffer: readMassBuffer,
                    field: field
                )
            }
            if foodState != nil {
                encodeFoodFieldOverwrite(
                    on: commandBuffer,
                    massBuffer: readMassBuffer
                )
            }
            if let patches = preStepParameterPatches[stepIndex] {
                for patch in patches {
                    encodeParameterPatch(
                        on: commandBuffer,
                        paramsBuffer: readParamsBuffer,
                        patch: patch
                    )
                }
            }
            pipeline.encodeStep(
                on: commandBuffer,
                preparedMassBuffer: readMassBuffer,
                paramsBuffer: readParamsBuffer,
                nextMassBuffer: writeMassBuffer,
                nextParamsBuffer: writeParamsBuffer,
                mixStep: currentMixStep + stepIndex - 1
            )
            if let patches = postStepParameterPatches[stepIndex] {
                for patch in patches {
                    encodeParameterPatch(
                        on: commandBuffer,
                        paramsBuffer: writeParamsBuffer,
                        patch: patch
                    )
                }
            }
            if let dissipationPatches = postStepDissipationPatches[stepIndex] {
                for dissipation in dissipationPatches {
                    encodeDissipationPatch(
                        on: commandBuffer,
                        massBuffer: writeMassBuffer,
                        paramsBuffer: writeParamsBuffer,
                        patch: dissipation
                    )
                }
            }
            if foodState != nil {
                encodeFoodDynamics(
                    on: commandBuffer,
                    massBuffer: writeMassBuffer
                )
            }
            if let scalarPatches = postStepScalarPatches[stepIndex],
               let foodState {
                for patch in scalarPatches {
                    encodeScalarPatch(
                        on: commandBuffer,
                        fieldBuffer: foodState.buffer,
                        patch: patch
                    )
                }
                if !scalarPatches.isEmpty {
                    encodeFoodFieldOverwrite(
                        on: commandBuffer,
                        massBuffer: writeMassBuffer
                    )
                }
            }
            if wallMaskEnabled {
                encodeWallMask(
                    on: commandBuffer,
                    massBuffer: writeMassBuffer,
                    paramsBuffer: writeParamsBuffer
                )
                if foodState != nil {
                    encodeFoodMask(on: commandBuffer)
                }
            }
            swap(&readMassBuffer, &writeMassBuffer)
            if reintegrateParams {
                swap(&readParamsBuffer, &writeParamsBuffer)
            }
        }
        FlowLeniaMetalFullPipeline.commitAndWait(commandBuffer, label: "flow-metal.state.step.\(count)")
        currentMassBuffer = readMassBuffer
        currentParamsBuffer = readParamsBuffer
        nextMassBuffer = writeMassBuffer
        nextParamsBuffer = writeParamsBuffer
        currentMixStep += count
    }

    private func stepChunkSegmented(
        count: Int,
        preStepParameterPatches: [Int: [FlowLeniaMetalParameterPatchBatch]],
        postStepParameterPatches: [Int: [FlowLeniaMetalParameterPatchBatch]],
        postStepScalarPatches: [Int: [FlowLeniaMetalScalarPatchBatch]],
        postStepDissipationPatches: [Int: [FlowLeniaMetalDissipationBatch]]
    ) {
        var readMassBuffer = currentMassBuffer
        var readParamsBuffer = currentParamsBuffer
        var writeMassBuffer = nextMassBuffer
        var writeParamsBuffer = nextParamsBuffer

        for stepIndex in 1...count {
            let prePatches = preStepParameterPatches[stepIndex] ?? []
            let hasPreWork = !staticChannelFields.isEmpty || foodState != nil || !prePatches.isEmpty
            if hasPreWork {
                submitAndWait(label: "flow-metal.state.segmented.pre.\(stepIndex)") { commandBuffer in
                    for field in staticChannelFields {
                        encodeChannelFieldOverwrite(
                            on: commandBuffer,
                            massBuffer: readMassBuffer,
                            field: field
                        )
                    }
                    if foodState != nil {
                        encodeFoodFieldOverwrite(
                            on: commandBuffer,
                            massBuffer: readMassBuffer
                        )
                    }
                    for patch in prePatches {
                        encodeParameterPatch(
                            on: commandBuffer,
                            paramsBuffer: readParamsBuffer,
                            patch: patch
                        )
                    }
                }
            }

            pipeline.runSegmentedStep(
                preparedMassBuffer: readMassBuffer,
                paramsBuffer: readParamsBuffer,
                nextMassBuffer: writeMassBuffer,
                nextParamsBuffer: writeParamsBuffer,
                mixStep: currentMixStep + stepIndex - 1
            )

            let postPatches = postStepParameterPatches[stepIndex] ?? []
            let dissipationPatches = postStepDissipationPatches[stepIndex] ?? []
            let scalarPatches = postStepScalarPatches[stepIndex] ?? []
            let hasPostWork = !postPatches.isEmpty || !dissipationPatches.isEmpty || foodState != nil || wallMaskEnabled
            if hasPostWork {
                submitAndWait(label: "flow-metal.state.segmented.post.\(stepIndex)") { commandBuffer in
                    for patch in postPatches {
                        encodeParameterPatch(
                            on: commandBuffer,
                            paramsBuffer: writeParamsBuffer,
                            patch: patch
                        )
                    }
                    for dissipation in dissipationPatches {
                        encodeDissipationPatch(
                            on: commandBuffer,
                            massBuffer: writeMassBuffer,
                            paramsBuffer: writeParamsBuffer,
                            patch: dissipation
                        )
                    }
                    if foodState != nil {
                        encodeFoodDynamics(
                            on: commandBuffer,
                            massBuffer: writeMassBuffer
                        )
                    }
                    if let foodState {
                        for patch in scalarPatches {
                            encodeScalarPatch(
                                on: commandBuffer,
                                fieldBuffer: foodState.buffer,
                                patch: patch
                            )
                        }
                        if !scalarPatches.isEmpty {
                            encodeFoodFieldOverwrite(
                                on: commandBuffer,
                                massBuffer: writeMassBuffer
                            )
                        }
                    }
                    if wallMaskEnabled {
                        encodeWallMask(
                            on: commandBuffer,
                            massBuffer: writeMassBuffer,
                            paramsBuffer: writeParamsBuffer
                        )
                        if foodState != nil {
                            encodeFoodMask(on: commandBuffer)
                        }
                    }
                }
            }

            swap(&readMassBuffer, &writeMassBuffer)
            if reintegrateParams {
                swap(&readParamsBuffer, &writeParamsBuffer)
            }
        }

        currentMassBuffer = readMassBuffer
        currentParamsBuffer = readParamsBuffer
        nextMassBuffer = writeMassBuffer
        nextParamsBuffer = writeParamsBuffer
        currentMixStep += count
    }

    private func encodeChannelFieldOverwrite(
        on commandBuffer: MTLCommandBuffer,
        massBuffer: MTLBuffer,
        field: FlowLeniaMetalChannelFieldBuffer
    ) {
        encodeChannelFieldOverwrite(
            on: commandBuffer,
            massBuffer: massBuffer,
            fieldBuffer: field.buffer,
            channelIndex: field.channelIndex
        )
    }

    private func encodeChannelFieldOverwrite(
        on commandBuffer: MTLCommandBuffer,
        massBuffer: MTLBuffer,
        fieldBuffer: MTLBuffer,
        channelIndex: Int
    ) {
        var uniforms = ChannelFieldUniforms(channelIndex: Int32(channelIndex))
        guard let encoder = commandBuffer.makeComputeCommandEncoder() else {
            preconditionFailure("Failed to create Flow Metal channel field encoder.")
        }
        encoder.setComputePipelineState(channelFieldPipeline)
        encoder.setBuffer(fieldBuffer, offset: 0, index: 0)
        encoder.setBuffer(massBuffer, offset: 0, index: 1)
        withUnsafeBytes(of: &uniforms) { rawUniforms in
            encoder.setBytes(rawUniforms.baseAddress!, length: rawUniforms.count, index: 2)
        }
        let threadWidth = min(16, max(1, channelFieldPipeline.threadExecutionWidth))
        let maxHeight = max(1, channelFieldPipeline.maxTotalThreadsPerThreadgroup / threadWidth)
        let threadHeight = min(16, maxHeight)
        let threadsPerGroup = MTLSize(width: threadWidth, height: threadHeight, depth: 1)
        let threads = MTLSize(width: config.sx, height: config.sy, depth: batchCount)
        encoder.dispatchThreads(threads, threadsPerThreadgroup: threadsPerGroup)
        encoder.endEncoding()
    }

    private func encodeScalarPatch(
        on commandBuffer: MTLCommandBuffer,
        fieldBuffer: MTLBuffer,
        patch: FlowLeniaMetalScalarPatchBatch
    ) {
        guard patch.origins.count == batchCount else {
            preconditionFailure(
                "FlowLeniaMetalFullStateRunner scalar patch expects \(batchCount) batch origins, got \(patch.origins.count)."
            )
        }
        let patchOrigins = patch.origins.map { ParameterPatchOrigin(x0: $0.x, y0: $0.y) }
        guard let originBuffer = device.makeBuffer(
            length: patchOrigins.count * MemoryLayout<ParameterPatchOrigin>.stride,
            options: .storageModeShared
        ) else {
            preconditionFailure("Failed to allocate Flow Metal scalar patch origin buffer.")
        }
        originBuffer.label = "flow-metal.state.scalarPatch.origins"
        _ = patchOrigins.withUnsafeBytes { rawOrigins in
            memcpy(originBuffer.contents(), rawOrigins.baseAddress, rawOrigins.count)
        }
        var uniforms = ScalarPatchUniforms(size: Int32(patch.size), value: patch.value)
        guard let encoder = commandBuffer.makeComputeCommandEncoder() else {
            preconditionFailure("Failed to create Flow Metal scalar patch encoder.")
        }
        encoder.setComputePipelineState(scalarPatchPipeline)
        encoder.setBuffer(originBuffer, offset: 0, index: 0)
        encoder.setBuffer(fieldBuffer, offset: 0, index: 1)
        withUnsafeBytes(of: &uniforms) { rawUniforms in
            encoder.setBytes(rawUniforms.baseAddress!, length: rawUniforms.count, index: 2)
        }
        let threadWidth = min(8, max(1, scalarPatchPipeline.threadExecutionWidth))
        let maxHeight = max(1, scalarPatchPipeline.maxTotalThreadsPerThreadgroup / threadWidth)
        let threadHeight = min(8, maxHeight)
        let threadsPerGroup = MTLSize(width: threadWidth, height: threadHeight, depth: 1)
        let threads = MTLSize(width: patch.size, height: patch.size, depth: batchCount)
        encoder.dispatchThreads(threads, threadsPerThreadgroup: threadsPerGroup)
        encoder.endEncoding()
    }

    private func encodeDissipationPatch(
        on commandBuffer: MTLCommandBuffer,
        massBuffer: MTLBuffer,
        paramsBuffer: MTLBuffer,
        patch: FlowLeniaMetalDissipationBatch
    ) {
        guard patch.removalOrigins.count == batchCount, patch.insertionOrigins.count == batchCount else {
            preconditionFailure(
                "FlowLeniaMetalFullStateRunner dissipation patch expects \(batchCount) batch origins."
            )
        }
        let expectedMassCount = batchCount * patch.size * patch.size * channelCount
        guard patch.insertedMass.count == expectedMassCount else {
            preconditionFailure(
                "FlowLeniaMetalFullStateRunner dissipation patch expects \(expectedMassCount) inserted mass values, got \(patch.insertedMass.count)."
            )
        }
        let expectedParamCount = batchCount * parameterCount
        guard patch.insertedParams.count == expectedParamCount else {
            preconditionFailure(
                "FlowLeniaMetalFullStateRunner dissipation patch expects \(expectedParamCount) inserted parameter values, got \(patch.insertedParams.count)."
            )
        }

        let removalOrigins = patch.removalOrigins.map { ParameterPatchOrigin(x0: $0.x, y0: $0.y) }
        let insertionOrigins = patch.insertionOrigins.map { ParameterPatchOrigin(x0: $0.x, y0: $0.y) }
        guard let removalOriginBuffer = device.makeBuffer(
            length: removalOrigins.count * MemoryLayout<ParameterPatchOrigin>.stride,
            options: .storageModeShared
        ), let insertionOriginBuffer = device.makeBuffer(
            length: insertionOrigins.count * MemoryLayout<ParameterPatchOrigin>.stride,
            options: .storageModeShared
        ), let insertedMassBuffer = device.makeBuffer(
            length: patch.insertedMass.count * MemoryLayout<Float>.stride,
            options: .storageModeShared
        ), let insertedParamsBuffer = device.makeBuffer(
            length: patch.insertedParams.count * MemoryLayout<Float>.stride,
            options: .storageModeShared
        ) else {
            preconditionFailure("Failed to allocate Flow Metal dissipation buffers.")
        }
        removalOriginBuffer.label = "flow-metal.state.dissipation.remove-origins"
        insertionOriginBuffer.label = "flow-metal.state.dissipation.insert-origins"
        insertedMassBuffer.label = "flow-metal.state.dissipation.insert-mass"
        insertedParamsBuffer.label = "flow-metal.state.dissipation.insert-params"
        _ = removalOrigins.withUnsafeBytes { rawOrigins in
            memcpy(removalOriginBuffer.contents(), rawOrigins.baseAddress, rawOrigins.count)
        }
        _ = insertionOrigins.withUnsafeBytes { rawOrigins in
            memcpy(insertionOriginBuffer.contents(), rawOrigins.baseAddress, rawOrigins.count)
        }
        FlowLeniaMetalFullPipeline.writeFloats(patch.insertedMass, to: insertedMassBuffer)
        FlowLeniaMetalFullPipeline.writeFloats(patch.insertedParams, to: insertedParamsBuffer)
        var uniforms = StatePatchUniforms(size: Int32(patch.size))

        guard let zeroEncoder = commandBuffer.makeComputeCommandEncoder() else {
            preconditionFailure("Failed to create Flow Metal dissipation zero encoder.")
        }
        zeroEncoder.setComputePipelineState(zeroStatePatchPipeline)
        zeroEncoder.setBuffer(removalOriginBuffer, offset: 0, index: 0)
        zeroEncoder.setBuffer(massBuffer, offset: 0, index: 1)
        zeroEncoder.setBuffer(paramsBuffer, offset: 0, index: 2)
        withUnsafeBytes(of: &uniforms) { rawUniforms in
            zeroEncoder.setBytes(rawUniforms.baseAddress!, length: rawUniforms.count, index: 3)
        }
        let zeroThreadWidth = min(8, max(1, zeroStatePatchPipeline.threadExecutionWidth))
        let zeroMaxHeight = max(1, zeroStatePatchPipeline.maxTotalThreadsPerThreadgroup / zeroThreadWidth)
        let zeroThreadHeight = min(8, zeroMaxHeight)
        let zeroThreadsPerGroup = MTLSize(width: zeroThreadWidth, height: zeroThreadHeight, depth: 1)
        let threads = MTLSize(width: patch.size, height: patch.size, depth: batchCount)
        zeroEncoder.dispatchThreads(threads, threadsPerThreadgroup: zeroThreadsPerGroup)
        zeroEncoder.endEncoding()

        guard let insertEncoder = commandBuffer.makeComputeCommandEncoder() else {
            preconditionFailure("Failed to create Flow Metal dissipation insert encoder.")
        }
        insertEncoder.setComputePipelineState(insertStatePatchPipeline)
        insertEncoder.setBuffer(insertedMassBuffer, offset: 0, index: 0)
        insertEncoder.setBuffer(insertedParamsBuffer, offset: 0, index: 1)
        insertEncoder.setBuffer(insertionOriginBuffer, offset: 0, index: 2)
        insertEncoder.setBuffer(massBuffer, offset: 0, index: 3)
        insertEncoder.setBuffer(paramsBuffer, offset: 0, index: 4)
        withUnsafeBytes(of: &uniforms) { rawUniforms in
            insertEncoder.setBytes(rawUniforms.baseAddress!, length: rawUniforms.count, index: 5)
        }
        let insertThreadWidth = min(8, max(1, insertStatePatchPipeline.threadExecutionWidth))
        let insertMaxHeight = max(1, insertStatePatchPipeline.maxTotalThreadsPerThreadgroup / insertThreadWidth)
        let insertThreadHeight = min(8, insertMaxHeight)
        let insertThreadsPerGroup = MTLSize(width: insertThreadWidth, height: insertThreadHeight, depth: 1)
        insertEncoder.dispatchThreads(threads, threadsPerThreadgroup: insertThreadsPerGroup)
        insertEncoder.endEncoding()
    }

    private func encodeFoodFieldOverwrite(
        on commandBuffer: MTLCommandBuffer,
        massBuffer: MTLBuffer
    ) {
        guard let foodState else {
            return
        }
        encodeChannelFieldOverwrite(
            on: commandBuffer,
            massBuffer: massBuffer,
            fieldBuffer: foodState.buffer,
            channelIndex: foodState.channelIndex
        )
    }

    private func encodeParameterPatch(
        on commandBuffer: MTLCommandBuffer,
        paramsBuffer: MTLBuffer,
        patch: FlowLeniaMetalParameterPatchBatch
    ) {
        guard patch.origins.count == batchCount else {
            preconditionFailure(
                "FlowLeniaMetalFullStateRunner parameter patch expects \(batchCount) batch origins, got \(patch.origins.count)."
            )
        }
        let expectedCount = batchCount * patch.size * patch.size * parameterCount
        guard patch.deltas.count == expectedCount else {
            preconditionFailure(
                "FlowLeniaMetalFullStateRunner parameter patch expects \(expectedCount) delta values, got \(patch.deltas.count)."
            )
        }
        guard let deltaBuffer = device.makeBuffer(
            length: patch.deltas.count * MemoryLayout<Float>.stride,
            options: .storageModeShared
        ) else {
            preconditionFailure("Failed to allocate Flow Metal parameter patch delta buffer.")
        }
        deltaBuffer.label = "flow-metal.state.paramPatch.delta"
        FlowLeniaMetalFullPipeline.writeFloats(patch.deltas, to: deltaBuffer)
        let patchOrigins = patch.origins.map { ParameterPatchOrigin(x0: $0.x, y0: $0.y) }
        guard let originBuffer = device.makeBuffer(
            length: patchOrigins.count * MemoryLayout<ParameterPatchOrigin>.stride,
            options: .storageModeShared
        ) else {
            preconditionFailure("Failed to allocate Flow Metal parameter patch origin buffer.")
        }
        originBuffer.label = "flow-metal.state.paramPatch.origins"
        _ = patchOrigins.withUnsafeBytes { rawOrigins in
            memcpy(originBuffer.contents(), rawOrigins.baseAddress, rawOrigins.count)
        }
        var uniforms = ParameterPatchUniforms(
            size: Int32(patch.size),
            applyClip: patch.clip == nil ? 0 : 1,
            clipLow: patch.clip?[0] ?? 0,
            clipHigh: patch.clip?[1] ?? 0
        )
        guard let encoder = commandBuffer.makeComputeCommandEncoder() else {
            preconditionFailure("Failed to create Flow Metal parameter patch encoder.")
        }
        encoder.setComputePipelineState(parameterPatchPipeline)
        encoder.setBuffer(deltaBuffer, offset: 0, index: 0)
        encoder.setBuffer(originBuffer, offset: 0, index: 1)
        encoder.setBuffer(paramsBuffer, offset: 0, index: 2)
        withUnsafeBytes(of: &uniforms) { rawUniforms in
            encoder.setBytes(rawUniforms.baseAddress!, length: rawUniforms.count, index: 3)
        }
        let threadWidth = min(8, max(1, parameterPatchPipeline.threadExecutionWidth))
        let maxHeight = max(1, parameterPatchPipeline.maxTotalThreadsPerThreadgroup / threadWidth)
        let threadHeight = min(8, maxHeight)
        let threadsPerGroup = MTLSize(width: threadWidth, height: threadHeight, depth: 1)
        let threads = MTLSize(width: patch.size, height: patch.size, depth: batchCount)
        encoder.dispatchThreads(threads, threadsPerThreadgroup: threadsPerGroup)
        encoder.endEncoding()
    }

    private func submitAndWait(
        label: String,
        encoding: (MTLCommandBuffer) -> Void
    ) {
        guard let commandBuffer = commandQueue.makeCommandBuffer() else {
            preconditionFailure("Failed to create Flow Metal command buffer \(label).")
        }
        commandBuffer.label = label
        encoding(commandBuffer)
        FlowLeniaMetalFullPipeline.commitAndWait(commandBuffer, label: label)
    }

    private func encodeCopies(_ copies: [BufferCopy], on commandBuffer: MTLCommandBuffer) {
        guard let encoder = commandBuffer.makeBlitCommandEncoder() else {
            preconditionFailure("Failed to create Flow Metal state transfer encoder.")
        }
        for copy in copies {
            guard copy.source.length >= copy.length, copy.destination.length >= copy.length else {
                preconditionFailure("Flow Metal state transfer buffer is smaller than the requested copy.")
            }
            encoder.copy(
                from: copy.source,
                sourceOffset: 0,
                to: copy.destination,
                destinationOffset: 0,
                size: copy.length
            )
        }
        encoder.endEncoding()
    }

    private func prepareWallMask(_ wallMask: MLXArray?) -> BufferCopy? {
        guard let wallMask else {
            return nil
        }
        let values = Self.expandScalarField(
            wallMask,
            batchCount: batchCount,
            sx: config.sx,
            sy: config.sy,
            label: "wallMask"
        )
        let byteCount = values.count * MemoryLayout<Float>.stride
        let buffers = wallMaskBuffers ?? FlowLeniaMetalFullPipeline.makeUploadBuffers(
            device: device,
            length: byteCount,
            label: "flow-metal.state.wallMask"
        )
        wallMaskBuffers = buffers
        FlowLeniaMetalFullPipeline.writeFloats(values, to: buffers.transferBuffer)
        return (buffers.transferBuffer, buffers.privateBuffer, byteCount)
    }

    private func prepareStaticChannelFields(
        _ fields: [FlowLeniaMetalChannelField]
    ) -> (fields: [FlowLeniaMetalChannelFieldBuffer], uploads: [BufferCopy]) {
        var fieldBuffers: [FlowLeniaMetalChannelFieldBuffer] = []
        var uploads: [BufferCopy] = []
        fieldBuffers.reserveCapacity(fields.count)
        uploads.reserveCapacity(fields.count)
        for field in fields {
            guard field.channelIndex >= 0, field.channelIndex < channelCount else {
                preconditionFailure("FlowLeniaMetalFullStateRunner static channel fields must target an in-range channel.")
            }
            let values = Self.expandScalarField(
                field.field,
                batchCount: batchCount,
                sx: config.sx,
                sy: config.sy,
                label: "channelField"
            )
            let byteCount = values.count * MemoryLayout<Float>.stride
            let transferBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
                device: device,
                length: byteCount,
                label: "flow-metal.state.channelField-transfer.\(field.channelIndex)"
            )
            let privateBuffer = FlowLeniaMetalFullPipeline.makePrivateBuffer(
                device: device,
                length: byteCount,
                label: "flow-metal.state.channelField.\(field.channelIndex)"
            )
            FlowLeniaMetalFullPipeline.writeFloats(values, to: transferBuffer)
            fieldBuffers.append(FlowLeniaMetalChannelFieldBuffer(
                channelIndex: field.channelIndex,
                buffer: privateBuffer
            ))
            uploads.append((transferBuffer, privateBuffer, byteCount))
        }
        return (fieldBuffers, uploads)
    }

    private func prepareFoodState(
        _ food: FlowLeniaMetalFoodState?
    ) -> (state: FlowLeniaMetalFoodStateBuffer?, upload: BufferCopy?) {
        guard let food else {
            return (nil, nil)
        }
        guard food.channelIndex >= 0, food.channelIndex < channelCount else {
            preconditionFailure("FlowLeniaMetalFullStateRunner food state must target an in-range channel.")
        }
        let values = Self.expandPlanarField(
            food.field,
            batchCount: batchCount,
            sx: config.sx,
            sy: config.sy,
            label: "food"
        )
        let byteCount = values.count * MemoryLayout<Float>.stride
        let transferBuffer: MTLBuffer
        let privateBuffer: MTLBuffer
        if let existing = foodState,
           existing.buffer.length == byteCount,
           existing.transferBuffer.length == byteCount {
            transferBuffer = existing.transferBuffer
            privateBuffer = existing.buffer
        } else {
            transferBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
                device: device,
                length: byteCount,
                label: "flow-metal.state.food-transfer"
            )
            privateBuffer = FlowLeniaMetalFullPipeline.makePrivateBuffer(
                device: device,
                length: byteCount,
                label: "flow-metal.state.food"
            )
        }
        FlowLeniaMetalFullPipeline.writeFloats(values, to: transferBuffer)
        let state = FlowLeniaMetalFoodStateBuffer(
            channelIndex: food.channelIndex,
            decayRate: food.decayRate,
            digestRate: food.digestRate,
            buffer: privateBuffer,
            transferBuffer: transferBuffer
        )
        return (state, (transferBuffer, privateBuffer, byteCount))
    }

    private func readFloats(
        from source: MTLBuffer,
        into destination: MTLBuffer,
        count: Int,
        label: String
    ) -> [Float] {
        submitAndWait(label: "\(label).readback") { commandBuffer in
            encodeCopies(
                [(source, destination, count * MemoryLayout<Float>.stride)],
                on: commandBuffer
            )
        }
        return FlowLeniaMetalFullPipeline.readFloats(from: destination, count: count)
    }

    private func encodeWallMask(
        on commandBuffer: MTLCommandBuffer,
        massBuffer: MTLBuffer,
        paramsBuffer: MTLBuffer
    ) {
        guard let wallMaskBuffer = wallMaskBuffers?.privateBuffer else {
            preconditionFailure("Flow Metal wall mask is enabled without an allocated buffer.")
        }
        guard let encoder = commandBuffer.makeComputeCommandEncoder() else {
            preconditionFailure("Failed to create Flow Metal wall mask encoder.")
        }
        encoder.setComputePipelineState(wallMaskPipeline)
        encoder.setBuffer(wallMaskBuffer, offset: 0, index: 0)
        encoder.setBuffer(massBuffer, offset: 0, index: 1)
        encoder.setBuffer(paramsBuffer, offset: 0, index: 2)
        let threadWidth = min(16, max(1, wallMaskPipeline.threadExecutionWidth))
        let maxHeight = max(1, wallMaskPipeline.maxTotalThreadsPerThreadgroup / threadWidth)
        let threadHeight = min(16, maxHeight)
        let threadsPerGroup = MTLSize(width: threadWidth, height: threadHeight, depth: 1)
        let threads = MTLSize(width: config.sx, height: config.sy, depth: batchCount)
        encoder.dispatchThreads(threads, threadsPerThreadgroup: threadsPerGroup)
        encoder.endEncoding()
    }

    private func encodeFoodMask(on commandBuffer: MTLCommandBuffer) {
        guard let foodState else {
            return
        }
        guard let wallMaskBuffer = wallMaskBuffers?.privateBuffer else {
            preconditionFailure("Flow Metal wall mask is enabled without an allocated buffer.")
        }
        guard let encoder = commandBuffer.makeComputeCommandEncoder() else {
            preconditionFailure("Failed to create Flow Metal food mask encoder.")
        }
        encoder.setComputePipelineState(scalarFieldMaskPipeline)
        encoder.setBuffer(wallMaskBuffer, offset: 0, index: 0)
        encoder.setBuffer(foodState.buffer, offset: 0, index: 1)
        let threadWidth = min(16, max(1, scalarFieldMaskPipeline.threadExecutionWidth))
        let maxHeight = max(1, scalarFieldMaskPipeline.maxTotalThreadsPerThreadgroup / threadWidth)
        let threadHeight = min(16, maxHeight)
        let threadsPerGroup = MTLSize(width: threadWidth, height: threadHeight, depth: 1)
        let threads = MTLSize(width: config.sx, height: config.sy, depth: batchCount)
        encoder.dispatchThreads(threads, threadsPerThreadgroup: threadsPerGroup)
        encoder.endEncoding()
    }

    private func encodeFoodDynamics(
        on commandBuffer: MTLCommandBuffer,
        massBuffer: MTLBuffer
    ) {
        guard let foodState else {
            return
        }
        var uniforms = FoodDynamicsUniforms(
            channelIndex: Int32(foodState.channelIndex),
            decayRate: foodState.decayRate,
            digestRate: foodState.digestRate,
            epsilon: 1e-6
        )
        guard let encoder = commandBuffer.makeComputeCommandEncoder() else {
            preconditionFailure("Failed to create Flow Metal food dynamics encoder.")
        }
        encoder.setComputePipelineState(foodDynamicsPipeline)
        currentMatterWeights.withUnsafeBufferPointer { weights in
            guard let base = weights.baseAddress else {
                preconditionFailure("FlowLeniaMetalFullStateRunner matter weights are unexpectedly empty.")
            }
            encoder.setBytes(base, length: weights.count * MemoryLayout<Float>.stride, index: 0)
        }
        encoder.setBuffer(massBuffer, offset: 0, index: 1)
        encoder.setBuffer(foodState.buffer, offset: 0, index: 2)
        withUnsafeBytes(of: &uniforms) { rawUniforms in
            encoder.setBytes(rawUniforms.baseAddress!, length: rawUniforms.count, index: 3)
        }
        let threadWidth = min(16, max(1, foodDynamicsPipeline.threadExecutionWidth))
        let maxHeight = max(1, foodDynamicsPipeline.maxTotalThreadsPerThreadgroup / threadWidth)
        let threadHeight = min(16, maxHeight)
        let threadsPerGroup = MTLSize(width: threadWidth, height: threadHeight, depth: 1)
        let threads = MTLSize(width: config.sx, height: config.sy, depth: batchCount)
        encoder.dispatchThreads(threads, threadsPerThreadgroup: threadsPerGroup)
        encoder.endEncoding()
    }

    private static func expandScalarField(
        _ values: MLXArray,
        batchCount: Int,
        sx: Int,
        sy: Int,
        label: String
    ) -> [Float] {
        guard values.shape.count == 4 else {
            preconditionFailure("FlowLeniaMetalFullStateRunner \(label) must have shape [batch, sx, sy, 1].")
        }
        guard values.shape[1] == sx, values.shape[2] == sy, values.shape[3] == 1 else {
            preconditionFailure("FlowLeniaMetalFullStateRunner \(label) must have shape [batch, \(sx), \(sy), 1].")
        }
        guard values.shape[0] == 1 || values.shape[0] == batchCount else {
            preconditionFailure("FlowLeniaMetalFullStateRunner \(label) must be shared across the batch or provided per batch element.")
        }
        let contiguous = values.contiguous()
        let raw = contiguous.asArray(Float.self)
        if values.shape[0] == batchCount {
            return raw
        }
        return Array(repeating: raw, count: batchCount).flatMap { $0 }
    }

    private static func expandPlanarField(
        _ values: MLXArray,
        batchCount: Int,
        sx: Int,
        sy: Int,
        label: String
    ) -> [Float] {
        switch values.shape.count {
        case 2:
            guard values.shape[0] == sx, values.shape[1] == sy else {
                preconditionFailure("FlowLeniaMetalFullStateRunner \(label) must have shape [\(sx), \(sy)].")
            }
            let raw = values.contiguous().asArray(Float.self)
            return Array(repeating: raw, count: batchCount).flatMap { $0 }
        case 3:
            guard values.shape[1] == sx, values.shape[2] == sy else {
                preconditionFailure("FlowLeniaMetalFullStateRunner \(label) must have shape [batch, \(sx), \(sy)].")
            }
            guard values.shape[0] == 1 || values.shape[0] == batchCount else {
                preconditionFailure("FlowLeniaMetalFullStateRunner \(label) must be shared across the batch or provided per batch element.")
            }
            let raw = values.contiguous().asArray(Float.self)
            if values.shape[0] == batchCount {
                return raw
            }
            return Array(repeating: raw, count: batchCount).flatMap { $0 }
        case 4:
            return expandScalarField(
                values,
                batchCount: batchCount,
                sx: sx,
                sy: sy,
                label: label
            )
        default:
            preconditionFailure("FlowLeniaMetalFullStateRunner \(label) must have shape [sx, sy], [batch, sx, sy], or [batch, sx, sy, 1].")
        }
    }

    private static func resolvedMatterWeights(
        weights: [Float]?,
        channelCount: Int
    ) -> [Float] {
        if let weights {
            guard weights.count == channelCount else {
                preconditionFailure("FlowLeniaMetalFullStateRunner matter weights must match the configured channel count.")
            }
            return weights
        }
        return Array(repeating: 1.0, count: channelCount)
    }

    private static func wallMaskKernelSource(
        parameterCount: Int,
        channelCount: Int,
        batchCount: Int,
        sx: Int,
        sy: Int
    ) -> String {
        """
        #include <metal_stdlib>
        using namespace metal;

        constant int kParamCount = \(parameterCount);
        constant int kChannelCount = \(channelCount);
        constant int kBatchCount = \(batchCount);
        constant int kSX = \(sx);
        constant int kSY = \(sy);
        constant uint kSummaryThreads = \(FlowLeniaMetalFullPipeline.summaryThreadCount)u;
        constant uint kSummaryChunkSpan = \(FlowLeniaMetalFullPipeline.summaryChunkSpan)u;
        constant uint kSummaryPartialGroups = \(FlowLeniaMetalFullPipeline.summaryPartialGroupCount(sx: sx, sy: sy))u;

        struct ParameterPatchUniforms {
            int size;
            uint applyClip;
            float clipLow;
            float clipHigh;
        };

        struct ParameterPatchOrigin {
            int x0;
            int y0;
        };

        struct ChannelFieldUniforms {
            int channelIndex;
        };

        struct ScalarPatchUniforms {
            int size;
            float value;
        };

        struct StatePatchUniforms {
            int size;
        };

        struct FoodDynamicsUniforms {
            int channelIndex;
            float decayRate;
            float digestRate;
            float epsilon;
        };

        kernel void flowMetalApplyWallMask(
            device const float *wallMask [[buffer(0)]],
            device float *mass [[buffer(1)]],
            device float *params [[buffer(2)]],
            uint3 gid [[thread_position_in_grid]]
        ) {
            if (int(gid.x) >= kSX || int(gid.y) >= kSY || int(gid.z) >= kBatchCount) {
                return;
            }
            int batch = int(gid.z);
            int x = int(gid.x);
            int y = int(gid.y);
            int cellIndex = (batch * kSX + x) * kSY + y;
            float maskValue = wallMask[cellIndex];
            int massBase = cellIndex * kChannelCount;
            for (int channel = 0; channel < kChannelCount; ++channel) {
                mass[massBase + channel] *= maskValue;
            }
            int paramBase = cellIndex * kParamCount;
            for (int k = 0; k < kParamCount; ++k) {
                params[paramBase + k] *= maskValue;
            }
        }

        kernel void flowMetalOverwriteChannelField(
            device const float *field [[buffer(0)]],
            device float *mass [[buffer(1)]],
            constant ChannelFieldUniforms &uniforms [[buffer(2)]],
            uint3 gid [[thread_position_in_grid]]
        ) {
            if (int(gid.x) >= kSX || int(gid.y) >= kSY || int(gid.z) >= kBatchCount) {
                return;
            }
            int batch = int(gid.z);
            int x = int(gid.x);
            int y = int(gid.y);
            int cellIndex = (batch * kSX + x) * kSY + y;
            int massBase = cellIndex * kChannelCount;
            mass[massBase + uniforms.channelIndex] = field[cellIndex];
        }

        kernel void flowMetalApplyScalarFieldMask(
            device const float *wallMask [[buffer(0)]],
            device float *field [[buffer(1)]],
            uint3 gid [[thread_position_in_grid]]
        ) {
            if (int(gid.x) >= kSX || int(gid.y) >= kSY || int(gid.z) >= kBatchCount) {
                return;
            }
            int batch = int(gid.z);
            int x = int(gid.x);
            int y = int(gid.y);
            int cellIndex = (batch * kSX + x) * kSY + y;
            field[cellIndex] *= wallMask[cellIndex];
        }

        kernel void flowMetalApplyScalarPatch(
            device const ParameterPatchOrigin *origins [[buffer(0)]],
            device float *field [[buffer(1)]],
            constant ScalarPatchUniforms &patch [[buffer(2)]],
            uint3 gid [[thread_position_in_grid]]
        ) {
            if (int(gid.x) >= patch.size || int(gid.y) >= patch.size || int(gid.z) >= kBatchCount) {
                return;
            }
            int batch = int(gid.z);
            ParameterPatchOrigin origin = origins[batch];
            if (origin.x0 < 0 || origin.y0 < 0) {
                return;
            }
            int x = origin.x0 + int(gid.x);
            int y = origin.y0 + int(gid.y);
            if (x < 0 || x >= kSX || y < 0 || y >= kSY) {
                return;
            }
            int cellIndex = (batch * kSX + x) * kSY + y;
            field[cellIndex] = patch.value;
        }

        kernel void flowMetalApplyFoodDynamics(
            constant float *matterWeights [[buffer(0)]],
            device float *mass [[buffer(1)]],
            device float *food [[buffer(2)]],
            constant FoodDynamicsUniforms &uniforms [[buffer(3)]],
            uint3 gid [[thread_position_in_grid]]
        ) {
            if (int(gid.x) >= kSX || int(gid.y) >= kSY || int(gid.z) >= kBatchCount) {
                return;
            }
            int batch = int(gid.z);
            int x = int(gid.x);
            int y = int(gid.y);
            int cellIndex = (batch * kSX + x) * kSY + y;
            int massBase = cellIndex * kChannelCount;
            float matter = 0.0f;
            for (int channel = 0; channel < kChannelCount; ++channel) {
                matter += mass[massBase + channel] * matterWeights[channel];
            }
            float oldFood = food[cellIndex];
            float decay = matter * uniforms.decayRate;
            float digestRaw = matter * uniforms.digestRate;
            float digestClipped = clamp(digestRaw, 0.0f, matter);
            float delta = digestClipped * oldFood;
            float newMatter = max(matter + delta - decay, 0.0f);
            float scale = newMatter / max(matter, uniforms.epsilon);
            for (int channel = 0; channel < kChannelCount; ++channel) {
                if (matterWeights[channel] != 0.0f) {
                    mass[massBase + channel] *= scale;
                }
            }
            float newFood = max(oldFood - delta, 0.0f);
            food[cellIndex] = newFood;
            mass[massBase + uniforms.channelIndex] = newFood;
        }

        kernel void flowMetalZeroStatePatch(
            device const ParameterPatchOrigin *origins [[buffer(0)]],
            device float *mass [[buffer(1)]],
            device float *params [[buffer(2)]],
            constant StatePatchUniforms &patch [[buffer(3)]],
            uint3 gid [[thread_position_in_grid]]
        ) {
            if (int(gid.x) >= patch.size || int(gid.y) >= patch.size || int(gid.z) >= kBatchCount) {
                return;
            }
            int batch = int(gid.z);
            ParameterPatchOrigin origin = origins[batch];
            if (origin.x0 < 0 || origin.y0 < 0) {
                return;
            }
            int x = origin.x0 + int(gid.x);
            int y = origin.y0 + int(gid.y);
            if (x < 0 || x >= kSX || y < 0 || y >= kSY) {
                return;
            }
            int cellIndex = (batch * kSX + x) * kSY + y;
            int massBase = cellIndex * kChannelCount;
            for (int channel = 0; channel < kChannelCount; ++channel) {
                mass[massBase + channel] = 0.0f;
            }
            int paramBase = cellIndex * kParamCount;
            for (int k = 0; k < kParamCount; ++k) {
                params[paramBase + k] = 0.0f;
            }
        }

        kernel void flowMetalInsertStatePatch(
            device const float *massValues [[buffer(0)]],
            device const float *paramValues [[buffer(1)]],
            device const ParameterPatchOrigin *origins [[buffer(2)]],
            device float *mass [[buffer(3)]],
            device float *params [[buffer(4)]],
            constant StatePatchUniforms &patch [[buffer(5)]],
            uint3 gid [[thread_position_in_grid]]
        ) {
            if (int(gid.x) >= patch.size || int(gid.y) >= patch.size || int(gid.z) >= kBatchCount) {
                return;
            }
            int batch = int(gid.z);
            ParameterPatchOrigin origin = origins[batch];
            if (origin.x0 < 0 || origin.y0 < 0) {
                return;
            }
            int localX = int(gid.x);
            int localY = int(gid.y);
            int x = origin.x0 + localX;
            int y = origin.y0 + localY;
            if (x < 0 || x >= kSX || y < 0 || y >= kSY) {
                return;
            }
            int cellIndex = (batch * kSX + x) * kSY + y;
            int insertedMassBase = ((batch * patch.size + localX) * patch.size + localY) * kChannelCount;
            int massBase = cellIndex * kChannelCount;
            for (int channel = 0; channel < kChannelCount; ++channel) {
                mass[massBase + channel] = massValues[insertedMassBase + channel];
            }
            int paramBase = cellIndex * kParamCount;
            int insertedParamBase = batch * kParamCount;
            for (int k = 0; k < kParamCount; ++k) {
                params[paramBase + k] = paramValues[insertedParamBase + k];
            }
        }

        kernel void flowMetalApplyParameterPatch(
            device const float *delta [[buffer(0)]],
            device const ParameterPatchOrigin *origins [[buffer(1)]],
            device float *params [[buffer(2)]],
            constant ParameterPatchUniforms &patch [[buffer(3)]],
            uint3 gid [[thread_position_in_grid]]
        ) {
            if (int(gid.x) >= patch.size || int(gid.y) >= patch.size || int(gid.z) >= kBatchCount) {
                return;
            }
            int batch = int(gid.z);
            int localX = int(gid.x);
            int localY = int(gid.y);
            ParameterPatchOrigin origin = origins[batch];
            int x = origin.x0 + localX;
            int y = origin.y0 + localY;
            if (x < 0 || x >= kSX || y < 0 || y >= kSY) {
                return;
            }
            int cellIndex = (batch * kSX + x) * kSY + y;
            int deltaBase = ((batch * patch.size + localX) * patch.size + localY) * kParamCount;
            int paramBase = cellIndex * kParamCount;
            for (int k = 0; k < kParamCount; ++k) {
                float value = params[paramBase + k] + delta[deltaBase + k];
                if (patch.applyClip != 0u) {
                    value = clamp(value, patch.clipLow, patch.clipHigh);
                }
                params[paramBase + k] = value;
            }
        }

        kernel void flowMetalBuildMassMap(
            device const float *mass [[buffer(0)]],
            device float *massMap [[buffer(1)]],
            device const float *channelWeights [[buffer(2)]],
            uint3 gid [[thread_position_in_grid]]
        ) {
            if (int(gid.x) >= kSX || int(gid.y) >= kSY || int(gid.z) >= kBatchCount) {
                return;
            }
            int batch = int(gid.z);
            int x = int(gid.x);
            int y = int(gid.y);
            int cellIndex = (batch * kSX + x) * kSY + y;
            int massBase = cellIndex * kChannelCount;
            float value = 0.0f;
            for (int channel = 0; channel < kChannelCount; ++channel) {
                value += mass[massBase + channel] * channelWeights[channel];
            }
            massMap[cellIndex] = value;
        }

        kernel void flowMetalScalarSummaryPartial(
            device const float *field [[buffer(0)]],
            device float *partialSums [[buffer(1)]],
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

            threadgroup float sumScratch[kSummaryThreads];
            float localSum = 0.0f;
            int spatialCount = kSX * kSY;
            uint chunkStart = partialGroup * kSummaryChunkSpan;
            uint chunkEnd = min(chunkStart + kSummaryChunkSpan, uint(spatialCount));
            int batchOffset = batch * spatialCount;
            for (uint linear = chunkStart + tid; linear < chunkEnd; linear += kSummaryThreads) {
                localSum += field[batchOffset + int(linear)];
            }

            localSum = simd_sum(localSum);
            if (lane == 0u) {
                sumScratch[simdGroup] = localSum;
            }
            threadgroup_barrier(mem_flags::mem_threadgroup);

            uint simdGroupCount = (kSummaryThreads + threadsPerSimdgroup - 1u) / threadsPerSimdgroup;
            float reducedSum = tid < simdGroupCount ? sumScratch[tid] : 0.0f;
            reducedSum = simd_sum(reducedSum);
            if (tid == 0u) {
                int partialIndex = batch * int(kSummaryPartialGroups) + int(partialGroup);
                partialSums[partialIndex] = reducedSum;
            }
        }

        kernel void flowMetalScalarSummaryFinalize(
            device const float *partialSums [[buffer(0)]],
            device float *sums [[buffer(1)]],
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

            threadgroup float sumScratch[kSummaryThreads];
            float localSum = 0.0f;
            for (uint partialIndex = tid; partialIndex < kSummaryPartialGroups; partialIndex += kSummaryThreads) {
                int index = batch * int(kSummaryPartialGroups) + int(partialIndex);
                localSum += partialSums[index];
            }

            localSum = simd_sum(localSum);
            if (lane == 0u) {
                sumScratch[simdGroup] = localSum;
            }
            threadgroup_barrier(mem_flags::mem_threadgroup);

            uint simdGroupCount = (kSummaryThreads + threadsPerSimdgroup - 1u) / threadsPerSimdgroup;
            float reducedSum = tid < simdGroupCount ? sumScratch[tid] : 0.0f;
            reducedSum = simd_sum(reducedSum);
            if (tid == 0u) {
                sums[batch] = reducedSum;
            }
        }
        """
    }
}

struct FlowLeniaMetalParameterPatchBatch {
    let origins: [SIMD2<Int32>]
    let size: Int
    let deltas: [Float]
    let clip: [Float]?
}

struct FlowLeniaMetalChannelField {
    let channelIndex: Int
    let field: MLXArray
}

struct FlowLeniaMetalFoodState {
    let channelIndex: Int
    let field: MLXArray
    let decayRate: Float
    let digestRate: Float
}

struct FlowLeniaMetalScalarPatchBatch {
    let origins: [SIMD2<Int32>]
    let size: Int
    let value: Float
}

struct FlowLeniaMetalDissipationBatch {
    let removalOrigins: [SIMD2<Int32>]
    let insertionOrigins: [SIMD2<Int32>]
    let size: Int
    let insertedMass: [Float]
    let insertedParams: [Float]
}

private struct FlowLeniaMetalChannelFieldBuffer {
    let channelIndex: Int
    let buffer: MTLBuffer
}

private struct FlowLeniaMetalFoodStateBuffer {
    let channelIndex: Int
    let decayRate: Float
    let digestRate: Float
    let buffer: MTLBuffer
    let transferBuffer: MTLBuffer
}

private struct ParameterPatchUniforms {
    var size: Int32
    var applyClip: UInt32
    var clipLow: Float
    var clipHigh: Float
}

private struct ChannelFieldUniforms {
    var channelIndex: Int32
}

private struct ScalarPatchUniforms {
    var size: Int32
    var value: Float
}

private struct StatePatchUniforms {
    var size: Int32
}

private struct FoodDynamicsUniforms {
    var channelIndex: Int32
    var decayRate: Float
    var digestRate: Float
    var epsilon: Float
}

private struct ParameterPatchOrigin {
    var x0: Int32
    var y0: Int32
}
