import XCTest
import Metal
import LeniaCore
import LeniaVisuals
@testable import LeniaStudio

final class LeniaStudioTests: XCTestCase {
    func testStudioInsightDerivedMotionSignals() throws {
        let metrics = makeMetrics(pathLength: 10, displacement: 2)

        XCTAssertEqual(try XCTUnwrap(studioTortuosity(metrics: metrics)), 5, accuracy: 0.0001)
        XCTAssertEqual(try XCTUnwrap(studioMovementEfficiency(metrics: metrics)), 0.2, accuracy: 0.0001)

        let items = studioComputationSections(for: metrics).flatMap(\.items)
        XCTAssertTrue(items.contains { $0.id == "tortuosity" && $0.value == "5.000" })
        XCTAssertTrue(items.contains { $0.id == "efficiency" && $0.value == "0.200" })
    }

    func testStudioMetricDiffRowsUseFirstEntryAsBaseline() throws {
        let baseline = makeEntry(
            id: "baseline",
            score: 0.5,
            metrics: makeMetrics(massMean: 2, centerVelocity: 0.1, pathLength: 4, displacement: 2)
        )
        let candidate = makeEntry(
            id: "candidate",
            score: 0.7,
            metrics: makeMetrics(massMean: 3, centerVelocity: 0.25, pathLength: 10, displacement: 2)
        )

        let rows = studioMetricDiffRows(for: [baseline, candidate])
        let mass = try XCTUnwrap(rows.first { $0.id == "mass" })
        XCTAssertEqual(mass.valueText(at: 0), "2.000")
        XCTAssertEqual(mass.valueText(at: 1), "3.000")
        XCTAssertEqual(mass.deltaText(at: 1), "+1.000")

        let tortuosity = try XCTUnwrap(rows.first { $0.id == "tortuosity" })
        XCTAssertEqual(tortuosity.valueText(at: 0), "2.000")
        XCTAssertEqual(tortuosity.valueText(at: 1), "5.000")
        XCTAssertEqual(tortuosity.deltaText(at: 1), "+3.000")
    }

    func testStudioCompareEntryCarriesClassificationContext() {
        let taxonomy = SpecimenTaxonomyRecord(
            familyID: "family-gliders",
            genusID: "genus-loopers",
            speciesID: "species-001",
            confidence: 0.82,
            method: "descriptor-knn",
            version: 2
        )
        let entry = makeEntry(
            id: "classified",
            score: 0.9,
            metrics: makeMetrics(),
            taxonomy: taxonomy,
            traitLabels: ["rotor", "glider"],
            runtimeCapabilities: ["flow", "ecology"]
        )

        XCTAssertEqual(entry.taxonomy?.familyID, "family-gliders")
        XCTAssertEqual(entry.taxonomy?.confidence, 0.82)
        XCTAssertEqual(entry.traitLabels, ["glider", "rotor"])
        XCTAssertEqual(entry.runtimeCapabilities, ["ecology", "flow"])
        XCTAssertEqual(entry.runtimeFamily, "flow-lenia")
        XCTAssertEqual(entry.sourceMode, "imgep")
        XCTAssertEqual(entry.sourceAlgorithm, "novelty-search")
    }

    func testPreferredStudioSurfaceFollowsProductRouting() {
        XCTAssertEqual(
            preferredStudioSurface(currentSelection: .lab, connectionState: .connected(role: .host)),
            .cluster
        )
        XCTAssertEqual(
            preferredStudioSurface(currentSelection: .lab, connectionState: .connected(role: .worker)),
            .cluster
        )
        XCTAssertEqual(
            preferredStudioSurface(currentSelection: .lab, connectionState: .connecting),
            .cluster
        )
        XCTAssertEqual(
            preferredStudioSurface(currentSelection: .cluster, connectionState: .error("boom")),
            .cluster
        )
        XCTAssertEqual(
            preferredStudioSurface(currentSelection: .lab, connectionState: .connected(role: .compendium)),
            .compendium
        )
        XCTAssertEqual(
            preferredStudioSurface(currentSelection: .compendium, connectionState: .disconnected),
            .compendium
        )
    }

