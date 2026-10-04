"""Small dependency-free statistics helpers for experiment comparisons."""
from __future__ import annotations

import math
import statistics as _statistics
from typing import Iterable, Optional


def percentile(values: Iterable[float], p: float) -> float:
    xs = sorted(float(v) for v in values)
    if not xs:
        return 0.0
    p = max(0.0, min(100.0, float(p)))
    if len(xs) == 1:
        return xs[0]
    index = (len(xs) - 1) * p / 100.0
    lo, hi = int(math.floor(index)), int(math.ceil(index))
    if lo == hi:
        return xs[lo]
    return xs[lo] + (xs[hi] - xs[lo]) * (index - lo)


def confidence_interval(values: Iterable[float], confidence: float = 0.95) -> dict[str, float]:
    xs = [float(v) for v in values]
    if not xs:
        return {"low": 0.0, "high": 0.0, "mean": 0.0, "confidence": confidence}
    mean = _statistics.mean(xs)
    if len(xs) < 2:
        return {"low": mean, "high": mean, "mean": mean, "confidence": confidence}
    se = _statistics.stdev(xs) / math.sqrt(len(xs))
    # 1.96 is a stable normal approximation and avoids a SciPy dependency.
    margin = 1.96 * se
    return {"low": mean - margin, "high": mean + margin, "mean": mean, "confidence": confidence}


def summarize(values: Iterable[float], *, success: Optional[Iterable[bool]] = None) -> dict[str, float]:
    xs = [float(v) for v in values]
    result = {
        "count": len(xs),
        "mean": _statistics.mean(xs) if xs else 0.0,
        "median": _statistics.median(xs) if xs else 0.0,
        "std": _statistics.stdev(xs) if len(xs) > 1 else 0.0,
        "p25": percentile(xs, 25),
        "p50": percentile(xs, 50),
        "p75": percentile(xs, 75),
        "p95": percentile(xs, 95),
    }
    ci = confidence_interval(xs)
    result.update({"ci_low": ci["low"], "ci_high": ci["high"]})
    if success is not None:
        flags = [bool(v) for v in success]
        result["success_rate"] = sum(flags) / len(flags) if flags else 0.0
        result["error_rate"] = 1.0 - result["success_rate"]
    return {k: round(float(v), 6) if isinstance(v, (int, float)) else v for k, v in result.items()}

