#if canImport(Metal)
import MLX
import XCTest
@testable import LeniaCore

/// The cpu backend mirrors the metal-full equations in fp32, so it should agree with Metal at
/// the level of Metal's own sensitivity to a one-ulp change of the initial mass.
final class FlowLeniaCPUAgreementTests: XCTestCase {
    override func setUpWithError() throws {
        try LeniaMetalLibrarySupport.ensureAvailable()
    }

    func testTenKernelTorusTracksMetal() throws {
        try assertTracksMetal(configName: "paper_random_2c_10k_128.json", overrides: ["params.ranges.R": [17.0, 20.5]])
    }

    func testTwentyKernelTorusTracksMetal() throws {
        try assertTracksMetal(configName: "paper_random_2c_20k_128.json", overrides: [:])
    }

    /// Random initial states are chaotic from the first step, so the cpu error is judged against
    /// how far a one-ulp perturbation moves Metal itself, until that yardstick saturates.
    private func assertTracksMetal(configName: String, overrides: [String: Any]) throws {
        let steps = 300
        let trace = try agreementTrace(configName: configName, overrides: overrides, steps: steps)
        for step in [1, 10, 50, 100, 200, 300] {
            let sample = trace[step - 1]
            print(
                "CPU_AGREEMENT config=\(configName) step=\(step)"
                    + " mass_rel_rms=\(sample.mass.relativeRMS) mass_max_abs=\(sample.mass.maxAbs)"
                    + " potential_rel_rms=\(sample.potential.relativeRMS) potential_max_abs=\(sample.potential.maxAbs)"
                    + " metal_ulp_mass_rel_rms=\(sample.metalULP.relativeRMS)"
            )
        }
        XCTAssertLessThan(trace[0].mass.relativeRMS, 1e-6)
        XCTAssertLessThan(trace[0].potential.relativeRMS, 1e-6)
        let unsaturated = trace.filter { $0.metalULP.relativeRMS < 1e-2 }
        XCTAssertGreaterThan(unsaturated.count, 10)
        let worstRatio = unsaturated.map { $0.mass.relativeRMS / $0.metalULP.relativeRMS }.max()!
        print("CPU_AGREEMENT config=\(configName) unsaturated_steps=\(unsaturated.count) worst_cpu_to_ulp_ratio=\(worstRatio)")
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
        let metalULP: FieldError
    }

    private func agreementTrace(configName: String, overrides: [String: Any], steps: Int) throws -> [StepAgreement] {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let configURL = packageRoot.appendingPathComponent("configs/base/\(configName)")
        let runtime = try loadRuntimeConfig(from: Data(contentsOf: configURL), overrides: overrides)
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
                metalULP: FieldError(metalPerturbed.materializeMass().asArray(Float.self), metalMass)
            ))
        }
        return trace
    }
}
#endif
