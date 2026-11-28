"""Private panels 39-43: alarm state, events list, expert load distribution and router balance (Week 5, item 3)."""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import urllib.parse
import urllib.request
import uuid

import pytest

HERE = Path(__file__).resolve().parent
PRIVATE_JSON = HERE / "private_v1.json"
ALARM_STATE, EVENTS, DISTRIBUTION, BALANCE = 39, 40, 42, 43


def _dash():
    return json.loads(PRIVATE_JSON.read_text(encoding="utf-8"))


def _panels():
    return {p["id"]: p for p in _dash()["panels"]}


def _sql(pid):
    return _panels()[pid]["targets"][0]["rawSql"]


def test_panels_and_layer_variable():
    d = _dash()
    ids = [p["id"] for p in d["panels"]]
    assert len(ids) == len(set(ids))
    p = _panels()
    assert p[ALARM_STATE]["type"] == p[EVENTS]["type"] == "table"
    assert p[DISTRIBUTION]["type"] == p[BALANCE]["type"] == "trend"
    assert "FROM run_events FINAL" in _sql(ALARM_STATE) and "FROM run_events FINAL" in _sql(EVENTS)
    assert "'${layer}'" in _sql(DISTRIBUTION) and "expert_load.%.%" in _sql(BALANCE)
    layer = next(v for v in d["templating"]["list"] if v["name"] == "layer")
    assert not layer["multi"] and "expert_load.%.%" in layer["query"]


def test_panel_32_counts_commits_as_well_as_events():
    sql = _panels()[32]["targets"][0]["rawSql"]
    assert sql.count("countIf(event IN ('events.loaded', 'commits.loaded')) = 0") == 4
    assert "countIf(event = 'events.loaded') = 0" not in sql


def test_even_share_line_is_dashed():
    ov = next(o for o in _panels()[DISTRIBUTION]["fieldConfig"]["overrides"] if o["matcher"]["options"] == ".* even share$")
    props = {p["id"]: p["value"] for p in ov["properties"]}
    assert props["custom.lineStyle"]["fill"] == "dash"


def _ch(sql: str, data: bytes | None = None) -> str:
    url = "http://127.0.0.1:8123/?" + urllib.parse.urlencode({"query": sql})
    with urllib.request.urlopen(urllib.request.Request(url, data=data or b"", method="POST"), timeout=10) as r:
        return r.read().decode("utf-8")


def _ch_up() -> bool:
    try:
        return _ch("SELECT 1").strip() == "1"
    except Exception:
        return False


def _rows(sql: str, run: str, layer: str = "0"):
    q = sql.replace("$event_run", f"'{run}'").replace("$run", f"'{run}'").replace("${layer}", layer)
    return [json.loads(x) for x in _ch(q + " FORMAT JSONEachRow").strip().splitlines()]


@pytest.mark.skipif(not _ch_up(), reason="ClickHouse server is not reachable on 127.0.0.1:8123")
def test_panel_sql_on_clickhouse():
    sys.path.insert(0, str(HERE.parent / "clickhouse"))
    from load_jsonl import ensure_schema
    from load_run_events import alarm_row, coverage_row, ensure_table, insert_rows, parse_commits  # noqa: F401
    ensure_schema()
    ensure_table()
    run = f"test-evx-{uuid.uuid4().hex[:8]}"
    events = [alarm_row({"step": 50, "metric": "indic_share", "rule": "indic_share", "severity": "page"}, run),
              alarm_row({"step": 120, "metric": "tokens_per_second", "rule": "throughput_drop", "severity": "warn"}, run),
              alarm_row({"step": 180, "metric": "tokens_per_second", "rule": "throughput_drop", "severity": "warn"}, run),
              coverage_row(run, "alarms"), coverage_row(run, "commits"),
              {"run_id": run, "event_time": "2026-11-27 10:00:00.000", "step": 100, "kind": "checkpoint",
               "event": "checkpoint.committed", "severity": "", "detail": "{}", "source": "commits", "event_key": f"{run}-c100"}]
    metrics = [{"run_id": run, "step": s, "time": "2026-11-27 00:00:00.000", "name": "loss_ntp", "value": 5.0 - s / 100}
               for s in (0, 50, 100, 120, 180)]
    metrics[0]["value"] = 0.0  # the record's placeholder at step 0
    for step, loads in ((50, [[8, 0, 0, 0], [1, 1, 1, 1]]), (100, [[2, 2, 2, 2], [4, 2, 1, 1]])):
        for layer, row in enumerate(loads):
            for expert, v in enumerate(row):
                metrics.append({"run_id": run, "step": step, "time": "2026-11-27 00:00:00.000",
                                "name": f"expert_load.{layer}.{expert}", "value": float(v)})
    try:
        insert_rows(events)
        _ch("INSERT INTO metrics_raw FORMAT JSONEachRow", "\n".join(map(json.dumps, metrics)).encode())

        state = {r["rule"]: r for r in _rows(_sql(ALARM_STATE), run)}
        assert state["indic_share"]["state"] == "fired" and int(state["indic_share"]["first_step"]) == 50
        assert state["throughput_drop"]["state"] == "fired" and int(state["throughput_drop"]["hits"]) == 2
        assert int(state["throughput_drop"]["last_step"]) == 180 and state["throughput_drop"]["severity"] == "warn"
        assert state["non_finite"]["state"] == "ok" and int(state["non_finite"]["hits"]) == 0
        assert state["ema_z"]["state"] == "off by default"
        assert len(state) == 8

        ev = _rows(_sql(EVENTS), run)
        assert [(int(r["step"]), r["kind"]) for r in ev] == [(50, "alarm"), (100, "checkpoint"), (120, "alarm"), (180, "alarm")]
        assert math.isclose(float(ev[1]["training_loss"]), 4.0)

        dist = _rows(_sql(DISTRIBUTION), run, layer="0")
        at50 = {r["series"]: float(r["value"]) for r in dist if int(r["step"]) == 50}
        assert math.isclose(at50[f"{run} expert 00"], 1.0) and math.isclose(at50[f"{run} even share"], 0.25)
        for step in (50, 100):
            shares = [float(r["value"]) for r in dist if int(r["step"]) == step and "expert" in r["series"]]
            assert math.isclose(sum(shares), 1.0)

        bal = {(int(r["step"]), r["series"]): float(r["value"]) for r in _rows(_sql(BALANCE), run)}
        assert math.isclose(bal[(50, f"{run} layer 0")], 25.0)    # avg 2 / max 8: one expert takes every pick
        assert math.isclose(bal[(50, f"{run} layer 1")], 100.0)   # perfectly even
        assert math.isclose(bal[(100, f"{run} layer 1")], 50.0)   # avg 2 / max 4
    finally:
        _ch(f"ALTER TABLE run_events DELETE WHERE run_id = '{run}' SETTINGS mutations_sync = 2")
        _ch(f"ALTER TABLE metrics_raw DELETE WHERE run_id = '{run}' SETTINGS mutations_sync = 2")
