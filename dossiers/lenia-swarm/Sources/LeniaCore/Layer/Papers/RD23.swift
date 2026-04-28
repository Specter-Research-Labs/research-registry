import Foundation
import Logging
import MLX
import MLXFFT

public struct ReactionDiffusionLenia2023AsymptoticConfig: Codable, Sendable {
    public let paper: String
    public let kernelFunction: String
    public let reactionTransform: String
    public let dtValues: [Float]
    public let gaussianMean: Float
    public let gaussianStd: Float
    public let orbiumConfig: String

    enum CodingKeys: String, CodingKey {
        case paper
        case kernelFunction = "kernel_function"
        case reactionTransform = "reaction_transform"
        case dtValues = "dt_values"
        case gaussianMean = "gaussian_mean"
        case gaussianStd = "gaussian_std"
        case orbiumConfig = "orbium_config"
    }
}

public struct ReactionDiffusionLenia2023ValidationConfig: Codable, Sendable {
    public let compareOriginalLenia: Bool
    public let compareAsymptoticLenia: Bool
    public let lowerClipOnlyAtSmallDt: Bool
    public let occasionalUpperClipDelta: Float
    public let expectedSmallDtThreshold: Float

    enum CodingKeys: String, CodingKey {
        case compareOriginalLenia = "compare_original_lenia"
        case compareAsymptoticLenia = "compare_asymptotic_lenia"
        case lowerClipOnlyAtSmallDt = "lower_clip_only_at_small_dt"
        case occasionalUpperClipDelta = "occasional_upper_clip_delta"
        case expectedSmallDtThreshold = "expected_small_dt_threshold"
    }
}

public struct ReactionDiffusionLenia2023EmulationConfig: Codable, Sendable {
    public let auxiliaryVariableCount: Int
    public let mu: Float
    public let diffusionStart: Int
    public let diffusionEnd: Int
    public let epsilon: Float
    public let eulerDt: Float

    enum CodingKeys: String, CodingKey {
        case auxiliaryVariableCount = "auxiliary_variable_count"
        case mu
        case diffusionStart = "diffusion_start"
        case diffusionEnd = "diffusion_end"
        case epsilon
        case eulerDt = "euler_dt"
    }
}

public struct ReactionDiffusionLenia2023ConfigBundle: Sendable {
    public let configDirectory: URL
    public let asymptotic: ReactionDiffusionLenia2023AsymptoticConfig
    public let validation: ReactionDiffusionLenia2023ValidationConfig
    public let emulation: ReactionDiffusionLenia2023EmulationConfig
}

public func loadReactionDiffusionLenia2023ConfigBundle(configDirectory: URL) throws -> ReactionDiffusionLenia2023ConfigBundle {
    let decoder = JSONDecoder()
    let asymptotic = try decoder.decode(
        ReactionDiffusionLenia2023AsymptoticConfig.self,
        from: Data(contentsOf: configDirectory.appendingPathComponent("asymptotic.json"))
    )
    let validation = try decoder.decode(
        ReactionDiffusionLenia2023ValidationConfig.self,
        from: Data(contentsOf: configDirectory.appendingPathComponent("validation.json"))
    )
    let emulation = try decoder.decode(
        ReactionDiffusionLenia2023EmulationConfig.self,
        from: Data(contentsOf: configDirectory.appendingPathComponent("rd_emulation.json"))
    )
    try validateReactionDiffusionLenia2023Config(
        asymptotic: asymptotic,
        validation: validation,
        emulation: emulation,
        configDirectory: configDirectory
    )
    return ReactionDiffusionLenia2023ConfigBundle(
        configDirectory: configDirectory,
        asymptotic: asymptotic,
        validation: validation,
        emulation: emulation
    )
}

