"""FastAPI application for the local stock-analysis web UI."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .jobs import manager
from .routes import alerts, analyze, history, portfolio, results, watchlist

_WEB_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _WEB_DIR / "static"
_INDEX = _WEB_DIR / "templates" / "index.html"


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Resume any jobs still queued when the process last stopped.
    manager.recover()
    # Backfill rec_history from pre-existing report snapshots (idempotent —
    # cheap no-op after the first run once every row already exists).
    try:
        from .reports_index import backfill_rec_history

        backfill_rec_history()
    except Exception:
        pass  # best-effort; never block startup
    yield


app = FastAPI(
    title="Stock Analysis", docs_url="/api/docs", openapi_url="/api/openapi.json",
    lifespan=_lifespan,
)

app.include_router(analyze.router)
app.include_router(history.router)
app.include_router(results.router)
app.include_router(alerts.router)
app.include_router(portfolio.router)
app.include_router(watchlist.router)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.middleware("http")
async def _revalidate_assets(request, call_next):
    """Make the browser revalidate our assets and per-symbol reports so edits and
    re-runs always show fresh content (cheap 304s on a localhost single-user app —
    avoids stale cached JS/CSS and stale embedded reports after a re-analysis)."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static") or path.startswith("/api/reports"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/api/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "active_job_id": manager.active_id})


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_INDEX, media_type="text/html")
