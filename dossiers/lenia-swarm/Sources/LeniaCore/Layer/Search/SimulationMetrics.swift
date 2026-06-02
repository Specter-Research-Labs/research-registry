import Foundation

public struct SimulationMetrics: Codable, Sendable {
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
    public let complexityMean: Float?
    public let complexityTargetScore: Float?
    public let complexityScales: [Float]?
    public let activityEacMean: Float?
    public let activityEanMean: Float?
    public let activityDiversityMean: Float?
    public let activitySpeciesMean: Float?
    public let survivalTracked: Bool
    public let survivalSteps: Int?
    public let foodInitialMass: Float?
    public let foodFinalMass: Float?
    public let foodConsumed: Float?
    public let hu1: Float?
    public let hu2: Float?
    public let hu3: Float?
    public let hu4: Float?
    public let hu5: Float?
    public let hu6: Float?
    public let hu7: Float?
    public let flusser1: Float?
    public let flusser2: Float?
    public let flusser3: Float?
    public let flusser4: Float?
    public let momentMass: Float?
    public let momentVolume: Float?
    public let momentDensity: Float?
    public let momentAnisotropy: Float?
    public let occupiedFraction: Float?
    public let midOccupiedFraction: Float?
    public let targetOccupiedFraction: Float?
    public let occupiedGrowth: Float?
    public let componentCount: Float?
    public let largestComponentFraction: Float?
    public let largestComponentAnisotropy: Float?
    public let largestComponentInternalStripe: Float?
    public let largestComponentOrientedRidge: Float?
    public let largestComponentSolidity: Float?
    public let largestComponentMeanThickness: Float?
    public let largestComponentMaxThickness: Float?
    public let largestComponentFilamentarity: Float?
    public let transportDisplacement: Float?
    public let translatedShapeOverlap: Float?
    public let coherentTransport: Float?
    public let bodyLocomotion: Float?

