from pathlib import Path


def get_bag_info(upload_path: str) -> dict:
    """
    Extract basic metadata (topics, duration, message count) without converting.
    Returns a dict suitable for pre-populating Bag columns.
    """
    path = Path(upload_path)

    try:
        if path.suffix.lower() == ".bag":
            return _ros1_info(path)
        else:
            return _ros2_info(path)
    except Exception:
        return {}


def _ros1_info(path: Path) -> dict:
    from rosbags.rosbag1 import Reader

    with Reader(path) as reader:
        connections = list(reader.connections)
        start_ns = reader.start_time
        end_ns = reader.end_time
        duration = (end_ns - start_ns) / 1e9 if end_ns and start_ns else None
        message_count = sum(c.msgcount for c in connections)
        topics = [
            {
                "name": c.topic,
                "msg_type": c.msgtype,
                "message_count": c.msgcount,
            }
            for c in connections
        ]
    return {
        "start_time_ns": start_ns,
        "end_time_ns": end_ns,
        "duration_sec": duration,
        "message_count": message_count,
        "topics": topics,
    }


def _ros2_info(path: Path) -> dict:
    from rosbags.rosbag2 import Reader

    src = path if path.is_file() else path
    with Reader(src) as reader:
        connections = list(reader.connections)
        start_ns = reader.start_time
        end_ns = reader.end_time
        duration = (end_ns - start_ns) / 1e9 if end_ns and start_ns else None
        message_count = sum(c.msgcount for c in connections)
        topics = [
            {
                "name": c.topic,
                "msg_type": c.msgtype,
                "message_count": c.msgcount,
            }
            for c in connections
        ]
    return {
        "start_time_ns": start_ns,
        "end_time_ns": end_ns,
        "duration_sec": duration,
        "message_count": message_count,
        "topics": topics,
    }
