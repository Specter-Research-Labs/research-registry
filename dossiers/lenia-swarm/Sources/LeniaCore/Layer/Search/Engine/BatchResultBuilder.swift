import Foundation
import MLX

struct SearchBatchResultBuilder {
    let runtimeConfig: LeniaRuntimeConfig
    let excludedMassChannels: Set<Int>

    func build(
        seeds: [Int],
        initSeedOffset: Int,
        searchConfig: SearchConfig,
        initialConditionFamily: String,
        activityConfig: ActivityConfig?,
        stabilityConfig: StabilityConfig,
        usesActivityMetrics: Bool,
        rolloutSummary: SearchRolloutFinalizedStats,
        terminalMassMap: MLXArray?,
        terminalStateBatch: MLXArray?,
        terminalParamBatch: MLXArray?,
        foodInitialMass: [Float]? = nil,
        foodFinalMass: [Float]? = nil
    ) -> [BatchSimulationResult] {
        let massForPostProcessing: MLXArray
        if let lastMassMap = rolloutSummary.lastMassMap {
            massForPostProcessing = lastMassMap
        } else if let terminalMassMap {
            massForPostProcessing = terminalMassMap
        } else if let terminalStateBatch {
            massForPostProcessing = massMapFromBatch(terminalStateBatch, searchConfig: searchConfig)
        } else {
            fatalError("Search result building requires a terminal mass map or terminal state batch.")
        }
        let postProcessingMass = materializeMassBatch(massForPostProcessing)
        let terminalStatePatches: [InitStatePatchConfig]?
        let terminalParamPatches: [InitStatePatchConfig]?
        if searchConfig.captureTerminalPatches {
            guard let terminalStateBatch else {
                fatalError("Terminal patch capture requires a terminal state batch.")
            }
            terminalStatePatches = materializeFullWorldPatches(batch: terminalStateBatch)
            terminalParamPatches = terminalParamBatch.map { materializeFullWorldPatches(batch: $0) }
        } else {
            terminalStatePatches = nil
            terminalParamPatches = nil
        }

        let complexityResult: ComplexityBatchResult?
        if let complexityConfig = searchConfig.complexity, complexityConfig.enabled {
            complexityResult = computeComplexityBatch(materialized: postProcessingMass, config: complexityConfig)
        } else {
            complexityResult = nil
        }

        let descriptorMomentsConfig = MomentsConfig(
            enabled: true,
            threshold: searchConfig.moments?.threshold ?? 0.01
        )
        let momentsResult = computeMomentsBatch(materialized: postProcessingMass, config: descriptorMomentsConfig)

        let componentThreshold = searchConfig.componentThreshold ?? searchConfig.occupancyThreshold
        let componentMetricsResult = computeComponentMetricsBatch(
            materialized: postProcessingMass,
            threshold: componentThreshold,
            useTorus: runtimeConfig.border == "torus"
        )
        let genotypeDescriptor = morphospaceGenotypeDescriptor(runtimeConfig.params)

        var results: [BatchSimulationResult] = []
        for (i, seed) in seeds.enumerated() {
            var activityEacMean: Float? = nil
            var activityEanMean: Float? = nil
            var activityDiversityMean: Float? = nil
            var activitySpeciesMean: Float? = nil
            if usesActivityMetrics {
                activityEacMean = rolloutSummary.activityEacMean[i]
                activityEanMean = rolloutSummary.activityEanMean[i]
                activityDiversityMean = rolloutSummary.activityDiversityMean[i]
                activitySpeciesMean = rolloutSummary.activitySpeciesMean[i]
            }
            let foodConsumed = zipOptional(foodInitialMass?[i], foodFinalMass?[i]).map { initial, final in
                max(initial - final, 0)
            }

            let huI = momentsResult.hu[i]
            let flI = momentsResult.flusser[i]

            let provisionalMetrics = SimulationMetrics(
                massMean: rolloutSummary.massMean[i],
                massStd: rolloutSummary.massStd[i],
                massMin: rolloutSummary.massMin[i],
                massMax: rolloutSummary.massMax[i],
                occupancyMean: rolloutSummary.occupancyMean[i],
                varianceMean: rolloutSummary.varianceMean[i],
                energyMean: rolloutSummary.energyMean[i],
                speedMean: rolloutSummary.speedMean[i],
                pathLength: rolloutSummary.pathLength[i],
                displacement: rolloutSummary.displacement[i],
                sampleCount: rolloutSummary.effectiveSampleCount,
                speedCount: rolloutSummary.speedCount,
                gyration: rolloutSummary.gyration[i],
                centerVelocity: rolloutSummary.velocity[i],
                velocityX: rolloutSummary.velocityX[i],
                velocityY: rolloutSummary.velocityY[i],
                headingRad: rolloutSummary.heading[i],
                isStable: false,
                complexityMean: complexityResult?.mean[i],
                complexityTargetScore: complexityResult?.targetScores?[i],
                complexityScales: complexityResult?.scales[i],
                activityEacMean: activityEacMean,
                activityEanMean: activityEanMean,
                activityDiversityMean: activityDiversityMean,
                activitySpeciesMean: activitySpeciesMean,
                survivalTracked: searchConfig.kSurvival?.enabled == true,
                survivalSteps: rolloutSummary.survivalDeathStep[i],
                foodInitialMass: foodInitialMass?[i],
                foodFinalMass: foodFinalMass?[i],
                foodConsumed: foodConsumed,
                hu1: huI[0], hu2: huI[1], hu3: huI[2], hu4: huI[3],
                hu5: huI[4], hu6: huI[5], hu7: huI[6],
                flusser1: flI[0], flusser2: flI[1], flusser3: flI[2], flusser4: flI[3],
                momentMass: momentsResult.mass[i],
                momentVolume: momentsResult.volume[i],
                momentDensity: momentsResult.density[i],
                momentAnisotropy: momentsResult.anisotropy[i],
                componentCount: componentMetricsResult.count[i],
                largestComponentFraction: componentMetricsResult.largestFraction[i],
                largestComponentAnisotropy: componentMetricsResult.largestAnisotropy[i]
            )

            let stable = isStableCreature(
                config: stabilityConfig,
                metrics: provisionalMetrics,
                finalMass: rolloutSummary.finalMass[i],
                massMin: rolloutSummary.massMin[i],
                massMax: rolloutSummary.massMax[i],
                windowMassStd: rolloutSummary.windowMassStd?[i],
                windowOccupancyStd: rolloutSummary.windowOccupancyStd?[i],
                windowGyrationStd: rolloutSummary.windowGyrationStd?[i]
            )
            let metrics = provisionalMetrics.withStability(stable)
            let activitySnapshots: [ActivitySnapshot]? = rolloutSummary.activityLogs?[i]
            let activitySummary: ActivitySummary?
            if let activityConfig, let activitySnapshots, !activitySnapshots.isEmpty {
                activitySummary = summarizeActivity(snapshots: activitySnapshots, config: activityConfig)
            } else {
                activitySummary = nil
            }
            let morphometrics = Morphometrics.from(metrics: metrics, activity: activitySummary)
            let componentSeriesStats = morphospaceTrajectoryComponentStats(activity: activitySnapshots)
            let finalSampleSummary = morphospaceFinalSampleSummary(
                materialized: postProcessingMass,
                sampleIndex: i,
                occupancyThreshold: searchConfig.occupancyThreshold,
                useTorus: runtimeConfig.border == "torus"
            )
            let trajectoryDescriptor = MorphospaceTrajectoryDescriptor(
                recordInterval: searchConfig.recordInterval,
                warmupSteps: searchConfig.warmupSteps,
                sampleCount: rolloutSummary.effectiveSampleCount,
                pathLength: metrics.pathLength,
                displacement: metrics.displacement,
                pathTortuosity: morphometrics.pathTortuosity,
                movementEfficiency: morphometrics.movementEfficiency,
                speedMean: metrics.speedMean,
                centerVelocity: metrics.centerVelocity,
                velocityX: metrics.velocityX,
                velocityY: metrics.velocityY,
                headingRad: metrics.headingRad,
                headingCircularVariance: rolloutSummary.headingCircularVariance[i],
                accumulatedTurnAbs: Float(rolloutSummary.accumulatedTurnAbs[i]),
                survivalSteps: metrics.survivalSteps,
                activityEacMean: activitySummary.flatMap { mean($0.eac) } ?? metrics.activityEacMean,
                activityEanMean: activitySummary.flatMap { mean($0.ean) } ?? metrics.activityEanMean,
                activityDiversityMean: activitySummary.flatMap { mean($0.diversity) } ?? metrics.activityDiversityMean,
                activitySpeciesMean: activitySummary.flatMap { mean($0.speciesCount) } ?? metrics.activitySpeciesMean,
                activitySpeciesMax: morphometrics.activitySpeciesMax,
                activitySpeciesStd: morphometrics.activitySpeciesStd,
                activityDiversityStd: morphometrics.activityDiversityStd,
                activityEacMax: morphometrics.activityEacMax,
                activityEanMax: morphometrics.activityEanMax,
                componentSeriesMean: componentSeriesStats.mean,
                componentSeriesStd: componentSeriesStats.std,
                componentSeriesMax: componentSeriesStats.max
            )
            let terminalDescriptor = MorphospaceTerminalDescriptor(
                massChannel: searchConfig.massChannel,
                borderMode: runtimeConfig.border,
                symmetryPolicy: "translation_kernel_permutation_v1",
                fingerprintResolution: finalSampleSummary.fingerprintResolution,
                fingerprintU8: finalSampleSummary.fingerprintU8,
                angularSymmetry: finalSampleSummary.angularSymmetry,
                fingerprintHash12: finalSampleSummary.fingerprintHash12,
                finalMass: finalSampleSummary.finalMass,
                finalOccupancy: finalSampleSummary.finalOccupancy,
                finalGyration: finalSampleSummary.finalGyration,
                momentMass: metrics.momentMass,
                momentVolume: metrics.momentVolume,
                momentDensity: metrics.momentDensity,
                momentAnisotropy: metrics.momentAnisotropy,
                componentCount: metrics.componentCount,
                largestComponentFraction: metrics.largestComponentFraction,
                largestComponentAnisotropy: metrics.largestComponentAnisotropy,
                hu1: metrics.hu1,
                hu2: metrics.hu2,
                hu3: metrics.hu3,
                hu4: metrics.hu4,
                hu5: metrics.hu5,
                hu6: metrics.hu6,
                hu7: metrics.hu7,
                flusser1: metrics.flusser1,
                flusser2: metrics.flusser2,
                flusser3: metrics.flusser3,
                flusser4: metrics.flusser4,
                windowMassStd: rolloutSummary.windowMassStd?[i],
                windowOccupancyStd: rolloutSummary.windowOccupancyStd?[i],
                windowGyrationStd: rolloutSummary.windowGyrationStd?[i],
                isStable: metrics.isStable
            )
            let descriptorBundle = MorphospaceDescriptorBundle(
                symmetryPolicy: "translation_kernel_permutation_v1",
                genotype: genotypeDescriptor,
                terminal: terminalDescriptor,
                trajectory: trajectoryDescriptor
            )
            results.append(BatchSimulationResult(
                seed: seed,
                initSeed: seed + initSeedOffset,
                metrics: metrics,
                params: runtimeConfig.params,
                activity: activitySnapshots,
                initialConditionFamily: initialConditionFamily,
                descriptorBundle: descriptorBundle,
                terminalStatePatch: terminalStatePatches?[i],
                terminalParamPatch: terminalParamPatches?[i]
            ))
        }
        return results
    }

