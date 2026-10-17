module CLI

using JSON3

using ..RD: RDParameters
using ..Controller: closed_loop_demo,
    rd_pattern_demo,
    wave_count_demo
using ..Diagrams: save_diagrams
using ..GridLesions: grid_patch_isolation_demo,
    grid_patch_metric_sensitivity_demo,
    grid_patch_threshold_sensitivity_demo,
    grid_patch_sweep_demo
using ..GraphRecovery: GraphRecoveryConfig, grid_patch_recovery_demo
using ..RecoveryCohort: RecoveryCohortSpec,
    RecoveryPlacement,
    RecoveryProtocol,
    RecoveryRegime,
    run_recovery_cohort,
    write_recovery_cohort_artifacts,
    write_recovery_cohort_protocol_manifest
using ..RecoveryAdaptive: AdaptiveExponentProtocol,
    AdaptiveSettlingProtocol
using ..RecoveryDevelopment: RecoveryDevelopmentProtocol,
    RecoveryDevelopmentSpec,
    run_recovery_development,
    write_recovery_development_artifacts,
    write_recovery_development_protocol
using ..Wiring: FragmentFamilyResult,
    InterventionKResult,
    PairedTrialSummary,
    REFERENCE_ONE_HEAD_D_A_100,
    wiring_bistability_demo,
    wiring_cut_sweep_demo,
    wiring_fragment_family_demo,
    wiring_intervention_k_demo,
    wiring_severity_phase_scan_demo

export main

const _TOP_LEVEL_HELP = """
PolyMorphogenesis CLI

Usage:
  main(["--help"])
  main(["diagrams", [--base-dir DIR], [--n-cells N]])
  main(["demo", <subcommand>, ...])

Commands:
  diagrams        Emit Graphviz diagrams for the requested tissue size.
  demo            Run one of the demo workflows below.
"""

const _DEMO_HELP = """
PolyMorphogenesis demo commands

Usage:
  main(["demo", <subcommand>, ...])

Subcommands:
  rd-pattern      Settle RD once and return the resulting morphology.
  wave-count      Run the wave counter on a synthetic profile.
  closed-loop     Run the iterative closed-loop controller.
  bistability     Compare connected and severed RD wiring.
  cut-sweep       Evaluate candidate cutsets at fixed diffusion.
  fragment-family Isolate a contiguous fragment with two cuts.
  grid-patch      Isolate a rectangular patch in a 2D grid by severing its boundary edges.
  grid-patch-recovery Settle a 2D grid, sever a patch, and compare shared and componentwise recovery.
  grid-patch-recovery-cohort Run a deterministic rectangular-lesion cohort and write evidence artifacts.
  grid-patch-recovery-development Run the guarded Protocol V2 adaptive/readout development cohort.
  grid-patch-sensitivity Compare alternative 2D severity metrics on one rectangular-patch regime.
  grid-patch-threshold-sensitivity Compare 2D severity rankings across active-mask thresholds.
  grid-patch-sweep Scan 2D rectangular patch lesions across patch sizes and diffusion parameters.
  severity-scan   Scan the decomposition-ranked severity across D_a values.
  wiring-k        Compare cut-ordering policies on an intervention search.
"""

