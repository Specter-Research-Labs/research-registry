#include "compute_common.h"

void kernel_main() {
    const uint32_t begin = get_arg_val<uint32_t>(1);
    const uint32_t end = get_arg_val<uint32_t>(2);
    init_sfpu(CB_IN, CB_OUT);
    cb_wait_front(CB_PAR, 2);
    for (uint32_t x = begin; x < end; x++) {
        for (uint32_t k = 0; k < NK; k++) {
            cb_wait_front(CB_IN, T);
            regs_begin();
            load_tiles(CB_IN, 0, T, 0);
            SFPU(p3_row());
            regs_handoff();
            cb_pop_front(CB_IN, T);
            pack_tiles(0, T, CB_P);
#ifdef CAPTURE
            pack_tiles(0, T, CB_CAP);
#endif
            tile_regs_release();
        }
        cb_wait_front(CB_P, NK * T);
        for (uint32_t q = 0; q < T; q++) {
            for (uint32_t i = 0; i < GROWTH_CHUNKS; i++) {
                const bool first = growth_first[i];
                const bool last = growth_last[i];
                if (!first) {
                    cb_wait_front(CB_ACC, 1);
                }
                regs_begin();
                if (!first) {
                    load_tiles(CB_ACC, 0, 1, 0);
                }
                copy_tile_to_dst_init_short(CB_P);
                for (uint32_t j = 0; j < growth_len[i]; j++) {
                    copy_tile(CB_P, growth_kernel[i][j] * T + q, 1 + j);
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
        }
        cb_pop_front(CB_P, NK * T);
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
