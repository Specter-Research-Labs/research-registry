import ArgumentParser
import Foundation
import LeniaCore
import Logging

struct DeclarativeCampaignPhaseSummary: Codable {
    let name: String
    let type: LeniaCampaignPhaseType
    let creaturesFound: Int
    let coverage: Float?
    let elapsedSeconds: Double
    let error: String?
}

struct DeclarativeCampaignSummary: Codable {
    let name: String
    let runID: String
    let phases: [DeclarativeCampaignPhaseSummary]
    let totalCreatures: Int
    let totalElapsedSeconds: Double
    let failedPhases: Int
}

private struct CampaignPhaseExecutionContext {
    let phaseOutputURL: URL
    let dossierRoot: URL
    let campaignConfigDirectory: URL
    let runID: String
    let backendRequest: String
    let logger: Logger
    let startTime: Date

    func resolve(_ path: String) -> URL {
        resolveCampaignRelativePath(
            path,
            configDirectory: campaignConfigDirectory,
            dossierRoot: dossierRoot
        )
    }

    func seedLibraryURL(_ path: String?) -> URL? {
        guard let path else {
            return nil
        }
        return resolve(path)
    }

    func localRequest(
        phase: LeniaCampaignPhaseConfig,
        preset: LeniaCampaignPreset,
        configURL: URL,
        seedLibraryURL: URL? = nil,
        seedQDConfigDirURL: URL? = nil,
        seedSelection: ResearchSeedSelection? = nil,
        exportBest: Int? = nil
    ) -> CampaignExecutionRequest {
        makeLocalCampaignRequest(
            runID: "\(runID)-\(phase.name)",
            preset: preset,
            configURL: configURL,
            outputURL: phaseOutputURL,
            backendRequest: backendRequest,
            seedLibraryURL: seedLibraryURL,
            seedQDConfigDirURL: seedQDConfigDirURL,
            seedSelection: seedSelection,
            exportBest: exportBest
        )
    }

    func result(
        phase: LeniaCampaignPhaseConfig,
        type: LeniaCampaignPhaseType,
        creaturesFound: Int,
        coverage: Float? = nil
    ) -> LeniaCampaignPhaseResult {
        LeniaCampaignPhaseResult(
            phaseName: phase.name,
            phaseType: type,
            creaturesFound: creaturesFound,
            coverage: coverage,
            elapsedSeconds: Date().timeIntervalSince(startTime),
            error: nil,
            outputDirectory: phaseOutputURL
        )
    }
}

func executeDeclarativePhase(
    phase: LeniaCampaignPhaseConfig,
    phaseOutputURL: URL,
    dossierRoot: URL,
    campaignConfigDirectory: URL,
    runID: String,
    backendRequest: String,
    logger: Logger
) throws -> LeniaCampaignPhaseResult {
    let context = CampaignPhaseExecutionContext(
        phaseOutputURL: phaseOutputURL,
        dossierRoot: dossierRoot,
        campaignConfigDirectory: campaignConfigDirectory,
        runID: runID,
        backendRequest: backendRequest,
        logger: logger,
        startTime: Date()
    )

    switch phase.type {
    case .qd:
        return try executeQDPhase(phase: phase, context: context)
    case .imgep:
        return try executeIMGEPPhase(phase: phase, context: context)
    case .sweep:
        return try executeSweepPhase(phase: phase, context: context)
    case .interventionBattery:
        return try executeInterventionBatteryPhase(phase: phase, context: context)
    case .ecology:
        return try executeEcologyPhase(phase: phase, context: context)
    case .curiosity:
        return try executeCuriosityPhase(phase: phase, context: context)
    }
}

