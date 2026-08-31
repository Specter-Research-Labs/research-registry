import CryptoKit
import Foundation

public struct MorphospaceDescriptorBundle: Codable, Sendable {
    public let descriptorVersion: Int
    public let symmetryPolicy: String
    public let genotype: MorphospaceGenotypeDescriptor
    public let terminal: MorphospaceTerminalDescriptor
    public let trajectory: MorphospaceTrajectoryDescriptor?

    public init(
        descriptorVersion: Int = 2,
        symmetryPolicy: String,
        genotype: MorphospaceGenotypeDescriptor,
        terminal: MorphospaceTerminalDescriptor,
        trajectory: MorphospaceTrajectoryDescriptor?
    ) {
        self.descriptorVersion = descriptorVersion
        self.symmetryPolicy = symmetryPolicy
        self.genotype = genotype
        self.terminal = terminal
        self.trajectory = trajectory
    }
}

public struct MorphospaceGenotypeDescriptor: Codable, Sendable {
    public let version: Int
    public let canonicalizer: String
    public let kernelCount: Int
    public let vectorLength: Int
    public let vector: [Float]
    public let hash12: String

    public init(
        version: Int = 1,
        canonicalizer: String = "kernel_permutation_sort_v1",
        kernelCount: Int,
        vectorLength: Int,
        vector: [Float],
        hash12: String
    ) {
        self.version = version
        self.canonicalizer = canonicalizer
        self.kernelCount = kernelCount
        self.vectorLength = vectorLength
        self.vector = vector
        self.hash12 = hash12
    }
}

public struct MorphospaceTerminalDescriptor: Codable, Sendable {
    public let version: Int
    public let massChannel: Int
    public let borderMode: String
    public let normalizationPolicy: String
    public let symmetryPolicy: String
    public let fingerprintResolution: Int
    public let fingerprintU8: Data
    public let angularSymmetry: MorphospaceAngularSymmetryDescriptor
    public let fingerprintHash12: String
    public let finalMass: Float
    public let finalOccupancy: Float
    public let finalGyration: Float
    public let momentMass: Float?
    public let momentVolume: Float?
    public let momentDensity: Float?
    public let momentAnisotropy: Float?
    public let componentCount: Float?
    public let largestComponentFraction: Float?
    public let largestComponentAnisotropy: Float?
    public let largestComponentInternalStripe: Float?
    public let largestComponentOrientedRidge: Float?
    public let largestComponentSolidity: Float?
    public let largestComponentMeanThickness: Float?
    public let largestComponentMaxThickness: Float?
    public let largestComponentFilamentarity: Float?
    public let hu1: Float?
    public let hu2: Float?
    public let hu3: Float?
    public let hu4: Float?
    public let hu5: Float?
    public let hu6: Float?
    public let hu7: Float?
    public let flusser1: Float?
    public let flusser2: Float?
    public let flusser3: Float?
    public let flusser4: Float?
    public let windowMassStd: Float?
    public let windowOccupancyStd: Float?
    public let windowGyrationStd: Float?
    public let isStable: Bool

