import Foundation

public enum ResearchSeedRankMetric: String, CaseIterable, Codable, Sendable {
    case score
    case recordedAt = "recorded_at"
    case displacement
    case pathLength = "path_length"
    case speedMean = "speed_mean"
    case occupancyMean = "occupancy_mean"
    case massMean = "mass_mean"
    case varianceMean = "variance_mean"
    case energyMean = "energy_mean"
    case gyration
    case centerVelocity = "center_velocity"
    case activityDiversityMean = "activity_diversity_mean"
    case activitySpeciesMean = "activity_species_mean"
    case isStable = "is_stable"
}

public struct ResearchSeedSelection: Codable, Sendable {
    public let sourceIDs: [String]
    public let names: [String]
    public let top: Int?
    public let rankBy: ResearchSeedRankMetric?
    public let ascending: Bool

    public init(
        sourceIDs: [String] = [],
        names: [String] = [],
        top: Int? = nil,
        rankBy: ResearchSeedRankMetric? = nil,
        ascending: Bool = false
    ) {
        self.sourceIDs = sourceIDs
        self.names = names
        self.top = top
        self.rankBy = rankBy
        self.ascending = ascending
    }
}

public struct ResearchSeedPatch: Codable, Sendable {
    public let sourceID: String
    public let name: String
    public let world: WorldState
    public let runID: String?
    public let campaignID: String?
    public let recordedAt: Date?
    public let score: Float?
    public let metrics: SimulationMetrics?
    public let kernelParams: KernelParams?
    public let kernelSources: [Int]?
    public let kernelTargets: [Int]?

    public init(
        sourceID: String,
        name: String,
        world: WorldState,
        runID: String? = nil,
        campaignID: String? = nil,
        recordedAt: Date? = nil,
        score: Float? = nil,
        metrics: SimulationMetrics? = nil,
        kernelParams: KernelParams? = nil,
        kernelSources: [Int]? = nil,
        kernelTargets: [Int]? = nil
    ) {
        self.sourceID = sourceID
        self.name = name
        self.world = world
        self.runID = runID
        self.campaignID = campaignID
        self.recordedAt = recordedAt
        self.score = score
        self.metrics = metrics
        self.kernelParams = kernelParams
        self.kernelSources = kernelSources
        self.kernelTargets = kernelTargets
    }

    public init(
        sourceID: String,
        name: String,
        width: Int,
        height: Int,
        channels: Int,
        data: [Float],
        runID: String? = nil,
        campaignID: String? = nil,
        recordedAt: Date? = nil,
        score: Float? = nil,
        metrics: SimulationMetrics? = nil,
        kernelParams: KernelParams? = nil,
        kernelSources: [Int]? = nil,
        kernelTargets: [Int]? = nil
    ) {
        self.init(
            sourceID: sourceID,
            name: name,
            world: WorldState(width: width, height: height, channels: channels, values: data),
            runID: runID,
            campaignID: campaignID,
            recordedAt: recordedAt,
            score: score,
            metrics: metrics,
            kernelParams: kernelParams,
            kernelSources: kernelSources,
            kernelTargets: kernelTargets
        )
    }

