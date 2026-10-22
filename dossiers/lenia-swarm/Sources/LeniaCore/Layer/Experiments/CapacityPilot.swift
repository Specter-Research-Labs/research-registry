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

public final class CapacityPilotHarness {
    private let simulator: FlowLeniaInteractiveSimulator
    private let width: Int
    private let height: Int
    private let channelCount: Int
    private let hasPhantom: Bool
    private var phantomFrames: [[String: Any]] = []

    public init(config: LeniaRuntimeConfig, phantom: FlowLeniaPhantomSpec? = nil) {
        precondition(config.channels >= 1)
        simulator = FlowLeniaInteractiveSimulator(runtimeConfig: config, phantom: phantom)
        width = config.sx
        height = config.sy
        channelCount = config.channels
        hasPhantom = phantom != nil
    }

    private func recordPhantom(step: Int) {
        guard hasPhantom else { return }
        let digest = simulator.phantomField().withUnsafeBytes { SHA256.hash(data: $0) }
        phantomFrames.append(["step": step, "sha256": digest.map { String(format: "%02x", $0) }.joined()])
    }

    private func writePhantomFrames(output: URL) throws {
        guard hasPhantom else { return }
        try JSONSerialization.data(withJSONObject: phantomFrames, options: [.sortedKeys, .prettyPrinted])
            .write(to: output.appendingPathComponent("phantom-frames.json"))
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
            centerX: body?.center.x, centerY: body?.center.y, image: image)
    }

    public func run(checkpointSteps: Int, horizon: Int, output: URL,
                    emit: (CapacityPilotBranch) throws -> Void) throws {
        let checkpoint = simulator.step(simulator.makeInitialState(), count: checkpointSteps)
        let original = checkpoint.mass.asArray(Float.self)
        let checkpointFrame = frame(checkpoint, relativeStep: 0)
        guard let centerX = checkpointFrame.centerX else {
            throw NSError(domain: "CapacityPilot", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "No thresholded body at checkpoint"])
        }
        try original.withUnsafeBytes { try Data($0).write(to: output.appendingPathComponent("checkpoint.f32")) }
        let branches: [(String, [Float], Int)] = [
            ("sham", original, horizon),
            ("probe-positive", capacityPilotShear(original, width: width, height: height, channels: channelCount, centerX: centerX, amount: 0.10), 128),
            ("probe-negative", capacityPilotShear(original, width: width, height: height, channels: channelCount, centerX: centerX, amount: -0.10), 128),
            ("challenge-positive", capacityPilotShear(original, width: width, height: height, channels: channelCount, centerX: centerX, amount: 0.30), horizon),
            ("challenge-negative", capacityPilotShear(original, width: width, height: height, channels: channelCount, centerX: centerX, amount: -0.30), horizon),
            ("write-positive", capacityPilotWrite(original, width: width, height: height, channels: channelCount, centerX: centerX, mode: "positive", dose: 0.04), horizon),
            ("write-negative", capacityPilotWrite(original, width: width, height: height, channels: channelCount, centerX: centerX, mode: "negative", dose: 0.04), horizon),
            ("write-scrambled", capacityPilotWrite(original, width: width, height: height, channels: channelCount, centerX: centerX, mode: "scrambled", dose: 0.04), horizon)
        ]
        for (name, values, steps) in branches {
            let (visible, edit, inventory) = editMetrics(original, values)
            guard inventory < 1e-6, !name.hasPrefix("write") || visible < 1e-6 else {
                throw NSError(domain: "CapacityPilot", code: 2,
                              userInfo: [NSLocalizedDescriptionKey: "Intervention invariant failed"])
            }
            var state = FlowLeniaInteractiveState(step: checkpoint.step,
                mass: MLXArray(values, checkpoint.mass.shape), params: checkpoint.params, food: checkpoint.food)
            var frames = [frame(state, relativeStep: 0)]
            for t in stride(from: 32, through: steps, by: 32) {
                state = simulator.step(state, count: 32)
                frames.append(frame(state, relativeStep: t))
            }
            try state.mass.asArray(Float.self).withUnsafeBytes {
                try Data($0).write(to: output.appendingPathComponent("\(name)-final.f32"))
            }
            try emit(CapacityPilotBranch(name: name, visibleEditL1: visible,
                channelEditL1: edit, channelInventoryError: inventory, frames: frames))
        }
        let replay = simulator.step(FlowLeniaInteractiveState(step: checkpoint.step,
            mass: MLXArray(original, checkpoint.mass.shape), params: checkpoint.params, food: checkpoint.food), count: 32)
        let replayValues = replay.mass.asArray(Float.self)
        let second = simulator.step(FlowLeniaInteractiveState(step: checkpoint.step,
            mass: MLXArray(original, checkpoint.mass.shape), params: checkpoint.params, food: checkpoint.food), count: 32)
        let error = zip(replayValues, second.mass.asArray(Float.self)).map { abs($0 - $1) }.max() ?? 0
        guard error < 1e-6 else { throw NSError(domain: "CapacityPilot", code: 3) }
        try Data("{\"repeat_max_abs_error\":\(error)}\n".utf8).write(to: output.appendingPathComponent("replay-check.json"))
    }
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

