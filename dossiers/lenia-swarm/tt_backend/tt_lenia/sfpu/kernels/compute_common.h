#pragma once
#include <cstdint>
#include "api/compute/common.h"
#include "api/compute/tile_move_copy.h"
#include "api/compute/eltwise_unary/eltwise_unary.h"
#include "api/compute/compute_kernel_api.h"
#include "tools/profiler/kernel_profiler.hpp"
#include "shape.h"

#ifdef TRISC_MATH
using namespace sfpi;

// SFPSWAP min/max is one instruction where a predicated v_if clamp costs several.
sfpi_inline vFloat clamp(vFloat x, float lo, float hi) {
    vFloat l = lo;
    vec_min_max(l, x);
    vFloat h = hi;
    vec_min_max(x, h);
    return x;
}

sfpi_inline vFloat max0(vFloat x) {
    vFloat l = 0.0f;
    vec_min_max(l, x);
    return x;
}

// exp(x) for x <= 0: Cody-Waite reduction by ln 2 and a degree 7 Taylor polynomial, then the
// exponent is spliced in as an integer. Below -86 the splice would need subnormals, which the
// SFPU flushes anyway, so the result is 0 there.
sfpi_inline vFloat exp_neg(vFloat x) {
    vFloat t = x * 1.44269504f + 12582912.0f;
    vFloat nf = t - 12582912.0f;
    vFloat r = (x - nf * 0.693359375f) - nf * -2.12194440e-4f;
    vFloat p = r * (1.0f / 5040.0f) + (1.0f / 720.0f);
    p = p * r + (1.0f / 120.0f);
    p = p * r + (1.0f / 24.0f);
    p = p * r + (1.0f / 6.0f);
    p = p * r + 0.5f;
    p = p * r + 1.0f;
    p = p * r + 1.0f;
    vInt n = reinterpret<vInt>(t) - 0x4B400000;
    vFloat out = reinterpret<vFloat>(reinterpret<vInt>(p) + (n << 23));
    v_if (x < -86.0f) { out = 0.0f; }
    v_endif;
    return out;
}

inline void sfpu_begin() {
    math::set_dst_write_addr<DstTileShape::Tile32x32, UnpackDestination::SrcRegs>(0);
    math::set_addr_mod_base();
    TTI_STALLWAIT(p_stall::STALL_SFPU, p_stall::MATH);
}

inline void sfpu_end() {
    math::clear_dst_reg_addr();
    TTI_STALLWAIT(p_stall::STALL_CFG, p_stall::WAIT_SFPU);
    math::clear_addr_mod_base();
}
#endif

#include GEN_HEADER

#define SFPU(call) MATH((sfpu_begin(), call, sfpu_end()))

constexpr uint32_t CB_IN = tt::CBIndex::c_0;
constexpr uint32_t CB_H = tt::CBIndex::c_1;
constexpr uint32_t CB_F = tt::CBIndex::c_2;
constexpr uint32_t CB_F2 = tt::CBIndex::c_3;
constexpr uint32_t CB_T = tt::CBIndex::c_4;
constexpr uint32_t CB_R = tt::CBIndex::c_5;
constexpr uint32_t CB_P = tt::CBIndex::c_6;
constexpr uint32_t CB_PAR = tt::CBIndex::c_7;
constexpr uint32_t CB_ACC = tt::CBIndex::c_8;
constexpr uint32_t CB_MASS = tt::CBIndex::c_9;
constexpr uint32_t CB_OUT = tt::CBIndex::c_16;
constexpr uint32_t CB_OUT2 = tt::CBIndex::c_17;
constexpr uint32_t CB_CAP = tt::CBIndex::c_18;

__attribute__((noinline)) void load_tiles(uint32_t cb, uint32_t first, uint32_t count, uint32_t slot) {
    copy_tile_to_dst_init_short(cb);
    for (uint32_t i = 0; i < count; i++) {
        copy_tile(cb, first + i, slot + i);
    }
}

__attribute__((noinline)) void pack_tiles(uint32_t slot, uint32_t count, uint32_t cb) {
    cb_reserve_back(cb, count);
    for (uint32_t i = 0; i < count; i++) {
        pack_tile(slot + i, cb);
    }
    cb_push_back(cb, count);
}

inline void regs_begin() { tile_regs_acquire(); }

inline void regs_handoff() {
    tile_regs_commit();
    tile_regs_wait();
}
