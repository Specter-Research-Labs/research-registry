#define _GNU_SOURCE
#include "FlowLeniaCPU.h"

#include <math.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

// Every operation below is a separately rounded IEEE fp32 operation in source order, so the
// result is the same on every host and for every thread partition. Contraction would let the
// compiler fuse per call site and per target.
#pragma clang fp contract(off)

#define LANES 16

typedef float v16 __attribute__((vector_size(64)));
typedef int32_t vi16 __attribute__((vector_size(64)));

static inline v16 vload(const float *p) {
    v16 v;
    memcpy(&v, p, sizeof v);
    return v;
}

static inline void vstore(float *p, v16 v) {
    memcpy(p, &v, sizeof v);
}

static inline v16 vsplat(float x) {
    v16 v = {x, x, x, x, x, x, x, x, x, x, x, x, x, x, x, x};
    return v;
}

static inline v16 vselect(vi16 mask, v16 a, v16 b) {
    return (v16)((mask & (vi16)a) | (~mask & (vi16)b));
}

static inline v16 vmin(v16 a, v16 b) {
    return vselect(a < b, a, b);
}

static inline v16 vmax(v16 a, v16 b) {
    return vselect(a > b, a, b);
}

static inline v16 vabs(v16 a) {
    vi16 mask = {
        0x7fffffff, 0x7fffffff, 0x7fffffff, 0x7fffffff, 0x7fffffff, 0x7fffffff, 0x7fffffff, 0x7fffffff,
        0x7fffffff, 0x7fffffff, 0x7fffffff, 0x7fffffff, 0x7fffffff, 0x7fffffff, 0x7fffffff, 0x7fffffff,
    };
    return (v16)((vi16)a & mask);
}

static inline v16 vclamp(v16 a, v16 lo, v16 hi) {
    return vmin(vmax(a, lo), hi);
}

static inline float hmax(v16 v) {
    float m = v[0];
    for (int i = 1; i < LANES; ++i) {
        m = v[i] > m ? v[i] : m;
    }
    return m;
}

// Cephes expf for x <= 0. Below -87 the true value is under 2^-125, and the only caller
// computes 2 exp(x) - 1, which then rounds to exactly -1 either way.
static inline v16 vexp_nonpositive(v16 x) {
    v16 tiny = vsplat(-87.0f);
    vi16 underflow = x < tiny;
    x = vmax(x, tiny);
    v16 t = x * vsplat(1.44269504088896341f) + vsplat(0.5f);
    vi16 ti = __builtin_convertvector(t, vi16);
    v16 fl = __builtin_convertvector(ti, v16);
    vi16 over = fl > t;
    fl = vselect(over, fl - vsplat(1.0f), fl);
    x = x - fl * vsplat(0.693359375f);
    x = x - fl * vsplat(-2.12194440e-4f);
    v16 z = x * x;
    v16 y = vsplat(1.9875691500E-4f);
    y = y * x + vsplat(1.3981999507E-3f);
    y = y * x + vsplat(8.3334519073E-3f);
    y = y * x + vsplat(4.1665795894E-2f);
    y = y * x + vsplat(1.6666665459E-1f);
    y = y * x + vsplat(5.0000001201E-1f);
    y = y * z + x + vsplat(1.0f);
    vi16 n = __builtin_convertvector(fl, vi16);
    vi16 bias = {127, 127, 127, 127, 127, 127, 127, 127, 127, 127, 127, 127, 127, 127, 127, 127};
    v16 scale = (v16)((n + bias) << 23);
    return vselect(underflow, vsplat(0.0f), y * scale);
}

typedef struct FFTPlan {
    int len;
    int radixCount;
    int radices[32];
    float *twRe;
    float *twIm;
} FFTPlan;

static inline void cmul(v16 *re, v16 *im, float wr, float wi) {
    v16 r = *re;
    v16 i = *im;
    v16 w0 = vsplat(wr);
    v16 w1 = vsplat(wi);
    *re = r * w0 - i * w1;
    *im = r * w1 + i * w0;
}

// Same Stockham autosort stages, twiddle indices and butterfly arithmetic as the Metal fftStage.
static void fft(const FFTPlan *p, v16 *aRe, v16 *aIm, v16 *bRe, v16 *bIm, int inverse, v16 **outRe, v16 **outIm) {
    int len = p->len;
    int stride = 1;
    float sign = inverse ? -1.0f : 1.0f;
    for (int stage = 0; stage < p->radixCount; ++stage) {
        int radix = p->radices[stage];
        if (radix == 4) {
            int butterflies = len / 4;
            int step = len / (stride * 4);
            for (int j = 0; j < butterflies; ++j) {
                int k = j % stride;
                v16 r0 = aRe[j], i0 = aIm[j];
                v16 r1 = aRe[j + butterflies], i1 = aIm[j + butterflies];
                v16 r2 = aRe[j + 2 * butterflies], i2 = aIm[j + 2 * butterflies];
                v16 r3 = aRe[j + 3 * butterflies], i3 = aIm[j + 3 * butterflies];
                int t1 = k * step, t2 = 2 * k * step, t3 = 3 * k * step;
                cmul(&r1, &i1, p->twRe[t1], sign * p->twIm[t1]);
                cmul(&r2, &i2, p->twRe[t2], sign * p->twIm[t2]);
                cmul(&r3, &i3, p->twRe[t3], sign * p->twIm[t3]);
                v16 s02r = r0 + r2, s02i = i0 + i2;
                v16 d02r = r0 - r2, d02i = i0 - i2;
                v16 s13r = r1 + r3, s13i = i1 + i3;
                v16 d13r = r1 - r3, d13i = i1 - i3;
                v16 rotr = inverse ? -d13i : d13i;
                v16 roti = inverse ? d13r : -d13r;
                int out = (j - k) * 4 + k;
                bRe[out] = s02r + s13r;
                bIm[out] = s02i + s13i;
                bRe[out + 2 * stride] = s02r - s13r;
                bIm[out + 2 * stride] = s02i - s13i;
                bRe[out + stride] = d02r + rotr;
                bIm[out + stride] = d02i + roti;
                bRe[out + 3 * stride] = d02r - rotr;
                bIm[out + 3 * stride] = d02i - roti;
            }
        } else {
            int butterflies = len / 2;
            int step = len / (stride * 2);
            for (int j = 0; j < butterflies; ++j) {
                int k = j % stride;
                v16 r0 = aRe[j], i0 = aIm[j];
                v16 r1 = aRe[j + butterflies], i1 = aIm[j + butterflies];
                int t1 = k * step;
                cmul(&r1, &i1, p->twRe[t1], sign * p->twIm[t1]);
                int out = (j - k) * 2 + k;
                bRe[out] = r0 + r1;
                bIm[out] = i0 + i1;
                bRe[out + stride] = r0 - r1;
                bIm[out + stride] = i0 - i1;
            }
        }
        v16 *swapRe = aRe;
        v16 *swapIm = aIm;
        aRe = bRe;
        aIm = bIm;
        bRe = swapRe;
        bIm = swapIm;
        stride *= radix;
    }
    *outRe = aRe;
    *outIm = aIm;
}

