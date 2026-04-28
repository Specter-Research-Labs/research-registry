#pragma once

namespace em2 {

struct RunConfig {
  double dt_mech;
  double dt_field;
  double dt_reg;
  int checkpoint_interval;
};

}  // namespace em2
