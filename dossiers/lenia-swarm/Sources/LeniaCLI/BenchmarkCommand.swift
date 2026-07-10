import ArgumentParser
import Foundation
import LeniaCore

private let benchmarkArtifactSchemaVersion = 2

struct BenchmarkCommand: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "benchmark",
        abstract: "Benchmark Flow Lenia backends"
    )

    @Option(name: .long, help: "Batch size for parallel simulation")
    var batchSize: Int = 16

    @Option(name: .long, help: "Number of simulation steps")
    var steps: Int = 100

    @Option(name: .long, help: "Grid size for the square simulation world")
    var gridSize: Int = 128

    @Flag(name: .long, help: "Benchmark the Lenia Lab sandbox step backends")
    var sandbox: Bool = false

    @Flag(name: .long, help: "Benchmark the headless Flow Lenia simulator backends")
    var flowLenia: Bool = false

    @Flag(name: .long, help: "Benchmark the headless SearchEngine backends on the canonical paper-compatible lane")
    var search: Bool = false

    @Flag(name: .long, help: "Benchmark the EvolutionEngine backends on the canonical paper-compatible lane")
    var evolution: Bool = false

    @Flag(name: .long, help: "Run a direct persistent Apple Metal sweep over grid/channel/kernel counts")
    var metalSweep: Bool = false

    @Flag(name: .long, help: "Include synchronous per-stage Metal timings in --metal-sweep output")
    var profileStages: Bool = false

    @Option(name: .long, help: "Comma-separated grid sizes for --metal-sweep")
    var metalGridSizes: String = "128,256,512"

    @Option(name: .long, help: "Comma-separated channel counts for --metal-sweep")
    var metalChannelCounts: String = "1,2"

    @Option(name: .long, help: "Comma-separated kernel counts for --metal-sweep")
    var metalKernelCounts: String = "4,10"

    @Option(name: .long, help: "Comma-separated parameter reintegration modes for --metal-sweep: true,false")
    var metalReintegrateParams: String = "true"

    @Option(name: .long, help: "Warmup steps before timing each --metal-sweep case")
    var metalWarmupSteps: Int = 5

    @Option(name: .long, help: "Warmup runs before each timed search/evolution benchmark sample")
    var warmupRuns: Int = 1

    @Option(name: .long, help: "Timed samples per backend for search/evolution benchmark reporting")
    var repeatRuns: Int = 5

    @Option(name: .long, help: "Frame-observation stride for search benchmarks; zero disables observation")
    var searchObservationStride: Int = 0

    @Option(name: .long, help: "Backend filter for backend benchmarks: metal-full|all|mlx")
    var backend: String = "metal-full"

    @Option(name: .shortAndLong, help: "Output directory for benchmark artifacts")
    var output: String?

    func run() async throws {
        guard gridSize > 0 else {
            throw ValidationError("--grid-size must be greater than zero")
        }
        guard warmupRuns >= 0 else {
            throw ValidationError("--warmup-runs must be >= 0")
        }
        guard repeatRuns > 0 else {
            throw ValidationError("--repeat-runs must be > 0")
        }
        guard searchObservationStride >= 0 else {
            throw ValidationError("--search-observation-stride must be >= 0")
        }
        guard search || searchObservationStride == 0 else {
            throw ValidationError("--search-observation-stride requires --search")
        }
        guard metalWarmupSteps >= 0 else {
            throw ValidationError("--metal-warmup-steps must be >= 0")
        }
        if (search || evolution) && gridSize < 40 {
            throw ValidationError("--search and --evolution require --grid-size >= 40 for the paper-profile init patch.")
        }
        let modeCount = [sandbox, flowLenia, search, evolution, metalSweep].filter { $0 }.count
        if modeCount > 1 {
            throw ValidationError("--sandbox, --flow-lenia, --search, --evolution, and --metal-sweep are mutually exclusive")
        }
        if modeCount == 0 {
            throw ValidationError("Choose one benchmark mode: --flow-lenia, --sandbox, --search, --evolution, or --metal-sweep.")
        }
        let computeBackends = try selectedComputeBackends(backend)
        let sandboxBackends = try selectedSandboxBackends(backend)
        let artifactRunID = LeniaLogging.makeRunId(prefix: "benchmark")

        if metalSweep {
            try runMetalSweepBenchmark(
                gridSizes: parsePositiveIntegerList(metalGridSizes, option: "--metal-grid-sizes"),
                channelCounts: parsePositiveIntegerList(metalChannelCounts, option: "--metal-channel-counts"),
                kernelCounts: parsePositiveIntegerList(metalKernelCounts, option: "--metal-kernel-counts"),
                reintegrateParamModes: parseBooleanList(metalReintegrateParams, option: "--metal-reintegrate-params"),
                batchSize: batchSize,
                steps: steps,
                warmupSteps: metalWarmupSteps,
                profileStages: profileStages
            )
            return
        }

        print("============================================================")
        print("Flow Lenia Swift Benchmark")
        print("============================================================")
        print("Grid: \(gridSize)x\(gridSize)")
        print("Channels: 1")
        print("Kernels: 10")
        print("Batch size: \(batchSize)")
        print("Steps: \(steps)")
        if search || evolution {
            print("Warmup runs: \(warmupRuns)")
            print("Repeat runs: \(repeatRuns)")
        }
        if search, searchObservationStride > 0 {
            print("Search observation stride: \(searchObservationStride)")
        }

        let ranges = KernelParamRanges(
            r: [0.2, 1.0],
            b: [0.0, 1.0],
            w: [0.01, 0.5],
            a: [0.0, 1.0],
            m: [0.05, 0.5],
            s: [0.001, 0.2],
            h: [0.0, 1.0],
            R: [2.0, 25.0]
        )
        let params = generateRandomParams(seed: 9, nbK: 10, ranges: ranges)

        if flowLenia {
            print("\nHeadless Flow Lenia simulator backends")
            let results = computeBackends.map {
                benchmarkFlowLeniaSimulatorBackend(
                    gridSize: gridSize,
                    steps: steps,
                    params: params,
                    backend: $0
                )
            }
            for result in results {
                print("   \(result.backend.displayName): \(String(format: "%.2f", result.stepsPerSecond)) steps/s")
                if let stageTimings = result.stageTimings {
                    print(
                        "      full-metal sync stages: prepare \(String(format: "%.2f", stageTimings.prepareMs)) ms, " +
                            "fft \(String(format: "%.2f", stageTimings.fftMs)) ms, " +
                            "growth \(String(format: "%.2f", stageTimings.growthReduceMs)) ms, " +
                            "flow \(String(format: "%.2f", stageTimings.flowMs)) ms, " +
                            "reintegrate \(String(format: "%.2f", stageTimings.reintegrateMs)) ms, " +
                            "total \(String(format: "%.2f", stageTimings.totalMs)) ms"
                    )
                }
            }

            if let mlx = results.first(where: { $0.backend == .mlx }),
               let full = results.first(where: { $0.backend == .metalFull }) {
                print("\nSpeedup (full vs mlx): \(String(format: "%.2f", full.stepsPerSecond / mlx.stepsPerSecond))x")
            }
            if let output {
                let artifactURL = try writeBenchmarkArtifact(
                    BenchmarkArtifactFile(
                        schemaVersion: benchmarkArtifactSchemaVersion,
                        generatedAt: benchmarkTimestampString(),
                        host: ProcessInfo.processInfo.hostName,
                        osVersion: ProcessInfo.processInfo.operatingSystemVersionString,
                        mode: "paper-flow",
                        throughputUnit: "steps_per_second",
                        gridSize: gridSize,
                        batchSize: batchSize,
                        steps: steps,
                        warmupRuns: nil,
                        repeatRuns: nil,
                        observationStride: nil,
                        backends: results.map(benchmarkBackendArtifact)
                    ),
                    runID: artifactRunID,
                    output: output,
                    dossier: dossierName
                )
                print("Artifact: \(artifactURL.path)")
            }
            return
        }

        if sandbox {
            let gridPreset: LabGridPreset
            switch gridSize {
            case 128:
                gridPreset = .compact128
            case 256:
                gridPreset = .standard256
            case 512:
                gridPreset = .expansive512
            default:
                throw ValidationError("--sandbox supports --grid-size values 128, 256, or 512")
            }

            print("\nSandbox Step Backends")
            var results: [FlowSandboxBenchmarkResult] = []
            results.reserveCapacity(sandboxBackends.count)
            for backend in sandboxBackends {
                let result = await benchmarkFlowSandboxBackend(
                    gridPreset: gridPreset,
                    steps: steps,
                    params: params,
                    backend: backend
                )
                results.append(result)
            }
            for result in results {
                print("   \(result.backend.displayName): \(String(format: "%.2f", result.stepsPerSecond)) steps/s")
                if let stageTimings = result.stageTimings {
                    print(
                        "      full-metal sync stages: prepare \(String(format: "%.2f", stageTimings.prepareMs)) ms, " +
                            "fft \(String(format: "%.2f", stageTimings.fftMs)) ms, " +
                            "growth \(String(format: "%.2f", stageTimings.growthReduceMs)) ms, " +
                            "flow \(String(format: "%.2f", stageTimings.flowMs)) ms, " +
                            "reintegrate \(String(format: "%.2f", stageTimings.reintegrateMs)) ms, " +
                            "total \(String(format: "%.2f", stageTimings.totalMs)) ms"
                    )
                }
            }

            if let mlx = results.first(where: { $0.backend == .mlx }),
               let full = results.first(where: { $0.backend == .metalFull }) {
                print("\nSpeedup (full vs mlx): \(String(format: "%.2f", full.stepsPerSecond / mlx.stepsPerSecond))x")
            }
            if let output {
                let artifactURL = try writeBenchmarkArtifact(
                    BenchmarkArtifactFile(
                        schemaVersion: benchmarkArtifactSchemaVersion,
                        generatedAt: benchmarkTimestampString(),
                        host: ProcessInfo.processInfo.hostName,
                        osVersion: ProcessInfo.processInfo.operatingSystemVersionString,
                        mode: "sandbox",
                        throughputUnit: "steps_per_second",
                        gridSize: gridSize,
                        batchSize: batchSize,
                        steps: steps,
                        warmupRuns: nil,
                        repeatRuns: nil,
                        observationStride: nil,
                        backends: results.map(benchmarkBackendArtifact)
                    ),
                    runID: artifactRunID,
                    output: output,
                    dossier: dossierName
                )
                print("Artifact: \(artifactURL.path)")
            }
            return
        }

        if search {
            print("\nSearch Backends (Repeated Warmed Samples)")
            let stats = computeBackends.map { backend in
                repeatedBenchmarkStats(repeatRuns: repeatRuns) {
                    benchmarkSearchEngineBackend(
                        gridSize: gridSize,
                        batchSize: batchSize,
                        steps: steps,
                        params: params,
                        backend: backend,
                        warmupRuns: warmupRuns,
                        observationStride: searchObservationStride > 0 ? searchObservationStride : nil
                    )
                } throughput: { $0.seedsPerSecond } duration: { $0.duration }
            }
            for (backend, stat) in zip(computeBackends, stats) {
                let run = stat.sample
                print(
                    "   \(backend.displayName): median \(String(format: "%.2f", stat.throughput.median)) seeds/s, " +
                        "mean \(String(format: "%.2f", stat.throughput.mean)), " +
                        "range \(String(format: "%.2f", stat.throughput.min))...\(String(format: "%.2f", stat.throughput.max))"
                )
                print(
                    "      sim-steps median \(String(format: "%.2f", stat.derivedMedian(run.map { $0.simStepsPerSecond })))" +
                        "/s, " +
                        "mean duration \(String(format: "%.2f", stat.duration.mean * 1000.0)) ms"
                )
                print(
                    "      search profile median: state-build \(String(format: "%.2f", stat.derivedMedian(run.map { $0.profile.stateBuildMs }))) ms, " +
                        "param-build \(String(format: "%.2f", stat.derivedMedian(run.map { $0.profile.parameterBuildMs }))) ms, " +
                        "food-build \(String(format: "%.2f", stat.derivedMedian(run.map { $0.profile.foodBuildMs }))) ms, " +
                        "wall-build \(String(format: "%.2f", stat.derivedMedian(run.map { $0.profile.wallBuildMs }))) ms, " +
                        "chem-build \(String(format: "%.2f", stat.derivedMedian(run.map { $0.profile.chemFieldBuildMs }))) ms, " +
                        "runner-setup \(String(format: "%.2f", stat.derivedMedian(run.map { $0.profile.runnerSetupMs }))) ms"
                )
                print(
                    "      search profile median: rollout \(String(format: "%.2f", stat.derivedMedian(run.map { $0.profile.rolloutMs }))) ms, " +
                        "summary \(String(format: "%.2f", stat.derivedMedian(run.map { $0.profile.summaryReductionMs }))) ms, " +
                        "combined-observation \(String(format: "%.2f", stat.derivedMedian(run.map { $0.profile.combinedObservationMs }))) ms, " +
                        "materialization \(String(format: "%.2f", stat.derivedMedian(run.map { $0.profile.materializationMs }))) ms, " +
                        "postprocess \(String(format: "%.2f", stat.derivedMedian(run.map { $0.profile.postprocessMs }))) ms, " +
                        "total \(String(format: "%.2f", stat.derivedMedian(run.map { $0.profile.totalMs }))) ms"
                )
                print("      mass-observation synchronizations: \(run.map { $0.profile.massObservationSynchronizations }.sorted()[run.count / 2])")
                let stageSamples = run.compactMap(\.stageTimings)
                if !stageSamples.isEmpty {
                    print(
                        "      full-metal rollout stages median: fft \(String(format: "%.2f", stat.derivedMedian(stageSamples.map { $0.fftMs }))) ms, " +
                            "growth \(String(format: "%.2f", stat.derivedMedian(stageSamples.map { $0.growthReduceMs }))) ms, " +
                            "flow \(String(format: "%.2f", stat.derivedMedian(stageSamples.map { $0.flowMs }))) ms, " +
                            "reintegrate \(String(format: "%.2f", stat.derivedMedian(stageSamples.map { $0.reintegrateMs }))) ms, " +
                            "total \(String(format: "%.2f", stat.derivedMedian(stageSamples.map { $0.totalMs }))) ms"
                    )
                }
            }
            if let mlx = stats.first(where: { $0.sample.first?.backend == .mlx }),
               let full = stats.first(where: { $0.sample.first?.backend == .metalFull }) {
                print("\nMedian speedup (full vs mlx): \(String(format: "%.2f", full.throughput.median / mlx.throughput.median))x")
            }
            if let output {
                let backends = zip(computeBackends, stats).map {
                    benchmarkBackendArtifact(
                        backend: $0.0,
                        stats: $0.1,
                        sampleArtifact: benchmarkSearchSampleArtifact,
                        profileMedian: searchProfileMedianArtifact,
                        stageMedian: { samples, stats in
                            stageTimingsMedianArtifact(samples, stats: stats) { $0.stageTimings }
                        }
                    )
                }
                let artifactURL = try writeBenchmarkArtifact(
                    BenchmarkArtifactFile(
                        schemaVersion: benchmarkArtifactSchemaVersion,
                        generatedAt: benchmarkTimestampString(),
                        host: ProcessInfo.processInfo.hostName,
                        osVersion: ProcessInfo.processInfo.operatingSystemVersionString,
                        mode: "search",
                        throughputUnit: "seeds_per_second",
                        gridSize: gridSize,
                        batchSize: batchSize,
                        steps: steps,
                        warmupRuns: warmupRuns,
                        repeatRuns: repeatRuns,
                        observationStride: searchObservationStride > 0 ? searchObservationStride : nil,
                        backends: backends
                    ),
                    runID: artifactRunID,
                    output: output,
                    dossier: dossierName
                )
                print("Artifact: \(artifactURL.path)")
            }
            return
        }

        if evolution {
            if batchSize % 2 != 0 {
                throw ValidationError("--evolution requires an even --batch-size population")
            }
            print("\nEvolution Backends (Repeated Warmed Samples)")
            let stats = computeBackends.map { backend in
                repeatedBenchmarkStats(repeatRuns: repeatRuns) {
                    benchmarkEvolutionEngineBackend(
                        gridSize: gridSize,
                        population: batchSize,
                        steps: steps,
                        params: params,
                        backend: backend,
                        warmupRuns: warmupRuns
                    )
                } throughput: { $0.candidatesPerSecond } duration: { $0.duration }
            }
            for (backend, stat) in zip(computeBackends, stats) {
                let run = stat.sample
                print(
                    "   \(backend.displayName): median \(String(format: "%.2f", stat.throughput.median)) candidates/s, " +
                        "mean \(String(format: "%.2f", stat.throughput.mean)), " +
                        "range \(String(format: "%.2f", stat.throughput.min))...\(String(format: "%.2f", stat.throughput.max))"
                )
                print(
                    "      sim-steps median \(String(format: "%.2f", stat.derivedMedian(run.map { $0.simStepsPerSecond })))" +
                        "/s, " +
                        "rollout median \(String(format: "%.2f", stat.derivedMedian(run.map { $0.profile.rolloutMs }))) ms, " +
                        "fitness median \(String(format: "%.2f", stat.derivedMedian(run.map { $0.profile.fitnessMs }))) ms"
                )
                print(
                    "      generation profile median: candidate-setup \(String(format: "%.2f", stat.derivedMedian(run.map { $0.profile.candidateSetupMs }))) ms, " +
                        "kernel-compile \(String(format: "%.2f", stat.derivedMedian(run.map { $0.profile.kernelCompileMs }))) ms, " +
                        "state-build \(String(format: "%.2f", stat.derivedMedian(run.map { $0.profile.stateBuildMs }))) ms, " +
                        "field-build \(String(format: "%.2f", stat.derivedMedian(run.map { $0.profile.fieldBuildMs }))) ms, " +
                        "optimizer \(String(format: "%.2f", stat.derivedMedian(run.map { $0.profile.optimizerMs }))) ms, " +
                        "total \(String(format: "%.2f", stat.derivedMedian(run.map { $0.profile.totalMs }))) ms"
                )
                let stageSamples = run.compactMap(\.stageTimings)
                if !stageSamples.isEmpty {
                    print(
                        "      full-metal rollout stages median: fft \(String(format: "%.2f", stat.derivedMedian(stageSamples.map { $0.fftMs }))) ms, " +
                            "growth \(String(format: "%.2f", stat.derivedMedian(stageSamples.map { $0.growthReduceMs }))) ms, " +
                            "flow \(String(format: "%.2f", stat.derivedMedian(stageSamples.map { $0.flowMs }))) ms, " +
                            "reintegrate \(String(format: "%.2f", stat.derivedMedian(stageSamples.map { $0.reintegrateMs }))) ms, " +
                            "total \(String(format: "%.2f", stat.derivedMedian(stageSamples.map { $0.totalMs }))) ms"
                    )
                }
            }
            if let mlx = stats.first(where: { $0.sample.first?.backend == .mlx }),
               let full = stats.first(where: { $0.sample.first?.backend == .metalFull }) {
                print("\nMedian speedup (full vs mlx): \(String(format: "%.2f", full.throughput.median / mlx.throughput.median))x")
            }
            if let output {
                let backends = zip(computeBackends, stats).map {
                    benchmarkBackendArtifact(
                        backend: $0.0,
                        stats: $0.1,
                        sampleArtifact: benchmarkEvolutionSampleArtifact,
                        profileMedian: evolutionProfileMedianArtifact,
                        stageMedian: { samples, stats in
                            stageTimingsMedianArtifact(samples, stats: stats) { $0.stageTimings }
                        }
                    )
                }
                let artifactURL = try writeBenchmarkArtifact(
                    BenchmarkArtifactFile(
                        schemaVersion: benchmarkArtifactSchemaVersion,
                        generatedAt: benchmarkTimestampString(),
                        host: ProcessInfo.processInfo.hostName,
                        osVersion: ProcessInfo.processInfo.operatingSystemVersionString,
                        mode: "evolution",
                        throughputUnit: "candidates_per_second",
                        gridSize: gridSize,
                        batchSize: batchSize,
                        steps: steps,
                        warmupRuns: warmupRuns,
                        repeatRuns: repeatRuns,
                        observationStride: nil,
                        backends: backends
                    ),
                    runID: artifactRunID,
                    output: output,
                    dossier: dossierName
                )
                print("Artifact: \(artifactURL.path)")
            }
            return
        }

    }
}

