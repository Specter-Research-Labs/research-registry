import CryptoKit
import Foundation

public struct CapturedSpecimenComponent: Sendable {
    public let fingerprint: String
    public let sourceStep: Int
    public let width: Int
    public let height: Int
    public let channels: Int
    public let parameterCount: Int
    public let mass: [Float]
    public let params: [Float]
    public let previewStamp: CreatureStamp
    public let metrics: SimulationMetrics

    public init(
        fingerprint: String,
        sourceStep: Int,
        width: Int,
        height: Int,
        channels: Int,
        parameterCount: Int,
        mass: [Float],
        params: [Float],
        previewStamp: CreatureStamp,
        metrics: SimulationMetrics
    ) {
        self.fingerprint = fingerprint
        self.sourceStep = sourceStep
        self.width = width
        self.height = height
        self.channels = channels
        self.parameterCount = parameterCount
        self.mass = mass
        self.params = params
        self.previewStamp = previewStamp
        self.metrics = metrics
    }

    public func savedCreature(
        name: String,
        ownerID: String,
        contract: FlowSandboxWorldContract
    ) -> SavedCreature {
        let center = [contract.gridSize / 2, contract.gridSize / 2]
        let statePatch = InitStatePatchConfig(
            center: center,
            width: width,
            height: height,
            channels: channels,
            values: mass
        )
        let parameterPatch = parameterCount > 0
            ? InitStatePatchConfig(
                center: center,
                width: width,
                height: height,
                channels: parameterCount,
                values: params
            )
            : nil
        return SavedCreature(
            name: name,
            ownerId: ownerID,
            genotype: KernelParams(
                r: contract.kernels.map(\.radius),
                b: contract.kernels.map(\.beta),
                w: contract.kernels.map(\.weights),
                a: contract.kernels.map(\.anchors),
                m: contract.kernels.map(\.center),
                s: contract.kernels.map(\.sigma),
                h: contract.kernels.map(\.gain),
                R: contract.radius
            ),
            initialCondition: InitConfig(
                seed: contract.seed,
                patches: [],
                a_uniform: UniformRange(low: 0, high: 0),
                p_uniform: parameterCount > 0 ? UniformRange(low: 0, high: 0) : nil,
                state_patch: statePatch,
                p_state_patch: parameterPatch
            ),
            initialConditionFamily: "studio-capture",
            metrics: metrics,
            configHash: fingerprint
        )
    }
}

public enum SpecimenCaptureError: LocalizedError, Equatable {
    case invalidSnapshot(String)
    case noMatterNearSelection

    public var errorDescription: String? {
        switch self {
        case .invalidSnapshot(let message):
            return message
        case .noMatterNearSelection:
            return "No organism matter is present in this world."
        }
    }
}

