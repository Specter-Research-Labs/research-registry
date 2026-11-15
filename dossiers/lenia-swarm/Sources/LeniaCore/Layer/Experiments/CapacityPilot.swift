import Crypto
import Foundation
import MLX
import MLXFFT

public struct CapacityPilotFrame: Codable {
    public let step: Int
    public let mass: Double
    public let channel0: Double
    public let radius95: Float?
    public let coherence: Float?
    public let centerX: Float?
    public let centerY: Float?
    public let image: [Float]
    public let fieldSha256: String
}

public struct CapacityPilotBranch: Codable {
    public let name: String
    public let visibleEditL1: Double
    public let channelEditL1: Double
    public let channelInventoryError: Double
    public let frames: [CapacityPilotFrame]
}

public struct CapacityPilotAncestry {
    public enum Seed {
        /// Founder index per cell in mass layout (x-major); -1 marks cells that must hold no matter.
        case labels([Int32])
        /// Founder mass [sx, sy, channels, founders]; per cell and channel the founders must sum exactly, in float32, to the initial mass.
        case founderMass([Float])
    }

    public let seed: Seed
    public let founderCount: Int
    public let exportSteps: Set<Int>

    public init(seed: Seed, founderCount: Int, exportSteps: Set<Int>) {
        self.seed = seed
        self.founderCount = founderCount
        self.exportSteps = exportSteps
    }
}

public struct CapacityPilotAncestryRecord: Codable {
    public let founders: Int
    public let channels: Int
    public let fieldShape: [Int]
    public let steps: [Int]
    /// Per step, per channel, per founder: total founder mass.
    public let founderMass: [[[Double]]]
    /// Per step, per channel: total matter, the quantity founder masses must sum to.
    public let channelMass: [[Double]]
    /// Per step: sum over cells and channels of |sum_j B[c, j] - A[c]| divided by total matter.
    public let founderSumResidual: [Double]
    public let exportSteps: [Int]
}

public func capacityPilotFounderMass(_ mass: [Float], labels: [Int32], channels: Int,
                                     founderCount: Int) throws -> [Float] {
    guard labels.count * channels == mass.count else {
        throw NSError(domain: "CapacityPilot", code: 9,
                      userInfo: [NSLocalizedDescriptionKey: "Ancestry labels must have one entry per cell"])
    }
    var founderMass = [Float](repeating: 0, count: mass.count * founderCount)
    for cell in labels.indices {
        let label = Int(labels[cell])
        let matter = (0..<channels).contains { mass[cell * channels + $0] > 0 }
        guard label >= -1, label < founderCount, label >= 0 || !matter else {
            throw NSError(domain: "CapacityPilot", code: 9, userInfo: [NSLocalizedDescriptionKey:
                "Ancestry label \(label) at cell \(cell) is out of range or leaves matter unlabeled"])
        }
        guard label >= 0 else { continue }
        for c in 0..<channels {
            founderMass[(cell * channels + c) * founderCount + label] = mass[cell * channels + c]
        }
    }
    return founderMass
}

public func capacityPilotCheckedFounderMass(_ mass: [Float], founderMass: [Float], channels: Int,
                                            founderCount: Int) throws -> [Float] {
    guard founderMass.count == mass.count * founderCount else {
        throw NSError(domain: "CapacityPilot", code: 9,
                      userInfo: [NSLocalizedDescriptionKey: "Founder mass must have shape [sx, sy, channels, founders]"])
    }
    for index in mass.indices {
        let parts = founderMass[(index * founderCount)..<((index + 1) * founderCount)]
        guard parts.allSatisfy({ $0.isFinite && $0 >= 0 }), parts.reduce(Float(0), +) == mass[index] else {
            throw NSError(domain: "CapacityPilot", code: 9, userInfo: [NSLocalizedDescriptionKey:
                "Founder mass at entry \(index) is negative, non-finite, or does not sum to the initial mass"])
        }
    }
    return founderMass
}

// Pair equal and opposite transfers so every cell retains its total matter and
// channel inventories stay fixed. Only channels 0 and 1 exchange matter. The dose counts both channel edits.
public func capacityPilotWrite(_ values: [Float], width: Int, height: Int, channels: Int,
                               centerX: Float, mode: String, dose: Double) -> [Float] {
    precondition(channels >= 2 && values.count == width * height * channels && dose >= 0 && dose < 1)
    precondition(["positive", "negative", "scrambled"].contains(mode))
    let total = values.reduce(0.0) { $0 + Double($1) }
    var positive = [Bool](repeating: false, count: width * height)
    var plus = 0.0, minus = 0.0
    for i in positive.indices {
        let x = i / height
        let hashed = (UInt64(i) &* 2654435761) ^ (UInt64(i) >> 3)
        positive[i] = mode == "scrambled" ? (hashed % 2 == 0) :
            (mode == "positive" ? Float(x) >= centerX : Float(x) < centerX)
        if positive[i] { plus += Double(values[channels * i + 1]) }
        else { minus += Double(values[channels * i]) }
    }
    let amount = min(total * dose / 4, min(plus, minus) * 0.95)
    guard amount > 0 else { return values }
    var result = values
    for i in positive.indices {
        let a = Double(values[channels * i]), b = Double(values[channels * i + 1])
        let delta = positive[i] ? amount * b / plus : -amount * a / minus
        result[channels * i] = Float(a + delta)
        result[channels * i + 1] = Float(b - delta)
    }
    return result
}

