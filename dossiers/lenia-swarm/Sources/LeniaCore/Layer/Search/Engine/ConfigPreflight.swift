struct SearchMetricRequirements {
    let usesComplexity: Bool
    let usesMoments: Bool
    let usesActivity: Bool
    let usesSurvival: Bool

    init(searchConfig: SearchConfig, stabilityFilters: [String: Float]) {
        usesComplexity = searchConfig.scoreWeights.keys.contains { $0.hasPrefix("complexity") }
            || searchConfig.filters.keys.contains { $0.hasPrefix("complexity") }
            || stabilityFilters.keys.contains { $0.hasPrefix("complexity") }
        usesMoments = searchMetricKeysRequireMoments(searchConfig.scoreWeights)
            || searchMetricKeysRequireMoments(searchConfig.filters)
            || searchMetricKeysRequireMoments(stabilityFilters)
        usesActivity = searchMetricKeysRequireActivity(searchConfig.filters)
            || searchMetricKeysRequireActivity(stabilityFilters)
            || searchMetricKeysRequireActivity(searchConfig.scoreWeights)
        usesSurvival = searchMetricKeysRequireSurvival(searchConfig.scoreWeights)
            || searchMetricKeysRequireSurvival(searchConfig.filters)
            || searchMetricKeysRequireSurvival(stabilityFilters)
    }
}

private func searchMetricKeysRequireSurvival(_ metrics: [String: Float]) -> Bool {
    metrics.keys.contains { key in
        key == "survived" || key == "survival_steps" || key.hasPrefix("survival_steps_")
    }
}

struct SearchConfigPreflight {
    let activityConfig: ActivityConfig?
    let stabilityConfig: StabilityConfig
    let metricRequirements: SearchMetricRequirements

    init(searchConfig: SearchConfig, useParamEmbedding: Bool) {
        if searchConfig.steps <= 0 {
            fatalError("search.steps must be > 0.")
        }
        if searchConfig.recordInterval <= 0 {
            fatalError("search.record_interval must be > 0.")
        }
        if searchConfig.warmupSteps < 0 {
            fatalError("search.warmup_steps must be >= 0.")
        }
        if searchConfig.warmupSteps + searchConfig.recordInterval > searchConfig.steps {
            fatalError("search configuration must record at least one post-warmup sample.")
        }

        let resolvedStabilityConfig = searchConfig.stability ?? StabilityConfig.defaultConfig
        let stabilityFilters = resolvedStabilityConfig.filters
        let metricRequirements = SearchMetricRequirements(
            searchConfig: searchConfig,
            stabilityFilters: stabilityFilters
        )

        if metricRequirements.usesComplexity && searchConfig.complexity?.enabled != true {
            fatalError("Complexity metrics requested but complexity is disabled.")
        }
        if let complexity = searchConfig.complexity, complexity.enabled, complexity.scales.isEmpty {
            fatalError("complexity.scales must be non-empty when complexity is enabled.")
        }

        if metricRequirements.usesMoments && searchConfig.moments?.enabled != true {
            fatalError("Moment metrics requested but moments is disabled.")
        }

        if metricRequirements.usesActivity && searchConfig.activity?.enabled != true {
            fatalError("Activity metrics requested but activity is disabled.")
        }
        if metricRequirements.usesSurvival && searchConfig.kSurvival?.enabled != true {
            fatalError("Survival metrics requested but k_survival is disabled.")
        }
        if let activity = searchConfig.activity, activity.enabled {
            if activity.interval <= 0 {
                fatalError("activity.interval must be > 0 when activity is enabled.")
            }
            if activity.threshold < 0 {
                fatalError("activity.threshold must be >= 0 when activity is enabled.")
            }
            if !useParamEmbedding {
                fatalError("Activity tracking requires parameter embedding to be enabled.")
            }
        }

        if let stability = searchConfig.stability {
            if stability.windowSamples < 0 {
                fatalError("stability.window_samples must be >= 0.")
            }
            let needsWindow = stability.windowSamples > 0
            if !needsWindow
                && (stability.windowMassStdMax != nil
                    || stability.windowOccupancyStdMax != nil
                    || stability.windowGyrationStdMax != nil) {
                fatalError("stability.window_samples must be > 0 when window thresholds are set.")
            }
            if stability.filters.keys.contains("stable") {
                fatalError("stability.filters cannot include stable (would be recursive).")
            }
            if stability.massMinFraction < 0 || stability.massMaxFraction <= stability.massMinFraction {
                fatalError("stability mass thresholds must be positive and max > min.")
            }
        }

        activityConfig = searchConfig.activity
        stabilityConfig = resolvedStabilityConfig
        self.metricRequirements = metricRequirements
    }

