# ruff: noqa: E501, W291
"""
DeepSeek-Prover-V1 theorems imported for sheaf analysis.

Generated from 500 theorems.
"""
from corpus.lean.theorems import Theorem

DEEPSEEK_CORPUS: list[Theorem] = [
    Theorem("ds_0000_thm_1986", """theorem {name} (x : ℝ) (h₀ : (x ^ 3) ^ (1 / 3) + (x ^ 3) ^ (1 / 3) = 4 * (x ^ 3) ^ (1 / 3)) :
    x = 0 ∨ x = 1 / 14 ∨ x = -1 / 12 := by
  sorry"""),
    Theorem("ds_0001_thm_2253", """theorem {name} (m : ℤ) : m - (m / 2005 : ℤ) = 2005 ↔ m = 2006 := by
  sorry"""),
    Theorem("ds_0002_thm_3195", """theorem {name} (m : ℤ) (p : Polynomial ℤ) (h₀ : p = Polynomial.C 4 * Polynomial.X ^ 2 - Polynomial.C 6 * Polynomial.X + Polynomial.C m) (h₁ : Polynomial.aeval (3 : ℤ) p = 0) : m = -18 ∧ -18 ∣ 36 := by
  sorry"""),
    Theorem("ds_0003_thm_3390", """theorem {name} (x : ℝ) (h₀ : x ≥ 0) (h₁ : x < 1000) :
  let y₀ := x;
  let y₁ := x * 0.9;
  let y₂ := 200 + y₁;
  y₂ - y₀ = 100 ∧ y₁ - y₂ = 100 → y₀ = 300 ∧ y₁ = 270 ∧ y₂ = 250 := by
  sorry"""),
    Theorem("ds_0004_thm_1248", """theorem {name} : ¬ ∃ (n : ℕ), n > 0 ∧ (∀ (m : ℕ), m > 0 → m ≤ n → (m * (m + 1) / 2) % 7 = 0) := by
  sorry"""),
    Theorem("ds_0005_thm_4137", """theorem {name} (ABCD PQ : ℕ) (h₀ : 0 < ABCD) (h₁ : 0 < PQ)
    (h₂ : ABCD ≠ PQ) : (ABCD * 3 : ℕ) = PQ ↔ PQ = 3 * ABCD := by
  sorry"""),
    Theorem("ds_0006_thm_624", """theorem {name} (a b : ℤ) :
  let f := fun x => a * x^3 - 6 * x^2 + b * x - 5;
  f (1) % 5 = -5 ∧ f (-2) % 5 = -53 → (a, b) = (2, 4) := by
  sorry"""),
    Theorem("ds_0007_thm_3906", """theorem {name} (f : ℝ → ℝ) (a : ℝ) (h₀ : ∀ x, f x = (a * x ^ 2 + x - 1) / exp x)
  (h₁ : 0 < a) :
  ∀ x, 0 < x → x < 1 → f x = 0 →
  (∀ y, 0 < y → y < 1 → f y ≠ 0) →
  ∃! x, 0 < x ∧ x < 1 ∧ f x = 0 := by
  sorry"""),
    Theorem("ds_0008_thm_4928", """theorem {name} : 
  ∀ n : ℤ, n ≥ 2 → ∃ (h : ℤ → ℤ), (∀ n, n ≥ 2 → h n = (n - 2) / 3 + 2) ∧ h 1 = 1 := by
  sorry"""),
    Theorem("ds_0009_thm_1441", """theorem {name} :
  ∀ (a : ℕ → ℕ) (p : ℕ), a 1 = 1 → (∀ n, a (n + 1) = a n + p) → p = 2 →
  (∀ n, a n % 2 = 1) → ∀ n, a n = 2 * n - 1 := by
  sorry"""),
    Theorem("ds_0010_thm_1694", """theorem {name} : 
  ∃ (min_stamps : ℕ), (min_stamps = 9) ∧ ∀ (x y : ℕ), (3 * x + 4 * y = 33) → (x + y ≥ 9) := by
  sorry"""),
    Theorem("ds_0011_thm_4533", """theorem {name} : ∀ n : ℕ, n ≥ 2 → ∀ (s : Finset ℕ), (∀ x : ℕ, x ∈ s ↔ x ∈ Finset.Icc 0 (2 * n)) →
    s.card ≤ 2 * n → s.card ≤ 3 * n + 1 := by
  sorry"""),
    Theorem("ds_0012_thm_4785", """theorem {name} (n : ℕ) (h₀ : n > 0) :
    n - 2 ≥ (n / 2) - 1 := by
  sorry"""),
    Theorem("ds_0013_thm_52", """theorem {name} (a : ℝ) (f : ℝ → ℝ) (h₀ : ∀ x, f x = (Real.log x + a) / (x + 1)) :
    (∀ a > 2, ∃! x, f x = 0) → ∀ a > 2, ∃ x, f x = 0 → ∃ x₁, f x₁ = 0 → x₁ ≤ x → x ≤ x₁ → x₁ = x := by
  sorry"""),
    Theorem("ds_0014_thm_600", """theorem {name} (a b n : ℕ) (h₀ : 1 < a) (h₁ : 1 < b) (h₂ : n > 0) :
    let A_n := a ^ n;
    let B_n := b ^ n;
    let A_n_minus_one := a ^ (n - 1);
    let B_n_minus_one := b ^ (n - 1);
    let A_n_div_A_n_minus_one := A_n / A_n_minus_one;
    let B_n_div_B_n_minus_one := B_n / B_n_minus_one;
    (A_n_div_A_n_minus_one < B_n_div_B_n_minus_one) ∧ (B_n_div_B_n_minus_one < A_n_div_A_n_minus_one) →
    (a > b) := by
  sorry"""),
    Theorem("ds_0015_thm_751", """theorem {name} (a b : ℝ) (h₀ : a > b) (h₁ : b > 0) (h₂ : a^2 - b^2 = 13) (h₃ : 2 * a + 2 * b = 16) :
    let P := (a, b);
    let A := (a, 0);
    let B := (0, b);
    let T := (4, 0);
    let Q := (4, b);
    let R := (0, b);
    let S := (a, 0);
    let T := (4, 0);
    let U := (0, b);
    let V := (a, 0);
    let W := (4, b);
    let X := (a, b);
    let Y := (4, b);
    let Z := (a, b);
    let area_triangle_APQ := 1/2 * a * b;
    let area_triangle_BQR := 1/2 * a * b;
    let area_triangle_CRS := 1/2 * a * b;
    let area_triangle_DTS := 1/2 * a * b;
    let area_triangle_EUR := 1/2 * a * b;
    let area_triangle_FPQ := 1/2 * a * b;
    let area_triangle_GQR := 1/2 * a * b;
    let area_triangle_HRS := 1/2 * a * b;
    let area_triangle_IPQ := 1/2 * a * b;
    let area_triangle_JQR := 1/2 * a * b;
    area_triangle_APQ + area_triangle_BQR + area_triangle_CRS + area_triangle_DTS + area_triangle_EUR + area_triangle_FPQ + area_triangle_GQR + area_triangle_HRS + area_triangle_IPQ + area_triangle_JQR = 13 * a * b →
    a = 4 ∧ b = 3 →
    ∃ (P Q : ℝ), P + Q = 13 := by
  sorry"""),
    Theorem("ds_0016_thm_1483", """theorem {name} (x y : ℝ) (h₀ : y = (Real.sin x + Real.cos x) / (Real.exp x)) :
  ¬(∃ x : ℝ, ∃ y : ℝ, y = (Real.sin x + Real.cos x) / (Real.exp x) ∧ x = 0 ∧ y = -2) := by
  sorry"""),
    Theorem("ds_0017_thm_1678", """theorem {name} (h₀ : 20 = 2 * 2 * 5) :
    Nat.divisors 20 = {{1, 2, 4, 5, 10, 20}} →
    ∑ i in Finset.filter (fun x => Nat.Prime x) (Nat.divisors 20), i = 7 := by
  sorry"""),
    Theorem("ds_0018_thm_2535", """theorem {name} (a : ℝ) (f : ℝ → ℝ) (h₀ : ∀ x, f x = a / x - x + a * Real.log x)
  (h₁ : ∃ x₁ x₂, x₁ ≠ x₂ ∧ f x₁ = f x₂) :
  ∃ min_value, ∀ x₁ x₂, x₁ ≠ x₂ → f x₁ = f x₂ → f x₁ + f x₂ - 3 * a ≤ min_value →
    min_value = -Real.exp 2 := by
  sorry"""),
    Theorem("ds_0019_thm_2743", """theorem {name} (b : ℝ) :
  let f := fun x => b / (2 * x - 3);
  let f_inv := fun x => 3 * x / 2 + b / 2;
  f_inv 2 = f_inv 3 → b = -3 → f_inv 2 = -3 := by
  sorry"""),
    Theorem("ds_0020_thm_2949", """theorem {name} (a b : ℤ) (h : 3 ∣ a ∧ 6 ∣ b) : 3 ∣ b ∧ 3 ∣ (a - b) := by
  sorry"""),
    Theorem("ds_0021_thm_3001", """theorem {name} (a b c : ℝ) (h₀ : 0 < a) (h₁ : 0 < b) (h₂ : 0 < c) :
    let red_parabola := fun x => a * x ^ 2 + b * x + c;
    let red_parabola_vertex := -b / (2 * a);
    let red_parabola_vertex_y := red_parabola red_parabola_vertex;
    let red_parabola_vertex_x := red_parabola_vertex;
    let blue_parabola := fun x => a * x ^ 2 + b * x + c + 1;
    let blue_parabola_vertex := -b / (2 * a);
    let blue_parabola_vertex_y := blue_parabola blue_parabola_vertex;
    let blue_parabola_vertex_x := blue_parabola_vertex;
    red_parabola_vertex_y = 0 ∧ blue_parabola_vertex_y = 1 ∧ red_parabola_vertex_x = 0 ∧ blue_parabola_vertex_x = 1 →
    a + b + c = -15 / 2 := by
  sorry"""),
    Theorem("ds_0022_thm_3221", """theorem {name} (n : ℕ) (h₀ : 1 ≤ n) (h₁ : n ≤ 39) : 1990 = ∑ i in Finset.range n, 39 → n = 12 := by
  sorry"""),
    Theorem("ds_0023_thm_3350", """theorem {name} (a b : ℕ) (h₀ : 0 < a ∧ 0 < b)
    (h₁ : ∀ n : ℕ, 2 ≤ n ∧ n ≤ a → ∃ k : ℕ, n + k = a ∧ n + k = b) :
    ∃ k : ℕ, ∀ n : ℕ, 2 ≤ n ∧ n ≤ a → k = a + b := by
  sorry"""),
    Theorem("ds_0024_thm_3494", """theorem {name} (r : ℝ) (h₀ : r ≠ 0) :
    (∃ (a₂ a₃ : ℝ), a₂ = 1 * r ∧ a₃ = a₂ * r ∧ 4 * a₂ + 5 * a₃ = -4 / 5 ∧ r = -2 / 5) ∧
    (∃ (a₂ a₃ : ℝ), a₂ = 1 * r ∧ a₃ = a₂ * r ∧ 4 * a₂ + 5 * a₃ = -4 / 5 ∧ r = 2 / 5) →
    4 * r ^ 2 = 4 / 5 := by
  sorry"""),
    Theorem("ds_0025_thm_3505", """theorem {name} (a : ℝ) (f : ℝ → ℝ) (h₀ : ∀ x, f x = a / x - x + a * Real.log x)
  (h₁ : ∃ x₁ x₂, f x₁ = f x₂ ∧ x₁ ≠ x₂) :
  ∃ min_value, ∀ x₁ x₂, f x₁ = f x₂ → x₁ ≠ x₂ → f x₁ + f x₂ - 3 * a ≤ min_value →
  min_value = -e ^ 2 := by
  sorry"""),
    Theorem("ds_0026_thm_3653", """theorem {name} (α β : ℝ) (h₀ : 0 < α) (h₁ : 0 < β) (h₂ : α + β ≤ 1) (h₃ : (α / β ^ 2) ∈ Set.range (fun n => n : ℕ → ℝ)) :
    α = 2 ∧ β = 1 → (α / β ^ 2) ∈ Set.range (fun n => n : ℕ → ℝ) := by
  sorry"""),
    Theorem("ds_0027_thm_3656", """theorem {name} (a b : ℝ) (h₀ : a ≠ 0) (h₁ : b ≠ 0) :
  let f (x : ℝ) := a * x ^ 3 + b * x ^ 2 + 4 * x + 4;
  let g (x : ℝ) := f x - 2 * x;
  let h (x : ℝ) := g x + 3 * x;
  h 2 = 0 ∧ g 2 = 0 → a = 1 ∧ b = -4 := by
  sorry"""),
    Theorem("ds_0028_thm_3693", """theorem {name} (a : ℝ) (f : ℝ → ℝ) (h₀ : ∀ x, f x = a / x - x + a * Real.log x)
  (h₁ : ∃ x₁ x₂, x₁ ≠ x₂ ∧ f x₁ = f x₂) :
  ∃ min_value, ∀ x₁ x₂, x₁ ≠ x₂ → f x₁ = f x₂ → min_value = -Real.exp 2 := by
  sorry"""),
    Theorem("ds_0029_thm_3760", """theorem {name} (n : ℕ) (h₀ : n ≥ 100) : 
  (∀ (k : ℕ) (h₁ : k ≤ n), ∃ (m : ℕ), m^2 = k ∨ m^2 = k + 1) → 
  (∀ (k : ℕ) (h₁ : k ≤ n), ∃ (m : ℕ), m^2 = k ∨ m^2 = k + 1) → 
  ∃ (k : ℕ), k ≤ n ∧ ∃ (m : ℕ), m^2 = k ∨ m^2 = k + 1 := by
  sorry"""),
    Theorem("ds_0030_thm_4782", """theorem {name} (a : ℝ) (h₀ : a ≠ 0) :
    let f := fun x => a * Real.log (x + 1) + x ^ 2 / 2 - x;
    let x := -Real.sqrt (Real.exp 1) + 1;
    f x = -Real.log (1 + Real.sqrt 2) + 1 - Real.sqrt 2 ∧
    a = -1 →
    f x = -Real.log (1 + Real.sqrt 2) + 1 - Real.sqrt 2 := by
  sorry"""),
    Theorem("ds_0031_thm_4880", """theorem {name} (d : ℕ) (h₀ : d ∈ Set.Icc 0 9) :
  (∃ (n : ℕ), n = 100 * (d + 2) + 10 * d + 1 ∧ (n - 100 * d - 10 * d - 1) % 9 = 0) →
  (9 - d) % 10 = 8 := by
  sorry"""),
    Theorem("ds_0032_thm_993", """theorem {name} : 
  ∀ (a : ℝ) (f : ℝ → ℝ), 
    (∀ x, f x = x^2 - 2 * a * x + a + 2) → 
    (∀ x, f (-x) = -f x) → 
    (∀ x, f x ≠ 0) → 
    (∀ x, -1 ≤ x ∧ x ≤ 1 → f x = x) → 
    (∀ x, x^2 - 2 * a * x + a + 2 = x) → 
    (a ≤ -2 ∨ 2 ≤ a) := by
  sorry"""),
    Theorem("ds_0033_thm_3955", """theorem {name} : 
  let r := (8 : ℝ) / 9;
  r = 8 / 9 ∧ 
  (∃ m n : ℕ, m.gcd n = 1 ∧ r = m / n ∧ m + n = 17) := by
  sorry"""),
    Theorem("ds_0034_thm_4640", """theorem {name} (x : ℝ) (h₀ : 0 < x) :
    let f := fun x => (3 * x ^ 2 - 5 * x + 4) / (x ^ 2 - 3 * x + 2);
    f x = 3 ∧ f x = 7 / 2 → x = 1 ∨ x = 2 := by
  sorry"""),
    Theorem("ds_0035_thm_343", """theorem {name} : ¬ (∃ (choice : Fin 5 → Prop), choice 1 ∧ choice 2 ∧ choice 3 ∧ choice 4 ∧ choice 5 ∧ (∀ (i j : Fin 5), i ≠ j → choice i → choice j → False)) := by
  sorry"""),
    Theorem("ds_0036_thm_1548", """theorem {name} (a b c R : ℝ) (h₀ : R * (b + c) = a * Real.sqrt (b * c))
    (h₁ : a ^ 2 + b ^ 2 = c ^ 2) : a = n * Real.sqrt 2 ∧ b = n ∧ c = n ∧ n > 0 → n = 100 ∧ a = 100 * Real.sqrt 2 ∧ b = 100 ∧ c = 100 ∧ 0 < n := by
  sorry"""),
    Theorem("ds_0037_thm_3083", """theorem {name} (a b c h k : ℝ) (A : Type) [LinearOrderedCommRing A]
    (h₀ : a > 0 ∧ b > 0 ∧ c > 0) (h₁ : a < b + c) (h₂ : b < a + c) (h₃ : c < a + b)
    (h₄ : k > 0 ∧ h > 0) (h₅ : a + h > b + k) (h₆ : b + k > c + h) (h₇ : c + h > a + k) :
    a + h = b + k ↔ a = b ∧ h = k := by
  sorry"""),
    Theorem("ds_0038_thm_1672", """theorem {name} (R S T : ℝ) (h₀ : R = 4 / 3) (h₁ : T = 9 / 14) (h₂ : S = 3 / 7) :
    S = 30 → (R = Real.sqrt 48 → T = Real.sqrt 75) ∧ (T = Real.sqrt 75 → R = Real.sqrt 48) := by
  sorry"""),
    Theorem("ds_0039_thm_2349", """theorem {name} : ¬∃ (digits : List ℕ), (List.sum digits = 9) ∧ (List.length digits = 4) ∧
  (∀ d ∈ digits, d ≠ 5) ∧ (∃ d ∈ digits, d = 5) := by
  sorry"""),
    Theorem("ds_0040_thm_3019", """theorem {name} (x y z : ℤ) (h₀ : x + y = 12) (h₁ : x + z = 17) (h₂ : y + z = 19) :
  max x (max y z) = 12 := by
  sorry"""),
    Theorem("ds_0041_thm_3713", """theorem {name} (x y z : ℝ) (h₀ : x ≠ y ∧ y ≠ z ∧ x ≠ z) (h₁ : x * y * z = 0) (h₂ : x * y + y * z + z * x = 0) :
    x = 1 / 3 ∧ y = 1 / 3 ∧ z = 1 / 3 := by
  sorry"""),
    Theorem("ds_0042_thm_198", """theorem {name} : 
  (∀ n : ℕ, ∃ a b : ℕ, a > 0 ∧ b > 0 ∧ a ∣ n ∧ b ∣ n ∧ a * b = n) →
  (∀ a b : ℕ, a > 0 ∧ b > 0 → a ∣ b → ∃ n : ℕ, n > 0 ∧ a ∣ n ∧ b ∣ n) := by
  sorry"""),
    Theorem("ds_0043_thm_420", """theorem {name} (k : ℝ) (h₀ : k = 1 + Real.sqrt 5) :
    let a := 1;
    let b := 5;
    k = a + Real.sqrt b ∧ a ≠ 0 ∧ b ≠ 0 ∧ b > a ∧ b < 100 ∧ a + b = 6 := by
  sorry"""),
    Theorem("ds_0044_thm_500", """theorem {name} :
  ∀ a : ℝ, (∀ k : ℕ, 1 ≤ k ∧ k ≤ 2000 → a = k) → a = 927 := by
  sorry"""),
    Theorem("ds_0045_thm_549", """theorem {name} (x : ℝ) (h₀ : 0 < x) (h₁ : x < 180) :
  let angle_BAC := 2 * x;
  let angle_ABC := 2 * x;
  let angle_BCA := 180 - 2 * x;
  angle_BAC + angle_ABC + angle_BCA = 180 → x = 36 := by
  sorry"""),
    Theorem("ds_0046_thm_711", """theorem {name} (x : ℝ) :
  (x = 7.37) → (240 * x = 1764) →
  (∀ (a b c d : ℝ), (a * b * c * d = 1764) → (a = 7.37) → (b = 240) → (c = 1) → (d = 1)) := by
  sorry"""),
    Theorem("ds_0047_thm_761", """theorem {name} :
  let r := (3 + Real.sqrt 69) / 3;
  r = (3 + Real.sqrt 69) / 3 ∧ ∃ (a b c d : ℕ), a * b * c * d = 330 ∧ a + b + c + d = 332 →
  a = 1 ∧ b = 2 ∧ c = 3 ∧ d = 110 ∨ a = 1 ∧ b = 2 ∧ c = 5 ∧ d = 66 ∨ a = 1 ∧ b = 2 ∧ c = 11 ∧ d = 30 ∨
  a = 1 ∧ b = 5 ∧ c = 2 ∧ d = 33 ∨ a = 1 ∧ b = 5 ∧ c = 3 ∧ d = 22 ∨ a = 1 ∧ b = 5 ∧ c = 11 ∧ d = 18 ∨
  a = 2 ∧ b = 3 ∧ c = 2 ∧ d = 33 ∨ a = 2 ∧ b = 3 ∧ c = 5 ∧ d = 22 ∨ a = 2 ∧ b = 3 ∧ c = 11 ∧ d = 18 ∨
  a = 2 ∧ b = 5 ∧ c = 3 ∧ d = 22 ∨ a = 2 ∧ b = 5 ∧ c = 11 ∧ d = 18 ∨ a = 3 ∧ b = 5 ∧ c = 2 ∧ d = 22 ∨
  a = 3 ∧ b = 5 ∧ c = 11 ∧ d = 18 := by
  sorry"""),
    Theorem("ds_0048_thm_1048", """theorem {name} (x y : ℝ) (θ : ℝ) (h₀ : x = 2 * cos θ) (h₁ : y = 4 * sin θ) (t : ℝ) (h₂ : x = 1 + t * cos θ) (h₃ : y = 2 + t * sin θ) :
  t = -2 → x = 1 ∧ y = 2 → x = 1 + t * cos θ ∧ y = 2 + t * sin θ := by
  sorry"""),
    Theorem("ds_0049_thm_1278", """theorem {name} (k : ℝ) :
  let A := ((-4 : ℝ), 0);
  let B := (0, -4);
  let X := (0, 8);
  let Y := (14, k);
  let AB := ((A.1 + B.1) / 2, (A.2 + B.2) / 2);
  let XY := ((X.1 + Y.1) / 2, (X.2 + Y.2) / 2);
  AB = XY → k = -6 := by
  sorry"""),
    Theorem("ds_0050_thm_1381", """theorem {name} : ∀ (a b : ℕ) (b_ge_3 : 3 ≤ b) (a_mul_b_even : Even (a * b)),
    ∀ (k : ℕ) (k_lt_b : k < b), ∀ (contestants : Finset ℕ), contestants.card = a →
      (∀ c ∈ contestants, ∀ d, d < b → (c * d) % 2 = 0 → c ≤ k) →
      (∀ c ∈ contestants, ∀ d, d < b → (c * d) % 2 = 1 → c ≤ k) →
      k ≤ b - 1 := by
  sorry"""),
    Theorem("ds_0051_thm_1390", """theorem {name} (n : ℤ) (h₀ : 0 ≤ n) (h₁ : n ≤ 6) :
    (n + 4) % 6 = 0 ↔ n % 6 = 2 := by
  sorry"""),
    Theorem("ds_0052_thm_1440", """theorem {name} (b : ℝ) (h₀ : b > 0 ∧ b < 4) :
  let line_eq := fun x : ℝ => b - x;
  let x_axis_intersection := b;
  let y_axis_intersection := b - 4;
  let m := -1;
  let c := b;
  let slope_intercept_eqn := fun x : ℝ => m * x + c;
  let ratio_of_areas := (1 / 2) * slope_intercept_eqn x_axis_intersection * y_axis_intersection;
  ratio_of_areas = 9 / 25 → b = 2.5 := by
  sorry"""),
    Theorem("ds_0053_thm_1550", """theorem {name} (x₁ x₂ x₃ x₄ x₅ x₆ x₇ x₈ x₉ x₁₀ : ℝ) (d : ℝ) (h₀ : d < 0)
  (h₁ : x₁ = 1) (h₂ : x₂ = 2) (h₃ : x₃ = 3) (h₄ : x₄ = 4) (h₅ : x₅ = 5) (h₆ : x₆ = 6)
  (h₇ : x₇ = 7) (h₈ : x₈ = 8) (h₉ : x₉ = 9) (h₁₀ : x₁₀ = 10) :
  x₁^2 - x₂^2 + x₃^2 - x₄^2 + x₅^2 - x₆^2 + x₇^2 - x₈^2 + x₉^2 - x₁₀^2 = 10 →
  d = -1 := by
  sorry"""),
    Theorem("ds_0054_thm_1609", """theorem {name} (n : ℕ) (hn : n > 0) :
  ∀ (p : ℕ → Prop) (h₀ : ∀ k, p k ↔ (k > 0 ∧ k < n ∧ k % 2 = 1)),
    ¬(∀ k, p k → k % 2 = 0) → ∃ k, p k ∧ k % 2 = 1 := by
  sorry"""),
    Theorem("ds_0055_thm_1915", """theorem {name} (x : ℕ) (y₁ y₂ : ℕ) (h₀ : y₁ = 8 * x) (h₁ : y₂ = 4 * x + 120) :
    y₁ = y₂ ↔ x = 30 := by
  sorry"""),
    Theorem("ds_0056_thm_2340", """theorem {name} :
  let P : ℝ × ℝ := (1, 1);
  let A : ℝ × ℝ := (4, 0);
  let B : ℝ × ℝ := (0, 4);
  let Q : ℝ × ℝ := (P.1 * A.1 + P.2 * A.2, P.1 * B.1 + P.2 * B.2);
  let R : ℝ × ℝ := (Q.1 * A.1 + Q.2 * A.2, Q.1 * B.1 + Q.2 * B.2);
  R = (-9, -9) →
  (∃ r : ℝ, ∃ s : ℝ, r + s = 1) := by
  sorry"""),
    Theorem("ds_0057_thm_2723", """theorem {name} :
  let f (x : ℝ) := Real.log x + (a - 1) / x;
  let g (x : ℝ) := a * x - 3;
  let h (x : ℝ) := f x * g x;
  (∃ (a : ℝ), ∀ (x : ℝ), 2 * a ≥ h x) → ∃ (a : ℤ), ∀ (x : ℝ), 2 * a ≥ h x → a = 0 := by
  sorry"""),
    Theorem("ds_0058_thm_2734", """theorem {name} (a : ℝ) :
  let f := fun x : ℝ => a * x - 1 / x - (a + 1) * Real.log x;
  (∃ x : ℝ, 0 < x ∧ f x = 0) → (0 < a → a ≠ 0) := by
  sorry"""),
    Theorem("ds_0059_thm_2869", """theorem {name} (x : ℝ) (h₀ : 0 < x) :
  let total_capacity_before_add := 1 / 8 * x;
  let total_capacity_after_add := 1 / 8 * x + 7.5;
  let total_capacity_after_add_4 := 1 / 8 * x + 7.5 + 4;
  total_capacity_after_add_4 = 15 →
  total_capacity_after_add = 15 →
  total_capacity_before_add = 15 →
  x = 120 := by
  sorry"""),
    Theorem("ds_0060_thm_2941", """theorem {name} (n : ℕ) (P : ℝ → ℝ) (h₀ : ∀ x, P x = x ^ (n + 1) - (n + 1)) (h₁ : ∀ k : ℕ, k ≤ n → P (k / (k + 1)) = 0) (h₂ : P 1 = 1) : P (n / (n + 2)) = 1 / (n + 2) := by
  sorry"""),
    Theorem("ds_0061_thm_2955", """theorem {name} (M : ℤ) (h₀ : M * (M - 6) = -5) : M + 6 = 11 ↔ M = 5 := by
  sorry"""),
    Theorem("ds_0062_thm_3175", """theorem {name} : {{x | 0 ≤ x / (x + 3)}} = Set.Ici 0 ∪ {{0}} := by
  sorry"""),
    Theorem("ds_0063_thm_3176", """theorem {name} (T : ℕ) (u : ℕ → ℕ) (h₀ : T = 7) (h₁ : u 3 = 5) (h₂ : u 6 = 89)
    (h₃ : ∀ n ≥ 1, u (n + 2) = 3 * u (n + 1) - u n) : u T = 233 := by
  sorry"""),
    Theorem("ds_0064_thm_3238", """theorem {name} (P P' R R' D : ℕ) (h₀ : D = 25140)
  (h₁ : P ≡ P' [MOD D]) (h₂ : R ≡ R' [MOD D]) : P % D = P' % D ∧ R % D = R' % D := by
  sorry"""),
    Theorem("ds_0065_thm_3534", """theorem {name} (a b : ℝ) (h₀ : 0 < a) (h₁ : 0 < b) (h₂ : a^2 = 2) (h₃ : b^2 = 1) :
    (∀ x y : ℝ, (x^2 / a^2) + (y^2 / b^2) = 1) → (∀ x y : ℝ, (x^2 / 2) + y^2 = 1) := by
  sorry"""),
    Theorem("ds_0066_thm_4262", """theorem {name} (a : ℝ) (f : ℝ → ℝ) (h₀ : ∀ x, f x = if x ≤ 1 then -x ^ 2 + a * x + 1 else a * x)
    (h₁ : a = 1) : (∃ x, ∀ y, f x ≤ f y) → ∃ x, ∀ y, f x ≤ f y → x = -0.5 := by
  sorry"""),
    Theorem("ds_0067_thm_4297", """theorem {name} : ∃ a : ℤ, 0 < a ∧ ∀ x : ℤ, 0 < x → x^3 - a * x^2 + 78 * x - 2010 = 0 → a = 78 := by
  sorry"""),
    Theorem("ds_0068_thm_4365", """theorem {name} (a b : ℕ) (h₀ : a < 2012) (h₁ : b < 2012) (h₂ : a ≠ b) : 
  Nat.findGreatest (fun k : ℕ => (2012 / (k + 1) : ℝ) ≤ 48) 502 = 502 := by
  sorry"""),
    Theorem("ds_0069_thm_4604", """theorem {name} :
    10 * 8 * 18 = 15 * 12 * x ↔ x = 8 := by
  sorry"""),
    Theorem("ds_0070_thm_4643", """theorem {name} (x y : ℝ) (h₀ : x ≠ 0 ∧ y ≠ 0) (h₁ : x * y = 168)
    (h₂ : x + y = 42) (h₃ : x = 2 * y) : y = -49 := by
  sorry"""),
    Theorem("ds_0071_thm_4726", """theorem {name} (r P K : ℝ) (h₀ : r > 0)
  (h₁ : P > 0) (h₂ : K > 0) : 2 / r = P / K ↔ P / K = 2 / r := by
  sorry"""),
    Theorem("ds_0072_thm_4", """theorem {name} (N : ℕ)
  (h₀ : 22^2 * 55^2 = 10^2 * N^2) : N = 121 := by
  sorry"""),
    Theorem("ds_0073_thm_56", """theorem {name} (portia_students : ℕ) (lara_students : ℕ) (h₀ : portia_students = 3 * lara_students)
  (h₁ : portia_students + lara_students = 2600) : portia_students = 1950 ∧ lara_students = 650 := by
  sorry"""),
    Theorem("ds_0074_thm_103", """theorem {name} (n : ℕ) (h₀ : 0 < n) :
    ∃ (k : ℕ), ∃ (a : Fin k → ℕ), ∀ (i j : Fin k), i ≠ j → a i ≠ a j ∧ a i ≠ a j →
      k = 14 ∧ ∀ (i : Fin k), a i = 10 ∧ k = 14 → ∃ (j : Fin k), a j = 10 ∧ k = 14 := by
  sorry"""),
    Theorem("ds_0075_thm_121", """theorem {name} (n : ℕ) (h₀ : n > 2) :
  (3 * n ^ 2 + 2 * n + 1) = 1 * n ^ 3 + 1 * n ^ 2 + 2 * n →
  (1 * n ^ 3 + 1 * n ^ 2 + 2 * n) = 1 * n ^ 3 + 1 * n ^ 2 + 0 * n + 0 →
  (1 * n ^ 3 + 1 * n ^ 2 + 0 * n + 0) = 1 * n ^ 4 + 1 * n ^ 3 + 0 * n ^ 2 + 0 * n + 0 →
  n + 0 = 11 := by
  sorry"""),
    Theorem("ds_0076_thm_130", """theorem {name} (q : ℕ → ℤ) (a₀ : ∀ m n : ℕ, m > n ∧ n ≥ 0 → (m - n : ℤ) ∣ q m - q n)
    (a₁ : ∃ P : ℕ → ℤ, ∀ n : ℕ, (n : ℤ) ≤ P n) : ∃ Q : ℕ → ℤ, ∀ n : ℕ, q n = Q n := by
  sorry"""),
    Theorem("ds_0077_thm_243", """theorem {name} (A : ℝ) (f : ℝ → ℝ) (h₀ : ∀ x, f x = 2 * sin x * cos x + A * cos 2 * x) (h₁ : ∃ x, f x = 0) (h₂ : ∃ x, f x = Real.sqrt 2) (h₃ : ∃ x, f x = 2 * Real.sqrt 2) :
  ∃ m, ∀ x, 0 < x ∧ x < m → f x = 0 → m = 3 * Real.pi / 8 ∨ m = 7 * Real.pi / 8 := by
  sorry"""),
    Theorem("ds_0078_thm_332", """theorem {name} (A B : ℕ) (h₀ : A ≠ 0 ∧ B ≠ 0) :
  let sum := 9 * 10000 + 8 * 1000 + (A * 10 + 3) * 100 + 2 * 10 + B;
  sum = 98765 →
  B + A = 1 := by
  sorry"""),
    Theorem("ds_0079_thm_383", """theorem {name} (b : ℕ) (h₀ : b > 1) :
  let sum_of_digits := 2 * b + 4 + 5 * b + 7;
  sum_of_digits = 12 * b → b = 10 := by
  sorry"""),
    Theorem("ds_0080_thm_392", """theorem {name} : 
  (∀ n : ℕ, n > 0 → n^3 - 12 * n^2 + 40 * n - 29 ∈ Set.Icc (0 : ℕ) 1 → n = 2 ∨ n = 4) := by
  sorry"""),
    Theorem("ds_0081_thm_442", """theorem {name} (p : ℕ) (h₀ : p.Prime ∧ p > 3) : (p + 1) % 6 = 0 → p % 6 = 1 ∨ p % 6 = 5 := by
  sorry"""),
    Theorem("ds_0082_thm_469", """theorem {name} (f : ℝ → ℝ) (h₀ : ∀ x y, f (x ^ 2 - y ^ 2) = x * f x - y * f y) :
    (∀ x, f x = x * f 1) → (∀ x, f x = x * f 1) := by
  sorry"""),
    Theorem("ds_0083_thm_479", """theorem {name} (m b : ℝ) (h₀ : m = -1 / 2) (h₁ : b = 4 / 5) :
    m * b ∈ Set.Ioo (-1 : ℝ) 0 := by
  sorry"""),
    Theorem("ds_0084_thm_519", """theorem {name} :
  (∃ (p : ℝ), ∀ (x : ℝ), x ≥ 75 ∧ x < 85 → p = 0.5) ∧ (∃ (p : ℝ), ∀ (x : ℝ), x ≥ 85 ∧ x < 95 → p = 0.2) ∧
  (∃ (p : ℝ), ∀ (x : ℝ), x ≥ 95 ∧ x < 105 → p = 0.05) → (∃ (p : ℝ), ∀ (x : ℝ), x ≥ 75 ∧ x < 105 → p = 0.625) := by
  sorry"""),
    Theorem("ds_0085_thm_576", """theorem {name} (a b : ℝ) (h₀ : a * b = -7) (h₁ : a + b = -3) :
    (2 * a - 3) * (4 * b - 6) = -2 := by
  sorry"""),
    Theorem("ds_0086_thm_593", """theorem {name} (a b c : ℕ) (h₀ : a < 11) (h₁ : b < 11) (h₂ : c < 11) : 621 = 11^3 + a*11^2 + b*11 + c → a = 6 ∧ b = 2 ∧ c = 1 := by
  sorry"""),
    Theorem("ds_0087_thm_625", """theorem {name} (k : ℕ) (h₀ : k > 0) :
  let a := k^2 + 1;
  let b := k^2 + 2;
  let c := k^2 + 3;
  let d := k^2 + 4;
  let e := k^2 + 5;
  let f := k^2 + 6;
  let g := k^2 + 7;
  let h := k^2 + 8;
  let i := k^2 + 9;
  let j := k^2 + 10;
  a + b + c = k^3 + (k + 1)^3 ∧ d + e + f = k^3 + (k + 1)^3 ∧ g + h + i = k^3 + (k + 1)^3 ∧ j = k^3 + (k + 1)^3 →
  k = 1 ∨ k = 2 ∨ k = 3 ∨ k = 4 := by
  sorry"""),
    Theorem("ds_0088_thm_686", """theorem {name} (a b c : ℕ) (h₀ : a < 11) (h₁ : b < 11) (h₂ : c < 11) :
  let N := 11 ^ 2 * a + 11 * b + c;
  let base_8_representation := 1 * 8 ^ 2 + b * 8 + c;
  N = base_8_representation → N = 621 := by
  sorry"""),
    Theorem("ds_0089_thm_703", """theorem {name} (n j r : ℕ) (hn : n > 0) (hj : j > 0) (hr : r > 0) :
  let fj := fun n j r => min (n * r) j + min (j / r) n;
  let gj := fun n j r => min (n * r + 1) j + min (j / r + 1) n;
  fj n j r ≤ n^2 + n ∧ gj n j r ≥ n^2 + n → fj n j r ≤ gj n j r := by
  sorry"""),
    Theorem("ds_0090_thm_714", """theorem {name} (x y : ℝ) (h₀ : y = 16) (h₁ : x = 1) (h₂ : 5 * y = k / (x ^ 2)) : y = 1 / 4 → x = 8 := by
  sorry"""),
    Theorem("ds_0091_thm_806", """theorem {name} (u : ℝ) (h₀ : 0 < u ∧ u < 1) :
    ∀ n : ℕ, n ≥ 1 →
      let u_n := 1 + u * n;
      u_n > 1 := by
  sorry"""),
    Theorem("ds_0092_thm_908", """theorem {name} : ∃ (f : ℝ → ℝ), (∀ x, f x = x ^ 2 - 2) ∧ ∀ x, f x > 0 → x ∈ Set.Ioi 1 ∧ x ∈ Set.Iio 2 → x ∈ Set.Ioo 1 2 := by
  sorry"""),
    Theorem("ds_0093_thm_942", """theorem {name} (Diamond : ℝ → ℝ → ℝ) (h₀ : ∀ x y, x > 0 ∧ y > 0 → Diamond x y = x * y)
  (h₁ : ∀ x y, x > 0 ∧ y > 0 → Diamond (x * y) y = x * Diamond y y) (h₂ : ∀ x y, x > 0 ∧ y > 0 → Diamond x (x * y) = Diamond x x * y)
  (h₃ : ∀ x y, x > 0 ∧ y > 0 → Diamond (x * y) (x * y) = (x * y) * Diamond x y) :
  Diamond 19 98 = 19 → 19 * 98 = 1884 := by
  sorry"""),
    Theorem("ds_0094_thm_972", """theorem {name} (AB AC BC AN PM : ℝ) (h₀ : AN = PM) (h₁ : 0 < BC) (h₂ : BC ≠ 0)
    (h₃ : 0 < AC) (h₄ : AC ≠ 0) (h₅ : 0 < AB) (h₆ : AB ≠ 0) :
    (∀ x : ℝ, 0 < x → x ≠ 0 → BC = AC) → BC = AC := by
  sorry"""),
    Theorem("ds_0095_thm_1068", """theorem {name} (k : ℝ) :
  let f := (fun x => (Real.sin x) ^ 6 + (Real.cos x) ^ 6 + k * (Real.sin x) ^ 4 + k * (Real.cos x) ^ 4);
  let f_range := Set.range f;
  let k_sol := -7 / 100;
  k_sol = k ↔ k = -7 / 100 := by
  sorry"""),
    Theorem("ds_0096_thm_1069", """theorem {name} (x y : ℤ) (h₀ : x - y = 1) (K : ℤ) (h₁ : K = x^2 + x - 2 * x * y + y^2 - y) :
  K = 2 := by
  sorry"""),
    Theorem("ds_0097_thm_1074", """theorem {name} (n : ℕ) (h₀ : n = 2017) :
  ¬ (∃ l : ℕ, n = 2 * l ∧ (∀ k < n, (k : ℤ) / n ≤ (k + l) / n)) := by
  sorry"""),
    Theorem("ds_0098_thm_1175", """theorem {name} (x y : ℝ) (h₀ : (3 * x - 4) / (y + 15) = 1 / 9) (h₁ : y = 3) (h₂ : x = 2) : x = 7 / 3 → y = 12 := by
  sorry"""),
    Theorem("ds_0099_thm_1197", """theorem {name} : 
  (∃ (p : ℝ), ∀ (h₀ : 0 ≤ p) (h₁ : p ≤ 1),
    (p = 64 / 100) ∧ (1 - p = 36 / 100)) →
  ∃ (p : ℝ), ∀ (h₀ : 0 ≤ p) (h₁ : p ≤ 1),
    (p = 16 / 25) := by
  sorry"""),
    Theorem("ds_0100_thm_1209", """theorem {name} (a : ℝ) (f : ℝ → ℝ) (h₀ : ∀ x, f x = a / x - x + a * Real.log x)
  (h₁ : ∃ x₁ x₂, f x₁ = f x₂) :
  ∃ min_value, ∀ x₁ x₂, f x₁ = f x₂ → f x₁ + f x₂ - 3 * a ≥ min_value → min_value = -e ^ 2 := by
  sorry"""),
    Theorem("ds_0101_thm_1237", """theorem {name} (x : ℝ) (h₀ : x > 0) (h₁ : x ≠ 0) :
  let y := 8;
  let z := 10;
  let side_length_in_smallest_triangle := x;
  let side_length_in_largest_triangle := 25;
  side_length_in_smallest_triangle / side_length_in_largest_triangle = x / 25 ∧
  side_length_in_smallest_triangle / side_length_in_largest_triangle = y / 25 ∧
  side_length_in_smallest_triangle / side_length_in_largest_triangle = z / 25 →
  x = 25 := by
  sorry"""),
    Theorem("ds_0102_thm_1256", """theorem {name} (t : ℝ) (h₀ : 0 ≤ t) (h₁ : t ≤ 1) :
    let f := fun x => (20 - 2 * x) * (20 - 2 * x);
    let g := fun x => 0.1 * x + 0.2 * (x + 2) + 0.3 * (x + 4) + 0.1 * (x + 6) + t * (x + 8) + 2 * t * (x + 10);
    (∀ x, g x = f x) → g 25 = 625 → g 25 = 10.6 := by
  sorry"""),
    Theorem("ds_0103_thm_1370", """theorem {name} (N c : ℤ) (f : ℤ → ℤ) (h₀ : ∀ n, f n = if n ≤ 0 then 0 else n * f (n - 1) + (f (n - 1) ^ 2 + n ^ 2 - 1)) :
  (∃ n, f n = 0) ∧ (∃ n, n = 5) ∧ (∃ n, n = -231) ∧ N = 5 ∧ c = -231 → N + c = -226 := by
  sorry"""),
    Theorem("ds_0104_thm_1407", """theorem {name} (d : ℕ) (h₀ : 0 ≤ d ∧ d ≤ 9) :
  (2 * 10000 + 3 * 1000 + 4 * 100 + 5 * 10 + d) % 9 = 0 → d = 4 := by
  sorry"""),
    Theorem("ds_0105_thm_1475", """theorem {name} :
  let x := (1 : ℝ) + 4 / 5;
  (1 / 3) * x + 3.5 = (3 / 4) * x + 0.5 → x = 1.875 := by
  sorry"""),
    Theorem("ds_0106_thm_1476", """theorem {name} :
  Nat.choose 5 3 = 10 ∧ Nat.choose 5 4 = 5 → Nat.choose 5 2 = 10 := by
  sorry"""),
    Theorem("ds_0107_thm_1501", """theorem {name} (a : ℝ) (f : ℝ → ℝ) (h₀ : ∀ x, f x = a / x - x + a * Real.log x)
  (h₁ : ∃ x₁ x₂, f x₁ = f x₂ ∧ x₁ ≠ x₂) :
  ∃ min_value, ∀ x₁ x₂, f x₁ = f x₂ → x₁ ≠ x₂ → f x₁ + f x₂ - 3 * a ≤ min_value →
    min_value = -Real.exp 2 := by
  sorry"""),
    Theorem("ds_0108_thm_1515", """theorem {name} : 
  let a := (5 : ℝ);
  let b := (8 : ℝ);
  let c := (6 : ℝ);
  let d := (4 : ℝ);
  let e := (7 : ℝ);
  let f := (4 : ℝ);
  (a + (b * c) + d) / e = f → d = 6 := by
  sorry"""),
    Theorem("ds_0109_thm_1532", """theorem {name} (x m : ℤ)
    (h₀ : 4 * x^2 - 6 * x + m = 0)
    (h₁ : x = 3) : m = -18 ∧ -18 ∣ 36 := by
  sorry"""),
    Theorem("ds_0110_thm_1613", """theorem {name} (AB : ℝ) (BC : ℝ) (CA : ℝ) (h₀ : AB = 13) (h₁ : BC = 15) (h₂ : CA = 17) (h₃ : 0 < AB) (h₄ : 0 < BC) (h₅ : 0 < CA) :
  let D := (AB / 2 : ℝ);
  let E := (BC / 2 : ℝ);
  let F := (CA / 2 : ℝ);
  let p := (13 / 2 : ℝ);
  let q := (15 / 2 : ℝ);
  let r := (17 / 2 : ℝ);
  (p + q + r = 16) ∧ (p + q + r = 16) ∧ (p + q + r = 16) →
  (AB + BC + CA) / 2 = 21 := by
  sorry"""),
    Theorem("ds_0111_thm_1800", """theorem {name} (x y m : ℝ) (h₀ : x^2 / 4 + y^2 / 3 = 1) (h₁ : x = m * y + 1) :
  y = 0 → x = 2 := by
  sorry"""),
    Theorem("ds_0112_thm_1812", """theorem {name} : ∀ n : ℕ, (∃ (boxes : ℕ → Prop), ∀ i, boxes i → (∃ j, j ≠ i ∧ boxes j ∧ (∃ k, k ≠ i ∧ boxes k ∧ (j ≡ i + 1 [MOD n] ∨ j ≡ i - 1 [MOD n] ∨ k ≡ i + 1 [MOD n] ∨ k ≡ i - 1 [MOD n]))) → (n ≤ 6)) := by
  sorry"""),
    Theorem("ds_0113_thm_1848", """theorem {name} (t d : ℝ) (h₀ : t = 105) (h₁ : d = 105) (h₂ : t ≠ 0) (h₃ : d ≠ 0) :
    let speed_auto := 45;
    let speed_foot := 5;
    let time_tom_auto := t / 60;
    let distance_tom_auto := speed_auto * time_tom_auto;
    let time_dorthy_auto := d / speed_auto;
    let distance_dorthy_foot := speed_foot * time_dorthy_auto;
    distance_tom_auto - distance_dorthy_foot = 20 → t - d = 20 := by
  sorry"""),
    Theorem("ds_0114_thm_1855", """theorem {name} (n : ℕ) (h₀ : n > 0) :
  let a := 6 * 10 ^ n + 25;
  let b := a / 25;
  a * b = 2525 * 10 ^ n ∧ a % 10 = 6 → b % 10 = 4 := by
  sorry"""),
    Theorem("ds_0115_thm_1991", """theorem {name} (A : ℝ) (h₀ : 0 < A ∧ A < 180) (h₁ : ∀ A, sin A = 1 ∧ cos A = 0) :
    sin (A / 2) - Real.sqrt 3 * cos (A / 2) = -2 → A = -60 := by
  sorry"""),
    Theorem("ds_0116_thm_2039", """theorem {name} (p : ℝ) (h₀ : p > 0) :
  let C := {{x : ℝ × ℝ | x.1 ^ 2 = 2 * p * x.2}};
  let M := (1, 1);
  let tangent_line_slope := 1 / 2;
  ∃ (p : ℝ), p > 0 ∧ tangent_line_slope = 1 / 2 := by
  sorry"""),
    Theorem("ds_0117_thm_2081", """theorem {name} (m n : ℕ) (h₀ : Nat.gcd m n = 6) (h₁ : Nat.lcm m n = 126) :
    m = 6 ∧ n = 21 → m * n = 126 ∧ Nat.gcd m n = 6 ∧ ∀ k, Nat.gcd k (m * n) = 6 → k = 6 := by
  sorry"""),
    Theorem("ds_0118_thm_2082", """theorem {name} :
  let w := ![2, -1, 2];
  ∀ v : Fin 3 → ℝ, v 0 = 4 ∧ v 1 = -2 ∧ v 2 = 4 →
    let p : Fin 3 → ℝ := ![v 0 / 3, v 1 / 3, v 2 / 3];
    let q : Fin 3 → ℝ := ![2 * p 0 - v 0, 2 * p 1 - v 1, 2 * p 2 - v 2];
    q 0 = 18 ∧ q 1 = -18 ∧ q 2 = 18 →
    let r : Fin 3 → ℝ := ![p 0, p 1, p 2];
    r 0 = 4 ∧ r 1 = -2 ∧ r 2 = 4 := by
  sorry"""),
    Theorem("ds_0119_thm_2094", """theorem {name} (a : ℕ → ℤ) (h₀ : a 1 = -10) (h₁ : a 2 + 10 = 0) (h₂ : a 3 + 8 = 0) (h₃ : a 4 + 6 = 0)
    (h₄ : a 5 + 4 = 0) (h₅ : a 6 + 2 = 0) : a 6 = 2 ∧ n = 615 → a n = 2 * n - 12 := by
  sorry"""),
    Theorem("ds_0120_thm_2099", """theorem {name} (A B : Set ℝ) (h₀ : A = {{x | 1 ≤ x ∧ x ≤ 5}}) (h₁ : B = {{x | (x - a) * (x - 3) > 0}})
  (h₂ : Set.Icc 1 5 ⊆ A ∪ B) (h₃ : Set.Ioo 3 5 ⊆ B) (h₄ : a = 3) : a ∈ Set.Icc 1 5 := by
  sorry"""),
    Theorem("ds_0121_thm_2136", """theorem {name} (n : ℕ) (h₀ : 0 < n) :
  let F_n := 3 * n + 1;
  let F_n_plus_one := 3 * (n + 1) + 1;
  let F_n_plus_two := 3 * (n + 2) + 1;
  let F_n_plus_three := 3 * (n + 3) + 1;
  F_n + F_n_plus_one + F_n_plus_two + F_n_plus_three = 4 * (n + 2) →
  n = 92 := by
  sorry"""),
    Theorem("ds_0122_thm_2151", """theorem {name} : ∃ x : ℝ, (∀ y : ℝ, y = 9 * x - 3 * x + 1 → y ≥ 3 / 4) ∧ x = log 3 (1 / 2) := by
  sorry"""),
    Theorem("ds_0123_thm_2163", """theorem {name} (a : ℝ) :
  (∀ x : ℝ, x > 0 → (Real.log x + a) / (x + 1) = (Real.log 2 + a) / (2 + 1) → a = 1) →
  a = 1 := by
  sorry"""),
    Theorem("ds_0124_thm_2218", """theorem {name} :
  let seven_digit_numbers := Nat.descFactorial 9 7;
  let seven_digit_numbers_with_distinct_digits := 7 * 6 * 5 * 4 * 3 * 2 * 1;
  seven_digit_numbers = 840 → seven_digit_numbers_with_distinct_digits = 5040 →
  seven_digit_numbers - seven_digit_numbers_with_distinct_digits = 3600 := by
  sorry"""),
    Theorem("ds_0125_thm_2311", """theorem {name} (k : ℕ) (hk : k ≥ 2) :
    (∀ a₀ a₁ : ℤ, (∀ n : ℕ, n ≥ 1 → a₀ + a₁ = 0 ∧ a₀ * a₁ = 0 ∨ a₀ + a₁ ≠ 0 ∧ a₀ * a₁ ≠ 0) →
      k = 2) → k = 2 := by
  sorry"""),
    Theorem("ds_0126_thm_2411", """theorem {name} (M : ℝ) (m : ℝ) (h₀ : ∀ x : ℝ, 0 ≤ x → x ≤ 10 → 2 * x + 3 ≤ M)
    (h₁ : ∀ x : ℝ, 0 ≤ x → x ≤ 10 → 2 * x + 3 ≥ m) : M = 13 ∧ m = 3 / 2 → 3 / 2 ≤ M ∧ 3 / 2 ≥ m := by
  sorry"""),
    Theorem("ds_0127_thm_2424", """theorem {name} (m n : ℕ) (h₀ : m ≥ 2) (h₁ : n ≥ 2) :
    let score (x : ℕ) := x * (m - x);
    let max_score := m * (n - m);
    score 1 ≤ max_score ∧ score n ≤ max_score → score 1 + score n ≤ max_score + max_score := by
  sorry"""),
    Theorem("ds_0128_thm_2442", """theorem {name} :
  let Q (R : ℝ) := (R ^ 2 + R + 1) / (R ^ 2 + R + 1)
  let P (R : ℝ) := R ^ 2 + R + 1
  let f := fun R => P R / Q R
  ∀ R, f R = R ^ 2 + R + 1 → ∃ a b c d e f, a * R ^ 2 + b * R + c = d * R ^ 2 + e * R + f := by
  sorry"""),
    Theorem("ds_0129_thm_2499", """theorem {name} (x : ℤ) (h₀ : 0 ≤ x) (h₁ : x < 31) : 
  (∀ y : ℤ, 0 ≤ y ∧ y < 31 → x = y) → x = 2 := by
  sorry"""),
    Theorem("ds_0130_thm_2630", """theorem {name} : ∀ (a b : ℕ), (a = 3 ∧ b = 2) → 72 ∣ (a * 10000 + 6 * 1000 + 7 * 100 + 9 * 10 + b) := by
  sorry"""),
    Theorem("ds_0131_thm_2638", """theorem {name} (x : ℝ) :
    2 * x + 1 / x = 5 → 2 * (2 * x + 1 / x) + 2 * (1 / (2 * x + 1 / x)) = 2004 →
    2 * x + 1 / x = 601 := by
  sorry"""),
    Theorem("ds_0132_thm_2701", """theorem {name} (m b : ℝ) (h₀ : m + b = -7) :
  let line := fun x => m * x + b;
  line (-3) = 5 ∧ line 0 = -4 → m + b = -7 := by
  sorry"""),
    Theorem("ds_0133_thm_2702", """theorem {name} (m n : ℕ) (h₀ : m.Coprime n) (h₁ : n ≠ 0) (h₂ : n ≠ 1) :
    let area := 30;
    let x := 12;
    let y := 16;
    let height := m / n;
    let area_triangle := x * y * height / 2;
    area_triangle = area ∧ m.Coprime n → m + n = 41 := by
  sorry"""),
    Theorem("ds_0134_thm_2749", """theorem {name} : Nat.choose 1000 979 ≡ 0 [MOD 7] := by
  sorry"""),
    Theorem("ds_0135_thm_2784", """theorem {name} (n : ℕ) (h₀ : n < 10) : (8 * 1000000 + 5 * 100000 + 4 * 10000 + n * 1000 + 5 * 100 + 2 * 10 + 6) % 11 = 0 → n = 5 := by
  sorry"""),
    Theorem("ds_0136_thm_2837", """theorem {name} (a : ℕ) (r : ℕ) (h₀ : 0 < r) (h₁ : a = 7) (h₂ : a * r ^ 3 = 21) :
    a * r ^ 6 = 63 := by
  sorry"""),
    Theorem("ds_0137_thm_2848", """theorem {name} (k r : ℕ) (h₀ : k ≥ 66) (h₁ : r < 50) :
  let consumer_pays := 300 + (50 * k + r - 300) / 2;
  consumer_pays = 360 →
  50 * k + r = 720 := by
  sorry"""),
    Theorem("ds_0138_thm_2852", """theorem {name} (jones_age : ℕ) (h₀ : jones_age = 9) :
  ¬(∃ children : List ℕ, children.length = 8 ∧ List.Nodup children ∧ 5 ∈ children ∧ 11 ∣ jones_age * 100 + 5) := by
  sorry"""),
    Theorem("ds_0139_thm_2885", """theorem {name} (n : ℕ) (h₀ : 0 < n) :
  let perim_square := 56;
  let area_square := 100;
  let perim_polygon := 25 * n;
  let area_polygon := (n + 4) * 100 / n;
  perim_square = perim_polygon ∧ area_square = area_polygon → n = 100 := by
  sorry"""),
    Theorem("ds_0140_thm_2948", """theorem {name} : 
  (∀ (n : ℕ), n > 0 → ∃ (a : ℝ), a > 0 ∧ ∑ j in Finset.range n, a^(3*j) = (∑ j in Finset.range n, a)^2) →
  (∀ (n : ℕ), n > 0 → ∃ (a : ℝ), a > 0 ∧ ∑ j in Finset.range n, a^(3*j) = (∑ j in Finset.range n, a)^2 ∧ a = n) →
  (∃ (a : ℝ), a > 0 ∧ ∀ (n : ℕ), n > 0 → ∃ (b : ℝ), b > 0 ∧ ∑ j in Finset.range n, a^(3*j) = (∑ j in Finset.range n, b)^2 ∧ a = b) →
  ∃ (a : ℝ), a > 0 ∧ ∀ (n : ℕ), n > 0 → ∃ (b : ℝ), b > 0 ∧ ∑ j in Finset.range n, a^(3*j) = (∑ j in Finset.range n, b)^2 ∧ a = b → a = b := by
  sorry"""),
    Theorem("ds_0141_thm_3030", """theorem {name} (A B C D E F G H : ℝ) (h₀ : C = 5) (h₁ : ∀ x, x = A ∨ x = B ∨ x = C ∨ x = D ∨ x = E ∨ x = F ∨ x = G ∨ x = H) (h₂ : A + B + C = 30) (h₃ : B + C + D = 30) (h₄ : C + D + E = 30) (h₅ : D + E + F = 30) (h₆ : E + F + G = 30) (h₇ : F + G + H = 30) : A + H = 25 := by
  sorry"""),
    Theorem("ds_0142_thm_3047", """theorem {name} : ∀ p : ℕ, Nat.Prime p → p ∣ (2023 ^ (p ^ 2) + (p - 1) ! + 2 ^ (p ^ 4)) →
  ∑ i in Finset.filter (fun p : ℕ => Nat.Prime p) (Finset.range 5), i = 5 := by
  sorry"""),
    Theorem("ds_0143_thm_3059", """theorem {name} (n : ℕ) (h₀ : n = 2009) :
  ∃ (k : ℕ), ∀ (blue_edges : ℕ) (red_edges : ℕ) (white_edges : ℕ),
    blue_edges + red_edges + white_edges = n →
    ∃ (triangle : ℕ), triangle = 1 ∧
    ∀ (i : ℕ), i < triangle →
      ∃ (b : ℕ), b = blue_edges ∧
      ∃ (r : ℕ), r = red_edges ∧
      ∃ (w : ℕ), w = white_edges ∧
      b + r + w = n →
      k = 1 := by
  sorry"""),
    Theorem("ds_0144_thm_3148", """theorem {name} (n : ℕ) :
  let d (n : ℕ) := (Finset.filter (fun x => x ∣ n) (Finset.range (n + 1))).card;
  let a (n : ℕ) := d (n * 3 / 2);
  let b (n : ℕ) := d (n * 3 / 2) + 2011;
  ∀ n : ℕ, ∃ m : ℕ, a n = a m ∧ b n = b m → n = m := by
  sorry"""),
    Theorem("ds_0145_thm_3155", """theorem {name} (k : ℕ) (r s : ℝ) (h₀ : r ≠ s) (h₁ : r * s = (k : ℝ) ^ 2) (h₂ : r + s = -((k : ℝ) + 1)) (h₃ : r * s = (k : ℝ) + 2) :
    (r + 1) * (s + 1) = 2 := by
  sorry"""),
    Theorem("ds_0146_thm_3284", """theorem {name} (a : ℝ) (h₀ : a = 2 * 3 ^ 2 / 4) (h₁ : 0 < a) :
    (∀ x : ℝ, x ^ 2 * a + x * 3 + 2 = 0 → x = -2 ∨ x = -1 / 3) → 0 ≤ a := by
  sorry"""),
    Theorem("ds_0147_thm_3328", """theorem {name} (n : ℕ) (h₀ : n ≥ 2) :
    let M := (2 * n - 1);
    let N := Nat.succ (2 * (n - 2));
    let pairs := (Nat.choose (n - 1) 1) * (n - 1);
    M = pairs ∧ N = pairs → M = N + 1 := by
  sorry"""),
    Theorem("ds_0148_thm_3378", """theorem {name} :
  (∀ a b : ℝ, 0 < a → 0 < b → a ^ 2 + b ^ 2 = 1 → 4 * a ^ 2 + b ^ 2 = 4) →
  (∀ a b : ℝ, 0 < a → 0 < b → a ^ 2 + b ^ 2 = 1 → 4 * a ^ 2 + b ^ 2 = 4) →
  ∃ n : ℕ, ∀ a b : ℝ, 0 < a → 0 < b → a ^ 2 + b ^ 2 = 1 → 4 * a ^ 2 + b ^ 2 = 4 →
  n = 2 := by
  sorry"""),
    Theorem("ds_0149_thm_3401", """theorem {name} (x y : ℝ) (h₀ : 7 * x + 4 * y = 100) (h₁ : 5 * x + 6 * y = 100) :
    x = 15 / 2 ∧ y = 100 / 7 → x = 15 / 2 ∧ y = 100 / 7 ∧ 7 * x + 4 * y = 100 ∧ 5 * x + 6 * y = 100 := by
  sorry"""),
    Theorem("ds_0150_thm_3435", """theorem {name} (n : ℕ) (h₀ : n > 0) (h₁ : ∀ k : ℕ, k < n → ∃ a b : ℝ, a * b = 0 ∧ a + b = 1 ∧ a * a + b * b = 1) :
    ∃ (a b : ℝ), a * b = 0 ∧ a + b = 1 ∧ a * a + b * b = 1 := by
  sorry"""),
    Theorem("ds_0151_thm_3506", """theorem {name} (a b c : ℝ) (h₀ : b > c) (h₁ : b ≠ 0) (h₂ : c ≠ 0) (h₃ : a + b + c = 0) :
    (a + b + c)^2 / b^2 = 4 / 3 → a + c = -b / 3 := by
  sorry"""),
    Theorem("ds_0152_thm_3511", """theorem {name} (n : ℕ) (h₀ : n > 0) :
  let a := 10 ^ n + 6;
  let b := a / 25;
  b = 625 ∧ n = 4 → a % 10 + a / 10 % 10 + a / 100 % 10 = 15 := by
  sorry"""),
    Theorem("ds_0153_thm_3515", """theorem {name} (n : ℕ) (h₀ : 0 < n) (h₁ : n ≤ 9) :
  (10 ^ 85 - 1) / 9 * n = 8322 * (10 ^ 81 - 1) / 9 → n = 8322 := by
  sorry"""),
    Theorem("ds_0154_thm_3525", """theorem {name} (a b : ℝ) :
  (∀ x : ℝ, b * x = 3 * x + 4) → b ≠ 3 := by
  sorry"""),
    Theorem("ds_0155_thm_3589", """theorem {name} (p q : ℝ) :
  let B := (12, 19);
  let C := (23, 20);
  let A := (p, q);
  let BC_mid := ((B.1 + C.1) / 2, (B.2 + C.2) / 2);
  let AB_slope := ((B.2 - A.2) / (B.1 - A.1));
  let AD_slope := ((A.2 - C.2) / (A.1 - C.1));
  AB_slope = -5 ∧ AD_slope = -5 ∧ BC_mid = (17, 19) ∧ 70 = 70 → p + q = 47 := by
  sorry"""),
    Theorem("ds_0156_thm_3678", """theorem {name} (I : ℝ × ℝ) (h₀ : I = (2, 3)) :
  let M := (I.1 + I.2) / 2;
  let N := (I.1 - I.2) / 2;
  let x := I.1 - N;
  let y := I.2 + M;
  x = 3 ∧ y = 7 → x ^ 2 - y ^ 2 = -1 := by
  sorry"""),
    Theorem("ds_0157_thm_3708", """theorem {name} (n : ℕ) (h₀ : n ≥ 2) :
    let M := (2 * n - 1);
    let N := Nat.succ (2 * (n - 2));
    let pairs := (Nat.choose (n - 1) 1);
    M = pairs ∧ N = pairs → M = N + 1 := by
  sorry"""),
    Theorem("ds_0158_thm_3720", """theorem {name} (n : ℕ) (h₀ : n ≥ 4) (a₁ a₂ a₃ an : ℝ) (h₁ : a₁ < a₂) (h₂ : a₂ < a₃)
    (h₃ : a₁ < an) (h₄ : ∀ i, i < n → a₁ ≤ a₂) (h₅ : ∀ i, i < n → a₂ ≤ a₃) (h₆ : ∀ i, i < n → a₁ ≤ an) :
    (∀ r : ℝ, 0 < r ∧ r < 1 → ∃! h : ℕ, h < n) → ∃ h : ℕ, h < n := by
  sorry"""),
    Theorem("ds_0159_thm_3746", """theorem {name} :
  ∀ (A B C A1 B1 C1 : ℝ), 
  (A1B1 = 2 * A1C1) ∧ (B1C1 = 2 * A1B1) ∧ (A1B1 + A1C1 + B1C1 = P) →
  let hexagon_area := (97 : ℝ) / 4;
  let triangle_area := (9 : ℝ) / 2;
  hexagon_area ≥ triangle_area := by
  sorry"""),
    Theorem("ds_0160_thm_3771", """theorem {name} (S T : ℕ → ℕ) (hS : ∀ n : ℕ, S n = n ^ 2 + 2 * n) (hT : ∀ n : ℕ, T n = (3 ^ n)) :
    (S 2 = 6 ∧ T 2 = 9 ∧ S 4 = 20 ∧ T 4 = 81 ∧ S 8 = 66 ∧ T 8 = 6561) → (S 1000 = 2002 ∧ T 1000 = 3 ^ 1000) := by
  sorry"""),
    Theorem("ds_0161_thm_3792", """theorem {name} (n : ℕ) (h₀ : n > 0) :
  let f (C : ℕ → ℕ) := ∑ i in Finset.range n, C i;
  let f' (C : ℕ → ℕ) := ∑ i in Finset.range n, C (i + 1);
  let f'' (C : ℕ → ℕ) := ∑ i in Finset.range n, C (i + 2);
  ∀ C : ℕ → ℕ, f C ≤ f' C ∧ f' C ≤ f'' C → f C ≤ f'' C := by
  sorry"""),
    Theorem("ds_0162_thm_3832", """theorem {name} :
  (∀ n : ℕ, n > 0 → (n + 1)! + (n + 2)! = n! * 440 → n = 5 → ∑ i in Finset.range n, i % 10 = 10) := by
  sorry"""),
    Theorem("ds_0163_thm_3836", """theorem {name} (a : ℝ) (f : ℝ → ℝ) (h₀ : ∀ x, f x = a / x - x + a * Real.log x)
  (h₁ : ∃ x₁ x₂, f x₁ = f x₂ ∧ x₁ ≠ x₂) :
  ∃ min_value, ∀ x₁ x₂, f x₁ = f x₂ ∧ x₁ ≠ x₂ → min_value = -Real.exp 2 := by
  sorry"""),
    Theorem("ds_0164_thm_3910", """theorem {name} (x y : ℝ) (h₀ : x^2 * y = k) (h₁ : y = 10) (h₂ : x = 2) (h₃ : k ≠ 0) :
    x = 1/10 → y = 4000 := by
  sorry"""),
    Theorem("ds_0165_thm_3952", """theorem {name} (a b : ℕ) (h₀ : a + b = 120) (h₁ : a = b + 4) :
  a = 62 ∧ b = 58 := by
  sorry"""),
    Theorem("ds_0166_thm_4016", """theorem {name} (p q : ℕ) (h₀ : p.Prime ∧ q.Prime) (h₁ : Nat.Prime (p - q)) (h₂ : p ≠ 2 ∧ q ≠ 2)
    (h₃ : p ≠ q) (h₄ : p < 2 * q) (h₅ : q < 2 * p) (h₆ : p + q ≠ 0) (h₇ : p - q ≠ 0) (h₈ : p * q ≠ 0) :
    p + q = 64 → p - q = 1 → p * q = 63 → p = 17 ∧ q = 19 := by
  sorry"""),
    Theorem("ds_0167_thm_4056", """theorem {name} : ∀ (a b c d : ℤ), a - b + c = 5 ∧ b - c + d = 6 ∧ c - d + a = 3 ∧ d - a + b = 2 → a + b + c + d = 16 := by
  sorry"""),
    Theorem("ds_0168_thm_4090", """theorem {name} (Snake : Prop) (h : ¬Snake) : ¬∀ (Happy : Prop), Snake ↔ Happy := by
  sorry"""),
    Theorem("ds_0169_thm_4142", """theorem {name} (a b : ℝ) (h₀ : 0 < a) (h₁ : 0 < b) (h₂ : a > b) :
  let ellipse := fun x => (x ^ 2) / a ^ 2 + (x ^ 2) / b ^ 2 = 1;
  let center_of_ellipse := (0, 0);
  let e := (1 / 2 : ℝ);
  let a_prime := a * e;
  let m := (0 : ℝ);
  let n := (1 : ℝ);
  let P := (m, n);
  let Q := (m + a_prime, n);
  let R := (m - a_prime, n);
  let S := (m + a_prime / 2, n + (b * Real.sqrt 3) / 2);
  let T := (m - a_prime / 2, n + (b * Real.sqrt 3) / 2);
  (S = T) ↔ (1 = 7) ∨ (1 = 0) := by
  sorry"""),
    Theorem("ds_0170_thm_4173", """theorem {name} :
  ∀ n : ℕ, n > 0 → (2 * n - 1) ≤ 3 * n + 1 ∧ (2 * n - 1) ≤ 3 * n + 1 := by
  sorry"""),
    Theorem("ds_0171_thm_4235", """theorem {name} (a b c d : ℕ) (h₀ : a + b + c + d = 2009) :
    let f := fun x : ℕ => x ^ 4 + a * x ^ 3 + b * x ^ 2 + c * x + d;
    f 1 = 1 ∧ f 2 = 2 ∧ f 3 = 3 ∧ f 4 = 4 → d = 528 := by
  sorry"""),
    Theorem("ds_0172_thm_4267", """theorem {name} (n : ℕ) (h₀ : n ≥ 1) :
  let K := n * (n - 1);
  let L := K * 2;
  let M := K * 3;
  let N := K * 4;
  let O := K * 5;
  let P := K * 6;
  let Q := K * 7;
  let R := K * 8;
  let S := K * 9;
  let T := K * 10;
  let U := K * 11;
  let V := K * 12;
  let W := K * 13;
  let X := K * 14;
  let Y := K * 15;
  let Z := K * 16;
  let K' := K * 17;
  let L' := K' * 2;
  let M' := K' * 3;
  let N' := K' * 4;
  let O' := K' * 5;
  let P' := K' * 6;
  let Q' := K' * 7;
  let R' := K' * 8;
  let S' := K' * 9;
  let T' := K' * 10;
  let U' := K' * 11;
  let V' := K' * 12;
  let W' := K' * 13;
  let X' := K' * 14;
  let Y' := K' * 15;
  let Z' := K' * 16;
  L + M + N + O + P + Q + R + S + T + U + V + W + X + Y + Z = 45 → n = 5 := by
  sorry"""),
    Theorem("ds_0173_thm_4286", """theorem {name} (Snake : Prop) (h₀ : ¬Snake) : ¬∀ (Purple : Prop), Purple ↔ Snake := by
  sorry"""),
    Theorem("ds_0174_thm_4303", """theorem {name} (n : ℕ) (A : Finset ℕ) (h₀ : ∀ x : ℕ, x ∈ A ↔ x ∣ 20!) :
  ∃ (n : ℕ), ∃ (x : Finset ℕ), ∀ y : Finset ℕ, y ∈ Finset.powerset x →
    (∃ (z : ℕ), z ∣ 20! ∧ z ∣ (y.prod id) ∧ z ∣ (x.prod id)) →
    (y.prod id) = (x.prod id) →
    n = 418037760 := by
  sorry"""),
    Theorem("ds_0175_thm_4379", """theorem {name} (target_pads : ℕ) (h₀ : target_pads = 2023) :
  let jumps_required := target_pads - 1;
  let jumps_executed := jumps_required / 2;
  let remaining_pads := target_pads - jumps_executed;
  remaining_pads = 1011 → jumps_executed = 1011 := by
  sorry"""),
    Theorem("ds_0176_thm_4382", """theorem {name} (a₁ a₂ a₃ : ℝ) (h₀ : a₁ ≠ a₂) (h₁ : a₂ ≠ a₃) (h₂ : a₁ ≠ a₃) :
  let a := a₁; let b := a₂; let c := a₃;
  (a + b + c) / 3 = 5 / 2 ∧ (a + b + c) / 3 = 29 / 6 →
  a = 13 := by
  sorry"""),
    Theorem("ds_0177_thm_4440", """theorem {name} (a b c : ℕ) (h₀ : a ≠ 0) (h₁ : b ≠ 0) (h₂ : c ≠ 0) : 
  ∑ k in Finset.range 6, (if k = 0 then a else if k = 1 then b else c) = 237 → 
  (a * 6^2 + b * 6 + c) = 2^(2 * 1 + 2 * 0) → a + b + c = 237 := by
  sorry"""),
    Theorem("ds_0178_thm_4576", """theorem {name} (y x : ℝ) (h : y = k * x) (h₀ : k ≠ 0) (h₁ : k = 2) (h₂ : y = 8) (h₃ : x = 4) : y = -16 → x = -8 := by
  sorry"""),
    Theorem("ds_0179_thm_4588", """theorem {name} (x y : ℝ) (h₀ : 5 * y = k / x^2) (h₁ : k ≠ 0) (h₂ : y = 16) (h₃ : x = 1) :
    y = 1/4 → x = 8 := by
  sorry"""),
    Theorem("ds_0180_thm_4646", """theorem {name} (h : ∀ n : ℕ, 0 < n → ∃ a b : ℤ, a ^ 2 + b ^ 2 = n) :
  ∃ a b : ℤ, a ^ 2 + b ^ 2 = 72 := by
  sorry"""),
    Theorem("ds_0181_thm_4753", """theorem {name} (n : ℕ) (h₀ : 20 = 2 * n) : Nat.choose (2 * n) n = 2 ^ (2 * n - 1) → n = 10 := by
  sorry"""),
    Theorem("ds_0182_thm_4789", """theorem {name} (f : ℝ → ℝ) (h₀ : ∀ x y, f (x + f (x + y)) + f (x * y) = x + f (x + y) + y * f x) :
    (∃ f : ℝ → ℝ, ∀ x, f x = x) ∨ (∃ f : ℝ → ℝ, ∀ x, f x = 2 - x) := by
  sorry"""),
    Theorem("ds_0183_thm_4865", """theorem {name} (x : ℝ) (h₀ : x ∈ Set.Icc 0 12) :
  x * Real.sqrt (12 - x) + Real.sqrt (12 * x - x^3) ≥ 12 →
  (x = 3) → (x * Real.sqrt (12 - x) + Real.sqrt (12 * x - x^3) ≥ 12) := by
  sorry"""),
    Theorem("ds_0184_thm_12", """theorem {name} (n : ℕ) (h₀ : 201 ≤ n) :
    let f := fun k : ℕ => 201 + k;
    let f_inv := fun k : ℕ => k - 201;
    let count_f := fun k : ℕ => k + 1;
    let count_f_inv := fun k : ℕ => k + 1;
    count_f (f_inv (n - 201)) = 149 → count_f_inv (f (n - 201)) = 149 → n = 53 := by
  sorry"""),
    Theorem("ds_0185_thm_14", """theorem {name} (x y : ℝ) (h₀ : x = 6 ∨ x = 8 ∨ x = 10 ∨ x = 12 ∨ x = 14) (h₁ : y = 15 ∨ y = 18 ∨ y = 20 ∨ y = 24 ∨ y = 23) :
    x = 8 → y = 18 → 13 ≤ 100 * x - 10 * y ∨ 13 ≤ 100 * x - 10 * y + 100 * (x - 8) - 10 * (y - 18) := by
  sorry"""),
    Theorem("ds_0186_thm_16", """theorem {name} (n : ℕ) (h₀ : n ≥ 1) (h₁ : ∀ m, m ≥ n → m < 1000) :
  let shaded_square_first_column := 1 + (n - 1) * 2;
  let shaded_square_second_column := 2 * n;
  let shaded_square_third_column := 2 * n;
  shaded_square_first_column + shaded_square_second_column + shaded_square_third_column = 120 →
  n = 12 := by
  sorry"""),
    Theorem("ds_0187_thm_21", """theorem {name} :
  ∀ a : ℤ, a % 35 = 23 → a % 7 = 2 := by
  sorry"""),
    Theorem("ds_0188_thm_32", """theorem {name} (t : ℝ) :
  let x := 4 - 2 * t;
  let y := 0 + 6 * t;
  let z := 1 - 3 * t;
  let distance_squared := x ^ 2 + y ^ 2 + z ^ 2;
  distance_squared = 14 * t ^ 2 - 8 * t + 14 →
  t = 1 / 7 →
  distance_squared = 14 * t ^ 2 - 8 * t + 14 := by
  sorry"""),
    Theorem("ds_0189_thm_90", """theorem {name} (A B C : Fin 3 → ℝ) (MBC : Fin 3 → ℝ) (MAC : Fin 3 → ℝ) (MAB : Fin 3 → ℝ) (h₀ : ∀ i, MBC i = (A i + B i) / 2) (h₁ : ∀ i, MAC i = (A i + C i) / 2) (h₂ : ∀ i, MAB i = (B i + C i) / 2) (h₃ : ∀ i, A i ≠ 0) (h₄ : ∀ i, B i ≠ 0) (h₅ : ∀ i, C i ≠ 0) :
  (∃ M : Fin 3 → ℝ, ∀ i, M i = (A i + B i) / 2) := by
  sorry"""),
    Theorem("ds_0190_thm_113", """theorem {name} (n : ℤ) : n % 7 = 2 → (3 * n - 7) % 7 = 6 := by
  sorry"""),
    Theorem("ds_0191_thm_124", """theorem {name} (a b c : ℝ)
    (h₀ : Real.sqrt 3 * a = b * (Real.sin c + Real.sqrt 3 * Real.cos c))
    (h₁ : a = 2) (h₂ : b = 1) (h₃ : c = Real.pi / 3) :
    Real.sqrt 3 / 4 + 1 ≤ 5 / 4 + Real.sqrt 3 / 2 := by
  sorry"""),
    Theorem("ds_0192_thm_135", """theorem {name} :
    let decimal_value := (11 : ℚ) / 444;
    decimal_value = 25 / 999 →
    let numerator_denominator_sum := 11 + 444;
    numerator_denominator_sum = 349 := by
  sorry"""),
    Theorem("ds_0193_thm_156", """theorem {name} (n : ℕ) (h₀ : 0 < n)
    (h₁ : ∀ a : ℕ → ℕ, ∃ S : ℕ, ∀ m : ℕ, S = 2 * m + 1 → a m = S)
    (h₂ : ∀ a : ℕ → ℕ, ∃ T : ℕ, ∀ m : ℕ, T = 2 * m + 1 → a m = T) :
    ∃ b : ℕ → ℕ, ∀ m : ℕ, b m = 2 - (n + 1) / 2 ^ (n - 1) := by
  sorry"""),
    Theorem("ds_0194_thm_158", """theorem {name} (x a : ℝ) (h₀ : 9 * x ^ 2 + 24 * x + a = (3 * x + 4) ^ 2) :
    a = 16 := by
  sorry"""),
    Theorem("ds_0195_thm_167", """theorem {name} :
  ∀ (a d : ℝ) (n : ℕ),
    n ≥ 1 →
    let S := 10 * n + 30;
    let T := 10 * n - 30;
    let totalSum := S + T;
    totalSum = 10000 →
    n = 199 →
    let greatestTerm := 10 * n + 30;
    let leastTerm := 10 * n - 30;
    greatestTerm - leastTerm = 8080 / 199 →
    true := by
  sorry"""),
    Theorem("ds_0196_thm_182", """theorem {name} (n : ℕ) :
    ∀ (i : ℕ), i ≤ n → (2 * n - (n - i)) + 1 ≤ 3 * n + 1 := by
  sorry"""),
    Theorem("ds_0197_thm_195", """theorem {name} (m b : ℝ) (h₀ : m * 3 - 2 * b = 6) (h₁ : m * b = 2) (h₂ : b > 0) : 
  let line_eq := fun x y => m * x + b = y;
  let x_intercept := -b / m;
  x_intercept = 3 → m = -2 → b = 2 → line_eq 3 0 := by
  sorry"""),
    Theorem("ds_0198_thm_216", """theorem {name} (AB AC BC : ℝ) (h₀ : AB = 7) (h₁ : AC = 5) (h₂ : BC = 3) :
  let BD := 1;
  let AE := 1;
  let BP := 2;
  let PE := 1;
  let PD := 2;
  let DE := 1;
  let ABC_area := (1/2 : ℝ) * AB * AC;
  let ABP_area := (1/2 : ℝ) * AB * BP;
  let AEP_area := (1/2 : ℝ) * AE * PE;
  let AD_ratio := ABP_area / ABC_area;
  let BE_ratio := AEP_area / ABC_area;
  let DE_ratio := (ABC_area - ABP_area - AEP_area) / ABC_area;
  DE_ratio = 1 / 3 →
  DE = 1 / 3 := by
  sorry"""),
    Theorem("ds_0199_thm_220", """theorem {name} (a b c : ℝ) (h₀ : a • b = -3) (h₁ : a • c = 4) (h₂ : b • c = 6) :
  b • (7 * c - 2 * a) = 48 := by
  sorry"""),
    Theorem("ds_0200_thm_251", """theorem {name} (eden_buckets : ℕ) (mary_buckets : ℕ) (iris_buckets : ℕ) (total_sand : ℕ)
    (h₀ : eden_buckets = 4) (h₁ : mary_buckets = eden_buckets + 3) (h₂ : iris_buckets = mary_buckets - x)
    (h₃ : total_sand = 34) (h₄ : total_sand = eden_buckets * 2 + mary_buckets * 2 + iris_buckets * 2) :
    x = 1 := by
  sorry"""),
    Theorem("ds_0201_thm_278", """theorem {name} :
  ∃ k : ℕ, ∀ a b c : ℕ, a > 0 → b > 0 → c > 0 → a ≤ 7 → b ≤ 7 → c ≤ 7 → a ^ k = a → b ^ k = b → c ^ k = c → k = 1 := by
  sorry"""),
    Theorem("ds_0202_thm_299", """theorem {name} : Nat.factors 32 = [2, 2, 2, 2, 2] → 6 = (Finset.filter (fun n => 0 < n) (Finset.filter (fun n => 32 % n = 0) (Finset.range 33))).card := by
  sorry"""),
    Theorem("ds_0203_thm_327", """theorem {name} : 3240 = 2 ^ 4 * 3 ^ 4 * 5 ^ 1 * 7 ^ 1 →
  (Finset.filter (fun x => x % 3 = 0) (Nat.divisors 3240)).card = 32 := by
  sorry"""),
    Theorem("ds_0204_thm_347", """theorem {name} :
  let x : ℝ := 21 / 2;
  let y : ℝ := 7 / 2;
  x ^ 4 + y ^ 4 = 147 →
  (∑ i in Finset.range 21, (i ^ 4 + (21 - i) ^ 4)) = 147 := by
  sorry"""),
    Theorem("ds_0205_thm_367", """theorem {name} : ∀ {{T : ℤ}}, T = 40 → ∀ {{x y : ℤ}}, x + 9 * y = 17 → T * x + (T + 1) * y = T + 2 → 20 * x + 14 * y = 8 := by
  sorry"""),
    Theorem("ds_0206_thm_397", """theorem {name} (n : ℕ) (h : n > 0) :
  (1 / 4) ^ n * (2 ^ n - 1) = 0 := by
  sorry"""),
    Theorem("ds_0207_thm_421", """theorem {name} (x y : ℝ) (h₀ : x = -3) (h₁ : abs (x - 5) + abs (y - 2) = 10) :
    y = -32 → abs (x - 5) + abs (y - 2) = 10 := by
  sorry"""),
    Theorem("ds_0208_thm_436", """theorem {name} (eggsPablo : ℕ) (eggsSofia : ℕ) (eggsMia : ℕ) (h₀ : eggsPablo = 3 * eggsSofia)
  (h₁ : eggsSofia = 2 * eggsMia) :
  let PabloAfter := eggsPablo - (eggsPablo / 6);
  let MiaAfter := eggsMia + (eggsPablo / 6);
  let equal := PabloAfter = MiaAfter;
  equal → (eggsPablo / 6) = 1 / 6 := by
  sorry"""),
    Theorem("ds_0209_thm_438", """theorem {name} (n : ℕ) (h₀ : 0 < n) :
  let a := 2 * n;
  let b := n;
  let c := n;
  let d := 2 * n;
  let e := 2 * n;
  let f := n;
  let g := n;
  let h := 2 * n;
  let i := n;
  let j := n;
  let k := 2 * n;
  let l := n;
  let m := n;
  let n := 2 * n;
  let o := n;
  let p := n;
  let q := 2 * n;
  let r := n;
  let s := n;
  let t := 2 * n;
  let u := n;
  let v := n;
  let w := 2 * n;
  let x := n;
  let y := n;
  let z := 2 * n;
  a + b + c + d + e + f + g + h + i + j + k + l + m + n + o + p + q + r + s + t + u + v + w + x + y + z = 2000 →
  n = 8000 := by
  sorry"""),
    Theorem("ds_0210_thm_462", """theorem {name} (f : ℝ → ℝ) (h₀ : ∀ x : ℝ, f x = x ^ 2 - 6 * x + 13) :
  f (f 0) = 13 / 4 → f 0 = -32 / 9 := by
  sorry"""),
    Theorem("ds_0211_thm_474", """theorem {name} (miles_day1 : ℕ) (miles_day2 : ℕ) (miles_day3 : ℕ)
  (total_miles : ℕ) (h₀ : miles_day1 = 125) (h₁ : miles_day2 = 223) (h₂ : miles_day1 + miles_day2 + miles_day3 = total_miles)
  (h₃ : total_miles = 493) : miles_day3 = 145 := by
  sorry"""),
    Theorem("ds_0212_thm_487", """theorem {name} :
  let f x := x * (1 - x) / (x ^ 3 - x + 1);
  ∃ x₀ : ℝ, ∀ x : ℝ, 0 < x → x < 1 → f x ≤ f x₀ → x₀ = (Real.sqrt 2 + 1 - Real.sqrt (2 * 2 - 2 * Real.sqrt 2 - 1)) / 2 := by
  sorry"""),
    Theorem("ds_0213_thm_489", """theorem {name} (n : ℕ) (h₀ : 10 ≤ n) (h₁ : n ≤ 20) : 
  let f := fun n => 10 * n;
  f n = 144 → n = 144 := by
  sorry"""),
    Theorem("ds_0214_thm_494", """theorem {name} (a b c : ℝ) (h₀ : a * b * c = 1) (h₁ : a + b + c = 2)
  (h₂ : a * b + b * c + c * a = 1) : (a - 1) * (b - 1) * (c - 1) = 1 := by
  sorry"""),
    Theorem("ds_0215_thm_547", """theorem {name} (a b : ℝ) (h₀ : a ^ 2 + b ^ 2 = 65) (h₁ : 4 * a + 4 * b = 28) :
    max (a ^ 2 + b ^ 2) (4 * a + 4 * b) = 65 := by
  sorry"""),
    Theorem("ds_0216_thm_563", """theorem {name} (n : ℕ) (h₀ : 0 < n) (h₁ : n < 100) :
    let d := (n % 10) * 10 + (n / 10);
    let m := d * 10 + (n % 10);
    let q := m * 10 + (n % 10);
    q = 119 → n = 119 := by
  sorry"""),
    Theorem("ds_0217_thm_570", """theorem {name} (pA pB pC pD : ℚ) (hA : pA = 3/8) (hB : pB = 1/4) (hC : pC = x) (hD : pD = x)
    (h : pA + pB + pC + pD = 1) : x = 3/16 := by
  sorry"""),
    Theorem("ds_0218_thm_573", """theorem {name} (p q : ℝ → ℝ) (b : ℝ)
    (h₀ : ∀ x, p x = 2 * x - 7)
    (h₁ : ∀ x, q x = 3 * x - b)
    (h₂ : p (q 4) = 7) :
    b = 5 := by
  sorry"""),
    Theorem("ds_0219_thm_581", """theorem {name} (n : ℕ) (h₀ : n > 1) : ∀ k : ℕ, k > 0 → (⌊(n ^ k) / k⌋₊ % 2 = 1) → ∃ m : ℕ, m > 1 → (⌊(n ^ m) / m⌋₊ % 2 = 1) := by
  sorry"""),
    Theorem("ds_0220_thm_586", """theorem {name} (a b c : ℕ) (h₀ : 2 ^ 1001 - 1 = a) (h₁ : 2 ^ 1012 - 1 = b)
  (h₂ : Nat.gcd a b = c) : c = 2047 := by
  sorry"""),
    Theorem("ds_0221_thm_588", """theorem {name} (x a b : ℤ) (h₀ : x^2 - 16*x + 60 = (x - a) * (x - b))
  (h₁ : a > b) (h₂ : a * b = 60) (h₃ : a + b = 16) : 3 * b - a = 8 := by
  sorry"""),
    Theorem("ds_0222_thm_596", """theorem {name} (n : ℕ) (h₀ : 3 ∣ n) (h₁ : n % 3 = 0) (h₂ : n / 3 % 2 = 1) : n % 2 = 1 := by
  sorry"""),
    Theorem("ds_0223_thm_646", """theorem {name} (z : ℂ) (h₀ : z = 1 + 2 * Complex.I) :
    Complex.abs (z - 0) = 2 → Complex.abs (z - 0) ≤ 3 := by
  sorry"""),
    Theorem("ds_0224_thm_665", """theorem {name} (n : ℕ) (h₀ : 0 < n) :
  let stage1 := 2 * n + 1;
  let stage2 := 3 * n + 1;
  let stage3 := 6 * n + 1;
  let stage4 := 2 * n - 1;
  let stage5 := 6 * n - 1;
  let stage6 := 6 * n + 1;
  let stage7 := 2 * n + 1;
  let stage8 := 6 * n - 1;
  stage8 = 610 → n = 100 := by
  sorry"""),
    Theorem("ds_0225_thm_697", """theorem {name} : 
  ∀ (f : Fin 3 → ℕ) (h₀ : ∀ i, f i ∈ ({{1, 2, 3, 4, 5, 6}} : Finset ℕ)), 
  (∀ i, f i ≠ 0) → 
  (∀ i, f i ≠ 1) → 
  (∀ i, f i ≠ 2) → 
  (∀ i, f i ≠ 3) → 
  (∀ i, f i ≠ 4) → 
  (∀ i, f i ≠ 5) → 
  (∀ i, f i ≠ 6) → 
  ¬ (∀ i, f i = 1) → 
  ¬ (∀ i, f i = 2) → 
  ¬ (∀ i, f i = 3) → 
  ¬ (∀ i, f i = 4) → 
  ¬ (∀ i, f i = 5) → 
  ¬ (∀ i, f i = 6) → 
  (∃ i, f i = 4) := by
  sorry"""),
    Theorem("ds_0226_thm_709", """theorem {name} (m n : ℤ) : 
  let a := Real.sqrt (m^2 + n^2) + Real.sqrt ((3*m^2 + 3*n^2 - 6*m + 12*n + 15) : ℝ);
  a = Real.sqrt 5 → m^2 + n^2 = 25 → ∃ (m n : ℤ), m^2 + n^2 = 25 := by
  sorry"""),
    Theorem("ds_0227_thm_763", """theorem {name} (AB BC AC : ℝ) (h₀ : AB = 25) (h₁ : BC = 39) (h₂ : AC = 42) :
  let AD := 19;
  let AE := 14;
  let s := 19;
  let t := 14;
  let u := 12;
  let v := 9;
  let w := 6;
  let x := 3;
  let y := 2;
  let z := 1;
  AD * AE / (AB * AC) = s / t + u / v + w / x + y / z →
  AD * AE / (AB * AC) = 19 / 14 + 14 / 12 + 12 / 9 + 9 / 6 + 6 / 3 + 3 / 2 + 2 / 1 := by
  sorry"""),
    Theorem("ds_0228_thm_770", """theorem {name} (AB AC BC : ℝ) (h₀ : AB = 24) (h₁ : BC = 18) (h₂ : AC = 30) :
    let P := 6;
    let PD := 6;
    let PE := 3;
    let PF := 20;
    let ABC_area := (1/2 : ℝ) * AB * AC;
    let ABC_area_cut := (1/3 : ℝ) * ABC_area;
    let B_cut := (1/2 : ℝ) * BC;
    let A_cut := (1/2 : ℝ) * AB;
    let D := A_cut + B_cut;
    let D_to_E := (1/2 : ℝ) * D;
    let E_to_F := (1/2 : ℝ) * D;
    let B_to_F := B_cut - E_to_F;
    ABC_area_cut = B_cut * (A_cut + B_cut) / 2 →
    ABC_area_cut = (1/2 : ℝ) * B_to_F * (A_cut + B_to_F) →
    ABC_area_cut = 108 := by
  sorry"""),
    Theorem("ds_0229_thm_820", """theorem {name} (n : ℕ) (h₀ : n = 3) :
    let X := Finset.range 4;
    let Y := Finset.filter (fun x => x ≠ 0) X;
    let f : ℕ → ℕ := fun x => x + 3;
    Y.Nonempty → (∀ x ∈ Y, f x ∈ Finset.range 4) →
    (∀ x ∈ Y, ∀ y ∈ Y, x ≠ y → f x ≠ f y) →
    (∀ x ∈ Y, f x ∈ Finset.range 4) →
    (∀ x ∈ Y, ∀ y ∈ Y, x ≠ y → f x ≠ f y) →
    Y.card = 3 := by
  sorry"""),
    Theorem("ds_0230_thm_834", """theorem {name} (x : ℕ) (h₀ : x ≤ 60) :
  let season_days := 213;
  let fisherman1_rate := 3;
  let fisherman2_rate_first := 1;
  let fisherman2_rate_second := x;
  let fisherman2_rate_third := 4;
  let fisherman2_total_fish := (30 * fisherman2_rate_first + 60 * fisherman2_rate_second + (season_days - 90) * fisherman2_rate_third);
  let fisherman1_total_fish := season_days * fisherman1_rate;
  fisherman2_total_fish - fisherman1_total_fish = 3 → x = 2 := by
  sorry"""),
    Theorem("ds_0231_thm_836", """theorem {name} (k n : ℕ) (h₀ : k ≠ 0) (h₁ : n ≠ 0) :
    let game := fun (x : ℕ) (N : ℕ) => (x ≤ N) = (x ≤ N);
    game k (2 ^ k) → game n (2 ^ n) → n ≤ k → ∃ x : ℕ, game x (2 ^ k) → x ≤ k := by
  sorry"""),
    Theorem("ds_0232_thm_864", """theorem {name} (x y : ℝ) (h₀ : y = k * x) (h₁ : k = 2) (h₂ : y = 8) (h₃ : x = 4) : y = -16 ↔ x = -8 := by
  sorry"""),
    Theorem("ds_0233_thm_881", """theorem {name} (a : ℝ) : ∀ x, x ∈ Set.Icc (-2) 3 → 0 ≤ 4 + 2 * x := by
  sorry"""),
    Theorem("ds_0234_thm_919", """theorem {name} (n : ℕ) :
  (n % 5 = 3) → (2 * n % 5 = 1) := by
  sorry"""),
    Theorem("ds_0235_thm_959", """theorem {name} (a b : ℂ) (h₀ : a * b = 10) :
  a = -2 + 3 * Complex.I → b = 1 + Complex.I → a * b = 10 := by
  sorry"""),
    Theorem("ds_0236_thm_982", """theorem {name} :
  let f : ℕ → ℕ := fun x => x + 2;
  let s : Finset ℕ := Finset.image f (Finset.range 5);
  s.card = 3 →
  let n : ℕ := 5;
  Nat.choose n 3 = 10 := by
  sorry"""),
    Theorem("ds_0237_thm_1017", """theorem {name} (A : Set ℕ) (h₀ : A.Nonempty) (h₁ : ∀ x : ℕ, x ∈ A → x > 0)
  (h₂ : ∀ a b : ℕ, a ∈ A → b ∈ A → a + b ∈ A) (h₃ : ∀ a b : ℕ, a ∈ A → b ∈ A → a = b ∨ a + b ∈ A) :
  (∀ a b : ℕ, a ∈ A → b ∈ A → a = b ∨ a + b ∈ A) → ∃ (n : ℕ), n ∈ A := by
  sorry"""),
    Theorem("ds_0238_thm_1042", """theorem {name} :
  let single_discount := (1 - (10 / 100 : ℝ));
  let successive_discount := (1 - (20 / 100 : ℝ)) * (1 - (10 / 100 : ℝ));
  single_discount = successive_discount →
  100 * (1 - single_discount) = 28 := by
  sorry"""),
    Theorem("ds_0239_thm_1064", """theorem {name} (u : ℕ → ℤ) (T : ℕ) (h₀ : T = 7) (h₁ : u 3 = 5) (h₂ : u 6 = 89)
    (h₃ : ∀ n ≥ 1, u (n + 2) = 3 * u (n + 1) - u n) : u T = 233 := by
  sorry"""),
    Theorem("ds_0240_thm_1135", """theorem {name} (k : ℕ) (h₀ : k > 0) :
    let b (n : ℕ) := n ^ 2 - n + 1;
    (∀ n > 0, ∃ m, b m = k) → ∃ n > 0, b n = k → ∃ n > 0, b n = k := by
  sorry"""),
    Theorem("ds_0241_thm_1146", """theorem {name} (n : ℕ) (hn : n > 0) (h₀ : 3 ∣ 2 * n - 1) :
  let k := n / 3;
  let E := (2 * n - 1) / 3;
  k = E → n = 3 * k := by
  sorry"""),
    Theorem("ds_0242_thm_1154", """theorem {name} (z : ℤ) :
  let p := fun x => 3 * x^4 - 4 * x^3 + 5 * x^2 - 11 * x + 2;
  let q := fun x => 3 * x^2 + 4 * x + 2;
  let r := -17 / 3;
  p z / q z = r → z = -2 ∨ z = 1 ∨ z = -1 ∨ z = 2 → 
  (∑ i in Finset.Icc (-2) 2, if i ∈ Finset.Icc (-2) 2 then i else 0) = -17 / 3 := by
  sorry"""),
    Theorem("ds_0243_thm_1177", """theorem {name} :
  let chips := [(18, 1), (19, 1), (20, 1), (21, 1), (22, 1), (23, 1), (24, 1), (25, 1), (26, 1), (27, 1)];
  let sel_two := Nat.choose 9 2;
  let total := 2 ^ sel_two;
  total = 7786668 → sel_two = 36 := by
  sorry"""),
    Theorem("ds_0244_thm_1221", """theorem {name} (x : ℝ) (h₀ : 0 ≤ x) (h₁ : x ≤ 180) :
    let angle_BGC := 180 - x;
    let angle_AGC := x;
    let angle_BGC_ref := 180 - angle_BGC;
    angle_BGC_ref = 2 * angle_AGC →
    x = 340 →
    x = 340 := by
  sorry"""),
    Theorem("ds_0245_thm_1287", """theorem {name} :
  let approx_cubic_root_2 := (1 : ℚ) + (1 / 7 : ℚ);
  approx_cubic_root_2 ^ 3 = (1 : ℚ) + (1 / 7 : ℚ) + (1 / 9 : ℚ) →
  approx_cubic_root_2 ^ 3 ≤ (2400 : ℚ) := by
  sorry"""),
    Theorem("ds_0246_thm_1324", """theorem {name} (a : ℝ) (h₀ : 0 < a) (h₁ : 3 < a) :
    let C := 0;
    let F := (a - 3);
    let M := (a - 3) / 2;
    let N := (a - 3) / 2;
    let k := 1 / 2;
    (M - N) ^ 2 = 9 / 4 →
    a = 6 := by
  sorry"""),
    Theorem("ds_0247_thm_1325", """theorem {name} (n : ℕ) (h₀ : 0 < n) :
    let cards := (n + 1) ^ 2;
    let diagonal_moves := 2 * n - 1;
    diagonal_moves ≤ cards → ∃ moves : ℕ, moves ≤ cards ∧ moves ≥ diagonal_moves := by
  sorry"""),
    Theorem("ds_0248_thm_1332", """theorem {name} : ∀ n : ℤ, n % 7 = 2 → (3 * n - 7) % 7 = 6 := by
  sorry"""),
    Theorem("ds_0249_thm_1392", """theorem {name} (n : ℕ) (h₀ : n = 16) :
  let gallons_used := 26;
  let gallons_per_square_foot := 350;
  let total_square_feet := n * 18 * 10;
  gallons_per_square_foot * total_square_feet = gallons_used * 350 →
  n = 26 := by
  sorry"""),
    Theorem("ds_0250_thm_1396", """theorem {name} (p q : ℝ → ℝ) (h₀ : ∀ x, p x = 2 * x - 7) (h₁ : ∀ x, q x = 3 * x - b)
    (h₂ : p (q 4) = 7) : b = 5 := by
  sorry"""),
    Theorem("ds_0251_thm_1428", """theorem {name} (a : ℝ) :
  let f (x : ℝ) := x^3 + 2 * x + 1;
  let g (x : ℝ) := x - 1;
  let h (x : ℝ) := f (x) / g (x);
  h 1 = 3 / 2 →
  a = 3 / 2 := by
  sorry"""),
    Theorem("ds_0252_thm_1432", """theorem {name} (a₁ a₁₃ : ℚ) (d : ℚ)
  (h₀ : a₁ = 7 / 9) (h₁ : a₁₃ = 4 / 5)
  (h₂ : a₁₃ = a₁ + 12 * d) (h₃ : d = (a₁₃ - a₁) / 12) :
  a₁ + 6 * d = 71 / 90 := by
  sorry"""),
    Theorem("ds_0253_thm_1442", """theorem {name} (x : ℝ) (h₀ : x = 0) :
  let initial_profit_per_item := 40;
  let initial_items_sold_per_day := 20;
  let new_profit_per_item_below_x := initial_profit_per_item - x;
  let new_items_sold_per_day_below_x := initial_items_sold_per_day + 2 * x;
  let total_profit_below_x := new_profit_per_item_below_x * new_items_sold_per_day_below_x;
  total_profit_below_x = 1200 → x = 10 := by
  sorry"""),
    Theorem("ds_0254_thm_1464", """theorem {name} : 
  (∀ x : ℝ, x ∈ Set.Ioc 0 2 → x = 1 / x * (-x) + 2) → 
  (∀ x : ℝ, x ∈ Set.Ioc 0 2 → x ∈ Set.Ioc 0 2) := by
  sorry"""),
    Theorem("ds_0255_thm_1499", """theorem {name} :
    let X := 100;
    let Y := 1000;
    let x := X.digits 10;
    let y := Y.digits 10;
    let x_sum := x.sum;
    let y_sum := y.sum;
    x_sum = 10000 → y_sum = 100000 → (x_sum * y_sum) % 100 = 0 := by
  sorry"""),
    Theorem("ds_0256_thm_1528", """theorem {name} (m n : ℕ) (h₀ : m ≤ n) (h₁ : n ≤ 1000) :
    let total_length := 2007;
    let area_difference := 1;
    let basic_rectangle_length := 4;
    let basic_rectangle_width := 5;
    let n_basic_rectangles := m;
    let total_area := n_basic_rectangles * (basic_rectangle_length * basic_rectangle_width);
    total_area = total_length →
    m = 896 := by
  sorry"""),
    Theorem("ds_0257_thm_1538", """theorem {name} :
  ∀ n : ℕ, 2018 ≤ n → ∀ circles : ℕ, circles = n →
    ∀ vertices : ℕ, vertices = 2 * circles →
      ∀ red : ℕ, red = circles / 2 →
      ∀ blue : ℕ, blue = circles / 2 →
        ∀ yellow : ℕ, yellow = circles - red - blue →
          yellow ≤ 2061 := by
  sorry"""),
    Theorem("ds_0258_thm_1563", """theorem {name} (a : ℝ) (h : 0 < a) :
  let f := fun x => x^3 - a * x^2 - a^2 * x + 1;
  let m := 1 - a * (-a) - a^2 * (-a);
  let g := fun x => x * (1 - a * x - a^2);
  let h := fun x => x^2 * (1 - a * x);
  let k := fun x => x * (1 - a^2 * x);
  let l := fun x => x * (1 - a^2 * x);
  f (-a) = 1 → m = 1 - a * (-a) - a^2 * (-a) → g (-a) = 0 → h (-a) = 0 → k (-a) = 0 → l (-a) = 0 →
  m + 1 / a = 1 + 4 * Real.sqrt 3 / 3 := by
  sorry"""),
    Theorem("ds_0259_thm_1567", """theorem {name} (r : ℝ) (h₀ : 0 < r) (h₁ : r < 1) : Nat.floor (100 * r) = 743 → r = 743 / 100 → Nat.floor (100 * r) = 743 := by
  sorry"""),
    Theorem("ds_0260_thm_1614", """theorem {name} : 
  let S := Finset.range 101;
  let f (s : ℕ) := s^2 + 2*s + 1;
  let ok (k : ℕ) := ∃ s ∈ S, f s = k;
  ok 100 → 98 ≤ 100 → ∃ k ∈ Finset.range 101, ok k := by
  sorry"""),
    Theorem("ds_0261_thm_1635", """theorem {name} (d : ℤ) (h₀ : d > 0) (n : ℕ) (h₁ : n % 2 = 1) (t₀ : ℤ) (h₂ : t₀ = 302) (t₃ : ℤ) (h₃ : t₃ = 296) (t₁ : ℤ) (h₄ : t₁ = t₀ - d) (t₂ : ℤ) (h₅ : t₂ = t₃ - d) (h₆ : t₁ - t₂ = 2 * d) :
    d = 3 := by
  sorry"""),
    Theorem("ds_0262_thm_1645", """theorem {name} (x : ℝ) (h₀ : (x^4 + x + 5) * (x^5 + x^3 + 15) = x^9 + x^7 + 20 * x^6 + 50 * x^5 + 100 * x^4 + 150 * x^3 + 100 * x^2 + 20 * x + 75) :
  x^4 + x + 5 = 0 → x^5 + x^3 + 15 = 0 → x^9 + x^7 + 20 * x^6 + 50 * x^5 + 100 * x^4 + 150 * x^3 + 100 * x^2 + 20 * x + 75 = 0 := by
  sorry"""),
    Theorem("ds_0263_thm_1648", """theorem {name} (a : ℕ → ℕ) (S : ℕ → ℕ) (h₀ : ∀ n, a n = 2 ^ n) (h₁ : ∀ n, S n = ∑ k in Finset.range n, a k) (b : ℕ → ℕ) (h₂ : ∀ n, b n = (Real.log 2 * Real.log (2 ^ n)) / Real.log 2) :
  (∀ n, a n = 2 ^ n) → (∀ n, S n = ∑ k in Finset.range n, a k) → (∀ n, b n = (Real.log 2 * Real.log (2 ^ n)) / Real.log 2) →
  (∃ T : ℕ → ℕ, ∀ n, T n = 2 - (n + 1) / 2 ^ (n - 1)) := by
  sorry"""),
    Theorem("ds_0264_thm_1661", """theorem {name} (n k m : ℕ) (h₀ : k ≥ 2) (h₁ : n ≤ m) (h₂ : m < (2 * k - 1) * n) :
    (∀ A : Finset ℕ, ∀ x ∈ Finset.range (m + 1), x ∈ A → A.card = n → ∃ a ∈ A, ∃ a' ∈ A, a - a' ∈ Finset.range (n + 1)) := by
  sorry"""),
    Theorem("ds_0265_thm_1685", """theorem {name} (x y z : ℕ) (h₀ : x + y + z = 99) (h₁ : x = 4 * y) (h₂ : y = 2 * z) : y = 18 := by
  sorry"""),
    Theorem("ds_0266_thm_1690", """theorem {name} (a b : ℝ) (h₀ : a / b + a / b ^ 2 + a / b ^ 3 + a / b ^ 4 = 4) :
    a / (a + b) + a / (a + b) ^ 2 + a / (a + b) ^ 3 + a / (a + b) ^ 4 = 4 / 5 → b = 0 → a = 0 := by
  sorry"""),
    Theorem("ds_0267_thm_1725", """theorem {name} (T : ℕ) (h₀ : T = 49) :
    (∑ i in Finset.range 50, (i * T) ^ 2) % 10 = 5 := by
  sorry"""),
    Theorem("ds_0268_thm_1733", """theorem {name} (x y : ℝ) (h₀ : 5 * y = k / x^2) (h₁ : y = 16) (h₂ : x = 1) :
  y = 1/4 → x = 8 := by
  sorry"""),
    Theorem("ds_0269_thm_1735", """theorem {name} (x : ℝ) (h : 0 < x) (h₀ : x = 1000) :
  let n : ℕ := 5;
  let p : ℝ := 0.01;
  (1 + p) ^ n * x = 1512.1 → x = 1512.1 := by
  sorry"""),
    Theorem("ds_0270_thm_1749", """theorem {name} (a : ℤ) : a % 35 = 23 → a % 7 = 2 := by
  sorry"""),
    Theorem("ds_0271_thm_1751", """theorem {name} (x₁ y₁ x₂ y₂ : ℝ)
  (h₀ : x₁ = 2) (h₁ : y₁ = 5) (h₂ : x₂ = -6) (h₃ : y₂ > 0) (h₄ : (y₂ - y₁) ^ 2 + (x₂ - x₁) ^ 2 = 10 ^ 2) :
  y₂ = 11 := by
  sorry"""),
    Theorem("ds_0272_thm_1817", """theorem {name} (V : ℝ) (h₀ : V = (1 / 6) * 7 ^ 2 * 8) :
  V = 343 / 3 →
  let s := 7;
  let h := 8;
  let area_ABCD := s * h;
  let volume_ABCD := area_ABCD * V;
  volume_ABCD = 343 * V := by
  sorry"""),
    Theorem("ds_0273_thm_1825", """theorem {name} :
    let bananas := 10;
    let oranges := 8;
    let bananas_worth_oranges := 5;
    let half_bananas_worth_oranges := (5 / 2 : ℚ);
    (2 / 3 : ℚ) * bananas * half_bananas_worth_oranges = oranges → 1 / 2 * bananas * bananas_worth_oranges = 3 * oranges := by
  sorry"""),
    Theorem("ds_0274_thm_1916", """theorem {name} (a b : ℤ) (h₀ : a = 3 ^ 1001 + 4 ^ 1002) (h₁ : b = 3 ^ 1001 - 4 ^ 1002) :
    a ^ 2 - b ^ 2 = 16 * 12 ^ 1001 := by
  sorry"""),
    Theorem("ds_0275_thm_1978", """theorem {name} (a b c : ℝ) (h₀ : a + b + c = 0) (h₁ : a * b + b * c + c * a = 0)
  (h₂ : a * b * c = -4) : a ^ 2 * b ^ 2 * c ^ 2 = 16 := by
  sorry"""),
    Theorem("ds_0276_thm_2047", """theorem {name} (P : ℝ → ℝ → ℝ → ℝ)
    (h₀ : ∀ x y z, P x y z = P x z y) (h₁ : ∀ x y z, P x y z = P y x z)
    (h₂ : ∀ x y z, P x y z = P z x y) (h₃ : ∀ x y z, P x y z = P y z x)
    (h₄ : ∀ x y z, P x y z = P z y x) (h₅ : ∀ x y z, P x y z = P x z y) (h₆ : ∀ x y z, P x y z = P y x z)
    (h₇ : ∀ x y z, P x y z = P z x y) (h₈ : ∀ x y z, P x y z = P y z x)
    (h₉ : ∀ x y z, P x y z = P z y x) : ∃ F : ℝ → ℝ, ∀ t, P 1 1 1 = F t := by
  sorry"""),
    Theorem("ds_0277_thm_2063", """theorem {name} :
    let f : ℕ → ℕ := fun n ↦ n;
    let pow : ℕ → ℕ := fun n ↦ n * n;
    let prod : ℕ → ℕ := fun n ↦ n * (n + 1) * (n + 2) * (n + 3) * (n + 4) * (n + 5) * (n + 6) * (n + 7) * (n + 8) * (n + 9);
    (∀ n : ℕ, f (pow n) ∣ prod n) → ∃ m : ℕ, 2010 = pow m → m = 77 := by
  sorry"""),
    Theorem("ds_0278_thm_2074", """theorem {name} (current_scores : List ℕ) (next_score : ℕ)
    (h₀ : current_scores = [90, 80, 70, 60, 85]) (h₁ : (current_scores.sum + next_score) / (current_scores.length + 1) -
      current_scores.sum / current_scores.length ≥ 3) : next_score ≥ 95 := by
  sorry"""),
    Theorem("ds_0279_thm_2117", """theorem {name} (n : ℕ) :
  let files_08 := 3;
  let files_07 := 12;
  let files_04 := 25 - files_08 - files_07;
  let disks_capacity := 1.44;
  let disk_size := 0.8;
  let total_files := files_08 + files_07 + files_04;
  total_files ≤ disks_capacity / disk_size → 13 ≤ n →
  n ≤ 13 → ∃ n, n ≤ 13 ∧ total_files ≤ disks_capacity / disk_size := by
  sorry"""),
    Theorem("ds_0280_thm_2169", """theorem {name} (a : ℤ) (h₀ : a % 35 = 23) : a % 7 = 2 := by
  sorry"""),
    Theorem("ds_0281_thm_2310", """theorem {name} :
    let M := {{p : ℝ × ℝ | p.snd ≥ 1 / 4 * p.fst ^ 2}};
    let N := {{p : ℝ × ℝ | p.snd ≤ -1 / 4 * p.fst ^ 2 + p.fst + 7}};
    let D := fun p : ℝ × ℝ => (p.fst - 2) ^ 2 + (p.snd - 1) ^ 2;
    let r := Real.sqrt (25 - 5 * Real.sqrt 5) / 2;
    ∀ p : ℝ × ℝ, p ∈ M ∩ N → ∃ r, D p = r → r = Real.sqrt (25 - 5 * Real.sqrt 5) / 2 := by
  sorry"""),
    Theorem("ds_0282_thm_2527", """theorem {name} :
  (∀ T : Finset (Fin 2 → ℤ), ∃ (n : ℕ), ∀ (d : Fin 2 → ℤ), d ∈ T → n ≤ (Finset.filter (fun x : Fin 2 → ℤ => x ≠ d) T).card) →
  (∀ T : Finset (Fin 2 → ℤ), ∃ (n : ℕ), ∀ (d : Fin 2 → ℤ), d ∈ T → n ≤ (Finset.filter (fun x : Fin 2 → ℤ => x ≠ d) T).card) := by
  sorry"""),
    Theorem("ds_0283_thm_2687", """theorem {name} : ∀ {{Q R : ℝ}}, (∀ {{P : ℝ}}, P ≠ Q → P ≠ R → ∃ x, x * (P - Q) + x * (P - R) = 2 * P - (Q + R)) →
    ∃ x, x * (29 - 59) + x * (29 - 63) = 2 * 29 - (59 + 63) → 58 * x = -864 → x = (-432 / 29 : ℝ) := by
  sorry"""),
    Theorem("ds_0284_thm_2745", """theorem {name} (p_A : ℝ) (p_B : ℝ) (h₀ : p_A = 0.8) (h₁ : p_B = 0.8) :
    p_A * 3 > p_B * 2 := by
  sorry"""),
    Theorem("ds_0285_thm_2786", """theorem {name} (a₁ d : ℤ) (h₀ : a₁ = -28) (h₁ : d = 4) (h₂ : a₁ + (n - 1) * d = 0) :
    n = 8 := by
  sorry"""),
    Theorem("ds_0286_thm_2817", """theorem {name} (a : ℕ → ℝ) (S : ℕ → ℝ) (h₀ : ∀ n, S n = n * (a 1 + a n) / 2)
  (h₁ : ∀ n, a n = 2 * n - 1) (h₂ : S 1 = 1) (h₃ : S 2 = 4) (h₄ : S 4 = 16) :
  ∃ a_n : ℕ → ℝ, ∀ n, a_n n = 2 * n - 1 := by
  sorry"""),
    Theorem("ds_0287_thm_2854", """theorem {name} (m : ℝ) :
  (∃ x : ℝ, x ∈ Set.Icc (-2) 4 ∧ Real.sqrt (2 + x) + Real.log (4 - x) = 2) →
  (∀ x : ℝ, x ∈ Set.Icc (-2) 4 → Real.sqrt (2 + x) + Real.log (4 - x) ≤ 2) →
  (∀ x : ℝ, x ∈ Set.Icc (-2) 4 → Real.sqrt (2 + x) + Real.log (4 - x) ≤ 2) →
  (∃ x : ℝ, x ∈ Set.Icc (-2) 4 ∧ Real.sqrt (2 + x) + Real.log (4 - x) = 2) →
  (∃ x : ℝ, x ∈ Set.Icc (-2) 4 ∧ Real.sqrt (2 + x) + Real.log (4 - x) = 2) →
  (∃ x : ℝ, x ∈ Set.Icc (-2) 4 ∧ Real.sqrt (2 + x) + Real.log (4 - x) = 2) →
  (∃ x : ℝ, x ∈ Set.Icc (-2) 4 ∧ Real.sqrt (2 + x) + Real.log (4 - x) = 2) →
  (∃ x : ℝ, x ∈ Set.Icc (-2) 4 ∧ Real.sqrt (2 + x) + Real.log (4 - x) = 2) →
  m = 2 →
  (∃ x : ℝ, x ∈ Set.Icc (-2) 4 ∧ Real.sqrt (2 + x) + Real.log (4 - x) = 2) →
  (∃ x : ℝ, x ∈ Set.Icc (-2) 4 ∧ Real.sqrt (2 + x) + Real.log (4 - x) = 2) →
  (∃ x : ℝ, x ∈ Set.Icc (-2) 4 ∧ Real.sqrt (2 + x) + Real.log (4 - x) = 2) →
  (∃ x : ℝ, x ∈ Set.Icc (-2) 4 ∧ Real.sqrt (2 + x) + Real.log (4 - x) = 2) →
  m ∈ Set.Icc (2 : ℝ) (5 / 2) := by
  sorry"""),
    Theorem("ds_0288_thm_2890", """theorem {name} (students : ℕ) (h₀ : 0 < students) (h₁ : students < 500)
  (h₂ : students % 23 = 22) (h₃ : students % 21 = 14) : students = 413 := by
  sorry"""),
    Theorem("ds_0289_thm_2907", """theorem {name} : ∃ (f : ℝ → ℝ), (∀ x y : ℝ, f (⌊x⌋ * y) = f x * ⌊f y⌋) → (∀ x : ℝ, f x = 0) ∨ (∀ x : ℝ, f x = 1) ∨ (∀ x : ℝ, f x = 2) ∨ (∀ x : ℝ, f x = x + 1) ∨ (∀ x : ℝ, f x = if x ≤ 1 then 0 else x + 1) := by
  sorry"""),
    Theorem("ds_0290_thm_3026", """theorem {name} : ∀ a b c : ℂ, Complex.abs a = Complex.abs b → Complex.abs b = Complex.abs c → Complex.abs a = 1 → Complex.abs b = 1 → Complex.abs c = 1 → ∃ z : ℂ, z^3 + a*z^2 + b*z + c = 0 → Complex.abs z = 1 := by
  sorry"""),
    Theorem("ds_0291_thm_3096", """theorem {name} (a : ℝ) (h₀ : a > 0) :
    let f := fun x => abs (x + 1) + abs (3 * x + a);
    let min_value := 1;
    f x = min_value → a = 1 ∨ a = 6 → a ≠ 1 → a = 6 := by
  sorry"""),
    Theorem("ds_0292_thm_3149", """theorem {name} (cars : ℕ) (motorcycles : ℕ) (h₀ : cars = 19) (h₁ : cars * 5 + motorcycles * 2 = 117) : motorcycles = 11 := by
  sorry"""),
    Theorem("ds_0293_thm_3340", """theorem {name} :
  ∀ (n : ℕ) (b : ℕ → ℕ),
    ∑ i in Finset.range (n + 1), b i = 2 →
      (∀ i ∈ Finset.range (n + 1), b i ≠ 0) →
      ∃ a : ℕ → ℕ,
        (∀ i ∈ Finset.range (n + 1), a i ≠ 0) →
          ∑ i in Finset.range (n + 1), (a i) = 2 := by
  sorry"""),
    Theorem("ds_0294_thm_3712", """theorem {name} : 
  let f := fun x => 10 * x + 3;
  let g := fun x => x^2 - 2;
  (∃ a, ∀ b, g (f b) = g a) → ∃ a, ∀ b, g (f b) = g a → a = 1 ∨ a = 11 := by
  sorry"""),
    Theorem("ds_0295_thm_3723", """theorem {name} (a b : ℕ) (A B : Finset ℕ) (h₀ : ∀ x, x ∈ A ↔ x ∈ B) :
    let op : (Finset ℕ) → (Finset ℕ) → (Finset ℕ) := fun x y => x ∪ y;
    let A' := (op A B);
    let B' := (op B A);
    A' = B' ↔ A = B := by
  sorry"""),
    Theorem("ds_0296_thm_3853", """theorem {name} (a b : ℝ) (h₀ : 0 < a) (h₁ : 0 < b) (h₂ : a > b) :
  let ellipse := (fun (x : ℝ) (y : ℝ) => x^2 / a^2 + y^2 / b^2 = 1);
  let center_of_ellipse := (0, 0);
  let e := (1 / 2 : ℝ);
  let a_prime := a * e;
  let m := (0 : ℝ);
  let n := (1 : ℝ);
  let P := (m, n);
  let Q := (m + a_prime, n);
  let R := (m - a_prime, n);
  let S := (m + a_prime / 2, n + (b * Real.sqrt 3) / 2);
  let T := (m - a_prime / 2, n + (b * Real.sqrt 3) / 2);
  (S = T) ↔ (1 = 7) ∨ (1 = 0) := by
  sorry"""),
    Theorem("ds_0297_thm_3883", """theorem {name} (p : ℝ) (h₀ : 0 < p) :
    let C := {{y : ℝ | y ^ 2 = 2 * p * x}};
    let A := (1, 2);
    let B := (1, 1);
    let R := ∃ (x : ℝ), x ∈ C ∧ (A.fst - x) ^ 2 + (A.snd - y) ^ 2 = (B.fst - x) ^ 2 + (B.snd - y) ^ 2;
    let S := ∃ (x : ℝ), x ∈ C ∧ (A.fst - x) ^ 2 + (A.snd - y) ^ 2 = (B.fst - x) ^ 2 + (B.snd - y) ^ 2;
    R → S → ∃ (k : ℝ), k > 0 ∧ ∃ (x : ℝ), x ∈ C ∧ (A.fst - x) ^ 2 + (A.snd - y) ^ 2 = (B.fst - x) ^ 2 + (B.snd - y) ^ 2 := by
  sorry"""),
    Theorem("ds_0298_thm_3902", """theorem {name} (p : ℝ) (h₀ : 0 ≤ p) (h₁ : p ≤ 1) (h₂ : p = 3 / 4 * 2 / 3 + 1 / 4 * 1 / 3) :
    p ∈ Set.Icc (5 / 12) (2 / 3) := by
  sorry"""),
    Theorem("ds_0299_thm_4308", """theorem {name} (h₀ : ∀ x : ℝ, sin x = 4 * cos x * (sin x - cos x) + 1) :
    (∃ t : ℝ, sin t = 4 * cos t * (sin t - cos t) + 1) → ∃ t : ℝ, t = 4 * Real.sqrt 2 := by
  sorry"""),
    Theorem("ds_0300_thm_4476", """theorem {name} (Z : ℕ) (h₀ : Z % 1000 = 999) (h₁ : Z / 1000 = 999) : 11 ∣ Z := by
  sorry"""),
    Theorem("ds_0301_thm_4586", """theorem {name} (k : ℕ) (h₀ : k ≥ 2) :
    let a_n := 2 * k - 1;
    let S_n := 2 * k - 1 + 2 * (k - 1) + 3 * (k - 2) + 4 * (k - 3) + 5 * (k - 4) + 6 * (k - 5);
    S_n = 32 → k = 4 ∨ k = 5 := by
  sorry"""),
    Theorem("ds_0302_thm_4610", """theorem {name} :
    let a_n := fun n => 23 + 7 * (n - 1);
    let S_n := fun n => 23 * n + 7 * (n - 1) * n / 2;
    (∃ n, S_n n = a_n n) → ∃ n, S_n n ≥ a_n n → ∃ n, S_n n ≥ a_n n → ∃ n, S_n n ≥ a_n n → ∃ n, S_n n ≥ a_n n →
      n = 10 := by
  sorry"""),
    Theorem("ds_0303_thm_4677", """theorem {name} (n : ℕ) (h₀ : 0 < n) :
  let board_size := n;
  let squares_per_side := board_size + 1;
  let total_squares := squares_per_side ^ 2;
  let good_paths := 2 * n - 1;
  good_paths ≤ total_squares → ∃ paths : ℕ, paths ≤ total_squares ∧ paths ≥ good_paths := by
  sorry"""),
    Theorem("ds_0304_thm_4681", """theorem {name} :
    let S := Finset.range 11;
    let f : ℕ → ℕ := fun x => x + 1;
    let s : ℕ → ℕ := fun x => x + 1;
    ∀ i ∈ S, f (s i) % 2 = 0 → ∃ j ∈ S, f j = 650 → ∃ k ∈ S, f k = 650 → ∃ l ∈ S, f l = 650 → ∃ m ∈ S, f m = 650 → ∃ n ∈ S, f n = 650 → ∃ o ∈ S, f o = 650 → ∃ p ∈ S, f p = 650 → ∃ q ∈ S, f q = 650 → ∃ r ∈ S, f r = 650 → 650 = 650 := by
  sorry"""),
    Theorem("ds_0305_thm_4714", """theorem {name} : 
  let A := {{a : ℝ | a ∈ Set.Icc (-1 : ℝ) 1}};
  (∀ p : Prop, p → (∃ a : ℝ, a ∈ A ∧ (∃ x : ℝ, x^2 - 2*x + a^2 = 0))) →
  A = Set.Icc (-1 : ℝ) 1 := by
  sorry"""),
    Theorem("ds_0306_thm_4727", """theorem {name} (a b c d : ℝ) (h₀ : c = -2) (h₁ : d = 2) (h₂ : a * (-1)^3 + b * (-1)^2 + c * (-1) + d = 0) (h₃ : a * 1^3 + b * 1^2 + c * 1 + d = 0) : b = -2 := by
  sorry"""),
    Theorem("ds_0307_thm_4862", """theorem {name} :
  let A (x : ℝ) := 1 / (1 + x);
  let B (x : ℝ) := 1 / (1 - x);
  let C (x : ℝ) := 1 / (1 + x ^ 2);
  let D (x : ℝ) := 1 / (1 - x ^ 2);
  let f (x : ℝ) := A (B x) * C (D x);
  ∀ x : ℝ, f x ≤ 3 / 860 → ∃ (x : ℝ), f x = 3 / 860 → x = 1 / 29 := by
  sorry"""),
    Theorem("ds_0308_thm_1558", """theorem {name} (a b c : ℕ) (h₀ : a % 47 = 25) (h₁ : b % 47 = 20) (h₂ : c % 47 = 3) :
    (a + b + c) % 47 = 1 := by
  sorry"""),
    Theorem("ds_0309_thm_83", """theorem {name} (length width : ℝ) (h₀ : 2 * length + 2 * width = 60) (h₁ : length = 2 * width) :
    length * width = 200 := by
  sorry"""),
    Theorem("ds_0310_thm_602", """theorem {name} (x y : ℝ) (h₀ : x + y = 19) (h₁ : x - y = 5) : x * y = 84 := by
  sorry"""),
    Theorem("ds_0311_thm_1127", """theorem {name} (a b : ℝ) (h₀ : a + b = 50) (h₁ : a - b = 6) : a * b = 616 := by
  sorry"""),
    Theorem("ds_0312_thm_294", """theorem {name} (x y : ℤ) (h₀ : x * (x + y) = x ^ 2 + 8) : x * y = 8 := by
  sorry"""),
    Theorem("ds_0313_thm_687", """theorem {name} :
    ∀ {{x : ℚ}}, (3 / 4) * x = (3 / 5) * x → x = 0 ∨ (3 / 4) * x / (3 / 5) = (5 / 4) := by
  sorry"""),
    Theorem("ds_0314_thm_845", """theorem {name} (x y : ℝ) (h₀ : (x + y) / 2 = 18) (h₁ : x * y = 92) : x^2 + y^2 = 1112 := by
  sorry"""),
    Theorem("ds_0315_thm_1034", """theorem {name} (a b c : ℕ) (h₀ : a % 12 = 7) (h₁ : b % 12 = 9) (h₂ : c % 12 = 10) :
  (a + b + c) % 12 = 2 := by
  sorry"""),
    Theorem("ds_0316_thm_2316", """theorem {name} (AB BC CA : ℝ) (h₀ : AB = 13) (h₁ : BC = 14) (h₂ : CA = 15) :
  let M := (AB / 2 : ℝ);
  let H := (0 : ℝ);
  let HM := abs (M - H);
  HM = 6.5 := by
  sorry"""),
    Theorem("ds_0317_thm_2335", """theorem {name} (l w : ℕ) (h₀ : 2 * (l + w) = 30) (h₁ : l ≤ w) : l * w ≤ 56 := by
  sorry"""),
    Theorem("ds_0318_thm_2672", """theorem {name} (a b : ℝ) (h₀ : a ^ 2 + b ^ 2 = 1)
    (h₁ : a * (-3 / 5) + b * (4 / 5) = 1) (h₂ : a * (-4 / 5) + b * (3 / 5) = 0) :
    (a, b) = (-3 / 5, 4 / 5) := by
  sorry"""),
    Theorem("ds_0319_thm_3348", """theorem {name} (l : ℝ) (h₀ : l = 2) (h₁ : l * Real.sqrt 3 / 2 = 3) :
    (l / 2) ^ 2 * Real.sqrt 3 / 4 = 3 / 4 := by
  sorry"""),
    Theorem("ds_0320_thm_3415", """theorem {name} (n : ℕ) (h₀ : n = 30) (h₁ : n ≥ 2) (h₂ : 20 * 19 / 2 ≤ n * (n - 1) / 2) :
    n * (n - 1) / 2 - 20 * 19 / 2 = 245 := by
  sorry"""),
    Theorem("ds_0321_thm_3616", """theorem {name} (n : ℕ) (h₀ : 3 ∣ n) : (n + 4 + (n + 6) + (n + 8)) % 9 = 0 := by
  sorry"""),
    Theorem("ds_0322_thm_3928", """theorem {name} (n : ℕ) (h : n % 15 = 7) : (n % 3 + n % 5) = 3 := by
  sorry"""),
    Theorem("ds_0323_thm_4072", """theorem {name} (x y : ℕ) (h₀ : x + y = 31) (h₁ : x - y = 3) : max x y = 17 := by
  sorry"""),
    Theorem("ds_0324_thm_4105", """theorem {name} (m n : ℕ) (h₀ : 0 < m) (h₁ : 0 < n) :
  ∀ (Anastasia : ℕ → ℕ) (Boris : ℕ → ℕ),
    (∀ k : ℕ, k < 2 * m → Anastasia k = k + 1) →
    (∀ k : ℕ, k < 2 * m → Boris k = k + 1) →
    ¬(∀ k : ℕ, k < 2 * m → Anastasia k + Boris k = n) →
    ∃ k : ℕ, k < 2 * m ∧ Anastasia k + Boris k ≠ n := by
  sorry"""),
    Theorem("ds_0325_thm_4257", """theorem {name} (y x : ℤ) (h₀ : y = k * x) (h₁ : k = 2) (h₂ : y = 8) : y = -16 ↔ x = -4 := by
  sorry"""),
    Theorem("ds_0326_thm_4783", """theorem {name} (a c : ℝ) (h₀ : -|a - 2| + 5 = 5) (h₁ : |c - 8| + 3 = 3) : a + c = 10 := by
  sorry"""),
    Theorem("ds_0327_thm_7", """theorem {name} (x y : ℝ) (h₀ : x + 2 * y = 4) (h₁ : x * y = -8) : x ^ 2 + 4 * y ^ 2 = 48 := by
  sorry"""),
    Theorem("ds_0328_thm_26", """theorem {name} (n : ℤ) (h₀ : n % 7 = 2) : (3 * n - 7) % 7 = 6 := by
  sorry"""),
    Theorem("ds_0329_thm_61", """theorem {name} (j b : ℕ) (h₀ : j = 10 * (b % 10) + (b / 10))
    (h₁ : j + 5 = 2 * (b + 5)) : j - b = 18 := by
  sorry"""),
    Theorem("ds_0330_thm_111", """theorem {name} (a b : ℝ) (h₀ : a * b = 5) (h₁ : a + b = 5) :
    a ^ 2 + b ^ 2 = 15 := by
  sorry"""),
    Theorem("ds_0331_thm_114", """theorem {name} (x y : ℝ) (h₀ : x + y = 6) (h₁ : x^2 - y^2 = 12) : x - y = 2 := by
  sorry"""),
    Theorem("ds_0332_thm_115", """theorem {name} (YZ XY : ℝ) (h₀ : YZ > 0) (h₁ : XY > 0) (h₂ : XY / YZ = 4 / 5)
    (h₃ : YZ = 30) : XY = 24 := by
  sorry"""),
    Theorem("ds_0333_thm_166", """theorem {name} (x : ℕ) (h₀ : x + 4 + 2 * x + 1 + 7 = 36) : max (max (x + 4) (2 * x + 1)) 7 = 17 := by
  sorry"""),
    Theorem("ds_0334_thm_213", """theorem {name} (n : ℕ) (h₀ : n < 500)
    (h₁ : n % 23 = 22) (h₂ : n % 21 = 14) : n = 413 := by
  sorry"""),
    Theorem("ds_0335_thm_282", """theorem {name} : Real.log 8 / Real.log (1 / 8) = -1 := by
  sorry"""),
    Theorem("ds_0336_thm_335", """theorem {name} (x₁ x₂ : ℝ) (h₀ : x₁ ≤ x₂) (h₁ : |x₁| + |x₂| = 1) (h₂ : x₁ + x₂ = 0) :
    let max := x₁ - x₂;
    max ≤ 41 / 800 := by
  sorry"""),
    Theorem("ds_0337_thm_374", """theorem {name} (A B C : ℝ) (h₀ : A = 86) (h₁ : B = 3 * C + 22) (h₂ : A + B + C = 180) :
    C = 18 := by
  sorry"""),
    Theorem("ds_0338_thm_393", """theorem {name} (x y z : ℝ) (h₀ : x * y * z = (1 / 2) * (1 / 2) * (1 / 2)) (h₁ : x + y + z = 1) :
    x * y * z ≥ 1 / 32 := by
  sorry"""),
    Theorem("ds_0339_thm_466", """theorem {name} (x : ℤ) (h₀ : x + (x + 4) = 128) : x + (x + 2) + (x + 4) = 192 := by
  sorry"""),
    Theorem("ds_0340_thm_583", """theorem {name} (a b p : ℝ × ℝ) (t u : ℝ)
    (h₀ : p.fst = a.fst + t * (b.fst - a.fst)) (h₁ : p.snd = a.snd + t * (b.snd - a.snd))
    (h₂ : p.fst = a.fst + u * (b.fst - a.fst)) (h₃ : p.snd = a.snd + u * (b.snd - a.snd))
    (h₄ : a.fst ≠ b.fst) (h₅ : a.snd ≠ b.snd) (h₆ : t ≠ u) (h₇ : t ≠ 0) (h₈ : u ≠ 0)
    (h₉ : p.fst = 10) (h₁₀ : p.snd = 3) : p = (10, 3) := by
  sorry"""),
    Theorem("ds_0341_thm_603", """theorem {name} (x y : ℝ) (h₀ : x + y = 16) (h₁ : x - y = 2) : x ^ 2 - y ^ 2 = 32 := by
  sorry"""),
    Theorem("ds_0342_thm_612", """theorem {name} (a b c : ℝ) (h₀ : a ≠ 0) (h₁ : b ≠ 0) (h₂ : c ≠ 0) (h₃ : a ≠ b)
  (h₄ : a ≠ c) (h₅ : b ≠ c) (h₆ : a + b + c = 0) (h₇ : a * b + b * c + c * a = 0)
  (h₈ : a * b * c = -1) : a^2 * b^2 * c^2 = 1 := by
  sorry"""),
    Theorem("ds_0343_thm_678", """theorem {name} (a d : ℝ) (h₀ : a = 7 / 9) (h₁ : a + 12 * d = 4 / 5) :
    a + 6 * d = 71 / 90 := by
  sorry"""),
    Theorem("ds_0344_thm_708", """theorem {name} (a b : ℝ) (h₀ : a + b = 19) (h₁ : a - b = 5) :
  a * b = 84 := by
  sorry"""),
    Theorem("ds_0345_thm_747", """theorem {name} (x y : ℝ) (h₀ : 2 * x + 2 * y = 180) (h₁ : x * y = 10 * (2 * x + 2 * y)) :
    x * y ≤ 2250 := by
  sorry"""),
    Theorem("ds_0346_thm_767", """theorem {name} (a b c : ℝ) (h₀ : a ≠ 0) (y₁ y₂ : ℝ) (h₁ : y₁ = a * 1 ^ 2 + b * 1 + c)
    (h₂ : y₂ = a * (-1) ^ 2 + b * (-1) + c) (h₃ : y₁ - y₂ = -6) : b = -3 := by
  sorry"""),
    Theorem("ds_0347_thm_777", """theorem {name} (n : ℝ) (h₀ : n > 0) (h₁ : 24 = 6 * n ^ 2) : n = 2 := by
  sorry"""),
    Theorem("ds_0348_thm_880", """theorem {name} (length width radius : ℝ) (h₀ : radius = 5) (h₁ : length / width = 2 / 1) (h₂ : width = 10) : length * width = 200 := by
  sorry"""),
    Theorem("ds_0349_thm_918", """theorem {name} (n : ℕ) (h₀ : n % 15 = 7) : n % 3 + n % 5 = 3 := by
  sorry"""),
    Theorem("ds_0350_thm_1024", """theorem {name} (y x : ℝ) (h₀ : y ≠ 0) (h₁ : y = k * x) (h₂ : k = 2) (h₃ : y = 8) (h₄ : x = 4) :
    y = -16 ↔ x = -8 := by
  sorry"""),
    Theorem("ds_0351_thm_1032", """theorem {name} :
  let f := fun (x : ℝ) =>
    if x > 5 then x ^ 2 + 1 else if x ≤ -5 then 3 else 2 * x - 3;
  f (-7) + f 0 + f 7 = 50 := by
  sorry"""),
    Theorem("ds_0352_thm_1124", """theorem {name} (x y : ℝ) (h₀ : x = y) (h₁ : (10 + 18 + x + y) / 4 = 15) : x * y = 256 := by
  sorry"""),
    Theorem("ds_0353_thm_1143", """theorem {name} (A B : ℕ) (h₀ : ∀ n : ℕ, ∃ m : ℕ, m ≥ n ∧ m % 2 = 0) (h₁ : A + B = 24)
  (h₂ : ∀ n : ℕ, ∃ m : ℕ, m ≥ n ∧ m % 2 = 1) (h₃ : A = 2 * B) : B = 8 := by
  sorry"""),
    Theorem("ds_0354_thm_1331", """theorem {name} (x y : ℤ)
  (h₀ : x + 2 * y = 4) (h₁ : x * y = -8) : x ^ 2 + 4 * y ^ 2 = 48 := by
  sorry"""),
    Theorem("ds_0355_thm_1357", """theorem {name} (a : ℤ) (h₀ : 4 * x ^ 2 - 12 * x + a = (2 * x - 3) ^ 2) : a = 9 := by
  sorry"""),
    Theorem("ds_0356_thm_1520", """theorem {name} (green_cost pink_cost : ℝ) (h₀ : green_cost = pink_cost + 1) (h₁ : 14 * green_cost + 14 * pink_cost = 546) : green_cost = 20 := by
  sorry"""),
    Theorem("ds_0357_thm_1521", """theorem {name} (x y : ℝ) (h₀ : x - y = 1) :
  let K := x ^ 2 + x - 2 * x * y + y ^ 2 - y;
  K = 2 := by
  sorry"""),
    Theorem("ds_0358_thm_1571", """theorem {name} (l w : ℕ) (h₀ : 2 * (l + w) = 120) (h₁ : w = 3 * l) : l * w = 675 := by
  sorry"""),
    Theorem("ds_0359_thm_1628", """theorem {name} (t : ℤ) (h₀ : (t - 6) * (2 * t - 5) = (2 * t - 8) * (t - 5)) : t = 10 := by
  sorry"""),
    Theorem("ds_0360_thm_1657", """theorem {name} (initial_bacteria : ℕ) (h₀ : initial_bacteria * 3^(180/20) = 275562) :
    initial_bacteria = 14 := by
  sorry"""),
    Theorem("ds_0361_thm_1815", """theorem {name} (n : ℕ) (h₀ : n ≥ 1000) (h₁ : n ≤ 2000) (h₂ : n % 5 = 0) (h₃ : n % 8 = 0) : 
  n % 40 = 0 := by
  sorry"""),
    Theorem("ds_0362_thm_1895", """theorem {name} (x : ℤ) (h : (8 - x) ^ 2 = x ^ 2) : x = 4 := by
  sorry"""),
    Theorem("ds_0363_thm_2002", """theorem {name} (c : ℝ) (h₀ : c / 5 + 3 = c / 4) : c = 60 := by
  sorry"""),
    Theorem("ds_0364_thm_2010", """theorem {name} (a b c d : ℝ) (h₀ : a * b + b * c + c * d + d * a = 30) (h₁ : b + d = 5) : a + c = 6 := by
  sorry"""),
    Theorem("ds_0365_thm_2014", """theorem {name} (n : ℕ) (h : n % 15 = 7) : (n % 3 + n % 5) % 15 = 3 := by
  sorry"""),
    Theorem("ds_0366_thm_2126", """theorem {name} (A : ℕ → Set ℝ) :
  (∀ j : ℕ, j ≥ 1 → ∀ x : ℝ, x ∈ A j ↔ x ∈ A 1) →
  ∀ j : ℕ, j ≥ 1 → A j = A 1 := by
  sorry"""),
    Theorem("ds_0367_thm_2150", """theorem {name} (x₁ x₂ : ℝ) (h₀ : 0 ≤ x₁) (h₁ : 0 ≤ x₂) (h₂ : x₁ + x₂ ≤ 1) (h₃ : x₁ + x₂ + x₁ * x₂ ≤ 1) :
  let S := x₁ * x₂;
  S ≤ 25 / 2 := by
  sorry"""),
    Theorem("ds_0368_thm_2280", """theorem {name} (a x : ℝ) (h₀ : 9 * x ^ 2 + 24 * x + a = (3 * x + 4) ^ 2) : a = 16 := by
  sorry"""),
    Theorem("ds_0369_thm_2759", """theorem {name} (x y : ℕ)
    (h₀ : 3 * x = 4 * y) (h₁ : x - y = 8) : x = 32 := by
  sorry"""),
    Theorem("ds_0370_thm_2774", """theorem {name} (R₁ R₂ R₃ : ℝ) (h₀ : R₁ = 2) (h₁ : R₂ = 2) (h₂ : R₃ = 2) :
    let hexagon_area := 13 * Real.sqrt 3;
    let triangle_area := 1 / 2 * 5 * 5 * Real.sqrt 3;
    hexagon_area ≥ triangle_area := by
  sorry"""),
    Theorem("ds_0371_thm_2850", """theorem {name} (f g : ℝ → ℝ) (h₀ : ∀ x, f x = -7 * x^4 + 3 * x^3 + x - 5)
    (h₁ : ∃ (n : ℕ), ∀ x, g x = x^n) (h₂ : ∃ (n : ℕ), ∀ x, f x + g x = x^n → n = 1) :
    ∃ (n : ℕ), ∀ x, g x = x^n → n = 4 := by
  sorry"""),
    Theorem("ds_0372_thm_2970", """theorem {name} (x y : ℕ) (h₀ : x + y = 9) (h₁ : 3 * x + 4 * y = 33) : y = 6 := by
  sorry"""),
    Theorem("ds_0373_thm_3014", """theorem {name} (x : ℕ) (h₀ : 2 * (2 * (2 * (2 * x))) = 48) : x = 3 := by
  sorry"""),
    Theorem("ds_0374_thm_3211", """theorem {name} (A : ℕ) (h₀ : A ≤ 9) (h₁ : (3 * 1000 + A * 100 + A * 10 + 1) % 9 = 0) : A = 7 := by
  sorry"""),
    Theorem("ds_0375_thm_3373", """theorem {name} (M P : ℕ)
  (h₀ : M = 8 * P) (h₁ : M + P = 27) : M = 24 := by
  sorry"""),
    Theorem("ds_0376_thm_3398", """theorem {name} (a b : ℤ) (h₀ : a > 0) (h₁ : b > 0) (h₂ : a - b = 12) (h₃ : a * b = 45) :
    a + b = 18 := by
  sorry"""),
    Theorem("ds_0377_thm_3598", """theorem {name} (a x : ℝ) (h₀ : (4 * x ^ 2 - 12 * x + a) = (2 * x - 3) ^ 2) : a = 9 := by
  sorry"""),
    Theorem("ds_0378_thm_3684", """theorem {name} (x y : ℝ) (h₀ : x = 4) (h₁ : y = 1) :
    (x, -y) = (x - 2 * (x - (-y)), y - 2 * (y - x)) ↔ (x, -y) = (-2, 5) := by
  sorry"""),
    Theorem("ds_0379_thm_3700", """theorem {name} (a b c : ℝ) (h₀ : a ^ 2 + b ^ 2 + c ^ 2 = 13 ^ 2) (h₁ : a ^ 2 + b ^ 2 - c ^ 2 = 14 ^ 2) (h₂ : -3 * a + 4 * b = 15) :
    Real.sqrt (a ^ 2 + b ^ 2) = 5 * Real.sqrt 13 := by
  sorry"""),
    Theorem("ds_0380_thm_3753", """theorem {name} (x y z : ℝ)
    (h₀ : x + y + z = 180) (h₁ : x / 3 = y / 3) (h₂ : y / 3 = z / 4) :
    z = 72 := by
  sorry"""),
    Theorem("ds_0381_thm_3793", """theorem {name} (a b : ℝ) (h₀ : ∃ x₀, x₀ ∈ Set.Icc (-1) 1 ∧ 2 * x₀ + a * x₀ ^ 2 + b = 0)
    (h₁ : ∃ x₀, x₀ ∈ Set.Icc (-1) 1 ∧ 2 * x₀ + a * x₀ ^ 2 + b = 0) :
    ∃ c : ℤ, (∃ x₀, x₀ ∈ Set.Icc (-1) 1 ∧ 2 * x₀ + a * x₀ ^ 2 + b = c) → c = -7 := by
  sorry"""),
    Theorem("ds_0382_thm_4048", """theorem {name} (n : ℕ) (hn : n > 0) (h₁ : 3 ∣ 2 * n - 1) (h₂ : ¬3 ∣ n) :
    let k := n / 3;
    n = 3 * k + 1 ∨ n = 3 * k + 2 := by
  sorry"""),
    Theorem("ds_0383_thm_4212", """theorem {name} (m : ℤ) [hm : Fact (m ≥ 5)] :
    let D (m : ℤ) := 1;
    let q (x : ℤ) := 2 * x^3 + 3 * x^2 + 4 * x + 5;
    ∀ m, D m = 1 → ∃ c : ℤ, (∀ x, q x % m = c) → c = 11 := by
  sorry"""),
    Theorem("ds_0384_thm_4909", """theorem {name} :
  let P := fun (x : ℤ) ↦ x^3 + 2 * x^2 + c * x + 10;
  P 5 = 0 ↔ c = -37 := by
  sorry"""),
    Theorem("ds_0385_thm_133", """theorem {name} (b : ℝ) (h₀ : b > 1)
  (x : ℝ) (h₁ : Real.log x = a) (h₂ : Real.sin x > 0) (h₃ : Real.cos x > 0) :
  Real.log (Real.sin x) / Real.log (Real.cos x) = 1 / 2 * (Real.log (1 - b ^ (2 * a)) - Real.log b) ↔
  1 / 2 * (Real.log (1 - b ^ (2 * a)) - Real.log b) = Real.log (Real.sin x) / Real.log (Real.cos x) := by
  sorry"""),
    Theorem("ds_0386_thm_304", """theorem {name} (n : ℕ) (h₀ : n = 100) :
  (Finset.filter (fun x => x ∈ Finset.range 50) (Finset.image (fun x => x % 10) (Finset.range 100))).card / n = 1 / 3 := by
  sorry"""),
    Theorem("ds_0387_thm_346", """theorem {name} (a : ℕ → ℕ) (S : ℕ → ℕ) (h₀ : ∀ n, a n > 0) (h₁ : ∀ n, S n = ∑ k in Finset.range (n + 1), a k) (h₂ : ∀ n, a (n + 1) = 2 * a n + 2) (h₃ : ∀ n, a n = 2 * a (n - 1) + 2) (h₄ : a 1 = 2) (h₅ : ∀ n, n ≥ 1 → S n = (a n ^ 2 + 2 * a n) / 4) (b : ℕ → ℕ) (h₆ : ∀ n, b n = a n * 3 ^ (a n / 2) - 1) (h₇ : ∀ n, n ≥ 1 → ∃! s, s = (n - 1 / 2) * 3 ^ (n + 1) - n + 3 / 2) : ∀ n, n ≥ 1 → ∃! s, s = (n - 1 / 2) * 3 ^ (n + 1) - n + 3 / 2 := by
  sorry"""),
    Theorem("ds_0388_thm_404", """theorem {name} (a b : ℝ) (h₀ : 0 < a) (h₁ : 0 < b) :
    (∃ x₀, |x₀ + a| - |x₀ - 2 * b| ≥ 4) → ∃ a_b : ℝ, a_b ≥ 4 := by
  sorry"""),
    Theorem("ds_0389_thm_448", """theorem {name} (n : ℕ) (h₀ : 102 = n / 6) (h₁ : 3 = n % 6) : n = 615 := by
  sorry"""),
    Theorem("ds_0390_thm_579", """theorem {name} (AB BC DE EF : ℝ) (h₀ : DE = 6) (h₁ : EF = 12) (h₂ : BC = 18) (h₃ : AB / BC = DE / EF) : AB = 9 := by
  sorry"""),
    Theorem("ds_0391_thm_689", """theorem {name} (n : ℕ) (h₀ : 8 < n) (h₁ : n < 10) (h₂ : n > 5) :
  let a_n := 4 * n - 4;
  let b_n := 2 * n + 3;
  (∑ k in Finset.range n, a_n) = ∑ k in Finset.range n, b_n ↔ n = 19 := by
  sorry"""),
    Theorem("ds_0392_thm_824", """theorem {name} (ab bc de ef : ℝ) (h₀ : de = 6) (h₁ : ef = 12) (h₂ : bc = 18) (h₃ : ab / bc = de / ef) :
  ab = 9 := by
  sorry"""),
    Theorem("ds_0393_thm_1117", """theorem {name} (a : ℤ) (h : a % 35 = 23) : a % 7 = 2 := by
  sorry"""),
    Theorem("ds_0394_thm_1131", """theorem {name} (N : ℕ) (h₀ : N ≡ 696 [MOD 1000]) : N % 1000 = 696 := by
  sorry"""),
    Theorem("ds_0395_thm_1347", """theorem {name} : ∃ (n : ℕ), ∀ (s : Finset ℕ), s.card = n → (∀ (i : ℕ), i ∈ s → 1 ≤ i) →
    (∀ (i : ℕ), i ∈ s → ∃ (j : ℕ), j ∈ s ∧ i * j = 2010) → n = 39 := by
  sorry"""),
    Theorem("ds_0396_thm_1364", """theorem {name} (n : ℕ) (h₀ : n > 3) :
    let m := (n^2 - n - 3) / 2;
    let rhombuses := m;
    let triangles := n^2 - m;
    rhombuses - triangles = 6 * n - 9 →
    ∃ rhombuses triangles : ℕ, rhombuses - triangles = 6 * n - 9 := by
  sorry"""),
    Theorem("ds_0397_thm_1411", """theorem {name} (M : Set ℤ) (h₀ : M.Nonempty) (h₁ : ∀ x : ℤ, x ∈ M → x ≠ 0) (f g : ℤ → ℤ)
  (h₂ : ∀ x : ℤ, x ∈ M → f x ∈ M) (h₃ : ∀ x : ℤ, x ∈ M → g x ∈ M) (h₄ : ∀ x : ℤ, x ∈ M → g (f x) = x)
  (h₅ : ∀ x : ℤ, x ∈ M → f (g x) = x) (h₆ : ∀ x : ℤ, x ∈ M → g (f x) = x) (h₇ : ∀ x : ℤ, x ∈ M → f (g x) = x)
  (h₈ : ∀ x : ℤ, x ∈ M → g (f x) = x) (h₉ : ∀ x : ℤ, x ∈ M → f (g x) = x) (h₁₀ : ∀ x : ℤ, x ∈ M → g (f x) = x) :
  ∀ x : ℤ, x ∈ M → ∃ y : ℤ, y ∈ M ∧ g (f y) = y := by
  sorry"""),
    Theorem("ds_0398_thm_1492", """theorem {name} : 
  let p := (1 : ℚ) / 2;
  ∀ n : ℕ, n ≥ 2 → (∑ k in Finset.range n, (n.choose k) * p ^ k * (1 - p) ^ (n - k)) < 1 →
    ∃ n : ℕ, n ≥ 2 ∧ (∑ k in Finset.range n, (n.choose k) * p ^ k * (1 - p) ^ (n - k)) < 1 := by
  sorry"""),
    Theorem("ds_0399_thm_1625", """theorem {name} (a : ℝ) : 
  (∃ (x : ℝ), x^2 - 2*x + a^2 = 0) →
  (∃ (x : ℝ), x^2 - 2*x + a^2 = 0) →
  ∃ (A : Set ℝ), (∀ (x : ℝ), x ∈ A ↔ x ∈ Set.Icc (-1 : ℝ) 1) := by
  sorry"""),
    Theorem("ds_0400_thm_1759", """theorem {name} (k : ℕ) (h₀ : k ≥ 2) :
  let smallest_n : ℕ := k + 3;
  (∀ n : ℕ, n ≥ smallest_n → (∀ (s : Finset ℝ), s.card = n → (∀ x ∈ s, ∃ a b c, x = a + b + c))) →
  (∀ (s : Finset ℝ), s.card = smallest_n → (∀ x ∈ s, ∃ a b c, x = a + b + c)) := by
  sorry"""),
    Theorem("ds_0401_thm_1781", """theorem {name} : 
  ∀ k : ℕ, k > 0 → (∀ n : ℕ, n > 0 → (4 * k ^ 2 - 1) ^ 2 % (8 * k * n - 1) = 0 → k % 2 = 0 → ∃ n : ℕ, n > 0 ∧ (4 * k ^ 2 - 1) ^ 2 % (8 * k * n - 1) = 0) := by
  sorry"""),
    Theorem("ds_0402_thm_1918", """theorem {name} (h₀ : 0 < x) (h₁ : x ^ 2 = 729) : x = 27 := by
  sorry"""),
    Theorem("ds_0403_thm_1970", """theorem {name} (n : ℕ) (h₀ : 2 ≤ n) (a : ℕ → ℝ) (h₁ : ∀ k, 0 < a k) (h₂ : ∀ k, a (k + 1) ≥ k * a k / (a k ^ 2 + (k - 1))) :
  ∀ m, 2 ≤ m → a m ≥ 2 → ∃ k, k ≥ 2 ∧ a k ≥ 2 := by
  sorry"""),
    Theorem("ds_0404_thm_2191", """theorem {name} (c : ℝ) (h₀ : c > 0) (h₁ : c = 3) :
    let area_of_triangle := 9 / c;
    let area_of_line := 27 / 2;
    area_of_line = area_of_triangle ↔ c = 2 / 3 := by
  sorry"""),
    Theorem("ds_0405_thm_2252", """theorem {name} (C : ℝ → ℝ → Prop) (h₀ : ∀ x y, C x y ↔ y = x ^ 2 - 2 * x + 2) :
  let f := fun x => (x ^ 2 - 2 * x + 2) ^ 2 - 2 * (x ^ 2 - 2 * x + 2) + 2;
  ∃ B : ℝ, ∀ x, C x (f x) → f x = B → f x = B := by
  sorry"""),
    Theorem("ds_0406_thm_2298", """theorem {name} (a : ℕ → ℕ) (h₀ : ∀ n, a (n + 1) = a n + 1) (h₁ : ∀ n, a n ≠ 0) (h₂ : ∀ n, a n ∈ Set.range (fun k => k ^ 2)) :
  ∀ n, ∃ k, a n = a k := by
  sorry"""),
    Theorem("ds_0407_thm_2596", """theorem {name} (AB BC : ℝ) (h₀ : BC = 18) (h₁ : 6 / 12 = AB / BC) : AB = 9 := by
  sorry"""),
    Theorem("ds_0408_thm_2679", """theorem {name} (a : ℕ → ℕ) (h₀ : ∀ n, a n = 2 ^ n + 2 ^ (n / 2)) (h₁ : ∀ n, a n ≠ 0) :
    ∀ n, ∃ k, a n = a k := by
  sorry"""),
    Theorem("ds_0409_thm_2720", """theorem {name} (a : ℕ → ℕ)
  (h₀ : a 1 > 0) (h₁ : ∀ n, n ≥ 2 → a n > 0) (h₂ : ∀ n, n ≥ 1 → a (n + 1) = Nat.minFac (n * a 1 + (n - 1) * a 2)) :
  ∀ n, n ≥ 1 → ∃ k, a n = a k := by
  sorry"""),
    Theorem("ds_0410_thm_2788", """theorem {name} (T : ℕ) (h₀ : T = 9) : ∃ k : ℕ, ∀ x : ℝ, x > 0 → (Real.log x / Real.log 2) ^ T - Real.log x / Real.log 4 = Real.log x / Real.log 8 → k = 27 := by
  sorry"""),
    Theorem("ds_0411_thm_2797", """theorem {name} :
    {{12 / 5, 16 / Real.exp 1, 5, -5}} ∪ {{x | x = -5 ∨ x = 39 / 5 ∨ x = -2 ∨ x = 16 / Real.exp 1}} =
      {{x | x = -5 ∨ x = 39 / 5 ∨ x = -2 ∨ x = 16 / Real.exp 1 ∨ x = 5 ∨ x = 12 / 5}} := by
  sorry"""),
    Theorem("ds_0412_thm_2836", """theorem {name} (heightSmallerTriangle : ℝ) (heightLargerTriangle : ℝ) (ratioArea : ℝ) (h₀ : 1 / 4 = ratioArea) (h₁ : heightSmallerTriangle = 3) (h₂ : heightLargerTriangle / heightSmallerTriangle = 2) : heightLargerTriangle = 6 := by
  sorry"""),
    Theorem("ds_0413_thm_3029", """theorem {name} : 
  ∀ (S : Finset ℕ) (h₀ : S.card = 2002), 
    (∀ (A : Finset ℕ) (h₁ : A ⊆ S), A.card ≥ 2002 → 
      (∀ (B : Finset ℕ) (h₂ : B ⊆ S), B.card ≥ 2002 → 
        (∃ (C : Finset ℕ) (h₃ : C ⊆ S), C.card = 2002))) → 
    ∃ (C : Finset ℕ) (h₄ : C ⊆ S), C.card = 2002 := by
  sorry"""),
    Theorem("ds_0414_thm_3189", """theorem {name} (h : ∀ n : ℕ, n > 0 → ∃ p : ℚ, p < 2 * Real.sqrt 3 - 2) :
  ∀ n : ℕ, n > 0 → ∃ p : ℚ, p < 2 * Real.sqrt 3 - 2 := by
  sorry"""),
    Theorem("ds_0415_thm_3298", """theorem {name} (AB BC DE EF : ℝ) (h₀ : DE = 6) (h₁ : EF = 12) (h₂ : BC = 18) (h₃ : AB / DE = BC / EF) : AB = 9 := by
  sorry"""),
    Theorem("ds_0416_thm_3384", """theorem {name} (S : Set (ℤ × ℤ)) (h : ∀ (h k : ℤ), (h, k) ∈ S ↔ h^2 - k^2 = 73) :
  ∃ (n : ℕ), ∀ (h k : ℤ), (h, k) ∈ S → n = 3 := by
  sorry"""),
    Theorem("ds_0417_thm_3403", """theorem {name} (n : ℕ) (h₀ : n > 0) (h₁ : ∀ k : ℕ, k > 0 → k ≤ n → k ^ 4 + 2 * k ^ 3 + 2 * k ^ 2 + 2 * k + 1 ≠ 0) :
    n = 1 ∨ n = 2 ∨ n = 3 ∨ n = 4 ∨ n = 5 ∨ n = 6 ∨ n = 7 ∨ n = 8 ∨ n = 9 ∨ n = 10 →
    n = 1 ∨ n = 2 ∨ n = 3 ∨ n = 4 ∨ n = 5 ∨ n = 6 ∨ n = 7 ∨ n = 8 ∨ n = 9 ∨ n = 10 ∨ n = 11 := by
  sorry"""),
    Theorem("ds_0418_thm_3443", """theorem {name} (n : ℕ) (h₀ : 5 ∣ n) (h₁ : n ∈ Finset.filter (fun x : ℕ => x % 5 = 0) (Finset.range (5!))) :
    (∃ m : ℕ, m ∈ Finset.filter (fun x : ℕ => x % 5 = 0) (Finset.range (5!))) = true := by
  sorry"""),
    Theorem("ds_0419_thm_3481", """theorem {name} (x : ℝ) (h₀ : 12 / (1 / 500) = x / (1 / 750)) : x = 8 := by
  sorry"""),
    Theorem("ds_0420_thm_3605", """theorem {name} (area_pqr : ℝ) (h₀ : area_pqr = 100) :
  let area_abc := 100 / 4;
  area_pqr > area_abc := by
  sorry"""),
    Theorem("ds_0421_thm_3815", """theorem {name} (A : Finset ℤ) (m : ℕ) (h₀ : 2 ≤ m) (h₁ : ∀ i ∈ A, ∀ j ∈ A, ∃ k ∈ A, i + j = k)
  (h₂ : ∀ i ∈ A, ∀ j ∈ A, ∃ k ∈ A, i - j = k) (h₃ : ∀ i ∈ A, ∀ j ∈ A, ∃ k ∈ A, i * j = k) :
  ∀ i ∈ A, ∃ j ∈ A, i ≤ j := by
  sorry"""),
    Theorem("ds_0422_thm_3846", """theorem {name} (a b c d e : ℤ) (h₀ : a = -7 ∨ a = -5 ∨ a = -1 ∨ a = 1 ∨ a = 3)
  (h₁ : b = -7 ∨ b = -5 ∨ b = -1 ∨ b = 1 ∨ b = 3) :
  a * b ≥ -21 := by
  sorry"""),
    Theorem("ds_0423_thm_4017", """theorem {name} : ¬ (∀ x : Prop, x → ¬ x) → (∃ x : Prop, x → ¬ x) := by
  sorry"""),
    Theorem("ds_0424_thm_4034", """theorem {name} (flagpole_height : ℝ) (flagpole_shadow_length : ℝ) (building_shadow_length : ℝ) (h₀ : flagpole_height = 5) (h₁ : flagpole_shadow_length = 6) (h₂ : building_shadow_length = 30) (h₃ : flagpole_height / flagpole_shadow_length = building_height / building_shadow_length) : building_height = 25 := by
  sorry"""),
    Theorem("ds_0425_thm_4051", """theorem {name} :
    let p1 := 101 / 100;
    let p2 := 45 / 44;
    let common_tangent_line := {{x : ℝ | p1 * x + p1 ^ 2 = p2 * x + p2 ^ 2}};
    (∃ x : ℝ, x ∈ common_tangent_line) → p1 + p2 + 1 = 210 / 99 →
    let m := 210 / 99;
    let n := 1;
    m + n = 309 := by
  sorry"""),
    Theorem("ds_0426_thm_4099", """theorem {name} (a b : ℝ) (h₀ : 0 < a) (h₁ : 0 < b) (h₂ : a > b) (h₃ : a ^ 2 / b ^ 2 + b ^ 2 / a ^ 2 = 1) :
    let A := (a, 0);
    let B := (0, b);
    let F := (a * Real.sqrt 3 / 2, b / 2);
    let P := (a * Real.sqrt 3 / 2, 0);
    let Q := (0, b / 2);
    let E := (a * Real.sqrt 3 / 2, b / 2);
    let M := (a * Real.sqrt 3 / 2, b / 2);
    let N := (a * Real.sqrt 3 / 2, b / 2);
    let x := a * Real.sqrt 3 / 2;
    let y := b / 2;
    a ^ 2 / b ^ 2 + b ^ 2 / a ^ 2 = 1 →
    (∃ k₁ k₂ : ℝ, k₁ * k₂ = -3 / 2) := by
  sorry"""),
    Theorem("ds_0427_thm_4126", """theorem {name} (speed : ℝ) (length : ℝ) (time : ℝ) (h₀ : speed = 800) (h₁ : length = 3200) (h₂ : time = 200) :
  (length + 200) / speed = time ↔ time = 4.5 := by
  sorry"""),
    Theorem("ds_0428_thm_4211", """theorem {name} (AF : ℝ) (G : ℝ) (H : ℝ) (E : ℝ) (h₀ : 0 < AF) (h₁ : 0 < G)
    (h₂ : 0 < H) (h₃ : 0 < E) (h₄ : G < AF) (h₅ : H < AF) (h₆ : E < AF) (h₇ : G < E) (h₈ : H < G)
    (h₉ : AF < 1) (h₁₀ : G < 1) (h₁₁ : H < 1) (h₁₂ : E < 1) : 
    (∃ (HC : ℝ), ∃ (JE : ℝ), HC / JE = 5 / 3) := by
  sorry"""),
    Theorem("ds_0429_thm_4277", """theorem {name} (T : Type) [Fintype T] (pop : ℕ) (dish : T → Finset ℕ)
  (chef : T → ℕ → Prop) (gr : ℕ → ℕ) (h₀ : ∀ t : T, ∃ d : ℕ, chef t d) (h₁ : ∀ d : ℕ, ∃ t : T, chef t d)
  (h₂ : ∀ t : T, ∀ d₁ d₂ : ℕ, d₁ ≠ d₂ → chef t d₁ ∧ chef t d₂ → False) (h₃ : ∀ d : ℕ, ∀ t₁ t₂ : T, t₁ ≠ t₂ → chef t₁ d ∧ chef t₂ d → False)
  (h₄ : ∀ t : T, ∀ d : ℕ, chef t d → gr d = 2) (h₅ : ∀ d : ℕ, gr d = 2 → ∃ t : T, chef t d) :
  ∀ t : T, ∀ d : ℕ, chef t d → gr d = 2 := by
  sorry"""),
    Theorem("ds_0430_thm_4479", """theorem {name} :
  ∃ (c : ℝ), ∀ (x y z : ℝ), x ≥ 0 → y ≥ 0 → z ≥ 0 →
  x^3 + y^3 + z^3 - 3 * x * y * z ≥ c * (x - y)^2 * (y - z)^2 * (z - x)^2 →
  c = (Real.sqrt 6 + 3 * Real.sqrt 2) / 2 := by
  sorry"""),
    Theorem("ds_0431_thm_4693", """theorem {name} (n : ℕ) (h₀ : 2 ≤ n) :
  ∀ (S : Finset (Fin n × Fin n)), (∀ (a b : Fin n), (a,b) ∈ S → a ≤ b) →
    ∃ (T : Finset (Fin n × Fin n)), T ⊆ S ∧ ∀ (a b : Fin n), (a,b) ∈ T → a ≤ b := by
  sorry"""),
    Theorem("ds_0432_thm_4694", """theorem {name} : ∀ (n : ℕ), n ≥ 4 → n ^ 2 ≤ n ! → ∃ (m : ℕ), m ≤ n ∧ m ^ 2 ≤ n ! := by
  sorry"""),
    Theorem("ds_0433_thm_4888", """theorem {name} (n : ℕ) (h₀ : 0 < n) :
  let board_size := n;
  let total_cells := board_size * board_size;
  let good_paths := 2 * n - 1;
  good_paths ≤ total_cells →
  ∃ (paths : ℕ), paths ≥ good_paths := by
  sorry"""),
    Theorem("ds_0434_thm_4943", """theorem {name} (a b c d e f : ℝ) (h₀ : b = a) (h₁ : c = b / 2) (h₂ : d = c / 2)
  (h₃ : e = d / 2) (h₄ : f = e / 2) (h₅ : f = 3) : a = 48 := by
  sorry"""),
    Theorem("ds_0435_thm_5013", """theorem {name} (k : ℕ) (h₀ : k > 0) (b : ℕ) (h₁ : b > 1) (w : ℕ) (h₂ : w > 1) (h₃ : w < b) :
    let white_pearl := w;
    let black_pearl := b;
    let steps := k;
    let remaining_pearls := black_pearl - white_pearl;
    remaining_pearls ≥ 2 → ∃ black_pearl : ℕ, black_pearl > 0 := by
  sorry"""),
    Theorem("ds_0436_thm_5015", """theorem {name} (AB BC AC : ℝ) (h₀ : AB = 13) (h₁ : BC = 14) (h₂ : AC = 15)
  (AD : ℝ) (h₃ : AD = 99 / Real.sqrt 148) :
  ∃ (HD HA : ℝ), HD / HA = 5 / 11 := by
  sorry"""),
    Theorem("ds_0437_thm_0", """theorem {name} : 
  let h := (3 : ℝ) / 2;
  let n := 5;
  h^n ≤ 0.5 → false := by
  sorry"""),
    Theorem("ds_0438_thm_35", """theorem {name} (n : ℕ) :
  let f (n : ℕ) := 2 * n - (1 + Nat.sqrt (8 * n - 7)) / 2;
  let g (n : ℕ) := 2 * n + (1 + Nat.sqrt (8 * n - 7)) / 2;
  n ≥ 1 → ∃ n, f n = 0 ∨ g n = 0 → ∀ m, ∃ n, f n = m ∨ g n = m → n = m := by
  sorry"""),
    Theorem("ds_0439_thm_46", """theorem {name} :
    ∀ f : ℝ → ℝ, (∀ x y : ℝ, f (Nat.floor x * y) = f x * Nat.floor (f y)) →
    (∀ x : ℝ, f x = 0) ∨ (∀ x : ℝ, f x = x) ∨ (∀ x : ℝ, f x = 2 * x - 1) →
    ∀ x : ℝ, f x = 0 ∨ f x = x ∨ f x = 2 * x - 1 := by
  sorry"""),
    Theorem("ds_0440_thm_141", """theorem {name} :
  ∀ k : ℕ, k ≠ 1 → ∃ (dissectedIntoTwoSimilarPolygons : Prop), dissectedIntoTwoSimilarPolygons ↔ (k ≠ 1) := by
  sorry"""),
    Theorem("ds_0441_thm_147", """theorem {name} (a b c d : ℂ) (h₀ : a ≠ 0 ∨ b ≠ 0 ∨ c ≠ 0 ∨ d ≠ 0)
    (h₁ : ∀ z : ℂ, (z ^ 4 + a * z ^ 3 + b * z ^ 2 + c * z + d = 0)) :
    ∃ (x y : ℂ), x + y = 3 + 4 * Complex.I := by
  sorry"""),
    Theorem("ds_0442_thm_223", """theorem {name} : 
  ∀ k : ℕ, k ≥ 2 → ∀ (a : ℕ → ℝ), (∀ n, a n = a 1 + (n - 1) * a 2) → ∀ (b : ℕ → ℝ), (∀ n, b n = b 1 + (n - 1) * b 2) → 
    (∀ n, a n = b n) → ∀ (S : ℕ → ℝ), (∀ n, S n = ∑ k in Finset.range n, a k) → 
    (∀ n, S n = 32) → ∃ (k : ℕ), k = 4 ∨ k = 5 := by
  sorry"""),
    Theorem("ds_0443_thm_225", """theorem {name} (n : ℕ) (h₀ : Even n) :
  ∃ (largest_size_clique : ℕ), Even largest_size_clique := by
  sorry"""),
    Theorem("ds_0444_thm_272", """theorem {name} (C : ℝ → ℝ → Prop) (l : ℝ → ℝ → ℝ) (h₀ : ∀ x y, C x y ↔ x ^ 2 + (y + 1) ^ 2 = 1)
  (h₁ : ∀ x y, l x y = 2 * x + 2 * y + 1) (h₂ : ∀ x y, C x y → l x y = 0) (h₃ : ∀ x y, l x y = 0 → C x y)
  (h₄ : ∀ x y, C x y → ∀ z, C z y → l x z = l z y) : ∀ x y, C x y → ∀ z, C z y → l x z = l z y := by
  sorry"""),
    Theorem("ds_0445_thm_285", """theorem {name} (h₀ : ∀ n : ℕ, n > 0 → (2^n - 1 : ℕ) = (2^n - 1 : ℤ)) :
  ∀ n : ℕ, n > 0 → (2^n - 1 : ℕ) = (2^n - 1 : ℤ) → ∃ k : ℕ, k > 0 ∧ (2^k - 1 : ℕ) = (2^k - 1 : ℤ) := by
  sorry"""),
    Theorem("ds_0446_thm_295", """theorem {name} (a p : ℝ) (h₀ : a > 0) (h₁ : p > 0) :
  let AB := a;
  let A := p / 2;
  let B := p / 2;
  let C := (p / 2) * (a / p);
  let D := (p / 2) * (a / p);
  let S_CDP := 1/2 * (a / 2) * (p / 2);
  let S_ABCD := a * (p / 2);
  S_CDP / S_ABCD = 1 / 4 →
  ∃ (S_1 S_2 : ℝ), S_1 / S_2 = 1 / 4 := by
  sorry"""),
    Theorem("ds_0447_thm_311", """theorem {name} (a : ℕ → ℕ) (h₀ : ∀ k : ℕ, a (k + 1) > 0) (h₁ : ∀ n : ℕ,
    (∑ i in Finset.range (n + 1), a (n - i) * a i) = (∑ i in Finset.range (n + 1), a (n - i)) ^ 2) :
    ∀ n : ℕ, ∃ k : ℕ, a n = a k := by
  sorry"""),
    Theorem("ds_0448_thm_357", """theorem {name} (S : ℝ → ℝ) (h₀ : ∀ x y z, x + y + z = 0 → S x + S y + S z = 0)
  (h₁ : ∀ x y z, x + y + z = 0 → S (x + y) + S (y + z) + S (z + x) = 0) :
  (∀ x y z, x + y + z = 0 → S x + S y + S z = 0) → (∀ x y z, x + y + z = 0 → S (x + y) + S (y + z) + S (z + x) = 0) →
  ∃ m n : ℕ, (m : ℝ) / n = 2 / 3 := by
  sorry"""),
    Theorem("ds_0449_thm_385", """theorem {name} (f : ℝ → ℝ) :
  ∀ x y : ℝ, f (x - f y) > y * f x + x → (∃ x y : ℝ, f (x - f y) > y * f x + x) := by
  sorry"""),
    Theorem("ds_0450_thm_401", """theorem {name} : 
  ∀ n : ℕ, n ≥ 1 → ∀ t₁ t₂ : ℕ → ℕ, t₁ n < t₂ n → ∃ n : ℕ, n ≥ 1 ∧ t₁ n < t₂ n := by
  sorry"""),
    Theorem("ds_0451_thm_428", """theorem {name} (m : ℕ) (h₀ : m > 1) (h₁ : Odd m) :
    (∃ (a b : Fin m → ℕ) (h₂ : a ≠ b), ∀ (i : Fin m), a i ≠ b i) →
    (∀ (a b : Fin m → ℕ) (h₂ : a ≠ b), ∀ (i : Fin m), a i ≠ b i) →
    ∃ (a b : Fin m → ℕ) (h₂ : a ≠ b), ∀ (i : Fin m), a i ≠ b i := by
  sorry"""),
    Theorem("ds_0452_thm_460", """theorem {name} (C : ℝ × ℝ) (F₁ F₂ A : ℝ × ℝ) (h₀ : F₁ = (1, 0)) (h₁ : F₂ = (-1, 0)) (h₂ : A = (0, 1)) (h₃ : C.1 = 0) (h₄ : C.2 = 0) (h₅ : ∀ x y, x^2 / a^2 + y^2 / b^2 = 1) (h₆ : F₁ ≠ F₂) (h₇ : dist F₁ A = 1) (h₈ : dist F₂ A = 1) : C = (0, 0) ∨ C = (0, -1) := by
  sorry"""),
    Theorem("ds_0453_thm_470", """theorem {name} : ∀ p : ℕ, Nat.Prime p →
  ∀ x y : ℤ, x ^ 2 + x * y + y ^ 2 = (x + y) ^ 3 / 3 + (x + y) ^ 2 / 2 →
  (∃ x y : ℤ, x ^ 2 + x * y + y ^ 2 = (x + y) ^ 3 / 3 + (x + y) ^ 2 / 2) := by
  sorry"""),
    Theorem("ds_0454_thm_490", """theorem {name} (a : ℝ) (h₀ : 0 < a) :
  ∀ (x : ℕ), x > 100 → ∀ (y : ℝ), y = (60 - 0.02 * x) → ∀ (W : ℝ), W = (x - 100) * y - 40 * x →
  W > 6000 → ∃ (x : ℕ), x > 100 ∧ (x - 100) * y - 40 * x > 6000 := by
  sorry"""),
    Theorem("ds_0455_thm_645", """theorem {name} (a : ℕ → ℝ) (h₀ : ∀ n, 0 < a n) (h₁ : 2 * a 1 + 3 * a 2 = 33) (h₂ : a 2 * a 4 = 27 * a 3) :
  ∀ n, ∃ b : ℕ → ℝ, b n = n + 1 := by
  sorry"""),
    Theorem("ds_0456_thm_656", """theorem {name} (a : ℕ) (h₀ : a % 35 = 23) : a % 7 = 2 := by
  sorry"""),
    Theorem("ds_0457_thm_659", """theorem {name} :
  ∀ n : ℕ, n ≥ 1 → ∀ a : ℕ → ℝ, a 1 = 2 → a 2 = 6 → ∀ S : ℕ → ℝ, S 1 = a 1 → S 2 = a 1 + a 2 →
    ∀ d : ℝ, d = a 2 - a 1 → ∀ n : ℕ, n ≥ 1 →
    ∑ i in Finset.range n, (1 / (S i + d)) < 2016 / 2017 →
    ∃ n : ℕ, n ≥ 1 ∧ ∑ i in Finset.range n, (1 / (S i + d)) < 2016 / 2017 := by
  sorry"""),
    Theorem("ds_0458_thm_695", """theorem {name} : 
  (Finset.card (Finset.filter (fun x => x = 1 / 3) (Finset.range (5^7)))) / (Finset.card (Finset.range (5^7))) = 1 / 3 := by
  sorry"""),
    Theorem("ds_0459_thm_853", """theorem {name} (a b c : ℝ) (h₀ : a ≠ 0 ∨ b ≠ 0 ∨ c ≠ 0)
    (h₁ : a * (2 - a) ≤ 1) (h₂ : b * (2 - b) ≤ 1) (h₃ : c * (2 - c) ≤ 1) :
    (a - 1) ^ 2 + (b - 1) ^ 2 + (c - 1) ^ 2 ≥ 0 := by
  sorry"""),
    Theorem("ds_0460_thm_915", """theorem {name} (S : ℕ → ℝ) (h₀ : ∀ n : ℕ, S n = 2 * n + 1) (h₁ : ∀ n : ℕ, n ≠ 0 → S n = S (n - 1) + 2) :
    (∀ n : ℕ, n ≠ 0 → S n = S (n - 1) + 2) → ∃ T : ℕ → ℝ, (∀ n : ℕ, T n = -n / (n + 1)) → ∃ T : ℕ → ℝ, (∀ n : ℕ, T n = -n / (n + 1)) := by
  sorry"""),
    Theorem("ds_0461_thm_1011", """theorem {name} : 
  ∀ (n : ℕ), n % 3 = 0 → ∃ (blackWins : Prop), blackWins = (n % 3 = 0) := by
  sorry"""),
    Theorem("ds_0462_thm_1058", """theorem {name} (x : ℝ) (h₀ : Real.logb 2 x * Real.logb 4 x * Real.logb 8 x = 1) :
  x = 64 ∨ x = 1 / 4 → x = 64 ∨ x = 1 / 4 ∨ x = 1 / 2 := by
  sorry"""),
    Theorem("ds_0463_thm_1116", """theorem {name} (p : ℝ) (h₀ : 0 < p) :
    (∃ x : ℝ, x > 0 ∧ p * x - (p / x) - 2 * Real.log x > 0) →
    (∀ x : ℝ, x > 0 → p * x - (p / x) - 2 * Real.log x > 0) →
    (∃ p : ℝ, p > 0 ∧ ∀ x : ℝ, x > 0 → p * x - (p / x) - 2 * Real.log x > 0) := by
  sorry"""),
    Theorem("ds_0464_thm_1150", """theorem {name} :
    ∀ f : ℝ → ℝ, (∀ x y : ℝ, f (Int.floor x * y) = f x * f (Int.floor y)) →
    (∀ x : ℝ, f x = 0) ∨ (∀ x : ℝ, f x = x + 1) ∨ (∀ x : ℝ, f x = 2 * x + 1) →
    ∀ x : ℝ, f x = x + 1 ∨ f x = 2 * x + 1 ∨ f x = 0 := by
  sorry"""),
    Theorem("ds_0465_thm_1186", """theorem {name} (f : ℝ → ℝ) (h₀ : ∀ x, f x = exp x - cos x) (h₁ : ∀ n : ℕ, n ≥ 2 → f (aₙ) = aₙ⁻¹) (h₂ : ∀ n : ℕ, n ≥ 2 → aₙ > 0) : ∀ n : ℕ, n ≥ 2 → aₙ⁻¹ > aₙ + aₙ ^ 2 → ∃ n : ℕ, n ≥ 2 ∧ aₙ⁻¹ > aₙ + aₙ ^ 2 := by
  sorry"""),
    Theorem("ds_0466_thm_1204", """theorem {name} (n : ℕ) (h₀ : n > 3) :
    let m := n * (n - 3);
    let d := (n - 2) * (n - 2);
    let rhombuses := m / 2;
    let triangles := d / 2;
    rhombuses - triangles = 6 * n - 9 →
    ∃ rhombuses triangles : ℕ, rhombuses - triangles = 6 * n - 9 := by
  sorry"""),
    Theorem("ds_0467_thm_1264", """theorem {name} : 
  ∀ (f : ℝ → ℝ) (h : ∀ x, f x = x^2), 
    (∀ x, f (x^2) = (f x)^2) → 
    (∀ x, f (x^2) = (f x)^2) → 
    ∃ (f : ℝ → ℝ), ∀ x, f x = x^2 := by
  sorry"""),
    Theorem("ds_0468_thm_1307", """theorem {name} :
  ∀ a : ℕ, ∀ x : Finset ℤ, (∀ n : ℤ, n ∈ x ↔ (n : ℤ) % (a : ℤ) = (n : ℤ) % (a : ℤ)) →
    ∃ y : Finset ℤ, ∀ n : ℤ, n ∈ y ↔ (n : ℤ) % (a : ℤ) = (n : ℤ) % (a : ℤ) := by
  sorry"""),
    Theorem("ds_0469_thm_1321", """theorem {name} (n : ℕ) (h₀ : 2 ≤ n) :
  let a_n := ∑ k in Finset.range n, 1 / (k + 1);
  let a_n_plus_one := ∑ k in Finset.range (n + 1), 1 / (k + 1);
  a_n_plus_one < a_n → ∃ n, n ≥ 2 ∧ a_n_plus_one < a_n := by
  sorry"""),
    Theorem("ds_0470_thm_1371", """theorem {name} :
  ∀ a₁ a₂ : ℕ, a₁ ≠ 0 → a₂ ≠ 0 → (∀ n : ℕ, n ≥ 2 → a₁ / a₂ = a₂ / a₁ → a₁ % 2 = 1 → a₂ % 2 = 1 → ∃ a₃ : ℕ, a₃ % 2 = 1) := by
  sorry"""),
    Theorem("ds_0471_thm_1469", """theorem {name} (p : ℕ) (hp : p > 3) (h₀ : Nat.Prime p) (h₁ : Nat.Prime (p + 2)) :
    (p + 1) % 6 = 0 → p % 6 = 1 ∨ p % 6 = 5 := by
  sorry"""),
    Theorem("ds_0472_thm_1655", """theorem {name} (a : ℕ → ℝ) (S : ℕ → ℝ) (h₀ : ∀ n, S n = n * (a 1 + a n) / 2)
    (h₁ : ∀ n, n ≠ 0 → a n = a 1 + (n - 1) * (a 2 - a 1)) (h₂ : a 2 = a 1 + S 1) :
    (∃ n : ℕ, n > 0 ∧ S n > a n) → ∃ n : ℕ, n = 7 := by
  sorry"""),
    Theorem("ds_0473_thm_1695", """theorem {name} :
    (∀ x : ℕ, 2^(x^2 - 3*x - 2) = 4^(x - 4) → x = 5) →
    ∃ x : ℕ, x = 5 := by
  sorry"""),
    Theorem("ds_0474_thm_1819", """theorem {name} :
  ∀ (n : ℕ), n > 0 → (n % 100 + 50) % 100 = 25 → n % 100 = 75 → ∃ (n : ℕ), n > 0 ∧ n % 100 = 75 := by
  sorry"""),
    Theorem("ds_0475_thm_1897", """theorem {name} : (∀ x : ℝ, (∃ x' : ℝ, x' ^ 2 = 19 - 2 * x ^ 2) → x = 0) →
    (∀ x : ℝ, x ^ 2 = 19 - 2 * x ^ 2 → x = 0) → 0 = 0 := by
  sorry"""),
    Theorem("ds_0476_thm_1937", """theorem {name} :
  ∀ n : ℕ, n < 2019 → (∑ i in (Nat.digits 7 n).toFinset, i) = 22 →
    ∃ n : ℕ, n < 2019 ∧ (∑ i in (Nat.digits 7 n).toFinset, i) = 22 := by
  sorry"""),
    Theorem("ds_0477_thm_2118", """theorem {name} : 
  ∀ (n : ℕ) (a : ℝ) (I : Fin n → ℝ), 
    (∀ i, I i = a) → 
    (∀ i j, I i = I j → i = j) → 
    ∃ (n : ℕ) (I : Fin n → ℝ), ∀ i j, I i = I j → i = j := by
  sorry"""),
    Theorem("ds_0478_thm_2119", """theorem {name} (t : ℝ) (h₀ : 0 < t) (h₁ : t < 1) :
    (∀ g ∈ ({{g | ∃ (x y : ℝ), g = x + y}} : Set ℝ), ∃ (r : ℝ), r > 0 ∧ r < 1) →
    (∀ g ∈ ({{g | ∃ (x y : ℝ), g = x + y}} : Set ℝ), ∃ (r : ℝ), r > 0 ∧ r < 1) →
    ∃ (t : ℝ), t > 0 ∧ t < 1 := by
  sorry"""),
    Theorem("ds_0479_thm_2145", """theorem {name} (a₁ a₂ a₃ a₄ a₅ a₆ : ℕ)
    (h₀ : a₁ + a₂ + a₃ + a₄ + a₅ + a₆ = 990)
    (h₁ : a₆ = 2 * a₁)
    (h₂ : a₂ = a₁ + d)
    (h₃ : a₃ = a₁ + 2 * d)
    (h₄ : a₄ = a₁ + 3 * d)
    (h₅ : a₅ = a₁ + 4 * d)
    (h₆ : a₆ = a₁ + 5 * d) :
    a₆ = 220 ∨ a₆ = 180 ∨ a₆ = 170 ∨ a₆ = 160 ∨ a₆ = 150 ∨ a₆ = 140 := by
  sorry"""),
    Theorem("ds_0480_thm_2159", """theorem {name} (x : ℝ) (h₀ : Real.log (x + 3) + Real.log (x - 1) = Real.log (x ^ 2 - 2 * x - 3)) :
    x = 0 ∨ x = -3 ∨ x = 1 ∨ x = 5 → x = 0 ∨ x = -3 ∨ x = 1 ∨ x = 5 ∨ x = -3 := by
  sorry"""),
    Theorem("ds_0481_thm_2283", """theorem {name} (B T : ℕ → ℕ) (h₀ : ∀ n : ℕ, T (n + 1) = 2 ^ T n) (h₁ : ∀ n : ℕ, B n = (T (2009)) ^ (T (2009)) ^ (T 2009)) :
  (∀ k : ℕ, (∃ n : ℕ, B n > 2 ^ k) → (∃ n : ℕ, B n > 2 ^ (k + 1))) → ∃ k : ℕ, 2009 = k := by
  sorry"""),
    Theorem("ds_0482_thm_2550", """theorem {name} : ∃ N : ℕ, (N % 100 + (N / 100)) ^ 2 = N % 100 + (N / 100) → N = 11 ∨ N = 19 ∨ N = 37 ∨ N = 73 := by
  sorry"""),
    Theorem("ds_0483_thm_3020", """theorem {name} (X : ℕ) (h₀ : X % 3 = 2) (h₁ : X % 5 = 4) : 14 ≤ X := by
  sorry"""),
    Theorem("ds_0484_thm_3041", """theorem {name} (Z : ℕ) (h₀ : Z % 1000 = 997) (h₁ : Z / 1000 = 997) : 11 ∣ Z := by
  sorry"""),
    Theorem("ds_0485_thm_3115", """theorem {name} (n k : ℕ) (h₀ : k ≤ n) (h₁ : n ≠ 0) (h₂ : k % 2 = 1) (h₃ : k ≤ n / 2) :
    (n / k) + 1 ≤ 60 ∨ (n / k) + 1 > 60 := by
  sorry"""),
    Theorem("ds_0486_thm_3172", """theorem {name} (A B C D E F G H : ℕ) (h₀ : C = 5) (h₁ : ∀ x, x = A ∨ x = B ∨ x = C ∨ x = D ∨ x = E ∨ x = F ∨ x = G ∨ x = H → x ≥ 0)
    (h₂ : A + B + C = 30) (h₃ : B + C + D = 30) (h₄ : C + D + E = 30) (h₅ : D + E + F = 30) (h₆ : E + F + G = 30)
    (h₇ : F + G + H = 30) : A + H = 25 := by
  sorry"""),
    Theorem("ds_0487_thm_3249", """theorem {name} (a : ℝ) (h₀ : Real.tan a + Real.cos a = 2) :
  Real.cos a = 1 ∨ Real.cos a = 2 ∨ Real.cos a = 1 / 2 ∨ Real.cos a = -1 ∨ Real.cos a = -2 ∨ Real.cos a = -1 / 2 →
  Real.cos a = 1 ∨ Real.cos a = 2 ∨ Real.cos a = 1 / 2 ∨ Real.cos a = -1 ∨ Real.cos a = -2 ∨ Real.cos a = -1 / 2 ∨
  ¬Real.cos a = 1 ∨ ¬Real.cos a = 2 ∨ ¬Real.cos a = 1 / 2 ∨ ¬Real.cos a = -1 ∨ ¬Real.cos a = -2 ∨ ¬Real.cos a = -1 / 2 := by
  sorry"""),
    Theorem("ds_0488_thm_3327", """theorem {name} (mary alice : ℝ) (h₀ : mary / alice = 3 / 5) (h₁ : alice = 30) : mary = 18 := by
  sorry"""),
    Theorem("ds_0489_thm_3351", """theorem {name} : 
  ∀ (a₀ a₁ a₂ a₃ : ℕ), a₀ > a₁ → a₁ > a₂ → a₂ > a₃ → 
    (∀ (n : ℕ), n ≠ 0 → (1 - (1 : ℝ) / a₁) + (1 - (1 : ℝ) / a₂) + (1 - (1 : ℝ) / a₃) = 2 * (1 - (1 : ℝ) / a₀)) →
    (a₀, a₁, a₂, a₃) = (24, 4, 3, 2) ∨ (a₀, a₁, a₂, a₃) = (60, 5, 3, 2) →
    ∃ (a₀ a₁ a₂ a₃ : ℕ), a₀ > a₁ → a₁ > a₂ → a₂ > a₃ → 
      (∀ (n : ℕ), n ≠ 0 → (1 - (1 : ℝ) / a₁) + (1 - (1 : ℝ) / a₂) + (1 - (1 : ℝ) / a₃) = 2 * (1 - (1 : ℝ) / a₀)) →
      (a₀, a₁, a₂, a₃) = (24, 4, 3, 2) ∨ (a₀, a₁, a₂, a₃) = (60, 5, 3, 2) := by
  sorry"""),
    Theorem("ds_0490_thm_3412", """theorem {name} (ABC : ℝ) (h₀ : 0 < ABC) (h₁ : ABC < 2 * Real.pi) :
  let D := Real.sin (ABC / 2);
  let E := Real.sin (ABC / 2);
  let P := Real.sin (ABC / 2);
  let Q := Real.sin (ABC / 2);
  ∃ (K : ℝ), K = 90 ↔ ABC = 90 := by
  sorry"""),
    Theorem("ds_0491_thm_3453", """theorem {name} (n : ℕ) (h₀ : n ≥ 2) (x : Fin n → ℝ) (h₁ : ∀ i, x i = (∑ j in Finset.univ, x j) ^ 2018)
  (h₂ : ∀ i j, i ≠ j → x i = x j) : (∀ i, x i = 0) → (∀ i, x i = 0) ∨ (∀ i, x i = 0) → (∀ i, x i = 0) := by
  sorry"""),
    Theorem("ds_0492_thm_3467", """theorem {name} (n k : ℕ) (h₀ : n > 0) (h₁ : k > 0) (h₂ : k ≤ 2 * n) : 
  (∀ n k : ℕ, n > 0 → k > 0 → k ≤ 2 * n → (∀ n k : ℕ, n > 0 → k > 0 → k ≤ 2 * n → k = n ∨ k = n + 1 ∨ k = n + 2)) →
  k = n ∨ k = n + 1 ∨ k = n + 2 := by
  sorry"""),
    Theorem("ds_0493_thm_3582", """theorem {name} (N : ℕ) (h₀ : N % 7 ^ 3 = 0) (h₁ : N % 7 ^ 2 % 7 ^ 1 = 0) (h₂ : N % 7 ^ 1 % 7 ^ 0 = 0) (h₃ : N / 7 ^ 0 % 9 = 1) : N % 7 ^ 1 = 0 := by
  sorry"""),
    Theorem("ds_0494_thm_3685", """theorem {name} (f : ℤ → ℤ) (h₀ : ∀ x y, f (x - f y) = f (f x) - f y - 1) :
    (∀ x, f x = -1) ∨ (∃ x, f x = -1) ∨ (∀ x, f x = x + 1) ∨ (∃ x, f x = x + 1) ∨
    (∀ x, f x = -1) ∨ (∃ x, f x = -1) ∨ (∀ x, f x = x + 1) ∨ (∃ x, f x = x + 1) →
    (∀ x, f x = -1) ∨ (∃ x, f x = -1) ∨ (∀ x, f x = x + 1) ∨ (∃ x, f x = x + 1) := by
  sorry"""),
    Theorem("ds_0495_thm_3744", """theorem {name} :
  ∀ A : Set ℕ, (∀ n : ℕ, n ∈ A ↔ ∃ m : ℕ, m ∈ Finset.range n ∧ 2 ^ m ∈ A) →
    (∀ a : ℕ, a ∈ A → a ≠ 1 → ∃ b : ℕ, b ∈ A ∧ b < 2 * a - 1) →
    ∀ a : ℕ, a ∈ A → a ≠ 1 → ∃ b : ℕ, b ∈ A ∧ b < 2 * a - 1 := by
  sorry"""),
    Theorem("ds_0496_thm_3915", """theorem {name} (x : ℝ) (h₀ : x ≠ 0) (h₁ : ∀ y : ℝ, y ≠ 0 → y = x ∨ y = ⌊x⌋) :
    x = 3 / 2 ∨ x = 1 ∨ x = 2 ∨ x = 3 ∨ x = 4 → x = 3 / 2 ∨ x = 1 ∨ x = 2 ∨ x = 3 ∨ x = 4 ∨ x = 5 := by
  sorry"""),
    Theorem("ds_0497_thm_4208", """theorem {name} (T : ℕ) (h₀ : T = Nat.choose 4046 2023 / Nat.choose 2023 2022) :
  T = Nat.choose 4046 2023 / Nat.choose 2023 2022 := by
  sorry"""),
    Theorem("ds_0498_thm_4609", """theorem {name} (n : ℕ) (h₀ : n % 56 = 29) : n % 8 = 5 := by
  sorry"""),
    Theorem("ds_0499_thm_4799", """theorem {name} (y : ℝ) (h₀ : y^3 - 6*y^2 + 7*y - 1 = 0) :
  let x := y^2;
  x^2 - 6*x + 7 = 0 →
  y^2 = 2 →
  y = 2 ∨ y = -1 →
  y^3 - 6*y^2 + 7*y - 1 = 0 := by
  sorry"""),
]