public func capacityPilotShear(_ values: [Float], width: Int, height: Int, channels: Int,
                               centerX: Float, amount: Float, periodic: Bool = false) -> [Float] {
    precondition(channels >= 1 && values.count == width * height * channels)
    var result = values
    for x in 0..<width {
        let offset = Float(x) - centerX
        let distance = periodic ? periodicDelta(offset, period: Float(width)) : offset
        let shift = Int((amount * distance).rounded())
        for y in 0..<height {
            let destinationY = ((y + shift) % height + height) % height
            for channel in 0..<channels {
                result[(x * height + destinationY) * channels + channel] = values[(x * height + y) * channels + channel]
            }
        }
    }
    return result
}

public func capacityPilotTransform(_ values: [Float], side: Int, channels: Int, transpose: Bool) -> [Float] {
    precondition(channels >= 2 && values.count == side * side * channels)
    var result = values
    for x in 0..<side {
        for y in 0..<side {
            let tx = transpose ? y : side - 1 - y
            let ty = x
            for c in 0..<channels { result[(tx * side + ty) * channels + c] = values[(x * side + y) * channels + c] }
        }
    }
    return result
}

/// A study the harness runs, with every magnitude and timing explicit. Shears are fractions of a
/// cell per cell of distance from the body's center column; doses are fractions of total matter.
public enum CapacityPilotStudy {
    case original(checkpointSteps: Int, horizon: Int, probeShear: Double, probeSteps: Int,
                  challengeShear: Double, writeDose: Double)
    case symmetry(checkpointSteps: Int, transformSteps: [Int])
    case followup(checkpointSteps: Int, horizon: Int, ageOffsets: [Int], probeShear: Double, probeSteps: Int,
                  challengeShear: Double, writeDose: Double, waitSteps: Int, secondWriteStep: Int)
    case development(horizon: Int, ancestry: CapacityPilotAncestry?)
    case response(checkpointSteps: Int, horizon: Int, offsets: [Int], probeShear: Double, probeSteps: Int,
                  challengeShear: Double)
    /// `replaceState` admits a field that changes density and channel inventories (the
    /// state-response counterfactual); otherwise the edit must preserve both.
    case write(checkpointSteps: Int, edit: CapacityPilotEdit, releaseSteps: Int,
               challenge: CapacityPilotChallenge?, replaceState: Bool)
    case stateContinuation(horizon: Int)
    case stateFlow(horizon: Int, savePotential: Bool)
    case transport(checkpointSteps: Int, releaseSteps: Int, horizon: Int, challengeShear: Double)

    public static let followupConditions = ["sham", "positive", "negative", "scrambled", "positive-immediate-undo",
                                            "positive-then-negative", "scrambled-twice"]

    /// True when the study starts from a supplied mass field instead of the seed-built state.
    public var usesField: Bool {
        switch self {
        case .stateContinuation, .stateFlow: true
        case let .write(_, edit, _, _, _): if case .field = edit { true } else { false }
        default: false
        }
    }

    /// The branches the study emits, in emission order, with their lengths in steps.
    public var branches: [(name: String, steps: Int)] {
        func ages(_ checkpointSteps: Int, _ offsets: [Int], _ horizon: Int, _ probeSteps: Int) -> [(name: String, steps: Int)] {
            offsets.flatMap { offset -> [(name: String, steps: Int)] in
                let prefix = "age-\(checkpointSteps + offset)"
                return [(prefix + "-sham", horizon), (prefix + "-probe-positive", probeSteps),
                        (prefix + "-challenge-positive", horizon), (prefix + "-probe-negative", probeSteps),
                        (prefix + "-challenge-negative", horizon)]
            }
        }
        switch self {
        case let .original(_, horizon, _, probeSteps, _, _):
            return [("sham", horizon), ("probe-positive", probeSteps), ("probe-negative", probeSteps),
                    ("challenge-positive", horizon), ("challenge-negative", horizon), ("write-positive", horizon),
                    ("write-negative", horizon), ("write-scrambled", horizon)]
        case .symmetry, .stateFlow, .transport:
            return []
        case let .followup(checkpointSteps, horizon, offsets, _, probeSteps, _, _, waitSteps, _):
            return ages(checkpointSteps, offsets, horizon, probeSteps) + Self.followupConditions.flatMap { condition in
                let prefix = "history-" + condition
                return [(prefix + "-wait", waitSteps), (prefix + "-unchallenged", horizon),
                        (prefix + "-challenge-positive", horizon), (prefix + "-challenge-negative", horizon)]
            }
        case let .development(horizon, _):
            return [("development", horizon)]
        case let .response(checkpointSteps, horizon, offsets, _, probeSteps, _):
            return ages(checkpointSteps, offsets, horizon, probeSteps)
        case let .write(_, _, releaseSteps, challenge, _):
            return [("release", releaseSteps)]
                + (challenge.map { [("unchallenged", $0.horizon), ("challenge", $0.horizon)] } ?? [])
        case let .stateContinuation(horizon):
            return [("continuation", horizon)]
        }
    }
}

public enum CapacityPilotEdit {
    case sham
    /// Balanced channel exchange, `mode` positive, negative or scrambled.
    case balanced(mode: String, dose: Double)
    /// The supplied field replaces the checkpoint mass.
    case field
}

