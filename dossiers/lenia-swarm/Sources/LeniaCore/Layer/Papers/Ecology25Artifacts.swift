import Foundation

func writeFlowLeniaEcologyFrames(_ frames: [FlowLeniaEcology2025FrameMetrics], to url: URL) throws {
    try writeJSONLines(frames, to: url)
}

public func writeFlowLeniaEcology2025RunArtifacts(
    runDirectory: URL,
    runID: String,
    campaignID: String?,
    replayBaseConfig: LeniaBaseConfig,
    replayPayload: FlowLeniaEcology2025ReplayPayload,
    runSummary: FlowLeniaEcology2025RunSummary,
    trajectoryFrames: [LeniaTrajectoryFrame],
    activitySummary: ActivitySummary?,
    exportedAt: Date,
    encoder: JSONEncoder
) throws -> FlowLeniaEcology2025RunRecord {
    let baseURL = runDirectory.appendingPathComponent("base.json")
    let payloadURL = runDirectory.appendingPathComponent("payload.json")
    let metadataURL = runDirectory.appendingPathComponent("meta.json")
    try encoder.encode(replayBaseConfig).write(to: baseURL)
    try encoder.encode(replayPayload).write(to: payloadURL)
    try encoder.encode(FlowLeniaEcology2025RunMetadata(
        runID: runID,
        campaignID: campaignID,
        bundleKind: .flowLeniaEcology2025ArenaReplayBundleV1,
        runSummary: runSummary,
        exportedAt: exportedAt
    )).write(to: metadataURL)
    let trajectoryFramesURL = trajectoryFrames.isEmpty
        ? nil
        : runDirectory.appendingPathComponent("trajectory-frames.jsonl")
    if let trajectoryFramesURL {
        try writeJSONLines(trajectoryFrames, to: trajectoryFramesURL)
    }
    let activitySummaryURL = activitySummary.map { _ in
        runDirectory.appendingPathComponent("activity-summary.json")
    }
    return FlowLeniaEcology2025RunRecord(
        trialID: flowLeniaEcology2025TrialID(runSummary),
        runID: runID,
        campaignID: campaignID,
        bundleKind: .flowLeniaEcology2025ArenaReplayBundleV1,
        variant: runSummary.variant,
        mutationProbability: runSummary.mutationProbability,
        repeatIndex: runSummary.repeatIndex,
        bundleDir: runDirectory.path,
        baseConfigPath: baseURL.path,
        payloadPath: payloadURL.path,
        metadataPath: metadataURL.path,
        summaryPath: runDirectory.appendingPathComponent("summary.json").path,
        framesPath: runDirectory.appendingPathComponent("frames.jsonl").path,
        trajectoryFramesPath: trajectoryFramesURL?.path,
        activitySummaryPath: activitySummaryURL?.path,
        exportedAt: exportedAt
    )
}

public func writeFlowLeniaEcology2025RunIndex(records: [FlowLeniaEcology2025RunRecord], to url: URL) throws {
    guard !records.isEmpty else { return }
    try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    encoder.dateEncodingStrategy = .deferredToDate
    try writeJSONLines(records, to: url, encoder: encoder)
}

func flowLeniaEcology2025TrialID(_ summary: FlowLeniaEcology2025RunSummary) -> String {
    "\(summary.variant)-pmut=\(flowLeniaFloatLabel(summary.mutationProbability))-repeat=\(summary.repeatIndex)"
}
