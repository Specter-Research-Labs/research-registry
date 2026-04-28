using Test

include("test_core.jl")
include("test_compile.jl")
include("test_hybrid.jl")
include("test_rd.jl")
include("test_rd_graph.jl")
include("test_grid_lesions.jl")
include("test_wave.jl")
include("test_phase_lenses.jl")
include("test_closed_loop.jl")
include("test_bistability.jl")
include("test_source_parity.jl")
include("test_act_claims.jl")
include("test_cli.jl")
if get(ENV, "POLY_RUN_UPSTREAM_ORACLE", "0") == "1"
    include("test_upstream_controller_oracle.jl")
end
