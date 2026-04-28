#include <cmath>
#include <cstdlib>
#include <iostream>

#include "em2/mechanics/legacy_cell_sorting_noise.hpp"
#include "em2/model/legacy_cell_sorting.hpp"

namespace {

int count_moved_nodes(
    const em2::LegacyCellSortingState& before,
    const em2::LegacyCellSortingState& after) {
  int moved = 0;
  for (std::size_t node_index = 0; node_index < before.nodes.size(); ++node_index) {
    if (before.nodes.x[node_index] != after.nodes.x[node_index] ||
        before.nodes.y[node_index] != after.nodes.y[node_index] ||
        before.nodes.z[node_index] != after.nodes.z[node_index]) {
      moved += 1;
    }
  }
  return moved;
}

}  // namespace

int main() {
  const em2::LegacyCellSortingState state = em2::build_legacy_cell_sorting_state(1234);
  if (state.config.noise_sphere_partitions != 1000) {
    std::cerr << "unexpected noise sphere partition count\n";
    return EXIT_FAILURE;
  }

  const double local_energy = em2::compute_legacy_cell_sorting_local_energy(state, 0);
  if (!std::isfinite(local_energy)) {
    std::cerr << "local energy is not finite\n";
    return EXIT_FAILURE;
  }

  em2::LegacyCellSortingState stepped_state = state;
  em2::LegacyNoiseRuntime runtime = em2::make_legacy_noise_runtime(32, 77);
  const em2::LegacyNoiseStep step =
      em2::apply_legacy_cell_sorting_noise(stepped_state, runtime, stepped_state.config.deltamin);
  if (step.node_index < 0 || step.node_index >= static_cast<int>(stepped_state.nodes.size())) {
    std::cerr << "noise step chose an invalid node\n";
    return EXIT_FAILURE;
  }
  if (stepped_state.genes.gex != state.genes.gex) {
    std::cerr << "noise step changed gene state\n";
    return EXIT_FAILURE;
  }

  const int moved_nodes = count_moved_nodes(state, stepped_state);
  if (step.accepted) {
    if (moved_nodes != 1) {
      std::cerr << "accepted noise step moved an unexpected number of nodes\n";
      return EXIT_FAILURE;
    }
    const std::size_t node_index = static_cast<std::size_t>(step.node_index);
    const std::size_t cell_index = static_cast<std::size_t>(step.cell_index);
    const double scale = static_cast<double>(stepped_state.cells.nunodes[cell_index]);
    const double node_dx = stepped_state.nodes.x[node_index] - state.nodes.x[node_index];
    const double node_dy = stepped_state.nodes.y[node_index] - state.nodes.y[node_index];
    const double node_dz = stepped_state.nodes.z[node_index] - state.nodes.z[node_index];
    const double centroid_dx = stepped_state.cells.cex[cell_index] - state.cells.cex[cell_index];
    const double centroid_dy = stepped_state.cells.cey[cell_index] - state.cells.cey[cell_index];
    const double centroid_dz = stepped_state.cells.cez[cell_index] - state.cells.cez[cell_index];
    if (std::abs((centroid_dx * scale) - node_dx) > 1e-12 ||
        std::abs((centroid_dy * scale) - node_dy) > 1e-12 ||
        std::abs((centroid_dz * scale) - node_dz) > 1e-12) {
      std::cerr << "accepted noise step drifted centroid bookkeeping\n";
      return EXIT_FAILURE;
    }
  } else if (moved_nodes != 0) {
    std::cerr << "rejected noise step still moved a node\n";
    return EXIT_FAILURE;
  }

  em2::LegacyCellSortingState batch_state = state;
  em2::LegacyNoiseRuntime batch_runtime = em2::make_legacy_noise_runtime(32, 77);
  const em2::LegacyNoiseBatchResult batch =
      em2::apply_legacy_cell_sorting_noise_batch(batch_state, batch_runtime, batch_state.config.deltamin);
  if (batch.attempts != 84) {
    std::cerr << "unexpected noise batch attempt count\n";
    return EXIT_FAILURE;
  }
  if ((batch.accepted + batch.rejected + batch.zero_displacement) != batch.attempts) {
    std::cerr << "noise batch accounting drifted\n";
    return EXIT_FAILURE;
  }

  return EXIT_SUCCESS;
}
