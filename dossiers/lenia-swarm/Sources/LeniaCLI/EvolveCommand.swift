import ArgumentParser
import Foundation
import LeniaCore
import Logging

func evolveCreatureChannelCount(
    channels: Int,
    chemotaxis: ChemotaxisConfig?,
    food: FoodConfig?,
    obstacleField: ESObstacleFieldConfig?
) -> Int {
    flowCreatureChannels(
        channels: channels,
        chemotaxis: chemotaxis,
        food: food,
        additionalExcludedChannels: obstacleField.map { $0.enabled ? [$0.channelIndex] : [] } ?? []
    ).count
}

func replacingNonPositiveKernelWeights(
    in params: KernelParams,
    with replacement: Float
) throws -> KernelParams {
    guard replacement > 0 else {
        throw ValidationError("--seed-kernel-zero-weight must be > 0.")
    }
    return KernelParams(
        r: params.r,
        b: params.b,
        w: params.w.map { row in row.map { $0 <= 0 ? replacement : $0 } },
        a: params.a,
        m: params.m,
        s: params.s,
        h: params.h,
        R: params.R
    )
}

private func validateEvolutionSequenceMetricConfig(_ esConfig: ESConfig) throws {
    let fitness = esConfig.fitness
    let usesTrajectoryMetrics = fitness.trajectoryPathLengthPenalty != nil ||
        fitness.trajectoryPathLengthReward != nil ||
        fitness.trajectoryDisplacementPenalty != nil ||
        fitness.trajectoryDisplacementReward != nil ||
        fitness.movementEfficiencyPenalty != nil ||
        fitness.movementEfficiencyReward != nil ||
        fitness.centerVelocityPenalty != nil ||
        fitness.centerVelocityReward != nil
    let usesOrientationPhaseMotion = fitness.orientationPhaseMotionReward != nil ||
        fitness.orientationPhaseMotionPenalty != nil
    let usesAngularPhaseMotion = fitness.angularPhaseMotionReward != nil ||
        fitness.angularPhaseMotionPenalty != nil
    let usesSectorTransport = fitness.sectorTransportReward != nil ||
        fitness.sectorTransportPenalty != nil
    let usesSequenceMetrics = usesTrajectoryMetrics ||
        usesOrientationPhaseMotion ||
        usesAngularPhaseMotion ||
        usesSectorTransport
    guard usesSequenceMetrics else {
        return
    }

    let normalizedSteps = Array(Set(fitness.templateSequenceSteps ?? [fitness.targetStep])).sorted()
    guard normalizedSteps.count >= 2 else {
        throw ValidationError(
            "trajectory, orientation, angular, and sector ES metrics require at least two unique template_sequence_steps."
        )
    }
    if let invalidStep = normalizedSteps.first(where: { $0 < 0 || $0 > esConfig.steps }) {
        throw ValidationError("template_sequence_steps entries must be within 0...\(esConfig.steps); found \(invalidStep).")
    }
}

