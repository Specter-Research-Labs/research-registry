#include "dataflow_common.h"

// For target row x, streams source rows x - dx in Metal's dx order: mass, shift x, shift y.
void kernel_main() {
    const uint32_t mass_addr = get_arg_val<uint32_t>(3);
    const uint32_t shift_addr = get_arg_val<uint32_t>(4);
    const uint32_t group = get_arg_val<uint32_t>(0);
    const uint32_t begin = get_arg_val<uint32_t>(1);
    const uint32_t end = get_arg_val<uint32_t>(2);
    constexpr auto mass_args = TensorAccessorArgs<0>();
    constexpr auto shift_args = TensorAccessorArgs<mass_args.next_compile_time_args_offset()>();
    const auto mass = TensorAccessor(mass_args, mass_addr, PAGE);
    const auto shift = TensorAccessor(shift_args, shift_addr, PAGE);
    for (uint32_t row = begin; row < end; row++) {
        const uint32_t c = row / SX;
        const uint32_t x = row % SX;
        for (int32_t dx = -DD; dx <= DD; dx++) {
            const uint32_t xs = (x + SX - dx) % SX;
            cb_reserve_back(CB_IN, 3 * T);
            const uint32_t l1 = get_write_ptr(CB_IN);
            read_pages(mass, ((group * NC + c) * SX + xs) * T, T, l1);
            read_pages(shift, (((group * NC + c) * 2 + 0) * SX + xs) * T, T, l1 + T * PAGE);
            read_pages(shift, (((group * NC + c) * 2 + 1) * SX + xs) * T, T, l1 + 2 * T * PAGE);
            noc_async_read_barrier();
            cb_push_back(CB_IN, 3 * T);
        }
    }
}
