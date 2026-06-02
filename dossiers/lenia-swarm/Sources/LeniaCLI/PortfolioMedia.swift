import ArgumentParser
import Foundation
import LeniaCore
import LeniaVisuals

struct PortfolioMediaBundle {
    let directoryURL: URL
    let manifest: PortfolioBundleManifest
    let universe: PortfolioUniverseBundle
    let sampler: PortfolioSamplerBundle
    let candidate: PortfolioCandidateCore
    let metrics: SimulationMetrics
    let seedPatch: ResearchSeedPatch?
    let selectionReason: String?
}

struct PortfolioArchiveSummary: Codable {
    let representativeLimit: Int
    let representativeCount: Int
    let representativeNiches: [String]
    let representatives: [PortfolioArchiveRepresentative]

    enum CodingKeys: String, CodingKey {
        case representativeLimit = "representative_limit"
        case representativeCount = "representative_count"
        case representativeNiches = "representative_niches"
        case representatives
    }

    static func empty(limit: Int) -> PortfolioArchiveSummary {
        PortfolioArchiveSummary(
            representativeLimit: limit,
            representativeCount: 0,
            representativeNiches: [],
            representatives: []
        )
    }
}

struct PortfolioArchiveRepresentative: Codable {
    let sourceID: String
    let contentHash: String
    let niche: String
    let occupancyMean: Float
    let componentCount: Float?
    let largestComponentFraction: Float?
    let largestComponentAnisotropy: Float?
    let centerVelocity: Float
    let displacement: Float
    let foodConsumedFraction: Float

    enum CodingKeys: String, CodingKey {
        case sourceID = "source_id"
        case contentHash = "content_hash"
        case niche
        case occupancyMean = "occupancy_mean"
        case componentCount = "component_count"
        case largestComponentFraction = "largest_component_fraction"
        case largestComponentAnisotropy = "largest_component_anisotropy"
        case centerVelocity = "center_velocity"
        case displacement
        case foodConsumedFraction = "food_consumed_fraction"
    }
}

func summarizePortfolioArchive(from inputURL: URL, representativeLimit: Int) throws -> PortfolioArchiveSummary {
    let bundles = try discoverPortfolioCandidateBundles(from: inputURL, top: representativeLimit)
    let representatives = bundles.map { bundle in
        let niche = bundle.selectionReason ?? "explicit-bundle"
        return PortfolioArchiveRepresentative(
            sourceID: "portfolio-\(bundle.manifest.contentHash.prefix(16))",
            contentHash: bundle.manifest.contentHash,
            niche: niche,
            occupancyMean: bundle.metrics.occupancyMean,
            componentCount: bundle.metrics.componentCount,
            largestComponentFraction: bundle.metrics.largestComponentFraction,
            largestComponentAnisotropy: bundle.metrics.largestComponentAnisotropy,
            centerVelocity: bundle.metrics.centerVelocity,
            displacement: bundle.metrics.displacement,
            foodConsumedFraction: foodConsumedFraction(bundle.metrics)
        )
    }
    return PortfolioArchiveSummary(
        representativeLimit: representativeLimit,
        representativeCount: representatives.count,
        representativeNiches: Array(Set(representatives.map(\.niche))).sorted(),
        representatives: representatives
    )
}

func discoverPortfolioCandidateBundles(from inputURL: URL, top: Int) throws -> [PortfolioMediaBundle] {
    if FileManager.default.fileExists(atPath: inputURL.appendingPathComponent("manifest.json").path) {
        let bundle = try loadPortfolioMediaBundle(directory: inputURL)
        return bundle.manifest.bundleKind == "portfolio_candidate_bundle_v1" ? [bundle] : []
    }

    let candidatesRoot = inputURL.appendingPathComponent("artifacts/candidates", isDirectory: true)
    guard FileManager.default.fileExists(atPath: candidatesRoot.path),
          let enumerator = FileManager.default.enumerator(
            at: candidatesRoot,
            includingPropertiesForKeys: [.isRegularFileKey],
            options: [.skipsHiddenFiles]
          )
    else {
        return []
    }
    var bundles: [PortfolioMediaBundle] = []
    for case let manifestURL as URL in enumerator where manifestURL.lastPathComponent == "manifest.json" {
        let bundle = try loadPortfolioMediaBundle(directory: manifestURL.deletingLastPathComponent())
        guard bundle.manifest.bundleKind == "portfolio_candidate_bundle_v1" else { continue }
        bundles.append(bundle)
    }
    return selectPortfolioNicheBundles(bundles, limit: top)
}

