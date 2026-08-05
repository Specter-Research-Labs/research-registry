import Foundation
import Combine
import CoreGraphics
import ImageIO
import LeniaCore
import UniformTypeIdentifiers

enum StudioExperimentActionKind: String, Codable, Sendable {
    case checkpoint
    case brush
    case stamp
    case capture
    case branch
}

struct StudioExperimentAction: Codable, Identifiable, Sendable {
    let id: UUID
    let recordedAt: Date
    let step: Int
    let kind: StudioExperimentActionKind
    let summary: String
    let details: [String: String]

    init(
        id: UUID = UUID(),
        recordedAt: Date = Date(),
        step: Int,
        kind: StudioExperimentActionKind,
        summary: String,
        details: [String: String] = [:]
    ) {
        self.id = id
        self.recordedAt = recordedAt
        self.step = step
        self.kind = kind
        self.summary = summary
        self.details = details
    }
}

struct StudioExperimentCheckpoint: Identifiable, Sendable {
    let id: UUID
    let label: String
    let recordedAt: Date
    let snapshot: FlowSandboxStateSnapshot

    init(
        id: UUID = UUID(),
        label: String,
        recordedAt: Date = Date(),
        snapshot: FlowSandboxStateSnapshot
    ) {
        self.id = id
        self.label = label
        self.recordedAt = recordedAt
        self.snapshot = snapshot
    }

    var estimatedBytes: Int {
        let floatCount = snapshot.mass.count
            + snapshot.params.count
            + snapshot.food.count
            + snapshot.walls.count
        return floatCount * MemoryLayout<Float>.stride
    }
}

@MainActor
final class StudioExperimentHistory: ObservableObject {
    @Published private(set) var checkpoints: [StudioExperimentCheckpoint] = []
    @Published private(set) var actions: [StudioExperimentAction] = []
    @Published private(set) var cursor: Int?

    let maximumBytes: Int
    let maximumActions: Int

    init(maximumBytes: Int = 256 * 1_024 * 1_024, maximumActions: Int = 2_000) {
        self.maximumBytes = max(1, maximumBytes)
        self.maximumActions = max(1, maximumActions)
    }

    var canUndo: Bool {
        guard let cursor else { return false }
        return cursor > 0
    }

    var canRedo: Bool {
        guard let cursor else { return false }
        return cursor + 1 < checkpoints.count
    }

    var current: StudioExperimentCheckpoint? {
        guard let cursor, checkpoints.indices.contains(cursor) else { return nil }
        return checkpoints[cursor]
    }

    var retainedBytes: Int {
        checkpoints.reduce(0) { $0 + $1.estimatedBytes }
    }

    func clear() {
        checkpoints = []
        actions = []
        cursor = nil
    }

    func reset(initial snapshot: FlowSandboxStateSnapshot, label: String = "Initial") {
        checkpoints = [StudioExperimentCheckpoint(label: label, snapshot: snapshot)]
        actions = [
            StudioExperimentAction(
                step: snapshot.step,
                kind: .checkpoint,
                summary: label
            )
        ]
        cursor = 0
    }

    func record(
        kind: StudioExperimentActionKind,
        summary: String,
        step: Int,
        details: [String: String] = [:]
    ) {
        actions.append(
            StudioExperimentAction(
                step: step,
                kind: kind,
                summary: summary,
                details: details
            )
        )
        if actions.count > maximumActions {
            actions.removeFirst(actions.count - maximumActions)
        }
    }

    func checkpoint(_ snapshot: FlowSandboxStateSnapshot, label: String) {
        if let cursor, cursor + 1 < checkpoints.count {
            checkpoints.removeSubrange((cursor + 1)..<checkpoints.endIndex)
            record(kind: .branch, summary: "Branched from step \(snapshot.step)", step: snapshot.step)
        }
        checkpoints.append(StudioExperimentCheckpoint(label: label, snapshot: snapshot))
        cursor = checkpoints.count - 1
        record(kind: .checkpoint, summary: label, step: snapshot.step)
        trimToBudget()
    }

    func undo() -> FlowSandboxStateSnapshot? {
        guard let cursor, cursor > 0 else { return nil }
        self.cursor = cursor - 1
        return checkpoints[cursor - 1].snapshot
    }

    func redo() -> FlowSandboxStateSnapshot? {
        guard let cursor, cursor + 1 < checkpoints.count else { return nil }
        self.cursor = cursor + 1
        return checkpoints[cursor + 1].snapshot
    }

    func restore(checkpointID: UUID) -> FlowSandboxStateSnapshot? {
        guard let index = checkpoints.firstIndex(where: { $0.id == checkpointID }) else {
            return nil
        }
        cursor = index
        return checkpoints[index].snapshot
    }

