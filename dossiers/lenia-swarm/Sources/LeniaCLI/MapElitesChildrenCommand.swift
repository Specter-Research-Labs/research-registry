import ArgumentParser
import Foundation
import LeniaCore

struct MapElitesChildrenSpec: Decodable {
    enum Pairing: String, Decodable {
        case same = "self"
        case cross
    }

    enum Mutation: String, Decodable {
        case params
        case patch
        case both
    }

    struct Lineage: Decodable {
        let id: String
        let runDir: String
        let parents: [UUID]
    }

    struct Cell: Decodable {
        let id: String
        let pairing: Pairing
        let mutate: Mutation
        let sigma: Float
        let lineSigma: Float
        let children: Int
        let start: Int
        let lineages: [String]
    }

    let runId: String
    let seed: UInt64
    let lineages: [Lineage]
    let cells: [Cell]
}

struct MapElitesChildParent {
    let id: UUID
    let name: String
    let cellKey: String
    let exportDir: URL
    let candidate: [Float]
}

struct MapElitesChildLineage {
    let id: String
    let mapConfig: FlowMAPElitesConfig
    let engine: EvolutionEngine
    let replayBase: LeniaBaseConfig
    let ranges: [String: (Float, Float)]
    let parents: [MapElitesChildParent]

    var dimensions: Int { engine.thetaParamsDim + engine.initPatchDim }

    func mutated(_ mutation: MapElitesChildrenSpec.Mutation) -> Range<Int> {
        switch mutation {
        case .params: return 0..<engine.thetaParamsDim
        case .patch: return engine.thetaParamsDim..<dimensions
        case .both: return 0..<dimensions
        }
    }

    func searchConfig(for initConfig: InitConfig) -> ParsedSearchConfig {
        buildStrictReplaySearchConfig(steps: mapConfig.steps, initSeedOffset: initConfig.seed)
    }
}

private struct MapElitesChildParentRecord: Encodable {
    let lineage: String
    let creatureId: UUID
    let name: String
    let cellKey: String
    let exportDir: String
    let dimensions: Int

    enum CodingKeys: String, CodingKey {
        case lineage
        case creatureId = "creature_id"
        case name
        case cellKey = "cell_key"
        case exportDir = "export_dir"
        case dimensions
    }
}

private struct MapElitesChildRecord: Encodable {
    let cell: String
    let index: Int
    let seed: UInt64
    let mutate: String
    let sigma: Float
    let lineSigma: Float
    let lineage: String
    let firstParent: UUID
    let secondLineage: String
    let secondParent: UUID
    let creatureId: UUID
    let exportDir: String

    enum CodingKeys: String, CodingKey {
        case cell
        case index
        case seed
        case mutate
        case sigma
        case lineSigma = "line_sigma"
        case lineage
        case firstParent = "first_parent"
        case secondLineage = "second_lineage"
        case secondParent = "second_parent"
        case creatureId = "creature_id"
        case exportDir = "export_dir"
    }
}

private struct LibraryCandidateRow: Decodable {
    struct Creature: Decodable {
        let id: UUID
    }

    struct Metadata: Decodable {
        let candidateVector: [Float]
        let cellKey: String

        enum CodingKeys: String, CodingKey {
            case candidateVector = "candidate_vector"
            case cellKey = "cell_key"
        }
    }

    let creature: Creature
    let researchMetadata: Metadata

    enum CodingKeys: String, CodingKey {
        case creature
        case researchMetadata = "research_metadata"
    }
}

private struct ArchiveCandidateRow: Decodable {
    let key: String
    let candidate: [Float]
}

