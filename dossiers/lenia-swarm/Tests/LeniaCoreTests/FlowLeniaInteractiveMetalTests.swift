import MLX
import XCTest
@testable import LeniaCore

final class FlowLeniaInteractiveMetalTests: XCTestCase {
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
            let data = try XCTUnwrap(Data(base64Encoded: encoded))
            let values = data.withUnsafeBytes { bytes in
                stride(from: 0, to: bytes.count, by: 4).map {
                    Float(bitPattern: UInt32(littleEndian: bytes.loadUnaligned(fromByteOffset: $0, as: UInt32.self)))
                }
            }
            return MLXArray(values).reshaped([32, 32, 2])
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
        for backend in [FlowLeniaComputeBackend.mlx, .metalFull] {
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

    func testQuarterTurnAndReflectionCommuteWithOneStep() {
        let n = 32, channels = 2
        func transform(_ a: MLXArray, reflect: Bool) -> MLXArray {
            let input = a.asArray(Float.self)
            var output = input
            for x in 0..<n { for y in 0..<n { for c in 0..<channels {
                let tx = reflect ? n - 1 - x : n - 1 - y
                let ty = reflect ? y : x
                output[(tx * n + ty) * channels + c] = input[(x * n + y) * channels + c]
            } } }
            return MLXArray(output).reshaped([n, n, channels])
        }
        for backend in [FlowLeniaComputeBackend.mlx, .metalFull] {
            for embedded in [false, true] {
                let simulator = FlowLeniaInteractiveSimulator(
                    runtimeConfig: interactiveRuntimeConfig(backend: backend, embedded: embedded))
                let initial = simulator.makeInitialState()
                // Uniform embedded weights keep the rule identical under spatial transforms.
                let params = initial.params.map { MLX.ones(like: $0) * Float(0.4) }
                let base = FlowLeniaInteractiveState(step: 0, mass: initial.mass, params: params, food: nil)
                let advanced = simulator.step(base)
                for reflect in [false, true] {
                    let turned = FlowLeniaInteractiveState(step: 0,
                        mass: transform(base.mass, reflect: reflect), params: params, food: nil)
                    let actual = simulator.step(turned)
                    XCTAssertLessThan(maxAbsDifference(actual.mass, transform(advanced.mass, reflect: reflect)),
                                      1e-4, "backend=\(backend), embedded=\(embedded), reflect=\(reflect)")
                }
            }
        }
    }

    func testResidentMetalCountMatchesSequentialAndResynchronizesBranches() {
        let metalConfig = interactiveRuntimeConfig(backend: .metalFull)
        let batchedSimulator = FlowLeniaInteractiveSimulator(runtimeConfig: metalConfig)
        let sequentialSimulator = FlowLeniaInteractiveSimulator(runtimeConfig: metalConfig)
        let batchedInitial = batchedSimulator.makeInitialState()
        var sequential = sequentialSimulator.makeInitialState()

        let batched = batchedSimulator.step(batchedInitial, count: 8)
        for _ in 0..<8 {
            sequential = sequentialSimulator.step(sequential)
        }

        XCTAssertEqual(batchedSimulator.effectiveBackend, .metalFull)
        XCTAssertEqual(batched.step, 8)
        XCTAssertEqual(sequential.step, 8)
        XCTAssertNil(batched.params)
        XCTAssertLessThan(maxAbsDifference(batched.mass, sequential.mass), 1e-5)
        XCTAssertTrue(batched.mass.asArray(Float.self).allSatisfy(\.isFinite))

        let mlxSimulator = FlowLeniaInteractiveSimulator(
            runtimeConfig: interactiveRuntimeConfig(backend: .mlx)
        )
        let expected = mlxSimulator.step(mlxSimulator.makeInitialState())
        let resynchronized = batchedSimulator.step(batchedInitial)

        XCTAssertEqual(resynchronized.step, 1)
        XCTAssertLessThan(maxAbsDifference(resynchronized.mass, expected.mass), 1e-3)
    }

    func testResidentMetalBatchesEmbeddedParamsFoodAndWalls() {
        let config = interactiveRuntimeConfig(
            backend: .metalFull,
            embedded: true,
            includeFoodAndWalls: true
        )
        let simulator = FlowLeniaInteractiveSimulator(runtimeConfig: config)
        let initial = simulator.makeInitialState()
        let stepped = simulator.step(initial, count: 4)

        XCTAssertEqual(simulator.effectiveBackend, .metalFull)
        XCTAssertEqual(stepped.step, 4)
        XCTAssertNotNil(stepped.params)
        XCTAssertNotNil(stepped.food)
        XCTAssertTrue(stepped.mass.asArray(Float.self).allSatisfy(\.isFinite))
        XCTAssertTrue(stepped.params?.asArray(Float.self).allSatisfy(\.isFinite) == true)
        XCTAssertTrue(stepped.food?.asArray(Float.self).allSatisfy(\.isFinite) == true)

        let mass = stepped.mass.asArray(Float.self)
        let food = stepped.food?.asArray(Float.self) ?? []
        for x in 6..<10 {
            for y in 6..<10 {
                let cell = x * config.sy + y
                XCTAssertEqual(mass[cell * config.channels], 0, accuracy: 1e-6)
                XCTAssertEqual(mass[cell * config.channels + 1], 0, accuracy: 1e-6)
                XCTAssertEqual(food[cell], 0, accuracy: 1e-6)
            }
        }
    }

    func testUnsupportedMetalContractIsRejectedByCapabilityCheck() {
        let config = interactiveRuntimeConfig(
            backend: .metalFull,
            embedded: true,
            mix: "softmax"
        )

        XCTAssertFalse(FlowLeniaInteractiveSimulator.supportsResidentMetal(config))
    }

    func testStochasticMixRestoreContinuesAtAbsoluteStep() throws {
        let config = interactiveRuntimeConfig(
            backend: .metalFull,
            embedded: true,
            mix: "stoch"
        )
        let referenceSimulator = FlowLeniaInteractiveSimulator(runtimeConfig: config)
        let restoredSimulator = FlowLeniaInteractiveSimulator(runtimeConfig: config)
        let reference = referenceSimulator.step(referenceSimulator.makeInitialState(), count: 6)
        let checkpoint = restoredSimulator.step(restoredSimulator.makeInitialState(), count: 5)
        let restored = FlowLeniaInteractiveState(
            step: checkpoint.step,
            mass: checkpoint.mass,
            params: checkpoint.params,
            food: checkpoint.food
        )

        let resumed = restoredSimulator.step(restored)

        XCTAssertEqual(resumed.step, reference.step)
        XCTAssertLessThan(maxAbsDifference(resumed.mass, reference.mass), 1e-5)
        XCTAssertLessThan(
            maxAbsDifference(try XCTUnwrap(resumed.params), try XCTUnwrap(reference.params)),
            1e-5
        )
    }

    func testEnvironmentPotentialIsNotAppliedAsBinaryWallMask() {
        let environment = EnvironmentConfig(
            type: "cross_map",
            depth: 1,
            wallThickness: 2,
            wallValue: -1,
            passageWidth: 4
        )
        let metalSimulator = FlowLeniaInteractiveSimulator(
            runtimeConfig: interactiveRuntimeConfig(
                backend: .metalFull,
                embedded: true,
                environment: environment
            )
        )
        let mlxSimulator = FlowLeniaInteractiveSimulator(
            runtimeConfig: interactiveRuntimeConfig(
                backend: .mlx,
                embedded: true,
                environment: environment
            )
        )

        let metal = metalSimulator.step(metalSimulator.makeInitialState())
        let mlx = mlxSimulator.step(mlxSimulator.makeInitialState())

        XCTAssertNil(metalSimulator.wallMaskMap())
        XCTAssertGreaterThan(metal.mass.asArray(Float.self).reduce(0, +), 0)
        XCTAssertLessThan(maxAbsDifference(metal.mass, mlx.mass), 1e-3)
    }

    func testDynamicHardCircularObstacleMasksBothBackendsAndCanBeCleared() throws {
        for backend in [FlowLeniaComputeBackend.mlx, .metalFull] {
            let simulator = FlowLeniaInteractiveSimulator(
                runtimeConfig: interactiveRuntimeConfig(backend: backend)
            )
            simulator.setHardCircularObstacle(centerX: 8, centerY: 8, radius: 3)

            let mask = try XCTUnwrap(simulator.wallMaskMap()).asArray(Float.self)
            XCTAssertEqual(mask[8 * 32 + 8], 0, accuracy: 1e-6)
            XCTAssertEqual(mask[0], 1, accuracy: 1e-6)

            let initial = simulator.makeInitialState()
            let stepped = simulator.step(initial)
            let mass = stepped.mass.asArray(Float.self)
            for x in 6...10 {
                for y in 6...10 where hypot(Float(x - 8), Float(y - 8)) <= 3 {
                    let cell = x * 32 + y
                    XCTAssertEqual(mass[cell * 2], 0, accuracy: 1e-6)
                    XCTAssertEqual(mass[cell * 2 + 1], 0, accuracy: 1e-6)
                }
            }

            simulator.clearHardObstacle()
            XCTAssertNil(simulator.wallMaskMap())
        }
    }

    func testDynamicHardObstacleDoesNotContaminateShamContinuation() {
        let config = interactiveRuntimeConfig(backend: .metalFull)
        let simulator = FlowLeniaInteractiveSimulator(runtimeConfig: config)
        let checkpoint = simulator.step(simulator.makeInitialState(), count: 3)

        simulator.clearHardObstacle()
        let firstSham = simulator.step(checkpoint, count: 2)
        simulator.setHardCircularObstacle(centerX: 8, centerY: 8, radius: 3)
        _ = simulator.step(checkpoint, count: 2)
        simulator.clearHardObstacle()
        let secondSham = simulator.step(checkpoint, count: 2)

        XCTAssertLessThan(maxAbsDifference(firstSham.mass, secondSham.mass), 1e-6)
    }

    func testDynamicCircularWallPotentialPreservesBranchStateAndClearsAcrossBackends() throws {
        for backend in [FlowLeniaComputeBackend.mlx, .metalFull] {
            let simulator = FlowLeniaInteractiveSimulator(
                runtimeConfig: interactiveRuntimeConfig(backend: backend, embedded: true)
            )
            let checkpoint = simulator.step(simulator.makeInitialState(), count: 3)
            let checkpointMass = checkpoint.mass.asArray(Float.self).reduce(0, +)
            let checkpointParams = try XCTUnwrap(checkpoint.params)

            simulator.setCircularWallPotential(centerX: 16, centerY: 16, radius: 3, height: 30)
            XCTAssertEqual(checkpoint.mass.asArray(Float.self).reduce(0, +), checkpointMass, accuracy: 1e-6)
            XCTAssertLessThan(maxAbsDifference(try XCTUnwrap(checkpoint.params), checkpointParams), 1e-6)
            let potentialStep = simulator.step(checkpoint)

            simulator.clearCircularWallPotential()
            let shamStep = simulator.step(checkpoint)
            XCTAssertGreaterThan(maxAbsDifference(potentialStep.mass, shamStep.mass), 1e-6)
            let potentialMass = potentialStep.mass.asArray(Float.self).reduce(0, +)
            XCTAssertEqual(potentialMass, checkpointMass, accuracy: checkpointMass * 0.01)

            let firstSham = simulator.step(checkpoint, count: 2)
            simulator.setCircularWallPotential(centerX: 16, centerY: 16, radius: 3, height: 30)
            _ = simulator.step(checkpoint, count: 2)
            simulator.clearCircularWallPotential()
            let secondSham = simulator.step(checkpoint, count: 2)

            XCTAssertLessThan(maxAbsDifference(firstSham.mass, secondSham.mass), 1e-6)
            XCTAssertLessThan(
                maxAbsDifference(try XCTUnwrap(firstSham.params), try XCTUnwrap(secondSham.params)),
                1e-6
            )
        }
    }

    func testAncestryTracerIsPassiveAndConservesFounderMass() throws {
        for authorReference in [false, true] {
            let runtime = interactiveRuntimeConfig(backend: .metalFull, authorReference: authorReference)
            let plain = FlowLeniaInteractiveSimulator(runtimeConfig: runtime)
            let expected = plain.step(plain.makeInitialState(), count: 64).mass.asArray(Float.self)

            let traced = FlowLeniaInteractiveSimulator(runtimeConfig: runtime)
            var state = traced.makeInitialState()
            let mass = state.mass.asArray(Float.self)
            let labels = (0..<(runtime.sx * runtime.sy)).map { Int32($0 / runtime.sy < runtime.sx / 2 ? 0 : 1) }
            let founders = try capacityPilotFounderMass(mass, labels: labels, channels: runtime.channels, founderCount: 2)
            traced.setAncestry(founders, founderCount: 2, for: state)
            for count in [1, 31, 32] {
                state = traced.step(state, count: count)
            }
            let actual = state.mass.asArray(Float.self)
            XCTAssertEqual(actual, expected, "authorReference=\(authorReference)")

            let initialTotals = founderTotals(founders, channels: runtime.channels, founderCount: 2)
            let finalFounders = traced.ancestryFounderMass(for: state)
            let finalTotals = founderTotals(finalFounders, channels: runtime.channels, founderCount: 2)
            for (initial, final) in zip(initialTotals, finalTotals) {
                XCTAssertGreaterThan(initial, 0)
                XCTAssertEqual(final, initial, accuracy: initial * 1e-5, "authorReference=\(authorReference)")
            }
            for cell in actual.indices {
                XCTAssertEqual(finalFounders[cell * 2] + finalFounders[cell * 2 + 1], actual[cell],
                               accuracy: 1e-6 + actual[cell] * 1e-5)
            }
            XCTAssertGreaterThan(zip(stride(from: 0, to: finalFounders.count, by: 2), actual).filter {
                finalFounders[$0.0] > 0.05 * $0.1 && finalFounders[$0.0 + 1] > 0.05 * $0.1
            }.count, 0, "founders should mix somewhere for the test to exercise mixing")
        }
    }

    func testSingleFounderAncestryEqualsMass() {
        for authorReference in [false, true] {
            let runtime = interactiveRuntimeConfig(backend: .metalFull, authorReference: authorReference)
            let simulator = FlowLeniaInteractiveSimulator(runtimeConfig: runtime)
            var state = simulator.makeInitialState()
            simulator.setAncestry(state.mass.asArray(Float.self), founderCount: 1, for: state)
            state = simulator.step(state, count: 48)
            XCTAssertEqual(simulator.ancestryFounderMass(for: state), state.mass.asArray(Float.self),
                           "authorReference=\(authorReference)")
        }
    }

    func testTwoFounderSplitMatchesFloat64Reintegration() {
        let runtime = interactiveRuntimeConfig(backend: .metalFull)
        let (sx, sy, channels, dd) = (runtime.sx, runtime.sy, runtime.channels, runtime.dd)
        let simulator = FlowLeniaInteractiveSimulator(runtimeConfig: runtime)
        var state = simulator.step(simulator.makeInitialState(), count: 8)
        let mass = state.mass.asArray(Float.self)
        var founders = [Float](repeating: 0, count: mass.count * 2)
        for i in mass.indices {
            let x = i / channels / sy
            let share = Float(x) / Float(sx - 1)
            founders[i * 2] = mass[i] * share
            founders[i * 2 + 1] = mass[i] - founders[i * 2]
        }
        simulator.setAncestry(founders, founderCount: 2, for: state)
        state = simulator.step(state, count: 1)
        let flow = simulator.capacityPilotLastFlow()
        let actual = simulator.ancestryFounderMass(for: state)

        let sigma = Double(runtime.sigma)
        let maxAdvection = Double(dd) - sigma
        let clipMax = min(1, 2 * sigma)
        var expected = [Double](repeating: 0, count: founders.count)
        for x in 0..<sx { for y in 0..<sy { for dx in -dd...dd { for dy in -dd...dd {
            let source = ((x - dx + sx) % sx) * sy + (y - dy + sy) % sy
            for c in 0..<channels where mass[source * channels + c] > 0 {
                let f = (source * channels + c) * 2
                let clippedX = min(max(Double(flow[f]) * Double(runtime.dt), -maxAdvection), maxAdvection)
                let clippedY = min(max(Double(flow[f + 1]) * Double(runtime.dt), -maxAdvection), maxAdvection)
                let szX = min(max(0.5 - abs(Double(dx) - clippedX) + sigma, 0), clipMax)
                let szY = min(max(0.5 - abs(Double(dy) - clippedY) + sigma, 0), clipMax)
                for j in 0..<2 {
                    expected[((x * sy + y) * channels + c) * 2 + j] +=
                        Double(founders[(source * channels + c) * 2 + j]) * szX * szY / (4 * sigma * sigma)
                }
            }
        } } } }
        let scale = expected.max()!
        XCTAssertGreaterThan(scale, 0)
        XCTAssertLessThan(zip(actual, expected).map { abs(Double($0) - $1) }.max()!, scale * 1e-5)
    }

    func testDynamicCircularWallPotentialAffectsNonEmbeddedMLXPath() {
        let simulator = FlowLeniaInteractiveSimulator(
            runtimeConfig: interactiveRuntimeConfig(backend: .mlx)
        )
        let checkpoint = simulator.step(simulator.makeInitialState(), count: 3)
        simulator.setCircularWallPotential(centerX: 16, centerY: 16, radius: 3, height: 30)
        let potential = simulator.step(checkpoint)
        simulator.clearCircularWallPotential()
        let sham = simulator.step(checkpoint)

        XCTAssertGreaterThan(maxAbsDifference(potential.mass, sham.mass), 1e-6)
    }
}

private func interactiveRuntimeConfig(
    backend: FlowLeniaComputeBackend,
    embedded: Bool = false,
    mix: String = "avg",
    includeFoodAndWalls: Bool = false,
    environment: EnvironmentConfig? = nil,
    authorReference: Bool = false
) -> LeniaRuntimeConfig {
    let params = ResolvedParams(
        r: [0.42, 0.55, 0.68, 0.81],
        b: Array(repeating: [1.0, 0.0, 0.0], count: 4),
        w: Array(repeating: [0.16, 0.2, 0.16], count: 4),
        a: [
            [0.25, 0.25, 0.25],
            [0.35, 0.35, 0.35],
            [0.45, 0.45, 0.45],
            [0.55, 0.55, 0.55],
        ],
        m: [0.12, 0.16, 0.2, 0.24],
        s: [0.035, 0.04, 0.045, 0.05],
        h: [0.3, 0.4, 0.5, 0.6],
        R: 6,
        seed: 11
    )
    let connectivity = connFromMatrix([[1, 1], [1, 1]])
    return LeniaRuntimeConfig(
        backend: backend,
        sx: 32,
        sy: 32,
        channels: 2,
        nbK: 4,
        profile: includeFoodAndWalls || authorReference ? .experimental : .paper,
        c0: connectivity.c0,
        c1: connectivity.c1,
        dt: 0.2,
        dd: 5,
        sigma: 0.65,
        n: 2,
        thetaA: 2,
        border: authorReference ? "wall" : "torus",
        implementation: ImplementationSettings(
            mode: authorReference ? "custom" : "flowlenia_2022_paper_equations",
            border: authorReference ? "wall" : "torus",
            gradientBoundary: authorReference ? "zero_pad" : "periodic",
            alphaMode: authorReference ? "per_channel" : "mass",
            kernelProfile: authorReference ? "flowlenia_2022_colab" : "flowlenia_2022_paper_equations",
            flowClip: "none"
        ),
        params: params,
        initSeed: 19,
        patches: [PatchConfig(center: [16, 16], size: 8)],
        aUniform: UniformRange(low: 0.1, high: 0.9),
        pUniform: embedded ? UniformRange(low: 0.2, high: 0.8) : nil,
        steps: 20,
        parameterEmbedding: ParameterEmbeddingConfig(
            enabled: embedded,
            mix: mix,
            mix_seed: mix == "avg" ? nil : 7
        ),
        chemotaxis: nil,
        food: includeFoodAndWalls
            ? FoodConfig(
                enabled: true,
                channel_index: 1,
                mode: "full",
                uniform: UniformRange(low: 0.4, high: 0.4),
                decay_rate: 0.002,
                digest_rate: 0.01,
                include_in_mass: false
            )
            : nil,
        walls: includeFoodAndWalls
            ? WallsConfig(enabled: true, patches: [PatchConfig(center: [8, 8], size: 4)])
            : nil,
        environment: environment,
        interventions: []
    )
}

private func founderTotals(_ founders: [Float], channels: Int, founderCount: Int) -> [Double] {
    var totals = [Double](repeating: 0, count: channels * founderCount)
    for (i, value) in founders.enumerated() {
        totals[i % (channels * founderCount)] += Double(value)
    }
    return totals
}

private func maxAbsDifference(_ lhs: MLXArray, _ rhs: MLXArray) -> Float {
    let left = lhs.asArray(Float.self)
    let right = rhs.asArray(Float.self)
    precondition(left.count == right.count)
    return zip(left, right).reduce(0) { difference, pair in
        max(difference, abs(pair.0 - pair.1))
    }
}
