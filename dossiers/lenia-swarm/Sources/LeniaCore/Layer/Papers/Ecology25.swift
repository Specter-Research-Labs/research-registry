import Foundation
import Logging
import MLX

public struct FlowLeniaEcology2025SimulationConfig: Codable, Sendable {
    public let paper: String
    public let gridSize: Int
    public let totalSteps: Int
    public let recordEverySteps: Int
    public let captureEverySteps: Int?
    public let channels: Int
    public let kernelsPerChannelPair: Int
    public let repeats: Int
    public let mutationProbabilities: [Float]
    public let variants: [String]
    public let activity: ActivityConfig

    enum CodingKeys: String, CodingKey {
        case paper
        case gridSize = "grid_size"
        case totalSteps = "total_steps"
        case recordEverySteps = "record_every_steps"
        case captureEverySteps = "capture_every_steps"
        case channels
        case kernelsPerChannelPair = "kernels_per_channel_pair"
        case repeats
        case mutationProbabilities = "mutation_probabilities"
        case variants
        case activity
    }

    public init(
        paper: String,
        gridSize: Int,
        totalSteps: Int,
        recordEverySteps: Int,
        captureEverySteps: Int? = nil,
        channels: Int,
        kernelsPerChannelPair: Int,
        repeats: Int,
        mutationProbabilities: [Float],
        variants: [String],
        activity: ActivityConfig
    ) {
        self.paper = paper
        self.gridSize = gridSize
        self.totalSteps = totalSteps
        self.recordEverySteps = recordEverySteps
        self.captureEverySteps = captureEverySteps
        self.channels = channels
        self.kernelsPerChannelPair = kernelsPerChannelPair
        self.repeats = repeats
        self.mutationProbabilities = mutationProbabilities
        self.variants = variants
        self.activity = activity
    }
}

public struct FlowLeniaEcology2025VariantConfig: Codable, Sendable {
    public let name: String
    public let baseConfig: String
    public let initPatchCount: Int
    public let initPatchSize: Int
    public let initParamMean: Float
    public let initParamStd: Float
    public let foodPatchCount: Int?
    public let foodPatchSize: Int?
    public let foodPatchValue: Float?
    public let foodSpawn: FlowLeniaFoodSpawnConfig?
    public let dissipation: FlowLeniaDissipationConfig?

    enum CodingKeys: String, CodingKey {
        case name
        case baseConfig = "base_config"
        case initPatchCount = "init_patch_count"
        case initPatchSize = "init_patch_size"
        case initParamMean = "init_param_mean"
        case initParamStd = "init_param_std"
        case foodPatchCount = "food_patch_count"
        case foodPatchSize = "food_patch_size"
        case foodPatchValue = "food_patch_value"
        case foodSpawn = "food_spawn"
        case dissipation
    }
}

public struct FlowLeniaEcology2025ConfigBundle: Sendable {
    public let configDirectory: URL
    public let simulation: FlowLeniaEcology2025SimulationConfig
    public let variants: [FlowLeniaEcology2025VariantConfig]
}

public struct FlowLeniaEcology2025FrameMetrics: Codable, Sendable {
    public let step: Int
    public let speciesCount: Int
    public let diversity: Float
    public let presenceActivity: Float
    public let countActivity: Float
    public let nonNeutralActivity: Float

    enum CodingKeys: String, CodingKey {
        case step
        case speciesCount = "species_count"
        case diversity
        case presenceActivity = "presence_activity"
        case countActivity = "count_activity"
        case nonNeutralActivity = "non_neutral_activity"
    }
}

public struct FlowLeniaEcology2025RunSummary: Codable, Sendable {
    public let variant: String
    public let mutationProbability: Float
    public let repeatIndex: Int
    public let frames: Int
    public let finalSpeciesCount: Int
    public let finalDiversity: Float
    public let finalPresenceActivity: Float
    public let finalCountActivity: Float
    public let finalNonNeutralActivity: Float
    public let finalMass: Float

    enum CodingKeys: String, CodingKey {
        case variant
        case mutationProbability = "mutation_probability"
        case repeatIndex = "repeat_index"
        case frames
        case finalSpeciesCount = "final_species_count"
        case finalDiversity = "final_diversity"
        case finalPresenceActivity = "final_presence_activity"
        case finalCountActivity = "final_count_activity"
        case finalNonNeutralActivity = "final_non_neutral_activity"
        case finalMass = "final_mass"
    }
}

public struct FlowLeniaEcology2025Summary: Codable, Sendable {
    public let paper: String
    public let totalRuns: Int
    public let runs: [FlowLeniaEcology2025RunSummary]

    enum CodingKeys: String, CodingKey {
        case paper
        case totalRuns = "total_runs"
        case runs
    }
}

public struct FlowLeniaEcology2025SeedProvenance: Codable, Sendable {
    public let sourceID: String
    public let name: String
    public let runID: String?
    public let campaignID: String?
    public let recordedAt: Date?
    public let score: Float?

    public init(
        sourceID: String,
        name: String,
        runID: String?,
        campaignID: String?,
        recordedAt: Date?,
        score: Float?
    ) {
        self.sourceID = sourceID
        self.name = name
        self.runID = runID
        self.campaignID = campaignID
        self.recordedAt = recordedAt
        self.score = score
    }
}