private func executeLocalPlannedPhase(
    phase: LeniaCampaignPhaseConfig,
    type: LeniaCampaignPhaseType,
    context: CampaignPhaseExecutionContext,
    request: CampaignExecutionRequest,
    jobs: [LeniaCampaignJob],
    metricsTransform: ((inout [LeniaCampaignMetricRecord]) -> Void)? = nil,
    creaturesFound: (LeniaCampaignJobExecution) -> Int,
    postCompendiumIngest: ((LeniaCampaignJobExecution, String) throws -> Void)? = nil
) throws -> LeniaCampaignPhaseResult {
    let execution = try executeLocalCampaignPhase(
        request: request,
        jobs: jobs,
        logger: context.logger,
        metricsTransform: metricsTransform,
        postCompendiumIngest: postCompendiumIngest
    )
    return context.result(
        phase: phase,
        type: type,
        creaturesFound: creaturesFound(execution)
    )
}

private func executeQDPhase(
    phase: LeniaCampaignPhaseConfig,
    context: CampaignPhaseExecutionContext
) throws -> LeniaCampaignPhaseResult {
    guard let configDir = phase.configDir else {
        throw ValidationError("QD phase '\(phase.name)' requires config_dir.")
    }
    let configDirURL = context.resolve(configDir)
    let bundle = try loadLeniaBreeder2024ConfigBundle(configDirectory: configDirURL)
    let algorithm = phase.algorithm ?? "me"
    let seeds = phase.seeds ?? [0]

    var totalOccupied = 0
    var bestCoverage: Float = 0

    for seed in seeds {
        let seedOutputURL = context.phaseOutputURL.appendingPathComponent("seed-\(seed)", isDirectory: true)
        try FileManager.default.createDirectory(at: seedOutputURL, withIntermediateDirectories: true)
        let runner = LeniaBreeder2024Runner(configs: bundle, logger: context.logger, seed: seed)

        let summary: LeniaBreeder2024RunSummary
        switch algorithm {
        case "aurora":
            summary = try runner.runAURORA(outputDirectory: seedOutputURL, runId: "\(context.runID)-\(phase.name)-seed-\(seed)")
        default:
            summary = try runner.runMAPElites(outputDirectory: seedOutputURL, runId: "\(context.runID)-\(phase.name)-seed-\(seed)")
        }
        totalOccupied += summary.occupiedCells
        bestCoverage = max(bestCoverage, summary.coverage)
        context.logger.info("QD seed \(seed): \(summary.occupiedCells) cells, coverage=\(String(format: "%.3f", summary.coverage)), qd_score=\(String(format: "%.2f", summary.qdScore))")

        try runCampaignCompendiumIndex(outputURL: seedOutputURL)
    }

    return context.result(
        phase: phase,
        type: .qd,
        creaturesFound: totalOccupied,
        coverage: bestCoverage
    )
}

