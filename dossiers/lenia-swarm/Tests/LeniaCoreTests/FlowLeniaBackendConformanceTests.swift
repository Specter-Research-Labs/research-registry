#if canImport(Metal)
import MLX
import XCTest
@testable import LeniaCore

/// MLX, metal-full and the C engine implement one field step. The author's JAX fixture and the
/// small ramp, impulse and patch fields must agree within 1e-4, the shared Metal fixture pins
/// tt_backend's numpy reference, and long random runs judge the C engine against Metal's own
/// one-ulp sensitivity.
final class FlowLeniaBackendConformanceTests: XCTestCase {
    override func setUpWithError() throws {
        try LeniaMetalLibrarySupport.ensureAvailable()
    }

    func testMatchesPinnedAuthorJAXAtOneAndEightSteps() throws {
        struct Fixture: Decodable {
            let input: String
            let steps: [String: String]
        }
        let url = try XCTUnwrap(Bundle.module.url(forResource: "flowlenia-author", withExtension: "json"))
        let fixture = try JSONDecoder().decode(Fixture.self, from: Data(contentsOf: url))
        func field(_ encoded: String) throws -> MLXArray {
            MLXArray(try littleEndianFloats(base64: encoded)).reshaped([32, 32, 2])
        }
        let runtime = interactiveRuntimeConfig(backend: .mlx, authorReference: true)
        let cfg = batchedConfigFromRuntime(runtime)
        let kernels = compileKernels(params: runtime.params, config: cfg, c0: runtime.c0, c1: runtime.c1)
        let direct = FlowLeniaBatched(config: cfg, kernels: kernels)
        var state = try field(fixture.input).expandedDimensions(axis: 0)
        for step in 1...8 {
            state = direct.stepUncompiled(state)
            if step == 1 || step == 8 {
                let difference = maxAbsDifference(state[0], try field(XCTUnwrap(fixture.steps[String(step)])))
                print("AUTHOR_REFERENCE backend=mlx-uncompiled step=\(step) max_abs=\(difference)")
                XCTAssertLessThan(difference, 1e-4)
            }
        }
        for backend in [FlowLeniaComputeBackend.mlx, .metalFull, .cpu] {
            let simulator = FlowLeniaInteractiveSimulator(
                runtimeConfig: interactiveRuntimeConfig(backend: backend, authorReference: true))
            let initial = FlowLeniaInteractiveState(step: 0, mass: try field(fixture.input), params: nil, food: nil)
            for step in [1, 8] {
                let actual = simulator.step(initial, count: step)
                let expected = try field(XCTUnwrap(fixture.steps[String(step)]))
                let difference = maxAbsDifference(actual.mass, expected)
                print("AUTHOR_REFERENCE backend=\(backend) step=\(step) max_abs=\(difference)")
                XCTAssertLessThan(difference, 1e-4)
            }
        }
    }

    /// flowlenia-metal-torus.json is the fixture that tt_backend's numpy reference is pinned to, so
    /// this keeps it tied to the kernels Swift compiles and the mass metal-full produces.
    func testMetalReproducesSharedReferenceFixture() throws {
        struct Encoded: Decodable {
            let shape: [Int]
            let data: String
        }
        struct Fixture: Decodable {
            let kernel_fK_re: Encoded
            let kernel_fK_im: Encoded
            let kernel_m: Encoded
            let kernel_s: Encoded
            let kernel_h: Encoded
            let kernel_c1_mask: Encoded
            let kernel_c0: [Int]
            let mass: [String: Encoded]
        }
        func array(_ encoded: Encoded) throws -> MLXArray {
            MLXArray(try littleEndianFloats(base64: encoded.data)).reshaped(encoded.shape)
        }
        let url = try XCTUnwrap(Bundle.module.url(forResource: "flowlenia-metal-torus", withExtension: "json"))
        let fixture = try JSONDecoder().decode(Fixture.self, from: Data(contentsOf: url))
        let runtime = interactiveRuntimeConfig(backend: .metalFull)
        let config = batchedConfigFromRuntime(runtime)
        let kernels = compileKernels(params: runtime.params, config: config, c0: runtime.c0, c1: runtime.c1)
        XCTAssertEqual(runtime.c0, fixture.kernel_c0)
        for (name, actual, expected) in [
            ("fK_re", kernels.fK.realPart(), fixture.kernel_fK_re), ("fK_im", kernels.fK.imaginaryPart(), fixture.kernel_fK_im),
            ("m", kernels.m, fixture.kernel_m), ("s", kernels.s, fixture.kernel_s), ("h", kernels.h, fixture.kernel_h),
            ("c1_mask", kernels.c1Mask, fixture.kernel_c1_mask),
        ] {
            XCTAssertLessThan(maxAbsDifference(actual, try array(expected)), 1e-6, name)
        }
        let initial = try array(XCTUnwrap(fixture.mass["0"]))
        let metal = FlowLeniaMetalFullStateRunner(config: config, kernels: kernels, batchCount: 1, reintegrateParams: false)
        let params = MLX.broadcast(kernels.h.reshaped([1, 1, 1, runtime.nbK]), to: [1, runtime.sx, runtime.sy, runtime.nbK])
        metal.reset(mass: initial, params: params, wallMask: nil, staticChannelFields: [], food: nil, mixStep: 0)
        var completed = 0
        for step in [1, 8] {
            metal.step(count: step - completed)
            completed = step
            let difference = maxAbsDifference(metal.materializeMass(), try array(XCTUnwrap(fixture.mass[String(step)])))
            print("CONFORMANCE shared_reference step=\(step) metal_max_abs=\(difference)")
            XCTAssertLessThan(difference, 1e-5)
        }
    }

