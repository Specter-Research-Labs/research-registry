#include "compute_common.h"

#ifdef TRISC_MATH
inline void reint_block(uint32_t parity, int32_t dx, bool first, bool last) {
    if (first) {
        reint_zero();
    }
    reint_set_dx(dx);
    if (parity == 0) {
        reint_prepare_0();
        reint_terms_0();
    } else {
        reint_prepare_1();
        reint_terms_1();
    }
    if (last) {
        reint_scale();
    }
}
#endif

// A 16-cell target segment reads the two source tiles that cover it with a dd halo: tiles
// (t-1, t) for even segments and (t, t+1) for odd ones. The accumulator round-trips through
// CB_ACC between dx so the sum keeps Metal's dx-outer, dy-inner order.
void kernel_main() {
    const uint32_t begin = get_arg_val<uint32_t>(1);
    const uint32_t end = get_arg_val<uint32_t>(2);
    init_sfpu(CB_IN, CB_OUT);
    for (uint32_t row = begin; row < end; row++) {
        for (int32_t dx = -DD; dx <= DD; dx++) {
            const bool first = dx == -DD;
            const bool last = dx == DD;
            cb_wait_front(CB_IN, 3 * T);
            for (uint32_t seg = 0; seg < 2 * T; seg++) {
                const uint32_t t = seg / 2;
                const uint32_t parity = seg % 2;
                const uint32_t lo = parity ? t : (t + T - 1) % T;
                const uint32_t hi = parity ? (t + 1) % T : t;
                if (!first) {
                    cb_wait_front(CB_ACC, 1);
                }
                regs_begin();
                if (!first) {
                    load_tiles(CB_ACC, 0, 1, 0);
                }
                {
                    DeviceZoneScopedSumN1("p5-copy");
                    copy_tile_to_dst_init_short(CB_IN);
                    for (uint32_t q = 0; q < 3; q++) {
                        copy_tile(CB_IN, q * T + lo, 1 + 2 * q);
                        copy_tile(CB_IN, q * T + hi, 2 + 2 * q);
                    }
                }
                {
                    DeviceZoneScopedSumN2("p5-sfpu");
                    SFPU(reint_block(parity, dx, first, last));
                }
                regs_handoff();
                if (!first) {
                    cb_pop_front(CB_ACC, 1);
                }
                pack_tiles(0, 1, last ? CB_OUT : CB_ACC);
                tile_regs_release();
            }
            cb_pop_front(CB_IN, 3 * T);
        }
    }
}