    static func captureConfig(_ frameCapture: FrameCapture?, batchSize: Int) -> FrameCapture? {
        guard let frameCapture else {
            return nil
        }
        if frameCapture.stride <= 0 {
            fatalError("frame_capture.stride must be > 0.")
        }
        if frameCapture.sampleIndex < 0 {
            fatalError("frame_capture.sample_index must be >= 0.")
        }
        if frameCapture.sampleIndex >= batchSize {
            fatalError("frame_capture.sample_index must be < batch size.")
        }
        return frameCapture
    }
}

enum SearchRuntimePreflight {
    static func validateMetalBackendCompatibility(
        runtimeConfig: LeniaRuntimeConfig,
        hasEnvironmentPotential _: Bool
    ) {
        if runtimeConfig.parameterEmbedding.enabled {
            let supportedMixModes = runtimeConfig.channels == 1 ? ["avg"] : ["avg", "stoch"]
            guard supportedMixModes.contains(runtimeConfig.parameterEmbedding.mix) else {
                fatalError("SearchEngine Metal backends currently require parameter_embedding.mix to be one of: \(supportedMixModes.joined(separator: ", ")).")
            }
        }
        let validBoundaryPair = (runtimeConfig.border == "torus" && runtimeConfig.implementation.gradientBoundary == "periodic") ||
            (runtimeConfig.border == "wall" && runtimeConfig.implementation.gradientBoundary == "zero_pad")
        guard validBoundaryPair else {
            fatalError("SearchEngine Metal backends require torus/periodic or wall/zero_pad boundaries.")
        }
    }

    static func validateRuntimeConfig(
        runtimeConfig: LeniaRuntimeConfig,
        profile: RuntimeProfile
    ) {
        if let chemConfig = runtimeConfig.chemotaxis, chemConfig.enabled {
            if chemConfig.channel_index < 0 || chemConfig.channel_index >= runtimeConfig.channels {
                fatalError("chemotaxis.channel_index is out of range for configured channels.")
            }
            if runtimeConfig.channels < 2 {
                fatalError("chemotaxis requires channels >= 2.")
            }
        }

        if let foodConfig = runtimeConfig.food, foodConfig.enabled {
            if profile != .experimental {
                fatalError("food requires profile=experimental.")
            }
            if foodConfig.channel_index < 0 || foodConfig.channel_index >= runtimeConfig.channels {
                fatalError("food.channel_index is out of range for configured channels.")
            }
            if runtimeConfig.channels < 2 {
                fatalError("food requires channels >= 2.")
            }
            if foodConfig.include_in_mass {
                fatalError("food.include_in_mass must be false for external food maps.")
            }
            if foodConfig.decay_rate < 0 {
                fatalError("food.decay_rate must be >= 0.")
            }
            if foodConfig.digest_rate < 0 {
                fatalError("food.digest_rate must be >= 0.")
            }
            if foodConfig.mode != "full" && foodConfig.mode != "patches" {
                fatalError("food.mode must be \"full\" or \"patches\".")
            }
            if foodConfig.mode == "patches", (foodConfig.patches?.isEmpty ?? true) {
                fatalError("food.mode=\"patches\" requires non-empty food.patches.")
            }
        }

        if let wallsConfig = runtimeConfig.walls, wallsConfig.enabled {
            if profile != .experimental {
                fatalError("walls require profile=experimental.")
            }
            if wallsConfig.patches.isEmpty {
                fatalError("walls.patches must be non-empty when walls are enabled.")
            }
        }

        if let beamConfig = runtimeConfig.beamMutation, beamConfig.enabled,
           beamConfig.patchSize > runtimeConfig.sx || beamConfig.patchSize > runtimeConfig.sy {
            fatalError("beam_mutation.patch_size must fit within the configured grid.")
        }

        if let chemConfig = runtimeConfig.chemotaxis, chemConfig.enabled,
           let foodConfig = runtimeConfig.food, foodConfig.enabled,
           chemConfig.channel_index == foodConfig.channel_index {
            fatalError("chemotaxis and food cannot share the same channel_index.")
        }

        if profile != .experimental && !runtimeConfig.interventions.isEmpty {
            fatalError("interventions require profile=experimental.")
        }

        if profile == .paper {
            validatePaperProfileConfig(runtimeConfig: runtimeConfig)
        }
    }

