# 环节：Leader 赋权约束；用途：将候选权重确定性投影到等权邻域，避免归一化突破上限。
import math


def normalize_weights(candidates: dict[str, float]) -> dict[str, float]:
    """Normalize relative importance without equal-weight priors or clipping."""
    if not candidates:
        return {}
    if any(isinstance(v, bool) or not math.isfinite(v) or v <= 0 for v in candidates.values()):
        raise ValueError("Retained weights must be finite and strictly positive")
    scale = max(candidates.values())
    scaled = {mid: value / scale for mid, value in candidates.items()}
    total = math.fsum(scaled.values())
    return {mid: value / total for mid, value in scaled.items()}


def average_stage_weights(stages: list[dict[str, float]]) -> dict[str, float]:
    if len(stages) != 3:
        raise ValueError("Exactly three weighting stages are required")
    if not any(stages):
        return {}
    if not all(stages):
        raise ValueError("A missing/empty stage cannot silently become a zero probability vector")
    vectors = [normalize_weights(stage) for stage in stages]
    union = dict.fromkeys(mid for vector in vectors for mid in vector)
    return {mid: math.fsum(vector.get(mid, 0) for vector in vectors) / 3 for mid in union}


def bounded_weights(candidates: dict[str, float], deviation: float = 0.2) -> dict[str, float]:
    """Euclidean projection onto sum=1 and [(1-rho)/m,(1+rho)/m]."""
    if not math.isfinite(deviation) or not 0 <= deviation < 1:
        raise ValueError("weight_deviation must be finite and in [0,1)")
    if not candidates:
        return {}
    values = list(candidates.values())
    if any(isinstance(v, bool) or not math.isfinite(v) or v < 0 for v in values):
        raise ValueError("Candidate weights must be finite and nonnegative")
    scale = max(values)
    if not scale:
        raise ValueError("Candidate weights cannot all be zero")
    # Normalize before summing to tolerate valid but extreme finite LLM numbers.
    values = [v / scale for v in values]
    total = math.fsum(values)
    size = len(values)
    low, high = (1 - deviation) / size, (1 + deviation) / size
    if size == 1 or deviation == 0:
        return dict.fromkeys(candidates, 1 / size)
    values = [v / total for v in values]
    left, right = min(v - high for v in values), max(v - low for v in values)
    for _ in range(100):
        shift = (left + right) / 2
        if math.fsum(max(low, min(high, v - shift)) for v in values) > 1:
            left = shift
        else:
            right = shift
    projected = [max(low, min(high, v - (left + right) / 2)) for v in values]
    remaining = 1 - math.fsum(projected)
    for i, value in enumerate(projected):
        correction = max(low - value, min(high - value, remaining))
        projected[i] += correction
        remaining -= correction
    return dict(zip(candidates, projected, strict=True))
