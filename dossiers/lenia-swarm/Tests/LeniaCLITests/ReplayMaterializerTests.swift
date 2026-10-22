import Foundation
import XCTest
import LeniaCore
@testable import LeniaCLIKit

final class ReplayMaterializerTests: XCTestCase {
    func testDevelopmentTraceStrideClampsToReplayLength() {
        XCTAssertEqual(developmentTraceStride(interval: 25, steps: 3), 3)
        XCTAssertEqual(developmentTraceStride(interval: 2, steps: 5), 2)
        XCTAssertEqual(developmentTraceStride(interval: 0, steps: 5), 1)
        XCTAssertEqual(developmentTraceStride(interval: 25, steps: 0), 1)
    }

    func testDevelopmentRawStepsParseAllOrAStepList() throws {
        XCTAssertEqual(try parseDevelopmentRawSteps("all"), .all)
        XCTAssertEqual(try parseDevelopmentRawSteps("0, 500,1000"), .steps([0, 500, 1000]))
        for text in ["", "0,", "-5", "first", "0;500"] {
            XCTAssertThrowsError(try parseDevelopmentRawSteps(text), text)
        }
    }

    func testDeclaredRawStepsMustBeSampled() throws {
        let sampled = [0, 25, 50, 75]
        XCTAssertNoThrow(try checkDevelopmentRawSteps(.steps([0, 75]), sampledSteps: sampled))
        XCTAssertNoThrow(try checkDevelopmentRawSteps(.all, sampledSteps: sampled))
        XCTAssertNoThrow(try checkDevelopmentRawSteps(nil, sampledSteps: sampled))
        XCTAssertThrowsError(try checkDevelopmentRawSteps(.steps([0, 60]), sampledSteps: sampled))
    }
}

final class BatchedReplayTests: XCTestCase {
    private func runtime(R: Double, m: Double, seed: Int) throws -> LeniaRuntimeConfig {
        let config: [String: Any] = [
            "backend": "metal-full",
            "channels": 1,
            "connectivity": [[2]],
            "flow": ["dt": 0.2, "n": 2, "theta_A": 2],
            "grid": ["sx": 32, "sy": 32],
            "implementation": ["mode": "flowlenia_2022_paper_equations"],
            "init": ["a_uniform": ["high": 1, "low": 0], "patches": [["center": [16, 16], "size": 10]], "seed": seed],
            "interventions": [],
            "parameter_embedding": ["enabled": false, "mix": "avg"],
            "params": [
                "mode": "explicit", "R": R, "seed": 0,
                "a": [[0.3, 0.6, 0.9], [0.2, 0.5, 0.8]],
                "b": [[1.0, 0.4, 0.7], [0.6, 1.0, 0.3]],
                "w": [[0.05, 0.1, 0.08], [0.07, 0.04, 0.12]],
                "r": [0.8, 0.6], "m": [m, 0.25], "s": [0.03, 0.04], "h": [0.6, 0.4],
            ],
            "profile": "experimental",
            "reintegration": ["border": "torus", "dd": 5, "sigma": 0.65],
            "run": ["steps": 40],
        ]
        return try loadRuntimeConfig(from: JSONSerialization.data(withJSONObject: config))
    }

    private func capture(samples: Int) -> (FrameCapture, () -> [[Int: [Float]]]) {
        final class Box { var frames: [[Int: [Float]]] = [] }
        let box = Box()
        box.frames = Array(repeating: [:], count: samples)
        let capture = FrameCapture(
            stride: 10,
            includeWarmup: true,
            handler: { _, _, _, _ in },
            stateHandler: { sample, step, _, _, _, values in box.frames[sample][step] = values }
        )
        return (capture, { box.frames })
    }