private struct BenchmarkSeriesStats {
    let min: Double
    let max: Double
    let mean: Double
    let median: Double
}

struct BenchmarkSeriesArtifact: Codable {
    let min: Double
    let max: Double
    let mean: Double
    let median: Double
}

struct BenchmarkStageTimingsArtifact: Codable {
    let prepareMs: Double
    let fftMs: Double
    let growthReduceMs: Double
    let flowMs: Double
    let reintegrateMs: Double
    let totalMs: Double
}

struct BenchmarkSearchProfileArtifact: Codable {
    let stateBuildMs: Double
    let parameterBuildMs: Double
    let foodBuildMs: Double
    let wallBuildMs: Double
    let chemFieldBuildMs: Double
    let runnerSetupMs: Double
    let rolloutMs: Double
    let summaryReductionMs: Double
    let combinedObservationMs: Double
    let materializationMs: Double
    let massObservationSynchronizations: Int
    let postprocessMs: Double
    let totalMs: Double
}

struct BenchmarkEvolutionProfileArtifact: Codable {
    let candidateSetupMs: Double
    let kernelCompileMs: Double
    let stateBuildMs: Double
    let fieldBuildMs: Double
    let rolloutMs: Double
    let fitnessMs: Double
    let optimizerMs: Double
    let totalMs: Double
}

