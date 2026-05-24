from pathlib import Path

from worker.celery_app import celery_app
from app.db.session import SyncSessionLocal
from app.models.bag import Bag
from app.models.nas_config import NASConfig


@celery_app.task(bind=True, max_retries=1, name="upload_bag_to_nas")
def upload_bag_to_nas(self, bag_id: str, dest_path: str | None = None):
    db = SyncSessionLocal()
    try:
        bag = db.get(Bag, bag_id)
        if not bag:
            raise ValueError(f"Bag {bag_id} not found")

        config = db.get(NASConfig, 1)
        if not config or not config.enabled:
            raise ValueError("NAS upload is not configured or disabled")

        from app.services.nas_service import decrypt_password, synology_login, synology_logout, synology_upload

        password = decrypt_password(config.encrypted_password)

        nas_dest = (dest_path or "").strip() or config.upload_path

        self.update_state(state="PROGRESS", meta={"pct": 0, "step": "Connecting to NAS"})
        sid = synology_login(config.dsm_url, config.username, password, config.verify_ssl)

        import re
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", bag.name).strip(" .")

        upload_path = Path(bag.upload_path)
        if upload_path.is_file():
            ext = Path(bag.original_filename).suffix  # e.g. ".bag" or ".mcap"
            filename = f"{safe_name}{ext}"
        else:
            filename = f"{safe_name}.zip"

        def on_progress(sent, total_bytes):
            pct = int(sent / total_bytes * 100) if total_bytes else 0
            self.update_state(state="PROGRESS", meta={"pct": pct, "step": f"Uploading {pct}%"})

        self.update_state(state="PROGRESS", meta={"pct": 1, "step": "Uploading to NAS"})

        if upload_path.is_file():
            synology_upload(config.dsm_url, sid, nas_dest, filename,
                            upload_path, config.verify_ssl, on_progress)
        else:
            # Directory bag (ROS2 multi-file) — zip it first
            import zipfile, tempfile
            self.update_state(state="PROGRESS", meta={"pct": 1, "step": "Zipping bag directory"})
            tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as zf:
                for f in upload_path.rglob("*"):
                    if f.is_file():
                        zf.write(f, f.relative_to(upload_path.parent))
            tmp_path = Path(tmp.name)
            self.update_state(state="PROGRESS", meta={"pct": 10, "step": "Uploading to NAS"})
            try:
                synology_upload(config.dsm_url, sid, nas_dest,
                                f"{bag.id}.zip", tmp_path, config.verify_ssl, on_progress)
            finally:
                tmp_path.unlink(missing_ok=True)

        synology_logout(config.dsm_url, sid, config.verify_ssl)

    except Exception as exc:
        raise self.retry(exc=exc, countdown=0, max_retries=0)
    finally:
        db.close()
