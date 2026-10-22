import XCTest
@testable import LeniaCLIKit

final class TTCommandTests: XCTestCase {
    func testLocalInvocationRunsReplayInContainerFromDossierRoot() throws {
        let root = URL(fileURLWithPath: "/tmp/lenia-swarm", isDirectory: true)

        let invocation = try TTReplayInvocation(
            input: "tmp/requal/input/index.jsonl",
            output: "/tmp/lenia-swarm/tmp/tt-replays/smoke",
            steps: 650,
            traceInterval: 50,
            cards: "0,1",
            seeds: "0-8",
            batch: 4096,
            python: "python3",
            host: nil,
            remoteRoot: nil,
            dossierRoot: root
        )

        XCTAssertEqual(invocation.executable, "/usr/bin/env")
        XCTAssertEqual(invocation.currentDirectory, root)
        XCTAssertEqual(
            invocation.arguments,
            [
                "python3", "tt_backend/devtools/container.py", "--",
                "python3", "-m", "tt_lenia.sfpu.replay",
                "--input", "/repo/tmp/requal/input/index.jsonl",
                "--output", "/repo/tmp/tt-replays/smoke",
                "--steps", "650",
                "--trace-interval", "50",
                "--cards", "0,1",
                "--seeds", "0-8",
                "--batch", "4096",
            ]
        )
    }

    func testRemoteInvocationMapsRemoteRootPathsIntoContainer() throws {
        let invocation = try TTReplayInvocation(
            input: "/remote/lenia-swarm/tmp/requal/input/index.jsonl",
            output: "tmp/tt-replays/smoke",
            steps: 40000,
            traceInterval: 1000,
            cards: "0,1,2,3",
            seeds: "0",
            batch: 256,
            python: "python3",
            host: "tt-host",
            remoteRoot: "/remote/lenia-swarm",
            dossierRoot: URL(fileURLWithPath: "/local/lenia-swarm", isDirectory: true)
        )

        XCTAssertEqual(Array(invocation.arguments.prefix(2)), ["ssh", "tt-host"])
        let remoteCommand = try XCTUnwrap(invocation.arguments.last)
        XCTAssertTrue(remoteCommand.hasPrefix("cd /remote/lenia-swarm && python3 tt_backend/devtools/container.py -- "))
        XCTAssertTrue(remoteCommand.contains("--input /repo/tmp/requal/input/index.jsonl"))
        XCTAssertTrue(remoteCommand.contains("--output /repo/tmp/tt-replays/smoke"))
        XCTAssertTrue(remoteCommand.contains("--cards 0,1,2,3 --seeds 0 --batch 256"))
    }

    func testPathsOutsideTheDossierAreRefused() throws {
        XCTAssertThrowsError(
            try TTReplayInvocation(
                input: "/elsewhere/index.jsonl",
                output: "tmp/out",
                steps: 1,
                traceInterval: 1,
                cards: "0",
                seeds: "0",
                batch: 64,
                python: "python3",
                host: nil,
                remoteRoot: nil,
                dossierRoot: URL(fileURLWithPath: "/local/lenia-swarm", isDirectory: true)
            )
        ) { error in
            XCTAssertTrue(String(describing: error).contains("dossier root"))
        }
    }

    func testRemoteInvocationRequiresRemoteRoot() throws {
        XCTAssertThrowsError(
            try TTReplayInvocation(
                input: "tmp/index.jsonl",
                output: "tmp/out",
                steps: 1,
                traceInterval: 1,
                cards: "0",
                seeds: "0",
                batch: 64,
                python: "python3",
                host: "tt-host",
                remoteRoot: nil,
                dossierRoot: URL(fileURLWithPath: "/local/lenia-swarm", isDirectory: true)
            )
        ) { error in
            XCTAssertTrue(String(describing: error).contains("--remote-root"))
        }
    }
}
