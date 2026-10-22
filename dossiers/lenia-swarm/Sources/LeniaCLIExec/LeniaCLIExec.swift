import LeniaCore
import LeniaCLIKit
import Foundation
#if !canImport(Metal)
import MLX
#endif

private func failStartup(_ message: String) -> Never {
    if let data = (message.hasSuffix("\n") ? message : "\(message)\n").data(using: .utf8) {
        FileHandle.standardError.write(data)
    }
    exit(EXIT_FAILURE)
}

@main
struct LeniaCLIExec {
    static func main() async {
        #if canImport(Metal)
        do {
            try LeniaMetalLibrarySupport.ensureAvailable()
        } catch {
            failStartup("LeniaCLI startup failed: \(error.localizedDescription)")
        }
        #else
        // MLX defaults to its GPU device, which Linux builds do not have.
        Device.setDefault(device: .cpu)
        #endif
        await LeniaSwarm.main()
    }
}
