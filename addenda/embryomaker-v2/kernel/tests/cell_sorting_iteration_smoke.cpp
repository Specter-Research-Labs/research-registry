#include <cmath>
#include <cstdlib>
#include <iostream>
#include <vector>

#include "em2/mechanics/contact_graph.hpp"
#include "em2/mechanics/legacy_cell_sorting_noise.hpp"
#include "em2/mechanics/legacy_cell_sorting_stepper.hpp"
#include "em2/mechanics/mesenchymal_forces.hpp"
#include "em2/model/legacy_cell_sorting.hpp"

namespace {

void advance_stage_positions(
    em2::LegacyCellSortingState& state,
    const em2::ForceState& forces,
    double scale) {
  for (std::size_t node_index = 0; node_index < state.nodes.size(); ++node_index) {
    state.nodes.x[node_index] += scale * forces.fx[node_index];
    state.nodes.y[node_index] += scale * forces.fy[node_index];
    state.nodes.z[node_index] += scale * forces.fz[node_index];
  }
}

}  // namespace

int main() {
  em2::LegacyCellSortingState state = em2::build_legacy_cell_sorting_state(1234);
  em2::LegacyNoiseRuntime runtime =
      em2::make_legacy_noise_runtime(state.config.noise_sphere_partitions, 77);

  em2::LegacyCellSortingState rk4_reference_state = state;
  const em2::LegacyMechanicsState mechanics =
      em2::prepare_legacy_cell_sorting_mechanics(rk4_reference_state);
  const std::vector<double> ox = rk4_reference_state.nodes.x;
  const std::vector<double> oy = rk4_reference_state.nodes.y;
  const std::vector<double> oz = rk4_reference_state.nodes.z;
  em2::ContactGraph stage_graph = mechanics.contact_graph;
  advance_stage_positions(rk4_reference_state, mechanics.forces, mechanics.delta * 0.5);
  em2::refresh_contact_graph_distances(rk4_reference_state.nodes, stage_graph);
  const em2::ForceState k2 = em2::compute_mesenchymal_forces(rk4_reference_state, stage_graph);
  advance_stage_positions(rk4_reference_state, k2, mechanics.delta * 0.5);
  em2::refresh_contact_graph_distances(rk4_reference_state.nodes, stage_graph);
  const em2::ForceState k3 = em2::compute_mesenchymal_forces(rk4_reference_state, stage_graph);
  advance_stage_positions(rk4_reference_state, k3, mechanics.delta);
  em2::refresh_contact_graph_distances(rk4_reference_state.nodes, stage_graph);
  const em2::ForceState k4 = em2::compute_mesenchymal_forces(rk4_reference_state, stage_graph);

  const double sixth_delta = mechanics.delta / 6.0;
  for (std::size_t node_index = 0; node_index < rk4_reference_state.nodes.size(); ++node_index) {
    rk4_reference_state.nodes.x[node_index] = ox[node_index] + sixth_delta * (
        mechanics.forces.fx[node_index] +
        (2.0 * k2.fx[node_index]) +
        (2.0 * k3.fx[node_index]) +
        k4.fx[node_index]);
    rk4_reference_state.nodes.y[node_index] = oy[node_index] + sixth_delta * (
        mechanics.forces.fy[node_index] +
        (2.0 * k2.fy[node_index]) +
        (2.0 * k3.fy[node_index]) +
        k4.fy[node_index]);
    rk4_reference_state.nodes.z[node_index] = oz[node_index] + sixth_delta * (
        mechanics.forces.fz[node_index] +
        (2.0 * k2.fz[node_index]) +
        (2.0 * k3.fz[node_index]) +
        k4.fz[node_index]);
  }

  em2::LegacyCellSortingState rk4_actual_state = state;
  em2::advance_legacy_cell_sorting_rungekutta4(
      rk4_actual_state,
      mechanics.contact_graph,
      mechanics.forces,
      mechanics.delta);
  for (std::size_t node_index = 0; node_index < rk4_actual_state.nodes.size(); ++node_index) {
    if (std::abs(rk4_actual_state.nodes.x[node_index] - rk4_reference_state.nodes.x[node_index]) > 1e-12 ||
        std::abs(rk4_actual_state.nodes.y[node_index] - rk4_reference_state.nodes.y[node_index]) > 1e-12 ||
        std::abs(rk4_actual_state.nodes.z[node_index] - rk4_reference_state.nodes.z[node_index]) > 1e-12) {
      std::cerr << "rungekutta stage reset drifted\n";
      return EXIT_FAILURE;
    }
  }

  em2::LegacyCellSortingState cutoff_state = state;
  cutoff_state.nodes.x[1] = cutoff_state.nodes.x[0] + 2.0;
  cutoff_state.nodes.y[1] = cutoff_state.nodes.y[0];
  cutoff_state.nodes.z[1] = cutoff_state.nodes.z[0];
  const em2::ContactGraph cutoff_graph{
      .left = {0},
      .right = {1},
      .distance = {2.0},
  };
  const em2::ForceState cutoff_forces =
      em2::compute_mesenchymal_forces(cutoff_state, cutoff_graph);
  if (std::abs(cutoff_forces.fx[0]) > 1e-12 || std::abs(cutoff_forces.fx[1]) > 1e-12 ||
      std::abs(cutoff_forces.fy[0]) > 1e-12 || std::abs(cutoff_forces.fy[1]) > 1e-12 ||
      std::abs(cutoff_forces.fz[0]) > 1e-12 || std::abs(cutoff_forces.fz[1]) > 1e-12) {
    std::cerr << "out-of-range contact force drifted\n";
    return EXIT_FAILURE;
  }

  em2::LegacyNoiseBatchResult cumulative_noise{
      .attempts = 0,
      .accepted = 0,
      .rejected = 0,
      .zero_displacement = 0,
  };

  double total_delta = 0.0;
  double last_max_force_norm = 0.0;
  std::size_t last_contact_count = 0;
  for (int step = 0; step < 3; ++step) {
    const em2::LegacyIterationResult iteration =
        em2::advance_legacy_cell_sorting_iteration(state, runtime);
    if (std::abs(iteration.delta - state.config.deltamin) > 1e-12) {
      std::cerr << "iteration delta drifted\n";
      return EXIT_FAILURE;
    }
    if (iteration.contact_count == 0) {
      std::cerr << "iteration lost all contacts\n";
      return EXIT_FAILURE;
    }
    if (iteration.noise.attempts != 84) {
      std::cerr << "iteration noise count drifted\n";
      return EXIT_FAILURE;
    }
    total_delta += iteration.delta;
    last_max_force_norm = iteration.max_force_norm;
    last_contact_count = iteration.contact_count;
    cumulative_noise.attempts += iteration.noise.attempts;
    cumulative_noise.accepted += iteration.noise.accepted;
    cumulative_noise.rejected += iteration.noise.rejected;
    cumulative_noise.zero_displacement += iteration.noise.zero_displacement;
  }

  const em2::LegacyTrajectorySummary summary =
      em2::summarize_legacy_cell_sorting_state(state, 3, &cumulative_noise);
  if (summary.steps != 3) {
    std::cerr << "summary step count drifted\n";
    return EXIT_FAILURE;
  }
  if (summary.node_count != 168 || summary.cell_count != 21) {
    std::cerr << "summary size drifted\n";
    return EXIT_FAILURE;
  }
  if (summary.type1_cell_count + summary.type2_cell_count != 21) {
    std::cerr << "summary adhesion counts drifted\n";
    return EXIT_FAILURE;
  }
  if (summary.total_noise_attempts != 252) {
    std::cerr << "summary noise attempts drifted\n";
    return EXIT_FAILURE;
  }
  if ((summary.total_noise_accepted + summary.total_noise_rejected +
       summary.total_noise_zero_displacement) != summary.total_noise_attempts) {
    std::cerr << "summary noise accounting drifted\n";
    return EXIT_FAILURE;
  }
  if (summary.contact_count != last_contact_count) {
    std::cerr << "summary contact count drifted\n";
    return EXIT_FAILURE;
  }
  if (summary.max_distance_from_origin <= 0.0 || summary.mean_distance_from_origin <= 0.0) {
    std::cerr << "summary geometry drifted\n";
    return EXIT_FAILURE;
  }
  if (summary.mean_neighbor_count <= 0.0 || last_max_force_norm <= 0.0 || total_delta <= 0.0) {
    std::cerr << "summary dynamics drifted\n";
    return EXIT_FAILURE;
  }

  return EXIT_SUCCESS;
}
