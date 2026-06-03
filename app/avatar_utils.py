"""Profile avatar upload, storage, and cleanup."""

from __future__ import annotations

import io
from pathlib import Path

from flask import current_app
from PIL import Image
from werkzeug.datastructures import FileStorage

from . import db
from .models import User

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_BYTES = 2 * 1024 * 1024
AVATAR_SIZE = (256, 256)


def _upload_dir() -> Path:
    return Path(current_app.config["UPLOAD_AVATAR_DIR"])


def avatar_disk_path(user_id: int, filename: str | None) -> Path | None:
    if not filename:
        return None
    return _upload_dir() / filename


def avatar_exists(user_id: int) -> bool:
    user = db.session.get(User, user_id)
    if not user or not user.avatar_filename:
        return False
    path = avatar_disk_path(user_id, user.avatar_filename)
    return path is not None and path.is_file()


def delete_avatar_file(user_id: int, filename: str | None) -> None:
    path = avatar_disk_path(user_id, filename)
    if path and path.is_file():
        path.unlink(missing_ok=True)


def save_avatar(user_id: int, file_storage: FileStorage) -> str:
    if not file_storage or not file_storage.filename:
        raise ValueError("No file selected.")

    ext = Path(file_storage.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Use JPG, PNG, or WebP (max 2 MB).")

    raw = file_storage.read()
    if not raw:
        raise ValueError("Uploaded file is empty.")
    if len(raw) > MAX_BYTES:
        raise ValueError("Image must be 2 MB or smaller.")

    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except Exception as exc:
        raise ValueError("Could not read image file.") from exc

    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.mode else "RGB")

    if image.mode == "RGBA":
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[3])
        image = background
    else:
        image = image.convert("RGB")

    image.thumbnail(AVATAR_SIZE, Image.Resampling.LANCZOS)

    upload_dir = _upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{user_id}.webp"
    out_path = upload_dir / filename
    image.save(out_path, format="WEBP", quality=85)
    return filename
