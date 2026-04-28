module Diagrams

using Catlab.Graphics: to_graphviz
using Catlab.Graphics.Graphviz: pprint
using Catlab.Graphics.WiringDiagramLayouts: LeftToRight

using ..Algebra: compile_phase
using ..RD: RDParameters, RDChainConfig, rd_phase_program
using ..Wave: WaveConfig, wave_phase_program

export save_diagrams

function _write_dot(path::String, graph)
    open(path, "w") do io
        pprint(io, graph)
    end
end

function save_diagrams(; base_dir::String, n_cells::Int=10)
    dir = joinpath(base_dir, "docs", "diagrams")
    mkpath(dir)

    rd_compiled = compile_phase(rd_phase_program(RDParameters(), RDChainConfig(n_cells=n_cells)))
    wave_compiled = compile_phase(wave_phase_program(WaveConfig(), n_cells))

    paths = Dict{String,String}()

    rd_default = to_graphviz(rd_compiled.diagram; node_labels=true, labels=true, label_attr=:label)
    rd_default_path = joinpath(dir, "rd_default.dot")
    _write_dot(rd_default_path, rd_default)
    paths["rd_default"] = rd_default_path

    rd_styled = to_graphviz(
        rd_compiled.diagram;
        orientation=LeftToRight,
        node_labels=true,
        labels=true,
        label_attr=:label,
        graph_attrs=Dict(:fontname => "Helvetica", :bgcolor => "white", :pad => "0.5", :nodesep => "0.4", :ranksep => "0.6"),
        node_attrs=Dict(:fontname => "Helvetica", :fontsize => "11"),
        edge_attrs=Dict(:color => "#4a90d9", :fontname => "Helvetica", :fontsize => "9", :fontcolor => "#2c5f8a"),
        cell_attrs=Dict(:bgcolor => "#e8f4fd", :border => "1", :cellpadding => "6", :color => "#4a90d9"),
    )
    rd_styled_path = joinpath(dir, "rd_styled.dot")
    _write_dot(rd_styled_path, rd_styled)
    paths["rd_styled"] = rd_styled_path

    wave_default = to_graphviz(wave_compiled.diagram; node_labels=true, labels=true, label_attr=:label)
    wave_default_path = joinpath(dir, "wave_default.dot")
    _write_dot(wave_default_path, wave_default)
    paths["wave_default"] = wave_default_path

    wave_styled = to_graphviz(
        wave_compiled.diagram;
        orientation=LeftToRight,
        node_labels=true,
        labels=true,
        label_attr=:label,
        graph_attrs=Dict(:fontname => "Helvetica", :bgcolor => "white", :pad => "0.5", :nodesep => "0.4", :ranksep => "0.6"),
        node_attrs=Dict(:fontname => "Helvetica", :fontsize => "11"),
        edge_attrs=Dict(:color => "#d94a7b", :fontname => "Helvetica", :fontsize => "9", :fontcolor => "#8a2c5f"),
        cell_attrs=Dict(:bgcolor => "#fde8f0", :border => "1", :cellpadding => "6", :color => "#d94a7b"),
    )
    wave_styled_path = joinpath(dir, "wave_styled.dot")
    _write_dot(wave_styled_path, wave_styled)
    paths["wave_styled"] = wave_styled_path

    return paths
end

end
