#include "compute_common.h"

void kernel_main() {
    const uint32_t begin = get_arg_val<uint32_t>(1);
    const uint32_t end = get_arg_val<uint32_t>(2);
    init_sfpu(CB_IN, CB_OUT);
    for (uint32_t row = begin; row < end; row++) {
        cb_wait_front(CB_IN, T);
        regs_begin();
        load_tiles(CB_IN, 0, T, 0);
        SFPU(p1_row());
        regs_handoff();
        cb_pop_front(CB_IN, T);
        pack_tiles(0, T, CB_OUT);
        tile_regs_release();
    }
}
