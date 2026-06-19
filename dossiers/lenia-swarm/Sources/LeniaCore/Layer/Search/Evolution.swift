import Foundation
import MLX
import MLXRandom

// ES Configuration structures matching es.py

public struct FitnessConfig: Codable {
    public let objective: String
    public let targetStep: Int
    public let angleThreshold: Float
    public let minimumDisplacement: Float?
    public let gyrationPenalty: Float?
    public let componentCountPenalty: Float?
    public let componentCountTarget: Float?
    public let componentCountTargetPenalty: Float?
    public let minimumComponentCount: Float?
    public let maximumComponentCount: Float?
    public let componentCountLimitPenalty: Float?
    public let largestComponentFractionReward: Float?
    public let minimumLargestComponentFraction: Float?
    public let maximumLargestComponentFraction: Float?
    public let largestComponentFractionPenalty: Float?
    public let largestComponentFractionLimitPenalty: Float?
    public let maximumLargestComponentAnisotropy: Float?
    public let largestComponentAnisotropyPenalty: Float?
    public let componentMassEvennessReward: Float?
    public let minimumComponentMassEvenness: Float?
    public let componentMassEvennessPenalty: Float?
    public let minimumMomentMass: Float?
    public let maximumMomentMass: Float?
    public let largestComponentSolidityReward: Float?
    public let largestComponentMeanThicknessReward: Float?
    public let largestComponentFilamentarityPenalty: Float?
    public let momentDensityReward: Float?
    public let minimumMomentDensity: Float?
    public let maximumMomentDensity: Float?
    public let momentDensityPenalty: Float?
    public let momentAnisotropyPenalty: Float?
    public let maximumMomentAnisotropy: Float?
    public let momentAnisotropyLimitPenalty: Float?
    public let morphologyGuardFailureFitness: Float?
    public let internalStripePenalty: Float?
    public let orientedRidgePenalty: Float?
    public let largestComponentInternalStripePenalty: Float?
    public let largestComponentOrientedRidgePenalty: Float?
    public let templateSimilarityReward: Float?
    public let templateSequenceReward: Float?
    public let templateSequenceMassPenalty: Float?
    public let templateSequenceSupportPenalty: Float?
    public let templateSequenceChangePenalty: Float?
    public let templateSequenceDeltaReward: Float?
    public let templateSequenceSignedDeltaReward: Float?
    public let templateSequenceSteps: [Int]?
    public let templateSequenceStatePatches: [InitStatePatchConfig]?
    public let orientationPhaseMotionReward: Float?
    public let minimumOrientationPhaseMotion: Float?
    public let orientationPhaseMotionPenalty: Float?
    public let angularPhaseMotionReward: Float?
    public let angularPhaseMotionOrder: Int?
    public let angularPhaseMotionMinimumAmplitude: Float?
    public let minimumAngularPhaseMotion: Float?
    public let angularPhaseMotionPenalty: Float?
    public let sectorTransportReward: Float?
    public let sectorTransportBinCount: Int?
    public let sectorTransportMinimumContrast: Float?
    public let minimumSectorTransport: Float?
    public let sectorTransportPenalty: Float?
    public let minimumTrajectoryPathLength: Float?
    public let trajectoryPathLengthPenalty: Float?
    public let trajectoryPathLengthReward: Float?
    public let minimumTrajectoryDisplacement: Float?
    public let trajectoryDisplacementPenalty: Float?
    public let trajectoryDisplacementReward: Float?
    public let minimumMovementEfficiency: Float?
    public let movementEfficiencyPenalty: Float?
    public let movementEfficiencyReward: Float?
    public let minimumCenterVelocity: Float?
    public let centerVelocityPenalty: Float?
    public let centerVelocityReward: Float?
    public let translatedShapeOverlapMin: Float?
    public let componentCountMax: Float?
    public let largestComponentFractionMin: Float?
    public let largestComponentSolidityMin: Float?
    public let largestComponentMeanThicknessMin: Float?
    public let largestComponentFilamentarityMax: Float?
    public let occupiedFractionMin: Float?
    public let occupiedFractionMax: Float?
    public let occupiedGrowthMax: Float?
    public let organismnessPenalty: Float?
    public let morphologyThreshold: Float?

    enum CodingKeys: String, CodingKey {
        case objective
        case targetStep = "target_step"
        case angleThreshold = "angle_threshold"
        case minimumDisplacement = "minimum_displacement"
        case gyrationPenalty = "gyration_penalty"
        case componentCountPenalty = "component_count_penalty"
        case componentCountTarget = "component_count_target"
        case componentCountTargetPenalty = "component_count_target_penalty"
        case minimumComponentCount = "minimum_component_count"
        case maximumComponentCount = "maximum_component_count"
        case componentCountLimitPenalty = "component_count_limit_penalty"
        case largestComponentFractionReward = "largest_component_fraction_reward"
        case minimumLargestComponentFraction = "minimum_largest_component_fraction"
        case maximumLargestComponentFraction = "maximum_largest_component_fraction"
        case largestComponentFractionPenalty = "largest_component_fraction_penalty"
        case largestComponentFractionLimitPenalty = "largest_component_fraction_limit_penalty"
        case maximumLargestComponentAnisotropy = "maximum_largest_component_anisotropy"
        case largestComponentAnisotropyPenalty = "largest_component_anisotropy_penalty"
        case componentMassEvennessReward = "component_mass_evenness_reward"
        case minimumComponentMassEvenness = "minimum_component_mass_evenness"
        case componentMassEvennessPenalty = "component_mass_evenness_penalty"
        case minimumMomentMass = "minimum_moment_mass"
        case maximumMomentMass = "maximum_moment_mass"
        case largestComponentSolidityReward = "largest_component_solidity_reward"
        case largestComponentMeanThicknessReward = "largest_component_mean_thickness_reward"
        case largestComponentFilamentarityPenalty = "largest_component_filamentarity_penalty"
        case momentDensityReward = "moment_density_reward"
        case minimumMomentDensity = "minimum_moment_density"
        case maximumMomentDensity = "maximum_moment_density"
        case momentDensityPenalty = "moment_density_penalty"
        case momentAnisotropyPenalty = "moment_anisotropy_penalty"
        case maximumMomentAnisotropy = "maximum_moment_anisotropy"
        case momentAnisotropyLimitPenalty = "moment_anisotropy_limit_penalty"
        case morphologyGuardFailureFitness = "morphology_guard_failure_fitness"
        case internalStripePenalty = "internal_stripe_penalty"
        case orientedRidgePenalty = "oriented_ridge_penalty"
        case largestComponentInternalStripePenalty = "largest_component_internal_stripe_penalty"
        case largestComponentOrientedRidgePenalty = "largest_component_oriented_ridge_penalty"
        case templateSimilarityReward = "template_similarity_reward"
        case templateSequenceReward = "template_sequence_reward"
        case templateSequenceMassPenalty = "template_sequence_mass_penalty"
        case templateSequenceSupportPenalty = "template_sequence_support_penalty"
        case templateSequenceChangePenalty = "template_sequence_change_penalty"
        case templateSequenceDeltaReward = "template_sequence_delta_reward"
        case templateSequenceSignedDeltaReward = "template_sequence_signed_delta_reward"
        case templateSequenceSteps = "template_sequence_steps"
        case templateSequenceStatePatches = "template_sequence_state_patches"
        case orientationPhaseMotionReward = "orientation_phase_motion_reward"
        case minimumOrientationPhaseMotion = "minimum_orientation_phase_motion"
        case orientationPhaseMotionPenalty = "orientation_phase_motion_penalty"
        case angularPhaseMotionReward = "angular_phase_motion_reward"
        case angularPhaseMotionOrder = "angular_phase_motion_order"
        case angularPhaseMotionMinimumAmplitude = "angular_phase_motion_minimum_amplitude"
        case minimumAngularPhaseMotion = "minimum_angular_phase_motion"
        case angularPhaseMotionPenalty = "angular_phase_motion_penalty"
        case sectorTransportReward = "sector_transport_reward"
        case sectorTransportBinCount = "sector_transport_bin_count"
        case sectorTransportMinimumContrast = "sector_transport_minimum_contrast"
        case minimumSectorTransport = "minimum_sector_transport"
        case sectorTransportPenalty = "sector_transport_penalty"
        case minimumTrajectoryPathLength = "minimum_trajectory_path_length"
        case trajectoryPathLengthPenalty = "trajectory_path_length_penalty"
        case trajectoryPathLengthReward = "trajectory_path_length_reward"
        case minimumTrajectoryDisplacement = "minimum_trajectory_displacement"
        case trajectoryDisplacementPenalty = "trajectory_displacement_penalty"
        case trajectoryDisplacementReward = "trajectory_displacement_reward"
        case minimumMovementEfficiency = "minimum_movement_efficiency"
        case movementEfficiencyPenalty = "movement_efficiency_penalty"
        case movementEfficiencyReward = "movement_efficiency_reward"
        case minimumCenterVelocity = "minimum_center_velocity"
        case centerVelocityPenalty = "center_velocity_penalty"
        case centerVelocityReward = "center_velocity_reward"
        case translatedShapeOverlapMin = "translated_shape_overlap_min"
        case componentCountMax = "component_count_max"
        case largestComponentFractionMin = "largest_component_fraction_min"
        case largestComponentSolidityMin = "largest_component_solidity_min"
        case largestComponentMeanThicknessMin = "largest_component_mean_thickness_min"
        case largestComponentFilamentarityMax = "largest_component_filamentarity_max"
        case occupiedFractionMin = "occupied_fraction_min"
        case occupiedFractionMax = "occupied_fraction_max"
        case occupiedGrowthMax = "occupied_growth_max"
        case organismnessPenalty = "organismness_penalty"
        case morphologyThreshold = "morphology_threshold"
    }

    public init(
        objective: String,
        targetStep: Int,
        angleThreshold: Float,
        minimumDisplacement: Float? = nil,
        gyrationPenalty: Float? = nil,
        componentCountPenalty: Float? = nil,
        componentCountTarget: Float? = nil,
        componentCountTargetPenalty: Float? = nil,
        minimumComponentCount: Float? = nil,
        maximumComponentCount: Float? = nil,
        componentCountLimitPenalty: Float? = nil,
        largestComponentFractionReward: Float? = nil,
        minimumLargestComponentFraction: Float? = nil,
        maximumLargestComponentFraction: Float? = nil,
        largestComponentFractionPenalty: Float? = nil,
        largestComponentFractionLimitPenalty: Float? = nil,
        maximumLargestComponentAnisotropy: Float? = nil,
        largestComponentAnisotropyPenalty: Float? = nil,
        componentMassEvennessReward: Float? = nil,
        minimumComponentMassEvenness: Float? = nil,
        componentMassEvennessPenalty: Float? = nil,
        minimumMomentMass: Float? = nil,
        maximumMomentMass: Float? = nil,
        largestComponentSolidityReward: Float? = nil,
        largestComponentMeanThicknessReward: Float? = nil,
        largestComponentFilamentarityPenalty: Float? = nil,
        momentDensityReward: Float? = nil,
        minimumMomentDensity: Float? = nil,
        maximumMomentDensity: Float? = nil,
        momentDensityPenalty: Float? = nil,
        momentAnisotropyPenalty: Float? = nil,
        maximumMomentAnisotropy: Float? = nil,
        momentAnisotropyLimitPenalty: Float? = nil,
        morphologyGuardFailureFitness: Float? = nil,
        internalStripePenalty: Float? = nil,
        orientedRidgePenalty: Float? = nil,
        largestComponentInternalStripePenalty: Float? = nil,
        largestComponentOrientedRidgePenalty: Float? = nil,
        templateSimilarityReward: Float? = nil,
        templateSequenceReward: Float? = nil,
        templateSequenceMassPenalty: Float? = nil,
        templateSequenceSupportPenalty: Float? = nil,
        templateSequenceChangePenalty: Float? = nil,
        templateSequenceDeltaReward: Float? = nil,
        templateSequenceSignedDeltaReward: Float? = nil,
        templateSequenceSteps: [Int]? = nil,
        templateSequenceStatePatches: [InitStatePatchConfig]? = nil,
        orientationPhaseMotionReward: Float? = nil,
        minimumOrientationPhaseMotion: Float? = nil,
        orientationPhaseMotionPenalty: Float? = nil,
        angularPhaseMotionReward: Float? = nil,
        angularPhaseMotionOrder: Int? = nil,
        angularPhaseMotionMinimumAmplitude: Float? = nil,
        minimumAngularPhaseMotion: Float? = nil,
        angularPhaseMotionPenalty: Float? = nil,
        sectorTransportReward: Float? = nil,
        sectorTransportBinCount: Int? = nil,
        sectorTransportMinimumContrast: Float? = nil,
        minimumSectorTransport: Float? = nil,
        sectorTransportPenalty: Float? = nil,
        minimumTrajectoryPathLength: Float? = nil,
        trajectoryPathLengthPenalty: Float? = nil,
        trajectoryPathLengthReward: Float? = nil,
        minimumTrajectoryDisplacement: Float? = nil,
        trajectoryDisplacementPenalty: Float? = nil,
        trajectoryDisplacementReward: Float? = nil,
        minimumMovementEfficiency: Float? = nil,
        movementEfficiencyPenalty: Float? = nil,
        movementEfficiencyReward: Float? = nil,
        minimumCenterVelocity: Float? = nil,
        centerVelocityPenalty: Float? = nil,
        centerVelocityReward: Float? = nil,
        translatedShapeOverlapMin: Float? = nil,
        componentCountMax: Float? = nil,
        largestComponentFractionMin: Float? = nil,
        largestComponentSolidityMin: Float? = nil,
        largestComponentMeanThicknessMin: Float? = nil,
        largestComponentFilamentarityMax: Float? = nil,
        occupiedFractionMin: Float? = nil,
        occupiedFractionMax: Float? = nil,
        occupiedGrowthMax: Float? = nil,
        organismnessPenalty: Float? = nil,
        morphologyThreshold: Float? = nil
    ) {
        self.objective = objective
        self.targetStep = targetStep
        self.angleThreshold = angleThreshold
        self.minimumDisplacement = minimumDisplacement
        self.gyrationPenalty = gyrationPenalty
        self.componentCountPenalty = componentCountPenalty
        self.componentCountTarget = componentCountTarget
        self.componentCountTargetPenalty = componentCountTargetPenalty
        self.minimumComponentCount = minimumComponentCount
        self.maximumComponentCount = maximumComponentCount
        self.componentCountLimitPenalty = componentCountLimitPenalty
        self.largestComponentFractionReward = largestComponentFractionReward
        self.minimumLargestComponentFraction = minimumLargestComponentFraction
        self.maximumLargestComponentFraction = maximumLargestComponentFraction
        self.largestComponentFractionPenalty = largestComponentFractionPenalty
        self.largestComponentFractionLimitPenalty = largestComponentFractionLimitPenalty
        self.maximumLargestComponentAnisotropy = maximumLargestComponentAnisotropy
        self.largestComponentAnisotropyPenalty = largestComponentAnisotropyPenalty
        self.componentMassEvennessReward = componentMassEvennessReward
        self.minimumComponentMassEvenness = minimumComponentMassEvenness
        self.componentMassEvennessPenalty = componentMassEvennessPenalty
        self.minimumMomentMass = minimumMomentMass
        self.maximumMomentMass = maximumMomentMass
        self.largestComponentSolidityReward = largestComponentSolidityReward
        self.largestComponentMeanThicknessReward = largestComponentMeanThicknessReward
        self.largestComponentFilamentarityPenalty = largestComponentFilamentarityPenalty
        self.momentDensityReward = momentDensityReward
        self.minimumMomentDensity = minimumMomentDensity
        self.maximumMomentDensity = maximumMomentDensity
        self.momentDensityPenalty = momentDensityPenalty
        self.momentAnisotropyPenalty = momentAnisotropyPenalty
        self.maximumMomentAnisotropy = maximumMomentAnisotropy
        self.momentAnisotropyLimitPenalty = momentAnisotropyLimitPenalty
        self.morphologyGuardFailureFitness = morphologyGuardFailureFitness
        self.internalStripePenalty = internalStripePenalty
        self.orientedRidgePenalty = orientedRidgePenalty
        self.largestComponentInternalStripePenalty = largestComponentInternalStripePenalty
        self.largestComponentOrientedRidgePenalty = largestComponentOrientedRidgePenalty
        self.templateSimilarityReward = templateSimilarityReward
        self.templateSequenceReward = templateSequenceReward
        self.templateSequenceMassPenalty = templateSequenceMassPenalty
        self.templateSequenceSupportPenalty = templateSequenceSupportPenalty
        self.templateSequenceChangePenalty = templateSequenceChangePenalty
        self.templateSequenceDeltaReward = templateSequenceDeltaReward
        self.templateSequenceSignedDeltaReward = templateSequenceSignedDeltaReward
        self.templateSequenceSteps = templateSequenceSteps
        self.templateSequenceStatePatches = templateSequenceStatePatches
        self.orientationPhaseMotionReward = orientationPhaseMotionReward
        self.minimumOrientationPhaseMotion = minimumOrientationPhaseMotion
        self.orientationPhaseMotionPenalty = orientationPhaseMotionPenalty
        self.angularPhaseMotionReward = angularPhaseMotionReward
        self.angularPhaseMotionOrder = angularPhaseMotionOrder
        self.angularPhaseMotionMinimumAmplitude = angularPhaseMotionMinimumAmplitude
        self.minimumAngularPhaseMotion = minimumAngularPhaseMotion
        self.angularPhaseMotionPenalty = angularPhaseMotionPenalty
        self.sectorTransportReward = sectorTransportReward
        self.sectorTransportBinCount = sectorTransportBinCount
        self.sectorTransportMinimumContrast = sectorTransportMinimumContrast
        self.minimumSectorTransport = minimumSectorTransport
        self.sectorTransportPenalty = sectorTransportPenalty
        self.minimumTrajectoryPathLength = minimumTrajectoryPathLength
        self.trajectoryPathLengthPenalty = trajectoryPathLengthPenalty
        self.trajectoryPathLengthReward = trajectoryPathLengthReward
        self.minimumTrajectoryDisplacement = minimumTrajectoryDisplacement
        self.trajectoryDisplacementPenalty = trajectoryDisplacementPenalty
        self.trajectoryDisplacementReward = trajectoryDisplacementReward
        self.minimumMovementEfficiency = minimumMovementEfficiency
        self.movementEfficiencyPenalty = movementEfficiencyPenalty
        self.movementEfficiencyReward = movementEfficiencyReward
        self.minimumCenterVelocity = minimumCenterVelocity
        self.centerVelocityPenalty = centerVelocityPenalty
        self.centerVelocityReward = centerVelocityReward
        self.translatedShapeOverlapMin = translatedShapeOverlapMin
        self.componentCountMax = componentCountMax
        self.largestComponentFractionMin = largestComponentFractionMin
        self.largestComponentSolidityMin = largestComponentSolidityMin
        self.largestComponentMeanThicknessMin = largestComponentMeanThicknessMin
        self.largestComponentFilamentarityMax = largestComponentFilamentarityMax
        self.occupiedFractionMin = occupiedFractionMin
        self.occupiedFractionMax = occupiedFractionMax
        self.occupiedGrowthMax = occupiedGrowthMax
        self.organismnessPenalty = organismnessPenalty
        self.morphologyThreshold = morphologyThreshold
    }

    var usesMorphologyMetrics: Bool {
            usesMorphologyGuard ||
            componentCountPenalty != nil ||
            componentCountTargetPenalty != nil ||
            componentCountLimitPenalty != nil ||
            objective == "body_locomotion" ||
            componentCountPenalty != nil ||
            largestComponentFractionReward != nil ||
            largestComponentFractionPenalty != nil ||
            largestComponentFractionLimitPenalty != nil ||
            maximumLargestComponentFraction != nil ||
            maximumLargestComponentAnisotropy != nil ||
            largestComponentAnisotropyPenalty != nil ||
            componentMassEvennessReward != nil ||
            componentMassEvennessPenalty != nil ||
            minimumComponentMassEvenness != nil ||
            minimumMomentMass != nil ||
            maximumMomentMass != nil ||
            largestComponentSolidityReward != nil ||
            largestComponentMeanThicknessReward != nil ||
            largestComponentFilamentarityPenalty != nil ||
            momentDensityReward != nil ||
            momentDensityPenalty != nil ||
            maximumMomentDensity != nil ||
            momentAnisotropyPenalty != nil ||
            momentAnisotropyLimitPenalty != nil ||
            internalStripePenalty != nil ||
            orientedRidgePenalty != nil ||
            largestComponentInternalStripePenalty != nil ||
            largestComponentOrientedRidgePenalty != nil ||
            templateSimilarityReward != nil
    }

    var usesMorphologyGuard: Bool {
        morphologyGuardFailureFitness != nil
    }

    var usesTemplateSequence: Bool {
        templateSequenceReward != nil ||
            templateSequenceMassPenalty != nil ||
            templateSequenceSupportPenalty != nil ||
            templateSequenceChangePenalty != nil ||
            templateSequenceDeltaReward != nil ||
            templateSequenceSignedDeltaReward != nil
    }

    var usesOrientationPhaseMotion: Bool {
        orientationPhaseMotionReward != nil ||
            orientationPhaseMotionPenalty != nil
    }

    var usesAngularPhaseMotion: Bool {
        angularPhaseMotionReward != nil ||
            angularPhaseMotionPenalty != nil
    }

    var usesSectorTransport: Bool {
        sectorTransportReward != nil ||
            sectorTransportPenalty != nil
    }

    var usesTrajectoryMetrics: Bool {
        trajectoryPathLengthPenalty != nil ||
            trajectoryPathLengthReward != nil ||
            trajectoryDisplacementPenalty != nil ||
            trajectoryDisplacementReward != nil ||
            movementEfficiencyPenalty != nil ||
            movementEfficiencyReward != nil ||
            centerVelocityPenalty != nil ||
            centerVelocityReward != nil
    }
}

public struct ESObstacleFieldConfig: Codable {
    public let enabled: Bool
    public let channelIndex: Int
    public let mode: String
    public let count: Int
    public let circleRadius: Float
    public let sigma: Float
    public let amplitude: Float
    public let center: [Float]?
    public let seed: Int

    enum CodingKeys: String, CodingKey {
        case enabled
        case channelIndex = "channel_index"
        case mode
        case count
        case circleRadius = "circle_radius"
        case sigma
        case amplitude
        case center
        case seed
    }

    public init(
        enabled: Bool,
        channelIndex: Int,
        mode: String,
        count: Int,
        circleRadius: Float,
        sigma: Float,
        amplitude: Float,
        center: [Float]?,
        seed: Int
    ) {
        self.enabled = enabled
        self.channelIndex = channelIndex
        self.mode = mode
        self.count = count
        self.circleRadius = circleRadius
        self.sigma = sigma
        self.amplitude = amplitude
        self.center = center
        self.seed = seed
    }
}

public struct InitPatchConfig: Codable {
    public let enabled: Bool
    public let size: Int
    public let center: [Int]
    public let valueLow: Float
    public let valueHigh: Float

    enum CodingKeys: String, CodingKey {
        case enabled
        case size
        case center
        case valueLow = "value_low"
        case valueHigh = "value_high"
    }

    public init(enabled: Bool, size: Int, center: [Int], valueLow: Float, valueHigh: Float) {
        self.enabled = enabled
        self.size = size
        self.center = center
        self.valueLow = valueLow
        self.valueHigh = valueHigh
    }
}

public struct ESConfig: Codable {
    public let outputDir: String
    public let generations: Int
    public let population: Int
    public let sigma: Float
    public let learningRate: Float
    public let seed: Int
    public let steps: Int
    public let fitness: FitnessConfig
    public let fitnessShaping: String  // "centered_rank", "standardize", "raw"
    public let includeParent: Bool?
    public let initPatch: InitPatchConfig?
    public let initialInitPatchValues: [Float]?
    public let initialKernelParams: KernelParams?
    public let paramRanges: [String: [Float]]?
    public let obstacleField: ESObstacleFieldConfig?

    enum CodingKeys: String, CodingKey {
        case outputDir = "output_dir"
        case generations
        case population
        case sigma
        case learningRate = "learning_rate"
        case seed
        case steps
        case fitness
        case fitnessShaping = "fitness_shaping"
        case includeParent = "include_parent"
        case initPatch = "init_patch"
        case initialInitPatchValues = "initial_init_patch_values"
        case initialKernelParams = "initial_kernel_params"
        case paramRanges = "param_ranges"
        case obstacleField = "obstacle_field"
    }

    public init(
        outputDir: String,
        generations: Int,
        population: Int,
        sigma: Float,
        learningRate: Float,
        seed: Int,
        steps: Int,
        fitness: FitnessConfig,
        fitnessShaping: String,
        includeParent: Bool? = nil,
        initPatch: InitPatchConfig?,
        initialInitPatchValues: [Float]?,
        initialKernelParams: KernelParams? = nil,
        paramRanges: [String: [Float]]?,
        obstacleField: ESObstacleFieldConfig?
    ) {
        self.outputDir = outputDir
        self.generations = generations
        self.population = population
        self.sigma = sigma
        self.learningRate = learningRate
        self.seed = seed
        self.steps = steps
        self.fitness = fitness
        self.fitnessShaping = fitnessShaping
        self.includeParent = includeParent
        self.initPatch = initPatch
        self.initialInitPatchValues = initialInitPatchValues
        self.initialKernelParams = initialKernelParams
        self.paramRanges = paramRanges
        self.obstacleField = obstacleField
    }
}

public struct FlowMAPElitesDescriptorConfig: Codable {
    public let name: String
    public let min: Float
    public let max: Float
    public let bins: Int

