#!/usr/bin/env python3
"""
File watcher for syncing markdown files to the Big Brain backend.

Usage:
    python -m file_sync.watcher

Environment variables:
    SYNC_WATCH_DIR  - Directory to watch (required)
    SYNC_API_URL    - Backend API URL (required)
    SYNC_API_KEY    - API key for authentication (required)
    SYNC_STATE_DB   - Path to SQLite state database (default: ~/.file_sync_state.db)
    SYNC_DEBOUNCE_DELAY - Seconds to wait after last edit before syncing (default: 10)
"""

import sys
import time
import signal
import logging
import threading
from pathlib import Path
from typing import Dict, Optional

from watchdog.observers import Observer
from watchdog.events import (
    FileSystemEventHandler,
    FileCreatedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileDeletedEvent,
)

from .config import get_config, SyncConfig
from .state import SyncState
from .api_client import SyncAPIClient
from .backfill import run_backfill

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class DebouncedTimer:
    """A timer that resets on each call, only firing after the delay passes."""

    def __init__(self, delay: float, callback):
        self.delay = delay
        self.callback = callback
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

    def reset(self):
        """Reset the timer. Callback will fire after delay seconds of inactivity."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.delay, self._fire)
            self._timer.start()

    def _fire(self):
        """Fire the callback."""
        with self._lock:
            self._timer = None
        self.callback()

    def cancel(self):
        """Cancel the timer if running."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None


class FileSyncHandler(FileSystemEventHandler):
    """Handles file system events and syncs files to the backend."""

    def __init__(
        self,
        config: SyncConfig,
        state: SyncState,
        client: SyncAPIClient,
    ):
        super().__init__()
        self.config = config
        self.state = state
        self.client = client

        # Debounce timers per file path
        self._timers: Dict[str, DebouncedTimer] = {}
        self._lock = threading.Lock()

    def _should_sync(self, path: Path) -> bool:
        """Check if a file should be synced based on config."""
        # Check extension
        if path.suffix.lower() not in self.config.allowed_extensions:
            return False

        # Check for hidden files
        if path.name.startswith("."):
            return False

        # Check excluded directories
        if any(excluded in path.parts for excluded in self.config.excluded_dirs):
            return False

        # Check file size
        try:
            if path.stat().st_size > self.config.max_file_size:
                logger.warning(f"Skipping {path.name}: exceeds max size")
                return False
        except OSError:
            return False

        return True

    def _get_debounced_sync(self, file_path: Path):
        """Get or create a debounced sync function for a file."""
        path_str = str(file_path)

        with self._lock:
            if path_str not in self._timers:
                def do_sync():
                    self._sync_file(file_path)

                self._timers[path_str] = DebouncedTimer(
                    self.config.debounce_delay,
                    do_sync,
                )

            return self._timers[path_str]

    def _sync_file(self, file_path: Path):
        """Sync a single file to the backend."""
        if not file_path.exists():
            logger.debug(f"File no longer exists: {file_path}")
            return

        if not self._should_sync(file_path):
            return

        filename = file_path.name

        try:
            current_hash = self.state.compute_hash(file_path)
            existing_state = self.state.get_file_state(filename)

            # Check if content actually changed
            if existing_state and existing_state.content_hash == current_hash:
                logger.debug(f"Content unchanged, skipping: {filename}")
                return

            # Determine if this is an upload or replace
            if existing_state is None:
                # New file - upload
                logger.info(f"[UPLOAD] {filename}")
                result = self.client.upload_file(file_path)
            else:
                # Existing file - replace
                logger.info(f"[REPLACE] {filename}")
                result = self.client.replace_file(file_path)

            # Update state
            self.state.set_file_state(
                filename,
                current_hash,
                remote_file_id=result.get("file_id")
            )

        except Exception as e:
            logger.error(f"Failed to sync {filename}: {e}")

    def on_created(self, event):
        """Handle file creation events."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        if not self._should_sync(file_path):
            return

        logger.debug(f"File created: {file_path.name}")

        # Use a shorter debounce for new files (2 seconds)
        timer = self._get_debounced_sync(file_path)
        timer.delay = 2.0  # Shorter delay for new files
        timer.reset()

    def on_modified(self, event):
        """Handle file modification events."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        if not self._should_sync(file_path):
            return

        logger.debug(f"File modified: {file_path.name}")

        # Reset the debounce timer
        timer = self._get_debounced_sync(file_path)
        timer.delay = self.config.debounce_delay  # Full delay for modifications
        timer.reset()

    def on_moved(self, event):
        """Handle file move/rename events."""
        if event.is_directory:
            return

        dest_path = Path(event.dest_path)

        # If moved into our watch directory or renamed, treat as new file
        if self._should_sync(dest_path):
            logger.debug(f"File moved/renamed to: {dest_path.name}")
            timer = self._get_debounced_sync(dest_path)
            timer.delay = 2.0
            timer.reset()

    def on_deleted(self, event):
        """Handle file deletion events."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Log the deletion but don't sync to backend (safety first)
        if file_path.suffix.lower() in self.config.allowed_extensions:
            logger.info(f"[DELETED] {file_path.name} (not synced to backend)")

            # Cancel any pending sync for this file
            path_str = str(file_path)
            with self._lock:
                if path_str in self._timers:
                    self._timers[path_str].cancel()
                    del self._timers[path_str]

    def shutdown(self):
        """Cancel all pending timers."""
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()


def main():
    """Main entry point for the file sync watcher."""
    logger.info("=== Big Brain File Sync ===")

    # Load configuration
    try:
        config = get_config()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    logger.info(f"Watch directory: {config.watch_dir}")
    logger.info(f"API URL: {config.api_url}")
    logger.info(f"State database: {config.state_db}")
    logger.info(f"Debounce delay: {config.debounce_delay}s")

    # Verify watch directory exists
    if not config.watch_dir.exists():
        logger.error(f"Watch directory does not exist: {config.watch_dir}")
        sys.exit(1)

    # Initialize components
    state = SyncState(config.state_db)
    client = SyncAPIClient(config.api_url, config.api_key)

    # Health check
    if not client.health_check():
        logger.warning("Backend health check failed - will retry on operations")

    # Run backfill on startup
    try:
        run_backfill(config, state, client)
    except Exception as e:
        logger.error(f"Backfill failed: {e}")
        logger.info("Continuing with file watching...")

    # Set up file watcher
    handler = FileSyncHandler(config, state, client)
    observer = Observer()
    observer.schedule(handler, str(config.watch_dir), recursive=config.recursive)

    # Handle shutdown signals
    shutdown_event = threading.Event()

    def signal_handler(signum, frame):
        logger.info("Shutdown signal received...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start watching
    observer.start()
    logger.info(f"Watching for changes in {config.watch_dir}...")
    logger.info("Press Ctrl+C to stop")

    try:
        while not shutdown_event.is_set():
            time.sleep(1)
    finally:
        logger.info("Shutting down...")
        observer.stop()
        handler.shutdown()
        client.close()
        observer.join()
        logger.info("Goodbye!")


if __name__ == "__main__":
    main()
