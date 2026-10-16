import ArgumentParser
import Foundation
import LeniaCore

struct CapacityPilotCommand: ParsableCommand {
    static let configuration = CommandConfiguration(commandName: "capacity-pilot",
        abstract: "Paired deformation and balanced-channel-write pilots with preserved checkpoints")
    @Option var config: String
    @Option var corpus: String
    @Option var output: String
    @Option var checkpointSteps: Int = 1200
    @Option var horizon: Int = 1024
    @Option var study: String = "original"
    @Option(help: "Comma-separated response checkpoint offsets; start with zero and increase in multiples of 32.")
    var responseOffsets: String = "0,128,256"
    @Option(help: "Duration of small-probe continuations in the response study.")
    var probeHorizon: Int = 128

    @Option var writeMode: String = "positive"
    @Option var writeDose: Double = 0.04
    @Option var releaseSteps: Int = 128
    @Option var challengeSign: Int = 1
    @Option var challengeAxis: String = "x"
    @Option var writeField: String?
    @Option(help: "Int32 founder label per cell in mass layout (x-major); -1 marks cells without matter. Development study, one corpus row.")
    var ancestryLabels: String?
    @Option(help: "Float32 founder mass [sx, sy, channels, founders] summing exactly to the initial field; replaces --ancestry-labels.")
    var ancestryFounderMass: String?
    @Option var ancestryFounders: Int?
    @Option(help: "Comma-separated steps at which founder mass [sx, sy, channels, founders] is exported.")
    var ancestryExportSteps: String?

