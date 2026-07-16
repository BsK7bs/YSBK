"""Health engine registry.

Allows swapping engines (V1 rule-based → V2 ML → V3 AI) with a single
configuration change while keeping the API/frontend stable.
"""
from __future__ import annotations

from typing import Any

from .base import HealthEngine
from .contracts import HealthAssessment
from .engine_v1 import HealthEngineV1RuleBased

_DEFAULT_ENGINE: HealthEngine = HealthEngineV1RuleBased()
_ENGINES: dict[str, HealthEngine] = {
    "v1-rule-based": _DEFAULT_ENGINE,
    # Future entries:
    # "v2-ml": HealthEngineV2ML(),
    # "v3-ai": HealthEngineV3AI(),
}


def get_engine(version: str | None = None) -> HealthEngine:
    if not version:
        return _DEFAULT_ENGINE
    return _ENGINES.get(version, _DEFAULT_ENGINE)


def assess_device(ctx: dict[str, Any], version: str | None = None) -> HealthAssessment:
    engine = get_engine(version)
    return engine.assess(ctx)
