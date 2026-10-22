import ArgumentParser
import Foundation
import LeniaCore

struct TTMaterializeInitCommand: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "materialize-init",
        abstract: "Rewrite seeded random-patch export bundles as explicit step-0 state patches",
        discussion: """
            The TT engine accepts only explicit state patches. Each bundle's step-0 state is rebuilt from its \
            replay seed, written as init.state_patch, and rebuilt again from the new base.json; the command \
            fails unless both states are bitwise identical. search.json is copied unchanged.
            """
    )

    @Option(name: .long, help: "Export index.jsonl of strict replay bundles")
    var input: String

    @Option(name: .shortAndLong, help: "New output directory for the rewritten bundles and their index.jsonl")
    var output: String

    func run() async throws {
        let inputURL = URL(fileURLWithPath: input)
        let outputURL = URL(fileURLWithPath: output, isDirectory: true)
        guard !FileManager.default.fileExists(atPath: outputURL.path) else {
            throw ValidationError("Output directory already exists: \(outputURL.path)")
        }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .deferredToDate
        let records = try replayReadJSONLines(inputURL).map { line in
            try decoder.decode(CreatureExportRecord.self, from: Data(line.utf8))
        }
        guard !records.isEmpty else {
            throw ValidationError("No export records in \(inputURL.path).")
        }
        try FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)
        let materialized = try records.map { record in
            try materializeExportInit(record, outputRoot: outputURL)
        }
        _ = try writeCreatureExportIndex(materialized, to: outputURL)
        print("Materialized \(materialized.count) bundle(s) into \(outputURL.path)")
    }
}

func materializeExportInit(_ record: CreatureExportRecord, outputRoot: URL) throws -> CreatureExportRecord {
    guard record.bundleKind == .strictReplayBundleV1,
          let basePath = record.baseConfigPath,
          let searchPath = record.searchConfigPath else {
        throw ValidationError("\(record.exportDir) is not a strict replay bundle.")
    }
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .deferredToDate
    let sourceDir = URL(fileURLWithPath: record.exportDir, isDirectory: true)
    let baseData = try Data(contentsOf: URL(fileURLWithPath: basePath))
    let searchData = try Data(contentsOf: URL(fileURLWithPath: searchPath))
    let metaData = try Data(contentsOf: sourceDir.appendingPathComponent("meta.json"))

    let searchConfig = try decoder.decode(ParsedSearchConfig.self, from: searchData)
    guard searchConfig.count == 1, searchConfig.overrides.isEmpty, let initSeedOffset = searchConfig.initSeedOffset else {
        throw ValidationError("\(record.exportDir): search.json must replay one body with an init seed offset and no overrides.")
    }
    let seed = searchConfig.seedStart + initSeedOffset
    let runtimeConfig = try loadRuntimeConfig(from: baseData)
    let statePatch = try materializedInitialStatePatch(runtimeConfig: runtimeConfig, seed: seed)

    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    guard var base = try JSONSerialization.jsonObject(with: baseData) as? [String: Any],
          var initObject = base["init"] as? [String: Any] else {
        throw ValidationError("\(basePath) has no init object.")
    }
    initObject["patches"] = []
    initObject["a_uniform"] = ["low": 0, "high": 0]
    initObject["state_patch"] = try JSONSerialization.jsonObject(with: encoder.encode(statePatch))
    base["init"] = initObject
    let materializedBase = try decoder.decode(
        LeniaBaseConfig.self,
        from: JSONSerialization.data(withJSONObject: base)
    )
    let materializedBaseData = try encoder.encode(materializedBase)

    let original = searchInitialState(runtimeConfig: runtimeConfig, seed: seed)
    let rebuilt = searchInitialState(runtimeConfig: try loadRuntimeConfig(from: materializedBaseData), seed: seed)
    guard original.map(\.bitPattern) == rebuilt.map(\.bitPattern) else {
        throw ValidationError("\(record.exportDir): the materialized step-0 state differs from the seeded one.")
    }

    guard var meta = try JSONSerialization.jsonObject(with: metaData) as? [String: Any],
          var creature = meta["creature"] as? [String: Any] else {
        throw ValidationError("\(record.exportDir)/meta.json has no creature object.")
    }
    creature["initialCondition"] = try JSONSerialization.jsonObject(with: encoder.encode(materializedBase.`init`))
    meta["creature"] = creature
    let materializedMeta = try decodeCreatureExportMetadata(
        JSONSerialization.data(withJSONObject: meta),
        decoder: decoder,
        indexBundleKind: record.bundleKind
    )

    let exportDir = outputRoot.appendingPathComponent(sourceDir.lastPathComponent, isDirectory: true)
    try FileManager.default.createDirectory(at: exportDir, withIntermediateDirectories: false)
    let baseURL = exportDir.appendingPathComponent("base.json")
    let searchURL = exportDir.appendingPathComponent("search.json")
    try materializedBaseData.write(to: baseURL)
    try searchData.write(to: searchURL)
    try encoder.encode(materializedMeta).write(to: exportDir.appendingPathComponent("meta.json"))
    return CreatureExportRecord(
        creatureId: record.creatureId,
        name: record.name,
        ownerId: record.ownerId,
        runId: record.runId,
        campaignId: record.campaignId,
        bundleKind: record.bundleKind,
        exportDir: exportDir.path,
        baseConfigPath: baseURL.path,
        searchConfigPath: searchURL.path,
        exportedAt: record.exportedAt,
        reason: record.reason,
        score: record.score,
        filtersPassed: record.filtersPassed,
        runtimeFamily: record.runtimeFamily,
        runtimeCapabilities: record.runtimeCapabilities,
        specimenManifest: record.specimenManifest
    )
}
