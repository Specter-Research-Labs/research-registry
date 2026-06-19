import Foundation

func writeFlowLeniaEcologyFrames(_ frames: [FlowLeniaEcology2025FrameMetrics], to url: URL) throws {
    try writeJSONLines(frames, to: url)
}

private func writeFlowLeniaEcologyTrajectoryFrames(_ frames: [LeniaTrajectoryFrame], to url: URL) throws {
    guard !frames.isEmpty else {
        return
    }
    let massURL = url.appendingPathComponent("frames", isDirectory: true)
    let colorURL = url.appendingPathComponent("frames_color", isDirectory: true)
    try FileManager.default.createDirectory(at: massURL, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: colorURL, withIntermediateDirectories: true)
    for frame in frames {
        let name = String(format: "frame_%06d.png", frame.step)
        try writeGrayscalePNG(
            bytes: frame.bytes,
            width: frame.width,
            height: frame.height,
            to: massURL.appendingPathComponent(name)
        )
        if let foodBytes = frame.foodBytes {
            try writeRGBAPNG(
                rgba: flowLeniaEcologyFoodRGBA(mass: frame.bytes, food: foodBytes),
                width: frame.width,
                height: frame.height,
                to: colorURL.appendingPathComponent(name)
            )
        } else {
            try writeGrayscalePNG(
                bytes: frame.bytes,
                width: frame.width,
                height: frame.height,
                to: colorURL.appendingPathComponent(name)
            )
        }
    }
}

private func flowLeniaEcologyFoodRGBA(mass: Data, food: Data) throws -> Data {
    guard mass.count == food.count else {
        throw ConfigError.invalidConfig("food frame stores \(food.count) bytes but mass frame stores \(mass.count).")
    }
    var rgba = [UInt8](repeating: 0, count: mass.count * 4)
    for index in 0..<mass.count {
        let m = Float(mass[index]) / 255
        let f = Float(food[index]) / 255
        rgba[index * 4] = UInt8(min(255, m * 255 + f * 32))
        rgba[index * 4 + 1] = UInt8(min(255, m * 180 + f * 230))
        rgba[index * 4 + 2] = UInt8(min(255, m * 90 + f * 40))
        rgba[index * 4 + 3] = 255
    }
    return Data(rgba)
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
        : runDirectory.appendingPathComponent("trajectory-frames", isDirectory: true)
    if let trajectoryFramesURL {
        try writeFlowLeniaEcologyTrajectoryFrames(trajectoryFrames, to: trajectoryFramesURL)
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
