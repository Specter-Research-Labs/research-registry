import Foundation
import LeniaCore
import SwiftUI

struct StudioComputationItem: Identifiable, Hashable {
    let id: String
    let label: String
    let value: String
    let unit: String?

    init(id: String, label: String, value: String, unit: String? = nil) {
        self.id = id
        self.label = label
        self.value = value
        self.unit = unit
    }
}

struct StudioComputationSection: Identifiable, Hashable {
    let id: String
    let title: String
    let items: [StudioComputationItem]
}

struct StudioMetricDiffRow: Identifiable, Hashable {
    let id: String
    let label: String
    let precision: Int
    let values: [Float?]

    func valueText(at index: Int) -> String {
        guard values.indices.contains(index) else { return "--" }
        return studioFormatNumber(values[index], precision: precision)
    }

    func deltaText(at index: Int) -> String {
        guard index > 0, values.indices.contains(index), let baseline = values.first.flatMap({ $0 }),
              let value = values[index] else {
            return index == 0 ? "baseline" : "--"
        }
        return studioFormatNumber(value - baseline, precision: precision, signed: true)
    }
}

func studioMetrics(for entry: StudioCompareEntry) -> SimulationMetrics? {
    entry.savedCreature?.metrics ?? entry.metrics
}

func studioTortuosity(metrics: SimulationMetrics) -> Float? {
    guard metrics.displacement > 1e-6 else { return nil }
    return metrics.pathLength / metrics.displacement
}

func studioMovementEfficiency(metrics: SimulationMetrics) -> Float? {
    guard metrics.pathLength > 1e-6 else { return nil }
    return metrics.displacement / metrics.pathLength
}

func studioFormatNumber(_ value: Float?, precision: Int, signed: Bool = false) -> String {
    guard let value, value.isFinite else { return "--" }
    let sign = signed ? "+" : ""
    return String(format: "%\(sign).\(precision)f", value)
}

func studioComputationSections(for metrics: SimulationMetrics) -> [StudioComputationSection] {
    [
        StudioComputationSection(
            id: "dynamics",
            title: "Dynamics",
            items: [
                StudioComputationItem(id: "stable", label: "Stable", value: metrics.isStable ? "yes" : "no"),
                StudioComputationItem(id: "mass-mean", label: "Mass mean", value: studioFormatNumber(metrics.massMean, precision: 3)),
                StudioComputationItem(id: "mass-std", label: "Mass std", value: studioFormatNumber(metrics.massStd, precision: 3)),
                StudioComputationItem(id: "occupancy", label: "Occupancy", value: studioFormatNumber(metrics.occupancyMean, precision: 3)),
                StudioComputationItem(id: "variance", label: "Variance", value: studioFormatNumber(metrics.varianceMean, precision: 3)),
                StudioComputationItem(id: "energy", label: "Energy", value: studioFormatNumber(metrics.energyMean, precision: 3)),
                StudioComputationItem(id: "samples", label: "Samples", value: "\(metrics.sampleCount)")
            ]
        ),
        StudioComputationSection(
            id: "motion",
            title: "Motion",
            items: [
                StudioComputationItem(id: "center-velocity", label: "Centroid speed", value: studioFormatNumber(metrics.centerVelocity, precision: 4)),
                StudioComputationItem(id: "speed-mean", label: "Mean speed", value: studioFormatNumber(metrics.speedMean, precision: 4)),
                StudioComputationItem(id: "velocity-vector", label: "Velocity vector", value: "\(studioFormatNumber(metrics.velocityX, precision: 3)), \(studioFormatNumber(metrics.velocityY, precision: 3))"),
                StudioComputationItem(id: "heading", label: "Heading", value: studioFormatNumber(metrics.headingRad, precision: 3), unit: "rad"),
                StudioComputationItem(id: "path", label: "Path", value: studioFormatNumber(metrics.pathLength, precision: 3)),
                StudioComputationItem(id: "displacement", label: "Displacement", value: studioFormatNumber(metrics.displacement, precision: 3)),
                StudioComputationItem(id: "tortuosity", label: "Tortuosity", value: studioFormatNumber(studioTortuosity(metrics: metrics), precision: 3)),
                StudioComputationItem(id: "efficiency", label: "Efficiency", value: studioFormatNumber(studioMovementEfficiency(metrics: metrics), precision: 3)),
                StudioComputationItem(id: "gyration", label: "Gyration", value: studioFormatNumber(metrics.gyration, precision: 3))
            ]
        ),
        StudioComputationSection(
            id: "structure",
            title: "Structure",
            items: [
                StudioComputationItem(id: "moment-mass", label: "Moment mass", value: studioFormatNumber(metrics.momentMass, precision: 3)),
                StudioComputationItem(id: "moment-volume", label: "Moment volume", value: studioFormatNumber(metrics.momentVolume, precision: 3)),
                StudioComputationItem(id: "moment-density", label: "Moment density", value: studioFormatNumber(metrics.momentDensity, precision: 3)),
                StudioComputationItem(id: "moment-anisotropy", label: "Moment anisotropy", value: studioFormatNumber(metrics.momentAnisotropy, precision: 3)),
                StudioComputationItem(id: "components", label: "Components", value: studioFormatNumber(metrics.componentCount, precision: 1)),
                StudioComputationItem(id: "largest-component", label: "Largest component", value: studioFormatNumber(metrics.largestComponentFraction, precision: 3)),
                StudioComputationItem(id: "hu1", label: "Hu 1", value: studioFormatNumber(metrics.hu1, precision: 4)),
                StudioComputationItem(id: "hu2", label: "Hu 2", value: studioFormatNumber(metrics.hu2, precision: 4)),
                StudioComputationItem(id: "flusser1", label: "Flusser 1", value: studioFormatNumber(metrics.flusser1, precision: 4)),
                StudioComputationItem(id: "flusser2", label: "Flusser 2", value: studioFormatNumber(metrics.flusser2, precision: 4))
            ].filter { $0.value != "--" }
        ),
        StudioComputationSection(
            id: "ecology",
            title: "Ecology",
            items: [
                StudioComputationItem(id: "complexity", label: "Complexity", value: studioFormatNumber(metrics.complexityMean, precision: 3)),
                StudioComputationItem(id: "target-score", label: "Target score", value: studioFormatNumber(metrics.complexityTargetScore, precision: 3)),
                StudioComputationItem(id: "activity-eac", label: "Activity EAC", value: studioFormatNumber(metrics.activityEacMean, precision: 3)),
                StudioComputationItem(id: "activity-ean", label: "Activity EAN", value: studioFormatNumber(metrics.activityEanMean, precision: 3)),
                StudioComputationItem(id: "activity-diversity", label: "Activity diversity", value: studioFormatNumber(metrics.activityDiversityMean, precision: 3)),
                StudioComputationItem(id: "activity-species", label: "Activity species", value: studioFormatNumber(metrics.activitySpeciesMean, precision: 3)),
                StudioComputationItem(id: "survival", label: "Survival", value: metrics.survivalSteps.map(String.init) ?? (metrics.survivalTracked ? "tracked" : "--")),
                StudioComputationItem(id: "food-consumed", label: "Food consumed", value: studioFormatNumber(metrics.foodConsumed, precision: 3)),
                StudioComputationItem(id: "food-final", label: "Food final", value: studioFormatNumber(metrics.foodFinalMass, precision: 3))
            ].filter { $0.value != "--" }
        )
    ].filter { !$0.items.isEmpty }
}

