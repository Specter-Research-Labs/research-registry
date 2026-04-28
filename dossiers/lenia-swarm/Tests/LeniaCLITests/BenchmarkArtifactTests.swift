import Foundation
import XCTest
@testable import LeniaCLIKit

final class BenchmarkArtifactTests: XCTestCase {
    override func tearDown() {
        unsetenv("SPECTER_ARTIFACT_ROOT")
        super.tearDown()
    }

    func testWriteBenchmarkArtifactResolvesCanonicalOutputAndRoundTrips() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        setenv("SPECTER_ARTIFACT_ROOT", root.path, 1)

        let artifact = BenchmarkArtifactFile(
            schemaVersion: 1,
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
            backends: [
                BenchmarkBackendArtifact(
                    backend: "Metal Full",
                    throughput: BenchmarkSeriesArtifact(min: 10, max: 12, mean: 11, median: 11),
                    durationSeconds: BenchmarkSeriesArtifact(min: 0.1, max: 0.2, mean: 0.15, median: 0.15),
                    simStepsPerSecond: BenchmarkSeriesArtifact(min: 100, max: 120, mean: 110, median: 110),
                    stageTimingsMedian: BenchmarkStageTimingsArtifact(
                        prepareMs: 0.1,
                        fftMs: 0.2,
                        growthReduceMs: 0.3,
                        flowMs: 0.4,
                        reintegrateMs: 0.5,
                        totalMs: 1.5
                    ),
                    searchProfileMedian: BenchmarkSearchProfileArtifact(
                        stateBuildMs: 1,
                        parameterBuildMs: 2,
                        foodBuildMs: 3,
                        wallBuildMs: 4,
                        chemFieldBuildMs: 5,
                        runnerSetupMs: 6,
                        rolloutMs: 7,
                        summaryReductionMs: 8,
                        materializationMs: 9,
                        postprocessMs: 10,
                        totalMs: 55
                    ),
                    evolutionProfileMedian: nil,
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
            output: "outputs/benchmarks",
            dossier: dossierName
        )

        XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
        XCTAssertTrue(url.path.hasPrefix(root.appendingPathComponent("lenia-swarm/outputs/benchmarks").path))

        let decoded = try JSONDecoder().decode(BenchmarkArtifactFile.self, from: Data(contentsOf: url))
        XCTAssertEqual(decoded.mode, "search")
        XCTAssertEqual(decoded.backends.count, 1)
        XCTAssertEqual(decoded.backends[0].backend, "Metal Full")
        let searchProfile = try XCTUnwrap(decoded.backends[0].searchProfileMedian)
        XCTAssertEqual(searchProfile.runnerSetupMs, 6, accuracy: 1e-6)
    }
}
