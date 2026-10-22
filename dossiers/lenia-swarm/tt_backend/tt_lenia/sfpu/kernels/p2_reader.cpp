#include "dataflow_common.h"

void kernel_main() {
    const uint32_t spec_addr = get_arg_val<uint32_t>(3);
    const uint32_t h_addr = get_arg_val<uint32_t>(4);
    const uint32_t group = get_arg_val<uint32_t>(0);
    const uint32_t begin = get_arg_val<uint32_t>(1);
    const uint32_t end = get_arg_val<uint32_t>(2);
    constexpr auto spec_args = TensorAccessorArgs<0>();
    constexpr auto h_args = TensorAccessorArgs<spec_args.next_compile_time_args_offset()>();
    const auto spec = TensorAccessor(spec_args, spec_addr, PAGE);
    const auto h = TensorAccessor(h_args, h_addr, PAGE);
#if GRID_SX > 128
    constexpr auto w_args = TensorAccessorArgs<h_args.next_compile_time_args_offset()>();
    read_twiddles(TensorAccessor(w_args, get_arg_val<uint32_t>(5), PAGE));
#endif
    for (uint32_t unit = begin; unit < end; unit++) {
        const uint32_t c = unit / M;
        const uint32_t ky = unit % M;
        cb_reserve_back(CB_IN, CT);
        read_pages(spec, ((group * NC + c) * M + ky) * CT, CT, get_write_ptr(CB_IN));
        noc_async_read_barrier();
        cb_push_back(CB_IN, CT);
        for (uint32_t k = 0; k < NK; k++) {
            if (c0[k] != c) {
                continue;
            }
            const uint32_t base = (group * NK + k) * (M + 1);
            if (ky == 0) {
                cb_reserve_back(CB_H, 2 * HT);
                read_pages(h, base * HT, HT, get_write_ptr(CB_H));
                read_pages(h, (base + M) * HT, HT, get_write_ptr(CB_H) + HT * PAGE);
                noc_async_read_barrier();
                cb_push_back(CB_H, 2 * HT);
            } else {
                cb_reserve_back(CB_H, HT);
                read_pages(h, (base + ky) * HT, HT, get_write_ptr(CB_H));
                noc_async_read_barrier();
                cb_push_back(CB_H, HT);
            }
        }
    }
}
