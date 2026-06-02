import ArgumentParser
import Foundation
import LeniaCore
import Logging
import SQLite3

let interventionTrialRecoveryThreshold: Double = 1.0

func writeInterventionTrialRows(
    metrics: [LeniaCampaignMetricRecord],
    perturbationFamilies: [String: String],
    compendiumPath: String,
    logger: Logger
) throws -> Int {
    let baselines = Dictionary(
        uniqueKeysWithValues: metrics.compactMap { metric -> (String, LeniaCampaignMetricRecord)? in
            guard metric.perturbationLabel == "baseline",
                  let group = metric.comparisonGroup else { return nil }
            return (group, metric)
        }
    )

    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let recordedAt = formatter.string(from: Date())

    struct Row {
        let id: String
        let sourceSpecimenID: String
        let targetSpecimenID: String
        let runID: String
        let campaignID: String?
        let recordedAt: String
        let trialKind: String
        let interventionFamily: String
        let protocolJson: String
        let normFamily: String
        let normValue: Double
        let normJson: String
        let success: Int
        let recovered: Int?
        let recoverySteps: Int?
        let lateDistance: Double
        let outcomeJson: String
    }

    let db = try SQLiteDB(path: compendiumPath)
    let resolver = try SpecimenIDResolver(db: db, compendiumPath: compendiumPath)

    var rows: [Row] = []
    var skipped: Int = 0
    for metric in metrics where metric.perturbationLabel != "baseline" {
        guard let pertLabel = metric.perturbationLabel else {
            logger.warning("Intervention trial promotion: skipping run \(metric.runID) - missing perturbation_label")
            skipped += 1
            continue
        }
        guard let group = metric.comparisonGroup else {
            logger.warning("Intervention trial promotion: skipping run \(metric.runID) (perturbation '\(pertLabel)') - missing comparison_group")
            skipped += 1
            continue
        }
        guard let baseline = baselines[group] else {
            logger.warning("Intervention trial promotion: skipping run \(metric.runID) (perturbation '\(pertLabel)', group '\(group)') - no baseline metric for group")
            skipped += 1
            continue
        }
        guard let family = perturbationFamilies[pertLabel] else {
            throw ValidationError(
                "intervention trial promotion: missing family for perturbation '\(pertLabel)'."
            )
        }
        let sourceSpecimenID = try resolver.specimenID(for: baseline, role: "baseline")
        let targetSpecimenID = try resolver.specimenID(for: metric, role: "intervention")
        let (norm, axes) = kinematicNorm(intervention: metric, baseline: baseline)
        let protocolObject: [String: Any] = [
            "perturbation_label": pertLabel,
            "family": family,
            "comparison_group": group,
            "environment_label": metric.environmentLabel ?? NSNull(),
            "baseline_run_id": baseline.runID,
            "baseline_specimen_id": sourceSpecimenID,
            "intervention_specimen_id": targetSpecimenID,
        ]
        let outcomeObject: [String: Any] = [
            "final_mass": jsonNumber(metric.finalMass),
            "displacement": jsonNumber(metric.displacement),
            "energy_mean": jsonNumber(metric.energyMean),
            "gyration": jsonNumber(metric.gyration),
            "speed_mean": jsonNumber(metric.speedMean),
            "post_perturbation_divergence": jsonNumber(metric.postPerturbationDivergence),
            "return_to_baseline_score": jsonNumber(metric.returnToBaselineScore),
        ]
        let normObject: [String: Any] = [
            "axes": axes.mapValues { jsonNumber(Double($0)) },
            "threshold": interventionTrialRecoveryThreshold,
        ]
        rows.append(Row(
            id: "trial:\(metric.runID)",
            sourceSpecimenID: sourceSpecimenID,
            targetSpecimenID: targetSpecimenID,
            runID: metric.runID,
            campaignID: metric.campaignID,
            recordedAt: recordedAt,
            trialKind: "campaign-intervention",
            interventionFamily: family,
            protocolJson: jsonEncode(protocolObject),
            normFamily: "kinematic-l2-relative",
            normValue: norm,
            normJson: jsonEncode(normObject),
            success: 1,
            recovered: norm < interventionTrialRecoveryThreshold ? 1 : 0,
            recoverySteps: nil,
            lateDistance: norm,
            outcomeJson: jsonEncode(outcomeObject)
        ))
    }

    guard !rows.isEmpty else {
        logger.info("Intervention trial promotion: no baseline/intervention pairs to record (skipped=\(skipped)).")
        return 0
    }

    try db.withImmediateTransaction {
        let stmt = try db.prepare("""
            INSERT OR REPLACE INTO perturbation_trials (
                id, source_specimen_id, source_attractor_id,
                target_specimen_id, target_attractor_id,
                run_id, campaign_id, recorded_at, trial_kind,
                intervention_family, protocol_json, norm_family,
                norm_value, norm_json, success, recovered,
                recovery_steps, late_distance, outcome_json
            ) VALUES (?, ?, NULL, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """)
        defer { sqlite3_finalize(stmt) }
        for row in rows {
            sqlite3_reset(stmt)
            db.bindText(stmt, index: 1, value: row.id)
            db.bindText(stmt, index: 2, value: row.sourceSpecimenID)
            db.bindText(stmt, index: 3, value: row.targetSpecimenID)
            db.bindText(stmt, index: 4, value: row.runID)
            db.bindText(stmt, index: 5, value: row.campaignID)
            db.bindText(stmt, index: 6, value: row.recordedAt)
            db.bindText(stmt, index: 7, value: row.trialKind)
            db.bindText(stmt, index: 8, value: row.interventionFamily)
            db.bindText(stmt, index: 9, value: row.protocolJson)
            db.bindText(stmt, index: 10, value: row.normFamily)
            db.bindDouble(stmt, index: 11, value: row.normValue)
            db.bindText(stmt, index: 12, value: row.normJson)
            db.bindInt(stmt, index: 13, value: row.success)
            db.bindInt(stmt, index: 14, value: row.recovered)
            db.bindInt(stmt, index: 15, value: row.recoverySteps)
            db.bindDouble(stmt, index: 16, value: row.lateDistance)
            db.bindText(stmt, index: 17, value: row.outcomeJson)
            try db.step(stmt)
        }
    }
    logger.info("Intervention trial promotion: wrote \(rows.count) rows to perturbation_trials (skipped=\(skipped))")
    return rows.count
}

