"""FastAPI application for the local stock-analysis web UI."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .jobs import manager
from .routes import analyze, history, results

_WEB_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _WEB_DIR / "static"
_INDEX = _WEB_DIR / "templates" / "index.html"

app = FastAPI(title="Stock Analysis", docs_url="/api/docs", openapi_url="/api/openapi.json")

app.include_router(analyze.router)
app.include_router(history.router)
app.include_router(results.router)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/api/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "active_job_id": manager.active_id})


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_INDEX, media_type="text/html")
