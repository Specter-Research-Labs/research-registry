import Foundation

public func loadQD2024SeedsFromLibrary(
    libraryURL: URL,
    qdConfigDirectoryOverride: URL? = nil,
    cells: [Int]? = nil
) throws -> [LeniaBreeder2024ExpressedSeed] {
    let runDirectory = libraryURL
        .deletingLastPathComponent()
        .deletingLastPathComponent()
    let run = try loadLeniaBreeder2024ResolvedRun(
        runDirectory: runDirectory,
        configDirectoryOverride: qdConfigDirectoryOverride
    )
    let elites = try loadLeniaBreeder2024EliteSummaries(runDirectory: runDirectory)
    let requestedCells = try qd2024RequestedCells(libraryURL: libraryURL, explicit: cells)
    let eliteByCell = Dictionary(uniqueKeysWithValues: elites.map { ($0.cell, $0) })
    return try requestedCells.map { cell in
        guard let elite = eliteByCell[cell] else {
            throw ConfigError.invalidConfig("qd-2024 library requested cell \(cell), but it is missing from \(runDirectory.path)/repertoire/occupied.json.")
        }
        return try expressLeniaBreeder2024Seed(run: run, elite: elite)
    }
}

public func qd2024CenterCropPatchValues(
    seed: LeniaBreeder2024ExpressedSeed,
    size: Int,
    channels: [Int]? = nil
) throws -> [Float] {
    guard size > 0 else {
        throw ConfigError.invalidConfig("qd-2024 seed patch size must be > 0.")
    }
    let selectedChannels = channels ?? Array(0..<seed.world.channels)
    guard !selectedChannels.isEmpty else {
        throw ConfigError.invalidConfig("qd-2024 seed patch must include at least one channel.")
    }
    for channel in selectedChannels where channel < 0 || channel >= seed.world.channels {
        throw ConfigError.invalidConfig("qd-2024 seed patch channel \(channel) is out of range for \(seed.world.channels)-channel seed.")
    }
    guard size <= seed.world.width, size <= seed.world.height else {
        throw ConfigError.invalidConfig("qd-2024 seed patch size \(size) exceeds seed dimensions \(seed.world.width)x\(seed.world.height).")
    }

    let startX = max(0, (seed.world.width - size) / 2)
    let startY = max(0, (seed.world.height - size) / 2)
    var out: [Float] = []
    out.reserveCapacity(size * size * selectedChannels.count)
    for x in startX..<(startX + size) {
        for y in startY..<(startY + size) {
            for channel in selectedChannels {
                out.append(seed.world.values[qd2024WorldIndex(x: x, y: y, channel: channel, width: seed.world.width, height: seed.world.height, channels: seed.world.channels)])
            }
        }
    }
    return out
}

public func qd2024ResizedMassInitialization(
    seed: LeniaBreeder2024ExpressedSeed,
    size: Int
) throws -> [[Float]] {
    guard size > 0 else {
        throw ConfigError.invalidConfig("qd-2024 initialization size must be > 0.")
    }
    let mass = qd2024MassMap(seed: seed)
    let bbox = qd2024ActiveBoundingBox(
        massMap: mass,
        width: seed.world.width,
        height: seed.world.height,
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
            out[row][col] = mass[srcY * seed.world.width + srcX]
        }
    }
    return out
}

public func qd2024ActivePatch(seed: LeniaBreeder2024ExpressedSeed) -> WorldState {
    let mass = qd2024MassMap(seed: seed)
    let bbox = qd2024ActiveBoundingBox(
        massMap: mass,
        width: seed.world.width,
        height: seed.world.height,
        threshold: 1e-5
    )
    var data: [Float] = []
    data.reserveCapacity(bbox.width * bbox.height * seed.world.channels)
    for x in bbox.minX..<(bbox.minX + bbox.width) {
        for y in bbox.minY..<(bbox.minY + bbox.height) {
            for channel in 0..<seed.world.channels {
                data.append(seed.world.values[qd2024WorldIndex(x: x, y: y, channel: channel, width: seed.world.width, height: seed.world.height, channels: seed.world.channels)])
            }
        }
    }
    return WorldState(width: bbox.width, height: bbox.height, channels: seed.world.channels, values: data)
}

