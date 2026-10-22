#include "compute_common.h"

void kernel_main() {
    const uint32_t begin = get_arg_val<uint32_t>(1);
    const uint32_t end = get_arg_val<uint32_t>(2);
    init_sfpu(CB_IN, CB_OUT);
    for (uint32_t block = begin; block < end; block++) {
        cb_wait_front(CB_IN, 7);
        for (uint32_t axis = 0; axis < 2; axis++) {
            regs_begin();
            load_tiles(CB_IN, 0, 7, 0);
            if (axis == 0) {
                SFPU(flow_x());
            } else {
                SFPU(flow_y());
            }
            regs_handoff();
            pack_tiles(6, 1, CB_OUT);
#ifdef CAPTURE
            pack_tiles(7, 1, CB_CAP);
#endif
            tile_regs_release();
        }
        cb_pop_front(CB_IN, 7);
    }
}
