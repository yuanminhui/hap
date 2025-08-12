import contextlib
from pathlib import Path
import types
import importlib
import pytest
from click.testing import CliRunner

from hap.__main__ import cli
from hap.lib.util_obj import ValidationResult


@pytest.fixture()
def gfa_rel_path(prepare_rel_mini_example_files):
    return prepare_rel_mini_example_files["gfa"]


def _monkey_build_pipeline(monkeypatch, gfa_path, seq_file=None):
    build = importlib.import_module("hap.commands.build")
    gfa = importlib.import_module("hap.lib.gfa")

    # Replace GFA class with lightweight dummy to avoid external tools
    class DummyGFA:
        def __init__(self, filepath: str):
            self.filepath = filepath
        def divide_into_subgraphs(self, outdir: str, chr_only: bool = True):
            return [("", str(gfa_path))]
        def separate_sequence(self, output_dir: str):
            return (self.filepath, None)
        def ensure_length_completeness(self):
            return None
        def can_extract_length(self):
            return True
        def get_haplotypes(self):
            return ["dummy"]
        def to_igraph(self):
            return types.SimpleNamespace()
    monkeypatch.setattr(gfa, "GFA", DummyGFA)

    # validations -> valid
    monkeypatch.setattr(build, "validate_gfa", lambda *args, **kwargs: ValidationResult(True, ""))
    monkeypatch.setattr(build, "validate_graph", lambda *args, **kwargs: ValidationResult(True, ""))
    monkeypatch.setattr(build, "check_name", lambda name: True)

    # override parallel builder to avoid multiprocessing and file ops
    def _fake_parallel(subgraph_items, min_resolution, temp_dir):
        result = []
        for name, path in subgraph_items:
            regions = types.SimpleNamespace()
            segments = types.SimpleNamespace()
            meta = {"sources": [], "name": name}
            result.append((regions, segments, meta, None))
        return result
    monkeypatch.setattr(build, "build_subgraphs_with_sequence_in_parallel", _fake_parallel)

    # override preprocessed pipeline as well
    monkeypatch.setattr(build, "prepare_preprocessed_subgraphs_in_parallel", lambda subgraph_items, sequence_file_tsv, temp_dir: [(name, path, str(sequence_file_tsv)) for name, path in subgraph_items])
    monkeypatch.setattr(build, "build_preprocessed_subgraphs_in_parallel", lambda preprocessed, min_resolution: [(types.SimpleNamespace(), types.SimpleNamespace(), {"sources": [], "name": name}, tsv) for (name, path, tsv) in preprocessed])

    # db.auto_connect -> nullcontext(fake conn)
    db = importlib.import_module("hap.lib.database")
    class _FakeConn:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def cursor(self):
            class _C:
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    return False
                def execute(self, *a, **k):
                    pass
                def executemany(self, *a, **k):
                    pass
                def copy_from(self, *a, **k):
                    pass
                def fetchone(self):
                    return None
                def fetchall(self):
                    return []
            return _C()
        def commit(self):
            pass
        def rollback(self):
            pass

    monkeypatch.setattr(db, "auto_connect", lambda: contextlib.nullcontext(_FakeConn()))

    # hap2db stub: assert shapes and capture inputs
    captured = {}

    def _hap2db(hap_info, subgraphs, conn):
        captured["hap_info"] = hap_info
        captured["subgraphs"] = subgraphs

    monkeypatch.setattr(build, "hap2db", _hap2db)

    return captured


def test_build_run_no_sequence_file(monkeypatch, runner, gfa_rel_path):
    captured = _monkey_build_pipeline(monkeypatch, gfa_rel_path)

    r = runner.invoke(
        cli,
        [
            "build",
            "run",
            str(gfa_rel_path),
            "-n",
            "hap1",
            "-a",
            "clade1",
            "-c",
            "me",
            "-x",
            "desc",
        ],
    )
    assert r.exit_code == 0
    assert captured["hap_info"]["name"] == "hap1"
    # subgraphs should be list with one tuple and last element is sequence file path or None
    assert isinstance(captured["subgraphs"], list)


def test_build_run_with_fasta_sequence_file(monkeypatch, runner, tmp_path, gfa_rel_path, prepare_rel_mini_example_files):
    captured = _monkey_build_pipeline(monkeypatch, gfa_rel_path)

    # Use the prepared nodes.fa (relative path) as external sequence file
    nodes_fa = prepare_rel_mini_example_files["nodes"]

    r = runner.invoke(
        cli,
        [
            "build",
            "run",
            str(gfa_rel_path),
            "-n",
            "hap2",
            "-a",
            "clade1",
            "-c",
            "me",
            "-x",
            "desc",
            "--sequence-file",
            str(nodes_fa),
        ],
    )
    assert r.exit_code == 0
    assert captured["hap_info"]["name"] == "hap2"


