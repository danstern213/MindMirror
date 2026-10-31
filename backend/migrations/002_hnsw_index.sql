-- Index the vectors. 001 scanned every row exactly, which is ~0.7s warm but
-- 5s+ (sometimes past the statement timeout) on a cold cache, because each
-- row still carries the wide legacy JSON `embedding` column.
--
-- Safe to run more than once. Takes a minute or two to build on ~13K rows.

create index if not exists embeddings_embedding_vec_hnsw
    on embeddings using hnsw (embedding_vec vector_cosine_ops);

-- An approximate index filters AFTER it finds neighbours, and this table holds
-- three accounts' notes, so a plain index scan could return mostly other
-- accounts' rows. pgvector 0.8+ can keep scanning until enough rows pass the
-- filter (iterative scan); on older versions a wide ef_search does most of
-- the same job. Date-filtered queries skip the index entirely (the `+ 0`
-- below): the date range already narrows the rows to a few hundred at most,
-- and an exact scan over those never misses one.
do $$
declare
    iterative text := '';
begin
    if (select string_to_array(extversion, '.')::int[] >= '{0,8}'::int[]
        from pg_extension where extname = 'vector') then
        iterative := 'set hnsw.iterative_scan = relaxed_order';
    end if;

    execute format($f$
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
        language plpgsql stable
        set hnsw.ef_search = 400
        %s
        as $body$
        begin
            if date_start is null and date_end is null then
                return query
                select e.file_id::text, e.chunk_index::int, e.text,
                       1 - (e.embedding_vec <=> query_embedding),
                       f.title::text, f.document_date::date
                from embeddings e
                join files f on f.id = e.file_id
                where e.user_id::text = match_user_id
                  and e.embedding_vec is not null
                order by e.embedding_vec <=> query_embedding
                limit match_count;
            else
                return query
                select e.file_id::text, e.chunk_index::int, e.text,
                       1 - (e.embedding_vec <=> query_embedding),
                       f.title::text, f.document_date::date
                from embeddings e
                join files f on f.id = e.file_id
                where e.user_id::text = match_user_id
                  and e.embedding_vec is not null
                  and (date_start is null or f.document_date >= date_start)
                  and (date_end is null or f.document_date <= date_end)
                order by (e.embedding_vec <=> query_embedding) + 0
                limit match_count;
            end if;
        end;
        $body$;
    $f$, iterative);
end;
$$;