    /// The batched replay is only valid if a body's trajectory does not depend on its batch
    /// neighbours or on running under population kernels instead of its own fixed rule.
    func testExplicitParamsBatchMatchesSingleBodyRuns() throws {
        let bodies = [try runtime(R: 5, m: 0.15, seed: 3), try runtime(R: 6.5, m: 0.2, seed: 7)]
        let search = SearchConfig(
            steps: 40, recordInterval: 10, warmupSteps: 0, occupancyThreshold: 0.05,
            massChannel: -1, scoreWeights: [:], filters: [:], complexity: nil,
            activity: nil, stability: nil
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys

        var singleFrames: [[Int: [Float]]] = []
        var singleMetrics: [Data] = []
        for (body, seed) in zip(bodies, [3, 7]) {
            let (capture, frames) = capture(samples: 1)
            let result = try XCTUnwrap(SearchEngine(runtimeConfig: body).runBatch(
                seeds: [0], initSeedOffset: seed, searchConfig: search, frameCapture: capture
            ).first)
            singleFrames.append(frames()[0])
            singleMetrics.append(try encoder.encode(result.metrics))
        }

        let (capture, frames) = capture(samples: 2)
        let batched = SearchEngine(runtimeConfig: bodies[0]).runBatch(
            seeds: [3, 7], initSeedOffset: 0, searchConfig: search, frameCapture: capture,
            explicitParamsBatch: bodies.map(\.params)
        )
        XCTAssertEqual(batched.count, 2)
        XCTAssertEqual(frames()[0].count, singleFrames[0].count)
        XCTAssertGreaterThanOrEqual(singleFrames[0].count, 4)
        for index in 0..<2 {
            XCTAssertEqual(frames()[index], singleFrames[index], "state of body \(index)")
            XCTAssertEqual(try encoder.encode(batched[index].metrics), singleMetrics[index], "metrics of body \(index)")
        }
        XCTAssertNotEqual(singleFrames[0], singleFrames[1])
    }

    /// Perturbation studies restart bodies from a recorded state, so a batch restarted from each
    /// body's step-20 state must continue exactly as the uninterrupted runs do.
    func testExplicitStatePatchesRestartBatchExactly() throws {
        let bodies = [try runtime(R: 5, m: 0.15, seed: 3), try runtime(R: 6.5, m: 0.2, seed: 7)]
        let search = SearchConfig(
            steps: 40, recordInterval: 10, warmupSteps: 0, occupancyThreshold: 0.05,
            massChannel: -1, scoreWeights: [:], filters: [:], complexity: nil,
            activity: nil, stability: nil
        )
        let (fullCapture, fullFrames) = capture(samples: 2)
        _ = SearchEngine(runtimeConfig: bodies[0]).runBatch(
            seeds: [3, 7], initSeedOffset: 0, searchConfig: search, frameCapture: fullCapture,
            explicitParamsBatch: bodies.map(\.params)
        )
        let full = fullFrames()
        let restartStates = try (0..<2).map { index in
            InitStatePatchConfig(center: [16, 16], width: 32, height: 32, channels: 1, values: try XCTUnwrap(full[index][20]))
        }

        let restartSearch = SearchConfig(
            steps: 20, recordInterval: 10, warmupSteps: 0, occupancyThreshold: 0.05,
            massChannel: -1, scoreWeights: [:], filters: [:], complexity: nil,
            activity: nil, stability: nil
        )
        let (restartCapture, restartFrames) = capture(samples: 2)
        _ = SearchEngine(runtimeConfig: bodies[0]).runBatch(
            seeds: [0, 0], initSeedOffset: 0, searchConfig: restartSearch, frameCapture: restartCapture,
            explicitParamsBatch: bodies.map(\.params), explicitStatePatches: restartStates
        )
        let restarted = restartFrames()
        for index in 0..<2 {
            XCTAssertEqual(Set(restarted[index].keys), [10, 20])
            for offset in [10, 20] {
                XCTAssertTrue(restarted[index][offset] == full[index][20 + offset], "body \(index) at step \(20 + offset)")
            }
        }
        XCTAssertNotEqual(full[0][40], full[1][40])
    }
}
