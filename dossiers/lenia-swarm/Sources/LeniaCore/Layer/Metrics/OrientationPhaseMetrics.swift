import Foundation

func computeOrientationPhaseMotionBatch(
    materialized sequence: [MassBatchCPU],
    threshold: Float
) -> [Float] {
    guard let first = sequence.first else {
        return []
    }
    let batch = first.batch
    for frame in sequence {
        precondition(frame.batch == batch, "orientation phase frames must have matching batch sizes.")
        precondition(frame.height == first.height, "orientation phase frames must have matching heights.")
        precondition(frame.width == first.width, "orientation phase frames must have matching widths.")
    }
    guard sequence.count >= 2 else {
        return [Float](repeating: 0, count: batch)
    }

    let angles = sequence.map { orientationAngles(materialized: $0, threshold: threshold) }
    let normalizer = Float.pi / 2
    var scores = [Float](repeating: 0, count: batch)
    var counts = [Float](repeating: 0, count: batch)

    for frameIndex in 1..<angles.count {
        let previous = angles[frameIndex - 1]
        let current = angles[frameIndex]
        for sampleIndex in 0..<batch {
            guard let a = previous[sampleIndex], let b = current[sampleIndex] else {
                continue
            }
            scores[sampleIndex] += axialAngleDistance(a, b)
            counts[sampleIndex] += 1
        }
    }

    return scores.indices.map { index in
        guard counts[index] > 0 else { return 0 }
        return max(0, min(1, scores[index] / counts[index] / normalizer))
    }
}

func computeAngularPhaseMotionBatch(
    materialized sequence: [MassBatchCPU],
    threshold: Float,
    order: Int,
    minimumAmplitude: Float
) -> [Float] {
    precondition(order > 0, "angular phase motion order must be positive.")
    guard let first = sequence.first else {
        return []
    }
    let batch = first.batch
    for frame in sequence {
        precondition(frame.batch == batch, "angular phase frames must have matching batch sizes.")
        precondition(frame.height == first.height, "angular phase frames must have matching heights.")
        precondition(frame.width == first.width, "angular phase frames must have matching widths.")
    }
    guard sequence.count >= 2 else {
        return [Float](repeating: 0, count: batch)
    }

    let phases = sequence.map {
        angularHarmonicPhases(
            materialized: $0,
            threshold: threshold,
            order: order,
            minimumAmplitude: minimumAmplitude
        )
    }
    var scores = [Float](repeating: 0, count: batch)
    var counts = [Float](repeating: 0, count: batch)

    for frameIndex in 1..<phases.count {
        let previous = phases[frameIndex - 1]
        let current = phases[frameIndex]
        for sampleIndex in 0..<batch {
            guard let a = previous[sampleIndex], let b = current[sampleIndex] else {
                continue
            }
            scores[sampleIndex] += circularAngleDistance(a, b)
            counts[sampleIndex] += 1
        }
    }

    return scores.indices.map { index in
        guard counts[index] > 0 else { return 0 }
        return max(0, min(1, scores[index] / counts[index] / Float.pi))
    }
}