struct MapElitesChildrenCommand: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "map-elites-children",
        abstract: "Emit seeded MAP-Elites children of archived Flow MAP-Elites elites as replay bundles",
        discussion: """
            Each lineage is a Flow MAP-Elites run directory; its parents are export creature IDs. Every parent \
            is rebuilt from its archived candidate and must reproduce its exported genotype, initial condition \
            and base.json before any child is written. Child k of a cell draws from its own generator, seeded \
            from the spec seed, the cell's position and k, so a cell can be emitted in chunks with `start`.
            """
    )

    @Option(name: .long, help: "Children spec JSON; run_dir paths resolve against its directory")
    var spec: String

    @Option(name: .shortAndLong, help: "New output directory")
    var output: String

    @Flag(name: .long, help: "Verify the parents and write parents.jsonl without emitting children")
    var verifyOnly: Bool = false

    func run() async throws {
        let specURL = URL(fileURLWithPath: spec)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let childrenSpec = try decoder.decode(MapElitesChildrenSpec.self, from: Data(contentsOf: specURL))
        let outputURL = URL(fileURLWithPath: output, isDirectory: true)
        guard !FileManager.default.fileExists(atPath: outputURL.path) else {
            throw ValidationError("Output directory already exists: \(outputURL.path)")
        }

        let specRoot = specURL.deletingLastPathComponent()
        var lineages: [String: MapElitesChildLineage] = [:]
        for lineage in childrenSpec.lineages {
            guard lineages[lineage.id] == nil else {
                throw ValidationError("Duplicate lineage id \(lineage.id).")
            }
            let runDir = URL(fileURLWithPath: lineage.runDir, relativeTo: specRoot).standardizedFileURL
            lineages[lineage.id] = try loadMapElitesChildLineage(id: lineage.id, runDir: runDir, parentIDs: lineage.parents)
        }

        try FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)
        let parentRecords = childrenSpec.lineages.flatMap { spec in
            lineages[spec.id]!.parents.map { parent in
                MapElitesChildParentRecord(
                    lineage: spec.id,
                    creatureId: parent.id,
                    name: parent.name,
                    cellKey: parent.cellKey,
                    exportDir: parent.exportDir.path,
                    dimensions: parent.candidate.count
                )
            }
        }
        try writeResearchJSONLines(parentRecords, to: outputURL.appendingPathComponent("parents.jsonl"))
        print("Verified \(parentRecords.count) parent(s) in \(lineages.count) lineage(s).")
        if verifyOnly {
            return
        }

        guard Set(childrenSpec.cells.map(\.id)).count == childrenSpec.cells.count else {
            throw ValidationError("Cell ids must be unique.")
        }
        var childRecords: [MapElitesChildRecord] = []
        for cell in childrenSpec.cells {
            let cellLineages = try cell.lineages.map { id in
                guard let lineage = lineages[id] else {
                    throw ValidationError("Cell \(cell.id) names unknown lineage \(id).")
                }
                return lineage
            }
            guard !cellLineages.isEmpty, cell.children > 0, cell.start >= 0 else {
                throw ValidationError("Cell \(cell.id) needs lineages, a positive child count and a non-negative start.")
            }
            if cell.pairing == .cross {
                guard cellLineages.count > 1 else {
                    throw ValidationError("Cross cell \(cell.id) needs at least two lineages.")
                }
                try requireSharedGenomeSpace(cellLineages, cell: cell.id)
            }
            let exportRoot = outputURL
                .appendingPathComponent(cell.id, isDirectory: true)
                .appendingPathComponent("exports", isDirectory: true)
            var exportRecords: [CreatureExportRecord] = []
            for index in cell.start..<(cell.start + cell.children) {
                let seed = mapElitesChildSeed(specSeed: childrenSpec.seed, cell: cell.id, index: index)
                var rng = SeededRandomNumberGenerator(seed: seed)
                let lineage = cellLineages[index % cellLineages.count]
                let first = lineage.parents[Int.random(in: 0..<lineage.parents.count, using: &rng)]
                let secondLineage: MapElitesChildLineage
                switch cell.pairing {
                case .same:
                    secondLineage = lineage
                case .cross:
                    let others = cellLineages.filter { $0.id != lineage.id }
                    secondLineage = others[Int.random(in: 0..<others.count, using: &rng)]
                }
                let second = cell.pairing == .same
                    ? first
                    : secondLineage.parents[Int.random(in: 0..<secondLineage.parents.count, using: &rng)]
                let candidate = EvolutionEngine.mapElitesChild(
                    first: first.candidate,
                    second: second.candidate,
                    sigma: cell.sigma,
                    lineSigma: cell.lineSigma,
                    mutated: lineage.mutated(cell.mutate),
                    rng: &rng
                )
                let genome = lineage.engine.researchExportGenome(candidate)
                let creature = archivedCreature(
                    stableKey: "\(childrenSpec.seed)|\(cell.id)|\(index)|\(first.id.uuidString)|\(second.id.uuidString)",
                    name: "\(cell.id)-\(index)",
                    ownerId: "map-elites-children",
                    genotype: genome.params,
                    initialCondition: genome.initConfig,
                    initialConditionFamily: morphospaceInitialConditionFamily(genome.initConfig),
                    metrics: unmeasuredChildMetrics
                )
                guard let artifacts = try writeReplayExportArtifacts(
                    exportRoot: exportRoot,
                    baseConfig: lineage.replayBase,
                    searchConfig: lineage.searchConfig(for: genome.initConfig),
                    creature: creature,
                    runId: childrenSpec.runId,
                    campaignId: nil,
                    score: nil,
                    filtersPassed: nil,
                    reason: "map-elites-child"
                ) else {
                    throw ValidationError("Child export already exists for \(creature.name) in \(exportRoot.path).")
                }
                exportRecords.append(artifacts.record)
                childRecords.append(MapElitesChildRecord(
                    cell: cell.id,
                    index: index,
                    seed: seed,
                    mutate: cell.mutate.rawValue,
                    sigma: cell.sigma,
                    lineSigma: cell.lineSigma,
                    lineage: lineage.id,
                    firstParent: first.id,
                    secondLineage: secondLineage.id,
                    secondParent: second.id,
                    creatureId: creature.id,
                    exportDir: artifacts.exportDir.path
                ))
            }
            _ = try writeCreatureExportIndex(exportRecords, to: exportRoot)
            print("Cell \(cell.id): \(exportRecords.count) child bundle(s) in \(exportRoot.path)")
        }
        try writeResearchJSONLines(childRecords, to: outputURL.appendingPathComponent("children.jsonl"))
    }
}

