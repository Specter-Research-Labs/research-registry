import Foundation
import Logging
import MLX
import MLXFFT
import simd

// Classical Lenia parameter-space atlas: a mu/sigma sweep classified into phases
// (order / chaos / transition) via Voronoi-polygon probes. Paper: Hudcova et al.,
// "Visualizing the Structure of Lenia Parameter Space" (2026). CLI: discover atlas-2026.
public struct Atlas2026KernelConfig: Codable, Sendable {
    public let paper: String
    public let arraySize: Int
    public let dt: Float
    public let function: String
    public let radius: Int
    public let betas: [Float]
    public let muK: [Float]?
    public let sigmaK: [Float]?

    enum CodingKeys: String, CodingKey {
        case paper
        case arraySize = "array_size"
        case dt
        case function
        case radius
        case betas
        case muK = "mu_k"
        case sigmaK = "sigma_k"
    }
}

public struct Atlas2026SweepConfig: Codable, Sendable {
    public struct RangeSpec: Codable, Sendable {
        public let start: Float
        public let stop: Float
        public let step: Float
    }

    public let mu: RangeSpec
    public let sigma: RangeSpec
    public let batchSize: Int
    public let samplesPerPolygon: Int
    public let polygonSizes: [Int]
    public let refineTransitions: Bool

    enum CodingKeys: String, CodingKey {
        case mu, sigma
        case batchSize = "batch_size"
        case samplesPerPolygon = "samples_per_polygon"
        case polygonSizes = "polygon_sizes"
        case refineTransitions = "refine_transitions"
    }
}

public struct Atlas2026InitConfig: Codable, Sendable {
    public let generatorSeed: Int
    public let polygonLibrarySize: Int
    public let polygonLibraryJSONPath: String?
    public let smallVoronoiPointRange: [Int]
    public let largeVoronoiPointRange: [Int]

    enum CodingKeys: String, CodingKey {
        case generatorSeed = "generator_seed"
        case polygonLibrarySize = "polygon_library_size"
        case polygonLibraryJSONPath = "polygon_library_json_path"
        case smallVoronoiPointRange = "small_voronoi_point_range"
        case largeVoronoiPointRange = "large_voronoi_point_range"
    }
}

public struct Atlas2026ClassifierConfig: Codable, Sendable {
    public let windowSize: Int
    public let std: Float
    public let shortTMaxMultiplier: Int
    public let longTMaxMultiplier: Int

    enum CodingKeys: String, CodingKey {
        case windowSize = "window_size"
        case std
        case shortTMaxMultiplier = "short_tmax_multiplier"
        case longTMaxMultiplier = "long_tmax_multiplier"
    }
}

public struct Atlas2026ConfigBundle: Sendable {
    public let configDirectory: URL
    public let kernel: Atlas2026KernelConfig
    public let sweep: Atlas2026SweepConfig
    public let initialization: Atlas2026InitConfig
    public let classifier: Atlas2026ClassifierConfig
}

public struct Atlas2026RunSummary: Codable, Sendable {
    public let systems: Int
    public let polygonSizes: [Int]
    public let muCount: Int
    public let sigmaCount: Int
    public let kernelKey: String
}

private enum Atlas2026LocalPhase: Int, Codable {
    case order = 0
    case chaos = 1
    case max = 2

    var label: String {
        switch self {
        case .order: return "order"
        case .chaos: return "chaos"
        case .max: return "max"
        }
    }
}

private enum Atlas2026GlobalPhase: String, Codable {
    case order
    case chaos
    case trans
    case max
    case noPhase = "no phase"
    case tba = "TBA"

    var siteCategory: Int {
        switch self {
        case .order: return 0
        case .chaos: return 1
        case .trans: return 2
        case .max: return 3
        case .noPhase, .tba: return 4
        }
    }
}

private struct Atlas2026PolygonMask {
    let width: Int
    let height: Int
    let values: [Float]
}

private struct Atlas2026SystemData {
    let params: [String: Any]
    let phaseMap: [String: String]
    let polygonData: [String: [String: Any]]
    let globalPhase: Atlas2026GlobalPhase
    let arraySize: Int
}

private struct Atlas2026PolygonEvaluation {
    let localPhases: [Atlas2026LocalPhase]
    let seeds: [Int]
    let sampleCount: Int

    var globalPhase: Atlas2026GlobalPhase {
        atlas2026Classify(phases: Set(localPhases.map(\.label)))
    }

    var jsonObject: [String: Any] {
        [
            "phase": localPhases.map(\.rawValue),
            "seed": seeds,
            "sample": Array(0..<sampleCount)
        ]
    }
}

private struct Atlas2026ConfigFiles {
    let kernel: URL
    let sweep: URL
    let initialization: URL
    let classifier: URL
}

private func atlas2026ConfigFiles(in directory: URL) -> Atlas2026ConfigFiles {
    Atlas2026ConfigFiles(
        kernel: directory.appendingPathComponent("kernel.json"),
        sweep: directory.appendingPathComponent("sweep.json"),
        initialization: directory.appendingPathComponent("init.json"),
        classifier: directory.appendingPathComponent("classifier.json")
    )
}

