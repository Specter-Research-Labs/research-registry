import ArgumentParser
import Foundation
import LeniaCore
import Logging

struct DiscoveryCampaignVariant: Codable {
    let id: String
    let config: String
    let search: String
    let count: Int
}

struct DiscoveryCampaignConfig: Codable {
    let variants: [DiscoveryCampaignVariant]
    let targetCreatures: Int?
    let maxCycles: Int?
    let keepBest: Int?
    let rankBy: ResearchSeedRankMetric?

    enum CodingKeys: String, CodingKey {
        case variants
        case targetCreatures = "target_creatures"
        case maxCycles = "max_cycles"
        case keepBest = "keep_best"
        case rankBy = "rank_by"
    }
}

struct SeededEcologyCampaignConfig: Codable {
    let configDir: String
    let variantNames: [String]?
    let mutationProbabilities: [Float]?
    let repeats: Int?
    let cohortMode: String?
    let maxSeedsPerRun: Int?

    enum CodingKeys: String, CodingKey {
        case configDir = "config_dir"
        case variantNames = "variant_names"
        case mutationProbabilities = "mutation_probabilities"
        case repeats
        case cohortMode = "cohort_mode"
        case maxSeedsPerRun = "max_seeds_per_run"
    }
}

struct CampaignOverrideSpec: Codable {
    let id: String
    let overrides: [String: AnyCodable]?
    let variantOverrides: [String: AnyCodable]?

    enum CodingKeys: String, CodingKey {
        case id
        case overrides
        case variantOverrides = "variant_overrides"
    }
}

struct CampaignPerturbationSpec: Codable {
    let id: String
    let family: String
    let overrides: [String: AnyCodable]?
    let variantOverrides: [String: AnyCodable]?
    let payload: [String: AnyCodable]?

    enum CodingKeys: String, CodingKey {
        case id
        case family
        case overrides
        case variantOverrides = "variant_overrides"
        case payload
    }
}

struct InterventionBatteryCampaignConfig: Codable {
    let mode: String
    let baseConfig: String?
    let searchConfig: String?
    let ecologyConfigDir: String?
    let variantName: String?
    let warmupSteps: Int
    let observationSteps: Int
    let recordEverySteps: Int
    let repeats: Int
    let environments: [CampaignOverrideSpec]
    let perturbations: [CampaignPerturbationSpec]

    enum CodingKeys: String, CodingKey {
        case mode
        case baseConfig = "base_config"
        case searchConfig = "search_config"
        case ecologyConfigDir = "ecology_config_dir"
        case variantName = "variant_name"
        case warmupSteps = "warmup_steps"
        case observationSteps = "observation_steps"
        case recordEverySteps = "record_every_steps"
        case repeats
        case environments
        case perturbations
    }
}

private struct CampaignPlanningContext {
    let request: CampaignExecutionRequest
    let dossierRoot: URL
    let configDirectory: URL

    func resolve(_ rawPath: String) -> URL {
        resolveCampaignRelativePath(
            rawPath,
            configDirectory: configDirectory,
            dossierRoot: dossierRoot
        )
    }

    func plannedSearchJob(
        components: [String],
        repeatIndex: Int,
        environmentLabel: String? = nil,
        perturbationLabel: String? = nil,
        comparisonGroup: String? = nil,
        seedReference: LeniaCampaignSeedReference? = nil,
        id: String,
        seedStart: Int,
        count: Int,
        baseConfig: LeniaBaseConfig,
        searchConfig: ParsedSearchConfig,
        configHash: String,
        exportEligible: Bool,
        sweepOverrides: [String: Double] = [:],
        perturbation: CampaignPerturbationSpec? = nil
    ) -> LeniaCampaignJob {
        LeniaCampaignJob(
            campaignID: request.runID,
            runID: campaignRunID(request.runID, components: components),
            preset: request.preset,
            executor: .search,
            backendRequest: request.backendRequest,
            executionMode: request.executionMode,
            repeatIndex: repeatIndex,
            environmentLabel: environmentLabel,
            perturbationLabel: perturbationLabel,
            comparisonGroup: comparisonGroup,
            seedReference: seedReference,
            search: LeniaCampaignSearchJobPayload(
                simulationJob: SimulationJob(
                    id: id,
                    seedStart: seedStart,
                    count: count,
                    baseConfig: baseConfig,
                    requestedBackend: request.backendRequest,
                    searchConfig: searchConfig,
                    sweepOverrides: sweepOverrides
                ),
                configHash: configHash,
                exportEligible: exportEligible,
                eventSpecs: campaignEventSpecs(for: perturbation)
            )
        )
    }

