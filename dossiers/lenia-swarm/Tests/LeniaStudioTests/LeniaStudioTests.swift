import XCTest
import Metal
import LeniaCore
import LeniaVisuals
import MLX
@testable import LeniaStudio

final class LeniaStudioTests: XCTestCase {
    override func setUp() {
        super.setUp()
        StudioMLXTestSupport.ensureMetalLibraryAvailable()
    }

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

    func testLeniaLabFallbackWorldUsesExplicitWarmInitialState() throws {
        let draft = try makeLabWorldDraft(for: orbiumStarterEntry(), gridSize: 128)
        let runtimeConfig = draft.runtimeConfigValue
        let statePatch = try XCTUnwrap(runtimeConfig.statePatch)

        XCTAssertTrue(runtimeConfig.patches.isEmpty)
        XCTAssertEqual(runtimeConfig.aUniform.low, 0)
        XCTAssertEqual(runtimeConfig.aUniform.high, 0)
        XCTAssertEqual(statePatch.center, [64, 64])
        XCTAssertEqual(statePatch.channels, 1)
        XCTAssertEqual(statePatch.valueCount, statePatch.width * statePatch.height)
        XCTAssertGreaterThan(statePatch.decodedValues().reduce(0, +), 0)
    }

    func testLeniaLabFallbackWorldAdvancesWithFiniteStructuredMatter() throws {
        let draft = try makeLabWorldDraft(for: orbiumStarterEntry(), gridSize: 128)
        let simulator = FlowLeniaInteractiveSimulator(runtimeConfig: draft.runtimeConfigValue)
        var state = simulator.makeInitialState()
        let initial = labMatterSummary(simulator: simulator, state: state)

        for _ in 0..<80 {
            state = simulator.step(state)
        }

        let final = labMatterSummary(simulator: simulator, state: state)
        XCTAssertEqual(state.step, 80)
        XCTAssertEqual(final.nonFiniteCount, 0)
        XCTAssertGreaterThan(initial.total, 1.0)
        XCTAssertGreaterThan(final.total, initial.total * 0.75)
        XCTAssertGreaterThan(final.occupied, 64)
        XCTAssertGreaterThan(final.peak, final.mean * 4.0)
    }

    func testLeniaLabFallbackWorldUsesSavedExplicitInitialState() throws {
        let values: [Float] = [0.1, 0.2, 0.3, 0.4]
        let initialCondition = InitConfig(
            seed: 7,
            patches: [],
            a_uniform: UniformRange(low: 0, high: 0),
            p_uniform: nil,
            state_patch: InitStatePatchConfig(
                center: [11, 13],
                width: 2,
                height: 2,
                channels: 1,
                values: values
            )
        )
        let saved = SavedCreature(
            id: UUID(uuidString: "11111111-2222-3333-4444-555555555555")!,
            name: "Saved Patch",
            ownerId: "test-node",
            genotype: KernelParams(
                r: [1.0],
                b: [[1.0]],
                w: [[0.2]],
                a: [[1.0]],
                m: [0.2],
                s: [0.05],
                h: [1.0],
                R: 12
            ),
            initialCondition: initialCondition,
            metrics: makeMetrics()
        )
        let draft = try makeLabWorldDraft(for: .saved(saved), gridSize: 64)
        let runtimeConfig = draft.runtimeConfigValue
        let statePatch = try XCTUnwrap(runtimeConfig.statePatch)

        XCTAssertTrue(runtimeConfig.patches.isEmpty)
        XCTAssertEqual(runtimeConfig.aUniform.low, 0)
        XCTAssertEqual(runtimeConfig.aUniform.high, 0)
        XCTAssertEqual(statePatch.center, [32, 32])
        XCTAssertEqual(statePatch.decodedValues(), values)
    }

