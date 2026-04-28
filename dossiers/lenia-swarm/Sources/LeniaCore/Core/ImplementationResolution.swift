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
    let kernelOptions = ["flowlenia_2022_paper_equations", "flowlenia_2022_colab", "qd24_bucketed_v1"]
    if !kernelOptions.contains(kernelProfile) {
        fatalError("implementation.kernel_profile must be one of: \(kernelOptions.joined(separator: ", ")).")
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
        validateImplementationValues(
            gradientBoundary: gradientBoundary,
            alphaMode: alphaMode,
            kernelProfile: kernelProfile,
            flowClip: flowClip
        )
        return ImplementationSettings(
            mode: "custom",
            border: border,
            gradientBoundary: gradientBoundary,
            alphaMode: alphaMode,
            kernelProfile: kernelProfile,
            flowClip: flowClip
        )
    default:
        fatalError("implementation.mode must be one of: flowlenia_2022_paper_equations, flowlenia_2022_colab, custom.")
    }
}
