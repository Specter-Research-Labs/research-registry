import Foundation

public struct KSurvivalConfig: Codable, Sendable {
    public let enabled: Bool
    public let blindTrials: Int
    public let deathThreshold: Float

    enum CodingKeys: String, CodingKey {
        case enabled
        case blindTrials = "blind_trials"
        case deathThreshold = "death_threshold"
    }

    public init(enabled: Bool, blindTrials: Int = 10, deathThreshold: Float = 0.01) {
        self.enabled = enabled
        self.blindTrials = blindTrials
        self.deathThreshold = deathThreshold
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        enabled = try container.decode(Bool.self, forKey: .enabled)
        blindTrials = try container.decodeIfPresent(Int.self, forKey: .blindTrials) ?? 10
        deathThreshold = try container.decodeIfPresent(Float.self, forKey: .deathThreshold) ?? 0.01
    }
}

public struct KSurvivalResult: Codable, Sendable {
    public let k: Float
    public let tauAgent: Int
    public let tauBlindMean: Float
    public let blindTrialSteps: [Int]

    enum CodingKeys: String, CodingKey {
        case k
        case tauAgent = "tau_agent"
        case tauBlindMean = "tau_blind_mean"
        case blindTrialSteps = "blind_trial_steps"
    }
}

/// K_survival = log10(tau_agent / tau_blind)
///
/// Following Chis-Ciure & Levin (2025), K measures orders of magnitude of
/// search efficiency — how much better the agent's kernel parameters are at
/// sustaining life compared to random parameters drawn from the same ranges.
/// Inverted from the paper's convention (tau_blind / tau_agent) because for
/// survival, longer is better.
///
/// Both agent and blind operate in the same problem space P = <S, O, C, E, H>:
/// same grid, same initial state, same physics, same horizon. Only the kernel
/// parameters (the "policy") differ.
public func evaluateKSurvival(
    agentSurvivalSteps: Int,
    runtimeConfig: LeniaRuntimeConfig,
    kConfig: KSurvivalConfig,
    steps: Int,
    recordInterval: Int,
    warmupSteps: Int,
    initSeed: Int,
    paramRanges: KernelParamRanges
) -> KSurvivalResult {
    if kConfig.blindTrials <= 0 {
        fatalError("k_survival.blind_trials must be > 0.")
    }

    let blindSearchConfig = SearchConfig(
        steps: steps,
        recordInterval: recordInterval,
        warmupSteps: warmupSteps,
        occupancyThreshold: 0.0,
        massChannel: -1,
        scoreWeights: [:],
        filters: [:],
        complexity: nil,
        activity: nil,
        stability: nil,
        kSurvival: KSurvivalConfig(enabled: true, deathThreshold: kConfig.deathThreshold)
    )

    var blindTrialSteps: [Int] = []
    blindTrialSteps.reserveCapacity(kConfig.blindTrials)

    for trialIndex in 0..<kConfig.blindTrials {
        let blindSeed = initSeed &* 100_003 &+ trialIndex
        let blindParams = generateRandomParams(
            seed: blindSeed,
            nbK: runtimeConfig.nbK,
            ranges: paramRanges
        )

        let blindRuntimeConfig = LeniaRuntimeConfig(
            backend: runtimeConfig.backend,
            sx: runtimeConfig.sx,
            sy: runtimeConfig.sy,
            channels: runtimeConfig.channels,
            nbK: runtimeConfig.nbK,
            profile: runtimeConfig.profile,
            c0: runtimeConfig.c0,
            c1: runtimeConfig.c1,
            dt: runtimeConfig.dt,
            dd: runtimeConfig.dd,
            sigma: runtimeConfig.sigma,
            n: runtimeConfig.n,
            thetaA: runtimeConfig.thetaA,
            border: runtimeConfig.border,
            implementation: runtimeConfig.implementation,
            params: blindParams,
            initSeed: runtimeConfig.initSeed,
            patches: runtimeConfig.patches,
            aUniform: runtimeConfig.aUniform,
            pUniform: runtimeConfig.pUniform,
            steps: runtimeConfig.steps,
            parameterEmbedding: runtimeConfig.parameterEmbedding,
            chemotaxis: runtimeConfig.chemotaxis,
            food: runtimeConfig.food,
            walls: runtimeConfig.walls,
            environment: runtimeConfig.environment,
            beamMutation: runtimeConfig.beamMutation,
            interventions: runtimeConfig.interventions
        )

        let blindEngine = SearchEngine(runtimeConfig: blindRuntimeConfig)
        let results = blindEngine.runBatch(
            seeds: [initSeed],
            initSeedOffset: 0,
            searchConfig: blindSearchConfig
        )

        let trialSteps = results[0].metrics.survivalSteps ?? steps
        blindTrialSteps.append(trialSteps)
    }

    let tauBlind = Float(blindTrialSteps.reduce(0, +)) / Float(kConfig.blindTrials)
    let tauAgent = agentSurvivalSteps

    let k: Float
    if tauBlind <= 0 {
        k = .infinity
    } else {
        k = log10(Float(tauAgent) / tauBlind)
    }

    return KSurvivalResult(
        k: k,
        tauAgent: tauAgent,
        tauBlindMean: tauBlind,
        blindTrialSteps: blindTrialSteps
    )
}
