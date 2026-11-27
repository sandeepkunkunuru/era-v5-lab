# Open infrastructure health: Week 4 evidence (`run_events`, panels 32 and 33)

Week 4 public dashboard upgrade 4 in [`dashboard_content_decisions_w4.md`](dashboard_content_decisions_w4.md):
restarts, alarm hits and checkpoints shown openly. The stored data and the private panels are on main (#774). This file
shows them working on real data from the repository, and gives the commands for dry run 2.

## 1. What is built (#774)

| Part | File | What it does |
|---|---|---|
| Table | [`clickhouse/run_events.sql`](../clickhouse/run_events.sql) | One row per restart (`restore.done`), checkpoint commit or failure, and alarm hit. `ReplacingMergeTree` on `(run_id, event_key)`, read with `FINAL`: a reload never double-counts, so numbers do not reset. |
| Loader | [`clickhouse/load_run_events.py`](../clickhouse/load_run_events.py) | Reads Team 07's `v5-event/1` lines (`common/events.py`, `$V5_EVENTS_DIR`) and `alarms/alarms.py --jsonl` output, unchanged. Never stores host names, job ids, store paths or file names. |
| Panels | `grafana/private_v1.json` panels 32 and 33 | 32: a table per run (restarts, failed restores, checkpoints, failed checkpoints, alarm hits by severity). 33: each kind of event counted up against the step. |

A blank cell in panel 32 means that input was never loaded for the run; a 0 means it was loaded and nothing happened.

## 2. Evidence on real data (27 Nov 2026, local ClickHouse 24.8)

Two real inputs from the repository, each loaded **twice**:

1. **Dry run 1, alarms.** `alarms.py --jsonl` on `teams/05-architecture/jobs/evidence/2026-11-15-dryrun1-full/metrics.jsonl`
   (1,222 steps, #475 / #620): 3 alarm hits.
2. **Team 07 CPU restart drill.** `teams/07-infrastructure/results/restart_cpu_rotation_03.txt` (4 planned SIGKILLs, each
   followed by a restore from the last committed checkpoint): 4 `restore.done` events. 19 other lines (supervisor lines,
   the result table) are skipped and counted.

**Panel 32** (its own SQL, both runs selected):

| run_id | restarts | failed_restores | checkpoints | failed_checkpoints | alarm_stop | alarm_page | alarm_warn | last_event_step |
|:-|-:|-:|-:|-:|-:|-:|-:|-:|
| dryrun1_full | *blank* | *blank* | *blank* | *blank* | 0 | 3 | 0 | 841 |
| team7_cpu_restart_drill | 4 | 0 | 0 | 0 | *blank* | *blank* | *blank* | 150 |

**Panel 33** (its own SQL):

| step | series | events so far |
|-:|:-|-:|
| 25 | team7_cpu_restart_drill restart | 1 |
| 75 | team7_cpu_restart_drill restart | 2 |
| 125 | team7_cpu_restart_drill restart | 3 |
| 150 | team7_cpu_restart_drill restart | 4 |
| 468 | dryrun1_full alarm | 1 |
| 505 | dryrun1_full alarm | 2 |
| 841 | dryrun1_full alarm | 3 |

What this shows:

- **Consistent with the existing record.** The 3 alarm hits are the `gradient_norm` `spike_score` pages at steps 468, 505
  and 841 that [`alarms_dryrun1.md`](../alarms_dryrun1.md) section 4 lists for the same file.
- **One restart per kill.** The drill's 4 kills give 4 restarts, at the 4 restored steps (25, 75, 125, 150).
- **No double counting.** Each input was loaded twice; the counts are the same as after one load.
- **No false zeros.** Dry run 1 ran without Team 07's `Checkpointer` ([`restore_dryrun1.md`](../../07-infrastructure/results/restore_dryrun1.md)
  section 1), so it has no events: its restart and checkpoint cells are blank, not 0. The drill had no alarm check, so its
  alarm cells are blank.

`test_run_events.py::test_dryrun1_alarms_match_alarms_dryrun1_md` repeats the dry run 1 part offline (no ClickHouse), so
this result cannot drift without a failing test.

## 3. What the alarm counts do and do not cover

The alarm columns count what `alarms.py --jsonl` reports with its defaults (`AlarmMonitor()`, no bounds). As #839
(`alarms/core_nikshrimali.md`) found, that means:

- `non_finite`, `spike_score` and `throughput_drop` run on the metrics dry run 1 and 2 log.
- Memory and MFU alarms need bounds that the CLI does not set, and `gpu_memory_used` / `model_flops_utilization` are not
  in dry run 1's `metrics.jsonl`. Expert alarms need `expert_load`, also absent. **A 0 in the alarm columns does not mean
  these were checked.** The public version of this panel must say which rules had data.

## 4. Dry run 2: commands (companion job #833)

Team 07 asked TSAI to start all three dry run 2 runs with `V5_EVENTS_DIR=./out/dryrun2-1234-events RUN_ID=dryrun2-1234`
and return that folder. After the run:

```bash
# Team 07 events: restarts, checkpoint commits and failures (the folder as returned; one file per process)
python -I teams/08-monitoring/clickhouse/load_run_events.py --events ./out/dryrun2-1234-events --run-id dryrun2-1234 --dry-run
python -I teams/08-monitoring/clickhouse/load_run_events.py --events ./out/dryrun2-1234-events --run-id dryrun2-1234

# Alarm hits from each run's metrics.jsonl, under the same run id
for d in dryrun2-1234 dryrun2-1234-resume-a dryrun2-1234-resume-b; do
  python -I teams/08-monitoring/alarms/alarms.py --jsonl ./out/$d/metrics.jsonl > ./out/monitoring/$d-alarms.jsonl
done
python -I teams/08-monitoring/clickhouse/load_run_events.py --run-id dryrun2-1234 \
  --alarms ./out/monitoring/dryrun2-1234-alarms.jsonl \
  --alarms ./out/monitoring/dryrun2-1234-resume-a-alarms.jsonl \
  --alarms ./out/monitoring/dryrun2-1234-resume-b-alarms.jsonl
```

Expected in panel 32 for `dryrun2-1234`: `restarts` = 2 if both kills (#738 (a) and (b)) run, 1 if only (a);
`checkpoints` = the number of committed saves; alarm hits by severity. A hit repeated on a re-run step after a restore is
counted once (same rule, metric, step and severity).

**Known issue.** `alarms.py --jsonl` stops with `JSONDecodeError` if a file ends in a half-written line, which a SIGKILL
can leave in the killed run's `metrics.jsonl` (reproduced on main at `57bdc7b`). Until that is fixed in `alarms.py`,
drop a torn last line before running it: `python -c "import sys;p=sys.argv[1];t=open(p).read();open(p,'w').write(t[:t.rfind(chr(10))+1])" FILE`
on a copy of the file. `load_run_events.py` itself already skips torn lines.

## 5. Reproduce section 2

```bash
docker start era-v5-clickhouse        # clickhouse/README.md section 1
python -I teams/08-monitoring/alarms/alarms.py --jsonl teams/05-architecture/jobs/evidence/2026-11-15-dryrun1-full/metrics.jsonl > /tmp/dryrun1_alarms.jsonl
python -I teams/08-monitoring/clickhouse/load_run_events.py --alarms /tmp/dryrun1_alarms.jsonl --run-id dryrun1_full
python -I teams/08-monitoring/clickhouse/load_run_events.py --events teams/07-infrastructure/results/restart_cpu_rotation_03.txt --run-id team7_cpu_restart_drill
# then panel 32 / 33's SQL from grafana/private_v1.json with $event_run = 'dryrun1_full','team7_cpu_restart_drill'
PYTHONPATH=teams/08-monitoring pytest teams/08-monitoring/clickhouse/tests/test_run_events.py -q
```
