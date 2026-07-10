import XCTest
@testable import LeniaCore
import LeniaVisuals
@testable import LeniaStudio

final class RuntimeSessionCorrectnessTests: XCTestCase {
    func testStrokeInterpolationFillsEveryGridCellAlongSegment() {
        XCTAssertEqual(
            labInterpolatedStrokePoints(
                from: SIMD2<Int>(2, 3),
                to: SIMD2<Int>(7, 5)
            ),
            [
                SIMD2<Int>(2, 3),
                SIMD2<Int>(3, 3),
                SIMD2<Int>(4, 4),
                SIMD2<Int>(5, 4),
                SIMD2<Int>(6, 5),
                SIMD2<Int>(7, 5),
            ]
        )
    }

    func testProjectionFramesDeriveMatterAndChannelsFromOneInterleavedReadback() throws {
        let snapshot = liveProjectionFrames(
            massData: [0, 0.25, 0.5, 0.75, 1, 0.125],
            width: 2,
            height: 1,
            channels: 3,
            excludedMassChannels: [1],
            step: 7
        )

        XCTAssertEqual(snapshot.matterData, [0.5, 0.875])
        XCTAssertEqual(snapshot.frames[.matter]?.bytes, Data([127, 223]))
        XCTAssertEqual(snapshot.frames[.channel(0)]?.bytes, Data([0, 191]))
        XCTAssertEqual(snapshot.frames[.channel(1)]?.bytes, Data([63, 255]))
        XCTAssertEqual(snapshot.frames[.channel(2)]?.bytes, Data([127, 31]))
        XCTAssertTrue(snapshot.frames.values.allSatisfy { $0.step == 7 })
    }

    func testTTFrameSequenceRetainsEagerlyValidatedBytes() throws {
        let fixture = try makeTTFrameSequenceFixture(frames: [[1, 2, 3, 4]])
        defer { try? FileManager.default.removeItem(at: fixture.root) }

        let sequence = try TTFrameSequence.load(manifestURL: fixture.manifestURL)
        let replacement = Data([9, 8, 7, 6])
        try replacement.write(to: fixture.frameURLs[0], options: .atomic)

        XCTAssertEqual(sequence[0].bytes, Data([1, 2, 3, 4]))
    }

    func testTTFrameRuntimeUsesIndependentPlaybackClockAndExactSeek() async throws {
        let fixture = try makeTTFrameSequenceFixture(
            frames: [
                [0, 0, 0, 0],
                [32, 32, 32, 32],
                [255, 255, 255, 255],
            ],
            steps: [0, 10, 20]
        )
        defer { try? FileManager.default.removeItem(at: fixture.root) }

        let sequence = try TTFrameSequence.load(manifestURL: fixture.manifestURL)
        let handle = LabRuntimeHandle.frameSequence(TTFrameSequenceRuntime(sequence: sequence))

        let initial = await handle.snapshot(refreshMetrics: true, projection: .matter)
        let stillPaused = await handle.snapshot(refreshMetrics: true, projection: .matter)
        XCTAssertEqual(initial.step, 0)
        XCTAssertEqual(stillPaused.step, 0)

        await handle.setSpeedCap(hz: 20)
        await handle.start()
        let firstTick = await handle.snapshot(refreshMetrics: true, projection: .matter)
        try await Task.sleep(for: .milliseconds(60))
        let secondTick = await handle.snapshot(refreshMetrics: true, projection: .matter)
        XCTAssertEqual(firstTick.step, 0)
        XCTAssertEqual(secondTick.step, 10)

        try await Task.sleep(for: .milliseconds(60))
        let thirdTick = await handle.snapshot(refreshMetrics: true, projection: .matter)
        XCTAssertEqual(thirdTick.step, 20)

        await handle.pause()
        let paused = await handle.snapshot(refreshMetrics: true, projection: .matter)
        XCTAssertEqual(paused.step, 20)

        await handle.step()
        let stepped = await handle.snapshot(refreshMetrics: true, projection: .matter)
        XCTAssertEqual(stepped.step, 0)

        await handle.seekReplay(to: 1)
        let sought = await handle.snapshot(refreshMetrics: true, projection: .matter)
        let replayPosition = await handle.replayPosition()
        let position = try XCTUnwrap(replayPosition)
        XCTAssertEqual(sought.step, 10)
        XCTAssertEqual(position.frameIndex, 1)
        XCTAssertEqual(position.frameCount, 3)
    }

