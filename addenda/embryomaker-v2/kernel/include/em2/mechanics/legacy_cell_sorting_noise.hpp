#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

#include "em2/core/gfortran_rng.hpp"
#include "em2/mechanics/legacy_neighbor_list.hpp"

namespace em2 {

struct LegacyCellSortingState;

struct LegacyNoiseSphere {
  int partitions;
  std::vector<double> x;
  std::vector<double> y;
  std::vector<double> z;

  [[nodiscard]] std::size_t size() const { return x.size(); }
};

struct LegacyNoiseRuntime {
  GFortranRngState rng;
  LegacyNoiseSphere sphere;
};

struct LegacyNoiseStep {
  int node_index;
  int cell_index;
  double displacement;
  double old_energy;
  double new_energy;
  bool accepted;
};

struct LegacyNoiseBatchResult {
  int attempts;
  int accepted;
  int rejected;
  int zero_displacement;
};

LegacyNoiseRuntime make_legacy_noise_runtime(int partitions, GFortranRngState rng);
LegacyNoiseRuntime make_legacy_noise_runtime(int partitions, std::int32_t repeated_seed_word);

double compute_legacy_cell_sorting_local_energy(
    const LegacyCellSortingState& state,
    const LegacyNeighborList& neighbor_list,
    std::size_t node_index);

double compute_legacy_cell_sorting_local_energy(
    const LegacyCellSortingState& state,
    std::size_t node_index);

LegacyNoiseStep apply_legacy_cell_sorting_noise(
    LegacyCellSortingState& state,
    LegacyNoiseRuntime& runtime,
    LegacyNeighborList& neighbor_list,
    double delta);

LegacyNoiseStep apply_legacy_cell_sorting_noise(
    LegacyCellSortingState& state,
    LegacyNoiseRuntime& runtime,
    double delta);

LegacyNoiseBatchResult apply_legacy_cell_sorting_noise_batch(
    LegacyCellSortingState& state,
    LegacyNoiseRuntime& runtime,
    LegacyNeighborList& neighbor_list,
    double delta);

LegacyNoiseBatchResult apply_legacy_cell_sorting_noise_batch(
    LegacyCellSortingState& state,
    LegacyNoiseRuntime& runtime,
    double delta);

}  // namespace em2
