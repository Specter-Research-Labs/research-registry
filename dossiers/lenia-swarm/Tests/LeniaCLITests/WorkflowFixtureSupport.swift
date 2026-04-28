import Foundation
import XCTest

private let leniaCLITestSupportRoot = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent()
    .deletingLastPathComponent()
    .deletingLastPathComponent()

func dossierConfigsRoot() -> URL {
    leniaCLITestSupportRoot.appendingPathComponent("configs", isDirectory: true)
}

func makeTempDirectory(prefix: String) throws -> URL {
    let url = FileManager.default.temporaryDirectory
        .appendingPathComponent("\(prefix)-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    return url
}

func writeJSON(_ object: Any, to url: URL) throws {
    try writeJSONObject(object, to: url)
}

func writeJSONObject(_ object: Any, to url: URL) throws {
    let data = try JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys])
    try data.write(to: url)
}

func writeJSONL<T: Encodable>(_ values: [T], to url: URL) throws {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    encoder.dateEncodingStrategy = .deferredToDate
    let content = try values.reduce(into: Data()) { data, value in
        data.append(try encoder.encode(value))
        data.append(0x0A)
    }
    try content.write(to: url)
}

func rewriteJSONFile(
    at url: URL,
    mutate: (inout [String: Any]) throws -> Void
) throws {
    let data = try Data(contentsOf: url)
    var root = try XCTUnwrap(
        JSONSerialization.jsonObject(with: data) as? [String: Any],
        "Expected JSON object at \(url.path)"
    )
    try mutate(&root)
    let rewritten = try JSONSerialization.data(withJSONObject: root, options: [.prettyPrinted, .sortedKeys])
    try rewritten.write(to: url)
}

func copyConfigFixture(
    relativePath: String,
    to destination: URL,
    mutate: ((inout [String: Any]) throws -> Void)? = nil
) throws {
    try FileManager.default.copyItem(
        at: dossierConfigsRoot().appendingPathComponent(relativePath),
        to: destination
    )
    if let mutate {
        try rewriteJSONFile(at: destination, mutate: mutate)
    }
}

func makeRunLayout(at runDir: URL) throws {
    let fm = FileManager.default
    try fm.createDirectory(at: runDir.appendingPathComponent("library", isDirectory: true), withIntermediateDirectories: true)
    try fm.createDirectory(at: runDir.appendingPathComponent("overall", isDirectory: true), withIntermediateDirectories: true)
    try fm.createDirectory(at: runDir.appendingPathComponent("exports", isDirectory: true), withIntermediateDirectories: true)
}

func countJSONLLines(at url: URL) throws -> Int {
    try String(contentsOf: url, encoding: .utf8)
        .split(separator: "\n")
        .count
}

func decodeSingleJSONL<T: Decodable>(_ type: T.Type, from url: URL) throws -> T {
    let line = try XCTUnwrap(
        String(contentsOf: url, encoding: .utf8)
            .split(whereSeparator: \.isNewline)
            .first
    )
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .deferredToDate
    return try decoder.decode(T.self, from: Data(line.utf8))
}
