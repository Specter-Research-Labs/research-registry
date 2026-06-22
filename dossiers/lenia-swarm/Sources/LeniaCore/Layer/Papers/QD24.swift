import DistributedCluster
import Foundation
import Logging
import MLX
 import MLXFFT
 
 public struct LeniaBreeder2024BaseConfig: Codable, Sendable {
     public let paper: String
     public let patternID: String
     public let worldSize: Int
     public let worldScale: Int
     public let nStep: Int
     public let nParamsSize: Int
     public let nCellsSize: Int
 
     enum CodingKeys: String, CodingKey {
         case paper
         case patternID = "pattern_id"
         case worldSize = "world_size"
         case worldScale = "world_scale"
         case nStep = "n_step"
         case nParamsSize = "n_params_size"
         case nCellsSize = "n_cells_size"
     }
 }
 
 public struct LeniaBreeder2024MAPElitesConfig: Codable, Sendable {
     public let algorithm: String
     public let phenotypeSize: Int
     public let centerPhenotype: Bool
     public let recordPhenotype: Bool
     public let nGenerations: Int
     public let logInterval: Int
     public let batchSize: Int
     public let repertoireSize: Int
     public let initialCVTSamples: Int
     public let isoSigma: Float
     public let lineSigma: Float
     public let fitness: String
     public let descriptor: [String]
     public let descriptorMin: [Float]
     public let descriptorMax: [Float]
     public let nKeep: Int
 
     enum CodingKeys: String, CodingKey {
         case algorithm
         case phenotypeSize = "phenotype_size"
         case centerPhenotype = "center_phenotype"
         case recordPhenotype = "record_phenotype"
         case nGenerations = "n_generations"
         case logInterval = "log_interval"
         case batchSize = "batch_size"
         case repertoireSize = "repertoire_size"
         case initialCVTSamples = "n_init_cvt_samples"
         case isoSigma = "iso_sigma"
         case lineSigma = "line_sigma"
         case fitness
         case descriptor
         case descriptorMin = "descriptor_min"
         case descriptorMax = "descriptor_max"
         case nKeep = "n_keep"
     }
 }
 
 public struct LeniaBreeder2024AURORAConfig: Codable, Sendable {
     public let algorithm: String
     public let phenotypeSize: Int
     public let centerPhenotype: Bool
     public let recordPhenotype: Bool
     public let nGenerations: Int
     public let logInterval: Int
     public let batchSize: Int
     public let repertoireSize: Int
     public let isoSigma: Float
     public let lineSigma: Float
     public let fitness: String
     public let secondaryFitness: String?
     public let secondaryFitnessWeight: Float
     public let nKeep: Int
     public let features: Int
     public let hiddenSize: Int
     public let trainRatio: Int
     public let learningRate: Float
     public let autoencoderBatchSize: Int
     public let nKeepAutoencoder: Int
     public let useDataAugmentation: Bool
 
     enum CodingKeys: String, CodingKey {
         case algorithm
         case phenotypeSize = "phenotype_size"
         case centerPhenotype = "center_phenotype"
         case recordPhenotype = "record_phenotype"
         case nGenerations = "n_generations"
         case logInterval = "log_interval"
         case batchSize = "batch_size"
         case repertoireSize = "repertoire_size"
         case isoSigma = "iso_sigma"
         case lineSigma = "line_sigma"
         case fitness
         case secondaryFitness = "secondary_fitness"
         case secondaryFitnessWeight = "secondary_fitness_weight"
         case nKeep = "n_keep"
         case features
         case hiddenSize = "hidden_size"
         case trainRatio = "train_ratio"
         case learningRate = "lr_init_value"
         case autoencoderBatchSize = "ae_batch_size"
         case nKeepAutoencoder = "n_keep_ae"
         case useDataAugmentation = "use_data_augmentation"
     }
 }
 
 public struct LeniaBreeder2024ConfigBundle: Sendable {
     public let configDirectory: URL
     public let base: LeniaBreeder2024BaseConfig
     public let mapElites: LeniaBreeder2024MAPElitesConfig
     public let aurora: LeniaBreeder2024AURORAConfig
 }
 
 public struct LeniaBreeder2024DistributedSpec: Codable, Sendable {
     public let base: LeniaBreeder2024BaseConfig
     public let mapElites: LeniaBreeder2024MAPElitesConfig
     public let pattern: LeniaBreeder2024PatternSpec
     public let specHash: String
 }
 
 public struct LeniaBreeder2024DistributedMAPElitesJob: Codable, Sendable {
     public let id: String
     public let generation: Int
     public let candidateOffset: Int
     public let genotypes: [[Float]]
     public let spec: LeniaBreeder2024DistributedSpec
 }
 
 public struct LeniaBreeder2024DistributedMAPElitesEvaluation: Codable, Sendable {
     public let fitness: Float
     public let descriptor: [Float]
     public let failed: Bool
     public let phenotype: [Float]?
     public let creatureSummary: LeniaBreeder2024CreatureSummary
 }
 
 public struct LeniaBreeder2024DistributedMAPElitesResult: Codable, Sendable {
     public let jobId: String
     public let generation: Int
     public let candidateOffset: Int
     public let workerId: String
     public let durationSeconds: Double
     public let evaluations: [LeniaBreeder2024DistributedMAPElitesEvaluation]
 }
 
 public struct LeniaBreeder2024DistributedWorkerSummary: Codable, Sendable {
     public let workerId: String
     public let hostname: String
 }
 
 public struct LeniaBreeder2024DistributedManifest: Codable, Sendable {
     public let paper: String
     public let algorithm: String
     public let seed: Int
     public let runId: String
     public let controllerId: String
     public let minWorkers: Int
     public let specHash: String
     public let chunkingPolicy: String
     public let workers: [LeniaBreeder2024DistributedWorkerSummary]
 }
 
 public struct LeniaBreeder2024HistoryEntry: Codable, Sendable {
     public let generation: Int
     public let qdScore: Float
     public let coverage: Float
     public let maxFitness: Float
     public let nElites: Int
     public let variance: Float
     public let elapsedSeconds: Double
 
     enum CodingKeys: String, CodingKey {
         case generation
         case qdScore = "qd_score"
         case coverage
         case maxFitness = "max_fitness"
         case nElites = "n_elites"
         case variance
         case elapsedSeconds = "elapsed_seconds"
     }
 }
 
 public struct LeniaBreeder2024AURORADescriptorStats: Codable, Sendable {
     public let count: Int
     public let finiteFitnessCount: Int
     public let failedCount: Int
     public let descriptorNormMean: Float
     public let descriptorNormStd: Float
     public let descriptorAbsMean: Float
     public let dimensionStdMean: Float
     public let nearZeroFraction: Float
 
     enum CodingKeys: String, CodingKey {
         case count
         case finiteFitnessCount = "finite_fitness_count"
         case failedCount = "failed_count"
         case descriptorNormMean = "descriptor_norm_mean"
         case descriptorNormStd = "descriptor_norm_std"
         case descriptorAbsMean = "descriptor_abs_mean"
         case dimensionStdMean = "dimension_std_mean"
         case nearZeroFraction = "near_zero_fraction"
     }
 }
 
 public struct LeniaBreeder2024AURORATrainingStats: Codable, Sendable {
     public let epochs: Int
     public let updates: Int
     public let datasetSize: Int
     public let batchSize: Int
     public let lastReconstructionLoss: Float
     public let lastKLLoss: Float
     public let lastTotalLoss: Float
     public let meanReconstructionLoss: Float
     public let meanKLLoss: Float
     public let meanTotalLoss: Float
 
     enum CodingKeys: String, CodingKey {
         case epochs, updates
         case datasetSize = "dataset_size"
         case batchSize = "batch_size"
         case lastReconstructionLoss = "last_reconstruction_loss"
         case lastKLLoss = "last_kl_loss"
         case lastTotalLoss = "last_total_loss"
         case meanReconstructionLoss = "mean_reconstruction_loss"
         case meanKLLoss = "mean_kl_loss"
         case meanTotalLoss = "mean_total_loss"
     }
 }
 
 public struct LeniaBreeder2024AURORADiagnosticsEntry: Codable, Sendable {
     public let generation: Int
     public let elapsedSeconds: Double
     public let trainingArchiveSize: Int
     public let retrained: Bool
     public let elitesAdded: Int
     public let occupiedCells: Int
     public let coverage: Float
     public let qdScore: Float
     public let maxFitness: Float
     public let occupiedCellsBeforeRebuild: Int?
     public let occupiedCellsAfterRebuild: Int?
     public let batchStats: LeniaBreeder2024AURORADescriptorStats
     public let repertoireStats: LeniaBreeder2024AURORADescriptorStats
     public let trainingStats: LeniaBreeder2024AURORATrainingStats?
 
     enum CodingKeys: String, CodingKey {
         case generation
         case elapsedSeconds = "elapsed_seconds"
         case trainingArchiveSize = "training_archive_size"
         case retrained
         case elitesAdded = "elites_added"
         case occupiedCells = "occupied_cells"
         case coverage
         case qdScore = "qd_score"
         case maxFitness = "max_fitness"
         case occupiedCellsBeforeRebuild = "occupied_cells_before_rebuild"
         case occupiedCellsAfterRebuild = "occupied_cells_after_rebuild"
         case batchStats = "batch_stats"
         case repertoireStats = "repertoire_stats"
         case trainingStats = "training_stats"
     }
 }
 
 public struct LeniaBreeder2024RunSummary: Codable, Sendable {
     public let paper: String
     public let algorithm: String
     public let seed: Int
     public let generations: Int
     public let occupiedCells: Int
     public let qdScore: Float
     public let coverage: Float
     public let maxFitness: Float
     public let variance: Float
     public let patternID: String
 
     enum CodingKeys: String, CodingKey {
         case paper, algorithm, seed, generations, variance
         case occupiedCells = "occupied_cells"
         case qdScore = "qd_score"
         case coverage
         case maxFitness = "max_fitness"
         case patternID = "pattern_id"
     }
 }
 
 public struct LeniaBreeder2024EliteSummary: Codable, Sendable {
     public let cell: Int
     public let generation: Int
     public let centroid: [Float]
     public let descriptor: [Float]
     public let fitness: Float
     public let genotype: [Float]
 
     public init(
         cell: Int,
         generation: Int,
         centroid: [Float],
         descriptor: [Float],
         fitness: Float,
         genotype: [Float]
     ) {
         self.cell = cell
         self.generation = generation
         self.centroid = centroid
         self.descriptor = descriptor
         self.fitness = fitness
         self.genotype = genotype
     }
 
     enum CodingKeys: String, CodingKey {
         case cell
         case generation
         case centroid
         case descriptor
         case fitness
         case genotype
     }
 
     public init(from decoder: Decoder) throws {
         let container = try decoder.container(keyedBy: CodingKeys.self)
         cell = try container.decode(Int.self, forKey: .cell)
         generation = try container.decodeIfPresent(Int.self, forKey: .generation) ?? 0
         centroid = try container.decode([Float].self, forKey: .centroid)
         descriptor = try container.decode([Float].self, forKey: .descriptor)
         fitness = try container.decode(Float.self, forKey: .fitness)
         genotype = try container.decode([Float].self, forKey: .genotype)
     }
 
     public func encode(to encoder: Encoder) throws {
         var container = encoder.container(keyedBy: CodingKeys.self)
         try container.encode(cell, forKey: .cell)
         try container.encode(generation, forKey: .generation)
         try container.encode(centroid, forKey: .centroid)
         try container.encode(descriptor, forKey: .descriptor)
         try container.encode(fitness, forKey: .fitness)
         try container.encode(genotype, forKey: .genotype)
     }
 }
 
 public struct LeniaBreeder2024ResolvedRun: Sendable {
     public let runDirectory: URL
     public let configDirectory: URL?
     public let base: LeniaBreeder2024BaseConfig
     public let mapElites: LeniaBreeder2024MAPElitesConfig
     public let aurora: LeniaBreeder2024AURORAConfig
     public let pattern: LeniaBreeder2024PatternSpec
     public let defaultAlgorithm: String
 }
 
 public struct LeniaBreeder2024EvaluatedElite: Sendable {
     public let elite: LeniaBreeder2024EliteSummary
     public let kernelParams: KernelParams
     public let metrics: SimulationMetrics
     public let summary: LeniaBreeder2024CreatureSummary
 }
 
 public struct LeniaBreeder2024ExpressedSeed: Sendable {
     public let elite: LeniaBreeder2024EliteSummary
     public let algorithm: String
     public let world: WorldState
     public let embryoSize: Int
     public let kernelParams: KernelParams
     public let pattern: LeniaBreeder2024PatternSpec
 
     public init(
         elite: LeniaBreeder2024EliteSummary,
         algorithm: String,
         world: WorldState,
         embryoSize: Int,
         kernelParams: KernelParams,
         pattern: LeniaBreeder2024PatternSpec
     ) {
         self.elite = elite
         self.algorithm = algorithm
         self.world = world
         self.embryoSize = embryoSize
         self.kernelParams = kernelParams
         self.pattern = pattern
     }
 }
 
public struct LeniaBreeder2024ReplayPayload: Codable, Sendable {
     public let paper: String
     public let algorithm: String
     public let base: LeniaBreeder2024BaseConfig
     public let mapElites: LeniaBreeder2024MAPElitesConfig
     public let aurora: LeniaBreeder2024AURORAConfig
     public let pattern: LeniaBreeder2024PatternSpec
     public let elite: LeniaBreeder2024EliteSummary
 
     public init(
         paper: String = "leniabreeder-2024",
         algorithm: String,
         base: LeniaBreeder2024BaseConfig,
         mapElites: LeniaBreeder2024MAPElitesConfig,
         aurora: LeniaBreeder2024AURORAConfig,
         pattern: LeniaBreeder2024PatternSpec,
         elite: LeniaBreeder2024EliteSummary
     ) {
         self.paper = paper
         self.algorithm = algorithm
         self.base = base
         self.mapElites = mapElites
         self.aurora = aurora
         self.pattern = pattern
         self.elite = elite
    }
}

public enum LeniaBreeder2024ArenaMode: Sendable {
    case paperIsolated
    case localizedSharedCopies(copyCount: Int, canvasSize: Int)
}

public func loadLeniaBreeder2024ConfigBundle(
    configDirectory: URL,
    baseURL: URL? = nil,
    mapElitesURL: URL? = nil,
    auroraURL: URL? = nil
) throws -> LeniaBreeder2024ConfigBundle {
     let decoder = JSONDecoder()
     let base = try decoder.decode(
         LeniaBreeder2024BaseConfig.self,
         from: Data(contentsOf: baseURL ?? configDirectory.appendingPathComponent("base.json"))
     )
     let mapElites = try decoder.decode(
         LeniaBreeder2024MAPElitesConfig.self,
         from: Data(contentsOf: mapElitesURL ?? configDirectory.appendingPathComponent("me.json"))
     )
     let aurora = try decoder.decode(
         LeniaBreeder2024AURORAConfig.self,
         from: Data(contentsOf: auroraURL ?? configDirectory.appendingPathComponent("aurora.json"))
     )
     try validateLeniaBreeder2024Config(base: base, mapElites: mapElites, aurora: aurora, configDirectory: configDirectory)
     return LeniaBreeder2024ConfigBundle(
         configDirectory: configDirectory,
         base: base,
         mapElites: mapElites,
         aurora: aurora
     )
 }
 
 public func leniaBreeder2024MakeDistributedSpec(configs: LeniaBreeder2024ConfigBundle) throws -> LeniaBreeder2024DistributedSpec {
     let patternURL = configs.configDirectory
         .appendingPathComponent("patterns")
         .appendingPathComponent("\(configs.base.patternID).json")
     let pattern = try JSONDecoder().decode(LeniaBreeder2024PatternSpec.self, from: Data(contentsOf: patternURL))
     return LeniaBreeder2024DistributedSpec(
         base: configs.base,
         mapElites: configs.mapElites,
         pattern: pattern,
         specHash: try leniaBreeder2024SpecHash(
             base: configs.base,
             mapElites: configs.mapElites,
             pattern: pattern
         )
     )
 }
 
 private func leniaBreeder2024SpecHash(
     base: LeniaBreeder2024BaseConfig,
     mapElites: LeniaBreeder2024MAPElitesConfig,
     pattern: LeniaBreeder2024PatternSpec
 ) throws -> String {
     let encoder = JSONEncoder()
     encoder.outputFormatting = [.sortedKeys]
     var data = Data()
     data.append(try encoder.encode(base))
     data.append(try encoder.encode(mapElites))
     data.append(try encoder.encode(pattern))
     var hash: UInt64 = 0xcbf29ce484222325
     for byte in data {
         hash ^= UInt64(byte)
         hash &*= 0x100000001b3
     }
     return String(format: "%016llx", hash)
 }
 
 private func validateLeniaBreeder2024Config(
     base: LeniaBreeder2024BaseConfig,
     mapElites: LeniaBreeder2024MAPElitesConfig,
     aurora: LeniaBreeder2024AURORAConfig,
     configDirectory: URL
 ) throws {
     guard base.paper == "toward-artificial-open-ended-evolution-within-lenia-using-quality-diversity-2024" else {
         throw ConfigError.invalidConfig("leniabreeder-2024 base.paper must match the 2024 QD paper identifier.")
     }
     guard base.worldSize >= base.nCellsSize else {
         throw ConfigError.invalidConfig("leniabreeder-2024 world_size must be >= n_cells_size so the embryo can be embedded without cropping.")
     }
     guard base.worldSize > 0, base.worldScale > 0, base.nStep > 0 else {
         throw ConfigError.invalidConfig("leniabreeder-2024 base world_size, world_scale, and n_step must be > 0.")
     }
     guard base.nParamsSize == 3 else {
         throw ConfigError.invalidConfig("leniabreeder-2024 base.n_params_size must be 3 for (m, s, h) per kernel.")
     }
     guard base.nCellsSize > 0 else {
         throw ConfigError.invalidConfig("leniabreeder-2024 base.n_cells_size must be > 0.")
     }
     let patternURL = configDirectory.appendingPathComponent("patterns").appendingPathComponent("\(base.patternID).json")
     guard FileManager.default.fileExists(atPath: patternURL.path) else {
         throw ConfigError.invalidConfig("leniabreeder-2024 pattern asset is missing at \(patternURL.path).")
     }
     guard mapElites.algorithm == "me" else {
         throw ConfigError.invalidConfig("leniabreeder-2024 me.algorithm must be \"me\".")
     }
     guard aurora.algorithm == "aurora" else {
         throw ConfigError.invalidConfig("leniabreeder-2024 aurora.algorithm must be \"aurora\".")
     }
     try validateLeniaBreeder2024Mode(
         phenotypeSize: mapElites.phenotypeSize,
         nGenerations: mapElites.nGenerations,
         logInterval: mapElites.logInterval,
         batchSize: mapElites.batchSize,
         repertoireSize: mapElites.repertoireSize,
         isoSigma: mapElites.isoSigma,
         lineSigma: mapElites.lineSigma
     )
     guard !mapElites.descriptor.isEmpty else {
         throw ConfigError.invalidConfig("leniabreeder-2024 me.descriptor must not be empty.")
     }
     guard mapElites.descriptor.count == mapElites.descriptorMin.count,
           mapElites.descriptor.count == mapElites.descriptorMax.count else {
         throw ConfigError.invalidConfig("leniabreeder-2024 MAP-Elites descriptor bounds must match descriptor count.")
     }
     try leniaBreeder2024ValidateMetricNames(mapElites.descriptor + [mapElites.fitness], context: "MAP-Elites")
     guard mapElites.nKeep > 0, mapElites.initialCVTSamples > 0 else {
         throw ConfigError.invalidConfig("leniabreeder-2024 MAP-Elites n_keep and n_init_cvt_samples must be > 0.")
     }
     try validateLeniaBreeder2024Mode(
         phenotypeSize: aurora.phenotypeSize,
         nGenerations: aurora.nGenerations,
         logInterval: aurora.logInterval,
         batchSize: aurora.batchSize,
         repertoireSize: aurora.repertoireSize,
         isoSigma: aurora.isoSigma,
         lineSigma: aurora.lineSigma
     )
     guard aurora.nKeep > 0,
           aurora.features == 8,
           aurora.hiddenSize > 0,
           aurora.trainRatio > 0,
           aurora.learningRate > 0,
           aurora.autoencoderBatchSize > 0,
           aurora.nKeepAutoencoder > 0 else {
         throw ConfigError.invalidConfig("leniabreeder-2024 AURORA requires an 8D latent descriptor and positive training hyperparameters.")
     }
 }
 
 private func validateLeniaBreeder2024Mode(
     phenotypeSize: Int,
     nGenerations: Int,
     logInterval: Int,
     batchSize: Int,
     repertoireSize: Int,
     isoSigma: Float,
     lineSigma: Float
 ) throws {
     guard phenotypeSize > 0,
           nGenerations > 0,
           logInterval > 0,
           batchSize > 0,
           repertoireSize > 0,
           isoSigma > 0,
           lineSigma > 0 else {
         throw ConfigError.invalidConfig("leniabreeder-2024 mode hyperparameters must be > 0.")
     }
 }
 
 public struct LeniaBreeder2024PatternSpec: Codable, Sendable {
     public struct ParsedRule: Codable, Sendable {
         let kernelCore: String?

         enum CodingKeys: String, CodingKey {
             case kernelCore = "kernel_core"
         }

         public init(kernelCore: String? = nil) {
             self.kernelCore = kernelCore
         }
     }

     public struct Kernel: Codable, Sendable {
         let b: [Float]
         let c0: Int
         let c1: Int
         let h: Float
         let m: Float
         let r: Float
         let s: Float
 
         public init(
             b: [Float],
             c0: Int,
             c1: Int,
             h: Float,
             m: Float,
             r: Float,
             s: Float
         ) {
             self.b = b
             self.c0 = c0
             self.c1 = c1
             self.h = h
             self.m = m
             self.r = r
             self.s = s
         }
     }
 
     let R: Int
     let T: Int
     let cells: [[[Float]]]
     let kernels: [Kernel]
     let name: String
     let parsedRule: ParsedRule?

     enum CodingKeys: String, CodingKey {
         case R
         case T
         case cells
         case kernels
         case name
         case parsedRule = "parsed_rule"
     }
 
     public init(
         R: Int,
         T: Int,
         cells: [[[Float]]],
         kernels: [Kernel],
         name: String,
         parsedRule: ParsedRule? = nil
     ) {
         self.R = R
         self.T = T
         self.cells = cells
         self.kernels = kernels
         self.name = name
         self.parsedRule = parsedRule
     }
 }
 
 struct LeniaBreeder2024Assets {
     let pattern: LeniaBreeder2024PatternSpec
     let nChannel: Int
     let nKernel: Int
     let nGene: Int
     let nParams: Int
     let worldSize: Int
     let phenotypeSize: Int
     let centerPhenotype: Bool
     let recordPhenotype: Bool
     let steps: Int
     let nKeep: Int
     let initialGenotype: [Float]
     let initialCarry: LeniaBreeder2024Carry
     let reshapeCK: MLXArray
     let reshapeKC: MLXArray
     let kernelFFT: MLXArray
     let xGrid: MLXArray
     let yGrid: MLXArray
     let mid: Int
     let cropHalf: Int
 }
 
 struct LeniaBreeder2024ModeSettings {
     let algorithm: String
     let phenotypeSize: Int
     let centerPhenotype: Bool
     let recordPhenotype: Bool
     let nKeep: Int
 }
 
 struct LeniaBreeder2024Carry {
     var world: MLXArray
     var m: MLXArray
     var s: MLXArray
     var h: MLXArray
     var lastCenter: SIMD2<Float>
     var lastShift: SIMD2<Int>
     var totalShift: SIMD2<Int>
     var lastAngle: Float
 }
 
 struct LeniaBreeder2024CarryBatch {
     var world: MLXArray
     var m: MLXArray
     var s: MLXArray
     var h: MLXArray
     var lastCenter: [SIMD2<Float>]
     var lastShift: [SIMD2<Int>]
     var totalShift: [SIMD2<Int>]
     var lastAngle: [Float]
 }
 
struct LeniaBreeder2024StepBatchResult {
     var carry: LeniaBreeder2024CarryBatch
     let mass: [Float]
     let centerX: [Float]
     let centerY: [Float]
     let linearVelocity: [Float]
     let angle: [Float]
     let angularVelocity: [Float]
     let isEmpty: [Bool]
     let isFull: [Bool]
     let isSpread: [Bool]
    let phenotype: [[Float]]?
}