public struct CapacityPilotChallenge {
    public let horizon: Int
    public let shear: Double
    public let sign: Int
    /// "x" shears along y by distance from the center column; "y" is the transposed shear.
    public let axis: String

    public init(horizon: Int, shear: Double, sign: Int, axis: String) {
        precondition([-1, 1].contains(sign) && ["x", "y"].contains(axis))
        self.horizon = horizon
        self.shear = shear
        self.sign = sign
        self.axis = axis
    }
}

/// Branch frames are taken every 32 steps and at the branch's last step.
public func capacityPilotFrameSteps(_ steps: Int) -> [Int] {
    Array(stride(from: 0, to: steps, by: 32)) + [steps]
}

/// Sorted keys, because JSONEncoder's key order otherwise changes from process to process and breaks byte-level repeat checks.
public func capacityPilotJSON(_ value: some Encodable) throws -> Data {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    return try encoder.encode(value)
}

public enum CapacityPilotSink {
    case directory(URL)
    /// Hash every output without writing it, for repeat checks.
    case hashOnly
}

private func sha256Hex<D: DataProtocol>(_ data: D) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

/// Runs one study for one ensemble member. Every output passes through the sink, which records
/// its sha256 under the output name; frame fields are recorded as "frame:<branch>@<step>".
public final class CapacityPilotHarness {
    private let simulator: FlowLeniaInteractiveSimulator
    private let width: Int
    private let height: Int
    private let channelCount: Int
    private let hasPhantom: Bool
    private let sink: CapacityPilotSink
    private let perturbation: CapacityPilotPerturbation
    private var phantomFrames: [[String: Any]] = []
    private var emitted: [String] = []
    public private(set) var hashes: [String: String] = [:]

    public init(config: LeniaRuntimeConfig, phantom: FlowLeniaPhantomSpec?, sink: CapacityPilotSink,
                perturbation: CapacityPilotPerturbation) {
        precondition(config.channels >= 1)
        simulator = FlowLeniaInteractiveSimulator(runtimeConfig: config, phantom: phantom)
        width = config.sx
        height = config.sy
        channelCount = config.channels
        hasPhantom = phantom != nil
        self.sink = sink
        self.perturbation = perturbation
    }

    public func run(_ study: CapacityPilotStudy, field: [Float]?, emit: (CapacityPilotBranch) throws -> Void) throws {
        precondition(hashes.isEmpty, "A harness runs one study")
        precondition(study.usesField == (field != nil))
        let made = simulator.makeInitialState()
        let start = try perturbation.apply(field ?? made.mass.asArray(Float.self))
        try store("perturbation.json", capacityPilotJSON(start.record))
        let initial = field == nil ? simulator.makeResident(copied(made, values: start.values)) : made
        switch study {
        case let .original(checkpointSteps, horizon, probeShear, probeSteps, challengeShear, writeDose):
            try runOriginal(initial, checkpointSteps: checkpointSteps, horizon: horizon, probeShear: probeShear,
                            probeSteps: probeSteps, challengeShear: challengeShear, writeDose: writeDose, emit: emit)
        case let .symmetry(checkpointSteps, transformSteps):
            try runSymmetry(initial, checkpointSteps: checkpointSteps, transformSteps: transformSteps)
        case let .followup(checkpointSteps, horizon, offsets, probeShear, probeSteps, challengeShear, writeDose,
                           waitSteps, secondWriteStep):
            let checkpoint = simulator.step(initial, count: checkpointSteps)
            try runAges(checkpoint, checkpointSteps: checkpointSteps, horizon: horizon, offsets: offsets,
                        probeShear: probeShear, probeSteps: probeSteps, challengeShear: challengeShear,
                        saveFrames: false, emit: emit)
            try runHistories(checkpoint, horizon: horizon, challengeShear: challengeShear, writeDose: writeDose,
                             waitSteps: waitSteps, secondWriteStep: secondWriteStep, emit: emit)
        case let .development(horizon, ancestry):
            try runDevelopment(initial, horizon: horizon, ancestry: ancestry, emit: emit)
        case let .response(checkpointSteps, horizon, offsets, probeShear, probeSteps, challengeShear):
            try runAges(simulator.step(initial, count: checkpointSteps), checkpointSteps: checkpointSteps,
                        horizon: horizon, offsets: offsets, probeShear: probeShear, probeSteps: probeSteps,
                        challengeShear: challengeShear, saveFrames: true, emit: emit)
        case let .write(checkpointSteps, edit, releaseSteps, challenge, replaceState):
            try runWrite(initial, checkpointSteps: checkpointSteps, edit: edit, field: start.values,
                         releaseSteps: releaseSteps, challenge: challenge, replaceState: replaceState, emit: emit)
        case let .stateContinuation(horizon):
            try runStateContinuation(initial, values: start.values, steps: horizon, emit: emit)
        case let .stateFlow(horizon, savePotential):
            try runStateFlow(initial, values: start.values, steps: horizon, savePotential: savePotential)
        case let .transport(checkpointSteps, releaseSteps, horizon, challengeShear):
            try runTransport(initial, checkpointSteps: checkpointSteps, releaseSteps: releaseSteps, horizon: horizon,
                             challengeShear: challengeShear)
        }
        if hasPhantom {
            try store("phantom-frames.json",
                      JSONSerialization.data(withJSONObject: phantomFrames, options: [.sortedKeys, .prettyPrinted]))
        }
        precondition(emitted == study.branches.map(\.name), "Emitted branches differ from the study's branch list")
    }

