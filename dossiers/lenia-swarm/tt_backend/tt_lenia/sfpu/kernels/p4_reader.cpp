#include "dataflow_common.h"

// The halo tile keeps, for input row r, cells y0-2 and y0-1 in chunk 2r and cells y0+32 and
// y0+33 in chunk 2r+1, which are the edge chunks of the neighboring tiles of that row.
template <typename A>
inline void read_row(const A& src, uint32_t base, uint32_t s, uint32_t r, uint32_t l1, uint32_t halo) {
    noc_async_read_page(base + s, src, l1 + r * PAGE);
    noc_async_read(src.get_noc_addr(base + (s + T - 1) % T, 15 * CHUNK), halo + 2 * r * CHUNK, CHUNK);
    noc_async_read(src.get_noc_addr(base + (s + 1) % T, 0), halo + (2 * r + 1) * CHUNK, CHUNK);
}

void kernel_main() {
    const uint32_t u_addr = get_arg_val<uint32_t>(3);
    const uint32_t matter_addr = get_arg_val<uint32_t>(4);
    const uint32_t group = get_arg_val<uint32_t>(0);
    const uint32_t begin = get_arg_val<uint32_t>(1);
    const uint32_t end = get_arg_val<uint32_t>(2);
    constexpr auto u_args = TensorAccessorArgs<0>();
    constexpr auto matter_args = TensorAccessorArgs<u_args.next_compile_time_args_offset()>();
    const auto u = TensorAccessor(u_args, u_addr, PAGE);
    const auto matter = TensorAccessor(matter_args, matter_addr, PAGE);
    for (uint32_t block = begin; block < end; block++) {
        const uint32_t c = block / (SX * T);
        const uint32_t x = block / T % SX;
        const uint32_t s = block % T;
        cb_reserve_back(CB_IN, 7);
        const uint32_t l1 = get_write_ptr(CB_IN);
        const uint32_t halo = l1 + 6 * PAGE;
        for (uint32_t r = 0; r < 3; r++) {
            const uint32_t xr = (x + SX - 1 + r) % SX;
            read_row(u, ((group * NC + c) * SX + xr) * T, s, r, l1, halo);
            read_row(matter, (group * SX + xr) * T, s, 3 + r, l1, halo);
        }
        noc_async_read_barrier();
        cb_push_back(CB_IN, 7);
    }
}