private struct LeniaBreeder2024ArenaBatchStepResult {
    let worlds: MLXArray
    let mass: [Float]
    let centerX: [Float]
    let centerY: [Float]
    let linearVelocity: [Float]
    let angle: [Float]
    let angularVelocity: [Float]
    let isEmpty: [Bool]
    let isCrowded: [Bool]
    let lastCenter: [SIMD2<Float>]
    let lastAngle: [Float]
}
 
 private struct LeniaBreeder2024VAEModel {
     var encoderW1: MLXArray
     var encoderB1: MLXArray
     var encoderWMu: MLXArray
     var encoderBMu: MLXArray
     var encoderWLogVar: MLXArray
     var encoderBLogVar: MLXArray
     var decoderW1: MLXArray
     var decoderB1: MLXArray
     var decoderWOut: MLXArray
     var decoderBOut: MLXArray
 
     init(
         encoderW1: MLXArray,
         encoderB1: MLXArray,
         encoderWMu: MLXArray,
         encoderBMu: MLXArray,
         encoderWLogVar: MLXArray,
         encoderBLogVar: MLXArray,
         decoderW1: MLXArray,
         decoderB1: MLXArray,
         decoderWOut: MLXArray,
         decoderBOut: MLXArray
     ) {
         self.encoderW1 = encoderW1
         self.encoderB1 = encoderB1
         self.encoderWMu = encoderWMu
         self.encoderBMu = encoderBMu
         self.encoderWLogVar = encoderWLogVar
         self.encoderBLogVar = encoderBLogVar
         self.decoderW1 = decoderW1
         self.decoderB1 = decoderB1
         self.decoderWOut = decoderWOut
         self.decoderBOut = decoderBOut
     }
 
     var arrays: [MLXArray] {
         [
             encoderW1, encoderB1,
             encoderWMu, encoderBMu,
             encoderWLogVar, encoderBLogVar,
             decoderW1, decoderB1,
             decoderWOut, decoderBOut,
         ]
     }
 
     init(arrays: [MLXArray]) {
         precondition(arrays.count == 10)
         self.encoderW1 = arrays[0]
         self.encoderB1 = arrays[1]
         self.encoderWMu = arrays[2]
         self.encoderBMu = arrays[3]
         self.encoderWLogVar = arrays[4]
         self.encoderBLogVar = arrays[5]
         self.decoderW1 = arrays[6]
         self.decoderB1 = arrays[7]
         self.decoderWOut = arrays[8]
         self.decoderBOut = arrays[9]
     }
 }
 
 struct LeniaBreeder2024Evaluation {
     let fitness: Float
     let descriptor: [Float]
     let failed: Bool
     let phenotype: [Float]?
     let phenotypeTrajectory: [[Float]]
     let creatureSummary: LeniaBreeder2024CreatureSummary
 }

 private struct LeniaBreeder2024MorphologyMetrics {
     let componentCount: Float
     let significantComponentCount: Float
     let largestComponentFraction: Float
     let largestComponentAnisotropy: Float
     let significantMassFraction: Float
     let momentDensity: Float
     let momentAnisotropy: Float
 }
 
 public struct LeniaBreeder2024CreatureSummary: Codable, Sendable {
     public let massMean: Float
     public let massStd: Float
     public let massMin: Float
     public let massMax: Float
     public let occupancyMean: Float
     public let varianceMean: Float
     public let energyMean: Float
     public let speedMean: Float
     public let pathLength: Float
     public let displacement: Float
     public let sampleCount: Int
     public let speedCount: Int
     public let gyration: Float
     public let centerVelocity: Float
     public let velocityX: Float
     public let velocityY: Float
     public let headingRad: Float
     public let isStable: Bool
 
     public init(
         massMean: Float,
         massStd: Float,
         massMin: Float,
         massMax: Float,
         occupancyMean: Float,
         varianceMean: Float,
         energyMean: Float,
         speedMean: Float,
         pathLength: Float,
         displacement: Float,
         sampleCount: Int,
         speedCount: Int,
         gyration: Float,
         centerVelocity: Float,
         velocityX: Float,
         velocityY: Float,
         headingRad: Float,
         isStable: Bool
     ) {
         self.massMean = massMean
         self.massStd = massStd
         self.massMin = massMin
         self.massMax = massMax
         self.occupancyMean = occupancyMean
         self.varianceMean = varianceMean
         self.energyMean = energyMean
         self.speedMean = speedMean
         self.pathLength = pathLength
         self.displacement = displacement
         self.sampleCount = sampleCount
         self.speedCount = speedCount
         self.gyration = gyration
         self.centerVelocity = centerVelocity
         self.velocityX = velocityX
         self.velocityY = velocityY
         self.headingRad = headingRad
         self.isStable = isStable
     }
 }
 
 struct LeniaBreeder2024WorkerAssetCacheEntry {
     let assets: LeniaBreeder2024Assets
 }
 
 private struct LeniaBreeder2024Repertoire {
     let centroids: [[Float]]
     var genotypes: [[Float]]
     var fitnesses: [Float]
     var descriptors: [[Float]]
     var generations: [Int]
     var phenotypes: [[Float]?]
     var phenotypeTrajectories: [[[Float]]?]
     var creatureSummaries: [LeniaBreeder2024CreatureSummary?]
 
     init(centroids: [[Float]], genotypeSize: Int) {
         self.centroids = centroids
         self.genotypes = Array(repeating: Array(repeating: 0, count: genotypeSize), count: centroids.count)
         self.fitnesses = Array(repeating: -.infinity, count: centroids.count)
         self.descriptors = Array(repeating: Array(repeating: 0, count: centroids.first?.count ?? 0), count: centroids.count)
         self.generations = Array(repeating: 0, count: centroids.count)
         self.phenotypes = Array(repeating: nil, count: centroids.count)
         self.phenotypeTrajectories = Array(repeating: nil, count: centroids.count)
         self.creatureSummaries = Array(repeating: nil, count: centroids.count)
     }
 
     mutating func add(genotypes candidates: [[Float]], evaluations: [LeniaBreeder2024Evaluation], generation: Int) -> Int {
         var updatedCells = Set<Int>()
         for (genotype, evaluation) in zip(candidates, evaluations) {
             guard evaluation.fitness.isFinite else { continue }
             let cell = nearestCentroidIndex(for: evaluation.descriptor)
             if evaluation.fitness > fitnesses[cell] {
                 fitnesses[cell] = evaluation.fitness
                 descriptors[cell] = evaluation.descriptor
                 generations[cell] = generation
                 genotypes[cell] = genotype
                 phenotypes[cell] = evaluation.phenotype
                 phenotypeTrajectories[cell] = evaluation.phenotypeTrajectory
                 creatureSummaries[cell] = evaluation.creatureSummary
                 updatedCells.insert(cell)
             }
         }
         return updatedCells.count
     }
 
     func occupiedIndices() -> [Int] {
         fitnesses.enumerated().compactMap { $0.element.isFinite ? $0.offset : nil }
     }
 
     func sampleParentIndices(count: Int, rng: inout SeededRandomNumberGenerator) -> [Int] {
         let occupied = occupiedIndices()
         if occupied.isEmpty {
             return []
         }
         return (0..<count).map { _ in occupied[Int.random(in: 0..<occupied.count, using: &rng)] }
     }
 
     func coverage() -> Float {
         guard !fitnesses.isEmpty else { return 0 }
         return Float(occupiedIndices().count) / Float(fitnesses.count)
     }
 
     func qdScore() -> Float {
         fitnesses.reduce(0) { partial, value in
             value.isFinite ? partial + value : partial
         }
     }
 
     func maxFitness() -> Float {
         fitnesses.compactMap { $0.isFinite ? $0 : nil }.max() ?? -.infinity
     }
 
     func variance() -> Float {
         let occupied = occupiedIndices()
         guard !occupied.isEmpty else { return 0 }
         guard let first = occupied.compactMap({ phenotypes[$0] }).first else { return 0 }
         var mean = Array(repeating: Float(0), count: first.count)
         var count: Float = 0
         for index in occupied {
             guard let phenotype = phenotypes[index] else { continue }
             for valueIndex in phenotype.indices {
                 mean[valueIndex] += phenotype[valueIndex]
             }
             count += 1
         }
         guard count > 0 else { return 0 }
         for valueIndex in mean.indices {
             mean[valueIndex] /= count
         }
         var variance = Array(repeating: Float(0), count: first.count)
         for index in occupied {
             guard let phenotype = phenotypes[index] else { continue }
             for valueIndex in phenotype.indices {
                 let diff = phenotype[valueIndex] - mean[valueIndex]
                 variance[valueIndex] += diff * diff
             }
         }
         let denom = max(count, 1)
         let total = variance.reduce(0) { $0 + $1 / denom }
         return total / Float(variance.count)
     }
 
     func eliteSummaries() -> [LeniaBreeder2024EliteSummary] {
         occupiedIndices().map { index in
             LeniaBreeder2024EliteSummary(
                 cell: index,
                 generation: generations[index],
                 centroid: centroids[index],
                 descriptor: descriptors[index],
                 fitness: fitnesses[index],
                 genotype: genotypes[index]
             )
         }
     }
 
     func occupiedEvaluations() -> [([Float], LeniaBreeder2024Evaluation)] {
         occupiedIndices().compactMap { index in
             guard let trajectory = phenotypeTrajectories[index],
                   let creatureSummary = creatureSummaries[index] else {
                 return nil
             }
             let evaluation = LeniaBreeder2024Evaluation(
                 fitness: fitnesses[index],
                 descriptor: descriptors[index],
                 failed: false,
                 phenotype: phenotypes[index],
                 phenotypeTrajectory: trajectory,
                 creatureSummary: creatureSummary
             )
             return (genotypes[index], evaluation)
         }
     }
 
     private func nearestCentroidIndex(for descriptor: [Float]) -> Int {
         var bestIndex = 0
         var bestDistance = Float.infinity
         for (index, centroid) in centroids.enumerated() {
             let distance = zip(centroid, descriptor).reduce(Float(0)) { partial, pair in
                 let diff = pair.0 - pair.1
                 return partial + diff * diff
             }
             if distance < bestDistance {
                 bestDistance = distance
                 bestIndex = index
             }
         }
         return bestIndex
     }
 }
 
 func leniaBreeder2024MAPElitesSettings(configs: LeniaBreeder2024ConfigBundle) -> LeniaBreeder2024ModeSettings {
     leniaBreeder2024MAPElitesSettings(config: configs.mapElites)
 }
 
 func leniaBreeder2024MAPElitesSettings(config: LeniaBreeder2024MAPElitesConfig) -> LeniaBreeder2024ModeSettings {
     LeniaBreeder2024ModeSettings(
         algorithm: config.algorithm,
         phenotypeSize: config.phenotypeSize,
         centerPhenotype: config.centerPhenotype,
         recordPhenotype: config.recordPhenotype,
         nKeep: config.nKeep
     )
 }
 
 private func leniaBreeder2024AURORASettings(configs: LeniaBreeder2024ConfigBundle) -> LeniaBreeder2024ModeSettings {
     LeniaBreeder2024ModeSettings(
         algorithm: configs.aurora.algorithm,
         phenotypeSize: configs.aurora.phenotypeSize,
         centerPhenotype: configs.aurora.centerPhenotype,
         recordPhenotype: configs.aurora.recordPhenotype,
         nKeep: configs.aurora.nKeep
     )
 }
 
public final class LeniaBreeder2024Runner {
    private let configs: LeniaBreeder2024ConfigBundle
    private let logger: Logger
    private let seed: Int
    private let arenaMode: LeniaBreeder2024ArenaMode
    private let encoder: JSONEncoder

    public init(
        configs: LeniaBreeder2024ConfigBundle,
        logger: Logger,
        seed: Int,
        arenaMode: LeniaBreeder2024ArenaMode = .paperIsolated
    ) {
        self.configs = configs
        self.logger = logger
        self.seed = seed
        self.arenaMode = arenaMode
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        self.encoder = encoder
     }
 
     public func writeResolvedConfigs(to outputDirectory: URL) throws {
         try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
         try encoder.encode(configs.base).write(to: outputDirectory.appendingPathComponent("base.json"))
        try encoder.encode(configs.mapElites).write(to: outputDirectory.appendingPathComponent("me.json"))
        try encoder.encode(configs.aurora).write(to: outputDirectory.appendingPathComponent("aurora.json"))
        let patternsDirectory = outputDirectory.appendingPathComponent("patterns", isDirectory: true)
        try FileManager.default.createDirectory(at: patternsDirectory, withIntermediateDirectories: true)
        try FileManager.default.copyItem(
            at: configs.configDirectory
                .appendingPathComponent("patterns", isDirectory: true)
                .appendingPathComponent("\(configs.base.patternID).json"),
            to: patternsDirectory.appendingPathComponent("\(configs.base.patternID).json")
        )
        let metadata: [String: Any] = [
            "seed": seed,
            "arena_mode": leniaBreeder2024ArenaModeLabel(arenaMode),
        ]
        try JSONSerialization.data(withJSONObject: metadata, options: [.prettyPrinted, .sortedKeys])
            .write(to: outputDirectory.appendingPathComponent("run.json"))
    }
 
    public func runMAPElites(outputDirectory: URL, runId: String) throws -> LeniaBreeder2024RunSummary {
        try writeResolvedConfigs(to: outputDirectory)

        let assets = try leniaBreeder2024LoadAssets(configs: configs, mode: leniaBreeder2024MAPElitesSettings(configs: configs))
         let configHash = try leniaBreeder2024MAPElitesConfigHash(base: configs.base, mapElites: configs.mapElites, pattern: assets.pattern)
         let centroids = leniaBreeder2024ComputeCVTCentroids(
             count: configs.mapElites.repertoireSize,
             descriptorMin: configs.mapElites.descriptorMin,
             descriptorMax: configs.mapElites.descriptorMax,
             sampleCount: configs.mapElites.initialCVTSamples,
             seed: seed
         )
         var repertoire = LeniaBreeder2024Repertoire(centroids: centroids, genotypeSize: assets.nGene)
         var rng = SeededRandomNumberGenerator(seed: UInt64(bitPattern: Int64(seed)))
 
        let initialPopulation = (0..<configs.mapElites.batchSize).map { _ in
            leniaBreeder2024PerturbInitialGenotype(
                base: assets.initialGenotype,
                isoSigma: configs.mapElites.isoSigma,
                rng: &rng
            )
        }
        let initialEvaluations = try evaluatePopulation(
            genotypes: initialPopulation,
            assets: assets
        )
         logger.info(
             "LeniaBreeder 2024 initial batch: finite=\(initialEvaluations.filter { $0.fitness.isFinite }.count) failed=\(initialEvaluations.filter { $0.failed }.count)"
         )
         _ = repertoire.add(genotypes: initialPopulation, evaluations: initialEvaluations, generation: 0)
 
         let historyURL = outputDirectory.appendingPathComponent("history.jsonl")
         FileManager.default.createFile(atPath: historyURL.path, contents: nil)
         let metricsCSVURL = outputDirectory.appendingPathComponent("metrics.csv")
         try "generation,qd_score,coverage,max_fitness,n_elites,variance,elapsed_seconds\n"
             .write(to: metricsCSVURL, atomically: true, encoding: .utf8)
 
         var history: [LeniaBreeder2024HistoryEntry] = []
         let logInterval = configs.mapElites.logInterval
         let generationCount = configs.mapElites.nGenerations
 
         var generation = 0
         while generation < generationCount {
             let start = Date()
             var elitesAdded = 0
             let limit = min(generation + logInterval, generationCount)
             while generation < limit {
                 let parentA = repertoire.sampleParentIndices(count: configs.mapElites.batchSize, rng: &rng)
                 let parentB = repertoire.sampleParentIndices(count: configs.mapElites.batchSize, rng: &rng)
                 guard !parentA.isEmpty, !parentB.isEmpty else {
                     throw ConfigError.invalidConfig("leniabreeder-2024 repertoire is empty; MAP-Elites cannot continue.")
                 }
                 let children = zip(parentA, parentB).map { lhs, rhs in
                     leniaBreeder2024IsolineVariation(
                         x1: repertoire.genotypes[lhs],
                         x2: repertoire.genotypes[rhs],
                         isoSigma: configs.mapElites.isoSigma,
                         lineSigma: configs.mapElites.lineSigma,
                         rng: &rng
                     )
                 }
                let evaluations = try evaluatePopulation(
                    genotypes: children,
                    assets: assets
                )
                 elitesAdded += repertoire.add(genotypes: children, evaluations: evaluations, generation: generation + 1)
                 generation += 1
             }
 
             let elapsed = Date().timeIntervalSince(start)
             let entry = LeniaBreeder2024HistoryEntry(
                 generation: generation,
                 qdScore: repertoire.qdScore(),
                 coverage: repertoire.coverage(),
                 maxFitness: repertoire.maxFitness(),
                 nElites: elitesAdded,
                 variance: repertoire.variance(),
                 elapsedSeconds: elapsed
             )
             history.append(entry)
             try appendJSONLine(entry, to: historyURL)
             try appendMetricsCSV(entry, to: metricsCSVURL)
             logger.info("LeniaBreeder 2024: gen=\(entry.generation) coverage=\(entry.coverage) qd=\(entry.qdScore) max=\(entry.maxFitness) added=\(entry.nElites)")
         }
 
         let repertoireRoot = outputDirectory.appendingPathComponent("repertoire", isDirectory: true)
         try FileManager.default.createDirectory(at: repertoireRoot, withIntermediateDirectories: true)
         try encoder.encode(repertoire.centroids).write(to: repertoireRoot.appendingPathComponent("centroids.json"))
         try encoder.encode(repertoire.eliteSummaries()).write(to: repertoireRoot.appendingPathComponent("occupied.json"))
         if let bestIndex = repertoire.occupiedIndices().max(by: { repertoire.fitnesses[$0] < repertoire.fitnesses[$1] }) {
             try encoder.encode(repertoire.eliteSummaries().first(where: { $0.cell == bestIndex }))
                 .write(to: outputDirectory.appendingPathComponent("best.json"))
         }
 
         let summary = LeniaBreeder2024RunSummary(
             paper: configs.base.paper,
             algorithm: configs.mapElites.algorithm,
             seed: seed,
             generations: generationCount,
             occupiedCells: repertoire.occupiedIndices().count,
             qdScore: repertoire.qdScore(),
             coverage: repertoire.coverage(),
             maxFitness: repertoire.maxFitness(),
             variance: repertoire.variance(),
             patternID: configs.base.patternID
         )
         try encoder.encode(summary).write(to: outputDirectory.appendingPathComponent("summary.json"))
         let resolvedRun = try loadLeniaBreeder2024ResolvedRun(
             runDirectory: outputDirectory,
             configDirectoryOverride: configs.configDirectory
         )
         try leniaBreeder2024WriteReplayExports(
             run: resolvedRun,
             repertoire: repertoire,
             runId: runId,
             algorithm: configs.mapElites.algorithm,
             configHash: configHash,
             outputDirectory: outputDirectory
         )
         try leniaBreeder2024WriteLibraryIndex(
             repertoire: repertoire,
             assets: assets,
             runId: runId,
             algorithm: configs.mapElites.algorithm,
             patternID: configs.base.patternID,
             configHash: configHash,
             distributed: false,
             canonicalExportAvailable: true,
             outputDirectory: outputDirectory
         )
         return summary
     }
 
    public func runDistributedMAPElites(
        outputDirectory: URL,
        controller: LeniaBreeder2024DistributedController,
        runId: String,
         controllerId: String,
         minWorkers: Int
     ) async throws -> LeniaBreeder2024RunSummary {
         try writeResolvedConfigs(to: outputDirectory)
 
         let distributedSpec = try leniaBreeder2024MakeDistributedSpec(configs: configs)
         let assets = try leniaBreeder2024LoadAssets(configs: configs, mode: leniaBreeder2024MAPElitesSettings(configs: configs))
         let configHash = try leniaBreeder2024MAPElitesConfigHash(base: configs.base, mapElites: configs.mapElites, pattern: assets.pattern)
         let centroids = leniaBreeder2024ComputeCVTCentroids(
             count: configs.mapElites.repertoireSize,
             descriptorMin: configs.mapElites.descriptorMin,
             descriptorMax: configs.mapElites.descriptorMax,
             sampleCount: configs.mapElites.initialCVTSamples,
             seed: seed
         )
         var repertoire = LeniaBreeder2024Repertoire(centroids: centroids, genotypeSize: assets.nGene)
         var rng = SeededRandomNumberGenerator(seed: UInt64(bitPattern: Int64(seed)))
 
         let initialPopulation = (0..<configs.mapElites.batchSize).map { _ in
             leniaBreeder2024PerturbInitialGenotype(
                 base: assets.initialGenotype,
                 isoSigma: configs.mapElites.isoSigma,
                 rng: &rng
             )
         }
         let initialEvaluations = try await controller.evaluateMAPElites(
             generation: 0,
             genotypes: initialPopulation,
             spec: distributedSpec
         )
         logger.info(
             "LeniaBreeder 2024 distributed initial batch: finite=\(initialEvaluations.filter { $0.fitness.isFinite }.count) failed=\(initialEvaluations.filter { $0.failed }.count)"
         )
         _ = repertoire.add(genotypes: initialPopulation, evaluations: initialEvaluations, generation: 0)
         try await controller.writeManifest(
             to: outputDirectory.appendingPathComponent("distributed.json"),
             algorithm: configs.mapElites.algorithm,
             seed: seed,
             specHash: distributedSpec.specHash,
             minWorkers: minWorkers,
             runId: runId,
             controllerId: controllerId
         )
 
         let historyURL = outputDirectory.appendingPathComponent("history.jsonl")
         FileManager.default.createFile(atPath: historyURL.path, contents: nil)
         let metricsCSVURL = outputDirectory.appendingPathComponent("metrics.csv")
         try "generation,qd_score,coverage,max_fitness,n_elites,variance,elapsed_seconds\n"
             .write(to: metricsCSVURL, atomically: true, encoding: .utf8)
 
         let generationCount = configs.mapElites.nGenerations
         let logInterval = configs.mapElites.logInterval
 
         var generation = 0
         while generation < generationCount {
             let start = Date()
             var elitesAdded = 0
             let limit = min(generation + logInterval, generationCount)
             while generation < limit {
                 let parentA = repertoire.sampleParentIndices(count: configs.mapElites.batchSize, rng: &rng)
                 let parentB = repertoire.sampleParentIndices(count: configs.mapElites.batchSize, rng: &rng)
                 guard !parentA.isEmpty, !parentB.isEmpty else {
                     throw ConfigError.invalidConfig("leniabreeder-2024 repertoire is empty; distributed MAP-Elites cannot continue.")
                 }
                 let children = zip(parentA, parentB).map { lhs, rhs in
                     leniaBreeder2024IsolineVariation(
                         x1: repertoire.genotypes[lhs],
                         x2: repertoire.genotypes[rhs],
                         isoSigma: configs.mapElites.isoSigma,
                         lineSigma: configs.mapElites.lineSigma,
                         rng: &rng
                     )
                 }
                 let evaluations = try await controller.evaluateMAPElites(
                     generation: generation + 1,
                     genotypes: children,
                     spec: distributedSpec
                 )
                 elitesAdded += repertoire.add(genotypes: children, evaluations: evaluations, generation: generation + 1)
                 generation += 1
             }
 
             let elapsed = Date().timeIntervalSince(start)
             let entry = LeniaBreeder2024HistoryEntry(
                 generation: generation,
                 qdScore: repertoire.qdScore(),
                 coverage: repertoire.coverage(),
                 maxFitness: repertoire.maxFitness(),
                 nElites: elitesAdded,
                 variance: repertoire.variance(),
                 elapsedSeconds: elapsed
             )
             try appendJSONLine(entry, to: historyURL)
             try appendMetricsCSV(entry, to: metricsCSVURL)
             logger.info("LeniaBreeder 2024 distributed: gen=\(entry.generation) coverage=\(entry.coverage) qd=\(entry.qdScore) max=\(entry.maxFitness) added=\(entry.nElites)")
         }
 
         let repertoireRoot = outputDirectory.appendingPathComponent("repertoire", isDirectory: true)
         try FileManager.default.createDirectory(at: repertoireRoot, withIntermediateDirectories: true)
         try encoder.encode(repertoire.centroids).write(to: repertoireRoot.appendingPathComponent("centroids.json"))
         try encoder.encode(repertoire.eliteSummaries()).write(to: repertoireRoot.appendingPathComponent("occupied.json"))
         if let bestIndex = repertoire.occupiedIndices().max(by: { repertoire.fitnesses[$0] < repertoire.fitnesses[$1] }) {
             try encoder.encode(repertoire.eliteSummaries().first(where: { $0.cell == bestIndex }))
                 .write(to: outputDirectory.appendingPathComponent("best.json"))
         }
 
         let summary = LeniaBreeder2024RunSummary(
             paper: configs.base.paper,
             algorithm: "\(configs.mapElites.algorithm)-distributed",
             seed: seed,
             generations: generationCount,
             occupiedCells: repertoire.occupiedIndices().count,
             qdScore: repertoire.qdScore(),
             coverage: repertoire.coverage(),
             maxFitness: repertoire.maxFitness(),
             variance: repertoire.variance(),
             patternID: configs.base.patternID
         )
         try encoder.encode(summary).write(to: outputDirectory.appendingPathComponent("summary.json"))
         let resolvedRun = try loadLeniaBreeder2024ResolvedRun(
             runDirectory: outputDirectory,
             configDirectoryOverride: configs.configDirectory
         )
         try leniaBreeder2024WriteReplayExports(
             run: resolvedRun,
             repertoire: repertoire,
             runId: runId,
             algorithm: configs.mapElites.algorithm,
             configHash: configHash,
             outputDirectory: outputDirectory
         )
         try leniaBreeder2024WriteLibraryIndex(
             repertoire: repertoire,
             assets: assets,
             runId: runId,
             algorithm: configs.mapElites.algorithm,
             patternID: configs.base.patternID,
             configHash: configHash,
             distributed: true,
             canonicalExportAvailable: true,
             outputDirectory: outputDirectory
        )
        return summary
    }

    private func evaluatePopulation(
        genotypes: [[Float]],
        assets: LeniaBreeder2024Assets
    ) throws -> [LeniaBreeder2024Evaluation] {
        switch arenaMode {
        case .paperIsolated:
            return try leniaBreeder2024EvaluatePopulation(
                genotypes: genotypes,
                assets: assets,
                descriptorNames: configs.mapElites.descriptor,
                fitnessName: configs.mapElites.fitness
            )
        case let .localizedSharedCopies(copyCount, canvasSize):
            return try leniaBreeder2024EvaluatePopulationLocalizedSharedArena(
                genotypes: genotypes,
                assets: assets,
                descriptorNames: configs.mapElites.descriptor,
                fitnessName: configs.mapElites.fitness,
                copyCount: copyCount,
                canvasSize: canvasSize
            )
        }
    }