    public init(name: String, min: Float, max: Float, bins: Int) {
        self.name = name
        self.min = min
        self.max = max
        self.bins = bins
    }
}

public struct FlowMAPElitesConfig: Codable {
    public let outputDir: String
    public let generations: Int
    public let population: Int
    public let sigma: Float
    public let lineSigma: Float
    public let seed: Int
    public let steps: Int
    public let fitness: FitnessConfig
    public let includeParent: Bool?
    public let descriptors: [FlowMAPElitesDescriptorConfig]
    public let exportTop: Int?
    public let exportReplayPoolLimit: Int?
    public let initPatch: InitPatchConfig?
    public let initialInitPatchValues: [Float]?
    public let initialKernelParams: KernelParams?
    public let paramRanges: [String: [Float]]?
    public let obstacleField: ESObstacleFieldConfig?

    enum CodingKeys: String, CodingKey {
        case outputDir = "output_dir"
        case generations
        case population
        case sigma
        case lineSigma = "line_sigma"
        case seed
        case steps
        case fitness
        case includeParent = "include_parent"
        case descriptors
        case exportTop = "export_top"
        case exportReplayPoolLimit = "export_replay_pool_limit"
        case initPatch = "init_patch"
        case initialInitPatchValues = "initial_init_patch_values"
        case initialKernelParams = "initial_kernel_params"
        case paramRanges = "param_ranges"
        case obstacleField = "obstacle_field"
    }

    public init(
        outputDir: String,
        generations: Int,
        population: Int,
        sigma: Float,
        lineSigma: Float,
        seed: Int,
        steps: Int,
        fitness: FitnessConfig,
        includeParent: Bool? = nil,
        descriptors: [FlowMAPElitesDescriptorConfig],
        exportTop: Int? = nil,
        exportReplayPoolLimit: Int? = nil,
        initPatch: InitPatchConfig?,
        initialInitPatchValues: [Float]?,
        initialKernelParams: KernelParams? = nil,
        paramRanges: [String: [Float]]?,
        obstacleField: ESObstacleFieldConfig?
    ) {
        self.outputDir = outputDir
        self.generations = generations
        self.population = population
        self.sigma = sigma
        self.lineSigma = lineSigma
        self.seed = seed
        self.steps = steps
        self.fitness = fitness
        self.includeParent = includeParent
        self.descriptors = descriptors
        self.exportTop = exportTop
        self.exportReplayPoolLimit = exportReplayPoolLimit
        self.initPatch = initPatch
        self.initialInitPatchValues = initialInitPatchValues
        self.initialKernelParams = initialKernelParams
        self.paramRanges = paramRanges
        self.obstacleField = obstacleField
    }

    public func asESConfig(outputDir overrideOutputDir: String? = nil) -> ESConfig {
        ESConfig(
            outputDir: overrideOutputDir ?? outputDir,
            generations: generations,
            population: population,
            sigma: sigma,
            learningRate: 0.0,
            seed: seed,
            steps: steps,
            fitness: fitness,
            fitnessShaping: "raw",
            includeParent: includeParent,
            initPatch: initPatch,
            initialInitPatchValues: initialInitPatchValues,
            initialKernelParams: initialKernelParams,
            paramRanges: paramRanges,
            obstacleField: obstacleField
        )
    }
}

public struct FlowMAPElitesCandidateEvaluation: Sendable {
    public let candidate: [Float]
    public let fitness: Float
    public let descriptors: [String: Float]

    public init(candidate: [Float], fitness: Float, descriptors: [String: Float]) {
        self.candidate = candidate
        self.fitness = fitness
        self.descriptors = descriptors
    }
}

// Parameter space with sigmoid/logit normalization (matches es.py)

public struct ParamSlice {
    public let start: Int
    public let end: Int
    public let shape: [Int]

    public init(start: Int, end: Int, shape: [Int]) {
        self.start = start
        self.end = end
        self.shape = shape
    }
}

public struct ParamSpace {
    public let slices: [String: ParamSlice]
    public let low: [Float]
    public let high: [Float]
    public let totalDim: Int
    public let radialParamCount: Int

    public init(nbK: Int, ranges: [String: (Float, Float)], radialParamCount: Int = 3) {
        precondition(radialParamCount > 0, "ParamSpace radialParamCount must be positive.")
        var slices: [String: ParamSlice] = [:]
        var low: [Float] = []
        var high: [Float] = []
        var offset = 0

        func add(_ name: String, _ shape: [Int]) {
            let (lo, hi) = ranges[name]!
            let size = shape.reduce(1, *)
            slices[name] = ParamSlice(start: offset, end: offset + size, shape: shape)
            low.append(contentsOf: [Float](repeating: lo, count: size))
            high.append(contentsOf: [Float](repeating: hi, count: size))
            offset += size
        }

        add("r", [nbK])
        add("b", [nbK, radialParamCount])
        add("w", [nbK, radialParamCount])
        add("a", [nbK, radialParamCount])
        add("m", [nbK])
        add("s", [nbK])
        add("h", [nbK])
        add("R", [1])

        self.slices = slices
        self.low = low
        self.high = high
        self.totalDim = offset
        self.radialParamCount = radialParamCount
    }
}

private func sigmoid(_ x: Float) -> Float {
    1.0 / (1.0 + exp(-x))
}

private func logit(_ x: Float) -> Float {
    log(x / (1.0 - x))
}

private func sigmoidArray(_ x: [Float]) -> [Float] {
    x.map { sigmoid($0) }
}

public func paramsToVector(_ params: ResolvedParams, space: ParamSpace) -> [Float] {
    var vec = [Float](repeating: 0.0, count: space.totalDim)

    func encode(_ name: String, _ values: [Float]) {
        let slice = space.slices[name]!
        for (i, val) in values.enumerated() {
            let lo = space.low[slice.start + i]
            let hi = space.high[slice.start + i]
            let span = hi - lo
            let normalized = (val - lo) / (span == 0 ? 1.0 : span)
            let clipped = max(1e-6, min(1.0 - 1e-6, normalized))
            vec[slice.start + i] = logit(clipped)
        }
    }

    encode("r", params.r)
    encode("b", params.b.flatMap { $0 })
    encode("w", params.w.flatMap { $0 })
    encode("a", params.a.flatMap { $0 })
    encode("m", params.m)
    encode("s", params.s)
    encode("h", params.h)
    encode("R", [params.R])

    return vec
}

public func vectorToParams(_ vec: [Float], space: ParamSpace, seed: Int = 0) -> ResolvedParams {
    let scaled = zip(zip(space.low, space.high), vec).map { (bounds, v) in
        let (lo, hi) = bounds
        return lo + sigmoid(v) * (hi - lo)
    }

    func decode1D(_ name: String) -> [Float] {
        let slice = space.slices[name]!
        return Array(scaled[slice.start..<slice.end])
    }

    func decode2D(_ name: String, cols: Int) -> [[Float]] {
        let slice = space.slices[name]!
        let flat = Array(scaled[slice.start..<slice.end])
        let rows = flat.count / cols
        return (0..<rows).map { r in
            Array(flat[r * cols..<(r + 1) * cols])
        }
    }

    return ResolvedParams(
        r: decode1D("r"),
        b: decode2D("b", cols: space.radialParamCount),
        w: decode2D("w", cols: space.radialParamCount),
        a: decode2D("a", cols: space.radialParamCount),
        m: decode1D("m"),
        s: decode1D("s"),
        h: decode1D("h"),
        R: decode1D("R")[0],
        seed: seed
    )
}

private func resolvedParams(from kernelParams: KernelParams, space: ParamSpace, seed: Int = 0) -> ResolvedParams {
    let kernelCount = space.slices["r"]?.shape.first ?? 0
    guard kernelParams.r.count == kernelCount,
          kernelParams.b.count == kernelCount,
          kernelParams.w.count == kernelCount,
          kernelParams.a.count == kernelCount,
          kernelParams.m.count == kernelCount,
          kernelParams.s.count == kernelCount,
          kernelParams.h.count == kernelCount else {
        fatalError("initial_kernel_params shape does not match ES topology nbK=\(kernelCount).")
    }

    func radialRows(_ name: String, _ rows: [[Float]], fill: Float) -> [[Float]] {
        rows.enumerated().map { index, row in
            guard row.count <= space.radialParamCount else {
                fatalError("initial_kernel_params.\(name)[\(index)] has \(row.count) entries; expected at most \(space.radialParamCount).")
            }
            return Array((row + Array(repeating: fill, count: space.radialParamCount)).prefix(space.radialParamCount))
        }
    }

    return ResolvedParams(
        r: kernelParams.r,
        b: radialRows("b", kernelParams.b, fill: 0.0),
        w: radialRows("w", kernelParams.w, fill: 0.0),
        a: radialRows("a", kernelParams.a, fill: 0.0),
        m: kernelParams.m,
        s: kernelParams.s,
        h: kernelParams.h,
        R: kernelParams.R,
        seed: seed
    )
}

private func radialParamCount(runtimeParams: ResolvedParams, initialKernelParams: KernelParams?) -> Int {
    var count = 1
    func include(_ rows: [[Float]]) {
        for row in rows {
            count = max(count, row.count)
        }
    }
    include(runtimeParams.b)
    include(runtimeParams.w)
    include(runtimeParams.a)
    if let initialKernelParams {
        include(initialKernelParams.b)
        include(initialKernelParams.w)
        include(initialKernelParams.a)
    }
    return count
}

// Adam Optimizer (matches es.py)

public class Adam {
    public let lr: Float
    public let beta1: Float
    public let beta2: Float
    public let eps: Float

    public var m: [Float]?
    public var v: [Float]?
    public var t: Int = 0

    public init(lr: Float, beta1: Float = 0.9, beta2: Float = 0.999, eps: Float = 1e-8) {
        self.lr = lr
        self.beta1 = beta1
        self.beta2 = beta2
        self.eps = eps
    }

    public func step(params: [Float], grad: [Float]) -> [Float] {
        if m == nil {
            m = [Float](repeating: 0.0, count: params.count)
            v = [Float](repeating: 0.0, count: params.count)
        }

        t += 1
        var newParams = params

        for i in 0..<params.count {
            m![i] = beta1 * m![i] + (1.0 - beta1) * grad[i]
            v![i] = beta2 * v![i] + (1.0 - beta2) * grad[i] * grad[i]

            let mHat = m![i] / (1.0 - pow(beta1, Float(t)))
            let vHat = v![i] / (1.0 - pow(beta2, Float(t)))

            let stepVal = lr * mHat / (sqrt(vHat) + eps)
            newParams[i] = params[i] + stepVal
        }

        return newParams
    }
}

// Fitness shaping (matches es.py)

public func fitnessShaping(_ fitness: [Float], mode: String) -> [Float] {
    switch mode {
    case "raw":
        return fitness

    case "standardize":
        let mean = fitness.reduce(0, +) / Float(fitness.count)
        let variance = fitness.map { ($0 - mean) * ($0 - mean) }.reduce(0, +) / Float(fitness.count)
        let std = sqrt(variance)
        if std == 0 {
            return fitness.map { $0 - mean }
        }
        return fitness.map { ($0 - mean) / std }

    case "centered_rank":
        let indexed = fitness.enumerated().map { ($0.offset, $0.element) }
        let sorted = indexed.sorted { $0.1 < $1.1 }
        var ranks = [Float](repeating: 0.0, count: fitness.count)
        for (rank, (idx, _)) in sorted.enumerated() {
            ranks[idx] = Float(rank)
        }
        let n = Float(fitness.count)
        if n > 1 {
            return ranks.map { $0 / (n - 1) - 0.5 }
        }
        return ranks.map { _ in 0.0 }

    default:
        return fitness
    }
}


func sampleOpenESNoise(
    population: Int,
    dimensions: Int,
    rng: inout SeededRandomNumberGenerator
) -> [[Float]] {
    guard population > 0 else { return [] }
    guard population % 2 == 0 else {
        fatalError("OpenES population must be even for antithetic sampling.")
    }

    let half = population / 2
    var plus = Array(
        repeating: Array(repeating: Float(0.0), count: dimensions),
        count: half
    )
    for i in 0..<half {
        for j in 0..<dimensions {
            plus[i][j] = gaussianSample(rng: &rng)
        }
    }

    var noise = plus
    noise.reserveCapacity(population)
    for row in plus {
        noise.append(row.map(-))
    }
    return noise
}

// Center of mass computation (matches es.py)

func excludedMassChannelsForEvolution(
    channels: Int,
    chemotaxis: ChemotaxisConfig?,
    food: FoodConfig?,
    obstacleField: ESObstacleFieldConfig?
) -> Set<Int> {
    flowExcludedMassChannels(
        channels: channels,
        chemotaxis: chemotaxis,
        food: food,
        additionalExcludedChannels: obstacleField.map { $0.enabled ? [$0.channelIndex] : [] } ?? []
    )
}

func creatureChannelsForEvolution(
    channels: Int,
    chemotaxis: ChemotaxisConfig?,
    food: FoodConfig?,
    obstacleField: ESObstacleFieldConfig?
) -> [Int] {
    flowCreatureChannels(
        channels: channels,
        chemotaxis: chemotaxis,
        food: food,
        additionalExcludedChannels: obstacleField.map { $0.enabled ? [$0.channelIndex] : [] } ?? []
    )
}

func evolutionMassMap(_ A: MLXArray, excludedChannels: Set<Int>) -> MLXArray {
    flowMatterMap(A, excludedChannels: excludedChannels)
}

private func evolutionMassMapBatch(_ A: MLXArray, excludedChannels: Set<Int>) -> MLXArray {
    flowMatterMap(A, excludedChannels: excludedChannels)
}

public func centerOfMass(_ A: MLXArray, excludedChannels: Set<Int> = []) -> (Float, Float)? {
    let massMap = evolutionMassMap(A, excludedChannels: excludedChannels)
    let sx = A.shape[0]
    let sy = A.shape[1]
    let coordsX = MLXArray(Array(0..<sx).map { Float($0) }).reshaped([sx, 1])
    let coordsY = MLXArray(Array(0..<sy).map { Float($0) }).reshaped([1, sy])
    let totalArr = massMap.sum()
    let sumXArr = (massMap * coordsX).sum()
    let sumYArr = (massMap * coordsY).sum()
    eval(totalArr, sumXArr, sumYArr)
    let total = totalArr.item(Float.self)
    if total <= 0 {
        return nil
    }
    let cx = sumXArr.item(Float.self) / total
    let cy = sumYArr.item(Float.self) / total

    // Normalize to [-0.5, 0.5]
    return (cx / Float(sx) - 0.5, cy / Float(sy) - 0.5)
}

private func computeGyrationScalar(_ A: MLXArray, excludedChannels: Set<Int>) -> Float {
    let massMap = evolutionMassMap(A, excludedChannels: excludedChannels)
    let sx = A.shape[0]
    let sy = A.shape[1]
    let coordsX = MLXArray(Array(0..<sx).map { Float($0) }).reshaped([sx, 1])
    let coordsY = MLXArray(Array(0..<sy).map { Float($0) }).reshaped([1, sy])
    let totalMassArr = massMap.sum()
    let sumXArr = (massMap * coordsX).sum()
    let sumYArr = (massMap * coordsY).sum()
    eval(totalMassArr, sumXArr, sumYArr)
    let totalMass = totalMassArr.item(Float.self)
    if totalMass <= 0 { return 1.0 }
    let cxArr = sumXArr / totalMassArr
    let cyArr = sumYArr / totalMassArr
    let distSq = (coordsX - cxArr) * (coordsX - cxArr) + (coordsY - cyArr) * (coordsY - cyArr)
    let gyrationArr = (massMap * distSq).sum() / totalMassArr
    eval(gyrationArr)
    return gyrationArr.item(Float.self) / Float(sx * sy)
}

private func applyExternalField(
    _ A: MLXArray,
    field: MLXArray,
    channelIndex: Int
) -> MLXArray {
    overwriteFieldChannel(A, field: field, channelIndex: channelIndex)
}

private func applyExternalFieldBatch(
    _ A: MLXArray,
    field: MLXArray,
    channelIndex: Int
) -> MLXArray {
    let signpost = LeniaSignposts.beginStep("applyExternalFieldBatch")
    defer { LeniaSignposts.end(signpost) }
    return overwriteFieldChannel(A, field: field, channelIndex: channelIndex)
}

private func buildChemotaxisField(
    sx: Int,
    sy: Int,
    config: ChemotaxisConfig,
    evalSeed: Int
) -> MLXArray {
    let coordsX = MLXArray(Array(0..<sx).map { Float($0) })
    let coordsY = MLXArray(Array(0..<sy).map { Float($0) })
    let (X, Y) = meshgrid(coordsX, coordsY)

    var cx = config.center[0]
    var cy = config.center[1]
    if config.mode == "random_on_circle", let radius = config.circle_radius {
        var rng = SeededRandomNumberGenerator(seed: UInt64(evalSeed))
        let angle = Float.random(in: 0...(2 * Float.pi), using: &rng)
        cx += radius * cos(angle)
        cy += radius * sin(angle)
    }

    let distSq = (X - MLXArray(cx)) * (X - MLXArray(cx)) + (Y - MLXArray(cy)) * (Y - MLXArray(cy))
    let sigma = config.sigma
    let exponent = -distSq / MLXArray(2.0 * sigma * sigma)
    return MLXArray(config.amplitude) * MLX.exp(exponent)
}

private func buildObstacleField(
    sx: Int,
    sy: Int,
    config: ESObstacleFieldConfig,
    evalSeed: Int
) -> MLXArray {
    let center = config.center ?? [Float(sx) / 2.0, Float(sy) / 2.0]
    let sigmaSq = max(config.sigma * config.sigma, 1e-6)
    var rng = SeededRandomNumberGenerator(seed: UInt64(evalSeed))
    var obstacleCenters: [(Float, Float)] = []
    obstacleCenters.reserveCapacity(config.count)

    switch config.mode {
    case "random_on_circle":
        for _ in 0..<config.count {
            let angle = Float.random(in: 0...(2 * Float.pi), using: &rng)
            obstacleCenters.append((
                center[0] + config.circleRadius * cos(angle),
                center[1] + config.circleRadius * sin(angle)
            ))
        }
    default:
        fatalError("Unsupported obstacle_field.mode: \(config.mode)")
    }

    let coordsX = MLXArray(Array(0..<sx).map { Float($0) })
    let coordsY = MLXArray(Array(0..<sy).map { Float($0) })
    let (X, Y) = meshgrid(coordsX, coordsY)
    let xGrid = X.expandedDimensions(axis: -1)
    let yGrid = Y.expandedDimensions(axis: -1)
    let centersX = MLXArray(obstacleCenters.map(\.0)).reshaped([1, 1, obstacleCenters.count])
    let centersY = MLXArray(obstacleCenters.map(\.1)).reshaped([1, 1, obstacleCenters.count])
    let dx = xGrid - centersX
    let dy = yGrid - centersY
    let distSq = dx * dx + dy * dy
    let exponent = -distSq / MLXArray(2.0 * sigmaSq)
    let gaussian = MLXArray(config.amplitude) * MLX.exp(exponent)
    return gaussian.max(axis: -1)
}

private func buildObstaclePotential(from field: MLXArray) -> MLXArray {
    switch field.shape.count {
    case 2:
        return (field * MLXArray(-1.0)).expandedDimensions(axes: [0, 3])
    case 3:
        return (field * MLXArray(-1.0)).expandedDimensions(axis: 3)
    default:
        fatalError("obstacle potential expects rank-2 or rank-3 field")
    }
}

private func durationMs(_ duration: Duration) -> Double {
    Double(duration.components.seconds) * 1_000.0 +
        Double(duration.components.attoseconds) / 1_000_000_000_000_000.0
}

func componentCountTargetMismatch(_ componentCount: Float, target: Float) -> Float {
    abs(componentCount - target)
}

// Evolution Engine (matches es.py)

public final class EvolutionEngine {
    private enum PopulationEvaluator {
        case mlx
        case metalFull
    }

    private struct CenterSnapshot {
        let alive: Bool
        let x: Float
        let y: Float
    }

    private struct CandidateMeasurement {
        let initial: CenterSnapshot
        let mid: CenterSnapshot?
        let target: CenterSnapshot?
        let translatedShapeOverlap: Float?
        let midOccupiedFraction: Float?
        let targetOccupiedFraction: Float?
        let occupiedGrowth: Float?
        let gyration: Float?
        let componentCount: Float?
        let largestComponentFraction: Float?
        let largestComponentAnisotropy: Float?
        let componentMassEvenness: Float?
        let momentMass: Float?
        let largestComponentSolidity: Float?
        let largestComponentMeanThickness: Float?
        let largestComponentMaxThickness: Float?
        let largestComponentFilamentarity: Float?
        let momentDensity: Float?
        let occupiedFraction: Float?
        let momentAnisotropy: Float?
        let internalStripe: Float?
        let orientedRidge: Float?
        let largestComponentInternalStripe: Float?
        let largestComponentOrientedRidge: Float?
        let templateSimilarity: Float?
        let templateSequenceSimilarity: Float?
        let templateSequenceMassMismatch: Float?
        let templateSequenceSupportMismatch: Float?
        let templateSequenceChangeMismatch: Float?
        let templateSequenceDeltaSimilarity: Float?
        let templateSequenceSignedDeltaSimilarity: Float?
        let orientationPhaseMotion: Float?
        let angularPhaseMotion: Float?
        let sectorTransport: Float?
        let trajectoryPathLength: Float?
        let trajectoryDisplacement: Float?
        let movementEfficiency: Float?
        let centerVelocity: Float?
        let chemotaxisScore: Float?
    }

    private struct MorphologyMeasurementBatch {
        let componentCount: [Float]?
        let largestComponentFraction: [Float]?
        let largestComponentAnisotropy: [Float]?
        let componentMassEvenness: [Float]?
        let momentMass: [Float]?
        let largestComponentSolidity: [Float]?
        let largestComponentMeanThickness: [Float]?
        let largestComponentMaxThickness: [Float]?
        let largestComponentFilamentarity: [Float]?
        let momentDensity: [Float]?
        let occupiedFraction: [Float]?
        let momentAnisotropy: [Float]?
        let internalStripe: [Float]?
        let orientedRidge: [Float]?
        let largestComponentInternalStripe: [Float]?
        let largestComponentOrientedRidge: [Float]?
        let templateSimilarity: [Float]?
    }

    private struct PopulationEvaluation {
        let measurements: [CandidateMeasurement]
        let kernelCompileMs: Double
        let stateBuildMs: Double
        let fieldBuildMs: Double
        let rolloutMs: Double
        let measurementMs: Double
    }

    public let config: BatchedConfig
    public let runtimeConfig: LeniaRuntimeConfig
    public let populationSim: FlowLeniaBatched
    public let esConfig: ESConfig
    public let paramSpace: ParamSpace
    public let optimizer: Adam
    public let excludedMassChannels: Set<Int>
    public let creatureChannels: [Int]
    public let metricGridX: MLXArray
    public let metricGridY: MLXArray
    private let morphologyTemplate: MassTemplate?
    private let templateSequenceTemplates: [MassTemplate]?
    private let populationEvaluator: PopulationEvaluator
    private var metalFullPopulationRunner: FlowLeniaMetalFullStateRunner?

    public var theta: [Float]
    public var rng: SeededRandomNumberGenerator
    public var evaluationCounter: Int = 0

    // For init patch evolution
    public let initPatchDim: Int
    public let thetaParamsDim: Int

