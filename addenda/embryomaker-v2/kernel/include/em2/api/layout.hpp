#pragma once

#include <string>
#include <vector>

namespace em2 {

struct ModuleSurface {
  std::string name;
  std::string responsibility;
};

struct LayoutReport {
  std::vector<ModuleSurface> modules;
  std::vector<std::string> hot_state_arrays;
  std::vector<std::string> parity_lanes;
};

LayoutReport describe_layout();

}  // namespace em2
