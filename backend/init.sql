-- RAG Database Schema
-- Creates tables for document tracking, chunking, and vector embeddings

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Documents table: tracks ingested files
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    sha256 VARCHAR(64) NOT NULL,
    ingested_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    file_size BIGINT,
    last_modified TIMESTAMP WITH TIME ZONE
);

-- Create index on path for faster lookups
CREATE INDEX IF NOT EXISTS idx_documents_path ON documents(path);
CREATE INDEX IF NOT EXISTS idx_documents_sha256 ON documents(sha256);

-- Chunks table: text chunks from documents
CREATE TABLE IF NOT EXISTS chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER,
    char_count INTEGER,
    headings TEXT[] DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    -- Ensure unique chunk index per document
    UNIQUE(document_id, chunk_index)
);

-- Full-text search vector column
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS content_tsv TSVECTOR;

-- Auto-populate tsvector on insert/update
CREATE OR REPLACE FUNCTION chunks_tsv_trigger() RETURNS trigger AS $$
BEGIN
  NEW.content_tsv := to_tsvector('english', COALESCE(NEW.content, ''));
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_chunks_tsv ON chunks;
CREATE TRIGGER trg_chunks_tsv BEFORE INSERT OR UPDATE OF content ON chunks
  FOR EACH ROW EXECUTE FUNCTION chunks_tsv_trigger();

-- Backfill existing rows
UPDATE chunks SET content_tsv = to_tsvector('english', COALESCE(content, ''))
  WHERE content_tsv IS NULL;

-- Create indexes for chunk lookups
CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_chunk_index ON chunks(chunk_index);
CREATE INDEX IF NOT EXISTS idx_chunks_content_tsv ON chunks USING GIN(content_tsv);

-- Embeddings table: vector embeddings for chunks
-- Using vector(1536) for text-embedding-3-small
-- Using vector(3072) for text-embedding-3-large (configurable)
CREATE TABLE IF NOT EXISTS embeddings (
    id SERIAL PRIMARY KEY,
    chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    embedding VECTOR(1536) NOT NULL,
    model VARCHAR(100) NOT NULL DEFAULT 'text-embedding-3-small',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    -- One embedding per chunk
    UNIQUE(chunk_id)
);

-- Create IVFFlat index for cosine similarity search
-- IVFFlat is good for approximate nearest neighbor search with cosine distance
-- Lists should be roughly sqrt of expected row count (adjust as needed)
CREATE INDEX IF NOT EXISTS idx_embeddings_cosine 
ON embeddings 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Alternative: HNSW index for better recall at cost of build time
-- Uncomment if you prefer HNSW over IVFFlat
-- CREATE INDEX IF NOT EXISTS idx_embeddings_hnsw 
-- ON embeddings 
-- USING hnsw (embedding vector_cosine_ops)
-- WITH (m = 16, ef_construction = 64);

-- Create index for model filtering
CREATE INDEX IF NOT EXISTS idx_embeddings_model ON embeddings(model);

-- View for convenient retrieval of full chunk + embedding + document info
CREATE OR REPLACE VIEW rag_chunks AS
SELECT
    c.id AS chunk_id,
    c.content,
    c.chunk_index,
    c.token_count,
    c.headings,
    d.id AS document_id,
    d.path AS document_path,
    d.sha256 AS document_hash,
    d.metadata AS document_metadata,
    e.embedding,
    e.model AS embedding_model
FROM chunks c
JOIN documents d ON c.document_id = d.id
JOIN embeddings e ON e.chunk_id = c.id;

