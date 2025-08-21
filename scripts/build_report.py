from pathlib import Path


def read_csv_metrics(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    metrics: dict[str, str] = {}
    for line in path.read_text().strip().splitlines()[1:]:
        if not line:
            continue
        k, v = line.split(",", 1)
        metrics[k] = v
    return metrics


def main() -> None:
    perf_dir = Path("reports/perf")
    report = Path("REPORT.md")
    perf_dir.mkdir(parents=True, exist_ok=True)
    seq = read_csv_metrics(perf_dir / "sequence_add_large.csv")
    bld = read_csv_metrics(perf_dir / "build_big.csv")
    lines = ["# Performance Report\n\n"]
    if seq:
        lines.append("## Sequence Add Large\n")
        for k, v in seq.items():
            lines.append(f"- {k}: {v}\n")
        lines.append("\n")
    if bld:
        lines.append("## Build Big\n")
        for k, v in bld.items():
            lines.append(f"- {k}: {v}\n")
        lines.append("\n")
    report.write_text("".join(lines))


if __name__ == "__main__":
    main()