func computeSectorTransportMotionBatch(
    materialized sequence: [MassBatchCPU],
    threshold: Float,
    binCount: Int,
    minimumContrast: Float
) -> [Float] {
    precondition(binCount >= 8, "sector transport bin count must be at least 8.")
    precondition(minimumContrast >= 0, "sector transport minimum contrast cannot be negative.")
    guard let first = sequence.first else {
        return []
    }
    let batch = first.batch
    for frame in sequence {
        precondition(frame.batch == batch, "sector transport frames must have matching batch sizes.")
        precondition(frame.height == first.height, "sector transport frames must have matching heights.")
        precondition(frame.width == first.width, "sector transport frames must have matching widths.")
    }
    guard sequence.count >= 2 else {
        return [Float](repeating: 0, count: batch)
    }

    let profiles = sequence.map {
        angularSectorProfiles(
            materialized: $0,
            threshold: threshold,
            binCount: binCount,
            minimumContrast: minimumContrast
        )
    }
    var scores = [Float](repeating: 0, count: batch)
    var counts = [Float](repeating: 0, count: batch)

    for frameIndex in 1..<profiles.count {
        let previous = profiles[frameIndex - 1]
        let current = profiles[frameIndex]
        for sampleIndex in 0..<batch {
            guard let a = previous[sampleIndex], let b = current[sampleIndex] else {
                continue
            }
            let shiftScore = circularProfileShiftScore(previous: a, current: b)
            if shiftScore > 0 {
                scores[sampleIndex] += shiftScore
                counts[sampleIndex] += 1
            }
        }
    }

    return scores.indices.map { index in
        guard counts[index] > 0 else { return 0 }
        return max(0, min(1, scores[index] / counts[index]))
    }
}

private func orientationAngles(materialized batchData: MassBatchCPU, threshold: Float) -> [Float?] {
    let flat = batchData.flat
    var angles: [Float?] = []
    angles.reserveCapacity(batchData.batch)

    for sampleIndex in 0..<batchData.batch {
        let offset = sampleIndex * batchData.sampleSize
        var mass: Float = 0
        var xSum: Float = 0
        var ySum: Float = 0
        for y in 0..<batchData.height {
            for x in 0..<batchData.width {
                let value = flat[offset + y * batchData.width + x]
                guard value > threshold else {
                    continue
                }
                mass += value
                xSum += Float(x) * value
                ySum += Float(y) * value
            }
        }
        guard mass > 1e-8 else {
            angles.append(nil)
            continue
        }

        let cx = xSum / mass
        let cy = ySum / mass
        var mu20: Float = 0
        var mu02: Float = 0
        var mu11: Float = 0
        for y in 0..<batchData.height {
            for x in 0..<batchData.width {
                let value = flat[offset + y * batchData.width + x]
                guard value > threshold else {
                    continue
                }
                let dx = Float(x) - cx
                let dy = Float(y) - cy
                mu20 += dx * dx * value
                mu02 += dy * dy * value
                mu11 += dx * dy * value
            }
        }

        let anisotropyNumerator = sqrt(max((mu20 - mu02) * (mu20 - mu02) + 4 * mu11 * mu11, 0))
        let anisotropyDenominator = mu20 + mu02
        guard anisotropyDenominator > 1e-8,
              anisotropyNumerator / anisotropyDenominator > 0.02 else {
            angles.append(nil)
            continue
        }
        angles.append(0.5 * atan2(2 * mu11, mu20 - mu02))
    }

    return angles
}

private func axialAngleDistance(_ a: Float, _ b: Float) -> Float {
    let period = Float.pi
    var delta = abs(a - b).truncatingRemainder(dividingBy: period)
    if delta > period / 2 {
        delta = period - delta
    }
    return delta
}

private func angularHarmonicPhases(
    materialized batchData: MassBatchCPU,
    threshold: Float,
    order: Int,
    minimumAmplitude: Float
) -> [Float?] {
    let flat = batchData.flat
    let centerX = (Float(batchData.width) - 1) * 0.5
    let centerY = (Float(batchData.height) - 1) * 0.5
    var phases: [Float?] = []
    phases.reserveCapacity(batchData.batch)

    for sampleIndex in 0..<batchData.batch {
        let offset = sampleIndex * batchData.sampleSize
        var total: Float = 0
        var real: Float = 0
        var imag: Float = 0
        for y in 0..<batchData.height {
            for x in 0..<batchData.width {
                let mass = flat[offset + y * batchData.width + x]
                guard mass > threshold else {
                    continue
                }
                total += mass
                let theta = atan2(Float(y) - centerY, Float(x) - centerX)
                real += mass * cos(Float(order) * theta)
                imag -= mass * sin(Float(order) * theta)
            }
        }

        guard total > 1e-8 else {
            phases.append(nil)
            continue
        }
        real /= total
        imag /= total
        let amplitude = sqrt(real * real + imag * imag)
        guard amplitude >= minimumAmplitude else {
            phases.append(nil)
            continue
        }
        phases.append(atan2(imag, real))
    }

    return phases
}

