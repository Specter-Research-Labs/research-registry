import Foundation
import MLX

typealias SearchRuntimeOperators = FlowLeniaRuntimeOperators

extension FlowLeniaRuntimeOperators {
    func applyPreStepOperators(
        step: Int,
        massBatch: inout MLXArray,
        paramBatch: inout MLXArray?,
        chemField: MLXArray?,
        foodBatch: MLXArray?
    ) {
        applyPreStepFields(
            massBatch: &massBatch,
            foodBatch: foodBatch,
            chemField: chemField
        )

        guard runtimeConfig.interventions.contains(where: { $0.step == step }) else {
            return
        }

        var updatedMass = massBatch
        var updatedParams = paramBatch
        for intervention in runtimeConfig.interventions where intervention.step == step {
            switch intervention.type {
            case "jitter_params", "shift_params":
                guard let currentParams = updatedParams else {
                    fatalError("Intervention \(intervention.type) requires parameter state.")
                }
                updatedParams = applyIntervention(currentParams, intervention: intervention)
            case "zero_state_patch":
                let zeroed = applyZeroStatePatch(updatedMass, params: updatedParams, intervention: intervention)
                updatedMass = zeroed.mass
                updatedParams = zeroed.params
            default:
                fatalError("Unsupported intervention type \(intervention.type).")
            }
        }
        massBatch = updatedMass
        paramBatch = updatedParams
    }

    func applyPostStepOperators(
        massBatch: inout MLXArray,
        paramBatch: inout MLXArray?,
        foodBatch: inout MLXArray?,
        wallMask: MLXArray?
    ) {
        if let foodConfig = runtimeConfig.food, foodConfig.enabled, let food = foodBatch {
            let updated = applyFoodDynamics(massBatch, food: food, config: foodConfig)
            massBatch = updated.mass
            foodBatch = updated.food
            massBatch = applyExternalField(massBatch, field: updated.food, channelIndex: foodConfig.channel_index)
        }

        if let mask = wallMask {
            massBatch = applyWallMask(massBatch, mask: mask)
            if let params = paramBatch {
                paramBatch = applyWallMask(params, mask: mask)
            }
            if let food = foodBatch {
                let maskedFood = applyWallMaskToField(food, mask: mask)
                foodBatch = maskedFood
                if let foodConfig = runtimeConfig.food, foodConfig.enabled {
                    massBatch = applyExternalField(massBatch, field: maskedFood, channelIndex: foodConfig.channel_index)
                }
            }
        }
    }

    func applyIntervention(_ paramsBatch: MLXArray, intervention: InterventionConfig) -> MLXArray {
        let batchSize = paramsBatch.shape[0]
        let sx = paramsBatch.shape[1]
        let sy = paramsBatch.shape[2]
        let nbK = paramsBatch.shape[3]
        let patch = buildInterventionPatch(
            intervention,
            batchSize: batchSize,
            sx: sx,
            sy: sy,
            parameterCount: nbK
        )

        eval(paramsBatch)
        var paramData: [Float] = paramsBatch.flattened().asArray(Float.self)
        for batchIndex in 0..<batchSize {
            let origin = patch.origins[batchIndex]
            for localX in 0..<patch.size {
                let x = Int(origin.x) + localX
                guard x >= 0 && x < sx else {
                    continue
                }
                for localY in 0..<patch.size {
                    let y = Int(origin.y) + localY
                    guard y >= 0 && y < sy else {
                        continue
                    }
                    for kernel in 0..<nbK {
                        let idx = batchIndex * sx * sy * nbK + x * sy * nbK + y * nbK + kernel
                        let deltaIndex = ((batchIndex * patch.size + localX) * patch.size + localY) * nbK + kernel
                        var newValue = paramData[idx] + patch.deltas[deltaIndex]
                        if let clip = patch.clip {
                            newValue = max(clip[0], min(clip[1], newValue))
                        }
                        paramData[idx] = newValue
                    }
                }
            }
        }

        return MLXArray(paramData).reshaped([batchSize, sx, sy, nbK])
    }

    func applyIntervention(runner: FlowLeniaMetalFullStateRunner, intervention: InterventionConfig) {
        switch intervention.type {
        case "jitter_params", "shift_params":
            let patch = buildInterventionPatch(
                intervention,
                batchSize: runner.batchCount,
                sx: runtimeConfig.sx,
                sy: runtimeConfig.sy,
                parameterCount: runtimeConfig.nbK
            )
            runner.applyParameterPatch(
                origins: patch.origins,
                size: patch.size,
                deltas: patch.deltas,
                clip: patch.clip
            )
        case "zero_state_patch":
            let patch = buildZeroStatePatch(intervention, batchSize: runner.batchCount)
            runner.applyZeroStatePatch(origins: patch.origins, size: patch.size)
        default:
            fatalError("Unsupported intervention type \(intervention.type).")
        }
    }

