"""Order model - connects to both product and batch"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.product import Product
    from app.db.models.batch import Batch
    from app.db.models.marking_code import MarkingCode
    from app.db.models.box import Box


class OrderStatus(str, enum.Enum):
    """Статус заказа"""
    ORDERING = "ordering"    # Заказ оформляется
    READY = "ready"         # Коды готовы
    ERROR = "error"         # Ошибка
    CLOSED = "closed"
    AGGREGATED = "aggregated"   # Заказ агрегирован
    IN_CIRCULATION = "in_circulation"  # Введен в обор

class Order(Base):
    """Модель заказа — связывает продукт и партию"""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True, server_default="unknown")
    gtin = Column(String, nullable=True)
    external_order_id = Column(String, unique=True, index=True, nullable=True)

    # Связи
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)

    qty = Column(Integer, nullable=False)
    status = Column(String, default=OrderStatus.ORDERING.value, server_default=OrderStatus.ORDERING.value, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    product = relationship("Product", back_populates="orders")
    batch = relationship(
        "Batch",
        back_populates="order",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True
    )
    marking_codes = relationship(
        "MarkingCode",
        back_populates="order",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    boxes = relationship(
        "Box",
        back_populates="order",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Order {self.id} | {self.name}>"