    private enum CodingKeys: String, CodingKey {
        case sourceID, name, width, height, channels, data, runID, campaignID, recordedAt, score, metrics
        case kernelParams, kernelSources, kernelTargets
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        sourceID = try container.decode(String.self, forKey: .sourceID)
        name = try container.decode(String.self, forKey: .name)
        let width = try container.decode(Int.self, forKey: .width)
        let height = try container.decode(Int.self, forKey: .height)
        let channels = try container.decode(Int.self, forKey: .channels)
        let data = try container.decode([Float].self, forKey: .data)
        world = WorldState(width: width, height: height, channels: channels, values: data)
        runID = try container.decodeIfPresent(String.self, forKey: .runID)
        campaignID = try container.decodeIfPresent(String.self, forKey: .campaignID)
        recordedAt = try container.decodeIfPresent(Date.self, forKey: .recordedAt)
        score = try container.decodeIfPresent(Float.self, forKey: .score)
        metrics = try container.decodeIfPresent(SimulationMetrics.self, forKey: .metrics)
        kernelParams = try container.decodeIfPresent(KernelParams.self, forKey: .kernelParams)
        kernelSources = try container.decodeIfPresent([Int].self, forKey: .kernelSources)
        kernelTargets = try container.decodeIfPresent([Int].self, forKey: .kernelTargets)
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(sourceID, forKey: .sourceID)
        try container.encode(name, forKey: .name)
        try container.encode(world.width, forKey: .width)
        try container.encode(world.height, forKey: .height)
        try container.encode(world.channels, forKey: .channels)
        try container.encode(world.values, forKey: .data)
        try container.encodeIfPresent(runID, forKey: .runID)
        try container.encodeIfPresent(campaignID, forKey: .campaignID)
        try container.encodeIfPresent(recordedAt, forKey: .recordedAt)
        try container.encodeIfPresent(score, forKey: .score)
        try container.encodeIfPresent(metrics, forKey: .metrics)
        try container.encodeIfPresent(kernelParams, forKey: .kernelParams)
        try container.encodeIfPresent(kernelSources, forKey: .kernelSources)
        try container.encodeIfPresent(kernelTargets, forKey: .kernelTargets)
    }
}

public func loadResearchSeedPatches(
    libraryURL: URL,
    qdConfigDirectoryOverride: URL? = nil,
    cells: [Int]? = nil,
    warmupSteps: Int? = nil,
    cropThreshold: Float = 0.05,
    padding: Int = 6,
    selection: ResearchSeedSelection? = nil
) throws -> [ResearchSeedPatch] {
    let kind = detectResearchSeedLibraryKind(libraryURL)
    let patches: [ResearchSeedPatch]
    switch kind {
    case .qd2024:
        let seeds = try loadQD2024SeedsFromLibrary(
            libraryURL: libraryURL,
            qdConfigDirectoryOverride: qdConfigDirectoryOverride,
            cells: cells
        )
        patches = seeds.map { seed in
            let patch = qd2024ActivePatch(seed: seed)
            return ResearchSeedPatch(
                sourceID: "qd2024-cell-\(seed.elite.cell)",
                name: seed.pattern.name,
                width: patch.width,
                height: patch.height,
                channels: patch.channels,
                data: patch.values,
                score: seed.elite.fitness,
                kernelParams: seed.kernelParams,
                kernelSources: seed.pattern.kernels.map(\.c0),
                kernelTargets: seed.pattern.kernels.map(\.c1)
            )
        }
    case .exports:
        guard cells == nil || cells?.isEmpty == true else {
            throw ConfigError.invalidConfig("Explicit seed cells are only supported for qd-2024 libraries.")
        }
        patches = try loadResearchSeedPatchesFromExportIndex(
            indexURL: libraryURL,
            warmupSteps: warmupSteps,
            cropThreshold: cropThreshold,
            padding: padding
        )
    case .seedPatches:
        guard cells == nil || cells?.isEmpty == true else {
            throw ConfigError.invalidConfig("Explicit seed cells are only supported for qd-2024 libraries.")
        }
        patches = try loadResearchSeedPatchesFromPatchIndex(indexURL: libraryURL)
    case .localLibrary:
        guard cells == nil || cells?.isEmpty == true else {
            throw ConfigError.invalidConfig("Explicit seed cells are only supported for qd-2024 libraries.")
        }
        patches = try loadResearchSeedPatchesFromLocalLibrary(
            indexURL: libraryURL,
            warmupSteps: warmupSteps,
            cropThreshold: cropThreshold,
            padding: padding
        )
    }
    return selectResearchSeedPatches(patches, selection: selection)
}

