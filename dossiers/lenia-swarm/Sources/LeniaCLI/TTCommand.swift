import ArgumentParser
import Foundation

struct TTCommands: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "tt",
        abstract: "Run Tenstorrent backend workflows",
        subcommands: [
            TTReplayCommand.self,
            TTMaterializeInitCommand.self,
        ]
    )
}

struct TTReplayCommand: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "replay",
        abstract: "Replay an export index on N300 cards with the fp32 SFPU engine",
        discussion: "Writes the same campaign layout as publish replay, so assess-creatures and classify-creatures read the result."
    )

    @Option(name: .long, help: "Export index.jsonl, under the dossier root")
    var input: String

    @Option(name: .shortAndLong, help: "New output directory, under the dossier root")
    var output: String

    @Option(name: .long, help: "Simulation steps")
    var steps: Int

    @Option(name: .long, help: "Write a development-trace row every N steps")
    var traceInterval: Int

    @Option(name: .long, help: "Comma-separated N300 card indices")
    var cards: String

    @Option(name: .long, help: "One-ulp ensemble seeds per body, such as 0-8; seed 0 is unperturbed")
    var seeds: String

    @Option(name: .long, help: "Lanes per engine round on each card, a multiple of 64")
    var batch: Int

    @Option(name: .long, help: "Python executable on the target host")
    var python: String = "python3"

    @Option(name: .long, help: "SSH host with the N300 cards")
    var host: String?

    @Option(
        name: .long,
        help: "Dossier root on the SSH host; required with --host unless LENIA_TT_REMOTE_ROOT is set"
    )
    var remoteRoot: String?

    @Flag(name: .long, help: "Print the resolved command without running it")
    var dryRun: Bool = false

    func run() async throws {
        let invocation = try TTReplayInvocation(
            input: input,
            output: output,
            steps: steps,
            traceInterval: traceInterval,
            cards: cards,
            seeds: seeds,
            batch: batch,
            python: python,
            host: host,
            remoteRoot: remoteRoot ?? ProcessInfo.processInfo.environment["LENIA_TT_REMOTE_ROOT"],
            dossierRoot: ttDossierRootURL()
        )
        if dryRun {
            print(invocation.displayCommand)
            return
        }
        try invocation.run()
    }
}

struct TTReplayInvocation {
    let executable: String
    let arguments: [String]
    let currentDirectory: URL?
    let displayCommand: String

    init(
        input: String,
        output: String,
        steps: Int,
        traceInterval: Int,
        cards: String,
        seeds: String,
        batch: Int,
        python: String,
        host: String?,
        remoteRoot: String?,
        dossierRoot: URL
    ) throws {
        let targetArgs = [
            python, "tt_backend/devtools/container.py", "--",
            python, "-m", "tt_lenia.sfpu.replay",
            "--input", try Self.containerPath(input, dossierRoot: dossierRoot, remoteRoot: remoteRoot),
            "--output", try Self.containerPath(output, dossierRoot: dossierRoot, remoteRoot: remoteRoot),
            "--steps", String(steps),
            "--trace-interval", String(traceInterval),
            "--cards", cards,
            "--seeds", seeds,
            "--batch", String(batch),
        ]
        self.executable = "/usr/bin/env"
        if let host {
            guard let remoteRoot, !remoteRoot.isEmpty else {
                throw ValidationError("--remote-root is required when --host is set. You may also set LENIA_TT_REMOTE_ROOT.")
            }
            let remoteCommand = "cd \(shellQuote(remoteRoot)) && " + targetArgs.map(shellQuote).joined(separator: " ")
            self.arguments = ["ssh", host, remoteCommand]
            self.currentDirectory = nil
        } else {
            self.arguments = targetArgs
            self.currentDirectory = dossierRoot
        }
        self.displayCommand = ([self.executable] + self.arguments).map(shellQuote).joined(separator: " ")
    }

    func run() throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments
        process.currentDirectoryURL = currentDirectory
        try process.run()
        process.waitUntilExit()
        if process.terminationStatus != 0 {
            throw ValidationError("TT replay failed with exit code \(process.terminationStatus).")
        }
    }

    private static func containerPath(_ path: String, dossierRoot: URL, remoteRoot: String?) throws -> String {
        if path.hasPrefix("/repo/") {
            return path
        }
        guard path.hasPrefix("/") else {
            return "/repo/" + path
        }
        for root in [dossierRoot.path, remoteRoot].compactMap({ $0 }) where path.hasPrefix(root + "/") {
            return "/repo/" + String(path.dropFirst(root.count + 1))
        }
        throw ValidationError("TT paths must live under the dossier root or use /repo paths: \(path)")
    }
}

func ttDossierRootURL() -> URL {
    URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .deletingLastPathComponent()
}

func shellQuote(_ value: String) -> String {
    if value.isEmpty {
        return "''"
    }
    let safe = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_+-=.,/:")
    if value.unicodeScalars.allSatisfy({ safe.contains($0) }) {
        return value
    }
    return "'" + value.replacingOccurrences(of: "'", with: "'\\''") + "'"
}
