# ruff: noqa: E501
"""
MiniF2F benchmark theorems (competition mathematics).

Contains 200 validated theorems from AMC, AIME, IMO, and MATH dataset.
These are problems neural theorem provers have been specifically trained on.
"""
from corpus.lean.theorems import Theorem

MINIF2F_CORPUS: list[Theorem] = [
    Theorem("f2f_000_aime_1983_p1", """theorem {name} (x y z w : ℕ) (ht : 1 < x ∧ 1 < y ∧ 1 < z) (hw : 0 ≤ w) (h0 : Real.log w / Real.log x = 24) (h1 : Real.log w / Real.log y = 40) (h2 : Real.log w / Real.log (x * y * z) = 12) : Real.log w / Real.log z = 60 := by
  sorry"""),
    Theorem("f2f_001_aime_1983_p2", """theorem {name} (x p : ℝ) (f : ℝ → ℝ) (h₀ : 0 < p ∧ p < 15) (h₁ : p ≤ x ∧ x ≤ 15) (h₂ : f x = abs (x - p) + abs (x - 15) + abs (x - p - 15)) : 15 ≤ f x := by
  sorry"""),
    Theorem("f2f_002_aime_1983_p3", """theorem {name} (f : ℝ → ℝ) (h₀ : ∀ x, f x = (x^2 + (18 * x + 30) - 2 * Real.sqrt (x^2 + (18 * x + 45)))) (h₁ : Fintype (f⁻¹' {{0}})) : ∏ x ∈ (f⁻¹' {{0}}).toFinset, x = 20 := by
  sorry"""),
    Theorem("f2f_003_aime_1984_p1", """theorem {name} (u : ℕ → ℚ) (h₀ : ∀ n, u (n + 1) = u n + 1) (h₁ : ∑ k ∈ Finset.range 98, u k.succ = 137) : ∑ k ∈ Finset.range 49, u (2 * k.succ) = 93 := by
  sorry"""),
    Theorem("f2f_004_aime_1984_p7", """theorem {name} (f : ℤ → ℤ) (h₀ : ∀ n, 1000 ≤ n → f n = n - 3) (h₁ : ∀ n, n < 1000 → f n = f (f (n + 5))) : f 84 = 997 := by
  sorry"""),
    Theorem("f2f_005_aime_1987_p5", """theorem {name} (x y : ℤ) (h₀ : y^2 + 3 * (x^2 * y^2) = 30 * x^2 + 517): 3 * (x^2 * y^2) = 588 := by
  sorry"""),
    Theorem("f2f_006_aime_1988_p8", """theorem {name} (f : ℕ → ℕ → ℝ) (h₀ : ∀ x, 0 < x → f x x = x) (h₁ : ∀ x y, (0 < x ∧ 0 < y) → f x y = f y x) (h₂ : ∀ x y, (0 < x ∧ 0 < y) → (↑x + ↑y) * f x y = y * (f x (x + y))) : f 14 52 = 364 := by
  sorry"""),
    Theorem("f2f_007_aime_1989_p8", """theorem {name} (a b c d e f g : ℝ) (h₀ : a + 4 * b + 9 * c + 16 * d + 25 * e + 36 * f + 49 * g = 1) (h₁ : 4 * a + 9 * b + 16 * c + 25 * d + 36 * e + 49 * f + 64 * g = 12) (h₂ : 9 * a + 16 * b + 25 * c + 36 * d + 49 * e + 64 * f + 81 * g = 123) : 16 * a + 25 * b + 36 * c + 49 * d + 64 * e + 81 * f + 100 * g = 334 := by
  sorry"""),
    Theorem("f2f_008_aime_1990_p15", """theorem {name} (a b x y : ℝ) (h₀ : a * x + b * y = 3) (h₁ : a * x^2 + b * y^2 = 7) (h₂ : a * x^3 + b * y^3 = 16) (h₃ : a * x^4 + b * y^4 = 42) : a * x^5 + b * y^5 = 20 := by
  sorry"""),
    Theorem("f2f_009_aime_1990_p4", """theorem {name} (x : ℝ) (h₀ : 0 < x) (h₁ : x^2 - 10 * x - 29 ≠ 0) (h₂ : x^2 - 10 * x - 45 ≠ 0) (h₃ : x^2 - 10 * x - 69 ≠ 0) (h₄ : 1 / (x^2 - 10 * x - 29) + 1 / (x^2 - 10 * x - 45) - 2 / (x^2 - 10 * x - 69) = 0) : x = 13 := by
  sorry"""),
    Theorem("f2f_010_aime_1991_p9", """theorem {name} (x : ℝ) (m : ℚ) (h₀ : 1 / Real.cos x + Real.tan x = 22 / 7) (h₁ : 1 / Real.sin x + 1 / Real.tan x = m) : ↑m.den + m.num = 44 := by
  sorry"""),
    Theorem("f2f_011_aime_1994_p3", """theorem {name} (f : ℤ → ℤ) (h0 : f x + f (x-1) = x^2) (h1 : f 19 = 94): f (94) % 1000 = 561 := by
  sorry"""),
    Theorem("f2f_012_aime_1995_p7", """theorem {name} (k m n : ℕ) (t : ℝ) (h₀ : 0 < k ∧ 0 < m ∧ 0 < n) (h₁ : Nat.gcd m n = 1) (h₂ : (1 + Real.sin t) * (1 + Real.cos t) = 5/4) (h₃ : (1 - Real.sin t) * (1- Real.cos t) = m/n - Real.sqrt k): k + m + n = 27 := by
  sorry"""),
    Theorem("f2f_013_aime_1997_p9", """theorem {name} (a : ℝ) (h₀ : 0 < a) (h₁ : 1 / a - Int.floor (1 / a) = a^2 - Int.floor (a^2)) (h₂ : 2 < a^2) (h₃ : a^2 < 3) : a^12 - 144 * (1 / a) = 233 := by
  sorry"""),
    Theorem("f2f_014_aime_1999_p11", """theorem {name} (m : ℚ) (h₀ : 0 < m) (h₁ : ∑ k ∈ Finset.Icc (1 : ℕ) 35, Real.sin (5 * k * π / 180) = Real.tan (m * π / 180)) (h₂ : (m.num:ℝ) / m.den < 90) : ↑m.den + m.num = 177 := by
  sorry"""),
    Theorem("f2f_015_algebra_2varlineareq_fp3zeq11_3tfm1m5zeqn68_feqn10", """theorem {name} (f z: ℂ) (h₀ : f + 3*z = 11) (h₁ : 3*(f - 1) - 5*z = -68) : f = -10 ∧ z = 7 := by
  sorry"""),
    Theorem("f2f_016_algebra_9onxpypzleqsum2onxpy", """theorem {name} (x y z : ℝ) (h₀ : 0 < x ∧ 0 < y ∧ 0 < z) : 9 / (x + y + z) ≤ 2 / (x + y) + 2 / (y + z) + 2 / (z + x) := by
  sorry"""),
    Theorem("f2f_017_algebra_abpbcpcageq3_sumaonsqrtapbgeq3onsqrt2", """theorem {name} (a b c : ℝ) (h₀ : 0 < a ∧ 0 < b ∧ 0 < c) (h₁ : 3 ≤ a * b + b * c + c * a) : 3 / Real.sqrt 2 ≤ a / Real.sqrt (a + b) + b / Real.sqrt (b + c) + c / Real.sqrt (c + a) := by
  sorry"""),
    Theorem("f2f_018_algebra_absapbon1pabsapbleqsumabsaon1pabsa", """theorem {name} (a b : ℝ) : abs (a + b) / (1 + abs (a + b)) ≤ abs a / (1 + abs a) + abs b / (1 + abs b) := by
  sorry"""),
    Theorem("f2f_019_algebra_absxm1pabsxpabsxp1eqxp2_0leqxleq1", """theorem {name} (x : ℝ) (h₀ : abs (x - 1) + abs x + abs (x + 1) = x + 2) : 0 ≤ x ∧ x ≤ 1 := by
  sorry"""),
    Theorem("f2f_020_algebra_amgm_sum1toneqn_prod1tonleq1", """theorem {name} (a : ℕ → NNReal) (n : ℕ) (h₀ : ∑ x ∈ Finset.range n, a x = n) : ∏ x ∈ Finset.range n, a x ≤ 1 := by
  sorry"""),
    Theorem("f2f_021_algebra_amgm_sumasqdivbgeqsuma", """theorem {name} (a b c d : ℝ) (h₀ : 0 < a ∧ 0 < b ∧ 0 < c ∧ 0 < d) : a^2 / b + b^2 / c + c^2 / d + d^2 / a ≥ a + b + c + d := by
  sorry"""),
    Theorem("f2f_022_algebra_apbmpcneq0_aeq0anbeq0anceq0", """theorem {name} (a b c : ℚ) (m n : ℝ) (h₀ : 0 < m ∧ 0 < n) (h₁ : m^3 = 2) (h₂ : n^3 = 4) (h₃ : (a:ℝ) + b * m + c * n = 0) : a = 0 ∧ b = 0 ∧ c = 0 := by
  sorry"""),
    Theorem("f2f_023_algebra_apbon2pownleqapownpbpowon2", """theorem {name} (a b : ℝ) (n : ℕ) (h₀ : 0 < a ∧ 0 < b) (h₁ : 0 < n) : ((a + b) / 2)^n ≤ (a^n + b^n) / 2 := by
  sorry"""),
    Theorem("f2f_024_algebra_apbpceq2_abpbcpcaeq1_aleq1on3anbleq1ancleq", """theorem {name} (a b c : ℝ) (h₀ : a ≤ b ∧ b ≤ c) (h₁ : a + b + c = 2) (h₂ : a * b + b * c + c * a = 1) : 0 ≤ a ∧ a ≤ 1 / 3 ∧ 1 / 3 ≤ b ∧ b ≤ 1 ∧ 1 ≤ c ∧ c ≤ 4 / 3 := by
  sorry"""),
    Theorem("f2f_025_algebra_bleqa_apbon2msqrtableqambsqon8b", """theorem {name} (a b : ℝ) (h₀ : 0 < a ∧ 0 < b) (h₁ : b ≤ a) : (a + b) / 2 - Real.sqrt (a * b) ≤ (a - b)^2 / (8 * b) := by
  sorry"""),
    Theorem("f2f_026_algebra_cubrtrp1oncubrtreq3_rcubp1onrcubeq5778", """theorem {name} (r : ℝ) (h₀ : r^(1 / 3: ℝ) + 1 / r^(1 / 3: ℝ) = 3) : r^3 + 1 / r^3 = 5778 := by
  sorry"""),
    Theorem("f2f_027_algebra_ineq_nto1onlt2m1on", """theorem {name} (n : ℕ) : (n : ℝ) ^ (1 / n : ℝ) < 2 - 1 / n := by
  sorry"""),
    Theorem("f2f_028_algebra_others_exirrpowirrrat", """theorem {name} : ∃ a b, Irrational a ∧ Irrational b ∧ ¬ Irrational (a^b) := by
  sorry"""),
    Theorem("f2f_029_algebra_sqineq_at2malt1", """theorem {name} (a : ℝ) : a * (2 - a) ≤ 1 := by
  sorry"""),
    Theorem("f2f_030_algebra_sqineq_unitcircatbpabsamblt1", """theorem {name} (a b: ℝ) (h₀ : a^2 + b^2 = 1) : a * b + |a - b| ≤ 1 := by
  sorry"""),
    Theorem("f2f_031_algebra_sqineq_unitcircatbpamblt1", """theorem {name} (a b: ℝ) (h₀ : a^2 + b^2 = 1) : a * b + (a - b) ≤ 1 := by
  sorry"""),
    Theorem("f2f_032_algebra_sum1onsqrt2to1onsqrt10000lt198", """theorem {name} : ∑ k ∈ (Finset.Icc (2 : ℕ) 10000), (1 / Real.sqrt k) < 198 := by
  sorry"""),
    Theorem("f2f_033_amc12_2000_p1", """theorem {name} (i m o : ℕ) (h₀ : i ≠ m ∧ m ≠ o ∧ o ≠ i) (h₁ : i*m*o = 2001) : i+m+o ≤ 671 := by
  sorry"""),
    Theorem("f2f_034_amc12_2000_p12", """theorem {name} (a m c : ℕ) (h₀ : a + m + c = 12) : a*m*c + a*m + m*c + a*c ≤ 112 := by
  sorry"""),
    Theorem("f2f_035_amc12_2000_p20", """theorem {name} (x y z : ℝ) (h₀ : 0 < x ∧ 0 < y ∧ 0 < z) (h₁ : x + 1/y = 4) (h₂ : y + 1/z = 1) (h₃ : z + 1/x = 7/3) : x*y*z = 1 := by
  sorry"""),
    Theorem("f2f_036_amc12_2000_p6", """theorem {name} (p q : ℕ) (h₀ : Nat.Prime p ∧ Nat.Prime q) (h₁ : 4 ≤ p ∧ p ≤ 18) (h₂ : 4 ≤ q ∧ q ≤ 18) : p * q - (p + q) ≠ 194 := by
  sorry"""),
    Theorem("f2f_037_amc12_2001_p21", """theorem {name} (a b c d : ℕ) (h₀ : a * b * c * d = Nat.factorial 8) (h₁ : a * b + a + b = 524) (h₂ : b * c + b + c = 146) (h₃ : c * d + c + d = 104) : ↑a - ↑d = (10 : ℤ) := by
  sorry"""),
    Theorem("f2f_038_amc12_2001_p5", """theorem {name} : Finset.prod (Finset.filter (λ x => ¬ Even x) (Finset.range 10000)) (id : ℕ → ℕ) = (10000!) / ((2^5000) * (5000!)) := by
  sorry"""),
    Theorem("f2f_039_amc12a_2002_p13", """theorem {name} (a b : ℝ) (h₀ : 0 < a ∧ 0 < b) (h₁ : a ≠ b) (h₂ : abs (a - 1/a) = 1) (h₃ : abs (b - 1/b) = 1) : a + b = Real.sqrt 5 := by
  sorry"""),
    Theorem("f2f_040_amc12a_2002_p6", """theorem {name} (n : ℕ) (h₀ : 0 < n) : ∃ m, (m > n ∧ ∃ p, m * p ≤ m + p) := by
  sorry"""),
    Theorem("f2f_041_amc12a_2003_p23", """theorem {name} (S : Finset ℕ) (h₀ : ∀ (k : ℕ), k ∈ S ↔ 0 < k ∧ ((k * k) : ℕ) ∣ (∏ i ∈ (Finset.Icc 1 9), i !)) : S.card = 672 := by
  sorry"""),
    Theorem("f2f_042_amc12a_2003_p5", """theorem {name} (A M C : ℕ) (h₀ : A ≤ 9 ∧ M ≤ 9 ∧ C ≤ 9) (h₁ : Nat.ofDigits 10 [0,1,C,M,A] + Nat.ofDigits 10 [2,1,C,M,A] = 123422) : A + M + C = 14 := by
  sorry"""),
    Theorem("f2f_043_amc12a_2008_p25", """theorem {name} (a b : ℕ → ℝ) (h₀ : ∀ n, a (n + 1) = Real.sqrt 3 * a n - b n) (h₁ : ∀ n, b (n + 1) = Real.sqrt 3 * b n + a n) (h₂ : a 100 = 2) (h₃ : b 100 = 4) : a 1 + b 1 = 1 / (2^98) := by
  sorry"""),
    Theorem("f2f_044_amc12a_2009_p6", """theorem {name} (m n p q : ℝ) (h₀ : p = 2 ^ m) (h₁ : q = 3 ^ n) : p^(2 * n) * (q^m) = 12^(m * n) := by
  sorry"""),
    Theorem("f2f_045_amc12a_2009_p7", """theorem {name} (x : ℝ) (n : ℕ) (a : ℕ → ℝ) (h₁ : ∀ m, a (m + 1) - a m = a (m + 2) - a (m + 1)) (h₂ : a 1 = 2 * x - 3) (h₃ : a 2 = 5 * x - 11) (h₄ : a 3 = 3 * x + 1) (h₅ : a n = 2009) : n = 502 := by
  sorry"""),
    Theorem("f2f_046_amc12a_2013_p4", """theorem {name} : (2^2014 + 2^2012) / (2^2014 - 2^2012) = (5:ℝ) / 3 := by
  sorry"""),
    Theorem("f2f_047_amc12a_2019_p12", """theorem {name} (x y : ℕ) (h₀ : x ≠ 1 ∧ y ≠ 1) (h₁ : Real.log x / Real.log 2 = Real.log 16 / Real.log y) (h₂ : x * y = 64) : (Real.log (x / y) / Real.log 2) ^ 2 = 20 := by
  sorry"""),
    Theorem("f2f_048_amc12a_2020_p10", """theorem {name} (n : ℕ) (h₀ : 0 < n) (h₁ : Real.logb 2 (Real.logb 16 n) = Real.logb 4 (Real.logb 4 n)) : (Nat.digits 10 n).sum = 13 := by
  sorry"""),
    Theorem("f2f_049_amc12a_2020_p15", """theorem {name} (a b : ℂ) (h₀ : a^3 - 8 = 0) (h₁ : b^3 - 8 * b^2 - 8 * b + 64 = 0) : ‖a - b‖ ≤ 2 * Real.sqrt 21 := by
  sorry"""),
    Theorem("f2f_050_amc12a_2020_p25", """theorem {name} (a : ℚ) (S : Finset ℝ) (h₀ : ∀ (x : ℝ), x ∈ S ↔ ↑⌊x⌋ * (x - ↑⌊x⌋) = ↑a * x ^ 2) (h₁ : ∑ k ∈ S, k = 420) : ↑a.den + a.num = 929 := by
  sorry"""),
    Theorem("f2f_051_amc12a_2020_p4", """theorem {name} (S : Finset ℕ) (h₀ : ∀ (n : ℕ), n ∈ S ↔ 1000 ≤ n ∧ n ≤ 9999 ∧ (∀ (d : ℕ), d ∈ Nat.digits 10 n → Even d) ∧ 5 ∣ n) : S.card = 100 := by
  sorry"""),
    Theorem("f2f_052_amc12a_2020_p7", """theorem {name} (a : ℕ → ℕ) (h₀ : (a 0)^3 = 1) (h₁ : (a 1)^3 = 8) (h₂ : (a 2)^3 = 27) (h₃ : (a 3)^3 = 64) (h₄ : (a 4)^3 = 125) (h₅ : (a 5)^3 = 216) (h₆ : (a 6)^3 = 343) : ∑ k ∈ Finset.range 7, (6 * (a k)^2) - ↑(2 * ∑ k ∈ Finset.range 6, (a k)^2) = 658 := by
  sorry"""),
    Theorem("f2f_053_amc12a_2020_p9", """theorem {name} (S : Finset ℝ) (h₀ : ∀ (x : ℝ), x ∈ S ↔ 0 ≤ x ∧ x ≤ 2 * Real.pi ∧ Real.tan (2 * x) = Real.cos (x / 2)) : S.card = 5 := by
  sorry"""),
    Theorem("f2f_054_amc12a_2021_p12", """theorem {name} (a b c d : ℝ) (f : ℂ → ℂ) (h₀ : ∀ z, f z = z^6 - 10 * z^5 + a * z^4 + b * z^3 + c * z^2 + d * z + 16) (h₁ : ∀ z, f z = 0 → (z.im = 0 ∧ 0 < z.re ∧ ↑(Int.floor z.re) = z.re)) : b = -88 := by
  sorry"""),
    Theorem("f2f_055_amc12a_2021_p14", """theorem {name} : (∑ k ∈ (Finset.Icc 1 20), (Real.logb (5^k) (3^(k^2)))) * (∑ k ∈ (Finset.Icc 1 100), (Real.logb (9^k) (25^k))) = 21000 := by
  sorry"""),
    Theorem("f2f_056_amc12a_2021_p18", """theorem {name} (f : ℚ → ℝ) (h₀ : ∀x>0, ∀y>0, f (x * y) = f x + f y) (h₁ : ∀p, Nat.Prime p → f p = p) : f (25 / 11) < 0 := by
  sorry"""),
    Theorem("f2f_057_amc12a_2021_p19", """theorem {name} (S : Finset ℝ) (h₀ : ∀ (x : ℝ), x ∈ S ↔ 0 ≤ x ∧ x ≤ Real.pi ∧ Real.sin (Real.pi / 2 * Real.cos x) = Real.cos (Real.pi / 2 * Real.sin x)) : S.card = 2 := by
  sorry"""),
    Theorem("f2f_058_amc12a_2021_p22", """theorem {name} (a b c : ℝ) (f : ℝ → ℝ) (h₀ : ∀ x, f x = x^3 + a * x^2 + b * x + c) (h₁ : f⁻¹' {{0}} = {{Real.cos (2 * Real.pi / 7), Real.cos (4 * Real.pi / 7), Real.cos (6 * Real.pi / 7)}}) : a * b * c = 1 / 32 := by
  sorry"""),
    Theorem("f2f_059_amc12a_2021_p25", """theorem {name} (N : ℕ) (f : ℕ → ℝ) (h₀ : ∀ n, 0 < n → f n = ((Nat.divisors n).card)/(n^((1:ℝ)/3))) (h₁ : ∀ n ≠ N, 0 < n → f n < f N) : (Nat.digits 10 N).sum = 9 := by
  sorry"""),
    Theorem("f2f_060_amc12a_2021_p3", """theorem {name} (x y : ℕ) (h₀ : x + y = 17402) (h₁ : 10∣x) (h₂ : x / 10 = y) : ↑x - ↑y = (14238:ℤ) := by
  sorry"""),
    Theorem("f2f_061_amc12a_2021_p8", """theorem {name} (d : ℕ → ℕ) (h₀ : d 0 = 0) (h₁ : d 1 = 0) (h₂ : d 2 = 1) (h₃ : ∀ n≥3, d n = d (n - 1) + d (n - 3)) : Even (d 2021) ∧ Odd (d 2022) ∧ Even (d 2023) := by
  sorry"""),
    Theorem("f2f_062_amc12a_2021_p9", """theorem {name} : ∏ k ∈ Finset.range 7, (2^(2^k) + 3^(2^k)) = 3^128 - 2^128 := by
  sorry"""),
    Theorem("f2f_063_amc12b_2002_p19", """theorem {name} (a b c: ℝ) (h₀ : 0 < a ∧ 0 < b ∧ 0 < c) (h₁ : a * (b + c) = 152) (h₂ : b * (c + a) = 162) (h₃ : c * (a + b) = 170) : a * b * c = 720 := by
  sorry"""),
    Theorem("f2f_064_amc12b_2002_p2", """theorem {name} (x : ℤ) (h₀ : x = 4) : (3 * x - 2) * (4 * x + 1) - (3 * x - 2) * (4 * x) + 1 = 11 := by
  sorry"""),
    Theorem("f2f_065_amc12b_2002_p4", """theorem {name} (n : ℕ) (h₀ : 0 < n) (h₁ : ((1 / 2 + 1 / 3 + 1 / 7 + 1 / n) : ℚ).den = 1) : n = 42 := by
  sorry"""),
    Theorem("f2f_066_amc12b_2002_p7", """theorem {name} (a b c : ℕ) (h₀ : 0 < a ∧ 0 < b ∧ 0 < c) (h₁ : b = a + 1) (h₂ : c = b + 1) (h₃ : a * b * c = 8 * (a + b + c)) : a^2 + (b^2 + c^2) = 77 := by
  sorry"""),
    Theorem("f2f_067_amc12b_2020_p13", """theorem {name} : Real.sqrt (Real.log 6 / Real.log 2 + Real.log 6 / Real.log 3) = Real.sqrt (Real.log 3 / Real.log 2) + Real.sqrt (Real.log 2 / Real.log 3) := by
  sorry"""),
    Theorem("f2f_068_amc12b_2020_p2", """theorem {name} : ((100 ^ 2 - 7 ^ 2):ℝ) / (70 ^ 2 - 11 ^ 2) * ((70 - 11) * (70 + 11) / ((100 - 7) * (100 + 7))) = 1 := by
  sorry"""),
    Theorem("f2f_069_amc12b_2020_p21", """theorem {name} (S : Finset ℕ) (h₀ : ∀ (n : ℕ), n ∈ S ↔ 0 < n ∧ (↑n + (1000 : ℝ)) / 70 = Int.floor (Real.sqrt n)) : S.card = 6 := by
  sorry"""),
    Theorem("f2f_070_amc12b_2020_p22", """theorem {name} (t : ℝ) : ((2^t - 3 * t) * t) / (4^t) ≤ 1 / 12 := by
  sorry"""),
    Theorem("f2f_071_amc12b_2020_p6", """theorem {name} (n : ℕ) (h₀ : 9 ≤ n) : ∃ (x : ℕ), (x : ℝ)^2 = (Nat.factorial (n + 2) - Nat.factorial (n + 1)) / n ! := by
  sorry"""),
    Theorem("f2f_072_amc12b_2021_p1", """theorem {name} (S : Finset ℤ) (h₀ : ∀ (x : ℤ), x ∈ S ↔ ↑(abs x) < 3 * Real.pi): S.card = 19 := by
  sorry"""),
    Theorem("f2f_073_amc12b_2021_p13", """theorem {name} (S : Finset ℝ) (h₀ : ∀ (x : ℝ), x ∈ S ↔ 0 < x ∧ x ≤ 2 * Real.pi ∧ 1 - 3 * Real.sin x + 5 * Real.cos (3 * x) = 0) : S.card = 6 := by
  sorry"""),
    Theorem("f2f_074_amc12b_2021_p18", """theorem {name} (z : ℂ) (h₀ : 12 * Complex.normSq z = 2 * Complex.normSq (z + 2) + Complex.normSq (z^2 + 1) + 31) : z + 6 / z = -2 := by
  sorry"""),
    Theorem("f2f_075_amc12b_2021_p3", """theorem {name} (x : ℝ) (h₀ : 2 + 1 / (1 + 1 / (2 + 2 / (3 + x))) = 144 / 53) : x = 3 / 4 := by
  sorry"""),
    Theorem("f2f_076_amc12b_2021_p4", """theorem {name} (m a : ℕ) (h₀ : 0 < m ∧ 0 < a) (h₁ : ↑m / ↑a = (3:ℝ) / 4) : (84 * ↑m + 70 * ↑a) / (↑m + ↑a) = (76:ℝ) := by
  sorry"""),
    Theorem("f2f_077_amc12b_2021_p9", """theorem {name} : (Real.log 80 / Real.log 2) / (Real.log 2 / Real.log 40) - (Real.log 160 / Real.log 2) / (Real.log 2 / Real.log 20) = 2 := by
  sorry"""),
    Theorem("f2f_078_imo_1959_p1", """theorem {name} (n : ℕ) (h₀ : 0 < n) : Nat.gcd (21*n + 4) (14*n + 3) = 1 := by
  sorry"""),
    Theorem("f2f_079_imo_1960_p2", """theorem {name} (x : ℝ) (h₀ : 0 ≤ 1 + 2 * x) (h₁ : (1 - Real.sqrt (1 + 2 * x))^2 ≠ 0) (h₂ : (4 * x^2) / (1 - Real.sqrt (1 + 2*x))^2 < 2*x + 9) (h₃ : x ≠ 0) : -(1 / 2) ≤ x ∧ x < 45 / 8 := by
  sorry"""),
    Theorem("f2f_080_imo_1962_p2", """theorem {name} (x : ℝ) (h₀ : 0 ≤ 3 - x) (h₁ : 0 ≤ x + 1) (h₂ : 1 / 2 < Real.sqrt (3 - x) - Real.sqrt (x + 1)) : -1 ≤ x ∧ x < 1 - Real.sqrt 31 / 8 := by
  sorry"""),
    Theorem("f2f_081_imo_1963_p5", """theorem {name} : Real.cos (π / 7) - Real.cos (2 * π / 7) + Real.cos (3 * π / 7) = 1 / 2 := by
  sorry"""),
    Theorem("f2f_082_imo_1964_p2", """theorem {name} (a b c : ℝ) (h₀ : 0 < a ∧ 0 < b ∧ 0 < c) (h₁ : c < a + b) (h₂ : b < a + c) (h₃ : a < b + c) : a^2 * (b + c - a) + b^2 * (c + a - b) + c^2 * (a + b - c) ≤ 3 * a * b * c := by
  sorry"""),
    Theorem("f2f_083_imo_1965_p2", """theorem {name} (x y z : ℝ) (a : ℕ → ℝ) (h₀ : 0 < a 0 ∧ 0 < a 4 ∧ 0 < a 8) (h₁ : a 1 < 0 ∧ a 2 < 0) (h₂ : a 3 < 0 ∧ a 5 < 0) (h₃ : a 6 < 0 ∧ a 7 < 0) (h₄ : 0 < a 0 + a 1 + a 2) (h₅ : 0 < a 3 + a 4 + a 5) (h₆ : 0 < a 6 + a 7 + a 8) (h₇ : a 0 * x + a 1 * y + a 2 * z = 0) (h₈ : a 3 * x + a 4 * y + a 5 * z = 0) (h₉ : a 6 * x + a 7 * y + a 8 * z = 0) : x = 0 ∧ y = 0 ∧ z = 0 := by
  sorry"""),
    Theorem("f2f_084_imo_1968_p5_1", """theorem {name} (a : ℝ) (f : ℝ → ℝ) (h₀ : 0 < a) (h₁ : ∀ x, f (x + a) = 1 / 2 + Real.sqrt (f x - (f x)^2)) : ∃ b > 0, ∀ x, f (x + b) = f x := by
  sorry"""),
    Theorem("f2f_085_imo_1969_p2", """theorem {name} (m n : ℝ) (k : ℕ) (a : ℕ → ℝ) (y : ℝ → ℝ) (h₀ : 0 < k) (h₁ : ∀ x, y x = ∑ i ∈ Finset.range k, ((Real.cos (a i + x)) / (2^i))) (h₂ : y m = 0) (h₃ : y n = 0) : ∃ t : ℤ, m - n = t * π := by
  sorry"""),
    Theorem("f2f_086_imo_1974_p3", """theorem {name} (n : ℕ) : ¬ 5∣∑ k ∈ Finset.range (n + 1), (Nat.choose (2 * n + 1) (2 * k + 1)) * (2^(3 * k)) := by
  sorry"""),
    Theorem("f2f_087_imo_1977_p6", """theorem {name} (f : ℕ → ℕ) (h₀ : ∀ n, 0 < f n) (h₁ : ∀ n, 0 < n → f (f n) < f (n + 1)) : ∀ n, 0 < n → f n = n := by
  sorry"""),
    Theorem("f2f_088_imo_1981_p6", """theorem {name} (f : ℕ → ℕ → ℕ) (g : ℕ → ℕ) (h₀ : ∀ y, f 0 y = y + 1) (h₁ : ∀ x, f (x + 1) 0 = f x 1) (h₂ : ∀ x y, f (x + 1) (y + 1) = f x (f (x + 1) y)) (h₃ : g 0 = 2) (h₄ : ∀ n, g (n + 1) = 2^(g n)) : f 4 1981 = g 1983 - 3 := by
  sorry"""),
    Theorem("f2f_089_imo_1982_p1", """theorem {name} (f : ℕ → ℕ) (h₀ : ∀ m n, (0 < m ∧ 0 < n) → f (m + n) - f m - f n = 0 ∨ f (m + n) - f m - f n = 1) (h₁ : f 2 = 0) (h₂ : 0 < f 3) (h₃ : f 9999 = 3333) : f 1982 = 660 := by
  sorry"""),
    Theorem("f2f_090_imo_1983_p6", """theorem {name} (a b c : ℝ) (h₀ : 0 < a ∧ 0 < b ∧ 0 < c) (h₁ : c < a + b) (h₂ : b < a + c) (h₃ : a < b + c) : 0 ≤ a^2 * b * (a - b) + b^2 * c * (b - c) + c^2 * a * (c - a) := by
  sorry"""),
    Theorem("f2f_091_imo_1984_p6", """theorem {name} (a b c d k m : ℕ) (h₀ : 0 < a ∧ 0 < b ∧ 0 < c ∧ 0 < d) (h₁ : Odd a ∧ Odd b ∧ Odd c ∧ Odd d) (h₂ : a < b ∧ b < c ∧ c < d) (h₃ : a * d = b * c) (h₄ : a + d = 2^k) (h₅ : b + c = 2^m) : a = 1 := by
  sorry"""),
    Theorem("f2f_092_imo_1985_p6", """theorem {name} (f : ℕ → NNReal → ℝ) (h₀ : ∀ x, f 1 x = x) (h₁ : ∀ x n, f (n + 1) x = f n x * (f n x + 1 / n)) : ∃! a, ∀ n, 0 < n → 0 < f n a ∧ f n a < f (n + 1) a ∧ f (n + 1) a < 1 := by
  sorry"""),
    Theorem("f2f_093_imo_1992_p1", """theorem {name} (p q r : ℤ) (h₀ : 1 < p ∧ p < q ∧ q < r) (h₁ : (p - 1) * (q - 1) * (r - 1)∣(p * q * r - 1)) : (p, q, r) = (2, 4, 8) ∨ (p, q, r) = (3, 5, 15) := by
  sorry"""),
    Theorem("f2f_094_imo_1997_p5", """theorem {name} (x y : ℕ) (h₀ : 0 < x ∧ 0 < y) (h₁ : x^(y^2) = y^x) : (x, y) = (1, 1) ∨ (x, y) = (16, 2) ∨ (x, y) = (27, 3) := by
  sorry"""),
    Theorem("f2f_095_imo_2001_p6", """theorem {name} (a b c d : ℕ) (h₀ : 0 < a ∧ 0 < b ∧ 0 < c ∧ 0 < d) (h₁ : d < c) (h₂ : c < b) (h₃ : b < a) (h₄ : a * c + b * d = (b + d + a - c) * (b + d + c - a)) : ¬ Nat.Prime (a * b + c * d) := by
  sorry"""),
    Theorem("f2f_096_imo_2019_p1", """theorem {name} (f : ℤ → ℤ) : ((∀ a b, f (2 * a) + (2 * f b) = f (f (a + b))) ↔ (∀ z, f z = 0 \\/ ∃ c, ∀ z, f z = 2 * z + c)) := by
  sorry"""),
    Theorem("f2f_097_imosl_2007_algebra_p6", """theorem {name} (a : ℕ → NNReal) (h₀ : ∑ x ∈ Finset.range 100, ((a (x + 1))^2) = 1) : ∑ x ∈ Finset.range 99, ((a (x + 1))^2 * a (x + 2)) + (a 100)^2 * a 1 < 12 / 25 := by
  sorry"""),
    Theorem("f2f_098_induction_11div10tonmn1ton", """theorem {name} (n : ℕ) : 11 ∣ (10^n - (-1 : ℤ)^n) := by
  sorry"""),
    Theorem("f2f_099_induction_12dvd4expnp1p20", """theorem {name} (n : ℕ) : 12 ∣ 4^(n+1) + 20 := by
  sorry"""),
    Theorem("f2f_100_induction_1pxpownlt1pnx", """theorem {name} (x : ℝ) (n : ℕ) (h₀ : -1 < x) (h₁ : 0 < n) : (1 + ↑n*x) ≤ (1 + x)^(n:ℕ) := by
  sorry"""),
    Theorem("f2f_101_induction_nfactltnexpnm1ngt3", """theorem {name} (n : ℕ) (h₀ : 3 ≤ n) : (n)! < n^(n - 1) := by
  sorry"""),
    Theorem("f2f_102_induction_pord1p1on2powklt5on2", """theorem {name} (n : ℕ) (h₀ : 0 < n) : ∏ k ∈ Finset.Icc 1 n, (1 + (1:ℝ) / 2^k) < 5 / 2 := by
  sorry"""),
    Theorem("f2f_103_induction_pprime_pdvdapowpma", """theorem {name} (p a : ℕ) (h₀ : 0 < a) (h₁ : Nat.Prime p) : p ∣ (a^p - a) := by
  sorry"""),
    Theorem("f2f_104_induction_prod1p1onk3le3m1onn", """theorem {name} (n : ℕ) (h₀ : 0 < n) : ∏ k ∈ Finset.Icc 1 n, (1 + (1:ℝ) / k^3) ≤ (3:ℝ) - 1 / ↑n := by
  sorry"""),
    Theorem("f2f_105_induction_sumkexp3eqsumksq", """theorem {name} (n : ℕ) : ∑ k ∈ Finset.range n, k^3 = (∑ k ∈ Finset.range n, k)^2 := by
  sorry"""),
    Theorem("f2f_106_mathd_algebra_107", """theorem {name} (x y : ℝ) (h₀ : x^2 + 8 * x + y^2 - 6 * y = 0) : (x + 4)^2 + (y-3)^2 = 5^2 := by
  sorry"""),
    Theorem("f2f_107_mathd_algebra_113", """theorem {name} (x : ℝ) : x^2 - 14 * x + 3 ≥ 7^2 - 14 * 7 + 3 := by
  sorry"""),
    Theorem("f2f_108_mathd_algebra_114", """theorem {name} (a : ℝ) (h₀ : a = 8) : (16 * (a^2) ^ (1 / 3 : ℝ)) ^ (1 / 3 : ℝ) = 4 := by
  sorry"""),
    Theorem("f2f_109_mathd_algebra_125", """theorem {name} (x y : ℕ) (h₀ : 0 < x ∧ 0 < y) (h₁ : 5 * x = y) (h₂ : (↑x - (3:ℤ)) + (y - (3:ℤ)) = 30) : x = 6 := by
  sorry"""),
    Theorem("f2f_110_mathd_algebra_129", """theorem {name} (a : ℝ) (h₀ : a ≠ 0) (h₁ : 8⁻¹ / 4⁻¹ - a⁻¹ = 1) : a = -2 := by
  sorry"""),
    Theorem("f2f_111_mathd_algebra_137", """theorem {name} (x : ℕ) (h₀ : ↑x + (4:ℝ) / (100:ℝ) * ↑x = 598) : x = 575 := by
  sorry"""),
    Theorem("f2f_112_mathd_algebra_139", """theorem {name} (s : ℝ → ℝ → ℝ) (h₀ : ∀ x, ∀ y, x≠0 -> y≠0 -> s x y = (1/y - 1/x) / (x-y)) : s 3 11 = 1/33 := by
  sorry"""),
    Theorem("f2f_113_mathd_algebra_141", """theorem {name} (a b : ℝ) (h₁ : (a * b)=180) (h₂ : 2 * (a + b)=54) : (a^2 + b^2) = 369 := by
  sorry"""),
    Theorem("f2f_114_mathd_algebra_142", """theorem {name} (m b : ℝ) (h₀ : m * 7 + b = -1) (h₁ : m * (-1) + b = 7) : m + b = 5 := by
  sorry"""),
    Theorem("f2f_115_mathd_algebra_143", """theorem {name} (f g : ℝ → ℝ) (h₀ : ∀ x, f x = x + 1) (h₁ : ∀ x, g x = x^2 + 3) : f (g 2) = 8 := by
  sorry"""),
    Theorem("f2f_116_mathd_algebra_148", """theorem {name} (c : ℝ) (f : ℝ → ℝ) (h₀ : ∀ x, f x = c * x^3 - 9 * x + 3) (h₁ : f 2 = 9) : c = 3 := by
  sorry"""),
    Theorem("f2f_117_mathd_algebra_153", """theorem {name} (n : ℝ) (h₀ : n = 1 / 3) : Int.floor (10 * n) + Int.floor (100 * n) + Int.floor (1000 * n) + Int.floor (10000 * n) = 3702 := by
  sorry"""),
    Theorem("f2f_118_mathd_algebra_156", """theorem {name} (x y : ℝ) (f g : ℝ → ℝ) (h₀ : ∀t, f t = t^4) (h₁ : ∀t, g t = 5 * t^2 - 6) (h₂ : f x = g x) (h₃ : f y = g y) (h₄ : x^2 < y^2) : y^2 - x^2 = 1 := by
  sorry"""),
    Theorem("f2f_119_mathd_algebra_158", """theorem {name} (a : ℕ) (h₀ : Even a) (h₁ : ∑ k ∈ Finset.range 8, (2 * k + 1) - ∑ k ∈ Finset.range 5, (a + 2 * k) = (4:ℤ)) : a = 8 := by
  sorry"""),
    Theorem("f2f_120_mathd_algebra_160", """theorem {name} (n x : ℝ) (h₀ : n + x = 97) (h₁ : n + 5 * x = 265) : n + 2 * x = 139 := by
  sorry"""),
    Theorem("f2f_121_mathd_algebra_17", """theorem {name} (a : ℝ) (h₀ : Real.sqrt (4 + Real.sqrt (16 + 16 * a)) + Real.sqrt (1 + Real.sqrt (1 + a)) = 6) : a = 8 := by
  sorry"""),
    Theorem("f2f_122_mathd_algebra_170", """theorem {name} (S : Finset ℤ) (h₀ : ∀ (n : ℤ), n ∈ S ↔ abs (n - 2) ≤ 5 + 6 / 10) : S.card = 11 := by
  sorry"""),
    Theorem("f2f_123_mathd_algebra_171", """theorem {name} (f : ℝ → ℝ) (h₀ : ∀x, f x = 5 * x + 4) : f 1 = 9 := by
  sorry"""),
    Theorem("f2f_124_mathd_algebra_176", """theorem {name} (x : ℝ) : (x + 1)^2 * x = x^3 + 2 * x^2 + x := by
  sorry"""),
    Theorem("f2f_125_mathd_algebra_184", """theorem {name} (a b : NNReal) (h₀ : 0 < a ∧ 0 < b) (h₁ : (a^2) = 6*b) (h₂ : (a^2) = 54/b) : a = 3 * NNReal.sqrt 2 := by
  sorry"""),
    Theorem("f2f_126_mathd_algebra_188", """theorem {name} (σ : Equiv ℝ ℝ) (h : σ.1 2 = σ.2 2) : σ.1 (σ.1 2) = 2 := by
  sorry"""),
    Theorem("f2f_127_mathd_algebra_196", """theorem {name} (S : Finset ℝ) (h₀ : ∀ (x : ℝ), x ∈ S ↔ abs (2 - x) = 3) : ∑ k ∈ S, k = 4 := by
  sorry"""),
    Theorem("f2f_128_mathd_algebra_208", """theorem {name} : Real.sqrt 1000000 - 1000000^(1/3) = 900 := by
  sorry"""),
    Theorem("f2f_129_mathd_algebra_209", """theorem {name} (σ : Equiv ℝ ℝ) (h₀ : σ.2 2 = 10) (h₁ : σ.2 10 = 1) (h₂ : σ.2 1 = 2) : σ.1 (σ.1 10) = 1 := by
  sorry"""),
    Theorem("f2f_130_mathd_algebra_215", """theorem {name} (S : Finset ℝ) (h₀ : ∀ (x : ℝ), x ∈ S ↔ (x + 3)^2 = 121) : ∑ k ∈ S, k = -6 := by
  sorry"""),
    Theorem("f2f_131_mathd_algebra_24", """theorem {name} (x : ℝ) (h₀ : x / 50 = 40) : x = 2000 := by
  sorry"""),
    Theorem("f2f_132_mathd_algebra_246", """theorem {name} (a b : ℝ) (f : ℝ → ℝ) (h₀ : ∀ x, f x = a * x^4 - b * x^2 + x + 5) (h₂ : f (-3) = 2) : f 3 = 8 := by
  sorry"""),
    Theorem("f2f_133_mathd_algebra_263", """theorem {name} (y : ℝ) (h₀ : 0 ≤ 19 + 3 * y) (h₁ : Real.sqrt (19 + 3 * y) = 7) : y = 10 := by
  sorry"""),
    Theorem("f2f_134_mathd_algebra_270", """theorem {name} (f : ℝ → ℝ) (h₀ : ∀ x, x ≠ -2 -> f x = 1 / (x + 2)) : f (f 1) = 3/7 := by
  sorry"""),
    Theorem("f2f_135_mathd_algebra_275", """theorem {name} (x : ℝ) (h : ((11:ℝ)^(1 / 4))^(3 * x - 3) = 1 / 5) : ((11:ℝ)^(1 / 4))^(6 * x + 2) = 121 / 25 := by
  sorry"""),
    Theorem("f2f_136_mathd_algebra_276", """theorem {name} (a b : ℤ) (h₀ : ∀ x : ℝ, 10 * x^2 - x - 24 = (a * x - 8) * (b * x + 3)) : a * b + b = 12 := by
  sorry"""),
    Theorem("f2f_137_mathd_algebra_288", """theorem {name} (x y : ℝ) (n : NNReal) (h₀ : x < 0 ∧ y < 0) (h₁ : abs y = 6) (h₂ : Real.sqrt ((x - 8)^2 + (y - 3)^2) = 15) (h₃ : Real.sqrt (x^2 + y^2) = Real.sqrt n) : n = 52 := by
  sorry"""),
    Theorem("f2f_138_mathd_algebra_289", """theorem {name} (k t m n : ℕ) (h₀ : Nat.Prime m ∧ Nat.Prime n) (h₁ : t < k) (h₂ : k^2 - m * k + n = 0) (h₃ : t^2 - m * t + n = 0) : m^n + n^m + k^t + t^k = 20 := by
  sorry"""),
    Theorem("f2f_139_mathd_algebra_293", """theorem {name} (x : NNReal) : Real.sqrt (60 * x) * Real.sqrt (12 * x) * Real.sqrt (63 * x) = 36 * x * Real.sqrt (35 * x) := by
  sorry"""),
    Theorem("f2f_140_mathd_algebra_296", """theorem {name} : abs (((3491 - 60) * (3491 + 60) - 3491^2):ℤ) = 3600 := by
  sorry"""),
    Theorem("f2f_141_mathd_algebra_302", """theorem {name} : (Complex.I / 2)^2 = -(1 / 4) := by
  sorry"""),
    Theorem("f2f_142_mathd_algebra_304", """theorem {name} : 91^2 = 8281 := by
  sorry"""),
    Theorem("f2f_143_mathd_algebra_313", """theorem {name} (v i z : ℂ) (h₀ : v = i * z) (h₁ : v = 1 + Complex.I) (h₂ : z = 2 - Complex.I) : i = 1/5 + 3/5 * Complex.I := by
  sorry"""),
    Theorem("f2f_144_mathd_algebra_314", """theorem {name} (n : ℕ) (h₀ : n = 11) : (1 / 4)^(n + 1) * 2^(2 * n) = 1 / 4 := by
  sorry"""),
    Theorem("f2f_145_mathd_algebra_320", """theorem {name} (x : ℝ) (a b c : ℕ) (h₀ : 0 < a ∧ 0 < b ∧ 0 < c ∧ 0 ≤ x) (h₁ : 2 * x^2 = 4 * x + 9) (h₂ : x = (a + Real.sqrt b) / c) (h₃ : c = 2) : a + b + c = 26 := by
  sorry"""),
    Theorem("f2f_146_mathd_algebra_329", """theorem {name} (x y : ℝ) (h₀ : 3 * y = x) (h₁ : 2 * x + 5 * y = 11) : x + y = 4 := by
  sorry"""),
    Theorem("f2f_147_mathd_algebra_33", """theorem {name} (x y z : ℝ) (h₀ : x ≠ 0) (h₁ : 2 * x = 5 * y) (h₂ : 7 * y = 10 * z) : z / x = 7 / 25 := by
  sorry"""),
    Theorem("f2f_148_mathd_algebra_332", """theorem {name} (x y : ℝ) (h₀ : (x + y) / 2 = 7) (h₁ : Real.sqrt (x * y) = Real.sqrt 19) : x^2 + y^2 = 158 := by
  sorry"""),
    Theorem("f2f_149_mathd_algebra_338", """theorem {name} (a b c : ℝ) (h₀ : 3 * a + b + c = -3) (h₁ : a + 3 * b + c = 9) (h₂ : a + b + 3 * c = 19) : a * b * c = -56 := by
  sorry"""),
    Theorem("f2f_150_mathd_algebra_342", """theorem {name} (a d: ℝ) (h₀ : ∑ k ∈ (Finset.range 5), (a + k * d) = 70) (h₁ : ∑ k ∈ (Finset.range 10), (a + k * d) = 210) : a = 42/5 := by
  sorry"""),
    Theorem("f2f_151_mathd_algebra_346", """theorem {name} (f g : ℝ → ℝ) (h₀ : ∀ x, f x = 2 * x - 3) (h₁ : ∀ x, g x = x + 1) : g (f 5 - 1) = 7 := by
  sorry"""),
    Theorem("f2f_152_mathd_algebra_354", """theorem {name} (a d : ℝ) (h₀ : a + 6 * d = 30) (h₁ : a + 10 * d = 60) : a + 20 * d = 135 := by
  sorry"""),
    Theorem("f2f_153_mathd_algebra_359", """theorem {name} (y : ℝ) (h₀ : y + 6 + y = 2 * 12) : y = 9 := by
  sorry"""),
    Theorem("f2f_154_mathd_algebra_362", """theorem {name} (a b : ℝ) (h₀ : a^2 * b^3 = 32 / 27) (h₁ : a / b^3 = 27 / 4) : a + b = 8 / 3 := by
  sorry"""),
    Theorem("f2f_155_mathd_algebra_388", """theorem {name} (x y z : ℝ) (h₀ : 3 * x + 4 * y - 12 * z = 10) (h₁ : -2 * x - 3 * y + 9 * z = -4) : x = 14 := by
  sorry"""),
    Theorem("f2f_156_mathd_algebra_392", """theorem {name} (n : ℕ) (h₀ : Even n) (h₁ : ((n:ℤ) - 2)^2 + (n:ℤ)^2 + ((n:ℤ) + 2)^2 = 12296) : ((n - 2) * n * (n + 2)) / 8 = 32736 := by
  sorry"""),
    Theorem("f2f_157_mathd_algebra_398", """theorem {name} (a b c : ℝ) (h₀ : 0 < a ∧ 0 < b ∧ 0 < c) (h₁ : 9 * b = 20 * c) (h₂ : 7 * a = 4 * b) : 63 * a = 80 * c := by
  sorry"""),
    Theorem("f2f_158_mathd_algebra_400", """theorem {name} (x : ℝ) (h₀ : 5 + 500 / 100 * 10 = 110 / 100 * x) : x = 50 := by
  sorry"""),
    Theorem("f2f_159_mathd_algebra_412", """theorem {name} (x y : ℝ) (h₀ : x + y = 25) (h₁ : x - y = 11) : x = 18 := by
  sorry"""),
    Theorem("f2f_160_mathd_algebra_419", """theorem {name} (a b : ℝ) (h₀ : a = -1) (h₁ : b = 5) : -a - b^2 + 3 * (a * b) = -39 := by
  sorry"""),
    Theorem("f2f_161_mathd_algebra_427", """theorem {name} (x y z : ℝ) (h₀ : 3 * x + y = 17) (h₁ : 5 * y + z = 14) (h₂ : 3 * x + 5 * z = 41) : x + y + z = 12 := by
  sorry"""),
    Theorem("f2f_162_mathd_algebra_432", """theorem {name} (x : ℝ) : (x + 3) * (2 * x - 6) = 2 * x^2 - 18 := by
  sorry"""),
    Theorem("f2f_163_mathd_algebra_44", """theorem {name} (s t : ℝ) (h₀ : s = 9 - 2 * t) (h₁ : t = 3 * s + 1) : s = 1 ∧ t = 4 := by
  sorry"""),
    Theorem("f2f_164_mathd_algebra_440", """theorem {name} (x : ℝ) (h₀ : 3 / 2 / 3 = x / 10) : x = 5 := by
  sorry"""),
    Theorem("f2f_165_mathd_algebra_441", """theorem {name} (x : ℝ) (h₀ : x ≠ 0) : 12 / (x * x) * (x^4 / (14 * x)) * (35 / (3 * x)) = 10 := by
  sorry"""),
    Theorem("f2f_166_mathd_algebra_452", """theorem {name} (a : ℕ → ℝ) (h₀ : ∀ n, a (n + 2) - a (n + 1) = a (n + 1) - a n) (h₁ : a 1 = 2 / 3) (h₂ : a 9 = 4 / 5) : a 5 = 11 / 15 := by
  sorry"""),
    Theorem("f2f_167_mathd_algebra_459", """theorem {name} (a b c d : ℚ) (h₀ : 3 * a = b + c + d) (h₁ : 4 * b = a + c + d) (h₂ : 2 * c = a + b + d) (h₃ : 8 * a + 10 * b + 6 * c = 24) : ↑d.den + d.num = 28 := by
  sorry"""),
    Theorem("f2f_168_mathd_algebra_478", """theorem {name} (b h v : ℝ) (h₀ : 0 < b ∧ 0 < h ∧ 0 < v) (h₁ : v = 1 / 3 * (b * h)) (h₂ : b = 30) (h₃ : h = 13 / 2) : v = 65 := by
  sorry"""),
    Theorem("f2f_169_mathd_algebra_484", """theorem {name} : Real.log 27 / Real.log 3 = 3 := by
  sorry"""),
    Theorem("f2f_170_mathd_algebra_487", """theorem {name} (a b c d : ℝ) (h₀ : b = a^2) (h₁ : a + b = 1) (h₂ : d = c^2) (h₃ : c + d = 1) (h₄ : a ≠ c) : Real.sqrt ((a - c)^2 + (b - d)^2)= Real.sqrt 10 := by
  sorry"""),
    Theorem("f2f_171_mathd_algebra_513", """theorem {name} (a b : ℝ) (h₀ : 3 * a + 2 * b = 5) (h₁ : a + b = 2) : a = 1 ∧ b = 1 := by
  sorry"""),
    Theorem("f2f_172_mathd_algebra_598", """theorem {name} (a b c d : ℝ) (h₁ : ((4:ℝ)^a) = 5) (h₂ : ((5:ℝ)^b) = 6) (h₃ : ((6:ℝ)^c) = 7) (h₄ : ((7:ℝ)^d) = 8) : a * b * c * d = 3 / 2 := by
  sorry"""),
    Theorem("f2f_173_mathd_algebra_756", """theorem {name} (a b : ℝ) (h₀ : (2:ℝ)^a = 32) (h₁ : a^b = 125) : b^a = 243 := by
  sorry"""),
    Theorem("f2f_174_mathd_algebra_76", """theorem {name} (f : ℤ → ℤ) (h₀ : ∀n, Odd n → f n = n^2) (h₁ : ∀ n, Even n → f n = n^2 - 4*n -1) : f 4 = -1 := by
  sorry"""),
    Theorem("f2f_175_mathd_algebra_80", """theorem {name} (x : ℝ) (h₀ : x ≠ -1) (h₁ : (x - 9) / (x + 1) = 2) : x = -11 := by
  sorry"""),
    Theorem("f2f_176_mathd_numbertheory_100", """theorem {name} (n : ℕ) (h₀ : 0 < n) (h₁ : Nat.gcd n 40 = 10) (h₂ : Nat.lcm n 40 = 280) : n = 70 := by
  sorry"""),
    Theorem("f2f_177_mathd_numbertheory_1124", """theorem {name} (n : ℕ) (h₀ : n ≤ 9) (h₁ : 18∣374 * 10 + n) : n = 4 := by
  sorry"""),
    Theorem("f2f_178_mathd_numbertheory_12", """theorem {name} : Finset.card (Finset.filter (λ x => 20∣x) (Finset.Icc 15 85)) = 4 := by
  sorry"""),
    Theorem("f2f_179_mathd_numbertheory_127", """theorem {name} : (∑ k ∈ (Finset.range 101), 2^k) % 7 = 3 := by
  sorry"""),
    Theorem("f2f_180_mathd_numbertheory_135", """theorem {name} (n A B C : ℕ) (h₀ : n = 3^17 + 3^10) (h₁ : 11 ∣ (n + 1)) (h₂ : [A,B,C].Pairwise (·≠·)) (h₃ : {{A,B,C}} ⊂ Finset.Icc 0 9) (h₄ : Odd A ∧ Odd C) (h₅ : ¬ 3 ∣ B) (h₆ : Nat.digits 10 n = [B,A,B,C,C,A,C,B,A]) : 100 * A + 10 * B + C = 129 := by
  sorry"""),
    Theorem("f2f_181_mathd_numbertheory_150", """theorem {name} (n : ℕ) (h₀ : ¬ Nat.Prime (7 + 30 * n)) : 6 ≤ n := by
  sorry"""),
    Theorem("f2f_182_mathd_numbertheory_175", """theorem {name} : (2^2010) % 10 = 4 := by
  sorry"""),
    Theorem("f2f_183_mathd_numbertheory_185", """theorem {name} (n : ℕ) (h₀ : n % 5 = 3) : (2 * n) % 5 = 1 := by
  sorry"""),
    Theorem("f2f_184_mathd_numbertheory_207", """theorem {name} : 8 * 9^2 + 5 * 9 + 2 = 695 := by
  sorry"""),
    Theorem("f2f_185_mathd_numbertheory_212", """theorem {name} : (16^17 * 17^18 * 18^19) % 10 = 8 := by
  sorry"""),
    Theorem("f2f_186_mathd_numbertheory_222", """theorem {name} (b : ℕ) (h₀ : Nat.lcm 120 b = 3720) (h₁ : Nat.gcd 120 b = 8) : b = 248 := by
  sorry"""),
    Theorem("f2f_187_mathd_numbertheory_227", """theorem {name} (x y n : ℕ+) (h₀ : ↑x / (4:ℝ) + y / 6 = (x + y) / n) : n = 5 := by
  sorry"""),
    Theorem("f2f_188_mathd_numbertheory_229", """theorem {name} : (5^30) % 7 = 1 := by
  sorry"""),
    Theorem("f2f_189_mathd_numbertheory_233", """theorem {name} (b : ZMod (11^2)) (h₀ : b = 24⁻¹) : b = 116 := by
  sorry"""),
    Theorem("f2f_190_mathd_numbertheory_234", """theorem {name} (a b : ℕ) (h₀ : 1 ≤ a ∧ a ≤ 9 ∧ b ≤ 9) (h₁ : (10 * a + b)^3 = 912673) : a + b = 16 := by
  sorry"""),
    Theorem("f2f_191_mathd_numbertheory_235", """theorem {name} : (29 * 79 + 31 * 81) % 10 = 2 := by
  sorry"""),
    Theorem("f2f_192_mathd_numbertheory_237", """theorem {name} : (∑ k ∈ (Finset.range 101), k) % 6 = 4 := by
  sorry"""),
    Theorem("f2f_193_mathd_numbertheory_239", """theorem {name} : (∑ k ∈ Finset.Icc 1 12, k) % 4 = 2 := by
  sorry"""),
    Theorem("f2f_194_mathd_numbertheory_247", """theorem {name} (n : ℕ) (h₀ : (3 * n) % 11 = 2) : n % 11 = 8 := by
  sorry"""),
    Theorem("f2f_195_mathd_numbertheory_254", """theorem {name} : (239 + 174 + 83) % 10 = 6 := by
  sorry"""),
    Theorem("f2f_196_mathd_numbertheory_277", """theorem {name} (m n : ℕ) (h₀ : Nat.gcd m n = 6) (h₁ : Nat.lcm m n = 126) : 60 ≤ m + n := by
  sorry"""),
    Theorem("f2f_197_mathd_numbertheory_293", """theorem {name} (n : ℕ) (h₀ : n ≤ 9) (h₁ : 11∣20 * 100 + 10 * n + 7) : n = 5 := by
  sorry"""),
    Theorem("f2f_198_mathd_numbertheory_296", """theorem {name} (n : ℕ) (h₀ : 2 ≤ n) (h₁ : ∃ x, x^3 = n) (h₂ : ∃ t, t^4 = n) : 4096 ≤ n := by
  sorry"""),
    Theorem("f2f_199_mathd_numbertheory_299", """theorem {name} : (1 * 3 * 5 * 7 * 9 * 11 * 13) % 10 = 5 := by
  sorry"""),
]
