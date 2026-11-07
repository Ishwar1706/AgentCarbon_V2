"""Safe evidence-file storage (type whitelist, magic-byte checks, hashing)."""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.core.config import settings

MAX_BYTES = 10 * 1024 * 1024
TYPES = {  # extension -> (content types, magic check)
    ".pdf": ({"application/pdf"}, lambda b: b.startswith(b"%PDF")),
    ".png": ({"image/png"}, lambda b: b.startswith(b"\x89PNG")),
    ".jpg": ({"image/jpeg"}, lambda b: b.startswith(b"\xff\xd8\xff")),
    ".jpeg": ({"image/jpeg"}, lambda b: b.startswith(b"\xff\xd8\xff")),
    ".txt": ({"text/plain"}, lambda b: _utf8(b)),
    ".csv": ({"text/csv", "text/plain", "application/vnd.ms-excel"}, lambda b: _utf8(b)),
    ".json": ({"application/json", "text/plain"}, lambda b: _json(b)),
}
DOCUMENT_TYPES = {
    "CALIBRATION_CERTIFICATE", "MAINTENANCE_RECORD", "UTILITY_BILL",
    "METER_PHOTO", "REPAIR_REPORT", "OTHER",
}
DATA_LABELS = {"USER_UPLOADED", "SYNTHETIC_DEMO"}


def _utf8(b: bytes) -> bool:
    try:
        b.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _json(b: bytes) -> bool:
    try:
        json.loads(b.decode("utf-8"))
        return True
    except Exception:
        return False


def store_upload(file: UploadFile, document_type: str, data_label: str):
    if document_type not in DOCUMENT_TYPES:
        raise HTTPException(400, f"document_type must be one of {sorted(DOCUMENT_TYPES)}")
    if data_label not in DATA_LABELS:
        raise HTTPException(400, f"data_label must be one of {sorted(DATA_LABELS)}")
    name = file.filename or "upload"
    ext = Path(name).suffix.lower()
    if ext not in TYPES:
        raise HTTPException(400, f"File type {ext or '(none)'} is not allowed. Allowed: {sorted(TYPES)}")
    content = file.file.read(MAX_BYTES + 1)
    if not content:
        raise HTTPException(400, "The file is empty.")
    if len(content) > MAX_BYTES:
        raise HTTPException(413, "The file is larger than 10 MB.")
    allowed_types, magic = TYPES[ext]
    if (file.content_type or "") not in allowed_types or not magic(content):
        raise HTTPException(400, "File content does not match its declared type.")
    stored = f"{uuid.uuid4().hex}{ext}"
    path = settings.path("upload_dir") / stored
    path.write_bytes(content)
    return {
        "stored_filename": stored, "original_filename": Path(name).name[:200],
        "content_type": file.content_type, "size_bytes": len(content),
        "sha256_hash": hashlib.sha256(content).hexdigest(),
    }
