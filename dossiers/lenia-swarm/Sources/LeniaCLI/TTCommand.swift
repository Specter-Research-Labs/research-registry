import ArgumentParser
import Foundation

struct TTCommands: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "tt",
        abstract: "Run Tenstorrent backend workflows",
        subcommands: [
            TTRunCommand.self,
        ]
    )
}

struct TTRunCommand: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "run",
        abstract: "Run a Flow Lenia trajectory through the TT backend"
    )

    @Option(name: .long, help: "Path to base config JSON, preferably repo-relative for remote/container runs")
    var config: String

    @Option(name: .shortAndLong, help: "Output directory for states and optional Studio frame export")
    var output: String

    @Option(name: .long, help: "Simulation steps")
    var steps: Int = 300

    @Option(name: .long, help: "Initial condition batch size")
    var batchSize: Int = 1

    @Option(name: .long, help: "Parameter seed override; defaults to params.seed from the config")
    var seed: Int?

    @Option(name: .long, help: "Comma-separated initial-state seeds for the batch")
    var seedList: String?

    @Option(name: .long, help: "Offset added to each initial-state seed")
    var initSeedOffset: Int = 0

    @Option(name: .long, help: "Save state every N steps; 0 writes only final_mass.npy")
    var saveEvery: Int = 0

    @Option(name: .long, help: "Export Studio-playable raw frames every N steps; 0 disables frame export")
    var frameEvery: Int = 0

    @Option(name: .long, help: "Frame projection: matter or channel:N")
    var frameProjection: String = "matter"

    @Option(name: .long, help: "Batch index to export frames from")
    var frameBatchIndex: Int = 0

    @Option(name: .long, help: "TT execution mode: single, fleet, or mesh")
    var executionMode: String = "single"

    @Option(name: .long, help: "Single-device TT id")
    var deviceId: Int = 0

    @Option(name: .long, help: "Comma-separated TT device ids, or auto")
    var deviceList: String?

    @Option(name: .long, help: "Explicit TT_VISIBLE_DEVICES value")
    var ttVisibleDevices: String?

    @Option(name: .long, help: "Explicit TT mesh shape as rows,cols")
    var meshShape: String?

    @Option(name: .long, help: "Reference bundle exported by export-reference")
    var reference: String?

    @Flag(name: .long, help: "Reuse persistent workers for fleet runs")
    var persistentWorkers: Bool = false

    @Option(name: .long, help: "Python executable on the target host")
    var python: String = "python3"

    @Option(name: .long, help: "SSH host for remote TT execution, for example quietbox")
    var host: String?

    @Option(
        name: .long,
        help: "Dossier root on the SSH host; required with --host unless LENIA_TT_REMOTE_ROOT is set"
    )
    var remoteRoot: String?

    @Flag(name: .customLong("no-container"), help: "Run the TT Python payload directly instead of through the TT-Lang container harness")
    var noContainer: Bool = false

    @Option(name: .long, help: "Host TT card mapped to container /dev/tenstorrent/0 in single mode")
    var ttCardNum: Int = 0

    @Option(name: .long, help: "Comma-separated host TT cards to expose in fleet/mesh container modes")
    var ttCardList: String?

    @Flag(name: .long, help: "Run tt-smi reset before container smoke/execution")
    var reset: Bool = false

    @Flag(name: .long, help: "Skip container smoke tests before running")
    var skipSmoke: Bool = false

    @Flag(name: .long, help: "Print the resolved command without running it")
    var dryRun: Bool = false

    func run() async throws {
        guard ["single", "fleet", "mesh"].contains(executionMode) else {
            throw ValidationError("--execution-mode must be one of: single, fleet, mesh")
        }
        if deviceList != nil && ttVisibleDevices != nil {
            throw ValidationError("--device-list and --tt-visible-devices cannot be used together.")
        }
        let invocation = try TTBackendRunInvocation(
            config: config,
            output: output,
            steps: steps,
            batchSize: batchSize,
            seed: seed,
            seedList: seedList,
            initSeedOffset: initSeedOffset,
            saveEvery: saveEvery,
            frameEvery: frameEvery,
            frameProjection: frameProjection,
            frameBatchIndex: frameBatchIndex,
            executionMode: executionMode,
            deviceId: deviceId,
            deviceList: deviceList,
            ttVisibleDevices: ttVisibleDevices,
            meshShape: meshShape,
            reference: reference,
            persistentWorkers: persistentWorkers,
            python: python,
            host: host,
            remoteRoot: remoteRoot ?? ProcessInfo.processInfo.environment["LENIA_TT_REMOTE_ROOT"],
            useContainer: !noContainer,
            ttCardNum: ttCardNum,
            ttCardList: ttCardList,
            reset: reset,
            skipSmoke: skipSmoke,
            dossierRoot: ttDossierRootURL()
        )
        if dryRun {
            print(invocation.displayCommand)
            return
        }
        try invocation.run()
    }
}

