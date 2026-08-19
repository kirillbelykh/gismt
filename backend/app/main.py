"""FastAPI application entrypoint"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from prometheus_client import make_asgi_app

from app.core.config import settings
from app.core.logging import configure_logging
from app.api.v1 import health, orders_web, camera

import os

# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------

configure_logging(debug=settings.DEBUG)

# ---------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------

BASE_DIR = os.path.dirname(__file__)
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
FRONTEND_DIR = os.path.join(BASE_DIR, "static", "frontend")

# ---------------------------------------------------------------------
# App
# ---------------------------------------------------------------------

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    debug=settings.DEBUG,
)

# ---------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------

templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ---------------------------------------------------------------------
# Static files (React build)
# ---------------------------------------------------------------------

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    assets_dir = os.path.join(FRONTEND_DIR, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

# ---------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ⚠️ в production ограничить
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------

app.include_router(health.router, prefix="/api/v1")
app.include_router(camera.router, prefix="/api/v1")
app.include_router(orders_web.router)

# ---------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------

app.mount("/metrics", make_asgi_app())

# ---------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/scanner", response_class=HTMLResponse)
async def scanner():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse(
            "<h1>React scanner not built</h1>",
            status_code=500,
        )
    return FileResponse(index_path)


@app.get("/api/v1/upload/")
async def redirect_legacy_upload():
    return RedirectResponse(url="/scanner")


# ---------------------------------------------------------------------
# SPA fallback (React Router)
# ---------------------------------------------------------------------

@app.get("/{path:path}")
async def spa_fallback(path: str):
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("Not found", status_code=404)
