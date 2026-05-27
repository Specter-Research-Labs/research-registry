import Foundation

struct MassTemplate: Sendable {
    let flat: [Float]
    let height: Int
    let width: Int
    let mass: Float
    let support: Int
    let centerRow: Float
    let centerCol: Float
}

func makeStatePatchMassTemplate(
    statePatch: InitStatePatchConfig,
    gridHeight: Int,
    gridWidth: Int,
    includedChannels: [Int],
    threshold: Float
) -> MassTemplate {
    let values = statePatch.decodedValues()
    precondition(statePatch.center.count >= 2, "init.state_patch.center must have x/y coordinates.")
    precondition(
        values.count == statePatch.width * statePatch.height * statePatch.channels,
        "init.state_patch.data length must match width*height*channels."
    )

    let centerRow = statePatch.center[0]
    let centerCol = statePatch.center[1]
    let halfHeight = statePatch.width / 2
    let halfWidth = statePatch.height / 2
    let row0 = centerRow - halfHeight
    let row1 = centerRow + (statePatch.width - halfHeight)
    let col0 = centerCol - halfWidth
    let col1 = centerCol + (statePatch.height - halfWidth)
    precondition(
        row0 >= 0 && col0 >= 0 && row1 <= gridHeight && col1 <= gridWidth,
        "init.state_patch bounds must fit within the ES runtime grid."
    )

    let channels = Set(includedChannels)
    var flat = [Float](repeating: 0, count: gridHeight * gridWidth)
    var patchIndex = 0
    var support = 0
    for row in row0..<row1 {
        for col in col0..<col1 {
            var mass: Float = 0
            for channel in 0..<statePatch.channels {
                let value = values[patchIndex]
                if channels.contains(channel) {
                    mass += value
                }
                patchIndex += 1
            }
            if mass > threshold {
                flat[row * gridWidth + col] = mass
                support += 1
            }
        }
    }

    let center = weightedCenter(flat: flat, offset: 0, height: gridHeight, width: gridWidth)
    return MassTemplate(
        flat: flat,
        height: gridHeight,
        width: gridWidth,
        mass: center.mass,
        support: support,
        centerRow: center.row,
        centerCol: center.col
    )
}

func computeTemplateSimilarityBatch(
    materialized batchData: MassBatchCPU,
    template: MassTemplate,
    threshold: Float,
    useTorus: Bool
) -> [Float] {
    precondition(batchData.height == template.height, "template height must match mass map height.")
    precondition(batchData.width == template.width, "template width must match mass map width.")
    guard template.mass > 1e-8 else {
        return [Float](repeating: 0, count: batchData.batch)
    }

    let flat = batchData.flat
    var scores: [Float] = []
    scores.reserveCapacity(batchData.batch)

    for sampleIndex in 0..<batchData.batch {
        let offset = sampleIndex * batchData.sampleSize
        let center = weightedCenter(
            flat: flat,
            offset: offset,
            height: batchData.height,
            width: batchData.width,
            threshold: threshold
        )
        guard center.mass > 1e-8 else {
            scores.append(0)
            continue
        }

        let rowShift = Int(round(center.row - template.centerRow))
        let colShift = Int(round(center.col - template.centerCol))
        var l1: Float = 0

        for row in 0..<batchData.height {
            for col in 0..<batchData.width {
                let templateValue = template.flat[row * batchData.width + col] / template.mass
                let sampleRow = row + rowShift
                let sampleCol = col + colShift
                let sampleIndex = shiftedIndex(
                    row: sampleRow,
                    col: sampleCol,
                    height: batchData.height,
                    width: batchData.width,
                    useTorus: useTorus
                )
                let sampleValue: Float
                if let sampleIndex {
                    let raw = flat[offset + sampleIndex]
                    sampleValue = raw > threshold ? raw / center.mass : 0
                } else {
                    sampleValue = 0
                }
                l1 += abs(templateValue - sampleValue)
            }
        }

        scores.append(max(0, min(1, 1 - 0.5 * l1)))
    }

    return scores
}

func computeTemplateMassMismatchBatch(
    materialized batchData: MassBatchCPU,
    template: MassTemplate,
    threshold: Float
) -> [Float] {
    precondition(batchData.height == template.height, "template height must match mass map height.")
    precondition(batchData.width == template.width, "template width must match mass map width.")

    let flat = batchData.flat
    var scores: [Float] = []
    scores.reserveCapacity(batchData.batch)

    for sampleIndex in 0..<batchData.batch {
        let offset = sampleIndex * batchData.sampleSize
        let center = weightedCenter(
            flat: flat,
            offset: offset,
            height: batchData.height,
            width: batchData.width,
            threshold: threshold
        )
        if template.mass <= 1e-8 {
            scores.append(center.mass <= 1e-8 ? 0 : 1)
            continue
        }
        guard center.mass > 1e-8 else {
            scores.append(1)
            continue
        }

        let ratio = max(center.mass / template.mass, 1e-8)
        let massMatch = min(ratio, 1 / ratio)
        scores.append(1 - max(0, min(1, massMatch)))
    }

    return scores
}

