-- Create tables for the Hap database idempotently.

-- Utilities
CREATE TABLE IF NOT EXISTS clade (
  id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  name VARCHAR(50) NOT NULL UNIQUE,
  description TEXT,
  image_url TEXT
);

CREATE TABLE IF NOT EXISTS genome (
  id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  name VARCHAR(30) NOT NULL UNIQUE,
  description TEXT,
  clade_id INTEGER
);

-- Graphs
CREATE TABLE IF NOT EXISTS pangenome (
  id SMALLINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  name VARCHAR(20) NOT NULL UNIQUE,
  description TEXT,
  clade_id INTEGER,
  creater VARCHAR(50),
  created_at TIMESTAMP DEFAULT NOW(),
  builder VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS subgraph (
  id SMALLINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  name VARCHAR(20) NOT NULL,
  pangenome_id SMALLINT NOT NULL,
  FOREIGN KEY(pangenome_id) REFERENCES pangenome(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS subgraph_statistics (
  id SMALLINT PRIMARY KEY NOT NULL,
  max_level SMALLINT NOT NULL CHECK(max_level >= 0),
  total_length BIGINT NOT NULL CHECK(total_length >= 0),
  total_variants INT NOT NULL CHECK(total_variants >= 0),
  FOREIGN KEY(id) REFERENCES subgraph(id) ON DELETE CASCADE
);

-- Elements
CREATE TABLE IF NOT EXISTS region (
  id BIGINT PRIMARY KEY,
  semantic_id VARCHAR(30) NOT NULL,
  level_range INT4RANGE NOT NULL,
  coordinate INT8RANGE NOT NULL,
  is_default BOOLEAN NOT NULL,
  type VARCHAR(10) NOT NULL,
  total_variants INT NOT NULL CHECK(total_variants >= 0),
  subgraph_id BIGINT NOT NULL,
  parent_segment_id BIGINT,
  FOREIGN KEY(subgraph_id) REFERENCES subgraph(id) ON DELETE CASCADE
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'region_coordinate_idx' AND n.nspname = 'public'
    ) THEN
        CREATE INDEX region_coordinate_idx ON region USING GIST (coordinate);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'region_level_range_idx' AND n.nspname = 'public'
    ) THEN
        CREATE INDEX region_level_range_idx ON region USING GIST (level_range);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'region_subgraph_idx' AND n.nspname = 'public'
    ) THEN
        CREATE INDEX region_subgraph_idx ON region(subgraph_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'region_parent_segment_idx' AND n.nspname = 'public'
    ) THEN
        CREATE INDEX region_parent_segment_idx ON region(parent_segment_id);
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS segment (
  id BIGINT PRIMARY KEY,
  semantic_id VARCHAR(30) NOT NULL,
  level_range INT4RANGE NOT NULL,
  coordinate INT8RANGE NOT NULL,
  rank SMALLINT NOT NULL CHECK(rank >= 0),
  length INT NOT NULL CHECK(length >= 0),
  frequency REAL NOT NULL CHECK(frequency >= 0 AND frequency <= 1),
  direct_variants SMALLINT NOT NULL CHECK(direct_variants >= 0),
  total_variants INT NOT NULL CHECK(total_variants >= 0),
  is_wrapper BOOLEAN NOT NULL,
  region_id BIGINT NOT NULL
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'segment_region_idx' AND n.nspname = 'public'
    ) THEN
        CREATE INDEX segment_region_idx ON segment(region_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'segment_level_range_idx' AND n.nspname = 'public'
    ) THEN
        CREATE INDEX segment_level_range_idx ON segment USING GIST(level_range);
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS segment_original_id (
  id BIGINT PRIMARY KEY NOT NULL,
  original_id VARCHAR(30) NOT NULL,
  FOREIGN KEY(id) REFERENCES segment(id) ON DELETE CASCADE
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'segment_original_id_original_idx' AND n.nspname = 'public'
    ) THEN
        CREATE INDEX segment_original_id_original_idx ON segment_original_id(original_id);
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS segment_sequence (
  id BIGINT PRIMARY KEY NOT NULL,
  segment_sequence TEXT,
  FOREIGN KEY(id) REFERENCES segment(id) ON DELETE CASCADE
);

-- Trigger function: validate and normalize segment_sequence
CREATE OR REPLACE FUNCTION validate_segment_sequence()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.segment_sequence IS NOT NULL THEN
        -- Convert to uppercase
        NEW.segment_sequence := UPPER(NEW.segment_sequence);

        -- Validate characters: only ACGTN-
        IF NEW.segment_sequence !~ '^[ACGTN-]+$' THEN
            RAISE EXCEPTION 'Invalid segment_sequence: must contain only A, C, G, T, N, or - characters';
        END IF;

        -- Validate length matches segment.length
        DECLARE
            expected_length INT;
        BEGIN
            SELECT length INTO expected_length FROM segment WHERE id = NEW.id;
            IF expected_length IS NOT NULL AND LENGTH(NEW.segment_sequence) != expected_length THEN
                RAISE EXCEPTION 'segment_sequence length (%) does not match segment.length (%)',
                    LENGTH(NEW.segment_sequence), expected_length;
            END IF;
        END;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'validate_segment_sequence_trigger'
    ) THEN
        CREATE TRIGGER validate_segment_sequence_trigger
        BEFORE INSERT OR UPDATE ON segment_sequence
        FOR EACH ROW
        EXECUTE FUNCTION validate_segment_sequence();
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS pangenome_genome (
  id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  pangenome_id SMALLINT NOT NULL,
  genome_id BIGINT NOT NULL,
  FOREIGN KEY(pangenome_id) REFERENCES pangenome(id) ON DELETE CASCADE,
  FOREIGN KEY(genome_id) REFERENCES genome(id) ON DELETE CASCADE
);

