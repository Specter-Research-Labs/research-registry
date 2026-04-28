{-# OPTIONS --cubical #-}

module Morphospace.Empirical.Topology where

open import Agda.Builtin.Nat using (Nat)

open import Morphospace.Empirical.Core
open import Morphospace.Generated.Ids public
open import Morphospace.Generated.Witnesses public

GeneratorSupportsReentry : GeneratorId → Set
GeneratorSupportsReentry generator = Reflects (generatorHasReentry generator)

GeneratorSupportsNonEndpointRepresentative : GeneratorId → Set
GeneratorSupportsNonEndpointRepresentative generator =
  Reflects (generatorHasNonEndpointRepresentative generator)

GeneratorSupportsAnchorInvariantEdge : GeneratorId → Set
GeneratorSupportsAnchorInvariantEdge generator =
  Reflects (generatorHasAnchorInvariantEdge generator)

EdgeSupportsReentry : EdgeId → Set
EdgeSupportsReentry edge = Reflects (edgeHasReentry edge)

EdgeVisitsNonEndpointRepresentative : EdgeId → Set
EdgeVisitsNonEndpointRepresentative edge =
  Reflects (edgeVisitsNonEndpointRepresentative edge)

EdgeIsAnchorInvariant : EdgeId → Set
EdgeIsAnchorInvariant edge = Reflects (edgeAnchorInvariant edge)

record GeneratorObservation : Set where
  constructor observeGenerator
  field
    generatorId : GeneratorId
    persistenceRank : Nat

record EdgeObservation : Set where
  constructor observeEdge
  field
    edgeId : EdgeId
    generatorId : GeneratorId
    representativeVisitCount : Nat
    branchSwitchCount : Nat
