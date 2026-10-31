-- Move similarity search into Postgres.
--
-- Before this, every chat message downloaded every embedding row as JSON and
-- scored it in pure Python (~1s of CPU and ~30MB of transfer per 1,000 chunks).
--
-- Run this in the Supabase SQL editor BEFORE deploying the code that uses it:
-- new uploads write `embedding_vec`, so the column has to exist first. It is
-- safe to run more than once.

create extension if not exists vector;

-- text-embedding-3-large shortened to 1536 dims (EMBEDDING_DIMENSIONS).
-- Filled by backend/scripts/reembed_vectors.py; the old JSON `embedding`
-- column (ada-002) stays untouched until the new path is proven.
alter table embeddings add column if not exists embedding_vec vector(1536);

-- Exact (sequential) search on purpose. A personal corpus is a few thousand
-- chunks, which Postgres scores in tens of milliseconds, and exact search never
-- drops rows when a date filter is applied (an approximate HNSW index filters
-- after the scan, so a narrow date range can come back nearly empty). Add
-- `using hnsw (embedding_vec vector_cosine_ops)` only past ~100k chunks.
create index if not exists embeddings_user_id_idx on embeddings (user_id);

create or replace function match_embeddings(
    query_embedding vector(1536),
    match_user_id text,
    match_count int default 150,
    date_start date default null,
    date_end date default null
)
returns table (
    file_id text,
    chunk_index int,
    text text,
    similarity float,
    title text,
    document_date date
)
language sql stable
as $$
    select
        e.file_id::text,
        e.chunk_index::int,
        e.text,
        1 - (e.embedding_vec <=> query_embedding) as similarity,
        f.title::text,
        f.document_date::date
    from embeddings e
    join files f on f.id = e.file_id
    where e.user_id::text = match_user_id
      and e.embedding_vec is not null
      and (date_start is null or f.document_date >= date_start)
      and (date_end is null or f.document_date <= date_end)
    order by e.embedding_vec <=> query_embedding
    limit match_count;
$$;
