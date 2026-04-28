import ArgumentParser
import Foundation
import LeniaCore
import Logging

struct MutateCommand: ParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "mutate",
        abstract: "Mutate Lenia parameters from search results or config"
    )

    @Option(name: .long, help: "Path to base config.json")
    var config: String

    @Option(name: .long, help: "Path to params file (JSON, JSONL, or search results)")
    var params: String

    @Option(name: .long, help: "Rank in params list (0 = best)")
    var rank: Int = 0

    @Option(name: .shortAndLong, help: "Output directory")
    var outputDir: String?

    @Option(name: .long, help: "Parameter jitter standard deviation")
    var paramJitterStd: Float = 0.0

    @Option(name: .long, help: "Parameter jitter seed")
    var paramJitterSeed: Int?

    @Flag(name: .long, help: "Clip params to config ranges")
    var clip: Bool = false

    @Option(name: .long, help: "Scale patch size")
    var patchScale: Float = 1.0

    @Option(name: .long, help: "Shift patch X")
    var patchShiftX: Int = 0

    @Option(name: .long, help: "Shift patch Y")
    var patchShiftY: Int = 0

    @Flag(name: .long, help: "Mirror patches on X axis")
    var mirrorX: Bool = false

    @Flag(name: .long, help: "Mirror patches on Y axis")
    var mirrorY: Bool = false

    @OptionGroup
    var logOptions: LogOptions

    func run() throws {
        let resolvedRunId = resolveRunID(prefix: "local", logOptions: logOptions)
        let logging = try bootstrapRunLogging(
            runID: resolvedRunId,
            role: "mutate",
            loggerLabel: "LeniaSwarm.Mutate",
            logStem: "mutate",
            outputForLogs: outputDir,
            logOptions: logOptions,
            dossier: dossierName
        )
        let logger = logging.logger
        logLoggingInitialized(logger, runID: resolvedRunId, logging: logging)

        let mutConfig = MutationConfig(
            paramJitterStd: paramJitterStd,
            paramJitterSeed: paramJitterSeed,
            clip: clip,
            patchScale: patchScale,
            patchShift: (patchShiftX, patchShiftY),
            mirrorX: mirrorX,
            mirrorY: mirrorY
        )

        // Generate output directory if not specified
        let outputPath: String
        if let dir = outputDir {
            outputPath = dir
        } else {
            let timestamp = ISO8601DateFormatter().string(from: Date())
                .replacingOccurrences(of: ":", with: "-")
                .replacingOccurrences(of: "T", with: "_")
                .prefix(15)
            outputPath = "mutations/\(timestamp)"
        }
        let resolvedOutputPath = try resolvePath(outputPath, dossier: dossierName)

        try mutateConfig(
            baseConfigPath: config,
            paramsPath: params,
            rank: rank,
            outputDir: resolvedOutputPath,
            config: mutConfig
        )

        logger.info("Mutated config saved to: \(resolvedOutputPath)/config.json")
        logger.info("Mutation record saved to: \(resolvedOutputPath)/mutation.json")
        logger.info("Params saved to: \(resolvedOutputPath)/params.json")
    }
}
