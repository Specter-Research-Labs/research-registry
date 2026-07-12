import Foundation
import LeniaCore

struct TTFrameSequenceManifest: Decodable, Sendable {
    struct Frame: Decodable, Sendable {
        let step: Int
        let path: String
    }

    struct Metadata: Decodable, Sendable {
        let dt: Double?
        let dd: Int?
        let sigma: Double?
        let n: Int?
        let thetaA: Double?
        let border: String?
        let kernelProfile: String?
        let kernelCount: Int?
        let radius: Double?

        enum CodingKeys: String, CodingKey {
            case dt
            case dd
            case sigma
            case n
            case thetaA = "theta_a"
            case border
            case kernelProfile = "kernel_profile"
            case kernelCount = "kernel_count"
            case radius
        }
    }

    let manifestVersion: Int
    let kind: String
    let backend: String
    let configPath: String
    let steps: Int
    let frameEvery: Int
    let width: Int
    let height: Int
    let channels: Int
    let projection: String
    let batchIndex: Int
    let dtype: String
    let storage: String
    let finalMassPath: String?
    let metadata: Metadata?
    let frames: [Frame]

    enum CodingKeys: String, CodingKey {
        case manifestVersion = "manifest_version"
        case kind
        case backend
        case configPath = "config_path"
        case steps
        case frameEvery = "frame_every"
        case width
        case height
        case channels
        case projection
        case batchIndex = "batch_index"
        case dtype
        case storage
        case finalMassPath = "final_mass_path"
        case metadata
        case frames
    }
}

struct TTFrameSequence: Sendable {
    struct Sample: Sendable {
        let step: Int
        let bytes: Data
        let metrics: FlowSandboxMetrics
    }

    let manifestURL: URL
    let manifest: TTFrameSequenceManifest
    private let loadedSamples: [Sample]

    var title: String { manifestURL.deletingLastPathComponent().lastPathComponent }
    var frameCount: Int { loadedSamples.count }
    var width: Int { manifest.width }
    var height: Int { manifest.height }

    static func load(manifestURL: URL) throws -> TTFrameSequence {
        let data = try Data(contentsOf: manifestURL)
        let manifest = try JSONDecoder().decode(TTFrameSequenceManifest.self, from: data)
        guard manifest.kind == "lenia_tt_frame_sequence" else {
            throw TTFrameSequenceError.unsupportedKind(manifest.kind)
        }
        guard manifest.dtype == "uint8", manifest.storage == "raw_r8" else {
            throw TTFrameSequenceError.unsupportedStorage(dtype: manifest.dtype, storage: manifest.storage)
        }
        guard manifest.width > 0, manifest.height > 0, !manifest.frames.isEmpty else {
            throw TTFrameSequenceError.emptySequence
        }

        let rootURL = manifestURL.deletingLastPathComponent()
        let expectedSize = manifest.width * manifest.height
        let loadedSamples = try manifest.frames.map { frame in
            let data = try Data(contentsOf: rootURL.appendingPathComponent(frame.path))
            guard data.count == expectedSize else {
                throw TTFrameSequenceError.invalidFrameSize(
                    path: frame.path,
                    expected: expectedSize,
                    actual: data.count
                )
            }
            return Sample(
                step: frame.step,
                bytes: data,
                metrics: metrics(from: data)
            )
        }
        return TTFrameSequence(manifestURL: manifestURL, manifest: manifest, loadedSamples: loadedSamples)
    }

    subscript(index: Int) -> Sample {
        precondition(loadedSamples.indices.contains(index), "TT frame index \(index) is outside the sequence.")
        return loadedSamples[index]
    }

    private static func metrics(from bytes: Data) -> FlowSandboxMetrics {
        var sum: Float = 0
        var occupied = 0
        var peak: UInt8 = 0
        for byte in bytes {
            sum += Float(byte) / 255.0
            if byte >= 13 {
                occupied += 1
            }
            peak = max(peak, byte)
        }
        let count = Float(max(1, bytes.count))
        return FlowSandboxMetrics(
            massMean: sum / count,
            occupancy: Float(occupied) / count,
            foodMean: 0,
            wallFraction: 0,
            massPeak: Float(peak) / 255.0,
            foodPeak: 0,
            nonFiniteFraction: 0
        )
    }
}

enum TTFrameSequenceError: LocalizedError {
    case unsupportedKind(String)
    case unsupportedStorage(dtype: String, storage: String)
    case emptySequence
    case invalidFrameSize(path: String, expected: Int, actual: Int)

