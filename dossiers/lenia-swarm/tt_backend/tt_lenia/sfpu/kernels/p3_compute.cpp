#include "compute_common.h"
#include "split.h"

struct Inverse {
    static void run() { MATH(split_inverse()); }
};

// Inverse row transform of the response at the front of CB_IN onto the back of CB_P.
inline void inverse_row() {
    cb_wait_front(CB_IN, T);
#if GRID_SY > 256
    for (uint32_t h = 0; h < 2; h++) {
        regs_begin();
        load_tiles(CB_IN, COL_TILES * h, COL_TILES, 0);
        if (h == 0) {
            SFPU(p3_half_0());
        } else {
            SFPU(p3_half_1());
        }
        regs_handoff();
        pack_tiles(0, COL_TILES, CB_T);
        tile_regs_release();
    }
    cb_pop_front(CB_IN, T);
    cb_wait_front(CB_T, T);
    split_stage<Inverse, Out::natural>(CB_T, T, M, CB_P);
    cb_pop_front(CB_T, T);
#else
    regs_begin();
    load_tiles(CB_IN, 0, T, 0);
    SFPU(p3_row());
    regs_handoff();
    cb_pop_front(CB_IN, T);
    pack_tiles(0, T, CB_P);
    tile_regs_release();
#endif
}

#ifdef CAPTURE
constexpr uint32_t CAP_BATCH = T < COL_TILES ? T : COL_TILES;

inline void capture(uint32_t j) {
    cb_wait_front(CB_P, (j + 1) * T);
    for (uint32_t i = 0; i < T; i += CAP_BATCH) {
        regs_begin();
        load_tiles(CB_P, j * T + i, CAP_BATCH, 0);
        regs_handoff();
        pack_tiles(0, CAP_BATCH, CB_CAP);
        tile_regs_release();
    }
}
#endif

// Growth runs chunk by chunk, so only one chunk's potentials sit in L1; the partial affinity
// of a channel waits in CB_ACC between its chunks.
void kernel_main() {
    const uint32_t begin = get_arg_val<uint32_t>(1);
    const uint32_t end = get_arg_val<uint32_t>(2);
    init_sfpu(CB_IN, CB_OUT);
    cb_wait_front(CB_PAR, 2);
#if GRID_SY > 256
    cb_wait_front(CB_W, TW_TILES);
#endif
    for (uint32_t x = begin; x < end; x++) {
        for (uint32_t i = 0; i < GROWTH_CHUNKS; i++) {
            const bool first = growth_first[i];
            const bool last = growth_last[i];
            const uint32_t len = growth_len[i];
            for (uint32_t j = 0; j < len; j++) {
                inverse_row();
#ifdef CAPTURE
                capture(j);
#endif
            }
            cb_wait_front(CB_P, len * T);
            for (uint32_t q = 0; q < T; q++) {
                if (!first) {
                    cb_wait_front(CB_ACC, 1);
                }
                regs_begin();
                if (!first) {
                    load_tiles(CB_ACC, 0, 1, 0);
                }
                copy_tile_to_dst_init_short(CB_P);
                for (uint32_t j = 0; j < len; j++) {
                    copy_tile(CB_P, j * T + q, 1 + j);
                }
                load_tiles(CB_PAR, 0, 2, 6);
                SFPU(growth_call(i));
                regs_handoff();
                if (!first) {
                    cb_pop_front(CB_ACC, 1);
                }
                pack_tiles(0, 1, last ? CB_OUT : CB_ACC);
                tile_regs_release();
            }
            cb_pop_front(CB_P, len * T);
        }
        cb_wait_front(CB_MASS, NC * T);
        for (uint32_t q = 0; q < T; q++) {
            regs_begin();
            copy_tile_to_dst_init_short(CB_MASS);
            for (uint32_t c = 0; c < NC; c++) {
                copy_tile(CB_MASS, c * T + q, c);
            }
            SFPU(matter());
            regs_handoff();
            pack_tiles(0, 1, CB_OUT2);
            tile_regs_release();
        }
        cb_pop_front(CB_MASS, NC * T);
    }
}
