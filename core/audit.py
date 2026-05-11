"""NDHGS-compliant audit middleware.

Every request that touches patient or admin data is recorded to the
append-only ``audit_logs`` MongoDB collection.  Audit writes are
best-effort: a failure is logged via loguru but NEVER surfaces to the
caller as an error.
"""
import re
from datetime import datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.security import verify_token
from utils.logger import logger

# ── Path rules ───────────────────────────────────────────────────────────────

_AUDIT_PREFIXES = (
    "/patients/",
    "/reports/",
    "/bp-readings/",
    "/admin/",
    "/doctor/",
)
_AUDIT_EXACT = {"/auth/login"}

_SKIP_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico"}

# Patient IDs always follow the format RMD-YY-NNN
_PATIENT_ID_RE = re.compile(r"RMD-\d{2}-\d{3,}")


def _should_audit(path: str, method: str) -> bool:
    if path in _SKIP_PATHS:
        return False
    if path.startswith("/docs") or path.startswith("/redoc") or path.startswith("/openapi"):
        return False
    # Skip webhook verification (GET /webhook is Meta's challenge-response)
    if path == "/webhook" and method == "GET":
        return False
    if path in _AUDIT_EXACT:
        return True
    return any(path.startswith(p) for p in _AUDIT_PREFIXES)


def _extract_patient_id(path: str) -> str | None:
    m = _PATIENT_ID_RE.search(path)
    return m.group(0) if m else None


def _extract_actor(request: Request) -> tuple[str, str]:
    """Return (actor_id, actor_role) from the Bearer token, or anonymous/unknown."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        payload = verify_token(auth[7:])
        if payload:
            return payload.get("user_id", "anonymous"), payload.get("role", "unknown")
    return "anonymous", "unknown"


# ── Middleware ────────────────────────────────────────────────────────────────

class AuditMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, db):
        super().__init__(app)
        self._db = db  # MongoDB wrapper instance (connected at startup)

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        method = request.method

        if not _should_audit(path, method):
            return await call_next(request)

        # Run the actual request first — audit is written after we know the status
        response = await call_next(request)

        try:
            actor_id, actor_role = _extract_actor(request)
            log_data = {
                "timestamp": datetime.utcnow(),
                "actor_id": actor_id,
                "actor_role": actor_role,
                "method": method,
                "endpoint": path,
                "patient_id": _extract_patient_id(path),
                "ip_address": request.client.host if request.client else "unknown",
                "user_agent": request.headers.get("User-Agent", ""),
                "response_status": response.status_code,
                "success": response.status_code < 400,
            }
            await self._db.create_audit_log(log_data)
        except Exception:
            # Audit failure must never break the request
            logger.opt(exception=True).warning("Audit log write failed — request continues normally")

        return response
