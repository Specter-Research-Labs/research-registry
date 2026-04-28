import ArgumentParser
import Foundation
import LeniaArchive

struct AnalyzeBiologicalCommand: ParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "biological",
        abstract: "Export a biological packet from the morphospace warehouse"
    )

    @Option(name: .long, help: "DuckDB warehouse path")
    var warehouse: String

    @Option(name: .long, help: "Baseline study id")
    var studyId: String

    @Option(name: .long, help: "Optional context/intervention study id")
    var contextStudyId: String?

    @Option(name: .shortAndLong, help: "Optional JSON output path for the packet")
    var output: String?

    @Flag(name: .long, help: "Print compact JSON instead of pretty JSON when writing to stdout")
    var json: Bool = false

    func run() throws {
        let resolvedWarehouse = try resolveArtifactPath(warehouse, dossier: dossierName)
        let packet = try exportWarehouseBiologicalPacket(
            warehousePath: resolvedWarehouse,
            studyId: studyId,
            contextStudyId: contextStudyId
        )
        if let output {
            let outputPath = try writeWarehousePacket(packet, output: output, dossier: dossierName)
            let summary = packetDictionaryValue(packet, key: "summary")
            let baselineStateCount = packetIntValue(summary, key: "baselineStateCount") ?? 0
            let contextStateCount = packetIntValue(summary, key: "contextStateCount") ?? 0
            print(
                "Biological packet exported: baseline_states=\(baselineStateCount) context_states=\(contextStateCount) output=\(outputPath)"
            )
            return
        }
        try printWarehousePacket(packet, json: json)
    }
}
