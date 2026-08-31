import Foundation
import LeniaCore

private let dossierRootURL = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent()
    .deletingLastPathComponent()
    .deletingLastPathComponent()

public struct WarehouseRefreshResult: Codable {
    public let warehousePath: String
    public let compendiumPath: String
    public let studyId: String
    public let axesUpdated: Int
    public let statusUpdated: Int
    public let anatomyUpdated: Int
    public let topologyStudyId: String?

    public init(
        warehousePath: String,
        compendiumPath: String,
        studyId: String,
        axesUpdated: Int,
        statusUpdated: Int,
        anatomyUpdated: Int,
        topologyStudyId: String?
    ) {
        self.warehousePath = warehousePath
        self.compendiumPath = compendiumPath
        self.studyId = studyId
        self.axesUpdated = axesUpdated
        self.statusUpdated = statusUpdated
        self.anatomyUpdated = anatomyUpdated
        self.topologyStudyId = topologyStudyId
    }
}

public struct WarehouseTopologyResult: Codable {
    public let warehousePath: String
    public let studyId: String
    public let topologyStudyId: String

    public init(warehousePath: String, studyId: String, topologyStudyId: String) {
        self.warehousePath = warehousePath
        self.studyId = studyId
        self.topologyStudyId = topologyStudyId
    }
}

public enum WarehouseBridgeError: LocalizedError {
    case commandFailed(command: [String], output: String)
    case invalidResponse(String)

    public var errorDescription: String? {
        switch self {
        case .commandFailed(let command, let output):
            let rendered = command.joined(separator: " ")
            return "Warehouse refresh failed: \(rendered)\n\(output)"
        case .invalidResponse(let output):
            return "Warehouse refresh returned invalid JSON:\n\(output)"
        }
    }
}

public func resolvedWarehousePath(explicitPath: String?, compendiumPath: String) -> String {
    explicitPath ?? defaultWarehousePath(compendiumPath: compendiumPath)
}