    public init(
        runtimeConfig: LeniaRuntimeConfig,
        esConfig: ESConfig,
        ranges: [String: (Float, Float)]
    ) {
        self.esConfig = esConfig
        self.runtimeConfig = runtimeConfig
        let builtConfig = batchedConfigFromRuntime(runtimeConfig)
        self.config = builtConfig
        self.excludedMassChannels = excludedMassChannelsForEvolution(
            channels: runtimeConfig.channels,
            chemotaxis: runtimeConfig.chemotaxis,
            food: runtimeConfig.food,
            obstacleField: esConfig.obstacleField
        )
        let builtCreatureChannels = creatureChannelsForEvolution(
            channels: runtimeConfig.channels,
            chemotaxis: runtimeConfig.chemotaxis,
            food: runtimeConfig.food,
            obstacleField: esConfig.obstacleField
        )
        self.creatureChannels = builtCreatureChannels

        let builtParamSpace = ParamSpace(
            nbK: builtConfig.nbK,
            ranges: ranges,
            radialParamCount: radialParamCount(
                runtimeParams: runtimeConfig.params,
                initialKernelParams: esConfig.initialKernelParams
            )
        )
        self.paramSpace = builtParamSpace
        self.thetaParamsDim = builtParamSpace.totalDim
        self.optimizer = Adam(lr: esConfig.learningRate)
        self.rng = SeededRandomNumberGenerator(seed: UInt64(esConfig.seed))

        let supportedObjectives: Set<String> = [
            "directed_motion",
            "angular_motion",
            "obstacle_navigation",
            "chemotaxis",
            "trajectory_motion",
            "template_sequence",
            "orientation_phase_motion",
            "angular_phase_motion",
            "sector_transport_motion",
            "coherent_transport",
            "body_locomotion",
            "organismness",
        ]
        if !supportedObjectives.contains(esConfig.fitness.objective) {
            fatalError("Unsupported evolution objective: \(esConfig.fitness.objective)")
        }
        if esConfig.population % 2 != 0 {
            fatalError("OpenES population must be even for antithetic sampling.")
        }
        if esConfig.fitness.objective == "chemotaxis",
           runtimeConfig.chemotaxis?.enabled != true {
            fatalError("chemotaxis objective requires chemotaxis.enabled in the base config.")
        }
        if esConfig.fitness.objective == "obstacle_navigation",
           esConfig.obstacleField?.enabled != true {
            fatalError("obstacle_navigation objective requires obstacle_field.enabled in the ES config.")
        }
        if esConfig.fitness.templateSimilarityReward != nil && runtimeConfig.statePatch == nil {
            fatalError("template_similarity_reward requires init.state_patch in the base config.")
        }
        if (esConfig.fitness.componentCountTarget == nil) !=
            (esConfig.fitness.componentCountTargetPenalty == nil) {
            fatalError("component_count_target and component_count_target_penalty must be provided together.")
        }
        if esConfig.fitness.componentCountLimitPenalty != nil &&
            esConfig.fitness.minimumComponentCount == nil &&
            esConfig.fitness.maximumComponentCount == nil {
            fatalError("component_count_limit_penalty requires minimum_component_count or maximum_component_count.")
        }
        if (esConfig.fitness.minimumComponentCount != nil || esConfig.fitness.maximumComponentCount != nil) &&
            esConfig.fitness.componentCountLimitPenalty == nil &&
            !esConfig.fitness.usesMorphologyGuard {
            fatalError("minimum_component_count/maximum_component_count require component_count_limit_penalty or morphology_guard_failure_fitness.")
        }
        if let minimum = esConfig.fitness.minimumComponentCount,
           let maximum = esConfig.fitness.maximumComponentCount,
           minimum > maximum {
            fatalError("minimum_component_count cannot exceed maximum_component_count.")
        }
        if (esConfig.fitness.minimumLargestComponentFraction == nil) !=
            (esConfig.fitness.largestComponentFractionPenalty == nil) &&
            !esConfig.fitness.usesMorphologyGuard {
            fatalError("minimum_largest_component_fraction and largest_component_fraction_penalty must be provided together unless morphology_guard_failure_fitness is set.")
        }
        if esConfig.fitness.largestComponentFractionPenalty != nil &&
            esConfig.fitness.minimumLargestComponentFraction == nil {
            fatalError("largest_component_fraction_penalty requires minimum_largest_component_fraction.")
        }
        if esConfig.fitness.largestComponentFractionLimitPenalty != nil &&
            esConfig.fitness.maximumLargestComponentFraction == nil {
            fatalError("largest_component_fraction_limit_penalty requires maximum_largest_component_fraction.")
        }
        if let minimum = esConfig.fitness.minimumLargestComponentFraction,
           let maximum = esConfig.fitness.maximumLargestComponentFraction,
           minimum > maximum {
            fatalError("minimum_largest_component_fraction cannot exceed maximum_largest_component_fraction.")
        }
        if (esConfig.fitness.minimumComponentMassEvenness == nil) !=
            (esConfig.fitness.componentMassEvennessPenalty == nil) &&
            !esConfig.fitness.usesMorphologyGuard {
            fatalError("minimum_component_mass_evenness and component_mass_evenness_penalty must be provided together unless morphology_guard_failure_fitness is set.")
        }
        if esConfig.fitness.componentMassEvennessPenalty != nil &&
            esConfig.fitness.minimumComponentMassEvenness == nil {
            fatalError("component_mass_evenness_penalty requires minimum_component_mass_evenness.")
        }
        if let minimum = esConfig.fitness.minimumComponentMassEvenness,
           (minimum < 0 || minimum > 1) {
            fatalError("minimum_component_mass_evenness must be between 0 and 1.")
        }
        if (esConfig.fitness.minimumMomentDensity == nil) !=
            (esConfig.fitness.momentDensityPenalty == nil) &&
            !esConfig.fitness.usesMorphologyGuard {
            fatalError("minimum_moment_density and moment_density_penalty must be provided together unless morphology_guard_failure_fitness is set.")
        }
        if esConfig.fitness.momentDensityPenalty != nil &&
            esConfig.fitness.minimumMomentDensity == nil {
            fatalError("moment_density_penalty requires minimum_moment_density.")
        }
        if (esConfig.fitness.maximumMomentAnisotropy == nil) !=
            (esConfig.fitness.momentAnisotropyLimitPenalty == nil) &&
            !esConfig.fitness.usesMorphologyGuard {
            fatalError("maximum_moment_anisotropy and moment_anisotropy_limit_penalty must be provided together unless morphology_guard_failure_fitness is set.")
        }
        if esConfig.fitness.momentAnisotropyLimitPenalty != nil &&
            esConfig.fitness.maximumMomentAnisotropy == nil {
            fatalError("moment_anisotropy_limit_penalty requires maximum_moment_anisotropy.")
        }
        if let minimum = esConfig.fitness.minimumMomentMass,
           let maximum = esConfig.fitness.maximumMomentMass,
           minimum > maximum {
            fatalError("minimum_moment_mass cannot exceed maximum_moment_mass.")
        }
        if let minimum = esConfig.fitness.minimumMomentDensity,
           let maximum = esConfig.fitness.maximumMomentDensity,
           minimum > maximum {
            fatalError("minimum_moment_density cannot exceed maximum_moment_density.")
        }
        let guardOnlyThresholdsPresent = esConfig.fitness.minimumMomentMass != nil ||
            esConfig.fitness.maximumMomentMass != nil ||
            esConfig.fitness.maximumMomentDensity != nil ||
            esConfig.fitness.maximumLargestComponentFraction != nil ||
            esConfig.fitness.maximumLargestComponentAnisotropy != nil ||
            esConfig.fitness.minimumComponentMassEvenness != nil
        if guardOnlyThresholdsPresent && !esConfig.fitness.usesMorphologyGuard {
            fatalError("guard-only morphology thresholds require morphology_guard_failure_fitness.")
        }
        if (esConfig.fitness.minimumTrajectoryPathLength == nil) !=
            (esConfig.fitness.trajectoryPathLengthPenalty == nil) {
            fatalError("minimum_trajectory_path_length and trajectory_path_length_penalty must be provided together.")
        }
        if (esConfig.fitness.minimumTrajectoryDisplacement == nil) !=
            (esConfig.fitness.trajectoryDisplacementPenalty == nil) {
            fatalError("minimum_trajectory_displacement and trajectory_displacement_penalty must be provided together.")
        }
        if (esConfig.fitness.minimumMovementEfficiency == nil) !=
            (esConfig.fitness.movementEfficiencyPenalty == nil) {
            fatalError("minimum_movement_efficiency and movement_efficiency_penalty must be provided together.")
        }
        if let minimum = esConfig.fitness.minimumMovementEfficiency,
           !(0...1).contains(minimum) {
            fatalError("minimum_movement_efficiency must be between 0 and 1.")
        }
        if (esConfig.fitness.minimumCenterVelocity == nil) !=
            (esConfig.fitness.centerVelocityPenalty == nil) {
            fatalError("minimum_center_velocity and center_velocity_penalty must be provided together.")
        }
        if (esConfig.fitness.minimumOrientationPhaseMotion == nil) !=
            (esConfig.fitness.orientationPhaseMotionPenalty == nil) {
            fatalError("minimum_orientation_phase_motion and orientation_phase_motion_penalty must be provided together.")
        }
        if (esConfig.fitness.minimumAngularPhaseMotion == nil) !=
            (esConfig.fitness.angularPhaseMotionPenalty == nil) {
            fatalError("minimum_angular_phase_motion and angular_phase_motion_penalty must be provided together.")
        }
        if (esConfig.fitness.minimumSectorTransport == nil) !=
            (esConfig.fitness.sectorTransportPenalty == nil) {
            fatalError("minimum_sector_transport and sector_transport_penalty must be provided together.")
        }
        if esConfig.fitness.usesAngularPhaseMotion {
            if let order = esConfig.fitness.angularPhaseMotionOrder, order <= 0 {
                fatalError("angular_phase_motion_order must be positive.")
            }
            if let minimumAmplitude = esConfig.fitness.angularPhaseMotionMinimumAmplitude,
               minimumAmplitude < 0 {
                fatalError("angular_phase_motion_minimum_amplitude cannot be negative.")
            }
        }
        if esConfig.fitness.usesSectorTransport {
            if let binCount = esConfig.fitness.sectorTransportBinCount, binCount < 8 {
                fatalError("sector_transport_bin_count must be at least 8.")
            }
            if let minimumContrast = esConfig.fitness.sectorTransportMinimumContrast,
               minimumContrast < 0 {
                fatalError("sector_transport_minimum_contrast cannot be negative.")
            }
        }
        let normalizedSequenceSteps = !(
            esConfig.fitness.usesTemplateSequence ||
                esConfig.fitness.usesTrajectoryMetrics ||
                esConfig.fitness.usesOrientationPhaseMotion ||
                esConfig.fitness.usesAngularPhaseMotion ||
                esConfig.fitness.usesSectorTransport
        )
            ? []
            : Array(Set(esConfig.fitness.templateSequenceSteps ?? [esConfig.fitness.targetStep])).sorted()
        if esConfig.fitness.usesTrajectoryMetrics && normalizedSequenceSteps.count < 2 {
            fatalError("trajectory no-regression metrics require at least two unique template_sequence_steps.")
        }
        if esConfig.fitness.usesOrientationPhaseMotion && normalizedSequenceSteps.count < 2 {
            fatalError("orientation_phase_motion metrics require at least two unique template_sequence_steps.")
        }
        if esConfig.fitness.usesAngularPhaseMotion && normalizedSequenceSteps.count < 2 {
            fatalError("angular_phase_motion metrics require at least two unique template_sequence_steps.")
        }
        if esConfig.fitness.usesSectorTransport && normalizedSequenceSteps.count < 2 {
            fatalError("sector_transport metrics require at least two unique template_sequence_steps.")
        }
        if esConfig.fitness.usesTemplateSequence &&
            runtimeConfig.statePatch == nil &&
            esConfig.fitness.templateSequenceStatePatches == nil {
            fatalError("template_sequence metrics require init.state_patch or template_sequence_state_patches.")
        }
        if let sequenceSteps = esConfig.fitness.templateSequenceSteps {
            if sequenceSteps.isEmpty {
                fatalError("template_sequence_steps must contain at least one step when provided.")
            }
            for step in sequenceSteps where step < 0 || step > esConfig.steps {
                fatalError("template_sequence_steps entries must be within 0...steps.")
            }
        }
        if esConfig.fitness.templateSequenceChangePenalty != nil && normalizedSequenceSteps.count < 2 {
            fatalError("template_sequence_change_penalty requires at least two unique template_sequence_steps.")
        }
        if esConfig.fitness.templateSequenceDeltaReward != nil && normalizedSequenceSteps.count < 2 {
            fatalError("template_sequence_delta_reward requires at least two unique template_sequence_steps.")
        }
        if esConfig.fitness.templateSequenceSignedDeltaReward != nil && normalizedSequenceSteps.count < 2 {
            fatalError("template_sequence_signed_delta_reward requires at least two unique template_sequence_steps.")
        }
        if let sequencePatches = esConfig.fitness.templateSequenceStatePatches {
            if sequencePatches.isEmpty {
                fatalError("template_sequence_state_patches must contain at least one patch when provided.")
            }
            if sequencePatches.count != normalizedSequenceSteps.count {
                fatalError("template_sequence_state_patches count must match unique template_sequence_steps count.")
            }
        }
        if let obstacleField = esConfig.obstacleField, obstacleField.enabled {
            if obstacleField.channelIndex < 0 || obstacleField.channelIndex >= runtimeConfig.channels {
                fatalError("obstacle_field.channel_index is out of range for configured channels.")
            }
            if obstacleField.count <= 0 {
                fatalError("obstacle_field.count must be > 0.")
            }
            if obstacleField.circleRadius <= 0 {
                fatalError("obstacle_field.circle_radius must be > 0.")
            }
            if obstacleField.sigma <= 0 {
                fatalError("obstacle_field.sigma must be > 0.")
            }
            if obstacleField.center != nil && obstacleField.center?.count != 2 {
                fatalError("obstacle_field.center must have exactly two coordinates when provided.")
            }
        }

        let initialParams = esConfig.initialKernelParams.map {
            resolvedParams(from: $0, space: builtParamSpace, seed: runtimeConfig.params.seed)
        } ?? runtimeConfig.params
        var thetaParams = paramsToVector(initialParams, space: builtParamSpace)

        // Handle init patch if enabled
        if let initPatch = esConfig.initPatch, initPatch.enabled {
            let patchSize = initPatch.size * initPatch.size * creatureChannels.count
            self.initPatchDim = patchSize

            var patchTheta: [Float] = []
            let initialValues = esConfig.initialInitPatchValues
            if let initialValues, initialValues.count != patchSize {
                fatalError("initial_init_patch_values count \(initialValues.count) does not match expected patch size \(patchSize).")
            }
            for index in 0..<patchSize {
                let val = initialValues?[index] ?? Float.random(in: initPatch.valueLow...initPatch.valueHigh, using: &rng)
                let normalized = (val - initPatch.valueLow) / (initPatch.valueHigh - initPatch.valueLow)
                let clipped = max(1e-6, min(1.0 - 1e-6, normalized))
                patchTheta.append(logit(clipped))
            }
            thetaParams.append(contentsOf: patchTheta)
        } else {
            self.initPatchDim = 0
        }

        self.theta = thetaParams

        let coordsX = MLXArray(Array(0..<config.sx).map { Float($0) }).reshaped([1, config.sx, 1])
        let coordsY = MLXArray(Array(0..<config.sy).map { Float($0) }).reshaped([1, 1, config.sy])
        self.metricGridX = coordsX
        self.metricGridY = coordsY
        self.morphologyTemplate = runtimeConfig.statePatch.map {
            makeStatePatchMassTemplate(
                statePatch: $0,
                gridHeight: builtConfig.sx,
                gridWidth: builtConfig.sy,
                includedChannels: builtCreatureChannels,
                threshold: esConfig.fitness.morphologyThreshold ?? 0.03
            )
        }
        self.templateSequenceTemplates = esConfig.fitness.templateSequenceStatePatches.map { patches in
            patches.map {
                makeStatePatchMassTemplate(
                    statePatch: $0,
                    gridHeight: builtConfig.sx,
                    gridWidth: builtConfig.sy,
                    includedChannels: builtCreatureChannels,
                    threshold: esConfig.fitness.morphologyThreshold ?? 0.03
                )
            }
        }

        let seedParams = Array(repeating: initialParams, count: esConfig.population)
        self.populationSim = FlowLeniaBatched(
            config: config,
            kernels: compilePopulationKernels(
                paramsBatch: seedParams,
                config: config,
                c0: runtimeConfig.c0,
                c1: runtimeConfig.c1
            )
        )

        switch runtimeConfig.backend {
        case .mlx:
            self.populationEvaluator = .mlx
        case .metalFull:
            Self.validateMetalBackendCompatibility(runtimeConfig: runtimeConfig, esConfig: esConfig)
            self.populationEvaluator = .metalFull
        }
    }

    private func reusableMetalFullPopulationRunner(kernels: CompiledKernels) -> FlowLeniaMetalFullStateRunner {
        if let runner = metalFullPopulationRunner {
            runner.updateKernels(kernels)
            runner.setMatterWeights(metalMatterWeights())
            return runner
        }
        let runner = FlowLeniaMetalFullStateRunner(
            config: config,
            kernels: kernels,
            batchCount: esConfig.population,
            matterWeights: metalMatterWeights()
        )
        metalFullPopulationRunner = runner
        return runner
    }

    private func metalMatterWeights() -> [Float]? {
        flowMatterWeights(channels: config.channels, excludedChannels: excludedMassChannels)
    }

    private func metalStaticChannelFields(
        chemFieldBatch: MLXArray?,
        obstacleFieldBatch: MLXArray?
    ) -> [FlowLeniaMetalChannelField] {
        var fields: [FlowLeniaMetalChannelField] = []
        if let field = chemFieldBatch,
           let chemotaxis = runtimeConfig.chemotaxis,
           chemotaxis.enabled {
            fields.append(FlowLeniaMetalChannelField(
                channelIndex: chemotaxis.channel_index,
                field: field.expandedDimensions(axis: 3)
            ))
        }
        if let field = obstacleFieldBatch,
           let obstacleField = esConfig.obstacleField,
           obstacleField.enabled {
            fields.append(FlowLeniaMetalChannelField(
                channelIndex: obstacleField.channelIndex,
                field: field.expandedDimensions(axis: 3)
            ))
        }
        return fields
    }

    public func buildInitialState(seed: Int) -> MLXArray {
        if let statePatch = runtimeConfig.statePatch {
            return buildExplicitRuntimeStatePatch(statePatch)
        }

        var localRng = SeededRandomNumberGenerator(seed: UInt64(seed))
        var data = [Float](repeating: 0.0, count: config.sx * config.sy * config.channels)

        let patches = runtimeConfig.patches.isEmpty
            ? [PatchConfig(center: [config.sx / 2, config.sy / 2], size: 40)]
            : runtimeConfig.patches
        let low = runtimeConfig.aUniform.low
        let high = runtimeConfig.aUniform.high

        for patch in patches {
            let cx = patch.center[0]
            let cy = patch.center[1]
            let half = patch.size / 2
            for x in (cx - half)..<(cx + patch.size - half) {
                for y in (cy - half)..<(cy + patch.size - half) {
                    for c in creatureChannels {
                        let idx = (x * config.sy + y) * config.channels + c
                        if idx >= 0 && idx < data.count {
                            data[idx] = Float.random(in: low...high, using: &localRng)
                        }
                    }
                }
            }
        }

        return MLXArray(data).reshaped([config.sx, config.sy, config.channels])
    }

    private func buildExplicitRuntimeStatePatch(_ statePatch: InitStatePatchConfig) -> MLXArray {
        let values = statePatch.decodedValues()
        precondition(statePatch.center.count >= 2, "init.state_patch.center must have x/y coordinates.")
        precondition(
            statePatch.channels == config.channels,
            "init.state_patch.channels must match runtime channels."
        )
        precondition(
            values.count == statePatch.width * statePatch.height * statePatch.channels,
            "init.state_patch.data length must match width*height*channels."
        )
        var data = [Float](repeating: 0.0, count: config.sx * config.sy * config.channels)

        let cx = statePatch.center[0]
        let cy = statePatch.center[1]
        let halfWidth = statePatch.width / 2
        let halfHeight = statePatch.height / 2
        let x0 = cx - halfWidth
        let x1 = cx + (statePatch.width - halfWidth)
        let y0 = cy - halfHeight
        let y1 = cy + (statePatch.height - halfHeight)
        precondition(
            x0 >= 0 && y0 >= 0 && x1 <= config.sx && y1 <= config.sy,
            "init.state_patch bounds must fit within the ES runtime grid."
        )

        var patchIndex = 0
        for x in x0..<x1 {
            for y in y0..<y1 {
                for channel in 0..<config.channels {
                    let idx = (x * config.sy + y) * config.channels + channel
                    data[idx] = values[patchIndex]
                    patchIndex += 1
                }
            }
        }

        return MLXArray(data).reshaped([config.sx, config.sy, config.channels])
    }

    public func buildStateFromPatch(_ patchValues: [Float]) -> MLXArray {
        guard let initPatch = esConfig.initPatch else {
            return buildInitialState(seed: runtimeConfig.initSeed)
        }

        var data = [Float](repeating: 0.0, count: config.sx * config.sy * config.channels)
        let size = initPatch.size
        let cx = initPatch.center[0]
        let cy = initPatch.center[1]
        let half = size / 2

        var patchIdx = 0
        for x in (cx - half)..<(cx + size - half) {
            for y in (cy - half)..<(cy + size - half) {
                for c in creatureChannels {
                    let idx = (x * config.sy + y) * config.channels + c
                    if idx >= 0 && idx < data.count && patchIdx < patchValues.count {
                        data[idx] = patchValues[patchIdx]
                    }
                    patchIdx += 1
                }
            }
        }

        return MLXArray(data).reshaped([config.sx, config.sy, config.channels])
    }

    private func buildStateForCandidate(_ candidate: [Float]) -> MLXArray {
        if initPatchDim == 0 {
            return buildInitialState(seed: runtimeConfig.initSeed)
        }
        let patchVec = Array(candidate[thetaParamsDim...])
        let patchValues = patchVec.map { val -> Float in
            guard let initPatch = esConfig.initPatch else { return 0 }
            let sig = sigmoid(val)
            return initPatch.valueLow + sig * (initPatch.valueHigh - initPatch.valueLow)
        }
        return buildStateFromPatch(patchValues)
    }

    private func buildStateBatch(_ candidates: [[Float]]) -> MLXArray {
        MLX.stacked(candidates.map(buildStateForCandidate))
    }

    private func buildChemotaxisFieldBatch(startIndex: Int, count: Int) -> MLXArray? {
        guard let chemotaxis = runtimeConfig.chemotaxis, chemotaxis.enabled else {
            return nil
        }
        var fields: [MLXArray] = []
        fields.reserveCapacity(count)
        for offset in 0..<count {
            let dynamicSeed = (chemotaxis.seed ?? 0) + startIndex + offset
            fields.append(buildChemotaxisField(
                sx: config.sx,
                sy: config.sy,
                config: chemotaxis,
                evalSeed: dynamicSeed
            ))
        }
        return MLX.stacked(fields)
    }

    private func buildObstacleFieldBatch(startIndex: Int, count: Int) -> MLXArray? {
        guard let obstacleField = esConfig.obstacleField, obstacleField.enabled else {
            return nil
        }
        var fields: [MLXArray] = []
        fields.reserveCapacity(count)
        for offset in 0..<count {
            fields.append(buildObstacleField(
                sx: config.sx,
                sy: config.sy,
                config: obstacleField,
                evalSeed: obstacleField.seed + startIndex + offset
            ))
        }
        return MLX.stacked(fields)
    }

    private func buildConstantParameterFieldBatch(_ parameterValuesBatch: [[Float]]) -> MLXArray {
        guard let parameterCount = parameterValuesBatch.first?.count else {
            preconditionFailure("EvolutionEngine requires at least one parameter vector to build a batched field.")
        }
        guard parameterValuesBatch.allSatisfy({ $0.count == parameterCount }) else {
            preconditionFailure("EvolutionEngine batched parameter fields require a consistent kernel count per candidate.")
        }
        let flatValues = parameterValuesBatch.flatMap { $0 }
        let template = MLXArray(flatValues).reshaped([parameterValuesBatch.count, 1, 1, parameterCount])
        return MLX.broadcast(template, to: [parameterValuesBatch.count, config.sx, config.sy, parameterCount])
    }

    private struct BatchCenterOfMassDevice {
        let total: MLXArray
        let x: MLXArray
        let y: MLXArray
    }

    private struct BatchCenterOfMassCPU {
        let alive: [Float]
        let x: [Float]
        let y: [Float]
    }

    private func centerOfMassBatchDevice(_ ABatch: MLXArray) -> BatchCenterOfMassDevice {
        let signpost = LeniaSignposts.beginPhase("centerOfMassBatch")
        defer { LeniaSignposts.end(signpost) }
        let massMap = evolutionMassMapBatch(ABatch, excludedChannels: excludedMassChannels)
        return centerOfMassBatchDeviceFromMassMap(massMap)
    }

    private func centerOfMassBatchDeviceFromMassMap(_ massMap: MLXArray) -> BatchCenterOfMassDevice {
        let totalArr = massMap.sum(axes: [1, 2])
        let totalSafe = MLX.maximum(totalArr, MLXArray(Float(1e-6)))
        let comXArr = (massMap * metricGridX).sum(axes: [1, 2]) / totalSafe
        let comYArr = (massMap * metricGridY).sum(axes: [1, 2]) / totalSafe
        return BatchCenterOfMassDevice(total: totalArr, x: comXArr, y: comYArr)
    }

    private func materializeCenterOfMassBatch(_ metrics: [BatchCenterOfMassDevice]) -> [BatchCenterOfMassCPU] {
        guard !metrics.isEmpty else { return [] }
        let evalSignpost = LeniaSignposts.beginPhase("centerOfMassBatchEval")
        var arrays: [MLXArray] = []
        arrays.reserveCapacity(metrics.count * 3)
        for metric in metrics {
            arrays.append(metric.total)
            arrays.append(metric.x)
            arrays.append(metric.y)
        }
        eval(arrays)
        LeniaSignposts.end(evalSignpost)
        return metrics.map { metric in
            let totalCPU: [Float] = metric.total.asArray(Float.self)
            let rawXCPU: [Float] = metric.x.asArray(Float.self)
            let rawYCPU: [Float] = metric.y.asArray(Float.self)
            let aliveCPU = totalCPU.map { $0 > 0 ? Float(1.0) : Float(0.0) }
            let xCPU = rawXCPU.map { $0 / Float(config.sx) - 0.5 }
            let yCPU = rawYCPU.map { $0 / Float(config.sy) - 0.5 }
            return BatchCenterOfMassCPU(alive: aliveCPU, x: xCPU, y: yCPU)
        }
    }

    private func objectiveRequirements() -> (
        objective: String,
        usesCenterOfMass: Bool,
        usesMidCenter: Bool,
        targetStep: Int,
        midStep: Int
    ) {
        let objective = esConfig.fitness.objective
        let usesCenterOfMass = objective == "directed_motion" ||
            objective == "obstacle_navigation" ||
            objective == "angular_motion" ||
            objectiveUsesTranslatedShapeOverlap(objective)
        let targetStep = esConfig.fitness.targetStep
        return (
            objective,
            usesCenterOfMass,
            objective == "angular_motion" || objectiveUsesTranslatedShapeOverlap(objective),
            targetStep,
            targetStep / 2
        )
    }

