import subprocess
import types
import pytest
from pathlib import Path

from hap.lib import gfa as gfa_mod


def test_ensure_length_completeness_raises(tmp_path):
    f = tmp_path / "miss.gfa"
    f.write_text("H\tVN:Z:1.0\nS\ts1\t*\n")
    # bypass validity checks to reach ensure_length_completeness
    old_is_valid = gfa_mod.GFA.is_valid
    gfa_mod.GFA.is_valid = lambda self: True
    try:
        g = gfa_mod.GFA(str(f))
        with pytest.raises(Exception):
            g.ensure_length_completeness()
    finally:
        gfa_mod.GFA.is_valid = old_is_valid


def test_version_detection_header(tmp_path, monkeypatch):
    f = tmp_path / "v.gfa"
    f.write_text("H\tVN:Z:2.0\nS\ts1\t10\t*\n")
    # bypass validity checks
    monkeypatch.setattr(gfa_mod.GFA, "is_valid", lambda self: True)
    g = gfa_mod.GFA(str(f))
    assert g.version == 2.0

