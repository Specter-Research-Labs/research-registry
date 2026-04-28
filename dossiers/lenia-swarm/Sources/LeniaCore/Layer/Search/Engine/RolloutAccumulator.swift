import Foundation
import MLX

private func searchRolloutMean(_ values: [Float]) -> Float? {
    guard !values.isEmpty else {
        return nil
    }
    return values.reduce(0, +) / Float(values.count)
}

private func searchRolloutSignedAngleDelta(_ lhs: Float, _ rhs: Float) -> Float {
    var delta = lhs - rhs
    while delta > Float.pi {
        delta -= 2 * Float.pi
    }
    while delta < -Float.pi {
        delta += 2 * Float.pi
    }
    return delta
}

private func searchRolloutWindowStd(_ samples: [[Float]], batchSize: Int) -> [Float] {
    guard !samples.isEmpty else {
        return Array(repeating: 0, count: batchSize)
    }
    let count = Float(samples.count)
    var sums = Array(repeating: Float(0), count: batchSize)
    var squareSums = Array(repeating: Float(0), count: batchSize)
    for sample in samples {
        for i in 0..<batchSize {
            sums[i] += sample[i]
            squareSums[i] += sample[i] * sample[i]
        }
    }
    return (0..<batchSize).map { i in
        let mean = sums[i] / count
        return sqrt(max(squareSums[i] / count - mean * mean, 0))
    }
}

struct SearchRolloutSampleContext {
    let batchSize: Int
    let windowSamples: Int
    let needsWindowStats: Bool
    let occupancyThreshold: MLXArray
    let massFloor: MLXArray
    let cellCountFloat: Float
    let cellCountArr: MLXArray
    let gX: MLXArray
    let gY: MLXArray
    let usesTorusBorder: Bool
    let xPeriodArr: MLXArray?
    let yPeriodArr: MLXArray?
    let xPeriod: Float
    let yPeriod: Float
    let deathThreshold: Float?
    let borderMode: String

    init(
        batchSize: Int,
        runtimeConfig: LeniaRuntimeConfig,
        searchConfig: SearchConfig,
        stabilityConfig: StabilityConfig
    ) {
        self.batchSize = batchSize
        windowSamples = max(stabilityConfig.windowSamples, 0)
        needsWindowStats = stabilityConfig.enabled
            && windowSamples > 0
            && (stabilityConfig.windowMassStdMax != nil
                || stabilityConfig.windowOccupancyStdMax != nil
                || stabilityConfig.windowGyrationStdMax != nil)

        let coordsX = MLXArray(Array(0..<runtimeConfig.sx).map { Float($0) + 0.5 })
        let coordsY = MLXArray(Array(0..<runtimeConfig.sy).map { Float($0) + 0.5 })
        let (gridX, gridY) = meshgrid(coordsX, coordsY)
        gX = gridX.expandedDimensions(axis: 0)
        gY = gridY.expandedDimensions(axis: 0)

        occupancyThreshold = MLXArray(searchConfig.occupancyThreshold)
        massFloor = MLXArray(Float(1e-5))
        cellCountFloat = Float(runtimeConfig.sx * runtimeConfig.sy)
        cellCountArr = MLXArray(cellCountFloat)
        usesTorusBorder = runtimeConfig.border == "torus"
        xPeriod = Float(runtimeConfig.sx)
        yPeriod = Float(runtimeConfig.sy)
        xPeriodArr = usesTorusBorder ? MLXArray(xPeriod) : nil
        yPeriodArr = usesTorusBorder ? MLXArray(yPeriod) : nil
        deathThreshold = searchConfig.kSurvival?.deathThreshold
        borderMode = runtimeConfig.border
    }
}

