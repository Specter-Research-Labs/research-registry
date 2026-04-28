from __future__ import annotations

import math
from types import SimpleNamespace

from experiments.distributed_mcts import DistributedMCTSConfig
from orchestrator.lean import runner as lean_runner
from orchestrator.lean.metadata import build_distributed_config
from prover.mcts import BackpropStrategy


def test_build_distributed_config_preserves_deterministic_inference() -> None:
    config = build_distributed_config(
        {
            "agents": 3,
            "inflight": 9,
            "virtual_loss": 2,
            "depth_bias": 0.25,
            "path_bias": 0.5,
            "history_cache": True,
            "deterministic_inference": True,
            "block_fraction": None,
            "block_duration": None,
            "block_seed": None,
            "reroute_max_attempts": None,
            "delay_probability": None,
            "delay_duration": None,
            "delay_seed": None,
        },
        budget=123,
    )

    assert isinstance(config, DistributedMCTSConfig)
    assert config.agents == 3
    assert config.max_iterations == 123
    assert config.max_inflight_expansions == 9
    assert config.virtual_loss == 2
    assert config.depth_bias == 0.25
    assert config.path_bias == 0.5
    assert config.history_cache is True
    assert config.deterministic_inference is True


def test_run_search_budget_uses_local_builder_not_runtime_private_helper(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_distributed_search(*_args, **kwargs):
        captured["config"] = kwargs["config"]
        return "ok"

    lean_runner.distributed_mcts_search = fake_distributed_search  # type: ignore[assignment]
    monkeypatch.setattr(
        lean_runner,
        "_lean_helpers",
        lambda: SimpleNamespace(
            _open_mcts_trace_writer=None,
            TheoremResult=None,
            InterventionResult=None,
        ),
    )

    result = lean_runner._run_search_budget(
        statement="theorem",
        adapter=None,  # type: ignore[arg-type]
        provider=None,  # type: ignore[arg-type]
        graph=None,  # type: ignore[arg-type]
        history=None,  # type: ignore[arg-type]
        goal_cache=None,
        goal_sig_config=None,  # type: ignore[arg-type]
        mcts_mode="distributed",
        budget=17,
        tree=None,
        distributed_settings={
            "agents": 2,
            "inflight": 4,
            "virtual_loss": 1,
            "depth_bias": 0.0,
            "path_bias": 0.0,
            "history_cache": False,
            "deterministic_inference": True,
            "block_fraction": None,
            "block_duration": None,
            "block_seed": None,
            "reroute_max_attempts": None,
            "delay_probability": None,
            "delay_duration": None,
            "delay_seed": None,
        },
    )

    import asyncio

    assert asyncio.run(result) == "ok"
    assert captured["config"] == DistributedMCTSConfig(
        agents=2,
        max_iterations=17,
        max_inflight_expansions=4,
        c=math.sqrt(2),
        backprop_strategy=BackpropStrategy.UNIFORM,
        virtual_loss=1,
        adapter_mode="single",
        block_policy=None,
        reroute_policy=None,
        delay_policy=None,
        depth_bias=0.0,
        path_bias=0.0,
        history_cache=False,
        deterministic_inference=True,
    )
