# 路径命名和注释系统完整修复方案

## 已完成的修改

### 1. AWK 脚本修改 ✓

**文件**:
- `src/awk/gfa/parse_gfa_paths.awk`
- `src/awk/gfa/generate_path_coordinates.awk`

**修改内容**:
```awk
# 修改后:
genome_name = sample "#" hap_index     # e.g., "hap1#0"
path_name = sample "#" hap_index "#" seq_name  # e.g., "hap1#0#1"
```

**结果**: 路径名现在符合 PanSN 规范

## 待修改项

### 2. Build.py 中 genome 名称处理

**问题**: `meta["sources"]` 包含 level 后缀 (e.g., "hap1.0")，需要去除

**位置**: `src/hap/commands/build.py:1732-1754`

**修改方案**:
```python
# 在创建 genome 时去除 level 后缀
for genome_name_raw in meta["sources"]:
    # Strip level suffix: "hap1.0" → "hap1#0"
    # Level格式: genome.level (e.g., "HG002#1.0")
    # 提取: genome部分,忽略.level
    if '.' in genome_name_raw:
        base_part, level_str = genome_name_raw.rsplit('.', 1)
        if level_str.isdigit():
            genome_name = base_part
        else:
            genome_name = genome_name_raw
    else:
        genome_name = genome_name_raw

    # Insert/get genome
    cursor.execute("SELECT id FROM genome WHERE name = %s", (genome_name,))
    ...
```

### 3. Annotation Import 修复

**文件**: `src/hap/commands/annotation.py`

**当前问题**:
1. 忽略文件中的 seqid 字段
2. 所有注释导入到单一 path
3. 不支持多路径导入

**修改方案 A: 自动匹配 seqid**

```python
def import_annotations(
    connection,
    filepath,
    format_type,
    genome_name=None,      # 可选: 指定基因组过滤
    subgraph_name=None,    # 可选: 指定子图过滤
    path_id=None,          # 可选: 强制单路径导入(忽略seqid)
):
    """Import annotations with seqid → path_name matching.

    Examples:
        # 自动匹配: seqid → path.name
        import_annotations(conn, "anno.gff3", "gff3")

        # 限定到特定基因组+子图
        import_annotations(conn, "anno.gff3", "gff3",
                          genome_name="hap1#0", subgraph_name="1")

        # 强制单路径导入(用于所有注释属于同一路径的情况)
        import_annotations(conn, "anno.gff3", "gff3", path_id=123)
    """

    # Parse file
    parsed_annotations = parse_annotation_file(filepath, format_type)

    if path_id:
        # 单路径导入: 忽略 seqid
        return import_to_single_path(connection, path_id, parsed_annotations)

    # 按 seqid 分组
    by_seqid = {}
    for ann in parsed_annotations:
        seqid = ann["seqid"]
        by_seqid.setdefault(seqid, []).append(ann)

    # 为每个 seqid 查找对应的 path
    total_imported = 0
    for seqid, anns in by_seqid.items():
        # 查找路径: name = seqid
        query = """
            SELECT p.id, p.name, p.genome_id, p.subgraph_id
            FROM path p
            JOIN genome g ON p.genome_id = g.id
            JOIN subgraph s ON p.subgraph_id = s.id
            WHERE p.name = %s
        """
        params = [seqid]

        # 添加过滤条件
        if genome_name:
            query += " AND g.name = %s"
            params.append(genome_name)
        if subgraph_name:
            query += " AND s.name = %s"
            params.append(subgraph_name)

        with connection.cursor() as cur:
            cur.execute(query, params)
            result = cur.fetchone()

        if not result:
            raise DataInvalidError(
                f"Path '{seqid}' not found in database. "
                f"Available filters: genome='{genome_name}', subgraph='{subgraph_name}'"
            )

        path_id_found, path_name, genome_id, subgraph_id = result

        # 导入该路径的注释
        count = import_to_single_path(connection, path_id_found, anns,
                                      genome_id, subgraph_id)
        total_imported += count

    return total_imported
```

### 4. 命令行接口修改

**文件**: `src/hap/commands/annotation.py`

```python
@annotation.command(name="add")
@click.option("--file", "filepath", type=click.Path(exists=True), required=True)
@click.option("--format", "format_type", type=click.Choice(["gff3", "gtf", "bed"]))
@click.option("--path-id", type=int, help="Import all annotations to this path (ignores seqid)")
@click.option("--genome", type=str, help="Filter paths by genome name (e.g., 'hap1#0')")
@click.option("--subgraph", type=str, help="Filter paths by subgraph name (e.g., 'chr1', '1')")
@click.option("--hap", type=str, help="[DEPRECATED] Use --genome instead")
def add_annotation(filepath, format_type, path_id, genome, subgraph, hap):
    """Import annotations from GFF3/GTF/BED file.

    The command automatically matches annotation seqid to path names in the database.

    Examples:
        # Auto-match seqid → path_name
        hap annotation add --file annotations.gff3

        # Filter by genome and subgraph
        hap annotation add --file annotations.gff3 --genome "hap1#0" --subgraph "1"

        # Force import to single path (ignore seqid)
        hap annotation add --file annotations.gff3 --path-id 123
    """
    # Detect format if not specified
    if not format_type:
        format_type = detect_annotation_format(filepath)
        click.echo(f"Auto-detected format: {format_type}")

    with db.auto_connect() as conn:
        try:
            num_imported = import_annotations(
                connection=conn,
                filepath=filepath,
                format_type=format_type.lower(),
                genome_name=genome or hap,  # Support legacy --hap flag
                subgraph_name=subgraph,
                path_id=path_id,
            )
            click.echo(f"Successfully imported {num_imported} annotations")
        except Exception as e:
            conn.rollback()
            click.echo(f"Error importing annotations: {e}", err=True)
            raise
```