    private func store(_ name: String, _ data: Data) throws {
        precondition(hashes[name] == nil, "Duplicate capacity-pilot output \(name)")
        hashes[name] = sha256Hex(data)
        if case .directory(let url) = sink { try data.write(to: url.appendingPathComponent(name)) }
    }

    private func store(_ name: String, floats: [Float]) throws {
        try store(name + ".f32", floats.withUnsafeBytes { Data($0) })
    }

    private func storeJSON(_ name: String, _ object: Any) throws {
        try store(name, JSONSerialization.data(withJSONObject: object, options: [.sortedKeys, .prettyPrinted]))
    }

    private func publish(_ branch: CapacityPilotBranch, _ emit: (CapacityPilotBranch) throws -> Void) throws {
        for frame in branch.frames {
            let key = "frame:\(branch.name)@\(frame.step)"
            precondition(hashes[key] == nil, "Duplicate capacity-pilot frame \(key)")
            hashes[key] = frame.fieldSha256
        }
        emitted.append(branch.name)
        try emit(branch)
    }

    private func recordPhantom(step: Int) {
        guard hasPhantom else { return }
        phantomFrames.append(["step": step, "sha256": simulator.phantomField().withUnsafeBytes { sha256Hex($0) }])
    }

    private func frame(_ state: FlowLeniaInteractiveState, relativeStep: Int) -> CapacityPilotFrame {
        let channels = state.mass.asArray(Float.self)
        let values = stride(from: 0, to: channels.count, by: channelCount).map { start in
            channels[start..<(start + channelCount)].reduce(0, +)
        }
        let body = unseenObstacleLargestBody(values: values, width: width, height: height,
                                             threshold: 0.01, periodic: simulator.runtimeConfig.border == "torus")
        var image = [Float](repeating: 0, count: 128 * 128)
        for x in 0..<width {
            for y in 0..<height {
                image[(y * 128 / height) * 128 + x * 128 / width] += values[x * height + y]
            }
        }
        return CapacityPilotFrame(step: relativeStep,
            mass: channels.reduce(0.0) { $0 + Double($1) },
            channel0: stride(from: 0, to: channels.count, by: channelCount).reduce(0.0) { $0 + Double(channels[$1]) },
            radius95: body?.radius95, coherence: body?.massFraction,
            centerX: body?.center.x, centerY: body?.center.y, image: image,
            fieldSha256: channels.withUnsafeBytes { sha256Hex($0) })
    }

    private func copied(_ state: FlowLeniaInteractiveState, values: [Float]) -> FlowLeniaInteractiveState {
        FlowLeniaInteractiveState(step: state.step, mass: MLXArray(values, state.mass.shape),
                                 params: state.params, food: state.food)
    }

    private func shear(_ values: [Float], centerX: Float, amount: Float) -> [Float] {
        capacityPilotShear(values, width: width, height: height, channels: channelCount, centerX: centerX,
                           amount: amount, periodic: simulator.runtimeConfig.border == "torus")
    }

    private func editMetrics(_ original: [Float], _ values: [Float]) -> (Double, Double, Double) {
        let total = original.reduce(0.0) { $0 + Double($1) }
        var visible = 0.0, edit = 0.0
        var inventory = [Double](repeating: 0, count: channelCount)
        for i in stride(from: 0, to: values.count, by: channelCount) {
            let before = original[i..<(i + channelCount)].reduce(0, +)
            let after = values[i..<(i + channelCount)].reduce(0, +)
            visible += abs(Double(after) - Double(before))
            for c in 0..<channelCount {
                let delta = Double(values[i + c]) - Double(original[i + c])
                edit += abs(delta)
                inventory[c] += delta
            }
        }
        return (visible / total, edit / total, inventory.map { abs($0) }.max()! / total)
    }

    private func center(_ state: FlowLeniaInteractiveState, _ context: String) throws -> (x: Float, y: Float) {
        let f = frame(state, relativeStep: 0)
        guard let x = f.centerX, let y = f.centerY else {
            throw NSError(domain: "CapacityPilot", code: 5,
                          userInfo: [NSLocalizedDescriptionKey: "No thresholded body at \(context)"])
        }
        return (x, y)
    }

    private func continueBranch(_ source: FlowLeniaInteractiveState, values: [Float], name: String,
                                steps: Int, saveFrames: Bool,
                                emit: (CapacityPilotBranch) throws -> Void) throws {
        let original = source.mass.asArray(Float.self)
        let edits = editMetrics(original, values)
        var state = copied(source, values: values)
        var frames = [frame(state, relativeStep: 0)]
        let mass = frames[0].mass
        let conservesMatter = simulator.runtimeConfig.implementation.mode != "qd24_additive_v1"
        if saveFrames { try store(name + "-step-0", floats: values) }
        for t in stride(from: 32, through: steps, by: 32) {
            state = simulator.step(state, count: 32)
            let f = frame(state, relativeStep: t)
            let field = state.mass.asArray(Float.self)
            guard field.allSatisfy({ $0.isFinite && $0 >= 0 }),
                  !conservesMatter || abs(f.mass / mass - 1) < 0.001 else {
                throw NSError(domain: "CapacityPilot", code: 4, userInfo: [NSLocalizedDescriptionKey: "Invalid continuation: \(name), step \(t)"])
            }
            frames.append(f)
            if saveFrames { try store(name + "-step-\(t)", floats: field) }
        }
        try store(name + "-final", floats: state.mass.asArray(Float.self))
        try publish(CapacityPilotBranch(name: name, visibleEditL1: edits.0, channelEditL1: edits.1,
                                        channelInventoryError: edits.2, frames: frames), emit)
    }