    private func templateSequenceSteps() -> [Int] {
        guard esConfig.fitness.usesTemplateSequence ||
            esConfig.fitness.usesTrajectoryMetrics ||
            esConfig.fitness.usesOrientationPhaseMotion ||
            esConfig.fitness.usesAngularPhaseMotion ||
            esConfig.fitness.usesSectorTransport else {
            return []
        }
        let steps = esConfig.fitness.templateSequenceSteps ?? [esConfig.fitness.targetStep]
        return Array(Set(steps)).sorted()
    }

    private func trajectoryMetricValues(from centers: [BatchCenterOfMassCPU], stepSpan: Float) -> (
        pathLength: [Float]?,
        displacement: [Float]?,
        movementEfficiency: [Float]?,
        centerVelocity: [Float]?
    ) {
        guard esConfig.fitness.usesTrajectoryMetrics else {
            return (nil, nil, nil, nil)
        }
        guard centers.count >= 2, let count = centers.first?.alive.count else {
            return (nil, nil, nil, nil)
        }
        var pathLengths = [Float](repeating: 0, count: count)
        var displacements = [Float](repeating: 0, count: count)
        var movementEfficiencies = [Float](repeating: 0, count: count)
        var centerVelocities = [Float](repeating: 0, count: count)
        for stepIndex in 1..<centers.count {
            let previous = centers[stepIndex - 1]
            let current = centers[stepIndex]
            for index in 0..<count where previous.alive[index] > 0 && current.alive[index] > 0 {
                let dx = current.x[index] - previous.x[index]
                let dy = current.y[index] - previous.y[index]
                let speed = sqrt(dx * dx + dy * dy)
                pathLengths[index] += speed
            }
        }
        let first = centers[0]
        let last = centers[centers.count - 1]
        for index in 0..<count where first.alive[index] > 0 && last.alive[index] > 0 {
            let dx = last.x[index] - first.x[index]
            let dy = last.y[index] - first.y[index]
            let displacement = sqrt(dx * dx + dy * dy)
            displacements[index] = displacement
            movementEfficiencies[index] = movementEfficiency(pathLength: pathLengths[index], displacement: displacement)
            centerVelocities[index] = displacement / max(stepSpan, 1)
        }
        return (pathLengths, displacements, movementEfficiencies, centerVelocities)
    }

    private func trajectoryMetricValues(from snapshots: [[CenterSnapshot]], stepSpan: Float) -> (
        pathLength: [Float]?,
        displacement: [Float]?,
        movementEfficiency: [Float]?,
        centerVelocity: [Float]?
    ) {
        guard esConfig.fitness.usesTrajectoryMetrics else {
            return (nil, nil, nil, nil)
        }
        guard snapshots.count >= 2, let count = snapshots.first?.count else {
            return (nil, nil, nil, nil)
        }
        var pathLengths = [Float](repeating: 0, count: count)
        var displacements = [Float](repeating: 0, count: count)
        var movementEfficiencies = [Float](repeating: 0, count: count)
        var centerVelocities = [Float](repeating: 0, count: count)
        for stepIndex in 1..<snapshots.count {
            let previous = snapshots[stepIndex - 1]
            let current = snapshots[stepIndex]
            for index in 0..<count where previous[index].alive && current[index].alive {
                let dx = current[index].x - previous[index].x
                let dy = current[index].y - previous[index].y
                let speed = sqrt(dx * dx + dy * dy)
                pathLengths[index] += speed
            }
        }
        let first = snapshots[0]
        let last = snapshots[snapshots.count - 1]
        for index in 0..<count where first[index].alive && last[index].alive {
            let dx = last[index].x - first[index].x
            let dy = last[index].y - first[index].y
            let displacement = sqrt(dx * dx + dy * dy)
            displacements[index] = displacement
            movementEfficiencies[index] = movementEfficiency(pathLength: pathLengths[index], displacement: displacement)
            centerVelocities[index] = displacement / max(stepSpan, 1)
        }
        return (pathLengths, displacements, movementEfficiencies, centerVelocities)
    }

    private func trajectoryMetricStepSpan() -> Float {
        let steps = templateSequenceSteps()
        guard let first = steps.first, let last = steps.last, last > first else {
            return Float(max(1, steps.count - 1))
        }
        return Float(last - first)
    }

    private func templateSequenceMetricValues(from massMaps: [MLXArray]) -> (
        similarity: [Float]?,
        massMismatch: [Float]?,
        supportMismatch: [Float]?,
        changeMismatch: [Float]?,
        deltaSimilarity: [Float]?,
        signedDeltaSimilarity: [Float]?
    ) {
        guard esConfig.fitness.usesTemplateSequence else {
            return (nil, nil, nil, nil, nil, nil)
        }
        guard !massMaps.isEmpty else {
            fatalError("template_sequence metrics requested but no sequence frames were captured.")
        }
        let templates: [MassTemplate]
        if let templateSequenceTemplates {
            templates = templateSequenceTemplates
        } else if let morphologyTemplate {
            templates = Array(repeating: morphologyTemplate, count: massMaps.count)
        } else {
            fatalError("template_sequence metrics require init.state_patch or template_sequence_state_patches.")
        }
        guard templates.count == massMaps.count else {
            fatalError("template_sequence_state_patches count must match captured sequence frames.")
        }
        let threshold = esConfig.fitness.morphologyThreshold ?? 0.03
        let materializedMaps = massMaps.map { materializeMassBatch($0) }
        var similarityTotals: [Float]?
        var mismatchTotals: [Float]?
        var supportMismatchTotals: [Float]?
        var changeMismatchTotals: [Float]?
        var deltaSimilarityTotals: [Float]?
        var signedDeltaSimilarityTotals: [Float]?
        for (materialized, template) in zip(materializedMaps, templates) {
            if esConfig.fitness.templateSequenceReward != nil {
                let values = computeTemplateSimilarityBatch(
                    materialized: materialized,
                    template: template,
                    threshold: threshold,
                    useTorus: runtimeConfig.border == "torus"
                )
                if similarityTotals == nil {
                    similarityTotals = Array(repeating: 0, count: values.count)
                }
                for index in values.indices {
                    similarityTotals![index] += values[index]
                }
            }
            if esConfig.fitness.templateSequenceMassPenalty != nil {
                let values = computeTemplateMassMismatchBatch(
                    materialized: materialized,
                    template: template,
                    threshold: threshold
                )
                if mismatchTotals == nil {
                    mismatchTotals = Array(repeating: 0, count: values.count)
                }
                for index in values.indices {
                    mismatchTotals![index] += values[index]
                }
            }
            if esConfig.fitness.templateSequenceSupportPenalty != nil {
                let values = computeTemplateSupportMismatchBatch(
                    materialized: materialized,
                    template: template,
                    threshold: threshold
                )
                if supportMismatchTotals == nil {
                    supportMismatchTotals = Array(repeating: 0, count: values.count)
                }
                for index in values.indices {
                    supportMismatchTotals![index] += values[index]
                }
            }
        }
        if esConfig.fitness.templateSequenceChangePenalty != nil ||
            esConfig.fitness.templateSequenceDeltaReward != nil ||
            esConfig.fitness.templateSequenceSignedDeltaReward != nil {
            guard materializedMaps.count >= 2 else {
                fatalError("temporal template_sequence metrics require at least two captured sequence frames.")
            }
            for index in 1..<materializedMaps.count {
                if esConfig.fitness.templateSequenceChangePenalty != nil {
                    let values = computeTemplateChangeMismatchBatch(
                        previous: materializedMaps[index - 1],
                        current: materializedMaps[index],
                        previousTemplate: templates[index - 1],
                        currentTemplate: templates[index],
                        threshold: threshold
                    )
                    if changeMismatchTotals == nil {
                        changeMismatchTotals = Array(repeating: 0, count: values.count)
                    }
                    for index in values.indices {
                        changeMismatchTotals![index] += values[index]
                    }
                }
                if esConfig.fitness.templateSequenceDeltaReward != nil {
                    let values = computeTemplateDeltaSimilarityBatch(
                        previous: materializedMaps[index - 1],
                        current: materializedMaps[index],
                        previousTemplate: templates[index - 1],
                        currentTemplate: templates[index],
                        threshold: threshold,
                        useTorus: runtimeConfig.border == "torus"
                    )
                    if deltaSimilarityTotals == nil {
                        deltaSimilarityTotals = Array(repeating: 0, count: values.count)
                    }
                    for index in values.indices {
                        deltaSimilarityTotals![index] += values[index]
                    }
                }
                if esConfig.fitness.templateSequenceSignedDeltaReward != nil {
                    let values = computeTemplateSignedDeltaSimilarityBatch(
                        previous: materializedMaps[index - 1],
                        current: materializedMaps[index],
                        previousTemplate: templates[index - 1],
                        currentTemplate: templates[index],
                        threshold: threshold,
                        useTorus: runtimeConfig.border == "torus"
                    )
                    if signedDeltaSimilarityTotals == nil {
                        signedDeltaSimilarityTotals = Array(repeating: 0, count: values.count)
                    }
                    for index in values.indices {
                        signedDeltaSimilarityTotals![index] += values[index]
                    }
                }
            }
        }
        let divisor = Float(massMaps.count)
        let changeDivisor = Float(max(1, massMaps.count - 1))
        return (
            similarityTotals?.map { $0 / divisor },
            mismatchTotals?.map { $0 / divisor },
            supportMismatchTotals?.map { $0 / divisor },
            changeMismatchTotals?.map { $0 / changeDivisor },
            deltaSimilarityTotals?.map { $0 / changeDivisor },
            signedDeltaSimilarityTotals?.map { $0 / changeDivisor }
        )
    }

    private func orientationPhaseMotionValues(from massMaps: [MLXArray]) -> [Float]? {
        guard esConfig.fitness.usesOrientationPhaseMotion else {
            return nil
        }
        guard massMaps.count >= 2 else {
            fatalError("orientation_phase_motion metrics require at least two captured sequence frames.")
        }
        let materializedMaps = massMaps.map { materializeMassBatch($0) }
        return computeOrientationPhaseMotionBatch(
            materialized: materializedMaps,
            threshold: esConfig.fitness.morphologyThreshold ?? 0.03
        )
    }

    private func angularPhaseMotionValues(from massMaps: [MLXArray]) -> [Float]? {
        guard esConfig.fitness.usesAngularPhaseMotion else {
            return nil
        }
        guard massMaps.count >= 2 else {
            fatalError("angular_phase_motion metrics require at least two captured sequence frames.")
        }
        let materializedMaps = massMaps.map { materializeMassBatch($0) }
        return computeAngularPhaseMotionBatch(
            materialized: materializedMaps,
            threshold: esConfig.fitness.morphologyThreshold ?? 0.03,
            order: esConfig.fitness.angularPhaseMotionOrder ?? 8,
            minimumAmplitude: esConfig.fitness.angularPhaseMotionMinimumAmplitude ?? 0.02
        )
    }

    private func sectorTransportValues(from massMaps: [MLXArray]) -> [Float]? {
        guard esConfig.fitness.usesSectorTransport else {
            return nil
        }
        guard massMaps.count >= 2 else {
            fatalError("sector_transport metrics require at least two captured sequence frames.")
        }
        let materializedMaps = massMaps.map { materializeMassBatch($0) }
        return computeSectorTransportMotionBatch(
            materialized: materializedMaps,
            threshold: esConfig.fitness.morphologyThreshold ?? 0.03,
            binCount: esConfig.fitness.sectorTransportBinCount ?? 48,
            minimumContrast: esConfig.fitness.sectorTransportMinimumContrast ?? 0.05
        )
    }

    private func objectiveUsesTranslatedShapeOverlap(_ objective: String) -> Bool {
        objective == "coherent_transport" || objective == "body_locomotion"
    }

    private func deadSnapshot() -> CenterSnapshot {
        CenterSnapshot(alive: false, x: 0.0, y: 0.0)
    }

    private func centerSnapshot(from metrics: BatchCenterOfMassCPU?, index: Int) -> CenterSnapshot? {
        guard let metrics else { return nil }
        return CenterSnapshot(
            alive: metrics.alive[index] > 0.0,
            x: metrics.x[index],
            y: metrics.y[index]
        )
    }

    private func centerSnapshotForSingleBatch(_ ABatch: MLXArray) -> CenterSnapshot {
        let metrics = materializeCenterOfMassBatch([centerOfMassBatchDevice(ABatch)])[0]
        return CenterSnapshot(
            alive: metrics.alive[0] > 0.0,
            x: metrics.x[0],
            y: metrics.y[0]
        )
    }

    private func centerSnapshot(
        centerXHistory: [Float],
        centerYHistory: [Float],
        aliveHistory: [Bool],
        index: Int
    ) -> CenterSnapshot {
        let clampedIndex = min(max(index, 0), centerXHistory.count - 1)
        return CenterSnapshot(
            alive: aliveHistory[clampedIndex],
            x: centerXHistory[clampedIndex],
            y: centerYHistory[clampedIndex]
        )
    }

    private func centerSnapshot(from summary: FlowLeniaMetalMassSummary, index: Int) -> CenterSnapshot {
        let total = summary.totalMass[index]
        guard total > 0 else {
            return deadSnapshot()
        }
        return CenterSnapshot(
            alive: true,
            x: summary.centerXIndex[index] / Float(config.sx) - 0.5,
            y: summary.centerYIndex[index] / Float(config.sy) - 0.5
        )
    }

    private func translatedShapeOverlapBatch(
        source: MassBatchCPU,
        target: MassBatchCPU,
        sourceCenters: BatchCenterOfMassCPU,
        targetCenters: BatchCenterOfMassCPU,
        threshold: Float,
        useTorus: Bool
    ) -> [Float] {
        guard source.batch == target.batch,
              source.height == target.height,
              source.width == target.width else {
            fatalError("translated shape overlap requires matching source and target mass batches.")
        }
        guard sourceCenters.alive.count == source.batch,
              sourceCenters.x.count == source.batch,
              sourceCenters.y.count == source.batch,
              targetCenters.alive.count == target.batch,
              targetCenters.x.count == target.batch,
              targetCenters.y.count == target.batch else {
            fatalError("translated shape overlap center batch size mismatch.")
        }

        return (0..<source.batch).map { sampleIndex in
            guard sourceCenters.alive[sampleIndex] > 0.0,
                  targetCenters.alive[sampleIndex] > 0.0 else {
                return 0.0
            }
            let rowShift = Int(((targetCenters.x[sampleIndex] - sourceCenters.x[sampleIndex]) * Float(source.height)).rounded())
            let colShift = Int(((targetCenters.y[sampleIndex] - sourceCenters.y[sampleIndex]) * Float(source.width)).rounded())
            return translatedMaskOverlap(
                source: source,
                target: target,
                sampleIndex: sampleIndex,
                rowShift: rowShift,
                colShift: colShift,
                threshold: threshold,
                useTorus: useTorus
            )
        }
    }

    private func occupiedFractionBatch(
        materialized batch: MassBatchCPU,
        threshold: Float
    ) -> [Float] {
        (0..<batch.batch).map { sampleIndex in
            let start = sampleIndex * batch.sampleSize
            var occupied = 0
            for index in 0..<batch.sampleSize where batch.flat[start + index] > threshold {
                occupied += 1
            }
            return Float(occupied) / Float(max(batch.sampleSize, 1))
        }
    }

    private func occupiedGrowth(mid: Float?, target: Float?) -> Float? {
        guard let mid, let target else { return nil }
        guard target > 0 else { return 0.0 }
        return target / max(mid, 1e-6)
    }

    private func translatedMaskOverlap(
        source: MassBatchCPU,
        target: MassBatchCPU,
        sampleIndex: Int,
        rowShift: Int,
        colShift: Int,
        threshold: Float,
        useTorus: Bool
    ) -> Float {
        let sourceStart = sampleIndex * source.sampleSize
        let targetStart = sampleIndex * target.sampleSize
        var targetCount = 0
        for index in 0..<target.sampleSize where target.flat[targetStart + index] > threshold {
            targetCount += 1
        }
        guard targetCount > 0 else { return 0.0 }

        var best: Float = 0.0
        let localSearchRadius = 2
        for rowDelta in (-localSearchRadius)...localSearchRadius {
            for colDelta in (-localSearchRadius)...localSearchRadius {
                var shiftedCount = 0
                var intersection = 0
                for row in 0..<source.height {
                    for col in 0..<source.width {
                        let sourceIndex = sourceStart + row * source.width + col
                        guard source.flat[sourceIndex] > threshold else { continue }

                        var targetRow = row + rowShift + rowDelta
                        var targetCol = col + colShift + colDelta
                        if useTorus {
                            targetRow = (targetRow % target.height + target.height) % target.height
                            targetCol = (targetCol % target.width + target.width) % target.width
                        } else if targetRow < 0 || targetCol < 0 || targetRow >= target.height || targetCol >= target.width {
                            continue
                        }

                        shiftedCount += 1
                        let targetIndex = targetStart + targetRow * target.width + targetCol
                        if target.flat[targetIndex] > threshold {
                            intersection += 1
                        }
                    }
                }
                let union = shiftedCount + targetCount - intersection
                if union > 0 {
                    best = max(best, Float(intersection) / Float(union))
                }
            }
        }
        return best
    }

    private func evaluatePopulation(
        candidates: [[Float]],
        paramsBatch: [ResolvedParams],
        evaluationStart: Int
    ) -> PopulationEvaluation {
        switch populationEvaluator {
        case .mlx:
            return evaluatePopulationMLX(
                candidates: candidates,
                paramsBatch: paramsBatch,
                evaluationStart: evaluationStart
            )
        case .metalFull:
            return evaluatePopulationMetal(
                candidates: candidates,
                paramsBatch: paramsBatch,
                evaluationStart: evaluationStart
            )
        }
    }

    private func evaluatePopulationMLX(
        candidates: [[Float]],
        paramsBatch: [ResolvedParams],
        evaluationStart: Int
    ) -> PopulationEvaluation {
        let pop = candidates.count
        let requirements = objectiveRequirements()

        let kernelCompileStart = ContinuousClock.now
        let kernelCompileSignpost = LeniaSignposts.beginPhase("kernelCompile")
        populationSim.kernels = compilePopulationKernels(
            paramsBatch: paramsBatch,
            config: config,
            c0: runtimeConfig.c0,
            c1: runtimeConfig.c1
        )
        LeniaSignposts.end(kernelCompileSignpost)
        let kernelCompileMs = durationMs(kernelCompileStart.duration(to: ContinuousClock.now))

        let stateBuildStart = ContinuousClock.now
        let stateBuildSignpost = LeniaSignposts.beginPhase("stateBuild")
        var ABatch = buildStateBatch(candidates)
        LeniaSignposts.end(stateBuildSignpost)
        let stateBuildMs = durationMs(stateBuildStart.duration(to: ContinuousClock.now))

        let fieldBuildStart = ContinuousClock.now
        let fieldBuildSignpost = LeniaSignposts.beginPhase("fieldBuild")
        let chemFieldBatch = buildChemotaxisFieldBatch(startIndex: evaluationStart, count: pop)
        let obstacleFieldBatch = buildObstacleFieldBatch(startIndex: evaluationStart, count: pop)
        populationSim.wallPotential = obstacleFieldBatch.map(buildObstaclePotential)

        if let field = chemFieldBatch, let chemotaxis = runtimeConfig.chemotaxis {
            ABatch = applyExternalFieldBatch(ABatch, field: field, channelIndex: chemotaxis.channel_index)
        }
        if let field = obstacleFieldBatch, let obstacleConfig = esConfig.obstacleField {
            ABatch = applyExternalFieldBatch(ABatch, field: field, channelIndex: obstacleConfig.channelIndex)
        }
        LeniaSignposts.end(fieldBuildSignpost)
        let fieldBuildMs = durationMs(fieldBuildStart.duration(to: ContinuousClock.now))

        let rolloutStart = ContinuousClock.now
        let rolloutSignpost = LeniaSignposts.beginPhase("rollout")
        let com0Device = requirements.usesCenterOfMass ? centerOfMassBatchDevice(ABatch) : nil
        var comMidDevice: BatchCenterOfMassDevice? = nil
        var comTargetDevice: BatchCenterOfMassDevice? = nil
        let sequenceStepSet = Set(templateSequenceSteps())
        var sequenceMassMaps: [MLXArray] = []
        var sequenceCenterDevices: [BatchCenterOfMassDevice] = []

        func captureTemplateSequenceStep(_ step: Int) {
            if sequenceStepSet.contains(step) {
                sequenceMassMaps.append(evolutionMassMapBatch(ABatch, excludedChannels: excludedMassChannels))
                if esConfig.fitness.usesTrajectoryMetrics {
                    sequenceCenterDevices.append(centerOfMassBatchDevice(ABatch))
                }
            }
        }

        captureTemplateSequenceStep(0)
        let usesTranslatedShapeOverlap = objectiveUsesTranslatedShapeOverlap(requirements.objective)
        var midMassMapDevice: MLXArray? = nil
        var targetMassMapDevice: MLXArray? = nil

        for step in 1...esConfig.steps {
            if let field = chemFieldBatch, let chemotaxis = runtimeConfig.chemotaxis {
                ABatch = applyExternalFieldBatch(ABatch, field: field, channelIndex: chemotaxis.channel_index)
            }
            if let field = obstacleFieldBatch, let obstacleConfig = esConfig.obstacleField {
                ABatch = applyExternalFieldBatch(ABatch, field: field, channelIndex: obstacleConfig.channelIndex)
            }
            ABatch = populationSim.step(ABatch)

            if requirements.usesMidCenter && step == requirements.midStep {
                comMidDevice = centerOfMassBatchDevice(ABatch)
                if usesTranslatedShapeOverlap {
                    midMassMapDevice = evolutionMassMapBatch(ABatch, excludedChannels: excludedMassChannels)
                }
            }
            if requirements.usesCenterOfMass && step == requirements.targetStep {
                comTargetDevice = centerOfMassBatchDevice(ABatch)
                if usesTranslatedShapeOverlap {
                    targetMassMapDevice = evolutionMassMapBatch(ABatch, excludedChannels: excludedMassChannels)
                }
            }
            captureTemplateSequenceStep(step)
        }

        LeniaSignposts.end(rolloutSignpost)
        let rolloutMs = durationMs(rolloutStart.duration(to: ContinuousClock.now))

        let measurementStart = ContinuousClock.now
        let measurementSignpost = LeniaSignposts.beginPhase("measurement")
        let centerMetrics: [BatchCenterOfMassCPU]
        if requirements.usesMidCenter, let com0Device, let comMidDevice, let comTargetDevice {
            centerMetrics = materializeCenterOfMassBatch([com0Device, comMidDevice, comTargetDevice])
        } else if requirements.usesCenterOfMass, let com0Device, let comTargetDevice {
            centerMetrics = materializeCenterOfMassBatch([com0Device, comTargetDevice])
        } else {
            centerMetrics = []
        }

        let initialCenters = requirements.usesCenterOfMass ? centerMetrics[0] : nil
        let midCenters = requirements.usesMidCenter ? centerMetrics[1] : nil
        let targetCenters = requirements.usesMidCenter ? centerMetrics[2] : (requirements.usesCenterOfMass ? centerMetrics[1] : nil)
        let trajectoryValues = trajectoryMetricValues(
            from: materializeCenterOfMassBatch(sequenceCenterDevices),
            stepSpan: trajectoryMetricStepSpan()
        )

        let gyrationValues = esConfig.fitness.gyrationPenalty == nil ? nil : computeGyrationBatch(ABatch)
        let morphologyValues = morphologyMeasurements(from: ABatch)
        let templateSequenceValues = templateSequenceMetricValues(from: sequenceMassMaps)
        let orientationPhaseMotion = orientationPhaseMotionValues(from: sequenceMassMaps)
        let angularPhaseMotion = angularPhaseMotionValues(from: sequenceMassMaps)
        let sectorTransport = sectorTransportValues(from: sequenceMassMaps)
        let midMassBatchCPU = midMassMapDevice.map(materializeMassBatch)
        let targetMassBatchCPU = targetMassMapDevice.map(materializeMassBatch)
        let midOccupiedFractionValues = midMassBatchCPU.map {
            occupiedFractionBatch(materialized: $0, threshold: esConfig.fitness.morphologyThreshold ?? 0.03)
        }
        let targetOccupiedFractionValues = targetMassBatchCPU.map {
            occupiedFractionBatch(materialized: $0, threshold: esConfig.fitness.morphologyThreshold ?? 0.03)
        }
        let translatedShapeOverlapValues: [Float]?
        if usesTranslatedShapeOverlap,
           let midMassBatchCPU,
           let targetMassBatchCPU,
           let midCenters,
           let targetCenters {
            translatedShapeOverlapValues = translatedShapeOverlapBatch(
                source: midMassBatchCPU,
                target: targetMassBatchCPU,
                sourceCenters: midCenters,
                targetCenters: targetCenters,
                threshold: esConfig.fitness.morphologyThreshold ?? 0.03,
                useTorus: runtimeConfig.border == "torus"
            )
        } else {
            translatedShapeOverlapValues = nil
        }
        let chemotaxisScores: [Float]?
        if requirements.objective == "chemotaxis" {
            guard let field = chemFieldBatch else {
                chemotaxisScores = Array(repeating: 0.0, count: pop)
                LeniaSignposts.end(measurementSignpost)
                let measurementMs = durationMs(measurementStart.duration(to: ContinuousClock.now))
                let measurements = (0..<pop).map { index in
                    CandidateMeasurement(
                        initial: deadSnapshot(),
                        mid: nil,
                        target: nil,
                        translatedShapeOverlap: nil,
                        midOccupiedFraction: nil,
                        targetOccupiedFraction: nil,
                        occupiedGrowth: nil,
                        gyration: nil,
                        componentCount: morphologyValues?.componentCount?[index],
                        largestComponentFraction: morphologyValues?.largestComponentFraction?[index],
                        largestComponentAnisotropy: morphologyValues?.largestComponentAnisotropy?[index],
                        componentMassEvenness: morphologyValues?.componentMassEvenness?[index],
                        momentMass: morphologyValues?.momentMass?[index],
                        largestComponentSolidity: morphologyValues?.largestComponentSolidity?[index],
                        largestComponentMeanThickness: morphologyValues?.largestComponentMeanThickness?[index],
                        largestComponentMaxThickness: morphologyValues?.largestComponentMaxThickness?[index],
                        largestComponentFilamentarity: morphologyValues?.largestComponentFilamentarity?[index],
                        momentDensity: morphologyValues?.momentDensity?[index],
                        occupiedFraction: morphologyValues?.occupiedFraction?[index],
                        momentAnisotropy: morphologyValues?.momentAnisotropy?[index],
                        internalStripe: morphologyValues?.internalStripe?[index],
                        orientedRidge: morphologyValues?.orientedRidge?[index],
                        largestComponentInternalStripe: morphologyValues?.largestComponentInternalStripe?[index],
                        largestComponentOrientedRidge: morphologyValues?.largestComponentOrientedRidge?[index],
                        templateSimilarity: morphologyValues?.templateSimilarity?[index],
                        templateSequenceSimilarity: templateSequenceValues.similarity?[index],
                        templateSequenceMassMismatch: templateSequenceValues.massMismatch?[index],
                        templateSequenceSupportMismatch: templateSequenceValues.supportMismatch?[index],
                        templateSequenceChangeMismatch: templateSequenceValues.changeMismatch?[index],
                        templateSequenceDeltaSimilarity: templateSequenceValues.deltaSimilarity?[index],
                        templateSequenceSignedDeltaSimilarity: templateSequenceValues.signedDeltaSimilarity?[index],
                        orientationPhaseMotion: orientationPhaseMotion?[index],
                        angularPhaseMotion: angularPhaseMotion?[index],
                        sectorTransport: sectorTransport?[index],
                        trajectoryPathLength: nil,
                        trajectoryDisplacement: nil,
                        movementEfficiency: nil,
                        centerVelocity: nil,
                        chemotaxisScore: 0.0
                    )
                }
                return PopulationEvaluation(
                    measurements: measurements,
                    kernelCompileMs: kernelCompileMs,
                    stateBuildMs: stateBuildMs,
                    fieldBuildMs: fieldBuildMs,
                    rolloutMs: rolloutMs,
                    measurementMs: measurementMs
                )
            }
            let massMap = evolutionMassMapBatch(ABatch, excludedChannels: excludedMassChannels)
            let numerator = (massMap * field).sum(axes: [1, 2])
            let denominator = massMap.sum(axes: [1, 2])
            eval(numerator, denominator)
            let numeratorCPU: [Float] = numerator.asArray(Float.self)
            let denominatorCPU: [Float] = denominator.asArray(Float.self)
            chemotaxisScores = zip(numeratorCPU, denominatorCPU).map { numerator, denominator in
                numerator / max(denominator, 1e-6)
            }
        } else {
            chemotaxisScores = nil
        }

        let measurements = (0..<pop).map { index in
            CandidateMeasurement(
                initial: centerSnapshot(from: initialCenters, index: index) ?? deadSnapshot(),
                mid: centerSnapshot(from: midCenters, index: index),
                target: centerSnapshot(from: targetCenters, index: index),
                translatedShapeOverlap: translatedShapeOverlapValues?[index],
                midOccupiedFraction: midOccupiedFractionValues?[index],
                targetOccupiedFraction: targetOccupiedFractionValues?[index],
                occupiedGrowth: occupiedGrowth(
                    mid: midOccupiedFractionValues?[index],
                    target: targetOccupiedFractionValues?[index]
                ),
                gyration: gyrationValues?[index],
                componentCount: morphologyValues?.componentCount?[index],
                largestComponentFraction: morphologyValues?.largestComponentFraction?[index],
                largestComponentAnisotropy: morphologyValues?.largestComponentAnisotropy?[index],
                componentMassEvenness: morphologyValues?.componentMassEvenness?[index],
                momentMass: morphologyValues?.momentMass?[index],
                largestComponentSolidity: morphologyValues?.largestComponentSolidity?[index],
                largestComponentMeanThickness: morphologyValues?.largestComponentMeanThickness?[index],
                largestComponentMaxThickness: morphologyValues?.largestComponentMaxThickness?[index],
                largestComponentFilamentarity: morphologyValues?.largestComponentFilamentarity?[index],
                momentDensity: morphologyValues?.momentDensity?[index],
                occupiedFraction: morphologyValues?.occupiedFraction?[index],
                momentAnisotropy: morphologyValues?.momentAnisotropy?[index],
                internalStripe: morphologyValues?.internalStripe?[index],
                orientedRidge: morphologyValues?.orientedRidge?[index],
                largestComponentInternalStripe: morphologyValues?.largestComponentInternalStripe?[index],
                largestComponentOrientedRidge: morphologyValues?.largestComponentOrientedRidge?[index],
                templateSimilarity: morphologyValues?.templateSimilarity?[index],
                templateSequenceSimilarity: templateSequenceValues.similarity?[index],
                templateSequenceMassMismatch: templateSequenceValues.massMismatch?[index],
                templateSequenceSupportMismatch: templateSequenceValues.supportMismatch?[index],
                templateSequenceChangeMismatch: templateSequenceValues.changeMismatch?[index],
                templateSequenceDeltaSimilarity: templateSequenceValues.deltaSimilarity?[index],
                templateSequenceSignedDeltaSimilarity: templateSequenceValues.signedDeltaSimilarity?[index],
                orientationPhaseMotion: orientationPhaseMotion?[index],
                angularPhaseMotion: angularPhaseMotion?[index],
                sectorTransport: sectorTransport?[index],
                trajectoryPathLength: trajectoryValues.pathLength?[index],
                trajectoryDisplacement: trajectoryValues.displacement?[index],
                movementEfficiency: trajectoryValues.movementEfficiency?[index],
                centerVelocity: trajectoryValues.centerVelocity?[index],
                chemotaxisScore: chemotaxisScores?[index]
            )
        }
        LeniaSignposts.end(measurementSignpost)
        let measurementMs = durationMs(measurementStart.duration(to: ContinuousClock.now))

        return PopulationEvaluation(
            measurements: measurements,
            kernelCompileMs: kernelCompileMs,
            stateBuildMs: stateBuildMs,
            fieldBuildMs: fieldBuildMs,
            rolloutMs: rolloutMs,
            measurementMs: measurementMs
        )
    }

