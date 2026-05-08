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
    private let renderMode: LeniaRenderMode

    init(outputDir: URL, renderMode: LeniaRenderMode = .body) {
        self.outputDir = outputDir
        self.renderMode = renderMode
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
                renderer: renderer,
                renderMode: renderMode
            )
        } catch {
            self.error = error
        }
    }
}

struct CapturedStateFrame {
    let step: Int
    let width: Int
    let height: Int
    let channels: Int
    let values: [Float]

    func matterTotals() -> [Float] {
        var totals = [Float](repeating: 0, count: width * height)
        for cell in 0..<(width * height) {
            let base = cell * channels
            var total: Float = 0
            for channel in 0..<channels {
                let value = values[base + channel]
                if value.isFinite {
                    total += max(0, value)
                }
            }
            totals[cell] = total
        }
        return totals
    }

    func matterBytes(scale explicitScale: Float? = nil) -> Data {
        let totals = matterTotals()
        let scale = max(explicitScale ?? robustPositiveScale(totals), 1e-6)
        let denominator = log1p(scale)
        var bytes = [UInt8](repeating: 0, count: width * height)
        for cell in 0..<(width * height) {
            let value = max(0, totals[cell])
            let normalized = max(0, min(1, log1p(value) / denominator))
            bytes[cell] = UInt8(normalized * 255)
        }
        return Data(bytes)
    }

    func occupancyMaskBytes(threshold: Float = 0.05) -> Data {
        let totals = matterTotals()
        var bytes = [UInt8](repeating: 0, count: width * height)
        for cell in 0..<(width * height) {
            bytes[cell] = totals[cell] >= threshold ? 255 : 0
        }
        return Data(bytes)
    }

    func supportMaskBytes(scale: Float? = nil) -> Data {
        let totals = matterTotals()
        let supportThreshold = max(0.005, 0.015 * max(scale ?? robustPositiveScale(totals), 1e-6))
        var bytes = [UInt8](repeating: 0, count: width * height)
        for cell in 0..<(width * height) {
            bytes[cell] = totals[cell] >= supportThreshold ? 255 : 0
        }
        return Data(bytes)
    }
}

final class ChannelAwareColorFrameWriter {
    let outputDir: URL
    private(set) var error: Error?
    private let fallbackWriter: ColorFrameWriter

    init(outputDir: URL) {
        self.outputDir = outputDir
        self.fallbackWriter = ColorFrameWriter(outputDir: outputDir)
    }

    func write(frame: CapturedStateFrame, scale: Float? = nil) {
        guard error == nil else { return }
        let name = String(format: "frame_%06d.png", frame.step)
        let url = outputDir.appendingPathComponent(name)
        do {
            if frame.channels <= 1 {
                fallbackWriter.write(
                    step: frame.step,
                    width: frame.width,
                    height: frame.height,
                    grayscale: frame.matterBytes(scale: scale)
                )
                if let error = fallbackWriter.error {
                    throw error
                }
            } else {
                try writePNGColorFrame(
                    rgba: channelAwareRGBA(frame: frame, scale: scale),
                    width: frame.width,
                    height: frame.height,
                    url: url
                )
            }
        } catch {
            self.error = error
        }
    }
}

final class ChannelDiagnosticFrameWriter {
    let outputDir: URL
    private(set) var error: Error?

    init(outputDir: URL) {
        self.outputDir = outputDir
    }