    private func runOriginal(_ initial: FlowLeniaInteractiveState, checkpointSteps: Int, horizon: Int,
                             probeShear: Double, probeSteps: Int, challengeShear: Double, writeDose: Double,
                             emit: (CapacityPilotBranch) throws -> Void) throws {
        let checkpoint = simulator.step(initial, count: checkpointSteps)
        let original = checkpoint.mass.asArray(Float.self)
        let centerX = try center(checkpoint, "checkpoint").x
        try store("checkpoint", floats: original)
        func write(_ mode: String) -> [Float] {
            capacityPilotWrite(original, width: width, height: height, channels: channelCount, centerX: centerX,
                               mode: mode, dose: writeDose)
        }
        let branches: [(String, [Float], Int)] = [
            ("sham", original, horizon),
            ("probe-positive", shear(original, centerX: centerX, amount: Float(probeShear)), probeSteps),
            ("probe-negative", shear(original, centerX: centerX, amount: -Float(probeShear)), probeSteps),
            ("challenge-positive", shear(original, centerX: centerX, amount: Float(challengeShear)), horizon),
            ("challenge-negative", shear(original, centerX: centerX, amount: -Float(challengeShear)), horizon),
            ("write-positive", write("positive"), horizon),
            ("write-negative", write("negative"), horizon),
            ("write-scrambled", write("scrambled"), horizon)
        ]
        for (name, values, steps) in branches {
            let (visible, edit, inventory) = editMetrics(original, values)
            guard inventory < 1e-6, !name.hasPrefix("write") || visible < 1e-6 else {
                throw NSError(domain: "CapacityPilot", code: 2,
                              userInfo: [NSLocalizedDescriptionKey: "Intervention invariant failed"])
            }
            var state = copied(checkpoint, values: values)
            var frames = [frame(state, relativeStep: 0)]
            for t in stride(from: 32, through: steps, by: 32) {
                state = simulator.step(state, count: 32)
                frames.append(frame(state, relativeStep: t))
            }
            try store("\(name)-final", floats: state.mass.asArray(Float.self))
            try publish(CapacityPilotBranch(name: name, visibleEditL1: visible,
                channelEditL1: edit, channelInventoryError: inventory, frames: frames), emit)
        }
    }

    private func runDevelopment(_ initial: FlowLeniaInteractiveState, horizon: Int, ancestry: CapacityPilotAncestry?,
                                emit: (CapacityPilotBranch) throws -> Void) throws {
        var state = initial
        var frames = [frame(state, relativeStep: 0)]
        try store("development-step-0", floats: state.mass.asArray(Float.self))
        recordPhantom(step: 0)
        var tracer: CapacityPilotAncestryTracer?
        if let ancestry {
            let mass = state.mass.asArray(Float.self)
            let founderMass: [Float]
            switch ancestry.seed {
            case .labels(let labels):
                founderMass = try capacityPilotFounderMass(mass, labels: labels, channels: channelCount,
                                                           founderCount: ancestry.founderCount)
            case .founderMass(let seeded):
                founderMass = try capacityPilotCheckedFounderMass(mass, founderMass: seeded, channels: channelCount,
                                                                  founderCount: ancestry.founderCount)
            }
            simulator.setAncestry(founderMass, founderCount: ancestry.founderCount, for: state)
            tracer = CapacityPilotAncestryTracer(ancestry: ancestry, width: width, height: height, channels: channelCount)
            try tracer!.record(state, simulator: simulator, store: store)
        }
        while state.step < horizon {
            // Founder totals are recorded every step; mass checkpoints keep the 32-step cadence.
            let advance = tracer == nil ? min(32, horizon - state.step) : 1
            state = simulator.step(state, count: advance)
            try tracer?.record(state, simulator: simulator, store: store)
            guard state.step % 32 == 0 || state.step == horizon else { continue }
            let values = state.mass.asArray(Float.self)
            guard values.allSatisfy({ $0.isFinite && $0 >= 0 }) else {
                throw NSError(domain: "CapacityPilot", code: 4,
                              userInfo: [NSLocalizedDescriptionKey: "Invalid development field"])
            }
            frames.append(frame(state, relativeStep: state.step))
            try store("development-step-\(state.step)", floats: values)
            recordPhantom(step: state.step)
        }
        if let tracer {
            try store("ancestry.json", capacityPilotJSON(tracer.finish()))
        }
        try publish(CapacityPilotBranch(name: "development", visibleEditL1: 0,
                                        channelEditL1: 0, channelInventoryError: 0, frames: frames), emit)
    }

