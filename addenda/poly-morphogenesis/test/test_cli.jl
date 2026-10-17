using PolyMorphogenesis
using JSON3
using Test

function _capture_error(f)
    try
        f()
        return nothing
    catch err
        return sprint(showerror, err)
    end
end

function _capture_stdout(f)
    path, io = mktemp()
    try
        redirect_stdout(io) do
            f()
        end
        flush(io)
        seekstart(io)
        return read(io, String)
    finally
        close(io)
        rm(path; force=true)
    end
end

@testset "cli main smoke" begin
    tempdir = mktempdir()
    redirect_stdout(devnull) do
        @test isnothing(main(["demo", "wave-count", "--peaks", "3"]))
        @test isnothing(main(["diagrams", "--base-dir", tempdir, "--n-cells", "4"]))
    end
    @test isfile(joinpath(tempdir, "docs", "diagrams", "rd_default.dot"))
    @test isfile(joinpath(tempdir, "docs", "diagrams", "wave_default.dot"))
end

@testset "grid patch recovery cli JSON contract" begin
    output = _capture_stdout() do
        @test isnothing(main([
            "demo",
            "grid-patch-recovery",
            "--rows",
            "2",
            "--cols",
            "3",
            "--patch-top",
            "1",
            "--patch-left",
            "2",
            "--patch-rows",
            "1",
            "--patch-cols",
            "1",
            "--seed",
            "7",
            "--d-a",
            "1.0",
            "--d-i",
            "30.0",
            "--exponent-min",
            "0",
            "--exponent-max",
            "0",
            "--step-factor",
            "1.21",
            "--max-iterations",
            "1",
            "--active-fraction",
            "0.5",
            "--meaningful-improvement",
            "0.25",
            "--settle-time",
            "0.1",
            "--steady-tol",
            "0.0001",
            "--steady-stop",
            "false",
            "--evidence-scope",
            "smoke_contract",
        ]))
    end

    payload = JSON3.read(output)
    @test payload.schema_version == 2
    @test payload.rows == 2
    @test payload.cols == 3
    @test payload.experiment.schema_version == 2
    @test startswith(String(payload.experiment.julia_version), "1.11")
    @test collect(payload.experiment.exponent_bounds) == [0, 0]
    @test payload.experiment.step_factor == 1.21
    @test payload.experiment.steady_tol == 0.0001
    @test payload.experiment.meaningful_improvement_threshold == 0.25
    @test payload.experiment.evidence_scope == "smoke_contract"
    @test !payload.experiment.all_evaluations_at_equilibrium
    @test payload.experiment.matched_feedback_initialization
    @test hasproperty(payload.experiment, :immediate_feasibility)
    @test hasproperty(payload.experiment, :delayed_feasibility)
    @test hasproperty(
        payload.experiment.immediate_feasibility,
        :global_count_constrained_best,
    )
    @test hasproperty(
        payload.experiment.immediate_feasibility,
        :count_constrained_relative_loss_reduction,
    )
    @test payload.experiment.fixed.policy == "fixed"
    @test payload.experiment.global_feedback.policy == "global_feedback"
    @test payload.experiment.componentwise_feedback.policy == "componentwise_feedback"
    @test hasproperty(payload.experiment.fixed, :final_evaluation)
    @test hasproperty(payload.experiment.global_feedback, :trace)
    @test hasproperty(payload.experiment.componentwise_feedback, :trace)
end

@testset "grid patch recovery cohort cli artifacts" begin
    output_dir = mktempdir()
    output = _capture_stdout() do
        @test isnothing(main([
            "demo",
            "grid-patch-recovery-cohort",
            "--cohort-id",
            "cli-smoke",
            "--output-dir",
            output_dir,
            "--seeds",
            "7",
            "--regime-id",
            "tiny-grid",
            "--rows",
            "1",
            "--cols",
            "2",
            "--patch-rows",
            "1",
            "--patch-cols",
            "1",
            "--patch-top",
            "1",
            "--patch-left",
            "1",
            "--d-a",
            "1.0",
            "--d-i",
            "30.0",
            "--step-factor",
            "1.21",
            "--max-iterations",
            "1",
            "--active-fraction",
            "0.5",
            "--meaningful-improvement",
            "0.2",
            "--max-count-selection-regret",
            "0.1",
            "--settle-time",
            "0.1",
            "--steady-stop",
            "false",
            "--evidence-scope",
            "cli_smoke",
        ]))
    end

    descriptor = JSON3.read(output)
    @test descriptor.schema_version == 1
    @test descriptor.cohort_id == "cli-smoke"
    @test descriptor.protocol_manifest.path == joinpath(output_dir, "recovery-protocol.json")
    @test length(String(descriptor.protocol_manifest.sha256)) == 64
    @test descriptor.outcome_artifacts.cases_path == joinpath(output_dir, "recovery-cases.jsonl")
    @test descriptor.outcome_artifacts.summary_path == joinpath(output_dir, "recovery-summary.json")
    @test descriptor.outcome_artifacts.manifest_path == joinpath(output_dir, "recovery-manifest.json")

    for path in (
        descriptor.protocol_manifest.path,
        descriptor.outcome_artifacts.cases_path,
        descriptor.outcome_artifacts.summary_path,
        descriptor.outcome_artifacts.manifest_path,
    )
        @test isfile(String(path))
    end

    protocol = JSON3.read(read(joinpath(output_dir, "recovery-protocol.json"), String))
    @test protocol.expected_case_count == 1
    @test collect(protocol.seeds) == [7]
    @test protocol.protocol.recovery.exponent_min == -11
    @test protocol.protocol.recovery.exponent_max == 11
    @test protocol.protocol.steady_tol == 1.0e-6
    @test !protocol.protocol.recovery.include_delayed_capacity
    @test !protocol.protocol.recovery.include_feedback

    case_lines = filter(!isempty, split(read(joinpath(output_dir, "recovery-cases.jsonl"), String), '\n'))
    @test length(case_lines) == 1
    case = JSON3.read(only(case_lines))
    @test case.case_id == "cli-smoke__tiny-grid__seed-0000000007__top-01__left-01"
    @test case.evidence_scope == "cli_smoke"
    @test isnothing(case.delayed_capacity_at_equilibrium)
    @test isnothing(case.feedback_at_equilibrium)
    @test isnothing(case.delayed_outcome_class)
    @test isnothing(case.global_feedback_final_exponents)
    @test isnothing(case.componentwise_feedback_final_exponents)
