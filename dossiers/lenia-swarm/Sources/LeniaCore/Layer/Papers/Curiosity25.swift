import Foundation
import Logging
import MLX

public struct AIScientist2025ExplorerConfig: Codable, Sendable {
    public let paper: String
    public let gridSize: Int
    public let totalSteps: Int
    public let coverageBinsPerDimension: Int
    public let coverageBoundsMode: String
    public let frameStride: Int
    public let mp4Framerate: Int
    public let evolutionaryActivityMetric: String
    public let experiments: [String]

    enum CodingKeys: String, CodingKey {
        case paper
        case gridSize = "grid_size"
        case totalSteps = "total_steps"
        case coverageBinsPerDimension = "coverage_bins_per_dimension"
        case coverageBoundsMode = "coverage_bounds_mode"
        case frameStride = "frame_stride"
        case mp4Framerate = "mp4_framerate"
        case evolutionaryActivityMetric = "evolutionary_activity_metric"
        case experiments
    }
}

public struct AIScientist2025ExperimentConfig: Codable, Sendable {
    public let name: String
    public let mode: String
    public let baseConfig: String
    public let iterations: Int
    public let bootstrapIterations: Int
    public let initPatchCount: Int
    public let initPatchSize: Int
    public let initParamMean: Float
    public let initParamStd: Float
    public let initZoneOrigin: [Int]?
    public let initZoneSize: Int?
    public let goalDimensions: [String]
    public let mutationProbabilityRange: [Float]
    public let beamPatchSizeRange: [Int]
    public let parameterMutation: IMGEPMutationConfig
    public let activity: ActivityConfig
    public let seed: Int
    public let foodPatchCount: Int?
    public let foodPatchSize: Int?
    public let foodPatchValue: Float?
    public let foodSpawn: FlowLeniaFoodSpawnConfig?
    public let dissipation: FlowLeniaDissipationConfig?

    enum CodingKeys: String, CodingKey {
        case name
        case mode
        case baseConfig = "base_config"
        case iterations
        case bootstrapIterations = "bootstrap_iterations"
        case initPatchCount = "init_patch_count"
        case initPatchSize = "init_patch_size"
        case initParamMean = "init_param_mean"
        case initParamStd = "init_param_std"
        case initZoneOrigin = "init_zone_origin"
        case initZoneSize = "init_zone_size"
        case goalDimensions = "goal_dimensions"
        case mutationProbabilityRange = "mutation_probability_range"
        case beamPatchSizeRange = "beam_patch_size_range"
        case parameterMutation = "parameter_mutation"
        case activity
        case seed
        case foodPatchCount = "food_patch_count"
        case foodPatchSize = "food_patch_size"
        case foodPatchValue = "food_patch_value"
        case foodSpawn = "food_spawn"
        case dissipation
    }
}

public struct AIScientist2025ConfigBundle: Sendable {
    public let configDirectory: URL
    public let explorer: AIScientist2025ExplorerConfig
    public let experiments: [AIScientist2025ExperimentConfig]
}

public struct AIScientist2025ExperimentState: Codable, Sendable {
    public let params: KernelParams
    public let mutationProbability: Float
    public let beamPatchSize: Int
    public let seed: Int
}

public struct AIScientist2025GoalRecord: Codable, Sendable {
    public let id: UUID
    public let experiment: String
    public let iteration: Int
    public let requestedGoal: [Float]?
    public let achievedGoal: [Float]
    public let state: AIScientist2025ExperimentState

    enum CodingKeys: String, CodingKey {
        case id
        case experiment
        case iteration
        case requestedGoal = "requested_goal"
        case achievedGoal = "achieved_goal"
        case state
    }
}

public struct AIScientist2025ExperimentSummary: Codable, Sendable {
    public let name: String
    public let mode: String
    public let records: Int
    public let averagePairwiseDistance: Float
    public let coverage: Int
    public let maxima: [Float]