const _DEMO_SUBCOMMAND_HELP = Dict{String,String}(
    "rd-pattern" => """
Usage:
  main(["demo", "rd-pattern", [--n-cells N], [--seed S]])
""",
    "wave-count" => """
Usage:
  main(["demo", "wave-count", [--peaks N], [--cells-per-peak N]])
""",
    "closed-loop" => """
Usage:
  main(["demo", "closed-loop", [--n-cells N], [--target-peaks N], [--seed S]])
""",
    "bistability" => """
Usage:
  main(["demo", "bistability", [--n-cells N], [--seed S], [--cut K], [--d-a D]])
""",
    "cut-sweep" => """
Usage:
  main(["demo", "cut-sweep", [--n-cells N], [--seed S], [--d-a D], [--cut-count K]])
""",
    "fragment-family" => """
Usage:
  main(["demo", "fragment-family", [--n-cells N], [--seed S], [--d-a D], [--fragment-size N], [--left-cuts K1,K2,...]])
""",
    "grid-patch" => """
Usage:
  main(["demo", "grid-patch", [--rows N], [--cols N], [--patch-rows N], [--patch-cols N], [--seed S], [--d-a D], [--d-i D], [--validate yes|no]])
""",
    "grid-patch-recovery" => """
Usage:
  main(["demo", "grid-patch-recovery", [--rows N], [--cols N], [--patch-top N], [--patch-left N], [--patch-rows N], [--patch-cols N], [--seed S], [--d-a D], [--d-i D], [--exponent-min K], [--exponent-max K], [--step-factor F], [--max-iterations N], [--active-fraction F], [--meaningful-improvement F], [--max-count-selection-regret F], [--settle-time T], [--steady-tol T], [--steady-stop yes|no], [--include-delayed-capacity yes|no], [--include-feedback yes|no], [--evidence-scope LABEL]])
""",
    "grid-patch-recovery-cohort" => """
Usage:
  main(["demo", "grid-patch-recovery-cohort", [--cohort-id ID], [--output-dir DIR], [--seeds S1,S2,...], [--regime-id ID], [--rows N], [--cols N], [--patch-rows N], [--patch-cols N], [--patch-top N], [--patch-left N], [--d-a D], [--d-i D], [--exponent-min K], [--exponent-max K], [--step-factor F], [--max-iterations N], [--active-fraction F], [--meaningful-improvement F], [--max-count-selection-regret F], [--settle-time T], [--steady-tol T], [--steady-stop yes|no], [--include-delayed-capacity yes|no], [--include-feedback yes|no], [--evidence-scope LABEL]])

By default the cohort enumerates every valid rectangular placement and runs the
capacity-only protocol (delayed capacity and feedback disabled). Provide both
--patch-top and --patch-left to restrict a smoke run to one placement.
""",
    "grid-patch-recovery-development" => """
Usage:
  main(["demo", "grid-patch-recovery-development", [--development-id ID], [--output-dir DIR], [--seeds S1,S2,...], [--regime-id ID], [--rows N], [--cols N], [--patch-rows N], [--patch-cols N], [--patch-top N], [--patch-left N], [--d-a D], [--d-i D], [--settle-chunk-time T], [--settle-max-time T], [--steady-tol T], [--exponent-min K], [--exponent-max K], [--exponent-hard-min K], [--exponent-hard-max K], [--exponent-expansion-step N], [--exponent-plateau-relative-tol T], [--exponent-plateau-patience N], [--step-factor F], [--active-fraction F], [--max-count-selection-regret F], [--alias-resolutions R1,R2,...]])

This command is development-only. It rejects reserved Holdout A/B seeds and
paths, has no delayed-capacity or feedback-controller mode, and refuses to
recompute a run after any outcome artifact exists.
""",
    "grid-patch-sensitivity" => """
Usage:
  main(["demo", "grid-patch-sensitivity", [--rows N], [--cols N], [--patch-rows N], [--patch-cols N], [--seed S], [--d-a D], [--d-i D], [--metrics M1,M2,...]])
""",
    "grid-patch-threshold-sensitivity" => """
Usage:
  main(["demo", "grid-patch-threshold-sensitivity", [--rows N], [--cols N], [--patch-rows N], [--patch-cols N], [--seed S], [--d-a D], [--d-i D], [--active-fractions F1,F2,...], [--metrics M1,M2,...]])
""",
    "grid-patch-sweep" => """
Usage:
  main(["demo", "grid-patch-sweep", [--rows N], [--cols N], [--patch-sizes HxW,HxW,...], [--seed S], [--d-a-values D1,D2,...], [--d-i-values D1,D2,...]])
""",
    "severity-scan" => """
Usage:
  main(["demo", "severity-scan", [--n-cells N], [--seed S], [--cut-count K], [--top-k K], [--d-a-values D1,D2,...]])
""",
    "wiring-k" => """
Usage:
  main(["demo", "wiring-k", [--n-cells N], [--seed S], [--d-a D], [--trials N], [--cut-count K], [--target-peaks N], [--target-top-k K], [--target-shape SHAPE]])
""",
)

const _DIAGRAMS_HELP = """
Usage:
  main(["diagrams", [--base-dir DIR], [--n-cells N]])
"""

struct FlagSpec
    name::Symbol
    flag::String
    parse_value::Function
    default_value::Function
end

struct CommandSpec
    help::String
    flags::Vector{FlagSpec}
    run::Function
end

_default_fn(default) = default isa Function ? default : (_ -> default)

_flag_spec(name::Symbol, flag::String, parser::Function, default) = FlagSpec(name, flag, parser, _default_fn(default))

_int_flag(name::Symbol, flag::String, default) = _flag_spec(name, flag, value -> parse(Int, value), default)
_float_flag(name::Symbol, flag::String, default) = _flag_spec(name, flag, value -> parse(Float64, value), default)
_string_flag(name::Symbol, flag::String, default) = _flag_spec(name, flag, identity, default)
_bool_flag(name::Symbol, flag::String, default) = _flag_spec(
    name,
    flag,
    value -> begin
        lowered = lowercase(value)
        lowered in ("true", "yes", "1") && return true
        lowered in ("false", "no", "0") && return false
        error("expected boolean value for `$flag`")
    end,
    default,
)
_symbol_flag(name::Symbol, flag::String, default, allowed::Tuple{Vararg{Symbol}}) = _flag_spec(
    name,
    flag,
    value -> begin
        parsed = Symbol(value)
        parsed in allowed || error("validation mode must be one of none, auto, all")
        parsed
    end,
    default,
)

function _list_parser(parse_value::Function, label::String)
    return value -> begin
        parsed = [parse_value(strip(part)) for part in split(value, ",") if !isempty(strip(part))]
        isempty(parsed) && error("expected at least one $label")
        return parsed
    end
end

function _cutset_family_parser(value::String)
    cutsets = Vector{Vector{Int}}()
    for raw_cutset in split(value, ";")
        parts = [strip(part) for part in split(raw_cutset, ",") if !isempty(strip(part))]
        isempty(parts) && continue
        push!(cutsets, [parse(Int, part) for part in parts])
    end
    isempty(cutsets) && error("expected at least one cutset")
    return cutsets
