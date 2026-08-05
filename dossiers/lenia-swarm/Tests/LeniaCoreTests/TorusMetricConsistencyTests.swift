import Metal
import XCTest
@testable import LeniaCore

final class TorusMetricConsistencyTests: XCTestCase {
    private func translated(
        _ field: [Float],
        width: Int,
        height: Int,
        shiftX: Int,
        shiftY: Int
    ) -> [Float] {
        var result = [Float](repeating: 0, count: field.count)
        for y in 0..<height {
            for x in 0..<width {
                let movedX = (x + shiftX + width) % width
                let movedY = (y + shiftY + height) % height
                result[movedY * width + movedX] = field[y * width + x]
            }
        }
        return result
    }

    private func summary(_ field: [Float], width: Int, height: Int) -> (
        fingerprint: Data,
        centerX: Float,
        centerY: Float,
        gyration: Float
    ) {
        let result = morphospaceFinalSampleSummary(
            materialized: MassBatchCPU(
                flat: field,
                batch: 1,
                height: height,
                width: width,
                sampleSize: width * height
            ),
            sampleIndex: 0,
            occupancyThreshold: 0.1,
            useTorus: true
        )
        return (result.fingerprintU8, result.centerX, result.centerY, result.finalGyration)
    }

    private func wrappedDelta(_ value: Float, period: Float) -> Float {
        value - round(value / period) * period
    }

    func testAntipodalCanonicalCenterAndMomentsAreTranslationInvariant() throws {
        let width = 16
        let height = 12
        var field = [Float](repeating: 0, count: width * height)
        field[2 * width + 2] = 1
        field[7 * width + 10] = 1
        field[3 * width + 2] = 0.4
        field[8 * width + 10] = 0.4
        let shiftX = 3
        let shiftY = -4
        let moved = translated(
            field,
            width: width,
            height: height,
            shiftX: shiftX,
            shiftY: shiftY
        )

        let original = summary(field, width: width, height: height)
        let shifted = summary(moved, width: width, height: height)

        XCTAssertEqual(original.fingerprint, shifted.fingerprint)
        XCTAssertEqual(original.gyration, shifted.gyration, accuracy: 1e-5)
        XCTAssertEqual(
            wrappedDelta(shifted.centerX - original.centerX, period: Float(width)),
            Float(shiftX),
            accuracy: 1e-5
        )
        XCTAssertEqual(
            wrappedDelta(shifted.centerY - original.centerY, period: Float(height)),
            Float(shiftY),
            accuracy: 1e-5
        )

        let originalMoments = computeMomentsBatch(
            materialized: morphospaceCenteredMassBatch(
                MassBatchCPU(
                    flat: field,
                    batch: 1,
                    height: height,
                    width: width,
                    sampleSize: width * height
                ),
                useTorus: true
            ),
            config: MomentsConfig(enabled: true)
        )
        let shiftedMoments = computeMomentsBatch(
            materialized: morphospaceCenteredMassBatch(
                MassBatchCPU(
                    flat: moved,
                    batch: 1,
                    height: height,
                    width: width,
                    sampleSize: width * height
                ),
                useTorus: true
            ),
            config: MomentsConfig(enabled: true)
        )
        for (lhs, rhs) in zip(originalMoments.hu[0], shiftedMoments.hu[0]) {
            XCTAssertEqual(lhs, rhs, accuracy: 1e-5)
        }
        for (lhs, rhs) in zip(originalMoments.flusser[0], shiftedMoments.flusser[0]) {
            XCTAssertEqual(lhs, rhs, accuracy: 1e-5)
        }
        XCTAssertEqual(
            originalMoments.anisotropy[0],
            shiftedMoments.anisotropy[0],
            accuracy: 1e-5
        )
    }

    func testRolloutFallbackUsesCanonicalPhysicalAxisGeometry() throws {
        let xCount = 16
        let yCount = 12
        var field = [Float](repeating: 0, count: xCount * yCount)
        field[2 * xCount + 2] = 1
        field[7 * xCount + 10] = 1
        var xMajor = [Float](repeating: 0, count: field.count)
        for x in 0..<xCount {
            for y in 0..<yCount {
                xMajor[x * yCount + y] = field[y * xCount + x]
            }
        }

        let rollout = try XCTUnwrap(searchRolloutTorusGeometry(
            batchData: MassBatchCPU(
                flat: xMajor,
                batch: 1,
                height: xCount,
                width: yCount,
                sampleSize: xCount * yCount
            ),
            sampleIndex: 0,
            xCount: xCount,
            yCount: yCount
        ))
        let terminal = try XCTUnwrap(morphospaceFieldGeometry(
            sample: field,
            width: xCount,
            height: yCount,
            useTorus: true
        ))

        XCTAssertEqual(rollout.centerX, terminal.centerX, accuracy: 1e-6)
        XCTAssertEqual(rollout.centerY, terminal.centerY, accuracy: 1e-6)
        XCTAssertEqual(rollout.gyration, terminal.gyration, accuracy: 1e-6)
    }