static inline void cpu_relax(void) {
#if defined(__x86_64__)
    __builtin_ia32_pause();
#elif defined(__aarch64__)
    __asm__ __volatile__("yield");
#endif
}

typedef struct Barrier {
    _Alignas(64) atomic_int count;
    _Alignas(64) atomic_int sense;
    int size;
} Barrier;

static void barrier_wait(Barrier *b, int *localSense) {
    if (b->size == 1) {
        return;
    }
    int sense = !*localSense;
    *localSense = sense;
    if (atomic_fetch_add_explicit(&b->count, 1, memory_order_acq_rel) == b->size - 1) {
        atomic_store_explicit(&b->count, 0, memory_order_relaxed);
        atomic_store_explicit(&b->sense, sense, memory_order_release);
        return;
    }
    int spins = 0;
    while (atomic_load_explicit(&b->sense, memory_order_acquire) != sense) {
        if (++spins < 4096) {
            cpu_relax();
        } else {
            sched_yield();
        }
    }
}

/// Intermediates of the one body a group is stepping.
typedef struct Group {
    float *sRe;
    float *sIm;
    v16 *colRe;
    v16 *colIm;
    float *respRe;
    float *respIm;
    float *u;
    float *matter;
    float *shX;
    float *shY;
    float *stM;
    float *cellMax;
    float *blockMax;
    Barrier barrier;
    int size;
    int body;
} Group;

typedef struct Worker {
    FLCPUEngine *engine;
    Group *group;
    int rank;
    int sense;
    v16 *bufRe[2];
    v16 *bufIm[2];
    pthread_t thread;
} Worker;

struct FLCPUEngine {
    FLCPUConfig config;
    int plane;
    int reducedY;
    int paddedY;
    int kyBlocks;
    int xBlocks;
    int uStride;
    int tStride;
    FFTPlan planX;
    FFTPlan planY;

    float *mass[2];
    float *params;
    float *lastU;
    int current;

    float *spectra;
    int32_t *c0;
    float *m;
    float *s;
    float *outputWeights;
    float *matterWeights;
    float *potential;

    int groupCount;
    int groupSize;
    Group *groups;
    Worker *workers;
    int workerCount;

    pthread_mutex_t mutex;
    pthread_cond_t startCondition;
    pthread_cond_t doneCondition;
    long generation;
    int pending;
    int shutdown;
    int stepCount;
    atomic_int nextBody;
};

static void *alloc_floats(size_t count) {
    void *p = NULL;
    size_t bytes = count * sizeof(float);
    if (bytes == 0) {
        bytes = 64;
    }
    bytes = (bytes + 63) & ~(size_t)63;
    if (posix_memalign(&p, 64, bytes) != 0) {
        abort();
    }
    memset(p, 0, bytes);
    return p;
}

static inline int wrap(int i, int n) {
    int r = i % n;
    return r < 0 ? r + n : r;
}

static inline int round_up16(int n) {
    return (n + 15) & ~15;
}

static void stage_spectrum(FLCPUEngine *e, Group *g, Worker *w, int item, const float *mass) {
    const FLCPUConfig *c = &e->config;
    int sx = c->sx, sy = c->sy, R = e->reducedY, Rp = e->paddedY;
    int pair = item / e->xBlocks;
    int xb = (item % e->xBlocks) * LANES;
    int c0 = 2 * pair;
    int hasPair = c0 + 1 < c->channelCount;
    const float *m0 = mass + (size_t)c0 * e->plane;
    const float *m1 = hasPair ? m0 + e->plane : NULL;
    v16 *aRe = w->bufRe[0], *aIm = w->bufIm[0];
    for (int y = 0; y < sy; ++y) {
        aRe[y] = vload(m0 + y * sx + xb);
        aIm[y] = hasPair ? vload(m1 + y * sx + xb) : vsplat(0.0f);
    }
    v16 *rowRe, *rowIm;
    fft(&e->planY, aRe, aIm, w->bufRe[1], w->bufIm[1], 0, &rowRe, &rowIm);
    float tile[4][LANES][LANES];
    float *dstRe0 = g->sRe + (size_t)c0 * sx * Rp;
    float *dstIm0 = g->sIm + (size_t)c0 * sx * Rp;
    for (int kb = 0; kb < e->kyBlocks; ++kb) {
        for (int kl = 0; kl < LANES; ++kl) {
            int ky = kb * LANES + kl;
            v16 s0r = vsplat(0.0f), s0i = vsplat(0.0f), s1r = vsplat(0.0f), s1i = vsplat(0.0f);
            if (ky < R) {
                v16 zr = rowRe[ky], zi = rowIm[ky];
                if (hasPair) {
                    int mi = ky == 0 ? 0 : sy - ky;
                    v16 mr = rowRe[mi];
                    v16 mim = -rowIm[mi];
                    v16 half = vsplat(0.5f);
                    v16 dr = half * (zr - mr);
                    v16 di = half * (zi - mim);
                    s0r = half * (zr + mr);
                    s0i = half * (zi + mim);
                    s1r = di;
                    s1i = -dr;
                } else {
                    s0r = zr;
                    s0i = zi;
                }
            }
            vstore(tile[0][kl], s0r);
            vstore(tile[1][kl], s0i);
            vstore(tile[2][kl], s1r);
            vstore(tile[3][kl], s1i);
        }
        int planes = hasPair ? 2 : 1;
        for (int ch = 0; ch < planes; ++ch) {
            float *dRe = dstRe0 + (size_t)ch * sx * Rp;
            float *dIm = dstIm0 + (size_t)ch * sx * Rp;
            for (int xl = 0; xl < LANES; ++xl) {
                float *pr = dRe + (size_t)(xb + xl) * Rp + kb * LANES;
                float *pi = dIm + (size_t)(xb + xl) * Rp + kb * LANES;
                for (int kl = 0; kl < LANES; ++kl) {
                    pr[kl] = tile[2 * ch][kl][xl];
                    pi[kl] = tile[2 * ch + 1][kl][xl];
                }
            }
        }
    }
}