end

function _patch_sizes_parser(value::String)
    patch_sizes = Tuple{Int,Int}[]
    for raw_size in split(value, ",")
        token = strip(raw_size)
        isempty(token) && continue
        parts = split(lowercase(token), "x")
        length(parts) == 2 || error("expected patch sizes formatted as HxW,HxW,...")
        push!(patch_sizes, (parse(Int, strip(parts[1])), parse(Int, strip(parts[2]))))
    end
    isempty(patch_sizes) && error("expected at least one patch size")
    return patch_sizes
end

function _metrics_parser(value::String)
    allowed = Set((:balanced, :structure, :profile))
    metrics = Symbol[]
    for raw_metric in split(value, ",")
        token = Symbol(strip(raw_metric))
        isempty(String(token)) && continue
        token in allowed || error("expected metrics drawn from balanced, structure, profile")
        push!(metrics, token)
    end
    isempty(metrics) && error("expected at least one metric")
    return metrics
end

_int_list_flag(name::Symbol, flag::String, default) = _flag_spec(name, flag, _list_parser(x -> parse(Int, x), "integer"), default)
_float_list_flag(name::Symbol, flag::String, default) = _flag_spec(name, flag, _list_parser(x -> parse(Float64, x), "float"), default)
_cutset_family_flag(name::Symbol, flag::String, default) = _flag_spec(name, flag, _cutset_family_parser, default)
_patch_sizes_flag(name::Symbol, flag::String, default) = _flag_spec(name, flag, _patch_sizes_parser, default)
_metrics_flag(name::Symbol, flag::String, default) = _flag_spec(name, flag, _metrics_parser, default)

_is_help_arg(arg::String) = arg == "--help" || arg == "-h"
_has_help(args::Vector{String}) = any(_is_help_arg, args)

function _print_help(text::AbstractString)
    print(text)
    if !endswith(text, "\n")
        println()
    end
end

function _print_top_help()
    _print_help(_TOP_LEVEL_HELP)
end

function _print_demo_help()
    _print_help(_DEMO_HELP)
end

function _print_demo_subcommand_help(subcommand::String)
    _print_help(get(_DEMO_SUBCOMMAND_HELP, subcommand, "Unknown demo subcommand: $subcommand\n"))
end

function _print_diagrams_help()
    _print_help(_DIAGRAMS_HELP)
end

function _parse_flag_pairs(args::Vector{String})
    flags = Dict{String,String}()
    idx = 1
    while idx <= length(args)
        arg = args[idx]
        startswith(arg, "--") || error("unexpected positional argument `$arg`")
        idx == length(args) && error("missing value for `$arg`")
        value = args[idx + 1]
        startswith(value, "--") && error("missing value for `$arg`")
        haskey(flags, arg) && error("duplicate flag `$arg`")
        flags[arg] = value
        idx += 2
    end
    return flags
end

function _parse_options(args::Vector{String}, specs::Vector{FlagSpec})
    flags = _parse_flag_pairs(args)
    allowed = Set(spec.flag for spec in specs)
    for flag in keys(flags)
        flag in allowed || error("unknown flag `$flag`")
    end

    parsed = Dict{Symbol,Any}()
    for spec in specs
        if haskey(flags, spec.flag)
            parsed[spec.name] = spec.parse_value(flags[spec.flag])
        else
            parsed[spec.name] = spec.default_value(parsed)
        end
    end
    return parsed
end

function _jsonable(value)
    data = Dict{Symbol,Any}()
    for name in fieldnames(typeof(value))
        field = getfield(value, name)
        data[name] = _jsonable(field)
    end
    return data
end

_jsonable(value::Nothing) = nothing
_jsonable(value::Bool) = value
_jsonable(value::Number) = value
_jsonable(value::AbstractString) = value
_jsonable(value::Symbol) = String(value)
_jsonable(value::AbstractVector) = [_jsonable(entry) for entry in value]
_jsonable(value::Tuple) = [_jsonable(entry) for entry in value]
_jsonable(value::BitVector) = [Bool(entry) for entry in value]
_jsonable(value::AbstractDict) = Dict(key => _jsonable(val) for (key, val) in value)

function _jsonable(value::PairedTrialSummary)
    return Dict(
        :K => Dict(
            :lower_bound_censored_at_H => value.lower_bound_censored_at_H,
            :conditional_on_both_solved => value.conditional_on_both_solved,
        ),
        :tau => Dict(
            :agent_mean_censored => value.agent_mean_censored,
            :blind_mean_censored => value.blind_mean_censored,
            :agent_mean_both_solved => value.agent_mean_both_solved,
            :blind_mean_both_solved => value.blind_mean_both_solved,
        ),
        :solve_rates => Dict(
            :agent => value.agent_solve_rate,
            :blind => value.blind_solve_rate,
            :both_solved => value.both_solved_rate,
        ),
        :counts => Dict(
            :trials => value.trials,
            :agent_solved => value.agent_solved,
            :blind_solved => value.blind_solved,
            :both_solved => value.both_solved,
        ),
        :notes => value.notes,
    )
end