struct EvolveCommand: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "evolve",
        abstract: "Run evolutionary optimization (ES) on Lenia parameters"
    )

    @Option(name: .long, help: "Path to base config.json")
    var config: String

    @Option(name: .long, help: "Path to ES config.json")
    var es: String

    @Option(name: .long, help: "Requested backend: auto|metal-full|mlx")
    var backend: String = "auto"

    @Option(name: .shortAndLong, help: "Output directory (overrides es config)")
    var output: String?

    @Option(name: .long, help: "Path to library/index.jsonl or exports/index.jsonl used to seed the initial patch")
    var seedLibrary: String?

    @Option(name: .long, help: "Optional qd-2024 config directory when the seed library comes from qd-2024 and pattern assets are missing")
    var seedQDConfigDir: String?

    @Option(name: .long, parsing: .upToNextOption, help: "QD cell ids to use for warm starts when the seed library comes from qd-2024")
    var seedCell: [Int] = []

    @OptionGroup
    var seedSelection: ResearchSeedSelectionOptions

    @Flag(name: .long, help: "Also warm-start ES kernel parameters from the selected research seed when available")
    var seedKernelParams: Bool = false

    @Option(name: .long, help: "When using --seed-kernel-params, replace non-positive seed kernel weights with this explicit value")
    var seedKernelZeroWeight: Float?

    @Option(name: .long, help: "Warmup steps used when expressing a research seed patch; use 0 to preserve the original initialization")
    var seedWarmupSteps: Int?

    @Flag(name: .long, help: "Validate configs and exit without running")
    var validateOnly: Bool = false

    @OptionGroup
    var promotion: ArchivePromotionOptions

    @OptionGroup
    var logOptions: LogOptions

    func run() async throws {
        let resolvedRunId = resolveRunID(prefix: "local", logOptions: logOptions)
        let logging = try bootstrapRunLogging(
            runID: resolvedRunId,
            role: "evolve",
            loggerLabel: "LeniaSwarm.Evolve",
            logStem: "evolve",
            outputForLogs: output,
            logOptions: logOptions,
            dossier: dossierName
        )
        let logger = logging.logger

        logLoggingInitialized(logger, runID: resolvedRunId, logging: logging)

        if seedKernelZeroWeight != nil && !seedKernelParams {
            throw ValidationError("--seed-kernel-zero-weight requires --seed-kernel-params.")
        }
        if let seedWarmupSteps, seedWarmupSteps < 0 {
            throw ValidationError("--seed-warmup-steps must be >= 0.")
        }

        logger.info("Loading configs...")

        // Load base config
        let baseConfigURL = URL(fileURLWithPath: config)
        let sourceBaseConfigData = try Data(contentsOf: baseConfigURL)

        // Load ES config
        var esConfig = try loadESConfig(path: es)
        func withOutput(
            _ outputPath: String,
            initialInitPatchValues: [Float]? = esConfig.initialInitPatchValues,
            initialKernelParams: KernelParams? = esConfig.initialKernelParams
        ) -> ESConfig {
            ESConfig(
                outputDir: outputPath,
                generations: esConfig.generations,
                population: esConfig.population,
                sigma: esConfig.sigma,
                learningRate: esConfig.learningRate,
                seed: esConfig.seed,
                steps: esConfig.steps,
                fitness: esConfig.fitness,
                fitnessShaping: esConfig.fitnessShaping,
                includeParent: esConfig.includeParent,
                initPatch: esConfig.initPatch,
                initialInitPatchValues: initialInitPatchValues,
                initialKernelParams: initialKernelParams,
                paramRanges: esConfig.paramRanges,
                obstacleField: esConfig.obstacleField
            )
        }
        esConfig = withOutput(try resolvePath(esConfig.outputDir, dossier: dossierName))

        // Override output dir if specified
        if let output = output {
            esConfig = withOutput(try resolvePath(output, dossier: dossierName))
        }

        let sourceRuntimeConfig = try loadRuntimeConfig(from: sourceBaseConfigData)
        let resolvedBackend = try resolveMetalFirstEvolutionBackend(
            requestValue: backend,
            runtimeConfig: sourceRuntimeConfig,
            esConfig: esConfig
        )
        let baseConfigData = try baseConfigDataBySettingBackend(sourceBaseConfigData, backend: resolvedBackend)
        let baseConfig = try JSONDecoder().decode(LeniaBaseConfig.self, from: baseConfigData)
        let runtimeConfig = try loadRuntimeConfig(from: baseConfigData)

        if let seedLibrary {
            let canSeedInitPatch = esConfig.initPatch?.enabled == true
            if !canSeedInitPatch && !seedKernelParams {
                throw ValidationError("--seed-library without --seed-kernel-params requires init_patch.enabled in the ES config.")
            }
            let resolvedSeedLibrary = try resolveArtifactPath(seedLibrary, dossier: dossierName)
            let resolvedQDConfigDir = try seedQDConfigDir.map { try resolvePath($0, dossier: dossierName) }
            let selection = try seedSelection.resolvedSelection()
            let patches = try loadResearchSeedPatches(
                libraryURL: URL(fileURLWithPath: resolvedSeedLibrary),
                qdConfigDirectoryOverride: resolvedQDConfigDir.map { URL(fileURLWithPath: $0, isDirectory: true) },
                cells: seedCell.isEmpty ? nil : seedCell,
                warmupSteps: seedWarmupSteps,
                selection: selection
            )
            let patch = try resolveSingleResearchSeedPatch(
                patches: patches,
                libraryPath: resolvedSeedLibrary,
                commandName: "evolve",
                selection: selection
            )
            let patchValues: [Float]?
            if let initPatch = esConfig.initPatch, initPatch.enabled {
                let creatureChannelCount = evolveCreatureChannelCount(
                    channels: runtimeConfig.channels,
                    chemotaxis: runtimeConfig.chemotaxis,
                    food: runtimeConfig.food,
                    obstacleField: esConfig.obstacleField
                )
                patchValues = try researchSeedCenterCropPatchValues(
                    patch: patch,
                    size: initPatch.size,
                    outputChannels: creatureChannelCount
                )
            } else {
                patchValues = esConfig.initialInitPatchValues
            }
            let kernelParams: KernelParams?
            if seedKernelParams {
                guard let seedKernelParams = patch.kernelParams else {
                    throw ValidationError("--seed-kernel-params requested, but selected seed '\(patch.name)' has no kernel parameters.")
                }
                kernelParams = try seedKernelZeroWeight.map {
                    try replacingNonPositiveKernelWeights(in: seedKernelParams, with: $0)
                } ?? seedKernelParams
            } else {
                kernelParams = esConfig.initialKernelParams
            }
            esConfig = withOutput(
                esConfig.outputDir,
                initialInitPatchValues: patchValues,
                initialKernelParams: kernelParams
            )
            if canSeedInitPatch {
                logger.info("Using research seed warm start '\(patch.name)' for evolve init patch")
            }
            if seedKernelParams {
                logger.info("Using research seed warm start '\(patch.name)' for evolve kernel parameters")
            }
        }

        // Get parameter ranges
        let ranges: [String: (Float, Float)]
        if let esRanges = esConfig.paramRanges {
            ranges = esRanges.mapValues { ($0[0], $0[1]) }
        } else {
            ranges = try extractRangesFromConfig(baseConfig)
        }
        try validateEvolutionSequenceMetricConfig(esConfig)

        if validateOnly {
            logger.info("Configs validated successfully (backend=\(resolvedBackend.rawValue))")
            return
        }

        // Create output directory
        let outputDir = URL(fileURLWithPath: esConfig.outputDir)
        try FileManager.default.createDirectory(at: outputDir, withIntermediateDirectories: true)

        // Save configs
        try baseConfigData.write(to: outputDir.appendingPathComponent("config.json"))
        let resolvedESConfigData = try JSONEncoder().encode(esConfig)
        try resolvedESConfigData.write(to: outputDir.appendingPathComponent("es_config.json"))

        logger.info("============================================================")
        logger.info("Flow Lenia Evolution Strategy")
        logger.info("============================================================")
        logger.info("Generations: \(esConfig.generations)")
        logger.info("Population: \(esConfig.population)")
        logger.info("Sigma: \(esConfig.sigma)")
        logger.info("Learning rate: \(esConfig.learningRate)")
        logger.info("Steps per eval: \(esConfig.steps)")
        logger.info("Objective: \(esConfig.fitness.objective)")
        logger.info("Backend: \(runtimeConfig.backend.rawValue)")
        logger.info("Fitness shaping: \(esConfig.fitnessShaping)")
        logger.info("Output: \(esConfig.outputDir)")
        logger.info("============================================================")

        // Create evolution engine
        let evo = EvolutionEngine(
            runtimeConfig: runtimeConfig,
            esConfig: esConfig,
            ranges: ranges
        )

        // Open history file
        let historyURL = outputDir.appendingPathComponent("history.jsonl")
        FileManager.default.createFile(atPath: historyURL.path, contents: nil)
        let historyHandle = try FileHandle(forWritingTo: historyURL)
        defer { try? historyHandle.close() }

        var bestFitness: Float = -.infinity
        var bestGen = 0
        var overallBestCandidate: [Float]?
        let configHash = try researchConfigHash([
            ("base", researchEncodedJSON(baseConfig)),
            ("es", resolvedESConfigData),
        ])

        // Run evolution loop
        for gen in 0..<esConfig.generations {
            let genStart = ContinuousClock.now
            let result = evo.runGeneration(gen: gen)
            let elapsed = genStart.duration(to: ContinuousClock.now)
            let elapsedMs =
                Double(elapsed.components.seconds) * 1_000.0 +
                Double(elapsed.components.attoseconds) / 1_000_000_000_000_000.0
            let candidateEvalPerSecond = elapsedMs > 0
                ? Double(esConfig.population) / (elapsedMs / 1_000.0)
                : nil
            let simStepsPerSecond = elapsedMs > 0
                ? Double(esConfig.population * esConfig.steps) / (elapsedMs / 1_000.0)
                : nil

            if result.bestFitness > bestFitness {
                bestFitness = result.bestFitness
                bestGen = gen
                overallBestCandidate = result.bestCandidate

                // Save best params
                let bestParams = vectorToParams(
                    Array(result.bestCandidate[0..<evo.thetaParamsDim]),
                    space: evo.paramSpace
                )
                let bestResult = ESBestResult(
                    generation: gen,
                    fitness: bestFitness,
                    params: bestParams.toKernelParams()
                )
                let bestData = try JSONEncoder().encode(bestResult)
                try bestData.write(to: outputDir.appendingPathComponent("best.json"))

                // Save best config (with explicit params)
                let bestConfig = evolveBaseConfigWithExplicitParams(baseConfig, params: bestParams)
                let bestConfigData = try JSONEncoder().encode(bestConfig)
                try bestConfigData.write(to: outputDir.appendingPathComponent("best_config.json"))
            }

            // Log progress
            let progressLine = String(
                format: "Gen %d: best=%.4f mean=%.4f std=%.4f wall_ms=%.1f evals_per_s=%.2f steps_per_s=%.2f rollout_ms=%.1f kernel_ms=%.1f fitness_ms=%.1f (overall best=%.4f @ gen %d)",
                gen,
                result.bestFitness,
                result.meanFitness,
                result.fitnessStd,
                elapsedMs,
                candidateEvalPerSecond ?? 0.0,
                simStepsPerSecond ?? 0.0,
                result.profile.rolloutMs,
                result.profile.kernelCompileMs,
                result.profile.fitnessMs,
                bestFitness,
                bestGen
            )
            logger.info("\(progressLine)")

            // Write history
            let historyEntry = ESHistoryEntry(
                generation: gen,
                fitnessMean: result.meanFitness,
                fitnessStd: result.fitnessStd,
                fitnessBest: result.bestFitness,
                fitnessShaping: esConfig.fitnessShaping,
                generationWallMs: elapsedMs,
                candidateEvalPerSecond: candidateEvalPerSecond,
                simStepsPerSecond: simStepsPerSecond,
                candidateSetupMs: result.profile.candidateSetupMs,
                kernelCompileMs: result.profile.kernelCompileMs,
                stateBuildMs: result.profile.stateBuildMs,
                fieldBuildMs: result.profile.fieldBuildMs,
                rolloutMs: result.profile.rolloutMs,
                fitnessMs: result.profile.fitnessMs,
                optimizerMs: result.profile.optimizerMs
            )
            let historyData = try JSONEncoder().encode(historyEntry)
            historyHandle.write(historyData)
            historyHandle.write("\n".data(using: .utf8)!)
        }

        logger.info("============================================================")
        logger.info("Evolution Complete")
        logger.info("============================================================")
        logger.info("Best fitness: \(String(format: "%.4f", bestFitness)) (generation \(bestGen))")
        logger.info("Results saved to: \(esConfig.outputDir)")

        if let overallBestCandidate {
            let overallBestParams = vectorToParams(
                Array(overallBestCandidate[0..<evo.thetaParamsDim]),
                space: evo.paramSpace
            )
            let evaluation = evo.evaluateCandidateForResearchExport(overallBestCandidate)
            let creature = evolveWinnerCreature(
                runId: resolvedRunId,
                objective: esConfig.fitness.objective,
                configHash: configHash,
                fitness: bestFitness,
                evaluation: evaluation
            )
            let libraryEntry = try evolveLibraryEntry(
                runId: resolvedRunId,
                objective: esConfig.fitness.objective,
                generation: bestGen,
                bestCandidate: overallBestCandidate,
                esConfig: esConfig,
                configHash: configHash,
                fitness: bestFitness,
                evaluation: evaluation,
                creature: creature
            )
            let replayWinnerBaseConfig = evolveBaseConfigWithExplicitParams(baseConfig, params: overallBestParams)
            let replayBaseConfig = buildEvolveReplayBaseConfig(baseConfig: replayWinnerBaseConfig, esConfig: esConfig)
            let replaySearchConfig = buildStrictReplaySearchConfig(
                steps: esConfig.steps,
                initSeedOffset: creature.initialCondition.seed,
                morphologyThreshold: esConfig.fitness.morphologyThreshold ?? 0.03
            )
            _ = try persistResearchArchiveArtifacts(
                runDirectory: outputDir,
                libraryEntries: [libraryEntry],
                exportRoot: outputDir.appendingPathComponent("exports", isDirectory: true),
                exportItems: [creature],
                emptyExportMessage: "Export bundle already exists for flow-tasks winner \(creature.name)."
            ) { creature in
                (
                    baseConfig: replayBaseConfig,
                    searchConfig: replaySearchConfig,
                    creature: creature,
                    runId: resolvedRunId,
                    campaignId: nil,
                    score: bestFitness,
                    filtersPassed: nil,
                    reason: "flow-tasks:\(esConfig.fitness.objective)"
                )
            }
        }

        let resolvedPromotion = try promoteIfConfigured(
            options: promotion,
            defaultCompendiumPath: outputDir.appendingPathComponent("compendium.sqlite").path,
            dossier: dossierName,
            defaultEnabled: true,
            runDir: outputDir.path,
            includeResults: true
        )
        if let compendiumPath = resolvedPromotion.compendiumPath {
            logger.info("Promoted evolve run into compendium: \(compendiumPath)")
        }
    }
}

