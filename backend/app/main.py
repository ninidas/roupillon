from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from . import backup
from . import models  # noqa: F401  (tables)
from .api import router
from .database import Base, engine, migrate
from .limiter import limiter

Base.metadata.create_all(bind=engine)
migrate()
backup.start()

app = FastAPI(title="Roupillon", docs_url=None, redoc_url=None, openapi_url=None)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.include_router(router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    if request.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


DIST = Path(__file__).parent.parent / "frontend_dist"
if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(DIST / "assets")), name="assets")


@app.get("/{full_path:path}")
async def spa(full_path: str):
    if full_path == "api" or full_path.startswith("api/"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    if not DIST.exists():
        return JSONResponse({"detail": "Frontend not built"}, status_code=404)
    try:
        candidate = (DIST / full_path).resolve()
    except (ValueError, OSError):
        return FileResponse(str(DIST / "index.html"))
    # Jamais de fichier hors du dossier du front
    if full_path and candidate.is_relative_to(DIST.resolve()) and candidate.is_file():
        headers = {}
        if full_path == "sw.js" or full_path.endswith(".webmanifest"):
            headers["Cache-Control"] = "no-cache"
        return FileResponse(str(candidate), headers=headers)
    return FileResponse(str(DIST / "index.html"), headers={"Cache-Control": "no-cache"})