    /// Ramps vary along one axis only, so a backend that swaps grid axes or flow components moves
    /// mass across the other axis; the grids are non-square in both orientations to catch it.
    /// Impulses sit on the torus seam and in a wall corner, where wrapped and clamped sources differ.
    /// A uniform ramp is unstable: a one-ulp change of its mass grows about threefold per step, to
    /// 1e-3 by step 8, so ramps are compared up to step 3 and the stable inputs up to step 8.
    func testSmallFieldsAgreeAcrossBackends() throws {
        for border in ["torus", "wall"] {
            for (input, sx, sy, lastStep) in [
                ("ramp_x", 64, 32, 3), ("ramp_y", 32, 64, 3), ("impulse", 32, 32, 8), ("patch", 64, 32, 8), ("patch", 32, 64, 8),
            ] {
                let name = "\(border) \(input) \(sx)x\(sy)"
                let fixture = try smallFixture(border: border, input: input, sx: sx, sy: sy)
                let mlx = FlowLeniaBatched(config: fixture.config, kernels: fixture.kernels)
                let metal = FlowLeniaMetalFullStateRunner(
                    config: fixture.config, kernels: fixture.kernels, batchCount: fixture.batchCount, reintegrateParams: false)
                metal.reset(mass: fixture.mass, params: fixture.params, wallMask: nil, staticChannelFields: [], food: nil, mixStep: 0)
                let cpu = FlowLeniaCPUStateRunner(
                    config: fixture.config, kernels: fixture.kernels, batchCount: fixture.batchCount, wallPotential: nil, matterWeights: nil)
                cpu.reset(mass: fixture.mass, params: fixture.params, wallMask: nil, staticChannelFields: [], food: nil, mixStep: 0)
                var mlxState = fixture.mass
                for step in 1...lastStep {
                    mlxState = mlx.step(mlxState)
                    metal.step(count: 1)
                    cpu.step(count: 1)
                    guard step == 1 || step == lastStep else { continue }
                    let metalState = metal.materializeMass()
                    let cpuState = cpu.materializeMass()
                    let metalError = maxAbsDifference(metalState, mlxState)
                    let cpuError = maxAbsDifference(cpuState, mlxState)
                    let motion = maxAbsDifference(mlxState, fixture.mass)
                    print("CONFORMANCE \(name) step=\(step) metal_vs_mlx=\(metalError) cpu_vs_mlx=\(cpuError) mlx_motion=\(motion)")
                    XCTAssertLessThan(metalError, 1e-4, "\(name) step \(step)")
                    XCTAssertLessThan(cpuError, 1e-4, "\(name) step \(step)")
                    XCTAssertGreaterThan(motion, 1e-3, "\(name) step \(step) is static")
                }
            }
        }
    }

    private struct SmallFixture {
        let config: BatchedConfig
        let kernels: CompiledKernels
        let batchCount: Int
        let mass: MLXArray
        let params: MLXArray
    }

