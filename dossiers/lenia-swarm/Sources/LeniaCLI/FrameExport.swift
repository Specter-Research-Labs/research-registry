#if canImport(Metal)
import ArgumentParser
import CoreGraphics
import Foundation
import ImageIO
import LeniaCore
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

final class GrayscaleColorRenderer {
    private let renderer: LeniaMetalFieldRenderer
    private let renderMode: LeniaRenderMode
    // Flux encodes the frame-to-frame mass change, so it carries the previous
    // frame; frames must be rendered in trajectory order.
    private var previousGrayscale: [UInt8]?

    init(renderMode: LeniaRenderMode) throws {
        self.renderMode = renderMode
        renderer = try makeLeniaMetalFieldRenderer()
    }

    func render(width: Int, height: Int, grayscale: Data) throws -> CGImage {
        let outputSize = colorOutputSize(width: width, height: height, superSample: colorFrameSuperSample)
        guard renderMode == .flux else {
            return try renderLeniaSpectrumImage(
                grayscale: grayscale,
                width: width,
                height: height,
                renderer: renderer,
                renderMode: renderMode,
                outputSize: outputSize
            )
        }
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
        return image
    }
}

final class ColorFrameWriter {
    let outputDir: URL
    private(set) var error: Error?
    private let renderer: GrayscaleColorRenderer

    init(outputDir: URL, renderMode: LeniaRenderMode) throws {
        self.outputDir = outputDir
        renderer = try GrayscaleColorRenderer(renderMode: renderMode)
    }

    func write(step: Int, width: Int, height: Int, grayscale: Data) {
        guard error == nil else { return }
        let url = outputDir.appendingPathComponent(String(format: "frame_%06d.png", step))
        do {
            try writePNGImage(image: renderer.render(width: width, height: height, grayscale: grayscale), url: url)
        } catch {
            self.error = error
        }
    }
}

final class ChannelColorRenderer {
    private let renderer: LeniaMetalFieldRenderer
    private let renderMode: LeniaRenderMode

    init(renderMode: LeniaRenderMode) throws {
        self.renderMode = renderMode
        renderer = try makeLeniaMetalFieldRenderer()
    }

    func render(frame: CapturedStateFrame, scale: Float?) throws -> CGImage {
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
            outputSize: colorOutputSize(width: frame.width, height: frame.height, superSample: colorFrameSuperSample)
        ) else {
            throw FrameExportError.renderFailed
        }
        return image
    }
}

func renderEcologySpeciesImage(
    mass: Data,
    seed: [Float],
    width: Int,
    height: Int,
    renderer: LeniaMetalFieldRenderer
) throws -> CGImage {
    let cellCount = width * height
    guard mass.count == cellCount else {
        throw FrameExportError.invalidSize(expected: cellCount, actual: mass.count)
    }
    guard seed.count == cellCount * 2 else {
        throw FrameExportError.invalidSize(expected: cellCount * 2, actual: seed.count)
    }
    let massBytes = [UInt8](mass)
    var rgba = [Float](repeating: 0, count: cellCount * 4)
    for cell in 0..<cellCount {
        rgba[cell * 4 + 0] = Float(massBytes[cell]) / 255.0
        rgba[cell * 4 + 2] = seed[cell * 2 + 0]
        rgba[cell * 4 + 3] = seed[cell * 2 + 1]
    }
    guard let image = renderer.renderMultiChannelImage(
        rgbaValues: rgba,
        channels: 1,
        width: width,
        height: height,
        renderMode: .species,
        outputSize: colorOutputSize(width: width, height: height, superSample: colorFrameSuperSample)
    ) else {
        throw FrameExportError.renderFailed
    }
    return image
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
        let denominator = logToneDenominator(totals, explicitScale: explicitScale)
        var bytes = [UInt8](repeating: 0, count: width * height)
        for cell in 0..<(width * height) {
            bytes[cell] = UInt8(logToneMapped(totals[cell], denominator: denominator) * 255)
        }
        return Data(bytes)
    }
}

