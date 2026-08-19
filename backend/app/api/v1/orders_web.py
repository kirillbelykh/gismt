"""Web interface for order management"""
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.order_service import order_service
from app.services.datamatrix_service import datamatrix_generator
from app.services.nomenclature_service import nomenclature_service
from app.services.validation_service import FormValidationService
from app.services.html_response_service import HTMLResponseService
from app.core.logging import get_logger

from data.options import (
    SIMPLIFIED_OPTIONS, COLOR_OPTIONS, VENCHIK_OPTIONS,
    SIZE_OPTIONS, UNITS_OPTIONS, COLOR_REQUIRED, VENCHIK_REQUIRED
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/orders-web", tags=["orders-web"])
templates = Jinja2Templates(directory="app/templates")
html_service = HTMLResponseService(templates)


@router.get("/", response_class=HTMLResponse)
async def orders_page(request: Request):
    """Web interface for creating orders"""
    return templates.TemplateResponse(
        "orders.html",
        {
            "request": request,
            "simplified_options": SIMPLIFIED_OPTIONS,
            "color_options": COLOR_OPTIONS,
            "venchik_options": VENCHIK_OPTIONS,
            "size_options": SIZE_OPTIONS,
            "units_options": UNITS_OPTIONS,
            "color_required": COLOR_REQUIRED,
            "venchik_required": VENCHIK_REQUIRED,
            "default_prod_date": date.today().isoformat(),
            "default_exp_date": date.today().replace(year=date.today().year + 5).isoformat()
        }
    )


@router.post("/create", response_class=HTMLResponse)
async def create_order_web(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create order via web form"""
    try:
        # Парсинг и валидация формы
        form_data = await FormValidationService.parse_form_data(request)
        logger.info(f"Получены данные формы: {form_data}")

        # Валидация данных
        order_form, validation_error = FormValidationService.validate_form_data(form_data)
        if validation_error:
            return HTMLResponse(
                content=html_service.render_error("Ошибка валидации", validation_error),
                status_code=400
            )

        # Проверка режима (GTIN или ручной ввод)
        if not order_form.gtin and not (order_form.simpl_name and order_form.size and order_form.units_per_pack): # type: ignore
            return HTMLResponse(
                content=html_service.render_error(
                    "Недостаточно данных",
                    "Должен быть заполнен либо GTIN, либо все обязательные поля ручного ввода"
                ),
                status_code=400
            )

        # Используем order_service для создания заказа
        try:
            order, error_message, html_response = await order_service.handle_order_from_web_form(
                db=db,
                nomenclature_service=nomenclature_service,
                quantity=order_form.quantity, # type: ignore
                batch_number=order_form.batch_number, # type: ignore
                prod_date=order_form.prod_date, # type: ignore
                exp_date=order_form.exp_date, # type: ignore
                gtin=order_form.gtin, # type: ignore
                simpl_name=order_form.simpl_name, # type: ignore
                size=order_form.size, # type: ignore
                units_per_pack=order_form.units_per_pack, # type: ignore
                color=order_form.color, # type: ignore
                venchik=order_form.venchik, # type: ignore
                order_name=order_form.order_name, # type: ignore
            )

            if error_message:
                return HTMLResponse(content=html_response, status_code=400)

            # Запускаем фоновую задачу
            if order:
                order_id = getattr(order, "id")
                from app.workers.tasks import order_codes_task

                try:
                    logger.info(f"Попытка запуска задачи Celery для заказа {order_id}")
                    result = order_codes_task.delay(order_id) # type: ignore
                    logger.info(f"Задача отправлена в Celery. Task ID: {result.id}, Order ID: {order_id}")

                    # Проверьте статус сразу
                    logger.info(f"Статус задачи после отправки: {result.status}")

                except Exception as e:
                    logger.error(f"Ошибка при отправке задачи в Celery: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

            return HTMLResponse(content=html_response)

        except Exception as service_error:
            logger.exception(f"Ошибка в order_service: {service_error}")
            return HTMLResponse(
                content=html_service.render_error(
                    "Ошибка сервиса",
                    str(service_error)
                ),
                status_code=500
            )

    except Exception as e:
        logger.exception(f"Непредвиденная ошибка создания заказа: {e}")
        return HTMLResponse(
            content=html_service.render_error(
                "Внутренняя ошибка сервера",
                "Произошла непредвиденная ошибка. Пожалуйста, попробуйте еще раз.",
                str(e)
            ),
            status_code=500
        )

@router.post("/delete/{order_id}")
async def delete_order_web(
    order_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete order with all related data"""
    try:
        close_order, message = await order_service.close_order(db, order_id)
        if close_order and "успешно закрыт" in message:
            success = await order_service.delete_order(db, order_id)
            if success:
                return JSONResponse(
                    status_code=200,
                    content={"success": True, "message": "Order deleted successfully"}
                )
            else:
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "error": "order not found"}
                )
        else:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": f"Cannot delete order: {message}"}
            )
    except Exception as e:
        logger.exception(f"Ошибка при удалении заказа {order_id}: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Internal server error: {str(e)}"}
        )

