#include "em2/mechanics/legacy_neighbor_list.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <unordered_map>
#include <utility>
#include <vector>

#include "em2/model/legacy_cell_sorting.hpp"

namespace em2 {
namespace {

struct BoxKey {
  int x;
  int y;
  int z;

  bool operator==(const BoxKey& other) const = default;
};

struct BoxKeyHash {
  std::size_t operator()(const BoxKey& key) const {
    const std::uint64_t x = static_cast<std::uint64_t>(static_cast<std::int64_t>(key.x) + 4096);
    const std::uint64_t y = static_cast<std::uint64_t>(static_cast<std::int64_t>(key.y) + 4096);
    const std::uint64_t z = static_cast<std::uint64_t>(static_cast<std::int64_t>(key.z) + 4096);
    return static_cast<std::size_t>((x << 24) ^ (y << 12) ^ z);
  }
};

int legacy_nint(double value) {
  return static_cast<int>(std::lround(value));
}

double distance_from_origin(double x, double y, double z) {
  return std::sqrt((x * x) + (y * y) + (z * z));
}

void resize_neighbor_storage(LegacyNeighborList& neighbor_list, int new_max_count) {
  if (new_max_count <= neighbor_list.max_count) {
    return;
  }

  std::vector<int> neighbors(
      neighbor_list.size() * static_cast<std::size_t>(new_max_count),
      -1);
  std::vector<double> distances(
      neighbor_list.size() * static_cast<std::size_t>(new_max_count),
      0.0);
  for (std::size_t node_index = 0; node_index < neighbor_list.size(); ++node_index) {
    const std::size_t old_base = node_index * static_cast<std::size_t>(neighbor_list.max_count);
    const std::size_t new_base = node_index * static_cast<std::size_t>(new_max_count);
    for (int local_index = 0; local_index < neighbor_list.counts[node_index]; ++local_index) {
      neighbors[new_base + static_cast<std::size_t>(local_index)] =
          neighbor_list.neighbors[old_base + static_cast<std::size_t>(local_index)];
      distances[new_base + static_cast<std::size_t>(local_index)] =
          neighbor_list.distances[old_base + static_cast<std::size_t>(local_index)];
    }
  }

  neighbor_list.max_count = new_max_count;
  neighbor_list.neighbors = std::move(neighbors);
  neighbor_list.distances = std::move(distances);
}

}  // namespace

LegacyNeighborList build_legacy_neighbor_list(const LegacyCellSortingState& state) {
  double extre = 0.0;
  double max_add = 0.0;
  double max_dmo = 0.0;
  for (std::size_t node_index = 0; node_index < state.nodes.size(); ++node_index) {
    extre = std::max(
        extre,
        distance_from_origin(
            state.nodes.x[node_index],
            state.nodes.y[node_index],
            state.nodes.z[node_index]));
    max_add = std::max(max_add, state.nodes.add[node_index]);
    max_dmo = std::max(max_dmo, state.nodes.dmo[node_index]);
  }

  const double rv = 2.0 * max_add;
  const double urv = 1.0 / (rv + 1e-3);
  const int nboxes = legacy_nint(extre * urv) +
                     static_cast<int>(max_dmo + state.config.dmax) + 2;
  (void)nboxes;

  std::unordered_map<BoxKey, int, BoxKeyHash> heads;
  heads.reserve(state.nodes.size());
  std::vector<int> next(state.nodes.size(), -1);
  for (std::size_t node_index = 0; node_index < state.nodes.size(); ++node_index) {
    const BoxKey key{
        .x = legacy_nint(state.nodes.x[node_index] * urv),
        .y = legacy_nint(state.nodes.y[node_index] * urv),
        .z = legacy_nint(state.nodes.z[node_index] * urv),
    };
    const auto it = heads.find(key);
    next[node_index] = it == heads.end() ? -1 : it->second;
    heads[key] = static_cast<int>(node_index);
  }

  std::vector<std::vector<int>> per_node_neighbors(state.nodes.size());
  std::vector<std::vector<double>> per_node_distances(state.nodes.size());
  int max_count = 0;

  for (std::size_t node_index = 0; node_index < state.nodes.size(); ++node_index) {
    const double ix = state.nodes.x[node_index];
    const double iy = state.nodes.y[node_index];
    const double iz = state.nodes.z[node_index];
    const int box_z = legacy_nint(iz * urv);
    const int box_y = legacy_nint(iy * urv);
    const int box_x = legacy_nint(ix * urv);
    const double dai = state.nodes.add[node_index];

    for (int z_offset = -1; z_offset <= 1; ++z_offset) {
      for (int y_offset = -1; y_offset <= 1; ++y_offset) {
        for (int x_offset = -1; x_offset <= 1; ++x_offset) {
          const BoxKey key{
              .x = box_x + x_offset,
              .y = box_y + y_offset,
              .z = box_z + z_offset,
          };
          auto head = heads.find(key);
          int neighbor_index = head == heads.end() ? -1 : head->second;
          while (neighbor_index != -1) {
            const double dx = state.nodes.x[static_cast<std::size_t>(neighbor_index)] - ix;
            const double dy = state.nodes.y[static_cast<std::size_t>(neighbor_index)] - iy;
            const double dz = state.nodes.z[static_cast<std::size_t>(neighbor_index)] - iz;
            const double dist_sq = (dx * dx) + (dy * dy) + (dz * dz);
            const double cutoff = dai + state.nodes.add[static_cast<std::size_t>(neighbor_index)];
            if (neighbor_index != static_cast<int>(node_index) && dist_sq <= (cutoff * cutoff)) {
              per_node_neighbors[node_index].push_back(neighbor_index);
              per_node_distances[node_index].push_back(std::sqrt(dist_sq));
            }
            neighbor_index = next[static_cast<std::size_t>(neighbor_index)];
          }
        }
      }
    }

    max_count = std::max(max_count, static_cast<int>(per_node_neighbors[node_index].size()));
  }

  LegacyNeighborList neighbor_list{
      .counts = std::vector<int>(state.nodes.size(), 0),
      .max_count = max_count,
      .neighbors = std::vector<int>(state.nodes.size() * static_cast<std::size_t>(max_count), -1),
      .distances = std::vector<double>(state.nodes.size() * static_cast<std::size_t>(max_count), 0.0),
  };

  for (std::size_t node_index = 0; node_index < state.nodes.size(); ++node_index) {
    neighbor_list.counts[node_index] = static_cast<int>(per_node_neighbors[node_index].size());
    const std::size_t base = node_index * static_cast<std::size_t>(max_count);
    for (std::size_t local_index = 0; local_index < per_node_neighbors[node_index].size(); ++local_index) {
      neighbor_list.neighbors[base + local_index] = per_node_neighbors[node_index][local_index];
      neighbor_list.distances[base + local_index] = per_node_distances[node_index][local_index];
    }
  }

  return neighbor_list;
}

void rebuild_legacy_neighbor_row(
    const LegacyCellSortingState& state,
    std::size_t node_index,
    LegacyNeighborList& neighbor_list) {
  if (neighbor_list.size() != state.nodes.size()) {
    throw std::invalid_argument("neighbor list size must match node count");
  }

  std::vector<int> row_neighbors;
  std::vector<double> row_distances;
  row_neighbors.reserve(state.nodes.size());
  row_distances.reserve(state.nodes.size());

  const double ix = state.nodes.x[node_index];
  const double iy = state.nodes.y[node_index];
  const double iz = state.nodes.z[node_index];
  const double dai = state.nodes.add[node_index];

  for (std::size_t other = 0; other < state.nodes.size(); ++other) {
    if (other == node_index) {
      continue;
    }

    const double dx = state.nodes.x[other] - ix;
    const double dy = state.nodes.y[other] - iy;
    const double dz = state.nodes.z[other] - iz;
    const double dist_sq = (dx * dx) + (dy * dy) + (dz * dz);
    const double cutoff = dai + state.nodes.add[other];
    if (dist_sq > (cutoff * cutoff)) {
      continue;
    }

    row_neighbors.push_back(static_cast<int>(other));
    row_distances.push_back(std::sqrt(dist_sq));
  }

  const int row_count = static_cast<int>(row_neighbors.size());
  resize_neighbor_storage(neighbor_list, std::max(neighbor_list.max_count, row_count));
  neighbor_list.counts[node_index] = row_count;

  const std::size_t base = node_index * static_cast<std::size_t>(neighbor_list.max_count);
  for (int local_index = 0; local_index < neighbor_list.max_count; ++local_index) {
    neighbor_list.neighbors[base + static_cast<std::size_t>(local_index)] = -1;
    neighbor_list.distances[base + static_cast<std::size_t>(local_index)] = 0.0;
  }
  for (int local_index = 0; local_index < row_count; ++local_index) {
    neighbor_list.neighbors[base + static_cast<std::size_t>(local_index)] =
        row_neighbors[static_cast<std::size_t>(local_index)];
    neighbor_list.distances[base + static_cast<std::size_t>(local_index)] =
        row_distances[static_cast<std::size_t>(local_index)];
  }
}

}  // namespace em2