/// Children are never simulated by the emitter; zero samples mark the metrics as unmeasured.
let unmeasuredChildMetrics = SimulationMetrics(
    massMean: 0,
    massStd: 0,
    massMin: 0,
    massMax: 0,
    occupancyMean: 0,
    varianceMean: 0,
    energyMean: 0,
    speedMean: 0,
    pathLength: 0,
    displacement: 0,
    sampleCount: 0,
    speedCount: 0,
    gyration: 0
)

/// Seeds from the cell id rather than its position, so a cell emitted alone or in chunks draws the
/// same children as in the full spec.
func mapElitesChildSeed(specSeed: UInt64, cell: String, index: Int) -> UInt64 {
    let cellHash = cell.utf8.reduce(UInt64(0xcbf2_9ce4_8422_2325)) { ($0 ^ UInt64($1)) &* 0x100_0000_01b3 }
    var cellMixer = SeededRandomNumberGenerator(seed: specSeed ^ cellHash)
    var childMixer = SeededRandomNumberGenerator(seed: cellMixer.next() &+ UInt64(index))
    return childMixer.next()
}

func loadMapElitesChildLineage(id: String, runDir: URL, parentIDs: [UUID]) throws -> MapElitesChildLineage {
    guard !parentIDs.isEmpty else {
        throw ValidationError("Lineage \(id) has no parents.")
    }
    let configData = try Data(contentsOf: runDir.appendingPathComponent("config.json"))
    let baseConfig = try JSONDecoder().decode(LeniaBaseConfig.self, from: configData)
    let runtimeConfig = try loadRuntimeConfig(from: configData)
    let mapConfig = try loadFlowMAPElitesConfig(path: runDir.appendingPathComponent("map_elites_config.json").path)
    let ranges: [String: (Float, Float)]
    if let mapRanges = mapConfig.paramRanges {
        ranges = try mapRanges.mapValues { values in
            guard values.count == 2 else {
                throw ValidationError("Lineage \(id): param_ranges entries must have exactly two values.")
            }
            return (values[0], values[1])
        }
    } else {
        ranges = try extractRangesFromConfig(baseConfig)
    }
    let engine = EvolutionEngine(runtimeConfig: runtimeConfig, esConfig: genomeDecodingESConfig(mapConfig), ranges: ranges)
    let replayBase = buildEvolveReplayBaseConfig(baseConfig: baseConfig, esConfig: mapConfig.asESConfig())

    let rowDecoder = JSONDecoder()
    var library: [UUID: LibraryCandidateRow] = [:]
    for line in try replayReadJSONLines(runDir.appendingPathComponent("library/index.jsonl")) {
        let row = try rowDecoder.decode(LibraryCandidateRow.self, from: Data(line.utf8))
        library[row.creature.id] = row
    }
    var archive: [String: [Float]] = [:]
    for line in try replayReadJSONLines(runDir.appendingPathComponent("archive/occupied.jsonl")) {
        let row = try rowDecoder.decode(ArchiveCandidateRow.self, from: Data(line.utf8))
        archive[row.key] = row.candidate
    }
    let exportsRoot = runDir.appendingPathComponent("exports", isDirectory: true)
    let exportDirs = try FileManager.default.contentsOfDirectory(atPath: exportsRoot.path)

    let parents = try parentIDs.map { parentID in
        guard let row = library[parentID] else {
            throw ValidationError("Lineage \(id): parent \(parentID) is not in library/index.jsonl.")
        }
        let candidate = row.researchMetadata.candidateVector
        guard archive[row.researchMetadata.cellKey] == candidate else {
            throw ValidationError("Lineage \(id): parent \(parentID) does not match archive cell \(row.researchMetadata.cellKey).")
        }
        guard candidate.count == engine.thetaParamsDim + engine.initPatchDim else {
            throw ValidationError("Lineage \(id): parent \(parentID) has \(candidate.count) dimensions, the run's genome has \(engine.thetaParamsDim + engine.initPatchDim).")
        }
        let suffix = "-" + parentID.uuidString.prefix(8)
        let matches = exportDirs.filter { $0.hasSuffix(suffix) }
        guard matches.count == 1 else {
            throw ValidationError("Lineage \(id): expected one export ending in \(suffix), found \(matches.count).")
        }
        let exportDir = exportsRoot.appendingPathComponent(matches[0], isDirectory: true)
        let name = try verifyMapElitesChildParent(
            candidate: candidate,
            parentID: parentID,
            exportDir: exportDir,
            engine: engine,
            replayBase: replayBase,
            steps: mapConfig.steps
        )
        return MapElitesChildParent(
            id: parentID,
            name: name,
            cellKey: row.researchMetadata.cellKey,
            exportDir: exportDir,
            candidate: candidate
        )
    }
    return MapElitesChildLineage(
        id: id,
        mapConfig: mapConfig,
        engine: engine,
        replayBase: replayBase,
        ranges: ranges,
        parents: parents
    )
}

