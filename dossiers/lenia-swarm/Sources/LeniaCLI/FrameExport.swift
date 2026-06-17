import ArgumentParser
import CoreGraphics
import Foundation
import ImageIO
import Metal
import UniformTypeIdentifiers
import LeniaVisuals

struct AutoFrameBox {
    let x0: Int
    let y0: Int
    let side: Int
}

// Union bounding box of occupied cells across a whole replay, squared and
// padded. A single stable box (not per-frame) keeps the crop from jittering as
// the creature breathes. Returns nil when nothing crosses the threshold.
func autoFrameBox(
    grayscaleFrames: [Data],
    width: Int,
    height: Int,
    threshold: UInt8 = 12,
    paddingFraction: Float = 0.14
) -> AutoFrameBox? {
    var minX = width, minY = height, maxX = -1, maxY = -1
    for frame in grayscaleFrames {
        frame.withUnsafeBytes { raw in
            let p = raw.bindMemory(to: UInt8.self)
            for y in 0..<height {
                let row = y * width
                for x in 0..<width where p[row + x] > threshold {
                    if x < minX { minX = x }
                    if x > maxX { maxX = x }
                    if y < minY { minY = y }
                    if y > maxY { maxY = y }
                }
            }
        }
    }
    guard maxX >= minX, maxY >= minY else { return nil }

    let boxSide = max(maxX - minX + 1, maxY - minY + 1)
    let padded = boxSide + 2 * Int((Float(boxSide) * paddingFraction).rounded())
    let side = min(padded, min(width, height))
    let cx = (minX + maxX + 1) / 2
    let cy = (minY + maxY + 1) / 2
    let x0 = min(max(cx - side / 2, 0), width - side)
    let y0 = min(max(cy - side / 2, 0), height - side)
    return AutoFrameBox(x0: x0, y0: y0, side: side)
}

// Crop a captured state (and its optional flow/growth fields) to the box, so
// the flow/pigment paths can frame the creature the way the grayscale path does.
func cropCapturedFrame(_ frame: CapturedStateFrame, box: AutoFrameBox) -> CapturedStateFrame {
    let w = frame.width
    let side = box.side
    let channels = frame.channels
    var values = [Float](repeating: 0, count: side * side * channels)
    var flow: [Float]? = frame.flow != nil ? [Float](repeating: 0, count: side * side * 2) : nil
    var growth: [Float]? = frame.growth != nil ? [Float](repeating: 0, count: side * side) : nil
    for y in 0..<side {
        for x in 0..<side {
            let srcCell = (box.y0 + y) * w + (box.x0 + x)
            let dstCell = y * side + x
            for c in 0..<channels {
                values[dstCell * channels + c] = frame.values[srcCell * channels + c]
            }
            if let src = frame.flow {
                flow?[dstCell * 2 + 0] = src[srcCell * 2 + 0]
                flow?[dstCell * 2 + 1] = src[srcCell * 2 + 1]
            }
            if let src = frame.growth {
                growth?[dstCell] = src[srcCell]
            }
        }
    }
    return CapturedStateFrame(step: frame.step, width: side, height: side, channels: channels, values: values, flow: flow, growth: growth)
}

func cropGrayscale(_ frame: Data, width: Int, box: AutoFrameBox) -> Data {
    var out = [UInt8](repeating: 0, count: box.side * box.side)
    frame.withUnsafeBytes { raw in
        let p = raw.bindMemory(to: UInt8.self)
        for y in 0..<box.side {
            let srcRow = (box.y0 + y) * width + box.x0
            let dstRow = y * box.side
            for x in 0..<box.side {
                out[dstRow + x] = p[srcRow + x]
            }
        }
    }
    return Data(out)
}

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

// Color frames render through the lit Metal kernel at superSample times the
// grid. The field is band-limited, so Catmull-Rom reconstruction at higher
// resolution yields real smoothness rather than nearest-neighbor blockiness.
let colorFrameSuperSample = 2