    public func runAURORA(outputDirectory: URL, runId: String) throws -> LeniaBreeder2024RunSummary {
        try writeResolvedConfigs(to: outputDirectory)
 
         let mode = leniaBreeder2024AURORASettings(configs: configs)
         let assets = try leniaBreeder2024LoadAssets(configs: configs, mode: mode)
         let configHash = try leniaBreeder2024AURORAConfigHash(base: configs.base, aurora: configs.aurora, pattern: assets.pattern)
         let latentBounds = Array(repeating: (-3.0 as Float, 3.0 as Float), count: configs.aurora.features)
         let centroids = leniaBreeder2024ComputeCVTCentroids(
             count: configs.aurora.repertoireSize,
             descriptorMin: latentBounds.map(\.0),
             descriptorMax: latentBounds.map(\.1),
             sampleCount: max(configs.mapElites.initialCVTSamples, configs.aurora.repertoireSize * 8),
             seed: seed ^ 0xA0A0A0
         )
         var repertoire = LeniaBreeder2024Repertoire(centroids: centroids, genotypeSize: assets.nGene)
         var rng = SeededRandomNumberGenerator(seed: UInt64(bitPattern: Int64(seed ^ 0x0A0A0A)))
         var trainingArchive: [[Float]] = []
 
         let historyURL = outputDirectory.appendingPathComponent("history.jsonl")
         FileManager.default.createFile(atPath: historyURL.path, contents: nil)
         let metricsCSVURL = outputDirectory.appendingPathComponent("metrics.csv")
         try "generation,qd_score,coverage,max_fitness,n_elites,variance,elapsed_seconds\n"
             .write(to: metricsCSVURL, atomically: true, encoding: .utf8)
         let diagnosticsURL = outputDirectory.appendingPathComponent("aurora-diagnostics.jsonl")
         FileManager.default.createFile(atPath: diagnosticsURL.path, contents: nil)
 
         let initialPopulation = (0..<configs.aurora.batchSize).map { _ in
             leniaBreeder2024PerturbInitialGenotype(
                 base: assets.initialGenotype,
                 isoSigma: configs.aurora.isoSigma,
                 rng: &rng
             )
         }
         let initialEvaluations = try leniaBreeder2024EvaluatePopulation(
             genotypes: initialPopulation,
             assets: assets,
             descriptorNames: [],
             fitnessName: configs.aurora.fitness
         )
         logger.info(
             "LeniaBreeder 2024 AURORA initial batch: finite=\(initialEvaluations.filter { $0.fitness.isFinite }.count) failed=\(initialEvaluations.filter { $0.failed }.count)"
         )
         leniaBreeder2024AppendPhenotypes(
             from: initialEvaluations,
             to: &trainingArchive,
             limit: configs.aurora.nKeepAutoencoder,
             rng: &rng,
             useAugmentation: false
         )
         let vaeInputSize = trainingArchive.first?.count ?? (assets.phenotypeSize * assets.phenotypeSize * assets.nChannel)
         var model = leniaBreeder2024InitVAE(
             inputSize: vaeInputSize,
             hiddenSize: configs.aurora.hiddenSize,
             latentSize: configs.aurora.features,
             seed: seed
         )
         var lastTrainingStats: LeniaBreeder2024AURORATrainingStats?
         if !trainingArchive.isEmpty {
             lastTrainingStats = leniaBreeder2024TrainVAE(
                 model: &model,
                 dataset: trainingArchive,
                 config: configs.aurora,
                 rng: &rng
             )
         }
         let initialAuroraEvals = try initialEvaluations.map { evaluation in
             try leniaBreeder2024ApplyAURORA(
                 evaluation: evaluation,
                 model: model,
                 config: configs.aurora,
                 nChannel: assets.nChannel,
                 phenotypeSize: assets.phenotypeSize
             )
         }
         _ = repertoire.add(genotypes: initialPopulation, evaluations: initialAuroraEvals, generation: 0)
 
         var generation = 0
         let logInterval = configs.aurora.logInterval
         let generationCount = configs.aurora.nGenerations
 
         while generation < generationCount {
             let start = Date()
             var elitesAdded = 0
             let limit = min(generation + logInterval, generationCount)
             while generation < limit {
                 let stepStart = Date()
                 let parentA = repertoire.sampleParentIndices(count: configs.aurora.batchSize, rng: &rng)
                 let parentB = repertoire.sampleParentIndices(count: configs.aurora.batchSize, rng: &rng)
                 guard !parentA.isEmpty, !parentB.isEmpty else {
                     throw ConfigError.invalidConfig("leniabreeder-2024 repertoire is empty; AURORA cannot continue.")
                 }
                 let children = zip(parentA, parentB).map { lhs, rhs in
                     leniaBreeder2024IsolineVariation(
                         x1: repertoire.genotypes[lhs],
                         x2: repertoire.genotypes[rhs],
                         isoSigma: configs.aurora.isoSigma,
                         lineSigma: configs.aurora.lineSigma,
                         rng: &rng
                     )
                 }
                 let rawEvaluations = try leniaBreeder2024EvaluatePopulation(
                     genotypes: children,
                     assets: assets,
                     descriptorNames: [],
                     fitnessName: configs.aurora.fitness
                 )
                 leniaBreeder2024AppendPhenotypes(
                     from: rawEvaluations,
                     to: &trainingArchive,
                     limit: configs.aurora.nKeepAutoencoder,
                     rng: &rng,
                     useAugmentation: configs.aurora.useDataAugmentation
                 )
                 var retrained = false
                 var occupiedBeforeRebuild: Int?
                 var occupiedAfterRebuild: Int?
                 var generationTrainingStats: LeniaBreeder2024AURORATrainingStats?
                 if generation > 0 && generation % configs.aurora.trainRatio == 0 && !trainingArchive.isEmpty {
                     retrained = true
                     occupiedBeforeRebuild = repertoire.occupiedIndices().count
                     generationTrainingStats = leniaBreeder2024TrainVAE(
                         model: &model,
                         dataset: trainingArchive,
                         config: configs.aurora,
                         rng: &rng
                     )
                     lastTrainingStats = generationTrainingStats
                     repertoire = try leniaBreeder2024RebuildAURORARepertoire(
                         from: repertoire,
                         model: model,
                         config: configs.aurora,
                         genotypeSize: assets.nGene,
                         nChannel: assets.nChannel,
                         phenotypeSize: assets.phenotypeSize
                     )
                     occupiedAfterRebuild = repertoire.occupiedIndices().count
                 }
                 let evaluations = try rawEvaluations.map { evaluation in
                     try leniaBreeder2024ApplyAURORA(
                         evaluation: evaluation,
                         model: model,
                         config: configs.aurora,
                         nChannel: assets.nChannel,
                         phenotypeSize: assets.phenotypeSize
                     )
                 }
                 let batchDescriptorStats = leniaBreeder2024AURORADescriptorStats(
                     evaluations: evaluations,
                     nearZeroThreshold: 1e-3
                 )
                 let generationElitesAdded = repertoire.add(genotypes: children, evaluations: evaluations, generation: generation + 1)
                 elitesAdded += generationElitesAdded
                 let repertoireDescriptorStats = leniaBreeder2024AURORADescriptorStats(
                     evaluations: repertoire.occupiedEvaluations().map(\.1),
                     nearZeroThreshold: 1e-3
                 )
                 generation += 1
                 let diagnosticsEntry = LeniaBreeder2024AURORADiagnosticsEntry(
                     generation: generation,
                     elapsedSeconds: Date().timeIntervalSince(stepStart),
                     trainingArchiveSize: trainingArchive.count,
                     retrained: retrained,
                     elitesAdded: generationElitesAdded,
                     occupiedCells: repertoire.occupiedIndices().count,
                     coverage: repertoire.coverage(),
                     qdScore: repertoire.qdScore(),
                     maxFitness: repertoire.maxFitness(),
                     occupiedCellsBeforeRebuild: occupiedBeforeRebuild,
                     occupiedCellsAfterRebuild: occupiedAfterRebuild,
                     batchStats: batchDescriptorStats,
                     repertoireStats: repertoireDescriptorStats,
                     trainingStats: generationTrainingStats
                 )
                 try appendJSONLine(diagnosticsEntry, to: diagnosticsURL)
             }
 
             let elapsed = Date().timeIntervalSince(start)
             let entry = LeniaBreeder2024HistoryEntry(
                 generation: generation,
                 qdScore: repertoire.qdScore(),
                 coverage: repertoire.coverage(),
                 maxFitness: repertoire.maxFitness(),
                 nElites: elitesAdded,
                 variance: repertoire.variance(),
                 elapsedSeconds: elapsed
             )
             try appendJSONLine(entry, to: historyURL)
             try appendMetricsCSV(entry, to: metricsCSVURL)
             logger.info("LeniaBreeder 2024 AURORA: gen=\(entry.generation) coverage=\(entry.coverage) qd=\(entry.qdScore) max=\(entry.maxFitness) added=\(entry.nElites)")
         }
 
         let repertoireRoot = outputDirectory.appendingPathComponent("repertoire", isDirectory: true)
         try FileManager.default.createDirectory(at: repertoireRoot, withIntermediateDirectories: true)
         try encoder.encode(repertoire.centroids).write(to: repertoireRoot.appendingPathComponent("centroids.json"))
         try encoder.encode(repertoire.eliteSummaries()).write(to: repertoireRoot.appendingPathComponent("occupied.json"))
         try leniaBreeder2024WriteVAEMetadata(
             model: model,
             config: configs.aurora,
             lastTrainingStats: lastTrainingStats,
             to: outputDirectory.appendingPathComponent("vae.json")
         )
         if let bestIndex = repertoire.occupiedIndices().max(by: { repertoire.fitnesses[$0] < repertoire.fitnesses[$1] }) {
             try encoder.encode(repertoire.eliteSummaries().first(where: { $0.cell == bestIndex }))
                 .write(to: outputDirectory.appendingPathComponent("best.json"))
         }
 
         let summary = LeniaBreeder2024RunSummary(
             paper: configs.base.paper,
             algorithm: configs.aurora.algorithm,
             seed: seed,
             generations: generationCount,
             occupiedCells: repertoire.occupiedIndices().count,
             qdScore: repertoire.qdScore(),
             coverage: repertoire.coverage(),
             maxFitness: repertoire.maxFitness(),
             variance: repertoire.variance(),
             patternID: configs.base.patternID
         )
         try encoder.encode(summary).write(to: outputDirectory.appendingPathComponent("summary.json"))
         let resolvedRun = try loadLeniaBreeder2024ResolvedRun(
             runDirectory: outputDirectory,
             configDirectoryOverride: configs.configDirectory
         )
         try leniaBreeder2024WriteReplayExports(
             run: resolvedRun,
             repertoire: repertoire,
             runId: runId,
             algorithm: configs.aurora.algorithm,
             configHash: configHash,
             outputDirectory: outputDirectory
         )
         try leniaBreeder2024WriteLibraryIndex(
             repertoire: repertoire,
             assets: assets,
             runId: runId,
             algorithm: configs.aurora.algorithm,
             patternID: configs.base.patternID,
             configHash: configHash,
             distributed: false,
             canonicalExportAvailable: true,
             outputDirectory: outputDirectory
         )
         return summary
     }
 }
 
 public actor LeniaBreeder2024DistributedController {
     private struct RemoteWorkerInfo {
         let worker: LeniaWorker
         let summary: LeniaBreeder2024DistributedWorkerSummary
     }
 
     private let system: ClusterSystem
     private let logger: Logger
     private let runContext: RunContext
     private var workers: [RemoteWorkerInfo] = []
 
     public init(system: ClusterSystem, logger: Logger, runContext: RunContext) {
         self.system = system
         self.logger = logger
         self.runContext = runContext
     }
 
     public func start(minCount: Int) async throws {
         await listenForWorkers()
         try await waitForWorkers(minCount: minCount)
     }
 
     public func workerSummaries() -> [LeniaBreeder2024DistributedWorkerSummary] {
         workers.map(\.summary).sorted { lhs, rhs in
             lhs.workerId < rhs.workerId
         }
     }
 
     public func writeManifest(
         to url: URL,
         algorithm: String,
         seed: Int,
         specHash: String,
         minWorkers: Int,
         runId: String,
         controllerId: String
     ) throws {
         let manifest = LeniaBreeder2024DistributedManifest(
             paper: "toward-artificial-open-ended-evolution-within-lenia-using-quality-diversity-2024",
             algorithm: algorithm,
             seed: seed,
             runId: runId,
             controllerId: controllerId,
             minWorkers: minWorkers,
             specHash: specHash,
             chunkingPolicy: "one-inflight-chunk-per-worker-round",
             workers: workerSummaries()
         )
         let encoder = JSONEncoder()
         encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
         try encoder.encode(manifest).write(to: url)
     }
 
     func evaluateMAPElites(
         generation: Int,
         genotypes: [[Float]],
         spec: LeniaBreeder2024DistributedSpec
     ) async throws -> [LeniaBreeder2024Evaluation] {
         let workersSnapshot = workers.sorted { lhs, rhs in
             lhs.summary.workerId < rhs.summary.workerId
         }
         guard !workersSnapshot.isEmpty else {
             throw ConfigError.invalidConfig("leniabreeder-2024 distributed MAP-Elites requires at least one worker.")
         }
         guard !genotypes.isEmpty else {
             return []
         }
 
         let chunkCount = min(workersSnapshot.count, genotypes.count)
         let chunkSize = Int(ceil(Double(genotypes.count) / Double(chunkCount)))
         var jobs: [(RemoteWorkerInfo, LeniaBreeder2024DistributedMAPElitesJob)] = []
         jobs.reserveCapacity(chunkCount)
 
         var candidateOffset = 0
         for workerIndex in 0..<chunkCount {
             let end = min(candidateOffset + chunkSize, genotypes.count)
             let slice = Array(genotypes[candidateOffset..<end])
             let job = LeniaBreeder2024DistributedMAPElitesJob(
                 id: "qd2024-me-g\(generation)-o\(candidateOffset)",
                 generation: generation,
                 candidateOffset: candidateOffset,
                 genotypes: slice,
                 spec: spec
             )
             jobs.append((workersSnapshot[workerIndex], job))
             candidateOffset = end
         }
 
         let results = try await withThrowingTaskGroup(of: LeniaBreeder2024DistributedMAPElitesResult.self) { group in
             for (workerInfo, job) in jobs {
                 group.addTask {
                     try await workerInfo.worker.evaluateMAPElites(job: job)
                 }
             }
 
             var collected: [LeniaBreeder2024DistributedMAPElitesResult] = []
             for try await result in group {
                 collected.append(result)
             }
             return collected
         }.sorted { lhs, rhs in
             lhs.candidateOffset < rhs.candidateOffset
         }
 
         var flattened: [LeniaBreeder2024Evaluation] = []
         flattened.reserveCapacity(genotypes.count)
         for result in results {
             logger.info(
                 "LeniaBreeder 2024 distributed batch: gen=\(result.generation) offset=\(result.candidateOffset) worker=\(result.workerId) duration=\(result.durationSeconds)s count=\(result.evaluations.count)"
             )
             flattened.append(contentsOf: result.evaluations.map { leniaBreeder2024Evaluation(from: $0) })
         }
 
         guard flattened.count == genotypes.count else {
             throw ConfigError.invalidConfig("leniabreeder-2024 distributed MAP-Elites returned \(flattened.count) evaluations for \(genotypes.count) genotypes.")
         }
         return flattened
     }
 
     private func listenForWorkers() async {
         let clusterSystem = self.system
         Task {
             for await worker in await clusterSystem.receptionist.listing(of: .leniaWorkers) {
                 await self.addWorker(worker)
             }
         }
     }
 
     private func addWorker(_ worker: LeniaWorker) async {
         if workers.contains(where: { $0.worker.id == worker.id }) {
             return
         }
         try? await worker.updateRunContext(runContext)
         let summary: LeniaBreeder2024DistributedWorkerSummary
         if let status = try? await worker.getStatus() {
             summary = LeniaBreeder2024DistributedWorkerSummary(workerId: status.workerId, hostname: status.hostname)
             logger.info("qd-2024 worker joined: \(status.workerId) @ \(status.hostname)")
         } else {
             summary = LeniaBreeder2024DistributedWorkerSummary(
                 workerId: String(describing: worker.id),
                 hostname: "unknown"
             )
             logger.info("qd-2024 worker joined: \(summary.workerId)")
         }
         workers.append(RemoteWorkerInfo(worker: worker, summary: summary))
     }
 
     private func waitForWorkers(minCount: Int) async throws {
         let maxWaitSeconds = 120
         var waited = 0
         while workers.count < minCount {
             if waited >= maxWaitSeconds {
                 throw ConfigError.invalidConfig("leniabreeder-2024 distributed MAP-Elites timed out waiting for \(minCount) worker(s).")
             }
             try await Task.sleep(for: .seconds(1))
             waited += 1
         }
     }
 }
 
 func leniaBreeder2024LoadAssets(
     configs: LeniaBreeder2024ConfigBundle,
     mode: LeniaBreeder2024ModeSettings
 ) throws -> LeniaBreeder2024Assets {
     let patternURL = configs.configDirectory.appendingPathComponent("patterns").appendingPathComponent("\(configs.base.patternID).json")
     let pattern = try JSONDecoder().decode(LeniaBreeder2024PatternSpec.self, from: Data(contentsOf: patternURL))
     return try leniaBreeder2024LoadAssets(
         base: configs.base,
         pattern: pattern,
         mode: mode
     )
 }
 
 func leniaBreeder2024LoadAssets(
     base: LeniaBreeder2024BaseConfig,
     pattern: LeniaBreeder2024PatternSpec,
     mode: LeniaBreeder2024ModeSettings
 ) throws -> LeniaBreeder2024Assets {
     let nChannel = pattern.cells.count
     let nKernel = pattern.kernels.count
     let nParams = base.nParamsSize * nKernel
     let nGene = nParams + base.nCellsSize * base.nCellsSize * nChannel
 
     let baseCells = leniaBreeder2024PatternCells(pattern)
     let paddedCells = leniaBreeder2024PadCells(baseCells, targetSize: base.nCellsSize)
     let initialWorld = leniaBreeder2024CreateWorld(
         cells: paddedCells,
         worldSize: base.worldSize,
         worldScale: base.worldScale
     )
 
     var reshapeCK = Array(repeating: Float(0), count: nChannel * nKernel)
     var reshapeKC = Array(repeating: Float(0), count: nKernel * nChannel)
     for (index, kernel) in pattern.kernels.enumerated() {
         reshapeCK[kernel.c0 * nKernel + index] = 1
         reshapeKC[index * nChannel + kernel.c1] = 1
     }
 
     let initialParams =
         pattern.kernels.map(\.m) +
         pattern.kernels.map(\.s) +
         pattern.kernels.map(\.h)
     let initialGenotype = initialParams + paddedCells.flatMap { row in
         row.flatMap { $0 }
     }
 
     let R = Float(pattern.R * base.worldScale)
     let mid = base.worldSize / 2
     let xCoords = (0..<base.worldSize).map { Float($0 - mid) / R }
     let yCoords = (0..<base.worldSize).map { Float($0 - mid) / R }
     let (yGrid, xGrid) = meshgrid(MLXArray(yCoords), MLXArray(xCoords))
 
     let kernelFFT = try leniaBreeder2024KernelFFT(
         pattern: pattern,
         worldSize: base.worldSize,
         worldScale: base.worldScale
     )
     let worldArray = MLXArray(initialWorld).reshaped([base.worldSize, base.worldSize, nChannel])
     let initialCarry = LeniaBreeder2024Carry(
         world: worldArray,
         m: MLXArray(pattern.kernels.map(\.m)),
         s: MLXArray(pattern.kernels.map(\.s)),
         h: MLXArray(pattern.kernels.map(\.h)),
         lastCenter: SIMD2<Float>(repeating: 0),
         lastShift: SIMD2<Int>(repeating: 0),
         totalShift: SIMD2<Int>(repeating: 0),
         lastAngle: 0
     )
 
     return LeniaBreeder2024Assets(
         pattern: pattern,
         nChannel: nChannel,
         nKernel: nKernel,
         nGene: nGene,
         nParams: nParams,
         worldSize: base.worldSize,
         phenotypeSize: mode.phenotypeSize,
         centerPhenotype: mode.centerPhenotype,
         recordPhenotype: mode.recordPhenotype,
         steps: base.nStep,
         nKeep: mode.nKeep,
         initialGenotype: initialGenotype,
         initialCarry: initialCarry,
         reshapeCK: MLXArray(reshapeCK).reshaped([nChannel, nKernel]),
         reshapeKC: MLXArray(reshapeKC).reshaped([nKernel, nChannel]),
         kernelFFT: kernelFFT,
         xGrid: xGrid,
         yGrid: yGrid,
         mid: mid,
         cropHalf: mode.phenotypeSize / 2
     )
 }
 
 private func leniaBreeder2024PatternCells(_ pattern: LeniaBreeder2024PatternSpec) -> [[[Float]]] {
     let height = pattern.cells[0].count
     let width = pattern.cells[0][0].count
     var out = Array(
         repeating: Array(
             repeating: Array(repeating: Float(0), count: pattern.cells.count),
             count: width
         ),
         count: height
     )
     for channel in pattern.cells.indices {
         for y in 0..<height {
             for x in 0..<width {
                 out[y][x][channel] = pattern.cells[channel][y][x]
             }
         }
     }
     return out
 }
 
 private func leniaBreeder2024PadCells(_ cells: [[[Float]]], targetSize: Int) -> [[[Float]]] {
     let height = cells.count
     let width = cells[0].count
     let channels = cells[0][0].count
     let padY = targetSize - height
     let padX = targetSize - width
     var out = Array(
         repeating: Array(
             repeating: Array(repeating: Float(0), count: channels),
             count: targetSize
         ),
         count: targetSize
     )
     let offsetY = padY / 2
     let offsetX = padX / 2
     for y in 0..<height {
         for x in 0..<width {
             out[offsetY + y][offsetX + x] = cells[y][x]
         }
     }
     return out
 }
 
 private func leniaBreeder2024CreateWorld(
     cells: [[[Float]]],
     worldSize: Int,
     worldScale: Int
 ) -> [Float] {
     let channels = cells[0][0].count
     let scaledHeight = cells.count * worldScale
     let scaledWidth = cells[0].count * worldScale
     var world = Array(repeating: Float(0), count: worldSize * worldSize * channels)
     let mid = worldSize / 2
     let startY = mid - scaledHeight / 2
     let startX = mid - scaledWidth / 2
     for y in cells.indices {
         for x in cells[y].indices {
             for sy in 0..<worldScale {
                 for sx in 0..<worldScale {
                     let dstY = startY + y * worldScale + sy
                     let dstX = startX + x * worldScale + sx
                     let offset = (dstY * worldSize + dstX) * channels
                     for channel in 0..<channels {
                         world[offset + channel] = cells[y][x][channel]
                     }
                 }
             }
         }
     }
     return world
 }
 
 private func leniaBreeder2024KernelFFT(
     pattern: LeniaBreeder2024PatternSpec,
     worldSize: Int,
     worldScale: Int
 ) throws -> MLXArray {
     let R = Float(pattern.R * worldScale)
     let mid = worldSize / 2
     let x = (0..<worldSize).map { Float($0 - mid) / R }
     let y = (0..<worldSize).map { Float($0 - mid) / R }
     let (Y, X) = meshgrid(MLXArray(y), MLXArray(x))
     let D = MLX.sqrt(X * X + Y * Y)
 
     let kernelCore = pattern.parsedRule?.kernelCore?.lowercased() ?? "bucketed"
     let kernels: [MLXArray] = pattern.kernels.map { kernel in
         let betaCount = kernel.b.count
         let scaled = D * MLXArray(Float(betaCount) / kernel.r)
         let gate = MLXArray((scaled .< MLXArray(Float(betaCount))).asArray(Bool.self).map { $0 ? Float(1) : Float(0) })
             .reshaped(scaled.shape)
         let buckets = scaled.asArray(Float.self).map { value -> Float in
             let idx = min(max(Int(floor(value)), 0), betaCount - 1)
             return kernel.b[idx]
         }
         let bucketArray = MLXArray(buckets).reshaped(scaled.shape)
         let fractional = scaled - MLX.floor(scaled)
         let bell = leniaBreeder2024KernelCore(fractional: fractional, core: kernelCore)
         return gate * bucketArray * bell
     }
     let kernelStack = MLX.stacked(kernels, axis: 2)
     let normalization = kernelStack
         .sum(axis: 0, keepDims: true)
         .sum(axis: 1, keepDims: true)
     let normalized = kernelStack / normalization
     let shifted = fftshift2(normalized)
     return MLXFFT.fft2(shifted, axes: [0, 1])
 }
 

 private func leniaBreeder2024KernelCore(fractional: MLXArray, core: String) -> MLXArray {
     switch core {
     case "bump4", "qd24_bump4_v1":
         let alpha = MLXArray(Float(4.0))
         let denominator = MLXArray(Float(4.0)) * fractional * (MLXArray(1.0) - fractional)
         let body = MLX.exp(alpha - alpha / denominator)
         let valid = MLXArray(fractional.asArray(Float.self).map { value in
             value > 0 && value < 1 ? Float(1) : Float(0)
         })
             .reshaped(fractional.shape)
         return valid * body
     case "quad4", "qd24_quad4_v1":
         let body = MLX.pow(MLX.maximum(MLXArray(0.0), MLXArray(Float(4.0)) * fractional * (MLXArray(1.0) - fractional)), Float(4.0))
         let valid = MLXArray(fractional.asArray(Float.self).map { value in
             value > 0 && value < 1 ? Float(1) : Float(0)
         })
             .reshaped(fractional.shape)
         return valid * body
     case "stpz1/4", "qd24_step_v1":
         return MLXArray(fractional.asArray(Float.self).map { value in
             value >= 0.25 && value <= 0.75 ? Float(1) : Float(0)
         })
             .reshaped(fractional.shape)
     case "life", "qd24_life_v1":
         return MLXArray(fractional.asArray(Float.self).map { value in
             if value >= 0 && value < 0.25 {
                 return Float(0.5)
             }
             if value >= 0.25 && value <= 0.75 {
                 return Float(1)
             }
             return Float(0)
         })
             .reshaped(fractional.shape)
     case "bucketed", "gaussian", "gaus":
         let bellInput = (fractional - MLXArray(0.5)) / MLXArray(0.15)
         return MLX.exp(-(bellInput * bellInput) / MLXArray(2.0))
     default:
         fatalError("Unsupported leniabreeder-2024 kernel core: \(core)")
     }
 }
 
 func leniaBreeder2024PerturbInitialGenotype(
     base: [Float],
     isoSigma: Float,
     rng: inout SeededRandomNumberGenerator
 ) -> [Float] {
     base.map { $0 + gaussianSample(std: isoSigma, rng: &rng) }
 }
 
 private func leniaBreeder2024IsolineVariation(
     x1: [Float],
     x2: [Float],
     isoSigma: Float,
     lineSigma: Float,
     rng: inout SeededRandomNumberGenerator
 ) -> [Float] {
     let lineNoise = gaussianSample(std: lineSigma, rng: &rng)
     return zip(x1, x2).map { lhs, rhs in
         lhs + gaussianSample(std: isoSigma, rng: &rng) + lineNoise * (rhs - lhs)
     }
 }
 

