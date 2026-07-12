import CoreGraphics
import MLX
import Accelerate

public struct LeniaRenderer {
    public init() {}

    public func renderToImage(mass: MLXArray, channel: Int = 0) -> CGImage? {
        eval(mass)

        let shape = mass.shape
        guard shape.count >= 2 else { return nil }

        let height = shape[0]
        let width = shape[1]

        // Extract single channel if multi-channel
        let channelData: MLXArray
        if shape.count == 3 {
            channelData = mass[0..., 0..., channel]
        } else {
            channelData = mass
        }

        // Convert to Float array on CPU
        let floatData = channelData.asArray(Float.self)

        // Normalize to 0-255 and convert to UInt8
        var minVal: Float = 0
        var maxVal: Float = 1
        vDSP_minv(floatData, 1, &minVal, vDSP_Length(floatData.count))
        vDSP_maxv(floatData, 1, &maxVal, vDSP_Length(floatData.count))

        let range = maxVal - minVal
        let scale: Float = range > 0 ? 255.0 / range : 0

        var normalized = [Float](repeating: 0, count: floatData.count)
        var negMin = -minVal
        vDSP_vsadd(floatData, 1, &negMin, &normalized, 1, vDSP_Length(floatData.count))
        vDSP_vsmul(normalized, 1, [scale], &normalized, 1, vDSP_Length(floatData.count))

        // RGBA so stitchable color-effect shaders can read .r and output full color
        var rgbaData = [UInt8](repeating: 0, count: floatData.count * 4)
        for i in 0..<floatData.count {
            let v = UInt8(min(255, max(0, normalized[i])))
            rgbaData[i * 4 + 0] = v
            rgbaData[i * 4 + 1] = v
            rgbaData[i * 4 + 2] = v
            rgbaData[i * 4 + 3] = 255
        }

        let colorSpace = CGColorSpaceCreateDeviceRGB()
        let bitmapInfo = CGBitmapInfo(rawValue: CGImageAlphaInfo.noneSkipLast.rawValue)

        guard let provider = CGDataProvider(data: Data(rgbaData) as CFData) else {
            return nil
        }

        return CGImage(
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
        )
    }

    public func renderToSignedImage(field: MLXArray) -> CGImage? {
        eval(field)

        let shape = field.shape
        guard shape.count >= 2 else { return nil }

        let height = shape[0]
        let width = shape[1]
        let floatData = field.asArray(Float.self)

        var minVal: Float = 0
        var maxVal: Float = 0
        vDSP_minv(floatData, 1, &minVal, vDSP_Length(floatData.count))
        vDSP_maxv(floatData, 1, &maxVal, vDSP_Length(floatData.count))
        let maxAbs = max(abs(minVal), abs(maxVal))
        let scale = maxAbs > 0 ? 1.0 / maxAbs : 0.0

        var rgbaData = [UInt8](repeating: 255, count: width * height * 4)
        for i in 0..<floatData.count {
            let normalized = max(-1.0, min(1.0, floatData[i] * scale))
            let color: (Float, Float, Float)
            if normalized >= 0 {
                let t = normalized
                color = (
                    0.82 + 0.16 * t,
                    0.24 + 0.40 * (1.0 - t),
                    0.58 + 0.24 * t
                )
            } else {
                let t = -normalized
                color = (
                    0.18 + 0.20 * (1.0 - t),
                    0.42 + 0.40 * t,
                    0.78 + 0.14 * t
                )
            }

            rgbaData[i * 4 + 0] = UInt8(max(0, min(255, Int(color.0 * 255.0))))
            rgbaData[i * 4 + 1] = UInt8(max(0, min(255, Int(color.1 * 255.0))))
            rgbaData[i * 4 + 2] = UInt8(max(0, min(255, Int(color.2 * 255.0))))
        }

        let colorSpace = CGColorSpaceCreateDeviceRGB()
        let bitmapInfo = CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue)

        guard let provider = CGDataProvider(data: Data(rgbaData) as CFData) else {
            return nil
        }

        return CGImage(
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
        )
    }
}
