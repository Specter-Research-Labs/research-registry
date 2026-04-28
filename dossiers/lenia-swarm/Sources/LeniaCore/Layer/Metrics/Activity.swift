import Foundation
import MLX

public struct ActivityConfig: Codable, Sendable {
    public let enabled: Bool
    public let interval: Int
    public let threshold: Float
    public let maxComponents: Int?
    public let matchThreshold: Float
    public let paramWeight: Float
    public let positionWeight: Float

    public init(
        enabled: Bool,
        interval: Int,
        threshold: Float,
        maxComponents: Int?,
        matchThreshold: Float,
        paramWeight: Float,
        positionWeight: Float
    ) {
        self.enabled = enabled
        self.interval = interval
        self.threshold = threshold
        self.maxComponents = maxComponents
        self.matchThreshold = matchThreshold
        self.paramWeight = paramWeight
        self.positionWeight = positionWeight
    }
}

public struct ComponentSnapshot: Codable, Sendable {
    public let id: Int
    public let mass: Float
    public let centroid: [Float]
    public let paramMean: [Float]

    public init(id: Int, mass: Float, centroid: [Float], paramMean: [Float]) {
        self.id = id
        self.mass = mass
        self.centroid = centroid
        self.paramMean = paramMean
    }
}

public struct ActivitySnapshot: Codable, Sendable {
    public let step: Int
    public let components: [ComponentSnapshot]
    public let width: Int
    public let height: Int
    public let isTorus: Bool

    public init(step: Int, components: [ComponentSnapshot], width: Int, height: Int, isTorus: Bool) {
        self.step = step
        self.components = components
        self.width = width
        self.height = height
        self.isTorus = isTorus
    }
}

public struct ActivitySummary: Codable, Sendable {
    public let steps: [Int]
    public let eap: [Float]
    public let eac: [Float]
    public let ean: [Float]
    public let diversity: [Float]
    public let speciesCount: [Int]

    public init(steps: [Int], eap: [Float], eac: [Float], ean: [Float], diversity: [Float], speciesCount: [Int]) {
        self.steps = steps
        self.eap = eap
        self.eac = eac
        self.ean = ean
        self.diversity = diversity
        self.speciesCount = speciesCount
    }
}

public struct ActivitySummaryRecord: Codable, Sendable {
    public let seed: Int
    public let workerId: String?
    public let summary: ActivitySummary
    public let implementation: ImplementationSettings

    public init(seed: Int, workerId: String?, summary: ActivitySummary, implementation: ImplementationSettings) {
        self.seed = seed
        self.workerId = workerId
        self.summary = summary
        self.implementation = implementation
    }
}

public func computeActivitySnapshots(
    massMap: MLXArray,
    paramMap: MLXArray,
    step: Int,
    config: ActivityConfig,
    border: String
) -> [ActivitySnapshot] {
    eval(massMap, paramMap)

    let shape = massMap.shape
    let batch: Int
    let height: Int
    let width: Int
    if shape.count == 3 {
        batch = shape[0]
        height = shape[1]
        width = shape[2]
    } else if shape.count == 2 {
        batch = 1
        height = shape[0]
        width = shape[1]
    } else {
        fatalError("massMap must have 2 or 3 dimensions for activity snapshots.")
    }
    let paramShape = paramMap.shape
    let nbK: Int
    if paramShape.count == 4 {
        if paramShape[0] != batch || paramShape[1] != height || paramShape[2] != width {
            fatalError("paramMap shape must match massMap batch/height/width for activity snapshots.")
        }
        nbK = paramShape[3]
    } else if paramShape.count == 3 {
        if batch != 1 {
            fatalError("paramMap missing batch dimension for activity snapshots.")
        }
        if paramShape[0] != height || paramShape[1] != width {
            fatalError("paramMap shape must match massMap height/width for activity snapshots.")
        }
        nbK = paramShape[2]
    } else {
        fatalError("paramMap must have 3 or 4 dimensions for activity snapshots.")
    }
    if nbK == 0 {
        fatalError("paramMap must have kernel dimension for activity snapshots.")
    }

    let sampleSize = width * height
    let paramSampleSize = sampleSize * nbK
    let massFlat = massMap.asArray(Float.self)
    let paramFlat = paramMap.asArray(Float.self)
    if massFlat.count != batch * sampleSize {
        fatalError("massMap data size does not match its shape for activity snapshots.")
    }
    if paramFlat.count != batch * paramSampleSize {
        fatalError("paramMap data size does not match its shape for activity snapshots.")
    }

    var snapshots: [ActivitySnapshot] = []
    snapshots.reserveCapacity(batch)
    let useTorus = border == "torus"

    for b in 0..<batch {
        let massStart = b * sampleSize
        let paramStart = b * paramSampleSize
        let components = extractComponents(
            mass: massFlat,
            massOffset: massStart,
            params: paramFlat,
            paramOffset: paramStart,
            width: width,
            height: height,
            nbK: nbK,
            threshold: config.threshold,
            maxComponents: config.maxComponents,
            useTorus: useTorus
        )
        snapshots.append(ActivitySnapshot(
            step: step,
            components: components,
            width: width,
            height: height,
            isTorus: useTorus
        ))
    }
    return snapshots
}

