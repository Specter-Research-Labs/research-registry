#include "dataflow_common.h"

// Pass 2 emits a column chunk by chunk, CW tiles from each column half per chunk.
inline uint32_t column_tile(uint32_t i) { return (i / CW) % 2 * (CT / 2) + i / (2 * CW) * CW + i % CW; }

void kernel_main() {
    const uint32_t resp_addr = get_arg_val<uint32_t>(3);
    const uint32_t group = get_arg_val<uint32_t>(0);
    const uint32_t begin = get_arg_val<uint32_t>(1);
    const uint32_t end = get_arg_val<uint32_t>(2);
    constexpr auto resp_args = TensorAccessorArgs<0>();
    const auto resp = TensorAccessor(resp_args, resp_addr, PAGE);
    for (uint32_t unit = begin; unit < end; unit++) {
        const uint32_t c = unit / M;
        const uint32_t ky = unit % M;
        for (uint32_t k = 0; k < NK; k++) {
            if (c0[k] != c) {
                continue;
            }
            const uint32_t base = ((group * NK + k) * M + ky) * CT;
            cb_wait_front(CB_OUT, CT);
            const uint32_t l1 = get_read_ptr(CB_OUT);
            for (uint32_t i = 0; i < CT; i++) {
                noc_async_write_page(base + column_tile(i), resp, l1 + i * PAGE);
            }
            noc_async_writes_flushed();
            cb_pop_front(CB_OUT, CT);
        }
    }
    noc_async_write_barrier();
}