struct SearchRolloutFinalizedStats {
    let effectiveSampleCount: Int
    let speedCount: Int
    let massMean: [Float]
    let massStd: [Float]
    let massMin: [Float]
    let massMax: [Float]
    let varianceMean: [Float]
    let energyMean: [Float]
    let occupancyMean: [Float]
    let gyration: [Float]
    let finalMass: [Float]
    let windowMassStd: [Float]?
    let windowOccupancyStd: [Float]?
    let windowGyrationStd: [Float]?
    let pathLength: [Float]
    let speedMean: [Float]
    let velocity: [Float]
    let velocityX: [Float]
    let velocityY: [Float]
    let heading: [Float]
    let displacement: [Float]
    let headingCircularVariance: [Float?]
    let accumulatedTurnAbs: [Double]
    let activityLogs: [[ActivitySnapshot]]?
    let activitySummaries: [ActivitySummarizer]?
    let activityEacMean: [Float?]
    let activityEanMean: [Float?]
    let activityDiversityMean: [Float?]
    let activitySpeciesMean: [Float?]
    let survivalDeathStep: [Int?]
    let lastMassMap: MLXArray?

    var massMeanCPU: [Float] { massMean }
    var massStdCPU: [Float] { massStd }
    var massMinCPU: [Float] { massMin }
    var massMaxCPU: [Float] { massMax }
    var varianceMeanCPU: [Float] { varianceMean }
    var energyMeanCPU: [Float] { energyMean }
    var occupancyMeanCPU: [Float] { occupancyMean }
    var gyrationCPU: [Float] { gyration }
    var finalMassCPU: [Float] { finalMass }
    var windowMassStdCPU: [Float]? { windowMassStd }
    var windowOccupancyStdCPU: [Float]? { windowOccupancyStd }
    var windowGyrationStdCPU: [Float]? { windowGyrationStd }
    var pathLengthCPU: [Float] { pathLength }
    var speedMeanCPU: [Float] { speedMean }
    var velocityCPU: [Float] { velocity }
    var velocityXCPU: [Float] { velocityX }
    var velocityYCPU: [Float] { velocityY }
    var headingCPU: [Float] { heading }
    var displacementCPU: [Float] { displacement }
}

struct SearchRolloutAccumulator {
    private let context: SearchRolloutSampleContext
    private let activityConfig: ActivityConfig?
    private let usesActivityMetrics: Bool

    private var massMin: [Float]
    private var massMax: [Float]
    private var massMeanAcc: [Double]
    private var massM2Acc: [Double]
    private var varianceSum: [Float]
    private var energySum: [Float]
    private var occupancySum: [Float]
    private var sampleCount = 0
    private var windowMassSamples: [[Float]] = []
    private var windowOccupancySamples: [[Float]] = []
    private var windowGyrationSamples: [[Float]] = []

    private var firstCoMX: [Float]?
    private var firstCoMY: [Float]?
    private var lastCoMX: [Float]?
    private var lastCoMY: [Float]?
    private var prevCoMX: [Float]?
    private var prevCoMY: [Float]?
    private var headingSinAcc: [Double]
    private var headingCosAcc: [Double]
    private var headingSampleCount: [Int]
    private var previousStepHeading: [Float?]
    private var accumulatedTurnAbs: [Double]
    private var pathLengthAcc: [Float]
    private var lastGyration: [Float]?
    private var finalMass: [Float]?
    private var lastMassMap: MLXArray?
    private var activityLogs: [[ActivitySnapshot]]?
    private var activitySummaries: [ActivitySummarizer]?
    private var survivalDeathStep: [Int?]

    init(
        context: SearchRolloutSampleContext,
        activityConfig: ActivityConfig?,
        usesActivityMetrics: Bool
    ) {
        self.context = context
        self.activityConfig = activityConfig
        self.usesActivityMetrics = usesActivityMetrics
        massMin = Array(repeating: Float.greatestFiniteMagnitude, count: context.batchSize)
        massMax = Array(repeating: -Float.greatestFiniteMagnitude, count: context.batchSize)
        massMeanAcc = Array(repeating: 0.0, count: context.batchSize)
        massM2Acc = Array(repeating: 0.0, count: context.batchSize)
        varianceSum = Array(repeating: 0.0, count: context.batchSize)
        energySum = Array(repeating: 0.0, count: context.batchSize)
        occupancySum = Array(repeating: 0.0, count: context.batchSize)
        headingSinAcc = Array(repeating: 0.0, count: context.batchSize)
        headingCosAcc = Array(repeating: 0.0, count: context.batchSize)
        headingSampleCount = Array(repeating: 0, count: context.batchSize)
        previousStepHeading = Array(repeating: nil, count: context.batchSize)
        accumulatedTurnAbs = Array(repeating: 0.0, count: context.batchSize)
        pathLengthAcc = Array(repeating: 0.0, count: context.batchSize)
        activityLogs = activityConfig?.enabled == true
            ? Array(repeating: [], count: context.batchSize)
            : nil
        activitySummaries = usesActivityMetrics
            ? Array(repeating: ActivitySummarizer(), count: context.batchSize)
            : nil
        survivalDeathStep = Array(repeating: nil, count: context.batchSize)
    }

