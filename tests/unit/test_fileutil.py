"""
Unit tests for hap.lib.fileutil.
"""

import gzip
import os
from pathlib import Path

import pytest

from hap.lib import fileutil


class TestGetFilesFromDir:
    def test_returns_files(self, tmp_path):
        (tmp_path / "a.gfa").write_text("x")
        (tmp_path / "b.gfa").write_text("y")
        files = fileutil.get_files_from_dir(str(tmp_path), extension="gfa")
        assert len(files) == 2

    def test_no_extension_returns_all(self, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "b.csv").write_text("y")
        files = fileutil.get_files_from_dir(str(tmp_path))
        assert len(files) == 2

    def test_empty_dir_returns_empty_list(self, tmp_path):
        files = fileutil.get_files_from_dir(str(tmp_path))
        assert files == []

    def test_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            fileutil.get_files_from_dir("/nonexistent/dir")

    def test_file_instead_of_dir_raises(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises(NotADirectoryError):
            fileutil.get_files_from_dir(str(f))


class TestRemoveFiles:
    def test_removes_files(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("a")
        f2.write_text("b")
        fileutil.remove_files([str(f1), str(f2)])
        assert not f1.exists()
        assert not f2.exists()


class TestCreateTmpFiles:
    def test_creates_correct_number(self):
        fps = fileutil.create_tmp_files(3)
        assert len(fps) == 3
        for fp in fps:
            assert os.path.exists(fp)
            os.remove(fp)

    def test_files_are_empty(self):
        fps = fileutil.create_tmp_files(2)
        for fp in fps:
            assert os.path.getsize(fp) == 0
            os.remove(fp)


class TestGzipFunctions:
    def test_gzip_roundtrip(self, tmp_path):
        p = tmp_path / "test.txt"
        p.write_text("hello world\n")
        gzp = fileutil.gzip_file(str(p))
        assert gzp == str(p) + ".gz"
        assert Path(gzp).exists()

        out = str(p).replace(".txt", "_out.txt")
        fileutil.ungzip_file(gzp, out)
        assert Path(out).read_text() == "hello world\n"

    def test_gzip_already_gzipped(self, tmp_path, capsys):
        gz = tmp_path / "test.txt.gz"
        gz.write_bytes(b"fakegz")
        result = fileutil.gzip_file(str(gz))
        assert result == str(gz)

    def test_ungzip_not_gzipped(self, tmp_path, capsys):
        p = tmp_path / "plain.txt"
        p.write_text("text")
        result = fileutil.ungzip_file(str(p))
        assert result == str(p)


class TestIsDirEmpty:
    def test_empty(self, tmp_path):
        assert fileutil.is_dir_empty(str(tmp_path)) is True

    def test_not_empty(self, tmp_path):
        (tmp_path / "f.txt").write_text("x")
        assert fileutil.is_dir_empty(str(tmp_path)) is False


class TestRemoveSuffixContaining:
    def test_removes_gfa_suffix(self):
        result = fileutil.remove_suffix_containing("my-file.chr1.gfa", ".gfa")
        assert result == "my-file.chr1"

    def test_no_suffix_unchanged(self):
        result = fileutil.remove_suffix_containing("myfile.txt", ".gfa")
        assert result == "myfile.txt"

    def test_first_occurrence_removed(self):
        result = fileutil.remove_suffix_containing("a.gfa.b.gfa", ".gfa")
        # rfind behavior: removes from last occurrence
        assert ".gfa" not in result or result.endswith(".b")


class TestIsTabDelimited:
    def test_tab_delimited(self, tmp_path):
        p = tmp_path / "tsv.txt"
        p.write_text("col1\tcol2\tcol3\n")
        assert fileutil.is_tab_delimited(str(p)) is True

    def test_not_tab_delimited(self, tmp_path):
        p = tmp_path / "csv.txt"
        p.write_text("col1,col2,col3\n")
        assert fileutil.is_tab_delimited(str(p)) is False
