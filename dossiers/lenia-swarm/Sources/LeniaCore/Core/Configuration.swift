import Foundation

private func require(_ condition: Bool, _ message: String) throws {
    if !condition {
        throw ConfigError.invalidConfig(message)
    }
}

private func validateUniformRange(_ range: UniformRange, name: String) throws {
    try require(range.low <= range.high, "\(name) must satisfy low <= high.")
}

private func validateRangeArray(_ range: [Float], name: String) throws {
    try require(range.count == 2, "\(name) must have exactly 2 values.")
    try require(range[0] <= range[1], "\(name) must satisfy low <= high.")
}

private func validatePatchBounds(center: [Int], size: Int, sx: Int, sy: Int, label: String) throws {
    try require(center.count == 2, "\(label) center must have two coordinates.")
    try require(size > 0, "\(label) size must be > 0.")

    let cx = center[0]
    let cy = center[1]
    let half = size / 2
    let x0 = cx - half
    let x1 = cx + (size - half)
    let y0 = cy - half
    let y1 = cy + (size - half)

    try require(x0 >= 0 && y0 >= 0 && x1 <= sx && y1 <= sy,
                "\(label) is out of bounds for grid \(sx)x\(sy).")
}

private func validateInitStatePatch(
    _ patch: InitStatePatchConfig,
    sx: Int,
    sy: Int,
    channels: Int,
    label: String
) throws {
    try require(patch.center.count == 2, "\(label).center must have two coordinates.")
    try require(patch.width > 0, "\(label).width must be > 0.")
    try require(patch.height > 0, "\(label).height must be > 0.")
    try require(patch.channels == channels, "\(label).channels must equal config.channels=\(channels).")
    try require(patch.encoding == "f32le", "\(label).encoding must be \"f32le\".")
    let expectedBytes = patch.width * patch.height * patch.channels * MemoryLayout<Float>.size
    try require(patch.data.count == expectedBytes, "\(label).data must contain exactly \(expectedBytes) bytes.")

    let cx = patch.center[0]
    let cy = patch.center[1]
    let halfWidth = patch.width / 2
    let halfHeight = patch.height / 2
    let x0 = cx - halfWidth
    let x1 = cx + (patch.width - halfWidth)
    let y0 = cy - halfHeight
    let y1 = cy + (patch.height - halfHeight)

    try require(x0 >= 0 && y0 >= 0 && x1 <= sx && y1 <= sy,
                "\(label) is out of bounds for grid \(sx)x\(sy).")
}

