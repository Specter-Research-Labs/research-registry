#include "dataflow_common.h"

// Output tile s holds segment seg of target rows 2s (first eight chunks) and 2s + 1.
void kernel_main() {
    const uint32_t mass_addr = get_arg_val<uint32_t>(3);
    const uint32_t group = get_arg_val<uint32_t>(0);
    const uint32_t begin = get_arg_val<uint32_t>(1);
    const uint32_t end = get_arg_val<uint32_t>(2);
    constexpr auto mass_args = TensorAccessorArgs<0>();
    const auto mass = TensorAccessor(mass_args, mass_addr, PAGE);
    for (uint32_t block = begin; block < end; block++) {
        for (uint32_t seg = 0; seg < 2 * T; seg++) {
            cb_wait_front(CB_OUT, 2);
            const uint32_t l1 = get_read_ptr(CB_OUT);
            for (uint32_t r = 0; r < ROWS; r++) {
                const uint32_t page = (group * NC * SX + block * ROWS + r) * T + seg / 2;
                noc_async_write(l1 + r * 8 * CHUNK, mass.get_noc_addr(page, (seg % 2) * 8 * CHUNK), 8 * CHUNK);
            }
            noc_async_writes_flushed();
            cb_pop_front(CB_OUT, 2);
        }
    }
    noc_async_write_barrier();
}
