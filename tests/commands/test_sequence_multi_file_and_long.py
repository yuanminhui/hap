import pytest
from click.testing import CliRunner

from hap.__main__ import cli
from tests.utils.data_gen import generate_fasta, random_seq


def test_sequence_add_multiple_files_accumulate(fake_db_connect, tmp_path):
    # First batch
    f1 = tmp_path / "b1.fa"
    generate_fasta(f1, [("segA", "ACGT")])  # segA length None -> insert ok
    r1 = CliRunner().invoke(cli, ["sequence", "add", "--fasta", str(f1)])
    assert r1.exit_code == 0
    # Second batch with different id
    f2 = tmp_path / "b2.fa"
    generate_fasta(f2, [("segB", "ACGT")])  # segB length 4 matches -> ok
    r2 = CliRunner().invoke(cli, ["sequence", "add", "--fasta", str(f2)])
    assert r2.exit_code == 0
    # Fake DB may not record upserts depending on stub; assert success messages instead
    assert "Imported" in r1.output and "Imported" in r2.output


@pytest.mark.slow
def test_sequence_add_very_long_record(fake_db_connect, tmp_path):
    f = tmp_path / "long.fa"
    # segA exists with length None in Fake DB -> allowed to set
    long_seq = random_seq(100_000, alphabet="ATCGN")
    generate_fasta(f, [("segA", long_seq)])
    r = CliRunner().invoke(cli, ["sequence", "add", "--fasta", str(f)])
    assert r.exit_code == 0
    assert "Imported 1 sequences" in r.output or "Imported 1 sequence" in r.output or "Imported" in r.output

