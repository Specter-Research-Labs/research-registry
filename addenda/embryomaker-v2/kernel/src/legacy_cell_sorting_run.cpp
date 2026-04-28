#include "em2/api/legacy_cell_sorting_run.hpp"

#include <cstdint>
#include <stdexcept>
#include <vector>

#include "em2/core/gfortran_rng.hpp"
#include "em2/mechanics/legacy_cell_sorting_noise.hpp"
#include "em2/model/legacy_cell_sorting.hpp"

namespace em2 {
namespace {

std::uint64_t legacy_noise_sphere_draw_count(const int partitions) {
  const std::uint64_t point_count =
      static_cast<std::uint64_t>(partitions) * static_cast<std::uint64_t>(partitions);
  return 2ULL * (point_count / 2ULL);
}

}  // namespace

LegacyCellSortingRunResult run_legacy_cell_sorting(const LegacyCellSortingRunConfig& config) {
  if (config.steps < 0) {
    throw std::invalid_argument("legacy cell sorting run steps must be non-negative");
  }

  GFortranRngState rng = make_gfortran_rng_state(config.initial_seed);
  LegacyCellSortingState state = build_legacy_cell_sorting_state(rng);
  if (config.initial_node_positions.has_value()) {
    const auto& positions = *config.initial_node_positions;
    std::vector<double> x;
    std::vector<double> y;
    std::vector<double> z;
    x.reserve(positions.size());
    y.reserve(positions.size());
    z.reserve(positions.size());
    for (const auto& position : positions) {
      x.push_back(position[0]);
      y.push_back(position[1]);
      z.push_back(position[2]);
    }
    apply_legacy_cell_sorting_node_positions(state, x, y, z);
  }
  if (config.initial_cell_types.has_value()) {
    apply_legacy_cell_sorting_cell_types(state, *config.initial_cell_types);
  }
  if (config.noise_seed_words.has_value()) {
    // Frame-0 snapshots persist the live RNG after inialea3d has already consumed the sphere draws.
    GFortranRngState frame_zero_live_rng = make_gfortran_rng_state(*config.noise_seed_words);
    GFortranRngState sphere_rng = frame_zero_live_rng;
    rewind_gfortran_random_r8(
        sphere_rng,
        legacy_noise_sphere_draw_count(state.config.noise_sphere_partitions));
    LegacyNoiseRuntime noise_runtime =
        make_legacy_noise_runtime(state.config.noise_sphere_partitions, sphere_rng);
    noise_runtime.rng = frame_zero_live_rng;
    LegacyNoiseBatchResult cumulative_noise{
        .attempts = 0,
        .accepted = 0,
        .rejected = 0,
        .zero_displacement = 0,
    };

    for (int step = 0; step < config.steps; ++step) {
      const LegacyIterationResult iteration =
          advance_legacy_cell_sorting_iteration(state, noise_runtime);
      cumulative_noise.attempts += iteration.noise.attempts;
      cumulative_noise.accepted += iteration.noise.accepted;
      cumulative_noise.rejected += iteration.noise.rejected;
      cumulative_noise.zero_displacement += iteration.noise.zero_displacement;
    }

    return LegacyCellSortingRunResult{
        .summary = summarize_legacy_cell_sorting_state(state, config.steps, &cumulative_noise),
    };
  }
  LegacyNoiseRuntime noise_runtime = config.noise_seed.has_value()
      ? make_legacy_noise_runtime(state.config.noise_sphere_partitions, *config.noise_seed)
      : make_legacy_noise_runtime(state.config.noise_sphere_partitions, rng);
  LegacyNoiseBatchResult cumulative_noise{
      .attempts = 0,
      .accepted = 0,
      .rejected = 0,
      .zero_displacement = 0,
  };

  for (int step = 0; step < config.steps; ++step) {
    const LegacyIterationResult iteration =
        advance_legacy_cell_sorting_iteration(state, noise_runtime);
    cumulative_noise.attempts += iteration.noise.attempts;
    cumulative_noise.accepted += iteration.noise.accepted;
    cumulative_noise.rejected += iteration.noise.rejected;
    cumulative_noise.zero_displacement += iteration.noise.zero_displacement;
  }

  return LegacyCellSortingRunResult{
      .summary = summarize_legacy_cell_sorting_state(state, config.steps, &cumulative_noise),
  };
}

}  // namespace em2