func computeTemplateSupportMismatchBatch(
    materialized batchData: MassBatchCPU,
    template: MassTemplate,
    threshold: Float
) -> [Float] {
    precondition(batchData.height == template.height, "template height must match mass map height.")
    precondition(batchData.width == template.width, "template width must match mass map width.")

    let flat = batchData.flat
    var scores: [Float] = []
    scores.reserveCapacity(batchData.batch)

    for sampleIndex in 0..<batchData.batch {
        let offset = sampleIndex * batchData.sampleSize
        var support = 0
        for index in 0..<batchData.sampleSize where flat[offset + index] > threshold {
            support += 1
        }

        if template.support == 0 {
            scores.append(support == 0 ? 0 : 1)
            continue
        }
        guard support > 0 else {
            scores.append(1)
            continue
        }

        let ratio = max(Float(support) / Float(template.support), 1e-8)
        let supportMatch = min(ratio, 1 / ratio)
        scores.append(1 - max(0, min(1, supportMatch)))
    }

    return scores
}

func computeTemplateChangeMismatchBatch(
    previous: MassBatchCPU,
    current: MassBatchCPU,
    previousTemplate: MassTemplate,
    currentTemplate: MassTemplate,
    threshold: Float
) -> [Float] {
    precondition(previous.batch == current.batch, "template change batches must have matching batch sizes.")
    precondition(previous.height == current.height, "template change batches must have matching heights.")
    precondition(previous.width == current.width, "template change batches must have matching widths.")
    precondition(previous.height == previousTemplate.height, "previous template height must match mass map height.")
    precondition(previous.width == previousTemplate.width, "previous template width must match mass map width.")
    precondition(current.height == currentTemplate.height, "current template height must match mass map height.")
    precondition(current.width == currentTemplate.width, "current template width must match mass map width.")

    let templateChange = temporalChangeMagnitude(
        previous: previousTemplate.flat,
        current: currentTemplate.flat,
        threshold: threshold
    )
    var scores: [Float] = []
    scores.reserveCapacity(current.batch)

    for sampleIndex in 0..<current.batch {
        let previousOffset = sampleIndex * previous.sampleSize
        let currentOffset = sampleIndex * current.sampleSize
        let sampleChange = temporalChangeMagnitude(
            previous: previous.flat,
            previousOffset: previousOffset,
            current: current.flat,
            currentOffset: currentOffset,
            count: current.sampleSize,
            threshold: threshold
        )

        if templateChange <= 1e-8 {
            scores.append(sampleChange <= 1e-8 ? 0 : 1)
            continue
        }
        guard sampleChange > 1e-8 else {
            scores.append(1)
            continue
        }

        let ratio = max(sampleChange / templateChange, 1e-8)
        let changeMatch = min(ratio, 1 / ratio)
        scores.append(1 - max(0, min(1, changeMatch)))
    }

    return scores
}

func computeTemplateDeltaSimilarityBatch(
    previous: MassBatchCPU,
    current: MassBatchCPU,
    previousTemplate: MassTemplate,
    currentTemplate: MassTemplate,
    threshold: Float,
    useTorus: Bool
) -> [Float] {
    precondition(previous.batch == current.batch, "template delta batches must have matching batch sizes.")
    precondition(previous.height == current.height, "template delta batches must have matching heights.")
    precondition(previous.width == current.width, "template delta batches must have matching widths.")
    precondition(previous.height == previousTemplate.height, "previous template height must match mass map height.")
    precondition(previous.width == previousTemplate.width, "previous template width must match mass map width.")
    precondition(current.height == currentTemplate.height, "current template height must match mass map height.")
    precondition(current.width == currentTemplate.width, "current template width must match mass map width.")

    let templateDelta = temporalDeltaMap(
        previous: previousTemplate.flat,
        current: currentTemplate.flat,
        threshold: threshold
    )
    let templateCenter = weightedCenter(
        flat: templateDelta,
        offset: 0,
        height: current.height,
        width: current.width
    )
    guard templateCenter.mass > 1e-8 else {
        return [Float](repeating: 0, count: current.batch)
    }

    var scores: [Float] = []
    scores.reserveCapacity(current.batch)
    var sampleDelta = [Float](repeating: 0, count: current.sampleSize)

    for sampleIndex in 0..<current.batch {
        let previousOffset = sampleIndex * previous.sampleSize
        let currentOffset = sampleIndex * current.sampleSize
        fillTemporalDeltaMap(
            previous: previous.flat,
            previousOffset: previousOffset,
            current: current.flat,
            currentOffset: currentOffset,
            output: &sampleDelta,
            threshold: threshold
        )
        let sampleCenter = weightedCenter(
            flat: sampleDelta,
            offset: 0,
            height: current.height,
            width: current.width
        )
        guard sampleCenter.mass > 1e-8 else {
            scores.append(0)
            continue
        }

        let rowShift = Int(round(sampleCenter.row - templateCenter.row))
        let colShift = Int(round(sampleCenter.col - templateCenter.col))
        var l1: Float = 0
        for row in 0..<current.height {
            for col in 0..<current.width {
                let templateValue = templateDelta[row * current.width + col] / templateCenter.mass
                let sampleRow = row + rowShift
                let sampleCol = col + colShift
                let shifted = shiftedIndex(
                    row: sampleRow,
                    col: sampleCol,
                    height: current.height,
                    width: current.width,
                    useTorus: useTorus
                )
                let sampleValue: Float
                if let shifted {
                    sampleValue = sampleDelta[shifted] / sampleCenter.mass
                } else {
                    sampleValue = 0
                }
                l1 += abs(templateValue - sampleValue)
            }
        }
        scores.append(max(0, min(1, 1 - 0.5 * l1)))
    }

    return scores
}

