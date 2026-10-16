import MLX
import XCTest
@testable import LeniaCore

final class PhantomFieldTests: XCTestCase {
    override func setUpWithError() throws {
        try LeniaMetalLibrarySupport.ensureAvailable()
    }

    func testZeroPhantomLeavesTrajectoryBitIdentical() {
        let mass = phantomBlob(centerX: 20, centerY: 30)
        let reference = phantomRun(mass, phantom: nil, steps: 16)
        let zero = [Float](repeating: 0, count: mass.count)
        for source in [FlowLeniaPhantomSpec.Source.fixed, .replay] {
            for pressure in [false, true] {
                let run = phantomRun(mass, phantom: FlowLeniaPhantomSpec(source: source, pressure: pressure, field: zero), steps: 16)
                XCTAssertEqual(phantomBits(run.mass), phantomBits(reference.mass), "source=\(source), pressure=\(pressure)")
            }
        }
    }

    func testReplayedPhantomIsSensedLikeRealMatterAtStepZero() {
        let a = phantomBlob(centerX: 20, centerY: 30)
        let b = phantomBlob(centerX: 34, centerY: 34)
        let pair = phantomRun(zip(a, b).map { $0 + $1 }, phantom: nil, steps: 1)
        for pressure in [false, true] {
            let run = phantomRun(a, phantom: FlowLeniaPhantomSpec(source: .replay, pressure: pressure, field: b), steps: 1)
            XCTAssertEqual(phantomBits(run.potential), phantomBits(pair.potential), "pressure=\(pressure)")
            if pressure {
                XCTAssertEqual(phantomBits(run.flow), phantomBits(pair.flow))
            } else {
                XCTAssertNotEqual(phantomBits(run.flow), phantomBits(pair.flow))
            }
        }
    }

    func testReplayedPhantomFollowsItsSoloTrajectory() {
        let a = phantomBlob(centerX: 20, centerY: 30)
        let b = phantomBlob(centerX: 34, centerY: 34)
        let solo = phantomRun(b, phantom: nil, steps: 12)
        let run = phantomRun(a, phantom: FlowLeniaPhantomSpec(source: .replay, pressure: true, field: b), steps: 12)
        XCTAssertEqual(phantomBits(run.phantom), phantomBits(solo.mass))
    }

    func testPhantomConservesRealMassAndCarriesNone() {
        let a = phantomBlob(centerX: 20, centerY: 30)
        let b = phantomBlob(centerX: 30, centerY: 32)
        let initial = a.reduce(0.0) { $0 + Double($1) }
        let alone = phantomBits(phantomRun(a, phantom: nil, steps: 24).mass)
        for source in [FlowLeniaPhantomSpec.Source.fixed, .replay] {
            for pressure in [false, true] {
                let run = phantomRun(a, phantom: FlowLeniaPhantomSpec(source: source, pressure: pressure, field: b), steps: 24)
                let final = run.mass.reduce(0.0) { $0 + Double($1) }
                XCTAssertEqual(final / initial, 1, accuracy: 1e-5, "source=\(source), pressure=\(pressure)")
                XCTAssertNotEqual(phantomBits(run.mass), alone)
                if source == .fixed {
                    XCTAssertEqual(phantomBits(run.phantom), phantomBits(b))
                }
            }
        }
    }
}

private let phantomSide = 48
private let phantomChannels = 2

private struct PhantomRun {
    let mass: [Float]
    let potential: [Float]
    let flow: [Float]
    let phantom: [Float]
}

private func phantomRun(_ mass: [Float], phantom: FlowLeniaPhantomSpec?, steps: Int) -> PhantomRun {
    let simulator = FlowLeniaInteractiveSimulator(runtimeConfig: phantomRuntimeConfig(), phantom: phantom)
    let initial = FlowLeniaInteractiveState(
        step: 0,
        mass: MLXArray(mass).reshaped([phantomSide, phantomSide, phantomChannels]),
        params: nil,
        food: nil
    )
    let final = simulator.step(initial, count: steps)
    return PhantomRun(
        mass: final.mass.asArray(Float.self),
        potential: simulator.capacityPilotLastPotential(),
        flow: simulator.capacityPilotLastFlow(),
        phantom: phantom == nil ? [] : simulator.phantomField()
    )
}

private func phantomBlob(centerX: Int, centerY: Int) -> [Float] {
    var values = [Float](repeating: 0, count: phantomSide * phantomSide * phantomChannels)
    for x in 0..<phantomSide {
        for y in 0..<phantomSide {
            let d2 = Float((x - centerX) * (x - centerX) + (y - centerY) * (y - centerY))
            guard d2 < 36 else { continue }
            for c in 0..<phantomChannels {
                values[(x * phantomSide + y) * phantomChannels + c] = (1 - d2 / 36) * Float(c + 1) / 2
            }
        }
    }
    return values
}

private func phantomBits(_ values: [Float]) -> [UInt32] {
    values.map(\.bitPattern)
}

private func phantomRuntimeConfig() -> LeniaRuntimeConfig {
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
        backend: .metalFull,
        sx: phantomSide,
        sy: phantomSide,
        channels: phantomChannels,
        nbK: 4,
        profile: .paper,
        c0: connectivity.c0,
        c1: connectivity.c1,
        dt: 0.2,
        dd: 5,
        sigma: 0.65,
        n: 2,
        thetaA: 2,
        border: "wall",
        implementation: ImplementationSettings(
            mode: "flowlenia_2022_paper_equations",
            border: "wall",
            gradientBoundary: "zero_pad",
            alphaMode: "mass",
            kernelProfile: "flowlenia_2022_paper_equations",
            flowClip: "none"
        ),
        params: params,
        initSeed: 19,
        patches: [],
        aUniform: UniformRange(low: 0, high: 0),
        pUniform: nil,
        steps: 20,
        parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
        chemotaxis: nil,
        food: nil,
        walls: nil,
        environment: nil,
        interventions: []
    )
}