extension CapacityPilotHarness {
    private func copied(_ state: FlowLeniaInteractiveState, values: [Float]) -> FlowLeniaInteractiveState {
        FlowLeniaInteractiveState(step: state.step, mass: MLXArray(values, state.mass.shape),
                                 params: state.params, food: state.food)
    }

    private func saveField(_ state: FlowLeniaInteractiveState, name: String, output: URL) throws {
        let values = state.mass.asArray(Float.self)
        try values.withUnsafeBytes { try Data($0).write(to: output.appendingPathComponent(name + ".f32")) }
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

    private func continueBranch(_ source: FlowLeniaInteractiveState, values: [Float], name: String,
                                steps: Int, output: URL, saveFrames: Bool = false,
                                emit: (CapacityPilotBranch) throws -> Void) throws {
        let original = source.mass.asArray(Float.self)
        let edits = editMetrics(original, values)
        var state = copied(source, values: values)
        var frames = [frame(state, relativeStep: 0)]
        let mass = frames[0].mass
        let conservesMatter = simulator.runtimeConfig.implementation.mode != "qd24_additive_v1"
        if saveFrames { try saveField(state, name: name + "-step-0", output: output) }
        for t in stride(from: 32, through: steps, by: 32) {
            state = simulator.step(state, count: 32)
            let f = frame(state, relativeStep: t)
            let field = state.mass.asArray(Float.self)
            guard field.allSatisfy({ $0.isFinite && $0 >= 0 }),
                  !conservesMatter || abs(f.mass / mass - 1) < 0.001 else {
                throw NSError(domain: "CapacityPilot", code: 4, userInfo: [NSLocalizedDescriptionKey: "Invalid continuation: \(name), step \(t)"])
            }
            frames.append(f)
            if saveFrames { try saveField(state, name: name + "-step-\(t)", output: output) }
        }
        try saveField(state, name: name + "-final", output: output)
        try emit(CapacityPilotBranch(name: name, visibleEditL1: edits.0, channelEditL1: edits.1,
                                    channelInventoryError: edits.2, frames: frames))
    }

    public func runDevelopment(horizon: Int, output: URL, ancestry: CapacityPilotAncestry? = nil,
                               emit: (CapacityPilotBranch) throws -> Void) throws {
        var state = simulator.makeInitialState()
        var frames = [frame(state, relativeStep: 0)]
        try saveField(state, name: "development-step-0", output: output)
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
            try tracer!.record(state, simulator: simulator, output: output)
        }
        while state.step < horizon {
            // Founder totals are recorded every step; mass checkpoints keep the 32-step cadence.
            let advance = tracer == nil ? min(32, horizon - state.step) : 1
            state = simulator.step(state, count: advance)
            try tracer?.record(state, simulator: simulator, output: output)
            guard state.step % 32 == 0 || state.step == horizon else { continue }
            let values = state.mass.asArray(Float.self)
            guard values.allSatisfy({ $0.isFinite && $0 >= 0 }) else {
                throw NSError(domain: "CapacityPilot", code: 4,
                              userInfo: [NSLocalizedDescriptionKey: "Invalid development field"])
            }
            frames.append(frame(state, relativeStep: state.step))
            try saveField(state, name: "development-step-\(state.step)", output: output)
            recordPhantom(step: state.step)
        }
        try writePhantomFrames(output: output)
        if let tracer {
            try JSONEncoder().encode(tracer.finish()).write(to: output.appendingPathComponent("ancestry.json"))
        }
        try emit(CapacityPilotBranch(name: "development", visibleEditL1: 0,
                                    channelEditL1: 0, channelInventoryError: 0, frames: frames))
    }