    func plannedEcologyJob(
        components: [String],
        repeatIndex: Int,
        environmentLabel: String? = nil,
        perturbationLabel: String? = nil,
        comparisonGroup: String? = nil,
        seedReference: LeniaCampaignSeedReference? = nil,
        simulation: FlowLeniaEcology2025SimulationConfig,
        variant: FlowLeniaEcology2025VariantConfig,
        baseConfig: LeniaBaseConfig,
        mutationProbability: Float,
        curatedSeeds: [ResearchSeedPatch],
        configHash: String,
        perturbation: CampaignPerturbationSpec? = nil
    ) -> LeniaCampaignJob {
        LeniaCampaignJob(
            campaignID: request.runID,
            runID: campaignRunID(request.runID, components: components),
            preset: request.preset,
            executor: .ecology2025,
            backendRequest: request.backendRequest,
            executionMode: request.executionMode,
            repeatIndex: repeatIndex,
            environmentLabel: environmentLabel,
            perturbationLabel: perturbationLabel,
            comparisonGroup: comparisonGroup,
            seedReference: seedReference,
            ecology: LeniaCampaignEcologyJobPayload(
                simulation: simulation,
                variant: variant,
                baseConfig: baseConfig,
                mutationProbability: mutationProbability,
                curatedSeeds: curatedSeeds,
                configHash: configHash,
                eventSpecs: campaignEventSpecs(for: perturbation)
            )
        )
    }
}

private func interventionComponents(
    environmentID: String,
    perturbation: CampaignPerturbationSpec?,
    repeatIndex: Int,
    cohortLabel: String = ""
) -> [String] {
    let perturbationLabel = perturbation?.id ?? "baseline"
    var parts = [perturbation == nil ? "baseline" : "intervention", environmentID]
    if perturbation != nil {
        parts.append(perturbationLabel)
    }
    parts.append(String(repeatIndex))
    if !cohortLabel.isEmpty {
        parts.append(cohortLabel)
    }
    return parts
}

private func forEachInterventionScenario(
    repeats: Int,
    environments: [CampaignOverrideSpec],
    perturbations: [CampaignPerturbationSpec],
    cohorts: [ResolvedEcologyCohort] = [ResolvedEcologyCohort(label: "", patches: [], seedReference: nil)],
    comparisonGroup: (Int, CampaignOverrideSpec, ResolvedEcologyCohort) -> String,
    _ body: (Int, CampaignOverrideSpec, CampaignPerturbationSpec?, ResolvedEcologyCohort, String) throws -> Void
) rethrows {
    let perturbationScenarios: [CampaignPerturbationSpec?] = [nil] + perturbations.map(Optional.some)
    for repeatIndex in 0..<repeats {
        for cohort in cohorts {
            for environment in environments {
                let group = comparisonGroup(repeatIndex, environment, cohort)
                for perturbation in perturbationScenarios {
                    try body(repeatIndex, environment, perturbation, cohort, group)
                }
            }
        }
    }
}