struct BenchmarkSampleArtifact: Codable {
    let durationSeconds: Double
    let throughput: Double
    let simStepsPerSecond: Double?
    let stageTimings: BenchmarkStageTimingsArtifact?
    let searchProfile: BenchmarkSearchProfileArtifact?
    let evolutionProfile: BenchmarkEvolutionProfileArtifact?
}

struct BenchmarkBackendArtifact: Codable {
    let backend: String
    let throughput: BenchmarkSeriesArtifact
    let durationSeconds: BenchmarkSeriesArtifact
    let simStepsPerSecond: BenchmarkSeriesArtifact?
    let stageTimingsMedian: BenchmarkStageTimingsArtifact?
    let searchProfileMedian: BenchmarkSearchProfileArtifact?
    let evolutionProfileMedian: BenchmarkEvolutionProfileArtifact?
    let samples: [BenchmarkSampleArtifact]
}

struct BenchmarkArtifactFile: Codable {
    let schemaVersion: Int
    let generatedAt: String
    let host: String
    let osVersion: String
    let mode: String
    let throughputUnit: String
    let gridSize: Int
    let batchSize: Int
    let steps: Int
    let warmupRuns: Int?
    let repeatRuns: Int?
    let observationStride: Int?
    let backends: [BenchmarkBackendArtifact]
}

