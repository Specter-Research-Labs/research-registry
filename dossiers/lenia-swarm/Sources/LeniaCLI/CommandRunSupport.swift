import ArgumentParser
import Foundation
import LeniaCore
import Logging

struct CommandLoggingContext {
    let logDirURL: URL?
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
    fallbackOutputLogDir: Bool = false,
    nodeID: String? = nil,
    logFileName: String? = nil,
    metricsFileName: String? = nil,
    extraMetadata: Logger.Metadata = [:]
) throws -> CommandLoggingContext {
    let resolvedLogBase = try resolveLogBase(
        explicit: logOptions.logDir,
        dossier: dossier,
        output: outputForLogs
    ) ?? {
        guard fallbackOutputLogDir, let outputForLogs else { return nil }
        return URL(fileURLWithPath: outputForLogs, isDirectory: true)
            .appendingPathComponent("logs", isDirectory: true)
            .path
    }()

    let logDirURL = resolvedLogBase.map { resolvedLogBase in
        URL(fileURLWithPath: resolvedLogBase, isDirectory: true)
            .appendingPathComponent(runID, isDirectory: true)
    }
    let resolvedNodeID = nodeID ?? ProcessInfo.processInfo.hostName
    let resolvedLogFileName = logFileName ?? "\(logStem).log.jsonl"
    let resolvedMetricsFileName = metricsFileName ?? "\(logStem).metrics.jsonl"

    try LeniaLogging.bootstrap(LogConfig(
        runId: runID,
        nodeId: resolvedNodeID,
        role: role,
        logLevel: try logOptions.resolvedLogLevel(),
        logToConsole: !logOptions.noLogConsole,
        logFileURL: logDirURL?.appendingPathComponent(resolvedLogFileName),
        metricsFileURL: logDirURL?.appendingPathComponent(resolvedMetricsFileName),
        extraMetadata: extraMetadata
    ))

    return CommandLoggingContext(
        logDirURL: logDirURL,
        nodeID: resolvedNodeID,
        logger: LeniaLogging.makeLogger(label: loggerLabel, extraMetadata: extraMetadata)
    )
}

func logLoggingInitialized(_ logger: Logger, runID: String, logging: CommandLoggingContext) {
    if let logDirURL = logging.logDirURL {
        logger.info("Logging initialized (run_id=\(runID), log_dir=\(logDirURL.path))")
    } else {
        logger.info("Logging initialized (run_id=\(runID), console_only=true)")
    }
}

@discardableResult
func promoteIfConfigured(
    options: ArchivePromotionOptions,
    defaultCompendiumPath: String?,
    dossier: String,
    defaultEnabled: Bool = false,
    runDir: String,
    runID: String? = nil,
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
        runID: runID,
        includeResults: includeResults,
        stats: stats
    )
}