    func testTTFrameSnapshotAtomicallyReportsPositionAndTerminalPause() async throws {
        let steps = [0, 10, 20]
        let fixture = try makeTTFrameSequenceFixture(
            frames: [
                [0, 0, 0, 0],
                [32, 32, 32, 32],
                [255, 255, 255, 255],
            ],
            steps: steps
        )
        defer { try? FileManager.default.removeItem(at: fixture.root) }

        let sequence = try TTFrameSequence.load(manifestURL: fixture.manifestURL)
        let runtime = TTFrameSequenceRuntime(sequence: sequence)
        let handle = LabRuntimeHandle.frameSequence(runtime)
        XCTAssertTrue(handle.isIdentical(to: .frameSequence(runtime)))
        XCTAssertFalse(handle.isIdentical(to: .frameSequence(TTFrameSequenceRuntime(sequence: sequence))))

        let initial = await handle.frameSnapshot(refreshMetrics: true, projection: .matter)
        let initialPosition = try XCTUnwrap(initial.replayPosition)
        XCTAssertEqual(initial.snapshot.step, steps[initialPosition.frameIndex])
        XCTAssertFalse(initialPosition.isRunning)

        await handle.setReplayLooping(false)
        await handle.setSpeedCap(hz: 60)
        await handle.start()

        let clock = ContinuousClock()
        let deadline = clock.now + .seconds(1)
        var terminalFrame: LabRuntimeFrameSnapshot?
        while clock.now < deadline {
            let frame = await handle.frameSnapshot(refreshMetrics: true, projection: .matter)
            let position = try XCTUnwrap(frame.replayPosition)
            XCTAssertEqual(frame.snapshot.step, steps[position.frameIndex])
            if !position.isRunning {
                terminalFrame = frame
                break
            }
            try await Task.sleep(for: .milliseconds(2))
        }

        let terminal = try XCTUnwrap(terminalFrame)
        let terminalPosition = try XCTUnwrap(terminal.replayPosition)
        XCTAssertEqual(terminalPosition.frameIndex, steps.count - 1)
        XCTAssertEqual(terminal.snapshot.step, steps.last)
        XCTAssertFalse(terminalPosition.isLooping)
        XCTAssertFalse(terminalPosition.isRunning)

        try await Task.sleep(for: .milliseconds(40))
        let settled = await handle.frameSnapshot(refreshMetrics: true, projection: .matter)
        XCTAssertEqual(settled.snapshot.step, terminal.snapshot.step)
        XCTAssertEqual(settled.replayPosition, terminal.replayPosition)

        await handle.start()
        let restarted = await handle.frameSnapshot(refreshMetrics: true, projection: .matter)
        let restartedPosition = try XCTUnwrap(restarted.replayPosition)
        XCTAssertEqual(restartedPosition.frameIndex, 0)
        XCTAssertEqual(restarted.snapshot.step, steps.first)
        XCTAssertTrue(restartedPosition.isRunning)
        await handle.stop()
    }

    func testConcurrentThumbnailRequestsShareRenderedResult() async throws {
        try prepareMetalRuntime()
        let creature = LeniaCreature(
            seed: 42,
            score: 0.5,
            params: ResolvedParams(
                r: [1.0],
                b: [[1.0]],
                w: [[0.2]],
                a: [[1.0]],
                m: [0.2],
                s: [0.05],
                h: [1.0],
                R: 12,
                seed: 42
            ),
            sourceNode: "thumbnail-test"
        )

        async let first = ThumbnailRenderer.shared.render(creature: creature)
        async let second = ThumbnailRenderer.shared.render(creature: creature)
        let (firstImage, secondImage) = await (first, second)

        XCTAssertEqual(try XCTUnwrap(firstImage).width, 128)
        XCTAssertEqual(try XCTUnwrap(secondImage).height, 128)
    }

    @MainActor
    func testPausedFrameStoreSleepsAfterOneSnapshotUntilRefreshed() async throws {
        let fixture = try makeTTFrameSequenceFixture(frames: [[0, 64, 128, 255]])
        defer { try? FileManager.default.removeItem(at: fixture.root) }

        let sequence = try TTFrameSequence.load(manifestURL: fixture.manifestURL)
        let handle = LabRuntimeHandle.frameSequence(TTFrameSequenceRuntime(sequence: sequence))
        let store = LeniaLabFrameStore()
        var updateCount = 0
        store.run(
            runtime: handle,
            speedCap: 60,
            projection: .matter,
            isRunning: false
        ) { _ in
            updateCount += 1
        }
        defer { store.stop() }

        try await Task.sleep(for: .milliseconds(180))
        XCTAssertEqual(updateCount, 1)
        try await Task.sleep(for: .milliseconds(180))
        XCTAssertEqual(updateCount, 1)

        store.requestRefresh()
        try await Task.sleep(for: .milliseconds(180))
        XCTAssertEqual(updateCount, 2)
    }

    @MainActor
    func testPausedFrameStorePreservesRefreshRequestedDuringSnapshot() async throws {
        let fixture = try makeTTFrameSequenceFixture(frames: [[0, 64, 128, 255]])
        defer { try? FileManager.default.removeItem(at: fixture.root) }

        let sequence = try TTFrameSequence.load(manifestURL: fixture.manifestURL)
        let handle = LabRuntimeHandle.frameSequence(TTFrameSequenceRuntime(sequence: sequence))
        let snapshotBarrier = OneShotAsyncBarrier()
        let store = LeniaLabFrameStore {
            await snapshotBarrier.enterAndWait()
        }
        var updateCount = 0
        store.run(
            runtime: handle,
            speedCap: 60,
            projection: .matter,
            isRunning: false
        ) { _ in
            updateCount += 1
        }
        defer { store.stop() }

        await snapshotBarrier.waitUntilEntered()
        store.requestRefresh()
        await snapshotBarrier.release()
        try await waitForFrameUpdates(expected: 2) {
            updateCount
        }
        XCTAssertEqual(updateCount, 2)
    }

    @MainActor
    func testLatestTTFrameSequenceLoadWins() async throws {
        let slowFixture = try makeTTFrameSequenceFixture(
            frames: [[1, 1, 1, 1]],
            repeatedDescriptorCount: 4_000,
            directoryPrefix: "older"
        )
        let latestFixture = try makeTTFrameSequenceFixture(
            frames: [[2, 2, 2, 2]],
            directoryPrefix: "latest"
        )
        defer {
            try? FileManager.default.removeItem(at: slowFixture.root)
            try? FileManager.default.removeItem(at: latestFixture.root)
        }

        let model = LeniaLabModel()
        model.loadFrameSequence(manifestURL: slowFixture.manifestURL)
        await Task.yield()
        try await Task.sleep(for: .milliseconds(2))
        model.loadFrameSequence(manifestURL: latestFixture.manifestURL)

        for _ in 0..<100 where model.externalReplayTitle != latestFixture.root.lastPathComponent {
            try await Task.sleep(for: .milliseconds(10))
        }
        XCTAssertEqual(model.externalReplayTitle, latestFixture.root.lastPathComponent)

        try await Task.sleep(for: .milliseconds(250))
        XCTAssertEqual(model.externalReplayTitle, latestFixture.root.lastPathComponent)
        model.shutdown()
    }