    func testLeniaLabStageTransformMapsPointsUnderZoomAndOffset() {
        let transform = LeniaLabStageTransform(
            zoom: 1.5,
            offset: CGSize(width: 30, height: -20)
        )
        let viewSize = CGSize(width: 900, height: 700)
        let rect = transform.imageRect(
            viewSize: viewSize,
            gridSize: CGSize(width: 256, height: 256)
        )

        XCTAssertEqual(
            transform.gridPoint(
                for: CGPoint(x: rect.midX, y: rect.midY),
                viewSize: viewSize,
                gridSize: 256
            ),
            SIMD2<Int>(128, 128)
        )
        XCTAssertEqual(
            transform.gridPoint(
                for: CGPoint(x: rect.minX + 1, y: rect.minY + 1),
                viewSize: viewSize,
                gridSize: 256
            ),
            SIMD2<Int>(0, 0)
        )
        XCTAssertNil(
            transform.gridPoint(
                for: CGPoint(x: rect.maxX + 5, y: rect.maxY + 5),
                viewSize: viewSize,
                gridSize: 256
            )
        )
    }

    func testLeniaLabStageTransformZoomKeepsAnchorStable() {
        let transform = LeniaLabStageTransform()
        let viewSize = CGSize(width: 800, height: 600)
        let anchor = CGPoint(x: 400, y: 300)

        let zoomed = transform.zoomed(
            to: 2.0,
            around: anchor,
            viewSize: viewSize,
            gridSize: 256
        )

        XCTAssertEqual(
            transform.gridPoint(for: anchor, viewSize: viewSize, gridSize: 256),
            zoomed.gridPoint(for: anchor, viewSize: viewSize, gridSize: 256)
        )
        XCTAssertEqual(zoomed.zoom, 2.0, accuracy: 1e-6)
    }

    func testLeniaLabBrushRadiusSteppingClampsToRange() {
        XCTAssertEqual(labBrushRadiusStepping(from: 3, delta: 1), 4)
        XCTAssertEqual(labBrushRadiusStepping(from: 1, delta: -5), 1)
        XCTAssertEqual(labBrushRadiusStepping(from: 16, delta: 5), 16)
    }

    func testLeniaMetalFieldRendererProducesOffscreenImage() {
        guard let device = MTLCreateSystemDefaultDevice() else {
            XCTFail("Metal device unavailable")
            return
        }

        let renderer = LeniaMetalFieldRenderer(device: device)
        let bytes = Data((0..<64).map { UInt8(($0 * 4) % 255) })
        let frame = LeniaFieldFrame(
            step: 0,
            width: 8,
            height: 8,
            bytes: bytes
        )

        let image = renderer.renderImage(
            frame: frame,
            renderMode: .smoothMagma,
            outputSize: CGSize(width: 64, height: 64)
        )

        XCTAssertEqual(image?.width, 64)
        XCTAssertEqual(image?.height, 64)
    }

    func testTTFrameSequenceLoadsRawFrames() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("tt-frame-sequence-\(UUID().uuidString)")
        let frames = root.appendingPathComponent("frames")
        try FileManager.default.createDirectory(at: frames, withIntermediateDirectories: true)
        try Data([0, 64, 128, 255]).write(to: frames.appendingPathComponent("frame_000000.r8"))

        let manifest = """
        {
          "manifest_version": 1,
          "kind": "lenia_tt_frame_sequence",
          "backend": "tt",
          "config_path": "configs/base/paper_base_2c_128.json",
          "steps": 4,
          "frame_every": 2,
          "width": 2,
          "height": 2,
          "channels": 2,
          "projection": "matter",
          "batch_index": 0,
          "dtype": "uint8",
          "storage": "raw_r8",
          "final_mass_path": "mass_final.npy",
          "metadata": {
            "dt": 0.1,
            "dd": 5,
            "sigma": 0.65,
            "n": 2,
            "theta_a": 1.0,
            "border": "torus",
            "kernel_profile": "gaussian",
            "kernel_count": 3,
            "radius": 12.0
          },
          "frames": [
            {"step": 0, "path": "frames/frame_000000.r8"}
          ]
        }
        """
        let manifestURL = root.appendingPathComponent("manifest.json")
        try manifest.write(to: manifestURL, atomically: true, encoding: .utf8)
        defer { try? FileManager.default.removeItem(at: root) }

