import AppKit
import SwiftUI
import LeniaCore

struct CreatureWorkbenchView: View {
    let entry: StudioCompareEntry
    @State private var showsInspector = true

    var body: some View {
        GeometryReader { proxy in
            Group {
                if showsInspector && proxy.size.width < 1_020 {
                    ScrollView {
                        VStack(spacing: 16) {
                            LeniaLiveView(
                                creature: entry.creature,
                                savedCreature: entry.savedCreature,
                                replaySource: entry.replayReference
                            )
                            .frame(minHeight: 360)

                            CreatureInspectorView(entry: entry)
                        }
                        .padding(16)
                    }
                } else {
                    HSplitView {
                        LeniaLiveView(
                            creature: entry.creature,
                            savedCreature: entry.savedCreature,
                            replaySource: entry.replayReference
                        )
                        .frame(minWidth: 420, minHeight: 360)
                        .layoutPriority(1)

                        if showsInspector {
                            CreatureInspectorView(entry: entry)
                                .frame(minWidth: 260, idealWidth: 320, maxWidth: 380)
                        }
                    }
                }
            }
        }
        .background(
            StudioSceneBackground()
        )
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button(showsInspector ? "Hide Inspector" : "Show Inspector") {
                    showsInspector.toggle()
                }
                .keyboardShortcut("i", modifiers: .command)
            }
        }
    }
}

struct CreatureInspectorView: View {
    @EnvironmentObject var node: LeniaNode
    let entry: StudioCompareEntry
    @State private var exportStatus: String?
    @State private var isExporting = false

    private var metrics: SimulationMetrics? {
        entry.savedCreature?.metrics ?? entry.metrics
    }

    private var displayScore: Float {
        entry.savedCreature?.score ?? entry.creature.score
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                StudioSurface(title: entry.name, subtitle: entry.subtitle) {
                    HStack(spacing: 10) {
                        StudioMetricPill(label: "Score", value: String(format: "%.3f", displayScore), accent: StudioPalette.ember)
                        StudioMetricPill(label: "Seed", value: "\(entry.creature.seed)")
                    }
                }

                if let metrics {
                    StudioSurface(title: "Metrics", subtitle: "Behavior and persistence") {
                        VStack(spacing: 8) {
                            StudioKeyValueRow(label: "Stable", value: metrics.isStable ? "Yes" : "No")
                            StudioKeyValueRow(label: "Gyration", value: String(format: "%.3f", metrics.gyration))
                            StudioKeyValueRow(label: "Velocity", value: String(format: "%.3f", metrics.centerVelocity))
                            StudioKeyValueRow(label: "Mass Mean", value: String(format: "%.3f", metrics.massMean))
                            StudioKeyValueRow(label: "Mass Std", value: String(format: "%.3f", metrics.massStd))
                            StudioKeyValueRow(label: "Occupancy", value: String(format: "%.3f", metrics.occupancyMean))
                            if let complexity = metrics.complexityMean {
                                StudioKeyValueRow(label: "Complexity", value: String(format: "%.3f", complexity))
                            }
                            if let survivalSteps = metrics.survivalSteps {
                                StudioKeyValueRow(label: "Survival", value: "\(survivalSteps)")
                            }
                        }
                    }
                }

                if let savedCreature = entry.savedCreature {
                    StudioSurface(title: "Score Breakdown", subtitle: "Weighted research signal") {
                        ScoreBreakdownView(creature: savedCreature)
                    }

                    StudioSurface(title: "Genotype", subtitle: "Parameters used to replay this creature") {
                        VStack(spacing: 8) {
                            StudioKeyValueRow(label: "R", value: String(format: "%.2f", savedCreature.genotype.R))
                            StudioKeyValueRow(label: "r", value: savedCreature.genotype.r.map { String(format: "%.2f", $0) }.joined(separator: ", "))
                            StudioKeyValueRow(label: "m", value: savedCreature.genotype.m.map { String(format: "%.2f", $0) }.joined(separator: ", "))
                            StudioKeyValueRow(label: "s", value: savedCreature.genotype.s.map { String(format: "%.3f", $0) }.joined(separator: ", "))
                            StudioKeyValueRow(label: "h", value: savedCreature.genotype.h.map { String(format: "%.2f", $0) }.joined(separator: ", "))
                        }
                    }

                    StudioSurface(title: "Provenance", subtitle: "Where this discovery came from") {
                        VStack(spacing: 8) {
                            StudioKeyValueRow(label: "Owner", value: savedCreature.ownerId)
                            StudioKeyValueRow(label: "Seed", value: "\(savedCreature.initialCondition.seed)")
                            StudioKeyValueRow(label: "Created", value: savedCreature.timestamp.formatted(date: .abbreviated, time: .shortened))
                            if let hash = savedCreature.configHash {
                                StudioKeyValueRow(label: "Config Hash", value: hash)
                            }
                        }
                    }
                } else {
                    StudioSurface(title: "Runtime", subtitle: "Live cluster snapshot") {
                        VStack(spacing: 8) {
                            StudioKeyValueRow(label: "Source", value: entry.creature.sourceNode)
                            StudioKeyValueRow(label: "Seed", value: "\(entry.creature.seed)")
                            StudioKeyValueRow(label: "Score", value: String(format: "%.3f", entry.creature.score))
                        }
                    }
                }

                StudioSurface(title: "Actions", subtitle: "Fast export and sharing") {
                    VStack(alignment: .leading, spacing: 10) {
                        if let savedCreature = entry.savedCreature {
                            HStack {
                                Button(isExporting ? "Exporting..." : "Export Config") {
                                    guard !isExporting else { return }
                                    isExporting = true
                                    exportStatus = nil
                                    Task {
                                        let path = await node.exportCreature(savedCreature)
                                        exportStatus = path.map { "Exported to \($0)" } ?? "Export failed"
                                        isExporting = false
                                    }
                                }
                                .buttonStyle(.borderedProminent)
                                .disabled(isExporting)

                                Button("Copy Config") {
                                    CreatureExport.copyConfigToClipboard(for: savedCreature)
                                }
                                .buttonStyle(.bordered)
                            }

                            Button("Save Config...") {
                                _ = CreatureExport.saveConfigToFile(for: savedCreature)
                            }
                            .buttonStyle(.bordered)
                            .keyboardShortcut("e", modifiers: .command)
                        }

                        Button("Copy Seed") {
                            let pasteboard = NSPasteboard.general
                            pasteboard.clearContents()
                            pasteboard.setString(String(entry.creature.seed), forType: .string)
                        }
                        .buttonStyle(.bordered)

                        if let exportStatus {
                            Text(exportStatus)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .padding(16)
        }
        .background(Color.clear)
    }
}
