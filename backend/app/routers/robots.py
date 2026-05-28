import asyncio
import ipaddress
import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import get_db, get_current_user, require_admin, require_robot_manager
from app.models.network import Network
from app.models.robot import Robot
from app.models.robot_access import RobotAccess

admin_router = APIRouter()
live_router = APIRouter()
templates = None  # set by main.py

_DEFAULT_PORT = 8765


# ── Access helpers ────────────────────────────────────────────────

async def _accessible_robot_ids(user, db: AsyncSession) -> set[int] | None:
    """None means all robots accessible (admin). Otherwise returns set of robot IDs."""
    if user is None:
        return set()
    if user.role == "admin":
        return None
    r1 = await db.execute(select(Robot.id).where(Robot.added_by_id == user.id))
    r2 = await db.execute(select(RobotAccess.robot_id).where(RobotAccess.user_id == user.id))
    return {row[0] for row in r1.all()} | {row[0] for row in r2.all()}


async def _require_robot_access(robot_id: int, user, db: AsyncSession):
    if user is None:
        return False
    if user.role == "admin":
        return True
    robot = await db.get(Robot, robot_id)
    if robot and robot.added_by_id == user.id:
        return True
    acc = await db.execute(
        select(RobotAccess).where(RobotAccess.robot_id == robot_id, RobotAccess.user_id == user.id)
    )
    return acc.scalar_one_or_none() is not None


async def _require_robot_manage(robot_id: int, user, db: AsyncSession):
    """Can the user manage access for this robot? creator or admin."""
    if user is None:
        return False
    if user.role == "admin":
        return True
    robot = await db.get(Robot, robot_id)
    return robot and robot.added_by_id == user.id


# ── Port / URL helpers ────────────────────────────────────────────

async def _check_port(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


async def _check_robots_online(robots: list[Robot]) -> dict[int, bool]:
    if not robots:
        return {}
    results = await asyncio.gather(
        *[_check_port(_host_from_url(r.ws_url), _port_from_url(r.ws_url)) for r in robots],
        return_exceptions=True,
    )
    return {r.id: (res is True) for r, res in zip(robots, results)}


def _host_from_url(ws_url: str) -> str:
    try:
        return ws_url.split("://", 1)[1].split("/")[0].rsplit(":", 1)[0]
    except Exception:
        return ws_url


def _port_from_url(ws_url: str) -> int:
    try:
        return int(ws_url.split("://", 1)[1].split("/")[0].rsplit(":", 1)[1])
    except Exception:
        return _DEFAULT_PORT


def _normalise_ws_url(ws_url: str) -> str:
    ws_url = ws_url.strip()
    if not ws_url.startswith(("ws://", "wss://")):
        ws_url = f"ws://{ws_url}"
    return ws_url


# ── Robot management page ─────────────────────────────────────────

@admin_router.get("", response_class=HTMLResponse)
async def robots_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_robot_manager),
):
    result = await db.execute(
        select(Network).order_by(Network.name).options(selectinload(Network.robots))
    )
    networks = result.scalars().all()

    ungrouped_result = await db.execute(
        select(Robot).where(Robot.network_id.is_(None)).order_by(Robot.name)
    )
    ungrouped = ungrouped_result.scalars().all()

    all_robots = [r for n in networks for r in n.robots] + list(ungrouped)
    online = await _check_robots_online(all_robots)

    # For each robot, load granted users
    robot_access: dict[int, list] = {}
    for r in all_robots:
        res = await db.execute(
            select(RobotAccess).where(RobotAccess.robot_id == r.id)
        )
        robot_access[r.id] = res.scalars().all()

    # All users for grant dropdown
    from app.models.user import User
    users_res = await db.execute(select(User).where(User.is_active == True).order_by(User.username))
    all_users = users_res.scalars().all()

    return templates.TemplateResponse(
        request,
        "robots.html",
        {
            "networks": networks,
            "ungrouped": ungrouped,
            "online": online,
            "robot_access": robot_access,
            "all_users": all_users,
            "current_user": user,
        },
    )


# ── Network CRUD ──────────────────────────────────────────────────

@admin_router.post("/networks/create")
async def create_network(
    name: str = Form(...),
    scan_subnet: str = Form(""),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_robot_manager),
):
    name = name.strip()
    if name:
        existing = await db.execute(select(Network).where(Network.name == name))
        if not existing.scalar_one_or_none():
            db.add(Network(name=name, scan_subnet=scan_subnet.strip()))
            await db.commit()
    return RedirectResponse(url="/robots", status_code=303)


