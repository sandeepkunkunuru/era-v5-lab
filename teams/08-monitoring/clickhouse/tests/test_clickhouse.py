import json
import math
from pathlib import Path
import sys
import tempfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_rows import run_selftest, verify_source  # noqa: E402
from load_jsonl import ch_Exec, ensure_schema, load_source, parse_source  # noqa: E402


def _ch_available() -> bool:
    try:
        return "1" in ch_Exec("SELECT 1")
    except Exception:
        return False


def test_parse_team5_and_team6_sources_offline():
    p_a = parse_source("teams/05-architecture/experiments/evidence/run_a/metrics.jsonl")
    assert p_a["run_id"] == "run_a"
    assert p_a["jsonl_lines"] == 40
    assert p_a["metric_rows"] == 240
    assert p_a["null_rows"] == 0

    p_b = parse_source("teams/05-architecture/experiments/evidence/run_b/")
    assert p_b["run_id"] == "run_b"
    assert p_b["jsonl_lines"] == 40
    assert p_b["metric_rows"] == 240

    p_g6 = parse_source("teams/06-performance/results/modal_gpu/h200_v1.json")
    assert p_g6["run_id"] == "h200_v1"
    assert p_g6["jsonl_lines"] == 150
    assert p_g6["metric_rows"] > 150
    names = {r["name"] for r in p_g6["rows"]}
    assert {"step_ms", "mfu", "model_flops_utilization", "gpu_utilization", "gpu_memory_used"} <= names


def test_parse_live_g6_events_and_null_handling():
    sample = "\n".join([
        json.dumps({
            "schema_version": 1,
            "event": "step_timing",
            "timestamp": "2026-10-30T12:09:59.413Z",
            "run_id": "g6_live_test",
            "node_id": "modal",
            "rank": 0,
            "local_rank": 0,
            "step": 1,
            "data_ms": 0.95,
            "raw_step_ms": 82.93,
        }),
        json.dumps({
            "schema_version": 1,
            "event": "gpu_sample",
            "timestamp": "2026-10-30T12:10:00.189Z",
            "run_id": "g6_live_test",
            "node_id": "modal",
            "gpu": {"name": "NVIDIA A100", "index": 0, "uuid": "GPU-1234", "pci_bus_id": "[Unknown Error]"},
            "step": 2,
            "metrics": {"gpu_util_pct": 64.0, "mem_used_mib": 8105.0, "power_w": 133.35, "temp_c": 41.0},
            "slowdown_flags": [],
        }),
        json.dumps({
            "step": 3,
            "time": "2026-10-30T12:10:01.000Z",
            "loss_ntp": None,
            "mfu": None,
            "mfu_unavailable_reason": "unknown_gpu",
            "gradient_norm": "nan",
        }),
    ])
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as tmp:
        tmp.write(sample + "\n")
        tmp_path = Path(tmp.name)

    try:
        parsed = parse_source(str(tmp_path))
        assert parsed["run_id"] == "g6_live_test"
        assert parsed["jsonl_lines"] == 3
        assert parsed["null_rows"] == 3
        by_name = {(r["step"], r["name"]): r["value"] for r in parsed["rows"]}
        assert math.isclose(by_name[(1, "loader_wait_time")], 0.00095)
        assert math.isclose(by_name[(2, "gpu_utilization")], 64.0)
        assert math.isclose(by_name[(2, "gpu_memory_used")], 8105.0 * 1048576.0)
        assert by_name[(3, "loss_ntp")] is None
        assert by_name[(3, "mfu")] is None
        assert by_name[(3, "gradient_norm")] is None
    finally:
        tmp_path.unlink(missing_ok=True)


@pytest.mark.skipif(not _ch_available(), reason="ClickHouse server is not reachable on CLICKHOUSE_URL")
def test_clickhouse_end_to_end_load_check_and_rollups():
    ensure_schema()
    assert run_selftest() is True

    for src in (
        "teams/05-architecture/experiments/evidence/run_a/metrics.jsonl",
        "teams/05-architecture/experiments/evidence/run_b/metrics.jsonl",
        "teams/06-performance/results/modal_gpu/h200_v1.json",
    ):
        load_source(src)
        res = verify_source(src)
        assert res["ok"], f"Verification failed for {src}: {res}"

    # Verify 10-step and 100-step rollups on `run_a` (40 steps -> 4 buckets in rollup_10, 1 bucket in rollup_100)
    r10 = ch_Exec(
        "SELECT step_bucket, min, max, mean, last, count "
        "FROM metrics_rollup_10 WHERE run_id = 'run_a' AND name = 'loss_ntp' "
        "ORDER BY step_bucket FORMAT JSONEachRow"
    ).strip().splitlines()
    assert len(r10) == 4
    b0 = json.loads(r10[0])
    assert int(b0["step_bucket"]) == 0
    assert int(b0["count"]) == 10
    assert b0["min"] <= b0["mean"] <= b0["max"]

    r100 = ch_Exec(
        "SELECT step_bucket, count FROM metrics_rollup_100 "
        "WHERE run_id = 'run_a' AND name = 'loss_ntp' FORMAT JSONEachRow"
    ).strip().splitlines()
    assert len(r100) == 1
    assert int(json.loads(r100[0])["count"]) == 40

    # Verify 1s GPU telemetry rollup has h200_v1 telemetry metrics
    g1s = ch_Exec(
        "SELECT name, count FROM gpu_telemetry_1s "
        "WHERE run_id = 'h200_v1' ORDER BY name FORMAT JSONEachRow"
    ).strip().splitlines()
    g_names = {json.loads(line)["name"] for line in g1s}
    assert {"gpu_utilization", "gpu_memory_used", "power_w", "temp_c"} <= g_names
