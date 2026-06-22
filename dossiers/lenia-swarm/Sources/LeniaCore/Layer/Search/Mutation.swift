import Foundation

public struct MutationConfig {
    public let paramJitterStd: Float
    public let paramJitterSeed: Int?
    public let clip: Bool
    public let patchScale: Float
    public let patchShift: (Int, Int)
    public let mirrorX: Bool
    public let mirrorY: Bool

    public init(
        paramJitterStd: Float,
        paramJitterSeed: Int?,
        clip: Bool,
        patchScale: Float,
        patchShift: (Int, Int),
        mirrorX: Bool,
        mirrorY: Bool
    ) {
        self.paramJitterStd = paramJitterStd
        self.paramJitterSeed = paramJitterSeed
        self.clip = clip
        self.patchScale = patchScale
        self.patchShift = patchShift
        self.mirrorX = mirrorX
        self.mirrorY = mirrorY
    }
}

public func loadParamsFromFile(path: String, rank: Int) throws -> [String: Any] {
    let url = URL(fileURLWithPath: path)
    let content = try String(contentsOf: url, encoding: .utf8)

    if let data = content.data(using: .utf8),
       let json = try? JSONSerialization.jsonObject(with: data) {

        if let dict = json as? [String: Any] {
            return try extractParams(from: dict)
        }

        if let array = json as? [[String: Any]] {
            let ranked = rankEntries(array)
            guard rank >= 0 && rank < ranked.count else {
                throw MutationError.rankOutOfRange(rank, ranked.count)
            }
            return try extractParams(from: ranked[rank])
        }
    }

    let lines = content.split(separator: "\n").map { String($0).trimmingCharacters(in: .whitespaces) }
    var entries: [[String: Any]] = []

    for line in lines {
        guard !line.isEmpty else { continue }
        if let data = line.data(using: .utf8),
           let entry = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            entries.append(entry)
        }
    }

    guard !entries.isEmpty else {
        throw MutationError.emptyParamsFile
    }

    let ranked = rankEntries(entries)
    guard rank >= 0 && rank < ranked.count else {
        throw MutationError.rankOutOfRange(rank, ranked.count)
    }

    return try extractParams(from: ranked[rank])
}

private func rankEntries(_ entries: [[String: Any]]) -> [[String: Any]] {
    if entries.allSatisfy({ $0["score"] != nil }) {
        return entries.sorted { e1, e2 in
            let s1 = (e1["score"] as? NSNumber)?.floatValue ?? 0
            let s2 = (e2["score"] as? NSNumber)?.floatValue ?? 0
            return s1 > s2
        }
    }
    return entries
}

private func extractParams(from entry: [String: Any]) throws -> [String: Any] {
    if let params = entry["params"] as? [String: Any] {
        return try validateParamsDict(params)
    }

    return try validateParamsDict(entry)
}

private func validateParamsDict(_ params: [String: Any]) throws -> [String: Any] {
    let required: Set<String> = ["r", "b", "w", "a", "m", "s", "h", "R"]
    let keys = Set(params.keys)
    guard required.isSubset(of: keys) else {
        throw MutationError.missingRequiredKeys(required.subtracting(keys))
    }
    return params
}

public func validateParams(_ params: [String: Any], nbK: Int) throws -> [String: [Float]] {
    func asArray(_ key: String, _ shape: [Int]) throws -> [Float] {
        guard let value = params[key] else {
            throw MutationError.missingKey(key)
        }

        var flat: [Float] = []

        if let arr = value as? [Any] {
            flat = try flattenToFloat(arr)
        } else if let num = value as? NSNumber {
            flat = [num.floatValue]
        } else {
            throw MutationError.invalidParamType(key)
        }

        let expectedSize = shape.reduce(1, *)
        guard flat.count == expectedSize else {
            throw MutationError.wrongShape(key, expected: shape, got: flat.count)
        }

        return flat
    }

    return [
        "r": try asArray("r", [nbK]),
        "b": try asArray("b", [nbK, 3]),
        "w": try asArray("w", [nbK, 3]),
        "a": try asArray("a", [nbK, 3]),
        "m": try asArray("m", [nbK]),
        "s": try asArray("s", [nbK]),
        "h": try asArray("h", [nbK]),
        "R": try asArray("R", [1])
    ]
}

private func flattenToFloat(_ arr: [Any]) throws -> [Float] {
    var result: [Float] = []
    for item in arr {
        if let num = item as? NSNumber {
            result.append(num.floatValue)
        } else if let subArr = item as? [Any] {
            result.append(contentsOf: try flattenToFloat(subArr))
        } else {
            throw MutationError.invalidArrayElement
        }
    }
    return result
}