    @MainActor
    func testSameSessionReplayMutationsExecuteInRequestOrder() async throws {
        let fixture = try makeTTFrameSequenceFixture(
            frames: [
                [0, 0, 0, 0],
                [64, 64, 64, 64],
                [128, 128, 128, 128],
                [255, 255, 255, 255],
            ],
            steps: [0, 10, 20, 30]
        )
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        let barrier = NamedMutationBarrier(blocking: "replay-seek")
        let model = LeniaLabModel(beforeRuntimeMutation: { name in
            await barrier.enter(name)
        })
        defer { model.shutdown() }

        model.loadFrameSequence(manifestURL: fixture.manifestURL)
        try await waitForLabModel(model) {
            model.hasSnapshot && model.replayFrameCount == 4
        }

        model.seekReplay(toProgress: 1)
        await barrier.waitUntilBlocked()
        model.stepReplayBackward()
        model.reset()
        model.step()
        model.setReplayLooping(false)
        model.seekReplay(toProgress: 0.5)
        model.stepReplayBackward()

        let whileBlocked = await barrier.recordedNames()
        XCTAssertEqual(whileBlocked, ["replay-seek"])
        await barrier.release()
        await model.waitForRuntimeMutations()

        let finalStep = await model.runtimeStepSnapshot()
        let mutationOrder = await barrier.recordedNames()
        XCTAssertEqual(finalStep, 10)
        XCTAssertFalse(model.replayIsLooping)
        XCTAssertEqual(
            mutationOrder,
            [
                "replay-seek",
                "replay-backward",
                "reset",
                "step",
                "replay-looping",
                "replay-seek",
                "replay-backward",
            ]
        )
    }

    @MainActor
    func testUndoThenRedoRestoresSnapshotsInRequestOrder() async throws {
        try prepareMetalRuntime()
        let preset = try XCTUnwrap(
            buildLabMissionPresets().first {
                $0.organismConfig?.catalogCollection == .flowNative
                    && $0.organismConfig?.catalogTier == .primary
            }
        )
        let draft = try XCTUnwrap(preset.defaultDraft)
        let barrier = NamedMutationBarrier(blocking: "restore")
        let model = LeniaLabModel(beforeRuntimeMutation: { name in
            await barrier.enter(name)
        })
        defer { model.shutdown() }

        model.rebuildWorld(
            sourceEntryID: preset.entry.id,
            runtimeConfig: draft.runtimeConfig(overridingBackend: .metalFull),
            backend: .metalFull,
            speedCap: 60
        )
        try await waitForLabModel(model) {
            model.hasSnapshot && model.checkpointCount == 1
        }
        model.step()
        await model.waitForRuntimeMutations()
        model.step()
        await model.waitForRuntimeMutations()
        let steppedTwice = await model.runtimeStepSnapshot()
        XCTAssertEqual(steppedTwice, 2)
        XCTAssertEqual(model.checkpointCount, 3)

        model.undo()
        await barrier.waitUntilBlocked()
        model.redo()
        await barrier.release()
        await model.waitForRuntimeMutations()

        let finalStep = await model.runtimeStepSnapshot()
        let mutationOrder = await barrier.recordedNames()
        XCTAssertEqual(finalStep, 2)
        XCTAssertEqual(model.history.current?.snapshot.step, 2)
        XCTAssertEqual(Array(mutationOrder.suffix(2)), ["restore", "restore"])
    }

    @MainActor
    func testWorldReplacementCancelsQueuedRuntimeMutations() async throws {
        let first = try makeTTFrameSequenceFixture(
            frames: [[0, 0, 0, 0], [1, 1, 1, 1], [2, 2, 2, 2]],
            steps: [0, 10, 20],
            directoryPrefix: "mutation-old"
        )
        let replacement = try makeTTFrameSequenceFixture(
            frames: [[9, 9, 9, 9], [8, 8, 8, 8]],
            steps: [100, 110],
            directoryPrefix: "mutation-new"
        )
        defer {
            try? FileManager.default.removeItem(at: first.root)
            try? FileManager.default.removeItem(at: replacement.root)
        }
        let barrier = NamedMutationBarrier(blocking: "replay-seek")
        let model = LeniaLabModel(beforeRuntimeMutation: { name in
            await barrier.enter(name)
        })
        defer { model.shutdown() }

        model.loadFrameSequence(manifestURL: first.manifestURL)
        try await waitForLabModel(model) {
            model.hasSnapshot && model.replayFrameCount == 3
        }
        model.seekReplay(toProgress: 1)
        await barrier.waitUntilBlocked()
        model.stepReplayBackward()
        model.loadFrameSequence(manifestURL: replacement.manifestURL)
        await barrier.release()

        try await waitForLabModel(model) {
            model.externalReplayTitle == replacement.root.lastPathComponent
                && model.hasSnapshot
                && model.replayFrameCount == 2
        }
        let finalStep = await model.runtimeStepSnapshot()
        let mutationOrder = await barrier.recordedNames()
        XCTAssertEqual(finalStep, 100)
        XCTAssertEqual(mutationOrder, ["replay-seek"])
    }