    public init(
        version: Int = 2,
        massChannel: Int,
        borderMode: String,
        normalizationPolicy: String = "border_aware_com_center_peak_q32_u8_v2",
        symmetryPolicy: String,
        fingerprintResolution: Int = 32,
        fingerprintU8: Data,
        angularSymmetry: MorphospaceAngularSymmetryDescriptor,
        fingerprintHash12: String,
        finalMass: Float,
        finalOccupancy: Float,
        finalGyration: Float,
        momentMass: Float?,
        momentVolume: Float?,
        momentDensity: Float?,
        momentAnisotropy: Float?,
        componentCount: Float?,
        largestComponentFraction: Float?,
        largestComponentAnisotropy: Float?,
        largestComponentInternalStripe: Float? = nil,
        largestComponentOrientedRidge: Float? = nil,
        largestComponentSolidity: Float? = nil,
        largestComponentMeanThickness: Float? = nil,
        largestComponentMaxThickness: Float? = nil,
        largestComponentFilamentarity: Float? = nil,
        hu1: Float?,
        hu2: Float?,
        hu3: Float?,
        hu4: Float?,
        hu5: Float?,
        hu6: Float?,
        hu7: Float?,
        flusser1: Float?,
        flusser2: Float?,
        flusser3: Float?,
        flusser4: Float?,
        windowMassStd: Float?,
        windowOccupancyStd: Float?,
        windowGyrationStd: Float?,
        isStable: Bool
    ) {
        self.version = version
        self.massChannel = massChannel
        self.borderMode = borderMode
        self.normalizationPolicy = normalizationPolicy
        self.symmetryPolicy = symmetryPolicy
        self.fingerprintResolution = fingerprintResolution
        self.fingerprintU8 = fingerprintU8
        self.angularSymmetry = angularSymmetry
        self.fingerprintHash12 = fingerprintHash12
        self.finalMass = finalMass
        self.finalOccupancy = finalOccupancy
        self.finalGyration = finalGyration
        self.momentMass = momentMass
        self.momentVolume = momentVolume
        self.momentDensity = momentDensity
        self.momentAnisotropy = momentAnisotropy
        self.componentCount = componentCount
        self.largestComponentFraction = largestComponentFraction
        self.largestComponentAnisotropy = largestComponentAnisotropy
        self.largestComponentInternalStripe = largestComponentInternalStripe
        self.largestComponentOrientedRidge = largestComponentOrientedRidge
        self.largestComponentSolidity = largestComponentSolidity
        self.largestComponentMeanThickness = largestComponentMeanThickness
        self.largestComponentMaxThickness = largestComponentMaxThickness
        self.largestComponentFilamentarity = largestComponentFilamentarity
        self.hu1 = hu1
        self.hu2 = hu2
        self.hu3 = hu3
        self.hu4 = hu4
        self.hu5 = hu5
        self.hu6 = hu6
        self.hu7 = hu7
        self.flusser1 = flusser1
        self.flusser2 = flusser2
        self.flusser3 = flusser3
        self.flusser4 = flusser4
        self.windowMassStd = windowMassStd
        self.windowOccupancyStd = windowOccupancyStd
        self.windowGyrationStd = windowGyrationStd
        self.isStable = isStable
    }
}

public struct MorphospaceAngularSymmetryDescriptor: Codable, Sendable {
    public let version: Int
    public let binCount: Int
    public let maxOrder: Int
    public let harmonics: [Float]
    public let dominantOrder: Int?
    public let dominantAmplitude: Float?
    public let normalizedEntropy: Float?

    public init(
        version: Int = 1,
        binCount: Int,
        maxOrder: Int,
        harmonics: [Float],
        dominantOrder: Int?,
        dominantAmplitude: Float?,
        normalizedEntropy: Float?
    ) {
        self.version = version
        self.binCount = binCount
        self.maxOrder = maxOrder
        self.harmonics = harmonics
        self.dominantOrder = dominantOrder
        self.dominantAmplitude = dominantAmplitude
        self.normalizedEntropy = normalizedEntropy
    }
}

public struct MorphospaceTrajectoryDescriptor: Codable, Sendable {
    public let version: Int
    public let recordInterval: Int
    public let warmupSteps: Int
    public let sampleCount: Int
    public let pathLength: Float
    public let displacement: Float
    public let pathTortuosity: Float?
    public let movementEfficiency: Float?
    public let speedMean: Float
    public let centerVelocity: Float
    public let velocityX: Float
    public let velocityY: Float
    public let headingRad: Float
    public let headingCircularVariance: Float?
    public let accumulatedTurnAbs: Float?
    public let survivalSteps: Int?
    public let activityEacMean: Float?
    public let activityEanMean: Float?
    public let activityDiversityMean: Float?
    public let activitySpeciesMean: Float?
    public let activitySpeciesMax: Int?
    public let activitySpeciesStd: Float?
    public let activityDiversityStd: Float?
    public let activityEacMax: Float?
    public let activityEanMax: Float?
    public let componentSeriesMean: Float?
    public let componentSeriesStd: Float?
    public let componentSeriesMax: Int?

