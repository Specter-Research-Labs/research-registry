import Foundation
import MLX

struct SearchInitializationBuilder {
    let runtimeConfig: LeniaRuntimeConfig
    let useParamEmbedding: Bool
    let constantPerPatchParameters: Bool

    func buildInitialState(seed: Int) -> MLXArray {
        if let statePatch = runtimeConfig.statePatch {
            return buildInitialState(statePatch: statePatch)
        }

        var rng = SeededRandomNumberGenerator(seed: UInt64(seed))
        var state = [[Float]](
            repeating: [Float](repeating: 0.0, count: runtimeConfig.sy * runtimeConfig.channels),
            count: runtimeConfig.sx
        )

        let low = runtimeConfig.aUniform.low
        let high = runtimeConfig.aUniform.high

        for patch in runtimeConfig.patches {
            let bounds = patchBounds(
                center: patch.center,
                size: patch.size,
                sx: runtimeConfig.sx,
                sy: runtimeConfig.sy,
                kind: "Patch"
            )
            for x in bounds.x0..<bounds.x1 {
                for y in bounds.y0..<bounds.y1 {
                    for channel in 0..<runtimeConfig.channels {
                        state[x][y * runtimeConfig.channels + channel] = Float.random(in: low...high, using: &rng)
                    }
                }
            }
        }

        let flat = state.flatMap { $0 }
        return MLXArray(flat).reshaped([runtimeConfig.sx, runtimeConfig.sy, runtimeConfig.channels])
    }

    func buildInitialState(statePatch: InitStatePatchConfig) -> MLXArray {
        buildExplicitInitialState(
            sx: runtimeConfig.sx,
            sy: runtimeConfig.sy,
            channels: runtimeConfig.channels,
            statePatch: statePatch
        )
    }

    func buildInitialParameterState(seed: Int) -> MLXArray? {
        guard useParamEmbedding else {
            return nil
        }
        if let paramPatch = runtimeConfig.paramPatch {
            return buildExplicitInitialState(
                sx: runtimeConfig.sx,
                sy: runtimeConfig.sy,
                channels: runtimeConfig.nbK,
                statePatch: paramPatch
            )
        }
        if let pUniform = runtimeConfig.pUniform, let envConfig = runtimeConfig.environment {
            return buildCrossMapInitialParams(
                seed: seed,
                pUniform: pUniform,
                environment: envConfig
            )
        }
        if let pUniform = runtimeConfig.pUniform {
            return buildInitialParams(seed: seed, pUniform: pUniform)
        }
        fatalError("parameter_embedding.enabled requires init.p_uniform or init.p_state_patch.")
    }

    func buildInitialFoodFieldIfEnabled(seed: Int) -> MLXArray? {
        guard let foodConfig = runtimeConfig.food, foodConfig.enabled else {
            return nil
        }
        return buildInitialFoodField(seed: seed, config: foodConfig)
    }

    func runtimeWallMask(includeEnvironmentMask: Bool = false) -> MLXArray? {
        if let wallsConfig = runtimeConfig.walls, wallsConfig.enabled {
            return buildWallMask(config: wallsConfig).expandedDimensions(axes: [0, 3])
        }
        if includeEnvironmentMask, let envConfig = runtimeConfig.environment {
            return buildCrossMapMask(config: envConfig).expandedDimensions(axes: [0, 3])
        }
        return nil
    }

    func runtimeChemotaxisField() -> MLXArray? {
        guard let chemConfig = runtimeConfig.chemotaxis, chemConfig.enabled else {
            return nil
        }
        return buildChemotaxisField(config: chemConfig).expandedDimensions(axes: [0, 3])
    }

    func environmentPotential() -> MLXArray? {
        guard let envConfig = runtimeConfig.environment else {
            return nil
        }
        return buildCrossMapMask(config: envConfig).expandedDimensions(axes: [0, 3])
    }

