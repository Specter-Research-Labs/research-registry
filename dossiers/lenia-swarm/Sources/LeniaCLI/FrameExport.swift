import ArgumentParser
import CoreGraphics
import Foundation
import ImageIO
import Metal
import UniformTypeIdentifiers
import LeniaVisuals

final class FrameWriter {
    let outputDir: URL
    private(set) var error: Error?

    init(outputDir: URL) {
        self.outputDir = outputDir
    }

    func write(step: Int, width: Int, height: Int, data: Data) {
        guard error == nil else { return }
        let name = String(format: "frame_%06d.png", step)
        let url = outputDir.appendingPathComponent(name)
        do {
            try writePNGFrame(data: data, width: width, height: height, url: url)
        } catch {
            self.error = error
        }
    }
}

final class ColorFrameWriter {
    let outputDir: URL
    private(set) var error: Error?
    private let renderer: LeniaMetalFieldRenderer

    init(outputDir: URL) {
        self.outputDir = outputDir
        guard let device = MTLCreateSystemDefaultDevice() else {
            preconditionFailure("Lenia color frame export requires a Metal device")
        }
        renderer = LeniaMetalFieldRenderer(device: device)
    }

    func write(step: Int, width: Int, height: Int, grayscale: Data) {
        guard error == nil else { return }
        let name = String(format: "frame_%06d.png", step)
        let url = outputDir.appendingPathComponent(name)
        do {
            try writeLeniaSpectrumPNG(
                grayscale: grayscale,
                width: width,
                height: height,
                url: url,
                renderer: renderer
            )
        } catch {
            self.error = error
        }
    }
}

enum FrameExportError: Error, LocalizedError {
    case invalidSize(expected: Int, actual: Int)
    case providerFailed
    case imageFailed
    case destinationFailed
    case writeFailed
    case ffmpegFailed(String)
    case metalDeviceUnavailable
    case renderFailed

    var errorDescription: String? {
        switch self {
        case .invalidSize(let expected, let actual):
            return "Frame data size mismatch: expected \(expected), got \(actual)"
        case .providerFailed:
            return "Failed to create CGDataProvider"
        case .imageFailed:
            return "Failed to create CGImage"
        case .destinationFailed:
            return "Failed to create PNG destination"
        case .writeFailed:
            return "Failed to finalize PNG write"
        case .ffmpegFailed(let message):
            return "ffmpeg failed: \(message)"
        case .metalDeviceUnavailable:
            return "Metal device unavailable for Lenia color export"
        case .renderFailed:
            return "Failed to render Lenia color frame"
        }
    }
}

func writePNGFrame(data: Data, width: Int, height: Int, url: URL) throws {
    let expected = width * height
    if data.count != expected {
        throw FrameExportError.invalidSize(expected: expected, actual: data.count)
    }
    guard let provider = CGDataProvider(data: data as CFData) else {
        throw FrameExportError.providerFailed
    }
    let colorSpace = CGColorSpaceCreateDeviceGray()
    let bitmapInfo = CGBitmapInfo(rawValue: CGImageAlphaInfo.none.rawValue)
    guard let image = CGImage(
        width: width,
        height: height,
        bitsPerComponent: 8,
        bitsPerPixel: 8,
        bytesPerRow: width,
        space: colorSpace,
        bitmapInfo: bitmapInfo,
        provider: provider,
        decode: nil,
        shouldInterpolate: false,
        intent: .defaultIntent
    ) else {
        throw FrameExportError.imageFailed
    }
    guard let destination = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil) else {
        throw FrameExportError.destinationFailed
    }
    CGImageDestinationAddImage(destination, image, nil)
    guard CGImageDestinationFinalize(destination) else {
        throw FrameExportError.writeFailed
    }
}

func writePNGColorFrame(rgba: Data, width: Int, height: Int, url: URL) throws {
    let expected = width * height * 4
    if rgba.count != expected {
        throw FrameExportError.invalidSize(expected: expected, actual: rgba.count)
    }
    guard let provider = CGDataProvider(data: rgba as CFData) else {
        throw FrameExportError.providerFailed
    }
    let colorSpace = CGColorSpaceCreateDeviceRGB()
    let bitmapInfo = CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue)
    guard let image = CGImage(
        width: width,
        height: height,
        bitsPerComponent: 8,
        bitsPerPixel: 32,
        bytesPerRow: width * 4,
        space: colorSpace,
        bitmapInfo: bitmapInfo,
        provider: provider,
        decode: nil,
        shouldInterpolate: false,
        intent: .defaultIntent
    ) else {
        throw FrameExportError.imageFailed
    }
    guard let destination = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil) else {
        throw FrameExportError.destinationFailed
    }
    CGImageDestinationAddImage(destination, image, nil)
    guard CGImageDestinationFinalize(destination) else {
        throw FrameExportError.writeFailed
    }
}

