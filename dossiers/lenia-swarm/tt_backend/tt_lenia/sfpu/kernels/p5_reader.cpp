#include "dataflow_common.h"

constexpr uint32_t HALO = (DD + 1) / 2;
constexpr uint32_t WINDOW = 8 + 2 * HALO;
constexpr uint32_t ROW_CHUNKS = 16 * T;

// One 16-cell segment of a row and the HALO chunks on either side, composed into one page.
// A window crosses exactly one page boundary, so it takes two reads.
template <typename A>
inline void read_window(const A& src, uint32_t row_page, uint32_t seg, uint32_t l1) {
    const uint32_t start = (8 * seg + ROW_CHUNKS - HALO) % ROW_CHUNKS;
    const uint32_t page = start / 16;
    const uint32_t offset = start % 16;
    const uint32_t first = 16 - offset;
    noc_async_read(src.get_noc_addr(row_page + page, offset * CHUNK), l1, first * CHUNK);
    noc_async_read(src.get_noc_addr(row_page + (page + 1) % T, 0), l1 + first * CHUNK, (WINDOW - first) * CHUNK);
}

// For a block of ROWS target rows from x0, streams the windows of source rows
// x0 + ROWS - 1 + DD down to x0 - DD for each segment: mass, shift x, shift y.
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
    for (uint32_t block = begin; block < end; block++) {
        const uint32_t c = block * ROWS / SX;
        const uint32_t x0 = block * ROWS % SX;
        for (uint32_t seg = 0; seg < 2 * T; seg++) {
            for (uint32_t k = 0; k < ROWS + 2 * DD; k++) {
                const uint32_t xs = (x0 + ROWS - 1 + DD + SX - k) % SX;
                cb_reserve_back(CB_IN, 3);
                const uint32_t l1 = get_write_ptr(CB_IN);
                read_window(mass, ((group * NC + c) * SX + xs) * T, seg, l1);
                read_window(shift, (((group * NC + c) * 2 + 0) * SX + xs) * T, seg, l1 + PAGE);
                read_window(shift, (((group * NC + c) * 2 + 1) * SX + xs) * T, seg, l1 + 2 * PAGE);
                noc_async_read_barrier();
                cb_push_back(CB_IN, 3);
            }
        }
    }
}