    func write(frame: CapturedStateFrame, scale: Float? = nil) {
        guard error == nil else { return }
        let name = String(format: "frame_%06d.png", frame.step)
        let url = outputDir.appendingPathComponent(name)
        do {
            try writePNGColorFrame(
                rgba: channelDiagnosticRGBA(frame: frame, scale: scale),
                width: frame.width,
                height: frame.height,
                url: url
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

func channelAwareRGBA(frame: CapturedStateFrame, scale explicitScale: Float? = nil) -> Data {
    let cellCount = frame.width * frame.height
    var totals = [Float](repeating: 0, count: cellCount)
    totals.withUnsafeMutableBufferPointer { totalsPtr in
        for cell in 0..<cellCount {
            let base = cell * frame.channels
            var total: Float = 0
            for channel in 0..<frame.channels {
                let value = frame.values[base + channel]
                if value.isFinite {
                    total += max(0, value)
                }
            }
            totalsPtr[cell] = total
        }
    }

    let scale = max(explicitScale ?? robustPositiveScale(totals), 1e-6)
    let logDenominator = log1p(scale)
    let palette: [(Float, Float, Float)] = [
        (0.18, 0.92, 0.42),
        (1.00, 0.25, 0.16),
        (0.18, 0.48, 1.00),
        (0.95, 0.82, 0.20),
        (0.82, 0.35, 1.00),
        (0.10, 0.85, 0.86),
    ]
    var rgba = [UInt8](repeating: 0, count: cellCount * 4)
    for cell in 0..<cellCount {
        rgba[cell * 4 + 3] = 255
    }

    for cell in 0..<cellCount {
        let total = totals[cell]
        guard total > 1e-9 else { continue }
        let base = cell * frame.channels
        var red: Float = 0
        var green: Float = 0
        var blue: Float = 0
        for channel in 0..<frame.channels {
            let value = frame.values[base + channel]
            let positive = value.isFinite ? max(0, value) : 0
            guard positive > 0 else { continue }
            let weight = positive / total
            let color = palette[channel % palette.count]
            red += weight * color.0
            green += weight * color.1
            blue += weight * color.2
        }
        let intensity = max(0, min(1, log1p(total) / logDenominator))
        let lifted = pow(intensity, 0.72)
        let out = cell * 4
        rgba[out + 0] = UInt8(max(0, min(1, red * lifted)) * 255)
        rgba[out + 1] = UInt8(max(0, min(1, green * lifted)) * 255)
        rgba[out + 2] = UInt8(max(0, min(1, blue * lifted)) * 255)
    }
    return Data(rgba)
}

func channelDiagnosticRGBA(frame: CapturedStateFrame, scale explicitScale: Float? = nil) -> Data {
    let cellCount = frame.width * frame.height
    let scale = max(explicitScale ?? robustPositiveScale(frame.matterTotals()), 1e-6)
    let logDenominator = log1p(scale)
    var rgba = [UInt8](repeating: 0, count: cellCount * 4)
    for cell in 0..<cellCount {
        let base = cell * frame.channels
        let red: Float
        let green: Float
        let blue: Float
        if frame.channels == 1 {
            let value = normalizedChannelValue(frame.values[base], logDenominator: logDenominator)
            red = value
            green = value
            blue = value
        } else if frame.channels == 2 {
            let first = normalizedChannelValue(frame.values[base], logDenominator: logDenominator)
            let second = normalizedChannelValue(frame.values[base + 1], logDenominator: logDenominator)
            red = first
            green = first
            blue = second
        } else {
            red = normalizedChannelValue(frame.values[base], logDenominator: logDenominator)
            green = normalizedChannelValue(frame.values[base + 1], logDenominator: logDenominator)
            blue = normalizedChannelValue(frame.values[base + 2], logDenominator: logDenominator)
        }
        let out = cell * 4
        rgba[out + 0] = UInt8(max(0, min(1, red)) * 255)
        rgba[out + 1] = UInt8(max(0, min(1, green)) * 255)
        rgba[out + 2] = UInt8(max(0, min(1, blue)) * 255)
        rgba[out + 3] = 255
    }
    return Data(rgba)
}

private func normalizedChannelValue(_ value: Float, logDenominator: Float) -> Float {
    guard value.isFinite else { return 0 }
    return max(0, min(1, log1p(max(0, value)) / logDenominator))
}

func robustMatterScale(_ frames: [CapturedStateFrame]) -> Float {
    frames.reduce(Float(1)) { scale, frame in
        max(scale, robustPositiveScale(frame.matterTotals()))
    }
}

func robustPositiveScale(_ values: [Float]) -> Float {
    let positives = values.filter { $0.isFinite && $0 > 0 }.sorted()
    guard !positives.isEmpty else { return 1 }
    let index = min(positives.count - 1, max(0, Int(Double(positives.count - 1) * 0.995)))
    return positives[index]
}

func parseLeniaRenderMode(_ rawValue: String) throws -> LeniaRenderMode {
    let normalized = rawValue
        .trimmingCharacters(in: .whitespacesAndNewlines)
        .lowercased()
        .replacingOccurrences(of: "_", with: "-")
        .replacingOccurrences(of: " ", with: "-")
    switch normalized {
    case "body", "mass", "density", "soft-body":
        return .body
    case "truth", "raw", "gray", "grayscale":
        return .truth
    case "magma", "smooth-magma":
        return .smoothMagma
    case "viridis":
        return .viridis
    case "inferno":
        return .inferno
    case "plasma":
        return .plasma
    default:
        throw ValidationError("Invalid render mode '\(rawValue)'. Expected body, truth, magma, viridis, inferno, or plasma.")
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
    renderMode: LeniaRenderMode = .body,
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
    renderMode: LeniaRenderMode = .body,
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