    public init(
        version: Int = 1,
        recordInterval: Int,
        warmupSteps: Int,
        sampleCount: Int,
        pathLength: Float,
        displacement: Float,
        pathTortuosity: Float?,
        movementEfficiency: Float?,
        speedMean: Float,
        centerVelocity: Float,
        velocityX: Float,
        velocityY: Float,
        headingRad: Float,
        headingCircularVariance: Float?,
        accumulatedTurnAbs: Float?,
        survivalSteps: Int?,
        activityEacMean: Float?,
        activityEanMean: Float?,
        activityDiversityMean: Float?,
        activitySpeciesMean: Float?,
        activitySpeciesMax: Int?,
        activitySpeciesStd: Float?,
        activityDiversityStd: Float?,
        activityEacMax: Float?,
        activityEanMax: Float?,
        componentSeriesMean: Float?,
        componentSeriesStd: Float?,
        componentSeriesMax: Int?
    ) {
        self.version = version
        self.recordInterval = recordInterval
        self.warmupSteps = warmupSteps
        self.sampleCount = sampleCount
        self.pathLength = pathLength
        self.displacement = displacement
        self.pathTortuosity = pathTortuosity
        self.movementEfficiency = movementEfficiency
        self.speedMean = speedMean
        self.centerVelocity = centerVelocity
        self.velocityX = velocityX
        self.velocityY = velocityY
        self.headingRad = headingRad
        self.headingCircularVariance = headingCircularVariance
        self.accumulatedTurnAbs = accumulatedTurnAbs
        self.survivalSteps = survivalSteps
        self.activityEacMean = activityEacMean
        self.activityEanMean = activityEanMean
        self.activityDiversityMean = activityDiversityMean
        self.activitySpeciesMean = activitySpeciesMean
        self.activitySpeciesMax = activitySpeciesMax
        self.activitySpeciesStd = activitySpeciesStd
        self.activityDiversityStd = activityDiversityStd
        self.activityEacMax = activityEacMax
        self.activityEanMax = activityEanMax
        self.componentSeriesMean = componentSeriesMean
        self.componentSeriesStd = componentSeriesStd
        self.componentSeriesMax = componentSeriesMax
    }
}

public func morphospaceCanonicalGenotypeVector(_ params: KernelParams) -> [Float] {
    let kernelCount = params.r.count
    guard kernelCount > 0 else {
        fatalError("Morphospace genotype canonicalization requires at least one kernel.")
    }
    guard params.m.count == kernelCount,
          params.s.count == kernelCount,
          params.h.count == kernelCount,
          params.b.count == kernelCount,
          params.w.count == kernelCount,
          params.a.count == kernelCount else {
        fatalError("Morphospace genotype canonicalization requires consistent kernel array lengths.")
    }

    var kernels: [MorphospaceCanonicalKernel] = []
    kernels.reserveCapacity(kernelCount)
    for index in 0..<kernelCount {
        kernels.append(
            MorphospaceCanonicalKernel(
                r: params.r[index],
                m: params.m[index],
                s: params.s[index],
                h: params.h[index],
                b: params.b[index],
                w: params.w[index],
                a: params.a[index]
            )
        )
    }
    kernels.sort { $0.signature < $1.signature }

    var vector: [Float] = []
    vector.reserveCapacity(kernels.count * 16 + 1)
    for kernel in kernels {
        vector.append(kernel.r)
        vector.append(kernel.m)
        vector.append(kernel.s)
        vector.append(kernel.h)
        vector.append(contentsOf: kernel.b)
        vector.append(contentsOf: kernel.w)
        vector.append(contentsOf: kernel.a)
    }
    vector.append(params.R)
    return vector
}

public func morphospaceGenotypeDescriptor(_ params: KernelParams) -> MorphospaceGenotypeDescriptor {
    let vector = morphospaceCanonicalGenotypeVector(params)
    return MorphospaceGenotypeDescriptor(
        kernelCount: params.r.count,
        vectorLength: vector.count,
        vector: vector,
        hash12: morphospaceHash12(data: morphospaceFloatData(vector))
    )
}

public func morphospaceGenotypeDescriptor(_ params: ResolvedParams) -> MorphospaceGenotypeDescriptor {
    morphospaceGenotypeDescriptor(params.toKernelParams())
}

