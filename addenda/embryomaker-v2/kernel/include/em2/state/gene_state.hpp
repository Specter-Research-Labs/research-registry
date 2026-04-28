#pragma once

#include <cstddef>
#include <vector>

namespace em2 {

struct GeneState {
  int gene_count;
  int adhesion_type_count;
  std::vector<int> adhesion_type_by_gene;
  std::vector<double> kadh;
  std::vector<double> gex;

  [[nodiscard]] double expression(std::size_t node_index, int gene_index) const {
    return gex[node_index * static_cast<std::size_t>(gene_count) + static_cast<std::size_t>(gene_index)];
  }

  void set_expression(std::size_t node_index, int gene_index, double value) {
    gex[node_index * static_cast<std::size_t>(gene_count) + static_cast<std::size_t>(gene_index)] = value;
  }

  [[nodiscard]] double adhesion_value(int left_type, int right_type) const {
    const std::size_t width = static_cast<std::size_t>(adhesion_type_count);
    const std::size_t row = static_cast<std::size_t>(left_type - 1);
    const std::size_t col = static_cast<std::size_t>(right_type - 1);
    return kadh[row * width + col];
  }
};

}  // namespace em2
