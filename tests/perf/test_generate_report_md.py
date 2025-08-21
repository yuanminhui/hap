from pathlib import Path


def test_generate_report_md(tmp_path):
    perf_dir = tmp_path / "reports" / "perf"
    perf_dir.mkdir(parents=True, exist_ok=True)
    (perf_dir / "sequence_add_large.csv").write_text("metric,value\nwall_time_s,1.23\nrss_delta_bytes,456\n")
    (perf_dir / "build_big.csv").write_text("metric,value\nwall_time_s,2.34\nrss_delta_bytes,789\n")
    report = tmp_path / "REPORT.md"
    content = [
        "# Performance Report\n\n",
        "## Sequence Add Large\n",
        "- wall_time_s: 1.23\n- rss_delta_bytes: 456\n\n",
        "## Build Big\n",
        "- wall_time_s: 2.34\n- rss_delta_bytes: 789\n",
    ]
    report.write_text("".join(content))
    assert report.exists() and report.stat().st_size > 0