public func researchSeedCenterCropPatchValues(
    patch: ResearchSeedPatch,
    size: Int,
    outputChannels: Int
) throws -> [Float] {
    guard size > 0 else {
        throw ConfigError.invalidConfig("research seed patch size must be > 0.")
    }
    guard outputChannels > 0 else {
        throw ConfigError.invalidConfig("research seed outputChannels must be > 0.")
    }
    guard size <= patch.world.width, size <= patch.world.height else {
        throw ConfigError.invalidConfig("research seed patch size \(size) exceeds patch dimensions \(patch.world.width)x\(patch.world.height).")
    }

    let startX = max(0, (patch.world.width - size) / 2)
    let startY = max(0, (patch.world.height - size) / 2)
    var out: [Float] = []
    out.reserveCapacity(size * size * outputChannels)
    for x in startX..<(startX + size) {
        for y in startY..<(startY + size) {
            let sourceBase = ((x * patch.world.height) + y) * patch.world.channels
            for channel in 0..<outputChannels {
                out.append(channel < patch.world.channels ? patch.world.values[sourceBase + channel] : 0)
            }
        }
    }
    return out
}

public func researchSeedResizedMassInitialization(
    patch: ResearchSeedPatch,
    size: Int
) throws -> [[Float]] {
    guard size > 0 else {
        throw ConfigError.invalidConfig("research seed initialization size must be > 0.")
    }
    let mass = researchSeedMassMap(patch: patch)
    let bbox = researchSeedActiveBoundingBox(
        massMap: mass,
        width: patch.world.width,
        height: patch.world.height,
        threshold: 1e-5
    )
    let sourceWidth = bbox.width
    let sourceHeight = bbox.height
    var out = Array(
        repeating: Array(repeating: Float(0), count: size),
        count: size
    )
    for row in 0..<size {
        let srcY = bbox.minY + min(sourceHeight - 1, Int(Float(row) / Float(max(size - 1, 1)) * Float(max(sourceHeight - 1, 0))))
        for col in 0..<size {
            let srcX = bbox.minX + min(sourceWidth - 1, Int(Float(col) / Float(max(size - 1, 1)) * Float(max(sourceWidth - 1, 0))))
            out[row][col] = mass[srcY * patch.world.width + srcX]
        }
    }
    return out
}

func researchSeedActiveBoundingBox(
    massMap: [Float],
    width: Int,
    height: Int,
    threshold: Float
) -> (minX: Int, minY: Int, width: Int, height: Int) {
    var minX = width
    var minY = height
    var maxX = -1
    var maxY = -1
    for y in 0..<height {
        for x in 0..<width {
            if massMap[y * width + x] > threshold {
                minX = min(minX, x)
                minY = min(minY, y)
                maxX = max(maxX, x)
                maxY = max(maxY, y)
            }
        }
    }
    if maxX < minX || maxY < minY {
        let side = min(width, height)
        let startX = max(0, (width - side) / 2)
        let startY = max(0, (height - side) / 2)
        return (startX, startY, side, side)
    }
    return (minX, minY, maxX - minX + 1, maxY - minY + 1)
}

func expandedSeedBounds(
    bounds: (minX: Int, minY: Int, width: Int, height: Int),
    width: Int,
    height: Int,
    padding: Int
) -> (minX: Int, minY: Int, maxX: Int, maxY: Int) {
    let maxX = bounds.minX + bounds.width - 1
    let maxY = bounds.minY + bounds.height - 1
    return (
        minX: max(0, bounds.minX - padding),
        minY: max(0, bounds.minY - padding),
        maxX: min(width - 1, maxX + padding),
        maxY: min(height - 1, maxY + padding)
    )
}

private enum ResearchSeedLibraryKind {
    case qd2024
    case exports
    case seedPatches
    case localLibrary
}

private func detectResearchSeedLibraryKind(_ libraryURL: URL) -> ResearchSeedLibraryKind {
    let parent = libraryURL.deletingLastPathComponent()
    let runDirectory = parent.deletingLastPathComponent()
    if parent.lastPathComponent == "exports" {
        return .exports
    }
    if libraryURL.lastPathComponent == "patches.jsonl" || isResearchSeedPatchJSONL(libraryURL) {
        return .seedPatches
    }
    let repertoireURL = runDirectory
        .appendingPathComponent("repertoire", isDirectory: true)
        .appendingPathComponent("occupied.json")
    if FileManager.default.fileExists(atPath: repertoireURL.path) {
        return .qd2024
    }
    return .localLibrary
}

