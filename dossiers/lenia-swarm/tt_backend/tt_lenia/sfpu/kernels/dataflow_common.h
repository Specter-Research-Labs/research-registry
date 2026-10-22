#pragma once
#include <stdint.h>
#include "api/dataflow/dataflow_api.h"
#include "shape.h"

constexpr uint32_t PAGE = 4096;
constexpr uint32_t CHUNK = 256;

constexpr uint32_t CB_IN = tt::CBIndex::c_0;
constexpr uint32_t CB_H = tt::CBIndex::c_1;
constexpr uint32_t CB_PAR = tt::CBIndex::c_7;
constexpr uint32_t CB_W = tt::CBIndex::c_11;
constexpr uint32_t CB_MASS = tt::CBIndex::c_9;
constexpr uint32_t CB_OUT = tt::CBIndex::c_16;
constexpr uint32_t CB_OUT2 = tt::CBIndex::c_17;
constexpr uint32_t CB_CAP = tt::CBIndex::c_18;

inline uint32_t bitrev(uint32_t i, uint32_t n) {
    uint32_t r = 0;
    for (uint32_t b = 1; b < n; b <<= 1) {
        r = (r << 1) | (i & 1);
        i >>= 1;
    }
    return r;
}

template <typename A>
inline void read_pages(const A& src, uint32_t first, uint32_t count, uint32_t l1) {
    for (uint32_t i = 0; i < count; i++) {
        noc_async_read_page(first + i, src, l1 + i * PAGE);
    }
}

template <typename A>
inline void write_pages(const A& dst, uint32_t first, uint32_t count, uint32_t l1) {
    for (uint32_t i = 0; i < count; i++) {
        noc_async_write_page(first + i, dst, l1 + i * PAGE);
    }
}

template <typename A>
inline void read_twiddles(const A& src) {
    cb_reserve_back(CB_W, TW_TILES);
    read_pages(src, 0, TW_TILES, get_write_ptr(CB_W));
    noc_async_read_barrier();
    cb_push_back(CB_W, TW_TILES);
}
