#if canImport(Metal)
import Foundation
import Metal

/// Passive founder bookkeeping for resident Metal Flow Lenia.
///
/// Each channel's matter carries founder masses B[c, j] with sum_j B[c, j] = A[c]. B is moved by the same
/// reintegration weights as A, so B[c, j] / A[c] is the mass-weighted average of the incoming founder
/// fractions. Tracking per channel keeps labels exact when channels follow different flows. Cells that
/// receive no matter receive no founder mass, so no fraction is defined there.
final class FlowLeniaMetalAncestryTracer {
    let founderCount: Int
    private let pipeline: MTLComputePipelineState
    private let sx: Int
    private let sy: Int
    private let batchCount: Int

    init(
        device: MTLDevice,
        config: BatchedConfig,
        batchCount: Int,
        founderCount: Int
    ) {
        precondition(founderCount > 0, "Ancestry tracing requires at least one founder.")
        self.founderCount = founderCount
        self.sx = config.sx
        self.sy = config.sy
        self.batchCount = batchCount
        let library = FlowLeniaMetalFullPipeline.makeLibrary(
            device: device,
            source: Self.kernelSource(
                batchCount: batchCount,
                channelCount: config.channels,
                founderCount: founderCount,
                sx: config.sx,
                sy: config.sy,
                dt: config.dt,
                dd: config.dd,
                sigma: config.sigma,
                useTorus: config.border == "torus"
            )
        )
        self.pipeline = FlowLeniaMetalFullPipeline.makePipeline(
            device: device,
            library: library,
            name: "flowMetalReintegrateAncestry"
        )
    }

    /// Must be encoded after the step's flow and before the next step overwrites it; `massBuffer` is the
    /// pre-step mass that the flow was computed from.
    func encode(
        on commandBuffer: MTLCommandBuffer,
        massBuffer: MTLBuffer,
        flowBuffer: MTLBuffer,
        ancestryBuffer: MTLBuffer,
        nextAncestryBuffer: MTLBuffer
    ) {
        guard let encoder = commandBuffer.makeComputeCommandEncoder() else {
            preconditionFailure("Failed to create Flow Metal ancestry encoder.")
        }
        encoder.setComputePipelineState(pipeline)
        encoder.setBuffer(massBuffer, offset: 0, index: 0)
        encoder.setBuffer(flowBuffer, offset: 0, index: 1)
        encoder.setBuffer(ancestryBuffer, offset: 0, index: 2)
        encoder.setBuffer(nextAncestryBuffer, offset: 0, index: 3)
        let threadWidth = max(1, pipeline.threadExecutionWidth)
        let threadHeight = min(8, max(1, pipeline.maxTotalThreadsPerThreadgroup / threadWidth))
        encoder.dispatchThreads(
            MTLSize(width: sy, height: sx, depth: batchCount),
            threadsPerThreadgroup: MTLSize(width: threadWidth, height: threadHeight, depth: 1)
        )
        encoder.endEncoding()
    }

    static func kernelSource(
        batchCount: Int,
        channelCount: Int,
        founderCount: Int,
        sx: Int,
        sy: Int,
        dt: Float,
        dd: Int,
        sigma: Float,
        useTorus: Bool
    ) -> String {
        let clipMax = min(1.0 as Float, sigma * 2.0)
        let maxAdvection = Float(dd) - sigma
        let areaScale = Float(1.0 / Double(4.0 * sigma * sigma))
        let distanceBody = FlowLeniaMetalFullPipeline.reintegrateDistanceBody(
            sx: sx, sy: sy, dd: dd, maxAdvection: maxAdvection, useTorus: useTorus)
        return """
        #include <metal_stdlib>
        using namespace metal;

        constant int kBatchCount = \(batchCount);
        constant int kChannelCount = \(channelCount);
        constant int kFounderCount = \(founderCount);
        constant int kSX = \(sx);
        constant int kSY = \(sy);
        constant float kDt = \(dt)f;
        constant float kSigma = \(sigma)f;
        constant float kClipMax = \(clipMax)f;
        constant float kMaxAdvection = \(maxAdvection)f;
        constant float kAreaScale = \(areaScale)f;

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

        kernel void flowMetalReintegrateAncestry(
            device const float *mass [[buffer(0)]],
            device const float *flow [[buffer(1)]],
            device const float *ancestry [[buffer(2)]],
            device float *nextAncestry [[buffer(3)]],
            uint3 gid [[thread_position_in_grid]]
        ) {
            \(FlowLeniaMetalFullPipeline.transportFloatPragma)
            if (int(gid.y) >= kSX || int(gid.x) >= kSY || int(gid.z) >= kBatchCount) {
                return;
            }
            int batch = int(gid.z);
            int x = int(gid.y);
            int y = int(gid.x);
            float targetY = float(y) + 0.5f;
            float targetX = float(x) + 0.5f;
            float total[kChannelCount * kFounderCount];
            for (int i = 0; i < kChannelCount * kFounderCount; ++i) {
                total[i] = 0.0f;
            }
            for (int dx = -\(dd); dx <= \(dd); ++dx) {
                for (int dy = -\(dd); dy <= \(dd); ++dy) {
                    int srcX = wrappedX(x - dx);
                    int srcY = wrappedY(y - dy);
                    int sourceCell = (batch * kSX + srcX) * kSY + srcY;
                    for (int c = 0; c < kChannelCount; ++c) {
                        // Same gate and weights as the mass kernel, so founder mass follows its channel exactly.
                        if (mass[sourceCell * kChannelCount + c] > 0.0f) {
                            int sourceFlowIndex = (sourceCell * kChannelCount + c) * 2;
                            float flowX = flow[sourceFlowIndex];
                            float flowY = flow[sourceFlowIndex + 1];
                            float clippedY = metal::fmin(metal::fmax(flowY * kDt, -kMaxAdvection), kMaxAdvection);
                            float clippedX = metal::fmin(metal::fmax(flowX * kDt, -kMaxAdvection), kMaxAdvection);
        \(distanceBody)
                            float szY = metal::fmin(metal::fmax(0.5f - dY + kSigma, 0.0f), kClipMax);
                            float szX = metal::fmin(metal::fmax(0.5f - dX + kSigma, 0.0f), kClipMax);
                            int sourceBase = (sourceCell * kChannelCount + c) * kFounderCount;
                            for (int j = 0; j < kFounderCount; ++j) {
                                total[c * kFounderCount + j] += ancestry[sourceBase + j] * szY * szX;
                            }
                        }
                    }
                }
            }
            int outputBase = ((batch * kSX + x) * kSY + y) * kChannelCount * kFounderCount;
            for (int i = 0; i < kChannelCount * kFounderCount; ++i) {
                nextAncestry[outputBase + i] = total[i] * kAreaScale;
            }
        }
        """
    }
}

#endif
