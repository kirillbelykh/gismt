"""Introduction (turnover) service"""
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models.box import Box
from app.services.crpt_client_service import CRPTClient
from app.core.logging import get_logger

logger = get_logger(__name__)


class IntroductionService:
    """Service for sending introduction (turnover) reports"""

    def __init__(self):
        self.crpt_client = CRPTClient()

    async def send_introduction(
        self,
        db: AsyncSession,
        box_id: int,
        participant_inn: str = "7843316794",
        producer_inn: str = "7843316794",
        owner_inn: str = "7843316794",
    ) -> dict:
        """
        Send introduction report to CRPT

        Args:
            db: Database session
            box_id: Box ID
            participant_inn: Participant INN
            producer_inn: Producer INN
            owner_inn: Owner INN

        Returns:
            Response from CRPT
        """
        # Get box
        box_result = await db.execute(
            select(Box).where(Box.id == box_id)
        )
        box = box_result.scalar_one_or_none()
        if not box:
            raise ValueError(f"Box {box_id} not found")

        response = await self.crpt_client.send_introduction_report(
            sscc_codes=[getattr(box, "sscc")],
            participant_inn=participant_inn,
            producer_inn=producer_inn,
            owner_inn=owner_inn,
        )

        logger.info(f"Introduction report sent for box {box_id}, SSCC: {box.sscc}")
        return response


introduction_service = IntroductionService()
