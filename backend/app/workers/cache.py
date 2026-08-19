from __future__ import annotations

from typing import Dict, Any, Optional
import time
import json
from app.core.logging import get_logger

logger = get_logger(__name__)


class Cache:
    """Единая асинхронная абстракция кэша.

    Поддерживает два режима:
    - redis (предпочтительно)
    - in-memory (fallback)

    ВАЖНО: интерфейс специально сделан одинаковым для обоих режимов,
    чтобы НИГДЕ в коде не проверять тип кэша.
    """

    def __init__(self) -> None:
        self.type: str
        self.client: Any | None
        self._memory_cache: Dict[str, Dict[str, Any]]
        self._init_cache()

    # ===================== INIT =====================

    def _init_cache(self) -> None:
        try:
            import redis.asyncio as redis

            self.client = redis.from_url(
                "redis://redis:6379",
                decode_responses=True,
            )
            self.type = "redis"
            self._memory_cache = {}
            logger.info("Redis cache initialized")
        except Exception as e:
            logger.warning(f"Redis недоступен ({e}), используем in-memory cache")
            self.client = None
            self.type = "memory"
            self._memory_cache = {}

    # ===================== BASIC OPS =====================

    async def get(self, key: str) -> Optional[str]:
        if self.type == "redis" and self.client:
            return await self.client.get(key)
        return self._memory_cache.get(key, {}).get('value')

    async def set(self, key: str, value: str, **kwargs) -> bool:
        """
        Установка значения с поддержкой nx (not exist) и ex (expire)
        Возвращает True если значение установлено, False если уже существует (при nx=True)
        """
        nx = kwargs.get('nx', False)
        ex = kwargs.get('ex')

        if self.type == "redis" and self.client:
            if nx and ex:
                return bool(await self.client.set(key, value, nx=True, ex=ex))
            elif nx:
                return bool(await self.client.set(key, value, nx=True))
            elif ex:
                await self.client.setex(key, ex, value)
                return True
            else:
                await self.client.set(key, value)
                return True
        else:
            # in-memory реализация
            if nx and key in self._memory_cache:
                return False

            entry = {'value': value, 'expires_at': None}
            if ex:
                entry['expires_at'] = time.time() + ex
                # Очистка просроченных записей
                self._clean_expired()

            self._memory_cache[key] = entry
            return True

    async def setex(self, key: str, expire: int, value: str) -> None:
        if self.type == "redis" and self.client:
            await self.client.setex(key, expire, value)
        else:
            entry = {'value': value, 'expires_at': time.time() + expire}
            self._memory_cache[key] = entry

    async def delete(self, key: str) -> None:
        if self.type == "redis" and self.client:
            await self.client.delete(key)
        else:
            self._memory_cache.pop(key, None)

    async def exists(self, key: str) -> bool:
        if self.type == "redis" and self.client:
            return bool(await self.client.exists(key))
        else:
            self._clean_expired()
            return key in self._memory_cache

    async def keys(self, pattern: str) -> list[str]:
        if self.type == "redis" and self.client:
            return list(await self.client.keys(pattern))

        # simple prefix matching for in-memory
        self._clean_expired()
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return [k for k in self._memory_cache if k.startswith(prefix)]
        return [k for k in self._memory_cache if k == pattern]

    # ===================== LOCK HELPERS =====================

    def _clean_expired(self):
        """Очистка просроченных записей в памяти"""
        now = time.time()
        expired = []
        for key, entry in self._memory_cache.items():
            if entry.get('expires_at') and entry['expires_at'] < now:
                expired.append(key)
        for key in expired:
            del self._memory_cache[key]

    async def acquire_lock(self, key: str, ttl: int) -> bool:
        """Атомарная блокировка.

        Возвращает True, если блокировка получена,
        False — если уже существует.
        """
        if self.type == "redis" and self.client:
            # SET key value NX EX ttl
            return bool(await self.client.set(key, "1", nx=True, ex=ttl))

        # in-memory fallback
        self._clean_expired()
        now = time.time()

        if key in self._memory_cache:
            entry = self._memory_cache[key]
            expires_at = entry.get('expires_at')
            if expires_at and expires_at > now:
                return False

        self._memory_cache[key] = {
            'value': '1',
            'expires_at': now + ttl
        }
        return True

    async def release_lock(self, key: str) -> None:
        await self.delete(key)


# ===================== SINGLETON =====================

_cache_instance: Cache | None = None


async def get_cache() -> Cache:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = Cache()
    return _cache_instance