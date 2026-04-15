"""
Configuration for the file sync service.
"""

import os
from pathlib import Path
from dataclasses import dataclass


@dataclass
class SyncConfig:
    """Configuration for the file sync service."""

    # Directory to watch for file changes
    watch_dir: Path

    # Backend API URL
    api_url: str

    # API key for authentication
    api_key: str

    # SQLite database path for state tracking
    state_db: Path

    # Debounce delay for file modifications (seconds)
    debounce_delay: float = 10.0

    # Maximum file size to sync (bytes) - matches backend limit
    max_file_size: int = 10 * 1024 * 1024  # 10MB

    # File extensions to sync
    allowed_extensions: tuple = (".md",)

    # Directories to exclude
    excluded_dirs: tuple = (".obsidian", ".git", ".trash")

    # Whether to sync files in subdirectories
    recursive: bool = True


def get_config() -> SyncConfig:
    """Load configuration from environment variables."""

    watch_dir = os.environ.get("SYNC_WATCH_DIR")
    if not watch_dir:
        raise ValueError("SYNC_WATCH_DIR environment variable is required")

    api_url = os.environ.get("SYNC_API_URL")
    if not api_url:
        raise ValueError("SYNC_API_URL environment variable is required")

    api_key = os.environ.get("SYNC_API_KEY")
    if not api_key:
        raise ValueError("SYNC_API_KEY environment variable is required")

    state_db = os.environ.get(
        "SYNC_STATE_DB",
        os.path.expanduser("~/.file_sync_state.db")
    )

    debounce_delay = float(os.environ.get("SYNC_DEBOUNCE_DELAY", "10.0"))

    return SyncConfig(
        watch_dir=Path(watch_dir).expanduser().resolve(),
        api_url=api_url.rstrip("/"),
        api_key=api_key,
        state_db=Path(state_db).expanduser().resolve(),
        debounce_delay=debounce_delay,
    )