public struct FlowLeniaEcology2025ReplayPayload: Codable, Sendable {
    public let paper: String
    public let variant: FlowLeniaEcology2025VariantConfig
    public let mutationProbability: Float
    public let repeatIndex: Int
    public let totalSteps: Int
    public let recordEverySteps: Int
    public let activity: ActivityConfig
    public let initialState: InitStatePatchConfig
    public let initialParams: InitStatePatchConfig
    public let initialFood: InitStatePatchConfig?
    public let curatedSeeds: [FlowLeniaEcology2025SeedProvenance]

    enum CodingKeys: String, CodingKey {
        case paper
        case variant
        case mutationProbability = "mutation_probability"
        case repeatIndex = "repeat_index"
        case totalSteps = "total_steps"
        case recordEverySteps = "record_every_steps"
        case activity
        case initialState = "initial_state"
        case initialParams = "initial_params"
        case initialFood = "initial_food"
        case curatedSeeds = "curated_seeds"
    }
}

public struct FlowLeniaEcology2025RunMetadata: Codable, Sendable {
    public let runID: String
    public let campaignID: String?
    public let bundleKind: LeniaArtifactBundleKind
    public let runSummary: FlowLeniaEcology2025RunSummary
    public let exportedAt: Date

    enum CodingKeys: String, CodingKey {
        case runID = "run_id"
        case campaignID = "campaign_id"
        case bundleKind = "bundle_kind"
        case runSummary = "run_summary"
        case exportedAt = "exported_at"
    }
}

public struct FlowLeniaEcology2025RunRecord: Codable, Sendable {
    public let trialID: String
    public let runID: String
    public let campaignID: String?
    public let bundleKind: LeniaArtifactBundleKind
    public let variant: String
    public let mutationProbability: Float
    public let repeatIndex: Int
    public let bundleDir: String
    public let baseConfigPath: String
    public let payloadPath: String
    public let metadataPath: String
    public let summaryPath: String
    public let framesPath: String
    public let trajectoryFramesPath: String?
    public let activitySummaryPath: String?
    public let exportedAt: Date

    enum CodingKeys: String, CodingKey {
        case trialID = "trial_id"
        case runID = "run_id"
        case campaignID = "campaign_id"
        case bundleKind = "bundle_kind"
        case variant
        case mutationProbability = "mutation_probability"
        case repeatIndex = "repeat_index"
        case bundleDir = "bundle_dir"
        case baseConfigPath = "base_config_path"
        case payloadPath = "payload_path"
        case metadataPath = "metadata_path"
        case summaryPath = "summary_path"
        case framesPath = "frames_path"
        case trajectoryFramesPath = "trajectory_frames_path"
        case activitySummaryPath = "activity_summary_path"
        case exportedAt = "exported_at"
    }
}

public struct FlowLeniaEcology2025TrialResult: Sendable {
    public let runSummary: FlowLeniaEcology2025RunSummary
    public let frameMetrics: [FlowLeniaEcology2025FrameMetrics]
    public let trajectoryFrames: [LeniaTrajectoryFrame]
    public let activitySummary: ActivitySummary?
    public let replayBaseConfig: LeniaBaseConfig
    public let replayPayload: FlowLeniaEcology2025ReplayPayload
}

public struct FlowLeniaEcology2025RuntimeOverrides: Sendable {
    public let backend: String?
    public let border: String?
    public let parameterMix: String?
    public let parameterMixSeed: Int?
    public let clearsParameterMixSeed: Bool

    public init(
        backend: String? = nil,
        border: String? = nil,
        parameterMix: String? = nil,
        parameterMixSeed: Int? = nil,
        clearsParameterMixSeed: Bool = false
    ) {
        self.backend = backend
        self.border = border
        self.parameterMix = parameterMix
        self.parameterMixSeed = parameterMixSeed
        self.clearsParameterMixSeed = clearsParameterMixSeed
    }

    public var isEmpty: Bool {
        backend == nil && border == nil && parameterMix == nil && parameterMixSeed == nil && !clearsParameterMixSeed
    }

    public func runtimeConfigOverrides() -> [String: Any] {
        var overrides: [String: Any] = [:]
        if let backend {
            overrides["backend"] = backend
        }
        if let border {
            overrides["reintegration.border"] = border
        }
        if let parameterMix {
            overrides["parameter_embedding.mix"] = parameterMix
        }
        if clearsParameterMixSeed {
            overrides["parameter_embedding.mix_seed"] = NSNull()
        }
        if let parameterMixSeed {
            overrides["parameter_embedding.mix_seed"] = parameterMixSeed
        }
        return overrides
    }
}

public func loadFlowLeniaEcology2025ConfigBundle(
    configDirectory: URL,
    strictPaperInvariants: Bool = true
) throws -> FlowLeniaEcology2025ConfigBundle {
    let decoder = JSONDecoder()
    let simulation = try decoder.decode(
        FlowLeniaEcology2025SimulationConfig.self,
        from: Data(contentsOf: configDirectory.appendingPathComponent("simulation.json"))
    )
    var variants: [FlowLeniaEcology2025VariantConfig] = []
    for variantName in simulation.variants {
        let variant = try decoder.decode(
            FlowLeniaEcology2025VariantConfig.self,
            from: Data(contentsOf: configDirectory.appendingPathComponent("\(variantName).json"))
        )
        variants.append(variant)
    }
    try validateFlowLeniaEcology2025Bundle(
        simulation: simulation,
        variants: variants,
        configDirectory: configDirectory,
        strictPaperInvariants: strictPaperInvariants
    )
    return FlowLeniaEcology2025ConfigBundle(
        configDirectory: configDirectory,
        simulation: simulation,
        variants: variants
    )
}

