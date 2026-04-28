#include "em2/model/legacy_invagination.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <limits>
#include <stdexcept>
#include <unordered_map>
#include <utility>
#include <vector>

namespace em2 {
namespace {

constexpr double kEpsilon = std::numeric_limits<double>::epsilon() * 10.0;

enum PairTraceStageCode : int {
  kPairTraceStageK1 = 1,
  kPairTraceStageK2 = 2,
  kPairTraceStageK3 = 3,
  kPairTraceStageK4 = 4,
};

enum PairTraceBranchCode : int {
  kPairTraceBranchNone = 0,
  kPairTraceBranchSamePoscaPos = 1,
  kPairTraceBranchSamePoscaNonposMc0 = 2,
  kPairTraceBranchSamePoscaNonposMc = 3,
  kPairTraceBranchDiffPoscaNeg = 4,
};

enum PairTraceRejectCode : int {
  kPairTraceRejectNone = 0,
  kPairTraceRejectDistance = 1,
  kPairTraceRejectMissingOther = 2,
  kPairTraceRejectNonEpithelial = 3,
  kPairTraceRejectMcNorm = 4,
  kPairTraceRejectDiffPoscaNonneg = 5,
  kPairTraceRejectDotp = 6,
  kPairTraceRejectSpringNorm = 7,
  kPairTraceRejectDddCutoff = 8,
  kPairTraceRejectVerticalCutoff = 9,
  kPairTraceRejectLateralCutoff = 10,
};

struct ForceEvaluation {
  std::vector<double> px;
  std::vector<double> py;
  std::vector<double> pz;
  std::vector<double> dex;
  std::vector<double> spring_x;
  std::vector<double> spring_y;
  std::vector<double> spring_z;
  std::vector<double> contact_adh_raw_x;
  std::vector<double> contact_adh_raw_y;
  std::vector<double> contact_adh_raw_z;
  std::vector<double> contact_adh_capped_x;
  std::vector<double> contact_adh_capped_y;
  std::vector<double> contact_adh_capped_z;
  std::vector<double> contact_rep_x;
  std::vector<double> contact_rep_y;
  std::vector<double> contact_rep_z;
  std::vector<double> torsion_x;
  std::vector<double> torsion_y;
  std::vector<double> torsion_z;
  std::vector<double> surface_torsion_x;
  std::vector<double> surface_torsion_y;
  std::vector<double> surface_torsion_z;
  std::vector<int> same_side_neighbor_count;
};

struct LegacyInvaginationOriginalNodeState {
  std::vector<double> add;
  std::vector<double> cod;
  std::vector<double> grd;
};

struct LegacyInvaginationNeighborEdge {
  std::size_t index;
  double add;
  double eqd;
};

using LegacyInvaginationNeighborhood = std::vector<std::vector<LegacyInvaginationNeighborEdge>>;

struct GridKeyHash {
  std::size_t operator()(const std::array<int, 3>& key) const noexcept {
    std::size_t hash = std::hash<int>{}(key[0]);
    hash ^= std::hash<int>{}(key[1]) + 0x9e3779b9 + (hash << 6U) + (hash >> 2U);
    hash ^= std::hash<int>{}(key[2]) + 0x9e3779b9 + (hash << 6U) + (hash >> 2U);
    return hash;
  }
};

void recompute_cell_centroids(const NodeState& nodes, CellState& cells) {
  for (std::size_t cell_index = 0; cell_index < cells.size(); ++cell_index) {
    const std::span<const int> cell_nodes = cells.nodes_for_cell(cell_index);
    double cex = 0.0;
    double cey = 0.0;
    double cez = 0.0;
    for (const int node_index : cell_nodes) {
      cex += nodes.x[static_cast<std::size_t>(node_index)];
      cey += nodes.y[static_cast<std::size_t>(node_index)];
      cez += nodes.z[static_cast<std::size_t>(node_index)];
    }

    const double count = static_cast<double>(cell_nodes.size());
    cells.cex[cell_index] = cex / count;
    cells.cey[cell_index] = cey / count;
    cells.cez[cell_index] = cez / count;
  }
}

[[nodiscard]] double vector_norm(const double x, const double y, const double z) {
  return std::sqrt((x * x) + (y * y) + (z * z));
}

[[nodiscard]] bool is_epithelial_node(const LegacyInvaginationState& state, const std::size_t index) {
  return state.nodes.tipus[index] < 3;
}

[[nodiscard]] const LegacyInvaginationNeighborEdge* find_neighbor_edge(
    const LegacyInvaginationNeighborhood& neighborhood,
    const std::size_t source,
    const std::size_t target) {
  for (const LegacyInvaginationNeighborEdge& edge : neighborhood[source]) {
    if (edge.index == target) {
      return &edge;
    }
  }
  return nullptr;
}

[[nodiscard]] double not_applicable() {
  return std::numeric_limits<double>::quiet_NaN();
}

[[nodiscard]] bool matches_traced_pair(
    const std::span<const LegacyInvaginationPairTracePair> traced_pairs,
    const std::size_t source,
    const std::size_t target) {
  const int source_int = static_cast<int>(source);
  const int target_int = static_cast<int>(target);
  for (const LegacyInvaginationPairTracePair& pair : traced_pairs) {
    if ((pair.source_node == source_int && pair.target_node == target_int) ||
        (pair.source_node == target_int && pair.target_node == source_int)) {
      return true;
    }
  }
  return false;
}

[[nodiscard]] bool should_trace_pair(
    const std::span<const int> traced_nodes,
    const std::span<const LegacyInvaginationPairTracePair> traced_pairs,
    const std::size_t source,
    const std::size_t target) {
  const int source_int = static_cast<int>(source);
  const int target_int = static_cast<int>(target);
  if (std::find(traced_nodes.begin(), traced_nodes.end(), source_int) != traced_nodes.end() ||
      std::find(traced_nodes.begin(), traced_nodes.end(), target_int) != traced_nodes.end()) {
    return true;
  }
  return matches_traced_pair(traced_pairs, source, target);
}

[[nodiscard]] bool should_trace_node(
    const std::span<const int> traced_nodes,
    const std::size_t node) {
  return std::find(
             traced_nodes.begin(),
             traced_nodes.end(),
             static_cast<int>(node)) != traced_nodes.end();
}

[[nodiscard]] LegacyInvaginationPairTraceEntry make_pair_trace_entry(
    const LegacyInvaginationState& state,
    const LegacyInvaginationNeighborEdge& edge,
    const LegacyInvaginationNeighborEdge& reverse_edge,
    const int getot,
    const int stage,
    const std::size_t source,
    const std::size_t target) {
  return LegacyInvaginationPairTraceEntry{
      .getot = getot,
      .stage = stage,
      .source_node = static_cast<int>(source),
      .target_node = static_cast<int>(target),
      .source_tipus = state.nodes.tipus[source],
      .target_tipus = state.nodes.tipus[target],
      .source_icel = state.nodes.icel[source],
      .target_icel = state.nodes.icel[target],
      .source_other_node = -1,
      .target_other_node = -1,
      .same_cell = state.nodes.icel[source] == state.nodes.icel[target] ? 1 : 0,
      .restored_only = (std::abs(edge.add) <= kEpsilon) &&
                               (std::abs(reverse_edge.add) <= kEpsilon) &&
                               (std::abs(edge.eqd) <= kEpsilon) &&
                               (std::abs(reverse_edge.eqd) <= kEpsilon)
                           ? 1
                           : 0,
      .branch_code = kPairTraceBranchNone,
      .reject_code = kPairTraceRejectNone,
      .interacts = 0,
      .twoep = 0,
      .torsion_active = 0,
      .distance = not_applicable(),
      .edge_add = edge.add,
      .reverse_edge_add = reverse_edge.add,
      .edge_eqd = edge.eqd,
      .reverse_edge_eqd = reverse_edge.eqd,
      .add_cutoff = edge.add + reverse_edge.add,
      .deqe = edge.eqd + reverse_edge.eqd,
      .posca = not_applicable(),
      .dotp = not_applicable(),
      .vertical_distance = not_applicable(),
      .lateral_distance = not_applicable(),
      .fd = not_applicable(),
      .vertical_projection = not_applicable(),
      .force_scalar = not_applicable(),
      .fx = not_applicable(),
      .fy = not_applicable(),
      .fz = not_applicable(),
      .source_torsion_y_raw = not_applicable(),
      .target_torsion_y_raw = not_applicable(),
      .source_surface_torsion_y_raw = not_applicable(),
      .target_surface_torsion_y_raw = not_applicable(),
      .source_x = not_applicable(),
      .source_y = not_applicable(),
      .source_z = not_applicable(),
      .target_x = not_applicable(),
      .target_y = not_applicable(),
      .target_z = not_applicable(),
      .source_other_x = not_applicable(),
      .source_other_y = not_applicable(),
      .source_other_z = not_applicable(),
      .target_other_x = not_applicable(),
      .target_other_y = not_applicable(),
      .target_other_z = not_applicable(),
      .pair_dx = not_applicable(),
      .pair_dy = not_applicable(),
      .pair_dz = not_applicable(),
      .source_other_dx = not_applicable(),
      .source_other_dy = not_applicable(),
      .source_other_dz = not_applicable(),
      .target_other_dx = not_applicable(),
      .target_other_dy = not_applicable(),
      .target_other_dz = not_applicable(),
      .mcx = not_applicable(),
      .mcy = not_applicable(),
      .mcz = not_applicable(),
      .mc_norm = not_applicable(),
      .torsion_margin = not_applicable(),
  };
}

void append_neighbor_edge(
    LegacyInvaginationNeighborhood& neighborhood,
    const std::size_t source,
    const std::size_t target,
    const double add,
    const double eqd) {
  if (find_neighbor_edge(neighborhood, source, target) != nullptr) {
    return;
  }
  neighborhood[source].push_back(LegacyInvaginationNeighborEdge{
      .index = target,
      .add = add,
      .eqd = eqd,
  });
}

void save_epithelial_neighbors(
    LegacyInvaginationState& state,
    const LegacyInvaginationNeighborhood& neighborhood) {
  state.saved_epithelial_neighbor_offsets.clear();
  state.saved_epithelial_neighbor_indices.clear();
  state.saved_epithelial_neighbor_offsets.reserve(neighborhood.size() + 1);
  state.saved_epithelial_neighbor_offsets.push_back(0);
  for (std::size_t node_index = 0; node_index < neighborhood.size(); ++node_index) {
    if (is_epithelial_node(state, node_index)) {
      for (const LegacyInvaginationNeighborEdge& edge : neighborhood[node_index]) {
        if (is_epithelial_node(state, edge.index)) {
          state.saved_epithelial_neighbor_indices.push_back(static_cast<int>(edge.index));
        }
      }
    }
    state.saved_epithelial_neighbor_offsets.push_back(
        static_cast<int>(state.saved_epithelial_neighbor_indices.size()));
  }
}

LegacyInvaginationNeighborhood build_current_invagination_neighborhood(
    const LegacyInvaginationState& state,
    const std::span<const double> x,
    const std::span<const double> y,
    const std::span<const double> z) {
  const std::size_t node_count = state.nodes.size();
  LegacyInvaginationNeighborhood neighborhood(node_count);

  double max_add = 0.0;
  for (std::size_t node_index = 0; node_index < node_count; ++node_index) {
    max_add = std::max(max_add, state.nodes.add[node_index]);
  }

  const double rv = std::max(2.0 * max_add, kEpsilon);
  const double urv = 1.0 / rv;
  std::unordered_map<std::array<int, 3>, std::vector<int>, GridKeyHash> boxes;
  boxes.reserve(node_count);
  for (std::size_t node_index = 0; node_index < node_count; ++node_index) {
    boxes[{static_cast<int>(std::llround(x[node_index] * urv)),
           static_cast<int>(std::llround(y[node_index] * urv)),
           static_cast<int>(std::llround(z[node_index] * urv))}]
        .push_back(static_cast<int>(node_index));
  }

  for (std::size_t left = 0; left < node_count; ++left) {
    const std::array<int, 3> box{
        static_cast<int>(std::llround(x[left] * urv)),
        static_cast<int>(std::llround(y[left] * urv)),
        static_cast<int>(std::llround(z[left] * urv)),
    };
    for (int dz = -1; dz <= 1; ++dz) {
      for (int dy = -1; dy <= 1; ++dy) {
        for (int dx = -1; dx <= 1; ++dx) {
          const auto it = boxes.find({box[0] + dx, box[1] + dy, box[2] + dz});
          if (it == boxes.end()) {
            continue;
          }

          for (const int right_raw : it->second) {
            const std::size_t right = static_cast<std::size_t>(right_raw);
            if (right == left) {
              continue;
            }
            const double dx_pair = x[right] - x[left];
            const double dy_pair = y[right] - y[left];
            const double dz_pair = z[right] - z[left];
            const double dist_sq =
                (dx_pair * dx_pair) + (dy_pair * dy_pair) + (dz_pair * dz_pair);
            const double add_cutoff = state.nodes.add[left] + state.nodes.add[right];
            if (dist_sq > (add_cutoff * add_cutoff)) {
              continue;
            }

            append_neighbor_edge(
                neighborhood,
                left,
                right,
                state.nodes.add[left],
                state.nodes.eqd[left]);
          }
        }
      }
    }
  }

  return neighborhood;
}

std::span<const int> saved_epithelial_neighbors_for_node(
    const LegacyInvaginationState& state,
    const std::size_t node_index) {
  const std::size_t begin =
      static_cast<std::size_t>(state.saved_epithelial_neighbor_offsets[node_index]);
  const std::size_t end =
      static_cast<std::size_t>(state.saved_epithelial_neighbor_offsets[node_index + 1]);
  return std::span<const int>(state.saved_epithelial_neighbor_indices.data() + begin, end - begin);
}

bool should_skip_restored_neighbor(
    const LegacyInvaginationNeighborhood& neighborhood,
    const std::size_t source,
    const std::size_t target) {
  for (const LegacyInvaginationNeighborEdge& shared_edge : neighborhood[source]) {
    const std::size_t shared = shared_edge.index;
    if (find_neighbor_edge(neighborhood, target, shared) == nullptr) {
      continue;
    }

    for (const LegacyInvaginationNeighborEdge& second_edge : neighborhood[source]) {
      const std::size_t second = second_edge.index;
      if (second == shared) {
        continue;
      }
      if (find_neighbor_edge(neighborhood, target, second) == nullptr) {
        continue;
      }
      if (find_neighbor_edge(neighborhood, second, shared) != nullptr) {
        return true;
      }
    }
  }

  return false;
}

LegacyInvaginationNeighborhood build_restored_invagination_neighborhood(
    const LegacyInvaginationState& state,
    const std::span<const double> x,
    const std::span<const double> y,
    const std::span<const double> z) {
  LegacyInvaginationNeighborhood neighborhood =
      build_current_invagination_neighborhood(state, x, y, z);

  for (std::size_t source = 0; source < neighborhood.size(); ++source) {
    if (!is_epithelial_node(state, source)) {
      continue;
    }

    for (const int saved_target_raw : saved_epithelial_neighbors_for_node(state, source)) {
      const std::size_t target = static_cast<std::size_t>(saved_target_raw);
      if (target < source || !is_epithelial_node(state, target)) {
        continue;
      }
      if (find_neighbor_edge(neighborhood, source, target) != nullptr) {
        continue;
      }
      if (should_skip_restored_neighbor(neighborhood, source, target)) {
        continue;
      }

      // Legacy restore_neighbors appends links after fill_pol_distances, so restored
      // edges keep zero ADDe/EQDe until the next outer neighbor rebuild.
      append_neighbor_edge(neighborhood, source, target, 0.0, 0.0);
      append_neighbor_edge(neighborhood, target, source, 0.0, 0.0);
    }
  }

  return neighborhood;
}

[[nodiscard]] double clamp_delta(const LegacyInvaginationConfig& config, const double max_force) {
  if (max_force < kEpsilon) {
    return config.deltamin;
  }

  const double raw_delta = config.resmax / max_force;
  return std::clamp(raw_delta, config.deltamin, config.deltamax);
}

[[nodiscard]] double clamp_gradual(
    const double current_value,
    const double original_value,
    const double target_value,
    const double rate) {
  if (std::abs(original_value) <= kEpsilon) {
    return target_value;
  }
  const double span = std::abs(original_value) * rate;
  return std::clamp(target_value, current_value - span, current_value + span);
}

[[nodiscard]] double invagination_gene_effect(
    const LegacyInvaginationState& state,
    const std::size_t node_index,
    const double gene1_effect,
    const double gene2_effect) {
  double effect = 0.0;
  if (state.genes.gene_count >= 1) {
    effect += state.genes.expression(node_index, 0) * gene1_effect;
  }
  if (state.genes.gene_count >= 2) {
    effect += state.genes.expression(node_index, 1) * gene2_effect;
  }
  return effect;
}

void apply_invagination_nexus_gradual(
    LegacyInvaginationState& state,
    const LegacyInvaginationOriginalNodeState& original) {
  for (std::size_t node_index = 0; node_index < state.nodes.size(); ++node_index) {
    if (state.nodes.tipus[node_index] != 1) {
      continue;
    }

    const int raw_other = state.nodes.altre[node_index];
    if (raw_other <= 0) {
      continue;
    }
    const std::size_t other_index = static_cast<std::size_t>(raw_other - 1);

    state.nodes.pld[node_index] = 0.0;
    state.nodes.pld[other_index] = 0.0;
    state.nodes.vod[node_index] = 0.0;
    state.nodes.vod[other_index] = 0.0;

    state.nodes.cod[node_index] = original.cod[node_index] + invagination_gene_effect(
        state,
        node_index,
        state.config.gene1_cod,
        state.config.gene2_cod);
    state.nodes.cod[other_index] = original.cod[other_index] + invagination_gene_effect(
        state,
        other_index,
        state.config.gene1_cod,
        state.config.gene2_cod);

    const double cod_sum = state.nodes.cod[node_index] + state.nodes.cod[other_index];
    if (std::abs(cod_sum) > 1.0e-5) {
      if (std::abs(state.nodes.cod[node_index]) > std::abs(state.nodes.cod[other_index])) {
        state.nodes.vod[other_index] =
            -state.nodes.cod[node_index] * state.nodes.kvol[node_index];
      } else {
        state.nodes.vod[node_index] =
            -state.nodes.cod[other_index] * state.nodes.kvol[node_index];
      }
    }

    const double add_offset_node = state.nodes.add[node_index] - state.nodes.eqd[node_index];
    const double add_offset_other = state.nodes.add[other_index] - state.nodes.eqd[other_index];
    const double eqd_target_node = state.nodes.grd[node_index] + state.nodes.cod[node_index] +
                                   state.nodes.pld[node_index] + state.nodes.vod[node_index];
    const double eqd_target_other = state.nodes.grd[other_index] + state.nodes.cod[other_index] +
                                    state.nodes.pld[other_index] + state.nodes.vod[other_index];

    state.nodes.eqd[node_index] = std::clamp(
        clamp_gradual(
            state.nodes.eqd[node_index],
            state.nodes.eqd[node_index],
            eqd_target_node,
            state.config.gradual_rate),
        state.config.reqmin,
        state.config.df_reqmax);
    state.nodes.eqd[other_index] = std::clamp(
        clamp_gradual(
            state.nodes.eqd[other_index],
            state.nodes.eqd[other_index],
            eqd_target_other,
            state.config.gradual_rate),
        state.config.reqmin,
        state.config.df_reqmax);

    state.nodes.add[node_index] =
        std::max(state.nodes.eqd[node_index], state.nodes.eqd[node_index] + add_offset_node);
    state.nodes.add[other_index] =
        std::max(state.nodes.eqd[other_index], state.nodes.eqd[other_index] + add_offset_other);

    const double target_add_node = original.add[node_index] + invagination_gene_effect(
        state,
        node_index,
        state.config.gene1_add,
        state.config.gene2_add);
    const double target_add_other = original.add[other_index] + invagination_gene_effect(
        state,
        other_index,
        state.config.gene1_add,
        state.config.gene2_add);

    state.nodes.add[node_index] = std::max(
        0.0,
        clamp_gradual(
            state.nodes.add[node_index],
            original.add[node_index],
            target_add_node,
            state.config.gradual_rate));
    state.nodes.add[other_index] = std::max(
        0.0,
        clamp_gradual(
            state.nodes.add[other_index],
            original.add[other_index],
            target_add_other,
            state.config.gradual_rate));
  }
}

ForceEvaluation compute_invagination_forces(
    const LegacyInvaginationState& state,
    const std::span<const double> x,
    const std::span<const double> y,
    const std::span<const double> z,
    const LegacyInvaginationNeighborhood& neighborhood,
    const int getot,
    const int stage,
    std::vector<LegacyInvaginationPairTraceEntry>* pair_trace_out,
    std::vector<LegacyInvaginationComponentTraceEntry>* component_trace_out) {
  const std::size_t node_count = state.nodes.size();
  const bool trace_pairs =
      pair_trace_out != nullptr &&
      (!state.diagnostic_pair_nodes.empty() || !state.diagnostic_pair_pairs.empty());
  const bool trace_components =
      component_trace_out != nullptr && !state.diagnostic_component_nodes.empty();
  ForceEvaluation evaluation{
      .px = std::vector<double>(node_count, 0.0),
      .py = std::vector<double>(node_count, 0.0),
      .pz = std::vector<double>(node_count, 0.0),
      .dex = std::vector<double>(node_count, 0.0),
      .spring_x = std::vector<double>(node_count, 0.0),
      .spring_y = std::vector<double>(node_count, 0.0),
      .spring_z = std::vector<double>(node_count, 0.0),
      .contact_adh_raw_x = std::vector<double>(node_count, 0.0),
      .contact_adh_raw_y = std::vector<double>(node_count, 0.0),
      .contact_adh_raw_z = std::vector<double>(node_count, 0.0),
      .contact_adh_capped_x = std::vector<double>(node_count, 0.0),
      .contact_adh_capped_y = std::vector<double>(node_count, 0.0),
      .contact_adh_capped_z = std::vector<double>(node_count, 0.0),
      .contact_rep_x = std::vector<double>(node_count, 0.0),
      .contact_rep_y = std::vector<double>(node_count, 0.0),
      .contact_rep_z = std::vector<double>(node_count, 0.0),
      .torsion_x = std::vector<double>(node_count, 0.0),
      .torsion_y = std::vector<double>(node_count, 0.0),
      .torsion_z = std::vector<double>(node_count, 0.0),
      .surface_torsion_x = std::vector<double>(node_count, 0.0),
      .surface_torsion_y = std::vector<double>(node_count, 0.0),
      .surface_torsion_z = std::vector<double>(node_count, 0.0),
      .same_side_neighbor_count = std::vector<int>(node_count, 0),
  };
  std::vector<double> spring_x(node_count, 0.0);
  std::vector<double> spring_y(node_count, 0.0);
  std::vector<double> spring_z(node_count, 0.0);
  std::vector<double> contact_adh_x(node_count, 0.0);
  std::vector<double> contact_adh_y(node_count, 0.0);
  std::vector<double> contact_adh_z(node_count, 0.0);
  std::vector<double> contact_rep_x(node_count, 0.0);
  std::vector<double> contact_rep_y(node_count, 0.0);
  std::vector<double> contact_rep_z(node_count, 0.0);
  std::vector<double> torsion_x(node_count, 0.0);
  std::vector<double> torsion_y(node_count, 0.0);
  std::vector<double> torsion_z(node_count, 0.0);
  std::vector<double> surface_torsion_x(node_count, 0.0);
  std::vector<double> surface_torsion_y(node_count, 0.0);
  std::vector<double> surface_torsion_z(node_count, 0.0);
  std::vector<int> same_side_neighbor_count(node_count, 0);

  for (std::size_t node_index = 0; node_index < node_count; ++node_index) {
    if (state.nodes.fix[node_index] == 2) {
      continue;
    }

    if (state.nodes.tipus[node_index] >= 3) {
      continue;
    }

    const int raw_other = state.nodes.altre[node_index];
    if (raw_other <= 0) {
      continue;
    }
    const std::size_t other_index = static_cast<std::size_t>(raw_other - 1);
    const double cx = x[other_index] - x[node_index];
    const double cy = y[other_index] - y[node_index];
    const double cz = z[other_index] - z[node_index];
    const double distance = vector_norm(cx, cy, cz);
    if (distance <= kEpsilon) {
      continue;
    }

    const double inverse_distance = 1.0 / distance;
    const double ddd =
        distance - state.nodes.eqs[node_index] - state.nodes.eqs[other_index];
    const double force = 2.0 * state.nodes.hoo[node_index] * ddd;
    spring_x[node_index] = force * cx * inverse_distance;
    spring_y[node_index] = force * cy * inverse_distance;
    spring_z[node_index] = force * cz * inverse_distance;
  }

  for (std::size_t nod = 0; nod < node_count; ++nod) {
    if (state.nodes.fix[nod] == 2) {
      continue;
    }

    for (const LegacyInvaginationNeighborEdge& edge : neighborhood[nod]) {
      const std::size_t ic = edge.index;
      if (ic < nod && state.nodes.fix[ic] != 2) {
        continue;
      }

      const LegacyInvaginationNeighborEdge* reverse_edge =
          find_neighbor_edge(neighborhood, ic, nod);
      if (reverse_edge == nullptr) {
        continue;
      }
      const bool trace_pair =
          trace_pairs &&
          should_trace_pair(
              state.diagnostic_pair_nodes,
              state.diagnostic_pair_pairs,
              nod,
              ic);
      LegacyInvaginationPairTraceEntry trace_entry{};
      if (trace_pair) {
        trace_entry = make_pair_trace_entry(state, edge, *reverse_edge, getot, stage, nod, ic);
      }
      const auto emit_trace = [&]() {
        if (trace_pair) {
          pair_trace_out->push_back(trace_entry);
        }
      };

      const double ix = x[nod];
      const double iy = y[nod];
      const double iz = z[nod];
      const double bx = x[ic];
      const double by = y[ic];
      const double bz = z[ic];
      const double dx_pair = bx - ix;
      const double dy_pair = by - iy;
      const double dz_pair = bz - iz;
      const double distance = vector_norm(dx_pair, dy_pair, dz_pair);
      if (trace_pair) {
        trace_entry.source_x = ix;
        trace_entry.source_y = iy;
        trace_entry.source_z = iz;
        trace_entry.target_x = bx;
        trace_entry.target_y = by;
        trace_entry.target_z = bz;
        trace_entry.distance = distance;
        trace_entry.pair_dx = dx_pair;
        trace_entry.pair_dy = dy_pair;
        trace_entry.pair_dz = dz_pair;
      }
      if (distance <= kEpsilon) {
        if (trace_pair) {
          trace_entry.reject_code = kPairTraceRejectDistance;
          emit_trace();
        }
        continue;
      }
      const double inverse_distance = 1.0 / distance;

      const int raw_other_nod = state.nodes.altre[nod];
      const int raw_other_ic = state.nodes.altre[ic];
      if (raw_other_nod <= 0 || raw_other_ic <= 0) {
        if (trace_pair) {
          trace_entry.reject_code = kPairTraceRejectMissingOther;
          emit_trace();
        }
        continue;
      }
      const std::size_t other_nod = static_cast<std::size_t>(raw_other_nod - 1);
      const std::size_t other_ic = static_cast<std::size_t>(raw_other_ic - 1);
      const int tipus_nod = state.nodes.tipus[nod];
      const int tipus_ic = state.nodes.tipus[ic];

      const double cx = x[other_nod] - ix;
      const double cy = y[other_nod] - iy;
      const double cz = z[other_nod] - iz;
      const double icx = x[other_ic] - bx;
      const double icy = y[other_ic] - by;
      const double icz = z[other_ic] - bz;
      const double posca = (icx * cx) + (icy * cy) + (icz * cz);
      if (trace_pair) {
        trace_entry.source_other_node = static_cast<int>(other_nod);
        trace_entry.target_other_node = static_cast<int>(other_ic);
        trace_entry.source_other_x = x[other_nod];
        trace_entry.source_other_y = y[other_nod];
        trace_entry.source_other_z = z[other_nod];
        trace_entry.target_other_x = x[other_ic];
        trace_entry.target_other_y = y[other_ic];
        trace_entry.target_other_z = z[other_ic];
        trace_entry.source_other_dx = cx;
        trace_entry.source_other_dy = cy;
        trace_entry.source_other_dz = cz;
        trace_entry.target_other_dx = icx;
        trace_entry.target_other_dy = icy;
        trace_entry.target_other_dz = icz;
        trace_entry.posca = posca;
      }

      double uvx = 0.0;
      double uvy = 0.0;
      double uvz = 0.0;
      double fd = 0.0;
      double dotp = 0.0;
      double mcx = 0.0;
      double mcy = 0.0;
      double mcz = 0.0;
      double md = 0.0;
      int twoep = 0;

      bool interacts = false;

      if (tipus_nod < 3 && tipus_ic < 3) {
        if (tipus_nod == tipus_ic) {
          if (posca > kEpsilon) {
            if (trace_pair) {
              trace_entry.branch_code = kPairTraceBranchSamePoscaPos;
            }
            mcx = icx + cx;
            mcy = icy + cy;
            mcz = icz + cz;
            const double mc_norm = vector_norm(mcx, mcy, mcz);
            if (trace_pair) {
              trace_entry.mcx = mcx;
              trace_entry.mcy = mcy;
              trace_entry.mcz = mcz;
              trace_entry.mc_norm = mc_norm;
            }
            if (mc_norm <= kEpsilon) {
              if (trace_pair) {
                trace_entry.reject_code = kPairTraceRejectMcNorm;
                emit_trace();
              }
              continue;
            }
            md = 1.0 / mc_norm;
            dotp = (mcx * dx_pair) + (mcy * dy_pair) + (mcz * dz_pair);
            const double vertical_distance = std::abs(dotp) * md;
            double lateral_sq =
                (distance * distance) - (vertical_distance * vertical_distance);
            if (lateral_sq < kEpsilon) {
              lateral_sq = kEpsilon;
            }
            const double lateral_distance = std::sqrt(lateral_sq);
            const double pesco = dotp * md * md;
            const double inverse_lateral = 1.0 / lateral_distance;
            uvx = (dx_pair - (mcx * pesco)) * inverse_lateral;
            uvy = (dy_pair - (mcy * pesco)) * inverse_lateral;
            uvz = (dz_pair - (mcz * pesco)) * inverse_lateral;
            fd = lateral_distance;
            twoep = 1;
            same_side_neighbor_count[nod] += 1;
            same_side_neighbor_count[ic] += 1;
            interacts = true;
            if (trace_pair) {
              trace_entry.dotp = dotp;
              trace_entry.vertical_distance = vertical_distance;
              trace_entry.lateral_distance = lateral_distance;
            }
          } else {
            mcx = icx + cx;
            mcy = icy + cy;
            mcz = icz + cz;
            const double mc_sq = (mcx * mcx) + (mcy * mcy) + (mcz * mcz);
            const double add_cutoff = edge.add + reverse_edge->add;
            if (trace_pair) {
              trace_entry.mcx = mcx;
              trace_entry.mcy = mcy;
              trace_entry.mcz = mcz;
            }
            if (mc_sq < kEpsilon) {
              if (trace_pair) {
                trace_entry.branch_code = kPairTraceBranchSamePoscaNonposMc0;
              }
              dotp = (cx * dx_pair) + (cy * dy_pair) + (cz * dz_pair);
              if (dotp >= kEpsilon) {
                if (trace_pair) {
                  trace_entry.dotp = dotp;
                  trace_entry.reject_code = kPairTraceRejectDotp;
                  emit_trace();
                }
                continue;
              }
              const double spring_norm = vector_norm(cx, cy, cz);
              if (spring_norm <= kEpsilon) {
                if (trace_pair) {
                  trace_entry.dotp = dotp;
                  trace_entry.reject_code = kPairTraceRejectSpringNorm;
                  emit_trace();
                }
                continue;
              }
              const double inverse_spring = 1.0 / spring_norm;
              const double ddd = -dotp * inverse_spring;
              if (ddd - add_cutoff >= kEpsilon) {
                if (trace_pair) {
                  trace_entry.dotp = dotp;
                  trace_entry.vertical_distance = ddd;
                  trace_entry.lateral_distance = distance;
                  trace_entry.reject_code = kPairTraceRejectDddCutoff;
                  emit_trace();
                }
                continue;
              }
              double lateral_sq = (distance * distance);
              if (lateral_sq < kEpsilon) {
                lateral_sq = kEpsilon;
              }
              fd = std::sqrt(lateral_sq);
              uvx = -cx * inverse_spring;
              uvy = -cy * inverse_spring;
              uvz = -cz * inverse_spring;
              twoep = 2;
              interacts = true;
              if (trace_pair) {
                trace_entry.dotp = dotp;
                trace_entry.vertical_distance = ddd;
                trace_entry.lateral_distance = distance;
              }
            } else {
              if (trace_pair) {
                trace_entry.branch_code = kPairTraceBranchSamePoscaNonposMc;
                trace_entry.mc_norm = std::sqrt(mc_sq);
              }
              md = 1.0 / std::sqrt(mc_sq);
              dotp = (mcx * dx_pair) + (mcy * dy_pair) + (mcz * dz_pair);
              const double vertical_distance = std::abs(dotp) * md;
              if (vertical_distance - add_cutoff >= kEpsilon) {
                if (trace_pair) {
                  trace_entry.dotp = dotp;
                  trace_entry.vertical_distance = vertical_distance;
                  trace_entry.reject_code = kPairTraceRejectVerticalCutoff;
                  emit_trace();
                }
                continue;
              }
              double lateral_sq =
                  (distance * distance) - (vertical_distance * vertical_distance);
              if (lateral_sq < kEpsilon) {
                lateral_sq = kEpsilon;
              }
              const double lateral_distance = std::sqrt(lateral_sq);
              if (lateral_distance - add_cutoff > kEpsilon) {
                if (trace_pair) {
                  trace_entry.dotp = dotp;
                  trace_entry.vertical_distance = vertical_distance;
                  trace_entry.lateral_distance = lateral_distance;
                  trace_entry.reject_code = kPairTraceRejectLateralCutoff;
                  emit_trace();
                }
                continue;
              }
              const double pesco = dotp * md * md;
              const double inverse_lateral = 1.0 / lateral_distance;
              uvx = (dx_pair - (mcx * pesco)) * inverse_lateral;
              uvy = (dy_pair - (mcy * pesco)) * inverse_lateral;
              uvz = (dz_pair - (mcz * pesco)) * inverse_lateral;
              fd = lateral_distance;
              twoep = 2;
              interacts = true;
              if (trace_pair) {
                trace_entry.dotp = dotp;
                trace_entry.vertical_distance = vertical_distance;
                trace_entry.lateral_distance = lateral_distance;
              }
            }
          }
        } else if (posca < 0.0) {
          if (trace_pair) {
            trace_entry.branch_code = kPairTraceBranchDiffPoscaNeg;
          }
          dotp = (cx * dx_pair) + (cy * dy_pair) + (cz * dz_pair);
          if (dotp >= kEpsilon) {
            if (trace_pair) {
              trace_entry.dotp = dotp;
              trace_entry.reject_code = kPairTraceRejectDotp;
              emit_trace();
            }
            continue;
          }
          const double spring_norm = vector_norm(cx, cy, cz);
          if (spring_norm <= kEpsilon) {
            if (trace_pair) {
              trace_entry.dotp = dotp;
              trace_entry.reject_code = kPairTraceRejectSpringNorm;
              emit_trace();
            }
            continue;
          }
          const double inverse_spring = 1.0 / spring_norm;
          const double ddd = -dotp * inverse_spring;
          const double add_cutoff = edge.add + reverse_edge->add;
          if (ddd - add_cutoff >= kEpsilon) {
            if (trace_pair) {
              trace_entry.dotp = dotp;
              trace_entry.vertical_distance = ddd;
              trace_entry.reject_code = kPairTraceRejectDddCutoff;
              emit_trace();
            }
            continue;
          }
          double lateral_sq = (distance * distance) - (ddd * ddd);
          if (lateral_sq < kEpsilon) {
            lateral_sq = kEpsilon;
          }
          const double lateral_distance = std::sqrt(lateral_sq);
          if (lateral_distance - add_cutoff > kEpsilon) {
            if (trace_pair) {
              trace_entry.dotp = dotp;
              trace_entry.vertical_distance = ddd;
              trace_entry.lateral_distance = lateral_distance;
              trace_entry.reject_code = kPairTraceRejectLateralCutoff;
              emit_trace();
            }
            continue;
          }
          uvx = cx * inverse_spring;
          uvy = cy * inverse_spring;
          uvz = cz * inverse_spring;
          fd = ddd;
          twoep = 2;
          interacts = true;
          if (trace_pair) {
            trace_entry.dotp = dotp;
            trace_entry.vertical_distance = ddd;
            trace_entry.lateral_distance = lateral_distance;
          }
        } else if (trace_pair) {
          trace_entry.reject_code = kPairTraceRejectDiffPoscaNonneg;
          emit_trace();
          continue;
        }
      } else {
        if (trace_pair) {
          trace_entry.reject_code = kPairTraceRejectNonEpithelial;
          emit_trace();
        }
        continue;
      }

      if (!interacts) {
        if (trace_pair) {
          emit_trace();
        }
        continue;
      }

      const double deqe = edge.eqd + reverse_edge->eqd;
      if (trace_pair) {
        trace_entry.interacts = 1;
        trace_entry.twoep = twoep;
        trace_entry.dotp = dotp;
        trace_entry.fd = fd;
        trace_entry.source_torsion_y_raw = 0.0;
        trace_entry.target_torsion_y_raw = 0.0;
        trace_entry.source_surface_torsion_y_raw = 0.0;
        trace_entry.target_surface_torsion_y_raw = 0.0;
      }
      double force_scalar = 0.0;
      if (state.nodes.icel[nod] == state.nodes.icel[ic]) {
        if ((fd - deqe) < -kEpsilon) {
          force_scalar =
              (state.nodes.rep[nod] + state.nodes.rep[ic]) * (fd - deqe);
        } else {
          force_scalar =
              (state.nodes.you[nod] + state.nodes.you[ic]) * (fd - deqe);
        }
      } else if ((fd - deqe) < -kEpsilon) {
        force_scalar =
            (state.nodes.rec[nod] + state.nodes.rec[ic]) * (fd - deqe);
      } else {
        const double adhesion = 0.5 * (state.nodes.adh[nod] + state.nodes.adh[ic]);
        force_scalar = 2.0 * adhesion * (fd - deqe);
      }

      const double fx = force_scalar * uvx;
      const double fy = force_scalar * uvy;
      const double fz = force_scalar * uvz;
      if (trace_pair) {
        trace_entry.force_scalar = force_scalar;
        trace_entry.fx = fx;
        trace_entry.fy = fy;
        trace_entry.fz = fz;
      }
      if (force_scalar > 0.0) {
        contact_adh_x[nod] += fx;
        contact_adh_y[nod] += fy;
        contact_adh_z[nod] += fz;
        contact_adh_x[ic] -= fx;
        contact_adh_y[ic] -= fy;
        contact_adh_z[ic] -= fz;
      } else {
        contact_rep_x[nod] += fx;
        contact_rep_y[nod] += fy;
        contact_rep_z[nod] += fz;
        contact_rep_x[ic] -= fx;
        contact_rep_y[ic] -= fy;
        contact_rep_z[ic] -= fz;
      }

      if (twoep == 1) {
        const double vertical_projection = dotp * md;
        const double torsion_margin =
            std::abs(vertical_projection) - (state.config.angletor * distance);
        if (trace_pair) {
          trace_entry.vertical_projection = vertical_projection;
          trace_entry.torsion_margin = torsion_margin;
        }
        if (torsion_margin > kEpsilon) {
          if (trace_pair) {
            trace_entry.torsion_active = 1;
          }
          const double uv_mcx = mcx * md;
          const double uv_mcy = mcy * md;
          const double uv_mcz = mcz * md;
          const double surface_force =
              (state.nodes.est[nod] + state.nodes.est[ic]) * vertical_projection;
          const double source_surface_torsion_x = surface_force * uv_mcx;
          const double source_surface_torsion_y = surface_force * uv_mcy;
          const double source_surface_torsion_z = surface_force * uv_mcz;
          const double target_surface_torsion_x = -source_surface_torsion_x;
          const double target_surface_torsion_y = -source_surface_torsion_y;
          const double target_surface_torsion_z = -source_surface_torsion_z;
          surface_torsion_x[nod] += source_surface_torsion_x;
          surface_torsion_y[nod] += source_surface_torsion_y;
          surface_torsion_z[nod] += source_surface_torsion_z;
          surface_torsion_x[ic] += target_surface_torsion_x;
          surface_torsion_y[ic] += target_surface_torsion_y;
          surface_torsion_z[ic] += target_surface_torsion_z;
          if (trace_pair) {
            trace_entry.source_surface_torsion_y_raw = source_surface_torsion_y;
            trace_entry.target_surface_torsion_y_raw = target_surface_torsion_y;
          }

          const double spring_norm_nod = vector_norm(cx, cy, cz);
          const double spring_norm_ic = vector_norm(icx, icy, icz);
          if (spring_norm_nod > kEpsilon && spring_norm_ic > kEpsilon) {
            const double nod_vertical =
                ((cx * dx_pair) + (cy * dy_pair) + (cz * dz_pair)) /
                spring_norm_nod;
            const double parallel_force =
                (state.nodes.erp[nod] + state.nodes.erp[ic]) * nod_vertical;
            const double uv_pair_x = dx_pair * inverse_distance;
            const double uv_pair_y = dy_pair * inverse_distance;
            const double uv_pair_z = dz_pair * inverse_distance;
            const double source_torsion_x = parallel_force * uv_pair_x;
            const double source_torsion_y = parallel_force * uv_pair_y;
            const double source_torsion_z = parallel_force * uv_pair_z;
            torsion_x[nod] += source_torsion_x;
            torsion_y[nod] += source_torsion_y;
            torsion_z[nod] += source_torsion_z;

            const double ic_vertical =
                -((icx * dx_pair) + (icy * dy_pair) + (icz * dz_pair)) /
                spring_norm_ic;
            const double reverse_parallel_force =
                (state.nodes.erp[nod] + state.nodes.erp[ic]) * ic_vertical;
            const double target_torsion_x = -reverse_parallel_force * uv_pair_x;
            const double target_torsion_y = -reverse_parallel_force * uv_pair_y;
            const double target_torsion_z = -reverse_parallel_force * uv_pair_z;
            torsion_x[ic] += target_torsion_x;
            torsion_y[ic] += target_torsion_y;
            torsion_z[ic] += target_torsion_z;
            if (trace_pair) {
              trace_entry.source_torsion_y_raw = source_torsion_y;
              trace_entry.target_torsion_y_raw = target_torsion_y;
            }
          }
        }
      }
      if (trace_pair) {
        emit_trace();
      }
    }
  }

  for (std::size_t node_index = 0; node_index < node_count; ++node_index) {
    if (state.nodes.fix[node_index] == 2) {
      evaluation.px[node_index] = 0.0;
      evaluation.py[node_index] = 0.0;
      evaluation.pz[node_index] = 0.0;
      evaluation.dex[node_index] = 0.0;
      continue;
    }

    double capped_adh_x = contact_adh_x[node_index];
    double capped_adh_y = contact_adh_y[node_index];
    double capped_adh_z = contact_adh_z[node_index];
    const double adhesion_norm = vector_norm(capped_adh_x, capped_adh_y, capped_adh_z);
    if (adhesion_norm > state.config.maxad) {
      const double scale = state.config.maxad / adhesion_norm;
      capped_adh_x *= scale;
      capped_adh_y *= scale;
      capped_adh_z *= scale;
    }

    double torsion_contrib_x = 0.0;
    double torsion_contrib_y = 0.0;
    double torsion_contrib_z = 0.0;
    double surface_torsion_contrib_x = 0.0;
    double surface_torsion_contrib_y = 0.0;
    double surface_torsion_contrib_z = 0.0;
    double fx = spring_x[node_index] + capped_adh_x + contact_rep_x[node_index];
    double fy = spring_y[node_index] + capped_adh_y + contact_rep_y[node_index];
    double fz = spring_z[node_index] + capped_adh_z + contact_rep_z[node_index];
    if (same_side_neighbor_count[node_index] > 0) {
      const double inverse_neighbor_count =
          1.0 / static_cast<double>(same_side_neighbor_count[node_index]);
      fx += (torsion_x[node_index] + surface_torsion_x[node_index]) *
            inverse_neighbor_count;
      fy += (torsion_y[node_index] + surface_torsion_y[node_index]) *
            inverse_neighbor_count;
      fz += (torsion_z[node_index] + surface_torsion_z[node_index]) *
            inverse_neighbor_count;
      torsion_contrib_x = torsion_x[node_index] * inverse_neighbor_count;
      torsion_contrib_y = torsion_y[node_index] * inverse_neighbor_count;
      torsion_contrib_z = torsion_z[node_index] * inverse_neighbor_count;
      surface_torsion_contrib_x = surface_torsion_x[node_index] * inverse_neighbor_count;
      surface_torsion_contrib_y = surface_torsion_y[node_index] * inverse_neighbor_count;
      surface_torsion_contrib_z = surface_torsion_z[node_index] * inverse_neighbor_count;
    }

    evaluation.spring_x[node_index] = spring_x[node_index];
    evaluation.spring_y[node_index] = spring_y[node_index];
    evaluation.spring_z[node_index] = spring_z[node_index];
    evaluation.contact_adh_raw_x[node_index] = contact_adh_x[node_index];
    evaluation.contact_adh_raw_y[node_index] = contact_adh_y[node_index];
    evaluation.contact_adh_raw_z[node_index] = contact_adh_z[node_index];
    evaluation.contact_adh_capped_x[node_index] = capped_adh_x;
    evaluation.contact_adh_capped_y[node_index] = capped_adh_y;
    evaluation.contact_adh_capped_z[node_index] = capped_adh_z;
    evaluation.contact_rep_x[node_index] = contact_rep_x[node_index];
    evaluation.contact_rep_y[node_index] = contact_rep_y[node_index];
    evaluation.contact_rep_z[node_index] = contact_rep_z[node_index];
    evaluation.torsion_x[node_index] = torsion_contrib_x;
    evaluation.torsion_y[node_index] = torsion_contrib_y;
    evaluation.torsion_z[node_index] = torsion_contrib_z;
    evaluation.surface_torsion_x[node_index] = surface_torsion_contrib_x;
    evaluation.surface_torsion_y[node_index] = surface_torsion_contrib_y;
    evaluation.surface_torsion_z[node_index] = surface_torsion_contrib_z;
    evaluation.same_side_neighbor_count[node_index] = same_side_neighbor_count[node_index];
    evaluation.px[node_index] = fx;
    evaluation.py[node_index] = fy;
    evaluation.pz[node_index] = fz;
    evaluation.dex[node_index] = vector_norm(fx, fy, fz);
    if (trace_components && should_trace_node(state.diagnostic_component_nodes, node_index)) {
      component_trace_out->push_back(LegacyInvaginationComponentTraceEntry{
          .getot = getot,
          .stage = stage,
          .node = static_cast<int>(node_index),
          .tipus = state.nodes.tipus[node_index],
          .icel = state.nodes.icel[node_index],
          .same_side_neighbor_count = same_side_neighbor_count[node_index],
          .x = x[node_index],
          .y = y[node_index],
          .z = z[node_index],
          .spring_x = spring_x[node_index],
          .spring_y = spring_y[node_index],
          .spring_z = spring_z[node_index],
          .contact_adh_raw_x = contact_adh_x[node_index],
          .contact_adh_raw_y = contact_adh_y[node_index],
          .contact_adh_raw_z = contact_adh_z[node_index],
          .contact_adh_capped_x = capped_adh_x,
          .contact_adh_capped_y = capped_adh_y,
          .contact_adh_capped_z = capped_adh_z,
          .contact_rep_x = contact_rep_x[node_index],
          .contact_rep_y = contact_rep_y[node_index],
          .contact_rep_z = contact_rep_z[node_index],
          .torsion_x = torsion_contrib_x,
          .torsion_y = torsion_contrib_y,
          .torsion_z = torsion_contrib_z,
          .surface_torsion_x = surface_torsion_contrib_x,
          .surface_torsion_y = surface_torsion_contrib_y,
          .surface_torsion_z = surface_torsion_contrib_z,
          .total_x = fx,
          .total_y = fy,
          .total_z = fz,
          .dex = evaluation.dex[node_index],
      });
    }
  }

  return evaluation;
}

void run_invagination_runge_kutta_step(
    LegacyInvaginationState& state,
    const LegacyInvaginationNeighborhood& neighborhood,
    const ForceEvaluation& k1,
    const double delta) {
  const std::size_t node_count = state.nodes.size();
  const double half_delta = delta * 0.5;
  const double sixth_delta = delta / 6.0;
  std::vector<double> original_x = state.nodes.x;
  std::vector<double> original_y = state.nodes.y;
  std::vector<double> original_z = state.nodes.z;

  for (std::size_t node_index = 0; node_index < node_count; ++node_index) {
    state.nodes.x[node_index] += half_delta * k1.px[node_index];
    state.nodes.y[node_index] += half_delta * k1.py[node_index];
    state.nodes.z[node_index] += half_delta * k1.pz[node_index];
  }
  const ForceEvaluation k2 = compute_invagination_forces(
      state,
      state.nodes.x,
      state.nodes.y,
      state.nodes.z,
      neighborhood,
      state.getot,
      kPairTraceStageK2,
      &state.last_pair_trace,
      &state.last_component_trace);

  for (std::size_t node_index = 0; node_index < node_count; ++node_index) {
    state.nodes.x[node_index] += half_delta * k2.px[node_index];
    state.nodes.y[node_index] += half_delta * k2.py[node_index];
    state.nodes.z[node_index] += half_delta * k2.pz[node_index];
  }
  const ForceEvaluation k3 = compute_invagination_forces(
      state,
      state.nodes.x,
      state.nodes.y,
      state.nodes.z,
      neighborhood,
      state.getot,
      kPairTraceStageK3,
      &state.last_pair_trace,
      &state.last_component_trace);

  for (std::size_t node_index = 0; node_index < node_count; ++node_index) {
    state.nodes.x[node_index] += delta * k3.px[node_index];
    state.nodes.y[node_index] += delta * k3.py[node_index];
    state.nodes.z[node_index] += delta * k3.pz[node_index];
  }
  const ForceEvaluation k4 = compute_invagination_forces(
      state,
      state.nodes.x,
      state.nodes.y,
      state.nodes.z,
      neighborhood,
      state.getot,
      kPairTraceStageK4,
      &state.last_pair_trace,
      &state.last_component_trace);

  state.last_k1x = k1.px;
  state.last_k1y = k1.py;
  state.last_k1z = k1.pz;
  state.last_k2x = k2.px;
  state.last_k2y = k2.py;
  state.last_k2z = k2.pz;
  state.last_k3x = k3.px;
  state.last_k3y = k3.py;
  state.last_k3z = k3.pz;
  state.last_k4x = k4.px;
  state.last_k4y = k4.py;
  state.last_k4z = k4.pz;

  for (std::size_t node_index = 0; node_index < node_count; ++node_index) {
    state.nodes.x[node_index] = original_x[node_index] +
                                sixth_delta * (k1.px[node_index] + (2.0 * k2.px[node_index]) +
                                               (2.0 * k3.px[node_index]) + k4.px[node_index]);
    state.nodes.y[node_index] = original_y[node_index] +
                                sixth_delta * (k1.py[node_index] + (2.0 * k2.py[node_index]) +
                                               (2.0 * k3.py[node_index]) + k4.py[node_index]);
    state.nodes.z[node_index] = original_z[node_index] +
                                sixth_delta * (k1.pz[node_index] + (2.0 * k2.pz[node_index]) +
                                               (2.0 * k3.pz[node_index]) + k4.pz[node_index]);
  }
}

LegacyInvaginationOriginalNodeState capture_original_node_state(
    const LegacyInvaginationState& state) {
  return LegacyInvaginationOriginalNodeState{
      .add = state.nodes.add,
      .cod = state.nodes.cod,
      .grd = state.nodes.grd,
  };
}

void advance_legacy_invagination_step(
    LegacyInvaginationState& state,
    const LegacyInvaginationOriginalNodeState& original) {
  state.getot += 1;
  state.last_component_trace.clear();
  state.last_pair_trace.clear();
  recompute_cell_centroids(state.nodes, state.cells);
  const LegacyInvaginationNeighborhood neighborhood =
      build_restored_invagination_neighborhood(
          state,
          state.nodes.x,
          state.nodes.y,
          state.nodes.z);
  // Legacy restore_neighbors ends by replacing the saved epithelial ledger
  // with the restored neighborhood for the next outer step.
  save_epithelial_neighbors(state, neighborhood);
  const ForceEvaluation k1 = compute_invagination_forces(
      state,
      state.nodes.x,
      state.nodes.y,
      state.nodes.z,
      neighborhood,
      state.getot,
      kPairTraceStageK1,
      &state.last_pair_trace,
      &state.last_component_trace);
  const auto max_force_it = std::max_element(k1.dex.begin(), k1.dex.end());
  const double max_force = *max_force_it;
  const std::size_t max_force_node =
      static_cast<std::size_t>(std::distance(k1.dex.begin(), max_force_it));
  const double rtime_before = state.rtime;
  const double max_force_node_x = state.nodes.x[max_force_node];
  const double max_force_node_y = state.nodes.y[max_force_node];
  const double max_force_node_z = state.nodes.z[max_force_node];
  const double delta = clamp_delta(state.config, max_force);
  apply_invagination_nexus_gradual(state, original);
  run_invagination_runge_kutta_step(state, neighborhood, k1, delta);
  state.rtime += delta;
  state.step_trace.push_back(LegacyInvaginationStepTrace{
      .getot = state.getot,
      .rtime_before = rtime_before,
      .delta = delta,
      .rtime_after = state.rtime,
      .max_force = max_force,
      .max_force_node = static_cast<int>(max_force_node),
      .max_force_tipus = state.nodes.tipus[max_force_node],
      .max_force_icel = state.nodes.icel[max_force_node],
      .max_force_same_side_neighbor_count = k1.same_side_neighbor_count[max_force_node],
      .max_force_node_x = max_force_node_x,
      .max_force_node_y = max_force_node_y,
      .max_force_node_z = max_force_node_z,
      .spring_x = k1.spring_x[max_force_node],
      .spring_y = k1.spring_y[max_force_node],
      .spring_z = k1.spring_z[max_force_node],
      .contact_adh_raw_x = k1.contact_adh_raw_x[max_force_node],
      .contact_adh_raw_y = k1.contact_adh_raw_y[max_force_node],
      .contact_adh_raw_z = k1.contact_adh_raw_z[max_force_node],
      .contact_adh_capped_x = k1.contact_adh_capped_x[max_force_node],
      .contact_adh_capped_y = k1.contact_adh_capped_y[max_force_node],
      .contact_adh_capped_z = k1.contact_adh_capped_z[max_force_node],
      .contact_rep_x = k1.contact_rep_x[max_force_node],
      .contact_rep_y = k1.contact_rep_y[max_force_node],
      .contact_rep_z = k1.contact_rep_z[max_force_node],
      .torsion_x = k1.torsion_x[max_force_node],
      .torsion_y = k1.torsion_y[max_force_node],
      .torsion_z = k1.torsion_z[max_force_node],
      .surface_torsion_x = k1.surface_torsion_x[max_force_node],
      .surface_torsion_y = k1.surface_torsion_y[max_force_node],
      .surface_torsion_z = k1.surface_torsion_z[max_force_node],
      .total_x = k1.px[max_force_node],
      .total_y = k1.py[max_force_node],
      .total_z = k1.pz[max_force_node],
  });
}

}  // namespace

LegacyInvaginationConfig legacy_invagination_config() {
  return LegacyInvaginationConfig{
      .gene_count = 2,
      .resmax = 1.0e-3,
      .deltamin = 1.0e-3,
      .deltamax = 1.0e-2,
      .maxad = 5.0,
      .reqmin = 0.05,
      .df_reqmax = 0.5,
      .gradual_rate = 0.005,
      .angletor = 0.0,
      .gene1_cod = 0.10,
      .gene2_cod = -0.10,
      .gene1_add = 0.15,
      .gene2_add = 0.10,
      .you = 5.0,
      .adh = 5.0,
      .rep = 50.0,
      .rec = 50.0,
      .eqs = 0.25,
      .hoo = 10.0,
      .erp = 20.0,
      .est = 60.0,
      .mov = 0.1,
      .dmo = 0.01,
  };
}

LegacyInvaginationState build_legacy_invagination_state(
    const std::span<const LegacyInvaginationBootstrapNode> bootstrap_nodes) {
  if (bootstrap_nodes.empty()) {
    throw std::invalid_argument("legacy invagination bootstrap requires at least one node");
  }

  const LegacyInvaginationConfig config = legacy_invagination_config();
  LegacyInvaginationState state{
      .config = config,
      .nodes = {},
      .cells = {},
      .genes =
          GeneState{
              .gene_count = config.gene_count,
              .adhesion_type_count = 0,
              .adhesion_type_by_gene = {},
              .kadh = {},
              .gex = {},
          },
      .saved_epithelial_neighbor_offsets = {},
      .saved_epithelial_neighbor_indices = {},
      .diagnostic_component_nodes = {},
      .diagnostic_pair_nodes = {},
      .diagnostic_pair_pairs = {},
      .last_k1x = {},
      .last_k1y = {},
      .last_k1z = {},
      .last_k2x = {},
      .last_k2y = {},
      .last_k2z = {},
      .last_k3x = {},
      .last_k3y = {},
      .last_k3z = {},
      .last_k4x = {},
      .last_k4y = {},
      .last_k4z = {},
      .last_component_trace = {},
      .last_pair_trace = {},
      .step_trace = {},
      .getot = 0,
      .rtime = 0.0,
  };

  const std::size_t node_count = bootstrap_nodes.size();
  state.nodes.x.reserve(node_count);
  state.nodes.y.reserve(node_count);
  state.nodes.z.reserve(node_count);
  state.nodes.e.reserve(node_count);
  state.nodes.orix.reserve(node_count);
  state.nodes.oriy.reserve(node_count);
  state.nodes.oriz.reserve(node_count);
  state.nodes.eqd.reserve(node_count);
  state.nodes.add.reserve(node_count);
  state.nodes.you.reserve(node_count);
  state.nodes.adh.reserve(node_count);
  state.nodes.rep.reserve(node_count);
  state.nodes.rec.reserve(node_count);
  state.nodes.cod.reserve(node_count);
  state.nodes.grd.reserve(node_count);
  state.nodes.pld.reserve(node_count);
  state.nodes.vod.reserve(node_count);
  state.nodes.eqs.reserve(node_count);
  state.nodes.hoo.reserve(node_count);
  state.nodes.erp.reserve(node_count);
  state.nodes.est.reserve(node_count);
  state.nodes.mov.reserve(node_count);
  state.nodes.dmo.reserve(node_count);
  state.nodes.dif.reserve(node_count);
  state.nodes.pla.reserve(node_count);
  state.nodes.kvol.reserve(node_count);
  state.nodes.tipus.reserve(node_count);
  state.nodes.icel.reserve(node_count);
  state.nodes.altre.reserve(node_count);
  state.nodes.marge.reserve(node_count);
  state.nodes.talone.reserve(node_count);
  state.nodes.fix.reserve(node_count);
  state.genes.gex.reserve(node_count * static_cast<std::size_t>(config.gene_count));

  int max_cell_index = 0;
  for (const LegacyInvaginationBootstrapNode& node : bootstrap_nodes) {
    if (node.icel <= 0) {
      throw std::invalid_argument("legacy invagination bootstrap requires positive cell ids");
    }
    max_cell_index = std::max(max_cell_index, node.icel);
  }

  std::vector<std::vector<int>> cell_nodes(static_cast<std::size_t>(max_cell_index + 1));
  for (std::size_t node_index = 0; node_index < bootstrap_nodes.size(); ++node_index) {
    const LegacyInvaginationBootstrapNode& node = bootstrap_nodes[node_index];
    state.nodes.x.push_back(node.x);
    state.nodes.y.push_back(node.y);
    state.nodes.z.push_back(node.z);
    state.nodes.e.push_back(0.0);
    state.nodes.orix.push_back(node.x);
    state.nodes.oriy.push_back(node.y);
    state.nodes.oriz.push_back(node.z);
    state.nodes.eqd.push_back(node.eqd);
    state.nodes.add.push_back(node.add);
    state.nodes.you.push_back(config.you);
    state.nodes.adh.push_back(config.adh);
    state.nodes.rep.push_back(config.rep);
    state.nodes.rec.push_back(config.rec);
    state.nodes.cod.push_back(node.cod);
    state.nodes.grd.push_back(node.grd);
    state.nodes.pld.push_back(node.pld);
    state.nodes.vod.push_back(node.vod);
    state.nodes.eqs.push_back(config.eqs);
    state.nodes.hoo.push_back(config.hoo);
    state.nodes.erp.push_back(config.erp);
    state.nodes.est.push_back(config.est);
    state.nodes.mov.push_back(config.mov);
    state.nodes.dmo.push_back(config.dmo);
    state.nodes.dif.push_back(0.0);
    state.nodes.pla.push_back(node.pla);
    state.nodes.kvol.push_back(node.kvol);
    state.nodes.tipus.push_back(node.tipus);
    state.nodes.icel.push_back(node.icel);
    state.nodes.altre.push_back(node.altre);
    state.nodes.marge.push_back(node.marge);
    state.nodes.talone.push_back(node.talone);
    state.nodes.fix.push_back(node.fix);
    state.genes.gex.push_back(node.gene1);
    state.genes.gex.push_back(node.gene2);
    cell_nodes[static_cast<std::size_t>(node.icel)].push_back(static_cast<int>(node_index));
  }

  state.cells.minsize_for_div.reserve(static_cast<std::size_t>(max_cell_index));
  state.cells.maxsize_for_div.reserve(static_cast<std::size_t>(max_cell_index));
  state.cells.cex.assign(static_cast<std::size_t>(max_cell_index), 0.0);
  state.cells.cey.assign(static_cast<std::size_t>(max_cell_index), 0.0);
  state.cells.cez.assign(static_cast<std::size_t>(max_cell_index), 0.0);
  state.cells.fase.assign(static_cast<std::size_t>(max_cell_index), 0.0);
  state.cells.nunodes.reserve(static_cast<std::size_t>(max_cell_index));
  state.cells.ctipus.assign(static_cast<std::size_t>(max_cell_index), 1);
  state.cells.adhesion_type.assign(static_cast<std::size_t>(max_cell_index), 0);
  state.cells.node_offsets.reserve(static_cast<std::size_t>(max_cell_index + 1));
  state.cells.node_indices.reserve(node_count);

  int offset = 0;
  state.cells.node_offsets.push_back(offset);
  for (int cell_index = 1; cell_index <= max_cell_index; ++cell_index) {
    const std::vector<int>& nodes_for_cell = cell_nodes[static_cast<std::size_t>(cell_index)];
    if (nodes_for_cell.empty()) {
      throw std::invalid_argument("legacy invagination bootstrap cell ids must stay contiguous");
    }
    state.cells.minsize_for_div.push_back(0.0);
    state.cells.maxsize_for_div.push_back(0.0);
    state.cells.nunodes.push_back(static_cast<int>(nodes_for_cell.size()));
    state.cells.node_indices.insert(
        state.cells.node_indices.end(),
        nodes_for_cell.begin(),
        nodes_for_cell.end());
    offset += static_cast<int>(nodes_for_cell.size());
    state.cells.node_offsets.push_back(offset);
  }

  recompute_cell_centroids(state.nodes, state.cells);
  const LegacyInvaginationNeighborhood initial_neighborhood =
      build_current_invagination_neighborhood(state, state.nodes.x, state.nodes.y, state.nodes.z);
  state.saved_epithelial_neighbor_indices.reserve(initial_neighborhood.size() * 8U);
  save_epithelial_neighbors(state, initial_neighborhood);
  const LegacyInvaginationNeighborhood restored_initial_neighborhood =
      build_restored_invagination_neighborhood(state, state.nodes.x, state.nodes.y, state.nodes.z);
  save_epithelial_neighbors(state, restored_initial_neighborhood);
  return state;
}

LegacyInvaginationState run_legacy_invagination(
    const std::span<const LegacyInvaginationBootstrapNode> bootstrap_nodes,
    const double target_rtime) {
  if (target_rtime < 0.0) {
    throw std::invalid_argument("legacy invagination target_rtime must be non-negative");
  }

  LegacyInvaginationState state = build_legacy_invagination_state(bootstrap_nodes);
  if (target_rtime <= 0.0) {
    return state;
  }

  const LegacyInvaginationOriginalNodeState original = capture_original_node_state(state);
  while (state.rtime < target_rtime) {
    advance_legacy_invagination_step(state, original);
  }

  recompute_cell_centroids(state.nodes, state.cells);
  return state;
}

LegacyInvaginationState run_legacy_invagination_steps(
    const std::span<const LegacyInvaginationBootstrapNode> bootstrap_nodes,
    const int steps) {
  if (steps < 0) {
    throw std::invalid_argument("legacy invagination step count must be non-negative");
  }

  LegacyInvaginationState state = build_legacy_invagination_state(bootstrap_nodes);
  if (steps == 0) {
    return state;
  }

  const LegacyInvaginationOriginalNodeState original = capture_original_node_state(state);
  for (int step = 0; step < steps; ++step) {
    advance_legacy_invagination_step(state, original);
  }

  recompute_cell_centroids(state.nodes, state.cells);
  return state;
}

LegacyInvaginationState run_legacy_invagination_steps_with_original(
    const std::span<const LegacyInvaginationBootstrapNode> bootstrap_nodes,
    const std::span<const LegacyInvaginationBootstrapNode> original_bootstrap_nodes,
    const int steps) {
  if (steps < 0) {
    throw std::invalid_argument("legacy invagination step count must be non-negative");
  }

  LegacyInvaginationState state = build_legacy_invagination_state(bootstrap_nodes);
  return advance_legacy_invagination_steps_with_original(
      std::move(state),
      original_bootstrap_nodes,
      steps);
}

LegacyInvaginationState advance_legacy_invagination_steps_with_original(
    LegacyInvaginationState state,
    const std::span<const LegacyInvaginationBootstrapNode> original_bootstrap_nodes,
    const int steps) {
  if (steps < 0) {
    throw std::invalid_argument("legacy invagination step count must be non-negative");
  }
  if (steps == 0) {
    return state;
  }

  const LegacyInvaginationState original_state =
      build_legacy_invagination_state(original_bootstrap_nodes);
  const LegacyInvaginationOriginalNodeState original =
      capture_original_node_state(original_state);
  for (int step = 0; step < steps; ++step) {
    advance_legacy_invagination_step(state, original);
  }

  recompute_cell_centroids(state.nodes, state.cells);
  return state;
}

LegacyInvaginationState run_legacy_invagination_steps_from_state_with_original(
    LegacyInvaginationState state,
    const std::span<const LegacyInvaginationBootstrapNode> original_bootstrap_nodes,
    const int steps) {
  if (steps < 0) {
    throw std::invalid_argument("legacy invagination step count must be non-negative");
  }
  if (steps == 0) {
    recompute_cell_centroids(state.nodes, state.cells);
    return state;
  }

  const LegacyInvaginationState original_state =
      build_legacy_invagination_state(original_bootstrap_nodes);
  const LegacyInvaginationOriginalNodeState original =
      capture_original_node_state(original_state);
  for (int step = 0; step < steps; ++step) {
    advance_legacy_invagination_step(state, original);
  }

  recompute_cell_centroids(state.nodes, state.cells);
  return state;
}

LegacyInvaginationSummary summarize_legacy_invagination_state(
    const LegacyInvaginationState& state) {
  std::size_t epithelial_node_count = 0;
  std::size_t apical_node_count = 0;
  std::size_t basal_node_count = 0;
  std::size_t paired_epithelial_node_count = 0;
  int gene1_positive_node_count = 0;
  int gene2_positive_node_count = 0;
  int zero_pla_node_count = 0;
  int zero_kvol_node_count = 0;
  double grd_sum = 0.0;
  double cod_sum = 0.0;
  double pld_sum = 0.0;
  double vod_sum = 0.0;
  std::vector<bool> epithelial_cells(state.cells.size(), false);
  std::vector<bool> gene1_cells(state.cells.size(), false);
  std::vector<bool> gene2_cells(state.cells.size(), false);

  for (std::size_t node_index = 0; node_index < state.nodes.size(); ++node_index) {
    const int tipus = state.nodes.tipus[node_index];
    if (tipus != 1 && tipus != 2) {
      continue;
    }

    epithelial_node_count += 1;
    if (tipus == 2) {
      apical_node_count += 1;
    } else {
      basal_node_count += 1;
    }
    if (state.nodes.altre[node_index] > 0) {
      paired_epithelial_node_count += 1;
    }
    if (state.nodes.pla[node_index] == 0.0) {
      zero_pla_node_count += 1;
    }
    if (state.nodes.kvol[node_index] == 0.0) {
      zero_kvol_node_count += 1;
    }

    grd_sum += state.nodes.grd[node_index];
    cod_sum += state.nodes.cod[node_index];
    pld_sum += state.nodes.pld[node_index];
    vod_sum += state.nodes.vod[node_index];

    const double gene1 = state.genes.expression(node_index, 0);
    const double gene2 = state.genes.expression(node_index, 1);
    if (gene1 > 0.0) {
      gene1_positive_node_count += 1;
    }
    if (gene2 > 0.0) {
      gene2_positive_node_count += 1;
    }

    const int raw_cell_index = state.nodes.icel[node_index];
    if (raw_cell_index <= 0) {
      continue;
    }
    const std::size_t cell_index = static_cast<std::size_t>(raw_cell_index - 1);
    epithelial_cells[cell_index] = true;
    gene1_cells[cell_index] = gene1_cells[cell_index] || gene1 > 0.0;
    gene2_cells[cell_index] = gene2_cells[cell_index] || gene2 > 0.0;
  }

  int epithelial_cell_count = 0;
  int gene1_positive_cell_count = 0;
  int gene2_positive_cell_count = 0;
  int polarized_expression_cell_count = 0;
  for (std::size_t cell_index = 0; cell_index < state.cells.size(); ++cell_index) {
    if (epithelial_cells[cell_index]) {
      epithelial_cell_count += 1;
    }
    if (gene1_cells[cell_index]) {
      gene1_positive_cell_count += 1;
    }
    if (gene2_cells[cell_index]) {
      gene2_positive_cell_count += 1;
    }
    if (gene1_cells[cell_index] && gene2_cells[cell_index]) {
      polarized_expression_cell_count += 1;
    }
  }

  const double count = static_cast<double>(epithelial_node_count);
  return LegacyInvaginationSummary{
      .getot = state.getot,
      .rtime = state.rtime,
      .node_count = state.nodes.size(),
      .cell_count = state.cells.size(),
      .epithelial_node_count = epithelial_node_count,
      .apical_node_count = apical_node_count,
      .basal_node_count = basal_node_count,
      .paired_epithelial_node_count = paired_epithelial_node_count,
      .epithelial_cell_count = static_cast<std::size_t>(epithelial_cell_count),
      .gene1_positive_node_count = gene1_positive_node_count,
      .gene2_positive_node_count = gene2_positive_node_count,
      .gene1_positive_cell_count = gene1_positive_cell_count,
      .gene2_positive_cell_count = gene2_positive_cell_count,
      .polarized_expression_cell_count = polarized_expression_cell_count,
      .zero_pla_node_count = zero_pla_node_count,
      .zero_kvol_node_count = zero_kvol_node_count,
      .mean_grd = epithelial_node_count == 0 ? 0.0 : grd_sum / count,
      .mean_cod = epithelial_node_count == 0 ? 0.0 : cod_sum / count,
      .mean_pld = epithelial_node_count == 0 ? 0.0 : pld_sum / count,
      .mean_vod = epithelial_node_count == 0 ? 0.0 : vod_sum / count,
  };
}

LegacyInvaginationNeighborSnapshot snapshot_legacy_invagination_restored_neighborhood(
    const LegacyInvaginationState& state) {
  const LegacyInvaginationNeighborhood neighborhood =
      build_restored_invagination_neighborhood(state, state.nodes.x, state.nodes.y, state.nodes.z);

  LegacyInvaginationNeighborSnapshot snapshot{
      .offsets = {},
      .indices = {},
  };
  snapshot.offsets.reserve(neighborhood.size() + 1);
  snapshot.offsets.push_back(0);
  for (const auto& edges : neighborhood) {
    for (const LegacyInvaginationNeighborEdge& edge : edges) {
      snapshot.indices.push_back(static_cast<int>(edge.index));
    }
    snapshot.offsets.push_back(static_cast<int>(snapshot.indices.size()));
  }
  return snapshot;
}

}  // namespace em2