function _jsonable(value::FragmentFamilyResult)
    payload = _jsonable(value.sweep)
    payload[:family] = value.family
    payload[:fragment_size] = value.fragment_size
    payload[:left_cuts] = _jsonable(value.left_cuts)
    payload[:candidate_cutsets] = _jsonable(value.candidate_cutsets)
    payload[:placements] = _jsonable(value.placements)
    return payload
end

function _jsonable(value::InterventionKResult)
    return Dict(
        :schema_version => value[:schema_version],
        :reference_addendum => value[:reference_addendum],
        :problem_space => _jsonable(value[:problem_space]),
        :policies => _jsonable(value[:policies]),
        :connected => _jsonable(value[:connected]),
        :severity_calibration => _jsonable(value[:severity_calibration]),
        :validation_scope => _jsonable(value[:validation_scope]),
        :ranking_connectivity => _jsonable(value[:ranking_connectivity]),
        :ranking_decomposition => _jsonable(value[:ranking_decomposition]),
        :validation => _jsonable(value[:validation]),
        :comparison => _jsonable(value[:comparison]),
        :trials => _jsonable(value[:trials]),
        :derived => _jsonable(value[:derived]),
        :notes => _jsonable(value[:notes]),
    )
end

function _cohort_placements(options::Dict{Symbol,Any})
    top = options[:patch_top]
    left = options[:patch_left]
    if isnothing(top) && isnothing(left)
        return nothing
    end
    isnothing(top) && error("--patch-top is required when --patch-left is provided")
    isnothing(left) && error("--patch-left is required when --patch-top is provided")
    return [RecoveryPlacement(top, left)]
end

function _run_grid_patch_recovery_cohort(options::Dict{Symbol,Any})
    recovery = GraphRecoveryConfig(
        exponent_min=options[:exponent_min],
        exponent_max=options[:exponent_max],
        step_factor=options[:step_factor],
        active_fraction=options[:active_fraction],
        meaningful_improvement=options[:meaningful_improvement],
        max_count_selection_regret=options[:max_count_selection_regret],
        max_iterations=options[:max_iterations],
        steady_stop=options[:steady_stop],
        include_delayed_capacity=options[:include_delayed_capacity],
        include_feedback=options[:include_feedback],
    )
    regime = RecoveryRegime(
        regime_id=options[:regime_id],
        rows=options[:rows],
        cols=options[:cols],
        patch_rows=options[:patch_rows],
        patch_cols=options[:patch_cols],
        baseline=RDParameters(D_a=options[:D_a], D_i=options[:D_i]),
    )
    protocol = RecoveryProtocol(
        settle_time=options[:settle_time],
        steady_tol=options[:steady_tol],
        recovery=recovery,
        evidence_scope=options[:evidence_scope],
    )
    spec = RecoveryCohortSpec(
        cohort_id=options[:cohort_id],
        regime=regime,
        protocol=protocol,
        seeds=options[:seeds],
        placements=_cohort_placements(options),
    )

    # Freeze the protocol before computing any outcomes.
    protocol_manifest = write_recovery_cohort_protocol_manifest(spec, options[:output_dir])
    result = run_recovery_cohort(spec)
    outcome_artifacts = write_recovery_cohort_artifacts(result, options[:output_dir])
    return (
        schema_version=1,
        cohort_id=result.cohort_id,
        protocol_manifest=protocol_manifest,
        outcome_artifacts=outcome_artifacts,
    )
end

const _DEVELOPMENT_OUTCOME_FILENAMES = (
    "response-surfaces.jsonl",
    "observability-cases.jsonl",
    "observability-summary.json",
    "development-manifest.json",
)

function _require_absent_development_outcomes(output_dir::String)
    existing = [
        name for name in _DEVELOPMENT_OUTCOME_FILENAMES
        if ispath(joinpath(output_dir, name))
    ]
    isempty(existing) || error(
        "refusing to recompute a frozen development run; outcome artifacts already exist: " *
        join(existing, ", ") * ". Use a new --development-id and output directory.",
    )
    return nothing
end

function _run_grid_patch_recovery_development(options::Dict{Symbol,Any})
    protocol = RecoveryDevelopmentProtocol(
        steady_tol=options[:steady_tol],
        settling=AdaptiveSettlingProtocol(
            chunk_time=options[:settle_chunk_time],
            max_time=options[:settle_max_time],
        ),
        exponents=AdaptiveExponentProtocol(
            initial_min=options[:exponent_min],
            initial_max=options[:exponent_max],
            hard_min=options[:exponent_hard_min],
            hard_max=options[:exponent_hard_max],
            expansion_step=options[:exponent_expansion_step],
            plateau_relative_tolerance=options[:exponent_plateau_relative_tol],
            plateau_patience=options[:exponent_plateau_patience],
        ),
        step_factor=options[:step_factor],
        active_fraction=options[:active_fraction],
        max_selection_regret=options[:max_count_selection_regret],
        alias_resolutions=options[:alias_resolutions],
    )
    regime = RecoveryRegime(
        regime_id=options[:regime_id],
        rows=options[:rows],
        cols=options[:cols],
        patch_rows=options[:patch_rows],
        patch_cols=options[:patch_cols],
        baseline=RDParameters(D_a=options[:D_a], D_i=options[:D_i]),
    )
    spec = RecoveryDevelopmentSpec(
        development_id=options[:development_id],
        regime=regime,
        protocol=protocol,
        seeds=options[:seeds],
        placements=_cohort_placements(options),
    )

    # Refuse partial or completed outcome directories before freezing any new file.
    _require_absent_development_outcomes(options[:output_dir])
    protocol_manifest = write_recovery_development_protocol(spec, options[:output_dir])
    result = run_recovery_development(spec)
    artifacts = write_recovery_development_artifacts(result, options[:output_dir])
    return (
        schema_version=1,
        protocol_version=2,
        development_id=result.development_id,
        protocol_manifest=protocol_manifest,
        outcome_artifacts=artifacts,
        summary=result.summary,
    )
