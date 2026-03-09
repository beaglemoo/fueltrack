"""OAuth token management for Fuel Finder API."""

import time
import logging

import httpx

logger = logging.getLogger(__name__)


class TokenManager:
    """Manages OAuth access tokens with automatic refresh."""

    def __init__(self, base_url: str, client_id: str, client_secret: str):
        self._base_url = base_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._expires_at: float = 0

    async def get_token(self, client: httpx.AsyncClient) -> str:
        if self._token and time.time() < self._expires_at - 60:
            return self._token

        url = f"{self._base_url}/api/v1/oauth/generate_access_token"
        resp = await client.post(
            url,
            json={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("success"):
            raise RuntimeError(f"Token request failed: {data}")

        self._token = data["data"]["access_token"]
        expires_in = data["data"].get("expires_in", 3600)
        self._expires_at = time.time() + expires_in
        logger.info("Obtained access token (expires in %ds)", expires_in)
        return self._token
