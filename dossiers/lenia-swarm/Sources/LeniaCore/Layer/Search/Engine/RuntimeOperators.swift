import Foundation
import MLX

struct SearchRuntimeOperators {
    let runtimeConfig: LeniaRuntimeConfig

    func applyWallMaskIfNeeded(
        massBatch: inout MLXArray,
        paramBatch: inout MLXArray?,
        foodBatch: inout MLXArray?,
        wallMask: MLXArray?
    ) {
        guard let wallMask else {
            return
        }
        massBatch = applyWallMask(massBatch, mask: wallMask)
        if let params = paramBatch {
            paramBatch = applyWallMask(params, mask: wallMask)
        }
        if let food = foodBatch {
            foodBatch = applyWallMaskToField(food, mask: wallMask)
        }
    }

    func applyChemotaxis(_ batch: MLXArray, field: MLXArray, channelIndex: Int) -> MLXArray {
        overwriteFieldChannel(batch, field: field, channelIndex: channelIndex)
    }

    func applyFoodField(_ batch: MLXArray, field: MLXArray, channelIndex: Int) -> MLXArray {
        overwriteFieldChannel(batch, field: field, channelIndex: channelIndex)
    }

    func applyWallMask(_ batch: MLXArray, mask: MLXArray) -> MLXArray {
        batch * MLX.broadcast(mask, to: batch.shape)
    }

    func applyWallMaskToField(_ field: MLXArray, mask: MLXArray) -> MLXArray {
        let mask2D = mask.squeezed(axis: 3)
        return field * MLX.broadcast(mask2D, to: field.shape)
    }

    func applyFoodDynamics(
        _ massBatch: MLXArray,
        food: MLXArray,
        config: FoodConfig
    ) -> (mass: MLXArray, food: MLXArray) {
        let decayRate = MLXArray(config.decay_rate)
        let digestRate = MLXArray(config.digest_rate)
        let eps = MLXArray(Float(1e-6))

        let massMap = matterMapFromBatch(massBatch)
        let decay = massMap * decayRate
        let digestRaw = massMap * digestRate
        let digestClipped = MLX.clip(digestRaw, min: MLXArray(0.0), max: massMap)
        let delta = digestClipped * food

        let newMass = MLX.maximum(massMap + delta - decay, MLXArray(0.0))
        let scale = newMass / MLX.maximum(massMap, eps)
        let scaleExpanded = scale.expandedDimensions(axis: -1)

        let excluded = excludedMassChannels()
        let channels = massBatch.shape[3]
        var parts: [MLXArray] = []
        for channel in 0..<channels {
            let channelBatch = massBatch[0..., 0..., 0..., channel].expandedDimensions(axis: -1)
            if excluded.contains(channel) {
                parts.append(channelBatch)
            } else {
                parts.append(channelBatch * scaleExpanded)
            }
        }
        let newMassBatch = MLX.concatenated(parts, axis: 3)
        let newFood = MLX.maximum(food - delta, MLXArray(0.0))
        return (newMassBatch, newFood)
    }

    func applyEnvironmentalFields(
        massBatch: inout MLXArray,
        chemField: MLXArray?,
        foodBatch: MLXArray?
    ) {
        if let field = chemField, let chemConfig = runtimeConfig.chemotaxis {
            massBatch = applyChemotaxis(massBatch, field: field, channelIndex: chemConfig.channel_index)
        }

        if let food = foodBatch, let foodConfig = runtimeConfig.food, foodConfig.enabled {
            massBatch = applyFoodField(massBatch, field: food, channelIndex: foodConfig.channel_index)
        }
    }

    func applyPreStepOperators(
        step: Int,
        massBatch: inout MLXArray,
        paramBatch: inout MLXArray?,
        chemField: MLXArray?,
        foodBatch: MLXArray?
    ) {
        applyEnvironmentalFields(
            massBatch: &massBatch,
            chemField: chemField,
            foodBatch: foodBatch
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
            massBatch = applyFoodField(massBatch, field: updated.food, channelIndex: foodConfig.channel_index)
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
                    massBatch = applyFoodField(massBatch, field: maskedFood, channelIndex: foodConfig.channel_index)
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

    func applyBeamMutation(_ paramsBatch: MLXArray, config: BeamMutationConfig, step: Int) -> MLXArray {
        let batchSize = paramsBatch.shape[0]
        let sx = paramsBatch.shape[1]
        let sy = paramsBatch.shape[2]
        let nbK = paramsBatch.shape[3]
        let patch = buildBeamMutationPatch(
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

    func beamMutationPatchSchedule(
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
            let patch = buildBeamMutationPatch(
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

    func excludedMassChannels() -> Set<Int> {
        flowExcludedMassChannels(
            channels: runtimeConfig.channels,
            chemotaxis: runtimeConfig.chemotaxis,
            food: runtimeConfig.food
        )
    }

    func matterWeights() -> [Float]? {
        flowMatterWeights(channels: runtimeConfig.channels, excludedChannels: excludedMassChannels())
    }

    func metalStaticChannelFields(chemField: MLXArray?) -> [FlowLeniaMetalChannelField] {
        var fields: [FlowLeniaMetalChannelField] = []
        if let field = chemField,
           let chemConfig = runtimeConfig.chemotaxis,
           chemConfig.enabled {
            fields.append(FlowLeniaMetalChannelField(
                channelIndex: chemConfig.channel_index,
                field: field
            ))
        }
        return fields
    }

    func metalFoodState(foodBatch: MLXArray?) -> FlowLeniaMetalFoodState? {
        guard let field = foodBatch,
              let foodConfig = runtimeConfig.food,
              foodConfig.enabled else {
            return nil
        }
        return FlowLeniaMetalFoodState(
            channelIndex: foodConfig.channel_index,
            field: field,
            decayRate: foodConfig.decay_rate,
            digestRate: foodConfig.digest_rate
        )
    }

    private func matterMapFromBatch(_ batch: MLXArray) -> MLXArray {
        flowMatterMap(batch, excludedChannels: excludedMassChannels())
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
                            let u1 = Float.random(in: 0.0001...0.9999, using: &rng)
                            let u2 = Float.random(in: 0.0...1.0, using: &rng)
                            deltas[deltaIndex] = sqrt(-2.0 * log(u1)) * cos(2.0 * Float.pi * u2) * (intervention.std ?? 0)
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

    private func buildBeamMutationPatch(
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
                        let u1 = Float.random(in: 0.0001...0.9999, using: &rng)
                        let u2 = Float.random(in: 0.0...1.0, using: &rng)
                        let noise = sqrt(-2.0 * log(u1)) * cos(2.0 * Float.pi * u2) * config.std
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