private func validateReactionDiffusionLenia2023Config(
    asymptotic: ReactionDiffusionLenia2023AsymptoticConfig,
    validation: ReactionDiffusionLenia2023ValidationConfig,
    emulation: ReactionDiffusionLenia2023EmulationConfig,
    configDirectory: URL
) throws {
    guard asymptotic.paper == "implementation-of-lenia-as-a-reaction-diffusion-system-2023" else {
        throw ConfigError.invalidConfig("reaction-diffusion-lenia-2023 asymptotic.paper must match the 2023 RD paper identifier.")
    }
    guard asymptotic.kernelFunction == "gauss" else {
        throw ConfigError.invalidConfig("reaction-diffusion-lenia-2023 currently expects kernel_function=\"gauss\" from the paper discussion.")
    }
    guard asymptotic.reactionTransform == "T=(G+1)/2" else {
        throw ConfigError.invalidConfig("reaction-diffusion-lenia-2023 reaction_transform must be \"T=(G+1)/2\".")
    }
    guard !asymptotic.dtValues.isEmpty, asymptotic.dtValues.allSatisfy({ $0 > 0 }) else {
        throw ConfigError.invalidConfig("reaction-diffusion-lenia-2023 dt_values must contain positive values.")
    }
    guard asymptotic.gaussianStd > 0 else {
        throw ConfigError.invalidConfig("reaction-diffusion-lenia-2023 gaussian_std must be > 0.")
    }
    let orbiumURL = configDirectory.appendingPathComponent(asymptotic.orbiumConfig)
    guard FileManager.default.fileExists(atPath: orbiumURL.path) else {
        throw ConfigError.invalidConfig("reaction-diffusion-lenia-2023 orbium_config is missing at \(orbiumURL.path).")
    }
    guard validation.compareOriginalLenia || validation.compareAsymptoticLenia else {
        throw ConfigError.invalidConfig("reaction-diffusion-lenia-2023 validation must compare original Lenia, asymptotic Lenia, or both.")
    }
    guard validation.occasionalUpperClipDelta > 0, validation.expectedSmallDtThreshold > 0 else {
        throw ConfigError.invalidConfig("reaction-diffusion-lenia-2023 clipping validation thresholds must be > 0.")
    }
    guard emulation.auxiliaryVariableCount == 40 else {
        throw ConfigError.invalidConfig("reaction-diffusion-lenia-2023 auxiliary_variable_count must be 40 to match the paper emulation.")
    }
    guard emulation.mu == 0.1 else {
        throw ConfigError.invalidConfig("reaction-diffusion-lenia-2023 emulation.mu must be 0.1 to match the paper.")
    }
    guard emulation.diffusionStart == 1, emulation.diffusionEnd == 40 else {
        throw ConfigError.invalidConfig("reaction-diffusion-lenia-2023 diffusion constants must span Dj=j for j in 1...40.")
    }
    guard emulation.epsilon == 0.005, emulation.eulerDt == 0.00001 else {
        throw ConfigError.invalidConfig("reaction-diffusion-lenia-2023 emulation must use epsilon=0.005 and euler_dt=1e-5.")
    }
}

public struct ReactionDiffusion2023TrajectorySummary: Codable, Sendable {
    public let variant: String
    public let dt: Float
    public let steps: Int
    public let finalMass: Float
    public let finalCenterX: Float
    public let finalCenterY: Float
    public let pathLength: Float
    public let finalMinimum: Float
    public let finalMaximum: Float
    public let l2ToReference: Float?

    enum CodingKeys: String, CodingKey {
        case variant, dt, steps
        case finalMass = "final_mass"
        case finalCenterX = "final_center_x"
        case finalCenterY = "final_center_y"
        case pathLength = "path_length"
        case finalMinimum = "final_minimum"
        case finalMaximum = "final_maximum"
        case l2ToReference = "l2_to_reference"
    }
}

public struct ReactionDiffusion2023ClippingSummary: Codable, Sendable {
    public let dt: Float
    public let occasionalClipIntervalSteps: Int
    public let lowerOnly: ReactionDiffusion2023TrajectorySummary
    public let occasionalUpperClip: ReactionDiffusion2023TrajectorySummary

    enum CodingKeys: String, CodingKey {
        case dt
        case occasionalClipIntervalSteps = "occasional_clip_interval_steps"
        case lowerOnly = "lower_only"
        case occasionalUpperClip = "occasional_upper_clip"
    }
}

public struct ReactionDiffusion2023KernelEmulationSummary: Codable, Sendable {
    public let alpha0: Double
    public let coefficients: [Double]
    public let rmse: Double
    public let maxAbsError: Double

    enum CodingKeys: String, CodingKey {
        case alpha0, coefficients, rmse
        case maxAbsError = "max_abs_error"
    }
}