private func selectedComputeBackends(_ value: String) throws -> [FlowLeniaComputeBackend] {
    let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    switch normalized {
    case "all":
        return FlowLeniaComputeBackend.allCases
    case "mlx", "mlx-swift":
        return [.mlx]
    case "metal-full":
        return [.metalFull]
    default:
        throw ValidationError("Unsupported --backend '\(value)'. Expected all, mlx, or metal-full.")
    }
}

private func selectedSandboxBackends(_ value: String) throws -> [FlowSandboxBackend] {
    let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    switch normalized {
    case "all":
        return FlowSandboxBackend.allCases
    case "mlx", "mlx-swift":
        return [.mlx]
    case "metal-full":
        return [.metalFull]
    default:
        throw ValidationError("Unsupported --backend '\(value)'. Expected all, mlx, or metal-full.")
    }
}

private func parsePositiveIntegerList(_ value: String, option: String) throws -> [Int] {
    let parts = value.split(separator: ",").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
    guard !parts.isEmpty else {
        throw ValidationError("\(option) must contain at least one integer")
    }
    var parsed: [Int] = []
    parsed.reserveCapacity(parts.count)
    for part in parts {
        guard let number = Int(part), number > 0 else {
            throw ValidationError("\(option) contains invalid value '\(part)'; expected positive integers")
        }
        parsed.append(number)
    }
    return parsed
}

