"""LifeSim offline artificial-life simulation package."""

from .core import (
    CognitiveProvider,
    MockLLMProvider,
    RuleBasedProvider,
    Simulation,
    SimulationConfig,
    make_demo,
)
from .stats import confidence_interval, percentile, summarize

__all__ = [
    "CognitiveProvider",
    "MockLLMProvider",
    "RuleBasedProvider",
    "Simulation",
    "SimulationConfig",
    "make_demo",
    "percentile",
    "confidence_interval",
    "summarize",
]
