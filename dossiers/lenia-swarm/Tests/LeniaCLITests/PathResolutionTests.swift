import Foundation
import XCTest
@testable import LeniaCLIKit

final class PathResolutionTests: XCTestCase {
    private var dossierRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }

    override func tearDown() {
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

    func testResolvePathRemapsTmpPathWhenRuntimeRootSet() throws {
        setenv("SPECTER_RUNTIME_ROOT", "/Volumes/Addenda/dev/specter-labs/tmp", 1)
        XCTAssertEqual(
            try resolvePath("/tmp/lenia-smoke", dossier: dossierName),
            "/Volumes/Addenda/dev/specter-labs/tmp/lenia-swarm/lenia-smoke"
        )
    }

    func testResolvePathRemapsPrivateTmpPathWhenRuntimeRootSet() throws {
        setenv("SPECTER_RUNTIME_ROOT", "/Volumes/Addenda/dev/specter-labs/tmp", 1)
        XCTAssertEqual(
            try resolvePath("/private/tmp/lenia-smoke", dossier: dossierName),
            "/Volumes/Addenda/dev/specter-labs/tmp/lenia-swarm/lenia-smoke"
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
        let expected = dossierRoot
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
        let expected = dossierRoot
            .appendingPathComponent("outputs", isDirectory: true)
            .appendingPathComponent("sweep-a", isDirectory: true)
            .path
        XCTAssertEqual(
            try resolveArtifactPath("outputs/sweep-a", dossier: dossierName),
            expected
        )
    }

    func testResolveLogBaseDefaultsToDossierOutputLogs() throws {
        let expected = dossierRoot
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
