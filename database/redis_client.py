import asyncio
import json
from typing import Optional

import redis.asyncio as aioredis

from config.settings import settings
from utils.logger import logger

_CONV_PREFIX = "conv:"
_RETRY_COUNT = 3
_RETRY_DELAY = 2  # seconds


class RedisClient:
    def __init__(self) -> None:
        self._client: Optional[aioredis.Redis] = None

    @property
    def client(self) -> aioredis.Redis:
        if self._client is None:
            raise RuntimeError("Redis not connected — call connect() first")
        return self._client

    async def connect(self) -> None:
        """Open the connection pool, retrying up to 3 times on failure."""
        for attempt in range(1, _RETRY_COUNT + 1):
            try:
                client = aioredis.from_url(
                    settings.redis_url,
                    password=settings.redis_password or None,
                    decode_responses=True,
                )
                await client.ping()
                self._client = client
                logger.info("Redis connected")
                return
            except Exception as exc:
                logger.warning(f"Redis connect attempt {attempt}/{_RETRY_COUNT} failed: {exc}")
                if attempt < _RETRY_COUNT:
                    await asyncio.sleep(_RETRY_DELAY)

        raise RuntimeError(
            f"Redis unavailable after {_RETRY_COUNT} attempts — check REDIS_URL in .env"
        )

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("Redis disconnected")

    # ── Conversation state ───────────────────────────────────────────────────

    async def get_conversation_state(self, phone_number: str) -> dict | None:
        """Return the stored conversation state dict, or None if absent/expired."""
        raw = await self.client.get(f"{_CONV_PREFIX}{phone_number}")
        if raw is None:
            return None
        return json.loads(raw)

    async def set_conversation_state(
        self,
        phone_number: str,
        state: dict,
        ttl_minutes: int | None = None,
    ) -> None:
        """Persist state as JSON with a TTL (defaults to settings value)."""
        ttl_seconds = (ttl_minutes or settings.session_conversation_timeout_minutes) * 60
        await self.client.setex(
            f"{_CONV_PREFIX}{phone_number}",
            ttl_seconds,
            json.dumps(state),
        )

    async def clear_conversation_state(self, phone_number: str) -> None:
        """Delete the conversation state key immediately."""
        await self.client.delete(f"{_CONV_PREFIX}{phone_number}")

    async def health_check(self) -> bool:
        """Ping Redis; returns True if reachable."""
        try:
            return await self.client.ping()
        except Exception:
            return False


redis_client = RedisClient()