func captureReplayStateFrames(
    runtimeConfig: LeniaRuntimeConfig,
    seed: Int,
    initSeedOffset: Int,
    searchConfig: SearchConfig,
    frameBudget: Int,
    captureFlow: Bool = false,
    emptyCaptureMessage: String
) throws -> [CapturedStateFrame] {
    var grayscaleFrames: [Data] = []
    var stateFrames: [CapturedStateFrame] = []
    var flowByStep: [Int: (flow: [Float], growth: [Float])] = [:]
    grayscaleFrames.reserveCapacity(frameBudget + 8)
    stateFrames.reserveCapacity(frameBudget + 8)

    let capture = FrameCapture(
        stride: searchConfig.recordInterval,
        includeWarmup: false,
        sampleIndex: 0,
        handler: { _, _, _, data in
            grayscaleFrames.append(data)
        },
        stateHandler: { _, step, width, height, channels, values in
            stateFrames.append(CapturedStateFrame(
                step: step,
                width: width,
                height: height,
                channels: channels,
                values: values
            ))
        },
        flowHandler: captureFlow ? { step, _, _, flow, growth in
            flowByStep[step] = (flow, growth)
        } : nil
    )
    // Search centering hides locomotion; media must preserve world coordinates.
    let engine = SearchEngine(runtimeConfig: runtimeConfig, recenterAdditive: false)
    _ = engine.runBatch(
        seeds: [seed],
        initSeedOffset: initSeedOffset,
        searchConfig: searchConfig,
        frameCapture: capture
    )

    guard !stateFrames.isEmpty || !grayscaleFrames.isEmpty else {
        throw ValidationError(emptyCaptureMessage)
    }
    if !stateFrames.isEmpty {
        return Array(stateFrames.prefix(frameBudget)).map { frame in
            guard let fields = flowByStep[frame.step] else { return frame }
            var attached = frame
            attached.flow = fields.flow
            attached.growth = fields.growth
            return attached
        }
    }
    return Array(grayscaleFrames.prefix(frameBudget).enumerated().map { index, data in
        CapturedStateFrame(
            step: index,
            width: runtimeConfig.sx,
            height: runtimeConfig.sy,
            channels: 1,
            values: data.map { Float($0) / 255.0 }
        )
    })
}

enum FrameExportError: Error, LocalizedError {
    case invalidSize(expected: Int, actual: Int)
    case providerFailed
    case imageFailed
    case destinationFailed
    case writeFailed
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
    let massDenominator = logToneDenominator(totals, explicitScale: explicitScale)

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
        rgba[cell * 4 + 0] = logToneMapped(totals[cell], denominator: massDenominator)
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
    let denominator = logToneDenominator(frame.matterTotals(), explicitScale: explicitScale)
    var rgba = [Float](repeating: 0, count: cellCount * 4)
    for cell in 0..<cellCount {
        let base = cell * frame.channels
        let out = cell * 4
        for channel in 0..<frame.channels {
            rgba[out + channel] = logToneMapped(frame.values[base + channel], denominator: denominator)
        }
    }
    return rgba
}

// Shared robust log tone-map: a creature's mass spans orders of magnitude, so
// every color path maps it through log1p, normalized by a robust per-frame
// scale. These two helpers are the single definition of that mapping.
private func logToneDenominator(_ totals: [Float], explicitScale: Float?) -> Float {
    log1p(max(explicitScale ?? robustPositiveScale(totals), 1e-6))
}

private func logToneMapped(_ value: Float, denominator: Float) -> Float {
    guard value.isFinite else { return 0 }
    return max(0, min(1, log1p(max(0, value)) / denominator))
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
    case "species", "param", "parameters":
        return .species
    default:
        throw ValidationError("Invalid render mode '\(rawValue)'. Expected body, truth, magma, viridis, inferno, plasma, turbo, tol, flux, flowhue, flowlic, toldepth, or species.")
    }
}

func grayscaleImage(_ data: Data, width: Int, height: Int) throws -> CGImage {
    try bitmapImage(
        data,
        width: width,
        height: height,
        bytesPerPixel: 1,
        space: CGColorSpaceCreateDeviceGray(),
        bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.none.rawValue)
    )
}

func rgbaImage(_ data: Data, width: Int, height: Int) throws -> CGImage {
    try bitmapImage(
        data,
        width: width,
        height: height,
        bytesPerPixel: 4,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue)
    )
}