static void stage_columns(FLCPUEngine *e, Group *g, Worker *w, int item) {
    const FLCPUConfig *c = &e->config;
    int sx = c->sx, Rp = e->paddedY;
    int ch = item / e->kyBlocks;
    int kb = item % e->kyBlocks;
    const float *srcRe = g->sRe + (size_t)ch * sx * Rp + kb * LANES;
    const float *srcIm = g->sIm + (size_t)ch * sx * Rp + kb * LANES;
    v16 *aRe = w->bufRe[0], *aIm = w->bufIm[0];
    for (int x = 0; x < sx; ++x) {
        aRe[x] = vload(srcRe + (size_t)x * Rp);
        aIm[x] = vload(srcIm + (size_t)x * Rp);
    }
    v16 *outRe, *outIm;
    fft(&e->planX, aRe, aIm, w->bufRe[1], w->bufIm[1], 0, &outRe, &outIm);
    v16 *dRe = g->colRe + ((size_t)ch * e->kyBlocks + kb) * sx;
    v16 *dIm = g->colIm + ((size_t)ch * e->kyBlocks + kb) * sx;
    memcpy(dRe, outRe, sizeof(v16) * sx);
    memcpy(dIm, outIm, sizeof(v16) * sx);
}

static void stage_responses(FLCPUEngine *e, Group *g, Worker *w, int item, int body) {
    const FLCPUConfig *c = &e->config;
    int sx = c->sx, R = e->reducedY, Rp = e->paddedY, K = c->kernelCount;
    int k = item / e->kyBlocks;
    int kb = item % e->kyBlocks;
    int source = e->c0[k];
    int kernelBatch = c->kernelBatchCount == 1 ? 0 : body;
    const v16 *cRe = g->colRe + ((size_t)source * e->kyBlocks + kb) * sx;
    const v16 *cIm = g->colIm + ((size_t)source * e->kyBlocks + kb) * sx;
    const float *spectrum = e->spectra + ((size_t)kernelBatch * K + k) * sx * Rp + kb * LANES;
    v16 *aRe = w->bufRe[0], *aIm = w->bufIm[0];
    for (int x = 0; x < sx; ++x) {
        v16 scale = vload(spectrum + (size_t)x * Rp);
        aRe[x] = cRe[x] * scale;
        aIm[x] = cIm[x] * scale;
    }
    v16 *outRe, *outIm;
    fft(&e->planX, aRe, aIm, w->bufRe[1], w->bufIm[1], 1, &outRe, &outIm);
    int rows = R - kb * LANES < LANES ? R - kb * LANES : LANES;
    float *dRe = g->respRe + ((size_t)k * R + kb * LANES) * sx;
    float *dIm = g->respIm + ((size_t)k * R + kb * LANES) * sx;
    for (int x = 0; x < sx; ++x) {
        float lr[LANES], li[LANES];
        vstore(lr, outRe[x]);
        vstore(li, outIm[x]);
        for (int kl = 0; kl < rows; ++kl) {
            dRe[(size_t)kl * sx + x] = lr[kl];
            dIm[(size_t)kl * sx + x] = li[kl];
        }
    }
}

