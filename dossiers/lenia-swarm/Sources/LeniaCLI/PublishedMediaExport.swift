import ArgumentParser
import Foundation
import LeniaCore

func captureReplayFrames(
    runtimeConfig: LeniaRuntimeConfig,
    seed: Int,
    parsedSearch: ParsedSearchConfig,
    frameBudget: Int
) throws -> [Data] {
    try LeniaMetalLibrarySupport.ensureAvailable()

    let targetFrames = max(frameBudget, 1)
    let warmupSteps = max(parsedSearch.warmupSteps, 0)
    let postWarmupSteps = max(parsedSearch.steps - warmupSteps, 96)
    // Replays should cover the full post-warmup excursion so motion reads as locomotion rather
    // than a sub-second wobble loop.
    let renderSteps = warmupSteps + postWarmupSteps
    let frameStride = max(1, postWarmupSteps / max(targetFrames - 1, 1))
    let searchConfig = SearchConfig(
        steps: renderSteps,
        recordInterval: frameStride,
        warmupSteps: warmupSteps,
        occupancyThreshold: parsedSearch.occupancyThreshold,
        massChannel: parsedSearch.massChannel,
        scoreWeights: [:],
        filters: [:],
        complexity: nil,
        activity: nil,
        stability: nil,
        kSurvival: nil,
        moments: nil
    )

    let engine = SearchEngine(runtimeConfig: runtimeConfig)
    var capturedFrames: [Data] = []
    capturedFrames.reserveCapacity(targetFrames + 8)
    let capture = FrameCapture(stride: frameStride, includeWarmup: false, sampleIndex: 0) { _, _, _, data in
        capturedFrames.append(data)
    }
    _ = engine.runBatch(seeds: [seed], initSeedOffset: 0, searchConfig: searchConfig, frameCapture: capture)

    guard !capturedFrames.isEmpty else {
        throw ValidationError("Failed to capture replay frames for seed \(seed).")
    }
    return downsampleReplayFrames(capturedFrames, target: targetFrames)
}