    enum CodingKeys: String, CodingKey {
        case name
        case mode
        case records
        case averagePairwiseDistance = "average_pairwise_distance"
        case coverage
        case maxima
    }
}

public struct AIScientist2025Summary: Codable, Sendable {
    public let paper: String
    public let experiments: [AIScientist2025ExperimentSummary]
}

public func loadAIScientist2025ConfigBundle(configDirectory: URL) throws -> AIScientist2025ConfigBundle {
    let decoder = JSONDecoder()
    let explorer = try decoder.decode(
        AIScientist2025ExplorerConfig.self,
        from: Data(contentsOf: configDirectory.appendingPathComponent("explorer.json"))
    )
    var experiments: [AIScientist2025ExperimentConfig] = []
    for experimentName in explorer.experiments {
        let experiment = try decoder.decode(
            AIScientist2025ExperimentConfig.self,
            from: Data(contentsOf: configDirectory.appendingPathComponent("\(experimentName).json"))
        )
        experiments.append(experiment)
    }
    try validateAIScientist2025Bundle(explorer: explorer, experiments: experiments, configDirectory: configDirectory)
    return AIScientist2025ConfigBundle(
        configDirectory: configDirectory,
        explorer: explorer,
        experiments: experiments
    )
}

private func validateAIScientist2025Bundle(
    explorer: AIScientist2025ExplorerConfig,
    experiments: [AIScientist2025ExperimentConfig],
    configDirectory: URL
) throws {
    guard explorer.paper == "exploring-flow-lenia-universes-with-a-curiosity-driven-ai-scientist-2025" else {
        throw ConfigError.invalidConfig("ai-scientist-2025 explorer.paper must match the 2025 AI scientist paper identifier.")
    }
    guard explorer.gridSize == 256 else {
        throw ConfigError.invalidConfig("ai-scientist-2025 grid_size must be 256.")
    }
    guard explorer.totalSteps == 10_000 else {
        throw ConfigError.invalidConfig("ai-scientist-2025 total_steps must be 10000.")
    }
    guard explorer.coverageBinsPerDimension == 5 else {
        throw ConfigError.invalidConfig("ai-scientist-2025 coverage_bins_per_dimension must be 5.")
    }
    guard explorer.coverageBoundsMode == "observed_archive" else {
        throw ConfigError.invalidConfig("ai-scientist-2025 currently requires coverage_bounds_mode=\"observed_archive\" because the paper does not publish fixed descriptor bounds.")
    }
    guard explorer.frameStride > 0, explorer.mp4Framerate > 0 else {
        throw ConfigError.invalidConfig("ai-scientist-2025 frame_stride and mp4_framerate must be > 0.")
    }
    guard explorer.evolutionaryActivityMetric == "non_neutral" else {
        throw ConfigError.invalidConfig("ai-scientist-2025 evolutionary_activity_metric must be \"non_neutral\".")
    }
    guard !experiments.isEmpty else {
        throw ConfigError.invalidConfig("ai-scientist-2025 requires at least one experiment.")
    }

    for experiment in experiments {
        guard experiment.mode == "ecosystem" || experiment.mode == "movement" else {
            throw ConfigError.invalidConfig("ai-scientist-2025 experiment.mode must be ecosystem or movement.")
        }
        guard experiment.iterations > 0,
              experiment.bootstrapIterations > 0,
              experiment.bootstrapIterations <= experiment.iterations else {
            throw ConfigError.invalidConfig("ai-scientist-2025 iterations and bootstrap_iterations must be > 0 and bootstrap_iterations <= iterations.")
        }
        guard experiment.initPatchCount > 0, experiment.initPatchSize > 0 else {
            throw ConfigError.invalidConfig("ai-scientist-2025 init_patch_count and init_patch_size must be > 0.")
        }
        guard experiment.initParamStd > 0 else {
            throw ConfigError.invalidConfig("ai-scientist-2025 init_param_std must be > 0.")
        }
        guard experiment.mutationProbabilityRange.count == 2,
              experiment.mutationProbabilityRange[0] <= experiment.mutationProbabilityRange[1] else {
            throw ConfigError.invalidConfig("ai-scientist-2025 mutation_probability_range must be [low, high].")
        }
        guard experiment.beamPatchSizeRange.count == 2,
              experiment.beamPatchSizeRange[0] > 0,
              experiment.beamPatchSizeRange[0] <= experiment.beamPatchSizeRange[1] else {
            throw ConfigError.invalidConfig("ai-scientist-2025 beam_patch_size_range must be [low, high] with positive values.")
        }
        let baseURL = configDirectory.appendingPathComponent(experiment.baseConfig)
        guard FileManager.default.fileExists(atPath: baseURL.path) else {
            throw ConfigError.invalidConfig("ai-scientist-2025 base config is missing at \(baseURL.path).")
        }
        let runtime = try loadRuntimeConfig(from: Data(contentsOf: baseURL))
        guard runtime.sx == explorer.gridSize, runtime.sy == explorer.gridSize else {
            throw ConfigError.invalidConfig("ai-scientist-2025 base config grid must match explorer.grid_size.")
        }
        guard runtime.parameterEmbedding.enabled else {
            throw ConfigError.invalidConfig("ai-scientist-2025 base configs require parameter_embedding.enabled=true.")
        }
        guard runtime.beamMutation != nil else {
            throw ConfigError.invalidConfig("ai-scientist-2025 base configs require beam_mutation so the explorer can mutate the universe.")
        }
        guard try JSONDecoder().decode(LeniaBaseConfig.self, from: Data(contentsOf: baseURL)).params.ranges != nil else {
            throw ConfigError.invalidConfig("ai-scientist-2025 base configs must expose parameter ranges.")
        }
        if experiment.mode == "ecosystem" {
            guard experiment.goalDimensions == ["ea", "mp4_bytes", "h3", "h4", "h5", "h6", "h7"] else {
                throw ConfigError.invalidConfig("ai-scientist-2025 ecosystem goal_dimensions must match [ea, mp4_bytes, h3, h4, h5, h6, h7].")
            }
        } else {
            guard experiment.goalDimensions == ["center_x", "center_y"] else {
                throw ConfigError.invalidConfig("ai-scientist-2025 movement goal_dimensions must match [center_x, center_y].")
            }
        }
    }
}

