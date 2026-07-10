import XCTest
import MLX
import LeniaCore
@testable import LeniaStudio

final class FeaturedOrganismTests: XCTestCase {
    func testThumbnailBytesConvertXMajorPatchToTextureRowOrder() throws {
        let patch = InitStatePatchConfig(
            center: [1, 1],
            width: 2,
            height: 3,
            channels: 1,
            values: [0, 0.25, 0.5, 0.75, 1, 0.125]
        )

        XCTAssertEqual(
            Array(try XCTUnwrap(organismThumbnailBytes(from: patch))),
            [0, 191, 64, 255, 128, 32]
        )
    }

    func testFeaturedOrganismsAreExactNamedStatePatches() throws {
        let configs = try bundledFeaturedOrganisms()

        XCTAssertEqual(configs.count, 10)
        XCTAssertEqual(configs.first?.displayName, "Reticulated diamond")
        XCTAssertEqual(configs.filter(\.isFeatured).count, configs.count)
        XCTAssertEqual(configs.filter { $0.featuredDescriptor?.runtimeKind == .mlx }.count, 8)
        XCTAssertEqual(configs.filter { $0.featuredDescriptor?.runtimeKind == .metal }.count, 2)

        for config in configs {
            let data = try Data(contentsOf: URL(fileURLWithPath: config.path))
            let runtime = try loadRuntimeConfig(from: data)
            let patch = try XCTUnwrap(runtime.statePatch, config.displayName)
            let values = patch.decodedValues()

            XCTAssertFalse(config.family.isEmpty)
            XCTAssertFalse(config.genus.isEmpty)
            XCTAssertFalse(config.displayName.isEmpty)
            XCTAssertEqual(values.count, patch.width * patch.height * patch.channels)
            XCTAssertGreaterThan(values.max() ?? 0, 0.1)
        }
    }

    func testLabDefaultsAreCanonicalOrganismsWithExplicitBackends() throws {
        let presets = buildLabMissionPresets()

        XCTAssertEqual(presets.count, 10)
        XCTAssertEqual(presets.first?.id, "flow-sail-0aa5d7b6")
        XCTAssertTrue(presets.allSatisfy { $0.organismConfig != nil })
        for preset in presets {
            let draft = try XCTUnwrap(preset.defaultDraft)
            XCTAssertNotNil(draft.runtimeConfigValue.statePatch)
            if preset.organismConfig?.requiredLabBackend == .mlx {
                XCTAssertEqual(draft.runtimeConfigValue.backend, .mlx)
                XCTAssertEqual(draft.runtimeConfigValue.implementation.mode, "qd24_additive_v1")
            } else {
                XCTAssertEqual(draft.runtimeConfigValue.backend, .metalFull)
                XCTAssertEqual(draft.runtimeConfigValue.implementation.mode, "flowlenia_2022_paper_equations")
            }
        }
    }

    func testSelectableLabWorldsRetainOrganicFlowDefault() {
        let presets = buildAllLabWorldPresets()

        XCTAssertEqual(presets.first?.id, "flow-sail-0aa5d7b6")
        XCTAssertTrue(presets.contains { $0.id == "flow-compact-b0cd1441" })
        XCTAssertTrue(presets.contains { $0.id == "paper-1c" })
        XCTAssertEqual(Set(presets.map(\.id)).count, presets.count)
    }

    func testFeaturedCatalogSeparatesFlowLineagesFromClassicalReferences() throws {
        let configs = try bundledFeaturedOrganisms()
        let flow = configs.filter { $0.catalogCollection == .flowNative }
        let classical = configs.filter { $0.catalogCollection == .classicalReference }
        let primary = flow.filter { $0.catalogTier == .primary }
        let experimental = flow.filter { $0.catalogTier == .experimental }

        XCTAssertEqual(flow.count, 2)
        XCTAssertEqual(classical.count, 8)
        XCTAssertEqual(primary.count, 1)
        XCTAssertEqual(experimental.count, 1)
        XCTAssertTrue(classical.allSatisfy { $0.catalogTier == .reference })
        XCTAssertEqual(flowOrganismFamilies(from: flow).map(\.name), ["Linear Flowforms", "Sail Flowforms"])
        XCTAssertEqual(Set(flow.compactMap { $0.flowClassification?.specimen }), [
            "b0cd1441",
            "0aa5d7b6",
        ])
        XCTAssertTrue(flow.allSatisfy { $0.requiredLabBackend == .metalFull })
        XCTAssertTrue(flow.allSatisfy { $0.implementationMode == "flowlenia_2022_paper_equations" })
        XCTAssertTrue(classical.allSatisfy { $0.requiredLabBackend == .mlx })
        XCTAssertTrue(classical.allSatisfy { $0.implementationMode == "qd24_additive_v1" })

        let primaryEntry = try XCTUnwrap(primary.first).studioEntry()
        XCTAssertEqual(primaryEntry.taxonomy?.familyID, "Linear Flowforms")
        XCTAssertEqual(primaryEntry.taxonomy?.genusID, "Three-bead glider")
        XCTAssertEqual(primaryEntry.taxonomy?.speciesID, "b0cd1441")
        XCTAssertTrue(primaryEntry.traitLabels.contains("R12 stable transport"))

        let experimentalEntry = try XCTUnwrap(experimental.first).studioEntry()
        XCTAssertEqual(experimentalEntry.taxonomy?.familyID, "Sail Flowforms")
        XCTAssertEqual(experimentalEntry.taxonomy?.genusID, "Reticulated diamond")
        XCTAssertEqual(experimentalEntry.taxonomy?.speciesID, "0aa5d7b6")
        XCTAssertTrue(experimentalEntry.traitLabels.contains("R19 coherent remodeling"))
    }

