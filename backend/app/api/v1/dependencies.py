from typing import Any, Dict, Optional
import json
from fastapi import Depends, HTTPException
from app.workers.cache import get_cache, Cache

# === КЭШ ЗАВИСИМОСТИ ===

async def get_cached_data(key: str, cache: Cache = Depends(get_cache)) -> Optional[Any]:
    """Зависимость для получения данных из кэша"""
    data = await cache.get(key)
    if data:
        return json.loads(data)
    return None


async def set_cached_data(
    key: str,
    value: Any,
    expire: int = 300,
    cache: Cache = Depends(get_cache)
):
    """Зависимость для сохранения данных в кэш"""
    await cache.setex(key, expire, json.dumps(value))


async def delete_cached_data(key: str, cache: Cache = Depends(get_cache)):
    """Зависимость для удаления данных из кэша"""
    await cache.delete(key)


# === КОМПОЗИЦИОННЫЕ ЗАВИСИМОСТИ ===

async def get_camera_last_scan(
    device_id: str,
    cache: Cache = Depends(get_cache)
) -> Optional[Dict[str, Any]]:
    """
    Получение последнего результата сканирования для устройства
    """
    cache_key = f"camera:{device_id}:last_scan"
    return await get_cached_data(cache_key, cache)


async def cache_camera_scan(
    device_id: str,
    result: Dict[str, Any],
    cache: Cache = Depends(get_cache)
):
    """
    Кэширование результата сканирования
    """
    cache_key = f"camera:{device_id}:last_scan"
    await set_cached_data(cache_key, result, expire=300)


async def get_or_create_cache_lock(
    key: str,
    cache: Cache = Depends(get_cache)
) -> bool:
    """
    Получение или создание блокировки в кэше
    Возвращает True, если блокировка создана, False если уже существует
    """
    existing = await cache.get(key)
    if existing:
        return False

    await cache.setex(key, 30, "locked")
    return True


async def release_cache_lock(
    key: str,
    cache: Cache = Depends(get_cache)
):
    """
    Освобождение блокировки в кэше
    """
    await cache.delete(key)


# === ПРОВЕРКИ ДЛЯ ENDPOINTS ===

async def check_duplicate_request(
    request_type: str,
    device_id: str,
    data_hash: str,
    cache: Cache = Depends(get_cache)
):
    """
    Проверка на дублирующие запросы
    """
    request_key = f"{request_type}_request:{device_id}:{data_hash}"

    # Проверяем существующую блокировку
    lock_key = f"lock:{request_key}"
    is_locked = await get_or_create_cache_lock(lock_key, cache)

    if not is_locked:
        raise HTTPException(
            status_code=429,
            detail="Такой запрос уже обрабатывается. Пожалуйста, подождите 30 секунд."
        )

    return {"request_key": request_key, "lock_key": lock_key}
