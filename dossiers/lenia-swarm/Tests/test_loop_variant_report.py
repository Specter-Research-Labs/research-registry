from __future__ import annotations

from lenia_swarm_analysis.loop_variant_report import (
    _canonicalize_control_group,
    build_loop_variant_report,
)


def test_canonicalize_control_group_strips_variant_and_scale() -> None:
    assert _canonicalize_control_group("crystal-mixed-hbias-medium") == (
        "crystal-mixed",
        "medium",
        "hbias",
    )
    assert _canonicalize_control_group("mystic-mixed-mh-small") == (
        "mystic-mixed",
        "small",
        "mh",
    )


def test_build_loop_variant_report_picks_best_variant(tmp_path) -> None:
    packet_a = tmp_path / "loop-variant-a.json"
    packet_b = tmp_path / "loop-variant-b.json"
    packet_a.write_text(
        """
        {
          "groups": [
            {
              "controlGroup": "mystic-mixed-mh-small",
              "topLoop": {"name": "square-forward-small"},
              "bestControl": {"name": "outback-h-small"},
              "loopMinusBestControlStateClosure": 0.00025,
              "loopMinusBestControlPhenotypeClosure": 0.0,
              "loopMinusBestControlRatio": 3.08
            }
          ]
        }
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    packet_b.write_text(
        """
        {
          "groups": [
            {
              "controlGroup": "mystic-mixed-mbias-small",
              "topLoop": {"name": "rect-forward-small-mbias"},
              "bestControl": {"name": "outback-m-small-mbias"},
              "loopMinusBestControlStateClosure": 0.00021,
              "loopMinusBestControlPhenotypeClosure": 0.0,
              "loopMinusBestControlRatio": -1.16
            }
          ]
        }
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    report = build_loop_variant_report(
        [
            ("small-square", packet_a),
            ("small-mbias", packet_b),
        ]
    )

    assert report["packetKind"] == "loop_variant_report_v1"
    assert report["groupCount"] == 1
    group = report["groups"][0]
    assert group["canonicalGroup"] == "mystic-mixed"
    assert group["scale"] == "small"
    assert group["variantCount"] == 2
    assert group["bestVariantByStateClosure"]["variant"] == "mh"
    assert group["bestVariantByRatio"]["variant"] == "mh"
