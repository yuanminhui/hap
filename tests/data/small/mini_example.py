from pathlib import Path

GFA_TEXT = """H	VN:Z:1.0
S	segA	*	LN:i:4
S	segB	*	LN:i:4
L	segA	+	segB	+	0M
"""

FASTA_TEXT = ">segA\nACGT\n>segB\nACGT\n"


def ensure_small_dataset(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    gfa = root / "mini-example.gfa"
    nodes = root / "nodes.fa"
    if not gfa.exists():
        gfa.write_text(GFA_TEXT)
    if not nodes.exists():
        nodes.write_text(FASTA_TEXT)
    return {"gfa": gfa, "nodes": nodes}

