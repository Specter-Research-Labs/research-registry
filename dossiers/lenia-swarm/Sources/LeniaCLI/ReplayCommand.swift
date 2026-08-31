import ArgumentParser
import Foundation
import LeniaCore
import Logging

struct ReplayCommand: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "replay",
        abstract: "Replay export or library specimens into strict, indexable run artifacts"
    )

    @Option(name: .long, help: "Path to exports/index.jsonl or library/index.jsonl")
    var input: String

    @Option(name: .long, help: "Expected SHA-256 of the exact input JSONL bytes")
    var inputSha256: String?

    @Option(name: .shortAndLong, help: "Replay batch output directory")
    var output: String?

    @Flag(name: .long, help: "Write replayed export bundles under each specimen campaign directory")
    var exportEnabled: Bool = false

    @OptionGroup
    var promotion: ArchivePromotionOptions

    @Flag(name: .long, help: "Validate the input and resolved replay configs without running")
    var validateOnly: Bool = false

    @Flag(name: .long, help: "Capture a per-step morphology development trace per specimen")
    var developmentTrace: Bool = false

    @Option(name: .long, help: "Steps between captured development-trace samples")
    var traceInterval: Int = 25

    @Option(name: .long, help: "If > 0, also capture a centered NxN Float16 field per trace sample")
    var developmentFieldResolution: Int = 0

    @OptionGroup
    var logOptions: LogOptions

    func run() async throws {
        let resolvedRunId = resolveRunID(prefix: "replay", logOptions: logOptions)
        let resolvedOutput = try resolveArtifactRunOutput(
            explicitOutput: output,
            defaultSubpath: "outputs/replays",
            runID: resolvedRunId,
            dossier: dossierName
        )
        let resolvedInput = try resolveArtifactPath(input, dossier: dossierName)
        let logging = try bootstrapRunLogging(
            runID: resolvedRunId,
            role: "replay",
            loggerLabel: "LeniaSwarm.Replay",
            logStem: "replay",
            outputForLogs: resolvedOutput,
            logOptions: logOptions,
            dossier: dossierName
        )
        let logger = logging.logger

        let inputURL = URL(fileURLWithPath: resolvedInput)
        let inputs = try loadReplayResolvedInputs(
            from: inputURL,
            expectedInputSha256: inputSha256
        )
        if validateOnly {
            guard !inputs.isEmpty else {
                throw ValidationError("No replayable specimens found in \(resolvedInput).")
            }
            logger.info("Resolved \(inputs.count) replay inputs from \(resolvedInput)")
            logger.info("Replay inputs validated successfully")
            return
        }

        let outputURL = URL(fileURLWithPath: resolvedOutput, isDirectory: true)
        let _ = try materializeReplayBatch(
            inputs: inputs,
            inputPath: resolvedInput,
            outputURL: outputURL,
            runID: resolvedRunId,
            exportEnabled: exportEnabled,
            developmentTraceInterval: developmentTrace ? max(1, traceInterval) : nil,
            developmentFieldResolution: developmentTrace ? max(0, developmentFieldResolution) : 0,
            logger: logger
        )

        try promoteIfConfigured(
            options: promotion,
            defaultCompendiumPath: nil,
            dossier: dossierName,
            runDir: outputURL.path,
            runID: resolvedRunId,
            includeResults: true
        )
    }
}