    @MainActor
    func testReplacementWorldPreservesCapturedRunIntent() async throws {
        try prepareMetalRuntime()
        let presets = buildLabMissionPresets()
        let orbium = try XCTUnwrap(presets.first { $0.id == "orbium-unicaudatus" })
        let paper = try XCTUnwrap(presets.first { $0.id == "parorbium-dividuus-pedes" })
        let orbiumDraft = try XCTUnwrap(orbium.defaultDraft)
        let paperDraft = try XCTUnwrap(paper.defaultDraft)
        let model = LeniaLabModel()
        defer { model.shutdown() }

        model.rebuildWorld(
            sourceEntryID: orbium.entry.id,
            runtimeConfig: orbiumDraft.runtimeConfig(overridingBackend: .metalFull),
            backend: .metalFull,
            speedCap: 120,
            shouldRun: false
        )
        try await waitForLabModel(model) {
            model.hasSnapshot && model.activeWorldEntryID == orbium.entry.id
        }

        model.setRunning(true)
        let shouldRun = model.isRunning
        model.rebuildWorld(
            sourceEntryID: paper.entry.id,
            runtimeConfig: paperDraft.runtimeConfig(overridingBackend: .metalFull),
            backend: .metalFull,
            speedCap: 120,
            shouldRun: shouldRun
        )
        try await waitForLabModel(model) {
            model.hasSnapshot && model.activeWorldEntryID == paper.entry.id
        }

        XCTAssertTrue(model.isRunning)
        let initialStep = model.latestStep
        try await waitForLabModel(model) {
            model.latestStep > initialStep
        }
    }

    @MainActor
    func testAutoplayWorldPublishesAndCheckpointsTZeroBeforeAdvancing() async throws {
        try prepareMetalRuntime()
        let preset = try XCTUnwrap(
            buildLabMissionPresets().first {
                $0.organismConfig?.catalogCollection == .flowNative
            }
        )
        let draft = try XCTUnwrap(preset.defaultDraft)
        let initializationBarrier = FirstCallAsyncBarrier()
        let model = LeniaLabModel(beforeExperimentSnapshot: {
            await initializationBarrier.blockFirstCall()
        })
        defer { model.shutdown() }

        model.rebuildWorld(
            sourceEntryID: preset.entry.id,
            runtimeConfig: draft.runtimeConfig(overridingBackend: .metalFull),
            backend: .metalFull,
            speedCap: 0,
            shouldRun: true
        )
        await initializationBarrier.waitUntilBlocked()

        let stepDuringInitialization = await model.runtimeStepSnapshot()
        XCTAssertTrue(model.hasSnapshot)
        XCTAssertEqual(model.latestStep, 0)
        XCTAssertEqual(stepDuringInitialization, 0)
        XCTAssertEqual(model.checkpointCount, 0)

        await initializationBarrier.release()
        try await waitForLabModel(model) {
            model.checkpointCount == 1
                && model.history.current?.snapshot.step == 0
                && model.latestStep > 0
        }

        XCTAssertTrue(model.isRunning)
        XCTAssertEqual(model.history.current?.snapshot.step, 0)
    }

    @MainActor
    func testManualStepPausesRuntimeBeforeAdvancingWhenPauseTransitionIsDelayed() async throws {
        try prepareMetalRuntime()
        let preset = try XCTUnwrap(
            buildLabMissionPresets().first {
                $0.organismConfig?.catalogCollection == .flowNative
            }
        )
        let draft = try XCTUnwrap(preset.defaultDraft)
        let pauseBarrier = FirstCallAsyncBarrier()
        let model = LeniaLabModel(beforeRunStateTransition: { running in
            guard !running else { return }
            await pauseBarrier.blockFirstCall()
        })
        defer { model.shutdown() }

        model.rebuildWorld(
            sourceEntryID: preset.entry.id,
            runtimeConfig: draft.runtimeConfig(overridingBackend: .metalFull),
            backend: .metalFull,
            speedCap: 0,
            shouldRun: true
        )
        try await waitForLabModel(model) {
            model.hasSnapshot && model.latestStep > 0
        }

        model.setRunning(false)
        await pauseBarrier.waitUntilBlocked()
        model.step(3)
        await model.waitForRuntimeMutations()

        let steppedSnapshot = await model.runtimeStepSnapshot()
        let stepped = try XCTUnwrap(steppedSnapshot)
        XCTAssertEqual(model.history.current?.label, "Step ×3")
        XCTAssertEqual(model.history.current?.snapshot.step, stepped)
        try await Task.sleep(for: .milliseconds(120))
        let settled = await model.runtimeStepSnapshot()
        XCTAssertEqual(settled, stepped)

        await pauseBarrier.release()
        await model.waitForRunStateTransition()
        XCTAssertFalse(model.isRunning)
    }