    func testFeaturedOrganismFramingUsesActualPatchExtent() throws {
        let presets = buildLabMissionPresets()
        let orbium = try XCTUnwrap(presets.first { $0.id == "orbium-unicaudatus" }?.defaultDraft)
        let worm = try XCTUnwrap(presets.first { $0.id == "catenopteryx-cinguli" }?.defaultDraft)
        let blank = try XCTUnwrap(buildBlankLabMissionPresets().first?.defaultDraft)

        XCTAssertEqual(labRecommendedStageZoom(for: orbium.runtimeConfigValue), 3.648, accuracy: 0.001)
        XCTAssertEqual(labRecommendedStageZoom(for: worm.runtimeConfigValue), 1, accuracy: 0.001)
        XCTAssertEqual(labRecommendedStageZoom(for: blank.runtimeConfigValue), 1.35, accuracy: 0.001)
    }

    func testFeaturedStatePatchesBypassTheGenericInteractiveEngine() throws {
        let presets = buildLabMissionPresets()

        for preset in presets {
            let runtimeConfig = try XCTUnwrap(preset.defaultDraft?.runtimeConfigValue)
            XCTAssertTrue(
                labConfigRequiresCanonicalRuntime(runtimeConfig),
                "\(preset.name) must preserve its exact state and rule contract"
            )
        }

        let blank = try XCTUnwrap(buildBlankLabMissionPresets().first?.defaultDraft?.runtimeConfigValue)
        XCTAssertFalse(labConfigRequiresCanonicalRuntime(blank))
    }

    func testTaxonomySearchMatchesLineageAndPatternCode() throws {
        let configs = try bundledFeaturedOrganisms()
        let catalog = try loadTrack1TaxonomyCatalog(
            rootPath: URL(fileURLWithPath: try XCTUnwrap(configs.first).path)
                .deletingLastPathComponent()
                .path
        )

        let orbium = try XCTUnwrap(configs.first { $0.id.contains("orbium_unicaudatus") })
        XCTAssertTrue(track1Config(orbium, matches: "orbidae"))
        XCTAssertTrue(track1Config(orbium, matches: "Orbium"))
        XCTAssertTrue(track1Config(orbium, matches: "O2-a"))
        XCTAssertFalse(track1Config(orbium, matches: "helicidae"))

        let flow = try XCTUnwrap(
            configs.first { $0.featuredDescriptor?.id == "flow-compact-b0cd1441" }
        )
        XCTAssertTrue(track1Config(flow, matches: "linear flowforms"))
        XCTAssertTrue(track1Config(flow, matches: "stable transport"))
        XCTAssertTrue(track1Config(flow, matches: "b0cd1441"))

        let filtered = filteredTrack1Families(catalog.families, search: "Tetravolvium")
        XCTAssertEqual(filtered.map(\.name), ["Volvidae"])
        XCTAssertEqual(filtered.first?.genera.first?.configs.first?.displayName, "Tetravolvium")
    }

    func testBundledWormExecutesThroughMLXInteractiveRuntime() throws {
        let worm = try XCTUnwrap(
            bundledFeaturedOrganisms().first { $0.id.contains("catenopteryx") }
        )
        XCTAssertEqual(worm.requiredLabBackend, .mlx)
        XCTAssertTrue(worm.isLabLoadable)

        let data = try Data(contentsOf: URL(fileURLWithPath: worm.path))
        let config = try loadRuntimeConfig(from: data)
        XCTAssertEqual(config.backend, .mlx)
        XCTAssertEqual(config.implementation.mode, "qd24_additive_v1")

        let simulator = FlowLeniaInteractiveSimulator(runtimeConfig: config)
        let initial = simulator.makeInitialState()
        let next = simulator.step(initial)
        let matter = simulator.matterMap(for: next)
        eval(matter)
        let values = matter.asArray(Float.self)
        XCTAssertEqual(next.step, 1)
        XCTAssertTrue(values.allSatisfy(\.isFinite))
        XCTAssertGreaterThan(values.max() ?? 0, 0.1)
    }

