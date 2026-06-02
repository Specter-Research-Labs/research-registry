import Foundation

struct ComponentMetricsBatchResult: Sendable {
    let count: [Float]
    let largestFraction: [Float]
    let largestAnisotropy: [Float]
    let massEvenness: [Float]
    let largestSolidity: [Float]
    let largestMeanThickness: [Float]
    let largestMaxThickness: [Float]
    let largestFilamentarity: [Float]
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
    var massEvennesses: [Float] = []
    var largestSolidities: [Float] = []
    var largestMeanThicknesses: [Float] = []
    var largestMaxThicknesses: [Float] = []
    var largestFilamentarities: [Float] = []
    counts.reserveCapacity(batch)
    largestFractions.reserveCapacity(batch)
    largestAnisotropies.reserveCapacity(batch)
    massEvennesses.reserveCapacity(batch)
    largestSolidities.reserveCapacity(batch)
    largestMeanThicknesses.reserveCapacity(batch)
    largestMaxThicknesses.reserveCapacity(batch)
    largestFilamentarities.reserveCapacity(batch)

    for sampleIndex in 0..<batch {
        let start = sampleIndex * sampleSize
        var visited = [Bool](repeating: false, count: sampleSize)
        var componentCount = 0
        var totalMass: Float = 0
        var largestMass: Float = 0
        var largestAnisotropy: Float = 0
        var componentMasses: [Float] = []
        var largestPixels: [(x: Int, y: Int)] = []

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
                var componentPixels: [(x: Int, y: Int)] = []

                while !queue.isEmpty {
                    let current = queue.removeLast()
                    let cx = current.x
                    let cy = current.y
                    let currentIndex = cy * width + cx
                    let currentMass = flat[start + currentIndex]
                    componentPixels.append((x: current.ux, y: current.uy))
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
                    largestPixels = componentPixels
                }
            }
        }

        let shape = componentShapeMetrics(pixels: largestPixels)
        counts.append(Float(componentCount))
        largestFractions.append(totalMass > 0 ? largestMass / totalMass : 0)
        largestAnisotropies.append(largestAnisotropy)
        massEvennesses.append(componentMassEvenness(componentMasses, totalMass: totalMass))
        largestSolidities.append(shape.solidity)
        largestMeanThicknesses.append(shape.meanThickness)
        largestMaxThicknesses.append(shape.maxThickness)
        largestFilamentarities.append(shape.filamentarity)
    }

    return ComponentMetricsBatchResult(
        count: counts,
        largestFraction: largestFractions,
        largestAnisotropy: largestAnisotropies,
        massEvenness: massEvennesses,
        largestSolidity: largestSolidities,
        largestMeanThickness: largestMeanThicknesses,
        largestMaxThickness: largestMaxThicknesses,
        largestFilamentarity: largestFilamentarities
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

private func componentMassEvenness(_ masses: [Float], totalMass: Float) -> Float {
    guard totalMass > 1e-12, masses.count > 1 else {
        return masses.count == 1 ? 1 : 0
    }
    var entropy: Float = 0
    for mass in masses where mass > 0 {
        let p = mass / totalMass
        entropy -= p * log(p)
    }
    let normalizer = log(Float(masses.count))
    guard normalizer > 1e-12 else { return 0 }
    return min(max(entropy / normalizer, 0), 1)
}

private struct ComponentShapeMetrics: Sendable {
    let solidity: Float
    let meanThickness: Float
    let maxThickness: Float
    let filamentarity: Float
}

private struct ComponentHullPoint {
    let x: Float
    let y: Float
}

private func componentShapeMetrics(pixels: [(x: Int, y: Int)]) -> ComponentShapeMetrics {
    guard !pixels.isEmpty else {
        return ComponentShapeMetrics(solidity: 0, meanThickness: 0, maxThickness: 0, filamentarity: 1)
    }

    let pixelArea = Float(pixels.count)
    let hullArea = max(componentConvexHullArea(pixels: pixels), pixelArea)
    let solidity = hullArea > 0 ? min(max(pixelArea / hullArea, 0), 1) : 0
    let thickness = componentThicknessStats(pixels: pixels)
    let filamentarity = 1.0 / (1.0 + max(thickness.mean - 1.0, 0.0))
    return ComponentShapeMetrics(
        solidity: solidity,
        meanThickness: thickness.mean,
        maxThickness: thickness.max,
        filamentarity: filamentarity
    )
}

private func componentConvexHullArea(pixels: [(x: Int, y: Int)]) -> Float {
    var points: [ComponentHullPoint] = []
    points.reserveCapacity(pixels.count * 4)
    for pixel in pixels {
        let x = Float(pixel.x)
        let y = Float(pixel.y)
        points.append(ComponentHullPoint(x: x - 0.5, y: y - 0.5))
        points.append(ComponentHullPoint(x: x + 0.5, y: y - 0.5))
        points.append(ComponentHullPoint(x: x - 0.5, y: y + 0.5))
        points.append(ComponentHullPoint(x: x + 0.5, y: y + 0.5))
    }
    points.sort {
        if $0.x == $1.x { return $0.y < $1.y }
        return $0.x < $1.x
    }

    var unique: [ComponentHullPoint] = []
    unique.reserveCapacity(points.count)
    for point in points {
        if let last = unique.last, last.x == point.x, last.y == point.y {
            continue
        }
        unique.append(point)
    }
    guard unique.count >= 3 else { return Float(pixels.count) }

    var lower: [ComponentHullPoint] = []
    for point in unique {
        while lower.count >= 2,
              componentCross(lower[lower.count - 2], lower[lower.count - 1], point) <= 0 {
            lower.removeLast()
        }
        lower.append(point)
    }

    var upper: [ComponentHullPoint] = []
    for point in unique.reversed() {
        while upper.count >= 2,
              componentCross(upper[upper.count - 2], upper[upper.count - 1], point) <= 0 {
            upper.removeLast()
        }
        upper.append(point)
    }

    let hull = lower.dropLast() + upper.dropLast()
    guard hull.count >= 3 else { return Float(pixels.count) }

    var area: Float = 0
    for index in hull.indices {
        let next = hull.index(after: index) == hull.endIndex ? hull.startIndex : hull.index(after: index)
        area += hull[index].x * hull[next].y - hull[next].x * hull[index].y
    }
    return abs(area) * 0.5
}

private func componentCross(
    _ origin: ComponentHullPoint,
    _ a: ComponentHullPoint,
    _ b: ComponentHullPoint
) -> Float {
    (a.x - origin.x) * (b.y - origin.y) - (a.y - origin.y) * (b.x - origin.x)
}

private func componentThicknessStats(pixels: [(x: Int, y: Int)]) -> (mean: Float, max: Float) {
    guard let minX = pixels.map(\.x).min(),
          let maxX = pixels.map(\.x).max(),
          let minY = pixels.map(\.y).min(),
          let maxY = pixels.map(\.y).max() else {
        return (0, 0)
    }

    let width = maxX - minX + 3
    let height = maxY - minY + 3
    let count = width * height
    var inside = [Bool](repeating: false, count: count)
    var distance = [Float](repeating: 0, count: count)
    let large = Float(width + height + 4)

    for pixel in pixels {
        let x = pixel.x - minX + 1
        let y = pixel.y - minY + 1
        let index = y * width + x
        inside[index] = true
        distance[index] = large
    }

    let diagonal = Float(2.0).squareRoot()
    for y in 0..<height {
        for x in 0..<width {
            let index = y * width + x
            guard inside[index] else { continue }
            if x > 0 {
                distance[index] = min(distance[index], distance[index - 1] + 1)
            }
            if y > 0 {
                distance[index] = min(distance[index], distance[index - width] + 1)
                if x > 0 {
                    distance[index] = min(distance[index], distance[index - width - 1] + diagonal)
                }
                if x + 1 < width {
                    distance[index] = min(distance[index], distance[index - width + 1] + diagonal)
                }
            }
        }
    }

    for y in stride(from: height - 1, through: 0, by: -1) {
        for x in stride(from: width - 1, through: 0, by: -1) {
            let index = y * width + x
            guard inside[index] else { continue }
            if x + 1 < width {
                distance[index] = min(distance[index], distance[index + 1] + 1)
            }
            if y + 1 < height {
                distance[index] = min(distance[index], distance[index + width] + 1)
                if x > 0 {
                    distance[index] = min(distance[index], distance[index + width - 1] + diagonal)
                }
                if x + 1 < width {
                    distance[index] = min(distance[index], distance[index + width + 1] + diagonal)
                }
            }
        }
    }

    var sum: Float = 0
    var maxValue: Float = 0
    for index in 0..<count where inside[index] {
        sum += distance[index]
        maxValue = max(maxValue, distance[index])
    }
    return (sum / Float(pixels.count), maxValue)
}