private func evolveBaseConfigWithExplicitParams(
    _ baseConfig: LeniaBaseConfig,
    params: ResolvedParams
) -> LeniaBaseConfig {
    var explicitConfig = baseConfig
    explicitConfig.params = ParamsConfig(
        mode: "explicit",
        seed: nil,
        ranges: nil,
        r: params.r,
        b: params.b,
        w: params.w,
        a: params.a,
        m: params.m,
        s: params.s,
        h: params.h,
        R: params.R
    )
    return explicitConfig
}

private func evolveWinnerCreature(
    runId: String,
    objective: String,
    configHash: String,
    fitness: Float,
    evaluation: ESEvaluatedCreatureExport
) -> SavedCreature {
    archivedCreatureFromResult(
        stableKey: "\(runId)|\(objective)|0",
        name: "task-\(objective)-0",
        ownerId: "flow-tasks",
        result: evaluation.resultData,
        initialCondition: evaluation.initConfig,
        configHash: configHash,
        score: fitness,
        scoreWeights: ["fitness": 1.0]
    )
}

func buildEvolveReplayBaseConfig(
    baseConfig: LeniaBaseConfig,
    esConfig: ESConfig
) -> LeniaBaseConfig {
    let obstacleField: ObstacleFieldConfig?
    if let esObstacle = esConfig.obstacleField, esObstacle.enabled {
        obstacleField = ObstacleFieldConfig(
            enabled: true,
            channel_index: esObstacle.channelIndex,
            mode: esObstacle.mode,
            count: esObstacle.count,
            circle_radius: esObstacle.circleRadius,
            sigma: esObstacle.sigma,
            amplitude: esObstacle.amplitude,
            center: esObstacle.center ?? [Float(baseConfig.grid.sx) / 2.0, Float(baseConfig.grid.sy) / 2.0],
            seed: esObstacle.seed
        )
    } else {
        obstacleField = baseConfig.obstacle_field
    }
    return LeniaBaseConfig(
        backend: baseConfig.backend,
        profile: baseConfig.profile,
        grid: baseConfig.grid,
        channels: baseConfig.channels,
        connectivity: baseConfig.connectivity,
        flow: baseConfig.flow,
        implementation: baseConfig.implementation,
        reintegration: baseConfig.reintegration,
        parameter_embedding: baseConfig.parameter_embedding,
        chemotaxis: baseConfig.chemotaxis,
        obstacle_field: obstacleField,
        food: baseConfig.food,
        walls: baseConfig.walls,
        environment: baseConfig.environment,
        beam_mutation: baseConfig.beam_mutation,
        params: baseConfig.params,
        init: baseConfig.`init`,
        run: baseConfig.run,
        interventions: baseConfig.interventions
    )
}

