import ArgumentParser
import Foundation
import LeniaCore
import SQLite3

struct TaxonomyCommand: ParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "taxonomy",
        abstract: "Assign deterministic family/genus/species IDs in a compendium database"
    )

    @Option(name: [.customLong("db"), .customLong("db-path")], help: "SQLite compendium DB path")
    var dbPath: String

    @Flag(name: .long, help: "Restrict taxonomy assignment to stable creatures")
    var stableOnly: Bool = false

    @Flag(name: .long, help: "Overwrite existing taxonomy values")
    var force: Bool = false

    func run() throws {
        let resolved = (dbPath as NSString).expandingTildeInPath
        _ = try SQLiteIndexer(path: resolved, rebuild: false)

        let db = try SQLiteDB(path: resolved)
        guard try db.tableExists("compendium_meta") else {
            throw ValidationError("Missing compendium_meta table.")
        }

        let schemaVersion = try db.scalarInt("SELECT schema_version FROM compendium_meta LIMIT 1")
        if schemaVersion != compendiumSchemaVersion {
            throw ValidationError("Compendium schema version \(schemaVersion) does not match expected \(compendiumSchemaVersion).")
        }

        let sql = """
        SELECT id, genotype_json, metrics_json, morphometrics_json,
               taxonomy_family_id, taxonomy_genus_id, taxonomy_species_id
        FROM creatures
        WHERE (? = 0 OR is_stable = 1)
        ORDER BY id ASC
        """
        let select = try db.prepare(sql)
        defer { sqlite3_finalize(select) }
        sqlite3_bind_int(select, 1, stableOnly ? 1 : 0)

        let decoder = JSONDecoder()
        var assignments: [TaxonomyAssignment] = []
        while sqlite3_step(select) == SQLITE_ROW {
            guard let idC = sqlite3_column_text(select, 0),
                  let genotypeC = sqlite3_column_text(select, 1),
                  let metricsC = sqlite3_column_text(select, 2) else {
                continue
            }

            let hasExisting = sqlite3_column_type(select, 4) != SQLITE_NULL
                || sqlite3_column_type(select, 5) != SQLITE_NULL
                || sqlite3_column_type(select, 6) != SQLITE_NULL
            if hasExisting && !force {
                continue
            }

            let id = String(cString: idC)
            let genotype = try decoder.decode(KernelParams.self, from: Data(String(cString: genotypeC).utf8))
            let metrics = try decoder.decode(SimulationMetrics.self, from: Data(String(cString: metricsC).utf8))
            let morphometrics: Morphometrics?
            if let morphC = sqlite3_column_text(select, 3) {
                morphometrics = try decoder.decode(Morphometrics.self, from: Data(String(cString: morphC).utf8))
            } else {
                morphometrics = nil
            }

            assignments.append(buildAssignment(id: id, genotype: genotype, metrics: metrics, morphometrics: morphometrics))
        }

        guard !assignments.isEmpty else {
            print("Taxonomy: no rows updated")
            return
        }

        try db.withImmediateTransaction {
            let update = try db.prepare("""
                UPDATE creatures
                SET taxonomy_family_id = ?,
                    taxonomy_genus_id = ?,
                    taxonomy_species_id = ?,
                    taxonomy_confidence = ?,
                    taxonomy_method = ?,
                    taxonomy_version = ?
                WHERE id = ?
            """)
            defer { sqlite3_finalize(update) }

            for assignment in assignments {
                sqlite3_reset(update)
                sqlite3_clear_bindings(update)
                db.bindText(update, index: 1, value: assignment.familyId)
                db.bindText(update, index: 2, value: assignment.genusId)
                db.bindText(update, index: 3, value: assignment.speciesId)
                db.bindDouble(update, index: 4, value: assignment.confidence)
                db.bindText(update, index: 5, value: assignment.method)
                db.bindInt(update, index: 6, value: assignment.version)
                db.bindText(update, index: 7, value: assignment.id)
                try db.step(update)
            }
        }

        let families = Set(assignments.map(\.familyId)).count
        let genera = Set(assignments.map(\.genusId)).count
        let species = Set(assignments.map(\.speciesId)).count
        print("Taxonomy: updated \(assignments.count) creatures (\(families) families, \(genera) genera, \(species) species)")
    }

    private func buildAssignment(
        id: String,
        genotype: KernelParams,
        metrics: SimulationMetrics,
        morphometrics: Morphometrics?
    ) -> TaxonomyAssignment {
        let kernelCount = genotype.r.count
        let speed = metrics.centerVelocity
        let tortuosity = morphometrics?.pathTortuosity ?? fallbackTortuosity(metrics: metrics)
        let complexity = metrics.complexityMean ?? 0.0
        let mass = metrics.massMean

        let motionClass: String
        if speed >= 0.008 {
            motionClass = "translator"
        } else if speed >= 0.002 {
            motionClass = tortuosity >= 4.0 ? "wanderer" : "glider"
        } else if tortuosity >= 8.0 {
            motionClass = "eddy"
        } else {
            motionClass = "drifter"
        }

        let structureClass: String
        switch kernelCount {
        case ..<2:
            structureClass = "soliton"
        case 2:
            structureClass = "pair"
        case 3:
            structureClass = "triplet"
        default:
            structureClass = "polyform"
        }

        let familyId = "fam-\(motionClass)-\(structureClass)"
        let genusId = [
            familyId,
            speedBand(speed),
            tortuosityBand(tortuosity),
            complexityBand(complexity),
            massBand(mass),
        ].joined(separator: ".")
        let speciesId = "\(genusId).\(speciesFingerprint(genotype))"

        let confidence: Double = morphometrics == nil ? 0.72 : 0.86
        return TaxonomyAssignment(
            id: id,
            familyId: familyId,
            genusId: genusId,
            speciesId: speciesId,
            confidence: confidence,
            method: "lenia-swarm:taxonomy-heuristic",
            version: 1
        )
    }

    private func fallbackTortuosity(metrics: SimulationMetrics) -> Float {
        let eps: Float = 1e-6
        guard metrics.displacement > eps else { return 0.0 }
        return metrics.pathLength / metrics.displacement
    }

    private func speedBand(_ speed: Float) -> String {
        switch speed {
        case ..<0.0005:
            return "speed-still"
        case ..<0.002:
            return "speed-slow"
        case ..<0.006:
            return "speed-motile"
        default:
            return "speed-fast"
        }
    }

    private func tortuosityBand(_ tortuosity: Float) -> String {
        switch tortuosity {
        case ..<1.5:
            return "path-straight"
        case ..<4.0:
            return "path-curved"
        case ..<10.0:
            return "path-meander"
        default:
            return "path-loop"
        }
    }

    private func complexityBand(_ complexity: Float) -> String {
        switch complexity {
        case ..<0.05:
            return "cx-low"
        case ..<0.12:
            return "cx-mid"
        default:
            return "cx-high"
        }
    }

    private func massBand(_ mass: Float) -> String {
        switch mass {
        case ..<150:
            return "mass-small"
        case ..<400:
            return "mass-medium"
        default:
            return "mass-large"
        }
    }

    private func speciesFingerprint(_ genotype: KernelParams) -> String {
        let vector = canonicalGenotypeVector(genotype)
        let rounded = vector.map { String(format: "%.3f", $0) }.joined(separator: ",")
        var hash: UInt64 = 0xcbf29ce484222325
        for byte in rounded.utf8 {
            hash ^= UInt64(byte)
            hash &*= 0x100000001b3
        }
        return String(format: "%010llx", hash)
    }

    private func canonicalGenotypeVector(_ params: KernelParams) -> [Float] {
        var kernels: [CanonicalKernel] = []
        kernels.reserveCapacity(params.r.count)
        for idx in 0..<params.r.count {
            kernels.append(CanonicalKernel(
                r: params.r[idx],
                m: params.m[idx],
                s: params.s[idx],
                h: params.h[idx],
                b: params.b[idx],
                w: params.w[idx],
                a: params.a[idx]
            ))
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
}

private struct TaxonomyAssignment {
    let id: String
    let familyId: String
    let genusId: String
    let speciesId: String
    let confidence: Double
    let method: String
    let version: Int
}

private struct CanonicalKernel {
    let r: Float
    let m: Float
    let s: Float
    let h: Float
    let b: [Float]
    let w: [Float]
    let a: [Float]

    var signature: CanonicalKernelSignature {
        CanonicalKernelSignature(
            r: r,
            m: m,
            s: s,
            h: h,
            bMean: b.isEmpty ? 0.0 : b.reduce(0, +) / Float(b.count),
            bMax: b.max() ?? 0.0,
            wMean: w.isEmpty ? 0.0 : w.reduce(0, +) / Float(w.count),
            wMax: w.max() ?? 0.0,
            aMean: a.isEmpty ? 0.0 : a.reduce(0, +) / Float(a.count),
            aMax: a.max() ?? 0.0
        )
    }
}

private struct CanonicalKernelSignature: Comparable {
    let r: Float
    let m: Float
    let s: Float
    let h: Float
    let bMean: Float
    let bMax: Float
    let wMean: Float
    let wMax: Float
    let aMean: Float
    let aMax: Float

    static func < (lhs: CanonicalKernelSignature, rhs: CanonicalKernelSignature) -> Bool {
        let left = [lhs.r, lhs.m, lhs.s, lhs.h, lhs.bMean, lhs.bMax, lhs.wMean, lhs.wMax, lhs.aMean, lhs.aMax]
        let right = [rhs.r, rhs.m, rhs.s, rhs.h, rhs.bMean, rhs.bMax, rhs.wMean, rhs.wMax, rhs.aMean, rhs.aMax]
        for (l, r) in zip(left, right) {
            if l < r { return true }
            if l > r { return false }
        }
        return false
    }
}