static void stage_growth(FLCPUEngine *e, Group *g, Worker *w, int item, int body, const float *mass) {
    const FLCPUConfig *c = &e->config;
    int sx = c->sx, sy = c->sy, R = e->reducedY, K = c->kernelCount, C = c->channelCount;
    int xb = item * LANES;
    int us = e->uStride;
    const float *params = e->params + (size_t)body * K * e->plane;
    for (int ch = 0; ch < C; ++ch) {
        for (int y = 0; y < sy; ++y) {
            vstore(g->u + ((size_t)ch * sy + y) * us + 1 + xb, vsplat(0.0f));
        }
    }
    v16 *aRe = w->bufRe[0], *aIm = w->bufIm[0];
    v16 zero = vsplat(0.0f);
    for (int k0 = 0; k0 < K; k0 += 2) {
        int hasPair = k0 + 1 < K;
        const float *r0 = g->respRe + (size_t)k0 * R * sx + xb;
        const float *i0 = g->respIm + (size_t)k0 * R * sx + xb;
        const float *r1 = r0 + (size_t)R * sx;
        const float *i1 = i0 + (size_t)R * sx;
        for (int j = 0; j < sy; ++j) {
            v16 h1r, h1i, h2r = zero, h2i = zero;
            if (j < R) {
                h1r = vload(r0 + (size_t)j * sx);
                h1i = vload(i0 + (size_t)j * sx);
                if (hasPair) {
                    h2r = vload(r1 + (size_t)j * sx);
                    h2i = vload(i1 + (size_t)j * sx);
                }
                if (j == 0 || j == sy / 2) {
                    h1i = zero;
                    h2i = zero;
                }
            } else {
                int jj = sy - j;
                h1r = vload(r0 + (size_t)jj * sx);
                h1i = -vload(i0 + (size_t)jj * sx);
                if (hasPair) {
                    h2r = vload(r1 + (size_t)jj * sx);
                    h2i = -vload(i1 + (size_t)jj * sx);
                }
            }
            aRe[j] = h1r - h2i;
            aIm[j] = h1i + h2r;
        }
        v16 *rowRe, *rowIm;
        fft(&e->planY, aRe, aIm, w->bufRe[1], w->bufIm[1], 1, &rowRe, &rowIm);
        v16 inverseScale = vsplat(c->inverseScale);
        int pairCount = hasPair ? 2 : 1;
        for (int y = 0; y < sy; ++y) {
            v16 zr = rowRe[y] * inverseScale;
            v16 zi = rowIm[y] * inverseScale;
            for (int kk = 0; kk < pairCount; ++kk) {
                int k = k0 + kk;
                v16 response = kk == 0 ? zr : zi;
                v16 localM = vsplat(e->m[(size_t)body * K + k]);
                v16 localS = vsplat(e->s[(size_t)body * K + k]);
                v16 localH = vload(params + (size_t)k * e->plane + y * sx + xb);
                v16 diff = (response - localM) / localS;
                v16 contribution = (vsplat(2.0f) * vexp_nonpositive(vsplat(-0.5f) * diff * diff) - vsplat(1.0f)) * localH;
                for (int ch = 0; ch < C; ++ch) {
                    float *up = g->u + ((size_t)ch * sy + y) * us + 1 + xb;
                    vstore(up, vload(up) + contribution * vsplat(e->outputWeights[ch * K + k]));
                }
            }
        }
    }
    const float *potential = e->potential ? e->potential + (size_t)body * e->plane : NULL;
    for (int y = 0; y < sy; ++y) {
        v16 total = zero;
        for (int ch = 0; ch < C; ++ch) {
            total = total + vload(mass + (size_t)ch * e->plane + y * sx + xb) * vsplat(e->matterWeights[ch]);
        }
        float *mp = g->matter + (size_t)y * us;
        vstore(mp + 1 + xb, total);
        if (xb == 0) {
            mp[1 + sx] = total[0];
        }
        if (xb == sx - LANES) {
            mp[0] = total[LANES - 1];
        }
        for (int ch = 0; ch < C; ++ch) {
            float *up = g->u + ((size_t)ch * sy + y) * us;
            v16 value = vload(up + 1 + xb);
            if (potential) {
                value = value + vload(potential + y * sx + xb);
                vstore(up + 1 + xb, value);
            }
            if (xb == 0) {
                up[1 + sx] = value[0];
            }
            if (xb == sx - LANES) {
                up[0] = value[LANES - 1];
            }
        }
    }
}

static inline v16 alpha_power(v16 base, int n) {
    switch (n) {
    case 0:
        return vsplat(1.0f);
    case 1:
        return base;
    case 2:
        return base * base;
    case 3:
        return base * base * base;
    default:
        return base * base * base * base;
    }
}

static void stage_flow(FLCPUEngine *e, Group *g, int y, const float *mass) {
    const FLCPUConfig *c = &e->config;
    int sx = c->sx, sy = c->sy, C = c->channelCount, dd = c->dd;
    int us = e->uStride, ts = e->tStride;
    const float *mRow[3];
    for (int o = 0; o < 3; ++o) {
        mRow[o] = g->matter + (size_t)wrap(y + o - 1, sy) * us;
    }
    v16 two = vsplat(2.0f), one = vsplat(1.0f), zero = vsplat(0.0f);
    v16 maxAdv = vsplat(c->maxAdvection), negMaxAdv = vsplat(-c->maxAdvection);
    v16 dt = vsplat(c->dt), thetaA = vsplat(c->thetaA);
    float *cellRow = g->cellMax + (size_t)y * ts + dd;
    for (int xb = 0; xb < sx; xb += LANES) {
        v16 g00 = vload(mRow[0] + xb), g10 = vload(mRow[0] + xb + 1), g20 = vload(mRow[0] + xb + 2);
        v16 g01 = vload(mRow[1] + xb), g11 = vload(mRow[1] + xb + 1), g21 = vload(mRow[1] + xb + 2);
        v16 g02 = vload(mRow[2] + xb), g12 = vload(mRow[2] + xb + 1), g22 = vload(mRow[2] + xb + 2);
        v16 gxA = (g20 + two * g21 + g22) - (g00 + two * g01 + g02);
        v16 gyA = (g02 + two * g12 + g22) - (g00 + two * g10 + g20);
        v16 cellMax = vsplat(-1.0f);
        for (int ch = 0; ch < C; ++ch) {
            const float *uBase = g->u + (size_t)ch * sy * us;
            const float *u0 = uBase + (size_t)wrap(y - 1, sy) * us + xb;
            const float *u1 = uBase + (size_t)y * us + xb;
            const float *u2 = uBase + (size_t)wrap(y + 1, sy) * us + xb;
            v16 u00 = vload(u0), u10 = vload(u0 + 1), u20 = vload(u0 + 2);
            v16 u01 = vload(u1), u21 = vload(u1 + 2);
            v16 u02 = vload(u2), u12 = vload(u2 + 1), u22 = vload(u2 + 2);
            v16 gxU = (u20 + two * u21 + u22) - (u00 + two * u01 + u02);
            v16 gyU = (u02 + two * u12 + u22) - (u00 + two * u10 + u20);
            v16 m = vload(mass + (size_t)ch * e->plane + y * sx + xb);
            v16 alphaSource = c->alphaPerChannel ? m : g11;
            v16 alpha = alpha_power(alphaSource / thetaA, c->n);
            alpha = vmin(vmax(alpha, zero), one);
            v16 flowY = gyU * (one - alpha) - gyA * alpha;
            v16 flowX = gxU * (one - alpha) - gxA * alpha;
            if (c->clipFlow) {
                flowY = vclamp(flowY, negMaxAdv, maxAdv);
                flowX = vclamp(flowX, negMaxAdv, maxAdv);
            }
            v16 clippedX = vclamp(flowX * dt, negMaxAdv, maxAdv);
            v16 clippedY = vclamp(flowY * dt, negMaxAdv, maxAdv);
            // An empty source sits far away with zero mass so it contributes exactly zero, as Metal stages it.
            vi16 occupied = m > zero;
            v16 far = vsplat(1.0e4f);
            size_t t = ((size_t)ch * sy + y) * ts + dd + xb;
            vstore(g->shX + t, vselect(occupied, clippedX, far));
            vstore(g->shY + t, vselect(occupied, clippedY, far));
            vstore(g->stM + t, vselect(occupied, m, zero));
            cellMax = vmax(cellMax, vselect(occupied, vmax(vabs(clippedX), vabs(clippedY)), vsplat(-1.0f)));
        }
        vstore(cellRow + xb, cellMax);
    }
    for (int ch = 0; ch <= C; ++ch) {
        float *rows[3];
        int fields = ch == C ? 1 : 3;
        if (ch == C) {
            rows[0] = cellRow;
        } else {
            size_t t = ((size_t)ch * sy + y) * ts + dd;
            rows[0] = g->shX + t;
            rows[1] = g->shY + t;
            rows[2] = g->stM + t;
        }
        for (int f = 0; f < fields; ++f) {
            float *row = rows[f];
            for (int i = 1; i <= dd; ++i) {
                row[-i] = row[sx - i];
                row[sx - 1 + i] = row[i - 1];
            }
        }
    }
    float *blockRow = g->blockMax + (size_t)y * e->xBlocks;
    for (int b = 0; b < e->xBlocks; ++b) {
        float best = -1.0f;
        for (int x = b * LANES - dd; x < b * LANES + LANES + dd; ++x) {
            best = cellRow[x] > best ? cellRow[x] : best;
        }
        blockRow[b] = best;
    }
}

