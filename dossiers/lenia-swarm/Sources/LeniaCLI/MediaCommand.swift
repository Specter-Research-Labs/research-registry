#if canImport(Metal)
import ArgumentParser
import CoreGraphics
import Foundation
import LeniaCore
import LeniaVisuals
import MLX

struct MediaCommand: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "media",
        abstract: "Render replay-capable research outputs to MP4 videos, with optional frame PNGs and contact sheets"
    )

    @Option(name: .long, help: "Path to a replay-capable run directory")
    var input: String

    @Option(name: .long, help: "Config directory with missing run assets, such as patterns/<pattern_id>.json")
    var configDir: String?

    @Option(name: .shortAndLong, help: "Output directory for rendered media")
    var output: String

    @Option(name: .long, parsing: .upToNextOption, help: "Specific qd-2024 MAP-Elites cell ids to render")
    var cell: [Int] = []

    @Option(name: .long, help: "Maximum representatives to render when explicit selection is omitted")
    var top: Int = 6

    @Option(name: .long, help: "Maximum replay frames to capture per specimen")
    var frameBudget: Int = 400

    @Option(name: .long, help: "Simulation steps to replay per specimen; defaults to the native replay length")
    var steps: Int?

    @Option(name: .long, parsing: .upToNextOption, help: "Exact native QD replay steps to capture for qd-2024 specimens")
    var nativeStep: [Int] = []

    @Option(name: .long, help: "Simulation steps between captured frames for Flow-Lenia ecology replay bundles")
    var captureStride: Int = 300

    @Option(name: .long, help: "Limit number of auto-detected ecology bundles to render")
    var limit: Int?

    @Flag(name: .long, help: "Render selected qd-2024 cells as independently replayed organisms composited into one scene")
    var scene: Bool = false

    @Flag(name: .long, help: "Render selected qd-2024 cells inside one native shared QD update")
    var sharedScene: Bool = false

    @Flag(name: .long, help: "Render selected qd-2024 cells inside one native shared QD update with localized per-specimen parameters")
    var localizedSharedScene: Bool = false

    @Option(name: .long, help: "Canvas size for scene renders")
    var canvasSize: Int = 512

    @Option(name: .long, help: "MP4 frames per second")
    var fps: Int = 6

    @Option(name: .long, help: "Render mode for mass-only videos: body, truth, magma, viridis, inferno, plasma, turbo, or flux")
    var renderMode: String = "body"

    @Option(name: .long, help: "ffmpeg executable")
    var ffmpeg: String = "ffmpeg"

    @Flag(name: .customLong("frames"), help: "Also write per-frame PNGs: exact grayscale truth to frames/ and the color render with alpha to frames_color/")
    var exportFrames: Bool = false

    @Flag(name: .long, help: "Write contact_sheet.png and contact_sheet_review.png from the first, middle and last frame of up to 24 specimens")
    var contactSheet: Bool = false

    func run() async throws {
        guard top > 0 else {
            throw ValidationError("--top must be > 0")
        }
        guard frameBudget > 1 else {
            throw ValidationError("--frame-budget must be > 1")
        }
        guard fps > 0 else {
            throw ValidationError("--fps must be > 0")
        }
        let ffmpegName = ffmpeg.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !ffmpegName.isEmpty else {
            throw ValidationError("--ffmpeg must name an executable")
        }
        guard ffmpegName != "true" && ffmpegName != "false" else {
            throw ValidationError("--ffmpeg expects an executable path or name; omit it to use ffmpeg")
        }
        guard captureStride > 0 else {
            throw ValidationError("--capture-stride must be > 0")
        }
        let resolvedRenderMode = try parseLeniaRenderMode(renderMode)
        if let limit, limit <= 0 {
            throw ValidationError("--limit must be > 0")
        }
        guard nativeStep.allSatisfy({ $0 >= 0 }) else {
            throw ValidationError("--native-step values must be non-negative")
        }
        let sceneModes = [scene, sharedScene, localizedSharedScene].filter { $0 }.count
        guard sceneModes <= 1 else {
            throw ValidationError("--scene, --shared-scene, and --localized-shared-scene are mutually exclusive")
        }
        if !nativeStep.isEmpty && sceneModes > 0 {
            throw ValidationError("--native-step is only supported for individual qd-2024 cell renders")
        }
        let inputURL = URL(fileURLWithPath: try resolveArtifactPath(input, dossier: dossierName), isDirectory: true)
        let configDirURL = try configDir.map { URL(fileURLWithPath: try resolvePath($0, dossier: dossierName), isDirectory: true) }
        let outputURL = URL(fileURLWithPath: try resolveArtifactPath(output, dossier: dossierName), isDirectory: true)
        try FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)

        var rendered = RenderedMedia(contactRowLimit: contactSheet ? 24 : 0)
        try renderMedia(
            into: &rendered,
            inputURL: inputURL,
            configDirURL: configDirURL,
            outputURL: outputURL,
            cells: cell,
            top: top,
            frameBudget: frameBudget,
            steps: steps,
            nativeSteps: nativeStep,
            captureStride: captureStride,
            limit: limit,
            scene: scene,
            sharedScene: sharedScene,
            localizedSharedScene: localizedSharedScene,
            canvasSize: canvasSize,
            renderMode: resolvedRenderMode,
            output: MediaOutputOptions(fps: fps, ffmpeg: ffmpegName, exportFrames: exportFrames)
        )

        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(rendered.records).write(to: outputURL.appendingPathComponent("index.json"))
        let sheetURLs = contactSheet
            ? try writeMediaContactSheets(rows: rendered.contactRows, outputURL: outputURL)
            : []
        let sheetSuffix = sheetURLs.map { " contactSheet=\($0.path)" }.joined()
        print("Media: rendered=\(rendered.records.count) output=\(outputURL.path)\(sheetSuffix)")
    }
}

