import Foundation
import LeniaCore

struct LabWorldRequest {
    let entry: StudioCompareEntry
    let draft: LabWorldDraft?

    func runtimeConfig(backend: FlowSandboxBackend) -> LeniaRuntimeConfig? {
        draft?.runtimeConfig(overridingBackend: backend)
    }
}

struct LabKernelRoute: Identifiable {
    let id: Int
    var source: Int
    var target: Int
}

enum LabWorldSelection: Equatable {
    case preset(String)
    case stamp(String)
    case track1Config(String)

    var taskKey: String {
        switch self {
        case .preset(let id):
            "preset:\(id)"
        case .stamp(let id):
            "stamp:\(id)"
        case .track1Config(let path):
            "track1:\(path)"
        }
    }
}

struct LabMissionPreset: Identifiable {
    let id: String
    let name: String
    let subtitle: String
    let detail: String
    let entry: StudioCompareEntry
    let defaultDraft: LabWorldDraft?
    let channels: Int
    let parameterFields: Int
    let kernelCount: Int
    let fixedGrid: Int?
}

struct LabWorldDraft {
    let presetID: String
    let basisName: String
    let sourceConfigPath: String

    private(set) var runtimeConfigValue: LeniaRuntimeConfig
    private(set) var connectivityMatrixValue: [[Int]]

    init(
        presetID: String,
        basisName: String,
        sourceConfigPath: String,
        runtimeConfig: LeniaRuntimeConfig
    ) {
        self.presetID = presetID
        self.basisName = basisName
        self.sourceConfigPath = sourceConfigPath
        self.runtimeConfigValue = runtimeConfig
        self.connectivityMatrixValue = labConnectivityMatrix(from: runtimeConfig)
    }

    var gridSize: Int { runtimeConfigValue.sx }
    var channels: Int { runtimeConfigValue.channels }
    var channelCount: Int { channels }
    var kernelCount: Int { runtimeConfigValue.nbK }
    var parameterFieldMode: FlowLeniaParameterFieldMode {
        FlowLeniaParameterFieldMode.fromEmbeddingEnabled(runtimeConfigValue.parameterEmbedding.enabled)
    }
    var parameterFieldCount: Int { runtimeConfigValue.parameterEmbedding.enabled ? runtimeConfigValue.nbK : 0 }
    var parameterEmbeddingEnabled: Bool { runtimeConfigValue.parameterEmbedding.enabled }
    var parameterMixMode: String { runtimeConfigValue.parameterEmbedding.mix }
    var foodEnabled: Bool { runtimeConfigValue.food?.enabled == true }
    var foodChannelIndex: Int { runtimeConfigValue.food?.channel_index ?? min(max(0, channels - 1), 1) }
    var border: String { runtimeConfigValue.border }
    var connectivityMatrix: [[Int]] { connectivityMatrixValue }
    var initSeed: Int { runtimeConfigValue.initSeed }
    var paramsSeed: Int { runtimeConfigValue.params.seed }
    var patchSize: Int { runtimeConfigValue.patches.first?.size ?? max(12, min(gridSize / 5, 48)) }
    var usesRandomKernelBank: Bool { false }
    var sourceSummary: String {
        guard !sourceConfigPath.isEmpty else {
            return "\(basisName) · synthesized contract"
        }
        return "\(basisName) · \(URL(fileURLWithPath: sourceConfigPath).lastPathComponent)"
    }
    var connectivitySummary: String {
        let edges = connectivityMatrixValue.enumerated().flatMap { source, row in
            row.enumerated().compactMap { target, count -> String? in
                guard count > 0 else { return nil }
                return "c\(source) -> c\(target) × \(count)"
            }
        }
        return edges.isEmpty ? "No active routes" : edges.joined(separator: ", ")
    }
    var kernelRoutes: [LabKernelRoute] {
        var routes: [LabKernelRoute] = []
        var routeID = 0
        for source in connectivityMatrixValue.indices {
            for target in connectivityMatrixValue[source].indices {
                let count = connectivityMatrixValue[source][target]
                guard count > 0 else { continue }
                for _ in 0..<count {
                    routes.append(
                        LabKernelRoute(id: routeID, source: source, target: target)
                    )
                    routeID += 1
                }
            }
        }
        if routes.isEmpty {
            return [LabKernelRoute(id: 0, source: 0, target: 0)]
        }
        return routes
    }

    func runtimeConfig(overridingBackend backend: FlowSandboxBackend) -> LeniaRuntimeConfig {
        labCopyRuntimeConfig(
            runtimeConfigValue,
            backend: labComputeBackend(for: backend)
        )
    }

