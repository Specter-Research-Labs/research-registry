#include "dataflow_common.h"

// Gathers row x of every kernel response, placing bin ky at chunk bitrev(ky) because the
// inverse row transform consumes bit-reversed input.
void kernel_main() {
    const uint32_t resp_addr = get_arg_val<uint32_t>(3);
    const uint32_t mass_addr = get_arg_val<uint32_t>(4);
    const uint32_t par_addr = get_arg_val<uint32_t>(5);
    const uint32_t group = get_arg_val<uint32_t>(0);
    const uint32_t begin = get_arg_val<uint32_t>(1);
    const uint32_t end = get_arg_val<uint32_t>(2);
    constexpr auto resp_args = TensorAccessorArgs<0>();
    constexpr auto mass_args = TensorAccessorArgs<resp_args.next_compile_time_args_offset()>();
    constexpr auto par_args = TensorAccessorArgs<mass_args.next_compile_time_args_offset()>();
    const auto resp = TensorAccessor(resp_args, resp_addr, PAGE);
    const auto mass = TensorAccessor(mass_args, mass_addr, PAGE);
    const auto par = TensorAccessor(par_args, par_addr, PAGE);
    cb_reserve_back(CB_PAR, 2);
    read_pages(par, group * 2, 2, get_write_ptr(CB_PAR));
    noc_async_read_barrier();
    cb_push_back(CB_PAR, 2);
    for (uint32_t x = begin; x < end; x++) {
        const uint32_t offset = (x % 16) * CHUNK;
        for (uint32_t k = 0; k < NK; k++) {
            cb_reserve_back(CB_IN, T);
            const uint32_t l1 = get_write_ptr(CB_IN);
            for (uint32_t ky = 0; ky < M; ky++) {
                const uint32_t page = ((group * NK + k) * M + ky) * CT + x / 16;
                noc_async_read(resp.get_noc_addr(page, offset), l1 + bitrev(ky, M) * CHUNK, CHUNK);
            }
            noc_async_read_barrier();
            cb_push_back(CB_IN, T);
        }
        cb_reserve_back(CB_MASS, NC * T);
        const uint32_t l1 = get_write_ptr(CB_MASS);
        for (uint32_t c = 0; c < NC; c++) {
            read_pages(mass, ((group * NC + c) * SX + x) * T, T, l1 + c * T * PAGE);
        }
        noc_async_read_barrier();
        cb_push_back(CB_MASS, NC * T);
    }
}