public func validateFlowLeniaEcology2025RuntimeOverrides(
    bundle: FlowLeniaEcology2025ConfigBundle,
    runtimeOverrides: FlowLeniaEcology2025RuntimeOverrides
) throws {
    let overrides = runtimeOverrides.runtimeConfigOverrides()
    for variant in bundle.variants {
        let baseURL = bundle.configDirectory.appendingPathComponent(variant.baseConfig)
        let baseData = try Data(contentsOf: baseURL)
        let runtime = try loadRuntimeConfig(from: baseData, overrides: overrides)
        _ = FlowLeniaSimulator(runtimeConfig: runtime)
    }
}

private func validateFlowLeniaEcology2025Bundle(
    simulation: FlowLeniaEcology2025SimulationConfig,
    variants: [FlowLeniaEcology2025VariantConfig],
    configDirectory: URL,
    strictPaperInvariants: Bool
) throws {
    guard simulation.paper == "flow-lenia-emergent-evolutionary-dynamics-2025" else {
        throw ConfigError.invalidConfig("flowlenia-ecology-2025 simulation.paper must match the 2025 ecology paper identifier.")
    }
    guard simulation.activity.enabled else {
        throw ConfigError.invalidConfig("flowlenia-ecology-2025 activity.enabled must be true.")
    }
    if strictPaperInvariants {
        guard simulation.channels == 3 else {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 channels must be 3.")
        }
        guard simulation.kernelsPerChannelPair == 5 else {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 kernels_per_channel_pair must be 5.")
        }
        guard simulation.totalSteps == 500_000 else {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 total_steps must be 500000.")
        }
        guard simulation.recordEverySteps == 100 else {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 record_every_steps must be 100.")
        }
        guard simulation.repeats == 5 else {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 repeats must be 5.")
        }
        guard simulation.mutationProbabilities == [0.001, 0.01, 0.1, 0.5, 1.0] else {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 mutation_probabilities must match the paper sweep [0.001, 0.01, 0.1, 0.5, 1.0].")
        }
    } else {
        guard simulation.totalSteps > 0 else {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 total_steps must be > 0.")
        }
        guard simulation.recordEverySteps > 0 else {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 record_every_steps must be > 0.")
        }
        guard simulation.repeats > 0 else {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 repeats must be > 0.")
        }
        guard !simulation.mutationProbabilities.isEmpty else {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 mutation_probabilities must be non-empty.")
        }
        guard simulation.channels > 0 else {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 channels must be > 0.")
        }
        guard simulation.kernelsPerChannelPair > 0 else {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 kernels_per_channel_pair must be > 0.")
        }
    }
    guard !variants.isEmpty else {
        throw ConfigError.invalidConfig("flowlenia-ecology-2025 requires at least one variant.")
    }

    for variant in variants {
        guard variant.name == "vanilla" || variant.name == "dissipative" || variant.name == "food" else {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 variant.name must be one of vanilla|dissipative|food.")
        }
        guard variant.initPatchCount > 0, variant.initPatchSize > 0 else {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 variant init_patch_count and init_patch_size must be > 0.")
        }
        guard variant.initParamStd > 0 else {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 init_param_std must be > 0.")
        }
        let baseURL = configDirectory.appendingPathComponent(variant.baseConfig)
        guard FileManager.default.fileExists(atPath: baseURL.path) else {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 base config is missing at \(baseURL.path).")
        }
        let runtime = try loadRuntimeConfig(from: Data(contentsOf: baseURL))
        guard runtime.sx == simulation.gridSize, runtime.sy == simulation.gridSize else {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 base config grid must match simulation.grid_size.")
        }
        guard runtime.channels == simulation.channels else {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 base config channels must match simulation.channels.")
        }
        if strictPaperInvariants {
            guard runtime.nbK == simulation.channels * simulation.channels * simulation.kernelsPerChannelPair else {
                throw ConfigError.invalidConfig("flowlenia-ecology-2025 base config must encode 45 kernels.")
            }
        } else {
            guard runtime.nbK > 0 else {
                throw ConfigError.invalidConfig("flowlenia-ecology-2025 base config must encode at least one kernel.")
            }
        }
        guard runtime.parameterEmbedding.enabled else {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 base configs require parameter_embedding.enabled=true.")
        }
        if variant.name == "food" {
            guard runtime.food?.enabled == true else {
                throw ConfigError.invalidConfig("flowlenia-ecology-2025 food variant requires food.enabled=true in its base config.")
            }
            guard variant.foodPatchCount != nil,
                  variant.foodPatchSize != nil,
                  variant.foodPatchValue != nil else {
                throw ConfigError.invalidConfig("flowlenia-ecology-2025 food variant requires food_patch_count, food_patch_size, and food_patch_value.")
            }
        }
        if variant.name == "dissipative" {
            guard variant.dissipation != nil else {
                throw ConfigError.invalidConfig("flowlenia-ecology-2025 dissipative variant requires dissipation config.")
            }
        }
    }
}

public final class FlowLeniaEcology2025Runner {
    private let configs: FlowLeniaEcology2025ConfigBundle
    private let logger: Logger
    private let encoder: JSONEncoder
    private let curatedSeeds: [ResearchSeedPatch]
    private let runtimeOverrides: FlowLeniaEcology2025RuntimeOverrides

