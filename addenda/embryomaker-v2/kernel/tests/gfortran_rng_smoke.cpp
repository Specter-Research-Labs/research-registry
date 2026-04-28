#include <array>
#include <cmath>
#include <cstdlib>
#include <iostream>

#include "em2/core/gfortran_rng.hpp"

namespace {

constexpr std::array<double, 5> kExpectedSamples = {
    0.53686441600804946,
    0.89205501123963993,
    0.044804048456224321,
    0.51446109399695250,
    0.34940900523890039,
};

constexpr std::array<std::int32_t, em2::kGFortranSeedWordCount> kExpectedState = {
    1159715046,
    1397023116,
    515274987,
    1784798529,
    1646420900,
    1708689512,
    -1064051338,
    -1619829934,
};

}  // namespace

int main() {
  const em2::GFortranRngState initial_state = em2::make_gfortran_rng_state(-11111);
  em2::GFortranRngState state = initial_state;

  for (std::size_t index = 0; index < kExpectedSamples.size(); ++index) {
    const double sample = em2::gfortran_random_r8(state);
    if (std::abs(sample - kExpectedSamples[index]) > 1e-15) {
      std::cerr << "gfortran random sample drifted at index " << index << '\n';
      return EXIT_FAILURE;
    }
  }

  if (em2::export_gfortran_seed_words(state) != kExpectedState) {
    std::cerr << "gfortran random state export drifted\n";
    return EXIT_FAILURE;
  }

  if (em2::export_gfortran_seed_words(em2::make_gfortran_rng_state(kExpectedState)) != kExpectedState) {
    std::cerr << "gfortran random state import drifted\n";
    return EXIT_FAILURE;
  }

  em2::GFortranRngState rewound_state = state;
  em2::rewind_gfortran_random_r8(rewound_state, kExpectedSamples.size());
  if (em2::export_gfortran_seed_words(rewound_state) !=
      em2::export_gfortran_seed_words(initial_state)) {
    std::cerr << "gfortran random rewind drifted\n";
    return EXIT_FAILURE;
  }

  for (std::size_t index = 0; index < kExpectedSamples.size(); ++index) {
    const double sample = em2::gfortran_random_r8(rewound_state);
    if (std::abs(sample - kExpectedSamples[index]) > 1e-15) {
      std::cerr << "gfortran random rewind replay drifted at index " << index << '\n';
      return EXIT_FAILURE;
    }
  }

  constexpr std::uint64_t kLongRunDraws = 1000000;
  em2::GFortranRngState long_run_state = initial_state;
  for (std::uint64_t draw = 0; draw < kLongRunDraws; ++draw) {
    static_cast<void>(em2::gfortran_random_r8(long_run_state));
  }
  em2::rewind_gfortran_random_r8(long_run_state, kLongRunDraws);
  if (em2::export_gfortran_seed_words(long_run_state) !=
      em2::export_gfortran_seed_words(initial_state)) {
    std::cerr << "gfortran long-run rewind drifted\n";
    return EXIT_FAILURE;
  }

  return EXIT_SUCCESS;
}
