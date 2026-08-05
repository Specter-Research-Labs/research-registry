import Foundation

public enum LeniaMetalLibrarySupport {
    private static let swiftPMBundleName = "mlx-swift_Cmlx"
    private static let xcodeDeveloperDir = "/Applications/Xcode.app/Contents/Developer"

    public enum Error: Swift.Error, LocalizedError {
        case missingExecutableURL
        case missingMLXSourceRoot(String)
        case noMetalSources(String)
        case toolFailed(String)

        public var errorDescription: String? {
            switch self {
            case .missingExecutableURL:
                return "Unable to resolve the current executable path for MLX metallib setup."
            case .missingMLXSourceRoot(let path):
                return "Unable to locate the MLX shader sources at \(path)."
            case .noMetalSources(let path):
                return "No MLX metal shader sources were found under \(path)."
            case .toolFailed(let message):
                return message
            }
        }
    }

    public static func ensureAvailable(executableURL: URL? = Bundle.main.executableURL) throws {
        guard let executableURL else {
            throw Error.missingExecutableURL
        }

        let fileManager = FileManager.default
        let binaryDir = executableURL.deletingLastPathComponent()
        let installTargets = installationTargets(binaryDir: binaryDir)
        if let configuredLibraryURL = configuredLibraryURL() {
            guard fileManager.fileExists(atPath: configuredLibraryURL.path) else {
                throw Error.toolFailed("MLX_METAL_PATH points to a missing metallib at \(configuredLibraryURL.path).")
            }
            let writableTargets = installTargets.filter { isWritableInstallTarget($0, fileManager: fileManager) }
            guard !writableTargets.isEmpty else {
                throw Error.toolFailed("MLX_METAL_PATH is set, but there is no writable MLX metallib install location.")
            }
            try installLibrary(at: configuredLibraryURL, into: writableTargets, fileManager: fileManager)
            return
        }
        let packageRoot = defaultPackageRoot()
        let sourceRoot = packageRoot
            .appendingPathComponent(".build/checkouts/mlx-swift/Source/Cmlx/mlx", isDirectory: true)
        let cacheURL = packageRoot
            .appendingPathComponent(".build/lenia-metal-cache", isDirectory: true)
            .appendingPathComponent("mlx.metallib")

        if let existingURL = existingLibraryURL(installTargets: installTargets, fileManager: fileManager) {
            if fileManager.fileExists(atPath: sourceRoot.path),
               try shouldRebuildCache(sourceRoot: sourceRoot, cacheURL: cacheURL, fileManager: fileManager)
            {
                try installLibrary(at: existingURL, into: [cacheURL], fileManager: fileManager)
            }
            return
        }

        guard fileManager.fileExists(atPath: sourceRoot.path) else {
            throw Error.missingMLXSourceRoot(sourceRoot.path)
        }

        if try shouldRebuildCache(sourceRoot: sourceRoot, cacheURL: cacheURL, fileManager: fileManager) {
            try compileMetallib(sourceRoot: sourceRoot, outputURL: cacheURL, fileManager: fileManager)
        }

        let writableTargets = installTargets.filter { isWritableInstallTarget($0, fileManager: fileManager) }
        guard !writableTargets.isEmpty else {
            throw Error.toolFailed("Unable to find a writable MLX metallib install location.")
        }
        try installLibrary(at: cacheURL, into: writableTargets, fileManager: fileManager)
    }

    private static func existingLibraryURL(installTargets: [URL], fileManager: FileManager) -> URL? {
        installTargets.first { fileManager.fileExists(atPath: $0.path) }
    }

    private static func configuredLibraryURL() -> URL? {
        guard let rawPath = ProcessInfo.processInfo.environment["MLX_METAL_PATH"]?
            .trimmingCharacters(in: .whitespacesAndNewlines),
            !rawPath.isEmpty else {
            return nil
        }
        return URL(fileURLWithPath: rawPath)
    }

