"""
Production-ready Celery tasks for CRPT integration
Исправленная версия: убраны @app.task с классов + корректная регистрация через register_task()
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from app.workers.base_task import AsyncDatabaseTask
from app.workers.celery_app import app
from app.services.order_service import order_service
from app.services.aggregation_service import aggregation_service
from app.services.introduction_service import introduction_service
from app.services.apply_service import apply_service
from app.services.crpt_client_service import CRPTClient
from app.core.logging import get_logger
from app.db.models.order import Order, OrderStatus
from app.db.models.marking_code import MarkingCodeStatus
from app.db.models.box import Box, BoxStatus
from app.db.models.box_item import BoxItem
from app.db.models.task_log import TaskLog, TaskStatus
from sqlalchemy.ext.asyncio import AsyncSession
logger = get_logger(__name__)
# =============================================================================
# 1. Заказ кодов маркировки
# =============================================================================
class OrderCodesTask(AsyncDatabaseTask):
    async def execute_async(self, db: AsyncSession, order_id: int):
        result = await db.execute(
            select(Order)
            .options(selectinload(Order.product))
            .where(Order.id == order_id)
            .with_for_update()
        )
        order = result.scalar_one_or_none()
        if not order:
            raise ValueError(f"Order {order_id} not found")
        if not order.product:
            raise ValueError(f"Product not found for order {order_id}")
        crpt_client = CRPTClient()
        logger.info(f"Creating emission order :: GTIN={order.product.gtin} qty={order.qty}")
        products = [{
            "gtin": order.product.gtin,
            "quantity": order.qty,
            "serialNumberType": "OPERATOR",
            "templateId": 12,
            "cisType": "UNIT",
        }]
        attributes = {
            "releaseMethodType": "PRODUCTION",
            "createMethodType": "SELF_MADE",
            "productionOrderId": order.name or f"ORDER-{order.id}",
            "paymentType": 2,
        }
        try:
            external_order_id = await asyncio.wait_for(
                crpt_client.create_emission_order(
                    product_group="wheelchairs",
                    products=products,
                    attributes=attributes,
                ),
                timeout=60,
            )
        except asyncio.TimeoutError:
            logger.error(f"Timeout creating emission order for order {order_id}")
            raise TimeoutError("CRPT create_emission_order timeout")
        order.external_order_id = external_order_id
        await db.commit()
        try:
            quantity, gtin = await asyncio.wait_for(
                crpt_client.wait_for_codes(external_order_id, timeout=300, interval=10),
                timeout=320,
            )
        except asyncio.TimeoutError:
            logger.error(f"Timeout waiting for codes (order {order_id})")
            raise TimeoutError("CRPT wait_for_codes timeout")
        try:
            block_id, codes = await asyncio.wait_for(
                crpt_client.get_codes(external_order_id, quantity=order.qty, gtin=str(gtin)),
                timeout=120,
            )
        except asyncio.TimeoutError:
            logger.error(f"Timeout getting codes (order {order_id})")
            raise TimeoutError("CRPT get_codes timeout")
        await order_service.store_codes(db, order_id, codes)
        await order_service.update_order_status(db, order_id, OrderStatus.READY)
        logger.info(f"Successfully generated {len(codes)} codes for order {order_id}")
        return {
            "order_id": order_id,
            "codes_generated": len(codes),
            "external_order_id": external_order_id,
            "block_id": block_id,
        }
# =============================================================================
# 2. Отчёт о нанесении (apply)
# =============================================================================
class SendApplyReportTask(AsyncDatabaseTask):
    async def execute_async(self, db: AsyncSession, box_id: int):
        result = await db.execute(
            select(Box)
            .options(selectinload(Box.order))
            .where(Box.id == box_id)
            .with_for_update()
        )
        box = result.scalar_one_or_none()
        if not box:
            raise ValueError(f"Box {box_id} not found")
        response = await apply_service.send_apply_report(db, box.id)
        report_id = response.get("reportId")
        if not report_id:
            raise ValueError("No reportId in CRPT response")
        max_wait, interval = 180, 5
        last_state = None
        for attempt in range(max_wait // interval):
            status = await CRPTClient().get_utilisation_report_status(report_id)
            state = status.get("state") or status.get("reportStatus") or status.get("status", "UNKNOWN")
            self.update_state(
                state="PROGRESS",
                meta={
                    "current": attempt * interval,
                    "total": max_wait,
                    "status": f"waiting_report_{state}",
                    "box_id": box_id,
                    "report_id": report_id,
                },
            )
            if state != last_state:
                logger.info(f"Box {box_id} apply report → {state}")
                last_state = state
            if state in ("SENT", "COMPLETED", "OK", "ACCEPTED", "DONE", "ACCEPTED_BY_CRPT"):
                break
            if state in ("FAILED", "ERROR", "REJECTED", "CANCELLED"):
                raise Exception(f"Apply report failed: {state}")
            await asyncio.sleep(interval)
        else:
            raise TimeoutError("Apply report timeout")
        await aggregation_service.update_statuses(db, box.id, "applied")
        await db.commit()
        logger.info(f"Box {box_id} apply report accepted")
        await self._launch_next_task(
            "app.workers.tasks.SendAggregationReportTask",
            [box.id]
        )
        return {"box_id": box_id, "report_id": report_id, "status": "apply_sent"}
# =============================================================================
# 3. Отчёт об агрегации
# =============================================================================
class SendAggregationReportTask(AsyncDatabaseTask):
    async def execute_async(self, db: AsyncSession, box_id: int):
        result = await db.execute(
            select(Box)
            .options(selectinload(Box.order))
            .where(Box.id == box_id)
            .with_for_update()
        )
        box = result.scalar_one_or_none()
        if not box:
            raise ValueError(f"Box {box_id} not found")
        items_result = await db.execute(
            select(BoxItem)
            .where(BoxItem.box_id == box.id)
            .options(selectinload(BoxItem.marking_code))
        )
        items = items_result.scalars().all()
        raw_codes = [
            item.marking_code.code_raw
            for item in items
            if item.marking_code and item.marking_code.code_raw
        ]
        if not raw_codes:
            raise ValueError(f"No valid codes in box {box_id}")
        logger.info(f"Sending aggregation report for SSCC {box.sscc} ({len(raw_codes)} codes)")
        await CRPTClient().send_aggregation_report(
            product_group="wheelchairs",
            participant_id="7843316794",
            sntins=raw_codes,
            sscc=str(box.sscc),
            aggregated_items_count=len(raw_codes),
        )
        max_wait, interval = 300, 10
        sscc_str = str(box.sscc)
        for attempt in range(max_wait // interval):
            found, status = await CRPTClient().check_aggregation_code_status(sscc_str)
            self.update_state(
                state="PROGRESS",
                meta={
                    "current": attempt * interval,
                    "total": max_wait,
                    "status": "found" if found else "not_found",
                    "sscc": sscc_str,
                },
            )
            if found and status in ("INTRODUCED", "AGGREGATED", "APPLIED", "ACTIVE"):
                break
            await asyncio.sleep(interval)
        else:
            logger.warning(f"SSCC {sscc_str} not registered in time")
        await aggregation_service.update_statuses(db, box.id, "aggregated")
        await db.commit()
        logger.info(f"Box {box_id} aggregated")
        await self._launch_next_task(
            "app.workers.tasks.SendIntroductionTask",
            [box.id]
        )
        return {"box_id": box_id, "sscc": sscc_str, "status": "aggregated"}
# =============================================================================
# 4. Ввод в оборот
# =============================================================================
class SendIntroductionTask(AsyncDatabaseTask):
    async def execute_async(self, db: AsyncSession, box_id: int):
        result = await db.execute(
            select(Box)
            .options(selectinload(Box.order))
            .where(Box.id == box_id)
            .with_for_update()
        )
        box = result.scalar_one_or_none()
        if not box:
            raise ValueError(f"Box {box_id} not found")
        response = await introduction_service.send_introduction(db, box.id)
        if not response.get("success"):
            error = response.get("error", "Unknown")
            raise Exception(f"Introduction failed: {error}")
        logger.info(f"Обновляем статус коробки {box_id}")
        await aggregation_service.update_statuses(db, box.id, "in_circulation")
        await db.commit()
        logger.info(f"Box {box_id} introduced into turnover, doc_id={response.get('document_id')}")
        return {"box_id": box_id, "document_id": response.get("document_id", "N/A")}
# =============================================================================
# 5–7. Вспомогательные задачи
# =============================================================================
class ProcessBoxChainTask(AsyncDatabaseTask):
    async def execute_async(self, db: AsyncSession, box_id: int):
        logger.info(f"Box chain requested for box {box_id}")
        return {"box_id": box_id, "status": "chain_requested"}
class CleanupOldTasksTask(AsyncDatabaseTask):
    async def execute_async(self, db: AsyncSession, days: int = 7):
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = await db.execute(
            delete(TaskLog)
            .where(TaskLog.created_at < cutoff)
            .where(TaskLog.status == TaskStatus.SUCCESS)
        )
        await db.commit()
        logger.info(f"Cleaned up {result.rowcount} old successful task logs")
        return {"deleted": result.rowcount}
class RetryFailedTasksTask(AsyncDatabaseTask):
    async def execute_async(self, db: AsyncSession, hours: int = 24, max_attempts: int = 3):
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        result = await db.execute(
            select(TaskLog)
            .where(TaskLog.status == TaskStatus.FAILED)
            .where(TaskLog.created_at >= cutoff)
            .where(TaskLog.attempts < max_attempts)
        )
        tasks = result.scalars().all()
        retried = skipped = 0
        for task_log in tasks:
            try:
                if task_log.task_type == "order_codes":
                    from app.workers.tasks import order_codes_task
                    order_codes_task.delay(task_log.related_id)
                elif task_log.task_type == "send_apply_report":
                    from app.workers.tasks import send_apply_report_task
                    send_apply_report_task.delay(task_log.related_id)
                elif task_log.task_type == "send_aggregation_report":
                    from app.workers.tasks import send_aggregation_report_task
                    send_aggregation_report_task.delay(task_log.related_id)
                elif task_log.task_type == "send_introduction":
                    from app.workers.tasks import send_introduction_task
                    send_introduction_task.delay(task_log.related_id)
                else:
                    skipped += 1
                    continue
                retried += 1
            except Exception as e:
                logger.error(f"Retry scheduling failed for TaskLog {task_log.id}: {e}")
                skipped += 1
        return {"retried": retried, "skipped": skipped, "total": len(tasks)}
# =============================================================================
# РЕГИСТРАЦИЯ ЗАДАЧ — здесь задаём имя, очередь, повторы и т.д.
# =============================================================================
order_codes_task = app.register_task(
    OrderCodesTask(),
    name="app.workers.tasks.order_codes_task",
    queue="high_priority",
    bind=True,
    max_retries=5,
    default_retry_delay=60,
)
send_apply_report_task = app.register_task(
    SendApplyReportTask(),
    name="app.workers.tasks.send_apply_report_task",
    queue="default",
    bind=True,
    max_retries=5,
    default_retry_delay=30,
    task_idempotent=True,
)
send_aggregation_report_task = app.register_task(
    SendAggregationReportTask(),
    name="app.workers.tasks.send_aggregation_report_task",
    queue="default",
    bind=True,
    max_retries=5,
    default_retry_delay=30,
    task_idempotent=True,
)
send_introduction_task = app.register_task(
    SendIntroductionTask(),
    name="app.workers.tasks.send_introduction_task",
    queue="default",
    bind=True,
    max_retries=5,
    default_retry_delay=30,
    task_idempotent=True,
)
process_box_chain_task = app.register_task(
    ProcessBoxChainTask(),
    name="app.workers.tasks.process_box_chain_task",
    queue="low_priority",
    bind=True,
)
cleanup_old_tasks = app.register_task(
    CleanupOldTasksTask(),
    name="app.workers.tasks.cleanup_old_tasks",
    queue="low_priority",
    bind=True,
)
retry_failed_tasks = app.register_task(
    RetryFailedTasksTask(),
    name="app.workers.tasks.retry_failed_tasks",
    queue="low_priority",
    bind=True,
)
# =============================================================================
# Обратная совместимость (Dramatiq-style вызовы)
# =============================================================================
def order_codes(order_id: int):
    """Старый стиль вызова: order_codes(6)"""
    return order_codes_task.delay(order_id)
def send_apply_report(box_id: int):
    return send_apply_report_task.apply_async(args=[box_id])
def send_aggregation_report(box_id: int):
    return send_aggregation_report_task.delay(box_id)
def send_introduction(box_id: int):
    return send_introduction_task.delay(box_id)