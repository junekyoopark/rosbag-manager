import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.routers import bags, jobs, viewer, health
from app.routers import auth as auth_router
from app.routers import admin as admin_router
from app.routers import nas as nas_router
from app.config import settings

# Paths that don't require authentication
_PUBLIC_PREFIXES = ("/login", "/auth/", "/static/", "/healthz", "/favicon")


class AuthMiddleware(BaseHTTPMiddleware):
    """Load current user from session into request.state; redirect if unauthenticated."""

    async def dispatch(self, request: Request, call_next):
        user_id_str = request.session.get("user_id")
        request.state.current_user = None

        if user_id_str:
            from app.db.session import AsyncSessionLocal
            from app.services.auth_service import get_user_by_id
            try:
                async with AsyncSessionLocal() as db:
                    user = await get_user_by_id(db, uuid.UUID(user_id_str))
                    request.state.current_user = user if (user and user.is_active) else None
            except Exception:
                request.session.pop("user_id", None)

        path = request.url.path
        if any(path == p or path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        if request.state.current_user is None:
            if request.headers.get("HX-Request"):
                from starlette.responses import Response
                return Response(status_code=401, headers={"HX-Redirect": f"/login?next={path}"})
            return RedirectResponse(url=f"/login?next={path}", status_code=303)

        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Bootstrap initial admin user if env vars are set and no users exist yet
    admin_user = settings.INITIAL_ADMIN_USERNAME
    admin_pass = settings.INITIAL_ADMIN_PASSWORD
    if admin_user and admin_pass:
        from app.db.session import AsyncSessionLocal
        from app.services.auth_service import user_count, create_user
        async with AsyncSessionLocal() as db:
            try:
                count = await user_count(db)
                if count == 0:
                    await create_user(db, admin_user, admin_pass, role="admin")
            except Exception:
                pass  # table may not exist yet (before first migration)
    yield


app = FastAPI(title="USRG ROSBAG Manager", lifespan=lifespan)

app.add_middleware(AuthMiddleware)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY, https_only=False)

app.include_router(health.router)
app.include_router(bags.router, prefix="/api/bags", tags=["bags"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(viewer.router, prefix="/bags", tags=["viewer"])
app.include_router(auth_router.router, tags=["auth"])
app.include_router(admin_router.router, prefix="/admin/users", tags=["admin"])
app.include_router(nas_router.router, prefix="/nas", tags=["nas"])

app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

templates = Jinja2Templates(directory="frontend/templates")


def format_duration(seconds: float) -> str:
    if seconds is None:
        return "unknown"
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def format_bytes(n: int) -> str:
    if n is None:
        return ""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def timeago(dt: datetime) -> str:
    if dt is None:
        return ""
    delta = datetime.now(timezone.utc) - dt
    if delta.days > 30:
        return dt.strftime("%Y-%m-%d")
    if delta.days > 0:
        return f"{delta.days}d ago"
    hours = delta.seconds // 3600
    if hours > 0:
        return f"{hours}h ago"
    minutes = delta.seconds // 60
    return f"{minutes}m ago"


TOPIC_CATEGORY_MAP = {
    "sensor_msgs/msg/Image": "image",
    "sensor_msgs/msg/CompressedImage": "image",
    "sensor_msgs/msg/PointCloud2": "pointcloud",
    "sensor_msgs/msg/Imu": "imu",
    "sensor_msgs/msg/NavSatFix": "gps",
    "tf2_msgs/msg/TFMessage": "tf",
    "geometry_msgs/msg/TransformStamped": "tf",
    "nav_msgs/msg/Odometry": "odom",
}


def topic_category(msg_type: str) -> str:
    return TOPIC_CATEGORY_MAP.get(msg_type, "other")


def format_number(n) -> str:
    if n is None:
        return ""
    return f"{int(n):,}"


templates.env.filters["format_duration"] = format_duration
templates.env.filters["format_bytes"] = format_bytes
templates.env.filters["timeago"] = timeago
templates.env.filters["topic_category"] = topic_category
templates.env.filters["format_number"] = format_number

# Share templates instance with routers that render partials
viewer.templates = templates
bags.templates = templates
auth_router.templates = templates
admin_router.templates = templates
nas_router.templates = templates


@app.get("/", response_class=HTMLResponse)
async def library_page(request: Request):
    from app.db.session import AsyncSessionLocal
    from app.services.bag_service import list_bags

    async with AsyncSessionLocal() as db:
        total, bags_list = await list_bags(db, None, None, None, "or", None, "created_at_desc", 20, 0)

    user = getattr(request.state, "current_user", None)
    can_nas = bool(user and (user.role == "admin" or getattr(user, "can_upload_to_nas", False)))
    return templates.TemplateResponse(
        request,
        "library.html",
        {"bags": bags_list, "total": total, "rerun_version": settings.RERUN_VERSION, "can_nas": can_nas},
    )


@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    user = getattr(request.state, "current_user", None)
    if not user or user.role != "admin":
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request,
        "upload.html",
        {"max_size_gb": settings.MAX_UPLOAD_SIZE_GB},
    )


@app.get("/info", response_class=HTMLResponse)
async def info_page(request: Request):
    return templates.TemplateResponse(
        request,
        "info.html",
        {"max_size_gb": settings.MAX_UPLOAD_SIZE_GB, "rerun_version": settings.RERUN_VERSION},
    )