private func leniaBreeder2024ArenaModeLabel(_ mode: LeniaBreeder2024ArenaMode) -> String {
    switch mode {
    case .paperIsolated:
        return "paper_isolated"
    case let .localizedSharedCopies(copyCount, canvasSize):
        return "localized_shared_copies:\(copyCount):\(canvasSize)"
    }
}

private func leniaBreeder2024EvaluatePopulation(
    genotypes: [[Float]],
    assets: LeniaBreeder2024Assets,
     descriptorNames: [String],
     fitnessName: String
 ) throws -> [LeniaBreeder2024Evaluation] {
     guard !genotypes.isEmpty else { return [] }
     let batchSize = genotypes.count
     var carry = try leniaBreeder2024ExpressPopulation(genotypes: genotypes, assets: assets)
     let phenotypeStartIndex = max(0, assets.steps - assets.nKeep)
 
     var massFlat: [Float] = []
     var centerXFlat: [Float] = []
     var centerYFlat: [Float] = []
     var linearVelocityFlat: [Float] = []
     var angleFlat: [Float] = []
     var angularVelocityFlat: [Float] = []
     massFlat.reserveCapacity(batchSize * assets.steps)
     centerXFlat.reserveCapacity(batchSize * assets.steps)
     centerYFlat.reserveCapacity(batchSize * assets.steps)
     linearVelocityFlat.reserveCapacity(batchSize * assets.steps)
     angleFlat.reserveCapacity(batchSize * assets.steps)
     angularVelocityFlat.reserveCapacity(batchSize * assets.steps)
 
     var lastPhenotype = Array(repeating: [Float](), count: batchSize)
     var phenotypeTrajectory = Array(repeating: [[Float]](), count: batchSize)
     var failed = Array(repeating: false, count: batchSize)
 
     for stepIndex in 0..<assets.steps {
         let shouldRecordPhenotype = assets.recordPhenotype && stepIndex >= phenotypeStartIndex
         let step = leniaBreeder2024StepBatch(
             carry: carry,
             assets: assets,
             recordPhenotype: shouldRecordPhenotype
         )
         carry = step.carry
         massFlat.append(contentsOf: step.mass)
         centerXFlat.append(contentsOf: step.centerX)
         centerYFlat.append(contentsOf: step.centerY)
         linearVelocityFlat.append(contentsOf: step.linearVelocity)
         angleFlat.append(contentsOf: step.angle)
         angularVelocityFlat.append(contentsOf: step.angularVelocity)
         for sampleIndex in 0..<batchSize {
             failed[sampleIndex] = failed[sampleIndex] || step.isEmpty[sampleIndex] || step.isFull[sampleIndex] || step.isSpread[sampleIndex]
         }
         if let phenotypeBatch = step.phenotype {
             for sampleIndex in 0..<batchSize {
                 lastPhenotype[sampleIndex] = phenotypeBatch[sampleIndex]
                 phenotypeTrajectory[sampleIndex].append(phenotypeBatch[sampleIndex])
             }
         }
     }
 
     let finalMassMap = carry.world.sum(axis: -1)
     eval(finalMassMap)
     let finalMassBatch = materializeMassBatch(finalMassMap)
     let finalStructure = computeComponentStructureBatch(
         materialized: finalMassBatch,
         threshold: 0.05,
         useTorus: true,
         significantMassMinimum: Float(assets.pattern.R * assets.pattern.R) * 0.35,
         significantMassFraction: 0.1
     )
     let finalMoments = computeMomentsBatch(
         materialized: finalMassBatch,
         config: MomentsConfig(enabled: true, threshold: 0.05)
     )

     return try (0..<batchSize).map { sampleIndex in
         let massHistory = leniaBreeder2024ExtractSeries(massFlat, sampleIndex: sampleIndex, batchSize: batchSize)
         let centerXHistory = leniaBreeder2024ExtractSeries(centerXFlat, sampleIndex: sampleIndex, batchSize: batchSize)
         let centerYHistory = leniaBreeder2024ExtractSeries(centerYFlat, sampleIndex: sampleIndex, batchSize: batchSize)
         let linearVelocityHistory = leniaBreeder2024ExtractSeries(linearVelocityFlat, sampleIndex: sampleIndex, batchSize: batchSize)
         let angleHistory = leniaBreeder2024ExtractSeries(angleFlat, sampleIndex: sampleIndex, batchSize: batchSize)
         let angularVelocityHistory = leniaBreeder2024ExtractSeries(angularVelocityFlat, sampleIndex: sampleIndex, batchSize: batchSize)
         let morphology = leniaBreeder2024MorphologyMetrics(
             structure: finalStructure,
             moments: finalMoments,
             sampleIndex: sampleIndex
         )
         let descriptor = try descriptorNames.map { name in
             try leniaBreeder2024Metric(
                 name: name,
                 mass: massHistory,
                 centerX: centerXHistory,
                 centerY: centerYHistory,
                 linearVelocity: linearVelocityHistory,
                 angle: angleHistory,
                 angularVelocity: angularVelocityHistory,
                 phenotype: lastPhenotype[sampleIndex],
                 morphology: morphology,
                 failed: failed[sampleIndex],
                 nKeep: assets.nKeep,
                 phenotypeSize: assets.phenotypeSize,
                 nChannel: assets.nChannel
             )
         }
         let fitness = try leniaBreeder2024Metric(
             name: fitnessName,
             mass: massHistory,
             centerX: centerXHistory,
             centerY: centerYHistory,
             linearVelocity: linearVelocityHistory,
             angle: angleHistory,
             angularVelocity: angularVelocityHistory,
             phenotype: lastPhenotype[sampleIndex],
             morphology: morphology,
             failed: failed[sampleIndex],
             nKeep: assets.nKeep,
             phenotypeSize: assets.phenotypeSize,
             nChannel: assets.nChannel
         )
         return LeniaBreeder2024Evaluation(
             fitness: failed[sampleIndex] || fitness.isNaN || descriptor.contains(where: \.isNaN) ? -.infinity : fitness,
             descriptor: descriptor,
             failed: failed[sampleIndex],
             phenotype: lastPhenotype[sampleIndex],
             phenotypeTrajectory: phenotypeTrajectory[sampleIndex],
             creatureSummary: leniaBreeder2024CreatureSummary(
                 mass: massHistory,
                 centerX: centerXHistory,
                 centerY: centerYHistory,
                 linearVelocity: linearVelocityHistory,
                 phenotype: lastPhenotype[sampleIndex],
                 phenotypeSize: assets.phenotypeSize,
                 nChannel: assets.nChannel,
                 failed: failed[sampleIndex]
             )
         )
     }
 }
 
 func leniaBreeder2024EvaluateMAPElitesJob(
     job: LeniaBreeder2024DistributedMAPElitesJob,
     workerId: String,
     cache: inout [String: LeniaBreeder2024WorkerAssetCacheEntry]
 ) throws -> LeniaBreeder2024DistributedMAPElitesResult {
     let start = Date()
     let assets: LeniaBreeder2024Assets
     if let cached = cache[job.spec.specHash] {
         assets = cached.assets
     } else {
         let loaded = try leniaBreeder2024LoadAssets(
             base: job.spec.base,
             pattern: job.spec.pattern,
             mode: leniaBreeder2024MAPElitesSettings(config: job.spec.mapElites)
         )
         cache[job.spec.specHash] = LeniaBreeder2024WorkerAssetCacheEntry(assets: loaded)
         assets = loaded
     }
     let evaluations = try leniaBreeder2024EvaluatePopulation(
         genotypes: job.genotypes,
         assets: assets,
         descriptorNames: job.spec.mapElites.descriptor,
         fitnessName: job.spec.mapElites.fitness
     ).map { evaluation in
         LeniaBreeder2024DistributedMAPElitesEvaluation(
             fitness: evaluation.fitness,
             descriptor: evaluation.descriptor,
             failed: evaluation.failed,
             phenotype: evaluation.phenotype,
             creatureSummary: evaluation.creatureSummary
         )
     }
     return LeniaBreeder2024DistributedMAPElitesResult(
         jobId: job.id,
         generation: job.generation,
         candidateOffset: job.candidateOffset,
         workerId: workerId,
         durationSeconds: Date().timeIntervalSince(start),
         evaluations: evaluations
     )
 }
 
 private func leniaBreeder2024Evaluation(
     from distributed: LeniaBreeder2024DistributedMAPElitesEvaluation
 ) -> LeniaBreeder2024Evaluation {
     LeniaBreeder2024Evaluation(
         fitness: distributed.fitness,
         descriptor: distributed.descriptor,
         failed: distributed.failed,
         phenotype: distributed.phenotype,
         phenotypeTrajectory: [],
         creatureSummary: distributed.creatureSummary
     )
 }
 
 private func leniaBreeder2024Express(
     genotype: [Float],
     assets: LeniaBreeder2024Assets
 ) throws -> LeniaBreeder2024Carry {
     guard genotype.count == assets.nGene else {
         throw ConfigError.invalidConfig("leniabreeder-2024 genotype length mismatch.")
     }
     let params = Array(genotype[0..<assets.nParams])
     let cellsFlat = Array(genotype[assets.nParams..<genotype.count])
     let cellsSize = assets.nGene - assets.nParams
     let embryoSide = Int(sqrt(Double(cellsSize / assets.nChannel)))
     guard embryoSide * embryoSide * assets.nChannel == cellsSize else {
         throw ConfigError.invalidConfig("leniabreeder-2024 embryo size must be square.")
     }
     var paddedCells = Array(
         repeating: Array(
             repeating: Array(repeating: Float(0), count: assets.nChannel),
             count: embryoSide
         ),
         count: embryoSide
     )
     var cursor = 0
     for y in 0..<embryoSide {
         for x in 0..<embryoSide {
             for channel in 0..<assets.nChannel {
                 paddedCells[y][x][channel] = cellsFlat[cursor]
                 cursor += 1
             }
         }
     }
     let world = leniaBreeder2024CreateWorld(
         cells: paddedCells,
         worldSize: assets.worldSize,
         worldScale: 1
     )
     let nKernel = assets.nKernel
     let m = Array(params[0..<nKernel])
     let s = Array(params[nKernel..<(2 * nKernel)])
     let h = Array(params[(2 * nKernel)..<(3 * nKernel)])
     return LeniaBreeder2024Carry(
         world: MLXArray(world).reshaped([assets.worldSize, assets.worldSize, assets.nChannel]),
         m: MLXArray(m),
         s: MLXArray(s),
         h: MLXArray(h),
         lastCenter: SIMD2<Float>(repeating: 0),
         lastShift: SIMD2<Int>(repeating: 0),
         totalShift: SIMD2<Int>(repeating: 0),
         lastAngle: 0
     )
 }
 
 private func leniaBreeder2024ExpressPopulation(
     genotypes: [[Float]],
     assets: LeniaBreeder2024Assets
 ) throws -> LeniaBreeder2024CarryBatch {
     let carries = try genotypes.map { try leniaBreeder2024Express(genotype: $0, assets: assets) }
     return LeniaBreeder2024CarryBatch(
         world: MLX.stacked(carries.map(\.world), axis: 0),
         m: MLX.stacked(carries.map(\.m), axis: 0),
         s: MLX.stacked(carries.map(\.s), axis: 0),
         h: MLX.stacked(carries.map(\.h), axis: 0),
         lastCenter: carries.map(\.lastCenter),
         lastShift: carries.map(\.lastShift),
         totalShift: carries.map(\.totalShift),
         lastAngle: carries.map(\.lastAngle)
     )
 }
 
 private func leniaBreeder2024RollBatch(
     _ world: MLXArray,
     shifts: [SIMD2<Int>]
 ) -> MLXArray {
     precondition(world.shape[0] == shifts.count, "leniabreeder-2024 batch roll count mismatch")
     let rolled = shifts.enumerated().map { sampleIndex, shift in
         rollMultiAxis(
             world[sampleIndex, 0..., 0..., 0...],
             shifts: [-shift.x, -shift.y],
             axes: [0, 1]
         )
     }
     return MLX.stacked(rolled, axis: 0)
 }
 
 private func leniaBreeder2024SplitPhenotypeBatch(
     _ batch: MLXArray,
     batchSize: Int,
     phenotypeSize: Int,
     nChannel: Int
 ) -> [[Float]] {
     let flat = batch.asArray(Float.self)
     let sampleSize = phenotypeSize * phenotypeSize * nChannel
     return (0..<batchSize).map { sampleIndex in
         let start = sampleIndex * sampleSize
         let end = start + sampleSize
         return Array(flat[start..<end])
     }
 }
 
private func leniaBreeder2024StepBatch(
    carry: LeniaBreeder2024CarryBatch,
    assets: LeniaBreeder2024Assets,
    recordPhenotype: Bool
) -> LeniaBreeder2024StepBatchResult {
     let batchSize = carry.lastCenter.count
     let shifted = leniaBreeder2024RollBatch(carry.world, shifts: carry.lastShift)
 #if DEBUG
     if batchSize > 0 {
         let serialShifted = rollMultiAxis(
             carry.world[0, 0..., 0..., 0...],
             shifts: [-carry.lastShift[0].x, -carry.lastShift[0].y],
             axes: [0, 1]
         )
         let batchShifted = shifted[0, 0..., 0..., 0...]
         eval(serialShifted, batchShifted)
         if serialShifted.asArray(Float.self) != batchShifted.asArray(Float.self) {
             fatalError("leniabreeder-2024 batch roll mismatch")
         }
     }
 #endif
     let fA = MLXFFT.fft2(shifted, axes: [1, 2])
     let fAK = MLX.matmul(fA, assets.reshapeCK)
     let UK = MLXFFT.ifft2(assets.kernelFFT.reshaped([1] + assets.kernelFFT.shape) * fAK, axes: [1, 2]).realPart()
     let m = carry.m.reshaped([batchSize, 1, 1, assets.nKernel])
     let s = carry.s.reshaped([batchSize, 1, 1, assets.nKernel])
     let h = carry.h.reshaped([batchSize, 1, 1, assets.nKernel])
     let GK = (MLXArray(2.0) * MLX.exp(-(((UK - m) / s) * ((UK - m) / s)) / MLXArray(2.0)) - MLXArray(1.0)) * h
     let G = MLX.matmul(GK, assets.reshapeKC)
     let nextA = MLX.clip(shifted + MLXArray(Float(1.0 / Float(assets.pattern.T))) * G, min: MLXArray(0.0), max: MLXArray(1.0))
 
     let currentMassArr = shifted.sum(axes: [1, 2, 3])
     let nextMassMap = nextA.sum(axis: -1)
     let xWeightedArr = (nextMassMap * assets.xGrid).sum(axes: [1, 2])
     let yWeightedArr = (nextMassMap * assets.yGrid).sum(axes: [1, 2])
     let channelMaxArr = nextA.max(axis: 1).max(axis: 1)
     let borderTopArr = nextA[0..., 0, 0..., 0...].sum(axes: [1, 2])
     let borderBottomArr = nextA[0..., assets.worldSize - 1, 0..., 0...].sum(axes: [1, 2])
     let borderLeftArr = nextA[0..., 0..., 0, 0...].sum(axes: [1, 2])
     let borderRightArr = nextA[0..., 0..., assets.worldSize - 1, 0...].sum(axes: [1, 2])
     let start = assets.mid - assets.cropHalf
     let end = assets.mid + assets.cropHalf
     let croppedCurrent = shifted[0..., start..<end, start..<end, 0...]
     let croppedMassArr = croppedCurrent.sum(axes: [1, 2, 3])
     eval(
         currentMassArr,
         xWeightedArr,
         yWeightedArr,
         channelMaxArr,
         borderTopArr,
         borderBottomArr,
         borderLeftArr,
         borderRightArr,
         croppedMassArr
     )
 
     let currentMassCPU = currentMassArr.asArray(Float.self)
     let xWeightedCPU = xWeightedArr.asArray(Float.self)
     let yWeightedCPU = yWeightedArr.asArray(Float.self)
     let channelMaxCPU = channelMaxArr.asArray(Float.self)
     let borderTopCPU = borderTopArr.asArray(Float.self)
     let borderBottomCPU = borderBottomArr.asArray(Float.self)
     let borderLeftCPU = borderLeftArr.asArray(Float.self)
     let borderRightCPU = borderRightArr.asArray(Float.self)
     let croppedMassCPU = croppedMassArr.asArray(Float.self)
 
     var mass = [Float](repeating: 0, count: batchSize)
     var centerX = [Float](repeating: 0, count: batchSize)
     var centerY = [Float](repeating: 0, count: batchSize)
     var linearVelocity = [Float](repeating: 0, count: batchSize)
     var angle = [Float](repeating: 0, count: batchSize)
     var angularVelocity = [Float](repeating: 0, count: batchSize)
     var isEmpty = [Bool](repeating: false, count: batchSize)
     var isFull = [Bool](repeating: false, count: batchSize)
     var isSpread = [Bool](repeating: false, count: batchSize)
     var nextLastCenter = carry.lastCenter
     var nextLastShift = carry.lastShift
     var nextTotalShift = carry.totalShift
     var nextLastAngle = carry.lastAngle
 
     for sampleIndex in 0..<batchSize {
         let currentMass = currentMassCPU[sampleIndex]
         let sampleCenterY = currentMass == 0 ? 0 : yWeightedCPU[sampleIndex] / currentMass
         let sampleCenterX = currentMass == 0 ? 0 : xWeightedCPU[sampleIndex] / currentMass
         let shift = SIMD2<Int>(
             Int(sampleCenterY * Float(assets.pattern.R)),
             Int(sampleCenterX * Float(assets.pattern.R))
         )
         let totalShift = carry.totalShift[sampleIndex] &+ shift
         let center = SIMD2<Float>(sampleCenterY, sampleCenterX)
         let centerDiff = SIMD2<Float>(
             center.x - carry.lastCenter[sampleIndex].x + Float(carry.lastShift[sampleIndex].x) / Float(assets.pattern.R),
             center.y - carry.lastCenter[sampleIndex].y + Float(carry.lastShift[sampleIndex].y) / Float(assets.pattern.R)
         )
         let sampleLinearVelocity = sqrt(centerDiff.x * centerDiff.x + centerDiff.y * centerDiff.y) * Float(assets.pattern.T)
         let sampleAngle = atan2(centerDiff.y, centerDiff.x) / .pi
         var angleDiff = fmodf(sampleAngle - carry.lastAngle[sampleIndex] + 3, 2) - 1
         if sampleLinearVelocity <= 0.01 {
             angleDiff = 0
         }
 
         let channelOffset = sampleIndex * assets.nChannel
         isEmpty[sampleIndex] = channelMaxCPU[channelOffset..<(channelOffset + assets.nChannel)].contains(where: { $0 < 0.1 })
         let borderMass = borderTopCPU[sampleIndex] + borderBottomCPU[sampleIndex] + borderLeftCPU[sampleIndex] + borderRightCPU[sampleIndex]
         isFull[sampleIndex] = borderMass > 0.1
         isSpread[sampleIndex] = currentMass > 0 ? croppedMassCPU[sampleIndex] / currentMass < 0.9 : true
         mass[sampleIndex] = currentMass / Float(assets.pattern.R * assets.pattern.R)
         centerX[sampleIndex] = sampleCenterX + Float(totalShift.y) / Float(assets.pattern.R)
         centerY[sampleIndex] = -(sampleCenterY + Float(totalShift.x) / Float(assets.pattern.R))
         linearVelocity[sampleIndex] = sampleLinearVelocity
         angle[sampleIndex] = sampleAngle
         angularVelocity[sampleIndex] = angleDiff * Float(assets.pattern.T)
         nextLastCenter[sampleIndex] = center
         nextLastShift[sampleIndex] = shift
         nextTotalShift[sampleIndex] = totalShift
         nextLastAngle[sampleIndex] = sampleAngle
     }
 
     let phenotype: [[Float]]?
     if recordPhenotype {
         let phenotypeWorld: MLXArray
         if assets.centerPhenotype {
             phenotypeWorld = nextA[0..., start..<end, start..<end, 0...]
         } else {
             let phenotypeShifts = zip(nextTotalShift, nextLastShift).map { totalShift, shift in
                 SIMD2<Int>(x: totalShift.x - shift.x, y: totalShift.y - shift.y)
             }
             let rolled = leniaBreeder2024RollBatch(nextA, shifts: phenotypeShifts)
             phenotypeWorld = rolled[0..., start..<end, start..<end, 0...]
         }
         eval(phenotypeWorld)
         phenotype = leniaBreeder2024SplitPhenotypeBatch(
             phenotypeWorld,
             batchSize: batchSize,
             phenotypeSize: assets.phenotypeSize,
             nChannel: assets.nChannel
         )
     } else {
         phenotype = nil
     }
 
    return LeniaBreeder2024StepBatchResult(
        carry: LeniaBreeder2024CarryBatch(
            world: nextA,
            m: carry.m,
             s: carry.s,
             h: carry.h,
             lastCenter: nextLastCenter,
             lastShift: nextLastShift,
             totalShift: nextTotalShift,
             lastAngle: nextLastAngle
         ),
         mass: mass,
         centerX: centerX,
         centerY: centerY,
         linearVelocity: linearVelocity,
         angle: angle,
         angularVelocity: angularVelocity,
         isEmpty: isEmpty,
         isFull: isFull,
         isSpread: isSpread,
        phenotype: phenotype
    )
}

private func leniaBreeder2024SharedArenaWorldBatch(
    worlds: MLXArray,
    anchors: [SIMD2<Int>],
    worldSize: Int,
    channels: Int,
    canvasSize: Int
) throws -> MLXArray {
    let batchSize = worlds.shape[0]
    eval(worlds)
    let values = worlds.asArray(Float.self)
    let inputSampleSize = worldSize * worldSize * channels
    let outputSampleSize = canvasSize * canvasSize * channels
    var batch = [Float](repeating: 0, count: batchSize * outputSampleSize)

    for sampleIndex in 0..<batchSize {
        let inputOffset = sampleIndex * inputSampleSize
        let outputOffset = sampleIndex * outputSampleSize
        for anchor in anchors {
            let startRow = anchor.x - worldSize / 2
            let startCol = anchor.y - worldSize / 2
            for row in 0..<worldSize {
                for col in 0..<worldSize {
                    let sourcePixel = inputOffset + (row * worldSize + col) * channels
                    let targetRow = startRow + row
                    let targetCol = startCol + col
                    guard targetRow >= 0, targetRow < canvasSize, targetCol >= 0, targetCol < canvasSize else {
                        continue
                    }
                    let targetPixel = outputOffset + (targetRow * canvasSize + targetCol) * channels
                    for channel in 0..<channels {
                        let value = values[sourcePixel + channel]
                        if value <= 1e-6 { continue }
                        batch[targetPixel + channel] = max(batch[targetPixel + channel], value)
                    }
                }
            }
        }
    }

    return MLXArray(batch).reshaped([batchSize, canvasSize, canvasSize, channels])
}

private func leniaBreeder2024StepArenaBatch(
    worlds: MLXArray,
    m: MLXArray,
    s: MLXArray,
    h: MLXArray,
    reshapeCK: MLXArray,
    reshapeKC: MLXArray,
    kernelFFT: MLXArray,
    T: Int,
    xGrid: MLXArray,
    yGrid: MLXArray,
    massNormalization: Float,
    occupancyThreshold: MLXArray,
    lastCenter: [SIMD2<Float>],
    lastAngle: [Float]
) -> LeniaBreeder2024ArenaBatchStepResult {
    let batchSize = worlds.shape[0]
    let nKernel = m.shape[1]
    let fA = MLXFFT.fft2(worlds, axes: [1, 2])
    let fAK = MLX.matmul(fA, reshapeCK)
    let UK = MLXFFT.ifft2(kernelFFT.reshaped([1] + kernelFFT.shape) * fAK, axes: [1, 2]).realPart()
    let mField = m.reshaped([batchSize, 1, 1, nKernel])
    let sField = s.reshaped([batchSize, 1, 1, nKernel])
    let hField = h.reshaped([batchSize, 1, 1, nKernel])
    let GK = (MLXArray(2.0) * MLX.exp(-(((UK - mField) / sField) * ((UK - mField) / sField)) / MLXArray(2.0)) - MLXArray(1.0)) * hField
    let G = MLX.matmul(GK, reshapeKC)
    let next = MLX.clip(worlds + MLXArray(Float(1.0 / Float(T))) * G, min: MLXArray(0.0), max: MLXArray(1.0))

    let massMap = next.sum(axis: -1)
    let totalMass = massMap.sum(axes: [1, 2])
    let xWeighted = (massMap * xGrid).sum(axes: [1, 2])
    let yWeighted = (massMap * yGrid).sum(axes: [1, 2])
    let channelMax = next.max(axis: 1).max(axis: 1)
    let occupancy = (massMap .> occupancyThreshold).asArray(Bool.self)
    eval(totalMass, xWeighted, yWeighted, channelMax)

    let totalMassCPU = totalMass.asArray(Float.self)
    let xWeightedCPU = xWeighted.asArray(Float.self)
    let yWeightedCPU = yWeighted.asArray(Float.self)
    let channelMaxCPU = channelMax.asArray(Float.self)
    let occupancyPerSample = worlds.shape[1] * worlds.shape[2]

    var mass = [Float](repeating: 0, count: batchSize)
    var centerX = [Float](repeating: 0, count: batchSize)
    var centerY = [Float](repeating: 0, count: batchSize)
    var linearVelocity = [Float](repeating: 0, count: batchSize)
    var angle = [Float](repeating: 0, count: batchSize)
    var angularVelocity = [Float](repeating: 0, count: batchSize)
    var isEmpty = [Bool](repeating: false, count: batchSize)
    var isCrowded = [Bool](repeating: false, count: batchSize)
    var nextLastCenter = lastCenter
    var nextLastAngle = lastAngle

    for sampleIndex in 0..<batchSize {
        let sampleMass = totalMassCPU[sampleIndex]
        let sampleCenterX = sampleMass == 0 ? 0 : xWeightedCPU[sampleIndex] / sampleMass
        let sampleCenterY = sampleMass == 0 ? 0 : yWeightedCPU[sampleIndex] / sampleMass
        let center = SIMD2<Float>(sampleCenterX, sampleCenterY)
        let diff = center - lastCenter[sampleIndex]
        let speed = sqrt(diff.x * diff.x + diff.y * diff.y) * Float(T)
        let sampleAngle = atan2(diff.y, diff.x) / .pi
        var angleDiff = fmodf(sampleAngle - lastAngle[sampleIndex] + 3, 2) - 1
        if speed <= 0.01 {
            angleDiff = 0
        }
        let occOffset = sampleIndex * occupancyPerSample
        let occupiedCount = occupancy[occOffset..<(occOffset + occupancyPerSample)].reduce(0) { $0 + ($1 ? 1 : 0) }

        mass[sampleIndex] = sampleMass / massNormalization
        centerX[sampleIndex] = sampleCenterX
        centerY[sampleIndex] = -sampleCenterY
        linearVelocity[sampleIndex] = speed
        angle[sampleIndex] = sampleAngle
        angularVelocity[sampleIndex] = angleDiff * Float(T)
        isEmpty[sampleIndex] = channelMaxCPU[(sampleIndex * channelMax.shape[1])..<(sampleIndex * channelMax.shape[1] + channelMax.shape[1])].contains(where: { $0 < 0.1 })
        isCrowded[sampleIndex] = Float(occupiedCount) / Float(max(occupancyPerSample, 1)) > 0.18 || sampleMass > 6_000
        nextLastCenter[sampleIndex] = center
        nextLastAngle[sampleIndex] = sampleAngle
    }

    return LeniaBreeder2024ArenaBatchStepResult(
        worlds: next,
        mass: mass,
        centerX: centerX,
        centerY: centerY,
        linearVelocity: linearVelocity,
        angle: angle,
        angularVelocity: angularVelocity,
        isEmpty: isEmpty,
        isCrowded: isCrowded,
        lastCenter: nextLastCenter,
        lastAngle: nextLastAngle
    )
}