    private func evaluatePopulationMetal(
        candidates: [[Float]],
        paramsBatch: [ResolvedParams],
        evaluationStart: Int
    ) -> PopulationEvaluation {
        let pop = candidates.count
        let requirements = objectiveRequirements()
        var measurements: [CandidateMeasurement] = []
        measurements.reserveCapacity(pop)
        let deadSnapshots = Array(repeating: deadSnapshot(), count: pop)
        var initialSnapshots = deadSnapshots
        var midSnapshots = [CenterSnapshot?](repeating: nil, count: pop)
        var targetSnapshots = [CenterSnapshot?](repeating: nil, count: pop)
        let usesTranslatedShapeOverlap = objectiveUsesTranslatedShapeOverlap(requirements.objective)
        var midMassBatch: MassBatchCPU? = nil
        var targetMassBatch: MassBatchCPU? = nil
        var kernelCompileMs = 0.0
        var stateBuildMs = 0.0
        var fieldBuildMs = 0.0
        var rolloutMs = 0.0
        var measurementMs = 0.0
        _ = evaluationStart
        let kernelCompileStart = ContinuousClock.now
        let kernels = compilePopulationKernels(
            paramsBatch: paramsBatch,
            config: config,
            c0: runtimeConfig.c0,
            c1: runtimeConfig.c1
        )
        let runner = reusableMetalFullPopulationRunner(kernels: kernels)
        kernelCompileMs = durationMs(kernelCompileStart.duration(to: ContinuousClock.now))

        let stateBuildStart = ContinuousClock.now
        var ABatch = buildStateBatch(candidates)
        let PBatch = buildConstantParameterFieldBatch(paramsBatch.map(\.h))
        stateBuildMs = durationMs(stateBuildStart.duration(to: ContinuousClock.now))

        let fieldBuildStart = ContinuousClock.now
        let chemFieldBatch = buildChemotaxisFieldBatch(startIndex: evaluationStart, count: pop)
        let obstacleFieldBatch = buildObstacleFieldBatch(startIndex: evaluationStart, count: pop)
        if let field = chemFieldBatch, let chemotaxis = runtimeConfig.chemotaxis {
            ABatch = applyExternalFieldBatch(ABatch, field: field, channelIndex: chemotaxis.channel_index)
        }
        if let field = obstacleFieldBatch, let obstacleField = esConfig.obstacleField {
            ABatch = applyExternalFieldBatch(ABatch, field: field, channelIndex: obstacleField.channelIndex)
        }
        runner.setMatterWeights(metalMatterWeights())
        runner.setWallPotential(obstacleFieldBatch.map(buildObstaclePotential))
        runner.setStaticChannelFields(
            metalStaticChannelFields(
                chemFieldBatch: chemFieldBatch,
                obstacleFieldBatch: obstacleFieldBatch
            )
        )
        runner.setState(mass: ABatch, params: PBatch)
        fieldBuildMs = durationMs(fieldBuildStart.duration(to: ContinuousClock.now))

        let initialMeasurementStart = ContinuousClock.now
        if requirements.usesCenterOfMass {
            if runner.supportsMassSummary {
                let summary = runner.summarizeMass(
                    occupancyThreshold: 0.0,
                    includeGyration: false,
                    channelWeights: metalMatterWeights()
                )
                initialSnapshots = (0..<pop).map { centerSnapshot(from: summary, index: $0) }
            } else {
                let massMap = runner.materializeMassMap(channelWeights: metalMatterWeights())
                let centers = materializeCenterOfMassBatch([centerOfMassBatchDeviceFromMassMap(massMap)])[0]
                initialSnapshots = (0..<pop).map { centerSnapshot(from: centers, index: $0) ?? deadSnapshot() }
            }
        }
        measurementMs += durationMs(initialMeasurementStart.duration(to: ContinuousClock.now))

        let rolloutStart = ContinuousClock.now
        var completedSteps = 0

        func advanceRunner(to targetStep: Int) {
            let delta = targetStep - completedSteps
            if delta > 0 {
                runner.step(count: delta)
                completedSteps = targetStep
            }
        }

        let sequenceStepSet = Set(templateSequenceSteps())
        var sequenceMassMaps: [MLXArray] = []
        var sequenceSnapshots: [[CenterSnapshot]] = []

        func captureTemplateSequenceStep(_ step: Int) {
            if sequenceStepSet.contains(step) {
                sequenceMassMaps.append(runner.materializeMassMap(channelWeights: metalMatterWeights()))
            }
        }

        func measureCenterSnapshots() -> [CenterSnapshot] {
            if runner.supportsMassSummary {
                let summary = runner.summarizeMass(
                    occupancyThreshold: 0.0,
                    includeGyration: false,
                    channelWeights: metalMatterWeights()
                )
                return (0..<pop).map { centerSnapshot(from: summary, index: $0) }
            }
            let massMap = runner.materializeMassMap(channelWeights: metalMatterWeights())
            let centers = materializeCenterOfMassBatch([centerOfMassBatchDeviceFromMassMap(massMap)])[0]
            return (0..<pop).map { centerSnapshot(from: centers, index: $0) ?? deadSnapshot() }
        }

        func captureTrajectoryStep(_ step: Int) {
            if esConfig.fitness.usesTrajectoryMetrics && sequenceStepSet.contains(step) {
                sequenceSnapshots.append(measureCenterSnapshots())
            }
        }

        captureTemplateSequenceStep(0)
        captureTrajectoryStep(0)
        var measurementSteps = Set(sequenceStepSet)
        if requirements.usesMidCenter {
            measurementSteps.insert(requirements.midStep)
        }
        if requirements.usesCenterOfMass {
            measurementSteps.insert(requirements.targetStep)
        }
        measurementSteps.insert(esConfig.steps)

        for step in measurementSteps.sorted() where step > 0 {
            let stepMeasurementStart = ContinuousClock.now
            advanceRunner(to: step)
            if requirements.usesMidCenter && step == requirements.midStep {
                midSnapshots = measureCenterSnapshots()
            }
            if requirements.usesCenterOfMass && step == requirements.targetStep {
                targetSnapshots = measureCenterSnapshots()
            }
            if usesTranslatedShapeOverlap && step == requirements.midStep {
                midMassBatch = materializeMassBatch(runner.materializeMassMap(channelWeights: metalMatterWeights()))
            }
            if usesTranslatedShapeOverlap && step == requirements.targetStep {
                targetMassBatch = materializeMassBatch(runner.materializeMassMap(channelWeights: metalMatterWeights()))
            }
            captureTemplateSequenceStep(step)
            captureTrajectoryStep(step)
            measurementMs += durationMs(stepMeasurementStart.duration(to: ContinuousClock.now))
        }

        rolloutMs = durationMs(rolloutStart.duration(to: ContinuousClock.now))

        let finalMeasurementStart = ContinuousClock.now
        var finalMassMapBatch: MLXArray? = nil
        let gyrationValues: [Float]?
        if runner.supportsMassSummary {
            let summary = runner.summarizeMass(
                occupancyThreshold: 0.0,
                includeGyration: esConfig.fitness.gyrationPenalty != nil,
                channelWeights: metalMatterWeights()
            )
            if let rawGyration = summary.rawGyration {
                gyrationValues = zip(summary.totalMass, rawGyration).map { totalMass, gyration in
                    totalMass > 0 ? gyration / Float(config.sx * config.sy) : 1.0
                }
            } else {
                gyrationValues = nil
            }
        } else {
            finalMassMapBatch = runner.materializeMassMap(channelWeights: metalMatterWeights())
            gyrationValues = esConfig.fitness.gyrationPenalty == nil ? nil : computeGyrationBatchFromMassMap(finalMassMapBatch!)
        }
        let morphologyValues: MorphologyMeasurementBatch?
        if esConfig.fitness.usesMorphologyMetrics {
            if finalMassMapBatch == nil {
                finalMassMapBatch = runner.materializeMassMap(channelWeights: metalMatterWeights())
            }
            morphologyValues = morphologyMeasurements(fromMassMap: finalMassMapBatch!)
        } else {
            morphologyValues = nil
        }
        let templateSequenceValues = templateSequenceMetricValues(from: sequenceMassMaps)
        let orientationPhaseMotion = orientationPhaseMotionValues(from: sequenceMassMaps)
        let angularPhaseMotion = angularPhaseMotionValues(from: sequenceMassMaps)
        let sectorTransport = sectorTransportValues(from: sequenceMassMaps)
        let trajectoryValues = trajectoryMetricValues(from: sequenceSnapshots, stepSpan: trajectoryMetricStepSpan())
        let chemotaxisScores: [Float]?
        if requirements.objective == "chemotaxis" {
            if let field = chemFieldBatch {
                if finalMassMapBatch == nil {
                    finalMassMapBatch = runner.materializeMassMap(channelWeights: metalMatterWeights())
                }
                let numerator = (finalMassMapBatch! * field).sum(axes: [1, 2])
                let denominator = finalMassMapBatch!.sum(axes: [1, 2])
                eval(numerator, denominator)
                let numeratorCPU: [Float] = numerator.asArray(Float.self)
                let denominatorCPU: [Float] = denominator.asArray(Float.self)
                chemotaxisScores = zip(numeratorCPU, denominatorCPU).map { numerator, denominator in
                    numerator / max(denominator, 1e-6)
                }
            } else {
                chemotaxisScores = Array(repeating: 0.0, count: pop)
            }
        } else {
            chemotaxisScores = nil
        }
        let translatedShapeOverlapValues: [Float]?
        if usesTranslatedShapeOverlap,
           let midMassBatch,
           let targetMassBatch {
            translatedShapeOverlapValues = translatedShapeOverlapBatch(
                source: midMassBatch,
                target: targetMassBatch,
                sourceCenters: BatchCenterOfMassCPU(
                    alive: midSnapshots.map { $0?.alive == true ? 1.0 : 0.0 },
                    x: midSnapshots.map { $0?.x ?? 0.0 },
                    y: midSnapshots.map { $0?.y ?? 0.0 }
                ),
                targetCenters: BatchCenterOfMassCPU(
                    alive: targetSnapshots.map { $0?.alive == true ? 1.0 : 0.0 },
                    x: targetSnapshots.map { $0?.x ?? 0.0 },
                    y: targetSnapshots.map { $0?.y ?? 0.0 }
                ),
                threshold: esConfig.fitness.morphologyThreshold ?? 0.03,
                useTorus: runtimeConfig.border == "torus"
            )
        } else {
            translatedShapeOverlapValues = nil
        }
        let midOccupiedFractionValues = midMassBatch.map {
            occupiedFractionBatch(materialized: $0, threshold: esConfig.fitness.morphologyThreshold ?? 0.03)
        }
        let targetOccupiedFractionValues = targetMassBatch.map {
            occupiedFractionBatch(materialized: $0, threshold: esConfig.fitness.morphologyThreshold ?? 0.03)
        }
        measurementMs += durationMs(finalMeasurementStart.duration(to: ContinuousClock.now))

        for index in 0..<pop {
            measurements.append(
                CandidateMeasurement(
                    initial: initialSnapshots[index],
                    mid: midSnapshots[index],
                    target: targetSnapshots[index],
                    translatedShapeOverlap: translatedShapeOverlapValues?[index],
                    midOccupiedFraction: midOccupiedFractionValues?[index],
                    targetOccupiedFraction: targetOccupiedFractionValues?[index],
                    occupiedGrowth: occupiedGrowth(
                        mid: midOccupiedFractionValues?[index],
                        target: targetOccupiedFractionValues?[index]
                    ),
                    gyration: gyrationValues?[index],
                    componentCount: morphologyValues?.componentCount?[index],
                    largestComponentFraction: morphologyValues?.largestComponentFraction?[index],
                    largestComponentAnisotropy: morphologyValues?.largestComponentAnisotropy?[index],
                    componentMassEvenness: morphologyValues?.componentMassEvenness?[index],
                    momentMass: morphologyValues?.momentMass?[index],
                    largestComponentSolidity: morphologyValues?.largestComponentSolidity?[index],
                    largestComponentMeanThickness: morphologyValues?.largestComponentMeanThickness?[index],
                    largestComponentMaxThickness: morphologyValues?.largestComponentMaxThickness?[index],
                    largestComponentFilamentarity: morphologyValues?.largestComponentFilamentarity?[index],
                    momentDensity: morphologyValues?.momentDensity?[index],
                    occupiedFraction: morphologyValues?.occupiedFraction?[index],
                    momentAnisotropy: morphologyValues?.momentAnisotropy?[index],
                    internalStripe: morphologyValues?.internalStripe?[index],
                    orientedRidge: morphologyValues?.orientedRidge?[index],
                    largestComponentInternalStripe: morphologyValues?.largestComponentInternalStripe?[index],
                    largestComponentOrientedRidge: morphologyValues?.largestComponentOrientedRidge?[index],
                    templateSimilarity: morphologyValues?.templateSimilarity?[index],
                    templateSequenceSimilarity: templateSequenceValues.similarity?[index],
                    templateSequenceMassMismatch: templateSequenceValues.massMismatch?[index],
                    templateSequenceSupportMismatch: templateSequenceValues.supportMismatch?[index],
                    templateSequenceChangeMismatch: templateSequenceValues.changeMismatch?[index],
                    templateSequenceDeltaSimilarity: templateSequenceValues.deltaSimilarity?[index],
                    templateSequenceSignedDeltaSimilarity: templateSequenceValues.signedDeltaSimilarity?[index],
                    orientationPhaseMotion: orientationPhaseMotion?[index],
                    angularPhaseMotion: angularPhaseMotion?[index],
                    sectorTransport: sectorTransport?[index],
                    trajectoryPathLength: trajectoryValues.pathLength?[index],
                    trajectoryDisplacement: trajectoryValues.displacement?[index],
                    movementEfficiency: trajectoryValues.movementEfficiency?[index],
                    centerVelocity: trajectoryValues.centerVelocity?[index],
                    chemotaxisScore: chemotaxisScores?[index]
                )
            )
        }

        return PopulationEvaluation(
            measurements: measurements,
            kernelCompileMs: kernelCompileMs,
            stateBuildMs: stateBuildMs,
            fieldBuildMs: fieldBuildMs,
            rolloutMs: rolloutMs,
            measurementMs: measurementMs
        )
    }

    private func fitnessValue(from measurement: CandidateMeasurement) -> Float {
        switch esConfig.fitness.objective {
        case "directed_motion", "obstacle_navigation":
            guard measurement.initial.alive, let target = measurement.target, target.alive else {
                return adjustedFitness(base: 0.0, measurement: measurement)
            }
            let dx = target.x - measurement.initial.x
            let dy = target.y - measurement.initial.y
            let displacement = sqrt(dx * dx + dy * dy)
            return adjustedFitness(base: displacement, measurement: measurement)
        case "angular_motion":
            guard measurement.initial.alive,
                  let mid = measurement.mid, mid.alive,
                  let target = measurement.target, target.alive else {
                return adjustedFitness(base: 0.0, measurement: measurement)
            }
            let v1 = (mid.x - measurement.initial.x, mid.y - measurement.initial.y)
            let v2 = (target.x - mid.x, target.y - mid.y)
            let d1 = sqrt(v1.0 * v1.0 + v1.1 * v1.1)
            let d2 = sqrt(v2.0 * v2.0 + v2.1 * v2.1)
            guard d1 >= esConfig.fitness.angleThreshold, d2 >= esConfig.fitness.angleThreshold else {
                return adjustedFitness(base: d1 + d2, measurement: measurement)
            }
            let dot = v1.0 * v2.0 + v1.1 * v2.1
            var cosAngle = dot / (d1 * d2)
            cosAngle = max(-1.0, min(1.0, cosAngle))
            return adjustedFitness(base: d1 + d2 + acos(cosAngle), measurement: measurement)
        case "chemotaxis":
            return adjustedFitness(base: measurement.chemotaxisScore ?? 0.0, measurement: measurement)
        case "trajectory_motion",
             "template_sequence",
             "orientation_phase_motion",
             "angular_phase_motion",
             "sector_transport_motion":
            return adjustedFitness(base: 0.0, measurement: measurement)
        case "organismness":
            return adjustedFitness(base: 0.0, measurement: measurement)
        case "coherent_transport":
            guard let mid = measurement.mid, mid.alive,
                  let target = measurement.target, target.alive else {
                return 0.0
            }
            guard let translatedShapeOverlap = measurement.translatedShapeOverlap else {
                fatalError("coherent_transport objective requires translated shape overlap.")
            }
            let dx = target.x - mid.x
            let dy = target.y - mid.y
            let displacement = sqrt(dx * dx + dy * dy)
            return coherentTransportAdjustedFitness(
                base: displacement * translatedShapeOverlap,
                displacement: displacement,
                measurement: measurement
            )
        case "body_locomotion":
            guard let mid = measurement.mid, mid.alive,
                  let target = measurement.target, target.alive else {
                return 0.0
            }
            guard let translatedShapeOverlap = measurement.translatedShapeOverlap else {
                fatalError("body_locomotion objective requires translated shape overlap.")
            }
            let dx = target.x - mid.x
            let dy = target.y - mid.y
            let displacement = sqrt(dx * dx + dy * dy)
            let base = bodyLocomotionScore(
                displacement: displacement,
                translatedShapeOverlap: translatedShapeOverlap,
                measurement: measurement
            )
            return bodyLocomotionAdjustedFitness(base: base, measurement: measurement)
        default:
            return 0.0
        }
    }

