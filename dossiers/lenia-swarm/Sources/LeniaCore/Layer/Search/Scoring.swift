import Foundation

public func scoreMetrics(_ metrics: SimulationMetrics, weights: [String: Float]) -> Float {
    var score: Float = 0.0
    for (key, weight) in weights {
        let value: Float
        switch key {
        case "mass_mean": value = metrics.massMean
        case "mass_std": value = metrics.massStd
        case "mass_min": value = metrics.massMin
        case "mass_max": value = metrics.massMax
        case "occupancy_mean": value = metrics.occupancyMean
        case "variance_mean": value = metrics.varianceMean
        case "energy_mean": value = metrics.energyMean
        case "speed_mean": value = metrics.speedMean
        case "path_length": value = metrics.pathLength
        case "displacement": value = metrics.displacement
        case "gyration": value = metrics.gyration
        case "center_velocity": value = metrics.centerVelocity
        case "translation_ratio": value = translationRatio(for: metrics)
        case "survived":
            guard metrics.survivalTracked else {
                fatalError("survived requested but k_survival tracking was not enabled.")
            }
            value = metrics.survivalSteps == nil ? 1.0 : 0.0
        case "survival_steps":
            guard metrics.survivalTracked else {
                fatalError("survival_steps requested but k_survival tracking was not enabled.")
            }
            value = Float(metrics.survivalSteps ?? metrics.sampleCount)
        case "compactness": value = compactness(for: metrics)
        case "localized_motion": value = localizedMotion(for: metrics)
        case "food_initial_mass": value = metrics.foodInitialMass ?? 0
        case "food_final_mass": value = metrics.foodFinalMass ?? 0
        case "food_consumed": value = metrics.foodConsumed ?? 0
        case "food_consumed_fraction": value = foodConsumedFraction(for: metrics)
        case "complexity_mean":
            guard let metric = metrics.complexityMean else {
                fatalError("complexity_mean requested but not computed.")
            }
            value = metric
        case "complexity_target_score":
            guard let metric = metrics.complexityTargetScore else {
                fatalError("complexity_target_score requested but not computed.")
            }
            value = metric
        case "hu1": guard let m = metrics.hu1 else { fatalError("hu1 requested but moments not computed.") }; value = m
        case "hu2": guard let m = metrics.hu2 else { fatalError("hu2 requested but moments not computed.") }; value = m
        case "hu3": guard let m = metrics.hu3 else { fatalError("hu3 requested but moments not computed.") }; value = m
        case "hu4": guard let m = metrics.hu4 else { fatalError("hu4 requested but moments not computed.") }; value = m
        case "hu5": guard let m = metrics.hu5 else { fatalError("hu5 requested but moments not computed.") }; value = m
        case "hu6": guard let m = metrics.hu6 else { fatalError("hu6 requested but moments not computed.") }; value = m
        case "hu7": guard let m = metrics.hu7 else { fatalError("hu7 requested but moments not computed.") }; value = m
        case "flusser1": guard let m = metrics.flusser1 else { fatalError("flusser1 requested but moments not computed.") }; value = m
        case "flusser2": guard let m = metrics.flusser2 else { fatalError("flusser2 requested but moments not computed.") }; value = m
        case "flusser3": guard let m = metrics.flusser3 else { fatalError("flusser3 requested but moments not computed.") }; value = m
        case "flusser4": guard let m = metrics.flusser4 else { fatalError("flusser4 requested but moments not computed.") }; value = m
        case "moment_mass": guard let m = metrics.momentMass else { fatalError("moment_mass requested but moments not computed.") }; value = m
        case "moment_volume": guard let m = metrics.momentVolume else { fatalError("moment_volume requested but moments not computed.") }; value = m
        case "moment_density": guard let m = metrics.momentDensity else { fatalError("moment_density requested but moments not computed.") }; value = m
        case "moment_anisotropy": guard let m = metrics.momentAnisotropy else { fatalError("moment_anisotropy requested but moments not computed.") }; value = m
        case "component_count":
            guard let metric = metrics.componentCount else {
                fatalError("component_count requested but component metrics not computed.")
            }
            value = metric
        case "largest_component_fraction":
            guard let metric = metrics.largestComponentFraction else {
                fatalError("largest_component_fraction requested but component metrics not computed.")
            }
            value = metric
        case "largest_component_anisotropy":
            guard let metric = metrics.largestComponentAnisotropy else {
                fatalError("largest_component_anisotropy requested but component metrics not computed.")
            }
            value = metric
        case "activity_eac_mean": value = metrics.activityEacMean ?? 0
        case "activity_ean_mean": value = metrics.activityEanMean ?? 0
        case "activity_diversity_mean": value = metrics.activityDiversityMean ?? 0
        case "activity_species_mean": value = metrics.activitySpeciesMean ?? 0
        default: continue
        }
        score += weight * value
    }
    return score
}

