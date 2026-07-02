import ArgumentParser
import Foundation
import XCTest
@testable import LeniaCLIKit

final class CLISurfaceTests: XCTestCase {
    private var dossierRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }

    func testTopLevelCommandGroupsRemainStable() {
        XCTAssertEqual(
            Set(commandNames(LeniaSwarm.configuration.subcommands)),
            Set([
                "discover",
                "orchestrate",
                "index",
                "analyze",
                "intervene",
                "publish",
                "tt",
                "benchmark",
                "export-reference",
            ])
        )
    }

    func testTTSubcommandsRemainStable() {
        XCTAssertEqual(
            Set(commandNames(TTCommands.configuration.subcommands)),
            Set([
                "run",
            ])
        )
    }

    func testDiscoverSubcommandsRemainStable() {
        XCTAssertEqual(
            Set(commandNames(DiscoverCommands.configuration.subcommands)),
            Set([
                "local",
                "evolve",
                "mutate",
                "sensorimotor-2024",
                "atlas-2026",
                "rd-2023",
                "qd-2024",
                "ecology-2025",
                "curiosity-2025",
                "map-elites",
                "sensorimotor-flowlenia",
                "evaluate",
            ])
        )
    }

    func testOrchestrateSubcommandsRemainStable() {
        XCTAssertEqual(
            Set(commandNames(OrchestrateCommands.configuration.subcommands)),
            Set([
                "controller",
                "worker",
                "campaign",
                "portfolio",
            ])
        )
    }

    func testReadmeUsesGroupedCLIExamples() throws {
        let readme = try String(contentsOf: dossierRoot.appendingPathComponent("README.md"), encoding: .utf8)

        XCTAssertTrue(readme.contains("LeniaCLI orchestrate controller"))
        XCTAssertTrue(readme.contains("LeniaCLI orchestrate worker"))
        XCTAssertTrue(readme.contains("LeniaCLI discover evolve"))
        XCTAssertTrue(readme.contains("LeniaCLI discover mutate"))

        XCTAssertFalse(readme.contains("LeniaCLI controller \\"))
        XCTAssertFalse(readme.contains("LeniaCLI worker \\"))
        XCTAssertFalse(readme.contains("LeniaCLI evolve \\"))
        XCTAssertFalse(readme.contains("LeniaCLI mutate \\"))
    }

    func testResearchModesUseGroupedCLIExamples() throws {
        let path = dossierRoot.appendingPathComponent("docs/contracts/ResearchModes.md")
        let text = try String(contentsOf: path, encoding: .utf8)

        XCTAssertTrue(text.contains("LeniaCLI discover evolve"))
        XCTAssertTrue(text.contains("LeniaCLI discover rd-2023"))
        XCTAssertFalse(text.contains("LeniaCLI evolve --config"))
    }

    private func commandNames(_ commands: [ParsableCommand.Type]) -> [String] {
        commands.compactMap { $0.configuration.commandName }
    }
}
