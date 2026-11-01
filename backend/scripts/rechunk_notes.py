#!/usr/bin/env python3
"""
Re-index notes whose stored chunks don't match what the chunker makes now.

Until 2026-11-01 the chunker could cut a tiny chunk at an early paragraph
break, creep forward a character at a time, and stop at its iteration cap,
silently dropping the rest of the note; it also repeated the last chunk's tail
as extra chunks. This downloads each note's original from storage, chunks it
again, and re-embeds the note if the chunks differ. Markdown and text only.

    python3 scripts/rechunk_notes.py --dry-run   # count, change nothing
    python3 scripts/rechunk_notes.py

Reads SUPABASE_URL, SUPABASE_KEY and OPENAI_API_KEY from backend/.env and the
account from BACKFILL_USER_ID.
"""
import argparse
import asyncio
import logging
import os
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / 'scripts'))

from supabase import create_client  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.services.embedding_service import EmbeddingService  # noqa: E402
from backfill_missing_notes import _all_rows  # noqa: E402

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("rechunk")
logger.setLevel(logging.INFO)
logging.getLogger("app.services.embedding_service").setLevel(logging.CRITICAL)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true', help='count notes to re-index, change nothing')
    args = parser.parse_args()

    user_id = os.environ.get('BACKFILL_USER_ID')
    if not user_id:
        sys.exit("Set BACKFILL_USER_ID to your Supabase user UUID")

    settings = get_settings()
    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    service = EmbeddingService(supabase)

    stored = defaultdict(list)
    for row in _all_rows(supabase, 'embeddings', 'file_id, chunk_index, text', user_id):
        stored[row['file_id']].append(row)
    files = [f for f in _all_rows(supabase, 'files', 'id, filename, title, document_date, storage_path', user_id)
             if f['filename'].lower().endswith(('.md', '.txt')) and f['id'] in stored]
    logger.info(f"Checking {len(files)} indexed notes")

    # The Supabase client is not safe to share across threads (broken pipes,
    # "deque mutated"), so each download worker gets its own.
    local = threading.local()

    def download(f):
        try:
            if not hasattr(local, 'client'):
                local.client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
            return f, local.client.storage.from_('documents').download(f['storage_path']).decode('utf-8', errors='ignore')
        except Exception as e:
            logger.error(f"Download failed for {f['filename']}: {e}")
            return f, None

    # Downloads are slow one at a time; writes below stay sequential.
    with ThreadPoolExecutor(max_workers=6) as pool:
        originals = list(pool.map(download, files))

    todo = []
    for f, text in originals:
        if not text or not text.strip():
            continue
        current = [r['text'] for r in sorted(stored[f['id']], key=lambda r: r['chunk_index'] or 0)]
        if service.chunk_text(text) != current:
            todo.append((f, text))
    logger.info(f"{len(todo)} notes need re-indexing")
    if args.dry_run:
        for f, text in sorted(todo, key=lambda t: -len(t[1]))[:25]:
            print(f"  {len(text):>7}  {f['filename']}")
        return

    done = failed = 0
    for f, text in todo:
        try:
            supabase.table('embeddings').delete().eq('file_id', f['id']).execute()
            asyncio.run(service.generate_and_save_embedding(
                text, f['id'], user_id, title=f['title'], document_date=f['document_date']
            ))
            done += 1
        except Exception as e:
            failed += 1
            logger.error(f"{f['filename']}: {e}")
        if (done + failed) % 25 == 0:
            logger.info(f"{done + failed}/{len(todo)} ({failed} failed)")
    logger.info(f"Done: {done} re-indexed, {failed} failed")


if __name__ == '__main__':
    main()
