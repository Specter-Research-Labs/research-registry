import LeniaCore
import LeniaCLIKit
import Foundation
import Darwin

private func failStartup(_ message: String) -> Never {
    if let data = (message.hasSuffix("\n") ? message : "\(message)\n").data(using: .utf8) {
        FileHandle.standardError.write(data)
    }
    exit(EXIT_FAILURE)
}

@main
struct LeniaCLIExec {
    static func main() async {
        do {
            try LeniaMetalLibrarySupport.ensureAvailable()
        } catch {
            failStartup("LeniaCLI startup failed: \(error.localizedDescription)")
        }

        guard #available(macOS 10.15, *) else {
            failStartup("LeniaCLI startup failed: requires macOS 10.15 or newer.")
        }
        await LeniaSwarm.main()
    }
}
