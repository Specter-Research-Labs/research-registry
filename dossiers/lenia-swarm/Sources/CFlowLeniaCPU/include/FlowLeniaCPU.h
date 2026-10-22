#ifndef FLOW_LENIA_CPU_H
#define FLOW_LENIA_CPU_H

#include <stdint.h>

/// Grid and rule constants for one engine. Derived constants are computed by the caller
/// exactly as the Metal pipeline computes them, so both backends use the same floats.
typedef struct FLCPUConfig {
    int32_t batchCount;
    int32_t sx;
    int32_t sy;
    int32_t channelCount;
    int32_t kernelCount;
    int32_t kernelBatchCount;
    int32_t dd;
    int32_t n;
    int32_t alphaPerChannel;
    int32_t clipFlow;
    int32_t threadCount;
    float dt;
    float sigma;
    float thetaA;
    float clipMax;
    float maxAdvection;
    float areaScale;
    float inverseScale;
    /// exp(-2 pi i m / sx) and exp(-2 pi i m / sy) as interleaved (cos, sin) pairs.
    const float *twiddleX;
    const float *twiddleY;
    /// Radix sequence of each side, all entries 2 or 4.
    const int32_t *radicesX;
    int32_t radixCountX;
    const int32_t *radicesY;
    int32_t radixCountY;
} FLCPUConfig;

typedef struct FLCPUEngine FLCPUEngine;

typedef struct FLCPUMassSummary {
    float totalMass;
    float sumSquares;
    float energy;
    float weightedX;
    float weightedY;
    float occupancyCount;
    float rawGyration;
} FLCPUMassSummary;

int32_t flcpu_available_threads(void);

FLCPUEngine *flcpu_create(const FLCPUConfig *config);
void flcpu_destroy(FLCPUEngine *engine);

/// spectra: real kernel spectra in the Metal layout [kernelBatch][sy / 2 + 1][kernelCount][sx].
/// m, s: [batch][kernelCount]. outputWeights: [channel][kernelCount].
void flcpu_set_kernels(
    FLCPUEngine *engine,
    const float *spectra,
    const int32_t *c0Idxs,
    const float *m,
    const float *s,
    const float *outputWeights
);
void flcpu_set_matter_weights(FLCPUEngine *engine, const float *weights);
/// potential: [batch][sx][sy], or NULL to disable.
void flcpu_set_potential(FLCPUEngine *engine, const float *potential);

/// mass: [batch][sx][sy][channel]. params: [batch][sx][sy][kernelCount].
void flcpu_set_state(FLCPUEngine *engine, const float *mass, const float *params);
void flcpu_get_mass(const FLCPUEngine *engine, float *mass);
void flcpu_get_params(const FLCPUEngine *engine, float *params);
/// The growth potential U of the last step, potential field included: [batch][sx][sy][channel].
void flcpu_get_last_potential(const FLCPUEngine *engine, float *potential);
/// out: [batch][sx][sy].
void flcpu_mass_map(const FLCPUEngine *engine, const float *channelWeights, float *out);
void flcpu_summarize(
    const FLCPUEngine *engine,
    float occupancyThreshold,
    const float *channelWeights,
    int32_t includeGyration,
    FLCPUMassSummary *out
);

/// origins: [batch][2] as (x0, y0). A negative origin leaves that batch element untouched.
void flcpu_zero_state_patch(FLCPUEngine *engine, const int32_t *origins, int32_t size);
/// deltas: [batch][size][size][kernelCount].
void flcpu_parameter_patch(
    FLCPUEngine *engine,
    const int32_t *origins,
    int32_t size,
    const float *deltas,
    int32_t applyClip,
    float clipLow,
    float clipHigh
);

void flcpu_step(FLCPUEngine *engine, int32_t count);

#endif