    var errorDescription: String? {
        switch self {
        case .unsupportedKind(let kind):
            return "Unsupported TT frame manifest kind: \(kind)"
        case .unsupportedStorage(let dtype, let storage):
            return "Unsupported TT frame storage: \(dtype) / \(storage)"
        case .emptySequence:
            return "TT frame sequence is empty or has invalid dimensions."
        case .invalidFrameSize(let path, let expected, let actual):
            return "TT frame \(path) has \(actual) bytes; expected \(expected)."
        }
    }
}

actor TTFrameSequenceRuntime {
    private let sequence: TTFrameSequence
    private var frameIndex = 0
    private var isPaused = true
    private var playbackTask: Task<Void, Never>?
    private var targetFrameDuration: Duration = .milliseconds(33)
    private var lastStepDurationMs = 0.0

    init(sequence: TTFrameSequence) {
        self.sequence = sequence
    }

    deinit {
        playbackTask?.cancel()
    }

    func start() {
        if playbackTask == nil {
            let runtime = self
            playbackTask = Task {
                await runtime.runLoop()
            }
        }
        isPaused = false
    }

    func pause() {
        isPaused = true
    }

    func resume() {
        start()
    }

    func stop() {
        playbackTask?.cancel()
        playbackTask = nil
        isPaused = true
    }

    func reset() {
        frameIndex = 0
        lastStepDurationMs = 0
    }

    func setSpeedCap(hz: Int) {
        let clamped = max(1, min(240, hz))
        targetFrameDuration = .milliseconds(max(1, Int((1000.0 / Double(clamped)).rounded())))
    }

    func setAutoFoodSpawn(enabled: Bool, probability: Float? = nil, patchSize: Int? = nil, value: Float? = nil) {
    }

    func worldContract() -> FlowSandboxWorldContract {
        let metadata = sequence.manifest.metadata
        return FlowSandboxWorldContract(
            backend: .metalFull,
            gridSize: sequence.width,
            channels: sequence.manifest.channels,
            parameterFieldMode: .none,
            parameterFieldCount: 0,
            kernelCount: metadata?.kernelCount ?? 0,
            dt: Float(metadata?.dt ?? 0),
            dd: metadata?.dd ?? 0,
            sigma: Float(metadata?.sigma ?? 0),
            n: metadata?.n ?? 0,
            thetaA: Float(metadata?.thetaA ?? 0),
            border: metadata?.border ?? "unknown",
            kernelProfile: metadata?.kernelProfile ?? "unknown",
            seed: 0,
            radius: Float(metadata?.radius ?? 0),
            executionSummary: "\(sequence.manifest.backend) compute export; Studio raw-frame playback",
            fieldSummary: "\(sequence.manifest.channels) TT matter lane(s), \(sequence.manifest.projection) projection",
            featureSummary: "Read-only exported frames; final state at \(sequence.manifest.finalMassPath ?? "mass_final.npy")",
            connectivitySummary: "Loaded \(sequence.frameCount) frame(s) from \(sequence.title)",
            kernels: []
        )
    }

    func snapshot(refreshMetrics _: Bool, projection _: LabFieldProjection) -> FlowSandboxSnapshot {
        let sample = sequence[frameIndex]
        return FlowSandboxSnapshot(
            step: sample.step,
            width: sequence.width,
            height: sequence.height,
            bytes: sample.bytes,
            metrics: sample.metrics
        )
    }

    func availableProjections() -> [LabFieldProjection] {
        [.matter]
    }

    func applyStroke(_ stroke: SandboxStroke) {
    }

    func applyCreatureStamp(_ stamp: CreatureStamp, center: SIMD2<Int>) {
    }

    func telemetry() -> FlowSandboxRuntimeTelemetry {
        FlowSandboxRuntimeTelemetry(
            lastStepDurationMs: lastStepDurationMs,
            realizedStepRateHz: lastStepDurationMs > 0 ? 1_000.0 / lastStepDurationMs : 0
        )
    }

    private func runLoop() async {
        while !Task.isCancelled {
            if isPaused {
                try? await Task.sleep(for: .milliseconds(25))
                continue
            }

            let startedAt = ContinuousClock.now
            frameIndex = (frameIndex + 1) % max(sequence.frameCount, 1)
            let elapsed = ContinuousClock.now - startedAt
            let remaining = targetFrameDuration - elapsed
            if remaining > .zero {
                try? await Task.sleep(for: remaining)
            }
            lastStepDurationMs = ttFrameDurationMs(ContinuousClock.now - startedAt)
        }
    }

}

private func ttFrameDurationMs(_ duration: Duration) -> Double {
    Double(duration.components.seconds) * 1_000.0 +
        Double(duration.components.attoseconds) / 1_000_000_000_000_000.0
}
