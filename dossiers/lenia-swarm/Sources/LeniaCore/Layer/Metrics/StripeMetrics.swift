import Foundation

func computeInternalStripeContrastBatch(
    materialized batchData: MassBatchCPU,
    threshold: Float,
    useTorus: Bool
) -> [Float] {
    let flat = batchData.flat
    let batch = batchData.batch
    let height = batchData.height
    let width = batchData.width
    let sampleSize = batchData.sampleSize
    let pairOffsets = [(1, 0), (0, 1), (1, 1), (1, -1)]

    var scores: [Float] = []
    scores.reserveCapacity(batch)

    for sampleIndex in 0..<batch {
        let start = sampleIndex * sampleSize
        var contrastSum: Float = 0
        var pairCount: Float = 0

        for y in 0..<height {
            for x in 0..<width {
                let idx = y * width + x
                let value = flat[start + idx]
                if value <= threshold || occupiedNeighborCount(
                    flat: flat,
                    offset: start,
                    width: width,
                    height: height,
                    x: x,
                    y: y,
                    threshold: threshold,
                    useTorus: useTorus
                ) < 6 {
                    continue
                }

                for (dx, dy) in pairOffsets {
                    guard let neighborIndex = stripeNeighborIndex(
                        width: width,
                        height: height,
                        x: x,
                        y: y,
                        dx: dx,
                        dy: dy,
                        useTorus: useTorus
                    ) else {
                        continue
                    }
                    let neighborValue = flat[start + neighborIndex]
                    if neighborValue <= threshold {
                        continue
                    }
                    contrastSum += abs(value - neighborValue)
                    pairCount += 1
                }
            }
        }

        scores.append(pairCount > 0 ? contrastSum / pairCount : 0)
    }

    return scores
}

func computeOrientedRidgeDominanceBatch(
    materialized batchData: MassBatchCPU,
    threshold: Float
) -> [Float] {
    let flat = batchData.flat
    let batch = batchData.batch
    let height = batchData.height
    let width = batchData.width
    let sampleSize = batchData.sampleSize

    var scores: [Float] = []
    scores.reserveCapacity(batch)

    for sampleIndex in 0..<batch {
        let start = sampleIndex * sampleSize
        var totalMass: Float = 0
        var maxValue: Float = threshold
        for idx in 0..<sampleSize {
            let value = flat[start + idx]
            if value <= threshold {
                continue
            }
            totalMass += value
            maxValue = max(maxValue, value)
        }
        if totalMass <= 1e-8 || maxValue <= threshold {
            scores.append(0)
            continue
        }

        let brightThreshold = threshold + 0.55 * (maxValue - threshold)
        var rowSums = [Float](repeating: 0, count: height)
        var colSums = [Float](repeating: 0, count: width)
        var diagSums = [Float](repeating: 0, count: height + width - 1)
        var antiDiagSums = [Float](repeating: 0, count: height + width - 1)
        var rowCounts = [Int](repeating: 0, count: height)
        var colCounts = [Int](repeating: 0, count: width)
        var diagCounts = [Int](repeating: 0, count: height + width - 1)
        var antiDiagCounts = [Int](repeating: 0, count: height + width - 1)
        var brightMass: Float = 0

        for y in 0..<height {
            for x in 0..<width {
                let value = flat[start + y * width + x]
                guard value > brightThreshold else {
                    continue
                }
                let mass = value - brightThreshold
                let diag = y - x + width - 1
                let antiDiag = y + x
                brightMass += mass
                rowSums[y] += mass
                colSums[x] += mass
                diagSums[diag] += mass
                antiDiagSums[antiDiag] += mass
                rowCounts[y] += 1
                colCounts[x] += 1
                diagCounts[diag] += 1
                antiDiagCounts[antiDiag] += 1
            }
        }

        if brightMass <= 1e-8 {
            scores.append(0)
            continue
        }

        let candidates = [
            maxLineDominance(sums: rowSums, counts: rowCounts, brightMass: brightMass),
            maxLineDominance(sums: colSums, counts: colCounts, brightMass: brightMass),
            maxLineDominance(sums: diagSums, counts: diagCounts, brightMass: brightMass),
            maxLineDominance(sums: antiDiagSums, counts: antiDiagCounts, brightMass: brightMass),
        ]
        scores.append(candidates.max() ?? 0)
    }

    return scores
}

