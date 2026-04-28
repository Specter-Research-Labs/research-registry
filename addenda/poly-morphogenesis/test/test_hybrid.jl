using PolyMorphogenesis
using Test

@testset "hybrid cell exposes mode-dependent interfaces" begin
    cell = PolyMorphogenesis.Controller.hybrid_cell_object(:cell)
    @test Set(cell.modes) == Set([:rd, :wave, :done])
    @test cell.port_schemas[:rd].outputs == [:A_out, :I_out]
    @test :peak_count in cell.port_schemas[:done].outputs
    @test any(==(:S0L_out), cell.port_schemas[:wave].outputs)

    rd_state = cell.initial_state()
    wave_state = copy(rd_state)
    wave_state[:mode] = :wave
    wave_state[:A_local] = 0.8
    wave_state[:pre][1] = 1.0
    done_state = copy(rd_state)
    done_state[:mode] = :done

    rd_outputs = cell.readout(rd_state)
    wave_outputs = cell.readout(wave_state)
    done_outputs = cell.readout(done_state)

    @test Set(keys(rd_outputs)) == Set([:A_out, :I_out])
    @test haskey(wave_outputs, :S0L_out)
    @test !haskey(wave_outputs, :A_out)
    @test done_outputs == Dict(:peak_count => 0.0)
end

@testset "hybrid cell executes per-mode updates" begin
    cell = PolyMorphogenesis.Controller.hybrid_cell_object(:cell)

    rd_state = Dict(
        :mode => :rd,
        :A => 0.5,
        :I => 0.2,
        :pre => zeros(12),
        :sig => zeros(12),
        :amdr => 0.0,
        :A_local => 0.0,
        :done => false,
        :peak_count => 0.0,
    )
    rd_next = cell.update(
        rd_state,
        Dict(:A_left => 0.5, :A_right => 0.5, :I_left => 0.2, :I_right => 0.2),
    )
    @test isfinite(rd_next[:A])
    @test isfinite(rd_next[:I])

    wave_state = cell.initial_state()
    wave_state[:mode] = :wave
    wave_state[:A_local] = 0.7
    wave_state[:pre][1] = 1.0
    wave_next = cell.update(wave_state, Dict{Symbol,Any}())
    @test wave_next[:pre][1] >= wave_state[:pre][1]
    @test wave_next[:amdr] >= 0.0

    done_state = copy(wave_state)
    done_state[:mode] = :done
    done_state[:peak_count] = 2.0
    done_next = cell.update(done_state, Dict(:peak_count => 3.0))
    @test done_next[:peak_count] == 3.0
end
