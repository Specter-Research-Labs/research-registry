import Foundation
#if canImport(os)
import os
#endif

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

#if canImport(os)
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
#else
public enum LeniaSignposts {
    public struct Interval {}

    private static let mode: LeniaSignpostMode = {
        let mode = LeniaSignpostMode(envValue: ProcessInfo.processInfo.environment["LENIA_SIGNPOSTS"])
        guard mode == .off else {
            fatalError("LENIA_SIGNPOSTS requires os_signpost, which is only available on Apple platforms.")
        }
        return mode
    }()

    public static var phaseEnabled: Bool {
        mode.rawValue >= LeniaSignpostMode.phase.rawValue
    }

    public static var stepEnabled: Bool {
        mode.rawValue >= LeniaSignpostMode.step.rawValue
    }

    public static func beginPhase(_ name: StaticString, generation: Int? = nil) -> Interval? {
        guard phaseEnabled else { return nil }
        return Interval()
    }

    public static func beginStep(_ name: StaticString) -> Interval? {
        guard stepEnabled else { return nil }
        return Interval()
    }

    public static func end(_ interval: Interval?) {}
}
#endif
