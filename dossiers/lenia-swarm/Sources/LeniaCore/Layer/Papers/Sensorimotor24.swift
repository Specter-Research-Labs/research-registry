import Foundation
import Logging
import MLX
import MLXFFT
 
 public struct SensorimotorRuleSpaceConfig: Codable, Sendable {
     public struct Grid: Codable, Sendable {
         public let sx: Int
         public let sy: Int
     }
 
     public struct Channels: Codable, Sendable {
         public let learnable: Int
         public let obstacle: Int
         public let total: Int
     }
 
     public struct Range: Codable, Sendable {
         public let low: Float
         public let high: Float
     }
 
     public struct LearnableRules: Codable, Sendable {
         public let count: Int
         public let bumpsPerKernel: Int
         public let sharedT: Range
         public let sharedR: Range
         public let r: Range
         public let a: Range
         public let b: Range
         public let w: Range
         public let mu: Range
         public let sigma: Range
         public let h: Range
         public let sourceChannel: Int
         public let targetChannel: Int
         public let gateGain: Float
 
         enum CodingKeys: String, CodingKey {
             case count
             case bumpsPerKernel = "bumps_per_kernel"
             case sharedT = "shared_T"
             case sharedR = "shared_R"
             case r, a, b, w, mu, sigma, h
             case sourceChannel = "source_channel"
             case targetChannel = "target_channel"
             case gateGain = "gate_gain"
         }
     }
 
     public struct FixedObstacleRule: Codable, Sendable {
         public let sourceChannel: Int
         public let targetChannel: Int
         public let R: Float
         public let r: [Float]
         public let a: [Float]
         public let b: [Float]
         public let w: [Float]
         public let growthClipEpsilon: Float
         public let growthScale: Float
 
         enum CodingKeys: String, CodingKey {
             case sourceChannel = "source_channel"
             case targetChannel = "target_channel"
             case R, r, a, b, w
             case growthClipEpsilon = "growth_clip_epsilon"
             case growthScale = "growth_scale"
         }
     }
 
     public struct Initialization: Codable, Sendable {
         public let size: Int
         public let origin: [Int]
         public let valueRange: [Float]
         public let historyInitHScale: Float
 
         enum CodingKeys: String, CodingKey {
             case size
             case origin
             case valueRange = "value_range"
             case historyInitHScale = "history_init_h_scale"
         }
     }
 
     public struct SearchEnvironment: Codable, Sendable {
         public let obstacleCount: Int
         public let obstacleRadius: Int
         public let leftHalfClear: Bool
         public let clearInitialization: Bool
         public let clearInitializationRadius: Int
 
         enum CodingKeys: String, CodingKey {
             case obstacleCount = "obstacle_count"
             case obstacleRadius = "obstacle_radius"
             case leftHalfClear = "left_half_clear"
             case clearInitialization = "clear_initialization"
             case clearInitializationRadius = "clear_initialization_radius"
         }
     }
 
     public let paper: String
     public let grid: Grid
     public let channels: Channels
     public let learnableRules: LearnableRules
     public let fixedObstacleRule: FixedObstacleRule
     public let initialization: Initialization
     public let searchEnvironment: SearchEnvironment
 
     enum CodingKeys: String, CodingKey {
         case paper, grid, channels
         case learnableRules = "learnable_rules"
         case fixedObstacleRule = "fixed_obstacle_rule"
         case initialization
         case searchEnvironment = "search_environment"
     }
 }
 
 public struct SensorimotorTrainingConfig: Codable, Sendable {
     public struct GoalSampling: Codable, Sendable {
         public let warmupSteps: Int
         public let warmupStart: [Float]
         public let warmupDelta: [Float]
         public let collapseGoalMean: Float
         public let collapseGoalJitterStd: Float
         public let bestGoalProbability: Float
         public let randomFarProbability: Float
         public let bestGoalYOffset: [Float]
         public let bestGoalXOffset: [Float]
         public let farXRange: [Float]
         public let farYRange: [Float]
         public let broadXRange: [Float]
         public let broadYRange: [Float]
         public let closeDistance: Float
         public let veryCloseDistance: Float
         public let minCloseNeighbors: Int
         public let maxVeryCloseNeighbors: Int
 
         enum CodingKeys: String, CodingKey {
             case warmupSteps = "warmup_steps"
             case warmupStart = "warmup_start"
             case warmupDelta = "warmup_delta"
             case collapseGoalMean = "collapse_goal_mean"
             case collapseGoalJitterStd = "collapse_goal_jitter_std"
             case bestGoalProbability = "best_goal_probability"
             case randomFarProbability = "random_far_probability"
             case bestGoalYOffset = "best_goal_y_offset"
             case bestGoalXOffset = "best_goal_x_offset"
             case farXRange = "far_x_range"
             case farYRange = "far_y_range"
             case broadXRange = "broad_x_range"
             case broadYRange = "broad_y_range"
             case closeDistance = "close_distance"
             case veryCloseDistance = "very_close_distance"
             case minCloseNeighbors = "min_close_neighbors"
             case maxVeryCloseNeighbors = "max_very_close_neighbors"
         }
     }
 
     public struct SourceSelection: Codable, Sendable {
         public let collapseMax: Float
         public let collapseGoal: Float
 
         enum CodingKeys: String, CodingKey {
             case collapseMax = "collapse_max"
             case collapseGoal = "collapse_goal"
         }
     }
 
     public struct Optimization: Codable, Sendable {
         public let optimizer: String
         public let stepsUnmutated: Int
         public let stepsMutated: Int
         public let initializationLr: Float
         public let ruleLr: Float
         public let betas: [Float]
         public let eps: Float
 
         enum CodingKeys: String, CodingKey {
             case optimizer
             case stepsUnmutated = "steps_unmutated"
             case stepsMutated = "steps_mutated"
             case initializationLr = "initialization_lr"
             case ruleLr = "rule_lr"
             case betas, eps
         }
     }
 
     public struct Mutation: Codable, Sendable {
         public let mutateEveryNSteps: Int
         public let activeSigmaThreshold: Float
         public let activeKernelMutationProbability: Float
         public let TStd: Float
         public let RStd: Float
         public let rStd: Float
         public let aStd: Float
         public let bStd: Float
         public let wStd: Float
         public let muStd: Float
         public let sigmaStd: Float
         public let hStd: Float
         public let collapseMax: Float
         public let collapseMassMin: Float
 
         enum CodingKeys: String, CodingKey {
             case mutateEveryNSteps = "mutate_every_n_steps"
             case activeSigmaThreshold = "active_sigma_threshold"
             case activeKernelMutationProbability = "active_kernel_mutation_probability"
             case TStd = "T_std"
             case RStd = "R_std"
             case rStd = "r_std"
             case aStd = "a_std"
             case bStd = "b_std"
             case wStd = "w_std"
             case muStd = "mu_std"
             case sigmaStd = "sigma_std"
             case hStd = "h_std"
             case collapseMax = "collapse_max"
             case collapseMassMin = "collapse_mass_min"
         }
     }
 
     public struct Restart: Codable, Sendable {
         public let maxAttempts: Int
         public let minAliveRandomInitializations: Int
         public let deterministicValidationSteps: Int
         public let maxLoss: Float
 
         enum CodingKeys: String, CodingKey {
             case maxAttempts = "max_attempts"
             case minAliveRandomInitializations = "min_alive_random_initializations"
             case deterministicValidationSteps = "deterministic_validation_steps"
             case maxLoss = "max_loss"
         }
     }
 
     public struct EvaluationAfterStep: Codable, Sendable {
         public let rollouts: Int
     }
 
     public struct GoalMask: Codable, Sendable {
         public let normalizer: Float
         public let innerRadius: Float
         public let outerRadius: Float
         public let innerWeight: Float
         public let outerWeight: Float
         public let amplitude: Float
         public let collapseProxyNormalizer: Float
 
         enum CodingKeys: String, CodingKey {
             case normalizer
             case innerRadius = "inner_radius"
             case outerRadius = "outer_radius"
             case innerWeight = "inner_weight"
             case outerWeight = "outer_weight"
             case amplitude
             case collapseProxyNormalizer = "collapse_proxy_normalizer"
         }
     }
 
     public let paper: String
     public let outerSteps: Int
     public let historyInitializationTrials: Int
     public let rolloutSteps: Int
     public let goalSampling: GoalSampling
     public let sourceSelection: SourceSelection
     public let optimization: Optimization
     public let mutation: Mutation
     public let restart: Restart
     public let evaluationAfterStep: EvaluationAfterStep
     public let goalMask: GoalMask
 
     enum CodingKeys: String, CodingKey {
         case paper
         case outerSteps = "outer_steps"
         case historyInitializationTrials = "history_initialization_trials"
         case rolloutSteps = "rollout_steps"
         case goalSampling = "goal_sampling"
         case sourceSelection = "source_selection"
         case optimization, mutation, restart
         case evaluationAfterStep = "evaluation_after_step"
         case goalMask = "goal_mask"
     }
 }
 
 public struct SensorimotorEvaluationConfig: Codable, Sendable {
     public struct Prefilter: Codable, Sendable {
         public let rolloutSteps: Int
         public let finalMassMin: Float
         public let finalMassMax: Float
 
         enum CodingKeys: String, CodingKey {
             case rolloutSteps = "rollout_steps"
             case finalMassMin = "final_mass_min"
             case finalMassMax = "final_mass_max"
         }
     }
 
     public struct Agency: Codable, Sendable {
         public let rolloutSteps: Int
         public let finalMassMin: Float
         public let finalMassMax: Float
         public let massWindowA: [Int]
         public let massWindowB: [Int]
         public let maxMassRatio: Float
         public let connectivityThreshold: Float
 
         enum CodingKeys: String, CodingKey {
             case rolloutSteps = "rollout_steps"
             case finalMassMin = "final_mass_min"
             case finalMassMax = "final_mass_max"
             case massWindowA = "mass_window_a"
             case massWindowB = "mass_window_b"
             case maxMassRatio = "max_mass_ratio"
             case connectivityThreshold = "connectivity_threshold"
         }
     }
 
     public struct Moving: Codable, Sendable {
         public let distanceThreshold: Float
         public let windowEnd: Int
         public let speedWindow: Int
         public let speedStart: Int
 
         enum CodingKeys: String, CodingKey {
             case distanceThreshold = "distance_threshold"
             case windowEnd = "window_end"
             case speedWindow = "speed_window"
             case speedStart = "speed_start"
         }
     }
 
     public struct BasicObstacleTest: Codable, Sendable {
         public let rollouts: Int
         public let rolloutSteps: Int
         public let obstacleRadius: Int
         public let obstacleCount: Int
         public let randomObstacles: Int
         public let forcedObstacleOnNominalTrajectory: Bool
         public let forcedObstacleReferenceStep: Int
         public let clearInitializationRadius: Int
 
         enum CodingKeys: String, CodingKey {
             case rollouts
             case rolloutSteps = "rollout_steps"
             case obstacleRadius = "obstacle_radius"
             case obstacleCount = "obstacle_count"
             case randomObstacles = "random_obstacles"
             case forcedObstacleOnNominalTrajectory = "forced_obstacle_on_nominal_trajectory"
             case forcedObstacleReferenceStep = "forced_obstacle_reference_step"
             case clearInitializationRadius = "clear_initialization_radius"
         }
     }
 
     public struct Generalization: Codable, Sendable {
         public let trialsPerSetting: Int
         public let obstacleRadius: [Int]
         public let obstacleCount: [Int]
         public let obstacleSpeed: [Float]
         public let updateMaskRate: [Float]
         public let updateNoiseStd: [Float]
         public let updateNoiseRate: [Float]
         public let initNoiseRate: [Float]
         public let initNoiseStd: [Float]
         public let scale: [Float]
 
         enum CodingKeys: String, CodingKey {
             case trialsPerSetting = "trials_per_setting"
             case obstacleRadius = "obstacle_radius"
             case obstacleCount = "obstacle_count"
             case obstacleSpeed = "obstacle_speed"
             case updateMaskRate = "update_mask_rate"
             case updateNoiseStd = "update_noise_std"
             case updateNoiseRate = "update_noise_rate"
             case initNoiseRate = "init_noise_rate"
             case initNoiseStd = "init_noise_std"
             case scale
         }
     }
 
     public let paper: String
     public let prefilter: Prefilter
     public let agency: Agency
     public let moving: Moving
     public let basicObstacleTest: BasicObstacleTest
     public let generalization: Generalization
 
     enum CodingKeys: String, CodingKey {
         case paper, prefilter, agency, moving
         case basicObstacleTest = "basic_obstacle_test"
         case generalization
     }
 }
 
 public struct SensorimotorGoal: Codable, Sendable {
     public let collapse: Float
     public let centroidX: Float
     public let centroidY: Float
 
     public init(collapse: Float, centroidX: Float, centroidY: Float) {
         self.collapse = collapse
         self.centroidX = centroidX
         self.centroidY = centroidY
     }
 
     var vector: [Float] { [collapse, centroidX, centroidY] }
 }
 
 public struct SensorimotorRuleParameters: Codable, Sendable {
     public let T: Float
     public let R: Float
     public let r: [Float]
     public let a: [[Float]]
     public let b: [[Float]]
     public let w: [[Float]]
     public let mu: [Float]
     public let sigma: [Float]
     public let h: [Float]
 }
 
 public struct SensorimotorCandidate: Codable, Sendable {
     public let initialization: [[Float]]
     public let rules: SensorimotorRuleParameters
 }
 
 public struct SensorimotorHistoryEntry: Codable, Sendable {
     public let step: Int
     public let goal: SensorimotorGoal?
     public let reached: SensorimotorGoal
     public let candidate: SensorimotorCandidate
     public let mutated: Bool
     public let optimizationSteps: Int
     public let trainingLoss: Float?
     public let rolloutCounts: SensorimotorRolloutCounts
 
     enum CodingKeys: String, CodingKey {
         case step, goal, reached, candidate, mutated
         case optimizationSteps = "optimization_steps"
         case trainingLoss = "training_loss"
         case rolloutCounts = "rollout_counts"
     }
 }
 
 public struct SensorimotorRolloutCounts: Codable, Sendable {
     public let randomInitialization: Int
     public let mutationFilter: Int
     public let gradient: Int
     public let evaluation: Int
 
     enum CodingKeys: String, CodingKey {
         case randomInitialization = "random_initialization"
         case mutationFilter = "mutation_filter"
         case gradient, evaluation
     }
 }
 
 public struct SensorimotorAgencySummary: Codable, Sendable {
     public let prefilterPassed: Bool
     public let agencyPassed: Bool
     public let movingPassed: Bool
     public let finalMass: Float
     public let massRatio: Float
     public let connected: Bool
     public let maxDistanceWithinWindow: Float
     public let speedNoObstacles: Float
 
     enum CodingKeys: String, CodingKey {
         case prefilterPassed = "prefilter_passed"
         case agencyPassed = "agency_passed"
         case movingPassed = "moving_passed"
         case finalMass = "final_mass"
         case massRatio = "mass_ratio"
         case connected
         case maxDistanceWithinWindow = "max_distance_within_window"
         case speedNoObstacles = "speed_no_obstacles"
     }
 }
 
 public struct SensorimotorScenarioResult: Codable, Sendable {
     public let name: String
     public let value: Float
     public let robustness: Float
     public let speed: Float
 }
 
 public struct SensorimotorEvaluationSummary: Codable, Sendable {
     public let agency: SensorimotorAgencySummary
     public let basicObstacleRobustness: Float
     public let basicObstacleSpeed: Float
     public let scenarios: [SensorimotorScenarioResult]
 
     enum CodingKeys: String, CodingKey {
         case agency
         case basicObstacleRobustness = "basic_obstacle_robustness"
         case basicObstacleSpeed = "basic_obstacle_speed"
         case scenarios
     }
 }
 
 public struct SensorimotorRunSummary: Codable, Sendable {
     public let restartCount: Int
     public let historyCount: Int
     public let bestReached: SensorimotorGoal
     public let bestEvaluation: SensorimotorEvaluationSummary
 
     enum CodingKeys: String, CodingKey {
         case restartCount = "restart_count"
         case historyCount = "history_count"
         case bestReached = "best_reached"
         case bestEvaluation = "best_evaluation"
     }
 }
 
 private struct SensorimotorLearnableState {
     var T: MLXArray
     var R: MLXArray
     var r: MLXArray
     var a: MLXArray
     var b: MLXArray
     var w: MLXArray
     var mu: MLXArray
     var sigma: MLXArray
     var h: MLXArray
     var initialization: MLXArray
 
     init(arrays: [MLXArray]) {
         self.T = arrays[0]
         self.R = arrays[1]
         self.r = arrays[2]
         self.a = arrays[3]
         self.b = arrays[4]
         self.w = arrays[5]
         self.mu = arrays[6]
         self.sigma = arrays[7]
         self.h = arrays[8]
         self.initialization = arrays[9]
     }
 
     var arrays: [MLXArray] {
         [T, R, r, a, b, w, mu, sigma, h, initialization]
     }
 }
 
 private struct SensorimotorAdamGroup {
     var m: [MLXArray]
     var v: [MLXArray]
     var learningRate: Float
 
     init(paramShapes: [[Int]], learningRate: Float) {
         self.m = paramShapes.map { MLX.zeros($0) }
         self.v = paramShapes.map { MLX.zeros($0) }
         self.learningRate = learningRate
     }
 }
 
 private struct SensorimotorAdam {
     private var ruleGroup: SensorimotorAdamGroup
     private var initGroup: SensorimotorAdamGroup
     private let beta1: Float
     private let beta2: Float
     private let eps: Float
     private var step: Int = 0
 
     init(state: SensorimotorLearnableState, ruleLr: Float, initLr: Float, betas: [Float], eps: Float) {
         let ruleShapes = state.arrays[0..<9].map(\.shape)
         self.ruleGroup = SensorimotorAdamGroup(paramShapes: ruleShapes, learningRate: ruleLr)
         self.initGroup = SensorimotorAdamGroup(paramShapes: [state.initialization.shape], learningRate: initLr)
         self.beta1 = betas[0]
         self.beta2 = betas[1]
         self.eps = eps
     }
 
     mutating func apply(state: inout SensorimotorLearnableState, gradients: [MLXArray]) {
         step += 1
         let t = Float(step)
         let oneMinusBeta1 = 1 - beta1
         let oneMinusBeta2 = 1 - beta2
         let bias1 = 1 - Foundation.pow(beta1, t)
         let bias2 = 1 - Foundation.pow(beta2, t)
         let arrays = state.arrays
         let ruleArrays = Array(arrays[0..<9])
 
         func gradientOrZero(_ index: Int) -> MLXArray {
             if index < gradients.count {
                 return gradients[index]
             }
             // MLX can leave disconnected entries out of array-list gradients, so preserve zero-update semantics.
             return MLX.zeros(arrays[index].shape)
         }
 
         var updatedRuleArrays: [MLXArray] = []
         updatedRuleArrays.reserveCapacity(ruleArrays.count)
         for index in 0..<ruleArrays.count {
             let grad = gradientOrZero(index)
             ruleGroup.m[index] = MLXArray(beta1) * ruleGroup.m[index] + MLXArray(oneMinusBeta1) * grad
             ruleGroup.v[index] = MLXArray(beta2) * ruleGroup.v[index] + MLXArray(oneMinusBeta2) * (grad * grad)
             let mHat = ruleGroup.m[index] / MLXArray(bias1)
             let vHat = ruleGroup.v[index] / MLXArray(bias2)
             let denom = MLX.sqrt(vHat) + MLXArray(eps)
             updatedRuleArrays.append(ruleArrays[index] - MLXArray(ruleGroup.learningRate) * mHat / denom)
         }
 
         let initGrad = gradientOrZero(9)
         initGroup.m[0] = MLXArray(beta1) * initGroup.m[0] + MLXArray(oneMinusBeta1) * initGrad
         initGroup.v[0] = MLXArray(beta2) * initGroup.v[0] + MLXArray(oneMinusBeta2) * (initGrad * initGrad)
         let initMHat = initGroup.m[0] / MLXArray(bias1)
         let initVHat = initGroup.v[0] / MLXArray(bias2)
         let initDenom = MLX.sqrt(initVHat) + MLXArray(eps)
         let updatedInit = state.initialization - MLXArray(initGroup.learningRate) * initMHat / initDenom
 
         var updatedArrays = updatedRuleArrays
         updatedArrays.append(updatedInit)
         state = SensorimotorLearnableState(arrays: updatedArrays)
     }
 }
 
 private struct SensorimotorPerturbations {
     var obstacleSpeed: Float?
     var updateMaskRate: Float?
     var updateNoiseStd: Float?
     var updateNoiseRate: Float?
     var initNoiseRate: Float?
     var initNoiseStd: Float?
     var scale: Float?
 }
 
 private struct SensorimotorObstacleBatch {
     let field: MLXArray
     let center: (Float, Float)?
 }
 
 private struct SensorimotorTrace {
     let masses: [Float]
     let centers: [(Float, Float)?]
     let finalState: MLXArray
 }
 
 public struct SensorimotorLenia2024ConfigBundle: Codable, Sendable {
     public let ruleSpace: SensorimotorRuleSpaceConfig
     public let training: SensorimotorTrainingConfig
     public let evaluation: SensorimotorEvaluationConfig
 }
 
 public struct SensorimotorBestResult: Codable, Sendable {
     public let reached: SensorimotorGoal
     public let candidate: SensorimotorCandidate
     public let evaluation: SensorimotorEvaluationSummary
 }
 
 public struct SensorimotorLenia2024ReplayPayload: Codable, Sendable {
     public let configs: SensorimotorLenia2024ConfigBundle
     public let archiveSlot: Int
     public let replaySeed: UInt64
     public let entry: SensorimotorHistoryEntry
 }
 
 public struct SensorimotorLenia2024ReplayOutcome: Sendable {
     public let resultData: SimulationResultData
     public let creature: SavedCreature
 
     public init(resultData: SimulationResultData, creature: SavedCreature) {
         self.resultData = resultData
         self.creature = creature
     }
 }
 
 private struct SensorimotorHistoryRecord {
     let entry: SensorimotorHistoryEntry
     let state: SensorimotorLearnableState
 }
 
 private struct SensorimotorGradientResult {
     let state: SensorimotorLearnableState
     let loss: Float
     let reached: SensorimotorGoal
     let steps: Int
     let gradientRollouts: Int
 }
 
 private let sensorimotorConfigFilenames = (
     ruleSpace: "rule_space_and_init.json",
     training: "train_curriculum.json",
     evaluation: "evaluation_battery.json"
 )
 
 public func loadSensorimotorLenia2024ConfigBundle(configDirectory: URL) throws -> SensorimotorLenia2024ConfigBundle {
     let decoder = JSONDecoder()
     let ruleData = try Data(contentsOf: configDirectory.appendingPathComponent(sensorimotorConfigFilenames.ruleSpace))
     let trainingData = try Data(contentsOf: configDirectory.appendingPathComponent(sensorimotorConfigFilenames.training))
     let evaluationData = try Data(contentsOf: configDirectory.appendingPathComponent(sensorimotorConfigFilenames.evaluation))
     return SensorimotorLenia2024ConfigBundle(
         ruleSpace: try decoder.decode(SensorimotorRuleSpaceConfig.self, from: ruleData),
         training: try decoder.decode(SensorimotorTrainingConfig.self, from: trainingData),
         evaluation: try decoder.decode(SensorimotorEvaluationConfig.self, from: evaluationData)
     )
 }
 
 public final class SensorimotorLenia2024Runner {
     private let configs: SensorimotorLenia2024ConfigBundle
     private let logger: Logger
     private let encoder: JSONEncoder
     private let seedInitialization: [[Float]]?
 
     public init(
         configs: SensorimotorLenia2024ConfigBundle,
         logger: Logger,
         seedInitialization: [[Float]]? = nil
     ) {
         self.configs = configs
         self.logger = logger
         self.seedInitialization = seedInitialization
         let encoder = JSONEncoder()
         encoder.outputFormatting = [.sortedKeys]
         self.encoder = encoder
     }
 
     public func writeResolvedConfigs(to outputDirectory: URL) throws {
         try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
         try encoder.encode(configs.ruleSpace).write(to: outputDirectory.appendingPathComponent(sensorimotorConfigFilenames.ruleSpace))
         try encoder.encode(configs.training).write(to: outputDirectory.appendingPathComponent(sensorimotorConfigFilenames.training))
         try encoder.encode(configs.evaluation).write(to: outputDirectory.appendingPathComponent(sensorimotorConfigFilenames.evaluation))
     }
 
     public func run(seed: UInt64, outputDirectory: URL, runId: String) throws -> SensorimotorRunSummary {
         try writeResolvedConfigs(to: outputDirectory)
 
         let historyURL = outputDirectory.appendingPathComponent("history.jsonl")
         let summaryURL = outputDirectory.appendingPathComponent("summary.json")
         let bestURL = outputDirectory.appendingPathComponent("best.json")
 
         FileManager.default.createFile(atPath: historyURL.path, contents: nil)
         let historyHandle = try FileHandle(forWritingTo: historyURL)
         defer { try? historyHandle.close() }
 
         var rng = SeededRandomNumberGenerator(seed: seed)
         let training = configs.training
         var restartCount = 0
         var finalHistory: [SensorimotorHistoryRecord] = []
 
         while restartCount < training.restart.maxAttempts && finalHistory.isEmpty {
             logger.info("Sensorimotor 2024 attempt \(restartCount + 1)/\(training.restart.maxAttempts)")
             let candidateHistory = try runAttempt(rng: &rng, historyHandle: historyHandle)
             if candidateHistory.isEmpty {
                 restartCount += 1
                 continue
             }
             finalHistory = candidateHistory
         }
 
         guard !finalHistory.isEmpty else {
             throw NSError(
                 domain: "SensorimotorLenia2024",
                 code: 1,
                 userInfo: [NSLocalizedDescriptionKey: "All Hamon 2024 restart attempts failed before producing a valid history."]
             )
         }
 
         let bestIndex = sensorimotorBestHistoryIndex(history: finalHistory, collapseMax: configs.training.sourceSelection.collapseMax)
         let bestRecord = finalHistory[bestIndex]
         logger.info("Evaluating best candidate from outer step \(bestRecord.entry.step)")
         let evaluation = try evaluate(state: bestRecord.state, rng: &rng)
         let bestResult = SensorimotorBestResult(
             reached: bestRecord.entry.reached,
             candidate: sensorimotorCandidate(from: bestRecord.state),
             evaluation: evaluation
         )
         try encoder.encode(bestResult).write(to: bestURL)
 
         let summary = SensorimotorRunSummary(
             restartCount: restartCount,
             historyCount: finalHistory.count,
             bestReached: bestRecord.entry.reached,
             bestEvaluation: evaluation
         )
         try encoder.encode(summary).write(to: summaryURL)
         try sensorimotorWriteLibraryIndex(
             configs: configs,
             history: finalHistory,
             bestIndex: bestIndex,
             bestEvaluation: evaluation,
             runId: runId,
             outputDirectory: outputDirectory
         )
         try sensorimotorWriteReplayExports(
             configs: configs,
             history: finalHistory,
             bestIndex: bestIndex,
             runId: runId,
             sourceSeed: seed,
             outputDirectory: outputDirectory
         )
         return summary
     }
 
     private func runAttempt(
         rng: inout SeededRandomNumberGenerator,
         historyHandle: FileHandle
     ) throws -> [SensorimotorHistoryRecord] {
         let rules = configs.ruleSpace
         let training = configs.training
         var history: [SensorimotorHistoryRecord] = []
         history.reserveCapacity(training.outerSteps)
         var aliveRandom = 0
         var restartAllowed = true
 
         while history.count < training.outerSteps {
             if history.count < training.historyInitializationTrials {
                 var state = sensorimotorSampleLearnableState(rules: rules, rng: &rng)
                 if history.isEmpty, let seedInitialization {
                     state.initialization = MLXArray(seedInitialization.flatMap { $0 }).reshaped([
                         seedInitialization.count,
                         seedInitialization.first?.count ?? 0
                     ])
                 }
                 let obstacle = sensorimotorRandomObstacleField(
                     rules: rules,
                     count: rules.searchEnvironment.obstacleCount,
                     radius: rules.searchEnvironment.obstacleRadius,
                     forcedCenter: nil,
                     rng: &rng
                 )
                 let trace = sensorimotorRollout(
                     state: state,
                     obstacleField: obstacle.field,
                     steps: training.rolloutSteps,
                     rules: rules,
                     perturbations: SensorimotorPerturbations(),
                     perturbUntilStep: training.rolloutSteps - 1,
                     rng: &rng
                 )
                 let reached = sensorimotorEmbedding(finalState: trace.finalState, training: training, rules: rules)
                 if sensorimotorIsAliveForArchive(reached: reached, finalMass: trace.masses.last ?? 0, collapseMax: training.sourceSelection.collapseMax) {
                     aliveRandom += 1
                 }
                 let entry = SensorimotorHistoryEntry(
                     step: history.count,
                     goal: nil,
                     reached: reached,
                     candidate: sensorimotorCandidate(from: state),
                     mutated: false,
                     optimizationSteps: 0,
                     trainingLoss: nil,
                     rolloutCounts: SensorimotorRolloutCounts(
                         randomInitialization: 1,
                         mutationFilter: 0,
                         gradient: 0,
                         evaluation: 1
                     )
                 )
                 try sensorimotorWriteHistoryEntry(entry, to: historyHandle, encoder: encoder)
                 history.append(SensorimotorHistoryRecord(entry: entry, state: state))
 
                 if history.count == training.historyInitializationTrials,
                     aliveRandom < training.restart.minAliveRandomInitializations
                 {
                     logger.warning("Restarting Hamon 2024 attempt: alive random count \(aliveRandom) < \(training.restart.minAliveRandomInitializations)")
                     return []
                 }
                 continue
             }
 
             let explorationIndex = history.count - training.historyInitializationTrials
             let goal = sensorimotorSampleGoal(
                 explorationIndex: explorationIndex,
                 history: history,
                 training: training,
                 rng: &rng
             )
             let sourceIndex = sensorimotorSourceIndex(for: goal, history: history, training: training)
             let sourceState = history[sourceIndex].state
             let useSourceDirectly =
                 explorationIndex < training.goalSampling.warmupSteps ||
                 history.count % training.mutation.mutateEveryNSteps == 0
 
             let mutationResult: (state: SensorimotorLearnableState, mutated: Bool, mutationRollouts: Int)
             if useSourceDirectly {
                 mutationResult = (sourceState, false, 0)
             } else {
                 mutationResult = sensorimotorMutatedState(
                     source: sourceState,
                     rules: rules,
                     training: training,
                     rng: &rng
                 )
             }
 
             let optimized = sensorimotorOptimizeTowardGoal(
                 initialState: mutationResult.state,
                 goal: goal,
                 rules: rules,
                 training: training,
                 mutated: mutationResult.mutated,
                 rng: &rng
             )
 
             if restartAllowed, explorationIndex < 2, optimized.loss > training.restart.maxLoss {
                 logger.warning("Restarting Hamon 2024 attempt: early post-random loss \(optimized.loss) > \(training.restart.maxLoss)")
                 return []
             }
             if restartAllowed, explorationIndex == 1 {
                 restartAllowed = false
             }
 
             let evaluationResult = sensorimotorArchiveEvaluation(
                 state: optimized.state,
                 rules: rules,
                 training: training,
                 rng: &rng
             )
 
             let entry = SensorimotorHistoryEntry(
                 step: history.count,
                 goal: goal,
                 reached: evaluationResult.reached,
                 candidate: sensorimotorCandidate(from: optimized.state),
                 mutated: mutationResult.mutated,
                 optimizationSteps: optimized.steps,
                 trainingLoss: optimized.loss,
                 rolloutCounts: SensorimotorRolloutCounts(
                     randomInitialization: 0,
                     mutationFilter: mutationResult.mutationRollouts,
                     gradient: optimized.gradientRollouts,
                     evaluation: training.evaluationAfterStep.rollouts
                 )
             )
             try sensorimotorWriteHistoryEntry(entry, to: historyHandle, encoder: encoder)
             history.append(SensorimotorHistoryRecord(entry: entry, state: optimized.state))
         }
 
         return history
     }
 
     private func evaluate(
         state: SensorimotorLearnableState,
         rng: inout SeededRandomNumberGenerator
     ) throws -> SensorimotorEvaluationSummary {
         try sensorimotorEvaluate(
             state: state,
             configs: configs,
             rng: &rng
         ).summary
     }
 }
 
 private func sensorimotorEvaluate(
     state: SensorimotorLearnableState,
     configs: SensorimotorLenia2024ConfigBundle,
     rng: inout SeededRandomNumberGenerator
 ) throws -> (nominalTrace: SensorimotorTrace, summary: SensorimotorEvaluationSummary) {
     let rules = configs.ruleSpace
     let evaluation = configs.evaluation
     let nominalTrace = sensorimotorRollout(
         state: state,
         obstacleField: MLX.zeros([rules.grid.sx, rules.grid.sy]),
         steps: evaluation.agency.rolloutSteps,
         rules: rules,
         perturbations: SensorimotorPerturbations(),
         perturbUntilStep: evaluation.agency.rolloutSteps - 1,
         rng: &rng
     )
     let agencySummary = sensorimotorAgencySummary(
         trace: nominalTrace,
         state: state,
         rules: rules,
         evaluation: evaluation
     )
 
     let basicObstacle = sensorimotorBasicObstacleEvaluation(
         state: state,
         nominalTrace: nominalTrace,
         rules: rules,
         evaluation: evaluation,
         rng: &rng
     )
 
     var scenarios: [SensorimotorScenarioResult] = []
     scenarios.reserveCapacity(
         evaluation.generalization.obstacleRadius.count +
         evaluation.generalization.obstacleCount.count +
         evaluation.generalization.obstacleSpeed.count +
         evaluation.generalization.updateMaskRate.count +
         evaluation.generalization.updateNoiseStd.count +
         evaluation.generalization.updateNoiseRate.count +
         evaluation.generalization.initNoiseRate.count +
         evaluation.generalization.initNoiseStd.count +
         evaluation.generalization.scale.count
     )
 
     for radius in evaluation.generalization.obstacleRadius {
         scenarios.append(try sensorimotorScenarioSweep(
             name: "obstacle_radius",
             value: Float(radius),
             state: state,
             rules: rules,
             evaluation: evaluation,
             perturbations: SensorimotorPerturbations(),
             obstacleCount: sensorimotorScaledObstacleCount(radius: radius),
             obstacleRadius: radius,
             rng: &rng
         ))
     }
     for count in evaluation.generalization.obstacleCount {
         scenarios.append(try sensorimotorScenarioSweep(
             name: "obstacle_count",
             value: Float(count),
             state: state,
             rules: rules,
             evaluation: evaluation,
             perturbations: SensorimotorPerturbations(),
             obstacleCount: count,
             obstacleRadius: evaluation.basicObstacleTest.obstacleRadius,
             rng: &rng
         ))
     }
     for speed in evaluation.generalization.obstacleSpeed {
         scenarios.append(try sensorimotorScenarioSweep(
             name: "obstacle_speed",
             value: speed,
             state: state,
             rules: rules,
             evaluation: evaluation,
             perturbations: SensorimotorPerturbations(obstacleSpeed: speed),
             obstacleCount: evaluation.basicObstacleTest.obstacleCount,
             obstacleRadius: evaluation.basicObstacleTest.obstacleRadius,
             rng: &rng
         ))
     }
     for rate in evaluation.generalization.updateMaskRate {
         scenarios.append(try sensorimotorScenarioSweep(
             name: "update_mask_rate",
             value: rate,
             state: state,
             rules: rules,
             evaluation: evaluation,
             perturbations: SensorimotorPerturbations(updateMaskRate: rate),
             obstacleCount: 0,
             obstacleRadius: evaluation.basicObstacleTest.obstacleRadius,
             perturbUntilStep: 1900 - 1,
             rng: &rng
         ))
     }
     for std in evaluation.generalization.updateNoiseStd {
         scenarios.append(try sensorimotorScenarioSweep(
             name: "update_noise_std",
             value: std,
             state: state,
             rules: rules,
             evaluation: evaluation,
             perturbations: SensorimotorPerturbations(updateNoiseStd: std, updateNoiseRate: 1.0),
             obstacleCount: 0,
             obstacleRadius: evaluation.basicObstacleTest.obstacleRadius,
             perturbUntilStep: 1900 - 1,
             rng: &rng
         ))
     }
     for rate in evaluation.generalization.updateNoiseRate {
         scenarios.append(try sensorimotorScenarioSweep(
             name: "update_noise_rate",
             value: rate,
             state: state,
             rules: rules,
             evaluation: evaluation,
             perturbations: SensorimotorPerturbations(updateNoiseStd: 1.0, updateNoiseRate: rate),
             obstacleCount: 0,
             obstacleRadius: evaluation.basicObstacleTest.obstacleRadius,
             perturbUntilStep: 1900 - 1,
             rng: &rng
         ))
     }
     for rate in evaluation.generalization.initNoiseRate {
         scenarios.append(try sensorimotorScenarioSweep(
             name: "init_noise_rate",
             value: rate,
             state: state,
             rules: rules,
             evaluation: evaluation,
             perturbations: SensorimotorPerturbations(initNoiseRate: rate, initNoiseStd: 1.0),
             obstacleCount: 0,
             obstacleRadius: evaluation.basicObstacleTest.obstacleRadius,
             rng: &rng
         ))
     }
     for std in evaluation.generalization.initNoiseStd {
         scenarios.append(try sensorimotorScenarioSweep(
             name: "init_noise_std",
             value: std,
             state: state,
             rules: rules,
             evaluation: evaluation,
             perturbations: SensorimotorPerturbations(initNoiseRate: 1.0, initNoiseStd: std),
             obstacleCount: 0,
             obstacleRadius: evaluation.basicObstacleTest.obstacleRadius,
             rng: &rng
         ))
     }
     for scale in evaluation.generalization.scale {
         scenarios.append(try sensorimotorScenarioSweep(
             name: "scale",
             value: scale,
             state: state,
             rules: rules,
             evaluation: evaluation,
             perturbations: SensorimotorPerturbations(scale: scale),
             obstacleCount: 0,
             obstacleRadius: evaluation.basicObstacleTest.obstacleRadius,
             rng: &rng
         ))
     }
 
     return (
         nominalTrace,
         SensorimotorEvaluationSummary(
             agency: agencySummary,
             basicObstacleRobustness: basicObstacle.robustness,
             basicObstacleSpeed: basicObstacle.speed,
             scenarios: scenarios
         )
     )
 }
 
 private func sensorimotorFFTShift2(_ x: MLXArray) -> MLXArray {
     rollMultiAxis(x, shifts: [x.shape[0] / 2, x.shape[1] / 2], axes: [0, 1])
 }
 
 private func sensorimotorGoalDistance(_ a: SensorimotorGoal, _ b: SensorimotorGoal) -> Float {
     let dc = a.collapse - b.collapse
     let dx = a.centroidX - b.centroidX
     let dy = a.centroidY - b.centroidY
     return sqrt(dc * dc + dx * dx + dy * dy)
 }
 
 private func sensorimotorGaussian(std: Float, rng: inout SeededRandomNumberGenerator) -> Float {
     let u1 = Float.random(in: 0.0001...0.9999, using: &rng)
     let u2 = Float.random(in: 0.0...1.0, using: &rng)
     return sqrt(-2.0 * log(u1)) * cos(2.0 * Float.pi * u2) * std
 }
 
 private func sensorimotorUniform(range: [Float], rng: inout SeededRandomNumberGenerator) -> Float {
     Float.random(in: range[0]...range[1], using: &rng)
 }
 
 private func sensorimotorCoordinates(_ rules: SensorimotorRuleSpaceConfig) -> (MLXArray, MLXArray) {
     let x = MLXArray(Array(0..<rules.grid.sx).map { Float($0) - Float(rules.grid.sx) / 2 })
     let y = MLXArray(Array(0..<rules.grid.sy).map { Float($0) - Float(rules.grid.sy) / 2 })
     return meshgrid(x, y)
 }
 
 private func sensorimotorRolloutStep(
     state: MLXArray,
     obstacleField: MLXArray,
     params: SensorimotorLearnableState,
     rules: SensorimotorRuleSpaceConfig
 ) -> MLXArray {
     let (X, Y) = sensorimotorCoordinates(rules)
     let distance = MLX.sqrt(X * X + Y * Y)
     let stateFFT = MLXFFT.fft2(state, axes: [0, 1])
     let obstacleFFT = MLXFFT.fft2(obstacleField, axes: [0, 1])
 
     var growthTotal = MLX.zeros([rules.grid.sx, rules.grid.sy])
     for ruleIndex in 0..<rules.learnableRules.count {
         // Upstream Hamon 2024 Lenia stores R as a discrete offset and scales kernels with (R + 15) * r.
         let radius = (params.R + MLXArray(15.0)) * params.r[ruleIndex]
         let scaled = distance / radius
         let gate = sigmoid((MLXArray(1.0) - scaled) * MLXArray(rules.learnableRules.gateGain))
         let kernel = gate * kernelProfile(
             scaled,
             a: params.a[ruleIndex],
             w: params.w[ruleIndex],
             b: params.b[ruleIndex],
             kernelProfile: "flowlenia_2022_paper_equations"
         )
         let kernelNorm = kernel / (kernel.sum() + MLXArray(1e-10))
         let kernelFFT = MLXFFT.fft2(sensorimotorFFTShift2(kernelNorm), axes: [0, 1])
         let potential = sensorimotorFFTShift2(
             MLXFFT.ifft2(stateFFT * kernelFFT, axes: [0, 1]).realPart()
         )
         let sigma = MLX.maximum(params.sigma[ruleIndex], MLXArray(1e-4))
         let diff = potential - params.mu[ruleIndex]
         let field = (MLX.exp(-(diff * diff) / (MLXArray(2.0) * sigma * sigma) - MLXArray(1e-3)) * MLXArray(2.0)) - MLXArray(1.0)
         growthTotal = growthTotal + params.h[ruleIndex] * field
     }
 
     let obstacleScaled = distance / MLXArray(rules.fixedObstacleRule.R)
     let obstacleGate = sigmoid((MLXArray(1.0) - obstacleScaled) * MLXArray(rules.learnableRules.gateGain))
     let obstacleKernel = obstacleGate * kernelProfile(
         obstacleScaled,
         a: MLXArray(rules.fixedObstacleRule.a),
         w: MLXArray(rules.fixedObstacleRule.w),
         b: MLXArray(rules.fixedObstacleRule.b),
         kernelProfile: "flowlenia_2022_paper_equations"
     )
     let obstacleKernelNorm = obstacleKernel / (obstacleKernel.sum() + MLXArray(1e-10))
     let obstacleKernelFFT = MLXFFT.fft2(sensorimotorFFTShift2(obstacleKernelNorm), axes: [0, 1])
     let obstaclePotential = sensorimotorFFTShift2(
         MLXFFT.ifft2(obstacleFFT * obstacleKernelFFT, axes: [0, 1]).realPart()
     )
     let obstacleGrowth = -MLX.clip(
         obstaclePotential - MLXArray(rules.fixedObstacleRule.growthClipEpsilon),
         min: MLXArray(0.0),
         max: MLXArray(1.0)
     ) * MLXArray(rules.fixedObstacleRule.growthScale)
 
     return MLX.clip(
         state + (growthTotal + obstacleGrowth) / MLX.maximum(params.T, MLXArray(1e-4)),
         min: MLXArray(0.0),
         max: MLXArray(1.0)
     )
 }
 
 private func sensorimotorGoalMask(
     goal: SensorimotorGoal,
     training: SensorimotorTrainingConfig,
     rules: SensorimotorRuleSpaceConfig
 ) -> MLXArray {
     let (X, Y) = sensorimotorCoordinates(rules)
     let targetX = MLXArray(goal.centroidX * Float(rules.grid.sx))
     let targetY = MLXArray(goal.centroidY * Float(rules.grid.sy))
     let dx = (X - targetX) / MLXArray(training.goalMask.normalizer)
     let dy = (Y - targetY) / MLXArray(training.goalMask.normalizer)
     let D = MLX.sqrt(dx * dx + dy * dy)
     let inner = (D .< MLXArray(training.goalMask.innerRadius)).asType(.float32) * MLXArray(training.goalMask.innerWeight)
     let outer = (D .< MLXArray(training.goalMask.outerRadius)).asType(.float32) * MLXArray(training.goalMask.outerWeight)
     return (inner + outer) * MLXArray(training.goalMask.amplitude)
 }
 
 private func sensorimotorGoalLoss(
     finalState: MLXArray,
     goal: SensorimotorGoal,
     training: SensorimotorTrainingConfig,
     rules: SensorimotorRuleSpaceConfig
 ) -> MLXArray {
     let target = sensorimotorGoalMask(goal: goal, training: training, rules: rules)
     let diff = target - finalState
     return MLX.sqrt((diff * diff).sum())
 }
 
 private func sensorimotorMassAndCentroidArrays(
     _ finalState: MLXArray,
     rules: SensorimotorRuleSpaceConfig
 ) -> (mass: MLXArray, centroidX: MLXArray, centroidY: MLXArray) {
     let (X, Y) = sensorimotorCoordinates(rules)
     let mass = finalState.sum()
     let denom = mass + MLXArray(1e-10)
     let centroidX = (X * finalState).sum() / denom
     let centroidY = (Y * finalState).sum() / denom
     return (mass, centroidX, centroidY)
 }
 
 private func sensorimotorCollapseProxy(
     finalState: MLXArray,
     training: SensorimotorTrainingConfig,
     rules: SensorimotorRuleSpaceConfig
 ) -> MLXArray {
     let (_, centroidX, centroidY) = sensorimotorMassAndCentroidArrays(finalState, rules: rules)
     let (X, Y) = sensorimotorCoordinates(rules)
     let dx = (X - centroidX) / MLXArray(training.goalMask.normalizer)
     let dy = (Y - centroidY) / MLXArray(training.goalMask.normalizer)
     let D = MLX.sqrt(dx * dx + dy * dy)
     let mask =
         (D .< MLXArray(training.goalMask.innerRadius)).asType(.float32) * MLXArray(training.goalMask.innerWeight) +
         (D .< MLXArray(training.goalMask.outerRadius)).asType(.float32) * MLXArray(training.goalMask.outerWeight)
     let diff = finalState - MLXArray(training.goalMask.amplitude) * mask
     return MLX.sqrt((diff * diff).sum()) / MLXArray(training.goalMask.collapseProxyNormalizer)
 }
 
 private func sensorimotorEmbedding(
     finalState: MLXArray,
     training: SensorimotorTrainingConfig,
     rules: SensorimotorRuleSpaceConfig
 ) -> SensorimotorGoal {
     let (mass, centroidX, centroidY) = sensorimotorMassAndCentroidArrays(finalState, rules: rules)
     let collapse = sensorimotorCollapseProxy(finalState: finalState, training: training, rules: rules).item(Float.self)
     let massScalar = mass.item(Float.self)
     var goal = SensorimotorGoal(
         collapse: collapse,
         centroidX: centroidX.item(Float.self) / Float(rules.grid.sx),
         centroidY: centroidY.item(Float.self) / Float(rules.grid.sy)
     )
     if massScalar < 1e-4 {
         goal = SensorimotorGoal(collapse: collapse, centroidX: goal.centroidX - 10, centroidY: goal.centroidY - 10)
     }
     return goal
 }
 
 private func sensorimotorInitializationState(
     candidate: SensorimotorLearnableState,
     rules: SensorimotorRuleSpaceConfig,
     perturbations: SensorimotorPerturbations,
     rng: inout SeededRandomNumberGenerator
 ) -> MLXArray {
     var patch = candidate.initialization
     if let scale = perturbations.scale, scale > 0, abs(scale - 1) > 1e-6 {
         let scaled = sensorimotorScalePatch(
             patch.asArray(Float.self),
             width: patch.shape[1],
             height: patch.shape[0],
             factor: scale
         )
         patch = MLXArray(scaled.values).reshaped([scaled.height, scaled.width])
     }
 
     if let rate = perturbations.initNoiseRate, let std = perturbations.initNoiseStd, std > 0 {
         var noise = [Float](repeating: 0, count: patch.size)
         for index in 0..<noise.count where Float.random(in: 0...1, using: &rng) <= rate {
             noise[index] = sensorimotorGaussian(std: std, rng: &rng)
         }
         patch = MLX.clip(
             patch + MLXArray(noise).reshaped(patch.shape),
             min: MLXArray(0.0),
             max: MLXArray(1.0)
         )
     }
 
     let state = MLX.zeros([rules.grid.sx, rules.grid.sy])
     let rows = patch.shape[0]
     let cols = patch.shape[1]
     let originX = max(0, min(rules.grid.sx - rows, rules.initialization.origin[0]))
     let originY = max(0, min(rules.grid.sy - cols, rules.initialization.origin[1]))
     state[originX..<(originX + rows), originY..<(originY + cols)] = patch
     return state
 }
 
 private struct ScaledPatch {
     let values: [Float]
     let width: Int
     let height: Int
 }
 
 private func sensorimotorScalePatch(
     _ values: [Float],
     width: Int,
     height: Int,
     factor: Float
 ) -> ScaledPatch {
     let newWidth = max(1, Int(round(Float(width) * factor)))
     let newHeight = max(1, Int(round(Float(height) * factor)))
     var out = [Float](repeating: 0, count: newWidth * newHeight)
     for row in 0..<newHeight {
         let sourceY = (Float(row) + 0.5) / factor - 0.5
         let y0 = max(0, min(height - 1, Int(floor(sourceY))))
         let y1 = max(0, min(height - 1, y0 + 1))
         let wy = sourceY - Float(y0)
         for col in 0..<newWidth {
             let sourceX = (Float(col) + 0.5) / factor - 0.5
             let x0 = max(0, min(width - 1, Int(floor(sourceX))))
             let x1 = max(0, min(width - 1, x0 + 1))
             let wx = sourceX - Float(x0)
             let v00 = values[y0 * width + x0]
             let v01 = values[y0 * width + x1]
             let v10 = values[y1 * width + x0]
             let v11 = values[y1 * width + x1]
             let top = v00 * (1 - wx) + v01 * wx
             let bottom = v10 * (1 - wx) + v11 * wx
             out[row * newWidth + col] = top * (1 - wy) + bottom * wy
         }
     }
     return ScaledPatch(values: out, width: newWidth, height: newHeight)
 }
 
 private func sensorimotorShiftObstacleField(
     _ field: MLXArray,
     speed: Float,
     step: Int
 ) -> MLXArray {
     guard speed > 0 else { return field }
     let shift: Int
     if speed < 1 {
         let interval = max(1, Int(round(1 / speed)))
         shift = step % interval == 0 ? 1 : 0
     } else {
         shift = max(1, Int(speed.rounded()))
     }
     guard shift > 0 else { return field }
     return MLX.roll(field, shift: -shift, axis: 1)
 }
 
 private func sensorimotorStepOnce(
     previous: MLXArray,
     obstacleField: MLXArray,
     params: SensorimotorLearnableState,
     rules: SensorimotorRuleSpaceConfig,
     perturbations: SensorimotorPerturbations,
     rng: inout SeededRandomNumberGenerator
 ) -> MLXArray {
     let next = sensorimotorRolloutStep(state: previous, obstacleField: obstacleField, params: params, rules: rules)
     var update = next - previous
 
     if let rate = perturbations.updateMaskRate, rate < 1 {
         var maskValues = [Float](repeating: 0, count: previous.size)
         for index in 0..<maskValues.count {
             maskValues[index] = Float.random(in: 0...1, using: &rng) < rate ? 1 : 0
         }
         update = update * MLXArray(maskValues).reshaped(previous.shape)
     }
 
     if let rate = perturbations.updateNoiseRate, let std = perturbations.updateNoiseStd, rate > 0, std > 0 {
         var noiseValues = [Float](repeating: 0, count: previous.size)
         for index in 0..<noiseValues.count where Float.random(in: 0...1, using: &rng) < rate {
             noiseValues[index] = sensorimotorGaussian(std: std, rng: &rng)
         }
         update = update + MLXArray(noiseValues).reshaped(previous.shape)
     }
 
     return MLX.clip(previous + update, min: MLXArray(0.0), max: MLXArray(1.0))
 }
 
 private func sensorimotorRollout(
     state: SensorimotorLearnableState,
     obstacleField: MLXArray,
     steps: Int,
     rules: SensorimotorRuleSpaceConfig,
     perturbations: SensorimotorPerturbations,
     perturbUntilStep: Int,
     rng: inout SeededRandomNumberGenerator
 ) -> SensorimotorTrace {
     var current = sensorimotorInitializationState(candidate: state, rules: rules, perturbations: perturbations, rng: &rng)
     var masses: [Float] = []
     var centers: [(Float, Float)?] = []
     masses.reserveCapacity(steps)
     centers.reserveCapacity(steps)
 
     let initialStats = sensorimotorMassAndCenter(current, rules: rules)
     masses.append(initialStats.mass)
     centers.append(initialStats.center)
 
     for step in 1..<steps {
         let dynamicObstacle = sensorimotorShiftObstacleField(
             obstacleField,
             speed: step <= perturbUntilStep ? (perturbations.obstacleSpeed ?? 0) : 0,
             step: step
         )
         if step <= perturbUntilStep, let maskRate = perturbations.updateMaskRate, maskRate > 1 {
             var fractional = maskRate
             while fractional > 1 {
                 current = sensorimotorStepOnce(
                     previous: current,
                     obstacleField: dynamicObstacle,
                     params: state,
                     rules: rules,
                     perturbations: SensorimotorPerturbations(updateMaskRate: 1.0),
                     rng: &rng
                 )
                 fractional -= 1
             }
             current = sensorimotorStepOnce(
                 previous: current,
                 obstacleField: dynamicObstacle,
                 params: state,
                 rules: rules,
                 perturbations: SensorimotorPerturbations(
                     updateMaskRate: fractional,
                     updateNoiseStd: perturbations.updateNoiseStd,
                     updateNoiseRate: perturbations.updateNoiseRate
                 ),
                 rng: &rng
             )
         } else {
             let applied = step <= perturbUntilStep ? perturbations : SensorimotorPerturbations()
             current = sensorimotorStepOnce(
                 previous: current,
                 obstacleField: dynamicObstacle,
                 params: state,
                 rules: rules,
                 perturbations: applied,
                 rng: &rng
             )
         }
         let stats = sensorimotorMassAndCenter(current, rules: rules)
         masses.append(stats.mass)
         centers.append(stats.center)
     }
 
     return SensorimotorTrace(masses: masses, centers: centers, finalState: current)
 }
 
 private func sensorimotorMassAndCenter(
     _ state: MLXArray,
     rules: SensorimotorRuleSpaceConfig
 ) -> (mass: Float, center: (Float, Float)?) {
     let flat = state.asArray(Float.self)
     var mass: Float = 0
     var rowWeighted: Float = 0
     var colWeighted: Float = 0
     for row in 0..<rules.grid.sx {
         for col in 0..<rules.grid.sy {
             let value = flat[row * rules.grid.sy + col]
             mass += value
             rowWeighted += Float(row) * value
             colWeighted += Float(col) * value
         }
     }
     if mass <= 1e-6 {
         return (mass, nil)
     }
     return (mass, (rowWeighted / mass, colWeighted / mass))
 }
 
 private func sensorimotorSampleLearnableState(
     rules: SensorimotorRuleSpaceConfig,
     rng: inout SeededRandomNumberGenerator
 ) -> SensorimotorLearnableState {
     let kernelCount = rules.learnableRules.count
     let bumpCount = rules.learnableRules.bumpsPerKernel
     let initializationCount = rules.initialization.size * rules.initialization.size
 
     let T = MLXArray(sensorimotorUniform(range: [rules.learnableRules.sharedT.low, rules.learnableRules.sharedT.high], rng: &rng))
     let R = MLXArray(sensorimotorUniform(range: [rules.learnableRules.sharedR.low, rules.learnableRules.sharedR.high], rng: &rng))
     let r = MLXArray((0..<kernelCount).map { _ in sensorimotorUniform(range: [rules.learnableRules.r.low, rules.learnableRules.r.high], rng: &rng) })
     let a = MLXArray(
         (0..<(kernelCount * bumpCount)).map { _ in sensorimotorUniform(range: [rules.learnableRules.a.low, rules.learnableRules.a.high], rng: &rng) }
     ).reshaped([kernelCount, bumpCount])
     let b = MLXArray(
         (0..<(kernelCount * bumpCount)).map { _ in sensorimotorUniform(range: [rules.learnableRules.b.low, rules.learnableRules.b.high], rng: &rng) }
     ).reshaped([kernelCount, bumpCount])
     let w = MLXArray(
         (0..<(kernelCount * bumpCount)).map { _ in sensorimotorUniform(range: [rules.learnableRules.w.low, rules.learnableRules.w.high], rng: &rng) }
     ).reshaped([kernelCount, bumpCount])
     let mu = MLXArray((0..<kernelCount).map { _ in sensorimotorUniform(range: [rules.learnableRules.mu.low, rules.learnableRules.mu.high], rng: &rng) })
     let sigma = MLXArray((0..<kernelCount).map { _ in sensorimotorUniform(range: [rules.learnableRules.sigma.low, rules.learnableRules.sigma.high], rng: &rng) })
     let h = MLXArray((0..<kernelCount).map { _ in
         sensorimotorUniform(range: [rules.learnableRules.h.low, rules.learnableRules.h.high], rng: &rng) * rules.initialization.historyInitHScale
     })
     let initialization = MLXArray((0..<initializationCount).map { _ in
         sensorimotorUniform(range: rules.initialization.valueRange, rng: &rng)
     }).reshaped([rules.initialization.size, rules.initialization.size])
 
     return SensorimotorLearnableState(arrays: [T, R, r, a, b, w, mu, sigma, h, initialization])
 }
 
 private func sensorimotorClamp(
     _ state: SensorimotorLearnableState,
     rules: SensorimotorRuleSpaceConfig
 ) -> SensorimotorLearnableState {
     SensorimotorLearnableState(arrays: [
         MLX.clip(state.T, min: MLXArray(rules.learnableRules.sharedT.low), max: MLXArray(rules.learnableRules.sharedT.high)),
         MLX.clip(state.R, min: MLXArray(rules.learnableRules.sharedR.low), max: MLXArray(rules.learnableRules.sharedR.high)),
         MLX.clip(state.r, min: MLXArray(rules.learnableRules.r.low), max: MLXArray(rules.learnableRules.r.high)),
         MLX.clip(state.a, min: MLXArray(rules.learnableRules.a.low), max: MLXArray(rules.learnableRules.a.high)),
         MLX.clip(state.b, min: MLXArray(rules.learnableRules.b.low), max: MLXArray(rules.learnableRules.b.high)),
         MLX.clip(state.w, min: MLXArray(rules.learnableRules.w.low), max: MLXArray(rules.learnableRules.w.high)),
         MLX.clip(state.mu, min: MLXArray(rules.learnableRules.mu.low), max: MLXArray(rules.learnableRules.mu.high)),
         MLX.clip(state.sigma, min: MLXArray(rules.learnableRules.sigma.low), max: MLXArray(rules.learnableRules.sigma.high)),
         MLX.clip(state.h, min: MLXArray(rules.learnableRules.h.low), max: MLXArray(rules.learnableRules.h.high)),
         MLX.clip(state.initialization, min: MLXArray(rules.initialization.valueRange[0]), max: MLXArray(rules.initialization.valueRange[1]))
     ])
 }
 
 private func sensorimotorMutatedState(
     source: SensorimotorLearnableState,
     rules: SensorimotorRuleSpaceConfig,
     training: SensorimotorTrainingConfig,
     rng: inout SeededRandomNumberGenerator
 ) -> (state: SensorimotorLearnableState, mutated: Bool, mutationRollouts: Int) {
     var rollouts = 0
     let sigmaValues = source.sigma.asArray(Float.self)
     let activeMask = sigmaValues.map { sigma in
         sigma > training.mutation.activeSigmaThreshold &&
             Float.random(in: 0...1, using: &rng) < training.mutation.activeKernelMutationProbability
     }
 
     for _ in 0..<64 {
         var candidate = source
         candidate.T = source.T + MLXArray(sensorimotorGaussian(std: training.mutation.TStd, rng: &rng))
         candidate.R = source.R + MLXArray(sensorimotorGaussian(std: training.mutation.RStd, rng: &rng))
 
         func mutateVector(_ sourceVector: MLXArray, std: Float) -> MLXArray {
             let values = sourceVector.asArray(Float.self)
             var mutated = values
             for index in mutated.indices where activeMask[min(index, activeMask.count - 1)] {
                 mutated[index] += sensorimotorGaussian(std: std, rng: &rng)
             }
             return MLXArray(mutated).reshaped(sourceVector.shape)
         }
         func mutateMatrix(_ sourceMatrix: MLXArray, std: Float) -> MLXArray {
             let shape = sourceMatrix.shape
             let rows = shape[0]
             let cols = shape[1]
             let flat = sourceMatrix.asArray(Float.self)
             var mutated = flat
             for row in 0..<rows where activeMask[row] {
                 for col in 0..<cols {
                     mutated[row * cols + col] += sensorimotorGaussian(std: std, rng: &rng)
                 }
             }
             return MLXArray(mutated).reshaped(shape)
         }
 
         candidate.r = mutateVector(source.r, std: training.mutation.rStd)
         candidate.a = mutateMatrix(source.a, std: training.mutation.aStd)
         candidate.b = mutateMatrix(source.b, std: training.mutation.bStd)
         candidate.w = mutateMatrix(source.w, std: training.mutation.wStd)
         candidate.mu = mutateVector(source.mu, std: training.mutation.muStd)
         candidate.sigma = mutateVector(source.sigma, std: training.mutation.sigmaStd)
         candidate.h = mutateVector(source.h, std: training.mutation.hStd)
         candidate = sensorimotorClamp(candidate, rules: rules)
 
         let zeroObstacle = MLX.zeros([rules.grid.sx, rules.grid.sy])
         let trace = sensorimotorRollout(
             state: candidate,
             obstacleField: zeroObstacle,
             steps: training.rolloutSteps,
             rules: rules,
             perturbations: SensorimotorPerturbations(),
             perturbUntilStep: training.rolloutSteps - 1,
             rng: &rng
         )
         rollouts += 1
         let reached = sensorimotorEmbedding(finalState: trace.finalState, training: training, rules: rules)
         if (trace.masses.last ?? 0) > training.mutation.collapseMassMin,
             reached.collapse <= training.mutation.collapseMax
         {
             return (candidate, true, rollouts)
         }
     }
 
     return (source, false, rollouts)
 }
 
 private func sensorimotorOptimizeTowardGoal(
     initialState: SensorimotorLearnableState,
     goal: SensorimotorGoal,
     rules: SensorimotorRuleSpaceConfig,
     training: SensorimotorTrainingConfig,
     mutated: Bool,
     rng: inout SeededRandomNumberGenerator
 ) -> SensorimotorGradientResult {
     var state = initialState
     state = sensorimotorClamp(state, rules: rules)
     var optimizer = SensorimotorAdam(
         state: state,
         ruleLr: training.optimization.ruleLr,
         initLr: training.optimization.initializationLr,
         betas: training.optimization.betas,
         eps: training.optimization.eps
     )
     let gradientSteps = mutated ? training.optimization.stepsMutated : training.optimization.stepsUnmutated
     var lastLoss: Float = .infinity
     var lastDead = false
 
     for _ in 0..<gradientSteps {
         let obstacle = sensorimotorRandomObstacleField(
             rules: rules,
             count: rules.searchEnvironment.obstacleCount,
             radius: rules.searchEnvironment.obstacleRadius,
             forcedCenter: nil,
             rng: &rng
         )
         let objectiveForObstacle = valueAndGrad { (arrays: [MLXArray]) -> [MLXArray] in
             let learnable = SensorimotorLearnableState(arrays: arrays)
             var localRng = SeededRandomNumberGenerator(seed: 0)
             let trace = sensorimotorRollout(
                 state: learnable,
                 obstacleField: obstacle.field,
                 steps: training.rolloutSteps,
                 rules: rules,
                 perturbations: SensorimotorPerturbations(),
                 perturbUntilStep: training.rolloutSteps - 1,
                 rng: &localRng
             )
             return [sensorimotorGoalLoss(finalState: trace.finalState, goal: goal, training: training, rules: rules)]
         }
         let (value, gradients) = objectiveForObstacle(state.arrays)
         optimizer.apply(state: &state, gradients: gradients)
         state = sensorimotorClamp(state, rules: rules)
         MLX.eval(state.arrays + value)
         lastLoss = value[0].item(Float.self)
 
         let aliveTrace = sensorimotorRollout(
             state: state,
             obstacleField: obstacle.field,
             steps: training.rolloutSteps,
             rules: rules,
             perturbations: SensorimotorPerturbations(),
             perturbUntilStep: training.rolloutSteps - 1,
             rng: &rng
         )
         let dead = (aliveTrace.masses.last ?? 0) < training.mutation.collapseMassMin
         if dead && lastDead {
             break
         }
         lastDead = dead
     }
 
     var evalRng = rng
     let evalTrace = sensorimotorRollout(
         state: state,
         obstacleField: MLX.zeros([rules.grid.sx, rules.grid.sy]),
         steps: training.rolloutSteps,
         rules: rules,
         perturbations: SensorimotorPerturbations(),
         perturbUntilStep: training.rolloutSteps - 1,
         rng: &evalRng
     )
     let reached = sensorimotorEmbedding(finalState: evalTrace.finalState, training: training, rules: rules)
     return SensorimotorGradientResult(
         state: state,
         loss: lastLoss,
         reached: reached,
         steps: gradientSteps,
         gradientRollouts: gradientSteps
     )
 }
 
 private func sensorimotorArchiveEvaluation(
     state: SensorimotorLearnableState,
     rules: SensorimotorRuleSpaceConfig,
     training: SensorimotorTrainingConfig,
     rng: inout SeededRandomNumberGenerator
 ) -> (reached: SensorimotorGoal, traces: [SensorimotorTrace]) {
     var traces: [SensorimotorTrace] = []
     traces.reserveCapacity(training.evaluationAfterStep.rollouts)
     var embeddings: [SensorimotorGoal] = []
     embeddings.reserveCapacity(training.evaluationAfterStep.rollouts)
 
     for _ in 0..<training.evaluationAfterStep.rollouts {
         let obstacle = sensorimotorRandomObstacleField(
             rules: rules,
             count: rules.searchEnvironment.obstacleCount,
             radius: rules.searchEnvironment.obstacleRadius,
             forcedCenter: nil,
             rng: &rng
         )
         let trace = sensorimotorRollout(
             state: state,
             obstacleField: obstacle.field,
             steps: training.rolloutSteps,
             rules: rules,
             perturbations: SensorimotorPerturbations(),
             perturbUntilStep: training.rolloutSteps - 1,
             rng: &rng
         )
         traces.append(trace)
         if (trace.masses.last ?? 0) < training.mutation.collapseMassMin {
             return (SensorimotorGoal(collapse: 10, centroidX: -10, centroidY: -10), traces)
         }
         embeddings.append(sensorimotorEmbedding(finalState: trace.finalState, training: training, rules: rules))
     }
 
     let inv = 1 / Float(max(embeddings.count, 1))
     let mean = embeddings.reduce(SensorimotorGoal(collapse: 0, centroidX: 0, centroidY: 0)) { partial, next in
         SensorimotorGoal(
             collapse: partial.collapse + next.collapse * inv,
             centroidX: partial.centroidX + next.centroidX * inv,
             centroidY: partial.centroidY + next.centroidY * inv
         )
     }
     return (mean, traces)
 }
 
 private func sensorimotorSampleGoal(
     explorationIndex: Int,
     history: [SensorimotorHistoryRecord],
     training: SensorimotorTrainingConfig,
     rng: inout SeededRandomNumberGenerator
 ) -> SensorimotorGoal {
     if explorationIndex < training.goalSampling.warmupSteps {
         return SensorimotorGoal(
             collapse: training.goalSampling.collapseGoalMean,
             centroidX: training.goalSampling.warmupStart[0] + Float(explorationIndex) * training.goalSampling.warmupDelta[0],
             centroidY: training.goalSampling.warmupStart[1] + Float(explorationIndex) * training.goalSampling.warmupDelta[1]
         )
     }
 
     let validReached = history.map(\.entry.reached)
     var target = SensorimotorGoal(collapse: 10, centroidX: -10, centroidY: -10)
     var closeCount = 0
     var veryCloseCount = Int.max
     while closeCount < training.goalSampling.minCloseNeighbors || veryCloseCount > training.goalSampling.maxVeryCloseNeighbors {
         let collapse = training.goalSampling.collapseGoalMean + sensorimotorGaussian(std: training.goalSampling.collapseGoalJitterStd, rng: &rng)
         if Float.random(in: 0...1, using: &rng) < training.goalSampling.bestGoalProbability,
             let best = validReached
                 .filter({ $0.collapse <= training.sourceSelection.collapseMax && $0.centroidX > -8 && $0.centroidY > -8 })
                 .min(by: { $0.centroidY < $1.centroidY })
         {
             target = SensorimotorGoal(
                 collapse: collapse,
                 centroidX: best.centroidX + sensorimotorUniform(range: training.goalSampling.bestGoalXOffset, rng: &rng),
                 centroidY: best.centroidY + sensorimotorUniform(range: training.goalSampling.bestGoalYOffset, rng: &rng)
             )
         } else if Float.random(in: 0...1, using: &rng) < training.goalSampling.randomFarProbability {
             target = SensorimotorGoal(
                 collapse: collapse,
                 centroidX: sensorimotorUniform(range: training.goalSampling.farXRange, rng: &rng),
                 centroidY: sensorimotorUniform(range: training.goalSampling.farYRange, rng: &rng)
             )
         } else {
             target = SensorimotorGoal(
                 collapse: collapse,
                 centroidX: sensorimotorUniform(range: training.goalSampling.broadXRange, rng: &rng),
                 centroidY: sensorimotorUniform(range: training.goalSampling.broadYRange, rng: &rng)
             )
         }
         let distances = validReached.map { sensorimotorGoalDistance(target, $0) }
         closeCount = distances.filter { $0 < training.goalSampling.closeDistance }.count
         veryCloseCount = distances.filter { $0 < training.goalSampling.veryCloseDistance }.count
     }
     return target
 }
 
 private func sensorimotorSourceIndex(
     for goal: SensorimotorGoal,
     history: [SensorimotorHistoryRecord],
     training: SensorimotorTrainingConfig
 ) -> Int {
     var bestIndex = 0
     var bestDistance = Float.greatestFiniteMagnitude
     for (index, record) in history.enumerated() {
         let reached = record.entry.reached
         if reached.collapse > training.sourceSelection.collapseMax || reached.centroidX < -8 || reached.centroidY < -8 {
             continue
         }
         let distance = sensorimotorGoalDistance(goal, reached)
         if distance < bestDistance {
             bestDistance = distance
             bestIndex = index
         }
     }
     return bestIndex
 }
 
 private func sensorimotorRandomObstacleField(
     rules: SensorimotorRuleSpaceConfig,
     count: Int,
     radius: Int,
     forcedCenter: (Float, Float)?,
     rng: inout SeededRandomNumberGenerator
 ) -> SensorimotorObstacleBatch {
     let sx = rules.grid.sx
     let sy = rules.grid.sy
     var field = [Float](repeating: 0, count: sx * sy)
 
     let randomColRange: ClosedRange<Int>
     if rules.searchEnvironment.leftHalfClear {
         randomColRange = max(0, sy / 2)...max(0, sy - 1)
     } else {
         randomColRange = 0...max(0, sy / 2 - 1)
     }
 
     func stamp(centerRow: Int, centerCol: Int) {
         let rowLo = max(0, centerRow - radius)
         let rowHi = min(sx - 1, centerRow + radius)
         let colLo = max(0, centerCol - radius)
         let colHi = min(sy - 1, centerCol + radius)
         let radiusSquared = radius * radius
         for row in rowLo...rowHi {
             for col in colLo...colHi {
                 let dr = row - centerRow
                 let dc = col - centerCol
                 if dr * dr + dc * dc <= radiusSquared {
                     field[row * sy + col] = 1
                 }
             }
         }
     }
 
     if count > 0 {
         for _ in 0..<count {
             let centerRow = Int.random(in: 0..<(sx), using: &rng)
             let centerCol = Int.random(in: randomColRange, using: &rng)
             stamp(centerRow: centerRow, centerCol: centerCol)
         }
     }
     if let forcedCenter {
         stamp(centerRow: Int(forcedCenter.0.rounded()), centerCol: Int(forcedCenter.1.rounded()))
     }
 
     if rules.searchEnvironment.clearInitialization {
         let rows = rules.initialization.size
         let cols = rules.initialization.size
         let pad = rules.searchEnvironment.clearInitializationRadius
         let rowLo = max(0, rules.initialization.origin[0] - pad)
         let rowHi = min(sx - 1, rules.initialization.origin[0] + rows + pad)
         let colLo = max(0, rules.initialization.origin[1] - pad)
         let colHi = min(sy - 1, rules.initialization.origin[1] + cols + pad)
         for row in rowLo...rowHi {
             for col in colLo...colHi {
                 if row < sx && col < sy {
                     field[row * sy + col] = 0
                 }
             }
         }
     }
 
     return SensorimotorObstacleBatch(
         field: MLXArray(field).reshaped([sx, sy]),
         center: forcedCenter
     )
 }
 
 private func sensorimotorMean(_ values: ArraySlice<Float>) -> Float {
     guard !values.isEmpty else { return 0 }
     return values.reduce(0, +) / Float(values.count)
 }
 
 private func sensorimotorSpeed(
     centers: [(Float, Float)?],
     start: Int
 ) -> Float {
     guard centers.count >= 2 else { return 0 }
     var total: Float = 0
     var count = 0
     for index in max(1, start)..<centers.count {
         guard let previous = centers[index - 1], let current = centers[index] else { continue }
         let dr = current.0 - previous.0
         let dc = current.1 - previous.1
         total += sqrt(dr * dr + dc * dc)
         count += 1
     }
     return count > 0 ? total / Float(count) : 0
 }
 
 private func sensorimotorMaxDistance(
     centers: [(Float, Float)?],
     end: Int
 ) -> Float {
     guard let origin = centers.first ?? nil else { return 0 }
     var best: Float = 0
     for center in centers.prefix(min(end, centers.count)) {
         guard let center else { continue }
         let dr = center.0 - origin.0
         let dc = center.1 - origin.1
         best = max(best, sqrt(dr * dr + dc * dc))
     }
     return best
 }
 
 private func sensorimotorConnected(
     finalState: MLXArray,
     threshold: Float
 ) -> Bool {
     let metrics = computeComponentMetricsBatch(
         materialized: materializeMassBatch(finalState),
         threshold: threshold,
         useTorus: false
     )
     return (metrics.count.first ?? 0) < 2
 }
 
 private func sensorimotorAgencySummary(
     trace: SensorimotorTrace,
     state: SensorimotorLearnableState,
     rules: SensorimotorRuleSpaceConfig,
     evaluation: SensorimotorEvaluationConfig
 ) -> SensorimotorAgencySummary {
     let finalMass = trace.masses.last ?? 0
     let prefilterPassed = finalMass > evaluation.prefilter.finalMassMin && finalMass < evaluation.prefilter.finalMassMax
     let sliceA = trace.masses[evaluation.agency.massWindowA[0]..<min(evaluation.agency.massWindowA[1], trace.masses.count)]
     let sliceB = trace.masses[evaluation.agency.massWindowB[0]..<min(evaluation.agency.massWindowB[1], trace.masses.count)]
     let massRatio = sensorimotorMean(sliceB) / max(sensorimotorMean(sliceA), 1e-6)
     let connected = sensorimotorConnected(finalState: trace.finalState, threshold: evaluation.agency.connectivityThreshold)
     let maxDistance = sensorimotorMaxDistance(centers: trace.centers, end: evaluation.moving.windowEnd)
     let speed = sensorimotorSpeed(centers: trace.centers, start: evaluation.moving.speedStart)
     let agencyPassed =
         finalMass > evaluation.agency.finalMassMin &&
         finalMass < evaluation.agency.finalMassMax &&
         massRatio < evaluation.agency.maxMassRatio &&
         connected
     let movingPassed = maxDistance > evaluation.moving.distanceThreshold
     return SensorimotorAgencySummary(
         prefilterPassed: prefilterPassed,
         agencyPassed: agencyPassed,
         movingPassed: movingPassed,
         finalMass: finalMass,
         massRatio: massRatio,
         connected: connected,
         maxDistanceWithinWindow: maxDistance,
         speedNoObstacles: speed
     )
 }
 
 private func sensorimotorBasicObstacleEvaluation(
     state: SensorimotorLearnableState,
     nominalTrace: SensorimotorTrace,
     rules: SensorimotorRuleSpaceConfig,
     evaluation: SensorimotorEvaluationConfig,
     rng: inout SeededRandomNumberGenerator
 ) -> (robustness: Float, speed: Float) {
     let referenceIndex = min(evaluation.basicObstacleTest.forcedObstacleReferenceStep, nominalTrace.centers.count - 1)
     let forcedCenter = evaluation.basicObstacleTest.forcedObstacleOnNominalTrajectory ? nominalTrace.centers[referenceIndex] : nil
     var robustCount = 0
     var speedSum: Float = 0
     for _ in 0..<evaluation.basicObstacleTest.rollouts {
         let obstacle = sensorimotorRandomObstacleField(
             rules: rules,
             count: evaluation.basicObstacleTest.randomObstacles,
             radius: evaluation.basicObstacleTest.obstacleRadius,
             forcedCenter: forcedCenter,
             rng: &rng
         )
         let trace = sensorimotorRollout(
             state: state,
             obstacleField: obstacle.field,
             steps: evaluation.basicObstacleTest.rolloutSteps,
             rules: rules,
             perturbations: SensorimotorPerturbations(),
             perturbUntilStep: evaluation.basicObstacleTest.rolloutSteps - 1,
             rng: &rng
         )
         let summary = sensorimotorAgencySummary(trace: trace, state: state, rules: rules, evaluation: evaluation)
         if summary.prefilterPassed && summary.movingPassed {
             robustCount += 1
         }
         speedSum += summary.speedNoObstacles
     }
     let denom = Float(max(evaluation.basicObstacleTest.rollouts, 1))
     return (Float(robustCount) / denom, speedSum / denom)
 }
 
 private func sensorimotorScenarioSweep(
     name: String,
     value: Float,
     state: SensorimotorLearnableState,
     rules: SensorimotorRuleSpaceConfig,
     evaluation: SensorimotorEvaluationConfig,
     perturbations: SensorimotorPerturbations,
     obstacleCount: Int,
     obstacleRadius: Int,
     perturbUntilStep: Int? = nil,
     rng: inout SeededRandomNumberGenerator
 ) throws -> SensorimotorScenarioResult {
     var robustCount = 0
     var speedSum: Float = 0
     for _ in 0..<evaluation.generalization.trialsPerSetting {
         let obstacle = sensorimotorRandomObstacleField(
             rules: rules,
             count: obstacleCount,
             radius: obstacleRadius,
             forcedCenter: nil,
             rng: &rng
         )
         let trace = sensorimotorRollout(
             state: state,
             obstacleField: obstacle.field,
             steps: evaluation.agency.rolloutSteps,
             rules: rules,
             perturbations: perturbations,
             perturbUntilStep: perturbUntilStep ?? (evaluation.agency.rolloutSteps - 1),
             rng: &rng
         )
         let summary = sensorimotorAgencySummary(trace: trace, state: state, rules: rules, evaluation: evaluation)
         if summary.prefilterPassed && summary.movingPassed {
             robustCount += 1
         }
         speedSum += summary.speedNoObstacles
     }
     let denom = Float(max(evaluation.generalization.trialsPerSetting, 1))
     return SensorimotorScenarioResult(
         name: name,
         value: value,
         robustness: Float(robustCount) / denom,
         speed: speedSum / denom
     )
 }
 
 private func sensorimotorBestHistoryIndex(
     history: [SensorimotorHistoryRecord],
     collapseMax: Float
 ) -> Int {
     var bestIndex = history.count - 1
     var bestY = Float.greatestFiniteMagnitude
     for (index, record) in history.enumerated() {
         let reached = record.entry.reached
         guard reached.collapse <= collapseMax, reached.centroidY > -8 else { continue }
         if reached.centroidY < bestY {
             bestY = reached.centroidY
             bestIndex = index
         }
     }
     return bestIndex
 }
 
 private func sensorimotorCandidate(from state: SensorimotorLearnableState) -> SensorimotorCandidate {
     SensorimotorCandidate(
         initialization: sensorimotorMatrix(state.initialization),
         rules: SensorimotorRuleParameters(
             T: state.T.item(Float.self),
             R: state.R.item(Float.self),
             r: state.r.asArray(Float.self),
             a: sensorimotorMatrix(state.a),
             b: sensorimotorMatrix(state.b),
             w: sensorimotorMatrix(state.w),
             mu: state.mu.asArray(Float.self),
             sigma: state.sigma.asArray(Float.self),
             h: state.h.asArray(Float.self)
         )
     )
 }
 
 private func sensorimotorLearnableState(candidate: SensorimotorCandidate) -> SensorimotorLearnableState {
     let initializationRows = candidate.initialization.count
     let initializationCols = candidate.initialization.first?.count ?? 0
     return SensorimotorLearnableState(arrays: [
         MLXArray(candidate.rules.T),
         MLXArray(candidate.rules.R),
         MLXArray(candidate.rules.r),
         MLXArray(candidate.rules.a.flatMap { $0 }).reshaped([candidate.rules.a.count, candidate.rules.a.first?.count ?? 0]),
         MLXArray(candidate.rules.b.flatMap { $0 }).reshaped([candidate.rules.b.count, candidate.rules.b.first?.count ?? 0]),
         MLXArray(candidate.rules.w.flatMap { $0 }).reshaped([candidate.rules.w.count, candidate.rules.w.first?.count ?? 0]),
         MLXArray(candidate.rules.mu),
         MLXArray(candidate.rules.sigma),
         MLXArray(candidate.rules.h),
         MLXArray(candidate.initialization.flatMap { $0 }).reshaped([initializationRows, initializationCols]),
     ])
 }
 
 private func sensorimotorMatrix(_ array: MLXArray) -> [[Float]] {
     let shape = array.shape
     let rows = shape[0]
     let cols = shape[1]
     let flat = array.asArray(Float.self)
     return (0..<rows).map { row in
         Array(flat[(row * cols)..<((row + 1) * cols)])
     }
 }
 
 private func sensorimotorWriteHistoryEntry(
     _ entry: SensorimotorHistoryEntry,
     to handle: FileHandle,
     encoder: JSONEncoder
 ) throws {
     let data = try encoder.encode(entry)
     handle.write(data)
     handle.write("\n".data(using: .utf8)!)
 }
 
 private func sensorimotorScaledObstacleCount(radius: Int) -> Int {
     Int(round(24 * Foundation.pow(10 / Float(max(radius, 1)), 2)))
 }
 
 private func sensorimotorIsAliveForArchive(
     reached: SensorimotorGoal,
     finalMass: Float,
     collapseMax: Float
 ) -> Bool {
     finalMass > 10 && reached.collapse <= collapseMax && reached.centroidX > -8 && reached.centroidY > -8
 }
 
 private func sensorimotorIsSourceSelectable(_ reached: SensorimotorGoal, collapseMax: Float) -> Bool {
     reached.collapse <= collapseMax && reached.centroidX > -8 && reached.centroidY > -8
 }
 
 private func sensorimotorRetainedHistoryRecords(
     configs: SensorimotorLenia2024ConfigBundle,
     history: [SensorimotorHistoryRecord],
     bestIndex: Int
 ) -> [(Int, SensorimotorHistoryRecord)] {
     let retained = history.enumerated().filter { _, record in
         sensorimotorIsSourceSelectable(
             record.entry.reached,
             collapseMax: configs.training.sourceSelection.collapseMax
         )
     }
     if retained.isEmpty {
         guard history.indices.contains(bestIndex) else { return [] }
         return [(bestIndex, history[bestIndex])]
     }
     return retained
 }
 
 private func sensorimotorWriteLibraryIndex(
     configs: SensorimotorLenia2024ConfigBundle,
     history: [SensorimotorHistoryRecord],
     bestIndex: Int,
     bestEvaluation: SensorimotorEvaluationSummary,
     runId: String,
     outputDirectory: URL
 ) throws {
     let exportRecords = sensorimotorRetainedHistoryRecords(
         configs: configs,
         history: history,
         bestIndex: bestIndex
     )
     let configHash = try sensorimotorConfigHash(configs: configs)
     let entries = try exportRecords.map { historyIndex, record -> ResearchLibraryEntry in
         let evaluationPayload = try historyIndex == bestIndex
             ? sensorimotorJSONObject(bestEvaluation)
             : sensorimotorArchiveEvaluationPayload(record.entry)
         let trainingLoss: Any = record.entry.trainingLoss.map { Double($0) } ?? NSNull()
         let archiveSlot = historyIndex
         let stableKey = "\(runId)|\(archiveSlot)"
         let candidate = record.entry.candidate
         let goalDescriptor = record.entry.goal?.vector ?? record.entry.reached.vector
         let metadata: [String: AnyCodable] = try [
             "version": researchMetadataValue(1),
             "mode": researchMetadataValue("sensorimotor-2024"),
             "morphospace_payload": researchMetadataValue("summary_only_metrics_v1"),
             "morphospace_ready": researchMetadataValue(false),
             "canonical_export_available": researchMetadataValue(true),
             "canonical_export_kind": researchMetadataValue("sensorimotor24_paper_replay_bundle_v1"),
             "generation": researchMetadataValue(record.entry.step),
             "goal_descriptor": researchMetadataValue(goalDescriptor),
             "evaluation": researchMetadataValue(evaluationPayload),
             "archive_slot": researchMetadataValue(archiveSlot),
             "candidate": researchMetadataValue(try sensorimotorJSONObject(candidate)),
             "reached": researchMetadataValue(try sensorimotorJSONObject(record.entry.reached)),
             "mutated": researchMetadataValue(record.entry.mutated),
             "optimization_steps": researchMetadataValue(record.entry.optimizationSteps),
             "training_loss": researchMetadataValue(trainingLoss),
             "rollout_counts": researchMetadataValue(try sensorimotorJSONObject(record.entry.rolloutCounts)),
         ]
        return archiveResearchLibraryEntry(
            creature: archivedCreature(
                stableKey: stableKey,
                name: "sensorimotor-\(archiveSlot)",
                ownerId: "sensorimotor-2024",
                genotype: sensorimotorKernelParams(candidate.rules),
                initialCondition: sensorimotorInitConfig(initialization: candidate.initialization, slot: archiveSlot),
                metrics: sensorimotorSimulationMetrics(
                    reached: record.entry.reached,
                    evaluation: historyIndex == bestIndex ? bestEvaluation : nil
                ),
                sweep: [
                    "archive_slot": Double(archiveSlot),
                    "generation": Double(record.entry.step),
                ],
                configHash: configHash
            ),
            runId: runId,
            configHash: configHash,
            sourceMode: "sensorimotor-2024",
            sourceAlgorithm: "imgep",
            researchMetadata: metadata
        )
     }
     _ = try ResearchLibraryWriter.write(entries: entries, runDirectory: outputDirectory)
 }
 
 private func sensorimotorWriteReplayExports(
     configs: SensorimotorLenia2024ConfigBundle,
     history: [SensorimotorHistoryRecord],
     bestIndex: Int,
     runId: String,
     sourceSeed: UInt64,
     outputDirectory: URL
 ) throws {
     let exportRecords = sensorimotorRetainedHistoryRecords(
         configs: configs,
         history: history,
         bestIndex: bestIndex
     )
     guard !exportRecords.isEmpty else { return }
 
     let exportsDirectory = outputDirectory.appendingPathComponent("exports", isDirectory: true)
     let exportedAt = Date()
     let configHash = try sensorimotorConfigHash(configs: configs)

     _ = try writePayloadReplayExportBatch(
        exportRoot: exportsDirectory,
        items: exportRecords
     ) { item in
        let (archiveSlot, record) = item
        let creature = archivedCreature(
            stableKey: "\(runId)|\(archiveSlot)|canonical-export",
             name: "sensorimotor-\(archiveSlot)",
             ownerId: "sensorimotor-2024",
            genotype: sensorimotorKernelParams(record.entry.candidate.rules),
             initialCondition: sensorimotorReplayInitialCondition(
                 candidate: record.entry.candidate,
                 rules: configs.ruleSpace,
                 seed: archiveSlot
             ),
             metrics: sensorimotorSimulationMetrics(
                 reached: record.entry.reached,
                 evaluation: nil
             ),
             sweep: [
                 "archive_slot": Double(archiveSlot),
                 "generation": Double(record.entry.step),
            ],
            configHash: configHash
         )
         let payload = SensorimotorLenia2024ReplayPayload(
             configs: configs,
             archiveSlot: archiveSlot,
             replaySeed: sourceSeed,
             entry: record.entry
         )
         return (
             creature: creature,
             runId: runId,
             campaignId: nil,
             bundleKind: .sensorimotor24PaperReplayBundleV1,
             payload: payload,
             reason: "sensorimotor-2024:imgep",
             score: nil,
             filtersPassed: nil,
             exportedAt: exportedAt
         )
     }
}
 
 private func sensorimotorKernelParams(_ rules: SensorimotorRuleParameters) -> KernelParams {
     KernelParams(
         r: rules.r,
         b: rules.b,
         w: rules.w,
         a: rules.a,
         m: rules.mu,
         s: rules.sigma,
         h: rules.h,
         R: rules.R
     )
 }
 
 private func sensorimotorInitConfig(initialization: [[Float]], slot: Int) -> InitConfig {
     let flattened = initialization.flatMap { $0 }
     let low = flattened.min() ?? 0
     let high = flattened.max() ?? low
     return InitConfig(
         seed: slot,
         patches: [],
         a_uniform: UniformRange(low: low, high: high),
         p_uniform: nil
     )
 }
 
 private func sensorimotorReplayInitialCondition(
     candidate: SensorimotorCandidate,
     rules: SensorimotorRuleSpaceConfig,
     seed: Int
 ) -> InitConfig {
     var rng = SeededRandomNumberGenerator(seed: 0)
     let state = sensorimotorInitializationState(
         candidate: sensorimotorLearnableState(candidate: candidate),
         rules: rules,
         perturbations: SensorimotorPerturbations(),
         rng: &rng
     )
     return InitConfig(
         seed: seed,
         patches: [],
         a_uniform: UniformRange(low: 0, high: 0),
         p_uniform: nil,
         state_patch: InitStatePatchConfig(
             center: [rules.grid.sx / 2, rules.grid.sy / 2],
             width: rules.grid.sx,
             height: rules.grid.sy,
             channels: 1,
             values: state.asArray(Float.self)
         )
     )
 }
 
 private func sensorimotorSimulationMetrics(
     reached: SensorimotorGoal,
     evaluation: SensorimotorEvaluationSummary?
 ) -> SimulationMetrics {
     let finalMass = evaluation?.agency.finalMass ?? 0
     let speed = evaluation?.agency.speedNoObstacles ?? 0
     let displacement = evaluation?.agency.maxDistanceWithinWindow ?? 0
     let occupancyProxy = max(0, min(1, 1 - reached.collapse))
     return SimulationMetrics(
         massMean: finalMass,
         massStd: 0,
         massMin: finalMass,
         massMax: finalMass,
         occupancyMean: occupancyProxy,
         varianceMean: evaluation?.agency.massRatio ?? 0,
         energyMean: speed,
         speedMean: speed,
         pathLength: displacement,
         displacement: displacement,
         sampleCount: 1,
         speedCount: 1,
         gyration: 0,
         centerVelocity: speed,
         velocityX: 0,
         velocityY: 0,
         headingRad: 0,
         isStable: evaluation?.agency.agencyPassed ?? false
     )
 }
 
 public func replaySensorimotorLenia2024Payload(
     _ payload: SensorimotorLenia2024ReplayPayload,
     runId: String,
     configHash: String? = nil
 ) throws -> SensorimotorLenia2024ReplayOutcome {
     var rng = SeededRandomNumberGenerator(seed: payload.replaySeed)
     let state = sensorimotorLearnableState(candidate: payload.entry.candidate)
     let replay = try sensorimotorEvaluate(
         state: state,
         configs: payload.configs,
         rng: &rng
     )
     let initialCondition = sensorimotorReplayInitialCondition(
         candidate: payload.entry.candidate,
         rules: payload.configs.ruleSpace,
         seed: payload.archiveSlot
     )
     let trajectory = sensorimotorReplayTrajectoryMetrics(trace: replay.nominalTrace)
     let massBatch = materializeMassBatch(replay.nominalTrace.finalState)
     let finalSummary = morphospaceFinalSampleSummary(
         materialized: massBatch,
         sampleIndex: 0,
         occupancyThreshold: 0.01,
         useTorus: false
     )
     let moments = computeMomentsBatch(
         materialized: massBatch,
         config: MomentsConfig(enabled: true, threshold: 0.01)
     )
     let components = computeComponentMetricsBatch(
         materialized: massBatch,
         threshold: 0.01,
         useTorus: false
     )
     let fieldVariance = sensorimotorReplayFieldVariance(replay.nominalTrace.finalState.asArray(Float.self))
     let metrics = SimulationMetrics(
         massMean: sensorimotorReplayMean(replay.nominalTrace.masses),
         massStd: sensorimotorReplayStd(replay.nominalTrace.masses),
         massMin: replay.nominalTrace.masses.min() ?? 0,
         massMax: replay.nominalTrace.masses.max() ?? 0,
         occupancyMean: finalSummary.finalOccupancy,
         varianceMean: fieldVariance,
         energyMean: trajectory.speedMean,
         speedMean: trajectory.speedMean,
         pathLength: trajectory.pathLength,
         displacement: trajectory.displacement,
         sampleCount: replay.nominalTrace.masses.count,
         speedCount: trajectory.speedCount,
         gyration: finalSummary.finalGyration,
         centerVelocity: trajectory.centerVelocity,
         velocityX: trajectory.velocityX,
         velocityY: trajectory.velocityY,
         headingRad: trajectory.headingRad,
         isStable: replay.summary.agency.prefilterPassed && replay.summary.agency.agencyPassed,
         survivalSteps: trajectory.survivalSteps,
         hu1: moments.hu.first?[0],
         hu2: moments.hu.first?[1],
         hu3: moments.hu.first?[2],
         hu4: moments.hu.first?[3],
         hu5: moments.hu.first?[4],
         hu6: moments.hu.first?[5],
         hu7: moments.hu.first?[6],
         flusser1: moments.flusser.first?[0],
         flusser2: moments.flusser.first?[1],
         flusser3: moments.flusser.first?[2],
         flusser4: moments.flusser.first?[3],
         momentMass: moments.mass.first,
         momentVolume: moments.volume.first,
         momentDensity: moments.density.first,
         momentAnisotropy: moments.anisotropy.first,
         componentCount: components.count.first,
         largestComponentFraction: components.largestFraction.first,
         largestComponentAnisotropy: components.largestAnisotropy.first
     )
     let morphometrics = Morphometrics.from(metrics: metrics, activity: nil)
     let descriptorBundle = MorphospaceDescriptorBundle(
         symmetryPolicy: "translation_only_v1",
         genotype: morphospaceOpaqueGenotypeDescriptor(
             vector: sensorimotorReplayGenotypeVector(payload.entry.candidate),
             kernelCount: payload.entry.candidate.rules.r.count,
             canonicalizer: "sensorimotor24_candidate_identity_v1"
         ),
         terminal: MorphospaceTerminalDescriptor(
             massChannel: 0,
             borderMode: "wall",
             symmetryPolicy: "translation_only_v1",
             fingerprintResolution: finalSummary.fingerprintResolution,
             fingerprintU8: finalSummary.fingerprintU8,
             angularSymmetry: finalSummary.angularSymmetry,
             fingerprintHash12: finalSummary.fingerprintHash12,
             finalMass: finalSummary.finalMass,
             finalOccupancy: finalSummary.finalOccupancy,
             finalGyration: finalSummary.finalGyration,
             momentMass: moments.mass.first,
             momentVolume: moments.volume.first,
             momentDensity: moments.density.first,
             momentAnisotropy: moments.anisotropy.first,
             componentCount: components.count.first,
             largestComponentFraction: components.largestFraction.first,
             largestComponentAnisotropy: components.largestAnisotropy.first,
             hu1: moments.hu.first?[0],
             hu2: moments.hu.first?[1],
             hu3: moments.hu.first?[2],
             hu4: moments.hu.first?[3],
             hu5: moments.hu.first?[4],
             hu6: moments.hu.first?[5],
             hu7: moments.hu.first?[6],
             flusser1: moments.flusser.first?[0],
             flusser2: moments.flusser.first?[1],
             flusser3: moments.flusser.first?[2],
             flusser4: moments.flusser.first?[3],
             windowMassStd: nil,
             windowOccupancyStd: nil,
             windowGyrationStd: nil,
             isStable: metrics.isStable
         ),
         trajectory: MorphospaceTrajectoryDescriptor(
             recordInterval: 1,
             warmupSteps: 0,
             sampleCount: metrics.sampleCount,
             pathLength: metrics.pathLength,
             displacement: metrics.displacement,
             pathTortuosity: morphometrics.pathTortuosity,
             movementEfficiency: morphometrics.movementEfficiency,
             speedMean: metrics.speedMean,
             centerVelocity: metrics.centerVelocity,
             velocityX: metrics.velocityX,
             velocityY: metrics.velocityY,
             headingRad: metrics.headingRad,
             headingCircularVariance: trajectory.headingCircularVariance,
             accumulatedTurnAbs: trajectory.accumulatedTurnAbs,
             survivalSteps: metrics.survivalSteps,
             activityEacMean: nil,
             activityEanMean: nil,
             activityDiversityMean: nil,
             activitySpeciesMean: nil,
             activitySpeciesMax: nil,
             activitySpeciesStd: nil,
             activityDiversityStd: nil,
             activityEacMax: nil,
             activityEanMax: nil,
             componentSeriesMean: nil,
             componentSeriesStd: nil,
             componentSeriesMax: nil
         )
     )
     let initialConditionFamily = morphospaceInitialConditionFamily(initialCondition)
     let filters = [
         "prefilter_passed": replay.summary.agency.prefilterPassed ? Float(1) : Float(0),
         "agency_passed": replay.summary.agency.agencyPassed ? Float(1) : Float(0),
         "moving_passed": replay.summary.agency.movingPassed ? Float(1) : Float(0),
         "basic_obstacle_robustness": replay.summary.basicObstacleRobustness,
         "basic_obstacle_speed": replay.summary.basicObstacleSpeed,
     ]
     let resultData = materializeReplayResultData(
         seed: payload.archiveSlot,
         initSeed: payload.archiveSlot,
         backend: "sensorimotor24-paper",
         implementation: ImplementationSettings(
             mode: "sensorimotor24-paper",
             border: "wall",
             gradientBoundary: "n/a",
             alphaMode: "n/a",
             kernelProfile: "sensorimotor24_paper_v1",
             flowClip: "n/a"
         ),
         initialConditionFamily: initialConditionFamily,
         descriptorBundle: descriptorBundle,
         score: nil,
         scoreWeights: nil,
         filtersPassed: replay.summary.agency.prefilterPassed && replay.summary.agency.agencyPassed && replay.summary.agency.movingPassed,
         filters: filters,
         metrics: metrics,
         activity: nil,
         params: sensorimotorKernelParams(payload.entry.candidate.rules),
         sweep: [
             "archive_slot": Double(payload.archiveSlot),
             "generation": Double(payload.entry.step),
         ]
     )
     let creature = archivedCreatureFromResult(
         stableKey: "\(runId)|sensorimotor-2024|\(payload.archiveSlot)|replayed",
         name: "sensorimotor-\(payload.archiveSlot)",
         ownerId: "sensorimotor-2024",
         result: resultData,
         initialCondition: initialCondition,
         configHash: configHash,
         sweep: [
             "archive_slot": Double(payload.archiveSlot),
             "generation": Double(payload.entry.step),
         ]
     )
     return SensorimotorLenia2024ReplayOutcome(resultData: resultData, creature: creature)
 }
 
 private func sensorimotorReplayGenotypeVector(_ candidate: SensorimotorCandidate) -> [Float] {
     var vector: [Float] = [candidate.rules.T, candidate.rules.R]
     vector.append(contentsOf: candidate.rules.r)
     vector.append(contentsOf: candidate.rules.a.flatMap { $0 })
     vector.append(contentsOf: candidate.rules.b.flatMap { $0 })
     vector.append(contentsOf: candidate.rules.w.flatMap { $0 })
     vector.append(contentsOf: candidate.rules.mu)
     vector.append(contentsOf: candidate.rules.sigma)
     vector.append(contentsOf: candidate.rules.h)
     vector.append(contentsOf: candidate.initialization.flatMap { $0 })
     return vector
 }
 
 private func sensorimotorReplayFieldVariance(_ values: [Float]) -> Float {
     guard !values.isEmpty else { return 0 }
     let mean = values.reduce(0, +) / Float(values.count)
     var sumSq: Float = 0
     for value in values {
         let delta = value - mean
         sumSq += delta * delta
     }
     return sumSq / Float(values.count)
 }
 
 private func sensorimotorReplayMean(_ values: [Float]) -> Float {
     guard !values.isEmpty else { return 0 }
     return values.reduce(0, +) / Float(values.count)
 }
 
 private func sensorimotorReplayStd(_ values: [Float]) -> Float {
     guard !values.isEmpty else { return 0 }
     if values.count == 1 { return 0 }
     let mean = sensorimotorReplayMean(values)
     var sumSq: Float = 0
     for value in values {
         let delta = value - mean
         sumSq += delta * delta
     }
     return sqrt(sumSq / Float(values.count))
 }
 
 private func sensorimotorReplayTrajectoryMetrics(
     trace: SensorimotorTrace
 ) -> (
     pathLength: Float,
     displacement: Float,
     speedMean: Float,
     speedCount: Int,
     centerVelocity: Float,
     velocityX: Float,
     velocityY: Float,
     headingRad: Float,
     headingCircularVariance: Float?,
     accumulatedTurnAbs: Float?,
     survivalSteps: Int?
 ) {
     var pathLength: Float = 0
     var totalDx: Float = 0
     var totalDy: Float = 0
     var speedCount = 0
     var headings: [Float] = []
     headings.reserveCapacity(max(trace.centers.count - 1, 0))
 
     for index in 1..<trace.centers.count {
         guard let previous = trace.centers[index - 1], let current = trace.centers[index] else { continue }
         let dy = current.0 - previous.0
         let dx = current.1 - previous.1
         let distance = sqrt(dx * dx + dy * dy)
         pathLength += distance
         totalDx += dx
         totalDy += dy
         speedCount += 1
         if distance > 1e-6 {
             headings.append(atan2(dy, dx))
         }
     }
 
     let displacement: Float
     let firstCenter = trace.centers.first.flatMap { $0 }
     let lastCenter = trace.centers.last.flatMap { $0 }
     if let first = firstCenter, let last = lastCenter {
         let dy = last.0 - first.0
         let dx = last.1 - first.1
         displacement = sqrt(dx * dx + dy * dy)
     } else {
         displacement = 0
     }
 
     let velocityX = speedCount > 0 ? totalDx / Float(speedCount) : 0
     let velocityY = speedCount > 0 ? totalDy / Float(speedCount) : 0
     let centerVelocity = sqrt(velocityX * velocityX + velocityY * velocityY)
     let headingRad = headings.last ?? 0
 
     let headingCircularVariance: Float?
     if headings.isEmpty {
         headingCircularVariance = nil
     } else {
         let sinAcc = headings.reduce(Double(0)) { $0 + Double(sin($1)) }
         let cosAcc = headings.reduce(Double(0)) { $0 + Double(cos($1)) }
         let resultant = sqrt(sinAcc * sinAcc + cosAcc * cosAcc) / Double(headings.count)
         headingCircularVariance = Float(max(0, 1 - resultant))
     }
 
     let accumulatedTurnAbs: Float?
     if headings.count < 2 {
         accumulatedTurnAbs = nil
     } else {
         var total: Float = 0
         for index in 1..<headings.count {
             var diff = headings[index] - headings[index - 1]
             while diff > Float.pi { diff -= 2 * Float.pi }
             while diff < -Float.pi { diff += 2 * Float.pi }
             total += abs(diff)
         }
         accumulatedTurnAbs = total
     }
 
     let survivalSteps = trace.masses.lastIndex(where: { $0 > 1e-6 }).map { $0 + 1 }
     return (
         pathLength,
         displacement,
         speedCount > 0 ? pathLength / Float(speedCount) : 0,
         speedCount,
         centerVelocity,
         velocityX,
         velocityY,
         headingRad,
         headingCircularVariance,
         accumulatedTurnAbs,
         survivalSteps
     )
 }
 
 private func sensorimotorArchiveEvaluationPayload(_ entry: SensorimotorHistoryEntry) throws -> Any {
     let trainingLoss: Any = entry.trainingLoss.map { Double($0) } ?? NSNull()
     return [
         "kind": "archive_record",
         "source_selectable": true,
         "reached": try sensorimotorJSONObject(entry.reached),
         "mutated": entry.mutated,
         "optimization_steps": entry.optimizationSteps,
         "training_loss": trainingLoss,
         "rollout_counts": try sensorimotorJSONObject(entry.rolloutCounts),
     ]
 }
 
 private func sensorimotorConfigHash(configs: SensorimotorLenia2024ConfigBundle) throws -> String {
     researchConfigHash([
         ("rule_space", try researchEncodedJSON(configs.ruleSpace)),
         ("training", try researchEncodedJSON(configs.training)),
         ("evaluation", try researchEncodedJSON(configs.evaluation)),
     ])
 }
 
private func sensorimotorJSONObject<T: Encodable>(_ value: T) throws -> Any {
    try JSONSerialization.jsonObject(with: researchEncodedJSON(value))
}
