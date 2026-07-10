import Foundation
import LeniaCore

struct StudioSpecimenCaptureResult {
    let creature: SavedCreature
    let component: CapturedSpecimenComponent
    let libraryIndexURL: URL
}

enum StudioSpecimenCaptureStore {
    static func capture(
        name: String,
        ownerID: String,
        snapshot: FlowSandboxStateSnapshot,
        contract: FlowSandboxWorldContract,
        near point: SIMD2<Int>,
        existingCreatures: [SavedCreature]
    ) throws -> StudioSpecimenCaptureResult {
        let component = try captureSpecimenComponent(
            from: snapshot,
            near: point,
            wraps: contract.border == "torus"
        )
        if let duplicate = existingCreatures.first(where: { $0.configHash == component.fingerprint }) {
            throw StudioSpecimenCaptureStoreError.duplicate(duplicate.name)
        }
        let creature = component.savedCreature(
            name: name,
            ownerID: ownerID,
            contract: contract
        )
        let timestamp = ISO8601DateFormatter().string(from: Date())
            .replacingOccurrences(of: ":", with: "")
        let runID = "studio-capture-\(timestamp)-\(component.fingerprint.prefix(8))"
        let root = URL(
            fileURLWithPath: try resolveRuntimeAwareArtifactPath(
                "artifacts/studio-captures/\(runID)",
                dossier: "lenia-swarm"
            ),
            isDirectory: true
        )
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let entry = archiveResearchLibraryEntry(
            creature: creature,
            runId: runID,
            configHash: component.fingerprint,
            sourceMode: "studio-capture",
            sourceAlgorithm: "connected-component-v1"
        )
        let indexURL = try ResearchLibraryWriter.write(entries: [entry], runDirectory: root)
        return StudioSpecimenCaptureResult(
            creature: creature,
            component: component,
            libraryIndexURL: indexURL
        )
    }
}

enum StudioSpecimenCaptureStoreError: LocalizedError {
    case duplicate(String)

    var errorDescription: String? {
        switch self {
        case .duplicate(let name):
            return "This exact specimen is already saved as \(name)."
        }
    }
}
