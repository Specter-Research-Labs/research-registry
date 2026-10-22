#include "dataflow_common.h"

void kernel_main() {
    const uint32_t shift_addr = get_arg_val<uint32_t>(3);
    [[maybe_unused]] const uint32_t flow_addr = get_arg_val<uint32_t>(4);
    const uint32_t group = get_arg_val<uint32_t>(0);
    const uint32_t begin = get_arg_val<uint32_t>(1);
    const uint32_t end = get_arg_val<uint32_t>(2);
    constexpr auto shift_args = TensorAccessorArgs<0>();
    const auto shift = TensorAccessor(shift_args, shift_addr, PAGE);
#ifdef CAPTURE
    constexpr auto flow_args = TensorAccessorArgs<shift_args.next_compile_time_args_offset()>();
    const auto flow = TensorAccessor(flow_args, flow_addr, PAGE);
#endif
    for (uint32_t block = begin; block < end; block++) {
        const uint32_t c = block / (SX * T);
        const uint32_t x = block / T % SX;
        const uint32_t s = block % T;
        for (uint32_t axis = 0; axis < 2; axis++) {
            const uint32_t page = (((group * NC + c) * 2 + axis) * SX + x) * T + s;
            cb_wait_front(CB_OUT, 1);
            write_pages(shift, page, 1, get_read_ptr(CB_OUT));
#ifdef CAPTURE
            cb_wait_front(CB_CAP, 1);
            write_pages(flow, page, 1, get_read_ptr(CB_CAP));
#endif
            noc_async_writes_flushed();
            cb_pop_front(CB_OUT, 1);
#ifdef CAPTURE
            cb_pop_front(CB_CAP, 1);
#endif
        }
    }
    noc_async_write_barrier();
}
