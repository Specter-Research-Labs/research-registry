import Compression
import CoreGraphics
import Foundation
import ImageIO
import MLX
import UniformTypeIdentifiers

public struct ComplexityConfig: Codable, Sendable {
    public let enabled: Bool
    public let scales: [Int]
    public let target: Float?
    public let polar: Bool
    public let backend: String

    public init(enabled: Bool, scales: [Int], target: Float?, polar: Bool, backend: String) {
        self.enabled = enabled
        self.scales = scales
        self.target = target
        self.polar = polar
        self.backend = backend
    }
}

public struct ComplexityBatchResult: Sendable {
    public let mean: [Float]
    public let scales: [[Float]]
    public let targetScores: [Float]?

    public init(mean: [Float], scales: [[Float]], targetScores: [Float]?) {
        self.mean = mean
        self.scales = scales
        self.targetScores = targetScores
    }
}

public func computeComplexityBatch(massMap: MLXArray, config: ComplexityConfig) -> ComplexityBatchResult {
    guard config.enabled else {
        return ComplexityBatchResult(mean: [], scales: [], targetScores: nil)
    }
    guard !config.scales.isEmpty else {
        fatalError("complexity.scales must be non-empty when complexity is enabled.")
    }
    for scale in config.scales {
        if scale < 0 {
            fatalError("complexity.scales must be >= 0 (got \(scale)).")
        }
    }
    return computeComplexityBatch(materialized: materializeMassBatch(massMap), config: config)
}

func computeComplexityBatch(materialized batchData: MassBatchCPU, config: ComplexityConfig) -> ComplexityBatchResult {
    let flat = batchData.flat
    let batch = batchData.batch
    let height = batchData.height
    let width = batchData.width
    let sampleSize = batchData.sampleSize

    var meanScores: [Float] = []
    var scaleScores: [[Float]] = []
    var targetScores: [Float]? = config.target != nil ? [] : nil

    let backend = config.backend.lowercased()
    for idx in 0..<batch {
        let start = idx * sampleSize

        var perScale: [Float] = []
        for scale in config.scales {
            let factor = 1 << scale
            let downsampled = downsampleMean(
                flat,
                offset: start,
                width: width,
                height: height,
                factor: factor
            )
            let downWidth = width / factor
            let downHeight = height / factor
            let finalData = config.polar ? polarResample(downsampled, width: downWidth, height: downHeight) : downsampled
            let bytes = normalizeToUInt8(finalData)

            let compressedSize: Int
            switch backend {
            case "png":
                compressedSize = pngCompressedSize(bytes, width: downWidth, height: downHeight)
            case "zlib":
                compressedSize = zlibCompressedSize(bytes)
            default:
                fatalError("Unsupported complexity.backend: \(config.backend)")
            }

            let rawSize = max(bytes.count, 1)
            let ratio = Float(compressedSize) / Float(rawSize)
            perScale.append(ratio)
        }

        let mean = perScale.reduce(0, +) / Float(perScale.count)
        meanScores.append(mean)
        scaleScores.append(perScale)

        if let target = config.target {
            let score = perScale.map { abs($0 - target) }.reduce(0, +) / Float(perScale.count)
            targetScores?.append(score)
        }
    }

    return ComplexityBatchResult(mean: meanScores, scales: scaleScores, targetScores: targetScores)
}

private func downsampleMean(_ data: [Float], offset: Int, width: Int, height: Int, factor: Int) -> [Float] {
    guard factor > 0 else {
        fatalError("downsample factor must be > 0")
    }
    let outWidth = width / factor
    let outHeight = height / factor
    guard outWidth > 0 && outHeight > 0 else {
        fatalError("downsample factor \(factor) too large for \(width)x\(height)")
    }

    var out = [Float](repeating: 0.0, count: outWidth * outHeight)
    let area = Float(factor * factor)
    for y in 0..<outHeight {
        for x in 0..<outWidth {
            var sum: Float = 0.0
            let baseX = x * factor
            let baseY = y * factor
            for dy in 0..<factor {
                let row = offset + (baseY + dy) * width
                for dx in 0..<factor {
                    sum += data[row + baseX + dx]
                }
            }
            out[y * outWidth + x] = sum / area
        }
    }
    return out
}