public func morphospaceOpaqueGenotypeDescriptor(
    vector: [Float],
    kernelCount: Int,
    canonicalizer: String
) -> MorphospaceGenotypeDescriptor {
    MorphospaceGenotypeDescriptor(
        canonicalizer: canonicalizer,
        kernelCount: kernelCount,
        vectorLength: vector.count,
        vector: vector,
        hash12: morphospaceHash12(data: morphospaceFloatData(vector))
    )
}

public func morphospaceInitialConditionFamily(_ initConfig: InitConfig) -> String {
    let normalized = MorphospaceNormalizedInitConfig(
        patches: initConfig.patches
            .map { MorphospaceNormalizedPatch(center: $0.center, size: $0.size) }
            .sorted {
                ($0.center[0], $0.center[1], $0.size) < ($1.center[0], $1.center[1], $1.size)
            },
        statePatch: initConfig.state_patch.map { patch in
            MorphospaceNormalizedStatePatch(
                center: patch.center,
                width: patch.width,
                height: patch.height,
                channels: patch.channels,
                hash12: morphospaceHash12(data: patch.data)
            )
        },
        paramStatePatch: initConfig.p_state_patch.map { patch in
            MorphospaceNormalizedStatePatch(
                center: patch.center,
                width: patch.width,
                height: patch.height,
                channels: patch.channels,
                hash12: morphospaceHash12(data: patch.data)
            )
        },
        aUniformLow: initConfig.a_uniform.low,
        aUniformHigh: initConfig.a_uniform.high,
        pUniformLow: initConfig.p_uniform?.low,
        pUniformHigh: initConfig.p_uniform?.high
    )
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    guard let data = try? encoder.encode(normalized) else {
        fatalError("Failed to encode normalized initial condition family payload.")
    }
    let patchLabel: String
    if let statePatch = normalized.statePatch {
        patchLabel = "state_patch\(statePatch.width)x\(statePatch.height)x\(statePatch.channels)"
    } else if let paramStatePatch = normalized.paramStatePatch {
        patchLabel = "param_patch\(paramStatePatch.width)x\(paramStatePatch.height)x\(paramStatePatch.channels)"
    } else {
        patchLabel = normalized.patches.count == 1 ? "single_patch" : "patches\(normalized.patches.count)"
    }
    return "initfam:v2:\(patchLabel):\(morphospaceHash12(data: data))"
}

public func morphospaceTrajectoryComponentStats(activity: [ActivitySnapshot]?) -> (mean: Float?, std: Float?, max: Int?) {
    guard let activity, !activity.isEmpty else {
        return (nil, nil, nil)
    }
    let counts = activity.map { $0.components.count }
    return (mean(counts), std(counts), counts.max())
}

func morphospaceFinalSampleSummary(
    materialized batchData: MassBatchCPU,
    sampleIndex: Int,
    occupancyThreshold: Float,
    useTorus: Bool
) -> (
    fingerprintResolution: Int,
    fingerprintU8: Data,
    angularSymmetry: MorphospaceAngularSymmetryDescriptor,
    fingerprintHash12: String,
    finalMass: Float,
    finalOccupancy: Float,
    finalGyration: Float,
    centerX: Float,
    centerY: Float
) {
    guard sampleIndex >= 0 && sampleIndex < batchData.batch else {
        fatalError("Morphospace final sample summary index \(sampleIndex) is out of range for batch size \(batchData.batch).")
    }

    let width = batchData.width
    let height = batchData.height
    let start = sampleIndex * batchData.sampleSize
    let sample = Array(batchData.flat[start..<(start + batchData.sampleSize)])

    var occupied = 0
    for y in 0..<height {
        let rowOffset = y * width
        for x in 0..<width {
            let value = sample[rowOffset + x]
            if value > occupancyThreshold {
                occupied += 1
            }
        }
    }

    let occupancy = Float(occupied) / Float(width * height)
    guard let geometry = morphospaceFieldGeometry(
        sample: sample,
        width: width,
        height: height,
        useTorus: useTorus
    ) else {
        let zeroFingerprint = Data(repeating: 0, count: 32 * 32)
        return (
            32,
            zeroFingerprint,
            morphospaceAngularSymmetryDescriptor(
                fingerprint: [UInt8](zeroFingerprint),
                width: 32,
                height: 32
            ),
            morphospaceHash12(data: zeroFingerprint),
            0,
            occupancy,
            0,
            Float(width) * 0.5,
            Float(height) * 0.5
        )
    }

    let quantized = morphospaceQuantizedFingerprint(
        sample: geometry.centered,
        width: width,
        height: height
    )

    let fingerprintData = Data(quantized)
    return (
        32,
        fingerprintData,
        morphospaceAngularSymmetryDescriptor(
            fingerprint: quantized,
            width: 32,
            height: 32
        ),
        morphospaceHash12(data: fingerprintData),
        geometry.mass,
        occupancy,
        geometry.gyration,
        geometry.centerX,
        geometry.centerY
    )
}

