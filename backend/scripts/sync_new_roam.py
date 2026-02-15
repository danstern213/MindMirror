#!/usr/bin/env python3
"""
One-shot sync of markdown files from New Roam to the Big Brain backend.

Scans SYNC_WATCH_DIR (default: ~/Documents/New Roam) for .md files,
fetches the list of already-uploaded files from the API, and uploads
any files not yet present.

Usage:
    python sync_new_roam.py

Environment variables:
    SYNC_API_URL   - Backend API URL (default: http://localhost:8000/api/v1)
    SYNC_API_KEY   - API key for authentication (required)
    SYNC_WATCH_DIR - Directory to scan (default: ~/Documents/New Roam)
"""

import os
import sys
import logging
from pathlib import Path

# Add the scripts directory to the path so we can import file_sync
scripts_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, scripts_dir)

from file_sync.api_client import SyncAPIClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_local_md_files(watch_dir: Path) -> list[Path]:
    """Recursively find all .md files, skipping hidden files and directories."""
    files = []
    for path in watch_dir.rglob("*.md"):
        rel_parts = path.relative_to(watch_dir).parts
        # Skip hidden files/dirs
        if any(part.startswith(".") for part in rel_parts):
            continue
        # Skip legacy Roam export folder (already uploaded with old naming)
        if rel_parts[0] == "Roam_2026":
            continue
        files.append(path)
    return sorted(files)


def main():
    api_url = os.environ.get("SYNC_API_URL", "http://localhost:8000/api/v1")
    api_key = os.environ.get("SYNC_API_KEY")
    watch_dir = Path(
        os.environ.get("SYNC_WATCH_DIR", "~/Documents/New Roam")
    ).expanduser().resolve()

    if not api_key:
        logger.error("SYNC_API_KEY environment variable is required")
        sys.exit(1)

    if not watch_dir.exists():
        logger.error(f"Watch directory does not exist: {watch_dir}")
        sys.exit(1)

    logger.info(f"Scanning: {watch_dir}")
    logger.info(f"API URL: {api_url}")

    # Find local .md files
    local_files = get_local_md_files(watch_dir)
    logger.info(f"Found {len(local_files)} .md files locally")

    if not local_files:
        logger.info("Nothing to do.")
        return

    # Fetch already-uploaded filenames from the API
    with SyncAPIClient(api_url, api_key) as client:
        remote_files = client.list_files()
        remote_filenames = {rf.filename for rf in remote_files}
        logger.info(f"Found {len(remote_filenames)} files already uploaded")

        # Upload files that don't exist remotely
        uploaded = 0
        skipped = 0
        failed = 0

        for file_path in local_files:
            if file_path.name in remote_filenames:
                logger.debug(f"Skipped (already uploaded): {file_path.name}")
                skipped += 1
                continue

            try:
                result = client.upload_file(file_path)
                if result.get("status") == "skipped":
                    logger.info(f"Skipped (duplicate on server): {file_path.name}")
                    skipped += 1
                else:
                    uploaded += 1
            except Exception as e:
                logger.error(f"Failed to upload {file_path.name}: {e}")
                failed += 1

    logger.info(f"Done. Uploaded: {uploaded}, Skipped: {skipped}, Failed: {failed}")


if __name__ == "__main__":
    main()