public func captureSpecimenComponent(
    from snapshot: FlowSandboxStateSnapshot,
    near selectedPoint: SIMD2<Int>,
    threshold: Float = 0.02,
    padding: Int = 3,
    wraps: Bool = true
) throws -> CapturedSpecimenComponent {
    let width = snapshot.width
    let height = snapshot.height
    let cellCount = width * height
    guard width > 0, height > 0, snapshot.channels > 0 else {
        throw SpecimenCaptureError.invalidSnapshot("Specimen capture requires a non-empty world.")
    }
    guard snapshot.mass.count == cellCount * snapshot.channels else {
        throw SpecimenCaptureError.invalidSnapshot(
            "Specimen capture expected \(cellCount * snapshot.channels) mass values, got \(snapshot.mass.count)."
        )
    }
    guard snapshot.parameterCount >= 0,
          snapshot.params.count == cellCount * snapshot.parameterCount else {
        throw SpecimenCaptureError.invalidSnapshot(
            "Specimen capture parameter field does not match the world shape."
        )
    }

    let activity = (0..<cellCount).map { cell -> Float in
        let base = cell * snapshot.channels
        return snapshot.mass[base..<(base + snapshot.channels)].reduce(0, +)
    }
    let start = nearestActiveCell(
        to: selectedPoint,
        activity: activity,
        width: width,
        height: height,
        threshold: threshold,
        wraps: wraps
    )
    guard let start else {
        throw SpecimenCaptureError.noMatterNearSelection
    }

    struct QueuePoint {
        let wrappedX: Int
        let wrappedY: Int
        let unwrappedX: Int
        let unwrappedY: Int
    }
    var queue = [QueuePoint(
        wrappedX: start.x,
        wrappedY: start.y,
        unwrappedX: start.x,
        unwrappedY: start.y
    )]
    var cursor = 0
    var visited = Set<Int>()
    visited.insert(start.x * height + start.y)
    var component: [QueuePoint] = []
    let neighbors = [
        (-1, -1), (-1, 0), (-1, 1),
        (0, -1),            (0, 1),
        (1, -1),  (1, 0),  (1, 1),
    ]

    while cursor < queue.count {
        let point = queue[cursor]
        cursor += 1
        component.append(point)
        for (dx, dy) in neighbors {
            let rawX = point.wrappedX + dx
            let rawY = point.wrappedY + dy
            if !wraps, (rawX < 0 || rawX >= width || rawY < 0 || rawY >= height) {
                continue
            }
            let x = positiveModulo(rawX, width)
            let y = positiveModulo(rawY, height)
            let index = x * height + y
            guard activity[index] > threshold, visited.insert(index).inserted else {
                continue
            }
            queue.append(
                QueuePoint(
                    wrappedX: x,
                    wrappedY: y,
                    unwrappedX: point.unwrappedX + dx,
                    unwrappedY: point.unwrappedY + dy
                )
            )
        }
    }

    let resolvedPadding = max(0, padding)
    let minX = (component.map(\.unwrappedX).min() ?? 0) - resolvedPadding
    let maxX = (component.map(\.unwrappedX).max() ?? 0) + resolvedPadding
    let minY = (component.map(\.unwrappedY).min() ?? 0) - resolvedPadding
    let maxY = (component.map(\.unwrappedY).max() ?? 0) + resolvedPadding
    let captureWidth = maxX - minX + 1
    let captureHeight = maxY - minY + 1
    var capturedMass = [Float](
        repeating: 0,
        count: captureWidth * captureHeight * snapshot.channels
    )
    var capturedParams = [Float](
        repeating: 0,
        count: captureWidth * captureHeight * snapshot.parameterCount
    )
    var previewMass = [Float](repeating: 0, count: captureWidth * captureHeight)
    var previewParams = [Float](
        repeating: 0,
        count: captureWidth * captureHeight * snapshot.parameterCount
    )

    for point in component {
        let sourceCell = point.wrappedX * height + point.wrappedY
        let localX = point.unwrappedX - minX
        let localY = point.unwrappedY - minY
        let targetCell = localX * captureHeight + localY
        var aggregate: Float = 0
        for channel in 0..<snapshot.channels {
            let value = snapshot.mass[sourceCell * snapshot.channels + channel]
            capturedMass[targetCell * snapshot.channels + channel] = value
            aggregate += value
        }
        previewMass[targetCell] = min(1, max(0, aggregate))
        for parameter in 0..<snapshot.parameterCount {
            let value = snapshot.params[sourceCell * snapshot.parameterCount + parameter]
            capturedParams[targetCell * snapshot.parameterCount + parameter] = value
            previewParams[targetCell * snapshot.parameterCount + parameter] = value
        }
    }

    let fingerprint = specimenFingerprint(
        width: captureWidth,
        height: captureHeight,
        channels: snapshot.channels,
        parameterCount: snapshot.parameterCount,
        mass: capturedMass,
        params: capturedParams
    )
    let metrics = captureMetrics(
        mass: previewMass,
        width: captureWidth,
        height: captureHeight,
        threshold: threshold
    )
    return CapturedSpecimenComponent(
        fingerprint: fingerprint,
        sourceStep: snapshot.step,
        width: captureWidth,
        height: captureHeight,
        channels: snapshot.channels,
        parameterCount: snapshot.parameterCount,
        mass: capturedMass,
        params: capturedParams,
        previewStamp: CreatureStamp(
            name: "Captured specimen",
            width: captureWidth,
            height: captureHeight,
            mass: previewMass,
            params: previewParams,
            parameterCount: snapshot.parameterCount
        ),
        metrics: metrics
    )
}

