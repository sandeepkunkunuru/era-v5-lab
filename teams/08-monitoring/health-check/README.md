# Node health-check JSON format (`v5-health/1`)

`health_check.py` defines the JSON contract between Team 7's node health scripts (`gpu_health.sh`,
`xid_scan.py`, `nccl_probe.py`, `launch.sh`) and Team 8's monitoring and ClickHouse loader.

```bash
python -I teams/08-monitoring/health-check/health_check.py --selftest
python -I teams/08-monitoring/health-check/health_check.py --validate node_health.jsonl
python -I teams/08-monitoring/health-check/health_check.py --clickhouse-jsonl node_health.jsonl
python -I teams/08-monitoring/health-check/health_check.py --example full
```

## 1. Top-level report (`v5-health/1`)

Each run of `gpu_health.sh` writes one JSON object to stdout (and one line when appended to a `.jsonl` node log):

```json
{
  "schema": "v5-health/1",
  "host": "gpu-node-01",
  "timestamp_utc": "2026-10-28T12:00:00+00:00",
  "mode": "prolog",
  "expected_gpus": 8,
  "verdict": "pass",
  "admit_training": true,
  "checks": [
    {
      "name": "gpu_inventory",
      "status": "pass",
      "required": true,
      "reason": "",
      "metrics": {"count": 8, "gpus": ["0, GPU-0000, NVIDIA H100 80GB HBM3, 81559, 81000, 38"]}
    }
  ],
  "drain_reason": null
}
```

| Field | Type | Rule |
|---|---|---|
| `schema` | `"v5-health/1"` | Versioned contract name. |
| `host` | `str` | Node hostname (`hostname -s` or `socket.gethostname()`). |
| `timestamp_utc` | `str` | ISO-8601 UTC timestamp (`time` accepted as an alias). |
| `mode` | `"prolog"` \| `"periodic"` \| `"full"` | `prolog` before a job starts; `periodic` every 30 s while a node is up; `full` before dry runs or after a repair. |
| `expected_gpus` | `int` | Expected GPU count on the node (`8` on H100/B200 nodes, `0` on a CPU-only test host). |
| `verdict` | `"pass"` \| `"warn"` \| `"fail"` | Derived from `checks` (see §2). |
| `admit_training` | `bool` | `true` only when `verdict == "pass"` and (when `expected_gpus > 0`) GPUs are present. |
| `checks` | `list[dict]` | Non-empty list of check records (see §3). |
| `drain_reason` | `str` \| `null` | Non-empty string naming the failing check(s) when `verdict == "fail"`; `null` otherwise. |

## 2. Verdict and missing-tool rules

Every check has `status` in `{"pass", "warn", "fail", "skipped"}` and a boolean `required`:

1. Any check with `status == "fail"` $\rightarrow$ `verdict = "fail"`.
2. Otherwise any check with `status == "warn"`, or any check with `status == "skipped"` and `required == true`, $\rightarrow$ `verdict = "warn"`.
3. Otherwise $\rightarrow$ `verdict = "pass"`.

A missing tool (`nvidia-smi`, `journalctl`, `dcgmi`, `torchrun`) must be reported as `"skipped"` with a non-empty `reason`. It never turns into `"pass"`.

## 3. Standard checks and `metrics` fields

| Check `name` | Mode | `metrics` fields | Fail condition |
|---|---|---|---|
| `gpu_inventory` | all | `count` (`int`), `gpus` (`list[str]`) | `nvidia-smi` fails, or `expected_gpus > 0` and `count != expected_gpus`. |
| `xid` | all | `counts` (`{code: int}`), `events` (`[{pci_bdf, code, severity, reason}]`) | Any event with `severity == "fail"`. |
| `ecc_uncorrectable` | all | `values` (`list[int]`, one per GPU) | Any GPU has uncorrectable volatile ECC $> 0$. |
| `dcgm_quick` | `full` | `exit_code` (`int`), `output_tail` (`str`) | `dcgmi diag -r 1` returns non-zero. |
| `nvlink` | `full` | optional link summary | Any active NVLink link down. |
| `nccl_all_reduce` | `full` | `g7-collective/1` object (`backend`, `world_size`, `status`, `sizes`) | Non-zero `max_error`, `all_ranks_correct == false`, timeout, or `backend != "nccl"`. |

CPU `gloo` runs of `nccl_probe.py` are valid standalone smoke tests (`schema: "g7-collective/1"`, `backend: "gloo"`), but a passing `nccl_all_reduce` check inside a node health report requires `backend == "nccl"` and `world_size >= 2`.

## 4. Xid classification

`xid_scan.py` parses `NVRM: Xid (PCI:<bdf>): <code>` from `journalctl -k` (default last 30 minutes) or a test file:

| Severity | Xid codes | Action |
|---|---|---|
| `fail` | `48` (DBE ECC), `64` (row-remap failure), `74` (NVLink), `79` (fell off bus), `95` (uncontained memory), `119` / `120` (GSP) | Block admission, page on-call, drain node. |
| `warn` or `fail` | `63` (row-remap event), `94` (contained memory error) | Block admission; restart affected job and drain if repeated. |
| `warn` | `13` (graphics engine), `31` (MMU page fault), `43` (app stopped), `45` (channel cleanup), or any unlisted code | Block admission in `launch.sh`; inspect before clearing. |

## 5. Week 2 ClickHouse loader row (`--clickhouse-jsonl`)

Each validated `v5-health/1` line maps to one row for the `node_health` table so that ClickHouse row counts match JSONL line counts:

| Column | Type | Source |
|---|---|---|
| `timestamp_utc` | `String` | `report.timestamp_utc` |
| `host` | `String` | `report.host` |
| `mode` | `LowCardinality(String)` | `report.mode` |
| `expected_gpus`, `gpus_seen` | `UInt8` | `report.expected_gpus`, `gpu_inventory.metrics.count` |
| `verdict` | `LowCardinality(String)` | `report.verdict` |
| `admit_training` | `UInt8` | `report.admit_training` |
| `drain_reason` | `String` | `report.drain_reason` (`""` when `null`) |
| `checks_pass`, `checks_warn`, `checks_fail`, `checks_skipped` | `UInt8` | Counts by status in `report.checks` |
| `xid_codes` | `Array(UInt16)` | Sorted integer keys of `xid.metrics.counts` |
| `ecc_uncorrectable_total` | `UInt32` | Sum of `ecc_uncorrectable.metrics.values` |
| `nccl_status` | `LowCardinality(String)` | `nccl_all_reduce.status` (`"not_run"` in `prolog`) |
| `raw_json` | `String` | Full canonical JSON line |

## 6. Self-test results

`python -I teams/08-monitoring/health-check/health_check.py --selftest`: 15/15 passed, including Team 7's `health_injected_xid.json` fixture, standalone `xid_scan.py` and `nccl_probe.py` outputs, missing-tool `skipped` handling, non-integer `world_size` handling, `xid.counts` vs `xid.events` consistency, required `gpu_inventory` when `expected_gpus > 0`, and ClickHouse row flattening.
