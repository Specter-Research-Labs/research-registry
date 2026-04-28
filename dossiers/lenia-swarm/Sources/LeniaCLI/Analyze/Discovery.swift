import ArgumentParser
import Foundation
import LeniaArchive

struct AnalyzeDiscoveryCommand: ParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "discovery",
        abstract: "Export creature-discovery candidates from the morphospace warehouse"
    )

    @Option(name: .long, help: "DuckDB warehouse path")
    var warehouse: String

    @Option(name: .long, help: "Optional warehouse study id to filter candidates")
    var studyId: String?

    @Option(name: .long, help: "Optional creature-discovery lens")
    var lens: String?

    @Option(name: .shortAndLong, help: "Optional JSON output path for the packet")
    var output: String?

    @Flag(name: .long, help: "Print compact JSON instead of pretty JSON when writing to stdout")
    var json: Bool = false

    func run() throws {
        let resolvedWarehouse = try resolveArtifactPath(warehouse, dossier: dossierName)
        let packet = try exportWarehouseCreatureDiscoveryPacket(
            warehousePath: resolvedWarehouse,
            studyId: studyId,
            lens: lens
        )
        if let output {
            let outputPath = try writeWarehousePacket(packet, output: output, dossier: dossierName)
            let summary = packetDictionaryValue(packet, key: "summary")
            let candidateCount = packetIntValue(summary, key: "candidateCount") ?? 0
            let bucketCount = packetIntValue(summary, key: "bucketCount") ?? 0
            print(
                "Discovery packet exported: candidates=\(candidateCount) buckets=\(bucketCount) output=\(outputPath)"
            )
            return
        }
        try printWarehousePacket(packet, json: json)
    }
}