private func loadPortfolioMediaBundle(directory: URL) throws -> PortfolioMediaBundle {
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .deferredToDate
    let manifest = try decoder.decode(
        PortfolioBundleManifest.self,
        from: Data(contentsOf: directory.appendingPathComponent("manifest.json"))
    )
    let universe = try decoder.decode(
        PortfolioUniverseBundle.self,
        from: Data(contentsOf: directory.appendingPathComponent("universe.json"))
    )
    let sampler = try decoder.decode(
        PortfolioSamplerBundle.self,
        from: Data(contentsOf: directory.appendingPathComponent("sampler.json"))
    )
    let candidate = try decoder.decode(
        PortfolioCandidateCore.self,
        from: Data(contentsOf: directory.appendingPathComponent("candidate.json"))
    )
    let metrics = try decoder.decode(
        SimulationMetrics.self,
        from: Data(contentsOf: directory.appendingPathComponent("metrics.json"))
    )
    let seedPatchURL = directory.appendingPathComponent("seed_patch.json")
    let seedPatch = FileManager.default.fileExists(atPath: seedPatchURL.path)
        ? try decoder.decode(ResearchSeedPatch.self, from: Data(contentsOf: seedPatchURL))
        : nil
    return PortfolioMediaBundle(
        directoryURL: directory,
        manifest: manifest,
        universe: universe,
        sampler: sampler,
        candidate: candidate,
        metrics: metrics,
        seedPatch: seedPatch,
        selectionReason: nil
    )
}

private func selectPortfolioNicheBundles(_ bundles: [PortfolioMediaBundle], limit: Int) -> [PortfolioMediaBundle] {
    guard limit > 0 else { return [] }
    var selected: [PortfolioMediaBundle] = []
    var selectedHashes = Set<String>()
    let orderedBundles = bundles.sorted { $0.manifest.contentHash < $1.manifest.contentHash }

    for niche in portfolioNiches {
        guard selected.count < limit else { break }
        guard let winner = bestPortfolioBundle(
            in: orderedBundles.filter { !selectedHashes.contains($0.manifest.contentHash) },
            score: { niche.rank($0.metrics) }
        )
        else {
            continue
        }
        selectedHashes.insert(winner.manifest.contentHash)
        selected.append(winner.withSelectionReason(niche.name))
    }

    while selected.count < limit {
        guard let winner = bestPortfolioBundle(
            in: orderedBundles.filter { !selectedHashes.contains($0.manifest.contentHash) },
            score: { descriptorDistance(from: $0.metrics, selected: selected) }
        )
        else {
            break
        }
        selectedHashes.insert(winner.manifest.contentHash)
        selected.append(winner.withSelectionReason("descriptor-spread"))
    }
    return selected
}

private func bestPortfolioBundle(
    in bundles: [PortfolioMediaBundle],
    score: (PortfolioMediaBundle) -> Float
) -> PortfolioMediaBundle? {
    bundles.reduce(nil) { best, candidate in
        guard let best else { return candidate }
        let candidateScore = score(candidate)
        let bestScore = score(best)
        if candidateScore > bestScore { return candidate }
        if candidateScore == bestScore && candidate.manifest.contentHash < best.manifest.contentHash {
            return candidate
        }
        return best
    }
}

private struct PortfolioNiche: Sendable {
    let name: String
    let rank: @Sendable (SimulationMetrics) -> Float
}

private let portfolioNiches: [PortfolioNiche] = [
    PortfolioNiche(name: "single-compact", rank: { descriptorTargetScore($0, occupancy: 0.25, components: 1, anisotropy: 0.35) }),
    PortfolioNiche(name: "single-large", rank: { descriptorTargetScore($0, occupancy: 0.65, components: 1, anisotropy: 0.60) }),
    PortfolioNiche(name: "paired", rank: { descriptorTargetScore($0, occupancy: 0.35, components: 2, anisotropy: 0.60) }),
    PortfolioNiche(name: "few-components", rank: { descriptorTargetScore($0, occupancy: 0.35, components: 3, anisotropy: 0.60) }),
    PortfolioNiche(name: "low-occupancy", rank: { -abs($0.occupancyMean - 0.15) }),
    PortfolioNiche(name: "motile", rank: { $0.centerVelocity }),
    PortfolioNiche(name: "food-consumer", rank: { foodConsumedFraction($0) }),
    PortfolioNiche(name: "low-anisotropy", rank: { -($0.largestComponentAnisotropy ?? 1) }),
    PortfolioNiche(name: "high-anisotropy", rank: { $0.largestComponentAnisotropy ?? 0 }),
    PortfolioNiche(name: "dense", rank: { $0.momentDensity ?? 0 }),
    PortfolioNiche(name: "compact", rank: { -$0.gyration }),
    PortfolioNiche(name: "displacing", rank: { $0.displacement })
]

