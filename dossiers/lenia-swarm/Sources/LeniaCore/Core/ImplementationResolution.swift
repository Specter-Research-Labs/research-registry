import Foundation

func validateProfileCompatibility(
    profile: RuntimeProfile,
    implementation: ImplementationConfig
) throws {
    switch profile {
    case .paper:
        if implementation.mode != "flowlenia_2022_paper_equations" {
            throw ConfigError.invalidConfig("profile=paper requires implementation.mode=\"flowlenia_2022_paper_equations\".")
        }
    case .colab:
        if implementation.mode != "flowlenia_2022_colab" {
            throw ConfigError.invalidConfig("profile=colab requires implementation.mode=\"flowlenia_2022_colab\".")
        }
    case .experimental:
        break
    }

    if profile != .colab, implementation.mode == "flowlenia_2022_colab" {
        throw ConfigError.invalidConfig("implementation.mode=\"flowlenia_2022_colab\" is only allowed when profile=colab.")
    }

    if profile != .experimental, implementation.mode == "custom" {
        throw ConfigError.invalidConfig("implementation.mode=\"custom\" is only allowed when profile=experimental.")
    }
}

private func validateImplementationValues(
    gradientBoundary: String,
    alphaMode: String,
    kernelProfile: String,
    growthProfile: String,
    flowClip: String
) {
    let gradientOptions = ["periodic", "zero_pad"]
    if !gradientOptions.contains(gradientBoundary) {
        fatalError("implementation.gradient_boundary must be one of: \(gradientOptions.joined(separator: ", ")).")
    }
    let alphaOptions = ["mass", "per_channel"]
    if !alphaOptions.contains(alphaMode) {
        fatalError("implementation.alpha_mode must be one of: \(alphaOptions.joined(separator: ", ")).")
    }
    let kernelOptions = ["flowlenia_2022_paper_equations", "flowlenia_2022_colab", "qd24_bucketed_v1", "qd24_bump4_v1", "qd24_quad4_v1", "qd24_step_v1", "qd24_life_v1"]
    if !kernelOptions.contains(kernelProfile) {
        fatalError("implementation.kernel_profile must be one of: \(kernelOptions.joined(separator: ", ")).")
    }
    let growthOptions = ["gaussian", "quad4", "stpz"]
    if !growthOptions.contains(growthProfile) {
        fatalError("implementation.growth_profile must be one of: \(growthOptions.joined(separator: ", ")).")
    }
    let clipOptions = ["none", "params_only", "always"]
    if !clipOptions.contains(flowClip) {
        fatalError("implementation.flow_clip must be one of: \(clipOptions.joined(separator: ", ")).")
    }
}

public func resolveImplementationSettings(
    implementation: ImplementationConfig,
    border: String
) -> ImplementationSettings {
    let validBorders = ["wall", "torus"]
    if !validBorders.contains(border) {
        fatalError("reintegration.border must be one of: \(validBorders.joined(separator: ", ")).")
    }

    let hasCustomFields = implementation.gradient_boundary != nil ||
        implementation.alpha_mode != nil ||
        implementation.kernel_profile != nil ||
        implementation.growth_profile != nil ||
        implementation.flow_clip != nil
    let hasQD24UnsupportedOverrides = implementation.gradient_boundary != nil ||
        implementation.alpha_mode != nil ||
        implementation.flow_clip != nil

    switch implementation.mode {
    case "flowlenia_2022_paper_equations":
        if hasCustomFields {
            fatalError("implementation.mode=flowlenia_2022_paper_equations does not allow custom implementation overrides.")
        }
        return ImplementationSettings(
            mode: "flowlenia_2022_paper_equations",
            border: border,
            gradientBoundary: border == "torus" ? "periodic" : "zero_pad",
            alphaMode: "mass",
            kernelProfile: "flowlenia_2022_paper_equations",
            flowClip: "none"
        )
    case "flowlenia_2022_colab":
        if hasCustomFields {
            fatalError("implementation.mode=flowlenia_2022_colab does not allow custom implementation overrides.")
        }
        return ImplementationSettings(
            mode: "flowlenia_2022_colab",
            border: border,
            gradientBoundary: border == "torus" ? "periodic" : "zero_pad",
            alphaMode: "per_channel",
            kernelProfile: "flowlenia_2022_colab",
            flowClip: "params_only"
        )
    case "custom":
        guard let gradientBoundary = implementation.gradient_boundary,
              let alphaMode = implementation.alpha_mode,
              let kernelProfile = implementation.kernel_profile,
              let flowClip = implementation.flow_clip else {
            fatalError("implementation.mode=custom requires gradient_boundary, alpha_mode, kernel_profile, and flow_clip.")
        }
        let growthProfile = implementation.growth_profile ?? "gaussian"
        validateImplementationValues(
            gradientBoundary: gradientBoundary,
            alphaMode: alphaMode,
            kernelProfile: kernelProfile,
            growthProfile: growthProfile,
            flowClip: flowClip
        )
        return ImplementationSettings(
            mode: "custom",
            border: border,
            gradientBoundary: gradientBoundary,
            alphaMode: alphaMode,
            kernelProfile: kernelProfile,
            growthProfile: growthProfile,
            flowClip: flowClip
        )
    case "qd24_additive_v1":
        if hasQD24UnsupportedOverrides {
            fatalError("implementation.mode=qd24_additive_v1 only allows kernel_profile and growth_profile as implementation overrides.")
        }
        let kernelProfile = implementation.kernel_profile ?? "qd24_bucketed_v1"
        let kernelOptions = ["qd24_bucketed_v1", "qd24_bump4_v1", "qd24_quad4_v1", "qd24_step_v1", "qd24_life_v1"]
        if !kernelOptions.contains(kernelProfile) {
            fatalError("implementation.kernel_profile for qd24_additive_v1 must be one of: \(kernelOptions.joined(separator: ", ")).")
        }
        let growthProfile = implementation.growth_profile ?? "gaussian"
        let growthOptions = ["gaussian", "quad4", "stpz"]
        if !growthOptions.contains(growthProfile) {
            fatalError("implementation.growth_profile for qd24_additive_v1 must be one of: \(growthOptions.joined(separator: ", ")).")
        }
        return ImplementationSettings(
            mode: "qd24_additive_v1",
            border: border,
            gradientBoundary: border == "torus" ? "periodic" : "zero_pad",
            alphaMode: "mass",
            kernelProfile: kernelProfile,
            growthProfile: growthProfile,
            flowClip: "none"
        )
    default:
        fatalError("implementation.mode must be one of: flowlenia_2022_paper_equations, flowlenia_2022_colab, custom, qd24_additive_v1.")
    }
}
