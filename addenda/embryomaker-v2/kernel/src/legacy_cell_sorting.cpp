#include "em2/model/legacy_cell_sorting.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <numbers>
#include <stdexcept>
#include <utility>
#include <vector>

#include "em2/core/gfortran_rng.hpp"
#include "em2/core/vec3.hpp"

namespace em2 {
namespace {

struct DraftCell {
  std::vector<int> nodes;
};

void push_mesenchymal_node(NodeState& nodes, const Vec3& point, int cell_index) {
  nodes.x.push_back(point.x);
  nodes.y.push_back(point.y);
  nodes.z.push_back(point.z);
  nodes.e.push_back(0.0);
  nodes.orix.push_back(point.x);
  nodes.oriy.push_back(point.y);
  nodes.oriz.push_back(point.z);
  nodes.eqd.push_back(0.25);
  nodes.add.push_back(0.5);
  nodes.you.push_back(60.0);
  nodes.adh.push_back(0.0);
  nodes.rep.push_back(60.0);
  nodes.rec.push_back(80.0);
  nodes.cod.push_back(0.0);
  nodes.grd.push_back(0.25);
  nodes.pld.push_back(0.0);
  nodes.vod.push_back(0.0);
  nodes.eqs.push_back(0.25);
  nodes.hoo.push_back(0.0);
  nodes.erp.push_back(1.0);
  nodes.est.push_back(0.0);
  nodes.mov.push_back(5.0);
  nodes.dmo.push_back(0.05);
  nodes.dif.push_back(0.0);
  nodes.pla.push_back(0.0);
  nodes.kvol.push_back(0.0);
  nodes.tipus.push_back(3);
  nodes.icel.push_back(cell_index);
  nodes.altre.push_back(0);
  nodes.marge.push_back(1);
  nodes.talone.push_back(0);
  nodes.fix.push_back(0);
}

Vec3 legacy_shell_offset(double radius, int selector, int& sign, GFortranRngState& rng) {
  double xx = 0.0;
  double yy = 0.0;
  double zz = 0.0;
  // Legacy mesenq burns one random draw into an unused local before xx/yy.
  static_cast<void>(gfortran_random_r8(rng));
  while (true) {
    xx = radius * (1.0 - (2.0 * gfortran_random_r8(rng)));
    yy = radius * (1.0 - (2.0 * gfortran_random_r8(rng)));
    const double zz_sq = (radius * radius) - (xx * xx) - (yy * yy);
    if (zz_sq < 0.0) {
      continue;
    }
    zz = static_cast<double>(sign) * std::sqrt(zz_sq);
    sign *= -1;
    break;
  }

  if ((selector % 3) == 0) {
    return Vec3{.x = zz, .y = xx, .z = yy};
  }
  if ((selector % 3) == 1) {
    return Vec3{.x = xx, .y = zz, .z = yy};
  }
  return Vec3{.x = xx, .y = yy, .z = zz};
}

void append_mesenchymal_cell(
    NodeState& nodes,
    std::vector<DraftCell>& cells,
    const Vec3& center,
    int nodes_per_cell,
    double shell_radius,
    bool use_global_selector,
    GFortranRngState& rng) {
  DraftCell cell;
  cell.nodes.reserve(static_cast<std::size_t>(nodes_per_cell));
  push_mesenchymal_node(nodes, center, static_cast<int>(cells.size()));
  cell.nodes.push_back(static_cast<int>(nodes.size() - 1));

  int sign = 1;
  for (int k = 2; k <= nodes_per_cell; ++k) {
    const int selector = use_global_selector ? static_cast<int>(nodes.size() + 1) : (k - 1);
    const Vec3 offset = legacy_shell_offset(shell_radius, selector, sign, rng);
    push_mesenchymal_node(
        nodes,
        Vec3{.x = center.x + offset.x, .y = center.y + offset.y, .z = center.z + offset.z},
        static_cast<int>(cells.size()));
    cell.nodes.push_back(static_cast<int>(nodes.size() - 1));
  }

  cells.push_back(std::move(cell));
}

void assign_cell_centroids_and_nuclei(NodeState& nodes, CellState& cells) {
  const double max_distance = std::numeric_limits<double>::max();
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
    cex /= count;
    cey /= count;
    cez /= count;
    cells.cex[cell_index] = cex;
    cells.cey[cell_index] = cey;
    cells.cez[cell_index] = cez;

    double best_distance = max_distance;
    std::size_t best_local_index = 0;
    for (std::size_t local_index = 0; local_index < cell_nodes.size(); ++local_index) {
      const int node_index = cell_nodes[local_index];
      const double dx = cex - nodes.x[static_cast<std::size_t>(node_index)];
      const double dy = cey - nodes.y[static_cast<std::size_t>(node_index)];
      const double dz = cez - nodes.z[static_cast<std::size_t>(node_index)];
      const double distance = std::sqrt((dx * dx) + (dy * dy) + (dz * dz));
      if (distance < best_distance) {
        best_distance = distance;
        best_local_index = local_index;
      }
    }

    const std::size_t begin = static_cast<std::size_t>(cells.node_offsets[cell_index]);
    const std::size_t nucleus_index = begin + best_local_index;
    nodes.marge[static_cast<std::size_t>(cells.node_indices[nucleus_index])] = 0;
    std::swap(cells.node_indices[begin], cells.node_indices[nucleus_index]);
  }
}

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

}  // namespace