private func atlas2026ResolvePolygonLibraryURL(
    configDirectory: URL,
    libraryPath: String
) -> URL {
    if libraryPath.hasPrefix("/") {
        return URL(fileURLWithPath: libraryPath)
    }
    return configDirectory.appendingPathComponent(libraryPath)
}

public func loadAtlas2026ConfigBundle(configDirectory: URL) throws -> Atlas2026ConfigBundle {
    let files = atlas2026ConfigFiles(in: configDirectory)
    let decoder = JSONDecoder()
    let kernel = try decoder.decode(
        Atlas2026KernelConfig.self,
        from: Data(contentsOf: files.kernel)
    )
    let sweep = try decoder.decode(
        Atlas2026SweepConfig.self,
        from: Data(contentsOf: files.sweep)
    )
    let initialization = try decoder.decode(
        Atlas2026InitConfig.self,
        from: Data(contentsOf: files.initialization)
    )
    let classifier = try decoder.decode(
        Atlas2026ClassifierConfig.self,
        from: Data(contentsOf: files.classifier)
    )
    try validateAtlas2026Config(kernel: kernel, sweep: sweep, initialization: initialization, classifier: classifier)
    if let libraryPath = initialization.polygonLibraryJSONPath {
        let resolvedURL = atlas2026ResolvePolygonLibraryURL(
            configDirectory: configDirectory,
            libraryPath: libraryPath
        )
        guard FileManager.default.fileExists(atPath: resolvedURL.path) else {
            throw ConfigError.invalidConfig("atlas polygon library JSON does not exist at \(resolvedURL.path).")
        }
    }
    return Atlas2026ConfigBundle(
        configDirectory: configDirectory,
        kernel: kernel,
        sweep: sweep,
        initialization: initialization,
        classifier: classifier
    )
}

public final class Atlas2026Runner {
    private let configs: Atlas2026ConfigBundle
    private let logger: Logger
    private let encoder: JSONEncoder

    public init(configs: Atlas2026ConfigBundle, logger: Logger) {
        self.configs = configs
        self.logger = logger
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        self.encoder = encoder
    }

    public func writeResolvedConfigs(to outputDirectory: URL) throws {
        let files = atlas2026ConfigFiles(in: outputDirectory)
        try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
        try encoder.encode(configs.kernel).write(to: files.kernel)
        try encoder.encode(configs.sweep).write(to: files.sweep)
        try encoder.encode(configs.initialization).write(to: files.initialization)
        try encoder.encode(configs.classifier).write(to: files.classifier)
    }

    public func run(outputDirectory: URL) throws -> Atlas2026RunSummary {
        try writeResolvedConfigs(to: outputDirectory)

        let kernelKey = atlas2026KernelKey(
            kernel: configs.kernel,
            tMax: atlas2026LongTMax(arraySize: configs.kernel.arraySize, classifier: configs.classifier)
        )
        let dataRoot = outputDirectory.appendingPathComponent("data", isDirectory: true)
        let phasesRoot = dataRoot.appendingPathComponent("phases", isDirectory: true)
        let kernelsRoot = dataRoot.appendingPathComponent("kernels", isDirectory: true)
            .appendingPathComponent(kernelKey, isDirectory: true)
        try FileManager.default.createDirectory(at: phasesRoot, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: kernelsRoot, withIntermediateDirectories: true)

        let polygonPoolSize = max(configs.initialization.polygonLibrarySize, configs.sweep.samplesPerPolygon)
        let polygonLibrary = try atlas2026ResolvedPolygonLibrary(
            configs: configs,
            poolSize: polygonPoolSize
        )
        let simulator = try Atlas2026Simulator(kernel: configs.kernel)
        let muValues = atlas2026RangeValues(configs.sweep.mu)
        let sigmaValues = atlas2026RangeValues(configs.sweep.sigma)

        var phaseEntries: [[Double]] = []
        phaseEntries.reserveCapacity(muValues.count * sigmaValues.count)

        for mu in muValues {
            logger.info("Atlas 2026: mu=\(atlas2026NumberString(mu))")
            let muDirectory = kernelsRoot.appendingPathComponent("mu_\(atlas2026NumberString(mu))", isDirectory: true)
            try FileManager.default.createDirectory(at: muDirectory, withIntermediateDirectories: true)
            for sigma in sigmaValues {
                let systemData = try evaluateSystem(
                    mu: mu,
                    sigma: sigma,
                    simulator: simulator,
                    polygonLibrary: polygonLibrary
                )
                let systemURL = muDirectory.appendingPathComponent("sigma_\(atlas2026NumberString(sigma)).json")
                try atlas2026WriteJSONObject(systemData.asJSONObject(), to: systemURL)
                phaseEntries.append([Double(mu), Double(sigma), Double(systemData.globalPhase.siteCategory)])
            }
        }

        let phasesObject: [String: Any] = ["p": phaseEntries]
        try atlas2026WriteJSONObject(phasesObject, to: phasesRoot.appendingPathComponent("\(kernelKey).json"))

        let summary = Atlas2026RunSummary(
            systems: phaseEntries.count,
            polygonSizes: configs.sweep.polygonSizes,
            muCount: muValues.count,
            sigmaCount: sigmaValues.count,
            kernelKey: kernelKey
        )
        try encoder.encode(summary).write(to: outputDirectory.appendingPathComponent("summary.json"))
        return summary
    }