// Floor on the rendered color dimension. Auto-framed crops can be small in grid
// cells; rendering them to at least this many pixels keeps hero frames crisp.
let colorFrameTargetPx = 512

func colorOutputSize(width: Int, height: Int, superSample: Int) -> CGSize {
    let w = max(width * superSample, colorFrameTargetPx)
    let h = max(height * superSample, colorFrameTargetPx)
    return CGSize(width: w, height: h)
}

final class ColorFrameWriter {
    let outputDir: URL
    private(set) var error: Error?
    private let renderer: LeniaMetalFieldRenderer
    private let renderMode: LeniaRenderMode
    private let superSample: Int
    private var previousGrayscale: [UInt8]?

    init(outputDir: URL, renderMode: LeniaRenderMode = .body, superSample: Int = colorFrameSuperSample) {
        self.outputDir = outputDir
        self.renderMode = renderMode
        self.superSample = max(1, superSample)
        guard let device = MTLCreateSystemDefaultDevice() else {
            preconditionFailure("Lenia color frame export requires a Metal device")
        }
        renderer = LeniaMetalFieldRenderer(device: device)
    }

    func write(step: Int, width: Int, height: Int, grayscale: Data) {
        guard error == nil else { return }
        let name = String(format: "frame_%06d.png", step)
        let url = outputDir.appendingPathComponent(name)
        let outputSize = colorOutputSize(width: width, height: height, superSample: superSample)
        do {
            if renderMode == .flux {
                try writeFluxFrame(grayscale: grayscale, width: width, height: height, url: url, outputSize: outputSize)
            } else {
                try writeLeniaSpectrumPNG(
                    grayscale: grayscale,
                    width: width,
                    height: height,
                    url: url,
                    renderer: renderer,
                    renderMode: renderMode,
                    outputSize: outputSize
                )
            }
        } catch {
            self.error = error
        }
    }

    private func writeFluxFrame(grayscale: Data, width: Int, height: Int, url: URL, outputSize: CGSize) throws {
        let cellCount = width * height
        let current = [UInt8](grayscale)
        var rgba = [Float](repeating: 0, count: cellCount * 4)
        for cell in 0..<cellCount {
            let mass = Float(current[cell]) / 255.0
            let previous = previousGrayscale.map { Float($0[cell]) / 255.0 } ?? mass
            rgba[cell * 4 + 0] = mass
            rgba[cell * 4 + 1] = mass - previous
        }
        previousGrayscale = current
        guard let image = renderer.renderMultiChannelImage(
            rgbaValues: rgba,
            channels: 1,
            width: width,
            height: height,
            renderMode: .flux,
            outputSize: outputSize
        ) else {
            throw FrameExportError.renderFailed
        }
        try writePNGImage(image: image, url: url)
    }
}

struct CapturedStateFrame {
    let step: Int
    let width: Int
    let height: Int
    let channels: Int
    let values: [Float]
    // Optional fields captured for flow visualization. flow is row-major with 2
    // components [dy, dx] per cell; growth is a signed scalar per cell.
    var flow: [Float]? = nil
    var growth: [Float]? = nil

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
    private let renderer: LeniaMetalFieldRenderer
    private let renderMode: LeniaRenderMode
    private let superSample: Int

    init(outputDir: URL, renderMode: LeniaRenderMode = .body, superSample: Int = colorFrameSuperSample) {
        self.outputDir = outputDir
        self.renderMode = renderMode
        self.superSample = max(1, superSample)
        guard let device = MTLCreateSystemDefaultDevice() else {
            preconditionFailure("Lenia color frame export requires a Metal device")
        }
        renderer = LeniaMetalFieldRenderer(device: device)
    }

