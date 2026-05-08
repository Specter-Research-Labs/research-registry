import ArgumentParser
import Foundation
import LeniaCore
import MLX

struct MediaCommand: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "media",
        abstract: "Render replay-capable research outputs to frame sequences and MP4 videos"
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

    @Option(name: .long, help: "ffmpeg executable")
    var ffmpeg: String = "ffmpeg"

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
        if let limit, limit <= 0 {
            throw ValidationError("--limit must be > 0")
        }
        let sceneModes = [scene, sharedScene, localizedSharedScene].filter { $0 }.count
        guard sceneModes <= 1 else {
            throw ValidationError("--scene, --shared-scene, and --localized-shared-scene are mutually exclusive")
        }
        let inputURL = URL(fileURLWithPath: try resolveArtifactPath(input, dossier: dossierName), isDirectory: true)
        let configDirURL = try configDir.map { URL(fileURLWithPath: try resolvePath($0, dossier: dossierName), isDirectory: true) }
        let outputURL = URL(fileURLWithPath: try resolveArtifactPath(output, dossier: dossierName), isDirectory: true)
        try FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)

        let records = try renderMedia(
            inputURL: inputURL,
            configDirURL: configDirURL,
            outputURL: outputURL,
            cells: cell,
            top: top,
            frameBudget: frameBudget,
            steps: steps,
            captureStride: captureStride,
            limit: limit,
            scene: scene,
            sharedScene: sharedScene,
            localizedSharedScene: localizedSharedScene,
            canvasSize: canvasSize,
            fps: fps,
            ffmpeg: ffmpeg
        )

        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(records).write(to: outputURL.appendingPathComponent("index.json"))
        print("Media: rendered=\(records.count) output=\(outputURL.path)")
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
    let framesPath: String
    let framesColorPath: String
    let videoPath: String
}

private func renderMedia(
    inputURL: URL,
    configDirURL: URL?,
    outputURL: URL,
    cells: [Int],
    top: Int,
    frameBudget: Int,
    steps: Int?,
    captureStride: Int,
    limit: Int?,
    scene: Bool,
    sharedScene: Bool,
    localizedSharedScene: Bool,
    canvasSize: Int,
    fps: Int,
    ffmpeg: String
) throws -> [MediaRenderRecord] {
    if FileManager.default.fileExists(atPath: inputURL.appendingPathComponent("repertoire/occupied.json").path),
       FileManager.default.fileExists(atPath: inputURL.appendingPathComponent("base.json").path),
       FileManager.default.fileExists(atPath: inputURL.appendingPathComponent("me.json").path) {
        return try renderQD2024Media(
            runURL: inputURL,
            configDirURL: configDirURL,
            outputURL: outputURL,
            cells: cells,
            top: top,
            frameBudget: frameBudget,
            steps: steps,
            scene: scene,
            sharedScene: sharedScene,
            localizedSharedScene: localizedSharedScene,
            canvasSize: canvasSize,
            fps: fps,
            ffmpeg: ffmpeg
        )
    }

    let ecologyBundles = try discoverLeniaRunBundles(from: inputURL).filter {
        $0.bundleKind == .flowLeniaEcology2025ArenaReplayBundleV1
    }
    if !ecologyBundles.isEmpty {
        let selectedBundles = limit.map { Array(ecologyBundles.prefix($0)) } ?? ecologyBundles
        return try selectedBundles.map {
            try renderEcologyMediaBundle(
                $0,
                outputRoot: outputURL,
                captureStride: captureStride,
                frameBudget: frameBudget,
                fps: fps,
                ffmpeg: ffmpeg
            )
        }
    }

    let portfolioBundles = try discoverPortfolioCandidateBundles(from: inputURL, top: limit ?? top)
    if !portfolioBundles.isEmpty {
        return try portfolioBundles.map {
            try renderPortfolioCandidateMediaBundle(
                $0,
                outputRoot: outputURL,
                frameBudget: frameBudget,
                steps: steps,
                fps: fps,
                ffmpeg: ffmpeg
            )
        }
    }

    let libraryReplayBundles = try discoverLibraryReplayBundles(from: inputURL)
    if !libraryReplayBundles.isEmpty {
        let selectedBundles = limit.map { Array(libraryReplayBundles.prefix($0)) } ?? libraryReplayBundles
        return try selectedBundles.map {
            try renderLibraryReplayMediaBundle(
                $0,
                outputRoot: outputURL,
                frameBudget: frameBudget,
                steps: steps,
                fps: fps,
                ffmpeg: ffmpeg
            )
        }
    }

    throw ValidationError("No media renderer matched \(inputURL.path). Expected a replay-capable run directory.")
}