private func parseBooleanList(_ value: String, option: String) throws -> [Bool] {
    let parts = value.split(separator: ",").map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
    guard !parts.isEmpty else {
        throw ValidationError("\(option) must contain at least one boolean")
    }
    var parsed: [Bool] = []
    parsed.reserveCapacity(parts.count)
    for part in parts {
        switch part {
        case "true", "yes", "on", "1":
            parsed.append(true)
        case "false", "no", "off", "0":
            parsed.append(false)
        default:
            throw ValidationError("\(option) contains invalid value '\(part)'; expected true or false")
        }
    }
    return parsed
}

private func runMetalSweepBenchmark(
    gridSizes: [Int],
    channelCounts: [Int],
    kernelCounts: [Int],
    reintegrateParamModes: [Bool],
    batchSize: Int,
    steps: Int,
    warmupSteps: Int,
    profileStages: Bool
) throws {
    print("============================================================")
    print("Flow Lenia Apple Metal Sweep")
    print("============================================================")
    print("Batch size: \(batchSize)")
    print("Steps: \(steps)")
    print("Warmup steps: \(warmupSteps)")
    print("Grids: \(gridSizes.map(String.init).joined(separator: ","))")
    print("Channels: \(channelCounts.map(String.init).joined(separator: ","))")
    print("Kernels: \(kernelCounts.map(String.init).joined(separator: ","))")
    print("Reintegrate params: \(reintegrateParamModes.map { $0 ? "true" : "false" }.joined(separator: ","))")
    print("")
    let baseColumns = "grid,channels,kernels,reintegrate_params,batch,steps,duration_s,steps_per_s,gcell_channel_steps_per_s,visible_working_set_mb"
    if profileStages {
        print(baseColumns + ",fft_ms,growth_ms,flow_ms,reintegrate_ms,total_profile_ms")
    } else {
        print(baseColumns)
    }

    for gridSize in gridSizes {
        for channels in channelCounts {
            for kernels in kernelCounts {
                for reintegrateParams in reintegrateParamModes {
                    let result = benchmarkFlowLeniaMetalSweepCase(
                        FlowLeniaMetalSweepCase(gridSize: gridSize, channels: channels, kernels: kernels),
                        batchSize: batchSize,
                        steps: steps,
                        warmupSteps: warmupSteps,
                        reintegrateParams: reintegrateParams,
                        profileStages: profileStages
                    )
                    let baseLine =
                        "\(result.gridSize)," +
                            "\(result.channels)," +
                            "\(result.kernels)," +
                            "\(result.reintegrateParams ? "true" : "false")," +
                            "\(result.batchSize)," +
                            "\(result.steps)," +
                            "\(String(format: "%.6f", result.duration))," +
                            "\(String(format: "%.2f", result.stepsPerSecond))," +
                            "\(String(format: "%.3f", result.cellChannelStepsPerSecond / 1_000_000_000.0))," +
                            "\(String(format: "%.1f", Double(result.visibleWorkingSetBytes) / 1_048_576.0))"
                    if let stageTimings = result.stageTimings {
                        print(
                            baseLine + "," +
                                "\(String(format: "%.3f", stageTimings.fftMs))," +
                                "\(String(format: "%.3f", stageTimings.growthReduceMs))," +
                                "\(String(format: "%.3f", stageTimings.flowMs))," +
                                "\(String(format: "%.3f", stageTimings.reintegrateMs))," +
                                "\(String(format: "%.3f", stageTimings.totalMs))"
                        )
                    } else {
                        print(baseLine)
                    }
                }
            }
        }
    }
}

