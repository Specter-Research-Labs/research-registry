import Foundation

enum TestCLIProcessError: Error, CustomStringConvertible {
    case missingExecutable([String])
    case failed(arguments: [String], status: Int32, stdout: String, stderr: String)

    var description: String {
        switch self {
        case .missingExecutable(let candidates):
            return "Missing LeniaCLI executable. Looked in: \(candidates.joined(separator: ", "))"
        case .failed(let arguments, let status, let stdout, let stderr):
            return """
                LeniaCLI failed with status \(status)
                args: \(arguments.joined(separator: " "))
                stdout:
                \(stdout)
                stderr:
                \(stderr)
                """
        }
    }
}

private let leniaCLITestPackageRoot = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent()
    .deletingLastPathComponent()
    .deletingLastPathComponent()

private func leniaCLIExecutableURL() throws -> URL {
    let candidates = [
        leniaCLITestPackageRoot.appendingPathComponent(".build/debug/LeniaCLI"),
        leniaCLITestPackageRoot.appendingPathComponent(".build/arm64-apple-macosx/debug/LeniaCLI"),
        leniaCLITestPackageRoot.appendingPathComponent(".build/x86_64-apple-macosx/debug/LeniaCLI"),
    ]
    for candidate in candidates where FileManager.default.isExecutableFile(atPath: candidate.path) {
        return candidate
    }
    throw TestCLIProcessError.missingExecutable(candidates.map(\.path))
}

@discardableResult
func runLeniaCLI(arguments: [String], currentDirectory: URL? = nil) throws -> String {
    let process = Process()
    process.executableURL = try leniaCLIExecutableURL()
    process.arguments = arguments
    process.currentDirectoryURL = currentDirectory ?? leniaCLITestPackageRoot

    let stdoutPipe = Pipe()
    let stderrPipe = Pipe()
    process.standardOutput = stdoutPipe
    process.standardError = stderrPipe

    try process.run()
    process.waitUntilExit()

    let stdout = String(decoding: stdoutPipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
    let stderr = String(decoding: stderrPipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
    if process.terminationStatus != 0 {
        throw TestCLIProcessError.failed(
            arguments: arguments,
            status: process.terminationStatus,
            stdout: stdout,
            stderr: stderr
        )
    }
    return stdout + stderr
}