private func renderQD2024Media(
    runURL: URL,
    configDirURL: URL?,
    outputURL: URL,
    cells: [Int],
    top: Int,
    frameBudget: Int,
    steps: Int?,
    scene: Bool,
    sharedScene: Bool,
    localizedSharedScene: Bool,
    canvasSize: Int,
    fps: Int,
    ffmpeg: String
) throws -> [MediaRenderRecord] {
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
        return [
            try renderQD2024MediaScene(
                run: run,
                elites: elites,
                outputRoot: outputURL,
                frameBudget: frameBudget,
                steps: steps,
                sharedScene: sharedScene,
                localizedSharedScene: localizedSharedScene,
                canvasSize: canvasSize,
                fps: fps,
                ffmpeg: ffmpeg
            )
        ]
    }
    return try elites.map { elite in
        try renderQD2024MediaElite(
            run: run,
            elite: elite,
            outputRoot: outputURL,
            frameBudget: frameBudget,
            steps: steps,
            fps: fps,
            ffmpeg: ffmpeg
        )
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
    fps: Int,
    ffmpeg: String
) throws -> MediaRenderRecord {
    let label = "qd-2024-cell-\(elite.cell)"
    let cellDir = outputRoot.appendingPathComponent(label, isDirectory: true)
    let framesURL = cellDir.appendingPathComponent("frames", isDirectory: true)
    let colorFramesURL = cellDir.appendingPathComponent("frames_color", isDirectory: true)
    try FileManager.default.createDirectory(at: framesURL, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: colorFramesURL, withIntermediateDirectories: true)

    let frames = try captureLeniaBreeder2024ReplayFrames(
        run: run,
        elite: elite,
        algorithmOverride: "me",
        frameBudget: frameBudget,
        stepsOverride: steps
    )
    let frameWriter = FrameWriter(outputDir: framesURL)
    let colorFrameWriter = ColorFrameWriter(outputDir: colorFramesURL)
    let size = run.base.worldSize
    for (index, frame) in frames.enumerated() {
        frameWriter.write(step: index, width: size, height: size, data: frame)
        colorFrameWriter.write(step: index, width: size, height: size, grayscale: frame)
    }
    if let error = frameWriter.error {
        throw error
    }
    if let error = colorFrameWriter.error {
        throw error
    }

    let videoURL = cellDir.appendingPathComponent("\(label).mp4")
    try encodeMP4FromPNGSequence(framesDir: colorFramesURL, outputURL: videoURL, fps: fps, ffmpeg: ffmpeg)

    return MediaRenderRecord(
        sourceMode: "qd-2024",
        label: label,
        cell: elite.cell,
        generation: elite.generation,
        fitness: elite.fitness,
        descriptor: elite.descriptor,
        selectionReason: nil,
        frames: frames.count,
        fps: fps,
        framesPath: framesURL.path,
        framesColorPath: colorFramesURL.path,
        videoPath: videoURL.path
    )
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
    fps: Int,
    ffmpeg: String
) throws -> MediaRenderRecord {
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
    let framesURL = sceneDir.appendingPathComponent("frames", isDirectory: true)
    let colorFramesURL = sceneDir.appendingPathComponent("frames_color", isDirectory: true)
    try FileManager.default.createDirectory(at: framesURL, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: colorFramesURL, withIntermediateDirectories: true)

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
    let frameWriter = FrameWriter(outputDir: framesURL)
    let colorFrameWriter = ColorFrameWriter(outputDir: colorFramesURL)
    for (index, frame) in frames.enumerated() {
        frameWriter.write(step: index, width: canvasSize, height: canvasSize, data: frame)
        colorFrameWriter.write(step: index, width: canvasSize, height: canvasSize, grayscale: frame)
    }
    if let error = frameWriter.error {
        throw error
    }
    if let error = colorFrameWriter.error {
        throw error
    }

    let videoURL = sceneDir.appendingPathComponent("\(label).mp4")
    try encodeMP4FromPNGSequence(framesDir: colorFramesURL, outputURL: videoURL, fps: fps, ffmpeg: ffmpeg)

    return MediaRenderRecord(
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
        fps: fps,
        framesPath: framesURL.path,
        framesColorPath: colorFramesURL.path,
        videoPath: videoURL.path
    )
}

