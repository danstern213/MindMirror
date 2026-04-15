"""
API client for interacting with the Big Brain backend.
"""

import time
import logging
import httpx
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RemoteFile:
    """Represents a file on the remote server."""
    id: str
    filename: str
    status: str
    created_at: str


class SyncAPIClient:
    """HTTP client for file sync API operations."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        max_retries: int = 5,
        initial_backoff: float = 1.0,
        max_backoff: float = 60.0,
    ):
        self.api_url = api_url
        self.api_key = api_key
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff

        self._client = httpx.Client(
            headers={"X-API-Key": api_key},
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    def close(self):
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _retry_with_backoff(self, operation: str, func, *args, **kwargs) -> Any:
        """Execute a function with exponential backoff retry."""
        backoff = self.initial_backoff

        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except httpx.HTTPStatusError as e:
                # Don't retry client errors (4xx) except 429 (rate limit)
                if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                    logger.error(f"{operation} failed with client error: {e}")
                    raise
                logger.warning(
                    f"{operation} attempt {attempt + 1}/{self.max_retries} failed: {e}"
                )
            except (httpx.RequestError, httpx.TimeoutException) as e:
                logger.warning(
                    f"{operation} attempt {attempt + 1}/{self.max_retries} failed: {e}"
                )

            if attempt < self.max_retries - 1:
                logger.info(f"Retrying in {backoff:.1f}s...")
                time.sleep(backoff)
                backoff = min(backoff * 2, self.max_backoff)

        raise Exception(f"{operation} failed after {self.max_retries} attempts")

    def list_files(self) -> List[RemoteFile]:
        """Fetch list of files from the server."""
        def _list():
            response = self._client.get(f"{self.api_url}/files/list")
            response.raise_for_status()
            return response.json()

        files_data = self._retry_with_backoff("list_files", _list)
        return [
            RemoteFile(
                id=f["id"],
                filename=f["filename"],
                status=f.get("status", "unknown"),
                created_at=f.get("created_at", ""),
            )
            for f in files_data
        ]

    def upload_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Upload a new file to the server.

        Returns the upload response containing file_id and status.
        """
        def _upload():
            with open(file_path, "rb") as f:
                files = {"file": (file_path.name, f, "text/markdown")}
                response = self._client.post(
                    f"{self.api_url}/files/upload",
                    files=files,
                )
                response.raise_for_status()
                return response.json()

        logger.info(f"Uploading: {file_path.name}")
        result = self._retry_with_backoff("upload_file", _upload)
        logger.info(
            f"Uploaded {file_path.name}: id={result.get('file_id')}, "
            f"status={result.get('status')}"
        )
        return result

    def replace_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Replace an existing file on the server.

        This deletes the old file and uploads the new version.
        Returns the upload response containing file_id and status.
        """
        def _replace():
            with open(file_path, "rb") as f:
                files = {"file": (file_path.name, f, "text/markdown")}
                response = self._client.put(
                    f"{self.api_url}/files/replace",
                    files=files,
                )
                response.raise_for_status()
                return response.json()

        logger.info(f"Replacing: {file_path.name}")
        result = self._retry_with_backoff("replace_file", _replace)
        logger.info(
            f"Replaced {file_path.name}: id={result.get('file_id')}, "
            f"status={result.get('status')}"
        )
        return result

    def health_check(self) -> bool:
        """Check if the API is reachable."""
        try:
            response = self._client.get(f"{self.api_url.rsplit('/api/v1', 1)[0]}/health")
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