end

const _DIAGRAMS_COMMAND = CommandSpec(
    _DIAGRAMS_HELP,
    [
        _string_flag(:base_dir, "--base-dir", _ -> pwd()),
        _int_flag(:n_cells, "--n-cells", 10),
    ],
    options -> save_diagrams(base_dir=options[:base_dir], n_cells=options[:n_cells]),
)

const _DEMO_COMMANDS = Dict{String,CommandSpec}(
    "rd-pattern" => CommandSpec(
        _DEMO_SUBCOMMAND_HELP["rd-pattern"],
        [
            _int_flag(:n_cells, "--n-cells", 100),
            _int_flag(:seed, "--seed", 0),
        ],
        options -> rd_pattern_demo(n_cells=options[:n_cells], seed=options[:seed]),
    ),
    "wave-count" => CommandSpec(
        _DEMO_SUBCOMMAND_HELP["wave-count"],
        [
            _int_flag(:peaks, "--peaks", 3),
            _int_flag(:cells_per_peak, "--cells-per-peak", 12),
        ],
        options -> wave_count_demo(peaks=options[:peaks], cells_per_peak=options[:cells_per_peak]),
    ),
    "closed-loop" => CommandSpec(
        _DEMO_SUBCOMMAND_HELP["closed-loop"],
        [
            _int_flag(:n_cells, "--n-cells", 100),
            _int_flag(:target_peaks, "--target-peaks", 3),
            _int_flag(:seed, "--seed", 0),
        ],
        options -> closed_loop_demo(
            n_cells=options[:n_cells],
            target_peaks=options[:target_peaks],
            seed=options[:seed],
        ),
    ),
    "bistability" => CommandSpec(
        _DEMO_SUBCOMMAND_HELP["bistability"],
        [
            _int_flag(:n_cells, "--n-cells", 100),
            _int_flag(:seed, "--seed", 0),
            _int_flag(:cut, "--cut", options -> options[:n_cells] ÷ 2),
            _float_flag(:D_a, "--d-a", REFERENCE_ONE_HEAD_D_A_100),
        ],
        options -> wiring_bistability_demo(
            n_cells=options[:n_cells],
            seed=options[:seed],
            cut=options[:cut],
            D_a=options[:D_a],
        ),
    ),
    "cut-sweep" => CommandSpec(
        _DEMO_SUBCOMMAND_HELP["cut-sweep"],
        [
            _int_flag(:n_cells, "--n-cells", 30),
            _int_flag(:seed, "--seed", 0),
            _float_flag(:D_a, "--d-a", REFERENCE_ONE_HEAD_D_A_100),
            _int_flag(:cut_count, "--cut-count", 1),
            _cutset_family_flag(:candidate_cutsets, "--candidate-cutsets", nothing),
            _cutset_family_flag(:validate_cutsets, "--validate-cutsets", Vector{Vector{Int}}()),
            _symbol_flag(:validation_mode, "--validation-mode", :auto, (:none, :auto, :all)),
        ],
        options -> wiring_cut_sweep_demo(
            n_cells=options[:n_cells],
            seed=options[:seed],
            D_a=options[:D_a],
            cut_count=options[:cut_count],
            candidate_cutsets=options[:candidate_cutsets],
            validate_cutsets=options[:validate_cutsets],
            validation_mode=options[:validation_mode],
        ),
    ),
    "fragment-family" => CommandSpec(
        _DEMO_SUBCOMMAND_HELP["fragment-family"],
        [
            _int_flag(:n_cells, "--n-cells", 30),
            _int_flag(:seed, "--seed", 0),
            _float_flag(:D_a, "--d-a", REFERENCE_ONE_HEAD_D_A_100),
            _int_flag(:fragment_size, "--fragment-size", options -> max(1, options[:n_cells] ÷ 4)),
            _int_list_flag(:left_cuts, "--left-cuts", nothing),
            _symbol_flag(:validation_mode, "--validation-mode", :auto, (:none, :auto, :all)),
        ],
        options -> wiring_fragment_family_demo(
            n_cells=options[:n_cells],
            seed=options[:seed],
            D_a=options[:D_a],
            fragment_size=options[:fragment_size],
            left_cuts=options[:left_cuts],
            validation_mode=options[:validation_mode],
        ),
    ),
    "grid-patch" => CommandSpec(
        _DEMO_SUBCOMMAND_HELP["grid-patch"],
        [
            _int_flag(:rows, "--rows", 8),
            _int_flag(:cols, "--cols", 8),
            _int_flag(:patch_rows, "--patch-rows", 2),
            _int_flag(:patch_cols, "--patch-cols", 2),
            _int_flag(:seed, "--seed", 0),
            _float_flag(:D_a, "--d-a", 1.0),
            _float_flag(:D_i, "--d-i", 30.0),
            _bool_flag(:validate, "--validate", false),
        ],
        options -> grid_patch_isolation_demo(
            rows=options[:rows],
            cols=options[:cols],
            patch_rows=options[:patch_rows],
            patch_cols=options[:patch_cols],
            seed=options[:seed],
            D_a=options[:D_a],
            D_i=options[:D_i],
            validate=options[:validate],
        ),
    ),
    "grid-patch-recovery" => CommandSpec(
        _DEMO_SUBCOMMAND_HELP["grid-patch-recovery"],
        [
            _int_flag(:rows, "--rows", 4),
            _int_flag(:cols, "--cols", 6),
            _int_flag(:patch_top, "--patch-top", 2),
            _int_flag(:patch_left, "--patch-left", 1),
            _int_flag(:patch_rows, "--patch-rows", 2),
            _int_flag(:patch_cols, "--patch-cols", 2),
            _int_flag(:seed, "--seed", 33),
            _float_flag(:D_a, "--d-a", 1.0),
            _float_flag(:D_i, "--d-i", 30.0),
            _int_flag(:exponent_min, "--exponent-min", -11),
            _int_flag(:exponent_max, "--exponent-max", 11),
            _float_flag(:step_factor, "--step-factor", 1.21),
            _int_flag(:max_iterations, "--max-iterations", 8),
            _float_flag(:active_fraction, "--active-fraction", 0.5),
            _float_flag(:meaningful_improvement, "--meaningful-improvement", 0.20),
            _float_flag(
                :max_count_selection_regret,
                "--max-count-selection-regret",
                0.10,
            ),
            _float_flag(:settle_time, "--settle-time", 300.0),
            _float_flag(:steady_tol, "--steady-tol", 1.0e-6),
            _bool_flag(:steady_stop, "--steady-stop", true),
            _bool_flag(:include_delayed_capacity, "--include-delayed-capacity", true),
            _bool_flag(:include_feedback, "--include-feedback", true),
            _string_flag(
                :evidence_scope,
                "--evidence-scope",
                "exploratory_single_regime",
            ),
        ],
        options -> grid_patch_recovery_demo(
            rows=options[:rows],
            cols=options[:cols],
            patch_top=options[:patch_top],
            patch_left=options[:patch_left],
            patch_rows=options[:patch_rows],
            patch_cols=options[:patch_cols],
            seed=options[:seed],
            D_a=options[:D_a],
            D_i=options[:D_i],
            exponent_min=options[:exponent_min],
            exponent_max=options[:exponent_max],
            step_factor=options[:step_factor],
            max_iterations=options[:max_iterations],
            active_fraction=options[:active_fraction],
            meaningful_improvement=options[:meaningful_improvement],
            max_count_selection_regret=options[:max_count_selection_regret],
            settle_time=options[:settle_time],
            steady_tol=options[:steady_tol],
            steady_stop=options[:steady_stop],
            include_delayed_capacity=options[:include_delayed_capacity],
            include_feedback=options[:include_feedback],
            evidence_scope=options[:evidence_scope],
        ),
    ),
    "grid-patch-recovery-cohort" => CommandSpec(
        _DEMO_SUBCOMMAND_HELP["grid-patch-recovery-cohort"],
        [
            _string_flag(:cohort_id, "--cohort-id", "grid-patch-recovery-cohort"),
            _string_flag(
                :output_dir,
                "--output-dir",
                options -> joinpath(pwd(), "artifacts", options[:cohort_id]),
            ),
            _int_list_flag(:seeds, "--seeds", collect(100:111)),
            _int_flag(:rows, "--rows", 4),
            _int_flag(:cols, "--cols", 6),
            _int_flag(:patch_rows, "--patch-rows", 2),
            _int_flag(:patch_cols, "--patch-cols", 2),
            _int_flag(:patch_top, "--patch-top", nothing),
            _int_flag(:patch_left, "--patch-left", nothing),
            _float_flag(:D_a, "--d-a", 1.0),
            _float_flag(:D_i, "--d-i", 30.0),
            _string_flag(
                :regime_id,
                "--regime-id",
                options -> string(
                    "grid",
                    options[:rows],
                    "x",
                    options[:cols],
                    "-patch",
                    options[:patch_rows],
                    "x",
                    options[:patch_cols],
                    "-da",
                    options[:D_a],
                    "-di",
                    options[:D_i],
                ),
            ),
            _int_flag(:exponent_min, "--exponent-min", -11),
            _int_flag(:exponent_max, "--exponent-max", 11),
            _float_flag(:step_factor, "--step-factor", 1.21),
            _int_flag(:max_iterations, "--max-iterations", 8),
            _float_flag(:active_fraction, "--active-fraction", 0.5),
            _float_flag(:meaningful_improvement, "--meaningful-improvement", 0.20),
            _float_flag(
                :max_count_selection_regret,
                "--max-count-selection-regret",
                0.10,
            ),
            _float_flag(:settle_time, "--settle-time", 300.0),
            _float_flag(:steady_tol, "--steady-tol", 1.0e-6),
            _bool_flag(:steady_stop, "--steady-stop", true),
            _bool_flag(:include_delayed_capacity, "--include-delayed-capacity", false),
            _bool_flag(:include_feedback, "--include-feedback", false),
            _string_flag(:evidence_scope, "--evidence-scope", "capacity_cohort"),
        ],
        _run_grid_patch_recovery_cohort,
    ),
    "grid-patch-recovery-development" => CommandSpec(
        _DEMO_SUBCOMMAND_HELP["grid-patch-recovery-development"],
        [
            _string_flag(
                :development_id,
                "--development-id",
                "protocol-v2-development",
            ),
            _string_flag(
                :output_dir,
                "--output-dir",
                options -> joinpath(
                    pwd(),
                    "artifacts",
                    "development",
                    options[:development_id],
                ),
            ),
            _int_list_flag(:seeds, "--seeds", collect(0:5)),
            _int_flag(:rows, "--rows", 4),
            _int_flag(:cols, "--cols", 6),
            _int_flag(:patch_rows, "--patch-rows", 2),
            _int_flag(:patch_cols, "--patch-cols", 2),
            _int_flag(:patch_top, "--patch-top", nothing),
            _int_flag(:patch_left, "--patch-left", nothing),
            _float_flag(:D_a, "--d-a", 1.0),
            _float_flag(:D_i, "--d-i", 30.0),
            _string_flag(
                :regime_id,
                "--regime-id",
                options -> string(
                    "grid",
                    options[:rows],
                    "x",
                    options[:cols],
                    "-patch",
                    options[:patch_rows],
                    "x",
                    options[:patch_cols],
                    "-da",
                    options[:D_a],
                    "-di",
                    options[:D_i],
                ),
            ),
            _float_flag(:settle_chunk_time, "--settle-chunk-time", 300.0),
            _float_flag(:settle_max_time, "--settle-max-time", 1200.0),
            _float_flag(:steady_tol, "--steady-tol", 1.0e-6),
            _int_flag(:exponent_min, "--exponent-min", -11),
            _int_flag(:exponent_max, "--exponent-max", 11),
            _int_flag(:exponent_hard_min, "--exponent-hard-min", -15),
            _int_flag(:exponent_hard_max, "--exponent-hard-max", 15),
            _int_flag(
                :exponent_expansion_step,
                "--exponent-expansion-step",
                2,
            ),
            _float_flag(
                :exponent_plateau_relative_tol,
                "--exponent-plateau-relative-tol",
                1.0e-3,
            ),
            _int_flag(
                :exponent_plateau_patience,
                "--exponent-plateau-patience",
                2,
            ),
            _float_flag(:step_factor, "--step-factor", 1.21),
            _float_flag(:active_fraction, "--active-fraction", 0.5),
            _float_flag(
                :max_count_selection_regret,
                "--max-count-selection-regret",
                0.10,
            ),
            _float_list_flag(
                :alias_resolutions,
                "--alias-resolutions",
                [1.0e-4, 1.0e-3, 1.0e-2],
            ),
        ],
        _run_grid_patch_recovery_development,
    ),
    "grid-patch-sensitivity" => CommandSpec(
        _DEMO_SUBCOMMAND_HELP["grid-patch-sensitivity"],
        [
            _int_flag(:rows, "--rows", 8),
            _int_flag(:cols, "--cols", 8),
            _int_flag(:patch_rows, "--patch-rows", 2),
            _int_flag(:patch_cols, "--patch-cols", 2),
            _int_flag(:seed, "--seed", 0),
            _float_flag(:D_a, "--d-a", 1.0),
            _float_flag(:D_i, "--d-i", 30.0),
            _metrics_flag(:metrics, "--metrics", [:balanced, :structure, :profile]),
        ],
        options -> grid_patch_metric_sensitivity_demo(
            rows=options[:rows],
            cols=options[:cols],
            patch_rows=options[:patch_rows],
            patch_cols=options[:patch_cols],
            seed=options[:seed],
            D_a=options[:D_a],
            D_i=options[:D_i],
            metrics=options[:metrics],
        ),
    ),
    "grid-patch-threshold-sensitivity" => CommandSpec(
        _DEMO_SUBCOMMAND_HELP["grid-patch-threshold-sensitivity"],
        [
            _int_flag(:rows, "--rows", 8),
            _int_flag(:cols, "--cols", 8),
            _int_flag(:patch_rows, "--patch-rows", 2),
            _int_flag(:patch_cols, "--patch-cols", 2),
            _int_flag(:seed, "--seed", 0),
            _float_flag(:D_a, "--d-a", 1.0),
            _float_flag(:D_i, "--d-i", 30.0),
            _float_list_flag(:active_fractions, "--active-fractions", [0.4, 0.5, 0.6]),
            _metrics_flag(:metrics, "--metrics", [:balanced, :structure, :profile]),
        ],
        options -> grid_patch_threshold_sensitivity_demo(
            rows=options[:rows],
            cols=options[:cols],
            patch_rows=options[:patch_rows],
            patch_cols=options[:patch_cols],
            seed=options[:seed],
            D_a=options[:D_a],
            D_i=options[:D_i],
            active_fractions=options[:active_fractions],
            metrics=options[:metrics],
        ),
    ),
    "grid-patch-sweep" => CommandSpec(
        _DEMO_SUBCOMMAND_HELP["grid-patch-sweep"],
        [
            _int_flag(:rows, "--rows", 8),
            _int_flag(:cols, "--cols", 8),
            _patch_sizes_flag(:patch_sizes, "--patch-sizes", [(1, 1), (2, 2), (2, 3)]),
            _int_flag(:seed, "--seed", 0),
            _float_list_flag(:D_a_values, "--d-a-values", [1.0]),
            _float_list_flag(:D_i_values, "--d-i-values", [30.0]),
        ],
        options -> grid_patch_sweep_demo(
            rows=options[:rows],
            cols=options[:cols],
            patch_sizes=options[:patch_sizes],
            seed=options[:seed],
            D_a_values=options[:D_a_values],
            D_i_values=options[:D_i_values],
        ),
    ),
    "severity-scan" => CommandSpec(
        _DEMO_SUBCOMMAND_HELP["severity-scan"],
        [
            _int_flag(:n_cells, "--n-cells", 30),
            _int_flag(:seed, "--seed", 0),
            _int_flag(:cut_count, "--cut-count", 1),
            _int_flag(:top_k, "--top-k", 1),
            _float_list_flag(:D_a_values, "--d-a-values", [REFERENCE_ONE_HEAD_D_A_100]),
            _cutset_family_flag(:candidate_cutsets, "--candidate-cutsets", nothing),
            _symbol_flag(:validation_mode, "--validation-mode", :none, (:none, :auto, :all)),
        ],
        options -> wiring_severity_phase_scan_demo(
            n_cells=options[:n_cells],
            seed=options[:seed],
            D_a_values=options[:D_a_values],
            cut_count=options[:cut_count],
            top_k=options[:top_k],
            candidate_cutsets=options[:candidate_cutsets],
            validation_mode=options[:validation_mode],
        ),
    ),
    "wiring-k" => CommandSpec(
        _DEMO_SUBCOMMAND_HELP["wiring-k"],
        [
            _int_flag(:n_cells, "--n-cells", 30),
            _int_flag(:seed, "--seed", 0),
            _float_flag(:D_a, "--d-a", REFERENCE_ONE_HEAD_D_A_100),
            _int_flag(:trials, "--trials", 1),
            _int_flag(:cut_count, "--cut-count", 1),
            _int_flag(:target_peak_count, "--target-peaks", nothing),
            _int_flag(:target_top_k, "--target-top-k", nothing),
            _string_flag(:target_shape, "--target-shape", nothing),
            _cutset_family_flag(:candidate_cutsets, "--candidate-cutsets", nothing),
            _cutset_family_flag(:validate_cutsets, "--validate-cutsets", Vector{Vector{Int}}()),
            _symbol_flag(:validation_mode, "--validation-mode", :auto, (:none, :auto, :all)),
        ],
        options -> wiring_intervention_k_demo(
            n_cells=options[:n_cells],
            seed=options[:seed],
            D_a=options[:D_a],
            trials=options[:trials],
            cut_count=options[:cut_count],
            target_peak_count=options[:target_peak_count],
            target_top_k=options[:target_top_k],
            target_shape=options[:target_shape],
            candidate_cutsets=options[:candidate_cutsets],
            validate_cutsets=options[:validate_cutsets],
            validation_mode=options[:validation_mode],
        ),
    ),
)

