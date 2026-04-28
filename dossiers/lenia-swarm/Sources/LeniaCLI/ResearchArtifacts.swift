import ArgumentParser
import Foundation
import LeniaCore

typealias ReplayExportBatchPayload = (
    baseConfig: LeniaBaseConfig,
    searchConfig: ParsedSearchConfig,
    creature: SavedCreature,
    runId: String,
    campaignId: UUID?,
    score: Float?,
    filtersPassed: Bool?,
    reason: String
)

struct PersistedResearchExecutionArtifacts {
    let configURL: URL?
    let searchURL: URL?
    let resultsURL: URL
    let activityURL: URL?
}

struct PersistedResearchArchiveArtifacts {
    let libraryURL: URL
    let exportIndexURL: URL?
    let exportCount: Int
}

struct PersistedResearchRunArtifacts {
    let execution: PersistedResearchExecutionArtifacts
    let archive: PersistedResearchArchiveArtifacts
}

@discardableResult
func persistResearchExecutionArtifacts(
    directory: URL,
    baseConfig: LeniaBaseConfig?,
    searchConfig: ParsedSearchConfig?,
    resultData: SimulationResultData,
    activityRecord: ActivitySummaryRecord?
) throws -> PersistedResearchExecutionArtifacts {
    let configURL = baseConfig.map { _ in directory.appendingPathComponent("config.json") }
    if let baseConfig, let configURL {
        try writeResearchJSON(baseConfig, to: configURL, prettyPrinted: true)
    }

    let searchURL = searchConfig.map { _ in directory.appendingPathComponent("search.json") }
    if let searchConfig, let searchURL {
        try writeResearchJSON(searchConfig, to: searchURL, prettyPrinted: true)
    }

    let resultsURL = directory.appendingPathComponent("results.jsonl")
    try writeResearchJSONLines([resultData], to: resultsURL)

    let activityURL: URL?
    if let activityRecord {
        let resolvedActivityURL = directory.appendingPathComponent("activity.jsonl")
        try writeResearchJSONLines([activityRecord], to: resolvedActivityURL)
        activityURL = resolvedActivityURL
    } else {
        activityURL = nil
    }

    return PersistedResearchExecutionArtifacts(
        configURL: configURL,
        searchURL: searchURL,
        resultsURL: resultsURL,
        activityURL: activityURL
    )
}

@discardableResult
func persistResearchArchiveArtifacts(
    runDirectory: URL,
    libraryEntries: [ResearchLibraryEntry]
) throws -> PersistedResearchArchiveArtifacts {
    PersistedResearchArchiveArtifacts(
        libraryURL: try ResearchLibraryWriter.write(entries: libraryEntries, runDirectory: runDirectory),
        exportIndexURL: nil,
        exportCount: 0
    )
}

@discardableResult
func persistResearchArchiveArtifacts<Item>(
    runDirectory: URL,
    libraryEntries: [ResearchLibraryEntry],
    exportRoot: URL? = nil,
    exportItems: [Item] = [],
    emptyExportMessage: String? = nil,
    buildExportPayload: ((Item) -> ReplayExportBatchPayload)? = nil
) throws -> PersistedResearchArchiveArtifacts {
    let libraryURL = try ResearchLibraryWriter.write(entries: libraryEntries, runDirectory: runDirectory)

    guard let exportRoot, !exportItems.isEmpty else {
        return PersistedResearchArchiveArtifacts(
            libraryURL: libraryURL,
            exportIndexURL: nil,
            exportCount: 0
        )
    }
    guard let buildExportPayload else {
        throw ValidationError("Missing replay export payload builder.")
    }

    let exportRecords = try writeReplayExportBatch(exportRoot: exportRoot, items: exportItems) { item in
        let payload = buildExportPayload(item)
        return (
            baseConfig: payload.baseConfig,
            searchConfig: payload.searchConfig,
            creature: payload.creature,
            runId: payload.runId,
            campaignId: payload.campaignId,
            score: payload.score,
            filtersPassed: payload.filtersPassed,
            reason: payload.reason
        )
    }
    guard !exportRecords.isEmpty else {
        throw ValidationError(emptyExportMessage ?? "Replay export bundle already exists for the selected archive artifacts.")
    }

    return PersistedResearchArchiveArtifacts(
        libraryURL: libraryURL,
        exportIndexURL: exportRoot.appendingPathComponent("index.jsonl"),
        exportCount: exportRecords.count
    )
}

@discardableResult
func persistResearchRunArtifacts<Item>(
    directory: URL,
    baseConfig: LeniaBaseConfig?,
    searchConfig: ParsedSearchConfig?,
    resultData: SimulationResultData,
    activityRecord: ActivitySummaryRecord?,
    libraryEntries: [ResearchLibraryEntry],
    exportRoot: URL? = nil,
    exportItems: [Item] = [],
    emptyExportMessage: String? = nil,
    buildExportPayload: ((Item) -> ReplayExportBatchPayload)? = nil
) throws -> PersistedResearchRunArtifacts {
    let execution = try persistResearchExecutionArtifacts(
        directory: directory,
        baseConfig: baseConfig,
        searchConfig: searchConfig,
        resultData: resultData,
        activityRecord: activityRecord
    )
    let archive: PersistedResearchArchiveArtifacts
    if let exportRoot {
        archive = try persistResearchArchiveArtifacts(
            runDirectory: directory,
            libraryEntries: libraryEntries,
            exportRoot: exportRoot,
            exportItems: exportItems,
            emptyExportMessage: emptyExportMessage,
            buildExportPayload: buildExportPayload
        )
    } else {
        archive = try persistResearchArchiveArtifacts(
            runDirectory: directory,
            libraryEntries: libraryEntries
        )
    }
    return PersistedResearchRunArtifacts(execution: execution, archive: archive)
}

@discardableResult
func persistResearchRunArtifacts(
    directory: URL,
    baseConfig: LeniaBaseConfig?,
    searchConfig: ParsedSearchConfig?,
    resultData: SimulationResultData,
    activityRecord: ActivitySummaryRecord?,
    libraryEntries: [ResearchLibraryEntry]
) throws -> PersistedResearchRunArtifacts {
    let execution = try persistResearchExecutionArtifacts(
        directory: directory,
        baseConfig: baseConfig,
        searchConfig: searchConfig,
        resultData: resultData,
        activityRecord: activityRecord
    )
    let archive = try persistResearchArchiveArtifacts(
        runDirectory: directory,
        libraryEntries: libraryEntries
    )
    return PersistedResearchRunArtifacts(execution: execution, archive: archive)
}