    public init(
        configs: FlowLeniaEcology2025ConfigBundle,
        logger: Logger,
        curatedSeeds: [ResearchSeedPatch] = [],
        runtimeOverrides: FlowLeniaEcology2025RuntimeOverrides = FlowLeniaEcology2025RuntimeOverrides()
    ) {
        self.configs = configs
        self.logger = logger
        self.curatedSeeds = curatedSeeds
        self.runtimeOverrides = runtimeOverrides
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        self.encoder = encoder
    }

    public func writeResolvedConfigs(to outputDirectory: URL) throws {
        try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
        try encoder.encode(configs.simulation).write(to: outputDirectory.appendingPathComponent("simulation.json"))
        for variant in configs.variants {
            try encoder.encode(variant).write(to: outputDirectory.appendingPathComponent("\(variant.name).json"))
        }
    }

    public func run(outputDirectory: URL) throws -> FlowLeniaEcology2025Summary {
        try writeResolvedConfigs(to: outputDirectory)
        var summaries: [FlowLeniaEcology2025RunSummary] = []
        var runRecords: [FlowLeniaEcology2025RunRecord] = []

        for variant in configs.variants {
            let baseURL = configs.configDirectory.appendingPathComponent(variant.baseConfig)
            let baseData = try Data(contentsOf: baseURL)
            for mutationProbability in configs.simulation.mutationProbabilities {
                for repeatIndex in 0..<configs.simulation.repeats {
                    let runDirectory = outputDirectory
                        .appendingPathComponent("runs", isDirectory: true)
                        .appendingPathComponent(variant.name, isDirectory: true)
                        .appendingPathComponent("pmut=\(flowLeniaFloatLabel(mutationProbability))", isDirectory: true)
                        .appendingPathComponent("repeat=\(repeatIndex)", isDirectory: true)
                    try FileManager.default.createDirectory(at: runDirectory, withIntermediateDirectories: true)
                    logger.info("Flow-Lenia Ecology 2025 starting variant=\(variant.name) pmut=\(mutationProbability) repeat=\(repeatIndex)")
                    let trial = try runFlowLeniaEcology2025Trial(
                        simulation: configs.simulation,
                        variant: variant,
                        baseConfigData: baseData,
                        mutationProbability: mutationProbability,
                        repeatIndex: repeatIndex,
                        curatedSeeds: curatedSeeds,
                        runtimeOverrides: runtimeOverrides,
                        logger: logger
                    )

                    try writeFlowLeniaEcologyFrames(trial.frameMetrics, to: runDirectory.appendingPathComponent("frames.jsonl"))
                    try encoder.encode(trial.runSummary).write(to: runDirectory.appendingPathComponent("summary.json"))
                    if let activitySummary = trial.activitySummary {
                        try encoder.encode(activitySummary).write(to: runDirectory.appendingPathComponent("activity-summary.json"))
                    }
                    runRecords.append(try writeFlowLeniaEcology2025RunArtifacts(
                        runDirectory: runDirectory,
                        runID: flowLeniaEcology2025TrialID(trial.runSummary),
                        campaignID: nil,
                        replayBaseConfig: trial.replayBaseConfig,
                        replayPayload: trial.replayPayload,
                        runSummary: trial.runSummary,
                        trajectoryFrames: trial.trajectoryFrames,
                        activitySummary: trial.activitySummary,
                        exportedAt: Date(),
                        encoder: encoder
                    ))
                    summaries.append(trial.runSummary)
                    logger.info("Flow-Lenia Ecology 2025: variant=\(variant.name) pmut=\(mutationProbability) repeat=\(repeatIndex) EA_N=\(trial.runSummary.finalNonNeutralActivity)")
                }
            }
        }

        let summary = FlowLeniaEcology2025Summary(
            paper: configs.simulation.paper,
            totalRuns: summaries.count,
            runs: summaries
        )
        try encoder.encode(summary).write(to: outputDirectory.appendingPathComponent("summary.json"))
        try writeFlowLeniaEcology2025RunIndex(
            records: runRecords,
            to: outputDirectory.appendingPathComponent("ecology-runs/index.jsonl")
        )
        return summary
    }
}