private func isResearchSeedPatchJSONL(_ libraryURL: URL) -> Bool {
    guard libraryURL.pathExtension == "jsonl",
          let data = try? firstJSONLRecordData(from: libraryURL),
          let text = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines),
          !text.isEmpty
    else {
        return false
    }
    return (try? JSONDecoder().decode(ResearchSeedPatch.self, from: Data(text.utf8))) != nil
}

private func firstJSONLRecordData(from url: URL, maxBytes: Int = 16 * 1024 * 1024) throws -> Data {
    let handle = try FileHandle(forReadingFrom: url)
    defer { try? handle.close() }

    var record = Data()
    var bytesRead = 0
    var recordCompleted = false
    while bytesRead < maxBytes {
        guard let chunk = try handle.read(upToCount: min(64 * 1024, maxBytes - bytesRead)),
              !chunk.isEmpty
        else {
            break
        }
        bytesRead += chunk.count
        for byte in chunk {
            if byte == 0x0A {
                if record.allSatisfy({ $0 == 0x20 || $0 == 0x09 || $0 == 0x0D }) {
                    record.removeAll(keepingCapacity: true)
                    continue
                } else {
                    recordCompleted = true
                    break
                }
            }
            record.append(byte)
        }
        if recordCompleted {
            break
        }
    }
    return record
}

private func loadResearchSeedPatchesFromExportIndex(
    indexURL: URL,
    warmupSteps: Int?,
    cropThreshold: Float,
    padding: Int
) throws -> [ResearchSeedPatch] {
    let records: [CreatureExportRecord] = try decodeJSONLines(indexURL)
    return try records.map { record in
        let exportDir = URL(fileURLWithPath: record.exportDir, isDirectory: true)
        let metaURL = exportDir.appendingPathComponent("meta.json")
        let decoder = JSONDecoder()
        let metadata = try decodeCreatureExportMetadata(
            Data(contentsOf: metaURL),
            decoder: decoder,
            fallbackBundleKind: record.bundleKind
        )
        let projection = resolveSpecimenProjection(
            id: researchSeedProjectionID(
                manifest: metadata.specimenManifest,
                fallback: record.creatureId
            ),
            name: metadata.creature.name,
            ownerId: metadata.creature.ownerId,
            manifest: metadata.specimenManifest,
            fallbackGenotype: metadata.creature.genotype,
            fallbackInitialCondition: metadata.creature.initialCondition,
            fallbackMetrics: metadata.creature.metrics,
            sweep: metadata.creature.sweep,
            score: metadata.score ?? metadata.creature.score,
            scoreWeights: metadata.creature.scoreWeights,
            fallbackInitialConditionFamily: metadata.creature.initialConditionFamily,
            fallbackDescriptorBundle: metadata.creature.descriptorBundle,
            fallbackConfigHash: metadata.creature.configHash,
            fallbackRuntimeFamily: metadata.runtimeFamily,
            fallbackRuntimeCapabilities: metadata.runtimeCapabilities
        )
        switch record.bundleKind {
        case .strictReplayBundleV1:
            guard let baseConfigPath = record.baseConfigPath,
                  let searchConfigPath = record.searchConfigPath else {
                throw ConfigError.invalidConfig("Strict Flow Lenia replay bundle is missing base/search config paths: \(record.exportDir)")
            }
            return try expressResearchSeedPatch(
                baseConfigURL: URL(fileURLWithPath: baseConfigPath),
                searchConfigURL: URL(fileURLWithPath: searchConfigPath),
                creature: projection.creature,
                name: projection.creature.name,
                sourceID: projection.creature.id.uuidString,
                runID: metadata.runId,
                campaignID: metadata.campaignId,
                recordedAt: metadata.exportedAt,
                score: metadata.score ?? projection.creature.score,
                metrics: projection.creature.metrics,
                warmupSteps: warmupSteps,
                cropThreshold: cropThreshold,
                padding: padding
            )
        case .qd24PaperReplayBundleV1, .sensorimotor24PaperReplayBundleV1:
            guard let statePatch = projection.creature.initialCondition.state_patch else {
                throw ConfigError.invalidConfig("Paper replay bundle is missing initialCondition.state_patch for seed extraction: \(record.exportDir)")
            }
            return researchSeedPatchFromStatePatch(
                statePatch: statePatch,
                name: projection.creature.name,
                sourceID: projection.creature.id.uuidString,
                runID: metadata.runId,
                campaignID: metadata.campaignId,
                recordedAt: metadata.exportedAt,
                score: metadata.score ?? projection.creature.score,
                metrics: projection.creature.metrics,
                kernelParams: projection.creature.genotype,
                cropThreshold: cropThreshold,
                padding: padding
            )
        case .flowLeniaEcology2025ArenaReplayBundleV1:
            throw ConfigError.invalidConfig("Flow Lenia ecology arena bundles are replay trajectories, not seed extraction bundles: \(record.exportDir)")
        }
    }
}

