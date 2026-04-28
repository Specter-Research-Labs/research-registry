{-# OPTIONS --cubical #-}

module Morphospace.Empirical.Fibration where

open import Agda.Builtin.String using (String)

import Morphospace.Generated.Witnesses as GenWitness

open import Morphospace.Empirical.Core public
open import Morphospace.Empirical.Topology public
open import Morphospace.Empirical.Transport public
open import Morphospace.Empirical.Attractors public

record EmpiricalFibration : Set₁ where
  field
    Generator : Set
    Edge : Set
    OpenTransport : Set
    TransportGroup : Set
    AttractorScale : Set
    AttractorComponent : Set
    topologyViewName : String
    attractorViewName : String

empiricalFibration : EmpiricalFibration
empiricalFibration = record
  { Generator = GeneratorId
  ; Edge = EdgeId
  ; OpenTransport = OpenTransportId
  ; TransportGroup = TransportGroupId
  ; AttractorScale = AttractorScaleId
  ; AttractorComponent = AttractorComponentId
  ; topologyViewName = GenWitness.topologyRepresentation
  ; attractorViewName = GenWitness.attractorRepresentation
  }

CycleLinkedReentrySupported : Set
CycleLinkedReentrySupported =
  Reflects GenWitness.supportsCycleLinkedReentry

HiddenStateDominanceSupported : Set
HiddenStateDominanceSupported =
  Reflects GenWitness.supportsHiddenStateDominance

PositiveLoopSurplusSupported : Set
PositiveLoopSurplusSupported =
  Reflects GenWitness.supportsPositiveLoopSurplus