struct MediaRenderRecord: Codable {
    let sourceMode: String
    let label: String
    let cell: Int?
    let generation: Int?
    let fitness: Float?
    let descriptor: [Float]?
    let selectionReason: String?
    let frames: Int
    let fps: Int
    let framesPath: String?
    let framesColorPath: String?
    let templatePatchesPath: String?
    let nativeSteps: [Int]?
    let videoPath: String
}

// Contact rows hold rendered images, so only the rows a sheet will show are
// kept while the rest of the specimens stream through.
private struct RenderedMedia {
    let contactRowLimit: Int
    private(set) var records: [MediaRenderRecord] = []
    private(set) var contactRows: [ContactSheetRow] = []

    init(contactRowLimit: Int) {
        self.contactRowLimit = contactRowLimit
    }

    mutating func add(_ record: MediaRenderRecord, _ contactRow: ContactSheetRow) {
        records.append(record)
        if contactRows.count < contactRowLimit {
            contactRows.append(contactRow)
        }
    }
}

private func renderMedia(
    into rendered: inout RenderedMedia,
    inputURL: URL,
    configDirURL: URL?,
    outputURL: URL,
    cells: [Int],
    top: Int,
    frameBudget: Int,
    steps: Int?,
    nativeSteps: [Int],
    captureStride: Int,
    limit: Int?,
    scene: Bool,
    sharedScene: Bool,
    localizedSharedScene: Bool,
    canvasSize: Int,
    renderMode: LeniaRenderMode,
    output: MediaOutputOptions
) throws {
    if FileManager.default.fileExists(atPath: inputURL.appendingPathComponent("repertoire/occupied.json").path),
       FileManager.default.fileExists(atPath: inputURL.appendingPathComponent("base.json").path),
       FileManager.default.fileExists(atPath: inputURL.appendingPathComponent("me.json").path) {
        try renderQD2024Media(
            into: &rendered,
            runURL: inputURL,
            configDirURL: configDirURL,
            outputURL: outputURL,
            cells: cells,
            top: top,
            frameBudget: frameBudget,
            steps: steps,
            nativeSteps: nativeSteps,
            scene: scene,
            sharedScene: sharedScene,
            localizedSharedScene: localizedSharedScene,
            canvasSize: canvasSize,
            renderMode: renderMode,
            output: output
        )
        return
    }

    let ecologyBundles = try discoverLeniaRunBundles(from: inputURL).filter {
        $0.bundleKind == .flowLeniaEcology2025ArenaReplayBundleV1
    }
    if !ecologyBundles.isEmpty {
        let selectedBundles = limit.map { Array(ecologyBundles.prefix($0)) } ?? ecologyBundles
        for bundle in selectedBundles {
            let specimen = try renderEcologyMediaBundle(
                bundle,
                outputRoot: outputURL,
                captureStride: captureStride,
                frameBudget: frameBudget,
                renderMode: renderMode,
                output: output
            )
            rendered.add(specimen.record, specimen.contactRow)
        }
        return
    }

    let libraryReplayBundles = try discoverLibraryReplayBundles(from: inputURL)
    if !libraryReplayBundles.isEmpty {
        let selectedBundles = limit.map { Array(libraryReplayBundles.prefix($0)) } ?? libraryReplayBundles
        for bundle in selectedBundles {
            let specimen = try renderLibraryReplayMediaBundle(
                bundle,
                outputRoot: outputURL,
                frameBudget: frameBudget,
                steps: steps,
                renderMode: renderMode,
                output: output
            )
            rendered.add(specimen.record, specimen.contactRow)
        }
        return
    }

    throw ValidationError("No media renderer matched \(inputURL.path). Expected a replay-capable run directory.")
}

