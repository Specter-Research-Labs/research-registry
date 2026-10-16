import ArgumentParser
import CryptoKit
import Foundation
import LeniaCore

private struct PhantomFile: Decodable {
    let source: String
    let pressure: Bool
    let field: String
    let field_sha256: String
}

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
    @Option(help: "Phantom spec JSON: source static|replay, pressure true|false, field path (relative to the spec), field_sha256.")
    var phantom: String?
    @Flag(name: .long, help: "In the state-flow study, also save the pre-step growth potential at each sampled step.")
    var savePotential = false

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
        if phantom != nil && !["development", "state-flow"].contains(study) {
            throw ValidationError("phantom fields are supported only in the development and state-flow studies")
        }
        if savePotential && study != "state-flow" {
            throw ValidationError("save-potential is supported only in the state-flow study")
        }
        let phantomSpec = try phantom.map { try loadPhantom($0) }
        let source = try Data(contentsOf: URL(fileURLWithPath: config))
        let rows = try String(contentsOfFile: corpus, encoding: .utf8).split(separator: "\n").map {
            try JSONDecoder().decode(CorpusRow.self, from: Data($0.utf8))
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
            if let phantomSpec {
                guard runtime.backend == .metalFull,
                      phantomSpec.spec.field.count == runtime.sx * runtime.sy * runtime.channels else {
                    throw ValidationError("phantom fields require metal-full and a field matching runtime Float32 dimensions")
                }
                try phantomSpec.json.write(to: directory.appendingPathComponent("phantom-spec.json"))
            }
            let harness = CapacityPilotHarness(config: runtime, phantom: phantomSpec?.spec)
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
                    try harness.runStateFlow(values: values, steps: horizon, output: directory, savePotential: savePotential)
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
            case "development": try harness.runDevelopment(horizon: horizon, output: directory, emit: emit)
            case "response": try harness.runResponse(checkpointSteps: checkpointSteps, horizon: horizon, output: directory, offsets: offsets, probeHorizon: probeHorizon, emit: emit)
            case "symmetry": try harness.runSymmetry(checkpointSteps: checkpointSteps, output: directory)
            case "followup": try harness.runFollowup(checkpointSteps: checkpointSteps, horizon: horizon, output: directory, emit: emit)
            default: try harness.run(checkpointSteps: checkpointSteps, horizon: horizon, output: directory, emit: emit)
            }
        }
    }

    private func loadPhantom(_ path: String) throws -> (spec: FlowLeniaPhantomSpec, json: Data) {
        let url = URL(fileURLWithPath: path)
        let json = try Data(contentsOf: url)
        let file = try JSONDecoder().decode(PhantomFile.self, from: json)
        guard let source = FlowLeniaPhantomSpec.Source(rawValue: file.source) else {
            throw ValidationError("phantom source must be static or replay")
        }
        let bytes = try Data(contentsOf: URL(fileURLWithPath: file.field, relativeTo: url.deletingLastPathComponent()))
        let digest = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
        guard digest == file.field_sha256 else {
            throw ValidationError("phantom field sha256 \(digest) does not match \(file.field_sha256)")
        }
        let values = bytes.withUnsafeBytes { raw in
            stride(from: 0, to: bytes.count, by: 4).map { raw.loadUnaligned(fromByteOffset: $0, as: Float.self) }
        }
        return (FlowLeniaPhantomSpec(source: source, pressure: file.pressure, field: values), json)
    }
}
