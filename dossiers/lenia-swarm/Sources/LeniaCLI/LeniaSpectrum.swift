import Foundation

private struct SpectrumRGB {
    let r: Float
    let g: Float
    let b: Float
}

private func spectrumMix(_ lhs: SpectrumRGB, _ rhs: SpectrumRGB, _ t: Float) -> SpectrumRGB {
    let x = max(0, min(1, t))
    return SpectrumRGB(
        r: lhs.r + (rhs.r - lhs.r) * x,
        g: lhs.g + (rhs.g - lhs.g) * x,
        b: lhs.b + (rhs.b - lhs.b) * x
    )
}

private func spectrumSmoothstep(_ edge0: Float, _ edge1: Float, _ x: Float) -> Float {
    let denom = max(edge1 - edge0, 1e-12)
    let t = max(0, min(1, (x - edge0) / denom))
    return t * t * (3 - 2 * t)
}

func leniaDeltaRGBA(previous: Data, current: Data, width: Int, height: Int) throws -> Data {
    let expected = width * height
    if previous.count != expected {
        throw FrameExportError.invalidSize(expected: expected, actual: previous.count)
    }
    if current.count != expected {
        throw FrameExportError.invalidSize(expected: expected, actual: current.count)
    }

    let negativeLow = SpectrumRGB(r: 0.090, g: 0.410, b: 0.960)
    let negativeHigh = SpectrumRGB(r: 0.320, g: 0.820, b: 0.990)
    let positiveLow = SpectrumRGB(r: 0.420, g: 0.980, b: 0.520)
    let positiveHigh = SpectrumRGB(r: 0.990, g: 0.420, b: 0.150)
    let background = SpectrumRGB(r: 0.060, g: 0.058, b: 0.085)

    var rgba = [UInt8](repeating: 0, count: width * height * 4)
    for idx in 0..<expected {
        let previousValue = Float(previous[previous.startIndex + idx]) / 255.0
        let currentValue = Float(current[current.startIndex + idx]) / 255.0
        let diff = currentValue - previousValue
        let magnitude = min(abs(diff) * 5.5, 1.0)
        let alpha = spectrumSmoothstep(0.015, 0.16, magnitude)

        let accent: SpectrumRGB
        if diff >= 0 {
            accent = spectrumMix(positiveLow, positiveHigh, pow(magnitude, 0.82))
        } else {
            accent = spectrumMix(negativeLow, negativeHigh, pow(magnitude, 0.82))
        }

        let value = spectrumMix(background, accent, alpha)
        let out = idx * 4
        rgba[out + 0] = UInt8(max(0, min(255, Int(value.r * alpha * 255.0 + 0.5))))
        rgba[out + 1] = UInt8(max(0, min(255, Int(value.g * alpha * 255.0 + 0.5))))
        rgba[out + 2] = UInt8(max(0, min(255, Int(value.b * alpha * 255.0 + 0.5))))
        rgba[out + 3] = UInt8(max(0, min(255, Int(alpha * 255.0 + 0.5))))
    }
    return Data(rgba)
}