private func renderQD2024Media(
    into rendered: inout RenderedMedia,
    runURL: URL,
    configDirURL: URL?,
    outputURL: URL,
    cells: [Int],
    top: Int,
    frameBudget: Int,
    steps: Int?,
    nativeSteps: [Int],
    scene: Bool,
    sharedScene: Bool,
    localizedSharedScene: Bool,
    canvasSize: Int,
    renderMode: LeniaRenderMode,
    output: MediaOutputOptions
) throws {
    let run = try loadLeniaBreeder2024ResolvedRun(
        runDirectory: runURL,
        configDirectoryOverride: configDirURL
    )
    let elites = try selectQD2024MediaElites(
        from: loadLeniaBreeder2024EliteSummaries(runDirectory: runURL),
        cells: cells,
        top: top
    )
    if scene || sharedScene || localizedSharedScene {
        let specimen = try renderQD2024MediaScene(
            run: run,
            elites: elites,
            outputRoot: outputURL,
            frameBudget: frameBudget,
            steps: steps,
            sharedScene: sharedScene,
            localizedSharedScene: localizedSharedScene,
            canvasSize: canvasSize,
            renderMode: renderMode,
            output: output
        )
        rendered.add(specimen.record, specimen.contactRow)
        return
    }
    for elite in elites {
        let specimen = try renderQD2024MediaElite(
            run: run,
            elite: elite,
            outputRoot: outputURL,
            frameBudget: frameBudget,
            steps: steps,
            nativeSteps: nativeSteps,
            renderMode: renderMode,
            output: output
        )
        rendered.add(specimen.record, specimen.contactRow)
    }
}

private func selectQD2024MediaElites(
    from elites: [LeniaBreeder2024EliteSummary],
    cells: [Int],
    top: Int
) throws -> [LeniaBreeder2024EliteSummary] {
    if cells.isEmpty {
        return Array(elites.sorted { lhs, rhs in
            if lhs.fitness == rhs.fitness { return lhs.cell < rhs.cell }
            return lhs.fitness > rhs.fitness
        }.prefix(top))
    }

    let byCell = Dictionary(uniqueKeysWithValues: elites.map { ($0.cell, $0) })
    return try cells.map { cell in
        guard let elite = byCell[cell] else {
            throw ValidationError("qd-2024 cell \(cell) is not occupied.")
        }
        return elite
    }
}