    func testCanonicalRestoreKeepsBaseWallsSeparateFromInteractiveOverlay() async throws {
        try prepareMetalRuntime()
        let config = try makeCanonicalWallRuntimeConfig()
        let runtime = CanonicalLabRuntime(runtimeConfig: config)
        let baseWallPoint = SIMD2<Int>(config.sx / 2, config.sy / 2)
        let baseWallIndex = baseWallPoint.x * config.sy + baseWallPoint.y
        let userWallPoint = SIMD2<Int>(2, 2)
        let userWallIndex = userWallPoint.x * config.sy + userWallPoint.y

        let initial = await runtime.materializeStateSnapshot()
        XCTAssertEqual(initial.walls[baseWallIndex], 0)
        XCTAssertEqual(initial.walls[userWallIndex], 1)
        let initialHasOverlay = await runtime.hasWallOverlay
        XCTAssertFalse(initialHasOverlay)

        try await runtime.restoreStateSnapshot(initial)
        let restoredInitialHasOverlay = await runtime.hasWallOverlay
        XCTAssertFalse(restoredInitialHasOverlay)
        let restoredInitial = await runtime.materializeStateSnapshot()
        XCTAssertEqual(restoredInitial.walls, initial.walls)

        await runtime.applyStroke(
            SandboxStroke(tool: .wall, points: [userWallPoint], radius: 0, strength: 1)
        )
        let edited = await runtime.materializeStateSnapshot()
        XCTAssertEqual(edited.walls[baseWallIndex], 0)
        XCTAssertEqual(edited.walls[userWallIndex], 0)
        let editedHasOverlay = await runtime.hasWallOverlay
        XCTAssertTrue(editedHasOverlay)

        await runtime.reset()
        let resetHasOverlay = await runtime.hasWallOverlay
        XCTAssertFalse(resetHasOverlay)
        try await runtime.restoreStateSnapshot(edited)
        let restoredEditHasOverlay = await runtime.hasWallOverlay
        XCTAssertTrue(restoredEditHasOverlay)
        let restoredEdit = await runtime.materializeStateSnapshot()
        XCTAssertEqual(restoredEdit.walls, edited.walls)
    }

    @MainActor
    func testStaleWorldInitializationCannotClearReplacementHistory() async throws {
        try prepareMetalRuntime()
        let flowPresets = buildLabMissionPresets().filter {
            $0.organismConfig?.catalogCollection == .flowNative
        }
        let first = try XCTUnwrap(flowPresets.first)
        let replacement = try XCTUnwrap(flowPresets.dropFirst().first)
        let firstDraft = try XCTUnwrap(first.defaultDraft)
        let replacementDraft = try XCTUnwrap(replacement.defaultDraft)
        let initializationBarrier = FirstCallAsyncBarrier()
        let model = LeniaLabModel(beforeExperimentSnapshot: {
            await initializationBarrier.blockFirstCall()
        })
        defer { model.shutdown() }

        model.rebuildWorld(
            sourceEntryID: first.entry.id,
            runtimeConfig: firstDraft.runtimeConfigValue,
            backend: .metalFull,
            speedCap: 120
        )
        await initializationBarrier.waitUntilBlocked()

        model.rebuildWorld(
            sourceEntryID: replacement.entry.id,
            runtimeConfig: replacementDraft.runtimeConfigValue,
            backend: .metalFull,
            speedCap: 120
        )
        try await waitForLabModel(model) {
            model.hasSnapshot
                && model.activeWorldEntryID == replacement.entry.id
                && model.checkpointCount == 1
        }

        await initializationBarrier.release()
        try await Task.sleep(for: .milliseconds(150))

        XCTAssertEqual(model.activeWorldEntryID, replacement.entry.id)
        XCTAssertEqual(model.checkpointCount, 1)
        XCTAssertEqual(model.history.current?.snapshot.step, 0)
    }

    @MainActor
    func testRapidFlowPresetSwitchingKeepsMaxSpeedPlaybackResponsive() async throws {
        try prepareMetalRuntime()
        let featuredFlow = buildLabMissionPresets().filter {
            $0.organismConfig?.featuredDescriptor?.collection == .flowNative
        }
        XCTAssertGreaterThanOrEqual(featuredFlow.count, 2)
        guard featuredFlow.count >= 2 else { return }
        let model = LeniaLabModel()
        defer { model.shutdown() }

        let iterationCount = 12
        let clock = ContinuousClock()
        var finalLoadStarted = clock.now
        for index in 0..<iterationCount {
            let preset = featuredFlow[index % featuredFlow.count]
            let draft = try XCTUnwrap(preset.defaultDraft)
            model.rebuildWorld(
                sourceEntryID: preset.entry.id,
                runtimeConfig: draft.runtimeConfig(overridingBackend: .metalFull),
                backend: .metalFull,
                speedCap: 0,
                shouldRun: true
            )
            if index == iterationCount - 1 {
                finalLoadStarted = clock.now
            }
            try await Task.sleep(for: .milliseconds(20))
        }

        let expected = featuredFlow[(iterationCount - 1) % featuredFlow.count]
        try await waitForLabModel(model, timeout: .seconds(12)) {
            model.hasSnapshot
                && model.activeWorldEntryID == expected.entry.id
                && model.worldContract?.backend == .metalFull
        }
        let startupSeconds = runtimeDurationSeconds(clock.now - finalLoadStarted)
        XCTAssertLessThan(startupSeconds, 5, "Latest-world load must not wait for stale preset builds")
        try await waitForLabModel(model, timeout: .seconds(8)) {
            model.activityHistory.count >= 2 && model.realizedStepRateHz > 0
        }

        print(
            String(
                format: "LENIA_LAB_SOAK grid=%d startup_ms=%.1f solver_hz=%.1f view_fps=%.1f",
                model.fieldWidth ?? 0,
                startupSeconds * 1_000,
                model.realizedStepRateHz,
                model.snapshotFps
            )
        )
        XCTAssertTrue(model.isRunning)
        XCTAssertEqual(model.fieldWidth, 256)
        XCTAssertGreaterThan(model.realizedStepRateHz, 30)
        XCTAssertGreaterThan(model.snapshotFps, 20)

        let stepSnapshot = await model.runtimeStepSnapshot()
        let stepAtPauseRequest = try XCTUnwrap(stepSnapshot)
        let pauseRequestedAt = ContinuousClock.now
        model.setRunning(false)
        await model.waitForRunStateTransition()
        let pausedSnapshot = await model.runtimeStepSnapshot()
        let pausedStep = try XCTUnwrap(pausedSnapshot)
        XCTAssertLessThan(runtimeDurationSeconds(ContinuousClock.now - pauseRequestedAt), 1)
        XCTAssertLessThanOrEqual(
            pausedStep - stepAtPauseRequest,
            16,
            "Pause should settle after at most one resident Metal batch"
        )
        try await Task.sleep(for: .milliseconds(120))
        let stablePausedStep = await model.runtimeStepSnapshot()
        XCTAssertEqual(stablePausedStep, pausedStep)
        try await waitForLabModel(model) {
            model.latestStep == pausedStep
        }

        model.step(3)
        try await waitForLabModel(model) {
            model.latestStep >= pausedStep + 3
        }

        model.setRunning(true)
        let resumedAt = model.latestStep
        try await waitForLabModel(model) {
            model.latestStep > resumedAt
        }

        for _ in 0..<4 {
            model.setRunning(false)
            try await Task.sleep(for: .milliseconds(20))
            model.setRunning(true)
            try await Task.sleep(for: .milliseconds(20))
        }
        let finalResumeStep = model.latestStep
        try await waitForLabModel(model) {
            model.latestStep > finalResumeStep
        }
        XCTAssertNil(model.runtimeStatusMessage)
    }

