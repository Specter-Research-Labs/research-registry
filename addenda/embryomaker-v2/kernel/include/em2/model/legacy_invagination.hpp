#pragma once

#include <cstddef>
#include <span>
#include <vector>

#include "em2/state/cell_state.hpp"
#include "em2/state/gene_state.hpp"
#include "em2/state/node_state.hpp"

namespace em2 {

struct LegacyInvaginationBootstrapNode {
  double x;
  double y;
  double z;
  double eqd;
  double add;
  double cod;
  double grd;
  double pld;
  double vod;
  double pla;
  double kvol;
  int tipus;
  int icel;
  int altre;
  int marge;
  int talone;
  int fix;
  double gene1;
  double gene2;
};

struct LegacyInvaginationConfig {
  int gene_count;
  double resmax;
  double deltamin;
  double deltamax;
  double maxad;
  double reqmin;
  double df_reqmax;
  double gradual_rate;
  double angletor;
  double gene1_cod;
  double gene2_cod;
  double gene1_add;
  double gene2_add;
  double you;
  double adh;
  double rep;
  double rec;
  double eqs;
  double hoo;
  double erp;
  double est;
  double mov;
  double dmo;
};

struct LegacyInvaginationStepTrace {
  int getot;
  double rtime_before;
  double delta;
  double rtime_after;
  double max_force;
  int max_force_node;
  int max_force_tipus;
  int max_force_icel;
  int max_force_same_side_neighbor_count;
  double max_force_node_x;
  double max_force_node_y;
  double max_force_node_z;
  double spring_x;
  double spring_y;
  double spring_z;
  double contact_adh_raw_x;
  double contact_adh_raw_y;
  double contact_adh_raw_z;
  double contact_adh_capped_x;
  double contact_adh_capped_y;
  double contact_adh_capped_z;
  double contact_rep_x;
  double contact_rep_y;
  double contact_rep_z;
  double torsion_x;
  double torsion_y;
  double torsion_z;
  double surface_torsion_x;
  double surface_torsion_y;
  double surface_torsion_z;
  double total_x;
  double total_y;
  double total_z;
};

struct LegacyInvaginationPairTraceEntry {
  int getot;
  int stage;
  int source_node;
  int target_node;
  int source_tipus;
  int target_tipus;
  int source_icel;
  int target_icel;
  int source_other_node;
  int target_other_node;
  int same_cell;
  int restored_only;
  int branch_code;
  int reject_code;
  int interacts;
  int twoep;
  int torsion_active;
  double distance;
  double edge_add;
  double reverse_edge_add;
  double edge_eqd;
  double reverse_edge_eqd;
  double add_cutoff;
  double deqe;
  double posca;
  double dotp;
  double vertical_distance;
  double lateral_distance;
  double fd;
  double vertical_projection;
  double force_scalar;
  double fx;
  double fy;
  double fz;
  double source_torsion_y_raw;
  double target_torsion_y_raw;
  double source_surface_torsion_y_raw;
  double target_surface_torsion_y_raw;
  double source_x;
  double source_y;
  double source_z;
  double target_x;
  double target_y;
  double target_z;
  double source_other_x;
  double source_other_y;
  double source_other_z;
  double target_other_x;
  double target_other_y;
  double target_other_z;
  double pair_dx;
  double pair_dy;
  double pair_dz;
  double source_other_dx;
  double source_other_dy;
  double source_other_dz;
  double target_other_dx;
  double target_other_dy;
  double target_other_dz;
  double mcx;
  double mcy;
  double mcz;
  double mc_norm;
  double torsion_margin;
};

struct LegacyInvaginationPairTracePair {
  int source_node;
  int target_node;
};

struct LegacyInvaginationComponentTraceEntry {
  int getot;
  int stage;
  int node;
  int tipus;
  int icel;
  int same_side_neighbor_count;
  double x;
  double y;
  double z;
  double spring_x;
  double spring_y;
  double spring_z;
  double contact_adh_raw_x;
  double contact_adh_raw_y;
  double contact_adh_raw_z;
  double contact_adh_capped_x;
  double contact_adh_capped_y;
  double contact_adh_capped_z;
  double contact_rep_x;
  double contact_rep_y;
  double contact_rep_z;
  double torsion_x;
  double torsion_y;
  double torsion_z;
  double surface_torsion_x;
  double surface_torsion_y;
  double surface_torsion_z;
  double total_x;
  double total_y;
  double total_z;
  double dex;
};

struct LegacyInvaginationState {
  LegacyInvaginationConfig config;
  NodeState nodes;
  CellState cells;
  GeneState genes;
  std::vector<int> saved_epithelial_neighbor_offsets;
  std::vector<int> saved_epithelial_neighbor_indices;
  std::vector<int> diagnostic_component_nodes;
  std::vector<int> diagnostic_pair_nodes;
  std::vector<LegacyInvaginationPairTracePair> diagnostic_pair_pairs;
  std::vector<double> last_k1x;
  std::vector<double> last_k1y;
  std::vector<double> last_k1z;
  std::vector<double> last_k2x;
  std::vector<double> last_k2y;
  std::vector<double> last_k2z;
  std::vector<double> last_k3x;
  std::vector<double> last_k3y;
  std::vector<double> last_k3z;
  std::vector<double> last_k4x;
  std::vector<double> last_k4y;
  std::vector<double> last_k4z;
  std::vector<LegacyInvaginationComponentTraceEntry> last_component_trace;
  std::vector<LegacyInvaginationPairTraceEntry> last_pair_trace;
  std::vector<LegacyInvaginationStepTrace> step_trace;
  int getot;
  double rtime;
};

struct LegacyInvaginationSummary {
  int getot;
  double rtime;
  std::size_t node_count;
  std::size_t cell_count;
  std::size_t epithelial_node_count;
  std::size_t apical_node_count;
  std::size_t basal_node_count;
  std::size_t paired_epithelial_node_count;
  std::size_t epithelial_cell_count;
  int gene1_positive_node_count;
  int gene2_positive_node_count;
  int gene1_positive_cell_count;
  int gene2_positive_cell_count;
  int polarized_expression_cell_count;
  int zero_pla_node_count;
  int zero_kvol_node_count;
  double mean_grd;
  double mean_cod;
  double mean_pld;
  double mean_vod;
};

struct LegacyInvaginationNeighborSnapshot {
  std::vector<int> offsets;
  std::vector<int> indices;
};

LegacyInvaginationConfig legacy_invagination_config();

LegacyInvaginationState build_legacy_invagination_state(
    std::span<const LegacyInvaginationBootstrapNode> bootstrap_nodes);

LegacyInvaginationState run_legacy_invagination(
    std::span<const LegacyInvaginationBootstrapNode> bootstrap_nodes,
    double target_rtime);

LegacyInvaginationState run_legacy_invagination_steps(
    std::span<const LegacyInvaginationBootstrapNode> bootstrap_nodes,
    int steps);

LegacyInvaginationState run_legacy_invagination_steps_with_original(
    std::span<const LegacyInvaginationBootstrapNode> bootstrap_nodes,
    std::span<const LegacyInvaginationBootstrapNode> original_bootstrap_nodes,
    int steps);

LegacyInvaginationState advance_legacy_invagination_steps_with_original(
    LegacyInvaginationState state,
    std::span<const LegacyInvaginationBootstrapNode> original_bootstrap_nodes,
    int steps);

LegacyInvaginationState run_legacy_invagination_steps_from_state_with_original(
    LegacyInvaginationState state,
    std::span<const LegacyInvaginationBootstrapNode> original_bootstrap_nodes,
    int steps);

LegacyInvaginationSummary summarize_legacy_invagination_state(
    const LegacyInvaginationState& state);

LegacyInvaginationNeighborSnapshot snapshot_legacy_invagination_restored_neighborhood(
    const LegacyInvaginationState& state);

}  // namespace em2
