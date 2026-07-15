import Foundation
import XCTest
@testable import LeniaCore
import Logging
import MLX
import MLXFFT

final class LeniaCoreTests: XCTestCase {
    override func setUp() {
        super.setUp()
        MLXTestSupport.ensureMetalLibraryAvailable()
    }

    private func overwriteJSONObject(
        at url: URL,
        mutate: (inout [String: Any]) throws -> Void
    ) throws {
        var json = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any]
        )
        try mutate(&json)
        let data = try JSONSerialization.data(withJSONObject: json, options: [.prettyPrinted, .sortedKeys])
        try data.write(to: url)
    }

    private func packageRootURL() -> URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }

    func testLeniaRunBundleLoadsEcologySnakeCaseMetadata() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-run-bundle-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let bundleDir = root.appendingPathComponent("run", isDirectory: true)
        try fm.createDirectory(
            at: bundleDir.appendingPathComponent("trajectory-frames/frames", isDirectory: true),
            withIntermediateDirectories: true
        )
        try "{}".write(to: bundleDir.appendingPathComponent("base.json"), atomically: true, encoding: .utf8)
        try "{}".write(to: bundleDir.appendingPathComponent("payload.json"), atomically: true, encoding: .utf8)
        try """
        {
          "bundle_kind": "flowlenia_ecology2025_arena_replay_bundle_v1",
          "run_id": "run-001",
          "exported_at": 0,
          "run_summary": {}
        }
        """.write(to: bundleDir.appendingPathComponent("meta.json"), atomically: true, encoding: .utf8)

        let bundle = try XCTUnwrap(loadLeniaRunBundle(from: bundleDir))
        XCTAssertEqual(bundle.bundleKind, .flowLeniaEcology2025ArenaReplayBundleV1)
        XCTAssertEqual(try bundle.requireBaseConfig().lastPathComponent, "base.json")
        XCTAssertEqual(try bundle.requirePayload().lastPathComponent, "payload.json")
        XCTAssertEqual(bundle.trajectoryFramesURL?.lastPathComponent, "trajectory-frames")
    }

    func testLeniaRunBundleIndexLoadsCamelAndSnakeCaseRecords() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("lenia-run-bundle-index-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }
        try fm.createDirectory(at: root, withIntermediateDirectories: true)
        let indexURL = root.appendingPathComponent("index.jsonl")
        let strictDir = root.appendingPathComponent("strict", isDirectory: true)
        let ecologyDir = root.appendingPathComponent("ecology", isDirectory: true)
        let contents = """
        {"bundleKind":"strict_replay_bundle_v1","exportDir":"\(strictDir.path)","baseConfigPath":"\(strictDir.appendingPathComponent("base.json").path)","searchConfigPath":"\(strictDir.appendingPathComponent("search.json").path)"}
        {"bundle_kind":"flowlenia_ecology2025_arena_replay_bundle_v1","bundle_dir":"\(ecologyDir.path)","base_config_path":"\(ecologyDir.appendingPathComponent("base.json").path)","payload_path":"\(ecologyDir.appendingPathComponent("payload.json").path)","trajectory_frames_path":"\(ecologyDir.appendingPathComponent("trajectory-frames").path)"}
        """
        try contents.write(to: indexURL, atomically: true, encoding: .utf8)

        let bundles = try loadLeniaRunBundles(from: indexURL)
        XCTAssertEqual(bundles.map(\.bundleKind), [.strictReplayBundleV1, .flowLeniaEcology2025ArenaReplayBundleV1])
        XCTAssertEqual(bundles[0].searchConfigURL?.lastPathComponent, "search.json")
        XCTAssertEqual(bundles[1].payloadURL?.lastPathComponent, "payload.json")
        XCTAssertEqual(bundles[1].trajectoryFramesURL?.lastPathComponent, "trajectory-frames")
    }

    private func testResearchSeedCreature(
        name: String = "seed-creature",
        score: Float? = nil
    ) throws -> (LeniaBaseConfig, ParsedSearchConfig, SavedCreature) {
        let packageRoot = packageRootURL()
        let baseURL = packageRoot.appendingPathComponent("configs/base/paper_base_1c_128.json")
        let searchURL = packageRoot.appendingPathComponent("configs/search/search_discovery_fast.json")
        let decoder = JSONDecoder()
        let baseConfig = try decoder.decode(LeniaBaseConfig.self, from: Data(contentsOf: baseURL))
        let searchConfig = try decoder.decode(ParsedSearchConfig.self, from: Data(contentsOf: searchURL))
        let runtime = try loadRuntimeConfig(from: Data(contentsOf: baseURL))
        let creature = SavedCreature(
            name: name,
            ownerId: "LeniaCoreTests",
            genotype: runtime.params.toKernelParams(),
            initialCondition: InitConfig(
                seed: runtime.initSeed,
                patches: runtime.patches,
                a_uniform: runtime.aUniform,
                p_uniform: runtime.pUniform
            ),
            metrics: SimulationMetrics(
                massMean: 1.0,
                massStd: 0.1,
                massMin: 0.9,
                massMax: 1.1,
                occupancyMean: 0.08,
                varianceMean: 0.02,
                energyMean: 0.03,
                speedMean: 0.01,
                pathLength: 1.0,
                displacement: 1.0,
                sampleCount: 4,
                speedCount: 4,
                gyration: 10.0,
                centerVelocity: 0.01,
                velocityX: 0.01,
                velocityY: 0.0,
                headingRad: 0.0,
                isStable: true
            ),
            score: score
        )
        return (baseConfig, searchConfig, creature)
    }

    func testSavedCreatureSanitizesNonFiniteScoreForPersistence() throws {
        let (_, _, creature) = try testResearchSeedCreature(name: "nonfinite-seed", score: -.infinity)
        XCTAssertNil(creature.score)
        XCTAssertNoThrow(try JSONEncoder().encode(creature))

        let runDirectory = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let entry = ResearchLibraryEntry(
            creature: creature,
            campaignId: nil,
            runId: "test-run",
            recordedAt: Date(),
            configHash: "config-hash"
        )
        XCTAssertNoThrow(try ResearchLibraryWriter.write(entries: [entry], runDirectory: runDirectory))
    }

    func testSimulationResultDataSanitizesNonFiniteScoreForEncoding() throws {
        let (_, _, creature) = try testResearchSeedCreature(name: "nonfinite-result")
        let result = SimulationResultData(
            seed: 1,
            initSeed: 1,
            mixSeed: nil,
            backend: "mlx",
            implementation: ImplementationSettings(
                mode: "baseline",
                border: "torus",
                gradientBoundary: "torus",
                alphaMode: "alpha",
                kernelProfile: "gaussian",
                flowClip: "none"
            ),
            score: -.infinity,
            scoreWeights: ["fitness": 1.0],
            filtersPassed: false,
            filters: [:],
            metrics: creature.metrics,
            activity: nil,
            params: creature.genotype,
            sweep: [:]
        )
        XCTAssertNil(result.score)
        XCTAssertNoThrow(try JSONEncoder().encode(result))
    }

    func testBuildSeedCreatureStampProducesNonEmptyStamp() throws {
        let (_, _, creature) = try testResearchSeedCreature(name: "seed-stamp")
        let genotype = creature.genotype
        let params = ResolvedParams(
            r: genotype.r,
            b: genotype.b,
            w: genotype.w,
            a: genotype.a,
            m: genotype.m,
            s: genotype.s,
            h: genotype.h,
            R: genotype.R,
            seed: creature.initialCondition.seed
        )
        let stamp = buildSeedCreatureStamp(
            id: creature.id,
            name: creature.name,
            params: params,
            seed: creature.initialCondition.seed,
            gridSize: 64
        )

        XCTAssertGreaterThan(stamp.width, 0)
        XCTAssertGreaterThan(stamp.height, 0)
        XCTAssertEqual(stamp.mass.count, stamp.width * stamp.height)
        XCTAssertEqual(stamp.params.count, stamp.width * stamp.height * stamp.parameterCount)
        XCTAssertGreaterThan(stamp.mass.reduce(0, +), 0)
    }

    func testSummarizeActivitySingleSnapshot() {
        let config = ActivityConfig(
            enabled: true,
            interval: 1,
            threshold: 0.1,
            maxComponents: nil,
            matchThreshold: 0.01,
            paramWeight: 1.0,
            positionWeight: 1.0
        )
        let snapshots = [
            ActivitySnapshot(
                step: 5,
                components: [
                    ComponentSnapshot(
                        id: 0,
                        mass: 1.0,
                        centroid: [0.0, 0.0],
                        paramMean: [0.0, 0.0]
                    ),
                    ComponentSnapshot(
                        id: 1,
                        mass: 1.0,
                        centroid: [1.0, 1.0],
                        paramMean: [1.0, 1.0]
                    )
                ],
                width: 2,
                height: 2,
                isTorus: false
            )
        ]

        let summary = summarizeActivity(snapshots: snapshots, config: config)

        XCTAssertEqual(summary.steps, [5])
        XCTAssertEqual(summary.speciesCount, [2])
        XCTAssertEqual(summary.eap.count, 1)
        XCTAssertEqual(summary.eac.count, 1)
        XCTAssertEqual(summary.ean.count, 1)
        XCTAssertEqual(summary.eap[0], 2.0, accuracy: 1e-6)
        XCTAssertEqual(summary.eac[0], 2.0, accuracy: 1e-6)
        XCTAssertEqual(summary.ean[0], 0.0, accuracy: 1e-6)
    }

    func testComputeActivitySnapshotsKeepsBatchesIsolated() {
        let config = ActivityConfig(
            enabled: true,
            interval: 1,
            threshold: 0.1,
            maxComponents: nil,
            matchThreshold: 0.01,
            paramWeight: 1.0,
            positionWeight: 1.0
        )
        let massMap = MLXArray([Float]([
            1.0, 0.0,
            0.0, 0.0,
            0.0, 0.0,
            0.0, 2.0
        ])).reshaped([2, 2, 2])
        let paramMap = MLXArray([Float]([
            0.25, 0.0,
            0.0, 0.0,
            0.0, 0.0,
            0.0, 0.75
        ])).reshaped([2, 2, 2, 1])

        let snapshots = computeActivitySnapshots(
            massMap: massMap,
            paramMap: paramMap,
            step: 3,
            config: config,
            border: "wall"
        )

        XCTAssertEqual(snapshots.count, 2)
        XCTAssertEqual(snapshots[0].components.count, 1)
        XCTAssertEqual(snapshots[1].components.count, 1)
        XCTAssertEqual(snapshots[0].components[0].mass, 1.0, accuracy: 1e-6)
        XCTAssertEqual(snapshots[1].components[0].mass, 2.0, accuracy: 1e-6)
        XCTAssertEqual(snapshots[0].components[0].paramMean.count, 1)
        XCTAssertEqual(snapshots[1].components[0].paramMean.count, 1)
        XCTAssertEqual(snapshots[0].components[0].paramMean[0], 0.25, accuracy: 1e-6)
        XCTAssertEqual(snapshots[1].components[0].paramMean[0], 0.75, accuracy: 1e-6)
    }

    func testMorphospaceFinalSampleSummaryCarriesQuantizedFingerprint() {
        let summary = morphospaceFinalSampleSummary(
            materialized: MassBatchCPU(
                flat: [
                    0, 0, 0, 0,
                    0, 1, 1, 0,
                    0, 1, 1, 0,
                    0, 0, 0, 0,
                ],
                batch: 1,
                height: 4,
                width: 4,
                sampleSize: 16
            ),
            sampleIndex: 0,
            occupancyThreshold: 0.1,
            useTorus: false
        )

        XCTAssertEqual(summary.fingerprintResolution, 32)
        XCTAssertEqual(summary.fingerprintU8.count, 32 * 32)
        XCTAssertEqual(summary.angularSymmetry.binCount, 32)
        XCTAssertEqual(summary.angularSymmetry.harmonics.count, 8)
        XCTAssertEqual(summary.fingerprintHash12.count, 12)
        XCTAssertGreaterThan(summary.finalMass, 0)
        XCTAssertGreaterThan(summary.finalOccupancy, 0)
    }

    func testMorphospaceFinalSampleSummaryDetectsFourFoldAngularSymmetry() {
        let summary = morphospaceFinalSampleSummary(
            materialized: MassBatchCPU(
                flat: [
                    0, 0, 1, 0, 0,
                    0, 0, 1, 0, 0,
                    1, 1, 1, 1, 1,
                    0, 0, 1, 0, 0,
                    0, 0, 1, 0, 0,
                ],
                batch: 1,
                height: 5,
                width: 5,
                sampleSize: 25
            ),
            sampleIndex: 0,
            occupancyThreshold: 0.1,
            useTorus: false
        )

        XCTAssertEqual(summary.angularSymmetry.dominantOrder, 4)
        XCTAssertGreaterThan(summary.angularSymmetry.dominantAmplitude ?? 0, 0.2)
    }

    func testIMGEPGoalVectorReadsDescriptorBundleFeatures() {
        let descriptorBundle = MorphospaceDescriptorBundle(
            symmetryPolicy: "translation_kernel_permutation_v1",
            genotype: MorphospaceGenotypeDescriptor(
                kernelCount: 1,
                vectorLength: 4,
                vector: [0.1, 0.2, 0.3, 0.4],
                hash12: "abcd1234ef56"
            ),
            terminal: MorphospaceTerminalDescriptor(
                massChannel: 0,
                borderMode: "torus",
                symmetryPolicy: "translation_kernel_permutation_v1",
                fingerprintResolution: 32,
                fingerprintU8: Data(repeating: 3, count: 32 * 32),
                angularSymmetry: MorphospaceAngularSymmetryDescriptor(
                    binCount: 32,
                    maxOrder: 8,
                    harmonics: [0.05, 0.15, 0.75, 0.1, 0.0, 0.0, 0.0, 0.0],
                    dominantOrder: 3,
                    dominantAmplitude: 0.75,
                    normalizedEntropy: 0.28
                ),
                fingerprintHash12: "1234abcd5678",
                finalMass: 1.2,
                finalOccupancy: 0.18,
                finalGyration: 4.5,
                momentMass: 1.2,
                momentVolume: 3.0,
                momentDensity: 0.4,
                momentAnisotropy: 0.35,
                componentCount: 2.0,
                largestComponentFraction: 0.8,
                largestComponentAnisotropy: 0.42,
                hu1: 0.1,
                hu2: 0.2,
                hu3: 0.3,
                hu4: 0.4,
                hu5: 0.5,
                hu6: 0.6,
                hu7: 0.7,
                flusser1: 0.11,
                flusser2: 0.12,
                flusser3: 0.13,
                flusser4: 0.14,
                windowMassStd: 0.02,
                windowOccupancyStd: 0.03,
                windowGyrationStd: 0.04,
                isStable: true
            ),
            trajectory: MorphospaceTrajectoryDescriptor(
                recordInterval: 10,
                warmupSteps: 100,
                sampleCount: 9,
                pathLength: 8.0,
                displacement: 5.0,
                pathTortuosity: 1.6,
                movementEfficiency: 0.625,
                speedMean: 0.45,
                centerVelocity: 0.5,
                velocityX: 0.1,
                velocityY: -0.1,
                headingRad: 1.2,
                headingCircularVariance: 0.18,
                accumulatedTurnAbs: 2.2,
                survivalSteps: 1000,
                activityEacMean: 0.1,
                activityEanMean: 0.2,
                activityDiversityMean: 0.3,
                activitySpeciesMean: 1.0,
                activitySpeciesMax: 2,
                activitySpeciesStd: 0.05,
                activityDiversityStd: 0.04,
                activityEacMax: 0.5,
                activityEanMax: 0.6,
                componentSeriesMean: 1.5,
                componentSeriesStd: 0.25,
                componentSeriesMax: 3
            )
        )

        let result = SimulationResultData(
            seed: 7,
            initSeed: 13,
            mixSeed: nil,
            backend: "mlx",
            implementation: ImplementationSettings(
                mode: "flowlenia_2022_paper_equations",
                border: "torus",
                gradientBoundary: "wrapped",
                alphaMode: "identity",
                kernelProfile: "poly_quad4",
                flowClip: "none"
            ),
            initialConditionFamily: "centered_patch_v1",
            descriptorBundle: descriptorBundle,
            score: 1.0,
            scoreWeights: [:],
            filtersPassed: true,
            filters: [:],
            metrics: SimulationMetrics(
                massMean: 1.1,
                massStd: 0.1,
                massMin: 1.0,
                massMax: 1.2,
                occupancyMean: 0.15,
                varianceMean: 0.02,
                energyMean: 0.3,
                speedMean: 0.4,
                pathLength: 8.0,
                displacement: 5.0,
                sampleCount: 9,
                speedCount: 9,
                gyration: 4.0,
                centerVelocity: 0.5,
                isStable: true
            ),
            activity: nil,
            params: KernelParams(
                r: [0.5],
                b: [[0.2, 0.3, 0.4]],
                w: [[0.1, 0.1, 0.1]],
                a: [[0.0, 0.0, 0.0]],
                m: [0.2],
                s: [0.1],
                h: [0.5],
                R: 10
            ),
            sweep: [:]
        )

        let embedding = goalVector(
            from: result,
            features: [
                "mass_mean",
                "symmetry_dominant_order",
                "symmetry_dominant_amplitude",
                "symmetry_entropy",
                "symmetry_harmonic_3",
                "trajectory_path_tortuosity",
                "trajectory_movement_efficiency",
                "terminal_component_count",
                "terminal_largest_component_fraction",
            ]
        )

        XCTAssertEqual(embedding[0], 1.1, accuracy: 1e-6)
        XCTAssertEqual(embedding[1], 3.0, accuracy: 1e-6)
        XCTAssertEqual(embedding[2], 0.75, accuracy: 1e-6)
        XCTAssertEqual(embedding[3], 0.28, accuracy: 1e-6)
        XCTAssertEqual(embedding[4], 0.75, accuracy: 1e-6)
        XCTAssertEqual(embedding[5], 1.6, accuracy: 1e-6)
        XCTAssertEqual(embedding[6], 0.625, accuracy: 1e-6)
        XCTAssertEqual(embedding[7], 2.0, accuracy: 1e-6)
        XCTAssertEqual(embedding[8], 0.8, accuracy: 1e-6)
    }

    func testTranslationRatioScoringAndFilters() {
        let metrics = SimulationMetrics(
            massMean: 1.0,
            massStd: 0.1,
            massMin: 0.9,
            massMax: 1.1,
            occupancyMean: 0.08,
            varianceMean: 0.02,
            energyMean: 0.03,
            speedMean: 0.01,
            pathLength: 10.0,
            displacement: 9.8,
            sampleCount: 16,
            speedCount: 16,
            gyration: 120.0,
            centerVelocity: 0.012,
            velocityX: 0.011,
            velocityY: 0.002,
            headingRad: 0.1798535,
            isStable: true
        )

        XCTAssertEqual(
            scoreMetrics(metrics, weights: ["translation_ratio": 2.0]),
            1.96,
            accuracy: 1e-6
        )
        XCTAssertTrue(passesFilters(metrics, filters: ["translation_ratio_min": 0.97]))
        XCTAssertFalse(passesFilters(metrics, filters: ["translation_ratio_min": 0.99]))
        XCTAssertTrue(passesFilters(metrics, filters: ["translation_ratio_max": 0.99]))
        XCTAssertFalse(passesFilters(metrics, filters: ["translation_ratio_max": 0.97]))
    }

    func testLocalizedSurvivalAndFoodScoringAndFilters() {
        let metrics = SimulationMetrics(
            massMean: 1.0,
            massStd: 0.1,
            massMin: 0.9,
            massMax: 1.1,
            occupancyMean: 0.08,
            varianceMean: 0.02,
            energyMean: 0.03,
            speedMean: 0.01,
            pathLength: 10.0,
            displacement: 6.0,
            sampleCount: 16,
            speedCount: 16,
            gyration: 3.0,
            centerVelocity: 0.2,
            velocityX: 0.19,
            velocityY: 0.04,
            headingRad: 0.207496,
            isStable: true,
            survivalTracked: true,
            survivalSteps: nil,
            foodInitialMass: 10.0,
            foodFinalMass: 6.0,
            foodConsumed: 4.0
        )

        XCTAssertEqual(scoreMetrics(metrics, weights: ["survived": 1.0]), 1.0, accuracy: 1e-6)
        XCTAssertEqual(scoreMetrics(metrics, weights: ["compactness": 1.0]), 0.25, accuracy: 1e-6)
        XCTAssertEqual(scoreMetrics(metrics, weights: ["localized_motion": 1.0]), 0.05, accuracy: 1e-6)
        XCTAssertEqual(scoreMetrics(metrics, weights: ["food_consumed_fraction": 1.0]), 0.4, accuracy: 1e-6)
        XCTAssertTrue(passesFilters(metrics, filters: ["survived": 1.0]))
        XCTAssertTrue(passesFilters(metrics, filters: ["localized_motion_min": 0.04]))
        XCTAssertFalse(passesFilters(metrics, filters: ["localized_motion_min": 0.06]))
        XCTAssertTrue(passesFilters(metrics, filters: ["food_consumed_fraction_min": 0.3]))
        XCTAssertFalse(passesFilters(metrics, filters: ["food_consumed_fraction_max": 0.3]))
    }

    func testComponentMetricsComputation() {
        let mass = MLXArray([
            Float(2), 2, 2, 0,
            0, 0, 0, 0,
            0, 0, 0, 1,
            0, 0, 0, 1,
        ]).reshaped([1, 4, 4])
        let result = computeComponentMetricsBatch(
            materialized: materializeMassBatch(mass),
            threshold: 0.5,
            useTorus: false
        )

        XCTAssertEqual(result.count.count, 1)
        XCTAssertEqual(result.count[0], 2.0, accuracy: 1e-6)
        XCTAssertEqual(result.largestFraction[0], 0.75, accuracy: 1e-6)
        XCTAssertGreaterThan(result.largestAnisotropy[0], 0.95)
        XCTAssertEqual(result.massEvenness[0], 0.8112781, accuracy: 1e-5)
        XCTAssertEqual(result.largestSolidity[0], 1.0, accuracy: 1e-6)
        XCTAssertEqual(result.largestMeanThickness[0], 1.0, accuracy: 1e-6)
        XCTAssertEqual(result.largestMaxThickness[0], 1.0, accuracy: 1e-6)
        XCTAssertEqual(result.largestFilamentarity[0], 1.0, accuracy: 1e-6)
    }

    func testComponentMassEvennessRewardsBalancedFleets() {
        let width = 10
        let height = 4
        var balanced = [Float](repeating: 0, count: width * height)
        var dominated = [Float](repeating: 0, count: width * height)
        for x in [0, 2, 4, 6, 8] {
            balanced[1 * width + x] = 1.0
        }
        for x in 0..<5 {
            dominated[1 * width + x] = 1.0
        }
        for x in [7, 9] {
            dominated[1 * width + x] = 0.1
        }
        dominated[3 * width + 0] = 0.1
        dominated[3 * width + 9] = 0.1
        let result = computeComponentMetricsBatch(
            materialized: MassBatchCPU(
                flat: balanced + dominated,
                batch: 2,
                height: height,
                width: width,
                sampleSize: width * height
            ),
            threshold: 0.05,
            useTorus: false
        )

        XCTAssertEqual(result.count[0], 5.0, accuracy: 1e-6)
        XCTAssertEqual(result.massEvenness[0], 1.0, accuracy: 1e-6)
        XCTAssertEqual(result.count[1], 5.0, accuracy: 1e-6)
        XCTAssertLessThan(result.massEvenness[1], 0.55)
    }

    func testComponentMetricScoringAndFilters() {
        let metrics = SimulationMetrics(
            massMean: 1.0,
            massStd: 0.1,
            massMin: 0.9,
            massMax: 1.1,
            occupancyMean: 0.08,
            varianceMean: 0.02,
            energyMean: 0.03,
            speedMean: 0.01,
            pathLength: 10.0,
            displacement: 9.8,
            sampleCount: 16,
            speedCount: 16,
            gyration: 120.0,
            centerVelocity: 0.012,
            velocityX: 0.011,
            velocityY: 0.002,
            headingRad: 0.1798535,
            isStable: true,
            componentCount: 2.0,
            largestComponentFraction: 0.88,
            largestComponentAnisotropy: 0.96,
            largestComponentSolidity: 0.72,
            largestComponentMeanThickness: 1.8,
            largestComponentMaxThickness: 3.0,
            largestComponentFilamentarity: 0.55
        )

        XCTAssertEqual(
            scoreMetrics(metrics, weights: ["largest_component_fraction": 2.0, "component_count": -0.5, "largest_component_anisotropy": -0.25]),
            0.52,
            accuracy: 1e-6
        )
        XCTAssertTrue(passesFilters(metrics, filters: ["component_count_max": 2.0]))
        XCTAssertFalse(passesFilters(metrics, filters: ["component_count_max": 1.0]))
        XCTAssertTrue(passesFilters(metrics, filters: ["largest_component_fraction_min": 0.8]))
        XCTAssertFalse(passesFilters(metrics, filters: ["largest_component_fraction_min": 0.9]))
        XCTAssertTrue(passesFilters(metrics, filters: ["largest_component_anisotropy_max": 1.0]))
        XCTAssertFalse(passesFilters(metrics, filters: ["largest_component_anisotropy_max": 0.9]))
        XCTAssertEqual(scoreMetrics(metrics, weights: ["solidity": 1.0, "thickness": 0.5, "filamentarity": -1.0]), 1.07, accuracy: 1e-6)
        XCTAssertTrue(passesFilters(metrics, filters: ["solidity_min": 0.7]))
        XCTAssertFalse(passesFilters(metrics, filters: ["solidity_min": 0.8]))
        XCTAssertTrue(passesFilters(metrics, filters: ["thickness_min": 1.5]))
        XCTAssertFalse(passesFilters(metrics, filters: ["filamentarity_max": 0.5]))
    }

    func testComponentCountTargetMismatchSupportsFamilyObjectives() {
        XCTAssertEqual(componentCountTargetMismatch(3.0, target: 3.0), 0.0, accuracy: 1e-6)
        XCTAssertEqual(componentCountTargetMismatch(2.0, target: 3.0), 1.0, accuracy: 1e-6)
        XCTAssertEqual(componentCountTargetMismatch(5.0, target: 3.0), 2.0, accuracy: 1e-6)

        let decoded = try! JSONDecoder().decode(
            FitnessConfig.self,
            from: Data(
                """
                {
                  "objective": "template_sequence",
                  "target_step": 120,
                  "angle_threshold": 0.0,
                  "component_count_target": 3.0,
                  "component_count_target_penalty": 2.0,
                  "minimum_component_count": 1.0,
                  "maximum_component_count": 3.0,
                  "component_count_limit_penalty": 7.0,
                  "minimum_largest_component_fraction": 0.95,
                  "maximum_largest_component_fraction": 0.98,
                  "largest_component_fraction_penalty": 9.0,
                  "largest_component_fraction_limit_penalty": 4.0,
                  "maximum_largest_component_anisotropy": 0.45,
                  "minimum_component_mass_evenness": 0.60,
                  "component_mass_evenness_penalty": 15.0,
                  "component_mass_evenness_reward": 1.5,
                  "minimum_moment_mass": 50.0,
                  "maximum_moment_mass": 115.0,
                  "minimum_moment_density": 0.05,
                  "maximum_moment_density": 0.50,
                  "moment_density_penalty": 11.0,
                  "maximum_moment_anisotropy": 0.20,
                  "moment_anisotropy_limit_penalty": 13.0,
                  "morphology_guard_failure_fitness": -1000000.0,
                  "largest_component_internal_stripe_penalty": 23.0,
                  "largest_component_oriented_ridge_penalty": 29.0,
                  "minimum_trajectory_path_length": 0.11,
                  "trajectory_path_length_penalty": 5.0,
                  "trajectory_path_length_reward": 0.25,
                  "minimum_trajectory_displacement": 0.07,
                  "trajectory_displacement_penalty": 6.0,
                  "trajectory_displacement_reward": 0.35,
                  "minimum_movement_efficiency": 0.40,
                  "movement_efficiency_penalty": 7.0,
                  "movement_efficiency_reward": 0.45,
                  "minimum_center_velocity": 0.015,
                  "center_velocity_penalty": 3.0,
                  "center_velocity_reward": 100.0,
                  "sector_transport_reward": 17.0,
                  "sector_transport_bin_count": 48,
                  "sector_transport_minimum_contrast": 0.04,
                  "minimum_sector_transport": 0.08,
                  "sector_transport_penalty": 19.0
                }
                """.utf8
            )
        )

        XCTAssertEqual(decoded.componentCountTarget, 3.0)
        XCTAssertEqual(decoded.componentCountTargetPenalty, 2.0)
        XCTAssertEqual(decoded.minimumComponentCount, 1.0)
        XCTAssertEqual(decoded.maximumComponentCount, 3.0)
        XCTAssertEqual(decoded.componentCountLimitPenalty, 7.0)
        XCTAssertEqual(decoded.minimumLargestComponentFraction, 0.95)
        XCTAssertEqual(decoded.maximumLargestComponentFraction, 0.98)
        XCTAssertEqual(decoded.largestComponentFractionPenalty, 9.0)
        XCTAssertEqual(decoded.largestComponentFractionLimitPenalty, 4.0)
        XCTAssertEqual(decoded.maximumLargestComponentAnisotropy, 0.45)
        XCTAssertEqual(decoded.minimumComponentMassEvenness, 0.60)
        XCTAssertEqual(decoded.componentMassEvennessPenalty, 15.0)
        XCTAssertEqual(decoded.componentMassEvennessReward, 1.5)
        XCTAssertEqual(decoded.minimumMomentMass, 50.0)
        XCTAssertEqual(decoded.maximumMomentMass, 115.0)
        XCTAssertEqual(decoded.minimumMomentDensity, 0.05)
        XCTAssertEqual(decoded.maximumMomentDensity, 0.50)
        XCTAssertEqual(decoded.momentDensityPenalty, 11.0)
        XCTAssertEqual(decoded.maximumMomentAnisotropy, 0.20)
        XCTAssertEqual(decoded.momentAnisotropyLimitPenalty, 13.0)
        XCTAssertEqual(decoded.morphologyGuardFailureFitness, -1000000.0)
        XCTAssertEqual(decoded.largestComponentInternalStripePenalty, 23.0)
        XCTAssertEqual(decoded.largestComponentOrientedRidgePenalty, 29.0)
        XCTAssertTrue(decoded.usesMorphologyGuard)
	        XCTAssertEqual(decoded.minimumTrajectoryPathLength, 0.11)
	        XCTAssertEqual(decoded.trajectoryPathLengthPenalty, 5.0)
	        XCTAssertEqual(decoded.trajectoryPathLengthReward, 0.25)
	        XCTAssertEqual(decoded.minimumTrajectoryDisplacement, 0.07)
	        XCTAssertEqual(decoded.trajectoryDisplacementPenalty, 6.0)
	        XCTAssertEqual(decoded.trajectoryDisplacementReward, 0.35)
	        XCTAssertEqual(decoded.minimumMovementEfficiency, 0.40)
	        XCTAssertEqual(decoded.movementEfficiencyPenalty, 7.0)
	        XCTAssertEqual(decoded.movementEfficiencyReward, 0.45)
	        XCTAssertEqual(decoded.minimumCenterVelocity, 0.015)
	        XCTAssertEqual(decoded.centerVelocityPenalty, 3.0)
	        XCTAssertEqual(decoded.centerVelocityReward, 100.0)
        XCTAssertEqual(decoded.sectorTransportReward, 17.0)
        XCTAssertEqual(decoded.sectorTransportBinCount, 48)
        XCTAssertEqual(decoded.sectorTransportMinimumContrast, 0.04)
        XCTAssertEqual(decoded.minimumSectorTransport, 0.08)
        XCTAssertEqual(decoded.sectorTransportPenalty, 19.0)
        XCTAssertTrue(decoded.usesMorphologyMetrics)
        XCTAssertTrue(decoded.usesTrajectoryMetrics)
        XCTAssertTrue(decoded.usesSectorTransport)
    }

    func testEvolutionMorphologyGuardRejectsDeadCandidateBeforeMotionScore() throws {
        let statePatch = InitStatePatchConfig(
            center: [16, 16],
            width: 4,
            height: 4,
            channels: 1,
            values: [Float](repeating: 0.0, count: 4 * 4)
        )
        let runtimeConfig = makeRuntimeConfigForSearchEngine(
            sx: 32,
            sy: 32,
            channels: 1,
            parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
            pUniform: nil,
            chemotaxis: nil,
            patches: [],
            aUniform: UniformRange(low: 0.0, high: 0.0),
            statePatch: statePatch
        )
        let esConfig = ESConfig(
            outputDir: "/tmp/evolution-morphology-guard-test",
            generations: 1,
            population: 2,
            sigma: 0.01,
            learningRate: 0.01,
            seed: 123,
            steps: 2,
            fitness: FitnessConfig(
                objective: "directed_motion",
                targetStep: 2,
                angleThreshold: 0.0,
                minimumComponentCount: 1.0,
                minimumLargestComponentFraction: 0.95,
                minimumMomentMass: 1.0,
                minimumMomentDensity: 0.05,
                maximumMomentAnisotropy: 0.4,
                morphologyGuardFailureFitness: -123.0
            ),
            fitnessShaping: "raw",
            initPatch: nil,
            initialInitPatchValues: nil,
            paramRanges: nil,
            obstacleField: nil
        )
        let ranges: [String: (Float, Float)] = [
            "r": (0.1, 1.0),
            "b": (0.0, 1.0),
            "w": (0.0, 1.0),
            "a": (0.0, 1.0),
            "m": (0.0, 1.0),
            "s": (0.01, 0.2),
            "h": (0.0, 1.0),
            "R": (1.0, 10.0),
        ]
        let engine = EvolutionEngine(runtimeConfig: runtimeConfig, esConfig: esConfig, ranges: ranges)
        let candidate = paramsToVector(
            runtimeConfig.params,
            space: ParamSpace(nbK: runtimeConfig.nbK, ranges: ranges)
        )

        let export = engine.evaluateCandidateForResearchExport(candidate)

        XCTAssertEqual(export.fitness, -123.0, accuracy: 1e-6)
        let morphology = try XCTUnwrap(export.finalMorphology)
        XCTAssertTrue(morphology.guardFailed)
        XCTAssertEqual(morphology.componentCount ?? -1, 0.0, accuracy: 1e-6)
        XCTAssertEqual(export.resultData.metrics.componentCount ?? -1, 0.0, accuracy: 1e-6)
        XCTAssertNotNil(export.resultData.metrics.momentDensity)
        XCTAssertNotNil(export.resultData.metrics.largestComponentInternalStripe)
        XCTAssertNotNil(export.resultData.metrics.largestComponentOrientedRidge)
        let metadata = try researchMetadataValue(morphology.metadataPayload)
        let metadataData = try JSONEncoder().encode(metadata)
        let metadataJSON = try XCTUnwrap(
            JSONSerialization.jsonObject(with: metadataData) as? [String: Any]
        )
        XCTAssertEqual(metadataJSON["guard_failed"] as? Bool, true)
        XCTAssertEqual(try XCTUnwrap(metadataJSON["component_count"] as? Double), 0.0, accuracy: 1e-6)
    }

    func testEvolutionHelpersExcludeExternalChannels() {
        let state = MLXArray([
            Float(1), 0, 10,
            0, 0, 10,
            0, 0, 10,
            0, 0, 10,
        ]).reshaped([2, 2, 3])

        let massMap = evolutionMassMap(state, excludedChannels: [2])
        eval(massMap)
        let flat = massMap.flattened().asArray(Float.self)
        XCTAssertEqual(flat, [1, 0, 0, 0])

        let com = centerOfMass(state, excludedChannels: [2])
        XCTAssertNotNil(com)
        XCTAssertEqual(com!.0, Float(-0.5), accuracy: 1e-6)
        XCTAssertEqual(com!.1, Float(-0.5), accuracy: 1e-6)
    }

    func testCreatureChannelsExcludeChemotaxisAndObstacleField() {
        let chemotaxis = ChemotaxisConfig(
            enabled: true,
            channel_index: 2,
            mode: "random_on_circle",
            sigma: 10.0,
            amplitude: 1.0,
            include_in_mass: false,
            center: [64.0, 64.0],
            circle_radius: 40.0,
            seed: 0
        )
        let obstacleField = ESObstacleFieldConfig(
            enabled: true,
            channelIndex: 2,
            mode: "random_on_circle",
            count: 12,
            circleRadius: 42.0,
            sigma: 3.5,
            amplitude: 1.0,
            center: [64.0, 64.0],
            seed: 7
        )

        let excluded = excludedMassChannelsForEvolution(
            channels: 3,
            chemotaxis: chemotaxis,
            food: nil,
            obstacleField: obstacleField
        )
        XCTAssertEqual(excluded, Set([2]))

        let creatureChannels = creatureChannelsForEvolution(
            channels: 3,
            chemotaxis: chemotaxis,
            food: nil,
            obstacleField: obstacleField
        )
        XCTAssertEqual(creatureChannels, [0, 1])
    }

    func testOverwriteChannelBatchMatchesConcatenationReference() {
        let batch = 2
        let sx = 4
        let sy = 3
        let channels = 3
        let values = (0..<(batch * sx * sy * channels)).map { Float($0) / 100.0 }
        let state = MLXArray(values).reshaped([batch, sx, sy, channels])
        let fieldValues = (0..<(batch * sx * sy)).map { Float($0) / 10.0 }
        let field = MLXArray(fieldValues).reshaped([batch, sx, sy])

        func reference(_ A: MLXArray, field: MLXArray, channelIndex: Int) -> MLXArray {
            let fieldExpanded = field.expandedDimensions(axis: -1)
            var parts: [MLXArray] = []
            for c in 0..<channels {
                if c == channelIndex {
                    parts.append(fieldExpanded)
                } else {
                    parts.append(A[0..., 0..., 0..., c].expandedDimensions(axis: -1))
                }
            }
            return MLX.concatenated(parts, axis: 3)
        }

        let expected = reference(state, field: field, channelIndex: 1)
        let actual = overwriteFieldChannel(state, field: field, channelIndex: 1)
        XCTAssertLessThan(maxAbsDiff(expected, actual), 1e-6)
    }

    func testComputeFlowWallPotentialRepelsFromCenter() {
        let sx = 7
        let sy = 7
        let A = MLX.zeros([1, sx, sy, 1])
        let fK = MLX.zeros([1, sx, sy, 1])
        let m = MLXArray([Float(0.15)])
        let s = MLXArray([Float(0.015)])
        let h = MLXArray([Float(0.0)])
        let c0Idxs = MLXArray([Int32(0)])
        let c1Mask = MLXArray([Float(1.0)]).reshaped([1, 1])

        var potential = [Float](repeating: 0.0, count: sx * sy)
        potential[3 * sy + 3] = -1.0
        let wallPotential = MLXArray(potential).reshaped([1, sx, sy, 1])

        let flow = computeFlow(
            A,
            fK: fK,
            m: m,
            s: s,
            h: h,
            c0Idxs: c0Idxs,
            c1Mask: c1Mask,
            thetaA: 1.0,
            n: 1,
            gradientBoundary: "zero_pad",
            alphaMode: "mass",
            flowClip: "none",
            chemChannel: nil,
            chemIncludeInMass: true,
            dd: 5,
            sigma: 0.65,
            wallPotential: wallPotential
        )

        let leftX = flow[0, 3, 2, 1].item(Float.self)
        let rightX = flow[0, 3, 4, 1].item(Float.self)
        XCTAssertGreaterThan(leftX, 0.0)
        XCTAssertLessThan(rightX, 0.0)
    }

    func testSampleOpenESNoiseUsesAntitheticPairs() {
        var rng = SeededRandomNumberGenerator(seed: 123)
        let noise = sampleOpenESNoise(population: 4, dimensions: 3, rng: &rng)
        XCTAssertEqual(noise.count, 4)
        XCTAssertEqual(noise[0].count, 3)
        for j in 0..<3 {
            XCTAssertEqual(noise[0][j], -noise[2][j], accuracy: 1e-6)
            XCTAssertEqual(noise[1][j], -noise[3][j], accuracy: 1e-6)
        }
    }

    func testKernelNormalization() {
        let (config, c0, c1, params) = makeTestSetup()
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)

        let kShifted = MLXFFT.ifft2(kernels.fK, axes: [1, 2]).realPart()
        let sums = kShifted.sum(axes: [1, 2])
        eval(sums)
        let values = sums.flattened().asArray(Float.self)

        XCTAssertEqual(values.count, config.nbK)
        for sum in values {
            XCTAssertEqual(sum, 1.0, accuracy: 1e-4)
        }
    }

    func testPopulationKernelsMatchSingleKernelPath() {
        let (config, c0, c1, params) = makeTestSetup()
        let singleKernels = compileKernels(params: params, config: config, c0: c0, c1: c1)
        let populationKernels = compilePopulationKernels(
            paramsBatch: [params, params],
            config: config,
            c0: c0,
            c1: c1
        )

        XCTAssertEqual(populationKernels.fK.shape[0], 2)
        XCTAssertEqual(populationKernels.m.shape, [2, config.nbK])
        XCTAssertEqual(populationKernels.s.shape, [2, config.nbK])
        XCTAssertEqual(populationKernels.h.shape, [2, config.nbK])

        let singleEngine = FlowLeniaBatched(config: config, kernels: singleKernels)
        let populationEngine = FlowLeniaBatched(config: config, kernels: populationKernels)

        let state = makePatchState(sx: config.sx, sy: config.sy, channels: config.channels)
        let singleStep = singleEngine.stepUncompiled(state.expandedDimensions(axis: 0))
        let populationStep = populationEngine.stepUncompiled(MLX.stacked([state, state]))
        let expectedPopulation = MLX.stacked([singleStep.squeezed(axis: 0), singleStep.squeezed(axis: 0)])
        XCTAssertLessThan(maxAbsDiff(expectedPopulation, populationStep), 1e-4)
    }

    func testMassConservationAndNonNegativityOnTorus() {
        let (config, c0, c1, params) = makeTestSetup()
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)
        let sim = FlowLeniaBatched(config: config, kernels: kernels)

        let A0 = makePatchState(sx: config.sx, sy: config.sy, channels: config.channels)
        let A1 = sim.stepUncompiled(A0.expandedDimensions(axis: 0)).squeezed(axis: 0)

        let total0 = sumArray(A0)
        let total1 = sumArray(A1)
        let tol = max(1e-5, 1e-4 * total0)
        XCTAssertEqual(total0, total1, accuracy: tol)

        let minVal = minArray(A1)
        XCTAssertGreaterThanOrEqual(minVal, -1e-6)
    }

    func testUniformStateIsFixedPoint() {
        let (config, c0, c1, params) = makeTestSetup()
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)
        let sim = FlowLeniaBatched(config: config, kernels: kernels)

        let A0 = makeUniformState(sx: config.sx, sy: config.sy, channels: config.channels, value: 0.5)
        let A1 = sim.stepUncompiled(A0.expandedDimensions(axis: 0)).squeezed(axis: 0)

        let diff = maxAbsDiff(A0, A1)
        XCTAssertLessThan(diff, 1e-4)
    }

    func testParameterEmbeddingMatchesBaseForConstantP() {
        let (config, c0, c1, params) = makeTestSetup()
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)

        let baseEngine = FlowLeniaBatched(config: config, kernels: kernels)
        let embedEngine = FlowLeniaParamsBatched(config: config, kernels: kernels, mixMode: "avg", mixSeed: nil)

        let A0 = makePatchState(sx: config.sx, sy: config.sy, channels: config.channels)
        let ABatch = A0.expandedDimensions(axis: 0)

        let h = kernels.h.reshaped([1, 1, 1, -1])
        let P = MLX.broadcast(h, to: [1, config.sx, config.sy, config.nbK])

        let ABase = baseEngine.step(ABatch)
        let (AEmbed, _) = embedEngine.step(ABatch, P)

        let diff = maxAbsDiff(ABase, AEmbed)
        XCTAssertLessThan(diff, 1e-4)
    }

    func testParameterEmbeddingMatchesBaseForConstantPAcrossMixModes() {
        let (config, c0, c1, params) = makeTestSetup()
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)

        let baseEngine = FlowLeniaBatched(config: config, kernels: kernels)
        let A0 = makePatchState(sx: config.sx, sy: config.sy, channels: config.channels)
        let ABatch = A0.expandedDimensions(axis: 0)

        let h = kernels.h.reshaped([1, 1, 1, -1])
        let P = MLX.broadcast(h, to: [1, config.sx, config.sy, config.nbK])
        let expectedA = baseEngine.step(ABatch)

        let mixModes: [(String, Int?)] = [
            ("avg", nil),
            ("softmax", 7),
            ("stoch", 7),
            ("argmax", nil),
            ("stoch_gene_wise", 7),
            ("energy", 7)
        ]

        for (mixMode, mixSeed) in mixModes {
            let embedEngine = FlowLeniaParamsBatched(
                config: config,
                kernels: kernels,
                mixMode: mixMode,
                mixSeed: mixSeed
            )
            let (embeddedA, embeddedP) = embedEngine.step(ABatch, P)
            XCTAssertLessThan(maxAbsDiff(expectedA, embeddedA), 1e-4, "mixMode=\(mixMode)")
            let support = embeddedA.sum(axis: -1)
            XCTAssertLessThan(
                maxParamDiffOnMassSupport(expected: P, actual: embeddedP, support: support),
                1e-6,
                "mixMode=\(mixMode)"
            )
        }
    }

    func testParameterEmbeddingNonAverageMixModesProduceFiniteOutputs() {
        let (config, c0, c1, params) = makeTestSetup()
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)
        let ABatch = makePatchState(sx: config.sx, sy: config.sy, channels: config.channels)
            .expandedDimensions(axis: 0)
        let P = makeVaryingParamBatch(batch: 1, sx: config.sx, sy: config.sy, nbK: config.nbK)

        let modes: [(String, Int?)] = [
            ("softmax", 7),
            ("stoch", 7),
            ("argmax", nil),
            ("stoch_gene_wise", 7),
            ("energy", 7)
        ]

        for (mode, seed) in modes {
            let engine = FlowLeniaParamsBatched(config: config, kernels: kernels, mixMode: mode, mixSeed: seed)
            let (nextA, nextP) = engine.step(ABatch, P)
            XCTAssertEqual(nextA.shape, ABatch.shape, "Unexpected A shape for mix mode \(mode)")
            XCTAssertEqual(nextP.shape, P.shape, "Unexpected P shape for mix mode \(mode)")

            eval(nextA, nextP)
            let aValues = nextA.flattened().asArray(Float.self)
            let pValues = nextP.flattened().asArray(Float.self)
            XCTAssertFalse(aValues.contains { !$0.isFinite }, "Non-finite A output for mix mode \(mode)")
            XCTAssertFalse(pValues.contains { !$0.isFinite }, "Non-finite P output for mix mode \(mode)")
        }
    }

    func testParameterEmbeddingSelectionMixModesPreserveConstantParameters() {
        let (config, c0, c1, params) = makeTestSetup()
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)
        let ABatch = makePatchState(sx: config.sx, sy: config.sy, channels: config.channels)
            .expandedDimensions(axis: 0)
        let constantParams = MLX.broadcast(
            kernels.h.reshaped([1, 1, 1, config.nbK]),
            to: [1, config.sx, config.sy, config.nbK]
        )

        let modes: [(String, Int?)] = [
            ("softmax", 7),
            ("stoch", 7),
            ("argmax", nil),
            ("stoch_gene_wise", 7),
            ("energy", 7)
        ]

        for (mode, seed) in modes {
            let engine = FlowLeniaParamsBatched(config: config, kernels: kernels, mixMode: mode, mixSeed: seed)
            let (nextA, nextP) = engine.step(ABatch, constantParams)
            let support = nextA.sum(axis: -1)
            let diff = maxParamDiffOnMassSupport(expected: constantParams, actual: nextP, support: support)
            XCTAssertLessThan(diff, 1e-5, "Constant parameters drifted for mix mode \(mode)")
        }
    }

    func testPaperKernelMatchesEquation1() {
        let (config, c0, c1, params) = makeTestSetup()
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)

        let expected = computePaperKernel2D(
            sx: config.sx,
            sy: config.sy,
            params: params,
            kernelIndex: 0
        )

        let kShifted = MLXFFT.ifft2(kernels.fK, axes: [1, 2]).realPart()
        let kNoBatch = kShifted.squeezed(axis: 0)
        let kUnshifted = unshift2(kNoBatch)
        let k0 = kUnshifted[0..., 0..., 0]
        eval(k0)
        let actual = k0.flattened().asArray(Float.self)

        XCTAssertEqual(actual.count, expected.count)
        var maxDiff: Float = 0.0
        for (a, e) in zip(actual, expected) {
            let diff = abs(a - e)
            if diff > maxDiff { maxDiff = diff }
        }
        XCTAssertLessThan(maxDiff, 1e-4)
    }

    func testAlphaModeMassMatchesPaperAndPerChannelDiffers() {
        let sx = 8
        let sy = 8
        let channels = 2
        let connectivity = [[1, 0], [0, 0]]
        let (c0, c1) = connFromMatrix(connectivity)

        let params = ResolvedParams(
            r: [0.5],
            b: [[1.0, 0.0, 0.0]],
            w: [[0.2, 0.2, 0.2]],
            a: [[0.5, 0.5, 0.5]],
            m: [0.15],
            s: [0.05],
            h: [0.0],
            R: 6.0,
            seed: 0
        )

        let config = BatchedConfig(
            sx: sx,
            sy: sy,
            channels: channels,
            nbK: c0.count,
            dt: 0.2,
            dd: 2,
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
            chemChannel: nil,
            chemIncludeInMass: true
        )

        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)
        let A = makeTwoChannelPatchBatch(sx: sx, sy: sy)

        let Fmass = computeFlow(
            A,
            fK: kernels.fK,
            m: kernels.m,
            s: kernels.s,
            h: kernels.h,
            c0Idxs: kernels.c0Idxs,
            c1Mask: kernels.c1Mask,
            thetaA: config.thetaA,
            n: config.n,
            gradientBoundary: config.implementation.gradientBoundary,
            alphaMode: "mass",
            flowClip: "none",
            chemChannel: nil,
            chemIncludeInMass: true,
            dd: config.dd,
            sigma: config.sigma
        ).squeezed(axis: 0)

        let FmassC0 = Fmass[0..., 0..., 0..., 0]
        let FmassC1 = Fmass[0..., 0..., 0..., 1]
        let diffMass = maxAbsDiff(FmassC0, FmassC1)
        XCTAssertLessThan(diffMass, 1e-6)

        let Fper = computeFlow(
            A,
            fK: kernels.fK,
            m: kernels.m,
            s: kernels.s,
            h: kernels.h,
            c0Idxs: kernels.c0Idxs,
            c1Mask: kernels.c1Mask,
            thetaA: config.thetaA,
            n: config.n,
            gradientBoundary: config.implementation.gradientBoundary,
            alphaMode: "per_channel",
            flowClip: "none",
            chemChannel: nil,
            chemIncludeInMass: true,
            dd: config.dd,
            sigma: config.sigma
        ).squeezed(axis: 0)

        let FperC0 = Fper[0..., 0..., 0..., 0]
        let FperC1 = Fper[0..., 0..., 0..., 1]
        let diffPer = maxAbsDiff(FperC0, FperC1)
        XCTAssertGreaterThan(diffPer, 1e-4)
    }

    func testPaperParamEmbeddingInitIsPatchConstant() throws {
        let runtimeConfig = makeRuntimeConfigForSearchEngine(
            channels: 1,
            parameterEmbedding: ParameterEmbeddingConfig(enabled: true, mix: "avg", mix_seed: nil),
            pUniform: UniformRange(low: 0.0, high: 1.0),
            chemotaxis: nil
        )
        let initializationBuilder = makeSearchInitializationBuilder(runtimeConfig: runtimeConfig)
        XCTAssertTrue(initializationBuilder.constantPerPatchParameters)
        let P = try XCTUnwrap(initializationBuilder.buildInitialParameterState(seed: 123))
        eval(P)
        let data = P.flattened().asArray(Float.self)

        let patch = runtimeConfig.patches[0]
        let half = patch.size / 2
        let x0 = patch.center[0] - half
        let x1 = patch.center[0] + (patch.size - half)
        let y0 = patch.center[1] - half
        let y1 = patch.center[1] + (patch.size - half)

        for k in 0..<runtimeConfig.nbK {
            let refIdx = ((x0 * runtimeConfig.sy) + y0) * runtimeConfig.nbK + k
            let ref = data[refIdx]
            for x in x0..<x1 {
                for y in y0..<y1 {
                    let idx = ((x * runtimeConfig.sy) + y) * runtimeConfig.nbK + k
                    XCTAssertEqual(data[idx], ref, accuracy: 1e-6)
                }
            }
        }
    }

    func testEvolutionInitialStateUsesRuntimeStatePatch() throws {
        let values = (0..<(4 * 4 * 2)).map { Float($0 + 1) / 100.0 }
        let statePatch = InitStatePatchConfig(
            center: [16, 16],
            width: 4,
            height: 4,
            channels: 2,
            values: values
        )
        let runtimeConfig = makeRuntimeConfigForSearchEngine(
            sx: 32,
            sy: 32,
            channels: 2,
            parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
            pUniform: nil,
            chemotaxis: nil,
            patches: [],
            aUniform: UniformRange(low: 0.0, high: 0.0),
            statePatch: statePatch
        )
        let esConfig = ESConfig(
            outputDir: "/tmp/evolution-state-patch-test",
            generations: 1,
            population: 2,
            sigma: 0.01,
            learningRate: 0.01,
            seed: 123,
            steps: 4,
            fitness: FitnessConfig(objective: "directed_motion", targetStep: 2, angleThreshold: 0.0),
            fitnessShaping: "raw",
            initPatch: nil,
            initialInitPatchValues: nil,
            paramRanges: nil,
            obstacleField: nil
        )
        let ranges: [String: (Float, Float)] = [
            "r": (0.1, 1.0),
            "b": (0.0, 1.0),
            "w": (0.0, 1.0),
            "a": (0.0, 1.0),
            "m": (0.0, 1.0),
            "s": (0.01, 0.2),
            "h": (0.0, 1.0),
            "R": (1.0, 10.0),
        ]

        let engine = EvolutionEngine(runtimeConfig: runtimeConfig, esConfig: esConfig, ranges: ranges)
        let state = engine.buildInitialState(seed: 999)
        eval(state)
        let data = state.flattened().asArray(Float.self)

        let x0 = 14
        let y0 = 14
        var patchIndex = 0
        for x in x0..<(x0 + 4) {
            for y in y0..<(y0 + 4) {
                for c in 0..<2 {
                    let idx = (x * runtimeConfig.sy + y) * runtimeConfig.channels + c
                    XCTAssertEqual(data[idx], values[patchIndex], accuracy: 1e-6)
                    patchIndex += 1
                }
            }
        }
        XCTAssertEqual(data.reduce(0, +), values.reduce(0, +), accuracy: 1e-5)
    }

    func testEvolutionResearchExportPreservesRuntimeStatePatch() throws {
        let values = (0..<(4 * 4 * 2)).map { Float($0 + 1) / 100.0 }
        let statePatch = InitStatePatchConfig(
            center: [16, 16],
            width: 4,
            height: 4,
            channels: 2,
            values: values
        )
        let runtimeConfig = makeRuntimeConfigForSearchEngine(
            sx: 32,
            sy: 32,
            channels: 2,
            parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
            pUniform: nil,
            chemotaxis: nil,
            patches: [],
            aUniform: UniformRange(low: 0.0, high: 0.0),
            statePatch: statePatch
        )
        let esConfig = ESConfig(
            outputDir: "/tmp/evolution-state-patch-export-test",
            generations: 1,
            population: 2,
            sigma: 0.01,
            learningRate: 0.01,
            seed: 123,
            steps: 4,
            fitness: FitnessConfig(objective: "directed_motion", targetStep: 2, angleThreshold: 0.0),
            fitnessShaping: "raw",
            initPatch: nil,
            initialInitPatchValues: nil,
            paramRanges: nil,
            obstacleField: nil
        )
        let ranges: [String: (Float, Float)] = [
            "r": (0.1, 1.0),
            "b": (0.0, 1.0),
            "w": (0.0, 1.0),
            "a": (0.0, 1.0),
            "m": (0.0, 1.0),
            "s": (0.01, 0.2),
            "h": (0.0, 1.0),
            "R": (1.0, 10.0),
        ]

        let engine = EvolutionEngine(runtimeConfig: runtimeConfig, esConfig: esConfig, ranges: ranges)
        let candidate = paramsToVector(
            runtimeConfig.params,
            space: ParamSpace(nbK: runtimeConfig.nbK, ranges: ranges)
        )
        let export = engine.evaluateCandidateForResearchExport(candidate)

        let exportedPatch = try XCTUnwrap(export.initConfig.state_patch)
        XCTAssertEqual(exportedPatch.width, statePatch.width)
        XCTAssertEqual(exportedPatch.height, statePatch.height)
        XCTAssertEqual(exportedPatch.channels, statePatch.channels)
        XCTAssertEqual(exportedPatch.center, statePatch.center)
        XCTAssertEqual(export.initConfig.patches.count, 0)
        XCTAssertEqual(export.initConfig.a_uniform.low, 0.0)
        XCTAssertEqual(export.initConfig.a_uniform.high, 0.0)
    }

    func testEvolutionTemplateSequenceObjectiveScoresRuntimeStatePatchFrames() throws {
        var values = [Float](repeating: 0.0, count: 8 * 8)
        for x in 2..<6 {
            for y in 2..<6 {
                values[x * 8 + y] = 0.75
            }
        }
        let statePatch = InitStatePatchConfig(
            center: [16, 16],
            width: 8,
            height: 8,
            channels: 1,
            values: values
        )
        let runtimeConfig = makeRuntimeConfigForSearchEngine(
            sx: 32,
            sy: 32,
            channels: 1,
            parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
            pUniform: nil,
            chemotaxis: nil,
            patches: [],
            aUniform: UniformRange(low: 0.0, high: 0.0),
            statePatch: statePatch
        )
        let esConfig = ESConfig(
            outputDir: "/tmp/evolution-template-sequence-test",
            generations: 1,
            population: 2,
            sigma: 0.01,
            learningRate: 0.01,
            seed: 321,
            steps: 3,
            fitness: FitnessConfig(
                objective: "template_sequence",
                targetStep: 3,
                angleThreshold: 0.0,
                templateSequenceReward: 1.0,
                templateSequenceSteps: [0, 1, 3]
            ),
            fitnessShaping: "raw",
            initPatch: nil,
            initialInitPatchValues: nil,
            paramRanges: nil,
            obstacleField: nil
        )
        let ranges: [String: (Float, Float)] = [
            "r": (0.1, 1.0),
            "b": (0.0, 1.0),
            "w": (0.0, 1.0),
            "a": (0.0, 1.0),
            "m": (0.0, 1.0),
            "s": (0.01, 0.2),
            "h": (0.0, 1.0),
            "R": (1.0, 10.0),
        ]

        let engine = EvolutionEngine(runtimeConfig: runtimeConfig, esConfig: esConfig, ranges: ranges)
        let result = engine.runGeneration(gen: 0)
        XCTAssertTrue(result.bestFitness.isFinite)
        XCTAssertGreaterThan(result.bestFitness, 0.0)

        let candidate = paramsToVector(
            runtimeConfig.params,
            space: ParamSpace(nbK: runtimeConfig.nbK, ranges: ranges)
        )
        let export = engine.evaluateCandidateForResearchExport(candidate)
        XCTAssertTrue(export.fitness.isFinite)
        XCTAssertGreaterThan(export.fitness, 0.0)
    }

    func testEvolutionTemplateSequenceObjectiveAcceptsExplicitSequencePatches() throws {
        var values = [Float](repeating: 0.0, count: 8 * 8)
        for x in 2..<6 {
            for y in 2..<6 {
                values[x * 8 + y] = 0.75
            }
        }
        let statePatch = InitStatePatchConfig(
            center: [16, 16],
            width: 8,
            height: 8,
            channels: 1,
            values: values
        )
        let runtimeConfig = makeRuntimeConfigForSearchEngine(
            sx: 32,
            sy: 32,
            channels: 1,
            parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
            pUniform: nil,
            chemotaxis: nil,
            patches: [],
            aUniform: UniformRange(low: 0.0, high: 0.0),
            statePatch: statePatch
        )
        let ranges: [String: (Float, Float)] = [
            "r": (0.1, 1.0),
            "b": (0.0, 1.0),
            "w": (0.0, 1.0),
            "a": (0.0, 1.0),
            "m": (0.0, 1.0),
            "s": (0.01, 0.2),
            "h": (0.0, 1.0),
            "R": (1.0, 10.0),
        ]
        let candidate = paramsToVector(
            runtimeConfig.params,
            space: ParamSpace(nbK: runtimeConfig.nbK, ranges: ranges)
        )

        func score(with templates: [InitStatePatchConfig]) -> Float {
            let esConfig = ESConfig(
                outputDir: "/tmp/evolution-explicit-template-sequence-test",
                generations: 1,
                population: 2,
                sigma: 0.01,
                learningRate: 0.01,
                seed: 321,
                steps: 1,
                fitness: FitnessConfig(
                    objective: "template_sequence",
                    targetStep: 1,
                    angleThreshold: 0.0,
                    templateSequenceReward: 1.0,
                    templateSequenceSteps: [0],
                    templateSequenceStatePatches: templates
                ),
                fitnessShaping: "raw",
                initPatch: nil,
                initialInitPatchValues: nil,
                paramRanges: nil,
                obstacleField: nil
            )
            let engine = EvolutionEngine(runtimeConfig: runtimeConfig, esConfig: esConfig, ranges: ranges)
            return engine.evaluateCandidateForResearchExport(candidate).fitness
        }

        let matchingScore = score(with: [statePatch])
        let emptyTemplate = InitStatePatchConfig(
            center: [16, 16],
            width: 8,
            height: 8,
            channels: 1,
            values: [Float](repeating: 0.0, count: 8 * 8)
        )
        let emptyTemplateScore = score(with: [emptyTemplate])

        XCTAssertGreaterThan(matchingScore, 0.9)
        XCTAssertLessThan(emptyTemplateScore, 0.1)
    }

    func testEvolutionTemplateSequenceMassPenaltyRejectsScaleDrift() throws {
        var values = [Float](repeating: 0.0, count: 8 * 8)
        for x in 2..<6 {
            for y in 2..<6 {
                values[x * 8 + y] = 0.5
            }
        }
        let statePatch = InitStatePatchConfig(
            center: [16, 16],
            width: 8,
            height: 8,
            channels: 1,
            values: values
        )
        let runtimeConfig = makeRuntimeConfigForSearchEngine(
            sx: 32,
            sy: 32,
            channels: 1,
            parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
            pUniform: nil,
            chemotaxis: nil,
            patches: [],
            aUniform: UniformRange(low: 0.0, high: 0.0),
            statePatch: statePatch
        )
        let ranges: [String: (Float, Float)] = [
            "r": (0.1, 1.0),
            "b": (0.0, 1.0),
            "w": (0.0, 1.0),
            "a": (0.0, 1.0),
            "m": (0.0, 1.0),
            "s": (0.01, 0.2),
            "h": (0.0, 1.0),
            "R": (1.0, 10.0),
        ]
        let candidate = paramsToVector(
            runtimeConfig.params,
            space: ParamSpace(nbK: runtimeConfig.nbK, ranges: ranges)
        )

        func score(with template: InitStatePatchConfig) -> Float {
            let esConfig = ESConfig(
                outputDir: "/tmp/evolution-template-sequence-mass-penalty-test",
                generations: 1,
                population: 2,
                sigma: 0.01,
                learningRate: 0.01,
                seed: 321,
                steps: 1,
                fitness: FitnessConfig(
                    objective: "template_sequence",
                    targetStep: 1,
                    angleThreshold: 0.0,
                    templateSequenceReward: 1.0,
                    templateSequenceMassPenalty: 1.0,
                    templateSequenceSteps: [0],
                    templateSequenceStatePatches: [template]
                ),
                fitnessShaping: "raw",
                initPatch: nil,
                initialInitPatchValues: nil,
                paramRanges: nil,
                obstacleField: nil
            )
            let engine = EvolutionEngine(runtimeConfig: runtimeConfig, esConfig: esConfig, ranges: ranges)
            return engine.evaluateCandidateForResearchExport(candidate).fitness
        }

        let matchingScore = score(with: statePatch)
        let doubledMassTemplate = InitStatePatchConfig(
            center: [16, 16],
            width: 8,
            height: 8,
            channels: 1,
            values: values.map { $0 * 2 }
        )
        let doubledMassScore = score(with: doubledMassTemplate)

        XCTAssertGreaterThan(matchingScore, 0.9)
        XCTAssertLessThan(doubledMassScore, matchingScore - 0.4)
    }

    func testTemplateSupportMismatchDetectsSwollenSupport() throws {
        var compactValues = [Float](repeating: 0.0, count: 8 * 8)
        for x in 3..<5 {
            for y in 3..<5 {
                compactValues[x * 8 + y] = 0.5
            }
        }
        let compactPatch = InitStatePatchConfig(
            center: [8, 8],
            width: 8,
            height: 8,
            channels: 1,
            values: compactValues
        )
        let template = makeStatePatchMassTemplate(
            statePatch: compactPatch,
            gridHeight: 16,
            gridWidth: 16,
            includedChannels: [0],
            threshold: 0.03
        )

        var compactSample = [Float](repeating: 0.0, count: 16 * 16)
        var swollenSample = [Float](repeating: 0.0, count: 16 * 16)
        for x in 7..<9 {
            for y in 7..<9 {
                compactSample[x * 16 + y] = 0.5
            }
        }
        for x in 5..<11 {
            for y in 5..<11 {
                swollenSample[x * 16 + y] = 0.06
            }
        }
        let materialized = MassBatchCPU(
            flat: compactSample + swollenSample,
            batch: 2,
            height: 16,
            width: 16,
            sampleSize: 16 * 16
        )

        let mismatches = computeTemplateSupportMismatchBatch(
            materialized: materialized,
            template: template,
            threshold: 0.03
        )

        XCTAssertEqual(mismatches[0], 0, accuracy: 1e-6)
        XCTAssertGreaterThan(mismatches[1], 0.8)
    }

    func testTemplateChangeMismatchRejectsStaticSequenceClone() throws {
        var previousTemplateValues = [Float](repeating: 0.0, count: 16 * 16)
        var currentTemplateValues = [Float](repeating: 0.0, count: 16 * 16)
        for x in 7..<9 {
            for y in 7..<9 {
                previousTemplateValues[x * 16 + y] = 0.5
                currentTemplateValues[(x + 1) * 16 + y] = 0.5
            }
        }
        let previousTemplate = MassTemplate(
            flat: previousTemplateValues,
            height: 16,
            width: 16,
            mass: previousTemplateValues.reduce(0, +),
            support: 4,
            centerRow: 7.5,
            centerCol: 7.5
        )
        let currentTemplate = MassTemplate(
            flat: currentTemplateValues,
            height: 16,
            width: 16,
            mass: currentTemplateValues.reduce(0, +),
            support: 4,
            centerRow: 8.5,
            centerCol: 7.5
        )
        let matchingSequence = previousTemplateValues + currentTemplateValues
        let staticSequence = previousTemplateValues + previousTemplateValues
        let previous = MassBatchCPU(
            flat: Array(matchingSequence[0..<(16 * 16)]) + Array(staticSequence[0..<(16 * 16)]),
            batch: 2,
            height: 16,
            width: 16,
            sampleSize: 16 * 16
        )
        let current = MassBatchCPU(
            flat: Array(matchingSequence[(16 * 16)..<matchingSequence.count]) +
                Array(staticSequence[(16 * 16)..<staticSequence.count]),
            batch: 2,
            height: 16,
            width: 16,
            sampleSize: 16 * 16
        )

        let mismatches = computeTemplateChangeMismatchBatch(
            previous: previous,
            current: current,
            previousTemplate: previousTemplate,
            currentTemplate: currentTemplate,
            threshold: 0.03
        )

        XCTAssertEqual(mismatches[0], 0, accuracy: 1e-6)
        XCTAssertEqual(mismatches[1], 1, accuracy: 1e-6)
    }

    func testTemplateDeltaSimilarityRejectsStaticSequenceClone() throws {
        var previousTemplateValues = [Float](repeating: 0.0, count: 16 * 16)
        var currentTemplateValues = [Float](repeating: 0.0, count: 16 * 16)
        for x in 7..<9 {
            for y in 7..<9 {
                previousTemplateValues[x * 16 + y] = 0.5
                currentTemplateValues[(x + 1) * 16 + y] = 0.5
            }
        }
        let previousTemplate = MassTemplate(
            flat: previousTemplateValues,
            height: 16,
            width: 16,
            mass: previousTemplateValues.reduce(0, +),
            support: 4,
            centerRow: 7.5,
            centerCol: 7.5
        )
        let currentTemplate = MassTemplate(
            flat: currentTemplateValues,
            height: 16,
            width: 16,
            mass: currentTemplateValues.reduce(0, +),
            support: 4,
            centerRow: 8.5,
            centerCol: 7.5
        )
        let previous = MassBatchCPU(
            flat: previousTemplateValues + previousTemplateValues,
            batch: 2,
            height: 16,
            width: 16,
            sampleSize: 16 * 16
        )
        let current = MassBatchCPU(
            flat: currentTemplateValues + previousTemplateValues,
            batch: 2,
            height: 16,
            width: 16,
            sampleSize: 16 * 16
        )

        let similarities = computeTemplateDeltaSimilarityBatch(
            previous: previous,
            current: current,
            previousTemplate: previousTemplate,
            currentTemplate: currentTemplate,
            threshold: 0.03,
            useTorus: false
        )

        XCTAssertGreaterThan(similarities[0], 0.99)
        XCTAssertEqual(similarities[1], 0, accuracy: 1e-6)
    }

    func testTemplateSignedDeltaSimilarityRejectsStaticAndReversedSequence() throws {
        var previousTemplateValues = [Float](repeating: 0.0, count: 16 * 16)
        var currentTemplateValues = [Float](repeating: 0.0, count: 16 * 16)
        for row in 7..<9 {
            for col in 7..<9 {
                previousTemplateValues[row * 16 + col] = 0.5
                currentTemplateValues[(row + 1) * 16 + col] = 0.5
            }
        }
        let previousTemplate = MassTemplate(
            flat: previousTemplateValues,
            height: 16,
            width: 16,
            mass: previousTemplateValues.reduce(0, +),
            support: 4,
            centerRow: 7.5,
            centerCol: 7.5
        )
        let currentTemplate = MassTemplate(
            flat: currentTemplateValues,
            height: 16,
            width: 16,
            mass: currentTemplateValues.reduce(0, +),
            support: 4,
            centerRow: 8.5,
            centerCol: 7.5
        )
        let previous = MassBatchCPU(
            flat: previousTemplateValues + previousTemplateValues + currentTemplateValues,
            batch: 3,
            height: 16,
            width: 16,
            sampleSize: 16 * 16
        )
        let current = MassBatchCPU(
            flat: currentTemplateValues + previousTemplateValues + previousTemplateValues,
            batch: 3,
            height: 16,
            width: 16,
            sampleSize: 16 * 16
        )

        let similarities = computeTemplateSignedDeltaSimilarityBatch(
            previous: previous,
            current: current,
            previousTemplate: previousTemplate,
            currentTemplate: currentTemplate,
            threshold: 0.03,
            useTorus: false
        )

        XCTAssertGreaterThan(similarities[0], 0.99)
        XCTAssertEqual(similarities[1], 0, accuracy: 1e-6)
        XCTAssertEqual(similarities[2], 0, accuracy: 1e-6)
    }

    func testEvolutionParamSpaceSupportsFourRadialKernelEntries() throws {
        let ranges: [String: (Float, Float)] = [
            "r": (0.1, 1.0),
            "b": (0.0, 1.0),
            "w": (0.0, 1.0),
            "a": (0.0, 1.0),
            "m": (0.0, 1.0),
            "s": (0.01, 0.2),
            "h": (0.0, 1.0),
            "R": (1.0, 40.0),
        ]
        let params = ResolvedParams(
            r: [0.5],
            b: [[1.0, 0.5, 0.33333334, 0.41666666]],
            w: [[0.2, 0.2, 0.2, 0.2]],
            a: [[0.5, 0.5, 0.5, 0.5]],
            m: [0.22],
            s: [0.022],
            h: [0.1],
            R: 36.0,
            seed: 0
        )
        let space = ParamSpace(nbK: 1, ranges: ranges, radialParamCount: 4)

        let vector = paramsToVector(params, space: space)
        let decoded = vectorToParams(vector, space: space)

        XCTAssertEqual(space.radialParamCount, 4)
        XCTAssertEqual(space.slices["b"]?.shape, [1, 4])
        XCTAssertEqual(decoded.b[0].count, 4)
        XCTAssertEqual(decoded.w[0].count, 4)
        XCTAssertEqual(decoded.a[0].count, 4)
        XCTAssertEqual(decoded.b[0][3], params.b[0][3], accuracy: 1e-5)
    }

    func testInternalStripeContrastDetectsInteriorRidges() throws {
        let width = 8
        let height = 8
        var smooth = [Float](repeating: 0, count: width * height)
        var striped = [Float](repeating: 0, count: width * height)
        for y in 1..<7 {
            for x in 1..<7 {
                smooth[y * width + x] = 0.5
                striped[y * width + x] = (x + y).isMultiple(of: 2) ? 0.9 : 0.1
            }
        }
        let materialized = MassBatchCPU(
            flat: smooth + striped,
            batch: 2,
            height: height,
            width: width,
            sampleSize: width * height
        )

        let scores = computeInternalStripeContrastBatch(
            materialized: materialized,
            threshold: 0.03,
            useTorus: false
        )

        XCTAssertEqual(scores[0], 0, accuracy: 1e-6)
        XCTAssertGreaterThan(scores[1], 0.3)
    }

    func testOrientedRidgeDominanceDetectsLongBrightLines() throws {
        let width = 16
        let height = 16
        var filled = [Float](repeating: 0, count: width * height)
        var ridge = [Float](repeating: 0, count: width * height)
        var spot = [Float](repeating: 0, count: width * height)
        for y in 3..<13 {
            for x in 3..<13 {
                filled[y * width + x] = 0.5
                ridge[y * width + x] = 0.35
            }
        }
        for i in 3..<13 {
            ridge[i * width + i] = 1.0
        }
        spot[8 * width + 8] = 1.0
        let materialized = MassBatchCPU(
            flat: filled + ridge + spot,
            batch: 3,
            height: height,
            width: width,
            sampleSize: width * height
        )

        let scores = computeOrientedRidgeDominanceBatch(
            materialized: materialized,
            threshold: 0.03
        )

        XCTAssertLessThan(scores[0], 0.2)
        XCTAssertGreaterThan(scores[1], 0.8)
        XCTAssertLessThan(scores[2], 0.2)
    }

    func testLargestComponentStripeMetricsIgnoreSmallStripedComponents() throws {
        let width = 16
        let height = 16
        var largeSmoothSmallStriped = [Float](repeating: 0, count: width * height)
        var largeStripedSmallSmooth = [Float](repeating: 0, count: width * height)

        for y in 2..<10 {
            for x in 2..<10 {
                largeSmoothSmallStriped[y * width + x] = 0.5
                largeStripedSmallSmooth[y * width + x] = (x + y).isMultiple(of: 2) ? 0.9 : 0.1
            }
        }
        for y in 12..<15 {
            for x in 12..<15 {
                largeSmoothSmallStriped[y * width + x] = (x + y).isMultiple(of: 2) ? 0.9 : 0.1
                largeStripedSmallSmooth[y * width + x] = 0.5
            }
        }
        let materialized = MassBatchCPU(
            flat: largeSmoothSmallStriped + largeStripedSmallSmooth,
            batch: 2,
            height: height,
            width: width,
            sampleSize: width * height
        )

        let largestStripe = computeLargestComponentInternalStripeContrastBatch(
            materialized: materialized,
            threshold: 0.03,
            useTorus: false
        )

        XCTAssertLessThan(largestStripe[0], 0.05)
        XCTAssertGreaterThan(largestStripe[1], 0.3)
    }

    func testLargestComponentStripeMetricsExportAsCodableFields() throws {
        let metrics = SimulationMetrics(
            massMean: 1.0,
            massStd: 0.1,
            massMin: 0.9,
            massMax: 1.1,
            occupancyMean: 0.08,
            varianceMean: 0.02,
            energyMean: 0.03,
            speedMean: 0.01,
            pathLength: 10.0,
            displacement: 9.8,
            sampleCount: 16,
            speedCount: 16,
            gyration: 120.0,
            centerVelocity: 0.012,
            isStable: true,
            largestComponentInternalStripe: 0.125,
            largestComponentOrientedRidge: 0.25
        )
        let decodedMetrics = try JSONDecoder().decode(
            SimulationMetrics.self,
            from: JSONEncoder().encode(metrics)
        )

        XCTAssertEqual(try XCTUnwrap(decodedMetrics.largestComponentInternalStripe), 0.125, accuracy: 1e-6)
        XCTAssertEqual(try XCTUnwrap(decodedMetrics.largestComponentOrientedRidge), 0.25, accuracy: 1e-6)

        let terminal = MorphospaceTerminalDescriptor(
            massChannel: 0,
            borderMode: "torus",
            symmetryPolicy: "translation_kernel_permutation_v1",
            fingerprintResolution: 32,
            fingerprintU8: Data(repeating: 3, count: 32 * 32),
            angularSymmetry: MorphospaceAngularSymmetryDescriptor(
                binCount: 32,
                maxOrder: 8,
                harmonics: [0.05, 0.15, 0.75, 0.1, 0.0, 0.0, 0.0, 0.0],
                dominantOrder: 3,
                dominantAmplitude: 0.75,
                normalizedEntropy: 0.28
            ),
            fingerprintHash12: "1234abcd5678",
            finalMass: 1.2,
            finalOccupancy: 0.18,
            finalGyration: 4.5,
            momentMass: nil,
            momentVolume: nil,
            momentDensity: nil,
            momentAnisotropy: nil,
            componentCount: 1,
            largestComponentFraction: 1,
            largestComponentAnisotropy: 0.42,
            largestComponentInternalStripe: 0.125,
            largestComponentOrientedRidge: 0.25,
            hu1: nil,
            hu2: nil,
            hu3: nil,
            hu4: nil,
            hu5: nil,
            hu6: nil,
            hu7: nil,
            flusser1: nil,
            flusser2: nil,
            flusser3: nil,
            flusser4: nil,
            windowMassStd: nil,
            windowOccupancyStd: nil,
            windowGyrationStd: nil,
            isStable: true
        )
        let decodedTerminal = try JSONDecoder().decode(
            MorphospaceTerminalDescriptor.self,
            from: JSONEncoder().encode(terminal)
        )

        XCTAssertEqual(try XCTUnwrap(decodedTerminal.largestComponentInternalStripe), 0.125, accuracy: 1e-6)
        XCTAssertEqual(try XCTUnwrap(decodedTerminal.largestComponentOrientedRidge), 0.25, accuracy: 1e-6)
    }

    func testOrientationPhaseMotionDetectsAxialRotation() throws {
        func frame(_ fill: (inout [Float]) -> Void) -> MassBatchCPU {
            let width = 16
            let height = 16
            var flat = [Float](repeating: 0, count: width * height)
            fill(&flat)
            return MassBatchCPU(flat: flat, batch: 1, height: height, width: width, sampleSize: width * height)
        }

        let horizontal = frame { flat in
            for col in 4..<12 {
                flat[8 * 16 + col] = 1.0
            }
        }
        let vertical = frame { flat in
            for row in 4..<12 {
                flat[row * 16 + 8] = 1.0
            }
        }

        let moving = computeOrientationPhaseMotionBatch(
            materialized: [horizontal, vertical],
            threshold: 0.03
        )
        let staticScore = computeOrientationPhaseMotionBatch(
            materialized: [horizontal, horizontal],
            threshold: 0.03
        )

        XCTAssertGreaterThan(moving[0], 0.95)
        XCTAssertLessThan(staticScore[0], 0.01)
    }

    func testAngularPhaseMotionDetectsSectorRotation() throws {
        func spokeFrame(rotation: Float) -> MassBatchCPU {
            let width = 33
            let height = 33
            let center = 16
            var flat = [Float](repeating: 0, count: width * height)
            for arm in 0..<4 {
                let angle = rotation + Float(arm) * Float.pi / 2
                for radius in 3...12 {
                    let x = center + Int(round(cos(angle) * Float(radius)))
                    let y = center + Int(round(sin(angle) * Float(radius)))
                    flat[y * width + x] = 1.0
                }
            }
            return MassBatchCPU(flat: flat, batch: 1, height: height, width: width, sampleSize: width * height)
        }

        let initial = spokeFrame(rotation: 0)
        let rotated = spokeFrame(rotation: Float.pi / 4)
        let moving = computeAngularPhaseMotionBatch(
            materialized: [initial, rotated],
            threshold: 0.03,
            order: 4,
            minimumAmplitude: 0.05
        )
        let staticScore = computeAngularPhaseMotionBatch(
            materialized: [initial, initial],
            threshold: 0.03,
            order: 4,
            minimumAmplitude: 0.05
        )

        XCTAssertGreaterThan(moving[0], 0.8)
        XCTAssertLessThan(staticScore[0], 0.01)
    }

    func testSectorTransportDetectsCoherentSectorShift() throws {
        func sectorFrame(rotation: Float) -> MassBatchCPU {
            let width = 33
            let height = 33
            let center = 16
            var flat = [Float](repeating: 0, count: width * height)
            for arm in 0..<4 {
                let angle = rotation + Float(arm) * Float.pi / 2
                for radius in 4...12 {
                    let x = center + Int(round(cos(angle) * Float(radius)))
                    let y = center + Int(round(sin(angle) * Float(radius)))
                    flat[y * width + x] = 1.0
                }
            }
            return MassBatchCPU(flat: flat, batch: 1, height: height, width: width, sampleSize: width * height)
        }

        let initial = sectorFrame(rotation: 0)
        let rotated = sectorFrame(rotation: Float.pi / 4)
        let moving = computeSectorTransportMotionBatch(
            materialized: [initial, rotated],
            threshold: 0.03,
            binCount: 48,
            minimumContrast: 0.05
        )
        let staticScore = computeSectorTransportMotionBatch(
            materialized: [initial, initial],
            threshold: 0.03,
            binCount: 48,
            minimumContrast: 0.05
        )

        XCTAssertGreaterThan(moving[0], 0.15)
        XCTAssertLessThan(staticScore[0], 0.01)
    }

    func testTemplateSimilarityTracksTranslatedShape() throws {
        let width = 10
        let height = 10
        var patchValues = [Float](repeating: 0, count: 4 * 4)
        patchValues[1 * 4 + 1] = 1.0
        patchValues[1 * 4 + 2] = 0.8
        patchValues[2 * 4 + 1] = 0.5

        let statePatch = InitStatePatchConfig(
            center: [5, 5],
            width: 4,
            height: 4,
            channels: 1,
            values: patchValues
        )
        let template = makeStatePatchMassTemplate(
            statePatch: statePatch,
            gridHeight: height,
            gridWidth: width,
            includedChannels: [0],
            threshold: 0.03
        )

        var identical = [Float](repeating: 0, count: width * height)
        var shifted = [Float](repeating: 0, count: width * height)
        var unrelated = [Float](repeating: 0, count: width * height)
        for row in 0..<height {
            for col in 0..<width {
                let value = template.flat[row * width + col]
                identical[row * width + col] = value
                if row + 2 < height && col + 1 < width {
                    shifted[(row + 2) * width + col + 1] = value
                }
            }
        }
        unrelated[7 * width + 7] = 1

        let materialized = MassBatchCPU(
            flat: identical + shifted + unrelated,
            batch: 3,
            height: height,
            width: width,
            sampleSize: width * height
        )
        let scores = computeTemplateSimilarityBatch(
            materialized: materialized,
            template: template,
            threshold: 0.03,
            useTorus: false
        )

        XCTAssertEqual(scores[0], 1, accuracy: 1e-6)
        XCTAssertEqual(scores[1], 1, accuracy: 1e-6)
        XCTAssertLessThan(scores[2], 0.5)
    }

    func testFlowLenia2022ColabParamEmbeddingInitIsPatchConstant() throws {
        let connectivity = [[1]]
        let (c0, c1) = connFromMatrix(connectivity)
        let params = ResolvedParams(
            r: [0.5],
            b: [[1.0, 0.0, 0.0]],
            w: [[0.2, 0.2, 0.2]],
            a: [[0.5, 0.5, 0.5]],
            m: [0.15],
            s: [0.05],
            h: [0.5],
            R: 6.0,
            seed: 0
        )
        let runtimeConfig = LeniaRuntimeConfig(
            backend: .mlx,
            sx: 64,
            sy: 64,
            channels: 1,
            nbK: c0.count,
            profile: .colab,
            c0: c0,
            c1: c1,
            dt: 0.2,
            dd: 5,
            sigma: 0.65,
            n: 2,
            thetaA: 2.0,
            border: "torus",
            implementation: ImplementationSettings(
                mode: "flowlenia_2022_colab",
                border: "torus",
                gradientBoundary: "periodic",
                alphaMode: "per_channel",
                kernelProfile: "flowlenia_2022_colab",
                flowClip: "params_only"
            ),
            params: params,
            initSeed: 0,
            patches: [PatchConfig(center: [32, 32], size: 40)],
            aUniform: UniformRange(low: 0.0, high: 1.0),
            pUniform: UniformRange(low: 0.0, high: 1.0),
            steps: 10,
            parameterEmbedding: ParameterEmbeddingConfig(enabled: true, mix: "stoch", mix_seed: nil),
            chemotaxis: nil,
            food: nil,
            walls: nil,
            interventions: []
        )
        let initializationBuilder = makeSearchInitializationBuilder(runtimeConfig: runtimeConfig)
        XCTAssertTrue(initializationBuilder.constantPerPatchParameters)
        let P = try XCTUnwrap(initializationBuilder.buildInitialParameterState(seed: 123))
        eval(P)
        let data = P.flattened().asArray(Float.self)

        let patch = runtimeConfig.patches[0]
        let half = patch.size / 2
        let x0 = patch.center[0] - half
        let x1 = patch.center[0] + (patch.size - half)
        let y0 = patch.center[1] - half
        let y1 = patch.center[1] + (patch.size - half)

        for k in 0..<runtimeConfig.nbK {
            let refIdx = ((x0 * runtimeConfig.sy) + y0) * runtimeConfig.nbK + k
            let ref = data[refIdx]
            for x in x0..<x1 {
                for y in y0..<y1 {
                    let idx = ((x * runtimeConfig.sy) + y) * runtimeConfig.nbK + k
                    XCTAssertEqual(data[idx], ref, accuracy: 1e-6)
                }
            }
        }
    }

    func testFlowLenia2022ColabParamEmbeddingInitIsPatchConstantOutsidePaperProfile() throws {
        let patches = [
            PatchConfig(center: [16, 16], size: 12),
            PatchConfig(center: [48, 48], size: 12),
        ]
        let runtimeConfig = makeRuntimeConfigForSearchEngine(
            sx: 64,
            sy: 64,
            channels: 2,
            parameterEmbedding: ParameterEmbeddingConfig(enabled: true, mix: "stoch", mix_seed: nil),
            pUniform: UniformRange(low: 0.0, high: 1.0),
            chemotaxis: nil,
            profile: .colab,
            implementationMode: "flowlenia_2022_colab",
            patches: patches
        )
        let initializationBuilder = makeSearchInitializationBuilder(runtimeConfig: runtimeConfig)
        XCTAssertTrue(initializationBuilder.constantPerPatchParameters)
        let P = try XCTUnwrap(initializationBuilder.buildInitialParameterState(seed: 321))
        eval(P)
        let data = P.flattened().asArray(Float.self)

        for patch in runtimeConfig.patches {
            let half = patch.size / 2
            let x0 = patch.center[0] - half
            let x1 = patch.center[0] + (patch.size - half)
            let y0 = patch.center[1] - half
            let y1 = patch.center[1] + (patch.size - half)

            for k in 0..<runtimeConfig.nbK {
                let refIdx = ((x0 * runtimeConfig.sy) + y0) * runtimeConfig.nbK + k
                let ref = data[refIdx]
                for x in x0..<x1 {
                    for y in y0..<y1 {
                        let idx = ((x * runtimeConfig.sy) + y) * runtimeConfig.nbK + k
                        XCTAssertEqual(data[idx], ref, accuracy: 1e-6)
                    }
                }
            }
        }
    }

    func testChemotaxisFieldMatchesGaussianRandomOnCircle() throws {
        let sx = 64
        let sy = 64
        let center = [Float(sx) / 2.0, Float(sy) / 2.0]
        let chemConfig = ChemotaxisConfig(
            enabled: true,
            channel_index: 1,
            mode: "random_on_circle",
            sigma: 3.0,
            amplitude: 2.0,
            include_in_mass: false,
            center: center,
            circle_radius: 7.0,
            seed: 42
        )
        let runtimeConfig = makeRuntimeConfigForSearchEngine(
            sx: sx,
            sy: sy,
            channels: 2,
            parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
            pUniform: nil,
            chemotaxis: chemConfig
        )
        let initializationBuilder = makeSearchInitializationBuilder(runtimeConfig: runtimeConfig)
        let field = try XCTUnwrap(initializationBuilder.runtimeChemotaxisField())
            .squeezed(axis: 0)
            .squeezed(axis: 2)
        eval(field)

        var rng = SeededRandomNumberGenerator(seed: UInt64(chemConfig.seed ?? 0))
        let angle = Float.random(in: 0...(2 * Float.pi), using: &rng)
        let cx = center[0] + (chemConfig.circle_radius ?? 0.0) * cos(angle)
        let cy = center[1] + (chemConfig.circle_radius ?? 0.0) * sin(angle)

        let xi = max(0, min(sx - 1, Int(round(cx))))
        let yi = max(0, min(sy - 1, Int(round(cy))))
        let dx = Float(xi) - cx
        let dy = Float(yi) - cy
        let distSq = dx * dx + dy * dy
        let expected = chemConfig.amplitude * exp(-distSq / (2.0 * chemConfig.sigma * chemConfig.sigma))

        let values = field.flattened().asArray(Float.self)
        let actual = values[xi * sy + yi]
        XCTAssertEqual(actual, expected, accuracy: 1e-5)
    }

    func testFlowGradientComponentOrdering() {
        let sx = 7
        let sy = 7
        let channels = 1
        let nbK = 1

        let fK = MLX.zeros([1, sx, sy, nbK])
        let m = MLXArray([Float(0.0)])
        let s = MLXArray([Float(1.0)])
        let h = MLXArray([Float(0.0)])
        let c0Idxs = MLXArray([Int32(0)])
        let c1Mask = MLXArray([Float(1.0)]).reshaped([channels, nbK])

        func makeRamp(axis: Int) -> MLXArray {
            var data = [Float](repeating: 0.0, count: sx * sy * channels)
            for x in 0..<sx {
                for y in 0..<sy {
                    let value = axis == 0 ? Float(x) : Float(y)
                    let idx = (x * sy + y) * channels
                    data[idx] = value
                }
            }
            return MLXArray(data).reshaped([1, sx, sy, channels])
        }

        let thetaA: Float = 1e-3
        let F_x = computeFlow(
            makeRamp(axis: 0),
            fK: fK,
            m: m,
            s: s,
            h: h,
            c0Idxs: c0Idxs,
            c1Mask: c1Mask,
            thetaA: thetaA,
            n: 1,
            gradientBoundary: "zero_pad",
            alphaMode: "mass",
            flowClip: "none",
            chemChannel: nil,
            chemIncludeInMass: true,
            dd: 2,
            sigma: 0.65
        ).squeezed(axis: 0)

        let interiorX = 1..<(sx - 1)
        let interiorY = 1..<(sy - 1)
        let fxY = F_x[interiorX, interiorY, 0, 0].mean()
        let fxX = F_x[interiorX, interiorY, 1, 0].mean()
        eval(fxY, fxX)
        let fxYVal = fxY.asArray(Float.self)[0]
        let fxXVal = fxX.asArray(Float.self)[0]

        XCTAssertGreaterThan(abs(fxYVal), 1e-3)
        XCTAssertLessThan(abs(fxXVal), 1e-3)

        let F_y = computeFlow(
            makeRamp(axis: 1),
            fK: fK,
            m: m,
            s: s,
            h: h,
            c0Idxs: c0Idxs,
            c1Mask: c1Mask,
            thetaA: thetaA,
            n: 1,
            gradientBoundary: "zero_pad",
            alphaMode: "mass",
            flowClip: "none",
            chemChannel: nil,
            chemIncludeInMass: true,
            dd: 2,
            sigma: 0.65
        ).squeezed(axis: 0)

        let fyY = F_y[interiorX, interiorY, 0, 0].mean()
        let fyX = F_y[interiorX, interiorY, 1, 0].mean()
        eval(fyY, fyX)
        let fyYVal = fyY.asArray(Float.self)[0]
        let fyXVal = fyX.asArray(Float.self)[0]

        XCTAssertGreaterThan(abs(fyXVal), 1e-3)
        XCTAssertLessThan(abs(fyYVal), 1e-3)
    }

    func testSurvivalStepsTracking() {
        let runtimeConfig = makeRuntimeConfigForSearchEngine(
            channels: 1,
            parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
            pUniform: nil,
            chemotaxis: nil
        )
        let engine = SearchEngine(runtimeConfig: runtimeConfig)

        let baseConfig = { (kSurvival: KSurvivalConfig?) in
            SearchConfig(
                steps: 10,
                recordInterval: 1,
                warmupSteps: 0,
                occupancyThreshold: 0.0,
                massChannel: -1,
                scoreWeights: [:],
                filters: [:],
                complexity: nil,
                activity: nil,
                stability: nil,
                kSurvival: kSurvival
            )
        }

        let noTracking = engine.runBatch(
            seeds: [42], initSeedOffset: 0,
            searchConfig: baseConfig(nil)
        )
        XCTAssertNil(noTracking[0].metrics.survivalSteps)
        XCTAssertFalse(noTracking[0].metrics.survivalTracked)

        let survives = engine.runBatch(
            seeds: [42], initSeedOffset: 0,
            searchConfig: baseConfig(KSurvivalConfig(enabled: true, deathThreshold: 0.001))
        )
        XCTAssertNil(survives[0].metrics.survivalSteps)
        XCTAssertTrue(survives[0].metrics.survivalTracked)

        let diesImmediately = engine.runBatch(
            seeds: [42], initSeedOffset: 0,
            searchConfig: baseConfig(KSurvivalConfig(enabled: true, deathThreshold: 1e6))
        )
        XCTAssertEqual(diesImmediately[0].metrics.survivalSteps, 1)
        XCTAssertTrue(diesImmediately[0].metrics.survivalTracked)
    }

    func testActivityMetricsComputedWhenOnlyScoreWeightsUseActivity() {
        let runtimeConfig = makeRuntimeConfigForSearchEngine(
            channels: 1,
            parameterEmbedding: ParameterEmbeddingConfig(enabled: true, mix: "avg", mix_seed: nil),
            pUniform: UniformRange(low: 0.0, high: 1.0),
            chemotaxis: nil
        )
        let engine = SearchEngine(runtimeConfig: runtimeConfig)

        let activityConfig = ActivityConfig(
            enabled: true,
            interval: 1,
            threshold: 0.0,
            maxComponents: nil,
            matchThreshold: 0.01,
            paramWeight: 1.0,
            positionWeight: 1.0
        )
        let searchConfig = SearchConfig(
            steps: 12,
            recordInterval: 1,
            warmupSteps: 0,
            occupancyThreshold: 0.0,
            massChannel: -1,
            scoreWeights: ["activity_ean_mean": 1.0],
            filters: [:],
            complexity: nil,
            activity: activityConfig,
            stability: nil
        )

        let results = engine.runBatch(seeds: [42], initSeedOffset: 0, searchConfig: searchConfig)
        XCTAssertEqual(results.count, 1)
        XCTAssertNotNil(results[0].metrics.activityEacMean)
        XCTAssertNotNil(results[0].metrics.activityEanMean)
        XCTAssertNotNil(results[0].metrics.activityDiversityMean)
        XCTAssertNotNil(results[0].metrics.activitySpeciesMean)
    }

    func testSearchEngineComputesComplexityAndMomentsTogether() {
        let runtimeConfig = makeRuntimeConfigForSearchEngine(
            channels: 1,
            parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
            pUniform: nil,
            chemotaxis: nil
        )
        let engine = SearchEngine(runtimeConfig: runtimeConfig)

        let searchConfig = SearchConfig(
            steps: 8,
            recordInterval: 2,
            warmupSteps: 0,
            occupancyThreshold: 0.0,
            massChannel: -1,
            scoreWeights: [:],
            filters: [:],
            complexity: ComplexityConfig(enabled: true, scales: [0], target: nil, polar: false, backend: "zlib"),
            activity: nil,
            stability: nil,
            moments: MomentsConfig(enabled: true, threshold: 0.01)
        )

        let metrics = engine.runBatch(seeds: [42], initSeedOffset: 0, searchConfig: searchConfig)[0].metrics
        XCTAssertNotNil(metrics.complexityMean)
        XCTAssertEqual(metrics.complexityScales?.count, 1)
        XCTAssertNotNil(metrics.hu1)
        XCTAssertNotNil(metrics.flusser1)
        XCTAssertNotNil(metrics.momentMass)
        XCTAssertNotNil(metrics.momentVolume)
        XCTAssertNotNil(metrics.momentDensity)
        XCTAssertNotNil(metrics.momentAnisotropy)
    }

    func testMomentAnisotropyDistinguishesLineFromBlob() {
        let width = 8
        let height = 8
        var line = [Float](repeating: 0, count: width * height)
        var blob = [Float](repeating: 0, count: width * height)

        for x in 1...6 {
            line[3 * width + x] = 1.0
        }
        for y in 3...4 {
            for x in 3...4 {
                blob[y * width + x] = 1.0
            }
        }

        let batch = MLXArray(line + blob).reshaped([2, height, width])
        let result = computeMomentsBatch(massMap: batch, config: MomentsConfig(enabled: true, threshold: 0.01))

        XCTAssertEqual(result.anisotropy.count, 2)
        XCTAssertGreaterThan(result.anisotropy[0], 0.95)
        XCTAssertLessThan(result.anisotropy[1], 0.1)
    }

    func testSpeedCountTracksRecordedIntervals() {
        let runtimeConfig = makeRuntimeConfigForSearchEngine(
            channels: 1,
            parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
            pUniform: nil,
            chemotaxis: nil
        )
        let engine = SearchEngine(runtimeConfig: runtimeConfig)

        let searchConfig = SearchConfig(
            steps: 10,
            recordInterval: 2,
            warmupSteps: 0,
            occupancyThreshold: 0.0,
            massChannel: -1,
            scoreWeights: [:],
            filters: [:],
            complexity: nil,
            activity: nil,
            stability: nil
        )

        let result = engine.runBatch(seeds: [42], initSeedOffset: 0, searchConfig: searchConfig)[0].metrics
        XCTAssertEqual(result.sampleCount, 5)
        XCTAssertEqual(result.speedCount, 4)
        XCTAssertGreaterThanOrEqual(result.speedMean, result.centerVelocity)
    }

    func testKSurvivalEvaluation() {
        let runtimeConfig = makeRuntimeConfigForSearchEngine(
            channels: 1,
            parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
            pUniform: nil,
            chemotaxis: nil
        )

        let steps = 20
        let blindTrials = 3
        let kConfig = KSurvivalConfig(enabled: true, blindTrials: blindTrials, deathThreshold: 1e6)
        let paramRanges = KernelParamRanges(
            r: [0.1, 0.9],
            b: [0.0, 1.0],
            w: [0.05, 0.5],
            a: [0.1, 0.9],
            m: [0.05, 0.3],
            s: [0.01, 0.1],
            h: [0.0, 1.0],
            R: [3.0, 10.0]
        )

        let result = evaluateKSurvival(
            agentSurvivalSteps: steps,
            runtimeConfig: runtimeConfig,
            kConfig: kConfig,
            steps: steps,
            recordInterval: 1,
            warmupSteps: 0,
            initSeed: 42,
            paramRanges: paramRanges
        )

        XCTAssertEqual(result.blindTrialSteps.count, blindTrials)
        XCTAssertEqual(result.tauAgent, steps)

        for trialStep in result.blindTrialSteps {
            XCTAssertEqual(trialStep, 1)
        }
        XCTAssertEqual(result.tauBlindMean, 1.0, accuracy: 1e-6)

        let expectedK = log10(Float(steps))
        XCTAssertEqual(result.k, expectedK, accuracy: 1e-4)
    }

    func testSensorimotor2024PaperConfigsDecode() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let configDirectory = packageRoot.appendingPathComponent("configs/papers/sensorimotor-lenia-2024", isDirectory: true)

        let bundle = try loadSensorimotorLenia2024ConfigBundle(configDirectory: configDirectory)

        XCTAssertEqual(bundle.ruleSpace.grid.sx, 256)
        XCTAssertEqual(bundle.ruleSpace.grid.sy, 256)
        XCTAssertEqual(bundle.ruleSpace.learnableRules.count, 10)
        XCTAssertEqual(bundle.ruleSpace.learnableRules.sharedR.low, 0.0, accuracy: 1e-6)
        XCTAssertEqual(bundle.ruleSpace.learnableRules.sharedR.high, 24.0, accuracy: 1e-6)
        XCTAssertEqual(bundle.ruleSpace.initialization.origin, [105, 180])
        XCTAssertEqual(bundle.ruleSpace.searchEnvironment.obstacleCount, 8)
        XCTAssertEqual(bundle.training.outerSteps, 160)
        XCTAssertEqual(bundle.training.historyInitializationTrials, 40)
        XCTAssertEqual(bundle.training.optimization.stepsUnmutated, 125)
        XCTAssertEqual(bundle.training.optimization.stepsMutated, 15)
        XCTAssertEqual(bundle.training.evaluationAfterStep.rollouts, 20)
        XCTAssertEqual(bundle.evaluation.prefilter.rolloutSteps, 500)
        XCTAssertEqual(bundle.evaluation.basicObstacleTest.rollouts, 50)
        XCTAssertEqual(bundle.evaluation.generalization.scale.count, 5)
    }

    func testSensorimotor2024RunnerCompletesTinySmoke() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let sourceDirectory = packageRoot.appendingPathComponent("configs/papers/sensorimotor-lenia-2024", isDirectory: true)
        let tempRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let configDirectory = tempRoot.appendingPathComponent("configs", isDirectory: true)
        let outputDirectory = tempRoot.appendingPathComponent("output", isDirectory: true)
        try FileManager.default.createDirectory(at: configDirectory, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempRoot) }

        for filename in ["rule_space_and_init.json", "train_curriculum.json", "evaluation_battery.json"] {
            try FileManager.default.copyItem(
                at: sourceDirectory.appendingPathComponent(filename),
                to: configDirectory.appendingPathComponent(filename)
            )
        }

        try rewriteJSONFile(at: configDirectory.appendingPathComponent("train_curriculum.json")) { root in
            root["outer_steps"] = 2
            root["history_initialization_trials"] = 1
            root["rollout_steps"] = 8
            var optimization = root["optimization"] as! [String: Any]
            optimization["steps_unmutated"] = 1
            optimization["steps_mutated"] = 1
            root["optimization"] = optimization
            var restart = root["restart"] as! [String: Any]
            restart["max_attempts"] = 1
            restart["min_alive_random_initializations"] = 0
            restart["max_loss"] = 1000.0
            root["restart"] = restart
            var evaluationAfterStep = root["evaluation_after_step"] as! [String: Any]
            evaluationAfterStep["rollouts"] = 1
            root["evaluation_after_step"] = evaluationAfterStep
        }

        try rewriteJSONFile(at: configDirectory.appendingPathComponent("evaluation_battery.json")) { root in
            var prefilter = root["prefilter"] as! [String: Any]
            prefilter["rollout_steps"] = 20
            root["prefilter"] = prefilter

            var moving = root["moving"] as! [String: Any]
            moving["window_end"] = 20
            moving["speed_start"] = 10
            root["moving"] = moving

            var agency = root["agency"] as! [String: Any]
            agency["rollout_steps"] = 24
            agency["mass_window_a"] = [0, 8]
            agency["mass_window_b"] = [16, 24]
            root["agency"] = agency

            var basicObstacleTest = root["basic_obstacle_test"] as! [String: Any]
            basicObstacleTest["rollouts"] = 1
            basicObstacleTest["rollout_steps"] = 24
            basicObstacleTest["forced_obstacle_reference_step"] = 12
            root["basic_obstacle_test"] = basicObstacleTest

            var generalization = root["generalization"] as! [String: Any]
            generalization["trials_per_setting"] = 1
            generalization["obstacle_radius"] = [10]
            generalization["obstacle_count"] = [24]
            generalization["obstacle_speed"] = [1.0]
            generalization["update_mask_rate"] = [1.0]
            generalization["update_noise_std"] = [1.0]
            generalization["update_noise_rate"] = [1.0]
            generalization["init_noise_rate"] = [1.0]
            generalization["init_noise_std"] = [1.0]
            generalization["scale"] = [1.0]
            root["generalization"] = generalization
        }

        let bundle = try loadSensorimotorLenia2024ConfigBundle(configDirectory: configDirectory)
        let runner = SensorimotorLenia2024Runner(
            configs: bundle,
            logger: Logger(label: "LeniaCoreTests.Sensorimotor2024")
        )
        let summary = try runner.run(seed: 7, outputDirectory: outputDirectory, runId: "test-sensorimotor-2024")

        XCTAssertGreaterThan(summary.historyCount, 0)
        XCTAssertEqual(summary.bestEvaluation.scenarios.count, 9)
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("library/index.jsonl").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("history.jsonl").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("summary.json").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("best.json").path))
    }

    func testAtlas2026PaperConfigsDecode() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let configDirectory = packageRoot.appendingPathComponent("configs/papers/lenia-atlas-2026", isDirectory: true)

        let bundle = try loadAtlas2026ConfigBundle(configDirectory: configDirectory)

        XCTAssertEqual(bundle.kernel.paper, "lenia-parameter-space-2026")
        XCTAssertEqual(bundle.kernel.arraySize, 100)
        XCTAssertEqual(bundle.kernel.dt, 0.1, accuracy: 1e-6)
        XCTAssertEqual(bundle.kernel.function, "gauss")
        XCTAssertEqual(bundle.kernel.radius, 13)
        XCTAssertEqual(bundle.kernel.betas, [1.0])
        XCTAssertEqual(bundle.kernel.muK, [0.5])
        XCTAssertEqual(bundle.kernel.sigmaK, [0.15])
        XCTAssertEqual(bundle.sweep.batchSize, 64)
        XCTAssertEqual(bundle.sweep.samplesPerPolygon, 64)
        XCTAssertEqual(bundle.sweep.polygonSizes, [10, 20, 30, 40, 50, 60, 70, 80, 90])
        XCTAssertTrue(bundle.sweep.refineTransitions)
        XCTAssertEqual(bundle.classifier.windowSize, 200)
        XCTAssertEqual(bundle.classifier.std, 3.0, accuracy: 1e-6)
        XCTAssertEqual(bundle.classifier.shortTMaxMultiplier, 100)
        XCTAssertEqual(bundle.classifier.longTMaxMultiplier, 1000)
    }

    func testLeniaBreeder2024PaperConfigsDecode() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let configDirectory = packageRoot.appendingPathComponent("configs/papers/leniabreeder-2024", isDirectory: true)

        let bundle = try loadLeniaBreeder2024ConfigBundle(configDirectory: configDirectory)

        XCTAssertEqual(bundle.base.paper, "toward-artificial-open-ended-evolution-within-lenia-using-quality-diversity-2024")
        XCTAssertEqual(bundle.base.patternID, "5N7KKM")
        XCTAssertEqual(bundle.base.worldSize, 128)
        XCTAssertEqual(bundle.base.worldScale, 1)
        XCTAssertEqual(bundle.base.nStep, 200)
        XCTAssertEqual(bundle.base.nParamsSize, 3)
        XCTAssertEqual(bundle.base.nCellsSize, 32)
        XCTAssertEqual(bundle.mapElites.algorithm, "me")
        XCTAssertEqual(bundle.mapElites.phenotypeSize, 64)
        XCTAssertEqual(bundle.mapElites.batchSize, 256)
        XCTAssertEqual(bundle.mapElites.repertoireSize, 1024)
        XCTAssertEqual(bundle.mapElites.initialCVTSamples, 50_000)
        XCTAssertEqual(bundle.mapElites.fitness, "neg_angle_var")
        XCTAssertEqual(bundle.mapElites.descriptor, ["pos_mass_avg", "pos_linear_velocity_avg"])
        XCTAssertEqual(bundle.mapElites.descriptorMin, [0.0, 0.0])
        XCTAssertEqual(bundle.mapElites.descriptorMax, [10.0, 0.5])
        XCTAssertEqual(bundle.mapElites.nKeep, 128)
        XCTAssertEqual(bundle.aurora.algorithm, "aurora")
        XCTAssertEqual(bundle.aurora.phenotypeSize, 32)
        XCTAssertEqual(bundle.aurora.batchSize, 256)
        XCTAssertEqual(bundle.aurora.repertoireSize, 1024)
        XCTAssertEqual(bundle.aurora.fitness, "pos_linear_velocity_avg")
        XCTAssertNil(bundle.aurora.secondaryFitness)
        XCTAssertEqual(bundle.aurora.hiddenSize, 128)
        XCTAssertEqual(bundle.aurora.features, 8)
        XCTAssertEqual(bundle.aurora.trainRatio, 8)
        XCTAssertEqual(bundle.aurora.learningRate, 0.0005, accuracy: 1e-9)
        XCTAssertEqual(bundle.aurora.autoencoderBatchSize, 256)
        XCTAssertEqual(bundle.aurora.nKeepAutoencoder, 128)
        XCTAssertTrue(bundle.aurora.useDataAugmentation)
    }

    func testLeniaBreeder2024VisualizationRuntimeUsesQD24BucketedKernelProfile() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let configDirectory = packageRoot.appendingPathComponent("configs/papers/leniabreeder-2024", isDirectory: true)
        let run = try loadLeniaBreeder2024ResolvedRun(runDirectory: configDirectory)
        let pattern = run.pattern
        let placeholder = pattern.kernels.map { Array(repeating: Float(0), count: $0.b.count) }
        let kernelParams = KernelParams(
            r: pattern.kernels.map(\.r),
            b: pattern.kernels.map(\.b),
            w: placeholder,
            a: placeholder,
            m: pattern.kernels.map(\.m),
            s: pattern.kernels.map(\.s),
            h: pattern.kernels.map(\.h),
            R: Float(pattern.R)
        )

        let runtime = leniaBreeder2024VisualizationRuntimeConfig(run: run, kernelParams: kernelParams)

        XCTAssertEqual(runtime.implementation.kernelProfile, "qd24_bucketed_v1")
        XCTAssertEqual(runtime.params.b, pattern.kernels.map(\.b))
        XCTAssertEqual(runtime.nbK, pattern.kernels.count)
    }

    func testQD24AdditiveImplementationResolvesBucketedKernelProfile() throws {
        let baseConfig = LeniaBaseConfig(
            backend: "mlx",
            profile: .experimental,
            grid: GridConfig(sx: 16, sy: 16),
            channels: 1,
            connectivity: [[1]],
            flow: FlowConfig(dt: 0.2, n: 2, theta_A: 2.0),
            implementation: ImplementationConfig(mode: "qd24_additive_v1"),
            reintegration: ReintegrationConfig(dd: 5, sigma: 0.65, border: "torus"),
            parameter_embedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
            chemotaxis: nil,
            obstacle_field: nil,
            food: nil,
            walls: nil,
            environment: nil,
            beam_mutation: nil,
            params: ParamsConfig(
                mode: "explicit",
                seed: 0,
                ranges: nil,
                r: [0.5],
                b: [[1.0, 0.5]],
                w: [[0.0, 0.0]],
                a: [[0.0, 0.0]],
                m: [0.15],
                s: [0.05],
                h: [0.0],
                R: 6.0
            ),
            init: InitConfig(
                seed: 0,
                patches: [],
                a_uniform: UniformRange(low: 0.0, high: 0.0),
                p_uniform: nil
            ),
            run: RunConfig(steps: 1),
            interventions: nil
        )

        let runtime = try loadRuntimeConfig(from: JSONEncoder().encode(baseConfig))

        XCTAssertEqual(runtime.implementation.mode, "qd24_additive_v1")
        XCTAssertEqual(runtime.implementation.kernelProfile, "qd24_bucketed_v1")
        XCTAssertEqual(runtime.backend, FlowLeniaComputeBackend.mlx)
    }

    func testQD24AdditiveImplementationAllowsNativeKernelCoreProfiles() throws {
        let baseConfig = LeniaBaseConfig(
            backend: "mlx",
            profile: .experimental,
            grid: GridConfig(sx: 16, sy: 16),
            channels: 1,
            connectivity: [[1]],
            flow: FlowConfig(dt: 0.2, n: 2, theta_A: 2.0),
            implementation: ImplementationConfig(mode: "qd24_additive_v1", kernel_profile: "qd24_quad4_v1"),
            reintegration: ReintegrationConfig(dd: 5, sigma: 0.65, border: "torus"),
            parameter_embedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
            chemotaxis: nil,
            obstacle_field: nil,
            food: nil,
            walls: nil,
            environment: nil,
            beam_mutation: nil,
            params: ParamsConfig(
                mode: "explicit",
                seed: 0,
                ranges: nil,
                r: [1.0],
                b: [[1.0, 0.5]],
                w: [[0.0, 0.0]],
                a: [[0.0, 0.0]],
                m: [0.15],
                s: [0.05],
                h: [0.0],
                R: 6.0
            ),
            init: InitConfig(
                seed: 0,
                patches: [],
                a_uniform: UniformRange(low: 0.0, high: 0.0),
                p_uniform: nil
            ),
            run: RunConfig(steps: 1),
            interventions: nil
        )

        let runtime = try loadRuntimeConfig(from: JSONEncoder().encode(baseConfig))

        XCTAssertEqual(runtime.implementation.mode, "qd24_additive_v1")
        XCTAssertEqual(runtime.implementation.kernelProfile, "qd24_quad4_v1")
        XCTAssertEqual(runtime.backend, FlowLeniaComputeBackend.mlx)
    }

    func testQD24AdditiveImplementationAllowsNativeStepKernelAndGrowthProfiles() throws {
        let baseConfig = LeniaBaseConfig(
            backend: "mlx",
            profile: .experimental,
            grid: GridConfig(sx: 16, sy: 16),
            channels: 1,
            connectivity: [[1]],
            flow: FlowConfig(dt: 0.2, n: 2, theta_A: 2.0),
            implementation: ImplementationConfig(
                mode: "qd24_additive_v1",
                kernel_profile: "qd24_step_v1",
                growth_profile: "stpz"
            ),
            reintegration: ReintegrationConfig(dd: 5, sigma: 0.65, border: "torus"),
            parameter_embedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
            chemotaxis: nil,
            obstacle_field: nil,
            food: nil,
            walls: nil,
            environment: nil,
            beam_mutation: nil,
            params: ParamsConfig(
                mode: "explicit",
                seed: 0,
                ranges: nil,
                r: [1.0],
                b: [[1.0]],
                w: [[0.0]],
                a: [[0.0]],
                m: [0.545],
                s: [0.186],
                h: [1.0],
                R: 6.0
            ),
            init: InitConfig(
                seed: 0,
                patches: [],
                a_uniform: UniformRange(low: 0.0, high: 0.0),
                p_uniform: nil
            ),
            run: RunConfig(steps: 1),
            interventions: nil
        )

        let runtime = try loadRuntimeConfig(from: JSONEncoder().encode(baseConfig))

        XCTAssertEqual(runtime.implementation.mode, "qd24_additive_v1")
        XCTAssertEqual(runtime.implementation.kernelProfile, "qd24_step_v1")
        XCTAssertEqual(runtime.implementation.growthProfile, "stpz")
    }

    func testQD24AdditiveImplementationAllowsNativeLifeKernel() throws {
        let baseConfig = LeniaBaseConfig(
            backend: "mlx",
            profile: .experimental,
            grid: GridConfig(sx: 16, sy: 16),
            channels: 1,
            connectivity: [[1]],
            flow: FlowConfig(dt: 1.0, n: 2, theta_A: 2.0),
            implementation: ImplementationConfig(
                mode: "qd24_additive_v1",
                kernel_profile: "qd24_life_v1",
                growth_profile: "stpz"
            ),
            reintegration: ReintegrationConfig(dd: 5, sigma: 0.65, border: "torus"),
            parameter_embedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
            chemotaxis: nil,
            obstacle_field: nil,
            food: nil,
            walls: nil,
            environment: nil,
            beam_mutation: nil,
            params: ParamsConfig(
                mode: "explicit",
                seed: 0,
                ranges: nil,
                r: [1.0],
                b: [[1.0]],
                w: [[0.0]],
                a: [[0.0]],
                m: [0.35],
                s: [0.07],
                h: [1.0],
                R: 2.0
            ),
            init: InitConfig(
                seed: 0,
                patches: [],
                a_uniform: UniformRange(low: 0.0, high: 0.0),
                p_uniform: nil
            ),
            run: RunConfig(steps: 1),
            interventions: nil
        )

        let runtime = try loadRuntimeConfig(from: JSONEncoder().encode(baseConfig))

        XCTAssertEqual(runtime.implementation.mode, "qd24_additive_v1")
        XCTAssertEqual(runtime.implementation.kernelProfile, "qd24_life_v1")
        XCTAssertEqual(runtime.implementation.growthProfile, "stpz")
    }

    func testQD24NativeKernelCoreProfilesChangeSpatialKernel() throws {
        let params = ResolvedParams(
            r: [1.0],
            b: [[1.0, 0.5]],
            w: [[0.0, 0.0]],
            a: [[0.0, 0.0]],
            m: [0.15],
            s: [0.05],
            h: [1.0],
            R: 6.0,
            seed: 0
        )
        let bucketedConfig = BatchedConfig(
            sx: 16,
            sy: 16,
            channels: 1,
            nbK: 1,
            dt: 0.2,
            dd: 5,
            sigma: 0.65,
            n: 2,
            thetaA: 2.0,
            border: "torus",
            implementation: ImplementationSettings(
                mode: "qd24_additive_v1",
                border: "torus",
                gradientBoundary: "periodic",
                alphaMode: "mass",
                kernelProfile: "qd24_bucketed_v1",
                flowClip: "none"
            ),
            chemChannel: nil,
            chemIncludeInMass: true
        )
        let quadConfig = BatchedConfig(
            sx: 16,
            sy: 16,
            channels: 1,
            nbK: 1,
            dt: 0.2,
            dd: 5,
            sigma: 0.65,
            n: 2,
            thetaA: 2.0,
            border: "torus",
            implementation: ImplementationSettings(
                mode: "qd24_additive_v1",
                border: "torus",
                gradientBoundary: "periodic",
                alphaMode: "mass",
                kernelProfile: "qd24_quad4_v1",
                flowClip: "none"
            ),
            chemChannel: nil,
            chemIncludeInMass: true
        )
        let stepConfig = BatchedConfig(
            sx: 16,
            sy: 16,
            channels: 1,
            nbK: 1,
            dt: 0.2,
            dd: 5,
            sigma: 0.65,
            n: 2,
            thetaA: 2.0,
            border: "torus",
            implementation: ImplementationSettings(
                mode: "qd24_additive_v1",
                border: "torus",
                gradientBoundary: "periodic",
                alphaMode: "mass",
                kernelProfile: "qd24_step_v1",
                flowClip: "none"
            ),
            chemChannel: nil,
            chemIncludeInMass: true
        )

        let bucketed = normalizedSpatialKernelStack(params: params, config: bucketedConfig).asArray(Float.self)
        let quad = normalizedSpatialKernelStack(params: params, config: quadConfig).asArray(Float.self)
        let step = normalizedSpatialKernelStack(params: params, config: stepConfig).asArray(Float.self)
        let absoluteDifference = zip(bucketed, quad).map { abs($0 - $1) }.reduce(0, +)
        let stepDifference = zip(bucketed, step).map { abs($0 - $1) }.reduce(0, +)

        XCTAssertGreaterThan(absoluteDifference, 0.05)
        XCTAssertGreaterThan(stepDifference, 0.05)
    }

    func testQD24LifeKernelWeightsCenterAndNeighborShell() throws {
        let params = ResolvedParams(
            r: [1.0],
            b: [[1.0]],
            w: [[0.0]],
            a: [[0.0]],
            m: [0.35],
            s: [0.07],
            h: [1.0],
            R: 2.0,
            seed: 0
        )
        let config = BatchedConfig(
            sx: 9,
            sy: 9,
            channels: 1,
            nbK: 1,
            dt: 1.0,
            dd: 5,
            sigma: 0.65,
            n: 2,
            thetaA: 2.0,
            border: "torus",
            implementation: ImplementationSettings(
                mode: "qd24_additive_v1",
                border: "torus",
                gradientBoundary: "periodic",
                alphaMode: "mass",
                kernelProfile: "qd24_life_v1",
                growthProfile: "stpz",
                flowClip: "none"
            ),
            chemChannel: nil,
            chemIncludeInMass: true
        )

        let kernel = normalizedSpatialKernelStack(params: params, config: config).asArray(Float.self)
        func cell(_ x: Int, _ y: Int) -> Float {
            kernel[(y * 9 + x)]
        }

        let center = cell(4, 4)
        let orthogonalNeighbor = cell(5, 4)
        let diagonalNeighbor = cell(5, 5)
        let farCell = cell(0, 0)
        let total = kernel.reduce(Float(0), +)

        XCTAssertEqual(total, 1.0, accuracy: 0.0001)
        XCTAssertEqual(center, 0.5 / 8.5, accuracy: 0.0001)
        XCTAssertEqual(orthogonalNeighbor, 1.0 / 8.5, accuracy: 0.0001)
        XCTAssertEqual(diagonalNeighbor, 1.0 / 8.5, accuracy: 0.0001)
        XCTAssertEqual(farCell, 0.0, accuracy: 0.0001)
    }

    func testQD24GrowthProfilesChangeAdditiveGrowth() throws {
        let values = MLXArray([Float(0.5), Float(0.7)]).reshaped([1, 1, 2, 1])
        let m = MLXArray([Float(0.5)])
        let s = MLXArray([Float(0.1)])
        let h = MLXArray([Float(1.0)])

        let gaussian = growth(values, m: m, s: s, h: h, profile: "gaussian").asArray(Float.self)
        let step = growth(values, m: m, s: s, h: h, profile: "stpz").asArray(Float.self)
        let quad = growth(values, m: m, s: s, h: h, profile: "quad4").asArray(Float.self)

        XCTAssertEqual(step, [1.0, -1.0])
        XCTAssertGreaterThan(abs(gaussian[1] - step[1]), 0.2)
        XCTAssertGreaterThan(abs(quad[1] - gaussian[1]), 0.05)
    }

    func testQD24AdditiveStepperDoesNotReintegrateWhenGrowthIsZero() throws {
        let config = BatchedConfig(
            sx: 16,
            sy: 16,
            channels: 1,
            nbK: 1,
            dt: 0.2,
            dd: 5,
            sigma: 0.65,
            n: 2,
            thetaA: 2.0,
            border: "torus",
            implementation: ImplementationSettings(
                mode: "qd24_additive_v1",
                border: "torus",
                gradientBoundary: "periodic",
                alphaMode: "mass",
                kernelProfile: "qd24_bucketed_v1",
                flowClip: "none"
            ),
            chemChannel: nil,
            chemIncludeInMass: true
        )
        let params = ResolvedParams(
            r: [0.5],
            b: [[1.0, 0.5]],
            w: [[0.0, 0.0]],
            a: [[0.0, 0.0]],
            m: [0.15],
            s: [0.05],
            h: [0.0],
            R: 6.0,
            seed: 0
        )
        let kernels = compileKernels(params: params, config: config, c0: [0], c1: [[0]])
        let engine = FlowLeniaBatched(config: config, kernels: kernels)
        var values = [Float](repeating: 0, count: 16 * 16)
        values[8 * 16 + 8] = 1.0
        values[8 * 16 + 9] = 0.5
        values[9 * 16 + 8] = 0.25
        let state = MLXArray(values).reshaped([1, 16, 16, 1])

        let next = engine.stepUncompiled(state)
        eval(next)

        XCTAssertEqual(next.asArray(Float.self), values)
    }

    func testQD24AdditiveStepperRecentersBeforeNextStep() throws {
        let config = BatchedConfig(
            sx: 16,
            sy: 16,
            channels: 1,
            nbK: 1,
            dt: 0.2,
            dd: 5,
            sigma: 0.65,
            n: 2,
            thetaA: 2.0,
            border: "torus",
            implementation: ImplementationSettings(
                mode: "qd24_additive_v1",
                border: "torus",
                gradientBoundary: "periodic",
                alphaMode: "mass",
                kernelProfile: "qd24_bucketed_v1",
                flowClip: "none"
            ),
            chemChannel: nil,
            chemIncludeInMass: true
        )
        let params = ResolvedParams(
            r: [0.5],
            b: [[1.0, 0.5]],
            w: [[0.0, 0.0]],
            a: [[0.0, 0.0]],
            m: [0.15],
            s: [0.05],
            h: [0.0],
            R: 6.0,
            seed: 0
        )
        let kernels = compileKernels(params: params, config: config, c0: [0], c1: [[0]])
        let engine = FlowLeniaBatched(config: config, kernels: kernels)
        var values = [Float](repeating: 0, count: 16 * 16)
        values[10 * 16 + 8] = 1.0
        let state = MLXArray(values).reshaped([1, 16, 16, 1])

        _ = engine.stepUncompiled(state)
        let recentered = engine.stepUncompiled(state)
        eval(recentered)
        var expected = [Float](repeating: 0, count: 16 * 16)
        expected[8 * 16 + 8] = 1.0

        XCTAssertEqual(recentered.asArray(Float.self), expected)
    }

    func testLeniaBreeder2024ReplayCapturesExactRequestedSteps() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let configDirectory = packageRoot.appendingPathComponent("configs/papers/leniabreeder-2024", isDirectory: true)
        let bundle = try loadLeniaBreeder2024ConfigBundle(configDirectory: configDirectory)
        let run = try loadLeniaBreeder2024ResolvedRun(runDirectory: configDirectory)
        let assets = try leniaBreeder2024LoadAssets(
            base: run.base,
            pattern: run.pattern,
            mode: leniaBreeder2024MAPElitesSettings(config: bundle.mapElites)
        )
        let elite = LeniaBreeder2024EliteSummary(
            cell: 0,
            generation: 0,
            centroid: [],
            descriptor: [],
            fitness: 0,
            genotype: assets.initialGenotype
        )

        let contiguous = try captureLeniaBreeder2024ReplayMassMaps(
            run: run,
            elite: elite,
            frameBudget: 4,
            stepsOverride: 3
        )
        let exact = try captureLeniaBreeder2024ReplayMassMapsAtSteps(
            run: run,
            elite: elite,
            steps: [3, 0, 1, 3],
            stepsOverride: 3
        )

        XCTAssertEqual(contiguous.count, 4)
        XCTAssertEqual(exact[0], contiguous[3])
        XCTAssertEqual(exact[1], contiguous[0])
        XCTAssertEqual(exact[2], contiguous[1])
        XCTAssertEqual(exact[3], contiguous[3])

        let patches = try captureLeniaBreeder2024ReplayStatePatchesAtSteps(
            run: run,
            elite: elite,
            steps: [1],
            stepsOverride: 3
        )
        XCTAssertEqual(patches.count, 1)
        XCTAssertEqual(patches[0].width, run.base.worldSize)
        XCTAssertEqual(patches[0].height, run.base.worldSize)
        XCTAssertEqual(patches[0].channels, 1)
        XCTAssertEqual(patches[0].decodedValues(), contiguous[1])

        XCTAssertThrowsError(
            try captureLeniaBreeder2024ReplayMassMapsAtSteps(
                run: run,
                elite: elite,
                steps: [4],
                stepsOverride: 3
            )
        )
        XCTAssertThrowsError(
            try captureLeniaBreeder2024ReplayMassMapsAtSteps(
                run: run,
                elite: elite,
                steps: [-1],
                stepsOverride: 3
            )
        )
    }

    func testLeniaBreeder2024PatternKernelCoreAffectsReplay() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let sourceDirectory = packageRoot.appendingPathComponent("configs/papers/leniabreeder-2024", isDirectory: true)
        let tempRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let bucketedDirectory = tempRoot.appendingPathComponent("bucketed", isDirectory: true)
        let bump4Directory = tempRoot.appendingPathComponent("bump4", isDirectory: true)
        try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempRoot) }
        try FileManager.default.copyItem(at: sourceDirectory, to: bucketedDirectory)
        try FileManager.default.copyItem(at: sourceDirectory, to: bump4Directory)

        let bump4Bundle = try loadLeniaBreeder2024ConfigBundle(configDirectory: bump4Directory)
        let bump4PatternURL = bump4Directory
            .appendingPathComponent("patterns", isDirectory: true)
            .appendingPathComponent("\(bump4Bundle.base.patternID).json")
        try rewriteJSONFile(at: bump4PatternURL) { root in
            root["parsed_rule"] = ["kernel_core": "bump4"]
        }

        let bucketedRun = try loadLeniaBreeder2024ResolvedRun(runDirectory: bucketedDirectory)
        let bump4Run = try loadLeniaBreeder2024ResolvedRun(runDirectory: bump4Directory)
        XCTAssertNil(bucketedRun.pattern.parsedRule?.kernelCore)
        XCTAssertEqual(bump4Run.pattern.parsedRule?.kernelCore, "bump4")

        func initialElite(run: LeniaBreeder2024ResolvedRun, directory: URL) throws -> LeniaBreeder2024EliteSummary {
            let bundle = try loadLeniaBreeder2024ConfigBundle(configDirectory: directory)
            let assets = try leniaBreeder2024LoadAssets(
                base: run.base,
                pattern: run.pattern,
                mode: leniaBreeder2024MAPElitesSettings(config: bundle.mapElites)
            )
            return LeniaBreeder2024EliteSummary(
                cell: 0,
                generation: 0,
                centroid: [],
                descriptor: [],
                fitness: 0,
                genotype: assets.initialGenotype
            )
        }

        let bucketed = try captureLeniaBreeder2024ReplayMassMapsAtSteps(
            run: bucketedRun,
            elite: initialElite(run: bucketedRun, directory: bucketedDirectory),
            steps: [8],
            stepsOverride: 8
        )[0]
        let bump4 = try captureLeniaBreeder2024ReplayMassMapsAtSteps(
            run: bump4Run,
            elite: initialElite(run: bump4Run, directory: bump4Directory),
            steps: [8],
            stepsOverride: 8
        )[0]

        let l1 = zip(bucketed, bump4).reduce(Float(0)) { total, pair in
            total + abs(pair.0 - pair.1)
        }
        XCTAssertGreaterThan(l1, 1e-3)
    }

    func testLeniaBreeder2024RunnerCompletesTinySmoke() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let sourceDirectory = packageRoot.appendingPathComponent("configs/papers/leniabreeder-2024", isDirectory: true)
        let tempRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let configDirectory = tempRoot.appendingPathComponent("configs", isDirectory: true)
        let outputDirectory = tempRoot.appendingPathComponent("output", isDirectory: true)
        try FileManager.default.createDirectory(at: configDirectory, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempRoot) }

        for filename in ["base.json", "me.json", "aurora.json"] {
            try FileManager.default.copyItem(
                at: sourceDirectory.appendingPathComponent(filename),
                to: configDirectory.appendingPathComponent(filename)
            )
        }
        let patternSource = sourceDirectory.appendingPathComponent("patterns", isDirectory: true)
        let patternTarget = configDirectory.appendingPathComponent("patterns", isDirectory: true)
        try FileManager.default.copyItem(at: patternSource, to: patternTarget)

        try rewriteJSONFile(at: configDirectory.appendingPathComponent("base.json")) { root in
            root["world_size"] = 128
            root["n_step"] = 20
        }

        try rewriteJSONFile(at: configDirectory.appendingPathComponent("me.json")) { root in
            root["phenotype_size"] = 64
            root["n_generations"] = 2
            root["log_interval"] = 1
            root["batch_size"] = 4
            root["repertoire_size"] = 8
            root["n_init_cvt_samples"] = 64
            root["n_keep"] = 4
            root["iso_sigma"] = 0.001
            root["line_sigma"] = 0.01
        }

        let bundle = try loadLeniaBreeder2024ConfigBundle(configDirectory: configDirectory)
        let runner = LeniaBreeder2024Runner(
            configs: bundle,
            logger: Logger(label: "LeniaCoreTests.LeniaBreeder2024"),
            seed: 7
        )
        let summary = try runner.runMAPElites(outputDirectory: outputDirectory, runId: "test-qd-me")

        XCTAssertEqual(summary.algorithm, "me")
        XCTAssertEqual(summary.generations, 2)
        XCTAssertEqual(summary.patternID, "5N7KKM")
        XCTAssertTrue(summary.coverage.isFinite)
        XCTAssertTrue(summary.qdScore.isFinite)
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("library/index.jsonl").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("summary.json").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("history.jsonl").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("metrics.csv").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("patterns/5N7KKM.json").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("repertoire/centroids.json").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("repertoire/occupied.json").path))
    }

    func testLeniaBreeder2024DistributedMAPElitesJobEvaluatesTinyBatch() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let sourceDirectory = packageRoot.appendingPathComponent("configs/papers/leniabreeder-2024", isDirectory: true)
        let tempRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let configDirectory = tempRoot.appendingPathComponent("configs", isDirectory: true)
        try FileManager.default.createDirectory(at: configDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempRoot) }

        for filename in ["base.json", "me.json", "aurora.json"] {
            try FileManager.default.copyItem(
                at: sourceDirectory.appendingPathComponent(filename),
                to: configDirectory.appendingPathComponent(filename)
            )
        }
        let patternSource = sourceDirectory.appendingPathComponent("patterns", isDirectory: true)
        let patternTarget = configDirectory.appendingPathComponent("patterns", isDirectory: true)
        try FileManager.default.copyItem(at: patternSource, to: patternTarget)

        try rewriteJSONFile(at: configDirectory.appendingPathComponent("base.json")) { root in
            root["world_size"] = 64
            root["n_step"] = 12
        }

        try rewriteJSONFile(at: configDirectory.appendingPathComponent("me.json")) { root in
            root["phenotype_size"] = 32
            root["batch_size"] = 4
            root["repertoire_size"] = 8
            root["n_init_cvt_samples"] = 64
            root["n_keep"] = 4
            root["iso_sigma"] = 0.001
            root["line_sigma"] = 0.01
        }

        let bundle = try loadLeniaBreeder2024ConfigBundle(configDirectory: configDirectory)
        let spec = try leniaBreeder2024MakeDistributedSpec(configs: bundle)
        let assets = try leniaBreeder2024LoadAssets(
            configs: bundle,
            mode: leniaBreeder2024MAPElitesSettings(configs: bundle)
        )
        var rng = SeededRandomNumberGenerator(seed: 11)
        let genotypes = (0..<2).map { _ in
            leniaBreeder2024PerturbInitialGenotype(
                base: assets.initialGenotype,
                isoSigma: bundle.mapElites.isoSigma,
                rng: &rng
            )
        }
        let job = LeniaBreeder2024DistributedMAPElitesJob(
            id: "tiny-distributed-me",
            generation: 1,
            candidateOffset: 0,
            genotypes: genotypes,
            spec: spec
        )
        var cache: [String: LeniaBreeder2024WorkerAssetCacheEntry] = [:]

        let result = try leniaBreeder2024EvaluateMAPElitesJob(
            job: job,
            workerId: "worker-test",
            cache: &cache
        )
        let repeated = try leniaBreeder2024EvaluateMAPElitesJob(
            job: job,
            workerId: "worker-test",
            cache: &cache
        )

        XCTAssertEqual(result.jobId, "tiny-distributed-me")
        XCTAssertEqual(result.generation, 1)
        XCTAssertEqual(result.candidateOffset, 0)
        XCTAssertEqual(result.evaluations.count, 2)
        XCTAssertEqual(repeated.evaluations.count, 2)
        XCTAssertEqual(cache.count, 1)
        XCTAssertEqual(repeated.workerId, "worker-test")
    }

    func testLeniaBreeder2024RunnerCompletesTinyAuroraSmoke() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let sourceDirectory = packageRoot.appendingPathComponent("configs/papers/leniabreeder-2024", isDirectory: true)
        let tempRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let configDirectory = tempRoot.appendingPathComponent("configs", isDirectory: true)
        let outputDirectory = tempRoot.appendingPathComponent("output", isDirectory: true)
        try FileManager.default.createDirectory(at: configDirectory, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempRoot) }

        for filename in ["base.json", "me.json", "aurora.json"] {
            try FileManager.default.copyItem(
                at: sourceDirectory.appendingPathComponent(filename),
                to: configDirectory.appendingPathComponent(filename)
            )
        }
        let patternSource = sourceDirectory.appendingPathComponent("patterns", isDirectory: true)
        let patternTarget = configDirectory.appendingPathComponent("patterns", isDirectory: true)
        try FileManager.default.copyItem(at: patternSource, to: patternTarget)

        try rewriteJSONFile(at: configDirectory.appendingPathComponent("base.json")) { root in
            root["world_size"] = 64
            root["n_step"] = 12
        }

        try rewriteJSONFile(at: configDirectory.appendingPathComponent("aurora.json")) { root in
            root["n_generations"] = 2
            root["log_interval"] = 1
            root["batch_size"] = 4
            root["repertoire_size"] = 8
            root["iso_sigma"] = 0.001
            root["line_sigma"] = 0.01
            root["n_keep"] = 4
            root["ae_batch_size"] = 4
            root["n_keep_ae"] = 16
            root["train_ratio"] = 1
        }

        let bundle = try loadLeniaBreeder2024ConfigBundle(configDirectory: configDirectory)
        let runner = LeniaBreeder2024Runner(
            configs: bundle,
            logger: Logger(label: "LeniaCoreTests.LeniaBreeder2024AURORA"),
            seed: 9
        )
        let summary = try runner.runAURORA(outputDirectory: outputDirectory, runId: "test-qd-aurora")

        XCTAssertEqual(summary.algorithm, "aurora")
        XCTAssertEqual(summary.generations, 2)
        XCTAssertEqual(summary.patternID, "5N7KKM")
        XCTAssertTrue(summary.coverage.isFinite)
        XCTAssertTrue(summary.qdScore.isFinite)
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("library/index.jsonl").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("summary.json").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("history.jsonl").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("metrics.csv").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("repertoire/centroids.json").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("repertoire/occupied.json").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("vae.json").path))
        let diagnosticsURL = outputDirectory.appendingPathComponent("aurora-diagnostics.jsonl")
        XCTAssertTrue(FileManager.default.fileExists(atPath: diagnosticsURL.path))
        let diagnostics = try String(contentsOf: diagnosticsURL, encoding: .utf8)
        XCTAssertGreaterThanOrEqual(diagnostics.split(separator: "\n").count, 2)
    }

    func testReactionDiffusionLenia2023PaperConfigsDecode() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let configDirectory = packageRoot.appendingPathComponent("configs/papers/reaction-diffusion-lenia-2023", isDirectory: true)

        let bundle = try loadReactionDiffusionLenia2023ConfigBundle(configDirectory: configDirectory)

        XCTAssertEqual(bundle.asymptotic.paper, "implementation-of-lenia-as-a-reaction-diffusion-system-2023")
        XCTAssertEqual(bundle.asymptotic.kernelFunction, "gauss")
        XCTAssertEqual(bundle.asymptotic.reactionTransform, "T=(G+1)/2")
        XCTAssertEqual(bundle.asymptotic.dtValues, [0.5, 0.1, 0.05, 0.01, 0.002])
        XCTAssertEqual(bundle.asymptotic.gaussianMean, 0.15, accuracy: 1e-6)
        XCTAssertEqual(bundle.asymptotic.gaussianStd, 0.017, accuracy: 1e-6)
        XCTAssertEqual(bundle.asymptotic.orbiumConfig, "../../presets/orbium_like_classic_1c_128.json")
        XCTAssertTrue(bundle.validation.compareOriginalLenia)
        XCTAssertTrue(bundle.validation.compareAsymptoticLenia)
        XCTAssertTrue(bundle.validation.lowerClipOnlyAtSmallDt)
        XCTAssertEqual(bundle.validation.occasionalUpperClipDelta, 0.1, accuracy: 1e-6)
        XCTAssertEqual(bundle.validation.expectedSmallDtThreshold, 0.002, accuracy: 1e-6)
        XCTAssertEqual(bundle.emulation.auxiliaryVariableCount, 40)
        XCTAssertEqual(bundle.emulation.mu, 0.1, accuracy: 1e-6)
        XCTAssertEqual(bundle.emulation.diffusionStart, 1)
        XCTAssertEqual(bundle.emulation.diffusionEnd, 40)
        XCTAssertEqual(bundle.emulation.epsilon, 0.005, accuracy: 1e-6)
        XCTAssertEqual(bundle.emulation.eulerDt, 0.00001, accuracy: 1e-9)
    }

    func testFlowLeniaEcology2025PaperConfigsDecode() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let configDirectory = packageRoot.appendingPathComponent("configs/papers/flowlenia-ecology-2025", isDirectory: true)

        let bundle = try loadFlowLeniaEcology2025ConfigBundle(configDirectory: configDirectory)

        XCTAssertEqual(bundle.simulation.paper, "flow-lenia-emergent-evolutionary-dynamics-2025")
        XCTAssertEqual(bundle.simulation.gridSize, 512)
        XCTAssertEqual(bundle.simulation.totalSteps, 500_000)
        XCTAssertEqual(bundle.simulation.recordEverySteps, 100)
        XCTAssertEqual(bundle.simulation.channels, 3)
        XCTAssertEqual(bundle.simulation.kernelsPerChannelPair, 5)
        XCTAssertEqual(bundle.simulation.repeats, 5)
        XCTAssertEqual(bundle.simulation.mutationProbabilities, [0.001, 0.01, 0.1, 0.5, 1.0])
        XCTAssertEqual(bundle.variants.map(\.name), ["vanilla", "dissipative", "food"])
    }

    func testFlowLeniaEcology2025RunnerCompletesTinySmoke() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let sourceDirectory = packageRoot.appendingPathComponent("configs/papers/flowlenia-ecology-2025", isDirectory: true)
        let tempRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let configDirectory = tempRoot.appendingPathComponent("configs", isDirectory: true)
        let outputDirectory = tempRoot.appendingPathComponent("output", isDirectory: true)
        try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
        try FileManager.default.copyItem(at: sourceDirectory, to: configDirectory)
        try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempRoot) }

        try overwriteJSONObject(at: configDirectory.appendingPathComponent("vanilla-base.json")) { json in
            json["grid"] = ["sx": 32, "sy": 32]
            json["run"] = ["steps": 20]
            json["init"] = [
                "seed": 0,
                "patches": [["center": [16, 16], "size": 8]],
                "a_uniform": ["low": 0.0, "high": 1.0],
                "p_uniform": ["low": 0.0, "high": 1.0]
            ]
            json["beam_mutation"] = [
                "enabled": true,
                "probability": 0.01,
                "patch_size": 4,
                "std": 1.0,
                "seed": 11
            ]
        }

        let simulation = FlowLeniaEcology2025SimulationConfig(
            paper: "flow-lenia-emergent-evolutionary-dynamics-2025",
            gridSize: 32,
            totalSteps: 20,
            recordEverySteps: 5,
            captureEverySteps: 5,
            channels: 3,
            kernelsPerChannelPair: 5,
            repeats: 1,
            mutationProbabilities: [0.0, 0.0003, 0.01],
            variants: ["vanilla"],
            activity: ActivityConfig(
                enabled: true,
                interval: 5,
                threshold: 0.05,
                maxComponents: 64,
                matchThreshold: 1.5,
                paramWeight: 1.0,
                positionWeight: 0.05
            )
        )
        let variant = FlowLeniaEcology2025VariantConfig(
            name: "vanilla",
            baseConfig: "vanilla-base.json",
            initPatchCount: 4,
            initPatchSize: 4,
            initParamMean: 0.0,
            initParamStd: 1.0,
            foodPatchCount: nil,
            foodPatchSize: nil,
            foodPatchValue: nil,
            foodSpawn: nil,
            dissipation: nil
        )
        let bundle = FlowLeniaEcology2025ConfigBundle(
            configDirectory: configDirectory,
            simulation: simulation,
            variants: [variant]
        )

        let runner = FlowLeniaEcology2025Runner(
            configs: bundle,
            logger: Logger(label: "LeniaCoreTests.FlowLeniaEcology2025")
        )
        let summary = try runner.run(outputDirectory: outputDirectory)

        XCTAssertEqual(summary.totalRuns, 3)
        XCTAssertEqual(summary.runs.count, 3)
        XCTAssertEqual(summary.runs[0].variant, "vanilla")
        XCTAssertTrue(summary.runs[0].frames >= 1)
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("summary.json").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("runs/vanilla/pmut=0_000/repeat=0/frames.jsonl").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("runs/vanilla/pmut=0_000300/repeat=0/frames.jsonl").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("runs/vanilla/pmut=0_010/repeat=0/frames.jsonl").path))
        let ecologyIndexURL = outputDirectory.appendingPathComponent("ecology-runs/index.jsonl")
        XCTAssertTrue(FileManager.default.fileExists(atPath: ecologyIndexURL.path))
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .deferredToDate
        let lines = try String(contentsOf: ecologyIndexURL, encoding: .utf8)
            .split(separator: "\n")
            .map(String.init)
        XCTAssertEqual(lines.count, 3)
        let records = try lines.map {
            try decoder.decode(FlowLeniaEcology2025RunRecord.self, from: Data($0.utf8))
        }
        XCTAssertEqual(Set(records.map(\.trialID)).count, 3)
        for record in records {
            XCTAssertEqual(record.bundleKind, .flowLeniaEcology2025ArenaReplayBundleV1)
            XCTAssertTrue(FileManager.default.fileExists(atPath: record.baseConfigPath))
            XCTAssertTrue(FileManager.default.fileExists(atPath: record.payloadPath))
            XCTAssertTrue(FileManager.default.fileExists(atPath: record.metadataPath))
            let trajectoryFramesPath = try XCTUnwrap(record.trajectoryFramesPath)
            XCTAssertTrue(FileManager.default.fileExists(atPath: trajectoryFramesPath))
        }
    }

    func testLoadResearchSeedPatchesFromLocalLibrary() throws {
        let (baseConfig, searchConfig, creature) = try testResearchSeedCreature(name: "library-seed")
        let tempRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let runDirectory = tempRoot.appendingPathComponent("run", isDirectory: true)
        let libraryDirectory = runDirectory.appendingPathComponent("library", isDirectory: true)
        try FileManager.default.createDirectory(at: libraryDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempRoot) }

        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .deferredToDate
        try encoder.encode(baseConfig).write(to: runDirectory.appendingPathComponent("config.json"))
        try encoder.encode(searchConfig).write(to: runDirectory.appendingPathComponent("search.json"))

        let initialEntry = ResearchLibraryEntry(
            creature: creature,
            campaignId: nil,
            runId: "test-run",
            recordedAt: Date(timeIntervalSinceReferenceDate: 0),
            configHash: "test-hash"
        )
        let initialIndexURL = try ResearchLibraryWriter.write(entries: [initialEntry], runDirectory: runDirectory)
        let initialPatches = try loadResearchSeedPatches(
            libraryURL: initialIndexURL,
            warmupSteps: 4,
            cropThreshold: 0.01,
            padding: 2
        )

        XCTAssertEqual(initialPatches.count, 1)
        XCTAssertEqual(initialPatches[0].name, creature.name)
        XCTAssertEqual(initialPatches[0].world.channels, 1)
        XCTAssertFalse(initialPatches[0].world.values.allSatisfy { abs($0) < 1e-6 })

        let staleCreature = SavedCreature(
            id: UUID(),
            name: creature.name,
            ownerId: creature.ownerId,
            genotype: creature.genotype,
            initialCondition: creature.initialCondition,
            metrics: creature.metrics,
            sweep: creature.sweep,
            score: creature.score,
            scoreWeights: creature.scoreWeights,
            configHash: creature.configHash
        )
        let manifestEntry = ResearchLibraryEntry(
            creature: staleCreature,
            campaignId: nil,
            runId: "test-run",
            recordedAt: Date(timeIntervalSinceReferenceDate: 0),
            configHash: "test-hash",
            specimenManifest: buildLibrarySpecimenManifest(
                creature: creature,
                campaignID: nil,
                runID: "test-run",
                recordedAt: Date(timeIntervalSinceReferenceDate: 0),
                configHash: "test-hash",
                sourceMode: nil,
                sourceAlgorithm: nil,
                researchMetadata: nil
            )
        )
        let manifestIndexURL = try ResearchLibraryWriter.write(entries: [manifestEntry], runDirectory: runDirectory)

        let manifestPatches = try loadResearchSeedPatches(
            libraryURL: manifestIndexURL,
            warmupSteps: 4,
            cropThreshold: 0.01,
            padding: 2
        )

        XCTAssertEqual(manifestPatches.count, 1)
        XCTAssertEqual(manifestPatches[0].sourceID, creature.id.uuidString)
        XCTAssertNotEqual(manifestPatches[0].sourceID, staleCreature.id.uuidString)
    }

    func testLoadResearchSeedPatchesFromExportIndex() throws {
        let (baseConfig, searchConfig, creature) = try testResearchSeedCreature(name: "export-seed")
        let tempRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let exportsDirectory = tempRoot.appendingPathComponent("exports", isDirectory: true)
        try FileManager.default.createDirectory(at: exportsDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempRoot) }

        let artifacts = try XCTUnwrap(
            writeReplayExportArtifacts(
                exportRoot: exportsDirectory,
                baseConfig: baseConfig,
                searchConfig: searchConfig,
                creature: creature,
                runId: "test-run",
                campaignId: nil,
                score: 1.0,
                filtersPassed: true,
                reason: "test",
                exportedAt: Date(timeIntervalSinceReferenceDate: 0)
            )
        )

        let indexURL = exportsDirectory.appendingPathComponent("index.jsonl")
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        encoder.dateEncodingStrategy = .deferredToDate
        try (try encoder.encode(artifacts.record) + Data([0x0A])).write(to: indexURL)

        let initialPatches = try loadResearchSeedPatches(
            libraryURL: indexURL,
            warmupSteps: 4,
            cropThreshold: 0.01,
            padding: 2
        )

        XCTAssertEqual(initialPatches.count, 1)
        XCTAssertEqual(initialPatches[0].name, creature.name)
        XCTAssertEqual(initialPatches[0].world.channels, 1)
        XCTAssertFalse(initialPatches[0].world.values.allSatisfy { abs($0) < 1e-6 })

        let metaURL = artifacts.exportDir.appendingPathComponent("meta.json")
        guard var root = try JSONSerialization.jsonObject(with: Data(contentsOf: metaURL)) as? [String: Any],
              var metaCreature = root["creature"] as? [String: Any] else {
            XCTFail("Expected export meta.json creature payload")
            return
        }
        metaCreature["id"] = UUID().uuidString
        root["creature"] = metaCreature
        let metaData = try JSONSerialization.data(withJSONObject: root, options: [.sortedKeys])
        try metaData.write(to: metaURL)

        try (try encoder.encode(artifacts.record) + Data([0x0A])).write(to: indexURL)

        let manifestPatches = try loadResearchSeedPatches(
            libraryURL: indexURL,
            warmupSteps: 4,
            cropThreshold: 0.01,
            padding: 2
        )

        XCTAssertEqual(manifestPatches.count, 1)
        XCTAssertEqual(manifestPatches[0].sourceID, creature.id.uuidString)
    }

    func testLoadResearchSeedPatchesSelectsTopFromLocalLibraryByScore() throws {
        let (baseConfig, searchConfig, lowCreature) = try testResearchSeedCreature(name: "low-score", score: 0.25)
        let (_, _, highCreature) = try testResearchSeedCreature(name: "high-score", score: 3.5)
        let tempRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let runDirectory = tempRoot.appendingPathComponent("run", isDirectory: true)
        let libraryDirectory = runDirectory.appendingPathComponent("library", isDirectory: true)
        try FileManager.default.createDirectory(at: libraryDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempRoot) }

        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .deferredToDate
        try encoder.encode(baseConfig).write(to: runDirectory.appendingPathComponent("config.json"))
        try encoder.encode(searchConfig).write(to: runDirectory.appendingPathComponent("search.json"))

        let entries = [
            ResearchLibraryEntry(
                creature: lowCreature,
                campaignId: nil,
                runId: "test-run",
                recordedAt: Date(timeIntervalSinceReferenceDate: 0),
                configHash: "test-hash"
            ),
            ResearchLibraryEntry(
                creature: highCreature,
                campaignId: nil,
                runId: "test-run",
                recordedAt: Date(timeIntervalSinceReferenceDate: 1),
                configHash: "test-hash"
            )
        ]
        let indexURL = try ResearchLibraryWriter.write(entries: entries, runDirectory: runDirectory)
        let patches = try loadResearchSeedPatches(
            libraryURL: indexURL,
            warmupSteps: 4,
            cropThreshold: 0.01,
            padding: 2,
            selection: ResearchSeedSelection(top: 1, rankBy: .score)
        )

        XCTAssertEqual(patches.count, 1)
        XCTAssertEqual(patches[0].name, highCreature.name)
        XCTAssertEqual(patches[0].score, highCreature.score)
    }

    func testLoadResearchSeedPatchesSelectsNamedPatchFromExportIndex() throws {
        let (baseConfig, searchConfig, alphaCreature) = try testResearchSeedCreature(name: "alpha-export", score: 0.5)
        let (_, _, betaCreature) = try testResearchSeedCreature(name: "beta-export", score: 1.5)
        let tempRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let exportsDirectory = tempRoot.appendingPathComponent("exports", isDirectory: true)
        try FileManager.default.createDirectory(at: exportsDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempRoot) }

        let alphaArtifacts = try XCTUnwrap(
            writeReplayExportArtifacts(
                exportRoot: exportsDirectory,
                baseConfig: baseConfig,
                searchConfig: searchConfig,
                creature: alphaCreature,
                runId: "test-run",
                campaignId: nil,
                score: alphaCreature.score,
                filtersPassed: true,
                reason: "test",
                exportedAt: Date(timeIntervalSinceReferenceDate: 0)
            )
        )
        let betaArtifacts = try XCTUnwrap(
            writeReplayExportArtifacts(
                exportRoot: exportsDirectory,
                baseConfig: baseConfig,
                searchConfig: searchConfig,
                creature: betaCreature,
                runId: "test-run",
                campaignId: nil,
                score: betaCreature.score,
                filtersPassed: true,
                reason: "test",
                exportedAt: Date(timeIntervalSinceReferenceDate: 1)
            )
        )

        let indexURL = exportsDirectory.appendingPathComponent("index.jsonl")
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        encoder.dateEncodingStrategy = .deferredToDate
        let records = [alphaArtifacts.record, betaArtifacts.record]
        let content = try records.reduce(into: Data()) { data, record in
            data.append(try encoder.encode(record))
            data.append(0x0A)
        }
        try content.write(to: indexURL)

        let patches = try loadResearchSeedPatches(
            libraryURL: indexURL,
            warmupSteps: 4,
            cropThreshold: 0.01,
            padding: 2,
            selection: ResearchSeedSelection(names: [betaCreature.name])
        )

        XCTAssertEqual(patches.count, 1)
        XCTAssertEqual(patches[0].name, betaCreature.name)
        XCTAssertEqual(patches[0].score, betaCreature.score)
    }

    func testLoadResearchSeedPatchesPrefiltersNamedExportIndexBeforeExpression() throws {
        let (baseConfig, searchConfig, selectedCreature) = try testResearchSeedCreature(name: "selected-export", score: 1.0)
        let tempRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let exportsDirectory = tempRoot.appendingPathComponent("exports", isDirectory: true)
        try FileManager.default.createDirectory(at: exportsDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempRoot) }

        let selectedArtifacts = try XCTUnwrap(
            writeReplayExportArtifacts(
                exportRoot: exportsDirectory,
                baseConfig: baseConfig,
                searchConfig: searchConfig,
                creature: selectedCreature,
                runId: "test-run",
                campaignId: nil,
                score: selectedCreature.score,
                filtersPassed: true,
                reason: "test",
                exportedAt: Date(timeIntervalSinceReferenceDate: 0)
            )
        )
        let missingRecord = CreatureExportRecord(
            creatureId: UUID(),
            name: "missing-export",
            ownerId: "test",
            runId: "test-run",
            campaignId: nil,
            bundleKind: .strictReplayBundleV1,
            exportDir: tempRoot.appendingPathComponent("missing-export", isDirectory: true).path,
            baseConfigPath: tempRoot.appendingPathComponent("missing-export/base.json").path,
            searchConfigPath: tempRoot.appendingPathComponent("missing-export/search.json").path,
            exportedAt: Date(timeIntervalSinceReferenceDate: 1),
            reason: "test",
            score: 2.0,
            filtersPassed: true,
            runtimeFamily: "flow_lenia",
            runtimeCapabilities: ["archive", "replay"]
        )

        let indexURL = exportsDirectory.appendingPathComponent("index.jsonl")
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        encoder.dateEncodingStrategy = .deferredToDate
        let records = [selectedArtifacts.record, missingRecord]
        let content = try records.reduce(into: Data()) { data, record in
            data.append(try encoder.encode(record))
            data.append(0x0A)
        }
        try content.write(to: indexURL)

        let patches = try loadResearchSeedPatches(
            libraryURL: indexURL,
            warmupSteps: 4,
            cropThreshold: 0.01,
            padding: 2,
            selection: ResearchSeedSelection(names: [selectedCreature.name])
        )

        XCTAssertEqual(patches.count, 1)
        XCTAssertEqual(patches[0].name, selectedCreature.name)
    }

    func testLoadResearchSeedPatchesDetectsLargePatchJSONLBySchema() throws {
        let tempRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tempRoot) }
        try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)

        let patch = ResearchSeedPatch(
            sourceID: "large-patch",
            name: "large-patch",
            width: 192,
            height: 192,
            channels: 1,
            data: Array(repeating: Float(0.25), count: 192 * 192),
            score: 1.25
        )
        let indexURL = tempRoot.appendingPathComponent("portfolio-seeds.jsonl")
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        try Data(("\n  \n" + String(decoding: encoder.encode(patch), as: UTF8.self) + "\n").utf8).write(to: indexURL)

        let patches = try loadResearchSeedPatches(
            libraryURL: indexURL,
            selection: ResearchSeedSelection(top: 1, rankBy: .score)
        )

        XCTAssertEqual(patches.count, 1)
        XCTAssertEqual(patches[0].sourceID, "large-patch")
        XCTAssertEqual(patches[0].world.values.count, 192 * 192)
    }

    func testBuildStrictReplaySearchConfigEnablesMorphospaceSignals() {
        let config = buildStrictReplaySearchConfig(steps: 24, initSeedOffset: 11)

        XCTAssertEqual(config.count, 1)
        XCTAssertEqual(config.initSeedOffset, 11)
        XCTAssertEqual(config.steps, 24)
        XCTAssertTrue(config.activity?.enabled == true)
        XCTAssertTrue(config.moments?.enabled == true)
        XCTAssertEqual(config.moments?.threshold, 0.01)
        XCTAssertEqual(config.occupancyThreshold, 0.01)
        XCTAssertTrue(config.stability?.enabled == true)
        XCTAssertEqual(config.stability?.massMinFraction, 0.001)
        XCTAssertEqual(config.collection?.enabled, false)
    }

    func testBuildStrictReplaySearchConfigUsesRequestedMorphologyThreshold() {
        let config = buildStrictReplaySearchConfig(
            steps: 24,
            initSeedOffset: 11,
            morphologyThreshold: 0.03
        )

        XCTAssertEqual(config.moments?.threshold, 0.03)
        XCTAssertEqual(config.occupancyThreshold, 0.03)
    }

    func testSearchResultBuilderUsesTerminalMassForFinalMorphology() {
        let runtimeConfig = makeRuntimeConfigForSearchEngine(
            sx: 5,
            sy: 5,
            channels: 1,
            parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
            pUniform: nil,
            chemotaxis: nil,
            patches: [PatchConfig(center: [2, 2], size: 2)]
        )
        let builder = SearchBatchResultBuilder(runtimeConfig: runtimeConfig, excludedMassChannels: [])
        let searchConfig = buildStrictReplaySearchConfig(
            steps: 4,
            initSeedOffset: 0,
            morphologyThreshold: 0.5
        )
        var sampledMass = [Float](repeating: 0, count: 25)
        sampledMass[1 * 5 + 1] = 1
        var terminalMass = sampledMass
        terminalMass[3 * 5 + 3] = 1
        let sampledMassMap = MLXArray(sampledMass).reshaped([1, 5, 5])
        let terminalMassMap = MLXArray(terminalMass).reshaped([1, 5, 5])
        let summary = SearchRolloutFinalizedStats(
            effectiveSampleCount: 1,
            speedCount: 0,
            massMean: [1],
            massStd: [0],
            massMin: [1],
            massMax: [1],
            varianceMean: [0],
            energyMean: [0],
            occupancyMean: [0.04],
            gyration: [0],
            finalMass: [2],
            windowMassStd: nil,
            windowOccupancyStd: nil,
            windowGyrationStd: nil,
            pathLength: [0],
            speedMean: [0],
            velocity: [0],
            velocityX: [0],
            velocityY: [0],
            heading: [0],
            displacement: [0],
            headingCircularVariance: [nil],
            accumulatedTurnAbs: [0],
            activityLogs: nil,
            activitySummaries: nil,
            activityEacMean: [nil],
            activityEanMean: [nil],
            activityDiversityMean: [nil],
            activitySpeciesMean: [nil],
            survivalDeathStep: [nil],
            lastMassMap: sampledMassMap,
            coherentTransportSourceMassMap: nil,
            needsCoherentTransport: false
        )

        let results = builder.build(
            seeds: [0],
            initSeedOffset: 0,
            searchConfig: searchConfig.toSearchConfig(),
            initialConditionFamily: "test",
            activityConfig: nil,
            stabilityConfig: StabilityConfig.defaultConfig,
            usesActivityMetrics: false,
            rolloutSummary: summary,
            terminalMassMap: terminalMassMap,
            terminalStateBatch: nil,
            terminalParamBatch: nil
        )

        XCTAssertEqual(results[0].metrics.componentCount, 2)
    }

    func testFlowLeniaEcology2025RunnerAcceptsCuratedSeedsWithFewerChannels() throws {
        let packageRoot = packageRootURL()
        let sourceDirectory = packageRoot.appendingPathComponent("configs/papers/flowlenia-ecology-2025", isDirectory: true)
        let tempRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let configDirectory = tempRoot.appendingPathComponent("configs", isDirectory: true)
        let outputDirectory = tempRoot.appendingPathComponent("output", isDirectory: true)
        try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
        try FileManager.default.copyItem(at: sourceDirectory, to: configDirectory)
        try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempRoot) }

        try overwriteJSONObject(at: configDirectory.appendingPathComponent("vanilla-base.json")) { json in
            json["grid"] = ["sx": 32, "sy": 32]
            json["run"] = ["steps": 20]
            json["init"] = [
                "seed": 0,
                "patches": [["center": [16, 16], "size": 8]],
                "a_uniform": ["low": 0.0, "high": 1.0],
                "p_uniform": ["low": 0.0, "high": 1.0]
            ]
            json["beam_mutation"] = [
                "enabled": true,
                "probability": 0.01,
                "patch_size": 4,
                "std": 1.0,
                "seed": 11
            ]
        }

        let simulation = FlowLeniaEcology2025SimulationConfig(
            paper: "flow-lenia-emergent-evolutionary-dynamics-2025",
            gridSize: 32,
            totalSteps: 20,
            recordEverySteps: 5,
            channels: 3,
            kernelsPerChannelPair: 5,
            repeats: 1,
            mutationProbabilities: [0.01],
            variants: ["vanilla"],
            activity: ActivityConfig(
                enabled: true,
                interval: 5,
                threshold: 0.05,
                maxComponents: 64,
                matchThreshold: 1.5,
                paramWeight: 1.0,
                positionWeight: 0.05
            )
        )
        let variant = FlowLeniaEcology2025VariantConfig(
            name: "vanilla",
            baseConfig: "vanilla-base.json",
            initPatchCount: 4,
            initPatchSize: 4,
            initParamMean: 0.0,
            initParamStd: 1.0,
            foodPatchCount: nil,
            foodPatchSize: nil,
            foodPatchValue: nil,
            foodSpawn: nil,
            dissipation: nil
        )
        let bundle = FlowLeniaEcology2025ConfigBundle(
            configDirectory: configDirectory,
            simulation: simulation,
            variants: [variant]
        )

        let runner = FlowLeniaEcology2025Runner(
            configs: bundle,
            logger: Logger(label: "LeniaCoreTests.FlowLeniaEcology2025Curated"),
            curatedSeeds: [
                ResearchSeedPatch(
                    sourceID: "seed-1",
                    name: "one-channel",
                    width: 2,
                    height: 2,
                    channels: 1,
                    data: [1.0, 0.6, 0.3, 0.9]
                )
            ]
        )
        let summary = try runner.run(outputDirectory: outputDirectory)

        XCTAssertEqual(summary.totalRuns, 1)
        XCTAssertEqual(summary.runs.count, 1)
        XCTAssertEqual(summary.runs[0].variant, "vanilla")
    }

    func testFlowLeniaEcology2025CuratedSeedsCannotOccupyFoodChannel() throws {
        let packageRoot = packageRootURL()
        let sourceDirectory = packageRoot.appendingPathComponent("configs/papers/flowlenia-ecology-2025", isDirectory: true)
        let tempRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let configDirectory = tempRoot.appendingPathComponent("configs", isDirectory: true)
        let outputDirectory = tempRoot.appendingPathComponent("output", isDirectory: true)
        try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
        try FileManager.default.copyItem(at: sourceDirectory, to: configDirectory)
        try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempRoot) }

        try overwriteJSONObject(at: configDirectory.appendingPathComponent("food-base.json")) { json in
            json["grid"] = ["sx": 32, "sy": 32]
            json["channels"] = 2
            json["connectivity"] = [[5, 5], [5, 5]]
            json["run"] = ["steps": 10]
            json["init"] = [
                "seed": 0,
                "patches": [["center": [16, 16], "size": 8]],
                "a_uniform": ["low": 0.0, "high": 1.0],
                "p_uniform": ["low": 0.0, "high": 1.0]
            ]
            json["food"] = [
                "enabled": true,
                "channel_index": 1,
                "mode": "full",
                "uniform": ["low": 0.0, "high": 0.0],
                "decay_rate": 0.002,
                "digest_rate": 0.02,
                "include_in_mass": false
            ]
            json["beam_mutation"] = [
                "enabled": true,
                "probability": 0.01,
                "patch_size": 4,
                "std": 1.0,
                "seed": 11
            ]
        }

        let simulation = FlowLeniaEcology2025SimulationConfig(
            paper: "flow-lenia-emergent-evolutionary-dynamics-2025",
            gridSize: 32,
            totalSteps: 10,
            recordEverySteps: 5,
            channels: 2,
            kernelsPerChannelPair: 5,
            repeats: 1,
            mutationProbabilities: [0.01],
            variants: ["food"],
            activity: ActivityConfig(
                enabled: true,
                interval: 5,
                threshold: 0.05,
                maxComponents: 64,
                matchThreshold: 1.5,
                paramWeight: 1.0,
                positionWeight: 0.05
            )
        )
        let variant = FlowLeniaEcology2025VariantConfig(
            name: "food",
            baseConfig: "food-base.json",
            initPatchCount: 4,
            initPatchSize: 4,
            initParamMean: 0.0,
            initParamStd: 1.0,
            foodPatchCount: 2,
            foodPatchSize: 2,
            foodPatchValue: 1.0,
            foodSpawn: nil,
            dissipation: nil
        )
        let runner = FlowLeniaEcology2025Runner(
            configs: FlowLeniaEcology2025ConfigBundle(
                configDirectory: configDirectory,
                simulation: simulation,
                variants: [variant]
            ),
            logger: Logger(label: "LeniaCoreTests.FlowLeniaEcology2025FoodChannel"),
            curatedSeeds: [
                ResearchSeedPatch(
                    sourceID: "two-channel-seed",
                    name: "two-channel",
                    width: 2,
                    height: 2,
                    channels: 2,
                    data: [
                        0.2, 0.8,
                        0.1, 0.7,
                        0.3, 0.6,
                        0.4, 0.5
                    ]
                )
            ]
        )

        XCTAssertThrowsError(try runner.run(outputDirectory: outputDirectory)) { error in
            XCTAssertTrue(String(describing: error).contains("occupies runtime food channel"))
        }
    }

    func testReplayFlowLeniaEcology2025PayloadRoundTripsTinyTrial() throws {
        let packageRoot = packageRootURL()
        let sourceDirectory = packageRoot.appendingPathComponent("configs/papers/flowlenia-ecology-2025", isDirectory: true)
        let tempRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let configDirectory = tempRoot.appendingPathComponent("configs", isDirectory: true)
        try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
        try FileManager.default.copyItem(at: sourceDirectory, to: configDirectory)
        defer { try? FileManager.default.removeItem(at: tempRoot) }

        try overwriteJSONObject(at: configDirectory.appendingPathComponent("vanilla-base.json")) { json in
            json["grid"] = ["sx": 32, "sy": 32]
            json["run"] = ["steps": 20]
            json["init"] = [
                "seed": 0,
                "patches": [["center": [16, 16], "size": 8]],
                "a_uniform": ["low": 0.0, "high": 1.0],
                "p_uniform": ["low": 0.0, "high": 1.0]
            ]
            json["beam_mutation"] = [
                "enabled": true,
                "probability": 0.01,
                "patch_size": 4,
                "std": 1.0,
                "seed": 11
            ]
        }

        let simulation = FlowLeniaEcology2025SimulationConfig(
            paper: "flow-lenia-emergent-evolutionary-dynamics-2025",
            gridSize: 32,
            totalSteps: 20,
            recordEverySteps: 5,
            channels: 3,
            kernelsPerChannelPair: 5,
            repeats: 1,
            mutationProbabilities: [0.01],
            variants: ["vanilla"],
            activity: ActivityConfig(
                enabled: true,
                interval: 5,
                threshold: 0.05,
                maxComponents: 64,
                matchThreshold: 1.5,
                paramWeight: 1.0,
                positionWeight: 0.05
            )
        )
        let variant = FlowLeniaEcology2025VariantConfig(
            name: "vanilla",
            baseConfig: "vanilla-base.json",
            initPatchCount: 4,
            initPatchSize: 4,
            initParamMean: 0.0,
            initParamStd: 1.0,
            foodPatchCount: nil,
            foodPatchSize: nil,
            foodPatchValue: nil,
            foodSpawn: nil,
            dissipation: nil
        )

        let trial = try runFlowLeniaEcology2025Trial(
            simulation: simulation,
            variant: variant,
            baseConfigData: Data(contentsOf: configDirectory.appendingPathComponent("vanilla-base.json")),
            mutationProbability: 0.01,
            repeatIndex: 0,
            curatedSeeds: [],
            logger: Logger(label: "LeniaCoreTests.FlowLeniaEcology2025Replay")
        )
        let replay = try replayFlowLeniaEcology2025Payload(
            baseConfig: trial.replayBaseConfig,
            payload: trial.replayPayload,
            logger: Logger(label: "LeniaCoreTests.FlowLeniaEcology2025Replay.RoundTrip")
        )

        XCTAssertEqual(replay.runSummary.variant, trial.runSummary.variant)
        XCTAssertEqual(replay.runSummary.repeatIndex, trial.runSummary.repeatIndex)
        XCTAssertEqual(replay.runSummary.frames, trial.runSummary.frames)
        XCTAssertEqual(replay.runSummary.finalSpeciesCount, trial.runSummary.finalSpeciesCount)
        XCTAssertEqual(replay.runSummary.finalDiversity, trial.runSummary.finalDiversity, accuracy: 1e-6)
        XCTAssertEqual(replay.runSummary.finalNonNeutralActivity, trial.runSummary.finalNonNeutralActivity, accuracy: 1e-6)
        XCTAssertEqual(replay.runSummary.finalMass, trial.runSummary.finalMass, accuracy: 1e-6)
    }

    func testAIScientist2025PaperConfigsDecode() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let configDirectory = packageRoot.appendingPathComponent("configs/papers/ai-scientist-2025", isDirectory: true)

        let bundle = try loadAIScientist2025ConfigBundle(configDirectory: configDirectory)

        XCTAssertEqual(bundle.explorer.paper, "exploring-flow-lenia-universes-with-a-curiosity-driven-ai-scientist-2025")
        XCTAssertEqual(bundle.explorer.gridSize, 256)
        XCTAssertEqual(bundle.explorer.totalSteps, 10_000)
        XCTAssertEqual(bundle.explorer.coverageBinsPerDimension, 5)
        XCTAssertEqual(bundle.explorer.coverageBoundsMode, "observed_archive")
        XCTAssertEqual(bundle.experiments.map(\.name), ["ecosystem", "movement"])
        XCTAssertEqual(bundle.experiments.first?.goalDimensions, ["ea", "mp4_bytes", "h3", "h4", "h5", "h6", "h7"])
        XCTAssertEqual(bundle.experiments.last?.iterations, 2_000)
    }

    func testAIScientist2025RunnerCompletesTinySmoke() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let sourceDirectory = packageRoot.appendingPathComponent("configs/papers/ai-scientist-2025", isDirectory: true)
        let tempRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let configDirectory = tempRoot.appendingPathComponent("configs", isDirectory: true)
        let outputDirectory = tempRoot.appendingPathComponent("output", isDirectory: true)
        try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
        try FileManager.default.copyItem(at: sourceDirectory, to: configDirectory)
        try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempRoot) }

        try overwriteJSONObject(at: configDirectory.appendingPathComponent("movement-base.json")) { json in
            json["grid"] = ["sx": 32, "sy": 32]
            json["run"] = ["steps": 20]
            json["environment"] = [
                "type": "cross_map",
                "depth": 1,
                "wall_thickness": 4,
                "wall_value": -10.0,
                "passage_width": 4
            ]
            json["init"] = [
                "seed": 0,
                "patches": [["center": [16, 16], "size": 8]],
                "a_uniform": ["low": 0.0, "high": 1.0],
                "p_uniform": ["low": 0.0, "high": 1.0]
            ]
            json["beam_mutation"] = [
                "enabled": true,
                "probability": 0.1,
                "patch_size": 4,
                "std": 1.0,
                "seed": 53
            ]
        }

        let explorer = AIScientist2025ExplorerConfig(
            paper: "exploring-flow-lenia-universes-with-a-curiosity-driven-ai-scientist-2025",
            gridSize: 32,
            totalSteps: 20,
            coverageBinsPerDimension: 5,
            coverageBoundsMode: "observed_archive",
            frameStride: 5,
            mp4Framerate: 10,
            evolutionaryActivityMetric: "non_neutral",
            experiments: ["movement"]
        )
        let experiment = AIScientist2025ExperimentConfig(
            name: "movement",
            mode: "movement",
            baseConfig: "movement-base.json",
            iterations: 3,
            bootstrapIterations: 1,
            initPatchCount: 4,
            initPatchSize: 4,
            initParamMean: 0.0,
            initParamStd: 1.0,
            initZoneOrigin: [0, 0],
            initZoneSize: 16,
            goalDimensions: ["center_x", "center_y"],
            mutationProbabilityRange: [0.001, 0.2],
            beamPatchSizeRange: [2, 4],
            parameterMutation: IMGEPMutationConfig(std: 0.1, clip: true),
            activity: ActivityConfig(
                enabled: true,
                interval: 5,
                threshold: 0.05,
                maxComponents: 64,
                matchThreshold: 1.5,
                paramWeight: 1.0,
                positionWeight: 0.05
            ),
            seed: 41,
            foodPatchCount: nil,
            foodPatchSize: nil,
            foodPatchValue: nil,
            foodSpawn: nil,
            dissipation: nil
        )
        let bundle = AIScientist2025ConfigBundle(
            configDirectory: configDirectory,
            explorer: explorer,
            experiments: [experiment]
        )

        let runner = AIScientist2025Runner(
            configs: bundle,
            logger: Logger(label: "LeniaCoreTests.AIScientist2025")
        )
        let summary = try runner.run(outputDirectory: outputDirectory)

        XCTAssertEqual(summary.experiments.count, 1)
        XCTAssertEqual(summary.experiments[0].records, 3)
        XCTAssertEqual(summary.experiments[0].mode, "movement")
        XCTAssertEqual(summary.experiments[0].maxima.count, 2)
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("movement/archive.jsonl").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("summary.json").path))
    }

    func testReactionDiffusion2023RunnerCompletesTinySmoke() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let sourceDirectory = packageRoot.appendingPathComponent("configs/papers/reaction-diffusion-lenia-2023", isDirectory: true)
        let orbiumSource = packageRoot.appendingPathComponent("configs/presets/orbium_like_classic_1c_128.json")
        let tempRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let configDirectory = tempRoot.appendingPathComponent("configs", isDirectory: true)
        let outputDirectory = tempRoot.appendingPathComponent("output", isDirectory: true)
        try FileManager.default.createDirectory(at: configDirectory, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempRoot) }

        for filename in ["asymptotic.json", "validation.json", "rd_emulation.json"] {
            try FileManager.default.copyItem(
                at: sourceDirectory.appendingPathComponent(filename),
                to: configDirectory.appendingPathComponent(filename)
            )
        }
        let orbiumTarget = configDirectory.appendingPathComponent("orbium_test.json")
        try FileManager.default.copyItem(at: orbiumSource, to: orbiumTarget)

        func rewriteJSON(at url: URL, transform: (inout [String: Any]) throws -> Void) throws {
            let data = try Data(contentsOf: url)
            var object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
            try transform(&object)
            let rewritten = try JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys])
            try rewritten.write(to: url)
        }

        try rewriteJSON(at: configDirectory.appendingPathComponent("asymptotic.json")) { root in
            root["orbium_config"] = "orbium_test.json"
            root["dt_values"] = [0.1, 0.01]
        }
        try rewriteJSON(at: orbiumTarget) { root in
            root["run"] = ["steps": 20]
            root["flow"] = ["dt": 0.1, "n": 2, "theta_A": 2.0]
            root["init"] = [
                "seed": 3,
                "patches": [["center": [64, 64], "size": 40]],
                "a_uniform": ["low": 0.0, "high": 1.0],
                "p_uniform": NSNull()
            ]
        }

        let bundle = try loadReactionDiffusionLenia2023ConfigBundle(configDirectory: configDirectory)
        let runner = ReactionDiffusionLenia2023Runner(
            configs: bundle,
            logger: Logger(label: "LeniaCoreTests.ReactionDiffusion2023")
        )
        let summary = try runner.run(outputDirectory: outputDirectory)

        XCTAssertEqual(summary.original.count, 2)
        XCTAssertEqual(summary.asymptotic.count, 2)
        XCTAssertEqual(summary.clipping.dt, 0.01, accuracy: 1e-6)
        XCTAssertEqual(summary.kernelEmulation.coefficients.count, 40)
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("summary.json").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("kernel-emulation.json").path))
    }

    func testAtlas2026RunnerCompletesTinySmoke() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let sourceDirectory = packageRoot.appendingPathComponent("configs/papers/lenia-atlas-2026", isDirectory: true)
        let tempRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let configDirectory = tempRoot.appendingPathComponent("configs", isDirectory: true)
        let outputDirectory = tempRoot.appendingPathComponent("output", isDirectory: true)
        try FileManager.default.createDirectory(at: configDirectory, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempRoot) }

        for filename in ["kernel.json", "sweep.json", "init.json", "classifier.json"] {
            try FileManager.default.copyItem(
                at: sourceDirectory.appendingPathComponent(filename),
                to: configDirectory.appendingPathComponent(filename)
            )
        }

        try rewriteJSONFile(at: configDirectory.appendingPathComponent("kernel.json")) { root in
            root["array_size"] = 16
            root["radius"] = 3
        }

        try rewriteJSONFile(at: configDirectory.appendingPathComponent("sweep.json")) { root in
            root["mu"] = ["start": 0.14, "stop": 0.16, "step": 0.01]
            root["sigma"] = ["start": 0.015, "stop": 0.025, "step": 0.01]
            root["batch_size"] = 2
            root["samples_per_polygon"] = 2
            root["polygon_sizes"] = [4, 8]
            root["refine_transitions"] = false
        }

        try rewriteJSONFile(at: configDirectory.appendingPathComponent("init.json")) { root in
            root["polygon_library_size"] = 2
        }

        try rewriteJSONFile(at: configDirectory.appendingPathComponent("classifier.json")) { root in
            root["window_size"] = 3
            root["std"] = 1.5
            root["short_tmax_multiplier"] = 4
            root["long_tmax_multiplier"] = 8
        }

        let bundle = try loadAtlas2026ConfigBundle(configDirectory: configDirectory)
        let runner = Atlas2026Runner(
            configs: bundle,
            logger: Logger(label: "LeniaCoreTests.Atlas2026")
        )
        let summary = try runner.run(outputDirectory: outputDirectory)

        XCTAssertEqual(summary.systems, 2)
        XCTAssertEqual(summary.muCount, 2)
        XCTAssertEqual(summary.sigmaCount, 1)
        XCTAssertEqual(summary.polygonSizes, [4, 8])
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("summary.json").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("data/phases/\(summary.kernelKey).json").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("data/kernels/\(summary.kernelKey)/mu_0.14/sigma_0.015.json").path))
    }

    func testAtlas2026RunnerSupportsExternalPolygonLibraryJSON() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let sourceDirectory = packageRoot.appendingPathComponent("configs/papers/lenia-atlas-2026", isDirectory: true)
        let tempRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let configDirectory = tempRoot.appendingPathComponent("configs", isDirectory: true)
        let outputDirectory = tempRoot.appendingPathComponent("output", isDirectory: true)
        let libraryURL = tempRoot.appendingPathComponent("polygons.json")
        try FileManager.default.createDirectory(at: configDirectory, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempRoot) }

        for filename in ["kernel.json", "sweep.json", "init.json", "classifier.json"] {
            try FileManager.default.copyItem(
                at: sourceDirectory.appendingPathComponent(filename),
                to: configDirectory.appendingPathComponent(filename)
            )
        }

        let libraryRoot: [String: Any] = [
            "seed": 42,
            "4": [
                [
                    [1, 1],
                    [1, 1]
                ],
                [
                    [1, 0],
                    [1, 1]
                ]
            ],
            "8": [
                [
                    [1, 1, 0],
                    [1, 1, 1]
                ],
                [
                    [0, 1, 1],
                    [1, 1, 1]
                ]
            ]
        ]
        let libraryData = try JSONSerialization.data(withJSONObject: libraryRoot, options: [.prettyPrinted, .sortedKeys])
        try libraryData.write(to: libraryURL)

        try rewriteJSONFile(at: configDirectory.appendingPathComponent("kernel.json")) { root in
            root["array_size"] = 16
            root["radius"] = 3
        }

        try rewriteJSONFile(at: configDirectory.appendingPathComponent("sweep.json")) { root in
            root["mu"] = ["start": 0.14, "stop": 0.16, "step": 0.01]
            root["sigma"] = ["start": 0.015, "stop": 0.025, "step": 0.01]
            root["batch_size"] = 2
            root["samples_per_polygon"] = 2
            root["polygon_sizes"] = [4, 8]
            root["refine_transitions"] = false
        }

        try rewriteJSONFile(at: configDirectory.appendingPathComponent("init.json")) { root in
            root["polygon_library_size"] = 2
            root["polygon_library_json_path"] = "polygons.json"
        }

        try FileManager.default.copyItem(at: libraryURL, to: configDirectory.appendingPathComponent("polygons.json"))

        try rewriteJSONFile(at: configDirectory.appendingPathComponent("classifier.json")) { root in
            root["window_size"] = 3
            root["std"] = 1.5
            root["short_tmax_multiplier"] = 4
            root["long_tmax_multiplier"] = 8
        }

        let bundle = try loadAtlas2026ConfigBundle(configDirectory: configDirectory)
        let runner = Atlas2026Runner(
            configs: bundle,
            logger: Logger(label: "LeniaCoreTests.Atlas2026.ExternalJSON")
        )
        let summary = try runner.run(outputDirectory: outputDirectory)

        XCTAssertEqual(summary.systems, 2)
        XCTAssertTrue(FileManager.default.fileExists(atPath: outputDirectory.appendingPathComponent("data/phases/\(summary.kernelKey).json").path))
    }

    func testBuildWarmCreatureStampIsDeterministic() {
        let (_, _, _, params) = makeTestSetup()
        let stampID = UUID(uuidString: "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE")!

        let first = buildWarmCreatureStamp(
            id: stampID,
            name: "Test",
            params: params,
            seed: 17,
            warmupSteps: 24,
            warmupGridSize: 64,
            cropThreshold: 0.01,
            padding: 4
        )
        let second = buildWarmCreatureStamp(
            id: stampID,
            name: "Test",
            params: params,
            seed: 17,
            warmupSteps: 24,
            warmupGridSize: 64,
            cropThreshold: 0.01,
            padding: 4
        )

        XCTAssertEqual(first.id, second.id)
        XCTAssertEqual(first.width, second.width)
        XCTAssertEqual(first.height, second.height)
        XCTAssertEqual(first.parameterCount, second.parameterCount)
        XCTAssertEqual(first.mass, second.mass)
        XCTAssertEqual(first.params, second.params)
        XCTAssertGreaterThan(first.mass.reduce(0, +), 0.0)
    }

    func testFlowSandboxRuntimeDefaultsToMetalFullBackend() async {
        let (_, _, _, params) = makeTestSetup()
        let runtime = FlowSandboxRuntime(params: params, gridPreset: .compact128)
        let backend = await runtime.backend
        XCTAssertEqual(backend, .metalFull)
    }

    func testFlowSandboxMetalFullMatchesMLXStep() {
        let params = makeSandboxMetalParityParams()
        let config = flowSandboxConfig(gridSize: 32, nbK: params.r.count)
        let c0 = Array(repeating: 0, count: params.r.count)
        let c1 = [Array(0..<params.r.count)]
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)

        let mass = flowSandboxSeedState(seed: 23, gridSize: 32)
        let embeddedParams = flowSandboxParameterField(
            mass: mass,
            parameterValues: params.h,
            threshold: 0.01
        )

        let mlxEngine = FlowLeniaParamsBatched(
            config: config,
            kernels: kernels,
            mixMode: "avg",
            mixSeed: nil
        )
        let metalEngine = FlowLeniaSandboxMetalEngine(config: config, kernels: kernels)

        let expected = mlxEngine.step(mass, embeddedParams)
        let actual = metalEngine.step(mass, embeddedParams)

        XCTAssertLessThan(maxAbsDiff(expected.0, actual.0), 1e-4)
        XCTAssertLessThan(
            maxParamDiffOnMassSupport(
                expected: expected.1,
                actual: actual.1,
                support: expected.0,
                threshold: 1e-5
            ),
            1e-4
        )
    }

    func testFlowSandboxMetalFullMatchesMLXStepWithWallPotential() {
        let params = makeSandboxMetalParityParams()
        let config = flowSandboxConfig(gridSize: 32, nbK: params.r.count)
        let c0 = Array(repeating: 0, count: params.r.count)
        let c1 = [Array(0..<params.r.count)]
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)

        let mass = flowSandboxSeedState(seed: 33, gridSize: 32)
        let embeddedParams = flowSandboxParameterField(
            mass: mass,
            parameterValues: params.h,
            threshold: 0.01
        )

        var wallPotentialValues = [Float](repeating: 0.0, count: config.sx * config.sy)
        for x in 10..<22 {
            for y in 14..<18 {
                wallPotentialValues[x * config.sy + y] = -4.0
            }
        }
        let wallPotential = MLXArray(wallPotentialValues).reshaped([1, config.sx, config.sy, 1])

        let mlxEngine = FlowLeniaParamsBatched(
            config: config,
            kernels: kernels,
            mixMode: "avg",
            mixSeed: nil,
            wallPotential: wallPotential
        )
        let metalEngine = FlowLeniaSandboxMetalEngine(config: config, kernels: kernels, wallPotential: wallPotential)

        let expected = mlxEngine.step(mass, embeddedParams)
        let actual = metalEngine.step(mass, embeddedParams)

        XCTAssertLessThan(maxAbsDiff(expected.0, actual.0), 1e-4)
        XCTAssertLessThan(
            maxParamDiffOnMassSupport(
                expected: expected.1,
                actual: actual.1,
                support: expected.0,
                threshold: 1e-5
            ),
            1e-4
        )
    }

    func testFlowSandboxMetalFullStagesMatchReferenceMathWithWallPotential() {
        let params = makeSandboxMetalParityParams()
        let config = flowSandboxConfig(gridSize: 32, nbK: params.r.count)
        let c0 = Array(repeating: 0, count: params.r.count)
        let c1 = [[0]]
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)
        let mass = flowSandboxSeedState(seed: 37, gridSize: 32)
        let embeddedParams = flowSandboxParameterField(
            mass: mass,
            parameterValues: params.h,
            threshold: 0.01
        )

        var wallPotentialValues = [Float](repeating: 0.0, count: config.sx * config.sy)
        for x in 8..<24 {
            wallPotentialValues[x * config.sy + 11] = -1.75
        }
        let wallPotential = MLXArray(wallPotentialValues).reshaped([1, config.sx, config.sy, 1])

        let metalEngine = FlowLeniaSandboxMetalEngine(config: config, kernels: kernels, wallPotential: wallPotential)
        let staged = metalEngine.stagedStep(mass, embeddedParams, captureStages: true)
        let expectedStages = flowSandboxReferenceStages(
            mass: mass,
            params: embeddedParams,
            kernels: kernels,
            config: config,
            wallPotential: wallPotential
        )

        let actualStages = try! XCTUnwrap(staged.stages)
        XCTAssertLessThan(maxAbsDiff(expectedStages.preparedMass, actualStages.preparedMass), 1e-6)
        XCTAssertLessThan(maxAbsDiff(expectedStages.uk, actualStages.uk), 1e-4)
        XCTAssertLessThan(maxAbsDiff(expectedStages.scalarField, actualStages.scalarField), 1e-4)
        XCTAssertLessThan(maxAbsDiff(expectedStages.flow, actualStages.flow), 1e-4)
    }

    func testFlowSandboxMetalFullTracksMLXOverShortTrajectory() {
        let params = makeSandboxMetalParityParams()
        let config = flowSandboxConfig(gridSize: 32, nbK: params.r.count)
        let c0 = Array(repeating: 0, count: params.r.count)
        let c1 = [Array(0..<params.r.count)]
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)

        let mlxEngine = FlowLeniaParamsBatched(
            config: config,
            kernels: kernels,
            mixMode: "avg",
            mixSeed: nil
        )
        let metalEngine = FlowLeniaSandboxMetalEngine(config: config, kernels: kernels)

        var expectedMass = flowSandboxSeedState(seed: 31, gridSize: 32)
        var expectedParams = flowSandboxParameterField(
            mass: expectedMass,
            parameterValues: params.h,
            threshold: 0.01
        )
        var actualMass = expectedMass
        var actualParams = expectedParams

        for _ in 0..<8 {
            let expected = mlxEngine.step(expectedMass, expectedParams)
            expectedMass = expected.0
            expectedParams = expected.1

            let actual = metalEngine.step(actualMass, actualParams)
            actualMass = actual.0
            actualParams = actual.1
        }

        XCTAssertLessThan(maxAbsDiff(expectedMass, actualMass), 1e-3)
        XCTAssertLessThan(
            maxParamDiffOnMassSupport(
                expected: expectedParams,
                actual: actualParams,
                support: expectedMass,
                threshold: 1e-5
            ),
            1e-3
        )
    }

    func testFlowSandboxMetalFullMatchesMLXStepForBatchedSamples() {
        let params = makeSandboxMetalParityParams()
        let config = flowSandboxConfig(gridSize: 32, nbK: params.r.count)
        let c0 = Array(repeating: 0, count: params.r.count)
        let c1 = [Array(0..<params.r.count)]
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)

        let mass = MLX.stacked([
            flowSandboxSeedState(seed: 41, gridSize: 32)[0, 0..., 0..., 0...],
            flowSandboxSeedState(seed: 43, gridSize: 32)[0, 0..., 0..., 0...],
        ])
        let embeddedParams = flowSandboxParameterField(
            mass: mass,
            parameterValues: params.h,
            threshold: 0.01
        )

        let mlxEngine = FlowLeniaParamsBatched(
            config: config,
            kernels: kernels,
            mixMode: "avg",
            mixSeed: nil
        )
        let metalEngine = FlowLeniaSandboxMetalEngine(config: config, kernels: kernels)

        let expected = mlxEngine.step(mass, embeddedParams)
        let actual = metalEngine.step(mass, embeddedParams)

        XCTAssertLessThan(maxAbsDiff(expected.0, actual.0), 1e-4)
        XCTAssertLessThan(
            maxParamDiffOnMassSupport(
                expected: expected.1,
                actual: actual.1,
                support: expected.0,
                threshold: 1e-5
            ),
            1e-4
        )
    }

    func testFlowSandboxMetalBackendsSupportPerSampleKernelBatches() {
        let paramsA = makeSandboxMetalParityParams()
        let paramsB = ResolvedParams(
            r: [0.37, 0.91],
            b: [
                [1.0, 0.0, 0.0],
                [0.8, 0.2, 0.0]
            ],
            w: [
                [0.14, 0.21, 0.14],
                [0.1, 0.17, 0.1]
            ],
            a: [
                [0.28, 0.28, 0.28],
                [0.55, 0.55, 0.55]
            ],
            m: [0.11, 0.29],
            s: [0.04, 0.06],
            h: [0.34, 0.76],
            R: 6.5,
            seed: 0
        )
        let config = flowSandboxConfig(gridSize: 32, nbK: paramsA.r.count)
        let c0 = Array(repeating: 0, count: paramsA.r.count)
        let c1 = [Array(0..<paramsA.r.count)]
        let kernels = compilePopulationKernels(
            paramsBatch: [paramsA, paramsB],
            config: config,
            c0: c0,
            c1: c1
        )

        let sampleA = flowSandboxSeedState(seed: 71, gridSize: 32)[0, 0..., 0..., 0...].expandedDimensions(axis: 0)
        let sampleB = flowSandboxSeedState(seed: 73, gridSize: 32)[0, 0..., 0..., 0...].expandedDimensions(axis: 0)
        let mass = MLX.stacked([
            sampleA.squeezed(axis: 0),
            sampleB.squeezed(axis: 0),
        ])
        let embeddedParams = MLX.stacked([
            flowSandboxParameterField(mass: sampleA, parameterValues: paramsA.h, threshold: 0.01).squeezed(axis: 0),
            flowSandboxParameterField(mass: sampleB, parameterValues: paramsB.h, threshold: 0.01).squeezed(axis: 0),
        ])

        let mlxEngine = FlowLeniaParamsBatched(
            config: config,
            kernels: kernels,
            mixMode: "avg",
            mixSeed: nil
        )
        let expected = mlxEngine.step(mass, embeddedParams)

        let actual = FlowLeniaSandboxMetalEngine(config: config, kernels: kernels).step(mass, embeddedParams)
        XCTAssertLessThan(maxAbsDiff(expected.0, actual.0), 1e-4)
        XCTAssertLessThan(
            maxParamDiffOnMassSupport(
                expected: expected.1,
                actual: actual.1,
                support: expected.0,
                threshold: 1e-5
            ),
            1e-4
        )
    }

    func testFlowLeniaMetalFullStateRunnerTracksMLXOverShortTrajectory() {
        let params = makeSandboxMetalParityParams()
        let config = flowSandboxConfig(gridSize: 32, nbK: params.r.count)
        let c0 = Array(repeating: 0, count: params.r.count)
        let c1 = [Array(0..<params.r.count)]
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)

        var expectedMass = MLX.stacked([
            flowSandboxSeedState(seed: 61, gridSize: 32)[0, 0..., 0..., 0...],
            flowSandboxSeedState(seed: 67, gridSize: 32)[0, 0..., 0..., 0...],
        ])
        var expectedParams = flowSandboxParameterField(
            mass: expectedMass,
            parameterValues: params.h,
            threshold: 0.01
        )

        let runner = FlowLeniaMetalFullStateRunner(config: config, kernels: kernels, batchCount: 2)
        runner.setState(mass: expectedMass, params: expectedParams)
        let mlxEngine = FlowLeniaParamsBatched(
            config: config,
            kernels: kernels,
            mixMode: "avg",
            mixSeed: nil
        )

        for _ in 0..<6 {
            let expected = mlxEngine.step(expectedMass, expectedParams)
            expectedMass = expected.0
            expectedParams = expected.1
            runner.step()
        }

        let actual = runner.materializeState()
        XCTAssertLessThan(maxAbsDiff(expectedMass, actual.mass), 1e-3)
        XCTAssertLessThan(
            maxParamDiffOnMassSupport(
                expected: expectedParams,
                actual: actual.params,
                support: expectedMass,
                threshold: 1e-5
            ),
            1e-3
        )
    }

    func testFlowLeniaMetalFullStateRunnerTracksMaskedTrajectoryWithWallPotential() {
        let params = makeSandboxMetalParityParams()
        let config = flowSandboxConfig(gridSize: 32, nbK: params.r.count)
        let c0 = Array(repeating: 0, count: params.r.count)
        let c1 = [Array(0..<params.r.count)]
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)

        var wallPotentialValues = [Float](repeating: 0.0, count: config.sx * config.sy)
        for x in 4..<28 {
            wallPotentialValues[x * config.sy + 15] = -2.5
        }
        let wallPotential = MLXArray(wallPotentialValues).reshaped([1, config.sx, config.sy, 1])

        var wallMaskValues = [Float](repeating: 1.0, count: config.sx * config.sy)
        for x in 12..<20 {
            for y in 12..<20 {
                wallMaskValues[x * config.sy + y] = 0.0
            }
        }
        let wallMask = MLXArray(wallMaskValues).reshaped([1, config.sx, config.sy, 1])

        var expectedMass = MLX.stacked([
            flowSandboxSeedState(seed: 91, gridSize: 32)[0, 0..., 0..., 0...],
            flowSandboxSeedState(seed: 93, gridSize: 32)[0, 0..., 0..., 0...],
        ])
        var expectedParams = flowSandboxParameterField(
            mass: expectedMass,
            parameterValues: params.h,
            threshold: 0.01
        )
        expectedMass = expectedMass * wallMask
        expectedParams = expectedParams * wallMask

        let runner = FlowLeniaMetalFullStateRunner(
            config: config,
            kernels: kernels,
            batchCount: 2,
            wallPotential: wallPotential
        )
        runner.reset(
            mass: expectedMass,
            params: expectedParams,
            wallMask: wallMask,
            staticChannelFields: [],
            food: nil
        )
        let mlxEngine = FlowLeniaParamsBatched(
            config: config,
            kernels: kernels,
            mixMode: "avg",
            mixSeed: nil,
            wallPotential: wallPotential
        )

        for _ in 0..<6 {
            let expected = mlxEngine.step(expectedMass, expectedParams)
            expectedMass = expected.0 * wallMask
            expectedParams = expected.1 * wallMask
            runner.step()
        }

        let actual = runner.materializeState()
        XCTAssertLessThan(maxAbsDiff(expectedMass, actual.mass), 1e-3)
        XCTAssertLessThan(
            maxParamDiffOnMassSupport(
                expected: expectedParams,
                actual: actual.params,
                support: expectedMass,
                threshold: 1e-5
            ),
            1e-3
        )
    }

    func testFlowLeniaMetalFullStateRunnerSummaryMatchesMaterializedMetrics() {
        let params = makeSandboxMetalParityParams()
        let config = flowSandboxConfig(gridSize: 32, nbK: params.r.count)
        let c0 = Array(repeating: 0, count: params.r.count)
        let c1 = [Array(0..<params.r.count)]
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)

        let initialMass = MLX.stacked([
            flowSandboxSeedState(seed: 71, gridSize: 32)[0, 0..., 0..., 0...],
            flowSandboxSeedState(seed: 79, gridSize: 32)[0, 0..., 0..., 0...],
        ])
        let initialParams = flowSandboxParameterField(
            mass: initialMass,
            parameterValues: params.h,
            threshold: 0.01
        )

        let runner = FlowLeniaMetalFullStateRunner(config: config, kernels: kernels, batchCount: 2)
        runner.setState(mass: initialMass, params: initialParams)
        runner.step(count: 4)

        let materialized = runner.materializeMass()
        let summary = runner.summarizeMass(occupancyThreshold: 0.05, includeGyration: true)
        let massMap = materialized[0..., 0..., 0..., 0]
        let totalArr = massMap.sum(axes: [1, 2])
        let sumSqArr = (massMap * massMap).sum(axes: [1, 2])
        let occupancyArr = MLX.greater(massMap, MLXArray(Float(0.05))).asType(.float32).sum(axes: [1, 2])
        let gridX = MLXArray(Array(0..<config.sx).map(Float.init)).reshaped([1, config.sx, 1])
        let gridY = MLXArray(Array(0..<config.sy).map(Float.init)).reshaped([1, 1, config.sy])
        let totalSafe = MLX.maximum(totalArr, MLXArray(Float(1e-6)))
        let centerXArr = (massMap * gridX).sum(axes: [1, 2]) / totalSafe
        let centerYArr = (massMap * gridY).sum(axes: [1, 2]) / totalSafe
        let centerXGrid = centerXArr.expandedDimensions(axes: [1, 2])
        let centerYGrid = centerYArr.expandedDimensions(axes: [1, 2])
        let dxRaw = MLX.abs(gridX - centerXGrid)
        let dyRaw = MLX.abs(gridY - centerYGrid)
        let dx = MLX.minimum(dxRaw, MLXArray(Float(config.sx)) - dxRaw)
        let dy = MLX.minimum(dyRaw, MLXArray(Float(config.sy)) - dyRaw)
        let gyrationArr = (massMap * (dx * dx + dy * dy)).sum(axes: [1, 2]) / totalSafe
        eval(totalArr, sumSqArr, occupancyArr, centerXArr, centerYArr, gyrationArr)

        let totals = totalArr.asArray(Float.self)
        let sumSquares = sumSqArr.asArray(Float.self)
        let occupancy = occupancyArr.asArray(Float.self)
        let centersX = centerXArr.asArray(Float.self)
        let centersY = centerYArr.asArray(Float.self)
        let gyration = gyrationArr.asArray(Float.self)

        XCTAssertEqual(summary.totalMass.count, totals.count)
        XCTAssertEqual(summary.rawGyration?.count, gyration.count)
        for index in 0..<totals.count {
            XCTAssertEqual(summary.totalMass[index], totals[index], accuracy: 1e-3)
            XCTAssertEqual(summary.sumSquares[index], sumSquares[index], accuracy: 1e-3)
            XCTAssertEqual(summary.occupancyCount[index], occupancy[index], accuracy: 1e-3)
            XCTAssertEqual(summary.centerXIndex[index], centersX[index], accuracy: 1e-3)
            XCTAssertEqual(summary.centerYIndex[index], centersY[index], accuracy: 1e-3)
            XCTAssertEqual(summary.rawGyration?[index] ?? 0.0, gyration[index], accuracy: 1e-3)
        }
    }

    func testFlowLeniaMetalFullStateRunnerFoodMassSummaryMatchesMaterializedFood() {
        let params = makeSandboxMetalParityParams()
        let config = flowSandboxConfig(gridSize: 16, nbK: params.r.count)
        let c0 = Array(repeating: 0, count: params.r.count)
        let c1 = [Array(0..<params.r.count)]
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)

        let batchCount = 3
        var foodValues = [Float](repeating: 0, count: batchCount * config.sx * config.sy)
        var expected = [Float](repeating: 0, count: batchCount)
        for batch in 0..<batchCount {
            for x in 0..<config.sx {
                for y in 0..<config.sy {
                    let index = ((batch * config.sx) + x) * config.sy + y
                    let value = Float(((batch + 1) * (x + 3) + y) % 11) / 37.0
                    foodValues[index] = value
                    expected[batch] += value
                }
            }
        }

        let runner = FlowLeniaMetalFullStateRunner(config: config, kernels: kernels, batchCount: batchCount)
        XCTAssertNil(runner.summarizeFoodMass())
        runner.reset(
            mass: MLX.zeros([batchCount, config.sx, config.sy, config.channels]),
            params: MLX.zeros([batchCount, config.sx, config.sy, runner.parameterCount]),
            wallMask: nil,
            staticChannelFields: [],
            food: FlowLeniaMetalFoodState(
                channelIndex: 0,
                field: MLXArray(foodValues).reshaped([batchCount, config.sx, config.sy]),
                decayRate: 0.0,
                digestRate: 0.0
            )
        )

        let summary = runner.summarizeFoodMass()
        let materialized = runner.materializeFood()!
        let materializedSum = materialized.sum(axes: [1, 2])
        eval(materializedSum)
        let materializedTotals = materializedSum.asArray(Float.self)

        XCTAssertEqual(summary?.count, batchCount)
        for batch in 0..<batchCount {
            XCTAssertEqual(summary?[batch] ?? -1, expected[batch], accuracy: 1e-3)
            XCTAssertEqual(summary?[batch] ?? -1, materializedTotals[batch], accuracy: 1e-3)
        }
    }

    func testFlowLeniaMetalFullStateRunnerResetReplacesConfigurationAndState() throws {
        let params = makeSandboxMetalParityParams()
        let config = flowMetalTestConfig(gridSize: 8, nbK: params.r.count)
        let kernels = compileKernels(
            params: params,
            config: config,
            c0: [0, 1],
            c1: [[0], [1], []]
        )
        let cellCount = config.sx * config.sy
        let cells = 0..<cellCount
        let massValues = cells.flatMap { cell in
            (0..<config.channels).map { Float(cell + $0 + 1) / 101.0 }
        }
        let paramValues = cells.flatMap { cell in
            params.h.indices.map { Float(cell + $0 + 2) / 97.0 }
        }
        let wallValues = cells.map { cell in
            cell / config.sy == 0 || cell % config.sy == 0 ? Float(0) : Float(1)
        }
        let staticValues = cells.map { cell in
            Float(cell / config.sy + 2 * (cell % config.sy) + 1) / 31.0
        }
        let foodValues = cells.map { cell in
            Float(2 * (cell / config.sy) + cell % config.sy + 3) / 37.0
        }

        func assertConfiguredState(
            _ runner: FlowLeniaMetalFullStateRunner,
            mass: MLXArray,
            params: MLXArray,
            wallMask: MLXArray,
            staticField: MLXArray,
            foodField: MLXArray,
            file: StaticString = #filePath,
            line: UInt = #line
        ) throws {
            let actual = runner.materializeState()
            let actualFood = try XCTUnwrap(runner.materializeFood(), file: file, line: line)
            let expectedMass = overwriteFieldChannel(
                overwriteFieldChannel(mass, field: staticField, channelIndex: 1),
                field: foodField,
                channelIndex: 2
            ) * wallMask
            let expectedParams = params * wallMask
            let expectedFood = foodField * wallMask.squeezed(axis: 3)
            XCTAssertLessThan(maxAbsDiff(expectedMass, actual.mass), 1e-6, file: file, line: line)
            XCTAssertLessThan(maxAbsDiff(expectedParams, actual.params), 1e-6, file: file, line: line)
            XCTAssertLessThan(maxAbsDiff(expectedFood, actualFood), 1e-6, file: file, line: line)
        }

        let mass = MLXArray(massValues).reshaped([1, config.sx, config.sy, config.channels])
        let paramMap = MLXArray(paramValues).reshaped([1, config.sx, config.sy, params.h.count])
        let wallMask = MLXArray(wallValues).reshaped([1, config.sx, config.sy, 1])
        let staticField = MLXArray(staticValues).reshaped([1, config.sx, config.sy, 1])
        let foodField = MLXArray(foodValues).reshaped([1, config.sx, config.sy])
        let runner = FlowLeniaMetalFullStateRunner(
            config: config,
            kernels: kernels,
            batchCount: 1,
            parameterMix: "stoch",
            mixSeed: 37
        )
        runner.reset(
            mass: mass,
            params: paramMap,
            wallMask: wallMask,
            staticChannelFields: [FlowLeniaMetalChannelField(
                channelIndex: 1,
                field: staticField
            )],
            food: FlowLeniaMetalFoodState(
                channelIndex: 2,
                field: foodField.squeezed(axis: 0),
                decayRate: 0,
                digestRate: 0
            )
        )
        try assertConfiguredState(
            runner,
            mass: mass,
            params: paramMap,
            wallMask: wallMask,
            staticField: staticField,
            foodField: foodField
        )

        runner.step()
        let replacementMass = MLXArray(massValues.reversed())
            .reshaped([1, config.sx, config.sy, config.channels])
        let replacementParams = MLXArray(paramValues.reversed())
            .reshaped([1, config.sx, config.sy, params.h.count])
        let replacementWallMask = MLXArray(wallValues.reversed())
            .reshaped([1, config.sx, config.sy, 1])
        let replacementStaticField = MLXArray(staticValues.reversed())
            .reshaped([1, config.sx, config.sy, 1])
        let replacementFoodField = MLXArray(foodValues.reversed())
            .reshaped([1, config.sx, config.sy])
        runner.reset(
            mass: replacementMass,
            params: replacementParams,
            wallMask: replacementWallMask,
            staticChannelFields: [FlowLeniaMetalChannelField(
                channelIndex: 1,
                field: replacementStaticField
            )],
            food: FlowLeniaMetalFoodState(
                channelIndex: 2,
                field: replacementFoodField,
                decayRate: 0,
                digestRate: 0
            )
        )
        try assertConfiguredState(
            runner,
            mass: replacementMass,
            params: replacementParams,
            wallMask: replacementWallMask,
            staticField: replacementStaticField,
            foodField: replacementFoodField
        )

        runner.step()
        runner.reset(
            mass: mass,
            params: paramMap,
            wallMask: nil,
            staticChannelFields: [],
            food: nil
        )

        let freshRunner = FlowLeniaMetalFullStateRunner(
            config: config,
            kernels: kernels,
            batchCount: 1,
            parameterMix: "stoch",
            mixSeed: 37
        )
        freshRunner.setState(mass: mass, params: paramMap)
        XCTAssertNil(runner.materializeFood())
        let resetState = runner.materializeState()
        XCTAssertLessThan(maxAbsDiff(mass, resetState.mass), 1e-6)
        XCTAssertLessThan(maxAbsDiff(paramMap, resetState.params), 1e-6)

        runner.step()
        freshRunner.step()
        let resetStep = runner.materializeState()
        let freshStep = freshRunner.materializeState()
        XCTAssertLessThan(maxAbsDiff(freshStep.mass, resetStep.mass), 1e-5)
        XCTAssertLessThan(maxAbsDiff(freshStep.params, resetStep.params), 1e-5)

        let convertedMass = mass.transposed(0, 2, 1, 3).asType(Float16.self)
        let convertedParams = paramMap.transposed(0, 2, 1, 3).asType(Float16.self)
        runner.setState(mass: convertedMass, params: convertedParams)
        let convertedState = runner.materializeState()
        XCTAssertLessThan(maxAbsDiff(convertedMass.asType(Float.self), convertedState.mass), 1e-6)
        XCTAssertLessThan(maxAbsDiff(convertedParams.asType(Float.self), convertedState.params), 1e-6)
    }

    func testFlowLeniaMetalFullStateRunnerMaterializesWeightedMassMap() {
        let params = makeSandboxMetalParityParams()
        let config = flowMetalTestConfig(gridSize: 8, nbK: params.r.count)
        let c0 = [0, 1]
        let c1 = [[0], [1], []]
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)

        let batchCount = 2
        var massValues = [Float](repeating: 0, count: batchCount * config.sx * config.sy * config.channels)
        var expected = [Float](repeating: 0, count: batchCount * config.sx * config.sy)
        let weights: [Float] = [1.0, 0.0, 0.25]
        for batch in 0..<batchCount {
            for x in 0..<config.sx {
                for y in 0..<config.sy {
                    let massBase = (((batch * config.sx) + x) * config.sy + y) * config.channels
                    let mapIndex = (batch * config.sx + x) * config.sy + y
                    massValues[massBase] = Float(batch + x + 1) / 17.0
                    massValues[massBase + 1] = Float(y + 2) / 19.0
                    massValues[massBase + 2] = Float((x + y + 3) % 7) / 23.0
                    expected[mapIndex] = massValues[massBase] + 0.25 * massValues[massBase + 2]
                }
            }
        }
        let mass = MLXArray(massValues).reshaped([batchCount, config.sx, config.sy, config.channels])
        let parameterCount = params.h.count
        let paramsMap = MLXArray([Float](repeating: 0.2, count: batchCount * config.sx * config.sy * parameterCount))
            .reshaped([batchCount, config.sx, config.sy, parameterCount])

        let runner = FlowLeniaMetalFullStateRunner(config: config, kernels: kernels, batchCount: batchCount)
        runner.setState(mass: mass, params: paramsMap)
        let actual = runner.materializeMassMap(channelWeights: weights)
        eval(actual)

        XCTAssertEqual(actual.shape, [batchCount, config.sx, config.sy])
        let actualValues = actual.asArray(Float.self)
        for index in expected.indices {
            XCTAssertEqual(actualValues[index], expected[index], accuracy: 1e-5)
        }
    }

    func testFlowLeniaMetalFullStateRunnerSummarySupportsWeightedChannels() {
        let params = makeSandboxMetalParityParams()
        let config = flowMetalTestConfig(gridSize: 8, nbK: params.r.count)
        let c0 = [0, 1]
        let c1 = [[0], [1], []]
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)

        let batchCount = 2
        var massValues = [Float](repeating: 0, count: batchCount * config.sx * config.sy * config.channels)
        for batch in 0..<batchCount {
            for x in 0..<config.sx {
                for y in 0..<config.sy {
                    let base = (((batch * config.sx) + x) * config.sy + y) * config.channels
                    massValues[base] = Float((batch + 1) * (x + 1)) / 100.0
                    massValues[base + 1] = Float(y + 1) / 50.0
                    massValues[base + 2] = Float((x + y + 1) % 5) / 40.0
                }
            }
        }
        let mass = MLXArray(massValues).reshaped([batchCount, config.sx, config.sy, config.channels])
        let parameterCount = params.h.count
        let paramValues = [Float](repeating: 0.25, count: batchCount * config.sx * config.sy * parameterCount)
        let paramMap = MLXArray(paramValues).reshaped([batchCount, config.sx, config.sy, parameterCount])
        let weights: [Float] = [1.0, 0.0, 1.0]

        let runner = FlowLeniaMetalFullStateRunner(config: config, kernels: kernels, batchCount: batchCount)
        runner.setState(mass: mass, params: paramMap)
        let synchronizationCount = runner.massObservationSynchronizationCount
        let observation = runner.observeMass(
            occupancyThreshold: 0.05,
            includeGyration: true,
            channelWeights: weights,
            materializeMap: true
        )
        let summary = observation.summary
        let observedMassMap = observation.massMap!.asArray(Float.self)

        XCTAssertEqual(runner.massObservationSynchronizationCount - synchronizationCount, 1)

        var expectedTotal = [Float](repeating: 0, count: batchCount)
        var expectedSumSquares = [Float](repeating: 0, count: batchCount)
        var expectedEnergy = [Float](repeating: 0, count: batchCount)
        var expectedOccupancy = [Float](repeating: 0, count: batchCount)
        var expectedWeightedX = [Float](repeating: 0, count: batchCount)
        var expectedWeightedY = [Float](repeating: 0, count: batchCount)
        for batch in 0..<batchCount {
            for x in 0..<config.sx {
                for y in 0..<config.sy {
                    let base = (((batch * config.sx) + x) * config.sy + y) * config.channels
                    let v0 = massValues[base]
                    let v2 = massValues[base + 2]
                    let reduced = v0 + v2
                    let mapIndex = (batch * config.sx + x) * config.sy + y
                    XCTAssertEqual(observedMassMap[mapIndex], reduced, accuracy: 1e-6)
                    expectedTotal[batch] += reduced
                    expectedSumSquares[batch] += reduced * reduced
                    expectedEnergy[batch] += v0 * v0 + v2 * v2
                    expectedOccupancy[batch] += reduced > 0.05 ? 1.0 : 0.0
                    expectedWeightedX[batch] += reduced * Float(x)
                    expectedWeightedY[batch] += reduced * Float(y)
                }
            }
        }

        XCTAssertEqual(summary.totalMass.count, batchCount)
        XCTAssertEqual(summary.energy.count, batchCount)
        for batch in 0..<batchCount {
            let centerX = expectedWeightedX[batch] / expectedTotal[batch]
            let centerY = expectedWeightedY[batch] / expectedTotal[batch]
            var expectedGyration: Float = 0
            for x in 0..<config.sx {
                for y in 0..<config.sy {
                    let base = (((batch * config.sx) + x) * config.sy + y) * config.channels
                    let reduced = massValues[base] + massValues[base + 2]
                    let dxRaw = abs(Float(x) - centerX)
                    let dyRaw = abs(Float(y) - centerY)
                    let dx = min(dxRaw, Float(config.sx) - dxRaw)
                    let dy = min(dyRaw, Float(config.sy) - dyRaw)
                    expectedGyration += reduced * (dx * dx + dy * dy)
                }
            }
            XCTAssertEqual(summary.totalMass[batch], expectedTotal[batch], accuracy: 1e-3)
            XCTAssertEqual(summary.sumSquares[batch], expectedSumSquares[batch], accuracy: 1e-3)
            XCTAssertEqual(summary.energy[batch], expectedEnergy[batch], accuracy: 1e-3)
            XCTAssertEqual(summary.occupancyCount[batch], expectedOccupancy[batch], accuracy: 1e-3)
            XCTAssertEqual(summary.centerXIndex[batch], centerX, accuracy: 1e-3)
            XCTAssertEqual(summary.centerYIndex[batch], centerY, accuracy: 1e-3)
            XCTAssertEqual(summary.rawGyration?[batch] ?? 0.0, expectedGyration / expectedTotal[batch], accuracy: 1e-3)
        }
    }

    func testFlowLeniaMetalFullStateRunnerKernelUpdatesTrackMLX() {
        let paramsA = makeSandboxMetalParityParams()
        let paramsB = ResolvedParams(
            r: [0.37, 0.91],
            b: [
                [1.0, 0.0, 0.0],
                [0.8, 0.2, 0.0]
            ],
            w: [
                [0.14, 0.21, 0.14],
                [0.1, 0.17, 0.1]
            ],
            a: [
                [0.28, 0.28, 0.28],
                [0.55, 0.55, 0.55]
            ],
            m: [0.11, 0.29],
            s: [0.04, 0.06],
            h: [0.34, 0.76],
            R: 6.5,
            seed: 0
        )
        let config = flowSandboxConfig(gridSize: 32, nbK: paramsA.r.count)
        let c0 = Array(repeating: 0, count: paramsA.r.count)
        let c1 = [Array(0..<paramsA.r.count)]
        let initialKernels = compilePopulationKernels(
            paramsBatch: [paramsA, paramsB],
            config: config,
            c0: c0,
            c1: c1
        )
        let updatedKernels = compilePopulationKernels(
            paramsBatch: [paramsB, paramsA],
            config: config,
            c0: c0,
            c1: c1
        )
        let runner = FlowLeniaMetalFullStateRunner(config: config, kernels: initialKernels, batchCount: 2)

        let warmupMass = MLX.stacked([
            flowSandboxSeedState(seed: 81, gridSize: 32)[0, 0..., 0..., 0...],
            flowSandboxSeedState(seed: 83, gridSize: 32)[0, 0..., 0..., 0...],
        ])
        let warmupParams = MLX.stacked([
            flowSandboxParameterField(
                mass: warmupMass[0].expandedDimensions(axis: 0),
                parameterValues: paramsA.h,
                threshold: 0.01
            ).squeezed(axis: 0),
            flowSandboxParameterField(
                mass: warmupMass[1].expandedDimensions(axis: 0),
                parameterValues: paramsB.h,
                threshold: 0.01
            ).squeezed(axis: 0),
        ])
        runner.setState(mass: warmupMass, params: warmupParams)
        runner.step(count: 2)

        runner.updateKernels(updatedKernels)
        var expectedMass = MLX.stacked([
            flowSandboxSeedState(seed: 89, gridSize: 32)[0, 0..., 0..., 0...],
            flowSandboxSeedState(seed: 97, gridSize: 32)[0, 0..., 0..., 0...],
        ])
        var expectedParams = MLX.stacked([
            flowSandboxParameterField(
                mass: expectedMass[0].expandedDimensions(axis: 0),
                parameterValues: paramsB.h,
                threshold: 0.01
            ).squeezed(axis: 0),
            flowSandboxParameterField(
                mass: expectedMass[1].expandedDimensions(axis: 0),
                parameterValues: paramsA.h,
                threshold: 0.01
            ).squeezed(axis: 0),
        ])
        runner.setState(mass: expectedMass, params: expectedParams)

        let mlxEngine = FlowLeniaParamsBatched(
            config: config,
            kernels: updatedKernels,
            mixMode: "avg",
            mixSeed: nil
        )

        for _ in 0..<4 {
            let expected = mlxEngine.step(expectedMass, expectedParams)
            expectedMass = expected.0
            expectedParams = expected.1
            runner.step()
        }

        let actual = runner.materializeState()
        XCTAssertLessThan(maxAbsDiff(expectedMass, actual.mass), 1e-3)
        XCTAssertLessThan(
            maxParamDiffOnMassSupport(
                expected: expectedParams,
                actual: actual.params,
                support: expectedMass,
                threshold: 1e-5
            ),
            1e-3
        )
    }

    func testFlowLeniaMetalFullStateRunnerKernelUpdatesPreserveMatterWeights() {
        let params = makeSandboxMetalParityParams()
        let config = flowMetalTestConfig(gridSize: 16, nbK: params.r.count)
        let kernels = compileKernels(
            params: params,
            config: config,
            c0: [0, 1],
            c1: [[0], [1], []]
        )
        let matterWeights: [Float] = [1.0, 1.0, 0.0]
        let cellCount = config.sx * config.sy
        var massValues = [Float](repeating: 0.0, count: cellCount * config.channels)
        for x in 0..<config.sx {
            for y in 0..<config.sy {
                let base = (x * config.sy + y) * config.channels
                let dx = x - config.sx / 2
                let dy = y - config.sy / 2
                massValues[base] = dx * dx + dy * dy < 20 ? 0.8 : 0.0
                massValues[base + 1] = (dx + 2) * (dx + 2) + (dy - 1) * (dy - 1) < 12 ? 0.5 : 0.0
                massValues[base + 2] = Float((x * 3 + y * 5) % 11) / 10.0
            }
        }
        let mass = MLXArray(massValues).reshaped([1, config.sx, config.sy, config.channels])
        let paramsMap = MLXArray(
            (0..<cellCount).flatMap { _ in params.h }
        ).reshaped([1, config.sx, config.sy, params.h.count])

        let expectedRunner = FlowLeniaMetalFullStateRunner(
            config: config,
            kernels: kernels,
            batchCount: 1,
            matterWeights: matterWeights
        )
        let updatedRunner = FlowLeniaMetalFullStateRunner(
            config: config,
            kernels: kernels,
            batchCount: 1,
            matterWeights: matterWeights
        )
        updatedRunner.updateKernels(kernels)
        expectedRunner.setState(mass: mass, params: paramsMap)
        updatedRunner.setState(mass: mass, params: paramsMap)
        expectedRunner.step()
        updatedRunner.step()

        let expected = expectedRunner.materializeState()
        let actual = updatedRunner.materializeState()
        XCTAssertLessThan(maxAbsDiff(expected.mass, actual.mass), 1e-5)
        XCTAssertLessThan(maxAbsDiff(expected.params, actual.params), 1e-5)
    }

    func testFlowSandboxMetalFullStagesMatchReferenceMath() {
        let params = makeSandboxMetalParityParams()
        let config = flowSandboxConfig(gridSize: 32, nbK: params.r.count)
        let c0 = Array(repeating: 0, count: params.r.count)
        let c1 = [[0]]
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)
        let mass = flowSandboxSeedState(seed: 47, gridSize: 32)
        let embeddedParams = flowSandboxParameterField(
            mass: mass,
            parameterValues: params.h,
            threshold: 0.01
        )

        let metalEngine = FlowLeniaSandboxMetalEngine(config: config, kernels: kernels)
        let staged = metalEngine.stagedStep(mass, embeddedParams, captureStages: true)
        let expectedStages = flowSandboxReferenceStages(
            mass: mass,
            params: embeddedParams,
            kernels: kernels,
            config: config
        )
        let expectedStep = FlowLeniaParamsBatched(
            config: config,
            kernels: kernels,
            mixMode: "avg",
            mixSeed: nil
        ).step(mass, embeddedParams)

        let actualStages = try! XCTUnwrap(staged.stages)
        XCTAssertLessThan(maxAbsDiff(expectedStages.preparedMass, actualStages.preparedMass), 1e-6)
        XCTAssertLessThan(maxAbsDiff(expectedStages.uk, actualStages.uk), 1e-4)
        XCTAssertLessThan(maxAbsDiff(expectedStages.scalarField, actualStages.scalarField), 1e-4)
        XCTAssertLessThan(maxAbsDiff(expectedStages.flow, actualStages.flow), 1e-4)
        XCTAssertLessThan(maxAbsDiff(expectedStep.0, staged.nextMass), 1e-4)
        XCTAssertLessThan(
            maxParamDiffOnMassSupport(
                expected: expectedStep.1,
                actual: staged.nextParams,
                support: expectedStep.0,
                threshold: 1e-5
            ),
            1e-4
        )
    }

    func testFlowSandboxMetalFullMatchesReferenceOnRectangularSmallTorus() {
        let params = makeSandboxMetalParityParams()
        let squareConfig = flowSandboxConfig(gridSize: 32, nbK: params.r.count)
        let config = BatchedConfig(
            sx: 16,
            sy: 24,
            channels: squareConfig.channels,
            nbK: squareConfig.nbK,
            dt: squareConfig.dt,
            dd: squareConfig.dd,
            sigma: squareConfig.sigma,
            n: squareConfig.n,
            thetaA: squareConfig.thetaA,
            border: squareConfig.border,
            implementation: squareConfig.implementation,
            chemChannel: nil,
            chemIncludeInMass: true
        )
        let c0 = Array(repeating: 0, count: params.r.count)
        let c1 = [Array(0..<params.r.count)]
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)
        let mass = makePatchState(sx: config.sx, sy: config.sy, channels: config.channels)
            .expandedDimensions(axis: 0)
        let embeddedParams = flowSandboxParameterField(
            mass: mass,
            parameterValues: params.h,
            threshold: 0.01
        )

        let staged = FlowLeniaSandboxMetalEngine(config: config, kernels: kernels)
            .stagedStep(mass, embeddedParams, captureStages: true)
        let expectedStages = flowSandboxReferenceStages(
            mass: mass,
            params: embeddedParams,
            kernels: kernels,
            config: config
        )
        let expected = FlowLeniaParamsBatched(
            config: config,
            kernels: kernels,
            mixMode: "avg",
            mixSeed: nil
        )
            .step(mass, embeddedParams)
        let actualStages = try! XCTUnwrap(staged.stages)

        XCTAssertLessThan(maxAbsDiff(expectedStages.uk, actualStages.uk), 1e-4)
        XCTAssertLessThan(maxAbsDiff(expectedStages.flow, actualStages.flow), 1e-4)
        XCTAssertLessThan(maxAbsDiff(expected.0, staged.nextMass), 1e-4)
        XCTAssertLessThan(
            maxParamDiffOnMassSupport(
                expected: expected.1,
                actual: staged.nextParams,
                support: expected.0,
                threshold: 1e-5
            ),
            1e-4
        )
    }

    func testFlowSandboxMetalStageProfilerReportsPositiveTimings() {
        let params = makeSandboxMetalParityParams()
        let config = flowSandboxConfig(gridSize: 32, nbK: params.r.count)
        let c0 = Array(repeating: 0, count: params.r.count)
        let c1 = [Array(0..<params.r.count)]
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)
        let mass = flowSandboxSeedState(seed: 53, gridSize: 32)
        let embeddedParams = flowSandboxParameterField(
            mass: mass,
            parameterValues: params.h,
            threshold: 0.01
        )

        let timings = profileFlowSandboxMetalStages(
            config: config,
            kernels: kernels,
            initialMass: mass,
            initialParams: embeddedParams,
            steps: 2
        )

        XCTAssertGreaterThan(timings.totalMs, 0.0)
        XCTAssertGreaterThanOrEqual(timings.prepareMs, 0.0)
        XCTAssertGreaterThanOrEqual(timings.fftMs, 0.0)
        XCTAssertGreaterThanOrEqual(timings.growthReduceMs, 0.0)
        XCTAssertGreaterThanOrEqual(timings.flowMs, 0.0)
        XCTAssertGreaterThanOrEqual(timings.reintegrateMs, 0.0)
    }

    func testSearchEngineMetalBackendsTrackMLXOverShortRunBatch() {
        let searchConfig = SearchConfig(
            steps: 8,
            recordInterval: 1,
            warmupSteps: 0,
            occupancyThreshold: 0.05,
            massChannel: 0,
            scoreWeights: [:],
            filters: [:],
            complexity: nil,
            activity: nil,
            stability: nil,
            kSurvival: nil,
            moments: nil
        )
        let seeds = [17, 19]

        func runtimeConfig(backend: FlowLeniaComputeBackend) -> LeniaRuntimeConfig {
            makeRuntimeConfigForSearchEngine(
                sx: 64,
                sy: 64,
                channels: 1,
                backend: backend,
                parameterEmbedding: ParameterEmbeddingConfig(enabled: true, mix: "avg", mix_seed: nil),
                pUniform: UniformRange(low: 0.0, high: 1.0),
                chemotaxis: nil
            )
        }

        func assertMetricsClose(_ expected: SimulationMetrics, _ actual: SimulationMetrics, file: StaticString = #filePath, line: UInt = #line) {
            XCTAssertEqual(actual.sampleCount, expected.sampleCount, file: file, line: line)
            XCTAssertEqual(actual.speedCount, expected.speedCount, file: file, line: line)
            XCTAssertEqual(actual.isStable, expected.isStable, file: file, line: line)
            XCTAssertEqual(actual.massMean, expected.massMean, accuracy: 1e-3, file: file, line: line)
            XCTAssertEqual(actual.massStd, expected.massStd, accuracy: 1e-3, file: file, line: line)
            XCTAssertEqual(actual.occupancyMean, expected.occupancyMean, accuracy: 1e-3, file: file, line: line)
            XCTAssertEqual(actual.energyMean, expected.energyMean, accuracy: 1e-3, file: file, line: line)
            XCTAssertEqual(actual.speedMean, expected.speedMean, accuracy: 1e-3, file: file, line: line)
            XCTAssertEqual(actual.pathLength, expected.pathLength, accuracy: 1e-3, file: file, line: line)
            XCTAssertEqual(actual.displacement, expected.displacement, accuracy: 1e-3, file: file, line: line)
        }

        let expected = SearchEngine(runtimeConfig: runtimeConfig(backend: .mlx)).runBatch(
            seeds: seeds,
            initSeedOffset: 0,
            searchConfig: searchConfig
        )

        for backend in [FlowLeniaComputeBackend.metalFull] {
            let actual = SearchEngine(runtimeConfig: runtimeConfig(backend: backend)).runBatch(
                seeds: seeds,
                initSeedOffset: 0,
                searchConfig: searchConfig
            )
            XCTAssertEqual(actual.count, expected.count)
            for (lhs, rhs) in zip(actual, expected) {
                XCTAssertEqual(lhs.seed, rhs.seed)
                XCTAssertEqual(lhs.initSeed, rhs.initSeed)
                assertMetricsClose(rhs.metrics, lhs.metrics)
            }
        }
    }

    func testEvolutionEngineMetalMatchesMLXWithOverlappingMeasurements() {
        let ranges: [String: (Float, Float)] = [
            "r": (0.3, 0.8),
            "b": (0.0, 1.0),
            "w": (0.05, 0.4),
            "a": (0.0, 1.0),
            "m": (0.05, 0.3),
            "s": (0.02, 0.12),
            "h": (0.1, 0.9),
            "R": (4.0, 8.0),
        ]
        let esConfig = ESConfig(
            outputDir: "",
            generations: 1,
            population: 4,
            sigma: 0.03,
            learningRate: 0.02,
            seed: 23,
            steps: 6,
            fitness: FitnessConfig(
                objective: "directed_motion",
                targetStep: 6,
                angleThreshold: 0.01,
                gyrationPenalty: 0.0001,
                componentCountPenalty: 0.0001,
                templateSequenceSteps: [0, 3],
                trajectoryDisplacementReward: 0.01,
                morphologyThreshold: 0.03
            ),
            fitnessShaping: "centered_rank",
            initPatch: nil,
            initialInitPatchValues: nil,
            paramRanges: nil,
            obstacleField: nil
        )

        func runtimeConfig(backend: FlowLeniaComputeBackend) -> LeniaRuntimeConfig {
            makeRuntimeConfigForSearchEngine(
                sx: 48,
                sy: 48,
                channels: 1,
                backend: backend,
                parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
                pUniform: nil,
                chemotaxis: nil
            )
        }

        let expectedEngine = EvolutionEngine(
            runtimeConfig: runtimeConfig(backend: .mlx),
            esConfig: esConfig,
            ranges: ranges
        )
        let expectedResult = expectedEngine.runGeneration(gen: 0)
        let expectedTheta = expectedEngine.theta

        for backend in [FlowLeniaComputeBackend.metalFull] {
            let actualEngine = EvolutionEngine(
                runtimeConfig: runtimeConfig(backend: backend),
                esConfig: esConfig,
                ranges: ranges
            )
            let actualResult = actualEngine.runGeneration(gen: 0)

            XCTAssertEqual(actualResult.bestFitness, expectedResult.bestFitness, accuracy: 2e-3)
            XCTAssertEqual(actualResult.meanFitness, expectedResult.meanFitness, accuracy: 2e-3)
            XCTAssertEqual(actualResult.fitnessStd, expectedResult.fitnessStd, accuracy: 2e-3)
            XCTAssertEqual(actualEngine.theta.count, expectedTheta.count)
            let maxThetaDiff = zip(actualEngine.theta, expectedTheta).map { abs($0 - $1) }.max() ?? 0.0
            XCTAssertLessThan(maxThetaDiff, 5e-2)
        }
    }

    func testEvolutionEngineMetalFullSupportsObstacleNavigation() {
        let ranges: [String: (Float, Float)] = [
            "r": (0.3, 0.8),
            "b": (0.0, 1.0),
            "w": (0.05, 0.4),
            "a": (0.0, 1.0),
            "m": (0.05, 0.3),
            "s": (0.02, 0.12),
            "h": (0.1, 0.9),
            "R": (4.0, 8.0),
        ]
        let esConfig = ESConfig(
            outputDir: "",
            generations: 1,
            population: 4,
            sigma: 0.03,
            learningRate: 0.02,
            seed: 31,
            steps: 6,
            fitness: FitnessConfig(
                objective: "obstacle_navigation",
                targetStep: 6,
                angleThreshold: 0.01
            ),
            fitnessShaping: "centered_rank",
            initPatch: nil,
            initialInitPatchValues: nil,
            paramRanges: nil,
            obstacleField: ESObstacleFieldConfig(
                enabled: true,
                channelIndex: 1,
                mode: "random_on_circle",
                count: 6,
                circleRadius: 12.0,
                sigma: 2.5,
                amplitude: 1.0,
                center: [24.0, 24.0],
                seed: 5
            )
        )

        func runtimeConfig(backend: FlowLeniaComputeBackend) -> LeniaRuntimeConfig {
            makeRuntimeConfigForSearchEngine(
                sx: 48,
                sy: 48,
                channels: 2,
                backend: backend,
                parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
                pUniform: nil,
                chemotaxis: nil
            )
        }

        let expectedEngine = EvolutionEngine(
            runtimeConfig: runtimeConfig(backend: .mlx),
            esConfig: esConfig,
            ranges: ranges
        )
        let expectedResult = expectedEngine.runGeneration(gen: 0)
        let expectedTheta = expectedEngine.theta

        let actualEngine = EvolutionEngine(
            runtimeConfig: runtimeConfig(backend: .metalFull),
            esConfig: esConfig,
            ranges: ranges
        )
        let actualResult = actualEngine.runGeneration(gen: 0)

        XCTAssertEqual(actualResult.bestFitness, expectedResult.bestFitness, accuracy: 2e-3)
        XCTAssertEqual(actualResult.meanFitness, expectedResult.meanFitness, accuracy: 2e-3)
        XCTAssertEqual(actualResult.fitnessStd, expectedResult.fitnessStd, accuracy: 2e-3)
        XCTAssertEqual(actualEngine.theta.count, expectedTheta.count)
        let maxThetaDiff = zip(actualEngine.theta, expectedTheta).map { abs($0 - $1) }.max() ?? 0.0
        XCTAssertLessThan(maxThetaDiff, 5e-2)
    }

    func testEvolutionEngineMetalFullSupportsChemotaxisObjective() {
        let ranges: [String: (Float, Float)] = [
            "r": (0.3, 0.8),
            "b": (0.0, 1.0),
            "w": (0.05, 0.4),
            "a": (0.0, 1.0),
            "m": (0.05, 0.3),
            "s": (0.02, 0.12),
            "h": (0.1, 0.9),
            "R": (4.0, 8.0),
        ]
        let chemotaxis = ChemotaxisConfig(
            enabled: true,
            channel_index: 1,
            mode: "random_on_circle",
            sigma: 8.0,
            amplitude: 1.0,
            include_in_mass: false,
            center: [24.0, 24.0],
            circle_radius: 10.0,
            seed: 11
        )
        let esConfig = ESConfig(
            outputDir: "",
            generations: 1,
            population: 4,
            sigma: 0.03,
            learningRate: 0.02,
            seed: 37,
            steps: 6,
            fitness: FitnessConfig(
                objective: "chemotaxis",
                targetStep: 6,
                angleThreshold: 0.01
            ),
            fitnessShaping: "centered_rank",
            initPatch: nil,
            initialInitPatchValues: nil,
            paramRanges: nil,
            obstacleField: nil
        )

        func runtimeConfig(backend: FlowLeniaComputeBackend) -> LeniaRuntimeConfig {
            makeRuntimeConfigForSearchEngine(
                sx: 48,
                sy: 48,
                channels: 2,
                backend: backend,
                parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
                pUniform: nil,
                chemotaxis: chemotaxis
            )
        }

        let expectedEngine = EvolutionEngine(
            runtimeConfig: runtimeConfig(backend: .mlx),
            esConfig: esConfig,
            ranges: ranges
        )
        let expectedResult = expectedEngine.runGeneration(gen: 0)
        let expectedTheta = expectedEngine.theta

        let actualEngine = EvolutionEngine(
            runtimeConfig: runtimeConfig(backend: .metalFull),
            esConfig: esConfig,
            ranges: ranges
        )
        let actualResult = actualEngine.runGeneration(gen: 0)

        XCTAssertEqual(actualResult.bestFitness, expectedResult.bestFitness, accuracy: 2e-3)
        XCTAssertEqual(actualResult.meanFitness, expectedResult.meanFitness, accuracy: 2e-3)
        XCTAssertEqual(actualResult.fitnessStd, expectedResult.fitnessStd, accuracy: 2e-3)
        XCTAssertEqual(actualEngine.theta.count, expectedTheta.count)
        let maxThetaDiff = zip(actualEngine.theta, expectedTheta).map { abs($0 - $1) }.max() ?? 0.0
        XCTAssertLessThan(maxThetaDiff, 5e-2)
    }

    func testSearchBenchmarkReportsPositiveThroughput() {
        let result = benchmarkSearchEngineBackend(
            gridSize: 64,
            batchSize: 2,
            steps: 6,
            params: makeSandboxMetalParityParams(),
            backend: .metalFull,
            warmupRuns: 1,
            observationStride: 1
        )
        XCTAssertGreaterThan(result.duration, 0.0)
        XCTAssertGreaterThan(result.seedsPerSecond, 0.0)
        XCTAssertGreaterThan(result.simStepsPerSecond, 0.0)
        XCTAssertGreaterThan(result.profile.totalMs, 0.0)
        XCTAssertGreaterThanOrEqual(result.profile.rolloutMs, 0.0)
        XCTAssertGreaterThan(result.profile.combinedObservationMs, 0.0)
        XCTAssertEqual(result.profile.massObservationSynchronizations, 5)
        XCTAssertGreaterThan(result.stageTimings?.totalMs ?? 0.0, 0.0)
    }

    func testSearchFinalObservedMassMapMatchesFreshTerminalMaterialization() throws {
        let runtimeConfig = makeRuntimeConfigForSearchEngine(
            sx: 48,
            sy: 48,
            channels: 1,
            backend: .metalFull,
            parameterEmbedding: ParameterEmbeddingConfig(enabled: true, mix: "avg", mix_seed: nil),
            pUniform: UniformRange(low: 0.0, high: 1.0),
            chemotaxis: nil
        )
        let searchConfig = SearchConfig(
            steps: 4,
            recordInterval: 1,
            warmupSteps: 0,
            occupancyThreshold: 0.05,
            massChannel: 0,
            scoreWeights: [:],
            filters: [:],
            complexity: nil,
            activity: nil,
            stability: nil,
            kSurvival: nil,
            moments: nil
        )
        let engine = SearchEngine(runtimeConfig: runtimeConfig)
        let seeds = [17, 19]

        let freshResults = engine.runBatch(
            seeds: seeds,
            initSeedOffset: 23,
            searchConfig: searchConfig
        )
        let freshProfile = try XCTUnwrap(engine.lastBatchProfile)
        let observedResults = engine.runBatch(
            seeds: seeds,
            initSeedOffset: 23,
            searchConfig: searchConfig,
            frameCapture: FrameCapture(stride: 1) { _, _, _, _ in }
        )
        let observedProfile = try XCTUnwrap(engine.lastBatchProfile)

        XCTAssertEqual(observedProfile.massObservationSynchronizations + 1, freshProfile.massObservationSynchronizations)
        XCTAssertEqual(observedResults.count, freshResults.count)
        for (observed, fresh) in zip(observedResults, freshResults) {
            let observedTerminal = observed.descriptorBundle.terminal
            let freshTerminal = fresh.descriptorBundle.terminal

            XCTAssertEqual(observed.seed, fresh.seed)
            XCTAssertEqual(observed.initSeed, fresh.initSeed)
            XCTAssertEqual(observedTerminal.fingerprintU8, freshTerminal.fingerprintU8)
            XCTAssertEqual(observedTerminal.fingerprintHash12, freshTerminal.fingerprintHash12)
            XCTAssertEqual(observedTerminal.finalMass, freshTerminal.finalMass, accuracy: 1e-6)
            XCTAssertEqual(observedTerminal.finalOccupancy, freshTerminal.finalOccupancy, accuracy: 1e-6)
            XCTAssertEqual(observedTerminal.finalGyration, freshTerminal.finalGyration, accuracy: 1e-6)
            XCTAssertEqual(
                try XCTUnwrap(observed.metrics.momentMass),
                try XCTUnwrap(fresh.metrics.momentMass),
                accuracy: 1e-6
            )
            XCTAssertEqual(
                try XCTUnwrap(observed.metrics.componentCount),
                try XCTUnwrap(fresh.metrics.componentCount),
                accuracy: 1e-6
            )
            XCTAssertEqual(
                try XCTUnwrap(observed.metrics.largestComponentFraction),
                try XCTUnwrap(fresh.metrics.largestComponentFraction),
                accuracy: 1e-6
            )
        }
    }

    func testEvolutionBenchmarkReportsPositiveThroughput() {
        let result = benchmarkEvolutionEngineBackend(
            gridSize: 64,
            population: 4,
            steps: 6,
            params: makeSandboxMetalParityParams(),
            backend: .metalFull,
            warmupRuns: 1
        )
        XCTAssertGreaterThan(result.duration, 0.0)
        XCTAssertGreaterThan(result.candidatesPerSecond, 0.0)
        XCTAssertGreaterThan(result.simStepsPerSecond, 0.0)
        XCTAssertGreaterThan(result.profile.totalMs, 0.0)
        XCTAssertGreaterThan(result.stageTimings?.totalMs ?? 0.0, 0.0)
    }

    func testFlowSandboxStrokeEditsStayLocal() async {
        let (_, _, _, params) = makeTestSetup()
        let runtime = FlowSandboxRuntime(params: params, gridPreset: .compact128)

        await runtime.applyStroke(
            SandboxStroke(
                tool: .food,
                points: [SIMD2<Int>(10, 10)],
                radius: 2,
                strength: 0.5
            )
        )
        var snapshot = await runtime.materializeStateSnapshot()
        XCTAssertGreaterThan(snapshot.food[sandboxIndex(x: 10, y: 10, height: snapshot.height)], 0.0)
        XCTAssertEqual(snapshot.food[sandboxIndex(x: 40, y: 40, height: snapshot.height)], 0.0, accuracy: 1e-6)

        await runtime.applyStroke(
            SandboxStroke(
                tool: .wall,
                points: [SIMD2<Int>(0, 0)],
                radius: 1,
                strength: 1.0
            )
        )
        snapshot = await runtime.materializeStateSnapshot()
        XCTAssertEqual(snapshot.walls[sandboxIndex(x: 0, y: 0, height: snapshot.height)], 0.0, accuracy: 1e-6)
        XCTAssertEqual(snapshot.mass[sandboxIndex(x: 0, y: 0, height: snapshot.height)], 0.0, accuracy: 1e-6)

        await runtime.applyStroke(
            SandboxStroke(
                tool: .erase,
                points: [SIMD2<Int>(0, 0)],
                radius: 1,
                strength: 1.0
            )
        )
        snapshot = await runtime.materializeStateSnapshot()
        XCTAssertEqual(snapshot.walls[sandboxIndex(x: 0, y: 0, height: snapshot.height)], 1.0, accuracy: 1e-6)

        await runtime.applyStroke(
            SandboxStroke(
                tool: .mutation,
                points: [SIMD2<Int>(12, 12)],
                radius: 1,
                strength: 1.0
            )
        )
        snapshot = await runtime.materializeStateSnapshot()
        XCTAssertNotEqual(
            snapshot.params[sandboxParamIndex(x: 12, y: 12, param: 0, height: snapshot.height, parameterCount: 1)],
            0.0
        )
        XCTAssertEqual(
            snapshot.params[sandboxParamIndex(x: 48, y: 48, param: 0, height: snapshot.height, parameterCount: 1)],
            0.0,
            accuracy: 1e-6
        )
    }

    func testFlowSandboxCreatureStampWritesOnlyStampedRegion() async {
        let (_, _, _, params) = makeTestSetup()
        let runtime = FlowSandboxRuntime(params: params, gridPreset: .compact128)
        let stampA = CreatureStamp(
            id: UUID(uuidString: "11111111-1111-1111-1111-111111111111")!,
            name: "A",
            width: 3,
            height: 3,
            mass: [
                0.0, 0.2, 0.0,
                0.4, 0.9, 0.4,
                0.0, 0.2, 0.0
            ],
            params: Array(repeating: 0.25, count: 9),
            parameterCount: 1
        )
        let stampB = CreatureStamp(
            id: UUID(uuidString: "22222222-2222-2222-2222-222222222222")!,
            name: "B",
            width: 3,
            height: 3,
            mass: [
                0.0, 0.1, 0.0,
                0.3, 0.8, 0.3,
                0.0, 0.1, 0.0
            ],
            params: Array(repeating: 0.75, count: 9),
            parameterCount: 1
        )

        await runtime.applyCreatureStamp(stampA, center: SIMD2<Int>(20, 20))
        await runtime.applyCreatureStamp(stampB, center: SIMD2<Int>(60, 60))

        let snapshot = await runtime.materializeStateSnapshot()
        XCTAssertEqual(snapshot.mass[sandboxIndex(x: 20, y: 20, height: snapshot.height)], 0.9, accuracy: 1e-6)
        XCTAssertEqual(
            snapshot.params[sandboxParamIndex(x: 20, y: 20, param: 0, height: snapshot.height, parameterCount: 1)],
            0.25,
            accuracy: 1e-6
        )
        XCTAssertEqual(snapshot.mass[sandboxIndex(x: 60, y: 60, height: snapshot.height)], 0.8, accuracy: 1e-6)
        XCTAssertEqual(
            snapshot.params[sandboxParamIndex(x: 60, y: 60, param: 0, height: snapshot.height, parameterCount: 1)],
            0.75,
            accuracy: 1e-6
        )
        XCTAssertEqual(snapshot.mass[sandboxIndex(x: 100, y: 100, height: snapshot.height)], 0.0, accuracy: 1e-6)
        XCTAssertEqual(
            snapshot.params[sandboxParamIndex(x: 100, y: 100, param: 0, height: snapshot.height, parameterCount: 1)],
            0.0,
            accuracy: 1e-6
        )
    }

    func testFlowSandboxSnapshotDefaultsToSharedMetalField() async {
        let (_, _, _, params) = makeTestSetup()
        let runtime = FlowSandboxRuntime(params: params, gridPreset: .compact128)

        let liveSnapshot = await runtime.snapshot()
        XCTAssertNil(liveSnapshot.bytes)
        XCTAssertNotNil(liveSnapshot.sharedField)

        let exportSnapshot = await runtime.snapshot(includeBytes: true, refreshMetrics: true)
        XCTAssertNotNil(exportSnapshot.bytes)
        XCTAssertNotNil(exportSnapshot.sharedField)
        XCTAssertEqual(exportSnapshot.width, 128)
        XCTAssertEqual(exportSnapshot.height, 128)
    }

    func testFlowSandboxSnapshotRefreshMetricsIsExplicit() async {
        let (_, _, _, params) = makeTestSetup()
        let runtime = FlowSandboxRuntime(
            params: params,
            gridPreset: .compact128,
            backend: .metalFull
        )

        let initial = await runtime.snapshot(refreshMetrics: true)
        await runtime.applyStroke(
            SandboxStroke(
                tool: .food,
                points: [SIMD2<Int>(12, 12)],
                radius: 3,
                strength: 0.75
            )
        )

        let stale = await runtime.snapshot(refreshMetrics: false)
        XCTAssertEqual(stale.metrics.foodMean, initial.metrics.foodMean, accuracy: 1e-6)

        let refreshed = await runtime.snapshot(refreshMetrics: true)
        XCTAssertGreaterThan(refreshed.metrics.foodMean, stale.metrics.foodMean)
    }

    func testFlowSandboxMetricsReduceFieldsInOneCanonicalPass() {
        let metrics = FlowSandboxMetrics(
            mass: [0.1, .nan, .infinity, -0.25],
            food: [.nan, 0.5, .infinity, -0.1],
            walls: [1, 0, .nan, 0.4]
        )

        XCTAssertEqual(metrics.massMean, -0.0375, accuracy: 1e-6)
        XCTAssertEqual(metrics.occupancy, 0.25, accuracy: 1e-6)
        XCTAssertEqual(metrics.foodMean, 0.1, accuracy: 1e-6)
        XCTAssertEqual(metrics.wallFraction, 0.5, accuracy: 1e-6)
        XCTAssertEqual(metrics.massPeak, 0.1, accuracy: 1e-6)
        XCTAssertEqual(metrics.foodPeak, 0.5, accuracy: 1e-6)
        XCTAssertEqual(metrics.nonFiniteFraction, 0.5, accuracy: 1e-6)
    }

    func testFlowSandboxMetalFullRuntimeEditsStayLocal() async {
        let (_, _, _, params) = makeTestSetup()
        let runtime = FlowSandboxRuntime(
            params: params,
            gridPreset: .compact128,
            backend: .metalFull
        )

        await runtime.applyStroke(
            SandboxStroke(
                tool: .food,
                points: [SIMD2<Int>(10, 10)],
                radius: 2,
                strength: 0.5
            )
        )

        let stamp = CreatureStamp(
            id: UUID(uuidString: "33333333-3333-3333-3333-333333333333")!,
            name: "Metal",
            width: 3,
            height: 3,
            mass: [
                0.0, 0.2, 0.0,
                0.4, 0.9, 0.4,
                0.0, 0.2, 0.0
            ],
            params: Array(repeating: 0.45, count: 9),
            parameterCount: 1
        )
        await runtime.applyCreatureStamp(stamp, center: SIMD2<Int>(20, 20))

        let snapshot = await runtime.materializeStateSnapshot()
        XCTAssertGreaterThan(snapshot.food[sandboxIndex(x: 10, y: 10, height: snapshot.height)], 0.0)
        XCTAssertEqual(snapshot.food[sandboxIndex(x: 48, y: 48, height: snapshot.height)], 0.0, accuracy: 1e-6)
        XCTAssertEqual(snapshot.mass[sandboxIndex(x: 20, y: 20, height: snapshot.height)], 0.9, accuracy: 1e-6)
        XCTAssertEqual(
            snapshot.params[sandboxParamIndex(x: 20, y: 20, param: 0, height: snapshot.height, parameterCount: 1)],
            0.45,
            accuracy: 1e-6
        )
        XCTAssertEqual(snapshot.mass[sandboxIndex(x: 96, y: 96, height: snapshot.height)], 0.0, accuracy: 1e-6)
    }

    func testFlowSandboxMetalFullRuntimeSnapshotAndStep() async {
        let (_, _, _, params) = makeTestSetup()
        let stamp = buildWarmCreatureStamp(
            name: "Metal Runtime",
            params: params,
            seed: 17,
            warmupSteps: 8,
            warmupGridSize: 64,
            cropThreshold: 0.01,
            padding: 2
        )
        let runtime = FlowSandboxRuntime(
            params: params,
            gridPreset: .compact128,
            initialStamp: stamp,
            backend: .metalFull
        )

        await runtime.step()
        let snapshot = await runtime.snapshot(refreshMetrics: true)
        XCTAssertNotNil(snapshot.sharedField)
        XCTAssertEqual(snapshot.width, 128)
        XCTAssertEqual(snapshot.height, 128)
        XCTAssertGreaterThanOrEqual(snapshot.metrics.occupancy, 0.0)

        let materialized = await runtime.materializeStateSnapshot()
        XCTAssertEqual(materialized.width, 128)
        XCTAssertEqual(materialized.height, 128)
        XCTAssertEqual(materialized.mass.count, 128 * 128)
        XCTAssertFalse(materialized.mass.contains(where: { $0.isNaN }))
    }

    func testLeniaInteractiveEngineBuildsFromSupportedRuntimeConfig() async throws {
        let packageRoot = packageRootURL()
        let baseURL = packageRoot.appendingPathComponent("configs/base/paper_base_1c_128.json")
        let runtimeConfig = try loadRuntimeConfig(
            from: Data(contentsOf: baseURL),
            overrides: ["backend": FlowSandboxBackend.metalFull.rawValue]
        )

        let engine = try XCTUnwrap(
            makeLeniaInteractiveEngine(from: runtimeConfig, backend: .metalFull)
        )
        XCTAssertEqual(engine.descriptor.backend, .metalFull)
        XCTAssertEqual(engine.descriptor.gridPreset, .compact128)
        XCTAssertEqual(engine.descriptor.executionLabel, "Metal engine")

        let contract = await engine.worldContract()
        XCTAssertEqual(contract.backend, .metalFull)
        XCTAssertEqual(contract.gridSize, 128)
        XCTAssertEqual(contract.channels, 1)

        await engine.step()
        let snapshot = await engine.displaySnapshot(refreshMetrics: true)
        XCTAssertNotNil(snapshot.sharedField)
        XCTAssertNil(snapshot.bytes)
        XCTAssertEqual(snapshot.width, 128)
        XCTAssertEqual(snapshot.height, 128)
        XCTAssertGreaterThanOrEqual(snapshot.metrics.occupancy, 0.0)
    }

    func testFlowLeniaComputeBackendParsesConfigAliases() throws {
        XCTAssertEqual(try FlowLeniaComputeBackend(configValue: "mlx"), .mlx)
        XCTAssertEqual(try FlowLeniaComputeBackend(configValue: "mlx-swift"), .mlx)
        XCTAssertEqual(try FlowLeniaComputeBackend(configValue: "metal-full"), .metalFull)
        XCTAssertThrowsError(try FlowLeniaComputeBackend(configValue: "cuda"))
    }

    func testFlowLeniaSimulatorMetalBackendsTrackMLXOverShortRollout() {
        let params = makeSandboxMetalParityParams()
        let c0 = Array(repeating: 0, count: params.r.count)
        let c1 = [Array(0..<params.r.count)]
        let observedRolloutConfig = FlowLeniaRolloutConfig(
            steps: 8,
            recordEverySteps: 1,
            captureEverySteps: 1,
            activityConfig: nil,
            foodSpawn: nil,
            dissipation: nil
        )
        let batchedRolloutConfig = FlowLeniaRolloutConfig(
            steps: 8,
            recordEverySteps: 8,
            captureEverySteps: nil,
            activityConfig: nil,
            foodSpawn: nil,
            dissipation: nil
        )
        let initialBatch = flowSandboxSeedState(seed: 37, gridSize: 32)
        let initialState = initialBatch[0, 0..., 0..., 0].expandedDimensions(axis: -1)
        let initialParams = flowSandboxParameterField(
            mass: initialBatch,
            parameterValues: params.h,
            threshold: 0.05
        )[0, 0..., 0..., 0...]

        func runtimeConfig(backend: FlowLeniaComputeBackend) -> LeniaRuntimeConfig {
            LeniaRuntimeConfig(
                backend: backend,
                sx: 32,
                sy: 32,
                channels: 1,
                nbK: params.r.count,
                profile: .paper,
                c0: c0,
                c1: c1,
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
                params: params,
                initSeed: 0,
                patches: [PatchConfig(center: [16, 16], size: 8)],
                aUniform: UniformRange(low: 0.0, high: 1.0),
                pUniform: UniformRange(low: 0.0, high: 1.0),
                steps: 8,
                parameterEmbedding: ParameterEmbeddingConfig(enabled: true, mix: "avg", mix_seed: nil),
                chemotaxis: nil,
                food: nil,
                walls: nil,
                environment: nil,
                beamMutation: nil,
                interventions: []
            )
        }

        let expected = FlowLeniaSimulator(runtimeConfig: runtimeConfig(backend: .mlx)).rollout(
            initialState: initialState,
            initialParams: initialParams,
            initialFood: nil,
            config: observedRolloutConfig
        )

        for backend in [FlowLeniaComputeBackend.metalFull] {
            let actual = FlowLeniaSimulator(runtimeConfig: runtimeConfig(backend: backend)).rollout(
                initialState: initialState,
                initialParams: initialParams,
                initialFood: nil,
                config: observedRolloutConfig
            )
            XCTAssertLessThan(maxAbsDiff(expected.finalMassMap, actual.finalMassMap), 1e-3, "backend=\(backend.rawValue)")
            XCTAssertEqual(actual.width, expected.width)
            XCTAssertEqual(actual.height, expected.height)
            XCTAssertEqual(actual.finalMass, expected.finalMass, accuracy: 1e-3)

            let batchedResult = FlowLeniaSimulator(runtimeConfig: runtimeConfig(backend: backend)).rollout(
                initialState: initialState,
                initialParams: initialParams,
                initialFood: nil,
                config: batchedRolloutConfig
            )
            XCTAssertLessThan(maxAbsDiff(actual.finalMassMap, batchedResult.finalMassMap), 1e-6)
        }
    }

    func testFlowLeniaSimulatorMetalFullSupportsBeamMutation() {
        let params = makeSandboxMetalParityParams()
        let c0 = Array(repeating: 0, count: params.r.count)
        let c1 = [Array(0..<params.r.count)]
        func rolloutConfig(captureEverySteps: Int?) -> FlowLeniaRolloutConfig {
            FlowLeniaRolloutConfig(
                steps: 8,
                recordEverySteps: 8,
                captureEverySteps: captureEverySteps,
                activityConfig: nil,
                foodSpawn: nil,
                dissipation: nil
            )
        }
        let initialBatch = flowSandboxSeedState(seed: 43, gridSize: 32)
        let initialState = initialBatch[0, 0..., 0..., 0].expandedDimensions(axis: -1)
        let initialParams = flowSandboxParameterField(
            mass: initialBatch,
            parameterValues: params.h,
            threshold: 0.05
        )[0, 0..., 0..., 0...]
        let beamMutation = BeamMutationConfig(
            enabled: true,
            probability: 1.0,
            patchSize: 5,
            std: 0.04,
            seed: 23
        )

        func runtimeConfig(backend: FlowLeniaComputeBackend) -> LeniaRuntimeConfig {
            LeniaRuntimeConfig(
                backend: backend,
                sx: 32,
                sy: 32,
                channels: 1,
                nbK: params.r.count,
                profile: .paper,
                c0: c0,
                c1: c1,
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
                params: params,
                initSeed: 0,
                patches: [PatchConfig(center: [16, 16], size: 8)],
                aUniform: UniformRange(low: 0.0, high: 1.0),
                pUniform: UniformRange(low: 0.0, high: 1.0),
                steps: 8,
                parameterEmbedding: ParameterEmbeddingConfig(enabled: true, mix: "avg", mix_seed: nil),
                chemotaxis: nil,
                food: nil,
                walls: nil,
                environment: nil,
                beamMutation: beamMutation,
                interventions: []
            )
        }

        let expected = FlowLeniaSimulator(runtimeConfig: runtimeConfig(backend: .mlx)).rollout(
            initialState: initialState,
            initialParams: initialParams,
            initialFood: nil,
            config: rolloutConfig(captureEverySteps: nil)
        )
        let actual = FlowLeniaSimulator(runtimeConfig: runtimeConfig(backend: .metalFull)).rollout(
            initialState: initialState,
            initialParams: initialParams,
            initialFood: nil,
            config: rolloutConfig(captureEverySteps: nil)
        )
        let observed = FlowLeniaSimulator(runtimeConfig: runtimeConfig(backend: .metalFull)).rollout(
            initialState: initialState,
            initialParams: initialParams,
            initialFood: nil,
            config: rolloutConfig(captureEverySteps: 1)
        )

        XCTAssertLessThan(maxAbsDiff(expected.finalMassMap, actual.finalMassMap), 2e-3)
        XCTAssertLessThan(maxAbsDiff(actual.finalMassMap, observed.finalMassMap), 1e-6)
        XCTAssertEqual(actual.width, expected.width)
        XCTAssertEqual(actual.height, expected.height)
        XCTAssertEqual(actual.finalMass, expected.finalMass, accuracy: 1e-3)
    }

    func testFlowLeniaSimulatorMetalFullSupportsChemotaxisField() {
        let rolloutConfig = FlowLeniaRolloutConfig(
            steps: 8,
            recordEverySteps: 8,
            captureEverySteps: nil,
            activityConfig: nil,
            foodSpawn: nil,
            dissipation: nil
        )
        let chemotaxis = ChemotaxisConfig(
            enabled: true,
            channel_index: 2,
            mode: "random_on_circle",
            sigma: 6.0,
            amplitude: 1.0,
            include_in_mass: false,
            center: [16.0, 16.0],
            circle_radius: 8.0,
            seed: 13
        )

        func runtimeConfig(backend: FlowLeniaComputeBackend) -> LeniaRuntimeConfig {
            makeRuntimeConfigForSearchEngine(
                sx: 32,
                sy: 32,
                channels: 3,
                backend: backend,
                parameterEmbedding: ParameterEmbeddingConfig(enabled: true, mix: "avg", mix_seed: nil),
                pUniform: UniformRange(low: 0.0, high: 1.0),
                chemotaxis: chemotaxis,
                profile: .paper,
                patches: [PatchConfig(center: [16, 16], size: 8)]
            )
        }

        let baseConfig = runtimeConfig(backend: .mlx)
        let initialState = makePatchState(sx: 32, sy: 32, channels: 3)
        let initialParams = flowSandboxParameterField(
            mass: initialState.expandedDimensions(axis: 0),
            parameterValues: baseConfig.params.h,
            threshold: 0.01
        )[0, 0..., 0..., 0...]

        let expected = FlowLeniaSimulator(runtimeConfig: runtimeConfig(backend: .mlx)).rollout(
            initialState: initialState,
            initialParams: initialParams,
            initialFood: nil,
            config: rolloutConfig
        )
        let actual = FlowLeniaSimulator(runtimeConfig: runtimeConfig(backend: .metalFull)).rollout(
            initialState: initialState,
            initialParams: initialParams,
            initialFood: nil,
            config: rolloutConfig
        )

        XCTAssertLessThan(maxAbsDiff(expected.finalMassMap, actual.finalMassMap), 2e-3)
        XCTAssertEqual(actual.width, expected.width)
        XCTAssertEqual(actual.height, expected.height)
        XCTAssertEqual(actual.finalMass, expected.finalMass, accuracy: 1e-3)
    }

    func testFlowLeniaSimulatorMetalFullSupportsFoodField() {
        let rolloutConfig = FlowLeniaRolloutConfig(
            steps: 8,
            recordEverySteps: 8,
            captureEverySteps: nil,
            activityConfig: nil,
            foodSpawn: nil,
            dissipation: nil
        )
        let food = FoodConfig(
            enabled: true,
            channel_index: 1,
            mode: "patches",
            uniform: UniformRange(low: 0.2, high: 0.8),
            patches: [PatchConfig(center: [16, 16], size: 10)],
            decay_rate: 0.01,
            digest_rate: 0.05,
            include_in_mass: false
        )

        func runtimeConfig(backend: FlowLeniaComputeBackend) -> LeniaRuntimeConfig {
            let config = makeRuntimeConfigForSearchEngine(
                sx: 32,
                sy: 32,
                channels: 2,
                backend: backend,
                parameterEmbedding: ParameterEmbeddingConfig(enabled: true, mix: "avg", mix_seed: nil),
                pUniform: UniformRange(low: 0.0, high: 1.0),
                chemotaxis: nil,
                profile: .experimental,
                patches: [PatchConfig(center: [16, 16], size: 8)]
            )
            return LeniaRuntimeConfig(
                backend: config.backend,
                sx: config.sx,
                sy: config.sy,
                channels: config.channels,
                nbK: config.nbK,
                profile: config.profile,
                c0: config.c0,
                c1: config.c1,
                dt: config.dt,
                dd: config.dd,
                sigma: config.sigma,
                n: config.n,
                thetaA: config.thetaA,
                border: config.border,
                implementation: config.implementation,
                params: config.params,
                initSeed: config.initSeed,
                patches: config.patches,
                aUniform: config.aUniform,
                pUniform: config.pUniform,
                steps: config.steps,
                parameterEmbedding: config.parameterEmbedding,
                chemotaxis: config.chemotaxis,
                food: food,
                walls: config.walls,
                environment: config.environment,
                beamMutation: config.beamMutation,
                interventions: config.interventions
            )
        }

        var initialFood = [Float](repeating: 0.0, count: 32 * 32)
        for x in 11..<21 {
            for y in 11..<21 {
                initialFood[x * 32 + y] = 0.6
            }
        }

        let baseConfig = runtimeConfig(backend: .mlx)
        let initialState = makePatchState(sx: 32, sy: 32, channels: 2)
        let initialParams = flowSandboxParameterField(
            mass: initialState.expandedDimensions(axis: 0),
            parameterValues: baseConfig.params.h,
            threshold: 0.01
        )[0, 0..., 0..., 0...]
        let initialFoodField = MLXArray(initialFood).reshaped([32, 32])

        let expected = FlowLeniaSimulator(runtimeConfig: runtimeConfig(backend: .mlx)).rollout(
            initialState: initialState,
            initialParams: initialParams,
            initialFood: initialFoodField,
            config: rolloutConfig
        )
        let actual = FlowLeniaSimulator(runtimeConfig: runtimeConfig(backend: .metalFull)).rollout(
            initialState: initialState,
            initialParams: initialParams,
            initialFood: initialFoodField,
            config: rolloutConfig
        )

        XCTAssertLessThan(maxAbsDiff(expected.finalMassMap, actual.finalMassMap), 0.15)
        XCTAssertEqual(actual.width, expected.width)
        XCTAssertEqual(actual.height, expected.height)
        XCTAssertEqual(actual.finalMass, expected.finalMass, accuracy: 0.1)
    }

    func testWorkerSupportsSimulationJobRespectsCanonicalMetalCapabilities() {
        let mlxOnlyStatus = WorkerStatus(
            capabilities: WorkerBackendCapabilities(
                canonicalSearchBackends: [.mlx],
                canonicalFlowLeniaBackends: [.mlx],
                canonicalSearchPreferredBackend: .mlx,
                canonicalFlowLeniaPreferredBackend: .mlx
            ),
            workerId: "mlx-only",
            hostname: "node-a",
            currentJob: nil,
            jobsCompleted: 0,
            totalSeedsProcessed: 0,
            isAvailable: true
        )
        let fullStatus = WorkerStatus(
            capabilities: WorkerBackendCapabilities(
                canonicalSearchBackends: [.mlx, .metalFull],
                canonicalFlowLeniaBackends: [.mlx, .metalFull],
                canonicalSearchPreferredBackend: .metalFull,
                canonicalFlowLeniaPreferredBackend: .metalFull
            ),
            workerId: "full",
            hostname: "node-b",
            currentJob: nil,
            jobsCompleted: 0,
            totalSeedsProcessed: 0,
            isAvailable: true
        )

        XCTAssertTrue(workerSupportsSimulationJob(mlxOnlyStatus, job: makeSimulationJob(backend: "mlx")))
        XCTAssertFalse(workerSupportsSimulationJob(mlxOnlyStatus, job: makeSimulationJob(backend: "metal-full")))
        XCTAssertTrue(workerSupportsSimulationJob(fullStatus, job: makeSimulationJob(backend: "metal-full")))
    }

    func testWorkerSupportsSimulationJobAutoBackendRequiresMetalWorker() {
        let mlxOnlyStatus = WorkerStatus(
            capabilities: WorkerBackendCapabilities(
                canonicalSearchBackends: [.mlx],
                canonicalFlowLeniaBackends: [.mlx],
                canonicalSearchPreferredBackend: .mlx,
                canonicalFlowLeniaPreferredBackend: .mlx
            ),
            workerId: "mlx-only",
            hostname: "node-a",
            currentJob: nil,
            jobsCompleted: 0,
            totalSeedsProcessed: 0,
            isAvailable: true
        )
        XCTAssertFalse(workerSupportsSimulationJob(mlxOnlyStatus, job: makeSimulationJob(backend: "auto")))
        XCTAssertNil(materializeSimulationJob(makeSimulationJob(backend: "auto"), for: mlxOnlyStatus))
    }

    func testMaterializedSimulationJobPreservesRequestedBackendIntent() throws {
        let fullStatus = WorkerStatus(
            capabilities: WorkerBackendCapabilities(
                canonicalSearchBackends: [.mlx, .metalFull],
                canonicalFlowLeniaBackends: [.mlx, .metalFull],
                canonicalSearchPreferredBackend: .metalFull,
                canonicalFlowLeniaPreferredBackend: .metalFull
            ),
            workerId: "full",
            hostname: "node-c",
            currentJob: nil,
            jobsCompleted: 0,
            totalSeedsProcessed: 0,
            isAvailable: true
        )

        let materialized = try XCTUnwrap(materializeSimulationJob(makeSimulationJob(backend: "auto"), for: fullStatus))
        XCTAssertEqual(materialized.baseConfig.backend, "metal-full")
        XCTAssertEqual(materialized.requestedBackend, "auto")

        let restored = restoreRequestedBackend(for: materialized)
        XCTAssertEqual(restored.baseConfig.backend, "auto")
        XCTAssertNil(restored.requestedBackend)
    }

    func testMaterializeAndRestoreSimulationJobPreserveObstacleField() throws {
        let fullStatus = WorkerStatus(
            capabilities: WorkerBackendCapabilities(
                canonicalSearchBackends: [.mlx, .metalFull],
                canonicalFlowLeniaBackends: [.mlx, .metalFull],
                canonicalSearchPreferredBackend: .metalFull,
                canonicalFlowLeniaPreferredBackend: .metalFull
            ),
            workerId: "full",
            hostname: "node-d",
            currentJob: nil,
            jobsCompleted: 0,
            totalSeedsProcessed: 0,
            isAvailable: true
        )
        let obstacleField = ObstacleFieldConfig(
            enabled: true,
            channel_index: 1,
            mode: "random_on_circle",
            count: 3,
            circle_radius: 6.0,
            sigma: 1.5,
            amplitude: 0.9,
            center: [16.0, 16.0],
            seed: 7
        )
        let baseJob = makeSimulationJob(backend: "auto")
        let job = SimulationJob(
            id: baseJob.id,
            seedStart: baseJob.seedStart,
            count: baseJob.count,
            baseConfig: LeniaBaseConfig(
                backend: baseJob.baseConfig.backend,
                profile: baseJob.baseConfig.profile,
                grid: baseJob.baseConfig.grid,
                channels: baseJob.baseConfig.channels,
                connectivity: baseJob.baseConfig.connectivity,
                flow: baseJob.baseConfig.flow,
                implementation: baseJob.baseConfig.implementation,
                reintegration: baseJob.baseConfig.reintegration,
                parameter_embedding: baseJob.baseConfig.parameter_embedding,
                chemotaxis: baseJob.baseConfig.chemotaxis,
                obstacle_field: obstacleField,
                food: baseJob.baseConfig.food,
                walls: baseJob.baseConfig.walls,
                environment: baseJob.baseConfig.environment,
                beam_mutation: baseJob.baseConfig.beam_mutation,
                params: baseJob.baseConfig.params,
                init: baseJob.baseConfig.`init`,
                run: baseJob.baseConfig.run,
                interventions: baseJob.baseConfig.interventions
            ),
            requestedBackend: baseJob.requestedBackend,
            searchConfig: baseJob.searchConfig,
            sweepOverrides: baseJob.sweepOverrides
        )

        let materialized = try XCTUnwrap(materializeSimulationJob(job, for: fullStatus))
        XCTAssertEqual(materialized.baseConfig.obstacle_field?.count, obstacleField.count)
        XCTAssertEqual(materialized.baseConfig.obstacle_field?.channel_index, obstacleField.channel_index)

        let restored = restoreRequestedBackend(for: materialized)
        XCTAssertEqual(restored.baseConfig.backend, "auto")
        XCTAssertEqual(restored.baseConfig.obstacle_field?.count, obstacleField.count)
        XCTAssertEqual(restored.baseConfig.obstacle_field?.channel_index, obstacleField.channel_index)
    }

    func testReserveCompatibleSimulationJobMaterializesFirstCompatibleEntry() throws {
        let mlxOnlyStatus = WorkerStatus(
            capabilities: WorkerBackendCapabilities(
                canonicalSearchBackends: [.mlx],
                canonicalFlowLeniaBackends: [.mlx],
                canonicalSearchPreferredBackend: .mlx,
                canonicalFlowLeniaPreferredBackend: .mlx
            ),
            workerId: "mlx-only",
            hostname: "node-a",
            currentJob: nil,
            jobsCompleted: 0,
            totalSeedsProcessed: 0,
            isAvailable: true
        )
        var queue = [
            makeSimulationJob(backend: "metal-full"),
            makeSimulationJob(backend: "auto"),
            makeSimulationJob(backend: "mlx")
        ]

        let reserved = try XCTUnwrap(reserveCompatibleSimulationJob(from: &queue, for: mlxOnlyStatus))

        XCTAssertEqual(reserved.baseConfig.backend, "mlx")
        XCTAssertNil(reserved.requestedBackend)
        XCTAssertEqual(queue.map(\.baseConfig.backend), ["metal-full", "auto"])
    }

    func testReserveCompatibleSimulationJobReturnsNilWithoutCompatibleWorkerBackend() {
        let mlxOnlyStatus = WorkerStatus(
            capabilities: WorkerBackendCapabilities(
                canonicalSearchBackends: [.mlx],
                canonicalFlowLeniaBackends: [.mlx],
                canonicalSearchPreferredBackend: .mlx,
                canonicalFlowLeniaPreferredBackend: .mlx
            ),
            workerId: "mlx-only",
            hostname: "node-a",
            currentJob: nil,
            jobsCompleted: 0,
            totalSeedsProcessed: 0,
            isAvailable: true
        )
        var queue = [makeSimulationJob(backend: "metal-full")]

        XCTAssertNil(reserveCompatibleSimulationJob(from: &queue, for: mlxOnlyStatus))
        XCTAssertEqual(queue.map(\.baseConfig.backend), ["metal-full"])
    }

    func testReserveCompatibleSimulationJobWithoutStatusPreservesFIFO() throws {
        var queue = [
            makeSimulationJob(backend: "auto"),
            makeSimulationJob(backend: "mlx")
        ]

        let reserved = try XCTUnwrap(reserveCompatibleSimulationJob(from: &queue, for: nil))

        XCTAssertEqual(reserved.baseConfig.backend, "auto")
        XCTAssertNil(reserved.requestedBackend)
        XCTAssertEqual(queue.map(\.baseConfig.backend), ["mlx"])
    }

    func testWorkerSupportsEcologyCampaignAutoBackendRequiresMetalWorker() {
        let mlxOnlyStatus = WorkerStatus(
            capabilities: WorkerBackendCapabilities(
                canonicalSearchBackends: [.mlx],
                canonicalFlowLeniaBackends: [.mlx],
                canonicalSearchPreferredBackend: .mlx,
                canonicalFlowLeniaPreferredBackend: .mlx
            ),
            workerId: "mlx-only",
            hostname: "node-a",
            currentJob: nil,
            jobsCompleted: 0,
            totalSeedsProcessed: 0,
            isAvailable: true
        )
        let job = makeEcologyCampaignJob(backend: "auto")

        XCTAssertFalse(workerSupportsCampaignJob(mlxOnlyStatus, job: job))
        XCTAssertNil(materializeCampaignJob(job, for: mlxOnlyStatus.capabilities))
    }

    func testMaterializedEcologyCampaignAutoBackendUsesMetalWorker() throws {
        let fullStatus = WorkerStatus(
            capabilities: WorkerBackendCapabilities(
                canonicalSearchBackends: [.mlx, .metalFull],
                canonicalFlowLeniaBackends: [.mlx, .metalFull],
                canonicalSearchPreferredBackend: .metalFull,
                canonicalFlowLeniaPreferredBackend: .metalFull
            ),
            workerId: "full",
            hostname: "node-b",
            currentJob: nil,
            jobsCompleted: 0,
            totalSeedsProcessed: 0,
            isAvailable: true
        )

        let materialized = try XCTUnwrap(materializeCampaignJob(makeEcologyCampaignJob(backend: "auto"), for: fullStatus.capabilities))
        XCTAssertEqual(materialized.ecology?.baseConfig.backend, "metal-full")
        XCTAssertEqual(materialized.backendRequest, "auto")
    }

    func testFlowLeniaSimulatorMetalFullSupportsFoodSpawnOnPersistentRunner() {
        func rolloutConfig(captureEverySteps: Int?) -> FlowLeniaRolloutConfig {
            FlowLeniaRolloutConfig(
                steps: 8,
                recordEverySteps: 8,
                captureEverySteps: captureEverySteps,
                activityConfig: nil,
                foodSpawn: FlowLeniaFoodSpawnConfig(
                    probability: 1.0,
                    patchSize: 4,
                    seed: 17,
                    value: 0.85
                ),
                dissipation: nil
            )
        }
        let food = FoodConfig(
            enabled: true,
            channel_index: 1,
            mode: "patches",
            uniform: UniformRange(low: 0.2, high: 0.8),
            patches: [PatchConfig(center: [16, 16], size: 10)],
            decay_rate: 0.01,
            digest_rate: 0.05,
            include_in_mass: false
        )

        func runtimeConfig(backend: FlowLeniaComputeBackend) -> LeniaRuntimeConfig {
            let config = makeRuntimeConfigForSearchEngine(
                sx: 32,
                sy: 32,
                channels: 2,
                backend: backend,
                parameterEmbedding: ParameterEmbeddingConfig(enabled: true, mix: "avg", mix_seed: nil),
                pUniform: UniformRange(low: 0.0, high: 1.0),
                chemotaxis: nil,
                profile: .experimental,
                patches: [PatchConfig(center: [16, 16], size: 8)]
            )
            return LeniaRuntimeConfig(
                backend: config.backend,
                sx: config.sx,
                sy: config.sy,
                channels: config.channels,
                nbK: config.nbK,
                profile: config.profile,
                c0: config.c0,
                c1: config.c1,
                dt: config.dt,
                dd: config.dd,
                sigma: config.sigma,
                n: config.n,
                thetaA: config.thetaA,
                border: config.border,
                implementation: config.implementation,
                params: config.params,
                initSeed: config.initSeed,
                patches: config.patches,
                aUniform: config.aUniform,
                pUniform: config.pUniform,
                steps: config.steps,
                parameterEmbedding: config.parameterEmbedding,
                chemotaxis: config.chemotaxis,
                food: food,
                walls: config.walls,
                environment: config.environment,
                beamMutation: config.beamMutation,
                interventions: config.interventions
            )
        }

        var initialFood = [Float](repeating: 0.0, count: 32 * 32)
        for x in 11..<21 {
            for y in 11..<21 {
                initialFood[x * 32 + y] = 0.6
            }
        }

        let baseConfig = runtimeConfig(backend: .mlx)
        let initialState = makePatchState(sx: 32, sy: 32, channels: 2)
        let initialParams = flowSandboxParameterField(
            mass: initialState.expandedDimensions(axis: 0),
            parameterValues: baseConfig.params.h,
            threshold: 0.01
        )[0, 0..., 0..., 0...]
        let initialFoodField = MLXArray(initialFood).reshaped([32, 32])

        let expected = FlowLeniaSimulator(runtimeConfig: runtimeConfig(backend: .mlx)).rollout(
            initialState: initialState,
            initialParams: initialParams,
            initialFood: initialFoodField,
            config: rolloutConfig(captureEverySteps: nil)
        )
        let actual = FlowLeniaSimulator(runtimeConfig: runtimeConfig(backend: .metalFull)).rollout(
            initialState: initialState,
            initialParams: initialParams,
            initialFood: initialFoodField,
            config: rolloutConfig(captureEverySteps: nil)
        )
        let observed = FlowLeniaSimulator(runtimeConfig: runtimeConfig(backend: .metalFull)).rollout(
            initialState: initialState,
            initialParams: initialParams,
            initialFood: initialFoodField,
            config: rolloutConfig(captureEverySteps: 1)
        )

        XCTAssertLessThan(maxAbsDiff(expected.finalMassMap, actual.finalMassMap), 0.2)
        XCTAssertLessThan(maxAbsDiff(actual.finalMassMap, observed.finalMassMap), 1e-6)
        XCTAssertEqual(actual.width, expected.width)
        XCTAssertEqual(actual.height, expected.height)
        XCTAssertEqual(actual.finalMass, expected.finalMass, accuracy: 0.15)
    }

    func testFlowLeniaSimulatorMetalFullSupportsDissipationOnPersistentRunner() {
        func rolloutConfig(captureEverySteps: Int?) -> FlowLeniaRolloutConfig {
            FlowLeniaRolloutConfig(
                steps: 8,
                recordEverySteps: 8,
                captureEverySteps: captureEverySteps,
                activityConfig: nil,
                foodSpawn: nil,
                dissipation: FlowLeniaDissipationConfig(
                    probability: 1.0,
                    patchSize: 4,
                    insertionZoneOrigin: [18, 18],
                    insertionZoneSize: 8,
                    seed: 23
                )
            )
        }

        func runtimeConfig(backend: FlowLeniaComputeBackend) -> LeniaRuntimeConfig {
            makeRuntimeConfigForSearchEngine(
                sx: 32,
                sy: 32,
                channels: 2,
                backend: backend,
                parameterEmbedding: ParameterEmbeddingConfig(enabled: true, mix: "avg", mix_seed: nil),
                pUniform: UniformRange(low: 0.0, high: 1.0),
                chemotaxis: nil,
                profile: .experimental,
                patches: [PatchConfig(center: [16, 16], size: 8)]
            )
        }

        let baseConfig = runtimeConfig(backend: .mlx)
        let initialState = makePatchState(sx: 32, sy: 32, channels: 2)
        let initialParams = flowSandboxParameterField(
            mass: initialState.expandedDimensions(axis: 0),
            parameterValues: baseConfig.params.h,
            threshold: 0.01
        )[0, 0..., 0..., 0...]

        let expected = FlowLeniaSimulator(runtimeConfig: runtimeConfig(backend: .mlx)).rollout(
            initialState: initialState,
            initialParams: initialParams,
            initialFood: nil,
            config: rolloutConfig(captureEverySteps: nil)
        )
        let actual = FlowLeniaSimulator(runtimeConfig: runtimeConfig(backend: .metalFull)).rollout(
            initialState: initialState,
            initialParams: initialParams,
            initialFood: nil,
            config: rolloutConfig(captureEverySteps: nil)
        )
        let observed = FlowLeniaSimulator(runtimeConfig: runtimeConfig(backend: .metalFull)).rollout(
            initialState: initialState,
            initialParams: initialParams,
            initialFood: nil,
            config: rolloutConfig(captureEverySteps: 1)
        )

        XCTAssertLessThan(maxAbsDiff(expected.finalMassMap, actual.finalMassMap), 0.2)
        XCTAssertLessThan(maxAbsDiff(actual.finalMassMap, observed.finalMassMap), 1e-6)
        XCTAssertEqual(actual.width, expected.width)
        XCTAssertEqual(actual.height, expected.height)
        XCTAssertEqual(actual.finalMass, expected.finalMass, accuracy: 0.15)
    }

    func testSearchExplicitParamsAreCallScopedAcrossKernelBatchShapes() {
        let runtimeConfig = makeRuntimeConfigForSearchEngine(
            sx: 32,
            sy: 32,
            channels: 1,
            backend: .metalFull,
            parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
            pUniform: nil,
            chemotaxis: nil,
            profile: .experimental,
            patches: [PatchConfig(center: [16, 16], size: 8)]
        )
        let searchConfig = SearchConfig(
            steps: 2,
            recordInterval: 1,
            warmupSteps: 0,
            occupancyThreshold: 0.05,
            massChannel: 0,
            scoreWeights: [:],
            filters: [:],
            complexity: nil,
            activity: nil,
            stability: nil,
            kSurvival: nil,
            moments: nil
        )
        let engine = SearchEngine(runtimeConfig: runtimeConfig)
        let seeds = [31, 37]
        let alternateParams = ResolvedParams(
            r: [0.7],
            b: [[0.9, 0.1, 0.0]],
            w: [[0.15, 0.2, 0.15]],
            a: [[0.4, 0.4, 0.4]],
            m: [0.2],
            s: [0.06],
            h: [0.3],
            R: 5.0,
            seed: 1
        )
        let explicitParams = [runtimeConfig.params, alternateParams]

        let sharedBefore = engine.runBatch(
            seeds: seeds,
            initSeedOffset: 0,
            searchConfig: searchConfig
        )
        let explicit = engine.runBatch(
            seeds: seeds,
            initSeedOffset: 0,
            searchConfig: searchConfig,
            explicitParamsBatch: explicitParams
        )
        let sharedAfter = engine.runBatch(
            seeds: seeds,
            initSeedOffset: 0,
            searchConfig: searchConfig
        )

        XCTAssertEqual(explicit.count, seeds.count)
        XCTAssertEqual(explicit.map(\.params.h), explicitParams.map(\.h))
        XCTAssertEqual(sharedAfter.count, sharedBefore.count)
        XCTAssertEqual(sharedAfter.map(\.params.h), sharedBefore.map(\.params.h))
        for (actual, expected) in zip(sharedAfter, sharedBefore) {
            XCTAssertEqual(actual.seed, expected.seed)
            XCTAssertEqual(actual.initSeed, expected.initSeed)
            XCTAssertEqual(actual.descriptorBundle.terminal.fingerprintU8, expected.descriptorBundle.terminal.fingerprintU8)
            XCTAssertEqual(actual.metrics.massMean, expected.metrics.massMean, accuracy: 1e-6)
            XCTAssertEqual(actual.metrics.energyMean, expected.metrics.energyMean, accuracy: 1e-6)
        }
    }

    func testSearchEngineMetalFullSupportsEnvironmentPotential() {
        let searchConfig = SearchConfig(
            steps: 1,
            recordInterval: 1,
            warmupSteps: 0,
            occupancyThreshold: 0.05,
            massChannel: 0,
            scoreWeights: [:],
            filters: [:],
            complexity: nil,
            activity: nil,
            stability: nil,
            kSurvival: nil,
            moments: nil
        )
        let seeds = [23, 29]

        func runtimeConfig(backend: FlowLeniaComputeBackend) -> LeniaRuntimeConfig {
            let config = makeRuntimeConfigForSearchEngine(
                sx: 32,
                sy: 32,
                channels: 1,
                backend: backend,
                parameterEmbedding: ParameterEmbeddingConfig(enabled: true, mix: "avg", mix_seed: nil),
                pUniform: UniformRange(low: 0.0, high: 1.0),
                chemotaxis: nil,
                profile: .experimental,
                patches: [PatchConfig(center: [16, 16], size: 8)]
            )
            return LeniaRuntimeConfig(
                backend: config.backend,
                sx: config.sx,
                sy: config.sy,
                channels: config.channels,
                nbK: config.nbK,
                profile: config.profile,
                c0: config.c0,
                c1: config.c1,
                dt: config.dt,
                dd: config.dd,
                sigma: config.sigma,
                n: config.n,
                thetaA: config.thetaA,
                border: config.border,
                implementation: config.implementation,
                params: config.params,
                initSeed: config.initSeed,
                patches: config.patches,
                aUniform: config.aUniform,
                pUniform: config.pUniform,
                steps: config.steps,
                parameterEmbedding: config.parameterEmbedding,
                chemotaxis: config.chemotaxis,
                food: config.food,
                walls: config.walls,
                environment: EnvironmentConfig(
                    type: "cross_map",
                    depth: 1,
                    wallThickness: 2,
                    wallValue: -1.0,
                    passageWidth: 4
                ),
                beamMutation: config.beamMutation,
                interventions: config.interventions
            )
        }

        let expected = SearchEngine(runtimeConfig: runtimeConfig(backend: .mlx)).runBatch(
            seeds: seeds,
            initSeedOffset: 0,
            searchConfig: searchConfig
        )
        let actual = SearchEngine(runtimeConfig: runtimeConfig(backend: .metalFull)).runBatch(
            seeds: seeds,
            initSeedOffset: 0,
            searchConfig: searchConfig
        )

        XCTAssertEqual(actual.count, expected.count)
        for (lhs, rhs) in zip(actual, expected) {
            XCTAssertEqual(lhs.seed, rhs.seed)
            XCTAssertEqual(lhs.initSeed, rhs.initSeed)
            XCTAssertEqual(lhs.metrics.sampleCount, rhs.metrics.sampleCount)
            XCTAssertEqual(lhs.metrics.speedCount, rhs.metrics.speedCount)
            XCTAssertEqual(lhs.metrics.massMean, rhs.metrics.massMean, accuracy: 1e-3)
            XCTAssertEqual(lhs.metrics.massStd, rhs.metrics.massStd, accuracy: 2e-2)
            XCTAssertEqual(lhs.metrics.occupancyMean, rhs.metrics.occupancyMean, accuracy: 1e-3)
            XCTAssertEqual(lhs.metrics.energyMean, rhs.metrics.energyMean, accuracy: 1e-3)
            XCTAssertEqual(lhs.metrics.speedMean, rhs.metrics.speedMean, accuracy: 1e-3)
            XCTAssertEqual(lhs.metrics.pathLength, rhs.metrics.pathLength, accuracy: 1e-3)
            XCTAssertEqual(lhs.metrics.displacement, rhs.metrics.displacement, accuracy: 1e-3)
        }
    }

    func testSearchEngineMetalFullSupportsFoodField() {
        let searchConfig = SearchConfig(
            steps: 8,
            recordInterval: 1,
            warmupSteps: 0,
            occupancyThreshold: 0.05,
            massChannel: 0,
            scoreWeights: [:],
            filters: [:],
            complexity: nil,
            activity: nil,
            stability: nil,
            kSurvival: nil,
            moments: nil
        )
        let seeds = [17, 41]
        let food = FoodConfig(
            enabled: true,
            channel_index: 1,
            mode: "patches",
            uniform: UniformRange(low: 0.2, high: 0.8),
            patches: [PatchConfig(center: [24, 24], size: 12)],
            decay_rate: 0.01,
            digest_rate: 0.05,
            include_in_mass: false
        )

        func runtimeConfig(backend: FlowLeniaComputeBackend) -> LeniaRuntimeConfig {
            let config = makeRuntimeConfigForSearchEngine(
                sx: 48,
                sy: 48,
                channels: 2,
                backend: backend,
                parameterEmbedding: ParameterEmbeddingConfig(enabled: true, mix: "avg", mix_seed: nil),
                pUniform: UniformRange(low: 0.0, high: 1.0),
                chemotaxis: nil,
                profile: .experimental,
                patches: [PatchConfig(center: [24, 24], size: 8)]
            )
            return LeniaRuntimeConfig(
                backend: config.backend,
                sx: config.sx,
                sy: config.sy,
                channels: config.channels,
                nbK: config.nbK,
                profile: config.profile,
                c0: config.c0,
                c1: config.c1,
                dt: config.dt,
                dd: config.dd,
                sigma: config.sigma,
                n: config.n,
                thetaA: config.thetaA,
                border: config.border,
                implementation: config.implementation,
                params: config.params,
                initSeed: config.initSeed,
                patches: config.patches,
                aUniform: config.aUniform,
                pUniform: config.pUniform,
                steps: config.steps,
                parameterEmbedding: config.parameterEmbedding,
                chemotaxis: config.chemotaxis,
                food: food,
                walls: config.walls,
                environment: config.environment,
                beamMutation: config.beamMutation,
                interventions: config.interventions
            )
        }

        let expected = SearchEngine(runtimeConfig: runtimeConfig(backend: .mlx)).runBatch(
            seeds: seeds,
            initSeedOffset: 0,
            searchConfig: searchConfig
        )
        let actual = SearchEngine(runtimeConfig: runtimeConfig(backend: .metalFull)).runBatch(
            seeds: seeds,
            initSeedOffset: 0,
            searchConfig: searchConfig
        )

        XCTAssertEqual(actual.count, expected.count)
        for (lhs, rhs) in zip(actual, expected) {
            XCTAssertEqual(lhs.seed, rhs.seed)
            XCTAssertEqual(lhs.initSeed, rhs.initSeed)
            XCTAssertEqual(lhs.metrics.sampleCount, rhs.metrics.sampleCount)
            XCTAssertEqual(lhs.metrics.speedCount, rhs.metrics.speedCount)
            XCTAssertEqual(lhs.metrics.massMean, rhs.metrics.massMean, accuracy: 5e-2)
            XCTAssertEqual(lhs.metrics.massStd, rhs.metrics.massStd, accuracy: 3e-2)
            XCTAssertEqual(lhs.metrics.occupancyMean, rhs.metrics.occupancyMean, accuracy: 3e-2)
            XCTAssertEqual(lhs.metrics.energyMean, rhs.metrics.energyMean, accuracy: 1.5)
            XCTAssertEqual(lhs.metrics.speedMean, rhs.metrics.speedMean, accuracy: 2e-2)
            XCTAssertEqual(lhs.metrics.pathLength, rhs.metrics.pathLength, accuracy: 8e-2)
            XCTAssertEqual(lhs.metrics.displacement, rhs.metrics.displacement, accuracy: 8e-2)
        }
    }

    func testSearchEngineMetalFullSupportsChemotaxisField() {
        let searchConfig = SearchConfig(
            steps: 8,
            recordInterval: 1,
            warmupSteps: 0,
            occupancyThreshold: 0.05,
            massChannel: 0,
            scoreWeights: [:],
            filters: [:],
            complexity: nil,
            activity: nil,
            stability: nil,
            kSurvival: nil,
            moments: nil
        )
        let seeds = [17, 41]
        let chemotaxis = ChemotaxisConfig(
            enabled: true,
            channel_index: 1,
            mode: "random_on_circle",
            sigma: 6.0,
            amplitude: 1.0,
            include_in_mass: false,
            center: [24.0, 24.0],
            circle_radius: 12.0,
            seed: 9
        )

        func runtimeConfig(backend: FlowLeniaComputeBackend) -> LeniaRuntimeConfig {
            makeRuntimeConfigForSearchEngine(
                sx: 48,
                sy: 48,
                channels: 2,
                backend: backend,
                parameterEmbedding: ParameterEmbeddingConfig(enabled: true, mix: "avg", mix_seed: nil),
                pUniform: UniformRange(low: 0.0, high: 1.0),
                chemotaxis: chemotaxis,
                profile: .experimental
            )
        }

        let expected = SearchEngine(runtimeConfig: runtimeConfig(backend: .mlx)).runBatch(
            seeds: seeds,
            initSeedOffset: 0,
            searchConfig: searchConfig
        )
        let actual = SearchEngine(runtimeConfig: runtimeConfig(backend: .metalFull)).runBatch(
            seeds: seeds,
            initSeedOffset: 0,
            searchConfig: searchConfig
        )

        XCTAssertEqual(actual.count, expected.count)
        for (lhs, rhs) in zip(actual, expected) {
            XCTAssertEqual(lhs.seed, rhs.seed)
            XCTAssertEqual(lhs.initSeed, rhs.initSeed)
            XCTAssertEqual(lhs.metrics.sampleCount, rhs.metrics.sampleCount)
            XCTAssertEqual(lhs.metrics.speedCount, rhs.metrics.speedCount)
            XCTAssertEqual(lhs.metrics.massMean, rhs.metrics.massMean, accuracy: 1e-3)
            XCTAssertEqual(lhs.metrics.massStd, rhs.metrics.massStd, accuracy: 2e-2)
            XCTAssertEqual(lhs.metrics.occupancyMean, rhs.metrics.occupancyMean, accuracy: 1e-3)
            XCTAssertEqual(lhs.metrics.energyMean, rhs.metrics.energyMean, accuracy: 6e-2)
            XCTAssertEqual(lhs.metrics.speedMean, rhs.metrics.speedMean, accuracy: 1e-3)
            XCTAssertEqual(lhs.metrics.pathLength, rhs.metrics.pathLength, accuracy: 1e-3)
            XCTAssertEqual(lhs.metrics.displacement, rhs.metrics.displacement, accuracy: 1e-3)
        }
    }

    func testSearchEngineMetalFullSupportsScheduledInterventions() {
        let searchConfig = SearchConfig(
            steps: 8,
            recordInterval: 1,
            warmupSteps: 0,
            occupancyThreshold: 0.05,
            massChannel: 0,
            scoreWeights: [:],
            filters: [:],
            complexity: nil,
            activity: nil,
            stability: nil,
            kSurvival: nil,
            moments: nil
        )
        let seeds = [11, 19]
        let interventions = [
            InterventionConfig(
                type: "jitter_params",
                step: 3,
                patch: InterventionPatch(center: [16, 16], size: 6),
                std: 0.05,
                seed: 17,
                clip: [0.0, 1.0]
            )
        ]

        func runtimeConfig(backend: FlowLeniaComputeBackend) -> LeniaRuntimeConfig {
            let config = makeRuntimeConfigForSearchEngine(
                sx: 32,
                sy: 32,
                channels: 1,
                backend: backend,
                parameterEmbedding: ParameterEmbeddingConfig(enabled: true, mix: "avg", mix_seed: nil),
                pUniform: UniformRange(low: 0.0, high: 1.0),
                chemotaxis: nil,
                profile: .experimental,
                patches: [PatchConfig(center: [16, 16], size: 8)]
            )
            return LeniaRuntimeConfig(
                backend: config.backend,
                sx: config.sx,
                sy: config.sy,
                channels: config.channels,
                nbK: config.nbK,
                profile: config.profile,
                c0: config.c0,
                c1: config.c1,
                dt: config.dt,
                dd: config.dd,
                sigma: config.sigma,
                n: config.n,
                thetaA: config.thetaA,
                border: config.border,
                implementation: config.implementation,
                params: config.params,
                initSeed: config.initSeed,
                patches: config.patches,
                aUniform: config.aUniform,
                pUniform: config.pUniform,
                steps: config.steps,
                parameterEmbedding: config.parameterEmbedding,
                chemotaxis: config.chemotaxis,
                food: config.food,
                walls: config.walls,
                environment: config.environment,
                beamMutation: config.beamMutation,
                interventions: interventions
            )
        }

        let expected = SearchEngine(runtimeConfig: runtimeConfig(backend: .mlx)).runBatch(
            seeds: seeds,
            initSeedOffset: 0,
            searchConfig: searchConfig
        )
        let actual = SearchEngine(runtimeConfig: runtimeConfig(backend: .metalFull)).runBatch(
            seeds: seeds,
            initSeedOffset: 0,
            searchConfig: searchConfig
        )

        XCTAssertEqual(actual.count, expected.count)
        for (lhs, rhs) in zip(actual, expected) {
            XCTAssertEqual(lhs.seed, rhs.seed)
            XCTAssertEqual(lhs.initSeed, rhs.initSeed)
            XCTAssertEqual(lhs.metrics.sampleCount, rhs.metrics.sampleCount)
            XCTAssertEqual(lhs.metrics.speedCount, rhs.metrics.speedCount)
            XCTAssertEqual(lhs.metrics.massMean, rhs.metrics.massMean, accuracy: 1e-3)
            XCTAssertEqual(lhs.metrics.massStd, rhs.metrics.massStd, accuracy: 2e-2)
            XCTAssertEqual(lhs.metrics.occupancyMean, rhs.metrics.occupancyMean, accuracy: 1e-3)
            XCTAssertEqual(lhs.metrics.energyMean, rhs.metrics.energyMean, accuracy: 1e-3)
            XCTAssertEqual(lhs.metrics.speedMean, rhs.metrics.speedMean, accuracy: 1e-3)
            XCTAssertEqual(lhs.metrics.pathLength, rhs.metrics.pathLength, accuracy: 1e-3)
            XCTAssertEqual(lhs.metrics.displacement, rhs.metrics.displacement, accuracy: 1e-3)
        }
    }

    func testSearchEngineMetalFullSupportsBeamMutation() {
        let searchConfig = SearchConfig(
            steps: 8,
            recordInterval: 1,
            warmupSteps: 0,
            occupancyThreshold: 0.05,
            massChannel: 0,
            scoreWeights: [:],
            filters: [:],
            complexity: nil,
            activity: nil,
            stability: nil,
            kSurvival: nil,
            moments: nil
        )
        let seeds = [13, 31]
        let beamMutation = BeamMutationConfig(
            enabled: true,
            probability: 1.0,
            patchSize: 5,
            std: 0.04,
            seed: 29
        )

        func runtimeConfig(backend: FlowLeniaComputeBackend) -> LeniaRuntimeConfig {
            let config = makeRuntimeConfigForSearchEngine(
                sx: 32,
                sy: 32,
                channels: 1,
                backend: backend,
                parameterEmbedding: ParameterEmbeddingConfig(enabled: true, mix: "avg", mix_seed: nil),
                pUniform: UniformRange(low: 0.0, high: 1.0),
                chemotaxis: nil,
                profile: .experimental,
                patches: [PatchConfig(center: [16, 16], size: 8)]
            )
            return LeniaRuntimeConfig(
                backend: config.backend,
                sx: config.sx,
                sy: config.sy,
                channels: config.channels,
                nbK: config.nbK,
                profile: config.profile,
                c0: config.c0,
                c1: config.c1,
                dt: config.dt,
                dd: config.dd,
                sigma: config.sigma,
                n: config.n,
                thetaA: config.thetaA,
                border: config.border,
                implementation: config.implementation,
                params: config.params,
                initSeed: config.initSeed,
                patches: config.patches,
                aUniform: config.aUniform,
                pUniform: config.pUniform,
                steps: config.steps,
                parameterEmbedding: config.parameterEmbedding,
                chemotaxis: config.chemotaxis,
                food: config.food,
                walls: config.walls,
                environment: config.environment,
                beamMutation: beamMutation,
                interventions: config.interventions
            )
        }

        let expected = SearchEngine(runtimeConfig: runtimeConfig(backend: .mlx)).runBatch(
            seeds: seeds,
            initSeedOffset: 0,
            searchConfig: searchConfig
        )
        let actual = SearchEngine(runtimeConfig: runtimeConfig(backend: .metalFull)).runBatch(
            seeds: seeds,
            initSeedOffset: 0,
            searchConfig: searchConfig
        )

        XCTAssertEqual(actual.count, expected.count)
        for (lhs, rhs) in zip(actual, expected) {
            XCTAssertEqual(lhs.seed, rhs.seed)
            XCTAssertEqual(lhs.initSeed, rhs.initSeed)
            XCTAssertEqual(lhs.metrics.sampleCount, rhs.metrics.sampleCount)
            XCTAssertEqual(lhs.metrics.speedCount, rhs.metrics.speedCount)
            XCTAssertEqual(lhs.metrics.massMean, rhs.metrics.massMean, accuracy: 1e-3)
            XCTAssertEqual(lhs.metrics.massStd, rhs.metrics.massStd, accuracy: 2e-2)
            XCTAssertEqual(lhs.metrics.occupancyMean, rhs.metrics.occupancyMean, accuracy: 1e-3)
            XCTAssertEqual(lhs.metrics.energyMean, rhs.metrics.energyMean, accuracy: 1e-3)
            XCTAssertEqual(lhs.metrics.speedMean, rhs.metrics.speedMean, accuracy: 1e-3)
            XCTAssertEqual(lhs.metrics.pathLength, rhs.metrics.pathLength, accuracy: 1e-3)
            XCTAssertEqual(lhs.metrics.displacement, rhs.metrics.displacement, accuracy: 1e-3)
        }
    }
}

private enum MLXTestSupport {
    static func ensureMetalLibraryAvailable(
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        do {
            try LeniaMetalLibrarySupport.ensureAvailable(
                executableURL: Bundle(for: MLXTestSupportMarker.self).executableURL
            )
        } catch {
            XCTFail("Failed to prepare MLX metallib: \(error)", file: file, line: line)
        }
    }
}

private final class MLXTestSupportMarker {}

private func rewriteJSONFile(
    at url: URL,
    mutate: (inout [String: Any]) throws -> Void
) throws {
    let data = try Data(contentsOf: url)
    var root = try XCTUnwrap(
        JSONSerialization.jsonObject(with: data) as? [String: Any],
        "Expected JSON object at \(url.path)"
    )
    try mutate(&root)
    let rewritten = try JSONSerialization.data(withJSONObject: root, options: [.prettyPrinted, .sortedKeys])
    try rewritten.write(to: url)
}

private func makeTestSetup() -> (BatchedConfig, [Int], [[Int]], ResolvedParams) {
    let connectivity = [[1]]
    let (c0, c1) = connFromMatrix(connectivity)
    let params = ResolvedParams(
        r: [0.5],
        b: [[1.0, 0.0, 0.0]],
        w: [[0.2, 0.2, 0.2]],
        a: [[0.5, 0.5, 0.5]],
        m: [0.15],
        s: [0.05],
        h: [0.5],
        R: 6.0,
        seed: 0
    )
    let config = BatchedConfig(
        sx: 16,
        sy: 16,
        channels: 1,
        nbK: c0.count,
        dt: 0.2,
        dd: 2,
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
        chemChannel: nil,
        chemIncludeInMass: true
    )
    return (config, c0, c1, params)
}

private func makeSandboxMetalParityParams() -> ResolvedParams {
    ResolvedParams(
        r: [0.45, 0.78],
        b: [
            [1.0, 0.0, 0.0],
            [0.9, 0.1, 0.0]
        ],
        w: [
            [0.16, 0.18, 0.16],
            [0.12, 0.2, 0.12]
        ],
        a: [
            [0.35, 0.35, 0.35],
            [0.62, 0.62, 0.62]
        ],
        m: [0.14, 0.24],
        s: [0.05, 0.07],
        h: [0.42, 0.83],
        R: 7.0,
        seed: 0
    )
}

private func flowMetalTestConfig(gridSize: Int, nbK: Int) -> BatchedConfig {
    BatchedConfig(
        sx: gridSize,
        sy: gridSize,
        channels: 3,
        nbK: nbK,
        dt: 0.2,
        dd: 2,
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
        chemChannel: nil,
        chemIncludeInMass: true
    )
}

func makeRuntimeConfigForSearchEngine(
    sx: Int = 64,
    sy: Int = 64,
    channels: Int,
    backend: FlowLeniaComputeBackend = .mlx,
    parameterEmbedding: ParameterEmbeddingConfig,
    pUniform: UniformRange?,
    chemotaxis: ChemotaxisConfig?,
    profile: RuntimeProfile = .paper,
    implementationMode: String = "flowlenia_2022_paper_equations",
    patches: [PatchConfig]? = nil,
    aUniform: UniformRange = UniformRange(low: 0.0, high: 1.0),
    statePatch: InitStatePatchConfig? = nil
) -> LeniaRuntimeConfig {
    var connectivity = Array(repeating: Array(repeating: 0, count: channels), count: channels)
    connectivity[0][0] = 1
    let (c0, c1) = connFromMatrix(connectivity)

    let params = ResolvedParams(
        r: [0.5],
        b: [[1.0, 0.0, 0.0]],
        w: [[0.2, 0.2, 0.2]],
        a: [[0.5, 0.5, 0.5]],
        m: [0.15],
        s: [0.05],
        h: [0.5],
        R: 6.0,
        seed: 0
    )

    let implementation: ImplementationSettings
    switch implementationMode {
    case "flowlenia_2022_colab":
        implementation = ImplementationSettings(
            mode: "flowlenia_2022_colab",
            border: "torus",
            gradientBoundary: "periodic",
            alphaMode: "per_channel",
            kernelProfile: "flowlenia_2022_colab",
            flowClip: "params_only"
        )
    case "flowlenia_2022_paper_equations":
        implementation = ImplementationSettings(
            mode: "flowlenia_2022_paper_equations",
            border: "torus",
            gradientBoundary: "periodic",
            alphaMode: "mass",
            kernelProfile: "flowlenia_2022_paper_equations",
            flowClip: "none"
        )
    default:
        fatalError("Unsupported implementationMode in test helper: \(implementationMode)")
    }

    return LeniaRuntimeConfig(
        backend: backend,
        sx: sx,
        sy: sy,
        channels: channels,
        nbK: c0.count,
        profile: profile,
        c0: c0,
        c1: c1,
        dt: 0.2,
        dd: 5,
        sigma: 0.65,
        n: 2,
        thetaA: 2.0,
        border: "torus",
        implementation: implementation,
        params: params,
        initSeed: 0,
        patches: patches ?? [PatchConfig(center: [sx / 2, sy / 2], size: 40)],
        aUniform: aUniform,
        pUniform: pUniform,
        statePatch: statePatch,
        steps: 10,
        parameterEmbedding: parameterEmbedding,
        chemotaxis: chemotaxis,
        food: nil,
        walls: nil,
        interventions: []
    )
}

private func makePatchState(sx: Int, sy: Int, channels: Int) -> MLXArray {
    var data = [Float](repeating: 0.0, count: sx * sy * channels)
    let size = 4
    let half = size / 2
    let cx = sx / 2
    let cy = sy / 2

    for x in (cx - half)..<(cx + size - half) {
        for y in (cy - half)..<(cy + size - half) {
            for c in 0..<channels {
                let idx = (x * sy + y) * channels + c
                if idx >= 0 && idx < data.count {
                    data[idx] = 1.0
                }
            }
        }
    }

    return MLXArray(data).reshaped([sx, sy, channels])
}

private func makeSimulationJob(backend: String) -> SimulationJob {
    let baseConfig = LeniaBaseConfig(
        backend: backend,
        profile: .paper,
        grid: GridConfig(sx: 32, sy: 32),
        channels: 1,
        connectivity: [[1]],
        flow: FlowConfig(dt: 0.2, n: 2, theta_A: 2.0),
        implementation: ImplementationConfig(
            mode: "flowlenia_2022_paper_equations",
            gradient_boundary: "periodic",
            alpha_mode: "mass",
            kernel_profile: "flowlenia_2022_paper_equations",
            flow_clip: "none"
        ),
        reintegration: ReintegrationConfig(dd: 5, sigma: 0.65, border: "torus"),
        parameter_embedding: ParameterEmbeddingConfig(enabled: true, mix: "avg", mix_seed: nil),
        chemotaxis: nil,
        food: nil,
        walls: nil,
        environment: nil,
        beam_mutation: nil,
        params: ParamsConfig(
            mode: "explicit",
            seed: 0,
            ranges: nil,
            r: [0.5],
            b: [[1.0, 0.0, 0.0]],
            w: [[0.2, 0.2, 0.2]],
            a: [[0.5, 0.5, 0.5]],
            m: [0.15],
            s: [0.05],
            h: [0.5],
            R: 6.0
        ),
        init: InitConfig(
            seed: 0,
            patches: [PatchConfig(center: [16, 16], size: 8)],
            a_uniform: UniformRange(low: 0.0, high: 1.0),
            p_uniform: UniformRange(low: 0.0, high: 1.0)
        ),
        run: RunConfig(steps: 8),
        interventions: []
    )
    let searchConfig = ParsedSearchConfig(
        count: 4,
        seedStart: 0,
        steps: 8,
        recordInterval: 4,
        warmupSteps: 0,
        topK: 2
    )
    return SimulationJob(
        id: "job-test",
        seedStart: 0,
        count: 4,
        baseConfig: baseConfig,
        searchConfig: searchConfig,
        sweepOverrides: nil
    )
}

private func makeEcologyCampaignJob(backend: String) -> LeniaCampaignJob {
    let baseConfig = makeSimulationJob(backend: backend).baseConfig
    let simulation = FlowLeniaEcology2025SimulationConfig(
        paper: "flow-lenia-emergent-evolutionary-dynamics-2025",
        gridSize: 32,
        totalSteps: 8,
        recordEverySteps: 4,
        channels: 1,
        kernelsPerChannelPair: 1,
        repeats: 1,
        mutationProbabilities: [0],
        variants: ["test"],
        activity: ActivityConfig(
            enabled: true,
            interval: 4,
            threshold: 0.05,
            maxComponents: 16,
            matchThreshold: 1.5,
            paramWeight: 1.0,
            positionWeight: 0.05
        )
    )
    let variant = FlowLeniaEcology2025VariantConfig(
        name: "test",
        baseConfig: "base.json",
        initPatchCount: 1,
        initPatchSize: 4,
        initParamMean: 0,
        initParamStd: 0,
        foodPatchCount: nil,
        foodPatchSize: nil,
        foodPatchValue: nil,
        foodSpawn: nil,
        dissipation: nil
    )
    let payload = LeniaCampaignEcologyJobPayload(
        simulation: simulation,
        variant: variant,
        baseConfig: baseConfig,
        mutationProbability: 0,
        curatedSeeds: [],
        configHash: "test"
    )
    return LeniaCampaignJob(
        campaignID: "campaign-test",
        runID: "ecology-test",
        preset: .seededEcology,
        executor: .ecology2025,
        backendRequest: backend,
        executionMode: .distributed,
        repeatIndex: 0,
        ecology: payload
    )
}

private func makeSearchInitializationBuilder(runtimeConfig: LeniaRuntimeConfig) -> SearchInitializationBuilder {
    SearchInitializationBuilder(
        runtimeConfig: runtimeConfig,
        useParamEmbedding: runtimeConfig.parameterEmbedding.enabled,
        constantPerPatchParameters: runtimeConfig.profile == .paper
            || runtimeConfig.implementation.mode == "flowlenia_2022_colab"
    )
}

private func makeVaryingParamBatch(batch: Int, sx: Int, sy: Int, nbK: Int) -> MLXArray {
    var data = [Float]()
    data.reserveCapacity(batch * sx * sy * nbK)
    for b in 0..<batch {
        for x in 0..<sx {
            for y in 0..<sy {
                for k in 0..<nbK {
                    let value = Float(b + x + y + k) / Float(max(sx + sy + nbK, 1))
                    data.append(value)
                }
            }
        }
    }
    return MLXArray(data).reshaped([batch, sx, sy, nbK])
}

private func makeUniformState(sx: Int, sy: Int, channels: Int, value: Float) -> MLXArray {
    let data = [Float](repeating: value, count: sx * sy * channels)
    return MLXArray(data).reshaped([sx, sy, channels])
}

private func flowSandboxReferenceStages(
    mass: MLXArray,
    params: MLXArray,
    kernels: CompiledKernels,
    config: BatchedConfig,
    wallPotential: MLXArray? = nil
) -> (preparedMass: MLXArray, uk: MLXArray, scalarField: MLXArray, flow: MLXArray) {
    let preparedMass = mass.contiguous()
    let fA = MLXFFT.fft2(preparedMass, axes: [1, 2])
    let fAK = fA.take(kernels.c0Idxs, axis: 3)
    let uk = MLXFFT.ifft2(fAK * kernels.fK, axes: [1, 2]).realPart()

    let mB = kernels.m.reshaped([1, 1, 1, -1])
    let sB = kernels.s.reshaped([1, 1, 1, -1])
    let diff = (uk - mB) / sB
    let bellShifted = MLX.exp(-(diff * diff) / MLXArray(2.0)) * MLXArray(2.0) - MLXArray(1.0)
    let outputWeights = kernels.c1Mask[0, 0...].reshaped([1, 1, 1, -1])
    var scalarField = (bellShifted * params * outputWeights).sum(axis: -1)
    if let wallPotential {
        scalarField = scalarField + wallPotential.squeezed(axis: 3)
    }

    let nablaU = flowSandboxReferenceSobel(
        scalarField.expandedDimensions(axis: 3),
        gradientBoundary: config.implementation.gradientBoundary
    )
    let nablaA = flowSandboxReferenceSobel(preparedMass, gradientBoundary: config.implementation.gradientBoundary)
    let alpha = MLX.clip(
        MLX.pow(preparedMass / MLXArray(config.thetaA), Float(config.n)),
        min: MLXArray(0.0),
        max: MLXArray(1.0)
    )
    let alphaExpanded = alpha.expandedDimensions(axis: 3)
    let flow = nablaU * (MLXArray(1.0) - alphaExpanded) - nablaA * alphaExpanded
    return (preparedMass, uk, scalarField, flow)
}

private func flowSandboxReferenceSobel(_ A: MLXArray, gradientBoundary: String) -> MLXArray {
    switch gradientBoundary {
    case "periodic":
        let a00 = rollMultiAxis(A, shifts: [1, 1], axes: [1, 2])
        let a01 = rollMultiAxis(A, shifts: [1, 0], axes: [1, 2])
        let a02 = rollMultiAxis(A, shifts: [1, -1], axes: [1, 2])
        let a10 = rollMultiAxis(A, shifts: [0, 1], axes: [1, 2])
        let a12 = rollMultiAxis(A, shifts: [0, -1], axes: [1, 2])
        let a20 = rollMultiAxis(A, shifts: [-1, 1], axes: [1, 2])
        let a21 = rollMultiAxis(A, shifts: [-1, 0], axes: [1, 2])
        let a22 = rollMultiAxis(A, shifts: [-1, -1], axes: [1, 2])

        let two = MLXArray(Float(2.0))
        let gx = (a00 + two * a10 + a20) - (a02 + two * a12 + a22)
        let gy = (a00 + two * a01 + a02) - (a20 + two * a21 + a22)
        return MLX.stacked([gy, gx], axis: 3)
    default:
        fatalError("Test helper only supports periodic Sobel gradients.")
    }
}

private func makeTwoChannelPatchBatch(sx: Int, sy: Int) -> MLXArray {
    let channels = 2
    var data = [Float](repeating: 0.0, count: sx * sy * channels)
    let size = 3
    let half = size / 2
    let cx = sx / 2
    let cy = sy / 2

    for x in (cx - half)..<(cx + size - half) {
        for y in (cy - half)..<(cy + size - half) {
            let idx = (x * sy + y) * channels
            if idx >= 0 && idx < data.count {
                data[idx] = 1.0
            }
        }
    }
    return MLXArray(data).reshaped([1, sx, sy, channels])
}

private func computePaperKernel2D(sx: Int, sy: Int, params: ResolvedParams, kernelIndex: Int) -> [Float] {
    let midX = sx / 2
    let midY = sy / 2
    let r = params.r[kernelIndex]
    let a = params.a[kernelIndex]
    let w = params.w[kernelIndex]
    let b = params.b[kernelIndex]

    var values = [Float](repeating: 0.0, count: sx * sy)
    var total: Float = 0.0
    for x in 0..<sx {
        let dx = Float(x - midX)
        for y in 0..<sy {
            let dy = Float(y - midY)
            let dist = sqrt(dx * dx + dy * dy)
            let D = dist / (params.R * r)
            var sum: Float = 0.0
            for j in 0..<a.count {
                let diff = D - a[j]
                let denom = 2.0 * w[j] * w[j]
                let exponent = -(diff * diff) / denom
                sum += b[j] * exp(exponent)
            }
            let idx = x * sy + y
            values[idx] = sum
            total += sum
        }
    }
    if total > 0 {
        for i in 0..<values.count {
            values[i] /= total
        }
    }
    return values
}

private func unshift2(_ x: MLXArray) -> MLXArray {
    let shiftX = x.shape[0] / 2
    let shiftY = x.shape[1] / 2
    var result = MLX.roll(x, shift: -shiftX, axis: 0)
    result = MLX.roll(result, shift: -shiftY, axis: 1)
    return result
}

private func values(_ array: MLXArray) -> [Float] {
    eval(array)
    return array.flattened().asArray(Float.self)
}

private func sumArray(_ array: MLXArray) -> Float {
    return values(array).reduce(0.0, +)
}

private func minArray(_ array: MLXArray) -> Float {
    return values(array).min() ?? 0.0
}

private func maxAbsDiff(_ a: MLXArray, _ b: MLXArray) -> Float {
    let av = values(a)
    let bv = values(b)
    var maxDiff: Float = 0.0
    for (x, y) in zip(av, bv) {
        let diff = abs(x - y)
        if diff > maxDiff {
            maxDiff = diff
        }
    }
    return maxDiff
}

private func maxAbsDiff(_ a: [Float], _ b: [Float]) -> Float {
    var maxDiff: Float = 0.0
    for (x, y) in zip(a, b) {
        let diff = abs(x - y)
        if diff > maxDiff {
            maxDiff = diff
        }
    }
    return maxDiff
}

private func maxParamDiffOnMassSupport(expected: MLXArray, actual: MLXArray, support: MLXArray, threshold: Float = 1e-6) -> Float {
    let expectedValues = values(expected)
    let actualValues = values(actual)
    let supportValues = values(support)
    let paramCount = expected.shape.last ?? 0
    if paramCount == 0 {
        return 0.0
    }

    var maxDiff: Float = 0.0
    for (cellIndex, mass) in supportValues.enumerated() where mass > threshold {
        let base = cellIndex * paramCount
        for paramIndex in 0..<paramCount {
            let diff = abs(expectedValues[base + paramIndex] - actualValues[base + paramIndex])
            if diff > maxDiff {
                maxDiff = diff
            }
        }
    }
    return maxDiff
}

private func sandboxIndex(x: Int, y: Int, height: Int) -> Int {
    x * height + y
}

private func sandboxParamIndex(x: Int, y: Int, param: Int, height: Int, parameterCount: Int) -> Int {
    (sandboxIndex(x: x, y: y, height: height) * parameterCount) + param
}
