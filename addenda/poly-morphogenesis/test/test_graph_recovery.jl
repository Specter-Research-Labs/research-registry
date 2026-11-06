using PolyMorphogenesis
using Test

const GraphRecoveryAPI = PolyMorphogenesis.GraphRecovery

@testset "recovery actions preserve direction and diffusion ratio" begin
    @test GraphRecoveryAPI.count_error_action.((-4, 0, 7)) == (-1, 0, 1)
    baseline = RDParameters(D_a=2.0, D_i=60.0)
    for exponent in -2:2
        adjusted = GraphRecoveryAPI.diffusion_parameters_at_exponent(baseline, exponent, 1.21)
        @test adjusted.D_i / adjusted.D_a ≈ baseline.D_i / baseline.D_a
    end
end

@testset "tiny recovery is bounded, factorized, and deterministic" begin
    options = (
        rows=2,
        cols=3,
        patch_top=1,
        patch_left=1,
        patch_rows=1,
        patch_cols=1,
        settle_time=0.1,
        seed=7,
        D_a=1.0,
        D_i=30.0,
        exponent_min=-1,
        exponent_max=1,
        max_iterations=1,
        active_fraction=0.5,
        steady_stop=false,
    )
    first = GraphRecoveryAPI.grid_patch_recovery_demo(; options...)
    second = GraphRecoveryAPI.grid_patch_recovery_demo(; options...)
    experiment = first.experiment

    @test experiment.connected_component_count == 1
    @test experiment.severed_component_count == 2
    @test sort([length(reference.nodes) for reference in experiment.references]) == [1, 5]
    @test experiment.immediate_feasibility.factorized_best.profile_relative_rmse <=
        experiment.immediate_feasibility.global_best.profile_relative_rmse +
        10 * eps(Float64)
    for run in (
        experiment.fixed,
        experiment.global_feedback,
        experiment.componentwise_feedback,
    )
        @test 1 <= run.iterations <= options.max_iterations
        @test all(
            options.exponent_min <= exponent <= options.exponent_max
            for exponent in run.final_exponents
        )
        @test all(action in (-1, 0, 1) for entry in run.trace for action in entry.actions)
    end
    @test second.settled_reference_A == first.settled_reference_A
    @test second.settled_reference_I == first.settled_reference_I
    @test second.experiment.immediate_feasibility.factorized_best.exponents ==
        experiment.immediate_feasibility.factorized_best.exponents
    @test [entry.actions for entry in second.experiment.componentwise_feedback.trace] ==
        [entry.actions for entry in experiment.componentwise_feedback.trace]
end