private func loadResearchSeedPatchesFromLocalLibrary(
    indexURL: URL,
    warmupSteps: Int?,
    cropThreshold: Float,
    padding: Int
) throws -> [ResearchSeedPatch] {
    let decoder = JSONDecoder()
    let entries = try String(contentsOf: indexURL, encoding: .utf8)
        .split(whereSeparator: \.isNewline)
        .map(String.init)
        .filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        .map { try decodeResearchLibraryEntry(Data($0.utf8), decoder: decoder) }
    let runDirectory = indexURL
        .deletingLastPathComponent()
        .deletingLastPathComponent()
    let baseConfigURL = runDirectory.appendingPathComponent("config.json")
    let searchConfigURL = runDirectory.appendingPathComponent("search.json")
    return try entries.map { entry in
        let projection = resolveSpecimenProjection(
            id: researchSeedProjectionID(
                manifest: entry.specimenManifest,
                fallback: entry.creature.id
            ),
            name: entry.creature.name,
            ownerId: entry.creature.ownerId,
            manifest: entry.specimenManifest,
            fallbackGenotype: entry.creature.genotype,
            fallbackInitialCondition: entry.creature.initialCondition,
            fallbackMetrics: entry.creature.metrics,
            sweep: entry.creature.sweep,
            score: entry.creature.score,
            scoreWeights: entry.creature.scoreWeights,
            fallbackInitialConditionFamily: entry.creature.initialConditionFamily,
            fallbackDescriptorBundle: entry.creature.descriptorBundle,
            fallbackConfigHash: entry.configHash,
            fallbackRuntimeFamily: entry.runtimeFamily,
            fallbackRuntimeCapabilities: entry.runtimeCapabilities,
            fallbackSourceMode: entry.sourceMode,
            fallbackSourceAlgorithm: entry.sourceAlgorithm,
            fallbackResearchMetadata: entry.researchMetadata
        )
        return try expressResearchSeedPatch(
            baseConfigURL: baseConfigURL,
            searchConfigURL: searchConfigURL,
            creature: projection.creature,
            name: projection.creature.name,
            sourceID: projection.creature.id.uuidString,
            runID: entry.runId,
            campaignID: entry.campaignId,
            recordedAt: entry.recordedAt,
            score: projection.creature.score,
            metrics: projection.creature.metrics,
            warmupSteps: warmupSteps,
            cropThreshold: cropThreshold,
            padding: padding
        )
    }
}

private func loadResearchSeedPatchesFromPatchIndex(indexURL: URL) throws -> [ResearchSeedPatch] {
    try decodeJSONLines(indexURL)
}

private func researchSeedProjectionID(
    manifest: SpecimenManifest?,
    fallback: UUID
) -> UUID {
    guard let raw = manifest?.creatureID ?? manifest?.specimenID,
          let id = UUID(uuidString: raw) else {
        return fallback
    }
    return id
}

