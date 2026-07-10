import MLX
import XCTest
@testable import LeniaCore
@testable import LeniaStudio

final class FlowNativeOrganismResourceTests: XCTestCase {
    func testPrimaryFlowResourcesRemainCoherentForSixHundredMetalSteps() throws {
        let primary = try bundledFeaturedOrganisms().filter {
            $0.catalogCollection == .flowNative && $0.catalogTier == .primary
        }
        XCTAssertFalse(primary.isEmpty)
        try LeniaMetalLibrarySupport.ensureAvailable()

        for organism in primary {
            let data = try Data(contentsOf: URL(fileURLWithPath: organism.path))
            let runtime = try loadRuntimeConfig(from: data)
            let failures = flowPrimaryObservationFailures(runtime)
            XCTAssertTrue(
                failures.isEmpty,
                "\(organism.displayName): \(failures.joined(separator: "; "))"
            )
        }
    }

    func testExperimentalFlowResourcesRemainLocalizedForSixHundredMetalSteps() throws {
        let experimental = try bundledFeaturedOrganisms().filter {
            $0.catalogCollection == .flowNative && $0.catalogTier == .experimental
        }
        XCTAssertFalse(experimental.isEmpty)
        try LeniaMetalLibrarySupport.ensureAvailable()

        for organism in experimental {
            let data = try Data(contentsOf: URL(fileURLWithPath: organism.path))
            let runtime = try loadRuntimeConfig(from: data)
            let failures = flowExperimentalObservationFailures(runtime)
            XCTAssertTrue(
                failures.isEmpty,
                "\(organism.displayName): \(failures.joined(separator: "; "))"
            )
        }
    }

    func testFlowNativeResourcesAreSelfContainedMetalReplays() throws {
        let expectedIDs = Set([
            "flow-compact-b0cd1441",
            "flow-sail-0aa5d7b6",
        ])
        let configs = try bundledFeaturedOrganisms().filter {
            $0.featuredDescriptor?.collection == .flowNative
        }

        XCTAssertEqual(Set(configs.compactMap { $0.featuredDescriptor?.id }), expectedIDs)
        XCTAssertEqual(configs.count, expectedIDs.count)

        for config in configs {
            let data = try Data(contentsOf: URL(fileURLWithPath: config.path))
            let runtime = try loadRuntimeConfig(from: data)
            let patch = try XCTUnwrap(runtime.statePatch, config.displayName)
            let values = patch.decodedValues()
            let document = try XCTUnwrap(
                JSONSerialization.jsonObject(with: data) as? [String: Any]
            )
            let provenance = try XCTUnwrap(document["provenance"] as? [String: Any])

            XCTAssertEqual(runtime.backend, .metalFull)
            XCTAssertEqual(runtime.implementation.mode, "flowlenia_2022_paper_equations")
            XCTAssertEqual(runtime.channels, 2)
            XCTAssertEqual(runtime.nbK, 20)
            XCTAssertEqual(runtime.aUniform.low, 0)
            XCTAssertEqual(runtime.aUniform.high, 0)
            XCTAssertTrue(runtime.patches.isEmpty)
            XCTAssertGreaterThan(patch.width, 0)
            XCTAssertLessThanOrEqual(patch.width, runtime.sx)
            XCTAssertGreaterThan(patch.height, 0)
            XCTAssertLessThanOrEqual(patch.height, runtime.sy)
            XCTAssertEqual(patch.channels, 2)
            XCTAssertEqual(values.count, patch.width * patch.height * patch.channels)
            XCTAssertTrue(values.allSatisfy(\.isFinite))
            XCTAssertGreaterThan(values.max() ?? 0, 0.1)
            XCTAssertTrue(labConfigRequiresCanonicalRuntime(runtime))

            let expectedBundleKind = config.catalogTier == .primary
                ? "strict_replay_bundle_v1"
                : "experimental_replay_bundle_v1"
            XCTAssertEqual(provenance["bundle_kind"] as? String, expectedBundleKind)
            XCTAssertEqual(provenance["replay_verified"] as? Bool, true)
            XCTAssertNotNil(provenance["source"] as? String)
            XCTAssertNotNil(provenance["source_base_sha256"] as? String)
            XCTAssertNotNil(provenance["source_config_hash"] as? String)
            XCTAssertNotNil(provenance["source_specimen_id"] as? String)
            if config.catalogTier == .experimental {
                XCTAssertEqual(provenance["replay_tier"] as? String, "coherent_remodeling_600")
                XCTAssertNotNil(provenance["replay_validation_sha256"] as? String)
            }
        }
    }
}

private struct FlowPrimaryObservationFrame {
    let step: Int
    let mass: Float
    let supportCount: Int
    let boundaryClearance: Int
    let significantComponentCount: Int
    let largestComponentFraction: Float
    let materializedMass: MassBatchCPU
}

