using PolyMorphogenesis
using Test

const RecoveryObservabilityAPI = PolyMorphogenesis.RecoveryObservability

function _observability_metric(
    exponent::Int,
    observed_count::Int,
    activator::Vector{Float64},
    profile_loss::Float64,
)
    reference_energy = 10.0
    return ComponentRecoveryMetrics(
        1,
        collect(eachindex(activator)),
        exponent,
        1.0,
        30.0,
        "Terminated",
        1.0,
        0.0,
        true,
        1,
        observed_count,
        observed_count - 1,
        1,
        observed_count,
        profile_loss,
        profile_loss,
        profile_loss,
        profile_loss,
        profile_loss,
        profile_loss,
        profile_loss,
        0.0,
        profile_loss ^ 2 * reference_energy,
        reference_energy,
        profile_loss ^ 2 * reference_energy,
        reference_energy,
        activator,
        zeros(length(activator)),
    )
end

@testset "recovery readouts expose the registered observables" begin
    reference = GraphComponentReference(
        1,
        [1, 2],
        0.5,
        1,
        1,
        [1.0, 3.0],
        [0.0, 0.0],
    )
    metrics = _observability_metric(0, 1, [3.0, 1.0], 0.5)

    @test recovery_readout(reference, [0.0, 1.0], [0.0, 0.0]) ==
        RecoveryObservabilityAPI.RecoveryReadout(1, 4.0, 0.75, 0.0)
    @test recovery_readout(metrics, [0.0, 1.0], [0.0, 0.0]) ==
        RecoveryObservabilityAPI.RecoveryReadout(1, 4.0, 0.25, 0.0)
    @test fieldnames(RecoveryObservabilityAPI.RecoveryReadout) == (
        :domain_count,
        :activator_mass,
        :centroid_x,
        :centroid_y,
    )
end

@testset "observability distinguishes aliases from informative readouts" begin
    reference = GraphComponentReference(
        1,
        [1, 2],
        0.5,
        1,
        1,
        [1.0, 3.0],
        [0.0, 0.0],
    )
    rows = [
        _observability_metric(0, 1, [0.5, 1.5], 0.8),
        _observability_metric(1, 1, [1.0, 3.0], 0.1),
        _observability_metric(2, 1, [2.0, 6.0], 0.9),
    ]
    report = RecoveryObservabilityAPI.component_observability_report(
        reference,
        rows,
        [0.0, 1.0],
        [0.0, 0.0];
        levels=[:domain_count, :domain_count_mass],
        alias_resolutions=[1.0e-3],
    )
    by_level = Dict(diagnostic.level => diagnostic for diagnostic in report.diagnostics)

    count = by_level[:domain_count]
    @test count.score_tied_exponents == [0, 1, 2]
    @test count.tie_break_failure
    @test !count.sufficient
    @test !isempty(count.quantized_alias_groups)

    mass = by_level[:domain_count_mass]
    @test mass.selected_exponent == 1
    @test mass.selected_normalized_regret == 0.0
    @test mass.sufficient
    @test isempty(mass.quantized_alias_groups)
end
