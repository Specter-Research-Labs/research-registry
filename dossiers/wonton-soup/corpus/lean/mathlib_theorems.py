# ruff: noqa: E501
"""
Mathlib4 theorems with non-trivial tactic proofs.

Extracted and validated 142 theorems from current mathlib4.
Each theorem has 3-12 tactic proof lines for interesting proof graphs.
"""
from corpus.lean.theorems import Theorem

MATHLIB_CORPUS: list[Theorem] = [
    Theorem("ml_000_UniqueFactorizationMonoid_primeFactors_m", """theorem {name} [DecidableEq M] (ha : a ≠ 0) (hb : b ≠ 0) :
    primeFactors (a * b) = primeFactors a ∪ primeFactors b := by
  sorry"""),
    Theorem("ml_001_isClosed_property", """theorem {name} [TopologicalSpace β] {{e : α → β}} {{p : β → Prop}} (he : DenseRange e)
    (hp : IsClosed {{ x | p x }}) (h : ∀ a, p (e a)) : ∀ b, p b := by
  sorry"""),
    Theorem("ml_002_Function_Semiconj", """theorem {name}.symm_adjoint [PartialOrder α] [Preorder β] {{fa : α ≃o α}} {{fb : β ↪o β}} {{g : α → β}}
    (h : Function.Semiconj g fa fb) {{g' : β → α}} (hg' : IsOrderRightAdjoint g g') :
    Function.Semiconj g' fb fa := by
  sorry"""),
    Theorem("ml_003_Set_wellFoundedOn_range", """theorem {name} : (range f).WellFoundedOn r ↔ WellFounded (r on f) := by
  sorry"""),
    Theorem("ml_004_Nat", """theorem {name}.emultiplicity_pow_sub_pow {{x y : ℕ}} (hxy : p ∣ x - y) (hx : ¬p ∣ x) (n : ℕ) :
    emultiplicity p (x ^ n - y ^ n) = emultiplicity p (x - y) + emultiplicity p n := by
  sorry"""),
    Theorem("ml_005_Nat_snd_mem_divisors_of_mem_antidiagonal", """theorem {name} {{x : ℕ × ℕ}} (h : x ∈ divisorsAntidiagonal n) :
    x.snd ∈ divisors n := by
  sorry"""),
    Theorem("ml_006_Algebra_FiniteType_isNoetherianRing", """theorem {name} (R S : Type*) [CommRing R] [CommRing S] [Algebra R S]
    [h : Algebra.FiniteType R S] [IsNoetherianRing R] : IsNoetherianRing S := by
  sorry"""),
    Theorem("ml_007_Real_geom_mean_eq_arith_mean_weighted_if", """theorem {name}' (w z : ι → ℝ) (hw : ∀ i ∈ s, 0 < w i)
    (hw' : ∑ i ∈ s, w i = 1) (hz : ∀ i ∈ s, 0 ≤ z i) :
    ∏ i ∈ s, z i ^ w i = ∑ i ∈ s, w i * z i ↔ ∀ j ∈ s, z j = ∑ i ∈ s, w i * z i := by
  sorry"""),
    Theorem("ml_008_exists_pow_lt_", """theorem {name} {{G : Type*}} [LinearOrderedCommGroupWithZero G] [MulArchimedean G]
    {{a : G}} (ha : a < 1) (b : Gˣ) : ∃ n : ℕ, a ^ n < b := by
  sorry"""),
    Theorem("ml_009_pmul_comm", """theorem {name} [CommMonoidWithZero R] (f g : ArithmeticFunction R) : f.pmul g = g.pmul f := by
  sorry"""),
    Theorem("ml_010_exists_increasing_or_nonincreasing_subse", """theorem {name}' (r : α → α → Prop) (f : ℕ → α) :
    ∃ g : ℕ ↪o ℕ,
      (∀ n : ℕ, r (f (g n)) (f (g (n + 1)))) ∨ ∀ m n : ℕ, m < n → ¬r (f (g m)) (f (g n)) := by
  sorry"""),
    Theorem("ml_011_Nat_fermatNumber_eq_fermatNumber_sq_sub_", """theorem {name} (n : ℕ) :
    fermatNumber (n + 2) = (fermatNumber (n + 1)) ^ 2 - 2 * (fermatNumber n - 1) ^ 2 := by
  sorry"""),
    Theorem("ml_012_Nat_pow_mul_mem_factoredNumbers", """theorem {name} {{s : Finset ℕ}} {{p n : ℕ}} (hp : p.Prime) (e : ℕ)
    (hn : n ∈ factoredNumbers s) :
    p ^ e * n ∈ factoredNumbers (insert p s) := by
  sorry"""),
    Theorem("ml_013_Set_bounded_lt_inter_lt", """theorem {name} [LinearOrder α] [NoMaxOrder α] (a : α) :
    Bounded (· < ·) (s ∩ {{ b | a < b }}) ↔ Bounded (· < ·) s := by
  sorry"""),
    Theorem("ml_014_Nat_sorted_divisorsAntidiagonalList_fst", """theorem {name} {{n : ℕ}} :
    n.divisorsAntidiagonalList.Sorted (·.fst < ·.fst) := by
  sorry"""),
    Theorem("ml_015_Set_exists_monotone_Icc_subset_open_cove", """theorem {name} {{ι}} {{a b : ℝ}} (h : a ≤ b) {{c : ι → Set (Icc a b)}}
    (hc₁ : ∀ i, IsOpen (c i)) (hc₂ : univ ⊆ ⋃ i, c i) : ∃ t : ℕ → Icc a b, t 0 = a ∧
      Monotone t ∧ (∃ m, ∀ n ≥ m, t n = b) ∧ ∀ n, ∃ i, Icc (t n) (t (n + 1)) ⊆ c i := by
  sorry"""),
    Theorem("ml_016_NFA_to_NFA__Closure", """theorem {name} (M : NFA α σ) (S : Set σ) : M.toεNFA.εClosure S = S := by
  sorry"""),
    Theorem("ml_017_Nat_not_pseudoperfect_iff_forall", """theorem {name} :
    ¬ Pseudoperfect n ↔ n = 0 ∨ ∀ s ⊆ properDivisors n, ∑ i ∈ s, i ≠ n := by
  sorry"""),
    Theorem("ml_018_WithBot_unbot_eq_iff", """theorem {name} {{a : WithBot α}} {{b : α}} (h : a ≠ ⊥) :
    a.unbot h = b ↔ a = b := by
  sorry"""),
    Theorem("ml_019_Nat_dvd_setGcd_iff", """theorem {name} : n ∣ setGcd s ↔ ∀ m ∈ s, n ∣ m := by
  sorry"""),
    Theorem("ml_020_Set_PartiallyWellOrderedOn_fiberProdLex", """theorem {name} [Preorder α] [Preorder β] {{s : Set (α ×ₗ β)}}
    (hαβ : s.IsPWO) (a : α) : {{y | toLex (a, y) ∈ s}}.IsPWO := by
  sorry"""),
    Theorem("ml_021_Function_semiconj_of_isLUB", """theorem {name} [PartialOrder α] [Group G] (f₁ f₂ : G →* α ≃o α) {{h : α → α}}
    (H : ∀ x, IsLUB (range fun g' => (f₁ g')⁻¹ (f₂ g' x)) (h x)) (g : G) :
    Function.Semiconj h (f₂ g) (f₁ g) := by
  sorry"""),
    Theorem("ml_022_summable_condensed_iff_of_nonneg", """theorem {name} {{f : ℕ → ℝ}} (h_nonneg : ∀ n, 0 ≤ f n)
    (h_mono : ∀ ⦃m n⦄, 0 < m → m ≤ n → f n ≤ f m) :
    (Summable fun k : ℕ => (2 : ℝ) ^ k * f (2 ^ k)) ↔ Summable f := by
  sorry"""),
    Theorem("ml_023_krullTopology_mem_nhds_one_iff_of_normal", """theorem {name} (K L : Type*) [Field K] [Field L] [Algebra K L]
    [Normal K L] (s : Set Gal(L/K)) : s ∈ 𝓝 1 ↔ ∃ E : IntermediateField K L,
    FiniteDimensional K E ∧ Normal K E ∧ (E.fixingSubgroup : Set Gal(L/K)) ⊆ s := by
  sorry"""),
    Theorem("ml_024_Nat_deficient_iff_not_abundant_and_not_p", """theorem {name} (hn : n ≠ 0) :
    Deficient n ↔ ¬ Abundant n ∧ ¬ Perfect n := by
  sorry"""),
    Theorem("ml_025_Nat_coprime_of_probablePrime", """theorem {name} {{n b : ℕ}} (h : ProbablePrime n b) (h₁ : 1 ≤ n) (h₂ : 1 ≤ b) :
    Nat.Coprime n b := by
  sorry"""),
    Theorem("ml_026_FirstOrder_Language_LHom_funext", """theorem {name} {{F G : L →ᴸ L'}} (h_fun : F.onFunction = G.onFunction)
    (h_rel : F.onRelation = G.onRelation) : F = G := by
  sorry"""),
    Theorem("ml_027_StableUnderComposition", """theorem {name}.respectsIso (hP : RingHom.StableUnderComposition @P)
    (hP' : ∀ {{R S : Type u}} [CommRing R] [CommRing S] (e : R ≃+* S), P e.toRingHom) :
    RingHom.RespectsIso @P := by
  sorry"""),
    Theorem("ml_028_Part_elim_toOption", """theorem {name} {{α β : Type*}} (a : Part α) [Decidable a.Dom] (b : β) (f : α → β) :
    a.toOption.elim b f = if h : a.Dom then f (a.get h) else b := by
  sorry"""),
    Theorem("ml_029_smul_eq_of_le_smul", """theorem {name}
    {{G : Type*}} [Group G] [Finite G] {{α : Type*}} [PartialOrder α] {{g : G}} {{a : α}}
    [MulAction G α] [CovariantClass G α HSMul.hSMul LE.le] (h : a ≤ g • a) : g • a = a := by
  sorry"""),
    Theorem("ml_030_wellFoundedGT_iff_monotone_chain_conditi", """theorem {name}' [Preorder α] :
    WellFoundedGT α ↔ ∀ a : ℕ →o α, ∃ n, ∀ m, n ≤ m → ¬a n < a m := by
  sorry"""),
    Theorem("ml_031_summable_indicator_mod_iff_summable_indi", """theorem {name} {{m : ℕ}} [NeZero m] {{f : ℕ → ℝ}}
    (hf : Antitone f) {{k : ZMod m}} (l : ZMod m)
    (hs : Summable ({{n : ℕ | (n : ZMod m) = k}}.indicator f)) :
    Summable ({{n : ℕ | (n : ZMod m) = l}}.indicator f) := by
  sorry"""),
    Theorem("ml_032_Units", """theorem {name}.mulArchimedean_iff {{G₀}} [LinearOrderedCommGroupWithZero G₀] :
    MulArchimedean G₀ˣ ↔ MulArchimedean G₀ := by
  sorry"""),
    Theorem("ml_033_cmpLE_eq_cmp", """theorem {name} {{α}} [Preorder α] [IsTotal α (· ≤ ·)] [DecidableLE α] [DecidableLT α]
    (x y : α) : cmpLE x y = cmp x y := by
  sorry"""),
    Theorem("ml_034_Real", """theorem {name}.not_summable_indicator_one_div_natCast {{m : ℕ}} (hm : m ≠ 0) (k : ZMod m) :
    ¬ Summable ({{n : ℕ | (n : ZMod m) = k}}.indicator fun n : ℕ ↦ (1 / n : ℝ)) := by
  sorry"""),
    Theorem("ml_035_integral_bernoulliFun_eq_zero", """theorem {name} {{k : ℕ}} (hk : k ≠ 0) :
    ∫ x : ℝ in 0..1, bernoulliFun k x = 0 := by
  sorry"""),
    Theorem("ml_036_IsAntichain", """theorem {name}.finite_of_wellQuasiOrdered {{s : Set α}} (hs : IsAntichain r s)
    (hr : WellQuasiOrdered r) : s.Finite := by
  sorry"""),
    Theorem("ml_037_continuous_uliftMap", """theorem {name} [TopologicalSpace X] [TopologicalSpace Y]
    (f : X → Y) (hf : Continuous f) :
    Continuous (ULift.map f : ULift.{{u'}} X → ULift.{{v'}} Y) := by
  sorry"""),
    Theorem("ml_038_Nat_eq_prod_primes_mul_sq_of_mem_smoothN", """theorem {name} {{n k : ℕ}} (h : n ∈ smoothNumbers k) :
    ∃ s ∈ k.primesBelow.powerset, ∃ m, n = m ^ 2 * (s.prod id) := by
  sorry"""),
    Theorem("ml_039_Nat_pow_add_mul_totient_mod_eq", """theorem {name} {{x k l n : ℕ}} (hn : 1 < n) (h : x.Coprime n) :
    (x ^ (k + l * φ n)) % n = (x ^ k) % n := by
  sorry"""),
    Theorem("ml_040_discreteTopology_iff_nhds", """theorem {name} [TopologicalSpace α] :
    DiscreteTopology α ↔ ∀ x : α, 𝓝 x = pure x := by
  sorry"""),
    Theorem("ml_041_PFun_preimage_comp", """theorem {name} (f : β →. γ) (g : α →. β) (s : Set γ) :
    (f.comp g).preimage s = g.preimage (f.preimage s) := by
  sorry"""),
    Theorem("ml_042_Nat_insert_self_properDivisors", """theorem {name} (h : n ≠ 0) : insert n (properDivisors n) = divisors n := by
  sorry"""),
    Theorem("ml_043_Nat_probablePrime_iff_modEq", """theorem {name} (n : ℕ) {{b : ℕ}} (h : 1 ≤ b) :
    ProbablePrime n b ↔ b ^ (n - 1) ≡ 1 [MOD n] := by
  sorry"""),
    Theorem("ml_044_bernoulli", """theorem {name}'_def' (n : ℕ) :
    bernoulli' n = 1 - ∑ k : Fin n, n.choose k / (n - k + 1) * bernoulli' k := by
  sorry"""),
    Theorem("ml_045_IsOrderRightAdjoint_comp_orderIso", """theorem {name} [Preorder α] [Preorder β] [Preorder γ] {{f : α → β}} {{g : β → α}}
    (h : IsOrderRightAdjoint f g) (e : γ ≃o α) : IsOrderRightAdjoint (f ∘ e) (e.symm ∘ g) := by
  sorry"""),
    Theorem("ml_046_Monoid_exponent_eq_prime_iff", """theorem {name} {{G : Type*}} [Monoid G] [Nontrivial G] {{p : ℕ}} (hp : p.Prime) :
    Monoid.exponent G = p ↔ ∀ g : G, g ≠ 1 → orderOf g = p := by
  sorry"""),
    Theorem("ml_047_IsBezout_dvd_gcd", """theorem {name} (hx : z ∣ x) (hy : z ∣ y) : z ∣ gcd x y := by
  sorry"""),
    Theorem("ml_048_Topology_image_snd_preimageImageRestrict", """theorem {name} [∀ i, TopologicalSpace (α i)] :
    Prod.snd '' (Homeomorph.preimageImageRestrict α S s ''
        ((fun (x : Sᶜ.restrict ⁻¹' (Sᶜ.restrict '' s)) ↦ (x : Π j, α j)) ⁻¹' s))
      = S.restrict '' s := by
  sorry"""),
    Theorem("ml_049_Nat_primeFactors_subset_of_mem_factoredN", """theorem {name} {{s : Finset ℕ}} {{m : ℕ}}
    (hm : m ∈ factoredNumbers s) :
    m.primeFactors ⊆ s := by
  sorry"""),
    Theorem("ml_050_Nat_Prime", """theorem {name}.divisors {{p : ℕ}} (pp : p.Prime) : divisors p = {{1, p}} := by
  sorry"""),
    Theorem("ml_051_summable_bernoulli_fourier", """theorem {name} {{k : ℕ}} (hk : 2 ≤ k) :
    Summable (fun n => -k ! / (2 * π * I * n) ^ k : ℤ → ℂ) := by
  sorry"""),
    Theorem("ml_052_sSupIndep_iff", """theorem {name} {{α : Type*}} [CompleteLattice α] (s : Set α) :
    sSupIndep s ↔ iSupIndep ((↑) : s → α) := by
  sorry"""),
    Theorem("ml_053_Mathlib_Meta_mersenne_mod_four", """theorem {name} {{n : ℕ}} (h : 2 ≤ n) : mersenne n % 4 = 3 := by
  sorry"""),
    Theorem("ml_054_Int", """theorem {name}.sq_ne_two_mod_four (z : ℤ) : z * z % 4 ≠ 2 := by
  sorry"""),
    Theorem("ml_055_reverse_lucas_primality", """theorem {name} (p : ℕ) (hP : p.Prime) :
    ∃ a : ZMod p, a ^ (p - 1) = 1 ∧ ∀ q : ℕ, q.Prime → q ∣ p - 1 → a ^ ((p - 1) / q) ≠ 1 := by
  sorry"""),
    Theorem("ml_056_bernoulli", """theorem {name}'_def' (n : ℕ) :
    bernoulli' n = 1 - ∑ k : Fin n, n.choose k / (n - k + 1) * bernoulli' k := by
  sorry"""),
    Theorem("ml_057_PresentedGroup_generated_by", """theorem {name} (rels : Set (FreeGroup α)) (H : Subgroup (PresentedGroup rels))
    (h : ∀ j : α, PresentedGroup.of j ∈ H) (x : PresentedGroup rels) : x ∈ H := by
  sorry"""),
    Theorem("ml_058_geomSum_ofColex_strictMono", """theorem {name} (hn : 2 ≤ n) : StrictMono fun s ↦ ∑ k ∈ ofColex s, n ^ k := by
  sorry"""),
    Theorem("ml_059_ZMod", """theorem {name}.isSquare_neg_one_of_dvd {{m n : ℕ}} (hd : m ∣ n) (hs : IsSquare (-1 : ZMod n)) :
    IsSquare (-1 : ZMod m) := by
  sorry"""),
    Theorem("ml_060_eq_iff_eq_on_prime_powers", """theorem {name} [CommMonoidWithZero R] (f : ArithmeticFunction R)
    (hf : f.IsMultiplicative) (g : ArithmeticFunction R) (hg : g.IsMultiplicative) :
    f = g ↔ ∀ p i : ℕ, Nat.Prime p → f (p ^ i) = g (p ^ i) := by
  sorry"""),
    Theorem("ml_061_Nat_frequently_atTop_modEq_one", """theorem {name} {{k : ℕ}} (hk0 : k ≠ 0) :
    ∃ᶠ p in atTop, Nat.Prime p ∧ p ≡ 1 [MOD k] := by
  sorry"""),
    Theorem("ml_062_Mathlib_Meta_mersenne_mod_eight", """theorem {name} {{n : ℕ}} (h : 3 ≤ n) : mersenne n % 8 = 7 := by
  sorry"""),
    Theorem("ml_063_WithZero", """theorem {name}.mulArchimedean_iff {{α}} [CommGroup α] [PartialOrder α] :
    MulArchimedean (WithZero α) ↔ MulArchimedean α := by
  sorry"""),
    Theorem("ml_064_niven_angle_eq", """theorem {name} (hθ : ∃ r : ℚ, θ = r * π) (hcos : ∃ q : ℚ, cos θ = q)
    (h_bnd : θ ∈ Set.Icc 0 π) : θ ∈ ({{0, π / 3, π / 2, π * (2 / 3), π}} : Set ℝ) := by
  sorry"""),
    Theorem("ml_065_ZMod", """theorem {name}.isSquare_neg_one_of_dvd {{m n : ℕ}} (hd : m ∣ n) (hs : IsSquare (-1 : ZMod n)) :
    IsSquare (-1 : ZMod m) := by
  sorry"""),
    Theorem("ml_066_preimage_metric_ball", """theorem {name} {{r : ℝ}} : p ⁻¹' Metric.ball 0 r = {{ x | p x < r }} := by
  sorry"""),
    Theorem("ml_067_Int", """theorem {name}.emultiplicity_pow_sub_pow {{x y : ℤ}} (hxy : ↑p ∣ x - y) (hx : ¬↑p ∣ x) (n : ℕ) :
    emultiplicity (↑p) (x ^ n - y ^ n) = emultiplicity (↑p) (x - y) + emultiplicity p n := by
  sorry"""),
    Theorem("ml_068_bernoulli", """theorem {name}'_def' (n : ℕ) :
    bernoulli' n = 1 - ∑ k : Fin n, n.choose k / (n - k + 1) * bernoulli' k := by
  sorry"""),
    Theorem("ml_069_pNilradical_le_nilradical", """theorem {name} {{R : Type*}} [CommSemiring R] {{p : ℕ}} :
    pNilradical R p ≤ nilradical R := by
  sorry"""),
    Theorem("ml_070_orderOf_eq_iff", """theorem {name} {{n}} (h : 0 < n) :
    orderOf x = n ↔ x ^ n = 1 ∧ ∀ m, m < n → 0 < m → x ^ m ≠ 1 := by
  sorry"""),
    Theorem("ml_071_IsPiSystem", """theorem {name}.singleton (S : Set α) : IsPiSystem ({{S}} : Set (Set α)) := by
  sorry"""),
    Theorem("ml_072_Mathlib_Meta_succ_mersenne", """theorem {name} (k : ℕ) : mersenne k + 1 = 2 ^ k := by
  sorry"""),
    Theorem("ml_073_dvd_sub_pow_of_dvd_sub", """theorem {name} {{R : Type*}} [CommRing R] {{p : ℕ}} {{a b : R}} (h : (p : R) ∣ a - b)
    (k : ℕ) : (p ^ (k + 1) : R) ∣ a ^ p ^ k - b ^ p ^ k := by
  sorry"""),
    Theorem("ml_074_Nat_Primrec__unpair_", """theorem {name} {{n f}} (hf : @Primrec' n f) : @Primrec' n fun v => (f v).unpair.1 := by
  sorry"""),
    Theorem("ml_075_PFun_mem_prodLift", """theorem {name} {{f : α →. β}} {{g : α →. γ}} {{x : α}} {{y : β × γ}} :
    y ∈ f.prodLift g x ↔ y.1 ∈ f x ∧ y.2 ∈ g x := by
  sorry"""),
    Theorem("ml_076_Nat_reverse_divisorsAntidiagonalList", """theorem {name} (n : ℕ) :
    n.divisorsAntidiagonalList.reverse = n.divisorsAntidiagonalList.map .swap := by
  sorry"""),
    Theorem("ml_077_ZMod", """theorem {name}.isSquare_neg_one_of_dvd {{m n : ℕ}} (hd : m ∣ n) (hs : IsSquare (-1 : ZMod n)) :
    IsSquare (-1 : ZMod m) := by
  sorry"""),
    Theorem("ml_078_Finite", """theorem {name}.wellQuasiOrdered (r : α → α → Prop) [Finite α] [IsRefl α r] :
    WellQuasiOrdered r := by
  sorry"""),
    Theorem("ml_079_Filter_mem_closure", """theorem {name} {{s : Set (Filter α)}} {{l : Filter α}} :
    l ∈ closure s ↔ ∀ t ∈ l, ∃ l' ∈ s, t ∈ l' := by
  sorry"""),
    Theorem("ml_080_secondCountableTopology_induced", """theorem {name} (α β) [t : TopologicalSpace β] [SecondCountableTopology β]
    (f : α → β) : @SecondCountableTopology α (t.induced f) := by
  sorry"""),
    Theorem("ml_081_acc_iff_isEmpty_descending_chain", """theorem {name} {{α}} {{r : α → α → Prop}} {{x : α}} :
    Acc r x ↔ IsEmpty {{ f : ℕ → α // f 0 = x ∧ ∀ n, r (f (n + 1)) (f n) }} := by
  sorry"""),
    Theorem("ml_082_Filter_sInter_nhds", """theorem {name} (l : Filter α) : ⋂₀ {{ s | s ∈ 𝓝 l }} = Iic l := by
  sorry"""),
    Theorem("ml_083_Nat_span_singleton_setGcd", """theorem {name} : Ideal.span {{(setGcd s : ℤ)}} = Ideal.span (((↑) : ℕ → ℤ) '' s) := by
  sorry"""),
    Theorem("ml_084_IsPiSystem", """theorem {name}.singleton (S : Set α) : IsPiSystem ({{S}} : Set (Set α)) := by
  sorry"""),
    Theorem("ml_085_Nat_exists_prime_lt_and_le_two_mul_event", """theorem {name} (n : ℕ) (n_large : 512 ≤ n) :
    ∃ p : ℕ, p.Prime ∧ n < p ∧ p ≤ 2 * n := by
  sorry"""),
    Theorem("ml_086_discreteTopology_iff_singleton_mem_nhds", """theorem {name} [TopologicalSpace α] :
    DiscreteTopology α ↔ ∀ x : α, {{x}} ∈ 𝓝 x := by
  sorry"""),
    Theorem("ml_087_ZMod", """theorem {name}.ker_intCastRingHom (n : ℕ) :
    RingHom.ker (Int.castRingHom (ZMod n)) = Ideal.span ({{(n : ℤ)}} : Set ℤ) := by
  sorry"""),
    Theorem("ml_088_Part_Dom", """theorem {name}.toOption {{o : Part α}} [Decidable o.Dom] (h : o.Dom) : o.toOption = o.get h :=
  dif_pos h

theorem toOption_eq_none_iff {{a : Part α}} [Decidable a.Dom] : a.toOption = Option.none ↔ ¬a.Dom :=
  Ne.dite_eq_right_iff fun _ => Option.some_ne_none _

@[simp]
theorem elim_toOption {{α β : Type*}} (a : Part α) [Decidable a.Dom] (b : β) (f : α → β) :
    a.toOption.elim b f = if h : a.Dom then f (a.get h) else b := by
  sorry"""),
    Theorem("ml_089_Nat_deficient_or_perfect_or_abundant", """theorem {name} (hn : 0 ≠ n) :
    Deficient n ∨ Abundant n ∨ Perfect n := by
  sorry"""),
    Theorem("ml_090_IsCoatomic", """theorem {name}.of_isChain_bounded {{α : Type*}} [PartialOrder α] [OrderTop α]
    (h : ∀ c : Set α, IsChain (· ≤ ·) c → c.Nonempty → ⊤ ∉ c → ∃ x ≠ ⊤, x ∈ upperBounds c) :
    IsCoatomic α := by
  sorry"""),
    Theorem("ml_091_nonempty_unique", """theorem {name} (α : Sort u) [Subsingleton α] [Nonempty α] : Nonempty (Unique α) := by
  sorry"""),
    Theorem("ml_092_Set_unbounded_lt_inter_le", """theorem {name} [LinearOrder α] (a : α) :
    Unbounded (· < ·) (s ∩ {{ b | a ≤ b }}) ↔ Unbounded (· < ·) s := by
  sorry"""),
    Theorem("ml_093_Nat", """theorem {name}.roughNumbersUpTo_card_le' (N k : ℕ) :
    (roughNumbersUpTo N k).card ≤
      N * (N.succ.primesBelow \\ k.primesBelow).sum (fun p ↦ (1 : ℝ) / p) := by
  sorry"""),
    Theorem("ml_094_Lattice", """theorem {name}.ext {{α}} {{A B : Lattice α}} (H : ∀ x y : α, (haveI := A; x ≤ y) ↔ x ≤ y) :
    A = B := by
  sorry"""),
    Theorem("ml_095_LTSeries_apply_add_index_le_apply_add_in", """theorem {name} (p : LTSeries ℕ) (i j : Fin (p.length + 1))
    (hij : i ≤ j) : p i + j ≤ p j + i := by
  sorry"""),
    Theorem("ml_096_schnirelmannDensity_finset", """theorem {name} (A : Finset ℕ) : schnirelmannDensity A = 0 := by
  sorry"""),
    Theorem("ml_097_eq_iff_atom_le_iff", """theorem {name} {{α}} [BooleanAlgebra α] [IsAtomic α] {{x y : α}} :
    x = y ↔ ∀ a, IsAtom a → (a ≤ x ↔ a ≤ y) := by
  sorry"""),
    Theorem("ml_098_PFun_dom_comp", """theorem {name} (f : β →. γ) (g : α →. β) : (f.comp g).Dom = g.preimage f.Dom := by
  sorry"""),
    Theorem("ml_099_denselyOrdered_iff", """theorem {name} [LT α] [NoMinOrder α] :
    DenselyOrdered (WithBot α) ↔ DenselyOrdered α := by
  sorry"""),
    Theorem("ml_100_orderOf_zero", """theorem {name} (M₀ : Type*) [MonoidWithZero M₀] [Nontrivial M₀] : orderOf (0 : M₀) = 0 := by
  sorry"""),
    Theorem("ml_101_WellQuasiOrdered", """theorem {name}.exists_monotone_subseq [IsPreorder α r] (h : WellQuasiOrdered r)
    (f : ℕ → α) : ∃ g : ℕ ↪o ℕ, ∀ m n, m ≤ n → r (f (g m)) (f (g n)) := by
  sorry"""),
    Theorem("ml_102_Nat", """theorem {name}.Prime.sq_add_sq {{p : ℕ}} [Fact p.Prime] (hp : p % 4 ≠ 3) :
    ∃ a b : ℕ, a ^ 2 + b ^ 2 = p := by
  sorry"""),
    Theorem("ml_103_Ordering_compares_swap", """theorem {name} [LT α] {{a b : α}} {{o : Ordering}} : o.swap.Compares a b ↔ o.Compares b a := by
  sorry"""),
    Theorem("ml_104_WellFounded", """theorem {name}.prod_lex_of_wellFoundedOn_fiber (hα : WellFounded (rα on f))
    (hβ : ∀ a, (f ⁻¹' {{a}}).WellFoundedOn (rβ on g)) :
    WellFounded (Prod.Lex rα rβ on fun c => (f c, g c)) := by
  sorry"""),
    Theorem("ml_105_Real_summable_nat_rpow", """theorem {name} {{p : ℝ}} : Summable (fun n => (n : ℝ) ^ p : ℕ → ℝ) ↔ p < -1 := by
  sorry"""),
    Theorem("ml_106_ack_one", """theorem {name} (n : ℕ) : ack 1 n = n + 2 := by
  sorry"""),
    Theorem("ml_107_Set_PartiallyWellOrderedOn_exists_notMem", """theorem {name} {{s : Set α}} (hs : s.PartiallyWellOrderedOn r) {{f : ℕ → α}}
    (hf : ∀ m n : ℕ, m < n → ¬ r (f m) (f n)) :
    ∃ k : ℕ, ∀ m, k < m → f m ∉ s := by
  sorry"""),
    Theorem("ml_108_Int", """theorem {name}.emultiplicity_pow_sub_pow {{x y : ℤ}} (hxy : ↑p ∣ x - y) (hx : ¬↑p ∣ x) (n : ℕ) :
    emultiplicity (↑p) (x ^ n - y ^ n) = emultiplicity (↑p) (x - y) + emultiplicity p n := by
  sorry"""),
    Theorem("ml_109_Acc", """theorem {name}.prod_gameAdd (ha : Acc rα a) (hb : Acc rβ b) :
    Acc (Prod.GameAdd rα rβ) (a, b) := by
  sorry"""),
    Theorem("ml_110_niven_sin", """theorem {name} (hθ : ∃ r : ℚ, θ = r * π) (hcos : ∃ q : ℚ, sin θ = q) :
    sin θ ∈ ({{-1, -1 / 2, 0, 1 / 2, 1}} : Set ℝ) := by
  sorry"""),
    Theorem("ml_111_isSolvable_of_comm", """theorem {name} {{G : Type*}} [hG : Group G] (h : ∀ a b : G, a * b = b * a) :
    IsSolvable G := by
  sorry"""),
    Theorem("ml_112_eq_or_eq_or_eq_of_forall_not_lt_lt", """theorem {name} [LinearOrder α]
    (h : ∀ ⦃x y z : α⦄, x < y → y < z → False) (x y z : α) : x = y ∨ y = z ∨ x = z := by
  sorry"""),
    Theorem("ml_113_Nat_factoredNumbers_insert", """theorem {name} (s : Finset ℕ) {{N : ℕ}} (hN : ¬ N.Prime) :
    factoredNumbers (insert N s) = factoredNumbers s := by
  sorry"""),
    Theorem("ml_114_Set_WellFounded", """theorem {name}.prod_lex_of_wellFoundedOn_fiber (hα : WellFounded (rα on f))
    (hβ : ∀ a, (f ⁻¹' {{a}}).WellFoundedOn (rβ on g)) :
    WellFounded (Prod.Lex rα rβ on fun c => (f c, g c)) := by
  sorry"""),
    Theorem("ml_115_Algebra", """theorem {name}.leftMulMatrix_complex (z : ℂ) :
    Algebra.leftMulMatrix Complex.basisOneI z = !![z.re, -z.im; z.im, z.re] := by
  sorry"""),
    Theorem("ml_116_IntermediateField", """theorem {name}.fixingSubgroup_isOpen {{K L : Type*}} [Field K] [Field L] [Algebra K L]
    (E : IntermediateField K L) [FiniteDimensional K E] :
    IsOpen (E.fixingSubgroup : Set Gal(L/K)) := by
  sorry"""),
    Theorem("ml_117_Nat", """theorem {name}.Prime.of_mersenne {{p : ℕ}} (h : (mersenne p).Prime) : Nat.Prime p := by
  sorry"""),
    Theorem("ml_118_Lists_lt_sizeof_cons", """theorem {name}' {{b}} (a : Lists' α b) (l) :
    SizeOf.sizeOf (⟨b, a⟩ : Lists α) < SizeOf.sizeOf (Lists'.cons' a l) := by
  sorry"""),
    Theorem("ml_119_IteratedWreathProduct", """theorem {name}.card [Finite G] : Nat.card (IteratedWreathProduct G n) =
    Nat.card G ^ (∑ i ∈ Finset.range n, Nat.card G ^ i) := by
  sorry"""),
    Theorem("ml_120_bernoulli", """theorem {name}'_def' (n : ℕ) :
    bernoulli' n = 1 - ∑ k : Fin n, n.choose k / (n - k + 1) * bernoulli' k := by
  sorry"""),
    Theorem("ml_121_PerfectRing", """theorem {name}.toPerfectField (K : Type*) (p : ℕ)
    [Field K] [ExpChar K p] [PerfectRing K p] : PerfectField K := by
  sorry"""),
    Theorem("ml_122_Nat_fermatPsp_base_one", """theorem {name} {{n : ℕ}} (h₁ : 1 < n) (h₂ : ¬n.Prime) : FermatPsp n 1 := by
  sorry"""),
    Theorem("ml_123_xor_iff_or_and_not_and", """theorem {name} (a b : Prop) : Xor' a b ↔ (a ∨ b) ∧ (¬(a ∧ b)) := by
  sorry"""),
    Theorem("ml_124_Nat_factoredNumbers_compl", """theorem {name} {{N : ℕ}} {{s : Finset ℕ}} (h : primesBelow N ≤ s) :
    (factoredNumbers s)ᶜ \\ {{0}} ⊆ {{n | N ≤ n}} := by
  sorry"""),
    Theorem("ml_125_Nat_disjoint_divisors_filter_isPrimePow", """theorem {name} {{a b : ℕ}} (hab : a.Coprime b) :
    Disjoint (a.divisors.filter IsPrimePow) (b.divisors.filter IsPrimePow) := by
  sorry"""),
    Theorem("ml_126_DihedralGroup_commProb_odd", """theorem {name} {{n : ℕ}} (hn : Odd n) :
    commProb (DihedralGroup n) = (n + 3) / (4 * n) := by
  sorry"""),
    Theorem("ml_127_Nat", """theorem {name}.Prime.sq_add_sq {{p : ℕ}} [Fact p.Prime] (hp : p % 4 ≠ 3) :
    ∃ a b : ℕ, a ^ 2 + b ^ 2 = p := by
  sorry"""),
    Theorem("ml_128_ZMod", """theorem {name}.isSquare_neg_one_of_dvd {{m n : ℕ}} (hd : m ∣ n) (hs : IsSquare (-1 : ZMod n)) :
    IsSquare (-1 : ZMod m) := by
  sorry"""),
    Theorem("ml_129_Rep_to_Module_monoidAlgebra_map_aux", """theorem {name} {{k G : Type*}} [CommRing k] [Monoid G] (V W : Type*)
    [AddCommGroup V] [AddCommGroup W] [Module k V] [Module k W] (ρ : G →* V →ₗ[k] V)
    (σ : G →* W →ₗ[k] W) (f : V →ₗ[k] W) (w : ∀ g : G, f.comp (ρ g) = (σ g).comp f)
    (r : MonoidAlgebra k G) (x : V) :
    f ((((MonoidAlgebra.lift k G (V →ₗ[k] V)) ρ) r) x) =
      (((MonoidAlgebra.lift k G (W →ₗ[k] W)) σ) r) (f x) := by
  sorry"""),
    Theorem("ml_130_exists_eq_pow_of_mul_eq_pow_of_coprime", """theorem {name} {{R : Type*}} [CommSemiring R] [IsDomain R]
    [GCDMonoid R] [Subsingleton Rˣ] {{a b c : R}} {{n : ℕ}} (cp : IsCoprime a b) (h : a * b = c ^ n) :
    ∃ d : R, a = d ^ n := by
  sorry"""),
    Theorem("ml_131_le_monotonicSequenceLimit", """theorem {name} [PartialOrder α] [WellFoundedGT α] (a : ℕ →o α) (m : ℕ) :
    a m ≤ monotonicSequenceLimit a := by
  sorry"""),
    Theorem("ml_132_Nat_infinite_odd_deficient", """theorem {name} : {{n : ℕ | Odd n ∧ n.Deficient}}.Infinite := by
  sorry"""),
    Theorem("ml_133_Set_bounded_le_inter_le", """theorem {name} [LinearOrder α] (a : α) :
    Bounded (· ≤ ·) (s ∩ {{ b | a ≤ b }}) ↔ Bounded (· ≤ ·) s := by
  sorry"""),
    Theorem("ml_134_IsPiSystem", """theorem {name}.singleton (S : Set α) : IsPiSystem ({{S}} : Set (Set α)) := by
  sorry"""),
    Theorem("ml_135_sup_eq_maxDefault", """theorem {name} [SemilatticeSup α] [DecidableLE α] [IsTotal α (· ≤ ·)] :
    (· ⊔ ·) = (maxDefault : α → α → α) := by
  sorry"""),
    Theorem("ml_136_Algebra", """theorem {name}.leftMulMatrix_complex (z : ℂ) :
    Algebra.leftMulMatrix Complex.basisOneI z = !![z.re, -z.im; z.im, z.re] := by
  sorry"""),
    Theorem("ml_137_TopologicalSpace_nhds_mkOfNhds_single", """theorem {name} [DecidableEq α] {{a₀ : α}} {{l : Filter α}} (h : pure a₀ ≤ l) (b : α) :
    @nhds α (TopologicalSpace.mkOfNhds (update pure a₀ l)) b =
      (update pure a₀ l : α → Filter α) b := by
  sorry"""),
    Theorem("ml_138_preimage_find_eq_disjointed", """theorem {name} (s : ℕ → Set α) (H : ∀ x, ∃ n, x ∈ s n)
    [∀ x n, Decidable (x ∈ s n)] (n : ℕ) : (fun x => Nat.find (H x)) ⁻¹' {{n}} = disjointed s n := by
  sorry"""),
    Theorem("ml_139_LTSeries_apply_add_index_le_apply_add_in", """theorem {name} (p : LTSeries ℤ) (i j : Fin (p.length + 1))
    (hij : i ≤ j) : p i + j ≤ p j + i := by
  sorry"""),
    Theorem("ml_140_Nat_mul_mem_smoothNumbers", """theorem {name} {{m₁ m₂ n : ℕ}}
    (hm1 : m₁ ∈ n.smoothNumbers) (hm2 : m₂ ∈ n.smoothNumbers) : m₁ * m₂ ∈ n.smoothNumbers := by
  sorry"""),
    Theorem("ml_141_isOfFinOrder_iff_isUnit", """theorem {name} [Monoid G] [Finite Gˣ] {{x : G}} : IsOfFinOrder x ↔ IsUnit x := by
  sorry"""),
]
