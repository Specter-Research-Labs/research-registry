import Crypto
import Foundation
import LeniaCore

struct CapacityPilotDesignError: LocalizedError, CustomStringConvertible {
    let description: String
    var errorDescription: String? { description }
    init(_ description: String) { self.description = description }
}

/// Reads one JSON object and refuses keys it was not asked for, so a typo never becomes a default.
private final class DesignObject {
    let path: String
    private let values: [String: Any]
    private var consumed: Set<String> = []

    init(_ value: Any, path: String) throws {
        guard let values = value as? [String: Any] else { throw CapacityPilotDesignError("\(path): expected an object") }
        self.values = values
        self.path = path
    }

    func has(_ key: String) -> Bool { values[key] != nil }

    private func raw(_ key: String) throws -> Any {
        guard let value = values[key] else { throw CapacityPilotDesignError("\(path).\(key): required") }
        consumed.insert(key)
        return value
    }

    func int(_ key: String) throws -> Int {
        guard let value = try raw(key) as? Int else { throw CapacityPilotDesignError("\(path).\(key): expected an integer") }
        return value
    }

    func double(_ key: String) throws -> Double {
        try Self.number(raw(key), "\(path).\(key)")
    }

    func string(_ key: String) throws -> String {
        guard let value = try raw(key) as? String else { throw CapacityPilotDesignError("\(path).\(key): expected a string") }
        return value
    }

    func bool(_ key: String) throws -> Bool {
        guard let value = try raw(key) as? Bool else { throw CapacityPilotDesignError("\(path).\(key): expected true or false") }
        return value
    }

    func array(_ key: String) throws -> [Any] {
        guard let value = try raw(key) as? [Any] else { throw CapacityPilotDesignError("\(path).\(key): expected an array") }
        return value
    }

    func ints(_ key: String) throws -> [Int] {
        try array(key).enumerated().map { index, value in
            guard let int = value as? Int else { throw CapacityPilotDesignError("\(path).\(key)[\(index)]: expected an integer") }
            return int
        }
    }

    func doubles(_ key: String) throws -> [Double] {
        try array(key).enumerated().map { try Self.number($1, "\(path).\(key)[\($0)]") }
    }

    func doubleRows(_ key: String) throws -> [[Double]] {
        try array(key).enumerated().map { row, value in
            guard let values = value as? [Any] else { throw CapacityPilotDesignError("\(path).\(key)[\(row)]: expected an array") }
            return try values.enumerated().map { try Self.number($1, "\(path).\(key)[\(row)][\($0)]") }
        }
    }

    func strings(_ key: String) throws -> [String] {
        try array(key).enumerated().map { index, value in
            guard let string = value as? String else { throw CapacityPilotDesignError("\(path).\(key)[\(index)]: expected a string") }
            return string
        }
    }

    func object(_ key: String) throws -> DesignObject {
        try DesignObject(raw(key), path: "\(path).\(key)")
    }

    func optionalObject(_ key: String) throws -> DesignObject? {
        has(key) ? try object(key) : nil
    }

    func objects(_ key: String) throws -> [DesignObject] {
        try array(key).enumerated().map { try DesignObject($1, path: "\(path).\(key)[\($0)]") }
    }

    /// The raw JSON value, for objects another decoder owns.
    func json(_ key: String) throws -> Any { try raw(key) }

    func fail(_ key: String, _ message: String) -> CapacityPilotDesignError {
        CapacityPilotDesignError("\(path).\(key): \(message)")
    }

    func finish() throws {
        let unknown = Set(values.keys).subtracting(consumed).sorted()
        guard unknown.isEmpty else {
            throw CapacityPilotDesignError("\(path): unknown keys \(unknown.joined(separator: ", "))")
        }
    }

    private static func number(_ value: Any, _ path: String) throws -> Double {
        if let int = value as? Int { return Double(int) }
        guard let double = value as? Double, double.isFinite else { throw CapacityPilotDesignError("\(path): expected a finite number") }
        return double
    }
}