    private func runAges(_ checkpoint: FlowLeniaInteractiveState, checkpointSteps: Int, horizon: Int, offsets: [Int],
                         probeShear: Double, probeSteps: Int, challengeShear: Double, saveFrames: Bool,
                         emit: (CapacityPilotBranch) throws -> Void) throws {
        precondition(offsets.first == 0 && offsets == offsets.sorted() && Set(offsets).count == offsets.count)
        var state = checkpoint
        var previousOffset = 0
        for offset in offsets {
            if offset > previousOffset { state = simulator.step(state, count: offset - previousOffset) }
            previousOffset = offset
            let values = state.mass.asArray(Float.self)
            let centerX = try center(state, "age \(checkpointSteps + offset)").x
            let prefix = "age-\(checkpointSteps + offset)"
            try store(prefix + "-checkpoint", floats: values)
            try continueBranch(state, values: values, name: prefix + "-sham", steps: horizon,
                               saveFrames: saveFrames, emit: emit)
            for (direction, sign): (String, Float) in [("positive", 1), ("negative", -1)] {
                for (kind, amount, steps) in [("probe", probeShear, probeSteps), ("challenge", challengeShear, horizon)] {
                    try continueBranch(state, values: shear(values, centerX: centerX, amount: sign * Float(amount)),
                                       name: prefix + "-" + kind + "-" + direction, steps: steps,
                                       saveFrames: saveFrames, emit: emit)
                }
            }
        }
    }

    private func runHistories(_ checkpoint: FlowLeniaInteractiveState, horizon: Int, challengeShear: Double,
                              writeDose: Double, waitSteps: Int, secondWriteStep: Int,
                              emit: (CapacityPilotBranch) throws -> Void) throws {
        let original = checkpoint.mass.asArray(Float.self)
        let centerX = try center(checkpoint, "checkpoint").x
        var events: [[String: Any]] = []
        for condition in CapacityPilotStudy.followupConditions {
            let mode = condition.hasPrefix("positive") ? "positive" : (condition.hasPrefix("scrambled") ? "scrambled" : condition)
            var values = mode == "sham" ? original : capacityPilotWrite(original, width: width, height: height,
                channels: channelCount, centerX: centerX, mode: mode, dose: writeDose)
            let first = editMetrics(original, values)
            guard first.0 < 1e-6, first.2 < 1e-6 else { throw NSError(domain: "CapacityPilot", code: 6) }
            events.append(["condition": condition, "step": 0, "visibleL1": first.0, "channelL1": first.1, "inventoryError": first.2])
            // Exact restoration is a handling control; a delayed opposite write is not an inverse.
            if condition == "positive-immediate-undo" { values = original }
            var state = copied(checkpoint, values: values)
            var waitFrames = [frame(state, relativeStep: 0)]
            for t in stride(from: 32, through: waitSteps, by: 32) {
                state = simulator.step(state, count: 32)
                if t == secondWriteStep && ["positive-then-negative", "scrambled-twice"].contains(condition) {
                    let before = state.mass.asArray(Float.self)
                    let x = try center(state, "\(condition) second write").x
                    let after = capacityPilotWrite(before, width: width, height: height, channels: channelCount, centerX: x,
                                                  mode: condition == "scrambled-twice" ? "scrambled" : "negative", dose: writeDose)
                    let edit = editMetrics(before, after)
                    guard edit.0 < 1e-6, edit.2 < 1e-6 else { throw NSError(domain: "CapacityPilot", code: 6) }
                    events.append(["condition": condition, "step": t, "visibleL1": edit.0, "channelL1": edit.1, "inventoryError": edit.2])
                    state = copied(state, values: after)
                }
                waitFrames.append(frame(state, relativeStep: t))
            }
            let prefix = "history-" + condition
            try publish(CapacityPilotBranch(name: prefix + "-wait", visibleEditL1: first.0, channelEditL1: first.1,
                                            channelInventoryError: first.2, frames: waitFrames), emit)
            let waiting = state.mass.asArray(Float.self)
            try store(prefix + "-checkpoint", floats: waiting)
            let x = try center(state, "\(condition) challenge").x
            try continueBranch(state, values: waiting, name: prefix + "-unchallenged", steps: horizon,
                               saveFrames: false, emit: emit)
            for (direction, sign): (String, Float) in [("positive", 1), ("negative", -1)] {
                try continueBranch(state, values: shear(waiting, centerX: x, amount: sign * Float(challengeShear)),
                                   name: prefix + "-challenge-" + direction, steps: horizon, saveFrames: false, emit: emit)
            }
        }
        try storeJSON("write-events.json", events)
    }

    private func runSymmetry(_ initial: FlowLeniaInteractiveState, checkpointSteps: Int, transformSteps: [Int]) throws {
        precondition(width == height)
        var rows: [[String: Any]] = []
        for age in [0, checkpointSteps] {
            let source = age == 0 ? initial : simulator.step(initial, count: age)
            let values = source.mass.asArray(Float.self)
            let total = values.reduce(0.0) { $0 + Double($1) }
            for transpose in [false, true] {
                let transformed = capacityPilotTransform(values, side: width, channels: channelCount, transpose: transpose)
                for steps in transformSteps {
                    let direct = simulator.step(copied(source, values: values), count: steps)
                    let other = simulator.step(copied(source, values: transformed), count: steps)
                    let expected = capacityPilotTransform(direct.mass.asArray(Float.self), side: width, channels: channelCount, transpose: transpose)
                    let actual = other.mass.asArray(Float.self)
                    let difference = zip(expected, actual).map { abs(Double($0) - Double($1)) }
                    rows.append(["age": age, "transform": transpose ? "transpose" : "quarter-turn", "steps": steps,
                                 "relativeL1": difference.reduce(0, +) / total, "maxAbs": difference.max()!])
                }
            }
        }
        try storeJSON("symmetry.json", rows)
    }

