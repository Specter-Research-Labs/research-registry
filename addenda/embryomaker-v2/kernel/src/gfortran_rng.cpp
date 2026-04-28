#include "em2/core/gfortran_rng.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <limits>

namespace em2 {
namespace {

constexpr std::array<std::uint64_t, 4> kXorKeys = {
    0xbd0c5b6e50c2df49ULL,
    0xd46061cd46e1df38ULL,
    0xbb4f4d4ed6103544ULL,
    0x114a583d0756ad39ULL,
};

std::uint64_t rotl(const std::uint64_t value, const int shift) {
  return std::rotl(value, shift);
}

std::uint64_t rotr(const std::uint64_t value, const int shift) {
  return std::rotr(value, shift);
}

std::uint64_t invert_xor_shift_left(std::uint64_t value, const int shift) {
  for (int step = shift; step < 64; step *= 2) {
    value ^= value << step;
  }
  return value;
}

std::array<std::uint64_t, 4> seed_words_to_state(
    const std::array<std::int32_t, kGFortranSeedWordCount>& seed_words) {
  std::array<std::int32_t, kGFortranSeedWordCount> reversed = seed_words;
  std::reverse(reversed.begin(), reversed.end());

  std::array<std::uint64_t, 4> state{};
  for (std::size_t word_index = 0; word_index < state.size(); ++word_index) {
    const std::size_t lower_index = word_index * 2;
    const std::uint64_t lower =
        static_cast<std::uint32_t>(reversed[lower_index]);
    const std::uint64_t upper =
        static_cast<std::uint32_t>(reversed[lower_index + 1]);
    state[word_index] = (lower | (upper << 32)) ^ kXorKeys[word_index];
  }
  return state;
}

std::uint64_t gfortran_prng_next(GFortranRngState& state) {
  const std::uint64_t result = rotl(state.s[1] * 5ULL, 7) * 9ULL;
  const std::uint64_t t = state.s[1] << 17;

  state.s[2] ^= state.s[0];
  state.s[3] ^= state.s[1];
  state.s[1] ^= state.s[2];
  state.s[0] ^= state.s[3];
  state.s[2] ^= t;
  state.s[3] = rotl(state.s[3], 45);

  return result;
}

void gfortran_prng_prev(GFortranRngState& state) {
  const std::uint64_t mix_31 = rotr(state.s[3], 45);
  const std::uint64_t restored_s0 = state.s[0] ^ mix_31;
  const std::uint64_t restored_s1 =
      invert_xor_shift_left(state.s[1] ^ state.s[2], 17);
  const std::uint64_t restored_s2 = state.s[1] ^ restored_s1 ^ restored_s0;
  const std::uint64_t restored_s3 = mix_31 ^ restored_s1;
  state.s = {restored_s0, restored_s1, restored_s2, restored_s3};
}

}  // namespace

GFortranRngState make_gfortran_rng_state(
    const std::array<std::int32_t, kGFortranSeedWordCount> seed_words) {
  return GFortranRngState{
      .s = seed_words_to_state(seed_words),
  };
}

GFortranRngState make_gfortran_rng_state(const std::int32_t repeated_seed_word) {
  return make_gfortran_rng_state({
      repeated_seed_word,
      repeated_seed_word,
      repeated_seed_word,
      repeated_seed_word,
      repeated_seed_word,
      repeated_seed_word,
      repeated_seed_word,
      repeated_seed_word,
  });
}

double gfortran_random_r8(GFortranRngState& state) {
  constexpr int digits = std::numeric_limits<double>::digits;
  const std::uint64_t raw = gfortran_prng_next(state);
  const std::uint64_t mask = (~std::uint64_t{0}) << (64 - digits);
  const std::uint64_t value = raw & mask;
  return static_cast<double>(value) * 0x1.0p-64;
}

void rewind_gfortran_random_r8(GFortranRngState& state, const std::uint64_t draws) {
  for (std::uint64_t draw = 0; draw < draws; ++draw) {
    gfortran_prng_prev(state);
  }
}

std::array<std::int32_t, kGFortranSeedWordCount> export_gfortran_seed_words(
    const GFortranRngState& state) {
  std::array<std::uint64_t, 4> unscrambled{};
  for (std::size_t word_index = 0; word_index < unscrambled.size(); ++word_index) {
    unscrambled[word_index] = state.s[word_index] ^ kXorKeys[word_index];
  }

  std::array<std::int32_t, kGFortranSeedWordCount> seed_words{};
  for (std::size_t word_index = 0; word_index < unscrambled.size(); ++word_index) {
    const std::size_t reversed_index = kGFortranSeedWordCount - 1 - (word_index * 2);
    seed_words[reversed_index] =
        static_cast<std::int32_t>(unscrambled[word_index] & 0xffffffffULL);
    seed_words[reversed_index - 1] =
        static_cast<std::int32_t>(unscrambled[word_index] >> 32);
  }

  return seed_words;
}

}  // namespace em2