    private static func installationTargets(binaryDir: URL) -> [URL] {
        var targets: [URL] = [
            binaryDir.appendingPathComponent("mlx.metallib"),
            binaryDir.appendingPathComponent("default.metallib"),
        ]

        let bundleResourceRoots = ([Bundle.main.resourceURL].compactMap { $0 } + Bundle.allBundles.compactMap(\.resourceURL) + Bundle.allFrameworks.compactMap(\.resourceURL))
            .map { $0.standardizedFileURL }

        var seen = Set<String>()
        for resourceRoot in bundleResourceRoots where seen.insert(resourceRoot.path).inserted {
            let bundleRoot = resourceRoot.appendingPathComponent("\(swiftPMBundleName).bundle", isDirectory: true)
            targets.append(bundleRoot.appendingPathComponent("default.metallib"))
            targets.append(
                bundleRoot
                    .appendingPathComponent("Contents/Resources", isDirectory: true)
                    .appendingPathComponent("default.metallib")
            )
        }

        return deduplicatedURLs(targets)
    }

    private static func deduplicatedURLs(_ urls: [URL]) -> [URL] {
        var seen = Set<String>()
        return urls.filter { seen.insert(canonicalURL($0).path).inserted }
    }

    private static func canonicalURL(_ url: URL) -> URL {
        url.standardizedFileURL.resolvingSymlinksInPath().standardizedFileURL
    }

