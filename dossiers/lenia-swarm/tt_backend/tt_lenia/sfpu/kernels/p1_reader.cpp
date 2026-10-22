#include "dataflow_common.h"

void kernel_main() {
    const uint32_t mass_addr = get_arg_val<uint32_t>(3);
    const uint32_t group = get_arg_val<uint32_t>(0);
    const uint32_t begin = get_arg_val<uint32_t>(1);
    const uint32_t end = get_arg_val<uint32_t>(2);
    constexpr auto mass_args = TensorAccessorArgs<0>();
    const auto mass = TensorAccessor(mass_args, mass_addr, PAGE);
    for (uint32_t row = begin; row < end; row++) {
        cb_reserve_back(CB_IN, T);
        read_pages(mass, (group * NC * SX + row) * T, T, get_write_ptr(CB_IN));
        noc_async_read_barrier();
        cb_push_back(CB_IN, T);
    }
}
