using PolyMorphogenesis
using Test

@testset "wiring change shifts the settled RD attractor" begin
    result = wiring_bistability_demo(n_cells=100, seed=0)
    @test result[:connected][:peak_count] == 1
    @test result[:connected][:shape] == "LH"
    @test result[:severed][:peak_count] == 2
    @test result[:severed][:shape] == "LHLH"
end

@testset "wiring intervention order prefers central cuts" begin
    @test cut_connectivity_loss(10, 5) == 25
    @test cut_connectivity_loss(10, 4) == 24
    @test wiring_intervention_order(10)[1:5] == [5, 4, 6, 3, 7]
end

@testset "cut factorization matches severed-chain simulation" begin
    sweep = wiring_cut_sweep_demo(
        n_cells=12,
        seed=0,
        cut_count=1,
        candidate_cutsets=[Int[6]],
        validate_cutsets=[Int[6]],
    )
    validation = sweep[:validation]
    @test validation !== nothing
    @test validation[:max_profile_linf_error] ≤ 1.0e-8
    @test validation[:max_peak_count_error] == 0
    @test validation[:cases][1][:shape_match]
end

@testset "candidate cutsets are normalized, deduplicated, and auto-validated" begin
    sweep = wiring_cut_sweep_demo(
        n_cells=12,
        seed=0,
        cut_count=2,
        candidate_cutsets=[Int[6, 3], Int[3, 6], Int[4, 8]],
    )
    @test sweep[:candidate_count] == 2
    @test [entry[:cuts] for entry in sweep[:cuts]] == [Int[3, 6], Int[4, 8]]
    @test sweep[:validation_scope][:validated_cutset_count] == 2
    @test sweep[:validation_scope][:all_candidates_validated]
    @test_throws ErrorException wiring_cut_sweep_demo(
        n_cells=12,
        seed=0,
        cut_count=1,
        candidate_cutsets=[Int[3, 6]],
    )
end

@testset "fragment family isolates fixed-size middle segments" begin
    result = wiring_fragment_family_demo(
        n_cells=20,
        seed=0,
        fragment_size=5,
        left_cuts=[5, 10],
        validation_mode=:all,
    )
    @test result[:candidate_count] == 2
    @test result[:fragment_size] == 5
    @test result[:left_cuts] == [5, 10]
    @test all(entry[:cut_count] == 2 for entry in result[:cuts])
    @test all(entry[:segment_lengths][2] == 5 for entry in result[:cuts])
    @test result[:validation_scope][:all_candidates_validated]
    @test_throws ErrorException wiring_fragment_family_demo(n_cells=20, fragment_size=19)
end

@testset "wiring K compares connectivity and decomposition policies" begin
    result = wiring_intervention_k_demo(
        n_cells=12,
        seed=0,
        trials=2,
        cut_count=1,
        target_peak_count=2,
        candidate_cutsets=[Int[3], Int[6], Int[9]],
        validate_cutsets=[Int[6]],
    )
    @test result[:derived][:candidate_count] == 3
    @test haskey(result[:comparison], :connectivity_loss_vs_blind)
    @test haskey(result[:comparison], :decomposition_severity_vs_blind)
    @test length(result[:ranking_connectivity]) == 3
    @test length(result[:ranking_decomposition]) == 3
    @test result[:validation][:max_profile_linf_error] ≤ 1.0e-8
end

@testset "double-cut severity can disagree with connectivity ranking" begin
    result = wiring_cut_sweep_demo(
        n_cells=20,
        seed=0,
        cut_count=2,
        candidate_cutsets=[Int[5, 10], Int[5, 15], Int[8, 12], Int[7, 14]],
        validate_cutsets=[Int[5, 15]],
    )
    @test result[:ranking_connectivity][1][:cuts] == [7, 14]
    @test result[:ranking_decomposition][1][:cuts] == [5, 15]
    @test result[:ranking_connectivity][1][:cut_connectivity_loss] > result[:ranking_decomposition][1][:cut_connectivity_loss]
    @test result[:ranking_decomposition][1][:severity_score] > result[:ranking_connectivity][1][:severity_score]
    @test result[:validation][:max_profile_linf_error] ≤ 1.0e-8
end

@testset "wiring K can target top-severity cuts" begin
    result = wiring_intervention_k_demo(
        n_cells=20,
        seed=0,
        trials=1,
        cut_count=1,
        target_top_k=1,
        candidate_cutsets=[Int[10], Int[13], Int[16]],
        validate_cutsets=[Int[10]],
    )
    @test result[:derived][:target_top_k] == 1
    @test result[:derived][:candidate_count] == 3
    @test result[:ranking_connectivity][1][:cut] == 10
    @test result[:ranking_decomposition][1][:cut] == 16
    @test result[:trials][1][:cost_connectivity] == 3.0
    @test result[:trials][1][:cost_decomposition] == 1.0
    @test result[:trials][1][:first_success_connectivity] == [16]
    @test result[:trials][1][:first_success_decomposition] == [16]
    @test result[:validation][:max_profile_linf_error] ≤ 1.0e-8
end

@testset "worst cut changes across D_a regimes" begin
    result = wiring_severity_phase_scan_demo(
        n_cells=30,
        seed=0,
        D_a_values=[7.5, 8.5, 9.849732675807608],
        candidate_cutsets=[Int[4], Int[24], Int[25]],
        validation_mode=:none,
    )
    @test [entry[:D_a] for entry in result[:scan]] == [7.5, 8.5, 9.849732675807608]
    @test result[:scan][1][:best_decomposition][:cuts] == [4]
    @test result[:scan][2][:best_decomposition][:cuts] == [25]
    @test result[:scan][3][:best_decomposition][:cuts] == [24]
    @test result[:scan][1][:best_decomposition][:shape] == "HLH"
    @test all(entry[:candidate_count] == 3 for entry in result[:scan])
    @test length(result[:regime_changes]) == 2
end
