import ArgumentParser
import Foundation
import LeniaCore
import Logging

private struct FlowMapElitesEliteSummary: Codable {
    let key: String
    let cell: [Int]
    let generation: Int
    let fitness: Float
    let descriptors: [String: Float]
    let candidate: [Float]
}

private struct FlowMapElitesHistoryEntry: Codable {
    let generation: Int
    let evaluations: Int
    let occupiedCells: Int
    let coverage: Float
    let addedOrImproved: Int
    let maxFitness: Float
    let qdScore: Float
    let elapsedSeconds: Double

    enum CodingKeys: String, CodingKey {
        case generation
        case evaluations
        case occupiedCells = "occupied_cells"
        case coverage
        case addedOrImproved = "added_or_improved"
        case maxFitness = "max_fitness"
        case qdScore = "qd_score"
        case elapsedSeconds = "elapsed_seconds"
    }
}

private struct FlowMapElitesRunSummary: Codable {
    let runId: String
    let generations: Int
    let evaluations: Int
    let occupiedCells: Int
    let totalCells: Int
    let coverage: Float
    let qdScore: Float
    let maxFitness: Float
    let descriptors: [FlowMAPElitesDescriptorConfig]

    enum CodingKeys: String, CodingKey {
        case runId = "run_id"
        case generations
        case evaluations
        case occupiedCells = "occupied_cells"
        case totalCells = "total_cells"
        case coverage
        case qdScore = "qd_score"
        case maxFitness = "max_fitness"
        case descriptors
    }
}

private struct FlowMapElitesSeedWarmStart {
    let sourceID: String
    let name: String
    let runID: String?
    let campaignID: String?
    let score: Float?
    let patchValues: [Float]?
    let kernelParams: KernelParams?
}

private struct FlowMapElitesSeedWarmStartRecord: Codable {
    let rank: Int
    let sourceID: String
    let name: String
    let runID: String?
    let campaignID: String?
    let score: Float?
    let patchValueCount: Int
    let hasKernelParams: Bool

    enum CodingKeys: String, CodingKey {
        case rank
        case sourceID = "source_id"
        case name
        case runID = "run_id"
        case campaignID = "campaign_id"
        case score
        case patchValueCount = "patch_value_count"
        case hasKernelParams = "has_kernel_params"
    }
}

