import ArgumentParser
import Foundation
import LeniaArchive

struct AnalyzeWarehouseCommand: ParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "warehouse",
        abstract: "Refresh the morphospace DuckDB warehouse from a canonical compendium SQLite database"
    )

    @Option(name: [.customLong("db"), .customLong("compendium")], help: "SQLite compendium DB path")
    var dbPath: String

    @Option(name: .long, help: "DuckDB warehouse path (default: sibling morphospace.duckdb next to the compendium DB)")
    var warehouse: String?

    @Option(name: .long, help: "Warehouse study label override")
    var label: String?

    @Flag(name: .long, help: "Also compute topology for the refreshed study")
    var topology: Bool = false

    @Flag(name: .long, help: "Print the machine-readable warehouse refresh summary")
    var json: Bool = false

    func run() throws {
        let result = try refreshWarehouseProjection(
            compendiumPath: resolveArtifactPath(dbPath, dossier: dossierName),
            warehousePath: try warehouse.map { try resolveArtifactPath($0, dossier: dossierName) },
            warehouseTopology: topology,
            label: label,
            defaultEnabled: true
        )!

        if json {
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.sortedKeys]
            print(String(decoding: try encoder.encode(result), as: UTF8.self))
            return
        }
        print(
            "Warehouse refreshed: study=\(result.studyId) axes=\(result.axesUpdated) status=\(result.statusUpdated) anatomy=\(result.anatomyUpdated) warehouse=\(result.warehousePath)"
        )
        if let topologyStudyId = result.topologyStudyId {
            print("Topology study: \(topologyStudyId)")
        }
    }
}