private func renderQD2024MediaElite(
    run: LeniaBreeder2024ResolvedRun,
    elite: LeniaBreeder2024EliteSummary,
    outputRoot: URL,
    frameBudget: Int,
    steps: Int?,
    nativeSteps: [Int],
    renderMode: LeniaRenderMode,
    output: MediaOutputOptions
) throws -> (record: MediaRenderRecord, contactRow: ContactSheetRow) {
    let label = "qd-2024-cell-\(elite.cell)"
    let cellDir = outputRoot.appendingPathComponent(label, isDirectory: true)

    let templatePatches: [InitStatePatchConfig]
    let frames: [Data]
    let frameSteps: [Int]
    if nativeSteps.isEmpty {
        templatePatches = try captureLeniaBreeder2024ReplayStatePatches(
            run: run,
            elite: elite,
            algorithmOverride: "me",
            frameBudget: frameBudget,
            stepsOverride: steps
        )
        frames = try captureLeniaBreeder2024ReplayFrames(
            run: run,
            elite: elite,
            algorithmOverride: "me",
            frameBudget: frameBudget,
            stepsOverride: steps
        )
        frameSteps = Array(frames.indices)
    } else {
        templatePatches = try captureLeniaBreeder2024ReplayStatePatchesAtSteps(
            run: run,
            elite: elite,
            algorithmOverride: "me",
            steps: nativeSteps,
            stepsOverride: steps
        )
        frames = try captureLeniaBreeder2024ReplayFramesAtSteps(
            run: run,
            elite: elite,
            algorithmOverride: "me",
            steps: nativeSteps,
            stepsOverride: steps
        )
        frameSteps = nativeSteps
    }
    let size = run.base.worldSize
    // Color frames crop to the creature so it fills the frame; truth frames
    // keep the full world for analysis.
    let box = autoFrameBox(grayscaleFrames: frames, width: size, height: size)
    let colorRenderer = try GrayscaleColorRenderer(renderMode: renderMode)
    let media = try writeSpecimenMedia(
        directory: cellDir,
        videoName: "\(label).mp4",
        frameCount: frames.count,
        output: output
    ) { index in
        let frame = frames[index]
        let color = if let box {
            try colorRenderer.render(width: box.side, height: box.side, grayscale: cropGrayscale(frame, width: size, box: box))
        } else {
            try colorRenderer.render(width: size, height: size, grayscale: frame)
        }
        return SpecimenFrame(step: frameSteps[index], truth: frame, truthWidth: size, truthHeight: size, color: color)
    }
    let templatePatchesURL = cellDir.appendingPathComponent("template_patches.json")
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    try encoder.encode(templatePatches).write(to: templatePatchesURL)

    let record = MediaRenderRecord(
        sourceMode: "qd-2024",
        label: label,
        cell: elite.cell,
        generation: elite.generation,
        fitness: elite.fitness,
        descriptor: elite.descriptor,
        selectionReason: nil,
        frames: frames.count,
        fps: output.fps,
        framesPath: media.framesURL?.path,
        framesColorPath: media.colorFramesURL?.path,
        templatePatchesPath: templatePatchesURL.path,
        nativeSteps: nativeSteps.isEmpty ? nil : nativeSteps,
        videoPath: media.videoURL.path
    )
    return (record, media.contactRow)
}