public struct ReactionDiffusion2023RunSummary: Codable, Sendable {
    public let original: [ReactionDiffusion2023TrajectorySummary]
    public let asymptotic: [ReactionDiffusion2023TrajectorySummary]
    public let clipping: ReactionDiffusion2023ClippingSummary
    public let kernelEmulation: ReactionDiffusion2023KernelEmulationSummary

    enum CodingKeys: String, CodingKey {
        case original, asymptotic, clipping
        case kernelEmulation = "kernel_emulation"
    }
}

private enum ReactionDiffusion2023Variant: String {
    case original = "original_lenia"
    case asymptotic = "asymptotic_lenia"
    case lowerOnly = "lower_clip_only"
    case occasionalUpperClip = "occasional_upper_clip"
}

private struct ReactionDiffusion2023Rollout {
    let summary: ReactionDiffusion2023TrajectorySummary
    let finalState: [Float]
}

private struct ReactionDiffusion2023OrbiumSpec {
    let runtime: LeniaRuntimeConfig
    let kernelFFT: MLXArray
    let initialState: MLXArray
    let baselinePhysicalDuration: Float
    let growthMean: Float
    let growthStd: Float
    let growthScale: Float
    let worldSize: Int
}

public final class ReactionDiffusionLenia2023Runner {
    private let configs: ReactionDiffusionLenia2023ConfigBundle
    private let logger: Logger
    private let encoder: JSONEncoder

    public init(configs: ReactionDiffusionLenia2023ConfigBundle, logger: Logger) {
        self.configs = configs
        self.logger = logger
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        self.encoder = encoder
    }

    public func writeResolvedConfigs(to outputDirectory: URL) throws {
        try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
        try encoder.encode(configs.asymptotic).write(to: outputDirectory.appendingPathComponent("asymptotic.json"))
        try encoder.encode(configs.validation).write(to: outputDirectory.appendingPathComponent("validation.json"))
        try encoder.encode(configs.emulation).write(to: outputDirectory.appendingPathComponent("rd_emulation.json"))
    }

    public func run(outputDirectory: URL) throws -> ReactionDiffusion2023RunSummary {
        try writeResolvedConfigs(to: outputDirectory)

        let orbium = try reactionDiffusion2023LoadOrbiumSpec(configs: configs)
        let originalURL = outputDirectory.appendingPathComponent("original.json")
        let asymptoticURL = outputDirectory.appendingPathComponent("asymptotic.json")
        let clippingURL = outputDirectory.appendingPathComponent("clipping.json")
        let emulationURL = outputDirectory.appendingPathComponent("kernel-emulation.json")
        let summaryURL = outputDirectory.appendingPathComponent("summary.json")

        var originalRuns: [ReactionDiffusion2023Rollout] = []
        var asymptoticRuns: [ReactionDiffusion2023Rollout] = []

        for dt in configs.asymptotic.dtValues {
            let steps = max(1, Int((orbium.baselinePhysicalDuration / dt).rounded()))
            logger.info("RD 2023: dt=\(dt), steps=\(steps)")
            originalRuns.append(
                try reactionDiffusion2023RunRollout(
                    variant: .original,
                    dt: dt,
                    steps: steps,
                    orbium: orbium
                )
            )
            asymptoticRuns.append(
                try reactionDiffusion2023RunRollout(
                    variant: .asymptotic,
                    dt: dt,
                    steps: steps,
                    orbium: orbium
                )
            )
        }

        let referenceIndex = reactionDiffusion2023ReferenceIndex(dtValues: configs.asymptotic.dtValues)
        let originalSummaries = reactionDiffusion2023AttachReferenceDistances(
            rollouts: originalRuns,
            referenceIndex: referenceIndex
        )
        let asymptoticSummaries = reactionDiffusion2023AttachReferenceDistances(
            rollouts: asymptoticRuns,
            referenceIndex: referenceIndex
        )
        try encoder.encode(originalSummaries).write(to: originalURL)
        try encoder.encode(asymptoticSummaries).write(to: asymptoticURL)

        let clippingDt = reactionDiffusion2023ClippingDt(configs: configs)
        let clippingSteps = max(1, Int((orbium.baselinePhysicalDuration / clippingDt).rounded()))
        let clipInterval = max(1, Int((configs.validation.occasionalUpperClipDelta / clippingDt).rounded()))
        let lowerOnly = try reactionDiffusion2023RunRollout(
            variant: .lowerOnly,
            dt: clippingDt,
            steps: clippingSteps,
            orbium: orbium
        )
        let occasionalUpperClip = try reactionDiffusion2023RunRollout(
            variant: .occasionalUpperClip,
            dt: clippingDt,
            steps: clippingSteps,
            orbium: orbium,
            occasionalUpperClipEvery: clipInterval
        )
        let clipping = ReactionDiffusion2023ClippingSummary(
            dt: clippingDt,
            occasionalClipIntervalSteps: clipInterval,
            lowerOnly: lowerOnly.summary,
            occasionalUpperClip: occasionalUpperClip.summary
        )
        try encoder.encode(clipping).write(to: clippingURL)

        let kernelEmulation = try reactionDiffusion2023KernelEmulation(configs: configs, orbium: orbium)
        try encoder.encode(kernelEmulation).write(to: emulationURL)

        let summary = ReactionDiffusion2023RunSummary(
            original: originalSummaries,
            asymptotic: asymptoticSummaries,
            clipping: clipping,
            kernelEmulation: kernelEmulation
        )
        try encoder.encode(summary).write(to: summaryURL)
        return summary
    }
}

