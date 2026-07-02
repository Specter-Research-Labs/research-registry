import Foundation

/// Unwrap a measurement metric that a configured fitness term depends on. A nil
/// means the term was requested in config but its metric was never computed —
/// a configuration error, not a runtime condition. Centralizes the contract
/// that was previously copy-pasted as a `guard … else { fatalError }` at every
/// penalty/reward site.
func requireMetric(_ value: Float?, requestedBy term: String) -> Float {
    guard let value else {
        fatalError("\(term) requested but its metric was not computed.")
    }
    return value
}

/// Clamp to [0, 1]; non-finite collapses to 0.
func unitInterval(_ value: Float) -> Float {
    guard value.isFinite else { return 0.0 }
    return max(0.0, min(1.0, value))
}

/// Mass-stability factor: peaks at 1 when occupied growth is 1 (mass-conserving)
/// and decays with the log-deviation from 1. Non-finite / non-positive growth
/// collapses to 0.
func bodyLocomotionGrowthTerm(_ value: Float) -> Float {
    guard value.isFinite, value > 0 else { return 0.0 }
    let deviation = abs(log(value))
    return 1.0 / (1.0 + 2.0 * deviation)
}

/// Specter-internal body-locomotion screening heuristic (not paper-defined):
/// reward coherent, mass-stable, morphologically-organism-like displacement.
/// Single source of truth shared by the ES fitness path (CandidateMeasurement)
/// and the post-hoc scoring path (SimulationMetrics) so the persisted score and
/// any recomputation cannot drift.
func bodyLocomotionScore(
    displacement: Float,
    translatedShapeOverlap: Float,
    occupiedGrowth: Float,
    largestComponentFraction: Float,
    largestComponentSolidity: Float,
    largestComponentAnisotropy: Float,
    largestComponentFilamentarity: Float
) -> Float {
    let overlapTerm = 0.2 + 0.8 * unitInterval(translatedShapeOverlap)
    let growthTerm = bodyLocomotionGrowthTerm(occupiedGrowth)
    let connectedTerm = 0.25 + 0.75 * unitInterval(largestComponentFraction)
    let solidityTerm = 0.35 + 0.65 * unitInterval(largestComponentSolidity)
    let anisotropyTerm = 0.35 + 0.65 * (1.0 - unitInterval(largestComponentAnisotropy))
    let filamentTerm = 0.35 + 0.65 * (1.0 - unitInterval(largestComponentFilamentarity))
    let morphologyTerm = (connectedTerm + solidityTerm + anisotropyTerm + filamentTerm) / 4.0
    return max(displacement, 0.0) * overlapTerm * growthTerm * morphologyTerm
}