    @MainActor
    func testRapidFlowObserverSwitchingSupportsPauseScrubAndResume() async throws {
        try prepareMetalRuntime()
        let featuredFlow = buildLabMissionPresets().filter {
            $0.organismConfig?.featuredDescriptor?.collection == .flowNative
        }
        XCTAssertGreaterThanOrEqual(featuredFlow.count, 2)
        guard featuredFlow.count >= 2 else { return }
        let iterationCount = 9
        let expected = featuredFlow[(iterationCount - 1) % featuredFlow.count]
        let model = LiveSimulationModel()
        defer { model.stop() }

        let clock = ContinuousClock()
        var finalRestartAt = clock.now
        for index in 0..<iterationCount {
            let preset = featuredFlow[index % featuredFlow.count]
            model.restart(
                creature: preset.entry.creature,
                savedCreature: preset.entry.savedCreature,
                replaySource: preset.entry.replayReference
            )
            if index == iterationCount - 1 {
                finalRestartAt = clock.now
            }
            try await Task.sleep(for: .milliseconds(20))
        }

        try await waitForObservationModel(model, timeout: .seconds(12)) {
            model.frameCount > 40 && model.captureProgress == 1
        }
        let captureSeconds = runtimeDurationSeconds(clock.now - finalRestartAt)
        print(
            String(
                format: "LENIA_OBSERVER_SOAK grid=%d capture_ms=%.1f frames=%d",
                model.displayFrame?.width ?? 0,
                captureSeconds * 1_000,
                model.frameCount
            )
        )

        XCTAssertEqual(model.displayFrame?.width, 256)
        XCTAssertLessThan(captureSeconds, 5, "Render capture must not block Play on diagnostics")
        XCTAssertTrue(model.runtimeLabel.contains("Metal full"), model.runtimeLabel)
        XCTAssertNil(model.diagnosticImages, "Render capture must not precompute diagnostics")
        model.setPaused(true)
        model.seek(toProgress: 0)

        let replay = try XCTUnwrap(expected.entry.replayReference)
        let baseData = try Data(contentsOf: URL(fileURLWithPath: replay.baseConfigPath))
        let baseConfig = try loadRuntimeConfig(from: baseData)
        let expectedConfig = try studioRuntimeConfig(
            base: baseConfig,
            creature: expected.entry.creature,
            savedCreature: expected.entry.savedCreature
        )
        let simulator = FlowLeniaInteractiveSimulator(runtimeConfig: expectedConfig)
        let expectedMatter = simulator.matterMap(for: simulator.makeInitialState()).asArray(Float.self)
        XCTAssertEqual(model.displayFrame?.bytes, quantizedFieldBytes(expectedMatter))

        for progress in [0.8, 0.2, 1.0, 0.0, 0.5] {
            model.seek(toProgress: progress)
            let expectedIndex = Int((progress * Double(model.frameCount - 1)).rounded())
            XCTAssertEqual(model.currentFrameIndex, expectedIndex)
            XCTAssertTrue(model.isPaused)
        }

        let diagnosticStarted = clock.now
        model.setDiagnosticsEnabled(true)
        XCTAssertTrue(
            model.isDiagnosticsCaptureActive,
            "The detached diagnostics pass must be owned before this main-actor turn yields"
        )
        XCTAssertFalse(
            model.isDiagnosticsCaptureComplete,
            "Diagnostics must start asynchronously after Render playback is installed"
        )
        let diagnosticStartFrame = model.currentFrameIndex
        model.stepForward()
        XCTAssertNotEqual(model.currentFrameIndex, diagnosticStartFrame)
        XCTAssertTrue(
            model.isDiagnosticsCaptureActive,
            "Playback must remain interactive while diagnostics are still pending"
        )
        model.setPlaybackRate(4)
        let resumeFrame = model.currentFrameIndex
        model.setPaused(false)
        try await waitForObservationModel(model) {
            model.currentFrameIndex != resumeFrame
        }
        try await waitForObservationModel(model) {
            model.diagnosticImages != nil && model.diagnosticTelemetry != nil
        }
        print(
            String(
                format: "LENIA_DIAGNOSTICS_LAZY first_frame_ms=%.1f",
                runtimeDurationSeconds(clock.now - diagnosticStarted) * 1_000
            )
        )
        model.setPaused(true)
        let pausedFrame = model.currentFrameIndex
        try await Task.sleep(for: .milliseconds(120))
        XCTAssertEqual(model.currentFrameIndex, pausedFrame)
        XCTAssertEqual(model.playbackRate, 4)
        model.setDiagnosticsEnabled(false)
        try await waitForObservationModel(model) {
            !model.isDiagnosticsCaptureActive
        }
    }

