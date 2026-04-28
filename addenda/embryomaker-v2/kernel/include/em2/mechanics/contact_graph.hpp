#pragma once

#include <cstddef>
#include <vector>

#include "em2/state/node_state.hpp"

namespace em2 {

struct LegacyNeighborList;

struct ContactGraph {
  std::vector<int> left;
  std::vector<int> right;
  std::vector<double> distance;

  [[nodiscard]] std::size_t size() const { return left.size(); }
};

ContactGraph build_mesenchymal_contact_graph(const NodeState& nodes);
ContactGraph build_mesenchymal_contact_graph(const LegacyNeighborList& neighbor_list);
void refresh_contact_graph_distances(const NodeState& nodes, ContactGraph& graph);

}  // namespace em2
