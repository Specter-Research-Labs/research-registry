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

private func maxAbsDifference(_ lhs: MLXArray, _ rhs: MLXArray) -> Float {
    let left = lhs.asArray(Float.self)
    let right = rhs.asArray(Float.self)
    precondition(left.count == right.count)
    return zip(left, right).reduce(0) { difference, pair in
        max(difference, abs(pair.0 - pair.1))
    }
}