private func angularSectorProfiles(
    materialized batchData: MassBatchCPU,
    threshold: Float,
    binCount: Int,
    minimumContrast: Float
) -> [[Float]?] {
    let flat = batchData.flat
    var profiles: [[Float]?] = []
    profiles.reserveCapacity(batchData.batch)

    for sampleIndex in 0..<batchData.batch {
        let offset = sampleIndex * batchData.sampleSize
        var mass: Float = 0
        var xSum: Float = 0
        var ySum: Float = 0
        for y in 0..<batchData.height {
            for x in 0..<batchData.width {
                let value = flat[offset + y * batchData.width + x]
                guard value > threshold else {
                    continue
                }
                mass += value
                xSum += Float(x) * value
                ySum += Float(y) * value
            }
        }
        guard mass > 1e-8 else {
            profiles.append(nil)
            continue
        }

        let cx = xSum / mass
        let cy = ySum / mass
        var bins = [Float](repeating: 0, count: binCount)
        for y in 0..<batchData.height {
            for x in 0..<batchData.width {
                let value = flat[offset + y * batchData.width + x]
                guard value > threshold else {
                    continue
                }
                let theta = atan2(Float(y) - cy, Float(x) - cx)
                let normalized = (theta + Float.pi) / (2 * Float.pi)
                let bin = min(binCount - 1, max(0, Int(normalized * Float(binCount))))
                bins[bin] += value
            }
        }

        for index in bins.indices {
            bins[index] /= mass
        }
        let mean = 1 / Float(binCount)
        let variance = bins.reduce(Float(0)) { partial, value in
            let centered = value - mean
            return partial + centered * centered
        } / Float(binCount)
        let contrast = sqrt(max(variance, 0)) / max(mean, 1e-8)
        guard contrast >= minimumContrast else {
            profiles.append(nil)
            continue
        }
        profiles.append(bins)
    }

    return profiles
}

private func circularProfileShiftScore(previous: [Float], current: [Float]) -> Float {
    precondition(previous.count == current.count, "sector profiles must have matching lengths.")
    let count = previous.count
    guard count >= 8 else { return 0 }
    let mean = 1 / Float(count)
    let previousCentered = previous.map { $0 - mean }
    let currentCentered = current.map { $0 - mean }
    let previousEnergy = previousCentered.reduce(Float(0)) { $0 + $1 * $1 }
    let currentEnergy = currentCentered.reduce(Float(0)) { $0 + $1 * $1 }
    let denominator = sqrt(previousEnergy * currentEnergy)
    guard denominator > 1e-8 else { return 0 }

    var bestShift = 0
    var bestCorrelation = -Float.greatestFiniteMagnitude
    for shift in 0..<count {
        var correlation: Float = 0
        for index in 0..<count {
            correlation += previousCentered[index] * currentCentered[(index + shift) % count]
        }
        correlation /= denominator
        if correlation > bestCorrelation {
            bestCorrelation = correlation
            bestShift = shift
        }
    }

    let signedShift = bestShift <= count / 2 ? bestShift : bestShift - count
    guard signedShift != 0, bestCorrelation > 0 else {
        return 0
    }
    let shiftFraction = min(Float(abs(signedShift)) / Float(count / 2), 1)
    return max(0, min(1, shiftFraction * bestCorrelation))
}

private func circularAngleDistance(_ a: Float, _ b: Float) -> Float {
    let period = Float.pi * 2
    var delta = abs(a - b).truncatingRemainder(dividingBy: period)
    if delta > Float.pi {
        delta = period - delta
    }
    return delta
}