@admin_router.post("/networks/{network_id}/delete")
async def delete_network(
    network_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_robot_manager),
):
    net = await db.get(Network, network_id)
    if net:
        await db.delete(net)
        await db.commit()
    return RedirectResponse(url="/robots", status_code=303)


@admin_router.post("/networks/{network_id}/update-subnet")
async def update_subnet(
    network_id: int,
    scan_subnet: str = Form(""),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_robot_manager),
):
    net = await db.get(Network, network_id)
    if net:
        net.scan_subnet = scan_subnet.strip()
        await db.commit()
    return RedirectResponse(url="/robots", status_code=303)


@admin_router.get("/networks/{network_id}/scan")
async def scan_network(
    network_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_robot_manager),
):
    net = await db.get(Network, network_id)
    if not net:
        return JSONResponse({"error": "Network not found."}, status_code=404)
    if not net.scan_subnet:
        return JSONResponse({"error": "No scan subnet configured for this network."}, status_code=400)
    try:
        network = ipaddress.ip_network(net.scan_subnet, strict=False)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    hosts = list(network.hosts())
    results = await asyncio.gather(
        *[_check_port(str(ip), _DEFAULT_PORT) for ip in hosts],
        return_exceptions=True,
    )
    found = [
        {"ip": str(ip), "ws_url": f"ws://{ip}:{_DEFAULT_PORT}"}
        for ip, ok in zip(hosts, results)
        if ok is True
    ]
    return JSONResponse(found)


# ── Robot CRUD ────────────────────────────────────────────────────

@admin_router.post("/create")
async def create_robot(
    name: str = Form(...),
    ws_url: str = Form(...),
    network_id: str = Form(""),
    use_proxy: str = Form("on"),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_robot_manager),
):
    name = name.strip()
    ws_url = _normalise_ws_url(ws_url)
    net_id = int(network_id) if network_id.strip() else None
    existing = await db.execute(select(Robot).where(Robot.name == name))
    if not existing.scalar_one_or_none():
        db.add(Robot(name=name, ws_url=ws_url, network_id=net_id, added_by_id=user.id, use_proxy=use_proxy == "on"))
        await db.commit()
    return RedirectResponse(url="/robots", status_code=303)


@admin_router.post("/{robot_id}/toggle-proxy")
async def toggle_robot_proxy(
    robot_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_robot_manager),
):
    robot = await db.get(Robot, robot_id)
    if robot:
        robot.use_proxy = not robot.use_proxy
        await db.commit()
    return RedirectResponse(url="/robots", status_code=303)


@admin_router.post("/{robot_id}/update-url")
async def update_robot_url(
    robot_id: int,
    ws_url: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_robot_manager),
):
    robot = await db.get(Robot, robot_id)
    if robot:
        robot.ws_url = _normalise_ws_url(ws_url)
        await db.commit()
    return RedirectResponse(url="/robots", status_code=303)


@admin_router.post("/{robot_id}/update-layout")
async def update_robot_layout(
    robot_id: int,
    layout_id: str = Form(""),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_robot_manager),
):
    robot = await db.get(Robot, robot_id)
    if robot:
        robot.layout_id = int(layout_id) if layout_id else None
        await db.commit()
    return RedirectResponse(url="/live", status_code=303)


@admin_router.post("/{robot_id}/delete")
async def delete_robot(
    robot_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_robot_manager),
):
    robot = await db.get(Robot, robot_id)
    if robot:
        await db.delete(robot)
        await db.commit()
    return RedirectResponse(url="/robots", status_code=303)


# ── Per-robot access management ───────────────────────────────────

