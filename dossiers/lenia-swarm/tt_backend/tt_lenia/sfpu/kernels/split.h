#pragma once
#include "compute_common.h"

constexpr uint32_t CB_W = tt::CBIndex::c_11;

__attribute__((noinline)) void pack_at(uint32_t slot, uint32_t count, uint32_t cb, uint32_t index) {
    for (uint32_t i = 0; i < count; i++) {
        pack_tile<true>(slot + i, cb, index + i);
    }
}

// Where the chunks of a split stage go: back to their own tiles of one reservation, or out in
// chunk order, whole or compacted to the real parts.
enum class Out { natural, chunks, compact };

// One radix-2 stage of span `span` complex values over the `tiles` tiles at the front of src.
// A chunk is SPLIT_TILES tiles from each half of a span block next to their twiddles, and
// Stage::run is the generated stage with any work that rides along on the chunk.
template <typename Stage, Out O>
void split_stage(uint32_t src, uint32_t tiles, uint32_t span, uint32_t dst) {
    const uint32_t block = span / 16;
    const uint32_t half = block / 2;
    const uint32_t tw = twiddle_tile(span);
    if constexpr (O == Out::natural) {
        cb_reserve_back(dst, tiles);
    }
    for (uint32_t b = 0; b < tiles; b += block) {
        for (uint32_t q = 0; q < half; q += SPLIT_TILES) {
            regs_begin();
            load_tiles(src, b + q, SPLIT_TILES, 0);
            load_tiles(src, b + half + q, SPLIT_TILES, SPLIT_TILES);
            load_tiles(CB_W, tw + q, SPLIT_TILES, 2 * SPLIT_TILES);
            SFPU(Stage::run());
            regs_handoff();
            if constexpr (O == Out::natural) {
                pack_at(0, SPLIT_TILES, dst, b + q);
                pack_at(SPLIT_TILES, SPLIT_TILES, dst, b + half + q);
            } else {
                pack_tiles(0, O == Out::compact ? SPLIT_TILES : 2 * SPLIT_TILES, dst);
            }
            tile_regs_release();
        }
    }
    if constexpr (O == Out::natural) {
        cb_push_back(dst, tiles);
    }
}
