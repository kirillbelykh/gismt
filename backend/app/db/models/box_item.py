"""Box item model"""
from sqlalchemy import Column, Integer, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class BoxItem(Base):
    """Box item model - links box to marking codes"""
    __tablename__ = "box_items"

    id = Column(Integer, primary_key=True, index=True)
    box_id = Column(
        Integer,
        ForeignKey("boxes.id", ondelete="CASCADE"),
        nullable=False,
    )
    marking_code_id = Column(Integer, ForeignKey("marking_codes.id"), nullable=False)
    scanned_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    box = relationship("Box", back_populates="box_items")
    marking_code = relationship("MarkingCode", back_populates="box_items")