public final class AIScientist2025Runner {
    private let configs: AIScientist2025ConfigBundle
    private let logger: Logger
    private let encoder: JSONEncoder

    public init(configs: AIScientist2025ConfigBundle, logger: Logger) {
        self.configs = configs
        self.logger = logger
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        self.encoder = encoder
    }

    public func writeResolvedConfigs(to outputDirectory: URL) throws {
        try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
        try encoder.encode(configs.explorer).write(to: outputDirectory.appendingPathComponent("explorer.json"))
        for experiment in configs.experiments {
            try encoder.encode(experiment).write(to: outputDirectory.appendingPathComponent("\(experiment.name).json"))
        }
    }

    public func run(outputDirectory: URL) throws -> AIScientist2025Summary {
        try writeResolvedConfigs(to: outputDirectory)
        var summaries: [AIScientist2025ExperimentSummary] = []
        for experiment in configs.experiments {
            let summary = try runExperiment(experiment, outputDirectory: outputDirectory.appendingPathComponent(experiment.name, isDirectory: true))
            summaries.append(summary)
        }
        let summary = AIScientist2025Summary(paper: configs.explorer.paper, experiments: summaries)
        try encoder.encode(summary).write(to: outputDirectory.appendingPathComponent("summary.json"))
        return summary
    }

