#include "compute_common.h"
#include "split.h"

constexpr uint32_t CB_U = tt::CBIndex::c_10;
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

template <Prep P>
struct Forward {
    static void run() { MATH((prep<P>(), split_forward())); }
};

template <bool COMPACT>
struct Inverse {
    static void run() {
        if constexpr (COMPACT) {
            MATH((split_inverse(), p2_compact()));
        } else {
            MATH(split_inverse());
        }
    }
};

inline uint32_t other(uint32_t cb) { return cb == CB_T ? CB_U : CB_T; }

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
#else
    split_stage<Forward<P>, Out::natural>(CB_IN, CT, SX, CB_T);
    uint32_t src = CB_T;
    for (uint32_t span = SX / 2; span > 128; span /= 2) {
        cb_wait_front(src, CT);
        split_stage<Forward<Prep::none>, Out::natural>(src, CT, span, other(src));
        cb_pop_front(src, CT);
        src = other(src);
    }
    cb_wait_front(src, CT);
    for (uint32_t b = 0; b < CT; b += COL_TILES) {
        regs_begin();
        load_tiles(src, b, COL_TILES, 0);
        SFPU(p2_forward());
        regs_handoff();
        pack_tiles(0, COL_TILES, cb_dst);
        tile_regs_release();
    }
    cb_pop_front(src, CT);
#endif
}

// Multiplies one column spectrum by a kernel column and runs the inverse x transform. The
// spectrum does not fit DST next to the kernel, so the early DIT stages run per 64-point
// block and the late ones per 128-point block and as split stages. The result leaves chunk
// by chunk, compacted to its real part when COMPACT.
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
    for (uint32_t b = 0; b < CT; b += COL_TILES) {
        regs_begin();
        load_tiles(CB_T, b, COL_TILES, 0);
        SFPU(p2_final());
        regs_handoff();
        pack_tiles(0, COL_TILES, CB_U);
        tile_regs_release();
    }
    cb_pop_front(CB_T, CT);
    uint32_t src = CB_U;
    for (uint32_t span = 256; span < SX; span *= 2) {
        cb_wait_front(src, CT);
        split_stage<Inverse<false>, Out::natural>(src, CT, span, other(src));
        cb_pop_front(src, CT);
        src = other(src);
    }
    cb_wait_front(src, CT);
    if constexpr (COMPACT) {
        split_stage<Inverse<true>, Out::compact>(src, CT, SX, CB_R);
    } else {
        split_stage<Inverse<false>, Out::chunks>(src, CT, SX, CB_OUT);
    }
    cb_pop_front(src, CT);
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
#if GRID_SX > 128
    cb_wait_front(CB_W, TW_TILES);
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