func buildCampaignJobs(
    request: CampaignExecutionRequest,
    dossierRoot: URL,
    configDirectory: URL,
    logger: Logger
) throws -> [LeniaCampaignJob] {
    switch request.preset {
    case .discovery, .foodDiscovery:
        let config = try JSONDecoder().decode(DiscoveryCampaignConfig.self, from: Data(contentsOf: request.configURL))
        return try buildDiscoveryCampaignJobs(
            request: request,
            config: config,
            dossierRoot: dossierRoot,
            configDirectory: configDirectory
        )
    case .seededEcology:
        let config = try JSONDecoder().decode(SeededEcologyCampaignConfig.self, from: Data(contentsOf: request.configURL))
        return try buildSeededEcologyJobs(
            request: request,
            config: config,
            dossierRoot: dossierRoot,
            configDirectory: configDirectory
        )
    case .interventionBattery:
        let config = try JSONDecoder().decode(InterventionBatteryCampaignConfig.self, from: Data(contentsOf: request.configURL))
        return try buildInterventionBatteryJobs(
            request: request,
            config: config,
            dossierRoot: dossierRoot,
            configDirectory: configDirectory,
            logger: logger
        )
    }
}

func buildDiscoveryCampaignJobs(
    request: CampaignExecutionRequest,
    config: DiscoveryCampaignConfig,
    dossierRoot: URL,
    configDirectory: URL
) throws -> [LeniaCampaignJob] {
    let planning = CampaignPlanningContext(
        request: request,
        dossierRoot: dossierRoot,
        configDirectory: configDirectory
    )
    let maxCycles = max(1, config.maxCycles ?? 1)
    return try config.variants.enumerated().flatMap { variantIndex, variant in
        try (0..<maxCycles).map { cycleIndex in
            let baseConfigURL = planning.resolve(variant.config)
            let searchConfigURL = planning.resolve(variant.search)
            let baseConfig = try JSONDecoder().decode(LeniaBaseConfig.self, from: Data(contentsOf: baseConfigURL))
            let searchConfig = try JSONDecoder().decode(ParsedSearchConfig.self, from: Data(contentsOf: searchConfigURL))
            let configuredSearch = copySearchConfig(
                searchConfig,
                count: variant.count,
                topK: max(searchConfig.topK, config.keepBest ?? searchConfig.topK)
            )
            let configHash = try researchConfigHash([
                ("base", Data(contentsOf: baseConfigURL)),
                ("search", Data(contentsOf: searchConfigURL)),
            ])
            return planning.plannedSearchJob(
                components: [request.preset.rawValue, variant.id, String(cycleIndex)],
                repeatIndex: cycleIndex,
                environmentLabel: variant.id,
                id: "campaign-\(variant.id)-\(cycleIndex)",
                seedStart: configuredSearch.seedStart + cycleIndex * variant.count * configuredSearch.seedStride,
                count: configuredSearch.count,
                baseConfig: baseConfig,
                searchConfig: configuredSearch,
                configHash: configHash,
                exportEligible: true,
                sweepOverrides: ["campaign_cycle": Double(cycleIndex), "variant_index": Double(variantIndex)]
            )
        }
    }
}