private func expressResearchSeedPatch(
    baseConfigURL: URL,
    searchConfigURL: URL,
    creature: SavedCreature,
    name: String,
    sourceID: String,
    runID: String?,
    campaignID: String?,
    recordedAt: Date?,
    score: Float?,
    metrics: SimulationMetrics,
    warmupSteps: Int?,
    cropThreshold: Float,
    padding: Int
) throws -> ResearchSeedPatch {
    let decoder = JSONDecoder()
    let baseConfig = try decoder.decode(LeniaBaseConfig.self, from: Data(contentsOf: baseConfigURL))
    let searchConfig = try decoder.decode(ParsedSearchConfig.self, from: Data(contentsOf: searchConfigURL))
    let replayBaseConfig = try buildReplayBaseConfig(
        baseConfig: baseConfig,
        searchConfig: searchConfig,
        creature: creature
    )
    let replaySearchConfig = buildReplaySearchConfig(from: searchConfig)
    let baseData = try JSONEncoder().encode(replayBaseConfig)
    let runtimeConfig = try loadRuntimeConfig(from: baseData)
    let engine = SearchEngine(runtimeConfig: runtimeConfig)
    let effectiveWarmup = warmupSteps ?? max(80, replaySearchConfig.warmupSteps)
    return engine.expressedSeedPatch(
        name: name,
        sourceID: sourceID,
        runID: runID,
        campaignID: campaignID,
        recordedAt: recordedAt,
        score: score,
        metrics: metrics,
        warmupSteps: effectiveWarmup,
        cropThreshold: cropThreshold,
        padding: padding
    )
}

private func decodeJSONLines<T: Decodable>(_ url: URL) throws -> [T] {
    let decoder = JSONDecoder()
    return try String(contentsOf: url, encoding: .utf8)
        .split(whereSeparator: \.isNewline)
        .map(String.init)
        .filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        .map { try decoder.decode(T.self, from: Data($0.utf8)) }
}

private func researchSeedPatchFromStatePatch(
    statePatch: InitStatePatchConfig,
    name: String,
    sourceID: String,
    runID: String?,
    campaignID: String?,
    recordedAt: Date?,
    score: Float?,
    metrics: SimulationMetrics?,
    kernelParams: KernelParams? = nil,
    cropThreshold: Float,
    padding: Int
) -> ResearchSeedPatch {
    let fullPatch = ResearchSeedPatch(
        sourceID: sourceID,
        name: name,
        world: statePatch.toWorldState(),
        runID: runID,
        campaignID: campaignID,
        recordedAt: recordedAt,
        score: score,
        metrics: metrics,
        kernelParams: kernelParams
    )
    let massMap = researchSeedMassMap(patch: fullPatch)
    let bounds = researchSeedActiveBoundingBox(
        massMap: massMap,
        width: fullPatch.world.width,
        height: fullPatch.world.height,
        threshold: cropThreshold
    )
    let expanded = expandedSeedBounds(
        bounds: bounds,
        width: fullPatch.world.width,
        height: fullPatch.world.height,
        padding: padding
    )
    let croppedWidth = expanded.maxX - expanded.minX + 1
    let croppedHeight = expanded.maxY - expanded.minY + 1
    var cropped: [Float] = []
    cropped.reserveCapacity(croppedWidth * croppedHeight * fullPatch.world.channels)
    for x in expanded.minX...expanded.maxX {
        for y in expanded.minY...expanded.maxY {
            let base = ((x * fullPatch.world.height) + y) * fullPatch.world.channels
            for channel in 0..<fullPatch.world.channels {
                cropped.append(fullPatch.world.values[base + channel])
            }
        }
    }
    return ResearchSeedPatch(
        sourceID: sourceID,
        name: name,
        width: croppedWidth,
        height: croppedHeight,
        channels: fullPatch.world.channels,
        data: cropped,
        runID: runID,
        campaignID: campaignID,
        recordedAt: recordedAt,
        score: score,
        metrics: metrics,
        kernelParams: kernelParams
    )
}

