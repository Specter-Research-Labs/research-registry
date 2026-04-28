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
          .x = 0.4,
          .y = 0.0,
          .z = 0.0,
          .eqd = 0.25,
          .add = 0.4,
          .cod = 0.0,
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
          .x = 0.4,
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

  const em2::LegacyInvaginationState state =
      em2::build_legacy_invagination_state(bootstrap_nodes);
  if (state.nodes.size() != 4 || state.cells.size() != 2) {
    std::cerr << "unexpected invagination bootstrap sizes\n";
    return EXIT_FAILURE;
  }
  if (state.nodes.altre[0] != 2 || state.nodes.pla[1] != 1.0 || state.nodes.kvol[2] != 0.0) {
    std::cerr << "legacy invagination node fields drifted\n";
    return EXIT_FAILURE;
  }
  if (std::abs(state.cells.cex[0] - 0.0) > 1e-12 || std::abs(state.cells.cey[0] - 0.1) > 1e-12 ||
      std::abs(state.cells.cex[1] - 0.4) > 1e-12 || std::abs(state.cells.cey[1] - 0.1) > 1e-12) {
    std::cerr << "legacy invagination centroids drifted\n";
    return EXIT_FAILURE;
  }
  if (state.saved_epithelial_neighbor_offsets.size() != 5 ||
      state.saved_epithelial_neighbor_indices.size() != 12 ||
      state.saved_epithelial_neighbor_offsets[1] != 3 ||
      state.saved_epithelial_neighbor_offsets[2] != 6 ||
      state.saved_epithelial_neighbor_offsets[3] != 9 ||
      state.saved_epithelial_neighbor_offsets[4] != 12 ||
      state.saved_epithelial_neighbor_indices[0] != 1 ||
      state.saved_epithelial_neighbor_indices[1] != 2 ||
      state.saved_epithelial_neighbor_indices[2] != 3 ||
      state.saved_epithelial_neighbor_indices[3] != 0 ||
      state.saved_epithelial_neighbor_indices[4] != 2 ||
      state.saved_epithelial_neighbor_indices[5] != 3 ||
      state.saved_epithelial_neighbor_indices[6] != 0 ||
      state.saved_epithelial_neighbor_indices[7] != 1 ||
      state.saved_epithelial_neighbor_indices[8] != 3 ||
      state.saved_epithelial_neighbor_indices[9] != 0 ||
      state.saved_epithelial_neighbor_indices[10] != 1 ||
      state.saved_epithelial_neighbor_indices[11] != 2) {
    std::cerr << "legacy invagination saved epithelial neighbors drifted\n";
    return EXIT_FAILURE;
  }

  const em2::LegacyInvaginationSummary summary =
      em2::summarize_legacy_invagination_state(state);
  if (summary.node_count != 4 || summary.cell_count != 2 ||
      summary.epithelial_node_count != 4 || summary.apical_node_count != 2 ||
      summary.basal_node_count != 2 || summary.paired_epithelial_node_count != 4 ||
      summary.epithelial_cell_count != 2 || summary.gene1_positive_node_count != 2 ||
      summary.gene2_positive_node_count != 2 || summary.gene1_positive_cell_count != 2 ||
      summary.gene2_positive_cell_count != 2 ||
      summary.polarized_expression_cell_count != 2 || summary.zero_pla_node_count != 2 ||
      summary.zero_kvol_node_count != 2) {
    std::cerr << "legacy invagination summary drifted\n";
    return EXIT_FAILURE;
  }
  if (std::abs(summary.mean_grd - 0.25) > 1e-12 || std::abs(summary.mean_cod - 0.025) > 1e-12 ||
      std::abs(summary.mean_pld) > 1e-12 || std::abs(summary.mean_vod) > 1e-12) {
    std::cerr << "legacy invagination means drifted\n";
    return EXIT_FAILURE;
  }

  return EXIT_SUCCESS;
}
