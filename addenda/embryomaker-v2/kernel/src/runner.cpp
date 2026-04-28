#include "em2/api/runner.hpp"

#include <sstream>

namespace em2 {

Runner::Runner(ModelSpec model, RunConfig run_config)
    : model_(std::move(model)), run_config_(run_config) {}

std::string Runner::summary() const {
  std::ostringstream out;
  out << "model=" << model_.name << " cell_types=" << model_.cell_type_count
      << " fields=" << model_.field_count << " dt_mech=" << run_config_.dt_mech
      << " dt_field=" << run_config_.dt_field << " dt_reg=" << run_config_.dt_reg;
  return out.str();
}

}  // namespace em2
