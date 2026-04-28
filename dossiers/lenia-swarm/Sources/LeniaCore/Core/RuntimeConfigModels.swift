import Foundation

public struct LeniaBaseConfig: Codable, Sendable {
    public let backend: String
    public let profile: RuntimeProfile
    public let grid: GridConfig
    public let channels: Int
    public let connectivity: [[Int]]
    public let flow: FlowConfig
    public let implementation: ImplementationConfig
    public let reintegration: ReintegrationConfig
    public let parameter_embedding: ParameterEmbeddingConfig
    public let chemotaxis: ChemotaxisConfig?
    public let obstacle_field: ObstacleFieldConfig?
    public let food: FoodConfig?
    public let walls: WallsConfig?
    public let environment: EnvironmentConfig?
    public let beam_mutation: BeamMutationConfig?
    public var params: ParamsConfig
    public let `init`: InitConfig
    public let run: RunConfig
    public let interventions: [InterventionConfig]?

    public init(
        backend: String,
        profile: RuntimeProfile,
        grid: GridConfig,
        channels: Int,
        connectivity: [[Int]],
        flow: FlowConfig,
        implementation: ImplementationConfig,
        reintegration: ReintegrationConfig,
        parameter_embedding: ParameterEmbeddingConfig,
        chemotaxis: ChemotaxisConfig?,
        obstacle_field: ObstacleFieldConfig? = nil,
        food: FoodConfig?,
        walls: WallsConfig?,
        environment: EnvironmentConfig? = nil,
        beam_mutation: BeamMutationConfig? = nil,
        params: ParamsConfig,
        `init`: InitConfig,
        run: RunConfig,
        interventions: [InterventionConfig]?
    ) {
        self.backend = backend
        self.profile = profile
        self.grid = grid
        self.channels = channels
        self.connectivity = connectivity
        self.flow = flow
        self.implementation = implementation
        self.reintegration = reintegration
        self.parameter_embedding = parameter_embedding
        self.chemotaxis = chemotaxis
        self.obstacle_field = obstacle_field
        self.food = food
        self.walls = walls
        self.environment = environment
        self.beam_mutation = beam_mutation
        self.params = params
        self.`init` = `init`
        self.run = run
        self.interventions = interventions
    }
}

public struct LeniaModelConfig: Sendable {
    public let grid: GridConfig
    public let channels: Int
    public let connectivity: [[Int]]
    public let flow: FlowConfig
    public let reintegration: ReintegrationConfig
    public let parameterEmbedding: ParameterEmbeddingConfig
    public let params: ParamsConfig
    public let chemotaxis: ChemotaxisConfig?
    public let obstacleField: ObstacleFieldConfig?
    public let food: FoodConfig?
    public let walls: WallsConfig?
    public let environment: EnvironmentConfig?
    public let beamMutation: BeamMutationConfig?
}

public struct LeniaExecutionConfig: Sendable {
    public let backend: String
    public let profile: RuntimeProfile
    public let implementation: ImplementationConfig
    public let run: RunConfig
    public let interventions: [InterventionConfig]
}

public extension LeniaBaseConfig {
    var model: LeniaModelConfig {
        LeniaModelConfig(
            grid: grid,
            channels: channels,
            connectivity: connectivity,
            flow: flow,
            reintegration: reintegration,
            parameterEmbedding: parameter_embedding,
            params: params,
            chemotaxis: chemotaxis,
            obstacleField: obstacle_field,
            food: food,
            walls: walls,
            environment: environment,
            beamMutation: beam_mutation
        )
    }

    var execution: LeniaExecutionConfig {
        LeniaExecutionConfig(
            backend: backend,
            profile: profile,
            implementation: implementation,
            run: run,
            interventions: interventions ?? []
        )
    }

    var initialState: InitConfig {
        self.`init`
    }
}

