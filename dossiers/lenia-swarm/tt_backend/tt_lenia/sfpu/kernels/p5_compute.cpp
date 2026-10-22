#include "compute_common.h"

// The accumulators of a ROWS x 16 target block stay in DST slots 0-1 while the source rows
// stream through slots 2-4, so each target sums its terms in Metal's dx-outer, dy-inner order.
void kernel_main() {
    const uint32_t begin = get_arg_val<uint32_t>(1);
    const uint32_t end = get_arg_val<uint32_t>(2);
    init_sfpu(CB_IN, CB_OUT);
    for (uint32_t block = begin; block < end; block++) {
        for (uint32_t seg = 0; seg < 2 * T; seg++) {
            regs_begin();
            SFPU(reint_zero());
            for (uint32_t k = 0; k < ROWS + 2 * DD; k++) {
                cb_wait_front(CB_IN, 3);
                {
                    DeviceZoneScopedSumN1("p5-copy");
                    load_tiles(CB_IN, 0, 3, 2);
                }
                {
                    DeviceZoneScopedSumN2("p5-sfpu");
                    SFPU(reint_source(k));
                }
                cb_pop_front(CB_IN, 3);
            }
            SFPU(reint_scale());
            regs_handoff();
            pack_tiles(0, 2, CB_OUT);
            tile_regs_release();
        }
    }
}