    private func runExperiment(
        _ experiment: AIScientist2025ExperimentConfig,
        outputDirectory: URL
    ) throws -> AIScientist2025ExperimentSummary {
        try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
        let baseURL = configs.configDirectory.appendingPathComponent(experiment.baseConfig)
        let baseData = try Data(contentsOf: baseURL)
        let runtime = try loadRuntimeConfig(from: baseData)
        guard let ranges = try JSONDecoder().decode(LeniaBaseConfig.self, from: baseData).params.ranges else {
            throw ConfigError.invalidConfig("ai-scientist-2025 base config must expose params.ranges.")
        }

        var rng = SeededRandomNumberGenerator(seed: UInt64(experiment.seed))
        var records: [AIScientist2025GoalRecord] = []
        let archiveURL = outputDirectory.appendingPathComponent("archive.jsonl")
        FileManager.default.createFile(atPath: archiveURL.path, contents: nil)
        let archiveHandle = try FileHandle(forWritingTo: archiveURL)
        defer { try? archiveHandle.close() }
        let lineEncoder = JSONEncoder()

        for iteration in 0..<experiment.iterations {
            let state: AIScientist2025ExperimentState
            let requestedGoal: [Float]?
            if iteration < experiment.bootstrapIterations || records.isEmpty {
                state = aiScientist2025RandomState(runtime: runtime, ranges: ranges, experiment: experiment, rng: &rng)
                requestedGoal = nil
            } else {
                let bounds = aiScientist2025Bounds(from: records)
                requestedGoal = sampleGoal(bounds: bounds, rng: &rng)
                let bestIndex = aiScientist2025NearestGoalIndex(goal: requestedGoal!, records: records)
                state = aiScientist2025MutatedState(
                    base: records[bestIndex].state,
                    ranges: ranges,
                    experiment: experiment,
                    rng: &rng
                )
            }

            let achievedGoal = try aiScientist2025Evaluate(
                state: state,
                experiment: experiment,
                explorer: configs.explorer,
                baseData: baseData,
                runtime: runtime
            )
            let record = AIScientist2025GoalRecord(
                id: UUID(),
                experiment: experiment.name,
                iteration: iteration,
                requestedGoal: requestedGoal,
                achievedGoal: achievedGoal,
                state: state
            )
            records.append(record)
            try appendJSONLine(record, to: archiveHandle, encoder: lineEncoder)
        }

        let goals = records.map(\.achievedGoal)
        let summary = AIScientist2025ExperimentSummary(
            name: experiment.name,
            mode: experiment.mode,
            records: records.count,
            averagePairwiseDistance: aiScientist2025AveragePairwiseDistance(goals),
            coverage: aiScientist2025Coverage(goals: goals, binsPerDimension: configs.explorer.coverageBinsPerDimension),
            maxima: aiScientist2025Maxima(goals)
        )
        try encoder.encode(summary).write(to: outputDirectory.appendingPathComponent("summary.json"))
        logger.info("AI Scientist 2025: experiment=\(experiment.name) records=\(summary.records) coverage=\(summary.coverage)")
        return summary
    }
}

private func aiScientist2025RandomState(
    runtime: LeniaRuntimeConfig,
    ranges: KernelParamRanges,
    experiment: AIScientist2025ExperimentConfig,
    rng: inout SeededRandomNumberGenerator
) -> AIScientist2025ExperimentState {
    let paramsSeed = Int.random(in: 0...Int.max, using: &rng)
    let resolved = generateRandomParams(seed: paramsSeed, nbK: runtime.nbK, ranges: ranges)
    let probability = Float.random(in: experiment.mutationProbabilityRange[0]...experiment.mutationProbabilityRange[1], using: &rng)
    let patchSize = Int.random(in: experiment.beamPatchSizeRange[0]...experiment.beamPatchSizeRange[1], using: &rng)
    return AIScientist2025ExperimentState(
        params: resolved.toKernelParams(),
        mutationProbability: probability,
        beamPatchSize: patchSize,
        seed: Int.random(in: 0...Int.max, using: &rng)
    )
}