private func leniaBreeder2024ExtractSeries(
    _ flat: [Float],
    sampleIndex: Int,
     batchSize: Int
 ) -> [Float] {
     var out: [Float] = []
     out.reserveCapacity(flat.count / max(batchSize, 1))
     for offset in stride(from: sampleIndex, to: flat.count, by: batchSize) {
         out.append(flat[offset])
     }
     return out
 }

 private let leniaBreeder2024MetricOperators: Set<String> = ["avg", "var", "max"]

 private let leniaBreeder2024SupportedMetrics: Set<String> = [
     "mass",
     "linear_velocity",
     "angular_velocity",
     "angle",
     "center_x",
     "center_y",
     "color",
     "survival",
     "component_count",
     "significant_component_count",
     "largest_component_fraction",
     "largest_component_anisotropy",
     "significant_mass_fraction",
     "moment_density",
     "moment_anisotropy",
     "organism_score"
 ]

 private func leniaBreeder2024MetricParts(_ name: String) throws -> (sign: Float, metric: String, op: String) {
     let parts = name.split(separator: "_")
     guard parts.count >= 3 else {
         throw ConfigError.invalidConfig("leniabreeder-2024 metric name \(name) is invalid.")
     }
     guard parts[0] == "pos" || parts[0] == "neg" else {
         throw ConfigError.invalidConfig("leniabreeder-2024 metric name \(name) must start with pos_ or neg_.")
     }
     let op = String(parts.last!)
     guard leniaBreeder2024MetricOperators.contains(op) else {
         throw ConfigError.invalidConfig("leniabreeder-2024 metric operator \(op) is unsupported.")
     }
     let metric = parts[1..<(parts.count - 1)].joined(separator: "_")
     guard leniaBreeder2024SupportedMetrics.contains(metric) else {
         throw ConfigError.invalidConfig("leniabreeder-2024 metric \(metric) is unsupported.")
     }
     return (parts[0] == "neg" ? Float(-1) : Float(1), metric, op)
 }

 private func leniaBreeder2024ValidateMetricNames(_ names: [String], context: String) throws {
     for name in names {
         _ = try leniaBreeder2024MetricParts(name)
     }
     guard names.allSatisfy({ !$0.isEmpty }) else {
         throw ConfigError.invalidConfig("leniabreeder-2024 \(context) metric names must not be empty.")
     }
 }

 private func leniaBreeder2024MorphologyMetrics(
     structure: ComponentStructureBatchResult,
     moments: MomentsBatchResult,
     sampleIndex: Int
 ) -> LeniaBreeder2024MorphologyMetrics {
     LeniaBreeder2024MorphologyMetrics(
         componentCount: structure.count[sampleIndex],
         significantComponentCount: structure.significantCount[sampleIndex],
         largestComponentFraction: structure.largestFraction[sampleIndex],
         largestComponentAnisotropy: structure.largestAnisotropy[sampleIndex],
         significantMassFraction: structure.significantMassFraction[sampleIndex],
         momentDensity: moments.density[sampleIndex],
         momentAnisotropy: moments.anisotropy[sampleIndex]
     )
 }
 
 private func leniaBreeder2024Metric(
     name: String,
     mass: [Float],
     centerX: [Float],
     centerY: [Float],
     linearVelocity: [Float],
     angle: [Float],
     angularVelocity: [Float],
     phenotype: [Float],
     morphology: LeniaBreeder2024MorphologyMetrics?,
     failed: Bool,
     nKeep: Int,
     phenotypeSize: Int,
     nChannel: Int
 ) throws -> Float {
     let window = max(1, min(nKeep, mass.count))
     func tail(_ values: [Float]) -> ArraySlice<Float> {
         values.suffix(window)
     }
 
     let (sign, metric, op) = try leniaBreeder2024MetricParts(name)
     let aggregate: ([Float]) -> Float
     switch op {
     case "avg":
         aggregate = { values in values.reduce(0, +) / Float(max(values.count, 1)) }
     case "var":
         aggregate = { values in
             guard !values.isEmpty else { return 0 }
             let mean = values.reduce(0, +) / Float(values.count)
             return values.reduce(0) { partial, value in
                 let diff = value - mean
                 return partial + diff * diff
             } / Float(values.count)
         }
     case "max":
         aggregate = { values in values.max() ?? 0 }
     default:
         throw ConfigError.invalidConfig("leniabreeder-2024 metric operator \(op) is unsupported.")
     }
 
     switch metric {
     case "mass":
         return sign * aggregate(Array(tail(mass)))
     case "linear_velocity":
         let startIndex = mass.count - window
         let dx = centerX.last! - centerX[startIndex]
         let dy = centerY.last! - centerY[startIndex]
         return sign * sqrt(dx * dx + dy * dy)
     case "angular_velocity":
         return sign * aggregate(Array(tail(angularVelocity)))
     case "angle":
         return sign * aggregate(Array(tail(angle)))
     case "center_x":
         return sign * aggregate(Array(tail(centerX)))
     case "center_y":
         return sign * aggregate(Array(tail(centerY)))
     case "color":
         guard !phenotype.isEmpty else { return 0 }
         var channels = Array(repeating: Float(0), count: nChannel)
         var count = 0
         for pixel in stride(from: 0, to: phenotype.count, by: nChannel) {
             for channel in 0..<nChannel {
                 channels[channel] += phenotype[pixel + channel]
             }
             count += 1
         }
         let denom = Float(max(count, 1))
         return sign * aggregate(channels.map { $0 / denom })
     case "survival":
         return sign * (failed ? 0 : 1)
     case "component_count":
         guard let morphology else { throw ConfigError.invalidConfig("leniabreeder-2024 metric \(metric) requires morphology metrics.") }
         return sign * morphology.componentCount
     case "significant_component_count":
         guard let morphology else { throw ConfigError.invalidConfig("leniabreeder-2024 metric \(metric) requires morphology metrics.") }
         return sign * morphology.significantComponentCount
     case "largest_component_fraction":
         guard let morphology else { throw ConfigError.invalidConfig("leniabreeder-2024 metric \(metric) requires morphology metrics.") }
         return sign * morphology.largestComponentFraction
     case "largest_component_anisotropy":
         guard let morphology else { throw ConfigError.invalidConfig("leniabreeder-2024 metric \(metric) requires morphology metrics.") }
         return sign * morphology.largestComponentAnisotropy
     case "significant_mass_fraction":
         guard let morphology else { throw ConfigError.invalidConfig("leniabreeder-2024 metric \(metric) requires morphology metrics.") }
         return sign * morphology.significantMassFraction
     case "moment_density":
         guard let morphology else { throw ConfigError.invalidConfig("leniabreeder-2024 metric \(metric) requires morphology metrics.") }
         return sign * morphology.momentDensity
     case "moment_anisotropy":
         guard let morphology else { throw ConfigError.invalidConfig("leniabreeder-2024 metric \(metric) requires morphology metrics.") }
         return sign * morphology.momentAnisotropy
     case "organism_score":
         guard let morphology else { throw ConfigError.invalidConfig("leniabreeder-2024 metric \(metric) requires morphology metrics.") }
         let survivalScore: Float = failed ? 0 : 1
         let motionScore = min(max(aggregate(Array(tail(linearVelocity))) / 0.004, 0), 1)
         let concentrationScore = min(max(morphology.largestComponentFraction, 0), 1)
         let densityScore = min(max(morphology.momentDensity / 0.08, 0), 1)
         let anisotropyPenalty = min(max(morphology.largestComponentAnisotropy, 0), 1)
         let fragmentationPenalty = min(max((morphology.componentCount - 3) / 12, 0), 1)
         return sign * survivalScore * (0.35 * motionScore + 0.25 * concentrationScore + 0.25 * densityScore + 0.15 * (1 - anisotropyPenalty)) * (1 - 0.5 * fragmentationPenalty)
     default:
         throw ConfigError.invalidConfig("leniabreeder-2024 metric \(metric) is unsupported.")
     }
 }
 
 private func leniaBreeder2024AppendPhenotypes(
     from evaluations: [LeniaBreeder2024Evaluation],
     to archive: inout [[Float]],
     limit: Int,
     rng: inout SeededRandomNumberGenerator,
     useAugmentation: Bool
 ) {
     for evaluation in evaluations where !evaluation.failed {
         for phenotype in evaluation.phenotypeTrajectory {
             archive.append(phenotype)
             if useAugmentation {
                 archive.append(leniaBreeder2024FlipPhenotypeHorizontally(phenotype))
                 archive.append(leniaBreeder2024FlipPhenotypeVertically(phenotype))
             }
         }
     }
     if archive.count > limit {
         let start = archive.count - limit
         archive = Array(archive[start...])
     }
 }
 
 private func leniaBreeder2024FlipPhenotypeHorizontally(_ phenotype: [Float]) -> [Float] {
     leniaBreeder2024TransformPhenotype(phenotype, transform: { width, _, x, y in
         (width - 1 - x, y)
     })
 }
 
 private func leniaBreeder2024FlipPhenotypeVertically(_ phenotype: [Float]) -> [Float] {
     leniaBreeder2024TransformPhenotype(phenotype, transform: { _, height, x, y in
         (x, height - 1 - y)
     })
 }
 
 private func leniaBreeder2024TransformPhenotype(
     _ phenotype: [Float],
     transform: (_ width: Int, _ height: Int, _ x: Int, _ y: Int) -> (Int, Int)
 ) -> [Float] {
     let channels = 3
     let side = Int(sqrt(Double(phenotype.count / channels)))
     guard side * side * channels == phenotype.count else {
         return phenotype
     }
     var out = Array(repeating: Float(0), count: phenotype.count)
     for y in 0..<side {
         for x in 0..<side {
             let (tx, ty) = transform(side, side, x, y)
             let srcBase = (y * side + x) * channels
             let dstBase = (ty * side + tx) * channels
             for channel in 0..<channels {
                 out[dstBase + channel] = phenotype[srcBase + channel]
             }
         }
     }
     return out
 }
 
 private func leniaBreeder2024InitVAE(
     inputSize: Int,
     hiddenSize: Int,
     latentSize: Int,
     seed: Int
 ) -> LeniaBreeder2024VAEModel {
     var rng = SeededRandomNumberGenerator(seed: UInt64(bitPattern: Int64(seed)) ^ 0x515151)
     func weight(_ rows: Int, _ cols: Int, scale: Float) -> MLXArray {
         let values = (0..<(rows * cols)).map { _ in
             gaussianSample(std: scale, rng: &rng)
         }
         return MLXArray(values).reshaped([rows, cols])
     }
     func bias(_ size: Int) -> MLXArray {
         MLX.zeros([size])
     }
     return LeniaBreeder2024VAEModel(
         encoderW1: weight(inputSize, hiddenSize, scale: 0.02),
         encoderB1: bias(hiddenSize),
         encoderWMu: weight(hiddenSize, latentSize, scale: 0.02),
         encoderBMu: bias(latentSize),
         encoderWLogVar: weight(hiddenSize, latentSize, scale: 0.02),
         encoderBLogVar: bias(latentSize),
         decoderW1: weight(latentSize, hiddenSize, scale: 0.02),
         decoderB1: bias(hiddenSize),
         decoderWOut: weight(hiddenSize, inputSize, scale: 0.02),
         decoderBOut: bias(inputSize)
     )
 }
 
 private func leniaBreeder2024VAEForward(
     inputs: MLXArray,
     model: LeniaBreeder2024VAEModel,
     epsilon: MLXArray
 ) -> (reconstruction: MLXArray, mean: MLXArray, logVar: MLXArray) {
     let hidden = MLX.maximum(MLX.matmul(inputs, model.encoderW1) + model.encoderB1, MLXArray(0))
     let mean = MLX.matmul(hidden, model.encoderWMu) + model.encoderBMu
     let logVar = MLX.matmul(hidden, model.encoderWLogVar) + model.encoderBLogVar
     let latent = mean + MLX.exp(logVar * MLXArray(0.5)) * epsilon
     let decodedHidden = MLX.maximum(MLX.matmul(latent, model.decoderW1) + model.decoderB1, MLXArray(0))
     let reconstruction = MLXArray(1.0) / (MLXArray(1.0) + MLX.exp(-(MLX.matmul(decodedHidden, model.decoderWOut) + model.decoderBOut)))
     return (reconstruction, mean, logVar)
 }
 
 private func leniaBreeder2024TrainVAE(
     model: inout LeniaBreeder2024VAEModel,
     dataset: [[Float]],
     config: LeniaBreeder2024AURORAConfig,
     rng: inout SeededRandomNumberGenerator
 ) -> LeniaBreeder2024AURORATrainingStats? {
     guard !dataset.isEmpty else { return nil }
     var optimizer = MLXAdam(
         paramShapes: model.arrays.map(\.shape),
         learningRate: config.learningRate
     )
     let inputSize = dataset[0].count
     let batchSize = max(1, min(config.autoencoderBatchSize, dataset.count))
     let epochs = max(config.trainRatio, 1)
     var updates = 0
     var reconstructionLossTotal: Float = 0
     var klLossTotal: Float = 0
     var totalLossTotal: Float = 0
     var lastReconstructionLoss: Float = 0
     var lastKLLoss: Float = 0
     var lastTotalLoss: Float = 0
 
     for _ in 0..<epochs {
         var order = Array(dataset.indices)
         order.shuffle(using: &rng)
         for start in stride(from: 0, to: order.count, by: batchSize) {
             let batchIndices = Array(order[start..<min(start + batchSize, order.count)])
             let batch = batchIndices.flatMap { dataset[$0] }
             let batchArray = MLXArray(batch).reshaped([batchIndices.count, inputSize])
             let noise = MLXArray((0..<(batchIndices.count * config.features)).map { _ in
                 gaussianSample(std: 1.0, rng: &rng)
             }).reshaped([batchIndices.count, config.features])
             let objective = valueAndGrad({ (arrays: [MLXArray]) -> [MLXArray] in
                 let model = LeniaBreeder2024VAEModel(arrays: arrays)
                 let forward = leniaBreeder2024VAEForward(inputs: batchArray, model: model, epsilon: noise)
                 let diff = forward.reconstruction - batchArray
                 let reconstructionLoss = MLX.mean(diff * diff)
                 let kl = MLX.mean(
                     MLXArray(-0.5) * (
                         MLXArray(1.0) + forward.logVar - (forward.mean * forward.mean) - MLX.exp(forward.logVar)
                     )
                 )
                 return [reconstructionLoss + MLXArray(1e-3) * kl]
             }, argumentNumbers: Array(model.arrays.indices))
             let (loss, gradients) = objective(model.arrays)
             let forward = leniaBreeder2024VAEForward(inputs: batchArray, model: model, epsilon: noise)
             let diff = forward.reconstruction - batchArray
             let reconstructionLoss = MLX.mean(diff * diff)
             let klLoss = MLX.mean(
                 MLXArray(-0.5) * (
                     MLXArray(1.0) + forward.logVar - (forward.mean * forward.mean) - MLX.exp(forward.logVar)
                 )
             )
             MLX.eval(loss + [reconstructionLoss, klLoss])
             let lossValue = loss[0].item(Float.self)
             let reconstructionValue = reconstructionLoss.item(Float.self)
             let klValue = klLoss.item(Float.self)
             model = LeniaBreeder2024VAEModel(arrays: optimizer.step(params: model.arrays, gradients: gradients))
             MLX.eval(model.arrays)
             updates += 1
             reconstructionLossTotal += reconstructionValue
             klLossTotal += klValue
             totalLossTotal += lossValue
             lastReconstructionLoss = reconstructionValue
             lastKLLoss = klValue
             lastTotalLoss = lossValue
         }
     }
     let denom = Float(max(updates, 1))
     return LeniaBreeder2024AURORATrainingStats(
         epochs: epochs,
         updates: updates,
         datasetSize: dataset.count,
         batchSize: batchSize,
         lastReconstructionLoss: lastReconstructionLoss,
         lastKLLoss: lastKLLoss,
         lastTotalLoss: lastTotalLoss,
         meanReconstructionLoss: reconstructionLossTotal / denom,
         meanKLLoss: klLossTotal / denom,
         meanTotalLoss: totalLossTotal / denom
     )
 }
 
 private func leniaBreeder2024LatentTrajectory(
     model: LeniaBreeder2024VAEModel,
     trajectory: [[Float]]
 ) -> [[Float]] {
     guard !trajectory.isEmpty else { return [] }
     let inputSize = trajectory[0].count
     let batch = MLXArray(trajectory.flatMap { $0 }).reshaped([trajectory.count, inputSize])
     let noise = MLX.zeros([trajectory.count, model.encoderBMu.shape[0]])
     let forward = leniaBreeder2024VAEForward(inputs: batch, model: model, epsilon: noise)
     MLX.eval(forward.mean)
     let flat = forward.mean.asArray(Float.self)
     let latentSize = model.encoderBMu.shape[0]
     guard latentSize > 0, flat.count % latentSize == 0 else {
         return []
     }
     return stride(from: 0, to: flat.count, by: latentSize).map { index in
         Array(flat[index..<(index + latentSize)])
     }
 }
 
 private func leniaBreeder2024ApplyAURORA(
     evaluation: LeniaBreeder2024Evaluation,
     model: LeniaBreeder2024VAEModel,
     config: LeniaBreeder2024AURORAConfig,
     nChannel: Int,
     phenotypeSize: Int
 ) throws -> LeniaBreeder2024Evaluation {
     let trajectory = evaluation.phenotypeTrajectory
     guard !trajectory.isEmpty else {
         return LeniaBreeder2024Evaluation(
             fitness: -.infinity,
             descriptor: Array(repeating: 0, count: config.features),
             failed: true,
             phenotype: evaluation.phenotype,
             phenotypeTrajectory: evaluation.phenotypeTrajectory,
             creatureSummary: evaluation.creatureSummary
         )
     }
     let latent = leniaBreeder2024LatentTrajectory(model: model, trajectory: trajectory)
     guard !latent.isEmpty else {
         return LeniaBreeder2024Evaluation(
             fitness: -.infinity,
             descriptor: Array(repeating: 0, count: config.features),
             failed: true,
             phenotype: evaluation.phenotype,
             phenotypeTrajectory: evaluation.phenotypeTrajectory,
             creatureSummary: evaluation.creatureSummary
         )
     }
     let descriptor = leniaBreeder2024MeanVector(latent)
     let unsupervised = leniaBreeder2024LatentStability(latent: latent, descriptor: descriptor)
     let primaryFitness = try leniaBreeder2024ResolveAURORAFitness(
         name: config.fitness,
         manualFitness: evaluation.fitness,
         unsupervisedFitness: unsupervised
     )
     let totalFitness: Float
     if let secondary = config.secondaryFitness {
         let secondaryValue = try leniaBreeder2024ResolveAURORAFitness(
             name: secondary,
             manualFitness: evaluation.fitness,
             unsupervisedFitness: unsupervised
         )
         totalFitness = primaryFitness + config.secondaryFitnessWeight * secondaryValue
     } else {
         totalFitness = primaryFitness
     }
     return LeniaBreeder2024Evaluation(
         fitness: totalFitness,
         descriptor: descriptor,
         failed: evaluation.failed,
         phenotype: evaluation.phenotype,
         phenotypeTrajectory: evaluation.phenotypeTrajectory,
         creatureSummary: evaluation.creatureSummary
     )
 }
 
 private func leniaBreeder2024ResolveAURORAFitness(
     name: String,
     manualFitness: Float,
     unsupervisedFitness: Float
 ) throws -> Float {
     switch name {
     case "unsupervised", "neg_latent_dispersion":
         return unsupervisedFitness
     default:
         return manualFitness
     }
 }
 
 private func leniaBreeder2024CreatureSummary(
     mass: [Float],
     centerX: [Float],
     centerY: [Float],
     linearVelocity: [Float],
     phenotype: [Float],
     phenotypeSize: Int,
     nChannel: Int,
     failed: Bool
 ) -> LeniaBreeder2024CreatureSummary {
     let massMean = leniaBreeder2024Mean(mass)
     let massStd = leniaBreeder2024Std(mass, mean: massMean)
     let massMin = mass.min() ?? 0
     let massMax = mass.max() ?? 0
     let speedMean = leniaBreeder2024Mean(linearVelocity)
     let pathLength = linearVelocity.reduce(0, +)
     let dx = (centerX.last ?? 0) - (centerX.first ?? 0)
     let dy = (centerY.last ?? 0) - (centerY.first ?? 0)
     let displacement = sqrt(dx * dx + dy * dy)
     let dt = Float(max(centerX.count - 1, 1))
     let velocityX = dx / dt
     let velocityY = dy / dt
     let centerVelocity = displacement / dt
     let headingRad = atan2(velocityY, velocityX)
     let phenotypeStats = leniaBreeder2024PhenotypeStats(
         phenotype: phenotype,
         phenotypeSize: phenotypeSize,
         nChannel: nChannel
     )
     return LeniaBreeder2024CreatureSummary(
         massMean: massMean,
         massStd: massStd,
         massMin: massMin,
         massMax: massMax,
         occupancyMean: phenotypeStats.occupancyMean,
         varianceMean: phenotypeStats.varianceMean,
         energyMean: phenotypeStats.energyMean,
         speedMean: speedMean,
         pathLength: pathLength,
         displacement: displacement,
         sampleCount: mass.count,
         speedCount: linearVelocity.count,
         gyration: phenotypeStats.gyration,
         centerVelocity: centerVelocity,
         velocityX: velocityX,
         velocityY: velocityY,
         headingRad: headingRad,
         isStable: !failed
     )
 }
 
 private func leniaBreeder2024PhenotypeStats(
     phenotype: [Float],
     phenotypeSize: Int,
     nChannel: Int
 ) -> (occupancyMean: Float, varianceMean: Float, energyMean: Float, gyration: Float) {
     guard phenotypeSize > 0, nChannel > 0, phenotype.count == phenotypeSize * phenotypeSize * nChannel else {
         return (0, 0, 0, 0)
     }
 
     var mass: Float = 0
     var occupied: Int = 0
     var sum: Float = 0
     var sumSquares: Float = 0
     var rowWeighted: Float = 0
     var colWeighted: Float = 0
 
     for row in 0..<phenotypeSize {
         for col in 0..<phenotypeSize {
             let base = (row * phenotypeSize + col) * nChannel
             let value = (0..<nChannel).reduce(Float(0)) { partial, channel in
                 partial + max(phenotype[base + channel], 0)
             }
             sum += value
             sumSquares += value * value
             if value > 1e-3 {
                 occupied += 1
             }
             mass += value
             rowWeighted += Float(row) * value
             colWeighted += Float(col) * value
         }
     }
 
     let count = Float(max(phenotypeSize * phenotypeSize, 1))
     let mean = sum / count
     let variance = max(0, (sumSquares / count) - mean * mean)
     guard mass > 1e-6 else {
         return (
             occupancyMean: Float(occupied) / count,
             varianceMean: variance,
             energyMean: mean,
             gyration: 0
         )
     }
 
     let centerRow = rowWeighted / mass
     let centerCol = colWeighted / mass
     var gyrationNumerator: Float = 0
     for row in 0..<phenotypeSize {
         for col in 0..<phenotypeSize {
             let base = (row * phenotypeSize + col) * nChannel
             let value = (0..<nChannel).reduce(Float(0)) { partial, channel in
                 partial + max(phenotype[base + channel], 0)
             }
             let dRow = Float(row) - centerRow
             let dCol = Float(col) - centerCol
             gyrationNumerator += value * (dRow * dRow + dCol * dCol)
         }
     }
 
     return (
         occupancyMean: Float(occupied) / count,
         varianceMean: variance,
         energyMean: mean,
         gyration: gyrationNumerator / mass
     )
 }
 
 private func leniaBreeder2024Mean(_ values: [Float]) -> Float {
     guard !values.isEmpty else { return 0 }
     return values.reduce(0, +) / Float(values.count)
 }
 
 private func leniaBreeder2024Std(_ values: [Float], mean: Float) -> Float {
     guard !values.isEmpty else { return 0 }
     let variance = values.reduce(Float(0)) { partial, value in
         let diff = value - mean
         return partial + diff * diff
     } / Float(values.count)
     return sqrt(max(variance, 0))
 }
 
 private func leniaBreeder2024MeanVector(_ vectors: [[Float]]) -> [Float] {
     guard let first = vectors.first else { return [] }
     var mean = Array(repeating: Float(0), count: first.count)
     for vector in vectors {
         for index in vector.indices {
             mean[index] += vector[index]
         }
     }
     let count = Float(vectors.count)
     return mean.map { $0 / count }
 }
 
 private func leniaBreeder2024LatentStability(
     latent: [[Float]],
     descriptor: [Float]
 ) -> Float {
     guard !latent.isEmpty else { return -.infinity }
     let total = latent.reduce(Float(0)) { partial, vector in
         partial + sqrt(zip(vector, descriptor).reduce(Float(0)) { inner, pair in
             let diff = pair.0 - pair.1
             return inner + diff * diff
         })
     }
     return -(total / Float(latent.count))
 }
 
 private func leniaBreeder2024AURORADescriptorStats(
     evaluations: [LeniaBreeder2024Evaluation],
     nearZeroThreshold: Float
 ) -> LeniaBreeder2024AURORADescriptorStats {
     let descriptors = evaluations.map(\.descriptor)
     let failedCount = evaluations.reduce(0) { $0 + ($1.failed ? 1 : 0) }
     let finiteFitnessCount = evaluations.reduce(0) { $0 + ($1.fitness.isFinite ? 1 : 0) }
     return leniaBreeder2024AURORADescriptorStats(
         descriptors: descriptors,
         finiteFitnessCount: finiteFitnessCount,
         failedCount: failedCount,
         nearZeroThreshold: nearZeroThreshold
     )
 }
 
 private func leniaBreeder2024AURORADescriptorStats(
     descriptors: [[Float]],
     finiteFitnessCount: Int,
     failedCount: Int,
     nearZeroThreshold: Float
 ) -> LeniaBreeder2024AURORADescriptorStats {
     guard let first = descriptors.first else {
         return LeniaBreeder2024AURORADescriptorStats(
             count: 0,
             finiteFitnessCount: finiteFitnessCount,
             failedCount: failedCount,
             descriptorNormMean: 0,
             descriptorNormStd: 0,
             descriptorAbsMean: 0,
             dimensionStdMean: 0,
             nearZeroFraction: 0
         )
     }
 
     var norms: [Float] = []
     norms.reserveCapacity(descriptors.count)
     var absTotal: Float = 0
     var zeroCount = 0
     var dimMeans = Array(repeating: Float(0), count: first.count)
 
     for descriptor in descriptors {
         let normSquared = descriptor.reduce(Float(0)) { partial, value in
             partial + value * value
         }
         let norm = sqrt(normSquared)
         norms.append(norm)
         absTotal += descriptor.reduce(Float(0)) { $0 + abs($1) }
         if norm <= nearZeroThreshold {
             zeroCount += 1
         }
         for index in descriptor.indices {
             dimMeans[index] += descriptor[index]
         }
     }
 
     let descriptorCount = Float(max(descriptors.count, 1))
     for index in dimMeans.indices {
         dimMeans[index] /= descriptorCount
     }
     var dimVarianceTotal: Float = 0
     for descriptor in descriptors {
         for index in descriptor.indices {
             let diff = descriptor[index] - dimMeans[index]
             dimVarianceTotal += diff * diff
         }
     }
     let meanNorm = norms.reduce(0, +) / descriptorCount
     let normVariance = norms.reduce(Float(0)) { partial, norm in
         let diff = norm - meanNorm
         return partial + diff * diff
     } / descriptorCount
     let dimensionDenom = Float(max(first.count, 1))
 
     return LeniaBreeder2024AURORADescriptorStats(
         count: descriptors.count,
         finiteFitnessCount: finiteFitnessCount,
         failedCount: failedCount,
         descriptorNormMean: meanNorm,
         descriptorNormStd: sqrt(normVariance),
         descriptorAbsMean: absTotal / (descriptorCount * dimensionDenom),
         dimensionStdMean: sqrt(dimVarianceTotal / (descriptorCount * dimensionDenom)),
         nearZeroFraction: Float(zeroCount) / descriptorCount
     )
 }
 
 private func leniaBreeder2024RebuildAURORARepertoire(
     from old: LeniaBreeder2024Repertoire,
     model: LeniaBreeder2024VAEModel,
     config: LeniaBreeder2024AURORAConfig,
     genotypeSize: Int,
     nChannel: Int,
     phenotypeSize: Int
 ) throws -> LeniaBreeder2024Repertoire {
     var rebuilt = LeniaBreeder2024Repertoire(centroids: old.centroids, genotypeSize: genotypeSize)
     let occupiedCells = old.occupiedIndices()
     let genotypes = occupiedCells.map { old.genotypes[$0] }
     let evaluations = try occupiedCells.compactMap { cell -> LeniaBreeder2024Evaluation? in
         guard let trajectory = old.phenotypeTrajectories[cell],
               let creatureSummary = old.creatureSummaries[cell] else {
             return nil
         }
         let previous = LeniaBreeder2024Evaluation(
             fitness: old.fitnesses[cell],
             descriptor: old.descriptors[cell],
             failed: false,
             phenotype: old.phenotypes[cell],
             phenotypeTrajectory: trajectory,
             creatureSummary: creatureSummary
         )
         return try leniaBreeder2024ApplyAURORA(
             evaluation: previous,
             model: model,
             config: config,
             nChannel: nChannel,
             phenotypeSize: phenotypeSize
         )
     }
     for ((cell, genotype), evaluation) in zip(zip(occupiedCells, genotypes), evaluations) {
         _ = rebuilt.add(genotypes: [genotype], evaluations: [evaluation], generation: old.generations[cell])
     }
     return rebuilt
 }
 
 private func leniaBreeder2024WriteVAEMetadata(
     model: LeniaBreeder2024VAEModel,
     config: LeniaBreeder2024AURORAConfig,
     lastTrainingStats: LeniaBreeder2024AURORATrainingStats?,
     to url: URL
 ) throws {
     var metadata: [String: Any] = [
         "latent_dim": config.features,
         "hidden_size": config.hiddenSize,
         "train_ratio": config.trainRatio,
         "ae_batch_size": config.autoencoderBatchSize,
         "parameter_shapes": model.arrays.map(\.shape),
     ]
     if let lastTrainingStats {
         metadata["last_training"] = [
             "epochs": lastTrainingStats.epochs,
             "updates": lastTrainingStats.updates,
             "dataset_size": lastTrainingStats.datasetSize,
             "batch_size": lastTrainingStats.batchSize,
             "last_reconstruction_loss": lastTrainingStats.lastReconstructionLoss,
             "last_kl_loss": lastTrainingStats.lastKLLoss,
             "last_total_loss": lastTrainingStats.lastTotalLoss,
             "mean_reconstruction_loss": lastTrainingStats.meanReconstructionLoss,
             "mean_kl_loss": lastTrainingStats.meanKLLoss,
             "mean_total_loss": lastTrainingStats.meanTotalLoss,
         ]
     }
     try JSONSerialization.data(withJSONObject: metadata, options: [.prettyPrinted, .sortedKeys]).write(to: url)
 }
 
 private func leniaBreeder2024ComputeCVTCentroids(
     count: Int,
     descriptorMin: [Float],
     descriptorMax: [Float],
     sampleCount: Int,
     seed: Int
 ) -> [[Float]] {
     precondition(descriptorMin.count == descriptorMax.count)
     precondition(!descriptorMin.isEmpty)
 
     var rng = SeededRandomNumberGenerator(seed: UInt64(bitPattern: Int64(seed)) ^ 0xC0FFEE)
     let samples: [[Float]] = (0..<sampleCount).map { _ in
         zip(descriptorMin, descriptorMax).map { minVal, maxVal in
             Float.random(in: 0..<1, using: &rng) * (maxVal - minVal) + minVal
         }
     }
     var centroids = (0..<count).map { _ in
         samples[Int.random(in: 0..<samples.count, using: &rng)]
     }
     for _ in 0..<16 {
         var sums = Array(repeating: Array(repeating: Float(0), count: descriptorMin.count), count: count)
         var counts = Array(repeating: 0, count: count)
         for sample in samples {
             var bestIndex = 0
             var bestDistance = Float.infinity
             for (index, centroid) in centroids.enumerated() {
                 let distance = zip(sample, centroid).reduce(Float(0)) { partial, pair in
                     let diff = pair.0 - pair.1
                     return partial + diff * diff
                 }
                 if distance < bestDistance {
                     bestDistance = distance
                     bestIndex = index
                 }
             }
             for dim in sample.indices {
                 sums[bestIndex][dim] += sample[dim]
             }
             counts[bestIndex] += 1
         }
         for index in centroids.indices {
             guard counts[index] > 0 else { continue }
             for dim in centroids[index].indices {
                 centroids[index][dim] = sums[index][dim] / Float(counts[index])
             }
         }
     }
     return centroids
 }
 
 private func leniaBreeder2024WriteLibraryIndex(
     repertoire: LeniaBreeder2024Repertoire,
     assets: LeniaBreeder2024Assets,
     runId: String,
     algorithm: String,
     patternID: String,
     configHash: String,
     distributed: Bool,
     canonicalExportAvailable: Bool = false,
     outputDirectory: URL
 ) throws {
     let entries = try repertoire.occupiedIndices().compactMap { cell -> ResearchLibraryEntry? in
         guard let creatureSummary = repertoire.creatureSummaries[cell] else {
             return nil
         }
         let stableKey = "\(runId)|\(algorithm)|\(cell)"
         var metadata: [String: AnyCodable] = try [
             "version": researchMetadataValue(1),
             "mode": researchMetadataValue("qd-2024"),
             "morphospace_payload": researchMetadataValue("summary_only_metrics_v1"),
             "morphospace_ready": researchMetadataValue(false),
             "algorithm": researchMetadataValue(algorithm),
             "generation": researchMetadataValue(repertoire.generations[cell]),
             "cell": researchMetadataValue(cell),
             "descriptor": researchMetadataValue(repertoire.descriptors[cell]),
             "centroid": researchMetadataValue(repertoire.centroids[cell]),
             "fitness": researchMetadataValue(repertoire.fitnesses[cell]),
             "pattern_id": researchMetadataValue(patternID),
             "distributed": researchMetadataValue(distributed),
             "genotype": researchMetadataValue(repertoire.genotypes[cell]),
         ]
         if canonicalExportAvailable {
             metadata["canonical_export_available"] = try researchMetadataValue(true)
             metadata["canonical_export_kind"] = try researchMetadataValue("qd24_paper_replay_bundle_v1")
         }
        return archiveResearchLibraryEntry(
            creature: archivedCreature(
                stableKey: stableKey,
                name: "qd-\(algorithm)-cell-\(cell)",
                ownerId: "qd-2024",
                genotype: leniaBreeder2024KernelParams(
                    genotype: repertoire.genotypes[cell],
                    assets: assets
                ),
                initialCondition: InitConfig(
                    seed: cell,
                    patches: [],
                    a_uniform: UniformRange(low: 0, high: 0),
                    p_uniform: nil
                ),
                metrics: leniaBreeder2024SimulationMetrics(summary: creatureSummary),
                sweep: ["cell": Double(cell)],
                score: repertoire.fitnesses[cell],
                scoreWeights: ["fitness": 1.0],
                configHash: configHash
            ),
            runId: runId,
            configHash: configHash,
            sourceMode: "qd-2024",
            sourceAlgorithm: algorithm,
            researchMetadata: metadata
        )
     }
     _ = try ResearchLibraryWriter.write(entries: entries, runDirectory: outputDirectory)
 }
 
 private func leniaBreeder2024WriteReplayExports(
     run: LeniaBreeder2024ResolvedRun,
     repertoire: LeniaBreeder2024Repertoire,
     runId: String,
     algorithm: String,
     configHash: String,
     outputDirectory: URL
 ) throws {
     let exportsDirectory = outputDirectory.appendingPathComponent("exports", isDirectory: true)
     let cells = repertoire.occupiedIndices().filter { repertoire.creatureSummaries[$0] != nil }
     _ = try writePayloadReplayExportBatch(
         exportRoot: exportsDirectory,
         items: cells
     ) { cell in
         guard let creatureSummary = repertoire.creatureSummaries[cell] else {
             throw ConfigError.invalidConfig("leniabreeder-2024 missing creature summary for occupied cell \(cell).")
         }
         let elite = LeniaBreeder2024EliteSummary(
             cell: cell,
             generation: repertoire.generations[cell],
             centroid: repertoire.centroids[cell],
             descriptor: repertoire.descriptors[cell],
             fitness: repertoire.fitnesses[cell],
             genotype: repertoire.genotypes[cell]
         )
         let expressedSeed = try expressLeniaBreeder2024Seed(
             run: run,
             elite: elite,
             algorithmOverride: algorithm
         )
         let statePatch = expressedSeed.world.toInitStatePatch(
             center: [run.base.worldSize / 2, run.base.worldSize / 2]
         )
         let creature = archivedCreature(
            stableKey: "\(runId)|\(algorithm)|\(cell)|canonical-export",
             name: "qd-\(algorithm)-cell-\(cell)",
             ownerId: "qd-2024",
             genotype: expressedSeed.kernelParams,
             initialCondition: InitConfig(
                 seed: cell,
                 patches: [],
                 a_uniform: UniformRange(low: 0, high: 0),
                 p_uniform: nil,
                 state_patch: statePatch
             ),
             metrics: leniaBreeder2024SimulationMetrics(summary: creatureSummary),
             sweep: ["cell": Double(cell)],
             score: repertoire.fitnesses[cell],
             scoreWeights: ["fitness": 1.0],
             configHash: configHash
         )
         let payload = LeniaBreeder2024ReplayPayload(
             algorithm: algorithm,
             base: run.base,
             mapElites: run.mapElites,
             aurora: run.aurora,
             pattern: run.pattern,
             elite: elite
         )
         return (
             creature: creature,
             runId: runId,
             campaignId: nil,
             bundleKind: .qd24PaperReplayBundleV1,
             payload: payload,
             reason: "qd-2024:\(algorithm)",
             score: repertoire.fitnesses[cell],
             filtersPassed: nil,
             exportedAt: Date()
         )
     }
}
 
 private func leniaBreeder2024KernelParams(
     genotype: [Float],
     assets: LeniaBreeder2024Assets
 ) -> KernelParams {
     let nKernel = assets.nKernel
     let params = Array(genotype[0..<assets.nParams])
     let m = Array(params[0..<nKernel])
     let s = Array(params[nKernel..<(2 * nKernel)])
     let h = Array(params[(2 * nKernel)..<(3 * nKernel)])
     let fixedB = assets.pattern.kernels.map(\.b)
     let fixedR = assets.pattern.kernels.map(\.r)
     let placeholder = fixedB.map { Array(repeating: Float(0), count: $0.count) }
     return KernelParams(
         r: fixedR,
         b: fixedB,
         w: placeholder,
         a: placeholder,
         m: m,
         s: s,
         h: h,
         R: Float(assets.pattern.R)
     )
 }
 
 private func leniaBreeder2024SimulationMetrics(summary: LeniaBreeder2024CreatureSummary) -> SimulationMetrics {
     SimulationMetrics(
         massMean: summary.massMean,
         massStd: summary.massStd,
         massMin: summary.massMin,
         massMax: summary.massMax,
         occupancyMean: summary.occupancyMean,
         varianceMean: summary.varianceMean,
         energyMean: summary.energyMean,
         speedMean: summary.speedMean,
         pathLength: summary.pathLength,
         displacement: summary.displacement,
         sampleCount: summary.sampleCount,
         speedCount: summary.speedCount,
         gyration: summary.gyration,
         centerVelocity: summary.centerVelocity,
         velocityX: summary.velocityX,
         velocityY: summary.velocityY,
         headingRad: summary.headingRad,
         isStable: summary.isStable
     )
 }
 
 public struct LeniaBreeder2024ReplayOutcome: Sendable {
     public let resultData: SimulationResultData
     public let creature: SavedCreature
 
     public init(resultData: SimulationResultData, creature: SavedCreature) {
         self.resultData = resultData
         self.creature = creature
     }
 }
 
 public func replayLeniaBreeder2024Payload(
     _ payload: LeniaBreeder2024ReplayPayload,
     runId: String,
     configHash: String? = nil
 ) throws -> LeniaBreeder2024ReplayOutcome {
     let run = LeniaBreeder2024ResolvedRun(
         runDirectory: URL(fileURLWithPath: "/tmp/leniabreeder-2024-replay", isDirectory: true),
         configDirectory: nil,
         base: payload.base,
         mapElites: payload.mapElites,
         aurora: payload.aurora,
         pattern: payload.pattern,
         defaultAlgorithm: payload.algorithm
     )
     let assets = try leniaBreeder2024ResolvedAssets(run: run, algorithm: payload.algorithm)
     guard let evaluation = try leniaBreeder2024EvaluatePopulation(
         genotypes: [payload.elite.genotype],
         assets: assets,
         descriptorNames: leniaBreeder2024DescriptorNames(run: run, algorithm: payload.algorithm),
         fitnessName: leniaBreeder2024FitnessName(run: run, algorithm: payload.algorithm)
     ).first else {
         throw ConfigError.invalidConfig("leniabreeder-2024 replay produced no evaluation.")
     }
     let diagnostics = try leniaBreeder2024ReplayDiagnostics(
         genotype: payload.elite.genotype,
         assets: assets
     )
     let expressedSeed = try expressLeniaBreeder2024Seed(
         run: run,
         elite: payload.elite,
         algorithmOverride: payload.algorithm
     )
     let statePatch = expressedSeed.world.toInitStatePatch(
         center: [expressedSeed.world.width / 2, expressedSeed.world.height / 2]
     )
     let initialCondition = InitConfig(
         seed: payload.elite.cell,
         patches: [],
         a_uniform: UniformRange(low: 0, high: 0),
         p_uniform: nil,
         state_patch: statePatch
     )
     let metrics = leniaBreeder2024SimulationMetrics(summary: evaluation.creatureSummary)
     let morphometrics = Morphometrics.from(metrics: metrics, activity: nil)
     let finalMassSummary = morphospaceFinalSampleSummary(
         materialized: MassBatchCPU(
             flat: diagnostics.finalMassMap,
             batch: 1,
             height: expressedSeed.world.height,
             width: expressedSeed.world.width,
             sampleSize: expressedSeed.world.width * expressedSeed.world.height
         ),
         sampleIndex: 0,
         occupancyThreshold: 0.01,
         useTorus: false
     )
     let headingCircularVariance: Float?
     if diagnostics.angleHistory.isEmpty {
         headingCircularVariance = nil
     } else {
         let sinAcc = diagnostics.angleHistory.reduce(Double(0)) { $0 + Double(sin(Double($1) * Double.pi)) }
         let cosAcc = diagnostics.angleHistory.reduce(Double(0)) { $0 + Double(cos(Double($1) * Double.pi)) }
         let resultant = sqrt(sinAcc * sinAcc + cosAcc * cosAcc) / Double(diagnostics.angleHistory.count)
         headingCircularVariance = Float(max(0, 1 - resultant))
     }
     let accumulatedTurnAbs: Float?
     if diagnostics.angleHistory.count < 2 {
         accumulatedTurnAbs = nil
     } else {
         var total: Float = 0
         for index in 1..<diagnostics.angleHistory.count {
             var diff = fmodf(diagnostics.angleHistory[index] - diagnostics.angleHistory[index - 1] + 3, 2) - 1
             if !diff.isFinite {
                 diff = 0
             }
             total += abs(diff)
         }
         accumulatedTurnAbs = total
     }
     let descriptorBundle = MorphospaceDescriptorBundle(
         symmetryPolicy: "translation_only_v1",
         genotype: morphospaceOpaqueGenotypeDescriptor(
             vector: payload.elite.genotype,
             kernelCount: payload.pattern.kernels.count,
             canonicalizer: "qd24_elite_identity_v1"
         ),
         terminal: MorphospaceTerminalDescriptor(
             massChannel: 0,
             borderMode: "wall",
             symmetryPolicy: "translation_only_v1",
             fingerprintResolution: finalMassSummary.fingerprintResolution,
             fingerprintU8: finalMassSummary.fingerprintU8,
             angularSymmetry: finalMassSummary.angularSymmetry,
             fingerprintHash12: finalMassSummary.fingerprintHash12,
             finalMass: finalMassSummary.finalMass,
             finalOccupancy: finalMassSummary.finalOccupancy,
             finalGyration: finalMassSummary.finalGyration,
             momentMass: nil,
             momentVolume: nil,
             momentDensity: nil,
             momentAnisotropy: nil,
             componentCount: nil,
             largestComponentFraction: nil,
             largestComponentAnisotropy: nil,
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
             isStable: metrics.isStable
         ),
         trajectory: MorphospaceTrajectoryDescriptor(
             recordInterval: 1,
             warmupSteps: 0,
             sampleCount: max(metrics.sampleCount, 1),
             pathLength: metrics.pathLength,
             displacement: metrics.displacement,
             pathTortuosity: morphometrics.pathTortuosity,
             movementEfficiency: morphometrics.movementEfficiency,
             speedMean: metrics.speedMean,
             centerVelocity: metrics.centerVelocity,
             velocityX: metrics.velocityX,
             velocityY: metrics.velocityY,
             headingRad: metrics.headingRad,
             headingCircularVariance: headingCircularVariance,
             accumulatedTurnAbs: accumulatedTurnAbs,
             survivalSteps: nil,
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
     let resultData = materializeReplayResultData(
         seed: payload.elite.cell,
         initSeed: payload.elite.cell,
         backend: "qd24-paper",
         implementation: ImplementationSettings(
             mode: "qd24-paper",
             border: "wall",
             gradientBoundary: "n/a",
             alphaMode: "n/a",
             kernelProfile: "qd24_bucketed_v1",
             flowClip: "n/a"
         ),
         initialConditionFamily: initialConditionFamily,
         descriptorBundle: descriptorBundle,
         score: evaluation.fitness,
         scoreWeights: ["fitness": 1.0],
         filtersPassed: evaluation.fitness.isFinite && !evaluation.failed,
         filters: [:],
         metrics: metrics,
         activity: nil,
         params: expressedSeed.kernelParams,
         sweep: ["cell": Double(payload.elite.cell)]
     )
     let creature = archivedCreatureFromResult(
         stableKey: "\(runId)|\(payload.algorithm)|\(payload.elite.cell)|replayed",
         name: "qd-\(payload.algorithm)-cell-\(payload.elite.cell)",
         ownerId: "qd-2024",
         result: resultData,
         initialCondition: initialCondition,
         configHash: configHash,
         sweep: ["cell": Double(payload.elite.cell)],
     )
     return LeniaBreeder2024ReplayOutcome(resultData: resultData, creature: creature)
 }
 
 private func leniaBreeder2024ReplayDiagnostics(
     genotype: [Float],
     assets: LeniaBreeder2024Assets
 ) throws -> (finalMassMap: [Float], angleHistory: [Float]) {
     var carry = try leniaBreeder2024ExpressPopulation(genotypes: [genotype], assets: assets)
     var angleHistory: [Float] = []
     angleHistory.reserveCapacity(max(assets.steps, 1))
     for _ in 0..<assets.steps {
         let step = leniaBreeder2024StepBatch(
             carry: carry,
             assets: assets,
             recordPhenotype: false
         )
         carry = step.carry
         angleHistory.append(step.angle[0])
     }
     return (try leniaBreeder2024WorldMassMap(carry.world), angleHistory)
 }
 
 private func leniaBreeder2024MAPElitesConfigHash(
     base: LeniaBreeder2024BaseConfig,
     mapElites: LeniaBreeder2024MAPElitesConfig,
     pattern: LeniaBreeder2024PatternSpec
 ) throws -> String {
     try leniaBreeder2024SpecHash(base: base, mapElites: mapElites, pattern: pattern)
 }
 
 private func leniaBreeder2024AURORAConfigHash(
     base: LeniaBreeder2024BaseConfig,
     aurora: LeniaBreeder2024AURORAConfig,
     pattern: LeniaBreeder2024PatternSpec
 ) throws -> String {
     let encoder = JSONEncoder()
     encoder.outputFormatting = [.sortedKeys]
     var data = Data()
     data.append(try encoder.encode(base))
     data.append(try encoder.encode(aurora))
     data.append(try encoder.encode(pattern))
     var hash: UInt64 = 0xcbf29ce484222325
     for byte in data {
         hash ^= UInt64(byte)
         hash &*= 0x100000001b3
     }
     return String(format: "%016llx", hash)
 }
 
 public func loadLeniaBreeder2024ResolvedRun(
     runDirectory: URL,
     configDirectoryOverride: URL? = nil
 ) throws -> LeniaBreeder2024ResolvedRun {
     let decoder = JSONDecoder()
     let base = try decoder.decode(
         LeniaBreeder2024BaseConfig.self,
         from: Data(contentsOf: runDirectory.appendingPathComponent("base.json"))
     )
     let mapElites = try decoder.decode(
         LeniaBreeder2024MAPElitesConfig.self,
         from: Data(contentsOf: runDirectory.appendingPathComponent("me.json"))
     )
     let aurora = try decoder.decode(
         LeniaBreeder2024AURORAConfig.self,
         from: Data(contentsOf: runDirectory.appendingPathComponent("aurora.json"))
     )
 
     let pattern = try loadLeniaBreeder2024Pattern(
         runDirectory: runDirectory,
         configDirectoryOverride: configDirectoryOverride,
         patternID: base.patternID,
         decoder: decoder
     )
 
     let defaultAlgorithm: String
     let summaryURL = runDirectory.appendingPathComponent("summary.json")
     if FileManager.default.fileExists(atPath: summaryURL.path),
        let summary = try? decoder.decode(LeniaBreeder2024RunSummary.self, from: Data(contentsOf: summaryURL)) {
         defaultAlgorithm = summary.algorithm
     } else {
         defaultAlgorithm = mapElites.algorithm
     }
 
     return LeniaBreeder2024ResolvedRun(
         runDirectory: runDirectory,
         configDirectory: configDirectoryOverride,
         base: base,
         mapElites: mapElites,
         aurora: aurora,
         pattern: pattern,
         defaultAlgorithm: defaultAlgorithm
     )
 }
 
 public func loadLeniaBreeder2024EliteSummaries(runDirectory: URL) throws -> [LeniaBreeder2024EliteSummary] {
     let url = runDirectory.appendingPathComponent("repertoire/occupied.json")
     let data = try Data(contentsOf: url)
     return try JSONDecoder().decode([LeniaBreeder2024EliteSummary].self, from: data)
 }
 
 public func evaluateLeniaBreeder2024Elites(
     run: LeniaBreeder2024ResolvedRun,
     elites: [LeniaBreeder2024EliteSummary],
     algorithmOverride: String? = nil
 ) throws -> [LeniaBreeder2024EvaluatedElite] {
     guard !elites.isEmpty else { return [] }
     let algorithm = leniaBreeder2024ResolvedAlgorithm(run: run, override: algorithmOverride)
     let assets = try leniaBreeder2024ResolvedAssets(run: run, algorithm: algorithm)
     let descriptorNames = leniaBreeder2024DescriptorNames(run: run, algorithm: algorithm)
     let fitnessName = leniaBreeder2024FitnessName(run: run, algorithm: algorithm)
     let evaluations = try leniaBreeder2024EvaluatePopulation(
         genotypes: elites.map(\.genotype),
         assets: assets,
         descriptorNames: descriptorNames,
         fitnessName: fitnessName
     )
     return zip(elites, evaluations).map { elite, evaluation in
         LeniaBreeder2024EvaluatedElite(
             elite: elite,
             kernelParams: leniaBreeder2024KernelParams(genotype: elite.genotype, assets: assets),
             metrics: leniaBreeder2024SimulationMetrics(summary: evaluation.creatureSummary),
             summary: evaluation.creatureSummary
         )
     }
 }
 
public func captureLeniaBreeder2024ReplayFrames(
    run: LeniaBreeder2024ResolvedRun,
    elite: LeniaBreeder2024EliteSummary,
    algorithmOverride: String? = nil,
    frameBudget: Int,
    stepsOverride: Int? = nil
) throws -> [Data] {
    let selected = try captureLeniaBreeder2024ReplayMassMaps(
        run: run,
        elite: elite,
        algorithmOverride: algorithmOverride,
        frameBudget: frameBudget,
        stepsOverride: stepsOverride
    )
    return leniaBreeder2024ByteFrames(selected)
}

public func captureLeniaBreeder2024ReplayStatePatches(
    run: LeniaBreeder2024ResolvedRun,
    elite: LeniaBreeder2024EliteSummary,
    algorithmOverride: String? = nil,
    frameBudget: Int,
    stepsOverride: Int? = nil
) throws -> [InitStatePatchConfig] {
    let selected = try captureLeniaBreeder2024ReplayMassMaps(
        run: run,
        elite: elite,
        algorithmOverride: algorithmOverride,
        frameBudget: frameBudget,
        stepsOverride: stepsOverride
    )
    return selected.map { frame in
        InitStatePatchConfig(
            center: [run.base.worldSize / 2, run.base.worldSize / 2],
            width: run.base.worldSize,
            height: run.base.worldSize,
            channels: 1,
            values: frame
        )
    }
}

public func captureLeniaBreeder2024ReplayFramesAtSteps(
    run: LeniaBreeder2024ResolvedRun,
    elite: LeniaBreeder2024EliteSummary,
    algorithmOverride: String? = nil,
    steps: [Int],
    stepsOverride: Int? = nil
) throws -> [Data] {
    let selected = try captureLeniaBreeder2024ReplayMassMapsAtSteps(
        run: run,
        elite: elite,
        algorithmOverride: algorithmOverride,
        steps: steps,
        stepsOverride: stepsOverride
    )
    return leniaBreeder2024ByteFrames(selected)
}

public func captureLeniaBreeder2024ReplayStatePatchesAtSteps(
    run: LeniaBreeder2024ResolvedRun,
    elite: LeniaBreeder2024EliteSummary,
    algorithmOverride: String? = nil,
    steps: [Int],
    stepsOverride: Int? = nil
) throws -> [InitStatePatchConfig] {
    let selected = try captureLeniaBreeder2024ReplayMassMapsAtSteps(
        run: run,
        elite: elite,
        algorithmOverride: algorithmOverride,
        steps: steps,
        stepsOverride: stepsOverride
    )
    return selected.map { frame in
        InitStatePatchConfig(
            center: [run.base.worldSize / 2, run.base.worldSize / 2],
            width: run.base.worldSize,
            height: run.base.worldSize,
            channels: 1,
            values: frame
        )
    }
}

public func captureLeniaBreeder2024ReplayMassMapsAtSteps(
    run: LeniaBreeder2024ResolvedRun,
    elite: LeniaBreeder2024EliteSummary,
    algorithmOverride: String? = nil,
    steps: [Int],
    stepsOverride: Int? = nil
) throws -> [[Float]] {
    guard !steps.isEmpty else { return [] }
    guard let maxRequestedStep = steps.max(), maxRequestedStep >= 0, steps.allSatisfy({ $0 >= 0 }) else {
        throw ConfigError.invalidConfig("leniabreeder-2024 replay steps must be non-negative.")
    }
    if let stepsOverride, stepsOverride < 0 {
        throw ConfigError.invalidConfig("leniabreeder-2024 steps_override must be non-negative.")
    }

    let algorithm = leniaBreeder2024ResolvedAlgorithm(run: run, override: algorithmOverride)
    let assets = try leniaBreeder2024ResolvedAssets(run: run, algorithm: algorithm)
    let horizon = stepsOverride ?? assets.steps
    guard maxRequestedStep <= horizon else {
        throw ConfigError.invalidConfig("leniabreeder-2024 requested replay step \(maxRequestedStep) exceeds horizon \(horizon).")
    }

    let requested = Set(steps)
    var captured: [Int: [Float]] = [:]
    var carry = try leniaBreeder2024ExpressPopulation(genotypes: [elite.genotype], assets: assets)
    if requested.contains(0) {
        captured[0] = try leniaBreeder2024WorldMassMap(carry.world)
    }
    if maxRequestedStep > 0 {
        for stepIndex in 1...maxRequestedStep {
            let stepped = leniaBreeder2024StepBatch(
                carry: carry,
                assets: assets,
                recordPhenotype: false
            )
            carry = stepped.carry
            if requested.contains(stepIndex) {
                captured[stepIndex] = try leniaBreeder2024WorldMassMap(carry.world)
            }
        }
    }

    return try steps.map { step in
        guard let frame = captured[step] else {
            throw ConfigError.invalidConfig("leniabreeder-2024 failed to capture requested replay step \(step).")
        }
        return frame
    }
}

public func captureLeniaBreeder2024ReplayMassMaps(
    run: LeniaBreeder2024ResolvedRun,
    elite: LeniaBreeder2024EliteSummary,
    algorithmOverride: String? = nil,
    frameBudget: Int,
    stepsOverride: Int? = nil
) throws -> [[Float]] {
     let algorithm = leniaBreeder2024ResolvedAlgorithm(run: run, override: algorithmOverride)
     let assets = try leniaBreeder2024ResolvedAssets(run: run, algorithm: algorithm)
     var carry = try leniaBreeder2024ExpressPopulation(genotypes: [elite.genotype], assets: assets)
     var sampled: [[Float]] = []
     sampled.reserveCapacity(max(frameBudget, 1) + 2)
 
     sampled.append(try leniaBreeder2024WorldMassMap(carry.world))
 
    let stepCount = max(stepsOverride ?? assets.steps, 1)
    let stride = max(1, stepCount / max(frameBudget - 1, 1))
     for stepIndex in 0..<stepCount {
         let stepped = leniaBreeder2024StepBatch(
             carry: carry,
             assets: assets,
             recordPhenotype: false
         )
         carry = stepped.carry
         if stepIndex == stepCount - 1 || stepIndex % stride == 0 {
             sampled.append(try leniaBreeder2024WorldMassMap(carry.world))
         }
     }
 
    let selected = sampled.count > frameBudget ? downsampleReplayFloatFrames(sampled, target: max(frameBudget, 1)) : sampled
    return selected
}

public func captureLeniaBreeder2024SceneFrames(
    run: LeniaBreeder2024ResolvedRun,
    elites: [LeniaBreeder2024EliteSummary],
    algorithmOverride: String? = nil,
    frameBudget: Int,
    stepsOverride: Int? = nil,
    canvasSize: Int = 512
) throws -> [Data] {
    guard !elites.isEmpty else {
        throw ConfigError.invalidConfig("leniabreeder-2024 scene render requires at least one elite.")
    }
    guard canvasSize >= run.base.worldSize else {
        throw ConfigError.invalidConfig("leniabreeder-2024 scene canvas_size must be >= world_size.")
    }
    let algorithm = leniaBreeder2024ResolvedAlgorithm(run: run, override: algorithmOverride)
    let assets = try leniaBreeder2024ResolvedAssets(run: run, algorithm: algorithm)
    var carry = try leniaBreeder2024ExpressPopulation(genotypes: elites.map(\.genotype), assets: assets)
    let anchors = leniaBreeder2024SceneAnchors(count: elites.count, canvasSize: canvasSize)

    var sampled: [[Float]] = []
    sampled.reserveCapacity(max(frameBudget, 1) + 2)
    sampled.append(try leniaBreeder2024SceneFrame(carry: carry, assets: assets, anchors: anchors, canvasSize: canvasSize))

    let stepCount = max(stepsOverride ?? assets.steps, 1)
    let stride = max(1, stepCount / max(frameBudget - 1, 1))
    for stepIndex in 0..<stepCount {
        let stepped = leniaBreeder2024StepBatch(
            carry: carry,
            assets: assets,
            recordPhenotype: false
        )
        carry = stepped.carry
        if stepIndex == stepCount - 1 || stepIndex % stride == 0 {
            sampled.append(try leniaBreeder2024SceneFrame(carry: carry, assets: assets, anchors: anchors, canvasSize: canvasSize))
        }
    }

    let selected = sampled.count > frameBudget ? downsampleReplayFloatFrames(sampled, target: max(frameBudget, 1)) : sampled
    return leniaBreeder2024ByteFrames(selected)
}

public func captureLeniaBreeder2024SharedSceneFrames(
    run: LeniaBreeder2024ResolvedRun,
    elites: [LeniaBreeder2024EliteSummary],
    algorithmOverride: String? = nil,
    frameBudget: Int,
    stepsOverride: Int? = nil,
    canvasSize: Int = 512
) throws -> [Data] {
    guard !elites.isEmpty else {
        throw ConfigError.invalidConfig("leniabreeder-2024 shared scene render requires at least one elite.")
    }
    guard canvasSize >= run.base.worldSize else {
        throw ConfigError.invalidConfig("leniabreeder-2024 shared scene canvas_size must be >= world_size.")
    }
    let algorithm = leniaBreeder2024ResolvedAlgorithm(run: run, override: algorithmOverride)
    let assets = try leniaBreeder2024ResolvedAssets(run: run, algorithm: algorithm)
    let carry = try leniaBreeder2024ExpressPopulation(genotypes: elites.map(\.genotype), assets: assets)
    let anchors = leniaBreeder2024BoundedSceneAnchors(
        count: elites.count,
        canvasSize: canvasSize,
        specimenSize: assets.worldSize
    )
    var world = try leniaBreeder2024SharedSceneWorld(
        carry: carry,
        assets: assets,
        anchors: anchors,
        canvasSize: canvasSize
    )
    let kernelFFT = try leniaBreeder2024KernelFFT(
        pattern: assets.pattern,
        worldSize: canvasSize,
        worldScale: run.base.worldScale
    )
    let m = carry.m[0, 0...].reshaped([1, 1, 1, assets.nKernel])
    let s = carry.s[0, 0...].reshaped([1, 1, 1, assets.nKernel])
    let h = carry.h[0, 0...].reshaped([1, 1, 1, assets.nKernel])

    var sampled: [[Float]] = []
    sampled.reserveCapacity(max(frameBudget, 1) + 2)
    sampled.append(try leniaBreeder2024SharedWorldMassMap(world))

    let stepCount = max(stepsOverride ?? assets.steps, 1)
    let stride = max(1, stepCount / max(frameBudget - 1, 1))
    for stepIndex in 0..<stepCount {
        world = leniaBreeder2024SharedSceneStep(
            world: world,
            kernelFFT: kernelFFT,
            m: m,
            s: s,
            h: h,
            assets: assets
        )
        eval(world)
        if stepIndex == stepCount - 1 || stepIndex % stride == 0 {
            sampled.append(try leniaBreeder2024SharedWorldMassMap(world))
        }
    }

    let selected = sampled.count > frameBudget ? downsampleReplayFloatFrames(sampled, target: max(frameBudget, 1)) : sampled
    return leniaBreeder2024ByteFrames(selected)
}

public func captureLeniaBreeder2024LocalizedSharedSceneFrames(
    run: LeniaBreeder2024ResolvedRun,
    elites: [LeniaBreeder2024EliteSummary],
    algorithmOverride: String? = nil,
    frameBudget: Int,
    stepsOverride: Int? = nil,
    canvasSize: Int = 512
) throws -> [Data] {
    guard !elites.isEmpty else {
        throw ConfigError.invalidConfig("leniabreeder-2024 localized shared scene render requires at least one elite.")
    }
    guard canvasSize >= run.base.worldSize else {
        throw ConfigError.invalidConfig("leniabreeder-2024 localized shared scene canvas_size must be >= world_size.")
    }
    let algorithm = leniaBreeder2024ResolvedAlgorithm(run: run, override: algorithmOverride)
    let assets = try leniaBreeder2024ResolvedAssets(run: run, algorithm: algorithm)
    let carry = try leniaBreeder2024ExpressPopulation(genotypes: elites.map(\.genotype), assets: assets)
    let anchors = leniaBreeder2024BoundedSceneAnchors(
        count: elites.count,
        canvasSize: canvasSize,
        specimenSize: assets.worldSize
    )
    var speciesWorlds = try leniaBreeder2024SharedSceneWorlds(
        carry: carry,
        assets: assets,
        anchors: anchors,
        canvasSize: canvasSize
    )
    let kernelFFT = try leniaBreeder2024KernelFFT(
        pattern: assets.pattern,
        worldSize: canvasSize,
        worldScale: run.base.worldScale
    )
    let supportFFT = leniaBreeder2024SupportKernelFFT(
        worldSize: canvasSize,
        sigma: Float(max(2, assets.pattern.R * run.base.worldScale / 6))
    )
    let batchSize = carry.lastCenter.count
    let m = carry.m.reshaped([batchSize, 1, 1, assets.nKernel])
    let s = carry.s.reshaped([batchSize, 1, 1, assets.nKernel])
    let h = carry.h.reshaped([batchSize, 1, 1, assets.nKernel])

    var sampled: [[Float]] = []
    sampled.reserveCapacity(max(frameBudget, 1) + 2)
    sampled.append(try leniaBreeder2024LocalizedSharedWorldMassMap(speciesWorlds))

    let stepCount = max(stepsOverride ?? assets.steps, 1)
    let stride = max(1, stepCount / max(frameBudget - 1, 1))
    for stepIndex in 0..<stepCount {
        speciesWorlds = leniaBreeder2024LocalizedSharedSceneStep(
            speciesWorlds: speciesWorlds,
            kernelFFT: kernelFFT,
            supportFFT: supportFFT,
            m: m,
            s: s,
            h: h,
            assets: assets
        )
        eval(speciesWorlds)
        if stepIndex == stepCount - 1 || stepIndex % stride == 0 {
            sampled.append(try leniaBreeder2024LocalizedSharedWorldMassMap(speciesWorlds))
        }
    }

    let selected = sampled.count > frameBudget ? downsampleReplayFloatFrames(sampled, target: max(frameBudget, 1)) : sampled
    return leniaBreeder2024ByteFrames(selected)
}

public func leniaBreeder2024VisualizationRuntimeConfig(
     run: LeniaBreeder2024ResolvedRun,
     kernelParams: KernelParams,
     algorithmOverride: String? = nil
 ) -> LeniaRuntimeConfig {
     let connectivity = leniaBreeder2024ConnectivityMatrix(pattern: run.pattern)
     let (c0, c1) = connFromMatrix(connectivity)
     return LeniaRuntimeConfig(
         backend: .metalFull,
         sx: run.base.worldSize,
         sy: run.base.worldSize,
         channels: run.pattern.cells.count,
         nbK: run.pattern.kernels.count,
         profile: .experimental,
         c0: c0,
         c1: c1,
         dt: 1.0 / Float(max(run.pattern.T, 1)),
         dd: 5,
         sigma: 0.65,
         n: 2,
         thetaA: 1.0,
         border: "wall",
         implementation: ImplementationSettings(
             mode: "custom",
             border: "wall",
             gradientBoundary: "zero_pad",
             alphaMode: "per_channel",
             kernelProfile: "qd24_bucketed_v1",
             flowClip: "params_only"
         ),
         params: ResolvedParams(
             r: kernelParams.r,
             b: kernelParams.b,
             w: kernelParams.w,
             a: kernelParams.a,
             m: kernelParams.m,
             s: kernelParams.s,
             h: kernelParams.h,
             R: kernelParams.R,
             seed: 0
         ),
         initSeed: 0,
         patches: [],
         aUniform: UniformRange(low: 0, high: 0),
         pUniform: nil,
         steps: run.base.nStep,
         parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "mean", mix_seed: nil),
         chemotaxis: nil,
         food: nil,
         walls: nil,
         environment: nil,
         beamMutation: nil,
         interventions: []
     )
 }
 
 public func retrofitLeniaBreeder2024LibraryIndex(
     run: LeniaBreeder2024ResolvedRun,
     outputDirectory: URL? = nil,
     runId: String? = nil
 ) throws -> URL {
     let elites = try loadLeniaBreeder2024EliteSummaries(runDirectory: run.runDirectory)
     let algorithm = leniaBreeder2024ResolvedAlgorithm(run: run, override: nil)
     let evaluated = try evaluateLeniaBreeder2024Elites(run: run, elites: elites, algorithmOverride: algorithm)
     return try writeLeniaBreeder2024ResearchLibraryIndex(
         run: run,
         evaluated: evaluated,
         outputDirectory: outputDirectory,
         runId: runId,
         algorithmOverride: algorithm
     )
 }
 
 public func writeLeniaBreeder2024ResearchLibraryIndex(
     run: LeniaBreeder2024ResolvedRun,
     evaluated: [LeniaBreeder2024EvaluatedElite],
     outputDirectory: URL? = nil,
     runId: String? = nil,
     algorithmOverride: String? = nil
 ) throws -> URL {
     let algorithm = leniaBreeder2024ResolvedAlgorithm(run: run, override: algorithmOverride)
     let assets = try leniaBreeder2024ResolvedAssets(run: run, algorithm: algorithm)
     let configHash: String = try {
         switch algorithm {
         case "aurora":
             return try leniaBreeder2024AURORAConfigHash(base: run.base, aurora: run.aurora, pattern: run.pattern)
         default:
             return try leniaBreeder2024MAPElitesConfigHash(base: run.base, mapElites: run.mapElites, pattern: run.pattern)
         }
     }()
     let effectiveRunId = runId ?? run.runDirectory.lastPathComponent
     let distributed = FileManager.default.fileExists(
         atPath: run.runDirectory.appendingPathComponent("distributed.json").path
     )
     let entries = try evaluated.map { evaluatedElite in
         let cell = evaluatedElite.elite.cell
         let metadata: [String: AnyCodable] = [
             "version": try researchMetadataValue(1),
             "mode": try researchMetadataValue("qd-2024"),
             "morphospace_payload": try researchMetadataValue("summary_only_metrics_v1"),
             "morphospace_ready": try researchMetadataValue(false),
             "algorithm": try researchMetadataValue(algorithm),
             "generation": try researchMetadataValue(evaluatedElite.elite.generation),
             "cell": try researchMetadataValue(cell),
             "descriptor": try researchMetadataValue(evaluatedElite.elite.descriptor),
             "centroid": try researchMetadataValue(evaluatedElite.elite.centroid),
             "fitness": try researchMetadataValue(evaluatedElite.elite.fitness),
             "pattern_id": try researchMetadataValue(run.base.patternID),
             "distributed": try researchMetadataValue(distributed),
             "genotype": try researchMetadataValue(evaluatedElite.elite.genotype),
         ]
        return archiveResearchLibraryEntry(
            creature: archivedCreature(
                stableKey: "\(effectiveRunId)|\(algorithm)|\(cell)",
                name: "qd-\(algorithm)-cell-\(cell)",
                ownerId: "qd-2024",
                genotype: leniaBreeder2024KernelParams(genotype: evaluatedElite.elite.genotype, assets: assets),
                initialCondition: InitConfig(
                    seed: cell,
                    patches: [],
                    a_uniform: UniformRange(low: 0, high: 0),
                    p_uniform: nil
                ),
                metrics: evaluatedElite.metrics,
                sweep: ["cell": Double(cell)],
                score: evaluatedElite.elite.fitness,
                scoreWeights: ["fitness": 1.0],
                configHash: configHash
            ),
            runId: effectiveRunId,
            configHash: configHash,
            sourceMode: "qd-2024",
            sourceAlgorithm: algorithm,
            researchMetadata: metadata
        )
     }
     return try ResearchLibraryWriter.write(
         entries: entries,
         runDirectory: outputDirectory ?? run.runDirectory
     )
 }
 
 public func expressLeniaBreeder2024Seed(
     run: LeniaBreeder2024ResolvedRun,
     elite: LeniaBreeder2024EliteSummary,
     algorithmOverride: String? = nil
 ) throws -> LeniaBreeder2024ExpressedSeed {
     let algorithm = leniaBreeder2024ResolvedAlgorithm(run: run, override: algorithmOverride)
     let assets = try leniaBreeder2024ResolvedAssets(run: run, algorithm: algorithm)
     let carry = try leniaBreeder2024Express(genotype: elite.genotype, assets: assets)
     let embryoSize = Int(sqrt(Double((elite.genotype.count - assets.nParams) / assets.nChannel)))
     return LeniaBreeder2024ExpressedSeed(
         elite: elite,
         algorithm: algorithm,
         world: WorldState(
             width: assets.worldSize,
             height: assets.worldSize,
             channels: assets.nChannel,
             values: carry.world.asArray(Float.self)
         ),
         embryoSize: embryoSize,
         kernelParams: leniaBreeder2024KernelParams(genotype: elite.genotype, assets: assets),
         pattern: leniaBreeder2024PatternSpec(
             basePattern: run.pattern,
             genotype: elite.genotype,
             nChannel: assets.nChannel,
             nKernel: assets.nKernel,
             embryoSize: embryoSize,
             name: run.pattern.name
         )
     )
 }
 
 public func leniaBreeder2024PatternSpecFromElite(
     run: LeniaBreeder2024ResolvedRun,
     elite: LeniaBreeder2024EliteSummary,
     name: String,
     algorithmOverride: String? = nil
 ) throws -> LeniaBreeder2024PatternSpec {
     let algorithm = leniaBreeder2024ResolvedAlgorithm(run: run, override: algorithmOverride)
     let assets = try leniaBreeder2024ResolvedAssets(run: run, algorithm: algorithm)
     let embryoSize = Int(sqrt(Double((elite.genotype.count - assets.nParams) / assets.nChannel)))
     return leniaBreeder2024PatternSpec(
         basePattern: run.pattern,
         genotype: elite.genotype,
         nChannel: assets.nChannel,
         nKernel: assets.nKernel,
         embryoSize: embryoSize,
         name: name
     )
 }
 
 private func loadLeniaBreeder2024Pattern(
     runDirectory: URL,
     configDirectoryOverride: URL?,
     patternID: String,
     decoder: JSONDecoder
 ) throws -> LeniaBreeder2024PatternSpec {
     let candidates = [
         runDirectory.appendingPathComponent("patterns/\(patternID).json"),
         runDirectory.appendingPathComponent("pattern.json"),
         configDirectoryOverride?.appendingPathComponent("patterns/\(patternID).json"),
     ]
     for candidate in candidates.compactMap({ $0 }) {
         if FileManager.default.fileExists(atPath: candidate.path) {
             return try decoder.decode(LeniaBreeder2024PatternSpec.self, from: Data(contentsOf: candidate))
         }
     }
     throw ConfigError.invalidConfig("leniabreeder-2024 pattern asset \(patternID) is missing for run \(runDirectory.path).")
 }
 
 private func leniaBreeder2024PatternSpec(
     basePattern: LeniaBreeder2024PatternSpec,
     genotype: [Float],
     nChannel: Int,
     nKernel: Int,
     embryoSize: Int,
     name: String
 ) -> LeniaBreeder2024PatternSpec {
     let params = Array(genotype[0..<(3 * nKernel)])
     let m = Array(params[0..<nKernel])
     let s = Array(params[nKernel..<(2 * nKernel)])
     let h = Array(params[(2 * nKernel)..<(3 * nKernel)])
     let cellsFlat = Array(genotype[(3 * nKernel)...])
 
     var cells = Array(
         repeating: Array(
             repeating: Array(repeating: Float(0), count: embryoSize),
             count: embryoSize
         ),
         count: nChannel
     )
     var cursor = 0
     for y in 0..<embryoSize {
         for x in 0..<embryoSize {
             for channel in 0..<nChannel {
                 cells[channel][y][x] = cellsFlat[cursor]
                 cursor += 1
             }
         }
     }
 
     let kernels = basePattern.kernels.enumerated().map { index, kernel in
         LeniaBreeder2024PatternSpec.Kernel(
             b: kernel.b,
             c0: kernel.c0,
             c1: kernel.c1,
             h: h[index],
             m: m[index],
             r: kernel.r,
             s: s[index]
         )
     }
     return LeniaBreeder2024PatternSpec(
         R: basePattern.R,
         T: basePattern.T,
         cells: cells,
         kernels: kernels,
         name: name
     )
 }
 
 private func leniaBreeder2024ResolvedAlgorithm(
     run: LeniaBreeder2024ResolvedRun,
     override: String?
 ) -> String {
     let algorithm = override?
         .trimmingCharacters(in: .whitespacesAndNewlines)
         .lowercased()
     let resolved = (algorithm?.isEmpty == false ? algorithm : nil) ?? run.defaultAlgorithm.lowercased()
     return resolved == "aurora" ? "aurora" : "me"
 }
 
 private func leniaBreeder2024ResolvedAssets(
     run: LeniaBreeder2024ResolvedRun,
     algorithm: String
 ) throws -> LeniaBreeder2024Assets {
     try leniaBreeder2024LoadAssets(
         base: run.base,
         pattern: run.pattern,
         mode: algorithm == "aurora"
             ? leniaBreeder2024AURORASettings(
                 configs: LeniaBreeder2024ConfigBundle(
                     configDirectory: run.configDirectory ?? run.runDirectory,
                     base: run.base,
                     mapElites: run.mapElites,
                     aurora: run.aurora
                 )
             )
             : leniaBreeder2024MAPElitesSettings(
                 config: run.mapElites
             )
     )
 }
 
 private func leniaBreeder2024DescriptorNames(
     run: LeniaBreeder2024ResolvedRun,
     algorithm: String
 ) -> [String] {
     algorithm == "aurora"
         ? [run.aurora.fitness]
         : run.mapElites.descriptor
 }
 
 private func leniaBreeder2024FitnessName(
     run: LeniaBreeder2024ResolvedRun,
     algorithm: String
 ) -> String {
     algorithm == "aurora" ? run.aurora.fitness : run.mapElites.fitness
 }
 
 private func leniaBreeder2024ConnectivityMatrix(pattern: LeniaBreeder2024PatternSpec) -> [[Int]] {
     var matrix = Array(
         repeating: Array(repeating: 0, count: pattern.cells.count),
         count: pattern.cells.count
     )
     for kernel in pattern.kernels {
         matrix[kernel.c0][kernel.c1] += 1
     }
     return matrix
 }
 
private func leniaBreeder2024WorldMassMap(_ worldBatch: MLXArray) throws -> [Float] {
    let sample = worldBatch[0, 0..., 0..., 0...]
    let massMap = sample.sum(axis: -1)
    eval(massMap)
    return massMap.asArray(Float.self)
}

private func leniaBreeder2024SharedWorldMassMap(_ world: MLXArray) throws -> [Float] {
    let massMap = world.sum(axis: -1)
    eval(massMap)
    return massMap.asArray(Float.self)
}

private func leniaBreeder2024LocalizedSharedWorldMassMap(_ speciesWorlds: MLXArray) throws -> [Float] {
    let totalWorld = MLX.clip(speciesWorlds.sum(axes: [0]), min: MLXArray(0.0), max: MLXArray(1.0))
    return try leniaBreeder2024SharedWorldMassMap(totalWorld)
}

private func leniaBreeder2024SharedSceneStep(
    world: MLXArray,
    kernelFFT: MLXArray,
    m: MLXArray,
    s: MLXArray,
    h: MLXArray,
    assets: LeniaBreeder2024Assets
) -> MLXArray {
    let batchedWorld = world.expandedDimensions(axis: 0)
    let fA = MLXFFT.fft2(batchedWorld, axes: [1, 2])
    let fAK = MLX.matmul(fA, assets.reshapeCK)
    let UK = MLXFFT.ifft2(kernelFFT.reshaped([1] + kernelFFT.shape) * fAK, axes: [1, 2]).realPart()
    let GK = (MLXArray(2.0) * MLX.exp(-(((UK - m) / s) * ((UK - m) / s)) / MLXArray(2.0)) - MLXArray(1.0)) * h
    let G = MLX.matmul(GK, assets.reshapeKC)
    let next = MLX.clip(batchedWorld + MLXArray(Float(1.0 / Float(assets.pattern.T))) * G, min: MLXArray(0.0), max: MLXArray(1.0))
    return next[0, 0..., 0..., 0...]
}

private func leniaBreeder2024LocalizedSharedSceneStep(
    speciesWorlds: MLXArray,
    kernelFFT: MLXArray,
    supportFFT: MLXArray,
    m: MLXArray,
    s: MLXArray,
    h: MLXArray,
    assets: LeniaBreeder2024Assets
) -> MLXArray {
    let batchSize = speciesWorlds.shape[0]
    let totalWorld = MLX.clip(speciesWorlds.sum(axes: [0]), min: MLXArray(0.0), max: MLXArray(1.0))
    let fA = MLXFFT.fft2(totalWorld.expandedDimensions(axis: 0), axes: [1, 2])
    let fAK = MLX.matmul(fA, assets.reshapeCK)
    let UKShared = MLXFFT.ifft2(kernelFFT.reshaped([1] + kernelFFT.shape) * fAK, axes: [1, 2]).realPart()
    let UK = MLX.broadcast(UKShared, to: [batchSize, speciesWorlds.shape[1], speciesWorlds.shape[2], assets.nKernel])
    let GK = (MLXArray(2.0) * MLX.exp(-(((UK - m) / s) * ((UK - m) / s)) / MLXArray(2.0)) - MLXArray(1.0)) * h
    let G = MLX.matmul(GK, assets.reshapeKC)
    let support = leniaBreeder2024LocalizedSharedSupport(speciesWorlds: speciesWorlds, supportFFT: supportFFT)
    let dt = MLXArray(Float(1.0 / Float(assets.pattern.T)))
    let nextSpecies = MLX.clip(speciesWorlds + support * dt * G, min: MLXArray(0.0), max: MLXArray(1.0))
    let occupancy = nextSpecies.sum(axes: [0], keepDims: true)
    let scale = MLX.minimum(
        MLXArray(1.0),
        MLXArray(1.0) / MLX.maximum(occupancy, MLXArray(1.0))
    )
    return nextSpecies * scale
}

private func leniaBreeder2024LocalizedSharedSupport(
    speciesWorlds: MLXArray,
    supportFFT: MLXArray
) -> MLXArray {
    let speciesMass = speciesWorlds.sum(axis: -1).expandedDimensions(axis: -1)
    let ownershipTotal = speciesMass.sum(axes: [0], keepDims: true)
    let hardOwnership = speciesMass / MLX.maximum(ownershipTotal, MLXArray(Float(1e-6)))
    let blurred = MLXFFT.ifft2(
        MLXFFT.fft2(speciesMass, axes: [1, 2]) * supportFFT.reshaped([1] + supportFFT.shape + [1]),
        axes: [1, 2]
    ).realPart()
    let clipped = MLX.maximum(blurred, MLXArray(0.0))
    let total = clipped.sum(axes: [0], keepDims: true)
    let totalSafe = MLX.maximum(total, MLXArray(Float(1e-6)))
    let frontier = clipped / totalSafe
    return hardOwnership * MLXArray(0.85) + frontier * MLXArray(0.15)
}

private func leniaBreeder2024SupportKernelFFT(
    worldSize: Int,
    sigma: Float
) -> MLXArray {
    let mid = worldSize / 2
    let coords = (0..<worldSize).map { Float($0 - mid) }
    let (Y, X) = meshgrid(MLXArray(coords), MLXArray(coords))
    let sigmaSq = max(sigma * sigma, 1)
    let kernel = MLX.exp(-((X * X + Y * Y) / MLXArray(2 * sigmaSq)))
    let normalized = kernel / kernel.sum()
    let shifted = fftshift2(normalized)
    return MLXFFT.fft2(shifted, axes: [0, 1])
}

private func leniaBreeder2024SharedSceneWorlds(
    carry: LeniaBreeder2024CarryBatch,
    assets: LeniaBreeder2024Assets,
    anchors: [SIMD2<Int>],
    canvasSize: Int
) throws -> MLXArray {
    let batchSize = carry.lastCenter.count
    precondition(anchors.count == batchSize, "leniabreeder-2024 shared scene anchor count mismatch")
    eval(carry.world)
    let worldValues = carry.world.asArray(Float.self)
    let sampleSize = assets.worldSize * assets.worldSize * assets.nChannel
    let canvasSampleSize = canvasSize * canvasSize * assets.nChannel
    var shared = [Float](repeating: 0, count: batchSize * canvasSampleSize)

    for sampleIndex in 0..<batchSize {
        let anchor = anchors[sampleIndex]
        let startRow = anchor.x - assets.worldSize / 2
        let startCol = anchor.y - assets.worldSize / 2
        let sampleOffset = sampleIndex * sampleSize
        let canvasOffset = sampleIndex * canvasSampleSize
        for row in 0..<assets.worldSize {
            for col in 0..<assets.worldSize {
                let sourcePixel = sampleOffset + (row * assets.worldSize + col) * assets.nChannel
                let targetRow = startRow + row
                let targetCol = startCol + col
                guard targetRow >= 0, targetRow < canvasSize, targetCol >= 0, targetCol < canvasSize else {
                    continue
                }
                let targetPixel = canvasOffset + (targetRow * canvasSize + targetCol) * assets.nChannel
                for channel in 0..<assets.nChannel {
                    let value = worldValues[sourcePixel + channel]
                    if value <= 1e-6 { continue }
                    shared[targetPixel + channel] = value
                }
            }
        }
    }

    return MLXArray(shared).reshaped([batchSize, canvasSize, canvasSize, assets.nChannel])
}

private func leniaBreeder2024SharedSceneWorld(
    carry: LeniaBreeder2024CarryBatch,
    assets: LeniaBreeder2024Assets,
    anchors: [SIMD2<Int>],
    canvasSize: Int
) throws -> MLXArray {
    let speciesWorlds = try leniaBreeder2024SharedSceneWorlds(
        carry: carry,
        assets: assets,
        anchors: anchors,
        canvasSize: canvasSize
    )
    eval(speciesWorlds)
    let speciesValues = speciesWorlds.asArray(Float.self)
    let batchSize = carry.lastCenter.count
    let sampleSize = canvasSize * canvasSize * assets.nChannel
    var shared = [Float](repeating: 0, count: canvasSize * canvasSize * assets.nChannel)

    for sampleIndex in 0..<batchSize {
        let sampleOffset = sampleIndex * sampleSize
        for row in 0..<canvasSize {
            for col in 0..<canvasSize {
                let sourcePixel = sampleOffset + (row * canvasSize + col) * assets.nChannel
                let targetPixel = (row * canvasSize + col) * assets.nChannel
                for channel in 0..<assets.nChannel {
                    let value = speciesValues[sourcePixel + channel]
                    if value <= 1e-6 { continue }
                    shared[targetPixel + channel] = max(shared[targetPixel + channel], value)
                }
            }
        }
    }

    return MLXArray(shared).reshaped([canvasSize, canvasSize, assets.nChannel])
}

private func leniaBreeder2024BoundedSceneAnchors(
    count: Int,
    canvasSize: Int,
    specimenSize: Int
) -> [SIMD2<Int>] {
    let center = Float(canvasSize) / 2
    guard count > 1 else {
        return [SIMD2<Int>(Int(center), Int(center))]
    }
    let margin = Float(max(4, specimenSize / 16))
    let boundedRadius = max(0, center - Float(specimenSize) / 2 - margin)
    let radius = min(Float(canvasSize) * 0.28, boundedRadius)
    return (0..<count).map { index in
        let angle = (2 * Float.pi * Float(index)) / Float(count)
        return SIMD2<Int>(
            Int((center + sin(angle) * radius).rounded()),
            Int((center + cos(angle) * radius).rounded())
        )
    }
}

private func leniaBreeder2024Clamp01(_ value: Float) -> Float {
    min(max(value, 0), 1)
}

private func leniaBreeder2024Ramp(_ value: Float, low: Float, high: Float) -> Float {
    guard high > low else {
        return value >= high ? 1 : 0
    }
    return leniaBreeder2024Clamp01((value - low) / (high - low))
}

private func leniaBreeder2024BandScore(
    _ value: Float,
    zeroLow: Float,
    low: Float,
    high: Float,
    zeroHigh: Float
) -> Float {
    guard low >= zeroLow, zeroHigh >= high else {
        return 0
    }
    if value <= zeroLow || value >= zeroHigh {
        return 0
    }
    if value < low {
        return leniaBreeder2024Ramp(value, low: zeroLow, high: low)
    }
    if value <= high {
        return 1
    }
    return 1 - leniaBreeder2024Ramp(value, low: high, high: zeroHigh)
}

private func leniaBreeder2024ArenaCountScore(significantCount: Float, copyCount: Int) -> Float {
    if significantCount < 2 {
        return 0
    }
    let softUpper = Float(max(copyCount + 2, 4))
    if significantCount <= softUpper {
        return 1
    }
    let hardUpper = Float(max(copyCount * 2 + 2, 8))
    return 1 - leniaBreeder2024Ramp(significantCount, low: softUpper, high: hardUpper)
}

private func leniaBreeder2024ArenaAdjustedFitness(
    baseFitness: Float,
    massAverage: Float,
    displacement: Float,
    componentCount: Float,
    significantCount: Float,
    largestFraction: Float,
    largestAnisotropy: Float,
    significantMassFraction: Float,
    copyCount: Int
) -> Float {
    let massScore = leniaBreeder2024Ramp(massAverage, low: 0.9, high: 2.8)
    let motionScore = leniaBreeder2024Ramp(displacement, low: 0.08, high: 0.25)
    let countScore = leniaBreeder2024ArenaCountScore(significantCount: significantCount, copyCount: copyCount)
    let concentrationScore = leniaBreeder2024Ramp(significantMassFraction, low: 0.45, high: 0.85)
    let dominanceScore = 1 - leniaBreeder2024Ramp(largestFraction, low: 0.62, high: 0.9)
    let shapeScore = leniaBreeder2024BandScore(
        largestAnisotropy,
        zeroLow: 0.04,
        low: 0.14,
        high: 0.58,
        zeroHigh: 0.92
    )
    let radialPenalty = 1 - leniaBreeder2024Ramp(largestAnisotropy, low: 0.08, high: 0.18)
    let fragmentationPenalty = leniaBreeder2024Ramp(
        componentCount,
        low: Float(max(copyCount * 2, 8)),
        high: Float(max(copyCount * 4, 16))
    )

    let structureScore = concentrationScore * countScore * dominanceScore * shapeScore
    let vitalityScore = massScore * (0.6 * motionScore + 0.4 * structureScore)

    var adjusted = baseFitness + 0.55 * vitalityScore - 0.18 * fragmentationPenalty
    adjusted -= 0.16 * radialPenalty * (1 - motionScore)
    if significantCount < 2 {
        adjusted -= 0.12
    }
    if massAverage < 0.8 {
        adjusted -= 0.18
    }
    if largestAnisotropy < 0.12 && displacement < 0.12 {
        adjusted -= 0.1
    }
    return adjusted
}

private func leniaBreeder2024EvaluatePopulationLocalizedSharedArena(
    genotypes: [[Float]],
    assets: LeniaBreeder2024Assets,
    descriptorNames: [String],
    fitnessName: String,
    copyCount: Int,
    canvasSize: Int
) throws -> [LeniaBreeder2024Evaluation] {
    guard !genotypes.isEmpty else { return [] }
    guard canvasSize >= assets.worldSize else {
        throw ConfigError.invalidConfig("leniabreeder-2024 localized shared arena canvas_size must be >= world_size.")
    }
    let batchSize = genotypes.count
    let carry = try leniaBreeder2024ExpressPopulation(genotypes: genotypes, assets: assets)
    let anchors = leniaBreeder2024BoundedSceneAnchors(
        count: copyCount,
        canvasSize: canvasSize,
        specimenSize: assets.worldSize
    )
    var arenaWorlds = try leniaBreeder2024SharedArenaWorldBatch(
        worlds: carry.world,
        anchors: anchors,
        worldSize: assets.worldSize,
        channels: assets.nChannel,
        canvasSize: canvasSize
    )
    let kernelFFT = try leniaBreeder2024KernelFFT(
        pattern: assets.pattern,
        worldSize: canvasSize,
        worldScale: 1
    )
    let mid = canvasSize / 2
    let coordScale = Float(max(canvasSize, 1)) / 2
    let xCoords = (0..<canvasSize).map { Float($0 - mid) / coordScale }
    let yCoords = (0..<canvasSize).map { Float($0 - mid) / coordScale }
    let (yGrid, xGrid) = meshgrid(MLXArray(yCoords), MLXArray(xCoords))
    let occupancyThreshold = MLXArray(Float(0.05))
    let massNormalization = Float(max(assets.pattern.R * assets.pattern.R * copyCount, 1))

    var massFlat: [Float] = []
    var centerXFlat: [Float] = []
    var centerYFlat: [Float] = []
    var linearVelocityFlat: [Float] = []
    var angleFlat: [Float] = []
    var angularVelocityFlat: [Float] = []
    massFlat.reserveCapacity(batchSize * assets.steps)
    centerXFlat.reserveCapacity(batchSize * assets.steps)
    centerYFlat.reserveCapacity(batchSize * assets.steps)
    linearVelocityFlat.reserveCapacity(batchSize * assets.steps)
    angleFlat.reserveCapacity(batchSize * assets.steps)
    angularVelocityFlat.reserveCapacity(batchSize * assets.steps)

    var failed = Array(repeating: false, count: batchSize)
    var lastCenter = Array(repeating: SIMD2<Float>(repeating: 0), count: batchSize)
    var lastAngle = Array(repeating: Float(0), count: batchSize)

    for _ in 0..<assets.steps {
        let step = leniaBreeder2024StepArenaBatch(
            worlds: arenaWorlds,
            m: carry.m,
            s: carry.s,
            h: carry.h,
            reshapeCK: assets.reshapeCK,
            reshapeKC: assets.reshapeKC,
            kernelFFT: kernelFFT,
            T: assets.pattern.T,
            xGrid: xGrid,
            yGrid: yGrid,
            massNormalization: massNormalization,
            occupancyThreshold: occupancyThreshold,
            lastCenter: lastCenter,
            lastAngle: lastAngle
        )
        arenaWorlds = step.worlds
        lastCenter = step.lastCenter
        lastAngle = step.lastAngle
        massFlat.append(contentsOf: step.mass)
        centerXFlat.append(contentsOf: step.centerX)
        centerYFlat.append(contentsOf: step.centerY)
        linearVelocityFlat.append(contentsOf: step.linearVelocity)
        angleFlat.append(contentsOf: step.angle)
        angularVelocityFlat.append(contentsOf: step.angularVelocity)
        for sampleIndex in 0..<batchSize {
            failed[sampleIndex] = failed[sampleIndex] || step.isEmpty[sampleIndex] || step.isCrowded[sampleIndex]
        }
    }

    let finalMassMap = arenaWorlds.sum(axis: -1)
    eval(finalMassMap)
    let finalMassBatch = materializeMassBatch(finalMassMap)
    let finalStructure = computeComponentStructureBatch(
        materialized: finalMassBatch,
        threshold: 0.05,
        useTorus: false,
        significantMassMinimum: Float(assets.pattern.R * assets.pattern.R) * 0.35,
        significantMassFraction: 0.1
    )
    let finalMoments = computeMomentsBatch(
        materialized: finalMassBatch,
        config: MomentsConfig(enabled: true, threshold: 0.05)
    )
    let phenotypeBatch = leniaBreeder2024SplitPhenotypeBatch(
        finalMassMap.expandedDimensions(axis: -1),
        batchSize: batchSize,
        phenotypeSize: canvasSize,
        nChannel: 1
    )

    return try (0..<batchSize).map { sampleIndex in
        let massHistory = leniaBreeder2024ExtractSeries(massFlat, sampleIndex: sampleIndex, batchSize: batchSize)
        let centerXHistory = leniaBreeder2024ExtractSeries(centerXFlat, sampleIndex: sampleIndex, batchSize: batchSize)
        let centerYHistory = leniaBreeder2024ExtractSeries(centerYFlat, sampleIndex: sampleIndex, batchSize: batchSize)
        let linearVelocityHistory = leniaBreeder2024ExtractSeries(linearVelocityFlat, sampleIndex: sampleIndex, batchSize: batchSize)
        let angleHistory = leniaBreeder2024ExtractSeries(angleFlat, sampleIndex: sampleIndex, batchSize: batchSize)
        let angularVelocityHistory = leniaBreeder2024ExtractSeries(angularVelocityFlat, sampleIndex: sampleIndex, batchSize: batchSize)
        let morphology = leniaBreeder2024MorphologyMetrics(
            structure: finalStructure,
            moments: finalMoments,
            sampleIndex: sampleIndex
        )
        let descriptor = try descriptorNames.map { name in
            try leniaBreeder2024Metric(
                name: name,
                mass: massHistory,
                centerX: centerXHistory,
                centerY: centerYHistory,
                linearVelocity: linearVelocityHistory,
                angle: angleHistory,
                angularVelocity: angularVelocityHistory,
                phenotype: phenotypeBatch[sampleIndex],
                morphology: morphology,
                failed: failed[sampleIndex],
                nKeep: assets.nKeep,
                phenotypeSize: canvasSize,
                nChannel: 1
            )
        }
        let baseFitness = try leniaBreeder2024Metric(
            name: fitnessName,
            mass: massHistory,
            centerX: centerXHistory,
            centerY: centerYHistory,
            linearVelocity: linearVelocityHistory,
            angle: angleHistory,
            angularVelocity: angularVelocityHistory,
            phenotype: phenotypeBatch[sampleIndex],
            morphology: morphology,
            failed: failed[sampleIndex],
            nKeep: assets.nKeep,
            phenotypeSize: canvasSize,
            nChannel: 1
        )
        let massAverage = try leniaBreeder2024Metric(
            name: "pos_mass_avg",
            mass: massHistory,
            centerX: centerXHistory,
            centerY: centerYHistory,
            linearVelocity: linearVelocityHistory,
            angle: angleHistory,
            angularVelocity: angularVelocityHistory,
            phenotype: phenotypeBatch[sampleIndex],
            morphology: morphology,
            failed: failed[sampleIndex],
            nKeep: assets.nKeep,
            phenotypeSize: canvasSize,
            nChannel: 1
        )
        let displacement = try leniaBreeder2024Metric(
            name: "pos_linear_velocity_avg",
            mass: massHistory,
            centerX: centerXHistory,
            centerY: centerYHistory,
            linearVelocity: linearVelocityHistory,
            angle: angleHistory,
            angularVelocity: angularVelocityHistory,
            phenotype: phenotypeBatch[sampleIndex],
            morphology: morphology,
            failed: failed[sampleIndex],
            nKeep: assets.nKeep,
            phenotypeSize: canvasSize,
            nChannel: 1
        )
        let fitness = leniaBreeder2024ArenaAdjustedFitness(
            baseFitness: baseFitness,
            massAverage: massAverage,
            displacement: displacement,
            componentCount: finalStructure.count[sampleIndex],
            significantCount: finalStructure.significantCount[sampleIndex],
            largestFraction: finalStructure.largestFraction[sampleIndex],
            largestAnisotropy: finalStructure.largestAnisotropy[sampleIndex],
            significantMassFraction: finalStructure.significantMassFraction[sampleIndex],
            copyCount: copyCount
        )
        return LeniaBreeder2024Evaluation(
            fitness: failed[sampleIndex] || !fitness.isFinite || descriptor.contains(where: { !$0.isFinite }) ? -.infinity : fitness,
            descriptor: descriptor,
            failed: failed[sampleIndex],
            phenotype: phenotypeBatch[sampleIndex],
            phenotypeTrajectory: [],
            creatureSummary: leniaBreeder2024CreatureSummary(
                mass: massHistory,
                centerX: centerXHistory,
                centerY: centerYHistory,
                linearVelocity: linearVelocityHistory,
                phenotype: phenotypeBatch[sampleIndex],
                phenotypeSize: canvasSize,
                nChannel: 1,
                failed: failed[sampleIndex]
            )
        )
    }
}

private func leniaBreeder2024SceneAnchors(count: Int, canvasSize: Int) -> [SIMD2<Int>] {
    let center = Float(canvasSize) / 2
    guard count > 1 else {
        return [SIMD2<Int>(Int(center), Int(center))]
    }
    let radius = Float(canvasSize) * 0.28
    return (0..<count).map { index in
        let angle = (2 * Float.pi * Float(index)) / Float(count)
        return SIMD2<Int>(
            Int((center + sin(angle) * radius).rounded()),
            Int((center + cos(angle) * radius).rounded())
        )
    }
}

private func leniaBreeder2024SceneFrame(
    carry: LeniaBreeder2024CarryBatch,
    assets: LeniaBreeder2024Assets,
    anchors: [SIMD2<Int>],
    canvasSize: Int
) throws -> [Float] {
    let batchSize = carry.lastCenter.count
    precondition(anchors.count == batchSize, "leniabreeder-2024 scene anchor count mismatch")
    let massBatch = carry.world.sum(axis: -1)
    eval(massBatch)
    let massValues = massBatch.asArray(Float.self)
    let sampleSize = assets.worldSize * assets.worldSize
    var canvas = [Float](repeating: 0, count: canvasSize * canvasSize)

    for sampleIndex in 0..<batchSize {
        let anchor = anchors[sampleIndex]
        let totalShift = carry.totalShift[sampleIndex]
        let startRow = anchor.x + totalShift.x - assets.worldSize / 2
        let startCol = anchor.y + totalShift.y - assets.worldSize / 2
        let sampleOffset = sampleIndex * sampleSize
        for row in 0..<assets.worldSize {
            for col in 0..<assets.worldSize {
                let value = massValues[sampleOffset + row * assets.worldSize + col]
                if value <= 1e-6 { continue }
                let targetRow = positiveModulo(startRow + row, canvasSize)
                let targetCol = positiveModulo(startCol + col, canvasSize)
                let targetIndex = targetRow * canvasSize + targetCol
                canvas[targetIndex] = min(1, canvas[targetIndex] + value)
            }
        }
    }
    return canvas
}

private func positiveModulo(_ value: Int, _ divisor: Int) -> Int {
    let remainder = value % divisor
    return remainder >= 0 ? remainder : remainder + divisor
}
 
 private func downsampleReplayFloatFrames(_ frames: [[Float]], target: Int) -> [[Float]] {
     guard frames.count > target, target > 1 else { return frames }
     let last = frames.count - 1
     return (0..<target).map { index in
         let fraction = Double(index) / Double(target - 1)
         let sourceIndex = Int((fraction * Double(last)).rounded())
         return frames[sourceIndex]
     }
 }
 
 private func leniaBreeder2024ByteFrames(_ frames: [[Float]]) -> [Data] {
     let maxValue = max(
         frames.flatMap { $0 }.max() ?? 0,
         1e-6
     )
     return frames.map { frame in
         Data(frame.map { value in
             leniaBreeder2024ReplayByte(pow(max(0, value) / maxValue, 0.72))
         })
     }
 }
 
 private func leniaBreeder2024ReplayByte(_ value: Float) -> UInt8 {
     UInt8(max(0, min(255, Int(max(0, min(1, value)) * 255.0 + 0.5))))
 }
 
private func appendMetricsCSV(_ entry: LeniaBreeder2024HistoryEntry, to url: URL) throws {
    let row = "\(entry.generation),\(entry.qdScore),\(entry.coverage),\(entry.maxFitness),\(entry.nElites),\(entry.variance),\(entry.elapsedSeconds)\n"
    let handle = try FileHandle(forWritingTo: url)
    defer { try? handle.close() }
    try handle.seekToEnd()
    handle.write(Data(row.utf8))
}
