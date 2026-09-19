"""
Attachment business rules (spec Section 4.5/9 / M22). See the model
module's docstring for the design decisions this leans on: exactly one of
EmployeeKPIID/RelatedEmployeeID per row, insert-only versioning via
FileVersion, and physical storage under settings.FILE_STORAGE_PATH.

Implements spec Section 9's "File upload" control list one control per
function: extension allow-list (validate_extension), size cap
(validate_size), stored outside web-root + filename sanitization
(sanitize_filename, save_file, generate_stored_filename), virus-scan hook
point (virus_scan_hook).
"""
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.attachment import Attachment

# The DDL gives no enumerated list (spec Section 9 only says "extension
# allow-list" in the abstract) - this is the minimum vocabulary that
# covers the evidence types Section 7's forms actually describe
# (documents, spreadsheets, scanned/photographed evidence), flagged here
# as an interpretive addition the same way Development Plan's
# CompletionStatus and PIP's Outcome vocabularies were.
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".png", ".jpg", ".jpeg"}

# Narrower allow-list used only for profile photos (app/api/routes/
# employees.py's photo endpoints) - a photo is always an image, so this
# is stricter than the general evidence-attachment list above rather than
# reusing it outright.
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
IMAGE_CONTENT_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp",
}

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(filename: str) -> str:
    """Strips any path component (defends against '../..' traversal in a
    caller-supplied name) and replaces anything outside a conservative
    safe-character set, per spec Section 9's "filename sanitization". The
    browser/OS on the far end of an intranet upload may be Windows, so
    both '/' and '\\' are treated as separators regardless of which
    platform this service itself runs on (pathlib.Path alone only splits
    on the host OS's own separator)."""
    normalized = filename.replace("\\", "/")
    name = Path(normalized).name
    name = _SAFE_NAME_RE.sub("_", name)
    if not name or name in (".", ".."):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid file name")
    return name


def validate_extension(filename: str) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{ext}' is not allowed. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )


def validate_image_extension(filename: str) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Image type '{ext}' is not allowed. Allowed types: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}",
        )


def image_content_type(stored_path: str) -> str:
    ext = Path(stored_path).suffix.lower()
    return IMAGE_CONTENT_TYPES.get(ext, "application/octet-stream")


def validate_size(size_bytes: int, max_mb: int) -> None:
    max_bytes = max_mb * 1024 * 1024
    if size_bytes <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
    if size_bytes > max_bytes:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"File exceeds the {max_mb} MB upload size cap",
        )


def ensure_exactly_one_target(employee_kpi_id: int | None, related_employee_id: int | None) -> None:
    """Exactly one of EmployeeKPIID/RelatedEmployeeID must be set - see
    model docstring."""
    if bool(employee_kpi_id) == bool(related_employee_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Provide exactly one of employee_kpi_id or related_employee_id, not both and not neither",
        )


def virus_scan_hook(file_bytes: bytes) -> None:
    """Spec Section 9 asks for a "virus-scan hook point" - this build has
    no real anti-malware engine to integrate with (none is reachable from
    this environment), so this function is that hook point: every upload
    is routed through it before being written to disk, and a future
    deployment wires a real scanner in here (raising HTTPException(422) on
    a positive match) without touching any caller. As shipped it is a
    documented no-op and always passes.
    """
    return None


def generate_stored_filename(original_filename: str) -> str:
    """Never reuses the caller-supplied name on disk (spec Section 9:
    "stored outside web-root, filename sanitization") - a random,
    collision-proof name with the original extension preserved only for
    the OS/tooling that might care about it."""
    ext = Path(original_filename).suffix.lower()
    return f"{uuid.uuid4().hex}{ext}"


def next_file_version(
    db: Session, employee_kpi_id: int | None, related_employee_id: int | None, file_name: str,
) -> int:
    """The next FileVersion for this logical slot - see model docstring."""
    current_max = (
        db.query(func.max(Attachment.FileVersion))
        .filter(
            Attachment.EmployeeKPIID == employee_kpi_id,
            Attachment.RelatedEmployeeID == related_employee_id,
            Attachment.FileName == file_name,
        )
        .scalar()
    )
    return (current_max or 0) + 1


def storage_root() -> Path:
    settings = get_settings()
    root = Path(settings.FILE_STORAGE_PATH) if settings.FILE_STORAGE_PATH else Path("storage/attachments")
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_file(stored_filename: str, content: bytes) -> str:
    """Writes the file under storage_root() and returns the relative
    StoredPath to persist on the Attachment row (never the absolute
    filesystem path, so the storage root can move without a data
    migration)."""
    root = storage_root()
    (root / stored_filename).write_bytes(content)
    return stored_filename


def read_file(stored_path: str) -> bytes:
    path = storage_root() / stored_path
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Stored file is missing from disk")
    return path.read_bytes()


def delete_file(stored_path: str) -> None:
    """Best-effort delete (used when a profile photo is replaced or
    removed - unlike Attachment rows, which are insert-only history, a
    photo has exactly one live copy per employee, so the old file is
    cleaned up rather than kept). Silently does nothing if the file is
    already gone."""
    path = storage_root() / stored_path
    if path.is_file():
        path.unlink()
