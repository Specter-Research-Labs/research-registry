#pragma once

#include <cstdint>
#include <span>

#include "em2/core/gfortran_rng.hpp"
#include "em2/state/cell_state.hpp"
#include "em2/state/gene_state.hpp"
#include "em2/state/node_state.hpp"

namespace em2 {

struct LegacyCellSortingConfig {
  int mradi;
  int mradicel;
  int layer;
  double zmes;
  double temp;
  double desmax;
  double resmax;
  double prop_noise;
  double reqmin;
  double deltamax;
  double dmax;
  double screen_radius;
  double deltamin;
  int noise_sphere_partitions;
  int integration_mode;
  bool fixed_delta;
  bool energy_biased_noise;
  bool adaptive_timestep;
  bool cap_adhesion;
  double maxad;
  int gene_count;
  int adhesion_type_count;
  double type1_threshold;

  [[nodiscard]] int hex_cells_per_layer() const;
  [[nodiscard]] int node_count() const;
  [[nodiscard]] int cell_count() const;
};

struct LegacyCellSortingState {
  LegacyCellSortingConfig config;
  NodeState nodes;
  CellState cells;
  GeneState genes;
};

LegacyCellSortingConfig legacy_cell_sorting_config();

LegacyCellSortingState build_legacy_cell_sorting_state(GFortranRngState& rng);
LegacyCellSortingState build_legacy_cell_sorting_state(
    std::int32_t repeated_seed_word);
void apply_legacy_cell_sorting_node_positions(
    LegacyCellSortingState& state,
    std::span<const double> x,
    std::span<const double> y,
    std::span<const double> z);
void apply_legacy_cell_sorting_cell_types(
    LegacyCellSortingState& state,
    std::span<const int> adhesion_types);

}  // namespace em2
