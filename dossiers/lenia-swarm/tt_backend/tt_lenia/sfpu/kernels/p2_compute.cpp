#include "compute_common.h"

constexpr uint32_t CB_U = tt::CBIndex::c_10;
constexpr uint32_t CB_W = tt::CBIndex::c_11;
constexpr uint32_t HALF = CT / 2;
constexpr uint32_t BLOCKS = SX / 64;
constexpr uint32_t CHUNKS = HALF / CW;

enum class Prep { none, zero_imag, imag_to_real };

#ifdef TRISC_MATH
template <Prep P>
inline void prep() {
    if constexpr (P == Prep::zero_imag) {
        p2_zero_imag();
    } else if constexpr (P == Prep::imag_to_real) {
        p2_imag_to_real();
    }
}
#endif

// Forward x transform of the column at the front of CB_IN into DIF order in cb_dst.
template <Prep P>
inline void forward(uint32_t cb_dst) {
#if GRID_SX == 128
    regs_begin();
    load_tiles(CB_IN, 0, CT, 0);
    SFPU((prep<P>(), p2_forward()));
    regs_handoff();
    pack_tiles(0, CT, cb_dst);
    tile_regs_release();
#elif GRID_SX == 256
    for (uint32_t q = 0; q < CHUNKS; q++) {
        regs_begin();
        load_tiles(CB_IN, CW * q, CW, 0);
        load_tiles(CB_IN, HALF + CW * q, CW, CW);
        load_tiles(CB_W, CW * q, CW, 2 * CW);
        SFPU((prep<P>(), p2_split_forward()));
        regs_handoff();
        pack_tiles(0, 2 * CW, CB_T);
        tile_regs_release();
    }
    cb_wait_front(CB_T, CT);
    for (uint32_t h = 0; h < 2; h++) {
        regs_begin();
        for (uint32_t q = 0; q < CHUNKS; q++) {
            load_tiles(CB_T, 2 * CW * q + CW * h, CW, CW * q);
        }
        SFPU(p2_forward());
        regs_handoff();
        pack_tiles(0, HALF, cb_dst);
        tile_regs_release();
    }
    cb_pop_front(CB_T, CT);
#else
#error "pass 2 supports 128- and 256-point columns"
#endif
}

// Multiplies one column spectrum by a kernel column and runs the inverse x transform. The
// spectrum does not fit DST next to the kernel, so the early DIT stages run per 64-point
// block. The result leaves chunk by chunk, compacted to its real part when COMPACT.
template <bool COMPACT>
inline void column(uint32_t cb_f, uint32_t h_first) {
    for (uint32_t b = 0; b < BLOCKS; b++) {
        regs_begin();
        load_tiles(cb_f, 4 * b, 4, 0);
        load_tiles(CB_H, h_first + 2 * b, 2, 4);
        SFPU(p2_block());
        regs_handoff();
        pack_tiles(0, 4, CB_T);
        tile_regs_release();
    }
    cb_wait_front(CB_T, CT);
#if GRID_SX == 128
    regs_begin();
    load_tiles(CB_T, 0, CT, 0);
    if constexpr (COMPACT) {
        SFPU((p2_final(), p2_compact()));
    } else {
        SFPU(p2_final());
    }
    regs_handoff();
    cb_pop_front(CB_T, CT);
    pack_tiles(0, COMPACT ? CW : 2 * CW, COMPACT ? CB_R : CB_OUT);
    tile_regs_release();
#else
    for (uint32_t h = 0; h < 2; h++) {
        regs_begin();
        load_tiles(CB_T, HALF * h, HALF, 0);
        SFPU(p2_final());
        regs_handoff();
        pack_tiles(0, HALF, CB_U);
        tile_regs_release();
    }
    cb_pop_front(CB_T, CT);
    cb_wait_front(CB_U, CT);
    for (uint32_t q = 0; q < CHUNKS; q++) {
        regs_begin();
        load_tiles(CB_U, CW * q, CW, 0);
        load_tiles(CB_U, HALF + CW * q, CW, CW);
        load_tiles(CB_W, CW * q, CW, 2 * CW);
        if constexpr (COMPACT) {
            SFPU((p2_split_inverse(), p2_compact()));
        } else {
            SFPU(p2_split_inverse());
        }
        regs_handoff();
        pack_tiles(0, COMPACT ? CW : 2 * CW, COMPACT ? CB_R : CB_OUT);
        tile_regs_release();
    }
    cb_pop_front(CB_U, CT);
#endif
}

// ky = 0 packs the real bins 0 and SY/2 into one complex column. Their kernel columns differ,
// so each real part is transformed on its own and the two real results are packed back.
inline void column_zero(uint32_t c) {
    forward<Prep::zero_imag>(CB_F);
    forward<Prep::imag_to_real>(CB_F2);
    cb_pop_front(CB_IN, CT);
    cb_wait_front(CB_F, CT);
    cb_wait_front(CB_F2, CT);
    for (uint32_t k = 0; k < NK; k++) {
        if (c0[k] != c) {
            continue;
        }
        cb_wait_front(CB_H, 2 * HT);
        column<true>(CB_F, 0);
        column<true>(CB_F2, HT);
        cb_pop_front(CB_H, 2 * HT);
        cb_wait_front(CB_R, CT);
        for (uint32_t q = 0; q < CHUNKS; q++) {
            regs_begin();
            load_tiles(CB_R, HALF + CW * q, CW, 0);
            load_tiles(CB_R, CW * q, CW, CW);
            SFPU(p2_merge());
            regs_handoff();
            pack_tiles(0, 2 * CW, CB_OUT);
            tile_regs_release();
        }
        cb_pop_front(CB_R, CT);
    }
    cb_pop_front(CB_F, CT);
    cb_pop_front(CB_F2, CT);
}

void kernel_main() {
    const uint32_t begin = get_arg_val<uint32_t>(1);
    const uint32_t end = get_arg_val<uint32_t>(2);
    init_sfpu(CB_IN, CB_OUT);
#if GRID_SX == 256
    cb_wait_front(CB_W, HALF);
#endif
    for (uint32_t unit = begin; unit < end; unit++) {
        const uint32_t c = unit / M;
        cb_wait_front(CB_IN, CT);
        if (unit % M == 0) {
            column_zero(c);
            continue;
        }
        forward<Prep::none>(CB_F);
        cb_pop_front(CB_IN, CT);
        cb_wait_front(CB_F, CT);
        for (uint32_t k = 0; k < NK; k++) {
            if (c0[k] != c) {
                continue;
            }
            cb_wait_front(CB_H, HT);
            column<false>(CB_F, 0);
            cb_pop_front(CB_H, HT);
        }
        cb_pop_front(CB_F, CT);
    }
}