private func polarResample(_ data: [Float], width: Int, height: Int) -> [Float] {
    guard width > 0 && height > 0 else { return [] }
    let centerX = Float(width - 1) * 0.5
    let centerY = Float(height - 1) * 0.5
    let radiusMax = min(centerX, centerY)
    let twoPi = Float.pi * 2.0

    var out = [Float](repeating: 0.0, count: width * height)
    for y in 0..<height {
        let r = radiusMax * Float(y) / Float(max(height - 1, 1))
        for x in 0..<width {
            let theta = twoPi * Float(x) / Float(width)
            let fx = centerX + r * cos(theta)
            let fy = centerY + r * sin(theta)
            out[y * width + x] = bilinearSample(data, width: width, height: height, x: fx, y: fy)
        }
    }
    return out
}

private func bilinearSample(_ data: [Float], width: Int, height: Int, x: Float, y: Float) -> Float {
    let x0 = max(0, min(width - 1, Int(floor(x))))
    let y0 = max(0, min(height - 1, Int(floor(y))))
    let x1 = max(0, min(width - 1, x0 + 1))
    let y1 = max(0, min(height - 1, y0 + 1))

    let fx = x - Float(x0)
    let fy = y - Float(y0)

    let v00 = data[y0 * width + x0]
    let v10 = data[y0 * width + x1]
    let v01 = data[y1 * width + x0]
    let v11 = data[y1 * width + x1]

    let v0 = v00 * (1 - fx) + v10 * fx
    let v1 = v01 * (1 - fx) + v11 * fx
    return v0 * (1 - fy) + v1 * fy
}

private func normalizeToUInt8(_ data: [Float]) -> [UInt8] {
    guard !data.isEmpty else { return [] }
    var minVal = Float.greatestFiniteMagnitude
    var maxVal = -Float.greatestFiniteMagnitude
    for v in data {
        minVal = min(minVal, v)
        maxVal = max(maxVal, v)
    }
    let range = maxVal - minVal
    let scale: Float = range > 0 ? 255.0 / range : 0.0

    var out = [UInt8](repeating: 0, count: data.count)
    for (i, v) in data.enumerated() {
        let scaled = (v - minVal) * scale
        let clamped = min(255.0, max(0.0, scaled))
        out[i] = UInt8(clamped)
    }
    return out
}

private func pngCompressedSize(_ bytes: [UInt8], width: Int, height: Int) -> Int {
    guard width > 0 && height > 0 else { return 0 }
    let data = Data(bytes)
    guard let provider = CGDataProvider(data: data as CFData) else {
        return bytes.count
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
        return bytes.count
    }

    let outputData = NSMutableData()
    guard let dest = CGImageDestinationCreateWithData(outputData, UTType.png.identifier as CFString, 1, nil) else {
        return bytes.count
    }
    CGImageDestinationAddImage(dest, image, nil)
    if CGImageDestinationFinalize(dest) {
        return outputData.length
    }
    return bytes.count
}

private func zlibCompressedSize(_ bytes: [UInt8]) -> Int {
    guard !bytes.isEmpty else { return 0 }
    let sourceSize = bytes.count
    let outputCapacity = sourceSize + max(64, sourceSize / 8)
    var output = [UInt8](repeating: 0, count: outputCapacity)
    let compressedSize = output.withUnsafeMutableBytes { dst in
        bytes.withUnsafeBytes { src in
            compression_encode_buffer(
                dst.bindMemory(to: UInt8.self).baseAddress!,
                outputCapacity,
                src.bindMemory(to: UInt8.self).baseAddress!,
                sourceSize,
                nil,
                COMPRESSION_ZLIB
            )
        }
    }
    if compressedSize == 0 {
        return sourceSize
    }
    return compressedSize
}
