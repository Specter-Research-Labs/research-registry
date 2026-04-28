import Foundation
import LeniaArchive

func defaultStudioSupportRoot(fileManager: FileManager = .default) -> URL? {
    fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first?
        .appendingPathComponent("lenia-swarm", isDirectory: true)
}

func defaultStudioCompendiumPath(anchorFilePath: String) -> String? {
#if DEBUG
    let sourceURL = URL(fileURLWithPath: anchorFilePath).standardizedFileURL
    let repositoryRoot = findLeniaSwarmRoot(from: sourceURL)
#else
    let repositoryRoot: URL? = nil
#endif
    return firstAvailableCompendiumPath(
        repositoryRoot: repositoryRoot,
        supportRoot: defaultStudioSupportRoot()
    )
}

func findLeniaSwarmRoot(from url: URL) -> URL? {
    let parts = url.pathComponents
    guard let idx = parts.firstIndex(of: "dossiers"),
          idx + 1 < parts.count,
          parts[idx + 1] == "lenia-swarm" else {
        return nil
    }

    var root = URL(fileURLWithPath: "/")
    for part in parts[1...idx + 1] {
        root.appendPathComponent(part, isDirectory: true)
    }
    return root
}
