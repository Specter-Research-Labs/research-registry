import Foundation
import LeniaCore

public struct LeniaCreature: Identifiable, Equatable, Hashable, Sendable {
    public let id: UUID
    public let seed: Int
    public let score: Float
    public let params: ResolvedParams
    public let sourceNode: String
    public let timestamp: Date

    public init(seed: Int, score: Float, params: ResolvedParams, sourceNode: String) {
        self.id = UUID()
        self.seed = seed
        self.score = score
        self.params = params
        self.sourceNode = sourceNode
        self.timestamp = Date()
    }

    public static func == (lhs: LeniaCreature, rhs: LeniaCreature) -> Bool {
        lhs.id == rhs.id
    }

    public func hash(into hasher: inout Hasher) {
        hasher.combine(id)
    }
}

// MARK: - Conversion from SavedCreature

extension SavedCreature {
    public func toLeniaCreature() -> LeniaCreature {
        let resolvedParams = ResolvedParams(
            r: genotype.r,
            b: genotype.b,
            w: genotype.w,
            a: genotype.a,
            m: genotype.m,
            s: genotype.s,
            h: genotype.h,
            R: genotype.R,
            seed: initialCondition.seed
        )
        return LeniaCreature(
            seed: initialCondition.seed,
            score: metrics.massMean,
            params: resolvedParams,
            sourceNode: ownerId
        )
    }
}
