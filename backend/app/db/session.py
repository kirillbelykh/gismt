"""Database session management"""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.base import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session with automatic transaction management"""
    async with AsyncSessionLocal() as session:
        try:
            # Явно начинаем транзакцию
            await session.begin()
            yield session
            # Коммитим если не было исключений
            await session.commit()
        except Exception:
            # При любой ошибке - откатываем
            await session.rollback()
            raise
        finally:
            await session.close()