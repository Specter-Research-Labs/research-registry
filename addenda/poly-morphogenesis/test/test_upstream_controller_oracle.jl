using JSON3
using PolyMorphogenesis
using Test

_repo_root() = normpath(joinpath(@__DIR__, "..", "..", ".."))

function _oracle_python()
    haskey(ENV, "POLY_ORACLE_PYTHON") && return ENV["POLY_ORACLE_PYTHON"]
    candidate = joinpath(_repo_root(), ".venv", "bin", "python3")
    return isfile(candidate) ? candidate : nothing
end

function _run_upstream_controller_oracle(; n_cells::Int, goal_peaks::Int, n_peaks_max::Int, max_loops::Int)
    python = _oracle_python()
    isnothing(python) && error("missing oracle python interpreter at $(joinpath(_repo_root(), ".venv", "bin", "python3"))")
    script = joinpath(@__DIR__, "upstream_controller_trace.py")
    cmd = Cmd([
        python,
        script,
        "--n-cells",
        string(n_cells),
        "--goal-peaks",
        string(goal_peaks),
        "--n-peaks-max",
        string(n_peaks_max),
        "--max-loops",
        string(max_loops),
    ])
    cmd = Cmd(cmd; dir=_repo_root())
    return JSON3.read(read(cmd, String))
end

_floatvec(values) = Float64[Float64(value) for value in values]
_intvec(values) = Int[Int(value) for value in values]
_max_abs_diff(xs, ys) = maximum(abs.(xs .- ys))

function _assert_controller_trace_entry(py, jl)
    @test jl[:loop_index] == Int(py.loop_index)
    @test jl[:previous_peak_count] ≈ Float64(py.previous_peak_count) atol=1.0e-12
    @test String(jl[:controller_action]) == String(py.controller_action)
    @test jl[:linear_spread_applied] == Bool(py.linear_spread_applied)
    @test jl[:source_D_a] ≈ Float64(py.D_a) rtol=1.0e-12 atol=1.0e-18
    @test jl[:source_D_i] ≈ Float64(py.D_i) rtol=1.0e-12 atol=1.0e-18
    @test jl[:rd_pre_decay] ≈ Float64(py.rd_pre_decay) atol=1.0e-12
    @test jl[:grn_pre_decay] ≈ Float64(py.grn_pre_decay) atol=1.0e-12
    @test jl[:rd_duration] ≈ Float64(py.rd_duration) atol=1.0e-12
    @test jl[:grn_duration] ≈ Float64(py.grn_duration) atol=1.0e-12
    @test jl[:seed_pre0l] ≈ Float64(py.seed_pre0l) atol=1.0e-12
    @test jl[:shape] == String(py.shape_after_rd)
    @test jl[:highest_pre_on] == (isnothing(py.highest_pre_on) ? nothing : Int(py.highest_pre_on))
    @test jl[:source_should_continue] == Bool(py.source_should_continue)
    @test jl[:n_peaks] ≈ Float64(py.n_peaks) atol=1.0e-12
    @test jl[:active_pre_indices] == _intvec(py.active_pre_indices)

    @test _max_abs_diff(_floatvec(py.rd_A_profile), jl[:rd_A_profile]) <= 1.0e-5
    @test _max_abs_diff(_floatvec(py.rd_I_profile), jl[:rd_I_profile]) <= 1.0e-5
    @test _max_abs_diff(_floatvec(py.head_pre), jl[:head_pre]) <= 1.0e-6
end

@testset "upstream controller oracle" begin
    cases = [
        (goal_peaks=1, max_loops=1, expected_actions=["decrease"]),
        (goal_peaks=0, max_loops=2, expected_actions=["decrease", "increase"]),
    ]

    for case in cases
        oracle = _run_upstream_controller_oracle(
            n_cells=2,
            goal_peaks=case.goal_peaks,
            n_peaks_max=1,
            max_loops=case.max_loops,
        )
        config = ClosedLoopConfig(
            n_cells=2,
            target_peaks=case.goal_peaks,
            min_iterations=1,
            max_iterations=case.max_loops,
            seed=0,
            wave=WaveConfig(n_peaks_max=1),
        )
        result = closed_loop(config; stop_on_target=false)

        @test length(result[:history]) == length(oracle.history) == case.max_loops
        @test [String(entry[:controller_action]) for entry in result[:history]] == case.expected_actions

        for idx in 1:case.max_loops
            _assert_controller_trace_entry(oracle.history[idx], result[:history][idx])
        end
    end
end