private func reactionDiffusion2023LoadOrbiumSpec(
    configs: ReactionDiffusionLenia2023ConfigBundle
) throws -> ReactionDiffusion2023OrbiumSpec {
    let orbiumURL = configs.configDirectory.appendingPathComponent(configs.asymptotic.orbiumConfig)
    let jsonData = try Data(contentsOf: orbiumURL)
    let runtime = try loadRuntimeConfig(from: jsonData)
    guard runtime.channels == 1, runtime.nbK == 1 else {
        throw ConfigError.invalidConfig("reaction-diffusion-lenia-2023 currently supports only single-channel single-kernel orbium-style configs.")
    }
    let batchedConfig = batchedConfigFromRuntime(runtime)
    let kernels = compileKernels(params: runtime.params, config: batchedConfig, c0: runtime.c0, c1: runtime.c1)
    let kernelFFT = kernels.fK[0, 0..., 0..., 0]
    let initialState = reactionDiffusion2023BuildInitialState(runtime: runtime)
    return ReactionDiffusion2023OrbiumSpec(
        runtime: runtime,
        kernelFFT: kernelFFT,
        initialState: initialState,
        baselinePhysicalDuration: Float(runtime.steps) * runtime.dt,
        growthMean: runtime.params.m[0],
        growthStd: runtime.params.s[0],
        growthScale: runtime.params.h[0],
        worldSize: runtime.sx
    )
}

private func reactionDiffusion2023BuildInitialState(runtime: LeniaRuntimeConfig) -> MLXArray {
    var rng = SeededRandomNumberGenerator(seed: UInt64(max(0, runtime.initSeed)))
    let width = runtime.sx
    let height = runtime.sy
    var values = [Float](repeating: 0, count: width * height)
    let patches = runtime.patches.isEmpty
        ? [PatchConfig(center: [width / 2, height / 2], size: 40)]
        : runtime.patches
    for patch in patches {
        let cx = patch.center[0]
        let cy = patch.center[1]
        let half = patch.size / 2
        for x in (cx - half)..<(cx + patch.size - half) {
            guard x >= 0 && x < width else { continue }
            for y in (cy - half)..<(cy + patch.size - half) {
                guard y >= 0 && y < height else { continue }
                values[x * height + y] = Float.random(in: runtime.aUniform.low...runtime.aUniform.high, using: &rng)
            }
        }
    }
    return MLXArray(values).reshaped([width, height])
}

