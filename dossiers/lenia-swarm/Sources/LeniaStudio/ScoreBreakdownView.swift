import SwiftUI
import LeniaCore

struct ScoreBreakdownView: View {
    let creature: SavedCreature

    var body: some View {
        let rows = scoreRows(for: creature)
        if rows.isEmpty {
            Text("Score breakdown unavailable")
                .font(.caption)
                .foregroundStyle(.secondary)
        } else {
            let computedTotal = rows.reduce(0) { $0 + $1.contribution }
            MetricRow(
                label: "Total",
                value: String(format: "%.4f", creature.score ?? computedTotal)
            )
            ForEach(rows) { row in
                MetricRow(
                    label: prettyMetricName(row.key),
                    value: String(format: "%+.4f", row.contribution)
                )
            }
        }
    }

    private func scoreRows(for creature: SavedCreature) -> [ScoreRow] {
        guard let weights = creature.scoreWeights, !weights.isEmpty else {
            return []
        }

        var rows: [ScoreRow] = []
        rows.reserveCapacity(weights.count)

        for (key, weight) in weights {
            guard let value = metricValue(for: key, creature: creature) else { continue }
            rows.append(ScoreRow(
                key: key,
                weight: weight,
                value: value,
                contribution: weight * value
            ))
        }

        return rows.sorted { abs($0.contribution) > abs($1.contribution) }
    }

    private func metricValue(for key: String, creature: SavedCreature) -> Float? {
        switch key {
        case "mass_mean": return creature.metrics.massMean
        case "mass_std": return creature.metrics.massStd
        case "mass_min": return creature.metrics.massMin
        case "mass_max": return creature.metrics.massMax
        case "occupancy_mean": return creature.metrics.occupancyMean
        case "variance_mean": return creature.metrics.varianceMean
        case "energy_mean": return creature.metrics.energyMean
        case "speed_mean": return creature.metrics.speedMean
        case "path_length": return creature.metrics.pathLength
        case "displacement": return creature.metrics.displacement
        case "gyration": return creature.metrics.gyration
        case "center_velocity": return creature.metrics.centerVelocity
        case "complexity_mean": return creature.metrics.complexityMean
        case "complexity_target_score": return creature.metrics.complexityTargetScore
        default: return nil
        }
    }

    private func prettyMetricName(_ key: String) -> String {
        key.replacingOccurrences(of: "_", with: " ").capitalized
    }
}

private struct ScoreRow: Identifiable {
    let key: String
    let weight: Float
    let value: Float
    let contribution: Float

    var id: String { key }
}
