import SwiftUI
import LeniaCore

struct HostDashboardView: View {
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var node: LeniaNode

    var body: some View {
        List {
            Section("Connected Workers (\(appState.connectedWorkers.count))") {
                if appState.connectedWorkers.isEmpty {
                    Text("No workers connected")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(appState.connectedWorkers, id: \.workerId) { worker in
                        WorkerStatusRow(worker: worker)
                    }
                }
            }

            Section("Cluster Statistics") {
                HStack {
                    Text("Total Jobs Completed")
                    Spacer()
                    Text("\(appState.connectedWorkers.reduce(0) { $0 + $1.jobsCompleted })")
                        .foregroundStyle(.secondary)
                }
                HStack {
                    Text("Total Seeds Processed")
                    Spacer()
                    Text("\(appState.connectedWorkers.reduce(0) { $0 + $1.totalSeedsProcessed })")
                        .foregroundStyle(.secondary)
                }
                HStack {
                    Text("Available Workers")
                    Spacer()
                    Text("\(appState.connectedWorkers.filter { $0.isAvailable }.count)")
                        .foregroundStyle(.secondary)
                }
            }

            Section("Outputs") {
                if let outputRoot = appState.outputRootPath {
                    HStack {
                        Text("Output Root")
                        Spacer()
                        Text(outputRoot)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                } else {
                    Text("Output root not configured")
                        .foregroundStyle(.secondary)
                }

                if let outputRun = appState.outputRunPath {
                    HStack {
                        Text("Run Directory")
                        Spacer()
                        Text(outputRun)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                }

                if let logFile = appState.logFilePath {
                    HStack {
                        Text("Studio Log")
                        Spacer()
                        Text(logFile)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                }
            }
        }
        .navigationTitle("Cluster Monitor")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    Task {
                        await node.refreshWorkerList()
                    }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .keyboardShortcut("r", modifiers: .command)
            }
        }
    }
}

struct WorkerStatusRow: View {
    let worker: WorkerStatus

    var body: some View {
        HStack {
            Circle()
                .fill(worker.isAvailable ? Color.green : Color.orange)
                .frame(width: 8, height: 8)

            VStack(alignment: .leading, spacing: 2) {
                Text(worker.workerId)
                    .font(.headline)
                Text(worker.hostname)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 2) {
                Text("Seeds: \(worker.totalSeedsProcessed)")
                    .font(.caption)
                Text("Jobs: \(worker.jobsCompleted)")
                    .font(.caption)
            }
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
    }
}

struct HostSweepView: View {
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var node: LeniaNode
    @State private var sweepName = "Batch 1"
    @State private var seedCount = 100
    @State private var steps = 200
    @State private var gridSize = 128

    var body: some View {
        Form {
            Section("New Parameter Sweep") {
                TextField("Job Name", text: $sweepName)
                Stepper("Seeds: \(seedCount)", value: $seedCount, in: 10...10000, step: 10)
                Stepper("Steps: \(steps)", value: $steps, in: 100...1000, step: 50)
                Picker("Grid Size", selection: $gridSize) {
                    Text("64x64").tag(64)
                    Text("128x128").tag(128)
                    Text("256x256").tag(256)
                }

                Button("Dispatch Jobs") {
                    Task {
                        await node.startSweep(name: sweepName, totalSeeds: seedCount, steps: steps, gridSize: gridSize)
                    }
                }
                .buttonStyle(.borderedProminent)
            }

            Section("Active Campaigns") {
                if appState.activeCampaigns.isEmpty {
                    Text("No active campaigns")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(appState.activeCampaigns) { campaign in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text(campaign.name)
                                    .font(.headline)
                                Spacer()
                                if campaign.isRunning {
                                    ProgressView()
                                        .controlSize(.small)
                                } else {
                                    Image(systemName: "checkmark.circle.fill")
                                        .foregroundStyle(.green)
                                }
                            }
                            ProgressView(value: Double(campaign.processedSeeds), total: Double(campaign.totalSeeds))
                            HStack {
                                Text("\(campaign.processedSeeds)/\(campaign.totalSeeds) seeds")
                                Spacer()
                                Text("\(campaign.completedJobs)/\(campaign.totalJobs) jobs")
                            }
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 4)
                    }
                }
            }
        }
        .navigationTitle("Parameter Sweeps")
    }
}

struct HostArenaView: View {
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var node: LeniaNode
    @State private var arenaSize = 256
    @State private var maxPlayers = 4

    var body: some View {
        Form {
            Section("Create Arena") {
                Picker("Grid Size", selection: $arenaSize) {
                    Text("256x256").tag(256)
                    Text("512x512").tag(512)
                }

                Stepper("Max Players: \(maxPlayers)", value: $maxPlayers, in: 2...8)

                Button("Initialize Arena") {
                    Task {
                        await node.createArena(size: arenaSize, maxPlayers: maxPlayers)
                    }
                }
                .buttonStyle(.borderedProminent)
            }

            if let arenaConfig = appState.activeArenaConfig {
                Section("Active Arena") {
                    HStack {
                        Text("ID")
                        Spacer()
                        Text(arenaConfig.id.uuidString.prefix(8) + "...")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    HStack {
                        Text("Size")
                        Spacer()
                        Text("\(arenaConfig.size)x\(arenaConfig.size)")
                            .foregroundStyle(.secondary)
                    }
                    HStack {
                        Text("Max Players")
                        Spacer()
                        Text("\(arenaConfig.maxPlayers)")
                            .foregroundStyle(.secondary)
                    }
                    if let state = appState.arenaState {
                        HStack {
                            Text("Status")
                            Spacer()
                            Text(state.status.rawValue.capitalized)
                                .foregroundStyle(statusColor(state.status))
                        }
                        HStack {
                            Text("Participants")
                            Spacer()
                            Text("\(state.participants.count)")
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                Section("Control") {
                    Button("Start Simulation") {
                        Task {
                            await node.startArena()
                        }
                    }
                    .disabled(appState.arenaState?.status == .running)

                    Button("Trigger Radiation Storm") {
                        Task {
                            await node.triggerArenaMutation()
                        }
                    }
                    .buttonStyle(.bordered)
                    .foregroundStyle(.orange)
                    .disabled(appState.arenaState?.status != .running)

                    Button("Stop Arena") {
                        Task {
                            await node.stopArena()
                        }
                    }
                    .foregroundStyle(.red)
                }
            }
        }
        .navigationTitle("Arena Manager")
    }

    private func statusColor(_ status: ArenaStatus) -> Color {
        switch status {
        case .lobby: return .yellow
        case .running: return .green
        case .ended: return .gray
        }
    }
}
