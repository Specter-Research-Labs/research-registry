import Distributed
@preconcurrency import DistributedCluster
import Foundation
import Logging

public actor IMGEPController {
    private let system: ClusterSystem
    private let baseConfig: LeniaBaseConfig
    private let searchConfig: ParsedSearchConfig
    private let imgepConfig: IMGEPConfig
    private let outputDir: URL
    private let logger: Logger
    private let ranges: KernelParamRanges
    private let nbK: Int
    private let implementation: ImplementationSettings
    private let patternStream: PatternStream?
    private let mutationSchedule: [IMGEPMutationProfile]?

    private var workers: [LeniaWorker] = []
    private var topResults: [SimulationResultData] = []
    private var history: [IMGEPHistoryEntry] = []
    private var nextSeed: Int

    public init(
        system: ClusterSystem,
        baseConfigPath: String,
        searchConfigPath: String,
        imgepConfigPath: String,
        outputDir: String,
        logger: Logger
    ) throws {
        self.system = system
        self.outputDir = URL(fileURLWithPath: outputDir)
        self.logger = logger

        let baseData = try Data(contentsOf: URL(fileURLWithPath: baseConfigPath))
        self.baseConfig = try JSONDecoder().decode(LeniaBaseConfig.self, from: baseData)

        let searchData = try Data(contentsOf: URL(fileURLWithPath: searchConfigPath))
        self.searchConfig = try JSONDecoder().decode(ParsedSearchConfig.self, from: searchData)

        let imgepData = try Data(contentsOf: URL(fileURLWithPath: imgepConfigPath))
        self.imgepConfig = try JSONDecoder().decode(IMGEPConfig.self, from: imgepData)

        if let experiment = imgepConfig.experiment {
            self.patternStream = PatternStream(config: experiment.patternStream)
            self.mutationSchedule = experiment.mutationSchedule.profiles
        } else {
            self.patternStream = nil
            self.mutationSchedule = nil
        }

        guard let ranges = baseConfig.params.ranges else {
            fatalError("IMGEP requires params.ranges in base config for mutation.")
        }
        self.ranges = ranges

        let (c0, _) = connFromMatrix(baseConfig.connectivity)
        self.nbK = c0.count
        self.implementation = resolveImplementationSettings(
            implementation: baseConfig.implementation,
            border: baseConfig.reintegration.border
        )
        self.nextSeed = searchConfig.seedStart

        try FileManager.default.createDirectory(
            at: self.outputDir,
            withIntermediateDirectories: true
        )
    }

    public func start() async throws {
        validateConfig()
        await listenForWorkers()
        try await waitForWorkers(minCount: 1)

        let resultsHandle = try openFileHandle("results.jsonl")
        let historyHandle = try openFileHandle("history.jsonl")
        let activityHandle = searchConfig.activity?.enabled == true ? try openFileHandle("activity.jsonl") : nil

        var rng = SeededRandomNumberGenerator(seed: UInt64(searchConfig.seedStart))
        var iteration = 0
        let total = imgepConfig.iterations

        while iteration < total {
            let remaining = total - iteration
            let batchCount = min(imgepConfig.batchSize, remaining)
            let trials = buildTrials(count: batchCount, iteration: iteration, rng: &rng)

            let results = try await dispatchTrials(trials)
            for trialResult in results {
                appendResults(trialResult.results, handle: resultsHandle)
                appendActivitySummaries(trialResult.results, handle: activityHandle)
                if let entry = makeHistoryEntry(from: trialResult) {
                    history.append(entry)
                    appendHistory(entry, handle: historyHandle)
                }
                updateTopResults(from: trialResult.results)
            }

            writeTopResults()
            iteration += batchCount
            logger.info("IMGEP progress: \(iteration)/\(total) iterations")
        }

        writeSummary(totalIterations: total)
        resultsHandle.closeFile()
        historyHandle.closeFile()
        activityHandle?.closeFile()
    }

    private func validateConfig() {
        guard imgepConfig.iterations > 0 else {
            fatalError("IMGEP iterations must be > 0.")
        }
        guard imgepConfig.warmupIterations >= 0 else {
            fatalError("IMGEP warmupIterations must be >= 0.")
        }
        guard imgepConfig.batchSize > 0 else {
            fatalError("IMGEP batchSize must be > 0.")
        }
        guard imgepConfig.seedsPerCandidate > 0 else {
            fatalError("IMGEP seedsPerCandidate must be > 0.")
        }
        guard !imgepConfig.goal.features.isEmpty else {
            fatalError("IMGEP goal.features must be non-empty.")
        }
        if imgepConfig.goal.boundsMode != "auto" && imgepConfig.goal.boundsMode != "fixed" {
            fatalError("IMGEP goal.boundsMode must be 'auto' or 'fixed'.")
        }
        if imgepConfig.goal.boundsMode == "fixed" {
            guard let bounds = imgepConfig.goal.bounds else {
                fatalError("IMGEP goal.bounds must be provided when boundsMode is fixed.")
            }
            for feature in imgepConfig.goal.features {
                guard let range = bounds[feature], range.count == 2 else {
                    fatalError("IMGEP goal.bounds missing range for feature '\(feature)'.")
                }
            }
        }
        if imgepConfig.warmupIterations > imgepConfig.iterations {
            fatalError("IMGEP warmupIterations cannot exceed iterations.")
        }
        if let experiment = imgepConfig.experiment {
            if baseConfig.profile != .experimental {
                fatalError("IMGEP experiment requires profile=experimental.")
            }
            let profileCount = experiment.mutationSchedule.profiles.count
            if profileCount == 0 {
                fatalError("IMGEP experiment mutationSchedule.profiles must be non-empty.")
            }
            if experiment.patternStream.labelCount != profileCount {
                fatalError("IMGEP experiment patternStream.labelCount must match mutationSchedule.profiles count.")
            }
        }
    }

    private func buildTrials(
        count: Int,
        iteration: Int,
        rng: inout SeededRandomNumberGenerator
    ) -> [IMGEPTrial] {
        var trials: [IMGEPTrial] = []
        for idx in 0..<count {
            let globalIteration = iteration + idx
            let patternLabel = patternStream?.label(atIndex: globalIteration)
            if globalIteration < imgepConfig.warmupIterations || history.isEmpty {
                let params = randomParams(rng: &rng)
                trials.append(IMGEPTrial(
                    params: params,
                    goal: nil,
                    patternLabel: patternLabel,
                    patternIndex: globalIteration
                ))
            } else {
                let bounds = goalBounds()
                let goal = sampleGoal(bounds: bounds, rng: &rng)
                let idx = nearestNeighborIndex(goal: goal, history: history)
                let base = history[idx].params
                let mutationConfig = mutationConfig(for: patternLabel)
                let params = mutateParams(base: base, ranges: ranges, config: mutationConfig, rng: &rng)
                trials.append(IMGEPTrial(
                    params: params,
                    goal: goal,
                    patternLabel: patternLabel,
                    patternIndex: globalIteration
                ))
            }
        }
        return trials
    }

    private func goalBounds() -> [(min: Float, max: Float)] {
        if imgepConfig.goal.boundsMode == "fixed" {
            guard let bounds = imgepConfig.goal.bounds else {
                fatalError("IMGEP goal.bounds must be provided when boundsMode is fixed.")
            }
            return imgepConfig.goal.features.map { feature in
                guard let range = bounds[feature], range.count == 2 else {
                    fatalError("IMGEP goal.bounds missing range for feature '\(feature)'.")
                }
                return (min: range[0], max: range[1])
            }
        }
        guard !history.isEmpty else {
            fatalError("IMGEP goal bounds requested before history is populated.")
        }
        return boundsFromHistory(history: history)
    }

    private func randomParams(rng: inout SeededRandomNumberGenerator) -> KernelParams {
        let seed = Int.random(in: 0...Int.max, using: &rng)
        let resolved = generateRandomParams(seed: seed, nbK: nbK, ranges: ranges)
        return resolved.toKernelParams()
    }

    private func mutationConfig(for label: Int?) -> IMGEPMutationConfig {
        guard let label = label, let profiles = mutationSchedule else {
            return imgepConfig.mutation
        }
        if label < 0 || label >= profiles.count {
            fatalError("IMGEP experiment pattern label is out of range.")
        }
        let profile = profiles[label]
        return IMGEPMutationConfig(std: profile.std, clip: profile.clip)
    }

    private func sweepOverrides(for trial: IMGEPTrial) -> [String: Double]? {
        guard let label = trial.patternLabel else { return nil }
        var overrides: [String: Double] = [
            "pattern_label": Double(label)
        ]
        if let index = trial.patternIndex {
            overrides["pattern_index"] = Double(index)
        }
        return overrides
    }

    private func dispatchTrials(_ trials: [IMGEPTrial]) async throws -> [IMGEPTrialResult] {
        let workersSnapshot = workers
        if workersSnapshot.isEmpty {
            fatalError("No workers available for IMGEP dispatch.")
        }

        var jobs: [IMGEPJob] = []
        jobs.reserveCapacity(trials.count)
        for (idx, trial) in trials.enumerated() {
            let seedStart = nextSeed
            nextSeed += imgepConfig.seedsPerCandidate * searchConfig.seedStride
            let base = baseConfigWithParams(trial.params)
            let sweepOverrides = sweepOverrides(for: trial)
            let job = SimulationJob(
                id: "imgep-\(idx)-\(seedStart)",
                seedStart: seedStart,
                count: imgepConfig.seedsPerCandidate,
                baseConfig: base,
                searchConfig: searchConfig,
                sweepOverrides: sweepOverrides
            )
            jobs.append(IMGEPJob(trial: trial, job: job))
        }

        return try await withThrowingTaskGroup(of: IMGEPTrialResult.self) { group in
            for (idx, job) in jobs.enumerated() {
                let worker = workersSnapshot[idx % workersSnapshot.count]
                group.addTask {
                    let result = try await worker.process(job: job.job)
                    return IMGEPTrialResult(
                        trial: job.trial,
                        result: result,
                        results: result.results.isEmpty ? nil : result.results
                    )
                }
            }

            var collected: [IMGEPTrialResult] = []
            for try await result in group {
                collected.append(result)
            }
            return collected
        }
    }

    private func makeHistoryEntry(from trialResult: IMGEPTrialResult) -> IMGEPHistoryEntry? {
        guard let results = trialResult.results, !results.isEmpty else { return nil }
        let representative = selectRepresentativeResult(results)
        let embedding = goalVector(from: representative, features: imgepConfig.goal.features)
        return IMGEPHistoryEntry(
            seed: representative.seed,
            params: representative.params,
            metrics: representative.metrics,
            embedding: embedding,
            goal: trialResult.trial.goal,
            score: representative.score
        )
    }

    private func selectRepresentativeResult(_ results: [SimulationResultData]) -> SimulationResultData {
        if let best = topSimulationResults(from: results, limit: 1).first {
            return best
        }
        return results[0]
    }

    private func updateTopResults(from results: [SimulationResultData]?) {
        guard let results = results else { return }
        mergeTopSimulationResults(results, into: &topResults, limit: searchConfig.topK)
    }

    private func appendResults(_ results: [SimulationResultData]?, handle: FileHandle) {
        guard let results = results else { return }
        do {
            try appendResearchJSONLines(results, to: handle)
        } catch {
            logger.error("Failed to append IMGEP results: \(error)")
        }
    }

    private func appendHistory(_ entry: IMGEPHistoryEntry, handle: FileHandle) {
        do {
            try appendResearchJSONLines([entry], to: handle)
        } catch {
            logger.error("Failed to append IMGEP history: \(error)")
        }
    }

    private func appendActivitySummaries(_ results: [SimulationResultData]?, handle: FileHandle?) {
        guard let results = results, let handle = handle else { return }
        guard let activityConfig = searchConfig.activity else { return }
        do {
            try appendResearchJSONLines(
                activitySummaryRecords(from: results, config: activityConfig),
                to: handle
            )
        } catch {
            logger.error("Failed to append IMGEP activity summaries: \(error)")
        }
    }

    private func writeTopResults() {
        do {
            try writeTopSimulationResultsSnapshot(
                topResults,
                to: outputDir.appendingPathComponent("top.json")
            )
        } catch {
            logger.error("Failed to write IMGEP top results: \(error)")
        }
    }

    private func writeSummary(totalIterations: Int) {
        let summary: [String: Any] = [
            "iterations": totalIterations,
            "history_count": history.count,
            "top_count": topResults.count,
            "workers_used": workers.count,
            "implementation": [
                "mode": implementation.mode,
                "border": implementation.border,
                "gradient_boundary": implementation.gradientBoundary,
                "alpha_mode": implementation.alphaMode,
                "kernel_profile": implementation.kernelProfile,
                "flow_clip": implementation.flowClip
            ]
        ]
        let summaryURL = outputDir.appendingPathComponent("summary.json")
        if let data = try? JSONSerialization.data(withJSONObject: summary, options: .prettyPrinted) {
            try? data.write(to: summaryURL)
        }
    }

    private func baseConfigWithParams(_ params: KernelParams) -> LeniaBaseConfig {
        var config = baseConfig
        config.params = ParamsConfig(
            mode: "explicit",
            seed: nil,
            ranges: nil,
            r: params.r,
            b: params.b,
            w: params.w,
            a: params.a,
            m: params.m,
            s: params.s,
            h: params.h,
            R: params.R
        )
        return config
    }

    private func listenForWorkers() async {
        let clusterSystem = self.system
        Task {
            for await worker in await clusterSystem.receptionist.listing(of: .leniaWorkers) {
                await self.addWorker(worker)
            }
        }
    }

    private func addWorker(_ worker: LeniaWorker) async {
        if workers.contains(where: { $0.id == worker.id }) {
            return
        }
        workers.append(worker)
        if let status = try? await worker.getStatus() {
            logger.info("IMGEP worker joined: \(status.workerId)")
        } else {
            logger.info("IMGEP worker joined.")
        }
    }

    private func waitForWorkers(minCount: Int) async throws {
        let maxWaitSeconds = 120
        var waited = 0
        while workers.count < minCount {
            if waited >= maxWaitSeconds {
                throw NSError(domain: "IMGEPController", code: 1, userInfo: [NSLocalizedDescriptionKey: "No workers available."])
            }
            try await Task.sleep(for: .seconds(1))
            waited += 1
        }
    }

    private func openFileHandle(_ name: String) throws -> FileHandle {
        let url = outputDir.appendingPathComponent(name)
        if !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: nil)
        }
        let handle = try FileHandle(forWritingTo: url)
        handle.seekToEndOfFile()
        return handle
    }
    private struct IMGEPJob {
        let trial: IMGEPTrial
        let job: SimulationJob
    }

    private struct IMGEPTrialResult {
        let trial: IMGEPTrial
        let result: SimulationResult
        let results: [SimulationResultData]?
    }

    private struct IMGEPTrial {
        let params: KernelParams
        let goal: [Float]?
        let patternLabel: Int?
        let patternIndex: Int?
    }
}