int LegacyCellSortingConfig::hex_cells_per_layer() const {
  int j = 0;
  for (int i = 1; i < mradicel; ++i) {
    j += i;
  }
  return (6 * j) + 1;
}

int LegacyCellSortingConfig::node_count() const { return mradi * cell_count(); }

int LegacyCellSortingConfig::cell_count() const { return hex_cells_per_layer() * layer; }

LegacyCellSortingConfig legacy_cell_sorting_config() {
  return LegacyCellSortingConfig{
      .mradi = 8,
      .mradicel = 2,
      .layer = 3,
      .zmes = 0.0,
      .temp = 5.0,
      .desmax = 5e-2,
      .resmax = 1e-3,
      .prop_noise = 0.5,
      .reqmin = 0.05,
      .deltamax = 1e-2,
      .dmax = 1.0,
      .screen_radius = 0.7,
      .deltamin = 1e-3,
      .noise_sphere_partitions = 1000,
      .integration_mode = 0,
      .fixed_delta = true,
      .energy_biased_noise = true,
      .adaptive_timestep = false,
      .cap_adhesion = true,
      .maxad = 50.0,
      .gene_count = 2,
      .adhesion_type_count = 2,
      .type1_threshold = 0.7,
  };
}

LegacyCellSortingState build_legacy_cell_sorting_state(GFortranRngState& rng) {
  const LegacyCellSortingConfig config = legacy_cell_sorting_config();
  if (config.mradi <= 0 || config.mradicel <= 0 || config.layer <= 0) {
    throw std::invalid_argument("legacy cell sorting preset requires positive mesenchymal dimensions");
  }
  LegacyCellSortingState state{
      .config = config,
      .nodes = {},
      .cells = {},
      .genes =
          GeneState{
              .gene_count = config.gene_count,
              .adhesion_type_count = config.adhesion_type_count,
              .adhesion_type_by_gene = {1, 2},
              .kadh = {100.0, 10.0, 10.0, 1.0},
              .gex = {},
          },
  };

  state.nodes.x.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.y.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.z.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.e.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.orix.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.oriy.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.oriz.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.eqd.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.add.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.you.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.adh.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.rep.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.rec.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.cod.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.grd.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.pld.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.vod.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.eqs.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.hoo.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.erp.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.est.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.mov.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.dmo.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.dif.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.pla.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.kvol.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.tipus.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.icel.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.altre.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.marge.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.talone.reserve(static_cast<std::size_t>(config.node_count()));
  state.nodes.fix.reserve(static_cast<std::size_t>(config.node_count()));

  const double degrees = std::numbers::pi_v<double> / 180.0;
  const double de = 0.25 * 2.0;
  const double di = (2.0 * de) + (2.0 * de * std::cos(60.0 * degrees));
  std::vector<DraftCell> draft_cells;
  draft_cells.reserve(static_cast<std::size_t>(config.cell_count()));

  for (int layer_index = 0; layer_index < config.layer; ++layer_index) {
    const Vec3 origin{.x = 0.0, .y = 0.0, .z = config.zmes - (di * static_cast<double>(layer_index))};
    append_mesenchymal_cell(state.nodes, draft_cells, origin, config.mradi, de, false, rng);

    for (int radial_cell = 2; radial_cell <= config.mradicel; ++radial_cell) {
      double dx1 = 0.0;
      double dx2 = 0.0;
      double dy1 = 0.0;
      double dy2 = 0.0;

      for (int sector = 1; sector <= 6; ++sector) {
        if (sector == 1) {
          dx2 = 0.0;
          dy2 = di * (static_cast<double>(radial_cell) - 1.0);
          dx1 = di * (static_cast<double>(radial_cell) - 1.0) * std::sin(-60.0 * degrees);
          dy1 = di * (static_cast<double>(radial_cell) - 1.0) * std::cos(-60.0 * degrees);
        } else {
          const double hip = di * (static_cast<double>(radial_cell) - 1.0);
          dx1 = dx2;
          dy1 = dy2;
          dx2 = hip * std::sin(static_cast<double>(sector - 1) * 60.0 * degrees);
          dy2 = hip * std::cos(static_cast<double>(sector - 1) * 60.0 * degrees);
        }

        append_mesenchymal_cell(
            state.nodes,
            draft_cells,
            Vec3{.x = origin.x + dx2, .y = origin.y + dy2, .z = origin.z},
            config.mradi,
            de,
            false,
            rng);

        if (radial_cell <= 2) {
          continue;
        }

        const double dx3 = (dx2 - dx1) / static_cast<double>(radial_cell - 1);
        const double dy3 = (dy2 - dy1) / static_cast<double>(radial_cell - 1);
        for (int intermediate = 1; intermediate <= (radial_cell - 2); ++intermediate) {
          append_mesenchymal_cell(
              state.nodes,
              draft_cells,
              Vec3{
                  .x = origin.x + dx1 + (static_cast<double>(intermediate) * dx3),
                  .y = origin.y + dy1 + (static_cast<double>(intermediate) * dy3),
                  .z = origin.z,
              },
              config.mradi,
              de,
              true,
              rng);
        }
      }
    }
  }

  state.cells.minsize_for_div.reserve(draft_cells.size());
  state.cells.maxsize_for_div.reserve(draft_cells.size());
  state.cells.cex.assign(draft_cells.size(), 0.0);
  state.cells.cey.assign(draft_cells.size(), 0.0);
  state.cells.cez.assign(draft_cells.size(), 0.0);
  state.cells.fase.assign(draft_cells.size(), 0.0);
  state.cells.nunodes.reserve(draft_cells.size());
  state.cells.ctipus.assign(draft_cells.size(), 3);
  state.cells.adhesion_type.assign(draft_cells.size(), 0);
  state.cells.node_offsets.reserve(draft_cells.size() + 1);
  state.cells.node_indices.reserve(static_cast<std::size_t>(config.node_count()));

  int offset = 0;
  state.cells.node_offsets.push_back(offset);
  for (const DraftCell& cell : draft_cells) {
    state.cells.minsize_for_div.push_back(static_cast<double>(cell.nodes.size() * 2));
    state.cells.maxsize_for_div.push_back(10000.0);
    state.cells.nunodes.push_back(static_cast<int>(cell.nodes.size()));
    state.cells.node_indices.insert(state.cells.node_indices.end(), cell.nodes.begin(), cell.nodes.end());
    offset += static_cast<int>(cell.nodes.size());
    state.cells.node_offsets.push_back(offset);
  }

  assign_cell_centroids_and_nuclei(state.nodes, state.cells);

  state.genes.gex.assign(
      state.nodes.size() * static_cast<std::size_t>(state.genes.gene_count), 0.0);
  for (std::size_t cell_index = 0; cell_index < state.cells.size(); ++cell_index) {
    const int gene_index = gfortran_random_r8(rng) > config.type1_threshold ? 0 : 1;
    state.cells.adhesion_type[cell_index] = gene_index + 1;
    for (const int node_index : state.cells.nodes_for_cell(cell_index)) {
      state.genes.set_expression(static_cast<std::size_t>(node_index), gene_index, 1.0);
    }
  }

  return state;
}