func buildSeededEcologyJobs(
    request: CampaignExecutionRequest,
    config: SeededEcologyCampaignConfig,
    dossierRoot: URL,
    configDirectory: URL
) throws -> [LeniaCampaignJob] {
    let planning = CampaignPlanningContext(
        request: request,
        dossierRoot: dossierRoot,
        configDirectory: configDirectory
    )
    let ecologyConfigURL = planning.resolve(config.configDir)
    let bundle = try loadFlowLeniaEcology2025ConfigBundle(
        configDirectory: ecologyConfigURL,
        strictPaperInvariants: false
    )
    let variants: [FlowLeniaEcology2025VariantConfig]
    if let requestedNames = config.variantNames {
        let availableNames = Set(bundle.variants.map(\.name))
        let missingNames = requestedNames.filter { !availableNames.contains($0) }
        guard missingNames.isEmpty else {
            throw ValidationError(
                "Unknown seeded-ecology variant_names: \(missingNames.joined(separator: ", ")). " +
                "Available variants: \(availableNames.sorted().joined(separator: ", "))."
            )
        }
        variants = bundle.variants.filter { requestedNames.contains($0.name) }
    } else {
        variants = bundle.variants
    }
    let mutationProbabilities = config.mutationProbabilities ?? bundle.simulation.mutationProbabilities
    let repeats = config.repeats ?? bundle.simulation.repeats
    let cohorts = try resolveEcologyCohorts(
        request: request,
        maxSeedsPerRun: config.maxSeedsPerRun,
        mode: config.cohortMode ?? "mixed"
    )

    var jobs: [LeniaCampaignJob] = []
    for variant in variants {
        let baseConfigURL = ecologyConfigURL.appendingPathComponent(variant.baseConfig)
        let baseConfigData = try Data(contentsOf: baseConfigURL)
        let baseConfig = try JSONDecoder().decode(LeniaBaseConfig.self, from: baseConfigData)
        let configHash = researchConfigHash([
            ("simulation", try JSONEncoder().encode(bundle.simulation)),
            ("variant", try JSONEncoder().encode(variant)),
            ("base", baseConfigData),
        ])
        for mutationProbability in mutationProbabilities {
            for repeatIndex in 0..<repeats {
                for cohort in cohorts {
                    jobs.append(planning.plannedEcologyJob(
                        components: [
                            request.preset.rawValue,
                            variant.name,
                            "pmut-\(paperFloatLabel(mutationProbability))",
                            "repeat-\(repeatIndex)",
                            cohort.label,
                        ],
                        repeatIndex: repeatIndex,
                        environmentLabel: variant.name,
                        seedReference: cohort.seedReference,
                        simulation: bundle.simulation,
                        variant: variant,
                        baseConfig: baseConfig,
                        mutationProbability: mutationProbability,
                        curatedSeeds: cohort.patches,
                        configHash: configHash
                    ))
                }
            }
        }
    }
    return jobs
}

func buildInterventionBatteryJobs(
    request: CampaignExecutionRequest,
    config: InterventionBatteryCampaignConfig,
    dossierRoot: URL,
    configDirectory: URL,
    logger: Logger
) throws -> [LeniaCampaignJob] {
    switch config.mode {
    case "search":
        return try buildSearchInterventionJobs(
            request: request,
            config: config,
            dossierRoot: dossierRoot,
            configDirectory: configDirectory
        )
    case "seeded-ecology":
        return try buildEcologyInterventionJobs(
            request: request,
            config: config,
            dossierRoot: dossierRoot,
            configDirectory: configDirectory,
            logger: logger
        )
    default:
        throw ValidationError("Unsupported intervention-battery mode '\(config.mode)'. Expected search or seeded-ecology.")
    }
}

