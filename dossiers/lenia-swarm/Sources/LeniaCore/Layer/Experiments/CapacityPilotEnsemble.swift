import Crypto
import Foundation

/// Member 0 is the unperturbed trajectory. Member m >= 1 moves `cells` distinct positive entries of
/// the starting mass field one ulp up or down, drawn from a SplitMix64 stream seeded by
/// mix(seed ^ mix(m)), where mix is the SplitMix64 finalizer. Each draw picks an entry with
/// multiply-high reduction (bias below count / 2^64) and redraws duplicates; one further draw's low
/// bit picks nextUp (1) or nextDown (0). Positive entries only, so no entry turns negative or
/// becomes newly occupied.
public struct CapacityPilotPerturbation: Sendable {
    public let seed: UInt64
    public let member: Int
    public let cells: Int

    public init(seed: UInt64, member: Int, cells: Int) {
        precondition(member >= 0 && cells >= 1)
        self.seed = seed
        self.member = member
        self.cells = cells
    }

    public struct Entry: Codable, Equatable {
        public let index: Int
        public let direction: String
    }

    public struct Record: Codable {
        public let member: Int
        public let seed: UInt64
        public let cells: Int
        public let entries: [Entry]
        public let startSha256: String
    }

    public func apply(_ values: [Float]) throws -> (values: [Float], record: Record) {
        var result = values
        var entries: [Entry] = []
        if member > 0 {
            let positive = values.indices.filter { values[$0] > 0 }
            guard positive.count >= cells else {
                throw NSError(domain: "CapacityPilot", code: 11, userInfo: [NSLocalizedDescriptionKey:
                    "Perturbation needs \(cells) positive entries, the starting field has \(positive.count)"])
            }
            var state = Self.mix(seed ^ Self.mix(UInt64(member)))
            func next() -> UInt64 {
                state &+= 0x9E37_79B9_7F4A_7C15
                return Self.mix(state)
            }
            var chosen = Set<Int>()
            while entries.count < cells {
                let index = positive[Int(next().multipliedFullWidth(by: UInt64(positive.count)).high)]
                guard chosen.insert(index).inserted else { continue }
                let up = next() & 1 == 1
                result[index] = up ? values[index].nextUp : values[index].nextDown
                entries.append(Entry(index: index, direction: up ? "up" : "down"))
            }
        }
        let digest = result.withUnsafeBytes { SHA256.hash(data: $0) }.map { String(format: "%02x", $0) }.joined()
        return (result, Record(member: member, seed: seed, cells: cells, entries: entries, startSha256: digest))
    }

    static func mix(_ value: UInt64) -> UInt64 {
        var z = value
        z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
        z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
        return z ^ (z >> 31)
    }
}

public let capacityPilotWilsonZ = 1.959963984540054

/// The 95% Wilson score interval for `successes` of `trials`.
public func capacityPilotWilson(successes: Int, trials: Int) -> [Double] {
    precondition(trials > 0 && (0...trials).contains(successes))
    let z = capacityPilotWilsonZ, n = Double(trials), k = Double(successes)
    let center = (k + z * z / 2) / (n + z * z)
    let half = z * (k * (n - k) / n + z * z / 4).squareRoot() / (n + z * z)
    // Rounding puts the exact bounds 0 (at k = 0) and 1 (at k = n) a few ulps outside [0, 1].
    return [max(0, center - half), min(1, center + half)]
}

public struct CapacityPilotVarianceSplit: Encodable, Equatable {
    public let values: Int
    public let total: Double
    public let acrossMember: Double
    public let acrossCondition: Double
}

/// One-way decomposition of population variance: total = mean within-condition squared deviation
/// (across members, the chaotic part) + count-weighted squared deviation of condition means (across
/// conditions, the intervention part). Groups may differ in size; empty groups contribute nothing.
public func capacityPilotVarianceSplit(_ groups: [[Double]]) -> CapacityPilotVarianceSplit? {
    let all = groups.flatMap { $0 }
    guard !all.isEmpty else { return nil }
    let n = Double(all.count)
    let mean = all.reduce(0, +) / n
    var within = 0.0, between = 0.0
    for group in groups where !group.isEmpty {
        let groupMean = group.reduce(0, +) / Double(group.count)
        within += group.reduce(0) { $0 + ($1 - groupMean) * ($1 - groupMean) }
        between += Double(group.count) * (groupMean - mean) * (groupMean - mean)
    }
    let total = all.reduce(0) { $0 + ($1 - mean) * ($1 - mean) }
    return CapacityPilotVarianceSplit(values: all.count, total: total / n, acrossMember: within / n, acrossCondition: between / n)
}