def test_build_run_with_tsv_sequence_file(monkeypatch, runner, tmp_path, gfa_rel_path, prepare_rel_mini_example_files):
    captured = _monkey_build_pipeline(monkeypatch, gfa_rel_path)

    # Convert nodes.fa to TSV in a tmp
    nodes_fa = prepare_rel_mini_example_files["nodes"]
    tsv = tmp_path / "nodes.tsv"
    # Simple conversion: id<tab>seq
    content = nodes_fa.read_text().splitlines()
    with tsv.open("w") as out:
        for i in range(0, len(content), 2):
            if content[i].startswith(">"):
                out.write(f"{content[i][1:]}\t{content[i+1]}\n")

    r = runner.invoke(
        cli,
        [
            "build",
            "run",
            str(gfa_rel_path),
            "-n",
            "hap3",
            "-a",
            "clade1",
            "-c",
            "me",
            "-x",
            "desc",
            "--sequence-file",
            str(tsv),
        ],
    )
    assert r.exit_code == 0
    assert captured["hap_info"]["name"] == "hap3"


def test_build_run_sequence_file_is_dir_error(monkeypatch, runner, tmp_path, gfa_rel_path):
    _ = _monkey_build_pipeline(monkeypatch, gfa_rel_path)

    r = runner.invoke(
        cli,
        [
            "build",
            "run",
            str(gfa_rel_path),
            "-n",
            "hap4",
            "-a",
            "clade1",
            "-c",
            "me",
            "-x",
            "desc",
            "--sequence-file",
            str(tmp_path),
        ],
    )
    assert r.exit_code != 0
    assert "--sequence-file must be a single file" in r.output


def test_build_validate_arg_path(monkeypatch, runner, tmp_path, gfa_rel_path):
    # multi files without -s should error
    g2 = tmp_path / "b.gfa"
    g2.write_text(gfa_rel_path.read_text())
    r = runner.invoke(
        cli,
        [
            "build",
            "run",
            str(gfa_rel_path),
            str(g2),
            "-n",
            "hap5",
            "-a",
            "clade1",
            "-c",
            "me",
            "-x",
            "desc",
        ],
    )
    assert r.exit_code != 0
    assert "Building for more than one graph is not supported" in r.output

    # -s with a directory is ok
    d = tmp_path / "subs"
    d.mkdir()
    f = d / "x.gfa"
    f.write_text(gfa_rel_path.read_text())

    # monkeypatch GFA.divide to return empty (so run falls back to [('', gfa)])
    gfa = importlib.import_module("hap.lib.gfa")

    monkeypatch.setattr(gfa.GFA, "divide_into_subgraphs", lambda self, outdir, chr_only: [])
    build = importlib.import_module("hap.commands.build")

    monkeypatch.setattr(build, "validate_gfa", lambda *args, **kwargs: ValidationResult(True, ""))
    monkeypatch.setattr(build, "validate_graph", lambda *args, **kwargs: ValidationResult(True, ""))
    monkeypatch.setattr(build, "graph2rstree", lambda g: (types.SimpleNamespace(), types.SimpleNamespace(), {}))
    monkeypatch.setattr(build, "calculate_properties_l2r", lambda *a, **k: a)
    monkeypatch.setattr(build, "wrap_rstree", lambda *a, **k: a)
    monkeypatch.setattr(build, "calculate_properties_r2l", lambda *a, **k: a)
    monkeypatch.setattr(build, "hap2db", lambda hap_info, subgraphs, conn: None)
    monkeypatch.setattr(build, "check_name", lambda name: True)
    monkeypatch.setattr(build, "build_subgraphs_with_sequence_in_parallel", lambda subgraph_items, min_resolution, temp_dir: [(types.SimpleNamespace(), types.SimpleNamespace(), {"sources": [], "name": n}, None) for n, p in subgraph_items])
    db = importlib.import_module("hap.lib.database")

    # define local fake conn for this scope as well
    class _FakeConn:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def cursor(self):
            class _C:
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    return False
                def execute(self, *a, **k):
                    pass
                def executemany(self, *a, **k):
                    pass
                def copy_from(self, *a, **k):
                    pass
                def fetchone(self):
                    return None
                def fetchall(self):
                    return []
            return _C()
        def commit(self):
            pass
        def rollback(self):
            pass
    monkeypatch.setattr(db, "auto_connect", lambda: contextlib.nullcontext(_FakeConn()))

    r = runner.invoke(
        cli,
        [
            "build",
            "run",
            str(d),
            "-s",
            "-n",
            "hap6",
            "-a",
            "clade1",
            "-c",
            "me",
            "-x",
            "desc",
        ],
    )
    assert r.exit_code == 0