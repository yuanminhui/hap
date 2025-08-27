import os
from pathlib import Path

import pytest

from hap.lib import fileutil as fu


def test_get_files_from_dir_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        fu.get_files_from_dir(str(tmp_path / "nope"))
    f = tmp_path / "file.txt"
    f.write_text("hello")
    with pytest.raises(NotADirectoryError):
        fu.get_files_from_dir(str(f))


def test_get_files_and_is_empty_and_extension(tmp_path):
    d = tmp_path / "d"; d.mkdir()
    assert fu.is_dir_empty(str(d)) is True
    (d / "a.txt").write_text("x")
    (d / "b.csv").write_text("y")
    all_files = fu.get_files_from_dir(str(d))
    assert len(all_files) == 2
    txt_files = fu.get_files_from_dir(str(d), extension="txt")
    assert any(p.endswith("a.txt") for p in txt_files)
    assert not any(p.endswith("b.csv") for p in txt_files)


def test_gzip_ungzip_roundtrip(tmp_path):
    p = tmp_path / "t.tsv"
    p.write_text("a\tb\n")
    gz = fu.gzip_file(str(p))
    assert gz.endswith(".gz") and Path(gz).exists()
    out = fu.ungzip_file(gz)
    assert out == str(p)
    assert Path(out).read_text() == "a\tb\n"
    # calling gzip on .gz returns same path
    assert fu.gzip_file(gz) == gz
    # ungzip on non-gz returns same path
    assert fu.ungzip_file(str(p)) == str(p)


def test_is_tab_delimited_and_remove_suffix(tmp_path):
    q = tmp_path / "x.txt"
    q.write_text("a\tb\n")
    assert fu.is_tab_delimited(str(q)) is True
    q.write_text("abc\n")
    assert fu.is_tab_delimited(str(q)) is False
    assert fu.remove_suffix_containing("abc.def.gfa", ".gfa") == "abc.def"
    assert fu.remove_suffix_containing("abc", ".gfa") == "abc"


def test_create_and_remove_tmp_files(tmp_path):
    files = fu.create_tmp_files(3)
    for fp in files:
        assert Path(fp).exists()
    fu.remove_files(files)
    for fp in files:
        assert not Path(fp).exists()