private func executeIMGEPPhase(
    phase: LeniaCampaignPhaseConfig,
    context: CampaignPhaseExecutionContext
) throws -> LeniaCampaignPhaseResult {
    guard let imgepConfigPath = phase.config,
          let baseConfigPath = phase.baseConfig,
          let searchConfigPath = phase.searchConfig else {
        throw ValidationError("IMGEP phase '\(phase.name)' requires config, base_config, and search_config.")
    }

    let imgepConfigURL = context.resolve(imgepConfigPath)
    let baseConfigURL = context.resolve(baseConfigPath)
    let searchConfigURL = context.resolve(searchConfigPath)

    let baseConfigData = try Data(contentsOf: baseConfigURL)
    let baseConfig = try JSONDecoder().decode(LeniaBaseConfig.self, from: baseConfigData)
    let parsedSearchConfig = try JSONDecoder().decode(ParsedSearchConfig.self, from: Data(contentsOf: searchConfigURL))
    let imgepConfig = try JSONDecoder().decode(IMGEPConfig.self, from: Data(contentsOf: imgepConfigURL))

    guard let ranges = baseConfig.params.ranges else {
        throw ValidationError("IMGEP phase '\(phase.name)' requires params.ranges in base config.")
    }

    let iterations = phase.target?.iterations ?? imgepConfig.iterations
    let (c0, _) = connFromMatrix(baseConfig.connectivity)
    let nbK = c0.count
    let implementation = resolveImplementationSettings(
        implementation: baseConfig.implementation,
        border: baseConfig.reintegration.border
    )
    let baseOverrides: [String: Any] = parsedSearchConfig.overridesAsDict()
    let initSeedOffset = parsedSearchConfig.initSeedOffset ?? 0
    let simSearchConfig = parsedSearchConfig.toSearchConfig()

    try baseConfigData.write(to: context.phaseOutputURL.appendingPathComponent("config.json"))

    let resultsURL = context.phaseOutputURL.appendingPathComponent("results.jsonl")
    let historyURL = context.phaseOutputURL.appendingPathComponent("history.jsonl")
    FileManager.default.createFile(atPath: resultsURL.path, contents: nil)
    FileManager.default.createFile(atPath: historyURL.path, contents: nil)
    let resultsHandle = try FileHandle(forWritingTo: resultsURL)
    let historyHandle = try FileHandle(forWritingTo: historyURL)
    defer {
        try? resultsHandle.close()
        try? historyHandle.close()
    }

    var history: [IMGEPHistoryEntry] = []
    var topResults: [SimulationResultData] = []
    var rng = SeededRandomNumberGenerator(seed: UInt64(parsedSearchConfig.seedStart))
    var nextSeed = parsedSearchConfig.seedStart

    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    var iteration = 0

    while iteration < iterations {
        let remaining = iterations - iteration
        let batchCount = min(imgepConfig.batchSize, remaining)

        for batchIdx in 0..<batchCount {
            let globalIteration = iteration + batchIdx

            let trialParams: KernelParams
            let trialGoal: [Float]?

            if globalIteration < imgepConfig.warmupIterations || history.isEmpty {
                let paramSeed = Int.random(in: 0...Int.max, using: &rng)
                let resolved = generateRandomParams(seed: paramSeed, nbK: nbK, ranges: ranges)
                trialParams = resolved.toKernelParams()
                trialGoal = nil
            } else {
                let bounds: [(min: Float, max: Float)]
                if imgepConfig.goal.boundsMode == "fixed" {
                    bounds = imgepConfig.goal.features.map { feature in
                        let range = imgepConfig.goal.bounds![feature]!
                        return (min: range[0], max: range[1])
                    }
                } else {
                    bounds = boundsFromHistory(history: history)
                }
                let goal = sampleGoal(bounds: bounds, rng: &rng)
                let idx = nearestNeighborIndex(goal: goal, history: history)
                let base = history[idx].params
                trialParams = mutateParams(base: base, ranges: ranges, config: imgepConfig.mutation, rng: &rng)
                trialGoal = goal
            }

            let trialSeeds = (0..<imgepConfig.seedsPerCandidate).map { i in
                nextSeed + i * parsedSearchConfig.seedStride
            }
            nextSeed += imgepConfig.seedsPerCandidate * parsedSearchConfig.seedStride

            var overrides = baseOverrides
            overrides["params.mode"] = "explicit"
            overrides["params.r"] = trialParams.r.map { Double($0) }
            overrides["params.b"] = trialParams.b.map { $0.map { Double($0) } }
            overrides["params.w"] = trialParams.w.map { $0.map { Double($0) } }
            overrides["params.a"] = trialParams.a.map { $0.map { Double($0) } }
            overrides["params.m"] = trialParams.m.map { Double($0) }
            overrides["params.s"] = trialParams.s.map { Double($0) }
            overrides["params.h"] = trialParams.h.map { Double($0) }
            overrides["params.R"] = Double(trialParams.R)
            overrides["params.seed"] = trialSeeds[0]
            overrides["run.steps"] = parsedSearchConfig.steps

            let runtimeConfig = try loadRuntimeConfig(from: baseConfigData, overrides: overrides)
            let engine = SearchEngine(runtimeConfig: runtimeConfig)
            let batchResults = engine.runBatch(
                seeds: trialSeeds,
                initSeedOffset: initSeedOffset,
                searchConfig: simSearchConfig
            )

            var trialResultDatas: [SimulationResultData] = []
            for result in batchResults {
                let resultData = materializeSearchResultData(
                    result,
                    backend: runtimeConfig.backend.rawValue,
                    implementation: implementation,
                    searchConfig: simSearchConfig
                )
                trialResultDatas.append(resultData)
            }
            try appendResearchJSONLines(trialResultDatas, to: resultsHandle, encoder: encoder)

            let representative = trialResultDatas.max(by: { ($0.score ?? 0) < ($1.score ?? 0) }) ?? trialResultDatas[0]
            let embedding = goalVector(from: representative, features: imgepConfig.goal.features)
            let entry = IMGEPHistoryEntry(
                seed: representative.seed,
                params: representative.params,
                metrics: representative.metrics,
                embedding: embedding,
                goal: trialGoal,
                score: representative.score
            )
            history.append(entry)
            try appendResearchJSONLines([entry], to: historyHandle, encoder: encoder)
            mergeTopSimulationResults(
                trialResultDatas,
                into: &topResults,
                limit: parsedSearchConfig.topK,
                headroomMultiplier: 1
            )
        }
        iteration += batchCount
    }

    let elapsed = Date().timeIntervalSince(context.startTime)
    context.logger.info("IMGEP phase '\(phase.name)': \(iterations) iterations, \(topResults.count) top results, \(String(format: "%.1f", elapsed))s")

    try runCampaignCompendiumIndex(outputURL: context.phaseOutputURL)

    return context.result(
        phase: phase,
        type: .imgep,
        creaturesFound: topResults.count
    )
}

