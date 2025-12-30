# Annotation Parser Field Mapping Analysis

## 问题概述

当前实现的注释解析器（GFF3Parser, GTFParser, BEDParser）在字段映射和语义理解上存在严重问题。

## 1. 字段映射对比

### 1.1 seqid 字段的含义差异

| 格式 | 原始字段名 | 当前映射 | 实际含义 | 问题 |
|------|-----------|---------|---------|------|
| GFF3 | seqid | seqid | 序列ID（染色体/contig名称） | ✓ 正确 |
| GTF | seqname | seqid | 序列名称（染色体/contig名称） | ✓ 正确 |
| BED | chrom | seqid | 染色体名称 | ✓ 正确 |

**结论**: seqid 字段映射一致，都表示染色体/contig/序列名称。

### 1.2 注释组织级别分析

#### 问题：注释文件是基于什么级别组织的？

查看测试数据文件 `new-mini-example.annotations.gff3`:

```gff3
##gff-version 3
##sequence-region hap1 1 88
##sequence-region hap2 1 86
##sequence-region hap3 1 85
hap1	manual	gene	5	45	.	+	.	ID=gene001;Name=TEST_GENE_1
hap2	manual	gene	10	50	.	+	.	ID=gene003;Name=TEST_GENE_2
hap3	manual	gene	8	40	.	+	.	ID=gene005;Name=TEST_GENE_3
```

**分析**:
1. **seqid 字段** (第1列: hap1, hap2, hap3) 实际是 **路径名称**
2. 注释文件以 **路径** (path) 为组织单位
3. 一个注释文件可以包含多个路径的注释
4. seqid 应该对应到数据库中的 `path.name`

#### 当前实现的错误

在 `import_annotations()` 函数中（annotation.py:566-820）:

```python
def import_annotations(
    connection,
    filepath,
    format_type,
    path_name=None,  # 只接受单个 path_name
    # ...
):
    # 问题1: 只查询单个 path
    query_path = "SELECT id, name, genome_id, subgraph_id FROM path WHERE name = %s"

    # 问题2: 所有注释都被强制导入到同一个 path
    for ann in parsed_annotations:
        # ann["seqid"] 被忽略！
        annotation_records.append({
            "path_id": path_id,  # 使用参数指定的 path_id
            # ...
        })
```

**错误示例**:
```bash
# 用户执行:
hap annotation add --path hap1 --file new-mini-example.annotations.gff3

# 结果: 所有注释（包括 hap2, hap3 的）都被导入到 hap1
# 数据库中:
# - hap2 的 gene003 被错误标记为在 hap1 上
# - hap3 的 gene005 被错误标记为在 hap1 上
```

### 1.3 路径名称 (path.name) 的语义问题

#### 当前实现

根据 `generate_path_coordinates.awk`:
```awk
/^W\t/ {
    sample = $2      # e.g., "hap1"
    hap_index = $3   # e.g., "0"
    seq_name = $4    # e.g., "1" (chromosome)

    # 当前实现: path_name = sample
    path_name = sample  # 结果: "hap1"
}
```

**问题**:
1. `sample` 只是基因组的一部分标识
2. 缺少染色体/subgraph 信息
3. 对于真实数据（如 HG002#1#chr1），无法区分不同染色体

#### 正确的 PanSN 格式

根据 PanSN 规范和真实数据需求:
```
格式: <sample>#<haplotype>#<sequence>
示例: HG002#1#chr1, HG002#2#chr2

组成:
- sample: 基因组/样本名称 (e.g., HG002, hap1)
- haplotype: 单倍型索引 (0, 1, 2, ...)
- sequence: 染色体/contig 名称 (chr1, chr2, ...)
```

**在数据库中**:
- `genome.name` = sample + "#" + haplotype (e.g., "HG002#1", "hap1#0")
- `subgraph.name` = sequence (e.g., "chr1", "1")
- `path.name` = 完整 PanSN (e.g., "HG002#1#chr1", "hap1#0#1")

## 2. 实际测试结果

### 2.1 当前错误的导入结果

```sql
-- 查询实际导入的数据
SELECT a.id, p.name as path, a.label, lower(a.coordinate) as start, upper(a.coordinate) as end
FROM annotation a
JOIN path p ON a.path_id = p.id
WHERE a.type = 'gene';

-- 结果（错误）:
 id | path |    label    | start | end
----+------+-------------+-------+-----
  1 | hap1 | TEST_GENE_1 |     4 |  45  ← 正确
  9 | hap1 | REV_GENE    |    59 |  85  ← 正确
 15 | hap1 | TEST_GENE_2 |     9 |  50  ← 错误！应该在 hap2
 21 | hap1 | SINGLE_EXON |    54 |  80  ← 错误！应该在 hap2
 25 | hap1 | TEST_GENE_3 |     7 |  40  ← 错误！应该在 hap3
 31 | hap1 | HAP3_REV    |    49 |  75  ← 错误！应该在 hap3
```

