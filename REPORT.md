# Performance Report (Initial Baseline)

This report summarizes initial performance baselines measured by the test suite.

- Sequence add (>=100MB by many records)
  - Source: tests/perf/test_perf_cli.py
  - Output CSV: reports/perf/sequence_add_large.csv
  - Metrics recorded: wall_time_s, rss_delta_bytes

Planned next steps:
- Add build-path benchmarking (small/medium/large), include split/merge phases
- Summarize IO throughput and peak RSS for each data size
- Provide before/after comparison upon optimizations (>10% improvement)