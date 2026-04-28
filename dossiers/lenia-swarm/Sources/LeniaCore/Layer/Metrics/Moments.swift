import Foundation
import MLX

public struct MomentsConfig: Codable, Sendable {
    public let enabled: Bool
    public let threshold: Float

    public init(enabled: Bool, threshold: Float = 0.01) {
        self.enabled = enabled
        self.threshold = threshold
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        enabled = try container.decode(Bool.self, forKey: .enabled)
        threshold = try container.decodeIfPresent(Float.self, forKey: .threshold) ?? 0.01
    }
}

public struct MomentsBatchResult: Sendable {
    public let hu: [[Float]]
    public let flusser: [[Float]]
    public let mass: [Float]
    public let volume: [Float]
    public let density: [Float]
    public let anisotropy: [Float]

    public init(
        hu: [[Float]],
        flusser: [[Float]],
        mass: [Float],
        volume: [Float],
        density: [Float],
        anisotropy: [Float]
    ) {
        self.hu = hu
        self.flusser = flusser
        self.mass = mass
        self.volume = volume
        self.density = density
        self.anisotropy = anisotropy
    }
}

public func computeMomentsBatch(massMap: MLXArray, config: MomentsConfig) -> MomentsBatchResult {
    guard config.enabled else {
        return MomentsBatchResult(hu: [], flusser: [], mass: [], volume: [], density: [], anisotropy: [])
    }
    return computeMomentsBatch(materialized: materializeMassBatch(massMap), config: config)
}

func computeMomentsBatch(materialized batchData: MassBatchCPU, config: MomentsConfig) -> MomentsBatchResult {
    let flat = batchData.flat
    let batch = batchData.batch
    let height = batchData.height
    let width = batchData.width
    let sampleSize = batchData.sampleSize

    var allHu: [[Float]] = []
    var allFlusser: [[Float]] = []
    var allMass: [Float] = []
    var allVolume: [Float] = []
    var allDensity: [Float] = []
    var allAnisotropy: [Float] = []

    allHu.reserveCapacity(batch)
    allFlusser.reserveCapacity(batch)
    allMass.reserveCapacity(batch)
    allVolume.reserveCapacity(batch)
    allDensity.reserveCapacity(batch)
    allAnisotropy.reserveCapacity(batch)

    for idx in 0..<batch {
        let start = idx * sampleSize

        let raw = rawMoments(flat, offset: start, width: width, height: height)

        let m00 = raw.m00
        allMass.append(m00)

        var vol: Float = 0
        for i in 0..<sampleSize {
            if flat[start + i] > config.threshold { vol += 1 }
        }
        allVolume.append(vol)
        allDensity.append(vol > 0 ? m00 / vol : 0)

        if m00 < 1e-12 {
            allHu.append([Float](repeating: 0, count: 7))
            allFlusser.append([Float](repeating: 0, count: 4))
            allAnisotropy.append(0)
            continue
        }

        let cx = raw.m10 / m00
        let cy = raw.m01 / m00

        let central = centralMoments(flat, offset: start, width: width, height: height, cx: cx, cy: cy)
        allAnisotropy.append(momentAnisotropy(central: central, mass: m00))

        let nu = normalizedCentralMoments(central, m00: m00)

        let hu = huMoments(nu)
        let fl = flusserMoments(nu)

        allHu.append(hu.map { logAbsMoment($0) })
        allFlusser.append(fl.map { logAbsMoment($0) })
    }

    return MomentsBatchResult(
        hu: allHu,
        flusser: allFlusser,
        mass: allMass,
        volume: allVolume,
        density: allDensity,
        anisotropy: allAnisotropy
    )
}

private func momentAnisotropy(central: CentralMoments, mass: Float) -> Float {
    if mass <= 1e-12 { return 0 }

    let covXX = central.mu20 / mass
    let covXY = central.mu11 / mass
    let covYY = central.mu02 / mass
    let trace = covXX + covYY
    if trace <= 1e-12 { return 0 }

    let discSquared = max((covXX - covYY) * (covXX - covYY) + 4 * covXY * covXY, 0)
    let disc = sqrt(discSquared)
    return min(max(disc / trace, 0), 1)
}

