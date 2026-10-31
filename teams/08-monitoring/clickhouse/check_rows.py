#!/usr/bin/env python3
"""Verify that ClickHouse row counts equal JSONL line counts and `null` values are stored as NULL.

Usage:
    python -I teams/08-monitoring/clickhouse/check_rows.py
    python -I teams/08-monitoring/clickhouse/check_rows.py \
        teams/05-architecture/experiments/evidence/run_a/metrics.jsonl \
        teams/05-architecture/experiments/evidence/run_b/metrics.jsonl \
        teams/06-performance/results/modal_gpu/h200_v1.json
    python -I teams/08-monitoring/clickhouse/check_rows.py --selftest
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_jsonl import (  # noqa: E402
    DEFAULT_CH_URL,
    DEFAULT_SOURCES,
    ch_Exec,
    ensure_schema,
    load_source,
    parse_source,
)


def query_run_counts(run_id: str, url: str = DEFAULT_CH_URL) -> dict:
    """Query line/step count, total metric row count, and NULL count from ClickHouse `metrics_raw`."""
    safe_run = run_id.replace("'", "''")
    sql = (
        "SELECT "
        "uniqExact(tuple(step, time, rank)) AS ch_lines, "
        "count() AS ch_metric_rows, "
        "countIf(value IS NULL) AS ch_null_rows "
        f"FROM metrics_raw WHERE run_id = '{safe_run}' "
        "FORMAT JSONEachRow"
    )
    out = ch_Exec(sql, url=url).strip()
    if not out:
        return {"ch_lines": 0, "ch_metric_rows": 0, "ch_null_rows": 0}
    row = json.loads(out.splitlines()[0])
    return {
        "ch_lines": int(row["ch_lines"]),
        "ch_metric_rows": int(row["ch_metric_rows"]),
        "ch_null_rows": int(row["ch_null_rows"]),
    }


def list_manifest_sources(url: str = DEFAULT_CH_URL) -> list[tuple[str, str]]:
    """Return `[(source_file, run_id), ...]` from `ingest_manifest`."""
    ensure_schema(url=url)
    sql = (
        "SELECT source_file, run_id "
        "FROM ingest_manifest FINAL "
        "ORDER BY run_id, source_file "
        "FORMAT JSONEachRow"
    )
    out = ch_Exec(sql, url=url).strip()
    if not out:
        return []
    pairs = []
    for line in out.splitlines():
        if line.strip():
            r = json.loads(line)
            pairs.append((r["source_file"], r["run_id"]))
    return pairs


def verify_source(source: str, run_id_override: str | None = None, url: str = DEFAULT_CH_URL) -> dict:
    """Compare source file line/metric/null counts against ClickHouse `metrics_raw`."""
    parsed = parse_source(source, run_id_override=run_id_override)
    run_id = parsed["run_id"]
    ch = query_run_counts(run_id, url=url)

    lines_match = ch["ch_lines"] == parsed["jsonl_lines"]
    metrics_match = ch["ch_metric_rows"] == parsed["metric_rows"]
    nulls_match = ch["ch_null_rows"] == parsed["null_rows"]
    ok = lines_match and metrics_match and nulls_match

    return {
        "ok": ok,
        "run_id": run_id,
        "source_file": parsed["source_file"],
        "jsonl_lines": parsed["jsonl_lines"],
        "ch_lines": ch["ch_lines"],
        "expected_metric_rows": parsed["metric_rows"],
        "ch_metric_rows": ch["ch_metric_rows"],
        "expected_null_rows": parsed["null_rows"],
        "ch_null_rows": ch["ch_null_rows"],
    }


def run_selftest(url: str = DEFAULT_CH_URL) -> bool:
    """Verify that a JSONL file containing `null` and non-finite values loads with equal line counts and NULL values."""
    test_run_id = "_check_rows_selftest"
    sample_lines = [
        {"step": 0, "time": "2026-10-31T00:00:00Z", "loss_ntp": 4.2, "validation_loss": None, "mfu": None},
        {"step": 1, "time": "2026-10-31T00:00:01Z", "loss_ntp": 3.9, "validation_loss": 4.0, "mfu": 0.35},
        {"step": 2, "time": "2026-10-31T00:00:02Z", "loss_ntp": "nan", "validation_loss": None, "mfu": 0.36},
    ]
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as tmp:
        for row in sample_lines:
            tmp.write(json.dumps(row) + "\n")
        tmp_path = Path(tmp.name)

    try:
        load_source(str(tmp_path), run_id_override=test_run_id, url=url)
        res = verify_source(str(tmp_path), run_id_override=test_run_id, url=url)
        assert res["ok"], f"Self-test failed: {res}"
        assert res["jsonl_lines"] == 3 and res["ch_lines"] == 3, f"Line count mismatch: {res}"
        assert res["expected_metric_rows"] == 9 and res["ch_metric_rows"] == 9, f"Metric row mismatch: {res}"
        assert res["expected_null_rows"] == 4 and res["ch_null_rows"] == 4, f"NULL row mismatch: {res}"
        print(
            f"  [PASS] selftest: jsonl_lines={res['jsonl_lines']} == ch_lines={res['ch_lines']}, "
            f"metric_rows={res['ch_metric_rows']}, null_rows={res['ch_null_rows']} (stored as NULL)"
        )
        return True
    finally:
        tmp_path.unlink(missing_ok=True)
        ch_Exec(
            f"ALTER TABLE metrics_raw DELETE WHERE run_id = '{test_run_id}' SETTINGS mutations_sync = 2",
            url=url,
        )
        ch_Exec(
            f"ALTER TABLE ingest_manifest DELETE WHERE run_id = '{test_run_id}' SETTINGS mutations_sync = 2",
            url=url,
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verify ClickHouse rows equal JSONL lines for loaded files.")
    ap.add_argument("sources", nargs="*", help="Files or directories to check (default: all loaded files in manifest)")
    ap.add_argument("--run-id", default=None, help="Explicit run_id override (when checking a single file)")
    ap.add_argument("--selftest", action="store_true", help="Run null-handling and line-count self-test")
    ap.add_argument("--url", default=DEFAULT_CH_URL, help=f"ClickHouse HTTP URL (default: {DEFAULT_CH_URL})")
    args = ap.parse_args(argv)

    if args.selftest:
        run_selftest(url=args.url)

    targets: list[tuple[str, str | None]] = []
    if args.sources:
        for s in args.sources:
            targets.append((s, args.run_id if len(args.sources) == 1 else None))
    else:
        manifest = list_manifest_sources(url=args.url)
        if manifest:
            targets = [(src, rid) for src, rid in manifest]
        elif not args.selftest:
            targets = [(s, None) for s in DEFAULT_SOURCES]

    all_ok = True
    for src, rid in targets:
        res = verify_source(src, run_id_override=rid, url=args.url)
        status = "PASS" if res["ok"] else "FAIL"
        print(
            f"[{status}] run_id={res['run_id']!r} source={res['source_file']} | "
            f"lines: file={res['jsonl_lines']} ch={res['ch_lines']} | "
            f"metric_rows: file={res['expected_metric_rows']} ch={res['ch_metric_rows']} | "
            f"null_rows: file={res['expected_null_rows']} ch={res['ch_null_rows']}"
        )
        if not res["ok"]:
            all_ok = False

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
