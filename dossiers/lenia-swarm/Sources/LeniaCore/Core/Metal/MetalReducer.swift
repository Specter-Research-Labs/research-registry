import Foundation
import Metal

struct FlowLeniaMetalMassSummary: Sendable {
    let totalMass: [Float]
    let sumSquares: [Float]
    let energy: [Float]
    let occupancyCount: [Float]
    let centerXIndex: [Float]
    let centerYIndex: [Float]
    let rawGyration: [Float]?
}

final class FlowLeniaMetalSummaryReducer: @unchecked Sendable {
    private let batchCount: Int
    private let channelCount: Int
    private let partialGroupCount: Int
    private let pass1PartialPipeline: MTLComputePipelineState
    private let pass1FinalizePipeline: MTLComputePipelineState
    private let pass2PartialPipeline: MTLComputePipelineState
    private let pass2FinalizePipeline: MTLComputePipelineState
    private let occupancyThresholdBuffer: MTLBuffer
    private let channelWeightsBuffer: MTLBuffer
    private let circularXWeightsBuffer: MTLBuffer
    private let circularYWeightsBuffer: MTLBuffer
    private let partialTotalMassBuffer: MTLBuffer
    private let partialSumSquaresBuffer: MTLBuffer
    private let partialEnergyBuffer: MTLBuffer
    private let partialWeightedXBuffer: MTLBuffer
    private let partialWeightedYBuffer: MTLBuffer
    private let partialOccupancyCountBuffer: MTLBuffer
    private let partialCircularFirstBuffer: MTLBuffer
    private let partialCircularSecondBuffer: MTLBuffer
    private let partialGyrationBuffer: MTLBuffer
    private let totalMassBuffer: MTLBuffer
    private let sumSquaresBuffer: MTLBuffer
    private let energyBuffer: MTLBuffer
    private let weightedXBuffer: MTLBuffer
    private let weightedYBuffer: MTLBuffer
    private let occupancyCountBuffer: MTLBuffer
    private let circularFirstBuffer: MTLBuffer
    private let circularSecondBuffer: MTLBuffer
    private let gyrationBuffer: MTLBuffer