private func logAbsMoment(_ value: Float) -> Float {
    let absVal = abs(value)
    if absVal < 1e-30 { return -30.0 }
    return log10(absVal)
}

private struct RawMoments {
    let m00: Float, m10: Float, m01: Float
    let m20: Float, m11: Float, m02: Float
    let m30: Float, m21: Float, m12: Float, m03: Float
}

private func rawMoments(_ data: [Float], offset: Int, width: Int, height: Int) -> RawMoments {
    var m00: Float = 0, m10: Float = 0, m01: Float = 0
    var m20: Float = 0, m11: Float = 0, m02: Float = 0
    var m30: Float = 0, m21: Float = 0, m12: Float = 0, m03: Float = 0

    for y in 0..<height {
        let fy = Float(y)
        let fy2 = fy * fy
        let fy3 = fy2 * fy
        let rowOffset = offset + y * width
        for x in 0..<width {
            let v = data[rowOffset + x]
            if v == 0 { continue }
            let fx = Float(x)
            let fx2 = fx * fx

            m00 += v
            m10 += fx * v
            m01 += fy * v
            m20 += fx2 * v
            m11 += fx * fy * v
            m02 += fy2 * v
            m30 += fx2 * fx * v
            m21 += fx2 * fy * v
            m12 += fx * fy2 * v
            m03 += fy3 * v
        }
    }

    return RawMoments(
        m00: m00, m10: m10, m01: m01,
        m20: m20, m11: m11, m02: m02,
        m30: m30, m21: m21, m12: m12, m03: m03
    )
}

private struct CentralMoments {
    let mu20: Float, mu11: Float, mu02: Float
    let mu30: Float, mu21: Float, mu12: Float, mu03: Float
    let mu40: Float, mu31: Float, mu22: Float, mu13: Float, mu04: Float
}

private func centralMoments(
    _ data: [Float],
    offset: Int,
    width: Int,
    height: Int,
    cx: Float,
    cy: Float
) -> CentralMoments {
    var mu20: Float = 0, mu11: Float = 0, mu02: Float = 0
    var mu30: Float = 0, mu21: Float = 0, mu12: Float = 0, mu03: Float = 0
    var mu40: Float = 0, mu31: Float = 0, mu22: Float = 0, mu13: Float = 0, mu04: Float = 0

    for y in 0..<height {
        let dy = Float(y) - cy
        let dy2 = dy * dy
        let dy3 = dy2 * dy
        let dy4 = dy2 * dy2
        let rowOffset = offset + y * width
        for x in 0..<width {
            let v = data[rowOffset + x]
            if v == 0 { continue }
            let dx = Float(x) - cx
            let dx2 = dx * dx
            let dx3 = dx2 * dx
            let dx4 = dx2 * dx2

            mu20 += dx2 * v
            mu11 += dx * dy * v
            mu02 += dy2 * v
            mu30 += dx3 * v
            mu21 += dx2 * dy * v
            mu12 += dx * dy2 * v
            mu03 += dy3 * v
            mu40 += dx4 * v
            mu31 += dx3 * dy * v
            mu22 += dx2 * dy2 * v
            mu13 += dx * dy3 * v
            mu04 += dy4 * v
        }
    }

    return CentralMoments(
        mu20: mu20, mu11: mu11, mu02: mu02,
        mu30: mu30, mu21: mu21, mu12: mu12, mu03: mu03,
        mu40: mu40, mu31: mu31, mu22: mu22, mu13: mu13, mu04: mu04
    )
}

private struct NormalizedMoments {
    let nu20: Float, nu11: Float, nu02: Float
    let nu30: Float, nu21: Float, nu12: Float, nu03: Float
    let nu40: Float, nu31: Float, nu22: Float, nu13: Float, nu04: Float
}