func computeLargestComponentInternalStripeContrastBatch(
    materialized batchData: MassBatchCPU,
    threshold: Float,
    useTorus: Bool
) -> [Float] {
    let masks = largestComponentMasks(
        materialized: batchData,
        threshold: threshold,
        useTorus: useTorus
    )
    return computeInternalStripeContrastBatch(
        materialized: batchData,
        threshold: threshold,
        useTorus: useTorus,
        masks: masks
    )
}

func computeLargestComponentOrientedRidgeDominanceBatch(
    materialized batchData: MassBatchCPU,
    threshold: Float,
    useTorus: Bool
) -> [Float] {
    let masks = largestComponentMasks(
        materialized: batchData,
        threshold: threshold,
        useTorus: useTorus
    )
    return computeOrientedRidgeDominanceBatch(
        materialized: batchData,
        threshold: threshold,
        masks: masks
    )
}

private func computeInternalStripeContrastBatch(
    materialized batchData: MassBatchCPU,
    threshold: Float,
    useTorus: Bool,
    masks: [[Bool]]?
) -> [Float] {
    let flat = batchData.flat
    let batch = batchData.batch
    let height = batchData.height
    let width = batchData.width
    let sampleSize = batchData.sampleSize
    let pairOffsets = [(1, 0), (0, 1), (1, 1), (1, -1)]

    var scores: [Float] = []
    scores.reserveCapacity(batch)

    for sampleIndex in 0..<batch {
        let start = sampleIndex * sampleSize
        let mask = masks?[sampleIndex]
        var contrastSum: Float = 0
        var pairCount: Float = 0

        for y in 0..<height {
            for x in 0..<width {
                let idx = y * width + x
                let value = flat[start + idx]
                if value <= threshold ||
                    (mask != nil && mask![idx] == false) ||
                    occupiedNeighborCount(
                        flat: flat,
                        mask: mask,
                        offset: start,
                        width: width,
                        height: height,
                        x: x,
                        y: y,
                        threshold: threshold,
                        useTorus: useTorus
                    ) < 6 {
                    continue
                }

                for (dx, dy) in pairOffsets {
                    guard let neighborIndex = stripeNeighborIndex(
                        width: width,
                        height: height,
                        x: x,
                        y: y,
                        dx: dx,
                        dy: dy,
                        useTorus: useTorus
                    ) else {
                        continue
                    }
                    if mask != nil && mask![neighborIndex] == false {
                        continue
                    }
                    let neighborValue = flat[start + neighborIndex]
                    if neighborValue <= threshold {
                        continue
                    }
                    contrastSum += abs(value - neighborValue)
                    pairCount += 1
                }
            }
        }

        scores.append(pairCount > 0 ? contrastSum / pairCount : 0)
    }

    return scores
}

private func computeOrientedRidgeDominanceBatch(
    materialized batchData: MassBatchCPU,
    threshold: Float,
    masks: [[Bool]]?
) -> [Float] {
    let flat = batchData.flat
    let batch = batchData.batch
    let height = batchData.height
    let width = batchData.width
    let sampleSize = batchData.sampleSize

    var scores: [Float] = []
    scores.reserveCapacity(batch)

    for sampleIndex in 0..<batch {
        let start = sampleIndex * sampleSize
        let mask = masks?[sampleIndex]
        var totalMass: Float = 0
        var maxValue: Float = threshold
        for idx in 0..<sampleSize {
            if mask != nil && mask![idx] == false {
                continue
            }
            let value = flat[start + idx]
            if value <= threshold {
                continue
            }
            totalMass += value
            maxValue = max(maxValue, value)
        }
        if totalMass <= 1e-8 || maxValue <= threshold {
            scores.append(0)
            continue
        }

        let brightThreshold = threshold + 0.55 * (maxValue - threshold)
        var rowSums = [Float](repeating: 0, count: height)
        var colSums = [Float](repeating: 0, count: width)
        var diagSums = [Float](repeating: 0, count: height + width - 1)
        var antiDiagSums = [Float](repeating: 0, count: height + width - 1)
        var rowCounts = [Int](repeating: 0, count: height)
        var colCounts = [Int](repeating: 0, count: width)
        var diagCounts = [Int](repeating: 0, count: height + width - 1)
        var antiDiagCounts = [Int](repeating: 0, count: height + width - 1)
        var brightMass: Float = 0

        for y in 0..<height {
            for x in 0..<width {
                let idx = y * width + x
                if mask != nil && mask![idx] == false {
                    continue
                }
                let value = flat[start + idx]
                guard value > brightThreshold else {
                    continue
                }
                let mass = value - brightThreshold
                let diag = y - x + width - 1
                let antiDiag = y + x
                brightMass += mass
                rowSums[y] += mass
                colSums[x] += mass
                diagSums[diag] += mass
                antiDiagSums[antiDiag] += mass
                rowCounts[y] += 1
                colCounts[x] += 1
                diagCounts[diag] += 1
                antiDiagCounts[antiDiag] += 1
            }
        }

        if brightMass <= 1e-8 {
            scores.append(0)
            continue
        }

        let candidates = [
            maxLineDominance(sums: rowSums, counts: rowCounts, brightMass: brightMass),
            maxLineDominance(sums: colSums, counts: colCounts, brightMass: brightMass),
            maxLineDominance(sums: diagSums, counts: diagCounts, brightMass: brightMass),
            maxLineDominance(sums: antiDiagSums, counts: antiDiagCounts, brightMass: brightMass),
        ]
        scores.append(candidates.max() ?? 0)
    }

    return scores
}