private func executeSweepPhase(
    phase: LeniaCampaignPhaseConfig,
    context: CampaignPhaseExecutionContext
) throws -> LeniaCampaignPhaseResult {
    guard let manifestPath = phase.manifest else {
        throw ValidationError("Sweep phase '\(phase.name)' requires manifest.")
    }
    let manifestURL = context.resolve(manifestPath)
    let sweepConfig = try JSONDecoder().decode(DiscoveryCampaignConfig.self, from: Data(contentsOf: manifestURL))

    let maxCycles = phase.target?.maxCycles ?? sweepConfig.maxCycles ?? 1
    let effectiveConfig = DiscoveryCampaignConfig(
        variants: sweepConfig.variants,
        targetCreatures: phase.target?.creatures ?? sweepConfig.targetCreatures,
        maxCycles: maxCycles,
        keepBest: sweepConfig.keepBest,
        rankBy: sweepConfig.rankBy
    )

    let request = context.localRequest(
        phase: phase,
        preset: .discovery,
        configURL: manifestURL,
        exportBest: effectiveConfig.keepBest
    )
    let jobs = try buildDiscoveryCampaignJobs(
        request: request,
        config: effectiveConfig,
        dossierRoot: context.dossierRoot,
        configDirectory: manifestURL.deletingLastPathComponent()
    )
    return try executeLocalPlannedPhase(
        phase: phase,
        type: .sweep,
        context: context,
        request: request,
        jobs: jobs,
        creaturesFound: { execution in
        execution.results.filter(\.filtersPassed).count
    })
}

private func executeInterventionBatteryPhase(
    phase: LeniaCampaignPhaseConfig,
    context: CampaignPhaseExecutionContext
) throws -> LeniaCampaignPhaseResult {
    guard let configPath = phase.config ?? phase.manifest else {
        throw ValidationError("Intervention-battery phase '\(phase.name)' requires config.")
    }
    let configURL = context.resolve(configPath)
    let interventionConfig = try JSONDecoder().decode(InterventionBatteryCampaignConfig.self, from: Data(contentsOf: configURL))

    let request = context.localRequest(
        phase: phase,
        preset: .interventionBattery,
        configURL: configURL,
        seedLibraryURL: context.seedLibraryURL(phase.seedLibrary),
        seedSelection: resolvedPhaseSeedSelection(from: phase)
    )
    let jobs = try buildInterventionBatteryJobs(
        request: request,
        config: interventionConfig,
        dossierRoot: context.dossierRoot,
        configDirectory: configURL.deletingLastPathComponent(),
        logger: context.logger
    )
    let perturbationFamilies = Dictionary(
        uniqueKeysWithValues: interventionConfig.perturbations.map { ($0.id, $0.family) }
    )
    return try executeLocalPlannedPhase(
        phase: phase,
        type: .interventionBattery,
        context: context,
        request: request,
        jobs: jobs,
        metricsTransform: applyBaselineComparisons,
        creaturesFound: { execution in
            execution.metrics.count
        },
        postCompendiumIngest: { execution, compendiumPath in
            _ = try writeInterventionTrialRows(
                metrics: execution.metrics,
                perturbationFamilies: perturbationFamilies,
                compendiumPath: compendiumPath,
                logger: context.logger
            )
        }
    )
}

