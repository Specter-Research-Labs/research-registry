import ArgumentParser
import Foundation
import LeniaCore
import SQLite3

struct CompendiumBackfillCommand: ParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "backfill",
        abstract: "Heal compendium gaps: orphan runs, provenance, taxonomy, trait labels"
    )

    @Option(name: [.customLong("db"), .customLong("db-path")], help: "SQLite compendium DB path")
    var dbPath: String

    func run() throws {
        let resolved = (dbPath as NSString).expandingTildeInPath
        _ = try SQLiteIndexer(path: resolved, rebuild: false)

        let db = try SQLiteDB(path: resolved)
        let schemaVersion = try db.scalarInt("SELECT schema_version FROM compendium_meta LIMIT 1")
        if schemaVersion != compendiumSchemaVersion {
            throw ValidationError("Schema version \(schemaVersion) != expected \(compendiumSchemaVersion)")
        }

        try backfillOrphanRuns(db: db)
        try backfillProvenance(db: db)
        try backfillTaxonomy(db: db)
        try backfillTraitLabels(db: db)

        let remaining = try db.scalarInt("""
            SELECT COUNT(*) FROM creatures
            WHERE is_stable = 1 AND (taxonomy_family_id IS NULL OR source_mode IS NULL OR trait_labels_json IS NULL)
        """)
        if remaining > 0 {
            print("backfill: \(remaining) stable creatures still incomplete")
        } else {
            print("backfill: all stable creatures complete")
        }
    }

    // MARK: - Orphan Runs

    private func backfillOrphanRuns(db: SQLiteDB) throws {
        let select = try db.prepare("""
            SELECT DISTINCT cr.run_id FROM creatures cr
            WHERE NOT EXISTS (SELECT 1 FROM runs r WHERE r.run_id = cr.run_id)
            ORDER BY cr.run_id
        """)
        defer { sqlite3_finalize(select) }

        var orphanRunIds: [String] = []
        while sqlite3_step(select) == SQLITE_ROW {
            guard let c = sqlite3_column_text(select, 0) else { continue }
            orphanRunIds.append(String(cString: c))
        }

        guard !orphanRunIds.isEmpty else {
            print("runs: no orphans")
            return
        }

        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let now = formatter.string(from: Date())

        try db.withImmediateTransaction {
            let insert = try db.prepare("""
                INSERT OR IGNORE INTO runs (run_id, run_name, run_dir, indexed_at)
                VALUES (?, ?, ?, ?)
            """)
            defer { sqlite3_finalize(insert) }

            for runId in orphanRunIds {
                let runName = stripHostPrefix(runId)
                sqlite3_reset(insert)
                sqlite3_clear_bindings(insert)
                db.bindText(insert, index: 1, value: runId)
                db.bindText(insert, index: 2, value: runName)
                db.bindText(insert, index: 3, value: "unknown")
                db.bindText(insert, index: 4, value: now)
                try db.step(insert)
            }
        }

        print("runs: backfilled \(orphanRunIds.count) orphan run records")
    }

    // MARK: - Provenance

    private static let provenanceRules: [(pattern: String, sourceMode: String, sourceAlgorithm: String)] = [
        ("nnea-fast", "nnea", "nnea-fast"),
        ("crossmap-fast", "crossmap", "crossmap-fast"),
        ("complexity-stable", "search", "complexity-stable"),
        ("glider-family", "glider-family", "glider-family"),
        ("motile-random", "search", "motile-random"),
        ("embed-food-fast", "search", "embed-food-fast"),
        ("activity-stable", "search", "activity-stable"),
    ]

    private func backfillProvenance(db: SQLiteDB) throws {
        let selectRuns = try db.prepare("SELECT run_id, source_mode, source_algorithm FROM runs ORDER BY run_id")
        defer { sqlite3_finalize(selectRuns) }

        var allRuns: [(id: String, hasProvenance: Bool, sourceMode: String?, sourceAlgorithm: String?)] = []
        while sqlite3_step(selectRuns) == SQLITE_ROW {
            guard let c = sqlite3_column_text(selectRuns, 0) else { continue }
            let mode = sqlite3_column_text(selectRuns, 1).map { String(cString: $0) }
            let algo = sqlite3_column_text(selectRuns, 2).map { String(cString: $0) }
            allRuns.append((id: String(cString: c), hasProvenance: mode != nil, sourceMode: mode, sourceAlgorithm: algo))
        }

        var matched = 0
        var unmatchedRunIds: [String] = []

        try db.withImmediateTransaction {
            let updateCreatures = try db.prepare("""
                UPDATE creatures SET source_mode = ?, source_algorithm = ?
                WHERE run_id = ? AND source_mode IS NULL
            """)
            defer { sqlite3_finalize(updateCreatures) }

            let updateRuns = try db.prepare("""
                UPDATE runs SET source_mode = ?, source_algorithm = ?
                WHERE run_id = ? AND source_mode IS NULL
            """)
            defer { sqlite3_finalize(updateRuns) }

            for run in allRuns {
                let sourceMode: String
                let sourceAlgorithm: String

                if let existing = run.sourceMode, let existingAlgo = run.sourceAlgorithm {
                    sourceMode = existing
                    sourceAlgorithm = existingAlgo
                } else {
                    let bare = stripHostPrefix(run.id)
                    guard let rule = Self.provenanceRules.first(where: { bare.hasPrefix($0.pattern) }) else {
                        unmatchedRunIds.append(run.id)
                        continue
                    }
                    sourceMode = rule.sourceMode
                    sourceAlgorithm = rule.sourceAlgorithm
                }

                for stmt in [updateCreatures, updateRuns] {
                    sqlite3_reset(stmt)
                    sqlite3_clear_bindings(stmt)
                    db.bindText(stmt, index: 1, value: sourceMode)
                    db.bindText(stmt, index: 2, value: sourceAlgorithm)
                    db.bindText(stmt, index: 3, value: run.id)
                    try db.step(stmt)
                }
                matched += 1
            }
        }

        print("provenance: processed \(matched) runs")
        if !unmatchedRunIds.isEmpty {
            print("provenance: \(unmatchedRunIds.count) runs did not match any pattern:")
            for id in unmatchedRunIds {
                print("  \(id)")
            }
        }
    }

    // MARK: - Taxonomy

    private func backfillTaxonomy(db: SQLiteDB) throws {
        let missing = try db.scalarInt("""
            SELECT COUNT(*) FROM creatures
            WHERE taxonomy_family_id IS NULL AND genotype_json IS NOT NULL AND metrics_json IS NOT NULL
        """)
        guard missing > 0 else {
            print("taxonomy: nothing to backfill")
            return
        }
        print("taxonomy: \(missing) creatures need assignment — run `compendium taxonomy --db <path>` to fill")
    }

    // MARK: - Trait Labels

    private func backfillTraitLabels(db: SQLiteDB) throws {
        let select = try db.prepare("""
            SELECT id, speed_mean, center_velocity, path_length, displacement,
                   mass_mean, complexity_mean, genotype_json, morphometrics_json
            FROM creatures
            WHERE is_stable = 1 AND trait_labels_json IS NULL
            ORDER BY id ASC
        """)
        defer { sqlite3_finalize(select) }

        let decoder = JSONDecoder()
        var assignments: [(id: String, labels: [String])] = []

        while sqlite3_step(select) == SQLITE_ROW {
            guard let idC = sqlite3_column_text(select, 0) else { continue }
            let id = String(cString: idC)

            let speed = sqlite3_column_type(select, 2) != SQLITE_NULL
                ? Float(sqlite3_column_double(select, 2)) : Float(sqlite3_column_double(select, 1))
            let pathLength = Float(sqlite3_column_double(select, 3))
            let displacement = Float(sqlite3_column_double(select, 4))
            let mass = Float(sqlite3_column_double(select, 5))
            let complexity = sqlite3_column_type(select, 6) != SQLITE_NULL
                ? Float(sqlite3_column_double(select, 6)) : nil

            var kernelCount = 1
            if let genotypeC = sqlite3_column_text(select, 7) {
                if let genotype = try? decoder.decode(KernelParams.self, from: Data(String(cString: genotypeC).utf8)) {
                    kernelCount = genotype.r.count
                }
            }

            let tortuosity: Float
            if let morphC = sqlite3_column_text(select, 8),
               let morphometrics = try? decoder.decode(Morphometrics.self, from: Data(String(cString: morphC).utf8)),
               let morphTortuosity = morphometrics.pathTortuosity {
                tortuosity = morphTortuosity
            } else {
                let eps: Float = 1e-6
                tortuosity = displacement > eps ? pathLength / displacement : 0.0
            }

            let labels = buildTraitLabels(
                speed: speed, tortuosity: tortuosity, mass: mass,
                complexity: complexity, kernelCount: kernelCount
            )
            assignments.append((id: id, labels: labels))
        }

        guard !assignments.isEmpty else {
            print("traits: nothing to backfill")
            return
        }

        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]

        try db.withImmediateTransaction {
            let update = try db.prepare("UPDATE creatures SET trait_labels_json = ? WHERE id = ?")
            defer { sqlite3_finalize(update) }

            for assignment in assignments {
                let json = try encoder.encode(assignment.labels)
                let jsonString = String(data: json, encoding: .utf8)!
                sqlite3_reset(update)
                sqlite3_clear_bindings(update)
                db.bindText(update, index: 1, value: jsonString)
                db.bindText(update, index: 2, value: assignment.id)
                try db.step(update)
            }
        }

        print("traits: assigned labels to \(assignments.count) creatures")
    }

    // MARK: - Helpers

    private func stripHostPrefix(_ runKey: String) -> String {
        if let idx = runKey.range(of: "::") {
            return String(runKey[idx.upperBound...])
        }
        return runKey
    }
}