struct FlowMapElitesCommand: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "map-elites",
        abstract: "Run Flow Lenia MAP-Elites over parameter and optional init-patch genotypes"
    )

    @Option(name: .long, help: "Path to base config.json")
    var config: String

    @Option(name: .long, help: "Path to Flow MAP-Elites config JSON")
    var mapElites: String

    @Option(name: .long, help: "Requested backend: auto|metal-full|mlx")
    var backend: String = "auto"

    @Option(name: .shortAndLong, help: "Output directory (overrides MAP-Elites config)")
    var output: String?

    @Option(name: .long, help: "Path to library/index.jsonl or exports/index.jsonl used to seed the initial patch")
    var seedLibrary: String?

    @Option(name: .long, help: "Optional qd-2024 config directory when the seed library comes from qd-2024 and pattern assets are missing")
    var seedQDConfigDir: String?

    @Option(name: .long, parsing: .upToNextOption, help: "QD cell ids to use for warm starts when the seed library comes from qd-2024")
    var seedCell: [Int] = []

    @OptionGroup
    var seedSelection: ResearchSeedSelectionOptions

    @Flag(name: .long, help: "Also warm-start kernel parameters from the selected research seed when available")
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
        let resolvedRunId = resolveRunID(prefix: "flow-map-elites", logOptions: logOptions)
        let logging = try bootstrapRunLogging(
            runID: resolvedRunId,
            role: "flow-map-elites",
            loggerLabel: "LeniaSwarm.FlowMapElites",
            logStem: "flow-map-elites",
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

        let baseConfigURL = URL(fileURLWithPath: config)
        let sourceBaseConfigData = try Data(contentsOf: baseConfigURL)
        var mapConfig = try loadFlowMAPElitesConfig(path: mapElites)

        func withOutput(
            _ outputPath: String,
            initialInitPatchValues: [Float]? = mapConfig.initialInitPatchValues,
            initialKernelParams: KernelParams? = mapConfig.initialKernelParams
        ) -> FlowMAPElitesConfig {
            FlowMAPElitesConfig(
                outputDir: outputPath,
                generations: mapConfig.generations,
                population: mapConfig.population,
                sigma: mapConfig.sigma,
                lineSigma: mapConfig.lineSigma,
                seed: mapConfig.seed,
                steps: mapConfig.steps,
                fitness: mapConfig.fitness,
                includeParent: mapConfig.includeParent,
                descriptors: mapConfig.descriptors,
                exportTop: mapConfig.exportTop,
                exportReplayPoolLimit: mapConfig.exportReplayPoolLimit,
                initPatch: mapConfig.initPatch,
                initialInitPatchValues: initialInitPatchValues,
                initialKernelParams: initialKernelParams,
                paramRanges: mapConfig.paramRanges,
                obstacleField: mapConfig.obstacleField
            )
        }

        mapConfig = withOutput(try resolvePath(mapConfig.outputDir, dossier: dossierName))
        if let output {
            mapConfig = withOutput(try resolvePath(output, dossier: dossierName))
        }

        try validateFlowMapElitesConfig(mapConfig)

        let sourceRuntimeConfig = try loadRuntimeConfig(from: sourceBaseConfigData)
        let esCompatibilityConfig = mapConfig.asESConfig()
        let resolvedBackend = try resolveMetalFirstEvolutionBackend(
            requestValue: backend,
            runtimeConfig: sourceRuntimeConfig,
            esConfig: esCompatibilityConfig
        )
        let baseConfigData = try baseConfigDataBySettingBackend(sourceBaseConfigData, backend: resolvedBackend)
        let baseConfig = try JSONDecoder().decode(LeniaBaseConfig.self, from: baseConfigData)
        let runtimeConfig = try loadRuntimeConfig(from: baseConfigData)
        var seedWarmStarts: [FlowMapElitesSeedWarmStart] = []

        if let seedLibrary {
            let canSeedInitPatch = mapConfig.initPatch?.enabled == true
            if !canSeedInitPatch && !seedKernelParams {
                throw ValidationError("--seed-library without --seed-kernel-params requires init_patch.enabled in the MAP-Elites config.")
            }
            let resolvedSeedLibrary = try resolveArtifactPath(seedLibrary, dossier: dossierName)
            let resolvedQDConfigDir = try seedQDConfigDir.map { try resolvePath($0, dossier: dossierName) }
            let selection = try flowMapElitesEffectiveSeedSelection(
                requested: seedSelection.resolvedSelection(),
                hasExplicitSeedCells: !seedCell.isEmpty
            )
            let patches = try loadResearchSeedPatches(
                libraryURL: URL(fileURLWithPath: resolvedSeedLibrary),
                qdConfigDirectoryOverride: resolvedQDConfigDir.map { URL(fileURLWithPath: $0, isDirectory: true) },
                cells: seedCell.isEmpty ? nil : seedCell,
                warmupSteps: seedWarmupSteps,
                selection: selection
            )
            guard !patches.isEmpty else {
                throw ValidationError("No research seeds resolved from \(resolvedSeedLibrary).")
            }
            let creatureChannelCount = evolveCreatureChannelCount(
                channels: runtimeConfig.channels,
                chemotaxis: runtimeConfig.chemotaxis,
                food: runtimeConfig.food,
                obstacleField: mapConfig.obstacleField
            )
            seedWarmStarts = try patches.map { patch in
                let patchValues: [Float]?
                if let initPatch = mapConfig.initPatch, initPatch.enabled {
                    patchValues = try researchSeedCenterCropPatchValues(
                        patch: patch,
                        size: initPatch.size,
                        outputChannels: creatureChannelCount
                    )
                } else {
                    patchValues = nil
                }
                let kernelParams: KernelParams?
                if seedKernelParams {
                    guard let selectedKernelParams = patch.kernelParams else {
                        throw ValidationError("--seed-kernel-params requested, but selected seed '\(patch.name)' has no kernel parameters.")
                    }
                    kernelParams = try seedKernelZeroWeight.map {
                        try replacingNonPositiveKernelWeights(in: selectedKernelParams, with: $0)
                    } ?? selectedKernelParams
                } else {
                    kernelParams = nil
                }
                return FlowMapElitesSeedWarmStart(
                    sourceID: patch.sourceID,
                    name: patch.name,
                    runID: patch.runID,
                    campaignID: patch.campaignID,
                    score: patch.score,
                    patchValues: patchValues,
                    kernelParams: kernelParams
                )
            }
            guard let firstSeed = seedWarmStarts.first else {
                throw ValidationError("No research seeds resolved from \(resolvedSeedLibrary).")
            }
            mapConfig = withOutput(
                mapConfig.outputDir,
                initialInitPatchValues: firstSeed.patchValues ?? mapConfig.initialInitPatchValues,
                initialKernelParams: firstSeed.kernelParams ?? mapConfig.initialKernelParams
            )
            let seedPreview = seedWarmStarts.prefix(4).map(\.name).joined(separator: ", ")
            let suffix = seedWarmStarts.count > 4 ? ", ..." : ""
            logger.info("Using \(seedWarmStarts.count) research seed warm start(s) for Flow MAP-Elites: \(seedPreview)\(suffix)")
        }

        let ranges: [String: (Float, Float)]
        if let mapRanges = mapConfig.paramRanges {
            ranges = try mapRanges.mapValues { values in
                guard values.count == 2 else {
                    throw ValidationError("MAP-Elites param_ranges entries must have exactly two values.")
                }
                return (values[0], values[1])
            }
        } else {
            ranges = try extractRangesFromConfig(baseConfig)
        }

        if validateOnly {
            logger.info("Configs validated successfully (backend=\(resolvedBackend.rawValue))")
            return
        }

        let outputDir = URL(fileURLWithPath: mapConfig.outputDir, isDirectory: true)
        try FileManager.default.createDirectory(at: outputDir, withIntermediateDirectories: true)
        try baseConfigData.write(to: outputDir.appendingPathComponent("config.json"))
        let resolvedMapConfigData = try researchJSONEncoder(prettyPrinted: true).encode(mapConfig)
        try resolvedMapConfigData.write(to: outputDir.appendingPathComponent("map_elites_config.json"))
        if !seedWarmStarts.isEmpty {
            let seedRecords = seedWarmStarts.enumerated().map { pair in
                FlowMapElitesSeedWarmStartRecord(
                    rank: pair.offset,
                    sourceID: pair.element.sourceID,
                    name: pair.element.name,
                    runID: pair.element.runID,
                    campaignID: pair.element.campaignID,
                    score: pair.element.score,
                    patchValueCount: pair.element.patchValues?.count ?? 0,
                    hasKernelParams: pair.element.kernelParams != nil
                )
            }
            try writeResearchJSONLines(seedRecords, to: outputDir.appendingPathComponent("seed_warm_starts.jsonl"))
        }

        logger.info("============================================================")
        logger.info("Flow Lenia MAP-Elites")
        logger.info("============================================================")
        logger.info("Generations: \(mapConfig.generations)")
        logger.info("Population: \(mapConfig.population)")
        logger.info("Sigma: \(mapConfig.sigma)")
        logger.info("Line sigma: \(mapConfig.lineSigma)")
        logger.info("Steps per eval: \(mapConfig.steps)")
        logger.info("Objective: \(mapConfig.fitness.objective)")
        logger.info("Descriptors: \(mapConfig.descriptors.map(\.name).joined(separator: ", "))")
        logger.info("Backend: \(runtimeConfig.backend.rawValue)")
        logger.info("Output: \(mapConfig.outputDir)")
        logger.info("============================================================")

        let engine = EvolutionEngine(
            runtimeConfig: runtimeConfig,
            esConfig: mapConfig.asESConfig(),
            ranges: ranges
        )
        let seedInitialCandidates = try seedWarmStarts.map { seed in
            try engine.mapElitesCandidate(
                kernelParams: seed.kernelParams,
                initPatchValues: seed.patchValues
            )
        }
        let descriptorNames = mapConfig.descriptors.map(\.name)
        let totalCells = mapConfig.descriptors.reduce(1) { $0 * max($1.bins, 1) }
        var archive: [String: FlowMapElitesEliteSummary] = [:]
        var evaluations = 0

        let historyURL = outputDir.appendingPathComponent("history.jsonl")
        FileManager.default.createFile(atPath: historyURL.path, contents: nil)
        let historyHandle = try FileHandle(forWritingTo: historyURL)
        defer { try? historyHandle.close() }

        for generation in 0..<mapConfig.generations {
            let generationStart = Date()
            let candidates: [[Float]]
            if generation == 0 {
                candidates = try engine.sampleMAPElitesInitialCandidates(
                    anchors: seedInitialCandidates,
                    count: mapConfig.population,
                    sigma: mapConfig.sigma,
                    includeParent: mapConfig.includeParent ?? true
                )
            } else {
                candidates = engine.sampleMAPElitesChildren(
                    parents: archive.values.map(\.candidate),
                    count: mapConfig.population,
                    sigma: mapConfig.sigma,
                    lineSigma: mapConfig.lineSigma
                )
            }

            let batch = try engine.evaluateMAPElitesCandidates(
                candidates,
                descriptorNames: descriptorNames
            )
            evaluations += batch.count
            var improved = 0
            for evaluation in batch {
                guard evaluation.fitness.isFinite,
                      let cell = flowMapElitesCell(for: evaluation, descriptors: mapConfig.descriptors) else {
                    continue
                }
                let key = cell.map(String.init).joined(separator: ":")
                if let existing = archive[key], existing.fitness >= evaluation.fitness {
                    continue
                }
                archive[key] = FlowMapElitesEliteSummary(
                    key: key,
                    cell: cell,
                    generation: generation,
                    fitness: evaluation.fitness,
                    descriptors: evaluation.descriptors,
                    candidate: evaluation.candidate
                )
                improved += 1
            }

            let history = FlowMapElitesHistoryEntry(
                generation: generation,
                evaluations: evaluations,
                occupiedCells: archive.count,
                coverage: Float(archive.count) / Float(max(totalCells, 1)),
                addedOrImproved: improved,
                maxFitness: archive.values.map(\.fitness).max() ?? -.infinity,
                qdScore: archive.values.reduce(Float(0)) { $0 + $1.fitness },
                elapsedSeconds: Date().timeIntervalSince(generationStart)
            )
            historyHandle.write(try researchJSONLine(history))
            logger.info("Flow MAP-Elites: gen=\(generation) occupied=\(archive.count) coverage=\(history.coverage) qd=\(history.qdScore) max=\(history.maxFitness) improved=\(improved)")
        }

        let archiveDir = outputDir.appendingPathComponent("archive", isDirectory: true)
        try FileManager.default.createDirectory(at: archiveDir, withIntermediateDirectories: true)
        let occupied = archive.values.sorted { lhs, rhs in
            if lhs.fitness == rhs.fitness {
                return lhs.key < rhs.key
            }
            return lhs.fitness > rhs.fitness
        }
        try writeResearchJSONLines(occupied, to: archiveDir.appendingPathComponent("occupied.jsonl"))
        let summary = FlowMapElitesRunSummary(
            runId: resolvedRunId,
            generations: mapConfig.generations,
            evaluations: evaluations,
            occupiedCells: archive.count,
            totalCells: totalCells,
            coverage: Float(archive.count) / Float(max(totalCells, 1)),
            qdScore: archive.values.reduce(Float(0)) { $0 + $1.fitness },
            maxFitness: archive.values.map(\.fitness).max() ?? -.infinity,
            descriptors: mapConfig.descriptors
        )
        try writeResearchJSON(summary, to: outputDir.appendingPathComponent("summary.json"), prettyPrinted: true)

        let exportTop = max(0, min(mapConfig.exportTop ?? 16, occupied.count))
        let defaultExportPoolLimit = max(exportTop * 4, exportTop)
        let configuredExportPoolLimit = mapConfig.exportReplayPoolLimit
            .map { max(exportTop, $0) } ?? defaultExportPoolLimit
        let exportPoolLimit = min(occupied.count, min(defaultExportPoolLimit, configuredExportPoolLimit))
        let selectedPool = flowMapElitesDiverseSelection(
            occupied,
            limit: exportPoolLimit,
            descriptors: mapConfig.descriptors
        )
        let configHash = try researchConfigHash([
            ("base", researchEncodedJSON(baseConfig)),
            ("map_elites", resolvedMapConfigData),
        ])
        let replayBaseConfig = buildEvolveReplayBaseConfig(
            baseConfig: baseConfig,
            esConfig: mapConfig.asESConfig()
        )
        logger.info("Evaluating \(selectedPool.count) archive elite(s) for replay-verified export selection")
        var evaluatedExportPool: [FlowMapElitesReplayExportCandidate] = []
        evaluatedExportPool.reserveCapacity(selectedPool.count)
        var bestReplayFitness = -Float.infinity
        var bestReplayExportScore = -Float.infinity
        for (offset, elite) in selectedPool.enumerated() {
            let exportCandidate = FlowMapElitesReplayExportCandidate(
                elite: elite,
                evaluation: engine.evaluateCandidateForResearchExport(
                    elite.candidate,
                    evaluationIndex: offset
                )
            )
            evaluatedExportPool.append(exportCandidate)
            bestReplayFitness = max(bestReplayFitness, exportCandidate.evaluation.fitness)
            bestReplayExportScore = max(
                bestReplayExportScore,
                flowMapElitesReplayExportScore(exportCandidate, fitness: mapConfig.fitness)
            )
            let evaluated = offset + 1
            if evaluated == selectedPool.count || evaluated % 32 == 0 {
                logger.info(
                    "Replay export evaluation: evaluated=\(evaluated)/\(selectedPool.count) best_replay_fitness=\(bestReplayFitness) best_replay_export_score=\(bestReplayExportScore)"
                )
            }
        }
        let selected = flowMapElitesReplayVerifiedSelection(
            evaluatedExportPool,
            limit: exportTop,
            descriptors: mapConfig.descriptors,
            fitness: mapConfig.fitness
        )
        let rawReplayPositiveCount = selected.filter { $0.evaluation.fitness > 0 }.count
        let replayGatePassedCount = selected.filter {
            flowMapElitesReplayExportGatePassed($0, fitness: mapConfig.fitness)
        }.count
        logger.info(
            "Replay-verified export selection: selected=\(selected.count) raw_replay_positive=\(rawReplayPositiveCount) replay_gate_passed=\(replayGatePassedCount)"
        )
        let creaturesAndEntries = try selected.enumerated().map { pair in
            let rank = pair.offset
            let exportCandidate = pair.element
            let elite = exportCandidate.elite
            let evaluation = exportCandidate.evaluation
            let creature = flowMapElitesCreature(
                runId: resolvedRunId,
                rank: rank,
                elite: elite,
                configHash: configHash,
                evaluation: evaluation,
                score: elite.fitness
            )
            let entry = try flowMapElitesLibraryEntry(
                runId: resolvedRunId,
                rank: rank,
                elite: elite,
                configHash: configHash,
                evaluation: evaluation,
                creature: creature,
                fitness: mapConfig.fitness
            )
            return (creature, entry)
        }
        _ = try persistResearchArchiveArtifacts(
            runDirectory: outputDir,
            libraryEntries: creaturesAndEntries.map { $0.1 },
            exportRoot: outputDir.appendingPathComponent("exports", isDirectory: true),
            exportItems: creaturesAndEntries.map { $0.0 },
            emptyExportMessage: "Export bundles already exist for Flow MAP-Elites elites."
        ) { creature in
            (
                baseConfig: replayBaseConfig,
                searchConfig: buildStrictReplaySearchConfig(
                    steps: mapConfig.steps,
                    initSeedOffset: creature.initialCondition.seed
                ),
                creature: creature,
                runId: resolvedRunId,
                campaignId: nil,
                score: creature.score,
                filtersPassed: nil,
                reason: "flow-map-elites"
            )
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
            logger.info("Promoted Flow MAP-Elites run into compendium: \(compendiumPath)")
        }
    }
}

