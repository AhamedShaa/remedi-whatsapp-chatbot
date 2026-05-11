from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from core.security import decode_token

_bearer = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    return decode_token(credentials.credentials)


def require_role(*roles: str):
    """Return a FastAPI dependency that enforces one of the given roles.

    Usage:
        current_user: dict = Depends(require_role("admin"))
        current_user: dict = Depends(require_role("doctor", "admin"))
    """
    async def dependency(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access requires role: {' or '.join(roles)}",
            )
        return user
    return dependency


# Convenience shortcuts kept for backwards compatibility
async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


async def require_doctor(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in ("admin", "doctor"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Doctor access required")
    return user


async def get_db(request: Request):
    """Inject the shared MongoDB instance from app.state."""
    return request.app.state.db