@admin_router.post("/{robot_id}/access/grant")
async def grant_access(
    robot_id: int,
    user_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not await _require_robot_manage(robot_id, current_user, db):
        return JSONResponse({"error": "Not allowed"}, status_code=403)
    uid = uuid.UUID(user_id)
    existing = await db.execute(
        select(RobotAccess).where(RobotAccess.robot_id == robot_id, RobotAccess.user_id == uid)
    )
    if not existing.scalar_one_or_none():
        db.add(RobotAccess(robot_id=robot_id, user_id=uid, granted_by_id=current_user.id))
        await db.commit()
    return RedirectResponse(url="/robots", status_code=303)


@admin_router.post("/{robot_id}/access/revoke")
async def revoke_access(
    robot_id: int,
    user_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not await _require_robot_manage(robot_id, current_user, db):
        return JSONResponse({"error": "Not allowed"}, status_code=403)
    uid = uuid.UUID(user_id)
    acc = await db.execute(
        select(RobotAccess).where(RobotAccess.robot_id == robot_id, RobotAccess.user_id == uid)
    )
    row = acc.scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()
    return RedirectResponse(url="/robots", status_code=303)


# ── SFTP browse ───────────────────────────────────────────────────

class SFTPBrowseIn(BaseModel):
    username: str
    password: str
    path: str = "."


@admin_router.post("/{robot_id}/sftp/browse")
async def sftp_browse(
    robot_id: int,
    body: SFTPBrowseIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    if not await _require_robot_access(robot_id, user, db):
        return JSONResponse({"error": "Access denied"}, status_code=403)
    robot = await db.get(Robot, robot_id)
    if not robot:
        return JSONResponse({"error": "Robot not found"}, status_code=404)

    ssh_host = _host_from_url(robot.ws_url)

    import paramiko

    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: ssh.connect(ssh_host, username=body.username, password=body.password, timeout=8, banner_timeout=8),
        )
        sftp = await asyncio.get_event_loop().run_in_executor(None, ssh.open_sftp)

        # Resolve home dir
        path = body.path
        if path in (".", "", "~"):
            _, stdout, _ = ssh.exec_command("echo $HOME")
            path = (await asyncio.get_event_loop().run_in_executor(None, stdout.read)).decode().strip() or "/home/" + body.username

        entries_raw = await asyncio.get_event_loop().run_in_executor(None, lambda: sftp.listdir_attr(path))
        sftp.close()
        ssh.close()

        import stat as _stat
        entries = []
        for e in sorted(entries_raw, key=lambda x: (not _stat.S_ISDIR(x.st_mode), x.filename.lower())):
            is_dir = _stat.S_ISDIR(e.st_mode)
            name = e.filename
            if name.startswith("."):
                continue
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if not is_dir and ext not in ("bag", "db3", "mcap", "zip"):
                continue
            entries.append({
                "name": name,
                "path": path.rstrip("/") + "/" + name,
                "is_dir": is_dir,
                "size": e.st_size or 0,
                "mtime": e.st_mtime or 0,
            })

        return JSONResponse({"path": path, "items": entries})

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


# ── SFTP import ───────────────────────────────────────────────────

class SFTPImportIn(BaseModel):
    username: str
    password: str
    path: str
    name: str | None = None
    description: str | None = None
    tags: list[str] = []
    team: list[str] = []


@admin_router.post("/{robot_id}/sftp/import")
async def sftp_import(
    robot_id: int,
    body: SFTPImportIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    if not await _require_robot_access(robot_id, user, db):
        return JSONResponse({"error": "Access denied"}, status_code=403)
    robot = await db.get(Robot, robot_id)
    if not robot:
        return JSONResponse({"error": "Robot not found"}, status_code=404)

    ssh_host = _host_from_url(robot.ws_url)
    import uuid as _uuid
    from pathlib import Path as _Path
    from app.models.bag import Bag

    remote_filename = _Path(body.path).name
    bag_name = (body.name or "").strip() or _Path(remote_filename).stem
    bag_id = str(_uuid.uuid4())

    bag = Bag(
        id=_uuid.UUID(bag_id),
        name=bag_name,
        description=body.description or None,
        original_filename=remote_filename,
        bag_format="unknown",
        upload_path="",
        file_size_bytes=0,
        status="pending",
        tags=body.tags or [],
        team=body.team or [],
        uploaded_by_id=user.id if user else None,
        published=False,
    )
    db.add(bag)
    await db.commit()

    task_id = str(_uuid.uuid4())
    from worker.tasks.sftp_import import import_bag_from_robot
    import_bag_from_robot.apply_async(
        args=[bag_id, ssh_host, body.username, body.password, body.path],
        task_id=task_id,
    )
    return {"task_id": task_id, "bag_id": bag_id}


# ── Live view ─────────────────────────────────────────────────────

@live_router.get("/live", response_class=HTMLResponse)
async def live_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    accessible = await _accessible_robot_ids(user, db)

    result = await db.execute(
        select(Network).order_by(Network.name).options(selectinload(Network.robots))
    )
    all_networks = result.scalars().all()

    # Filter robots per network
    networks = []
    for net in all_networks:
        if accessible is None:
            net._visible_robots = sorted(net.robots, key=lambda r: r.name)
        else:
            net._visible_robots = sorted(
                [r for r in net.robots if r.id in accessible], key=lambda r: r.name
            )
        if net._visible_robots:
            networks.append(net)

    ungrouped_result = await db.execute(
        select(Robot).where(Robot.network_id.is_(None)).order_by(Robot.name)
    )
    all_ungrouped = ungrouped_result.scalars().all()
    ungrouped = all_ungrouped if accessible is None else [r for r in all_ungrouped if r.id in accessible]

    all_visible = [r for n in networks for r in n._visible_robots] + list(ungrouped)
    online = await _check_robots_online(all_visible)

    can_manage = user and (user.role == "admin" or getattr(user, "can_manage_robots", False))

    from app.models.lichtblick_layout import LichtblickLayout
    layouts_result = await db.execute(select(LichtblickLayout).order_by(LichtblickLayout.name))
    layouts = layouts_result.scalars().all()

    return templates.TemplateResponse(
        request,
        "live.html",
        {
            "networks": networks,
            "ungrouped": ungrouped,
            "online": online,
            "can_manage": can_manage,
            "layouts": layouts,
        },
    )


@live_router.post("/live/robots/create")
async def live_create_robot(
    name: str = Form(...),
    ws_url: str = Form(...),
    network_id: str = Form(""),
    use_proxy: str = Form("on"),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_robot_manager),
):
    name = name.strip()
    ws_url = _normalise_ws_url(ws_url)
    net_id = int(network_id) if network_id.strip() else None
    existing = await db.execute(select(Robot).where(Robot.name == name))
    if not existing.scalar_one_or_none():
        db.add(Robot(name=name, ws_url=ws_url, network_id=net_id, added_by_id=user.id, use_proxy=use_proxy == "on"))
        await db.commit()
    return RedirectResponse(url="/live", status_code=303)


# ── WebSocket proxy (access-controlled) ──────────────────────────

from fastapi import WebSocket


@live_router.websocket("/ws/robot/{robot_id}")
async def robot_ws_proxy(websocket: WebSocket, robot_id: int):
    user_id = websocket.session.get("user_id")
    if not user_id:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    from app.db.session import AsyncSessionLocal
    from app.services.auth_service import get_user_by_id

    async with AsyncSessionLocal() as db:
        user = await get_user_by_id(db, uuid.UUID(user_id))
        has_access = await _require_robot_access(robot_id, user, db)
        robot = await db.get(Robot, robot_id) if has_access else None

    if not has_access or not robot:
        await websocket.close(code=1008, reason="Access denied")
        return

    # Forward subprotocols so foxglove-bridge can negotiate (foxglove.websocket.v1 etc.)
    proto_header = websocket.headers.get("sec-websocket-protocol", "")
    requested_protocols = [p.strip() for p in proto_header.split(",") if p.strip()]

    import websockets as ws_lib

    try:
        connect_kwargs = {}
        if requested_protocols:
            connect_kwargs["subprotocols"] = requested_protocols

        async with ws_lib.connect(robot.ws_url, **connect_kwargs) as robot_conn:
            # Accept client with the subprotocol the robot selected
            negotiated = getattr(robot_conn, "subprotocol", None)
            try:
                await websocket.accept(subprotocol=negotiated)
            except Exception:
                return

            async def fwd_to_robot():
                try:
                    while True:
                        msg = await websocket.receive()
                        if msg["type"] == "websocket.disconnect":
                            break
                        if msg.get("bytes"):
                            await robot_conn.send(msg["bytes"])
                        elif msg.get("text"):
                            await robot_conn.send(msg["text"])
                except Exception:
                    pass
                finally:
                    await robot_conn.close()

            async def fwd_to_client():
                try:
                    async for msg in robot_conn:
                        if isinstance(msg, bytes):
                            await websocket.send_bytes(msg)
                        else:
                            await websocket.send_text(msg)
                except Exception:
                    pass
                finally:
                    try:
                        await websocket.close()
                    except Exception:
                        pass

            await asyncio.gather(fwd_to_robot(), fwd_to_client(), return_exceptions=True)

    except Exception as e:
        try:
            await websocket.close(code=1011, reason=f"Cannot connect to robot: {e}")
        except Exception:
            pass
