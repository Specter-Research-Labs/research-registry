import ArgumentParser
import Foundation
import LeniaCore

struct LibraryReplayBundle {
    let campaignDir: URL
    let manifest: LibraryReplayManifest
    let entry: ResearchLibraryEntry
    let baseConfig: LeniaBaseConfig
    let parsedSearch: ParsedSearchConfig
}

struct LibraryReplayManifest: Codable {
    let campaignId: String
    let inputKind: String
    let sourceCreatureId: String?
    let sourceRunId: String?
    let replayRunId: String?
}

func discoverLibraryReplayBundles(from inputURL: URL) throws -> [LibraryReplayBundle] {
    let campaignsURL = inputURL.appendingPathComponent("campaigns", isDirectory: true)
    guard FileManager.default.fileExists(atPath: campaignsURL.path) else {
        return []
    }
    let entries = try FileManager.default.contentsOfDirectory(
        at: campaignsURL,
        includingPropertiesForKeys: [.isDirectoryKey],
        options: [.skipsHiddenFiles]
    ).sorted { $0.lastPathComponent < $1.lastPathComponent }

    var bundles: [LibraryReplayBundle] = []
    let decoder = JSONDecoder()
    for campaignDir in entries {
        let manifestURL = campaignDir.appendingPathComponent("replay-manifest.json")
        guard FileManager.default.fileExists(atPath: manifestURL.path) else { continue }
        let manifest = try decoder.decode(LibraryReplayManifest.self, from: Data(contentsOf: manifestURL))
        guard manifest.inputKind == "library_index" || manifest.inputKind == "export_index" else { continue }

        let libraryURL = campaignDir.appendingPathComponent("library/index.jsonl")
        let configURL = campaignDir.appendingPathComponent("config.json")
        let searchURL = campaignDir.appendingPathComponent("search.json")
        for required in [libraryURL, configURL, searchURL] {
            guard FileManager.default.fileExists(atPath: required.path) else {
                throw ValidationError("Library replay bundle missing required file: \(required.path)")
            }
        }

        let libraryRaw = try String(contentsOf: libraryURL, encoding: .utf8)
        let lines = libraryRaw.split(separator: "\n", omittingEmptySubsequences: true)
        guard let firstLine = lines.first, let lineData = firstLine.data(using: .utf8) else {
            throw ValidationError("Library replay bundle empty: \(libraryURL.path)")
        }
        guard lines.count == 1 else {
            throw ValidationError("Library replay bundle expects exactly one entry, found \(lines.count): \(libraryURL.path)")
        }
        let entry = try decodeResearchLibraryEntry(lineData, decoder: decoder)
        let baseConfig = try decoder.decode(LeniaBaseConfig.self, from: Data(contentsOf: configURL))
        let parsedSearch = try decoder.decode(ParsedSearchConfig.self, from: Data(contentsOf: searchURL))

        bundles.append(
            LibraryReplayBundle(
                campaignDir: campaignDir,
                manifest: manifest,
                entry: entry,
                baseConfig: baseConfig,
                parsedSearch: parsedSearch
            )
        )
    }
    return bundles
}

func libraryReplayBaseConfig(
    bundle: LibraryReplayBundle,
    steps: Int?
) throws -> LeniaBaseConfig {
    let base = bundle.baseConfig
    let creature = bundle.entry.creature
    let initConfig = creature.initialCondition
    let resolvedSteps = steps ?? base.run.steps
    let replayConfig = LeniaBaseConfig(
        backend: base.backend,
        profile: base.profile,
        grid: base.grid,
        channels: base.channels,
        connectivity: base.connectivity,
        flow: base.flow,
        implementation: base.implementation,
        reintegration: base.reintegration,
        parameter_embedding: base.parameter_embedding,
        chemotaxis: base.chemotaxis,
        obstacle_field: base.obstacle_field,
        food: base.food,
        walls: base.walls,
        environment: base.environment,
        beam_mutation: base.beam_mutation,
        params: ParamsConfig(
            mode: "explicit",
            seed: nil,
            ranges: nil,
            r: creature.genotype.r,
            b: creature.genotype.b,
            w: creature.genotype.w,
            a: creature.genotype.a,
            m: creature.genotype.m,
            s: creature.genotype.s,
            h: creature.genotype.h,
            R: creature.genotype.R
        ),
        init: initConfig,
        run: RunConfig(steps: resolvedSteps),
        interventions: base.interventions
    )
    let resolvedBackend = try resolveReplaySearchBackend(baseConfig: replayConfig)
    return baseConfigBySettingBackend(replayConfig, backend: resolvedBackend)
}