    enum CodingKeys: String, CodingKey {
        case massMean = "mass_mean"
        case massStd = "mass_std"
        case massMin = "mass_min"
        case massMax = "mass_max"
        case occupancyMean = "occupancy_mean"
        case varianceMean = "variance_mean"
        case energyMean = "energy_mean"
        case speedMean = "speed_mean"
        case pathLength = "path_length"
        case displacement
        case sampleCount = "sample_count"
        case speedCount = "speed_count"
        case gyration
        case centerVelocity = "center_velocity"
        case velocityX = "velocity_x"
        case velocityY = "velocity_y"
        case headingRad = "heading_rad"
        case isStable = "is_stable"
        case complexityMean = "complexity_mean"
        case complexityTargetScore = "complexity_target_score"
        case complexityScales = "complexity_scales"
        case activityEacMean = "activity_eac_mean"
        case activityEanMean = "activity_ean_mean"
        case activityDiversityMean = "activity_diversity_mean"
        case activitySpeciesMean = "activity_species_mean"
        case survivalTracked = "survival_tracked"
        case survivalSteps = "survival_steps"
        case foodInitialMass = "food_initial_mass"
        case foodFinalMass = "food_final_mass"
        case foodConsumed = "food_consumed"
        case hu1, hu2, hu3, hu4, hu5, hu6, hu7
        case flusser1, flusser2, flusser3, flusser4
        case momentMass = "moment_mass"
        case momentVolume = "moment_volume"
        case momentDensity = "moment_density"
        case momentAnisotropy = "moment_anisotropy"
        case occupiedFraction = "occupied_fraction"
        case midOccupiedFraction = "mid_occupied_fraction"
        case targetOccupiedFraction = "target_occupied_fraction"
        case occupiedGrowth = "occupied_growth"
        case componentCount = "component_count"
        case largestComponentFraction = "largest_component_fraction"
        case largestComponentAnisotropy = "largest_component_anisotropy"
        case largestComponentInternalStripe = "largest_component_internal_stripe"
        case largestComponentOrientedRidge = "largest_component_oriented_ridge"
        case largestComponentSolidity = "largest_component_solidity"
        case largestComponentMeanThickness = "largest_component_mean_thickness"
        case largestComponentMaxThickness = "largest_component_max_thickness"
        case largestComponentFilamentarity = "largest_component_filamentarity"
        case transportDisplacement = "transport_displacement"
        case translatedShapeOverlap = "translated_shape_overlap"
        case coherentTransport = "coherent_transport"
        case bodyLocomotion = "body_locomotion"
    }

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
        gyration: Float = 1000.0,
        centerVelocity: Float = 0.0,
        velocityX: Float = 0.0,
        velocityY: Float = 0.0,
        headingRad: Float = 0.0,
        isStable: Bool = false,
        complexityMean: Float? = nil,
        complexityTargetScore: Float? = nil,
        complexityScales: [Float]? = nil,
        activityEacMean: Float? = nil,
        activityEanMean: Float? = nil,
        activityDiversityMean: Float? = nil,
        activitySpeciesMean: Float? = nil,
        survivalTracked: Bool = false,
        survivalSteps: Int? = nil,
        foodInitialMass: Float? = nil,
        foodFinalMass: Float? = nil,
        foodConsumed: Float? = nil,
        hu1: Float? = nil,
        hu2: Float? = nil,
        hu3: Float? = nil,
        hu4: Float? = nil,
        hu5: Float? = nil,
        hu6: Float? = nil,
        hu7: Float? = nil,
        flusser1: Float? = nil,
        flusser2: Float? = nil,
        flusser3: Float? = nil,
        flusser4: Float? = nil,
        momentMass: Float? = nil,
        momentVolume: Float? = nil,
        momentDensity: Float? = nil,
        momentAnisotropy: Float? = nil,
        occupiedFraction: Float? = nil,
        midOccupiedFraction: Float? = nil,
        targetOccupiedFraction: Float? = nil,
        occupiedGrowth: Float? = nil,
        componentCount: Float? = nil,
        largestComponentFraction: Float? = nil,
        largestComponentAnisotropy: Float? = nil,
        largestComponentInternalStripe: Float? = nil,
        largestComponentOrientedRidge: Float? = nil,
        largestComponentSolidity: Float? = nil,
        largestComponentMeanThickness: Float? = nil,
        largestComponentMaxThickness: Float? = nil,
        largestComponentFilamentarity: Float? = nil,
        transportDisplacement: Float? = nil,
        translatedShapeOverlap: Float? = nil,
        coherentTransport: Float? = nil,
        bodyLocomotion: Float? = nil
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
        self.complexityMean = complexityMean
        self.complexityTargetScore = complexityTargetScore
        self.complexityScales = complexityScales
        self.activityEacMean = activityEacMean
        self.activityEanMean = activityEanMean
        self.activityDiversityMean = activityDiversityMean
        self.activitySpeciesMean = activitySpeciesMean
        self.survivalTracked = survivalTracked
        self.survivalSteps = survivalSteps
        self.foodInitialMass = foodInitialMass
        self.foodFinalMass = foodFinalMass
        self.foodConsumed = foodConsumed
        self.hu1 = hu1
        self.hu2 = hu2
        self.hu3 = hu3
        self.hu4 = hu4
        self.hu5 = hu5
        self.hu6 = hu6
        self.hu7 = hu7
        self.flusser1 = flusser1
        self.flusser2 = flusser2
        self.flusser3 = flusser3
        self.flusser4 = flusser4
        self.momentMass = momentMass
        self.momentVolume = momentVolume
        self.momentDensity = momentDensity
        self.momentAnisotropy = momentAnisotropy
        self.occupiedFraction = occupiedFraction
        self.midOccupiedFraction = midOccupiedFraction
        self.targetOccupiedFraction = targetOccupiedFraction
        self.occupiedGrowth = occupiedGrowth
        self.componentCount = componentCount
        self.largestComponentFraction = largestComponentFraction
        self.largestComponentAnisotropy = largestComponentAnisotropy
        self.largestComponentInternalStripe = largestComponentInternalStripe
        self.largestComponentOrientedRidge = largestComponentOrientedRidge
        self.largestComponentSolidity = largestComponentSolidity
        self.largestComponentMeanThickness = largestComponentMeanThickness
        self.largestComponentMaxThickness = largestComponentMaxThickness
        self.largestComponentFilamentarity = largestComponentFilamentarity
        self.transportDisplacement = transportDisplacement
        self.translatedShapeOverlap = translatedShapeOverlap
        self.coherentTransport = coherentTransport
        self.bodyLocomotion = bodyLocomotion
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        massMean = try container.decode(Float.self, forKey: .massMean)
        massStd = try container.decode(Float.self, forKey: .massStd)
        massMin = try container.decode(Float.self, forKey: .massMin)
        massMax = try container.decode(Float.self, forKey: .massMax)
        occupancyMean = try container.decode(Float.self, forKey: .occupancyMean)
        varianceMean = try container.decode(Float.self, forKey: .varianceMean)
        energyMean = try container.decode(Float.self, forKey: .energyMean)
        speedMean = try container.decode(Float.self, forKey: .speedMean)
        pathLength = try container.decode(Float.self, forKey: .pathLength)
        displacement = try container.decode(Float.self, forKey: .displacement)
        sampleCount = try container.decode(Int.self, forKey: .sampleCount)
        speedCount = try container.decode(Int.self, forKey: .speedCount)
        gyration = try container.decode(Float.self, forKey: .gyration)
        centerVelocity = try container.decode(Float.self, forKey: .centerVelocity)
        velocityX = try container.decodeIfPresent(Float.self, forKey: .velocityX) ?? 0.0
        velocityY = try container.decodeIfPresent(Float.self, forKey: .velocityY) ?? 0.0
        headingRad = try container.decodeIfPresent(Float.self, forKey: .headingRad) ?? 0.0
        isStable = try container.decode(Bool.self, forKey: .isStable)
        complexityMean = try container.decodeIfPresent(Float.self, forKey: .complexityMean)
        complexityTargetScore = try container.decodeIfPresent(Float.self, forKey: .complexityTargetScore)
        complexityScales = try container.decodeIfPresent([Float].self, forKey: .complexityScales)
        activityEacMean = try container.decodeIfPresent(Float.self, forKey: .activityEacMean)
        activityEanMean = try container.decodeIfPresent(Float.self, forKey: .activityEanMean)
        activityDiversityMean = try container.decodeIfPresent(Float.self, forKey: .activityDiversityMean)
        activitySpeciesMean = try container.decodeIfPresent(Float.self, forKey: .activitySpeciesMean)
        survivalTracked = try container.decodeIfPresent(Bool.self, forKey: .survivalTracked) ?? false
        survivalSteps = try container.decodeIfPresent(Int.self, forKey: .survivalSteps)
        foodInitialMass = try container.decodeIfPresent(Float.self, forKey: .foodInitialMass)
        foodFinalMass = try container.decodeIfPresent(Float.self, forKey: .foodFinalMass)
        foodConsumed = try container.decodeIfPresent(Float.self, forKey: .foodConsumed)
        hu1 = try container.decodeIfPresent(Float.self, forKey: .hu1)
        hu2 = try container.decodeIfPresent(Float.self, forKey: .hu2)
        hu3 = try container.decodeIfPresent(Float.self, forKey: .hu3)
        hu4 = try container.decodeIfPresent(Float.self, forKey: .hu4)
        hu5 = try container.decodeIfPresent(Float.self, forKey: .hu5)
        hu6 = try container.decodeIfPresent(Float.self, forKey: .hu6)
        hu7 = try container.decodeIfPresent(Float.self, forKey: .hu7)
        flusser1 = try container.decodeIfPresent(Float.self, forKey: .flusser1)
        flusser2 = try container.decodeIfPresent(Float.self, forKey: .flusser2)
        flusser3 = try container.decodeIfPresent(Float.self, forKey: .flusser3)
        flusser4 = try container.decodeIfPresent(Float.self, forKey: .flusser4)
        momentMass = try container.decodeIfPresent(Float.self, forKey: .momentMass)
        momentVolume = try container.decodeIfPresent(Float.self, forKey: .momentVolume)
        momentDensity = try container.decodeIfPresent(Float.self, forKey: .momentDensity)
        momentAnisotropy = try container.decodeIfPresent(Float.self, forKey: .momentAnisotropy)
        occupiedFraction = try container.decodeIfPresent(Float.self, forKey: .occupiedFraction)
        midOccupiedFraction = try container.decodeIfPresent(Float.self, forKey: .midOccupiedFraction)
        targetOccupiedFraction = try container.decodeIfPresent(Float.self, forKey: .targetOccupiedFraction)
        occupiedGrowth = try container.decodeIfPresent(Float.self, forKey: .occupiedGrowth)
        componentCount = try container.decodeIfPresent(Float.self, forKey: .componentCount)
        largestComponentFraction = try container.decodeIfPresent(Float.self, forKey: .largestComponentFraction)
        largestComponentAnisotropy = try container.decodeIfPresent(Float.self, forKey: .largestComponentAnisotropy)
        largestComponentInternalStripe = try container.decodeIfPresent(Float.self, forKey: .largestComponentInternalStripe)
        largestComponentOrientedRidge = try container.decodeIfPresent(Float.self, forKey: .largestComponentOrientedRidge)
        largestComponentSolidity = try container.decodeIfPresent(Float.self, forKey: .largestComponentSolidity)
        largestComponentMeanThickness = try container.decodeIfPresent(Float.self, forKey: .largestComponentMeanThickness)
        largestComponentMaxThickness = try container.decodeIfPresent(Float.self, forKey: .largestComponentMaxThickness)
        largestComponentFilamentarity = try container.decodeIfPresent(Float.self, forKey: .largestComponentFilamentarity)
        transportDisplacement = try container.decodeIfPresent(Float.self, forKey: .transportDisplacement)
        translatedShapeOverlap = try container.decodeIfPresent(Float.self, forKey: .translatedShapeOverlap)
        coherentTransport = try container.decodeIfPresent(Float.self, forKey: .coherentTransport)
        bodyLocomotion = try container.decodeIfPresent(Float.self, forKey: .bodyLocomotion)
    }

    func withStability(_ isStable: Bool) -> SimulationMetrics {
        SimulationMetrics(
            massMean: massMean,
            massStd: massStd,
            massMin: massMin,
            massMax: massMax,
            occupancyMean: occupancyMean,
            varianceMean: varianceMean,
            energyMean: energyMean,
            speedMean: speedMean,
            pathLength: pathLength,
            displacement: displacement,
            sampleCount: sampleCount,
            speedCount: speedCount,
            gyration: gyration,
            centerVelocity: centerVelocity,
            velocityX: velocityX,
            velocityY: velocityY,
            headingRad: headingRad,
            isStable: isStable,
            complexityMean: complexityMean,
            complexityTargetScore: complexityTargetScore,
            complexityScales: complexityScales,
            activityEacMean: activityEacMean,
            activityEanMean: activityEanMean,
            activityDiversityMean: activityDiversityMean,
            activitySpeciesMean: activitySpeciesMean,
            survivalTracked: survivalTracked,
            survivalSteps: survivalSteps,
            foodInitialMass: foodInitialMass,
            foodFinalMass: foodFinalMass,
            foodConsumed: foodConsumed,
            hu1: hu1,
            hu2: hu2,
            hu3: hu3,
            hu4: hu4,
            hu5: hu5,
            hu6: hu6,
            hu7: hu7,
            flusser1: flusser1,
            flusser2: flusser2,
            flusser3: flusser3,
            flusser4: flusser4,
            momentMass: momentMass,
            momentVolume: momentVolume,
            momentDensity: momentDensity,
            momentAnisotropy: momentAnisotropy,
            occupiedFraction: occupiedFraction,
            midOccupiedFraction: midOccupiedFraction,
            targetOccupiedFraction: targetOccupiedFraction,
            occupiedGrowth: occupiedGrowth,
            componentCount: componentCount,
            largestComponentFraction: largestComponentFraction,
            largestComponentAnisotropy: largestComponentAnisotropy,
            largestComponentInternalStripe: largestComponentInternalStripe,
            largestComponentOrientedRidge: largestComponentOrientedRidge,
            largestComponentSolidity: largestComponentSolidity,
            largestComponentMeanThickness: largestComponentMeanThickness,
            largestComponentMaxThickness: largestComponentMaxThickness,
            largestComponentFilamentarity: largestComponentFilamentarity,
            transportDisplacement: transportDisplacement,
            translatedShapeOverlap: translatedShapeOverlap,
            coherentTransport: coherentTransport,
            bodyLocomotion: bodyLocomotion
        )
    }
}