private func validateFlowMapElitesConfig(_ config: FlowMAPElitesConfig) throws {
    guard config.generations > 0 else {
        throw ValidationError("MAP-Elites generations must be > 0.")
    }
    guard config.population > 0 else {
        throw ValidationError("MAP-Elites population must be > 0.")
    }
    guard config.population % 2 == 0 else {
        throw ValidationError("MAP-Elites population must be even for the current Flow evaluator.")
    }
    guard config.sigma >= 0 else {
        throw ValidationError("MAP-Elites sigma must be >= 0.")
    }
    guard config.lineSigma >= 0 else {
        throw ValidationError("MAP-Elites line_sigma must be >= 0.")
    }
    guard config.steps > 0 else {
        throw ValidationError("MAP-Elites steps must be > 0.")
    }
    if let exportTop = config.exportTop {
        guard exportTop >= 0 else {
            throw ValidationError("MAP-Elites export_top must be >= 0.")
        }
    }
    if let exportReplayPoolLimit = config.exportReplayPoolLimit {
        guard exportReplayPoolLimit > 0 else {
            throw ValidationError("MAP-Elites export_replay_pool_limit must be > 0 when set.")
        }
        let requestedExportTop = config.exportTop ?? 16
        guard exportReplayPoolLimit >= requestedExportTop else {
            throw ValidationError("MAP-Elites export_replay_pool_limit must be >= export_top.")
        }
    }
    guard !config.descriptors.isEmpty else {
        throw ValidationError("MAP-Elites descriptors must not be empty.")
    }
    for descriptor in config.descriptors {
        guard descriptor.bins > 0 else {
            throw ValidationError("Descriptor \(descriptor.name) bins must be > 0.")
        }
        guard descriptor.max > descriptor.min else {
            throw ValidationError("Descriptor \(descriptor.name) max must be greater than min.")
        }
    }
}