private func buildTraitLabels(
    speed: Float,
    tortuosity: Float,
    mass: Float,
    complexity: Float?,
    kernelCount: Int
) -> [String] {
    var labels: [String] = []

    if speed >= 0.008 {
        labels.append("translator")
    } else if speed >= 0.002 {
        labels.append(tortuosity >= 4.0 ? "wanderer" : "glider")
    } else if tortuosity >= 8.0 {
        labels.append("eddy")
    } else {
        labels.append("drifter")
    }

    if speed >= 0.006 {
        labels.append("fast")
    } else if speed >= 0.002 {
        labels.append("motile")
    } else if speed >= 0.0005 {
        labels.append("slow")
    } else {
        labels.append("still")
    }

    switch kernelCount {
    case ..<2: labels.append("soliton")
    case 2: labels.append("pair")
    case 3: labels.append("triplet")
    default: labels.append("polyform")
    }

    if mass >= 400 {
        labels.append("massive")
    } else if mass < 150 {
        labels.append("compact")
    }

    if let cx = complexity {
        if cx >= 0.12 {
            labels.append("complex")
        } else if cx < 0.05 {
            labels.append("simple")
        }
    }

    if tortuosity >= 10.0 {
        labels.append("looper")
    } else if tortuosity < 1.5 && speed >= 0.002 {
        labels.append("linear")
    }

    labels.sort()
    return labels
}