public func runFlowLeniaEcology2025Trial(
    simulation: FlowLeniaEcology2025SimulationConfig,
    variant: FlowLeniaEcology2025VariantConfig,
    baseConfigData: Data,
    mutationProbability: Float,
    repeatIndex: Int,
    curatedSeeds: [ResearchSeedPatch],
    runtimeOverrides: FlowLeniaEcology2025RuntimeOverrides = FlowLeniaEcology2025RuntimeOverrides(),
    logger: Logger
) throws -> FlowLeniaEcology2025TrialResult {
    let overrides = runtimeOverrides.runtimeConfigOverrides().merging([
        "run.steps": simulation.totalSteps,
        "beam_mutation.probability": mutationProbability
    ]) { _, trialValue in trialValue }
    let replayBaseConfig = try flowLeniaEcology2025ResolvedBaseConfig(
        from: baseConfigData,
        overrides: overrides
    )
    let runtime = try loadRuntimeConfig(from: baseConfigData, overrides: overrides)
    let evaluator = FlowLeniaSimulator(runtimeConfig: runtime)
    logger.info(
        "Flow-Lenia Ecology 2025 runtime backend=\(runtime.backend.rawValue) parameter_mix=\(runtime.parameterEmbedding.mix)"
    )
    let parameterFieldStyle = flowLeniaEcology2025ParameterFieldStyle(runtime: runtime, curatedSeeds: curatedSeeds)
    let parameterCount = flowLeniaEcology2025RuntimeParameterCount(runtime: runtime, style: parameterFieldStyle)
    let initialState: MLXArray
    let initialParams: MLXArray
    if curatedSeeds.isEmpty {
        initialState = flowLeniaBuildRandomPatchState(
            sx: runtime.sx,
            sy: runtime.sy,
            channels: runtime.channels,
            patchCount: variant.initPatchCount,
            patchSize: variant.initPatchSize,
            seed: runtime.initSeed + repeatIndex,
            valueRange: runtime.aUniform
        )
        initialParams = flowLeniaBuildRandomPatchParamsNormal(
            sx: runtime.sx,
            sy: runtime.sy,
            parameterCount: parameterCount,
            patchCount: variant.initPatchCount,
            patchSize: variant.initPatchSize,
            seed: runtime.initSeed + 10_000 + repeatIndex,
            mean: variant.initParamMean,
            std: variant.initParamStd
        )
    } else {
        let seededFields = try flowLeniaEcology2025CuratedSeedFields(
            seeds: curatedSeeds,
            sx: runtime.sx,
            sy: runtime.sy,
            channels: runtime.channels,
            parameterCount: parameterCount,
            parameterFieldStyle: parameterFieldStyle,
            runtimeSources: runtime.c0,
            runtimeTargets: flowLeniaEcology2025KernelTargets(runtime.c1, parameterCount: runtime.nbK),
            backgroundEmbeddedParams: flowLeniaEcology2025BackgroundEmbeddedParams(runtime: runtime, style: parameterFieldStyle),
            reservedFoodChannel: runtime.food?.enabled == true ? runtime.food?.channel_index : nil,
            seed: runtime.initSeed + repeatIndex
        )
        initialState = seededFields.state
        initialParams = seededFields.params
    }
    let initialFood: MLXArray?
    if variant.name == "food" {
        initialFood = flowLeniaBuildFoodField(
            sx: runtime.sx,
            sy: runtime.sy,
            patchCount: variant.foodPatchCount!,
            patchSize: variant.foodPatchSize!,
            seed: runtime.initSeed + 20_000 + repeatIndex,
            value: variant.foodPatchValue!
        )
    } else {
        initialFood = nil
    }
    let replayPayload = FlowLeniaEcology2025ReplayPayload(
        paper: simulation.paper,
        variant: variant,
        mutationProbability: mutationProbability,
        repeatIndex: repeatIndex,
        totalSteps: simulation.totalSteps,
        recordEverySteps: simulation.recordEverySteps,
        activity: simulation.activity,
        initialState: flowLeniaEcology2025StatePatch(
            from: initialState,
            width: runtime.sx,
            height: runtime.sy,
            channels: runtime.channels
        ),
        initialParams: flowLeniaEcology2025StatePatch(
            from: initialParams,
            width: runtime.sx,
            height: runtime.sy,
            channels: parameterCount
        ),
        initialFood: initialFood.map {
            flowLeniaEcology2025StatePatch(
                from: $0,
                width: runtime.sx,
                height: runtime.sy,
                channels: 1
            )
        },
        curatedSeeds: curatedSeeds.map {
            FlowLeniaEcology2025SeedProvenance(
                sourceID: $0.sourceID,
                name: $0.name,
                runID: $0.runID,
                campaignID: $0.campaignID,
                recordedAt: $0.recordedAt,
                score: $0.score
            )
        }
    )

    let rollout = evaluator.rollout(
        initialState: initialState,
        initialParams: initialParams,
        initialFood: initialFood,
        config: FlowLeniaRolloutConfig(
            steps: simulation.totalSteps,
            recordEverySteps: simulation.recordEverySteps,
            captureEverySteps: simulation.captureEverySteps,
            activityConfig: simulation.activity,
            foodSpawn: variant.foodSpawn,
            dissipation: variant.dissipation,
            logger: logger
        )
    )

    let frameMetrics = flowLeniaEcology2025FrameMetrics(from: rollout.activitySummary)
    let runSummary = FlowLeniaEcology2025RunSummary(
        variant: variant.name,
        mutationProbability: mutationProbability,
        repeatIndex: repeatIndex,
        frames: frameMetrics.count,
        finalSpeciesCount: frameMetrics.last?.speciesCount ?? 0,
        finalDiversity: frameMetrics.last?.diversity ?? 0,
        finalPresenceActivity: frameMetrics.last?.presenceActivity ?? 0,
        finalCountActivity: frameMetrics.last?.countActivity ?? 0,
        finalNonNeutralActivity: frameMetrics.last?.nonNeutralActivity ?? 0,
        finalMass: rollout.finalMass
    )
    return FlowLeniaEcology2025TrialResult(
        runSummary: runSummary,
        frameMetrics: frameMetrics,
        trajectoryFrames: rollout.recordedFrames,
        activitySummary: rollout.activitySummary,
        replayBaseConfig: replayBaseConfig,
        replayPayload: replayPayload
    )
}

