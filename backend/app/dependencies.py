import uuid
from typing import AsyncGenerator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.services.storage import StorageBackend, get_storage_backend


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


def get_storage() -> StorageBackend:
    return get_storage_backend()


async def get_current_user(request: Request):
    """Returns the User loaded by AuthMiddleware, or None."""
    return getattr(request.state, "current_user", None)


async def require_admin(user=Depends(get_current_user)):
    if user is None or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
