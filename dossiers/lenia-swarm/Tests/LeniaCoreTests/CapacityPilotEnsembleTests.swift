import Foundation
import XCTest
@testable import LeniaCore

final class CapacityPilotEnsembleTests: XCTestCase {
    private let field: [Float] = (0..<64).map { $0 % 3 == 0 ? 0 : Float($0) / 7 }

    func testMemberZeroIsUnperturbed() throws {
        let start = try CapacityPilotPerturbation(seed: 9, member: 0, cells: 3).apply(field)
        XCTAssertEqual(start.values, field)
        XCTAssertEqual(start.record.entries, [])
    }

    func testPerturbationIsDeterministicAndMovesDistinctPositiveEntriesOneUlp() throws {
        let first = try CapacityPilotPerturbation(seed: 9, member: 4, cells: 3).apply(field)
        let again = try CapacityPilotPerturbation(seed: 9, member: 4, cells: 3).apply(field)
        XCTAssertEqual(first.values, again.values)
        XCTAssertEqual(first.record.entries, again.record.entries)
        XCTAssertEqual(first.record.startSha256, again.record.startSha256)
        XCTAssertEqual(Set(first.record.entries.map(\.index)).count, 3)
        for entry in first.record.entries {
            XCTAssertGreaterThan(field[entry.index], 0)
            XCTAssertEqual(first.values[entry.index], entry.direction == "up" ? field[entry.index].nextUp : field[entry.index].nextDown)
        }
        let changed = field.indices.filter { first.values[$0] != field[$0] }
        XCTAssertEqual(Set(changed), Set(first.record.entries.map(\.index)))

        let otherMember = try CapacityPilotPerturbation(seed: 9, member: 5, cells: 3).apply(field)
        let otherSeed = try CapacityPilotPerturbation(seed: 10, member: 4, cells: 3).apply(field)
        XCTAssertNotEqual(otherMember.record.startSha256, first.record.startSha256)
        XCTAssertNotEqual(otherSeed.record.startSha256, first.record.startSha256)
    }

    func testPerturbationPinsItsDrawSequence() throws {
        let record = try CapacityPilotPerturbation(seed: 20_261_114, member: 1, cells: 2).apply(field).record
        XCTAssertEqual(record.entries.map(\.index), Self.pinnedIndices)
        XCTAssertEqual(record.entries.map(\.direction), Self.pinnedDirections)
    }

    func testPerturbationDrawsBodyCellsOverANearZeroBackground() throws {
        var background = [Float](repeating: 1e-9, count: 64)
        background[40] = 1
        background[41] = 2
        for member in 1...8 {
            let record = try CapacityPilotPerturbation(seed: 9, member: member, cells: 2).apply(background).record
            XCTAssertEqual(Set(record.entries.map(\.index)), [40, 41])
        }
    }

    func testPerturbationNeedsEnoughPositiveEntries() {
        XCTAssertThrowsError(try CapacityPilotPerturbation(seed: 0, member: 1, cells: 2).apply([0, 1, 0])) { error in
            XCTAssertTrue("\(error.localizedDescription)".contains("needs 2 positive entries"))
        }
    }

    func testWilsonMatchesClosedForm() {
        let mid = capacityPilotWilson(successes: 5, trials: 16)
        XCTAssertEqual(mid[0], 0.14164643854782039, accuracy: 1e-15)
        XCTAssertEqual(mid[1], 0.5559564416525933, accuracy: 1e-15)
        XCTAssertEqual(capacityPilotWilson(successes: 0, trials: 16)[0], 0)
        XCTAssertEqual(capacityPilotWilson(successes: 0, trials: 16)[1], 0.1936076805344365, accuracy: 1e-15)
        XCTAssertEqual(capacityPilotWilson(successes: 16, trials: 16)[0], 0.8063923194655637, accuracy: 1e-15)
        XCTAssertEqual(capacityPilotWilson(successes: 16, trials: 16)[1], 1)
    }

    func testVarianceSplitsIntoAcrossMemberAndAcrossCondition() throws {
        let split = try XCTUnwrap(capacityPilotVarianceSplit([[1, 2, 3], [4, 5, 6], []]))
        XCTAssertEqual(split.values, 6)
        XCTAssertEqual(split.total, 17.5 / 6, accuracy: 1e-12)
        XCTAssertEqual(split.acrossMember, 4.0 / 6, accuracy: 1e-12)
        XCTAssertEqual(split.acrossCondition, 13.5 / 6, accuracy: 1e-12)
        XCTAssertNil(capacityPilotVarianceSplit([[], []]))
    }

    func testProbabilityCountsUndefinedMembersSeparately() {
        let probability = CapacityPilotProbability([true, false, nil, true])
        XCTAssertEqual(probability.successes, 2)
        XCTAssertEqual(probability.defined, 3)
        XCTAssertEqual(probability.undefined, 1)
        XCTAssertEqual(probability.probability, 2.0 / 3)
        XCTAssertNil(CapacityPilotProbability([nil]).probability)
    }

    #if canImport(Metal)
    func testCPURepeatReproducesEveryOutputHash() throws {
        try LeniaMetalLibrarySupport.ensureAvailable()
        let config = interactiveRuntimeConfig(backend: .cpu)
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        func run(member: Int, sink: CapacityPilotSink) throws -> [String: String] {
            let harness = CapacityPilotHarness(config: config, phantom: nil, sink: sink,
                                               perturbation: CapacityPilotPerturbation(seed: 3, member: member, cells: 1))
            try harness.run(.development(horizon: 64, ancestry: nil), field: nil) { _ in }
            return harness.hashes
        }
        let written = try run(member: 2, sink: .directory(directory))
        XCTAssertEqual(try run(member: 2, sink: .hashOnly), written)
        XCTAssertNotEqual(try run(member: 0, sink: .hashOnly)["frame:development@0"], written["frame:development@0"])
        for (name, digest) in written where !name.hasPrefix("frame:") {
            let data = try Data(contentsOf: directory.appendingPathComponent(name))
            XCTAssertEqual(ProvenanceDigest.sha256Hex(data), digest, name)
        }
    }
    #endif

    /// Computed outside Swift from the documented SplitMix64 scheme.
    private static let pinnedIndices = [40, 52]
    private static let pinnedDirections = ["down", "up"]
}
