import ArgumentParser
import Foundation
import LeniaCore
import MLX

private struct ResolvedParamsArtifact: Codable {
    let seed: Int
    let params: KernelParams
}

private struct ReferenceManifestArtifact: Codable {
    let manifestVersion: Int
    let kind: String
    let parameterSeed: Int
    let initialSeeds: [Int]
    let initSeedOffset: Int
    let batchSize: Int
    let files: [String]

    enum CodingKeys: String, CodingKey {
        case manifestVersion = "manifest_version"
        case kind
        case parameterSeed = "parameter_seed"
        case initialSeeds = "initial_seeds"
        case initSeedOffset = "init_seed_offset"
        case batchSize = "batch_size"
        case files
    }
}

struct ExportReferenceCommand: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "export-reference",
        abstract: "Export initial state, compiled kernels, and one-step output as .npy files for cross-backend validation"
    )

    @Option(name: .long, help: "Path to base config.json")
    var config: String

    @Option(name: .shortAndLong, help: "Output directory for .npy files")
    var output: String

    @Option(name: .long, help: "Random seed for initial state and kernel params")
    var seed: Int = 0

    @Option(name: .long, help: "Comma-separated initial-state seeds for a reference batch; defaults to --seed")
    var seedList: String?

    @Option(name: .long, help: "Offset added to each initial-state seed")
    var initSeedOffset: Int = 0

    func run() async throws {
        let initialSeeds = try parseReferenceSeedList(seedList) ?? [seed]
        let configURL = URL(fileURLWithPath: config)
        let configData = try Data(contentsOf: configURL)
        let runtimeConfig = try loadRuntimeConfig(from: configData, overrides: ["params.seed": seed])
        let batchedConfig = batchedConfigFromRuntime(runtimeConfig)

        let kernels = compileKernels(
            params: runtimeConfig.params,
            config: batchedConfig,
            c0: runtimeConfig.c0,
            c1: runtimeConfig.c1
        )

        let mass = makeExportInitialStateBatch(
            runtimeConfig: runtimeConfig,
            seeds: initialSeeds,
            initSeedOffset: initSeedOffset
        )

        let outputURL = URL(
            fileURLWithPath: try resolvePath(output, dossier: dossierName),
            isDirectory: true
        )
        try FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)

        print("Config: \(batchedConfig.sx)x\(batchedConfig.sy), \(batchedConfig.channels)ch, \(batchedConfig.nbK)k")
        print("Parameter seed: \(seed)")
        print("Initial seeds: \(initialSeeds.map(String.init).joined(separator: ","))")
        print("Output: \(outputURL.path)")

        try save(array: mass, url: outputURL.appendingPathComponent("mass_in.npy"))

        let engine = FlowLeniaBatched(config: batchedConfig, kernels: kernels)
        let nextMass = engine.step(mass)
        MLX.eval(nextMass)
        try save(array: nextMass, url: outputURL.appendingPathComponent("mass_out.npy"))

        try save(array: kernels.fK.realPart(), url: outputURL.appendingPathComponent("kernel_fK_re.npy"))
        try save(array: kernels.fK.imaginaryPart(), url: outputURL.appendingPathComponent("kernel_fK_im.npy"))
        try save(array: kernels.m, url: outputURL.appendingPathComponent("kernel_m.npy"))
        try save(array: kernels.s, url: outputURL.appendingPathComponent("kernel_s.npy"))
        try save(array: kernels.h, url: outputURL.appendingPathComponent("kernel_h.npy"))
        try save(array: kernels.c0Idxs, url: outputURL.appendingPathComponent("kernel_c0.npy"))
        try save(array: kernels.c1Mask, url: outputURL.appendingPathComponent("kernel_c1_mask.npy"))

        let paramsArtifact = ResolvedParamsArtifact(seed: runtimeConfig.params.seed, params: runtimeConfig.params.toKernelParams())
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let paramsData = try encoder.encode(paramsArtifact)
        try paramsData.write(to: outputURL.appendingPathComponent("resolved_params.json"))

        var files = try FileManager.default.contentsOfDirectory(atPath: outputURL.path)
            .filter { $0.hasSuffix(".npy") || $0.hasSuffix(".json") }
            .sorted()
        let referenceManifest = ReferenceManifestArtifact(
            manifestVersion: 1,
            kind: "lenia_swift_reference_bundle",
            parameterSeed: runtimeConfig.params.seed,
            initialSeeds: initialSeeds,
            initSeedOffset: initSeedOffset,
            batchSize: initialSeeds.count,
            files: files
        )
        try encoder.encode(referenceManifest)
            .write(to: outputURL.appendingPathComponent("reference_manifest.json"))
        files = try FileManager.default.contentsOfDirectory(atPath: outputURL.path)
            .filter { $0.hasSuffix(".npy") || $0.hasSuffix(".json") }
            .sorted()
        print("Exported \(files.count) reference files:")
        for f in files {
            print("  \(f)")
        }
    }
}

private func parseReferenceSeedList(_ value: String?) throws -> [Int]? {
    guard let value else { return nil }
    let seeds = try value
        .split(separator: ",")
        .map { token -> Int in
            guard let seed = Int(token.trimmingCharacters(in: .whitespacesAndNewlines)) else {
                throw ValidationError("--seed-list must contain comma-separated integers.")
            }
            return seed
        }
    guard !seeds.isEmpty else {
        throw ValidationError("--seed-list must contain at least one seed.")
    }
    return seeds
}

private func makeExportInitialStateBatch(
    runtimeConfig: LeniaRuntimeConfig,
    seeds: [Int],
    initSeedOffset: Int
) -> MLXArray {
    precondition(!seeds.isEmpty, "reference export requires at least one seed")
    let sx = runtimeConfig.sx
    let sy = runtimeConfig.sy
    let channels = runtimeConfig.channels
    let state = MLX.zeros([seeds.count, sx, sy, channels])

    if let statePatch = runtimeConfig.statePatch {
        let values = statePatch.decodedValues()
        let patchArr = MLXArray(values).reshaped([1, statePatch.width, statePatch.height, channels])
        let cx = statePatch.center[0]
        let cy = statePatch.center[1]
        let halfW = statePatch.width / 2
        let halfH = statePatch.height / 2
        let x0 = cx - halfW
        let y0 = cy - halfH
        for batchIndex in seeds.indices {
            state[batchIndex..<(batchIndex + 1), x0..<(x0 + statePatch.width), y0..<(y0 + statePatch.height), 0...] = patchArr
        }
        return state
    }

    let lo = runtimeConfig.aUniform.low
    let hi = runtimeConfig.aUniform.high

    for (batchIndex, seed) in seeds.enumerated() {
        var rng = SeededRandomNumberGenerator(seed: UInt64(seed + initSeedOffset))
        for patch in runtimeConfig.patches {
            let cx = patch.center[0]
            let cy = patch.center[1]
            let half = patch.size / 2
            let x0 = max(0, cx - half)
            let x1 = min(sx, cx + half)
            let y0 = max(0, cy - half)
            let y1 = min(sy, cy + half)
            let w = x1 - x0
            let h = y1 - y0
            var values: [Float] = []
            values.reserveCapacity(w * h * channels)
            for _ in 0..<(w * h * channels) {
                values.append(Float.random(in: lo...hi, using: &rng))
            }
            let patchArr = MLXArray(values).reshaped([1, w, h, channels])
            state[batchIndex..<(batchIndex + 1), x0..<x1, y0..<y1, 0...] = patchArr
        }
    }
    return state
}