private func reactionDiffusion2023RunRollout(
    variant: ReactionDiffusion2023Variant,
    dt: Float,
    steps: Int,
    orbium: ReactionDiffusion2023OrbiumSpec,
    occasionalUpperClipEvery: Int? = nil
) throws -> ReactionDiffusion2023Rollout {
    var current = orbium.initialState
    var masses: [Float] = []
    var centers: [(Float, Float)] = []
    masses.reserveCapacity(steps)
    centers.reserveCapacity(steps)

    for step in 0..<steps {
        switch variant {
        case .original:
            current = reactionDiffusion2023OriginalStep(
                current,
                kernelFFT: orbium.kernelFFT,
                dt: dt,
                mean: orbium.growthMean,
                std: orbium.growthStd,
                scale: orbium.growthScale,
                lowerClip: true,
                upperClip: true
            )
        case .asymptotic:
            current = reactionDiffusion2023AsymptoticStep(
                current,
                kernelFFT: orbium.kernelFFT,
                dt: dt,
                mean: orbium.growthMean,
                std: orbium.growthStd,
                scale: orbium.growthScale
            )
        case .lowerOnly:
            current = reactionDiffusion2023OriginalStep(
                current,
                kernelFFT: orbium.kernelFFT,
                dt: dt,
                mean: orbium.growthMean,
                std: orbium.growthStd,
                scale: orbium.growthScale,
                lowerClip: true,
                upperClip: false
            )
        case .occasionalUpperClip:
            let shouldUpperClip = if let occasionalUpperClipEvery {
                step % occasionalUpperClipEvery == 0
            } else {
                false
            }
            current = reactionDiffusion2023OriginalStep(
                current,
                kernelFFT: orbium.kernelFFT,
                dt: dt,
                mean: orbium.growthMean,
                std: orbium.growthStd,
                scale: orbium.growthScale,
                lowerClip: true,
                upperClip: shouldUpperClip
            )
        }
        let (mass, centerX, centerY) = reactionDiffusion2023MassAndCenter(current)
        masses.append(mass)
        centers.append((centerX, centerY))
    }

    eval(current)
    let finalState = current.asArray(Float.self)
    let finalMass = masses.last ?? 0
    let finalCenter = centers.last ?? (0, 0)
    let pathLength = reactionDiffusion2023PathLength(centers)
    let minValue = finalState.min() ?? 0
    let maxValue = finalState.max() ?? 0

    return ReactionDiffusion2023Rollout(
        summary: ReactionDiffusion2023TrajectorySummary(
            variant: variant.rawValue,
            dt: dt,
            steps: steps,
            finalMass: finalMass,
            finalCenterX: finalCenter.0,
            finalCenterY: finalCenter.1,
            pathLength: pathLength,
            finalMinimum: minValue,
            finalMaximum: maxValue,
            l2ToReference: nil
        ),
        finalState: finalState
    )
}

private func reactionDiffusion2023OriginalStep(
    _ state: MLXArray,
    kernelFFT: MLXArray,
    dt: Float,
    mean: Float,
    std: Float,
    scale: Float,
    lowerClip: Bool,
    upperClip: Bool
) -> MLXArray {
    let stateFFT = MLXFFT.fft2(state, axes: [0, 1])
    let convolved = MLXFFT.ifft2(stateFFT * kernelFFT, axes: [0, 1]).realPart()
    let growthField = reactionDiffusion2023Growth(convolved, mean: mean, std: std, scale: scale)
    var next = state + MLXArray(dt) * growthField
    if lowerClip {
        next = MLX.maximum(next, MLXArray(0.0))
    }
    if upperClip {
        next = MLX.minimum(next, MLXArray(1.0))
    }
    return next
}

private func reactionDiffusion2023AsymptoticStep(
    _ state: MLXArray,
    kernelFFT: MLXArray,
    dt: Float,
    mean: Float,
    std: Float,
    scale: Float
) -> MLXArray {
    let stateFFT = MLXFFT.fft2(state, axes: [0, 1])
    let convolved = MLXFFT.ifft2(stateFFT * kernelFFT, axes: [0, 1]).realPart()
    let growthField = reactionDiffusion2023Growth(convolved, mean: mean, std: std, scale: scale)
    let target = (growthField + MLXArray(1.0)) / MLXArray(2.0)
    return state + MLXArray(dt) * (target - state)
}

private func reactionDiffusion2023Growth(
    _ field: MLXArray,
    mean: Float,
    std: Float,
    scale: Float
) -> MLXArray {
    let diff = (field - MLXArray(mean)) / MLXArray(std)
    return (MLXArray(2.0) * MLX.exp(-((diff * diff) / MLXArray(2.0))) - MLXArray(1.0)) * MLXArray(scale)
}