public func applyJitter(
    params: [String: [Float]],
    std: Float,
    seed: Int?
) -> [String: [Float]] {
    guard std > 0 else { return params }

    var rng: SeededRandomNumberGenerator
    if let seed = seed {
        rng = SeededRandomNumberGenerator(seed: UInt64(seed))
    } else {
        rng = SeededRandomNumberGenerator(seed: UInt64.random(in: 0...UInt64.max))
    }

    var jittered: [String: [Float]] = [:]

    for (key, values) in params {
        var newValues: [Float] = []
        for val in values {
            newValues.append(val + gaussianSample(std: std, rng: &rng))
        }
        jittered[key] = newValues
    }

    return jittered
}

public func clipParams(
    params: inout [String: [Float]],
    ranges: [String: (Float, Float)]
) {
    for (key, values) in params {
        guard let (lo, hi) = ranges[key] else { continue }
        params[key] = values.map { max(lo, min(hi, $0)) }
    }
}

public struct PatchTransform {
    public let center: [Int]
    public let size: Int

    public init(center: [Int], size: Int) {
        self.center = center
        self.size = size
    }
}

public func transformPatches(
    patches: [[String: Any]],
    sx: Int,
    sy: Int,
    scale: Float,
    shift: (Int, Int),
    mirrorX: Bool,
    mirrorY: Bool
) throws -> [[String: Any]] {
    var result: [[String: Any]] = []

    for patch in patches {
        guard let center = patch["center"] as? [Int],
              let size = patch["size"] as? Int,
              center.count == 2 else {
            throw MutationError.invalidPatch
        }

        var cx = center[0]
        var cy = center[1]
        var newSize = Int(round(Float(size) * scale))
        newSize = max(1, newSize)

        if mirrorX {
            cx = (sx - 1) - cx
        }
        if mirrorY {
            cy = (sy - 1) - cy
        }

        cx += shift.0
        cy += shift.1

        let half = newSize / 2
        let x0 = cx - half
        let x1 = cx + (newSize - half)
        let y0 = cy - half
        let y1 = cy + (newSize - half)

        if x0 < 0 || y0 < 0 || x1 > sx || y1 > sy {
            throw MutationError.patchOutOfBounds
        }

        result.append([
            "center": [cx, cy],
            "size": newSize
        ])
    }

    return result
}

public func paramsToNestedDict(_ params: [String: [Float]], nbK: Int) -> [String: Any] {
    func reshape2D(_ flat: [Float], rows: Int, cols: Int) -> [[Float]] {
        (0..<rows).map { r in
            Array(flat[r * cols..<(r + 1) * cols])
        }
    }

    return [
        "mode": "explicit",
        "r": params["r"]!,
        "b": reshape2D(params["b"]!, rows: nbK, cols: 3),
        "w": reshape2D(params["w"]!, rows: nbK, cols: 3),
        "a": reshape2D(params["a"]!, rows: nbK, cols: 3),
        "m": params["m"]!,
        "s": params["s"]!,
        "h": params["h"]!,
        "R": params["R"]![0]
    ]
}

public func extractRangesFromBaseConfig(_ config: [String: Any]) throws -> [String: (Float, Float)] {
    guard let paramsConfig = config["params"] as? [String: Any],
          let mode = paramsConfig["mode"] as? String,
          mode == "random",
          let ranges = paramsConfig["ranges"] as? [String: [Any]] else {
        throw MutationError.invalidRangesConfig
    }

    var result: [String: (Float, Float)] = [:]

    for key in ["r", "b", "w", "a", "m", "s", "h", "R"] {
        guard let range = ranges[key],
              range.count == 2,
              let lo = (range[0] as? NSNumber)?.floatValue,
              let hi = (range[1] as? NSNumber)?.floatValue else {
            throw MutationError.invalidRange(key)
        }
        result[key] = (lo, hi)
    }

    return result
}

