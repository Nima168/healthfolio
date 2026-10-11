"""Document storage behind a replaceable interface (backend_spec.md Section 6.3).

Local files in development; object storage is added for deployment with the same interface.
Keys are opaque `{user_id}/{document_id}` values, never user-supplied names.
"""

import os
import re
import tempfile
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Protocol

from app.core.config import Settings

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_KEY_PATTERN = re.compile(rf"^{_UUID}/{_UUID}$")
CHUNK_SIZE = 64 * 1024


class StorageError(Exception):
    """The storage backend could not complete the operation."""


class DocumentStorage(Protocol):
    def save(self, key: str, chunks: Iterable[bytes]) -> None: ...
    def open(self, key: str) -> Iterator[bytes]: ...
    def delete(self, key: str) -> None: ...


def storage_key(user_id: object, document_id: object) -> str:
    return f"{user_id}/{document_id}"


def _check_key(key: str) -> None:
    # Only "{uuid}/{uuid}": no "..", no absolute paths, no separators of other kinds.
    if not _KEY_PATTERN.match(key):
        raise ValueError("Invalid storage key")


class LocalDocumentStorage:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        _check_key(key)
        return self.root / key

    def save(self, key: str, chunks: Iterable[bytes]) -> None:
        """Write to a temporary file, then rename, so a crash never leaves a half-written document."""
        target = self._path(key)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(dir=target.parent, prefix=".upload-")
            try:
                with os.fdopen(fd, "wb") as handle:
                    for chunk in chunks:
                        handle.write(chunk)
                os.replace(temp_name, target)
            except BaseException:
                Path(temp_name).unlink(missing_ok=True)
                raise
        except OSError as exc:
            raise StorageError("save_failed") from exc

    def open(self, key: str) -> Iterator[bytes]:
        path = self._path(key)
        try:
            handle = path.open("rb")
        except OSError as exc:
            raise StorageError("open_failed") from exc

        def iterate() -> Iterator[bytes]:
            with handle:
                while chunk := handle.read(CHUNK_SIZE):
                    yield chunk

        return iterate()

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError("delete_failed") from exc


def get_document_storage(settings: Settings) -> DocumentStorage:
    return LocalDocumentStorage(settings.document_storage_dir)