### 5. Query/Get 命令修改

**要求**: 至少指定到 subgraph 级别

```python
@annotation.command(name="get")
@click.option("--id", "ann_ids", type=int, multiple=True)
@click.option("--label", type=str, help="Filter by label pattern (regex)")
@click.option("--type", "ann_type", type=str, help="Filter by type (e.g., 'gene', 'exon')")
@click.option("--path", type=str, help="Filter by path name")
@click.option("--genome", type=str, help="Filter by genome name")
@click.option("--subgraph", type=str, help="Filter by subgraph name (REQUIRED if no path specified)")
@click.option("--range", type=str, help="Filter by coordinate range (e.g., '1000-5000')")
@click.option("--format", "output_format", type=click.Choice(["tsv", "gff3", "gtf", "bed", "json"]), default="tsv")
@click.option("--output", type=click.Path(), help="Output file (default: stdout)")
def get_annotation(...):
    """Query annotations with filters.

    IMPORTANT: Must specify at least one of: --id, --path, --subgraph

    Examples:
        # Get by ID
        hap annotation get --id 123

        # Get all genes in a subgraph
        hap annotation get --subgraph chr1 --type gene

        # Get specific path's annotations
        hap annotation get --path "hap1#0#chr1" --type exon
    """
    # Validate: must have at least one filter
    if not any([ann_ids, path, genome, subgraph]):
        click.echo("Error: Must specify at least one filter: --id, --path, --genome, or --subgraph", err=True)
        return

    # Rest of implementation...
```

### 6. Edit 命令增强

```python
@annotation.command(name="edit")
@click.option("--id", "ann_id", type=int, help="Annotation ID to edit")
@click.option("--label", "label_pattern", type=str, help="Find annotation by label pattern (requires --path or --subgraph)")
@click.option("--path", type=str, help="Limit search to this path (for --label)")
@click.option("--subgraph", type=str, help="Limit search to this subgraph (for --label)")
@click.option("--set-label", type=str, help="New label value")
@click.option("--set-type", type=str, help="New type value")
@click.option("--set-strand", type=click.Choice(["+", "-", "."]), help="New strand value")
@click.option("--set-score", type=float, help="New score value")
@click.option("--set-source", type=str, help="New source value")
def edit_annotation(ann_id, label_pattern, path, subgraph,
                   set_label, set_type, set_strand, set_score, set_source):
    """Edit annotation properties.

    Can find annotation by:
    - ID: --id 123
    - Label: --label "GENE.*" --path "hap1#0#chr1"

    Examples:
        # Edit by ID
        hap annotation edit --id 123 --set-label "BRCA1"

        # Find by label and edit
        hap annotation edit --label "TEST_GENE" --path "hap1#0#1" --set-type "pseudogene"
    """
    if not ann_id and not label_pattern:
        click.echo("Error: Must specify --id or --label", err=True)
        return

    if label_pattern and not (path or subgraph):
        click.echo("Error: --label requires --path or --subgraph to ensure uniqueness", err=True)
        return

    # Find annotation(s)
    with db.auto_connect() as conn:
        if ann_id:
            annotations = [{"id": ann_id}]
        else:
            # Search by label
            filters = {"label": label_pattern}
            if path:
                filters["path"] = path
            if subgraph:
                filters["subgraph"] = subgraph
            annotations = query_annotations(conn, filters)

        if not annotations:
            click.echo("No annotations found", err=True)
            return

        if len(annotations) > 1:
            click.echo(f"Found {len(annotations)} annotations. Please be more specific.", err=True)
            for ann in annotations[:5]:
                click.echo(f"  ID {ann['id']}: {ann['label']} on {ann['path_name']}")
            return

        # Build UPDATE query
        updates = []
        params = []
        if set_label:
            updates.append("label = %s")
            params.append(set_label)
        if set_type:
            updates.append("type = %s")
            params.append(set_type)
        if set_strand:
            updates.append("strand = %s")
            params.append(set_strand)
        if set_score is not None:
            updates.append("score = %s")
            params.append(set_score)
        if set_source:
            updates.append("source = %s")
            params.append(set_source)

        if not updates:
            click.echo("No fields to update specified", err=True)
            return

        params.append(annotations[0]["id"])
        query = f"UPDATE annotation SET {', '.join(updates)}, updated_at = NOW() WHERE id = %s;"

        with conn.cursor() as cur:
            cur.execute(query, params)
        conn.commit()

        click.echo(f"Successfully updated annotation {annotations[0]['id']}")
```

## 总结

### 修改的文件列表

1. ✓ `src/awk/gfa/parse_gfa_paths.awk` - 路径命名修复
2. ✓ `src/awk/gfa/generate_path_coordinates.awk` - 路径命名修复
3. ⏳ `src/hap/commands/build.py` - genome 名称去除 level 后缀
4. ⏳ `src/hap/commands/annotation.py` - 完整重构 import/query/edit 命令

### 核心变更

| 项目 | 修改前 | 修改后 | 状态 |
|------|--------|--------|------|
| path.name | "hap1" | "hap1#0#1" | ✓ |
| genome.name | "hap1.0" (含level) | "hap1#0" (PanSN) | ⏳ |
| seqid处理 | 忽略 | 自动匹配 path.name | ⏳ |
| import命令 | --path (单一) | --genome/--subgraph/--path-id | ⏳ |
| edit命令 | --id only | --id or --label + scope | ⏳ |
| query命令 | 可选subgraph | 必需subgraph | ⏳ |

### 兼容性影响

**重要**: 这些修改会破坏现有数据库中的路径名称格式

**迁移步骤**:
1. 备份现有数据库
2. 删除所有 pangenome 记录
3. 使用新代码重新构建
4. 重新导入注释