    func testResidentMetalThroughputAtRepresentativeFlowGridSizes() throws {
        try prepareMetalRuntime()
        let configs = try bundledFeaturedOrganisms()
        let gridSizes = Set(configs.compactMap {
            $0.featuredDescriptor?.runtimeKind == .metal ? $0.gridSize : nil
        }).sorted()
        XCTAssertFalse(gridSizes.isEmpty)
        for gridSize in gridSizes {
            let featured = try XCTUnwrap(
                configs.first {
                    $0.gridSize == gridSize
                        && $0.featuredDescriptor?.runtimeKind == .metal
                }
            )
            let data = try Data(contentsOf: URL(fileURLWithPath: featured.path))
            let config = try loadRuntimeConfig(from: data, overrides: ["backend": "metal-full"])
            let simulator = FlowLeniaInteractiveSimulator(runtimeConfig: config)
            var state = simulator.makeInitialState()
            state = simulator.step(state, count: 8)

            let clock = ContinuousClock()
            let batchStarted = clock.now
            state = simulator.step(state, count: 16)
            let batchSeconds = runtimeDurationSeconds(clock.now - batchStarted)

            let sustainedSteps = 128
            let sustainedStarted = clock.now
            state = simulator.step(state, count: sustainedSteps)
            let sustainedSeconds = runtimeDurationSeconds(clock.now - sustainedStarted)
            let stepRate = Double(sustainedSteps) / sustainedSeconds

            print(
                String(
                    format: "LENIA_METAL_BENCH grid=%d batch16_ms=%.2f sustained_hz=%.1f",
                    gridSize,
                    batchSeconds * 1_000,
                    stepRate
                )
            )
            XCTAssertEqual(simulator.effectiveBackend, .metalFull)
            XCTAssertEqual(state.step, 8 + 16 + sustainedSteps)
            XCTAssertTrue(state.mass.asArray(Float.self).allSatisfy(\.isFinite))
            XCTAssertLessThan(batchSeconds, 2, "A 16-step batch must not monopolize playback")
            XCTAssertGreaterThan(stepRate, 5, "Resident Metal appears stalled or fell off the fast path")
        }
    }
}

private final class RuntimeSessionCorrectnessMarker {}

private func prepareMetalRuntime() throws {
    try LeniaMetalLibrarySupport.ensureAvailable(
        executableURL: Bundle(for: RuntimeSessionCorrectnessMarker.self).executableURL
    )
}

private func makeCanonicalWallRuntimeConfig() throws -> LeniaRuntimeConfig {
    let base = try makeLabWorldDraft(for: orbiumStarterEntry(), gridSize: 32).runtimeConfigValue
    return LeniaRuntimeConfig(
        backend: .metalFull,
        sx: base.sx,
        sy: base.sy,
        channels: base.channels,
        nbK: base.nbK,
        profile: base.profile,
        c0: base.c0,
        c1: base.c1,
        dt: base.dt,
        dd: base.dd,
        sigma: base.sigma,
        n: base.n,
        thetaA: base.thetaA,
        border: base.border,
        implementation: base.implementation,
        params: base.params,
        randomParamRanges: base.randomParamRanges,
        initSeed: base.initSeed,
        patches: base.patches,
        aUniform: base.aUniform,
        pUniform: base.pUniform,
        statePatch: base.statePatch,
        paramPatch: base.paramPatch,
        steps: base.steps,
        parameterEmbedding: base.parameterEmbedding,
        chemotaxis: base.chemotaxis,
        obstacleField: base.obstacleField,
        food: base.food,
        walls: WallsConfig(
            enabled: true,
            patches: [PatchConfig(center: [base.sx / 2, base.sy / 2], size: 4)]
        ),
        environment: base.environment,
        beamMutation: base.beamMutation,
        interventions: base.interventions
    )
}

@MainActor
private func waitForLabModel(
    _ model: LeniaLabModel,
    timeout: Duration = .seconds(8),
    condition: () -> Bool
) async throws {
    let clock = ContinuousClock()
    let deadline = clock.now + timeout
    while !condition() {
        guard clock.now < deadline else {
            XCTFail("Timed out waiting for Lenia Lab runtime state")
            return
        }
        try await Task.sleep(for: .milliseconds(20))
    }
}

@MainActor
private func waitForObservationModel(
    _ model: LiveSimulationModel,
    timeout: Duration = .seconds(8),
    condition: () -> Bool
) async throws {
    let clock = ContinuousClock()
    let deadline = clock.now + timeout
    while !condition() {
        guard clock.now < deadline else {
            XCTFail("Timed out waiting for observation playback state: \(model.stats)")
            return
        }
        try await Task.sleep(for: .milliseconds(20))
    }
}

private func runtimeDurationSeconds(_ duration: Duration) -> Double {
    Double(duration.components.seconds)
        + Double(duration.components.attoseconds) / 1_000_000_000_000_000_000.0
}

