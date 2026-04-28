#pragma once

#include <array>
#include <cstdint>
#include <optional>
#include <vector>

#include "em2/core/gfortran_rng.hpp"
#include "em2/mechanics/legacy_cell_sorting_stepper.hpp"

namespace em2 {

struct LegacyCellSortingRunConfig {
  std::int32_t initial_seed;
  std::optional<std::int32_t> noise_seed;
  std::optional<std::array<std::int32_t, kGFortranSeedWordCount>> noise_seed_words;
  std::optional<std::vector<std::array<double, 3>>> initial_node_positions;
  std::optional<std::vector<int>> initial_cell_types;
  int steps;
};

struct LegacyCellSortingRunResult {
  LegacyTrajectorySummary summary;
};

LegacyCellSortingRunResult run_legacy_cell_sorting(const LegacyCellSortingRunConfig& config);

}  // namespace em2