    mutating func setGridSize(_ size: Int) {
        let clamped = max(32, size)
        guard clamped != gridSize else { return }
        let recenteredStatePatch = runtimeConfigValue.statePatch.map {
            labCenteredStatePatch($0, gridSize: clamped)
        }
        runtimeConfigValue = labCopyRuntimeConfig(
            runtimeConfigValue,
            sx: clamped,
            sy: clamped,
            patches: labScaledPatches(runtimeConfigValue.patches, from: gridSize, to: clamped),
            statePatch: recenteredStatePatch
        )
    }

    mutating func setChannels(_ nextChannelCount: Int) {
        let clamped = max(1, min(4, nextChannelCount))
        guard clamped != channels else { return }
        let resized = labResizedConnectivityMatrix(connectivityMatrixValue, to: clamped)
        applyConnectivityMatrix(
            resized,
            food: updatedFoodConfig(
                for: resized,
                existing: runtimeConfigValue.food,
                enabled: runtimeConfigValue.food?.enabled ?? false
            )
        )
    }

    mutating func setEdgeCount(source: Int, target: Int, count: Int) {
        guard source >= 0,
              target >= 0,
              source < connectivityMatrixValue.count,
              target < connectivityMatrixValue.count else {
            return
        }
        var matrix = connectivityMatrixValue
        matrix[source][target] = max(0, min(8, count))
        if labKernelTotal(matrix) == 0 {
            matrix[0][0] = 1
        }
        applyConnectivityMatrix(matrix)
    }

    mutating func setParameterEmbeddingEnabled(_ enabled: Bool) {
        let mix = runtimeConfigValue.parameterEmbedding.mix
        runtimeConfigValue = labCopyRuntimeConfig(
            runtimeConfigValue,
            overridePUniform: true,
            pUniform: enabled ? (runtimeConfigValue.pUniform ?? UniformRange(low: 0, high: 1)) : nil,
            parameterEmbedding: ParameterEmbeddingConfig(
                enabled: enabled,
                mix: mix,
                mix_seed: enabled ? labResolvedMixSeed(for: mix, current: runtimeConfigValue.parameterEmbedding.mix_seed) : nil
            )
        )
    }

    mutating func setParameterMixMode(_ mode: String) {
        let enabled = runtimeConfigValue.parameterEmbedding.enabled
        runtimeConfigValue = labCopyRuntimeConfig(
            runtimeConfigValue,
            overridePUniform: true,
            pUniform: enabled ? (runtimeConfigValue.pUniform ?? UniformRange(low: 0, high: 1)) : runtimeConfigValue.pUniform,
            parameterEmbedding: ParameterEmbeddingConfig(
                enabled: enabled,
                mix: mode,
                mix_seed: enabled ? labResolvedMixSeed(for: mode, current: runtimeConfigValue.parameterEmbedding.mix_seed) : nil
            )
        )
    }

    mutating func setFoodEnabled(_ enabled: Bool) {
        runtimeConfigValue = labCopyRuntimeConfig(
            runtimeConfigValue,
            overrideFood: true,
            food: updatedFoodConfig(
                for: connectivityMatrixValue,
                existing: runtimeConfigValue.food,
                enabled: enabled
            )
        )
    }

    mutating func setFoodChannelIndex(_ channelIndex: Int) {
        runtimeConfigValue = labCopyRuntimeConfig(
            runtimeConfigValue,
            overrideFood: true,
            food: updatedFoodConfig(
                for: connectivityMatrixValue,
                existing: runtimeConfigValue.food,
                enabled: true,
                forcedChannel: channelIndex
            )
        )
    }

    mutating func setBorder(_ nextBorder: String) {
        let normalized = nextBorder == "torus" ? "torus" : "wall"
        guard normalized != runtimeConfigValue.border else { return }
        runtimeConfigValue = labCopyRuntimeConfig(
            runtimeConfigValue,
            border: normalized
        )
    }

    mutating func setInitSeed(_ seed: Int) {
        let clamped = max(0, seed)
        guard clamped != runtimeConfigValue.initSeed else { return }
        runtimeConfigValue = labCopyRuntimeConfig(
            runtimeConfigValue,
            initSeed: clamped
        )
    }

    mutating func setPatchSize(_ size: Int) {
        let clamped = max(8, min(gridSize, size))
        let centers = runtimeConfigValue.patches.isEmpty
            ? [[gridSize / 2, gridSize / 2]]
            : runtimeConfigValue.patches.map(\.center)
        runtimeConfigValue = labCopyRuntimeConfig(
            runtimeConfigValue,
            patches: centers.map { center in
                PatchConfig(center: center, size: clamped)
            }
        )
    }