private func flowMapElitesEffectiveSeedSelection(
    requested: ResearchSeedSelection?,
    hasExplicitSeedCells: Bool
) throws -> ResearchSeedSelection? {
    guard let requested else {
        return hasExplicitSeedCells ? nil : ResearchSeedSelection(top: 1, rankBy: .score)
    }
    if requested.sourceIDs.isEmpty, requested.names.isEmpty, requested.top == nil, !hasExplicitSeedCells {
        throw ValidationError("--seed-rank-by and --seed-rank-ascending only order seeds; use --seed-top, --seed-name, or --seed-id to choose a bounded MAP-Elites seed set.")
    }
    return requested
}

private func flowMapElitesDiverseSelection(
    _ elites: [FlowMapElitesEliteSummary],
    limit: Int,
    descriptors: [FlowMAPElitesDescriptorConfig]
) -> [FlowMapElitesEliteSummary] {
    guard limit > 0, !elites.isEmpty else { return [] }
    guard !descriptors.isEmpty else { return Array(elites.prefix(limit)) }

    let poolLimit = min(elites.count, max(limit * 4, limit))
    let pool = Array(elites.prefix(poolLimit))
    var selected = [pool[0]]
    var selectedPoints = [flowMapElitesDescriptorPoint(elites[0], descriptors: descriptors)]
    var remaining = Array(pool.dropFirst())
    let bestFitness = pool.first?.fitness ?? 0
    let fitnessScale = max(abs(bestFitness), 1.0)

    while selected.count < limit, !remaining.isEmpty {
        var bestIndex = 0
        var bestScore = -Float.infinity
        for (index, elite) in remaining.enumerated() {
            let point = flowMapElitesDescriptorPoint(elite, descriptors: descriptors)
            let nearestDistance = selectedPoints
                .map { flowMapElitesSquaredDistance(point, $0) }
                .min() ?? 0
            let fitnessBias = max(-1.0, min(1.0, elite.fitness / fitnessScale)) * 1e-4
            let score = nearestDistance + fitnessBias
            if score > bestScore || (score == bestScore && elite.key < remaining[bestIndex].key) {
                bestScore = score
                bestIndex = index
            }
        }
        let next = remaining.remove(at: bestIndex)
        selected.append(next)
        selectedPoints.append(flowMapElitesDescriptorPoint(next, descriptors: descriptors))
    }

    return selected
}