/// Rebuilds the parent's export from its archived candidate and requires it to match the bundle
/// on disk, so children vary exactly the genome that produced the exported body.
func verifyMapElitesChildParent(
    candidate: [Float],
    parentID: UUID,
    exportDir: URL,
    engine: EvolutionEngine,
    replayBase: LeniaBaseConfig,
    steps: Int
) throws -> String {
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .deferredToDate
    let meta = try decodeCreatureExportMetadata(
        Data(contentsOf: exportDir.appendingPathComponent("meta.json")),
        decoder: decoder,
        indexBundleKind: .strictReplayBundleV1
    )
    guard meta.creature.id == parentID else {
        throw ValidationError("Export \(exportDir.path) holds creature \(meta.creature.id), not \(parentID).")
    }
    let genome = engine.researchExportGenome(candidate)
    let encoder = mapElitesChildCanonicalEncoder()
    guard try encoder.encode(genome.params) == encoder.encode(meta.creature.genotype) else {
        throw ValidationError("Parent \(parentID): rebuilt genotype differs from \(exportDir.path).")
    }
    guard try encoder.encode(genome.initConfig) == encoder.encode(meta.creature.initialCondition) else {
        throw ValidationError("Parent \(parentID): rebuilt initial condition differs from \(exportDir.path).")
    }
    let rebuiltBase = try buildReplayBaseConfig(
        baseConfig: replayBase,
        searchConfig: buildStrictReplaySearchConfig(steps: steps, initSeedOffset: genome.initConfig.seed),
        creature: meta.creature
    )
    let exportedBase = try decoder.decode(
        LeniaBaseConfig.self,
        from: Data(contentsOf: exportDir.appendingPathComponent("base.json"))
    )
    guard try encoder.encode(rebuiltBase) == encoder.encode(exportedBase) else {
        throw ValidationError("Parent \(parentID): rebuilt base.json differs from \(exportDir.path).")
    }
    let exportedSearch = try decoder.decode(
        ParsedSearchConfig.self,
        from: Data(contentsOf: exportDir.appendingPathComponent("search.json"))
    )
    guard exportedSearch.count == 1,
          exportedSearch.seedStart == 0,
          exportedSearch.initSeedOffset == genome.initConfig.seed,
          exportedSearch.steps == steps else {
        throw ValidationError("Parent \(parentID): search.json is not the strict replay of \(steps) steps from seed \(genome.initConfig.seed).")
    }
    return meta.creature.name
}