public struct ResolvedParams: Sendable {
    public let r: [Float]
    public let b: [[Float]]
    public let w: [[Float]]
    public let a: [[Float]]
    public let m: [Float]
    public let s: [Float]
    public let h: [Float]
    public let R: Float
    public let seed: Int

    public init(
        r: [Float],
        b: [[Float]],
        w: [[Float]],
        a: [[Float]],
        m: [Float],
        s: [Float],
        h: [Float],
        R: Float,
        seed: Int
    ) {
        self.r = r
        self.b = b
        self.w = w
        self.a = a
        self.m = m
        self.s = s
        self.h = h
        self.R = R
        self.seed = seed
    }
}

extension ResolvedParams {
    public func toKernelParams() -> KernelParams {
        KernelParams(r: r, b: b, w: w, a: a, m: m, s: s, h: h, R: R)
    }
}

public struct LeniaRuntimeConfig: Sendable {
    public let backend: FlowLeniaComputeBackend
    public let sx: Int
    public let sy: Int
    public let channels: Int
    public let nbK: Int
    public let profile: RuntimeProfile
    public let c0: [Int]
    public let c1: [[Int]]
    public let dt: Float
    public let dd: Int
    public let sigma: Float
    public let n: Int
    public let thetaA: Float
    public let border: String
    public let implementation: ImplementationSettings
    public let params: ResolvedParams
    public let initSeed: Int
    public let patches: [PatchConfig]
    public let aUniform: UniformRange
    public let pUniform: UniformRange?
    public let statePatch: InitStatePatchConfig?
    public let paramPatch: InitStatePatchConfig?
    public let steps: Int
    public let parameterEmbedding: ParameterEmbeddingConfig
    public let chemotaxis: ChemotaxisConfig?
    public let obstacleField: ObstacleFieldConfig?
    public let food: FoodConfig?
    public let walls: WallsConfig?
    public let environment: EnvironmentConfig?
    public let beamMutation: BeamMutationConfig?
    public let interventions: [InterventionConfig]

    public init(
        backend: FlowLeniaComputeBackend,
        sx: Int,
        sy: Int,
        channels: Int,
        nbK: Int,
        profile: RuntimeProfile,
        c0: [Int],
        c1: [[Int]],
        dt: Float,
        dd: Int,
        sigma: Float,
        n: Int,
        thetaA: Float,
        border: String,
        implementation: ImplementationSettings,
        params: ResolvedParams,
        initSeed: Int,
        patches: [PatchConfig],
        aUniform: UniformRange,
        pUniform: UniformRange?,
        statePatch: InitStatePatchConfig? = nil,
        paramPatch: InitStatePatchConfig? = nil,
        steps: Int,
        parameterEmbedding: ParameterEmbeddingConfig,
        chemotaxis: ChemotaxisConfig?,
        obstacleField: ObstacleFieldConfig? = nil,
        food: FoodConfig?,
        walls: WallsConfig?,
        environment: EnvironmentConfig? = nil,
        beamMutation: BeamMutationConfig? = nil,
        interventions: [InterventionConfig]
    ) {
        self.backend = backend
        self.sx = sx
        self.sy = sy
        self.channels = channels
        self.nbK = nbK
        self.c0 = c0
        self.c1 = c1
        self.profile = profile
        self.dt = dt
        self.dd = dd
        self.sigma = sigma
        self.n = n
        self.thetaA = thetaA
        self.border = border
        self.implementation = implementation
        self.params = params
        self.initSeed = initSeed
        self.patches = patches
        self.aUniform = aUniform
        self.pUniform = pUniform
        self.statePatch = statePatch
        self.paramPatch = paramPatch
        self.steps = steps
        self.parameterEmbedding = parameterEmbedding
        self.chemotaxis = chemotaxis
        self.obstacleField = obstacleField
        self.food = food
        self.walls = walls
        self.environment = environment
        self.beamMutation = beamMutation
        self.interventions = interventions
    }
}