func studioMetricDiffRows(for entries: [StudioCompareEntry]) -> [StudioMetricDiffRow] {
    let metrics = entries.map(studioMetrics)
    guard metrics.contains(where: { $0 != nil }) else { return [] }

    func values(_ keyPath: KeyPath<SimulationMetrics, Float>) -> [Float?] {
        metrics.map { $0?[keyPath: keyPath] }
    }

    func optionalValues(_ keyPath: KeyPath<SimulationMetrics, Float?>) -> [Float?] {
        metrics.map { $0?[keyPath: keyPath] ?? nil }
    }

    func derived(_ transform: (SimulationMetrics) -> Float?) -> [Float?] {
        metrics.map { metric in
            guard let metric else { return nil }
            return transform(metric)
        }
    }

    return [
        StudioMetricDiffRow(id: "score", label: "Score", precision: 4, values: entries.map { $0.savedCreature?.score ?? $0.creature.score }),
        StudioMetricDiffRow(id: "mass", label: "Mass mean", precision: 3, values: values(\.massMean)),
        StudioMetricDiffRow(id: "mass-std", label: "Mass std", precision: 3, values: values(\.massStd)),
        StudioMetricDiffRow(id: "occupancy", label: "Occupancy", precision: 3, values: values(\.occupancyMean)),
        StudioMetricDiffRow(id: "energy", label: "Energy", precision: 3, values: values(\.energyMean)),
        StudioMetricDiffRow(id: "velocity", label: "Centroid speed", precision: 4, values: values(\.centerVelocity)),
        StudioMetricDiffRow(id: "path", label: "Path", precision: 3, values: values(\.pathLength)),
        StudioMetricDiffRow(id: "displacement", label: "Displacement", precision: 3, values: values(\.displacement)),
        StudioMetricDiffRow(id: "tortuosity", label: "Tortuosity", precision: 3, values: derived(studioTortuosity)),
        StudioMetricDiffRow(id: "gyration", label: "Gyration", precision: 3, values: values(\.gyration)),
        StudioMetricDiffRow(id: "complexity", label: "Complexity", precision: 3, values: optionalValues(\.complexityMean)),
        StudioMetricDiffRow(id: "components", label: "Components", precision: 1, values: optionalValues(\.componentCount)),
        StudioMetricDiffRow(id: "largest-component", label: "Largest component", precision: 3, values: optionalValues(\.largestComponentFraction)),
        StudioMetricDiffRow(id: "food-consumed", label: "Food consumed", precision: 3, values: optionalValues(\.foodConsumed))
    ]
}