    private func buildExplicitInitialState(
        sx: Int,
        sy: Int,
        channels: Int,
        statePatch: InitStatePatchConfig
    ) -> MLXArray {
        let values = statePatch.decodedValues()
        precondition(statePatch.center.count == 2, "state patch center must have x/y coordinates")
        precondition(statePatch.channels == channels, "state patch channels must match runtime channels")
        precondition(
            values.count == statePatch.width * statePatch.height * channels,
            "state patch data length must match width*height*channels"
        )
        var state = [[Float]](
            repeating: [Float](repeating: 0.0, count: sy * channels),
            count: sx
        )

        let cx = statePatch.center[0]
        let cy = statePatch.center[1]
        let halfWidth = statePatch.width / 2
        let halfHeight = statePatch.height / 2
        let x0 = cx - halfWidth
        let x1 = cx + (statePatch.width - halfWidth)
        let y0 = cy - halfHeight
        let y1 = cy + (statePatch.height - halfHeight)
        precondition(
            x0 >= 0 && y0 >= 0 && x1 <= sx && y1 <= sy,
            "state patch bounds must fit within the runtime grid"
        )

        var patchIndex = 0
        for x in x0..<x1 {
            for y in y0..<y1 {
                for channel in 0..<channels {
                    state[x][y * channels + channel] = values[patchIndex]
                    patchIndex += 1
                }
            }
        }

        let flat = state.flatMap { $0 }
        return MLXArray(flat).reshaped([sx, sy, channels])
    }

    private func buildInitialParams(seed: Int, pUniform: UniformRange) -> MLXArray {
        var rng = SeededRandomNumberGenerator(seed: UInt64(seed))
        var params = [[Float]](
            repeating: [Float](repeating: 0.0, count: runtimeConfig.sy * runtimeConfig.nbK),
            count: runtimeConfig.sx
        )

        let low = pUniform.low
        let high = pUniform.high

        for patch in runtimeConfig.patches {
            let bounds = patchBounds(
                center: patch.center,
                size: patch.size,
                sx: runtimeConfig.sx,
                sy: runtimeConfig.sy,
                kind: "Patch"
            )
            let patchParams: [Float] = constantPerPatchParameters
                ? (0..<runtimeConfig.nbK).map { _ in Float.random(in: low...high, using: &rng) }
                : []
            for x in bounds.x0..<bounds.x1 {
                for y in bounds.y0..<bounds.y1 {
                    for kernel in 0..<runtimeConfig.nbK {
                        let value = constantPerPatchParameters
                            ? patchParams[kernel]
                            : Float.random(in: low...high, using: &rng)
                        params[x][y * runtimeConfig.nbK + kernel] = value
                    }
                }
            }
        }

        let flat = params.flatMap { $0 }
        return MLXArray(flat).reshaped([runtimeConfig.sx, runtimeConfig.sy, runtimeConfig.nbK])
    }

    private func buildCrossMapInitialParams(
        seed: Int,
        pUniform: UniformRange,
        environment: EnvironmentConfig
    ) -> MLXArray {
        var rng = SeededRandomNumberGenerator(seed: UInt64(seed))
        let low = pUniform.low
        let high = pUniform.high

        let numCells = 1 << (2 * environment.depth)
        var cellParams: [[Float]] = []
        for _ in 0..<numCells {
            cellParams.append((0..<runtimeConfig.nbK).map { _ in Float.random(in: low...high, using: &rng) })
        }

        var params = [[Float]](
            repeating: [Float](repeating: 0.0, count: runtimeConfig.sy * runtimeConfig.nbK),
            count: runtimeConfig.sx
        )

        for patch in runtimeConfig.patches {
            let bounds = patchBounds(
                center: patch.center,
                size: patch.size,
                sx: runtimeConfig.sx,
                sy: runtimeConfig.sy,
                kind: "Patch"
            )
            for x in bounds.x0..<bounds.x1 {
                for y in bounds.y0..<bounds.y1 {
                    let cellIndex = crossMapCellIndex(x: x, y: y, depth: environment.depth)
                    let cell = cellParams[cellIndex]
                    for kernel in 0..<runtimeConfig.nbK {
                        params[x][y * runtimeConfig.nbK + kernel] = cell[kernel]
                    }
                }
            }
        }

        let flat = params.flatMap { $0 }
        return MLXArray(flat).reshaped([runtimeConfig.sx, runtimeConfig.sy, runtimeConfig.nbK])
    }

