import importlib
import types

import pytest


def test_validate_graph_ok(monkeypatch):
    build = importlib.import_module("hap.commands.build")

    class G:
        is_dag = True
        vs = []
        def is_connected(self, mode="WEAK"):
            return True
    r = build.validate_graph(G())
    assert r.valid is True


def test_validate_graph_not_dag(monkeypatch):
    build = importlib.import_module("hap.commands.build")

    class G:
        is_dag = False
        vs = []
        def is_connected(self, mode="WEAK"):
            return True
    r = build.validate_graph(G())
    assert r.valid is False and "not a DAG" in r.message


def test_validate_graph_not_connected(monkeypatch):
    build = importlib.import_module("hap.commands.build")

    class G:
        is_dag = True
        vs = []
        def is_connected(self, mode="WEAK"):
            return False
    r = build.validate_graph(G())
    assert r.valid is False and "not connected" in r.message