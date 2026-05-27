import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

from worker.celery_app import celery_app
from app.db.session import SyncSessionLocal
from app.models.bag import Bag
from app.models.job import ConversionJob
from app.config import settings


def detect_format(path: Path) -> str:
    if path.is_file():
        suffix = path.suffix.lower()
        if suffix == ".bag":
            return "ros1_bag"
        if suffix == ".mcap":
            return "mcap_single"
        if suffix == ".db3":
            return "ros2_db3"

    if path.is_dir():
        metadata_file = path / "metadata.yaml"
        if not metadata_file.exists():
            raise ValueError(f"No metadata.yaml in directory {path}")
        meta = yaml.safe_load(metadata_file.read_text())
        storage_id = (
            meta.get("rosbag2_bagfile_information", {}).get("storage_identifier", "")
        )
        if storage_id == "mcap":
            return "ros2_mcap"
        if storage_id == "sqlite3":
            return "ros2_db3"

    raise ValueError(f"Unrecognized bag format: {path}")



def _ros1_to_ros2_val(val, ts_ros2):
    """Recursively convert a ROS1 deserialized value to a ROS2 type (drops seq from Headers)."""
    import numpy as np
    if hasattr(val, '__msgtype__'):
        return _ros1_to_ros2_msg(val, ts_ros2)
    if isinstance(val, np.ndarray) and val.dtype == object and val.size > 0:
        return np.array([_ros1_to_ros2_val(v, ts_ros2) for v in val], dtype=object)
    return val


def _ros1_to_ros2_msg(msg, ts_ros2):
    """Re-create a deserialized ROS1 message as a ROS2 type object (seq stripped from Headers)."""
    ros2_cls = ts_ros2.types.get(msg.__msgtype__)
    if ros2_cls is None:
        return msg
    kwargs = {}
    for field_name in ros2_cls.__annotations__:
        if field_name == '__msgtype__':
            continue
        # ROS1 uses uppercase for some fields (e.g. CameraInfo: D/K/R/P vs d/k/r/p)
        val = getattr(msg, field_name, None)
        if val is None:
            val = getattr(msg, field_name.upper(), None)
        kwargs[field_name] = _ros1_to_ros2_val(val, ts_ros2)
    return ros2_cls(**kwargs)


def ros1_to_mcap(bag_path: Path, bag_id: str) -> Path:
    from rosbags.rosbag1 import Reader as Ros1Reader
    from rosbags.rosbag2 import Writer as Ros2Writer
    from rosbags.rosbag2.writer import StoragePlugin
    from rosbags.typesys import get_typestore, Stores

    out_dir = Path(settings.UPLOADS_DIR) / f"{bag_id}_mcap"
    if out_dir.exists():
        shutil.rmtree(out_dir)

    ts_ros1 = get_typestore(Stores.ROS1_NOETIC)  # for deserializing ROS1 binary (has seq)
    ts_ros2 = get_typestore(Stores.LATEST)        # for CDR schema + serialization (no seq)

    with Ros1Reader(bag_path) as reader:
        connections = list(reader.connections)
        with Ros2Writer(out_dir, version=9, storage_plugin=StoragePlugin.MCAP) as writer:
            conn_map = {}
            skipped = []
            for conn in connections:
                try:
                    ext_conn = writer.add_connection(
                        conn.topic,
                        conn.msgtype,
                        typestore=ts_ros2,
                    )
                    conn_map[conn.id] = ext_conn
                except Exception:
                    skipped.append(conn.topic)
            if skipped:
                import logging
                logging.getLogger(__name__).warning(
                    "Skipped topics with unknown types: %s", skipped
                )
            if not conn_map:
                raise RuntimeError(
                    f"No convertible topics found. All {len(skipped)} topics have unknown message types."
                )
            deser_errors: set[str] = set()
            for conn, timestamp, rawdata in reader.messages():
                if conn.id not in conn_map:
                    continue
                try:
                    msg_ros1 = ts_ros1.deserialize_ros1(rawdata, conn.msgtype)
                    msg_ros2 = _ros1_to_ros2_msg(msg_ros1, ts_ros2)
                    # Rerun drops entities with empty frame names — derive one from the topic
                    if hasattr(msg_ros2, 'header') and not getattr(msg_ros2.header, 'frame_id', None):
                        msg_ros2.header.frame_id = '_anon/' + conn.topic.lstrip('/')
                    cdr = ts_ros2.serialize_cdr(msg_ros2, conn.msgtype)
                    writer.write(conn_map[conn.id], timestamp, cdr)
                except Exception as e:
                    if conn.msgtype not in deser_errors:
                        import logging
                        logging.getLogger(__name__).warning(
                            "Skipping messages for %s (%s): %s", conn.topic, conn.msgtype, e
                        )
                        deser_errors.add(conn.msgtype)

    mcap_files = list(out_dir.glob("*.mcap"))
    if not mcap_files:
        raise RuntimeError(f"rosbags did not produce a .mcap file in {out_dir}")
    return mcap_files[0]


