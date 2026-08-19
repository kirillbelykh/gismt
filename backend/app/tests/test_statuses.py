import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.base import engine   # если у тебя так называется engine
from app.services.aggregation_service import aggregation_service


async def main():
    async_session_factory = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    async with async_session_factory() as db:
        result = await aggregation_service.update_statuses(
            db=db,
            box_id=17,
            action="in_circulation",
        )

        # ⚠️ commit делаем ЗДЕСЬ, а не в сервисе
        await db.commit()

        print("RESULT:", result)


if __name__ == "__main__":
    asyncio.run(main())
