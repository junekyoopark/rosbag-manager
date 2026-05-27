import uuid as _uuid
import zipfile as _zf
from datetime import datetime, timezone
from pathlib import Path

from worker.celery_app import celery_app
from app.db.session import SyncSessionLocal
from app.models.bag import Bag
from app.models.nas_config import NASConfig


@celery_app.task(bind=True, max_retries=0, name="import_bag_from_nas")
def import_bag_from_nas(self, bag_id: str, nas_path: str):
    db = SyncSessionLocal()
    try:
        bag = db.get(Bag, bag_id)
        if not bag:
            raise ValueError(f"Bag {bag_id} not found")

        config = db.get(NASConfig, 1)
        if not config or not config.enabled:
            raise ValueError("NAS is not configured or disabled")

        from app.services.nas_service import (
            decrypt_password, synology_login, synology_logout, synology_download,
        )
        from app.config import settings

        password = decrypt_password(config.encrypted_password)

        self.update_state(state="PROGRESS", meta={"pct": 0, "step": "Connecting to NAS"})
        sid = synology_login(config.dsm_url, config.username, password, config.verify_ssl)

        nas_filename = Path(nas_path).name
        dest_path = Path(settings.UPLOADS_DIR) / bag_id / nas_filename
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        def on_progress(downloaded, total):
            pct = int(downloaded / total * 88) if total else 0
            self.update_state(state="PROGRESS", meta={"pct": pct + 2, "step": f"Downloading {pct + 2}%"})

        self.update_state(state="PROGRESS", meta={"pct": 2, "step": "Downloading from NAS"})
        synology_download(config.dsm_url, sid, nas_path, dest_path, config.verify_ssl, on_progress)
        synology_logout(config.dsm_url, sid, config.verify_ssl)

        # Handle zip
        actual_path = dest_path
        if dest_path.suffix.lower() == ".zip":
            self.update_state(state="PROGRESS", meta={"pct": 91, "step": "Extracting zip"})
            out_dir = dest_path.parent / f"{bag_id}_unzipped"
            out_dir.mkdir(parents=True, exist_ok=True)
            with _zf.ZipFile(dest_path, "r") as zf:
                zf.extractall(out_dir)
            dest_path.unlink(missing_ok=True)
            found = None
            for child in out_dir.rglob("metadata.yaml"):
                found = child.parent
                break
            if not found:
                for ext in (".mcap", ".db3", ".bag"):
                    candidates = list(out_dir.rglob(f"*{ext}"))
                    if candidates:
                        found = candidates[0]
                        break
            if not found:
                raise ValueError("No recognizable bag content found in zip")
            actual_path = found

        from app.services.bag_service import detect_format_from_extension

        size = (
            actual_path.stat().st_size
            if actual_path.is_file()
            else sum(f.stat().st_size for f in actual_path.rglob("*") if f.is_file())
        )
        bag.upload_path = str(actual_path)
        bag.file_size_bytes = size
        bag.bag_format = detect_format_from_extension(nas_filename)
        db.commit()

        # Create conversion job and dispatch
        self.update_state(state="PROGRESS", meta={"pct": 95, "step": "Queuing conversion"})
        from app.models.job import ConversionJob
        from app.services.job_service import dispatch_conversion

        job_id = _uuid.uuid4()
        job = ConversionJob(
            id=job_id,
            bag_id=bag.id,
            celery_task_id=str(job_id),
            status="queued",
            queued_at=datetime.now(timezone.utc),
        )
        db.add(job)
        bag.status = "converting"
        db.commit()
        dispatch_conversion(str(bag.id), str(job_id))
        return {"bag_id": bag_id}

    except Exception as exc:
        try:
            err_bag = db.get(Bag, bag_id)
            if err_bag:
                err_bag.status = "error"
                db.commit()
        except Exception:
            pass
        raise self.retry(exc=exc, countdown=0, max_retries=0)
    finally:
        db.close()