def ros2_db3_to_mcap(bag_path: Path, bag_id: str) -> Path:
    from rosbags.rosbag2 import Reader, Writer
    from rosbags.rosbag2.writer import StoragePlugin

    out_dir = Path(settings.UPLOADS_DIR) / f"{bag_id}_mcap"
    if out_dir.exists():
        shutil.rmtree(out_dir)

    with Reader(bag_path) as reader:
        with Writer(out_dir, version=9, storage_plugin=StoragePlugin.MCAP) as writer:
            conn_map = {}
            for conn in reader.connections:
                out_conn = writer.add_connection(
                    conn.topic,
                    conn.msgtype,
                    typestore=reader.typestore,
                )
                conn_map[conn.id] = out_conn
            # Track which topics need frame_id patching (checked on first message)
            needs_patch: dict[str, bool] = {}
            for conn, timestamp, data in reader.messages():
                topic = conn.topic
                if topic not in needs_patch:
                    try:
                        probe = reader.typestore.deserialize_cdr(data, conn.msgtype)
                        needs_patch[topic] = (
                            hasattr(probe, 'header') and
                            not getattr(probe.header, 'frame_id', None)
                        )
                    except Exception:
                        needs_patch[topic] = False
                if needs_patch[topic]:
                    try:
                        msg = reader.typestore.deserialize_cdr(data, conn.msgtype)
                        msg.header.frame_id = '_anon/' + topic.lstrip('/')
                        data = reader.typestore.serialize_cdr(msg, conn.msgtype)
                    except Exception:
                        pass
                writer.write(conn_map[conn.id], timestamp, data)

    mcap_files = list(out_dir.glob("*.mcap"))
    if not mcap_files:
        raise RuntimeError(f"rosbags did not produce a .mcap file in {out_dir}")
    return mcap_files[0]