    private func smallFixture(border: String, input: String, sx: Int, sy: Int) throws -> SmallFixture {
        let runtime = try loadPackageConfig("paper_random_2c_10k_128.json", overrides: [
            "profile": "experimental",
            "grid": ["sx": sx, "sy": sy],
            "reintegration": ["dd": 5, "sigma": 0.65, "border": border],
            "init": ["seed": 0, "patches": [["center": [sx / 4, sy / 3], "size": 16]], "a_uniform": ["low": 0, "high": 1], "p_uniform": NSNull()],
            "params.ranges.R": [6.0, 9.0],
        ])
        let config = batchedConfigFromRuntime(runtime)
        let ranges = try XCTUnwrap(runtime.randomParamRanges)
        let seeds = [11, 12]
        let kernels = compilePopulationKernels(
            paramsBatch: seeds.map { generateRandomParams(seed: $0, nbK: runtime.nbK, ranges: ranges) },
            config: config, c0: runtime.c0, c1: runtime.c1)
        let channels = runtime.channels
        let mass: MLXArray
        switch input {
        case "ramp_x", "ramp_y":
            let values = (0..<sx).flatMap { x in
                (0..<sy).flatMap { y in
                    (0..<channels).map { c in
                        Float((input == "ramp_x" ? x : y) + 1) / Float((input == "ramp_x" ? sx : sy) + 1) * (c == 0 ? 0.6 : 0.3)
                    }
                }
            }
            mass = MLX.stacked(seeds.map { _ in MLXArray(values).reshaped([sx, sy, channels]) })
        case "impulse":
            var values = [Float](repeating: 0, count: sx * sy * channels)
            for (x, y) in [(0, 0), (sx / 2, sy - 1), (sx / 2, sy / 2)] {
                for c in 0..<channels { values[(x * sy + y) * channels + c] = 1 }
            }
            mass = MLX.stacked(seeds.map { _ in MLXArray(values).reshaped([sx, sy, channels]) })
        case "patch":
            let builder = SearchInitializationBuilder(runtimeConfig: runtime, useParamEmbedding: false, constantPerPatchParameters: false)
            mass = MLX.stacked(seeds.map { builder.buildInitialState(seed: $0 + 100) })
        default:
            preconditionFailure("unknown input \(input)")
        }
        let params = MLX.broadcast(kernels.h.reshaped([seeds.count, 1, 1, runtime.nbK]), to: [seeds.count, sx, sy, runtime.nbK])
        return SmallFixture(config: config, kernels: kernels, batchCount: seeds.count, mass: mass, params: params)
    }

    private func littleEndianFloats(base64: String) throws -> [Float] {
        let data = try XCTUnwrap(Data(base64Encoded: base64))
        return data.withUnsafeBytes { bytes in
            stride(from: 0, to: bytes.count, by: 4).map {
                Float(bitPattern: UInt32(littleEndian: bytes.loadUnaligned(fromByteOffset: $0, as: UInt32.self)))
            }
        }
    }

    private func loadPackageConfig(_ name: String, overrides: [String: Any]) throws -> LeniaRuntimeConfig {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        return try loadRuntimeConfig(
            from: Data(contentsOf: packageRoot.appendingPathComponent("configs/base/\(name)")), overrides: overrides)
    }

    func testTenKernelTorusTracksMetal() throws {
        try assertTracksMetal(configName: "paper_random_2c_10k_128.json", overrides: ["params.ranges.R": [17.0, 20.5]])
    }

    func testTwentyKernelTorusTracksMetal() throws {
        try assertTracksMetal(configName: "paper_random_2c_20k_128.json", overrides: [:])
    }

    /// Bodies start against all four walls of a non-square grid, so the wall clamp, the zero-padded
    /// stencils and the skipped wrapped sources all carry mass from the first step.
    func testTenKernelNonSquareWallTracksMetal() throws {
        try assertTracksMetal(configName: "paper_random_2c_10k_128.json", overrides: [
            "profile": "experimental",
            "grid": ["sx": 128, "sy": 64],
            "reintegration": ["dd": 5, "sigma": 0.65, "border": "wall"],
            "init": [
                "seed": 0,
                "patches": [
                    ["center": [12, 12], "size": 24],
                    ["center": [64, 52], "size": 24],
                    ["center": [116, 30], "size": 24],
                ],
                "a_uniform": ["low": 0, "high": 1],
                "p_uniform": NSNull(),
            ],
            "params.ranges.R": [17.0, 20.5],
        ])
    }