private func descriptorTargetScore(
    _ metrics: SimulationMetrics,
    occupancy: Float,
    components: Float,
    anisotropy: Float
) -> Float {
    let componentCount = metrics.componentCount ?? 0
    let componentScore = -abs(componentCount - components) / 4
    let occupancyScore = -abs(metrics.occupancyMean - occupancy)
    let anisotropyScore = -abs((metrics.largestComponentAnisotropy ?? anisotropy) - anisotropy)
    return componentScore + occupancyScore + anisotropyScore
}

private func descriptorDistance(from metrics: SimulationMetrics, selected: [PortfolioMediaBundle]) -> Float {
    guard !selected.isEmpty else { return 0 }
    return selected.map { other in
        let a = portfolioDescriptor(metrics)
        let b = portfolioDescriptor(other.metrics)
        return zip(a, b).reduce(Float(0)) { partial, pair in
            let delta = pair.0 - pair.1
            return partial + delta * delta
        }
    }.min() ?? 0
}

private func portfolioDescriptor(_ metrics: SimulationMetrics) -> [Float] {
    [
        metrics.occupancyMean,
        min((metrics.componentCount ?? 0) / 8, 1),
        metrics.largestComponentAnisotropy ?? 0,
        min(metrics.centerVelocity / 0.005, 1),
        foodConsumedFraction(metrics),
        min(metrics.gyration / 12000, 1)
    ]
}

private func foodConsumedFraction(_ metrics: SimulationMetrics) -> Float {
    guard let initial = metrics.foodInitialMass, initial > 1e-6 else { return 0 }
    return max(metrics.foodConsumed ?? 0, 0) / initial
}

private extension PortfolioMediaBundle {
    func withSelectionReason(_ reason: String) -> PortfolioMediaBundle {
        PortfolioMediaBundle(
            directoryURL: directoryURL,
            manifest: manifest,
            universe: universe,
            sampler: sampler,
            candidate: candidate,
            metrics: metrics,
            seedPatch: seedPatch,
            selectionReason: reason
        )
    }
}

