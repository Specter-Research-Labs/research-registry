import ArgumentParser
import Foundation
import LeniaCore

struct CapacityPilotCommand: ParsableCommand {
    static let configuration = CommandConfiguration(commandName: "capacity-pilot",
        abstract: "Run a capacity-pilot study ensemble declared in one design file (docs/contracts/CapacityPilotDesign.md)")
    @Option(help: "Design JSON naming the runtime, bodies, study, ensemble and outcomes.")
    var design: String
    @Option(help: "Run directory to create; it must not exist.")
    var output: String

    func run() throws {
        let plan = try CapacityPilotDesign.load(URL(fileURLWithPath: design))
        let root = URL(fileURLWithPath: output)
        guard !FileManager.default.fileExists(atPath: root.path) else {
            throw ValidationError("output already exists: \(output)")
        }
        let receipt = try beginRunReceipt(
            directory: root,
            executableURL: try LeniaBuildInfo.runningExecutableURL(),
            backend: plan.backend,
            config: ResolvedRunConfig(parts: [("design", plan.data)]),
            seeds: plan.bodies.map(\.initSeed),
            inputs: plan.inputs
        )
        try plan.data.write(to: root.appendingPathComponent("design.json"))
        func harness(for body: CapacityPilotDesign.Body, member: Int, sink: CapacityPilotSink) -> CapacityPilotHarness {
            CapacityPilotHarness(config: body.runtime, phantom: plan.phantom, sink: sink,
                                 perturbation: CapacityPilotPerturbation(seed: plan.perturbationSeed, member: member,
                                                                         cells: plan.perturbedCells))
        }
        let measured = Set(plan.continuous.flatMap(\.branches))
        var bodies: [CapacityPilotBodyMembers] = []
        var compared = 0
        var matched = 0
        var mismatches: [String] = []
        for body in plan.bodies {
            var members: [[String: [CapacityPilotFrame]]] = []
            var hashes: [[String: String]] = []
            for member in 0..<plan.members {
                let directory = root.appendingPathComponent(body.id).appendingPathComponent("member-\(member)")
                try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
                let run = harness(for: body, member: member, sink: .directory(directory))
                var frames: [String: [CapacityPilotFrame]] = [:]
                try run.run(plan.study, field: body.field) { branch in
                    try capacityPilotJSON(branch).write(to: directory.appendingPathComponent("\(branch.name).json"))
                    if measured.contains(branch.name) { frames[branch.name] = branch.frames }
                    print("\(body.id) member-\(member) \(branch.name) completed")
                    fflush(nil)
                }
                members.append(frames)
                hashes.append(run.hashes)
            }
            for member in 0..<plan.repeatMembers {
                let rerun = harness(for: body, member: member, sink: .hashOnly)
                try rerun.run(plan.study, field: body.field) { _ in }
                let names = Set(hashes[member].keys).union(rerun.hashes.keys).sorted()
                compared += names.count
                for name in names {
                    if let first = hashes[member][name], first == rerun.hashes[name] {
                        matched += 1
                    } else {
                        mismatches.append("\(body.id)/member-\(member)/\(name)")
                    }
                }
            }
            bodies.append(CapacityPilotBodyMembers(body: body.id, diameter: body.diameter, members: members))
        }
        // The cpu engine is deterministic by contract, so a repeat difference there is a defect, not noise.
        if plan.backend == .cpu && !mismatches.isEmpty {
            throw ValidationError("cpu repeat check differed in \(mismatches.count) outputs: \(mismatches.prefix(8).joined(separator: ", "))")
        }
        let runtime = plan.bodies[0].runtime
        let conditions = capacityPilotConditions(bodies: bodies, continuous: plan.continuous, binary: plan.binary,
                                                 width: runtime.sx, height: runtime.sy, periodic: plan.periodic)
        let summary = CapacityPilotEnsembleSummary(
            designSha256: plan.sha256,
            members: plan.members,
            perturbedCells: plan.perturbedCells,
            perturbationSeed: plan.perturbationSeed,
            wilsonZ: capacityPilotWilsonZ,
            conditions: conditions,
            variance: capacityPilotVariance(conditions: conditions, continuous: plan.continuous),
            repeatCheck: CapacityPilotRepeatSummary(backend: plan.backend.rawValue, members: plan.repeatMembers,
                                                    compared: compared, matched: matched, mismatches: mismatches)
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .prettyPrinted]
        try encoder.encode(summary).write(to: root.appendingPathComponent("ensemble.json"))
        print("repeat check \(plan.backend.rawValue): \(matched)/\(compared) outputs matched")
        try receipt.finish()
    }
}
