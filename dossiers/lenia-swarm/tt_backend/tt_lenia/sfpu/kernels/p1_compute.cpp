#include "compute_common.h"
#include "split.h"

struct Forward {
    static void run() { MATH(split_forward()); }
};

void kernel_main() {
    const uint32_t begin = get_arg_val<uint32_t>(1);
    const uint32_t end = get_arg_val<uint32_t>(2);
    init_sfpu(CB_IN, CB_OUT);
#if GRID_SY > 256
    cb_wait_front(CB_W, TW_TILES);
#endif
    for (uint32_t row = begin; row < end; row++) {
        cb_wait_front(CB_IN, T);
#if GRID_SY > 256
        split_stage<Forward, Out::natural>(CB_IN, T, M, CB_T);
        cb_pop_front(CB_IN, T);
        cb_wait_front(CB_T, T);
        for (uint32_t h = 0; h < 2; h++) {
            regs_begin();
            load_tiles(CB_T, COL_TILES * h, COL_TILES, 0);
            if (h == 0) {
                SFPU(p1_half_0());
            } else {
                SFPU(p1_half_1());
            }
            regs_handoff();
            pack_tiles(0, COL_TILES, CB_OUT);
            tile_regs_release();
        }
        cb_pop_front(CB_T, T);
#else
        regs_begin();
        load_tiles(CB_IN, 0, T, 0);
        SFPU(p1_row());
        regs_handoff();
        cb_pop_front(CB_IN, T);
        pack_tiles(0, T, CB_OUT);
        tile_regs_release();
#endif
    }
}
