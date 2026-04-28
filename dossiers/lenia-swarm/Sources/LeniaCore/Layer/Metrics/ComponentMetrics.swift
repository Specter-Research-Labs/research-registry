import Foundation

struct ComponentMetricsBatchResult: Sendable {
    let count: [Float]
    let largestFraction: [Float]
    let largestAnisotropy: [Float]
}

struct ComponentStructureBatchResult: Sendable {
    let count: [Float]
    let significantCount: [Float]
    let largestFraction: [Float]
    let largestAnisotropy: [Float]
    let significantMassFraction: [Float]
}

func computeComponentMetricsBatch(
    materialized batchData: MassBatchCPU,
    threshold: Float,
    useTorus: Bool
) -> ComponentMetricsBatchResult {
    let flat = batchData.flat
    let batch = batchData.batch
    let height = batchData.height
    let width = batchData.width
    let sampleSize = batchData.sampleSize

    var counts: [Float] = []
    var largestFractions: [Float] = []
    var largestAnisotropies: [Float] = []
    counts.reserveCapacity(batch)
    largestFractions.reserveCapacity(batch)
    largestAnisotropies.reserveCapacity(batch)

    for sampleIndex in 0..<batch {
        let start = sampleIndex * sampleSize
        var visited = [Bool](repeating: false, count: sampleSize)
        var componentCount = 0
        var totalMass: Float = 0
        var largestMass: Float = 0
        var largestAnisotropy: Float = 0

        for y in 0..<height {
            for x in 0..<width {
                let idx = y * width + x
                let mass = flat[start + idx]
                if visited[idx] || mass <= threshold {
                    continue
                }

                visited[idx] = true
                var queue = [(x: x, y: y, ux: 0, uy: 0)]
                var componentMass: Float = 0
                var sumUx: Float = 0
                var sumUy: Float = 0
                var sumUx2: Float = 0
                var sumUxUy: Float = 0
                var sumUy2: Float = 0

                while !queue.isEmpty {
                    let current = queue.removeLast()
                    let cx = current.x
                    let cy = current.y
                    let currentIndex = cy * width + cx
                    let currentMass = flat[start + currentIndex]
                    componentMass += currentMass
                    let ux = Float(current.ux)
                    let uy = Float(current.uy)
                    sumUx += currentMass * ux
                    sumUy += currentMass * uy
                    sumUx2 += currentMass * ux * ux
                    sumUxUy += currentMass * ux * uy
                    sumUy2 += currentMass * uy * uy

                    for (dx, dy) in componentNeighborOffsets {
                        var nx = cx + dx
                        var ny = cy + dy
                        if useTorus {
                            nx = (nx + width) % width
                            ny = (ny + height) % height
                        } else if nx < 0 || ny < 0 || nx >= width || ny >= height {
                            continue
                        }

                        let neighborIndex = ny * width + nx
                        if visited[neighborIndex] || flat[start + neighborIndex] <= threshold {
                            continue
                        }
                        visited[neighborIndex] = true
                        queue.append((x: nx, y: ny, ux: current.ux + dx, uy: current.uy + dy))
                    }
                }

                componentCount += 1
                totalMass += componentMass
                if componentMass > largestMass {
                    largestMass = componentMass
                    largestAnisotropy = componentAnisotropy(
                        mass: componentMass,
                        sumX: sumUx,
                        sumY: sumUy,
                        sumXX: sumUx2,
                        sumXY: sumUxUy,
                        sumYY: sumUy2
                    )
                }
            }
        }

        counts.append(Float(componentCount))
        largestFractions.append(totalMass > 0 ? largestMass / totalMass : 0)
        largestAnisotropies.append(largestAnisotropy)
    }

    return ComponentMetricsBatchResult(
        count: counts,
        largestFraction: largestFractions,
        largestAnisotropy: largestAnisotropies
    )
}

