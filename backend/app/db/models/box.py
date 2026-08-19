"""Box model"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.db.base import Base


class BoxStatus(str, enum.Enum):
    """Box status enum"""
    SCANNED = "scanned"
    RESERVED = "reserved"
    APPLY_SENT = "apply_sent"
    AGGREGATED = "aggregated"
    TURNOVER_DONE = "turnover_done"
    ERROR = "error"


class Box(Base):
    """Box model"""
    __tablename__ = "boxes"

    id = Column(Integer, primary_key=True, index=True)
    sscc = Column(String, unique=True, index=True, nullable=False)

    # Связи
    # batch_id теперь не нужен напрямую, т.к. партия привязана к заказу
    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )

    status = Column(SQLEnum(BoxStatus), default=BoxStatus.SCANNED, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    # Связь с партией через заказ (опционально, для удобства)
    # Можно получать партию через order.batch
    order = relationship("Order", back_populates="boxes")
    box_items = relationship("BoxItem", back_populates="box", cascade="all, delete-orphan")

    # Свойство для удобного доступа к партии
    @property
    def batch(self):
        """Get batch through order relationship"""
        if self.order and self.order.batch:
            return self.order.batch
        return None

    @property
    def batch_id(self):
        """Get batch_id through order relationship"""
        if self.order and self.order.batch:
            return self.order.batch.id
        return None

    @property
    def batch_number(self):
        """Get batch_number through order relationship"""
        if self.order and self.order.batch:
            return self.order.batch.batch_number
        return None

    def __repr__(self):
        return f"<Box(id={self.id}, sscc={self.sscc}, order_id={self.order_id})>"