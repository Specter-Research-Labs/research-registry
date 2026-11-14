import XCTest
@testable import LeniaCore

final class RunReceiptTests: XCTestCase {
    private var root: URL!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("lenia-receipt-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try FileManager.default.removeItem(at: root)
    }

    private func stampedExecutable(named name: String = "LeniaCLI", bytes: String = "binary-v1", patch: String? = nil) throws -> URL {
        let directory = root.appendingPathComponent("bin-\(name)-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let executable = directory.appendingPathComponent(name)
        try Data(bytes.utf8).write(to: executable)
        if let patch {
            try Data(patch.utf8).write(to: LeniaBuildInfo.sourcePatchURL(executableURL: executable))
        }
        let info = LeniaBuildInfo(
            sourceCommit: String(repeating: "a", count: 40),
            dirty: patch != nil,
            binarySha256: ProvenanceDigest.sha256Hex(Data(bytes.utf8)),
            swiftVersion: "Swift version 6.0",
            cEngineSha256: String(repeating: "c", count: 64),
            sourcePatchSha256: patch.map { ProvenanceDigest.sha256Hex(Data($0.utf8)) }
        )
        try JSONEncoder().encode(info).write(to: LeniaBuildInfo.buildInfoURL(executableURL: executable))
        return executable
    }

    private func begin(_ runDir: URL, executable: URL, backend: FlowLeniaComputeBackend = .cpu) throws -> RunReceiptSession {
        let input = root.appendingPathComponent("input.json")
        try Data("{\"seed\":3}".utf8).write(to: input)
        return try RunReceiptSession.begin(
            directory: runDir,
            executableURL: executable,
            argv: ["LeniaCLI", "discover", "local"],
            backend: backend,
            config: ["steps": 10],
            seeds: [3, 4],
            inputs: [input]
        )
    }

    func testReceiptRoundTripsAndCompletionHashesOutputs() throws {
        let executable = try stampedExecutable()
        let runDir = root.appendingPathComponent("run", isDirectory: true)
        let session = try begin(runDir, executable: executable)

        let loaded = try RunReceiptSession.load(directory: runDir)
        XCTAssertEqual(loaded.provenance, session.provenance)
        XCTAssertEqual(loaded.receipt.seeds, [3, 4])
        XCTAssertEqual(loaded.receipt.argv, ["LeniaCLI", "discover", "local"])
        XCTAssertEqual(loaded.receipt.engine, LeniaEngineIdentity(backend: .cpu, buildInfo: loaded.receipt.build))
        XCTAssertEqual(loaded.receipt.inputs.count, 1)
        XCTAssertNil(loaded.receipt.sourcePatch)
        XCTAssertEqual(
            loaded.receiptSha256,
            try ProvenanceDigest.sha256Hex(fileAt: runDir.appendingPathComponent(RunReceipt.fileName))
        )

        try Data("row\n".utf8).write(to: runDir.appendingPathComponent("results.jsonl"))
        try FileManager.default.createDirectory(at: runDir.appendingPathComponent("logs"), withIntermediateDirectories: true)
        try Data("log".utf8).write(to: runDir.appendingPathComponent("logs/run.log"))
        let completion = try session.finish()
        XCTAssertEqual(completion.receiptSha256, session.receiptSha256)
        XCTAssertEqual(Array(completion.outputs.keys), ["results.jsonl"])
        XCTAssertEqual(completion.outputs["results.jsonl"], ProvenanceDigest.sha256Hex(Data("row\n".utf8)))
    }

    func testBeginRefusesBinaryThatDiffersFromBuildInfo() throws {
        let executable = try stampedExecutable()
        try Data("rebuilt-without-stamp".utf8).write(to: executable)
        XCTAssertThrowsError(try begin(root.appendingPathComponent("run"), executable: executable)) { error in
            guard case ProvenanceError.binaryMismatch = error else {
                return XCTFail("expected binaryMismatch, got \(error)")
            }
        }
        XCTAssertFalse(FileManager.default.fileExists(atPath: root.appendingPathComponent("run/receipt.json").path))
    }

    func testBeginRefusesMissingBuildInfo() throws {
        let executable = try stampedExecutable()
        try FileManager.default.removeItem(at: LeniaBuildInfo.buildInfoURL(executableURL: executable))
        XCTAssertThrowsError(try begin(root.appendingPathComponent("run"), executable: executable)) { error in
            guard case ProvenanceError.missingBuildInfo = error else {
                return XCTFail("expected missingBuildInfo, got \(error)")
            }
        }
    }

    func testBeginRefusesExistingReceipt() throws {
        let executable = try stampedExecutable()
        let runDir = root.appendingPathComponent("run", isDirectory: true)
        _ = try begin(runDir, executable: executable)
        XCTAssertThrowsError(try begin(runDir, executable: executable)) { error in
            guard case ProvenanceError.receiptExists = error else {
                return XCTFail("expected receiptExists, got \(error)")
            }
        }
    }

    func testDirtyBuildCopiesSourcePatchIntoRun() throws {
        let executable = try stampedExecutable(patch: "diff --git a/x b/x\n")
        let runDir = root.appendingPathComponent("run", isDirectory: true)
        let session = try begin(runDir, executable: executable)
        XCTAssertEqual(session.receipt.sourcePatch, "LeniaCLI.source.patch")
        XCTAssertEqual(
            try String(contentsOf: runDir.appendingPathComponent("LeniaCLI.source.patch"), encoding: .utf8),
            "diff --git a/x b/x\n"
        )

        try Data("edited".utf8).write(to: LeniaBuildInfo.sourcePatchURL(executableURL: executable))
        XCTAssertThrowsError(try begin(root.appendingPathComponent("run-2"), executable: executable)) { error in
            guard case ProvenanceError.sourcePatchMismatch = error else {
                return XCTFail("expected sourcePatchMismatch, got \(error)")
            }
        }
    }

    func testResumeRefusesOtherBinaryOrEngine() throws {
        let executable = try stampedExecutable()
        let runDir = root.appendingPathComponent("run", isDirectory: true)
        let session = try begin(runDir, executable: executable)
        XCTAssertEqual(try RunReceiptSession.resume(directory: runDir, executableURL: executable, backend: .cpu).provenance, session.provenance)

        XCTAssertThrowsError(try RunReceiptSession.resume(directory: runDir, executableURL: executable, backend: .mlx)) { error in
            guard case ProvenanceError.receiptMismatch = error else {
                return XCTFail("expected receiptMismatch, got \(error)")
            }
        }
        let other = try stampedExecutable(bytes: "binary-v2")
        XCTAssertThrowsError(try RunReceiptSession.resume(directory: runDir, executableURL: other, backend: .cpu)) { error in
            guard case ProvenanceError.receiptMismatch = error else {
                return XCTFail("expected receiptMismatch, got \(error)")
            }
        }
    }

    func testReceiptWithMissingFieldIsRefused() throws {
        let executable = try stampedExecutable()
        let runDir = root.appendingPathComponent("run", isDirectory: true)
        _ = try begin(runDir, executable: executable)
        let receiptURL = runDir.appendingPathComponent(RunReceipt.fileName)
        for key in ["source_patch", "engine_id", "seeds"] {
            var json = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: receiptURL)) as? [String: Any])
            json.removeValue(forKey: key)
            let tampered = root.appendingPathComponent("tampered-\(key)", isDirectory: true)
            try FileManager.default.createDirectory(at: tampered, withIntermediateDirectories: true)
            try JSONSerialization.data(withJSONObject: json).write(to: tampered.appendingPathComponent(RunReceipt.fileName))
            XCTAssertThrowsError(try RunReceiptSession.load(directory: tampered), key)
        }
    }

    func testEngineIDTracksBackendAndCEngine() {
        let info = LeniaBuildInfo(
            sourceCommit: "a",
            dirty: false,
            binarySha256: "b",
            swiftVersion: "s",
            cEngineSha256: "c",
            sourcePatchSha256: nil
        )
        let otherC = LeniaBuildInfo(
            sourceCommit: "z",
            dirty: false,
            binarySha256: "y",
            swiftVersion: "s",
            cEngineSha256: "d",
            sourcePatchSha256: nil
        )
        let mlx = LeniaEngineIdentity(backend: .mlx, buildInfo: info)
        XCTAssertEqual(mlx.engineID.count, LeniaEngineIdentity.shortLength)
        XCTAssertNotEqual(mlx.engineID, LeniaEngineIdentity(backend: .metalFull, buildInfo: info).engineID)
        XCTAssertNotEqual(mlx.engineID, LeniaEngineIdentity(backend: .mlx, buildInfo: otherC).engineID)
        let sameEngineOtherCommit = LeniaBuildInfo(
            sourceCommit: "q",
            dirty: true,
            binarySha256: "r",
            swiftVersion: "s",
            cEngineSha256: "c",
            sourcePatchSha256: "p"
        )
        XCTAssertEqual(mlx.engineID, LeniaEngineIdentity(backend: .mlx, buildInfo: sameEngineOtherCommit).engineID)
    }

    func testWorkerEngineMismatchesNameEveryDifferingBackend() {
        let status = WorkerStatus(
            capabilities: WorkerBackendCapabilities(
                canonicalSearchBackends: [.mlx, .metalFull],
                canonicalFlowLeniaBackends: [.mlx],
                canonicalSearchPreferredBackend: .metalFull,
                canonicalFlowLeniaPreferredBackend: .mlx
            ),
            workerId: "w",
            hostname: "node",
            currentJob: nil,
            jobsCompleted: 0,
            totalSeedsProcessed: 0,
            isAvailable: true,
            engineIDs: ["mlx": "e-mlx", "metal-full": "e-metal"]
        )
        XCTAssertEqual(status.engineMismatches(expected: ["mlx": "e-mlx", "metal-full": "e-metal", "cpu": "e-cpu"]), [])
        XCTAssertEqual(
            status.engineMismatches(expected: ["mlx": "e-mlx", "metal-full": "other"]),
            ["metal-full: worker e-metal, controller other"]
        )
        let silent = WorkerStatus(
            capabilities: status.capabilities,
            workerId: "w",
            hostname: "node",
            currentJob: nil,
            jobsCompleted: 0,
            totalSeedsProcessed: 0,
            isAvailable: true,
            engineIDs: ["mlx": "e-mlx"]
        )
        XCTAssertEqual(
            silent.engineMismatches(expected: ["mlx": "e-mlx", "metal-full": "e-metal"]),
            ["metal-full: worker missing, controller e-metal"]
        )
    }
}