private struct MorphospaceCanonicalKernel {
    let r: Float
    let m: Float
    let s: Float
    let h: Float
    let b: [Float]
    let w: [Float]
    let a: [Float]

    var signature: String {
        let values = [r, m, s, h] + b + w + a
        return values.map { String(format: "%.6f", $0) }.joined(separator: ",")
    }
}

private struct MorphospaceNormalizedPatch: Codable, Sendable {
    let center: [Int]
    let size: Int
}

private struct MorphospaceNormalizedStatePatch: Codable, Sendable {
    let center: [Int]
    let width: Int
    let height: Int
    let channels: Int
    let hash12: String
}

private struct MorphospaceNormalizedInitConfig: Codable, Sendable {
    let patches: [MorphospaceNormalizedPatch]
    let statePatch: MorphospaceNormalizedStatePatch?
    let paramStatePatch: MorphospaceNormalizedStatePatch?
    let aUniformLow: Float
    let aUniformHigh: Float
    let pUniformLow: Float?
    let pUniformHigh: Float?
}

private func morphospaceFloatData(_ values: [Float]) -> Data {
    var data = Data(capacity: values.count * MemoryLayout<Float>.size)
    for value in values {
        var littleEndian = value.bitPattern.littleEndian
        withUnsafeBytes(of: &littleEndian) { rawBytes in
            data.append(contentsOf: rawBytes)
        }
    }
    return data
}

private func morphospaceHash12(data: Data) -> String {
    SHA256.hash(data: data).prefix(6).map { String(format: "%02x", $0) }.joined()
}

struct MorphospaceFieldGeometry: Sendable {
    let mass: Float
    let centerX: Float
    let centerY: Float
    let gyration: Float
    let centered: [Float]
}

private func morphospaceCircularCenterCandidates(profile: [Double]) -> [Float] {
    guard !profile.isEmpty else { return [0] }
    let period = Double(profile.count)
    let total = profile.reduce(0, +)
    let threshold = max(abs(total), 1) * 1e-10
    for harmonic in 1...max(1, profile.count / 2) {
        var real: Double = 0
        var imaginary: Double = 0
        for (index, value) in profile.enumerated() {
            let angle = (Double(index) + 0.5) * 2 * Double.pi * Double(harmonic) / period
            real += value * cos(angle)
            imaginary += value * sin(angle)
        }
        guard hypot(real, imaginary) > threshold else {
            continue
        }
        var phase = atan2(imaginary, real)
        if phase < 0 {
            phase += 2 * Double.pi
        }
        let spacing = period / Double(harmonic)
        let base = phase * period / (2 * Double.pi * Double(harmonic))
        return (0..<harmonic).map { branch in
            Float((base + Double(branch) * spacing).truncatingRemainder(dividingBy: period))
        }
    }
    return profile.indices.map { Float($0) + 0.5 }
}

private func morphospaceWrappedDelta(_ value: Float, period: Float) -> Float {
    value - round(value / period) * period
}

