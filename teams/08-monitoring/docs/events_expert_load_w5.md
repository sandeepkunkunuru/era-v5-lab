# Events view and expert load charts (Week 5, design task 3)

Capstone Lab 5 asks for a training dashboard with an **Events** view (as in the V4 LightningLM dashboard: checkpoints,
restarts, alarms with their state) and an **expert load distribution** chart (load per expert over steps, a dashed line
at the even share, an "even %" readout), plus router balance per layer. This file shows them on the real dry run 2
record (#869). Panels are in `grafana/private_v1.json`.

## 1. What is built

| Part | Where | What it does |
|---|---|---|
| `--commits` input | `clickhouse/load_run_events.py` | Reads Team 07's `commits.jsonl` (`ckpt/ckpt.py`): one `checkpoint` row per commit, with its real commit time; a rise in `epoch` (a new attempt took over the run) is a `restart` row. For runs with no event files, such as dry run 2. Store paths are not stored. |
| Panel 32 | infra health per run | Checkpoint and restart columns now count when either event files or `commits.jsonl` were loaded (blank only when neither was). |
| Panel 39 | Alarm state per rule | Every `alarms.py` rule for each run whose alarm hits were loaded: **fired** (hits, first and last step, severity), **ok** (ran, did not fire) or **off by default** (`ema_z`, `static_bound`, `val_regression`). |
| Panel 40 | Events list | Checkpoints, restarts and alarm hits in step order, with the training loss (`loss_ntp`) at that step. |
| Panel 42 | Expert load distribution, layer `$layer` | Each expert's share of its layer's picks per logged step, with the even share (1 / experts) dashed. |
| Panel 43 | Router balance per layer | **even %** = 100 × average expert load / busiest expert load per layer (100% even; 50% = busiest gets twice the average). Equals 100 / `expert_load_imbalance`. The legend's current value is the "even %" readout. |

## 2. Dry run 2 on the panels (28 Nov, local ClickHouse 24.8)

Loaded: `commits.jsonl` (9 lines) and the alarm hits of the composition replay
([`alarms/replay_dryrun2_indic_share.log`](../alarms/replay_dryrun2_indic_share.log)), both under `dryrun2-1234`.

**Panel 32:** 0 restarts, 9 checkpoints, 0 failed; alarm hits 0 stop, 2 page, 1 warn; last event step 1,221.

**Panel 39 (alarm state):**

| Rule | State | Hits | First / last step |
|---|---|---:|---|
| non_finite | ok | 0 | |
| spike_score | fired (page) | 1 | 1,184 |
| ema_z | off by default | 0 | |
| throughput_drop | fired (warn) | 1 | 226 |
| moe_routing | ok (**blind, see section 4**) | 0 | |
| static_bound | off by default | 0 | |
| val_regression | off by default | 0 | |
| indic_share | fired (page) | 1 | 50 |

**Panel 40 (events):** checkpoints at steps 0, 195, 350, 513, 672, 836, 993, 1,150 and 1,221 (commit times
27 Nov 09:44:55 to 11:08:54 UTC, reasons start / interval / final, all attempt 1, so no restart), and the three alarm
hits at 50, 226 and 1,184. Training loss at the checkpoints falls from 6.80 (step 195) to 5.24 (step 1,221).
Checkpoint duration and size are not in `commits.jsonl`, so they are not shown for this run.

**Panels 42 and 43 (expert load, 8 layers x 16 experts, every 50 steps):**

| Step | even % per layer (0 to 7) |
|---:|---|
| 50 | 12.6, 12.6, 12.5, 12.7, 13.3, 12.5, 12.7, 12.7 |
| 150 | 22.2, 28.7, 21.5, 22.6, 13.8, 17.0, 18.8, 19.1 |
| 600 | 76.4, 38.6, 60.8, 49.7, 79.3, 62.2, 66.6, 58.6 |
| 1,200 | 56.0, 41.1, 44.0, 68.2, 60.6, 59.2, 71.8, 40.3 |

## 3. Finding: routing starts collapsed and recovers

At step 50 every layer's even % is about 12.5%: one expert takes about half of its layer's picks (8 × the average; in
layer 0, expert 02 has 49.8% of the picks). The balance improves by step 600 and ends between 40% and 72% per layer.
The run's own alarms did not show this (section 4).

## 4. Finding: `moe_routing` is blind on dry run 2's `expert_load`

`alarms.py` rule 5 (`moe_routing`) did not fire on dry run 2, although every layer had MaxVio near 7 at step 50, far
over its limit of 1.0. Two reasons, both reproduced on the record:

| `expert_load` passed as | `moe_patience` | `moe_routing` hits |
|---|---:|---:|
| as logged: a list of 8 per-layer lists | 1 | **0** |
| the same data as `{layer: list}` | 1 | **113** (from step 50, MaxVio about 7.0 in each layer) |
| the same data as `{layer: list}` | 2 | **0** |

1. **Format.** The rule treats only a dict as per-layer data. A list of lists becomes one "layer" whose values are
   lists; they fail the number check and the streak resets on every row, so nothing is ever evaluated.
2. **Sparse logging.** A gap in step numbers (`step != last + 1`) resets the streak. With `expert_load` every 50 steps
   the streak never passes 1, so any `moe_patience` above 1 cannot fire.

So panel 39's "ok" for `moe_routing` on this run means "could not see the data", not "routing was fine". The fix belongs
in `alarms.py` (accept a list of per-layer lists; count consecutive *logged* rows, not consecutive steps). It is reported
to the alarm owners rather than changed here, because it changes the rule's behaviour for every replay.

## 5. Reproduce

```bash
python -I teams/08-monitoring/metrics_logger/dryrun2_composition.py teams/05-architecture/results/dryrun2-1234/metrics.jsonl --out ./out/dryrun2-1234/metrics.jsonl
python -I teams/08-monitoring/alarms/alarms.py --jsonl ./out/dryrun2-1234/metrics.jsonl > ./out/dryrun2-1234/alarms.jsonl
python -I teams/08-monitoring/clickhouse/load_jsonl.py --run-id dryrun2-1234 ./out/dryrun2-1234/metrics.jsonl
python -I teams/08-monitoring/clickhouse/load_run_events.py --run-id dryrun2-1234 \
  --commits teams/05-architecture/results/dryrun2-1234/commits.jsonl --alarms ./out/dryrun2-1234/alarms.jsonl
# then panels 32 and 39-43 in grafana/private_v1.json (run / event run = dryrun2-1234, layer = 0)
PYTHONPATH=teams/08-monitoring pytest teams/08-monitoring/clickhouse/tests/test_run_events.py \
  teams/08-monitoring/grafana/test_private_events_expert_panels.py -q
```
