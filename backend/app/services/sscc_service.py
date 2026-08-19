"""SSCC generation service using database counter"""
from datetime import date
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from app.db.models.sscc_counter import SSCCCounter
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def get_today_code() -> str:
    """YYMMDD — как в Контур.Маркировке"""
    return date.today().strftime("%y%m%d")


class SSCCService:
    """Service for generating unique SSCC codes compatible with Contour.Markirovka"""

    def __init__(self):
        self.prefix = settings.GS1_PREFIX
        self.extension_digit = settings.GS1_EXTENSION_DIGIT

    async def generate_next_sscc(
        self,
        db: AsyncSession,
    ) -> str:
        """
        Generate next unique 26-digit SSCC compatible with Contour.Markirovka

        Structure: extension(1) + prefix(9) + date(6) + serial(10) = 26 digits

        Args:
            db: Database session
            site_prefix: Optional site prefix (not used in current format)

        Returns:
            Unique SSCC string (26 digits)
        """
        today = date.today()
        today_code = get_today_code()

        # Use PostgreSQL upsert to atomically increment counter for today's date
        stmt = insert(SSCCCounter).values(
            date=today,
            last_serial_int=1
        ).on_conflict_do_update(
            index_elements=['date'],
            set_=dict(
                last_serial_int=SSCCCounter.last_serial_int + 1
            )
        ).returning(SSCCCounter.last_serial_int)

        result = await db.execute(stmt)
        await db.commit()

        serial = result.scalar_one()

        # Generate 26-digit SSCC: extension + prefix + date + 10-digit serial
        sscc = f"{self.extension_digit}{self.prefix}{today_code}{serial:010d}"

        logger.info(f"Generated SSCC: {sscc} (date: {today_code}, serial: {serial})")
        return sscc


# Global instance
sscc_service = SSCCService()