private struct RepeatedBenchmarkStats<Result> {
    let sample: [Result]
    let duration: BenchmarkSeriesStats
    let throughput: BenchmarkSeriesStats

    func derivedMedian(_ values: [Double]) -> Double {
        summarizeBenchmarkSeries(values).median
    }
}

private func repeatedBenchmarkStats<Result>(
    repeatRuns: Int,
    benchmark: () -> Result,
    throughput: (Result) -> Double,
    duration: (Result) -> TimeInterval
) -> RepeatedBenchmarkStats<Result> {
    var samples: [Result] = []
    samples.reserveCapacity(repeatRuns)
    for _ in 0..<repeatRuns {
        samples.append(benchmark())
    }
    return RepeatedBenchmarkStats(
        sample: samples,
        duration: summarizeBenchmarkSeries(samples.map { duration($0) }),
        throughput: summarizeBenchmarkSeries(samples.map { throughput($0) })
    )
}

private func summarizeBenchmarkSeries(_ values: [Double]) -> BenchmarkSeriesStats {
    guard !values.isEmpty else {
        fatalError("Benchmark summary requires at least one sample.")
    }
    let sorted = values.sorted()
    let count = sorted.count
    let median: Double
    if count % 2 == 0 {
        median = (sorted[count / 2 - 1] + sorted[count / 2]) * 0.5
    } else {
        median = sorted[count / 2]
    }
    let mean = sorted.reduce(0, +) / Double(count)
    return BenchmarkSeriesStats(
        min: sorted[0],
        max: sorted[count - 1],
        mean: mean,
        median: median
    )
}

func benchmarkTimestampString() -> String {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter.string(from: Date())
}

private func benchmarkSeriesArtifact(_ stats: BenchmarkSeriesStats) -> BenchmarkSeriesArtifact {
    BenchmarkSeriesArtifact(
        min: stats.min,
        max: stats.max,
        mean: stats.mean,
        median: stats.median
    )
}

private func benchmarkSeriesArtifact(single value: Double) -> BenchmarkSeriesArtifact {
    benchmarkSeriesArtifact(summarizeBenchmarkSeries([value]))
}

private func benchmarkStageTimingsArtifact(_ timings: FlowSandboxMetalStageTimings) -> BenchmarkStageTimingsArtifact {
    BenchmarkStageTimingsArtifact(
        prepareMs: timings.prepareMs,
        fftMs: timings.fftMs,
        growthReduceMs: timings.growthReduceMs,
        flowMs: timings.flowMs,
        reintegrateMs: timings.reintegrateMs,
        totalMs: timings.totalMs
    )
}

private func benchmarkSearchProfileArtifact(_ profile: SearchBatchProfile) -> BenchmarkSearchProfileArtifact {
    BenchmarkSearchProfileArtifact(
        stateBuildMs: profile.stateBuildMs,
        parameterBuildMs: profile.parameterBuildMs,
        foodBuildMs: profile.foodBuildMs,
        wallBuildMs: profile.wallBuildMs,
        chemFieldBuildMs: profile.chemFieldBuildMs,
        runnerSetupMs: profile.runnerSetupMs,
        rolloutMs: profile.rolloutMs,
        summaryReductionMs: profile.summaryReductionMs,
        combinedObservationMs: profile.combinedObservationMs,
        materializationMs: profile.materializationMs,
        massObservationSynchronizations: profile.massObservationSynchronizations,
        postprocessMs: profile.postprocessMs,
        totalMs: profile.totalMs
    )
}

