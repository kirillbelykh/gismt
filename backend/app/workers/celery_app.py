from celery import Celery
from app.core.config import settings

# Создаём приложение Celery
app = Celery(
    'aggr_system',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=['app.workers.tasks']  # важно: подхватываются все задачи из tasks.py
)

# =============================================================================
# Глобальные настройки Celery — лучшие практики + фикс очередей
# =============================================================================
app.conf.update(
    # Сериализация
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],

    # Часовой пояс
    timezone='Europe/Moscow',
    enable_utc=False,  # лучше False + явно указанный timezone

    # Поведение при потере воркера
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # критично для acks_late
    task_track_started=True,

    # Таймауты и надёжность
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=10,
    broker_connection_max_retries=5,

    # Результаты
    result_expires=3600,  # 1 час
    result_backend_transport_options={'visibility_timeout': 3600},

    # Мониторинг и события
    worker_send_task_events=True,
    task_send_sent_event=True,

    # === САМОЕ ГЛАВНОЕ: ИСПРАВЛЕНИЕ ОЧЕРЕДЕЙ ===
    task_default_queue='default',           # ← теперь очередь по умолчанию — "default"
    task_create_missing_queues=True,        # ← автоматически создаёт очереди, если их нет
    task_queues={
        'default': {
            'exchange': 'default',
            'routing_key': 'default',
        },
        'high_priority': {
            'exchange': 'high_priority',
            'routing_key': 'high_priority',
        },
        'low_priority': {
            'exchange': 'low_priority',
            'routing_key': 'low_priority',
        },
    },
    task_routes={
        'app.workers.tasks.order_codes_task': {'queue': 'high_priority'},
        'app.workers.tasks.send_apply_report_task': {'queue': 'default'},
        'app.workers.tasks.SendAggregationReportTask': {'queue': 'default'},     # ← важно
        'app.workers.tasks.SendIntroductionTask': {'queue': 'default'},          # ← важно
        'app.workers.tasks.*': {'queue': 'default'},  # всё остальное — в default
    },
)

# Опционально: красивый вывод при запуске
@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    pass  # можно будет добавить beat-задачи позже

if __name__ == '__main__':
    app.start()