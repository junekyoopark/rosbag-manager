import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path

from worker.celery_app import celery_app
from app.db.session import SyncSessionLocal
from app.models.bag import Bag


@celery_app.task(bind=True, max_retries=0, name="import_bag_from_robot")
def import_bag_from_robot(self, bag_id: str, ssh_host: str, ssh_user: str, ssh_password: str, remote_path: str):
    import paramiko

    db = SyncSessionLocal()
    try:
        bag = db.get(Bag, _uuid.UUID(bag_id))
        if not bag:
            raise ValueError(f"Bag {bag_id} not found")

        from app.config import settings

        remote_filename = Path(remote_path).name
        dest_path = Path(settings.UPLOADS_DIR) / bag_id / remote_filename
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        self.update_state(state="PROGRESS", meta={"pct": 1, "step": "Connecting to robot"})

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ssh_host, username=ssh_user, password=ssh_password, timeout=15, banner_timeout=15)
        sftp = ssh.open_sftp()

        remote_stat = sftp.stat(remote_path)
        total_bytes = remote_stat.st_size or 1
        downloaded = [0]

        def _progress(transferred, total):
            downloaded[0] = transferred
            pct = int(transferred / total * 88) + 2 if total else 2
            self.update_state(state="PROGRESS", meta={"pct": pct, "step": f"Downloading {pct}%"})

        self.update_state(state="PROGRESS", meta={"pct": 2, "step": "Downloading from robot"})
        sftp.get(remote_path, str(dest_path), callback=_progress)
        sftp.close()
        ssh.close()

        from app.services.bag_service import detect_format_from_extension
        size = dest_path.stat().st_size
        bag.upload_path = str(dest_path)
        bag.file_size_bytes = size
        bag.bag_format = detect_format_from_extension(remote_filename)
        db.commit()

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
            err_bag = db.get(Bag, _uuid.UUID(bag_id))
            if err_bag:
                err_bag.status = "error"
                db.commit()
        except Exception:
            pass
        raise self.retry(exc=exc, countdown=0, max_retries=0)
    finally:
        db.close()
