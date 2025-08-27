def test_rewrite_gfa_with_length_and_clear_sequence(tmp_path):
    from hap.commands.build import rewrite_gfa_with_length_and_clear_sequence

    # GFA1: add LN and clear sequence
    g1 = tmp_path / "a.gfa"
    g1.write_text("S\t1\tACG\nS\t2\t*\tLN:i:5\n")
    id_to_len = {"1": 3, "2": 5}
    rewrite_gfa_with_length_and_clear_sequence(str(g1), id_to_len)
    lines = g1.read_text().splitlines()
    assert lines[0].startswith("S\t1\t*") and "LN:i:3" in lines[0]
    assert lines[1] == "S\t2\t*\tLN:i:5"

    # GFA2 style: third field is length, fourth is sequence; ensure sequence cleared to *
    g2 = tmp_path / "b.gfa"
    g2.write_text("S\t1\t3\tACG\n")
    rewrite_gfa_with_length_and_clear_sequence(str(g2), {"1": 3})
    assert g2.read_text().strip().endswith("\t*")