    private func trimToBudget() {
        while checkpoints.count > 1, retainedBytes > maximumBytes {
            checkpoints.removeFirst()
            if let cursor {
                self.cursor = max(0, cursor - 1)
            }
        }
    }
}

struct StudioExperimentKernelRecord: Codable, Sendable {
    let id: Int
    let radius: Float
    let center: Float
    let sigma: Float
    let gain: Float
    let beta: [Float]
    let weights: [Float]
    let anchors: [Float]

    init(_ kernel: FlowSandboxKernelContract) {
        id = kernel.id
        radius = kernel.radius
        center = kernel.center
        sigma = kernel.sigma
        gain = kernel.gain
        beta = kernel.beta
        weights = kernel.weights
        anchors = kernel.anchors
    }
}

struct StudioExperimentContractRecord: Codable, Sendable {
    let backend: String
    let gridSize: Int
    let channels: Int
    let parameterFieldMode: String
    let parameterFieldCount: Int
    let kernelCount: Int
    let dt: Float
    let dd: Int
    let sigma: Float
    let n: Int
    let thetaA: Float
    let border: String
    let kernelProfile: String
    let seed: Int
    let radius: Float
    let kernels: [StudioExperimentKernelRecord]

    init(_ contract: FlowSandboxWorldContract) {
        backend = contract.backend.rawValue
        gridSize = contract.gridSize
        channels = contract.channels
        parameterFieldMode = contract.parameterFieldMode.displayName
        parameterFieldCount = contract.parameterFieldCount
        kernelCount = contract.kernelCount
        dt = contract.dt
        dd = contract.dd
        sigma = contract.sigma
        n = contract.n
        thetaA = contract.thetaA
        border = contract.border
        kernelProfile = contract.kernelProfile
        seed = contract.seed
        radius = contract.radius
        kernels = contract.kernels.map(StudioExperimentKernelRecord.init)
    }
}

struct StudioExperimentCheckpointRecord: Codable, Sendable {
    let id: UUID
    let label: String
    let recordedAt: Date
    let step: Int
    let file: String
}

struct StudioExperimentManifest: Codable, Sendable {
    let schemaVersion: Int
    let title: String
    let sourceName: String
    let createdAt: Date
    let exportedAt: Date
    let contract: StudioExperimentContractRecord
    let actions: [StudioExperimentAction]
    let checkpoints: [StudioExperimentCheckpointRecord]
    let currentCheckpointID: UUID?
    let previewFile: String
    let timelineFile: String?
}

enum StudioExperimentBundleError: LocalizedError {
    case destinationExists(String)
    case emptyHistory
    case mediaEncodingFailed(String)

    var errorDescription: String? {
        switch self {
        case .destinationExists(let path):
            return "Experiment destination already exists: \(path)"
        case .emptyHistory:
            return "The experiment has no checkpoints to export."
        case .mediaEncodingFailed(let filename):
            return "Failed to encode experiment media: \(filename)"
        }
    }
}

enum StudioExperimentBundleWriter {
    @MainActor
    static func write(
        title: String,
        sourceName: String,
        contract: FlowSandboxWorldContract,
        history: StudioExperimentHistory,
        to destination: URL
    ) throws {
        guard !history.checkpoints.isEmpty else {
            throw StudioExperimentBundleError.emptyHistory
        }
        guard !FileManager.default.fileExists(atPath: destination.path) else {
            throw StudioExperimentBundleError.destinationExists(destination.path)
        }

        let temporary = destination
            .deletingLastPathComponent()
            .appendingPathComponent(".\(destination.lastPathComponent).\(UUID().uuidString).tmp", isDirectory: true)
        let checkpointDirectory = temporary.appendingPathComponent("checkpoints", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: temporary) }

        try FileManager.default.createDirectory(at: checkpointDirectory, withIntermediateDirectories: true)
        let encoder = PropertyListEncoder()
        encoder.outputFormat = .binary
        var records: [StudioExperimentCheckpointRecord] = []
        for checkpoint in history.checkpoints {
            let filename = "\(checkpoint.id.uuidString.lowercased()).plist"
            let relativePath = "checkpoints/\(filename)"
            try encoder.encode(checkpoint.snapshot).write(
                to: checkpointDirectory.appendingPathComponent(filename),
                options: .atomic
            )
            records.append(
                StudioExperimentCheckpointRecord(
                    id: checkpoint.id,
                    label: checkpoint.label,
                    recordedAt: checkpoint.recordedAt,
                    step: checkpoint.snapshot.step,
                    file: relativePath
                )
            )
        }

