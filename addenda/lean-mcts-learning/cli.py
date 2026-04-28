# ruff: noqa: I001
from __future__ import annotations

import argparse
from collections.abc import Callable

from eval.batch_family_prior import main as batch_family_prior_eval_main
from data.tactic_sft import main as build_tactic_sft_dataset_main
from eval.family_prior_replay import main as eval_family_prior_replay_main
from train.value import main as train_value_main


COMMANDS: dict[str, tuple[str, Callable[[list[str] | None], None]]] = {
    "build-tactic-sft-dataset": (
        "Build miniCTX-style tactic SFT JSONL from wonton-soup run logs",
        build_tactic_sft_dataset_main,
    ),
    "eval-family-prior-replay": (
        "Replay-evaluate family_prior ordering on existing MCTS traces",
        eval_family_prior_replay_main,
    ),
    "batch-family-prior-eval": (
        "Train and replay-evaluate family_prior over many runs",
        batch_family_prior_eval_main,
    ),
    "train-value": (
        "Train a simple logistic-regression value model from a dataset",
        train_value_main,
    ),
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="lean-mcts-learning")
    parser.add_argument("command", nargs="?", choices=sorted(COMMANDS), help="Subcommand to run")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments for the subcommand")
    ns = parser.parse_args(argv)
    if ns.command is None:
        parser.print_help()
        raise SystemExit(1)

    _, handler = COMMANDS[ns.command]
    handler(ns.args)
