#pragma once

#include <string>

#include "em2/api/model_spec.hpp"
#include "em2/api/run_config.hpp"

namespace em2 {

class Runner {
 public:
  Runner(ModelSpec model, RunConfig run_config);

  [[nodiscard]] std::string summary() const;

 private:
  ModelSpec model_;
  RunConfig run_config_;
};

}  // namespace em2