func libraryReplaySearchConfig(
    parsed: ParsedSearchConfig,
    steps: Int,
    frameBudget: Int
) -> SearchConfig {
    let requestedFrames = max(frameBudget, 1)
    let warmupSteps = min(max(parsed.warmupSteps, 0), max(steps - requestedFrames, 0))
    let postWarmupSteps = max(steps - warmupSteps, 1)
    let frameStride = max(1, postWarmupSteps / requestedFrames)
    return SearchConfig(
        steps: steps,
        recordInterval: frameStride,
        warmupSteps: warmupSteps,
        occupancyThreshold: parsed.occupancyThreshold,
        componentThreshold: parsed.componentThreshold,
        massChannel: parsed.massChannel,
        scoreWeights: [:],
        filters: [:],
        complexity: nil,
        activity: nil,
        stability: nil,
        kSurvival: nil,
        moments: nil
    )
}

private func captureLibraryReplayFrames(
    runtimeConfig: LeniaRuntimeConfig,
    seed: Int,
    searchConfig: SearchConfig,
    frameBudget: Int
) throws -> [CapturedStateFrame] {
    let stride = max(1, max(searchConfig.steps - searchConfig.warmupSteps, 1) / max(frameBudget, 1))
    var capturedFrames: [Data] = []
    var capturedStateFrames: [CapturedStateFrame] = []
    capturedFrames.reserveCapacity(frameBudget + 8)
    capturedStateFrames.reserveCapacity(frameBudget + 8)
    let capture = FrameCapture(
        stride: stride,
        includeWarmup: false,
        sampleIndex: 0,
        handler: { _, _, _, data in
            capturedFrames.append(data)
        },
        stateHandler: { step, width, height, channels, values in
            capturedStateFrames.append(CapturedStateFrame(
                step: step,
                width: width,
                height: height,
                channels: channels,
                values: values
            ))
        }
    )
    let engine = SearchEngine(runtimeConfig: runtimeConfig)
    _ = engine.runBatch(
        seeds: [seed],
        initSeedOffset: 0,
        searchConfig: searchConfig,
        frameCapture: capture
    )
    guard !capturedStateFrames.isEmpty || !capturedFrames.isEmpty else {
        throw ValidationError("Failed to capture library replay frames for seed \(seed).")
    }
    if !capturedStateFrames.isEmpty {
        return Array(capturedStateFrames.prefix(frameBudget))
    }
    return Array(capturedFrames.prefix(frameBudget).enumerated().map { index, data in
        CapturedStateFrame(
            step: index,
            width: runtimeConfig.sx,
            height: runtimeConfig.sy,
            channels: 1,
            values: data.map { Float($0) / 255.0 }
        )
    })
}

