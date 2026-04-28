import Foundation

struct SwarmControllerOutputLayout {
    let outputDir: URL
    let overallOutputDir: URL
    let campaignOutputRoot: URL
    let libraryOutputDir: URL
    let exportOutputDir: URL

    init(outputRoot: String) {
        let outputDir = URL(fileURLWithPath: outputRoot)
        self.outputDir = outputDir
        self.overallOutputDir = outputDir.appendingPathComponent("overall")
        self.campaignOutputRoot = outputDir.appendingPathComponent("campaigns")
        self.libraryOutputDir = outputDir.appendingPathComponent("library")
        self.exportOutputDir = outputDir.appendingPathComponent("exports")
    }

    func createDirectories(fileManager: FileManager = .default) throws {
        try fileManager.createDirectory(at: outputDir, withIntermediateDirectories: true)
        try fileManager.createDirectory(at: overallOutputDir, withIntermediateDirectories: true)
        try fileManager.createDirectory(at: campaignOutputRoot, withIntermediateDirectories: true)
        try fileManager.createDirectory(at: libraryOutputDir, withIntermediateDirectories: true)
        try fileManager.createDirectory(at: exportOutputDir, withIntermediateDirectories: true)
    }
}

struct SwarmControllerBootstrap {
    let baseConfig: LeniaBaseConfig
    let searchConfig: ParsedSearchConfig
    let collectionConfig: CollectionConfig
    let seedsPerJob: Int
    let totalSeeds: Int
    let topK: Int
    let jobQueue: [SimulationJob]

    static func load(
        baseConfigPath: String,
        searchConfigPath: String,
        seedsPerJob: Int
    ) throws -> SwarmControllerBootstrap {
        let baseConfig = try JSONDecoder().decode(
            LeniaBaseConfig.self,
            from: Data(contentsOf: URL(fileURLWithPath: baseConfigPath))
        )
        let searchConfig = try JSONDecoder().decode(
            ParsedSearchConfig.self,
            from: Data(contentsOf: URL(fileURLWithPath: searchConfigPath))
        )
        return SwarmControllerBootstrap(
            baseConfig: baseConfig,
            searchConfig: searchConfig,
            seedsPerJob: seedsPerJob
        )
    }

    init(
        baseConfig: LeniaBaseConfig,
        searchConfig: ParsedSearchConfig,
        seedsPerJob: Int
    ) {
        self.baseConfig = baseConfig
        self.searchConfig = searchConfig
        self.collectionConfig = searchConfig.collection ?? CollectionConfig.defaultConfig
        self.seedsPerJob = searchConfig.seedsPerJob ?? seedsPerJob
        self.totalSeeds = searchConfig.count
        self.topK = searchConfig.topK
        self.jobQueue = Self.makeJobQueue(
            baseConfig: baseConfig,
            searchConfig: searchConfig,
            seedsPerJob: self.seedsPerJob
        )
    }

    private static func makeJobQueue(
        baseConfig: LeniaBaseConfig,
        searchConfig: ParsedSearchConfig,
        seedsPerJob: Int
    ) -> [SimulationJob] {
        var currentSeed = searchConfig.seedStart
        var queue: [SimulationJob] = []
        for offset in stride(from: 0, to: searchConfig.count, by: seedsPerJob) {
            let jobCount = min(seedsPerJob, searchConfig.count - offset)
            queue.append(
                SimulationJob(
                    id: "job-\(queue.count)",
                    seedStart: currentSeed,
                    count: jobCount,
                    baseConfig: baseConfig,
                    searchConfig: searchConfig,
                    sweepOverrides: nil
                )
            )
            currentSeed += jobCount * searchConfig.seedStride
        }
        return queue
    }
}