    private mutating func applyConnectivityMatrix(
        _ matrix: [[Int]],
        food: FoodConfig? = nil
    ) {
        let total = max(1, labKernelTotal(matrix))
        let adjacency = connFromMatrix(matrix)
        runtimeConfigValue = labCopyRuntimeConfig(
            runtimeConfigValue,
            channels: matrix.count,
            nbK: total,
            c0: adjacency.c0,
            c1: adjacency.c1,
            params: labAdjustedParams(runtimeConfigValue.params, targetKernelCount: total),
            overrideFood: true,
            food: food ?? updatedFoodConfig(
                for: matrix,
                existing: runtimeConfigValue.food,
                enabled: runtimeConfigValue.food?.enabled ?? false
            )
        )
        connectivityMatrixValue = matrix
    }

    private func updatedFoodConfig(
        for matrix: [[Int]],
        existing: FoodConfig?,
        enabled: Bool,
        forcedChannel: Int? = nil
    ) -> FoodConfig? {
        guard enabled else {
            return nil
        }
        guard let current = existing else {
            let channel = min(max(0, forcedChannel ?? 1), max(0, matrix.count - 1))
            return FoodConfig(
                enabled: true,
                channel_index: channel,
                mode: "full",
                uniform: UniformRange(low: 0.0, high: 0.5),
                patches: nil,
                decay_rate: 0.002,
                digest_rate: 0.01,
                include_in_mass: false
            )
        }
        let channel = min(max(0, forcedChannel ?? current.channel_index), max(0, matrix.count - 1))
        return FoodConfig(
            enabled: true,
            channel_index: channel,
            mode: current.mode,
            uniform: current.uniform,
            patches: current.patches,
            decay_rate: current.decay_rate,
            digest_rate: current.digest_rate,
            include_in_mass: current.include_in_mass
        )
    }
}

func buildLabMissionPresets() -> [LabMissionPreset] {
    let orbium = orbiumStarterEntry()
    let orbiumDraft: LabWorldDraft
    do {
        orbiumDraft = try makeLabWorldDraft(for: orbium, gridSize: LabGridPreset.compact128.rawValue)
    } catch {
        fatalError("Failed to synthesize Orbium lab draft: \(error.localizedDescription)")
    }
    return [
        LabMissionPreset(
            id: "orbium-sandbox",
            name: "Orbium Seed",
            subtitle: "Editable single-kernel sandbox",
            detail: "Fastest lab contract. One matter lane, one kernel, and direct brush edits for quick local experiments.",
            entry: orbium,
            defaultDraft: orbiumDraft,
            channels: orbiumDraft.channels,
            parameterFields: orbiumDraft.parameterFieldCount,
            kernelCount: orbiumDraft.kernelCount,
            fixedGrid: nil
        ),
        bundleLabMissionPreset(
            id: "paper-1c",
            resourceName: "paper_base_1c_128",
            name: "Paper 1C",
            subtitle: "Canonical single-channel base",
            detail: "One matter lane on the paper runtime. Use this when you want the simplest canonical world without parameter transport."
        ),
        bundleLabMissionPreset(
            id: "paper-2c",
            resourceName: "paper_base_2c_128",
            name: "Paper 2C",
            subtitle: "Coupled two-channel base",
            detail: "Cross-coupled canonical paper world with multiple kernels. This is the cleanest default when you want visibly multi-channel dynamics."
        ),
        bundleLabMissionPreset(
            id: "paper-pe-1c",
            resourceName: "paper_base_pe_1c_128",
            name: "Embedded 1C",
            subtitle: "Single matter lane with parameter transport",
            detail: "Canonical one-channel world with parameter embedding enabled, so the lab exposes transported kernel fields without adding extra matter channels."
        ),
        bundleLabMissionPreset(
            id: "eco-food-2c",
            resourceName: "paper_embed_food_2c_128",
            name: "Ecology 2C",
            subtitle: "Food-rich two-channel ecology",
            detail: "Experimental two-channel world with food dynamics and parameter embedding. Use this when you want the fullest canonical contract the lab can display today."
        ),
    ]
}

