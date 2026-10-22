import Foundation

/// Threadgroup FFT layout for the fused convolution and growth stage.
///
/// The stage runs in three passes so that no full-size complex intermediate other than the
/// channel spectra and the per-kernel responses touches device memory:
/// 1. `flowMetalSpectrumRows`: one threadgroup per (batch, x) row packs two real channels into
///    one complex FFT along y and keeps the ky <= sy / 2 half spectrum.
/// 2. `flowMetalResponseColumns`: one threadgroup per (batch, ky) column transforms every
///    channel along x, multiplies by each kernel spectrum and transforms back along x.
/// 3. `flowMetalGrowthRows`: `rowBlock` rows per threadgroup pack two kernel responses into
///    one inverse complex FFT along y and reduce them straight into growth and matter.
/// The inverse matches numpy `irfft2`: imaginary parts at ky = 0 and the even-length Nyquist
/// bin are dropped after the x inverse.
struct FlowLeniaSpectralPlan {
    static let radixOrder = [4, 2, 3, 5, 7]

    let sx: Int
    let sy: Int
    let radicesX: [Int]
    let radicesY: [Int]
    let threadsX: Int
    let threadsY: Int
    let rowBlock: Int

    init(sx: Int, sy: Int, channelCount: Int, maxThreadgroupMemory: Int) {
        guard let radicesX = Self.radices(sx), let radicesY = Self.radices(sy) else {
            preconditionFailure("Flow Metal FFT needs grid sides whose prime factors are 2, 3, 5 and 7, got \(sx) x \(sy).")
        }
        self.sx = sx
        self.sy = sy
        self.radicesX = radicesX
        self.radicesY = radicesY
        // One butterfly of the smallest radix per thread, so every stage needs at most one pass over its butterflies per thread.
        let threadsY = sy / radicesY.min()!
        self.threadsX = sx / radicesX.min()!
        self.threadsY = threadsY
        let complexBytes = MemoryLayout<SIMD2<Float>>.stride
        let columnBytes = (channelCount + 2) * sx * complexBytes
        guard 2 * sy * complexBytes <= maxThreadgroupMemory, columnBytes <= maxThreadgroupMemory else {
            preconditionFailure("Flow Metal FFT for \(sx) x \(sy) with \(channelCount) channels exceeds \(maxThreadgroupMemory) bytes of threadgroup memory.")
        }
        // Several rows per growth threadgroup make the strided response reads coalesce across x; 16 KB keeps two threadgroups resident.
        self.rowBlock = [4, 2, 1].first { block in
            sx % block == 0 && block * threadsY <= 1024 && 2 * block * sy * complexBytes <= min(16_384, maxThreadgroupMemory)
        } ?? 1
    }

    static func radices(_ length: Int) -> [Int]? {
        guard length >= 2 else {
            return nil
        }
        var remaining = length
        var radices: [Int] = []
        for radix in radixOrder {
            while remaining % radix == 0 {
                radices.append(radix)
                remaining /= radix
            }
        }
        return remaining == 1 ? radices : nil
    }

    /// exp(-2 pi i m / length) for m < length, computed in double.
    static func twiddles(length: Int) -> [Float] {
        (0..<length).flatMap { m -> [Float] in
            let angle = -2.0 * Double.pi * Double(m) / Double(length)
            return [Float(cos(angle)), Float(sin(angle))]
        }
    }

    func validate(spectrumRows: Int, responseColumns: Int, growthRows: Int) {
        guard threadsY <= spectrumRows, threadsX <= responseColumns, rowBlock * threadsY <= growthRows else {
            preconditionFailure("Flow Metal FFT for \(sx) x \(sy) needs \(threadsY), \(threadsX) and \(rowBlock * threadsY) threads per threadgroup; the pipelines allow \(spectrumRows), \(responseColumns) and \(growthRows).")
        }
    }

    private static func fftFunction(name: String, length: Int, radices: [Int], threads: String) -> String {
        var stride = 1
        var stages = ""
        for radix in radices {
            stages += """
                fftStage<\(radix)>(a, b, tw, t, \(threads), \(length), \(stride), inverse);
                threadgroup_barrier(mem_flags::mem_threadgroup);
                { threadgroup float2 *swap = a; a = b; b = swap; }

            """
            stride *= radix
        }
        return """
        inline threadgroup float2 *\(name)(threadgroup float2 *a, threadgroup float2 *b, device const float2 *tw, int t, bool inverse) {
        \(stages)    return a;
        }
        """
    }

