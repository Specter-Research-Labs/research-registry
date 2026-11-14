import ArgumentParser
import Foundation
import LeniaCore

struct CompendiumIngestPlan {
    let runInputs: [RunInput]
    let resolvedDBPath: String
}

func resolveCompendiumIngestPlan(
    outputRoots: [String],
    runDirs: [String],
    dbPath: String?,
    legacyEngineID: String?
) throws -> CompendiumIngestPlan {
    let hasOutputRoot = !outputRoots.isEmpty
    let hasRunDir = !runDirs.isEmpty

    if hasOutputRoot == hasRunDir {
        throw ValidationError("Provide exactly one of --output-root or --run-dir.")
    }

    let runInputs = try hasOutputRoot
        ? collectRunInputs(outputRoots: outputRoots, legacyEngineID: legacyEngineID)
        : runDirs.map { try makeRunInput(runDir: $0, legacyEngineID: legacyEngineID) }
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
    includeResults: Bool
) throws -> SQLiteIndexer {
    let indexer = try SQLiteIndexer(path: plan.resolvedDBPath, rebuild: rebuild)
    for input in plan.runInputs {
        try indexer.ingestRun(input: input, includeResults: includeResults)
    }
    try indexer.ensureCanonicalSpecimenCoverage()
    return indexer
}

func collectRunInputs(outputRoots: [String], legacyEngineID: String?) throws -> [RunInput] {
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
                        runDirRelative: relativePath(from: rootURL, to: run),
                        provenance: try resolveRunProvenance(runDir: run, legacyEngineID: legacyEngineID)
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

func makeRunInput(runDir: String, legacyEngineID: String?) throws -> RunInput {
    let runURL = try existingDirectoryURL(path: runDir, label: "Run directory")
    let inferred = inferOutputRootAndHostId(from: runURL)
    let runId = try canonicalRunId(for: runURL)
    return RunInput(
        runDir: runURL,
        runId: runId,
        runKey: runKey(hostId: inferred.hostId, runId: runId),
        hostId: inferred.hostId,
        outputRoot: inferred.outputRoot,
        runDirRelative: inferred.outputRoot.flatMap { relativePath(from: $0, to: runURL) },
        provenance: try resolveRunProvenance(runDir: runURL, legacyEngineID: legacyEngineID)
    )
}

/// A run names its engine through its receipt.json; a legacy directory written before receipts
/// gets only the engine id the caller declares for it, with no source commit or receipt.
func resolveRunProvenance(runDir: URL, legacyEngineID: String?) throws -> CompendiumRunProvenance {
    guard FileManager.default.fileExists(atPath: runDir.appendingPathComponent(RunReceipt.fileName).path) else {
        guard let legacyEngineID else {
            throw ValidationError(
                "Run directory \(runDir.path) has no \(RunReceipt.fileName). Pass --engine-id <id> to index a legacy run written before receipts."
            )
        }
        return CompendiumRunProvenance(engineID: legacyEngineID, sourceCommit: nil, receiptSha256: nil)
    }
    let provenance = try RunReceiptSession.load(directory: runDir).provenance
    if let legacyEngineID, legacyEngineID != provenance.engineID {
        throw ValidationError(
            "--engine-id \(legacyEngineID) contradicts \(runDir.path)/\(RunReceipt.fileName), which names engine \(provenance.engineID)."
        )
    }
    return CompendiumRunProvenance(
        engineID: provenance.engineID,
        sourceCommit: provenance.sourceCommit,
        receiptSha256: provenance.receiptSha256
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
    let provenance: CompendiumRunProvenance
}

struct CompendiumRunProvenance {
    let engineID: String
    let sourceCommit: String?
    let receiptSha256: String?
}

private struct HolonomyRunIdentity: Decodable {
    let runId: String

    enum CodingKeys: String, CodingKey {
        case runId = "run_id"
    }
}