func renderPortfolioCandidateMediaBundle(
    _ bundle: PortfolioMediaBundle,
    outputRoot: URL,
    frameBudget: Int,
    steps: Int?,
    fps: Int,
    renderMode: LeniaRenderMode,
    ffmpeg: String
) throws -> MediaRenderRecord {
    let label = "portfolio-\(bundle.manifest.contentHash.prefix(12))"
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

    let replayConfig = try portfolioReplayBaseConfig(bundle: bundle, steps: steps)
    let runtimeConfig = try loadRuntimeConfig(from: JSONEncoder().encode(replayConfig))
    let replaySearch = portfolioReplaySearchConfig(
        bundle: bundle,
        steps: replayConfig.run.steps,
        frameBudget: frameBudget
    )
    let frames = try capturePortfolioReplayFrames(
        runtimeConfig: runtimeConfig,
        seed: bundle.candidate.seed,
        initSeedOffset: bundle.candidate.initSeed - bundle.candidate.seed,
        searchConfig: replaySearch,
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

    let videoURL = runURL.appendingPathComponent("video.mp4")
    try encodeMP4FromPNGSequence(framesDir: colorFramesURL, outputURL: videoURL, fps: fps, ffmpeg: ffmpeg)
    return MediaRenderRecord(
        sourceMode: "portfolio-candidate",
        label: label,
        cell: nil,
        generation: nil,
        fitness: bundle.candidate.score,
        descriptor: nil,
        selectionReason: bundle.selectionReason,
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

func portfolioReplayBaseConfig(bundle: PortfolioMediaBundle, steps: Int?) throws -> LeniaBaseConfig {
    let base = bundle.universe.baseConfig
    let statePatch = try portfolioReplayStatePatch(bundle: bundle, base: base)
    let initConfig = InitConfig(
        seed: bundle.candidate.initSeed,
        patches: statePatch == nil || base.parameter_embedding.enabled ? base.`init`.patches : [],
        a_uniform: statePatch == nil ? base.`init`.a_uniform : UniformRange(low: 0, high: 0),
        p_uniform: base.`init`.p_uniform,
        state_patch: statePatch,
        p_state_patch: base.`init`.p_state_patch
    )
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
            r: bundle.candidate.params.r,
            b: bundle.candidate.params.b,
            w: bundle.candidate.params.w,
            a: bundle.candidate.params.a,
            m: bundle.candidate.params.m,
            s: bundle.candidate.params.s,
            h: bundle.candidate.params.h,
            R: bundle.candidate.params.R
        ),
        init: initConfig,
        run: RunConfig(steps: steps ?? portfolioNativeReplaySteps(bundle: bundle, base: base)),
        interventions: base.interventions
    )
    let resolvedBackend = try resolveReplaySearchBackend(baseConfig: replayConfig)
    return baseConfigBySettingBackend(replayConfig, backend: resolvedBackend)
}

private func portfolioReplayStatePatch(bundle: PortfolioMediaBundle, base: LeniaBaseConfig) throws -> InitStatePatchConfig? {
    if let esConfig = bundle.sampler.esConfig,
       let initPatch = esConfig.initPatch,
       initPatch.enabled,
       let values = esConfig.initialInitPatchValues {
        return try portfolioExpandedStatePatch(
            values: values,
            width: initPatch.size,
            height: initPatch.size,
            center: initPatch.center,
            outputChannels: base.channels
        )
    }
    if let seedPatch = bundle.seedPatch {
        return try portfolioStatePatch(from: seedPatch, for: base)
    }
    return nil
}

private func portfolioExpandedStatePatch(
    values: [Float],
    width: Int,
    height: Int,
    center: [Int],
    outputChannels: Int
) throws -> InitStatePatchConfig {
    guard width > 0, height > 0, outputChannels > 0 else {
        throw ValidationError("Portfolio replay state patch dimensions must be positive.")
    }
    let cellCount = width * height
    guard values.count % cellCount == 0 else {
        throw ValidationError("Portfolio replay state patch has \(values.count) values for \(width)x\(height).")
    }
    let inputChannels = values.count / cellCount
    guard inputChannels <= outputChannels else {
        throw ValidationError("Portfolio replay state patch has \(inputChannels) channels but the universe has \(outputChannels).")
    }
    if inputChannels == outputChannels {
        return InitStatePatchConfig(center: center, width: width, height: height, channels: outputChannels, values: values)
    }
    var expanded = [Float](repeating: 0, count: cellCount * outputChannels)
    for cell in 0..<cellCount {
        for channel in 0..<inputChannels {
            expanded[cell * outputChannels + channel] = values[cell * inputChannels + channel]
        }
    }
    return InitStatePatchConfig(center: center, width: width, height: height, channels: outputChannels, values: expanded)
}

private func portfolioNativeReplaySteps(bundle: PortfolioMediaBundle, base: LeniaBaseConfig) -> Int {
    bundle.sampler.searchConfig?.steps ?? bundle.sampler.esConfig?.steps ?? base.run.steps
}

func portfolioReplaySearchConfig(
    bundle: PortfolioMediaBundle,
    steps: Int,
    frameBudget: Int
) -> SearchConfig {
    let parsedSearch = bundle.sampler.searchConfig
    let requestedFrames = max(frameBudget, 1)
    let warmupSteps = min(max(parsedSearch?.warmupSteps ?? 0, 0), max(steps - requestedFrames, 0))
    let postWarmupSteps = max(steps - warmupSteps, 1)
    let frameStride = max(1, postWarmupSteps / max(frameBudget, 1))
    return SearchConfig(
        steps: steps,
        recordInterval: frameStride,
        warmupSteps: warmupSteps,
        occupancyThreshold: parsedSearch?.occupancyThreshold ?? 0.05,
        componentThreshold: parsedSearch?.componentThreshold,
        massChannel: parsedSearch?.massChannel ?? -1,
        scoreWeights: [:],
        filters: [:],
        complexity: nil,
        activity: nil,
        stability: nil,
        kSurvival: nil,
        moments: nil
    )
}

private func capturePortfolioReplayFrames(
    runtimeConfig: LeniaRuntimeConfig,
    seed: Int,
    initSeedOffset: Int,
    searchConfig: SearchConfig,
    frameBudget: Int
) throws -> [CapturedStateFrame] {
    let stride = portfolioReplayFrameStride(searchConfig: searchConfig, frameBudget: frameBudget)
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
        initSeedOffset: initSeedOffset,
        searchConfig: searchConfig,
        frameCapture: capture
    )
    guard !capturedStateFrames.isEmpty || !capturedFrames.isEmpty else {
        throw ValidationError("Failed to capture portfolio replay frames for seed \(seed).")
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

func portfolioReplayFrameStride(searchConfig: SearchConfig, frameBudget: Int) -> Int {
    let postWarmupSteps = max(searchConfig.steps - searchConfig.warmupSteps, 1)
    return max(1, postWarmupSteps / max(frameBudget, 1))
}