private func aiScientist2025MutatedState(
    base: AIScientist2025ExperimentState,
    ranges: KernelParamRanges,
    experiment: AIScientist2025ExperimentConfig,
    rng: inout SeededRandomNumberGenerator
) -> AIScientist2025ExperimentState {
    let params = mutateParams(base: base.params, ranges: ranges, config: experiment.parameterMutation, rng: &rng)
    let probWidth = experiment.mutationProbabilityRange[1] - experiment.mutationProbabilityRange[0]
    let prob = max(
        experiment.mutationProbabilityRange[0],
        min(
            experiment.mutationProbabilityRange[1],
            base.mutationProbability + gaussianSample(std: max(probWidth * experiment.parameterMutation.std, 1e-6), rng: &rng)
        )
    )
    let sizeWidth = Float(experiment.beamPatchSizeRange[1] - experiment.beamPatchSizeRange[0])
    let rawSize = Float(base.beamPatchSize) + gaussianSample(std: max(sizeWidth * experiment.parameterMutation.std, 1), rng: &rng)
    let patchSize = max(
        experiment.beamPatchSizeRange[0],
        min(experiment.beamPatchSizeRange[1], Int(rawSize.rounded()))
    )
    return AIScientist2025ExperimentState(
        params: params,
        mutationProbability: prob,
        beamPatchSize: patchSize,
        seed: Int.random(in: 0...Int.max, using: &rng)
    )
}

private func aiScientist2025Evaluate(
    state: AIScientist2025ExperimentState,
    experiment: AIScientist2025ExperimentConfig,
    explorer: AIScientist2025ExplorerConfig,
    baseData: Data,
    runtime baseRuntime: LeniaRuntimeConfig
) throws -> [Float] {
    let runtime = try loadRuntimeConfig(from: baseData, overrides: [
        "run.steps": explorer.totalSteps,
        "params.mode": "explicit",
        "params.r": state.params.r,
        "params.b": state.params.b,
        "params.w": state.params.w,
        "params.a": state.params.a,
        "params.m": state.params.m,
        "params.s": state.params.s,
        "params.h": state.params.h,
        "params.R": state.params.R,
        "beam_mutation.probability": state.mutationProbability,
        "beam_mutation.patch_size": state.beamPatchSize
    ])
    let evaluator = FlowLeniaSimulator(runtimeConfig: runtime)
    let initialState = flowLeniaBuildRandomPatchState(
        sx: runtime.sx,
        sy: runtime.sy,
        channels: runtime.channels,
        patchCount: experiment.initPatchCount,
        patchSize: experiment.initPatchSize,
        seed: state.seed,
        valueRange: runtime.aUniform,
        zoneOrigin: experiment.initZoneOrigin,
        zoneSize: experiment.initZoneSize
    )
    let initialParams = flowLeniaBuildRandomPatchParamsNormal(
        sx: runtime.sx,
        sy: runtime.sy,
        parameterCount: runtime.nbK,
        patchCount: experiment.initPatchCount,
        patchSize: experiment.initPatchSize,
        seed: state.seed + 10_000,
        mean: experiment.initParamMean,
        std: experiment.initParamStd,
        zoneOrigin: experiment.initZoneOrigin,
        zoneSize: experiment.initZoneSize
    )
    let initialFood: MLXArray?
    if let foodPatchCount = experiment.foodPatchCount,
       let foodPatchSize = experiment.foodPatchSize,
       let foodPatchValue = experiment.foodPatchValue {
        initialFood = flowLeniaBuildFoodField(
            sx: runtime.sx,
            sy: runtime.sy,
            patchCount: foodPatchCount,
            patchSize: foodPatchSize,
            seed: state.seed + 20_000,
            value: foodPatchValue
        )
    } else {
        initialFood = nil
    }

    let rollout = evaluator.rollout(
        initialState: initialState,
        initialParams: initialParams,
        initialFood: initialFood,
        config: FlowLeniaRolloutConfig(
            steps: explorer.totalSteps,
            recordEverySteps: explorer.frameStride,
            captureEverySteps: experiment.mode == "ecosystem" ? explorer.frameStride : nil,
            activityConfig: experiment.activity,
            foodSpawn: experiment.foodSpawn,
            dissipation: experiment.dissipation
        )
    )

    if experiment.mode == "movement" {
        return [rollout.finalCenterX, rollout.finalCenterY]
    }

    let ea: Float
    switch explorer.evolutionaryActivityMetric {
    case "non_neutral":
        ea = rollout.activitySummary?.ean.last ?? 0
    default:
        fatalError("Unsupported AI Scientist evolutionary activity metric.")
    }
    let mp4Bytes = try aiScientist2025MP4Size(frames: rollout.recordedFrames, framerate: explorer.mp4Framerate)
    let h3 = aiScientist2025MultiScaleEntropy(massMap: rollout.finalMassMap, width: rollout.width, height: rollout.height, exponent: 3)
    let h4 = aiScientist2025MultiScaleEntropy(massMap: rollout.finalMassMap, width: rollout.width, height: rollout.height, exponent: 4)
    let h5 = aiScientist2025MultiScaleEntropy(massMap: rollout.finalMassMap, width: rollout.width, height: rollout.height, exponent: 5)
    let h6 = aiScientist2025MultiScaleEntropy(massMap: rollout.finalMassMap, width: rollout.width, height: rollout.height, exponent: 6)
    let h7 = aiScientist2025MultiScaleEntropy(massMap: rollout.finalMassMap, width: rollout.width, height: rollout.height, exponent: 7)
    return [ea, Float(mp4Bytes), h3, h4, h5, h6, h7]
}

