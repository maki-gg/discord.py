"""
The MIT License (MIT)

Copyright (c) 2015-present Rapptz

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

_log = logging.getLogger(__name__)

__all__ = ('RedisCacheOptions', 'RedisCache')

# Keys stripped from the gateway GUILD_CREATE payload before storing guild base data.
# Sub-entities live in their own HASH keys; ephemeral data is not persisted.
GUILD_BASE_STRIP_KEYS: frozenset = frozenset({
    'roles',
    'emojis',
    'stickers',
    'members',
    'channels',
    'threads',
    'presences',
    'voice_states',
    'stage_instances',
    'guild_scheduled_events',
})


class RedisCacheOptions:
    """Configuration for the Redis guild cache.

    Pass an instance of this class as the ``redis_cache`` keyword argument to
    :class:`discord.ext.commands.Bot` to enable Redis-backed guild caching.

    Parameters
    ----------
    uri: :class:`str`
        The Redis connection URI, e.g. ``redis://localhost:6379``.
    guild_ttl: :class:`int`
        Seconds before the guild base data expires. Defaults to ``86400`` (24 hours).
    member_ttl: :class:`int`
        Seconds before member data expires. Defaults to ``21600`` (6 hours).
        Members are the largest sub-entity per guild; active guilds stay refreshed
        by gateway events so only truly silent guilds will reach this limit.
    channel_ttl: :class:`int`
        Seconds before channel data expires. Defaults to ``86400`` (24 hours).
    role_ttl: :class:`int`
        Seconds before role data expires. Defaults to ``86400`` (24 hours).
    thread_ttl: :class:`int`
        Seconds before thread data expires. Defaults to ``3600`` (1 hour).
    emoji_ttl: :class:`int`
        Seconds before emoji data expires. Defaults to ``86400`` (24 hours).
    sticker_ttl: :class:`int`
        Seconds before sticker data expires. Defaults to ``86400`` (24 hours).
    max_memory_guilds: Optional[:class:`int`]
        Maximum number of guilds to keep fully loaded in memory at once.
        When this limit is exceeded the least-recently-used guilds are
        unloaded to Redis.  ``None`` disables LRU eviction. Defaults to
        ``None``.
    """

    __slots__ = (
        'uri',
        'guild_ttl',
        'member_ttl',
        'channel_ttl',
        'role_ttl',
        'thread_ttl',
        'emoji_ttl',
        'sticker_ttl',
        'max_memory_guilds',
    )

    def __init__(
        self,
        uri: str,
        *,
        guild_ttl: int = 86400,
        member_ttl: int = 21600,
        channel_ttl: int = 86400,
        role_ttl: int = 86400,
        thread_ttl: int = 3600,
        emoji_ttl: int = 86400,
        sticker_ttl: int = 86400,
        max_memory_guilds: Optional[int] = None,
    ) -> None:
        self.uri: str = uri
        self.guild_ttl: int = guild_ttl
        self.member_ttl: int = member_ttl
        self.channel_ttl: int = channel_ttl
        self.role_ttl: int = role_ttl
        self.thread_ttl: int = thread_ttl
        self.emoji_ttl: int = emoji_ttl
        self.sticker_ttl: int = sticker_ttl
        self.max_memory_guilds: Optional[int] = max_memory_guilds

    def __repr__(self) -> str:
        return (
            f'<RedisCacheOptions uri={self.uri!r} guild_ttl={self.guild_ttl} '
            f'member_ttl={self.member_ttl} max_memory_guilds={self.max_memory_guilds}>'
        )


class RedisCache:
    """Backing store for the discord.py guild cache using Redis.

    All sub-entity collections (members, channels, roles, threads, emojis,
    stickers) are stored as Redis HASHes keyed by entity ID.  The guild base
    data (scalar fields only) is stored as a STRING (JSON).  Each collection
    has its own TTL so large member lists can expire sooner than stable data
    like channels or roles.

    Key schema::

        guild:{id}            STRING  – guild base JSON (no sub-entities)
        guild:{id}:roles      HASH    – role_id  → role JSON
        guild:{id}:channels   HASH    – channel_id → channel JSON
        guild:{id}:members    HASH    – user_id  → member JSON
        guild:{id}:threads    HASH    – thread_id → thread JSON
        guild:{id}:emojis     HASH    – emoji_id  → emoji JSON
        guild:{id}:stickers   HASH    – sticker_id → sticker JSON
    """

    __slots__ = (
        '_uri',
        '_client',
        'guild_ttl',
        'member_ttl',
        'channel_ttl',
        'role_ttl',
        'thread_ttl',
        'emoji_ttl',
        'sticker_ttl',
    )

    def __init__(self, options: RedisCacheOptions) -> None:
        try:
            import redis.asyncio as aioredis  # noqa: F401
        except ImportError:
            raise RuntimeError(
                'redis package is required for Redis caching. '
                'Install it with: pip install "discord.py[redis]"'
            ) from None

        self._uri: str = options.uri
        self._client: Optional[Any] = None
        self.guild_ttl: int = options.guild_ttl
        self.member_ttl: int = options.member_ttl
        self.channel_ttl: int = options.channel_ttl
        self.role_ttl: int = options.role_ttl
        self.thread_ttl: int = options.thread_ttl
        self.emoji_ttl: int = options.emoji_ttl
        self.sticker_ttl: int = options.sticker_ttl

    async def connect(self) -> None:
        import redis.asyncio as aioredis

        self._client = aioredis.from_url(self._uri, decode_responses=True)
        await self._client.ping()
        _log.debug('Redis cache connected to %s', self._uri)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            _log.debug('Redis cache connection closed')

    @property
    def client(self) -> Any:
        if self._client is None:
            raise RuntimeError('RedisCache is not connected.')
        return self._client

    # ------------------------------------------------------------------
    # Guild base (STRING key)
    # ------------------------------------------------------------------

    async def set_guild_base(self, guild_id: int, data: Dict[str, Any]) -> None:
        await self.client.set(f'guild:{guild_id}', json.dumps(data), ex=self.guild_ttl)

    async def get_guild_base(self, guild_id: int) -> Optional[Dict[str, Any]]:
        raw = await self.client.get(f'guild:{guild_id}')
        return json.loads(raw) if raw is not None else None

    async def delete_guild(self, guild_id: int) -> None:
        pipe = self.client.pipeline()
        for suffix in ('', ':roles', ':channels', ':members', ':threads', ':emojis', ':stickers'):
            pipe.delete(f'guild:{guild_id}{suffix}')
        await pipe.execute()

    # ------------------------------------------------------------------
    # Generic HASH helpers
    # ------------------------------------------------------------------

    async def _hset_one(self, key: str, field: int, data: Dict[str, Any], ttl: int) -> None:
        pipe = self.client.pipeline()
        pipe.hset(key, str(field), json.dumps(data))
        pipe.expire(key, ttl)
        await pipe.execute()

    async def _hdel_one(self, key: str, field: int) -> None:
        await self.client.hdel(key, str(field))

    async def _hset_bulk(self, key: str, mapping: Dict[int, Dict[str, Any]], ttl: int) -> None:
        if not mapping:
            return
        pipe = self.client.pipeline()
        pipe.hset(key, mapping={str(k): json.dumps(v) for k, v in mapping.items()})
        pipe.expire(key, ttl)
        await pipe.execute()

    async def _hgetall(self, key: str) -> Dict[str, Dict[str, Any]]:
        raw: Dict[str, str] = await self.client.hgetall(key)
        return {k: json.loads(v) for k, v in raw.items()}

    async def _replace_hash(self, key: str, mapping: Dict[int, Dict[str, Any]], ttl: int) -> None:
        """Delete the existing HASH and write a fresh one atomically."""
        pipe = self.client.pipeline()
        pipe.delete(key)
        if mapping:
            pipe.hset(key, mapping={str(k): json.dumps(v) for k, v in mapping.items()})
            pipe.expire(key, ttl)
        await pipe.execute()

    # ------------------------------------------------------------------
    # Per-entity-type methods
    # ------------------------------------------------------------------

    async def set_role(self, guild_id: int, role_id: int, data: Dict[str, Any]) -> None:
        await self._hset_one(f'guild:{guild_id}:roles', role_id, data, self.role_ttl)

    async def set_roles_bulk(self, guild_id: int, roles: Dict[int, Dict[str, Any]]) -> None:
        await self._hset_bulk(f'guild:{guild_id}:roles', roles, self.role_ttl)

    async def delete_role(self, guild_id: int, role_id: int) -> None:
        await self._hdel_one(f'guild:{guild_id}:roles', role_id)

    async def get_roles(self, guild_id: int) -> Dict[str, Dict[str, Any]]:
        return await self._hgetall(f'guild:{guild_id}:roles')

    async def set_channel(self, guild_id: int, channel_id: int, data: Dict[str, Any]) -> None:
        await self._hset_one(f'guild:{guild_id}:channels', channel_id, data, self.channel_ttl)

    async def set_channels_bulk(self, guild_id: int, channels: Dict[int, Dict[str, Any]]) -> None:
        await self._hset_bulk(f'guild:{guild_id}:channels', channels, self.channel_ttl)

    async def delete_channel(self, guild_id: int, channel_id: int) -> None:
        await self._hdel_one(f'guild:{guild_id}:channels', channel_id)

    async def get_channels(self, guild_id: int) -> Dict[str, Dict[str, Any]]:
        return await self._hgetall(f'guild:{guild_id}:channels')

    async def set_member(self, guild_id: int, user_id: int, data: Dict[str, Any]) -> None:
        await self._hset_one(f'guild:{guild_id}:members', user_id, data, self.member_ttl)

    async def set_members_bulk(self, guild_id: int, members: Dict[int, Dict[str, Any]]) -> None:
        await self._hset_bulk(f'guild:{guild_id}:members', members, self.member_ttl)

    async def delete_member(self, guild_id: int, user_id: int) -> None:
        await self._hdel_one(f'guild:{guild_id}:members', user_id)

    async def get_members(self, guild_id: int) -> Dict[str, Dict[str, Any]]:
        return await self._hgetall(f'guild:{guild_id}:members')

    async def set_thread(self, guild_id: int, thread_id: int, data: Dict[str, Any]) -> None:
        await self._hset_one(f'guild:{guild_id}:threads', thread_id, data, self.thread_ttl)

    async def set_threads_bulk(self, guild_id: int, threads: Dict[int, Dict[str, Any]]) -> None:
        await self._hset_bulk(f'guild:{guild_id}:threads', threads, self.thread_ttl)

    async def delete_thread(self, guild_id: int, thread_id: int) -> None:
        await self._hdel_one(f'guild:{guild_id}:threads', thread_id)

    async def get_threads(self, guild_id: int) -> Dict[str, Dict[str, Any]]:
        return await self._hgetall(f'guild:{guild_id}:threads')

    async def set_emojis(self, guild_id: int, emojis: Dict[int, Dict[str, Any]]) -> None:
        await self._replace_hash(f'guild:{guild_id}:emojis', emojis, self.emoji_ttl)

    async def get_emojis(self, guild_id: int) -> Dict[str, Dict[str, Any]]:
        return await self._hgetall(f'guild:{guild_id}:emojis')

    async def set_stickers(self, guild_id: int, stickers: Dict[int, Dict[str, Any]]) -> None:
        await self._replace_hash(f'guild:{guild_id}:stickers', stickers, self.sticker_ttl)

    async def get_stickers(self, guild_id: int) -> Dict[str, Dict[str, Any]]:
        return await self._hgetall(f'guild:{guild_id}:stickers')