@router.post("/close/{order_id}")
async def close_order_web(
    order_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Close order in SUZ"""
    try:
        success = await order_service.close_order(db, order_id)
        if success:
            return JSONResponse(
                status_code=200,
                content={"success": True, "message": "Order closed successfully"}
            )
        else:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "order not found"}
            )
    except Exception as e:
        logger.exception(f"Ошибка при закрытии заказа {order_id}: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Internal server error"}
        )

@router.get("/search-by-gtin")
async def search_by_gtin(gtin: str):
    """
    Поиск позиции по GTIN ТОЛЬКО в Excel-файле номенклатуры
    """
    if not gtin or not gtin.strip():
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "GTIN не может быть пустым"}
        )

    try:
        full_name, simpl_name = nomenclature_service.lookup_by_gtin(gtin)
        if full_name and simpl_name:
            return {
                "success": True,
                "data": {
                    "gtin": gtin,
                    "full_name": full_name,
                    "simpl_name": simpl_name
                }
            }
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="GTIN не найден в номенклатуре"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка поиска по GTIN {gtin}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при поиске GTIN: {str(e)}"
        )


@router.get("/list")
async def list_orders_web(
    db: AsyncSession = Depends(get_db),
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 20
):
    """List all orders in JSON format"""
    try:
        orders = await order_service.get_all_orders_with_products(
            db, skip=skip, limit=limit
        )

        status_map = {
            "READY": "ГОТОВ",
            "PROCESSING": "В ПРОЦЕССЕ",
            "PENDING": "ОЖИДАЕТ",
            "ORDERING": "ЗАКАЗЫВАЕТСЯ",
            "ERROR": "ОШИБКА",
            "CLOSED": "ЗАКРЫТ",
            "AGGREGATING": "ВЫПОЛНЯЕТСЯ АГРЕГАЦИЯ",
            "AGGREGATED": "АГРЕГИРОВАН",
            "IN_CIRCULATION": "ВВЕДЕН В ОБОРОТ",
        }

        orders_data = []

        for order in orders:
            try:
                # --- fallback статус из order.status (если понадобится) ---
                raw_status = None
                order_status = getattr(order, "status", None)
                if order_status:
                    raw_status = (
                        order_status.value
                        if hasattr(order_status, "value")
                        else str(order_status)
                    )

                # --- ВАЖНО: получаем UI-статус через сервис ---
                status_value = await order_service.get_order_ui_status(
                    db=db,
                    order_id=order.id,
                    fallback_status=raw_status,
                )

                # --- Номер партии ---
                batch_number = "Не указан"
                if getattr(order, "batch", None) and getattr(order.batch, "batch_number", None):
                    batch_number = order.batch.batch_number
                elif getattr(order, "batch", None):
                    batch_number = f"Партия ID: {order.batch.id}"

                # --- Дата создания ---
                created_at_str = "Не указано"
                if getattr(order, "created_at", None):
                    created_at_str = order.created_at.strftime('%Y-%m-%d %H:%M')

                normalized_status = str(status_value).upper()

                orders_data.append({
                    "id": order.id,
                    "name": getattr(order, "name", "").strip() or "Без названия",
                    "status": normalized_status,
                    "status_display": status_map.get(normalized_status, normalized_status),
                    "qty": getattr(order, "qty", 0),
                    "batch_number": batch_number,
                    "created_at": created_at_str,
                    "is_ready": normalized_status == "READY",
                })

            except Exception as order_error:
                logger.error(
                    f"Ошибка обработки заказа {getattr(order, 'id', 'unknown')}: {order_error}",
                    exc_info=True
                )
                orders_data.append({
                    "id": getattr(order, "id", None),
                    "name": f"Заказ #{getattr(order, 'id', 'unknown')} (ошибка)",
                    "status": "ERROR",
                    "status_display": "ОШИБКА",
                    "qty": 0,
                    "batch_number": "Ошибка",
                    "created_at": "",
                    "is_ready": False,
                    "error": str(order_error),
                })

        # --- Фильтрация поиска ---
        if search:
            search_lower = search.lower()
            orders_data = [
                order for order in orders_data
                if (
                    search_lower in str(order.get("name", "")).lower()
                    or search_lower in str(order.get("batch_number", "")).lower()
                    or search_lower in str(order.get("status_display", "")).lower()
                    or search_lower in str(order.get("id", ""))
                    or search_lower in str(order.get("qty", ""))
                )
            ]

        return {
            "success": True,
            "data": orders_data,
            "total": len(orders_data),
            "has_more": len(orders) == limit,
        }

    except Exception as e:
        logger.exception(f"Ошибка при получении списка заказов: {e}")
        return {
            "success": False,
            "error": str(e),
            "data": [],
        }

@router.get("/{order_id}/view", response_class=HTMLResponse)
async def view_order_with_codes_html(
    order_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """View order codes in HTML format"""
    try:
        order_data, codes = await order_service.prepare_order_for_view(db, order_id)

        if not order_data:
            raise HTTPException(status_code=404, detail="Order not found")

        return templates.TemplateResponse(
            "order_codes.html",
            {
                "request": request,
                "order": order_data,
                "codes": codes
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Ошибка при отображении заказа {order_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.get("/{order_id}/pdf-datamatrix")
async def get_order_codes_pdf_datamatrix(
    order_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Generate minimal PDF with Data-Matrix codes only"""
    try:
        order = await order_service.get_order(db, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        if getattr(order, "status") != 'ready':
            raise HTTPException(status_code=400, detail="Codes not ready")

        codes = await order_service.get_order_codes(db, order_id)

        if not codes:
            raise HTTPException(status_code=400, detail="No codes available")

        return datamatrix_generator.create_minimal_pdf_response(
            codes=codes,
            order_id=getattr(order, "id"),
            order_name=getattr(order, "name") or ""
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Ошибка генерации PDF для заказа {order_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка генерации PDF: {str(e)}"
        )


@router.get("/{order_id}/csv-datamatrix")
async def get_order_codes_csv_datamatrix(
    order_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    CSV выгрузка кодов DataMatrix для заказа.
    ⚠️ ВРЕМЕННО: заглушка, сервис будет добавлен позже.
    """
    # 1️⃣ Получаем заказ
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # 2️⃣ Проверяем готовность кодов
    if getattr(order, "status") != "ready":
        raise HTTPException(status_code=400, detail="Codes not ready")

    # 3️⃣ Получаем коды заказа
    codes = await order_service.get_order_codes(db, order_id)
    if not codes:
        raise HTTPException(status_code=400, detail="No codes available")

    # 4️⃣ Генерируем CSV через сервис
    return datamatrix_generator.create_codes_csv_response(
        codes=codes,
        order_id=order_id
    )