public func mutateConfig(
    baseConfigPath: String,
    paramsPath: String,
    rank: Int,
    outputDir: String,
    config: MutationConfig
) throws {
    let baseConfigURL = URL(fileURLWithPath: baseConfigPath)
    let baseConfigData = try Data(contentsOf: baseConfigURL)
    guard var baseConfig = try JSONSerialization.jsonObject(with: baseConfigData) as? [String: Any] else {
        throw MutationError.invalidBaseConfig
    }

    guard let grid = baseConfig["grid"] as? [String: Int],
          let sx = grid["sx"],
          let sy = grid["sy"] else {
        throw MutationError.invalidGridConfig
    }

    guard let connectivity = baseConfig["connectivity"] as? [[Int]] else {
        throw MutationError.invalidConnectivity
    }
    let nbK = connectivity.flatMap { $0 }.reduce(0, +)

    let paramsRaw = try loadParamsFromFile(path: paramsPath, rank: rank)
    var params = try validateParams(paramsRaw, nbK: nbK)

    params = applyJitter(params: params, std: config.paramJitterStd, seed: config.paramJitterSeed)

    if config.clip {
        let ranges = try extractRangesFromBaseConfig(baseConfig)
        clipParams(params: &params, ranges: ranges)
    }

    guard let initConfig = baseConfig["init"] as? [String: Any],
          let patches = initConfig["patches"] as? [[String: Any]] else {
        throw MutationError.invalidInitConfig
    }

    let newPatches = try transformPatches(
        patches: patches,
        sx: sx,
        sy: sy,
        scale: config.patchScale,
        shift: config.patchShift,
        mirrorX: config.mirrorX,
        mirrorY: config.mirrorY
    )

    let mutationRecord: [String: Any] = [
        "base_config": baseConfigPath,
        "params_source": paramsPath,
        "params_rank": rank,
        "param_jitter_std": config.paramJitterStd,
        "param_jitter_seed": config.paramJitterSeed as Any,
        "clip": config.clip,
        "patch_scale": config.patchScale,
        "patch_shift": [config.patchShift.0, config.patchShift.1],
        "mirror_x": config.mirrorX,
        "mirror_y": config.mirrorY
    ]

    let outputURL = URL(fileURLWithPath: outputDir)
    try FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)

    baseConfig["params"] = paramsToNestedDict(params, nbK: nbK)

    var initConfigMut = initConfig
    initConfigMut["patches"] = newPatches
    baseConfig["init"] = initConfigMut

    let runDir = outputURL.appendingPathComponent("run").path
    if var logging = baseConfig["logging"] as? [String: Any] {
        logging["output_dir"] = runDir
        baseConfig["logging"] = logging
    }
    if var render = baseConfig["render"] as? [String: Any] {
        render["frames_dir"] = runDir + "/frames"
        render["output_mp4"] = runDir + "/video.mp4"
        render["enabled"] = true
        baseConfig["render"] = render
    }

    let configData = try JSONSerialization.data(withJSONObject: baseConfig, options: .prettyPrinted)
    try configData.write(to: outputURL.appendingPathComponent("config.json"))

    let mutationData = try JSONSerialization.data(withJSONObject: mutationRecord, options: .prettyPrinted)
    try mutationData.write(to: outputURL.appendingPathComponent("mutation.json"))

    let flatParams: [String: Any] = [
        "r": params["r"]!,
        "b": params["b"]!.chunked(into: 3),
        "w": params["w"]!.chunked(into: 3),
        "a": params["a"]!.chunked(into: 3),
        "m": params["m"]!,
        "s": params["s"]!,
        "h": params["h"]!,
        "R": params["R"]![0]
    ]
    let paramsData = try JSONSerialization.data(withJSONObject: flatParams, options: .prettyPrinted)
    try paramsData.write(to: outputURL.appendingPathComponent("params.json"))
}

public extension Array {
    func chunked(into size: Int) -> [[Element]] {
        stride(from: 0, to: count, by: size).map {
            Array(self[$0..<Swift.min($0 + size, count)])
        }
    }
}

public enum MutationError: Error, LocalizedError {
    case emptyParamsFile
    case rankOutOfRange(Int, Int)
    case missingRequiredKeys(Set<String>)
    case missingKey(String)
    case invalidParamType(String)
    case wrongShape(String, expected: [Int], got: Int)
    case invalidArrayElement
    case invalidBaseConfig
    case invalidPatch
    case patchOutOfBounds
    case invalidRangesConfig
    case invalidRange(String)
    case invalidGridConfig
    case invalidConnectivity
    case invalidInitConfig

    public var errorDescription: String? {
        switch self {
        case .emptyParamsFile:
            return "Params file is empty"
        case .rankOutOfRange(let rank, let count):
            return "Rank \(rank) out of range (0..<\(count))"
        case .missingRequiredKeys(let keys):
            return "Missing required keys: \(keys)"
        case .missingKey(let key):
            return "Missing key: \(key)"
        case .invalidParamType(let key):
            return "Invalid type for param: \(key)"
        case .wrongShape(let key, let expected, let got):
            return "Wrong shape for \(key): expected \(expected), got \(got) elements"
        case .invalidArrayElement:
            return "Invalid array element type"
        case .invalidBaseConfig:
            return "Invalid base config format"
        case .invalidPatch:
            return "Invalid patch configuration"
        case .patchOutOfBounds:
            return "Mutated patch is out of bounds"
        case .invalidRangesConfig:
            return "Invalid ranges configuration"
        case .invalidRange(let key):
            return "Invalid range for: \(key)"
        case .invalidGridConfig:
            return "Invalid grid configuration"
        case .invalidConnectivity:
            return "Invalid connectivity configuration"
        case .invalidInitConfig:
            return "Invalid init configuration"
        }
    }
}