private func sha256Hex(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

/// A complete capacity-pilot study read from one design file. See docs/contracts/CapacityPilotDesign.md.
struct CapacityPilotDesign {
    struct Body {
        let id: String
        let initSeed: Int
        let runtime: LeniaRuntimeConfig
        let field: [Float]?
        let diameter: Double?
    }

    let data: Data
    let sha256: String
    let inputs: [URL]
    let backend: FlowLeniaComputeBackend
    let bodies: [Body]
    let study: CapacityPilotStudy
    let phantom: FlowLeniaPhantomSpec?
    let members: Int
    let perturbedCells: Int
    let perturbationSeed: UInt64
    let repeatMembers: Int
    let continuous: [CapacityPilotContinuousOutcome]
    let binary: [CapacityPilotBinaryOutcome]

    var periodic: Bool { bodies[0].runtime.border == "torus" }

    static func load(_ url: URL) throws -> CapacityPilotDesign {
        let data = try Data(contentsOf: url)
        let base = url.deletingLastPathComponent()
        var inputs = [url]
        func file(_ object: DesignObject, _ key: String) throws -> Data {
            let ref = try object.object(key)
            let path = try ref.string("path")
            let expected = try ref.string("sha256")
            try ref.finish()
            let fileURL = URL(fileURLWithPath: path, relativeTo: base).standardizedFileURL
            let bytes = try Data(contentsOf: fileURL)
            let actual = sha256Hex(bytes)
            guard actual == expected else {
                throw CapacityPilotDesignError("\(ref.path): \(path) has sha256 \(actual), the design names \(expected)")
            }
            inputs.append(fileURL)
            return bytes
        }
        func floats(_ bytes: Data, count: Int, _ path: String) throws -> [Float] {
            guard bytes.count == count * MemoryLayout<Float>.size else {
                throw CapacityPilotDesignError("\(path): expected \(count) float32 values, the file holds \(bytes.count) bytes")
            }
            return bytes.withUnsafeBytes { raw in
                stride(from: 0, to: bytes.count, by: 4).map { raw.loadUnaligned(fromByteOffset: $0, as: Float.self) }
            }
        }

        let root = try DesignObject(JSONDecoder().decode(AnyCodable.self, from: data).value, path: "design")

        let runtimeObject = try root.object("runtime")
        let config = try file(runtimeObject, "config")
        let backendName = try runtimeObject.string("backend")
        guard let backend = FlowLeniaComputeBackend(rawValue: backendName) else {
            throw runtimeObject.fail("backend", "must be mlx, metal-full or cpu")
        }
        let border = try runtimeObject.string("border")
        try runtimeObject.finish()

        let studyObject = try root.object("study")
        let kind = try studyObject.string("kind")
        let ensembleObject = try root.object("ensemble")
        let members = try ensembleObject.int("members")
        let perturbedCells = try ensembleObject.int("perturbed_cells")
        let seed = try ensembleObject.int("seed")
        try ensembleObject.finish()
        guard members >= 1 else { throw ensembleObject.fail("members", "must be at least 1") }
        guard perturbedCells >= 1 else { throw ensembleObject.fail("perturbed_cells", "must be at least 1") }
        guard seed >= 0 else { throw ensembleObject.fail("seed", "must be non-negative") }
        let repeatObject = try root.object("repeat_check")
        let repeatMembers = try repeatObject.int("members")
        try repeatObject.finish()
        guard (1...members).contains(repeatMembers) else {
            throw repeatObject.fail("members", "must lie in 1...\(members)")
        }

        let observation = ["development", "response"].contains(kind)
        let bodyObjects = try root.objects("bodies")
        guard !bodyObjects.isEmpty else { throw CapacityPilotDesignError("design.bodies: needs at least one body") }
        var bodies: [Body] = []
        var diameterFlags: [Bool] = []
        for object in bodyObjects {
            let id = try object.string("specimen_id")
            guard !id.isEmpty, !id.contains("/"), !id.hasPrefix("."), !bodies.contains(where: { $0.id == id }) else {
                throw object.fail("specimen_id", "must be a unique, nonempty name without '/' or a leading '.'")
            }
            let initSeed = try object.int("init_seed")
            let params = try object.object("params")
            var overrides: [String: Any] = [
                "backend": backendName,
                "reintegration.border": border,
                "params.mode": "explicit",
                "params.seed": initSeed,
                // Float32 first, as corpus rows decode their parameters.
                "params.R": Double(Float(try params.double("R"))),
                "params.r": try params.doubles("r").map { Double(Float($0)) },
                "params.m": try params.doubles("m").map { Double(Float($0)) },
                "params.s": try params.doubles("s").map { Double(Float($0)) },
                "params.h": try params.doubles("h").map { Double(Float($0)) },
                "params.a": try params.doubleRows("a").map { $0.map { Double(Float($0)) } },
                "params.b": try params.doubleRows("b").map { $0.map { Double(Float($0)) } },
                "params.w": try params.doubleRows("w").map { $0.map { Double(Float($0)) } },
            ]
            try params.finish()
            if object.has("initial_condition") {
                let initial = try object.json("initial_condition")
                let decoded = try JSONDecoder().decode(InitConfig.self,
                                                       from: JSONSerialization.data(withJSONObject: initial))
                guard decoded.seed == initSeed else {
                    throw object.fail("initial_condition", "seed \(decoded.seed) differs from init_seed \(initSeed)")
                }
                overrides["init"] = try JSONSerialization.jsonObject(with: JSONEncoder().encode(decoded))
            }
            let runtime: LeniaRuntimeConfig
            do { runtime = try loadRuntimeConfig(from: config, overrides: overrides) } catch {
                throw CapacityPilotDesignError("\(object.path): runtime config rejected: \(error)")
            }
            guard runtime.initSeed == initSeed else {
                throw object.fail("init_seed", "\(initSeed) differs from the runtime's init seed \(runtime.initSeed); give an initial_condition with that seed")
            }
            if let previous = bodies.first?.runtime,
               (previous.sx, previous.sy, previous.channels) != (runtime.sx, runtime.sy, runtime.channels) {
                throw CapacityPilotDesignError("\(object.path): all bodies must share grid and channels")
            }
            let field: [Float]?
            if object.has("field") {
                field = try floats(file(object, "field"), count: runtime.sx * runtime.sy * runtime.channels, "\(object.path).field")
            } else {
                field = nil
            }
            let diameter = object.has("diameter") ? try object.double("diameter") : nil
            if let diameter, diameter <= 0 { throw object.fail("diameter", "must be positive") }
            diameterFlags.append(diameter != nil)
            try object.finish()
            try validateRuntime(runtime, kind: kind, observation: observation, path: object.path)
            bodies.append(Body(id: id, initSeed: initSeed, runtime: runtime, field: field, diameter: diameter))
        }
        let runtime = bodies[0].runtime

        var phantom: FlowLeniaPhantomSpec?
        if let object = try studyObject.optionalObject("phantom") {
            guard ["development", "state-flow"].contains(kind) else {
                throw studyObject.fail("phantom", "only the development and state-flow studies take a phantom")
            }
            guard backend == .metalFull else {
                throw studyObject.fail("phantom", "needs backend metal-full; the \(backendName) engine has no phantom field")
            }
            let sourceName = try object.string("source")
            guard let source = FlowLeniaPhantomSpec.Source(rawValue: sourceName) else {
                throw object.fail("source", "must be static or replay")
            }
            let pressure = try object.bool("pressure")
            let values = try floats(file(object, "field"), count: runtime.sx * runtime.sy * runtime.channels, "\(object.path).field")
            try object.finish()
            phantom = FlowLeniaPhantomSpec(source: source, pressure: pressure, field: values)
        }

        func steps(_ key: String, multipleOf32: Bool) throws -> Int {
            let value = try studyObject.int(key)
            guard value > 0, !multipleOf32 || value % 32 == 0 else {
                throw studyObject.fail(key, multipleOf32 ? "must be a positive multiple of 32" : "must be positive")
            }
            return value
        }
        func release(_ key: String) throws -> Int {
            let value = try studyObject.int(key)
            guard value >= 0, value % 32 == 0 else { throw studyObject.fail(key, "must be a non-negative multiple of 32") }
            return value
        }
        func shear(_ key: String) throws -> Double {
            let value = try studyObject.double(key)
            guard value > 0 else { throw studyObject.fail(key, "must be positive; studies apply both signs or name one") }
            return value
        }
        func dose(_ object: DesignObject, _ key: String) throws -> Double {
            let value = try object.double(key)
            guard (0..<1).contains(value) else { throw object.fail(key, "must lie in [0, 1)") }
            return value
        }
        func ageOffsets() throws -> [Int] {
            let offsets = try studyObject.ints("age_offsets")
            guard offsets.first == 0, zip(offsets, offsets.dropFirst()).allSatisfy({ $0 < $1 }),
                  offsets.allSatisfy({ $0 % 32 == 0 }) else {
                throw studyObject.fail("age_offsets", "must start at 0 and increase in multiples of 32")
            }
            return offsets
        }
        func challenge() throws -> CapacityPilotChallenge {
            let object = try studyObject.object("challenge")
            let horizon = try object.int("horizon")
            let shear = try object.double("shear")
            let sign = try object.int("sign")
            let axis = try object.string("axis")
            try object.finish()
            guard horizon > 0, horizon % 32 == 0 else { throw object.fail("horizon", "must be a positive multiple of 32") }
            guard shear > 0 else { throw object.fail("shear", "must be positive; sign gives the direction") }
            guard [-1, 1].contains(sign) else { throw object.fail("sign", "must be 1 or -1") }
            guard ["x", "y"].contains(axis) else { throw object.fail("axis", "must be x or y") }
            guard axis == "x" || runtime.sx == runtime.sy else { throw object.fail("axis", "y needs a square grid") }
            return CapacityPilotChallenge(horizon: horizon, shear: shear, sign: sign, axis: axis)
        }
        func writeEdit() throws -> CapacityPilotEdit {
            let mode = try studyObject.string("write_mode")
            switch mode {
            case "sham": return .sham
            case "field": return .field
            case "positive", "negative", "scrambled": return .balanced(mode: mode, dose: try dose(studyObject, "write_dose"))
            default: throw studyObject.fail("write_mode", "must be sham, positive, negative, scrambled or field")
            }
        }

        let study: CapacityPilotStudy
        switch kind {
        case "original":
            study = .original(checkpointSteps: try steps("checkpoint_steps", multipleOf32: false),
                              horizon: try steps("horizon", multipleOf32: true),
                              probeShear: try shear("probe_shear"), probeSteps: try steps("probe_steps", multipleOf32: true),
                              challengeShear: try shear("challenge_shear"), writeDose: try dose(studyObject, "write_dose"))
        case "symmetry":
            guard runtime.sx == runtime.sy else { throw studyObject.fail("kind", "symmetry needs a square grid") }
            let transformSteps = try studyObject.ints("transform_steps")
            guard !transformSteps.isEmpty, transformSteps.allSatisfy({ $0 > 0 }) else {
                throw studyObject.fail("transform_steps", "must be a nonempty list of positive step counts")
            }
            study = .symmetry(checkpointSteps: try steps("checkpoint_steps", multipleOf32: false), transformSteps: transformSteps)
        case "followup":
            let checkpointSteps = try steps("checkpoint_steps", multipleOf32: false)
            let horizon = try steps("horizon", multipleOf32: true)
            let offsets = try ageOffsets()
            let probeShear = try shear("probe_shear")
            let probeSteps = try steps("probe_steps", multipleOf32: true)
            let challengeShear = try shear("challenge_shear")
            let writeDose = try dose(studyObject, "write_dose")
            let waitSteps = try steps("wait_steps", multipleOf32: true)
            let secondWrite = try steps("second_write_step", multipleOf32: true)
            guard secondWrite <= waitSteps else { throw studyObject.fail("second_write_step", "must not exceed wait_steps") }
            study = .followup(checkpointSteps: checkpointSteps, horizon: horizon, ageOffsets: offsets,
                              probeShear: probeShear, probeSteps: probeSteps, challengeShear: challengeShear,
                              writeDose: writeDose, waitSteps: waitSteps, secondWriteStep: secondWrite)
        case "development":
            let horizon = try steps("horizon", multipleOf32: false)
            var ancestry: CapacityPilotAncestry?
            if let object = try studyObject.optionalObject("ancestry") {
                guard backend == .metalFull else {
                    throw studyObject.fail("ancestry", "needs backend metal-full; the \(backendName) engine has no founder-mass transport")
                }
                guard bodies.count == 1 else { throw studyObject.fail("ancestry", "needs exactly one body") }
                let founders = try object.int("founders")
                guard founders > 0 else { throw object.fail("founders", "must be positive") }
                let exportSteps = try object.ints("export_steps")
                guard Set(exportSteps).count == exportSteps.count, exportSteps.allSatisfy({ (0...horizon).contains($0) }) else {
                    throw object.fail("export_steps", "must be distinct steps within 0...\(horizon)")
                }
                let cells = runtime.sx * runtime.sy
                let seedValue: CapacityPilotAncestry.Seed
                switch (object.has("labels"), object.has("founder_mass")) {
                case (true, false):
                    let bytes = try file(object, "labels")
                    guard bytes.count == cells * MemoryLayout<Int32>.size else {
                        throw object.fail("labels", "needs one int32 per cell")
                    }
                    seedValue = .labels(bytes.withUnsafeBytes { raw in
                        stride(from: 0, to: bytes.count, by: 4).map { raw.loadUnaligned(fromByteOffset: $0, as: Int32.self) }
                    })
                case (false, true):
                    // Founder masses must sum exactly to the starting field, which a perturbation would break.
                    guard members == 1 else { throw object.fail("founder_mass", "needs ensemble.members 1") }
                    seedValue = .founderMass(try floats(file(object, "founder_mass"), count: cells * runtime.channels * founders,
                                                        "\(object.path).founder_mass"))
                default:
                    throw studyObject.fail("ancestry", "needs exactly one of labels or founder_mass")
                }
                try object.finish()
                ancestry = CapacityPilotAncestry(seed: seedValue, founderCount: founders, exportSteps: Set(exportSteps))
            }
            study = .development(horizon: horizon, ancestry: ancestry)
        case "response":
            study = .response(checkpointSteps: try steps("checkpoint_steps", multipleOf32: false),
                              horizon: try steps("horizon", multipleOf32: true), offsets: try ageOffsets(),
                              probeShear: try shear("probe_shear"), probeSteps: try steps("probe_steps", multipleOf32: true),
                              challengeShear: try shear("challenge_shear"))
        case "write-response":
            study = .write(checkpointSteps: try steps("checkpoint_steps", multipleOf32: false), edit: try writeEdit(),
                           releaseSteps: try release("release_steps"), challenge: try challenge(), replaceState: false)
        case "write-release":
            study = .write(checkpointSteps: try steps("checkpoint_steps", multipleOf32: false), edit: try writeEdit(),
                           releaseSteps: try release("release_steps"), challenge: nil, replaceState: false)
        case "state-response":
            study = .write(checkpointSteps: try steps("checkpoint_steps", multipleOf32: false), edit: .field,
                           releaseSteps: 0, challenge: try challenge(), replaceState: true)
        case "state-continuation":
            study = .stateContinuation(horizon: try steps("horizon", multipleOf32: true))
        case "state-flow":
            study = .stateFlow(horizon: try steps("horizon", multipleOf32: false),
                               savePotential: try studyObject.bool("save_potential"))
        case "transport":
            guard runtime.sx >= 256, runtime.sy >= 256 else { throw studyObject.fail("kind", "transport needs a grid of at least 256 x 256") }
            study = .transport(checkpointSteps: try steps("checkpoint_steps", multipleOf32: false),
                               releaseSteps: try release("release_steps"), horizon: try steps("horizon", multipleOf32: false),
                               challengeShear: try shear("challenge_shear"))
        default:
            throw studyObject.fail("kind", "unknown study \(kind); expected original, symmetry, followup, development, response, write-response, write-release, state-response, state-continuation, state-flow or transport")
        }
        try studyObject.finish()
        for (body, object) in zip(bodies, bodyObjects) where (body.field != nil) != study.usesField {
            throw CapacityPilotDesignError("\(object.path).field: " + (study.usesField
                ? "required, this study starts from a supplied field" : "unused, this study starts from the seed-built state"))
        }

        let branches = Dictionary(uniqueKeysWithValues: study.branches.map { ($0.name, $0.steps) })
        let outcomesObject = try root.object("outcomes")
        var names = Set<String>()
        var continuous: [CapacityPilotContinuousOutcome] = []
        for object in try outcomesObject.objects("continuous") {
            let name = try object.string("name")
            guard names.insert(name).inserted else { throw object.fail("name", "duplicate outcome \(name)") }
            let measureName = try object.string("measure")
            guard let measure = CapacityPilotMeasure(rawValue: measureName) else {
                throw object.fail("measure", "must be one of \(CapacityPilotMeasure.allCases.map(\.rawValue).joined(separator: ", "))")
            }
            let outcomeBranches = try object.strings("branches")
            let from = try object.int("from_step")
            let to = try object.int("to_step")
            try object.finish()
            guard !outcomeBranches.isEmpty, Set(outcomeBranches).count == outcomeBranches.count else {
                throw object.fail("branches", "must be a nonempty list of distinct branches")
            }
            for branch in outcomeBranches {
                guard let length = branches[branch] else {
                    throw object.fail("branches", "\(kind) emits no branch \(branch); it emits \(study.branches.map(\.name).joined(separator: ", "))")
                }
                let frames = capacityPilotFrameSteps(length)
                guard from < to, frames.contains(from), frames.contains(to) else {
                    throw object.fail("from_step", "\(from)...\(to) must be an increasing pair of frame steps of \(branch) (every 32 steps through \(length))")
                }
            }
            continuous.append(CapacityPilotContinuousOutcome(name: name, measure: measure, branches: outcomeBranches,
                                                             fromStep: from, toStep: to))
        }
        var binary: [CapacityPilotBinaryOutcome] = []
        for object in try outcomesObject.objects("binary") {
            let name = try object.string("name")
            guard names.insert(name).inserted else { throw object.fail("name", "duplicate outcome \(name)") }
            var conditions: [CapacityPilotBinaryOutcome.Condition] = []
            for condition in try object.objects("all") {
                let outcome = try condition.string("outcome")
                let op = try condition.string("op")
                let value = try condition.double("value")
                try condition.finish()
                guard continuous.contains(where: { $0.name == outcome }) else {
                    throw condition.fail("outcome", "names no continuous outcome")
                }
                guard let comparison = CapacityPilotBinaryOutcome.Comparison(rawValue: op) else {
                    throw condition.fail("op", "must be >= or <=")
                }
                conditions.append(.init(outcome: outcome, comparison: comparison, value: value))
            }
            try object.finish()
            let referenced = Set(conditions.map(\.outcome)).map { name in continuous.first { $0.name == name }!.branches }
            guard !conditions.isEmpty, Set(referenced).count == 1 else {
                throw object.fail("all", "needs at least one condition, over continuous outcomes with identical branches")
            }
            binary.append(CapacityPilotBinaryOutcome(name: name, all: conditions))
        }
        try outcomesObject.finish()
        let needsDiameter = continuous.contains { $0.measure == .centroidPathDiameters }
        for (flag, object) in zip(diameterFlags, bodyObjects) where flag != needsDiameter {
            throw CapacityPilotDesignError("\(object.path).diameter: " + (needsDiameter
                ? "required by a centroid_path_diameters outcome" : "unused, no outcome measures in diameters"))
        }
        try root.finish()
        return CapacityPilotDesign(
            data: data, sha256: sha256Hex(data), inputs: inputs, backend: backend, bodies: bodies, study: study,
            phantom: phantom, members: members, perturbedCells: perturbedCells, perturbationSeed: UInt64(seed),
            repeatMembers: repeatMembers, continuous: continuous, binary: binary)
    }

    private static func validateRuntime(_ runtime: LeniaRuntimeConfig, kind: String, observation: Bool, path: String) throws {
        func fail(_ message: String) -> CapacityPilotDesignError { CapacityPilotDesignError("\(path): \(message)") }
        guard runtime.environment == nil, runtime.walls?.enabled != true, runtime.obstacleField?.enabled != true,
              runtime.interventions.isEmpty else {
            throw fail("the pilot needs a clean runtime without environment, walls, obstacles or interventions")
        }
        if !observation {
            guard runtime.channels >= 2, runtime.border == "wall" else {
                throw fail("\(kind) needs at least two channels and a wall border")
            }
        }
        switch runtime.backend {
        case .mlx:
            guard observation else { throw fail("\(kind) needs backend metal-full or cpu; mlx keeps no resident state") }
        case .metalFull:
            guard FlowLeniaInteractiveSimulator.supportsResidentMetal(runtime) else {
                throw fail("backend metal-full does not support this runtime contract")
            }
        case .cpu:
            if let violation = FlowLeniaInteractiveSimulator.residentCPUViolation(runtime) { throw fail(violation) }
        @unknown default:
            throw fail("unsupported backend \(runtime.backend)")
        }
        let paperKinds = ["write-response", "write-release", "state-response", "state-continuation", "state-flow", "transport"]
        if paperKinds.contains(kind) && runtime.implementation.mode != "flowlenia_2022_paper_equations" {
            throw fail("\(kind) needs implementation mode flowlenia_2022_paper_equations")
        }
        if ["state-continuation", "state-flow"].contains(kind) && runtime.parameterEmbedding.enabled {
            throw fail("\(kind) restarts from mass alone and needs fixed parameters without embedding")
        }
    }
}
