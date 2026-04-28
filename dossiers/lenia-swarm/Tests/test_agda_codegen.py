from __future__ import annotations

from lenia_swarm_analysis.agda.codegen import render_agda_module, render_agda_package


def test_render_agda_module_emits_finite_id_types_and_witness_predicates() -> None:
    packet = {
        "packetKind": "agda_facing_packet_v1",
        "summary": {
            "topologyRepresentation": "fingerprint_plus_symmetry",
            "attractorRepresentation": "fingerprint_only",
            "supportsCycleLinkedReentry": True,
            "supportsHiddenStateDominance": True,
            "supportsPositiveLoopSurplus": False,
        },
        "thresholds": {
            "hiddenStateDominanceRatioMin": 1.0,
            "positiveLoopSurplusMinStateClosure": 0.0,
            "anchorInvariantMaxPhenotypeDelta": 0.0,
        },
        "ids": {
            "generators": [{"id": "h1-rank01-feature0028", "ctor": "g_h1_rank01_feature0028"}],
            "cycleEdges": [
                {
                    "id": "h1-rank01-feature0028:edge03",
                    "ctor": "e_h1_rank01_feature0028_edge03",
                }
            ],
            "openTransportRuns": [{"id": "crystal-h0-open", "ctor": "ot_crystal_h0_openkw"}],
            "transportGroups": [{"id": "crystal-mh", "ctor": "tg_crystal_mh"}],
            "attractorScales": [{"id": "h0_scale_rank_01", "ctor": "as_h0_scale_rank_n01"}],
            "attractorComponents": [
                {
                    "id": "h0_scale_rank_01_component_01",
                    "ctor": "ac_h0_scale_rank_n01_component_n01",
                }
            ],
        },
        "generators": [
            {
                "id": "h1-rank01-feature0028",
                "ctor": "g_h1_rank01_feature0028",
                "persistenceRank": 1,
                "hasReentryEdge": True,
                "hasNonEndpointRepresentativeEdge": True,
                "hasAnchorInvariantEdge": True,
                "interestingEdgeIds": ["h1-rank01-feature0028:edge03"],
                "interestingEdgeCtors": ["e_h1_rank01_feature0028_edge03"],
            }
        ],
        "cycleEdges": [
            {
                "id": "h1-rank01-feature0028:edge03",
                "ctor": "e_h1_rank01_feature0028_edge03",
                "generatorId": "h1-rank01-feature0028",
                "generatorCtor": "g_h1_rank01_feature0028",
                "hasReentry": True,
                "visitsNonEndpointRepresentative": True,
                "anchorInvariant": True,
                "representativeVisitCount": 4,
                "branchSwitchCount": 5,
            }
        ],
        "openTransportRuns": [
            {
                "id": "crystal-h0-open",
                "ctor": "ot_crystal_h0_openkw",
                "coordinate": "h.0",
                "hiddenStateDominant": True,
            }
        ],
        "transportGroups": [
            {
                "id": "crystal-mh",
                "ctor": "tg_crystal_mh",
                "bestScaleByState": "medium",
                "bestScaleByRatio": "small",
                "loopBeatsControlByState": True,
                "loopBeatsControlByRatio": False,
            }
        ],
        "attractorScales": [
            {
                "id": "h0_scale_rank_01",
                "ctor": "as_h0_scale_rank_n01",
                "rank": 1,
                "componentCount": 2,
                "topComponentIds": ["h0_scale_rank_01_component_01"],
                "topComponentCtors": ["ac_h0_scale_rank_n01_component_n01"],
            }
        ],
        "attractorComponents": [
            {
                "id": "h0_scale_rank_01_component_01",
                "ctor": "ac_h0_scale_rank_n01_component_n01",
                "scaleId": "h0_scale_rank_01",
                "scaleCtor": "as_h0_scale_rank_n01",
                "specimenCount": 7,
                "representativeSpecimenId": "spec-a",
            }
        ],
        "witnessSets": {
            "generatorHasReentry": ["h1-rank01-feature0028"],
            "edgeHasReentry": ["h1-rank01-feature0028:edge03"],
        },
        "topWitnesses": [{"kind": "cycle_generator", "id": "h1-rank01-feature0028"}],
        "topHotspots": [{"kind": "transport_group", "id": "crystal-mh"}],
    }

    source = render_agda_module(
        packet,
        module_name="Morphospace.Generated.EmpiricalFibration",
    )

    assert "module Morphospace.Generated.EmpiricalFibration where" in source
    assert "data GeneratorId : Set where" in source
    assert "g_h1_rank01_feature0028 : GeneratorId" in source
    assert "e_h1_rank01_feature0028_edge03 : EdgeId" in source
    assert "ot_crystal_h0_openkw : OpenTransportId" in source
    assert "as_h0_scale_rank_n01 : AttractorScaleId" in source
    assert "generatorHasReentry g_h1_rank01_feature0028 = true" in source
    assert (
        "edgeVisitsNonEndpointRepresentative"
        " e_h1_rank01_feature0028_edge03 = true"
    ) in source
    assert "transportBestScaleByState tg_crystal_mh = medium" in source
    assert "supportsPositiveLoopSurplus = false" in source


