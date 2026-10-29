import math

import numpy as np
import pytest
import torch

from alarms import AlarmMonitor, max_vio_and_dead, run_synthetic


def test_synthetic_3000_steps():
    res = run_synthetic(steps=3000, seed=15)
    assert res["steps"] == 3000
    assert res["planted"] == 11
    assert res["caught"] == 11
    assert res["missed"] == 0
    assert res["false_alarms"] == 0


@pytest.mark.parametrize("bad", [
    float("nan"), float("inf"), float("-inf"),
    "nan", "inf", "-inf",
    np.float32("nan"), np.float32("inf"),
    torch.tensor(float("nan")), torch.tensor(float("-inf")),
])
def test_non_finite_fires_stop_at_once(bad):
    mon = AlarmMonitor()
    out = mon.check(0, "loss_ntp", bad)
    assert len(out) == 1
    assert out[0]["rule"] == "non_finite"
    assert out[0]["severity"] == "stop"
    assert out[0]["metric"] == "loss_ntp"


def test_spike_score_7sigma_and_no_window_poisoning():
    mon = AlarmMonitor(window=200, min_window=100, sigma_threshold=7.0)
    for s in range(150):
        # Small deterministic oscillation around 2.0 (std ~ 0.01)
        val = 2.0 + (0.01 if s % 2 == 0 else -0.01)
        assert mon.step(s, loss_ntp=val) == []

    # Two consecutive spikes must both page because the first spike does not enter the window.
    a1 = mon.step(150, loss_ntp=2.5)
    a2 = mon.step(151, loss_ntp=2.5)
    assert len(a1) == 1 and a1[0]["rule"] == "spike_score" and a1[0]["severity"] == "page"
    assert len(a2) == 1 and a2[0]["rule"] == "spike_score" and a2[0]["severity"] == "page"


def test_duplicate_loss_and_loss_ntp_fires_once():
    mon = AlarmMonitor()
    out = mon.step(0, loss_ntp=float("nan"), loss=float("nan"))
    assert len(out) == 1
    assert out[0]["metric"] == "loss_ntp"


def test_ema_z_warns_without_paging():
    mon = AlarmMonitor(window=500, min_window=100, sigma_threshold=7.0, ema_warmup=50, ema_z_threshold=2.5)
    for s in range(100):
        val = 1.0 + (0.02 if s % 2 == 0 else -0.02)
        assert mon.step(s, gradient_norm=val) == []
    # 4 sigma excursion: above EMA z=2.5 (warn), below 7 sigma (page).
    out = mon.step(100, gradient_norm=1.08)
    assert len(out) == 1
    assert out[0]["rule"] == "ema_z"
    assert out[0]["severity"] == "warn"


def test_throughput_drop_fires_once_at_patience():
    mon = AlarmMonitor(tps_window=50, tps_drop_fraction=0.10, tps_patience=100)
    # Step 0 setup is ignored.
    assert mon.step(0, tokens_per_second=500.0) == []
    for s in range(1, 51):
        assert mon.step(s, tokens_per_second=40000.0) == []
    fired = []
    for s in range(51, 170):
        fired.extend(mon.step(s, tokens_per_second=32000.0))  # 20% drop
    assert len(fired) == 1
    assert fired[0]["step"] == 150
    assert fired[0]["rule"] == "throughput_drop"


def test_moe_routing_max_vio_and_dead_experts():
    mv, dead = max_vio_and_dead([0.5, 0.5, 0.0, 0.0])
    assert math.isclose(mv, 1.0)
    assert dead == 2

    mon = AlarmMonitor(moe_max_vio_limit=1.0, moe_patience=5)
    for s in range(4):
        assert mon.step(s, expert_load=[0.7, 0.3, 0.0, 0.0]) == []
    out = mon.step(4, expert_load=[0.7, 0.3, 0.0, 0.0])
    assert len(out) == 1
    assert out[0]["rule"] == "moe_routing"
    assert out[0]["dead_experts"] == 2