-- Path: genome paths from GFA W/P lines
CREATE TABLE IF NOT EXISTS path (
  id BIGINT PRIMARY KEY,
  name VARCHAR(50) NOT NULL,
  genome_id INTEGER NOT NULL,
  subgraph_id SMALLINT NOT NULL,
  length BIGINT NOT NULL CHECK(length >= 0),
  FOREIGN KEY(genome_id) REFERENCES genome(id) ON DELETE CASCADE,
  FOREIGN KEY(subgraph_id) REFERENCES subgraph(id) ON DELETE CASCADE,
  UNIQUE(subgraph_id, genome_id, name)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'path_genome_idx' AND n.nspname = 'public'
    ) THEN
        CREATE INDEX path_genome_idx ON path(genome_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'path_subgraph_idx' AND n.nspname = 'public'
    ) THEN
        CREATE INDEX path_subgraph_idx ON path(subgraph_id);
    END IF;
END
$$;

-- Path-segment coordinate mapping
CREATE TABLE IF NOT EXISTS path_segment_coordinate (
  id BIGINT PRIMARY KEY,
  path_id BIGINT NOT NULL,
  segment_id BIGINT NOT NULL,
  coordinate INT8RANGE NOT NULL,
  segment_order SMALLINT NOT NULL CHECK(segment_order >= 0),
  FOREIGN KEY(path_id) REFERENCES path(id) ON DELETE CASCADE,
  FOREIGN KEY(segment_id) REFERENCES segment(id) ON DELETE CASCADE
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'path_seg_coord_path_idx' AND n.nspname = 'public'
    ) THEN
        CREATE INDEX path_seg_coord_path_idx ON path_segment_coordinate(path_id, segment_order);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'path_seg_coord_segment_idx' AND n.nspname = 'public'
    ) THEN
        CREATE INDEX path_seg_coord_segment_idx ON path_segment_coordinate(segment_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'path_seg_coord_coordinate_idx' AND n.nspname = 'public'
    ) THEN
        CREATE INDEX path_seg_coord_coordinate_idx ON path_segment_coordinate USING GIST(coordinate);
    END IF;
END
$$;

-- ============================================================================
-- ANNOTATION SYSTEM
-- ============================================================================

