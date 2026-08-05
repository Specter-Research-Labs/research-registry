import Foundation

struct CoherentTransportBatchResult: Sendable {
    let displacement: [Float]
    let translatedShapeOverlap: [Float]
    let coherentTransport: [Float]
}

func computeCoherentTransportBatch(
    source: MassBatchCPU,
    target: MassBatchCPU,
    threshold: Float,
    useTorus: Bool
) -> CoherentTransportBatchResult {
    guard source.batch == target.batch,
          source.height == target.height,
          source.width == target.width else {
        fatalError("Coherent transport requires matching source and target mass batches.")
    }

    var displacements: [Float] = []
    var overlaps: [Float] = []
    var scores: [Float] = []
    displacements.reserveCapacity(source.batch)
    overlaps.reserveCapacity(source.batch)
    scores.reserveCapacity(source.batch)

    let rowPhases = useTorus ? CircularCoordinateLookup(count: source.height) : nil
    let colPhases = useTorus ? CircularCoordinateLookup(count: source.width) : nil

    for sampleIndex in 0..<source.batch {
        let sourceCenter = massCenter(
            materialized: source,
            sampleIndex: sampleIndex,
            rowPhases: rowPhases,
            colPhases: colPhases
        )
        let targetCenter = massCenter(
            materialized: target,
            sampleIndex: sampleIndex,
            rowPhases: rowPhases,
            colPhases: colPhases
        )
        guard sourceCenter.alive, targetCenter.alive else {
            displacements.append(0)
            overlaps.append(0)
            scores.append(0)
            continue
        }

        var rowDelta = targetCenter.row - sourceCenter.row
        var colDelta = targetCenter.col - sourceCenter.col
        if useTorus {
            let halfHeight = Float(source.height) * 0.5
            let halfWidth = Float(source.width) * 0.5
            if rowDelta > halfHeight { rowDelta -= Float(source.height) }
            if rowDelta < -halfHeight { rowDelta += Float(source.height) }
            if colDelta > halfWidth { colDelta -= Float(source.width) }
            if colDelta < -halfWidth { colDelta += Float(source.width) }
        }

        let displacement = sqrt(rowDelta * rowDelta + colDelta * colDelta)
        let overlap = translatedMaskOverlap(
            source: source,
            target: target,
            sampleIndex: sampleIndex,
            rowShift: Int(rowDelta.rounded()),
            colShift: Int(colDelta.rounded()),
            threshold: threshold,
            useTorus: useTorus
        )
        displacements.append(displacement)
        overlaps.append(overlap)
        scores.append(displacement * overlap)
    }

    return CoherentTransportBatchResult(
        displacement: displacements,
        translatedShapeOverlap: overlaps,
        coherentTransport: scores
    )
}

private func massCenter(
    materialized batch: MassBatchCPU,
    sampleIndex: Int,
    rowPhases: CircularCoordinateLookup?,
    colPhases: CircularCoordinateLookup?
) -> (alive: Bool, row: Float, col: Float) {
    let start = sampleIndex * batch.sampleSize
    var mass: Float = 0
    var rowSum: Float = 0
    var colSum: Float = 0
    var rowSinSum: Float = 0
    var rowCosSum: Float = 0
    var colSinSum: Float = 0
    var colCosSum: Float = 0
    for row in 0..<batch.height {
        for col in 0..<batch.width {
            let value = batch.flat[start + row * batch.width + col]
            if value <= 0 { continue }
            mass += value
            if let rowPhases, let colPhases {
                rowSinSum += rowPhases.sine[row] * value
                rowCosSum += rowPhases.cosine[row] * value
                colSinSum += colPhases.sine[col] * value
                colCosSum += colPhases.cosine[col] * value
            } else {
                rowSum += Float(row) * value
                colSum += Float(col) * value
            }
        }
    }
    guard mass > 1e-12 else {
        return (false, 0, 0)
    }
    if rowPhases != nil, colPhases != nil {
        return (
            true,
            circularCoordinate(sine: rowSinSum, cosine: rowCosSum, count: batch.height),
            circularCoordinate(sine: colSinSum, cosine: colCosSum, count: batch.width)
        )
    }
    return (true, rowSum / mass, colSum / mass)
}

private struct CircularCoordinateLookup {
    let sine: [Float]
    let cosine: [Float]

    init(count: Int) {
        let scale = 2 * Float.pi / Float(count)
        sine = (0..<count).map { sinf(Float($0) * scale) }
        cosine = (0..<count).map { cosf(Float($0) * scale) }
    }
}

private func circularCoordinate(sine: Float, cosine: Float, count: Int) -> Float {
    let twoPi = 2 * Float.pi
    let angle = atan2f(sine, cosine)
    return (angle < 0 ? angle + twoPi : angle) / twoPi * Float(count)
}

private func translatedMaskOverlap(
    source: MassBatchCPU,
    target: MassBatchCPU,
    sampleIndex: Int,
    rowShift: Int,
    colShift: Int,
    threshold: Float,
    useTorus: Bool
) -> Float {
    let sourceStart = sampleIndex * source.sampleSize
    let targetStart = sampleIndex * target.sampleSize
    var sourceCount = 0
    for index in 0..<source.sampleSize where source.flat[sourceStart + index] > threshold {
        sourceCount += 1
    }
    guard sourceCount > 0 else { return 0 }

    var targetCount = 0
    for index in 0..<target.sampleSize where target.flat[targetStart + index] > threshold {
        targetCount += 1
    }
    guard targetCount > 0 else { return 0 }

    var best: Float = 0
    let localSearchRadius = 2
    for rowDelta in (-localSearchRadius)...localSearchRadius {
        for colDelta in (-localSearchRadius)...localSearchRadius {
            var intersection = 0
            for row in 0..<source.height {
                for col in 0..<source.width {
                    let sourceIndex = sourceStart + row * source.width + col
                    guard source.flat[sourceIndex] > threshold else { continue }

                    var targetRow = row + rowShift + rowDelta
                    var targetCol = col + colShift + colDelta
                    if useTorus {
                        targetRow = (targetRow % target.height + target.height) % target.height
                        targetCol = (targetCol % target.width + target.width) % target.width
                    } else if targetRow < 0 || targetCol < 0 || targetRow >= target.height || targetCol >= target.width {
                        continue
                    }

                    let targetIndex = targetStart + targetRow * target.width + targetCol
                    if target.flat[targetIndex] > threshold {
                        intersection += 1
                    }
                }
            }
            let union = sourceCount + targetCount - intersection
            if union > 0 {
                best = max(best, Float(intersection) / Float(union))
            }
        }
    }
    return best
}
