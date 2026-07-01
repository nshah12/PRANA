-- 036_hnsw_embedding_index.sql
-- Replaces ivfflat index with HNSW on employee_master.name_embedding.
-- ivfflat requires periodic REINDEX (blocks table) and degrades in recall as rows grow.
-- HNSW maintains recall quality without reindexing and is the recommended choice at
-- employee counts above 1M.
-- m=16 and ef_construction=64 are standard production defaults for 1536-dim vectors.
-- Both DROP and CREATE run CONCURRENTLY to avoid table locks.

DROP INDEX CONCURRENTLY IF EXISTS idx_emp_embedding;

CREATE INDEX CONCURRENTLY idx_emp_embedding_hnsw
  ON employee_master
  USING hnsw (name_embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
