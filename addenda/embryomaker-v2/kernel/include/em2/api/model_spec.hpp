#pragma once

#include <string>

namespace em2 {

struct ModelSpec {
  std::string name;
  int cell_type_count;
  int field_count;
};

}  // namespace em2