private func buildSearchInterventionJobs(
    request: CampaignExecutionRequest,
    config: InterventionBatteryCampaignConfig,
    dossierRoot: URL,
    configDirectory: URL
) throws -> [LeniaCampaignJob] {
    if request.seedLibraryURL != nil || request.seedSelection != nil {
        throw ValidationError(
            "intervention-battery search mode does not consume seed_library or seed selectors; use the direct battery config without seeded inputs, or switch to seeded-ecology mode."
        )
    }
    let planning = CampaignPlanningContext(
        request: request,
        dossierRoot: dossierRoot,
        configDirectory: configDirectory
    )
    guard let baseConfigPath = config.baseConfig, let searchConfigPath = config.searchConfig else {
        throw ValidationError("intervention-battery search mode requires base_config and search_config.")
    }
    let baseConfigURL = planning.resolve(baseConfigPath)
    let searchConfigURL = planning.resolve(searchConfigPath)
    let baseConfigData = try Data(contentsOf: baseConfigURL)
    let baseConfig = try JSONDecoder().decode(LeniaBaseConfig.self, from: baseConfigData)
    let searchConfig = try JSONDecoder().decode(ParsedSearchConfig.self, from: Data(contentsOf: searchConfigURL))
    let runSteps = config.warmupSteps + config.observationSteps
    let baseSearchConfig = copySearchConfig(
        searchConfig,
        count: 1,
        steps: runSteps,
        recordInterval: config.recordEverySteps,
        warmupSteps: config.warmupSteps,
        topK: 1,
        batchSize: 1
    )
    let baseHash = researchConfigHash([
        ("base", baseConfigData),
        ("search", try JSONEncoder().encode(baseSearchConfig)),
    ])

    var jobs: [LeniaCampaignJob] = []
    let seedStride = max(1, baseSearchConfig.seedStride)
    forEachInterventionScenario(
        repeats: config.repeats,
        environments: config.environments,
        perturbations: config.perturbations,
        comparisonGroup: { repeatIndex, environment, _ in
            let seedStart = baseSearchConfig.seedStart + repeatIndex * seedStride
            return "\(environment.id)-\(repeatIndex)-\(seedStart)"
        }
    ) { repeatIndex, environment, perturbation, _, comparisonGroup in
        let seedStart = baseSearchConfig.seedStart + repeatIndex * seedStride
        let environmentOverrides = environment.overrides ?? [:]
        let mergedOverrides = perturbation.map {
            mergeAnyCodable(environmentOverrides, $0.overrides ?? [:])
        } ?? environmentOverrides
        let searchJobConfig = copySearchConfig(
            baseSearchConfig,
            seedStart: seedStart,
            overrides: mergedOverrides
        )
        let perturbationLabel = perturbation?.id ?? "baseline"
        jobs.append(planning.plannedSearchJob(
            components: interventionComponents(
                environmentID: environment.id,
                perturbation: perturbation,
                repeatIndex: repeatIndex
            ),
            repeatIndex: repeatIndex,
            environmentLabel: environment.id,
            perturbationLabel: perturbationLabel,
            comparisonGroup: comparisonGroup,
            id: perturbation == nil
                ? "baseline-\(environment.id)-\(repeatIndex)"
                : "intervention-\(environment.id)-\(perturbationLabel)-\(repeatIndex)",
            seedStart: seedStart,
            count: 1,
            baseConfig: baseConfig,
            searchConfig: searchJobConfig,
            configHash: baseHash,
            exportEligible: false,
            sweepOverrides: ["repeat_index": Double(repeatIndex)],
            perturbation: perturbation
        ))
    }
    return jobs
}

private func buildEcologyInterventionJobs(
    request: CampaignExecutionRequest,
    config: InterventionBatteryCampaignConfig,
    dossierRoot: URL,
    configDirectory: URL,
    logger: Logger
) throws -> [LeniaCampaignJob] {
    let planning = CampaignPlanningContext(
        request: request,
        dossierRoot: dossierRoot,
        configDirectory: configDirectory
    )
    guard let ecologyConfigDir = config.ecologyConfigDir else {
        throw ValidationError("intervention-battery seeded-ecology mode requires ecology_config_dir.")
    }
    let ecologyConfigURL = planning.resolve(ecologyConfigDir)
    let bundle = try loadFlowLeniaEcology2025ConfigBundle(
        configDirectory: ecologyConfigURL,
        strictPaperInvariants: false
    )
    guard let baseVariant = bundle.variants.first(where: { $0.name == (config.variantName ?? bundle.variants.first?.name) }) else {
        throw ValidationError("Could not resolve the requested ecology variant.")
    }
    let baseConfigURL = ecologyConfigURL.appendingPathComponent(baseVariant.baseConfig)
    let baseConfigData = try Data(contentsOf: baseConfigURL)
    let baseConfig = try JSONDecoder().decode(LeniaBaseConfig.self, from: baseConfigData)
    let cohorts = try resolveEcologyCohorts(request: request, maxSeedsPerRun: 1, mode: "mixed")
    let mutationProbability = bundle.simulation.mutationProbabilities.first ?? 0.0
    let baseHash = researchConfigHash([
        ("simulation", try JSONEncoder().encode(bundle.simulation)),
        ("variant", try JSONEncoder().encode(baseVariant)),
        ("base", baseConfigData),
    ])

    var jobs: [LeniaCampaignJob] = []
    try forEachInterventionScenario(
        repeats: config.repeats,
        environments: config.environments,
        perturbations: config.perturbations,
        cohorts: cohorts,
        comparisonGroup: { repeatIndex, environment, cohort in
            "\(environment.id)-\(repeatIndex)-\(cohort.label)"
        }
    ) { repeatIndex, environment, perturbation, cohort, comparisonGroup in
        let baselineVariant = try applyJSONOverrides(
            baseVariant,
            overrides: environment.variantOverrides ?? [:],
            context: "Ecology variant"
        )
        let baselineBaseConfig = try applyJSONOverrides(
            baseConfig,
            overrides: environment.overrides ?? [:],
            context: "Base config"
        )
        let perturbedVariant = try applyJSONOverrides(
            baselineVariant,
            overrides: perturbation?.variantOverrides ?? [:],
            context: "Ecology variant"
        )
        let perturbedBaseConfig = try applyJSONOverrides(
            baselineBaseConfig,
            overrides: perturbation?.overrides ?? [:],
            context: "Base config"
        )
        let perturbationLabel = perturbation?.id ?? "baseline"
        jobs.append(planning.plannedEcologyJob(
            components: interventionComponents(
                environmentID: environment.id,
                perturbation: perturbation,
                repeatIndex: repeatIndex,
                cohortLabel: cohort.label
            ),
            repeatIndex: repeatIndex,
            environmentLabel: environment.id,
            perturbationLabel: perturbationLabel,
            comparisonGroup: comparisonGroup,
            seedReference: cohort.seedReference,
            simulation: bundle.simulation,
            variant: perturbedVariant,
            baseConfig: perturbedBaseConfig,
            mutationProbability: mutationProbability,
            curatedSeeds: cohort.patches,
            configHash: baseHash,
            perturbation: perturbation
        ))
    }
    logger.debug("Built \(jobs.count) ecology intervention jobs")
    return jobs
}