func makeLabWorldDraft(for entry: StudioCompareEntry, gridSize: Int) throws -> LabWorldDraft {
    if let replayReference = entry.replayReference {
        let data = try Data(contentsOf: URL(fileURLWithPath: replayReference.baseConfigPath))
        let baseRuntimeConfig = try loadRuntimeConfig(from: data)
        let runtimeConfig = try studioRuntimeConfig(
            base: baseRuntimeConfig,
            creature: entry.creature,
            savedCreature: entry.savedCreature
        )
        return LabWorldDraft(
            presetID: entry.id,
            basisName: entry.name,
            sourceConfigPath: replayReference.baseConfigPath,
            runtimeConfig: runtimeConfig
        )
    }

    let runtimeConfig = try studioFallbackRuntimeConfig(
        creature: entry.creature,
        savedCreature: entry.savedCreature,
        gridSize: gridSize
    )
    return LabWorldDraft(
        presetID: entry.id,
        basisName: entry.name,
        sourceConfigPath: "",
        runtimeConfig: runtimeConfig
    )
}

func studioRuntimeConfig(
    base runtimeConfig: LeniaRuntimeConfig,
    creature: LeniaCreature,
    savedCreature: SavedCreature?
) throws -> LeniaRuntimeConfig {
    let selectedParams = savedCreature.map(labResolvedParams(from:)) ?? creature.params
    try labValidateParams(selectedParams, kernelCount: runtimeConfig.nbK, label: "selected creature")

    guard let savedCreature else {
        return labCopyRuntimeConfig(
            runtimeConfig,
            params: selectedParams,
            initSeed: creature.seed
        )
    }

    let initial = savedCreature.initialCondition
    let statePatch = try initial.state_patch.map {
        try labPreparedStatePatch(
            $0,
            sx: runtimeConfig.sx,
            sy: runtimeConfig.sy,
            channels: runtimeConfig.channels,
            label: "init.state_patch"
        )
    }
    let paramPatch = try initial.p_state_patch.map {
        try labPreparedStatePatch(
            $0,
            sx: runtimeConfig.sx,
            sy: runtimeConfig.sy,
            channels: runtimeConfig.nbK,
            label: "init.p_state_patch"
        )
    }

    if !runtimeConfig.parameterEmbedding.enabled,
       initial.p_uniform != nil || paramPatch != nil {
        throw ConfigError.invalidConfig(
            "Selected creature has parameter-field initialization, but replay base has parameter_embedding disabled."
        )
    }
    if paramPatch != nil, initial.p_uniform != nil {
        throw ConfigError.invalidConfig("init.p_state_patch cannot be combined with init.p_uniform.")
    }

    let usesExplicitState = statePatch != nil
    let patches = usesExplicitState && !runtimeConfig.parameterEmbedding.enabled
        ? []
        : try labValidatedPatches(initial.patches, sx: runtimeConfig.sx, sy: runtimeConfig.sy, label: "init.patches")
    let aUniform = usesExplicitState ? UniformRange(low: 0, high: 0) : initial.a_uniform
    let resolvedParamPatch: InitStatePatchConfig?
    let resolvedPUniform: UniformRange?
    if runtimeConfig.parameterEmbedding.enabled {
        resolvedParamPatch = paramPatch
        resolvedPUniform = paramPatch == nil ? (initial.p_uniform ?? runtimeConfig.pUniform) : nil
        if resolvedParamPatch == nil, resolvedPUniform == nil {
            throw ConfigError.invalidConfig(
                "parameter_embedding.enabled requires init.p_uniform or init.p_state_patch."
            )
        }
    } else {
        resolvedParamPatch = nil
        resolvedPUniform = nil
    }

    return labCopyRuntimeConfig(
        runtimeConfig,
        params: selectedParams,
        initSeed: initial.seed,
        patches: patches,
        aUniform: aUniform,
        overrideStatePatch: true,
        statePatch: statePatch,
        overridePUniform: true,
        pUniform: resolvedPUniform,
        overrideParamPatch: true,
        paramPatch: resolvedParamPatch
    )
}

