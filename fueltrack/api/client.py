"""Fuel Finder API client."""

import asyncio
import logging

import httpx

from .auth import TokenManager
from .models import Station

logger = logging.getLogger(__name__)

MAX_BATCH_SIZE = 500
MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 30]


class FuelFinderClient:
    """Async client for the Fuel Finder API."""

    def __init__(self, base_url: str, token_manager: TokenManager):
        self._base_url = base_url
        self._token_manager = token_manager
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def _get(self, path: str, params: dict | None = None) -> httpx.Response:
        assert self._client is not None
        token = await self._token_manager.get_token(self._client)
        headers = {"Authorization": f"Bearer {token}"}

        for attempt in range(MAX_RETRIES):
            resp = await self._client.get(
                f"{self._base_url}{path}",
                headers=headers,
                params=params,
            )
            if resp.status_code == 429:
                delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                logger.warning("Rate limited, waiting %ds", delay)
                await asyncio.sleep(delay)
                continue
            if resp.status_code == 401:
                self._token_manager._token = None
                token = await self._token_manager.get_token(self._client)
                headers = {"Authorization": f"Bearer {token}"}
                continue
            resp.raise_for_status()
            return resp

        raise RuntimeError(f"Failed after {MAX_RETRIES} retries: {path}")

    async def fetch_all_prices(self) -> list[Station]:
        """Fetch all fuel prices across all batches."""
        all_stations: list[Station] = []
        batch = 1

        while True:
            logger.info("Fetching fuel prices batch %d", batch)
            resp = await self._get(
                "/api/v1/pfs/fuel-prices",
                params={"batch-number": batch},
            )

            if resp.status_code == 404:
                break

            data = resp.json()
            if not data:
                break

            stations = [Station(**s) for s in data]
            all_stations.extend(stations)
            logger.info("Batch %d: %d stations", batch, len(stations))

            if len(stations) < MAX_BATCH_SIZE:
                break

            batch += 1
            await asyncio.sleep(0.5)

        logger.info("Total stations fetched: %d", len(all_stations))
        return all_stations