    private func adjustedFitness(base: Float, measurement: CandidateMeasurement) -> Float {
        var value = base
        if let failureFitness = esConfig.fitness.morphologyGuardFailureFitness,
           failsMorphologyGuard(measurement) {
            return failureFitness
        }
        if let penalty = esConfig.fitness.gyrationPenalty {
            guard let gyration = measurement.gyration else {
                fatalError("gyration_penalty requested but gyration was not computed.")
            }
            value -= penalty * gyration
        }
        if let penalty = esConfig.fitness.componentCountPenalty {
            guard let componentCount = measurement.componentCount else {
                fatalError("component_count_penalty requested but component metrics were not computed.")
            }
            value -= penalty * max(componentCount - 1.0, 0.0)
        }
        if let target = esConfig.fitness.componentCountTarget,
           let penalty = esConfig.fitness.componentCountTargetPenalty {
            guard let componentCount = measurement.componentCount else {
                fatalError("component_count_target_penalty requested but component metrics were not computed.")
            }
            value -= penalty * componentCountTargetMismatch(componentCount, target: target)
        }
        if let penalty = esConfig.fitness.componentCountLimitPenalty {
            guard let componentCount = measurement.componentCount else {
                fatalError("component_count_limit_penalty requested but component metrics were not computed.")
            }
            if let minimum = esConfig.fitness.minimumComponentCount {
                value -= penalty * max(minimum - componentCount, 0)
            }
            if let maximum = esConfig.fitness.maximumComponentCount {
                value -= penalty * max(componentCount - maximum, 0)
            }
        }
        if let reward = esConfig.fitness.largestComponentFractionReward {
            guard let largestComponentFraction = measurement.largestComponentFraction else {
                fatalError("largest_component_fraction_reward requested but component metrics were not computed.")
            }
            value += reward * largestComponentFraction
        }
        if let minimum = esConfig.fitness.minimumLargestComponentFraction,
           let penalty = esConfig.fitness.largestComponentFractionPenalty {
            guard let largestComponentFraction = measurement.largestComponentFraction else {
                fatalError("largest_component_fraction_penalty requested but component metrics were not computed.")
            }
            value -= penalty * max(minimum - largestComponentFraction, 0)
        }
        if let maximum = esConfig.fitness.maximumLargestComponentFraction,
           let penalty = esConfig.fitness.largestComponentFractionLimitPenalty {
            guard let largestComponentFraction = measurement.largestComponentFraction else {
                fatalError("largest_component_fraction_limit_penalty requested but component metrics were not computed.")
            }
            value -= penalty * max(largestComponentFraction - maximum, 0)
        }
        if let penalty = esConfig.fitness.largestComponentAnisotropyPenalty {
            guard let largestComponentAnisotropy = measurement.largestComponentAnisotropy else {
                fatalError("largest_component_anisotropy_penalty requested but component metrics were not computed.")
            }
            value -= penalty * largestComponentAnisotropy
        }
        if let reward = esConfig.fitness.componentMassEvennessReward {
            guard let componentMassEvenness = measurement.componentMassEvenness else {
                fatalError("component_mass_evenness_reward requested but component metrics were not computed.")
            }
            value += reward * componentMassEvenness
        }
        if let minimum = esConfig.fitness.minimumComponentMassEvenness,
           let penalty = esConfig.fitness.componentMassEvennessPenalty {
            guard let componentMassEvenness = measurement.componentMassEvenness else {
                fatalError("component_mass_evenness_penalty requested but component metrics were not computed.")
            }
            value -= penalty * max(minimum - componentMassEvenness, 0)
        }
        if let reward = esConfig.fitness.largestComponentSolidityReward {
            guard let largestComponentSolidity = measurement.largestComponentSolidity else {
                fatalError("largest_component_solidity_reward requested but component metrics were not computed.")
            }
            value += reward * largestComponentSolidity
        }
        if let reward = esConfig.fitness.largestComponentMeanThicknessReward {
            guard let largestComponentMeanThickness = measurement.largestComponentMeanThickness else {
                fatalError("largest_component_mean_thickness_reward requested but component metrics were not computed.")
            }
            value += reward * largestComponentMeanThickness
        }
        if let penalty = esConfig.fitness.largestComponentFilamentarityPenalty {
            guard let largestComponentFilamentarity = measurement.largestComponentFilamentarity else {
                fatalError("largest_component_filamentarity_penalty requested but component metrics were not computed.")
            }
            value -= penalty * largestComponentFilamentarity
        }
        if let reward = esConfig.fitness.momentDensityReward {
            guard let momentDensity = measurement.momentDensity else {
                fatalError("moment_density_reward requested but moment metrics were not computed.")
            }
            value += reward * momentDensity
        }
        if let minimum = esConfig.fitness.minimumMomentDensity,
           let penalty = esConfig.fitness.momentDensityPenalty {
            guard let momentDensity = measurement.momentDensity else {
                fatalError("moment_density_penalty requested but moment metrics were not computed.")
            }
            value -= penalty * max(minimum - momentDensity, 0)
        }
        if let penalty = esConfig.fitness.momentAnisotropyPenalty {
            guard let momentAnisotropy = measurement.momentAnisotropy else {
                fatalError("moment_anisotropy_penalty requested but moment metrics were not computed.")
            }
            value -= penalty * momentAnisotropy
        }
        if let maximum = esConfig.fitness.maximumMomentAnisotropy,
           let penalty = esConfig.fitness.momentAnisotropyLimitPenalty {
            guard let momentAnisotropy = measurement.momentAnisotropy else {
                fatalError("moment_anisotropy_limit_penalty requested but moment metrics were not computed.")
            }
            value -= penalty * max(momentAnisotropy - maximum, 0)
        }
        if let penalty = esConfig.fitness.internalStripePenalty {
            guard let internalStripe = measurement.internalStripe else {
                fatalError("internal_stripe_penalty requested but stripe metrics were not computed.")
            }
            value -= penalty * internalStripe
        }
        if let penalty = esConfig.fitness.orientedRidgePenalty {
            guard let orientedRidge = measurement.orientedRidge else {
                fatalError("oriented_ridge_penalty requested but ridge metrics were not computed.")
            }
            value -= penalty * orientedRidge
        }
        if let penalty = esConfig.fitness.largestComponentInternalStripePenalty {
            guard let largestComponentInternalStripe = measurement.largestComponentInternalStripe else {
                fatalError("largest_component_internal_stripe_penalty requested but largest-component stripe metrics were not computed.")
            }
            value -= penalty * largestComponentInternalStripe
        }
        if let penalty = esConfig.fitness.largestComponentOrientedRidgePenalty {
            guard let largestComponentOrientedRidge = measurement.largestComponentOrientedRidge else {
                fatalError("largest_component_oriented_ridge_penalty requested but largest-component ridge metrics were not computed.")
            }
            value -= penalty * largestComponentOrientedRidge
        }
        if let reward = esConfig.fitness.templateSimilarityReward {
            guard let templateSimilarity = measurement.templateSimilarity else {
                fatalError("template_similarity_reward requested but template similarity was not computed.")
            }
            value += reward * templateSimilarity
        }
        if let reward = esConfig.fitness.templateSequenceReward {
            guard let templateSequenceSimilarity = measurement.templateSequenceSimilarity else {
                fatalError("template_sequence_reward requested but template sequence similarity was not computed.")
            }
            value += reward * templateSequenceSimilarity
        }
        if let penalty = esConfig.fitness.templateSequenceMassPenalty {
            guard let templateSequenceMassMismatch = measurement.templateSequenceMassMismatch else {
                fatalError("template_sequence_mass_penalty requested but template sequence mass mismatch was not computed.")
            }
            value -= penalty * templateSequenceMassMismatch
        }
        if let penalty = esConfig.fitness.templateSequenceSupportPenalty {
            guard let templateSequenceSupportMismatch = measurement.templateSequenceSupportMismatch else {
                fatalError("template_sequence_support_penalty requested but template sequence support mismatch was not computed.")
            }
            value -= penalty * templateSequenceSupportMismatch
        }
        if let penalty = esConfig.fitness.templateSequenceChangePenalty {
            guard let templateSequenceChangeMismatch = measurement.templateSequenceChangeMismatch else {
                fatalError("template_sequence_change_penalty requested but template sequence change mismatch was not computed.")
            }
            value -= penalty * templateSequenceChangeMismatch
        }
        if let reward = esConfig.fitness.templateSequenceDeltaReward {
            guard let templateSequenceDeltaSimilarity = measurement.templateSequenceDeltaSimilarity else {
                fatalError("template_sequence_delta_reward requested but template sequence delta similarity was not computed.")
            }
            value += reward * templateSequenceDeltaSimilarity
        }
        if let reward = esConfig.fitness.templateSequenceSignedDeltaReward {
            guard let templateSequenceSignedDeltaSimilarity = measurement.templateSequenceSignedDeltaSimilarity else {
                fatalError("template_sequence_signed_delta_reward requested but template sequence signed-delta similarity was not computed.")
            }
            value += reward * templateSequenceSignedDeltaSimilarity
        }
        if let reward = esConfig.fitness.orientationPhaseMotionReward {
            guard let orientationPhaseMotion = measurement.orientationPhaseMotion else {
                fatalError("orientation_phase_motion_reward requested but orientation phase motion was not computed.")
            }
            value += reward * orientationPhaseMotion
        }
        if let minimum = esConfig.fitness.minimumOrientationPhaseMotion,
           let penalty = esConfig.fitness.orientationPhaseMotionPenalty {
            guard let orientationPhaseMotion = measurement.orientationPhaseMotion else {
                fatalError("orientation_phase_motion_penalty requested but orientation phase motion was not computed.")
            }
            value -= penalty * max(minimum - orientationPhaseMotion, 0)
        }
        if let reward = esConfig.fitness.angularPhaseMotionReward {
            guard let angularPhaseMotion = measurement.angularPhaseMotion else {
                fatalError("angular_phase_motion_reward requested but angular phase motion was not computed.")
            }
            value += reward * angularPhaseMotion
        }
        if let minimum = esConfig.fitness.minimumAngularPhaseMotion,
           let penalty = esConfig.fitness.angularPhaseMotionPenalty {
            guard let angularPhaseMotion = measurement.angularPhaseMotion else {
                fatalError("angular_phase_motion_penalty requested but angular phase motion was not computed.")
            }
            value -= penalty * max(minimum - angularPhaseMotion, 0)
        }
        if let reward = esConfig.fitness.sectorTransportReward {
            guard let sectorTransport = measurement.sectorTransport else {
                fatalError("sector_transport_reward requested but sector transport was not computed.")
            }
            value += reward * sectorTransport
        }
        if let minimum = esConfig.fitness.minimumSectorTransport,
           let penalty = esConfig.fitness.sectorTransportPenalty {
            guard let sectorTransport = measurement.sectorTransport else {
                fatalError("sector_transport_penalty requested but sector transport was not computed.")
            }
            value -= penalty * max(minimum - sectorTransport, 0)
        }
        if let minimum = esConfig.fitness.minimumTrajectoryPathLength,
           let penalty = esConfig.fitness.trajectoryPathLengthPenalty {
            guard let trajectoryPathLength = measurement.trajectoryPathLength else {
                fatalError("trajectory_path_length_penalty requested but trajectory path length was not computed.")
            }
            value -= penalty * max(minimum - trajectoryPathLength, 0)
        }
        if let reward = esConfig.fitness.trajectoryPathLengthReward {
            guard let trajectoryPathLength = measurement.trajectoryPathLength else {
                fatalError("trajectory_path_length_reward requested but trajectory path length was not computed.")
            }
            value += reward * trajectoryPathLength
        }
        if let minimum = esConfig.fitness.minimumTrajectoryDisplacement,
           let penalty = esConfig.fitness.trajectoryDisplacementPenalty {
            guard let trajectoryDisplacement = measurement.trajectoryDisplacement else {
                fatalError("trajectory_displacement_penalty requested but trajectory displacement was not computed.")
            }
            value -= penalty * max(minimum - trajectoryDisplacement, 0)
        }
        if let reward = esConfig.fitness.trajectoryDisplacementReward {
            guard let trajectoryDisplacement = measurement.trajectoryDisplacement else {
                fatalError("trajectory_displacement_reward requested but trajectory displacement was not computed.")
            }
            value += reward * trajectoryDisplacement
        }
        if let minimum = esConfig.fitness.minimumMovementEfficiency,
           let penalty = esConfig.fitness.movementEfficiencyPenalty {
            guard let movementEfficiency = measurement.movementEfficiency else {
                fatalError("movement_efficiency_penalty requested but movement efficiency was not computed.")
            }
            value -= penalty * max(minimum - movementEfficiency, 0)
        }
        if let reward = esConfig.fitness.movementEfficiencyReward {
            guard let movementEfficiency = measurement.movementEfficiency else {
                fatalError("movement_efficiency_reward requested but movement efficiency was not computed.")
            }
            value += reward * movementEfficiency
        }
        if let minimum = esConfig.fitness.minimumCenterVelocity,
           let penalty = esConfig.fitness.centerVelocityPenalty {
            guard let centerVelocity = measurement.centerVelocity else {
                fatalError("center_velocity_penalty requested but center velocity was not computed.")
            }
            value -= penalty * max(minimum - centerVelocity, 0)
        }
        if let reward = esConfig.fitness.centerVelocityReward {
            guard let centerVelocity = measurement.centerVelocity else {
                fatalError("center_velocity_reward requested but center velocity was not computed.")
            }
            value += reward * centerVelocity
        }
        return applyOrganismnessPenalty(value, measurement: measurement)
    }

    private func bodyLocomotionAdjustedFitness(base: Float, measurement: CandidateMeasurement) -> Float {
        var value = base
        if let penalty = esConfig.fitness.gyrationPenalty {
            guard let gyration = measurement.gyration else {
                fatalError("gyration_penalty requested but gyration was not computed.")
            }
            value -= penalty * gyration
        }
        if let penalty = esConfig.fitness.componentCountPenalty {
            guard let componentCount = measurement.componentCount else {
                fatalError("component_count_penalty requested but component metrics were not computed.")
            }
            value -= penalty * max(componentCount - 1.0, 0.0)
        }
        return applyOrganismnessPenalty(value, measurement: measurement)
    }

    private func bodyLocomotionScore(
        displacement: Float,
        translatedShapeOverlap: Float,
        measurement: CandidateMeasurement
    ) -> Float {
        let overlapTerm = 0.2 + 0.8 * unitInterval(translatedShapeOverlap)
        let growthTerm = bodyLocomotionGrowthTerm(measurement.occupiedGrowth ?? 1.0)
        let connectedTerm = 0.25 + 0.75 * unitInterval(measurement.largestComponentFraction ?? 0.0)
        let solidityTerm = 0.35 + 0.65 * unitInterval(measurement.largestComponentSolidity ?? 0.0)
        let anisotropyTerm = 0.35 + 0.65 * (1.0 - unitInterval(measurement.largestComponentAnisotropy ?? 1.0))
        let filamentTerm = 0.35 + 0.65 * (1.0 - unitInterval(measurement.largestComponentFilamentarity ?? 1.0))
        let morphologyTerm = (connectedTerm + solidityTerm + anisotropyTerm + filamentTerm) / 4.0
        return max(displacement, 0.0) * overlapTerm * growthTerm * morphologyTerm
    }

    private func bodyLocomotionGrowthTerm(_ value: Float) -> Float {
        guard value.isFinite, value > 0 else { return 0.0 }
        let deviation = abs(log(value))
        return 1.0 / (1.0 + 2.0 * deviation)
    }

    private func unitInterval(_ value: Float) -> Float {
        guard value.isFinite else { return 0.0 }
        return max(0.0, min(1.0, value))
    }

    private func organismnessViolation(measurement: CandidateMeasurement) -> Float {
        var violation: Float = 0.0
        if let minimum = esConfig.fitness.translatedShapeOverlapMin {
            guard let metric = measurement.translatedShapeOverlap else {
                fatalError("translated_shape_overlap_min requested but translated overlap was not computed.")
            }
            violation += max(minimum - metric, 0.0)
        }
        if let maximum = esConfig.fitness.componentCountMax {
            guard let metric = measurement.componentCount else {
                fatalError("component_count_max requested but component metrics were not computed.")
            }
            violation += max(metric - maximum, 0.0)
        }
        if let minimum = esConfig.fitness.largestComponentFractionMin {
            guard let metric = measurement.largestComponentFraction else {
                fatalError("largest_component_fraction_min requested but component metrics were not computed.")
            }
            violation += max(minimum - metric, 0.0)
        }
        if let minimum = esConfig.fitness.largestComponentSolidityMin {
            guard let metric = measurement.largestComponentSolidity else {
                fatalError("largest_component_solidity_min requested but component metrics were not computed.")
            }
            violation += max(minimum - metric, 0.0)
        }
        if let minimum = esConfig.fitness.largestComponentMeanThicknessMin {
            guard let metric = measurement.largestComponentMeanThickness else {
                fatalError("largest_component_mean_thickness_min requested but component metrics were not computed.")
            }
            violation += max(minimum - metric, 0.0)
        }
        if let maximum = esConfig.fitness.largestComponentFilamentarityMax {
            guard let metric = measurement.largestComponentFilamentarity else {
                fatalError("largest_component_filamentarity_max requested but component metrics were not computed.")
            }
            violation += max(metric - maximum, 0.0)
        }
        if let minimum = esConfig.fitness.occupiedFractionMin {
            guard let metric = measurement.occupiedFraction else {
                fatalError("occupied_fraction_min requested but moment metrics were not computed.")
            }
            violation += max(minimum - metric, 0.0)
        }
        if let maximum = esConfig.fitness.occupiedFractionMax {
            guard let metric = measurement.occupiedFraction else {
                fatalError("occupied_fraction_max requested but moment metrics were not computed.")
            }
            violation += max(metric - maximum, 0.0)
        }
        if let maximum = esConfig.fitness.occupiedGrowthMax {
            guard let metric = measurement.occupiedGrowth else {
                fatalError("occupied_growth_max requested but mid/target occupancy was not computed.")
            }
            violation += max(metric - maximum, 0.0)
        }
        return violation
    }

    private func applyOrganismnessPenalty(_ value: Float, measurement: CandidateMeasurement) -> Float {
        let violation = organismnessViolation(measurement: measurement)
        guard violation > 0 else { return value }
        return value - (esConfig.fitness.organismnessPenalty ?? 1.0) * violation
    }

    private func coherentTransportAdjustedFitness(
        base: Float,
        displacement: Float,
        measurement: CandidateMeasurement
    ) -> Float {
        var value = base
        let minimumDisplacement = max(esConfig.fitness.minimumDisplacement ?? esConfig.fitness.angleThreshold, 0.0)
        let rewardGate: Float
        if minimumDisplacement <= 0.0 {
            rewardGate = 1.0
        } else {
            rewardGate = min(max((displacement - minimumDisplacement) / minimumDisplacement, 0.0), 1.0)
        }

        if let penalty = esConfig.fitness.gyrationPenalty {
            guard let gyration = measurement.gyration else {
                fatalError("gyration_penalty requested but gyration was not computed.")
            }
            value -= penalty * gyration
        }
        if let penalty = esConfig.fitness.componentCountPenalty {
            guard let componentCount = measurement.componentCount else {
                fatalError("component_count_penalty requested but component metrics were not computed.")
            }
            value -= penalty * max(componentCount - 1.0, 0.0)
        }
        if let reward = esConfig.fitness.largestComponentFractionReward {
            guard let largestComponentFraction = measurement.largestComponentFraction else {
                fatalError("largest_component_fraction_reward requested but component metrics were not computed.")
            }
            value += rewardGate * reward * largestComponentFraction
        }
        if let penalty = esConfig.fitness.largestComponentAnisotropyPenalty {
            guard let largestComponentAnisotropy = measurement.largestComponentAnisotropy else {
                fatalError("largest_component_anisotropy_penalty requested but component metrics were not computed.")
            }
            value -= penalty * largestComponentAnisotropy
        }
        if let reward = esConfig.fitness.largestComponentSolidityReward {
            guard let largestComponentSolidity = measurement.largestComponentSolidity else {
                fatalError("largest_component_solidity_reward requested but component metrics were not computed.")
            }
            value += rewardGate * reward * largestComponentSolidity
        }
        if let reward = esConfig.fitness.largestComponentMeanThicknessReward {
            guard let largestComponentMeanThickness = measurement.largestComponentMeanThickness else {
                fatalError("largest_component_mean_thickness_reward requested but component metrics were not computed.")
            }
            value += rewardGate * reward * largestComponentMeanThickness
        }
        if let penalty = esConfig.fitness.largestComponentFilamentarityPenalty {
            guard let largestComponentFilamentarity = measurement.largestComponentFilamentarity else {
                fatalError("largest_component_filamentarity_penalty requested but component metrics were not computed.")
            }
            value -= penalty * largestComponentFilamentarity
        }
        if let reward = esConfig.fitness.momentDensityReward {
            guard let momentDensity = measurement.momentDensity else {
                fatalError("moment_density_reward requested but moment metrics were not computed.")
            }
            value += rewardGate * reward * momentDensity
        }
        if let penalty = esConfig.fitness.momentAnisotropyPenalty {
            guard let momentAnisotropy = measurement.momentAnisotropy else {
                fatalError("moment_anisotropy_penalty requested but moment metrics were not computed.")
            }
            value -= penalty * momentAnisotropy
        }
        return applyOrganismnessPenalty(value, measurement: measurement)
    }

    private func failsMorphologyGuard(_ measurement: CandidateMeasurement) -> Bool {
        if let minimum = esConfig.fitness.minimumComponentCount {
            guard let componentCount = measurement.componentCount else {
                fatalError("minimum_component_count guard requested but component metrics were not computed.")
            }
            if componentCount < minimum { return true }
        }
        if let maximum = esConfig.fitness.maximumComponentCount {
            guard let componentCount = measurement.componentCount else {
                fatalError("maximum_component_count guard requested but component metrics were not computed.")
            }
            if componentCount > maximum { return true }
        }
        if let minimum = esConfig.fitness.minimumLargestComponentFraction {
            guard let largestComponentFraction = measurement.largestComponentFraction else {
                fatalError("minimum_largest_component_fraction guard requested but component metrics were not computed.")
            }
            if largestComponentFraction < minimum { return true }
        }
        if let maximum = esConfig.fitness.maximumLargestComponentFraction {
            guard let largestComponentFraction = measurement.largestComponentFraction else {
                fatalError("maximum_largest_component_fraction guard requested but component metrics were not computed.")
            }
            if largestComponentFraction > maximum { return true }
        }
        if let maximum = esConfig.fitness.maximumLargestComponentAnisotropy {
            guard let largestComponentAnisotropy = measurement.largestComponentAnisotropy else {
                fatalError("maximum_largest_component_anisotropy guard requested but component metrics were not computed.")
            }
            if largestComponentAnisotropy > maximum { return true }
        }
        if let minimum = esConfig.fitness.minimumComponentMassEvenness {
            guard let componentMassEvenness = measurement.componentMassEvenness else {
                fatalError("minimum_component_mass_evenness guard requested but component metrics were not computed.")
            }
            if componentMassEvenness < minimum { return true }
        }
        if let minimum = esConfig.fitness.minimumMomentMass {
            guard let momentMass = measurement.momentMass else {
                fatalError("minimum_moment_mass guard requested but moment metrics were not computed.")
            }
            if momentMass < minimum { return true }
        }
        if let maximum = esConfig.fitness.maximumMomentMass {
            guard let momentMass = measurement.momentMass else {
                fatalError("maximum_moment_mass guard requested but moment metrics were not computed.")
            }
            if momentMass > maximum { return true }
        }
        if let minimum = esConfig.fitness.minimumMomentDensity {
            guard let momentDensity = measurement.momentDensity else {
                fatalError("minimum_moment_density guard requested but moment metrics were not computed.")
            }
            if momentDensity < minimum { return true }
        }
        if let maximum = esConfig.fitness.maximumMomentDensity {
            guard let momentDensity = measurement.momentDensity else {
                fatalError("maximum_moment_density guard requested but moment metrics were not computed.")
            }
            if momentDensity > maximum { return true }
        }
        if let maximum = esConfig.fitness.maximumMomentAnisotropy {
            guard let momentAnisotropy = measurement.momentAnisotropy else {
                fatalError("maximum_moment_anisotropy guard requested but moment metrics were not computed.")
            }
            if momentAnisotropy > maximum { return true }
        }
        return false
    }

    private func fitnessValues(from measurements: [CandidateMeasurement]) -> [Float] {
        measurements.map(fitnessValue(from:))
    }

    private func morphologyMeasurements(
        from stateBatch: MLXArray,
        includeDiagnostics: Bool = false
    ) -> MorphologyMeasurementBatch? {
        guard esConfig.fitness.usesMorphologyMetrics else {
            return nil
        }
        let massMap = evolutionMassMapBatch(stateBatch, excludedChannels: excludedMassChannels)
        return morphologyMeasurements(fromMassMap: massMap, includeDiagnostics: includeDiagnostics)
    }