private func morphospaceGyration(
    sample: [Float],
    width: Int,
    height: Int,
    mass: Float,
    centerX: Float,
    centerY: Float,
    useTorus: Bool
) -> Float {
    var accumulator: Float = 0
    for y in 0..<height {
        let rowOffset = y * width
        for x in 0..<width {
            let value = sample[rowOffset + x]
            guard value != 0 else { continue }
            var dx = (Float(x) + 0.5) - centerX
            var dy = (Float(y) + 0.5) - centerY
            if useTorus {
                dx = morphospaceWrappedDelta(dx, period: Float(width))
                dy = morphospaceWrappedDelta(dy, period: Float(height))
            }
            accumulator += value * (dx * dx + dy * dy)
        }
    }
    return accumulator / mass
}

func morphospaceFieldGeometry(
    sample: [Float],
    width: Int,
    height: Int,
    useTorus: Bool
) -> MorphospaceFieldGeometry? {
    guard width > 0, height > 0, sample.count == width * height else {
        fatalError("Morphospace field geometry requires a complete positive-size field.")
    }
    var total: Double = 0
    var momentX: Double = 0
    var momentY: Double = 0
    var profileX = [Double](repeating: 0, count: width)
    var profileY = [Double](repeating: 0, count: height)
    for y in 0..<height {
        for x in 0..<width {
            let value = Double(sample[y * width + x])
            total += value
            momentX += value * (Double(x) + 0.5)
            momentY += value * (Double(y) + 0.5)
            profileX[x] += value
            profileY[y] += value
        }
    }
    guard total > 1e-8 else { return nil }
    let mass = Float(total)
    if useTorus, let first = sample.first, sample.dropFirst().allSatisfy({ $0 == first }) {
        let centerX = Float(width) * 0.5
        let centerY = Float(height) * 0.5
        return MorphospaceFieldGeometry(
            mass: mass,
            centerX: centerX,
            centerY: centerY,
            gyration: morphospaceGyration(
                sample: sample,
                width: width,
                height: height,
                mass: mass,
                centerX: centerX,
                centerY: centerY,
                useTorus: true
            ),
            centered: sample
        )
    }
    let centerCandidatesX: [Float]
    let centerCandidatesY: [Float]
    if useTorus {
        centerCandidatesX = morphospaceCircularCenterCandidates(profile: profileX)
        centerCandidatesY = morphospaceCircularCenterCandidates(profile: profileY)
    } else {
        centerCandidatesX = [Float(momentX / total)]
        centerCandidatesY = [Float(momentY / total)]
    }

    var selected: MorphospaceFieldGeometry?
    var selectedSignature: [UInt8]?
    for centerY in centerCandidatesY {
        for centerX in centerCandidatesX {
            let centered = morphospaceCenteredSample(
                sample: sample,
                width: width,
                height: height,
                centerX: centerX,
                centerY: centerY,
                useTorus: useTorus
            )
            let gyration = morphospaceGyration(
                sample: sample,
                width: width,
                height: height,
                mass: mass,
                centerX: centerX,
                centerY: centerY,
                useTorus: useTorus
            )
            let candidate = MorphospaceFieldGeometry(
                mass: mass,
                centerX: centerX,
                centerY: centerY,
                gyration: gyration,
                centered: centered
            )
            guard centerCandidatesX.count > 1 || centerCandidatesY.count > 1 else {
                return candidate
            }
            let signature = morphospaceQuantizedFingerprint(
                sample: centered,
                width: width,
                height: height
            )
            if let currentSignature = selectedSignature {
                if signature.lexicographicallyPrecedes(currentSignature) {
                    selected = candidate
                    selectedSignature = signature
                } else if signature == currentSignature, let current = selected, gyration < current.gyration {
                    selected = candidate
                }
            } else {
                selected = candidate
                selectedSignature = signature
            }
        }
    }
    guard let selected else {
        fatalError("Morphospace field geometry produced no center candidates.")
    }
    return selected
}

func morphospaceCenteredMassBatch(_ batchData: MassBatchCPU, useTorus: Bool) -> MassBatchCPU {
    guard useTorus else { return batchData }
    var centered: [Float] = []
    centered.reserveCapacity(batchData.flat.count)
    for sampleIndex in 0..<batchData.batch {
        let start = sampleIndex * batchData.sampleSize
        let sample = Array(batchData.flat[start..<(start + batchData.sampleSize)])
        if let geometry = morphospaceFieldGeometry(
            sample: sample,
            width: batchData.width,
            height: batchData.height,
            useTorus: true
        ) {
            centered.append(contentsOf: geometry.centered)
        } else {
            centered.append(contentsOf: sample)
        }
    }
    return MassBatchCPU(
        flat: centered,
        batch: batchData.batch,
        height: batchData.height,
        width: batchData.width,
        sampleSize: batchData.sampleSize
    )
}

