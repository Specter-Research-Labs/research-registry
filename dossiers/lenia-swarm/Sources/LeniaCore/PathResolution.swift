import Foundation

private let runtimeRootEnv = "SPECTER_RUNTIME_ROOT"
private let localLogRootEnv = "SPCTR_LOCAL_LOG_ROOT"
private let localArtifactRootEnv = "SPCTR_LOCAL_ARTIFACT_ROOT"
private let logRootEnv = "SPECTER_LOG_ROOT"
private let artifactRootEnv = "SPECTER_ARTIFACT_ROOT"
private let repoRootURL = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent()
    .deletingLastPathComponent()
    .deletingLastPathComponent()
    .deletingLastPathComponent()
    .deletingLastPathComponent()

public enum RuntimePathResolutionError: LocalizedError {
    case emptyEnvVar(String)

    public var errorDescription: String? {
        switch self {
        case .emptyEnvVar(let name):
            return "\(name) is set but empty."
        }
    }
}

private func normalizedPathValue(_ value: String?) -> String? {
    guard let value else { return nil }
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
}

func defaultPersistentDossierParent(repoRoot: URL) -> URL {
    let workspaceParent = repoRoot.deletingLastPathComponent()
    if workspaceParent.lastPathComponent == "research-registry-workspaces" {
        let sharedDossiers = workspaceParent
            .deletingLastPathComponent()
            .appendingPathComponent("research-registry", isDirectory: true)
            .appendingPathComponent("dossiers", isDirectory: true)
        if FileManager.default.fileExists(atPath: sharedDossiers.path) {
            return sharedDossiers
        }
    }
    return repoRoot.appendingPathComponent("dossiers", isDirectory: true)
}

private func defaultPersistentRoot(dossier: String) -> URL {
    defaultPersistentDossierParent(repoRoot: repoRootURL)
        .appendingPathComponent(dossier, isDirectory: true)
}

private func configuredPersistentRoot(envNames: [String], dossier: String) throws -> URL? {
    for envName in envNames {
        guard let raw = ProcessInfo.processInfo.environment[envName] else {
            continue
        }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            throw RuntimePathResolutionError.emptyEnvVar(envName)
        }
        return URL(fileURLWithPath: (trimmed as NSString).expandingTildeInPath, isDirectory: true)
            .appendingPathComponent(dossier, isDirectory: true)
    }
    return nil
}

private func dossierRoot(dossier: String) -> URL {
    repoRootURL
        .appendingPathComponent("dossiers", isDirectory: true)
        .appendingPathComponent(dossier, isDirectory: true)
}

private func dossierOutputRoot(dossier: String) -> URL {
    defaultPersistentRoot(dossier: dossier)
        .appendingPathComponent("outputs", isDirectory: true)
}

private func dossierArtifactRoot(dossier: String) -> URL {
    defaultPersistentRoot(dossier: dossier)
        .appendingPathComponent("artifacts", isDirectory: true)
}

private func canonicalRelativeSuffix(_ path: String, prefix: String) -> String? {
    if path == prefix {
        return ""
    }
    let prefixSlash = "\(prefix)/"
    guard path.hasPrefix(prefixSlash) else {
        return nil
    }
    return String(path.dropFirst(prefixSlash.count))
}

