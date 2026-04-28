#include <cmath>
#include <cstdlib>
#include <iostream>
#include <vector>

#include "em2/model/legacy_invagination.hpp"

int main() {
  const std::vector<em2::LegacyInvaginationBootstrapNode> bootstrap_nodes{
      {
          .x = 0.0,
          .y = 0.0,
          .z = 0.0,
          .eqd = 0.25,
          .add = 0.4,
          .cod = 0.1,
          .grd = 0.25,
          .pld = 0.0,
          .vod = 0.0,
          .pla = 0.0,
          .kvol = 0.0,
          .tipus = 2,
          .icel = 1,
          .altre = 2,
          .gene1 = 0.0,
          .gene2 = 1.0,
      },
      {
          .x = 0.0,
          .y = 0.2,
          .z = 0.0,
          .eqd = 0.25,
          .add = 0.4,
          .cod = 0.0,
          .grd = 0.25,
          .pld = 0.0,
          .vod = 0.0,
          .pla = 1.0,
          .kvol = 1.0,
          .tipus = 1,
          .icel = 1,
          .altre = 1,
          .gene1 = 1.0,
          .gene2 = 0.0,
      },
      {
          .x = 1.0,
          .y = 0.0,
          .z = 0.0,
          .eqd = 0.25,
          .add = 0.4,
          .cod = 0.1,
          .grd = 0.25,
          .pld = 0.0,
          .vod = 0.0,
          .pla = 0.0,
          .kvol = 0.0,
          .tipus = 2,
          .icel = 2,
          .altre = 4,
          .gene1 = 0.0,
          .gene2 = 1.0,
      },
      {
          .x = 1.0,
          .y = 0.2,
          .z = 0.0,
          .eqd = 0.25,
          .add = 0.4,
          .cod = 0.0,
          .grd = 0.25,
          .pld = 0.0,
          .vod = 0.0,
          .pla = 1.0,
          .kvol = 1.0,
          .tipus = 1,
          .icel = 2,
          .altre = 3,
          .gene1 = 1.0,
          .gene2 = 0.0,
      },
  };

  const em2::LegacyInvaginationState state = em2::run_legacy_invagination(bootstrap_nodes, 0.05);
  if (state.nodes.size() != 4 || state.cells.size() != 2) {
    std::cerr << "unexpected invagination run sizes\n";
    return EXIT_FAILURE;
  }
  if (state.getot <= 0 || state.rtime < 0.05) {
    std::cerr << "invagination run did not advance to target time\n";
    return EXIT_FAILURE;
  }
  for (std::size_t node_index = 0; node_index < state.nodes.size(); ++node_index) {
    if (!std::isfinite(state.nodes.x[node_index]) || !std::isfinite(state.nodes.y[node_index]) ||
        !std::isfinite(state.nodes.z[node_index])) {
      std::cerr << "invagination run produced non-finite node positions\n";
      return EXIT_FAILURE;
    }
  }

  const em2::LegacyInvaginationSummary summary =
      em2::summarize_legacy_invagination_state(state);
  if (summary.getot != state.getot || summary.rtime != state.rtime ||
      summary.epithelial_node_count != 4 || summary.epithelial_cell_count != 2) {
    std::cerr << "invagination run summary drifted\n";
    return EXIT_FAILURE;
  }

  const em2::LegacyInvaginationState stepped_state =
      em2::run_legacy_invagination_steps(bootstrap_nodes, 3);
  if (stepped_state.getot != 3 || stepped_state.rtime <= 0.0) {
    std::cerr << "invagination step run did not advance exact iteration count\n";
    return EXIT_FAILURE;
  }
  if (stepped_state.step_trace.size() != 3) {
    std::cerr << "invagination step trace length drifted\n";
    return EXIT_FAILURE;
  }
  if (stepped_state.step_trace.back().getot != 3) {
    std::cerr << "invagination step trace iteration drifted\n";
    return EXIT_FAILURE;
  }
  if (std::abs(stepped_state.step_trace.back().rtime_after - stepped_state.rtime) > 1.0e-12) {
    std::cerr << "invagination step trace time drifted\n";
    return EXIT_FAILURE;
  }
  for (const em2::LegacyInvaginationStepTrace& trace : stepped_state.step_trace) {
    if (!(trace.delta > 0.0) || !(trace.max_force >= 0.0)) {
      std::cerr << "invagination step trace captured invalid force data\n";
      return EXIT_FAILURE;
    }
  }

  return EXIT_SUCCESS;
}
