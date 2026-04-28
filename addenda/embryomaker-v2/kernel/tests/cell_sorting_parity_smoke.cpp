#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <ranges>
#include <span>
#include <vector>

#include "em2/api/legacy_cell_sorting_run.hpp"
#include "em2/core/gfortran_rng.hpp"
#include "em2/mechanics/contact_graph.hpp"
#include "em2/mechanics/legacy_cell_sorting_stepper.hpp"
#include "em2/mechanics/legacy_neighbor_list.hpp"
#include "em2/mechanics/mesenchymal_forces.hpp"
#include "em2/model/legacy_cell_sorting.hpp"

int main() {
  const em2::LegacyCellSortingConfig config = em2::legacy_cell_sorting_config();
  if (config.cell_count() != 21) {
    std::cerr << "unexpected cell count\n";
    return EXIT_FAILURE;
  }
  if (config.node_count() != 168) {
    std::cerr << "unexpected node count\n";
    return EXIT_FAILURE;
  }
  if (!config.fixed_delta || config.integration_mode != 0 || !config.cap_adhesion) {
    std::cerr << "legacy flags drifted\n";
    return EXIT_FAILURE;
  }

  const em2::LegacyCellSortingState state = em2::build_legacy_cell_sorting_state(1234);
  if (state.cells.size() != 21 || state.nodes.size() != 168) {
    std::cerr << "unexpected built preset sizes\n";
    return EXIT_FAILURE;
  }
  if (state.genes.gene_count != 2 || state.genes.adhesion_type_count != 2) {
    std::cerr << "unexpected gene configuration\n";
    return EXIT_FAILURE;
  }

  for (std::size_t cell_index = 0; cell_index < state.cells.size(); ++cell_index) {
    const std::span<const int> cell_nodes = state.cells.nodes_for_cell(cell_index);
    if (cell_nodes.size() != 8) {
      std::cerr << "unexpected nodes per cell\n";
      return EXIT_FAILURE;
    }
    const int expected_type = state.cells.adhesion_type[cell_index];
    for (const int node_index : cell_nodes) {
      const double g1 = state.genes.expression(static_cast<std::size_t>(node_index), 0);
      const double g2 = state.genes.expression(static_cast<std::size_t>(node_index), 1);
      if (std::abs((g1 + g2) - 1.0) > 1e-9) {
        std::cerr << "gene expression is not one-hot\n";
        return EXIT_FAILURE;
      }
      if ((expected_type == 1 && g1 != 1.0) || (expected_type == 2 && g2 != 1.0)) {
        std::cerr << "cell-level adhesion type drifted across nodes\n";
        return EXIT_FAILURE;
      }
    }
  }

  const em2::LegacyCellSortingState legacy_seed_state =
      em2::build_legacy_cell_sorting_state(-11111);
  int type1_cells = 0;
  int type2_cells = 0;
  for (const int adhesion_type : legacy_seed_state.cells.adhesion_type) {
    if (adhesion_type == 1) {
      type1_cells += 1;
    } else if (adhesion_type == 2) {
      type2_cells += 1;
    }
  }
  if (type1_cells != 8 || type2_cells != 13) {
    std::cerr << "seeded legacy cell-type split drifted\n";
    return EXIT_FAILURE;
  }

  em2::LegacyCellSortingState bootstrapped_state = legacy_seed_state;
  em2::apply_legacy_cell_sorting_cell_types(
      bootstrapped_state,
      std::array<int, 21>{1, 1, 2, 2, 1, 1, 2, 2, 2, 1, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 1});
  int bootstrapped_type1 = 0;
  int bootstrapped_type2 = 0;
  for (const int adhesion_type : bootstrapped_state.cells.adhesion_type) {
    if (adhesion_type == 1) {
      bootstrapped_type1 += 1;
    } else if (adhesion_type == 2) {
      bootstrapped_type2 += 1;
    }
  }
  if (bootstrapped_type1 != 7 || bootstrapped_type2 != 14) {
    std::cerr << "bootstrapped legacy cell-type split drifted\n";
    return EXIT_FAILURE;
  }

  em2::LegacyCellSortingState repositioned_state = state;
  std::vector<double> boot_x = repositioned_state.nodes.x;
  std::vector<double> boot_y = repositioned_state.nodes.y;
  std::vector<double> boot_z = repositioned_state.nodes.z;
  boot_x[0] += 0.25;
  em2::apply_legacy_cell_sorting_node_positions(repositioned_state, boot_x, boot_y, boot_z);
  if (repositioned_state.nodes.x[0] != boot_x[0]) {
    std::cerr << "bootstrapped node positions drifted\n";
    return EXIT_FAILURE;
  }
  const std::span<const int> repositioned_cell_nodes = repositioned_state.cells.nodes_for_cell(0);
  double expected_cex = 0.0;
  for (const int node_index : repositioned_cell_nodes) {
    expected_cex += repositioned_state.nodes.x[static_cast<std::size_t>(node_index)];
  }
  expected_cex /= static_cast<double>(repositioned_cell_nodes.size());
  if (std::abs(repositioned_state.cells.cex[0] - expected_cex) > 1e-12) {
    std::cerr << "bootstrapped centroids drifted\n";
    return EXIT_FAILURE;
  }

  const em2::LegacyNeighborList neighbor_list = em2::build_legacy_neighbor_list(state);
  if (neighbor_list.size() != state.nodes.size()) {
    std::cerr << "neighbor list size drifted\n";
    return EXIT_FAILURE;
  }
  if (neighbor_list.max_count <= 0) {
    std::cerr << "neighbor list max count drifted\n";
    return EXIT_FAILURE;
  }

  std::size_t reciprocal_links = 0;
  for (std::size_t node_index = 0; node_index < neighbor_list.size(); ++node_index) {
    const std::span<const int> neighbors = neighbor_list.neighbors_for_node(node_index);
    const std::span<const double> distances = neighbor_list.distances_for_node(node_index);
    if (neighbors.size() != distances.size()) {
      std::cerr << "neighbor distances drifted\n";
      return EXIT_FAILURE;
    }
    for (std::size_t local_index = 0; local_index < neighbors.size(); ++local_index) {
      const int other = neighbors[local_index];
      const std::span<const int> reverse_neighbors =
          neighbor_list.neighbors_for_node(static_cast<std::size_t>(other));
      const bool reciprocal = std::ranges::find(
                                  reverse_neighbors,
                                  static_cast<int>(node_index)) != reverse_neighbors.end();
      if (!reciprocal) {
        std::cerr << "neighbor symmetry drifted\n";
        return EXIT_FAILURE;
      }
      if (distances[local_index] <= 0.0 || distances[local_index] > 1.0) {
        std::cerr << "neighbor distance drifted\n";
        return EXIT_FAILURE;
      }
      reciprocal_links += 1;
    }
  }
  if (reciprocal_links == 0) {
    std::cerr << "neighbor list is empty\n";
    return EXIT_FAILURE;
  }

  std::size_t asymmetric_node = state.nodes.size();
  int asymmetric_neighbor = -1;
  for (std::size_t node_index = 0; node_index < neighbor_list.size(); ++node_index) {
    const std::span<const int> neighbors = neighbor_list.neighbors_for_node(node_index);
    if (!neighbors.empty()) {
      asymmetric_node = node_index;
      asymmetric_neighbor = neighbors.front();
      break;
    }
  }
  if (asymmetric_node == state.nodes.size() || asymmetric_neighbor < 0) {
    std::cerr << "could not find a neighbor row to update\n";
    return EXIT_FAILURE;
  }

  em2::LegacyCellSortingState asymmetric_state = state;
  em2::LegacyNeighborList asymmetric_neighbors = neighbor_list;
  asymmetric_state.nodes.x[asymmetric_node] += 10.0;
  asymmetric_state.nodes.y[asymmetric_node] += 10.0;
  asymmetric_state.nodes.z[asymmetric_node] += 10.0;
  em2::rebuild_legacy_neighbor_row(
      asymmetric_state,
      asymmetric_node,
      asymmetric_neighbors);
  if (!asymmetric_neighbors.neighbors_for_node(asymmetric_node).empty()) {
    std::cerr << "single-row neighbor rebuild did not clear a displaced node\n";
    return EXIT_FAILURE;
  }
  const std::span<const int> stale_reverse_neighbors =
      asymmetric_neighbors.neighbors_for_node(static_cast<std::size_t>(asymmetric_neighbor));
  if (std::ranges::find(
          stale_reverse_neighbors,
          static_cast<int>(asymmetric_node)) == stale_reverse_neighbors.end()) {
    std::cerr << "single-row neighbor rebuild lost legacy asymmetry\n";
    return EXIT_FAILURE;
  }
  const double asymmetric_energy =
      em2::compute_legacy_cell_sorting_local_energy(
          asymmetric_state,
          asymmetric_neighbors,
          asymmetric_node);
  if (!std::isfinite(asymmetric_energy)) {
    std::cerr << "single-row neighbor rebuild broke local energy\n";
    return EXIT_FAILURE;
  }

  const em2::ContactGraph graph = em2::build_mesenchymal_contact_graph(neighbor_list);
  if (graph.size() == 0) {
    std::cerr << "contact graph is empty\n";
    return EXIT_FAILURE;
  }

  const em2::ForceState forces = em2::compute_mesenchymal_forces(state, graph);
  if (forces.interacting_pair_count != graph.size()) {
    std::cerr << "force pair count drifted\n";
    return EXIT_FAILURE;
  }
  if (forces.fx.size() != state.nodes.size() || forces.fy.size() != state.nodes.size() ||
      forces.fz.size() != state.nodes.size()) {
    std::cerr << "force vectors have the wrong size\n";
    return EXIT_FAILURE;
  }

  const double max_adhesion =
      *std::max_element(forces.adhesion_norm.begin(), forces.adhesion_norm.end());
  if (max_adhesion > (config.maxad + 1e-9)) {
    std::cerr << "adhesion cap drifted\n";
    return EXIT_FAILURE;
  }

  const bool has_force = std::ranges::any_of(forces.fx, [](double value) { return value != 0.0; }) ||
                         std::ranges::any_of(forces.fy, [](double value) { return value != 0.0; }) ||
                         std::ranges::any_of(forces.fz, [](double value) { return value != 0.0; });
  if (!has_force) {
    std::cerr << "forces are unexpectedly zero\n";
    return EXIT_FAILURE;
  }

  em2::LegacyCellSortingState stepped_state = state;
  const em2::LegacyMechanicsState mechanics = em2::prepare_legacy_cell_sorting_mechanics(stepped_state);
  if (std::abs(mechanics.delta - 1e-3) > 1e-12) {
    std::cerr << "fixed delta drifted\n";
    return EXIT_FAILURE;
  }
  em2::advance_legacy_cell_sorting_rungekutta4(
      stepped_state,
      mechanics.contact_graph,
      mechanics.forces,
      mechanics.delta);
  const bool moved = std::ranges::any_of(
      std::views::iota(std::size_t{0}, stepped_state.nodes.size()),
      [&](std::size_t node_index) {
        return stepped_state.nodes.x[node_index] != state.nodes.x[node_index] ||
               stepped_state.nodes.y[node_index] != state.nodes.y[node_index] ||
               stepped_state.nodes.z[node_index] != state.nodes.z[node_index];
      });
  if (!moved) {
    std::cerr << "rungekutta step did not move any node\n";
    return EXIT_FAILURE;
  }

  em2::GFortranRngState seeded_rng = em2::make_gfortran_rng_state(-11111);
  const em2::LegacyCellSortingState seeded_state =
      em2::build_legacy_cell_sorting_state(seeded_rng);
  const em2::LegacyNoiseRuntime seeded_runtime =
      em2::make_legacy_noise_runtime(config.noise_sphere_partitions, seeded_rng);

  em2::LegacyCellSortingState direct_state = seeded_state;
  em2::LegacyNoiseRuntime direct_runtime = seeded_runtime;
  const em2::LegacyIterationResult direct_iteration =
      em2::advance_legacy_cell_sorting_iteration(direct_state, direct_runtime);
  const em2::LegacyTrajectorySummary direct_summary =
      em2::summarize_legacy_cell_sorting_state(direct_state, 1, &direct_iteration.noise);

  std::vector<std::array<double, 3>> boot_positions;
  boot_positions.reserve(seeded_state.nodes.size());
  for (std::size_t node_index = 0; node_index < seeded_state.nodes.size(); ++node_index) {
    boot_positions.push_back(std::array<double, 3>{
        seeded_state.nodes.x[node_index],
        seeded_state.nodes.y[node_index],
        seeded_state.nodes.z[node_index],
    });
  }
  const em2::LegacyCellSortingRunResult bootstrapped_run = em2::run_legacy_cell_sorting(
      em2::LegacyCellSortingRunConfig{
          .initial_seed = -11111,
          .noise_seed = std::nullopt,
          .noise_seed_words = em2::export_gfortran_seed_words(seeded_runtime.rng),
          .initial_node_positions = boot_positions,
          .initial_cell_types = seeded_state.cells.adhesion_type,
          .steps = 1,
      });
  const em2::LegacyTrajectorySummary& boot_summary = bootstrapped_run.summary;
  if (boot_summary.contact_count != direct_summary.contact_count ||
      boot_summary.total_noise_attempts != direct_summary.total_noise_attempts ||
      boot_summary.total_noise_accepted != direct_summary.total_noise_accepted ||
      boot_summary.total_noise_rejected != direct_summary.total_noise_rejected ||
      boot_summary.total_noise_zero_displacement != direct_summary.total_noise_zero_displacement ||
      std::abs(boot_summary.max_distance_from_origin - direct_summary.max_distance_from_origin) > 1e-12 ||
      std::abs(boot_summary.mean_distance_from_origin - direct_summary.mean_distance_from_origin) > 1e-12 ||
      std::abs(boot_summary.mean_neighbor_count - direct_summary.mean_neighbor_count) > 1e-12) {
    std::cerr << "frame-zero live-seed bootstrap drifted\n";
    return EXIT_FAILURE;
  }

  return EXIT_SUCCESS;
}
