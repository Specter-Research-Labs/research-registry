import Foundation
import XCTest
@testable import LeniaCore
@testable import LeniaCLIKit

final class PathResolutionTests: XCTestCase {
    private var dossierRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }

    private var persistentDossierRoot: URL {
        let repoRoot = dossierRoot
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        return defaultPersistentDossierParent(repoRoot: repoRoot)
            .appendingPathComponent(dossierName, isDirectory: true)
    }

    override func tearDown() {
        unsetenv("SPCTR_LOCAL_LOG_ROOT")
        unsetenv("SPCTR_LOCAL_ARTIFACT_ROOT")
        unsetenv("SPECTER_LOG_ROOT")
        unsetenv("SPECTER_ARTIFACT_ROOT")
        unsetenv("SPECTER_RUNTIME_ROOT")
        super.tearDown()
    }

    func testResolvePathKeepsRelativePathLocalEvenWhenSpecterLogRootSet() throws {
        setenv("SPECTER_LOG_ROOT", "/tmp/remote-logs", 1)
        XCTAssertEqual(try resolvePath("runs/session-a", dossier: dossierName), "runs/session-a")
    }

    func testResolveArtifactPathUsesRemoteRootForCanonicalOutputs() throws {
        setenv("SPECTER_ARTIFACT_ROOT", "/tmp/remote-artifacts", 1)
        XCTAssertEqual(
            try resolveArtifactPath("outputs/sweep-a", dossier: dossierName),
            "/tmp/remote-artifacts/lenia-swarm/outputs/sweep-a"
        )
    }

    func testResolveArtifactPathUsesSharedRootForCanonicalArtifacts() throws {
        setenv("SPCTR_LOCAL_ARTIFACT_ROOT", "/tmp/shared-artifacts", 1)
        XCTAssertEqual(
            try resolveArtifactPath("artifacts/compendium.sqlite", dossier: dossierName),
            "/tmp/shared-artifacts/lenia-swarm/artifacts/compendium.sqlite"
        )
    }

    func testLocalArtifactRootWinsOverLegacyArtifactRoot() throws {
        setenv("SPCTR_LOCAL_ARTIFACT_ROOT", "/tmp/local-artifacts", 1)
        setenv("SPECTER_ARTIFACT_ROOT", "/tmp/server-artifacts", 1)
        XCTAssertEqual(
            try resolveArtifactPath("outputs/sweep-a", dossier: dossierName),
            "/tmp/local-artifacts/lenia-swarm/outputs/sweep-a"
        )
    }

    func testResolvePathRemapsTmpPathWhenRuntimeRootSet() throws {
        setenv("SPECTER_RUNTIME_ROOT", "/tmp/specter-runtime", 1)
        XCTAssertEqual(
            try resolvePath("/tmp/lenia-smoke", dossier: dossierName),
            "/tmp/specter-runtime/lenia-swarm/lenia-smoke"
        )
    }

    func testResolvePathRemapsPrivateTmpPathWhenRuntimeRootSet() throws {
        setenv("SPECTER_RUNTIME_ROOT", "/tmp/specter-runtime", 1)
        XCTAssertEqual(
            try resolvePath("/private/tmp/lenia-smoke", dossier: dossierName),
            "/tmp/specter-runtime/lenia-swarm/lenia-smoke"
        )
    }

    func testResolvePathErrorsWhenRuntimeRootIsEmpty() {
        setenv("SPECTER_RUNTIME_ROOT", "   ", 1)
        XCTAssertThrowsError(try resolvePath("/tmp/lenia-smoke", dossier: dossierName))
    }

    func testResolveLogBaseUsesOutputSubdirectory() throws {
        let expected = URL(fileURLWithPath: "results", isDirectory: true)
            .appendingPathComponent("logs", isDirectory: true)
            .path
        XCTAssertEqual(
            try resolveLogBase(explicit: nil, dossier: dossierName, output: "results"),
            expected
        )
    }

    func testResolveLogBaseUsesCanonicalOutputSubdirectory() throws {
        let expected = persistentDossierRoot
            .appendingPathComponent("outputs", isDirectory: true)
            .appendingPathComponent("ecology", isDirectory: true)
            .appendingPathComponent("logs", isDirectory: true)
            .path
        XCTAssertEqual(
            try resolveLogBase(explicit: nil, dossier: dossierName, output: "outputs/ecology"),
            expected
        )
    }

    func testResolveArtifactPathDefaultsOutputsToDossierRoot() throws {
        let expected = persistentDossierRoot
            .appendingPathComponent("outputs", isDirectory: true)
            .appendingPathComponent("sweep-a", isDirectory: true)
            .path
        XCTAssertEqual(
            try resolveArtifactPath("outputs/sweep-a", dossier: dossierName),
            expected
        )
    }

    func testResolveArtifactPathDefaultsArtifactsToDossierRoot() throws {
        let expected = persistentDossierRoot
            .appendingPathComponent("artifacts", isDirectory: true)
            .appendingPathComponent("compendium.sqlite")
            .path
        XCTAssertEqual(
            try resolveArtifactPath("artifacts/compendium.sqlite", dossier: dossierName),
            expected
        )
    }

    func testWorkspaceRepoUsesSiblingMainDossiersAsDefaultPersistentRoot() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let mainDossiers = root
            .appendingPathComponent("research-registry", isDirectory: true)
            .appendingPathComponent("dossiers", isDirectory: true)
        let workspaceRepo = root
            .appendingPathComponent("research-registry-workspaces", isDirectory: true)
            .appendingPathComponent("lenia-atlas-live", isDirectory: true)
        try FileManager.default.createDirectory(at: mainDossiers, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: workspaceRepo, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        XCTAssertEqual(defaultPersistentDossierParent(repoRoot: workspaceRepo), mainDossiers)
    }

    func testResolveLogBaseDefaultsToDossierOutputLogs() throws {
        let expected = persistentDossierRoot
            .appendingPathComponent("outputs", isDirectory: true)
            .appendingPathComponent("logs", isDirectory: true)
            .path
        XCTAssertEqual(try resolveLogBase(explicit: nil, dossier: dossierName), expected)
    }

    func testResolveLogBaseUsesRemoteRootWhenConfigured() throws {
        setenv("SPECTER_LOG_ROOT", "/tmp/remote-logs", 1)
        let expected = "/tmp/remote-logs/lenia-swarm/logs"
        XCTAssertEqual(try resolveLogBase(explicit: nil, dossier: dossierName), expected)
    }

    func testResolveLogBaseExplicitPathStaysLocal() throws {
        setenv("SPECTER_LOG_ROOT", "/tmp/remote-logs", 1)
        XCTAssertEqual(
            try resolveLogBase(explicit: "custom-logs", dossier: dossierName),
            "custom-logs"
        )
    }

    func testResolveLogBaseCanonicalLogsPathUsesRemoteRoot() throws {
        setenv("SPECTER_LOG_ROOT", "/tmp/remote-logs", 1)
        XCTAssertEqual(
            try resolveLogBase(explicit: "logs/search-a", dossier: dossierName),
            "/tmp/remote-logs/lenia-swarm/logs/search-a"
        )
    }
}
