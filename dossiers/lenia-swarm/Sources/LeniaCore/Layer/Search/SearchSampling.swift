import Foundation

/// Box-Muller normal sample scaled by `std`. The `u1` floor avoids `log(0)`.
/// This is the single source for Gaussian draws across the search and paper
/// runners; with `std == 1` it matches the standard-normal draw used by the
/// OpenES antithetic sampler.
func gaussianSample(std: Float = 1, rng: inout SeededRandomNumberGenerator) -> Float {
    let u1 = max(Float.random(in: 0..<1, using: &rng), 1e-7)
    let u2 = Float.random(in: 0..<1, using: &rng)
    return sqrt(-2.0 * log(u1)) * cos(2.0 * Float.pi * u2) * std
}
