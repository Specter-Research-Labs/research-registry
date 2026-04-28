import Foundation

public struct Morphometrics: Codable, Sendable {
    public let version: Int

    public let pathTortuosity: Float?
    public let movementEfficiency: Float?

    public let activitySpeciesMax: Int?
    public let activitySpeciesStd: Float?
    public let activityDiversityStd: Float?
    public let activityEacMax: Float?
    public let activityEanMax: Float?

    public static func from(metrics: SimulationMetrics, activity: ActivitySummary?) -> Morphometrics {
        let eps: Float = 1e-6
        let tortuosity: Float? = metrics.displacement > eps ? (metrics.pathLength / metrics.displacement) : nil
        let efficiency: Float? = metrics.pathLength > eps ? (metrics.displacement / metrics.pathLength) : nil

        let activityDerived = activity.map(Self.activityDerived) ?? ActivityDerived()

        return Morphometrics(
            version: 1,
            pathTortuosity: tortuosity,
            movementEfficiency: efficiency,
            activitySpeciesMax: activityDerived.speciesMax,
            activitySpeciesStd: activityDerived.speciesStd,
            activityDiversityStd: activityDerived.diversityStd,
            activityEacMax: activityDerived.eacMax,
            activityEanMax: activityDerived.eanMax
        )
    }

    public func with(activity: ActivitySummary) -> Morphometrics {
        let derived = Self.activityDerived(activity)
        return Morphometrics(
            version: version,
            pathTortuosity: pathTortuosity,
            movementEfficiency: movementEfficiency,
            activitySpeciesMax: derived.speciesMax,
            activitySpeciesStd: derived.speciesStd,
            activityDiversityStd: derived.diversityStd,
            activityEacMax: derived.eacMax,
            activityEanMax: derived.eanMax
        )
    }

    private struct ActivityDerived: Sendable {
        var speciesMax: Int? = nil
        var speciesStd: Float? = nil
        var diversityStd: Float? = nil
        var eacMax: Float? = nil
        var eanMax: Float? = nil
    }

    private static func activityDerived(_ activity: ActivitySummary) -> ActivityDerived {
        var derived = ActivityDerived()
        derived.speciesMax = activity.speciesCount.max()
        derived.speciesStd = std(activity.speciesCount.map(Float.init))
        derived.diversityStd = std(activity.diversity)
        derived.eacMax = activity.eac.max()
        derived.eanMax = activity.ean.max()
        return derived
    }

    private static func std(_ values: [Float]) -> Float? {
        guard !values.isEmpty else { return nil }
        if values.count == 1 { return 0 }
        let mean = values.reduce(0, +) / Float(values.count)
        var sumSq: Float = 0
        for v in values {
            let d = v - mean
            sumSq += d * d
        }
        return sqrt(sumSq / Float(values.count))
    }
}