### 2.2 坐标映射错误

因为 hap1, hap2, hap3 的序列长度不同:
- hap1: 88bp
- hap2: 86bp
- hap3: 85bp

将 hap2/hap3 的注释强制导入 hap1 会导致:
1. 坐标超出范围（可能）
2. 映射到错误的 segment
3. 注释语义完全错误

## 3. 必需的修复方案

### 3.1 修改 path.name 生成逻辑

**文件**: `src/awk/gfa/parse_gfa_paths.awk`, `src/awk/gfa/generate_path_coordinates.awk`

```awk
# 修改 W 行处理
/^W\t/ {
    sample = $2
    hap_index = $3
    seq_name = $4

    # 新实现: 构造完整 PanSN 路径名
    genome_name = sample "#" hap_index
    path_name = sample "#" hap_index "#" seq_name

    # 输出: path_name, genome_name, walk
}
```

### 3.2 修改 import_annotations() 逻辑

**文件**: `src/hap/commands/annotation.py`

#### 方案 A: 使用 seqid 自动匹配路径

```python
def import_annotations(
    connection,
    filepath,
    format_type,
    genome_name=None,    # 可选: 限定基因组
    subgraph_id=None,    # 可选: 限定子图
):
    # 解析文件
    parsed_annotations = parse_file(filepath, format_type)

    # 按 seqid 分组
    by_seqid = {}
    for ann in parsed_annotations:
        seqid = ann["seqid"]
        if seqid not in by_seqid:
            by_seqid[seqid] = []
        by_seqid[seqid].append(ann)

    # 对每个 seqid，查找对应的 path
    for seqid, anns in by_seqid.items():
        # 查找路径: WHERE name = seqid
        # 或根据 genome_name/subgraph_id 过滤
        path_id = find_path_by_name(connection, seqid, genome_name, subgraph_id)

        if not path_id:
            raise Error(f"Path '{seqid}' not found in database")

        # 导入该路径的注释
        import_to_path(connection, path_id, anns)
```

#### 方案 B: 显式指定映射关系

```python
def import_annotations(
    connection,
    filepath,
    format_type,
    path_id=None,           # 选项1: 直接指定 path_id (所有注释导入同一路径)
    genome_subgraph=None,   # 选项2: "genome_name:subgraph_name" (自动匹配 seqid)
):
    if path_id:
        # 单路径导入: 忽略 seqid
        pass
    elif genome_subgraph:
        # 自动匹配: seqid → path.name
        genome, subgraph = genome_subgraph.split(":")
        # 查找所有属于该 genome+subgraph 的 paths
        # 按 seqid 匹配
        pass
```

### 3.3 修改命令行接口

```bash
# 方式1: 使用 path_id (适合单个路径)
hap annotation add --path-id 123 --file anno.gff3

# 方式2: 使用 genome+subgraph (自动匹配多个路径)
hap annotation add --genome hap1#0 --subgraph chr1 --file anno.gff3

# 方式3: 自动从文件中推断（检查所有 seqid）
hap annotation add --file anno.gff3 --auto-match
```

## 4. 其他发现的问题

### 4.1 label 字段提取不一致

- GFF3: 从 attributes["Name"] 或 attributes["ID"] 提取
- GTF: 从 attributes["gene_name"] 或 attributes["transcript_name"] 提取
- BED: 直接使用 name 列

**建议**: 统一优先级规则，并在文档中明确说明。

### 4.2 缺少 seqid 验证

导入时不验证 seqid 是否匹配 path.name，导致数据不一致。

## 5. 总结

当前实现的核心问题:
1. ✗ seqid 字段被忽略，所有注释强制导入到单个 path
2. ✗ path.name 不符合 PanSN 规范，缺少 subgraph 信息
3. ✗ genome.name 包含 level 后缀 (.0, .1)，语义错误
4. ✗ 缺少 seqid → path 的映射验证

必需的修复:
1. ✓ 修改 path.name 为完整 PanSN 格式
2. ✓ 去除 genome.name 的 level 后缀
3. ✓ 实现 seqid → path 的正确映射
4. ✓ 添加导入时的路径验证