func runFileBackedWarehouseCommand(
    executableURL: URL,
    arguments: [String],
    currentDirectoryURL: URL?
) throws -> Data {
    let fileManager = FileManager.default
    let captureDirectory = fileManager.temporaryDirectory
        .appendingPathComponent("lenia-warehouse-\(UUID().uuidString)", isDirectory: true)
    try fileManager.createDirectory(at: captureDirectory, withIntermediateDirectories: true)
    defer { try? fileManager.removeItem(at: captureDirectory) }

    let stdoutURL = captureDirectory.appendingPathComponent("stdout.json")
    let stderrURL = captureDirectory.appendingPathComponent("stderr.log")
    guard fileManager.createFile(atPath: stdoutURL.path, contents: nil),
          fileManager.createFile(atPath: stderrURL.path, contents: nil) else {
        throw WarehouseBridgeError.invalidResponse("Unable to create warehouse process capture files.")
    }
    let stdoutHandle = try FileHandle(forWritingTo: stdoutURL)
    let stderrHandle = try FileHandle(forWritingTo: stderrURL)

    let process = Process()
    process.executableURL = executableURL
    process.arguments = arguments
    process.currentDirectoryURL = currentDirectoryURL

    process.standardOutput = stdoutHandle
    process.standardError = stderrHandle

    do {
        try process.run()
        process.waitUntilExit()
        try stdoutHandle.close()
        try stderrHandle.close()
    } catch {
        try? stdoutHandle.close()
        try? stderrHandle.close()
        throw error
    }

    let stdoutData = try Data(contentsOf: stdoutURL)
    let stderrData = try Data(contentsOf: stderrURL)
    let stdout = String(decoding: stdoutData, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
    let stderr = String(decoding: stderrData, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)

    guard process.terminationStatus == 0 else {
        let output = [stdout, stderr]
            .filter { !$0.isEmpty }
            .joined(separator: "\n")
        throw WarehouseBridgeError.commandFailed(
            command: [executableURL.path] + arguments,
            output: output
        )
    }
    guard !stdoutData.isEmpty else {
        throw WarehouseBridgeError.invalidResponse(stdout)
    }
    return stdoutData
}

func runWarehouseCLI(arguments: [String]) throws -> Data {
    try runFileBackedWarehouseCommand(
        executableURL: URL(fileURLWithPath: "/usr/bin/env"),
        arguments: arguments,
        currentDirectoryURL: dossierRootURL
    )
}

private func decodeWarehouseJSON<T: Decodable>(_ data: Data, as type: T.Type) throws -> T {
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    do {
        return try decoder.decode(type, from: data)
    } catch {
        let output = String(decoding: data, as: UTF8.self)
        throw WarehouseBridgeError.invalidResponse(output)
    }
}

@discardableResult
public func refreshWarehouseFromCompendium(
    compendiumPath: String,
    warehousePath: String,
    label: String? = nil,
    topology: Bool = false
) throws -> WarehouseRefreshResult {
    let warehouseURL = URL(fileURLWithPath: warehousePath)
    try FileManager.default.createDirectory(
        at: warehouseURL.deletingLastPathComponent(),
        withIntermediateDirectories: true
    )

    var arguments = [
        "uv",
        "run",
        "lenia-swarm-analysis",
        "morphospace",
        "refresh-compendium",
        "--warehouse",
        warehousePath,
        "--compendium",
        compendiumPath,
        "--json",
    ]
    if let label, !label.isEmpty {
        arguments.append(contentsOf: ["--label", label])
    }
    if topology {
        arguments.append("--topology")
    }
    let data = try runWarehouseCLI(arguments: arguments)
    return try decodeWarehouseJSON(data, as: WarehouseRefreshResult.self)
}

public func runWarehouseTopology(
    warehousePath: String,
    studyId: String,
    sourcePacketKind: String = "focal",
    minGroupSize: Int = 2,
    maxHomologyDim: Int = 1
) throws -> WarehouseTopologyResult {
    let data = try runWarehouseCLI(arguments: [
        "uv",
        "run",
        "lenia-swarm-analysis",
        "morphospace",
        "run-topology",
        "--warehouse",
        warehousePath,
        "--study-id",
        studyId,
        "--source-packet-kind",
        sourcePacketKind,
        "--min-group-size",
        String(minGroupSize),
        "--max-homology-dim",
        String(maxHomologyDim),
        "--json",
    ])
    return try decodeWarehouseJSON(data, as: WarehouseTopologyResult.self)
}

public func exportWarehouseBiologicalPacket(
    warehousePath: String,
    studyId: String,
    contextStudyId: String? = nil
) throws -> [String: AnyCodable] {
    var arguments = [
        "uv",
        "run",
        "lenia-swarm-analysis",
        "morphospace",
        "export-biological",
        "--warehouse",
        warehousePath,
        "--study-id",
        studyId,
        "--json",
    ]
    if let contextStudyId, !contextStudyId.isEmpty {
        arguments.append(contentsOf: ["--context-study-id", contextStudyId])
    }
    let data = try runWarehouseCLI(arguments: arguments)
    return try decodeWarehouseJSON(data, as: [String: AnyCodable].self)
}

public func exportWarehouseCreatureDiscoveryPacket(
    warehousePath: String,
    studyId: String? = nil,
    lens: String? = nil
) throws -> [String: AnyCodable] {
    var arguments = [
        "uv",
        "run",
        "lenia-swarm-analysis",
        "morphospace",
        "export-creature-discovery",
        "--warehouse",
        warehousePath,
        "--json",
    ]
    if let studyId, !studyId.isEmpty {
        arguments.append(contentsOf: ["--study-id", studyId])
    }
    if let lens, !lens.isEmpty {
        arguments.append(contentsOf: ["--lens", lens])
    }
    let data = try runWarehouseCLI(arguments: arguments)
    return try decodeWarehouseJSON(data, as: [String: AnyCodable].self)
}
