import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.workers.tasks import (
    SendApplyReportTask,
    SendAggregationReportTask,
    SendIntroductionTask,
)
from app.services.aggregation_service import aggregation_service
from app.db.models.box import Box, BoxStatus
from app.db.models.order import Order, OrderStatus
from app.db.models.product import Product
from app.db.models.marking_code import MarkingCode, MarkingCodeStatus
from app.db.models.box_item import BoxItem
from app.db.base import Base


@pytest.mark.asyncio
async def test_full_box_lifecycle_chain(async_session: AsyncSession):
    """
    Apply -> Aggregation -> Introduction
    + real update_statuses execution
    """

    # ------------------------------------------------------------------
    # Arrange: test data
    # ------------------------------------------------------------------
    product = Product(
        id=1,
        gtin="04601234567890",
        name="Test Product",
    )

    order = Order(
        id=1,
        status=OrderStatus.READY,
        qty=2,
        name="TEST-ORDER",
        product=product,   # 🔥 КЛЮЧЕВО
    )

    box = Box(
        id=1,
        sscc="123456789012345678",
        order=order,
        status=BoxStatus.SCANNED,
    )

    code1 = MarkingCode(
        id=1,
        code_raw="CODE1",
        sntin="046012345678900001",   # 🔥 ОБЯЗАТЕЛЬНО
        order=order,                 # 🔥 ОБЯЗАТЕЛЬНО
        status=MarkingCodeStatus.RESERVED,
    )

    code2 = MarkingCode(
        id=2,
        code_raw="CODE2",
        sntin="046012345678900002",
        order=order,
        status=MarkingCodeStatus.RESERVED,
    )
    async_session.add_all([
        product,
        order,
        box,
        code1,
        code2,
        BoxItem(box=box, marking_code=code1),
        BoxItem(box=box, marking_code=code2),
    ])
    await async_session.commit()

    # ------------------------------------------------------------------
    # Mocks
    # ------------------------------------------------------------------
    with patch(
        "app.workers.base_task.AsyncDatabaseTask.update_state",
        new=lambda *args, **kwargs: None,
    ), patch(
        "app.workers.base_task.AsyncDatabaseTask._launch_next_task",
        new=AsyncMock(),
    ), patch(
        "app.services.apply_service.apply_service.send_apply_report",
        new=AsyncMock(return_value={"reportId": "RPT-1"}),
    ), patch(
        "app.services.crpt_client_service.CRPTClient.get_utilisation_report_status",
        new=AsyncMock(return_value={"state": "ACCEPTED"}),
    ), patch(
        "app.services.crpt_client_service.CRPTClient.send_aggregation_report",
        new=AsyncMock(),
    ), patch(
        "app.services.crpt_client_service.CRPTClient.check_aggregation_code_status",
        new=AsyncMock(return_value=(True, "AGGREGATED")),
    ), patch(
        "app.services.introduction_service.introduction_service.send_introduction",
        new=AsyncMock(return_value={"success": True, "document_id": "DOC-1"}),
    ), patch(
        "asyncio.sleep",
        new=AsyncMock(),
    ):

        # ------------------------------------------------------------------
        # Act: run chain
        # ------------------------------------------------------------------
        await SendApplyReportTask().execute_async(async_session, box.id)
        await SendAggregationReportTask().execute_async(async_session, box.id)
        await SendIntroductionTask().execute_async(async_session, box.id)

    # ------------------------------------------------------------------
    # Assert: final DB state
    # ------------------------------------------------------------------
    box_status = await async_session.scalar(
        select(Box.status).where(Box.id == 1)
    )
    order_status = await async_session.scalar(
        select(Order.status).where(Order.id == 1)
    )

    assert box_status == BoxStatus.TURNOVER_DONE
    assert order_status == OrderStatus.IN_CIRCULATION

    codes = (
        await async_session.execute(
            select(MarkingCode)
        )
    ).scalars().all()

    assert all(code.status == MarkingCodeStatus.IN_CIRCULATION for code in codes)
