#if canImport(Metal)
import Foundation
import Metal
import MLX

struct FlowLeniaMetalSensing {
    let fieldMassBuffer: MTLBuffer
    let pressureMassBuffer: MTLBuffer
}

final class FlowLeniaMetalPhantom {
    let pressure: Bool
    /// Number of real steps the phantom has been advanced through. A replayed
    /// phantom is the solo trajectory of its initial field at this step.
    private(set) var step = 0

    private let elementCount: Int
    private let device: MTLDevice
    private let commandQueue: MTLCommandQueue
    private let sensePipeline: MTLComputePipelineState
    private let sensedBuffer: MTLBuffer
    private var fieldBuffer: MTLBuffer
    private var nextFieldBuffer: MTLBuffer
    private let replayPipeline: FlowLeniaMetalFullPipeline?
    private let replayParamsBuffer: MTLBuffer?

    init(
        spec: FlowLeniaPhantomSpec,
        config: BatchedConfig,
        kernels: CompiledKernels,
        device: MTLDevice,
        commandQueue: MTLCommandQueue,
        wallPotential: MLXArray?,
        matterWeights: [Float]
    ) {
        elementCount = config.sx * config.sy * config.channels
        guard spec.field.count == elementCount,
              spec.field.allSatisfy({ $0.isFinite && $0 >= 0 }) else {
            preconditionFailure("Phantom field must be finite, nonnegative, and shaped [sx, sy, channels].")
        }
        pressure = spec.pressure
        self.device = device
        self.commandQueue = commandQueue
        let library = FlowLeniaMetalFullPipeline.makeLibrary(device: device, source: Self.kernelSource)
        sensePipeline = FlowLeniaMetalFullPipeline.makePipeline(device: device, library: library, name: "flowMetalPhantomSense")
        let bytes = elementCount * MemoryLayout<Float>.stride
        sensedBuffer = FlowLeniaMetalFullPipeline.makePrivateBuffer(device: device, length: bytes, label: "flow-metal.phantom.sensed")
        fieldBuffer = FlowLeniaMetalFullPipeline.makePrivateBuffer(device: device, length: bytes, label: "flow-metal.phantom.field")
        nextFieldBuffer = FlowLeniaMetalFullPipeline.makePrivateBuffer(device: device, length: bytes, label: "flow-metal.phantom.nextField")
        FlowLeniaMetalFullPipeline.uploadFloats(
            spec.field,
            toPrivate: fieldBuffer,
            device: device,
            commandQueue: commandQueue,
            label: "flow-metal.phantom.field"
        )
        switch spec.source {
        case .fixed:
            replayPipeline = nil
            replayParamsBuffer = nil
        case .replay:
            // The replay owns a second pipeline so the real pipeline's last U and
            // flow stay those of the real step.
            replayPipeline = FlowLeniaMetalFullPipeline(
                config: config,
                kernels: kernels,
                batchCount: 1,
                device: device,
                commandQueue: commandQueue,
                wallPotential: wallPotential,
                matterWeights: matterWeights,
                parameterFieldMode: .kernelGain,
                reintegrateParams: false
            )
            let gains = kernels.h.asArray(Float.self)
            let cellCount = config.sx * config.sy
            let params = (0..<cellCount).flatMap { _ in gains }
            let paramsBuffer = FlowLeniaMetalFullPipeline.makePrivateBuffer(
                device: device,
                length: params.count * MemoryLayout<Float>.stride,
                label: "flow-metal.phantom.params"
            )
            FlowLeniaMetalFullPipeline.uploadFloats(
                params,
                toPrivate: paramsBuffer,
                device: device,
                commandQueue: commandQueue,
                label: "flow-metal.phantom.params"
            )
            replayParamsBuffer = paramsBuffer
        }
    }

    func encodeSensing(on commandBuffer: MTLCommandBuffer, massBuffer: MTLBuffer) -> FlowLeniaMetalSensing {
        guard let encoder = commandBuffer.makeComputeCommandEncoder() else {
            preconditionFailure("Failed to create Flow Metal phantom encoder.")
        }
        var count = UInt32(elementCount)
        encoder.setComputePipelineState(sensePipeline)
        encoder.setBuffer(massBuffer, offset: 0, index: 0)
        encoder.setBuffer(fieldBuffer, offset: 0, index: 1)
        encoder.setBuffer(sensedBuffer, offset: 0, index: 2)
        encoder.setBytes(&count, length: MemoryLayout<UInt32>.stride, index: 3)
        encoder.dispatchThreads(
            MTLSize(width: elementCount, height: 1, depth: 1),
            threadsPerThreadgroup: MTLSize(width: min(elementCount, sensePipeline.maxTotalThreadsPerThreadgroup), height: 1, depth: 1)
        )
        encoder.endEncoding()
        return FlowLeniaMetalSensing(
            fieldMassBuffer: sensedBuffer,
            pressureMassBuffer: pressure ? sensedBuffer : massBuffer
        )
    }

    func encodeAdvance(on commandBuffer: MTLCommandBuffer) {
        step += 1
        guard let replayPipeline, let replayParamsBuffer else {
            return
        }
        replayPipeline.encodeStep(
            on: commandBuffer,
            preparedMassBuffer: fieldBuffer,
            paramsBuffer: replayParamsBuffer,
            nextMassBuffer: nextFieldBuffer,
            nextParamsBuffer: replayParamsBuffer
        )
        swap(&fieldBuffer, &nextFieldBuffer)
    }

    func materializeField() -> [Float] {
        FlowLeniaMetalFullPipeline.copyFloatsFromGPUBuffer(
            fieldBuffer,
            count: elementCount,
            device: device,
            commandQueue: commandQueue,
            label: "flow-metal.phantom.field"
        )
    }

    private static let kernelSource = """
    #include <metal_stdlib>
    using namespace metal;

    kernel void flowMetalPhantomSense(
        device const float *mass [[buffer(0)]],
        device const float *phantom [[buffer(1)]],
        device float *sensed [[buffer(2)]],
        constant uint &count [[buffer(3)]],
        uint gid [[thread_position_in_grid]]
    ) {
        if (gid >= count) {
            return;
        }
        sensed[gid] = mass[gid] + phantom[gid];
    }
    """
}

#endif