private func nearestActiveCell(
    to selectedPoint: SIMD2<Int>,
    activity: [Float],
    width: Int,
    height: Int,
    threshold: Float,
    wraps: Bool
) -> SIMD2<Int>? {
    let selectedX = min(width - 1, max(0, selectedPoint.x))
    let selectedY = min(height - 1, max(0, selectedPoint.y))
    let selectedIndex = selectedX * height + selectedY
    if activity[selectedIndex] > threshold {
        return SIMD2<Int>(selectedX, selectedY)
    }

    var best: (distance: Int, point: SIMD2<Int>)?
    for x in 0..<width {
        for y in 0..<height where activity[x * height + y] > threshold {
            let directX = abs(x - selectedX)
            let directY = abs(y - selectedY)
            let dx = wraps ? min(directX, width - directX) : directX
            let dy = wraps ? min(directY, height - directY) : directY
            let distance = dx * dx + dy * dy
            if best == nil || distance < best!.distance {
                best = (distance, SIMD2<Int>(x, y))
            }
        }
    }
    return best?.point
}

private func positiveModulo(_ value: Int, _ modulus: Int) -> Int {
    let remainder = value % modulus
    return remainder >= 0 ? remainder : remainder + modulus
}

private func specimenFingerprint(
    width: Int,
    height: Int,
    channels: Int,
    parameterCount: Int,
    mass: [Float],
    params: [Float]
) -> String {
    var data = Data()
    for value in [width, height, channels, parameterCount] {
        var encoded = Int64(value).littleEndian
        withUnsafeBytes(of: &encoded) { data.append(contentsOf: $0) }
    }
    for value in mass + params {
        var encoded = value.bitPattern.littleEndian
        withUnsafeBytes(of: &encoded) { data.append(contentsOf: $0) }
    }
    return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

private func captureMetrics(
    mass: [Float],
    width: Int,
    height: Int,
    threshold: Float
) -> SimulationMetrics {
    let count = Float(max(1, mass.count))
    let total = mass.reduce(0, +)
    let mean = total / count
    let variance = mass.reduce(0) { $0 + ($1 - mean) * ($1 - mean) } / count
    let occupiedCount = mass.reduce(0) { count, value in
        count + (value > threshold ? 1 : 0)
    }
    let occupied = Float(occupiedCount) / count
    let energy = mass.reduce(0) { $0 + $1 * $1 } / count
    var centerX: Float = 0
    var centerY: Float = 0
    if total > 0 {
        for x in 0..<width {
            for y in 0..<height {
                let value = mass[x * height + y]
                centerX += Float(x) * value
                centerY += Float(y) * value
            }
        }
        centerX /= total
        centerY /= total
    }
    var gyration: Float = 0
    if total > 0 {
        for x in 0..<width {
            for y in 0..<height {
                let value = mass[x * height + y]
                let dx = Float(x) - centerX
                let dy = Float(y) - centerY
                gyration += value * (dx * dx + dy * dy)
            }
        }
        gyration /= total
    }
    return SimulationMetrics(
        massMean: mean,
        massStd: sqrt(max(0, variance)),
        massMin: mass.min() ?? 0,
        massMax: mass.max() ?? 0,
        occupancyMean: occupied,
        varianceMean: variance,
        energyMean: energy,
        speedMean: 0,
        pathLength: 0,
        displacement: 0,
        sampleCount: 1,
        speedCount: 0,
        gyration: gyration,
        centerVelocity: 0,
        isStable: false,
        occupiedFraction: occupied,
        componentCount: 1,
        largestComponentFraction: 1
    )
}