// nu_pq = mu_pq / m00^((p+q)/2 + 1)
private func normalizedCentralMoments(_ central: CentralMoments, m00: Float) -> NormalizedMoments {
    let inv2 = 1.0 / (m00 * m00)
    let inv2_5 = 1.0 / (m00 * m00 * sqrt(m00))
    let inv3 = 1.0 / (m00 * m00 * m00)

    return NormalizedMoments(
        nu20: central.mu20 * inv2,
        nu11: central.mu11 * inv2,
        nu02: central.mu02 * inv2,
        nu30: central.mu30 * inv2_5,
        nu21: central.mu21 * inv2_5,
        nu12: central.mu12 * inv2_5,
        nu03: central.mu03 * inv2_5,
        nu40: central.mu40 * inv3,
        nu31: central.mu31 * inv3,
        nu22: central.mu22 * inv3,
        nu13: central.mu13 * inv3,
        nu04: central.mu04 * inv3
    )
}

// Hu (1962) -- 7 rotation-invariant moments from 2nd and 3rd order
private func huMoments(_ n: NormalizedMoments) -> [Float] {
    let h1 = n.nu20 + n.nu02

    let h2 = (n.nu20 - n.nu02) * (n.nu20 - n.nu02) + 4 * n.nu11 * n.nu11

    let h3 = (n.nu30 - 3 * n.nu12) * (n.nu30 - 3 * n.nu12)
        + (3 * n.nu21 - n.nu03) * (3 * n.nu21 - n.nu03)

    let h4 = (n.nu30 + n.nu12) * (n.nu30 + n.nu12)
        + (n.nu21 + n.nu03) * (n.nu21 + n.nu03)

    let p30_12 = n.nu30 + n.nu12
    let p21_03 = n.nu21 + n.nu03
    let p30_12_sq = p30_12 * p30_12
    let p21_03_sq = p21_03 * p21_03
    let h5 = (n.nu30 - 3 * n.nu12) * p30_12 * (p30_12_sq - 3 * p21_03_sq)
        + (3 * n.nu21 - n.nu03) * p21_03 * (3 * p30_12_sq - p21_03_sq)

    let h6 = (n.nu20 - n.nu02) * (p30_12_sq - p21_03_sq)
        + 4 * n.nu11 * p30_12 * p21_03

    let h7 = (3 * n.nu21 - n.nu03) * p30_12 * (p30_12_sq - 3 * p21_03_sq)
        - (n.nu30 - 3 * n.nu12) * p21_03 * (3 * p30_12_sq - p21_03_sq)

    return [h1, h2, h3, h4, h5, h6, h7]
}

// Flusser rotation invariants from 4th order moments
// Following adtool/FlowLeniaStatistics.py (flusser9-flusser12)
private func flusserMoments(_ n: NormalizedMoments) -> [Float] {
    let c = n.nu30 + n.nu12
    let e = n.nu03 + n.nu21
    let d = n.nu30 - n.nu12
    let f = n.nu03 - n.nu21
    let i4 = n.nu40 + n.nu04
    let j = n.nu40 - n.nu04
    let k = n.nu31 + n.nu13
    let l = n.nu31 - n.nu13
    let yVar = 2 * n.nu22

    // f1: 4th-order isotropic magnitude
    let f1 = i4 + yVar

    // f2: mixed 3rd-4th order coupling
    let f2 = j * (c * c - e * e) + 4 * l * d * f

    // f3: mixed 3rd-4th order coupling (orthogonal to f2)
    let f3 = -2 * k * (c * c - e * e) - 2 * j * d * f

    // f4: higher-order combination
    let m = i4 - 3 * yVar
    let c2 = c * c
    let e2 = e * e
    let t1 = (c2 - e2) * (c2 - e2) - 4 * c2 * e2
    let t2 = 4 * c * e * (c2 - e2)
    let f4 = 4 * l * t2 + m * t1

    return [f1, f2, f3, f4]
}