func studioFallbackRuntimeConfig(
    creature: LeniaCreature,
    savedCreature: SavedCreature?,
    gridSize: Int
) throws -> LeniaRuntimeConfig {
    let selectedParams = savedCreature.map(labResolvedParams(from:)) ?? creature.params
    let kernelCount = max(1, selectedParams.r.count)
    try labValidateParams(selectedParams, kernelCount: kernelCount, label: "selected creature")

    let savedInitial = savedCreature?.initialCondition
    let savedStatePatch = savedInitial?.state_patch
    let patchRequiredGrid = savedInitial.map { labRequiredGridSize(for: $0.patches) } ?? 0
    let resolvedGrid = max(
        32,
        gridSize,
        savedStatePatch?.width ?? 0,
        savedStatePatch?.height ?? 0,
        patchRequiredGrid
    )
    let channels = max(1, savedStatePatch?.channels ?? 1)
    let connectivity = labFallbackConnectivity(channels: channels, kernelCount: kernelCount)
    let adjacency = connFromMatrix(connectivity)
    let statePatch: InitStatePatchConfig?
    let patches: [PatchConfig]
    let aUniform: UniformRange

    if let savedStatePatch {
        try labValidateStatePatchShape(
            savedStatePatch,
            sx: resolvedGrid,
            sy: resolvedGrid,
            channels: channels,
            label: "init.state_patch"
        )
        let recentered = labRecenteredStatePatch(savedStatePatch, sx: resolvedGrid, sy: resolvedGrid)
        guard labStatePatchFits(recentered, sx: resolvedGrid, sy: resolvedGrid) else {
            throw ConfigError.invalidConfig(
                "init.state_patch is out of bounds for grid \(resolvedGrid)x\(resolvedGrid)."
            )
        }
        statePatch = recentered
        patches = []
        aUniform = UniformRange(low: 0, high: 0)
    } else if let savedInitial, !savedInitial.patches.isEmpty {
        statePatch = nil
        patches = try labValidatedPatches(
            savedInitial.patches,
            sx: resolvedGrid,
            sy: resolvedGrid,
            label: "init.patches"
        )
        aUniform = savedInitial.a_uniform
    } else {
        statePatch = labWarmInitialStatePatch(
            for: creature,
            savedCreature: savedCreature,
            gridSize: resolvedGrid
        )
        patches = []
        aUniform = UniformRange(low: 0, high: 0)
    }

    return LeniaRuntimeConfig(
        backend: .metalFull,
        sx: resolvedGrid,
        sy: resolvedGrid,
        channels: channels,
        nbK: kernelCount,
        profile: .paper,
        c0: adjacency.c0,
        c1: adjacency.c1,
        dt: 0.2,
        dd: 5,
        sigma: 0.65,
        n: 2,
        thetaA: 2.0,
        border: "torus",
        implementation: ImplementationSettings(
            mode: "flowlenia_2022_paper_equations",
            border: "torus",
            gradientBoundary: "periodic",
            alphaMode: "mass",
            kernelProfile: "flowlenia_2022_paper_equations",
            flowClip: "none"
        ),
        params: selectedParams,
        initSeed: savedInitial?.seed ?? creature.seed,
        patches: patches,
        aUniform: aUniform,
        pUniform: nil,
        statePatch: statePatch,
        steps: 4_000,
        parameterEmbedding: ParameterEmbeddingConfig(enabled: false, mix: "avg", mix_seed: nil),
        chemotaxis: nil,
        food: nil,
        walls: nil,
        environment: nil,
        beamMutation: nil,
        interventions: []
    )
}

private func labResolvedParams(from creature: SavedCreature) -> ResolvedParams {
    ResolvedParams(
        r: creature.genotype.r,
        b: creature.genotype.b,
        w: creature.genotype.w,
        a: creature.genotype.a,
        m: creature.genotype.m,
        s: creature.genotype.s,
        h: creature.genotype.h,
        R: creature.genotype.R,
        seed: creature.initialCondition.seed
    )
}

private func labWarmInitialStatePatch(
    for creature: LeniaCreature,
    savedCreature: SavedCreature?,
    gridSize: Int
) -> InitStatePatchConfig {
    let stamp = buildWarmCreatureStamp(
        id: savedCreature?.id ?? creature.id,
        name: savedCreature?.name ?? creature.sourceNode,
        params: savedCreature.map(labResolvedParams(from:)) ?? creature.params,
        seed: savedCreature?.initialCondition.seed ?? creature.seed,
        warmupSteps: 80,
        warmupGridSize: gridSize,
        cropThreshold: 0.01,
        padding: 4
    )
    return labInitialStatePatch(from: stamp, gridSize: gridSize)
}

private func labInitialStatePatch(from stamp: CreatureStamp, gridSize: Int) -> InitStatePatchConfig {
    InitStatePatchConfig(
        center: [gridSize / 2, gridSize / 2],
        width: stamp.width,
        height: stamp.height,
        channels: 1,
        values: stamp.mass
    )
}

private func labCenteredStatePatch(_ statePatch: InitStatePatchConfig, gridSize: Int) -> InitStatePatchConfig {
    labRecenteredStatePatch(statePatch, sx: gridSize, sy: gridSize)
}

private func labRecenteredStatePatch(_ statePatch: InitStatePatchConfig, sx: Int, sy: Int) -> InitStatePatchConfig {
    InitStatePatchConfig(
        center: [sx / 2, sy / 2],
        width: statePatch.width,
        height: statePatch.height,
        channels: statePatch.channels,
        data: statePatch.data
    )
}

