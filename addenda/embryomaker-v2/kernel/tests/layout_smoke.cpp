#include <cstdlib>
#include <iostream>

#include "em2/api/legacy_cell_sorting_run.hpp"
#include "em2/api/layout.hpp"
#include "em2/api/model_spec.hpp"
#include "em2/api/run_config.hpp"
#include "em2/api/runner.hpp"

int main() {
  const em2::LayoutReport layout = em2::describe_layout();
  if (layout.modules.size() != 10) {
    std::cerr << "unexpected module count\n";
    return EXIT_FAILURE;
  }
  if (layout.parity_lanes.size() != 5) {
    std::cerr << "unexpected parity lane count\n";
    return EXIT_FAILURE;
  }

  const em2::Runner runner(
      em2::ModelSpec{.name = "stub", .cell_type_count = 2, .field_count = 1},
      em2::RunConfig{.dt_mech = 0.01, .dt_field = 0.02, .dt_reg = 0.05, .checkpoint_interval = 10});

  const std::string summary = runner.summary();
  if (summary.find("model=stub") == std::string::npos) {
    std::cerr << "runner summary missing model name\n";
    return EXIT_FAILURE;
  }

  const em2::LegacyCellSortingRunResult legacy_result = em2::run_legacy_cell_sorting(
      em2::LegacyCellSortingRunConfig{.initial_seed = 1234, .noise_seed = 77, .steps = 1});
  if (legacy_result.summary.steps != 1 || legacy_result.summary.node_count != 168) {
    std::cerr << "legacy cell sorting run summary drifted\n";
    return EXIT_FAILURE;
  }

  return EXIT_SUCCESS;
}
