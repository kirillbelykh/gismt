"""
Base task class with proper async/sync handling and error management
"""
import asyncio
from typing import Optional, Any
from celery import Task
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import AsyncSessionLocal
from app.db.models.task_log import TaskLog, TaskStatus
from app.core.logging import get_logger
from datetime import datetime, timedelta
import random

logger = get_logger(__name__)


class AsyncDatabaseTask(Task):
    """Base task with async database support"""

    # Task configuration
    max_retries = 3
    default_retry_delay = 60
    time_limit = 300
    soft_time_limit = 280
    acks_late = True
    reject_on_worker_lost = True

    # For idempotency
    task_idempotent = False
    task_idempotency_window = 3600

    def __init__(self):
        super().__init__()
        self._event_loop = None

    @property
    def event_loop(self):
        """Get or create event loop for async operations"""
        if self._event_loop is None or self._event_loop.is_closed():
            try:
                self._event_loop = asyncio.get_event_loop()
            except RuntimeError:
                self._event_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._event_loop)
        return self._event_loop

    async def _create_task_log(self, db: AsyncSession, task_type: str, related_id: int) -> Optional[TaskLog]:
        """Create task log entry with idempotency check"""
        from sqlalchemy import select

        # Check for recent successful task
        if self.task_idempotent:
            result = await db.execute(
                select(TaskLog).where(
                    TaskLog.task_type == task_type,
                    TaskLog.related_id == related_id,
                    TaskLog.status == TaskStatus.SUCCESS,
                    TaskLog.created_at >= datetime.utcnow() - timedelta(seconds=self.task_idempotency_window)
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                logger.info(f"Task {task_type} for ID {related_id} already completed recently, skipping")
                raise self.retry(countdown=86400)

        task_log = TaskLog(
            task_type=task_type,
            related_id=related_id,
            attempts=1,
            status=TaskStatus.RUNNING,
            metadata={
                'task_id': self.request.id,
                'worker': self.request.hostname,
            }
        )
        db.add(task_log)
        await db.commit()
        await db.refresh(task_log)
        return task_log

    async def _update_task_log(self, db: AsyncSession, task_log: Optional[TaskLog], status: TaskStatus, error: str = None):
        """Update task log with result"""
        if task_log:
            task_log.status = status
            task_log.completed_at = datetime.utcnow()
            if error:
                task_log.last_error = error
            if status == TaskStatus.FAILED:
                task_log.attempts = (task_log.attempts or 0) + 1
            await db.commit()

    def run(self, *args, **kwargs):
        """Celery task entry point with proper async handling"""
        try:
            # Run async task in event loop
            return self.event_loop.run_until_complete(self._run_async(*args, **kwargs))
        except asyncio.CancelledError:
            logger.warning(f"Task {self.name} was cancelled")
            raise
        except Exception as e:
            logger.error(f"Task {self.name} failed: {e}")
            raise

    async def _run_async(self, *args, **kwargs):
        """Run task with retry logic and proper resource management"""
        async with AsyncSessionLocal() as db:
            task_log = None
            try:
                # Create task log
                task_type = self.name.split('.')[-1]
                related_id = kwargs.get('related_id') or args[0] if args else None

                if related_id:
                    task_log = await self._create_task_log(db, task_type, related_id)

                # Execute the actual task logic
                result = await self.execute_async(db, *args, **kwargs)

                # Update task log on success
                if task_log:
                    await self._update_task_log(db, task_log, TaskStatus.SUCCESS)

                # Check if we need to launch next task in chain
                if isinstance(result, dict) and 'next_task' in result:
                    await self._launch_next_task(result['next_task'], result['next_task_args'])

                return result

            except Exception as e:
                logger.exception(f"Task {self.name} failed: {e}")

                # Update task log on failure
                if task_log:
                    await self._update_task_log(db, task_log, TaskStatus.FAILED, str(e))

                # Check if we should retry
                if self.request.retries < self.max_retries:
                    retry_delay = self.calculate_retry_delay(self.request.retries)
                    logger.info(f"Retrying task {self.name} in {retry_delay}s (attempt {self.request.retries + 1})")
                    raise self.retry(countdown=retry_delay, exc=e)
                else:
                    # Final failure
                    logger.error(f"Task {self.name} failed after {self.max_retries} retries")
                    raise

    async def execute_async(self, db: AsyncSession, *args, **kwargs):
        """This method should be overridden by concrete tasks"""
        raise NotImplementedError("Subclasses must implement execute_async")

    async def _launch_next_task(self, task_name: str, task_args: list):
        """Launch next task in the chain — БЕЗ лишнего related_id в kwargs"""
        try:
            logger.info(f"Attempting to launch next task: {task_name} with args {task_args}")

            from app.workers.celery_app import app

            # Определяем очередь (нечувствительно к регистру)
            queue = 'default'
            lower_name = task_name.lower()
            if 'order_codes' in lower_name:
                queue = 'high_priority'
            # остальные — default (apply, aggregation, introduction)

            # ВАЖНО: НЕ передаём kwargs={'related_id': ...} — он не нужен!
            result = app.send_task(
                task_name,
                args=task_args,
                queue=queue,
                # kwargs={}  # можно явно указать пустой, но и без него нормально
            )

            logger.info(f"Next task {task_name} launched successfully. Task ID: {result.id}")

        except Exception as e:
            logger.error(f"Failed to launch next task {task_name}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Не падаем — цепочкой — просто логируем

    def calculate_retry_delay(self, retry_count: int) -> int:
        """Calculate exponential backoff with jitter"""
        base_delay = self.default_retry_delay * (2 ** retry_count)
        jitter = random.uniform(0.8, 1.2)
        return min(int(base_delay * jitter), 3600)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called when task fails"""
        logger.error(f"Task {self.name} ({task_id}) failed: {exc}")

    def on_success(self, retval, task_id, args, kwargs):
        """Called when task succeeds"""
        logger.info(f"Task {self.name} ({task_id}) completed successfully")