private func labPreparedStatePatch(
    _ statePatch: InitStatePatchConfig,
    sx: Int,
    sy: Int,
    channels: Int,
    label: String
) throws -> InitStatePatchConfig {
    try labValidateStatePatchShape(statePatch, sx: sx, sy: sy, channels: channels, label: label)
    if labStatePatchFits(statePatch, sx: sx, sy: sy) {
        return statePatch
    }
    let recentered = labRecenteredStatePatch(statePatch, sx: sx, sy: sy)
    guard labStatePatchFits(recentered, sx: sx, sy: sy) else {
        throw ConfigError.invalidConfig("\(label) is out of bounds for grid \(sx)x\(sy).")
    }
    return recentered
}

private func labValidateStatePatchShape(
    _ statePatch: InitStatePatchConfig,
    sx: Int,
    sy: Int,
    channels: Int,
    label: String
) throws {
    guard statePatch.center.count == 2 else {
        throw ConfigError.invalidConfig("\(label).center must have two coordinates.")
    }
    guard statePatch.width > 0, statePatch.height > 0 else {
        throw ConfigError.invalidConfig("\(label).width and height must be > 0.")
    }
    guard statePatch.width <= sx, statePatch.height <= sy else {
        throw ConfigError.invalidConfig("\(label) is larger than grid \(sx)x\(sy).")
    }
    guard statePatch.channels == channels else {
        throw ConfigError.invalidConfig("\(label).channels must equal \(channels).")
    }
    guard statePatch.encoding == "f32le" else {
        throw ConfigError.invalidConfig("\(label).encoding must be \"f32le\".")
    }
    let expectedBytes = statePatch.width * statePatch.height * statePatch.channels * MemoryLayout<Float>.size
    guard statePatch.data.count == expectedBytes else {
        throw ConfigError.invalidConfig("\(label).data must contain exactly \(expectedBytes) bytes.")
    }
}

private func labStatePatchFits(_ statePatch: InitStatePatchConfig, sx: Int, sy: Int) -> Bool {
    guard statePatch.center.count == 2 else {
        return false
    }
    let cx = statePatch.center[0]
    let cy = statePatch.center[1]
    let halfWidth = statePatch.width / 2
    let halfHeight = statePatch.height / 2
    let x0 = cx - halfWidth
    let x1 = cx + (statePatch.width - halfWidth)
    let y0 = cy - halfHeight
    let y1 = cy + (statePatch.height - halfHeight)
    return x0 >= 0 && y0 >= 0 && x1 <= sx && y1 <= sy
}

private func labValidatedPatches(
    _ patches: [PatchConfig],
    sx: Int,
    sy: Int,
    label: String
) throws -> [PatchConfig] {
    for (index, patch) in patches.enumerated() {
        guard patch.center.count == 2 else {
            throw ConfigError.invalidConfig("\(label)[\(index)].center must have two coordinates.")
        }
        guard patch.size > 0 else {
            throw ConfigError.invalidConfig("\(label)[\(index)].size must be > 0.")
        }
        let half = patch.size / 2
        let x0 = patch.center[0] - half
        let x1 = patch.center[0] + (patch.size - half)
        let y0 = patch.center[1] - half
        let y1 = patch.center[1] + (patch.size - half)
        guard x0 >= 0, y0 >= 0, x1 <= sx, y1 <= sy else {
            throw ConfigError.invalidConfig("\(label)[\(index)] is out of bounds for grid \(sx)x\(sy).")
        }
    }
    return patches
}

private func labRequiredGridSize(for patches: [PatchConfig]) -> Int {
    patches.reduce(0) { required, patch in
        guard patch.center.count == 2 else {
            return required
        }
        let half = patch.size / 2
        let x1 = patch.center[0] + (patch.size - half)
        let y1 = patch.center[1] + (patch.size - half)
        return max(required, x1, y1)
    }
}

private func labFallbackConnectivity(channels: Int, kernelCount: Int) -> [[Int]] {
    let resolvedChannels = max(1, channels)
    var matrix = Array(
        repeating: Array(repeating: 0, count: resolvedChannels),
        count: resolvedChannels
    )
    for kernel in 0..<max(1, kernelCount) {
        let channel = kernel % resolvedChannels
        matrix[channel][channel] += 1
    }
    return matrix
}

private func labValidateParams(
    _ params: ResolvedParams,
    kernelCount: Int,
    label: String
) throws {
    guard params.r.count == kernelCount,
          params.m.count == kernelCount,
          params.s.count == kernelCount,
          params.h.count == kernelCount,
          params.b.count == kernelCount,
          params.w.count == kernelCount,
          params.a.count == kernelCount else {
        throw ConfigError.invalidConfig(
            "\(label) has \(params.r.count) kernels but runtime contract expects \(kernelCount)."
        )
    }
}