    func testPrimaryAndReferenceOrganismsStayLocalizedAcrossObservationWindow() throws {
        let localizedCatalog = try bundledFeaturedOrganisms().filter {
            $0.catalogTier != .experimental
        }
        for config in localizedCatalog {
            let data = try Data(contentsOf: URL(fileURLWithPath: config.path))
            let runtimeConfig = try loadRuntimeConfig(from: data)
            let simulator = FlowLeniaInteractiveSimulator(runtimeConfig: runtimeConfig)
            let initial = simulator.makeInitialState()
            let initialMatter = simulator.matterMap(for: initial)
            let final = simulator.step(initial, count: 300)
            let finalMatter = simulator.matterMap(for: final)
            eval(initialMatter, finalMatter)

            let initialValues = initialMatter.asArray(Float.self)
            let finalValues = finalMatter.asArray(Float.self)
            let initialMass = initialValues.reduce(0, +)
            let finalMass = finalValues.reduce(0, +)
            let initialSupport = initialValues.count { $0 > 0.05 }
            let finalSupport = finalValues.count { $0 > 0.05 }

            XCTAssertGreaterThan(initialMass, 0, config.displayName)
            XCTAssertGreaterThan(initialSupport, 0, config.displayName)
            XCTAssertEqual(finalMass / initialMass, 1, accuracy: 0.08, config.displayName)
            XCTAssertEqual(
                Float(finalSupport) / Float(initialSupport),
                1,
                accuracy: 0.20,
                config.displayName
            )
        }
    }

    func testOrbiumLocomotionRemainsInWorldCoordinates() throws {
        let config = try XCTUnwrap(
            bundledFeaturedOrganisms().first { $0.id.contains("orbium_unicaudatus") }
        )
        let data = try Data(contentsOf: URL(fileURLWithPath: config.path))
        let runtimeConfig = try loadRuntimeConfig(from: data)
        let simulator = FlowLeniaInteractiveSimulator(runtimeConfig: runtimeConfig)
        let initial = simulator.makeInitialState()
        let initialMatter = simulator.matterMap(for: initial)
        let finalMatter = simulator.matterMap(for: simulator.step(initial, count: 300))
        eval(initialMatter, finalMatter)

        let start = centerOfMass(
            initialMatter.asArray(Float.self),
            width: runtimeConfig.sx,
            height: runtimeConfig.sy
        )
        let end = centerOfMass(
            finalMatter.asArray(Float.self),
            width: runtimeConfig.sx,
            height: runtimeConfig.sy
        )
        XCTAssertGreaterThan(hypot(end.x - start.x, end.y - start.y), 1.0)
    }

    @MainActor
    func testCanonicalObserverCapturesThenSeeksWithoutRerunning() async throws {
        let preset = try XCTUnwrap(
            buildLabMissionPresets().first { $0.id == "orbium-unicaudatus" }
        )
        let model = LiveSimulationModel()
        defer { model.stop() }

        model.start(
            creature: preset.entry.creature,
            savedCreature: preset.entry.savedCreature,
            replaySource: preset.entry.replayReference
        )
        for _ in 0..<200 where model.frameCount == 0 {
            try await Task.sleep(for: .milliseconds(50))
        }

        XCTAssertGreaterThan(model.frameCount, 40, model.stats)
        XCTAssertEqual(model.captureProgress, 1, accuracy: 0.001)
        model.setPaused(true)
        model.seek(toProgress: 1)
        XCTAssertEqual(model.currentFrameIndex, model.frameCount - 1)
        let terminalStep = model.stepCount
        model.stepBackward()
        XCTAssertEqual(model.currentFrameIndex, model.frameCount - 2)
        XCTAssertLessThan(model.stepCount, terminalStep)
        model.stepForward()
        XCTAssertEqual(model.stepCount, terminalStep)
    }

    private func centerOfMass(
        _ values: [Float],
        width: Int,
        height: Int
    ) -> (x: Float, y: Float) {
        var mass: Float = 0
        var weightedX: Float = 0
        var weightedY: Float = 0
        for x in 0..<width {
            for y in 0..<height {
                let value = values[x * height + y]
                mass += value
                weightedX += Float(x) * value
                weightedY += Float(y) * value
            }
        }
        return (weightedX / mass, weightedY / mass)
    }
}
