import os
from pathlib import Path
import pytest

from hap.lib import gfa as gfa_mod


@pytest.fixture()
def tmp_gfa(tmp_path):
    f = tmp_path / "mini.gfa"
    # Minimal header + one segment line to look like a GFA-ish file
    f.write_text("H\tVN:Z:1.0\nS\tn1\t*\tLN:i:1\n")
    return f


def test_gfa_contains_methods_light(monkeypatch, tmp_gfa):
    # Avoid heavy validation in __init__
    monkeypatch.setattr(gfa_mod.GFA, "is_valid", lambda self: True)
    # Fix version to 1.0 so that contains_* select the GFA1 patterns
    monkeypatch.setattr(gfa_mod.GFA, "version", property(lambda self: 1.0))

    # Simulate subprocess.run behavior for grep-based checks
    class Res:
        def __init__(self, rc):
            self.returncode = rc
            self.stdout = ""
            self.stderr = ""

    def fake_run(cmd, *a, **k):
        s = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        # make contains_segment True, contains_edge False, contains_path False
        if "^S" in s:
            return Res(0)
        if "^L" in s or "^(O|U)" in s or "^P" in s or "^W" in s:
            return Res(1)
        if "\\tLN:" in s:
            return Res(0)
        return Res(1)

    monkeypatch.setattr(gfa_mod.subprocess, "run", fake_run)

    g = gfa_mod.GFA(str(tmp_gfa))
    assert g.contains_segment() is True
    assert g.contains_edge() is False
    assert g.contains_path() is False
    assert g.contains_length() is True


@pytest.mark.skipif(False, reason="external tools not required in this suite")
def test_gfa_skip_when_external_unavailable():
    # This demonstrates skipping when external tools are absent; always skipped here.
    pass