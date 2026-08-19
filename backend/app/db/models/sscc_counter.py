"""SSCC counter model"""
from sqlalchemy import Column, String, Integer, Date, UniqueConstraint
from app.db.base import Base


class SSCCCounter(Base):
    """SSCC counter model - stores daily serial counters"""
    __tablename__ = "sscc_counters"

    date = Column(Date, primary_key=True, nullable=False)
    last_serial_int = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint('date', name='uq_sscc_counters_date'),
    )