private func morphospaceCenteredSample(
    sample: [Float],
    width: Int,
    height: Int,
    centerX: Float,
    centerY: Float,
    useTorus: Bool
) -> [Float] {
    let desiredCenterX = Float(width) * 0.5
    let desiredCenterY = Float(height) * 0.5
    let shiftX = desiredCenterX - centerX
    let shiftY = desiredCenterY - centerY

    func value(x: Int, y: Int) -> Float {
        if useTorus {
            let wrappedX = ((x % width) + width) % width
            let wrappedY = ((y % height) + height) % height
            return sample[wrappedY * width + wrappedX]
        }
        guard x >= 0, x < width, y >= 0, y < height else { return 0 }
        return sample[y * width + x]
    }

    var centered = [Float](repeating: 0, count: sample.count)
    for y in 0..<height {
        let centeredRowOffset = y * width
        for x in 0..<width {
            let sourceX = Float(x) - shiftX
            let sourceY = Float(y) - shiftY
            let x0 = Int(floor(sourceX))
            let y0 = Int(floor(sourceY))
            let fractionX = sourceX - Float(x0)
            let fractionY = sourceY - Float(y0)
            let top = value(x: x0, y: y0) * (1 - fractionX)
                + value(x: x0 + 1, y: y0) * fractionX
            let bottom = value(x: x0, y: y0 + 1) * (1 - fractionX)
                + value(x: x0 + 1, y: y0 + 1) * fractionX
            centered[centeredRowOffset + x] = top * (1 - fractionY) + bottom * fractionY
        }
    }
    return centered
}

private func morphospaceBoxResample(
    sample: [Float],
    width: Int,
    height: Int,
    outputWidth: Int,
    outputHeight: Int
) -> [Float] {
    var reduced = [Float](repeating: 0, count: outputWidth * outputHeight)
    for outY in 0..<outputHeight {
        let y0 = outY * height / outputHeight
        let y1 = max(y0 + 1, (outY + 1) * height / outputHeight)
        for outX in 0..<outputWidth {
            let x0 = outX * width / outputWidth
            let x1 = max(x0 + 1, (outX + 1) * width / outputWidth)
            var sum: Float = 0
            var count = 0
            for y in y0..<y1 {
                let rowOffset = y * width
                for x in x0..<x1 {
                    sum += sample[rowOffset + x]
                    count += 1
                }
            }
            reduced[outY * outputWidth + outX] = count > 0 ? sum / Float(count) : 0
        }
    }
    return reduced
}

private func morphospaceQuantizedFingerprint(
    sample: [Float],
    width: Int,
    height: Int,
    outputWidth: Int = 32,
    outputHeight: Int = 32
) -> [UInt8] {
    let reduced = morphospaceBoxResample(
        sample: sample,
        width: width,
        height: height,
        outputWidth: outputWidth,
        outputHeight: outputHeight
    )
    guard let peak = reduced.max(), peak > 1e-8 else {
        return [UInt8](repeating: 0, count: outputWidth * outputHeight)
    }

    return reduced.map { value in
        let normalized = max(0, min(1, value / peak))
        return UInt8((normalized * 255).rounded())
    }
}

