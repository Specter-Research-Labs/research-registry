import Foundation
import XCTest
@testable import LeniaCLIKit
import LeniaCore

final class EcologyExportTests: XCTestCase {
    func testEcologyExportWritesEmbeddingPlotAndPCA() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-ecology-tests-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let runDir = root.appendingPathComponent("run-001", isDirectory: true)
        let libraryDir = runDir.appendingPathComponent("library", isDirectory: true)
        let overallDir = runDir.appendingPathComponent("overall", isDirectory: true)
        try fm.createDirectory(at: libraryDir, withIntermediateDirectories: true)
        try fm.createDirectory(at: overallDir, withIntermediateDirectories: true)

        let creature = makeEcologyCreature(
            id: UUID(uuidString: "40404040-4040-4040-4040-404040404040")!,
            name: "test-creature",
            seed: 7,
            score: 0.99,
            fingerprintByte: 0x40
        )

        struct Entry: Codable {
            let creature: SavedCreature
            let campaign_id: String?
            let run_id: String
            let recorded_at: Date
        }

        let entryA = Entry(creature: creature, campaign_id: nil, run_id: "run-001", recorded_at: Date())
        let creature2 = makeEcologyCreature(
            id: UUID(uuidString: "50505050-5050-5050-5050-505050505050")!,
            name: "test-creature-2",
            seed: 8,
            score: 0.99,
            fingerprintByte: 0x50
        )
        let entryB = Entry(creature: creature2, campaign_id: nil, run_id: "run-001", recorded_at: Date())

        let encoder = JSONEncoder()
        let libraryPath = libraryDir.appendingPathComponent("index.jsonl")
        let aData = try encoder.encode(entryA)
        let bData = try encoder.encode(entryB)
        try (
            String(data: aData, encoding: .utf8)! + "\n" +
            String(data: bData, encoding: .utf8)! + "\n"
        ).write(to: libraryPath, atomically: true, encoding: .utf8)

        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        var index = try IndexCommand.parseAsRoot([
            "--run-dir", runDir.path,
            "--db", dbPath,
            "--rebuild",
        ])
        try index.run()

        let outDir = root.appendingPathComponent("ecology-out", isDirectory: true)
        var ecology = try EcologyCommand.parseAsRoot([
            "--db", dbPath,
            "--output", outDir.path,
            "--plot",
            "--pca",
            "--pca-max-rows", "100",
        ])
        try ecology.run()

        let files = try fm.contentsOfDirectory(atPath: outDir.path)
        let summaryName = files.first { $0.contains("ecology-summary.json") }
        XCTAssertNotNil(summaryName)
        let summaryURL = outDir.appendingPathComponent(summaryName!)

        let summaryData = try Data(contentsOf: summaryURL)
        let summary = try JSONSerialization.jsonObject(with: summaryData) as! [String: Any]
        XCTAssertNotNil(summary["dataFile"] as? String)
        XCTAssertNotNil(summary["plotFile"] as? String)
        XCTAssertNotNil(summary["pcaFile"] as? String)

        let dataPath = summary["dataFile"] as! String
        let plotPath = summary["plotFile"] as! String
        let pcaPath = summary["pcaFile"] as! String
        XCTAssertTrue(fm.fileExists(atPath: dataPath))
        XCTAssertTrue(fm.fileExists(atPath: plotPath))
        XCTAssertTrue(fm.fileExists(atPath: pcaPath))

        let pcaText = try String(contentsOfFile: pcaPath, encoding: .utf8)
        XCTAssertFalse(pcaText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
    }

    func testEcologyLimitOrdersRowsByScore() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-ecology-order-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let runDir = root.appendingPathComponent("run-001", isDirectory: true)
        let libraryDir = runDir.appendingPathComponent("library", isDirectory: true)
        let overallDir = runDir.appendingPathComponent("overall", isDirectory: true)
        try fm.createDirectory(at: libraryDir, withIntermediateDirectories: true)
        try fm.createDirectory(at: overallDir, withIntermediateDirectories: true)

        struct Entry: Codable {
            let creature: SavedCreature
            let campaign_id: String?
            let run_id: String
            let recorded_at: Date
        }

        let creatures = [
            makeEcologyCreature(
                id: UUID(uuidString: "10101010-1010-1010-1010-101010101010")!,
                name: "low-score",
                seed: 1,
                score: 0.1,
                fingerprintByte: 0x10
            ),
            makeEcologyCreature(
                id: UUID(uuidString: "20202020-2020-2020-2020-202020202020")!,
                name: "top-score",
                seed: 2,
                score: 0.9,
                fingerprintByte: 0x20
            ),
            makeEcologyCreature(
                id: UUID(uuidString: "30303030-3030-3030-3030-303030303030")!,
                name: "mid-score",
                seed: 3,
                score: 0.5,
                fingerprintByte: 0x30
            ),
        ]

        let encoder = JSONEncoder()
        let libraryPath = libraryDir.appendingPathComponent("index.jsonl")
        let payload = try creatures.map {
            let entry = Entry(creature: $0, campaign_id: nil, run_id: "run-001", recorded_at: Date(timeIntervalSince1970: 1_700_000_000))
            return String(data: try encoder.encode(entry), encoding: .utf8)! + "\n"
        }.joined()
        try payload.write(to: libraryPath, atomically: true, encoding: .utf8)

        let dbPath = root.appendingPathComponent("compendium.sqlite").path
        var index = try IndexCommand.parseAsRoot([
            "--run-dir", runDir.path,
            "--db", dbPath,
            "--rebuild",
        ])
        try index.run()