private func kinematicNorm(
    intervention: LeniaCampaignMetricRecord,
    baseline: LeniaCampaignMetricRecord
) -> (Double, [String: Double]) {
    var axes: [String: Double] = [:]
    var sumSquares: Double = 0
    func add(_ key: String, _ a: Float?, _ b: Float?) {
        guard let a, let b else { return }
        let denom = max(abs(Double(b)), 1e-6)
        let delta = (Double(a) - Double(b)) / denom
        axes[key] = delta
        sumSquares += delta * delta
    }
    add("final_mass", intervention.finalMass, baseline.finalMass)
    add("displacement", intervention.displacement, baseline.displacement)
    add("energy_mean", intervention.energyMean, baseline.energyMean)
    add("gyration", intervention.gyration, baseline.gyration)
    return (sqrt(sumSquares), axes)
}

private func jsonNumber(_ value: Float?) -> Any {
    if let value, value.isFinite { return Double(value) }
    return NSNull()
}

private func jsonNumber(_ value: Double?) -> Any {
    if let value, value.isFinite { return value }
    return NSNull()
}

private func jsonEncode(_ object: Any) -> String {
    guard let data = try? JSONSerialization.data(
        withJSONObject: object,
        options: [.sortedKeys]
    ) else {
        return "{}"
    }
    return String(data: data, encoding: .utf8) ?? "{}"
}

private final class SpecimenIDResolver {
    private let db: SQLiteDB
    private let stmt: OpaquePointer
    private let runKey: String

    init(db: SQLiteDB, compendiumPath: String) throws {
        self.db = db
        self.runKey = URL(fileURLWithPath: compendiumPath)
            .deletingLastPathComponent()
            .lastPathComponent
        self.stmt = try db.prepare("""
            SELECT id FROM specimens
            WHERE run_id = ? AND seed = ? AND source_kind = 'result'
            LIMIT 1
        """)
    }

    deinit {
        sqlite3_finalize(stmt)
    }

    func specimenID(for metric: LeniaCampaignMetricRecord, role: String) throws -> String {
        guard let seed = metric.seed else {
            throw ValidationError(
                "intervention trial promotion: \(role) metric for run '\(metric.runID)' is missing seed; only search-mode campaigns expose seed metadata."
            )
        }
        sqlite3_reset(stmt)
        sqlite3_clear_bindings(stmt)
        db.bindText(stmt, index: 1, value: runKey)
        db.bindInt(stmt, index: 2, value: seed)
        guard sqlite3_step(stmt) == SQLITE_ROW else {
            throw ValidationError(
                "intervention trial promotion: no result specimen found for \(role) run '\(metric.runID)' (run_id='\(runKey)', seed=\(seed)). Ensure compendium ingest ran before trial promotion."
            )
        }
        guard let idC = sqlite3_column_text(stmt, 0) else {
            throw ValidationError(
                "intervention trial promotion: specimen lookup returned non-text id for \(role) run '\(metric.runID)' (run_id='\(runKey)', seed=\(seed))."
            )
        }
        return String(cString: idC)
    }
}
