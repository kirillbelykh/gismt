from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models.box import Box

class BoxCRUD:
    """CRUD операции для работы с коробками"""

    @staticmethod
    async def get_box_by_id(db: AsyncSession, box_id: int) -> Optional[Box]:
        """Получить коробку по ID"""
        stmt = select(Box).where(Box.id == box_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_box_with_sscc(db: AsyncSession, box_id: int) -> Optional[Box]:
        """Получить коробку с проверкой наличия SSCC"""
        box = await BoxCRUD.get_box_by_id(db, box_id)
        if box and not getattr(box, "sscc"):
            raise ValueError(f"У коробки {box_id} нет SSCC-кода")
        return box

box_crud = BoxCRUD()