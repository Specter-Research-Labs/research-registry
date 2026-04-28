import AppKit
import SwiftUI
import LeniaCore

private struct StudioStartupIssue {
    let title: String
    let message: String
    let suggestion: String
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        let isBundledApp = Bundle.main.bundleURL.pathExtension == "app"
        if !isBundledApp {
            NSApp.setActivationPolicy(.regular)
            NSApp.activate(ignoringOtherApps: true)
        }
    }
}

@main
struct LeniaStudioApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var appState: AppState
    @StateObject private var node: LeniaNode
    private let startupIssue: StudioStartupIssue?

    init() {
        let state = AppState()
        var issue: StudioStartupIssue?

        do {
            try LeniaMetalLibrarySupport.ensureAvailable()

            let runId = LeniaLogging.makeRunId(prefix: "studio")
            let nodeId = ProcessInfo.processInfo.hostName
            let logFileURL = try Self.makeLogFileURL(runId: runId)

            try LeniaLogging.bootstrap(LogConfig(
                runId: runId,
                nodeId: nodeId,
                role: "studio",
                logLevel: .info,
                logToConsole: true,
                logFileURL: logFileURL,
                metricsFileURL: nil
            ))

            state.logFilePath = logFileURL.path
        } catch {
            issue = StudioStartupIssue(
                title: "Lenia Studio could not start",
                message: (error as? LocalizedError)?.errorDescription ?? error.localizedDescription,
                suggestion: "Fix the missing dependency or log path, then relaunch the app."
            )
        }

        _appState = StateObject(wrappedValue: state)
        _node = StateObject(wrappedValue: LeniaNode(appState: state))
        startupIssue = issue
    }

    var body: some Scene {
        WindowGroup {
            if let startupIssue {
                StudioStartupFailureView(issue: startupIssue)
            } else {
                MainLayoutView()
                    .environmentObject(appState)
                    .environmentObject(node)
                    .frame(minWidth: 760, minHeight: 520)
            }
        }
        .defaultSize(width: 1180, height: 780)
        .windowStyle(.automatic)
        .commands {
            CommandGroup(replacing: .newItem) {}
        }
    }

    private static func makeLogFileURL(runId: String) throws -> URL {
        let env = ProcessInfo.processInfo.environment["LENIA_STUDIO_LOG_DIR"]?.trimmingCharacters(in: .whitespacesAndNewlines)
        let baseURL: URL
        if let env = env, !env.isEmpty {
            baseURL = URL(fileURLWithPath: (env as NSString).expandingTildeInPath, isDirectory: true)
        } else if let library = FileManager.default.urls(for: .libraryDirectory, in: .userDomainMask).first {
            baseURL = library.appendingPathComponent("Logs/LeniaStudio", isDirectory: true)
        } else {
            baseURL = FileManager.default.temporaryDirectory.appendingPathComponent("lenia-studio-logs", isDirectory: true)
        }

        try FileManager.default.createDirectory(at: baseURL, withIntermediateDirectories: true)
        return baseURL.appendingPathComponent("lenia-studio-\(runId).log.jsonl")
    }
}

private struct StudioStartupFailureView: View {
    let issue: StudioStartupIssue

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color(nsColor: .windowBackgroundColor),
                    Color(nsColor: .controlBackgroundColor),
                    Color(nsColor: .textBackgroundColor)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            VStack(alignment: .leading, spacing: 18) {
                Text(issue.title)
                    .font(.system(size: 28, weight: .bold, design: .rounded))

                Text("Studio startup stopped before the main workspace was created.")
                    .font(.headline)
                    .foregroundStyle(.secondary)

                VStack(alignment: .leading, spacing: 10) {
                    Text(issue.message)
                        .font(.body)
                        .textSelection(.enabled)
                    Text(issue.suggestion)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .strokeBorder(.quaternary, lineWidth: 1)
                )

                HStack {
                    Button("Quit Lenia Studio") {
                        NSApp.terminate(nil)
                    }
                    .keyboardShortcut(.defaultAction)

                    Spacer()
                }
            }
            .padding(28)
            .frame(maxWidth: 720)
        }
        .frame(minWidth: 760, minHeight: 520)
    }
}
