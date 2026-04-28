import Foundation
import Logging

public struct LogConfig {
    public let runId: String
    public let nodeId: String
    public let role: String
    public let logLevel: Logger.Level
    public let logToConsole: Bool
    public let logFileURL: URL?
    public let metricsFileURL: URL?
    public let extraMetadata: Logger.Metadata

    public init(
        runId: String,
        nodeId: String,
        role: String,
        logLevel: Logger.Level,
        logToConsole: Bool,
        logFileURL: URL?,
        metricsFileURL: URL?,
        extraMetadata: Logger.Metadata = [:]
    ) {
        self.runId = runId
        self.nodeId = nodeId
        self.role = role
        self.logLevel = logLevel
        self.logToConsole = logToConsole
        self.logFileURL = logFileURL
        self.metricsFileURL = metricsFileURL
        self.extraMetadata = extraMetadata
    }
}

private final class LoggingState: @unchecked Sendable {
    static let shared = LoggingState()
    let lock = NSLock()
    var didBootstrap = false
    var baseMetadata: Logger.Metadata = [:]
    var metricsRecorder: MetricsRecorder?
}

public enum LeniaLogging {
    private static let state = LoggingState.shared

    public static func bootstrap(_ config: LogConfig) throws {
        state.lock.lock()
        defer { state.lock.unlock() }

        guard !state.didBootstrap else {
            fatalError("LeniaLogging.bootstrap called more than once.")
        }

        var metadata: Logger.Metadata = [
            "run_id": .string(config.runId),
            "node_id": .string(config.nodeId),
            "role": .string(config.role)
        ]
        metadata.merge(config.extraMetadata, uniquingKeysWith: { _, new in new })
        state.baseMetadata = metadata

        let logWriter: LogFileWriter?
        if let logFileURL = config.logFileURL {
            logWriter = try LogFileWriter(fileURL: logFileURL)
        } else {
            logWriter = nil
        }

        if let metricsFileURL = config.metricsFileURL {
            let metricsWriter = try LogFileWriter(fileURL: metricsFileURL)
            state.metricsRecorder = MetricsRecorder(writer: metricsWriter, baseFields: metadata)
        } else {
            state.metricsRecorder = nil
        }

        let logLevel = config.logLevel
        let logToConsole = config.logToConsole
        let metadataSnapshot = metadata
        let metadataProvider = LeniaLogging.baseMetadataSnapshot

        LoggingSystem.bootstrap { label in
            var handlers: [LogHandler] = []

            if logToConsole {
                var console = StreamLogHandler.standardError(label: label)
                console.logLevel = logLevel
                console.metadata = metadataSnapshot
                handlers.append(DynamicMetadataLogHandler(
                    handler: console,
                    metadataProvider: metadataProvider
                ))
            }

            if let logWriter = logWriter {
                var jsonl = JSONLLogHandler(label: label, writer: logWriter, logLevel: logLevel)
                jsonl.metadata = metadataSnapshot
                handlers.append(DynamicMetadataLogHandler(
                    handler: jsonl,
                    metadataProvider: metadataProvider
                ))
            }

            guard !handlers.isEmpty else {
                fatalError("No log handlers configured.")
            }

            if handlers.count == 1 {
                return handlers[0]
            }
            return MultiplexLogHandler(handlers)
        }

        state.didBootstrap = true
    }

    public static func makeLogger(label: String, extraMetadata: Logger.Metadata = [:]) -> Logger {
        var logger = Logger(label: label)
        for (key, value) in extraMetadata {
            logger[metadataKey: key] = value
        }
        return logger
    }

    public static func makeRunId(prefix: String) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        let stamp = formatter.string(from: Date())
        return "\(prefix)-\(stamp)"
    }

    public static func updateMetadata(_ metadata: Logger.Metadata) {
        state.lock.lock()
        defer { state.lock.unlock() }
        state.baseMetadata.merge(metadata, uniquingKeysWith: { _, new in new })
        state.metricsRecorder?.updateBaseFields(state.baseMetadata)
    }

    public static func baseMetadataSnapshot() -> Logger.Metadata {
        state.lock.lock()
        defer { state.lock.unlock() }
        return state.baseMetadata
    }

    public static func currentRunId() -> String {
        let metadata = baseMetadataSnapshot()
        guard let value = metadata["run_id"] else {
            fatalError("run_id metadata missing. Logging must be bootstrapped first.")
        }
        return metadataValueToString(value)
    }

    public static func currentNodeId() -> String {
        let metadata = baseMetadataSnapshot()
        guard let value = metadata["node_id"] else {
            fatalError("node_id metadata missing. Logging must be bootstrapped first.")
        }
        return metadataValueToString(value)
    }

    fileprivate static func recorder() -> MetricsRecorder? {
        state.lock.lock()
        defer { state.lock.unlock() }
        return state.metricsRecorder
    }
}

public enum LeniaMetrics {
    public static func counter(_ name: String, _ value: Double = 1.0, fields: [String: String] = [:]) {
        LeniaLogging.recorder()?.record(name: name, kind: "counter", value: value, fields: fields)
    }

    public static func gauge(_ name: String, _ value: Double, fields: [String: String] = [:]) {
        LeniaLogging.recorder()?.record(name: name, kind: "gauge", value: value, fields: fields)
    }

    public static func timing(_ name: String, _ value: Double, fields: [String: String] = [:]) {
        LeniaLogging.recorder()?.record(name: name, kind: "timing", value: value, fields: fields)
    }
}