    public func runResponse(checkpointSteps: Int, horizon: Int, output: URL,
                            offsets: [Int] = [0, 128, 256], probeHorizon: Int = 128,
                            emit: (CapacityPilotBranch) throws -> Void) throws {
        precondition(offsets.first == 0 && offsets == offsets.sorted() && Set(offsets).count == offsets.count)
        precondition(offsets.allSatisfy { $0 >= 0 && $0 % 32 == 0 })
        precondition(probeHorizon >= 128 && probeHorizon % 32 == 0)
        var state = simulator.step(simulator.makeInitialState(), count: checkpointSteps)
        var previousOffset = 0
        for offset in offsets {
            if offset > previousOffset { state = simulator.step(state, count: offset - previousOffset) }
            previousOffset = offset
            let values = state.mass.asArray(Float.self)
            guard let center = frame(state, relativeStep: 0).centerX else {
                throw NSError(domain: "CapacityPilot", code: 5,
                              userInfo: [NSLocalizedDescriptionKey: "No body at response checkpoint"])
            }
            let prefix = "age-\(checkpointSteps + offset)"
            try saveField(state, name: prefix + "-checkpoint", output: output)
            try continueBranch(state, values: values, name: prefix + "-sham", steps: horizon,
                               output: output, saveFrames: true, emit: emit)
            for (direction, sign): (String, Float) in [("positive", 1), ("negative", -1)] {
                for (kind, dose, steps): (String, Float, Int) in [("probe", 0.1, probeHorizon), ("challenge", 0.3, horizon)] {
                    let edited = capacityPilotShear(values, width: width, height: height, channels: channelCount,
                                                    centerX: center, amount: sign * dose,
                                                    periodic: simulator.runtimeConfig.border == "torus")
                    try continueBranch(state, values: edited, name: prefix + "-" + kind + "-" + direction,
                                       steps: steps, output: output, saveFrames: true, emit: emit)
                }
            }
        }
    }

    public func runSymmetry(checkpointSteps: Int, output: URL) throws {
        precondition(width == height)
        let initial = simulator.makeInitialState()
        var rows: [[String: Any]] = []
        for age in [0, checkpointSteps] {
            let source = age == 0 ? initial : simulator.step(initial, count: age)
            let values = source.mass.asArray(Float.self)
            let total = values.reduce(0.0) { $0 + Double($1) }
            for transpose in [false, true] {
                let transformed = capacityPilotTransform(values, side: width, channels: channelCount, transpose: transpose)
                for steps in [1, 8, 32] {
                    let direct = simulator.step(copied(source, values: values), count: steps)
                    let other = simulator.step(copied(source, values: transformed), count: steps)
                    let expected = capacityPilotTransform(direct.mass.asArray(Float.self), side: width, channels: channelCount, transpose: transpose)
                    let actual = other.mass.asArray(Float.self)
                    let difference = zip(expected, actual).map { abs(Double($0) - Double($1)) }
                    rows.append(["age": age, "transform": transpose ? "transpose" : "quarter-turn", "steps": steps,
                                 "relativeL1": difference.reduce(0, +) / total, "maxAbs": difference.max() ?? 0])
                }
            }
        }
        try JSONSerialization.data(withJSONObject: rows, options: [.sortedKeys, .prettyPrinted])
            .write(to: output.appendingPathComponent("symmetry.json"))
    }

    public func runStateContinuation(values: [Float], steps: Int, output: URL,
                                     emit: (CapacityPilotBranch) throws -> Void) throws {
        guard !simulator.runtimeConfig.parameterEmbedding.enabled,
              values.count == width * height * channelCount,
              values.allSatisfy({ $0.isFinite && $0 >= 0 }),
              values.contains(where: { $0 > 0 }) else {
            throw NSError(domain: "CapacityPilot", code: 7,
                          userInfo: [NSLocalizedDescriptionKey: "Restart requires a finite, nonempty mass field and fixed parameters"])
        }
        // In the clean autonomous runtime, fixed parameters and mass are the full
        // dynamical state. Relative step zero does not restart a time-dependent input.
        let source = simulator.makeInitialState()
        try continueBranch(source, values: values, name: "continuation", steps: steps,
                           output: output, saveFrames: true, emit: emit)
    }

