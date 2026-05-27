import CryptoKit
import Foundation

public func connFromMatrix(_ mat: [[Int]]) -> (c0: [Int], c1: [[Int]]) {
    let c = mat.count
    var c0: [Int] = []
    var c1: [[Int]] = Array(repeating: [], count: c)
    var index = 0
    for source in 0..<c {
        for target in 0..<c {
            let count = mat[source][target]
            if count > 0 {
                c0.append(contentsOf: Array(repeating: source, count: count))
                c1[target].append(contentsOf: Array(index..<(index + count)))
            }
            index += count
        }
    }
    return (c0, c1)
}

public func generateRandomParams(seed: Int, nbK: Int, ranges: KernelParamRanges) -> ResolvedParams {
    var rng = SeededRandomNumberGenerator(seed: UInt64(seed))

    func uniformRange(_ range: [Float], count: Int) -> [Float] {
        let low = range[0]
        let high = range[1]
        return (0..<count).map { _ in Float.random(in: low...high, using: &rng) }
    }

    func uniformRange2D(_ range: [Float], rows: Int, cols: Int) -> [[Float]] {
        let low = range[0]
        let high = range[1]
        return (0..<rows).map { _ in
            (0..<cols).map { _ in Float.random(in: low...high, using: &rng) }
        }
    }

    let r = uniformRange(ranges.r, count: nbK)
    let b = uniformRange2D(ranges.b, rows: nbK, cols: 3)
    let w = uniformRange2D(ranges.w, rows: nbK, cols: 3)
    let a = uniformRange2D(ranges.a, rows: nbK, cols: 3)
    let m = uniformRange(ranges.m, count: nbK)
    let s = uniformRange(ranges.s, count: nbK)
    let h = uniformRange(ranges.h, count: nbK)
    let R = Float.random(in: ranges.R[0]...ranges.R[1], using: &rng)

    return ResolvedParams(r: r, b: b, w: w, a: a, m: m, s: s, h: h, R: R, seed: seed)
}

public struct SeededRandomNumberGenerator: RandomNumberGenerator {
    private var state: UInt64

    public init(seed: UInt64) {
        self.state = seed
    }

    public mutating func next() -> UInt64 {
        state &+= 0x9e3779b97f4a7c15
        var z = state
        z = (z ^ (z >> 30)) &* 0xbf58476d1ce4e5b9
        z = (z ^ (z >> 27)) &* 0x94d049bb133111eb
        return z ^ (z >> 31)
    }
}

public func loadRuntimeConfig(from jsonData: Data, overrides: [String: Any]? = nil) throws -> LeniaRuntimeConfig {
    guard var json = try JSONSerialization.jsonObject(with: jsonData) as? [String: Any] else {
        throw ConfigError.invalidConfig("Root JSON must be an object.")
    }

    if let overrides = overrides {
        applyOverrides(&json, overrides: overrides)
    }

    let modifiedData = try JSONSerialization.data(withJSONObject: json)
    let baseConfig = try JSONDecoder().decode(LeniaBaseConfig.self, from: modifiedData)
    let model = baseConfig.model
    let execution = baseConfig.execution
    let initialState = baseConfig.initialState

    let nbK = try validateBaseConfig(baseConfig)
    try validateProfileCompatibility(profile: execution.profile, implementation: execution.implementation)

    let (c0, c1) = connFromMatrix(model.connectivity)

    let resolvedParams: ResolvedParams
    if model.params.mode == "random" {
        guard let seed = model.params.seed,
              let ranges = model.params.ranges else {
            throw ConfigError.missingParamSeed
        }
        resolvedParams = generateRandomParams(seed: seed, nbK: nbK, ranges: ranges)
    } else if model.params.mode == "explicit" {
        guard let r = model.params.r,
              let b = model.params.b,
              let w = model.params.w,
              let a = model.params.a,
              let m = model.params.m,
              let s = model.params.s,
              let h = model.params.h,
              let R = model.params.R else {
            throw ConfigError.missingExplicitParams
        }
        resolvedParams = ResolvedParams(
            r: r,
            b: b,
            w: w,
            a: a,
            m: m,
            s: s,
            h: h,
            R: R,
            seed: model.params.seed ?? 0
        )
    } else {
        throw ConfigError.unsupportedParamMode(model.params.mode)
    }

    let resolvedBackend = try FlowLeniaComputeBackend(configValue: execution.backend)

    return LeniaRuntimeConfig(
        backend: resolvedBackend,
        sx: model.grid.sx,
        sy: model.grid.sy,
        channels: model.channels,
        nbK: nbK,
        profile: execution.profile,
        c0: c0,
        c1: c1,
        dt: model.flow.dt,
        dd: model.reintegration.dd,
        sigma: model.reintegration.sigma,
        n: model.flow.n,
        thetaA: model.flow.theta_A,
        border: model.reintegration.border,
        implementation: resolveImplementationSettings(
            implementation: execution.implementation,
            border: model.reintegration.border
        ),
        params: resolvedParams,
        randomParamRanges: model.params.mode == "random" ? model.params.ranges : nil,
        initSeed: initialState.seed,
        patches: initialState.patches,
        aUniform: initialState.a_uniform,
        pUniform: initialState.p_uniform,
        statePatch: initialState.state_patch,
        paramPatch: initialState.p_state_patch,
        steps: execution.run.steps,
        parameterEmbedding: model.parameterEmbedding,
        chemotaxis: model.chemotaxis,
        obstacleField: model.obstacleField,
        food: model.food,
        walls: model.walls,
        environment: model.environment,
        beamMutation: model.beamMutation,
        interventions: execution.interventions
    )
}

public func applyOverrides(_ json: inout [String: Any], overrides: [String: Any]) {
    for (path, value) in overrides {
        let parts = path.split(separator: ".").map(String.init)
        setNestedValue(&json, path: parts, value: value)
    }
}

public func setNestedValue(_ dict: inout [String: Any], path: [String], value: Any) {
    guard !path.isEmpty else { return }

    if path.count == 1 {
        dict[path[0]] = value
    } else {
        let key = path[0]
        var nested = dict[key] as? [String: Any] ?? [:]
        setNestedValue(&nested, path: Array(path.dropFirst()), value: value)
        dict[key] = nested
    }
}

public func configTopologyHash(_ config: LeniaBaseConfig) -> String {
    let model = config.model
    var dict: [String: Any] = [
        "sx": model.grid.sx,
        "sy": model.grid.sy,
        "channels": model.channels,
        "connectivity": model.connectivity,
        "border": model.reintegration.border,
        "mode": config.execution.implementation.mode,
        "food": model.food?.enabled ?? false,
        "walls": model.walls?.enabled ?? false,
        "obstacle_field": model.obstacleField?.enabled ?? false,
        "param_embed": model.parameterEmbedding.enabled,
    ]
    if let env = model.environment {
        dict["environment_type"] = env.type
    }
    let json = try! JSONSerialization.data(
        withJSONObject: dict,
        options: [.sortedKeys]
    )
    let digest = SHA256.hash(data: json)
    return digest.prefix(6).map { String(format: "%02x", $0) }.joined()
}
