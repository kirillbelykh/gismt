"""Task log model"""
from sqlalchemy import Column, Integer, String, DateTime, JSON, Enum as SQLEnum, Index
from sqlalchemy.sql import func
import enum
from app.db.base import Base


class TaskStatus(str, enum.Enum):
    """Task status enum"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class TaskLog(Base):
    """Task log model - tracks background task execution"""
    __tablename__ = "task_log"

    id = Column(Integer, primary_key=True, index=True)
    task_type = Column(String, nullable=False, index=True)
    related_id = Column(Integer, nullable=False, index=True)  # order_id, box_id, etc.
    attempts = Column(Integer, default=0, nullable=False)
    last_error = Column(String, nullable=True)
    payload = Column(JSON, nullable=True)
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# Create index for idempotency
Index("idx_task_log_idempotency", TaskLog.task_type, TaskLog.related_id)