    private func buildInitialFoodField(seed: Int, config: FoodConfig) -> MLXArray {
        var rng = SeededRandomNumberGenerator(seed: UInt64(seed))
        var field = [[Float]](
            repeating: [Float](repeating: 0.0, count: runtimeConfig.sy),
            count: runtimeConfig.sx
        )

        let low = config.uniform.low
        let high = config.uniform.high

        switch config.mode {
        case "full":
            for x in 0..<runtimeConfig.sx {
                for y in 0..<runtimeConfig.sy {
                    field[x][y] = Float.random(in: low...high, using: &rng)
                }
            }
        case "patches":
            guard let patches = config.patches, !patches.isEmpty else {
                fatalError("food.mode=\"patches\" requires non-empty food.patches.")
            }
            for patch in patches {
                let bounds = patchBounds(
                    center: patch.center,
                    size: patch.size,
                    sx: runtimeConfig.sx,
                    sy: runtimeConfig.sy,
                    kind: "Food patch"
                )
                for x in bounds.x0..<bounds.x1 {
                    for y in bounds.y0..<bounds.y1 {
                        field[x][y] = Float.random(in: low...high, using: &rng)
                    }
                }
            }
        default:
            fatalError("food.mode must be \"full\" or \"patches\".")
        }

        let flat = field.flatMap { $0 }
        return MLXArray(flat).reshaped([runtimeConfig.sx, runtimeConfig.sy])
    }

    private func buildWallMask(config: WallsConfig) -> MLXArray {
        var mask = [[Float]](
            repeating: [Float](repeating: 1.0, count: runtimeConfig.sy),
            count: runtimeConfig.sx
        )

        for patch in config.patches {
            let bounds = patchBounds(
                center: patch.center,
                size: patch.size,
                sx: runtimeConfig.sx,
                sy: runtimeConfig.sy,
                kind: "Wall patch"
            )
            for x in bounds.x0..<bounds.x1 {
                for y in bounds.y0..<bounds.y1 {
                    mask[x][y] = 0.0
                }
            }
        }

        let flat = mask.flatMap { $0 }
        return MLXArray(flat).reshaped([runtimeConfig.sx, runtimeConfig.sy])
    }

    private func buildCrossMapMask(config: EnvironmentConfig) -> MLXArray {
        var mask = [[Float]](
            repeating: [Float](repeating: 0.0, count: runtimeConfig.sy),
            count: runtimeConfig.sx
        )
        let wallThickness = config.wallThickness
        let wallValue = config.wallValue

        func bisect(x0: Int, y0: Int, x1: Int, y1: Int, depth: Int) {
            guard depth > 0 else { return }
            let midX = (x0 + x1) / 2
            let midY = (y0 + y1) / 2
            let halfW = wallThickness / 2

            for x in max(0, midX - halfW)..<min(runtimeConfig.sx, midX - halfW + wallThickness) {
                for y in y0..<y1 {
                    mask[x][y] = wallValue
                }
            }
            for x in x0..<x1 {
                for y in max(0, midY - halfW)..<min(runtimeConfig.sy, midY - halfW + wallThickness) {
                    mask[x][y] = wallValue
                }
            }

            if let passageWidth = config.passageWidth, passageWidth > 0 {
                let halfP = passageWidth / 2
                for x in max(0, midX - halfW)..<min(runtimeConfig.sx, midX - halfW + wallThickness) {
                    for y in max(y0, midY - halfP)..<min(y1, midY - halfP + passageWidth) {
                        mask[x][y] = 0.0
                    }
                }
                for y in max(0, midY - halfW)..<min(runtimeConfig.sy, midY - halfW + wallThickness) {
                    for x in max(x0, midX - halfP)..<min(x1, midX - halfP + passageWidth) {
                        mask[x][y] = 0.0
                    }
                }
            }

            bisect(x0: x0, y0: y0, x1: midX - halfW, y1: midY - halfW, depth: depth - 1)
            bisect(x0: midX - halfW + wallThickness, y0: y0, x1: x1, y1: midY - halfW, depth: depth - 1)
            bisect(x0: x0, y0: midY - halfW + wallThickness, x1: midX - halfW, y1: y1, depth: depth - 1)
            bisect(x0: midX - halfW + wallThickness, y0: midY - halfW + wallThickness, x1: x1, y1: y1, depth: depth - 1)
        }

        bisect(x0: 0, y0: 0, x1: runtimeConfig.sx, y1: runtimeConfig.sy, depth: config.depth)

        let flat = mask.flatMap { $0 }
        return MLXArray(flat).reshaped([runtimeConfig.sx, runtimeConfig.sy])
    }

