import base64
import hashlib
from pathlib import Path

import httpx

from app.config import settings


def _fernet():
    from cryptography.fernet import Fernet
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


def encrypt_password(password: str) -> str:
    return _fernet().encrypt(password.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    return _fernet().decrypt(encrypted.encode()).decode()


_BAG_EXTENSIONS = {".bag", ".mcap", ".db3", ".zip"}


def synology_list_dir(dsm_url: str, sid: str, path: str, verify_ssl: bool) -> list[dict]:
    """Return subdirs and bag files at a NAS path."""
    with _client(verify_ssl) as client:
        r = client.get(
            f"{dsm_url}/webapi/entry.cgi",
            params={
                "api": "SYNO.FileStation.List",
                "version": "2",
                "method": "list",
                "folder_path": path,
                "filetype": "both",
                "sort_by": "name",
                "sort_direction": "ASC",
                "additional": '["size","time"]',
                "limit": 1000,
                "_sid": sid,
            },
        )
    data = r.json()
    if not data.get("success"):
        code = data.get("error", {}).get("code", "?")
        raise RuntimeError(f"Cannot list NAS folder (code {code})")
    items = data.get("data", {}).get("files", [])
    result = []
    for item in items:
        name = item.get("name", "")
        is_dir = item.get("isdir", False)
        full_path = item.get("path", "")
        additional = item.get("additional", {})
        size = additional.get("size", 0)
        mtime = additional.get("time", {}).get("mtime", 0)
        if is_dir or Path(name).suffix.lower() in _BAG_EXTENSIONS:
            result.append({"name": name, "path": full_path,
                           "is_dir": is_dir, "size": size, "mtime": mtime})
    return result


def synology_download(
    dsm_url: str,
    sid: str,
    nas_path: str,
    dest_path: Path,
    verify_ssl: bool,
    progress_cb=None,
) -> None:
    """Stream a file from NAS to a local path with optional progress callback."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with _client(verify_ssl) as client:
        with client.stream("GET", f"{dsm_url}/webapi/entry.cgi", params={
            "api": "SYNO.FileStation.Download",
            "version": "2",
            "method": "download",
            "path": nas_path,
            "mode": "download",
            "_sid": sid,
        }) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(dest_path, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb and total:
                        progress_cb(downloaded, total)


_UPLOAD_ERRORS: dict[int, str] = {
    105: "Permission denied — the account does not have access to this path",
    406: "Need admin privilege to upload to this system folder",
    407: "Not enough quota on the NAS volume",
    408: "Destination path not found — the shared folder does not exist on the NAS",
    409: "Read-only file system",
    414: "No write permission on the destination path",
    418: "Destination path is outside the permitted paths",
    419: "Could not obtain write permission on the destination",
}


def _client(verify_ssl: bool) -> httpx.Client:
    return httpx.Client(verify=verify_ssl, follow_redirects=True, timeout=7200)


def synology_list_shares(dsm_url: str, sid: str, verify_ssl: bool) -> list[str]:
    """Return a sorted list of top-level shared folder paths available to this user."""
    with _client(verify_ssl) as client:
        r = client.get(
            f"{dsm_url}/webapi/entry.cgi",
            params={
                "api": "SYNO.FileStation.List",
                "version": "2",
                "method": "list_share",
                "sort_by": "name",
                "sort_direction": "ASC",
                "limit": 200,
                "_sid": sid,
            },
        )
    data = r.json()
    if not data.get("success"):
        return []
    shares = data.get("data", {}).get("shares", [])
    return sorted(f"/{s['path'].strip('/')}" if s.get("path") else f"/{s['name']}"
                  for s in shares)


def synology_login(dsm_url: str, username: str, password: str, verify_ssl: bool) -> str:
    with _client(verify_ssl) as client:
        r = client.get(
            f"{dsm_url}/webapi/auth.cgi",
            params={
                "api": "SYNO.API.Auth",
                "version": "6",
                "method": "login",
                "account": username,
                "passwd": password,
                "session": "FileStation",
                "format": "sid",
            },
        )
        data = r.json()
    if not data.get("success"):
        code = data.get("error", {}).get("code", "?")
        raise RuntimeError(f"Synology login failed (error code {code})")
    return data["data"]["sid"]


def synology_logout(dsm_url: str, sid: str, verify_ssl: bool) -> None:
    try:
        with _client(verify_ssl) as client:
            client.get(
                f"{dsm_url}/webapi/auth.cgi",
                params={"api": "SYNO.API.Auth", "version": "1", "method": "logout",
                        "session": "FileStation", "_sid": sid},
            )
    except Exception:
        pass


class _ProgressFile:
    """File-like wrapper that fires a progress callback as httpx reads chunks."""

    def __init__(self, path: Path, progress_cb):
        self._f = open(path, "rb")
        self._total = path.stat().st_size
        self._sent = 0
        self._cb = progress_cb

    def read(self, size: int = -1) -> bytes:
        chunk = self._f.read(size)
        if chunk and self._cb:
            self._sent += len(chunk)
            self._cb(self._sent, self._total)
        return chunk

    def close(self) -> None:
        self._f.close()


def synology_upload(
    dsm_url: str,
    sid: str,
    upload_path: str,
    filename: str,
    file_path: Path,
    verify_ssl: bool,
    progress_cb=None,
) -> None:
    pf = _ProgressFile(file_path, progress_cb)
    try:
        with _client(verify_ssl) as client:
            # _sid must be a query param for FileStation.Upload — embedding it in
            # multipart form data is silently ignored on many DSM versions (→ error 119).
            r = client.post(
                f"{dsm_url}/webapi/entry.cgi",
                params={"_sid": sid},
                data={
                    "api": "SYNO.FileStation.Upload",
                    "version": "2",
                    "method": "upload",
                    "path": upload_path,
                    "create_parents": "true",
                    "overwrite": "true",
                },
                files={"file": (filename, pf, "application/octet-stream")},
            )
    finally:
        pf.close()
    result = r.json()
    if not result.get("success"):
        code = result.get("error", {}).get("code", "?")
        desc = _UPLOAD_ERRORS.get(code, f"error code {code}")
        raise RuntimeError(f"Synology upload failed: {desc}")
