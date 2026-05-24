from pathlib import Path

from worker.celery_app import celery_app
from app.db.session import SyncSessionLocal
from app.models.bag import Bag
from app.models.topic import Topic


@celery_app.task(name="introspect_bag")
def introspect_bag(bag_id: str, rrd_path: str, mcap_path: str):
    from rosbags.rosbag2 import Reader

    db = SyncSessionLocal()
    try:
        bag = db.get(Bag, bag_id)
        if not bag:
            return

        mcap = Path(mcap_path)
        src = mcap if mcap.is_file() else mcap.parent

        with Reader(src) as reader:
            bag.start_time_ns = reader.start_time
            bag.end_time_ns = reader.end_time
            if reader.end_time and reader.start_time:
                bag.duration_sec = (reader.end_time - reader.start_time) / 1e9
            bag.message_count = sum(c.msgcount for c in reader.connections)

            db.query(Topic).filter(Topic.bag_id == bag_id).delete()

            for conn in reader.connections:
                duration_ns = (reader.end_time or 0) - (reader.start_time or 0)
                freq = (
                    conn.msgcount / (duration_ns / 1e9)
                    if duration_ns > 0
                    else 0
                )
                topic = Topic(
                    bag_id=bag_id,
                    name=conn.topic,
                    msg_type=conn.msgtype,
                    message_count=conn.msgcount,
                    frequency_hz=round(freq, 2),
                    serialization_format=getattr(conn, "serialization_format", None),
                )
                db.add(topic)

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@celery_app.task(name="extract_thumbnail_task")
def extract_thumbnail_task(bag_id: str, mcap_path: str):
    from app.utils.thumbnails import extract_thumbnail
    from app.db.session import SyncSessionLocal

    db = SyncSessionLocal()
    try:
        result = extract_thumbnail(bag_id, mcap_path)
        if result:
            bag = db.get(Bag, bag_id)
            if bag:
                bag.thumbnail_path = str(result)
                db.commit()
    except Exception:
        pass
    finally:
        db.close()