func renderLibraryReplayMediaBundle(
    _ bundle: LibraryReplayBundle,
    outputRoot: URL,
    frameBudget: Int,
    steps: Int?,
    fps: Int,
    ffmpeg: String
) throws -> MediaRenderRecord {
    let creature = bundle.entry.creature
    let runId = bundle.manifest.sourceRunId ?? bundle.entry.runId
    let label = "library-\(creature.initialCondition.seed)-\(creature.name)"
    let runURL = outputRoot.appendingPathComponent(label, isDirectory: true)
    if FileManager.default.fileExists(atPath: runURL.path) {
        try FileManager.default.removeItem(at: runURL)
    }
    let framesURL = runURL.appendingPathComponent("frames", isDirectory: true)
    let colorFramesURL = runURL.appendingPathComponent("frames_color", isDirectory: true)
    let channelFramesURL = runURL.appendingPathComponent("frames_channels", isDirectory: true)
    let maskFramesURL = runURL.appendingPathComponent("frames_mask", isDirectory: true)
    try FileManager.default.createDirectory(at: framesURL, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: colorFramesURL, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: channelFramesURL, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: maskFramesURL, withIntermediateDirectories: true)

    let replayConfig = try libraryReplayBaseConfig(bundle: bundle, steps: steps)
    let runtimeConfig = try loadRuntimeConfig(from: JSONEncoder().encode(replayConfig))
    let searchConfig = libraryReplaySearchConfig(
        parsed: bundle.parsedSearch,
        steps: replayConfig.run.steps,
        frameBudget: frameBudget
    )
    let frames = try captureLibraryReplayFrames(
        runtimeConfig: runtimeConfig,
        seed: creature.initialCondition.seed,
        searchConfig: searchConfig,
        frameBudget: frameBudget
    )

    let matterScale = robustMatterScale(frames)
    let frameWriter = FrameWriter(outputDir: framesURL)
    let colorWriter = ChannelAwareColorFrameWriter(outputDir: colorFramesURL)
    let channelWriter = ChannelDiagnosticFrameWriter(outputDir: channelFramesURL)
    let maskWriter = FrameWriter(outputDir: maskFramesURL)
    for (index, frame) in frames.enumerated() {
        frameWriter.write(
            step: index,
            width: runtimeConfig.sx,
            height: runtimeConfig.sy,
            data: frame.matterBytes(scale: matterScale)
        )
        let indexedFrame = CapturedStateFrame(
            step: index,
            width: frame.width,
            height: frame.height,
            channels: frame.channels,
            values: frame.values
        )
        colorWriter.write(frame: indexedFrame, scale: matterScale)
        channelWriter.write(frame: indexedFrame, scale: matterScale)
        maskWriter.write(
            step: index,
            width: runtimeConfig.sx,
            height: runtimeConfig.sy,
            data: indexedFrame.supportMaskBytes(scale: matterScale)
        )
    }
    if let error = frameWriter.error {
        throw error
    }
    if let error = colorWriter.error {
        throw error
    }
    if let error = channelWriter.error {
        throw error
    }
    if let error = maskWriter.error {
        throw error
    }

    let videoURL = runURL.appendingPathComponent("\(label).mp4")
    try encodeMP4FromPNGSequence(framesDir: colorFramesURL, outputURL: videoURL, fps: fps, ffmpeg: ffmpeg)

    let specimenId = "result:\(runId)|overall|\(creature.initialCondition.seed)"
    try writeLibraryReplaySidecar(
        runURL: runURL,
        bundle: bundle,
        specimenId: specimenId,
        videoURL: videoURL,
        frameCount: frames.count,
        fps: fps
    )

    return MediaRenderRecord(
        sourceMode: "library-replay",
        label: label,
        cell: nil,
        generation: nil,
        fitness: creature.score,
        descriptor: nil,
        selectionReason: specimenId,
        frames: frames.count,
        fps: fps,
        framesPath: framesURL.path,
        framesColorPath: colorFramesURL.path,
        framesChannelPath: channelFramesURL.path,
        framesMaskPath: maskFramesURL.path,
        templatePatchesPath: nil,
        nativeSteps: nil,
        videoPath: videoURL.path
    )
}

struct LibraryReplaySidecar: Codable {
    let specimenId: String
    let runId: String
    let initSeed: Int
    let creatureName: String
    let creatureId: String
    let configHash: String?
    let score: Float?
    let frames: Int
    let fps: Int
    let videoPath: String

    enum CodingKeys: String, CodingKey {
        case specimenId = "specimen_id"
        case runId = "run_id"
        case initSeed = "init_seed"
        case creatureName = "creature_name"
        case creatureId = "creature_id"
        case configHash = "config_hash"
        case score
        case frames
        case fps
        case videoPath = "video_path"
    }
}

private func writeLibraryReplaySidecar(
    runURL: URL,
    bundle: LibraryReplayBundle,
    specimenId: String,
    videoURL: URL,
    frameCount: Int,
    fps: Int
) throws {
    let creature = bundle.entry.creature
    let sidecar = LibraryReplaySidecar(
        specimenId: specimenId,
        runId: bundle.manifest.sourceRunId ?? bundle.entry.runId,
        initSeed: creature.initialCondition.seed,
        creatureName: creature.name,
        creatureId: creature.id.uuidString,
        configHash: bundle.entry.configHash ?? creature.configHash,
        score: creature.score,
        frames: frameCount,
        fps: fps,
        videoPath: videoURL.path
    )
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    try encoder.encode(sidecar).write(to: runURL.appendingPathComponent("specimen.json"))
}