func computeTemplateSignedDeltaSimilarityBatch(
    previous: MassBatchCPU,
    current: MassBatchCPU,
    previousTemplate: MassTemplate,
    currentTemplate: MassTemplate,
    threshold: Float,
    useTorus: Bool
) -> [Float] {
    precondition(previous.batch == current.batch, "template signed-delta batches must have matching batch sizes.")
    precondition(previous.height == current.height, "template signed-delta batches must have matching heights.")
    precondition(previous.width == current.width, "template signed-delta batches must have matching widths.")
    precondition(previous.height == previousTemplate.height, "previous template height must match mass map height.")
    precondition(previous.width == previousTemplate.width, "previous template width must match mass map width.")
    precondition(current.height == currentTemplate.height, "current template height must match mass map height.")
    precondition(current.width == currentTemplate.width, "current template width must match mass map width.")

    let templateDelta = temporalSignedDeltaMaps(
        previous: previousTemplate.flat,
        current: currentTemplate.flat,
        threshold: threshold
    )
    let templateMass = templateDelta.combined.reduce(0, +)
    guard templateMass > 1e-8 else {
        return [Float](repeating: 0, count: current.batch)
    }
    let templateCenter = weightedCenter(
        flat: templateDelta.combined,
        offset: 0,
        height: current.height,
        width: current.width
    )

    var scores: [Float] = []
    scores.reserveCapacity(current.batch)
    var sampleBirth = [Float](repeating: 0, count: current.sampleSize)
    var sampleDeath = [Float](repeating: 0, count: current.sampleSize)
    var sampleCombined = [Float](repeating: 0, count: current.sampleSize)

    for sampleIndex in 0..<current.batch {
        let previousOffset = sampleIndex * previous.sampleSize
        let currentOffset = sampleIndex * current.sampleSize
        fillTemporalSignedDeltaMaps(
            previous: previous.flat,
            previousOffset: previousOffset,
            current: current.flat,
            currentOffset: currentOffset,
            birth: &sampleBirth,
            death: &sampleDeath,
            combined: &sampleCombined,
            threshold: threshold
        )
        let sampleMass = sampleCombined.reduce(0, +)
        guard sampleMass > 1e-8 else {
            scores.append(0)
            continue
        }
        let sampleCenter = weightedCenter(
            flat: sampleCombined,
            offset: 0,
            height: current.height,
            width: current.width
        )

        let rowShift = Int(round(sampleCenter.row - templateCenter.row))
        let colShift = Int(round(sampleCenter.col - templateCenter.col))
        var l1: Float = 0
        for row in 0..<current.height {
            for col in 0..<current.width {
                let flatIndex = row * current.width + col
                let templateBirth = templateDelta.birth[flatIndex] / templateMass
                let templateDeath = templateDelta.death[flatIndex] / templateMass
                let shifted = shiftedIndex(
                    row: row + rowShift,
                    col: col + colShift,
                    height: current.height,
                    width: current.width,
                    useTorus: useTorus
                )
                let sampleBirthValue: Float
                let sampleDeathValue: Float
                if let shifted {
                    sampleBirthValue = sampleBirth[shifted] / sampleMass
                    sampleDeathValue = sampleDeath[shifted] / sampleMass
                } else {
                    sampleBirthValue = 0
                    sampleDeathValue = 0
                }
                l1 += abs(templateBirth - sampleBirthValue)
                l1 += abs(templateDeath - sampleDeathValue)
            }
        }
        scores.append(max(0, min(1, 1 - 0.5 * l1)))
    }

    return scores
}

