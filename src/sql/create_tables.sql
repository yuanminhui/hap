-- Create tables for the Hap database idempotently.

-- Utilities
CREATE TABLE IF NOT EXISTS clade (
  id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  name VARCHAR(50) NOT NULL UNIQUE,
  description TEXT,
  image_url TEXT
);

CREATE TABLE IF NOT EXISTS source (
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
        SELECT 1
        FROM   pg_class c
        JOIN   pg_namespace n ON n.oid = c.relnamespace
        WHERE  c.relname = 'region_coordinate_idx'
        AND    n.nspname = 'public'
    ) THEN
        CREATE INDEX region_coordinate_idx ON region USING GIST (coordinate);
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM   pg_class c
        JOIN   pg_namespace n ON n.oid = c.relnamespace
        WHERE  c.relname = 'region_level_range_idx'
        AND    n.nspname = 'public'
    ) THEN
        CREATE INDEX region_level_range_idx ON region USING GIST (level_range);
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


CREATE TABLE IF NOT EXISTS segment_original_id (
  id BIGINT PRIMARY KEY NOT NULL,
  original_id VARCHAR(30) NOT NULL,
  FOREIGN KEY(id) REFERENCES segment(id) ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS annotation (
  id BIGINT PRIMARY KEY,
  semantic_id VARCHAR(20) NOT NULL UNIQUE,
  level_range INT4RANGE NOT NULL,
  coordinate INT8RANGE NOT NULL,
  type VARCHAR(20) NOT NULL,
  length INT NOT NULL CHECK(length >= 0),
  subgraph_id SMALLINT NOT NULL,
  FOREIGN KEY(subgraph_id) REFERENCES subgraph(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS segment_sequence (
  id BIGINT PRIMARY KEY NOT NULL,
  segment_sequence TEXT,
  FOREIGN KEY(id) REFERENCES segment(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pangenome_source (
  id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  pangenome_id SMALLINT NOT NULL,
  source_id BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS segment_source_coordinate (
  id BIGINT PRIMARY KEY,
  segment_id BIGINT NOT NULL,
  source_id BIGINT NOT NULL,
  coordinate INT8RANGE
);

CREATE TABLE IF NOT EXISTS segment_annotation_coordinate (
  id BIGINT PRIMARY KEY,
  segment_id BIGINT NOT NULL,
  annotation_id BIGINT NOT NULL,
  coordinate INT8RANGE
);