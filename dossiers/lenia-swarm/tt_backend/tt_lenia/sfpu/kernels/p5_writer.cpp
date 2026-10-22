#include "dataflow_common.h"

// Each output tile carries one 16-cell segment in its first eight chunks.
void kernel_main() {
    const uint32_t mass_addr = get_arg_val<uint32_t>(3);
    const uint32_t group = get_arg_val<uint32_t>(0);
    const uint32_t begin = get_arg_val<uint32_t>(1);
    const uint32_t end = get_arg_val<uint32_t>(2);
    constexpr auto mass_args = TensorAccessorArgs<0>();
    const auto mass = TensorAccessor(mass_args, mass_addr, PAGE);
    for (uint32_t row = begin; row < end; row++) {
        for (uint32_t seg = 0; seg < 2 * T; seg++) {
            cb_wait_front(CB_OUT, 1);
            const uint32_t page = (group * NC * SX + row) * T + seg / 2;
            noc_async_write(get_read_ptr(CB_OUT), mass.get_noc_addr(page, (seg % 2) * 8 * CHUNK), 8 * CHUNK);
            noc_async_writes_flushed();
            cb_pop_front(CB_OUT, 1);
        }
    }
    noc_async_write_barrier();
}