struct TTBackendRunInvocation {
    let executable: String
    let arguments: [String]
    let currentDirectory: URL?
    let displayCommand: String

    init(
        config: String,
        output: String,
        steps: Int,
        batchSize: Int,
        seed: Int?,
        seedList: String?,
        initSeedOffset: Int,
        saveEvery: Int,
        frameEvery: Int,
        frameProjection: String,
        frameBatchIndex: Int,
        executionMode: String,
        deviceId: Int,
        deviceList: String?,
        ttVisibleDevices: String?,
        meshShape: String?,
        reference: String?,
        persistentWorkers: Bool,
        python: String,
        host: String?,
        remoteRoot: String?,
        useContainer: Bool,
        ttCardNum: Int,
        ttCardList: String?,
        reset: Bool,
        skipSmoke: Bool,
        dossierRoot: URL
    ) throws {
        let runArgs = try Self.pythonRunArgs(
            config: config,
            output: output,
            steps: steps,
            batchSize: batchSize,
            seed: seed,
            seedList: seedList,
            initSeedOffset: initSeedOffset,
            saveEvery: saveEvery,
            frameEvery: frameEvery,
            frameProjection: frameProjection,
            frameBatchIndex: frameBatchIndex,
            executionMode: executionMode,
            deviceId: deviceId,
            deviceList: deviceList,
            ttVisibleDevices: ttVisibleDevices,
            meshShape: meshShape,
            reference: reference,
            persistentWorkers: persistentWorkers,
            useContainer: useContainer,
            dossierRoot: dossierRoot,
            remoteRoot: remoteRoot
        )

        let targetArgs: [String]
        if useContainer {
            targetArgs = Self.containerArgs(
                python: python,
                executionMode: executionMode,
                ttCardNum: ttCardNum,
                ttCardList: ttCardList,
                meshShape: meshShape,
                reset: reset,
                skipSmoke: skipSmoke,
                runArgs: runArgs
            )
        } else {
            targetArgs = [python] + runArgs
        }

        if let host {
            guard let remoteRoot, !remoteRoot.isEmpty else {
                throw ValidationError("--remote-root is required when --host is set. You may also set LENIA_TT_REMOTE_ROOT.")
            }
            let remoteCommand = "cd \(shellQuote(remoteRoot)) && " + targetArgs.map(shellQuote).joined(separator: " ")
            self.executable = "/usr/bin/env"
            self.arguments = ["ssh", host, remoteCommand]
            self.currentDirectory = nil
            self.displayCommand = ([self.executable] + self.arguments).map(shellQuote).joined(separator: " ")
        } else {
            self.executable = "/usr/bin/env"
            self.arguments = targetArgs
            self.currentDirectory = dossierRoot
            self.displayCommand = ([self.executable] + self.arguments).map(shellQuote).joined(separator: " ")
        }
    }