public func summarizeActivity(
    snapshots: [ActivitySnapshot],
    config: ActivityConfig
) -> ActivitySummary {
    var summarizer = ActivitySummarizer()
    for snapshot in snapshots {
        summarizer.record(snapshot: snapshot, config: config)
    }
    return summarizer.summary()
}

private struct TrackedComponent {
    let speciesId: Int
    let mass: Float
    let centroid: [Float]
    let paramMean: [Float]
}

private struct SpeciesState {
    var presenceActivity: Float = 0
    var countActivity: Float = 0
    var nonNeutralActivity: Float = 0
    var prevRho: Float = 0
    var lastParams: [Float] = []
    var lastCentroid: [Float] = []
}

struct ActivitySummarizer {
    private var speciesNextId = 0
    private var speciesStates: [Int: SpeciesState] = [:]
    private var prevComponents: [TrackedComponent] = []
    private var steps: [Int] = []
    private var eapSeries: [Float] = []
    private var eacSeries: [Float] = []
    private var eanSeries: [Float] = []
    private var diversitySeries: [Float] = []
    private var speciesCount: [Int] = []
    private var snapshotIndex = 0

    mutating func record(snapshot: ActivitySnapshot, config: ActivityConfig) {
        let tracked = matchComponents(
            current: snapshot.components,
            previous: prevComponents,
            config: config,
            nextId: &speciesNextId,
            gridWidth: snapshot.width,
            gridHeight: snapshot.height,
            useTorus: snapshot.isTorus
        )
        prevComponents = tracked

        let totalMass = tracked.reduce(0) { $0 + $1.mass }
        var nextStates: [Int: SpeciesState] = [:]
        var totalPresenceActivity: Float = 0
        var totalCountActivity: Float = 0
        var totalNonNeutralActivity: Float = 0
        for component in tracked {
            let id = component.speciesId
            var state = speciesStates[id] ?? SpeciesState()
            state.presenceActivity += 1
            state.countActivity += component.mass
            let rho = totalMass > 0 ? component.mass / totalMass : 0
            if snapshotIndex > 0 && rho > state.prevRho {
                let delta = rho - state.prevRho
                let activityDelta = totalMass * delta * delta
                state.nonNeutralActivity += activityDelta
            }
            state.prevRho = rho
            state.lastParams = component.paramMean
            state.lastCentroid = component.centroid
            nextStates[id] = state
            totalPresenceActivity += state.presenceActivity
            totalCountActivity += state.countActivity
            totalNonNeutralActivity += state.nonNeutralActivity
        }
        speciesStates = nextStates

        steps.append(snapshot.step)
        eapSeries.append(totalPresenceActivity)
        eacSeries.append(totalCountActivity)
        eanSeries.append(totalNonNeutralActivity)
        diversitySeries.append(averagePairwiseDistance(tracked.map { $0.paramMean }))
        speciesCount.append(tracked.count)
        snapshotIndex += 1
    }

