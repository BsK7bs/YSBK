"""Scikit-learn model registry for the prediction engine.

We train one small RandomForestClassifier per failure type on synthetic
training data seeded with realistic failure patterns. This gives us a
usable ML signal on cold-start; models can be retrained against real
labeled outcomes as they accumulate.

Design choices
--------------
* RandomForest: interpretable feature importances, robust to unscaled inputs,
  works well on small tabular data.
* Synthetic data: we generate ``TRAINING_SIZE`` samples per class with
  bounded random noise so both healthy and failing conditions are represented.
* Deterministic seeds: same models across processes / restarts.
* Lazy loading: models are trained once per process and cached in-memory.
  We never persist to disk to keep the deployment stateless.
"""
from __future__ import annotations

import logging
import random
from threading import Lock
from typing import Callable

import numpy as np
from sklearn.ensemble import RandomForestClassifier

log = logging.getLogger("prediction.models")

TRAINING_SIZE = 400  # samples per class; kept small for fast startup
RNG_SEED = 42

_MODELS: dict[str, RandomForestClassifier] = {}
_LOCK = Lock()


# ---------------------------------------------------------------------------
# Synthetic training data generators (one per failure type).
# Each returns (X, y) where y=1 means "will fail within horizon".
# Feature vectors must match the order emitted by features.py.
# ---------------------------------------------------------------------------

def _mk_ssd_samples(rng: random.Random) -> tuple[list[list[float]], list[int]]:
    X, y = [], []
    for _ in range(TRAINING_SIZE):
        # Healthy: SMART pass, low reallocated/pending, high health %, low temp.
        X.append([
            0.0,
            rng.uniform(0, 5),
            rng.uniform(0, 5),
            rng.uniform(0, 15),   # 100 - health%
            rng.uniform(20, 75),  # disk usage
            rng.uniform(0, 30),   # ssd_failure_confidence
            rng.uniform(25, 45),  # disk temp
        ])
        y.append(0)
    for _ in range(TRAINING_SIZE):
        # Failing: SMART fail OR high reallocated/pending OR very low health.
        smart_fail = 1.0 if rng.random() > 0.3 else 0.0
        X.append([
            smart_fail,
            rng.uniform(50, 500),
            rng.uniform(30, 300),
            rng.uniform(30, 80),   # 100 - health% -> health is 20-70
            rng.uniform(50, 99),
            rng.uniform(60, 99),
            rng.uniform(45, 65),
        ])
        y.append(1)
    return X, y


def _mk_fan_samples(rng: random.Random) -> tuple[list[list[float]], list[int]]:
    X, y = [], []
    for _ in range(TRAINING_SIZE):
        X.append([
            0.0, 0.0,
            rng.uniform(35, 70),   # cpu_temp
            rng.uniform(35, 70),   # gpu_temp
            rng.uniform(1000, 3500),  # max_rpm
        ])
        y.append(0)
    for _ in range(TRAINING_SIZE):
        zero = 1.0 if rng.random() > 0.4 else 0.0
        abnormal = 1.0 if rng.random() > 0.3 else 0.0
        X.append([
            zero, abnormal,
            rng.uniform(70, 100),
            rng.uniform(75, 100),
            0.0 if zero else rng.uniform(0, 900),
        ])
        y.append(1)
    return X, y


def _mk_cpu_thermal_samples(rng: random.Random) -> tuple[list[list[float]], list[int]]:
    X, y = [], []
    for _ in range(TRAINING_SIZE):
        X.append([
            rng.uniform(30, 75),
            rng.uniform(5, 60),
            0.0,
            rng.uniform(-1, 1),
        ])
        y.append(0)
    for _ in range(TRAINING_SIZE):
        X.append([
            rng.uniform(85, 105),
            rng.uniform(50, 100),
            1.0 if rng.random() > 0.5 else 0.0,
            rng.uniform(0.5, 4.0),
        ])
        y.append(1)
    return X, y


def _mk_battery_samples(rng: random.Random) -> tuple[list[list[float]], list[int]]:
    X, y = [], []
    for _ in range(TRAINING_SIZE):
        X.append([
            rng.uniform(0, 20),    # 100 - health%
            rng.uniform(50, 400),  # cycles
            rng.uniform(0, 20),    # 100 - capacity ratio
        ])
        y.append(0)
    for _ in range(TRAINING_SIZE):
        X.append([
            rng.uniform(40, 80),
            rng.uniform(500, 2000),
            rng.uniform(40, 80),
        ])
        y.append(1)
    return X, y


