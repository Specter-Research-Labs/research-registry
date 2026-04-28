import Foundation
import os

private enum LeniaSignpostMode: Int {
    case off = 0
    case phase = 1
    case step = 2

    init(envValue: String?) {
        switch envValue?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "1", "phase", "phases":
            self = .phase
        case "2", "step", "steps", "verbose":
            self = .step
        default:
            self = .off
        }
    }
}

public enum LeniaSignposts {
    public struct Interval {
        fileprivate let name: StaticString
        fileprivate let id: OSSignpostID
    }

    private static let mode = LeniaSignpostMode(
        envValue: ProcessInfo.processInfo.environment["LENIA_SIGNPOSTS"]
    )
    private static let log = OSLog(
        subsystem: "labs.specter.lenia-swarm",
        category: "PointsOfInterest"
    )

    public static var phaseEnabled: Bool {
        mode.rawValue >= LeniaSignpostMode.phase.rawValue
    }

    public static var stepEnabled: Bool {
        mode.rawValue >= LeniaSignpostMode.step.rawValue
    }

    public static func beginPhase(_ name: StaticString, generation: Int? = nil) -> Interval? {
        guard phaseEnabled else { return nil }
        return begin(name, generation: generation)
    }

    public static func beginStep(_ name: StaticString) -> Interval? {
        guard stepEnabled else { return nil }
        return begin(name, generation: nil)
    }

    public static func end(_ interval: Interval?) {
        guard let interval else { return }
        os_signpost(.end, log: log, name: interval.name, signpostID: interval.id)
    }

    private static func begin(_ name: StaticString, generation: Int?) -> Interval {
        let id = OSSignpostID(log: log)
        if let generation {
            os_signpost(.begin, log: log, name: name, signpostID: id, "gen=%d", generation)
        } else {
            os_signpost(.begin, log: log, name: name, signpostID: id)
        }
        return Interval(name: name, id: id)
    }
}