    private func runStateContinuation(_ initial: FlowLeniaInteractiveState, values: [Float], steps: Int,
                                      emit: (CapacityPilotBranch) throws -> Void) throws {
        try checkStateField(values)
        // In the clean autonomous runtime, fixed parameters and mass are the full
        // dynamical state. Relative step zero does not restart a time-dependent input.
        try continueBranch(initial, values: values, name: "continuation", steps: steps, saveFrames: true, emit: emit)
    }

    private func checkStateField(_ values: [Float]) throws {
        guard !simulator.runtimeConfig.parameterEmbedding.enabled,
              values.count == width * height * channelCount,
              values.allSatisfy({ $0.isFinite && $0 >= 0 }),
              values.contains(where: { $0 > 0 }) else {
            throw NSError(domain: "CapacityPilot", code: 7,
                          userInfo: [NSLocalizedDescriptionKey: "Restart requires a finite, nonempty mass field and fixed parameters"])
        }
    }

    private func runStateFlow(_ initial: FlowLeniaInteractiveState, values: [Float], steps: Int, savePotential: Bool) throws {
        try checkStateField(values)
        let k = simulator.kernels
        let spatial = MLXFFT.ifft2(k.fK, axes: [1, 2]).realPart()
        try store("kernels", floats: spatial.asArray(Float.self))
        let samples = Set([0, 1, 2, 4, 8, 16, 32, 64, 128, steps].filter { $0 <= steps })
        var state = copied(initial, values: values)
        for t in 0...steps {
            if samples.contains(t) {
                try store("mass-\(t)", floats: state.mass.asArray(Float.self))
                recordPhantom(step: t)
            }
            state = simulator.step(state, count: 1)
            if samples.contains(t) {
                if savePotential {
                    try store("potential-\(t)", floats: simulator.capacityPilotLastPotential())
                }
                try store("flow-\(t)", floats: simulator.capacityPilotLastFlow())
                try store("next-\(t)", floats: state.mass.asArray(Float.self))
            }
        }
        var metadata: [String: Any] = [
            "shape": [width, height, channelCount], "kernelShape": spatial.shape,
            "samples": samples.sorted(), "flowOrder": "x,y per channel; pre-step flow",
            "c0": k.c0Idxs.asArray(Int32.self).map { Int($0) },
            "c1Mask": k.c1Mask.asArray(Float.self), "m": k.m.asArray(Float.self),
            "s": k.s.asArray(Float.self), "h": k.h.asArray(Float.self)
        ]
        if savePotential {
            metadata["potentialOrder"] = "channel; pre-step growth potential including wall potential"
        }
        try storeJSON("state-flow.json", metadata)
    }

    private func runTransport(_ initial: FlowLeniaInteractiveState, checkpointSteps: Int, releaseSteps: Int,
                              horizon: Int, challengeShear: Double) throws {
        precondition(width >= 256 && height >= 256 && releaseSteps >= 0)
        var state = simulator.step(initial, count: checkpointSteps)
        let start = try center(state, "transport checkpoint")
        let x0 = min(max(Int(start.x) - 128, 0), width - 256)
        let y0 = min(max(Int(start.y) - 128, 0), height - 256)
        var observations: [[String: Any]] = []
        func save(_ values: [Float], stride: Int, name: String) throws {
            var crop: [Float] = []
            crop.reserveCapacity(256 * 256 * stride)
            for x in x0..<(x0 + 256) {
                let lower = (x * height + y0) * stride
                crop.append(contentsOf: values[lower..<(lower + 256 * stride)])
            }
            try store(name, floats: crop)
            if stride == channelCount {
                let total = values.reduce(0.0) { $0 + Double($1) }
                observations.append(["name": name, "mass": total,
                    "cropMass": crop.reduce(0.0) { $0 + Double($1) }])
            }
        }
        func follow(_ prefix: String, steps: Int) throws {
            try save(state.mass.asArray(Float.self), stride: channelCount, name: prefix + "-mass-0")
            for t in 0..<steps {
                state = simulator.step(state, count: 1)
                // The buffer records the pre-step flow actually used for this transport.
                try save(simulator.capacityPilotLastFlow(), stride: channelCount * 2, name: prefix + "-flow-\(t)")
                try save(state.mass.asArray(Float.self), stride: channelCount, name: prefix + "-mass-\(t + 1)")
            }
        }
        try follow("release", steps: releaseSteps)
        let centerX = try center(state, "transport challenge").x
        state = copied(state, values: shear(state.mass.asArray(Float.self), centerX: centerX, amount: Float(challengeShear)))
        try follow("challenge", steps: horizon)
        try storeJSON("transport.json", ["cropOrigin": [x0, y0], "cropSide": 256,
            "channels": channelCount, "flowOrder": "x,y per channel", "checkpointSteps": checkpointSteps,
            "releaseSteps": releaseSteps, "horizon": horizon, "shearCenterX": centerX,
            "shearAmount": challengeShear, "observations": observations] as [String: Any])
    }