def mcap_to_rrd(mcap_path: Path, bag_id: str) -> Path:
    import logging
    log = logging.getLogger(__name__)

    out_rrd = Path(settings.RRD_DIR) / f"{bag_id}.rrd"
    out_rrd.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "rerun", "mcap", "convert",
        str(mcap_path),
        "-o", str(out_rrd),
        "--application-id", bag_id,
        "--recording-id", bag_id,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

    # Always surface rerun's output so skipped topics are visible in worker logs
    if result.stdout.strip():
        log.info("rerun mcap convert stdout [%s]:\n%s", bag_id, result.stdout.strip())
    if result.stderr.strip():
        log.warning("rerun mcap convert stderr [%s]:\n%s", bag_id, result.stderr.strip())

    if result.returncode != 0:
        raise RuntimeError(
            f"rerun mcap convert failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    if not out_rrd.exists():
        raise RuntimeError(f"rerun mcap convert succeeded but {out_rrd} not found")

    return out_rrd


def _patch_mcap_empty_frameids(mcap_path: Path, bag_id: str) -> Path:
    """
    Scan the MCAP for messages whose header.frame_id is empty.
    If any are found, write a patched copy and return its path;
    otherwise return the original path unchanged.
    """
    from rosbags.rosbag2 import Reader, Writer
    from rosbags.rosbag2.writer import StoragePlugin

    needs_patch: dict[str, bool] = {}
    with Reader(mcap_path) as reader:
        all_topics = {c.topic for c in reader.connections}
        for conn, timestamp, data in reader.messages():
            if conn.topic in needs_patch:
                continue
            try:
                msg = reader.typestore.deserialize_cdr(data, conn.msgtype)
                needs_patch[conn.topic] = (
                    hasattr(msg, 'header') and not getattr(msg.header, 'frame_id', None)
                )
            except Exception:
                needs_patch[conn.topic] = False
            if needs_patch.keys() >= all_topics:
                break  # every topic sampled — no need to read further

    if not any(needs_patch.values()):
        return mcap_path

    out_dir = Path(settings.UPLOADS_DIR) / f"{bag_id}_mcap_patched"
    if out_dir.exists():
        shutil.rmtree(out_dir)

    with Reader(mcap_path) as reader:
        with Writer(out_dir, version=9, storage_plugin=StoragePlugin.MCAP) as writer:
            conn_map = {}
            for conn in reader.connections:
                conn_map[conn.id] = writer.add_connection(
                    conn.topic, conn.msgtype, typestore=reader.typestore
                )
            for conn, timestamp, data in reader.messages():
                if needs_patch.get(conn.topic):
                    try:
                        msg = reader.typestore.deserialize_cdr(data, conn.msgtype)
                        msg.header.frame_id = '_anon/' + conn.topic.lstrip('/')
                        data = reader.typestore.serialize_cdr(msg, conn.msgtype)
                    except Exception:
                        pass
                writer.write(conn_map[conn.id], timestamp, data)

    mcap_files = list(out_dir.glob("*.mcap"))
    return mcap_files[0] if mcap_files else mcap_path


def _update_progress(task, job: ConversionJob, db, pct: int, step: str):
    task.update_state(state="PROGRESS", meta={"pct": pct, "step": step})
    job.status = "progress"
    job.progress_pct = pct
    job.current_step = step
    db.commit()


@celery_app.task(bind=True, max_retries=1, name="convert_bag")
def convert_bag(self, bag_id: str):
    db = SyncSessionLocal()
    bag = None
    job = None
    try:
        bag = db.get(Bag, bag_id)
        if not bag:
            raise ValueError(f"Bag {bag_id} not found")

        job = bag.job
        job.started_at = datetime.now(timezone.utc)
        job.worker_hostname = self.request.hostname
        db.commit()

        _update_progress(self, job, db, 0, "Detecting bag format")
        bag_format = detect_format(Path(bag.upload_path))

        mcap_path = None
        if bag_format == "ros1_bag":
            _update_progress(self, job, db, 10, "Converting ROS1 bag → MCAP")
            mcap_path = ros1_to_mcap(Path(bag.upload_path), bag_id)

        elif bag_format == "ros2_db3":
            _update_progress(self, job, db, 10, "Converting ROS2 db3 → MCAP")
            mcap_path = ros2_db3_to_mcap(Path(bag.upload_path), bag_id)

        elif bag_format in ("ros2_mcap", "mcap_single"):
            _update_progress(self, job, db, 10, "Checking MCAP frame IDs")
            mcap_path = _patch_mcap_empty_frameids(Path(bag.upload_path), bag_id)

        _update_progress(self, job, db, 50, "Converting MCAP → RRD")
        rrd_path = mcap_to_rrd(mcap_path, bag_id)

        _update_progress(self, job, db, 80, "Extracting metadata")
        from worker.tasks.introspect import introspect_bag
        introspect_bag.delay(bag_id, str(rrd_path), str(mcap_path))

        _update_progress(self, job, db, 90, "Extracting thumbnail")
        from worker.tasks.introspect import extract_thumbnail_task
        extract_thumbnail_task.delay(bag_id, str(mcap_path))

        bag.rrd_path = str(rrd_path)
        bag.rrd_size_bytes = rrd_path.stat().st_size
        bag.rrd_url = f"/rrd/{rrd_path.name}"
        bag.status = "ready"
        job.status = "success"
        job.progress_pct = 100
        job.current_step = "Done"
        job.finished_at = datetime.now(timezone.utc)
        db.commit()

    except Exception as exc:
        if bag:
            bag.status = "error"
        if job:
            job.status = "failure"
            job.error_message = str(exc)
            job.finished_at = datetime.now(timezone.utc)
        db.commit()
        raise self.retry(exc=exc, countdown=0, max_retries=0)
    finally:
        db.close()
