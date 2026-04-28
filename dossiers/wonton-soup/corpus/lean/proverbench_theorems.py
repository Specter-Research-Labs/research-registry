# ruff: noqa: E501
"""
DeepSeek-ProverBench theorems validated against Lean REPL.

Generated from 94 valid theorems (out of 325 total).
Only theorems that successfully typecheck in Lean 4 / Mathlib are included.
"""
from corpus.lean.theorems import Theorem

PROVERBENCH_CORPUS: list[Theorem] = [
    Theorem("pb_000_aime_2024i_p2", """set_option maxHeartbeats 0
open BigOperators Real Nat Topology Rat

theorem {name} (x y : ℝ) (hx : 1 < x) (hy : 1 < y)
    (h₁ : Real.logb x (y ^ x) = 10) (h₂ : Real.logb y (x ^ (4 * y)) = 10) :
    x * y = 25 := by
  sorry"""),
    Theorem("pb_001_aime_2024ii_p4", """set_option maxHeartbeats 0
open BigOperators Real Nat Topology Rat

theorem {name} (ans : ℚ) (x y z : ℝ)
    (hx : 0 < x) (hy : 0 < y) (hz : 0 < z)
    (h₀ : Real.logb 2 (x / (y * z)) = (1 : ℝ) / 2)
    (h₁ : Real.logb 2 (y / (x * z)) = (1 : ℝ) / 3)
    (h₂ : Real.logb 2 (z / (x * y)) = (1 : ℝ) / 4)
    (answer : ans = |Real.logb 2 (x ^ 4 * y ^ 3 * z ^ 2)|) :
    ↑ans.den + ans.num = 33 := by
  sorry"""),
    Theorem("pb_002_aime_2024ii_p13", """set_option maxHeartbeats 0
open BigOperators Real Nat Topology Rat

theorem {name} (ω : ℂ) (h₀ : ω = Complex.exp (2 * ↑Real.pi * Complex.I / 13)) :
    (∏ k ∈ Finset.range 13, (2 - 2 * ω ^ k + ω ^ (2 * k))) % 1000 = 321 := by
  sorry"""),
    Theorem("pb_003_aime_2025i_p1", """set_option maxHeartbeats 0
open BigOperators Real Nat Topology Rat

theorem {name} (S : Finset ℕ)
    (h₀ : ∀ (b : ℕ), b ∈ S ↔ b > 9 ∧ b + 7 ∣ 9 * b + 7) :
    (∑ b ∈ S, b) = 70 := by
  sorry"""),
    Theorem("pb_004_aime_2025i_p9", """set_option maxHeartbeats 0
open BigOperators Real Nat Topology Rat

theorem {name} (x y x' y' : ℝ) (hx : 0 < x) (hy : y < 0)
    (hx' : x' = x * Real.cos (Real.pi / 3) + y * Real.sin (Real.pi / 3))
    (hy' : y' = - x * Real.sin (Real.pi / 3) + y * Real.cos (Real.pi / 3))
    (h₀ : y = (x ^ 2) - 4) (h₁ : y' = (x' ^ 2) - 4) :
    ∃ (a b c d : ℕ), 0 < a ∧ 0 < b ∧ 0 < c ∧ Nat.Coprime a c ∧
    y = (a - Real.sqrt b) / c ∧ a + b + c = 62 := by
  sorry"""),
    Theorem("pb_005_aime_2025i_p11", """set_option maxHeartbeats 0
open BigOperators Real Nat Topology Rat

theorem {name} (f : ℝ → ℝ) (S : Finset ℝ)
    (h₀ : ∀ (x : ℝ), (-1 ≤ x ∧ x < 1) → f x = x)
    (h₁ : ∀ (x : ℝ), (1 ≤ x ∧ x < 3) → f x = 2 - x)
    (h₂ : ∀ (x : ℝ), f x = f (x + 4))
    (h₃ : ∀ (x : ℝ), ∀ x : ℝ, x ∈ S ↔ x = 34 * (f x) ^ 2) :
    ∃ (a b c d : ℕ), 0 < a ∧ 0 < b ∧ 0 < c ∧ 0 < d ∧
    Nat.Coprime a b ∧ Nat.Coprime a d ∧ Nat.Coprime b d ∧ Squarefree c ∧
    (∑ x ∈ S, f x) = (a + b * Real.sqrt c) / d ∧ a + b + c + d = 259 := by
  sorry"""),
    Theorem("pb_006_aime_2025ii_p2", """set_option maxHeartbeats 0
open BigOperators Real Nat Topology Rat

theorem {name} (S : Finset ℕ)
    (h₀ : ∀ (n : ℕ), n ∈ S ↔ (n + 2) ∣ 3 * (n + 3) * (n ^ 2 + 9)) :
    (∑ n ∈ S, n) = 49 := by
  sorry"""),
    Theorem("pb_007_aime_2025ii_p4", """set_option maxHeartbeats 0
open BigOperators Real Nat Topology Rat

theorem {name} (ans : ℚ)
    (answer : ans = (∏ k ∈ Finset.Icc (4 : ℕ) 63,
      (Real.logb k (5 ^ (k ^ 2 - 1)) / Real.logb (k + 1) (5 ^ (k ^ 2 - 4)))
    )) :
    ↑ans.den + ans.num = 106 := by
  sorry"""),
    Theorem("pb_008_number_theory__p2", """theorem {name} (x y : ℤ) (u : ℤ) (n : ℕ) :
  x^2 + y^2 - 1 = 4 * x * y → x + u * Real.sqrt 3 = (2 + Real.sqrt 3)^n := by
  sorry"""),
    Theorem("pb_009_number_theory__p3_2", """open Int Nat

theorem {name} (p : ℕ) : ∃ m : ℕ, (15 * m + 8) % 7 = 1 ∧ m = 7 * p := by
  sorry"""),
    Theorem("pb_010_number_theory__p4", """theorem {name} (x y : ℤ) :
  (∃ x, p ∣ x^2 - x + 3) ↔ (∃ y, p ∣ y^2 - y + 25) := by
  sorry"""),
    Theorem("pb_011_number_theory__p5", """theorem {name} (l : ℤ) (hl : 1 ≤ l ∧ l ≤ n) :
  ∃ (a b : ℤ), a < n ∧ b < n ∧
  Nat.gcd (a.natAbs) n.natAbs = 1 ∧
  Nat.gcd (b.natAbs) n.natAbs = 1 ∧
  (l = a + b ∨ l = a - b) := by
  sorry"""),
    Theorem("pb_012_number_theory__p6", """theorem {name} (t : ℚ) :
  ∃ (x y : ℚ), x = (d * t^2 + 1) / (d * t^2 - 1) ∧ y = 2 * t / (d * t^2 - 1) ∧ x^2 - d * y^2 = 1 := by
  sorry"""),
    Theorem("pb_013_number_theory__p8", """theorem {name} (x y z : ℕ) (h : x * y = z^2 + 1) :
  ∃ (a b c d : ℤ), x = a^2 + b^2 ∧ y = c^2 + d^2 ∧ z = a * c + b * d := by
  sorry"""),
    Theorem("pb_014_number_theory__p9", """theorem {name} {{m : ℤ}} (h : m = 2 + 2 * Real.sqrt (28 * n^2 + 1))
  (h_int : ∃ k : ℤ, Real.sqrt (28 * n^2 + 1) = k) :
  ∃ k : ℤ, m = k^2 := by
  sorry"""),
    Theorem("pb_015_number_theory__p10", """theorem {name} {{α : ℝ}} (hα : Irrational α) {{n : ℕ}} (hn : 0 < n) :
  ∃ p q : ℤ, 0 < q ∧ q ≤ n ∧ |α - p/q| < 1/((n + 1) * q) := by
  sorry"""),
    Theorem("pb_016_number_theory__p11", """theorem {name} (p : ℕ) (hp : Nat.Prime p) :
  ∃ (a b : ℤ), (a^2 + b^2 + 1) % p = 0 := by
  sorry"""),
    Theorem("pb_017_number_theory__p12", """theorem {name} : ¬ ∃ (k : ℤ), (a^2 + b^2 + c^2 : ℤ) = k * (3 * (a * b + b * c + c * a : ℤ)) := by
  sorry"""),
    Theorem("pb_018_number_theory__p13", """theorem {name} (d x : ℤ) (hd : d ∣ 5 * x^2 + 1) (h_odd : Odd d) :
  d % 20 = 1 ∨ d % 20 = 3 ∨ d % 20 = 7 ∨ d % 20 = 9 := by
  sorry"""),
    Theorem("pb_019_number_theory__p14", """theorem {name} (p : ℤ) (hp : Prime p) (hp_mod_6 : p % 6 = 1) :
  ∃ (a b : ℤ), p = a^2 - a * b + b^2 := by
  sorry"""),
    Theorem("pb_020_number_theory__p16", """theorem {name} {{n : ℕ}}
  (h1 : n % 7 = 5) (h2 : n % 9 = 3) (h3 : n % 11 = 7) :
  n = 579 := by
  sorry"""),
    Theorem("pb_021_number_theory__p17", """theorem {name} (n : ℕ) :
  (∃ (k : ℕ), k > 0 ∧ k < n ∧
    ∃ (x_i y_i : ℕ), x_i % 2 = 1 ∧ y_i % 2 = 1 ∧
      x_i + y_i * Real.sqrt 2 = (1 + Real.sqrt 2)^(2 * n + 1) ∧
      n = (x_i - 3) / 2) ↔
  ∃ (k : ℕ), k > 0 ∧ k < n ∧
    Nat.choose n (k - 1) = 2 * Nat.choose n k + Nat.choose n (k + 1) := by
  sorry"""),
    Theorem("pb_022_number_theory__p19_1", """theorem {name} :
  ∃ (S : Set ℕ), Set.Infinite S ∧ ∀ p ∈ S, Nat.Prime p ∧ p ≡ 1 [MOD 4] := by
  sorry"""),
    Theorem("pb_023_number_theory__p19_2", """theorem {name} :
  ∃ (S : Set ℕ), Set.Infinite S ∧ ∀ p ∈ S, Nat.Prime p ∧ p ≡ 9 [MOD 10] := by
  sorry"""),
    Theorem("pb_024_number_theory__p20", """theorem {name} :
  ∀ (n : ℕ), ∀ (a b c d e f : ℕ),
    (a * b * c * d * e * f = n^5) →
    (a + 1 = b ∧ b + 1 = c ∧ c + 1 = d ∧ d + 1 = e ∧ e + 1 = f) →
    False := by
  sorry"""),
    Theorem("pb_025_number_theory__p23", """theorem {name} :
  ∀ p : ℕ, p.Prime → p ∣ n^4 - n^2 + 1 → ∃ k : ℕ, p = 12 * k + 1 := by
  sorry"""),
    Theorem("pb_026_number_theory__p24", """theorem {name} (a : ℕ) (d : ℤ := a^2 - 1) (x y : ℤ) (m : ℤ := x^2 - d * y^2) :
  |m| < 2 * a + 2 → ∃ k : ℤ, k^2 = |m| := by
  sorry"""),
    Theorem("pb_027_number_theory__p25", """theorem {name} (x y : ℕ) (h : 37 ∣ 15 * x + 11 * y) : 37 ∣ 7 * x + 15 * y := by
  sorry"""),
    Theorem("pb_028_number_theory__p26", """theorem {name} (α : ℝ) :
  ∃ (p q : ℕ) (h : q > 0), ∀ (n : ℕ), n > 0 → ∃ (p_n q_n : ℕ) (h_n : q_n > 0),
  |α - (p_n : ℝ) / q_n| < 1 / q_n^2 := by
  sorry"""),
    Theorem("pb_029_number_theory__p27", """theorem {name} {{x y k m n : PNat}}
  (h : ∃ z : PNat, (x : ℕ)^(m : ℕ) + (y : ℕ)^(n : ℕ) = z) :
  ¬((4 * k * x * y - 1) ∣ z) := by
  sorry"""),
    Theorem("pb_030_number_theory__p29", """theorem {name} (h : x ≠ 1) :
  (x^2 - d * y^2 = 1) ↔ ∃ t : ℚ, x = (d * t^2 + 1) / (d * t^2 - 1) ∧ y = 2 * t / (d * t^2 - 1) := by
  sorry"""),
    Theorem("pb_031_number_theory__p31", """theorem {name} (x y : ℤ) (hx : 2 < x) (hy : 2 < y) : ¬(∃ z : ℤ, (x^2 + 1) = z * (y^2 - 5)) := by
  sorry"""),
    Theorem("pb_032_number_theory__p32", """theorem {name} :
  (∃ (x y : ℤ), x^2 - p * y^2 = -1) ↔ p = 2 ∨ p % 4 = 1 := by
  sorry"""),
    Theorem("pb_033_elementary_algebra__p2", """theorem {name} :
    a^2 + b^2 + c^2 + d^2 = a * (b + c + d) → a = 0 ∧ b = 0 ∧ c = 0 ∧ d = 0 := by
  sorry"""),
    Theorem("pb_034_elementary_algebra__p4", """theorem {name} :
  (2 * x + 3 * y = 8) ∧ (5 * x + 9 * y = -2) → (x = 26 ∧ y = -44/3) := by
  sorry"""),
    Theorem("pb_035_elementary_algebra__p5", """open Polynomial BigOperators

theorem {name} :
  coeff ((∑ i ∈ Finset.range 101, X ^ i) ^ 3) 4 = 15 := by
  sorry"""),
    Theorem("pb_036_elementary_algebra__p6", """theorem {name} (ha : 0 < a) (hb : 0 < b): a^3 + b^3 ≥ a^2 * b + a * b^2 := by
  sorry"""),
    Theorem("pb_037_elementary_algebra__p8_1", """open Real

theorem {name} : LHS = RHS := by
  sorry"""),
    Theorem("pb_038_elementary_algebra__p9", """theorem {name} (n : ℕ) (hn : 0 < n) : 5^n > n! ↔ n ≤ 11 := by
  sorry"""),
    Theorem("pb_039_elementary_algebra__p11", """theorem {name} : ∀ (n : ℕ), n > 0 → (5^n > n.factorial ↔ n ≤ 11) := by
  sorry"""),
    Theorem("pb_040_elementary_algebra__p14_2", """open Real

theorem {name} : (4 * p^4 * q^7 * r^8) / (2 * p^3) = 2 * p * q^7 * r^8 := by
  sorry"""),
    Theorem("pb_041_elementary_algebra__p15", """theorem {name} :
  ( (n + 1) ^ 3 - n ^ 3 = n ^ 2 ) → ∃ k : ℕ, k ^ 2 = 2 * n - 1 := by
  sorry"""),
    Theorem("pb_042_elementary_algebra__p19", """theorem {name} {{a b c s : ℝ}} :
  a^2 * (s - a) + b^2 * (s - b) + c^2 * (s - c) ≤ (3/2) * a * b * c := by
  sorry"""),
    Theorem("pb_043_elementary_algebra__p21", """theorem {name} (a b c : ℝ) :
    a^2 + b^2 + c^2 ≥ a * b + b * c + c * a := by
  sorry"""),
    Theorem("pb_044_elementary_algebra__p22", """theorem {name} (a b c : ℝ) (ha : 0 < a) (hb : 0 < b) (hc : 0 < c) :
  2 * a^3 + 2 * b^3 + 2 * c^3 + a^2 * b + b^2 * c + c^2 * a ≥ 3 * a * b^2 + 3 * b * c^2 + 3 * c * a^2 := by
  sorry"""),
    Theorem("pb_045_elementary_algebra__p24", """theorem {name} : 5 * catPrice + 3 * dogPrice = 41 := by
  sorry"""),
    Theorem("pb_046_linear_algebra__p8_2", """open Matrix

theorem {name} : (4, -4, -2) ∈ {{x : ℚ × ℚ × ℚ |
-19 * x.1 + 8 * x.2.1 = -108 ∧
-71 * x.1 + 30 * x.2.1 = -404 ∧
-2 * x.1 + x.2.1 = -12 ∧
4 * x.1 + x.2.2 = 14}} := by
  sorry"""),
    Theorem("pb_047_linear_algebra__p16", """open InnerProductSpace

theorem {name} : ¬ ∀ (x y : EuclideanSpace ℝ (Fin 2)), ‖x + y‖ = ‖x‖ + ‖y‖ := by
  sorry"""),
    Theorem("pb_048_abstract_algebra__p2", """theorem {name} (h : ∀ x, Polynomial.eval (Real.cos x) P = Polynomial.eval (Real.sin x) P) :
∃ Q : Polynomial ℝ, ∀ x, Polynomial.eval x P = Polynomial.eval (x^4 - x^2) Q := by
  sorry"""),
    Theorem("pb_049_abstract_algebra__p3", """theorem {name} :
  ∃ (G : Type) (_ : Group G) (_ : Fintype G),
    Fintype.card G = 6 ∧ ¬(∀ a b : G, a * b = b * a) := by
  sorry"""),
    Theorem("pb_050_abstract_algebra__p4_2", """open Polynomial -- Ensure Polynomial is recognized in Lean 4

theorem {name} : (-3 : ZMod 8) = 5 := by
  sorry"""),
    Theorem("pb_051_abstract_algebra__p4_3", """open Polynomial -- Ensure Polynomial is recognized in Lean 4

theorem {name} : f + g = C 2 * X^2 + C 5 := by
  sorry"""),
    Theorem("pb_052_abstract_algebra__p5", """open Polynomial

theorem {name} {{K : Type*}} [CommRing K] [Field K] [CharZero K] [Algebra ℚ K]
  (P : Polynomial ℚ) (hd : P.degree = 4)
  (x₁ x₂ : K) (hr₁ : eval x₁ (map (algebraMap ℚ K) P) = 0)
  (hr₂ : eval x₂ (map (algebraMap ℚ K) P) = 0)
  (hsum : x₁ + x₂ ≠ (-P.coeff 1) / (2 * P.leadingCoeff)) :
  ∃ q : ℚ, x₁ * x₂ = algebraMap ℚ K q := by
  sorry"""),
    Theorem("pb_053_abstract_algebra__p6", """open Polynomial

theorem {name} (h : P^2 - C 2 = C 2 * eval₂ C (2 * X^2 - C 1) P) :
  P = C (1 + Real.sqrt 3) ∨ P = C (1 - Real.sqrt 3) := by
  sorry"""),
    Theorem("pb_054_abstract_algebra__p7", """theorem {name} :
  (∀ x, P.eval x ^ 2 - 2 = 2 * P.eval (2 * x ^ 2 - 1)) ↔
  ∃ a : ℝ , a ^ 2 - 2 * a - 2 = 0 ∧ P = Polynomial.C a := by
  sorry"""),
    Theorem("pb_055_abstract_algebra__p9", """theorem {name} (h : x + y + z = x * y * z) :
 1 / (1 + x * y) + 1 / (1 + y * z) + 1 / (1 + z * x) ≤ 3 / 4 := by
  sorry"""),
    Theorem("pb_056_abstract_algebra__p10", """theorem {name} (a b c : ℝ) (ha : 0 < a) (hb : 0 < b) (hc : 0 < c)
  (h_sum : (a^2 / (1 + a^2)) + (b^2 / (1 + b^2)) + (c^2 / (1 + c^2)) = 1) :
  abs (a * b * c) ≤ 1 / (2 * Real.sqrt 2) := by
  sorry"""),
    Theorem("pb_057_abstract_algebra__p11_1", """open Polynomial

theorem {name} : Polynomial.IsRoot f 1 := by
  sorry"""),
    Theorem("pb_058_abstract_algebra__p12", """open Polynomial

theorem {name} :
  (∀ x, (P %ₘ (X - 1)^3).eval x = -1) ∧ (∀ x, (P %ₘ (X + 1)^3).eval x = 1) →
  P = -C (3/8) * X^5 + C (5/4) * X^3 - C (15/8) * X := by
  sorry"""),
    Theorem("pb_059_abstract_algebra__p16", """open Polynomial

theorem {name} (h : ∀ x, P.eval x ^ 2 - 1 = 4 * P.eval (x ^ 2 - 4 * x + 1)) :
  P = C (2 + Real.sqrt 5) ∨ P = C (2 - Real.sqrt 5) := by
  sorry"""),
    Theorem("pb_060_abstract_algebra__p19", """theorem {name} :
  ∃ (A B : Polynomial ℝ), P = A^2 + Polynomial.X * B^2 := by
  sorry"""),
    Theorem("pb_061_abstract_algebra__p32", """theorem {name}  :
e = 0 ∧ g = 0 ∧ f = 0 := by
  sorry"""),
    Theorem("pb_062_abstract_algebra__p34", """open BigOperators Finset Nat

theorem {name} (n : ℕ) (x : ℝ) :
 ∑ k ∈ range (2 * n + 1), (Nat.choose n (k/2)) * x^k = (1 + x) * (1 + x^2)^n := by
  sorry"""),
    Theorem("pb_063_calculus__p4", """open Filter Topology

theorem {name} :
Tendsto (fun x : ℝ => (Real.cos (2 * x - 6) - 1) / (x^3 - 6 * x^2 + 9 * x)) (𝓝 3) (𝓝 (-2 / 3)) := by
  sorry"""),
    Theorem("pb_064_calculus__p6", """open scoped Topology Filter

theorem {name} : deriv (fun x => Real.cos (x^3)) x = -Real.sin (x^3) * (3 * x^2) := by
  sorry"""),
    Theorem("pb_065_calculus__p8", """theorem {name} :
∫ (x : ℝ) in Set.Icc (-Real.sqrt 7) (Real.sqrt 7), ∫ (y : ℝ) in Set.Icc (-Real.sqrt (7 - x^2)) (Real.sqrt (7 - x^2)),
(x^2 + y^2 + 2*(7 - x^2 - y^2)) = (957 * Real.sqrt 29 - 47) / 20 * π := by
  sorry"""),
    Theorem("pb_066_calculus__p11", """open Filter

theorem {name} : deriv (fun x : ℝ => x^3) 4 = 48 := by
  sorry"""),
    Theorem("pb_067_calculus__p13_5", """open Real

theorem {name} :
  HasDerivAt f (8 * Real.sqrt 3) (π / 3) ∧
  f (π / 3) = 8 * Real.sqrt 3 * (π / 3 - π / 3) + 4 := by
  sorry"""),
    Theorem("pb_068_calculus__p14", """open MeasureTheory

theorem {name} (D : Set (Fin 3 → ℝ))
  (hD : D = {{p : Fin 3 → ℝ | p 2 ≥ 0 ∧ p 3 ≥ 0 ∧ p 2 ≤ p 1 ∧ p 3 ≤ 4 - p 1^2 - p 2^2}}) :
  let integrand := fun p : Fin 3 → ℝ => Real.exp (p 1^2 + p 2^2)
  ∫ p in D, integrand p = (Real.exp 4 - 5) * π / 8 := by
  sorry"""),
    Theorem("pb_069_calculus__p18", """open Real

theorem {name} :
(∫ x in Set.Icc 2 8, (1 / x + x^2) : ℝ) = Real.log 4 + 168 := by
  sorry"""),
    Theorem("pb_070_calculus__p36", """theorem {name} (p : ℝ) (hp : p ≠ -1) :
∫ x in Set.Icc 0 1, x^p = (1^(p+1) - 0^(p+1)) / (p+1) := by
  sorry"""),
    Theorem("pb_071_calculus__p41", """open Filter Topology

theorem {name} : Tendsto (fun x => (Real.exp (8 * x) - 1) / x) (𝓝[Set.Ioi 0] 0) (𝓝 8) := by
  sorry"""),
    Theorem("pb_072_calculus__p44", """open Filter Topology

theorem {name} :
  Tendsto (fun x => (1 - (Real.cos x)^(Real.sin x)) / x^3) (𝓝 0) (𝓝 (1 / 2)) := by
  sorry"""),
    Theorem("pb_073_calculus__p49", """open Real
open MeasureTheory

theorem {name} :
∫ x in Set.Icc (-1) 1, (x^2 / (1 + x^2)) = 2 - π / 2 := by
  sorry"""),
    Theorem("pb_074_calculus__p59", """open Set Filter MeasureTheory

theorem {name} :
  let f := fun x y => 11 - 2 * x - 3 * y^2
  let R := Icc (1 : ℝ) (3 : ℝ) ×ˢ Icc (-2 : ℝ) (5 : ℝ)
  ∫ x in Icc (1 : ℝ) (3 : ℝ), ∫ y in Icc (-2 : ℝ) (5 : ℝ), f x y = -168 := by
  sorry"""),
    Theorem("pb_075_calculus__p60", """open Filter Topology

theorem {name} :
Tendsto (fun x => Real.sin (3 * x + x^2) / (5 * x + 2 * x^2)) (𝓝 0) (𝓝 (3 / 5)) := by
  sorry"""),
    Theorem("pb_076_calculus__p61", """open Filter Topology

theorem {name} :
  Tendsto (fun x => (3^x - 1) / x) (𝓝[≠] 0) (𝓝 (Real.log 3)) := by
  sorry"""),
    Theorem("pb_077_calculus__p63", """theorem {name} {{f : ℝ → ℝ}}
    (hf : Continuous f)
    (h_diff : ∀ x, DifferentiableAt ℝ f x)
    (h_deriv : ∀ x, deriv f x = (1 / 5 : ℝ) * Real.sin (5 * x)) :
    ∃ C, ∀ x, f x = (1 / 5 : ℝ) * Real.sin (5 * x) + C := by
  sorry"""),
    Theorem("pb_078_calculus__p65", """theorem {name} : deriv (fun x => Real.cos x) = fun x => -Real.sin x := by
  sorry"""),
    Theorem("pb_079_calculus__p68", """open MeasureTheory
open Real

theorem {name} :(∫⁻ (p : ℝ × ℝ × ℝ) in {{p : ℝ × ℝ × ℝ | p.1 ∈ Set.Icc 0 5 ∧ p.2.1 ∈ Set.Icc 0 1 ∧
  p.2.2 ∈ Set.Icc 0 1 ∧ p.2.1 + p.2.2 ≤ 1}}, ENNReal.ofReal p.2.2) = 5 / 6 := by
  sorry"""),
    Theorem("pb_080_real_analysis__p5", """theorem {name} :
  a = 0 ∧ b = 0 ∧ c = 0 ∧ d = 0 := by
  sorry"""),
    Theorem("pb_081_real_analysis__p6_2", """open Real NNReal

theorem {name} {{a b : ℕ+ → ℝ≥0}} (h : ∀ n, a n ≤ b n) (hb : ¬ Summable b) :
    ¬ Summable a := by
  sorry"""),
    Theorem("pb_082_real_analysis__p7_1", """open Real

theorem {name} : ∀ x ∈ Set.Ioo 0 8, HasDerivAt f ((1/3 : ℝ) * (8 * x - x^2)^(-2/3 : ℝ) * (8 - 2 * x)) x := by
  sorry"""),
    Theorem("pb_083_real_analysis__p8_1", """open Real Set

theorem {name} (x : ℝ) : 0 < x^2 + 1 := by
  sorry"""),
    Theorem("pb_084_real_analysis__p8_2", """open Real Set

theorem {name} : ∀ x : ℝ, x ∈ univ := by
  sorry"""),
    Theorem("pb_085_real_analysis__p8_3", """open Real Set

theorem {name} :
  ∀ x : ℝ, ∃! y : ℝ, y = Real.log (x^2 + 1) := by
  sorry"""),
    Theorem("pb_086_real_analysis__p12_1", """open Topology Metric Filter

theorem {name} (x : ℝ) : |Real.sin x| ≤ 1 := by
  sorry"""),
    Theorem("pb_087_real_analysis__p12_2", """open Topology Metric Filter

theorem {name} {{x : ℕ → ℝ}} (hx : ∃ L, Tendsto x atTop (𝓝 L)) :
  ∃ M, ∀ n, |x n| ≤ M := by
  sorry"""),
    Theorem("pb_088_complex_analysis__p2_1", """open Complex Real

theorem {name} : exp (I * (5 * π / 2)) = exp (I * (π / 2)) := by
  sorry"""),
    Theorem("pb_089_complex_analysis__p2_2", """open Complex Real

theorem {name} : exp (I * (π / 2)) = I := by
  sorry"""),
    Theorem("pb_090_complex_analysis__p4_1", """open Complex

theorem {name} : I ^ 73 = I := by
  sorry"""),
    Theorem("pb_091_complex_analysis__p4_2", """open Complex

theorem {name} (n : ℕ) : I ^ n = I ^ (n % 4) := by
  sorry"""),
    Theorem("pb_092_probability__p1_3", """open Real MeasureTheory ProbabilityTheory

theorem {name} (h : Summable (fun (k : ℕ) => k * poissonPMFReal lambda k)) :
  ∑' k, k * poissonPMFReal lambda k = lambda := by
  sorry"""),
    Theorem("pb_093_probability__p1_4", """open Real MeasureTheory ProbabilityTheory

theorem {name} (h0 : lambda = 1)
  (h1 : Summable fun k => k * k^2 * poissonPMFReal lambda k)
  (h2 : Summable fun k => k * poissonPMFReal lambda k)
  (h3 : Summable fun k => k^2 * poissonPMFReal lambda k) :
  (∑' k, k * k^2 * poissonPMFReal lambda k) -
  (∑' k, k * poissonPMFReal lambda k) * (∑' k, k^2 * poissonPMFReal lambda k) = 3 := by
  sorry"""),
]