    func testLeniaLabFallbackWorldPreservesMultiChannelSavedInitialState() throws {
        let values: [Float] = [
            0.1, 0.2,
            0.3, 0.4,
            0.5, 0.6,
            0.7, 0.8,
        ]
        let initialCondition = InitConfig(
            seed: 11,
            patches: [],
            a_uniform: UniformRange(low: 0, high: 0),
            p_uniform: nil,
            state_patch: InitStatePatchConfig(
                center: [9, 9],
                width: 2,
                height: 2,
                channels: 2,
                values: values
            )
        )
        let saved = SavedCreature(
            id: UUID(uuidString: "22222222-3333-4444-5555-666666666666")!,
            name: "Two Channel Patch",
            ownerId: "test-node",
            genotype: KernelParams(
                r: [1.0, 0.8],
                b: [[1.0], [1.0]],
                w: [[0.2], [0.15]],
                a: [[1.0], [1.0]],
                m: [0.2, 0.18],
                s: [0.05, 0.04],
                h: [1.0, 0.9],
                R: 12
            ),
            initialCondition: initialCondition,
            metrics: makeMetrics()
        )

        let draft = try makeLabWorldDraft(for: .saved(saved), gridSize: 64)
        let runtimeConfig = draft.runtimeConfigValue
        let statePatch = try XCTUnwrap(runtimeConfig.statePatch)

        XCTAssertEqual(runtimeConfig.channels, 2)
        XCTAssertEqual(runtimeConfig.nbK, 2)
        XCTAssertEqual(runtimeConfig.c0, [0, 1])
        XCTAssertEqual(runtimeConfig.c1, [[0], [1]])
        XCTAssertTrue(runtimeConfig.patches.isEmpty)
        XCTAssertEqual(runtimeConfig.aUniform.low, 0)
        XCTAssertEqual(runtimeConfig.aUniform.high, 0)
        XCTAssertEqual(statePatch.center, [32, 32])
        XCTAssertEqual(statePatch.channels, 2)
        XCTAssertEqual(statePatch.decodedValues(), values)
    }

    func testStudioRuntimeConfigOverlaysSelectedSavedCreatureOnReplayBase() throws {
        let baseRuntimeConfig = LeniaRuntimeConfig(
            backend: .metalFull,
            sx: 64,
            sy: 64,
            channels: 2,
            nbK: 2,
            profile: .paper,
            c0: [0, 1],
            c1: [[0], [1]],
            dt: 0.2,
            dd: 5,
            sigma: 0.65,
            n: 2,
            thetaA: 2.0,
            border: "torus",
            implementation: ImplementationSettings(
                mode: "flowlenia_2022_paper_equations",
                border: "torus",
                gradientBoundary: "periodic",
                alphaMode: "mass",
                kernelProfile: "flowlenia_2022_paper_equations",
                flowClip: "none"
            ),
            params: ResolvedParams(
                r: [0.25, 0.35],
                b: [[1.0], [1.0]],
                w: [[0.1], [0.1]],
                a: [[1.0], [1.0]],
                m: [0.1, 0.1],
                s: [0.02, 0.02],
                h: [0.2, 0.2],
                R: 8,
                seed: 1
            ),
            initSeed: 1,
            patches: [PatchConfig(center: [32, 32], size: 16)],
            aUniform: UniformRange(low: 0.2, high: 0.3),
            pUniform: nil,
            steps: 400,
            parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
            chemotaxis: nil,
            food: nil,
            walls: nil,
            interventions: []
        )
        let values: [Float] = [0.9, 0.1, 0.8, 0.2, 0.7, 0.3, 0.6, 0.4]
        let saved = SavedCreature(
            id: UUID(uuidString: "33333333-4444-5555-6666-777777777777")!,
            name: "Replay Creature",
            ownerId: "test-node",
            genotype: KernelParams(
                r: [0.75, 0.85],
                b: [[1.0], [1.0]],
                w: [[0.24], [0.18]],
                a: [[1.0], [1.0]],
                m: [0.22, 0.19],
                s: [0.055, 0.045],
                h: [1.1, 0.95],
                R: 13
            ),
            initialCondition: InitConfig(
                seed: 77,
                patches: [],
                a_uniform: UniformRange(low: 0, high: 0),
                p_uniform: nil,
                state_patch: InitStatePatchConfig(
                    center: [20, 22],
                    width: 2,
                    height: 2,
                    channels: 2,
                    values: values
                )
            ),
            metrics: makeMetrics()
        )

        let runtimeConfig = try studioRuntimeConfig(
            base: baseRuntimeConfig,
            creature: saved.toLeniaCreature(),
            savedCreature: saved
        )
        let statePatch = try XCTUnwrap(runtimeConfig.statePatch)

        XCTAssertEqual(runtimeConfig.channels, 2)
        XCTAssertEqual(runtimeConfig.nbK, 2)
        XCTAssertEqual(runtimeConfig.params.r, [0.75, 0.85])
        XCTAssertEqual(runtimeConfig.params.m, [0.22, 0.19])
        XCTAssertEqual(runtimeConfig.params.R, 13)
        XCTAssertEqual(runtimeConfig.initSeed, 77)
        XCTAssertTrue(runtimeConfig.patches.isEmpty)
        XCTAssertEqual(runtimeConfig.aUniform.low, 0)
        XCTAssertEqual(runtimeConfig.aUniform.high, 0)
        XCTAssertEqual(statePatch.center, [20, 22])
        XCTAssertEqual(statePatch.decodedValues(), values)
    }

