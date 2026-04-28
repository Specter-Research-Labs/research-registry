#pragma once

#include <array>
#include <cstdint>

namespace em2 {

constexpr std::size_t kGFortranSeedWordCount = 8;

struct GFortranRngState {
  std::array<std::uint64_t, 4> s;
};

GFortranRngState make_gfortran_rng_state(
    std::array<std::int32_t, kGFortranSeedWordCount> seed_words);
GFortranRngState make_gfortran_rng_state(std::int32_t repeated_seed_word);

double gfortran_random_r8(GFortranRngState& state);

void rewind_gfortran_random_r8(GFortranRngState& state, std::uint64_t draws);

std::array<std::int32_t, kGFortranSeedWordCount> export_gfortran_seed_words(
    const GFortranRngState& state);

}  // namespace em2