func validateBaseConfig(_ config: LeniaBaseConfig) throws -> Int {
    try require(config.grid.sx > 0 && config.grid.sy > 0, "grid.sx and grid.sy must be > 0.")
    try require(config.channels > 0, "channels must be > 0.")
    try require(config.run.steps > 0, "run.steps must be > 0.")

    try require(config.flow.dt > 0, "flow.dt must be > 0.")
    try require(config.flow.n > 0, "flow.n must be > 0.")
    try require(config.flow.theta_A > 0, "flow.theta_A must be > 0.")

    try require(config.reintegration.dd >= 0, "reintegration.dd must be >= 0.")
    try require(config.reintegration.sigma > 0, "reintegration.sigma must be > 0.")

    let validBorders = ["wall", "torus"]
    try require(validBorders.contains(config.reintegration.border),
                "reintegration.border must be one of: \(validBorders.joined(separator: ", ")).")

    try validateUniformRange(config.`init`.a_uniform, name: "init.a_uniform")
    if let pUniform = config.`init`.p_uniform {
        try validateUniformRange(pUniform, name: "init.p_uniform")
    }
    if let statePatch = config.`init`.state_patch {
        try validateInitStatePatch(
            statePatch,
            sx: config.grid.sx,
            sy: config.grid.sy,
            channels: config.channels,
            label: "init.state_patch"
        )
        try require(
            config.`init`.a_uniform.low == 0 && config.`init`.a_uniform.high == 0,
            "init.state_patch requires init.a_uniform to be [0, 0]."
        )
        if !config.parameter_embedding.enabled {
            try require(
                config.`init`.patches.isEmpty,
                "init.state_patch cannot be combined with init.patches unless parameter_embedding.enabled."
            )
        }
    }
    try require(config.connectivity.count == config.channels,
                "connectivity must have \(config.channels) rows.")
    var nbK = 0
    for (rowIndex, row) in config.connectivity.enumerated() {
        try require(row.count == config.channels,
                    "connectivity row \(rowIndex) must have \(config.channels) columns.")
        for count in row {
            try require(count >= 0, "connectivity counts must be >= 0.")
            nbK += count
        }
    }
    try require(nbK > 0, "connectivity must define at least one kernel.")
    if let paramPatch = config.`init`.p_state_patch {
        try validateInitStatePatch(
            paramPatch,
            sx: config.grid.sx,
            sy: config.grid.sy,
            channels: nbK,
            label: "init.p_state_patch"
        )
        try require(config.parameter_embedding.enabled, "init.p_state_patch requires parameter_embedding.enabled.")
        try require(config.`init`.p_uniform == nil, "init.p_state_patch cannot be combined with init.p_uniform.")
    }

    let allowedModes = ["flowlenia_2022_paper_equations", "flowlenia_2022_colab", "custom"]
    try require(allowedModes.contains(config.implementation.mode),
                "implementation.mode must be one of: flowlenia_2022_paper_equations, flowlenia_2022_colab, custom.")

    let hasCustomFields = config.implementation.gradient_boundary != nil ||
        config.implementation.alpha_mode != nil ||
        config.implementation.kernel_profile != nil ||
        config.implementation.flow_clip != nil

    if config.implementation.mode == "custom" {
        try require(config.implementation.gradient_boundary != nil &&
                    config.implementation.alpha_mode != nil &&
                    config.implementation.kernel_profile != nil &&
                    config.implementation.flow_clip != nil,
                    "implementation.mode=custom requires gradient_boundary, alpha_mode, kernel_profile, and flow_clip.")
        if let gradientBoundary = config.implementation.gradient_boundary,
           let alphaMode = config.implementation.alpha_mode,
           let kernelProfile = config.implementation.kernel_profile,
           let flowClip = config.implementation.flow_clip {
            let gradientOptions = ["periodic", "zero_pad"]
            try require(gradientOptions.contains(gradientBoundary),
                        "implementation.gradient_boundary must be one of: \(gradientOptions.joined(separator: ", ")).")
            let alphaOptions = ["mass", "per_channel"]
            try require(alphaOptions.contains(alphaMode),
                        "implementation.alpha_mode must be one of: \(alphaOptions.joined(separator: ", ")).")
            let kernelOptions = ["flowlenia_2022_paper_equations", "flowlenia_2022_colab", "qd24_bucketed_v1"]
            try require(kernelOptions.contains(kernelProfile),
                        "implementation.kernel_profile must be one of: \(kernelOptions.joined(separator: ", ")).")
            let clipOptions = ["none", "params_only", "always"]
            try require(clipOptions.contains(flowClip),
                        "implementation.flow_clip must be one of: \(clipOptions.joined(separator: ", ")).")
        }
    } else {
        try require(!hasCustomFields, "implementation.mode=\(config.implementation.mode) does not allow custom implementation overrides.")
    }

    if config.parameter_embedding.enabled {
        try require(config.`init`.p_uniform != nil || config.`init`.p_state_patch != nil,
                    "parameter_embedding.enabled requires init.p_uniform or init.p_state_patch.")
        let allowedMix = ["avg", "softmax", "stoch", "argmax", "stoch_gene_wise", "energy"]
        try require(allowedMix.contains(config.parameter_embedding.mix),
                    "parameter_embedding.mix must be one of: \(allowedMix.joined(separator: ", ")).")
        let stochasticModes: Set<String> = ["stoch", "softmax", "stoch_gene_wise", "energy"]
        if stochasticModes.contains(config.parameter_embedding.mix) {
            if config.implementation.mode == "flowlenia_2022_colab" {
                try require(config.parameter_embedding.mix_seed == nil,
                            "parameter_embedding.mix_seed must be omitted when implementation.mode == \"flowlenia_2022_colab\".")
            } else {
                try require(config.parameter_embedding.mix_seed != nil,
                            "parameter_embedding.mix_seed is required for \(config.parameter_embedding.mix) mixing when implementation.mode != \"flowlenia_2022_colab\".")
            }
        }
    } else {
        try require(config.`init`.p_uniform == nil, "init.p_uniform requires parameter_embedding.enabled.")
        try require(config.`init`.p_state_patch == nil, "init.p_state_patch requires parameter_embedding.enabled.")
    }

    if config.params.mode == "random" {
        try require(config.params.seed != nil, "params.seed is required when params.mode=\"random\".")
        try require(config.params.ranges != nil, "params.ranges is required when params.mode=\"random\".")
        if let ranges = config.params.ranges {
            try validateRangeArray(ranges.r, name: "params.ranges.r")
            try validateRangeArray(ranges.b, name: "params.ranges.b")
            try validateRangeArray(ranges.w, name: "params.ranges.w")
            try validateRangeArray(ranges.a, name: "params.ranges.a")
            try validateRangeArray(ranges.m, name: "params.ranges.m")
            try validateRangeArray(ranges.s, name: "params.ranges.s")
            try validateRangeArray(ranges.h, name: "params.ranges.h")
            try validateRangeArray(ranges.R, name: "params.ranges.R")
        }
    } else if config.params.mode == "explicit" {
        try require(config.params.r != nil &&
                    config.params.b != nil &&
                    config.params.w != nil &&
                    config.params.a != nil &&
                    config.params.m != nil &&
                    config.params.s != nil &&
                    config.params.h != nil &&
                    config.params.R != nil,
                    "params.mode=\"explicit\" requires r, b, w, a, m, s, h, R.")
        if let r = config.params.r,
           let b = config.params.b,
           let w = config.params.w,
           let a = config.params.a,
           let m = config.params.m,
           let s = config.params.s,
           let h = config.params.h,
           let R = config.params.R {
            try require(r.count == nbK, "params.r must have length nbK=\(nbK).")
            try require(m.count == nbK, "params.m must have length nbK=\(nbK).")
            try require(s.count == nbK, "params.s must have length nbK=\(nbK).")
            try require(h.count == nbK, "params.h must have length nbK=\(nbK).")
            try require(b.count == nbK, "params.b must have \(nbK) rows.")
            try require(w.count == nbK, "params.w must have \(nbK) rows.")
            try require(a.count == nbK, "params.a must have \(nbK) rows.")
            try require(R > 0, "params.R must be > 0.")
            let kernelProfile = config.implementation.kernel_profile ?? config.implementation.mode
            for idx in 0..<nbK {
                try require(!b[idx].isEmpty, "params.b[\(idx)] must have at least one value.")
                try require(w[idx].count == b[idx].count, "params.w[\(idx)] must match params.b[\(idx)] length.")
                try require(a[idx].count == b[idx].count, "params.a[\(idx)] must match params.b[\(idx)] length.")
                try require(s[idx] > 0, "params.s[\(idx)] must be > 0.")
                if kernelProfile != "qd24_bucketed_v1" {
                    for wVal in w[idx] {
                        try require(wVal > 0, "params.w[\(idx)] values must be > 0.")
                    }
                }
            }
        }
    } else {
        throw ConfigError.unsupportedParamMode(config.params.mode)
    }

    for (idx, patch) in config.`init`.patches.enumerated() {
        try validatePatchBounds(
            center: patch.center,
            size: patch.size,
            sx: config.grid.sx,
            sy: config.grid.sy,
            label: "init.patches[\(idx)]"
        )
    }

    if let chem = config.chemotaxis, chem.enabled {
        try require(chem.channel_index >= 0 && chem.channel_index < config.channels,
                    "chemotaxis.channel_index is out of range for configured channels.")
        try require(config.channels >= 2, "chemotaxis requires channels >= 2.")
        try require(chem.sigma > 0, "chemotaxis.sigma must be > 0.")
        try require(chem.center.count == 2, "chemotaxis.center must have two coordinates.")
        try require(!chem.include_in_mass, "chemotaxis.include_in_mass must be false for Flow Lenia.")
        if chem.mode == "random_on_circle" {
            try require(chem.circle_radius != nil && chem.seed != nil,
                        "chemotaxis.mode=\"random_on_circle\" requires circle_radius and seed.")
        }
    }

    if let obstacle = config.obstacle_field, obstacle.enabled {
        try require(obstacle.channel_index >= 0 && obstacle.channel_index < config.channels,
                    "obstacle_field.channel_index is out of range for configured channels.")
        try require(config.channels >= 2, "obstacle_field requires channels >= 2.")
        try require(obstacle.mode == "random_on_circle",
                    "obstacle_field.mode must be \"random_on_circle\".")
        try require(obstacle.count > 0, "obstacle_field.count must be > 0.")
        try require(obstacle.sigma > 0, "obstacle_field.sigma must be > 0.")
        try require(obstacle.amplitude > 0, "obstacle_field.amplitude must be > 0.")
        try require(obstacle.center.count == 2, "obstacle_field.center must have two coordinates.")
        try require((obstacle.circle_radius ?? 0) > 0,
                    "obstacle_field.circle_radius must be > 0 for mode=\"random_on_circle\".")
    }

    if let food = config.food, food.enabled {
        try require(config.profile == .experimental, "food requires profile=experimental.")
        try require(food.channel_index >= 0 && food.channel_index < config.channels,
                    "food.channel_index is out of range for configured channels.")
        try require(config.channels >= 2, "food requires channels >= 2.")
        try require(!food.include_in_mass, "food.include_in_mass must be false for external food maps.")
        try require(food.decay_rate >= 0, "food.decay_rate must be >= 0.")
        try require(food.digest_rate >= 0, "food.digest_rate must be >= 0.")
        try validateUniformRange(food.uniform, name: "food.uniform")
        try require(food.mode == "full" || food.mode == "patches",
                    "food.mode must be \"full\" or \"patches\".")
        if food.mode == "patches" {
            try require(!(food.patches?.isEmpty ?? true),
                        "food.mode=\"patches\" requires non-empty food.patches.")
            if let patches = food.patches {
                for (idx, patch) in patches.enumerated() {
                    try validatePatchBounds(
                        center: patch.center,
                        size: patch.size,
                        sx: config.grid.sx,
                        sy: config.grid.sy,
                        label: "food.patches[\(idx)]"
                    )
                }
            }
        }
    }

    if let walls = config.walls, walls.enabled {
        try require(config.profile == .experimental, "walls require profile=experimental.")
        try require(!walls.patches.isEmpty, "walls.patches must be non-empty when walls are enabled.")
        for (idx, patch) in walls.patches.enumerated() {
            try validatePatchBounds(
                center: patch.center,
                size: patch.size,
                sx: config.grid.sx,
                sy: config.grid.sy,
                label: "walls.patches[\(idx)]"
            )
        }
    }

    if let env = config.environment {
        try require(config.profile == .experimental, "environment requires profile=experimental.")
        try require(env.type == "cross_map", "environment.type must be \"cross_map\".")
        try require(env.depth >= 1 && env.depth <= 4, "environment.depth must be in 1...4.")
        try require(env.wallThickness > 0, "environment.wall_thickness must be > 0.")
        try require(config.parameter_embedding.enabled, "environment requires parameter_embedding.enabled.")
        if let pw = env.passageWidth {
            try require(pw > 0, "environment.passage_width must be > 0 when set.")
        }
        let wallsEnabled = config.walls?.enabled ?? false
        try require(!wallsEnabled, "environment and walls.enabled are mutually exclusive.")
        let obstacleEnabled = config.obstacle_field?.enabled ?? false
        try require(!obstacleEnabled, "environment and obstacle_field.enabled are mutually exclusive.")
    }

    if let beam = config.beam_mutation {
        try require(config.profile == .experimental, "beam_mutation requires profile=experimental.")
        if beam.enabled {
            try require(config.parameter_embedding.enabled, "beam_mutation requires parameter_embedding.enabled.")
            try require(beam.probability >= 0 && beam.probability <= 1, "beam_mutation.probability must be in [0, 1].")
            try require(beam.patchSize > 0, "beam_mutation.patch_size must be > 0.")
            try require(beam.std > 0, "beam_mutation.std must be > 0.")
        }
    }

    if let chem = config.chemotaxis, chem.enabled,
       let food = config.food, food.enabled,
       chem.channel_index == food.channel_index {
        throw ConfigError.invalidConfig("chemotaxis and food cannot share the same channel_index.")
    }
    if let chem = config.chemotaxis, chem.enabled,
       let obstacle = config.obstacle_field, obstacle.enabled,
       chem.channel_index == obstacle.channel_index {
        throw ConfigError.invalidConfig("chemotaxis and obstacle_field cannot share the same channel_index.")
    }
    if let food = config.food, food.enabled,
       let obstacle = config.obstacle_field, obstacle.enabled,
       food.channel_index == obstacle.channel_index {
        throw ConfigError.invalidConfig("food and obstacle_field cannot share the same channel_index.")
    }

    let interventions = config.interventions ?? []
    if !interventions.isEmpty {
        try require(config.profile == .experimental, "interventions require profile=experimental.")
        for (idx, intervention) in interventions.enumerated() {
            try require(intervention.version == 1, "interventions[\(idx)].version must be 1.")
            try require(intervention.step >= 0, "interventions[\(idx)].step must be >= 0.")
            try validatePatchBounds(
                center: intervention.patch.center,
                size: intervention.patch.size,
                sx: config.grid.sx,
                sy: config.grid.sy,
                label: "interventions[\(idx)].patch"
            )
            if let clip = intervention.clip {
                try require(clip.count == 2, "interventions[\(idx)].clip must have 2 values.")
                try require(clip[0] <= clip[1], "interventions[\(idx)].clip must satisfy low <= high.")
            }
            switch intervention.type {
            case "jitter_params":
                try require(config.parameter_embedding.enabled, "interventions[\(idx)] jitter_params requires parameter_embedding.enabled.")
                try require(intervention.std != nil, "interventions[\(idx)].std is required for jitter_params.")
                try require(intervention.seed != nil, "interventions[\(idx)].seed is required for jitter_params.")
                try require(intervention.delta == nil, "interventions[\(idx)].delta is not allowed for jitter_params.")
                if let std = intervention.std {
                    try require(std >= 0, "interventions[\(idx)].std must be >= 0.")
                }
            case "shift_params":
                try require(config.parameter_embedding.enabled, "interventions[\(idx)] shift_params requires parameter_embedding.enabled.")
                try require(intervention.delta != nil, "interventions[\(idx)].delta is required for shift_params.")
                try require(intervention.std == nil, "interventions[\(idx)].std is not allowed for shift_params.")
                try require(intervention.seed == nil, "interventions[\(idx)].seed is not allowed for shift_params.")
                if let delta = intervention.delta {
                    try require(delta.count == nbK, "interventions[\(idx)].delta must have \(nbK) values.")
                }
            case "zero_state_patch":
                try require(intervention.std == nil, "interventions[\(idx)].std is not allowed for zero_state_patch.")
                try require(intervention.seed == nil, "interventions[\(idx)].seed is not allowed for zero_state_patch.")
                try require(intervention.delta == nil, "interventions[\(idx)].delta is not allowed for zero_state_patch.")
                try require(intervention.clip == nil, "interventions[\(idx)].clip is not allowed for zero_state_patch.")
            default:
                throw ConfigError.invalidConfig(
                    "interventions[\(idx)].type must be one of: jitter_params, shift_params, zero_state_patch."
                )
            }
        }
    }

    if config.profile == .paper {
        if config.`init`.state_patch == nil {
            try require(config.`init`.patches.count == 1,
                        "profile=paper requires exactly one init patch when init.state_patch is absent.")
            let patch = config.`init`.patches[0]
            try require(patch.size == 40, "profile=paper requires init patch size == 40 when init.state_patch is absent.")
            let expectedCenter = [config.grid.sx / 2, config.grid.sy / 2]
            try require(patch.center == expectedCenter,
                        "profile=paper requires init patch centered at \(expectedCenter) when init.state_patch is absent.")
            try require(config.`init`.a_uniform.low == 0.0 && config.`init`.a_uniform.high == 1.0,
                        "profile=paper requires init.a_uniform range [0, 1] when init.state_patch is absent.")
        }
        if config.parameter_embedding.enabled {
            let mix = config.parameter_embedding.mix
            try require(mix == "avg" || mix == "softmax",
                        "profile=paper requires parameter_embedding.mix to be \"avg\" or \"softmax\".")
        }
        if let chem = config.chemotaxis, chem.enabled {
            try require(chem.mode == "random_on_circle",
                        "profile=paper chemotaxis requires mode == \"random_on_circle\".")
            try require(chem.circle_radius != nil && chem.seed != nil,
                        "profile=paper chemotaxis requires circle_radius and seed.")
            let expectedCenter = [Float(config.grid.sx) / 2.0, Float(config.grid.sy) / 2.0]
            try require(chem.center.count == 2 &&
                        chem.center[0] == expectedCenter[0] &&
                        chem.center[1] == expectedCenter[1],
                        "profile=paper chemotaxis requires center at \(expectedCenter).")
        }
        if let obstacle = config.obstacle_field, obstacle.enabled {
            try require(obstacle.mode == "random_on_circle",
                        "profile=paper obstacle_field requires mode == \"random_on_circle\".")
            try require((obstacle.circle_radius ?? 0) > 0,
                        "profile=paper obstacle_field requires circle_radius.")
            let expectedCenter = [Float(config.grid.sx) / 2.0, Float(config.grid.sy) / 2.0]
            try require(obstacle.center.count == 2 &&
                        obstacle.center[0] == expectedCenter[0] &&
                        obstacle.center[1] == expectedCenter[1],
                        "profile=paper obstacle_field requires center at \(expectedCenter).")
        }
    } else if config.profile == .colab {
        try require(config.reintegration.border == "wall",
                    "profile=colab requires reintegration.border == \"wall\".")
    }

    return nbK
}

public enum ConfigError: Error {
    case missingParamSeed
    case missingExplicitParams
    case unsupportedParamMode(String)
    case invalidConfig(String)
}
