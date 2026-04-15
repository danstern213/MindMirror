"""
SQLite state management for tracking synced files.
"""

import sqlite3
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FileState:
    """State of a synced file."""
    filename: str
    content_hash: str
    last_synced: datetime
    remote_file_id: Optional[str] = None


class SyncState:
    """Manages SQLite database for tracking synced file state."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite database schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS synced_files (
                    filename TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    last_synced TEXT NOT NULL,
                    remote_file_id TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_content_hash
                ON synced_files(content_hash)
            """)
            conn.commit()

        logger.info(f"Initialized state database at {self.db_path}")

    @staticmethod
    def compute_hash(file_path: Path) -> str:
        """Compute MD5 hash of file content."""
        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def get_file_state(self, filename: str) -> Optional[FileState]:
        """Get the state of a synced file."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT filename, content_hash, last_synced, remote_file_id "
                "FROM synced_files WHERE filename = ?",
                (filename,)
            )
            row = cursor.fetchone()

            if row:
                return FileState(
                    filename=row[0],
                    content_hash=row[1],
                    last_synced=datetime.fromisoformat(row[2]),
                    remote_file_id=row[3]
                )
            return None

    def set_file_state(
        self,
        filename: str,
        content_hash: str,
        remote_file_id: Optional[str] = None
    ):
        """Update or insert the state of a synced file."""
        now = datetime.utcnow().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO synced_files (filename, content_hash, last_synced, remote_file_id)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(filename) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    last_synced = excluded.last_synced,
                    remote_file_id = COALESCE(excluded.remote_file_id, remote_file_id)
            """, (filename, content_hash, now, remote_file_id))
            conn.commit()

        logger.debug(f"Updated state for {filename}: hash={content_hash[:8]}...")

    def remove_file_state(self, filename: str):
        """Remove a file from the state database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM synced_files WHERE filename = ?",
                (filename,)
            )
            conn.commit()

        logger.debug(f"Removed state for {filename}")

    def get_all_states(self) -> Dict[str, FileState]:
        """Get all file states as a dictionary keyed by filename."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT filename, content_hash, last_synced, remote_file_id "
                "FROM synced_files"
            )
            return {
                row[0]: FileState(
                    filename=row[0],
                    content_hash=row[1],
                    last_synced=datetime.fromisoformat(row[2]),
                    remote_file_id=row[3]
                )
                for row in cursor.fetchall()
            }

    def needs_sync(self, file_path: Path) -> bool:
        """
        Check if a file needs to be synced.

        Returns True if:
        - File is not in the state database
        - File content hash differs from stored hash
        """
        filename = file_path.name
        current_hash = self.compute_hash(file_path)

        state = self.get_file_state(filename)
        if state is None:
            logger.debug(f"{filename}: not in state db, needs sync")
            return True

        if state.content_hash != current_hash:
            logger.debug(
                f"{filename}: hash changed "
                f"({state.content_hash[:8]}... -> {current_hash[:8]}...), needs sync"
            )
            return True

        logger.debug(f"{filename}: hash unchanged, skip sync")
        return False
