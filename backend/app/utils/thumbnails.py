import io
import math
import shutil
from pathlib import Path

from app.config import settings

EXTRACT_FPS    = 0.5   # frames per second of bag time to sample
MIN_FRAMES     = 8
MAX_FRAMES     = 60
SPRITE_COLS    = 5
SPRITE_FRAME_W = 320
SPRITE_FRAME_H = 180

IMAGE_TOPIC_TYPES = {
    "sensor_msgs/msg/Image",
    "sensor_msgs/msg/CompressedImage",
}


def _decode_frame(msg, msgtype):
    import numpy as np
    from PIL import Image
    try:
        from PIL import ImageOps
        if "CompressedImage" in msgtype:
            img = Image.open(io.BytesIO(bytes(msg.data)))
        else:
            arr = np.frombuffer(bytes(msg.data), dtype=np.uint8)
            h, w = msg.height, msg.width
            enc = msg.encoding.lower()
            if enc == "rgb8":
                img = Image.fromarray(arr.reshape(h, w, 3), "RGB")
            elif enc == "bgr8":
                img = Image.fromarray(arr.reshape(h, w, 3)[..., ::-1], "RGB")
            elif enc == "mono8":
                img = Image.fromarray(arr.reshape(h, w), "L").convert("RGB")
            else:
                return None
        return ImageOps.fit(img.convert("RGB"), (640, 360), Image.LANCZOS)
    except Exception:
        return None


def extract_frames(bag_id: str, mcap_path: str) -> int:
    """Sample frames from the bag and build a sprite sheet.

    Frame count = clamp(duration_sec * EXTRACT_FPS, MIN_FRAMES, MAX_FRAMES).

    Produces:
      {THUMB_DIR}/{bag_id}_sprite.jpg  — SPRITE_COLS-wide grid, 320×180 per cell
      {THUMB_DIR}/{bag_id}.jpg         — default thumbnail (middle frame, 640×360)

    Returns the number of frames in the sprite.
    """
    from rosbags.rosbag2 import Reader
    from rosbags.typesys import get_typestore, Stores
    from PIL import Image

    thumb_dir = Path(settings.THUMB_DIR)
    thumb_dir.mkdir(parents=True, exist_ok=True)

    typestore = get_typestore(Stores.LATEST)
    src = Path(mcap_path)
    if not src.is_file() and not src.is_dir():
        src = src.parent

    with Reader(src) as reader:
        image_conns = [c for c in reader.connections if c.msgtype in IMAGE_TOPIC_TYPES]
        if not image_conns:
            return 0

        target_conn = max(image_conns, key=lambda c: c.msgcount)
        total = target_conn.msgcount
        if total == 0:
            return 0

        duration_sec = 0.0
        if reader.end_time and reader.start_time:
            duration_sec = (reader.end_time - reader.start_time) / 1e9

        raw = int(duration_sec * EXTRACT_FPS) if duration_sec > 0 else 0
        n = max(MIN_FRAMES, min(MAX_FRAMES, raw or MIN_FRAMES))
        actual_n = min(n, total)

        want = {int(round(i * (total - 1) / max(actual_n - 1, 1))) for i in range(actual_n)}

        frames = []
        for idx, (conn, _, rawdata) in enumerate(reader.messages(connections=[target_conn])):
            if idx in want:
                msg = typestore.deserialize_cdr(rawdata, conn.msgtype)
                img = _decode_frame(msg, conn.msgtype)
                if img is not None:
                    frames.append(img)
                    want.discard(idx)
            if not want:
                break

    if not frames:
        return 0

    # Default thumbnail = middle frame at 640×360 (already sized by _decode_frame)
    frames[len(frames) // 2].save(thumb_dir / f"{bag_id}.jpg", "JPEG", quality=85)

    # Build sprite sheet: center-crop each frame to exact cell size (object-fit: cover)
    from PIL import ImageOps
    rows = math.ceil(len(frames) / SPRITE_COLS)
    sprite = Image.new("RGB", (SPRITE_COLS * SPRITE_FRAME_W, rows * SPRITE_FRAME_H), (15, 15, 15))
    for i, frame in enumerate(frames):
        sf = ImageOps.fit(frame.copy(), (SPRITE_FRAME_W, SPRITE_FRAME_H), Image.LANCZOS)
        col = i % SPRITE_COLS
        row = i // SPRITE_COLS
        sprite.paste(sf, (col * SPRITE_FRAME_W, row * SPRITE_FRAME_H))
    sprite.save(thumb_dir / f"{bag_id}_sprite.jpg", "JPEG", quality=82)

    return len(frames)


def frame_from_sprite(bag_id: str, frame_index: int) -> bool:
    """Extract a single frame from the sprite and save it as the thumbnail."""
    from PIL import Image

    thumb_dir = Path(settings.THUMB_DIR)
    sprite_path = thumb_dir / f"{bag_id}_sprite.jpg"
    if not sprite_path.exists():
        return False

    sprite = Image.open(sprite_path)
    col = frame_index % SPRITE_COLS
    row = frame_index // SPRITE_COLS
    x, y = col * SPRITE_FRAME_W, row * SPRITE_FRAME_H
    frame = sprite.crop((x, y, x + SPRITE_FRAME_W, y + SPRITE_FRAME_H))
    # Upscale to match default thumbnail dimensions
    frame = frame.resize((640, 360), Image.LANCZOS)
    frame.save(thumb_dir / f"{bag_id}.jpg", "JPEG", quality=85)
    return True


def extract_thumbnail(bag_id: str, mcap_path: str) -> Path | None:
    count = extract_frames(bag_id, mcap_path)
    return Path(settings.THUMB_DIR) / f"{bag_id}.jpg" if count else None