    func summary() -> ActivitySummary {
        ActivitySummary(
            steps: steps,
            eap: eapSeries,
            eac: eacSeries,
            ean: eanSeries,
            diversity: diversitySeries,
            speciesCount: speciesCount
        )
    }
}

private func matchComponents(
    current: [ComponentSnapshot],
    previous: [TrackedComponent],
    config: ActivityConfig,
    nextId: inout Int,
    gridWidth: Int,
    gridHeight: Int,
    useTorus: Bool
) -> [TrackedComponent] {
    var usedPrev: Set<Int> = []
    var tracked: [TrackedComponent] = []

    let sortedCurrent = current.sorted { $0.mass > $1.mass }
    for component in sortedCurrent {
        var bestIndex: Int? = nil
        var bestDistance = Float.greatestFiniteMagnitude
        for (idx, prev) in previous.enumerated() {
            if usedPrev.contains(idx) { continue }
            let dist = componentDistance(
                paramsA: component.paramMean,
                paramsB: prev.paramMean,
                centroidA: component.centroid,
                centroidB: prev.centroid,
                paramWeight: config.paramWeight,
                positionWeight: config.positionWeight,
                gridWidth: gridWidth,
                gridHeight: gridHeight,
                useTorus: useTorus
            )
            if dist < bestDistance {
                bestDistance = dist
                bestIndex = idx
            }
        }

        if let matchIdx = bestIndex,
           bestDistance <= config.matchThreshold {
            let prevComp = previous[matchIdx]
            usedPrev.insert(matchIdx)
            tracked.append(TrackedComponent(
                speciesId: prevComp.speciesId,
                mass: component.mass,
                centroid: component.centroid,
                paramMean: component.paramMean
            ))
        } else {
            let newId = nextId
            nextId += 1
            tracked.append(TrackedComponent(
                speciesId: newId,
                mass: component.mass,
                centroid: component.centroid,
                paramMean: component.paramMean
            ))
        }
    }

    return tracked
}

private func componentDistance(
    paramsA: [Float],
    paramsB: [Float],
    centroidA: [Float],
    centroidB: [Float],
    paramWeight: Float,
    positionWeight: Float,
    gridWidth: Int,
    gridHeight: Int,
    useTorus: Bool
) -> Float {
    let paramDist = l2Distance(paramsA, paramsB)
    let posDist: Float
    if useTorus, centroidA.count >= 2, centroidB.count >= 2 {
        let dx = torusDelta(centroidA[0], centroidB[0], period: Float(gridWidth))
        let dy = torusDelta(centroidA[1], centroidB[1], period: Float(gridHeight))
        posDist = sqrt(dx * dx + dy * dy)
    } else {
        posDist = l2Distance(centroidA, centroidB)
    }
    return paramWeight * paramDist + positionWeight * posDist
}

private func torusDelta(_ a: Float, _ b: Float, period: Float) -> Float {
    let diff = abs(a - b)
    let wrapped = period - diff
    return min(diff, wrapped)
}

private func l2Distance(_ a: [Float], _ b: [Float]) -> Float {
    guard a.count == b.count else { return Float.greatestFiniteMagnitude }
    var sum: Float = 0
    for i in 0..<a.count {
        let diff = a[i] - b[i]
        sum += diff * diff
    }
    return sqrt(sum)
}

private func averagePairwiseDistance(_ vectors: [[Float]]) -> Float {
    let count = vectors.count
    if count < 2 { return 0 }
    var total: Float = 0
    var pairs = 0
    for i in 0..<count {
        for j in (i + 1)..<count {
            total += l2Distance(vectors[i], vectors[j])
            pairs += 1
        }
    }
    return pairs > 0 ? total / Float(pairs) : 0
}

