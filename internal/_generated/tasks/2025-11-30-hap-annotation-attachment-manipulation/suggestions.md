1. 不是针对不同注释文件格式增加不同数据表，是根据不同注释类型进行特有项的记录，并归纳抽提出不同类型通用项作为annotation表的添加字段。下面为gpt给出的设计方案，供你参考:
---------
一、注释数据项：通用字段与类型特有字段
1) 通用（所有注释共享，覆盖 GFF3/BED/VCF/BigBed/BigWig/…）

id：唯一主键

hap_id / subgraph_id：对应到哪个 HAP/子图（匹配你以 HAP 为可视化/查询基本单位的设计）。

level：该注释建议显示的最小层级（与“分层/缩放级别”一致，用于按尺度裁剪显示）。

track_id：属于哪个可视化 Track（便于前端像 JBrowse2 一样 Track 级别开关/样式/分组）

kind：注释类型（gene/transcript/exon/CDS/UTR/repeat/TE/regulatory/motif/variant/signal/coverage/alignment/custom…）

label：显示名（如 gene symbol、rsID、motif name）

strand：+/-/.

score：通用数值（如 GFF3 的 score、BED 的 score、或可视化排序用）

attrs：JSONB 自由属性（GFF3 的 9 列 attributes、BED 的附加列、VCF INFO/ANN）

定位信息（HAP 体系）：

注释不是“染色体全局坐标”，而是一系列 segment 局部坐标的有序片段：[(segment_id, start, end), ...]（对应“注释跨越多个相邻 segment”的常见情况；这正是 PRD 里“注释映射到 1..n 个 segment 内部线性坐标”的思想）。

可选 path_name/genome_id：当注释本质位于某条来源路径（线性基因组）时保留（有助于线性视图切换）。

created_at / updated_at / source：溯源

2) 类型特有（拆分为扩展表/JSONB）

gene/transcript/exon/CDS/UTR：gene_id/transcript_id/biotype/phase/cds_frame/Parent（GFF3 兼容）

repeat/TE：class/family/subfamily/method（RepeatMasker/EDTA 兼容）

regulatory/motif：tf/name/pwm/score/pval/qval/source_db

alignment（PSL/PAF/BAM 索引外显层）：target_id/identity/mapq/cigar/num_mismatch/clip（前端可选“简图”）

signal/coverage（BigWig/bedGraph）：存为“binned”表：segment_id, start, end, value（见下文 Signal 表）

variant（VCF）：独立扩展表保存：ref, alt, svtype, svlen, qual, filter, info(jsonb), genotypes(jsonb)

这配合“注释主表 + 变体扩展表”的模式，可同时覆盖 SNP/INDEL/SV/CNV/INV/INS/DEL/BND 等
---------

2. 不是要验证path行与segment的关联，是确保build命令输入的gfa中有path行（作一些简单基础的验证即可），并在有注释文件（无论是build时提供还是后续提供annotation命令提供）时验证注释文件中的基因组path名称是否在对应hap中存在，为参与构建图形泛基因组的基因组 

3. 对每个annotation都会在annotation_span表中生成记录，而不是只对multi-segment annotation 

4. annotation是在command目录下，与build等命令相同，而非lib目录；database.py只提供数据库连接的函数，数据表定义在create_tables.sql中 

5. path和annotation类是否必须？如无必要，不需增加。 

6. Annotation中的source项如果指的是注释的提供来源（文献/研究/工具/批次等），则无需重命名，不予待改动的source表冲突 

7. 去除level项的筛选 

8. 现有的id生成是为了预先生成好完整的数据块，一次导入数据库，而无需逐条写入而设计的；如果注释也是批量写入，则应该采取同样的方式。 

9. 直接修改create_tables.sql中的表设计即可，无需drop/create。 

10. Path至少在subraph中唯一，可能在整个泛基因组即hap中唯一。 

11. 需要统一0-based和1-based坐标系为0-based（需要与现有segment坐标系一致） 

12. 对于正常结点，理应具有segement_original_id，只有在build时生成的wrapper segment和deletion segment没有该属性，这两者本就没有注释信息。 