    func massMapFromBatch(_ batch: MLXArray, searchConfig: SearchConfig) -> MLXArray {
        let batchSize = batch.shape[0]
        if searchConfig.massChannel == -1 {
            if excludedMassChannels.isEmpty {
                return batch.sum(axis: -1)
            }
            var summed = MLX.zeros([batchSize, runtimeConfig.sx, runtimeConfig.sy])
            for channel in 0..<runtimeConfig.channels {
                if !excludedMassChannels.contains(channel) {
                    summed = summed + batch[0..., 0..., 0..., channel]
                }
            }
            return summed
        }
        return batch[0..., 0..., 0..., searchConfig.massChannel]
    }

    private func materializeFullWorldPatches(batch: MLXArray) -> [InitStatePatchConfig] {
        eval(batch)
        let shape = batch.shape
        guard shape.count == 4 else {
            fatalError("Expected full state batch to have shape [batch, sx, sy, channels], got \(shape)")
        }
        let batchCount = shape[0]
        let sx = shape[1]
        let sy = shape[2]
        let channels = shape[3]
        let sampleSize = sx * sy * channels
        let flat = batch.asArray(Float.self)
        if flat.count != batchCount * sampleSize {
            fatalError("Full state batch size mismatch: expected \(batchCount * sampleSize), got \(flat.count)")
        }
        return (0..<batchCount).map { index in
            let start = index * sampleSize
            let end = start + sampleSize
            return InitStatePatchConfig(
                center: [sx / 2, sy / 2],
                width: sx,
                height: sy,
                channels: channels,
                values: Array(flat[start..<end])
            )
        }
    }