/// The emitter never evaluates a candidate, and archived runs used objectives the engine no longer
/// accepts, so the engine is built with a fixed objective. Parent verification proves the decoded
/// genome is unchanged.
private func genomeDecodingESConfig(_ mapConfig: FlowMAPElitesConfig) -> ESConfig {
    let source = mapConfig.asESConfig()
    return ESConfig(
        outputDir: source.outputDir,
        generations: source.generations,
        population: source.population,
        sigma: source.sigma,
        learningRate: source.learningRate,
        seed: source.seed,
        steps: source.steps,
        fitness: FitnessConfig(objective: "body_locomotion", targetStep: source.steps, angleThreshold: 0),
        fitnessShaping: source.fitnessShaping,
        includeParent: source.includeParent,
        initPatch: source.initPatch,
        initialInitPatchValues: source.initialInitPatchValues,
        initialKernelParams: source.initialKernelParams,
        paramRanges: source.paramRanges,
        obstacleField: source.obstacleField
    )
}

private func requireSharedGenomeSpace(_ lineages: [MapElitesChildLineage], cell: String) throws {
    let encoder = mapElitesChildCanonicalEncoder()
    func signature(_ lineage: MapElitesChildLineage) throws -> [Data] {
        let ranges = lineage.ranges.mapValues { [$0.0, $0.1] }
        return [
            try encoder.encode(ranges),
            try encoder.encode(lineage.mapConfig.initPatch),
            try encoder.encode([lineage.engine.thetaParamsDim, lineage.engine.initPatchDim]),
            try encoder.encode(lineage.replayBase),
        ]
    }
    let reference = try signature(lineages[0])
    for lineage in lineages.dropFirst() where try signature(lineage) != reference {
        throw ValidationError("Cross cell \(cell): lineage \(lineage.id) does not share the genome space of \(lineages[0].id).")
    }
}

func mapElitesChildCanonicalEncoder() -> JSONEncoder {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    return encoder
}