def test_render_agda_package_emits_split_modules() -> None:
    packet = {
        "packetKind": "agda_facing_packet_v1",
        "summary": {
            "topologyRepresentation": "fingerprint_plus_symmetry",
            "attractorRepresentation": "fingerprint_only",
            "supportsCycleLinkedReentry": True,
            "supportsHiddenStateDominance": True,
            "supportsPositiveLoopSurplus": True,
        },
        "thresholds": {
            "hiddenStateDominanceRatioMin": 1.0,
            "positiveLoopSurplusMinStateClosure": 0.0,
            "anchorInvariantMaxPhenotypeDelta": 0.0,
        },
        "generators": [
            {
                "id": "h1-rank01-feature0028",
                "ctor": "g_h1_rank01_feature0028",
                "persistenceRank": 1,
                "hasReentryEdge": True,
                "hasNonEndpointRepresentativeEdge": True,
                "hasAnchorInvariantEdge": True,
                "interestingEdgeIds": ["h1-rank01-feature0028:edge03"],
                "interestingEdgeCtors": ["e_h1_rank01_feature0028_edge03"],
            }
        ],
        "cycleEdges": [
            {
                "id": "h1-rank01-feature0028:edge03",
                "ctor": "e_h1_rank01_feature0028_edge03",
                "generatorId": "h1-rank01-feature0028",
                "generatorCtor": "g_h1_rank01_feature0028",
                "hasReentry": True,
                "visitsNonEndpointRepresentative": True,
                "anchorInvariant": True,
                "representativeVisitCount": 4,
                "branchSwitchCount": 5,
            }
        ],
        "openTransportRuns": [
            {
                "id": "crystal-h0-open",
                "ctor": "ot_crystal_h0_openkw",
                "coordinate": "h.0",
                "hiddenStateDominant": True,
                "pointCount": 5,
            }
        ],
        "transportGroups": [
            {
                "id": "crystal-mh",
                "ctor": "tg_crystal_mh",
                "bestScaleByState": "medium",
                "bestScaleByRatio": "small",
                "scaleCount": 3,
                "loopBeatsControlByState": True,
                "loopBeatsControlByRatio": True,
            }
        ],
        "attractorScales": [
            {
                "id": "h0_scale_rank_01",
                "ctor": "as_h0_scale_rank_n01",
                "rank": 1,
                "componentCount": 2,
                "topComponentIds": ["h0_scale_rank_01_component_01"],
                "topComponentCtors": ["ac_h0_scale_rank_n01_component_n01"],
            }
        ],
        "attractorComponents": [
            {
                "id": "h0_scale_rank_01_component_01",
                "ctor": "ac_h0_scale_rank_n01_component_n01",
                "scaleId": "h0_scale_rank_01",
                "scaleCtor": "as_h0_scale_rank_n01",
                "specimenCount": 7,
                "representativeSpecimenId": "spec-a",
            }
        ],
        "witnessSets": {},
        "topWitnesses": [{"kind": "cycle_generator", "id": "h1-rank01-feature0028"}],
        "topHotspots": [{"kind": "transport_group", "id": "crystal-mh"}],
    }

    package = render_agda_package(packet, root_module="Morphospace")

    assert set(package) == {
        "Generated/Ids.agda",
        "Generated/Witnesses.agda",
        "Generated/Attractors.agda",
    }
    assert "module Morphospace.Generated.Ids where" in package["Generated/Ids.agda"]
    assert "module Morphospace.Generated.Witnesses where" in package["Generated/Witnesses.agda"]
    assert "module Morphospace.Generated.Attractors where" in package["Generated/Attractors.agda"]