private func resolveCanonicalRelativePath(_ path: String, dossier: String) throws -> String? {
    if let suffix = canonicalRelativeSuffix(path, prefix: "outputs") {
        let base = try configuredPersistentRoot(envNames: [localArtifactRootEnv, artifactRootEnv], dossier: dossier)?
            .appendingPathComponent("outputs", isDirectory: true)
            ?? dossierOutputRoot(dossier: dossier)
        guard !suffix.isEmpty else { return base.path }
        return base.appendingPathComponent(suffix, isDirectory: false).path
    }
    if let suffix = canonicalRelativeSuffix(path, prefix: "artifacts") {
        let base = try configuredPersistentRoot(envNames: [localArtifactRootEnv, artifactRootEnv], dossier: dossier)?
            .appendingPathComponent("artifacts", isDirectory: true)
            ?? dossierArtifactRoot(dossier: dossier)
        guard !suffix.isEmpty else { return base.path }
        return base.appendingPathComponent(suffix, isDirectory: false).path
    }
    if let suffix = canonicalRelativeSuffix(path, prefix: "logs") {
        let base = try configuredPersistentRoot(envNames: [localLogRootEnv, logRootEnv], dossier: dossier)?
            .appendingPathComponent("logs", isDirectory: true)
            ?? dossierOutputRoot(dossier: dossier).appendingPathComponent("logs", isDirectory: true)
        guard !suffix.isEmpty else { return base.path }
        return base.appendingPathComponent(suffix, isDirectory: false).path
    }
    return nil
}

private func configuredRuntimeRoot(dossier: String) throws -> String? {
    guard let raw = ProcessInfo.processInfo.environment[runtimeRootEnv] else {
        return nil
    }
    let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    if trimmed.isEmpty {
        throw RuntimePathResolutionError.emptyEnvVar(runtimeRootEnv)
    }
    return URL(fileURLWithPath: (trimmed as NSString).expandingTildeInPath, isDirectory: true)
        .appendingPathComponent(dossier, isDirectory: true)
        .path
}

private func remapTmpPath(_ path: String, dossier: String) throws -> String {
    let expanded = (path as NSString).expandingTildeInPath
    let suffix: String
    if expanded == "/tmp" || expanded == "/private/tmp" {
        suffix = ""
    } else if expanded.hasPrefix("/tmp/") {
        suffix = String(expanded.dropFirst("/tmp/".count))
    } else if expanded.hasPrefix("/private/tmp/") {
        suffix = String(expanded.dropFirst("/private/tmp/".count))
    } else {
        return expanded
    }
    guard let runtimeRoot = try configuredRuntimeRoot(dossier: dossier) else {
        return expanded
    }
    guard !suffix.isEmpty else {
        return runtimeRoot
    }
    return URL(fileURLWithPath: runtimeRoot, isDirectory: true)
        .appendingPathComponent(suffix, isDirectory: false)
        .path
}

public func resolveRuntimeAwarePath(_ path: String, dossier: String) throws -> String {
    let raw = normalizedPathValue(path) ?? path
    if raw.hasPrefix("/") || raw.hasPrefix("~") {
        return try remapTmpPath(raw, dossier: dossier)
    }
    return raw
}

public func resolveRuntimeAwareArtifactPath(_ path: String, dossier: String) throws -> String {
    let raw = normalizedPathValue(path) ?? path
    if raw.hasPrefix("/") || raw.hasPrefix("~") {
        return try remapTmpPath(raw, dossier: dossier)
    }
    if let canonical = try resolveCanonicalRelativePath(raw, dossier: dossier) {
        return canonical
    }
    return raw
}

public func resolveRuntimeAwareLogBase(
    explicit: String?,
    dossier: String,
    output: String? = nil
) throws -> String {
    if let explicit = normalizedPathValue(explicit) {
        if let canonical = try resolveCanonicalRelativePath(explicit, dossier: dossier) {
            return canonical
        }
        return try resolveRuntimeAwarePath(explicit, dossier: dossier)
    }
    if let output = output {
        let resolvedOutput = try resolveRuntimeAwareArtifactPath(output, dossier: dossier)
        return URL(fileURLWithPath: resolvedOutput, isDirectory: true)
            .appendingPathComponent("logs", isDirectory: true)
            .path
    }
    if let remoteLogRoot = try configuredPersistentRoot(envNames: [localLogRootEnv, logRootEnv], dossier: dossier) {
        return remoteLogRoot.appendingPathComponent("logs", isDirectory: true).path
    }
    return dossierOutputRoot(dossier: dossier)
        .appendingPathComponent("logs", isDirectory: true)
        .path
}
