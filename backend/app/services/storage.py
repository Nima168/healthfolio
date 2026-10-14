"""Document storage behind a replaceable interface (backend_spec.md Section 6.3).

Local files in development; an S3 bucket in deployment (STORAGE_BACKEND=s3), with the same interface.
Keys are opaque `{user_id}/{document_id}` values, never user-supplied names.
"""

import os
import re
import tempfile
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, Protocol

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


class S3DocumentStorage:
    """Documents in a private S3 bucket, encrypted at rest. Credentials come from the AWS role, never from code."""

    def __init__(self, bucket: str, client: Any = None) -> None:
        self.bucket = bucket
        if client is None:
            import boto3  # only needed when S3 is used

            client = boto3.client("s3")
        self.client = client

    def save(self, key: str, chunks: Iterable[bytes]) -> None:
        _check_key(key)
        # Spooled: small uploads stay in memory, large ones go to a temporary file, never fully into memory.
        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as buffer:
            for chunk in chunks:
                buffer.write(chunk)
            buffer.seek(0)
            try:
                self.client.upload_fileobj(buffer, self.bucket, key, ExtraArgs={"ServerSideEncryption": "AES256"})
            except Exception as exc:  # botocore raises several unrelated error types
                raise StorageError("save_failed") from exc

    def open(self, key: str) -> Iterator[bytes]:
        _check_key(key)
        try:
            body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"]
        except Exception as exc:
            raise StorageError("open_failed") from exc

        def iterate() -> Iterator[bytes]:
            try:
                yield from body.iter_chunks(CHUNK_SIZE)
            finally:
                body.close()

        return iterate()

    def delete(self, key: str) -> None:
        _check_key(key)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            raise StorageError("delete_failed") from exc


def get_document_storage(settings: Settings) -> DocumentStorage:
    if settings.storage_backend == "s3":
        return S3DocumentStorage(settings.s3_bucket or "")
    return LocalDocumentStorage(settings.document_storage_dir)
