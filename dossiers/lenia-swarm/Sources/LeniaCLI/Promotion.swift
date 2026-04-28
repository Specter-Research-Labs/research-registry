import ArgumentParser
import Foundation
import LeniaArchive

struct WarehouseRefreshOptions: ParsableArguments {
    @Option(name: .long, help: "DuckDB warehouse path override (default: sibling morphospace.duckdb next to the compendium DB)")
    var warehouse: String?

    @Flag(name: .long, help: "Also compute topology for the refreshed warehouse study")
    var warehouseTopology: Bool = false
}

struct ArchivePromotionOptions: ParsableArguments {
    @Flag(name: .customLong("no-promotion"), help: "Disable automatic promotion into compendium.sqlite and morphospace.duckdb")
    var noPromotion: Bool = false

    @Option(name: [.customLong("db"), .customLong("compendium")], help: "Compendium SQLite path for promotion outputs")
    var compendium: String?

    @OptionGroup
    var warehouseRefresh: WarehouseRefreshOptions

    var warehouse: String? { warehouseRefresh.warehouse }
    var warehouseTopology: Bool { warehouseRefresh.warehouseTopology }

    func resolvedConfig(
        defaultCompendiumPath: String?,
        dossier: String,
        defaultEnabled: Bool = false
    ) throws -> ArchivePromotionConfig {
        if noPromotion, compendium != nil || warehouseRefresh.warehouse != nil || warehouseRefresh.warehouseTopology {
            throw ValidationError("--no-promotion cannot be combined with promotion path or topology overrides.")
        }
        if noPromotion {
            return ArchivePromotionConfig(compendiumPath: nil, warehousePath: nil, warehouseTopology: false)
        }

        let shouldPromote = defaultEnabled || compendium != nil || warehouseRefresh.warehouse != nil || warehouseRefresh.warehouseTopology
        let resolvedCompendium = try compendium.map { try resolveArtifactPath($0, dossier: dossier) } ?? (shouldPromote ? defaultCompendiumPath : nil)
        let hasWarehouseOptions = warehouseRefresh.warehouse != nil || warehouseRefresh.warehouseTopology
        if hasWarehouseOptions && resolvedCompendium == nil {
            throw ValidationError("--warehouse and --warehouse-topology require a compendium path (--db or a default).")
        }
        let resolvedWarehouse = try warehouseRefresh.warehouse.map { try resolveArtifactPath($0, dossier: dossier) }
            ?? resolvedCompendium.map(defaultWarehousePath)

        return ArchivePromotionConfig(
            compendiumPath: resolvedCompendium,
            warehousePath: resolvedWarehouse,
            warehouseTopology: warehouseRefresh.warehouseTopology
        )
    }
}

struct ArchivePromotionConfig {
    let compendiumPath: String?
    let warehousePath: String?
    let warehouseTopology: Bool

    var isEnabled: Bool { compendiumPath != nil || warehousePath != nil || warehouseTopology }
}

@discardableResult
func promoteRunArtifacts(
    runDir: String,
    compendiumPath: String,
    includeResults: Bool = true,
    stats: Bool = false,
    warehousePath: String? = nil,
    warehouseTopology: Bool = false
) throws -> String {
    let indexer = try executeCompendiumIngest(
        plan: CompendiumIngestPlan(
            runInputs: [try makeRunInput(runDir: runDir)],
            resolvedDBPath: compendiumPath
        ),
        rebuild: false,
        includeResults: includeResults,
        repairOnly: false
    )

    if stats {
        print("Compendium: \(try indexer.stats())")
    }
    if let warehouseResult = try refreshWarehouseProjection(
        compendiumPath: compendiumPath,
        warehousePath: warehousePath,
        warehouseTopology: warehouseTopology,
        defaultEnabled: true
    ), stats {
        print(
            "Warehouse: study=\(warehouseResult.studyId) axes=\(warehouseResult.axesUpdated) status=\(warehouseResult.statusUpdated) anatomy=\(warehouseResult.anatomyUpdated)"
        )
    }
    return compendiumPath
}

@discardableResult
func applyPromotionIfEnabled(
    config: ArchivePromotionConfig,
    runDir: String,
    includeResults: Bool = true,
    stats: Bool = false
) throws -> ArchivePromotionConfig {
    if let compendiumPath = config.compendiumPath {
        try promoteRunArtifacts(
            runDir: runDir,
            compendiumPath: compendiumPath,
            includeResults: includeResults,
            stats: stats,
            warehousePath: config.warehousePath,
            warehouseTopology: config.warehouseTopology
        )
    }
    return config
}

@discardableResult
func refreshWarehouseProjection(
    compendiumPath: String,
    warehousePath: String? = nil,
    warehouseTopology: Bool = false,
    label: String? = nil,
    defaultEnabled: Bool = false
) throws -> WarehouseRefreshResult? {
    guard defaultEnabled || warehousePath != nil || warehouseTopology else {
        return nil
    }
    return try refreshWarehouseFromCompendium(
        compendiumPath: compendiumPath,
        warehousePath: resolvedWarehousePath(explicitPath: warehousePath, compendiumPath: compendiumPath),
        label: label,
        topology: warehouseTopology
    )
}