    private func mean(_ values: [Float]) -> Float? {
        guard !values.isEmpty else { return nil }
        let sum = values.reduce(0, +)
        return sum / Float(values.count)
    }

    private func mean(_ values: [Int]) -> Float? {
        guard !values.isEmpty else { return nil }
        let sum = values.reduce(0, +)
        return Float(sum) / Float(values.count)
    }

    private func zipOptional<T, U>(_ lhs: T?, _ rhs: U?) -> (T, U)? {
        guard let lhs, let rhs else { return nil }
        return (lhs, rhs)
    }

    private func isStableCreature(
        config: StabilityConfig,
        metrics: SimulationMetrics,
        finalMass: Float,
        massMin: Float,
        massMax: Float,
        windowMassStd: Float?,
        windowOccupancyStd: Float?,
        windowGyrationStd: Float?
    ) -> Bool {
        guard config.enabled else { return false }

        let gridArea = Float(runtimeConfig.sx * runtimeConfig.sy)
        let minMass = gridArea * config.massMinFraction
        let maxMass = gridArea * config.massMaxFraction

        if finalMass < minMass || finalMass > maxMass { return false }
        if config.requireSurvival {
            if massMin < minMass || massMax > maxMass { return false }
        }

        if let limit = config.windowMassStdMax {
            guard let value = windowMassStd else {
                fatalError("stability.window_mass_std_max requires window statistics.")
            }
            if value > limit { return false }
        }
        if let limit = config.windowOccupancyStdMax {
            guard let value = windowOccupancyStd else {
                fatalError("stability.window_occupancy_std_max requires window statistics.")
            }
            if value > limit { return false }
        }
        if let limit = config.windowGyrationStdMax {
            guard let value = windowGyrationStd else {
                fatalError("stability.window_gyration_std_max requires window statistics.")
            }
            if value > limit { return false }
        }

        if !config.filters.isEmpty && !passesFilters(metrics, filters: config.filters) {
            return false
        }

        return true
    }
}
