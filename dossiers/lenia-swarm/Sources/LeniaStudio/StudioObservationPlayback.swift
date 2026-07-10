import Combine
import Foundation
import LeniaVisuals

protocol StudioObservationFrameSource: Sendable {
    var frameCount: Int { get }
    var nominalFramesPerSecond: Double { get }

    func frame(at index: Int) throws -> LeniaFieldFrame
}

enum StudioObservationPlaybackError: LocalizedError, Equatable {
    case emptySource
    case invalidFrameRate(Double)
    case invalidPlaybackRate(Double)
    case frameIndexOutOfBounds(Int)

    var errorDescription: String? {
        switch self {
        case .emptySource:
            return "An observation clip must contain at least one frame."
        case .invalidFrameRate(let rate):
            return "Observation frame rate must be finite and greater than zero; received \(rate)."
        case .invalidPlaybackRate(let rate):
            return "Playback rate must be finite and greater than zero; received \(rate)."
        case .frameIndexOutOfBounds(let index):
            return "Observation frame index \(index) is outside the clip."
        }
    }
}

struct StudioObservationClip: StudioObservationFrameSource, Sendable {
    let frames: [LeniaFieldFrame]
    let nominalFramesPerSecond: Double

    var frameCount: Int { frames.count }

    init(frames: [LeniaFieldFrame], nominalFramesPerSecond: Double) throws {
        guard !frames.isEmpty else {
            throw StudioObservationPlaybackError.emptySource
        }
        guard nominalFramesPerSecond.isFinite, nominalFramesPerSecond > 0 else {
            throw StudioObservationPlaybackError.invalidFrameRate(nominalFramesPerSecond)
        }
        self.frames = frames
        self.nominalFramesPerSecond = nominalFramesPerSecond
    }

    func frame(at index: Int) throws -> LeniaFieldFrame {
        guard frames.indices.contains(index) else {
            throw StudioObservationPlaybackError.frameIndexOutOfBounds(index)
        }
        return frames[index]
    }
}

@MainActor
final class StudioObservationPlayback: ObservableObject {
    @Published private(set) var currentFrame: LeniaFieldFrame
    @Published private(set) var currentFrameIndex = 0
    @Published private(set) var isPlaying = false
    @Published private(set) var playbackRate = 1.0
    @Published private(set) var isLooping: Bool

    let frameCount: Int
    let nominalFramesPerSecond: Double

    var currentStep: Int { currentFrame.step }
    var canPlay: Bool { frameCount > 1 }
    var canStepBackward: Bool { currentFrameIndex > 0 }
    var canStepForward: Bool { currentFrameIndex + 1 < frameCount }
    var progress: Double {
        guard frameCount > 1 else { return 0 }
        return Double(currentFrameIndex) / Double(frameCount - 1)
    }

    private let source: any StudioObservationFrameSource
    private var fractionalFrameIndex = 0.0

    init(
        source: any StudioObservationFrameSource,
        isLooping: Bool = true
    ) throws {
        guard source.frameCount > 0 else {
            throw StudioObservationPlaybackError.emptySource
        }
        guard source.nominalFramesPerSecond.isFinite,
              source.nominalFramesPerSecond > 0 else {
            throw StudioObservationPlaybackError.invalidFrameRate(source.nominalFramesPerSecond)
        }
        self.source = source
        self.frameCount = source.frameCount
        self.nominalFramesPerSecond = source.nominalFramesPerSecond
        self.isLooping = isLooping
        self.currentFrame = try source.frame(at: 0)
    }

    func play() throws {
        guard canPlay else { return }
        if !isLooping, currentFrameIndex == frameCount - 1 {
            try setPosition(0)
        }
        isPlaying = true
    }

    func pause() {
        isPlaying = false
    }

    func togglePlayback() throws {
        if isPlaying {
            pause()
        } else {
            try play()
        }
    }

    func seek(to index: Int) throws {
        guard sourceFrameIndices.contains(index) else {
            throw StudioObservationPlaybackError.frameIndexOutOfBounds(index)
        }
        try setPosition(index)
    }

    func seek(toProgress progress: Double) throws {
        let clampedProgress = min(1, max(0, progress.isFinite ? progress : 0))
        let index = Int((clampedProgress * Double(max(frameCount - 1, 0))).rounded())
        try setPosition(index)
    }

    func stepBackward() throws {
        pause()
        try setPosition(max(0, currentFrameIndex - 1))
    }

    func stepForward() throws {
        pause()
        try setPosition(min(frameCount - 1, currentFrameIndex + 1))
    }

    func setPlaybackRate(_ rate: Double) throws {
        guard rate.isFinite, rate > 0 else {
            throw StudioObservationPlaybackError.invalidPlaybackRate(rate)
        }
        playbackRate = rate
    }

    func setLooping(_ looping: Bool) {
        isLooping = looping
    }

    func advance(by elapsed: Duration) throws {
        guard isPlaying, canPlay else { return }
        let seconds = observationDurationSeconds(elapsed)
        guard seconds > 0 else { return }

        let nextPosition = fractionalFrameIndex
            + seconds * nominalFramesPerSecond * playbackRate
        if isLooping {
            let period = Double(frameCount)
            let wrappedPosition = nextPosition.truncatingRemainder(dividingBy: period)
            try setFractionalPosition(wrappedPosition >= 0 ? wrappedPosition : wrappedPosition + period)
            return
        }

        let finalPosition = Double(frameCount - 1)
        if nextPosition >= finalPosition {
            try setFractionalPosition(finalPosition)
            pause()
        } else {
            try setFractionalPosition(nextPosition)
        }
    }

    private var sourceFrameIndices: Range<Int> {
        0..<frameCount
    }

    private func setPosition(_ index: Int) throws {
        try setFractionalPosition(Double(index))
    }

    private func setFractionalPosition(_ position: Double) throws {
        let index = min(frameCount - 1, max(0, Int(position.rounded(.down))))
        guard index != currentFrameIndex else {
            fractionalFrameIndex = position
            return
        }
        let frame = try source.frame(at: index)
        fractionalFrameIndex = position
        currentFrame = frame
        currentFrameIndex = index
    }
}

private func observationDurationSeconds(_ duration: Duration) -> Double {
    Double(duration.components.seconds)
        + Double(duration.components.attoseconds) / 1_000_000_000_000_000_000.0
}
