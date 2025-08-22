from pathlib import Path


def read_csv_metrics(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    metrics: dict[str, str] = {}
    lines = path.read_text().strip().splitlines()
    for line in lines[1:]:  # skip header
        if not line:
            continue
        if "," in line:
            k, v = line.split(",", 1)
            metrics[k] = v
    return metrics


def section_table(title: str, metrics: dict[str, str]) -> list[str]:
    if not metrics:
        return []
    lines = [f"## {title}\n\n", "| metric | value |\n", "|---|---|\n"]
    for k, v in metrics.items():
        lines.append(f"| {k} | {v} |\n")
    lines.append("\n")
    return lines


def main() -> None:
    perf_dir = Path("reports/perf")
    report = Path("REPORT.md")
    perf_dir.mkdir(parents=True, exist_ok=True)

    seq_small = read_csv_metrics(perf_dir / "sequence_add_small.csv")
    seq_medium = read_csv_metrics(perf_dir / "sequence_add_medium.csv")
    seq_large = read_csv_metrics(perf_dir / "sequence_add_large.csv")
    build_big = read_csv_metrics(perf_dir / "build_big.csv")

    out: list[str] = ["# Performance Report\n\n"]
    out += section_table("Sequence Add Small", seq_small)
    out += section_table("Sequence Add Medium", seq_medium)
    out += section_table("Sequence Add Large", seq_large)
    out += section_table("Build Big", build_big)

    if len(out) == 1:  # only title
        out.append("No performance data found.\n")

    report.write_text("".join(out))


if __name__ == "__main__":
    main()