    init(
        config: BatchedConfig,
        batchCount: Int,
        device: MTLDevice,
        library: MTLLibrary
    ) {
        self.batchCount = batchCount
        self.channelCount = config.channels
        self.partialGroupCount = FlowLeniaMetalFullPipeline.summaryPartialGroupCount(sx: config.sx, sy: config.sy)

        self.pass1PartialPipeline = FlowLeniaMetalFullPipeline.makePipeline(
            device: device,
            library: library,
            name: "flowMetalMassSummaryPass1Partial"
        )
        self.pass1FinalizePipeline = FlowLeniaMetalFullPipeline.makePipeline(
            device: device,
            library: library,
            name: "flowMetalMassSummaryPass1Finalize"
        )
        self.pass2PartialPipeline = FlowLeniaMetalFullPipeline.makePipeline(
            device: device,
            library: library,
            name: "flowMetalMassSummaryGyrationPartial"
        )
        self.pass2FinalizePipeline = FlowLeniaMetalFullPipeline.makePipeline(
            device: device,
            library: library,
            name: "flowMetalMassSummaryGyrationFinalize"
        )

        let vectorBytes = batchCount * MemoryLayout<Float>.stride
        let partialVectorBytes = batchCount * self.partialGroupCount * MemoryLayout<Float>.stride
        let circularVectorBytes = 4 * vectorBytes
        let partialCircularVectorBytes = 4 * partialVectorBytes
        self.occupancyThresholdBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
            device: device,
            length: MemoryLayout<Float>.stride,
            label: "flow-metal.summary.occupancy-threshold"
        )
        self.channelWeightsBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
            device: device,
            length: max(1, config.channels) * MemoryLayout<Float>.stride,
            label: "flow-metal.summary.channel-weights"
        )
        self.circularXWeightsBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
            device: device,
            length: config.sx * 4 * MemoryLayout<Float>.stride,
            label: "flow-metal.summary.circular-x-weights"
        )
        self.circularYWeightsBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
            device: device,
            length: config.sy * 4 * MemoryLayout<Float>.stride,
            label: "flow-metal.summary.circular-y-weights"
        )
        let twoPi = 2 * Float.pi
        let circularXWeights = (0..<config.sx).flatMap { index -> [Float] in
            let angle = (Float(index) + 0.5) * twoPi / Float(config.sx)
            return [cosf(angle), sinf(angle), cosf(2 * angle), sinf(2 * angle)]
        }
        let circularYWeights = (0..<config.sy).flatMap { index -> [Float] in
            let angle = (Float(index) + 0.5) * twoPi / Float(config.sy)
            return [cosf(angle), sinf(angle), cosf(2 * angle), sinf(2 * angle)]
        }
        FlowLeniaMetalFullPipeline.writeFloats(circularXWeights, to: circularXWeightsBuffer)
        FlowLeniaMetalFullPipeline.writeFloats(circularYWeights, to: circularYWeightsBuffer)
        self.partialTotalMassBuffer = FlowLeniaMetalFullPipeline.makePrivateBuffer(
            device: device,
            length: partialVectorBytes,
            label: "flow-metal.summary.partial-total-mass"
        )
        self.partialSumSquaresBuffer = FlowLeniaMetalFullPipeline.makePrivateBuffer(
            device: device,
            length: partialVectorBytes,
            label: "flow-metal.summary.partial-sum-squares"
        )
        self.partialEnergyBuffer = FlowLeniaMetalFullPipeline.makePrivateBuffer(
            device: device,
            length: partialVectorBytes,
            label: "flow-metal.summary.partial-energy"
        )
        self.partialWeightedXBuffer = FlowLeniaMetalFullPipeline.makePrivateBuffer(
            device: device,
            length: partialVectorBytes,
            label: "flow-metal.summary.partial-weighted-x"
        )
        self.partialWeightedYBuffer = FlowLeniaMetalFullPipeline.makePrivateBuffer(
            device: device,
            length: partialVectorBytes,
            label: "flow-metal.summary.partial-weighted-y"
        )
        self.partialOccupancyCountBuffer = FlowLeniaMetalFullPipeline.makePrivateBuffer(
            device: device,
            length: partialVectorBytes,
            label: "flow-metal.summary.partial-occupancy-count"
        )
        self.partialCircularFirstBuffer = FlowLeniaMetalFullPipeline.makePrivateBuffer(
            device: device,
            length: partialCircularVectorBytes,
            label: "flow-metal.summary.partial-circular-first"
        )
        self.partialCircularSecondBuffer = FlowLeniaMetalFullPipeline.makePrivateBuffer(
            device: device,
            length: partialCircularVectorBytes,
            label: "flow-metal.summary.partial-circular-second"
        )
        self.partialGyrationBuffer = FlowLeniaMetalFullPipeline.makePrivateBuffer(
            device: device,
            length: partialVectorBytes,
            label: "flow-metal.summary.partial-gyration"
        )
        self.totalMassBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
            device: device,
            length: vectorBytes,
            label: "flow-metal.summary.total-mass"
        )
        self.sumSquaresBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
            device: device,
            length: vectorBytes,
            label: "flow-metal.summary.sum-squares"
        )
        self.energyBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
            device: device,
            length: vectorBytes,
            label: "flow-metal.summary.energy"
        )
        self.weightedXBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
            device: device,
            length: vectorBytes,
            label: "flow-metal.summary.weighted-x"
        )
        self.weightedYBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
            device: device,
            length: vectorBytes,
            label: "flow-metal.summary.weighted-y"
        )
        self.occupancyCountBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
            device: device,
            length: vectorBytes,
            label: "flow-metal.summary.occupancy-count"
        )
        self.circularFirstBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
            device: device,
            length: circularVectorBytes,
            label: "flow-metal.summary.circular-first"
        )
        self.circularSecondBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
            device: device,
            length: circularVectorBytes,
            label: "flow-metal.summary.circular-second"
        )
        self.gyrationBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
            device: device,
            length: vectorBytes,
            label: "flow-metal.summary.gyration"
        )
    }

    func encodeSummary(
        on commandBuffer: MTLCommandBuffer,
        massBuffer: MTLBuffer,
        occupancyThreshold: Float,
        includeGyration: Bool,
        channelWeights: [Float]?
    ) {
        let resolvedWeights = channelWeights ?? Array(repeating: 1.0, count: channelCount)
        guard resolvedWeights.count == channelCount else {
            preconditionFailure("Flow Metal summary channel weights must match the configured channel count.")
        }
        FlowLeniaMetalFullPipeline.writeFloats([occupancyThreshold], to: occupancyThresholdBuffer)
        FlowLeniaMetalFullPipeline.writeFloats(resolvedWeights, to: channelWeightsBuffer)

        encodePass1(on: commandBuffer, massBuffer: massBuffer)
        if includeGyration {
            encodePass2(on: commandBuffer, massBuffer: massBuffer)
        }
    }

    func readSummary(includeGyration: Bool) -> FlowLeniaMetalMassSummary {
        let totalMass = FlowLeniaMetalFullPipeline.readFloats(from: totalMassBuffer, count: batchCount)
        let sumSquares = FlowLeniaMetalFullPipeline.readFloats(from: sumSquaresBuffer, count: batchCount)
        let energy = FlowLeniaMetalFullPipeline.readFloats(from: energyBuffer, count: batchCount)
        let weightedX = FlowLeniaMetalFullPipeline.readFloats(from: weightedXBuffer, count: batchCount)
        let weightedY = FlowLeniaMetalFullPipeline.readFloats(from: weightedYBuffer, count: batchCount)
        let occupancyCount = FlowLeniaMetalFullPipeline.readFloats(from: occupancyCountBuffer, count: batchCount)
        let centerXIndex = zip(weightedX, totalMass).map { weighted, total in
            total > 1e-6 ? weighted / total : 0.0
        }
        let centerYIndex = zip(weightedY, totalMass).map { weighted, total in
            total > 1e-6 ? weighted / total : 0.0
        }
        let rawGyration = includeGyration
            ? FlowLeniaMetalFullPipeline.readFloats(from: gyrationBuffer, count: batchCount)
            : nil

        return FlowLeniaMetalMassSummary(
            totalMass: totalMass,
            sumSquares: sumSquares,
            energy: energy,
            occupancyCount: occupancyCount,
            centerXIndex: centerXIndex,
            centerYIndex: centerYIndex,
            rawGyration: rawGyration
        )
    }

    private func encodePass1(on commandBuffer: MTLCommandBuffer, massBuffer: MTLBuffer) {
        guard let encoder = commandBuffer.makeComputeCommandEncoder() else {
            preconditionFailure("Failed to create Flow Metal summary encoder.")
        }
        encoder.setComputePipelineState(pass1PartialPipeline)
        encoder.setBuffer(massBuffer, offset: 0, index: 0)
        encoder.setBuffer(occupancyThresholdBuffer, offset: 0, index: 1)
        encoder.setBuffer(partialTotalMassBuffer, offset: 0, index: 2)
        encoder.setBuffer(partialSumSquaresBuffer, offset: 0, index: 3)
        encoder.setBuffer(partialEnergyBuffer, offset: 0, index: 4)
        encoder.setBuffer(partialWeightedXBuffer, offset: 0, index: 5)
        encoder.setBuffer(partialWeightedYBuffer, offset: 0, index: 6)
        encoder.setBuffer(partialOccupancyCountBuffer, offset: 0, index: 7)
        encoder.setBuffer(channelWeightsBuffer, offset: 0, index: 8)
        encoder.setBuffer(partialCircularFirstBuffer, offset: 0, index: 9)
        encoder.setBuffer(partialCircularSecondBuffer, offset: 0, index: 10)
        encoder.setBuffer(circularXWeightsBuffer, offset: 0, index: 11)
        encoder.setBuffer(circularYWeightsBuffer, offset: 0, index: 12)
        encoder.dispatchThreadgroups(
            MTLSize(width: partialGroupCount, height: 1, depth: batchCount),
            threadsPerThreadgroup: MTLSize(width: FlowLeniaMetalFullPipeline.summaryThreadCount, height: 1, depth: 1)
        )
        encoder.endEncoding()

        guard let finalizeEncoder = commandBuffer.makeComputeCommandEncoder() else {
            preconditionFailure("Failed to create Flow Metal summary finalize encoder.")
        }
        finalizeEncoder.setComputePipelineState(pass1FinalizePipeline)
        finalizeEncoder.setBuffer(partialTotalMassBuffer, offset: 0, index: 0)
        finalizeEncoder.setBuffer(partialSumSquaresBuffer, offset: 0, index: 1)
        finalizeEncoder.setBuffer(partialEnergyBuffer, offset: 0, index: 2)
        finalizeEncoder.setBuffer(partialWeightedXBuffer, offset: 0, index: 3)
        finalizeEncoder.setBuffer(partialWeightedYBuffer, offset: 0, index: 4)
        finalizeEncoder.setBuffer(partialOccupancyCountBuffer, offset: 0, index: 5)
        finalizeEncoder.setBuffer(totalMassBuffer, offset: 0, index: 6)
        finalizeEncoder.setBuffer(sumSquaresBuffer, offset: 0, index: 7)
        finalizeEncoder.setBuffer(energyBuffer, offset: 0, index: 8)
        finalizeEncoder.setBuffer(weightedXBuffer, offset: 0, index: 9)
        finalizeEncoder.setBuffer(weightedYBuffer, offset: 0, index: 10)
        finalizeEncoder.setBuffer(occupancyCountBuffer, offset: 0, index: 11)
        finalizeEncoder.setBuffer(partialCircularFirstBuffer, offset: 0, index: 12)
        finalizeEncoder.setBuffer(partialCircularSecondBuffer, offset: 0, index: 13)
        finalizeEncoder.setBuffer(circularFirstBuffer, offset: 0, index: 14)
        finalizeEncoder.setBuffer(circularSecondBuffer, offset: 0, index: 15)
        finalizeEncoder.dispatchThreadgroups(
            MTLSize(width: 1, height: 1, depth: batchCount),
            threadsPerThreadgroup: MTLSize(width: FlowLeniaMetalFullPipeline.summaryThreadCount, height: 1, depth: 1)
        )
        finalizeEncoder.endEncoding()
    }

    private func encodePass2(on commandBuffer: MTLCommandBuffer, massBuffer: MTLBuffer) {
        guard let encoder = commandBuffer.makeComputeCommandEncoder() else {
            preconditionFailure("Failed to create Flow Metal summary gyration encoder.")
        }
        encoder.setComputePipelineState(pass2PartialPipeline)
        encoder.setBuffer(massBuffer, offset: 0, index: 0)
        encoder.setBuffer(totalMassBuffer, offset: 0, index: 1)
        encoder.setBuffer(weightedXBuffer, offset: 0, index: 2)
        encoder.setBuffer(weightedYBuffer, offset: 0, index: 3)
        encoder.setBuffer(partialGyrationBuffer, offset: 0, index: 4)
        encoder.setBuffer(channelWeightsBuffer, offset: 0, index: 5)
        encoder.dispatchThreadgroups(
            MTLSize(width: partialGroupCount, height: 1, depth: batchCount),
            threadsPerThreadgroup: MTLSize(width: FlowLeniaMetalFullPipeline.summaryThreadCount, height: 1, depth: 1)
        )
        encoder.endEncoding()

        guard let finalizeEncoder = commandBuffer.makeComputeCommandEncoder() else {
            preconditionFailure("Failed to create Flow Metal summary gyration finalize encoder.")
        }
        finalizeEncoder.setComputePipelineState(pass2FinalizePipeline)
        finalizeEncoder.setBuffer(partialGyrationBuffer, offset: 0, index: 0)
        finalizeEncoder.setBuffer(totalMassBuffer, offset: 0, index: 1)
        finalizeEncoder.setBuffer(gyrationBuffer, offset: 0, index: 2)
        finalizeEncoder.dispatchThreadgroups(
            MTLSize(width: 1, height: 1, depth: batchCount),
            threadsPerThreadgroup: MTLSize(width: FlowLeniaMetalFullPipeline.summaryThreadCount, height: 1, depth: 1)
        )
        finalizeEncoder.endEncoding()
    }
}

