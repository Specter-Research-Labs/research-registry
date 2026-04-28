#include "em2/mechanics/legacy_cell_sorting_stepper.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <vector>

#include "em2/model/legacy_cell_sorting.hpp"

namespace em2 {
namespace {

double max_force_norm(const ForceState& forces) {
  double max_norm = 0.0;
  for (std::size_t node_index = 0; node_index < forces.fx.size(); ++node_index) {
    const double norm = std::sqrt(
        (forces.fx[node_index] * forces.fx[node_index]) +
        (forces.fy[node_index] * forces.fy[node_index]) +
        (forces.fz[node_index] * forces.fz[node_index]));
    max_norm = std::max(max_norm, norm);
  }
  return max_norm;
}

double distance_from_origin(double x, double y, double z) {
  return std::sqrt((x * x) + (y * y) + (z * z));
}

}  // namespace

LegacyMechanicsState prepare_legacy_cell_sorting_mechanics(const LegacyCellSortingState& state) {
  const LegacyNeighborList neighbor_list = build_legacy_neighbor_list(state);
  const ContactGraph contact_graph = build_mesenchymal_contact_graph(neighbor_list);
  const ForceState forces = compute_mesenchymal_forces(state, contact_graph);

  const double epsilon = std::numeric_limits<double>::epsilon() * 10.0;
  const double max_norm = max_force_norm(forces);
  double delta = state.config.deltamin;
  if (max_norm >= epsilon) {
    if (!state.config.fixed_delta) {
      delta = state.config.resmax / max_norm;
    }
    delta = std::clamp(delta, state.config.deltamin, state.config.deltamax);
  }

  return LegacyMechanicsState{
      .neighbor_list = neighbor_list,
      .contact_graph = contact_graph,
      .forces = forces,
      .delta = delta,
  };
}

void advance_legacy_cell_sorting_rungekutta4(
    LegacyCellSortingState& state,
    const ContactGraph& contact_graph,
    const ForceState& initial_forces,
    double delta) {
  const double half_delta = delta * 0.5;
  const double sixth_delta = delta / 6.0;
  const std::vector<double> ox = state.nodes.x;
  const std::vector<double> oy = state.nodes.y;
  const std::vector<double> oz = state.nodes.z;

  const std::vector<double> k1x = initial_forces.fx;
  const std::vector<double> k1y = initial_forces.fy;
  const std::vector<double> k1z = initial_forces.fz;

  for (std::size_t node_index = 0; node_index < state.nodes.size(); ++node_index) {
    state.nodes.x[node_index] += half_delta * k1x[node_index];
    state.nodes.y[node_index] += half_delta * k1y[node_index];
    state.nodes.z[node_index] += half_delta * k1z[node_index];
  }
  ContactGraph stage_graph = contact_graph;
  refresh_contact_graph_distances(state.nodes, stage_graph);
  const ForceState k2 = compute_mesenchymal_forces(state, stage_graph);

  for (std::size_t node_index = 0; node_index < state.nodes.size(); ++node_index) {
    state.nodes.x[node_index] += half_delta * k2.fx[node_index];
    state.nodes.y[node_index] += half_delta * k2.fy[node_index];
    state.nodes.z[node_index] += half_delta * k2.fz[node_index];
  }
  refresh_contact_graph_distances(state.nodes, stage_graph);
  const ForceState k3 = compute_mesenchymal_forces(state, stage_graph);

  for (std::size_t node_index = 0; node_index < state.nodes.size(); ++node_index) {
    state.nodes.x[node_index] += delta * k3.fx[node_index];
    state.nodes.y[node_index] += delta * k3.fy[node_index];
    state.nodes.z[node_index] += delta * k3.fz[node_index];
  }
  refresh_contact_graph_distances(state.nodes, stage_graph);
  const ForceState k4 = compute_mesenchymal_forces(state, stage_graph);

  for (std::size_t node_index = 0; node_index < state.nodes.size(); ++node_index) {
    state.nodes.x[node_index] = ox[node_index] + sixth_delta * (
        k1x[node_index] +
        (2.0 * k2.fx[node_index]) +
        (2.0 * k3.fx[node_index]) +
        k4.fx[node_index]);
    state.nodes.y[node_index] = oy[node_index] + sixth_delta * (
        k1y[node_index] +
        (2.0 * k2.fy[node_index]) +
        (2.0 * k3.fy[node_index]) +
        k4.fy[node_index]);
    state.nodes.z[node_index] = oz[node_index] + sixth_delta * (
        k1z[node_index] +
        (2.0 * k2.fz[node_index]) +
        (2.0 * k3.fz[node_index]) +
        k4.fz[node_index]);
  }
}

LegacyIterationResult advance_legacy_cell_sorting_iteration(
    LegacyCellSortingState& state,
    LegacyNoiseRuntime& noise_runtime) {
  const LegacyMechanicsState mechanics = prepare_legacy_cell_sorting_mechanics(state);
  advance_legacy_cell_sorting_rungekutta4(
      state,
      mechanics.contact_graph,
      mechanics.forces,
      mechanics.delta);
  LegacyNeighborList noise_neighbors = mechanics.neighbor_list;
  const LegacyNoiseBatchResult noise =
      apply_legacy_cell_sorting_noise_batch(
          state,
          noise_runtime,
          noise_neighbors,
          mechanics.delta);
  const LegacyNeighborList post_step_neighbors = build_legacy_neighbor_list(state);
  const ContactGraph post_step_graph = build_mesenchymal_contact_graph(post_step_neighbors);

  return LegacyIterationResult{
      .delta = mechanics.delta,
      .max_force_norm = max_force_norm(mechanics.forces),
      .contact_count = post_step_graph.size(),
      .noise = noise,
  };
}

LegacyTrajectorySummary summarize_legacy_cell_sorting_state(
    const LegacyCellSortingState& state,
    int steps,
    const LegacyNoiseBatchResult* cumulative_noise) {
  const LegacyNeighborList neighbor_list = build_legacy_neighbor_list(state);
  const ContactGraph contact_graph = build_mesenchymal_contact_graph(neighbor_list);

  double distance_sum = 0.0;
  double max_distance = 0.0;
  int type1_cell_count = 0;
  int type2_cell_count = 0;
  int neighbor_sum = 0;

  for (std::size_t node_index = 0; node_index < state.nodes.size(); ++node_index) {
    const double radius = distance_from_origin(
        state.nodes.x[node_index],
        state.nodes.y[node_index],
        state.nodes.z[node_index]);
    distance_sum += radius;
    max_distance = std::max(max_distance, radius);
    neighbor_sum += neighbor_list.counts[node_index];
  }

  for (const int adhesion_type : state.cells.adhesion_type) {
    if (adhesion_type == 1) {
      type1_cell_count += 1;
    } else if (adhesion_type == 2) {
      type2_cell_count += 1;
    }
  }

  const LegacyNoiseBatchResult zero_noise{
      .attempts = 0,
      .accepted = 0,
      .rejected = 0,
      .zero_displacement = 0,
  };
  const LegacyNoiseBatchResult& noise = cumulative_noise == nullptr ? zero_noise : *cumulative_noise;

  return LegacyTrajectorySummary{
      .steps = steps,
      .node_count = state.nodes.size(),
      .cell_count = state.cells.size(),
      .contact_count = contact_graph.size(),
      .max_distance_from_origin = max_distance,
      .mean_distance_from_origin =
          state.nodes.size() == 0 ? 0.0 : distance_sum / static_cast<double>(state.nodes.size()),
      .mean_neighbor_count =
          state.nodes.size() == 0
              ? 0.0
              : static_cast<double>(neighbor_sum) / static_cast<double>(state.nodes.size()),
      .type1_cell_count = type1_cell_count,
      .type2_cell_count = type2_cell_count,
      .total_noise_attempts = noise.attempts,
      .total_noise_accepted = noise.accepted,
      .total_noise_rejected = noise.rejected,
      .total_noise_zero_displacement = noise.zero_displacement,
  };
}

}  // namespace em2