public func passesFilters(_ metrics: SimulationMetrics, filters: [String: Float]) -> Bool {
    for (key, threshold) in filters {
        switch key {
        case "mass_min":
            if metrics.massMin < threshold { return false }
        case "mass_max":
            if metrics.massMax > threshold { return false }
        case "occupancy_min":
            if metrics.occupancyMean < threshold { return false }
        case "occupancy_max":
            if metrics.occupancyMean > threshold { return false }
        case "variance_max":
            if metrics.varianceMean > threshold { return false }
        case "energy_max":
            if metrics.energyMean > threshold { return false }
        case "speed_min":
            if metrics.speedMean < threshold { return false }
        case "speed_max":
            if metrics.speedMean > threshold { return false }
        case "path_length_min":
            if metrics.pathLength < threshold { return false }
        case "path_length_max":
            if metrics.pathLength > threshold { return false }
        case "displacement_min":
            if metrics.displacement < threshold { return false }
        case "displacement_max":
            if metrics.displacement > threshold { return false }
        case "gyration_max":
            if metrics.gyration > threshold { return false }
        case "gyration_min":
            if metrics.gyration < threshold { return false }
        case "velocity_min":
            if metrics.centerVelocity < threshold { return false }
        case "velocity_max":
            if metrics.centerVelocity > threshold { return false }
        case "translation_ratio_min":
            if translationRatio(for: metrics) < threshold { return false }
        case "translation_ratio_max":
            if translationRatio(for: metrics) > threshold { return false }
        case "survived":
            guard metrics.survivalTracked else {
                fatalError("survived filter requested but k_survival tracking was not enabled.")
            }
            if threshold > 0 && metrics.survivalSteps != nil { return false }
        case "survival_steps_min":
            guard metrics.survivalTracked else {
                fatalError("survival_steps_min requested but k_survival tracking was not enabled.")
            }
            if Float(metrics.survivalSteps ?? metrics.sampleCount) < threshold { return false }
        case "survival_steps_max":
            guard metrics.survivalTracked else {
                fatalError("survival_steps_max requested but k_survival tracking was not enabled.")
            }
            if Float(metrics.survivalSteps ?? metrics.sampleCount) > threshold { return false }
        case "compactness_min":
            if compactness(for: metrics) < threshold { return false }
        case "compactness_max":
            if compactness(for: metrics) > threshold { return false }
        case "localized_motion_min":
            if localizedMotion(for: metrics) < threshold { return false }
        case "localized_motion_max":
            if localizedMotion(for: metrics) > threshold { return false }
        case "food_initial_mass_min":
            if (metrics.foodInitialMass ?? 0) < threshold { return false }
        case "food_initial_mass_max":
            if (metrics.foodInitialMass ?? 0) > threshold { return false }
        case "food_final_mass_min":
            if (metrics.foodFinalMass ?? 0) < threshold { return false }
        case "food_final_mass_max":
            if (metrics.foodFinalMass ?? 0) > threshold { return false }
        case "food_consumed_min":
            if (metrics.foodConsumed ?? 0) < threshold { return false }
        case "food_consumed_max":
            if (metrics.foodConsumed ?? 0) > threshold { return false }
        case "food_consumed_fraction_min":
            if foodConsumedFraction(for: metrics) < threshold { return false }
        case "food_consumed_fraction_max":
            if foodConsumedFraction(for: metrics) > threshold { return false }
        case "complexity_min":
            guard let metric = metrics.complexityMean else {
                fatalError("complexity_min requested but complexity_mean not computed.")
            }
            if metric < threshold { return false }
        case "complexity_max":
            guard let metric = metrics.complexityMean else {
                fatalError("complexity_max requested but complexity_mean not computed.")
            }
            if metric > threshold { return false }
        case "activity_eac_min":
            guard let metric = metrics.activityEacMean else {
                fatalError("activity_eac_min requested but activity_eac_mean not computed.")
            }
            if metric < threshold { return false }
        case "activity_eac_max":
            guard let metric = metrics.activityEacMean else {
                fatalError("activity_eac_max requested but activity_eac_mean not computed.")
            }
            if metric > threshold { return false }
        case "activity_ean_min":
            guard let metric = metrics.activityEanMean else {
                fatalError("activity_ean_min requested but activity_ean_mean not computed.")
            }
            if metric < threshold { return false }
        case "activity_ean_max":
            guard let metric = metrics.activityEanMean else {
                fatalError("activity_ean_max requested but activity_ean_mean not computed.")
            }
            if metric > threshold { return false }
        case "activity_diversity_min":
            guard let metric = metrics.activityDiversityMean else {
                fatalError("activity_diversity_min requested but activity_diversity_mean not computed.")
            }
            if metric < threshold { return false }
        case "activity_diversity_max":
            guard let metric = metrics.activityDiversityMean else {
                fatalError("activity_diversity_max requested but activity_diversity_mean not computed.")
            }
            if metric > threshold { return false }
        case "activity_species_min":
            guard let metric = metrics.activitySpeciesMean else {
                fatalError("activity_species_min requested but activity_species_mean not computed.")
            }
            if metric < threshold { return false }
        case "activity_species_max":
            guard let metric = metrics.activitySpeciesMean else {
                fatalError("activity_species_max requested but activity_species_mean not computed.")
            }
            if metric > threshold { return false }
        case "stable":
            if threshold > 0 && !metrics.isStable { return false }
        case "hu1_min": guard let m = metrics.hu1 else { fatalError("hu1_min: moments not computed.") }; if m < threshold { return false }
        case "hu1_max": guard let m = metrics.hu1 else { fatalError("hu1_max: moments not computed.") }; if m > threshold { return false }
        case "hu2_min": guard let m = metrics.hu2 else { fatalError("hu2_min: moments not computed.") }; if m < threshold { return false }
        case "hu2_max": guard let m = metrics.hu2 else { fatalError("hu2_max: moments not computed.") }; if m > threshold { return false }
        case "hu3_min": guard let m = metrics.hu3 else { fatalError("hu3_min: moments not computed.") }; if m < threshold { return false }
        case "hu3_max": guard let m = metrics.hu3 else { fatalError("hu3_max: moments not computed.") }; if m > threshold { return false }
        case "hu4_min": guard let m = metrics.hu4 else { fatalError("hu4_min: moments not computed.") }; if m < threshold { return false }
        case "hu4_max": guard let m = metrics.hu4 else { fatalError("hu4_max: moments not computed.") }; if m > threshold { return false }
        case "hu5_min": guard let m = metrics.hu5 else { fatalError("hu5_min: moments not computed.") }; if m < threshold { return false }
        case "hu5_max": guard let m = metrics.hu5 else { fatalError("hu5_max: moments not computed.") }; if m > threshold { return false }
        case "hu6_min": guard let m = metrics.hu6 else { fatalError("hu6_min: moments not computed.") }; if m < threshold { return false }
        case "hu6_max": guard let m = metrics.hu6 else { fatalError("hu6_max: moments not computed.") }; if m > threshold { return false }
        case "hu7_min": guard let m = metrics.hu7 else { fatalError("hu7_min: moments not computed.") }; if m < threshold { return false }
        case "hu7_max": guard let m = metrics.hu7 else { fatalError("hu7_max: moments not computed.") }; if m > threshold { return false }
        case "flusser1_min": guard let m = metrics.flusser1 else { fatalError("flusser1_min: moments not computed.") }; if m < threshold { return false }
        case "flusser1_max": guard let m = metrics.flusser1 else { fatalError("flusser1_max: moments not computed.") }; if m > threshold { return false }
        case "flusser2_min": guard let m = metrics.flusser2 else { fatalError("flusser2_min: moments not computed.") }; if m < threshold { return false }
        case "flusser2_max": guard let m = metrics.flusser2 else { fatalError("flusser2_max: moments not computed.") }; if m > threshold { return false }
        case "flusser3_min": guard let m = metrics.flusser3 else { fatalError("flusser3_min: moments not computed.") }; if m < threshold { return false }
        case "flusser3_max": guard let m = metrics.flusser3 else { fatalError("flusser3_max: moments not computed.") }; if m > threshold { return false }
        case "flusser4_min": guard let m = metrics.flusser4 else { fatalError("flusser4_min: moments not computed.") }; if m < threshold { return false }
        case "flusser4_max": guard let m = metrics.flusser4 else { fatalError("flusser4_max: moments not computed.") }; if m > threshold { return false }
        case "moment_mass_min": guard let m = metrics.momentMass else { fatalError("moment_mass_min: moments not computed.") }; if m < threshold { return false }
        case "moment_mass_max": guard let m = metrics.momentMass else { fatalError("moment_mass_max: moments not computed.") }; if m > threshold { return false }
        case "moment_volume_min": guard let m = metrics.momentVolume else { fatalError("moment_volume_min: moments not computed.") }; if m < threshold { return false }
        case "moment_volume_max": guard let m = metrics.momentVolume else { fatalError("moment_volume_max: moments not computed.") }; if m > threshold { return false }
        case "moment_density_min": guard let m = metrics.momentDensity else { fatalError("moment_density_min: moments not computed.") }; if m < threshold { return false }
        case "moment_density_max": guard let m = metrics.momentDensity else { fatalError("moment_density_max: moments not computed.") }; if m > threshold { return false }
        case "moment_anisotropy_min": guard let m = metrics.momentAnisotropy else { fatalError("moment_anisotropy_min: moments not computed.") }; if m < threshold { return false }
        case "moment_anisotropy_max": guard let m = metrics.momentAnisotropy else { fatalError("moment_anisotropy_max: moments not computed.") }; if m > threshold { return false }
        case "component_count_min":
            guard let metric = metrics.componentCount else { fatalError("component_count_min: component metrics not computed.") }
            if metric < threshold { return false }
        case "component_count_max":
            guard let metric = metrics.componentCount else { fatalError("component_count_max: component metrics not computed.") }
            if metric > threshold { return false }
        case "largest_component_fraction_min":
            guard let metric = metrics.largestComponentFraction else {
                fatalError("largest_component_fraction_min: component metrics not computed.")
            }
            if metric < threshold { return false }
        case "largest_component_fraction_max":
            guard let metric = metrics.largestComponentFraction else {
                fatalError("largest_component_fraction_max: component metrics not computed.")
            }
            if metric > threshold { return false }
        case "largest_component_anisotropy_min":
            guard let metric = metrics.largestComponentAnisotropy else {
                fatalError("largest_component_anisotropy_min: component metrics not computed.")
            }
            if metric < threshold { return false }
        case "largest_component_anisotropy_max":
            guard let metric = metrics.largestComponentAnisotropy else {
                fatalError("largest_component_anisotropy_max: component metrics not computed.")
            }
            if metric > threshold { return false }
        default:
            fatalError("passesFilters: unknown filter key '\(key)'")
        }
    }
    return true
}

private func translationRatio(for metrics: SimulationMetrics) -> Float {
    let path = metrics.pathLength
    guard path > 1e-6 else { return 0 }
    return metrics.displacement / path
}

private func compactness(for metrics: SimulationMetrics) -> Float {
    1.0 / (1.0 + max(metrics.gyration, 0.0))
}

private func localizedMotion(for metrics: SimulationMetrics) -> Float {
    metrics.centerVelocity * compactness(for: metrics)
}

private func foodConsumedFraction(for metrics: SimulationMetrics) -> Float {
    guard let initial = metrics.foodInitialMass, initial > 1e-6 else {
        return 0
    }
    return max(metrics.foodConsumed ?? 0, 0) / initial
}