private func renderQD2024MediaScene(
    run: LeniaBreeder2024ResolvedRun,
    elites: [LeniaBreeder2024EliteSummary],
    outputRoot: URL,
    frameBudget: Int,
    steps: Int?,
    sharedScene: Bool,
    localizedSharedScene: Bool,
    canvasSize: Int,
    renderMode: LeniaRenderMode,
    output: MediaOutputOptions
) throws -> (record: MediaRenderRecord, contactRow: ContactSheetRow) {
    let cellLabel = elites.map { String($0.cell) }.joined(separator: "-")
    let label: String
    if localizedSharedScene {
        label = "qd-2024-localized-shared-scene-\(cellLabel)"
    } else if sharedScene {
        label = "qd-2024-shared-scene-\(cellLabel)"
    } else {
        label = "qd-2024-scene-\(cellLabel)"
    }
    let sceneDir = outputRoot.appendingPathComponent(label, isDirectory: true)

    let frames = if localizedSharedScene {
        try captureLeniaBreeder2024LocalizedSharedSceneFrames(
            run: run,
            elites: elites,
            algorithmOverride: "me",
            frameBudget: frameBudget,
            stepsOverride: steps,
            canvasSize: canvasSize
        )
    } else if sharedScene {
        try captureLeniaBreeder2024SharedSceneFrames(
            run: run,
            elites: elites,
            algorithmOverride: "me",
            frameBudget: frameBudget,
            stepsOverride: steps,
            canvasSize: canvasSize
        )
    } else {
        try captureLeniaBreeder2024SceneFrames(
            run: run,
            elites: elites,
            algorithmOverride: "me",
            frameBudget: frameBudget,
            stepsOverride: steps,
            canvasSize: canvasSize
        )
    }
    let colorRenderer = try GrayscaleColorRenderer(renderMode: renderMode)
    let media = try writeSpecimenMedia(
        directory: sceneDir,
        videoName: "\(label).mp4",
        frameCount: frames.count,
        output: output
    ) { index in
        SpecimenFrame(
            step: index,
            truth: frames[index],
            truthWidth: canvasSize,
            truthHeight: canvasSize,
            color: try colorRenderer.render(width: canvasSize, height: canvasSize, grayscale: frames[index])
        )
    }

    let record = MediaRenderRecord(
        sourceMode: localizedSharedScene
            ? "qd-2024-shared-native-localized"
            : (sharedScene ? "qd-2024-shared-native" : "qd-2024-scene-composite"),
        label: label,
        cell: nil,
        generation: elites.map(\.generation).max(),
        fitness: elites.map(\.fitness).max(),
        descriptor: nil,
        selectionReason: nil,
        frames: frames.count,
        fps: output.fps,
        framesPath: media.framesURL?.path,
        framesColorPath: media.colorFramesURL?.path,
        templatePatchesPath: nil,
        nativeSteps: nil,
        videoPath: media.videoURL.path
    )
    return (record, media.contactRow)
}