    func write(frame: CapturedStateFrame, scale: Float? = nil) {
        guard error == nil else { return }
        let name = String(format: "frame_%06d.png", frame.step)
        let url = outputDir.appendingPathComponent(name)
        do {
            let rgba: [Float]
            let channels: Int
            if renderMode == .flowHue || renderMode == .flowLIC || renderMode == .flux {
                rgba = normalizedFlowFloats(frame: frame, scale: scale)
                channels = 1
            } else {
                rgba = normalizedChannelFloats(frame: frame, scale: scale)
                channels = frame.channels
            }
            guard let image = renderer.renderMultiChannelImage(
                rgbaValues: rgba,
                channels: channels,
                width: frame.width,
                height: frame.height,
                renderMode: renderMode,
                outputSize: colorOutputSize(width: frame.width, height: frame.height, superSample: superSample)
            ) else {
                throw FrameExportError.renderFailed
            }
            try writePNGImage(image: image, url: url)
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

// Pack mass + signed growth + flow vector into RGBA for the flow/flux modes:
// r = log-normalized total mass (drives lighting), g = signed growth scaled to
// ~[-1,1], b/a = flow components (dx, dy) scaled by a robust speed so the
// shader can read direction and magnitude.
func normalizedFlowFloats(frame: CapturedStateFrame, scale explicitScale: Float? = nil) -> [Float] {
    guard let flow = frame.flow, let growth = frame.growth else {
        preconditionFailure("Flow/flux render requires captured flow and growth fields; re-run media with --render-mode flowhue")
    }
    let cellCount = frame.width * frame.height
    let totals = frame.matterTotals()
    let massScale = max(explicitScale ?? robustPositiveScale(totals), 1e-6)
    let massDenominator = log1p(massScale)

    var magnitudes = [Float](repeating: 0, count: cellCount)
    for cell in 0..<cellCount {
        let dy = flow[cell * 2 + 0]
        let dx = flow[cell * 2 + 1]
        magnitudes[cell] = (dx * dx + dy * dy).squareRoot()
    }
    let flowScale = max(robustPositiveScale(magnitudes), 1e-6)
    let growthScale = max(robustPositiveScale(growth.map { abs($0) }), 1e-6)

    var rgba = [Float](repeating: 0, count: cellCount * 4)
    for cell in 0..<cellCount {
        rgba[cell * 4 + 0] = max(0, min(1, log1p(max(0, totals[cell])) / massDenominator))
        rgba[cell * 4 + 1] = max(-1, min(1, growth[cell] / growthScale))
        rgba[cell * 4 + 2] = max(-1, min(1, flow[cell * 2 + 1] / flowScale))
        rgba[cell * 4 + 3] = max(-1, min(1, flow[cell * 2 + 0] / flowScale))
    }
    return rgba
}

// Pack per-channel field values into a normalized RGBA float buffer for the
// Metal colorizer: each channel is log-normalized by the same robust scale, so
// the kernel composites channels as pigments and lights the total mass.
func normalizedChannelFloats(frame: CapturedStateFrame, scale explicitScale: Float? = nil) -> [Float] {
    precondition(frame.channels >= 1 && frame.channels <= 4, "Channel export supports 1...4 channels, got \(frame.channels)")
    let cellCount = frame.width * frame.height
    let scale = max(explicitScale ?? robustPositiveScale(frame.matterTotals()), 1e-6)
    let logDenominator = log1p(scale)
    var rgba = [Float](repeating: 0, count: cellCount * 4)
    for cell in 0..<cellCount {
        let base = cell * frame.channels
        let out = cell * 4
        for channel in 0..<frame.channels {
            let value = frame.values[base + channel]
            let positive = value.isFinite ? max(0, value) : 0
            rgba[out + channel] = max(0, min(1, log1p(positive) / logDenominator))
        }
    }
    return rgba
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
    case "turbo":
        return .turbo
    case "tol", "tol-rainbow", "rainbow":
        return .tol
    case "flux":
        return .flux
    case "flow", "flowhue", "flow-hue":
        return .flowHue
    case "flowlic", "flow-lines", "lic":
        return .flowLIC
    case "toldepth", "tol-depth", "depth":
        return .tolDepth
    default:
        throw ValidationError("Invalid render mode '\(rawValue)'. Expected body, truth, magma, viridis, inferno, plasma, turbo, tol, flux, flowhue, flowlic, or toldepth.")
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