private func bundleLabMissionPreset(
    id: String,
    resourceName: String,
    name: String,
    subtitle: String,
    detail: String
) -> LabMissionPreset {
    guard let resourceURL = Bundle.module.url(forResource: resourceName, withExtension: "json", subdirectory: "Presets")
        ?? Bundle.module.url(forResource: resourceName, withExtension: "json")
    else {
        fatalError("Missing lab preset resource: \(resourceName).json")
    }
    do {
        let configData = try Data(contentsOf: resourceURL)
        let runtimeConfig = try loadRuntimeConfig(from: configData)
        let entry = StudioCompareEntry.live(
            creature: LeniaCreature(
                seed: runtimeConfig.initSeed,
                score: 0,
                params: runtimeConfig.params,
                sourceNode: "Preset"
            ),
            name: name,
            subtitle: subtitle,
            replayReference: StudioReplayReference(
                baseConfigPath: resourceURL.path,
                runtimeFamily: "lab-preset"
            )
        )
        let draft = LabWorldDraft(
            presetID: id,
            basisName: name,
            sourceConfigPath: resourceURL.path,
            runtimeConfig: runtimeConfig
        )
        return LabMissionPreset(
            id: id,
            name: name,
            subtitle: subtitle,
            detail: detail,
            entry: entry,
            defaultDraft: draft,
            channels: draft.channels,
            parameterFields: draft.parameterFieldCount,
            kernelCount: draft.kernelCount,
            fixedGrid: draft.gridSize
        )
    } catch {
        fatalError("Failed to load bundled lab preset \(resourceName): \(error.localizedDescription)")
    }
}

func orbiumStarterEntry() -> StudioCompareEntry {
    let params = ResolvedParams(
        r: [0.5],
        b: [[1.0, 0.0, 0.0]],
        w: [[0.2, 0.2, 0.2]],
        a: [[0.5, 0.5, 0.5]],
        m: [0.15],
        s: [0.017],
        h: [0.1],
        R: 13.0,
        seed: 0
    )
    let creature = LeniaCreature(seed: 0, score: 0.0, params: params, sourceNode: "Preset")
    return .live(creature: creature, name: "Orbium", subtitle: "Sandbox seed")
}

private func labComputeBackend(for backend: FlowSandboxBackend) -> FlowLeniaComputeBackend {
    switch backend {
    case .mlx:
        return .mlx
    case .metalFull:
        return .metalFull
    }
}

private func labConnectivityMatrix(from runtimeConfig: LeniaRuntimeConfig) -> [[Int]] {
    var matrix = Array(repeating: Array(repeating: 0, count: runtimeConfig.channels), count: runtimeConfig.channels)
    for target in runtimeConfig.c1.indices {
        for kernel in runtimeConfig.c1[target] {
            guard kernel >= 0, kernel < runtimeConfig.c0.count else { continue }
            let source = runtimeConfig.c0[kernel]
            matrix[source][target] += 1
        }
    }
    return matrix
}

private func labResizedConnectivityMatrix(_ matrix: [[Int]], to channelCount: Int) -> [[Int]] {
    var resized = Array(repeating: Array(repeating: 0, count: channelCount), count: channelCount)
    let overlap = min(channelCount, matrix.count)
    for source in 0..<overlap {
        for target in 0..<overlap {
            resized[source][target] = matrix[source][target]
        }
    }
    if labKernelTotal(resized) == 0 {
        resized[0][0] = 1
    }
    return resized
}

private func labKernelTotal(_ matrix: [[Int]]) -> Int {
    matrix.flatMap(\.self).reduce(0, +)
}

private func labAdjustedParams(_ params: ResolvedParams, targetKernelCount: Int) -> ResolvedParams {
    let count = max(1, targetKernelCount)

    func resized(_ values: [Float], defaultValue: Float) -> [Float] {
        guard let last = values.last else {
            return Array(repeating: defaultValue, count: count)
        }
        return (0..<count).map { index in
            index < values.count ? values[index] : last
        }
    }

    func resizedVectors(_ values: [[Float]], defaultValue: [Float]) -> [[Float]] {
        guard let last = values.last else {
            return Array(repeating: defaultValue, count: count)
        }
        return (0..<count).map { index in
            index < values.count ? values[index] : last
        }
    }

    return ResolvedParams(
        r: resized(params.r, defaultValue: 0.5),
        b: resizedVectors(params.b, defaultValue: [1, 0, 0]),
        w: resizedVectors(params.w, defaultValue: [0.2, 0.2, 0.2]),
        a: resizedVectors(params.a, defaultValue: [0.5, 0.5, 0.5]),
        m: resized(params.m, defaultValue: 0.15),
        s: resized(params.s, defaultValue: 0.017),
        h: resized(params.h, defaultValue: 0.1),
        R: params.R,
        seed: params.seed
    )
}

