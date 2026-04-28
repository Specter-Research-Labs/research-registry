module CLI

using JSON3

using ..Controller: closed_loop_demo,
    rd_pattern_demo,
    wave_count_demo
using ..Diagrams: save_diagrams
using ..GridLesions: grid_patch_isolation_demo,
    grid_patch_metric_sensitivity_demo,
    grid_patch_threshold_sensitivity_demo,
    grid_patch_sweep_demo
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
        field === nothing && continue
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
