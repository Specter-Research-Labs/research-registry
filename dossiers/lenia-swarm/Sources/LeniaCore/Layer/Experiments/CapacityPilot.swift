import Foundation
import MLX

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

// Pair equal and opposite transfers so every cell retains its total matter and
// the two channel inventories stay fixed. The dose counts both channel edits.
public func capacityPilotWrite(_ values: [Float], width: Int, height: Int,
                               centerX: Float, mode: String, dose: Double) -> [Float] {
    precondition(values.count == width * height * 2 && dose >= 0 && dose < 1)
    precondition(["positive", "negative", "scrambled"].contains(mode))
    let total = values.reduce(0.0) { $0 + Double($1) }
    var positive = [Bool](repeating: false, count: width * height)
    var plus = 0.0, minus = 0.0
    for i in positive.indices {
        let x = i / height
        let hashed = (UInt64(i) &* 2654435761) ^ (UInt64(i) >> 3)
        positive[i] = mode == "scrambled" ? (hashed % 2 == 0) :
            (mode == "positive" ? Float(x) >= centerX : Float(x) < centerX)
        if positive[i] { plus += Double(values[2 * i + 1]) }
        else { minus += Double(values[2 * i]) }
    }
    let amount = min(total * dose / 4, min(plus, minus) * 0.95)
    guard amount > 0 else { return values }
    var result = values
    for i in positive.indices {
        let a = Double(values[2 * i]), b = Double(values[2 * i + 1])
        let delta = positive[i] ? amount * b / plus : -amount * a / minus
        result[2 * i] = Float(a + delta)
        result[2 * i + 1] = Float(b - delta)
    }
    return result
}

public func capacityPilotShear(_ values: [Float], width: Int, height: Int,
                               centerX: Float, amount: Float) -> [Float] {
    precondition(values.count == width * height * 2)
    var result = values
    for x in 0..<width {
        let shift = Int((amount * (Float(x) - centerX)).rounded())
        for y in 0..<height {
            let destinationY = ((y + shift) % height + height) % height
            for channel in 0..<2 {
                result[(x * height + destinationY) * 2 + channel] = values[(x * height + y) * 2 + channel]
            }
        }
    }
    return result
}

public final class CapacityPilotHarness {
    private let simulator: FlowLeniaInteractiveSimulator
    private let width: Int
    private let height: Int

    public init(config: LeniaRuntimeConfig) {
        precondition(config.channels == 2)
        simulator = FlowLeniaInteractiveSimulator(runtimeConfig: config)
        width = config.sx
        height = config.sy
    }

