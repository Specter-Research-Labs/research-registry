import CryptoKit
import XCTest
import LeniaCore
@testable import LeniaCLIKit

final class ReplayMaterializerTests: XCTestCase {
    func testDevelopmentTraceStrideClampsToReplayLength() {
        XCTAssertEqual(developmentTraceStride(interval: 25, steps: 3), 3)
        XCTAssertEqual(developmentTraceStride(interval: 2, steps: 5), 2)
        XCTAssertEqual(developmentTraceStride(interval: 0, steps: 5), 1)
        XCTAssertEqual(developmentTraceStride(interval: 25, steps: 0), 1)
    }

    func testCanonicalReplayBaseConfigMapsUnambiguousLegacyPaperAlias() throws {
        let source = try replayTestBaseConfig(profile: .paper, implementation: ImplementationConfig(mode: "paper"))

        let canonical = try canonicalReplayBaseConfig(source)
        let expected = try replayTestBaseConfig(
            profile: .paper,
            implementation: ImplementationConfig(mode: "flowlenia_2022_paper_equations")
        )

        XCTAssertEqual(canonical.profile, .paper)
        XCTAssertEqual(canonical.implementation.mode, "flowlenia_2022_paper_equations")
        XCTAssertEqual(try researchEncodedJSON(canonical), try researchEncodedJSON(expected))
    }

    func testCanonicalReplayBaseConfigRejectsLegacyPaperAliasOutsidePaperProfile() throws {
        let source = try replayTestBaseConfig(profile: .experimental, implementation: ImplementationConfig(mode: "paper"))

        XCTAssertThrowsError(try canonicalReplayBaseConfig(source))
    }

    func testCanonicalReplayBaseConfigRejectsLegacyPaperAliasWithOverrides() throws {
        let source = try replayTestBaseConfig(
            profile: .paper,
            implementation: ImplementationConfig(mode: "paper", flow_clip: "none")
        )

        XCTAssertThrowsError(try canonicalReplayBaseConfig(source))
    }

    func testSourceBoundReplayAcceptsExactContentAndLegacyRecordRemainsCompatible() throws {
        let fixture = try replaySourceBindingFixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }

        XCTAssertNil(fixture.legacyRecord.sourceContentSha256)
        let legacyData = try JSONEncoder().encode(fixture.legacyRecord)
        let legacyJSON = try XCTUnwrap(JSONSerialization.jsonObject(with: legacyData) as? [String: Any])
        XCTAssertNil(legacyJSON["sourceContentSha256"])
        XCTAssertNil(try JSONDecoder().decode(CreatureExportRecord.self, from: legacyData).sourceContentSha256)

