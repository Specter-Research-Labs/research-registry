import ArgumentParser
import Foundation
import LeniaCore
import Metal

func resolveMetalFirstSearchBackend(requestValue: String, baseConfig: LeniaBaseConfig) throws -> FlowLeniaComputeBackend {
    let request = try SimulationJobBackendRequest(configValue: requestValue)
    switch request {
    case .explicit(let backend):
        guard isSearchBackendCompatible(backend: backend, config: baseConfig) else {
            throw ValidationError("Requested backend \(backend.rawValue) is not compatible with this search config.")
        }
        return backend
    case .auto:
        guard MTLCreateSystemDefaultDevice() != nil else {
            throw ValidationError("Auto backend requires Apple Metal. Pass --backend mlx explicitly for reference/unsupported runs.")
        }
        guard isSearchBackendCompatible(backend: .metalFull, config: baseConfig) else {
            throw ValidationError("Auto backend requires a Metal-compatible search config. Pass --backend mlx explicitly for reference/unsupported runs.")
        }
        return .metalFull
    }
}

func resolveMetalFirstEvolutionBackend(
    requestValue: String,
    runtimeConfig: LeniaRuntimeConfig,
    esConfig: ESConfig
) throws -> FlowLeniaComputeBackend {
    let request = try SimulationJobBackendRequest(configValue: requestValue)
    switch request {
    case .explicit(let backend):
        guard backend == .mlx || isEvolutionMetalBackendCompatible(runtimeConfig: runtimeConfig, esConfig: esConfig) else {
            throw ValidationError("Requested backend \(backend.rawValue) is not compatible with this ES config.")
        }
        return backend
    case .auto:
        guard MTLCreateSystemDefaultDevice() != nil else {
            throw ValidationError("Auto backend requires Apple Metal. Pass --backend mlx explicitly for reference/unsupported runs.")
        }
        guard isEvolutionMetalBackendCompatible(runtimeConfig: runtimeConfig, esConfig: esConfig) else {
            throw ValidationError("Auto backend requires a Metal-compatible ES config. Pass --backend mlx explicitly for reference/unsupported runs.")
        }
        return .metalFull
    }
}

func resolveMetalFirstSimulatorBackend(
    requestValue: String,
    runtimeConfigs: [LeniaRuntimeConfig]
) throws -> FlowLeniaComputeBackend {
    let request = try SimulationJobBackendRequest(configValue: requestValue)
    switch request {
    case .explicit(let backend):
        guard backend == .mlx || runtimeConfigs.allSatisfy(isFlowLeniaSimulatorMetalBackendCompatible) else {
            throw ValidationError("Requested backend \(backend.rawValue) is not compatible with this simulator config.")
        }
        return backend
    case .auto:
        guard MTLCreateSystemDefaultDevice() != nil else {
            throw ValidationError("Auto backend requires Apple Metal. Pass --backend mlx explicitly for reference/unsupported runs.")
        }
        guard runtimeConfigs.allSatisfy(isFlowLeniaSimulatorMetalBackendCompatible) else {
            throw ValidationError("Auto backend requires Metal-compatible simulator configs. Pass --backend mlx explicitly for reference/unsupported runs.")
        }
        return .metalFull
    }
}

func baseConfigDataBySettingBackend(_ data: Data, backend: FlowLeniaComputeBackend) throws -> Data {
    try baseConfigDataByApplyingOverrides(data, overrides: ["backend": backend.rawValue])
}

func baseConfigDataByApplyingOverrides(_ data: Data, overrides: [String: Any]) throws -> Data {
    guard var json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
        throw ConfigError.invalidConfig("Root JSON must be an object.")
    }
    applyOverrides(&json, overrides: overrides)
    return try JSONSerialization.data(withJSONObject: json, options: [.prettyPrinted, .sortedKeys])
}

func resolveReplaySearchBackend(baseConfig: LeniaBaseConfig) throws -> FlowLeniaComputeBackend {
    if MTLCreateSystemDefaultDevice() != nil,
       isSearchBackendCompatible(backend: .metalFull, config: baseConfig) {
        return .metalFull
    }
    return try FlowLeniaComputeBackend(configValue: baseConfig.backend)
}

func resolveReplaySimulatorBackend(runtimeConfig: LeniaRuntimeConfig) throws -> FlowLeniaComputeBackend {
    if MTLCreateSystemDefaultDevice() != nil,
       isFlowLeniaSimulatorMetalBackendCompatible(runtimeConfig) {
        return .metalFull
    }
    return runtimeConfig.backend
}

func baseConfigBySettingBackend(_ baseConfig: LeniaBaseConfig, backend: FlowLeniaComputeBackend) -> LeniaBaseConfig {
    LeniaBaseConfig(
        backend: backend.rawValue,
        profile: baseConfig.profile,
        grid: baseConfig.grid,
        channels: baseConfig.channels,
        connectivity: baseConfig.connectivity,
        flow: baseConfig.flow,
        implementation: baseConfig.implementation,
        reintegration: baseConfig.reintegration,
        parameter_embedding: baseConfig.parameter_embedding,
        chemotaxis: baseConfig.chemotaxis,
        obstacle_field: baseConfig.obstacle_field,
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

private func isEvolutionMetalBackendCompatible(runtimeConfig: LeniaRuntimeConfig, esConfig: ESConfig) -> Bool {
    let validBoundaryPair = (runtimeConfig.border == "torus" && runtimeConfig.implementation.gradientBoundary == "periodic") ||
        (runtimeConfig.border == "wall" && runtimeConfig.implementation.gradientBoundary == "zero_pad")
    guard validBoundaryPair else { return false }
    if let food = runtimeConfig.food, food.enabled {
        return false
    }
    let supportedObjectives: Set<String> = [
        "directed_motion",
        "angular_motion",
        "obstacle_navigation",
        "chemotaxis",
        "template_sequence",
    ]
    return supportedObjectives.contains(esConfig.fitness.objective)
}

func isFlowLeniaSimulatorMetalBackendCompatible(_ runtimeConfig: LeniaRuntimeConfig) -> Bool {
    guard runtimeConfig.parameterEmbedding.enabled else { return false }
    guard runtimeConfig.parameterEmbedding.mix == "avg" || runtimeConfig.parameterEmbedding.mix == "stoch" else { return false }
    let validBoundaryPair = (runtimeConfig.border == "torus" && runtimeConfig.implementation.gradientBoundary == "periodic") ||
        (runtimeConfig.border == "wall" && runtimeConfig.implementation.gradientBoundary == "zero_pad")
    guard validBoundaryPair else { return false }
    return runtimeConfig.environment == nil
}
