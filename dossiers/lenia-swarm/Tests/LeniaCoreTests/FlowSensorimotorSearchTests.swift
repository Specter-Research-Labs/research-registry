import Foundation
import XCTest
@testable import LeniaCore
import MLX
import Logging

// End-to-end smoke of the IMGEP search: random-init seeding, goal sampling,
// gradient descent with Adam, mutation, and archive evaluation must run to
// completion and produce finite behavior descriptors and losses.
private final class FlowSensorimotorSearchMarker {}

final class FlowSensorimotorSearchTests: XCTestCase {
    override func setUp() {
        super.setUp()
        do {
            try LeniaMetalLibrarySupport.ensureAvailable(
                executableURL: Bundle(for: FlowSensorimotorSearchMarker.self).executableURL
            )
        } catch {
            XCTFail("Failed to prepare MLX metallib: \(error)")
        }
    }

    private func smallConfig() -> FlowSensorimotorConfig {
        FlowSensorimotorConfig(
            paper: "flow-lenia-sensorimotor-test",
            grid: .init(sx: 48, sy: 48),
            physics: .init(
                nbK: 3, bumpsPerKernel: 1, dd: 3, sigma: 0.65, dt: 0.1, n: 2, thetaA: 1.0, kernelRadius: 13.0,
                kernelProfile: "flowlenia_2022_colab", gradientBoundary: "zero_pad",
                alphaMode: "mass", flowClip: "none", growthProfile: "gaussian", useTorus: false
            ),
            ruleSpace: .init(
                a: .init(low: 0.3, high: 0.6), w: .init(low: 0.1, high: 0.2), b: .init(low: 0.4, high: 0.8),
                r: .init(low: 0.6, high: 0.9), m: .init(low: 0.1, high: 0.2),
                s: .init(low: 0.01, high: 0.02), h: .init(low: 0.2, high: 0.4)
            ),
            initialization: .init(size: 8, origin: [20, 20], valueRange: [0.0, 0.5]),
            obstacles: .init(count: 1, radius: 4, potentialHeight: 5.0, leftHalfClear: false, clearInitializationRadius: 8),
            viability: .init(componentMassThreshold: 0.01, maxGyration: 18.0, minLargestComponentFraction: 0.5, maxComponentCount: 3),
            outerSteps: 6,
            historyInitializationTrials: 4,
            rolloutSteps: 12,
            evaluationRollouts: 1,
            goalSampling: .init(
                warmupSteps: 1, warmupStart: [0.0, 0.0], warmupDelta: [0.05, 0.0],
                compactnessGoalMean: 0.1, compactnessJitterStd: 0.005,
                bestGoalProbability: 0.3, randomFarProbability: 0.5,
                bestGoalXOffset: [-0.05, 0.05], bestGoalYOffset: [-0.05, 0.05],
                farXRange: [-0.2, 0.2], farYRange: [-0.2, 0.2],
                broadXRange: [-0.2, 0.2], broadYRange: [-0.2, 0.2],
                closeDistance: 0.1, veryCloseDistance: 0.05, minCloseNeighbors: 0, maxVeryCloseNeighbors: 1000
            ),
            optimization: .init(stepsUnmutated: 2, stepsMutated: 1, ruleLr: 0.0008, initializationLr: 0.008, betas: [0.9, 0.999], eps: 1e-8),
            mutation: .init(mutateEveryNSteps: 3, ruleStd: 0.01, initStd: 0.02, viabilityTrials: 2),
            restart: .init(maxAttempts: 2, minAliveRandomInitializations: 0, maxLoss: 1e9),
            evaluation: .init(obstacleRollouts: 2, movingMinDisplacement: 1.0)
        )
    }

    func testSearchProducesFiniteHistory() {
        let runner = FlowSensorimotorRunner(config: smallConfig(), logger: Logger(label: "test"))
        let result = runner.search(seed: 7)

        XCTAssertEqual(result.records.count, 6, "permissive restart thresholds should let one attempt fill the history")
        for record in result.records {
            XCTAssertTrue(record.reached.compactness.isFinite)
            XCTAssertTrue(record.reached.x.isFinite)
            XCTAssertTrue(record.reached.y.isFinite)
            if let loss = record.trainingLoss {
                XCTAssertTrue(loss.isFinite, "training loss at step \(record.step) must be finite")
            }
        }
        let exploration = result.records.filter { $0.goal != nil }
        XCTAssertEqual(exploration.count, 2, "history beyond the initialization trials is goal-directed")
    }

    func testRunWritesReproducibleArtifacts() throws {
        let runner = FlowSensorimotorRunner(config: smallConfig(), logger: Logger(label: "test"))
        let outputDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("flow-sensorimotor-\(UInt64(7))-test", isDirectory: true)
        try? FileManager.default.removeItem(at: outputDirectory)
        defer { try? FileManager.default.removeItem(at: outputDirectory) }

        let summary = try runner.run(seed: 7, outputDirectory: outputDirectory, runId: "test-run")
        XCTAssertEqual(summary.historyCount, 6)
        XCTAssertTrue(summary.agency.obstacleRobustness >= 0 && summary.agency.obstacleRobustness <= 1)

        let decoder = JSONDecoder()
        let configData = try Data(contentsOf: outputDirectory.appendingPathComponent("config.json"))
        XCTAssertNoThrow(try decoder.decode(FlowSensorimotorConfig.self, from: configData))

        let bestData = try Data(contentsOf: outputDirectory.appendingPathComponent("best.json"))
        let best = try decoder.decode(FlowSensorimotorBestResult.self, from: bestData)
        XCTAssertEqual(best.candidate.r.count, 3, "candidate carries the per-kernel rule parameters")

        let summaryData = try Data(contentsOf: outputDirectory.appendingPathComponent("summary.json"))
        XCTAssertNoThrow(try decoder.decode(FlowSensorimotorRunSummary.self, from: summaryData))

        let historyText = try String(contentsOf: outputDirectory.appendingPathComponent("history.jsonl"), encoding: .utf8)
        let lines = historyText.split(separator: "\n")
        XCTAssertEqual(lines.count, 6, "one history line per outer step")
        for line in lines {
            XCTAssertNoThrow(try decoder.decode(FlowSensorimotorHistoryEntry.self, from: Data(line.utf8)))
        }
    }
}
