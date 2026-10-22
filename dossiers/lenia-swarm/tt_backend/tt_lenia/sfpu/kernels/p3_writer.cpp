#include "dataflow_common.h"

// Affinity leaves in growth-chunk order: tile q of every channel before tile q + 1.
void kernel_main() {
    const uint32_t u_addr = get_arg_val<uint32_t>(3);
    const uint32_t matter_addr = get_arg_val<uint32_t>(4);
    [[maybe_unused]] const uint32_t pot_addr = get_arg_val<uint32_t>(5);
    const uint32_t group = get_arg_val<uint32_t>(0);
    const uint32_t begin = get_arg_val<uint32_t>(1);
    const uint32_t end = get_arg_val<uint32_t>(2);
    constexpr auto u_args = TensorAccessorArgs<0>();
    constexpr auto matter_args = TensorAccessorArgs<u_args.next_compile_time_args_offset()>();
    const auto u = TensorAccessor(u_args, u_addr, PAGE);
    const auto matter = TensorAccessor(matter_args, matter_addr, PAGE);
#ifdef CAPTURE
    constexpr auto pot_args = TensorAccessorArgs<matter_args.next_compile_time_args_offset()>();
    const auto pot = TensorAccessor(pot_args, pot_addr, PAGE);
#endif
    for (uint32_t x = begin; x < end; x++) {
#ifdef CAPTURE
        for (uint32_t k = 0; k < NK; k++) {
            cb_wait_front(CB_CAP, T);
            write_pages(pot, ((group * SX + x) * NK + k) * T, T, get_read_ptr(CB_CAP));
            noc_async_writes_flushed();
            cb_pop_front(CB_CAP, T);
        }
#endif
        for (uint32_t q = 0; q < T; q++) {
            for (uint32_t c = 0; c < NC; c++) {
                cb_wait_front(CB_OUT, 1);
                write_pages(u, ((group * NC + c) * SX + x) * T + q, 1, get_read_ptr(CB_OUT));
                noc_async_writes_flushed();
                cb_pop_front(CB_OUT, 1);
            }
        }
        for (uint32_t q = 0; q < T; q++) {
            cb_wait_front(CB_OUT2, 1);
            write_pages(matter, (group * SX + x) * T + q, 1, get_read_ptr(CB_OUT2));
            noc_async_writes_flushed();
            cb_pop_front(CB_OUT2, 1);
        }
    }
    noc_async_write_barrier();
}
