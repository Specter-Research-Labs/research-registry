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

    func run() throws {
        guard checkpointSteps > 0, horizon >= 128, horizon % 32 == 0 else {
            throw ValidationError("checkpoint must be positive; horizon must be >=128 and divisible by 32")
        }
        guard ["original", "symmetry", "followup"].contains(study) else {
            throw ValidationError("study must be original, symmetry, or followup")
        }
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
            overrides["backend"] = "metal-full"
            let runtime = try loadRuntimeConfig(from: source, overrides: overrides)
            guard runtime.channels == 2, runtime.border == "wall",
                  runtime.environment == nil, runtime.walls?.enabled != true,
                  runtime.obstacleField?.enabled != true, runtime.interventions.isEmpty,
                  FlowLeniaInteractiveSimulator.supportsResidentMetal(runtime) else {
                throw ValidationError("pilot requires supported two-channel Metal runtime in a clean wall arena")
            }
            try JSONSerialization.data(withJSONObject: ["source": JSONSerialization.jsonObject(with: source),
                "overrides": overrides], options: [.sortedKeys]).write(to: directory.appendingPathComponent("runtime-inputs.json"))
            let harness = CapacityPilotHarness(config: runtime)
            let emit: (CapacityPilotBranch) throws -> Void = { branch in
                try JSONEncoder().encode(branch).write(to: directory.appendingPathComponent("\(branch.name).json"))
                print("\(id.prefix(8)) \(branch.name) completed", terminator: "\n")
                fflush(stdout)
            }
            switch study {
            case "symmetry": try harness.runSymmetry(checkpointSteps: checkpointSteps, output: directory)
            case "followup": try harness.runFollowup(checkpointSteps: checkpointSteps, horizon: horizon, output: directory, emit: emit)
            default: try harness.run(checkpointSteps: checkpointSteps, horizon: horizon, output: directory, emit: emit)
            }
        }
    }
}
