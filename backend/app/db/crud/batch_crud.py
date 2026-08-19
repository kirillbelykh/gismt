# app/crud/batch_crud.py
"""CRUD операции для модели Batch"""

from datetime import date
from typing import Optional

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.batch import Batch
from app.db.models.product import Product


class BatchCRUD:
    """Набор CRUD-операций для работы с партиями (Batch)"""

    async def get_by_id(self, db: AsyncSession, batch_id: int) -> Optional[Batch]:
        """Получить партию по ID"""
        result = await db.execute(select(Batch).where(Batch.id == batch_id))
        return result.scalar_one_or_none()

    async def get_by_batch_number(
        self,
        db: AsyncSession,
        batch_number: str,
    ) -> Optional[Batch]:
        """
        Получить партию по номеру партии.
        Опционально можно указать product_id для точного совпадения.
        """
        query = select(Batch).where(Batch.batch_number == batch_number)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        db: AsyncSession,
        batch_number: str,
        prod_date: date,
        exp_date: date,
        order_id: int,
    ) -> Batch:
        """
        Получить существующую партию или создать новую.
        Используется при создании заказов — чтобы не дублировать партии.
        """

        new_batch = Batch(
            batch_number=batch_number,
            prod_date=prod_date,
            exp_date=exp_date,
            order_id=order_id,
        )
        db.add(new_batch)
        await db.flush()  # чтобы получить batch.id
        return new_batch

    async def create(
        self,
        db: AsyncSession,
        batch_number: str,
        product_id: int,
        prod_date: date,
        exp_date: date,
    ) -> Batch:
        """Создать новую партию (без проверки на дубли)"""
        batch = Batch(
            batch_number=batch_number,
            product_id=product_id,
            prod_date=prod_date,
            exp_date=exp_date,
        )
        db.add(batch)
        await db.flush()
        return batch

    async def update_dates(
        self,
        db: AsyncSession,
        batch_id: int,
        prod_date: Optional[date] = None,
        exp_date: Optional[date] = None,
    ) -> Optional[Batch]:
        """Обновить даты производства/годности у партии"""
        values = {}
        if prod_date is not None:
            values["prod_date"] = prod_date
        if exp_date is not None:
            values["exp_date"] = exp_date

        if not values:
            return await self.get_by_id(db, batch_id)

        await db.execute(
            update(Batch).where(Batch.id == batch_id).values(**values)
        )
        await db.flush()
        return await self.get_by_id(db, batch_id)

    async def delete(self, db: AsyncSession, batch_id: int) -> bool:
        """Удалить партию (если нет связанных коробок/кодов — иначе будет ошибка FK)"""
        batch = await self.get_by_id(db, batch_id)
        if not batch:
            return False
        await db.delete(batch)
        return True


# Экземпляр для импорта в других модулях
batch_crud = BatchCRUD()