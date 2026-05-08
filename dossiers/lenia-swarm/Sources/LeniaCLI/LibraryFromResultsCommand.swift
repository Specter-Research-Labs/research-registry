import ArgumentParser
import Foundation
import LeniaCore

struct LibraryFromResultsCommand: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "library-from-results",
        abstract: "Synthesize library/index.jsonl from a scout run's results.jsonl + config.json + search.json"
    )

    @Option(name: .long, help: "Scout run directory containing config.json, search.json, results.jsonl")
    var scoutDir: String

    @Option(name: .long, help: "Owner id stamped onto every synthesized creature")
    var ownerId: String = "lenia-tribe-overlay"

    @Option(name: .long, help: "Take only the top-N results by score (descending). 0 = all.")
    var top: Int = 0

    @Option(name: .long, help: "Cap on number of entries written. 0 = no cap.")
    var limit: Int = 0

    @Flag(name: .long, help: "Skip rows with filters_passed=false.")
    var requireFiltersPassed: Bool = false

    @Flag(name: .long, help: "Validate inputs and report counts without writing library/index.jsonl.")
    var validateOnly: Bool = false

    func run() async throws {
        let scoutURL = URL(
            fileURLWithPath: try resolveArtifactPath(scoutDir, dossier: dossierName),
            isDirectory: true
        )
        let configURL = scoutURL.appendingPathComponent("config.json")
        let searchURL = scoutURL.appendingPathComponent("search.json")
        let resultsURL = scoutURL.appendingPathComponent("results.jsonl")
        for url in [configURL, searchURL, resultsURL] {
            guard FileManager.default.fileExists(atPath: url.path) else {
                throw ValidationError("Missing required file: \(url.path)")
            }
        }

        let baseConfigData = try Data(contentsOf: configURL)
        let baseConfig = try JSONDecoder().decode(LeniaBaseConfig.self, from: baseConfigData)
        let topologyHash = configTopologyHash(baseConfig)

        let searchData = try Data(contentsOf: searchURL)
        let parsedSearchConfig = try JSONDecoder().decode(ParsedSearchConfig.self, from: searchData)

        var refOverrides = parsedSearchConfig.overridesAsDict()
        refOverrides["run.steps"] = parsedSearchConfig.steps
        let refConfig = try loadRuntimeConfig(from: baseConfigData, overrides: refOverrides)

        let resultsRaw = try String(contentsOf: resultsURL, encoding: .utf8)
        let decoder = JSONDecoder()
        var results: [SimulationResultData] = []
        for (idx, line) in resultsRaw.split(separator: "\n", omittingEmptySubsequences: true).enumerated() {
            guard let data = line.data(using: .utf8) else {
                throw ValidationError("results.jsonl line \(idx + 1) is not valid UTF-8")
            }
            do {
                results.append(try decoder.decode(SimulationResultData.self, from: data))
            } catch {
                throw ValidationError("results.jsonl line \(idx + 1) failed to decode: \(error)")
            }
        }

        var selected = results
        if requireFiltersPassed {
            selected = selected.filter { $0.filtersPassed }
        }
        if top > 0 {
            selected.sort { (lhs, rhs) in
                let l = lhs.score ?? -.greatestFiniteMagnitude
                let r = rhs.score ?? -.greatestFiniteMagnitude
                return l > r
            }
            if selected.count > top {
                selected = Array(selected.prefix(top))
            }
        }
        if limit > 0 && selected.count > limit {
            selected = Array(selected.prefix(limit))
        }

        guard !selected.isEmpty else {
            throw ValidationError("No results selected; nothing to write.")
        }

        let runId = scoutURL.lastPathComponent
        var entries: [ResearchLibraryEntry] = []
        entries.reserveCapacity(selected.count)
        for result in selected {
            let initialCondition = InitConfig(
                seed: result.initSeed,
                patches: refConfig.patches,
                a_uniform: refConfig.aUniform,
                p_uniform: refConfig.pUniform,
                state_patch: refConfig.statePatch,
                p_state_patch: refConfig.paramPatch
            )
            let creature = archivedCreatureFromResult(
                stableKey: libraryResultStableKey(runId: runId, result: result),
                name: synthesizedCreatureName(runId: runId, seed: result.initSeed),
                ownerId: ownerId,
                result: result,
                initialCondition: initialCondition,
                configHash: topologyHash
            )
            let entry = archiveResearchLibraryEntry(
                creature: creature,
                runId: runId,
                configHash: topologyHash
            )
            entries.append(entry)
        }

        print("scout_dir: \(scoutURL.path)")
        print("run_id: \(runId)")
        print("results_total: \(results.count)  selected: \(selected.count)")
        print("specimen_id\tinit_seed\tscore")
        for (entry, result) in zip(entries, selected) {
            let specimenId = libraryResultStableKey(runId: runId, result: result)
            let scoreText = result.score.map { String(format: "%+.4f", $0) } ?? "n/a"
            print("\(specimenId)\t\(result.initSeed)\t\(scoreText)")
            _ = entry
        }

        if validateOnly {
            print("validate-only: not writing library/index.jsonl")
            return
        }

        let indexURL = try ResearchLibraryWriter.write(entries: entries, runDirectory: scoutURL)
        print("\nlibrary index: \(indexURL.path)")
    }
}

private func synthesizedCreatureName(runId: String, seed: Int) -> String {
    "lib-\(runId)-\(seed)"
}

func libraryResultStableKey(runId: String, result: SimulationResultData) -> String {
    "result:\(runId)|overall|\(result.initSeed)"
}
