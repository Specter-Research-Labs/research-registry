import XCTest
import LeniaArchive
import LeniaCore
@testable import LeniaStudio

@MainActor
final class StudioUnifiedLibraryTests: XCTestCase {
    func testUnifiedLibraryPrefersLocalFingerprintAndKeepsUniqueRemoteEntries() {
        let local = savedCreature(id: UUID(), name: "Local capture", hash: "same", stable: true)
        let duplicate = savedCreature(id: UUID(), name: "Remote duplicate", hash: "same", stable: true)
        let unique = savedCreature(id: UUID(), name: "Remote novel", hash: "novel", stable: false)
        let entries = studioUnifiedLibraryEntries(
            local: [local],
            remote: [browseEntry(duplicate), browseEntry(unique)],
            replayReference: { _ in nil }
        )

        XCTAssertEqual(entries.map(\.name), ["Local capture", "Remote novel"])
        XCTAssertEqual(entries.first?.runId, "local-library")
    }

    func testLocalFilteringCombinesTermsStabilityScoreAndFavorites() {
        let creature = savedCreature(id: UUID(), name: "Bright Orbium", hash: "bright", stable: true)
        let entry = browseEntry(creature)
        XCTAssertTrue(studioLibraryEntryMatches(
            entry,
            search: "bright local",
            stableOnly: true,
            minimumScore: 0,
            favoritesOnly: true,
            favoriteIDs: [entry.id]
        ))
        XCTAssertFalse(studioLibraryEntryMatches(
            entry,
            search: "bright missing",
            stableOnly: true,
            minimumScore: nil,
            favoritesOnly: false,
            favoriteIDs: []
        ))
    }

    func testDisplayedLibraryResultsReconcileHiddenSelection() {
        let hidden = UUID()
        let firstVisible = UUID()
        let secondVisible = UUID()

        XCTAssertEqual(
            reconciledCompendiumSelection(
                selectedIDs: [hidden],
                displayedIDs: [firstVisible, secondVisible]
            ),
            [firstVisible]
        )
        XCTAssertEqual(
            reconciledCompendiumSelection(
                selectedIDs: [hidden, secondVisible],
                displayedIDs: [firstVisible, secondVisible]
            ),
            [secondVisible]
        )
        XCTAssertEqual(
            reconciledCompendiumSelection(
                selectedIDs: [hidden],
                displayedIDs: []
            ),
            []
        )
    }

    func testCompareTrayRejectsFifthEntryWithoutEvicting() {
        let state = AppState()
        let entries = (0..<5).map { index in
            StudioCompareEntry.saved(
                savedCreature(
                    id: UUID(),
                    name: "Creature \(index)",
                    hash: "hash-\(index)",
                    stable: true
                )
            )
        }
        for entry in entries.prefix(4) {
            XCTAssertTrue(state.addCompareEntry(entry))
        }
        XCTAssertFalse(state.addCompareEntry(entries[4]))
        XCTAssertEqual(state.compareTray.map(\.id), Array(entries.prefix(4)).map(\.id))
    }

    private func browseEntry(_ creature: SavedCreature) -> CompendiumBrowseEntry {
        CompendiumBrowseEntry(
            id: creature.id,
            creature: creature,
            runId: "local-run",
            runName: "Local run",
            hostId: nil,
            campaignId: nil,
            recordedAt: "",
            outputRoot: nil,
            runDir: nil,
            exportDir: nil,
            baseConfigPath: nil,
            searchConfigPath: nil,
            runtimeFamily: "flow-lenia",
            runtimeCapabilities: [],
            specimenManifest: nil,
            sourceMode: "local",
            sourceAlgorithm: nil,
            traitLabels: [],
            specimenRecordID: creature.id.uuidString,
            specimenSourceKind: "test"
        )
    }

    private func savedCreature(
        id: UUID,
        name: String,
        hash: String,
        stable: Bool
    ) -> SavedCreature {
        SavedCreature(
            id: id,
            name: name,
            ownerId: "local worker",
            genotype: KernelParams(
                r: [0.5],
                b: [[1, 0, 0]],
                w: [[0.2, 0.2, 0.2]],
                a: [[0.5, 0.5, 0.5]],
                m: [0.15],
                s: [0.017],
                h: [0.1],
                R: 13
            ),
            initialCondition: InitConfig(
                seed: 1,
                patches: [PatchConfig(center: [16, 16], size: 8)],
                a_uniform: UniformRange(low: 0.1, high: 0.2),
                p_uniform: nil
            ),
            metrics: metrics(stable: stable),
            score: 1,
            configHash: hash
        )
    }

    private func metrics(stable: Bool) -> SimulationMetrics {
        SimulationMetrics(
            massMean: 0.2,
            massStd: 0.1,
            massMin: 0,
            massMax: 1,
            occupancyMean: 0.25,
            varianceMean: 0.01,
            energyMean: 0.2,
            speedMean: 0.1,
            pathLength: 2,
            displacement: 1,
            sampleCount: 10,
            speedCount: 9,
            gyration: 3,
            centerVelocity: 0.1,
            isStable: stable,
            occupiedFraction: 0.25,
            componentCount: 1,
            largestComponentFraction: 1
        )
    }
}