    init(
        batchSize: Int,
        runtimeConfig: LeniaRuntimeConfig,
        searchConfig: SearchConfig,
        stabilityConfig: StabilityConfig,
        activityConfig: ActivityConfig?,
        usesActivityMetrics: Bool
    ) {
        self.init(
            context: SearchRolloutSampleContext(
                batchSize: batchSize,
                runtimeConfig: runtimeConfig,
                searchConfig: searchConfig,
                stabilityConfig: stabilityConfig
            ),
            activityConfig: activityConfig,
            usesActivityMetrics: usesActivityMetrics
        )
    }

    mutating func recordActivity(_ snapshots: [ActivitySnapshot], config: ActivityConfig) {
        guard var logs = activityLogs else {
            fatalError("Activity tracking requested but activity logs are missing.")
        }
        for i in 0..<context.batchSize {
            logs[i].append(snapshots[i])
        }
        activityLogs = logs

        if usesActivityMetrics {
            guard var summaries = activitySummaries else {
                fatalError("Activity metrics requested but activity summaries are missing.")
            }
            for i in 0..<context.batchSize {
                summaries[i].record(snapshot: snapshots[i], config: config)
            }
            activitySummaries = summaries
        }
    }

    mutating func recordActivity(
        massMap: MLXArray,
        paramMap: MLXArray,
        step: Int,
        config: ActivityConfig,
        border: String
    ) {
        recordActivity(
            computeActivitySnapshots(
                massMap: massMap,
                paramMap: paramMap,
                step: step,
                config: config,
                border: border
            ),
            config: config
        )
    }

    mutating func recordActivity(
        massMap: MLXArray,
        paramMap: MLXArray,
        step: Int
    ) {
        guard let activityConfig else {
            fatalError("Activity tracking requested but activity config is missing.")
        }
        let snapshots = computeActivitySnapshots(
            massMap: massMap,
            paramMap: paramMap,
            step: step,
            config: activityConfig,
            border: context.borderMode
        )
        recordActivity(snapshots, config: activityConfig)
    }

