from fastapi import HTTPException
from typing import Any
import time

DEFAULT_LOCK_TTL = 30  # seconds


async def acquire_cache_lock(
    key: str,
    cache: Any,
    ttl: int = DEFAULT_LOCK_TTL,
) -> None:
    """Приобретает блокировку в Redis или in-memory кэше"""

    # Проверяем, поддерживает ли cache метод acquire_lock
    if hasattr(cache, "acquire_lock"):
        acquired = await cache.acquire_lock(key, ttl)
        if not acquired:
            raise HTTPException(
                status_code=429,
                detail="Этот набор кодов уже обрабатывается другим запросом. Пожалуйста, подождите."
            )
        return

    # Fallback для старого интерфейса
    if hasattr(cache, "set"):
        try:
            # Пробуем установить блокировку
            result = await cache.set(key, "processing", nx=True, ex=ttl)
            if not result:
                raise HTTPException(
                    status_code=429,
                    detail="Запрос уже обрабатывается, повторите позже"
                )
            return
        except Exception as e:
            # Если не поддерживается nx/ex, используем простую проверку
            existing = await cache.get(key)
            if existing:
                raise HTTPException(
                    status_code=429,
                    detail="Запрос уже обрабатывается, повторите позже"
                )
            await cache.set(key, "processing")
            return

    # Если ничего не работает, пропускаем блокировку
    print(f"⚠️ Неизвестный тип cache для блокировки: {type(cache)}")


async def release_cache_lock(key: str, cache: Any) -> None:
    """Освобождает блокировку"""
    try:
        if hasattr(cache, "delete"):
            await cache.delete(key)
        elif hasattr(cache, "release_lock"):
            await cache.release_lock(key)
    except Exception as e:
        print(f"⚠️ Ошибка при снятии блокировки {key}: {e}")