    private func runWrite(_ initial: FlowLeniaInteractiveState, checkpointSteps: Int, edit: CapacityPilotEdit,
                          field: [Float], releaseSteps: Int, challenge: CapacityPilotChallenge?, replaceState: Bool,
                          emit: (CapacityPilotBranch) throws -> Void) throws {
        precondition(releaseSteps >= 0 && releaseSteps % 32 == 0)
        let checkpoint = simulator.step(initial, count: checkpointSteps)
        let original = checkpoint.mass.asArray(Float.self)
        let centerX = try center(checkpoint, "write checkpoint").x
        try store("prewrite", floats: original)
        let values: [Float]
        let isField: Bool
        switch edit {
        case .sham: values = original; isField = false
        case let .balanced(mode, dose):
            values = capacityPilotWrite(original, width: width, height: height, channels: channelCount,
                                        centerX: centerX, mode: mode, dose: dose)
            isField = false
        case .field: values = field; isField = true
        }
        guard values.count == original.count else {
            throw NSError(domain: "CapacityPilot", code: 6,
                          userInfo: [NSLocalizedDescriptionKey: "Write field must match the runtime dimensions"])
        }
        let edits = editMetrics(original, values)
        // Counterfactual state replacements may change density and channel inventory;
        // balanced writes retain both. Both studies retain total matter.
        let mass = original.reduce(0.0) { $0 + Double($1) }
        let replacementMass = values.reduce(0.0) { $0 + Double($1) }
        guard !replaceState || (isField && releaseSteps == 0),
              replaceState || (edits.0 < 1e-6 && edits.2 < 1e-6),
              mass > 0, abs(replacementMass / mass - 1) < 1e-6,
              values.allSatisfy({ $0.isFinite && $0 >= 0 }) else {
            throw NSError(domain: "CapacityPilot", code: 6, userInfo: [NSLocalizedDescriptionKey:
                "Write must keep total matter and, unless it replaces the state, density and channel inventories"])
        }
        var state = copied(checkpoint, values: values)
        var frames = [frame(state, relativeStep: 0)]
        try store("release-step-0", floats: values)
        for t in stride(from: 32, through: releaseSteps, by: 32) {
            state = simulator.step(state, count: 32)
            frames.append(frame(state, relativeStep: t))
            try store("release-step-\(t)", floats: state.mass.asArray(Float.self))
        }
        try publish(CapacityPilotBranch(name: "release", visibleEditL1: edits.0,
            channelEditL1: edits.1, channelInventoryError: edits.2, frames: frames), emit)
        guard let challenge else { return }
        let released = state.mass.asArray(Float.self)
        try store("challenge-checkpoint", floats: released)
        let releasedCenter = try center(state, "challenge checkpoint")
        try continueBranch(state, values: released, name: "unchallenged", steps: challenge.horizon,
                           saveFrames: true, emit: emit)
        let amount = Float(challenge.sign) * Float(challenge.shear)
        let challenged: [Float]
        if challenge.axis == "x" {
            challenged = capacityPilotShear(released, width: width, height: height,
                channels: channelCount, centerX: releasedCenter.x, amount: amount)
        } else {
            precondition(width == height)
            let transposed = capacityPilotTransform(released, side: width, channels: channelCount, transpose: true)
            let shifted = capacityPilotShear(transposed, width: width, height: height,
                channels: channelCount, centerX: releasedCenter.y, amount: amount)
            challenged = capacityPilotTransform(shifted, side: width, channels: channelCount, transpose: true)
        }
        try continueBranch(state, values: challenged, name: "challenge", steps: challenge.horizon,
                           saveFrames: true, emit: emit)
    }
}

private struct CapacityPilotAncestryTracer {
    let ancestry: CapacityPilotAncestry
    let width: Int
    let height: Int
    let channels: Int
    var steps: [Int] = []
    var founderMass: [[[Double]]] = []
    var channelMass: [[Double]] = []
    var residual: [Double] = []

    init(ancestry: CapacityPilotAncestry, width: Int, height: Int, channels: Int) {
        self.ancestry = ancestry
        self.width = width
        self.height = height
        self.channels = channels
    }

    mutating func record(_ state: FlowLeniaInteractiveState, simulator: FlowLeniaInteractiveSimulator,
                         store: (String, [Float]) throws -> Void) throws {
        let k = ancestry.founderCount
        let mass = state.mass.asArray(Float.self)
        let founders = simulator.ancestryFounderMass(for: state)
        var totals = [[Double]](repeating: [Double](repeating: 0, count: k), count: channels)
        var matter = [Double](repeating: 0, count: channels)
        var mismatch = 0.0
        for i in mass.indices {
            let c = i % channels
            var sum = 0.0
            for j in 0..<k {
                let value = Double(founders[i * k + j])
                totals[c][j] += value
                sum += value
            }
            matter[c] += Double(mass[i])
            mismatch += abs(sum - Double(mass[i]))
        }
        guard founders.allSatisfy({ $0.isFinite && $0 >= 0 }) else {
            throw NSError(domain: "CapacityPilot", code: 10,
                          userInfo: [NSLocalizedDescriptionKey: "Invalid founder mass at step \(state.step)"])
        }
        steps.append(state.step)
        founderMass.append(totals)
        channelMass.append(matter)
        residual.append(mismatch / matter.reduce(0, +))
        if ancestry.exportSteps.contains(state.step) {
            try store("ancestry-step-\(state.step)", founders)
        }
    }

    func finish() -> CapacityPilotAncestryRecord {
        CapacityPilotAncestryRecord(founders: ancestry.founderCount, channels: channels,
                                    fieldShape: [width, height, channels, ancestry.founderCount], steps: steps,
                                    founderMass: founderMass, channelMass: channelMass,
                                    founderSumResidual: residual, exportSteps: ancestry.exportSteps.sorted())
    }
}
