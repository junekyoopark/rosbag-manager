from redis.asyncio import Redis
from app.config import settings

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client


ONLINE_TTL = 300  # seconds — user considered online if seen within this window


async def mark_online(user_id: str) -> None:
    await get_redis().setex(f"online:{user_id}", ONLINE_TTL, "1")


async def get_online_user_ids() -> set[str]:
    r = get_redis()
    keys = await r.keys("online:*")
    return {k.removeprefix("online:") for k in keys}
