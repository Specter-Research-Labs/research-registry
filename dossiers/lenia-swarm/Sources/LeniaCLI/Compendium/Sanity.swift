import ArgumentParser
import Foundation
import LeniaCore
import SQLite3

struct CompendiumSanityCommand: ParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "sanity",
        abstract: "Sanity-check a SQLite compendium database"
    )

    @Option(name: [.customLong("db"), .customLong("db-path")], help: "SQLite compendium DB path")
    var dbPath: String

    func run() throws {
        let db = try SQLiteDB(path: (dbPath as NSString).expandingTildeInPath)

        let requiredTables = [
            "compendium_meta",
            "runs",
            "campaigns",
            "creatures",
            "exports",
            "results",
            "specimens",
            "attractor_nodes",
            "attractor_memberships",
            "perturbation_trials",
            "transition_edges",
        ]
        for table in requiredTables where try !db.tableExists(table) {
            throw ValidationError("Missing required table: \(table)")
        }

        guard try db.scalarInt("SELECT COUNT(*) FROM compendium_meta") > 0 else {
            throw ValidationError("compendium_meta has no rows")
        }
        let schemaVersion = try db.scalarInt("SELECT schema_version FROM compendium_meta LIMIT 1")
        if schemaVersion != compendiumSchemaVersion {
            throw ValidationError("Compendium schema version \(schemaVersion) does not match expected \(compendiumSchemaVersion)")
        }

        let runs = try db.scalarInt("SELECT COUNT(*) FROM runs")
        let campaigns = try db.scalarInt("SELECT COUNT(*) FROM campaigns")
        let creatures = try db.scalarInt("SELECT COUNT(*) FROM creatures")
        let stableCreatures = try db.scalarInt("SELECT COUNT(*) FROM creatures WHERE is_stable = 1")
        let exports = try db.scalarInt("SELECT COUNT(*) FROM exports")
        let results = try db.scalarInt("SELECT COUNT(*) FROM results")
        print("Compendium: runs=\(runs) campaigns=\(campaigns) creatures=\(creatures) stable=\(stableCreatures) exports=\(exports) results=\(results)")

        let referentialIssues = try issueCounts(db: db, queries: [
            ("orphan_campaigns", """
                SELECT COUNT(*) FROM campaigns c
                WHERE NOT EXISTS (SELECT 1 FROM runs r WHERE r.run_id = c.run_id)
            """),
            ("orphan_creatures", """
                SELECT COUNT(*) FROM creatures cr
                WHERE NOT EXISTS (SELECT 1 FROM runs r WHERE r.run_id = cr.run_id)
            """),
            ("orphan_exports_by_creature", """
                SELECT COUNT(*) FROM exports e
                WHERE NOT EXISTS (SELECT 1 FROM creatures c WHERE c.id = e.creature_id)
            """),
            ("orphan_exports_by_run", """
                SELECT COUNT(*) FROM exports e
                WHERE NOT EXISTS (SELECT 1 FROM runs r WHERE r.run_id = e.run_id)
            """),
            ("orphan_results_by_run", """
                SELECT COUNT(*) FROM results res
                WHERE NOT EXISTS (SELECT 1 FROM runs r WHERE r.run_id = res.run_id)
            """),
            ("orphan_creatures_by_campaign", """
                SELECT COUNT(*) FROM creatures cr
                WHERE cr.campaign_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM campaigns c
                      WHERE c.run_id = cr.run_id AND c.campaign_id = cr.campaign_id
                  )
            """),
            ("orphan_exports_by_campaign", """
                SELECT COUNT(*) FROM exports e
                WHERE e.campaign_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM campaigns c
                      WHERE c.run_id = e.run_id AND c.campaign_id = e.campaign_id
                  )
            """),
            ("orphan_results_by_campaign", """
                SELECT COUNT(*) FROM results res
                WHERE res.campaign_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM campaigns c
                      WHERE c.run_id = res.run_id AND c.campaign_id = res.campaign_id
                  )
            """)
        ])
        print("Referential: \(formattedIssues(referentialIssues))")

        let completenessIssues = try issueCounts(db: db, queries: [
            ("stable_missing_taxonomy", """
                SELECT COUNT(*) FROM creatures
                WHERE is_stable = 1 AND taxonomy_family_id IS NULL
            """),
            ("missing_source_mode", "SELECT COUNT(*) FROM creatures WHERE source_mode IS NULL"),
            ("stable_missing_morphometrics", """
                SELECT COUNT(*) FROM creatures
                WHERE is_stable = 1 AND morphometrics_json IS NULL
            """),
            ("stable_missing_trait_labels", """
                SELECT COUNT(*) FROM creatures
                WHERE is_stable = 1 AND trait_labels_json IS NULL
            """)
        ])
        let completeness = Dictionary(uniqueKeysWithValues: completenessIssues)
        print("""
        Completeness (stable): missing_taxonomy=\(completeness["stable_missing_taxonomy"] ?? 0) missing_morphometrics=\(completeness["stable_missing_morphometrics"] ?? 0)         missing_trait_labels=\(completeness["stable_missing_trait_labels"] ?? 0)
        Completeness (all): missing_source_mode=\(completeness["missing_source_mode"] ?? 0)
        """)

        try reportGapsPerRun(db: db)

        let failures = (referentialIssues + completenessIssues)
            .filter { $0.1 > 0 }
            .map { "\($0.0)=\($0.1)" }
        if !failures.isEmpty {
            throw ValidationError("Compendium invariants failed: \(failures.joined(separator: ", "))")
        }

        print("Sanity: all checks passed")
    }

    private func issueCounts(db: SQLiteDB, queries: [(String, String)]) throws -> [(String, Int)] {
        try queries.map { ($0.0, try db.scalarInt($0.1)) }
    }

    private func formattedIssues(_ issues: [(String, Int)]) -> String {
        issues.map { "\($0.0)=\($0.1)" }.joined(separator: " ")
    }

    private func reportGapsPerRun(db: SQLiteDB) throws {
        let stmt = try db.prepare("""
            SELECT r.run_id,
                   COUNT(*) AS total,
                   SUM(CASE WHEN c.is_stable = 1 THEN 1 ELSE 0 END) AS stable,
                   SUM(CASE WHEN c.taxonomy_family_id IS NULL AND c.is_stable = 1 THEN 1 ELSE 0 END) AS no_taxonomy,
                   SUM(CASE WHEN c.source_mode IS NULL THEN 1 ELSE 0 END) AS no_provenance,
                   SUM(CASE WHEN c.morphometrics_json IS NULL AND c.is_stable = 1 THEN 1 ELSE 0 END) AS no_morphometrics,
                   SUM(CASE WHEN c.trait_labels_json IS NULL AND c.is_stable = 1 THEN 1 ELSE 0 END) AS no_traits
            FROM creatures c
            JOIN runs r ON r.run_id = c.run_id
            GROUP BY r.run_id
            ORDER BY r.run_id
        """)
        defer { sqlite3_finalize(stmt) }

        var hasGaps = false
        while sqlite3_step(stmt) == SQLITE_ROW {
            guard let runIdC = sqlite3_column_text(stmt, 0) else { continue }
            let runId = String(cString: runIdC)
            let total = Int(sqlite3_column_int64(stmt, 1))
            let stable = Int(sqlite3_column_int64(stmt, 2))
            let noTax = Int(sqlite3_column_int64(stmt, 3))
            let noProv = Int(sqlite3_column_int64(stmt, 4))
            let noMorph = Int(sqlite3_column_int64(stmt, 5))
            let noTraits = Int(sqlite3_column_int64(stmt, 6))

            if noTax > 0 || noProv > 0 || noMorph > 0 || noTraits > 0 {
                if !hasGaps {
                    print("Per-run gaps:")
                    hasGaps = true
                }
                print("  \(runId): total=\(total) stable=\(stable) no_taxonomy=\(noTax) no_provenance=\(noProv) no_morphometrics=\(noMorph) no_traits=\(noTraits)")
            }
        }
    }
}