final class FlowLeniaMetalScalarSummaryReducer: @unchecked Sendable {
    private let batchCount: Int
    private let partialGroupCount: Int
    private let commandQueue: MTLCommandQueue
    private let partialPipeline: MTLComputePipelineState
    private let finalizePipeline: MTLComputePipelineState
    private let partialSumsBuffer: MTLBuffer
    private let sumsBuffer: MTLBuffer

    init(
        batchCount: Int,
        partialGroupCount: Int,
        device: MTLDevice,
        commandQueue: MTLCommandQueue,
        library: MTLLibrary
    ) {
        self.batchCount = batchCount
        self.partialGroupCount = partialGroupCount
        self.commandQueue = commandQueue

        self.partialPipeline = FlowLeniaMetalFullPipeline.makePipeline(
            device: device,
            library: library,
            name: "flowMetalScalarSummaryPartial"
        )
        self.finalizePipeline = FlowLeniaMetalFullPipeline.makePipeline(
            device: device,
            library: library,
            name: "flowMetalScalarSummaryFinalize"
        )

        let vectorBytes = batchCount * MemoryLayout<Float>.stride
        let partialVectorBytes = batchCount * self.partialGroupCount * MemoryLayout<Float>.stride
        self.partialSumsBuffer = FlowLeniaMetalFullPipeline.makePrivateBuffer(
            device: device,
            length: partialVectorBytes,
            label: "flow-metal.scalar-summary.partial-sums"
        )
        self.sumsBuffer = FlowLeniaMetalFullPipeline.makeSharedBuffer(
            device: device,
            length: vectorBytes,
            label: "flow-metal.scalar-summary.sums"
        )
    }