private func bitmapImage(
    _ data: Data,
    width: Int,
    height: Int,
    bytesPerPixel: Int,
    space: CGColorSpace,
    bitmapInfo: CGBitmapInfo
) throws -> CGImage {
    let expected = width * height * bytesPerPixel
    guard data.count == expected else {
        throw FrameExportError.invalidSize(expected: expected, actual: data.count)
    }
    guard let provider = CGDataProvider(data: data as CFData) else {
        throw FrameExportError.providerFailed
    }
    guard let image = CGImage(
        width: width,
        height: height,
        bitsPerComponent: 8,
        bitsPerPixel: 8 * bytesPerPixel,
        bytesPerRow: width * bytesPerPixel,
        space: space,
        bitmapInfo: bitmapInfo,
        provider: provider,
        decode: nil,
        shouldInterpolate: false,
        intent: .defaultIntent
    ) else {
        throw FrameExportError.imageFailed
    }
    return image
}

func writePNGFrame(data: Data, width: Int, height: Int, url: URL) throws {
    try writePNGImage(image: grayscaleImage(data, width: width, height: height), url: url)
}

func writePNGColorFrame(rgba: Data, width: Int, height: Int, url: URL) throws {
    try writePNGImage(image: rgbaImage(rgba, width: width, height: height), url: url)
}

// Renders are premultiplied, so the encoder dropping alpha composites them over
// black rather than showing straight color at soft, low-alpha edges.
func bgraBytes(_ image: CGImage) throws -> Data {
    let bytesPerRow = image.width * 4
    var data = Data(count: bytesPerRow * image.height)
    let drawn = data.withUnsafeMutableBytes { raw -> Bool in
        guard let context = CGContext(
            data: raw.baseAddress,
            width: image.width,
            height: image.height,
            bitsPerComponent: 8,
            bytesPerRow: bytesPerRow,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGBitmapInfo.byteOrder32Little.rawValue | CGImageAlphaInfo.premultipliedFirst.rawValue
        ) else {
            return false
        }
        context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
        return true
    }
    guard drawn else {
        throw FrameExportError.imageFailed
    }
    return data
}

struct MediaOutputOptions {
    let fps: Int
    let ffmpeg: String
    let exportFrames: Bool
}

struct SpecimenFrame {
    let step: Int
    let truth: Data
    let truthWidth: Int
    let truthHeight: Int
    let color: CGImage
}

struct ContactSheetRow {
    let color: [CGImage]
    let truth: [CGImage]
}

struct SpecimenMedia {
    let videoURL: URL
    let framesURL: URL?
    let colorFramesURL: URL?
    let contactRow: ContactSheetRow
}

// The single path from a trajectory to persistent media. The specimen
// directory is replaced so no stale frames survive a rerun. Every frame streams
// to ffmpeg; per-frame PNGs (exact grayscale truth in frames/, the color render
// with alpha in frames_color/) are written only when exportFrames is set.
// Only the first, middle and last frames are retained for contact sheets.
func writeSpecimenMedia(
    directory: URL,
    videoName: String,
    frameCount: Int,
    output: MediaOutputOptions,
    frame render: (Int) throws -> SpecimenFrame
) throws -> SpecimenMedia {
    guard frameCount > 0 else {
        throw ValidationError("No frames were captured for \(directory.path).")
    }
    let framesURL = output.exportFrames ? directory.appendingPathComponent("frames", isDirectory: true) : nil
    let colorFramesURL = output.exportFrames ? directory.appendingPathComponent("frames_color", isDirectory: true) : nil
    if FileManager.default.fileExists(atPath: directory.path) {
        try FileManager.default.removeItem(at: directory)
    }
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    for url in [framesURL, colorFramesURL].compactMap({ $0 }) {
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    }
    var sampleIndices: [Int] = []
    for index in [0, frameCount / 2, frameCount - 1] where !sampleIndices.contains(index) {
        sampleIndices.append(index)
    }
    var colorSamples: [CGImage] = []
    var truthSamples: [CGImage] = []
    let videoURL = directory.appendingPathComponent(videoName)
    try encodeMP4(ffmpeg: output.ffmpeg, outputURL: videoURL, fps: output.fps, pixelFormat: .bgra) { sink in
        for index in 0..<frameCount {
            let frame = try render(index)
            try sink.append(bgraBytes(frame.color), width: frame.color.width, height: frame.color.height)
            let isSample = sampleIndices.contains(index)
            guard isSample || output.exportFrames else { continue }
            let truth = try grayscaleImage(frame.truth, width: frame.truthWidth, height: frame.truthHeight)
            if isSample {
                colorSamples.append(frame.color)
                truthSamples.append(truth)
            }
            if let framesURL, let colorFramesURL {
                let name = String(format: "frame_%06d.png", frame.step)
                try writePNGImage(image: truth, url: framesURL.appendingPathComponent(name))
                try writePNGImage(image: frame.color, url: colorFramesURL.appendingPathComponent(name))
            }
        }
    }
    return SpecimenMedia(
        videoURL: videoURL,
        framesURL: framesURL,
        colorFramesURL: colorFramesURL,
        contactRow: ContactSheetRow(color: colorSamples, truth: truthSamples)
    )
}

