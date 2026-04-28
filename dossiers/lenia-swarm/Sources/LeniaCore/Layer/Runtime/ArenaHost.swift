import Distributed
import DistributedCluster
import Foundation
import MLX
import MLXRandom
import Logging

public distributed actor ArenaHost {
    public typealias ActorSystem = ClusterSystem

    private let config: ArenaConfig
    private var participants: [String: (LeniaWorker, SavedCreature)] = [:]
    private var isRunning = false
    private let logger: Logger

    private var engine: FlowLeniaParamsBatched?
    private var stateA: MLXArray?
    private var stateP: MLXArray?
    private var batchedConfig: BatchedConfig?
    private var step: Int = 0

    public init(system: ClusterSystem, config: ArenaConfig) {
        self.actorSystem = system
        self.config = config
        self.logger = LeniaLogging.makeLogger(
            label: "ArenaHost",
            extraMetadata: ["arena_id": .string(config.id.uuidString)]
        )
    }

    public distributed func join(worker: LeniaWorker, workerId: String, creature: SavedCreature) async -> Bool {
        guard !isRunning, participants.count < config.maxPlayers else { return false }
        if let existing = participants.values.first?.1,
           !isCompatibleGenotype(existing.genotype, creature.genotype) {
            logger.warning("Arena \(config.id) rejected \(workerId): genotype mismatch (only h may differ).")
            return false
        }
        participants[workerId] = (worker, creature)
        logger.info("\(workerId) joined arena \(config.id) (\(participants.count)/\(config.maxPlayers) players)")

        let lobbyState = ArenaState(config: config, status: .lobby, participants: Array(participants.keys))
        for (w, _) in participants.values {
            try? await w.receiveArenaState(lobbyState)
        }

        if participants.count >= config.maxPlayers {
            logger.info("Arena \(config.id) full - auto-starting!")
            Task {
                await self.start()
            }
        }

        return true
    }

    public distributed func getState() async -> ArenaState {
        let status: ArenaStatus = isRunning ? .running : (participants.isEmpty ? .lobby : .lobby)
        return ArenaState(config: config, status: status, participants: Array(participants.keys))
    }

    public distributed func start() async {
        guard !isRunning, !participants.isEmpty else { return }
        isRunning = true

        logger.info("Initializing Arena Physics...")
        initPhysics()

        let runningState = ArenaState(config: config, status: .running, participants: Array(participants.keys))
        for (worker, _) in participants.values {
            try? await worker.receiveArenaState(runningState)
        }

        Task {
            await gameLoop()
        }
    }

    public distributed func stop() async {
        isRunning = false
        logger.info("Arena \(config.id) stopped")
    }

    public distributed func triggerMutationEvent(strength: Float = 0.05) async {
        guard isRunning, let currentP = stateP else { return }
        logger.info("Triggering Radiation Storm in Arena \(config.id)!")

        let shape = currentP.shape

        // Generate noise for parameter mutation
        let noise = MLXRandom.normal(shape, stream: .default) * strength

        // Apply jitter to parameters and clip to valid range
        let mutatedP = currentP + noise
        self.stateP = MLX.clip(mutatedP, min: MLXArray(0.0), max: MLXArray(1.0))

        // Also jitter the mass slightly to break physical symmetry
        if let currentA = stateA {
            let massNoise = MLXRandom.normal(currentA.shape, stream: .default) * 0.01
            self.stateA = MLX.clip(currentA + massNoise, min: MLXArray(0.0), max: MLXArray(1.0))
        }
    }

    private func initPhysics() {
        let size = config.size

        guard let first = participants.values.first?.1 else { return }
        let genotype = first.genotype

        let nbK = genotype.r.count
        if genotype.h.count != nbK {
            fatalError("Genotype h length (\(genotype.h.count)) must match r length (\(nbK))")
        }
        // All kernels operate on the single channel (channel 0)
        let c0 = Array(repeating: 0, count: nbK)
        let c1 = [Array(0..<nbK)]

        let params = ResolvedParams(
            r: genotype.r,
            b: genotype.b,
            w: genotype.w,
            a: genotype.a,
            m: genotype.m,
            s: genotype.s,
            h: genotype.h,
            R: genotype.R,
            seed: first.initialCondition.seed
        )

        let bConfig = BatchedConfig(
            sx: size, sy: size, channels: 1, nbK: nbK,
            dt: 0.2, dd: 5, sigma: 0.65, n: 2, thetaA: 2.0, border: "torus",
            implementation: ImplementationSettings(
                mode: "flowlenia_2022_paper_equations",
                border: "torus",
                gradientBoundary: "periodic",
                alphaMode: "mass",
                kernelProfile: "flowlenia_2022_paper_equations",
                flowClip: "none"
            ),
            chemChannel: nil,
            chemIncludeInMass: true
        )
        self.batchedConfig = bConfig

        let kernels = compileKernels(params: params, config: bConfig, c0: c0, c1: c1)
        self.engine = FlowLeniaParamsBatched(
            config: bConfig,
            kernels: kernels,
            mixMode: "avg",
            mixSeed: nil
        )

        var dataA = [Float](repeating: 0, count: size * size)
        var dataP = [Float](repeating: 0, count: size * size * nbK)

        let positions = [
            (size / 4, size / 4),
            (size * 3 / 4, size * 3 / 4),
            (size / 4, size * 3 / 4),
            (size * 3 / 4, size / 4)
        ]

        var idx = 0
        for (_, creature) in participants.values {
            if idx >= positions.count { break }
            let (cx, cy) = positions[idx]
            placeCreature(creature, at: (cx, cy), intoA: &dataA, intoP: &dataP, arenaSize: size, nbK: nbK)
            idx += 1
        }

        self.stateA = MLXArray(dataA).reshaped([1, size, size, 1])
        self.stateP = MLXArray(dataP).reshaped([1, size, size, nbK])
    }

    private func placeCreature(_ c: SavedCreature, at center: (Int, Int), intoA: inout [Float], intoP: inout [Float], arenaSize: Int, nbK: Int) {
        var rng = SeededRandomNumberGenerator(seed: UInt64(c.initialCondition.seed))

        let radius = 20
        for y in (center.1 - radius)...(center.1 + radius) {
            for x in (center.0 - radius)...(center.0 + radius) {
                let px = (x + arenaSize) % arenaSize
                let py = (y + arenaSize) % arenaSize

                let dx = x - center.0
                let dy = y - center.1
                if dx * dx + dy * dy < radius * radius {
                    intoA[py * arenaSize + px] = Float.random(in: 0.0...1.0, using: &rng)

                    for k in 0..<nbK {
                        let pIndex = (py * arenaSize + px) * nbK + k
                        if k < c.genotype.h.count {
                            intoP[pIndex] = c.genotype.h[k]
                        }
                    }
                }
            }
        }
    }

    private func gameLoop() async {
        while isRunning {
            guard let eng = engine, var A = stateA, var P = stateP else { break }

            let (newA, newP) = eng.step(A, P)
            A = newA
            P = newP

            // Automatic entropy injection every 200 steps to prevent stagnant loops
            if step % 200 == 0 && step > 0 {
                let entropy = MLXRandom.normal(P.shape, stream: .default) * 0.002
                P = P + entropy
            }

            stateA = A
            stateP = P

            if step % 2 == 0 {
                if let frameData = prepareFrameData(A) {
                    let frame = ArenaFrame(
                        arenaId: config.id,
                        step: step,
                        width: config.size,
                        height: config.size,
                        data: frameData
                    )
                    await broadcast(frame)
                }
            }

            step += 1

            if step % 20 == 0 {
                eval(A)
                eval(P)
            }

            try? await Task.sleep(for: .milliseconds(16))
        }
    }

    private func prepareFrameData(_ A: MLXArray) -> Data? {
        let flat = A.flattened()
        eval(flat)
        let floatData: [Float] = flat.asArray(Float.self)
        let uint8Data = floatData.map { UInt8(max(0, min(1, $0)) * 255) }
        return Data(uint8Data)
    }

    private func broadcast(_ frame: ArenaFrame) async {
        for (worker, _) in participants.values {
            try? await worker.receiveArenaFrame(frame)
        }
    }

    private func isCompatibleGenotype(_ base: KernelParams, _ candidate: KernelParams) -> Bool {
        guard base.r == candidate.r,
              base.b == candidate.b,
              base.w == candidate.w,
              base.a == candidate.a,
              base.m == candidate.m,
              base.s == candidate.s,
              base.R == candidate.R else {
            return false
        }
        return candidate.h.count == base.h.count
    }
}
