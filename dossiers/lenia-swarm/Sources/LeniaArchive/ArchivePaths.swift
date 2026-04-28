import Foundation

public func resolveCompendiumArtifactPath(
    outputRoot: String?,
    runDir: String?,
    path: String?
) -> String? {
    if let path, path.hasPrefix("/") || path.hasPrefix("~") {
        return (path as NSString).expandingTildeInPath
    }

    if let path,
       let runPath = resolveCompendiumArtifactPath(outputRoot: outputRoot, runDir: runDir, path: nil) {
        return URL(fileURLWithPath: runPath, isDirectory: true)
            .appendingPathComponent(path)
            .path
    }

    guard let runDir else { return nil }
    if runDir.hasPrefix("/") || runDir.hasPrefix("~") {
        return (runDir as NSString).expandingTildeInPath
    }

    guard let outputRoot else { return nil }
    let root = (outputRoot as NSString).expandingTildeInPath
    return URL(fileURLWithPath: root, isDirectory: true)
        .appendingPathComponent(runDir)
        .path
}

public func defaultWarehousePath(compendiumPath: String) -> String {
    URL(fileURLWithPath: compendiumPath)
        .deletingLastPathComponent()
        .appendingPathComponent("morphospace.duckdb")
        .path
}

public func defaultCompendiumPathCandidates(
    repositoryRoot: URL?,
    supportRoot: URL?
) -> [String] {
    var candidates: [String] = []

    if let repositoryRoot {
        candidates.append(
            repositoryRoot.appendingPathComponent("outputs")
                .appendingPathComponent("compendium.sqlite")
                .path
        )
    }

    if let supportRoot {
        candidates.append(
            supportRoot.appendingPathComponent("outputs")
                .appendingPathComponent("compendium.sqlite")
                .path
        )
    }

    var seen: Set<String> = []
    return candidates.filter { seen.insert($0).inserted }
}

public func firstAvailableCompendiumPath(
    repositoryRoot: URL?,
    supportRoot: URL?,
    fileManager: FileManager = .default
) -> String? {
    let candidates = defaultCompendiumPathCandidates(
        repositoryRoot: repositoryRoot,
        supportRoot: supportRoot
    )
    for candidate in candidates where usableCompendiumCandidate(candidate, fileManager: fileManager) {
        return candidate
    }
    return candidates.first
}

private func usableCompendiumCandidate(
    _ path: String,
    fileManager: FileManager
) -> Bool {
    guard fileManager.fileExists(atPath: path) else {
        return false
    }
    guard
        let attributes = try? fileManager.attributesOfItem(atPath: path),
        let fileSize = attributes[.size] as? NSNumber
    else {
        return false
    }
    return fileSize.int64Value > 0
}
