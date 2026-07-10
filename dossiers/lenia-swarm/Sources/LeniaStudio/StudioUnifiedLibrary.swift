import Foundation
import LeniaArchive
import LeniaCore

func studioUnifiedLibraryEntries(
    local: [SavedCreature],
    remote: [CompendiumBrowseEntry],
    replayReference: (SavedCreature) -> StudioReplayReference?
) -> [CompendiumBrowseEntry] {
    var fingerprints = Set<String>()
    var identifiers = Set<UUID>()
    var result: [CompendiumBrowseEntry] = []

    for creature in local {
        let fingerprint = (creature.configHash ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard identifiers.insert(creature.id).inserted else { continue }
        if !fingerprint.isEmpty {
            guard fingerprints.insert(fingerprint).inserted else { continue }
        }
        let replay = replayReference(creature)
        result.append(
            CompendiumBrowseEntry(
                id: creature.id,
                creature: creature,
                runId: "local-library",
                runName: "Saved locally",
                hostId: nil,
                campaignId: nil,
                recordedAt: "",
                outputRoot: nil,
                runDir: nil,
                exportDir: nil,
                baseConfigPath: replay?.baseConfigPath,
                searchConfigPath: replay?.searchConfigPath,
                runtimeFamily: replay?.runtimeFamily,
                runtimeCapabilities: [],
                specimenManifest: nil,
                sourceMode: creature.initialConditionFamily == "studio-capture"
                    ? "studio-capture"
                    : "local-library",
                sourceAlgorithm: nil,
                traitLabels: [],
                catalogStatus: "active",
                specimenRecordID: "local:\(creature.id.uuidString.lowercased())",
                specimenSourceKind: "studio-library"
            )
        )
    }

    for entry in remote {
        let fingerprint = (entry.creature.configHash ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard identifiers.insert(entry.id).inserted else { continue }
        if !fingerprint.isEmpty {
            guard fingerprints.insert(fingerprint).inserted else { continue }
        }
        result.append(entry)
    }
    return result
}

func studioLibraryEntryMatches(
    _ entry: CompendiumBrowseEntry,
    search: String,
    stableOnly: Bool,
    minimumScore: Float?,
    favoritesOnly: Bool,
    favoriteIDs: Set<UUID>
) -> Bool {
    if stableOnly, !entry.isStable { return false }
    if let minimumScore, (entry.score ?? -.infinity) < minimumScore { return false }
    if favoritesOnly, !favoriteIDs.contains(entry.id) { return false }
    let terms = search
        .split(whereSeparator: \.isWhitespace)
        .map { $0.lowercased() }
    guard !terms.isEmpty else { return true }
    let haystack = [
        entry.name,
        entry.ownerId,
        entry.runName,
        entry.runtimeFamily ?? "",
        entry.sourceMode ?? "",
        entry.sourceAlgorithm ?? "",
        entry.traitLabels.joined(separator: " "),
    ]
        .joined(separator: " ")
        .lowercased()
    return terms.allSatisfy(haystack.contains)
}