    func summarize(buffer: MTLBuffer) -> [Float] {
        guard let commandBuffer = commandQueue.makeCommandBuffer() else {
            preconditionFailure("Failed to create Flow Metal scalar summary command buffer.")
        }
        commandBuffer.label = "flow-metal.scalar-summary"

        guard let encoder = commandBuffer.makeComputeCommandEncoder() else {
            preconditionFailure("Failed to create Flow Metal scalar summary encoder.")
        }
        encoder.setComputePipelineState(partialPipeline)
        encoder.setBuffer(buffer, offset: 0, index: 0)
        encoder.setBuffer(partialSumsBuffer, offset: 0, index: 1)
        encoder.dispatchThreadgroups(
            MTLSize(width: partialGroupCount, height: 1, depth: batchCount),
            threadsPerThreadgroup: MTLSize(width: FlowLeniaMetalFullPipeline.summaryThreadCount, height: 1, depth: 1)
        )
        encoder.endEncoding()

        guard let finalizeEncoder = commandBuffer.makeComputeCommandEncoder() else {
            preconditionFailure("Failed to create Flow Metal scalar summary finalize encoder.")
        }
        finalizeEncoder.setComputePipelineState(finalizePipeline)
        finalizeEncoder.setBuffer(partialSumsBuffer, offset: 0, index: 0)
        finalizeEncoder.setBuffer(sumsBuffer, offset: 0, index: 1)
        finalizeEncoder.dispatchThreadgroups(
            MTLSize(width: 1, height: 1, depth: batchCount),
            threadsPerThreadgroup: MTLSize(width: FlowLeniaMetalFullPipeline.summaryThreadCount, height: 1, depth: 1)
        )
        finalizeEncoder.endEncoding()

        commandBuffer.commit()
        commandBuffer.waitUntilCompleted()
        if let error = commandBuffer.error {
            preconditionFailure("Flow Metal scalar summary command buffer failed: \(error)")
        }

        return FlowLeniaMetalFullPipeline.readFloats(from: sumsBuffer, count: batchCount)
    }
}