private func researchSeedMassMap(patch: ResearchSeedPatch) -> [Float] {
    var out = [Float](repeating: 0, count: patch.world.width * patch.world.height)
    for x in 0..<patch.world.width {
        for y in 0..<patch.world.height {
            let base = ((x * patch.world.height) + y) * patch.world.channels
            var total: Float = 0
            for channel in 0..<patch.world.channels {
                total += patch.world.values[base + channel]
            }
            out[y * patch.world.width + x] = total
        }
    }
    return out
}

func expressedSeedMassMap(
    world: WorldState,
    excludedChannels: Set<Int>
) -> [Float] {
    var out = [Float](repeating: 0, count: world.width * world.height)
    for x in 0..<world.width {
        for y in 0..<world.height {
            let base = ((x * world.height) + y) * world.channels
            var total: Float = 0
            for channel in 0..<world.channels where !excludedChannels.contains(channel) {
                total += world.values[base + channel]
            }
            out[y * world.width + x] = total
        }
    }
    return out
}

private func selectResearchSeedPatches(
    _ patches: [ResearchSeedPatch],
    selection: ResearchSeedSelection?
) -> [ResearchSeedPatch] {
    guard let selection else {
        return patches
    }

    var selected = patches
    if !selection.sourceIDs.isEmpty {
        selected = selected.filter { patch in
            selection.sourceIDs.contains(where: { requested in
                let normalizedRequested = requested.lowercased()
                let normalizedSource = patch.sourceID.lowercased()
                return normalizedSource == normalizedRequested || normalizedSource.hasPrefix(normalizedRequested)
            })
        }
    }

    if !selection.names.isEmpty {
        let normalizedNames = Set(selection.names.map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() })
        selected = selected.filter { patch in
            normalizedNames.contains(patch.name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased())
        }
    }

    let rankMetric = selection.rankBy ?? (selection.top != nil ? .score : nil)
    if let rankMetric {
        selected = selected
            .enumerated()
            .sorted { lhsEntry, rhsEntry in
                let lhsValue = researchSeedRankValue(lhsEntry.element, metric: rankMetric)
                let rhsValue = researchSeedRankValue(rhsEntry.element, metric: rankMetric)
                switch (lhsValue, rhsValue) {
                case let (lhsRank?, rhsRank?):
                    if lhsRank == rhsRank {
                        return lhsEntry.offset < rhsEntry.offset
                    }
                    return selection.ascending ? lhsRank < rhsRank : lhsRank > rhsRank
                case (_?, nil):
                    return true
                case (nil, _?):
                    return false
                case (nil, nil):
                    return lhsEntry.offset < rhsEntry.offset
                }
            }
            .map(\.element)
    }

    if let top = selection.top {
        selected = Array(selected.prefix(top))
    }
    return selected
}

private func researchSeedRankValue(
    _ patch: ResearchSeedPatch,
    metric: ResearchSeedRankMetric
) -> Double? {
    switch metric {
    case .score:
        return patch.score.map(Double.init)
    case .recordedAt:
        return patch.recordedAt?.timeIntervalSinceReferenceDate
    case .displacement:
        return patch.metrics.map { Double($0.displacement) }
    case .pathLength:
        return patch.metrics.map { Double($0.pathLength) }
    case .speedMean:
        return patch.metrics.map { Double($0.speedMean) }
    case .occupancyMean:
        return patch.metrics.map { Double($0.occupancyMean) }
    case .massMean:
        return patch.metrics.map { Double($0.massMean) }
    case .varianceMean:
        return patch.metrics.map { Double($0.varianceMean) }
    case .energyMean:
        return patch.metrics.map { Double($0.energyMean) }
    case .gyration:
        return patch.metrics.map { Double($0.gyration) }
    case .centerVelocity:
        return patch.metrics.map { Double($0.centerVelocity) }
    case .activityDiversityMean:
        return patch.metrics?.activityDiversityMean.map(Double.init)
    case .activitySpeciesMean:
        return patch.metrics?.activitySpeciesMean.map(Double.init)
    case .isStable:
        return patch.metrics.map { $0.isStable ? 1.0 : 0.0 }
    }
}