    private func crossMapCellIndex(x: Int, y: Int, depth: Int) -> Int {
        var cellIndex = 0
        var cx0 = 0
        var cy0 = 0
        var cx1 = runtimeConfig.sx
        var cy1 = runtimeConfig.sy
        for _ in 0..<depth {
            let midX = (cx0 + cx1) / 2
            let midY = (cy0 + cy1) / 2
            let quadrant: Int
            if x < midX && y < midY {
                quadrant = 0
                cx1 = midX
                cy1 = midY
            } else if x >= midX && y < midY {
                quadrant = 1
                cx0 = midX
                cy1 = midY
            } else if x < midX && y >= midY {
                quadrant = 2
                cx1 = midX
                cy0 = midY
            } else {
                quadrant = 3
                cx0 = midX
                cy0 = midY
            }
            cellIndex = cellIndex * 4 + quadrant
        }
        return cellIndex
    }

    private func buildChemotaxisField(config: ChemotaxisConfig) -> MLXArray {
        let coordsX = MLXArray(Array(0..<runtimeConfig.sx).map { Float($0) })
        let coordsY = MLXArray(Array(0..<runtimeConfig.sy).map { Float($0) })
        let (gridX, gridY) = meshgrid(coordsX, coordsY)

        var cx = config.center[0]
        var cy = config.center[1]

        if config.mode == "random_on_circle",
           let radius = config.circle_radius,
           let seed = config.seed {
            var rng = SeededRandomNumberGenerator(seed: UInt64(seed))
            let angle = Float.random(in: 0...(2 * Float.pi), using: &rng)
            cx += radius * cos(angle)
            cy += radius * sin(angle)
        }

        let cxArr = MLXArray(cx)
        let cyArr = MLXArray(cy)
        let distSq = (gridX - cxArr) * (gridX - cxArr) + (gridY - cyArr) * (gridY - cyArr)
        let exponent = -distSq / MLXArray(2.0 * config.sigma * config.sigma)
        return MLXArray(config.amplitude) * MLX.exp(exponent)
    }

    private func patchBounds(
        center: [Int],
        size: Int,
        sx: Int,
        sy: Int,
        kind: String
    ) -> (x0: Int, x1: Int, y0: Int, y1: Int) {
        let cx = center[0]
        let cy = center[1]
        let half = size / 2
        let x0 = cx - half
        let x1 = cx + (size - half)
        let y0 = cy - half
        let y1 = cy + (size - half)

        if x0 < 0 || y0 < 0 || x1 > sx || y1 > sy {
            fatalError("\(kind) out of bounds: center=(\(cx),\(cy)) size=\(size) grid=\(sx)x\(sy)")
        }

        return (x0, x1, y0, y1)
    }
}