func writePNGImage(image: CGImage, url: URL) throws {
    guard let destination = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil) else {
        throw FrameExportError.destinationFailed
    }
    CGImageDestinationAddImage(destination, image, nil)
    guard CGImageDestinationFinalize(destination) else {
        throw FrameExportError.writeFailed
    }
}

func makeLeniaMetalFieldRenderer() throws -> LeniaMetalFieldRenderer {
    guard let device = MTLCreateSystemDefaultDevice() else {
        throw FrameExportError.metalDeviceUnavailable
    }
    return LeniaMetalFieldRenderer(device: device)
}

func renderLeniaSpectrumImage(
    grayscale: Data,
    width: Int,
    height: Int,
    renderer: LeniaMetalFieldRenderer,
    renderMode: LeniaRenderMode = .smoothMagma,
    outputSize: CGSize? = nil
) throws -> CGImage {
    let expected = width * height
    if grayscale.count != expected {
        throw FrameExportError.invalidSize(expected: expected, actual: grayscale.count)
    }

    let frame = LeniaFieldFrame(
        step: 0,
        width: width,
        height: height,
        bytes: grayscale
    )
    let targetSize = outputSize ?? CGSize(width: width, height: height)
    guard let image = renderer.renderImage(frame: frame, renderMode: renderMode, outputSize: targetSize) else {
        throw FrameExportError.renderFailed
    }
    return image
}

func writeLeniaSpectrumPNG(
    grayscale: Data,
    width: Int,
    height: Int,
    url: URL,
    renderer: LeniaMetalFieldRenderer,
    renderMode: LeniaRenderMode = .smoothMagma,
    outputSize: CGSize? = nil
) throws {
    let image = try renderLeniaSpectrumImage(
        grayscale: grayscale,
        width: width,
        height: height,
        renderer: renderer,
        renderMode: renderMode,
        outputSize: outputSize
    )
    try writePNGImage(image: image, url: url)
}

func resolveFramesDir(framesDir: String?, runDir: URL) -> URL {
    guard let framesDir else {
        return runDir.appendingPathComponent("frames", isDirectory: true)
    }
    let trimmed = framesDir.trimmingCharacters(in: .whitespacesAndNewlines)
    if trimmed.isEmpty {
        return runDir.appendingPathComponent("frames", isDirectory: true)
    }
    let expanded = (trimmed as NSString).expandingTildeInPath
    if expanded.hasPrefix("/") {
        return URL(fileURLWithPath: expanded, isDirectory: true)
    }
    return runDir.appendingPathComponent(expanded, isDirectory: true)
}

func resolveFramesColorDir(framesDir: String?, runDir: URL) -> URL {
    guard let framesDir else {
        return runDir.appendingPathComponent("frames_color", isDirectory: true)
    }
    let trimmed = framesDir.trimmingCharacters(in: .whitespacesAndNewlines)
    if trimmed.isEmpty {
        return runDir.appendingPathComponent("frames_color", isDirectory: true)
    }
    let expanded = (trimmed as NSString).expandingTildeInPath
    if expanded.hasPrefix("/") {
        return URL(fileURLWithPath: expanded, isDirectory: true)
    }
    return runDir.appendingPathComponent(expanded, isDirectory: true)
}

func encodeMP4FromPNGSequence(
    framesDir: URL,
    outputURL: URL,
    fps: Int,
    ffmpeg: String,
    globPattern: String = "frame_*.png"
) throws {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
    process.arguments = [
        ffmpeg,
        "-v", "error",
        "-nostdin",
        "-y",
        "-framerate", String(fps),
        "-pattern_type", "glob",
        "-i", globPattern,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        outputURL.path
    ]
    process.currentDirectoryURL = framesDir

    let stderr = Pipe()
    process.standardError = stderr
    process.standardOutput = Pipe()

    try process.run()
    process.waitUntilExit()
    if process.terminationStatus != 0 {
        let data = stderr.fileHandleForReading.readDataToEndOfFile()
        let message = String(data: data, encoding: .utf8) ?? "Unknown ffmpeg error"
        throw FrameExportError.ffmpegFailed(message)
    }
    let values = try outputURL.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey])
    guard values.isRegularFile == true, (values.fileSize ?? 0) > 0 else {
        throw FrameExportError.ffmpegFailed("encoder did not create a non-empty output at \(outputURL.path)")
    }
}