    /// Random initial states are chaotic from the first step, so the cpu error is judged against
    /// how far a one-ulp perturbation moves Metal itself, until that yardstick saturates.
    private func assertTracksMetal(configName: String, overrides: [String: Any]) throws {
        let steps = 300
        let trace = try agreementTrace(configName: configName, overrides: overrides, steps: steps)
        for step in [1, 10, 50, 100, 200, 300] {
            let sample = trace[step - 1]
            print(
                "CONFORMANCE config=\(configName) step=\(step)"
                    + " mass_rel_rms=\(sample.mass.relativeRMS) mass_max_abs=\(sample.mass.maxAbs)"
                    + " potential_rel_rms=\(sample.potential.relativeRMS) potential_max_abs=\(sample.potential.maxAbs)"
                    + " flow_rel_rms=\(sample.flow.relativeRMS) flow_max_abs=\(sample.flow.maxAbs)"
                    + " metal_ulp_mass_rel_rms=\(sample.metalULP.relativeRMS)"
            )
        }
        XCTAssertLessThan(trace[0].mass.relativeRMS, 1e-6)
        XCTAssertLessThan(trace[0].potential.relativeRMS, 1e-6)
        // The flow differences gradients of U and mass, so it amplifies the potential's float32 error.
        XCTAssertLessThan(trace[0].flow.relativeRMS, 1e-5)
        let unsaturated = trace.filter { $0.metalULP.relativeRMS < 1e-2 }
        XCTAssertGreaterThan(unsaturated.count, 10)
        let worstRatio = unsaturated.map { $0.mass.relativeRMS / $0.metalULP.relativeRMS }.max()!
        print("CONFORMANCE config=\(configName) unsaturated_steps=\(unsaturated.count) worst_cpu_to_ulp_ratio=\(worstRatio)")
        XCTAssertLessThan(worstRatio, 4, "cpu drifts from Metal faster than a one-ulp perturbation of Metal")
    }

    private struct FieldError {
        let relativeRMS: Double
        let maxAbs: Double

        init(_ actual: [Float], _ expected: [Float]) {
            var squaredError = 0.0
            var squaredNorm = 0.0
            var maxAbs = 0.0
            for (a, e) in zip(actual, expected) {
                let difference = Double(a) - Double(e)
                squaredError += difference * difference
                squaredNorm += Double(e) * Double(e)
                maxAbs = max(maxAbs, abs(difference))
            }
            self.relativeRMS = (squaredError / squaredNorm).squareRoot()
            self.maxAbs = maxAbs
        }
    }

    private struct StepAgreement {
        let step: Int
        let mass: FieldError
        let potential: FieldError
        let flow: FieldError
        let metalULP: FieldError
    }

    private func agreementTrace(configName: String, overrides: [String: Any], steps: Int) throws -> [StepAgreement] {
        let runtime = try loadPackageConfig(configName, overrides: overrides)
        let config = batchedConfigFromRuntime(runtime)
        let ranges = try XCTUnwrap(runtime.randomParamRanges)
        let seeds = [11, 12, 13, 14]
        let params = seeds.map { generateRandomParams(seed: $0, nbK: runtime.nbK, ranges: ranges) }
        let kernels = compilePopulationKernels(paramsBatch: params, config: config, c0: runtime.c0, c1: runtime.c1)
        let builder = SearchInitializationBuilder(
            runtimeConfig: runtime,
            useParamEmbedding: false,
            constantPerPatchParameters: false
        )
        let mass = MLX.stacked(seeds.map { builder.buildInitialState(seed: $0 + 100) })
        let perturbedMass = MLXArray(mass.asArray(Float.self).map { $0 > 0 ? $0.nextUp : $0 }).reshaped(mass.shape)
        let fieldParams = MLX.broadcast(
            kernels.h.reshaped([seeds.count, 1, 1, runtime.nbK]),
            to: [seeds.count, runtime.sx, runtime.sy, runtime.nbK]
        )

        func metalRunner(_ initial: MLXArray) -> FlowLeniaMetalFullStateRunner {
            let runner = FlowLeniaMetalFullStateRunner(
                config: config,
                kernels: kernels,
                batchCount: seeds.count,
                reintegrateParams: false
            )
            runner.reset(mass: initial, params: fieldParams, wallMask: nil, staticChannelFields: [], food: nil, mixStep: 0)
            return runner
        }
        let metal = metalRunner(mass)
        let metalPerturbed = metalRunner(perturbedMass)
        let cpu = FlowLeniaCPUStateRunner(
            config: config,
            kernels: kernels,
            batchCount: seeds.count,
            wallPotential: nil,
            matterWeights: nil
        )
        cpu.reset(mass: mass, params: fieldParams, wallMask: nil, staticChannelFields: [], food: nil, mixStep: 0)

        var trace: [StepAgreement] = []
        for step in 1...steps {
            metal.step(count: 1)
            metalPerturbed.step(count: 1)
            cpu.step(count: 1)
            let metalMass = metal.materializeMass().asArray(Float.self)
            trace.append(StepAgreement(
                step: step,
                mass: FieldError(cpu.materializeMass().asArray(Float.self), metalMass),
                potential: FieldError(cpu.materializeLastPotential(), metal.materializeLastPotential()),
                flow: FieldError(cpu.materializeLastFlow(), metal.materializeLastFlow()),
                metalULP: FieldError(metalPerturbed.materializeMass().asArray(Float.self), metalMass)
            ))
        }
        return trace
    }
}
#endif
