#!/usr/bin/env python3
"""
Re-embed every stored chunk into the pgvector `embedding_vec` column.

Each chunk is embedded with EMBEDDING_MODEL (text-embedding-3-large) and with
its note title and date prefixed (see embedding_input), replacing the old
ada-002 vectors that only ever saw the raw chunk text.

Idempotent and resumable: it only touches rows whose `embedding_vec` is still
null, so stopping it and running it again picks up where it left off. Run it
once after applying migrations/001_pgvector_search.sql, and once more after
deploying, to catch anything uploaded in between.

Reads SUPABASE_URL, SUPABASE_KEY (the new secret key) and OPENAI_API_KEY from
backend/.env.

    python3 scripts/reembed_vectors.py --dry-run   # count rows, estimate cost
    python3 scripts/reembed_vectors.py
"""
import argparse
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
os.chdir(BACKEND_DIR)  # Settings reads .env relative to the working directory
sys.path.insert(0, str(BACKEND_DIR))

from supabase import create_client  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.services.embedding_helper import embedding_input, generate_embeddings_batch  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
# The helper logs a line per text; at batch scale that drowns out the progress.
logging.getLogger("app.services.embedding_helper").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("reembed")

BATCH_SIZE = 100
UPDATE_WORKERS = 8
# text-embedding-3-large list price, USD per 1M tokens.
PRICE_PER_MILLION_TOKENS = 0.13


def fetch_pending(supabase, limit: int):
    return supabase.table('embeddings')\
        .select('id, text, files(title, document_date)')\
        .is_('embedding_vec', 'null')\
        .limit(limit)\
        .execute().data


def count_pending(supabase) -> int:
    return supabase.table('embeddings')\
        .select('id', count='exact')\
        .is_('embedding_vec', 'null')\
        .limit(1)\
        .execute().count


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true', help='count pending rows and estimate cost, write nothing')
    args = parser.parse_args()

    settings = get_settings()
    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

    pending = count_pending(supabase)
    logger.info(f"{pending} chunks need embedding with {settings.EMBEDDING_MODEL}")
    if pending == 0:
        return

    if args.dry_run:
        sample = fetch_pending(supabase, 500)
        avg_chars = sum(len(r['text'] or '') for r in sample) / max(len(sample), 1)
        est_tokens = pending * avg_chars / 4
        logger.info(
            f"~{est_tokens / 1e6:.2f}M tokens, about ${est_tokens / 1e6 * PRICE_PER_MILLION_TOKENS:.2f}"
        )
        return

    failed_ids = set()
    done = 0

    def write(row_and_vector):
        row_id, vector = row_and_vector
        supabase.table('embeddings').update({'embedding_vec': json.dumps(vector)}).eq('id', row_id).execute()

    while True:
        # Finished rows drop out of the null filter, so the first page is always
        # the next work. Over-fetch by the failures so they cannot stall the loop.
        rows = [r for r in fetch_pending(supabase, BATCH_SIZE + len(failed_ids))
                if r['id'] not in failed_ids][:BATCH_SIZE]
        if not rows:
            break
        empty = [r for r in rows if not (r['text'] or '').strip()]
        failed_ids.update(r['id'] for r in empty)
        rows = [r for r in rows if r not in empty]
        if not rows:
            continue

        inputs = [
            embedding_input(r['text'], (r.get('files') or {}).get('title'), (r.get('files') or {}).get('document_date'))
            for r in rows
        ]
        try:
            vectors = generate_embeddings_batch(inputs)
        except Exception as e:
            logger.error(f"Batch failed, skipping {len(rows)} rows this run: {e}")
            failed_ids.update(r['id'] for r in rows)
            continue

        with ThreadPoolExecutor(max_workers=UPDATE_WORKERS) as pool:
            results = pool.map(lambda pair: _safe(write, pair), zip([r['id'] for r in rows], vectors))
            for row, ok in zip(rows, results):
                if ok:
                    done += 1
                else:
                    failed_ids.add(row['id'])

        logger.info(f"{done}/{pending} embedded" + (f", {len(failed_ids)} failed" if failed_ids else ""))

    logger.info(f"Done. Embedded {done}, failed {len(failed_ids)}. Re-run to retry failures.")


def _safe(fn, arg) -> bool:
    try:
        fn(arg)
        return True
    except Exception as e:
        logger.error(f"Update failed for row {arg[0]}: {e}")
        return False


if __name__ == '__main__':
    main()
