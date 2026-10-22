#pragma once
#include <stdint.h>

constexpr uint32_t SX = GRID_SX;
constexpr uint32_t SY = GRID_SY;
constexpr uint32_t NC = CHANNELS;
constexpr uint32_t NK = KERNELS;
constexpr int32_t DD = REINT_DD;
constexpr uint32_t M = SY / 2;
constexpr uint32_t T = SY / 32;
constexpr uint32_t CT = SX / 16;
constexpr uint32_t HT = SX / 32;
// Pass 2 moves a column through DST in chunks of CW tiles from each column half.
constexpr uint32_t CW = SX == 128 ? 4 : 2;
constexpr uint32_t c0[NK] = {C0_LIST};
