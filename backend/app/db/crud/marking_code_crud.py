"""CRUD operations for MarkingCode model"""
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.db.models.marking_code import MarkingCode, MarkingCodeStatus
from app.core.logging import get_logger

logger = get_logger(__name__)


class MarkingCodeCRUD:
    """CRUD operations for MarkingCode model"""

    async def create_bulk(
        self,
        db: AsyncSession,
        order_id: int,
        codes: List[str],
        status: MarkingCodeStatus = MarkingCodeStatus.UNUSED,
    ) -> int:
        """Create multiple marking codes at once"""
        from app.services.code_parse_service import extract_sntin

        marking_codes = []
        for code_raw in codes:
            sntin = extract_sntin(code_raw)
            marking_code = MarkingCode(
                order_id=order_id,
                code_raw=code_raw,
                sntin=sntin,
                status=status,
            )
            marking_codes.append(marking_code)

        db.add_all(marking_codes)
        await db.commit()

        logger.info(f"Created {len(marking_codes)} marking codes for order {order_id}")
        return len(marking_codes)

    async def get_by_order_id(
        self,
        db: AsyncSession,
        order_id: int,
        skip: int = 0,
        limit: int = 0,
    ) -> List[MarkingCode]:
        """Get marking codes by order ID"""
        query = select(MarkingCode).where(MarkingCode.order_id == order_id)

        if limit > 0:
            query = query.offset(skip).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_codes_raw_by_order_id(
        self,
        db: AsyncSession,
        order_id: int,
    ) -> List[str]:
        """Get raw codes by order ID"""
        result = await db.execute(
            select(MarkingCode.code_raw).where(MarkingCode.order_id == order_id)
        )
        return [row[0] for row in result.all()]

    async def count_by_order_id(
        self,
        db: AsyncSession,
        order_id: int,
        status: Optional[MarkingCodeStatus] = None,
    ) -> int:
        """Count marking codes by order ID and optional status"""
        query = select(func.count(MarkingCode.id)).where(MarkingCode.order_id == order_id)

        if status:
            query = query.where(MarkingCode.status == status)

        result = await db.execute(query)
        return result.scalar_one() or 0

    async def update_status(
        self,
        db: AsyncSession,
        code_id: int,
        status: MarkingCodeStatus,
    ) -> Optional[MarkingCode]:
        """Update marking code status"""
        result = await db.execute(
            select(MarkingCode).where(MarkingCode.id == code_id)
        )
        code = result.scalar_one_or_none()

        if code:
            code.status = status
            await db.commit()
            await db.refresh(code)

        return code

    async def update_status_bulk(
        self,
        db: AsyncSession,
        order_id: int,
        status: MarkingCodeStatus,
    ) -> int:
        """Update status for all codes in order"""
        result = await db.execute(
            select(MarkingCode).where(MarkingCode.order_id == order_id)
        )
        codes = result.scalars().all()

        updated_count = 0
        for code in codes:
            code.status = status
            updated_count += 1

        if updated_count > 0:
            await db.commit()
            logger.info(f"Updated {updated_count} codes for order {order_id} to status {status}")

        return updated_count

    async def delete_by_order_id(
        self,
        db: AsyncSession,
        order_id: int,
    ) -> int:
        """Delete all marking codes for order"""
        result = await db.execute(
            select(MarkingCode).where(MarkingCode.order_id == order_id)
        )
        codes = result.scalars().all()

        deleted_count = 0
        for code in codes:
            await db.delete(code)
            deleted_count += 1

        if deleted_count > 0:
            await db.commit()
            logger.info(f"Deleted {deleted_count} marking codes for order {order_id}")

        return deleted_count


marking_code_crud = MarkingCodeCRUD()