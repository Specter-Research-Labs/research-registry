import MLX
import XCTest
@testable import LeniaCore

/// Golden field hashes for the C engine. Kernel spectra, parameters and initial mass come from
/// exact integer formulas instead of MLX's FFT and random generators, so any host that builds the
/// engine must reproduce these bits; MLX only packs and transposes the arrays.
final class FlowLeniaCPUGoldenTests: XCTestCase {
    private static let golden: [String: [Int: String]] = [
        "torus 32x32": [1: "24e4bbaeba23ca64", 8: "0bf5334ef0ae51a8", 32: "26c70a45738f2666"],
        "torus 64x32": [1: "99aaf74ec598c8dc", 8: "54c8b819db4b0b82", 32: "596bdb7db18a2e35"],
        "wall 32x32": [1: "94437581b257c937", 8: "54fa12987aa8aae4", 32: "4744f8cd326e1536"],
        "wall 32x64": [1: "ab2269701e0352f0", 8: "972db98f8899d1f3", 32: "d7c4c4fc96f75947"],
    ]

    override func setUpWithError() throws {
        #if canImport(Metal)
        try LeniaMetalLibrarySupport.ensureAvailable()
        #endif
    }

    func testFieldHashesMatchGolden() {
        for (border, sx, sy) in [("torus", 32, 32), ("torus", 64, 32), ("wall", 32, 32), ("wall", 32, 64)] {
            let name = "\(border) \(sx)x\(sy)"
            let runner = goldenRunner(border: border, sx: sx, sy: sy)
            var completed = 0
            for step in [1, 8, 32] {
                runner.step(count: step - completed)
                completed = step
                let hash = fnv1a(runner.materializeMass().asArray(Float.self))
                print("CPU_GOLDEN \(name) step=\(step) hash=\(hash)")
                XCTAssertEqual(hash, Self.golden[name]?[step], "\(name) step \(step)")
            }
        }
    }

    /// The engine's twiddles are Double cos and sin rounded to Float. Hosts whose libm differs by
    /// an ulp still round to the same Float as long as no twiddle sits near a rounding boundary.
    func testTwiddlesAreFarFromFloatRoundingBoundaries() {
        for length in [32, 64] {
            for m in 0..<length {
                let angle = -2.0 * Double.pi * Double(m) / Double(length)
                for value in [cos(angle), sin(angle)] {
                    var below = value, above = value
                    for _ in 0..<2 {
                        below = below.nextDown
                        above = above.nextUp
                    }
                    XCTAssertEqual(Float(below), Float(value), "length \(length), m \(m)")
                    XCTAssertEqual(Float(above), Float(value), "length \(length), m \(m)")
                }
            }
        }
    }

    private func goldenRunner(border: String, sx: Int, sy: Int) -> FlowLeniaCPUStateRunner {
        let batchCount = 2, channels = 2, kernelCount = 3
        let config = BatchedConfig(
            sx: sx, sy: sy, channels: channels, nbK: kernelCount, dt: 0.2, dd: 5, sigma: 0.65, n: 2, thetaA: 2,
            border: border,
            implementation: ImplementationSettings(
                mode: "custom", border: border, gradientBoundary: border == "torus" ? "periodic" : "zero_pad",
                alphaMode: "mass", kernelProfile: "flowlenia_2022_paper_equations", flowClip: "none"
            ),
            chemChannel: nil, chemIncludeInMass: false
        )
        // Real low-pass spectra 1 / (1 + |k|^2 / c) with signed integer wavenumbers: point
        // symmetric, normalized to unit mass, and anisotropic in physical units on non-square grids.
        var spectra = [Float]()
        for b in 0..<batchCount {
            for kx in 0..<sx {
                for ky in 0..<sy {
                    for k in 0..<kernelCount {
                        let fx = Double(min(kx, sx - kx)), fy = Double(min(ky, sy - ky))
                        spectra.append(Float(1.0 / (1.0 + (fx * fx + fy * fy) / Double(1 + k + 2 * b))))
                    }
                }
            }
        }
        let kernels = CompiledKernels(
            fK: MLXArray(spectra).reshaped([batchCount, sx, sy, kernelCount]).asType(.complex64),
            m: MLXArray([Float](arrayLiteral: 0.15, 0.25, 0.35, 0.2, 0.3, 0.4)).reshaped([batchCount, kernelCount]),
            s: MLXArray([Float](arrayLiteral: 0.05, 0.08, 0.1, 0.06, 0.09, 0.12)).reshaped([batchCount, kernelCount]),
            h: MLXArray([Float](arrayLiteral: 0.4, 0.6, 0.8, 0.5, 0.7, 0.9)).reshaped([batchCount, kernelCount]),
            c0Idxs: MLXArray([Int32](arrayLiteral: 0, 1, 1)),
            c1Mask: MLXArray([Float](arrayLiteral: 1, 0, 1, 0, 1, 1)).reshaped([channels, kernelCount])
        )
        // Mass fills the cells within 7 x 4 of a corner, so it wraps into one body on a torus and
        // presses into four corners inside walls; a transposed axis moves it.
        var state: UInt32 = 0x9e37_79b9
        var mass = [Float]()
        var params = [Float]()
        for b in 0..<batchCount {
            for x in 0..<sx {
                for y in 0..<sy {
                    let inside = min(x, sx - 1 - x) < 7 && min(y, sy - 1 - y) < 4
                    for _ in 0..<channels {
                        state = state &* 1_664_525 &+ 1_013_904_223
                        mass.append(inside ? Float(state >> 8) / Float(1 << 24) : 0)
                    }
                    for k in 0..<kernelCount {
                        params.append(Float(4 + k + 2 * b + x % 3) * 0.125)
                    }
                }
            }
        }
        let runner = FlowLeniaCPUStateRunner(
            config: config, kernels: kernels, batchCount: batchCount, wallPotential: nil, matterWeights: nil
        )
        runner.reset(
            mass: MLXArray(mass).reshaped([batchCount, sx, sy, channels]),
            params: MLXArray(params).reshaped([batchCount, sx, sy, kernelCount]),
            wallMask: nil, staticChannelFields: [], food: nil, mixStep: 0
        )
        return runner
    }

    private func fnv1a(_ values: [Float]) -> String {
        var hash: UInt64 = 0xcbf2_9ce4_8422_2325
        for value in values {
            var bits = value.bitPattern
            for _ in 0..<4 {
                hash ^= UInt64(bits & 0xff)
                hash = hash &* 0x0000_0100_0000_01b3
                bits >>= 8
            }
        }
        return String(format: "%016llx", hash)
    }
}