func writeRenderedMediaAssets(
    creatureId: String,
    genotype: KernelParams,
    runtimeConfig: LeniaRuntimeConfig,
    selectedFrames: [Data],
    assetBaseURL: URL,
    creatureDir: URL,
    fps: Int,
    includeReplay: Bool
) throws -> AtlasRenderedMedia {
    let cleanedFrames = selectedFrames.map(cleanReplayFrame)

    guard let firstFrame = cleanedFrames.first else {
        throw ValidationError("Failed to capture replay frames for creature \(creatureId).")
    }

    let width = runtimeConfig.sx
    let height = runtimeConfig.sy
    let centroids = cleanedFrames.map { centroidForReplayFrame($0, width: width, height: height) }
    let velocities = computeCentroidVelocities(centroids: centroids)
    let telemetry = buildReplayTelemetrySummary(centroids: centroids, velocities: velocities, width: width, height: height)

    let posterIndex = min(cleanedFrames.count - 1, max(cleanedFrames.count / 2, 0))
    let fieldFrame = cleanedFrames[posterIndex]
    let previousFrame = cleanedFrames[max(0, posterIndex - 1)]

    let posterURL = creatureDir.appendingPathComponent("poster.png")
    let fieldURL = creatureDir.appendingPathComponent("field.png")
    let deltaURL = creatureDir.appendingPathComponent("delta.png")
    let neighborURL = creatureDir.appendingPathComponent("neighbor.png")
    let kernelURL = creatureDir.appendingPathComponent("kernel.png")
    let renderer = try makeLeniaMetalFieldRenderer()

    try writeLeniaSpectrumPNG(
        grayscale: fieldFrame,
        width: width,
        height: height,
        url: posterURL,
        renderer: renderer
    )
    try writeLeniaSpectrumPNG(
        grayscale: fieldFrame,
        width: width,
        height: height,
        url: fieldURL,
        renderer: renderer
    )

    let deltaRGBA = try leniaDeltaRGBA(previous: previousFrame, current: fieldFrame, width: width, height: height)
    try writePNGColorFrame(rgba: deltaRGBA, width: width, height: height, url: deltaURL)

    let neighborFrame = neighborhoodResponseFrame(
        for: fieldFrame,
        width: width,
        height: height,
        radius: neighborhoodRadius(genotype: genotype, width: width, height: height)
    )
    try writeLeniaSpectrumPNG(
        grayscale: neighborFrame,
        width: width,
        height: height,
        url: neighborURL,
        renderer: renderer
    )

    let kernelFrame = publishedKernelFrame(
        genotype: genotype,
        runtimeConfig: runtimeConfig,
        width: width,
        height: height
    )
    try writeLeniaSpectrumPNG(
        grayscale: kernelFrame,
        width: width,
        height: height,
        url: kernelURL,
        renderer: renderer
    )

    var replayPath: String?
    if includeReplay {
        let framesURL = creatureDir.appendingPathComponent("frames.bin")
        let replayURL = creatureDir.appendingPathComponent("replay.json")

        var payload = Data()
        payload.reserveCapacity(selectedFrames.count * firstFrame.count)
        for frame in cleanedFrames {
            payload.append(frame)
        }
        try payload.write(to: framesURL)

        let replay = AtlasReplay(
            width: width,
            height: height,
            frameCount: cleanedFrames.count,
            fps: fps,
            framesPath: relativePublishedPath(from: assetBaseURL, to: framesURL),
            centroids: centroids.map { [$0.x, $0.y] },
            velocities: velocities.map { [$0.x, $0.y] },
            palette: "lenia-spectrum"
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(replay).write(to: replayURL)
        replayPath = relativePublishedPath(from: assetBaseURL, to: replayURL)
    }

    return AtlasRenderedMedia(
        media: AtlasMedia(
            posterPath: relativePublishedPath(from: assetBaseURL, to: posterURL),
            replayPath: replayPath,
            width: width,
            height: height,
            anatomy: AtlasAnatomyMedia(
                fieldPath: relativePublishedPath(from: assetBaseURL, to: fieldURL),
                deltaPath: relativePublishedPath(from: assetBaseURL, to: deltaURL),
                neighborPath: relativePublishedPath(from: assetBaseURL, to: neighborURL),
                kernelPath: relativePublishedPath(from: assetBaseURL, to: kernelURL)
            )
        ),
        telemetry: telemetry
    )
}

private func centroidForReplayFrame(_ frame: Data, width: Int, height: Int) -> SIMD2<Float> {
    var sumMass: Float = 0
    var sumX: Float = 0
    var sumY: Float = 0
    frame.withUnsafeBytes { rawBuffer in
        let values = rawBuffer.bindMemory(to: UInt8.self)
        for y in 0..<height {
            let rowOffset = y * width
            for x in 0..<width {
                let mass = Float(values[rowOffset + x]) / 255.0
                if mass <= 0.005 { continue }
                sumMass += mass
                sumX += Float(x) * mass
                sumY += Float(y) * mass
            }
        }
    }
    if sumMass <= 1e-6 {
        return SIMD2(Float(width) * 0.5, Float(height) * 0.5)
    }
    return SIMD2(sumX / sumMass, sumY / sumMass)
}

private func computeCentroidVelocities(centroids: [SIMD2<Float>]) -> [SIMD2<Float>] {
    guard !centroids.isEmpty else { return [] }
    var velocities = [SIMD2<Float>](repeating: .zero, count: centroids.count)
    for index in 1..<centroids.count {
        velocities[index] = centroids[index] - centroids[index - 1]
    }
    return velocities
}

private func downsampleReplayFrames(_ frames: [Data], target: Int) -> [Data] {
    guard frames.count > target, target > 1 else { return frames }
    let last = frames.count - 1
    return (0..<target).map { index in
        let fraction = Double(index) / Double(target - 1)
        let sourceIndex = Int((fraction * Double(last)).rounded())
        return frames[sourceIndex]
    }
}

private func cleanReplayFrame(_ frame: Data) -> Data {
    guard let maxByte = frame.max(), maxByte > 0 else {
        return frame
    }

    let floor = max(12, Int((Float(maxByte) * 0.06).rounded(.down)))
    if floor >= Int(maxByte) {
        return frame
    }

    let scale = 255.0 / Float(Int(maxByte) - floor)
    return Data(frame.map { value in
        let raw = Int(value)
        if raw <= floor {
            return 0
        }
        let lifted = Float(raw - floor) * scale
        return replayByte(lifted / 255.0)
    })
}

private func buildReplayTelemetrySummary(
    centroids: [SIMD2<Float>],
    velocities: [SIMD2<Float>],
    width: Int,
    height: Int
) -> AtlasTelemetrySummary {
    guard let last = centroids.last else {
        return AtlasTelemetrySummary(
            centroid: AtlasPoint(x: 0.5, y: 0.5),
            trail: [],
            vx: 0,
            vy: 0,
            speed: 0,
            headingRad: 0
        )
    }

    let recent = Array(centroids.suffix(4))
    let rawVelocity = velocities.reversed().first { abs($0.x) > 1e-6 || abs($0.y) > 1e-6 } ?? .zero
    let normalizedVx = rawVelocity.x / max(Float(width), 1)
    let normalizedVy = -rawVelocity.y / max(Float(height), 1)
    let speed = sqrt(normalizedVx * normalizedVx + normalizedVy * normalizedVy)
    let headingRad: Float = speed > 1e-6 ? atan2(normalizedVy, normalizedVx) : 0

    return AtlasTelemetrySummary(
        centroid: normalizedReplayPoint(last, width: width, height: height),
        trail: recent.dropLast().map { normalizedReplayPoint($0, width: width, height: height) },
        vx: normalizedVx,
        vy: normalizedVy,
        speed: speed,
        headingRad: headingRad
    )
}

private func normalizedReplayPoint(_ point: SIMD2<Float>, width: Int, height: Int) -> AtlasPoint {
    AtlasPoint(
        x: clampReplayValue(point.x / max(Float(width), 1), lower: 0.05, upper: 0.95),
        y: clampReplayValue(point.y / max(Float(height), 1), lower: 0.05, upper: 0.95)
    )
}

private func neighborhoodRadius(genotype: KernelParams, width: Int, height: Int) -> Int {
    let scaled = genotype.R * max(genotype.r.first ?? 1.0, 0.2) * 0.35
    let maxRadius = max(2, min(width, height) / 10)
    return max(2, min(Int(scaled.rounded()), maxRadius))
}

private func neighborhoodResponseFrame(for frame: Data, width: Int, height: Int, radius: Int) -> Data {
    let values = [UInt8](frame)
    let clampedRadius = max(1, radius)
    let window = Float(clampedRadius * 2 + 1)
    var horizontal = [Float](repeating: 0, count: values.count)

    for y in 0..<height {
        let rowOffset = y * width
        var sum = 0
        for dx in -clampedRadius...clampedRadius {
            let x = min(width - 1, max(0, dx))
            sum += Int(values[rowOffset + x])
        }
        horizontal[rowOffset] = Float(sum) / window
        if width > 1 {
            for x in 1..<width {
                let addX = min(width - 1, x + clampedRadius)
                let removeX = max(0, x - clampedRadius - 1)
                sum += Int(values[rowOffset + addX]) - Int(values[rowOffset + removeX])
                horizontal[rowOffset + x] = Float(sum) / window
            }
        }
    }

    var output = [UInt8](repeating: 0, count: values.count)
    for x in 0..<width {
        var sum: Float = 0
        for dy in -clampedRadius...clampedRadius {
            let y = min(height - 1, max(0, dy))
            sum += horizontal[y * width + x]
        }
        output[x] = replayByte((sum / window) / 255.0 * 1.18)
        if height > 1 {
            for y in 1..<height {
                let addY = min(height - 1, y + clampedRadius)
                let removeY = max(0, y - clampedRadius - 1)
                sum += horizontal[addY * width + x] - horizontal[removeY * width + x]
                output[y * width + x] = replayByte((sum / window) / 255.0 * 1.18)
            }
        }
    }
    return Data(output)
}

private func publishedKernelFrame(
    genotype: KernelParams,
    runtimeConfig: LeniaRuntimeConfig,
    width: Int,
    height: Int
) -> Data {
    let lobesA = genotype.a.first ?? []
    let lobesW = genotype.w.first ?? []
    let lobesB = genotype.b.first ?? []
    let lobeCount = min(lobesA.count, lobesW.count, lobesB.count)
    guard lobeCount > 0 else {
        return Data(repeating: 0, count: width * height)
    }

    let kernelProfile = runtimeConfig.implementation.kernelProfile
    let radiusBase: Float = kernelProfile == "flowlenia_2022_colab" ? (genotype.R + 15.0) : genotype.R
    let divisor = max(radiusBase * max(genotype.r.first ?? 1.0, 0.05), 1e-6)
    let centerX = Float(width - 1) * 0.5
    let centerY = Float(height - 1) * 0.5

    var field = [Float](repeating: 0, count: width * height)
    var maxValue: Float = 0
    for y in 0..<height {
        let dy = Float(y) - centerY
        let rowOffset = y * width
        for x in 0..<width {
            let dx = Float(x) - centerX
            let distance = sqrt(dx * dx + dy * dy) / divisor
            var value: Float = 0
            for index in 0..<lobeCount {
                let diff = distance - lobesA[index]
                let widthValue = max(lobesW[index], 1e-4)
                let exponent: Float
                if kernelProfile == "flowlenia_2022_colab" {
                    exponent = -(diff * diff) / widthValue
                } else {
                    exponent = -(diff * diff) / (2.0 * widthValue * widthValue)
                }
                value += lobesB[index] * Float(Foundation.exp(Double(exponent)))
            }
            if kernelProfile == "flowlenia_2022_colab" {
                value *= 1.0 / (1.0 + Float(Foundation.exp(Double((distance - 1.0) * 10.0))))
            }
            let cleaned = max(value, 0)
            field[rowOffset + x] = cleaned
            maxValue = max(maxValue, cleaned)
        }
    }

    guard maxValue > 1e-6 else {
        return Data(repeating: 0, count: width * height)
    }
    return Data(field.map { replayByte(pow($0 / maxValue, 0.72)) })
}

private func relativePublishedPath(from base: URL, to target: URL) -> String {
    let baseURL = base.standardizedFileURL
    let targetURL = target.standardizedFileURL
    let basePath = baseURL.path.hasSuffix("/") ? baseURL.path : "\(baseURL.path)/"
    guard targetURL.path.hasPrefix(basePath) else {
        return targetURL.path
    }
    return String(targetURL.path.dropFirst(basePath.count))
}

private func clampReplayValue(_ value: Float, lower: Float, upper: Float) -> Float {
    max(lower, min(upper, value))
}

private func replayByte(_ value: Float) -> UInt8 {
    UInt8(max(0, min(255, Int(clampReplayValue(value, lower: 0, upper: 1) * 255.0 + 0.5))))
}