    private static func installLibrary(at sourceURL: URL, into targets: [URL], fileManager: FileManager) throws {
        let canonicalSource = canonicalURL(sourceURL)
        for targetURL in targets {
            try fileManager.createDirectory(
                at: targetURL.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            let canonicalTarget = canonicalURL(targetURL)
            if canonicalSource.path == canonicalTarget.path {
                continue
            }
            if fileManager.fileExists(atPath: targetURL.path) {
                if matchingCopyMetadata(
                    sourcePath: canonicalSource.path,
                    targetPath: canonicalTarget.path,
                    fileManager: fileManager
                ) {
                    continue
                }
                if fileManager.contentsEqual(atPath: canonicalSource.path, andPath: canonicalTarget.path) {
                    continue
                }
                try fileManager.removeItem(at: targetURL)
            }
            try fileManager.copyItem(at: sourceURL, to: targetURL)
        }
    }

    private static func matchingCopyMetadata(
        sourcePath: String,
        targetPath: String,
        fileManager: FileManager
    ) -> Bool {
        guard let source = try? fileManager.attributesOfItem(atPath: sourcePath),
              let target = try? fileManager.attributesOfItem(atPath: targetPath),
              let sourceSize = source[.size] as? NSNumber,
              let targetSize = target[.size] as? NSNumber,
              let sourceModified = source[.modificationDate] as? Date,
              let targetModified = target[.modificationDate] as? Date else {
            return false
        }
        return sourceSize == targetSize && sourceModified == targetModified
    }

    private static func isWritableInstallTarget(_ targetURL: URL, fileManager: FileManager) -> Bool {
        var candidate = targetURL.deletingLastPathComponent()
        while !fileManager.fileExists(atPath: candidate.path) {
            let parent = candidate.deletingLastPathComponent()
            if parent.path == candidate.path {
                return false
            }
            candidate = parent
        }
        return fileManager.isWritableFile(atPath: candidate.path)
    }

    private static func compileMetallib(sourceRoot: URL, outputURL: URL, fileManager: FileManager) throws {
        let kernelsRoot = sourceRoot.appendingPathComponent("mlx/backend/metal/kernels", isDirectory: true)
        let buildRoot = outputURL.deletingLastPathComponent()
            .appendingPathComponent("lenia-metal-build", isDirectory: true)
        try fileManager.createDirectory(at: outputURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        try fileManager.createDirectory(at: buildRoot, withIntermediateDirectories: true)

        let metalSources = try discoverMetalSources(in: kernelsRoot, fileManager: fileManager)
        guard !metalSources.isEmpty else {
            throw Error.noMetalSources(kernelsRoot.path)
        }

        var airFiles: [URL] = []
        airFiles.reserveCapacity(metalSources.count)

        for sourceURL in metalSources {
            let relativePath = sourceURL.path.replacingOccurrences(of: kernelsRoot.path + "/", with: "")
            let airURL = buildRoot
                .appendingPathComponent(relativePath)
                .deletingPathExtension()
                .appendingPathExtension("air")
            try fileManager.createDirectory(at: airURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            try runTool(
                "/usr/bin/xcrun",
                arguments: [
                    "-sdk", "macosx",
                    "metal",
                    "-x", "metal",
                    "-std=metal3.2",
                    "-Wall",
                    "-Wextra",
                    "-fno-fast-math",
                    "-Wno-c++17-extensions",
                    "-Wno-c++20-extensions",
                    "-c", sourceURL.path,
                    "-I", sourceRoot.path,
                    "-I", kernelsRoot.path,
                    "-o", airURL.path,
                ]
            )
            airFiles.append(airURL)
        }

        try runTool(
            "/usr/bin/xcrun",
            arguments: ["-sdk", "macosx", "metallib"] + airFiles.map(\.path) + ["-o", outputURL.path]
        )
    }

    private static func shouldRebuildCache(sourceRoot: URL, cacheURL: URL, fileManager: FileManager) throws -> Bool {
        guard fileManager.fileExists(atPath: cacheURL.path) else {
            return true
        }

        let sourceTimestamp = try latestSourceTimestamp(in: sourceRoot, fileManager: fileManager)
        let cacheValues = try cacheURL.resourceValues(forKeys: [.contentModificationDateKey])
        guard let cacheTimestamp = cacheValues.contentModificationDate else {
            return true
        }
        return sourceTimestamp > cacheTimestamp
    }

    private static func latestSourceTimestamp(in sourceRoot: URL, fileManager: FileManager) throws -> Date {
        let kernelsRoot = sourceRoot.appendingPathComponent("mlx/backend/metal/kernels", isDirectory: true)
        guard let enumerator = fileManager.enumerator(
            at: kernelsRoot,
            includingPropertiesForKeys: [.contentModificationDateKey, .isRegularFileKey],
            options: [.skipsHiddenFiles]
        ) else {
            throw Error.noMetalSources(kernelsRoot.path)
        }

        var latest = Date.distantPast
        for case let url as URL in enumerator {
            guard let values = try? url.resourceValues(forKeys: [.isRegularFileKey, .contentModificationDateKey]),
                  values.isRegularFile == true else {
                continue
            }
            guard ["metal", "h"].contains(url.pathExtension) else { continue }
            if let modifiedAt = values.contentModificationDate, modifiedAt > latest {
                latest = modifiedAt
            }
        }
        return latest
    }

    private static func discoverMetalSources(in kernelsRoot: URL, fileManager: FileManager) throws -> [URL] {
        guard let enumerator = fileManager.enumerator(
            at: kernelsRoot,
            includingPropertiesForKeys: [.isRegularFileKey],
            options: [.skipsHiddenFiles]
        ) else {
            return []
        }

        var sources: [URL] = []
        for case let url as URL in enumerator {
            guard url.pathExtension == "metal" else { continue }
            let relativePath = url.path.replacingOccurrences(of: kernelsRoot.path + "/", with: "")
            if relativePath.contains("_nax") {
                continue
            }
            sources.append(url)
        }
        return sources.sorted { $0.path < $1.path }
    }

    private static func runTool(_ launchPath: String, arguments: [String]) throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: launchPath)
        process.arguments = arguments
        process.environment = toolEnvironment()

        let stdout = Pipe()
        let stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr

        try process.run()
        process.waitUntilExit()

        guard process.terminationStatus == 0 else {
            let output = String(data: stderr.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
                .trimmingCharacters(in: .whitespacesAndNewlines)
            let message = output?.isEmpty == false ? output! : "Command failed: \(launchPath) \(arguments.joined(separator: " "))"
            throw Error.toolFailed(message)
        }
    }

    private static func toolEnvironment() -> [String: String] {
        var environment = ProcessInfo.processInfo.environment
        for key in environment.keys where key.hasPrefix("NIX_") {
            environment.removeValue(forKey: key)
        }
        for key in ["CC", "CXX", "SDKROOT", "TOOLCHAINS", "LD", "LD_DYLD_PATH", "LIBRARY_PATH"] {
            environment.removeValue(forKey: key)
        }
        if FileManager.default.fileExists(atPath: xcodeDeveloperDir) {
            environment["DEVELOPER_DIR"] = xcodeDeveloperDir
        } else {
            environment.removeValue(forKey: "DEVELOPER_DIR")
        }
        return environment
    }

    private static func defaultPackageRoot(filePath: String = #filePath) -> URL {
        URL(fileURLWithPath: filePath)
            .deletingLastPathComponent() // Metal/
            .deletingLastPathComponent() // Core/
            .deletingLastPathComponent() // LeniaCore/
            .deletingLastPathComponent() // Sources/
            .deletingLastPathComponent() // package root
    }
}
