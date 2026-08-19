# Web-сканер GISMT

React-интерфейс для сканирования DataMatrix-кодов камерой, проверки состава коробки и отправки агрегации в GISMT backend.

## Запуск

```bash
npm ci
npm run dev
```

Локальный Vite-сервер проксирует запросы `/api/v1` на `http://localhost:8000`.

## Проверки и сборка

```bash
npm run lint
npm run build
```

Production-сборка создаётся в `../backend/app/static/frontend`, откуда её обслуживает FastAPI. Для доступа к камере используйте `localhost` либо HTTPS и разрешите браузеру работу с камерой.