    func run() throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments
        process.currentDirectoryURL = currentDirectory
        try process.run()
        process.waitUntilExit()
        if process.terminationStatus != 0 {
            throw ValidationError("TT backend run failed with exit code \(process.terminationStatus).")
        }
    }

    private static func pythonRunArgs(
        config: String,
        output: String,
        steps: Int,
        batchSize: Int,
        seed: Int?,
        seedList: String?,
        initSeedOffset: Int,
        saveEvery: Int,
        frameEvery: Int,
        frameProjection: String,
        frameBatchIndex: Int,
        executionMode: String,
        deviceId: Int,
        deviceList: String?,
        ttVisibleDevices: String?,
        meshShape: String?,
        reference: String?,
        persistentWorkers: Bool,
        useContainer: Bool,
        dossierRoot: URL,
        remoteRoot: String?
    ) throws -> [String] {
        let configPath = try pathForTarget(config, useContainer: useContainer, dossierRoot: dossierRoot, remoteRoot: remoteRoot)
        let outputPath = try pathForTarget(output, useContainer: useContainer, dossierRoot: dossierRoot, remoteRoot: remoteRoot)
        var args = [
            useContainer ? "devtools/run.py" : "tt_backend/devtools/run.py",
            "--config", configPath,
            "--backend", "tt",
            "--execution-mode", executionMode,
            "--steps", String(steps),
            "--batch-size", String(batchSize),
            "--output", outputPath,
            "--init-seed-offset", String(initSeedOffset),
            "--save-every", String(saveEvery),
            "--frame-every", String(frameEvery),
            "--frame-projection", frameProjection,
            "--frame-batch-index", String(frameBatchIndex),
            "--device-id", String(deviceId),
        ]
        if let seed {
            args += ["--seed", String(seed)]
        }
        if let deviceList {
            args += ["--device-list", deviceList]
        }
        if let seedList {
            args += ["--seed-list", seedList]
        }
        if let ttVisibleDevices {
            args += ["--tt-visible-devices", ttVisibleDevices]
        }
        if let meshShape {
            args += ["--mesh-shape", meshShape]
        }
        if let reference {
            args += ["--reference", try pathForTarget(reference, useContainer: useContainer, dossierRoot: dossierRoot, remoteRoot: remoteRoot)]
        }
        if persistentWorkers {
            args.append("--persistent-workers")
        }
        return args
    }

    private static func containerArgs(
        python: String,
        executionMode: String,
        ttCardNum: Int,
        ttCardList: String?,
        meshShape: String?,
        reset: Bool,
        skipSmoke: Bool,
        runArgs: [String]
    ) -> [String] {
        var args = [
            python,
            "tt_backend/devtools/quietbox_container.py",
            "--device-mode", executionMode,
            "--tt-card-num", String(ttCardNum),
        ]
        if let ttCardList {
            args += ["--tt-card-list", ttCardList]
        }
        if let meshShape {
            args += ["--mesh-shape", meshShape]
        }
        if reset {
            args.append("--reset")
        }
        if skipSmoke {
            args.append("--skip-smoke")
        }
        args.append("--")
        args += [python] + runArgs
        return args
    }

    private static func pathForTarget(
        _ path: String,
        useContainer: Bool,
        dossierRoot: URL,
        remoteRoot: String?
    ) throws -> String {
        guard useContainer else { return path }
        if path.hasPrefix("/repo/") {
            return path
        }
        if path.hasPrefix("/") {
            let rootPath = dossierRoot.path
            if path == rootPath {
                return "/repo"
            }
            if path.hasPrefix(rootPath + "/") {
                return "/repo/" + String(path.dropFirst(rootPath.count + 1))
            }
            if let remoteRoot {
                if path == remoteRoot {
                    return "/repo"
                }
                if path.hasPrefix(remoteRoot + "/") {
                    return "/repo/" + String(path.dropFirst(remoteRoot.count + 1))
                }
            }
            throw ValidationError("Container TT paths must live under the dossier root or use /repo paths: \(path)")
        }
        return "/repo/" + path
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
