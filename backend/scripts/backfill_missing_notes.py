#!/usr/bin/env python3
"""
Upload local notes that Big Brain is missing or holds an outdated copy of.

Three ways a note falls through the weekly sync:
- missing: Roam_2026/ is never synced, and its daily notes are named
  "September 1st, 2021.md" where Obsidian says "2021-09-01.md", so a
  filename check cannot tell what is already there;
- no text: uploaded while blank, so nothing was indexed;
- stale: uploaded early (a daily note at 8am) and written in afterwards.

This compares each local note's text with what is stored (front matter
removed, punctuation-insensitive names, both daily-note spellings), skips
empty pages (Roam creates one for every [[link]]), and uploads or replaces
the rest through UploadService, the same path the API uses.

    python3 scripts/backfill_missing_notes.py --dry-run   # list, change nothing
    python3 scripts/backfill_missing_notes.py

Reads SUPABASE_URL, SUPABASE_KEY and OPENAI_API_KEY from backend/.env, the
account from BACKFILL_USER_ID, and the notes folder from SYNC_WATCH_DIR
(default ~/Documents/New Roam).
"""
import argparse
import asyncio
import io
import logging
import os
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from uuid import UUID

BACKEND_DIR = Path(__file__).resolve().parent.parent
os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))

from fastapi import UploadFile  # noqa: E402
from supabase import create_client  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.services.upload_service import UploadService  # noqa: E402

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("backfill")
logger.setLevel(logging.INFO)

# Below this many non-whitespace characters (front matter removed) a page has
# no writing in it.
MIN_CONTENT_CHARS = 20
# A stored copy shorter than this share of the local text is an early draft.
STALE_RATIO = 0.7
# Note templates and Roam's own settings pages are not writing.
SKIP_DIRS = {'Templates', 'roam'}
FRONT_MATTER = re.compile(r'\A---\n.*?\n---+\n?', re.S)


def _ordinal(day: int) -> str:
    if 11 <= day % 100 <= 13:
        return f"{day}th"
    return f"{day}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th') }"


def name_key(filename: str) -> str:
    """Letters and digits only: the export drops characters like '?' that uploads kept."""
    return re.sub(r'[^a-z0-9]', '', filename.lower().removesuffix('.md'))


def name_keys(filename: str) -> set:
    """The note's key, plus the other daily-note spelling's if it is one."""
    stem = filename.removesuffix('.md')
    keys = {name_key(filename)}
    iso = re.fullmatch(r'(\d{4})-(\d{2})-(\d{2})', stem)
    if iso:
        d = date(*map(int, iso.groups()))
        keys.add(name_key(f"{d.strftime('%B')} {_ordinal(d.day)}, {d.year}"))
    return keys


def note_body(text: str) -> str:
    return FRONT_MATTER.sub('', text)


def classify(watch_dir: Path, stored: dict) -> list:
    """(path, reason, stored filename or None) for every note that needs uploading."""
    todo = []
    for path in sorted(watch_dir.rglob('*.md')):
        parts = path.relative_to(watch_dir).parts
        if any(part.startswith('.') or part in SKIP_DIRS for part in parts):
            continue
        body = note_body(path.read_text(encoding='utf-8', errors='ignore'))
        if len(re.sub(r'\s', '', body)) < MIN_CONTENT_CHARS:
            continue
        matches = [stored[k] for k in name_keys(path.name) if k in stored]
        if not matches:
            todo.append((path, 'missing', None))
            continue
        filename, stored_chars = max(matches, key=lambda m: m[1])
        if stored_chars == 0:
            todo.append((path, 'no text', filename))
        elif stored_chars < STALE_RATIO * len(body):
            todo.append((path, 'stale', filename))
    return todo


def _all_rows(supabase, table: str, columns: str, user_id: str) -> list:
    # Ordered, or PostgREST pages can overlap and skip rows.
    rows, offset = [], 0
    while True:
        page = supabase.table(table).select(columns).eq('user_id', user_id)\
            .order('id').range(offset, offset + 999).execute().data
        rows += page
        if len(page) < 1000:
            return rows
        offset += 1000


def stored_notes(supabase, user_id: str) -> dict:
    """name key -> (stored filename, characters of indexed text)."""
    chars = Counter()
    for row in _all_rows(supabase, 'embeddings', 'file_id, text', user_id):
        chars[row['file_id']] += len(row['text'] or '')
    stored = {}
    for f in _all_rows(supabase, 'files', 'id, filename', user_id):
        key = name_key(f['filename'])
        if key not in stored or chars[f['id']] > stored[key][1]:
            stored[key] = (f['filename'], chars[f['id']])
    return stored


async def upload(service: UploadService, path: Path, user_id: UUID, replaces: str | None) -> str:
    if replaces:
        # Remove the stored copy by its own name, which may differ from the
        # local one ("Am I a good husband?.md" vs "Am I a good husband.md").
        await service.delete_file_by_name(replaces, user_id)
    file = UploadFile(filename=path.name, file=io.BytesIO(path.read_bytes()))
    return (await service.save_file(file, user_id)).status


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true', help='list what would be uploaded, change nothing')
    args = parser.parse_args()

    user_id = os.environ.get('BACKFILL_USER_ID')
    if not user_id:
        sys.exit("Set BACKFILL_USER_ID to your Supabase user UUID")
    watch_dir = Path(os.environ.get('SYNC_WATCH_DIR', '~/Documents/New Roam')).expanduser()

    settings = get_settings()
    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    todo = classify(watch_dir, stored_notes(supabase, user_id))
    logger.info(f"To upload: {dict(Counter(reason for _, reason, _ in todo))}")

    if args.dry_run:
        for path, reason, _ in todo:
            print(f"  {reason:8} {path.relative_to(watch_dir)}")
        return

    service = UploadService(supabase)
    results = Counter()
    for i, (path, reason, replaces) in enumerate(todo, 1):
        try:
            status = asyncio.run(upload(service, path, UUID(user_id), replaces))
        except Exception as e:
            status = 'failed'
            logger.error(f"{path.name}: {e}")
        results[status] += 1
        if i % 10 == 0:
            logger.info(f"{i}/{len(todo)} {dict(results)}")
    logger.info(f"Done: {dict(results)}")


if __name__ == '__main__':
    main()
