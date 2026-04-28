import ArgumentParser
import Foundation
import LeniaArchive

struct AnalyzeTopologyCommand: ParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "topology",
        abstract: "Compute topology for an existing morphospace warehouse study"
    )

    @Option(name: .long, help: "DuckDB warehouse path")
    var warehouse: String

    @Option(name: .long, help: "Warehouse study id")
    var studyId: String

    @Option(name: .long, help: "Source packet kind for topology derivation (`focal` by default; use `atlas` for replay-complete studies)")
    var sourcePacketKind: String = "focal"

    @Option(name: .long, help: "Minimum cohort size per topology slice")
    var minGroupSize: Int = 2

    @Option(name: .long, help: "Maximum homology dimension")
    var maxHomologyDim: Int = 1

    @Flag(name: .long, help: "Print the machine-readable topology summary")
    var json: Bool = false

    func run() throws {
        let resolvedWarehouse = try resolveArtifactPath(warehouse, dossier: dossierName)
        let result = try runWarehouseTopology(
            warehousePath: resolvedWarehouse,
            studyId: studyId,
            sourcePacketKind: sourcePacketKind,
            minGroupSize: minGroupSize,
            maxHomologyDim: maxHomologyDim
        )
        if json {
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.sortedKeys]
            print(String(decoding: try encoder.encode(result), as: UTF8.self))
            return
        }
        print(
            "Topology computed: study=\(result.studyId) topology_study=\(result.topologyStudyId) warehouse=\(result.warehousePath)"
        )
    }
}
