"""Erreurs métier. L'API renvoie `{"error": {"code", "message"}}` ; l'interface traduit le code."""

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    status = 400
    code = "invalid"

    def __init__(self, message: str = "", code: str | None = None, **details: object) -> None:
        super().__init__(message or self.code)
        self.message = message
        if code:
            self.code = code
        self.details = details


class NotFound(AppError):
    """Aussi renvoyée pour la donnée d'un autre utilisateur : on ne confirme pas qu'elle existe (RG-01)."""

    status = 404
    code = "not_found"


class Unauthorized(AppError):
    status = 401
    code = "unauthorized"


class Forbidden(AppError):
    status = 403
    code = "forbidden"


class Conflict(AppError):
    status = 409
    code = "conflict"


class TooManyRequests(AppError):
    status = 429
    code = "rate_limited"


class QuotaExceeded(AppError):
    """RG-20 : quota d'IA atteint ; la saisie manuelle reste possible."""

    status = 429
    code = "ai_quota_exceeded"


class AIUnavailable(AppError):
    """IA-04 : l'IA est indisponible ou sa réponse est inexploitable ; rien n'est appliqué."""

    status = 503
    code = "ai_unavailable"


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    body = {"code": exc.code, "message": exc.message, **exc.details}
    return JSONResponse({"error": body}, status_code=exc.status)