private enum FlowObservationTier {
    case primary
    case experimental
}

private func flowPrimaryObservationFailures(_ runtime: LeniaRuntimeConfig) -> [String] {
    flowObservationFailures(runtime, tier: .primary)
}

private func flowExperimentalObservationFailures(_ runtime: LeniaRuntimeConfig) -> [String] {
    flowObservationFailures(runtime, tier: .experimental)
}

private func flowObservationFailures(
    _ runtime: LeniaRuntimeConfig,
    tier: FlowObservationTier
) -> [String] {
    guard runtime.backend == .metalFull else {
        return ["backend is \(runtime.backend.rawValue), expected metal-full"]
    }
    guard FlowLeniaInteractiveSimulator.supportsResidentMetal(runtime) else {
        return ["configuration is not supported by resident Metal"]
    }

    let threshold: Float = 0.05
    let useTorus = runtime.border == "torus"
    let requiredClearance = useTorus
        ? (tier == .experimental ? 1 : 0)
        : Int(ceil(runtime.params.R)) + 2
    let supportRange: ClosedRange<Float> = tier == .primary ? 0.75...1.25 : 0.65...1.35
    let simulator = FlowLeniaInteractiveSimulator(runtimeConfig: runtime)
    var state = simulator.makeInitialState()
    var frames: [FlowPrimaryObservationFrame] = []
    for targetStep in [0, 150, 300, 450, 600] {
        if state.step < targetStep {
            state = simulator.step(state, count: targetStep - state.step)
        }
        let matter = simulator.matterMap(for: state)
        let batch = materializeMassBatch(matter)
        let components = computeComponentStructureBatch(
            materialized: batch,
            threshold: threshold,
            useTorus: useTorus,
            significantMassMinimum: threshold * 4,
            significantMassFraction: 0.01
        )
        var supportCount = 0
        var minRow = batch.height
        var minColumn = batch.width
        var maxRow = -1
        var maxColumn = -1
        for row in 0..<batch.height {
            for column in 0..<batch.width where batch.flat[row * batch.width + column] > threshold {
                supportCount += 1
                minRow = min(minRow, row)
                minColumn = min(minColumn, column)
                maxRow = max(maxRow, row)
                maxColumn = max(maxColumn, column)
            }
        }
        let clearance = supportCount == 0
            ? -1
            : min(minRow, min(minColumn, batch.height - 1 - maxRow, batch.width - 1 - maxColumn))
        frames.append(FlowPrimaryObservationFrame(
            step: targetStep,
            mass: batch.flat.reduce(0, +),
            supportCount: supportCount,
            boundaryClearance: clearance,
            significantComponentCount: Int(components.significantCount[0].rounded()),
            largestComponentFraction: components.largestFraction[0],
            materializedMass: batch
        ))
    }

    guard let initial = frames.first, initial.mass > 0, initial.supportCount > 0 else {
        return ["initial state has no active matter"]
    }
    var failures: [String] = []
    for (index, frame) in frames.enumerated() {
        let massRatio = frame.mass / initial.mass
        let supportRatio = Float(frame.supportCount) / Float(initial.supportCount)
        let initialOverlap = computeCoherentTransportBatch(
            source: initial.materializedMass,
            target: frame.materializedMass,
            threshold: threshold,
            useTorus: useTorus
        ).translatedShapeOverlap[0]
        let adjacentOverlap = index == 0 ? 1 : computeCoherentTransportBatch(
            source: frames[index - 1].materializedMass,
            target: frame.materializedMass,
            threshold: threshold,
            useTorus: useTorus
        ).translatedShapeOverlap[0]

        if !(0.92...1.08).contains(massRatio) {
            failures.append("step \(frame.step) mass ratio \(massRatio)")
        }
        if !supportRange.contains(supportRatio) {
            failures.append("step \(frame.step) support ratio \(supportRatio)")
        }
        if frame.boundaryClearance < requiredClearance {
            failures.append("step \(frame.step) boundary clearance \(frame.boundaryClearance) < \(requiredClearance)")
        }
        if frame.significantComponentCount != 1 {
            failures.append("step \(frame.step) significant components \(frame.significantComponentCount)")
        }
        if frame.largestComponentFraction < 0.95 {
            failures.append("step \(frame.step) largest component fraction \(frame.largestComponentFraction)")
        }
        if tier == .primary {
            if initialOverlap < 0.65 {
                failures.append("step \(frame.step) initial translated overlap \(initialOverlap)")
            }
            if adjacentOverlap < 0.72 {
                failures.append("step \(frame.step) adjacent translated overlap \(adjacentOverlap)")
            }
        }
    }
    return failures
}