private struct FlowMapElitesReplayExportCandidate {
    let elite: FlowMapElitesEliteSummary
    let evaluation: ESEvaluatedCreatureExport
}

private func flowMapElitesReplayVerifiedSelection(
    _ candidates: [FlowMapElitesReplayExportCandidate],
    limit: Int,
    descriptors: [FlowMAPElitesDescriptorConfig],
    fitness: FitnessConfig
) -> [FlowMapElitesReplayExportCandidate] {
    guard limit > 0, !candidates.isEmpty else { return [] }
    let finite = candidates.filter { $0.evaluation.fitness.isFinite }
    let finitePool = finite.isEmpty ? candidates : finite
    let replayPassed = finitePool.filter { flowMapElitesReplayExportGatePassed($0, fitness: fitness) }
    var selected = flowMapElitesReplayDiverseSelection(
        replayPassed.isEmpty ? finitePool : replayPassed,
        limit: limit,
        descriptors: descriptors,
        fitness: fitness
    )
    guard selected.count < limit else { return selected }

    let selectedKeys = Set(selected.map(\.elite.key))
    let fallback = finitePool
        .filter { !selectedKeys.contains($0.elite.key) }
        .sorted { flowMapElitesReplayExportIsBetter($0, than: $1, fitness: fitness) }
    selected.append(contentsOf: flowMapElitesReplayDiverseSelection(
        fallback,
        limit: limit - selected.count,
        descriptors: descriptors,
        fitness: fitness
    ))
    return selected
}