private func renderEcologyMediaBundle(
    _ bundle: LeniaRunBundle,
    outputRoot: URL,
    captureStride: Int,
    frameBudget: Int,
    fps: Int,
    ffmpeg: String
) throws -> MediaRenderRecord {
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .deferredToDate
    guard bundle.bundleKind == .flowLeniaEcology2025ArenaReplayBundleV1 else {
        throw ValidationError("Unsupported ecology media bundle kind '\(bundle.bundleKind.rawValue)'.")
    }
    let baseConfig = try decoder.decode(LeniaBaseConfig.self, from: Data(contentsOf: try bundle.requireBaseConfig()))
    let payload = try decoder.decode(FlowLeniaEcology2025ReplayPayload.self, from: Data(contentsOf: try bundle.requirePayload()))
    let label = ecologyMediaLabel(payload)

    if let trajectoryFramesURL = bundle.trajectoryFramesURL,
       FileManager.default.fileExists(atPath: trajectoryFramesURL.path) {
        return try renderEcologyRecordedFrames(
            framesURL: trajectoryFramesURL,
            label: label,
            outputRoot: outputRoot,
            frameBudget: frameBudget,
            fps: fps,
            ffmpeg: ffmpeg
        )
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
            dissipation: payload.variant.dissipation
        )
    )

    let mediaDirs = try prepareEcologyMediaRunDirectories(label: label, outputRoot: outputRoot)
    let framesURL = mediaDirs.framesURL
    let colorFramesURL = mediaDirs.colorFramesURL

    let frameWriter = FrameWriter(outputDir: framesURL)
    let colorWriter = ColorFrameWriter(outputDir: colorFramesURL)
    for frame in rollout.recordedFrames {
        frameWriter.write(step: frame.step, width: frame.width, height: frame.height, data: frame.bytes)
        if let foodBytes = frame.foodBytes {
            let name = String(format: "frame_%06d.png", frame.step)
            let url = colorFramesURL.appendingPathComponent(name)
            try writePNGColorFrame(
                rgba: ecologyFoodRGBA(mass: frame.bytes, food: foodBytes),
                width: frame.width,
                height: frame.height,
                url: url
            )
        } else {
            colorWriter.write(step: frame.step, width: frame.width, height: frame.height, grayscale: frame.bytes)
        }
    }
    if let error = frameWriter.error {
        throw error
    }
    if let error = colorWriter.error {
        throw error
    }

    let videoURL = mediaDirs.runURL.appendingPathComponent("video.mp4")
    try encodeMP4FromPNGSequence(framesDir: colorFramesURL, outputURL: videoURL, fps: fps, ffmpeg: ffmpeg)
    return MediaRenderRecord(
        sourceMode: "flowlenia-ecology-2025",
        label: label,
        cell: nil,
        generation: nil,
        fitness: nil,
        descriptor: nil,
        selectionReason: nil,
        frames: rollout.recordedFrames.count,
        fps: fps,
        framesPath: framesURL.path,
        framesColorPath: colorFramesURL.path,
        videoPath: videoURL.path
    )
}

private func renderEcologyRecordedFrames(
    framesURL: URL,
    label: String,
    outputRoot: URL,
    frameBudget: Int,
    fps: Int,
    ffmpeg: String
) throws -> MediaRenderRecord {
    var isDirectory: ObjCBool = false
    if FileManager.default.fileExists(atPath: framesURL.path, isDirectory: &isDirectory),
       isDirectory.boolValue {
        return try renderEcologyRecordedPNGFrames(
            sourceRoot: framesURL,
            label: label,
            outputRoot: outputRoot,
            frameBudget: frameBudget,
            fps: fps,
            ffmpeg: ffmpeg
        )
    }

    let frames = try loadEcologyTrajectoryFrames(framesURL: framesURL, frameBudget: frameBudget)
    guard !frames.isEmpty else {
        throw ValidationError("Recorded ecology frame file is empty: \(framesURL.path)")
    }
    let mediaDirs = try prepareEcologyMediaRunDirectories(label: label, outputRoot: outputRoot)
    let framesOutputURL = mediaDirs.framesURL
    let colorFramesURL = mediaDirs.colorFramesURL

    let frameWriter = FrameWriter(outputDir: framesOutputURL)
    let colorWriter = ColorFrameWriter(outputDir: colorFramesURL)
    for frame in frames {
        frameWriter.write(step: frame.step, width: frame.width, height: frame.height, data: frame.bytes)
        if let foodBytes = frame.foodBytes {
            let name = String(format: "frame_%06d.png", frame.step)
            let url = colorFramesURL.appendingPathComponent(name)
            try writePNGColorFrame(
                rgba: ecologyFoodRGBA(mass: frame.bytes, food: foodBytes),
                width: frame.width,
                height: frame.height,
                url: url
            )
        } else {
            colorWriter.write(step: frame.step, width: frame.width, height: frame.height, grayscale: frame.bytes)
        }
    }
    if let error = frameWriter.error {
        throw error
    }
    if let error = colorWriter.error {
        throw error
    }

    let videoURL = mediaDirs.runURL.appendingPathComponent("video.mp4")
    try encodeMP4FromPNGSequence(framesDir: colorFramesURL, outputURL: videoURL, fps: fps, ffmpeg: ffmpeg)
    return MediaRenderRecord(
        sourceMode: "flowlenia-ecology-2025-recorded",
        label: label,
        cell: nil,
        generation: nil,
        fitness: nil,
        descriptor: nil,
        selectionReason: nil,
        frames: frames.count,
        fps: fps,
        framesPath: framesOutputURL.path,
        framesColorPath: colorFramesURL.path,
        videoPath: videoURL.path
    )
}