static void stage_reintegrate(FLCPUEngine *e, Group *g, int y, float *next) {
    const FLCPUConfig *c = &e->config;
    int sx = c->sx, sy = c->sy, C = c->channelCount, dd = c->dd, ts = e->tStride;
    v16 zero = vsplat(0.0f), half = vsplat(0.5f), sigma = vsplat(c->sigma), clipMax = vsplat(c->clipMax);
    v16 areaScale = vsplat(c->areaScale);
    for (int b = 0; b < e->xBlocks; ++b) {
        int xb = b * LANES;
        float maxShift = -1.0f;
        for (int dy = -dd; dy <= dd; ++dy) {
            float v = g->blockMax[(size_t)wrap(y + dy, sy) * e->xBlocks + b];
            maxShift = v > maxShift ? v : maxShift;
        }
        if (maxShift < 0.0f) {
            for (int ch = 0; ch < C; ++ch) {
                vstore(next + (size_t)ch * e->plane + y * sx + xb, zero);
            }
            continue;
        }
        // The same reach as the Metal tiled kernel; every omitted term is an exact +0.
        int reach = (int)floorf(maxShift + 0.5f + c->sigma) + 1;
        reach = reach < dd ? reach : dd;
        for (int ch = 0; ch < C; ++ch) {
            v16 total = zero;
            const float *baseX = g->shX + (size_t)ch * sy * ts + dd + xb;
            const float *baseY = g->shY + (size_t)ch * sy * ts + dd + xb;
            const float *baseM = g->stM + (size_t)ch * sy * ts + dd + xb;
            for (int dx = -reach; dx <= reach; ++dx) {
                v16 fdx = vsplat((float)dx);
                for (int dy = -reach; dy <= reach; ++dy) {
                    size_t offset = (size_t)wrap(y - dy, sy) * ts - dx;
                    v16 dY = vabs(vsplat((float)dy) - vload(baseY + offset));
                    v16 dX = vabs(fdx - vload(baseX + offset));
                    v16 szY = vmin(vmax(half - dY + sigma, zero), clipMax);
                    v16 szX = vmin(vmax(half - dX + sigma, zero), clipMax);
                    total = total + vload(baseM + offset) * szY * szX;
                }
            }
            vstore(next + (size_t)ch * e->plane + y * sx + xb, total * areaScale);
        }
    }
}

static void step_body(FLCPUEngine *e, Worker *w, int body, int count) {
    Group *g = w->group;
    const FLCPUConfig *c = &e->config;
    int size = g->size, rank = w->rank;
    size_t bodyStride = (size_t)c->channelCount * e->plane;
    int pairs = (c->channelCount + 1) / 2;
    int spectrumItems = pairs * e->xBlocks;
    int columnItems = c->channelCount * e->kyBlocks;
    int responseItems = c->kernelCount * e->kyBlocks;
    int parity = e->current;
    for (int s = 0; s < count; ++s) {
        float *mass = e->mass[parity] + (size_t)body * bodyStride;
        float *next = e->mass[parity ^ 1] + (size_t)body * bodyStride;
        for (int i = rank; i < spectrumItems; i += size) {
            stage_spectrum(e, g, w, i, mass);
        }
        barrier_wait(&g->barrier, &w->sense);
        for (int i = rank; i < columnItems; i += size) {
            stage_columns(e, g, w, i);
        }
        barrier_wait(&g->barrier, &w->sense);
        for (int i = rank; i < responseItems; i += size) {
            stage_responses(e, g, w, i, body);
        }
        barrier_wait(&g->barrier, &w->sense);
        for (int i = rank; i < e->xBlocks; i += size) {
            stage_growth(e, g, w, i, body, mass);
        }
        barrier_wait(&g->barrier, &w->sense);
        if (s == count - 1) {
            for (int y = rank; y < c->sy; y += size) {
                for (int ch = 0; ch < c->channelCount; ++ch) {
                    memcpy(e->lastU + (size_t)body * bodyStride + (size_t)ch * e->plane + (size_t)y * c->sx,
                           g->u + ((size_t)ch * c->sy + y) * e->uStride + 1,
                           (size_t)c->sx * sizeof(float));
                }
            }
        }
        for (int y = rank; y < c->sy; y += size) {
            stage_flow(e, g, y, mass);
        }
        barrier_wait(&g->barrier, &w->sense);
        for (int y = rank; y < c->sy; y += size) {
            stage_reintegrate(e, g, y, next);
        }
        barrier_wait(&g->barrier, &w->sense);
        parity ^= 1;
    }
}

