-- ERA V5 Team 08 (Monitoring & Records) — ClickHouse Rollups v1
-- 1. Step rollups at 10, 100, 1,000, and 10,000 steps (`min`, `max`, `mean`, `last`).
-- 2. 1-second rollup for GPU telemetry (`gpu_telemetry_1s`).

-- ============================================================================
-- 10-step rollup
-- ============================================================================
CREATE TABLE IF NOT EXISTS metrics_rollup_10_agg
(
    run_id      LowCardinality(String),
    step_bucket UInt64,
    name        LowCardinality(String),
    rank        UInt16,
    min_state   AggregateFunction(min, Float64),
    max_state   AggregateFunction(max, Float64),
    mean_state  AggregateFunction(avg, Float64),
    last_state  AggregateFunction(argMax, Float64, Tuple(UInt64, DateTime64(3, 'UTC'))),
    count_state AggregateFunction(count, Float64)
)
ENGINE = AggregatingMergeTree
ORDER BY (run_id, name, step_bucket, rank);

CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_rollup_10_mv
TO metrics_rollup_10_agg
AS
SELECT
    run_id,
    intDiv(step, 10) * 10 AS step_bucket,
    name,
    rank,
    minState(assumeNotNull(value)) AS min_state,
    maxState(assumeNotNull(value)) AS max_state,
    avgState(assumeNotNull(value)) AS mean_state,
    argMaxState(assumeNotNull(value), tuple(step, time)) AS last_state,
    countState(assumeNotNull(value)) AS count_state
FROM metrics_raw
WHERE value IS NOT NULL
GROUP BY run_id, step_bucket, name, rank;

CREATE OR REPLACE VIEW metrics_rollup_10 AS
SELECT
    run_id,
    intDiv(step, 10) * 10 AS step_bucket,
    name,
    rank,
    min(value) AS min,
    max(value) AS max,
    avg(value) AS mean,
    argMax(value, tuple(step, time)) AS last,
    count(value) AS count
FROM metrics_raw
WHERE value IS NOT NULL
GROUP BY run_id, step_bucket, name, rank
ORDER BY run_id, name, step_bucket, rank;

-- ============================================================================
-- 100-step rollup
-- ============================================================================
CREATE TABLE IF NOT EXISTS metrics_rollup_100_agg
(
    run_id      LowCardinality(String),
    step_bucket UInt64,
    name        LowCardinality(String),
    rank        UInt16,
    min_state   AggregateFunction(min, Float64),
    max_state   AggregateFunction(max, Float64),
    mean_state  AggregateFunction(avg, Float64),
    last_state  AggregateFunction(argMax, Float64, Tuple(UInt64, DateTime64(3, 'UTC'))),
    count_state AggregateFunction(count, Float64)
)
ENGINE = AggregatingMergeTree
ORDER BY (run_id, name, step_bucket, rank);

CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_rollup_100_mv
TO metrics_rollup_100_agg
AS
SELECT
    run_id,
    intDiv(step, 100) * 100 AS step_bucket,
    name,
    rank,
    minState(assumeNotNull(value)) AS min_state,
    maxState(assumeNotNull(value)) AS max_state,
    avgState(assumeNotNull(value)) AS mean_state,
    argMaxState(assumeNotNull(value), tuple(step, time)) AS last_state,
    countState(assumeNotNull(value)) AS count_state
FROM metrics_raw
WHERE value IS NOT NULL
GROUP BY run_id, step_bucket, name, rank;

CREATE OR REPLACE VIEW metrics_rollup_100 AS
SELECT
    run_id,
    intDiv(step, 100) * 100 AS step_bucket,
    name,
    rank,
    min(value) AS min,
    max(value) AS max,
    avg(value) AS mean,
    argMax(value, tuple(step, time)) AS last,
    count(value) AS count
FROM metrics_raw
WHERE value IS NOT NULL
GROUP BY run_id, step_bucket, name, rank
ORDER BY run_id, name, step_bucket, rank;

-- ============================================================================
-- 1,000-step rollup
-- ============================================================================
CREATE TABLE IF NOT EXISTS metrics_rollup_1000_agg
(
    run_id      LowCardinality(String),
    step_bucket UInt64,
    name        LowCardinality(String),
    rank        UInt16,
    min_state   AggregateFunction(min, Float64),
    max_state   AggregateFunction(max, Float64),
    mean_state  AggregateFunction(avg, Float64),
    last_state  AggregateFunction(argMax, Float64, Tuple(UInt64, DateTime64(3, 'UTC'))),
    count_state AggregateFunction(count, Float64)
)
ENGINE = AggregatingMergeTree
ORDER BY (run_id, name, step_bucket, rank);

CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_rollup_1000_mv
TO metrics_rollup_1000_agg
AS
SELECT
    run_id,
    intDiv(step, 1000) * 1000 AS step_bucket,
    name,
    rank,
    minState(assumeNotNull(value)) AS min_state,
    maxState(assumeNotNull(value)) AS max_state,
    avgState(assumeNotNull(value)) AS mean_state,
    argMaxState(assumeNotNull(value), tuple(step, time)) AS last_state,
    countState(assumeNotNull(value)) AS count_state