private func flowMapElitesReplayDiverseSelection(
    _ candidates: [FlowMapElitesReplayExportCandidate],
    limit: Int,
    descriptors: [FlowMAPElitesDescriptorConfig],
    fitness: FitnessConfig
) -> [FlowMapElitesReplayExportCandidate] {
    guard limit > 0, !candidates.isEmpty else { return [] }
    guard !descriptors.isEmpty else {
        return Array(candidates
            .sorted { flowMapElitesReplayExportIsBetter($0, than: $1, fitness: fitness) }
            .prefix(limit))
    }

    let ranked = candidates.sorted { flowMapElitesReplayExportIsBetter($0, than: $1, fitness: fitness) }
    var selected = [ranked[0]]
    var selectedPoints = [flowMapElitesReplayDescriptorPoint(ranked[0], descriptors: descriptors)]
    var remaining = Array(ranked.dropFirst())
    let bestScore = ranked.first.map { flowMapElitesReplayExportScore($0, fitness: fitness) } ?? 0
    let scoreScale = max(abs(bestScore), 1.0)

    while selected.count < limit, !remaining.isEmpty {
        var bestIndex = 0
        var bestScore = -Float.infinity
        for (index, candidate) in remaining.enumerated() {
            let point = flowMapElitesReplayDescriptorPoint(candidate, descriptors: descriptors)
            let nearestDistance = selectedPoints
                .map { flowMapElitesSquaredDistance(point, $0) }
                .min() ?? 0
            let exportScore = flowMapElitesReplayExportScore(candidate, fitness: fitness)
            let fitnessBias = max(-1.0, min(1.0, exportScore / scoreScale)) * 1e-4
            let score = nearestDistance + fitnessBias
            if score > bestScore || (score == bestScore && candidate.elite.key < remaining[bestIndex].elite.key) {
                bestScore = score
                bestIndex = index
            }
        }
        let next = remaining.remove(at: bestIndex)
        selected.append(next)
        selectedPoints.append(flowMapElitesReplayDescriptorPoint(next, descriptors: descriptors))
    }

    return selected
}

private func flowMapElitesReplayExportIsBetter(
    _ lhs: FlowMapElitesReplayExportCandidate,
    than rhs: FlowMapElitesReplayExportCandidate,
    fitness: FitnessConfig
) -> Bool {
    let lhsScore = flowMapElitesReplayExportScore(lhs, fitness: fitness)
    let rhsScore = flowMapElitesReplayExportScore(rhs, fitness: fitness)
    if lhsScore == rhsScore {
        if lhs.evaluation.fitness == rhs.evaluation.fitness {
            if lhs.elite.fitness == rhs.elite.fitness {
                return lhs.elite.key < rhs.elite.key
            }
            return lhs.elite.fitness > rhs.elite.fitness
        }
        return lhs.evaluation.fitness > rhs.evaluation.fitness
    }
    return lhsScore > rhsScore
}

private func flowMapElitesReplayExportGatePassed(
    _ candidate: FlowMapElitesReplayExportCandidate,
    fitness: FitnessConfig
) -> Bool {
    if fitness.objective == "body_locomotion" {
        let metrics = candidate.evaluation.resultData.metrics
        guard bodyLocomotion(for: metrics) > 0,
              (metrics.transportDisplacement ?? 0) > 1,
              (metrics.translatedShapeOverlap ?? 0) >= (fitness.translatedShapeOverlapMin ?? 0.5) else {
            return false
        }
        return flowMapElitesReplayExportViolation(metrics, fitness: fitness) <= 0.35 &&
            flowMapElitesReplayExportScore(candidate, fitness: fitness) > 0
    }
    if candidate.evaluation.fitness > 0 {
        return true
    }
    let metrics = candidate.evaluation.resultData.metrics
    guard (metrics.coherentTransport ?? 0) > 0 else {
        return false
    }
    return flowMapElitesReplayExportViolation(metrics, fitness: fitness) <= 0.75 &&
        flowMapElitesReplayExportScore(candidate, fitness: fitness) > 0
}