    private func evaluateSystem(
        mu: Float,
        sigma: Float,
        simulator: Atlas2026Simulator,
        polygonLibrary: [Int: [Atlas2026PolygonMask]]
    ) throws -> Atlas2026SystemData {
        let shortTMax = atlas2026ShortTMax(arraySize: configs.kernel.arraySize, classifier: configs.classifier)
        let longTMax = atlas2026LongTMax(arraySize: configs.kernel.arraySize, classifier: configs.classifier)
        var rng = SeededRandomNumberGenerator(seed: UInt64(max(0, configs.initialization.generatorSeed)))

        var polygonData: [String: [String: Any]] = [:]
        var perPolygon: [(Int, Atlas2026GlobalPhase)] = []
        perPolygon.reserveCapacity(configs.sweep.polygonSizes.count)

        for polygonSize in configs.sweep.polygonSizes {
            let evaluation = try atlas2026EvaluatePolygon(
                polygonSize: polygonSize,
                polygonLibrary: polygonLibrary,
                simulator: simulator,
                rng: &rng,
                sampleCount: configs.sweep.samplesPerPolygon,
                batchSize: configs.sweep.batchSize,
                mu: mu,
                sigma: sigma,
                shortTMax: shortTMax,
                longTMax: longTMax,
                std: configs.classifier.std,
                windowSize: configs.classifier.windowSize
            )
            perPolygon.append((polygonSize, evaluation.globalPhase))
            polygonData[String(polygonSize)] = evaluation.jsonObject
        }

        if configs.sweep.refineTransitions {
            let refined = try atlas2026RefinePolygonTransitions(
                base: perPolygon,
                mu: mu,
                sigma: sigma,
                simulator: simulator,
                polygonLibrary: polygonLibrary,
                seed: UInt64(max(0, configs.initialization.generatorSeed)) ^ UInt64(mu.bitPattern) ^ (UInt64(sigma.bitPattern) << 1),
                sampleCount: configs.sweep.samplesPerPolygon,
                batchSize: configs.sweep.batchSize,
                shortTMax: shortTMax,
                longTMax: longTMax,
                std: configs.classifier.std,
                windowSize: configs.classifier.windowSize
            )
            for (polygonSize, evaluation) in refined {
                polygonData[String(polygonSize)] = evaluation.jsonObject
                perPolygon.append((polygonSize, evaluation.globalPhase))
            }
        }

        let globalPhase = atlas2026OverallPhase(from: perPolygon)
        return Atlas2026SystemData(
            params: atlas2026SystemParams(kernel: configs.kernel, mu: mu, sigma: sigma),
            phaseMap: ["0": "order", "1": "chaos", "2": "max"],
            polygonData: polygonData,
            globalPhase: globalPhase,
            arraySize: configs.kernel.arraySize
        )
    }
}

private struct Atlas2026Simulator {
    let kernel: Atlas2026KernelConfig
    let kernelFFT: MLXArray

    init(kernel: Atlas2026KernelConfig) throws {
        self.kernel = kernel
        self.kernelFFT = try atlas2026KernelFFT(kernel)
    }

    func classifyBatch(
        masks: [Atlas2026PolygonMask],
        seeds: [Int],
        mu: Float,
        sigma: Float,
        tMax: Int,
        std: Float,
        windowSize: Int
    ) throws -> [Atlas2026LocalPhase] {
        let state = atlas2026InitialBatchState(arraySize: kernel.arraySize, masks: masks, seeds: seeds)
        var current = state
        var centerX = [Float](repeating: 0, count: tMax * masks.count)
        var centerY = [Float](repeating: 0, count: tMax * masks.count)
        var totalMass = [Float](repeating: 0, count: tMax * masks.count)
        let muArr = MLXArray(mu)
        let sigmaArr = MLXArray(sigma)

        for step in 0..<tMax {
            current = atlas2026Step(current, kernelFFT: kernelFFT, dt: kernel.dt, mu: muArr, sigma: sigmaArr)
            let stats = atlas2026MassCenterAndMass(current)
            let offset = step * masks.count
            for index in 0..<masks.count {
                centerX[offset + index] = stats.centerX[index]
                centerY[offset + index] = stats.centerY[index]
                totalMass[offset + index] = stats.totalMass[index]
            }
        }

        return atlas2026GetBatchPhases(
            count: masks.count,
            tMax: tMax,
            centerX: centerX,
            centerY: centerY,
            totalMass: totalMass,
            std: std,
            windowSize: windowSize
        )
    }
}