-- Annotation: genomic features on paths
CREATE TABLE IF NOT EXISTS annotation (
  id BIGINT PRIMARY KEY,
  subgraph_id SMALLINT NOT NULL,
  path_id BIGINT,
  coordinate INT8RANGE NOT NULL,
  type VARCHAR(50) NOT NULL,
  label VARCHAR(200),
  strand CHAR(1) CHECK(strand IN ('+', '-', '.')) DEFAULT '.',
  source VARCHAR(100),
  score REAL,
  attributes JSONB,
  genome_id INTEGER NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  FOREIGN KEY(subgraph_id) REFERENCES subgraph(id) ON DELETE CASCADE,
  FOREIGN KEY(path_id) REFERENCES path(id) ON DELETE CASCADE,
  FOREIGN KEY(genome_id) REFERENCES genome(id) ON DELETE CASCADE
);

-- Trigger function: update updated_at timestamp
CREATE OR REPLACE FUNCTION update_annotation_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for annotation
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'update_annotation_timestamp_trigger'
    ) THEN
        CREATE TRIGGER update_annotation_timestamp_trigger
        BEFORE UPDATE ON annotation
        FOR EACH ROW
        EXECUTE FUNCTION update_annotation_timestamp();
    END IF;
END
$$;

DO $$
BEGIN
    -- 复合索引: subgraph + genome + type（核心查询模式）
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'annotation_subgraph_genome_type_idx' AND n.nspname = 'public'
    ) THEN
        CREATE INDEX annotation_subgraph_genome_type_idx ON annotation(subgraph_id, genome_id, type);
    END IF;

    -- JSONB属性查询（GIN索引）
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'annotation_attrs_gin_idx' AND n.nspname = 'public'
    ) THEN
        CREATE INDEX annotation_attrs_gin_idx ON annotation USING GIN(attributes);
    END IF;
END
$$;

-- Gene structure annotations
CREATE TABLE IF NOT EXISTS annotation_gene (
  annotation_id BIGINT PRIMARY KEY,
  feature_kind VARCHAR(20) NOT NULL CHECK(feature_kind IN ('gene', 'transcript', 'exon', 'cds', 'utr5', 'utr3', 'intron')),
  gene_id VARCHAR(100),
  transcript_id VARCHAR(100),
  parent_id BIGINT,
  biotype VARCHAR(50),
  phase SMALLINT CHECK(phase IN (0, 1, 2)),
  FOREIGN KEY(annotation_id) REFERENCES annotation(id) ON DELETE CASCADE,
  FOREIGN KEY(parent_id) REFERENCES annotation(id) ON DELETE CASCADE
);

DO $$
BEGIN
    -- 按gene_id查询（高频：查找基因的所有特征）
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'annotation_gene_gene_id_idx' AND n.nspname = 'public'
    ) THEN
        CREATE INDEX annotation_gene_gene_id_idx ON annotation_gene(gene_id);
    END IF;

    -- 按transcript_id查询（高频：查找转录本的exon/cds）
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'annotation_gene_transcript_id_idx' AND n.nspname = 'public'
    ) THEN
        CREATE INDEX annotation_gene_transcript_id_idx ON annotation_gene(transcript_id);
    END IF;

    -- 按parent_id递归查询（高频：层级关系）
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'annotation_gene_parent_id_idx' AND n.nspname = 'public'
    ) THEN
        CREATE INDEX annotation_gene_parent_id_idx ON annotation_gene(parent_id);
    END IF;

    -- 按feature_kind过滤（中频：统计各层级）
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'annotation_gene_feature_kind_idx' AND n.nspname = 'public'
    ) THEN
        CREATE INDEX annotation_gene_feature_kind_idx ON annotation_gene(feature_kind);
    END IF;
END
$$;

-- Annotation-segment mapping
CREATE TABLE IF NOT EXISTS annotation_span (
  id BIGINT PRIMARY KEY,
  annotation_id BIGINT NOT NULL,
  segment_id BIGINT NOT NULL,
  coordinate INT4RANGE NOT NULL,
  span_order SMALLINT NOT NULL CHECK(span_order >= 0),
  FOREIGN KEY(annotation_id) REFERENCES annotation(id) ON DELETE CASCADE,
  FOREIGN KEY(segment_id) REFERENCES segment(id) ON DELETE CASCADE
);

DO $$
BEGIN
    -- 按segment_id查询annotations（必须）
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'annotation_span_segment_idx' AND n.nspname = 'public'
    ) THEN
        CREATE INDEX annotation_span_segment_idx ON annotation_span(segment_id);
    END IF;
END
$$;
