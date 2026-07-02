import Foundation

/// Write a batch of encodable items as newline-delimited JSON, creating (or
/// truncating) the file at `url`. The caller supplies the encoder so output
/// formatting (sorted keys, date strategy) stays explicit per call site.
func writeJSONLines<T: Encodable>(_ items: [T], to url: URL, encoder: JSONEncoder = JSONEncoder()) throws {
    FileManager.default.createFile(atPath: url.path, contents: nil)
    let handle = try FileHandle(forWritingTo: url)
    defer { try? handle.close() }
    for item in items {
        handle.write(try encoder.encode(item))
        handle.write(Data([0x0A]))
    }
}

/// Append one encodable item as a JSON line to an already-open handle (the
/// caller owns the handle's lifecycle), for incremental streaming writes.
func appendJSONLine<T: Encodable>(_ item: T, to handle: FileHandle, encoder: JSONEncoder) throws {
    handle.write(try encoder.encode(item))
    handle.write(Data([0x0A]))
}

/// Append one encodable item as a JSON line to the file at `url`, seeking to the
/// end so existing lines are preserved. The file must already exist.
func appendJSONLine<T: Encodable>(_ item: T, to url: URL, encoder: JSONEncoder = JSONEncoder()) throws {
    let handle = try FileHandle(forWritingTo: url)
    defer { try? handle.close() }
    try handle.seekToEnd()
    handle.write(try encoder.encode(item))
    handle.write(Data([0x0A]))
}