    public func runStateFlow(values: [Float], steps: Int, output: URL, savePotential: Bool) throws {
        precondition(!simulator.runtimeConfig.parameterEmbedding.enabled)
        guard values.count == width * height * channelCount,
              values.allSatisfy({ $0.isFinite && $0 >= 0 }), values.contains(where: { $0 > 0 }) else {
            throw NSError(domain: "CapacityPilot", code: 8,
                          userInfo: [NSLocalizedDescriptionKey: "Flow tracing requires a finite, nonempty mass field"])
        }
        func save(_ values: [Float], _ name: String) throws {
            try values.withUnsafeBytes { try Data($0).write(to: output.appendingPathComponent(name + ".f32")) }
        }
        let k = simulator.kernels
        let spatial = MLXFFT.ifft2(k.fK, axes: [1, 2]).realPart()
        try save(spatial.asArray(Float.self), "kernels")
        let samples = Set([0, 1, 2, 4, 8, 16, 32, 64, 128, steps])
        var state = copied(simulator.makeInitialState(), values: values)
        for t in 0...steps {
            if samples.contains(t) {
                try save(state.mass.asArray(Float.self), "mass-\(t)")
                recordPhantom(step: t)
            }
            state = simulator.step(state, count: 1)
            if samples.contains(t) {
                if savePotential {
                    try save(simulator.capacityPilotLastPotential(), "potential-\(t)")
                }
                try save(simulator.capacityPilotLastFlow(), "flow-\(t)")
                try save(state.mass.asArray(Float.self), "next-\(t)")
            }
        }
        try writePhantomFrames(output: output)
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
        try JSONSerialization.data(withJSONObject: metadata, options: [.sortedKeys, .prettyPrinted])
            .write(to: output.appendingPathComponent("state-flow.json"))
    }