private func aiScientist2025Bounds(from records: [AIScientist2025GoalRecord]) -> [(min: Float, max: Float)] {
    guard let first = records.first else {
        return []
    }
    var mins = first.achievedGoal
    var maxs = first.achievedGoal
    for record in records.dropFirst() {
        for index in record.achievedGoal.indices {
            mins[index] = min(mins[index], record.achievedGoal[index])
            maxs[index] = max(maxs[index], record.achievedGoal[index])
        }
    }
    return zip(mins, maxs).map { (min: $0.0, max: $0.1) }
}

private func aiScientist2025NearestGoalIndex(goal: [Float], records: [AIScientist2025GoalRecord]) -> Int {
    var bestIndex = 0
    var bestDistance = Float.greatestFiniteMagnitude
    for (index, record) in records.enumerated() {
        let distance = sqrt(zip(goal, record.achievedGoal).reduce(Float(0)) { partial, pair in
            let diff = pair.0 - pair.1
            return partial + diff * diff
        })
        if distance < bestDistance {
            bestDistance = distance
            bestIndex = index
        }
    }
    return bestIndex
}

private func aiScientist2025AveragePairwiseDistance(_ goals: [[Float]]) -> Float {
    guard goals.count > 1 else { return 0 }
    var total: Double = 0
    var count = 0
    for lhs in 0..<goals.count {
        for rhs in (lhs + 1)..<goals.count {
            let distanceSquared = zip(goals[lhs], goals[rhs]).reduce(Double(0)) { partial, pair in
                let diff = Double(pair.0) - Double(pair.1)
                return partial + diff * diff
            }
            total += sqrt(distanceSquared)
            count += 1
        }
    }
    let average = total / Double(max(count, 1))
    if !average.isFinite {
        return Float.greatestFiniteMagnitude
    }
    return Float(min(average, Double(Float.greatestFiniteMagnitude)))
}

