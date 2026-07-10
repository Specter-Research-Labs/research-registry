import MLX
import XCTest
@testable import LeniaCore

final class FlowLeniaInteractiveMetalTests: XCTestCase {
    override func setUpWithError() throws {
        try LeniaMetalLibrarySupport.ensureAvailable()
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

    func testUnsupportedMetalContractFallsBackToMLXWithoutCrashing() {
        let config = interactiveRuntimeConfig(
            backend: .metalFull,
            embedded: true,
            mix: "softmax"
        )

        XCTAssertFalse(FlowLeniaInteractiveSimulator.supportsResidentMetal(config))
        let simulator = FlowLeniaInteractiveSimulator(runtimeConfig: config)
        let stepped = simulator.step(simulator.makeInitialState(), count: 2)

        XCTAssertEqual(simulator.effectiveBackend, .mlx)
        XCTAssertEqual(stepped.step, 2)
        XCTAssertTrue(stepped.mass.asArray(Float.self).allSatisfy(\.isFinite))
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
}

private func interactiveRuntimeConfig(
    backend: FlowLeniaComputeBackend,
    embedded: Bool = false,
    mix: String = "avg",
    includeFoodAndWalls: Bool = false,
    environment: EnvironmentConfig? = nil
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
        profile: includeFoodAndWalls ? .experimental : .paper,
        c0: connectivity.c0,
        c1: connectivity.c1,
        dt: 0.2,
        dd: 5,
        sigma: 0.65,
        n: 2,
        thetaA: 2,
        border: "torus",
        implementation: ImplementationSettings(
            mode: "flowlenia_2022_paper_equations",
            border: "torus",
            gradientBoundary: "periodic",
            alphaMode: "mass",
            kernelProfile: "flowlenia_2022_paper_equations",
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
