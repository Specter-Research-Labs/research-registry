import ArgumentParser
import Foundation
import LeniaCore
import Logging

struct CommandLoggingContext {
    let logDirURL: URL
    let nodeID: String
    let logger: Logger
}

func resolveRunID(prefix: String, logOptions: LogOptions) -> String {
    logOptions.runId ?? LeniaLogging.makeRunId(prefix: prefix)
}

func resolveArtifactRunOutput(
    explicitOutput: String?,
    defaultSubpath: String,
    runID: String,
    dossier: String
) throws -> String {
    try resolveArtifactPath(
        explicitOutput ?? "\(defaultSubpath)/\(runID)",
        dossier: dossier
    )
}

func makeRunOutputDirectory(outputRoot: String, runID: String) -> URL {
    URL(fileURLWithPath: outputRoot, isDirectory: true)
        .appendingPathComponent(runID, isDirectory: true)
}

func bootstrapRunLogging(
    runID: String,
    role: String,
    loggerLabel: String,
    logStem: String,
    outputForLogs: String?,
    logOptions: LogOptions,
    dossier: String,
    nodeID: String? = nil,
    logFileName: String? = nil,
    metricsFileName: String? = nil,
    extraMetadata: Logger.Metadata = [:]
) throws -> CommandLoggingContext {
    let logDirURL = URL(
        fileURLWithPath: try resolveLogBase(explicit: logOptions.logDir, dossier: dossier, output: outputForLogs),
        isDirectory: true
    ).appendingPathComponent(runID, isDirectory: true)
    let resolvedNodeID = nodeID ?? ProcessInfo.processInfo.hostName
    let resolvedLogFileName = logFileName ?? "\(logStem).log.jsonl"
    let resolvedMetricsFileName = metricsFileName ?? "\(logStem).metrics.jsonl"

    try LeniaLogging.bootstrap(LogConfig(
        runId: runID,
        nodeId: resolvedNodeID,
        role: role,
        logLevel: try logOptions.resolvedLogLevel(),
        logToConsole: !logOptions.noLogConsole,
        logFileURL: logDirURL.appendingPathComponent(resolvedLogFileName),
        metricsFileURL: logDirURL.appendingPathComponent(resolvedMetricsFileName),
        extraMetadata: extraMetadata
    ))

    return CommandLoggingContext(
        logDirURL: logDirURL,
        nodeID: resolvedNodeID,
        logger: LeniaLogging.makeLogger(label: loggerLabel, extraMetadata: extraMetadata)
    )
}

func logLoggingInitialized(_ logger: Logger, runID: String, logging: CommandLoggingContext) {
    logger.info("Logging initialized (run_id=\(runID), log_dir=\(logging.logDirURL.path))")
}

@discardableResult
func promoteIfConfigured(
    options: ArchivePromotionOptions,
    defaultCompendiumPath: String?,
    dossier: String,
    defaultEnabled: Bool = false,
    runDir: String,
    includeResults: Bool = true,
    stats: Bool = false
) throws -> ArchivePromotionConfig {
    let resolvedPromotion = try options.resolvedConfig(
        defaultCompendiumPath: defaultCompendiumPath,
        dossier: dossier,
        defaultEnabled: defaultEnabled
    )
    return try applyPromotionIfEnabled(
        config: resolvedPromotion,
        runDir: runDir,
        includeResults: includeResults,
        stats: stats
    )
}

/// The resolved inputs a research run executes, as one JSON object in its receipt.
struct ResolvedRunConfig: Encodable {
    let parts: [(String, Data)]

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: ResolvedRunConfigKey.self)
        for (name, data) in parts {
            try container.encode(try JSONDecoder().decode(AnyCodable.self, from: data), forKey: ResolvedRunConfigKey(name))
        }
    }
}

private struct ResolvedRunConfigKey: CodingKey {
    let stringValue: String
    var intValue: Int? { nil }

    init(_ stringValue: String) { self.stringValue = stringValue }
    init?(stringValue: String) { self.stringValue = stringValue }
    init?(intValue: Int) { nil }
}

func runningBuildInfo() throws -> LeniaBuildInfo {
    try LeniaBuildInfo.loadVerified(executableURL: try LeniaBuildInfo.runningExecutableURL())
}

/// Starts a research run's receipt before it writes any record; refuses a binary that does not match its build info.
func beginRunReceipt<Config: Encodable>(
    directory: URL,
    executableURL: URL,
    backend: FlowLeniaComputeBackend,
    config: Config,
    seeds: [Int],
    inputs: [URL]
) throws -> RunReceiptSession {
    try RunReceiptSession.begin(
        directory: directory,
        executableURL: executableURL,
        argv: CommandLine.arguments,
        backend: backend,
        config: config,
        seeds: seeds,
        inputs: inputs
    )
}

func resumeRunReceipt(directory: URL, backend: FlowLeniaComputeBackend) throws -> RunReceiptSession {
    try RunReceiptSession.resume(
        directory: directory,
        executableURL: try LeniaBuildInfo.runningExecutableURL(),
        backend: backend
    )
}

/// A config file keyed by its path relative to its directory, so nested files cannot collide.
struct ConfigDirectoryFile {
    let name: String
    let url: URL
}

/// Paper protocols read their whole locked config directory, so the receipt records every file in it.
func beginPaperRunReceipt(
    outputDirectory: URL,
    executableURL: URL,
    configFiles: [ConfigDirectoryFile],
    extraInputs: [URL],
    backend: FlowLeniaComputeBackend,
    seeds: [Int]
) throws -> RunReceiptSession {
    try beginRunReceipt(
        directory: outputDirectory,
        executableURL: executableURL,
        backend: backend,
        config: ResolvedRunConfig(parts: try configFiles.map { ($0.name, try Data(contentsOf: $0.url)) }),
        seeds: seeds,
        inputs: configFiles.map(\.url) + extraInputs
    )
}

func configDirectoryFiles(in directory: URL) throws -> [ConfigDirectoryFile] {
    let root = directory.standardizedFileURL.resolvingSymlinksInPath()
    guard let enumerator = FileManager.default.enumerator(at: root, includingPropertiesForKeys: [.isRegularFileKey]) else {
        throw ValidationError("Cannot enumerate paper config directory \(root.path).")
    }
    let prefix = root.path + "/"
    var files: [ConfigDirectoryFile] = []
    for case let url as URL in enumerator where try url.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile == true {
        let path = url.standardizedFileURL.resolvingSymlinksInPath().path
        guard path.hasPrefix(prefix) else {
            throw ValidationError("Paper config file \(path) lies outside \(root.path).")
        }
        files.append(ConfigDirectoryFile(name: String(path.dropFirst(prefix.count)), url: URL(fileURLWithPath: path)))
    }
    guard !files.isEmpty else {
        throw ValidationError("Paper config directory \(root.path) holds no files.")
    }
    return files.sorted { $0.name < $1.name }
}

/// The single backend a set of Flow Lenia base configs names; paper protocols that mix backends are refused.
func uniformConfigBackend(_ configFiles: [URL]) throws -> FlowLeniaComputeBackend {
    let backends = try Set(configFiles.map { url in
        try JSONDecoder().decode(LeniaBaseConfig.self, from: Data(contentsOf: url)).backend
    })
    guard backends.count == 1, let backend = backends.first else {
        throw ValidationError("Base configs name backends \(backends.sorted()); a run must use exactly one.")
    }
    return try FlowLeniaComputeBackend(configValue: backend)
}
