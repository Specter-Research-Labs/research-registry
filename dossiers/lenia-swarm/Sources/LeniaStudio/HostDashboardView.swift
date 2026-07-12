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