private func flowMapElitesReplayExportScore(
    _ candidate: FlowMapElitesReplayExportCandidate,
    fitness: FitnessConfig
) -> Float {
    let metrics = candidate.evaluation.resultData.metrics
    let bodyScore = bodyLocomotion(for: metrics)
    let bodyScoreUnit = bodyScore / (1 + bodyScore)
    let transport = max(metrics.coherentTransport ?? 0, 0)
    let transportScore = transport / (1 + transport)
    let overlap = flowMapElitesUnitMetric(metrics.translatedShapeOverlap)
    let solidity = flowMapElitesUnitMetric(metrics.largestComponentSolidity)
    let thickness = min(max(metrics.largestComponentMeanThickness ?? 0, 0), 4) / 4
    let largestComponentFraction = flowMapElitesUnitMetric(metrics.largestComponentFraction)
    let filamentarity = flowMapElitesUnitMetric(metrics.largestComponentFilamentarity ?? 1)
    let replayFitness = candidate.evaluation.fitness.isFinite ? candidate.evaluation.fitness : -1
    let violation = flowMapElitesReplayExportViolation(metrics, fitness: fitness)

    return 0.25 * replayFitness +
        0.90 * bodyScoreUnit +
        transportScore +
        0.30 * overlap +
        0.20 * solidity +
        0.10 * thickness +
        0.10 * largestComponentFraction -
        0.20 * filamentarity -
        0.75 * violation
}

private func flowMapElitesReplayExportViolation(
    _ metrics: SimulationMetrics,
    fitness: FitnessConfig
) -> Float {
    var violation: Float = 0
    violation += flowMapElitesMinimumViolation(metrics.translatedShapeOverlap, minimum: fitness.translatedShapeOverlapMin)
    violation += flowMapElitesMaximumViolation(metrics.componentCount, maximum: fitness.componentCountMax)
    violation += flowMapElitesMinimumViolation(metrics.largestComponentFraction, minimum: fitness.largestComponentFractionMin)
    violation += flowMapElitesMinimumViolation(metrics.largestComponentSolidity, minimum: fitness.largestComponentSolidityMin)
    violation += flowMapElitesMinimumViolation(
        metrics.largestComponentMeanThickness,
        minimum: fitness.largestComponentMeanThicknessMin
    )
    violation += flowMapElitesMaximumViolation(
        metrics.largestComponentFilamentarity,
        maximum: fitness.largestComponentFilamentarityMax
    )
    violation += flowMapElitesMinimumViolation(metrics.occupiedFraction, minimum: fitness.occupiedFractionMin)
    violation += flowMapElitesMaximumViolation(metrics.occupiedFraction, maximum: fitness.occupiedFractionMax)
    violation += flowMapElitesMaximumViolation(metrics.occupiedGrowth, maximum: fitness.occupiedGrowthMax)
    return violation
}

private func flowMapElitesMinimumViolation(_ value: Float?, minimum: Float?) -> Float {
    guard let minimum else { return 0 }
    guard let value, value.isFinite else { return 1 }
    guard value < minimum else { return 0 }
    return (minimum - value) / max(abs(minimum), 1)
}

private func flowMapElitesMaximumViolation(_ value: Float?, maximum: Float?) -> Float {
    guard let maximum else { return 0 }
    guard let value, value.isFinite else { return 1 }
    guard value > maximum else { return 0 }
    return (value - maximum) / max(abs(maximum), 1)
}

private func flowMapElitesUnitMetric(_ value: Float?) -> Float {
    guard let value, value.isFinite else { return 0 }
    return max(0, min(1, value))
}

private func flowMapElitesReplayDescriptorPoint(
    _ candidate: FlowMapElitesReplayExportCandidate,
    descriptors: [FlowMAPElitesDescriptorConfig]
) -> [Float] {
    let archivePoint = flowMapElitesDescriptorPoint(candidate.elite, descriptors: descriptors)
    return descriptors.enumerated().map { index, descriptor in
        if let value = flowMapElitesMetricValue(
            name: descriptor.name,
            metrics: candidate.evaluation.resultData.metrics,
            fitness: candidate.evaluation.fitness
        ), value.isFinite {
            let normalized = (value - descriptor.min) / (descriptor.max - descriptor.min)
            return max(0.0, min(1.0, normalized))
        }
        return index < archivePoint.count ? archivePoint[index] : 0
    }
}

private func flowMapElitesMetricValue(
    name: String,
    metrics: SimulationMetrics,
    fitness: Float
) -> Float? {
    switch name {
    case "fitness":
        return fitness
    case "coherent_transport":
        return metrics.coherentTransport
    case "body_locomotion":
        return bodyLocomotion(for: metrics)
    case "transport_displacement":
        return metrics.transportDisplacement
    case "translated_shape_overlap":
        return metrics.translatedShapeOverlap
    case "gyration":
        return metrics.gyration
    case "component_count":
        return metrics.componentCount
    case "largest_component_fraction":
        return metrics.largestComponentFraction
    case "largest_component_anisotropy":
        return metrics.largestComponentAnisotropy
    case "largest_component_solidity", "solidity":
        return metrics.largestComponentSolidity
    case "largest_component_mean_thickness", "thickness":
        return metrics.largestComponentMeanThickness
    case "largest_component_max_thickness":
        return metrics.largestComponentMaxThickness
    case "largest_component_filamentarity", "filamentarity":
        return metrics.largestComponentFilamentarity
    case "moment_density":
        return metrics.momentDensity
    case "occupied_fraction":
        return metrics.occupiedFraction
    case "mid_occupied_fraction":
        return metrics.midOccupiedFraction
    case "target_occupied_fraction":
        return metrics.targetOccupiedFraction
    case "occupied_growth":
        return metrics.occupiedGrowth
    case "moment_anisotropy":
        return metrics.momentAnisotropy
    default:
        return nil
    }
}

