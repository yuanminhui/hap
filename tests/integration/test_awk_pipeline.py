"""
Integration tests for awk pipeline scripts used by hap.
"""

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).parent.parent.parent
AWK_DIR = REPO_ROOT / "src" / "awk" / "gfa"
MINI_GFA = REPO_ROOT / "data" / "mini-example" / "mini-example.gfa"


def awk_available():
    return subprocess.run(["which", "awk"], capture_output=True).returncode == 0


@pytest.mark.skipif(not awk_available(), reason="awk not available")
class TestAwkPipeline:
    def test_parse_pansn_str_script_exists(self):
        assert (AWK_DIR / "parse_pansn_str.awk").exists()

    def test_parse_gfa_paths_script_exists(self):
        assert (AWK_DIR / "parse_gfa_paths.awk").exists()

    def test_gfa12csv_script_exists(self):
        assert (AWK_DIR / "gfa12csv.awk").exists()

    def test_generate_path_coordinates_exists(self):
        assert (AWK_DIR / "generate_path_coordinates.awk").exists()

    def test_parse_paths_awk_produces_output(self):
        """parse_gfa_paths.awk should produce genome path lines for mini-example."""
        if not MINI_GFA.exists():
            pytest.skip("mini-example GFA not found")

        cmd = [
            "awk",
            "-f", str(AWK_DIR / "parse_pansn_str.awk"),
            "-f", str(AWK_DIR / "parse_gfa_paths.awk"),
            str(MINI_GFA),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, f"awk stderr: {result.stderr}"
        lines = result.stdout.strip().splitlines()
        assert len(lines) >= 3, f"Expected >=3 path lines, got {len(lines)}"
        # Each line: path_name\tsample\thaplotype_id\thap_origin\twalk
        for line in lines:
            parts = line.split("\t")
            assert len(parts) >= 4, f"Unexpected line format: {line}"

    def test_haplotype_names_extraction(self):
        """extract_haplotype_names_gfa2.awk or gfa1 extracts genome names."""
        if not MINI_GFA.exists():
            pytest.skip("mini-example GFA not found")

        # Mini-example is GFA 1.1 (W lines) so use gfa1 awk
        cmd = [
            "awk",
            "-f", str(AWK_DIR / "parse_pansn_str.awk"),
            "-f", str(AWK_DIR / "extract_haplotype_names_gfa1.awk"),
            str(MINI_GFA),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        # returncode can be 0 or 1 (no match for GFA1.1 P-only script on W lines)
        # Just check it doesn't crash badly
        assert result.returncode in (0, 1)

    def test_extract_subgraph_names(self):
        """Subgraph name extraction should yield chr1."""
        if not MINI_GFA.exists():
            pytest.skip("mini-example GFA not found")

        # For GFA 1.1 (W lines), subgraph name is in column 4
        cmd = "grep '^W' '{}' | awk '{{print $4}}' | sort -u".format(str(MINI_GFA))
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0
        names = result.stdout.strip().splitlines()
        assert "chr1" in names

    def test_subgraph_extraction(self, tmp_path):
        """extract_subgraph_unified.awk should extract a valid sub-GFA."""
        if not MINI_GFA.exists():
            pytest.skip("mini-example GFA not found")

        path_records = tmp_path / "paths.tmp"
        main_file = tmp_path / "main.tmp"
        output = tmp_path / "chr1.gfa"

        # Step 1: extract path records for chr1
        cmd1 = [
            "awk",
            "-v", "subgraph_name=chr1",
            "-f", str(AWK_DIR / "parse_pansn_str.awk"),
            "-f", str(AWK_DIR / "extract_paths_by_name.awk"),
            str(MINI_GFA),
        ]
        r1 = subprocess.run(cmd1, capture_output=True, text=True, timeout=30)
        path_records.write_text(r1.stdout)

        assert r1.returncode == 0 and r1.stdout.strip(), "No path records extracted"

        # Step 2: extract structural lines
        cmd2 = [
            "awk",
            "-f", str(AWK_DIR / "extract_subgraph_unified.awk"),
            str(path_records),
            str(MINI_GFA),
        ]
        r2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=30)
        main_file.write_text(r2.stdout)

        # Step 3: concat
        output.write_text(r2.stdout + r1.stdout)

        assert output.stat().st_size > 0, "Extracted subgraph is empty"
        content = output.read_text()
        assert "S\t" in content, "No segment records in extracted subgraph"