LegacyCellSortingState build_legacy_cell_sorting_state(const std::int32_t repeated_seed_word) {
  GFortranRngState rng = make_gfortran_rng_state(repeated_seed_word);
  return build_legacy_cell_sorting_state(rng);
}

void apply_legacy_cell_sorting_node_positions(
    LegacyCellSortingState& state,
    const std::span<const double> x,
    const std::span<const double> y,
    const std::span<const double> z) {
  if (x.size() != state.nodes.size() || y.size() != state.nodes.size() || z.size() != state.nodes.size()) {
    throw std::invalid_argument("legacy node-position bootstrap size drifted");
  }

  std::ranges::copy(x, state.nodes.x.begin());
  std::ranges::copy(y, state.nodes.y.begin());
  std::ranges::copy(z, state.nodes.z.begin());
  recompute_cell_centroids(state.nodes, state.cells);
}

void apply_legacy_cell_sorting_cell_types(
    LegacyCellSortingState& state,
    const std::span<const int> adhesion_types) {
  if (adhesion_types.size() != state.cells.size()) {
    throw std::invalid_argument("legacy cell-type bootstrap size drifted");
  }

  std::fill(state.genes.gex.begin(), state.genes.gex.end(), 0.0);
  for (std::size_t cell_index = 0; cell_index < state.cells.size(); ++cell_index) {
    const int adhesion_type = adhesion_types[cell_index];
    if (adhesion_type != 1 && adhesion_type != 2) {
      throw std::invalid_argument("legacy cell-type bootstrap requires adhesion types 1 or 2");
    }
    state.cells.adhesion_type[cell_index] = adhesion_type;
    const int gene_index = adhesion_type - 1;
    for (const int node_index : state.cells.nodes_for_cell(cell_index)) {
      state.genes.set_expression(static_cast<std::size_t>(node_index), gene_index, 1.0);
    }
  }
}

}  // namespace em2
