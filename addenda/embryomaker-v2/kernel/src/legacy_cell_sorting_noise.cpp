#include "em2/mechanics/legacy_cell_sorting_noise.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <limits>
#include <stdexcept>

#include "em2/core/gfortran_rng.hpp"
#include "em2/model/legacy_cell_sorting.hpp"

namespace em2 {
namespace {

constexpr double kLegacyPi = 3.141592;
constexpr double kLegacyNue = 2.71828;

std::size_t random_index(GFortranRngState& rng, std::size_t upper) {
  if (upper == 0) {
    throw std::invalid_argument("random_index requires a non-empty range");
  }
  const double sample = gfortran_random_r8(rng);
  const std::size_t index = static_cast<std::size_t>(sample * static_cast<double>(upper));
  return std::min(index, upper - 1);
}

double adhesive_strength(const LegacyCellSortingState& state, std::size_t left, std::size_t right) {
  double strength = 0.5 * (state.nodes.adh[left] + state.nodes.adh[right]);
  for (int left_gene = 0; left_gene < state.genes.gene_count; ++left_gene) {
    const double left_expression = state.genes.expression(left, left_gene);
    if (left_expression <= 0.0) {
      continue;
    }
    const int left_type = state.genes.adhesion_type_by_gene[static_cast<std::size_t>(left_gene)];
    if (left_type <= 0) {
      continue;
    }
    for (int right_gene = 0; right_gene < state.genes.gene_count; ++right_gene) {
      const double right_expression = state.genes.expression(right, right_gene);
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

void update_mesenchymal_centroid(
    LegacyCellSortingState& state,
    std::size_t node_index,
    double old_x,
    double old_y,
    double old_z) {
  const std::size_t cell_index = static_cast<std::size_t>(state.nodes.icel[node_index]);
  const double inv_count = 1.0 / static_cast<double>(state.cells.nunodes[cell_index]);
  state.cells.cex[cell_index] += (state.nodes.x[node_index] - old_x) * inv_count;
  state.cells.cey[cell_index] += (state.nodes.y[node_index] - old_y) * inv_count;
  state.cells.cez[cell_index] += (state.nodes.z[node_index] - old_z) * inv_count;
}

}  // namespace

LegacyNoiseRuntime make_legacy_noise_runtime(int partitions, GFortranRngState rng) {
  if (partitions <= 0) {
    throw std::invalid_argument("legacy noise partitions must be positive");
  }

  LegacyNoiseRuntime runtime{
      .rng = rng,
      .sphere =
          LegacyNoiseSphere{
              .partitions = partitions,
              .x = {},
              .y = {},
              .z = {},
          },
  };

  const std::size_t point_count =
      static_cast<std::size_t>(partitions) * static_cast<std::size_t>(partitions);
  runtime.sphere.x.resize(point_count);
  runtime.sphere.y.resize(point_count);
  runtime.sphere.z.resize(point_count);

  const std::size_t half = point_count / 2;
  for (std::size_t index = 0; index < half; ++index) {
    const double azimuth = 2.0 * kLegacyPi * gfortran_random_r8(runtime.rng);
    const double vertical = (2.0 * gfortran_random_r8(runtime.rng)) - 1.0;
    const double radial = std::sqrt(std::max(0.0, 1.0 - (vertical * vertical)));
    const double x = radial * std::cos(azimuth);
    const double y = radial * std::sin(azimuth);

    runtime.sphere.x[index] = x;
    runtime.sphere.y[index] = y;
    runtime.sphere.z[index] = vertical;
    runtime.sphere.x[index + half] = -x;
    runtime.sphere.y[index + half] = -y;
    runtime.sphere.z[index + half] = -vertical;
  }

  if ((point_count % 2) == 1) {
    const std::size_t index = point_count - 1;
    runtime.sphere.x[index] = 0.0;
    runtime.sphere.y[index] = 0.0;
    runtime.sphere.z[index] = 1.0;
  }

  return runtime;
}

LegacyNoiseRuntime make_legacy_noise_runtime(
    const int partitions,
    const std::int32_t repeated_seed_word) {
  return make_legacy_noise_runtime(partitions, make_gfortran_rng_state(repeated_seed_word));
}

double compute_legacy_cell_sorting_local_energy(
    const LegacyCellSortingState& state,
    const LegacyNeighborList& neighbor_list,
    std::size_t node_index) {
  const double epsilon = std::numeric_limits<double>::epsilon() * 10.0;
  double energy = 0.0;

  const double ix = state.nodes.x[node_index];
  const double iy = state.nodes.y[node_index];
  const double iz = state.nodes.z[node_index];
  const double reqnod = state.nodes.eqd[node_index];
  const double younod = state.nodes.you[node_index];
  const double repnod = state.nodes.rep[node_index];
  const double repcelnod = state.nodes.rec[node_index];
  const double nodda = state.nodes.add[node_index];
  const int left_cell = state.nodes.icel[node_index];

  if (state.nodes.fix[node_index] == 2) {
    return std::numeric_limits<double>::max();
  }

  for (const int other_index : neighbor_list.neighbors_for_node(node_index)) {
    const std::size_t other = static_cast<std::size_t>(other_index);
    const double dx = state.nodes.x[other] - ix;
    const double dy = state.nodes.y[other] - iy;
    const double dz = state.nodes.z[other] - iz;
    const double distance = std::sqrt((dx * dx) + (dy * dy) + (dz * dz));
    const double cutoff = nodda + state.nodes.add[other];
    if ((distance - cutoff) > epsilon) {
      continue;
    }

    const double deqe = reqnod + state.nodes.eqd[other];
    const double scaled_delta = (distance - deqe) / deqe;
    const double ideqe = ((cutoff - deqe) / deqe) * ((cutoff - deqe) / deqe);

    if (left_cell == state.nodes.icel[other]) {
      const double youe = 0.5 * (younod + state.nodes.you[other]);
      const double repe = 0.5 * (repnod + state.nodes.rep[other]);
      if ((distance - deqe) < -epsilon) {
        energy += repe * (scaled_delta * scaled_delta) - (youe * ideqe);
      } else {
        energy += youe * (scaled_delta * scaled_delta) - (youe * ideqe);
      }
      continue;
    }

    const double adhe = adhesive_strength(state, node_index, other);
    const double repcele = 0.5 * (repcelnod + state.nodes.rec[other]);
    if ((distance - deqe) < -epsilon) {
      energy += repcele * (scaled_delta * scaled_delta) - (adhe * ideqe);
    } else {
      energy += adhe * (scaled_delta * scaled_delta) - (adhe * ideqe);
    }
  }

  return energy;
}

double compute_legacy_cell_sorting_local_energy(
    const LegacyCellSortingState& state,
    std::size_t node_index) {
  return compute_legacy_cell_sorting_local_energy(
      state,
      build_legacy_neighbor_list(state),
      node_index);
}

LegacyNoiseStep apply_legacy_cell_sorting_noise(
    LegacyCellSortingState& state,
    LegacyNoiseRuntime& runtime,
    LegacyNeighborList& neighbor_list,
    double delta) {
  const double epsilon = std::numeric_limits<double>::epsilon() * 10.0;
  LegacyNoiseStep step{
      .node_index = -1,
      .cell_index = -1,
      .displacement = 0.0,
      .old_energy = 0.0,
      .new_energy = 0.0,
      .accepted = false,
  };

  int attempts = 0;
  while (attempts <= static_cast<int>(state.nodes.size() * 2)) {
    const std::size_t node_index = random_index(runtime.rng, state.nodes.size());
    attempts += 1;
    if (state.nodes.fix[node_index] == 2) {
      continue;
    }

    step.node_index = static_cast<int>(node_index);
    step.cell_index = state.nodes.icel[node_index];
    if (state.config.energy_biased_noise) {
      step.old_energy = compute_legacy_cell_sorting_local_energy(state, neighbor_list, node_index);
      state.nodes.e[node_index] = step.old_energy;
    }

    const double old_x = state.nodes.x[node_index];
    const double old_y = state.nodes.y[node_index];
    const double old_z = state.nodes.z[node_index];
    const double old_cex = state.cells.cex[static_cast<std::size_t>(step.cell_index)];
    const double old_cey = state.cells.cey[static_cast<std::size_t>(step.cell_index)];
    const double old_cez = state.cells.cez[static_cast<std::size_t>(step.cell_index)];

    step.displacement = gfortran_random_r8(runtime.rng) * state.nodes.dmo[node_index] * delta;
    if (step.displacement < epsilon) {
      step.new_energy = step.old_energy;
      return step;
    }

    const std::size_t direction_index = random_index(runtime.rng, runtime.sphere.size());
    state.nodes.x[node_index] += runtime.sphere.x[direction_index] * step.displacement;
    state.nodes.y[node_index] += runtime.sphere.y[direction_index] * step.displacement;
    state.nodes.z[node_index] += runtime.sphere.z[direction_index] * step.displacement;
    update_mesenchymal_centroid(state, node_index, old_x, old_y, old_z);

    if (!state.config.energy_biased_noise) {
      step.accepted = true;
      return step;
    }

    rebuild_legacy_neighbor_row(state, node_index, neighbor_list);
    step.new_energy = compute_legacy_cell_sorting_local_energy(state, neighbor_list, node_index);
    state.nodes.e[node_index] = step.new_energy;
    const double energy_delta = step.new_energy - step.old_energy;
    if (energy_delta < -epsilon) {
      step.accepted = true;
      return step;
    }

    double kl = state.config.temp + state.nodes.mov[node_index];
    if (kl < epsilon) {
      kl = epsilon;
    }
    const double accept_threshold = std::pow(kLegacyNue, -energy_delta / kl);
    if (gfortran_random_r8(runtime.rng) < accept_threshold) {
      step.accepted = true;
      return step;
    }

    state.nodes.x[node_index] = old_x;
    state.nodes.y[node_index] = old_y;
    state.nodes.z[node_index] = old_z;
    state.nodes.e[node_index] = step.old_energy;
    state.cells.cex[static_cast<std::size_t>(step.cell_index)] = old_cex;
    state.cells.cey[static_cast<std::size_t>(step.cell_index)] = old_cey;
    state.cells.cez[static_cast<std::size_t>(step.cell_index)] = old_cez;
    rebuild_legacy_neighbor_row(state, node_index, neighbor_list);
    step.new_energy = step.old_energy;
    return step;
  }

  return step;
}

LegacyNoiseStep apply_legacy_cell_sorting_noise(
    LegacyCellSortingState& state,
    LegacyNoiseRuntime& runtime,
    double delta) {
  LegacyNeighborList neighbor_list = build_legacy_neighbor_list(state);
  return apply_legacy_cell_sorting_noise(state, runtime, neighbor_list, delta);
}

LegacyNoiseBatchResult apply_legacy_cell_sorting_noise_batch(
    LegacyCellSortingState& state,
    LegacyNoiseRuntime& runtime,
    LegacyNeighborList& neighbor_list,
    double delta) {
  LegacyNoiseBatchResult result{
      .attempts = 0,
      .accepted = 0,
      .rejected = 0,
      .zero_displacement = 0,
  };

  const double c = static_cast<double>(state.nodes.size()) * state.config.prop_noise * delta /
                   state.config.deltamin;
  int iterations = 0;
  if (c > 1.0) {
    iterations = static_cast<int>(c);
  } else if (gfortran_random_r8(runtime.rng) < c) {
    iterations = 1;
  }

  const double epsilon = std::numeric_limits<double>::epsilon() * 10.0;
  for (int iteration = 0; iteration < iterations; ++iteration) {
    const LegacyNoiseStep step = apply_legacy_cell_sorting_noise(state, runtime, neighbor_list, delta);
    result.attempts += 1;
    if (step.displacement < epsilon) {
      result.zero_displacement += 1;
      continue;
    }
    if (step.accepted) {
      result.accepted += 1;
    } else {
      result.rejected += 1;
    }
  }

  return result;
}

LegacyNoiseBatchResult apply_legacy_cell_sorting_noise_batch(
    LegacyCellSortingState& state,
    LegacyNoiseRuntime& runtime,
    double delta) {
  LegacyNeighborList neighbor_list = build_legacy_neighbor_list(state);
  return apply_legacy_cell_sorting_noise_batch(state, runtime, neighbor_list, delta);
}

}  // namespace em2