    mutating func recordSample(
        step: Int,
        summarySample: FlowLeniaMetalMassSummary?,
        massMap: MLXArray?,
        energyPerSample explicitEnergyPerSample: MLXArray?
    ) {
        let currentMassCPU: [Float]
        let varianceCPU: [Float]
        let energyCPU: [Float]
        let occupancyCPU: [Float]
        let comXCPU: [Float]
        let comYCPU: [Float]
        let gyrationCPU: [Float]

        if let summarySample {
            currentMassCPU = summarySample.totalMass
            varianceCPU = zip(summarySample.sumSquares, summarySample.totalMass).map { sumSquares, totalMass in
                let meanCellMass = totalMass / context.cellCountFloat
                return max(sumSquares / context.cellCountFloat - meanCellMass * meanCellMass, 0)
            }
            energyCPU = summarySample.energy
            occupancyCPU = summarySample.occupancyCount.map { $0 / context.cellCountFloat }
            comXCPU = summarySample.centerXIndex.map { $0 + 0.5 }
            comYCPU = summarySample.centerYIndex.map { $0 + 0.5 }
            gyrationCPU = summarySample.rawGyration ?? Array(repeating: 0.0, count: context.batchSize)
        } else {
            guard let massMap else {
                fatalError("Metric recording requested but mass map is missing.")
            }
            guard let explicitEnergyPerSample else {
                fatalError("Metric recording requested but energy is missing.")
            }

            let currentMass = massMap.sum(axes: [1, 2])
            lastMassMap = massMap
            let varPerSample = massMap.variance(axes: [1, 2])
            let occMask = MLX.greater(massMap, context.occupancyThreshold).asType(.float32)
            let occPerSample = occMask.mean(axes: [1, 2])

            let massSafe = MLX.maximum(currentMass, context.massFloor)
            let comX = (massMap * context.gX).sum(axes: [1, 2]) / massSafe
            let comY = (massMap * context.gY).sum(axes: [1, 2]) / massSafe

            let cX = comX.expandedDimensions(axes: [1, 2])
            let cY = comY.expandedDimensions(axes: [1, 2])
            let dxRawG = MLX.abs(context.gX - cX)
            let dyRawG = MLX.abs(context.gY - cY)
            let dxG: MLXArray
            let dyG: MLXArray
            if context.usesTorusBorder {
                guard let xPeriodArr = context.xPeriodArr, let yPeriodArr = context.yPeriodArr else {
                    fatalError("torus border requires period arrays.")
                }
                dxG = MLX.minimum(dxRawG, xPeriodArr - dxRawG)
                dyG = MLX.minimum(dyRawG, yPeriodArr - dyRawG)
            } else {
                dxG = dxRawG
                dyG = dyRawG
            }
            let distSq = dxG * dxG + dyG * dyG
            let gyrationPerSample = (massMap * distSq).sum(axes: [1, 2]) / massSafe

            eval(currentMass, varPerSample, explicitEnergyPerSample, occPerSample, comX, comY, gyrationPerSample)
            currentMassCPU = currentMass.asArray(Float.self)
            varianceCPU = varPerSample.asArray(Float.self)
            energyCPU = explicitEnergyPerSample.asArray(Float.self)
            occupancyCPU = occPerSample.asArray(Float.self)
            comXCPU = comX.asArray(Float.self)
            comYCPU = comY.asArray(Float.self)
            gyrationCPU = gyrationPerSample.asArray(Float.self)
        }

        let sampleOrdinal = Double(sampleCount + 1)
        for i in 0..<context.batchSize {
            let value = Double(currentMassCPU[i])
            let delta = value - massMeanAcc[i]
            massMeanAcc[i] += delta / sampleOrdinal
            let delta2 = value - massMeanAcc[i]
            massM2Acc[i] += delta * delta2
        }

        if let threshold = context.deathThreshold {
            for i in 0..<context.batchSize where survivalDeathStep[i] == nil {
                if currentMassCPU[i] < threshold {
                    survivalDeathStep[i] = step
                }
            }
        }

        for i in 0..<context.batchSize {
            massMin[i] = min(massMin[i], currentMassCPU[i])
            massMax[i] = max(massMax[i], currentMassCPU[i])
            varianceSum[i] += varianceCPU[i]
            energySum[i] += energyCPU[i]
            occupancySum[i] += occupancyCPU[i]
        }

        if let px = prevCoMX, let py = prevCoMY {
            let wrap = context.usesTorusBorder
            for i in 0..<context.batchSize {
                var stepDX = comXCPU[i] - px[i]
                var stepDY = comYCPU[i] - py[i]
                if wrap {
                    let halfX = context.xPeriod * 0.5
                    let halfY = context.yPeriod * 0.5
                    if stepDX > halfX { stepDX -= context.xPeriod }
                    if stepDX < -halfX { stepDX += context.xPeriod }
                    if stepDY > halfY { stepDY -= context.yPeriod }
                    if stepDY < -halfY { stepDY += context.yPeriod }
                }
                let stepMagnitude = sqrt(stepDX * stepDX + stepDY * stepDY)
                pathLengthAcc[i] += stepMagnitude
                if stepMagnitude <= 1e-6 {
                    continue
                }
                let heading = atan2f(stepDY, stepDX)
                headingSinAcc[i] += Double(sinf(heading))
                headingCosAcc[i] += Double(cosf(heading))
                headingSampleCount[i] += 1
                if let previousHeading = previousStepHeading[i] {
                    accumulatedTurnAbs[i] += Double(abs(searchRolloutSignedAngleDelta(heading, previousHeading)))
                }
                previousStepHeading[i] = heading
            }
        }

        prevCoMX = comXCPU
        prevCoMY = comYCPU

        if firstCoMX == nil {
            firstCoMX = comXCPU
            firstCoMY = comYCPU
        }
        lastCoMX = comXCPU
        lastCoMY = comYCPU
        finalMass = currentMassCPU
        lastGyration = gyrationCPU

        if context.needsWindowStats {
            windowMassSamples.append(currentMassCPU)
            windowOccupancySamples.append(occupancyCPU)
            windowGyrationSamples.append(gyrationCPU)
            if windowMassSamples.count > context.windowSamples {
                windowMassSamples.removeFirst()
                windowOccupancySamples.removeFirst()
                windowGyrationSamples.removeFirst()
            }
        }

        sampleCount += 1
    }