private func validateAtlas2026Config(
    kernel: Atlas2026KernelConfig,
    sweep: Atlas2026SweepConfig,
    initialization: Atlas2026InitConfig,
    classifier: Atlas2026ClassifierConfig
) throws {
    guard kernel.paper == "lenia-parameter-space-2026" else {
        throw ConfigError.invalidConfig("kernel.paper must be lenia-parameter-space-2026.")
    }
    guard kernel.arraySize > 0 else {
        throw ConfigError.invalidConfig("kernel.array_size must be > 0.")
    }
    guard kernel.dt > 0 else {
        throw ConfigError.invalidConfig("kernel.dt must be > 0.")
    }
    guard kernel.radius > 0 else {
        throw ConfigError.invalidConfig("kernel.radius must be > 0.")
    }
    guard !kernel.betas.isEmpty else {
        throw ConfigError.invalidConfig("kernel.betas must not be empty.")
    }
    switch kernel.function {
    case "gauss":
        guard let muK = kernel.muK, let sigmaK = kernel.sigmaK, muK.count == kernel.betas.count, sigmaK.count == kernel.betas.count else {
            throw ConfigError.invalidConfig("gauss kernels require mu_k and sigma_k arrays matching betas.")
        }
    case "exp", "quad4":
        break
    default:
        throw ConfigError.invalidConfig("kernel.function must be one of: gauss, exp, quad4.")
    }
    guard sweep.batchSize > 0, sweep.samplesPerPolygon > 0 else {
        throw ConfigError.invalidConfig("sweep.batch_size and sweep.samples_per_polygon must be > 0.")
    }
    guard !sweep.polygonSizes.isEmpty else {
        throw ConfigError.invalidConfig("sweep.polygon_sizes must not be empty.")
    }
    guard sweep.mu.step > 0, sweep.sigma.step > 0 else {
        throw ConfigError.invalidConfig("sweep step sizes must be > 0.")
    }
    guard sweep.mu.start < sweep.mu.stop, sweep.sigma.start < sweep.sigma.stop else {
        throw ConfigError.invalidConfig("sweep ranges must satisfy start < stop.")
    }
    guard initialization.polygonLibrarySize > 0 else {
        throw ConfigError.invalidConfig("init.polygon_library_size must be > 0.")
    }
    guard initialization.smallVoronoiPointRange.count == 2, initialization.largeVoronoiPointRange.count == 2 else {
        throw ConfigError.invalidConfig("Voronoi point ranges must have exactly two integers.")
    }
    guard classifier.windowSize > 0, classifier.std > 0, classifier.shortTMaxMultiplier > 0, classifier.longTMaxMultiplier >= classifier.shortTMaxMultiplier else {
        throw ConfigError.invalidConfig("classifier hyperparameters must be positive and long_tmax_multiplier >= short_tmax_multiplier.")
    }
}

private func atlas2026KernelFFT(_ config: Atlas2026KernelConfig) throws -> MLXArray {
    let size = 2 * config.radius + 1
    let values = atlas2026KernelValues(config: config, size: size)
    let normalization = max(atlas2026Sum(values), 1e-12)
    let normalized = values.map { row in row.map { $0 / normalization } }
    var padded = [Float](repeating: 0, count: config.arraySize * config.arraySize)
    let start = config.arraySize / 2 - size / 2
    for row in 0..<size {
        let dst = (start + row) * config.arraySize + start
        for col in 0..<size {
            padded[dst + col] = normalized[row][col]
        }
    }
    let paddedArray = MLXArray(padded).reshaped([config.arraySize, config.arraySize])
    let shifted = rollMultiAxis(paddedArray, shifts: [-config.arraySize / 2, -config.arraySize / 2], axes: [0, 1])
    return MLXFFT.fft2(shifted, axes: [0, 1])
}

private func atlas2026KernelValues(config: Atlas2026KernelConfig, size: Int) -> [[Float]] {
    let xyrange = (0..<size).map { index -> Float in
        if size == 1 { return 0 }
        return -1 + 2 * Float(index) / Float(size - 1)
    }
    let muK = config.muK ?? []
    let sigmaK = config.sigmaK ?? []
    var out = Array(repeating: Array(repeating: Float(0), count: size), count: size)
    for y in 0..<size {
        for x in 0..<size {
            let radius = sqrt(xyrange[x] * xyrange[x] + xyrange[y] * xyrange[y])
            out[y][x] = atlas2026KernelValue(
                function: config.function,
                radius: radius,
                betas: config.betas,
                muK: muK,
                sigmaK: sigmaK
            )
        }
    }
    return out
}

private func atlas2026KernelValue(
    function: String,
    radius: Float,
    betas: [Float],
    muK: [Float],
    sigmaK: [Float]
) -> Float {
    switch function {
    case "gauss":
        return zip(zip(betas, muK), sigmaK).reduce(0) { partial, tuple in
            let ((beta, muKValue), sigmaKValue) = tuple
            let z = (radius - muKValue) / sigmaKValue
            return partial + beta * exp(-(z * z) / 2)
        }
    case "exp":
        guard let band = atlas2026RadialBand(radius: radius, betas: betas),
              band.phase > 0,
              band.phase < 1 else {
            return 0
        }
        return band.beta * exp(4 - 1 / (band.phase * (1 - band.phase)))
    case "quad4":
        guard let band = atlas2026RadialBand(radius: radius, betas: betas) else {
            return 0
        }
        return band.beta * pow(4 * band.phase * (1 - band.phase), 4)
    default:
        fatalError("validated kernel function")
    }
}

