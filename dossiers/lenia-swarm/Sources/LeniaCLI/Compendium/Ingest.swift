import ArgumentParser
import Foundation

struct CompendiumIngestPlan {
    let runInputs: [RunInput]
    let resolvedDBPath: String
}

func resolveCompendiumIngestPlan(
    outputRoots: [String],
    runDirs: [String],
    dbPath: String?,
    repairOnly: Bool
) throws -> CompendiumIngestPlan {
    let hasOutputRoot = !outputRoots.isEmpty
    let hasRunDir = !runDirs.isEmpty

    if repairOnly {
        guard !(hasOutputRoot && hasRunDir) else {
            throw ValidationError("Provide at most one of --output-root or --run-dir when using --repair-only.")
        }
        guard hasOutputRoot || hasRunDir || dbPath != nil else {
            throw ValidationError("Provide --db when using --repair-only without --output-root or --run-dir.")
        }
    } else if hasOutputRoot == hasRunDir {
        throw ValidationError("Provide exactly one of --output-root or --run-dir.")
    }

    let runInputs = try hasOutputRoot
        ? collectRunInputs(outputRoots: outputRoots)
        : runDirs.map { try makeRunInput(runDir: $0) }
    if hasOutputRoot && runInputs.isEmpty {
        throw ValidationError("No run directories found under output root(s).")
    }

    return CompendiumIngestPlan(
        runInputs: runInputs,
        resolvedDBPath: try resolvedCompendiumDBPath(
            explicitDBPath: dbPath,
            outputRoots: outputRoots,
            runInputs: runInputs
        )
    )
}

@discardableResult
func executeCompendiumIngest(
    plan: CompendiumIngestPlan,
    rebuild: Bool,
    includeResults: Bool,
    repairOnly: Bool
) throws -> SQLiteIndexer {
    let indexer = try SQLiteIndexer(path: plan.resolvedDBPath, rebuild: rebuild)
    if !repairOnly {
        for input in plan.runInputs {
            try indexer.ingestRun(input: input, includeResults: includeResults)
        }
    }
    try indexer.ensureCanonicalSpecimenCoverage()
    return indexer
}

func collectRunInputs(outputRoots: [String]) throws -> [RunInput] {
    var inputs: [RunInput] = []
    for outputRoot in outputRoots {
        let rootURL = try existingDirectoryURL(path: outputRoot, label: "Output root")
        let hostsURL = try existingDirectoryURL(
            path: rootURL.appendingPathComponent("hosts").path,
            label: "Output root missing hosts/ directory"
        )
        let hostDirs = try FileManager.default.contentsOfDirectory(
            at: hostsURL,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: .skipsHiddenFiles
        )
        for hostDir in hostDirs where hostDir.hasDirectoryPath {
            let hostId = hostDir.lastPathComponent
            let runsURL = hostDir.appendingPathComponent("runs", isDirectory: true)
            var isDir: ObjCBool = false
            guard FileManager.default.fileExists(atPath: runsURL.path, isDirectory: &isDir), isDir.boolValue else {
                continue
            }
            let runs = try FileManager.default.contentsOfDirectory(
                at: runsURL,
                includingPropertiesForKeys: [.isDirectoryKey],
                options: .skipsHiddenFiles
            )
            for run in runs where run.hasDirectoryPath {
                let runId = run.lastPathComponent
                inputs.append(
                    RunInput(
                        runDir: run,
                        runId: runId,
                        runKey: runKey(hostId: hostId, runId: runId),
                        hostId: hostId,
                        outputRoot: rootURL,
                        runDirRelative: relativePath(from: rootURL, to: run)
                    )
                )
            }
        }
    }

    var seen: Set<String> = []
    return inputs
        .filter { seen.insert($0.runDir.standardizedFileURL.path).inserted }
        .sorted { $0.runDir.path < $1.runDir.path }
}

func makeRunInput(runDir: String, explicitRunID: String? = nil) throws -> RunInput {
    let runURL = try existingDirectoryURL(path: runDir, label: "Run directory")
    let inferred = inferOutputRootAndHostId(from: runURL)
    let runId = try explicitRunID ?? canonicalRunId(for: runURL)
    guard !runId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
        throw ValidationError("Explicit run ID must not be empty.")
    }
    return RunInput(
        runDir: runURL,
        runId: runId,
        runKey: runKey(hostId: inferred.hostId, runId: runId),
        hostId: inferred.hostId,
        outputRoot: inferred.outputRoot,
        runDirRelative: inferred.outputRoot.flatMap { relativePath(from: $0, to: runURL) }
    )
}

func resolvedCompendiumDBPath(
    explicitDBPath: String?,
    outputRoots: [String],
    runInputs: [RunInput]
) throws -> String {
    if let explicitDBPath {
        return explicitDBPath
    }
    if !outputRoots.isEmpty {
        guard outputRoots.count == 1 else {
            throw ValidationError("Provide --db when indexing multiple output roots.")
        }
        return URL(fileURLWithPath: outputRoots[0], isDirectory: true)
            .appendingPathComponent("compendium.sqlite")
            .path
    }
    return runInputs.first?.runDir.appendingPathComponent("compendium.sqlite").path ?? "compendium.sqlite"
}

private func existingDirectoryURL(path: String, label: String) throws -> URL {
    let url = URL(fileURLWithPath: path, isDirectory: true).standardizedFileURL
    var isDir: ObjCBool = false
    guard FileManager.default.fileExists(atPath: url.path, isDirectory: &isDir), isDir.boolValue else {
        throw ValidationError("\(label): \(path)")
    }
    return url
}

private func canonicalRunId(for runDir: URL) throws -> String {
    let manifestURL = runDir.appendingPathComponent("holonomy-manifest.json")
    guard FileManager.default.fileExists(atPath: manifestURL.path) else {
        return runDir.lastPathComponent
    }
    do {
        return try JSONDecoder().decode(HolonomyRunIdentity.self, from: Data(contentsOf: manifestURL)).runId
    } catch {
        throw ValidationError("Invalid holonomy manifest at \(manifestURL.path): \(error)")
    }
}

private func inferOutputRootAndHostId(from runDir: URL) -> (outputRoot: URL?, hostId: String?) {
    let parts = runDir.standardizedFileURL.pathComponents
    guard let hostsIndex = parts.lastIndex(of: "hosts"), hostsIndex + 2 < parts.count, parts[hostsIndex + 2] == "runs" else {
        return (nil, nil)
    }
    let hostId = parts[hostsIndex + 1]
    return (
        URL(fileURLWithPath: NSString.path(withComponents: Array(parts[..<hostsIndex])), isDirectory: true),
        hostId
    )
}

private func runKey(hostId: String?, runId: String) -> String {
    guard let hostId, !hostId.isEmpty else { return runId }
    return "\(hostId)::\(runId)"
}

private func relativePath(from base: URL, to target: URL) -> String? {
    let basePath = base.standardizedFileURL.path.hasSuffix("/") ? base.standardizedFileURL.path : "\(base.standardizedFileURL.path)/"
    let targetPath = target.standardizedFileURL.path
    guard targetPath.hasPrefix(basePath) else { return nil }
    return String(targetPath.dropFirst(basePath.count))
}

struct RunInput {
    let runDir: URL
    let runId: String
    let runKey: String
    let hostId: String?
    let outputRoot: URL?
    let runDirRelative: String?
}

private struct HolonomyRunIdentity: Decodable {
    let runId: String

    enum CodingKeys: String, CodingKey {
        case runId = "run_id"
    }
}