private struct EcologyMediaRunDirectories {
    let runURL: URL
    let framesURL: URL
    let colorFramesURL: URL
}

private func prepareEcologyMediaRunDirectories(label: String, outputRoot: URL) throws -> EcologyMediaRunDirectories {
    let runURL = outputRoot.appendingPathComponent(slugifyEcologyMediaLabel(label), isDirectory: true)
    if FileManager.default.fileExists(atPath: runURL.path) {
        try FileManager.default.removeItem(at: runURL)
    }
    let framesURL = runURL.appendingPathComponent("frames", isDirectory: true)
    let colorFramesURL = runURL.appendingPathComponent("frames_color", isDirectory: true)
    try FileManager.default.createDirectory(at: framesURL, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: colorFramesURL, withIntermediateDirectories: true)
    return EcologyMediaRunDirectories(runURL: runURL, framesURL: framesURL, colorFramesURL: colorFramesURL)
}

private func renderEcologyRecordedPNGFrames(
    sourceRoot: URL,
    label: String,
    outputRoot: URL,
    frameBudget: Int,
    fps: Int,
    ffmpeg: String
) throws -> MediaRenderRecord {
    let sourceFramesURL = sourceRoot.appendingPathComponent("frames", isDirectory: true)
    let sourceColorFramesURL = sourceRoot.appendingPathComponent("frames_color", isDirectory: true)
    let frameFiles = try selectedPNGFrameFiles(in: sourceFramesURL, frameBudget: frameBudget)
    let colorFrameFiles = try selectedPNGFrameFiles(in: sourceColorFramesURL, frameBudget: frameBudget)
    guard !colorFrameFiles.isEmpty else {
        throw ValidationError("Recorded ecology frame directory is empty: \(sourceColorFramesURL.path)")
    }

    let mediaDirs = try prepareEcologyMediaRunDirectories(label: label, outputRoot: outputRoot)
    try copyPNGFrames(frameFiles, to: mediaDirs.framesURL)
    try copyPNGFrames(colorFrameFiles, to: mediaDirs.colorFramesURL)
    let videoURL = mediaDirs.runURL.appendingPathComponent("video.mp4")
    try encodeMP4FromPNGSequence(framesDir: mediaDirs.colorFramesURL, outputURL: videoURL, fps: fps, ffmpeg: ffmpeg)
    return MediaRenderRecord(
        sourceMode: "flowlenia-ecology-2025-recorded",
        label: label,
        cell: nil,
        generation: nil,
        fitness: nil,
        descriptor: nil,
        selectionReason: nil,
        frames: colorFrameFiles.count,
        fps: fps,
        framesPath: mediaDirs.framesURL.path,
        framesColorPath: mediaDirs.colorFramesURL.path,
        videoPath: videoURL.path
    )
}

private func selectedPNGFrameFiles(in directory: URL, frameBudget: Int) throws -> [URL] {
    let files = try FileManager.default.contentsOfDirectory(
        at: directory,
        includingPropertiesForKeys: nil,
        options: [.skipsHiddenFiles]
    )
    .filter { $0.pathExtension == "png" }
    .sorted { $0.lastPathComponent < $1.lastPathComponent }
    let stride = max(1, Int(ceil(Double(files.count) / Double(frameBudget))))
    return files.enumerated().compactMap { index, file in
        index % stride == 0 ? file : nil
    }
}

private func copyPNGFrames(_ files: [URL], to outputDirectory: URL) throws {
    for file in files {
        try FileManager.default.copyItem(
            at: file,
            to: outputDirectory.appendingPathComponent(file.lastPathComponent)
        )
    }
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