private func atlas2026RadialBand(
    radius: Float,
    betas: [Float]
) -> (beta: Float, phase: Float)? {
    guard radius <= 1 else {
        return nil
    }
    guard betas.count > 1 else {
        return (betas[0], radius)
    }
    let scaled = Float(betas.count) * radius
    let bucket = min(Int(floor(scaled)), betas.count - 1)
    return (betas[bucket], scaled.truncatingRemainder(dividingBy: 1))
}

private func atlas2026Step(
    _ state: MLXArray,
    kernelFFT: MLXArray,
    dt: Float,
    mu: MLXArray,
    sigma: MLXArray
) -> MLXArray {
    let stateFFT = MLXFFT.fft2(state, axes: [1, 2])
    let convolved = MLXFFT.ifft2(stateFFT * kernelFFT.reshaped([1] + kernelFFT.shape), axes: [1, 2]).realPart()
    let diff = convolved - mu
    let growth = MLXArray(2.0) * MLX.exp(-((diff * diff) / (sigma * sigma)) / MLXArray(2.0)) - MLXArray(1.0)
    return MLX.clip(state + MLXArray(dt) * growth, min: MLXArray(0.0), max: MLXArray(1.0))
}

private func atlas2026MassCenterAndMass(_ state: MLXArray) -> (centerX: [Float], centerY: [Float], totalMass: [Float]) {
    let shape = state.shape
    let batch = shape[0]
    let width = shape[1]
    let height = shape[2]
    let flat = state.asArray(Float.self)
    var centerX = [Float](repeating: 0, count: batch)
    var centerY = [Float](repeating: 0, count: batch)
    var totalMass = [Float](repeating: 0, count: batch)
    let plane = width * height
    for batchIndex in 0..<batch {
        let offset = batchIndex * plane
        var mass: Float = 0
        var xWeighted: Float = 0
        var yWeighted: Float = 0
        for x in 0..<width {
            let rowOffset = offset + x * height
            for y in 0..<height {
                let value = flat[rowOffset + y]
                mass += value
                xWeighted += Float(x) * value
                yWeighted += Float(y) * value
            }
        }
        totalMass[batchIndex] = mass
        if mass != 0 {
            centerX[batchIndex] = xWeighted / mass
            centerY[batchIndex] = yWeighted / mass
        }
    }
    return (centerX, centerY, totalMass)
}

private func atlas2026GetBatchPhases(
    count: Int,
    tMax: Int,
    centerX: [Float],
    centerY: [Float],
    totalMass: [Float],
    std: Float,
    windowSize: Int
) -> [Atlas2026LocalPhase] {
    var phases = [Atlas2026LocalPhase](repeating: .max, count: count)
    let lastOffset = (tMax - 1) * count
    for batchIndex in 0..<count {
        let latestMass = totalMass[lastOffset + batchIndex]
        let latestX = centerX[lastOffset + batchIndex]
        let latestY = centerY[lastOffset + batchIndex]

        var sameMass = false
        var sameX = false
        var sameY = false
        for step in 0..<(tMax - 1) {
            let offset = step * count + batchIndex
            sameMass = sameMass || totalMass[offset] == latestMass
            sameX = sameX || centerX[offset] == latestX
            sameY = sameY || centerY[offset] == latestY
        }
        if sameMass && sameX && sameY {
            phases[batchIndex] = .order
            continue
        }

        let start = max(0, tMax - windowSize)
        var sumX: Float = 0
        var sumY: Float = 0
        let windowCount = max(tMax - start, 1)
        for step in start..<tMax {
            let offset = step * count + batchIndex
            sumX += centerX[offset]
            sumY += centerY[offset]
        }
        let meanX = sumX / Float(windowCount)
        let meanY = sumY / Float(windowCount)
        var stableX = true
        var stableY = true
        for step in start..<tMax {
            let offset = step * count + batchIndex
            stableX = stableX && abs(meanX - centerX[offset]) < std
            stableY = stableY && abs(meanY - centerY[offset]) < std
        }
        phases[batchIndex] = (stableX && stableY) ? .chaos : .max
    }
    return phases
}

private func atlas2026Classify(phases: Set<String>) -> Atlas2026GlobalPhase {
    if phases == ["order"] {
        return .order
    } else if phases == ["chaos"] {
        return .chaos
    } else if phases == ["order", "chaos", "max"] {
        return .max
    } else if phases == ["order", "max"] {
        return .max
    } else if phases == ["order", "chaos"] {
        return .trans
    } else if !phases.isEmpty {
        return .noPhase
    } else {
        return .tba
    }
}

private func atlas2026OverallPhase(from perPolygon: [(Int, Atlas2026GlobalPhase)]) -> Atlas2026GlobalPhase {
    let phases = Set(perPolygon.map { $0.1.rawValue })
    return atlas2026Classify(phases: phases)
}