public func replayFlowLeniaEcology2025Payload(
    baseConfig: LeniaBaseConfig,
    payload: FlowLeniaEcology2025ReplayPayload,
    logger: Logger
) throws -> FlowLeniaEcology2025TrialResult {
    let runtime = try loadRuntimeConfig(from: JSONEncoder().encode(baseConfig))
    let evaluator = FlowLeniaSimulator(runtimeConfig: runtime)
    let initialState = try flowLeniaEcology2025WorldArray(
        from: payload.initialState,
        sx: runtime.sx,
        sy: runtime.sy,
        channels: runtime.channels,
        label: "initial_state"
    )
    let initialParams = try flowLeniaEcology2025WorldArray(
        from: payload.initialParams,
        sx: runtime.sx,
        sy: runtime.sy,
        channels: payload.initialParams.channels,
        label: "initial_params"
    )
    let initialFood = try payload.initialFood.map {
        try flowLeniaEcology2025ScalarField(
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
            captureEverySteps: nil,
            activityConfig: payload.activity,
            foodSpawn: payload.variant.foodSpawn,
            dissipation: payload.variant.dissipation,
            logger: logger
        )
    )

    let frameMetrics = flowLeniaEcology2025FrameMetrics(from: rollout.activitySummary)
    let runSummary = FlowLeniaEcology2025RunSummary(
        variant: payload.variant.name,
        mutationProbability: payload.mutationProbability,
        repeatIndex: payload.repeatIndex,
        frames: frameMetrics.count,
        finalSpeciesCount: frameMetrics.last?.speciesCount ?? 0,
        finalDiversity: frameMetrics.last?.diversity ?? 0,
        finalPresenceActivity: frameMetrics.last?.presenceActivity ?? 0,
        finalCountActivity: frameMetrics.last?.countActivity ?? 0,
        finalNonNeutralActivity: frameMetrics.last?.nonNeutralActivity ?? 0,
        finalMass: rollout.finalMass
    )
    return FlowLeniaEcology2025TrialResult(
        runSummary: runSummary,
        frameMetrics: frameMetrics,
        trajectoryFrames: rollout.recordedFrames,
        activitySummary: rollout.activitySummary,
        replayBaseConfig: baseConfig,
        replayPayload: payload
    )
}

private func flowLeniaEcology2025CuratedSeedFields(
    seeds: [ResearchSeedPatch],
    sx: Int,
    sy: Int,
    channels: Int,
    parameterCount: Int,
    parameterFieldStyle: FlowLeniaEcology2025ParameterFieldStyle,
    runtimeSources: [Int],
    runtimeTargets: [Int],
    backgroundEmbeddedParams: [Float],
    reservedFoodChannel: Int?,
    seed: Int
) throws -> (state: MLXArray, params: MLXArray) {
    guard !seeds.isEmpty else {
        throw ConfigError.invalidConfig("flowlenia-ecology-2025 curated seed state requires at least one seed.")
    }
    var world = [Float](repeating: 0, count: sx * sy * channels)
    guard backgroundEmbeddedParams.count == parameterCount else {
        throw ConfigError.invalidConfig("flowlenia-ecology-2025 background embedded parameter count \(backgroundEmbeddedParams.count) does not match expected \(parameterCount).")
    }
    var params = [Float](repeating: 0, count: sx * sy * parameterCount)
    for x in 0..<sx {
        for y in 0..<sy {
            let paramBase = (x * sy + y) * parameterCount
            for parameterIndex in 0..<parameterCount {
                params[paramBase + parameterIndex] = backgroundEmbeddedParams[parameterIndex]
            }
        }
    }
    let placements = try flowLeniaEcology2025CuratedSeedPlacements(seeds: seeds, sx: sx, sy: sy, seed: seed)
    for (patch, placement) in zip(seeds, placements) {
        guard patch.world.channels <= channels else {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 curated seed channels \(patch.world.channels) exceed runtime channels \(channels).")
        }
        guard patch.world.width <= sx, patch.world.height <= sy else {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 curated seed patch \(patch.world.width)x\(patch.world.height) exceeds runtime grid \(sx)x\(sy).")
        }
        if let reservedFoodChannel,
           reservedFoodChannel < patch.world.channels,
           flowLeniaEcology2025SeedOccupiesChannel(patch, channel: reservedFoodChannel) {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 curated seed '\(patch.sourceID)' occupies runtime food channel \(reservedFoodChannel); use a separate food channel or remap the seed channels.")
        }
        let seedWeights: [Float]
        if patch.kernelParams == nil {
            seedWeights = backgroundEmbeddedParams
        } else if let embedded = flowLeniaEcology2025SeedEmbeddedParameters(
            patch: patch,
            parameterFieldStyle: parameterFieldStyle,
            kernelCount: flowLeniaEcology2025KernelCount(parameterCount: parameterCount, style: parameterFieldStyle),
            runtimeSources: runtimeSources,
            runtimeTargets: runtimeTargets
        ) {
            seedWeights = embedded
        } else {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 curated seed '\(patch.sourceID)' does not provide kernel parameters compatible with the runtime kernel routes.")
        }
        for x in 0..<patch.world.width {
            for y in 0..<patch.world.height {
                let sourceBase = ((x * patch.world.height) + y) * patch.world.channels
                var mass: Float = 0
                for channel in 0..<channels {
                    let value = channel < patch.world.channels ? patch.world.values[sourceBase + channel] : 0
                    let targetIndex = ((placement.x + x) * sy + (placement.y + y)) * channels + channel
                    world[targetIndex] = max(world[targetIndex], value)
                    mass += value
                }
                if mass > 1e-6 {
                    let paramBase = ((placement.x + x) * sy + (placement.y + y)) * parameterCount
                    for parameterIndex in 0..<parameterCount {
                        params[paramBase + parameterIndex] = seedWeights[parameterIndex]
                    }
                }
            }
        }
    }
    return (
        MLXArray(world).reshaped([sx, sy, channels]),
        MLXArray(params).reshaped([sx, sy, parameterCount])
    )
}