private struct ResolvedEcologyCohort {
    let label: String
    let patches: [ResearchSeedPatch]
    let seedReference: LeniaCampaignSeedReference?
}

private func resolveEcologyCohorts(
    request: CampaignExecutionRequest,
    maxSeedsPerRun: Int?,
    mode: String
) throws -> [ResolvedEcologyCohort] {
    guard let libraryURL = request.seedLibraryURL else {
        return [ResolvedEcologyCohort(label: "unseeded", patches: [], seedReference: nil)]
    }
    let patches = try loadResearchSeedPatches(
        libraryURL: libraryURL,
        qdConfigDirectoryOverride: request.seedQDConfigDirURL,
        selection: request.seedSelection
    )
    guard !patches.isEmpty else {
        throw ValidationError("No research seeds resolved from \(libraryURL.path).")
    }
    switch mode {
    case "single-seed":
        let limit = max(1, maxSeedsPerRun ?? patches.count)
        return patches.prefix(limit).map { patch in
            ResolvedEcologyCohort(
                label: sanitizeCampaignComponent("\(patch.name)-\(patch.sourceID)"),
                patches: [patch],
                seedReference: LeniaCampaignSeedReference(patch: patch)
            )
        }
    case "mixed":
        let limited = maxSeedsPerRun.map { Array(patches.prefix($0)) } ?? patches
        return [
            ResolvedEcologyCohort(
                label: "mixed-\(limited.count)",
                patches: limited,
                seedReference: limited.count == 1 ? LeniaCampaignSeedReference(patch: limited[0]) : nil
            )
        ]
    default:
        throw ValidationError("Unsupported seeded-ecology cohort_mode '\(mode)'. Expected mixed or single-seed.")
    }
}