public enum CapacityPilotMeasure: String, CaseIterable, Sendable {
    /// Summed displacement of the largest body's center between consecutive frames, in cells.
    case centroidPath = "centroid_path"
    /// The centroid path divided by the body's declared diameter.
    case centroidPathDiameters = "centroid_path_diameters"
    /// The smallest largest-body mass fraction over the window's frames.
    case minCoherence = "min_coherence"
}

public struct CapacityPilotContinuousOutcome: Sendable {
    public let name: String
    public let measure: CapacityPilotMeasure
    public let branches: [String]
    public let fromStep: Int
    public let toStep: Int

    public init(name: String, measure: CapacityPilotMeasure, branches: [String], fromStep: Int, toStep: Int) {
        self.name = name
        self.measure = measure
        self.branches = branches
        self.fromStep = fromStep
        self.toStep = toStep
    }

    /// Nil when a window frame has no thresholded body, so the measure is undefined for that member.
    public func evaluate(_ frames: [CapacityPilotFrame], diameter: Double?, width: Int, height: Int, periodic: Bool) -> Double? {
        let window = frames.filter { (fromStep...toStep).contains($0.step) }
        precondition(window.first?.step == fromStep && window.last?.step == toStep && window.count >= 2,
                     "Outcome \(name) window \(fromStep)...\(toStep) is not covered by frames")
        switch measure {
        case .minCoherence:
            let values = window.map(\.coherence)
            guard values.allSatisfy({ $0 != nil }) else { return nil }
            return Double(values.map { $0! }.min()!)
        case .centroidPath, .centroidPathDiameters:
            var path = 0.0
            for (a, b) in zip(window, window.dropFirst()) {
                guard let ax = a.centerX, let ay = a.centerY, let bx = b.centerX, let by = b.centerY else { return nil }
                let dx = periodic ? periodicDelta(bx - ax, period: Float(width)) : bx - ax
                let dy = periodic ? periodicDelta(by - ay, period: Float(height)) : by - ay
                path += (Double(dx) * Double(dx) + Double(dy) * Double(dy)).squareRoot()
            }
            if measure == .centroidPath { return path }
            return path / diameter!
        }
    }
}

public struct CapacityPilotBinaryOutcome: Sendable {
    public enum Comparison: String, Sendable {
        case atLeast = ">="
        case atMost = "<="
    }

    public struct Condition: Sendable {
        public let outcome: String
        public let comparison: Comparison
        public let value: Double

        public init(outcome: String, comparison: Comparison, value: Double) {
            self.outcome = outcome
            self.comparison = comparison
            self.value = value
        }
    }

    public let name: String
    public let all: [Condition]

    public init(name: String, all: [Condition]) {
        self.name = name
        self.all = all
    }

    /// Nil when any referenced continuous outcome is undefined for the member.
    public func evaluate(_ continuous: [String: Double?]) -> Bool? {
        var holds = true
        for condition in all {
            guard let value = continuous[condition.outcome]! else { return nil }
            holds = holds && (condition.comparison == .atLeast ? value >= condition.value : value <= condition.value)
        }
        return holds
    }
}

public struct CapacityPilotMemberOutcome: Encodable {
    public let member: Int
    public let continuous: [String: Double?]
    public let binary: [String: Bool?]
}

public struct CapacityPilotProbability: Encodable {
    public let successes: Int
    public let defined: Int
    public let undefined: Int
    public let probability: Double?
    public let wilson95: [Double]?

    public init(_ outcomes: [Bool?]) {
        let defined = outcomes.compactMap { $0 }
        successes = defined.filter { $0 }.count
        self.defined = defined.count
        undefined = outcomes.count - defined.count
        probability = defined.isEmpty ? nil : Double(successes) / Double(defined.count)
        wilson95 = defined.isEmpty ? nil : capacityPilotWilson(successes: successes, trials: defined.count)
    }

    enum CodingKeys: String, CodingKey { case successes, defined, undefined, probability, wilson95 }

    /// Writes an explicit null when no member is defined, so every condition has the same keys.
    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(successes, forKey: .successes)
        try container.encode(defined, forKey: .defined)
        try container.encode(undefined, forKey: .undefined)
        try container.encode(probability, forKey: .probability)
        try container.encode(wilson95, forKey: .wilson95)
    }
}

