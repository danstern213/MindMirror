"""
Backfill logic for syncing existing files on startup.
"""

import logging
from pathlib import Path
from typing import Set

from .config import SyncConfig
from .state import SyncState
from .api_client import SyncAPIClient

logger = logging.getLogger(__name__)


def get_local_files(config: SyncConfig) -> Set[Path]:
    """
    Get all markdown files in the watch directory.

    Respects config settings for:
    - allowed_extensions
    - excluded_dirs
    - recursive scanning
    """
    files = set()

    if config.recursive:
        pattern = "**/*"
    else:
        pattern = "*"

    for ext in config.allowed_extensions:
        for file_path in config.watch_dir.glob(f"{pattern}{ext}"):
            # Skip excluded directories
            if any(excluded in file_path.parts for excluded in config.excluded_dirs):
                continue

            # Skip hidden files
            if file_path.name.startswith("."):
                continue

            # Skip files that are too large
            try:
                if file_path.stat().st_size > config.max_file_size:
                    logger.warning(
                        f"Skipping {file_path.name}: "
                        f"exceeds max size ({config.max_file_size} bytes)"
                    )
                    continue
            except OSError as e:
                logger.warning(f"Could not stat {file_path}: {e}")
                continue

            files.add(file_path)

    return files


def run_backfill(
    config: SyncConfig,
    state: SyncState,
    client: SyncAPIClient,
) -> dict:
    """
    Sync existing local files with the remote server.

    Returns a summary dict with counts of uploaded, replaced, skipped files.
    """
    logger.info("Starting backfill sync...")

    # Get remote files
    try:
        remote_files = client.list_files()
        remote_by_name = {f.filename: f for f in remote_files}
        logger.info(f"Found {len(remote_files)} files on server")
    except Exception as e:
        logger.error(f"Failed to fetch remote file list: {e}")
        raise

    # Get local files
    local_files = get_local_files(config)
    logger.info(f"Found {len(local_files)} local files to check")

    summary = {
        "uploaded": 0,
        "replaced": 0,
        "skipped": 0,
        "errors": 0,
    }

    for file_path in sorted(local_files):
        filename = file_path.name

        try:
            current_hash = state.compute_hash(file_path)
            local_state = state.get_file_state(filename)

            if filename not in remote_by_name:
                # File doesn't exist on server - upload it
                logger.info(f"[UPLOAD] {filename} (not on server)")
                result = client.upload_file(file_path)
                state.set_file_state(
                    filename,
                    current_hash,
                    remote_file_id=result.get("file_id")
                )
                summary["uploaded"] += 1

            elif local_state is None or local_state.content_hash != current_hash:
                # File exists on server but local state differs - replace it
                logger.info(f"[REPLACE] {filename} (content changed)")
                result = client.replace_file(file_path)
                state.set_file_state(
                    filename,
                    current_hash,
                    remote_file_id=result.get("file_id")
                )
                summary["replaced"] += 1

            else:
                # File exists and hash matches - skip
                logger.debug(f"[SKIP] {filename} (unchanged)")
                summary["skipped"] += 1

        except Exception as e:
            logger.error(f"Error processing {filename}: {e}")
            summary["errors"] += 1

    logger.info(
        f"Backfill complete: "
        f"{summary['uploaded']} uploaded, "
        f"{summary['replaced']} replaced, "
        f"{summary['skipped']} skipped, "
        f"{summary['errors']} errors"
    )

    return summary
