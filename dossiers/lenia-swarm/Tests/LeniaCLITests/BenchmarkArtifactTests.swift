import Foundation
import LeniaCore
import XCTest
@testable import LeniaCLIKit

final class BenchmarkArtifactTests: XCTestCase {
    func testWriteBenchmarkArtifactRoundTripsStableSchema() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let artifact = BenchmarkArtifactFile(
            schemaVersion: 2,
            generatedAt: benchmarkTimestampString(),
            host: "test-host",
            osVersion: "test-os",
            mode: "search",
            throughputUnit: "seeds_per_second",
            gridSize: 256,
            batchSize: 4,
            steps: 10,
            warmupRuns: 1,
            repeatRuns: 3,
            observationStride: 2,
            backends: [
                BenchmarkBackendArtifact(
                    backend: "Metal Full",
                    throughput: BenchmarkSeriesArtifact(min: 10, max: 12, mean: 11, median: 11),
                    durationSeconds: BenchmarkSeriesArtifact(min: 0.1, max: 0.2, mean: 0.15, median: 0.15),
                    simStepsPerSecond: BenchmarkSeriesArtifact(min: 100, max: 120, mean: 110, median: 110),
                    stageTimingsMedian: FlowSandboxMetalStageTimings(
                        prepareMs: 0.1,
                        fftMs: 0.2,
                        growthReduceMs: 0.3,
                        flowMs: 0.4,
                        reintegrateMs: 0.5,
                        totalMs: 1.5
                    ),
                    searchProfileMedian: SearchBatchProfile(
                        stateBuildMs: 1,
                        parameterBuildMs: 2,
                        foodBuildMs: 3,
                        wallBuildMs: 4,
                        chemFieldBuildMs: 5,
                        runnerSetupMs: 6,
                        rolloutMs: 7,
                        summaryReductionMs: 8,
                        combinedObservationMs: 8.5,
                        materializationMs: 9,
                        massObservationSynchronizations: 11,
                        postprocessMs: 10,
                        totalMs: 55
                    ),
                    evolutionProfileMedian: ESGenerationProfile(
                        candidateSetupMs: 1,
                        kernelCompileMs: 2,
                        stateBuildMs: 3,
                        fieldBuildMs: 4,
                        rolloutMs: 5,
                        fitnessMs: 6,
                        optimizerMs: 7,
                        totalMs: 28
                    ),
                    samples: [
                        BenchmarkSampleArtifact(
                            durationSeconds: 0.15,
                            throughput: 11,
                            simStepsPerSecond: 110,
                            stageTimings: nil,
                            searchProfile: nil,
                            evolutionProfile: nil
                        )
                    ]
                )
            ]
        )

        let url = try writeBenchmarkArtifact(
            artifact,
            runID: "benchmark-artifact-test",
            output: root.appendingPathComponent("outputs/benchmarks", isDirectory: true).path,
            dossier: dossierName
        )

        XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
        XCTAssertTrue(url.path.hasPrefix(root.appendingPathComponent("outputs/benchmarks").path))

        let data = try Data(contentsOf: url)
        let decoded = try JSONDecoder().decode(BenchmarkArtifactFile.self, from: data)
        XCTAssertEqual(decoded.mode, "search")
        XCTAssertEqual(decoded.schemaVersion, 2)
        XCTAssertEqual(decoded.observationStride, 2)
        XCTAssertEqual(decoded.backends.count, 1)
        XCTAssertEqual(decoded.backends[0].backend, "Metal Full")
        let searchProfile = try XCTUnwrap(decoded.backends[0].searchProfileMedian)
        XCTAssertEqual(searchProfile.runnerSetupMs, 6, accuracy: 1e-6)
        XCTAssertEqual(searchProfile.combinedObservationMs, 8.5, accuracy: 1e-6)
        XCTAssertEqual(searchProfile.massObservationSynchronizations, 11)

        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let backends = try XCTUnwrap(json["backends"] as? [[String: Any]])
        let backend = try XCTUnwrap(backends.first)
        XCTAssertEqual(
            Set(try XCTUnwrap(backend["stageTimingsMedian"] as? [String: Any]).keys),
            ["prepareMs", "fftMs", "growthReduceMs", "flowMs", "reintegrateMs", "totalMs"]
        )
        XCTAssertEqual(
            Set(try XCTUnwrap(backend["searchProfileMedian"] as? [String: Any]).keys),
            ["stateBuildMs", "parameterBuildMs", "foodBuildMs", "wallBuildMs", "chemFieldBuildMs", "runnerSetupMs", "rolloutMs", "summaryReductionMs", "combinedObservationMs", "materializationMs", "massObservationSynchronizations", "postprocessMs", "totalMs"]
        )
        XCTAssertEqual(
            Set(try XCTUnwrap(backend["evolutionProfileMedian"] as? [String: Any]).keys),
            ["candidateSetupMs", "kernelCompileMs", "stateBuildMs", "fieldBuildMs", "rolloutMs", "fitnessMs", "optimizerMs", "totalMs"]
        )
    }
}