FROM metrics_raw
WHERE value IS NOT NULL
GROUP BY run_id, step_bucket, name, rank;

CREATE OR REPLACE VIEW metrics_rollup_1000 AS
SELECT
    run_id,
    intDiv(step, 1000) * 1000 AS step_bucket,
    name,
    rank,
    min(value) AS min,
    max(value) AS max,
    avg(value) AS mean,
    argMax(value, tuple(step, time)) AS last,
    count(value) AS count
FROM metrics_raw
WHERE value IS NOT NULL
GROUP BY run_id, step_bucket, name, rank
ORDER BY run_id, name, step_bucket, rank;

-- ============================================================================
-- 10,000-step rollup
-- ============================================================================
CREATE TABLE IF NOT EXISTS metrics_rollup_10000_agg
(
    run_id      LowCardinality(String),
    step_bucket UInt64,
    name        LowCardinality(String),
    rank        UInt16,
    min_state   AggregateFunction(min, Float64),
    max_state   AggregateFunction(max, Float64),
    mean_state  AggregateFunction(avg, Float64),
    last_state  AggregateFunction(argMax, Float64, Tuple(UInt64, DateTime64(3, 'UTC'))),
    count_state AggregateFunction(count, Float64)
)
ENGINE = AggregatingMergeTree
ORDER BY (run_id, name, step_bucket, rank);

CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_rollup_10000_mv
TO metrics_rollup_10000_agg
AS
SELECT
    run_id,
    intDiv(step, 10000) * 10000 AS step_bucket,
    name,
    rank,
    minState(assumeNotNull(value)) AS min_state,
    maxState(assumeNotNull(value)) AS max_state,
    avgState(assumeNotNull(value)) AS mean_state,
    argMaxState(assumeNotNull(value), tuple(step, time)) AS last_state,
    countState(assumeNotNull(value)) AS count_state
FROM metrics_raw
WHERE value IS NOT NULL
GROUP BY run_id, step_bucket, name, rank;

CREATE OR REPLACE VIEW metrics_rollup_10000 AS
SELECT
    run_id,
    intDiv(step, 10000) * 10000 AS step_bucket,
    name,
    rank,
    min(value) AS min,
    max(value) AS max,
    avg(value) AS mean,
    argMax(value, tuple(step, time)) AS last,
    count(value) AS count
FROM metrics_raw
WHERE value IS NOT NULL
GROUP BY run_id, step_bucket, name, rank
ORDER BY run_id, name, step_bucket, rank;

-- ============================================================================
-- 1-second GPU telemetry rollup
-- ============================================================================
CREATE TABLE IF NOT EXISTS gpu_telemetry_1s_agg
(
    run_id      LowCardinality(String),
    time_1s     DateTime('UTC'),
    name        LowCardinality(String),
    rank        UInt16,
    min_state   AggregateFunction(min, Float64),
    max_state   AggregateFunction(max, Float64),
    mean_state  AggregateFunction(avg, Float64),
    last_state  AggregateFunction(argMax, Float64, Tuple(DateTime64(3, 'UTC'), UInt64)),
    count_state AggregateFunction(count, Float64)
)
ENGINE = AggregatingMergeTree
ORDER BY (run_id, name, time_1s, rank);

CREATE MATERIALIZED VIEW IF NOT EXISTS gpu_telemetry_1s_mv
TO gpu_telemetry_1s_agg
AS
SELECT
    run_id,
    toStartOfSecond(time, 'UTC') AS time_1s,
    name,
    rank,
    minState(assumeNotNull(value)) AS min_state,
    maxState(assumeNotNull(value)) AS max_state,
    avgState(assumeNotNull(value)) AS mean_state,
    argMaxState(assumeNotNull(value), tuple(time, step)) AS last_state,
    countState(assumeNotNull(value)) AS count_state
FROM metrics_raw
WHERE value IS NOT NULL
  AND name IN (
      'gpu_utilization', 'gpu_util_pct',
      'gpu_memory_used', 'mem_used_mib', 'mem_util_pct',
      'gpu_alloc_gb', 'gpu_alloc_gib',
      'sm_clock_mhz', 'mem_clock_mhz',
      'power_w', 'temp_c', 'gpu_temp_c'
  )
GROUP BY run_id, time_1s, name, rank;

CREATE OR REPLACE VIEW gpu_telemetry_1s AS
SELECT
    run_id,
    toStartOfSecond(time, 'UTC') AS time_1s,
    name,
    rank,
    min(value) AS min,
    max(value) AS max,
    avg(value) AS mean,
    argMax(value, tuple(time, step)) AS last,
    count(value) AS count
FROM metrics_raw
WHERE value IS NOT NULL
  AND name IN (
      'gpu_utilization', 'gpu_util_pct',
      'gpu_memory_used', 'mem_used_mib', 'mem_util_pct',
      'gpu_alloc_gb', 'gpu_alloc_gib',
      'sm_clock_mhz', 'mem_clock_mhz',
      'power_w', 'temp_c', 'gpu_temp_c'
  )
GROUP BY run_id, time_1s, name, rank
ORDER BY run_id, name, time_1s, rank;