private func flowLeniaEcology2025SeedOccupiesChannel(_ patch: ResearchSeedPatch, channel: Int) -> Bool {
    guard channel >= 0, channel < patch.world.channels else {
        return false
    }
    for x in 0..<patch.world.width {
        for y in 0..<patch.world.height {
            let index = ((x * patch.world.height) + y) * patch.world.channels + channel
            if patch.world.values[index] > 1e-6 {
                return true
            }
        }
    }
    return false
}

private typealias FlowLeniaEcology2025ParameterFieldStyle = FlowLeniaParameterFieldMode

private func flowLeniaEcology2025ParameterFieldStyle(
    runtime: LeniaRuntimeConfig,
    curatedSeeds: [ResearchSeedPatch]
) -> FlowLeniaEcology2025ParameterFieldStyle {
    guard !curatedSeeds.isEmpty, runtime.parameterEmbedding.enabled else {
        return .kernelGain
    }
    return .localizedGrowthParameters
}

private func flowLeniaEcology2025KernelCount(
    parameterCount: Int,
    style: FlowLeniaEcology2025ParameterFieldStyle
) -> Int {
    switch style {
    case .none:
        return 0
    case .kernelGain:
        return parameterCount
    case .localizedGrowthParameters:
        return parameterCount / 3
    }
}

private func flowLeniaEcology2025RuntimeParameterCount(
    runtime: LeniaRuntimeConfig,
    style: FlowLeniaEcology2025ParameterFieldStyle
) -> Int {
    switch style {
    case .none:
        return 0
    case .kernelGain:
        return runtime.nbK
    case .localizedGrowthParameters:
        return runtime.nbK * 3
    }
}

private func flowLeniaEcology2025BackgroundEmbeddedParams(
    runtime: LeniaRuntimeConfig,
    style: FlowLeniaEcology2025ParameterFieldStyle
) -> [Float] {
    switch style {
    case .none:
        return []
    case .kernelGain:
        return [Float](repeating: 0, count: runtime.nbK)
    case .localizedGrowthParameters:
        return runtime.params.m + runtime.params.s + [Float](repeating: 0, count: runtime.nbK)
    }
}

private func flowLeniaEcology2025CuratedSeedPlacements(
    seeds: [ResearchSeedPatch],
    sx: Int,
    sy: Int,
    seed: Int
) throws -> [(x: Int, y: Int)] {
    let count = seeds.count
    let columns = max(1, Int(ceil(sqrt(Double(count)))))
    let rows = max(1, Int(ceil(Double(count) / Double(columns))))
    let cellWidth = max(1, sx / columns)
    let cellHeight = max(1, sy / rows)
    var rng = SeededRandomNumberGenerator(seed: UInt64(max(seed, 0)))
    return try seeds.enumerated().map { index, patch in
        guard patch.world.width <= sx, patch.world.height <= sy else {
            throw ConfigError.invalidConfig("flowlenia-ecology-2025 curated seed patch \(patch.world.width)x\(patch.world.height) exceeds runtime grid \(sx)x\(sy).")
        }
        let column = index % columns
        let row = index / columns
        let cellX0 = column * cellWidth
        let cellY0 = row * cellHeight
        let cellX1 = column == columns - 1 ? sx : min(sx, cellX0 + cellWidth)
        let cellY1 = row == rows - 1 ? sy : min(sy, cellY0 + cellHeight)
        let centerX = (cellX0 + cellX1 - patch.world.width) / 2
        let centerY = (cellY0 + cellY1 - patch.world.height) / 2
        let jitterX = max(0, min(cellWidth / 5, max(0, sx - patch.world.width) / 8))
        let jitterY = max(0, min(cellHeight / 5, max(0, sy - patch.world.height) / 8))
        let dx = jitterX == 0 ? 0 : Int.random(in: -jitterX...jitterX, using: &rng)
        let dy = jitterY == 0 ? 0 : Int.random(in: -jitterY...jitterY, using: &rng)
        return (
            x: min(max(0, centerX + dx), max(0, sx - patch.world.width)),
            y: min(max(0, centerY + dy), max(0, sy - patch.world.height))
        )
    }
}

private func flowLeniaEcology2025KernelTargets(_ c1: [[Int]], parameterCount: Int) -> [Int] {
    var targets = [Int](repeating: -1, count: parameterCount)
    for target in 0..<c1.count {
        for kernelIndex in c1[target] where kernelIndex >= 0 && kernelIndex < parameterCount {
            targets[kernelIndex] = target
        }
    }
    return targets
}

private func flowLeniaEcology2025ReorderedKernelScalars(
    values: [Float],
    kernelCount: Int,
    seedSources: [Int]?,
    seedTargets: [Int]?,
    runtimeSources: [Int],
    runtimeTargets: [Int]
) -> [Float]? {
    guard values.count == kernelCount else {
        return nil
    }
    guard let seedSources,
          let seedTargets,
          seedSources.count == kernelCount,
          seedTargets.count == kernelCount,
          runtimeSources.count == kernelCount,
          runtimeTargets.count == kernelCount else {
        return values
    }

    var unusedByRoute: [String: [Int]] = [:]
    for kernelIndex in 0..<kernelCount {
        unusedByRoute["\(seedSources[kernelIndex])->\(seedTargets[kernelIndex])", default: []].append(kernelIndex)
    }

    var reordered: [Float] = []
    reordered.reserveCapacity(kernelCount)
    for kernelIndex in 0..<kernelCount {
        let route = "\(runtimeSources[kernelIndex])->\(runtimeTargets[kernelIndex])"
        guard var candidates = unusedByRoute[route], !candidates.isEmpty else {
            return nil
        }
        let seedKernelIndex = candidates.removeFirst()
        unusedByRoute[route] = candidates
        reordered.append(values[seedKernelIndex])
    }
    return reordered
}

