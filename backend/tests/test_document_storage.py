import uuid

import pytest

from app.services.document_validation import detect_media_type, sanitise_filename
from app.services.storage import LocalDocumentStorage, storage_key

PDF = b"%PDF-1.4\n%synthetic\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (PDF, "application/pdf"),
        (PNG, "image/png"),
        (JPEG, "image/jpeg"),
        (b"<html><script>alert(1)</script>", None),  # an HTML file renamed to .pdf
        (b"MZ\x90\x00", None),  # a Windows executable
        (b"PK\x03\x04", None),  # a zip / Office document
        (b"", None),
    ],
)
def test_media_type_comes_from_content(content, expected):
    assert detect_media_type(content[:8]) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("blood test.pdf", "blood test.pdf"),
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("C:\\Users\\me\\scan.png", "scan.png"),
        ("evil\x00name\x1f.pdf", "evilname.pdf"),
        ("   ", "document.pdf"),
        (None, "document.pdf"),
        ("..", "document.pdf"),
    ],
)
def test_sanitise_filename(name, expected):
    assert sanitise_filename(name, "application/pdf") == expected


def test_sanitise_filename_truncates_but_keeps_extension():
    name = sanitise_filename("x" * 300 + ".pdf", "application/pdf")

    assert len(name) == 255
    assert name.endswith(".pdf")


def test_local_storage_round_trip_and_delete(tmp_path):
    storage = LocalDocumentStorage(tmp_path)
    key = storage_key(uuid.uuid4(), uuid.uuid4())

    storage.save(key, iter([b"part one, ", b"part two"]))
    assert b"".join(storage.open(key)) == b"part one, part two"
    assert not list(tmp_path.rglob(".upload-*")), "temporary file must be renamed away"

    storage.delete(key)
    assert not (tmp_path / key).exists()
    storage.delete(key)  # deleting twice is harmless


@pytest.mark.parametrize("bad_key", ["../outside", "/etc/passwd", "a/b", f"{uuid.uuid4()}/../../x", ""])
def test_local_storage_rejects_unsafe_keys(tmp_path, bad_key):
    storage = LocalDocumentStorage(tmp_path)

    with pytest.raises(ValueError):
        storage.save(bad_key, iter([b"x"]))


def test_failed_save_leaves_no_partial_file(tmp_path):
    storage = LocalDocumentStorage(tmp_path)
    key = storage_key(uuid.uuid4(), uuid.uuid4())

    def broken_chunks():
        yield b"first chunk"
        raise RuntimeError("connection dropped")

    with pytest.raises(RuntimeError):
        storage.save(key, broken_chunks())
    assert not any(path.is_file() for path in tmp_path.rglob("*"))
