import XCTest
import LeniaVisuals
@testable import LeniaStudio

@MainActor
final class StudioObservationPlaybackTests: XCTestCase {
    func testFrameReadsDoNotAdvancePlayback() throws {
        let playback = try makePlayback(frameCount: 4, framesPerSecond: 2)
        try playback.play()

        XCTAssertEqual(playback.currentFrame.step, 0)
        XCTAssertEqual(playback.currentFrame.step, 0)
        XCTAssertEqual(playback.currentFrameIndex, 0)

        try playback.advance(by: .milliseconds(500))
        XCTAssertEqual(playback.currentFrame.step, 10)
        XCTAssertEqual(playback.currentFrameIndex, 1)
    }

    func testElapsedTimeAndPlaybackRateSelectExpectedFrame() throws {
        let playback = try makePlayback(frameCount: 8, framesPerSecond: 4)
        try playback.setPlaybackRate(2)
        try playback.play()

        try playback.advance(by: .milliseconds(375))

        XCTAssertEqual(playback.currentFrameIndex, 3)
        XCTAssertEqual(playback.currentStep, 30)
    }

    func testFractionalElapsedTimeAccumulatesWithoutPollingDrift() throws {
        let playback = try makePlayback(frameCount: 8, framesPerSecond: 4)
        try playback.play()

        try playback.advance(by: .milliseconds(100))
        try playback.advance(by: .milliseconds(100))
        XCTAssertEqual(playback.currentFrameIndex, 0)

        try playback.advance(by: .milliseconds(50))
        XCTAssertEqual(playback.currentFrameIndex, 1)
    }

    func testPauseSeekAndFrameStepsAreExact() throws {
        let playback = try makePlayback(frameCount: 5, framesPerSecond: 30)
        try playback.play()
        try playback.seek(to: 3)
        playback.pause()

        try playback.advance(by: .seconds(5))
        XCTAssertEqual(playback.currentFrameIndex, 3)
        XCTAssertEqual(playback.currentStep, 30)

        try playback.stepBackward()
        XCTAssertEqual(playback.currentFrameIndex, 2)
        XCTAssertFalse(playback.isPlaying)

        try playback.stepForward()
        XCTAssertEqual(playback.currentFrameIndex, 3)
        XCTAssertFalse(playback.isPlaying)
    }

    func testNonLoopingPlaybackStopsAtEndAndReplayRestarts() throws {
        let playback = try makePlayback(frameCount: 3, framesPerSecond: 2, isLooping: false)
        try playback.play()

        try playback.advance(by: .seconds(10))
        XCTAssertEqual(playback.currentFrameIndex, 2)
        XCTAssertFalse(playback.isPlaying)

        try playback.play()
        XCTAssertEqual(playback.currentFrameIndex, 0)
        XCTAssertTrue(playback.isPlaying)
    }

    func testLoopingPlaybackWrapsUsingElapsedTime() throws {
        let playback = try makePlayback(frameCount: 3, framesPerSecond: 2, isLooping: true)
        try playback.play()

        try playback.advance(by: .seconds(2))

        XCTAssertEqual(playback.currentFrameIndex, 1)
        XCTAssertTrue(playback.isPlaying)
    }

    func testProgressSeekClampsToClipBounds() throws {
        let playback = try makePlayback(frameCount: 5, framesPerSecond: 30)

        try playback.seek(toProgress: 0.5)
        XCTAssertEqual(playback.currentFrameIndex, 2)
        XCTAssertEqual(playback.progress, 0.5, accuracy: 1e-9)

        try playback.seek(toProgress: 2)
        XCTAssertEqual(playback.currentFrameIndex, 4)

        try playback.seek(toProgress: -1)
        XCTAssertEqual(playback.currentFrameIndex, 0)
    }

    func testInvalidSourcesRatesAndIndicesFailLoudly() throws {
        XCTAssertThrowsError(
            try StudioObservationClip(frames: [], nominalFramesPerSecond: 30)
        ) { error in
            XCTAssertEqual(error as? StudioObservationPlaybackError, .emptySource)
        }

        XCTAssertThrowsError(
            try StudioObservationClip(frames: [Self.frame(index: 0)], nominalFramesPerSecond: 0)
        ) { error in
            XCTAssertEqual(error as? StudioObservationPlaybackError, .invalidFrameRate(0))
        }

        let playback = try makePlayback(frameCount: 2, framesPerSecond: 30)
        XCTAssertThrowsError(try playback.setPlaybackRate(0)) { error in
            XCTAssertEqual(error as? StudioObservationPlaybackError, .invalidPlaybackRate(0))
        }
        XCTAssertThrowsError(try playback.seek(to: 2)) { error in
            XCTAssertEqual(error as? StudioObservationPlaybackError, .frameIndexOutOfBounds(2))
        }
    }

    func testSingleFrameClipRemainsPaused() throws {
        let playback = try makePlayback(frameCount: 1, framesPerSecond: 30)

        try playback.play()
        try playback.advance(by: .seconds(1))

        XCTAssertFalse(playback.canPlay)
        XCTAssertFalse(playback.isPlaying)
        XCTAssertEqual(playback.currentFrameIndex, 0)
        XCTAssertEqual(playback.progress, 0)
    }

    func testLazySourceFailureDoesNotPartiallyAdvancePosition() throws {
        let source = FailingObservationSource(
            frames: (0..<3).map(Self.frame(index:)),
            failingIndex: 1
        )
        let playback = try StudioObservationPlayback(source: source)
        try playback.play()

        XCTAssertThrowsError(try playback.advance(by: .seconds(1)))
        XCTAssertEqual(playback.currentFrameIndex, 0)
        XCTAssertEqual(playback.currentStep, 0)
        XCTAssertEqual(playback.progress, 0)
    }

    private func makePlayback(
        frameCount: Int,
        framesPerSecond: Double,
        isLooping: Bool = true
    ) throws -> StudioObservationPlayback {
        let clip = try StudioObservationClip(
            frames: (0..<frameCount).map(Self.frame(index:)),
            nominalFramesPerSecond: framesPerSecond
        )
        return try StudioObservationPlayback(source: clip, isLooping: isLooping)
    }

    private static func frame(index: Int) -> LeniaFieldFrame {
        LeniaFieldFrame(
            step: index * 10,
            width: 2,
            height: 2,
            bytes: Data(repeating: UInt8(index), count: 4)
        )
    }
}

private struct FailingObservationSource: StudioObservationFrameSource {
    let frames: [LeniaFieldFrame]
    let failingIndex: Int
    let nominalFramesPerSecond = 1.0

    var frameCount: Int { frames.count }

    func frame(at index: Int) throws -> LeniaFieldFrame {
        if index == failingIndex {
            throw StudioObservationPlaybackError.frameIndexOutOfBounds(index)
        }
        return frames[index]
    }
}