static void run_job(Worker *w) {
    FLCPUEngine *e = w->engine;
    Group *g = w->group;
    for (;;) {
        if (w->rank == 0) {
            g->body = atomic_fetch_add_explicit(&e->nextBody, 1, memory_order_relaxed);
        }
        barrier_wait(&g->barrier, &w->sense);
        int body = g->body;
        if (body >= e->config.batchCount) {
            return;
        }
        step_body(e, w, body, e->stepCount);
        barrier_wait(&g->barrier, &w->sense);
    }
}

static void *worker_main(void *arg) {
    Worker *w = arg;
    FLCPUEngine *e = w->engine;
    long seen = 0;
    for (;;) {
        pthread_mutex_lock(&e->mutex);
        while (e->generation == seen && !e->shutdown) {
            pthread_cond_wait(&e->startCondition, &e->mutex);
        }
        if (e->shutdown) {
            pthread_mutex_unlock(&e->mutex);
            return NULL;
        }
        seen = e->generation;
        pthread_mutex_unlock(&e->mutex);

        run_job(w);

        pthread_mutex_lock(&e->mutex);
        if (--e->pending == 0) {
            pthread_cond_signal(&e->doneCondition);
        }
        pthread_mutex_unlock(&e->mutex);
    }
}

int32_t flcpu_available_threads(void) {
#if defined(__linux__)
    cpu_set_t set;
    if (sched_getaffinity(0, sizeof set, &set) != 0) {
        abort();
    }
    return CPU_COUNT(&set);
#else
    return (int32_t)sysconf(_SC_NPROCESSORS_ONLN);
#endif
}

static void init_plan(FFTPlan *plan, int len, const float *twiddles, const int32_t *radices, int radixCount) {
    plan->len = len;
    plan->radixCount = radixCount;
    for (int i = 0; i < radixCount; ++i) {
        plan->radices[i] = radices[i];
    }
    plan->twRe = alloc_floats(len);
    plan->twIm = alloc_floats(len);
    for (int i = 0; i < len; ++i) {
        plan->twRe[i] = twiddles[2 * i];
        plan->twIm[i] = twiddles[2 * i + 1];
    }
}

FLCPUEngine *flcpu_create(const FLCPUConfig *config) {
    FLCPUEngine *e = calloc(1, sizeof *e);
    if (!e) {
        abort();
    }
    e->config = *config;
    e->config.twiddleX = NULL;
    e->config.twiddleY = NULL;
    e->config.radicesX = NULL;
    e->config.radicesY = NULL;
    const FLCPUConfig *c = &e->config;
    int sx = c->sx, sy = c->sy, C = c->channelCount, K = c->kernelCount, B = c->batchCount;
    e->plane = sx * sy;
    e->reducedY = sy / 2 + 1;
    e->paddedY = round_up16(e->reducedY);
    e->kyBlocks = e->paddedY / LANES;
    e->xBlocks = sx / LANES;
    e->uStride = round_up16(sx + 2);
    e->tStride = round_up16(sx + 2 * c->dd);
    init_plan(&e->planX, sx, config->twiddleX, config->radicesX, config->radixCountX);
    init_plan(&e->planY, sy, config->twiddleY, config->radicesY, config->radixCountY);

    e->mass[0] = alloc_floats((size_t)B * C * e->plane);
    e->mass[1] = alloc_floats((size_t)B * C * e->plane);
    e->params = alloc_floats((size_t)B * K * e->plane);
    e->lastU = alloc_floats((size_t)B * C * e->plane);
    e->spectra = alloc_floats((size_t)c->kernelBatchCount * K * sx * e->paddedY);
    e->c0 = calloc((size_t)K, sizeof(int32_t));
    e->m = alloc_floats((size_t)B * K);
    e->s = alloc_floats((size_t)B * K);
    e->outputWeights = alloc_floats((size_t)C * K);
    e->matterWeights = alloc_floats((size_t)C);
    for (int ch = 0; ch < C; ++ch) {
        e->matterWeights[ch] = 1.0f;
    }

    int threads = c->threadCount;
    e->groupCount = threads < B ? threads : B;
    e->groupSize = threads / e->groupCount;
    // Measured on 128 and 256 grids: past four ranks the per-stage barriers cost more than the
    // split work saves, so leftover threads stay idle rather than spin.
    if (e->groupSize > 4) {
        e->groupSize = 4;
    }
    e->workerCount = e->groupCount * e->groupSize;
    e->groups = calloc((size_t)e->groupCount, sizeof(Group));
    e->workers = calloc((size_t)e->workerCount, sizeof(Worker));
    int fftLen = sx > sy ? sx : sy;
    for (int gi = 0; gi < e->groupCount; ++gi) {
        Group *g = &e->groups[gi];
        g->size = e->groupSize;
        g->barrier.size = e->groupSize;
        atomic_init(&g->barrier.count, 0);
        atomic_init(&g->barrier.sense, 0);
        g->sRe = alloc_floats((size_t)C * sx * e->paddedY);
        g->sIm = alloc_floats((size_t)C * sx * e->paddedY);
        g->colRe = alloc_floats((size_t)C * e->kyBlocks * sx * LANES);
        g->colIm = alloc_floats((size_t)C * e->kyBlocks * sx * LANES);
        g->respRe = alloc_floats((size_t)K * e->reducedY * sx);
        g->respIm = alloc_floats((size_t)K * e->reducedY * sx);
        g->u = alloc_floats((size_t)C * sy * e->uStride);
        g->matter = alloc_floats((size_t)sy * e->uStride);
        g->shX = alloc_floats((size_t)C * sy * e->tStride);
        g->shY = alloc_floats((size_t)C * sy * e->tStride);
        g->stM = alloc_floats((size_t)C * sy * e->tStride);
        g->cellMax = alloc_floats((size_t)sy * e->tStride);
        g->blockMax = alloc_floats((size_t)sy * e->xBlocks);
    }
    pthread_mutex_init(&e->mutex, NULL);
    pthread_cond_init(&e->startCondition, NULL);
    pthread_cond_init(&e->doneCondition, NULL);
    for (int i = 0; i < e->workerCount; ++i) {
        Worker *w = &e->workers[i];
        w->engine = e;
        w->group = &e->groups[i / e->groupSize];
        w->rank = i % e->groupSize;
        for (int b = 0; b < 2; ++b) {
            w->bufRe[b] = alloc_floats((size_t)fftLen * LANES);
            w->bufIm[b] = alloc_floats((size_t)fftLen * LANES);
        }
        if (pthread_create(&w->thread, NULL, worker_main, w) != 0) {
            abort();
        }
    }
    return e;
}