private func aiScientist2025Coverage(goals: [[Float]], binsPerDimension: Int) -> Int {
    guard !goals.isEmpty else { return 0 }
    let dims = goals[0].count
    var mins = Array(repeating: Float.greatestFiniteMagnitude, count: dims)
    var maxs = Array(repeating: -Float.greatestFiniteMagnitude, count: dims)
    for goal in goals {
        for index in 0..<dims {
            mins[index] = min(mins[index], goal[index])
            maxs[index] = max(maxs[index], goal[index])
        }
    }

    var occupied = Set<[Int]>()
    for goal in goals {
        var cell: [Int] = []
        for index in 0..<dims {
            let span = max(maxs[index] - mins[index], 1e-6)
            let normalized = (goal[index] - mins[index]) / span
            let bucket = min(max(Int(floor(normalized * Float(binsPerDimension))), 0), binsPerDimension - 1)
            cell.append(bucket)
        }
        occupied.insert(cell)
    }
    return occupied.count
}

private func aiScientist2025Maxima(_ goals: [[Float]]) -> [Float] {
    guard let first = goals.first else {
        return []
    }
    var maxima = first
    for goal in goals.dropFirst() {
        for index in goal.indices {
            maxima[index] = max(maxima[index], goal[index])
        }
    }
    return maxima
}


private func aiScientist2025MultiScaleEntropy(
    massMap: [Float],
    width: Int,
    height: Int,
    exponent: Int
) -> Float {
    let factor = 1 << exponent
    let outWidth = max(width / factor, 1)
    let outHeight = max(height / factor, 1)
    var downsampled = [Float](repeating: 0, count: outWidth * outHeight)
    let area = Float(factor * factor)
    for y in 0..<outHeight {
        for x in 0..<outWidth {
            var sum: Float = 0
            for dy in 0..<factor {
                for dx in 0..<factor {
                    let srcX = min(width - 1, x * factor + dx)
                    let srcY = min(height - 1, y * factor + dy)
                    sum += massMap[srcX * height + srcY]
                }
            }
            downsampled[y * outWidth + x] = sum / area
        }
    }
    let total = max(downsampled.reduce(0, +), 1e-8)
    var entropy: Float = 0
    for value in downsampled {
        let probability = value / total
        if probability > 0 {
            entropy -= probability * log(probability)
        }
    }
    return entropy
}

private func aiScientist2025MP4Size(frames: [LeniaTrajectoryFrame], framerate: Int) throws -> Int {
    guard !frames.isEmpty else {
        return 0
    }
    guard let ffmpeg = ProcessInfo.processInfo.environment["PATH"]?
        .split(separator: ":")
        .map(String.init)
        .map({ URL(fileURLWithPath: $0).appendingPathComponent("ffmpeg").path })
        .first(where: { FileManager.default.isExecutableFile(atPath: $0) }) else {
        throw ConfigError.invalidConfig("ffmpeg must be available on PATH for ai-scientist-2025 MP4 metrics.")
    }

    let tempDirectory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
    try FileManager.default.createDirectory(at: tempDirectory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: tempDirectory) }

    for (index, frame) in frames.enumerated() {
        let pngURL = tempDirectory.appendingPathComponent(String(format: "frame_%05d.png", index))
        try writeGrayscalePNG(bytes: frame.bytes, width: frame.width, height: frame.height, to: pngURL)
    }

    let outputURL = tempDirectory.appendingPathComponent("out.mp4")
    let process = Process()
    process.executableURL = URL(fileURLWithPath: ffmpeg)
    process.arguments = [
        "-y",
        "-framerate", String(framerate),
        "-i", tempDirectory.appendingPathComponent("frame_%05d.png").path,
        "-pix_fmt", "yuv420p",
        outputURL.path
    ]
    let stderrPipe = Pipe()
    process.standardError = stderrPipe
    try process.run()
    process.waitUntilExit()
    guard process.terminationStatus == 0 else {
        let error = String(data: stderrPipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        throw ConfigError.invalidConfig("ffmpeg failed while computing ai-scientist-2025 MP4 size: \(error)")
    }
    let attributes = try FileManager.default.attributesOfItem(atPath: outputURL.path)
    return attributes[.size] as? Int ?? 0
}
