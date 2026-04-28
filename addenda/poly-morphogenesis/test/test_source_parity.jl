using PolyMorphogenesis
using Test

function _documented_spread_lh_shape(n_cells::Int, field_length::Float64)
    config = RDChainConfig(n_cells=n_cells, field_length=field_length, seed=0)
    state = zeros(2 * n_cells)
    spread_pattern!(state, "LH"; A_template=[0.0, 0.5, 1.0], I_template=nothing)
    settle_rd_source!(state, RDParameters(), config; steady_stop=false)
    return PolyMorphogenesis.RD.shape_string(@view state[1:n_cells])
end

function _documented_linear_spread_shape(n_cells::Int, field_length::Float64)
    config = RDChainConfig(n_cells=n_cells, field_length=field_length, seed=0)
    state = zeros(2 * n_cells)
    linear_spread!(state)
    preseed_lxh!(state)
    settle_rd_source!(state, RDParameters(), config; steady_stop=false)
    return PolyMorphogenesis.RD.shape_string(@view state[1:n_cells])
end

function _documented_stick_shape(seed_shape::AbstractString, n_cells::Int, field_length::Float64)
    config = RDChainConfig(n_cells=n_cells, field_length=field_length, seed=0)
    state = zeros(2 * n_cells)
    spread_pattern!(state, seed_shape)
    settle_rd_source!(state, RDParameters(), config; steady_stop=false)
    return PolyMorphogenesis.RD.shape_string(@view state[1:n_cells])
end

function _wave_result_from_head_species(species_idx::Union{Nothing,Int}; n_cells::Int=4, n_species::Int=6, threshold::Float64=0.6)
    pre = zeros(n_species, n_cells)
    if !isnothing(species_idx)
        pre[species_idx, end] = threshold + 0.1
    end
    sig = zeros(n_species, n_cells)
    amdr = zeros(n_cells)
    return PolyMorphogenesis.Wave._wave_result(zeros(n_cells), zeros(n_cells), pre, sig, amdr, trues(n_cells), threshold)
end

@testset "documented BITSEY spread(\"LH\") RD outcomes" begin
    # These expectations come from upstream RD_0readme's run_werner1() table.
    cases = [
        (50, 10.0, "LH"),
        (50, 15.0, "LHL"),
        (100, 20.0, "LHLH"),
        (100, 25.0, "LHLH"),
        (100, 30.0, "LHLHLH"),
        (100, 35.0, "LHLHLH"),
        (100, 40.0, "LHLHLH"),
        (100, 45.0, "LHLHLHLH"),
        (100, 50.0, "LHLHLHLH"),
    ]

    for (n_cells, field_length, expected_shape) in cases
        @test _documented_spread_lh_shape(n_cells, field_length) == expected_shape
    end
end

@testset "documented BITSEY linear-spread RD outcomes" begin
    # These expectations follow the fetched executable BITSEY source path
    # (setup_werner1 + linear_spread + set_preseed_LXH + sim.sim(300)).
    # RD_0readme's prose summary undercounts the L=40 and L=50 cases.
    cases = [
        (50, 10.0, "LH"),
        (50, 15.0, "LHL"),
        (100, 20.0, "LHLH"),
        (100, 25.0, "LHLH"),
        (100, 30.0, "LHLHLH"),
        (100, 35.0, "LHLHLH"),
        (100, 40.0, "LHLHLHLH"),
        (100, 45.0, "LHLHLHLH"),
        (100, 50.0, "LHLHLHLHLH"),
    ]

    for (n_cells, field_length, expected_shape) in cases
        @test _documented_linear_spread_shape(n_cells, field_length) == expected_shape
    end
end

@testset "documented BITSEY what-sticks cases remain stable under source seeding" begin
    cases = [
        ("LHLH", 50, 15.0, "LHLH"),
        ("LHLHL", 100, 20.0, "LHLHL"),
        ("LHLHLH", 100, 25.0, "LHLHLH"),
        ("LHLHLHLH", 100, 35.0, "LHLHLHLH"),
        ("LHLHLHLHLH", 100, 45.0, "LHLHLHLHLH"),
    ]

    for (seed_shape, n_cells, field_length, expected_shape) in cases
        @test _documented_stick_shape(seed_shape, n_cells, field_length) == expected_shape
    end
end

@testset "wave readout matches source GRN_N_peaks convention" begin
    @test _wave_result_from_head_species(nothing).count == 0.0
    @test _wave_result_from_head_species(2).count == 1.0
    @test _wave_result_from_head_species(3).count == 1.5
    @test _wave_result_from_head_species(4).count == 2.0
end