private func renderEcologyMediaBundle(
    _ bundle: LeniaRunBundle,
    outputRoot: URL,
    captureStride: Int,
    frameBudget: Int,
    renderMode: LeniaRenderMode,
    output: MediaOutputOptions
) throws -> (record: MediaRenderRecord, contactRow: ContactSheetRow) {
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .deferredToDate
    guard bundle.bundleKind == .flowLeniaEcology2025ArenaReplayBundleV1 else {
        throw ValidationError("Unsupported ecology media bundle kind '\(bundle.bundleKind.rawValue)'.")
    }
    let baseConfig = try decoder.decode(LeniaBaseConfig.self, from: Data(contentsOf: try bundle.requireBaseConfig()))
    let payload = try decoder.decode(FlowLeniaEcology2025ReplayPayload.self, from: Data(contentsOf: try bundle.requirePayload()))
    let label = ecologyMediaLabel(payload)
    let runURL = outputRoot.appendingPathComponent(slugifyEcologyMediaLabel(label), isDirectory: true)

    if let trajectoryFramesURL = bundle.trajectoryFramesURL {
        let frames = try loadEcologyTrajectoryFrames(framesURL: trajectoryFramesURL, frameBudget: frameBudget)
        guard !frames.isEmpty else {
            throw ValidationError("Recorded ecology frame file is empty: \(trajectoryFramesURL.path)")
        }
        let media = try writeEcologyMedia(
            frames: frames,
            speciesSeeds: nil,
            runURL: runURL,
            renderMode: renderMode,
            output: output
        )
        let record = ecologyMediaRecord(
            sourceMode: "flowlenia-ecology-2025-recorded",
            label: label,
            frames: frames.count,
            media: media,
            fps: output.fps
        )
        return (record, media.contactRow)
    }

    let sourceRuntime = try loadRuntimeConfig(from: JSONEncoder().encode(baseConfig))
    let resolvedBackend = try resolveReplaySimulatorBackend(runtimeConfig: sourceRuntime)
    let replayBaseConfig = baseConfigBySettingBackend(baseConfig, backend: resolvedBackend)
    let runtime = try loadRuntimeConfig(from: JSONEncoder().encode(replayBaseConfig))
    let evaluator = FlowLeniaSimulator(runtimeConfig: runtime)

    let initialState = try ecologyMediaArray(
        from: payload.initialState,
        sx: runtime.sx,
        sy: runtime.sy,
        channels: runtime.channels,
        label: "initial_state"
    )
    let initialParams = try ecologyMediaArray(
        from: payload.initialParams,
        sx: runtime.sx,
        sy: runtime.sy,
        channels: payload.initialParams.channels,
        label: "initial_params"
    )
    let initialFood = try payload.initialFood.map {
        try ecologyMediaScalarField(
            from: $0,
            sx: runtime.sx,
            sy: runtime.sy,
            label: "initial_food"
        )
    }

    let rollout = evaluator.rollout(
        initialState: initialState,
        initialParams: initialParams,
        initialFood: initialFood,
        config: FlowLeniaRolloutConfig(
            steps: payload.totalSteps,
            recordEverySteps: payload.recordEverySteps,
            captureEverySteps: captureStride,
            activityConfig: nil,
            foodSpawn: payload.variant.foodSpawn,
            dissipation: payload.variant.dissipation,
            captureParameters: renderMode == .species
        )
    )

    let speciesSeeds: [[Float]]?
    if renderMode == .species {
        guard let seeds = rollout.parameterSeeds, seeds.count == rollout.recordedFrames.count else {
            throw ValidationError(
                "Species render needs one parameter seed field per recorded frame; got \(rollout.parameterSeeds?.count ?? 0) for \(rollout.recordedFrames.count) frames."
            )
        }
        speciesSeeds = seeds
    } else {
        speciesSeeds = nil
    }
    let media = try writeEcologyMedia(
        frames: rollout.recordedFrames,
        speciesSeeds: speciesSeeds,
        runURL: runURL,
        renderMode: renderMode,
        output: output
    )
    let record = ecologyMediaRecord(
        sourceMode: "flowlenia-ecology-2025",
        label: label,
        frames: rollout.recordedFrames.count,
        media: media,
        fps: output.fps
    )
    return (record, media.contactRow)
}

private func writeEcologyMedia(
    frames: [LeniaTrajectoryFrame],
    speciesSeeds: [[Float]]?,
    runURL: URL,
    renderMode: LeniaRenderMode,
    output: MediaOutputOptions
) throws -> SpecimenMedia {
    let speciesRenderer = try speciesSeeds.map { _ in try makeLeniaMetalFieldRenderer() }
    let massRenderer = try GrayscaleColorRenderer(renderMode: renderMode)
    return try writeSpecimenMedia(
        directory: runURL,
        videoName: "video.mp4",
        frameCount: frames.count,
        output: output
    ) { index in
        let frame = frames[index]
        let color: CGImage
        if let speciesSeeds, let speciesRenderer {
            color = try renderEcologySpeciesImage(
                mass: frame.bytes,
                seed: speciesSeeds[index],
                width: frame.width,
                height: frame.height,
                renderer: speciesRenderer
            )
        } else if let foodBytes = frame.foodBytes {
            color = try rgbaImage(ecologyFoodRGBA(mass: frame.bytes, food: foodBytes), width: frame.width, height: frame.height)
        } else {
            color = try massRenderer.render(width: frame.width, height: frame.height, grayscale: frame.bytes)
        }
        return SpecimenFrame(step: frame.step, truth: frame.bytes, truthWidth: frame.width, truthHeight: frame.height, color: color)
    }
}

private func ecologyMediaRecord(sourceMode: String, label: String, frames: Int, media: SpecimenMedia, fps: Int) -> MediaRenderRecord {
    MediaRenderRecord(
        sourceMode: sourceMode,
        label: label,
        cell: nil,
        generation: nil,
        fitness: nil,
        descriptor: nil,
        selectionReason: nil,
        frames: frames,
        fps: fps,
        framesPath: media.framesURL?.path,
        framesColorPath: media.colorFramesURL?.path,
        templatePatchesPath: nil,
        nativeSteps: nil,
        videoPath: media.videoURL.path
    )
}