private func reactionDiffusion2023MassAndCenter(_ state: MLXArray) -> (Float, Float, Float) {
    eval(state)
    let width = state.shape[0]
    let height = state.shape[1]
    let values = state.asArray(Float.self)
    var mass: Float = 0
    var weightedX: Float = 0
    var weightedY: Float = 0
    for x in 0..<width {
        let rowOffset = x * height
        for y in 0..<height {
            let value = values[rowOffset + y]
            mass += value
            weightedX += Float(x) * value
            weightedY += Float(y) * value
        }
    }
    guard mass > 0 else { return (0, 0, 0) }
    return (mass, weightedX / mass, weightedY / mass)
}

private func reactionDiffusion2023PathLength(_ centers: [(Float, Float)]) -> Float {
    guard centers.count > 1 else { return 0 }
    var total: Float = 0
    for index in 1..<centers.count {
        let dx = centers[index].0 - centers[index - 1].0
        let dy = centers[index].1 - centers[index - 1].1
        total += sqrt(dx * dx + dy * dy)
    }
    return total
}

private func reactionDiffusion2023ReferenceIndex(dtValues: [Float]) -> Int {
    guard let minDt = dtValues.min(), let index = dtValues.firstIndex(of: minDt) else {
        return 0
    }
    return index
}

private func reactionDiffusion2023AttachReferenceDistances(
    rollouts: [ReactionDiffusion2023Rollout],
    referenceIndex: Int
) -> [ReactionDiffusion2023TrajectorySummary] {
    guard !rollouts.isEmpty else { return [] }
    let reference = rollouts[referenceIndex].finalState
    return rollouts.map { rollout in
        let diff = reactionDiffusion2023L2Distance(rollout.finalState, reference)
        return ReactionDiffusion2023TrajectorySummary(
            variant: rollout.summary.variant,
            dt: rollout.summary.dt,
            steps: rollout.summary.steps,
            finalMass: rollout.summary.finalMass,
            finalCenterX: rollout.summary.finalCenterX,
            finalCenterY: rollout.summary.finalCenterY,
            pathLength: rollout.summary.pathLength,
            finalMinimum: rollout.summary.finalMinimum,
            finalMaximum: rollout.summary.finalMaximum,
            l2ToReference: diff
        )
    }
}

private func reactionDiffusion2023L2Distance(_ lhs: [Float], _ rhs: [Float]) -> Float {
    guard lhs.count == rhs.count else { return .infinity }
    var total: Float = 0
    for index in lhs.indices {
        let delta = lhs[index] - rhs[index]
        total += delta * delta
    }
    return sqrt(total / Float(max(lhs.count, 1)))
}

private func reactionDiffusion2023ClippingDt(
    configs: ReactionDiffusionLenia2023ConfigBundle
) -> Float {
    let preferred = configs.asymptotic.dtValues
        .filter { $0 <= configs.validation.expectedSmallDtThreshold }
        .min()
    return preferred ?? configs.asymptotic.dtValues.min() ?? configs.validation.expectedSmallDtThreshold
}

private func reactionDiffusion2023KernelEmulation(
    configs: ReactionDiffusionLenia2023ConfigBundle,
    orbium: ReactionDiffusion2023OrbiumSpec
) throws -> ReactionDiffusion2023KernelEmulationSummary {
    let batchedConfig = batchedConfigFromRuntime(orbium.runtime)
    let kernel = normalizedSpatialKernelStack(params: orbium.runtime.params, config: batchedConfig)[0..., 0..., 0]
    eval(kernel)
    let target = kernel.asArray(Float.self)
    let width = orbium.worldSize
    let lapFFT = reactionDiffusion2023LaplacianFFT(size: width)

    var delta = [Float](repeating: 0, count: width * width)
    delta[(width / 2) * width + width / 2] = 1
    let deltaField = MLXArray(delta).reshaped([width, width])
    let deltaFFT = MLXFFT.fft2(deltaField, axes: [0, 1])

    let mu = MLXArray(configs.emulation.mu)
    var features = Array(repeating: [Double](repeating: 0, count: width * width), count: configs.emulation.auxiliaryVariableCount)
    for (index, diffusion) in (configs.emulation.diffusionStart...configs.emulation.diffusionEnd).enumerated() {
        let denom = MLXArray(1.0) - MLXArray(Float(diffusion)) * lapFFT
        let vFFT = (mu * deltaFFT) / denom
        let vField = MLXFFT.ifft2(vFFT, axes: [0, 1]).realPart()
        eval(vField)
        features[index] = vField.asArray(Float.self).map(Double.init)
    }

    let fit = try reactionDiffusion2023SolveLeastSquares(target: target.map(Double.init), features: features)
    return ReactionDiffusion2023KernelEmulationSummary(
        alpha0: fit.alpha0,
        coefficients: fit.coefficients,
        rmse: fit.rmse,
        maxAbsError: fit.maxAbsError
    )
}