private actor OneShotAsyncBarrier {
    private var hasEntered = false
    private var isReleased = false
    private var entryWaiters: [CheckedContinuation<Void, Never>] = []
    private var releaseWaiters: [CheckedContinuation<Void, Never>] = []

    func enterAndWait() async {
        hasEntered = true
        let waiters = entryWaiters
        entryWaiters.removeAll()
        for waiter in waiters {
            waiter.resume()
        }
        guard !isReleased else { return }
        await withCheckedContinuation { continuation in
            releaseWaiters.append(continuation)
        }
    }

    func waitUntilEntered() async {
        guard !hasEntered else { return }
        await withCheckedContinuation { continuation in
            entryWaiters.append(continuation)
        }
    }

    func release() {
        isReleased = true
        let waiters = releaseWaiters
        releaseWaiters.removeAll()
        for waiter in waiters {
            waiter.resume()
        }
    }
}

private actor FirstCallAsyncBarrier {
    private var firstCallClaimed = false
    private var isReleased = false
    private var entryWaiters: [CheckedContinuation<Void, Never>] = []
    private var releaseWaiter: CheckedContinuation<Void, Never>?

    func blockFirstCall() async {
        guard !firstCallClaimed else { return }
        firstCallClaimed = true
        let waiters = entryWaiters
        entryWaiters.removeAll()
        for waiter in waiters {
            waiter.resume()
        }
        guard !isReleased else { return }
        await withCheckedContinuation { continuation in
            releaseWaiter = continuation
        }
    }

    func waitUntilBlocked() async {
        guard !firstCallClaimed else { return }
        await withCheckedContinuation { continuation in
            entryWaiters.append(continuation)
        }
    }

    func release() {
        isReleased = true
        releaseWaiter?.resume()
        releaseWaiter = nil
    }
}

private actor NamedMutationBarrier {
    private let blockedName: String
    private var hasClaimedBlock = false
    private var isBlocked = false
    private var isReleased = false
    private var names: [String] = []
    private var blockedWaiters: [CheckedContinuation<Void, Never>] = []
    private var releaseWaiter: CheckedContinuation<Void, Never>?

    init(blocking blockedName: String) {
        self.blockedName = blockedName
    }

    func enter(_ name: String) async {
        names.append(name)
        guard name == blockedName, !hasClaimedBlock else { return }
        hasClaimedBlock = true
        isBlocked = true
        let waiters = blockedWaiters
        blockedWaiters.removeAll()
        for waiter in waiters {
            waiter.resume()
        }
        guard !isReleased else { return }
        await withCheckedContinuation { continuation in
            releaseWaiter = continuation
        }
    }

    func waitUntilBlocked() async {
        guard !isBlocked else { return }
        await withCheckedContinuation { continuation in
            blockedWaiters.append(continuation)
        }
    }

    func release() {
        isReleased = true
        releaseWaiter?.resume()
        releaseWaiter = nil
    }

    func recordedNames() -> [String] {
        names
    }
}

@MainActor
private func waitForFrameUpdates(
    expected: Int,
    timeout: Duration = .seconds(2),
    count: () -> Int
) async throws {
    let clock = ContinuousClock()
    let deadline = clock.now + timeout
    while count() < expected {
        guard clock.now < deadline else {
            XCTFail("Timed out waiting for \(expected) frame updates; observed \(count()).")
            return
        }
        try await Task.sleep(for: .milliseconds(10))
    }
}

private func quantizedFieldBytes(_ values: [Float]) -> Data {
    Data(values.map { value in
        UInt8(max(0, min(255, Int(max(0, min(1, value)) * 255))))
    })
}

private struct TTFrameSequenceFixture {
    let root: URL
    let manifestURL: URL
    let frameURLs: [URL]
}

private func makeTTFrameSequenceFixture(
    frames: [[UInt8]],
    steps: [Int]? = nil,
    repeatedDescriptorCount: Int? = nil,
    directoryPrefix: String = "tt-runtime"
) throws -> TTFrameSequenceFixture {
    precondition(!frames.isEmpty)
    precondition(frames.allSatisfy { $0.count == 4 })
    if let steps {
        precondition(steps.count == frames.count)
    }

    let root = FileManager.default.temporaryDirectory
        .appendingPathComponent("\(directoryPrefix)-\(UUID().uuidString)")
    let frameDirectory = root.appendingPathComponent("frames")
    try FileManager.default.createDirectory(at: frameDirectory, withIntermediateDirectories: true)

    var frameURLs: [URL] = []
    var descriptors: [[String: Any]] = []
    for (index, bytes) in frames.enumerated() {
        let name = String(format: "frame_%06d.r8", index)
        let url = frameDirectory.appendingPathComponent(name)
        try Data(bytes).write(to: url)
        frameURLs.append(url)
        descriptors.append([
            "step": steps?[index] ?? index,
            "path": "frames/\(name)",
        ])
    }

    if let repeatedDescriptorCount, repeatedDescriptorCount > descriptors.count {
        let descriptor = descriptors[0]
        descriptors = (0..<repeatedDescriptorCount).map { index in
            [
                "step": index,
                "path": descriptor["path"]!,
            ]
        }
    }

    let manifest: [String: Any] = [
        "manifest_version": 1,
        "kind": "lenia_tt_frame_sequence",
        "backend": "tt",
        "config_path": "configs/base.json",
        "steps": descriptors.count,
        "frame_every": 1,
        "width": 2,
        "height": 2,
        "channels": 1,
        "projection": "matter",
        "batch_index": 0,
        "dtype": "uint8",
        "storage": "raw_r8",
        "frames": descriptors,
    ]
    let manifestURL = root.appendingPathComponent("manifest.json")
    try JSONSerialization.data(withJSONObject: manifest, options: [.sortedKeys])
        .write(to: manifestURL, options: .atomic)
    return TTFrameSequenceFixture(
        root: root,
        manifestURL: manifestURL,
        frameURLs: frameURLs
    )
}
