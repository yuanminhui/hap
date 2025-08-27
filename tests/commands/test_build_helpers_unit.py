import importlib
from pathlib import Path


def test_collect_segment_ids_from_gfa(tmp_path):
    build = importlib.import_module("hap.commands.build")
    p = tmp_path / "a.gfa"
    p.write_text("""H	VN:Z:1.0
S	s0	*	LN:i:1
S	s1	*	LN:i:2
L	s0	+	s1	+	0M
""")
    ids = build.collect_segment_ids_from_gfa(str(p))
    assert ids == {"s0", "s1"}


def test_filter_sequence_tsv_by_ids(tmp_path):
    build = importlib.import_module("hap.commands.build")
    full = tmp_path / "full.tsv"
    full.write_text("""s0	ACGT
badline
s1	A

s2	TT
""")
    outp = tmp_path / "out.tsv"
    ids = {"s0", "s2"}
    id2len = build.filter_sequence_tsv_by_ids(str(full), ids, str(outp))
    assert id2len == {"s0": 4, "s2": 2}
    assert outp.read_text().strip().splitlines() == ["s0\tACGT", "s2\tTT"]


def test_rewrite_gfa_with_length_and_clear_sequence_gfa1(tmp_path):
    build = importlib.import_module("hap.commands.build")
    gfa = tmp_path / "g1.gfa"
    gfa.write_text("""H	VN:Z:1.0
S	s0	ACGT
S	s1	*
""")
    build.rewrite_gfa_with_length_and_clear_sequence(str(gfa), {"s0": 4, "s1": 1})
    txt = gfa.read_text().splitlines()
    # s0 should have LN and *; s1 already * and may add LN
    assert any(line.startswith("S\ts0\t*\t") and "LN:i:4" in line for line in txt)
    assert any(line.startswith("S\ts1\t*") for line in txt)


def test_rewrite_gfa_with_length_and_clear_sequence_gfa2(tmp_path):
    build = importlib.import_module("hap.commands.build")
    gfa = tmp_path / "g2.gfa"
    # GFA2 style: fields[2] is length, fields[3] is sequence
    gfa.write_text("""H	VN:Z:2.0
S	sA	10	AC
S	sB	5	*
""")
    build.rewrite_gfa_with_length_and_clear_sequence(str(gfa), {"sA": 10, "sB": 5})
    txt = gfa.read_text().splitlines()
    assert any(line.startswith("S\tsA\t10\t*") for line in txt)
    assert any(line.startswith("S\tsB\t5\t*") for line in txt)