func applyBaselineComparisons(to metrics: inout [LeniaCampaignMetricRecord]) {
    let baselines = Dictionary(
        uniqueKeysWithValues: metrics.compactMap { metric -> (String, LeniaCampaignMetricRecord)? in
            guard metric.perturbationLabel == "baseline",
                  let comparisonGroup = metric.comparisonGroup else {
                return nil
            }
            return (comparisonGroup, metric)
        }
    )

    for index in metrics.indices {
        guard metrics[index].perturbationLabel != "baseline",
              let comparisonGroup = metrics[index].comparisonGroup,
              let baseline = baselines[comparisonGroup] else {
            continue
        }
        metrics[index].massRetentionRatio = campaignRatio(metrics[index].finalMass, baseline.finalMass)
        metrics[index].displacementRatio = campaignRatio(metrics[index].displacement, baseline.displacement)
        metrics[index].occupancyDelta = campaignDelta(metrics[index].occupancyMean, baseline.occupancyMean)
        metrics[index].varianceDelta = campaignDelta(metrics[index].varianceMean, baseline.varianceMean)
        if let survival = metrics[index].survivalSteps, let baselineSurvival = baseline.survivalSteps {
            metrics[index].recoveryLagSteps = max(0, baselineSurvival - survival)
        }
        metrics[index].postPerturbationDivergence = campaignDivergence(metric: metrics[index], baseline: baseline)
        if let divergence = metrics[index].postPerturbationDivergence {
            metrics[index].returnToBaselineScore = max(0, 1 - divergence)
            metrics[index].redirectedBehaviorScore = max(0, divergence)
        }
        if let label = metrics[index].perturbationLabel,
           label.contains("chem") || label.contains("food") {
            metrics[index].pursuitScore = campaignRatio(metrics[index].speedMean, baseline.speedMean)
        }
    }
}

private func campaignRatio(_ numerator: Float?, _ denominator: Float?) -> Float? {
    guard let numerator, let denominator, denominator != 0 else { return nil }
    return numerator / denominator
}

private func campaignDelta(_ lhs: Float?, _ rhs: Float?) -> Float? {
    guard let lhs, let rhs else { return nil }
    return lhs - rhs
}

private func campaignDivergence(metric: LeniaCampaignMetricRecord, baseline: LeniaCampaignMetricRecord) -> Float? {
    var deltas: [Float] = []
    if let delta = campaignDelta(metric.finalMass, baseline.finalMass) { deltas.append(abs(delta)) }
    if let delta = campaignDelta(metric.displacement, baseline.displacement) { deltas.append(abs(delta)) }
    if let delta = campaignDelta(metric.occupancyMean, baseline.occupancyMean) { deltas.append(abs(delta)) }
    if let delta = campaignDelta(metric.varianceMean, baseline.varianceMean) { deltas.append(abs(delta)) }
    guard !deltas.isEmpty else { return nil }
    return deltas.reduce(0, +) / Float(deltas.count)
}

private func campaignEventSpecs(for perturbation: CampaignPerturbationSpec?) -> [LeniaCampaignEventSpec] {
    guard let perturbation else {
        return []
    }
    return [
        LeniaCampaignEventSpec(
            label: perturbation.id,
            family: perturbation.family,
            payload: perturbation.payload ?? perturbation.overrides ?? [:]
        )
    ]
}

private func campaignRunID(_ root: String, components: [String]) -> String {
    ([root] + components.map(sanitizeCampaignComponent)).joined(separator: "--")
}

private func paperFloatLabel(_ value: Float) -> String {
    let formatted = String(format: "%.3f", value)
    return formatted.replacingOccurrences(of: ".", with: "_")
}

private func sanitizeCampaignComponent(_ value: String) -> String {
    let filtered = value.lowercased().map { character -> Character in
        switch character {
        case "a"..."z", "0"..."9":
            return character
        default:
            return "-"
        }
    }
    return String(filtered).replacingOccurrences(of: "--+", with: "-", options: .regularExpression)
}

func resolveCampaignRelativePath(
    _ rawPath: String,
    configDirectory: URL,
    dossierRoot: URL
) -> URL {
    let expanded = NSString(string: rawPath).expandingTildeInPath
    if expanded.hasPrefix("/") {
        return URL(fileURLWithPath: expanded)
    }
    let relativeToConfig = configDirectory.appendingPathComponent(expanded)
    if FileManager.default.fileExists(atPath: relativeToConfig.path) {
        return relativeToConfig
    }
    return dossierRoot.appendingPathComponent(expanded)
}

