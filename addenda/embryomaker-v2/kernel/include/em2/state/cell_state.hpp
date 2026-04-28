#pragma once

#include <cstddef>
#include <span>
#include <vector>

namespace em2 {

struct CellState {
  std::vector<double> minsize_for_div;
  std::vector<double> maxsize_for_div;
  std::vector<double> cex;
  std::vector<double> cey;
  std::vector<double> cez;
  std::vector<double> fase;
  std::vector<int> nunodes;
  std::vector<int> ctipus;
  std::vector<int> adhesion_type;
  std::vector<int> node_offsets;
  std::vector<int> node_indices;

  [[nodiscard]] std::size_t size() const { return nunodes.size(); }

  [[nodiscard]] std::span<const int> nodes_for_cell(std::size_t cell_index) const {
    const std::size_t begin = static_cast<std::size_t>(node_offsets[cell_index]);
    const std::size_t end = static_cast<std::size_t>(node_offsets[cell_index + 1]);
    return std::span<const int>(node_indices.data() + begin, end - begin);
  }
};

}  // namespace em2
