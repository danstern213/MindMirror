"""
API Key service for managing long-lived API keys.
Keys are hashed (SHA-256) before storage - plaintext is shown only once at creation.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from uuid import UUID
import logging

from supabase import Client

logger = logging.getLogger(__name__)


class APIKeyService:
    """Service for managing API keys."""

    KEY_PREFIX = "ak_"
    KEY_LENGTH = 32  # 32 hex chars = 128 bits of entropy

    def __init__(self, client: Client):
        self.client = client

    def _generate_key(self) -> str:
        """Generate a new API key with prefix."""
        random_bytes = secrets.token_hex(self.KEY_LENGTH // 2)
        return f"{self.KEY_PREFIX}{random_bytes}"

    def _hash_key(self, api_key: str) -> str:
        """Hash an API key using SHA-256."""
        return hashlib.sha256(api_key.encode()).hexdigest()

    def _get_key_prefix(self, api_key: str) -> str:
        """Get the first 8 characters of the key for identification."""
        return api_key[:8]

    async def create_api_key(
        self,
        user_id: UUID,
        name: str,
        expires_in_days: Optional[int] = None
    ) -> dict:
        """
        Create a new API key for a user.

        Returns the key info including the plaintext key (shown only once).
        """
        # Generate key
        plaintext_key = self._generate_key()
        key_hash = self._hash_key(plaintext_key)
        key_prefix = self._get_key_prefix(plaintext_key)

        # Calculate expiration if provided
        expires_at = None
        if expires_in_days:
            expires_at = (datetime.now(timezone.utc) + timedelta(days=expires_in_days)).isoformat()

        # Store in database
        result = self.client.table("api_keys").insert({
            "user_id": str(user_id),
            "key_hash": key_hash,
            "key_prefix": key_prefix,
            "name": name,
            "expires_at": expires_at
        }).execute()

        if not result.data:
            raise Exception("Failed to create API key")

        key_data = result.data[0]

        return {
            "id": key_data["id"],
            "name": key_data["name"],
            "key_prefix": key_data["key_prefix"],
            "key": plaintext_key,  # Only time this is returned
            "created_at": key_data["created_at"],
            "expires_at": key_data.get("expires_at")
        }

    async def validate_api_key(self, api_key: str) -> Optional[UUID]:
        """
        Validate an API key and return the associated user_id.

        Returns None if the key is invalid, revoked, or expired.
        """
        if not api_key or not api_key.startswith(self.KEY_PREFIX):
            return None

        key_hash = self._hash_key(api_key)
        key_prefix = self._get_key_prefix(api_key)

        # Look up key by prefix first (indexed), then verify hash
        result = self.client.table("api_keys").select("*").eq(
            "key_prefix", key_prefix
        ).eq(
            "is_revoked", False
        ).execute()

        if not result.data:
            return None

        # Find matching key by hash
        for key_record in result.data:
            if key_record["key_hash"] == key_hash:
                # Check expiration
                if key_record.get("expires_at"):
                    expires_at = datetime.fromisoformat(key_record["expires_at"].replace("Z", "+00:00"))
                    if expires_at < datetime.now(timezone.utc):
                        logger.info(f"API key {key_prefix}... has expired")
                        return None

                # Update last_used_at
                try:
                    self.client.table("api_keys").update({
                        "last_used_at": datetime.now(timezone.utc).isoformat()
                    }).eq("id", key_record["id"]).execute()
                except Exception as e:
                    logger.warning(f"Failed to update last_used_at: {e}")

                return UUID(key_record["user_id"])

        return None

    async def list_api_keys(self, user_id: UUID) -> List[dict]:
        """List all API keys for a user (without plaintext)."""
        result = self.client.table("api_keys").select(
            "id, name, key_prefix, created_at, last_used_at, expires_at, is_revoked, revoked_at"
        ).eq(
            "user_id", str(user_id)
        ).order(
            "created_at", desc=True
        ).execute()

        return result.data or []

    async def revoke_api_key(self, key_id: UUID, user_id: UUID) -> bool:
        """Revoke an API key (soft delete)."""
        result = self.client.table("api_keys").update({
            "is_revoked": True,
            "revoked_at": datetime.now(timezone.utc).isoformat()
        }).eq(
            "id", str(key_id)
        ).eq(
            "user_id", str(user_id)
        ).execute()

        return len(result.data) > 0 if result.data else False