private func extractComponents(
    mass: [Float],
    massOffset: Int,
    params: [Float],
    paramOffset: Int,
    width: Int,
    height: Int,
    nbK: Int,
    threshold: Float,
    maxComponents: Int?,
    useTorus: Bool
) -> [ComponentSnapshot] {
    let totalCells = width * height
    var visited = [Bool](repeating: false, count: totalCells)
    var components: [ComponentSnapshot] = []
    var componentId = 0

    let offsets = componentNeighborOffsets
    for y in 0..<height {
        for x in 0..<width {
            let idx = y * width + x
            let massIndex = massOffset + idx
            if visited[idx] || mass[massIndex] <= threshold {
                continue
            }

            var queue: [(Int, Int)] = [(x, y)]
            visited[idx] = true

            var massSum: Float = 0
            var sumX: Float = 0
            var sumY: Float = 0
            var sumCosX: Float = 0
            var sumSinX: Float = 0
            var sumCosY: Float = 0
            var sumSinY: Float = 0
            let twoPi = 2 * Float.pi
            var paramSum = [Float](repeating: 0, count: nbK)

            while !queue.isEmpty {
                let (cx, cy) = queue.removeLast()
                let cidx = cy * width + cx
                let m = mass[massOffset + cidx]
                massSum += m
                if useTorus {
                    let angleX = twoPi * Float(cx) / Float(width)
                    let angleY = twoPi * Float(cy) / Float(height)
                    sumCosX += m * cos(angleX)
                    sumSinX += m * sin(angleX)
                    sumCosY += m * cos(angleY)
                    sumSinY += m * sin(angleY)
                } else {
                    sumX += Float(cx) * m
                    sumY += Float(cy) * m
                }

                let pBase = paramOffset + cidx * nbK
                for k in 0..<nbK {
                    paramSum[k] += m * params[pBase + k]
                }

                for (dx, dy) in offsets {
                    var nx = cx + dx
                    var ny = cy + dy
                    if useTorus {
                        nx = (nx + width) % width
                        ny = (ny + height) % height
                    } else {
                        if nx < 0 || ny < 0 || nx >= width || ny >= height {
                            continue
                        }
                    }
                    let nidx = ny * width + nx
                    if visited[nidx] || mass[massOffset + nidx] <= threshold {
                        continue
                    }
                    visited[nidx] = true
                    queue.append((nx, ny))
                }
            }

            if massSum > 0 {
                let centroid: [Float]
                if useTorus {
                    centroid = torusCentroid(
                        sumSinX: sumSinX,
                        sumCosX: sumCosX,
                        sumSinY: sumSinY,
                        sumCosY: sumCosY,
                        width: width,
                        height: height
                    )
                } else {
                    centroid = [sumX / massSum, sumY / massSum]
                }
                let paramMean = paramSum.map { $0 / massSum }
                let component = ComponentSnapshot(
                    id: componentId,
                    mass: massSum,
                    centroid: centroid,
                    paramMean: paramMean
                )
                components.append(component)
                componentId += 1
            }
        }
    }

    if let maxComponents = maxComponents, components.count > maxComponents {
        components.sort { $0.mass > $1.mass }
        components = Array(components.prefix(maxComponents))
    }

    return components
}

private func torusCentroid(
    sumSinX: Float,
    sumCosX: Float,
    sumSinY: Float,
    sumCosY: Float,
    width: Int,
    height: Int
) -> [Float] {
    let twoPi = 2 * Float.pi
    let angleX = atan2(sumSinX, sumCosX)
    let angleY = atan2(sumSinY, sumCosY)
    let normX = angleX < 0 ? angleX + twoPi : angleX
    let normY = angleY < 0 ? angleY + twoPi : angleY
    return [normX / twoPi * Float(width), normY / twoPi * Float(height)]
}

private func neighborOffsets() -> [(Int, Int)] {
    var offsets: [(Int, Int)] = []
    for dy in -1...1 {
        for dx in -1...1 {
            if dx == 0 && dy == 0 { continue }
            offsets.append((dx, dy))
        }
    }
    return offsets
}

private let componentNeighborOffsets = neighborOffsets()