        let resolved = try replayResolvedInput(from: fixture.boundRecord)
        XCTAssertEqual(resolved.sourceContentSha256, fixture.boundRecord.sourceContentSha256)
        guard case .flow = resolved.executionPlan else {
            return XCTFail("Expected strict replay bundle to resolve as Flow Lenia.")
        }
    }

    func testSourceBoundReplayRejectsOneByteDriftInEveryBoundFile() throws {
        let fixture = try replaySourceBindingFixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }

        for (label, url) in [
            ("baseConfig", fixture.baseURL),
            ("searchConfig", fixture.searchURL),
            ("meta", fixture.metaURL),
        ] {
            let original = try Data(contentsOf: url)
            var drifted = original
            drifted[drifted.startIndex] ^= 0x01
            try drifted.write(to: url)

            XCTAssertThrowsError(try replayResolvedInput(from: fixture.boundRecord)) { error in
                let description = String(describing: error)
                XCTAssertTrue(description.contains("SHA-256 mismatch"), description)
                XCTAssertTrue(description.contains(label), description)
            }
            try original.write(to: url)
        }
    }

    func testSourceBoundReplayRejectsMalformedAndIncompleteDigestContracts() throws {
        let fixture = try replaySourceBindingFixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }

        let malformed = replayRecord(
            fixture.legacyRecord,
            sourceContentSha256: CreatureExportSourceContentSHA256(
                baseConfig: "not-a-sha256",
                searchConfig: try sourceSHA256(fixture.searchURL),
                meta: try sourceSHA256(fixture.metaURL)
            )
        )
        XCTAssertThrowsError(try replayResolvedInput(from: malformed)) { error in
            XCTAssertTrue(String(describing: error).contains("Malformed source-content SHA-256"))
        }

        let encoded = try JSONEncoder().encode(fixture.boundRecord)
        var root = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
        var hashes = try XCTUnwrap(root["sourceContentSha256"] as? [String: Any])
        hashes.removeValue(forKey: "meta")
        root["sourceContentSha256"] = hashes
        let incomplete = try JSONSerialization.data(withJSONObject: root, options: [.sortedKeys])
        XCTAssertThrowsError(try JSONDecoder().decode(CreatureExportRecord.self, from: incomplete))
    }

    func testReplayManifestPersistsSourceContentDigests() throws {
        let hashes = CreatureExportSourceContentSHA256(
            baseConfig: String(repeating: "a", count: 64),
            searchConfig: String(repeating: "b", count: 64),
            meta: String(repeating: "c", count: 64)
        )
        let manifest = ReplaySpecimenManifest(
            inputKind: ReplayInputKind.exportIndex.rawValue,
            inputPath: "/source/index.jsonl",
            sourceRunId: "source-run",
            sourceCampaignId: nil,
            sourceCreatureId: UUID().uuidString,
            sourceExportDir: "/source/export",
            sourceReason: "test",
            sourceContentSha256: hashes,
            sourceImplementationMode: "flowlenia_2022_paper_equations",
            replayImplementationMode: "flowlenia_2022_paper_equations",
            replayRunId: "replay-run",
            campaignId: "campaign-0001",
            configHash: "config-hash",
            configPath: "/output/config.json",
            searchPath: "/output/search.json",
            resultsPath: "/output/results.jsonl",
            libraryPath: "/output/library/index.jsonl",
            activityPath: nil,
            exportIndexPath: nil,
            replayedAt: Date(timeIntervalSinceReferenceDate: 0),
            developmentTracePath: nil,
            capturedSteps: nil,
            sampleCount: nil,
            recordEvery: nil
        )

        let decoded = try JSONDecoder().decode(
            ReplaySpecimenManifest.self,
            from: JSONEncoder().encode(manifest)
        )
        XCTAssertEqual(decoded.sourceContentSha256, hashes)
    }

    func testInputSHA256BindsExactShardBytesBeforeDecoding() throws {
        let fixture = try replaySourceBindingFixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }

        let inputURL = fixture.root.appendingPathComponent("shard.jsonl")
        var inputData = try JSONEncoder().encode(fixture.boundRecord)
        inputData.append(0x0A)
        try inputData.write(to: inputURL)
        let inputSha256 = sourceSHA256(inputData)

        let command = try XCTUnwrap(ReplayCommand.parseAsRoot([
            "--input", inputURL.path,
            "--input-sha256", inputSha256,
        ]) as? ReplayCommand)
        XCTAssertEqual(command.inputSha256, inputSha256)
        XCTAssertEqual(
            try loadReplayResolvedInputs(
                from: inputURL,
                expectedInputSha256: inputSha256
            ).count,
            1
        )

        inputData[inputData.startIndex] ^= 0x01
        try inputData.write(to: inputURL)
        XCTAssertThrowsError(
            try loadReplayResolvedInputs(
                from: inputURL,
                expectedInputSha256: inputSha256
            )
        ) { error in
            let description = String(describing: error)
            XCTAssertTrue(description.contains("SHA-256 mismatch"), description)
            XCTAssertTrue(description.contains("input"), description)
        }
    }

    func testInputSHA256RequiresSourceContentHashesOnEveryExportRecord() throws {
        let fixture = try replaySourceBindingFixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }

        let inputURL = fixture.root.appendingPathComponent("shard.jsonl")
        var inputData = try JSONEncoder().encode(fixture.legacyRecord)
        inputData.append(0x0A)
        try inputData.write(to: inputURL)

        XCTAssertThrowsError(
            try loadReplayResolvedInputs(
                from: inputURL,
                expectedInputSha256: sourceSHA256(inputData)
            )
        ) { error in
            XCTAssertTrue(String(describing: error).contains("missing sourceContentSha256"))
        }
    }

    private func replaySourceBindingFixture() throws -> (
        root: URL,
        legacyRecord: CreatureExportRecord,
        boundRecord: CreatureExportRecord,
        baseURL: URL,
        searchURL: URL,
        metaURL: URL
    ) {
        let root = try makeTempDirectory(prefix: "lenia-replay-source-binding")
        do {
            let baseData = try Data(
                contentsOf: dossierConfigsRoot().appendingPathComponent("base/paper_base_1c_128.json")
            )
            let searchData = try Data(
                contentsOf: dossierConfigsRoot().appendingPathComponent("base/paper_search_random.json")
            )
            let decoder = JSONDecoder()
            let baseConfig = try decoder.decode(LeniaBaseConfig.self, from: baseData)
            let searchConfig = try decoder.decode(ParsedSearchConfig.self, from: searchData)
            let runtime = try loadRuntimeConfig(from: baseData)
            let creature = SavedCreature(
                name: "source-bound-replay",
                ownerId: "test",
                genotype: runtime.params.toKernelParams(),
                initialCondition: InitConfig(
                    seed: runtime.initSeed,
                    patches: runtime.patches,
                    a_uniform: runtime.aUniform,
                    p_uniform: runtime.pUniform
                ),
                metrics: SimulationMetrics(
                    massMean: 1,
                    massStd: 0.1,
                    massMin: 0,
                    massMax: 2,
                    occupancyMean: 0.2,
                    varianceMean: 0.01,
                    energyMean: 0.3,
                    speedMean: 0.4,
                    pathLength: 10,
                    displacement: 2,
                    sampleCount: 2,
                    speedCount: 1,
                    gyration: 3,
                    centerVelocity: 0.5,
                    velocityX: 0.012,
                    velocityY: -0.004,
                    headingRad: 0,
                    isStable: true
                ),
                score: 0.9,
                scoreWeights: ["mass_mean": 1]
            )
            let artifacts = try XCTUnwrap(writeReplayExportArtifacts(
                exportRoot: root.appendingPathComponent("exports", isDirectory: true),
                baseConfig: baseConfig,
                searchConfig: searchConfig,
                creature: creature,
                runId: "source-run",
                campaignId: nil,
                score: creature.score,
                filtersPassed: true,
                reason: "test",
                exportedAt: Date(timeIntervalSinceReferenceDate: 0)
            ))
            let baseURL = try XCTUnwrap(artifacts.baseConfigURL)
            let searchURL = try XCTUnwrap(artifacts.searchConfigURL)
            let hashes = CreatureExportSourceContentSHA256(
                baseConfig: try sourceSHA256(baseURL),
                searchConfig: try sourceSHA256(searchURL),
                meta: try sourceSHA256(artifacts.metadataURL)
            )
            return (
                root,
                artifacts.record,
                replayRecord(artifacts.record, sourceContentSha256: hashes),
                baseURL,
                searchURL,
                artifacts.metadataURL
            )
        } catch {
            try? FileManager.default.removeItem(at: root)
            throw error
        }
    }

    private func replayRecord(
        _ record: CreatureExportRecord,
        sourceContentSha256: CreatureExportSourceContentSHA256
    ) -> CreatureExportRecord {
        CreatureExportRecord(
            creatureId: record.creatureId,
            name: record.name,
            ownerId: record.ownerId,
            runId: record.runId,
            campaignId: record.campaignId,
            bundleKind: record.bundleKind,
            exportDir: record.exportDir,
            baseConfigPath: record.baseConfigPath,
            searchConfigPath: record.searchConfigPath,
            payloadPath: record.payloadPath,
            exportedAt: record.exportedAt,
            reason: record.reason,
            score: record.score,
            filtersPassed: record.filtersPassed,
            runtimeFamily: record.runtimeFamily,
            runtimeCapabilities: record.runtimeCapabilities,
            specimenManifest: record.specimenManifest,
            sourceContentSha256: sourceContentSha256
        )
    }

    private func sourceSHA256(_ url: URL) throws -> String {
        sourceSHA256(try Data(contentsOf: url))
    }

    private func sourceSHA256(_ data: Data) -> String {
        SHA256.hash(data: data)
            .map { String(format: "%02x", $0) }
            .joined()
    }

    private func replayTestBaseConfig(
        profile: RuntimeProfile,
        implementation: ImplementationConfig
    ) throws -> LeniaBaseConfig {
        let data = Data(
            """
            {
              "backend": "metal",
              "profile": "paper",
              "grid": {"sx": 16, "sy": 16},
              "channels": 1,
              "connectivity": [[0]],
              "flow": {"dt": 0.2, "n": 2, "theta_A": 2.0},
              "implementation": {"mode": "flowlenia_2022_paper_equations"},
              "reintegration": {"dd": 1, "sigma": 0.65, "border": "torus"},
              "parameter_embedding": {"enabled": false, "mix": "none", "mix_seed": null},
              "params": {
                "mode": "explicit", "seed": null, "ranges": null,
                "r": [1.0], "b": [[1.0]], "w": [[0.1]], "a": [[1.0]],
                "m": [0.15], "s": [0.015], "h": [1.0], "R": 4.0
              },
              "init": {
                "seed": 1, "patches": [],
                "a_uniform": {"low": 0.0, "high": 1.0},
                "p_uniform": null, "state_patch": null, "p_state_patch": null
              },
              "run": {"steps": 4},
              "interventions": null
            }
            """.utf8
        )
        let decoded = try JSONDecoder().decode(LeniaBaseConfig.self, from: data)
        return LeniaBaseConfig(
            backend: decoded.backend,
            profile: profile,
            grid: decoded.grid,
            channels: decoded.channels,
            connectivity: decoded.connectivity,
            flow: decoded.flow,
            implementation: implementation,
            reintegration: decoded.reintegration,
            parameter_embedding: decoded.parameter_embedding,
            chemotaxis: decoded.chemotaxis,
            obstacle_field: decoded.obstacle_field,
            food: decoded.food,
            walls: decoded.walls,
            environment: decoded.environment,
            beam_mutation: decoded.beam_mutation,
            params: decoded.params,
            init: decoded.`init`,
            run: decoded.run,
            interventions: decoded.interventions
        )
    }
}
