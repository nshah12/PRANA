"""Tests for zip-bomb defence in batch upload (finding H4)."""
import io
import zipfile

import pytest
from fastapi import HTTPException

from routers.ingest import _assert_not_zip_bomb


def _zip(files: dict[str, bytes]) -> zipfile.ZipFile:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    buf.seek(0)
    return zipfile.ZipFile(buf)


def test_normal_archive_passes():
    zf = _zip({"a.pdf": b"%PDF-1.4 hello world" * 50, "b.pdf": b"%PDF-1.4 more" * 50})
    _assert_not_zip_bomb(zf)  # must not raise


def test_high_compression_ratio_is_rejected():
    # 2 MB of zeros compresses to a few KB → ratio well above the 200x cap.
    zf = _zip({"bomb.pdf": b"\x00" * (2 * 1024 * 1024)})
    with pytest.raises(HTTPException) as e:
        _assert_not_zip_bomb(zf)
    assert e.value.status_code == 413
    assert e.value.detail == "ZIP_BOMB_DETECTED"


def test_empty_and_dir_entries_do_not_crash():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("folder/", b"")          # directory-like entry
        z.writestr("folder/ok.pdf", b"%PDF-1.4 tiny")
    buf.seek(0)
    _assert_not_zip_bomb(zipfile.ZipFile(buf))  # must not raise