        let current = history.current ?? history.checkpoints[history.checkpoints.count - 1]
        let previewFilename = "preview.png"
        try writePreview(
            snapshot: current.snapshot,
            to: temporary.appendingPathComponent(previewFilename)
        )
        let timelineFilename: String?
        if history.checkpoints.count > 1 {
            timelineFilename = "timeline.gif"
            try writeTimeline(
                checkpoints: history.checkpoints,
                to: temporary.appendingPathComponent("timeline.gif")
            )
        } else {
            timelineFilename = nil
        }

        let manifest = StudioExperimentManifest(
            schemaVersion: 2,
            title: title,
            sourceName: sourceName,
            createdAt: history.checkpoints[0].recordedAt,
            exportedAt: Date(),
            contract: StudioExperimentContractRecord(contract),
            actions: history.actions,
            checkpoints: records,
            currentCheckpointID: history.current?.id,
            previewFile: previewFilename,
            timelineFile: timelineFilename
        )
        let jsonEncoder = JSONEncoder()
        jsonEncoder.dateEncodingStrategy = .iso8601
        jsonEncoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        try jsonEncoder.encode(manifest).write(
            to: temporary.appendingPathComponent("manifest.json"),
            options: .atomic
        )
        try FileManager.default.moveItem(at: temporary, to: destination)
    }

    private static func writePreview(
        snapshot: FlowSandboxStateSnapshot,
        to destination: URL
    ) throws {
        guard let image = image(for: snapshot),
              let encoder = CGImageDestinationCreateWithURL(
                destination as CFURL,
                UTType.png.identifier as CFString,
                1,
                nil
              ) else {
            throw StudioExperimentBundleError.mediaEncodingFailed(destination.lastPathComponent)
        }
        CGImageDestinationAddImage(encoder, image, nil)
        guard CGImageDestinationFinalize(encoder) else {
            throw StudioExperimentBundleError.mediaEncodingFailed(destination.lastPathComponent)
        }
    }

    private static func writeTimeline(
        checkpoints: [StudioExperimentCheckpoint],
        to destination: URL
    ) throws {
        guard let encoder = CGImageDestinationCreateWithURL(
            destination as CFURL,
            UTType.gif.identifier as CFString,
            checkpoints.count,
            nil
        ) else {
            throw StudioExperimentBundleError.mediaEncodingFailed(destination.lastPathComponent)
        }
        let fileProperties = [
            kCGImagePropertyGIFDictionary: [kCGImagePropertyGIFLoopCount: 0]
        ] as CFDictionary
        CGImageDestinationSetProperties(encoder, fileProperties)
        for checkpoint in checkpoints {
            guard let frame = image(for: checkpoint.snapshot) else {
                throw StudioExperimentBundleError.mediaEncodingFailed(destination.lastPathComponent)
            }
            let frameProperties = [
                kCGImagePropertyGIFDictionary: [kCGImagePropertyGIFDelayTime: 0.12]
            ] as CFDictionary
            CGImageDestinationAddImage(encoder, frame, frameProperties)
        }
        guard CGImageDestinationFinalize(encoder) else {
            throw StudioExperimentBundleError.mediaEncodingFailed(destination.lastPathComponent)
        }
    }

    private static func image(for snapshot: FlowSandboxStateSnapshot) -> CGImage? {
        guard snapshot.width > 0,
              snapshot.height > 0,
              snapshot.channels > 0,
              snapshot.mass.count == snapshot.width * snapshot.height * snapshot.channels else {
            return nil
        }
        var pixels = [UInt8](
            repeating: 0,
            count: snapshot.width * snapshot.height * 4
        )
        for y in 0..<snapshot.height {
            for x in 0..<snapshot.width {
                let sourceCell = x * snapshot.height + y
                let sourceBase = sourceCell * snapshot.channels
                var matter: Float = 0
                for channel in 0..<snapshot.channels {
                    matter += snapshot.mass[sourceBase + channel]
                }
                let value = max(0, min(1, matter))
                let target = (y * snapshot.width + x) * 4
                pixels[target] = UInt8(12 + value * 210)
                pixels[target + 1] = UInt8(18 + value * 225)
                pixels[target + 2] = UInt8(28 + value * 165)
                pixels[target + 3] = 255
            }
        }
        guard let provider = CGDataProvider(data: Data(pixels) as CFData) else {
            return nil
        }
        return CGImage(
            width: snapshot.width,
            height: snapshot.height,
            bitsPerComponent: 8,
            bitsPerPixel: 32,
            bytesPerRow: snapshot.width * 4,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.noneSkipLast.rawValue),
            provider: provider,
            decode: nil,
            shouldInterpolate: false,
            intent: .defaultIntent
        )
    }
}