private func reactionDiffusion2023LaplacianFFT(size: Int) -> MLXArray {
    var values = [Float](repeating: 0, count: size * size)
    let mid = size / 2
    func set(_ x: Int, _ y: Int, _ value: Float) {
        values[x * size + y] = value
    }
    set(mid, mid, -4)
    set(mid - 1, mid, 1)
    set(mid + 1, mid, 1)
    set(mid, mid - 1, 1)
    set(mid, mid + 1, 1)
    let kernel = MLXArray(values).reshaped([size, size])
    return MLXFFT.fft2(rollMultiAxis(kernel, shifts: [-mid, -mid], axes: [0, 1]), axes: [0, 1])
}

private func reactionDiffusion2023SolveLeastSquares(
    target: [Double],
    features: [[Double]]
) throws -> (alpha0: Double, coefficients: [Double], rmse: Double, maxAbsError: Double) {
    guard let sampleCount = features.first?.count, target.count == sampleCount else {
        throw ConfigError.invalidConfig("reaction-diffusion-lenia-2023 kernel regression requires features with the same sample count as the target.")
    }
    let featureCount = features.count + 1
    var xtx = Array(repeating: Array(repeating: 0.0, count: featureCount), count: featureCount)
    var xty = Array(repeating: 0.0, count: featureCount)

    for sampleIndex in 0..<sampleCount {
        var row = [Double](repeating: 0, count: featureCount)
        row[0] = 1.0
        for featureIndex in features.indices {
            row[featureIndex + 1] = features[featureIndex][sampleIndex]
        }
        let y = target[sampleIndex]
        for i in 0..<featureCount {
            xty[i] += row[i] * y
            for j in 0..<featureCount {
                xtx[i][j] += row[i] * row[j]
            }
        }
    }

    for index in 0..<featureCount {
        xtx[index][index] += 1e-8
    }

    let coefficients = try reactionDiffusion2023GaussianSolve(matrix: xtx, rhs: xty)
    var squaredError = 0.0
    var maxAbsError = 0.0
    for sampleIndex in 0..<sampleCount {
        var prediction = coefficients[0]
        for featureIndex in features.indices {
            prediction += coefficients[featureIndex + 1] * features[featureIndex][sampleIndex]
        }
        let error = prediction - target[sampleIndex]
        squaredError += error * error
        maxAbsError = max(maxAbsError, abs(error))
    }
    return (
        alpha0: coefficients[0],
        coefficients: Array(coefficients.dropFirst()),
        rmse: sqrt(squaredError / Double(max(sampleCount, 1))),
        maxAbsError: maxAbsError
    )
}

private func reactionDiffusion2023GaussianSolve(
    matrix: [[Double]],
    rhs: [Double]
) throws -> [Double] {
    var a = matrix
    var b = rhs
    let count = rhs.count
    for pivot in 0..<count {
        var bestRow = pivot
        var bestValue = abs(a[pivot][pivot])
        for row in (pivot + 1)..<count {
            let value = abs(a[row][pivot])
            if value > bestValue {
                bestValue = value
                bestRow = row
            }
        }
        if bestValue < 1e-12 {
            throw ConfigError.invalidConfig("reaction-diffusion-lenia-2023 kernel regression matrix is singular.")
        }
        if bestRow != pivot {
            a.swapAt(pivot, bestRow)
            b.swapAt(pivot, bestRow)
        }
        let pivotValue = a[pivot][pivot]
        for column in pivot..<count {
            a[pivot][column] /= pivotValue
        }
        b[pivot] /= pivotValue
        for row in 0..<count where row != pivot {
            let factor = a[row][pivot]
            guard factor != 0 else { continue }
            for column in pivot..<count {
                a[row][column] -= factor * a[pivot][column]
            }
            b[row] -= factor * b[pivot]
        }
    }
    return b
}
