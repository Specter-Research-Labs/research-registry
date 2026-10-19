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