func writeMediaContactSheets(rows: [ContactSheetRow], outputURL: URL) throws -> [URL] {
    let colorURL = outputURL.appendingPathComponent("contact_sheet.png")
    try writeContactSheet(
        rows: rows.map { [$0.color] },
        tileSize: 160,
        gap: 12,
        groupGap: 12,
        url: colorURL
    )
    let reviewURL = outputURL.appendingPathComponent("contact_sheet_review.png")
    try writeContactSheet(
        rows: rows.map { [$0.color, $0.truth] },
        tileSize: 128,
        gap: 10,
        groupGap: 18,
        url: reviewURL
    )
    return [colorURL, reviewURL]
}

// Each row holds groups of up to three samples (first, middle, last); a group
// with fewer samples repeats its last image so every row has the same width.
private func writeContactSheet(
    rows: [[[CGImage]]],
    tileSize: Int,
    gap: Int,
    groupGap: Int,
    url: URL
) throws {
    guard let groupCount = rows.first?.count, groupCount > 0,
          rows.allSatisfy({ $0.count == groupCount && $0.allSatisfy { !$0.isEmpty } })
    else {
        preconditionFailure("contact sheet rows need the same non-empty groups")
    }
    let margin = 16
    let columns = groupCount * 3
    let width = margin * 2 + columns * tileSize + (columns - groupCount) * gap + (groupCount - 1) * groupGap
    let height = margin * 2 + rows.count * tileSize + max(rows.count - 1, 0) * gap
    guard let context = CGContext(
        data: nil,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: width * 4,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
    ) else {
        throw FrameExportError.imageFailed
    }
    context.setFillColor(red: 0.015, green: 0.018, blue: 0.024, alpha: 1)
    context.fill(CGRect(x: 0, y: 0, width: width, height: height))
    context.interpolationQuality = .high
    for (rowIndex, groups) in rows.enumerated() {
        let y = margin + rowIndex * (tileSize + gap)
        for column in 0..<columns {
            let groupIndex = column / 3
            let images = groups[groupIndex]
            let image = images[min(column % 3, images.count - 1)]
            let x = margin + column * (tileSize + gap) + groupIndex * (groupGap - gap)
            context.setFillColor(red: 0.05, green: 0.055, blue: 0.07, alpha: 1)
            context.fill(CGRect(x: x, y: y, width: tileSize, height: tileSize))
            let scale = min(Double(tileSize) / Double(image.width), Double(tileSize) / Double(image.height))
            let drawWidth = Double(image.width) * scale
            let drawHeight = Double(image.height) * scale
            context.draw(image, in: CGRect(
                x: Double(x) + (Double(tileSize) - drawWidth) * 0.5,
                y: Double(y) + (Double(tileSize) - drawHeight) * 0.5,
                width: drawWidth,
                height: drawHeight
            ))
        }
    }
    guard let sheet = context.makeImage() else {
        throw FrameExportError.imageFailed
    }
    try writePNGImage(image: sheet, url: url)
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

func resolveFramesDir(_ framesDir: String?, defaultName: String, runDir: URL) -> URL {
    let trimmed = framesDir?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    guard !trimmed.isEmpty else {
        return runDir.appendingPathComponent(defaultName, isDirectory: true)
    }
    let expanded = (trimmed as NSString).expandingTildeInPath
    if expanded.hasPrefix("/") {
        return URL(fileURLWithPath: expanded, isDirectory: true)
    }
    return runDir.appendingPathComponent(expanded, isDirectory: true)
}
#endif