void flcpu_destroy(FLCPUEngine *e) {
    pthread_mutex_lock(&e->mutex);
    e->shutdown = 1;
    pthread_cond_broadcast(&e->startCondition);
    pthread_mutex_unlock(&e->mutex);
    for (int i = 0; i < e->workerCount; ++i) {
        Worker *w = &e->workers[i];
        pthread_join(w->thread, NULL);
        for (int b = 0; b < 2; ++b) {
            free(w->bufRe[b]);
            free(w->bufIm[b]);
        }
    }
    for (int gi = 0; gi < e->groupCount; ++gi) {
        Group *g = &e->groups[gi];
        free(g->sRe);
        free(g->sIm);
        free(g->colRe);
        free(g->colIm);
        free(g->respRe);
        free(g->respIm);
        free(g->u);
        free(g->matter);
        free(g->shX);
        free(g->shY);
        free(g->stM);
        free(g->cellMax);
        free(g->blockMax);
    }
    pthread_mutex_destroy(&e->mutex);
    pthread_cond_destroy(&e->startCondition);
    pthread_cond_destroy(&e->doneCondition);
    free(e->groups);
    free(e->workers);
    free(e->planX.twRe);
    free(e->planX.twIm);
    free(e->planY.twRe);
    free(e->planY.twIm);
    free(e->mass[0]);
    free(e->mass[1]);
    free(e->params);
    free(e->lastU);
    free(e->spectra);
    free(e->c0);
    free(e->m);
    free(e->s);
    free(e->outputWeights);
    free(e->matterWeights);
    free(e->potential);
    free(e);
}

void flcpu_set_kernels(
    FLCPUEngine *e,
    const float *spectra,
    const int32_t *c0Idxs,
    const float *m,
    const float *s,
    const float *outputWeights
) {
    const FLCPUConfig *c = &e->config;
    int sx = c->sx, R = e->reducedY, Rp = e->paddedY, K = c->kernelCount;
    for (int kb = 0; kb < c->kernelBatchCount; ++kb) {
        for (int k = 0; k < K; ++k) {
            float *dst = e->spectra + ((size_t)kb * K + k) * sx * Rp;
            for (int x = 0; x < sx; ++x) {
                for (int ky = 0; ky < R; ++ky) {
                    dst[(size_t)x * Rp + ky] = spectra[(((size_t)kb * R + ky) * K + k) * sx + x];
                }
            }
        }
    }
    memcpy(e->c0, c0Idxs, sizeof(int32_t) * K);
    memcpy(e->m, m, sizeof(float) * c->batchCount * K);
    memcpy(e->s, s, sizeof(float) * c->batchCount * K);
    memcpy(e->outputWeights, outputWeights, sizeof(float) * c->channelCount * K);
}

void flcpu_set_matter_weights(FLCPUEngine *e, const float *weights) {
    memcpy(e->matterWeights, weights, sizeof(float) * e->config.channelCount);
}

void flcpu_set_potential(FLCPUEngine *e, const float *potential) {
    const FLCPUConfig *c = &e->config;
    free(e->potential);
    e->potential = NULL;
    if (!potential) {
        return;
    }
    e->potential = alloc_floats((size_t)c->batchCount * e->plane);
    for (int b = 0; b < c->batchCount; ++b) {
        for (int x = 0; x < c->sx; ++x) {
            for (int y = 0; y < c->sy; ++y) {
                e->potential[(size_t)b * e->plane + y * c->sx + x] = potential[((size_t)b * c->sx + x) * c->sy + y];
            }
        }
    }
}

// Interleaved [batch][sx][sy][fields] <-> planar [batch][fields][sy][sx].
static void to_planar(const FLCPUEngine *e, const float *src, float *dst, int fields) {
    const FLCPUConfig *c = &e->config;
    for (int b = 0; b < c->batchCount; ++b) {
        for (int x = 0; x < c->sx; ++x) {
            for (int y = 0; y < c->sy; ++y) {
                const float *cell = src + (((size_t)b * c->sx + x) * c->sy + y) * fields;
                for (int f = 0; f < fields; ++f) {
                    dst[((size_t)b * fields + f) * e->plane + y * c->sx + x] = cell[f];
                }
            }
        }
    }
}

static void from_planar(const FLCPUEngine *e, const float *src, float *dst, int fields) {
    const FLCPUConfig *c = &e->config;
    for (int b = 0; b < c->batchCount; ++b) {
        for (int x = 0; x < c->sx; ++x) {
            for (int y = 0; y < c->sy; ++y) {
                float *cell = dst + (((size_t)b * c->sx + x) * c->sy + y) * fields;
                for (int f = 0; f < fields; ++f) {
                    cell[f] = src[((size_t)b * fields + f) * e->plane + y * c->sx + x];
                }
            }
        }
    }
}

void flcpu_set_state(FLCPUEngine *e, const float *mass, const float *params) {
    e->current = 0;
    to_planar(e, mass, e->mass[0], e->config.channelCount);
    to_planar(e, params, e->params, e->config.kernelCount);
}

void flcpu_get_mass(const FLCPUEngine *e, float *mass) {
    from_planar(e, e->mass[e->current], mass, e->config.channelCount);
}

void flcpu_get_params(const FLCPUEngine *e, float *params) {
    from_planar(e, e->params, params, e->config.kernelCount);
}

