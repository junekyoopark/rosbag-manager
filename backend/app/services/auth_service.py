import uuid

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def authenticate(db: AsyncSession, username: str, password: str) -> User | None:
    user = await get_user_by_username(db, username)
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def create_user(
    db: AsyncSession,
    username: str,
    password: str,
    role: str = "user",
    email: str | None = None,
) -> User:
    user = User(
        id=uuid.uuid4(),
        username=username,
        email=email or None,
        hashed_password=hash_password(password),
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def list_users(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).order_by(User.created_at))
    return list(result.scalars().all())


async def delete_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    user = await get_user_by_id(db, user_id)
    if user:
        await db.delete(user)
        await db.commit()


async def set_user_role(db: AsyncSession, user_id: uuid.UUID, role: str) -> None:
    user = await get_user_by_id(db, user_id)
    if user:
        user.role = role
        await db.commit()


async def set_user_active(db: AsyncSession, user_id: uuid.UUID, is_active: bool) -> None:
    user = await get_user_by_id(db, user_id)
    if user:
        user.is_active = is_active
        await db.commit()


async def user_count(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(User))
    return result.scalar_one()
