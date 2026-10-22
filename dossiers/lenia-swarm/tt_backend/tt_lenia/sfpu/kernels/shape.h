#pragma once
#include <stdint.h>

constexpr uint32_t SX = GRID_SX;
constexpr uint32_t SY = GRID_SY;
constexpr uint32_t NC = CHANNELS;
constexpr uint32_t NK = KERNELS;
constexpr int32_t DD = REINT_DD;
constexpr uint32_t ROWS = REINT_ROWS;
constexpr uint32_t M = SY / 2;
constexpr uint32_t T = SY / 32;
constexpr uint32_t CT = SX / 16;
constexpr uint32_t HT = SX / 32;
// Pass 2 moves a column through DST in chunks of CW tiles from each column half.
constexpr uint32_t CW = SX == 128 ? 4 : 2;
// Tiles of a 128-point complex transform, which fits DST whole, and of one half of a split
// stage chunk.
constexpr uint32_t COL_TILES = 8;
constexpr uint32_t SPLIT_TILES = 2;
// codegen.twiddle_table: span s starts (TW_TOP - s) / 16 tiles in.
constexpr uint32_t TW_TOP = TWIDDLE_TOP;
constexpr uint32_t TW_TILES = TWIDDLE_TILES;
constexpr uint32_t twiddle_tile(uint32_t span) { return (TW_TOP - span) / 16; }
constexpr uint32_t c0[NK] = {C0_LIST};