    private func morphologyMeasurements(
        fromMassMap massMap: MLXArray,
        includeDiagnostics: Bool = false
    ) -> MorphologyMeasurementBatch? {
        guard esConfig.fitness.usesMorphologyMetrics else {
            return nil
        }
        let materialized = materializeMassBatch(massMap)
        let threshold = esConfig.fitness.morphologyThreshold ?? 0.03
        let componentMetricsNeeded = includeDiagnostics ||
            esConfig.fitness.componentCountPenalty != nil ||
            esConfig.fitness.componentCountTargetPenalty != nil ||
            esConfig.fitness.componentCountLimitPenalty != nil ||
            esConfig.fitness.minimumComponentCount != nil ||
            esConfig.fitness.maximumComponentCount != nil ||
            esConfig.fitness.objective == "body_locomotion" ||
            esConfig.fitness.largestComponentFractionReward != nil ||
            esConfig.fitness.minimumLargestComponentFraction != nil ||
            esConfig.fitness.maximumLargestComponentFraction != nil ||
            esConfig.fitness.largestComponentFractionLimitPenalty != nil ||
            esConfig.fitness.maximumLargestComponentAnisotropy != nil ||
            esConfig.fitness.largestComponentAnisotropyPenalty != nil ||
            esConfig.fitness.componentMassEvennessReward != nil ||
            esConfig.fitness.minimumComponentMassEvenness != nil ||
            esConfig.fitness.componentMassEvennessPenalty != nil ||
            esConfig.fitness.largestComponentSolidityReward != nil ||
            esConfig.fitness.largestComponentMeanThicknessReward != nil ||
            esConfig.fitness.largestComponentFilamentarityPenalty != nil ||
            esConfig.fitness.componentCountMax != nil ||
            esConfig.fitness.largestComponentFractionMin != nil ||
            esConfig.fitness.largestComponentSolidityMin != nil ||
            esConfig.fitness.largestComponentMeanThicknessMin != nil ||
            esConfig.fitness.largestComponentFilamentarityMax != nil
        let componentMetrics = componentMetricsNeeded
            ? computeComponentMetricsBatch(
                materialized: materialized,
                threshold: threshold,
                useTorus: runtimeConfig.border == "torus"
            )
            : nil
        let momentMetricsNeeded = includeDiagnostics ||
            esConfig.fitness.momentDensityReward != nil ||
            esConfig.fitness.minimumMomentMass != nil ||
            esConfig.fitness.maximumMomentMass != nil ||
            esConfig.fitness.minimumMomentDensity != nil ||
            esConfig.fitness.maximumMomentDensity != nil ||
            esConfig.fitness.momentDensityPenalty != nil ||
            esConfig.fitness.momentAnisotropyPenalty != nil ||
            esConfig.fitness.maximumMomentAnisotropy != nil ||
            esConfig.fitness.momentAnisotropyLimitPenalty != nil ||
            esConfig.fitness.occupiedFractionMin != nil ||
            esConfig.fitness.occupiedFractionMax != nil
        let momentMetrics = !momentMetricsNeeded
            ? nil
            : computeMomentsBatch(
                materialized: materialized,
                config: MomentsConfig(enabled: true, threshold: threshold)
            )
        let internalStripe = !includeDiagnostics && esConfig.fitness.internalStripePenalty == nil
            ? nil
            : computeInternalStripeContrastBatch(
                materialized: materialized,
                threshold: threshold,
                useTorus: runtimeConfig.border == "torus"
            )
        let orientedRidge = !includeDiagnostics && esConfig.fitness.orientedRidgePenalty == nil
            ? nil
            : computeOrientedRidgeDominanceBatch(
                materialized: materialized,
                threshold: threshold
            )
        let largestComponentInternalStripe = !includeDiagnostics && esConfig.fitness.largestComponentInternalStripePenalty == nil
            ? nil
            : computeLargestComponentInternalStripeContrastBatch(
                materialized: materialized,
                threshold: threshold,
                useTorus: runtimeConfig.border == "torus"
            )
        let largestComponentOrientedRidge = !includeDiagnostics && esConfig.fitness.largestComponentOrientedRidgePenalty == nil
            ? nil
            : computeLargestComponentOrientedRidgeDominanceBatch(
                materialized: materialized,
                threshold: threshold,
                useTorus: runtimeConfig.border == "torus"
            )
        let templateSimilarity = esConfig.fitness.templateSimilarityReward == nil
            ? nil
            : computeTemplateSimilarityBatch(
                materialized: materialized,
                template: morphologyTemplate!,
                threshold: threshold,
                useTorus: runtimeConfig.border == "torus"
            )
        return MorphologyMeasurementBatch(
            componentCount: componentMetrics?.count,
            largestComponentFraction: componentMetrics?.largestFraction,
            largestComponentAnisotropy: componentMetrics?.largestAnisotropy,
            componentMassEvenness: componentMetrics?.massEvenness,
            momentMass: momentMetrics?.mass,
            largestComponentSolidity: componentMetrics?.largestSolidity,
            largestComponentMeanThickness: componentMetrics?.largestMeanThickness,
            largestComponentMaxThickness: componentMetrics?.largestMaxThickness,
            largestComponentFilamentarity: componentMetrics?.largestFilamentarity,
            momentDensity: momentMetrics?.density,
            occupiedFraction: momentMetrics?.volume.map {
                $0 / Float(max(materialized.sampleSize, 1))
            },
            momentAnisotropy: momentMetrics?.anisotropy,
            internalStripe: internalStripe,
            orientedRidge: orientedRidge,
            largestComponentInternalStripe: largestComponentInternalStripe,
            largestComponentOrientedRidge: largestComponentOrientedRidge,
            templateSimilarity: templateSimilarity
        )
    }

    private func computeGyrationBatchFromMassMap(_ massMap: MLXArray) -> [Float] {
        let signpost = LeniaSignposts.beginPhase("computeGyrationBatch")
        defer { LeniaSignposts.end(signpost) }
        let totalArr = massMap.sum(axes: [1, 2])
        let totalSafe = MLX.maximum(totalArr, MLXArray(Float(1e-6)))
        let comXArr = (massMap * metricGridX).sum(axes: [1, 2]) / totalSafe
        let comYArr = (massMap * metricGridY).sum(axes: [1, 2]) / totalSafe
        let comXGrid = comXArr.expandedDimensions(axes: [1, 2])
        let comYGrid = comYArr.expandedDimensions(axes: [1, 2])
        let distSq = (metricGridX - comXGrid) * (metricGridX - comXGrid) +
            (metricGridY - comYGrid) * (metricGridY - comYGrid)
        let scale = MLXArray(Float(config.sx * config.sy))
        let gyrationArr = (massMap * distSq).sum(axes: [1, 2]) / totalSafe / scale
        let evalSignpost = LeniaSignposts.beginPhase("computeGyrationBatchEval")
        eval(totalArr, gyrationArr)
        LeniaSignposts.end(evalSignpost)
        let totalCPU: [Float] = totalArr.asArray(Float.self)
        let gyrationCPU: [Float] = gyrationArr.asArray(Float.self)
        return zip(totalCPU, gyrationCPU).map { total, gyration in
            total > 0 ? gyration : 1.0
        }
    }

    private func computeGyrationBatch(_ ABatch: MLXArray) -> [Float] {
        let massMap = evolutionMassMapBatch(ABatch, excludedChannels: excludedMassChannels)
        return computeGyrationBatchFromMassMap(massMap)
    }

    private static func validateMetalBackendCompatibility(
        runtimeConfig: LeniaRuntimeConfig,
        esConfig: ESConfig
    ) {
        let validBoundaryPair = (runtimeConfig.border == "torus" && runtimeConfig.implementation.gradientBoundary == "periodic") ||
            (runtimeConfig.border == "wall" && runtimeConfig.implementation.gradientBoundary == "zero_pad")
        guard validBoundaryPair else {
            fatalError("EvolutionEngine Metal backends require torus/periodic or wall/zero_pad boundaries.")
        }
        if let food = runtimeConfig.food, food.enabled {
            fatalError("EvolutionEngine Metal backends do not support food fields yet.")
        }
        let supportedObjectives: Set<String> = [
            "directed_motion",
            "angular_motion",
            "obstacle_navigation",
            "chemotaxis",
            "trajectory_motion",
            "template_sequence",
            "orientation_phase_motion",
            "angular_phase_motion",
            "sector_transport_motion",
            "coherent_transport",
            "body_locomotion",
            "organismness",
        ]
        if !supportedObjectives.contains(esConfig.fitness.objective) {
            fatalError("EvolutionEngine Metal backends do not support objective \(esConfig.fitness.objective).")
        }
    }

    public func runGeneration(gen: Int) -> ESGenerationResult {
        let generationStart = ContinuousClock.now
        let generationSignpost = LeniaSignposts.beginPhase("runGeneration", generation: gen)
        defer { LeniaSignposts.end(generationSignpost) }
        let totalDim = theta.count
        let pop = esConfig.population

        let candidateSetupStart = generationStart
        let candidateSetupSignpost = LeniaSignposts.beginPhase("candidateSetup")
        let noise = sampleOpenESNoise(
            population: pop,
            dimensions: totalDim,
            rng: &rng
        )
        var candidateNoise = noise
        if esConfig.includeParent == true {
            candidateNoise[0] = Array(repeating: 0, count: totalDim)
        }

        let evalStart = evaluationCounter
        evaluationCounter += pop

        var candidates: [[Float]] = []
        candidates.reserveCapacity(pop)
        var paramsBatch: [ResolvedParams] = []
        paramsBatch.reserveCapacity(pop)
        for i in 0..<pop {
            var candidate: [Float] = []
            for j in 0..<totalDim {
                candidate.append(theta[j] + esConfig.sigma * candidateNoise[i][j])
            }
            candidates.append(candidate)
            let paramsVec = Array(candidate[0..<thetaParamsDim])
            paramsBatch.append(vectorToParams(paramsVec, space: paramSpace))
        }
        LeniaSignposts.end(candidateSetupSignpost)
        let candidateSetupMs = durationMs(candidateSetupStart.duration(to: ContinuousClock.now))

        let evaluation = evaluatePopulation(
            candidates: candidates,
            paramsBatch: paramsBatch,
            evaluationStart: evalStart
        )

        let fitnessStart = ContinuousClock.now
        let fitnessSignpost = LeniaSignposts.beginPhase("fitness")
        let fitnessValues = fitnessValues(from: evaluation.measurements)

        let safeFitnessValues = fitnessValues.map { fitness in
            fitness.isFinite ? fitness : -1e9
        }
        LeniaSignposts.end(fitnessSignpost)
        let fitnessMs = evaluation.measurementMs + durationMs(fitnessStart.duration(to: ContinuousClock.now))

        let optimizerStart = ContinuousClock.now
        let optimizerSignpost = LeniaSignposts.beginPhase("optimizer")
        let shaped = fitnessShaping(safeFitnessValues, mode: esConfig.fitnessShaping)

        // Compute gradient estimate: grad = (noise.T @ shaped) / (pop * sigma)
        var grad = [Float](repeating: 0.0, count: totalDim)
        for j in 0..<totalDim {
            var sum: Float = 0.0
            for i in 0..<pop {
                sum += candidateNoise[i][j] * shaped[i]
            }
            grad[j] = sum / (Float(pop) * esConfig.sigma)
        }

        // Update theta
        theta = optimizer.step(params: theta, grad: grad)

        let bestIndex = safeFitnessValues.enumerated().max(by: { $0.element < $1.element })?.offset ?? 0
        let bestFitness = safeFitnessValues[bestIndex]
        let meanFitness = safeFitnessValues.reduce(0, +) / Float(pop)
        let variance = safeFitnessValues.reduce(Float(0.0)) { partial, value in
            let diff = value - meanFitness
            return partial + diff * diff
        } / Float(pop)
        let fitnessStd = sqrt(max(variance, 0.0))
        LeniaSignposts.end(optimizerSignpost)
        let optimizerMs = durationMs(optimizerStart.duration(to: ContinuousClock.now))
        let totalMs = durationMs(generationStart.duration(to: ContinuousClock.now))

        return ESGenerationResult(
            bestFitness: bestFitness,
            meanFitness: meanFitness,
            fitnessStd: fitnessStd,
            bestCandidate: candidates[bestIndex],
            profile: ESGenerationProfile(
                candidateSetupMs: candidateSetupMs,
                kernelCompileMs: evaluation.kernelCompileMs,
                stateBuildMs: evaluation.stateBuildMs,
                fieldBuildMs: evaluation.fieldBuildMs,
                rolloutMs: evaluation.rolloutMs,
                fitnessMs: fitnessMs,
                optimizerMs: optimizerMs,
                totalMs: totalMs
            )
        )
    }

    public func getBestParams() -> ResolvedParams {
        let paramsVec = Array(theta[0..<thetaParamsDim])
        return vectorToParams(paramsVec, space: paramSpace)
    }

    public func sampleMAPElitesInitialCandidates(
        count: Int,
        sigma: Float,
        includeParent: Bool
    ) -> [[Float]] {
        guard count > 0 else { return [] }
        let totalDim = theta.count
        return (0..<count).map { index in
            if includeParent && index == 0 {
                return theta
            }
            return (0..<totalDim).map { dimension in
                theta[dimension] + sigma * gaussianSample(rng: &rng)
            }
        }
    }

    public func mapElitesCandidate(
        kernelParams: KernelParams?,
        initPatchValues: [Float]?
    ) throws -> [Float] {
        var candidate = kernelParams.map {
            paramsToVector(
                resolvedParams(from: $0, space: paramSpace, seed: runtimeConfig.params.seed),
                space: paramSpace
            )
        } ?? Array(theta[0..<thetaParamsDim])

        if initPatchDim > 0 {
            guard let initPatch = esConfig.initPatch, initPatch.enabled else {
                throw ConfigError.invalidConfig("Flow MAP-Elites init patch dimensions are active, but init_patch is missing.")
            }
            let values: [Float]
            if let initPatchValues {
                guard initPatchValues.count == initPatchDim else {
                    throw ConfigError.invalidConfig("seed init patch values count \(initPatchValues.count) does not match expected patch size \(initPatchDim).")
                }
                values = initPatchValues
            } else {
                values = Array(theta[thetaParamsDim..<theta.count]).map {
                    initPatch.valueLow + sigmoid($0) * (initPatch.valueHigh - initPatch.valueLow)
                }
            }
            candidate.reserveCapacity(theta.count)
            for value in values {
                let normalized = (value - initPatch.valueLow) / (initPatch.valueHigh - initPatch.valueLow)
                let clipped = max(1e-6, min(1.0 - 1e-6, normalized))
                candidate.append(logit(clipped))
            }
        } else if initPatchValues != nil {
            throw ConfigError.invalidConfig("seed init patch values require init_patch.enabled in the MAP-Elites config.")
        }

        guard candidate.count == theta.count else {
            throw ConfigError.invalidConfig("Flow MAP-Elites candidate dimension \(candidate.count) does not match expected dimension \(theta.count).")
        }
        return candidate
    }

    public func sampleMAPElitesInitialCandidates(
        anchors: [[Float]],
        count: Int,
        sigma: Float,
        includeParent: Bool
    ) throws -> [[Float]] {
        guard count > 0 else { return [] }
        guard !anchors.isEmpty else {
            return sampleMAPElitesInitialCandidates(count: count, sigma: sigma, includeParent: includeParent)
        }
        for (index, anchor) in anchors.enumerated() {
            guard anchor.count == theta.count else {
                throw ConfigError.invalidConfig("Flow MAP-Elites seed anchor \(index) has dimension \(anchor.count), expected \(theta.count).")
            }
        }
        return (0..<count).map { index in
            let anchor = anchors[index % anchors.count]
            if includeParent && index < anchors.count {
                return anchor
            }
            return anchor.map { value in
                value + sigma * gaussianSample(rng: &rng)
            }
        }
    }

    public func sampleMAPElitesChildren(
        parents: [[Float]],
        count: Int,
        sigma: Float,
        lineSigma: Float
    ) -> [[Float]] {
        guard count > 0 else { return [] }
        guard !parents.isEmpty else {
            return sampleMAPElitesInitialCandidates(count: count, sigma: sigma, includeParent: false)
        }
        let dimensions = parents[0].count
        return (0..<count).map { _ in
            let first = parents[Int.random(in: 0..<parents.count, using: &rng)]
            let second = parents[Int.random(in: 0..<parents.count, using: &rng)]
            return (0..<dimensions).map { dimension in
                let isotropic = sigma * gaussianSample(rng: &rng)
                let directional = lineSigma * gaussianSample(rng: &rng) * (second[dimension] - first[dimension])
                return first[dimension] + isotropic + directional
            }
        }
    }

    public func evaluateMAPElitesCandidates(
        _ candidates: [[Float]],
        descriptorNames: [String]
    ) throws -> [FlowMAPElitesCandidateEvaluation] {
        guard !candidates.isEmpty else { return [] }
        let evalStart = evaluationCounter
        evaluationCounter += candidates.count
        let paramsBatch = candidates.map { candidate in
            vectorToParams(Array(candidate[0..<thetaParamsDim]), space: paramSpace)
        }
        let evaluation = evaluatePopulation(
            candidates: candidates,
            paramsBatch: paramsBatch,
            evaluationStart: evalStart
        )
        let fitnesses = fitnessValues(from: evaluation.measurements)
        return try zip(zip(candidates, fitnesses), evaluation.measurements).map { pair, measurement in
            let (candidate, fitness) = pair
            var descriptors: [String: Float] = [:]
            for name in descriptorNames {
                guard let value = mapElitesDescriptorValue(
                    name: name,
                    measurement: measurement,
                    fitness: fitness
                ) else {
                    throw ConfigError.invalidConfig("Flow MAP-Elites descriptor '\(name)' is unavailable for objective '\(esConfig.fitness.objective)'.")
                }
                descriptors[name] = value
            }
            return FlowMAPElitesCandidateEvaluation(
                candidate: candidate,
                fitness: fitness,
                descriptors: descriptors
            )
        }
    }

    private func mapElitesDescriptorValue(
        name: String,
        measurement: CandidateMeasurement,
        fitness: Float
    ) -> Float? {
        switch name {
        case "fitness":
            return fitness
        case "coherent_transport":
            guard let displacement = transportDisplacementPixels(from: measurement),
                  let translatedShapeOverlap = measurement.translatedShapeOverlap else {
                return nil
            }
            return displacement * translatedShapeOverlap
        case "body_locomotion":
            guard let displacement = transportDisplacementPixels(from: measurement),
                  let translatedShapeOverlap = measurement.translatedShapeOverlap else {
                return nil
            }
            return bodyLocomotionScore(
                displacement: displacement,
                translatedShapeOverlap: translatedShapeOverlap,
                measurement: measurement
            )
        case "transport_displacement":
            return transportDisplacementPixels(from: measurement)
        case "translated_shape_overlap":
            return measurement.translatedShapeOverlap
        case "gyration":
            return measurement.gyration
        case "component_count":
            return measurement.componentCount
        case "largest_component_fraction":
            return measurement.largestComponentFraction
        case "largest_component_anisotropy":
            return measurement.largestComponentAnisotropy
        case "largest_component_solidity", "solidity":
            return measurement.largestComponentSolidity
        case "largest_component_mean_thickness", "thickness":
            return measurement.largestComponentMeanThickness
        case "largest_component_max_thickness":
            return measurement.largestComponentMaxThickness
        case "largest_component_filamentarity", "filamentarity":
            return measurement.largestComponentFilamentarity
        case "moment_density":
            return measurement.momentDensity
        case "occupied_fraction":
            return measurement.occupiedFraction
        case "mid_occupied_fraction":
            return measurement.midOccupiedFraction
        case "target_occupied_fraction":
            return measurement.targetOccupiedFraction
        case "occupied_growth":
            return measurement.occupiedGrowth
        case "moment_anisotropy":
            return measurement.momentAnisotropy
        default:
            return nil
        }
    }

    private func transportDisplacementPixels(from measurement: CandidateMeasurement) -> Float? {
        guard let mid = measurement.mid, mid.alive,
              let target = measurement.target, target.alive else {
            return nil
        }
        let dx = target.x - mid.x
        let dy = target.y - mid.y
        return sqrt(dx * dx + dy * dy) * Float(max(config.sx, config.sy))
    }