/// High-fidelity sibling of the UInt8 fingerprint for off-line analysis (cubical persistent
/// homology, Zernike moments). Same torus-aware COM centering and box-resample, but emits Float at
/// the requested resolution normalized to peak = 1, so it keeps full dynamic range instead of the
/// 8-bit mass-fraction quantization that collapses the stored fingerprint to a handful of levels.
/// Returns nil for an empty field. Only invoked on opt-in development-trace capture, never on the
/// search/replay hot path.
public func morphospaceCenteredFloatField(
    sample: [Float],
    width: Int,
    height: Int,
    useTorus: Bool,
    outputResolution: Int
) -> [Float]? {
    guard outputResolution > 0 else { return nil }
    guard let geometry = morphospaceFieldGeometry(
        sample: sample,
        width: width,
        height: height,
        useTorus: useTorus
    ) else { return nil }
    let reduced = morphospaceBoxResample(
        sample: geometry.centered,
        width: width,
        height: height,
        outputWidth: outputResolution,
        outputHeight: outputResolution
    )
    guard let peak = reduced.max(), peak > 1e-8 else { return nil }
    return reduced.map { $0 / peak }
}

private func morphospaceAngularSymmetryDescriptor(
    fingerprint: [UInt8],
    width: Int,
    height: Int,
    binCount: Int = 32,
    maxOrder: Int = 8
) -> MorphospaceAngularSymmetryDescriptor {
    guard width > 0, height > 0, fingerprint.count == width * height else {
        fatalError("Angular symmetry descriptor requires a complete fingerprint grid.")
    }
    guard binCount > 0, maxOrder > 0 else {
        fatalError("Angular symmetry descriptor requires positive binCount and maxOrder.")
    }

    let centerX = (Float(width) - 1) * 0.5
    let centerY = (Float(height) - 1) * 0.5
    let twoPi = Float.pi * 2
    var angularProfile = [Float](repeating: 0, count: binCount)
    var total: Float = 0

    for y in 0..<height {
        let rowOffset = y * width
        for x in 0..<width {
            let mass = Float(fingerprint[rowOffset + x])
            if mass <= 0 {
                continue
            }
            total += mass
            let dx = Float(x) - centerX
            let dy = Float(y) - centerY
            var theta = atan2f(dy, dx)
            if theta < 0 {
                theta += twoPi
            }
            let scaled = theta / twoPi * Float(binCount)
            let bin = min(binCount - 1, max(0, Int(floor(scaled))))
            angularProfile[bin] += mass
        }
    }

    guard total > 1e-8 else {
        return MorphospaceAngularSymmetryDescriptor(
            binCount: binCount,
            maxOrder: maxOrder,
            harmonics: Array(repeating: 0, count: maxOrder),
            dominantOrder: nil,
            dominantAmplitude: nil,
            normalizedEntropy: nil
        )
    }

    for index in angularProfile.indices {
        angularProfile[index] /= total
    }

    var harmonics: [Float] = []
    harmonics.reserveCapacity(maxOrder)
    for order in 1...maxOrder {
        var real: Float = 0
        var imag: Float = 0
        for binIndex in 0..<binCount {
            let theta = (Float(binIndex) + 0.5) * twoPi / Float(binCount)
            let weight = angularProfile[binIndex]
            real += weight * cosf(Float(order) * theta)
            imag -= weight * sinf(Float(order) * theta)
        }
        harmonics.append(sqrt(real * real + imag * imag))
    }

    let dominantPair = harmonics.enumerated().max { lhs, rhs in
        lhs.element < rhs.element
    }
    var entropy: Float = 0
    for value in angularProfile where value > 1e-8 {
        entropy -= value * logf(value)
    }
    let normalizedEntropy = entropy / logf(Float(binCount))

    return MorphospaceAngularSymmetryDescriptor(
        binCount: binCount,
        maxOrder: maxOrder,
        harmonics: harmonics,
        dominantOrder: dominantPair.map { $0.offset + 1 },
        dominantAmplitude: dominantPair?.element,
        normalizedEntropy: normalizedEntropy.isFinite ? normalizedEntropy : nil
    )
}

private func mean(_ values: [Int]) -> Float? {
    guard !values.isEmpty else { return nil }
    return Float(values.reduce(0, +)) / Float(values.count)
}

private func std(_ values: [Int]) -> Float? {
    guard !values.isEmpty else { return nil }
    if values.count == 1 {
        return 0
    }
    let meanValue = Float(values.reduce(0, +)) / Float(values.count)
    var sumSquares: Float = 0
    for value in values {
        let delta = Float(value) - meanValue
        sumSquares += delta * delta
    }
    return sqrt(sumSquares / Float(values.count))
}
