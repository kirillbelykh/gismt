from datetime import datetime
from uuid import uuid4
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict

from app.db.session import get_db
from app.workers.cache import get_cache
from app.core.logging import get_logger
from app.schemas.camera import ScanRequest, ScanResponse, OrderScanInfo, AggregationTestRequest
from app.services.camera_service import get_camera_service
from app.services.order_service import order_service
from hashlib import md5


logger = get_logger(__name__)
router = APIRouter(prefix="/camera", tags=["camera"])

# === ОСНОВНЫЕ ENDPOINTS ===

@router.post("/scan", response_model=ScanResponse)
async def camera_scan(
    payload: ScanRequest,
    db: AsyncSession = Depends(get_db),
    cache = Depends(get_cache)
):
    """
    Принимает отсканированные коды и возвращает информацию о заказах
    """
    service = get_camera_service(db, cache)
    result = await service.scan_codes(payload.codes, payload.device_id)

    # Конвертируем в ScanResponse
    orders = []
    for order_info in result["orders"]:
        orders.append(OrderScanInfo(
            order_id=order_info["order_id"],
            order_name=order_info["order_name"],
            external_order_id=order_info["external_order_id"],
            product_name=order_info["product_name"],
            gtin=order_info["gtin"],
            quantity=len(order_info["codes"]),
            codes=order_info["codes"]
        ))

    return ScanResponse(
        orders=orders,
        total_codes=result["total_codes"],
        found_codes=result["found_codes"],
        not_found_codes=result["not_found_codes"]
    )

@router.post("/scan/aggregation", response_model=Dict)
async def camera_scan_aggregation(
    payload: ScanRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cache = Depends(get_cache)
):
    """
    БОЕВОЕ сканирование кодов и автоматическое создание агрегации.
    Контракт ответа унифицирован со scanner (main.cpp).
    """
    service = get_camera_service(db, cache)
    # 🔒 Жёсткое правило: агрегация ТОЛЬКО при ровно 10 кодах
    if len(payload.codes) != 10:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "INVALID_CODES_COUNT",
                "expected": 10,
                "received": len(payload.codes),
                "message": f"Ожидалось ровно 10 кодов, получено {len(payload.codes)}"
            }
        )

    try:
        result = await service.scan_and_aggregate(
            payload.codes,
            payload.device_id,
            background_tasks
        )

        # --- определяем бизнес-статус для scanner ---
        status = "OK"

        # коробка уже существовала (идемпотентный повтор)
        if result.get("print_status") == "already_exists":
            status = "ALREADY_EXISTS"

        # все коды уже были использованы ранее
        if result.get("box_id") == 0:
            status = "ALREADY_EXISTS"

        return {
            "success": True,
            "status": status,
            "box_id": result.get("box_id"),
            "order_id": result.get("order_id"),
            "sscc_code": result.get("sscc_code"),
            "message": result.get("message", "Агрегация выполнена")
        }

    except HTTPException as e:
        detail = e.detail

        # --- коды уже агрегированы ---
        if isinstance(detail, dict) and "already" in str(detail).lower():
            return {
                "success": True,
                "status": "ALREADY_EXISTS",
                "message": "Агрегат уже был наполнен"
            }

        # --- нет заказа ---
        if isinstance(detail, str) and "заказ" in detail.lower():
            return {
                "success": False,
                "status": "NO_ORDER",
                "message": detail
            }

        # --- ошибка валидации ---
        if e.status_code == 400:
            return {
                "success": False,
                "status": "VALIDATION_ERROR",
                "message": detail
            }

        # --- системная ошибка ---
        return {
            "success": False,
            "status": "ERROR",
            "message": "Ошибка агрегации"
        }

    except Exception as e:
        logger.error(f"❌ scan/aggregation failed: {e}")
        return {
            "success": False,
            "status": "ERROR",
            "message": "Внутренняя ошибка сервера"
        }

# in-memory storage for test only
TEST_AGGREGATIONS = {}

@router.post("/scan/aggregation/test")
async def test_aggregation(payload: AggregationTestRequest):
    if len(payload.codes) != 10:
        return {
            "success": False,
            "status": "ERROR",
            "message": "Ожидалось ровно 10 кодов",
        }
    logger.info(f"Получены коды: {payload.codes}")
    # deterministic hash (order independent)
    codes_hash = md5("".join(sorted(payload.codes)).encode()).hexdigest()

    # already scanned
    if codes_hash in TEST_AGGREGATIONS:
        box = TEST_AGGREGATIONS[codes_hash]
        return {
            "success": True,
            "status": "ALREADY_EXISTS",
            "box_id": box["box_id"],
            "order_id": box["order_id"],
            "sscc_code": box["sscc_code"],
            "print_status": "mock",
            "message": "Агрегат уже был наполнен"
        }

    # create new mock box
    box = {
        "box_id": len(TEST_AGGREGATIONS) + 1,
        "order_id": 123456,
        "sscc_code": f"TEST-SSCC-{uuid4().hex[:8]}",
        "created_at": datetime.now().isoformat()
    }

    TEST_AGGREGATIONS[codes_hash] = box

    return {
        "success": True,
        "status": "OK",
        "box_id": box["box_id"],
        "order_id": box["order_id"],
        "sscc_code": box["sscc_code"],
        "print_status": "mock",
        "message": "Агрегация выполнена (тест)"
    }

# === RESET TEST_AGGREGATIONS endpoint ===
@router.post("/scan/aggregation/test/reset")
async def reset_test_aggregations():
    """
    Сброс тестовых агрегаций (только для dev/test)
    """
    TEST_AGGREGATIONS.clear()
    return {
        "success": True,
        "message": "TEST_AGGREGATIONS сброшен"
    }

@router.post("/order-info")
async def get_order_info(
    payload: AggregationTestRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Получение информации о заказе по отсканированным кодам
    """
    order_info = await order_service.get_order_info_by_codes(
        db=db,
        raw_codes=payload.codes,
    )

    return order_info