#include "em2/api/layout.hpp"

namespace em2 {

LayoutReport describe_layout() {
  return LayoutReport{
      .modules =
          {
              {"core", "ids, numerics, rng, and error handling"},
              {"model", "static model definition"},
              {"state", "dynamic SoA simulation state"},
              {"mechanics", "neighbors, contacts, forces, and integration"},
              {"fields", "field storage and updates"},
              {"regulation", "per-cell species and behavior modifiers"},
              {"events", "division, death, and state transitions"},
              {"scheduler", "multi-rate stepping order"},
              {"io", "checkpoints and summaries"},
              {"api", "narrow public kernel surface"},
          },
      .hot_state_arrays =
          {
              "x",
              "y",
              "z",
              "radius",
              "polarity",
              "cell_type",
              "lineage_id",
              "cycle_phase",
              "differentiation_state",
              "alive",
          },
      .parity_lanes =
          {
              "mathematical transcription",
              "state-space parity",
              "execution parity",
              "baseline execution",
              "v2 comparison",
          },
  };
}

}  // namespace em2
