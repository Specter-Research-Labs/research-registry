import Foundation
import XCTest
@testable import LeniaCore

final class VideoEncodingTests: XCTestCase {
    private func scratchURL(_ name: String) throws -> URL {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("video-encoding-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: directory) }
        return directory.appendingPathComponent(name)
    }

    func testStreamsRawGrayFramesToMP4() throws {
        let url = try scratchURL("gray.mp4")
        try encodeMP4(ffmpeg: "ffmpeg", outputURL: url, fps: 6, pixelFormat: .gray) { sink in
            for value in stride(from: 0, to: 240, by: 40) {
                try sink.append(Data(repeating: UInt8(value), count: 16 * 16), width: 16, height: 16)
            }
            XCTAssertEqual(sink.frameCount, 6)
        }
        let size = try XCTUnwrap(url.resourceValues(forKeys: [.fileSizeKey]).fileSize)
        XCTAssertGreaterThan(size, 0)
    }

    func testMissingEncoderFailsBeforeAnyFrame() throws {
        let url = try scratchURL("missing.mp4")
        XCTAssertThrowsError(
            try encodeMP4(ffmpeg: "lenia-no-such-ffmpeg", outputURL: url, fps: 6, pixelFormat: .gray) { _ in
                XCTFail("frames must not be rendered without an encoder")
            }
        ) { error in
            guard case VideoEncodingError.executableNotFound = error else {
                return XCTFail("unexpected error \(error)")
            }
        }
    }

    func testGeometryChangeAbortsAndRemovesPartialOutput() throws {
        let url = try scratchURL("partial.mp4")
        XCTAssertThrowsError(
            try encodeMP4(ffmpeg: "ffmpeg", outputURL: url, fps: 6, pixelFormat: .bgra) { sink in
                try sink.append(Data(count: 16 * 16 * 4), width: 16, height: 16)
                try sink.append(Data(count: 32 * 16 * 4), width: 32, height: 16)
            }
        ) { error in
            guard case VideoEncodingError.frameGeometryChanged = error else {
                return XCTFail("unexpected error \(error)")
            }
        }
        XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
    }

    func testEmptyBodyFailsLoudly() throws {
        let url = try scratchURL("empty.mp4")
        XCTAssertThrowsError(
            try encodeMP4(ffmpeg: "ffmpeg", outputURL: url, fps: 6, pixelFormat: .gray) { _ in }
        ) { error in
            guard case VideoEncodingError.noFrames = error else {
                return XCTFail("unexpected error \(error)")
            }
        }
    }
}
