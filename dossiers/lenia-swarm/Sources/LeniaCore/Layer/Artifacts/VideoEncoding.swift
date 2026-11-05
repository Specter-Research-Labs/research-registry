import Foundation

public enum RawVideoPixelFormat: String, Sendable {
    case gray
    case bgra

    var bytesPerPixel: Int {
        switch self {
        case .gray: 1
        case .bgra: 4
        }
    }
}

public enum VideoEncodingError: Error, LocalizedError {
    case executableNotFound(String)
    case noFrames(URL)
    case frameGeometryChanged(expected: String, actual: String)
    case frameSizeMismatch(expected: Int, actual: Int)
    case encoderFailed(String)

    public var errorDescription: String? {
        switch self {
        case .executableNotFound(let name):
            return "ffmpeg executable '\(name)' was not found; install ffmpeg or pass its path."
        case .noFrames(let url):
            return "No frames were sent to the encoder for \(url.path)."
        case .frameGeometryChanged(let expected, let actual):
            return "Video frames must keep one size: started at \(expected), got \(actual)."
        case .frameSizeMismatch(let expected, let actual):
            return "Raw video frame stores \(actual) bytes but expected \(expected)."
        case .encoderFailed(let message):
            return "ffmpeg failed: \(message)"
        }
    }
}

public func resolveExecutable(_ name: String) throws -> URL {
    if name.contains("/") {
        let url = URL(fileURLWithPath: (name as NSString).expandingTildeInPath)
        guard FileManager.default.isExecutableFile(atPath: url.path) else {
            throw VideoEncodingError.executableNotFound(name)
        }
        return url
    }
    let searchPath = ProcessInfo.processInfo.environment["PATH"] ?? ""
    for directory in searchPath.split(separator: ":") {
        let candidate = URL(fileURLWithPath: String(directory)).appendingPathComponent(name)
        if FileManager.default.isExecutableFile(atPath: candidate.path) {
            return candidate
        }
    }
    throw VideoEncodingError.executableNotFound(name)
}

public final class MP4FrameSink {
    fileprivate let ffmpegURL: URL
    fileprivate let outputURL: URL
    fileprivate let fps: Int
    fileprivate let pixelFormat: RawVideoPixelFormat
    fileprivate var process: Process?
    fileprivate var input: FileHandle?
    fileprivate var stderrURL: URL?
    private var geometry: (width: Int, height: Int)?
    public private(set) var frameCount = 0

    fileprivate init(ffmpegURL: URL, outputURL: URL, fps: Int, pixelFormat: RawVideoPixelFormat) {
        self.ffmpegURL = ffmpegURL
        self.outputURL = outputURL
        self.fps = fps
        self.pixelFormat = pixelFormat
    }

    public func append(_ frame: Data, width: Int, height: Int) throws {
        if let geometry {
            guard geometry == (width, height) else {
                throw VideoEncodingError.frameGeometryChanged(
                    expected: "\(geometry.width)x\(geometry.height)",
                    actual: "\(width)x\(height)"
                )
            }
        } else {
            try start(width: width, height: height)
            geometry = (width, height)
        }
        let expected = width * height * pixelFormat.bytesPerPixel
        guard frame.count == expected else {
            throw VideoEncodingError.frameSizeMismatch(expected: expected, actual: frame.count)
        }
        guard let input else {
            preconditionFailure("encoder input is opened by start(width:height:)")
        }
        do {
            try input.write(contentsOf: frame)
        } catch {
            throw VideoEncodingError.encoderFailed("stdin closed after \(frameCount) frames: \(try waitForFailure())")
        }
        frameCount += 1
    }

    private func start(width: Int, height: Int) throws {
        let stderrURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("lenia-ffmpeg-\(UUID().uuidString).log")
        guard FileManager.default.createFile(atPath: stderrURL.path, contents: nil) else {
            throw VideoEncodingError.encoderFailed("could not create \(stderrURL.path)")
        }
        let stdin = Pipe()
        let process = Process()
        process.executableURL = ffmpegURL
        process.arguments = [
            "-v", "error",
            "-y",
            "-f", "rawvideo",
            "-pix_fmt", pixelFormat.rawValue,
            "-s", "\(width)x\(height)",
            "-framerate", String(fps),
            "-i", "pipe:0",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            outputURL.path,
        ]
        process.standardInput = stdin
        process.standardOutput = FileHandle.nullDevice
        let stderrHandle = try FileHandle(forWritingTo: stderrURL)
        process.standardError = stderrHandle
        try process.run()
        try stderrHandle.close()
        self.process = process
        self.input = stdin.fileHandleForWriting
        self.stderrURL = stderrURL
    }

    fileprivate func finish() throws {
        guard let process, let input else {
            throw VideoEncodingError.noFrames(outputURL)
        }
        try input.close()
        process.waitUntilExit()
        let log = try consumeStderr()
        guard process.terminationStatus == 0 else {
            throw VideoEncodingError.encoderFailed("exit \(process.terminationStatus): \(log)")
        }
        let values = try outputURL.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey])
        guard values.isRegularFile == true, (values.fileSize ?? 0) > 0 else {
            throw VideoEncodingError.encoderFailed("no non-empty output at \(outputURL.path)")
        }
    }

    fileprivate func abort() {
        if let input {
            try? input.close()
        }
        if let process {
            if process.isRunning {
                process.terminate()
            }
            process.waitUntilExit()
        }
        _ = try? consumeStderr()
        try? FileManager.default.removeItem(at: outputURL)
    }

    private func waitForFailure() throws -> String {
        guard let process else { return "" }
        process.waitUntilExit()
        return "exit \(process.terminationStatus): \(try consumeStderr())"
    }

    private func consumeStderr() throws -> String {
        guard let stderrURL else { return "" }
        let log = try String(contentsOf: stderrURL, encoding: .utf8)
        try FileManager.default.removeItem(at: stderrURL)
        self.stderrURL = nil
        return log.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

// Frames stream to ffmpeg's stdin as raw video, so encoding never stages image
// files on disk. A throwing body or encoder failure removes the partial output.
public func encodeMP4(
    ffmpeg: String,
    outputURL: URL,
    fps: Int,
    pixelFormat: RawVideoPixelFormat,
    frames body: (MP4FrameSink) throws -> Void
) throws {
    precondition(fps > 0, "MP4 fps must be > 0")
    // Writing to a pipe whose reader exited raises SIGPIPE; ignoring it turns
    // that into a thrown EPIPE so the ffmpeg error can be reported.
    signal(SIGPIPE, SIG_IGN)
    let sink = MP4FrameSink(
        ffmpegURL: try resolveExecutable(ffmpeg),
        outputURL: outputURL,
        fps: fps,
        pixelFormat: pixelFormat
    )
    do {
        try body(sink)
        try sink.finish()
    } catch {
        sink.abort()
        throw error
    }
}
