"""Application FastAPI : API sous /api/v1 (T-02), interface compilée servie en fichiers statiques."""

from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.middleware.gzip import GZipMiddleware

from app.api import admin, auth, catalog, collections, me, photos, public, purchases
from app.config import get_settings
from app.deps import Db
from app.errors import AppError, app_error_handler

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CSP = (
    "default-src 'self'; img-src 'self' data: blob: https:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


def create_app() -> FastAPI:
    settings = get_settings()
    dev = settings.env in ("dev", "test")
    app = FastAPI(
        title=settings.product_name,
        version=settings.app_version,
        docs_url="/api/docs" if dev else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if dev else None,
    )
    app.add_exception_handler(AppError, app_error_handler)
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    allowed_origin = "{0.scheme}://{0.netloc}".format(urlsplit(settings.app_url))

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # S-03 (CSRF) : une requête modifiante venue d'un navigateur doit provenir de l'application.
        if request.method in UNSAFE_METHODS:
            origin = request.headers.get("origin")
            own = f"{request.url.scheme}://{request.headers.get('host', '')}"
            if origin and origin not in (allowed_origin, own):
                return JSONResponse({"error": {"code": "bad_origin", "message": ""}}, status_code=403)
        response = await call_next(request)
        response.headers["X-App-Version"] = (
            settings.app_version
        )  # l'interface se met à jour d'elle-même (8.3)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(self), geolocation=(), microphone=()"
        if not request.url.path.startswith("/api/docs"):
            response.headers["Content-Security-Policy"] = CSP
        if settings.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.url.path.startswith("/api/") and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"  # données privées : jamais en cache partagé
        return response

    api = APIRouter(prefix="/api/v1")

    @api.get("/health", tags=["technique"])
    def health(db: Db) -> dict:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "version": settings.app_version}

    for module in (auth, me, catalog, collections, purchases, photos, public, admin):
        api.include_router(module.router)
    app.include_router(api)

    @app.api_route(
        "/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False
    )
    def api_not_found(path: str):
        return JSONResponse({"error": {"code": "not_found", "message": ""}}, status_code=404)

    dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            """Chaque écran a une adresse propre (F-03) : toute adresse inconnue rend l'application."""
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(dist):
                return FileResponse(candidate)
            return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
