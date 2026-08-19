"""Aggregation service for box scanning and processing"""
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.db.models.box import Box, BoxStatus
from app.db.models.box_item import BoxItem
from app.db.models.marking_code import MarkingCode, MarkingCodeStatus
from app.db.models.order import Order, OrderStatus
from app.services.sscc_service import sscc_service
from app.services.code_parse_service import extract_sntin
from app.core.logging import get_logger

logger = get_logger(__name__)


class AggregationService:
    """Service for box aggregation"""

    async def create_box(self, db: AsyncSession, order_id: int, raw_codes: List[str]) -> Box:
        """
        Create box based on scanned codes from photo.
        Теперь проверяет коды независимо от их статуса (кроме уже использованных)
        """
        # 1. Извлекаем SGTIN из кодов
        sntins = []
        for code in raw_codes:
            sntin = extract_sntin(code)
            if not sntin:
                raise ValueError(f"Неверный формат кода: {code}")
            sntins.append(sntin)

        # 2. Находим коды в БД для этого заказа
        # Теперь ищем ВСЕ коды независимо от статуса (кроме уже использованных в ДРУГИХ коробках)
        from sqlalchemy import select
        codes_result = await db.execute(
            select(MarkingCode).where(
                MarkingCode.order_id == order_id,
                MarkingCode.sntin.in_(sntins)
            )
        )
        codes = codes_result.scalars().all()

        # 3. Проверяем, что все коды найдены и не используются в других коробках
        found_sntins = {code.sntin for code in codes}
        missing_sntins = set(sntins) - found_sntins

        if missing_sntins:
            raise ValueError(f"Коды не найдены в БД для заказа {order_id}: {list(missing_sntins)[:3]}...")

        # 4. Проверяем, что коды не используются в ДРУГИХ коробках
        # (в текущей коробке они уже могли быть использованы - это нормально)
        for code in codes:
            # Проверяем, есть ли этот код в других коробках
            from sqlalchemy import exists, select

            used_in_other_boxes = await db.execute(
                select(exists().where(
                    BoxItem.marking_code_id == code.id,
                    BoxItem.box_id != None  # Уже привязан к какой-то коробке
                ))
            )

            is_used = used_in_other_boxes.scalar()

            if is_used:
                # Проверяем, не в этом ли заказе?
                from sqlalchemy import join

                box_check = await db.execute(
                    select(Box.order_id)
                    .join(BoxItem, Box.id == BoxItem.box_id)
                    .where(BoxItem.marking_code_id == code.id)
                    .limit(1)
                )

                other_order_id = box_check.scalar()

                if other_order_id != order_id:
                    raise ValueError(f"Код {code.sntin} уже используется в другом заказе {other_order_id}")
                # Если в том же заказе - это нормально (сценарий 5+4+1)

        # 5. Меняем статус кодов на RESERVED (если они еще не RESERVED/AGGREGATED)
        for code in codes:
            if code.status in [MarkingCodeStatus.UNUSED, MarkingCodeStatus.PRINTED]:
                code.status = MarkingCodeStatus.RESERVED # type: ignore

        # 6. Получаем информацию о заказе
        order_result = await db.execute(select(Order).where(Order.id == order_id))
        order = order_result.scalar_one()

        # 7. Генерируем SSCC
        sscc = await sscc_service.generate_next_sscc(db)

        # 8. Создаём box
        box = Box(
            sscc=sscc,
            order_id=order_id,
            status=BoxStatus.SCANNED
        )
        db.add(box)
        await db.flush()

        # 9. Создаём box_items (если их еще нет)
        for code in codes:
            # Проверяем, не создан ли уже BoxItem для этого кода
            existing_item = await db.execute(
                select(BoxItem).where(
                    BoxItem.box_id == box.id,
                    BoxItem.marking_code_id == code.id
                )
            )

            if not existing_item.scalar_one_or_none():
                box_item = BoxItem(
                    box_id=box.id,
                    marking_code_id=code.id
                )
                db.add(box_item)

        await db.flush()
        await db.refresh(box)

        # 10. Обновляем статус кодов на AGGREGATED
        for code in codes:
            code.status = MarkingCodeStatus.AGGREGATED # type: ignore

        return box


    async def scan_box(
        self,
        db: AsyncSession,
        order_id: int,
        batch_id: Optional[int],
        raw_codes: List[str],
    ) -> Box:
        """
        Scan box with marking codes

        Args:
            db: Database session
            order_id: Order ID
            batch_id: Optional batch ID
            raw_codes: List of raw DataMatrix codes

        Returns:
            Created box with SSCC

        Raises:
            ValueError: If codes are invalid or not found
        """
        from app.services.code_parse_service import extract_sntin

        # Validate order exists
        order_result = await db.execute(select(Order).where(Order.id == order_id))
        order = order_result.scalar_one_or_none()
        if not order:
            raise ValueError(f"Order {order_id} not found")

        # Extract SNTINs and find codes in database
        sntins = [extract_sntin(code) for code in raw_codes]

        # Find marking codes
        codes_result = await db.execute(
            select(MarkingCode).where(
                MarkingCode.order_id == order_id,
                MarkingCode.sntin.in_(sntins),
                MarkingCode.status.in_([MarkingCodeStatus.UNUSED, MarkingCodeStatus.PRINTED]),
            )
        )
        found_codes = codes_result.scalars().all()

        if len(found_codes) != len(raw_codes):
            raise ValueError(
                f"Not all codes found: expected {len(raw_codes)}, found {len(found_codes)}"
            )

        # Mark codes as reserved
        for code in found_codes:
            code.status = MarkingCodeStatus.RESERVED # type: ignore

        # Generate SSCC
        sscc = await sscc_service.generate_next_sscc(db)

        # Create box
        box = Box(
            sscc=sscc,
            order_id=order_id,
            batch_id=batch_id,
            status=BoxStatus.SCANNED,
        )
        db.add(box)
        await db.flush()  # Get box.id

        # Create box items
        box_items = [
            BoxItem(
                box_id=box.id,
                marking_code_id=code.id,
            )
            for code in found_codes
        ]
        db.add_all(box_items)

        await db.commit()
        await db.refresh(box)

        logger.info(f"Box scanned: {box.id}, SSCC: {sscc}, codes: {len(found_codes)}")
        box_id = getattr(box, "id")
        # Enqueue apply report task
        from app.workers.tasks import send_apply_report
        send_apply_report(box_id)
        logger.info(f"Enqueued apply report task for box {box.id}")

        return box

    async def get_box(self, db: AsyncSession, box_id: int) -> Optional[Box]:
        """Get box by ID"""
        result = await db.execute(select(Box).where(Box.id == box_id))
        return result.scalar_one_or_none()

    async def update_statuses(
        self,
        db: AsyncSession,
        box_id: int,
        action: str,  # "aggregated", "in_circulation", "turnover_done"
    ) -> dict:
        """
        Atomically update all statuses for a box, its order, and codes.
        Returns: dict with counts of updated items
        """
        logger.info(f"🔄 [update_statuses] START for box {box_id}, action={action}")

        try:
            # 1. Получаем коробку с блокировкой
            result = await db.execute(
                select(Box)
                .options(selectinload(Box.order))
                .where(Box.id == box_id)
                .with_for_update()
            )
            box = result.scalar_one_or_none()

            if not box:
                raise ValueError(f"Box {box_id} not found")

            logger.info(f"📦 Box {box_id} found: order_id={box.order_id}, current_status={box.status}")

            # 2. Определяем целевые статусы
            if action == "aggregated":
                box_status = BoxStatus.AGGREGATED
                order_status = OrderStatus.AGGREGATED
                code_status = MarkingCodeStatus.AGGREGATED
            elif action == "in_circulation" or action == "turnover_done":
                box_status = BoxStatus.TURNOVER_DONE
                order_status = OrderStatus.IN_CIRCULATION
                code_status = MarkingCodeStatus.IN_CIRCULATION
            elif action == "applied":
                box_status = BoxStatus.APPLY_SENT
                order_status = OrderStatus.AGGREGATED
                code_status = MarkingCodeStatus.APPLIED
            else:
                raise ValueError(f"Unknown action: {action}")

            logger.info(f"🎯 Target statuses: box={box_status}, order={order_status}, codes={code_status}")

            # 3. Обновляем коробку
            box_updated = False
            if box.status != box_status: # type: ignore
                old_box_status = box.status
                box.status = box_status # type: ignore
                box_updated = True
                logger.info(f"✅ Box {box_id}: {old_box_status} → {box_status}")
            else:
                logger.info(f"ℹ️ Box {box_id} already has status {box_status}")

            # 4. Обновляем заказ
            order_updated = False
            if box.order:
                if box.order.status != order_status:
                    old_order_status = box.order.status
                    box.order.status = order_status
                    order_updated = True
                    logger.info(f"✅ Order {box.order_id}: {old_order_status} → {order_status}")
                else:
                    logger.info(f"ℹ️ Order {box.order_id} already has status {order_status}")
            else:
                logger.warning(f"⚠️ Box {box_id} has no associated order!")

            # 5. Обновляем коды маркировки в этой коробке
            codes_result = await db.execute(
                select(MarkingCode)
                .join(BoxItem, MarkingCode.id == BoxItem.marking_code_id)
                .where(BoxItem.box_id == box_id)
            )
            codes = codes_result.scalars().all()

            codes_updated = 0
            for code in codes:
                if code.status != code_status: # type: ignore
                    old_code_status = code.status
                    code.status = code_status # type: ignore
                    codes_updated += 1
                    if codes_updated <= 3:  # Логируем только первые 3
                        logger.debug(f"  Code {code.id}: {old_code_status} → {code_status}")

            logger.info(f"✅ Updated {codes_updated} of {len(codes)} codes to {code_status}")

            result_summary = {
                "box_id": box_id,
                "order_id": box.order_id,
                "box_updated": box_updated,
                "order_updated": order_updated,
                "codes_updated": codes_updated,
                "total_codes": len(codes),
                "action": action,
                "box_status": box_status.value if hasattr(box_status, 'value') else str(box_status),
                "order_status": order_status.value if hasattr(order_status, 'value') else str(order_status),
                "code_status": code_status.value if hasattr(code_status, 'value') else str(code_status),
            }

            logger.info(f"🎉 [update_statuses] COMPLETE: {result_summary}")
            return result_summary

        except Exception as e:
            logger.error(f"❌ [update_statuses] FAILED for box {box_id}: {e}", exc_info=True)
            await db.rollback()
            raise


aggregation_service = AggregationService()