    func applySearchBeamMutation(_ paramsBatch: MLXArray, config: BeamMutationConfig, step: Int) -> MLXArray {
        let batchSize = paramsBatch.shape[0]
        let sx = paramsBatch.shape[1]
        let sy = paramsBatch.shape[2]
        let nbK = paramsBatch.shape[3]
        let patch = buildSearchBeamMutationPatch(
            config: config,
            step: step,
            batchSize: batchSize,
            sx: sx,
            sy: sy,
            parameterCount: nbK
        )

        eval(paramsBatch)
        var paramData: [Float] = paramsBatch.flattened().asArray(Float.self)
        for batchIndex in 0..<batchSize {
            let origin = patch.origins[batchIndex]
            for localX in 0..<patch.size {
                let x = Int(origin.x) + localX
                guard x >= 0 && x < sx else {
                    continue
                }
                for localY in 0..<patch.size {
                    let y = Int(origin.y) + localY
                    guard y >= 0 && y < sy else {
                        continue
                    }
                    for kernel in 0..<nbK {
                        let idx = batchIndex * sx * sy * nbK + x * sy * nbK + y * nbK + kernel
                        let deltaIndex = ((batchIndex * patch.size + localX) * patch.size + localY) * nbK + kernel
                        paramData[idx] += patch.deltas[deltaIndex]
                    }
                }
            }
        }

        return MLXArray(paramData).reshaped([batchSize, sx, sy, nbK])
    }

    func searchBeamMutationPatchSchedule(
        startStep: Int,
        count: Int,
        batchSize: Int,
        parameterCount: Int
    ) -> [Int: [FlowLeniaMetalParameterPatchBatch]] {
        guard let beamConfig = runtimeConfig.beamMutation, beamConfig.enabled else {
            return [:]
        }
        guard count > 0 else {
            return [:]
        }
        var schedule: [Int: [FlowLeniaMetalParameterPatchBatch]] = [:]
        for localStep in 1...count {
            let patch = buildSearchBeamMutationPatch(
                config: beamConfig,
                step: startStep + localStep - 1,
                batchSize: batchSize,
                sx: runtimeConfig.sx,
                sy: runtimeConfig.sy,
                parameterCount: parameterCount
            )
            if patch.deltas.contains(where: { $0 != 0 }) {
                schedule[localStep] = [patch.asMetalPatchBatch()]
            }
        }
        return schedule
    }

    func energyFromBatch(_ batch: MLXArray) -> MLXArray {
        let batchSize = batch.shape[0]
        let excluded = excludedMassChannels()
        if excluded.isEmpty {
            return (batch * batch).sum(axes: [1, 2, 3])
        }
        var energy = MLX.zeros([batchSize])
        for channel in 0..<runtimeConfig.channels {
            if !excluded.contains(channel) {
                let channelBatch = batch[0..., 0..., 0..., channel]
                energy = energy + (channelBatch * channelBatch).sum(axes: [1, 2])
            }
        }
        return energy
    }

    private func buildInterventionPatch(
        _ intervention: InterventionConfig,
        batchSize: Int,
        sx: Int,
        sy: Int,
        parameterCount: Int
    ) -> SearchParameterPatch {
        let seed = intervention.seed ?? 0
        var rng = SeededRandomNumberGenerator(seed: UInt64(seed))
        let size = intervention.patch.size
        let cx = intervention.patch.center[0]
        let cy = intervention.patch.center[1]
        let half = size / 2
        let x0 = cx - half
        let y0 = cy - half
        let origins = Array(repeating: SIMD2<Int32>(Int32(x0), Int32(y0)), count: batchSize)
        var deltas = [Float](repeating: 0, count: batchSize * size * size * parameterCount)
        for batchIndex in 0..<batchSize {
            for localX in 0..<size {
                let x = x0 + localX
                for localY in 0..<size {
                    let y = y0 + localY
                    guard x >= 0 && x < sx && y >= 0 && y < sy else {
                        continue
                    }
                    for kernel in 0..<parameterCount {
                        let deltaIndex = ((batchIndex * size + localX) * size + localY) * parameterCount + kernel
                        switch intervention.type {
                        case "jitter_params":
                            deltas[deltaIndex] = gaussianSample(std: intervention.std ?? 0, rng: &rng)
                        case "shift_params":
                            deltas[deltaIndex] = intervention.delta?[kernel] ?? 0
                        default:
                            fatalError("Intervention \(intervention.type) cannot build a parameter patch.")
                        }
                    }
                }
            }
        }
        return SearchParameterPatch(
            origins: origins,
            size: size,
            deltas: deltas,
            clip: intervention.clip
        )
    }