    private func frame(_ state: FlowLeniaInteractiveState, relativeStep: Int) -> CapacityPilotFrame {
        let channels = state.mass.asArray(Float.self)
        let values = stride(from: 0, to: channels.count, by: 2).map { channels[$0] + channels[$0 + 1] }
        let body = unseenObstacleLargestBody(values: values, width: width, height: height,
                                             threshold: 0.01, periodic: false)
        var image = [Float](repeating: 0, count: 128 * 128)
        for x in 0..<width {
            for y in 0..<height {
                image[(y * 128 / height) * 128 + x * 128 / width] += values[x * height + y]
            }
        }
        return CapacityPilotFrame(step: relativeStep,
            mass: channels.reduce(0.0) { $0 + Double($1) },
            channel0: stride(from: 0, to: channels.count, by: 2).reduce(0.0) { $0 + Double(channels[$1]) },
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
        let total = checkpointFrame.mass
        let branches: [(String, [Float], Int)] = [
            ("sham", original, horizon),
            ("probe-positive", capacityPilotShear(original, width: width, height: height, centerX: centerX, amount: 0.10), 128),
            ("probe-negative", capacityPilotShear(original, width: width, height: height, centerX: centerX, amount: -0.10), 128),
            ("challenge-positive", capacityPilotShear(original, width: width, height: height, centerX: centerX, amount: 0.30), horizon),
            ("challenge-negative", capacityPilotShear(original, width: width, height: height, centerX: centerX, amount: -0.30), horizon),
            ("write-positive", capacityPilotWrite(original, width: width, height: height, centerX: centerX, mode: "positive", dose: 0.04), horizon),
            ("write-negative", capacityPilotWrite(original, width: width, height: height, centerX: centerX, mode: "negative", dose: 0.04), horizon),
            ("write-scrambled", capacityPilotWrite(original, width: width, height: height, centerX: centerX, mode: "scrambled", dose: 0.04), horizon)
        ]
        for (name, values, steps) in branches {
            var visible = 0.0, edit = 0.0, channelDifference = 0.0
            for i in stride(from: 0, to: values.count, by: 2) {
                visible += abs(Double(values[i] + values[i + 1]) - Double(original[i] + original[i + 1]))
                edit += abs(Double(values[i]) - Double(original[i])) + abs(Double(values[i + 1]) - Double(original[i + 1]))
                channelDifference += Double(values[i]) - Double(original[i])
            }
            guard abs(channelDifference) / total < 1e-6,
                  !name.hasPrefix("write") || visible / total < 1e-6 else {
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
            try emit(CapacityPilotBranch(name: name, visibleEditL1: visible / total,
                channelEditL1: edit / total, channelInventoryError: abs(channelDifference) / total, frames: frames))
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

public func capacityPilotTransform(_ values: [Float], side: Int, transpose: Bool) -> [Float] {
    precondition(values.count == side * side * 2)
    var result = values
    for x in 0..<side {
        for y in 0..<side {
            let tx = transpose ? y : side - 1 - y
            let ty = x
            for c in 0..<2 { result[(tx * side + ty) * 2 + c] = values[(x * side + y) * 2 + c] }
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
        var visible = 0.0, edit = 0.0, inventory = 0.0
        for i in stride(from: 0, to: values.count, by: 2) {
            visible += abs(Double(values[i] + values[i + 1]) - Double(original[i] + original[i + 1]))
            edit += abs(Double(values[i]) - Double(original[i])) + abs(Double(values[i + 1]) - Double(original[i + 1]))
            inventory += Double(values[i]) - Double(original[i])
        }
        return (visible / total, edit / total, abs(inventory) / total)
    }

    private func continueBranch(_ source: FlowLeniaInteractiveState, values: [Float], name: String,
                                steps: Int, output: URL, emit: (CapacityPilotBranch) throws -> Void) throws {
        let original = source.mass.asArray(Float.self)
        let edits = editMetrics(original, values)
        var state = copied(source, values: values)
        var frames = [frame(state, relativeStep: 0)]
        let mass = frames[0].mass
        for t in stride(from: 32, through: steps, by: 32) {
            state = simulator.step(state, count: 32)
            let f = frame(state, relativeStep: t)
            let field = state.mass.asArray(Float.self)
            guard field.allSatisfy({ $0.isFinite && $0 >= 0 }), abs(f.mass / mass - 1) < 0.001 else {
                throw NSError(domain: "CapacityPilot", code: 4, userInfo: [NSLocalizedDescriptionKey: "Invalid continuation: \(name), step \(t)"])
            }
            frames.append(f)
        }
        try saveField(state, name: name + "-final", output: output)
        try emit(CapacityPilotBranch(name: name, visibleEditL1: edits.0, channelEditL1: edits.1,
                                    channelInventoryError: edits.2, frames: frames))
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
                let transformed = capacityPilotTransform(values, side: width, transpose: transpose)
                for steps in [1, 8, 32] {
                    let direct = simulator.step(copied(source, values: values), count: steps)
                    let other = simulator.step(copied(source, values: transformed), count: steps)
                    let expected = capacityPilotTransform(direct.mass.asArray(Float.self), side: width, transpose: transpose)
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
                    let edited = capacityPilotShear(values, width: width, height: height, centerX: center, amount: sign * dose)
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
            var values = mode == "sham" ? original : capacityPilotWrite(original, width: width, height: height, centerX: center, mode: mode, dose: 0.04)
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
                    let after = capacityPilotWrite(before, width: width, height: height, centerX: x,
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
                let edited = capacityPilotShear(waiting, width: width, height: height, centerX: x, amount: sign * 0.3)
                try continueBranch(state, values: edited, name: prefix + "-challenge-" + direction,
                                   steps: horizon, output: output, emit: emit)
            }
        }
        try JSONSerialization.data(withJSONObject: events, options: [.sortedKeys, .prettyPrinted])
            .write(to: output.appendingPathComponent("write-events.json"))
    }
}