void flcpu_get_last_potential(const FLCPUEngine *e, float *potential) {
    from_planar(e, e->lastU, potential, e->config.channelCount);
}

void flcpu_mass_map(const FLCPUEngine *e, const float *channelWeights, float *out) {
    const FLCPUConfig *c = &e->config;
    const float *mass = e->mass[e->current];
    for (int b = 0; b < c->batchCount; ++b) {
        for (int x = 0; x < c->sx; ++x) {
            for (int y = 0; y < c->sy; ++y) {
                float value = 0.0f;
                for (int ch = 0; ch < c->channelCount; ++ch) {
                    value += mass[((size_t)b * c->channelCount + ch) * e->plane + y * c->sx + x] * channelWeights[ch];
                }
                out[((size_t)b * c->sx + x) * c->sy + y] = value;
            }
        }
    }
}

// Sums run in double; Metal reduces the same per-cell float terms in a float tree.
void flcpu_summarize(
    const FLCPUEngine *e,
    float occupancyThreshold,
    const float *channelWeights,
    int32_t includeGyration,
    FLCPUMassSummary *out
) {
    const FLCPUConfig *c = &e->config;
    const float *mass = e->mass[e->current];
    int sx = c->sx, sy = c->sy, C = c->channelCount;
    for (int b = 0; b < c->batchCount; ++b) {
        const float *body = mass + (size_t)b * C * e->plane;
        double total = 0, sumSq = 0, energy = 0, wx = 0, wy = 0, occupancy = 0;
        for (int x = 0; x < sx; ++x) {
            for (int y = 0; y < sy; ++y) {
                float value = 0.0f;
                for (int ch = 0; ch < C; ++ch) {
                    float cm = body[(size_t)ch * e->plane + y * sx + x];
                    value += cm * channelWeights[ch];
                    energy += cm * cm * channelWeights[ch];
                }
                total += value;
                sumSq += value * value;
                wx += value * (float)x;
                wy += value * (float)y;
                occupancy += value > occupancyThreshold ? 1.0 : 0.0;
            }
        }
        FLCPUMassSummary *summary = &out[b];
        summary->totalMass = (float)total;
        summary->sumSquares = (float)sumSq;
        summary->energy = (float)energy;
        summary->weightedX = (float)wx;
        summary->weightedY = (float)wy;
        summary->occupancyCount = (float)occupancy;
        summary->rawGyration = 0.0f;
        if (!includeGyration) {
            continue;
        }
        float clampedTotal = summary->totalMass > 1.0e-6f ? summary->totalMass : 1.0e-6f;
        float cx = summary->weightedX / clampedTotal;
        float cy = summary->weightedY / clampedTotal;
        double gyration = 0;
        for (int x = 0; x < sx; ++x) {
            for (int y = 0; y < sy; ++y) {
                float value = 0.0f;
                for (int ch = 0; ch < C; ++ch) {
                    value += body[(size_t)ch * e->plane + y * sx + x] * channelWeights[ch];
                }
                float dx = fabsf((float)x - cx);
                float dy = fabsf((float)y - cy);
                dx = fminf(dx, (float)sx - dx);
                dy = fminf(dy, (float)sy - dy);
                gyration += value * (dx * dx + dy * dy);
            }
        }
        summary->rawGyration = (float)gyration / clampedTotal;
    }
}

void flcpu_zero_state_patch(FLCPUEngine *e, const int32_t *origins, int32_t size) {
    const FLCPUConfig *c = &e->config;
    float *mass = e->mass[e->current];
    for (int b = 0; b < c->batchCount; ++b) {
        int x0 = origins[2 * b], y0 = origins[2 * b + 1];
        if (x0 < 0 || y0 < 0) {
            continue;
        }
        for (int lx = 0; lx < size; ++lx) {
            for (int ly = 0; ly < size; ++ly) {
                int x = x0 + lx, y = y0 + ly;
                if (x >= c->sx || y >= c->sy) {
                    continue;
                }
                for (int ch = 0; ch < c->channelCount; ++ch) {
                    mass[((size_t)b * c->channelCount + ch) * e->plane + y * c->sx + x] = 0.0f;
                }
                for (int k = 0; k < c->kernelCount; ++k) {
                    e->params[((size_t)b * c->kernelCount + k) * e->plane + y * c->sx + x] = 0.0f;
                }
            }
        }
    }
}

void flcpu_parameter_patch(
    FLCPUEngine *e,
    const int32_t *origins,
    int32_t size,
    const float *deltas,
    int32_t applyClip,
    float clipLow,
    float clipHigh
) {
    const FLCPUConfig *c = &e->config;
    int K = c->kernelCount;
    for (int b = 0; b < c->batchCount; ++b) {
        int x0 = origins[2 * b], y0 = origins[2 * b + 1];
        for (int lx = 0; lx < size; ++lx) {
            for (int ly = 0; ly < size; ++ly) {
                int x = x0 + lx, y = y0 + ly;
                if (x < 0 || x >= c->sx || y < 0 || y >= c->sy) {
                    continue;
                }
                const float *delta = deltas + (((size_t)b * size + lx) * size + ly) * K;
                for (int k = 0; k < K; ++k) {
                    float *p = &e->params[((size_t)b * K + k) * e->plane + y * c->sx + x];
                    float value = *p + delta[k];
                    if (applyClip) {
                        value = fminf(fmaxf(value, clipLow), clipHigh);
                    }
                    *p = value;
                }
            }
        }
    }
}

void flcpu_step(FLCPUEngine *e, int32_t count) {
    if (count <= 0) {
        return;
    }
    pthread_mutex_lock(&e->mutex);
    e->stepCount = count;
    atomic_store_explicit(&e->nextBody, 0, memory_order_relaxed);
    e->pending = e->workerCount;
    e->generation += 1;
    pthread_cond_broadcast(&e->startCondition);
    while (e->pending > 0) {
        pthread_cond_wait(&e->doneCondition, &e->mutex);
    }
    pthread_mutex_unlock(&e->mutex);
    e->current ^= count & 1;
}