function _run_spec(spec::CommandSpec, args::Vector{String})
    options = _parse_options(args, spec.flags)
    return spec.run(options)
end

function main(args::Vector{String}=ARGS)
    isempty(args) && error("expected command; use `--help` for usage")
    if _is_help_arg(args[1])
        _print_top_help()
        return nothing
    end

    if args[1] == "diagrams"
        if _has_help(args[2:end])
            _print_diagrams_help()
            return nothing
        end
        paths = _run_spec(_DIAGRAMS_COMMAND, args[2:end])
        for (name, path) in sort(collect(paths))
            println("$name: $path")
        end
        return nothing
    end

    args[1] == "demo" || error("expected `demo` or `diagrams` command")
    length(args) < 2 && error("expected demo subcommand; use `main([\"demo\", \"--help\"])` for usage")
    if _is_help_arg(args[2])
        _print_demo_help()
        return nothing
    end

    subcommand = args[2]
    haskey(_DEMO_COMMANDS, subcommand) || error("unknown demo subcommand: $(subcommand)")
    if _has_help(args[3:end])
        _print_demo_subcommand_help(subcommand)
        return nothing
    end

    payload = _run_spec(_DEMO_COMMANDS[subcommand], args[3:end])
    println(JSON3.write(_jsonable(payload)))
    return nothing
end

end
