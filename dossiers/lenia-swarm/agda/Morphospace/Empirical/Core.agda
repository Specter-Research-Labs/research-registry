{-# OPTIONS --cubical #-}

module Morphospace.Empirical.Core where

open import Agda.Builtin.Bool using (Bool; true; false)
open import Agda.Builtin.Unit using (⊤; tt)

data ⊥ : Set where

Reflects : Bool → Set
Reflects true = ⊤
Reflects false = ⊥
