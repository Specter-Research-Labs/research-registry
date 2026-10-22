#include "dataflow_common.h"

// Scatters each row spectrum into column-major S[c][ky][x] so that pass 2 reads whole
// columns contiguously. The row FFT leaves bin k at chunk bitrev(k).
void kernel_main() {
    const uint32_t spec_addr = get_arg_val<uint32_t>(3);
    const uint32_t group = get_arg_val<uint32_t>(0);
    const uint32_t begin = get_arg_val<uint32_t>(1);
    const uint32_t end = get_arg_val<uint32_t>(2);
    constexpr auto spec_args = TensorAccessorArgs<0>();
    const auto spec = TensorAccessor(spec_args, spec_addr, PAGE);
    for (uint32_t row = begin; row < end; row++) {
        const uint32_t c = row / SX;
        const uint32_t x = row % SX;
        cb_wait_front(CB_OUT, T);
        const uint32_t l1 = get_read_ptr(CB_OUT);
        const uint32_t offset = (x % 16) * CHUNK;
        for (uint32_t p = 0; p < M; p++) {
            const uint32_t page = ((group * NC + c) * M + bitrev(p, M)) * CT + x / 16;
            noc_async_write(l1 + p * CHUNK, spec.get_noc_addr(page, offset), CHUNK);
        }
        noc_async_writes_flushed();
        cb_pop_front(CB_OUT, T);
    }
    noc_async_write_barrier();
}
