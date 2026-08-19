"""Batch model - linked to specific order"""
from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class Batch(Base):
    """Модель партии - привязана к конкретному заказу"""
    __tablename__ = "batches"

    id = Column(Integer, primary_key=True, index=True)
    batch_number = Column(String, nullable=False, index=True)  # например: "251201"
    prod_date = Column(Date, nullable=False)  # Дата производства
    exp_date = Column(Date, nullable=False)   # Срок годности
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связь с заказом (обязательная)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Relationships
    order = relationship("Order", back_populates="batch", uselist=False)


    def __repr__(self):
        return f"<Batch(id={self.id}, order_id={self.order_id}, batch_number={self.batch_number})>"