public struct CapacityPilotCondition: Encodable {
    public let body: String
    public let branch: String
    public let probabilities: [String: CapacityPilotProbability]
    public let members: [CapacityPilotMemberOutcome]
}

public struct CapacityPilotRepeatSummary: Encodable {
    public let backend: String
    public let members: Int
    public let compared: Int
    public let matched: Int
    public let matchRate: Double
    /// "body/member-m/output" for every output whose re-run hash differed or was missing.
    public let mismatches: [String]

    public init(backend: String, members: Int, compared: Int, matched: Int, mismatches: [String]) {
        precondition(compared > 0)
        self.backend = backend
        self.members = members
        self.compared = compared
        self.matched = matched
        self.matchRate = Double(matched) / Double(compared)
        self.mismatches = mismatches
    }
}

public struct CapacityPilotEnsembleSummary: Encodable {
    public let designSha256: String
    public let members: Int
    public let perturbedCells: Int
    public let perturbationSeed: UInt64
    public let wilsonZ: Double
    public let conditions: [CapacityPilotCondition]
    public let variance: [String: CapacityPilotVarianceSplit?]
    public let repeatCheck: CapacityPilotRepeatSummary

    public init(designSha256: String, members: Int, perturbedCells: Int, perturbationSeed: UInt64, wilsonZ: Double,
                conditions: [CapacityPilotCondition], variance: [String: CapacityPilotVarianceSplit?],
                repeatCheck: CapacityPilotRepeatSummary) {
        self.designSha256 = designSha256
        self.members = members
        self.perturbedCells = perturbedCells
        self.perturbationSeed = perturbationSeed
        self.wilsonZ = wilsonZ
        self.conditions = conditions
        self.variance = variance
        self.repeatCheck = repeatCheck
    }
}

/// Member trajectories of one body, keyed by branch name, as the ensemble aggregation reads them.
public struct CapacityPilotBodyMembers {
    public let body: String
    public let diameter: Double?
    public let members: [[String: [CapacityPilotFrame]]]

    public init(body: String, diameter: Double?, members: [[String: [CapacityPilotFrame]]]) {
        self.body = body
        self.diameter = diameter
        self.members = members
    }
}

public func capacityPilotConditions(
    bodies: [CapacityPilotBodyMembers],
    continuous: [CapacityPilotContinuousOutcome],
    binary: [CapacityPilotBinaryOutcome],
    width: Int, height: Int, periodic: Bool
) -> [CapacityPilotCondition] {
    var conditions: [CapacityPilotCondition] = []
    let branches = Array(Set(continuous.flatMap(\.branches))).sorted()
    for body in bodies {
        for branch in branches {
            let applicable = continuous.filter { $0.branches.contains(branch) }
            let names = Set(applicable.map(\.name))
            let binaries = binary.filter { $0.all.allSatisfy { names.contains($0.outcome) } }
            let members = body.members.enumerated().map { index, trajectories -> CapacityPilotMemberOutcome in
                let frames = trajectories[branch]!
                var values: [String: Double?] = [:]
                for outcome in applicable {
                    values[outcome.name] = outcome.evaluate(frames, diameter: body.diameter, width: width, height: height, periodic: periodic)
                }
                var verdicts: [String: Bool?] = [:]
                for outcome in binaries { verdicts[outcome.name] = outcome.evaluate(values) }
                return CapacityPilotMemberOutcome(member: index, continuous: values, binary: verdicts)
            }
            var probabilities: [String: CapacityPilotProbability] = [:]
            for outcome in binaries {
                probabilities[outcome.name] = CapacityPilotProbability(members.map { $0.binary[outcome.name]! })
            }
            conditions.append(CapacityPilotCondition(body: body.body, branch: branch, probabilities: probabilities, members: members))
        }
    }
    return conditions
}

public func capacityPilotVariance(conditions: [CapacityPilotCondition],
                                  continuous: [CapacityPilotContinuousOutcome]) -> [String: CapacityPilotVarianceSplit?] {
    var result: [String: CapacityPilotVarianceSplit?] = [:]
    for outcome in continuous {
        let groups = conditions.filter { outcome.branches.contains($0.branch) }.map { condition in
            condition.members.compactMap { $0.continuous[outcome.name]! }
        }
        result[outcome.name] = capacityPilotVarianceSplit(groups)
    }
    return result
}