private func largestComponentMasks(
    materialized batchData: MassBatchCPU,
    threshold: Float,
    useTorus: Bool
) -> [[Bool]] {
    let flat = batchData.flat
    let batch = batchData.batch
    let height = batchData.height
    let width = batchData.width
    let sampleSize = batchData.sampleSize

    var result: [[Bool]] = []
    result.reserveCapacity(batch)

    for sampleIndex in 0..<batch {
        let start = sampleIndex * sampleSize
        var visited = [Bool](repeating: false, count: sampleSize)
        var bestMask = [Bool](repeating: false, count: sampleSize)
        var bestMass: Float = 0

        for y in 0..<height {
            for x in 0..<width {
                let idx = y * width + x
                if visited[idx] || flat[start + idx] <= threshold {
                    continue
                }

                visited[idx] = true
                var queue = [(x: x, y: y)]
                var componentIndices: [Int] = []
                var componentMass: Float = 0

                while !queue.isEmpty {
                    let current = queue.removeLast()
                    let currentIndex = current.y * width + current.x
                    componentIndices.append(currentIndex)
                    componentMass += flat[start + currentIndex]

                    for dy in -1...1 {
                        for dx in -1...1 where dx != 0 || dy != 0 {
                            guard let neighborIndex = stripeNeighborIndex(
                                width: width,
                                height: height,
                                x: current.x,
                                y: current.y,
                                dx: dx,
                                dy: dy,
                                useTorus: useTorus
                            ) else {
                                continue
                            }
                            if visited[neighborIndex] || flat[start + neighborIndex] <= threshold {
                                continue
                            }
                            visited[neighborIndex] = true
                            queue.append((x: neighborIndex % width, y: neighborIndex / width))
                        }
                    }
                }

                if componentMass > bestMass {
                    bestMass = componentMass
                    bestMask = [Bool](repeating: false, count: sampleSize)
                    for componentIndex in componentIndices {
                        bestMask[componentIndex] = true
                    }
                }
            }
        }

        result.append(bestMask)
    }

    return result
}

private func maxLineDominance(sums: [Float], counts: [Int], brightMass: Float) -> Float {
    var best: Float = 0
    for index in sums.indices {
        guard sums[index] > 0 else {
            continue
        }
        let concentration = sums[index] / brightMass
        let support = min(1, Float(counts[index]) / 8.0)
        best = max(best, concentration * support)
    }
    return best
}

private func occupiedNeighborCount(
    flat: [Float],
    mask: [Bool]? = nil,
    offset: Int,
    width: Int,
    height: Int,
    x: Int,
    y: Int,
    threshold: Float,
    useTorus: Bool
) -> Int {
    var count = 0
    for dy in -1...1 {
        for dx in -1...1 where dx != 0 || dy != 0 {
            guard let neighborIndex = stripeNeighborIndex(
                width: width,
                height: height,
                x: x,
                y: y,
                dx: dx,
                dy: dy,
                useTorus: useTorus
            ) else {
                continue
            }
            if mask != nil && mask![neighborIndex] == false {
                continue
            }
            if flat[offset + neighborIndex] > threshold {
                count += 1
            }
        }
    }
    return count
}

private func stripeNeighborIndex(
    width: Int,
    height: Int,
    x: Int,
    y: Int,
    dx: Int,
    dy: Int,
    useTorus: Bool
) -> Int? {
    var nx = x + dx
    var ny = y + dy
    if useTorus {
        nx = (nx + width) % width
        ny = (ny + height) % height
    } else if nx < 0 || ny < 0 || nx >= width || ny >= height {
        return nil
    }
    return ny * width + nx
}