-- Function for cosine similarity search
CREATE OR REPLACE FUNCTION search_similar_chunks(
    query_embedding VECTOR(1536),
    match_threshold FLOAT DEFAULT 0.0,
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    chunk_id INTEGER,
    content TEXT,
    document_path TEXT,
    similarity FLOAT,
    headings TEXT[]
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id AS chunk_id,
        c.content,
        d.path AS document_path,
        1 - (e.embedding <=> query_embedding) AS similarity,
        c.headings
    FROM embeddings e
    JOIN chunks c ON c.id = e.chunk_id
    JOIN documents d ON d.id = c.document_id
    WHERE 1 - (e.embedding <=> query_embedding) > match_threshold
    ORDER BY e.embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- Images extracted from documents
CREATE TABLE IF NOT EXISTS images (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,              -- relative to /images mount
    file_size BIGINT,
    mime_type VARCHAR(50) DEFAULT 'image/png',
    width INTEGER,
    height INTEGER,
    page_number INTEGER,
    bbox_left FLOAT, bbox_top FLOAT, bbox_right FLOAT, bbox_bottom FLOAT,
    bbox_coord_origin VARCHAR(50),
    caption TEXT,
    label VARCHAR(100),
    image_index INTEGER NOT NULL,
    phash VARCHAR(64) NOT NULL,           -- perceptual hash for cross-doc dedup
    sha256 VARCHAR(64) NOT NULL,          -- exact bytes hash
    extracted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    UNIQUE(document_id, image_index)
);

-- Image indexes
CREATE INDEX IF NOT EXISTS idx_images_document_id ON images(document_id);
CREATE INDEX IF NOT EXISTS idx_images_phash ON images(phash);
CREATE INDEX IF NOT EXISTS idx_images_sha256 ON images(sha256);

-- Chunk-image relationships (many-to-many)
CREATE TABLE IF NOT EXISTS chunk_images (
    id SERIAL PRIMARY KEY,
    chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    relationship_type VARCHAR(50) NOT NULL DEFAULT 'same_page',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(chunk_id, image_id)
);

CREATE INDEX IF NOT EXISTS idx_chunk_images_chunk_id ON chunk_images(chunk_id);
CREATE INDEX IF NOT EXISTS idx_chunk_images_image_id ON chunk_images(image_id);

-- Cross-document duplicate finder
CREATE OR REPLACE VIEW image_duplicates AS
SELECT i.phash, i.id AS image_id, i.document_id, d.path AS document_path,
       i.page_number, i.file_path, i.caption,
       COUNT(*) OVER (PARTITION BY i.phash) AS occurrence_count
FROM images i JOIN documents d ON d.id = i.document_id
WHERE i.phash IN (SELECT phash FROM images GROUP BY phash HAVING COUNT(*) > 1)
ORDER BY i.phash, d.path;

-- Pages table: page-level metadata from document layout analysis
CREATE TABLE IF NOT EXISTS pages (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    width FLOAT NOT NULL,
    height FLOAT NOT NULL,
    element_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(document_id, page_number)
);
CREATE INDEX IF NOT EXISTS idx_pages_document_id ON pages(document_id);

-- Layout elements table: every detected element with spatial data
CREATE TABLE IF NOT EXISTS layout_elements (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_id INTEGER REFERENCES pages(id) ON DELETE CASCADE,
    self_ref VARCHAR(100) NOT NULL,
    element_type VARCHAR(50) NOT NULL,
    content_layer VARCHAR(20) NOT NULL DEFAULT 'body',
    reading_order INTEGER NOT NULL,
    page_number INTEGER,
    bbox_left FLOAT, bbox_top FLOAT, bbox_right FLOAT, bbox_bottom FLOAT,
    bbox_coord_origin VARCHAR(50),
    text_preview TEXT,
    full_text TEXT,
    heading_level INTEGER,
    parent_ref VARCHAR(100),
    group_label VARCHAR(50),
    children_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    UNIQUE(document_id, self_ref)
);
CREATE INDEX IF NOT EXISTS idx_layout_elements_document_id ON layout_elements(document_id);
CREATE INDEX IF NOT EXISTS idx_layout_elements_page_id ON layout_elements(page_id);
CREATE INDEX IF NOT EXISTS idx_layout_elements_element_type ON layout_elements(element_type);
CREATE INDEX IF NOT EXISTS idx_layout_elements_page_number ON layout_elements(page_number);
CREATE INDEX IF NOT EXISTS idx_layout_elements_doc_eltype_reading_order
    ON layout_elements(document_id, element_type, reading_order);

-- Chunk-element junction: links chunks to their source layout elements
CREATE TABLE IF NOT EXISTS chunk_elements (
    id SERIAL PRIMARY KEY,
    chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    element_id INTEGER NOT NULL REFERENCES layout_elements(id) ON DELETE CASCADE,
    UNIQUE(chunk_id, element_id)
);
CREATE INDEX IF NOT EXISTS idx_chunk_elements_chunk_id ON chunk_elements(chunk_id);
CREATE INDEX IF NOT EXISTS idx_chunk_elements_element_id ON chunk_elements(element_id);

-- View: per-page element type distribution
CREATE OR REPLACE VIEW page_layout_summary AS
SELECT
    p.id AS page_id,
    p.document_id,
    d.path AS document_path,
    p.page_number,
    p.width,
    p.height,
    p.element_count,
    COUNT(le.id) FILTER (WHERE le.element_type = 'text') AS text_count,
    COUNT(le.id) FILTER (WHERE le.element_type = 'section_header') AS header_count,
    COUNT(le.id) FILTER (WHERE le.element_type = 'picture') AS picture_count,
    COUNT(le.id) FILTER (WHERE le.element_type = 'table') AS table_count,
    COUNT(le.id) FILTER (WHERE le.element_type = 'code') AS code_count,
    COUNT(le.id) FILTER (WHERE le.element_type = 'list_item') AS list_item_count,
    COUNT(le.id) FILTER (WHERE le.element_type = 'caption') AS caption_count,
    COUNT(le.id) FILTER (WHERE le.content_layer = 'furniture') AS furniture_count
FROM pages p
JOIN documents d ON d.id = p.document_id
LEFT JOIN layout_elements le ON le.page_id = p.id
GROUP BY p.id, p.document_id, d.path, p.page_number, p.width, p.height, p.element_count
ORDER BY p.document_id, p.page_number;

-- View: section heading hierarchy (table of contents)
CREATE OR REPLACE VIEW document_structure AS
SELECT
    le.document_id,
    d.path AS document_path,
    le.reading_order,
    le.page_number,
    le.heading_level,
    le.text_preview AS heading_text,
    le.self_ref
FROM layout_elements le
JOIN documents d ON d.id = le.document_id
WHERE le.element_type = 'section_header'
ORDER BY le.document_id, le.reading_order;

-- Comment on tables for documentation
COMMENT ON TABLE documents IS 'Tracks ingested files with SHA256 hash for change detection';
COMMENT ON TABLE chunks IS 'Text chunks from documents with token counts';
COMMENT ON TABLE embeddings IS 'Vector embeddings for chunks using pgvector';
COMMENT ON VIEW rag_chunks IS 'Convenience view joining chunks, documents, and embeddings';
COMMENT ON TABLE images IS 'Images extracted from documents with perceptual hashes for dedup';
COMMENT ON TABLE chunk_images IS 'Many-to-many relationships between chunks and nearby images';

-- Tables extracted from documents
CREATE TABLE IF NOT EXISTS tables (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    table_index INTEGER NOT NULL,
    num_rows INTEGER NOT NULL,
    num_cols INTEGER NOT NULL,
    page_number INTEGER,
    bbox_left FLOAT, bbox_top FLOAT, bbox_right FLOAT, bbox_bottom FLOAT,
    bbox_coord_origin VARCHAR(50),
    caption TEXT,
    label VARCHAR(100),
    content_markdown TEXT NOT NULL,
    content_html TEXT,
    content_text TEXT,
    sha256 VARCHAR(64) NOT NULL,
    extracted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    UNIQUE(document_id, table_index)
);

CREATE INDEX IF NOT EXISTS idx_tables_document_id ON tables(document_id);
CREATE INDEX IF NOT EXISTS idx_tables_sha256 ON tables(sha256);
CREATE INDEX IF NOT EXISTS idx_tables_page_table ON tables(page_number, table_index);

-- Chunk-table relationships (many-to-many)
CREATE TABLE IF NOT EXISTS chunk_tables (
    id SERIAL PRIMARY KEY,
    chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    table_id INTEGER NOT NULL REFERENCES tables(id) ON DELETE CASCADE,
    relationship_type VARCHAR(50) NOT NULL DEFAULT 'same_page',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(chunk_id, table_id)
);

CREATE INDEX IF NOT EXISTS idx_chunk_tables_chunk_id ON chunk_tables(chunk_id);
CREATE INDEX IF NOT EXISTS idx_chunk_tables_table_id ON chunk_tables(table_id);

-- Cross-document table duplicate finder
CREATE OR REPLACE VIEW table_duplicates AS
WITH duplicate_hashes AS (
    SELECT sha256
    FROM tables
    GROUP BY sha256
    HAVING COUNT(*) > 1
)
SELECT t.sha256, t.id AS table_id, t.document_id, d.path AS document_path,
       t.page_number, t.num_rows, t.num_cols, t.caption,
       COUNT(*) OVER (PARTITION BY t.sha256) AS occurrence_count
FROM tables t
JOIN documents d ON d.id = t.document_id
JOIN duplicate_hashes dh ON dh.sha256 = t.sha256;

COMMENT ON TABLE tables IS 'Tables extracted from documents with structured content and hashes for dedup';
COMMENT ON TABLE chunk_tables IS 'Many-to-many relationships between chunks and nearby tables';

-- Individual cells from extracted tables
CREATE TABLE IF NOT EXISTS table_cells (
    id SERIAL PRIMARY KEY,
    table_id INTEGER NOT NULL REFERENCES tables(id) ON DELETE CASCADE,
    row_idx INTEGER NOT NULL,
    col_idx INTEGER NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    row_span INTEGER NOT NULL DEFAULT 1,
    col_span INTEGER NOT NULL DEFAULT 1,
    is_column_header BOOLEAN NOT NULL DEFAULT FALSE,
    is_row_header BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(table_id, row_idx, col_idx)
);

CREATE INDEX IF NOT EXISTS idx_table_cells_table_id ON table_cells(table_id);

COMMENT ON TABLE table_cells IS 'Individual cells from extracted tables with position, span, and header info';
COMMENT ON TABLE pages IS 'Page-level metadata from Docling layout analysis';
COMMENT ON TABLE layout_elements IS 'Every detected document element with spatial data and reading order';
COMMENT ON TABLE chunk_elements IS 'Junction table linking chunks to their source layout elements';
COMMENT ON VIEW page_layout_summary IS 'Per-page element type distribution for layout overview';
COMMENT ON VIEW document_structure IS 'Section heading hierarchy for document navigation';

-- ─── Multi-Index Support ───────────────────────────────────────

-- Indexes table: logical namespaces for document collections
CREATE TABLE IF NOT EXISTS indexes (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Seed the default index (idempotent)
INSERT INTO indexes (slug, display_name, description) VALUES
    ('default', 'Default', 'Documents ingested before multi-index support')
ON CONFLICT (slug) DO NOTHING;

-- Add index_id foreign key to documents
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'documents' AND column_name = 'index_id'
    ) THEN
        ALTER TABLE documents ADD COLUMN index_id INTEGER REFERENCES indexes(id);
        UPDATE documents SET index_id = (SELECT id FROM indexes WHERE slug = 'default')
            WHERE index_id IS NULL;
        ALTER TABLE documents ALTER COLUMN index_id SET NOT NULL;
    END IF;
END $$;

-- Update unique constraint: path unique per index (not globally)
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_path_key;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'documents_index_path_unique'
    ) THEN
        ALTER TABLE documents ADD CONSTRAINT documents_index_path_unique
            UNIQUE (index_id, path);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_documents_index_id ON documents(index_id);

