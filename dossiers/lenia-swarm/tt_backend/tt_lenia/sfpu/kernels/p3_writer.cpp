#include "dataflow_common.h"
#include GEN_HEADER

// Pass 3 emits growth chunk by chunk: the captured potentials of the chunk's kernels, then
// the channel's affinity once its last chunk is done.
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
        for (uint32_t i = 0; i < GROWTH_CHUNKS; i++) {
#ifdef CAPTURE
            for (uint32_t j = 0; j < growth_len[i]; j++) {
                const uint32_t k = growth_kernel[i][j];
                cb_wait_front(CB_CAP, T);
                write_pages(pot, ((group * SX + x) * NK + k) * T, T, get_read_ptr(CB_CAP));
                noc_async_writes_flushed();
                cb_pop_front(CB_CAP, T);
            }
#endif
            if (!growth_last[i]) {
                continue;
            }
            const uint32_t c = growth_channel[i];
            for (uint32_t q = 0; q < T; q++) {
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
