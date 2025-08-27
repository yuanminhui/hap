import importlib
from pathlib import Path
import types
import pytest


def test_validate_arg_path_from_subgraphs_dir(tmp_path):
    build = importlib.import_module("hap.commands.build")
    # Create a directory with two subgraph files
    d = tmp_path / "subs"; d.mkdir()
    (d / "g.part1.gfa").write_text("H\tVN:Z:1.0\n")
    (d / "g.part2.gfa").write_text("H\tVN:Z:1.0\n")

    ctx = types.SimpleNamespace(params={"from_subgraphs": True})
    val = build.validate_arg_path(ctx, None, (d,))
    assert val == (d,)


def test_validate_arg_path_from_subgraphs_multi_dir_error(tmp_path):
    build = importlib.import_module("hap.commands.build")
    d1 = tmp_path / "d1"; d1.mkdir()
    d2 = tmp_path / "d2"; d2.mkdir()
    ctx = types.SimpleNamespace(params={"from_subgraphs": True})
    with pytest.raises(Exception):
        build.validate_arg_path(ctx, None, (d1, d2))


def test_validate_arg_path_single_graph_error(tmp_path):
    build = importlib.import_module("hap.commands.build")
    g1 = tmp_path / "g1.gfa"; g1.write_text("H\tVN:Z:1.0\n")
    g2 = tmp_path / "g2.gfa"; g2.write_text("H\tVN:Z:1.0\n")
    ctx = types.SimpleNamespace(params={"from_subgraphs": False})
    with pytest.raises(Exception):
        build.validate_arg_path(ctx, None, (g1, g2))


def test_get_name_from_context(tmp_path, monkeypatch):
    build = importlib.import_module("hap.commands.build")
    # subgraphs mode
    d = tmp_path / "subs"; d.mkdir()
    (d / "abc.part1.gfa").write_text("H\tVN:Z:1.0\n")
    (d / "abc.part2.gfa").write_text("H\tVN:Z:1.0\n")
    ctx = types.SimpleNamespace(params={"from_subgraphs": True, "path": (d,)})
    name = build.get_name_from_context(ctx)
    assert name.startswith("abc")
    # single gfa
    g = tmp_path / "hello.gfa"; g.write_text("H\tVN:Z:1.0\n")
    ctx2 = types.SimpleNamespace(params={"from_subgraphs": False, "path": (g,)})
    name2 = build.get_name_from_context(ctx2)
    assert name2 == "hello"


def test_check_name_and_get_username(monkeypatch, tmp_path):
    build = importlib.import_module("hap.commands.build")
    db = importlib.import_module("hap.lib.database")
    # Stub create tables script path
    sql = tmp_path / "create.sql"; sql.write_text("-- noop\n")
    monkeypatch.setattr(db, "SCRIPT_PATH_CREATE_TABLES", str(sql), raising=False)
    # DB stub to simulate no existing name
    class _C:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def cursor(self):
            class C:
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    return False
                def execute(self, *a, **k):
                    pass
                def fetchone(self):
                    return None
            return C()
        def commit(self):
            pass
    monkeypatch.setattr(db, "auto_connect", lambda: _C())
    assert build.check_name("valid_name") is True
    assert build.check_name("") is False
    # get_username via connection info
    monkeypatch.setattr(db, "get_connection_info", lambda: {"user": "uu"})
    assert build.get_username() == "uu"