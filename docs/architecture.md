# Архитектура системы агрегации

## Обзор

Система состоит из следующих компонентов:

1. **Backend (FastAPI)** - REST API для управления заказами, коробками и агрегацией
2. **Worker (Celery)** - Фоновые задачи для интеграции с CRPT
3. **Aggregation Client** - Клиент для сканирования DataMatrix кодов
4. **PostgreSQL** - База данных
5. **Redis** - Брокер сообщений для Celery

## Последовательность операций

### 1. Создание заказа кодов

```
Client → POST /api/v1/orders
  ↓
Backend создаёт Order (status=ORDERING)
  ↓
Enqueue: order_codes_task(order_id)
  ↓
Worker:
  - create_emission_order() → CRPT SUZ
  - wait_for_codes()
  - get_codes()
  - store_codes() → DB
  - update_order(status=READY)
```

### 2. Сканирование коробки

```
Aggregation Client → POST /api/v1/boxes/scan
  ↓
Backend:
  - Валидация кодов (принадлежность order, статус)
  - Резервирование кодов (status=RESERVED)
  - Генерация SSCC (атомарно через DB)
  - Создание Box и BoxItems
  ↓
Enqueue: send_apply_report(box_id)
  ↓
Return: {box_id, sscc, print_url}
```

### 3. Фоновая обработка коробки

```
send_apply_report(box_id):
  - prepare_apply_payload()
  - send_utilisation_report() → CRPT SUZ
  - wait_for_report_status()
  - update_box(status=APPLY_SENT)
  - Enqueue: send_aggregation_report(box_id)

send_aggregation_report(box_id):
  - get_box_items()
  - send_aggregation_report() → CRPT SUZ
  - update_box(status=AGGREGATED)
  - Enqueue: send_introduction(box_id)

send_introduction(box_id):
  - send_introduction_report() → CRPT TRUE API
  - update_box(status=TURNOVER_DONE)
```

## Схема базы данных

### Основные таблицы

- **orders** - Заказы кодов
- **marking_codes** - Коды маркировки (raw + SNTIN)
- **boxes** - Коробки агрегации
- **box_items** - Связь коробок и кодов
- **sscc_counters** - Счётчики для генерации SSCC
- **task_log** - Логи фоновых задач

### Индексы

- `marking_codes.code_raw` - Быстрый поиск по raw коду
- `marking_codes.sntin` - Быстрый поиск по SNTIN
- `task_log(task_type, related_id)` - Идемпотентность задач

## Retry и обработка ошибок

### Идемпотентность

Задачи проверяют `task_log` перед выполнением:
- Если задача уже успешно выполнена → skip
- Если задача в процессе → retry только при ошибке


## SSCC генерация

### Формат

- **Numeric SSCC**: 26 цифр
- **Mod10 check digit**: Стандартный алгоритм GS1

### Атомарность

Используется PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` для атомарного инкремента счётчика.

## Интеграция с CRPT

### SUZ API

- `create_emission_order()` - Создание заказа эмиссии
- `get_emission_status()` - Статус заказа
- `get_codes()` - Получение кодов
- `send_utilisation_report()` - Отчёт о нанесении
- `send_aggregation_report()` - Отчёт об агрегации

### TRUE API

- `get_token()` - Аутентификация
- `send_introduction_report()` - Ввод в оборот

### Подписание

Все запросы к SUZ подписываются через CryptoPro CSP:
- Откреплённая подпись (`detached=True`)
- CAdES-BES для TRUE API (`cadesbes=True`)

## Безопасность

- Токены только из переменных окружения
- API защищён через `API_SUPERUSER_TOKEN` (для production использовать JWT)
- Подписи через CryptoPro (не хранятся в коде)

## Мониторинг

- **Prometheus metrics**: `/metrics`
- **Structured logging**: JSON формат
- **Task logs**: В БД (`task_log`)

## Масштабирование

- **Backend**: Горизонтальное масштабирование (stateless)
- **Worker**: Множественные инстансы (Celery распределяет задачи)
- **Redis**: Кластер для production
- **PostgreSQL**: Репликация для production