public func writeQD2024FamilyConfig(
    sourceConfigDirectory: URL,
    familyRoot: URL,
    familyID: String,
    familyName: String,
    derivedPattern: LeniaBreeder2024PatternSpec
) throws -> URL {
    let fileManager = FileManager.default
    try fileManager.createDirectory(at: familyRoot, withIntermediateDirectories: true)
    let patternsDirectory = familyRoot.appendingPathComponent("patterns", isDirectory: true)
    try fileManager.createDirectory(at: patternsDirectory, withIntermediateDirectories: true)

    for name in ["me.json", "aurora.json"] {
        let source = sourceConfigDirectory.appendingPathComponent(name)
        let target = familyRoot.appendingPathComponent(name)
        if fileManager.fileExists(atPath: target.path) {
            try fileManager.removeItem(at: target)
        }
        try fileManager.copyItem(at: source, to: target)
    }

    let baseURL = sourceConfigDirectory.appendingPathComponent("base.json")
    let baseObject = try JSONSerialization.jsonObject(with: Data(contentsOf: baseURL), options: [])
    guard var baseJSON = baseObject as? [String: Any] else {
        throw ConfigError.invalidConfig("qd-2024 base.json must decode as a JSON object.")
    }
    baseJSON["pattern_id"] = familyID
    let baseData = try JSONSerialization.data(withJSONObject: baseJSON, options: [.prettyPrinted, .sortedKeys])
    try baseData.write(to: familyRoot.appendingPathComponent("base.json"))

    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    try encoder.encode(
        LeniaBreeder2024PatternSpec(
            R: derivedPattern.R,
            T: derivedPattern.T,
            cells: derivedPattern.cells,
            kernels: derivedPattern.kernels,
            name: familyName
        )
    ).write(to: patternsDirectory.appendingPathComponent("\(familyID).json"))

    return familyRoot
}

private func qd2024RequestedCells(libraryURL: URL, explicit: [Int]?) throws -> [Int] {
    if let explicit, !explicit.isEmpty {
        return explicit
    }
    let decoder = JSONDecoder()
    let lines = try String(contentsOf: libraryURL)
        .split(whereSeparator: \.isNewline)
        .map(String.init)
        .filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    let entries = try lines.map { line in
        try decodeResearchLibraryEntry(Data(line.utf8), decoder: decoder)
    }
    let cells = entries.compactMap { entry -> Int? in
        let raw = entry.researchMetadata?["cell"]?.value
        switch raw {
        case let value as Int:
            return value
        case let value as Double:
            return Int(value)
        default:
            return nil
        }
    }
    guard !cells.isEmpty else {
        throw ConfigError.invalidConfig("qd-2024 library \(libraryURL.path) does not contain research_metadata.cell values.")
    }
    return cells
}

private func qd2024WorldIndex(
    x: Int,
    y: Int,
    channel: Int,
    width: Int,
    height: Int,
    channels: Int
) -> Int {
    ((x * height) + y) * channels + channel
}

private func qd2024MassMap(seed: LeniaBreeder2024ExpressedSeed) -> [Float] {
    var out = [Float](repeating: 0, count: seed.world.width * seed.world.height)
    for x in 0..<seed.world.width {
        for y in 0..<seed.world.height {
            var total: Float = 0
            for channel in 0..<seed.world.channels {
                total += seed.world.values[qd2024WorldIndex(x: x, y: y, channel: channel, width: seed.world.width, height: seed.world.height, channels: seed.world.channels)]
            }
            out[y * seed.world.width + x] = total
        }
    }
    return out
}

private func qd2024ActiveBoundingBox(
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
    let margin = 2
    minX = max(0, minX - margin)
    minY = max(0, minY - margin)
    maxX = min(width - 1, maxX + margin)
    maxY = min(height - 1, maxY + margin)
    return (minX, minY, maxX - minX + 1, maxY - minY + 1)
}