private func executeEcologyPhase(
    phase: LeniaCampaignPhaseConfig,
    context: CampaignPhaseExecutionContext
) throws -> LeniaCampaignPhaseResult {
    guard let configPath = phase.config ?? phase.configDir else {
        throw ValidationError("Ecology phase '\(phase.name)' requires config or config_dir.")
    }
    let configURL = context.resolve(configPath)
    let ecologyConfig = try JSONDecoder().decode(SeededEcologyCampaignConfig.self, from: Data(contentsOf: configURL))

    let request = context.localRequest(
        phase: phase,
        preset: .seededEcology,
        configURL: configURL,
        seedLibraryURL: context.seedLibraryURL(phase.seedLibrary)
    )
    let jobs = try buildSeededEcologyJobs(
        request: request,
        config: ecologyConfig,
        dossierRoot: context.dossierRoot,
        configDirectory: configURL.deletingLastPathComponent()
    )
    return try executeLocalPlannedPhase(
        phase: phase,
        type: .ecology,
        context: context,
        request: request,
        jobs: jobs,
        creaturesFound: { execution in
        execution.ecologyArtifacts.count
    })
}

private func executeCuriosityPhase(
    phase: LeniaCampaignPhaseConfig,
    context: CampaignPhaseExecutionContext
) throws -> LeniaCampaignPhaseResult {
    guard let configDir = phase.configDir else {
        throw ValidationError("Curiosity phase '\(phase.name)' requires config_dir.")
    }
    let configDirURL = context.resolve(configDir)
    let bundle = try loadAIScientist2025ConfigBundle(configDirectory: configDirURL)
    let runner = AIScientist2025Runner(configs: bundle, logger: context.logger)
    let summary = try runner.run(outputDirectory: context.phaseOutputURL)

    let totalCreatures = summary.experiments.reduce(0) { $0 + $1.records }
    return context.result(
        phase: phase,
        type: .curiosity,
        creaturesFound: totalCreatures
    )
}

private func resolvedPhaseSeedSelection(from phase: LeniaCampaignPhaseConfig) -> ResearchSeedSelection? {
    guard let top = phase.seedTop else {
        return nil
    }
    let rankBy = phase.seedRankBy.flatMap { ResearchSeedRankMetric(rawValue: $0) } ?? .score
    return ResearchSeedSelection(top: top, rankBy: rankBy)
}

private func makeLocalCampaignRequest(
    runID: String,
    preset: LeniaCampaignPreset,
    configURL: URL,
    outputURL: URL,
    backendRequest: String,
    seedLibraryURL: URL? = nil,
    seedQDConfigDirURL: URL? = nil,
    seedSelection: ResearchSeedSelection? = nil,
    exportBest: Int? = nil
) -> CampaignExecutionRequest {
    CampaignExecutionRequest(
        runID: runID,
        preset: preset,
        configURL: configURL,
        outputURL: outputURL,
        seedLibraryURL: seedLibraryURL,
        seedQDConfigDirURL: seedQDConfigDirURL,
        seedSelection: seedSelection,
        backendRequest: backendRequest,
        executionMode: .local,
        distributedControllerHost: nil,
        distributedControllerPort: 7337,
        distributedBindHost: "0.0.0.0",
        distributedBindPort: 0,
        exportBest: exportBest,
        promotion: phasePromotionConfig(outputURL: outputURL)
    )
}
