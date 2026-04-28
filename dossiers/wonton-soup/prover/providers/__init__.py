from prover.providers.base import TacticProvider as TacticProvider

__all__ = [
    "BFSProverTacticProvider",
    "TacticProvider",
    "DeepSeekTacticProvider",
    "InternLMStepProverTacticProvider",
    "ReProverTacticProvider",
]


def __getattr__(name: str):
    if name == "BFSProverTacticProvider":
        from prover.providers.bfs_prover import BFSProverTacticProvider

        return BFSProverTacticProvider
    if name == "DeepSeekTacticProvider":
        from prover.providers.deepseek import DeepSeekTacticProvider

        return DeepSeekTacticProvider
    if name == "InternLMStepProverTacticProvider":
        from prover.providers.internlm_step import InternLMStepProverTacticProvider

        return InternLMStepProverTacticProvider
    if name == "ReProverTacticProvider":
        from prover.providers.reprover import ReProverTacticProvider

        return ReProverTacticProvider
    if name == "TacticProvider":
        return TacticProvider
    raise AttributeError(f"module {__name__} has no attribute {name}")
