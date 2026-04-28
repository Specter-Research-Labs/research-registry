#pragma once

#include <cstddef>
#include <span>
#include <vector>

namespace em2 {

struct LegacyCellSortingState;

struct LegacyNeighborList {
  std::vector<int> counts;
  int max_count;
  std::vector<int> neighbors;
  std::vector<double> distances;

  [[nodiscard]] std::size_t size() const { return counts.size(); }

  [[nodiscard]] std::span<const int> neighbors_for_node(std::size_t node_index) const {
    const std::size_t begin = node_index * static_cast<std::size_t>(max_count);
    return std::span<const int>(
        neighbors.data() + begin,
        static_cast<std::size_t>(counts[node_index]));
  }

  [[nodiscard]] std::span<const double> distances_for_node(std::size_t node_index) const {
    const std::size_t begin = node_index * static_cast<std::size_t>(max_count);
    return std::span<const double>(
        distances.data() + begin,
        static_cast<std::size_t>(counts[node_index]));
  }
};

LegacyNeighborList build_legacy_neighbor_list(const LegacyCellSortingState& state);

void rebuild_legacy_neighbor_row(
    const LegacyCellSortingState& state,
    std::size_t node_index,
    LegacyNeighborList& neighbor_list);

}  // namespace em2