    func testTrack1TaxonomyCatalogParsesRuntimeProvenance() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("track1-taxonomy-\(UUID().uuidString)")
        let configs = root.appendingPathComponent("track1_section2_orbidae_species_panel")
        try FileManager.default.createDirectory(at: configs, withIntermediateDirectories: true)
        defer {
            try? FileManager.default.removeItem(at: root)
        }

        let configURL = configs.appendingPathComponent("Orbidae-OG2-qd24-additive-native-parity-mlx.json")
        let config = """
        {
          "backend": "mlx",
          "channels": 1,
          "connectivity": [[1]],
          "grid": {"sx": 192, "sy": 192},
          "implementation": {
            "mode": "qd24_additive_v1",
            "kernel_profile": "qd24_bump4_v1"
          },
          "params": {"r": [1.0]},
          "provenance": {
            "family": "Orbidae",
            "pattern_id": "OG2",
            "species": "Gyrorbium"
          },
          "run": {"steps": 1600}
        }
        """
        try Data(config.utf8).write(to: configURL)

        let catalog = try loadTrack1TaxonomyCatalog(rootPath: root.path)
        let parsed = try XCTUnwrap(catalog.configs.first)

        XCTAssertEqual(catalog.families.map(\.name), ["Orbidae"])
        XCTAssertEqual(catalog.genusCount, 1)
        XCTAssertEqual(catalog.speciesCount, 1)
        XCTAssertEqual(catalog.labLoadableCount, 0)
        XCTAssertEqual(parsed.family, "Orbidae")
        XCTAssertEqual(parsed.genus, "Gyrorbium")
        XCTAssertEqual(parsed.displayName, "Gyrorbium")
        XCTAssertEqual(parsed.patternID, "OG2")
        XCTAssertFalse(parsed.isLabLoadable)
        XCTAssertEqual(parsed.backend, "mlx")
        XCTAssertEqual(parsed.implementationMode, "qd24_additive_v1")
        XCTAssertEqual(parsed.kernelProfile, "qd24_bump4_v1")
        XCTAssertEqual(parsed.gridSize, 192)
        XCTAssertEqual(parsed.kernelCount, 1)
        XCTAssertEqual(parsed.runSteps, 1600)
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

