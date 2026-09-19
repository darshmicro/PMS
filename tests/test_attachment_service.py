import pytest
from fastapi import HTTPException

from app.services.attachment_service import (
    ensure_exactly_one_target,
    generate_stored_filename,
    sanitize_filename,
    validate_extension,
    validate_size,
    virus_scan_hook,
)


def test_sanitize_filename_strips_path_traversal():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\windows\\win.ini") == "win.ini"


def test_sanitize_filename_replaces_unsafe_characters():
    assert sanitize_filename("my report (final)!.pdf") == "my_report_final_.pdf"


def test_sanitize_filename_rejects_empty_result():
    with pytest.raises(HTTPException) as exc_info:
        sanitize_filename("")
    assert exc_info.value.status_code == 400


def test_validate_extension_allows_listed_types():
    for name in ("evidence.pdf", "scan.PNG", "report.xlsx"):
        validate_extension(name)  # should not raise


def test_validate_extension_rejects_unlisted_types():
    with pytest.raises(HTTPException) as exc_info:
        validate_extension("script.exe")
    assert exc_info.value.status_code == 400


def test_validate_size_rejects_empty_file():
    with pytest.raises(HTTPException) as exc_info:
        validate_size(0, max_mb=25)
    assert exc_info.value.status_code == 400


def test_validate_size_rejects_oversized_file():
    with pytest.raises(HTTPException) as exc_info:
        validate_size(26 * 1024 * 1024, max_mb=25)
    assert exc_info.value.status_code == 400


def test_validate_size_allows_within_cap():
    validate_size(1024, max_mb=25)  # should not raise


def test_ensure_exactly_one_target_rejects_both():
    with pytest.raises(HTTPException) as exc_info:
        ensure_exactly_one_target(1, 2)
    assert exc_info.value.status_code == 400


def test_ensure_exactly_one_target_rejects_neither():
    with pytest.raises(HTTPException) as exc_info:
        ensure_exactly_one_target(None, None)
    assert exc_info.value.status_code == 400


def test_ensure_exactly_one_target_allows_kpi_only():
    ensure_exactly_one_target(1, None)  # should not raise


def test_ensure_exactly_one_target_allows_employee_only():
    ensure_exactly_one_target(None, 1)  # should not raise


def test_virus_scan_hook_is_a_documented_noop():
    assert virus_scan_hook(b"some bytes") is None


def test_generate_stored_filename_is_unique_and_keeps_extension():
    first = generate_stored_filename("evidence.pdf")
    second = generate_stored_filename("evidence.pdf")
    assert first != second
    assert first.endswith(".pdf")
    assert second.endswith(".pdf")