        let outDir = root.appendingPathComponent("ecology-out", isDirectory: true)
        var ecology = try EcologyCommand.parseAsRoot([
            "--db", dbPath,
            "--output", outDir.path,
            "--limit", "2",
        ])
        try ecology.run()

        let files = try fm.contentsOfDirectory(atPath: outDir.path)
        let dataName = try XCTUnwrap(files.first { $0.contains("ecology-embedding.jsonl") })
        let dataURL = outDir.appendingPathComponent(dataName)
        let lines = try String(contentsOf: dataURL, encoding: .utf8)
            .split(whereSeparator: \.isNewline)
            .map(String.init)

        struct Row: Decodable {
            let id: String
        }

        let decoder = JSONDecoder()
        let ids = try lines.map { try decoder.decode(Row.self, from: Data($0.utf8)).id }
        XCTAssertEqual(ids, [
            "20202020-2020-2020-2020-202020202020",
            "30303030-3030-3030-3030-303030303030",
        ])
    }
}

private func makeEcologyCreature(
    id: UUID,
    name: String,
    seed: Int,
    score: Float,
    fingerprintByte: UInt8
) -> SavedCreature {
    let genotype = KernelParams(
        r: [1.0],
        b: [[0.1, 0.2, 0.3]],
        w: [[0.4, 0.5, 0.6]],
        a: [[0.7, 0.8, 0.9]],
        m: [0.15],
        s: [0.03],
        h: [1.0],
        R: 10.0
    )
    let initialCondition = InitConfig(
        seed: seed,
        patches: [],
        a_uniform: UniformRange(low: 0, high: 0),
        p_uniform: nil
    )
    let baseGenotypeDescriptor = morphospaceGenotypeDescriptor(genotype)
    let descriptorBundle = MorphospaceDescriptorBundle(
        symmetryPolicy: "translation_kernel_permutation_v1",
        genotype: MorphospaceGenotypeDescriptor(
            version: baseGenotypeDescriptor.version,
            canonicalizer: "kernel_permutation_sort_v1",
            kernelCount: baseGenotypeDescriptor.kernelCount,
            vectorLength: baseGenotypeDescriptor.vectorLength,
            vector: baseGenotypeDescriptor.vector,
            hash12: baseGenotypeDescriptor.hash12
        ),
        terminal: MorphospaceTerminalDescriptor(
            massChannel: 0,
            borderMode: "wall",
            symmetryPolicy: "translation_kernel_permutation_v1",
            fingerprintResolution: 32,
            fingerprintU8: Data(repeating: fingerprintByte, count: 32 * 32),
            angularSymmetry: MorphospaceAngularSymmetryDescriptor(
                binCount: 32,
                maxOrder: 8,
                harmonics: Array(repeating: 0.1, count: 8),
                dominantOrder: 2,
                dominantAmplitude: 0.2,
                normalizedEntropy: 0.5
            ),
            fingerprintHash12: String(repeating: String(fingerprintByte, radix: 16), count: 12).prefix(12).description,
            finalMass: 1,
            finalOccupancy: 0.2,
            finalGyration: 3,
            momentMass: 1,
            momentVolume: 1,
            momentDensity: 1,
            momentAnisotropy: 0.1,
            componentCount: 1,
            largestComponentFraction: 1,
            largestComponentAnisotropy: 0.1,
            hu1: 0.1,
            hu2: 0.1,
            hu3: 0.1,
            hu4: 0.1,
            hu5: 0.1,
            hu6: 0.1,
            hu7: 0.1,
            flusser1: 0.1,
            flusser2: 0.1,
            flusser3: 0.1,
            flusser4: 0.1,
            windowMassStd: 0.01,
            windowOccupancyStd: 0.01,
            windowGyrationStd: 0.01,
            isStable: true
        ),
        trajectory: MorphospaceTrajectoryDescriptor(
            recordInterval: 1,
            warmupSteps: 0,
            sampleCount: 4,
            pathLength: 1,
            displacement: 1,
            pathTortuosity: 1,
            movementEfficiency: 1,
            speedMean: 0.4,
            centerVelocity: 0.5,
            velocityX: 0.012,
            velocityY: -0.004,
            headingRad: -0.32175055,
            headingCircularVariance: 0.1,
            accumulatedTurnAbs: 0.2,
            survivalSteps: 20,
            activityEacMean: 0.1,
            activityEanMean: 0.2,
            activityDiversityMean: 0.3,
            activitySpeciesMean: 1.0,
            activitySpeciesMax: 2,
            activitySpeciesStd: 0.1,
            activityDiversityStd: 0.1,
            activityEacMax: 0.3,
            activityEanMax: 0.4,
            componentSeriesMean: 1.0,
            componentSeriesStd: 0.0,
            componentSeriesMax: 1
        )
    )
    return SavedCreature(
        id: id,
        name: name,
        ownerId: "tester",
        genotype: genotype,
        initialCondition: initialCondition,
        descriptorBundle: descriptorBundle,
        metrics: SimulationMetrics(
            massMean: 1,
            massStd: 0.1,
            massMin: 0,
            massMax: 2,
            occupancyMean: 0.2,
            varianceMean: 0.01,
            energyMean: 0.3,
            speedMean: 0.4,
            pathLength: 10,
            displacement: 2,
            sampleCount: 2,
            speedCount: 1,
            gyration: 3,
            centerVelocity: 0.5,
            velocityX: 0.012,
            velocityY: -0.004,
            headingRad: -0.32175055,
            isStable: true
        ),
        sweep: nil,
        score: score,
        scoreWeights: ["mass_mean": 1.0]
    )
}