private func flowMapElitesDescriptorPoint(
    _ elite: FlowMapElitesEliteSummary,
    descriptors: [FlowMAPElitesDescriptorConfig]
) -> [Float] {
    descriptors.map { descriptor in
        if let value = elite.descriptors[descriptor.name], value.isFinite {
            let normalized = (value - descriptor.min) / (descriptor.max - descriptor.min)
            return max(0.0, min(1.0, normalized))
        }
        guard let index = descriptors.firstIndex(where: { $0.name == descriptor.name }),
              index < elite.cell.count,
              descriptor.bins > 1 else {
            return 0
        }
        return Float(elite.cell[index]) / Float(descriptor.bins - 1)
    }
}

private func flowMapElitesSquaredDistance(_ lhs: [Float], _ rhs: [Float]) -> Float {
    zip(lhs, rhs).reduce(Float(0)) { partial, pair in
        let delta = pair.0 - pair.1
        return partial + delta * delta
    }
}

private func flowMapElitesCell(
    for evaluation: FlowMAPElitesCandidateEvaluation,
    descriptors: [FlowMAPElitesDescriptorConfig]
) -> [Int]? {
    var cell: [Int] = []
    cell.reserveCapacity(descriptors.count)
    for descriptor in descriptors {
        guard let value = evaluation.descriptors[descriptor.name], value.isFinite else {
            return nil
        }
        let normalized = (value - descriptor.min) / (descriptor.max - descriptor.min)
        let clamped = max(0.0, min(0.999_999, normalized))
        cell.append(Int(floor(clamped * Float(descriptor.bins))))
    }
    return cell
}

private func flowMapElitesCreature(
    runId: String,
    rank: Int,
    elite: FlowMapElitesEliteSummary,
    configHash: String,
    evaluation: ESEvaluatedCreatureExport,
    score: Float
) -> SavedCreature {
    archivedCreatureFromResult(
        stableKey: "\(runId)|flow-map-elites|\(elite.key)|\(rank)",
        name: "flow-map-elite-\(rank)",
        ownerId: "flow-map-elites",
        result: evaluation.resultData,
        initialCondition: evaluation.initConfig,
        configHash: configHash,
        score: score,
        scoreWeights: ["fitness": 1.0]
    )
}

private func flowMapElitesLibraryEntry(
    runId: String,
    rank: Int,
    elite: FlowMapElitesEliteSummary,
    configHash: String,
    evaluation: ESEvaluatedCreatureExport,
    creature: SavedCreature,
    fitness: FitnessConfig
) throws -> ResearchLibraryEntry {
    let exportCandidate = FlowMapElitesReplayExportCandidate(elite: elite, evaluation: evaluation)
    let metadata: [String: AnyCodable] = try [
        "version": researchMetadataValue(1),
        "mode": researchMetadataValue("flow-map-elites"),
        "morphospace_payload": researchMetadataValue("summary_only_metrics_v1"),
        "morphospace_ready": researchMetadataValue(false),
        "canonical_export_available": researchMetadataValue(true),
        "canonical_export_kind": researchMetadataValue("strict_replay_bundle_v1"),
        "rank": researchMetadataValue(rank),
        "cell": researchMetadataValue(elite.cell),
        "cell_key": researchMetadataValue(elite.key),
        "generation": researchMetadataValue(elite.generation),
        "fitness": researchMetadataValue(elite.fitness),
        "archive_fitness": researchMetadataValue(elite.fitness),
        "replay_fitness": researchMetadataValue(evaluation.fitness),
        "replay_export_score": researchMetadataValue(
            flowMapElitesReplayExportScore(exportCandidate, fitness: fitness)
        ),
        "replay_export_violation": researchMetadataValue(
            flowMapElitesReplayExportViolation(evaluation.resultData.metrics, fitness: fitness)
        ),
        "replay_export_gate_passed": researchMetadataValue(
            flowMapElitesReplayExportGatePassed(exportCandidate, fitness: fitness)
        ),
        "descriptors": researchMetadataValue(elite.descriptors),
        "init_patch_values": researchMetadataValue(evaluation.initPatchValues ?? NSNull()),
        "candidate_vector": researchMetadataValue(elite.candidate),
    ]
    return archiveResearchLibraryEntry(
        creature: creature,
        runId: runId,
        configHash: configHash,
        sourceMode: "flow-map-elites",
        sourceAlgorithm: "map-elites",
        researchMetadata: metadata
    )
}