private func atlas2026RefinePolygonTransitions(
    base: [(Int, Atlas2026GlobalPhase)],
    mu: Float,
    sigma: Float,
    simulator: Atlas2026Simulator,
    polygonLibrary: [Int: [Atlas2026PolygonMask]],
    seed: UInt64,
    sampleCount: Int,
    batchSize: Int,
    shortTMax: Int,
    longTMax: Int,
    std: Float,
    windowSize: Int
) throws -> [Int: Atlas2026PolygonEvaluation] {
    let phaseStrings = base.map(\.1.rawValue)
    guard !phaseStrings.contains("max") else { return [:] }

    let refinementRange: [Int]
    if phaseStrings.contains("trans") {
        guard let rMin = base.filter({ $0.1 == .trans }).map(\.0).min() else { return [:] }
        let rMax = min(rMin + 10, base.map(\.0).max() ?? rMin)
        refinementRange = Array(rMin..<rMax)
    } else if phaseStrings.contains("order") && phaseStrings.contains("chaos") {
        guard let rMin = base.filter({ $0.1 == .order }).map(\.0).max() else { return [:] }
        let rMax = min(rMin + 10, base.map(\.0).max() ?? rMin)
        refinementRange = Array(rMin..<rMax)
    } else {
        return [:]
    }

    var output: [Int: Atlas2026PolygonEvaluation] = [:]
    var rng = SeededRandomNumberGenerator(seed: seed)
    for polygonSize in refinementRange {
        guard polygonLibrary[polygonSize] != nil else { continue }
        let evaluation = try atlas2026EvaluatePolygon(
            polygonSize: polygonSize,
            polygonLibrary: polygonLibrary,
            simulator: simulator,
            rng: &rng,
            sampleCount: sampleCount,
            batchSize: batchSize,
            mu: mu,
            sigma: sigma,
            shortTMax: shortTMax,
            longTMax: longTMax,
            std: std,
            windowSize: windowSize
        )
        output[polygonSize] = evaluation
    }
    return output
}

private func atlas2026EvaluatePolygon(
    polygonSize: Int,
    polygonLibrary: [Int: [Atlas2026PolygonMask]],
    simulator: Atlas2026Simulator,
    rng: inout SeededRandomNumberGenerator,
    sampleCount: Int,
    batchSize: Int,
    mu: Float,
    sigma: Float,
    shortTMax: Int,
    longTMax: Int,
    std: Float,
    windowSize: Int
) throws -> Atlas2026PolygonEvaluation {
    guard let masks = polygonLibrary[polygonSize] else {
        throw NSError(
            domain: "Atlas2026",
            code: 2,
            userInfo: [NSLocalizedDescriptionKey: "Missing Voronoi masks for polygon size \(polygonSize)."]
        )
    }

    let chunkSize = max(batchSize, 1)
    let adjustedSampleCount = atlas2026AdjustedSampleCount(
        requested: sampleCount,
        batchSize: chunkSize
    )
    let sampledMasks = Array(masks.prefix(adjustedSampleCount))
    let seeds = (0..<sampledMasks.count).map { _ in Int.random(in: 0...Int(UInt32.max), using: &rng) }

    var localPhases = try atlas2026ClassifyInBatches(
        simulator: simulator,
        masks: sampledMasks,
        seeds: seeds,
        batchSize: chunkSize,
        mu: mu,
        sigma: sigma,
        tMax: shortTMax,
        std: std,
        windowSize: windowSize
    )
    if localPhases.contains(.max) {
        localPhases = try atlas2026ClassifyInBatches(
            simulator: simulator,
            masks: sampledMasks,
            seeds: seeds,
            batchSize: chunkSize,
            mu: mu,
            sigma: sigma,
            tMax: longTMax,
            std: std,
            windowSize: windowSize
        )
    }

    return Atlas2026PolygonEvaluation(
        localPhases: localPhases,
        seeds: seeds,
        sampleCount: sampledMasks.count
    )
}

private func atlas2026AdjustedSampleCount(requested: Int, batchSize: Int) -> Int {
    let effectiveBatch = max(batchSize, 1)
    if requested <= effectiveBatch {
        return effectiveBatch
    }
    if requested % effectiveBatch == 0 {
        return requested
    }
    return ((requested / effectiveBatch) + 1) * effectiveBatch
}

private func atlas2026ClassifyInBatches(
    simulator: Atlas2026Simulator,
    masks: [Atlas2026PolygonMask],
    seeds: [Int],
    batchSize: Int,
    mu: Float,
    sigma: Float,
    tMax: Int,
    std: Float,
    windowSize: Int
) throws -> [Atlas2026LocalPhase] {
    precondition(masks.count == seeds.count)
    let chunkSize = max(batchSize, 1)
    var phases: [Atlas2026LocalPhase] = []
    phases.reserveCapacity(masks.count)
    var start = 0
    while start < masks.count {
        let end = min(start + chunkSize, masks.count)
        phases += try simulator.classifyBatch(
            masks: Array(masks[start..<end]),
            seeds: Array(seeds[start..<end]),
            mu: mu,
            sigma: sigma,
            tMax: tMax,
            std: std,
            windowSize: windowSize
        )
        start = end
    }
    return phases
}