fileprivate func metadataValueToString(_ value: Logger.Metadata.Value) -> String {
    switch value {
    case .string(let string):
        return string
    case .stringConvertible(let convertible):
        return String(describing: convertible)
    case .dictionary(let dictionary):
        let items = dictionary.keys.sorted().map { key -> String in
            let value = dictionary[key] ?? .string("")
            return "\(key)=\(metadataValueToString(value))"
        }
        return "{\(items.joined(separator: ","))}"
    case .array(let array):
        let items = array.map(metadataValueToString)
        return "[\(items.joined(separator: ","))]"
    @unknown default:
        return String(describing: value)
    }
}

private final class LogFileWriter: @unchecked Sendable {
    private let fileHandle: FileHandle
    private let lock = NSLock()
    private let formatter: ISO8601DateFormatter

    init(fileURL: URL) throws {
        let directory = fileURL.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        if !FileManager.default.fileExists(atPath: fileURL.path) {
            FileManager.default.createFile(atPath: fileURL.path, contents: nil)
        }

        self.fileHandle = try FileHandle(forWritingTo: fileURL)
        try self.fileHandle.seekToEnd()

        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        self.formatter = formatter
    }

    deinit {
        try? fileHandle.close()
    }

    func timestamp() -> String {
        lock.lock()
        defer { lock.unlock() }
        return formatter.string(from: Date())
    }

    func writeLine(_ line: String) {
        guard let data = (line + "\n").data(using: .utf8) else {
            return
        }
        lock.lock()
        defer { lock.unlock() }
        fileHandle.write(data)
    }
}

private struct DynamicMetadataLogHandler: LogHandler {
    private var handler: LogHandler
    private let metadataProvider: @Sendable () -> Logger.Metadata

    init(handler: LogHandler, metadataProvider: @escaping @Sendable () -> Logger.Metadata) {
        self.handler = handler
        self.metadataProvider = metadataProvider
    }

    var metadata: Logger.Metadata {
        get { handler.metadata }
        set { handler.metadata = newValue }
    }

    var logLevel: Logger.Level {
        get { handler.logLevel }
        set { handler.logLevel = newValue }
    }

    subscript(metadataKey key: String) -> Logger.Metadata.Value? {
        get { handler[metadataKey: key] }
        set { handler[metadataKey: key] = newValue }
    }

    func log(
        level: Logger.Level,
        message: Logger.Message,
        metadata: Logger.Metadata?,
        source: String,
        file: String,
        function: String,
        line: UInt
    ) {
        var combined = metadataProvider()
        if let metadata = metadata {
            combined.merge(metadata, uniquingKeysWith: { _, new in new })
        }
        handler.log(
            level: level,
            message: message,
            metadata: combined,
            source: source,
            file: file,
            function: function,
            line: line
        )
    }
}

private struct JSONLLogHandler: LogHandler {
    var metadata: Logger.Metadata = [:]
    var logLevel: Logger.Level

    private let label: String
    private let writer: LogFileWriter

    init(label: String, writer: LogFileWriter, logLevel: Logger.Level) {
        self.label = label
        self.writer = writer
        self.logLevel = logLevel
    }

    subscript(metadataKey key: String) -> Logger.Metadata.Value? {
        get { metadata[key] }
        set { metadata[key] = newValue }
    }

    func log(
        level: Logger.Level,
        message: Logger.Message,
        metadata: Logger.Metadata?,
        source: String,
        file: String,
        function: String,
        line: UInt
    ) {
        var record: [String: Any] = [
            "ts": writer.timestamp(),
            "level": level.rawValue,
            "msg": message.description,
            "label": label,
            "source": source,
            "file": (file as NSString).lastPathComponent,
            "function": function,
            "line": Int(line)
        ]

        var merged = self.metadata
        if let metadata = metadata {
            merged.merge(metadata, uniquingKeysWith: { _, new in new })
        }

        for (key, value) in merged {
            if record[key] == nil {
                record[key] = metadataValueToString(value)
            }
        }

        guard JSONSerialization.isValidJSONObject(record),
              let data = try? JSONSerialization.data(withJSONObject: record),
              let json = String(data: data, encoding: .utf8) else {
            fatalError("Failed to serialize log record.")
        }

        writer.writeLine(json)
    }
}

private final class MetricsRecorder: @unchecked Sendable {
    private let writer: LogFileWriter
    private let lock = NSLock()
    private var baseFields: [String: String]

    init(writer: LogFileWriter, baseFields: Logger.Metadata) {
        self.writer = writer
        self.baseFields = baseFields.mapValues { value in
            metadataValueToString(value)
        }
    }

    func updateBaseFields(_ metadata: Logger.Metadata) {
        let updated = metadata.mapValues { value in
            metadataValueToString(value)
        }
        lock.lock()
        baseFields = updated
        lock.unlock()
    }

    func record(name: String, kind: String, value: Double, fields: [String: String]) {
        lock.lock()
        let baseSnapshot = baseFields
        lock.unlock()

        var record: [String: Any] = [
            "ts": writer.timestamp(),
            "type": "metric",
            "name": name,
            "kind": kind,
            "value": value
        ]

        for (key, value) in baseSnapshot where record[key] == nil {
            record[key] = value
        }

        for (key, value) in fields where record[key] == nil {
            record[key] = value
        }

        guard JSONSerialization.isValidJSONObject(record),
              let data = try? JSONSerialization.data(withJSONObject: record),
              let json = String(data: data, encoding: .utf8) else {
            fatalError("Failed to serialize metric record.")
        }

        writer.writeLine(json)
    }
}