    public func runTransport(checkpointSteps: Int, releaseSteps: Int, horizon: Int, output: URL) throws {
        precondition(width >= 256 && height >= 256 && releaseSteps >= 0)
        var state = simulator.step(simulator.makeInitialState(), count: checkpointSteps)
        let start = frame(state, relativeStep: 0)
        let x0 = min(max(Int(start.centerX!) - 128, 0), width - 256)
        let y0 = min(max(Int(start.centerY!) - 128, 0), height - 256)
        var observations: [[String: Any]] = []
        func save(_ values: [Float], stride: Int, name: String) throws {
            var crop: [Float] = []
            crop.reserveCapacity(256 * 256 * stride)
            for x in x0..<(x0 + 256) {
                let lower = (x * height + y0) * stride
                crop.append(contentsOf: values[lower..<(lower + 256 * stride)])
            }
            try crop.withUnsafeBytes { try Data($0).write(to: output.appendingPathComponent(name + ".f32")) }
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
        let center = frame(state, relativeStep: 0).centerX!
        let values = capacityPilotShear(state.mass.asArray(Float.self), width: width, height: height,
            channels: channelCount, centerX: center, amount: 0.3)
        state = copied(state, values: values)
        try follow("challenge", steps: horizon)
        try JSONSerialization.data(withJSONObject: ["cropOrigin": [x0, y0], "cropSide": 256,
            "channels": channelCount, "flowOrder": "x,y per channel", "checkpointSteps": checkpointSteps,
            "releaseSteps": releaseSteps, "horizon": horizon, "shearCenterX": center,
            "shearAmount": 0.3, "observations": observations], options: [.prettyPrinted, .sortedKeys])
            .write(to: output.appendingPathComponent("transport.json"))
    }

    public func runWriteResponse(checkpointSteps: Int, horizon: Int, output: URL,
                                 mode: String, dose: Double, releaseSteps: Int, challengeSign: Int,
                                 challengeAxis: String, replaceState: Bool = false, releaseOnly: Bool = false, writeField: [Float]?,
                                 emit: (CapacityPilotBranch) throws -> Void) throws {
        precondition(["sham", "positive", "negative", "scrambled", "field"].contains(mode))
        precondition((mode == "field") == (writeField != nil) && ["x", "y"].contains(challengeAxis))
        precondition(dose >= 0 && dose < 1 && releaseSteps >= 0 && releaseSteps % 32 == 0)
        precondition(challengeSign == -1 || challengeSign == 1)
        let checkpoint = simulator.step(simulator.makeInitialState(), count: checkpointSteps)
        let original = checkpoint.mass.asArray(Float.self)
        guard let center = frame(checkpoint, relativeStep: 0).centerX else {
            throw NSError(domain: "CapacityPilot", code: 5)
        }
        try saveField(checkpoint, name: "prewrite", output: output)
        let values = writeField ?? (mode == "sham" ? original : capacityPilotWrite(original, width: width,
            height: height, channels: channelCount, centerX: center, mode: mode, dose: dose))
        guard values.count == original.count else { throw NSError(domain: "CapacityPilot", code: 6) }
        let edits = editMetrics(original, values)
        // Counterfactual state replacements may change density and channel inventory;
        // balanced writes retain both. Both studies retain total matter.
        let mass = original.reduce(0.0) { $0 + Double($1) }
        let replacementMass = values.reduce(0.0) { $0 + Double($1) }
        guard !replaceState || (mode == "field" && releaseSteps == 0),
              replaceState || (edits.0 < 1e-6 && edits.2 < 1e-6),
              mass > 0, abs(replacementMass / mass - 1) < 1e-6,
              values.allSatisfy({ $0.isFinite && $0 >= 0 }) else {
            throw NSError(domain: "CapacityPilot", code: 6)
        }
        var state = copied(checkpoint, values: values)
        var frames = [frame(state, relativeStep: 0)]
        try saveField(state, name: "release-step-0", output: output)
        if releaseSteps > 0 {
            for t in stride(from: 32, through: releaseSteps, by: 32) {
                state = simulator.step(state, count: 32)
                frames.append(frame(state, relativeStep: t))
                try saveField(state, name: "release-step-\(t)", output: output)
            }
        }
        try emit(CapacityPilotBranch(name: "release", visibleEditL1: edits.0,
            channelEditL1: edits.1, channelInventoryError: edits.2, frames: frames))
        if releaseOnly { return }
        try saveField(state, name: "challenge-checkpoint", output: output)
        let released = state.mass.asArray(Float.self)
        guard let x = frame(state, relativeStep: 0).centerX else {
            throw NSError(domain: "CapacityPilot", code: 5)
        }
        try continueBranch(state, values: released, name: "unchallenged", steps: horizon,
                           output: output, saveFrames: true, emit: emit)
        let challenged: [Float]
        if challengeAxis == "x" {
            challenged = capacityPilotShear(released, width: width, height: height,
                channels: channelCount, centerX: x, amount: Float(challengeSign) * 0.3)
        } else {
            precondition(width == height)
            let y = frame(state, relativeStep: 0).centerY!
            let transposed = capacityPilotTransform(released, side: width, channels: channelCount, transpose: true)
            let shifted = capacityPilotShear(transposed, width: width, height: height,
                channels: channelCount, centerX: y, amount: Float(challengeSign) * 0.3)
            challenged = capacityPilotTransform(shifted, side: width, channels: channelCount, transpose: true)
        }
        try continueBranch(state, values: challenged, name: "challenge", steps: horizon,
                           output: output, saveFrames: true, emit: emit)
    }

    public func runFollowup(checkpointSteps: Int, horizon: Int, output: URL,
                           emit: (CapacityPilotBranch) throws -> Void) throws {
        let checkpoint = simulator.step(simulator.makeInitialState(), count: checkpointSteps)
        var ageState = checkpoint
        for offset in [0, 128, 256] {
            if offset > 0 { ageState = simulator.step(ageState, count: 128) }
            let values = ageState.mass.asArray(Float.self)
            guard let center = frame(ageState, relativeStep: 0).centerX else { throw NSError(domain: "CapacityPilot", code: 5) }
            let prefix = "age-\(checkpointSteps + offset)"
            try saveField(ageState, name: prefix + "-checkpoint", output: output)
            try continueBranch(ageState, values: values, name: prefix + "-sham", steps: horizon, output: output, emit: emit)
            for (direction, sign): (String, Float) in [("positive", 1), ("negative", -1)] {
                for (kind, dose, steps): (String, Float, Int) in [("probe", 0.1, 128), ("challenge", 0.3, horizon)] {
                    let edited = capacityPilotShear(values, width: width, height: height, channels: channelCount, centerX: center, amount: sign * dose)
                    try continueBranch(ageState, values: edited, name: prefix + "-" + kind + "-" + direction,
                                       steps: steps, output: output, emit: emit)
                }
            }
        }
        let original = checkpoint.mass.asArray(Float.self)
        guard let center = frame(checkpoint, relativeStep: 0).centerX else { throw NSError(domain: "CapacityPilot", code: 5) }
        var events: [[String: Any]] = []
        for condition in ["sham", "positive", "negative", "scrambled", "positive-immediate-undo", "positive-then-negative", "scrambled-twice"] {
            let mode = condition.hasPrefix("positive") ? "positive" : (condition.hasPrefix("scrambled") ? "scrambled" : condition)
            var values = mode == "sham" ? original : capacityPilotWrite(original, width: width, height: height, channels: channelCount, centerX: center, mode: mode, dose: 0.04)
            let first = editMetrics(original, values)
            guard first.0 < 1e-6, first.2 < 1e-6 else { throw NSError(domain: "CapacityPilot", code: 6) }
            events.append(["condition": condition, "step": 0, "visibleL1": first.0, "channelL1": first.1, "inventoryError": first.2])
            // Exact restoration is a handling control; a delayed opposite write is not an inverse.
            if condition == "positive-immediate-undo" { values = original }
            var state = copied(checkpoint, values: values)
            var waitFrames = [frame(state, relativeStep: 0)]
            for t in stride(from: 32, through: 256, by: 32) {
                state = simulator.step(state, count: 32)
                if t == 128 && ["positive-then-negative", "scrambled-twice"].contains(condition) {
                    let before = state.mass.asArray(Float.self)
                    guard let x = frame(state, relativeStep: t).centerX else { throw NSError(domain: "CapacityPilot", code: 5) }
                    let after = capacityPilotWrite(before, width: width, height: height, channels: channelCount, centerX: x,
                                                  mode: condition == "scrambled-twice" ? "scrambled" : "negative", dose: 0.04)
                    let edit = editMetrics(before, after)
                    guard edit.0 < 1e-6, edit.2 < 1e-6 else { throw NSError(domain: "CapacityPilot", code: 6) }
                    events.append(["condition": condition, "step": t, "visibleL1": edit.0, "channelL1": edit.1, "inventoryError": edit.2])
                    state = copied(state, values: after)
                }
                waitFrames.append(frame(state, relativeStep: t))
            }
            let prefix = "history-" + condition
            try emit(CapacityPilotBranch(name: prefix + "-wait", visibleEditL1: first.0, channelEditL1: first.1,
                                        channelInventoryError: first.2, frames: waitFrames))
            try saveField(state, name: prefix + "-checkpoint", output: output)
            let waiting = state.mass.asArray(Float.self)
            guard let x = frame(state, relativeStep: 0).centerX else { throw NSError(domain: "CapacityPilot", code: 5) }
            try continueBranch(state, values: waiting, name: prefix + "-unchallenged", steps: horizon, output: output, emit: emit)
            for (direction, sign): (String, Float) in [("positive", 1), ("negative", -1)] {
                let edited = capacityPilotShear(waiting, width: width, height: height, channels: channelCount, centerX: x, amount: sign * 0.3)
                try continueBranch(state, values: edited, name: prefix + "-challenge-" + direction,
                                   steps: horizon, output: output, emit: emit)
            }
        }
        try JSONSerialization.data(withJSONObject: events, options: [.sortedKeys, .prettyPrinted])
            .write(to: output.appendingPathComponent("write-events.json"))
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
                         output: URL) throws {
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
            try founders.withUnsafeBytes {
                try Data($0).write(to: output.appendingPathComponent("ancestry-step-\(state.step).f32"))
            }
        }
    }

    func finish() -> CapacityPilotAncestryRecord {
        CapacityPilotAncestryRecord(founders: ancestry.founderCount, channels: channels,
                                    fieldShape: [width, height, channels, ancestry.founderCount], steps: steps,
                                    founderMass: founderMass, channelMass: channelMass,
                                    founderSumResidual: residual, exportSteps: ancestry.exportSteps.sorted())
    }
}