private func atlas2026GeneratePolygonLibrary(
    arraySize: Int,
    targetSizes: [Int],
    poolSize: Int,
    initialization: Atlas2026InitConfig
) throws -> [Int: [Atlas2026PolygonMask]] {
    var rng = SeededRandomNumberGenerator(seed: UInt64(max(initialization.generatorSeed, 0)))
    let sortedSizes = Array(Set(targetSizes)).sorted()
    var buckets: [Int: [Atlas2026PolygonMask]] = Dictionary(uniqueKeysWithValues: sortedSizes.map { ($0, []) })

    while buckets.values.contains(where: { $0.count < poolSize }) {
        for targetSize in sortedSizes {
            guard buckets[targetSize]!.count < poolSize else { continue }
            let largeCanvas = targetSize >= arraySize / 2
            let scale = largeCanvas ? 2 : 1
            let canvas = arraySize * scale
            let pointRange = largeCanvas ? initialization.largeVoronoiPointRange : initialization.smallVoronoiPointRange
            for pointCount in pointRange[0]..<pointRange[1] {
                guard buckets[targetSize]!.count < poolSize else { break }
                let seeds = (0..<pointCount).map { _ in
                    SIMD2<Float>(
                        Float.random(in: 0..<Float(canvas), using: &rng),
                        Float.random(in: 0..<Float(canvas), using: &rng)
                    )
                }
                let masks = atlas2026VoronoiMasks(canvasSize: canvas, seeds: seeds)
                for mask in masks {
                    guard max(mask.width, mask.height) < arraySize + 1 else { continue }
                    let area = Int(round(sqrt(Double(mask.values.reduce(0, +)))))
                    guard buckets[area] != nil, buckets[area]!.count < poolSize else { continue }
                    buckets[area]!.append(mask)
                }
            }
        }
    }

    return buckets
}

private func atlas2026ResolvedPolygonLibrary(
    configs: Atlas2026ConfigBundle,
    poolSize: Int
) throws -> [Int: [Atlas2026PolygonMask]] {
    if let libraryPath = configs.initialization.polygonLibraryJSONPath {
        return try atlas2026LoadPolygonLibrary(
            url: atlas2026ResolvePolygonLibraryURL(
                configDirectory: configs.configDirectory,
                libraryPath: libraryPath
            ),
            targetSizes: configs.sweep.polygonSizes,
            poolSize: poolSize
        )
    }
    return try atlas2026GeneratePolygonLibrary(
        arraySize: configs.kernel.arraySize,
        targetSizes: configs.sweep.polygonSizes,
        poolSize: poolSize,
        initialization: configs.initialization
    )
}

private func atlas2026LoadPolygonLibrary(
    url: URL,
    targetSizes: [Int],
    poolSize: Int
) throws -> [Int: [Atlas2026PolygonMask]] {
    let data = try Data(contentsOf: url)
    guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
        throw ConfigError.invalidConfig("atlas polygon library JSON must decode to a dictionary.")
    }
    var output: [Int: [Atlas2026PolygonMask]] = [:]
    for size in Set(targetSizes) {
        guard let rawMasks = object[String(size)] as? [[[Any]]] else {
            throw ConfigError.invalidConfig("atlas polygon library is missing polygon size \(size).")
        }
        let masks = try rawMasks.prefix(poolSize).map { rows -> Atlas2026PolygonMask in
            let width = rows.count
            let height = rows.first?.count ?? 0
            var values: [Float] = []
            values.reserveCapacity(width * height)
            for row in rows {
                for value in row {
                    guard let number = value as? NSNumber else {
                        throw ConfigError.invalidConfig("atlas polygon library masks must contain numeric cells.")
                    }
                    values.append(number.floatValue)
                }
            }
            return Atlas2026PolygonMask(width: width, height: height, values: values)
        }
        guard masks.count >= min(poolSize, rawMasks.count), !masks.isEmpty else {
            throw ConfigError.invalidConfig("atlas polygon library has no masks for polygon size \(size).")
        }
        output[size] = masks
    }
    return output
}

private func atlas2026VoronoiMasks(canvasSize: Int, seeds: [SIMD2<Float>]) -> [Atlas2026PolygonMask] {
    guard !seeds.isEmpty else { return [] }
    var labels = [Int](repeating: 0, count: canvasSize * canvasSize)
    for row in 0..<canvasSize {
        for col in 0..<canvasSize {
            let point = SIMD2<Float>(Float(row), Float(col))
            var best = 0
            var bestDistance = Float.greatestFiniteMagnitude
            for (index, seed) in seeds.enumerated() {
                let delta = point - seed
                let distance = simd_length_squared(delta)
                if distance < bestDistance {
                    bestDistance = distance
                    best = index
                }
            }
            labels[row * canvasSize + col] = best
        }
    }

    var masks: [Atlas2026PolygonMask] = []
    masks.reserveCapacity(seeds.count)
    for region in seeds.indices {
        var rowMin = canvasSize
        var rowMax = -1
        var colMin = canvasSize
        var colMax = -1
        for row in 0..<canvasSize {
            for col in 0..<canvasSize {
                if labels[row * canvasSize + col] == region {
                    rowMin = min(rowMin, row)
                    rowMax = max(rowMax, row)
                    colMin = min(colMin, col)
                    colMax = max(colMax, col)
                }
            }
        }
        guard rowMax >= rowMin, colMax >= colMin else {
            masks.append(Atlas2026PolygonMask(width: canvasSize, height: canvasSize, values: [Float](repeating: 0, count: canvasSize * canvasSize)))
            continue
        }
        let width = rowMax - rowMin + 1
        let height = colMax - colMin + 1
        var values = [Float](repeating: 0, count: width * height)
        for row in rowMin...rowMax {
            for col in colMin...colMax {
                if labels[row * canvasSize + col] == region {
                    values[(row - rowMin) * height + (col - colMin)] = 1
                }
            }
        }
        masks.append(Atlas2026PolygonMask(width: width, height: height, values: values))
    }
    return masks
}