private func weightedCenter(
    flat: [Float],
    offset: Int,
    height: Int,
    width: Int,
    threshold: Float = 0
) -> (mass: Float, row: Float, col: Float) {
    var mass: Float = 0
    var rowSum: Float = 0
    var colSum: Float = 0

    for row in 0..<height {
        for col in 0..<width {
            let value = flat[offset + row * width + col]
            if value <= threshold {
                continue
            }
            mass += value
            rowSum += Float(row) * value
            colSum += Float(col) * value
        }
    }

    if mass <= 1e-8 {
        return (0, 0, 0)
    }
    return (mass, rowSum / mass, colSum / mass)
}

private func shiftedIndex(
    row: Int,
    col: Int,
    height: Int,
    width: Int,
    useTorus: Bool
) -> Int? {
    var shiftedRow = row
    var shiftedCol = col
    if useTorus {
        shiftedRow = (shiftedRow + height) % height
        shiftedCol = (shiftedCol + width) % width
    } else if shiftedRow < 0 || shiftedCol < 0 || shiftedRow >= height || shiftedCol >= width {
        return nil
    }
    return shiftedRow * width + shiftedCol
}

private func temporalChangeMagnitude(
    previous: [Float],
    current: [Float],
    threshold: Float
) -> Float {
    precondition(previous.count == current.count, "template frames must have matching dimensions.")
    return temporalChangeMagnitude(
        previous: previous,
        previousOffset: 0,
        current: current,
        currentOffset: 0,
        count: current.count,
        threshold: threshold
    )
}

private func temporalChangeMagnitude(
    previous: [Float],
    previousOffset: Int,
    current: [Float],
    currentOffset: Int,
    count: Int,
    threshold: Float
) -> Float {
    var change: Float = 0
    for index in 0..<count {
        let previousValue = previous[previousOffset + index]
        let currentValue = current[currentOffset + index]
        let previousMass = previousValue > threshold ? previousValue : 0
        let currentMass = currentValue > threshold ? currentValue : 0
        change += abs(currentMass - previousMass)
    }
    return change
}

private func temporalDeltaMap(
    previous: [Float],
    current: [Float],
    threshold: Float
) -> [Float] {
    precondition(previous.count == current.count, "template frames must have matching dimensions.")
    var output = [Float](repeating: 0, count: current.count)
    fillTemporalDeltaMap(
        previous: previous,
        previousOffset: 0,
        current: current,
        currentOffset: 0,
        output: &output,
        threshold: threshold
    )
    return output
}

private func fillTemporalDeltaMap(
    previous: [Float],
    previousOffset: Int,
    current: [Float],
    currentOffset: Int,
    output: inout [Float],
    threshold: Float
) {
    for index in output.indices {
        let previousValue = previous[previousOffset + index]
        let currentValue = current[currentOffset + index]
        let previousMass = previousValue > threshold ? previousValue : 0
        let currentMass = currentValue > threshold ? currentValue : 0
        output[index] = abs(currentMass - previousMass)
    }
}

private func temporalSignedDeltaMaps(
    previous: [Float],
    current: [Float],
    threshold: Float
) -> (birth: [Float], death: [Float], combined: [Float]) {
    precondition(previous.count == current.count, "template frames must have matching dimensions.")
    var birth = [Float](repeating: 0, count: current.count)
    var death = [Float](repeating: 0, count: current.count)
    var combined = [Float](repeating: 0, count: current.count)
    fillTemporalSignedDeltaMaps(
        previous: previous,
        previousOffset: 0,
        current: current,
        currentOffset: 0,
        birth: &birth,
        death: &death,
        combined: &combined,
        threshold: threshold
    )
    return (birth, death, combined)
}

private func fillTemporalSignedDeltaMaps(
    previous: [Float],
    previousOffset: Int,
    current: [Float],
    currentOffset: Int,
    birth: inout [Float],
    death: inout [Float],
    combined: inout [Float],
    threshold: Float
) {
    precondition(birth.count == death.count, "signed-delta output maps must match.")
    precondition(birth.count == combined.count, "signed-delta output maps must match.")
    for index in birth.indices {
        let previousValue = previous[previousOffset + index]
        let currentValue = current[currentOffset + index]
        let previousMass = previousValue > threshold ? previousValue : 0
        let currentMass = currentValue > threshold ? currentValue : 0
        let born = max(currentMass - previousMass, 0)
        let died = max(previousMass - currentMass, 0)
        birth[index] = born
        death[index] = died
        combined[index] = born + died
    }
}
