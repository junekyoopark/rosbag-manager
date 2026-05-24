import uuid
from abc import ABC, abstractmethod
from pathlib import Path

import aiofiles
from fastapi import UploadFile

from app.config import settings


class StorageBackend(ABC):
    @abstractmethod
    async def save(self, file: UploadFile, bag_id: str) -> Path:
        ...

    @abstractmethod
    async def delete(self, path: str) -> None:
        ...


class LocalStorage(StorageBackend):
    def __init__(self, uploads_dir: str):
        self.uploads_dir = Path(uploads_dir)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, file: UploadFile, bag_id: str) -> Path:
        suffix = Path(file.filename).suffix.lower()
        dest = self.uploads_dir / f"{bag_id}{suffix}"
        async with aiofiles.open(dest, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                await f.write(chunk)
        return dest

    async def delete(self, path: str) -> None:
        p = Path(path)
        if p.exists():
            p.unlink(missing_ok=True)


def get_storage_backend() -> StorageBackend:
    if settings.STORAGE_BACKEND == "s3":
        raise NotImplementedError("S3 storage not yet implemented")
    return LocalStorage(settings.UPLOADS_DIR)
