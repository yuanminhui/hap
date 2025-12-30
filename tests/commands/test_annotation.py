"""Tests for annotation command functionality."""

import tempfile
from pathlib import Path

import pytest

from hap.commands.annotation import (
    BEDParser,
    GFF3Parser,
    GTFParser,
    detect_annotation_format,
)


class TestGFF3Parser:
    """Test GFF3 file parsing."""

    def test_parse_basic_gff3(self):
        """Test parsing a basic GFF3 file with coordinate conversion."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".gff3", delete=False) as f:
            f.write("##gff-version 3\n")
            f.write("chr1\ttest\tgene\t1000\t2000\t.\t+\t.\tID=gene1;Name=TEST\n")
            temp_path = f.name

        try:
            result = GFF3Parser.parse(temp_path)
            assert len(result) == 1
            # Check 1-based → 0-based conversion
            assert result[0]["start"] == 999  # 1000 - 1
            assert result[0]["end"] == 2000
            assert result[0]["attributes"]["ID"] == "gene1"
        finally:
            Path(temp_path).unlink()

    def test_parse_empty_gff3(self):
        """Test parsing empty GFF3 file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".gff3", delete=False) as f:
            f.write("##gff-version 3\n")
            temp_path = f.name

        try:
            result = GFF3Parser.parse(temp_path)
            assert result == []
        finally:
            Path(temp_path).unlink()


class TestGTFParser:
    """Test GTF file parsing."""

    def test_parse_basic_gtf(self):
        """Test parsing a basic GTF file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".gtf", delete=False) as f:
            f.write('chr1\ttest\tgene\t1000\t2000\t.\t+\t.\tgene_id "GENE1"; gene_name "TEST";\n')
            temp_path = f.name

        try:
            result = GTFParser.parse(temp_path)
            assert len(result) == 1
            # Check coordinate conversion
            assert result[0]["start"] == 999  # 1000 - 1
            assert result[0]["end"] == 2000
            assert result[0]["attributes"]["gene_id"] == "GENE1"
        finally:
            Path(temp_path).unlink()


class TestBEDParser:
    """Test BED file parsing."""

    def test_parse_bed3(self):
        """Test parsing BED3 format (chrom, start, end)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bed", delete=False) as f:
            f.write("chr1\t1000\t2000\n")
            temp_path = f.name

        try:
            result = BEDParser.parse(temp_path)
            assert len(result) == 1
            assert result[0]["seqid"] == "chr1"
            assert result[0]["start"] == 1000  # BED is already 0-based
            assert result[0]["end"] == 2000
        finally:
            Path(temp_path).unlink()

    def test_parse_bed6(self):
        """Test parsing BED6 format with name, score, strand."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bed", delete=False) as f:
            f.write("chr1\t1000\t2000\tGENE1\t100\t+\n")
            temp_path = f.name

        try:
            result = BEDParser.parse(temp_path)
            assert result[0]["score"] == 100.0
            assert result[0]["strand"] == "+"
        finally:
            Path(temp_path).unlink()


class TestDetectAnnotationFormat:
    """Test automatic format detection."""

    def test_detect_by_extension(self):
        """Test detection by file extension."""
        assert detect_annotation_format("test.gff3") == "gff3"
        assert detect_annotation_format("test.gtf") == "gtf"
        assert detect_annotation_format("test.bed") == "bed"


class TestCoordinateConversion:
    """Test coordinate system conversions."""

    def test_gff3_to_internal_conversion(self):
        """Test GFF3 1-based inclusive to 0-based half-open."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".gff3", delete=False) as f:
            f.write("##gff-version 3\n")
            f.write("chr1\ttest\tgene\t1\t100\t.\t+\t.\tID=g1\n")
            temp_path = f.name

        try:
            result = GFF3Parser.parse(temp_path)
            assert result[0]["start"] == 0  # 1 - 1
            assert result[0]["end"] == 100
        finally:
            Path(temp_path).unlink()
