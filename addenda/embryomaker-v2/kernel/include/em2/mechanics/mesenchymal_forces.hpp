#pragma once

#include <cstddef>
#include <vector>

#include "em2/mechanics/contact_graph.hpp"

namespace em2 {

struct LegacyCellSortingState;

struct ForceState {
  std::vector<double> fx;
  std::vector<double> fy;
  std::vector<double> fz;
  std::vector<double> adhesion_norm;
  std::vector<double> repulsion_norm;
  std::size_t interacting_pair_count;
};

ForceState compute_mesenchymal_forces(
    const LegacyCellSortingState& state,
    const ContactGraph& contact_graph);

}  // namespace em2
