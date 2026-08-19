"""Marking code model"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum as SQLEnum, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.db.base import Base


class MarkingCodeStatus(str, enum.Enum):
    """Marking code status enum"""
    PRINTED = "printed"
    UNUSED = "unused"
    RESERVED = "reserved"
    APPLIED = "applied"
    IN_CIRCULATION = "in_circulation"
    ERROR = "error"
    AGGREGATED = "aggregated"


class MarkingCode(Base):
    """Marking code model"""
    __tablename__ = "marking_codes"

    id = Column(Integer, primary_key=True, index=True)
    code_raw = Column(String, nullable=False, index=True)
    sntin = Column(String, nullable=False, index=True)
    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    status = Column(SQLEnum(MarkingCodeStatus), default=MarkingCodeStatus.UNUSED, nullable=False)
    printed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    order = relationship("Order", back_populates="marking_codes")
    box_items = relationship("BoxItem", back_populates="marking_code")


# Create indexes
Index("idx_marking_codes_code_raw", MarkingCode.code_raw)
Index("idx_marking_codes_sntin", MarkingCode.sntin)
