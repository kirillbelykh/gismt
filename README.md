# GISMT — система агрегации кодов маркировки

Система для заказа, сканирования и агрегации GS1 DataMatrix-кодов с последующей передачей отчётов в сервисы «Честного знака». Проект объединяет web-сканер, FastAPI backend, фоновые Celery-задачи и отдельный сервис электронной подписи CryptoPro.

## Возможности

- создание и сопровождение заказов кодов маркировки;
- импорт номенклатуры и поиск продукции по GTIN;
- сканирование нескольких DataMatrix-кодов камерой устройства;
- проверка кодов и защита от повторного использования;
- генерация SSCC и формирование коробок;
- последовательная отправка отчётов о нанесении, агрегации и вводе в оборот;
- sandbox- и mock-режимы интеграции с CRPT;
- фоновые задачи с Redis/Celery и журналом выполнения;
- Prometheus-метрики и структурированные журналы.

## Компоненты

| Каталог | Назначение |
|---|---|
| `backend/` | FastAPI API, PostgreSQL-модели, Alembic, сервисы и Celery-задачи |
| `frontend/` | React/Vite web-сканер для камеры мобильного устройства или рабочей станции |
| `signer_service/` | Локальный HTTP-мост к CryptoPro/cryptcp для подписи документов |
| `scanner/` | Указатель на отдельный нативный ZXing-сканер |
| `docs/` | Архитектура и инженерные задачи |
| `compose.yaml` | PostgreSQL, Redis, API и Celery worker |

Подробная последовательность операций описана в [документе по архитектуре](docs/architecture.md).

## Быстрый запуск backend

Нужны Docker и Docker Compose.

```bash
cp .env.example .env
# заполните все обязательные значения в .env
docker compose up --build
```

API будет доступен на `http://localhost:8000`, документация OpenAPI — на `http://localhost:8000/docs`, метрики — на `http://localhost:8000/metrics`.

До запуска задайте параметры PostgreSQL и Redis, случайные `SECRET_KEY` и служебные токены, идентификаторы CRPT/OMS, отпечаток сертификата, GS1-префикс и параметры сервиса подписи. Пустые значения в `.env.example` намеренны. Сначала используйте sandbox- или mock-режим; production-секреты в репозитории отсутствуют.

## Web-сканер

```bash
cd frontend
npm ci
npm run dev
```

Vite проксирует `/api/v1` на локальный backend. Production-сборка помещается в `backend/app/static/frontend` и затем обслуживается FastAPI:

```bash
npm run build
```

Для сканирования браузеру требуется разрешение на камеру и безопасный контекст: `localhost` либо HTTPS.

## Сервис подписи

Сервис подписи запускается на Windows-машине, где установлены CryptoPro CSP/cryptcp и сертификат организации.

```powershell
cd signer_service
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
copy .env.example .env
# заполните CRPT_THUMBPRINT, CRPT_MOCK_MODE и SIGNER_TOKEN в .env
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8010
```

Передайте тот же `SIGNER_TOKEN` backend через `CRPT_SIGNER_TOKEN`. Не открывайте этот сервис в интернет без дополнительной сетевой защиты.

## Разработка и проверки

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements.dev.txt
pytest app/tests
```

Frontend:

```bash
cd frontend
npm ci
npm run build
```

Сборка TypeScript проверяется в CI. В текущем ESLint-конфиге остаются замечания к унаследованному коду сканера; они не скрыты и вынесены за пределы обязательной проверки до отдельной чистки.

Синтаксис отдельных Python-компонентов можно проверить без подключения к внешним сервисам:

```bash
python -m compileall backend/app signer_service
```

## Миграции

```bash
cd backend
alembic upgrade head
```

Миграции используют параметры PostgreSQL из корневого `.env` при запуске через Compose либо из окружения текущего процесса при локальной разработке.

## Ограничения

- Реальная подпись и полный цикл CRPT требуют Windows, CryptoPro и сертификата организации.
- Интеграционные сценарии нельзя полностью воспроизвести без учётных данных sandbox/production CRPT.
- Текущая авторизация API основана на едином служебном токене и требует усиления перед доступом из недоверенной сети.
- Нативный сканер развивается отдельно, чтобы не дублировать C++-код и его зависимости в этом репозитории.