        let sequence = try TTFrameSequence.load(manifestURL: manifestURL)
        let frame = try sequence.frame(at: 0)

        XCTAssertEqual(sequence.frameCount, 1)
        XCTAssertEqual(frame.step, 0)
        XCTAssertEqual(frame.width, 2)
        XCTAssertEqual(frame.height, 2)
        XCTAssertEqual(frame.bytes, Data([0, 64, 128, 255]))
    }

    func testTTFrameSequenceRejectsWrongSizedFrameAtLoad() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("tt-frame-sequence-bad-\(UUID().uuidString)")
        let frames = root.appendingPathComponent("frames")
        try FileManager.default.createDirectory(at: frames, withIntermediateDirectories: true)
        try Data([0, 64, 128]).write(to: frames.appendingPathComponent("frame_000000.r8"))

        let manifest = """
        {
          "manifest_version": 1,
          "kind": "lenia_tt_frame_sequence",
          "backend": "tt",
          "config_path": "configs/base/paper_base_2c_128.json",
          "steps": 4,
          "frame_every": 2,
          "width": 2,
          "height": 2,
          "channels": 2,
          "projection": "matter",
          "batch_index": 0,
          "dtype": "uint8",
          "storage": "raw_r8",
          "final_mass_path": "mass_final.npy",
          "frames": [
            {"step": 0, "path": "frames/frame_000000.r8"}
          ]
        }
        """
        let manifestURL = root.appendingPathComponent("manifest.json")
        try manifest.write(to: manifestURL, atomically: true, encoding: .utf8)
        defer { try? FileManager.default.removeItem(at: root) }

        XCTAssertThrowsError(try TTFrameSequence.load(manifestURL: manifestURL)) { error in
            guard case TTFrameSequenceError.invalidFrameSize = error else {
                return XCTFail("Expected invalidFrameSize, got \(error)")
            }
        }
    }
}

private func makeMetrics(
    massMean: Float = 1.5,
    centerVelocity: Float = 0.125,
    pathLength: Float = 6,
    displacement: Float = 3
) -> SimulationMetrics {
    SimulationMetrics(
        massMean: massMean,
        massStd: 0.2,
        massMin: 0.8,
        massMax: 2.4,
        occupancyMean: 0.4,
        varianceMean: 0.06,
        energyMean: 0.15,
        speedMean: centerVelocity,
        pathLength: pathLength,
        displacement: displacement,
        sampleCount: 120,
        speedCount: 119,
        gyration: 8.5,
        centerVelocity: centerVelocity,
        velocityX: 0.1,
        velocityY: 0.2,
        headingRad: 0.5,
        isStable: true,
        complexityMean: 0.61,
        activityEacMean: 0.33,
        activityEanMean: 0.44,
        activityDiversityMean: 0.55,
        activitySpeciesMean: 0.66,
        survivalTracked: true,
        survivalSteps: 100,
        foodInitialMass: 4.0,
        foodFinalMass: 1.5,
        foodConsumed: 2.5,
        hu1: 0.01,
        flusser1: 0.02,
        momentMass: massMean,
        momentVolume: 12,
        momentDensity: 0.7,
        momentAnisotropy: 0.12,
        componentCount: 2,
        largestComponentFraction: 0.8
    )
}

private func makeEntry(
    id: String,
    score: Float,
    metrics: SimulationMetrics,
    taxonomy: SpecimenTaxonomyRecord? = nil,
    traitLabels: [String] = [],
    runtimeCapabilities: [String] = []
) -> StudioCompareEntry {
    let params = ResolvedParams(
        r: [1.0],
        b: [[1.0]],
        w: [[0.2]],
        a: [[1.0]],
        m: [0.2],
        s: [0.05],
        h: [1.0],
        R: 12,
        seed: 42
    )
    let creature = LeniaCreature(
        seed: 42,
        score: score,
        params: params,
        sourceNode: "test-node"
    )
    return StudioCompareEntry(
        id: id,
        creature: creature,
        name: id,
        subtitle: "test-node",
        metrics: metrics,
        taxonomy: taxonomy,
        traitLabels: traitLabels,
        runtimeFamily: "flow-lenia",
        sourceMode: "imgep",
        sourceAlgorithm: "novelty-search",
        runtimeCapabilities: runtimeCapabilities
    )
}
