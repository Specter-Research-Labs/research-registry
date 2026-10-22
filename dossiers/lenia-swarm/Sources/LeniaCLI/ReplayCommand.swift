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

    @Flag(name: .long, help: "Also write the raw per-channel Float32 state of the raw steps to development-state.f32")
    var developmentState: Bool = false

    @Option(name: .long, help: "Trace steps that keep fields and raw state: \"all\" or comma-separated steps. Required with --development-field-resolution or --development-state")
    var developmentRawSteps: String?

    @Option(name: .long, help: "Flow bodies per engine batch. Above 1, every body in a batch must share its config except rule parameters and init seed")
    var batchSize: Int = 1

    @Option(name: .long, help: "Replay backend: auto, metal-full or cpu. Auto picks metal-full when the host and config support it, otherwise the config backend")
    var backend: String = "auto"

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

        if developmentState && !developmentTrace {
            throw ValidationError("--development-state requires --development-trace.")
        }
        let capturesRaw = developmentState || developmentFieldResolution > 0
        if capturesRaw && developmentRawSteps == nil {
            throw ValidationError("--development-field-resolution and --development-state require --development-raw-steps (\"all\" or the restart and exemplar steps to keep).")
        }
        if !capturesRaw && developmentRawSteps != nil {
            throw ValidationError("--development-raw-steps needs --development-field-resolution or --development-state.")
        }
        let rawSteps = try developmentRawSteps.map(parseDevelopmentRawSteps)
        let inputURL = URL(fileURLWithPath: resolvedInput)
        let inputs = try loadReplayResolvedInputs(from: inputURL)
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
            backendRequest: backend,
            exportEnabled: exportEnabled,
            developmentTrace: developmentTrace
                ? DevelopmentTraceOptions(
                    interval: max(1, traceInterval),
                    fieldResolution: max(0, developmentFieldResolution),
                    recordState: developmentState,
                    rawSteps: rawSteps
                )
                : nil,
            batchSize: batchSize,
            logger: logger
        )

        try promoteIfConfigured(
            options: promotion,
            defaultCompendiumPath: nil,
            dossier: dossierName,
            runDir: outputURL.path,
            includeResults: true
        )
    }
}