    func run() throws {
        guard (checkpointSteps > 0 || (["state-continuation", "state-flow"].contains(study) && checkpointSteps == 0)), horizon >= 128, (study == "development" || horizon % 32 == 0) else {
            throw ValidationError("checkpoint must be positive; horizon must be >=128, and divisible by 32 except for development")
        }
        guard ["original", "symmetry", "followup", "development", "response", "write-response", "write-release", "state-response", "state-continuation", "state-flow", "transport"].contains(study) else {
            throw ValidationError("study must be original, symmetry, followup, development, response, write-response, write-release, state-response, state-continuation, state-flow, or transport")
        }
        let offsetParts = responseOffsets.split(separator: ",", omittingEmptySubsequences: false)
        let offsets = offsetParts.compactMap { Int($0) }
        guard offsets.count == offsetParts.count, offsets.first == 0,
              offsets == offsets.sorted(), Set(offsets).count == offsets.count,
              offsets.allSatisfy({ $0 >= 0 && $0 % 32 == 0 }),
              probeHorizon >= 128, probeHorizon % 32 == 0 else {
            throw ValidationError("response offsets must start at zero and increase in multiples of32; probe horizon must be >=128 and divisible by32")
        }
        guard ["sham", "positive", "negative", "scrambled", "field"].contains(writeMode),
              writeDose.isFinite, writeDose >= 0, writeDose < 1,
              releaseSteps >= 0, releaseSteps % 32 == 0, [-1, 1].contains(challengeSign), ["x", "y"].contains(challengeAxis),
              (writeMode == "field") == (writeField != nil),
              writeField == nil || ["write-response", "write-release", "state-response", "state-continuation", "state-flow"].contains(study) else {
            throw ValidationError("invalid write mode, dose, release interval, or challenge sign")
        }
        if study == "state-response" && (writeMode != "field" || releaseSteps != 0) {
            throw ValidationError("state-response requires a field and zero release steps")
        }
        if ["state-continuation", "state-flow"].contains(study) && (writeMode != "field" || checkpointSteps != 0) {
            throw ValidationError("state-continuation requires an explicit mass field and checkpoint-steps zero")
        }
        let source = try Data(contentsOf: URL(fileURLWithPath: config))
        let rows = try String(contentsOfFile: corpus, encoding: .utf8).split(separator: "\n").map {
            try JSONDecoder().decode(CorpusRow.self, from: Data($0.utf8))
        }
        guard ancestryLabels == nil || ancestryFounderMass == nil else {
            throw ValidationError("ancestry labels and founder mass are alternatives")
        }
        let ancestrySeed = ancestryLabels ?? ancestryFounderMass
        let ancestryOptions = [ancestrySeed != nil, ancestryFounders != nil, ancestryExportSteps != nil]
        guard ancestryOptions.allSatisfy({ $0 }) || ancestryOptions.allSatisfy({ !$0 }) else {
            throw ValidationError("ancestry labels or founder mass, founders, and export steps must be given together")
        }
        let exportParts = ancestryExportSteps?.split(separator: ",") ?? []
        let exportSteps = Set(exportParts.compactMap { Int($0) })
        if ancestrySeed != nil {
            guard study == "development", rows.count == 1, ancestryFounders! > 0,
                  exportSteps.count == exportParts.count, exportSteps.allSatisfy({ (0...horizon).contains($0) }) else {
                throw ValidationError("ancestry requires the development study, one corpus row, positive founders, and export steps within the horizon")
            }
        }
        let root = URL(fileURLWithPath: output)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        for row in rows {
            guard let id = row.specimenId else { throw ValidationError("missing specimen ID") }
            let directory = root.appendingPathComponent(id)
            guard !FileManager.default.fileExists(atPath: directory.path) else {
                throw ValidationError("output specimen already exists: \(id)")
            }
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            var overrides = row.params.explicitOverrides(seed: row.initSeed ?? 0)
            if let initial = row.initialCondition {
                overrides["init"] = try JSONSerialization.jsonObject(with: JSONEncoder().encode(initial))
            }
            let observationStudy = study == "development" || study == "response"
            if !observationStudy { overrides["backend"] = "metal-full" }
            let runtime = try loadRuntimeConfig(from: source, overrides: overrides)
            guard runtime.channels >= (observationStudy ? 1 : 2),
                  observationStudy || runtime.border == "wall",
                  runtime.environment == nil, runtime.walls?.enabled != true,
                  runtime.obstacleField?.enabled != true, runtime.interventions.isEmpty,
                  (observationStudy && runtime.backend == .mlx) || FlowLeniaInteractiveSimulator.supportsResidentMetal(runtime) else {
                throw ValidationError("pilot requires a supported clean runtime; channel-write studies require at least two channels and Metal wall boundaries")
            }
            try JSONSerialization.data(withJSONObject: ["source": JSONSerialization.jsonObject(with: source),
                "overrides": overrides], options: [.sortedKeys]).write(to: directory.appendingPathComponent("runtime-inputs.json"))
            if ["write-response", "write-release", "state-response", "state-continuation", "state-flow", "transport"].contains(study) && runtime.implementation.mode != "flowlenia_2022_paper_equations" {
                throw ValidationError("write-response requires explicit Flow Lenia paper-equations mode")
            }
            if ["state-continuation", "state-flow"].contains(study) && runtime.parameterEmbedding.enabled {
                throw ValidationError("mass-only restart requires fixed parameters without embedding")
            }
            let harness = CapacityPilotHarness(config: runtime)
            let emit: (CapacityPilotBranch) throws -> Void = { branch in
                try JSONEncoder().encode(branch).write(to: directory.appendingPathComponent("\(branch.name).json"))
                print("\(id.prefix(8)) \(branch.name) completed", terminator: "\n")
                fflush(stdout)
            }
            switch study {
            case "state-continuation", "state-flow":
                let bytes = try Data(contentsOf: URL(fileURLWithPath: writeField!))
                guard bytes.count == runtime.sx * runtime.sy * runtime.channels * MemoryLayout<Float>.size else {
                    throw ValidationError("state field must match runtime Float32 dimensions")
                }
                try bytes.write(to: directory.appendingPathComponent("state-input.f32"))
                let values = bytes.withUnsafeBytes { raw in
                    stride(from: 0, to: bytes.count, by: 4).map { raw.loadUnaligned(fromByteOffset: $0, as: Float.self) }
                }
                if study == "state-flow" {
                    try harness.runStateFlow(values: values, steps: horizon, output: directory)
                } else {
                    try harness.runStateContinuation(values: values, steps: horizon, output: directory, emit: emit)
                }
            case "transport": try harness.runTransport(checkpointSteps: checkpointSteps, releaseSteps: releaseSteps, horizon: horizon, output: directory)
            case "write-response", "write-release", "state-response": try harness.runWriteResponse(checkpointSteps: checkpointSteps, horizon: horizon,
                output: directory, mode: writeMode, dose: writeDose, releaseSteps: releaseSteps,
                challengeSign: challengeSign, challengeAxis: challengeAxis, replaceState: study == "state-response", releaseOnly: study == "write-release",
                writeField: try writeField.map { path in
                    let bytes = try Data(contentsOf: URL(fileURLWithPath: path))
                    guard bytes.count == runtime.sx * runtime.sy * runtime.channels * MemoryLayout<Float>.size else {
                        throw ValidationError("write field must match runtime Float32 dimensions")
                    }
                    try bytes.write(to: directory.appendingPathComponent("write-input.f32"))
                    return bytes.withUnsafeBytes { raw in
                        stride(from: 0, to: bytes.count, by: 4).map { raw.loadUnaligned(fromByteOffset: $0, as: Float.self) }
                    }
                }, emit: emit)
            case "development":
                let ancestry = try ancestrySeed.map { path in
                    let bytes = try Data(contentsOf: URL(fileURLWithPath: path))
                    guard runtime.backend == .metalFull else { throw ValidationError("ancestry requires metal-full") }
                    let seed: CapacityPilotAncestry.Seed
                    if ancestryLabels != nil {
                        guard bytes.count == runtime.sx * runtime.sy * MemoryLayout<Int32>.size else {
                            throw ValidationError("ancestry labels need one Int32 per cell")
                        }
                        try bytes.write(to: directory.appendingPathComponent("ancestry-labels.i32"))
                        seed = .labels(bytes.withUnsafeBytes { raw in
                            stride(from: 0, to: bytes.count, by: 4).map { raw.loadUnaligned(fromByteOffset: $0, as: Int32.self) }
                        })
                    } else {
                        guard bytes.count == runtime.sx * runtime.sy * runtime.channels * ancestryFounders! * MemoryLayout<Float>.size else {
                            throw ValidationError("ancestry founder mass needs [sx, sy, channels, founders] float32 values")
                        }
                        try bytes.write(to: directory.appendingPathComponent("ancestry-founder-mass.f32"))
                        seed = .founderMass(bytes.withUnsafeBytes { raw in
                            stride(from: 0, to: bytes.count, by: 4).map { raw.loadUnaligned(fromByteOffset: $0, as: Float.self) }
                        })
                    }
                    return CapacityPilotAncestry(seed: seed, founderCount: ancestryFounders!, exportSteps: exportSteps)
                }
                try harness.runDevelopment(horizon: horizon, output: directory, ancestry: ancestry, emit: emit)
            case "response": try harness.runResponse(checkpointSteps: checkpointSteps, horizon: horizon, output: directory, offsets: offsets, probeHorizon: probeHorizon, emit: emit)
            case "symmetry": try harness.runSymmetry(checkpointSteps: checkpointSteps, output: directory)
            case "followup": try harness.runFollowup(checkpointSteps: checkpointSteps, horizon: horizon, output: directory, emit: emit)
            default: try harness.run(checkpointSteps: checkpointSteps, horizon: horizon, output: directory, emit: emit)
            }
        }
    }
}
