import XCTest
@testable import LeniaCLIKit

final class TTCommandTests: XCTestCase {
    func testLocalNoContainerInvocationUsesDossierWorkingDirectory() throws {
        let root = URL(fileURLWithPath: "/tmp/lenia-swarm", isDirectory: true)

        let invocation = try TTBackendRunInvocation(
            config: "configs/base/paper_base_1c_128.json",
            output: "tmp/tt-runs/smoke",
            steps: 2,
            batchSize: 1,
            seed: nil,
            seedList: nil,
            initSeedOffset: 0,
            saveEvery: 0,
            frameEvery: 1,
            frameProjection: "matter",
            frameBatchIndex: 0,
            executionMode: "single",
            deviceId: 0,
            deviceList: nil,
            ttVisibleDevices: nil,
            meshShape: nil,
            reference: nil,
            persistentWorkers: false,
            python: "python3",
            host: nil,
            remoteRoot: nil,
            useContainer: false,
            ttCardNum: 0,
            ttCardList: nil,
            reset: false,
            skipSmoke: false,
            dossierRoot: root
        )

        XCTAssertEqual(invocation.executable, "/usr/bin/env")
        XCTAssertEqual(invocation.currentDirectory, root)
        XCTAssertEqual(Array(invocation.arguments.prefix(3)), ["python3", "tt_backend/devtools/run.py", "--config"])
        XCTAssertTrue(invocation.arguments.contains("configs/base/paper_base_1c_128.json"))
        XCTAssertFalse(invocation.arguments.contains("--seed"))
    }

    func testRemoteContainerInvocationMapsRepoRelativePathsIntoContainer() throws {
        let invocation = try TTBackendRunInvocation(
            config: "configs/base/paper_base_1c_128.json",
            output: "tmp/tt-runs/smoke",
            steps: 2,
            batchSize: 1,
            seed: 0,
            seedList: "0",
            initSeedOffset: 11,
            saveEvery: 0,
            frameEvery: 1,
            frameProjection: "matter",
            frameBatchIndex: 0,
            executionMode: "mesh",
            deviceId: 0,
            deviceList: "0",
            ttVisibleDevices: nil,
            meshShape: "1,2",
            reference: nil,
            persistentWorkers: false,
            python: "python3",
            host: "quietbox",
            remoteRoot: "/remote/lenia-swarm",
            useContainer: true,
            ttCardNum: 0,
            ttCardList: "0",
            reset: false,
            skipSmoke: false,
            dossierRoot: URL(fileURLWithPath: "/local/lenia-swarm", isDirectory: true)
        )

        XCTAssertEqual(invocation.executable, "/usr/bin/env")
        XCTAssertEqual(Array(invocation.arguments.prefix(2)), ["ssh", "quietbox"])
        let remoteCommand = try XCTUnwrap(invocation.arguments.last)
        XCTAssertTrue(remoteCommand.contains("python3 tt_backend/devtools/quietbox_container.py"))
        XCTAssertTrue(remoteCommand.contains("--device-mode mesh"))
        XCTAssertTrue(remoteCommand.contains("--config /repo/configs/base/paper_base_1c_128.json"))
        XCTAssertTrue(remoteCommand.contains("--output /repo/tmp/tt-runs/smoke"))
        XCTAssertTrue(remoteCommand.contains("--seed-list 0"))
        XCTAssertTrue(remoteCommand.contains("--seed 0"))
        XCTAssertTrue(remoteCommand.contains("--init-seed-offset 11"))
        XCTAssertTrue(remoteCommand.contains("--mesh-shape 1,2"))
    }

    func testRemoteInvocationRequiresRemoteRoot() throws {
        XCTAssertThrowsError(
            try TTBackendRunInvocation(
                config: "configs/base/paper_base_1c_128.json",
                output: "tmp/tt-runs/smoke",
                steps: 2,
                batchSize: 1,
                seed: nil,
                seedList: nil,
                initSeedOffset: 0,
                saveEvery: 0,
                frameEvery: 0,
                frameProjection: "matter",
                frameBatchIndex: 0,
                executionMode: "single",
                deviceId: 0,
                deviceList: nil,
                ttVisibleDevices: nil,
                meshShape: nil,
                reference: nil,
                persistentWorkers: false,
                python: "python3",
                host: "quietbox",
                remoteRoot: nil,
                useContainer: true,
                ttCardNum: 0,
                ttCardList: nil,
                reset: false,
                skipSmoke: false,
                dossierRoot: URL(fileURLWithPath: "/local/lenia-swarm", isDirectory: true)
            )
        ) { error in
            XCTAssertTrue(String(describing: error).contains("--remote-root"))
        }
    }
}
