{-# OPTIONS --cubical #-}

module Morphospace.Empirical.Transport where

open import Agda.Builtin.Maybe using (Maybe)
open import Agda.Builtin.String using (String)

open import Morphospace.Empirical.Core
open import Morphospace.Generated.Ids public
open import Morphospace.Generated.Witnesses public

OpenTransportHiddenStateDominant : OpenTransportId → Set
OpenTransportHiddenStateDominant run =
  Reflects (openTransportHiddenStateDominant run)

TransportLoopBeatsControlByState : TransportGroupId → Set
TransportLoopBeatsControlByState group =
  Reflects (transportLoopBeatsControlByState group)

TransportLoopBeatsControlByRatio : TransportGroupId → Set
TransportLoopBeatsControlByRatio group =
  Reflects (transportLoopBeatsControlByRatio group)

record OpenTransportObservation : Set where
  constructor observeOpenTransport
  field
    runId : OpenTransportId
    coordinate : Maybe String

record TransportGroupObservation : Set where
  constructor observeTransportGroup
  field
    groupId : TransportGroupId
    bestScaleByState : Scale
    bestScaleByRatio : Scale
