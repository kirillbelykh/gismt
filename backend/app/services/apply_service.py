"""Apply (utilisation) service"""
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models.order import Order
from app.db.models.box import Box
from app.db.models.box_item import BoxItem
from app.db.models.marking_code import MarkingCode
from app.services.crpt_client_service import CRPTClient
from app.core.logging import get_logger

logger = get_logger(__name__)


class ApplyService:
    """Service for sending apply (utilisation) reports"""

    def __init__(self):
        self.crpt_client = CRPTClient()

    async def prepare_apply_payload(
        self,
        db: AsyncSession,
        box_id: int,
    ) -> dict:
        """
        Prepare apply report payload

        Args:
            db: Database session
            box_id: Box ID

        Returns:
            Payload dictionary
        """
        # Get box with items
        from sqlalchemy.orm import selectinload

        box_result = await db.execute(
            select(Box)
            .options(
                selectinload(Box.order).selectinload(Order.batch)  # ← ВОТ ЭТО ГЛАВНОЕ
            )
            .where(Box.id == box_id)
        )
        box = box_result.scalar_one_or_none()
        if not box:
            raise ValueError(f"Box {box_id} not found")

        # Get marking codes
        items_result = await db.execute(
            select(BoxItem).where(BoxItem.box_id == box_id)
        )
        items = items_result.scalars().all()

        code_ids = [item.marking_code_id for item in items]
        codes_result = await db.execute(
            select(MarkingCode).where(MarkingCode.id.in_(code_ids))
        )
        codes = codes_result.scalars().all()

        # Extract SNTINs
        sntins = [code.code_raw for code in codes]

        # Prepare attributes from order
        attributes = {
            "productionDate": box.order.batch.prod_date.isoformat(),
            "expirationDate": box.order.batch.exp_date.isoformat(),
            "batchNumber": box.order.batch.batch_number,
        }

        return {
            "product_group": "wheelchairs",  # TODO: make configurable
            "sntins": sntins,
            "attributes": attributes,
        }

    async def send_apply_report(
        self,
        db: AsyncSession,
        box_id: int,
    ) -> dict:
        """
        Send apply report to CRPT

        Args:
            db: Database session
            box_id: Box ID

        Returns:
            Response from CRPT
        """
        payload = await self.prepare_apply_payload(db, box_id)

        response = await self.crpt_client.send_utilisation_report(
            product_group=payload["product_group"],
            sntins=payload["sntins"],
            attributes=payload["attributes"],
        )

        logger.info(f"Apply report sent for box {box_id}, report_id: {response.get('reportId')}")
        return response


apply_service = ApplyService()
