import Foundation
import LeniaCore

func encodeWarehousePacket(_ packet: [String: AnyCodable], pretty: Bool) throws -> Data {
    let encoder = JSONEncoder()
    encoder.outputFormatting = pretty ? [.prettyPrinted, .sortedKeys] : [.sortedKeys]
    return try encoder.encode(packet)
}

func writeWarehousePacket(
    _ packet: [String: AnyCodable],
    output: String,
    dossier: String
) throws -> String {
    let resolvedOutput = try resolveArtifactPath(output, dossier: dossier)
    let outputURL = URL(fileURLWithPath: resolvedOutput)
    try FileManager.default.createDirectory(
        at: outputURL.deletingLastPathComponent(),
        withIntermediateDirectories: true
    )
    try encodeWarehousePacket(packet, pretty: true).write(to: outputURL)
    return outputURL.path
}

func printWarehousePacket(_ packet: [String: AnyCodable], json: Bool) throws {
    let data = try encodeWarehousePacket(packet, pretty: !json)
    print(String(decoding: data, as: UTF8.self))
}

func packetDictionaryValue(_ packet: [String: AnyCodable], key: String) -> [String: Any]? {
    packet[key]?.value as? [String: Any]
}

func packetIntValue(_ dictionary: [String: Any]?, key: String) -> Int? {
    dictionary?[key] as? Int
}
