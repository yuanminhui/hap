# HAP Annotation System - User Guide

## Table of Contents

1. [Introduction](#introduction)
2. [Core Concepts](#core-concepts)
3. [Quick Start](#quick-start)
4. [Command Reference](#command-reference)
5. [File Format Guide](#file-format-guide)
6. [Common Workflows](#common-workflows)
7. [Troubleshooting](#troubleshooting)
8. [Advanced Topics](#advanced-topics)

## Introduction

The HAP Annotation System provides comprehensive support for managing genomic annotations in hierarchical pangenomes. It supports multiple standard annotation formats (GFF3, GTF, BED) with automatic coordinate conversion and mapping to pangenome structures.

### Key Features

- **Multi-format support**: Import and export GFF3, GTF, BED formats
- **Automatic coordinate conversion**: 1-based ↔ 0-based coordinate systems
- **Intelligent path mapping**: seqid + genome → unique path resolution
- **Flexible querying**: Filter by type, label, path, subgraph, coordinates
- **Complete CRUD operations**: Add, query, edit, delete, export

## Core Concepts

### 1. Genome and Haplotype

A **genome** represents a sample with one or more haplotypes:

```
Genome: (name, haplotype_index)
Examples:
  - (smp1, 0) = Sample smp1, haplotype 0
  - (HG002, 1) = Sample HG002, haplotype 1
  - (HG002, 2) = Sample HG002, haplotype 2
```

### 2. Path Naming Convention

Paths follow the **PanSN specification**:

```
Format: sample#haplotype#sequence
Examples:
  - smp1#0#1 = sample:smp1, haplotype:0, sequence:1
  - HG002#1#chr1 = sample:HG002, haplotype:1, chromosome:chr1
  - NA12878#0#chr22 = sample:NA12878, haplotype:0, chromosome:22
```

### 3. Coordinate Systems

| Format | Coordinate System | Example Range |
|--------|-------------------|---------------|
| GFF3   | 1-based, inclusive | [1, 100] = positions 1 through 100 |
| GTF    | 1-based, inclusive | [1, 100] = positions 1 through 100 |
| BED    | 0-based, half-open | [0, 100) = positions 0 through 99 |
| HAP Internal | 0-based, half-open | [0, 100) = positions 0 through 99 |

**Note**: HAP automatically converts coordinates during import/export.

### 4. seqid → Path Mapping

Annotation files use **seqid** (chromosome/contig name) which maps to **subgraph.name**:

```
Annotation file:
  seqid = "chr1"

Database mapping:
  subgraph.name = "chr1"
  genome.name = "HG002"
  genome.haplotype_index = 1

Result:
  path.name = "HG002#1#chr1"
```

**Important**: You must specify which genome the annotations belong to!

## Quick Start

### 1. Import Annotations

```bash
# Import with automatic haplotype selection
hap annotation add --file annotations.gff3 --genome-name smp1

# Import with specific haplotype
hap annotation add --file annotations.gff3 --genome-name HG002 --haplotype-index 1

# Import specific subgraph from multi-chromosome file
hap annotation add --file genome_wide.gff3 --genome-name HG002 --haplotype-index 1 --subgraph chr1
```

### 2. Query Annotations

```bash
# Query all genes
hap annotation get --type gene

# Query annotations on specific path
hap annotation get --path "smp1#0#1"

# Query with label pattern
hap annotation get --label "BRCA.*" --type gene

# Query by coordinate range
hap annotation get --range "1000-5000" --path "chr1"
```

### 3. Export Annotations

```bash
# Export to GFF3 (coordinates converted to 1-based)
hap annotation export --path "smp1#0#1" --format gff3 --output output.gff3

# Export to GTF
hap annotation export --path "smp1#0#1" --format gtf --output output.gtf

# Export to BED (coordinates in 0-based)
hap annotation export --path "smp1#0#1" --format bed --output output.bed
```

## Command Reference

### `hap annotation add`

Import annotations from file.

**Syntax**:
```bash
hap annotation add --file <FILE> --genome-name <NAME> [OPTIONS]
```

**Required Arguments**:
- `--file PATH`: Path to annotation file (GFF3/GTF/BED)
- `--genome-name NAME`: Genome/sample name

**Optional Arguments**:
- `--haplotype-index INT`: Haplotype index (0, 1, 2, ...). If not specified, auto-selects first available
- `--format FORMAT`: File format (gff3|gtf|bed). Auto-detected if not specified
- `--subgraph NAME`: Limit import to specific subgraph/chromosome

**Examples**:
```bash
# Basic import
hap annotation add --file genes.gff3 --genome-name smp1

# Explicit haplotype
hap annotation add --file genes.gff3 --genome-name HG002 --haplotype-index 1

# Force format
hap annotation add --file custom.txt --genome-name smp1 --format gff3

# Import only chr1
hap annotation add --file genome.gff3 --genome-name HG002 --haplotype-index 1 --subgraph chr1
```

**Output**:
```
Auto-selected haplotype_index=0 for genome 'smp1'
  Imported 142 annotations: seqid 'chr1' → path 'smp1#0#1' (genome: smp1#0)
Successfully imported 142 annotations
```

### `hap annotation get`

Query annotations with filters.

**Syntax**:
```bash
hap annotation get [OPTIONS]
```

**Filter Options**:
- `--id INT`: Annotation ID (can specify multiple)
- `--type TYPE`: Annotation type (gene, exon, CDS, etc.)
- `--label PATTERN`: Label pattern (supports regex)
- `--path NAME`: Path name filter
- `--subgraph NAME`: Subgraph name filter
- `--segment ID`: Segment ID or semantic_id
- `--range START-END`: Coordinate range (0-based)

**Output Options**:
- `--format FORMAT`: Output format (tsv|gff3|gtf|bed|json). Default: tsv
- `--output FILE`: Output file (default: stdout)

**Examples**:
```bash
# Query all genes
hap annotation get --type gene

# Query specific annotation
hap annotation get --id 123

# Query by label pattern
hap annotation get --label "BRCA.*"

# Query specific path
hap annotation get --path "HG002#1#chr1" --type exon

# Query coordinate range
hap annotation get --range "100000-200000" --path "smp1#0#1"

# Export query results
hap annotation get --type gene --format gff3 --output genes.gff3
```

**Output (TSV)**:
```
id      path            start   end     type    label           strand  score
1       smp1#0#1        4       45      gene    TEST_GENE_1     +       .
9       smp1#0#1        59      85      gene    REV_GENE        -       .
```

### `hap annotation edit`

Edit annotation properties.

**Syntax**:
```bash
hap annotation edit --id <ID> [OPTIONS]
```

**Required Arguments**:
- `--id INT`: Annotation ID to edit

**Optional Arguments**:
- `--label TEXT`: New label
- `--type TYPE`: New type

**Examples**:
```bash
# Update label
hap annotation edit --id 123 --label "BRCA1"

# Update type
hap annotation edit --id 456 --type "pseudogene"

# Update both
hap annotation edit --id 789 --label "TP53" --type "tumor_suppressor"
```

### `hap annotation delete`

Delete annotations.

**Syntax**:
```bash
hap annotation delete [OPTIONS] --confirm
```

**Filter Options**:
- `--id INT`: Annotation ID(s) to delete
- `--label PATTERN`: Delete by label pattern
- `--type TYPE`: Delete by type
- `--path NAME`: Delete from path

**Safety**:
- `--confirm`: Required flag to confirm deletion

**Examples**:
```bash
# Delete specific annotation
hap annotation delete --id 123 --confirm

# Delete by label pattern
hap annotation delete --label "test_.*" --confirm

# Delete all genes from path
hap annotation delete --path "smp1#0#1" --type gene --confirm
```

### `hap annotation export`

Export annotations to file.

**Syntax**:
```bash
hap annotation export --format <FORMAT> --output <FILE> [OPTIONS]
```

**Required Arguments**:
- `--format FORMAT`: Export format (gff3|gtf|bed)
- `--output FILE`: Output file path

**Filter Options**:
- `--path NAME`: Export from specific path
- `--subgraph NAME`: Export from specific subgraph

**Examples**:
```bash
# Export all annotations from path
hap annotation export --path "smp1#0#1" --format gff3 --output smp1.gff3

# Export from subgraph
hap annotation export --subgraph chr1 --format gtf --output chr1.gtf

# Export to BED
hap annotation export --path "HG002#1#chr22" --format bed --output chr22.bed
```

## File Format Guide

### GFF3 Format

```gff3
##gff-version 3
##sequence-region chr1 1 248956422
chr1    HAVANA  gene    11869   14409   .       +       .       ID=ENSG00000223972;Name=DDX11L1
chr1    HAVANA  transcript      11869   14409   .       +       .       ID=ENST00000456328;Parent=ENSG00000223972
chr1    HAVANA  exon    11869   12227   .       +       .       ID=exon1;Parent=ENST00000456328
```

**Key Points**:
- 1-based coordinates (inclusive)
- seqid column = subgraph.name (e.g., "chr1", not "sample#0#chr1")
- Must specify genome during import

### GTF Format

```gtf
chr1    HAVANA  gene    11869   14409   .       +       .       gene_id "DDX11L1"; gene_name "DDX11L1";
chr1    HAVANA  transcript      11869   14409   .       +       .       gene_id "DDX11L1"; transcript_id "DDX11L1.1";
chr1    HAVANA  exon    11869   12227   .       +       .       gene_id "DDX11L1"; transcript_id "DDX11L1.1"; exon_number "1";
```

**Key Points**:
- 1-based coordinates (inclusive)
- Attributes in `key "value";` format
- gene_id and transcript_id required for hierarchical features

### BED Format

```bed
chr1    11868   14409   DDX11L1 .       +       11868   14409   0,128,0 3       359,109,1189    0,744,1451
chr1    15000   20000   REGION1 .       +
```

**Key Points**:
- 0-based, half-open coordinates [start, end)
- Minimum 3 columns: chrom, chromStart, chromEnd
- Optional columns: name, score, strand, thickStart, thickEnd, itemRgb, blockCount, blockSizes, blockStarts

## Common Workflows

### Workflow 1: Import Annotations for a New Genome

**Scenario**: You have a GFF3 file with annotations for sample HG002 haplotype 1.

```bash
# Step 1: Check available genomes
hap query genomes  # Or query database

# Step 2: Import annotations
hap annotation add \
  --file HG002_hap1.gff3 \
  --genome-name HG002 \
  --haplotype-index 1

# Step 3: Verify import
hap annotation get --path "HG002#1#chr1" | head -10
```

### Workflow 2: Export Annotations for External Analysis

**Scenario**: Extract gene annotations from chr1 for downstream analysis.

```bash
# Export all genes from chr1
hap annotation get \
  --subgraph chr1 \
  --type gene \
  --format gff3 \
  --output chr1_genes.gff3

# Or export entire path
hap annotation export \
  --path "smp1#0#1" \
  --format gtf \
  --output smp1_chr1.gtf
```

### Workflow 3: Updating Annotation Labels

**Scenario**: Rename genes after improved annotation.

```bash
# Find annotation ID
hap annotation get --label "gene_12345" --type gene

# Update label
hap annotation edit --id 123 --label "BRCA1"

# Verify update
hap annotation get --id 123
```

### Workflow 4: Multi-Chromosome Import

**Scenario**: Import genome-wide annotations covering multiple chromosomes.

```bash
# Import all chromosomes at once
hap annotation add \
  --file genome_wide.gff3 \
  --genome-name HG002 \
  --haplotype-index 1

# System automatically maps:
# - seqid "chr1" → path "HG002#1#chr1"
# - seqid "chr2" → path "HG002#1#chr2"
# - seqid "chrX" → path "HG002#1#chrX"
```

### Workflow 5: Compare Annotations Across Haplotypes

```bash
# Import haplotype 1
hap annotation add --file HG002_hap1.gff3 --genome-name HG002 --haplotype-index 1

# Import haplotype 2
hap annotation add --file HG002_hap2.gff3 --genome-name HG002 --haplotype-index 2

# Query haplotype 1 genes
hap annotation get --path "HG002#1#chr1" --type gene > hap1_genes.tsv

# Query haplotype 2 genes
hap annotation get --path "HG002#2#chr1" --type gene > hap2_genes.tsv

# Compare externally
diff hap1_genes.tsv hap2_genes.tsv
```

## Troubleshooting

### Error: "Path not found for seqid 'chr1'"

**Full error**:
```
Path not found for seqid 'chr1' with genome 'smp1' haplotype 0.
Available subgraphs for this genome: ['chr2', 'chr3']
```

**Cause**: The seqid in your annotation file doesn't match any subgraph.name for the specified genome.

**Solutions**:
1. Check available subgraphs: See error message for list
2. Verify seqid matches subgraph name in database
3. Check if genome has been built with correct contig names

### Error: "Genome not found: name='HG003', haplotype_index=1"

**Cause**: The specified genome doesn't exist in the database.

**Solutions**:
1. Check genome name spelling
2. List available genomes: Query database or check build output
3. Build pangenome with this genome first

### Warning: "Auto-selected haplotype_index=0"

**This is normal**: When you don't specify `--haplotype-index`, HAP automatically selects the first available haplotype (0, 1, or 2).

**To avoid this**:
```bash
# Explicitly specify haplotype
hap annotation add --file anno.gff3 --genome-name smp1 --haplotype-index 0
```

### Coordinate Mismatch After Export

**Symptom**: Exported coordinates don't match original file.

**Explanation**:
- GFF3/GTF use 1-based coordinates
- HAP internally uses 0-based coordinates
- During import: 1-based → 0-based (start - 1)
- During export: 0-based → 1-based (start + 1)

**This is correct behavior**: Round-trip should preserve coordinates.

**Example**:
```
Original GFF3:  start=1000, end=2000
After import:   start=999,  end=2000  (internal 0-based)
After export:   start=1000, end=2000  (converted back to 1-based)
```

## Advanced Topics

### Custom Annotation Types

HAP supports arbitrary annotation types. Common types include:

- **Genes**: gene, pseudogene, ncRNA_gene
- **Transcripts**: mRNA, transcript, lncRNA, miRNA
- **Exons**: exon, CDS, five_prime_UTR, three_prime_UTR
- **Regulatory**: promoter, enhancer, silencer
- **Repeats**: repeat_region, tandem_repeat

### Programmatic Access

For programmatic access, use JSON output:

```bash
# Get annotations as JSON
hap annotation get --type gene --format json > genes.json

# Process with jq
hap annotation get --type gene --format json | jq '.[] | select(.label == "BRCA1")'
```

### Batch Operations

For batch imports, use shell scripting:

```bash
# Import multiple files
for file in *.gff3; do
    genome=$(basename $file .gff3)
    hap annotation add --file $file --genome-name $genome
done
```

### Database Queries

For complex queries, access the database directly:

```sql
-- Find genes longer than 10kb
SELECT a.id, a.label, (a.coordinate).upper - (a.coordinate).lower as length
FROM annotation a
WHERE a.type = 'gene'
  AND (a.coordinate).upper - (a.coordinate).lower > 10000;

-- Count annotations by type and path
SELECT p.name, a.type, COUNT(*)
FROM annotation a
JOIN path p ON a.path_id = p.id
GROUP BY p.name, a.type;
```

## Best Practices

1. **Always specify genome name**: Use `--genome-name` to avoid ambiguity
2. **Check available genomes first**: Query database before importing
3. **Use consistent naming**: Follow PanSN convention for clarity
4. **Verify imports**: Check annotation counts after import
5. **Backup before delete**: Always verify filters before using `--confirm`
6. **Use explicit coordinates**: When exporting, verify coordinate system expectations

## Support

For issues or questions:
- GitHub: https://github.com/your-repo/hap/issues
- Documentation: See `docs/` directory
- Examples: See `data/mini-example/` for sample files

---

**Version**: 1.0
**Last Updated**: 2025-12-29