private func flowLeniaEcology2025SeedEmbeddedParameters(
    patch: ResearchSeedPatch,
    parameterFieldStyle: FlowLeniaEcology2025ParameterFieldStyle,
    kernelCount: Int,
    runtimeSources: [Int],
    runtimeTargets: [Int]
) -> [Float]? {
    guard let kernelParams = patch.kernelParams else {
        return nil
    }
    let seedSources = patch.kernelSources
    let seedTargets = patch.kernelTargets
    switch parameterFieldStyle {
    case .none:
        return nil
    case .kernelGain:
        return flowLeniaEcology2025ReorderedKernelScalars(
            values: kernelParams.h,
            kernelCount: kernelCount,
            seedSources: seedSources,
            seedTargets: seedTargets,
            runtimeSources: runtimeSources,
            runtimeTargets: runtimeTargets
        )
    case .localizedGrowthParameters:
        guard let reorderedM = flowLeniaEcology2025ReorderedKernelScalars(
            values: kernelParams.m,
            kernelCount: kernelCount,
            seedSources: seedSources,
            seedTargets: seedTargets,
            runtimeSources: runtimeSources,
            runtimeTargets: runtimeTargets
        ), let reorderedS = flowLeniaEcology2025ReorderedKernelScalars(
            values: kernelParams.s,
            kernelCount: kernelCount,
            seedSources: seedSources,
            seedTargets: seedTargets,
            runtimeSources: runtimeSources,
            runtimeTargets: runtimeTargets
        ), let reorderedH = flowLeniaEcology2025ReorderedKernelScalars(
            values: kernelParams.h,
            kernelCount: kernelCount,
            seedSources: seedSources,
            seedTargets: seedTargets,
            runtimeSources: runtimeSources,
            runtimeTargets: runtimeTargets
        ) else {
            return nil
        }
        return reorderedM + reorderedS + reorderedH
    }
}

private func flowLeniaEcology2025FrameMetrics(from summary: ActivitySummary?) -> [FlowLeniaEcology2025FrameMetrics] {
    guard let summary else {
        return []
    }
    return summary.steps.indices.map { index in
        FlowLeniaEcology2025FrameMetrics(
            step: summary.steps[index],
            speciesCount: summary.speciesCount[index],
            diversity: summary.diversity[index],
            presenceActivity: summary.eap[index],
            countActivity: summary.eac[index],
            nonNeutralActivity: summary.ean[index]
        )
    }
}

private func flowLeniaEcology2025ResolvedBaseConfig(
    from baseConfigData: Data,
    overrides: [String: Any]
) throws -> LeniaBaseConfig {
    guard var json = try JSONSerialization.jsonObject(with: baseConfigData) as? [String: Any] else {
        throw ConfigError.invalidConfig("flowlenia-ecology-2025 base config JSON must be an object.")
    }
    applyOverrides(&json, overrides: overrides)
    let modifiedData = try JSONSerialization.data(withJSONObject: json)
    return try JSONDecoder().decode(LeniaBaseConfig.self, from: modifiedData)
}

private func flowLeniaEcology2025StatePatch(
    from array: MLXArray,
    width: Int,
    height: Int,
    channels: Int
) -> InitStatePatchConfig {
    InitStatePatchConfig(
        center: [width / 2, height / 2],
        width: width,
        height: height,
        channels: channels,
        values: array.asArray(Float.self)
    )
}

private func flowLeniaEcology2025WorldArray(
    from patch: InitStatePatchConfig,
    sx: Int,
    sy: Int,
    channels: Int,
    label: String
) throws -> MLXArray {
    guard patch.width == sx, patch.height == sy, patch.channels == channels else {
        throw ConfigError.invalidConfig(
            "flowlenia-ecology-2025 \(label) patch \(patch.width)x\(patch.height)x\(patch.channels) does not match runtime \(sx)x\(sy)x\(channels)."
        )
    }
    let values = patch.decodedValues()
    guard values.count == sx * sy * channels else {
        throw ConfigError.invalidConfig(
            "flowlenia-ecology-2025 \(label) patch stores \(values.count) values but expected \(sx * sy * channels)."
        )
    }
    return MLXArray(values).reshaped([sx, sy, channels])
}

private func flowLeniaEcology2025ScalarField(
    from patch: InitStatePatchConfig,
    sx: Int,
    sy: Int,
    label: String
) throws -> MLXArray {
    guard patch.width == sx, patch.height == sy, patch.channels == 1 else {
        throw ConfigError.invalidConfig(
            "flowlenia-ecology-2025 \(label) patch \(patch.width)x\(patch.height)x\(patch.channels) does not match scalar field \(sx)x\(sy)x1."
        )
    }
    let values = patch.decodedValues()
    guard values.count == sx * sy else {
        throw ConfigError.invalidConfig(
            "flowlenia-ecology-2025 \(label) patch stores \(values.count) values but expected \(sx * sy)."
        )
    }
    return MLXArray(values).reshaped([sx, sy])
}

func flowLeniaFloatLabel(_ value: Float) -> String {
    let precision = abs(value) < 0.001 && value != 0 ? "%.6f" : "%.3f"
    let formatted = String(format: precision, value)
    return formatted.replacingOccurrences(of: ".", with: "_")
}