private func loadEcologyTrajectoryFrames(framesURL: URL, frameBudget: Int) throws -> [LeniaTrajectoryFrame] {
    let decoder = JSONDecoder()
    let lines = try String(contentsOf: framesURL, encoding: .utf8)
        .split(separator: "\n")
        .map(String.init)
    let stride = max(1, Int(ceil(Double(lines.count) / Double(frameBudget))))
    return try lines.enumerated().compactMap { index, line in
        guard index % stride == 0 else {
            return nil
        }
        return try decoder.decode(LeniaTrajectoryFrame.self, from: Data(line.utf8))
    }
}

private func ecologyMediaArray(
    from patch: InitStatePatchConfig,
    sx: Int,
    sy: Int,
    channels: Int,
    label: String
) throws -> MLXArray {
    guard patch.width == sx, patch.height == sy, patch.channels == channels else {
        throw ValidationError(
            "\(label) patch \(patch.width)x\(patch.height)x\(patch.channels) does not match runtime \(sx)x\(sy)x\(channels)."
        )
    }
    let values = patch.decodedValues()
    guard values.count == sx * sy * channels else {
        throw ValidationError("\(label) stores \(values.count) values but expected \(sx * sy * channels).")
    }
    return MLXArray(values).reshaped([sx, sy, channels])
}

private func ecologyMediaScalarField(
    from patch: InitStatePatchConfig,
    sx: Int,
    sy: Int,
    label: String
) throws -> MLXArray {
    guard patch.width == sx, patch.height == sy, patch.channels == 1 else {
        throw ValidationError(
            "\(label) patch \(patch.width)x\(patch.height)x\(patch.channels) does not match runtime scalar field \(sx)x\(sy)x1."
        )
    }
    let values = patch.decodedValues()
    guard values.count == sx * sy else {
        throw ValidationError("\(label) stores \(values.count) values but expected \(sx * sy).")
    }
    return MLXArray(values).reshaped([sx, sy])
}

private func ecologyFoodRGBA(mass: Data, food: Data) throws -> Data {
    guard mass.count == food.count else {
        throw FrameExportError.invalidSize(expected: mass.count, actual: food.count)
    }
    var rgba = [UInt8](repeating: 0, count: mass.count * 4)
    for index in 0..<mass.count {
        let m = Float(mass[index]) / 255
        let f = Float(food[index]) / 255
        rgba[index * 4] = UInt8(min(255, m * 255 + f * 32))
        rgba[index * 4 + 1] = UInt8(min(255, m * 180 + f * 230))
        rgba[index * 4 + 2] = UInt8(min(255, m * 90 + f * 40))
        rgba[index * 4 + 3] = 255
    }
    return Data(rgba)
}

private func ecologyMediaLabel(_ payload: FlowLeniaEcology2025ReplayPayload) -> String {
    "\(payload.variant.name)-pmut=\(ecologyProbabilityLabel(payload.mutationProbability))-repeat=\(payload.repeatIndex)"
}

private func ecologyProbabilityLabel(_ value: Float) -> String {
    let precision = abs(value) < 0.001 && value != 0 ? "%.6f" : "%.3f"
    return String(format: precision, value).replacingOccurrences(of: ".", with: "_")
}

private func slugifyEcologyMediaLabel(_ label: String) -> String {
    var output = ""
    var previousWasDash = false
    for scalar in label.unicodeScalars {
        let value = scalar.value
        if value >= 48 && value <= 57 || value >= 97 && value <= 122 {
            output.unicodeScalars.append(scalar)
            previousWasDash = false
        } else if value >= 65 && value <= 90, let lower = UnicodeScalar(value + 32) {
            output.unicodeScalars.append(lower)
            previousWasDash = false
        } else if !previousWasDash {
            output.append("-")
            previousWasDash = true
        }
    }
    let trimmed = output.trimmingCharacters(in: CharacterSet(charactersIn: "-"))
    return trimmed.isEmpty ? "ecology-run" : trimmed
}
#endif