    func finalize(recordInterval: Int) -> SearchRolloutFinalizedStats {
        let effectiveSampleCount = max(sampleCount, 1)
        let sampleCountF = Float(effectiveSampleCount)
        let speedIntervals = max(effectiveSampleCount - 1, 0)
        let speedTimeSteps = Float(speedIntervals * recordInterval)

        let varianceMeanCPU = varianceSum.map { $0 / sampleCountF }
        let energyMeanCPU = energySum.map { $0 / sampleCountF }
        let occupancyMeanCPU = occupancySum.map { $0 / sampleCountF }
        let gyrationCPU = lastGyration ?? Array(repeating: 1000.0, count: context.batchSize)
        let finalMassCPU = finalMass ?? Array(repeating: 0.0, count: context.batchSize)

        let windowMassStdCPU: [Float]?
        let windowOccupancyStdCPU: [Float]?
        let windowGyrationStdCPU: [Float]?
        if context.needsWindowStats {
            guard !windowMassSamples.isEmpty else {
                fatalError("stability.window_samples requires at least one recorded sample.")
            }
            windowMassStdCPU = searchRolloutWindowStd(windowMassSamples, batchSize: context.batchSize)
            windowOccupancyStdCPU = searchRolloutWindowStd(windowOccupancySamples, batchSize: context.batchSize)
            windowGyrationStdCPU = searchRolloutWindowStd(windowGyrationSamples, batchSize: context.batchSize)
        } else {
            windowMassStdCPU = nil
            windowOccupancyStdCPU = nil
            windowGyrationStdCPU = nil
        }

        let massMeanCPU = sampleCount > 0
            ? massMeanAcc.map { Float($0) }
            : Array(repeating: 0.0, count: context.batchSize)
        let massStdCPU = sampleCount > 0
            ? massM2Acc.map { Float(sqrt(max($0 / Double(effectiveSampleCount), 0.0))) }
            : Array(repeating: 0.0, count: context.batchSize)
        let speedMeanCPU: [Float]
        let velocityCPU: [Float]
        let velocityXCPU: [Float]
        let velocityYCPU: [Float]
        let headingCPU: [Float]
        let displacementCPU: [Float]
        if let fx = firstCoMX, let fy = firstCoMY, let lx = lastCoMX, let ly = lastCoMY {
            let wrap = context.usesTorusBorder
            var velocityValues: [Float] = []
            var velocityXValues: [Float] = []
            var velocityYValues: [Float] = []
            var headingValues: [Float] = []
            var speedValues: [Float] = []
            var displacementValues: [Float] = []
            speedValues.reserveCapacity(context.batchSize)
            velocityValues.reserveCapacity(context.batchSize)
            velocityXValues.reserveCapacity(context.batchSize)
            velocityYValues.reserveCapacity(context.batchSize)
            headingValues.reserveCapacity(context.batchSize)
            displacementValues.reserveCapacity(context.batchSize)
            for i in 0..<context.batchSize {
                var dx = lx[i] - fx[i]
                var dy = ly[i] - fy[i]
                if wrap {
                    let halfX = context.xPeriod * 0.5
                    let halfY = context.yPeriod * 0.5
                    if dx > halfX { dx -= context.xPeriod }
                    if dx < -halfX { dx += context.xPeriod }
                    if dy > halfY { dy -= context.yPeriod }
                    if dy < -halfY { dy += context.yPeriod }
                }
                let displacement = sqrt(dx * dx + dy * dy)
                displacementValues.append(displacement)
                if speedIntervals > 0 {
                    let velocityX = dx / speedTimeSteps
                    let velocityY = dy / speedTimeSteps
                    speedValues.append(pathLengthAcc[i] / speedTimeSteps)
                    velocityValues.append(displacement / speedTimeSteps)
                    velocityXValues.append(velocityX)
                    velocityYValues.append(velocityY)
                    headingValues.append(atan2f(velocityY, velocityX))
                } else {
                    speedValues.append(0.0)
                    velocityValues.append(0.0)
                    velocityXValues.append(0.0)
                    velocityYValues.append(0.0)
                    headingValues.append(0.0)
                }
            }
            speedMeanCPU = speedValues
            velocityCPU = velocityValues
            velocityXCPU = velocityXValues
            velocityYCPU = velocityYValues
            headingCPU = headingValues
            displacementCPU = displacementValues
        } else {
            speedMeanCPU = Array(repeating: 0.0, count: context.batchSize)
            velocityCPU = Array(repeating: 0.0, count: context.batchSize)
            velocityXCPU = Array(repeating: 0.0, count: context.batchSize)
            velocityYCPU = Array(repeating: 0.0, count: context.batchSize)
            headingCPU = Array(repeating: 0.0, count: context.batchSize)
            displacementCPU = Array(repeating: 0.0, count: context.batchSize)
        }

        let headingCircularVariance = (0..<context.batchSize).map { index -> Float? in
            guard headingSampleCount[index] > 0 else {
                return nil
            }
            let resultantLength = sqrt(
                headingSinAcc[index] * headingSinAcc[index] + headingCosAcc[index] * headingCosAcc[index]
            ) / Double(headingSampleCount[index])
            return Float(max(0, 1 - resultantLength))
        }

        let activityEacMean: [Float?]
        let activityEanMean: [Float?]
        let activityDiversityMean: [Float?]
        let activitySpeciesMean: [Float?]
        if usesActivityMetrics {
            guard let activitySummaries else {
                fatalError("Activity metrics requested but activity tracking is disabled.")
            }
            let summaries = activitySummaries.map { $0.summary() }
            activityEacMean = summaries.map { searchRolloutMean($0.eac) }
            activityEanMean = summaries.map { searchRolloutMean($0.ean) }
            activityDiversityMean = summaries.map { searchRolloutMean($0.diversity) }
            activitySpeciesMean = summaries.map { searchRolloutMean($0.speciesCount.map(Float.init)) }
        } else {
            activityEacMean = Array(repeating: nil, count: context.batchSize)
            activityEanMean = Array(repeating: nil, count: context.batchSize)
            activityDiversityMean = Array(repeating: nil, count: context.batchSize)
            activitySpeciesMean = Array(repeating: nil, count: context.batchSize)
        }

        return SearchRolloutFinalizedStats(
            effectiveSampleCount: effectiveSampleCount,
            speedCount: speedIntervals,
            massMean: massMeanCPU,
            massStd: massStdCPU,
            massMin: massMin,
            massMax: massMax,
            varianceMean: varianceMeanCPU,
            energyMean: energyMeanCPU,
            occupancyMean: occupancyMeanCPU,
            gyration: gyrationCPU,
            finalMass: finalMassCPU,
            windowMassStd: windowMassStdCPU,
            windowOccupancyStd: windowOccupancyStdCPU,
            windowGyrationStd: windowGyrationStdCPU,
            pathLength: pathLengthAcc,
            speedMean: speedMeanCPU,
            velocity: velocityCPU,
            velocityX: velocityXCPU,
            velocityY: velocityYCPU,
            heading: headingCPU,
            displacement: displacementCPU,
            headingCircularVariance: headingCircularVariance,
            accumulatedTurnAbs: accumulatedTurnAbs,
            activityLogs: activityLogs,
            activitySummaries: activitySummaries,
            activityEacMean: activityEacMean,
            activityEanMean: activityEanMean,
            activityDiversityMean: activityDiversityMean,
            activitySpeciesMean: activitySpeciesMean,
            survivalDeathStep: survivalDeathStep,
            lastMassMap: lastMassMap
        )
    }
}