private func atlas2026InitialBatchState(
    arraySize: Int,
    masks: [Atlas2026PolygonMask],
    seeds: [Int]
) -> MLXArray {
    var values = [Float](repeating: 0, count: masks.count * arraySize * arraySize)
    let plane = arraySize * arraySize
    for (index, mask) in masks.enumerated() {
        var localRng = SeededRandomNumberGenerator(seed: UInt64(bitPattern: Int64(seeds[index])))
        let rowStart = arraySize / 2 - mask.width / 2
        let colStart = arraySize / 2 - mask.height / 2
        for row in 0..<mask.width {
            for col in 0..<mask.height {
                let maskValue = mask.values[row * mask.height + col]
                guard maskValue > 0 else { continue }
                let value = Float.random(in: 0...1, using: &localRng) * maskValue
                let dst = index * plane + (rowStart + row) * arraySize + (colStart + col)
                values[dst] = value
            }
        }
    }
    return MLXArray(values).reshaped([masks.count, arraySize, arraySize])
}

private func atlas2026SystemParams(kernel: Atlas2026KernelConfig, mu: Float, sigma: Float) -> [String: Any] {
    var params: [String: Any] = [
        "k_size": 2 * kernel.radius + 1,
        "mu": mu,
        "sigma": sigma,
        "weights": 1.0
    ]
    if kernel.betas.count == 1 {
        params["beta"] = kernel.betas[0]
    } else {
        params["beta"] = kernel.betas
    }
    if let muK = kernel.muK {
        params["mu_k"] = muK.count == 1 ? muK[0] : muK
    }
    if let sigmaK = kernel.sigmaK {
        params["sigma_k"] = sigmaK.count == 1 ? sigmaK[0] : sigmaK
    }
    return params
}

private func atlas2026WriteJSONObject(_ object: [String: Any], to url: URL) throws {
    try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
    let data = try JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys])
    try data.write(to: url)
}

private func atlas2026KernelKey(kernel: Atlas2026KernelConfig, tMax: Int) -> String {
    let betas = kernel.betas.map(atlas2026NumberString).joined(separator: ",")
    switch kernel.function {
    case "gauss":
        let muK = (kernel.muK ?? []).map(atlas2026NumberString).joined(separator: ",")
        let sigmaK = (kernel.sigmaK ?? []).map(atlas2026NumberString).joined(separator: ",")
        return "gauss_\(muK)_\(sigmaK)_\(betas)_\(kernel.radius)_\(kernel.arraySize)_\(tMax)"
    case "exp":
        return "exp_\(betas)_\(kernel.radius)_\(kernel.arraySize)_\(tMax)"
    case "quad4":
        return "quad4_\(betas)_\(kernel.radius)_\(kernel.arraySize)_\(tMax)"
    default:
        fatalError("validated kernel function")
    }
}

private func atlas2026RangeValues(_ spec: Atlas2026SweepConfig.RangeSpec) -> [Float] {
    var values: [Float] = []
    var current = spec.start
    while current < spec.stop - spec.step * 0.25 {
        values.append(Float((Double(current) * 100_000).rounded() / 100_000))
        current += spec.step
    }
    return values
}

private func atlas2026ShortTMax(arraySize: Int, classifier: Atlas2026ClassifierConfig) -> Int {
    Int(round(Double(classifier.shortTMaxMultiplier) * log2(Double(arraySize))))
}

private func atlas2026LongTMax(arraySize: Int, classifier: Atlas2026ClassifierConfig) -> Int {
    Int(round(Double(classifier.longTMaxMultiplier) * log2(Double(arraySize))))
}

private func atlas2026NumberString(_ value: Float) -> String {
    if abs(value.rounded() - value) < 1e-6 {
        return String(format: "%.1f", Double(value))
    }
    var string = String(format: "%.5f", Double(value))
    while string.contains(".") && string.last == "0" {
        string.removeLast()
    }
    if string.last == "." {
        string.removeLast()
    }
    return string
}

private func atlas2026Sum(_ matrix: [[Float]]) -> Float {
    matrix.reduce(0) { partial, row in partial + row.reduce(0, +) }
}

private extension Atlas2026SystemData {
    func asJSONObject() -> [String: Any] {
        var root: [String: Any] = [
            "params": params,
            "phase_map": phaseMap
        ]
        root[String(arraySize)] = polygonData
        return root
    }
}