private func labScaledPatches(_ patches: [PatchConfig], from sourceSize: Int, to targetSize: Int) -> [PatchConfig] {
    guard sourceSize != targetSize, sourceSize > 0, targetSize > 0 else {
        return patches
    }
    let scale = Float(targetSize) / Float(sourceSize)
    return patches.map { patch in
        PatchConfig(
            center: [
                min(targetSize - 1, max(0, Int((Float(patch.center[0]) * scale).rounded()))),
                min(targetSize - 1, max(0, Int((Float(patch.center[1]) * scale).rounded())))
            ],
            size: min(targetSize, max(1, Int((Float(patch.size) * scale).rounded())))
        )
    }
}

private func labResolvedMixSeed(for mode: String, current: Int?) -> Int? {
    let stochasticModes: Set<String> = ["stoch", "softmax", "stoch_gene_wise", "energy"]
    return stochasticModes.contains(mode) ? (current ?? 42) : nil
}

private func labCopyRuntimeConfig(
    _ runtimeConfig: LeniaRuntimeConfig,
    backend: FlowLeniaComputeBackend? = nil,
    sx: Int? = nil,
    sy: Int? = nil,
    channels: Int? = nil,
    nbK: Int? = nil,
    c0: [Int]? = nil,
    c1: [[Int]]? = nil,
    border: String? = nil,
    params: ResolvedParams? = nil,
    initSeed: Int? = nil,
    patches: [PatchConfig]? = nil,
    aUniform: UniformRange? = nil,
    overrideStatePatch: Bool = false,
    statePatch: InitStatePatchConfig? = nil,
    overridePUniform: Bool = false,
    pUniform: UniformRange? = nil,
    overrideParamPatch: Bool = false,
    paramPatch: InitStatePatchConfig? = nil,
    parameterEmbedding: ParameterEmbeddingConfig? = nil,
    overrideFood: Bool = false,
    food: FoodConfig? = nil
) -> LeniaRuntimeConfig {
    let resolvedBorder = border ?? runtimeConfig.border
    return LeniaRuntimeConfig(
        backend: backend ?? runtimeConfig.backend,
        sx: sx ?? runtimeConfig.sx,
        sy: sy ?? runtimeConfig.sy,
        channels: channels ?? runtimeConfig.channels,
        nbK: nbK ?? runtimeConfig.nbK,
        profile: runtimeConfig.profile,
        c0: c0 ?? runtimeConfig.c0,
        c1: c1 ?? runtimeConfig.c1,
        dt: runtimeConfig.dt,
        dd: runtimeConfig.dd,
        sigma: runtimeConfig.sigma,
        n: runtimeConfig.n,
        thetaA: runtimeConfig.thetaA,
        border: resolvedBorder,
        implementation: ImplementationSettings(
            mode: runtimeConfig.implementation.mode,
            border: resolvedBorder,
            gradientBoundary: resolvedBorder == "torus" ? "periodic" : "zero_pad",
            alphaMode: runtimeConfig.implementation.alphaMode,
            kernelProfile: runtimeConfig.implementation.kernelProfile,
            flowClip: runtimeConfig.implementation.flowClip
        ),
        params: params ?? runtimeConfig.params,
        initSeed: initSeed ?? runtimeConfig.initSeed,
        patches: patches ?? runtimeConfig.patches,
        aUniform: aUniform ?? runtimeConfig.aUniform,
        pUniform: overridePUniform ? pUniform : runtimeConfig.pUniform,
        statePatch: overrideStatePatch ? statePatch : (statePatch ?? runtimeConfig.statePatch),
        paramPatch: overrideParamPatch ? paramPatch : (paramPatch ?? runtimeConfig.paramPatch),
        steps: runtimeConfig.steps,
        parameterEmbedding: parameterEmbedding ?? runtimeConfig.parameterEmbedding,
        chemotaxis: runtimeConfig.chemotaxis,
        obstacleField: runtimeConfig.obstacleField,
        food: overrideFood ? food : runtimeConfig.food,
        walls: runtimeConfig.walls,
        environment: runtimeConfig.environment,
        beamMutation: runtimeConfig.beamMutation,
        interventions: runtimeConfig.interventions
    )
}
