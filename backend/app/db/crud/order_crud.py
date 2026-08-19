"""CRUD operations for Order model (связь через Batch)"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.order import Order, OrderStatus
from app.core.logging import get_logger

logger = get_logger(__name__)


class OrderCRUD:
    """CRUD операции для модели Order с нормализованной структурой через Batch"""

    async def create(
        self,
        db: AsyncSession,
        *,
        product_id: int,
        name: Optional[str] = None,
        gtin: Optional[str] = None,
        qty: int,
        status: OrderStatus = OrderStatus.ORDERING,
    ) -> Order:
        """
        Создать новый заказ.
        Партия (Batch) должна быть уже создана заранее!
        """
        order = Order(
            product_id=product_id,
            name=name,
            gtin=gtin,
            qty=qty,
            status=status,
        )
        db.add(order)
        await db.commit()
        await db.flush()  # получаем order.id без commit
        logger.info(f"Создан заказ #{order.id}, qty={qty})")
        return order

    async def get_by_id(self, db: AsyncSession, order_id: int) -> Optional[Order]:
        """Получить заказ по ID с подгрузкой продукта и партии"""
        result = await db.execute(
            select(Order)
            .options(
                selectinload(Order.product),
                selectinload(Order.batch)
            )
            .where(Order.id == order_id)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
        order_by: str = "created_at_desc",
    ) -> List[Order]:
        """Получить все заказы с пагинацией и подгрузкой связанных данных"""
        query = (
            select(Order)
            .options(
                selectinload(Order.product),
                selectinload(Order.batch)
            )
        )

        if order_by == "created_at_desc":
            query = query.order_by(desc(Order.created_at))
        elif order_by == "created_at_asc":
            query = query.order_by(Order.created_at)

        query = query.offset(skip).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_by_batch_id(
        self,
        db: AsyncSession,
        batch_id: int,
    ) -> List[Order]:
        """Получить все заказы по ID партии"""
        result = await db.execute(
            select(Order)
            .where(Order.batch.id == batch_id)
            .options(
                selectinload(Order.product),
                selectinload(Order.batch)
            )
            .order_by(desc(Order.created_at))
        )
        return list(result.scalars().all())

    async def get_active_orders(
        self,
        db: AsyncSession,
        limit: int = 50,
    ) -> List[Order]:
        """Последние активные заказы (ordering или ready)"""
        result = await db.execute(
            select(Order)
            .where(Order.status.in_([OrderStatus.ORDERING, OrderStatus.READY]))
            .options(
                selectinload(Order.product),
                selectinload(Order.batch)
            )
            .order_by(desc(Order.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        db: AsyncSession,
        order_id: int,
        status: OrderStatus,
    ) -> Optional[Order]:
        """Обновить статус заказа"""
        order = await self.get_by_id(db, order_id)
        if not order:
            return None

        order.status = status
        await db.flush()
        logger.info(f"Статус заказа #{order_id} изменён на {status.value}")
        return order

    async def delete(self, db: AsyncSession, order_id: int) -> bool:
        """Удалить заказ и связанные данные (партия, коды, коробки)"""
        try:
            # Получаем заказ с привязанными данными
            order = await self.get_by_id(db, order_id)
            if not order:
                return False

            # Сохраняем информацию для логов
            order_info = f"Заказ #{order.id} '{order.name}'"

            # Удаляем заказ (каскадно удалится партия, коды и коробки)
            await db.delete(order)
            await db.commit()

            logger.info(f"{order_info} и все связанные данные удалены")
            return True

        except Exception as e:
            await db.rollback()
            logger.exception(f"Ошибка при удалении заказа #{order_id}: {e}")
            return False

    async def close(self, db: AsyncSession, order_id: int) -> bool:
        """Сменить статус на ЗАКРЫТ"""
        try:
            # Получаем заказ
            order = await self.get_by_id(db, order_id)
            if not order:
                logger.error(f"Заказ {order_id} не найден")
                return False

            # Проверяем, можно ли закрыть заказ (статус должен быть READY)
            if order.status != OrderStatus.READY:
                logger.warning(
                    f"Попытка закрыть заказ {order_id} со статусом {order.status}. "
                    f"Можно закрывать только заказы со статусом READY"
                )
                return False

            # Обновляем статус
            update_success = await self.update_status(
                db,
                order_id,
                OrderStatus.CLOSED
            )

            if update_success:
                logger.info(f"Статус заказа {order_id} изменен на {OrderStatus.CLOSED}")
                # Дополнительно можно сохранить дату закрытия
                try:
                    await db.commit()
                    return True
                except Exception as e:
                    logger.error(f"Ошибка при сохранении даты закрытия заказа {order_id}: {e}")
                    await db.rollback()

            return False

        except Exception as e:
            logger.exception(f"Ошибка при закрытии заказа {order_id} в БД: {e}")
            return False

    async def find_ext_order_id(self, db: AsyncSession, order_id: int) -> Optional[str]:
        """Найти external_order_id заказа"""
        try:
            result = await db.execute(
                select(Order).where(Order.id == order_id)
            )

            order = result.scalar_one_or_none()
            if not order:
                logger.warning(f"Заказ {order_id} не найден в БД")
                return None

            external_id = getattr(order, "external_order_id", None)
            if not external_id:
                logger.warning(f"Заказ {order_id} не имеет external_order_id")
                return None

            return str(external_id) if external_id else None

        except Exception as e:
            logger.exception(f"Ошибка при поиске external_order_id для заказа {order_id}: {e}")
            return None

# Экземпляр для импорта
order_crud = OrderCRUD()