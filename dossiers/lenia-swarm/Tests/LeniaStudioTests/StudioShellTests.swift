import XCTest
@testable import LeniaStudio

final class StudioShellTests: XCTestCase {
    func testDestinationCommandsSelectExplicitWorkspace() {
        for destination in StudioDestination.allCases {
            XCTAssertEqual(
                studioDestination(
                    current: .lab,
                    applying: .showDestination(destination)
                ),
                destination
            )
        }
    }

    func testClusterCommandPreservesCurrentWorkspace() {
        XCTAssertEqual(
            studioDestination(current: .compare, applying: .openClusterConnection),
            .compare
        )
    }

    func testConnectionStateDoesNotStealStudioDestination() {
        let connectionStates: [ConnectionState] = [
            .disconnected,
            .connecting,
            .connected(role: .host),
            .connected(role: .worker),
            .connected(role: .compendium),
            .error("boom"),
        ]

        for destination in StudioDestination.allCases {
            for connectionState in connectionStates {
                XCTAssertEqual(
                    studioDestinationAfterConnectionChange(
                        current: destination,
                        connectionState: connectionState
                    ),
                    destination
                )
            }
        }
    }

    func testCommandCenterPublishesDistinctEvents() throws {
        let center = StudioCommandCenter()

        center.send(.showDestination(.library))
        let first = try XCTUnwrap(center.latestEvent)

        center.send(.showDestination(.library))
        let second = try XCTUnwrap(center.latestEvent)

        XCTAssertEqual(first.command, .showDestination(.library))
        XCTAssertEqual(second.command, .showDestination(.library))
        XCTAssertNotEqual(first.id, second.id)
    }

    func testDestinationMetadataIsComplete() {
        XCTAssertEqual(StudioDestination.allCases.map(\.title), ["Lab", "Library", "Compare", "Runs"])
        XCTAssertTrue(StudioDestination.allCases.allSatisfy { !$0.systemImage.isEmpty })
        XCTAssertEqual(StudioDestination.allCases.map(\.shortcutNumber), ["1", "2", "3", "4"])
        XCTAssertTrue(StudioDestination.allCases.allSatisfy { $0.accessibilityHint.contains($0.title) })
    }

    func testInitialDestinationUsesOptionalLaunchEnvironment() {
        XCTAssertEqual(studioInitialDestination(environment: [:]), .lab)
        XCTAssertEqual(
            studioInitialDestination(
                environment: [studioInitialDestinationEnvironmentKey: " compare "]
            ),
            .compare
        )
        XCTAssertEqual(
            studioInitialDestination(
                environment: [studioInitialDestinationEnvironmentKey: "invalid"]
            ),
            .lab
        )
    }

    func testCompareTrayReadinessKeepsPartialSelectionVisible() {
        XCTAssertEqual(studioCompareTrayReadiness(for: -1), .empty)
        XCTAssertEqual(studioCompareTrayReadiness(for: 0), .empty)
        XCTAssertEqual(studioCompareTrayReadiness(for: 1), .needsOneMore)
        XCTAssertEqual(studioCompareTrayReadiness(for: 2), .ready)
        XCTAssertEqual(studioCompareTrayReadiness(for: 4), .ready)
    }

    func testComparisonLayoutUsesReadableResponsiveColumns() {
        XCTAssertEqual(comparisonGridColumnCount(availableWidth: 700, entryCount: 4), 1)
        XCTAssertEqual(comparisonGridColumnCount(availableWidth: 779, entryCount: 2), 1)
        XCTAssertEqual(comparisonGridColumnCount(availableWidth: 780, entryCount: 2), 2)
        XCTAssertEqual(comparisonGridColumnCount(availableWidth: 1_400, entryCount: 4), 2)
        XCTAssertEqual(comparisonGridColumnCount(availableWidth: 1_400, entryCount: 1), 1)
    }

    func testComparisonMatrixMinimumWidthScalesWithSpecimens() {
        XCTAssertGreaterThan(
            comparisonMetricMatrixMinimumWidth(entryCount: 4),
            comparisonMetricMatrixMinimumWidth(entryCount: 2)
        )
        XCTAssertEqual(
            comparisonMetricMatrixMinimumWidth(entryCount: 0),
            comparisonMetricMatrixMinimumWidth(entryCount: 1)
        )
    }

    func testComparisonPlaybackGroupTracksAsyncChildPauseChanges() {
        let entries = ["baseline", "candidate"]
        var state = ComparisonPlaybackGroupState()

        XCTAssertTrue(state.anyPaused(entryIDs: entries))
        XCTAssertFalse(state.targetPaused(entryIDs: entries))

        state.record(entryID: "baseline", isPaused: false)
        state.record(entryID: "candidate", isPaused: false)
        XCTAssertFalse(state.anyPaused(entryIDs: entries))
        XCTAssertTrue(state.targetPaused(entryIDs: entries))

        state.record(entryID: "candidate", isPaused: true)
        XCTAssertTrue(state.anyPaused(entryIDs: entries))
        XCTAssertFalse(state.targetPaused(entryIDs: entries))

        state.retain(entryIDs: ["baseline"])
        XCTAssertEqual(state.pausedByEntryID, ["baseline": false])
    }
}
