#pragma once

#include <cstddef>

#include "em2/mechanics/contact_graph.hpp"
#include "em2/mechanics/legacy_cell_sorting_noise.hpp"
#include "em2/mechanics/legacy_neighbor_list.hpp"
#include "em2/mechanics/mesenchymal_forces.hpp"

namespace em2 {

struct LegacyCellSortingState;

struct LegacyMechanicsState {
  LegacyNeighborList neighbor_list;
  ContactGraph contact_graph;
  ForceState forces;
  double delta;
};

struct LegacyIterationResult {
  double delta;
  double max_force_norm;
  std::size_t contact_count;
  LegacyNoiseBatchResult noise;
};

struct LegacyTrajectorySummary {
  int steps;
  std::size_t node_count;
  std::size_t cell_count;
  std::size_t contact_count;
  double max_distance_from_origin;
  double mean_distance_from_origin;
  double mean_neighbor_count;
  int type1_cell_count;
  int type2_cell_count;
  int total_noise_attempts;
  int total_noise_accepted;
  int total_noise_rejected;
  int total_noise_zero_displacement;
};

LegacyMechanicsState prepare_legacy_cell_sorting_mechanics(const LegacyCellSortingState& state);

void advance_legacy_cell_sorting_rungekutta4(
    LegacyCellSortingState& state,
    const ContactGraph& contact_graph,
    const ForceState& initial_forces,
    double delta);

LegacyIterationResult advance_legacy_cell_sorting_iteration(
    LegacyCellSortingState& state,
    LegacyNoiseRuntime& noise_runtime);

LegacyTrajectorySummary summarize_legacy_cell_sorting_state(
    const LegacyCellSortingState& state,
    int steps,
    const LegacyNoiseBatchResult* cumulative_noise = nullptr);

}  // namespace em2