struct StudioClassificationPanel: View {
    let entry: StudioCompareEntry

    private var taxonomy: SpecimenTaxonomyRecord? {
        entry.taxonomy
    }

    private var classValue: String {
        firstClean(entry.runtimeFamily, entry.replayReference?.runtimeFamily) ?? "Flow Lenia"
    }

    private var orderValue: String {
        let parts = [entry.sourceMode, entry.sourceAlgorithm]
            .compactMap(cleanLabel)
        return parts.isEmpty ? "--" : parts.joined(separator: " / ")
    }

    private var taxonomyStatus: String {
        if let taxonomy, taxonomyHasValue(taxonomy) {
            return firstClean(taxonomy.method, taxonomy.version.map { "v\($0)" }) ?? "assigned"
        }
        return "pending"
    }

    var body: some View {
        StudioSurface(title: "Classification", subtitle: "Flow-Lenia specimen context") {
            VStack(alignment: .leading, spacing: 12) {
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], alignment: .leading, spacing: 8) {
                    StudioClassificationCell(label: "Class", value: classValue)
                    StudioClassificationCell(label: "Order", value: orderValue)
                    StudioClassificationCell(label: "Family", value: cleanLabel(taxonomy?.familyID) ?? "Pending")
                    StudioClassificationCell(label: "Genus", value: cleanLabel(taxonomy?.genusID) ?? "Pending")
                    StudioClassificationCell(label: "Species", value: cleanLabel(taxonomy?.speciesID) ?? "Pending")
                    StudioClassificationCell(label: "Taxonomy", value: taxonomyStatus)
                }

                HStack(spacing: 8) {
                    if let confidence = taxonomy?.confidence {
                        StudioMetricPill(
                            label: "Confidence",
                            value: String(format: "%.2f", confidence),
                            accent: confidence >= 0.7 ? StudioPalette.moss : StudioPalette.ember
                        )
                    }
                    if !entry.runtimeCapabilities.isEmpty {
                        StudioMetricPill(
                            label: "Runtime",
                            value: "\(entry.runtimeCapabilities.count) caps",
                            accent: StudioPalette.ocean
                        )
                    }
                    Spacer()
                }

                if !entry.traitLabels.isEmpty {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 64), spacing: 6)], alignment: .leading, spacing: 6) {
                        ForEach(entry.traitLabels.prefix(8), id: \.self) { label in
                            StudioTag(text: label)
                        }
                    }
                }
            }
        }
    }
}

struct StudioComputationPanel: View {
    let metrics: SimulationMetrics

    private var sections: [StudioComputationSection] {
        studioComputationSections(for: metrics)
    }

    var body: some View {
        StudioSurface(title: "Computations", subtitle: "Rollout, moment, motion, and ecology signals") {
            VStack(alignment: .leading, spacing: 14) {
                ForEach(sections) { section in
                    StudioComputationSectionView(section: section)
                    if section.id != sections.last?.id {
                        Divider()
                    }
                }
            }
        }
    }
}

private struct StudioClassificationCell: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label.uppercased())
                .font(.system(size: 9, weight: .semibold, design: .monospaced))
                .foregroundStyle(StudioPalette.mutedInk)
            Text(value)
                .font(.system(.callout, design: .monospaced, weight: .semibold))
                .foregroundStyle(StudioPalette.ink)
                .lineLimit(1)
                .minimumScaleFactor(0.72)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct StudioComputationSectionView: View {
    let section: StudioComputationSection

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(section.title.uppercased())
                .font(.system(size: 10, weight: .semibold, design: .monospaced))
                .foregroundStyle(StudioPalette.mutedInk)

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], alignment: .leading, spacing: 7) {
                ForEach(section.items) { item in
                    StudioKeyValueRow(
                        label: item.label,
                        value: item.unit.map { "\(item.value) \($0)" } ?? item.value
                    )
                }
            }
        }
    }
}

private struct StudioTag: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.caption2)
            .foregroundStyle(StudioPalette.ink)
            .lineLimit(1)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(
                Capsule(style: .continuous)
                    .fill(StudioPalette.surfaceSoft)
            )
            .overlay(
                Capsule(style: .continuous)
                    .stroke(StudioPalette.hairline, lineWidth: 1)
            )
    }
}

private func cleanLabel(_ value: String?) -> String? {
    guard let value else { return nil }
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
}

private func firstClean(_ values: String?...) -> String? {
    values.lazy.compactMap(cleanLabel).first
}

private func taxonomyHasValue(_ taxonomy: SpecimenTaxonomyRecord) -> Bool {
    firstClean(taxonomy.familyID, taxonomy.genusID, taxonomy.speciesID, taxonomy.method) != nil ||
        taxonomy.confidence != nil ||
        taxonomy.version != nil
}