    func testWallGeometryRemainsCartesian() throws {
        let width = 16
        let height = 4
        var field = [Float](repeating: 0, count: width * height)
        field[2 * width] = 1
        field[2 * width + 15] = 1

        let wall = try XCTUnwrap(morphospaceFieldGeometry(
            sample: field,
            width: width,
            height: height,
            useTorus: false
        ))
        let torus = try XCTUnwrap(morphospaceFieldGeometry(
            sample: field,
            width: width,
            height: height,
            useTorus: true
        ))

        XCTAssertEqual(wall.centerX, 8, accuracy: 1e-6)
        XCTAssertEqual(wall.gyration, 56.25, accuracy: 1e-6)
        XCTAssertEqual(torus.gyration, 0.25, accuracy: 1e-5)
    }

    func testMetalSummaryMatchesCanonicalTorusGeometryAcrossSeam() throws {
        let width = 16
        let height = 8
        var field = [Float](repeating: 0, count: width * height)
        field[3 * width + 15] = 1
        field[3 * width] = 2
        field[3 * width + 1] = 1
        let expected = try XCTUnwrap(morphospaceFieldGeometry(
            sample: field,
            width: width,
            height: height,
            useTorus: true
        ))
        var xMajor = [Float](repeating: 0, count: field.count)
        for x in 0..<width {
            for y in 0..<height {
                xMajor[x * height + y] = field[y * width + x]
            }
        }

        guard let device = MTLCreateSystemDefaultDevice(),
              let queue = device.makeCommandQueue() else {
            throw XCTSkip("Metal is unavailable")
        }
        let implementation = ImplementationSettings(
            mode: "flowlenia_2022_paper_equations",
            border: "torus",
            gradientBoundary: "periodic",
            alphaMode: "mass",
            kernelProfile: "flowlenia_2022_paper_equations",
            flowClip: "none"
        )
        let config = BatchedConfig(
            sx: width,
            sy: height,
            channels: 1,
            nbK: 1,
            dt: 0.2,
            dd: 2,
            sigma: 0.65,
            n: 2,
            thetaA: 2,
            border: "torus",
            implementation: implementation,
            chemChannel: nil,
            chemIncludeInMass: true
        )
        let library = FlowLeniaMetalFullPipeline.makeLibrary(
            device: device,
            source: FlowLeniaMetalFullPipeline.kernelSource(
                kernelCount: 1,
                parameterCount: 1,
                batchCount: 1,
                channelCount: 1,
                kernelBatchCount: 1,
                summaryPartialGroupCount: FlowLeniaMetalFullPipeline.summaryPartialGroupCount(
                    sx: width,
                    sy: height
                ),
                sx: width,
                sy: height,
                dt: config.dt,
                dd: config.dd,
                sigma: config.sigma,
                thetaA: config.thetaA,
                n: config.n,
                useTorus: true,
                alphaMode: config.implementation.alphaMode,
                flowClip: config.implementation.flowClip,
                parameterFieldMode: .kernelGain,
                reintegrateParams: true,
                parameterMixMode: .average
            )
        )
        let reducer = FlowLeniaMetalSummaryReducer(
            config: config,
            batchCount: 1,
            device: device,
            library: library
        )
        let maybeBuffer: MTLBuffer? = xMajor.withUnsafeBytes { bytes in
            guard let baseAddress = bytes.baseAddress else { return nil }
            return device.makeBuffer(
                bytes: baseAddress,
                length: bytes.count,
                options: .storageModeShared
            )
        }
        let buffer = try XCTUnwrap(maybeBuffer)
        let commandBuffer = try XCTUnwrap(queue.makeCommandBuffer())
        reducer.encodeSummary(
            on: commandBuffer,
            massBuffer: buffer,
            occupancyThreshold: 0.1,
            includeGyration: true,
            channelWeights: nil
        )
        commandBuffer.commit()
        commandBuffer.waitUntilCompleted()
        let summary = reducer.readSummary(includeGyration: true)

        XCTAssertEqual(summary.centerXIndex[0] + 0.5, expected.centerX, accuracy: 1e-4)
        XCTAssertEqual(summary.centerYIndex[0] + 0.5, expected.centerY, accuracy: 1e-4)
        XCTAssertEqual(summary.rawGyration?[0] ?? -1, expected.gyration, accuracy: 1e-4)
    }

}
