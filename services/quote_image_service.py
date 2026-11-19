"""Image selection and upload helpers for hotel quotes."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from flask import current_app
from sqlalchemy import select
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from extensions import db
from models.hotel import HotelImage


_IMAGE_EXTENSIONS_BY_MIME = {
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
    "image/gif": {".gif"},
}
MAX_QUOTE_IMAGE_BYTES = 10 * 1024 * 1024


class InvalidQuoteImage(ValueError):
    """Raised when an uploaded quote image is not supported."""


@dataclass(frozen=True)
class QuoteImageUpload:
    data: bytes
    extension: str
    digest: str


def hotel_cover_image_url(hotel_id: int) -> str | None:
    """Return the first sorted image from a hotel's gallery, if present."""
    return db.session.scalar(
        select(HotelImage.url)
        .where(
            HotelImage.hotel_id == hotel_id,
            HotelImage.media_type == "image",
        )
        .order_by(HotelImage.sort_order.asc(), HotelImage.id.asc())
        .limit(1)
    )


def hotel_cover_image_urls(hotel_ids: list[int]) -> dict[int, str]:
    """Return the first sorted gallery image for each requested hotel."""
    if not hotel_ids:
        return {}

    covers: dict[int, str] = {}
    rows = db.session.execute(
        select(HotelImage.hotel_id, HotelImage.url)
        .where(
            HotelImage.hotel_id.in_(hotel_ids),
            HotelImage.media_type == "image",
        )
        .order_by(
            HotelImage.sort_order.asc(),
            HotelImage.id.asc(),
        )
    )
    for hotel_id, image_url in rows:
        covers.setdefault(hotel_id, image_url)
    return covers


def validate_quote_image(file: FileStorage) -> QuoteImageUpload:
    """Read and validate an image upload without writing it to disk."""
    mime_type = (getattr(file, "mimetype", "") or "").lower()
    extensions = _IMAGE_EXTENSIONS_BY_MIME.get(mime_type)
    if not extensions:
        raise InvalidQuoteImage("Use a JPEG, PNG, WebP, or GIF image.")

    filename = secure_filename(getattr(file, "filename", "") or "")
    extension = Path(filename).suffix.lower()
    if extension not in extensions:
        raise InvalidQuoteImage("The image file extension does not match its type.")

    data = file.read(MAX_QUOTE_IMAGE_BYTES + 1)
    if not data:
        raise InvalidQuoteImage("The selected image is empty.")
    if len(data) > MAX_QUOTE_IMAGE_BYTES:
        raise InvalidQuoteImage("Quote images must be 10 MB or smaller.")

    return QuoteImageUpload(
        data=data,
        extension=extension,
        digest=hashlib.sha1(data).hexdigest(),
    )


def store_quote_image(upload: QuoteImageUpload) -> str:
    """Store a validated quote-specific image and return its public URL."""
    upload_root = Path(current_app.root_path) / current_app.config.get(
        "UPLOAD_FOLDER", "static/images/uploads"
    )
    target_dir = upload_root / "quotes"
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{upload.digest}{upload.extension}"
    target = target_dir / filename
    if not target.exists():
        target.write_bytes(upload.data)

    return f"/static/images/uploads/quotes/{filename}"