    func testLiveProjectionFrameReadsOnlyTheSelectedChannel() {
        var readChannels: [Int] = []
        let readChannel: (Int) -> [Float] = { channel in
            readChannels.append(channel)
            return channel == 2 ? [1, 0.5, 0.25, 0] : [0, 0.25, 0.5, 1]
        }

        let initialFrame = liveProjectionFrame(
            matterData: [0, 0.25, 0.5, 1],
            selectedProjection: .channel(2),
            step: 7,
            width: 2,
            height: 2,
            channelCount: 4,
            channelData: readChannel
        )
        let switchedFrame = liveProjectionFrame(
            matterData: [0, 0.25, 0.5, 1],
            selectedProjection: .channel(0),
            step: 8,
            width: 2,
            height: 2,
            channelCount: 4,
            channelData: readChannel
        )

        XCTAssertEqual(readChannels, [2, 0])
        XCTAssertEqual(initialFrame.bytes, Data([255, 127, 63, 0]))
        XCTAssertEqual(switchedFrame.bytes, Data([0, 63, 127, 255]))
        XCTAssertEqual(switchedFrame.step, 8)
    }

    func testLiveProjectionFrameNeedsNoChannelReadForMatterOrInvalidSelection() {
        var readChannels: [Int] = []
        let readChannel: (Int) -> [Float] = { channel in
            readChannels.append(channel)
            return [1]
        }

        let matterFrame = liveProjectionFrame(
            matterData: [0.5],
            selectedProjection: .matter,
            step: 1,
            width: 1,
            height: 1,
            channelCount: 3,
            channelData: readChannel
        )
        let fallbackFrame = liveProjectionFrame(
            matterData: [0.5],
            selectedProjection: .channel(3),
            step: 2,
            width: 1,
            height: 1,
            channelCount: 3,
            channelData: readChannel
        )

        XCTAssertEqual(matterFrame.bytes, Data([127]))
        XCTAssertEqual(fallbackFrame.bytes, Data([127]))
        XCTAssertTrue(readChannels.isEmpty)
        XCTAssertEqual(
            LabFieldProjection.options(channelCount: 3),
            [.matter, .channel(0), .channel(1), .channel(2)]
        )
    }

    func testTTFrameSequenceLoadsRawFrames() async throws {
        let fixture = try makeTTFrameSequenceFixture(frameBytes: [0, 13, 128, 255])
        defer { try? FileManager.default.removeItem(at: fixture.root) }

        let sequence = try TTFrameSequence.load(manifestURL: fixture.manifestURL)
        let sample = sequence[0]
        let runtimeSnapshot = await TTFrameSequenceRuntime(sequence: sequence).snapshot(
            refreshMetrics: true,
            projection: .matter
        )

        XCTAssertEqual(sequence.frameCount, 1)
        XCTAssertEqual(sequence.width, 2)
        XCTAssertEqual(sequence.height, 2)
        XCTAssertEqual(sample.step, 0)
        XCTAssertEqual(sample.bytes, Data([0, 13, 128, 255]))
        XCTAssertEqual(sample.metrics.massMean, Float(396) / Float(4 * 255), accuracy: 1e-6)
        XCTAssertEqual(sample.metrics.occupancy, 0.75, accuracy: 1e-6)
        XCTAssertEqual(sample.metrics.massPeak, 1, accuracy: 1e-6)
        XCTAssertEqual(runtimeSnapshot.metrics.massMean, sample.metrics.massMean, accuracy: 1e-6)
        XCTAssertEqual(runtimeSnapshot.metrics.occupancy, sample.metrics.occupancy, accuracy: 1e-6)
    }

