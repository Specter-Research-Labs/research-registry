using PolyMorphogenesis
using Test

const PMAlgebra = PolyMorphogenesis.Algebra

function _synthetic_profile(peaks::Int; cells_per_peak::Int=12)
    A = Float64[]
    for _ in 1:(peaks - 1)
        append!(A, collect(range(0.0, 1.0; length=cells_per_peak + 1))[1:end-1])
        append!(A, collect(range(1.0, 0.0; length=cells_per_peak + 1)))
    end
    append!(A, collect(range(0.0, 1.0; length=cells_per_peak + 1)))
    return A
end

function _wave_machine_lens(config::WaveConfig, n_cells::Int)
    plan = PolyMorphogenesis.Wave.compile_wave_plan(config, n_cells)
    return PMAlgebra.DependentLens(
        :wave_machine,
        PMAlgebra.PortSchema([:wave_A, :normalized_A, :source_pre], Symbol[]),
        PMAlgebra.PortSchema(Symbol[], [:peak_count, :emitted, :done]),
        inputs -> PolyMorphogenesis.Wave.wave_phase_outputs(
            PolyMorphogenesis.Wave.wave_count_composed_from_normalized(
                plan,
                inputs[:wave_A];
                source_pre=inputs[:source_pre],
            ),
        ),
        (state, incoming) -> incoming,
    )
end

@testset "phase lenses" begin
    n_cells = 10

    @testset "rd_to_wave_lens preserves raw A profile by default" begin
        lens = PMAlgebra.rd_to_wave_lens(n_cells)

        rd_outputs = Dict(
            :A_profile => [sin(2π * i / n_cells) for i in 1:n_cells],
            :I_profile => fill(0.5, n_cells),
        )

        result = lens.forward(rd_outputs)
        @test haskey(result, :wave_A)
        @test haskey(result, :normalized_A)
        @test haskey(result, :source_pre)
        @test result[:source_pre] == 1.0
        @test result[:wave_A] == Float64.(rd_outputs[:A_profile])
        @test length(result[:normalized_A]) == n_cells
        @test all(0.0 .<= result[:normalized_A] .<= 1.0)
    end

    @testset "rd_to_wave_lens can still normalize explicitly" begin
        lens = PMAlgebra.rd_to_wave_lens(n_cells; normalize=true)
        rd_outputs = Dict(
            :A_profile => collect(range(0.2, 0.8; length=n_cells)),
            :I_profile => fill(0.5, n_cells),
        )

        result = lens.forward(rd_outputs)
        @test result[:wave_A] == PolyMorphogenesis.Wave.normalize_profile(rd_outputs[:A_profile])
        @test result[:normalized_A] == PolyMorphogenesis.Wave.normalize_profile(rd_outputs[:A_profile])
    end

    @testset "wave_to_ctrl_lens" begin
        lens = PMAlgebra.wave_to_ctrl_lens(n_cells)
        wave_outputs = Dict(
            :peak_count => 3.0,
            :emitted => fill(:S0H, n_cells),
            :done => trues(n_cells),
        )
        result = lens.forward(wave_outputs)
        @test result[:peak_count] == 3.0
    end

    @testset "rd to wave to ctrl composition matches manual execution" begin
        for peaks in (1, 2, 3), normalize in (false, true)
            profile = _synthetic_profile(peaks; cells_per_peak=4)
            n = length(profile)
            config = WaveConfig(normalize_input=normalize)
            rd_outputs = Dict(:A_profile => profile, :I_profile => zeros(n))

            rd_wave = PMAlgebra.rd_to_wave_lens(n; normalize=normalize)
            wave_machine = _wave_machine_lens(config, n)
            wave_ctrl = PMAlgebra.wave_to_ctrl_lens(n)

            wave_inputs = rd_wave.forward(rd_outputs)
            manual_wave = PolyMorphogenesis.Wave.wave_count_composed_from_normalized(
                PolyMorphogenesis.Wave.compile_wave_plan(config, n),
                wave_inputs[:wave_A];
                source_pre=wave_inputs[:source_pre],
            )
            manual_wave_outputs = PolyMorphogenesis.Wave.wave_phase_outputs(manual_wave)
            manual_ctrl_result = wave_ctrl.forward(manual_wave_outputs)

            wave_pipeline = PolyMorphogenesis.Algebra.compose_lenses(rd_wave, wave_machine)
            ctrl_pipeline = PolyMorphogenesis.Algebra.compose_lenses(
                rd_wave,
                PolyMorphogenesis.Algebra.compose_lenses(wave_machine, wave_ctrl),
            )

            @test wave_pipeline.forward(rd_outputs) == manual_wave_outputs
            @test ctrl_pipeline.forward(rd_outputs) == manual_ctrl_result
        end
    end
end