private func benchmarkEvolutionProfileArtifact(_ profile: ESGenerationProfile) -> BenchmarkEvolutionProfileArtifact {
    BenchmarkEvolutionProfileArtifact(
        candidateSetupMs: profile.candidateSetupMs,
        kernelCompileMs: profile.kernelCompileMs,
        stateBuildMs: profile.stateBuildMs,
        fieldBuildMs: profile.fieldBuildMs,
        rolloutMs: profile.rolloutMs,
        fitnessMs: profile.fitnessMs,
        optimizerMs: profile.optimizerMs,
        totalMs: profile.totalMs
    )
}

private func benchmarkBackendArtifact(_ result: FlowSandboxBenchmarkResult) -> BenchmarkBackendArtifact {
    BenchmarkBackendArtifact(
        backend: result.backend.displayName,
        throughput: benchmarkSeriesArtifact(single: result.stepsPerSecond),
        durationSeconds: benchmarkSeriesArtifact(single: result.duration),
        simStepsPerSecond: benchmarkSeriesArtifact(single: result.stepsPerSecond),
        stageTimingsMedian: result.stageTimings.map(benchmarkStageTimingsArtifact),
        searchProfileMedian: nil,
        evolutionProfileMedian: nil,
        samples: [
            BenchmarkSampleArtifact(
                durationSeconds: result.duration,
                throughput: result.stepsPerSecond,
                simStepsPerSecond: result.stepsPerSecond,
                stageTimings: result.stageTimings.map(benchmarkStageTimingsArtifact),
                searchProfile: nil,
                evolutionProfile: nil
            )
        ]
    )
}

private func benchmarkBackendArtifact(_ result: FlowLeniaBenchmarkResult) -> BenchmarkBackendArtifact {
    BenchmarkBackendArtifact(
        backend: result.backend.displayName,
        throughput: benchmarkSeriesArtifact(single: result.stepsPerSecond),
        durationSeconds: benchmarkSeriesArtifact(single: result.duration),
        simStepsPerSecond: benchmarkSeriesArtifact(single: result.stepsPerSecond),
        stageTimingsMedian: result.stageTimings.map(benchmarkStageTimingsArtifact),
        searchProfileMedian: nil,
        evolutionProfileMedian: nil,
        samples: [
            BenchmarkSampleArtifact(
                durationSeconds: result.duration,
                throughput: result.stepsPerSecond,
                simStepsPerSecond: result.stepsPerSecond,
                stageTimings: result.stageTimings.map(benchmarkStageTimingsArtifact),
                searchProfile: nil,
                evolutionProfile: nil
            )
        ]
    )
}

private func benchmarkSearchSampleArtifact(_ result: SearchBenchmarkResult) -> BenchmarkSampleArtifact {
    BenchmarkSampleArtifact(
        durationSeconds: result.duration,
        throughput: result.seedsPerSecond,
        simStepsPerSecond: result.simStepsPerSecond,
        stageTimings: result.stageTimings.map(benchmarkStageTimingsArtifact),
        searchProfile: benchmarkSearchProfileArtifact(result.profile),
        evolutionProfile: nil
    )
}

private func benchmarkEvolutionSampleArtifact(_ result: EvolutionBenchmarkResult) -> BenchmarkSampleArtifact {
    BenchmarkSampleArtifact(
        durationSeconds: result.duration,
        throughput: result.candidatesPerSecond,
        simStepsPerSecond: result.simStepsPerSecond,
        stageTimings: result.stageTimings.map(benchmarkStageTimingsArtifact),
        searchProfile: nil,
        evolutionProfile: benchmarkEvolutionProfileArtifact(result.profile)
    )
}

private func searchProfileMedianArtifact(
    _ samples: [SearchBenchmarkResult],
    stats: RepeatedBenchmarkStats<SearchBenchmarkResult>
) -> BenchmarkSearchProfileArtifact {
    BenchmarkSearchProfileArtifact(
        stateBuildMs: stats.derivedMedian(samples.map { $0.profile.stateBuildMs }),
        parameterBuildMs: stats.derivedMedian(samples.map { $0.profile.parameterBuildMs }),
        foodBuildMs: stats.derivedMedian(samples.map { $0.profile.foodBuildMs }),
        wallBuildMs: stats.derivedMedian(samples.map { $0.profile.wallBuildMs }),
        chemFieldBuildMs: stats.derivedMedian(samples.map { $0.profile.chemFieldBuildMs }),
        runnerSetupMs: stats.derivedMedian(samples.map { $0.profile.runnerSetupMs }),
        rolloutMs: stats.derivedMedian(samples.map { $0.profile.rolloutMs }),
        summaryReductionMs: stats.derivedMedian(samples.map { $0.profile.summaryReductionMs }),
        combinedObservationMs: stats.derivedMedian(samples.map { $0.profile.combinedObservationMs }),
        materializationMs: stats.derivedMedian(samples.map { $0.profile.materializationMs }),
        massObservationSynchronizations: samples.map { $0.profile.massObservationSynchronizations }.sorted()[samples.count / 2],
        postprocessMs: stats.derivedMedian(samples.map { $0.profile.postprocessMs }),
        totalMs: stats.derivedMedian(samples.map { $0.profile.totalMs })
    )
}

