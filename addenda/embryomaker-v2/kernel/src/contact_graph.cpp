#include "em2/mechanics/contact_graph.hpp"

#include <cmath>
#include <limits>

#include "em2/mechanics/legacy_neighbor_list.hpp"

namespace em2 {

ContactGraph build_mesenchymal_contact_graph(const NodeState& nodes) {
  ContactGraph graph;
  const double epsilon = std::numeric_limits<double>::epsilon() * 10.0;

  for (std::size_t left = 0; left < nodes.size(); ++left) {
    for (std::size_t right = left + 1; right < nodes.size(); ++right) {
      const double dx = nodes.x[right] - nodes.x[left];
      const double dy = nodes.y[right] - nodes.y[left];
      const double dz = nodes.z[right] - nodes.z[left];
      const double distance = std::sqrt((dx * dx) + (dy * dy) + (dz * dz));
      const double cutoff = nodes.add[left] + nodes.add[right];
      if ((distance - cutoff) > epsilon) {
        continue;
      }
      graph.left.push_back(static_cast<int>(left));
      graph.right.push_back(static_cast<int>(right));
      graph.distance.push_back(distance);
    }
  }

  return graph;
}

ContactGraph build_mesenchymal_contact_graph(const LegacyNeighborList& neighbor_list) {
  ContactGraph graph;
  for (std::size_t left = 0; left < neighbor_list.size(); ++left) {
    const std::span<const int> neighbors = neighbor_list.neighbors_for_node(left);
    const std::span<const double> distances = neighbor_list.distances_for_node(left);
    for (std::size_t index = 0; index < neighbors.size(); ++index) {
      const int right = neighbors[index];
      if (right < 0 || right <= static_cast<int>(left)) {
        continue;
      }
      graph.left.push_back(static_cast<int>(left));
      graph.right.push_back(right);
      graph.distance.push_back(distances[index]);
    }
  }

  return graph;
}

void refresh_contact_graph_distances(const NodeState& nodes, ContactGraph& graph) {
  for (std::size_t pair_index = 0; pair_index < graph.size(); ++pair_index) {
    const std::size_t left = static_cast<std::size_t>(graph.left[pair_index]);
    const std::size_t right = static_cast<std::size_t>(graph.right[pair_index]);
    const double dx = nodes.x[right] - nodes.x[left];
    const double dy = nodes.y[right] - nodes.y[left];
    const double dz = nodes.z[right] - nodes.z[left];
    graph.distance[pair_index] = std::sqrt((dx * dx) + (dy * dy) + (dz * dz));
  }
}

}  // namespace em2