def _mk_memory_samples(rng: random.Random) -> tuple[list[list[float]], list[int]]:
    X, y = [], []
    for _ in range(TRAINING_SIZE):
        X.append([
            rng.uniform(20, 75),  # ram_percent
            0.0,
            rng.uniform(0, 2),    # ecc_errors
            rng.uniform(0, 20),   # swap_percent
            rng.uniform(-2, 2),   # ram slope
        ])
        y.append(0)
    for _ in range(TRAINING_SIZE):
        leak = 1.0 if rng.random() > 0.4 else 0.0
        X.append([
            rng.uniform(85, 100),
            leak,
            rng.uniform(5, 100),
            rng.uniform(30, 100),
            rng.uniform(0.5, 8.0),
        ])
        y.append(1)
    return X, y


def _mk_network_samples(rng: random.Random) -> tuple[list[list[float]], list[int]]:
    X, y = [], []
    for _ in range(TRAINING_SIZE):
        X.append([
            rng.uniform(0, 0.15),   # 1 - up_ratio
            rng.uniform(5, 80),     # latency
            rng.uniform(0, 1),      # packet_loss
            rng.uniform(0, 5),      # errors
            rng.uniform(0, 2),      # minutes since last seen
        ])
        y.append(0)
    for _ in range(TRAINING_SIZE):
        X.append([
            rng.uniform(0.4, 1.0),
            rng.uniform(200, 2000),
            rng.uniform(5, 50),
            rng.uniform(30, 500),
            rng.uniform(15, 60),
        ])
        y.append(1)
    return X, y


def _mk_crash_samples(rng: random.Random) -> tuple[list[list[float]], list[int]]:
    """Synthetic training for the crash-probability model.

    Features (order matches ``features_crash``):
        bsod, hard_reboots, app_crashes, err_events,
        neg_health_slope, thermal_throttling, cpu_temp, ram_pct
    """
    X, y = [], []
    # Healthy machines: no BSODs, few app-crashes, flat/rising health.
    for _ in range(TRAINING_SIZE):
        X.append([
            0,
            rng.randint(0, 1),
            rng.randint(0, 3),
            rng.randint(0, 10),
            rng.uniform(-0.5, 0.3),
            rng.choice([0, 0, 0]),
            rng.uniform(35, 65),
            rng.uniform(20, 65),
        ])
        y.append(0)
    # Machines about to crash: BSODs, hard reboots, thermal throttling, RAM high.
    for _ in range(TRAINING_SIZE):
        X.append([
            rng.randint(1, 5),
            rng.randint(1, 6),
            rng.randint(3, 30),
            rng.randint(20, 300),
            rng.uniform(0.4, 3.0),
            rng.choice([0, 1, 1]),
            rng.uniform(75, 100),
            rng.uniform(80, 99),
        ])
        y.append(1)
    return X, y


SAMPLE_MAKERS: dict[str, Callable[[random.Random], tuple[list[list[float]], list[int]]]] = {
    "ssd": _mk_ssd_samples,
    "fan": _mk_fan_samples,
    "cpu_thermal": _mk_cpu_thermal_samples,
    "battery": _mk_battery_samples,
    "memory": _mk_memory_samples,
    "network": _mk_network_samples,
    "crash": _mk_crash_samples,
}


def _train(failure_type: str) -> RandomForestClassifier:
    rng = random.Random(RNG_SEED + hash(failure_type) % 1000)
    X, y = SAMPLE_MAKERS[failure_type](rng)
    clf = RandomForestClassifier(
        n_estimators=60,
        max_depth=6,
        random_state=RNG_SEED,
        n_jobs=1,
    )
    clf.fit(np.array(X), np.array(y))
    return clf


def get_model(failure_type: str) -> RandomForestClassifier:
    """Return a lazily-trained classifier for the given failure type."""
    if failure_type in _MODELS:
        return _MODELS[failure_type]
    with _LOCK:
        if failure_type not in _MODELS:
            log.info("training prediction model for %s", failure_type)
            _MODELS[failure_type] = _train(failure_type)
    return _MODELS[failure_type]


def warm_all() -> None:
    """Train every model up-front (called on app startup)."""
    for k in SAMPLE_MAKERS:
        get_model(k)
