{-# OPTIONS --cubical #-}

module Morphospace.Empirical.Attractors where

open import Agda.Builtin.Nat using (Nat)
open import Agda.Builtin.String using (String)

open import Morphospace.Generated.Ids public
open import Morphospace.Generated.Attractors public

record AttractorScaleObservation : Set where
  constructor observeAttractorScale
  field
    scaleId : AttractorScaleId
    rank : Nat
    componentCount : Nat

record AttractorComponentObservation : Set where
  constructor observeAttractorComponent
  field
    componentId : AttractorComponentId
    scaleId : AttractorScaleId
    specimenCount : Nat
    representativeSpecimenId : String
