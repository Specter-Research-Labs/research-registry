#include "em2/mechanics/mesenchymal_forces.hpp"

#include <cmath>
#include <limits>
#include <stdexcept>
#include <vector>

#include "em2/model/legacy_cell_sorting.hpp"

namespace em2 {
namespace {

double adhesive_strength(const LegacyCellSortingState& state, int left_node, int right_node) {
  double strength = 0.5 * (state.nodes.adh[left_node] + state.nodes.adh[right_node]);
  for (int left_gene = 0; left_gene < state.genes.gene_count; ++left_gene) {
    const double left_expression = state.genes.expression(static_cast<std::size_t>(left_node), left_gene);
    if (left_expression <= 0.0) {
      continue;
    }
    const int left_type = state.genes.adhesion_type_by_gene[static_cast<std::size_t>(left_gene)];
    if (left_type <= 0) {
      continue;
    }
    for (int right_gene = 0; right_gene < state.genes.gene_count; ++right_gene) {
      const double right_expression =
          state.genes.expression(static_cast<std::size_t>(right_node), right_gene);
      if (right_expression <= 0.0) {
        continue;
      }
      const int right_type = state.genes.adhesion_type_by_gene[static_cast<std::size_t>(right_gene)];
      if (right_type <= 0) {
        continue;
      }
      strength += left_expression * right_expression *
                  state.genes.adhesion_value(left_type, right_type);
    }
  }
  return strength;
}

double vector_norm(double x, double y, double z) {
  return std::sqrt((x * x) + (y * y) + (z * z));
}

}  // namespace

ForceState compute_mesenchymal_forces(
    const LegacyCellSortingState& state,
    const ContactGraph& contact_graph) {
  if (contact_graph.left.size() != contact_graph.right.size() ||
      contact_graph.left.size() != contact_graph.distance.size()) {
    throw std::invalid_argument("contact graph arrays must have the same size");
  }

  const double epsilon = std::numeric_limits<double>::epsilon() * 10.0;
  std::vector<double> adhesion_x(state.nodes.size(), 0.0);
  std::vector<double> adhesion_y(state.nodes.size(), 0.0);
  std::vector<double> adhesion_z(state.nodes.size(), 0.0);
  std::vector<double> repulsion_x(state.nodes.size(), 0.0);
  std::vector<double> repulsion_y(state.nodes.size(), 0.0);
  std::vector<double> repulsion_z(state.nodes.size(), 0.0);

  for (std::size_t pair_index = 0; pair_index < contact_graph.size(); ++pair_index) {
    const int left = contact_graph.left[pair_index];
    const int right = contact_graph.right[pair_index];
    const double dx = state.nodes.x[static_cast<std::size_t>(right)] -
                      state.nodes.x[static_cast<std::size_t>(left)];
    const double dy = state.nodes.y[static_cast<std::size_t>(right)] -
                      state.nodes.y[static_cast<std::size_t>(left)];
    const double dz = state.nodes.z[static_cast<std::size_t>(right)] -
                      state.nodes.z[static_cast<std::size_t>(left)];
    const double distance = contact_graph.distance[pair_index];
    if (distance <= epsilon) {
      continue;
    }

    const double unit_x = dx / distance;
    const double unit_y = dy / distance;
    const double unit_z = dz / distance;
    const double cutoff = state.nodes.add[static_cast<std::size_t>(left)] +
                          state.nodes.add[static_cast<std::size_t>(right)];
    if ((distance - cutoff) > epsilon) {
      continue;
    }
    const double deqe = state.nodes.eqd[static_cast<std::size_t>(left)] +
                        state.nodes.eqd[static_cast<std::size_t>(right)];
    const bool same_cell =
        state.nodes.icel[static_cast<std::size_t>(left)] ==
        state.nodes.icel[static_cast<std::size_t>(right)];

    double force_scalar = 0.0;
    if (same_cell) {
      if ((distance - deqe) < -epsilon) {
        force_scalar = (state.nodes.rep[static_cast<std::size_t>(left)] +
                        state.nodes.rep[static_cast<std::size_t>(right)]) *
                       (distance - deqe);
      } else {
        force_scalar = (state.nodes.you[static_cast<std::size_t>(left)] +
                        state.nodes.you[static_cast<std::size_t>(right)]) *
                       (distance - deqe);
      }
    } else if ((distance - deqe) < -epsilon) {
      force_scalar = (state.nodes.rec[static_cast<std::size_t>(left)] +
                      state.nodes.rec[static_cast<std::size_t>(right)]) *
                     (distance - deqe);
    } else {
      force_scalar = 2.0 * adhesive_strength(state, left, right) * (distance - deqe);
    }

    std::vector<double>* target_x = &repulsion_x;
    std::vector<double>* target_y = &repulsion_y;
    std::vector<double>* target_z = &repulsion_z;
    if (state.config.cap_adhesion && force_scalar > 0.0) {
      target_x = &adhesion_x;
      target_y = &adhesion_y;
      target_z = &adhesion_z;
    }

    (*target_x)[static_cast<std::size_t>(left)] += force_scalar * unit_x;
    (*target_y)[static_cast<std::size_t>(left)] += force_scalar * unit_y;
    (*target_z)[static_cast<std::size_t>(left)] += force_scalar * unit_z;
    (*target_x)[static_cast<std::size_t>(right)] -= force_scalar * unit_x;
    (*target_y)[static_cast<std::size_t>(right)] -= force_scalar * unit_y;
    (*target_z)[static_cast<std::size_t>(right)] -= force_scalar * unit_z;
  }

  ForceState forces{
      .fx = std::vector<double>(state.nodes.size(), 0.0),
      .fy = std::vector<double>(state.nodes.size(), 0.0),
      .fz = std::vector<double>(state.nodes.size(), 0.0),
      .adhesion_norm = std::vector<double>(state.nodes.size(), 0.0),
      .repulsion_norm = std::vector<double>(state.nodes.size(), 0.0),
      .interacting_pair_count = contact_graph.size(),
  };

  for (std::size_t node_index = 0; node_index < state.nodes.size(); ++node_index) {
    double capped_x = adhesion_x[node_index];
    double capped_y = adhesion_y[node_index];
    double capped_z = adhesion_z[node_index];
    const double adhesion_length = vector_norm(capped_x, capped_y, capped_z);
    if (state.config.cap_adhesion && adhesion_length > state.config.maxad) {
      const double scale = state.config.maxad / adhesion_length;
      capped_x *= scale;
      capped_y *= scale;
      capped_z *= scale;
    }
    forces.fx[node_index] = capped_x + repulsion_x[node_index];
    forces.fy[node_index] = capped_y + repulsion_y[node_index];
    forces.fz[node_index] = capped_z + repulsion_z[node_index];
    forces.adhesion_norm[node_index] = vector_norm(capped_x, capped_y, capped_z);
    forces.repulsion_norm[node_index] =
        vector_norm(repulsion_x[node_index], repulsion_y[node_index], repulsion_z[node_index]);
  }

  return forces;
}

}  // namespace em2