private func evolutionProfileMedianArtifact(
    _ samples: [EvolutionBenchmarkResult],
    stats: RepeatedBenchmarkStats<EvolutionBenchmarkResult>
) -> BenchmarkEvolutionProfileArtifact {
    BenchmarkEvolutionProfileArtifact(
        candidateSetupMs: stats.derivedMedian(samples.map { $0.profile.candidateSetupMs }),
        kernelCompileMs: stats.derivedMedian(samples.map { $0.profile.kernelCompileMs }),
        stateBuildMs: stats.derivedMedian(samples.map { $0.profile.stateBuildMs }),
        fieldBuildMs: stats.derivedMedian(samples.map { $0.profile.fieldBuildMs }),
        rolloutMs: stats.derivedMedian(samples.map { $0.profile.rolloutMs }),
        fitnessMs: stats.derivedMedian(samples.map { $0.profile.fitnessMs }),
        optimizerMs: stats.derivedMedian(samples.map { $0.profile.optimizerMs }),
        totalMs: stats.derivedMedian(samples.map { $0.profile.totalMs })
    )
}

private func stageTimingsMedianArtifact<Result>(
    _ samples: [Result],
    stats: RepeatedBenchmarkStats<Result>,
    extract: (Result) -> FlowSandboxMetalStageTimings?
) -> BenchmarkStageTimingsArtifact? {
    let stageSamples = samples.compactMap(extract)
    guard !stageSamples.isEmpty else {
        return nil
    }
    return BenchmarkStageTimingsArtifact(
        prepareMs: stats.derivedMedian(stageSamples.map(\.prepareMs)),
        fftMs: stats.derivedMedian(stageSamples.map(\.fftMs)),
        growthReduceMs: stats.derivedMedian(stageSamples.map(\.growthReduceMs)),
        flowMs: stats.derivedMedian(stageSamples.map(\.flowMs)),
        reintegrateMs: stats.derivedMedian(stageSamples.map(\.reintegrateMs)),
        totalMs: stats.derivedMedian(stageSamples.map(\.totalMs))
    )
}

private func benchmarkBackendArtifact<Result>(
    backend: FlowLeniaComputeBackend,
    stats: RepeatedBenchmarkStats<Result>,
    sampleArtifact: (Result) -> BenchmarkSampleArtifact,
    profileMedian: ([Result], RepeatedBenchmarkStats<Result>) -> BenchmarkSearchProfileArtifact?,
    stageMedian: ([Result], RepeatedBenchmarkStats<Result>) -> BenchmarkStageTimingsArtifact?
) -> BenchmarkBackendArtifact {
    let samples = stats.sample.map(sampleArtifact)
    let simStepValues = samples.compactMap(\.simStepsPerSecond)
    return BenchmarkBackendArtifact(
        backend: backend.displayName,
        throughput: benchmarkSeriesArtifact(stats.throughput),
        durationSeconds: benchmarkSeriesArtifact(stats.duration),
        simStepsPerSecond: simStepValues.isEmpty ? nil : benchmarkSeriesArtifact(summarizeBenchmarkSeries(simStepValues)),
        stageTimingsMedian: stageMedian(stats.sample, stats),
        searchProfileMedian: profileMedian(stats.sample, stats),
        evolutionProfileMedian: nil,
        samples: samples
    )
}

private func benchmarkBackendArtifact(
    backend: FlowLeniaComputeBackend,
    stats: RepeatedBenchmarkStats<EvolutionBenchmarkResult>,
    sampleArtifact: (EvolutionBenchmarkResult) -> BenchmarkSampleArtifact,
    profileMedian: ([EvolutionBenchmarkResult], RepeatedBenchmarkStats<EvolutionBenchmarkResult>) -> BenchmarkEvolutionProfileArtifact?,
    stageMedian: ([EvolutionBenchmarkResult], RepeatedBenchmarkStats<EvolutionBenchmarkResult>) -> BenchmarkStageTimingsArtifact?
) -> BenchmarkBackendArtifact {
    let samples = stats.sample.map(sampleArtifact)
    let simStepValues = samples.compactMap(\.simStepsPerSecond)
    return BenchmarkBackendArtifact(
        backend: backend.displayName,
        throughput: benchmarkSeriesArtifact(stats.throughput),
        durationSeconds: benchmarkSeriesArtifact(stats.duration),
        simStepsPerSecond: simStepValues.isEmpty ? nil : benchmarkSeriesArtifact(summarizeBenchmarkSeries(simStepValues)),
        stageTimingsMedian: stageMedian(stats.sample, stats),
        searchProfileMedian: nil,
        evolutionProfileMedian: profileMedian(stats.sample, stats),
        samples: samples
    )
}

func writeBenchmarkArtifact(
    _ artifact: BenchmarkArtifactFile,
    runID: String,
    output: String,
    dossier: String
) throws -> URL {
    let resolvedOutput = try resolveArtifactPath(output, dossier: dossier)
    let outputURL = URL(fileURLWithPath: resolvedOutput, isDirectory: true)
    try FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)
    let artifactURL = outputURL.appendingPathComponent("\(artifact.mode)-\(runID).json")
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    try encoder.encode(artifact).write(to: artifactURL)
    return artifactURL
}