func resolvePhaseReferences(
    _ phase: LeniaCampaignPhaseConfig,
    completedPhaseOutputs: [String: URL]
) -> LeniaCampaignPhaseConfig {
    guard let seedLibrary = phase.seedLibrary, seedLibrary.hasPrefix("$PHASE:") else {
        return phase
    }
    let afterPrefix = seedLibrary.dropFirst("$PHASE:".count)
    guard let slashIndex = afterPrefix.firstIndex(of: "/") else {
        fatalError("$PHASE: reference in seed_library must include a subpath (e.g. $PHASE:discovery/exports/index.jsonl).")
    }
    let phaseName = String(afterPrefix[afterPrefix.startIndex..<slashIndex])
    let subpath = String(afterPrefix[afterPrefix.index(after: slashIndex)...])
    guard let phaseDir = completedPhaseOutputs[phaseName] else {
        fatalError("$PHASE:\(phaseName) references phase '\(phaseName)' which has not completed yet.")
    }
    let resolvedPath = phaseDir.appendingPathComponent(subpath).path
    return LeniaCampaignPhaseConfig(
        name: phase.name,
        type: phase.type,
        algorithm: phase.algorithm,
        configDir: phase.configDir,
        config: phase.config,
        baseConfig: phase.baseConfig,
        searchConfig: phase.searchConfig,
        manifest: phase.manifest,
        seeds: phase.seeds,
        seedLibrary: resolvedPath,
        seedTop: phase.seedTop,
        seedRankBy: phase.seedRankBy,
        mode: phase.mode,
        target: phase.target
    )
}

func collectCompendiumPaths(under directory: URL) -> [URL] {
    let fm = FileManager.default
    let top = directory.appendingPathComponent("compendium.sqlite")
    if fm.fileExists(atPath: top.path) {
        return [top]
    }
    guard let children = try? fm.contentsOfDirectory(at: directory, includingPropertiesForKeys: [.isDirectoryKey]) else {
        return []
    }
    return children.compactMap { child -> URL? in
        let isDir = (try? child.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) ?? false
        guard isDir else { return nil }
        let path = child.appendingPathComponent("compendium.sqlite")
        return fm.fileExists(atPath: path.path) ? path : nil
    }
}

func campaignDossierRoot() -> URL {
    URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .deletingLastPathComponent()
}

func mergeAnyCodable(
    _ lhs: [String: AnyCodable],
    _ rhs: [String: AnyCodable]
) -> [String: AnyCodable] {
    lhs.merging(rhs) { _, new in new }
}

func copySearchConfig(
    _ config: ParsedSearchConfig,
    count: Int? = nil,
    steps: Int? = nil,
    recordInterval: Int? = nil,
    warmupSteps: Int? = nil,
    topK: Int? = nil,
    batchSize: Int? = nil,
    seedStart: Int? = nil,
    overrides: [String: AnyCodable]? = nil
) -> ParsedSearchConfig {
    ParsedSearchConfig(
        count: count ?? config.count,
        seedStart: seedStart ?? config.seedStart,
        seedStride: config.seedStride,
        initSeedOffset: config.initSeedOffset,
        steps: steps ?? config.steps,
        recordInterval: recordInterval ?? config.recordInterval,
        warmupSteps: warmupSteps ?? config.warmupSteps,
        occupancyThreshold: config.occupancyThreshold,
        componentThreshold: config.componentThreshold,
        massChannel: config.massChannel,
        scoreWeights: config.scoreWeights,
        filters: config.filters,
        overrides: overrides ?? config.overrides,
        topK: topK ?? config.topK,
        batchSize: batchSize ?? config.batchSize,
        seedsPerJob: config.seedsPerJob,
        complexity: config.complexity,
        activity: config.activity,
        stability: config.stability,
        kSurvival: config.kSurvival,
        moments: config.moments,
        collection: config.collection
    )
}

func applyJSONOverrides<T: Codable>(
    _ value: T,
    overrides: [String: AnyCodable],
    context: String
) throws -> T {
    if overrides.isEmpty { return value }
    let data = try JSONEncoder().encode(value)
    guard var json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
        throw ValidationError("\(context) overrides require an object-shaped JSON config.")
    }
    applyOverrides(&json, overrides: overrides.mapValues(\.value))
    let modified = try JSONSerialization.data(withJSONObject: json)
    return try JSONDecoder().decode(T.self, from: modified)
}