    private static func validatePaperProfileConfig(runtimeConfig: LeniaRuntimeConfig) {
        if runtimeConfig.parameterEmbedding.enabled {
            let mixMode = runtimeConfig.parameterEmbedding.mix
            if mixMode != "avg" && mixMode != "softmax" {
                fatalError("profile=paper requires parameter_embedding.mix to be \"avg\" or \"softmax\".")
            }
        }

        if runtimeConfig.statePatch == nil {
            if runtimeConfig.patches.count != 1 {
                fatalError("profile=paper requires exactly one init patch when init.state_patch is absent.")
            }

            let patch = runtimeConfig.patches[0]
            if patch.size != 40 {
                fatalError("profile=paper requires init patch size == 40 when init.state_patch is absent.")
            }

            if patch.center.count != 2 {
                fatalError("init patch center must have two coordinates.")
            }

            let expectedCenter = [runtimeConfig.sx / 2, runtimeConfig.sy / 2]
            if patch.center != expectedCenter {
                fatalError("profile=paper requires init patch centered at \(expectedCenter) when init.state_patch is absent.")
            }

            if runtimeConfig.aUniform.low != 0.0 || runtimeConfig.aUniform.high != 1.0 {
                fatalError("profile=paper requires init.a_uniform range [0, 1] when init.state_patch is absent.")
            }
        }

        if let chemConfig = runtimeConfig.chemotaxis, chemConfig.enabled {
            if runtimeConfig.channels < 2 {
                fatalError("profile=paper chemotaxis requires channels >= 2.")
            }
            if chemConfig.include_in_mass {
                fatalError("profile=paper chemotaxis requires include_in_mass == false.")
            }
            if chemConfig.mode != "random_on_circle" {
                fatalError("profile=paper chemotaxis requires mode == \"random_on_circle\".")
            }
            if chemConfig.circle_radius == nil || chemConfig.seed == nil {
                fatalError("profile=paper chemotaxis requires circle_radius and seed.")
            }
            if chemConfig.center.count != 2 {
                fatalError("chemotaxis.center must have two coordinates.")
            }
            let expectedCenter = [Float(runtimeConfig.sx) / 2.0, Float(runtimeConfig.sy) / 2.0]
            if chemConfig.center[0] != expectedCenter[0] || chemConfig.center[1] != expectedCenter[1] {
                fatalError("profile=paper chemotaxis requires center at \(expectedCenter).")
            }
        }
    }
}

private func searchMetricKeysRequireActivity(_ filters: [String: Float]) -> Bool {
    filters.keys.contains { $0.hasPrefix("activity_") }
}

private func searchMetricKeysRequireMoments(_ keys: [String: Float]) -> Bool {
    keys.keys.contains { key in
        key.hasPrefix("hu") || key.hasPrefix("flusser") || key.hasPrefix("moment_")
    }
}