private func evolveLibraryEntry(
    runId: String,
    objective: String,
    generation: Int,
    bestCandidate: [Float],
    esConfig: ESConfig,
    configHash: String,
    fitness: Float,
    evaluation: ESEvaluatedCreatureExport,
    creature: SavedCreature
) throws -> ResearchLibraryEntry {
    var metadata: [String: AnyCodable] = try [
        "version": researchMetadataValue(1),
        "mode": researchMetadataValue("flow-tasks"),
        "morphospace_payload": researchMetadataValue("summary_only_metrics_v1"),
        "morphospace_ready": researchMetadataValue(false),
        "canonical_export_available": researchMetadataValue(true),
        "canonical_export_kind": researchMetadataValue("strict_replay_bundle_v1"),
        "task": researchMetadataValue(objective),
        "generation": researchMetadataValue(generation),
        "fitness": researchMetadataValue(fitness),
        "export_evaluation_fitness": researchMetadataValue(evaluation.fitness),
        "fitness_shaping": researchMetadataValue(esConfig.fitnessShaping),
        "winner_rank": researchMetadataValue(0),
        "init_patch_values": researchMetadataValue(evaluation.initPatchValues ?? NSNull()),
        "candidate_vector": researchMetadataValue(bestCandidate),
    ]
    if let finalMorphology = evaluation.finalMorphology {
        metadata["es_final_morphology"] = try researchMetadataValue(finalMorphology.metadataPayload)
        metadata["es_morphology_guard_failed"] = try researchMetadataValue(finalMorphology.guardFailed)
    }
    return archiveResearchLibraryEntry(
        creature: creature,
        runId: runId,
        configHash: configHash,
        sourceMode: "flow-tasks",
        sourceAlgorithm: "openes",
        researchMetadata: metadata
    )
}