end

@testset "grid patch recovery development cli is guarded and one-shot" begin
    output_dir = mktempdir()
    args = [
        "demo",
        "grid-patch-recovery-development",
        "--development-id",
        "cli-development-smoke",
        "--output-dir",
        output_dir,
        "--seeds",
        "7",
        "--regime-id",
        "tiny-development-grid",
        "--rows",
        "1",
        "--cols",
        "2",
        "--patch-rows",
        "1",
        "--patch-cols",
        "1",
        "--patch-top",
        "1",
        "--patch-left",
        "1",
        "--settle-chunk-time",
        "0.01",
        "--settle-max-time",
        "0.02",
        "--steady-tol",
        "1000000.0",
        "--exponent-min",
        "0",
        "--exponent-max",
        "0",
        "--exponent-hard-min",
        "-1",
        "--exponent-hard-max",
        "1",
        "--exponent-expansion-step",
        "1",
        "--exponent-plateau-relative-tol",
        "0.0",
        "--exponent-plateau-patience",
        "2",
        "--alias-resolutions",
        "0.001",
    ]
    output = _capture_stdout() do
        @test isnothing(main(args))
    end
    descriptor = JSON3.read(output)
    @test descriptor.schema_version == 1
    @test descriptor.protocol_version == 2
    @test descriptor.development_id == "cli-development-smoke"
    @test descriptor.summary.registered_case_count == 1
    @test descriptor.summary.completed_case_count == 0
    @test descriptor.summary.failed_case_count == 1
    @test descriptor.summary.unresolved_boundary_case_count == 1
    @test descriptor.summary.numerical_readiness_rate_registered == 0.0
    for name in (
        "development-protocol.json",
        "response-surfaces.jsonl",
        "observability-cases.jsonl",
        "observability-summary.json",
        "development-manifest.json",
    )
        @test isfile(joinpath(output_dir, name))
    end
    protocol = JSON3.read(read(joinpath(output_dir, "development-protocol.json"), String))
    @test protocol.protocol_version == 2
    @test protocol.evidence_scope == "development_only"
    @test collect(protocol.seeds) == [7]
    @test !hasproperty(protocol.protocol, :include_delayed_capacity)
    @test !hasproperty(protocol.protocol, :include_feedback)

    replay_error = _capture_error() do
        main(args)
    end
    @test !isnothing(replay_error)
    @test occursin("refusing to recompute a frozen development run", replay_error)

    partial_dir = mktempdir()
    write(joinpath(partial_dir, "response-surfaces.jsonl"), "partial-marker\n")
    partial_args = copy(args)
    output_index = findfirst(==("--output-dir"), partial_args)
    partial_args[output_index + 1] = partial_dir
    partial_error = _capture_error() do
        main(partial_args)
    end
    @test !isnothing(partial_error)
    @test occursin("refusing to recompute a frozen development run", partial_error)
    @test !ispath(joinpath(partial_dir, "development-protocol.json"))

    reserved_args = copy(args)
    reserved_args[findfirst(==("7"), reserved_args)] = "200"
    reserved_args[findfirst(==(output_dir), reserved_args)] = mktempdir()
    reserved_error = _capture_error() do
        main(reserved_args)
    end
    @test !isnothing(reserved_error)
    @test occursin("reserved Holdout A/B seeds", reserved_error)
end

@testset "cli missing or invalid flag values" begin
    err = _capture_error() do
        main(["demo", "wave-count", "--peaks"])
    end
    @test !isnothing(err)
    @test occursin("missing value for `--peaks`", err)

    err = _capture_error() do
        main(["demo", "fragment-family", "--left-cuts"])
    end
    @test !isnothing(err)
    @test occursin("missing value for `--left-cuts`", err)

    err = _capture_error() do
        main(["demo", "cut-sweep", "--validation-mode", "bad"])
    end
    @test !isnothing(err)
    @test occursin("validation mode must be one of none, auto, all", err)

    err = _capture_error() do
        main(["demo", "grid-patch-sweep", "--patch-sizes", "bad"])
    end
    @test !isnothing(err)
    @test occursin("expected patch sizes formatted as HxW,HxW,...", err)

    err = _capture_error() do
        main(["demo", "grid-patch-sensitivity", "--metrics", "bad"])
    end
    @test !isnothing(err)
    @test occursin("expected metrics drawn from balanced, structure, profile", err)

    err = _capture_error() do
        main(["demo", "grid-patch-threshold-sensitivity", "--active-fractions", ""])
    end
    @test !isnothing(err)
    @test occursin("expected at least one float", err)
end