func computeComponentStructureBatch(
    materialized batchData: MassBatchCPU,
    threshold: Float,
    useTorus: Bool,
    significantMassMinimum: Float,
    significantMassFraction: Float
) -> ComponentStructureBatchResult {
    let flat = batchData.flat
    let batch = batchData.batch
    let height = batchData.height
    let width = batchData.width
    let sampleSize = batchData.sampleSize

    var counts: [Float] = []
    var significantCounts: [Float] = []
    var largestFractions: [Float] = []
    var largestAnisotropies: [Float] = []
    var significantMassFractions: [Float] = []
    counts.reserveCapacity(batch)
    significantCounts.reserveCapacity(batch)
    largestFractions.reserveCapacity(batch)
    largestAnisotropies.reserveCapacity(batch)
    significantMassFractions.reserveCapacity(batch)

    for sampleIndex in 0..<batch {
        let start = sampleIndex * sampleSize
        var visited = [Bool](repeating: false, count: sampleSize)
        var componentCount = 0
        var totalMass: Float = 0
        var largestMass: Float = 0
        var largestAnisotropy: Float = 0
        var componentMasses: [Float] = []

        for y in 0..<height {
            for x in 0..<width {
                let idx = y * width + x
                let mass = flat[start + idx]
                if visited[idx] || mass <= threshold {
                    continue
                }

                visited[idx] = true
                var queue = [(x: x, y: y, ux: 0, uy: 0)]
                var componentMass: Float = 0
                var sumUx: Float = 0
                var sumUy: Float = 0
                var sumUx2: Float = 0
                var sumUxUy: Float = 0
                var sumUy2: Float = 0

                while !queue.isEmpty {
                    let current = queue.removeLast()
                    let cx = current.x
                    let cy = current.y
                    let currentIndex = cy * width + cx
                    let currentMass = flat[start + currentIndex]
                    componentMass += currentMass
                    let ux = Float(current.ux)
                    let uy = Float(current.uy)
                    sumUx += currentMass * ux
                    sumUy += currentMass * uy
                    sumUx2 += currentMass * ux * ux
                    sumUxUy += currentMass * ux * uy
                    sumUy2 += currentMass * uy * uy

                    for (dx, dy) in componentNeighborOffsets {
                        var nx = cx + dx
                        var ny = cy + dy
                        if useTorus {
                            nx = (nx + width) % width
                            ny = (ny + height) % height
                        } else if nx < 0 || ny < 0 || nx >= width || ny >= height {
                            continue
                        }

                        let neighborIndex = ny * width + nx
                        if visited[neighborIndex] || flat[start + neighborIndex] <= threshold {
                            continue
                        }
                        visited[neighborIndex] = true
                        queue.append((x: nx, y: ny, ux: current.ux + dx, uy: current.uy + dy))
                    }
                }

                componentCount += 1
                totalMass += componentMass
                componentMasses.append(componentMass)
                if componentMass > largestMass {
                    largestMass = componentMass
                    largestAnisotropy = componentAnisotropy(
                        mass: componentMass,
                        sumX: sumUx,
                        sumY: sumUy,
                        sumXX: sumUx2,
                        sumXY: sumUxUy,
                        sumYY: sumUy2
                    )
                }
            }
        }

        let significanceThreshold = max(significantMassMinimum, totalMass * significantMassFraction)
        let significantMasses = componentMasses.filter { $0 >= significanceThreshold }
        let significantMass = significantMasses.reduce(0, +)

        counts.append(Float(componentCount))
        significantCounts.append(Float(significantMasses.count))
        largestFractions.append(totalMass > 0 ? largestMass / totalMass : 0)
        largestAnisotropies.append(largestAnisotropy)
        significantMassFractions.append(totalMass > 0 ? significantMass / totalMass : 0)
    }

    return ComponentStructureBatchResult(
        count: counts,
        significantCount: significantCounts,
        largestFraction: largestFractions,
        largestAnisotropy: largestAnisotropies,
        significantMassFraction: significantMassFractions
    )
}

private let componentNeighborOffsets = buildComponentNeighborOffsets()

private func buildComponentNeighborOffsets() -> [(Int, Int)] {
    var offsets: [(Int, Int)] = []
    for dy in -1...1 {
        for dx in -1...1 where !(dx == 0 && dy == 0) {
            offsets.append((dx, dy))
        }
    }
    return offsets
}

private func componentAnisotropy(
    mass: Float,
    sumX: Float,
    sumY: Float,
    sumXX: Float,
    sumXY: Float,
    sumYY: Float
) -> Float {
    if mass <= 1e-12 { return 0 }
    let meanX = sumX / mass
    let meanY = sumY / mass
    let covXX = max(sumXX / mass - meanX * meanX, 0)
    let covXY = sumXY / mass - meanX * meanY
    let covYY = max(sumYY / mass - meanY * meanY, 0)
    let trace = covXX + covYY
    if trace <= 1e-12 { return 0 }
    let discSquared = max((covXX - covYY) * (covXX - covYY) + 4 * covXY * covXY, 0)
    let disc = sqrt(discSquared)
    return min(max(disc / trace, 0), 1)
}
