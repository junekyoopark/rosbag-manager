import io
from pathlib import Path

from app.config import settings

IMAGE_TOPIC_TYPES = {
    "sensor_msgs/msg/Image",
    "sensor_msgs/msg/CompressedImage",
}


def extract_thumbnail(bag_id: str, mcap_path: str) -> Path | None:
    import numpy as np
    from PIL import Image
    from rosbags.rosbag2 import Reader
    from rosbags.typesys import get_typestore, Stores

    thumb_dir = Path(settings.THUMB_DIR)
    thumb_dir.mkdir(parents=True, exist_ok=True)
    out_path = thumb_dir / f"{bag_id}.jpg"

    typestore = get_typestore(Stores.LATEST)
    src = Path(mcap_path)
    src = src if src.is_file() else src.parent

    with Reader(src) as reader:
        image_conns = [
            c for c in reader.connections if c.msgtype in IMAGE_TOPIC_TYPES
        ]
        if not image_conns:
            return None

        target_conn = image_conns[0]

        for conn, timestamp, rawdata in reader.messages(connections=[target_conn]):
            msg = typestore.deserialize_cdr(rawdata, conn.msgtype)

            try:
                if "CompressedImage" in conn.msgtype:
                    img = Image.open(io.BytesIO(bytes(msg.data)))
                else:
                    arr = np.frombuffer(bytes(msg.data), dtype=np.uint8)
                    h, w = msg.height, msg.width
                    encoding = msg.encoding.lower()
                    if encoding == "rgb8":
                        arr = arr.reshape(h, w, 3)
                        img = Image.fromarray(arr, "RGB")
                    elif encoding == "bgr8":
                        arr = arr.reshape(h, w, 3)[..., ::-1]
                        img = Image.fromarray(arr, "RGB")
                    elif encoding == "mono8":
                        arr = arr.reshape(h, w)
                        img = Image.fromarray(arr, "L")
                    else:
                        continue

                img.thumbnail((640, 360))
                img.save(out_path, "JPEG", quality=85)
                return out_path
            except Exception:
                continue

    return None