    func testCanonicalLabRuntimeAdvancesOnlyWhileRunning() async throws {
        let draft = try makeLabWorldDraft(for: orbiumStarterEntry(), gridSize: 32)
        let runtime = CanonicalLabRuntime(
            runtimeConfig: draft.runtimeConfig(overridingBackend: .mlx)
        )

        let initial = await runtime.snapshot(refreshMetrics: false, projection: .matter)
        let stillPaused = await runtime.snapshot(refreshMetrics: false, projection: .matter)
        XCTAssertEqual(stillPaused.step, initial.step)

        await runtime.start()
        let firstRunning = await runtime.snapshot(refreshMetrics: false, projection: .matter)
        let secondRunning = await runtime.snapshot(refreshMetrics: false, projection: .matter)
        XCTAssertEqual(firstRunning.step, initial.step + 1)
        XCTAssertEqual(secondRunning.step, firstRunning.step + 1)

        await runtime.pause()
        let paused = await runtime.snapshot(refreshMetrics: false, projection: .matter)
        XCTAssertEqual(paused.step, secondRunning.step)

        await runtime.resume()
        let resumed = await runtime.snapshot(refreshMetrics: false, projection: .matter)
        XCTAssertEqual(resumed.step, paused.step + 1)
    }

    func testTTFrameSequenceRejectsWrongSizedFrameAtLoad() throws {
        let fixture = try makeTTFrameSequenceFixture(frameBytes: [0, 64, 128])
        defer { try? FileManager.default.removeItem(at: fixture.root) }

        XCTAssertThrowsError(try TTFrameSequence.load(manifestURL: fixture.manifestURL)) { error in
            guard case TTFrameSequenceError.invalidFrameSize = error else {
                return XCTFail("Expected invalidFrameSize, got \(error)")
            }
        }
    }
}

private func makeTTFrameSequenceFixture(frameBytes: [UInt8]) throws -> (root: URL, manifestURL: URL) {
    let root = FileManager.default.temporaryDirectory
        .appendingPathComponent("tt-frame-sequence-\(UUID().uuidString)")
    let frames = root.appendingPathComponent("frames")
    try FileManager.default.createDirectory(at: frames, withIntermediateDirectories: true)
    try Data(frameBytes).write(to: frames.appendingPathComponent("frame_000000.r8"))

    let manifest: [String: Any] = [
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
        "metadata": [
            "dt": 0.1,
            "dd": 5,
            "sigma": 0.65,
            "n": 2,
            "theta_a": 1.0,
            "border": "torus",
            "kernel_profile": "gaussian",
            "kernel_count": 3,
            "radius": 12.0,
        ],
        "frames": [
            ["step": 0, "path": "frames/frame_000000.r8"],
        ],
    ]
    let manifestURL = root.appendingPathComponent("manifest.json")
    try JSONSerialization.data(withJSONObject: manifest, options: [.sortedKeys])
        .write(to: manifestURL, options: .atomic)
    return (root, manifestURL)
}

private enum StudioMLXTestSupport {
    static func ensureMetalLibraryAvailable(
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        do {
            try LeniaMetalLibrarySupport.ensureAvailable(
                executableURL: Bundle(for: StudioMLXTestSupportMarker.self).executableURL
            )
        } catch {
            XCTFail("Failed to prepare MLX metallib: \(error)", file: file, line: line)
        }
    }
}

private final class StudioMLXTestSupportMarker {}

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

private struct LabMatterSummary {
    let total: Float
    let mean: Float
    let peak: Float
    let occupied: Int
    let nonFiniteCount: Int
}

private func labMatterSummary(
    simulator: FlowLeniaInteractiveSimulator,
    state: FlowLeniaInteractiveState
) -> LabMatterSummary {
    let matter = simulator.matterMap(for: state).contiguous()
    eval(matter)
    let values = matter.asArray(Float.self)
    let finite = values.filter(\.isFinite)
    let total = finite.reduce(0, +)
    return LabMatterSummary(
        total: total,
        mean: total / Float(max(1, values.count)),
        peak: finite.max() ?? 0,
        occupied: finite.filter { $0 > 0.01 }.count,
        nonFiniteCount: values.count - finite.count
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