COMMENT ON TABLE indexes IS 'Logical namespaces for organizing documents into separate collections';

-- ─── Ingestion Jobs (pipeline status tracking) ─────────────────

CREATE TABLE IF NOT EXISTS ingestion_jobs (
  id            SERIAL PRIMARY KEY,
  filename      VARCHAR(500) NOT NULL,
  index_slug    VARCHAR(100) NOT NULL DEFAULT 'default',
  status        VARCHAR(50)  NOT NULL DEFAULT 'queued',
  progress      JSONB        NOT NULL DEFAULT '{}',
  document_id   INTEGER,
  error_message TEXT,
  created_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
  started_at    TIMESTAMP,
  updated_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
  completed_at  TIMESTAMP
);

-- Partial index: only index active jobs for fast polling queries
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_active
  ON ingestion_jobs (status) WHERE status NOT IN ('completed', 'failed');

-- Index for cleanup queries on completed_at
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_completed_at
  ON ingestion_jobs (completed_at) WHERE completed_at IS NOT NULL;

COMMENT ON TABLE ingestion_jobs IS 'Pipeline status tracking for document ingestion jobs';

-- ─── Pipeline Config (enrichment toggles) ───────────────────────

CREATE TABLE IF NOT EXISTS pipeline_config (
  key VARCHAR(100) PRIMARY KEY,
  value VARCHAR(100) NOT NULL,
  label VARCHAR(200) NOT NULL,
  description TEXT,
  updated_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO pipeline_config (key, value, label, description) VALUES
  ('enable_code_enrichment', 'true', 'Code Enrichment',
   'Classifies code blocks by language (50+ languages) using Granite-Docling-258M VLM. Moderate GPU/CPU cost.'),
  ('enable_formula_enrichment', 'true', 'Formula Enrichment',
   'Extracts LaTeX from visual equations using Granite-Docling-258M VLM. Moderate GPU/CPU cost.'),
  ('enable_picture_description', 'false', 'Picture Description',
   'Generates natural-language descriptions of images using SmolVLM-256M. High GPU/CPU cost — slow on CPU-only hardware.'),
  ('enable_picture_classification', 'false', 'Picture Classification',
   'Classifies images (chart, photo, diagram, etc.) using DocumentFigureClassifier. Moderate GPU/CPU cost.')
ON CONFLICT (key) DO NOTHING;

COMMENT ON TABLE pipeline_config IS 'Pipeline enrichment toggles readable by frontend control panel';

-- ============================================================
-- LLM-Wiki: entity graph + generated wiki pages (per index)
-- ============================================================

CREATE TABLE IF NOT EXISTS wiki_jobs (
  id            SERIAL PRIMARY KEY,
  index_id      INTEGER NOT NULL REFERENCES indexes(id) ON DELETE CASCADE,
  status        VARCHAR(50)  NOT NULL DEFAULT 'queued',
  progress      JSONB        NOT NULL DEFAULT '{}',
  error_message TEXT,
  created_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
  started_at    TIMESTAMP,
  updated_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
  completed_at  TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_wiki_jobs_active
  ON wiki_jobs (status) WHERE status NOT IN ('completed', 'failed');

CREATE TABLE IF NOT EXISTS wiki_entities (
  id              SERIAL PRIMARY KEY,
  index_id        INTEGER NOT NULL REFERENCES indexes(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  type            VARCHAR(50) NOT NULL DEFAULT 'other',
  description     TEXT,
  embedding       VECTOR(1536),
  mention_count   INTEGER NOT NULL DEFAULT 0,
  metadata        JSONB NOT NULL DEFAULT '{}',
  UNIQUE (index_id, normalized_name)
);

CREATE TABLE IF NOT EXISTS wiki_relationships (
  id                SERIAL PRIMARY KEY,
  index_id          INTEGER NOT NULL REFERENCES indexes(id) ON DELETE CASCADE,
  subject_entity_id INTEGER NOT NULL REFERENCES wiki_entities(id) ON DELETE CASCADE,
  predicate         TEXT NOT NULL,
  object_entity_id  INTEGER NOT NULL REFERENCES wiki_entities(id) ON DELETE CASCADE,
  description       TEXT,
  -- denormalized chunk provenance for this specific relationship (entity-level provenance lives in entity_chunks)
  chunk_refs        INTEGER[] NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS entity_chunks (
  entity_id INTEGER NOT NULL REFERENCES wiki_entities(id) ON DELETE CASCADE,
  chunk_id  INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  PRIMARY KEY (entity_id, chunk_id)
);

CREATE TABLE IF NOT EXISTS wiki_pages (
  id          SERIAL PRIMARY KEY,
  index_id    INTEGER NOT NULL REFERENCES indexes(id) ON DELETE CASCADE,
  slug        VARCHAR(200) NOT NULL,
  title       TEXT NOT NULL,
  type        VARCHAR(50) NOT NULL,
  content_md  TEXT NOT NULL DEFAULT '',
  frontmatter JSONB NOT NULL DEFAULT '{}',
  felix_refs  INTEGER[] NOT NULL DEFAULT '{}',
  entity_id   INTEGER REFERENCES wiki_entities(id) ON DELETE SET NULL,
  created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE (index_id, slug)
);

CREATE TABLE IF NOT EXISTS wiki_links (
  id             SERIAL PRIMARY KEY,
  source_page_id INTEGER NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
  target_page_id INTEGER REFERENCES wiki_pages(id) ON DELETE CASCADE,
  target_slug    VARCHAR(200) NOT NULL,
  link_type      VARCHAR(50) NOT NULL DEFAULT 'wiki'
);

CREATE INDEX IF NOT EXISTS idx_wiki_pages_index ON wiki_pages(index_id);
CREATE INDEX IF NOT EXISTS idx_wiki_entities_index ON wiki_entities(index_id);
CREATE INDEX IF NOT EXISTS idx_wiki_links_source ON wiki_links(source_page_id);
CREATE INDEX IF NOT EXISTS idx_wiki_relationships_subject ON wiki_relationships(subject_entity_id);
CREATE INDEX IF NOT EXISTS idx_wiki_relationships_object ON wiki_relationships(object_entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_chunks_chunk_id ON entity_chunks(chunk_id);
CREATE INDEX IF NOT EXISTS idx_wiki_links_target_slug ON wiki_links(target_slug);