    private static func rootTable(_ radix: Int) -> String {
        let roots = twiddles(length: radix)
        let values = (0..<radix).map { "float2(\(roots[2 * $0])f, \(roots[2 * $0 + 1])f)" }
        return "constant float2 kRoot\(radix)[\(radix)] = {\(values.joined(separator: ", "))};"
    }

    /// Kernels for the three passes. They rely on the index helpers and constants of the full
    /// pipeline source (kSX, kSY, kReducedY, kChannelCount, kKernelCount, kKernelBatchCount,
    /// kUsesLocalizedGrowthParameters, massIndex, paramIndex, spectrumIndex, uIndex, scalarIndex).
    func source() -> String {
        let inverseScale = Float(1.0 / (Double(sx) * Double(sy)))
        return """
        constant int kThreadsX = \(threadsX);
        constant int kThreadsY = \(threadsY);
        constant int kRowValues = kSY / kThreadsY;
        constant int kRowBlock = \(rowBlock);
        constant float kInverseScale = \(inverseScale)f;
        \(Self.rootTable(3))
        \(Self.rootTable(5))
        \(Self.rootTable(7))

        inline float2 complexMultiply(float2 a, float2 b) {
            return float2(a.x * b.x - a.y * b.y, a.x * b.y + a.y * b.x);
        }

        inline float2 conjugateIf(float2 w, bool inverse) {
            return inverse ? float2(w.x, -w.y) : w;
        }

        template <int P>
        inline float2 smallRoot(int m) {
            return P == 3 ? kRoot3[m] : (P == 5 ? kRoot5[m] : kRoot7[m]);
        }

        template <int P>
        inline void butterfly(thread float2 *v, bool inverse) {
            if (P == 2) {
                float2 a = v[0];
                float2 b = v[1];
                v[0] = a + b;
                v[1] = a - b;
            } else if (P == 4) {
                float2 s02 = v[0] + v[2];
                float2 d02 = v[0] - v[2];
                float2 s13 = v[1] + v[3];
                float2 d13 = v[1] - v[3];
                float2 rotated = inverse ? float2(-d13.y, d13.x) : float2(d13.y, -d13.x);
                v[0] = s02 + s13;
                v[2] = s02 - s13;
                v[1] = d02 + rotated;
                v[3] = d02 - rotated;
            } else {
                float2 out[P];
                for (int s = 0; s < P; ++s) {
                    float2 acc = v[0];
                    for (int r = 1; r < P; ++r) {
                        acc += complexMultiply(v[r], conjugateIf(smallRoot<P>((r * s) % P), inverse));
                    }
                    out[s] = acc;
                }
                for (int s = 0; s < P; ++s) {
                    v[s] = out[s];
                }
            }
        }

        // Stockham autosort stage over `stride` already-combined points: natural-order input stays natural-order after the last stage.
        template <int P>
        inline void fftStage(threadgroup const float2 *a, threadgroup float2 *b, device const float2 *tw, int t, int threads, int length, int stride, bool inverse) {
            int butterflies = length / P;
            int twiddleStep = length / (stride * P);
            for (int j = t; j < butterflies; j += threads) {
                int k = j % stride;
                float2 v[P];
                for (int r = 0; r < P; ++r) {
                    v[r] = a[j + r * butterflies];
                }
                for (int r = 1; r < P; ++r) {
                    v[r] = complexMultiply(v[r], conjugateIf(tw[r * k * twiddleStep], inverse));
                }
                butterfly<P>(v, inverse);
                int out = (j - k) * P + k;
                for (int r = 0; r < P; ++r) {
                    b[out + r * stride] = v[r];
                }
            }
        }

        \(Self.fftFunction(name: "fftX", length: sx, radices: radicesX, threads: "kThreadsX"))

        \(Self.fftFunction(name: "fftY", length: sy, radices: radicesY, threads: "kThreadsY"))

        inline int responseIndex(int batch, int k, int ky, int x) {
            return ((batch * kKernelCount + k) * kReducedY + ky) * kSX + x;
        }

        inline int transposedKernelIndex(int kernelBatch, int ky, int k, int x) {
            return ((kernelBatch * kReducedY + ky) * kKernelCount + k) * kSX + x;
        }

        kernel void flowMetalSpectrumRows(
            device const float *mass [[buffer(0)]],
            device const float2 *twiddleY [[buffer(1)]],
            device float2 *channelSpectra [[buffer(2)]],
            uint tid [[thread_index_in_threadgroup]],
            uint2 group [[threadgroup_position_in_grid]]
        ) {
            threadgroup float2 bufferA[kSY];
            threadgroup float2 bufferB[kSY];
            int t = int(tid);
            int x = int(group.x);
            int batch = int(group.y);
            for (int c0 = 0; c0 < kChannelCount; c0 += 2) {
                bool pair = c0 + 1 < kChannelCount;
                for (int y = t; y < kSY; y += kThreadsY) {
                    int index = massIndex(batch, x, y, c0);
                    bufferA[y] = float2(mass[index], pair ? mass[index + 1] : 0.0f);
                }
                threadgroup_barrier(mem_flags::mem_threadgroup);
                threadgroup float2 *row = fftY(bufferA, bufferB, twiddleY, t, false);
                for (int ky = t; ky < kReducedY; ky += kThreadsY) {
                    float2 z = row[ky];
                    if (pair) {
                        // Split the packed transform: X0 = (Z[k] + conj Z[-k]) / 2, X1 = (Z[k] - conj Z[-k]) / 2i.
                        float2 mirror = row[ky == 0 ? 0 : kSY - ky];
                        mirror.y = -mirror.y;
                        float2 d = 0.5f * (z - mirror);
                        channelSpectra[spectrumIndex(batch, x, ky, c0)] = 0.5f * (z + mirror);
                        channelSpectra[spectrumIndex(batch, x, ky, c0 + 1)] = float2(d.y, -d.x);
                    } else {
                        channelSpectra[spectrumIndex(batch, x, ky, c0)] = z;
                    }
                }
                threadgroup_barrier(mem_flags::mem_threadgroup);
            }
        }

        kernel void flowMetalResponseColumns(
            device const float2 *channelSpectra [[buffer(0)]],
            device const float2 *kernelSpectra [[buffer(1)]],
            device const int *c0Idxs [[buffer(2)]],
            device const float2 *twiddleX [[buffer(3)]],
            device float2 *responses [[buffer(4)]],
            uint tid [[thread_index_in_threadgroup]],
            uint2 group [[threadgroup_position_in_grid]]
        ) {
            threadgroup float2 columns[kChannelCount][kSX];
            threadgroup float2 bufferA[kSX];
            threadgroup float2 bufferB[kSX];
            int t = int(tid);
            int ky = int(group.x);
            int batch = int(group.y);
            int kernelBatch = kKernelBatchCount == 1 ? 0 : batch;
            for (int c = 0; c < kChannelCount; ++c) {
                for (int x = t; x < kSX; x += kThreadsX) {
                    bufferA[x] = channelSpectra[spectrumIndex(batch, x, ky, c)];
                }
                threadgroup_barrier(mem_flags::mem_threadgroup);
                threadgroup float2 *column = fftX(bufferA, bufferB, twiddleX, t, false);
                for (int x = t; x < kSX; x += kThreadsX) {
                    columns[c][x] = column[x];
                }
                threadgroup_barrier(mem_flags::mem_threadgroup);
            }
            for (int k = 0; k < kKernelCount; ++k) {
                int source = c0Idxs[k];
                int kernelBase = transposedKernelIndex(kernelBatch, ky, k, 0);
                for (int x = t; x < kSX; x += kThreadsX) {
                    bufferA[x] = complexMultiply(columns[source][x], kernelSpectra[kernelBase + x]);
                }
                threadgroup_barrier(mem_flags::mem_threadgroup);
                threadgroup float2 *column = fftX(bufferA, bufferB, twiddleX, t, true);
                int responseBase = responseIndex(batch, k, ky, 0);
                for (int x = t; x < kSX; x += kThreadsX) {
                    responses[responseBase + x] = column[x];
                }
                threadgroup_barrier(mem_flags::mem_threadgroup);
            }
        }

        kernel void flowMetalGrowthRows(
            device const float2 *responses [[buffer(0)]],
            device const float *params [[buffer(1)]],
            device const float *m [[buffer(2)]],
            device const float *s [[buffer(3)]],
            device const float *outputWeights [[buffer(4)]],
            device float *u [[buffer(5)]],
            device const float *mass [[buffer(6)]],
            device const float *matterWeights [[buffer(7)]],
            device float *matter [[buffer(8)]],
            device const float2 *twiddleY [[buffer(9)]],
            uint tid [[thread_index_in_threadgroup]],
            uint2 group [[threadgroup_position_in_grid]]
        ) {
            threadgroup float2 bufferA[kRowBlock][kSY];
            threadgroup float2 bufferB[kRowBlock][kSY];
            // Adjacent threads take adjacent rows so the x-contiguous response reads coalesce.
            int localRow = int(tid) % kRowBlock;
            int t = int(tid) / kRowBlock;
            int x = int(group.x) * kRowBlock + localRow;
            int batch = int(group.y);
            float sums[kRowValues][kChannelCount];
            for (int i = 0; i < kRowValues; ++i) {
                for (int c = 0; c < kChannelCount; ++c) {
                    sums[i][c] = 0.0f;
                }
            }
            for (int k0 = 0; k0 < kKernelCount; k0 += 2) {
                bool pair = k0 + 1 < kKernelCount;
                int firstBase = responseIndex(batch, k0, 0, x);
                int secondBase = firstBase + kReducedY * kSX;
                for (int j = t; j < kSY; j += kThreadsY) {
                    // Hermitian extension of two real rows, packed as h1 + i h2 so one inverse transform yields both.
                    float2 h1;
                    float2 h2 = float2(0.0f);
                    if (j < kReducedY) {
                        h1 = responses[firstBase + j * kSX];
                        if (pair) {
                            h2 = responses[secondBase + j * kSX];
                        }
                        if (j == 0 || (kSY % 2 == 0 && j == kSY / 2)) {
                            h1.y = 0.0f;
                            h2.y = 0.0f;
                        }
                    } else {
                        h1 = responses[firstBase + (kSY - j) * kSX];
                        h1.y = -h1.y;
                        if (pair) {
                            h2 = responses[secondBase + (kSY - j) * kSX];
                            h2.y = -h2.y;
                        }
                    }
                    bufferA[localRow][j] = float2(h1.x - h2.y, h1.y + h2.x);
                }
                threadgroup_barrier(mem_flags::mem_threadgroup);
                threadgroup float2 *row = fftY(bufferA[localRow], bufferB[localRow], twiddleY, t, true);
                for (int i = 0; i < kRowValues; ++i) {
                    int y = t + i * kThreadsY;
                    float2 z = row[y] * kInverseScale;
                    int paramBase = paramIndex(batch, x, y, 0);
                    for (int kk = 0; kk < (pair ? 2 : 1); ++kk) {
                        int k = k0 + kk;
                        int kernelIndex = batch * kKernelCount + k;
                        float response = kk == 0 ? z.x : z.y;
                        float localM = kUsesLocalizedGrowthParameters ? params[paramBase + k] : m[kernelIndex];
                        float localS = kUsesLocalizedGrowthParameters ? params[paramBase + kKernelCount + k] : s[kernelIndex];
                        float localH = kUsesLocalizedGrowthParameters ? params[paramBase + 2 * kKernelCount + k] : params[paramBase + k];
                        float diff = (response - localM) / localS;
                        float contribution = (2.0f * metal::exp(-0.5f * diff * diff) - 1.0f) * localH;
                        for (int c = 0; c < kChannelCount; ++c) {
                            sums[i][c] += contribution * outputWeights[c * kKernelCount + k];
                        }
                    }
                }
                threadgroup_barrier(mem_flags::mem_threadgroup);
            }
            for (int i = 0; i < kRowValues; ++i) {
                int y = t + i * kThreadsY;
                int outputBase = uIndex(batch, x, y, 0);
                for (int c = 0; c < kChannelCount; ++c) {
                    u[outputBase + c] = sums[i][c];
                }
                int massBase = massIndex(batch, x, y, 0);
                float total = 0.0f;
                for (int c = 0; c < kChannelCount; ++c) {
                    total += mass[massBase + c] * matterWeights[c];
                }
                matter[scalarIndex(batch, x, y)] = total;
            }
        }
        """
    }
}