    public func evaluateCandidateForResearchExport(
        _ candidate: [Float],
        evaluationIndex: Int = 0
    ) -> ESEvaluatedCreatureExport {
        let paramsVec = Array(candidate[0..<thetaParamsDim])
        let params = vectorToParams(paramsVec, space: paramSpace)
        let patchValues = resolvedInitPatchValues(candidate)
        let initConfig = resolvedResearchInitConfig(patchValues: patchValues)

        let sim = FlowLeniaBatched(
            config: config,
            kernels: compilePopulationKernels(
                paramsBatch: [params],
                config: config,
                c0: runtimeConfig.c0,
                c1: runtimeConfig.c1
            )
        )

        var ABatch = MLX.stacked([
            patchValues.map(buildStateFromPatch) ?? buildInitialState(seed: runtimeConfig.initSeed)
        ])
        let chemFieldBatch = buildChemotaxisFieldBatch(startIndex: evaluationIndex, count: 1)
        let obstacleFieldBatch = buildObstacleFieldBatch(startIndex: evaluationIndex, count: 1)
        sim.wallPotential = obstacleFieldBatch.map(buildObstaclePotential)

        var massHistory: [Float] = []
        var occupancyHistory: [Float] = []
        var varianceHistory: [Float] = []
        var energyHistory: [Float] = []
        var centerXHistory: [Float] = []
        var centerYHistory: [Float] = []
        var aliveHistory: [Bool] = []
        let sequenceStepSet = Set(templateSequenceSteps())
        var sequenceMassMaps: [MLXArray] = []
        var sequenceCenterSnapshots: [[CenterSnapshot]] = []
        let requirements = objectiveRequirements()
        let usesTranslatedShapeOverlap = objectiveUsesTranslatedShapeOverlap(requirements.objective)
        var midMassBatch: MassBatchCPU? = nil
        var targetMassBatch: MassBatchCPU? = nil

        func applyFields() {
            if let field = chemFieldBatch, let chemotaxis = runtimeConfig.chemotaxis {
                ABatch = applyExternalFieldBatch(ABatch, field: field, channelIndex: chemotaxis.channel_index)
            }
            if let field = obstacleFieldBatch, let obstacleConfig = esConfig.obstacleField {
                ABatch = applyExternalFieldBatch(ABatch, field: field, channelIndex: obstacleConfig.channelIndex)
            }
        }

        func record(step: Int) {
            let massMap = evolutionMassMapBatch(ABatch, excludedChannels: excludedMassChannels)
            let total = massMap.sum(axes: [1, 2])
            let occupancy = MLX.greater(massMap, MLXArray(Float(1e-3))).asType(.float32).mean(axes: [1, 2])
            let meanMass = massMap.mean(axes: [1, 2])
            let centered = massMap - meanMass.expandedDimensions(axes: [1, 2])
            let variance = (centered * centered).mean(axes: [1, 2])
            let energy = (massMap * massMap).mean(axes: [1, 2])
            let com = centerOfMassBatchDevice(ABatch)
            eval(total, occupancy, variance, energy, com.total, com.x, com.y)

            let totalCPU = total.asArray(Float.self)[0]
            let occupancyCPU = occupancy.asArray(Float.self)[0]
            let varianceCPU = variance.asArray(Float.self)[0]
            let energyCPU = energy.asArray(Float.self)[0]
            let alive = com.total.asArray(Float.self)[0] > 0
            let centerX = com.x.asArray(Float.self)[0] / Float(config.sx) - 0.5
            let centerY = com.y.asArray(Float.self)[0] / Float(config.sy) - 0.5

            massHistory.append(totalCPU)
            occupancyHistory.append(occupancyCPU)
            varianceHistory.append(varianceCPU)
            energyHistory.append(energyCPU)
            centerXHistory.append(centerX)
            centerYHistory.append(centerY)
            aliveHistory.append(alive)

            if sequenceStepSet.contains(step) {
                sequenceMassMaps.append(massMap)
                if esConfig.fitness.usesTrajectoryMetrics {
                    sequenceCenterSnapshots.append([CenterSnapshot(alive: alive, x: centerX, y: centerY)])
                }
            }
        }

        applyFields()
        record(step: 0)
        for step in 1...esConfig.steps {
            applyFields()
            ABatch = sim.step(ABatch)
            record(step: step)
            if usesTranslatedShapeOverlap && step == requirements.midStep {
                midMassBatch = materializeMassBatch(evolutionMassMapBatch(ABatch, excludedChannels: excludedMassChannels))
            }
            if usesTranslatedShapeOverlap && step == requirements.targetStep {
                targetMassBatch = materializeMassBatch(evolutionMassMapBatch(ABatch, excludedChannels: excludedMassChannels))
            }
        }

        let speeds = evolutionSpeeds(
            centerXHistory: centerXHistory,
            centerYHistory: centerYHistory,
            aliveHistory: aliveHistory
        )
        let velocityX = speeds.last?.dx ?? 0
        let velocityY = speeds.last?.dy ?? 0
        let lastSpeed = speeds.last?.speed ?? 0
        let heading = lastSpeed > 0 ? atan2(velocityY, velocityX) : 0
        let pathLength = speeds.reduce(Float(0)) { $0 + $1.speed }
        let displacement = evolutionDisplacement(
            centerXHistory: centerXHistory,
            centerYHistory: centerYHistory,
            aliveHistory: aliveHistory
        )
        let speedValues = speeds.map(\.speed)
        let massMean = evolutionMean(massHistory)
        let massStd = evolutionStd(massHistory, mean: massMean)
        let morphologyValues = morphologyMeasurements(from: ABatch, includeDiagnostics: true)
        let gyration = computeGyrationBatch(ABatch)[0]

        let chemotaxisScore: Float?
        if esConfig.fitness.objective == "chemotaxis", let field = chemFieldBatch {
            let massMap = evolutionMassMapBatch(ABatch, excludedChannels: excludedMassChannels)
            let numerator = (massMap * field).sum(axes: [1, 2])
            let denominator = massMap.sum(axes: [1, 2])
            eval(numerator, denominator)
            chemotaxisScore = numerator.asArray(Float.self)[0] / max(denominator.asArray(Float.self)[0], 1e-6)
        } else {
            chemotaxisScore = nil
        }
        let translatedShapeOverlap: Float?
        let transportDisplacement: Float?
        if usesTranslatedShapeOverlap,
           let midMassBatch,
           let targetMassBatch {
            let mid = centerSnapshot(
                centerXHistory: centerXHistory,
                centerYHistory: centerYHistory,
                aliveHistory: aliveHistory,
                index: requirements.midStep
            )
            let target = centerSnapshot(
                centerXHistory: centerXHistory,
                centerYHistory: centerYHistory,
                aliveHistory: aliveHistory,
                index: requirements.targetStep
            )
            if mid.alive && target.alive {
                let dx = target.x - mid.x
                let dy = target.y - mid.y
                transportDisplacement = sqrt(dx * dx + dy * dy) * Float(max(config.sx, config.sy))
            } else {
                transportDisplacement = 0
            }
            translatedShapeOverlap = translatedShapeOverlapBatch(
                source: midMassBatch,
                target: targetMassBatch,
                sourceCenters: BatchCenterOfMassCPU(
                    alive: [mid.alive ? 1.0 : 0.0],
                    x: [mid.x],
                    y: [mid.y]
                ),
                targetCenters: BatchCenterOfMassCPU(
                    alive: [target.alive ? 1.0 : 0.0],
                    x: [target.x],
                    y: [target.y]
                ),
                threshold: esConfig.fitness.morphologyThreshold ?? 0.03,
                useTorus: runtimeConfig.border == "torus"
            ).first
        } else {
            translatedShapeOverlap = nil
            transportDisplacement = nil
        }
        let midOccupiedFraction = midMassBatch.flatMap {
            occupiedFractionBatch(materialized: $0, threshold: esConfig.fitness.morphologyThreshold ?? 0.03).first
        }
        let targetOccupiedFraction = targetMassBatch.flatMap {
            occupiedFractionBatch(materialized: $0, threshold: esConfig.fitness.morphologyThreshold ?? 0.03).first
        }
        let occupiedGrowthValue = occupiedGrowth(mid: midOccupiedFraction, target: targetOccupiedFraction)
        let templateSequenceValues = templateSequenceMetricValues(from: sequenceMassMaps)
        let orientationPhaseMotion = orientationPhaseMotionValues(from: sequenceMassMaps)
        let angularPhaseMotion = angularPhaseMotionValues(from: sequenceMassMaps)
        let sectorTransport = sectorTransportValues(from: sequenceMassMaps)
        let trajectoryValues = trajectoryMetricValues(
            from: sequenceCenterSnapshots,
            stepSpan: trajectoryMetricStepSpan()
        )
        let candidateMeasurement = CandidateMeasurement(
            initial: centerSnapshot(
                centerXHistory: centerXHistory,
                centerYHistory: centerYHistory,
                aliveHistory: aliveHistory,
                index: 0
            ),
            mid: requirements.usesMidCenter
                ? centerSnapshot(
                    centerXHistory: centerXHistory,
                    centerYHistory: centerYHistory,
                    aliveHistory: aliveHistory,
                    index: requirements.midStep
                )
                : nil,
            target: requirements.usesCenterOfMass
                ? centerSnapshot(
                    centerXHistory: centerXHistory,
                    centerYHistory: centerYHistory,
                    aliveHistory: aliveHistory,
                    index: requirements.targetStep
                )
                : nil,
            translatedShapeOverlap: translatedShapeOverlap,
            midOccupiedFraction: midOccupiedFraction,
            targetOccupiedFraction: targetOccupiedFraction,
            occupiedGrowth: occupiedGrowthValue,
            gyration: gyration,
            componentCount: morphologyValues?.componentCount?.first,
            largestComponentFraction: morphologyValues?.largestComponentFraction?.first,
            largestComponentAnisotropy: morphologyValues?.largestComponentAnisotropy?.first,
            componentMassEvenness: morphologyValues?.componentMassEvenness?.first,
            momentMass: morphologyValues?.momentMass?.first,
            largestComponentSolidity: morphologyValues?.largestComponentSolidity?.first,
            largestComponentMeanThickness: morphologyValues?.largestComponentMeanThickness?.first,
            largestComponentMaxThickness: morphologyValues?.largestComponentMaxThickness?.first,
            largestComponentFilamentarity: morphologyValues?.largestComponentFilamentarity?.first,
            momentDensity: morphologyValues?.momentDensity?.first,
            occupiedFraction: morphologyValues?.occupiedFraction?.first,
            momentAnisotropy: morphologyValues?.momentAnisotropy?.first,
            internalStripe: morphologyValues?.internalStripe?.first,
            orientedRidge: morphologyValues?.orientedRidge?.first,
            largestComponentInternalStripe: morphologyValues?.largestComponentInternalStripe?.first,
            largestComponentOrientedRidge: morphologyValues?.largestComponentOrientedRidge?.first,
            templateSimilarity: morphologyValues?.templateSimilarity?.first,
            templateSequenceSimilarity: templateSequenceValues.similarity?.first,
            templateSequenceMassMismatch: templateSequenceValues.massMismatch?.first,
            templateSequenceSupportMismatch: templateSequenceValues.supportMismatch?.first,
            templateSequenceChangeMismatch: templateSequenceValues.changeMismatch?.first,
            templateSequenceDeltaSimilarity: templateSequenceValues.deltaSimilarity?.first,
            templateSequenceSignedDeltaSimilarity: templateSequenceValues.signedDeltaSimilarity?.first,
            orientationPhaseMotion: orientationPhaseMotion?.first,
            angularPhaseMotion: angularPhaseMotion?.first,
            sectorTransport: sectorTransport?.first,
            trajectoryPathLength: trajectoryValues.pathLength?.first,
            trajectoryDisplacement: trajectoryValues.displacement?.first,
            movementEfficiency: trajectoryValues.movementEfficiency?.first,
            centerVelocity: trajectoryValues.centerVelocity?.first,
            chemotaxisScore: chemotaxisScore
        )
        let fitness = fitnessValue(from: candidateMeasurement)
        let coherentTransport: Float?
        if let transportDisplacement, let translatedShapeOverlap {
            coherentTransport = transportDisplacement * translatedShapeOverlap
        } else {
            coherentTransport = nil
        }
        let bodyLocomotion: Float?
        if let transportDisplacement, let translatedShapeOverlap {
            bodyLocomotion = bodyLocomotionScore(
                displacement: transportDisplacement,
                translatedShapeOverlap: translatedShapeOverlap,
                measurement: candidateMeasurement
            )
        } else {
            bodyLocomotion = nil
        }
        let metrics = SimulationMetrics(
            massMean: massMean,
            massStd: massStd,
            massMin: massHistory.min() ?? 0,
            massMax: massHistory.max() ?? 0,
            occupancyMean: evolutionMean(occupancyHistory),
            varianceMean: evolutionMean(varianceHistory),
            energyMean: evolutionMean(energyHistory),
            speedMean: evolutionMean(speedValues),
            pathLength: pathLength,
            displacement: displacement,
            sampleCount: massHistory.count,
            speedCount: speedValues.count,
            gyration: gyration,
            centerVelocity: lastSpeed,
            velocityX: velocityX,
            velocityY: velocityY,
            headingRad: heading,
            isStable: evolutionIsStable(
                massMean: massMean,
                massStd: massStd,
                finalMass: massHistory.last ?? 0
            ),
            momentMass: morphologyValues?.momentMass?.first,
            momentDensity: morphologyValues?.momentDensity?.first,
            momentAnisotropy: morphologyValues?.momentAnisotropy?.first,
            occupiedFraction: morphologyValues?.occupiedFraction?.first,
            midOccupiedFraction: midOccupiedFraction,
            targetOccupiedFraction: targetOccupiedFraction,
            occupiedGrowth: occupiedGrowthValue,
            componentCount: morphologyValues?.componentCount?.first,
            largestComponentFraction: morphologyValues?.largestComponentFraction?.first,
            largestComponentAnisotropy: morphologyValues?.largestComponentAnisotropy?.first,
            largestComponentInternalStripe: morphologyValues?.largestComponentInternalStripe?.first,
            largestComponentOrientedRidge: morphologyValues?.largestComponentOrientedRidge?.first,
            largestComponentSolidity: morphologyValues?.largestComponentSolidity?.first,
            largestComponentMeanThickness: morphologyValues?.largestComponentMeanThickness?.first,
            largestComponentMaxThickness: morphologyValues?.largestComponentMaxThickness?.first,
            largestComponentFilamentarity: morphologyValues?.largestComponentFilamentarity?.first,
            transportDisplacement: transportDisplacement,
            translatedShapeOverlap: translatedShapeOverlap,
            coherentTransport: coherentTransport,
            bodyLocomotion: bodyLocomotion
        )

        let morphologyGuardFailed = esConfig.fitness.usesMorphologyGuard && failsMorphologyGuard(candidateMeasurement)
        let resultData = materializeReplayResultData(
            seed: evaluationIndex,
            initSeed: initConfig.seed,
            backend: runtimeConfig.backend.rawValue,
            implementation: runtimeConfig.implementation,
            initialConditionFamily: morphospaceInitialConditionFamily(initConfig),
            descriptorBundle: nil,
            score: fitness,
            scoreWeights: ["fitness": 1.0],
            filtersPassed: fitness.isFinite,
            filters: [:],
            metrics: metrics,
            params: params.toKernelParams()
        )

        let finalMorphology = esConfig.fitness.usesMorphologyMetrics
            ? ESFinalMorphologyDiagnostics(
                threshold: esConfig.fitness.morphologyThreshold ?? 0.03,
                guardFailed: morphologyGuardFailed,
                componentCount: candidateMeasurement.componentCount,
                largestComponentFraction: candidateMeasurement.largestComponentFraction,
                largestComponentAnisotropy: candidateMeasurement.largestComponentAnisotropy,
                componentMassEvenness: candidateMeasurement.componentMassEvenness,
                momentMass: candidateMeasurement.momentMass,
                momentDensity: candidateMeasurement.momentDensity,
                momentAnisotropy: candidateMeasurement.momentAnisotropy,
                internalStripe: candidateMeasurement.internalStripe,
                orientedRidge: candidateMeasurement.orientedRidge,
                largestComponentInternalStripe: candidateMeasurement.largestComponentInternalStripe,
                largestComponentOrientedRidge: candidateMeasurement.largestComponentOrientedRidge,
                templateSimilarity: candidateMeasurement.templateSimilarity
            )
            : nil

        return ESEvaluatedCreatureExport(
            initConfig: initConfig,
            initPatchValues: patchValues,
            fitness: fitness,
            finalMorphology: finalMorphology,
            resultData: resultData
        )
    }

    private func resolvedInitPatchValues(_ candidate: [Float]) -> [Float]? {
        guard initPatchDim > 0 else { return nil }
        let patchVec = Array(candidate[thetaParamsDim...])
        return patchVec.map { val -> Float in
            guard let initPatch = esConfig.initPatch else { return 0 }
            let sig = sigmoid(val)
            return initPatch.valueLow + sig * (initPatch.valueHigh - initPatch.valueLow)
        }
    }

    private func resolvedResearchInitConfig(patchValues: [Float]?) -> InitConfig {
        if let initPatch = esConfig.initPatch, initPatch.enabled {
            if let patchValues {
                let statePatch = explicitInitStatePatch(
                    from: patchValues,
                    initPatch: initPatch
                )
                let parameterPatches = runtimeConfig.parameterEmbedding.enabled
                    ? [PatchConfig(center: initPatch.center, size: initPatch.size)]
                    : []
                return InitConfig(
                    seed: runtimeConfig.initSeed,
                    patches: parameterPatches,
                    a_uniform: UniformRange(low: 0, high: 0),
                    p_uniform: runtimeConfig.pUniform,
                    state_patch: statePatch,
                    p_state_patch: runtimeConfig.paramPatch
                )
            }
            return InitConfig(
                seed: runtimeConfig.initSeed,
                patches: [PatchConfig(center: initPatch.center, size: initPatch.size)],
                a_uniform: UniformRange(low: initPatch.valueLow, high: initPatch.valueHigh),
                p_uniform: nil
            )
        }
        let patches: [PatchConfig]
        if runtimeConfig.statePatch != nil {
            patches = runtimeConfig.patches
        } else if runtimeConfig.patches.isEmpty {
            patches = [PatchConfig(center: [config.sx / 2, config.sy / 2], size: 40)]
        } else {
            patches = runtimeConfig.patches
        }
        return InitConfig(
            seed: runtimeConfig.initSeed,
            patches: patches,
            a_uniform: runtimeConfig.aUniform,
            p_uniform: runtimeConfig.pUniform,
            state_patch: runtimeConfig.statePatch,
            p_state_patch: runtimeConfig.paramPatch
        )
    }

    private func explicitInitStatePatch(
        from patchValues: [Float],
        initPatch: InitPatchConfig
    ) -> InitStatePatchConfig {
        let size = initPatch.size
        var values = [Float](repeating: 0, count: size * size * config.channels)
        var patchIndex = 0
        for x in 0..<size {
            for y in 0..<size {
                for channel in creatureChannels {
                    let valueIndex = (x * size + y) * config.channels + channel
                    if valueIndex < values.count && patchIndex < patchValues.count {
                        values[valueIndex] = patchValues[patchIndex]
                    }
                    patchIndex += 1
                }
            }
        }
        return InitStatePatchConfig(
            center: initPatch.center,
            width: size,
            height: size,
            channels: config.channels,
            values: values
        )
    }

}

public struct ESEvaluatedCreatureExport: Sendable {
    public let initConfig: InitConfig
    public let initPatchValues: [Float]?
    public let fitness: Float
    public let finalMorphology: ESFinalMorphologyDiagnostics?
    public let resultData: SimulationResultData
}

public struct ESFinalMorphologyDiagnostics: Sendable {
    public let threshold: Float
    public let guardFailed: Bool
    public let componentCount: Float?
    public let largestComponentFraction: Float?
    public let largestComponentAnisotropy: Float?
    public let componentMassEvenness: Float?
    public let momentMass: Float?
    public let momentDensity: Float?
    public let momentAnisotropy: Float?
    public let internalStripe: Float?
    public let orientedRidge: Float?
    public let largestComponentInternalStripe: Float?
    public let largestComponentOrientedRidge: Float?
    public let templateSimilarity: Float?

    public var metadataPayload: [String: Any] {
        var payload: [String: Any] = [
            "version": 1,
            "threshold": threshold,
            "guard_failed": guardFailed,
        ]
        func add(_ key: String, _ value: Float?) {
            if let value {
                payload[key] = value
            }
        }
        add("component_count", componentCount)
        add("largest_component_fraction", largestComponentFraction)
        add("largest_component_anisotropy", largestComponentAnisotropy)
        add("component_mass_evenness", componentMassEvenness)
        add("moment_mass", momentMass)
        add("moment_density", momentDensity)
        add("moment_anisotropy", momentAnisotropy)
        add("internal_stripe", internalStripe)
        add("oriented_ridge", orientedRidge)
        add("largest_component_internal_stripe", largestComponentInternalStripe)
        add("largest_component_oriented_ridge", largestComponentOrientedRidge)
        add("template_similarity", templateSimilarity)
        return payload
    }
}

private func evolutionMean(_ values: [Float]) -> Float {
    guard !values.isEmpty else { return 0 }
    return values.reduce(0, +) / Float(values.count)
}

private func evolutionStd(_ values: [Float], mean: Float) -> Float {
    guard !values.isEmpty else { return 0 }
    let variance = values.reduce(Float(0)) { partial, value in
        let diff = value - mean
        return partial + diff * diff
    } / Float(values.count)
    return sqrt(max(variance, 0))
}

private func evolutionDisplacement(
    centerXHistory: [Float],
    centerYHistory: [Float],
    aliveHistory: [Bool]
) -> Float {
    guard let firstIndex = aliveHistory.firstIndex(of: true),
          let lastIndex = aliveHistory.lastIndex(of: true) else {
        return 0
    }
    let dx = centerXHistory[lastIndex] - centerXHistory[firstIndex]
    let dy = centerYHistory[lastIndex] - centerYHistory[firstIndex]
    return sqrt(dx * dx + dy * dy)
}

private func movementEfficiency(pathLength: Float, displacement: Float) -> Float {
    guard pathLength > 1e-6 else { return 0 }
    return max(0, min(1, displacement / pathLength))
}

private func evolutionSpeeds(
    centerXHistory: [Float],
    centerYHistory: [Float],
    aliveHistory: [Bool]
) -> [(dx: Float, dy: Float, speed: Float)] {
    guard centerXHistory.count == centerYHistory.count, centerXHistory.count == aliveHistory.count else {
        return []
    }
    guard centerXHistory.count > 1 else { return [] }
    return (1..<centerXHistory.count).compactMap { index in
        guard aliveHistory[index - 1], aliveHistory[index] else { return nil }
        let dx = centerXHistory[index] - centerXHistory[index - 1]
        let dy = centerYHistory[index] - centerYHistory[index - 1]
        return (dx, dy, sqrt(dx * dx + dy * dy))
    }
}

private func evolutionIsStable(massMean: Float, massStd: Float, finalMass: Float) -> Bool {
    finalMass > 0 && massMean > 0 && massStd <= max(0.1 * massMean, 1e-6)
}

// Load ES config from file

public func loadESConfig(path: String) throws -> ESConfig {
    let url = URL(fileURLWithPath: path)
    let data = try Data(contentsOf: url)
    return try JSONDecoder().decode(ESConfig.self, from: data)
}

public func loadFlowMAPElitesConfig(path: String) throws -> FlowMAPElitesConfig {
    let url = URL(fileURLWithPath: path)
    let data = try Data(contentsOf: url)
    return try JSONDecoder().decode(FlowMAPElitesConfig.self, from: data)
}

// Extract param ranges from base config

public func extractRangesFromConfig(_ config: LeniaBaseConfig) throws -> [String: (Float, Float)] {
    guard config.params.mode == "random",
          let ranges = config.params.ranges else {
        throw NSError(domain: "Evolution", code: 1,
                      userInfo: [NSLocalizedDescriptionKey: "params.mode must be 'random' with ranges"])
    }

    return [
        "r": (ranges.r[0], ranges.r[1]),
        "b": (ranges.b[0], ranges.b[1]),
        "w": (ranges.w[0], ranges.w[1]),
        "a": (ranges.a[0], ranges.a[1]),
        "m": (ranges.m[0], ranges.m[1]),
        "s": (ranges.s[0], ranges.s[1]),
        "h": (ranges.h[0], ranges.h[1]),
        "R": (ranges.R[0], ranges.R[1])
    ]
}

// History entry for logging

public struct ESGenerationResult {
    public let bestFitness: Float
    public let meanFitness: Float
    public let fitnessStd: Float
    public let bestCandidate: [Float]
    public let profile: ESGenerationProfile

    public init(
        bestFitness: Float,
        meanFitness: Float,
        fitnessStd: Float,
        bestCandidate: [Float],
        profile: ESGenerationProfile
    ) {
        self.bestFitness = bestFitness
        self.meanFitness = meanFitness
        self.fitnessStd = fitnessStd
        self.bestCandidate = bestCandidate
        self.profile = profile
    }
}

public struct ESGenerationProfile: Sendable {
    public let candidateSetupMs: Double
    public let kernelCompileMs: Double
    public let stateBuildMs: Double
    public let fieldBuildMs: Double
    public let rolloutMs: Double
    public let fitnessMs: Double
    public let optimizerMs: Double
    public let totalMs: Double

    public init(
        candidateSetupMs: Double,
        kernelCompileMs: Double,
        stateBuildMs: Double,
        fieldBuildMs: Double,
        rolloutMs: Double,
        fitnessMs: Double,
        optimizerMs: Double,
        totalMs: Double
    ) {
        self.candidateSetupMs = candidateSetupMs
        self.kernelCompileMs = kernelCompileMs
        self.stateBuildMs = stateBuildMs
        self.fieldBuildMs = fieldBuildMs
        self.rolloutMs = rolloutMs
        self.fitnessMs = fitnessMs
        self.optimizerMs = optimizerMs
        self.totalMs = totalMs
    }
}

public struct ESHistoryEntry: Codable {
    public let generation: Int
    public let fitnessMean: Float
    public let fitnessStd: Float
    public let fitnessBest: Float
    public let fitnessShaping: String
    public let generationWallMs: Double?
    public let candidateEvalPerSecond: Double?
    public let simStepsPerSecond: Double?
    public let candidateSetupMs: Double?
    public let kernelCompileMs: Double?
    public let stateBuildMs: Double?
    public let fieldBuildMs: Double?
    public let rolloutMs: Double?
    public let fitnessMs: Double?
    public let optimizerMs: Double?

    enum CodingKeys: String, CodingKey {
        case generation
        case fitnessMean = "fitness_mean"
        case fitnessStd = "fitness_std"
        case fitnessBest = "fitness_best"
        case fitnessShaping = "fitness_shaping"
        case generationWallMs = "generation_wall_ms"
        case candidateEvalPerSecond = "candidate_eval_per_second"
        case simStepsPerSecond = "sim_steps_per_second"
        case candidateSetupMs = "candidate_setup_ms"
        case kernelCompileMs = "kernel_compile_ms"
        case stateBuildMs = "state_build_ms"
        case fieldBuildMs = "field_build_ms"
        case rolloutMs = "rollout_ms"
        case fitnessMs = "fitness_ms"
        case optimizerMs = "optimizer_ms"
    }

    public init(
        generation: Int,
        fitnessMean: Float,
        fitnessStd: Float,
        fitnessBest: Float,
        fitnessShaping: String,
        generationWallMs: Double? = nil,
        candidateEvalPerSecond: Double? = nil,
        simStepsPerSecond: Double? = nil,
        candidateSetupMs: Double? = nil,
        kernelCompileMs: Double? = nil,
        stateBuildMs: Double? = nil,
        fieldBuildMs: Double? = nil,
        rolloutMs: Double? = nil,
        fitnessMs: Double? = nil,
        optimizerMs: Double? = nil
    ) {
        self.generation = generation
        self.fitnessMean = fitnessMean
        self.fitnessStd = fitnessStd
        self.fitnessBest = fitnessBest
        self.fitnessShaping = fitnessShaping
        self.generationWallMs = generationWallMs
        self.candidateEvalPerSecond = candidateEvalPerSecond
        self.simStepsPerSecond = simStepsPerSecond
        self.candidateSetupMs = candidateSetupMs
        self.kernelCompileMs = kernelCompileMs
        self.stateBuildMs = stateBuildMs
        self.fieldBuildMs = fieldBuildMs
        self.rolloutMs = rolloutMs
        self.fitnessMs = fitnessMs
        self.optimizerMs = optimizerMs
    }
}

public struct ESBestResult: Codable {
    public let generation: Int
    public let fitness: Float
    public let params: KernelParams

    public init(generation: Int, fitness: Float, params: KernelParams) {
        self.generation = generation
        self.fitness = fitness
        self.params = params
    }
}

extension EvolutionEngine {
    func benchmarkRolloutStageTimings() -> FlowSandboxMetalStageTimings? {
        guard runtimeConfig.backend == .metalFull else {
            return nil
        }

        let totalDim = theta.count
        let pop = esConfig.population
        var localRng = rng
        let noise = sampleOpenESNoise(
            population: pop,
            dimensions: totalDim,
            rng: &localRng
        )

        var candidates: [[Float]] = []
        candidates.reserveCapacity(pop)
        var paramsBatch: [ResolvedParams] = []
        paramsBatch.reserveCapacity(pop)
        for i in 0..<pop {
            var candidate: [Float] = []
            for j in 0..<totalDim {
                candidate.append(theta[j] + esConfig.sigma * noise[i][j])
            }
            candidates.append(candidate)
            let paramsVec = Array(candidate[0..<thetaParamsDim])
            paramsBatch.append(vectorToParams(paramsVec, space: paramSpace))
        }

        let runner = reusableMetalFullPopulationRunner(
            kernels: compilePopulationKernels(
                paramsBatch: paramsBatch,
                config: config,
                c0: runtimeConfig.c0,
                c1: runtimeConfig.c1
            )
        )
        runner.setState(
            mass: buildStateBatch(candidates),
            params: buildConstantParameterFieldBatch(paramsBatch.map(\.h))
        )

        let preProfileSteps = min(max(esConfig.steps / 4, 0), max(esConfig.steps - 1, 0))
        if preProfileSteps > 0 {
            runner.step(count: preProfileSteps)
        }
        return runner.profileCurrentStep()
    }
}

public struct EvolutionBenchmarkResult: Sendable {
    public let backend: FlowLeniaComputeBackend
    public let gridSize: Int
    public let steps: Int
    public let population: Int
    public let duration: TimeInterval
    public let candidatesPerSecond: Double
    public let simStepsPerSecond: Double
    public let profile: ESGenerationProfile
    public let stageTimings: FlowSandboxMetalStageTimings?

    public init(
        backend: FlowLeniaComputeBackend,
        gridSize: Int,
        steps: Int,
        population: Int,
        duration: TimeInterval,
        candidatesPerSecond: Double,
        simStepsPerSecond: Double,
        profile: ESGenerationProfile,
        stageTimings: FlowSandboxMetalStageTimings? = nil
    ) {
        self.backend = backend
        self.gridSize = gridSize
        self.steps = steps
        self.population = population
        self.duration = duration
        self.candidatesPerSecond = candidatesPerSecond
        self.simStepsPerSecond = simStepsPerSecond
        self.profile = profile
        self.stageTimings = stageTimings
    }
}

public func benchmarkEvolutionEngineBackend(
    gridSize: Int,
    population: Int,
    steps: Int,
    params: ResolvedParams,
    backend: FlowLeniaComputeBackend,
    warmupRuns: Int = 1
) -> EvolutionBenchmarkResult {
    guard population > 0, population % 2 == 0 else {
        preconditionFailure("Evolution benchmark requires an even, positive population.")
    }

    let runtimeConfig = flowLeniaBenchmarkRuntimeConfig(
        gridSize: gridSize,
        steps: steps,
        params: params,
        backend: backend
    )
    let esConfig = ESConfig(
        outputDir: "/tmp/lenia-evolution-benchmark",
        generations: 1,
        population: population,
        sigma: 0.05,
        learningRate: 0.03,
        seed: 17,
        steps: steps,
        fitness: FitnessConfig(
            objective: "directed_motion",
            targetStep: max(1, steps),
            angleThreshold: 1.0,
            gyrationPenalty: 0.01
        ),
        fitnessShaping: "centered_rank",
        includeParent: nil,
        initPatch: nil,
        initialInitPatchValues: nil,
        paramRanges: nil,
        obstacleField: nil
    )
    let engine = EvolutionEngine(
        runtimeConfig: runtimeConfig,
        esConfig: esConfig,
        ranges: flowLeniaBenchmarkEvolutionRanges()
    )
    for generation in 0..<max(warmupRuns, 0) {
        _ = engine.runGeneration(gen: generation)
    }

    let measuredGeneration = max(warmupRuns, 0)
    let stageTimings = backend == .metalFull ? engine.benchmarkRolloutStageTimings() : nil
    let start = Date()
    let result = engine.runGeneration(gen: measuredGeneration)
    let duration = Date().timeIntervalSince(start)
    return EvolutionBenchmarkResult(
        backend: backend,
        gridSize: gridSize,
        steps: steps,
        population: population,
        duration: duration,
        candidatesPerSecond: Double(population) / duration,
        simStepsPerSecond: Double(population * steps) / duration,
        profile: result.profile,
        stageTimings: stageTimings
    )
}