    private func buildZeroStatePatch(
        _ intervention: InterventionConfig,
        batchSize: Int
    ) -> SearchZeroStatePatch {
        let size = intervention.patch.size
        let cx = intervention.patch.center[0]
        let cy = intervention.patch.center[1]
        let half = size / 2
        let x0 = cx - half
        let y0 = cy - half
        return SearchZeroStatePatch(
            origins: Array(repeating: SIMD2<Int32>(Int32(x0), Int32(y0)), count: batchSize),
            size: size
        )
    }

    private func applyZeroStatePatch(
        _ massBatch: MLXArray,
        params paramBatch: MLXArray?,
        intervention: InterventionConfig
    ) -> (mass: MLXArray, params: MLXArray?) {
        let batchSize = massBatch.shape[0]
        let sx = massBatch.shape[1]
        let sy = massBatch.shape[2]
        let channels = massBatch.shape[3]
        let patch = buildZeroStatePatch(intervention, batchSize: batchSize)

        eval(massBatch)
        var massData: [Float] = massBatch.flattened().asArray(Float.self)
        var paramData: [Float]? = nil
        var nbK = 0
        if let paramBatch {
            eval(paramBatch)
            paramData = paramBatch.flattened().asArray(Float.self)
            nbK = paramBatch.shape[3]
        }

        for batchIndex in 0..<batchSize {
            let origin = patch.origins[batchIndex]
            for localX in 0..<patch.size {
                let x = Int(origin.x) + localX
                guard x >= 0 && x < sx else {
                    continue
                }
                for localY in 0..<patch.size {
                    let y = Int(origin.y) + localY
                    guard y >= 0 && y < sy else {
                        continue
                    }
                    let massBase = batchIndex * sx * sy * channels + x * sy * channels + y * channels
                    for channel in 0..<channels {
                        massData[massBase + channel] = 0
                    }
                    if paramData != nil {
                        let paramBase = batchIndex * sx * sy * nbK + x * sy * nbK + y * nbK
                        for kernel in 0..<nbK {
                            paramData![paramBase + kernel] = 0
                        }
                    }
                }
            }
        }

        let nextMass = MLXArray(massData).reshaped([batchSize, sx, sy, channels])
        let nextParams = paramData.map { MLXArray($0).reshaped([batchSize, sx, sy, nbK]) }
        return (nextMass, nextParams)
    }

    private func buildSearchBeamMutationPatch(
        config: BeamMutationConfig,
        step: Int,
        batchSize: Int,
        sx: Int,
        sy: Int,
        parameterCount: Int
    ) -> SearchParameterPatch {
        var rng = SeededRandomNumberGenerator(seed: UInt64(config.seed) + UInt64(step))
        var origins = Array(
            repeating: SIMD2<Int32>(Int32(-config.patchSize), Int32(-config.patchSize)),
            count: batchSize
        )
        var deltas = [Float](repeating: 0, count: batchSize * config.patchSize * config.patchSize * parameterCount)
        for batchIndex in 0..<batchSize {
            let roll = Float.random(in: 0.0..<1.0, using: &rng)
            if roll >= config.probability { continue }

            let px = Int.random(in: 0...(sx - config.patchSize), using: &rng)
            let py = Int.random(in: 0...(sy - config.patchSize), using: &rng)
            origins[batchIndex] = SIMD2(Int32(px), Int32(py))

            for localX in 0..<config.patchSize {
                for localY in 0..<config.patchSize {
                    for kernel in 0..<parameterCount {
                        let noise = gaussianSample(std: config.std, rng: &rng)
                        let deltaIndex =
                            ((batchIndex * config.patchSize + localX) * config.patchSize + localY) * parameterCount + kernel
                        deltas[deltaIndex] = noise
                    }
                }
            }
        }
        return SearchParameterPatch(
            origins: origins,
            size: config.patchSize,
            deltas: deltas,
            clip: nil
        )
    }
}
